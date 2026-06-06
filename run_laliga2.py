"""
LaLiga 训练/评估
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from src.utils import logger
from src.data_loader import download_league_data, standardize_dataframe
from src.features import build_features
from src.ml_models import FootballPredictor, EnsemblePredictor, load_per_league_models
from src.poisson import calc_attack_defense_strength, predict_match_poisson
from config import LEAGUES

LEAGUE = "LaLiga"
print(f"\n{'='*60}")
print(f"{LEAGUE} ({LEAGUES[LEAGUE]['name']})")

# Load data
raw = download_league_data(LEAGUE, force=False)
std = standardize_dataframe(raw)

# --- Data summary ---
print(f"\n【数据概览】")
print(f"  总场次: {len(std)}")
print(f"  日期: {std['date'].min()} ~ {std['date'].max()}")
print(f"  主胜: {(std['result']=='H').mean():.1%} 平局: {(std['result']=='D').mean():.1%} 客胜: {(std['result']=='A').mean():.1%}")
print(f"  场均进球: 主 {std['home_goals'].mean():.2f} / 客 {std['away_goals'].mean():.2f}")

# Feature engineering
df = build_features(std)
train_df = df[df["season_code"] < "2526"].copy()
test_df = df[df["season_code"] >= "2526"].copy()
print(f"\n  训练: {len(train_df)} / 测试: {len(test_df)}")

# Poisson
attack, defense, avg_h, avg_a = calc_attack_defense_strength(train_df)
poisson_correct = 0
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
        poisson_correct += 1

print(f"\n=== 泊松模型 (测试集) ===")
print(f"  准确率: {poisson_correct}/{len(test_df)} = {poisson_correct/len(test_df):.2%}")

# ML models - load saved models or train
print(f"\n=== ML 模型 ===")
models_config = ["random_forest", "logistic_regression", "gradient_boosting"]
predictors = []

for mt in models_config:
    model_path = Path(__file__).parent / "models" / f"{LEAGUE}_{mt}_v1.pkl"
    if model_path.exists():
        print(f"  {mt}: 加载已有模型...")
        p = FootballPredictor.load(league=LEAGUE, model_type=mt)
        predictors.append(p)
        # evaluate
        correct = 0
        for _, row in test_df.iterrows():
            feat = {c: row[c] for c in p.feature_names if c in row.index}
            try:
                if p.predict(feat).predicted == row["result"]:
                    correct += 1
            except: pass
        print(f"    测试集: {correct}/{len(test_df)} = {correct/len(test_df):.2%}")
    else:
        print(f"  {mt}: 训练新模型...")
        p = FootballPredictor(model_type=mt, league=LEAGUE)
        tr = p.train(train_df, use_tscv=True)
        if "error" not in tr:
            p.save()
            predictors.append(p)
            correct = 0
            for _, row in test_df.iterrows():
                feat = {c: row[c] for c in p.feature_names if c in row.index}
                try:
                    if p.predict(feat).predicted == row["result"]:
                        correct += 1
                except: pass
            print(f"    测试集: {correct}/{len(test_df)} = {correct/len(test_df):.2%}")
        else:
            print(f"    训练失败: {tr['error']}")

# Ensemble
if len(predictors) >= 2:
    ensemble = EnsemblePredictor(predictors)
    correct = 0
    for _, row in test_df.iterrows():
        feat = {c: row[c] for c in predictors[0].feature_names if c in row.index}
        try:
            if ensemble.predict(feat).predicted == row["result"]:
                correct += 1
        except: pass
    print(f"\n  Ensemble (集成): {correct}/{len(test_df)} = {correct/len(test_df):.2%}")

# Final summary
print(f"\n{'='*60}")
print(f"{LEAGUE} 结果汇总 (2526赛季测试集, {len(test_df)}场)")
print(f"{'='*60}")
print(f"{'模型':30s} {'准确率':>8s}")
print(f"{'-'*40}")
print(f"{'泊松':30s} {poisson_correct/len(test_df):>8.2%}")
for p in predictors:
    c = sum(1 for _, row in test_df.iterrows()
            if p.predict({c: row[c] for c in p.feature_names if c in row.index}).predicted == row["result"])
    print(f"{p.model_type:30s} {c/len(test_df):>8.2%}")
if len(predictors) >= 2:
    ensemble = EnsemblePredictor(predictors)
    ec = sum(1 for _, row in test_df.iterrows()
             if ensemble.predict({c: row[c] for c in predictors[0].feature_names if c in row.index}).predicted == row["result"])
    print(f"{'Ensemble':30s} {ec/len(test_df):>8.2%}")

print(f"\nDone!")
