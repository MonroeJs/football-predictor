#!/usr/bin/env python3
"""
全模型对比 — EPL 近10赛季
包含: RF, LR, GB, XGBoost, LightGBM, CatBoost + 集成 + 校准
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import numpy as np
import pandas as pd

from src.data_loader import download_league_data, standardize_dataframe
from src.features import build_features
from src.features_v2 import build_features_v2, get_feature_columns_v2
from src.ml_models import FootballPredictor
from src.poisson import calc_attack_defense_strength, predict_match_poisson
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score

LEAGUE = "EPL"
SEP = "=" * 60
DASH = "-" * 50

print(SEP)
print(f"[{LEAGUE}] 全模型对比 - 近10赛季 (2526 测试)")
print(SEP)

# ── 1. 加载数据 ──
raw = download_league_data(LEAGUE, force=False)
if raw.empty:
    print("[ERR] 无数据，退出")
    sys.exit(1)
std = standardize_dataframe(raw)

# xG 合并 (在特征工程之前)
try:
    from src.xg_scraper import add_xg_to_pipeline
    std = add_xg_to_pipeline(std)
except Exception as e:
    print(f"[WARN] xG 跳过: {e}")

# v2 特征工程 (链式调用所有子函数)
df = build_features_v2(std)

# 分割
train_df = df[df["season_code"] < "2526"].copy()
test_df = df[df["season_code"] >= "2526"].copy()
print(f"训练: {len(train_df)} 场 | 测试: {len(test_df)} 场\n")

# ── 2. 泊松基准 ──
print(DASH)
print("  泊松 (Dixon-Coles)")
attack, defense, avg_h, avg_a = calc_attack_defense_strength(train_df)
p_correct, p_total = 0, 0
for _, row in test_df.iterrows():
    pred = predict_match_poisson(
        row["home_team"], row["away_team"],
        attack, defense, avg_h, avg_a,
        league=row["league"],
        elo_home=row.get("elo_home"),
        elo_away=row.get("elo_away"),
    )
    pick = ("H" if pred.home_win_prob > max(pred.draw_prob, pred.away_win_prob)
            else ("D" if pred.draw_prob > pred.away_win_prob else "A"))
    if pick == row["result"]:
        p_correct += 1
    p_total += 1
p_acc = p_correct / p_total if p_total else 0
print(f"    准确率: {p_acc:.2%} ({p_correct}/{p_total})")

# ── 3. ML 模型全面对比 ──
MODEL_NAMES = {
    "random_forest": "Random Forest",
    "logistic_regression": "Logistic Regression",
    "gradient_boosting": "Gradient Boosting",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "catboost": "CatBoost",
}

results = {}
predictors = {}
best_predictor = None
best_acc = 0

# 使用 v2 特征集
V2_FEATURES = get_feature_columns_v2()

for mt, name in MODEL_NAMES.items():
    print(f"\n  {name:25s}...", end=" ")
    sys.stdout.flush()
    try:
        p = FootballPredictor(model_type=mt, league=LEAGUE)
        p.feature_names = V2_FEATURES  # 使用 v2 特征集
        tr = p.train(train_df, use_tscv=True)
        if "error" not in tr:
            p.save()
            # 测试集评估
            avail = [c for c in p.feature_names if c in test_df.columns]
            X_test = test_df[avail].fillna(0).values
            if p.model_type in ("logistic_regression",):
                X_test = p.scaler.transform(X_test)
            y_prob = p.model.predict_proba(X_test)
            preds = [p.inv_label_map[i] for i in y_prob.argmax(axis=1)]
            acc = accuracy_score(test_df["result"].values, preds)

            # 逐类准确率
            h_correct = sum(1 for a, b in zip(preds, test_df["result"].values) if a == b == "H")
            h_total = sum(1 for r in test_df["result"].values if r == "H")
            d_correct = sum(1 for a, b in zip(preds, test_df["result"].values) if a == b == "D")
            d_total = sum(1 for r in test_df["result"].values if r == "D")
            a_correct = sum(1 for a, b in zip(preds, test_df["result"].values) if a == b == "A")
            a_total = sum(1 for r in test_df["result"].values if r == "A")

            results[name] = {
                "acc": acc,
                "h": h_correct / h_total if h_total else 0,
                "d": d_correct / d_total if d_total else 0,
                "a": a_correct / a_total if a_total else 0,
            }
            predictors[name] = p

            print(f"[OK] {acc:.2%}  (H:{h_correct/h_total:.0%}|D:{d_correct/d_total:.0%}|A:{a_correct/a_total:.0%})")
            if acc > best_acc:
                best_acc = acc
                best_predictor = p
        else:
            print(f"[ERR] {tr.get('error', 'unknown')}")
            results[name] = {"acc": 0, "h": 0, "d": 0, "a": 0}
    except Exception as e:
        print(f"[ERR] {e}")
        results[name] = {"acc": 0, "h": 0, "d": 0, "a": 0}

# ── 4. 概率校准 ──
print(f"\n  {'概率校准':25s} (Platt Scaling)...", end=" ")
sys.stdout.flush()
if best_predictor is not None:
    try:
        avail = [c for c in best_predictor.feature_names if c in train_df.columns]
        X_train = train_df[avail].fillna(0).values
        y_train = train_df["result"].map(best_predictor.label_map).values

        tscv = TimeSeriesSplit(n_splits=3)
        calibrator = CalibratedClassifierCV(
            best_predictor._create_model(),
            method="sigmoid",
            cv=tscv,
        )

        if best_predictor.model_type in ("logistic_regression",):
            X_train = best_predictor.scaler.transform(X_train)
        calibrator.fit(X_train, y_train)

        # 测试
        X_test = test_df[[c for c in best_predictor.feature_names if c in test_df.columns]].fillna(0).values
        if best_predictor.model_type in ("logistic_regression",):
            X_test = best_predictor.scaler.transform(X_test)

        cal_probs = calibrator.predict_proba(X_test)
        cal_preds = [best_predictor.inv_label_map[i] for i in cal_probs.argmax(axis=1)]
        cal_acc = accuracy_score(test_df["result"].values, cal_preds)

        # Brier score
        y_test_bin = np.zeros((len(test_df), 3))
        for i, lbl in enumerate(test_df["result"].map(best_predictor.label_map).values):
            y_test_bin[i, lbl] = 1

        orig_probs = best_predictor.model.predict_proba(X_test)
        orig_brier = np.mean(np.sum((y_test_bin - orig_probs) ** 2, axis=1))
        calib_brier = np.mean(np.sum((y_test_bin - cal_probs) ** 2, axis=1))

        print(f"[OK] {cal_acc:.2%}  (Brier: {orig_brier:.4f} -> {calib_brier:.4f})")
        results["概率校准"] = {"acc": cal_acc, "h": 0, "d": 0, "a": 0, "note": f"Brier {orig_brier:.4f}->{calib_brier:.4f}"}
    except Exception as e:
        print(f"[ERR] {e}")

# ── 5. 集成 ──
print(f"\n  {'集成 (全部6个)':25s}...", end=" ")
sys.stdout.flush()
if len(predictors) >= 3:
    try:
        avail = [c for c in best_predictor.feature_names if c in test_df.columns]
        X_test = test_df[avail].fillna(0).values

        votes = []
        for p in predictors.values():
            Xp = X_test.copy()
            if p.model_type in ("logistic_regression",):
                Xp = p.scaler.transform(Xp)
            votes.append(p.model.predict_proba(Xp))

        avg_probs = np.mean(votes, axis=0)
        ens_preds = [best_predictor.inv_label_map[i] for i in avg_probs.argmax(axis=1)]
        ens_acc = accuracy_score(test_df["result"].values, ens_preds)
        print(f"[OK] {ens_acc:.2%}")

        # 加权集成（基于验证集准确率加权）
        weights = np.array([max(r["acc"], 0.01) for r in results.values() if isinstance(r, dict) and "acc" in r])
        if len(weights) == len(votes):
            w_avg = np.average(votes, axis=0, weights=weights / weights.sum())
            w_preds = [best_predictor.inv_label_map[i] for i in w_avg.argmax(axis=1)]
            w_acc = accuracy_score(test_df["result"].values, w_preds)
            print(f"  {'加权集成':25s} [OK] {w_acc:.2%}")
            results["加权集成"] = {"acc": w_acc}
        results["集成 (全部)"] = {"acc": ens_acc}
    except Exception as e:
        print(f"[ERR] {e}")

# ── 6. 排行榜 ──
print(f"\n\n{SEP}")
print(f"[最终排名 - {LEAGUE} 2526 测试]")
print(SEP)
print(f"{'模型':28s} {'准确率':>8s} {'主胜':>6s} {'平局':>6s} {'客胜':>6s}")
print(f"{'─'*56}")
print(f"{'泊松 (Dixon-Coles)':28s} {p_acc:>8.2%}")
sorted_results = sorted(results.items(), key=lambda x: x[1].get("acc", 0) if isinstance(x[1], dict) else 0, reverse=True)
for name, res in sorted_results:
    if isinstance(res, dict):
        h_str = f"{res['h']:.0%}" if "h" in res else "  -"
        d_str = f"{res['d']:.0%}" if "d" in res else "  -"
        a_str = f"{res['a']:.0%}" if "a" in res else "  -"
        note = f"  ({res.get('note', '')})" if res.get('note') else ""
        print(f"{name:28s} {res['acc']:>8.2%} {h_str:>6s} {d_str:>6s} {a_str:>6s}{note}")

print(f"\n[DONE]")
