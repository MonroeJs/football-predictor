"""
全流程训练脚本 — v2 特征 + 模型升级

使用方法:
    python run_improved.py                   # 默认使用 EPL + 真实数据
    python run_improved.py --league EPL       # 指定联赛
    python run_improved.py --all-leagues       # 全部五大联赛
    python run_improved.py --only-backtest     # 只跑回测
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.absolute()))

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit, train_test_split
from sklearn.metrics import accuracy_score, classification_report, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV

from config import LEAGUES, ML_CONFIG, TRAIN_SEASONS
from src.utils import logger, setup_logger
from src.data_loader import download_league_data, standardize_dataframe, load_data
from src.features_v2 import build_features_v2, get_feature_columns_v2
from src.poisson import calc_attack_defense_strength, predict_match_poisson, evaluate_poisson_model


def evaluate_calibration(y_true, y_prob_pos):
    """计算 Brier score（衡量概率校准质量）"""
    try:
        return brier_score_loss(y_true, y_prob_pos)
    except Exception:
        return None


def train_evaluate_v2(
    league_key: str,
    force_download: bool = False,
    test_cutoff: str = "2425",
    report_dir: str | None = None,
) -> dict:
    """
    使用 v2 特征训练并评估模型

    Args:
        league_key: 联赛代码
        force_download: 强制重下
        test_cutoff: 测试集起始赛季（用>=该赛季的做测试）
        report_dir: 报告输出目录

    Returns:
        训练结果字典
    """
    tag = f"[{league_key}]"
    logger.info(f"\n{'='*60}")
    logger.info(f"{tag} 训练开始 ({datetime.now().strftime('%H:%M:%S')})")
    logger.info(f"{'='*60}")

    # 1. 加载数据
    all_seasons = TRAIN_SEASONS.copy()
    if test_cutoff not in all_seasons:
        all_seasons.append(test_cutoff)
    all_seasons = sorted(set(all_seasons))

    raw = download_league_data(league_key, season_codes=all_seasons, force=force_download)
    if raw.empty:
        logger.error(f"{tag} 无数据")
        return {"error": "无数据"}

    std = standardize_dataframe(raw)
    logger.info(f"{tag} 标准化后: {len(std)} 条")

    # 2. v2 特征工程
    df = build_features_v2(std)
    n_features = len([c for c in get_feature_columns_v2() if c in df.columns])
    logger.info(f"{tag} v2 特征工程: {len(df)} 行, {n_features} 个特征")

    if len(df) < 200:
        logger.error(f"{tag} 数据不足")
        return {"error": "数据不足"}

    # 3. 拆分训练/测试
    train_df = df[df["season_code"] < test_cutoff].copy()
    test_df = df[df["season_code"] >= test_cutoff].copy()

    if len(test_df) < 20:
        logger.warning(f"{tag} 测试集太小 ({len(test_df)} 场)，使用最后 20%")
        split = int(len(df) * 0.8)
        train_df = df.iloc[:split].copy()
        test_df = df.iloc[split:].copy()

    logger.info(f"{tag} 训练: {len(train_df)} 场, 测试: {len(test_df)} 场")

    # 4. 准备特征矩阵
    feature_cols = get_feature_columns_v2()
    available_features = [c for c in feature_cols if c in df.columns]

    X_train = train_df[available_features].fillna(0).values
    y_train = train_df["result"].map({"H": 0, "D": 1, "A": 2}).values
    X_test = test_df[available_features].fillna(0).values
    y_test = test_df["result"].map({"H": 0, "D": 1, "A": 2}).values

    results = {}
    predictions = {}

    # 5. 泊松基线
    logger.info(f"\n{tag} 泊松基线...")
    attack, defense, avg_h, avg_a = calc_attack_defense_strength(train_df)
    poisson_correct = 0
    poisson_brier = []

    for idx, row in test_df.iterrows():
        pred = predict_match_poisson(
            row["home_team"], row["away_team"],
            attack, defense, avg_h, avg_a,
            league=row.get("league"),
            elo_home=row.get("elo_home"),
            elo_away=row.get("elo_away"),
        )
        probs = [pred.home_win_prob, pred.draw_prob, pred.away_win_prob]
        predicted_result = ["H", "D", "A"][np.argmax(probs)]
        actual = row["result"]
        poisson_correct += (predicted_result == actual)

    poisson_acc = poisson_correct / len(test_df)
    results["poisson"] = round(poisson_acc, 4)
    logger.info(f"{tag} 泊松准确率: {poisson_acc:.2%}")

    # 6. ML 模型
    # 快速 RF + XGBoost
    models_config = {
        "rf": RandomForestClassifier(
            n_estimators=300, max_depth=10, min_samples_split=8,
            min_samples_leaf=4, class_weight="balanced",
            random_state=42, n_jobs=-1,
        ),
        "xgb": None,
    }

    try:
        import xgboost as xgb
        models_config["xgb"] = xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            eval_metric="mlogloss", random_state=42, verbosity=0,
            n_jobs=-1,
        )
    except ImportError:
        del models_config["xgb"]

    for model_name, model in models_config.items():
        logger.info(f"\n{tag} 训练 {model_name}...")

        # 时序交叉验证
        tscv = TimeSeriesSplit(n_splits=min(5, len(X_train) // 100))
        try:
            cv_scores = []
            for train_idx, val_idx in tscv.split(X_train):
                X_cv_train, X_cv_val = X_train[train_idx], X_train[val_idx]
                y_cv_train, y_cv_val = y_train[train_idx], y_train[val_idx]

                m = model.__class__(**model.get_params())
                m.fit(X_cv_train, y_cv_train)
                cv_scores.append(m.score(X_cv_val, y_cv_val))

            cv_mean = np.mean(cv_scores)
            cv_std = np.std(cv_scores)
            logger.info(f"  CV 准确率: {cv_mean:.2%} +/- {cv_std:.2%}")
        except Exception as e:
            logger.warning(f"  CV 失败: {e}")
            cv_mean = 0

        # 全量训练
        m = model.__class__(**model.get_params())
        m.fit(X_train, y_train)

        # 测试集评估
        y_pred = m.predict(X_test)
        y_prob = m.predict_proba(X_test)

        acc = accuracy_score(y_test, y_pred)

        # 各结果准确率
        correct_by_class = {}
        for i, label in enumerate(["H", "D", "A"]):
            mask = y_test == i
            if mask.sum() > 0:
                correct_by_class[label] = round((y_pred[mask] == i).sum() / mask.sum(), 4)
            else:
                correct_by_class[label] = 0

        # 置信度分层
        conf_thresholds = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
        conf_analysis = {}
        for thresh in conf_thresholds:
            mask = y_prob.max(axis=1) >= thresh
            if mask.sum() > 0:
                conf_analysis[f">={thresh:.0%}"] = {
                    "count": int(mask.sum()),
                    "accuracy": round((y_pred[mask] == y_test[mask]).sum() / mask.sum(), 4),
                    "coverage": round(mask.sum() / len(y_test), 4),
                }

        # 特征重要性
        fi = []
        if hasattr(m, "feature_importances_"):
            fi = sorted(zip(available_features, m.feature_importances_),
                       key=lambda x: -x[1])
            fi = [{"feature": f, "importance": round(i, 4)} for f, i in fi[:10]]

        results[model_name] = {
            "accuracy": round(acc, 4),
            "cv_accuracy": round(cv_mean, 4) if cv_mean else None,
            "per_class": correct_by_class,
            "confidence_analysis": conf_analysis,
            "feature_importance": fi,
        }

        predictions[model_name] = {
            "y_pred": y_pred.tolist(),
            "y_prob": y_prob.tolist(),
        }

        logger.info(f"  测试准确率: {acc:.2%} | H={correct_by_class.get('H', 0):.2%} "
                    f"D={correct_by_class.get('D', 0):.2%} A={correct_by_class.get('A', 0):.2%}")

    # 7. 集成预测（概率平均）
    ensemble_probs = None
    ensemble_count = 0
    for model_name in models_config:
        if model_name in predictions:
            p = np.array(predictions[model_name]["y_prob"])
            if ensemble_probs is None:
                ensemble_probs = p
            else:
                ensemble_probs += p
            ensemble_count += 1

    if ensemble_count > 1:
        ensemble_probs /= ensemble_count
        ensemble_pred = np.argmax(ensemble_probs, axis=1)
        ensemble_acc = accuracy_score(y_test, ensemble_pred)
        results["ensemble"] = round(ensemble_acc, 4)
        logger.info(f"  集成准确率: {ensemble_acc:.2%}")

    # 8. 总结
    print(f"\n{'='*60}")
    print(f"{tag} 训练总结 ({league_key})")
    print(f"{'='*60}")
    print(f"  数据:         训练 {len(train_df)} 场 / 测试 {len(test_df)} 场")
    print(f"  特征:         {n_features} 个")
    print(f"  泊松基线:     {results.get('poisson', 0):.2%}")
    for mn in models_config:
        if mn in results:
            r = results[mn]
            print(f"  {mn:12s}:       {r['accuracy']:.2%} "
                  f"(CV={r.get('cv_accuracy', 'N/A')}) "
                  f"H={r.get('per_class', {}).get('H', '?'):.0%} "
                  f"D={r.get('per_class', {}).get('D', '?'):.0%} "
                  f"A={r.get('per_class', {}).get('A', '?'):.0%}")
    if "ensemble" in results:
        print(f"  {'ensemble':12s}: {results['ensemble']:.2%}")

    # 9. 保存报告
    if report_dir:
        report_path = Path(report_dir)
        report_path.mkdir(parents=True, exist_ok=True)

        report = {
            "league": league_key,
            "date": datetime.now().isoformat(),
            "train_matches": len(train_df),
            "test_matches": len(test_df),
            "n_features": n_features,
            "results": results,
        }
        report_file = report_path / f"{league_key}_v2_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"报告已保存: {report_file}")

    return results


def run_all_leagues(force_download=False, report_dir=None):
    """跑全部五大联赛"""
    all_results = {}
    for league_key in LEAGUES:
        try:
            r = train_evaluate_v2(
                league_key,
                force_download=force_download,
                test_cutoff="2425",
                report_dir=report_dir,
            )
            all_results[league_key] = r
        except Exception as e:
            logger.error(f"{league_key} 失败: {e}")
            all_results[league_key] = {"error": str(e)}

    # 汇总
    print(f"\n{'='*60}")
    print("各联赛对比汇总")
    print(f"{'='*60}")
    print(f"{'联赛':12s} {'泊松':8s} {'RF':8s} {'GBDT':8s} {'LR':8s} {'Ensemble':10s}")
    print(f"{'-'*60}")
    for lk in LEAGUES:
        r = all_results.get(lk, {})
        poisson = f"{r.get('poisson', 0):.2%}" if isinstance(r.get('poisson'), float) else "N/A"
        rf = f"{r.get('rf', {}).get('accuracy', 0):.2%}" if isinstance(r.get('rf'), dict) else "N/A"
        gbdt = f"{r.get('gbdt', {}).get('accuracy', 0):.2%}" if isinstance(r.get('gbdt'), dict) else "N/A"
        lr = f"{r.get('lr', {}).get('accuracy', 0):.2%}" if isinstance(r.get('lr'), dict) else "N/A"
        ens = f"{r.get('ensemble', 0):.2%}" if isinstance(r.get('ensemble'), float) else "N/A"
        print(f"{lk:12s} {poisson:8s} {rf:8s} {gbdt:8s} {lr:8s} {ens:10s}")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="改进版训练")
    parser.add_argument("--league", default="EPL", help="联赛代码（默认 EPL）")
    parser.add_argument("--all-leagues", action="store_true", help="跑全部五大联赛")
    parser.add_argument("--force-download", action="store_true", help="强制重下数据")
    parser.add_argument("--test-cutoff", default="2425", help="测试赛季起始")
    args = parser.parse_args()

    report_dir = Path(__file__).parent / "docs" / "training_reports_v2"
    report_dir.mkdir(parents=True, exist_ok=True)

    if args.all_leagues:
        run_all_leagues(force_download=args.force_download, report_dir=report_dir)
    else:
        train_evaluate_v2(
            args.league,
            force_download=args.force_download,
            test_cutoff=args.test_cutoff,
            report_dir=str(report_dir),
        )
