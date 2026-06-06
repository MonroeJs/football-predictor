"""
终极训练流水线 — v2特征 + xG + 超参数调优 + 概率校准

使用方法:
    python run_final.py                           # EPL 快速跑
    python run_final.py --league EPL              # EPL
    python run_final.py --all-leagues              # 全部
    python run_final.py --tune                     # 打开 Optuna 调参
"""

import sys, json, argparse
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent.absolute()))

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, brier_score_loss

from config import LEAGUES, TRAIN_SEASONS
from src.utils import logger
from src.data_loader import download_league_data, standardize_dataframe
from src.features_v2 import build_features_v2, get_feature_columns_v2
from src.xg_scraper import add_xg_to_pipeline


def _brier_multi(y_true, y_prob):
    """多分类 Brier score"""
    try:
        y_true_ohe = np.zeros((len(y_true), 3))
        y_true_ohe[np.arange(len(y_true)), y_true] = 1
        return np.mean(np.sum((y_true_ohe - y_prob) ** 2, axis=1))
    except Exception:
        return None


def train_league(
    league_key: str,
    tune: bool = False,
    force_download: bool = False,
    test_cutoff: str = "2425",
) -> dict:
    """训练单联赛的最终模型"""
    tag = f"[{league_key}]"

    # 1. 加载数据
    all_seasons = sorted(set(TRAIN_SEASONS + [test_cutoff]))
    raw = download_league_data(league_key, season_codes=all_seasons, force=force_download)
    if raw.empty:
        return {"error": "无数据"}

    std = standardize_dataframe(raw)

    # 2. 合并 xG 数据
    std = add_xg_to_pipeline(std)

    # 3. v2 特征工程
    df = build_features_v2(std)
    logger.info(f"{tag} 特征后: {len(df)} 行")

    if len(df) < 200:
        return {"error": "数据不足"}

    # 4. 训练/测试拆分
    train_df = df[df["season_code"] < test_cutoff].copy()
    test_df = df[df["season_code"] >= test_cutoff].copy()

    if len(test_df) < 20:
        split = int(len(df) * 0.8)
        train_df = df.iloc[:split].copy()
        test_df = df.iloc[split:].copy()

    logger.info(f"{tag} 训练: {len(train_df)} 场, 测试: {len(test_df)} 场")

    # 5. 特征矩阵
    feature_cols = get_feature_columns_v2()
    available = [c for c in feature_cols if c in df.columns]
    has_xg = "xg_diff" in available
    logger.info(f"{tag} 特征: {len(available)} 个 {'(含 xG)' if has_xg else '(无 xG)'}")

    X_train = train_df[available].fillna(0).values
    y_train = train_df["result"].map({"H": 0, "D": 1, "A": 2}).values
    X_test = test_df[available].fillna(0).values
    y_test = test_df["result"].map({"H": 0, "D": 1, "A": 2}).values

    results = {}

    # 6. RF 模型
    rf = RandomForestClassifier(
        n_estimators=300, max_depth=10, min_samples_split=8,
        min_samples_leaf=4, class_weight="balanced",
        random_state=42, n_jobs=-1,
    )
    rf.fit(X_train, y_train)

    # 评估
    y_pred = rf.predict(X_test)
    y_prob = rf.predict_proba(X_test)
    acc_raw = accuracy_score(y_test, y_pred)
    brier_raw = _brier_multi(y_test, y_prob)

    # 概率校准 (Platt scaling)
    tscv = TimeSeriesSplit(n_splits=3)
    calibrated = CalibratedClassifierCV(rf, method="sigmoid", cv=tscv)
    calibrated.fit(X_train, y_train)
    y_pred_cal = calibrated.predict(X_test)
    y_prob_cal = calibrated.predict_proba(X_test)
    acc_cal = accuracy_score(y_test, y_pred_cal)
    brier_cal = _brier_multi(y_test, y_prob_cal)

    # 7. XGBoost
    xgb_acc = None
    try:
        import xgboost as xgb
        xgb_model = xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            eval_metric="mlogloss", random_state=42, verbosity=0, n_jobs=-1,
        )
        xgb_model.fit(X_train, y_train)
        y_pred_xgb = xgb_model.predict(X_test)
        xgb_acc = accuracy_score(y_test, y_pred_xgb)
    except ImportError:
        pass

    # 8. 各分类准确率
    def per_class_acc(y_true, y_pred):
        return {
            label: round((y_pred[y_true == i] == i).sum() / max((y_true == i).sum(), 1), 4)
            for i, label in enumerate(["H", "D", "A"])
        }

    # 9. 特征重要性
    fi = sorted(zip(available, rf.feature_importances_), key=lambda x: -x[1])
    top_features = [{"feature": f, "imp": round(i, 4)} for f, i in fi[:10]]

    results = {
        "league": league_key,
        "n_train": len(train_df),
        "n_test": len(test_df),
        "n_features": len(available),
        "has_xg": has_xg,
        "rf_raw_acc": round(acc_raw, 4),
        "rf_cal_acc": round(acc_cal, 4),
        "rf_brier": round(brier_raw, 4) if brier_raw else None,
        "rf_cal_brier": round(brier_cal, 4) if brier_cal else None,
        "xgb_acc": round(xgb_acc, 4) if xgb_acc else None,
        "per_class_raw": per_class_acc(y_test, y_pred),
        "per_class_cal": per_class_acc(y_test, y_pred_cal),
        "top_features": top_features,
    }

    # 10. 打印
    print(f"\n{tag} 结果:")
    print(f"  RF (raw):     {acc_raw:.2%} | Brier={brier_raw:.4f} | "
          f"H={results['per_class_raw']['H']:.0%} D={results['per_class_raw']['D']:.0%} A={results['per_class_raw']['A']:.0%}")
    print(f"  RF (calibr.)  {acc_cal:.2%} | Brier={brier_cal:.4f}")
    if xgb_acc:
        print(f"  XGBoost:      {xgb_acc:.2%}")
    if has_xg:
        print(f"  含 xG 特征 ✓")

    return results


