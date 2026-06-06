"""
LaLiga XGBoost 对比 — 近10赛季
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

import numpy as np
from src.data_loader import download_league_data, standardize_dataframe
from src.features import build_features
from src.ml_models import FootballPredictor
from src.poisson import calc_attack_defense_strength, predict_match_poisson

LEAGUE = "LaLiga"
print(f"{LEAGUE} -- 完整模型对比 (近10赛季)")

raw = download_league_data(LEAGUE, force=False)
std = standardize_dataframe(raw)
df = build_features(std)

train_df = df[df["season_code"] < "2526"].copy()
test_df = df[df["season_code"] >= "2526"].copy()
print(f"训练 {len(train_df)} / 测试 {len(test_df)}")

# Poisson
attack, defense, avg_h, avg_a = calc_attack_defense_strength(train_df)
p_correct = 0
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

print(f"\n  泊松:          {p_correct/len(test_df):.2%} ({p_correct}/{len(test_df)})")

# All ML models
all_models = [
    ("random_forest", "Random Forest"),
    ("logistic_regression", "Logistic Regression"),
    ("gradient_boosting", "Gradient Boosting"),
    ("xgboost", "XGBoost"),
]

predictors = []
results = {}

for mt, name in all_models:
    print(f"  Training {name}...", end=" ")
    sys.stdout.flush()
    p = FootballPredictor(model_type=mt, league=LEAGUE)
    tr = p.train(train_df, use_tscv=True)
    if "error" not in tr:
        p.save()
        predictors.append(p)
        # Batch eval
        avail = [c for c in p.feature_names if c in test_df.columns]
        X = test_df[avail].fillna(0).values
        if p.model_type in ("logistic_regression",):
            X = p.scaler.transform(X)
        y_prob = p.model.predict_proba(X)
        preds = [p.inv_label_map[i] for i in y_prob.argmax(axis=1)]
        correct = sum(1 for a, b in zip(preds, test_df["result"].values) if a == b)
        results[name] = correct / len(test_df)
        print(f"{correct/len(test_df):.2%} ({correct}/{len(test_df)})")
    else:
        results[name] = 0
        print(f"FAILED: {tr.get('error', 'unknown')}")

# Ensemble (all 4)
if len(predictors) >= 3:
    votes = []
    for p in predictors:
        avail = [c for c in p.feature_names if c in test_df.columns]
        X = test_df[avail].fillna(0).values
        if p.model_type in ("logistic_regression",):
            X = p.scaler.transform(X)
        votes.append(p.model.predict_proba(X))
    avg = np.mean(votes, axis=0)
    preds = [predictors[0].inv_label_map[i] for i in avg.argmax(axis=1)]
    correct = sum(1 for a, b in zip(preds, test_df["result"].values) if a == b)
    results["Ensemble (全部4个)"] = correct / len(test_df)
    print(f"  Ensemble (全部4个): {correct/len(test_df):.2%} ({correct}/{len(test_df)})")

# Ensemble (前3, no xgboost)
no_xgb = [p for p in predictors if p.model_type != "xgboost"]
if len(no_xgb) >= 2:
    votes = []
    for p in no_xgb:
        avail = [c for c in p.feature_names if c in test_df.columns]
        X = test_df[avail].fillna(0).values
        if p.model_type in ("logistic_regression",):
            X = p.scaler.transform(X)
        votes.append(p.model.predict_proba(X))
    avg = np.mean(votes, axis=0)
    preds = [predictors[0].inv_label_map[i] for i in avg.argmax(axis=1)]
    correct = sum(1 for a, b in zip(preds, test_df["result"].values) if a == b)
    results["Ensemble (前3个)"] = correct / len(test_df)
    print(f"  Ensemble (前3个):  {correct/len(test_df):.2%} ({correct}/{len(test_df)})")

# Summary
print(f"\n{'='*50}")
print(f"【LaLiga 近10赛季 — 完整模型对比】")
print(f"{'='*50}")
print(f"{'模型':30s} {'准确率':>12s}")
print(f"{'-'*44}")
print(f"{'泊松':30s} {p_correct/len(test_df):>12.2%}")
for name, acc in results.items():
    print(f"{name:30s} {acc:>12.2%}")
