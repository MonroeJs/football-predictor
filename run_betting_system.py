#!/usr/bin/env python3
"""
置信度分层投注系统 — 回测运行器

预测 → 概率校准 → 置信度分层 → Kelly 资金管理 → 完整回测

使用方式:
    python run_betting_system.py                             # EPL 快速跑
    python run_betting_system.py --league EPL                # EPL
    python run_betting_system.py --all-leagues               # 全部五大联赛
    python run_betting_system.py --league EPL --model catboost  # 指定模型
    python run_betting_system.py --league EPL --no-kelly     # 等额投注对比
    python run_betting_system.py --league EPL --export       # 导出结果到 JSON
    python run_betting_system.py --compare                   # Kelly vs 等额 vs 全量对比
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).parent.absolute()))

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score

from config import LEAGUES
from src.utils import logger
from src.data_loader import download_league_data, standardize_dataframe
from src.features_v2 import build_features_v2, get_feature_columns_v2
from src.xg_scraper import add_xg_to_pipeline
from src.ml_models import FootballPredictor
from src.betting_system import (
    ConfidenceBettingSystem,
    run_tiered_backtest_with_model_probs,
    export_results,
    _print_results,
    ConfidenceTier,
    get_confidence_tier,
    KellyCalculator,
)

SEP = "=" * 64


# ─── 加载与特征 ───────────────────────────────────────────────

def load_and_build_features(
    league_key: str,
    test_cutoff: str = "2526",
    force_download: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """加载数据、合并 xG、构建 v2 特征，返回 (train_df, test_df, feature_cols)"""
    from config import TRAIN_SEASONS

    tag = f"[{league_key}]"
    all_seasons = sorted(set(TRAIN_SEASONS + [test_cutoff]))

    print(f"{tag} 加载数据 {all_seasons[0]}~{all_seasons[-1]}...")
    raw = download_league_data(league_key, season_codes=all_seasons, force=force_download)
    if raw.empty:
        return pd.DataFrame(), pd.DataFrame(), []

    std = standardize_dataframe(raw)

    # 合并 xG
    try:
        std = add_xg_to_pipeline(std)
        has_xg = "xg_home" in std.columns
        if has_xg:
            print(f"{tag} xG 数据合并成功 [OK]")
    except Exception as e:
        print(f"{tag} xG 跳过: {e}")
        has_xg = False

    # v2 特征
    df = build_features_v2(std)
    print(f"{tag} 特征后: {len(df)} 行 {len(df.columns)} 列")

    # 分割
    train_df = df[df["season_code"] < test_cutoff].copy()
    test_df = df[df["season_code"] >= test_cutoff].copy()

    if len(test_df) < 20:
        # 兜底：按 80/20 切
        split = int(len(df) * 0.8)
        train_df = df.iloc[:split].copy()
        test_df = df.iloc[split:].copy()

    print(f"{tag} 训练: {len(train_df)} 场  测试: {len(test_df)} 场")

    feature_cols = get_feature_columns_v2()
    available = [c for c in feature_cols if c in df.columns]
    print(f"{tag} 特征: {len(available)} 个 {'(含 xG)' if 'xg_diff' in available else '(无 xG)'}")

    return train_df, test_df, available


# ─── 模型训练 ─────────────────────────────────────────────────

def compute_calibration_factors(
    model,
    val_df: pd.DataFrame,
    feature_cols: list[str],
    min_samples: int = 20,
) -> dict[str, float]:
    """
    从验证集计算每个置信度分层的校准因子

    校准因子 = 该层实际准确率 / 该层平均预测概率
    如果 < 1.0，说明模型在该层过于自信；> 1.0 则过于保守。
    至少需要 min_samples 样本才计算，否则返回 1.0。

    Returns:
        {"VHigh": 0.85, "Elite": 0.95, ...}
    """
    available = [c for c in feature_cols if c in val_df.columns]
    X_val = val_df[available].fillna(0).values
    y_prob = model.predict_proba(X_val)
    y_pred = y_prob.argmax(axis=1)

    y_val = val_df["result"].map({"H": 0, "D": 1, "A": 2}).values

    tier_data = {}
    for i in range(len(val_df)):
        probs = y_prob[i]
        max_prob = probs.max()
        tier = get_confidence_tier(max_prob).value
        correct = int(y_pred[i] == y_val[i])

        if tier not in tier_data:
            tier_data[tier] = {"max_probs": [], "corrects": []}
        tier_data[tier]["max_probs"].append(max_prob)
        tier_data[tier]["corrects"].append(correct)

    cal_factors = {}
    for tier, data in tier_data.items():
        n = len(data["max_probs"])
        if n < min_samples:
            continue
        actual_acc = sum(data["corrects"]) / n
        avg_pred_prob = sum(data["max_probs"]) / n
        if avg_pred_prob > 0:
            factor = actual_acc / avg_pred_prob
            # 限制在合理范围 (0.6 ~ 1.5)
            factor = max(0.6, min(1.5, factor))
            cal_factors[tier] = round(factor, 3)
            print(f"    校准 {tier:12s}: avg_pred={avg_pred_prob:.2%}  actual={actual_acc:.2%}  factor={factor:.3f} ({n} 场)")

    return cal_factors


def train_best_model(
    train_df: pd.DataFrame,
    feature_cols: list[str],
    model_type: str = "catboost",
    league: str = "EPL",
) -> FootballPredictor:
    """训练最佳模型并返回"""
    tag = f"[{league}]"

    available = [c for c in feature_cols if c in train_df.columns]
    X_train = train_df[available].fillna(0).values
    y_train = train_df["result"].map({"H": 0, "D": 1, "A": 2}).values

    print(f"\n{tag} 训练 {model_type}...")

    if model_type == "catboost":
        from catboost import CatBoostClassifier
        model = CatBoostClassifier(
            iterations=500, depth=6, learning_rate=0.03,
            l2_leaf_reg=3, border_count=128,
            random_seed=42, verbose=False,
        )
    elif model_type == "random_forest":
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(
            n_estimators=300, max_depth=10, min_samples_split=8,
            min_samples_leaf=4, class_weight="balanced",
            random_state=42, n_jobs=-1,
        )
    elif model_type == "xgboost":
        import xgboost as xgb
        model = xgb.XGBClassifier(
            n_estimators=500, max_depth=6, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8,
            eval_metric="mlogloss", random_state=42, verbosity=0, n_jobs=-1,
        )
    elif model_type == "lightgbm":
        import lightgbm as lgb
        model = lgb.LGBMClassifier(
            n_estimators=500, max_depth=8, learning_rate=0.03,
            num_leaves=31, subsample=0.8, class_weight="balanced",
            random_state=42, verbose=-1,
        )
    else:
        raise ValueError(f"未知模型: {model_type}")

    model.fit(X_train, y_train)
    print(f"{tag} 训练完成 [OK]")

    # 包装成 FootballPredictor 以便复用 predict 逻辑
    predictor = FootballPredictor(model_type=model_type, league=league)
    predictor.feature_names = available
    predictor.model = model
    predictor.is_fitted = True
    predictor._used_features = available

    # 训练集评估
    y_pred = model.predict(X_train)
    acc = accuracy_score(y_train, y_pred)
    print(f"{tag} 训练集准确率: {acc:.2%}")

    return predictor


# ─── 单联赛回测 ──────────────────────────────────────────────

def backtest_league(
    league_key: str,
    model_type: str = "catboost",
    test_cutoff: str = "2526",
    initial_bankroll: float = 10000.0,
    min_edge: float = 0.03,
    use_kelly: bool = True,
    force_download: bool = False,
    verbose: bool = True,
    export: bool = False,
) -> dict:
    """完整单联赛回测流水线"""
    tag = f"[{league_key}]"

    print(f"\n{SEP}")
    print(f"  {league_key} ({LEAGUES[league_key]['name']})")
    print(f"  模型: {model_type}  |  "
          f"Kelly: {'ON' if use_kelly else 'OFF'}  |  "
          f"测试赛季: {test_cutoff}")
    print(SEP)

    # 1. 加载 + 特征
    train_df, test_df, feature_cols = load_and_build_features(
        league_key, test_cutoff, force_download,
    )
    if test_df.empty:
        print(f"{tag} 无测试数据，跳过")
        return {"error": "无数据"}

    # 2. 训练模型
    predictor = train_best_model(train_df, feature_cols, model_type, league_key)

    # 2b. 用最近 2 个赛季的验证数据计算校准因子
    print(f"\n{tag} 校准因子计算 (从训练集最近 2 赛季)...")
    val_seasons = sorted(train_df["season_code"].unique())[-3:]  # 最近 3 个赛季
    val_df = train_df[train_df["season_code"].isin(val_seasons)].copy()
    cal_factors = compute_calibration_factors(predictor.model, val_df, feature_cols)
    if cal_factors:
        print(f"{tag} 校准因子: {cal_factors}")
    else:
        print(f"{tag} 校准因子: 无 (样本不足)")

    # 3. 测试集预测
    available = [c for c in feature_cols if c in test_df.columns]
    X_test = test_df[available].fillna(0).values
    y_prob = predictor.model.predict_proba(X_test)
    y_pred = y_prob.argmax(axis=1)

    # 基础准确率
    y_test = test_df["result"].map({"H": 0, "D": 1, "A": 2}).values
    base_acc = accuracy_score(y_test, y_pred)
    print(f"{tag} 测试集准确率: {base_acc:.2%}")

    # 逐类准确率
    for label, code in [("H", 0), ("D", 1), ("A", 2)]:
        mask = y_test == code
        if mask.sum() > 0:
            cls_acc = (y_pred[mask] == code).sum() / mask.sum()
            print(f"    {label}: {cls_acc:.2%} ({mask.sum()} 场)")

    # 4. 置信度分层预测准确率（纯预测，不涉及投注）
    print(f"\n{tag} 置信度分层预测准确率:")
    pred_results = []
    for i in range(len(test_df)):
        probs = y_prob[i]
        max_prob = probs.max()
        tier = get_confidence_tier(max_prob).value
        correct = y_pred[i] == y_test[i]
        pred_results.append({"tier": tier, "correct": correct, "n": 1})

    pred_df = pd.DataFrame(pred_results)
    for t in ["Max", "Elite", "VHigh", "High", "Medium", "Low"]:
        td = pred_df[pred_df["tier"] == t]
        if len(td) > 0:
            acc = td["correct"].mean()
            print(f"    {t:12s}: {acc:.2%} ({len(td)} 场)")

    # 5. 投注重测
    print(f"\n{tag} 投注重测中...")
    kelly_label = "+Kelly" if use_kelly else ""
    print(f"  策略: {model_type}{kelly_label} | "
          f"资金: {initial_bankroll:.0f} | "
          f"最小 Edge: {min_edge:.0%}")

    inv_label_map = {0: "H", 1: "D", 2: "A"}
    result = run_tiered_backtest_with_model_probs(
        test_df,
        y_prob,
        inv_label_map,
        verbose=True,
        initial_bankroll=initial_bankroll,
        min_edge=min_edge,
        use_kelly=use_kelly,
        calibration_factors=cal_factors if cal_factors else None,
    )

    # 6. 导出
    if export:
        export_path = Path(f"betting_results/{league_key}_{model_type}_{test_cutoff}.json")
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_results(result, export_path)
        print(f"  结果已导出: {export_path}")

    return {
        "league": league_key,
        "model": model_type,
        "base_accuracy": base_acc,
        "test_matches": len(test_df),
        "result": result,
        "summary": result.summary,
    }


# ─── 全部联赛 ─────────────────────────────────────────────────

def all_leagues(
    model_type: str = "catboost",
    use_kelly: bool = True,
    min_edge: float = 0.03,
    initial_bankroll: float = 10000.0,
    export: bool = False,
):
    """全部五大联赛分别回测"""
    all_results = []

    for lk in LEAGUES:
        r = backtest_league(
            league_key=lk,
            model_type=model_type,
            use_kelly=use_kelly,
            min_edge=min_edge,
            initial_bankroll=initial_bankroll,
            verbose=False,
            export=export,
        )
        all_results.append(r)

    # 汇总
    print(f"\n\n{SEP}")
    print(f"  五大联赛投注重测汇总")
    print(f"{SEP}")
    print(f"  {'联赛':10s} {'准确率':7s} {'投注':5s} {'胜率':7s} {'ROI':7s} {'总盈亏':>10s} {'回撤':7s}")
    print(f"  {'─'*55}")
    for r in all_results:
        if "error" in r:
            print(f"  {str(r.get('league', '?')):10s} {'ERROR':7s}")
            continue
        s = r["summary"]
        tot = s.get('total_bets', 0)
        wr = s.get('win_rate', 'N/A')
        roi = s.get('roi', 'N/A')
        prof = s.get('total_profit', '?')
        dd = s.get('drawdown', '?')
        print(f"  {r['league']:10s} {r['base_accuracy']:6.1%} "
              f"{str(tot):>5s} {str(wr):>7s} "
              f"{str(roi):>7s} {str(prof):>10s} "
              f"{str(dd):>7s}")

    return all_results


# ─── Kelly vs 等额对比 ───────────────────────────────────────

def compare_strategies(
    league: str = "EPL",
    model_type: str = "catboost",
):
    """Kelly 投注 vs 等额投注 vs 不投注（纯预测准确率）对比"""
    tag = f"[{league}]"
    print(f"\n{SEP}")
    print(f"  策略对比 — {league}")
    print(f"{SEP}")

    # 一次性加载+训练，复用预测
    train_df, test_df, feature_cols = load_and_build_features(league)
    if test_df.empty:
        print(f"{tag} 无数据")
        return

    predictor = train_best_model(train_df, feature_cols, model_type, league)

    available = [c for c in feature_cols if c in test_df.columns]
    X_test = test_df[available].fillna(0).values
    y_prob = predictor.model.predict_proba(X_test)
    y_test = test_df["result"].map({"H": 0, "D": 1, "A": 2}).values

    # 基础准确率
    y_pred = y_prob.argmax(axis=1)
    base_acc = accuracy_score(y_test, y_pred)
    print(f"\n  {tag} 基础准确率: {base_acc:.2%}")

    inv_label_map = {0: "H", 1: "D", 2: "A"}

    strategies = [
        ("1. Kelly (分层 3%)", True, 0.03),
        ("2. Kelly (宽松 1%)", True, 0.01),
        ("3. Kelly (严格 5%)", True, 0.05),
        ("4. 等额投注", False, 0.03),
        ("5. 等比 2%", False, 0.03),
    ]

    all_results = {}
    for name, use_kelly, me in strategies:
        print(f"\n  [{name}] ...", end=" ")
        sys.stdout.flush()

        cbs = ConfidenceBettingSystem(
            initial_bankroll=10000.0,
            min_edge=me,
            use_kelly=use_kelly,
        )

        for i, (_, row) in enumerate(test_df.iterrows()):
            probs = y_prob[i]
            mp = {"H": float(probs[0]), "D": float(probs[1]), "A": float(probs[2])}
            odds_s = {
                "H": row.get("AvgH", row.get("B365H", 0)),
                "D": row.get("AvgD", row.get("B365D", 0)),
                "A": row.get("AvgA", row.get("B365A", 0)),
            }
            for k in odds_s:
                if pd.isna(odds_s[k]) or odds_s[k] <= 1:
                    odds_s[k] = 0.0

            match_id = f"{row.get('home_team', '?')} vs {row.get('away_team', '?')}"
            actual = row.get("result", "?")
            if actual not in ("H", "D", "A"):
                continue

            decision = cbs.evaluate_bet(
                mp, odds_s, match_id,
                row.get("league", "?"),
                row.get("date", "?"),
                actual,
            )

            # 策略 5 (等比): 覆盖为固定 2% bankroll
            if name == "5. 等比 2%":
                if decision.bet_on is not None and decision.edge > 0.03:
                    tier = get_confidence_tier(decision.confidence)
                    if tier != ConfidenceTier.LOW:
                        decision.bet_stake = min(200.0, cbs.bankroll * 0.02)

            cbs.settle_bet(decision)

        result = cbs.get_betting_stats()
        all_results[name] = result
        s = result.summary
        print(f"投注 {s['total_bets']} 场 | "
              f"胜率 {s['win_rate']} | "
              f"ROI {s['roi']} | "
              f"利润 {s['total_profit']} | "
              f"回撤 {s['drawdown']}")

    # 汇总表
    print(f"\n\n{SEP}")
    print(f"  [{league}] 策略对比汇总 (CatBoost, 2526 测试)")
    print(SEP)
    print(f"  {'策略':22s} {'投注':>6s} {'胜率':>7s} {'ROI':>8s} {'盈亏':>12s} {'投注额':>12s} {'回撤':>7s}")
    print(f"  {'─'*77}")

    base_row = f"  {'0. 纯预测(基线)':22s} {'':>6s} {base_acc:>6.1%}"
    print(base_row)

    for name, r in all_results.items():
        s = r.summary
        print(f"  {name:22s} {s['total_bets']:>6d} "
              f"{s['win_rate']:>7s} {s['roi']:>8s} "
              f"{s['total_profit']:>12s} "
              f"{s['total_staked']:>12s} "
              f"{s['drawdown']:>7s}")


# ─── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="置信度分层投注回测")
    parser.add_argument("--league", default="EPL", help="联赛 (EPL/LaLiga/SerieA/Bundesliga/Ligue1)")
    parser.add_argument("--all-leagues", action="store_true", help="全部五大联赛")
    parser.add_argument("--model", default="catboost", help="模型 (catboost/rf/xgboost/lightgbm)")
    parser.add_argument("--no-kelly", action="store_true", help="关闭 Kelly，使用等额投注")
    parser.add_argument("--edge", type=float, default=0.03, help="最小 Edge 门槛 (默认 0.03)")
    parser.add_argument("--bankroll", type=float, default=10000.0, help="初始资金 (默认 10000)")
    parser.add_argument("--force-download", action="store_true", help="强制重新下载数据")
    parser.add_argument("--export", action="store_true", help="导出结果到 JSON")
    parser.add_argument("--compare", action="store_true", help="策略对比模式")
    args = parser.parse_args()

    if args.compare:
        compare_strategies(league=args.league, model_type=args.model)
    elif args.all_leagues:
        all_leagues(
            model_type=args.model,
            use_kelly=not args.no_kelly,
            min_edge=args.edge,
            initial_bankroll=args.bankroll,
            export=args.export,
        )
    else:
        backtest_league(
            league_key=args.league,
            model_type=args.model,
            use_kelly=not args.no_kelly,
            min_edge=args.edge,
            initial_bankroll=args.bankroll,
            force_download=args.force_download,
            export=args.export,
        )