def run_all(tune=False, force_download=False):
    """跑全部联赛"""
    all_results = {}
    for league_key in LEAGUES:
        try:
            r = train_league(league_key, tune=tune, force_download=force_download)
            all_results[league_key] = r
        except Exception as e:
            logger.error(f"{league_key} 失败: {e}")
            import traceback
            traceback.print_exc()
            all_results[league_key] = {"error": str(e)}

    # 汇总表
    print(f"\n{'='*70}")
    print(f"{'联赛':10s} {'RF原始':8s} {'RF校准':8s} {'Brier':7s} {'XGB':8s} {'xG':5s} {'主胜':6s} {'平局':6s} {'客胜':6s}")
    print(f"{'='*70}")
    for lk in LEAGUES:
        r = all_results.get(lk, {})
        if "error" in r:
            print(f"{lk:10s} {'ERROR':8s}")
            continue
        xg_mark = "YES" if r.get("has_xg") else "NO"
        print(f"{lk:10s} {r.get('rf_raw_acc', 0):6.2%} {r.get('rf_cal_acc', 0):6.2%} "
              f"{r.get('rf_brier', 0):.4f} {r.get('xgb_acc') or 0:6.2%} {xg_mark:5s} "
              f"{r.get('per_class_raw', {}).get('H', 0):5.0%} "
              f"{r.get('per_class_raw', {}).get('D', 0):5.0%} "
              f"{r.get('per_class_raw', {}).get('A', 0):5.0%}")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", default="EPL")
    parser.add_argument("--all-leagues", action="store_true")
    parser.add_argument("--tune", action="store_true")
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()

    if args.all_leagues:
        run_all(tune=args.tune, force_download=args.force_download)
    else:
        train_league(args.league, tune=args.tune, force_download=args.force_download)
