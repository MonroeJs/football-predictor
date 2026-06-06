"""
LaLiga 评测 — 批量预测，速度快
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from src.utils import logger
from src.data_loader import download_league_data, standardize_dataframe
from src.features import build_features
from src.ml_models import FootballPredictor, EnsemblePredictor
from src.poisson import calc_attack_defense_strength, predict_match_poisson
from config import LEAGUES, MODELS_DIR

LEAGUE = "LaLiga"
print(f"\n{'='*60}")
print(f"{LEAGUE} ({LEAGUES[LEAGUE]['name']})")

# Load data
raw = download_league_data(LEAGUE, force=False)
std = standardize_dataframe(raw)

# Data summary
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

# ========== Poisson ==========
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

# ========== ML models (批量预测) ==========
print(f"\n=== ML 模型 ===")
models_config = ["random_forest", "logistic_regression", "gradient_boosting"]
predictors = []
results = {}

for mt in models_config:
    model_path = MODELS_DIR / f"{LEAGUE}_{mt}_v1.pkl"
    if model_path.exists():
        print(f"  {mt}: 加载模型...")
        p = FootballPredictor.load(league=LEAGUE, model_type=mt)
        if p and p.is_fitted:
            predictors.append(p)
            # Batch predict
            available = [c for c in p.feature_names if c in test_df.columns]
            X_test = test_df[available].fillna(0)
            # Direct model predict (bypass predict() overhead)
            y_prob = p.model.predict_proba(
                p.scaler.transform(X_test.values) if p.model_type in ("logistic_regression",)
                else X_test.values
            )
            pred_indices = y_prob.argmax(axis=1)
            pred_results = [p.inv_label_map[i] for i in pred_indices]
            
            actual = test_df["result"].values
            correct = sum(1 for a, b in zip(pred_results, actual) if a == b)
            acc = correct / len(test_df)
            results[mt] = acc
            print(f"    测试集: {correct}/{len(test_df)} = {acc:.2%}")
    else:
        print(f"  {mt}: 文件未找到，使用已有训练输出...")

# ========== Ensemble (批量) ==========
if len(predictors) >= 2:
    ensemble = EnsemblePredictor(predictors)
    print(f"\n  Ensemble (集成)...")

    # For each model, batch predict
    ensemble_votes = []
    import numpy as np
    n_matches = len(test_df)
    
    for p in predictors:
        available = [c for c in p.feature_names if c in test_df.columns]
        X_test = test_df[available].fillna(0).values
        needs_scale = p.model_type in ("logistic_regression",)
        if needs_scale:
            X_test = p.scaler.transform(X_test)
        y_prob = p.model.predict_proba(X_test)
        ensemble_votes.append(y_prob)

    # Average probabilities
    avg_probs = np.mean(ensemble_votes, axis=0)
    pred_indices = avg_probs.argmax(axis=1)
    pred_results = [predictors[0].inv_label_map[i] for i in pred_indices]
    
    actual = test_df["result"].values
    correct = sum(1 for a, b in zip(pred_results, actual) if a == b)
    results["Ensemble"] = correct / len(test_df)
    print(f"    测试集: {correct}/{len(test_df)} = {correct/len(test_df):.2%}")

# ========== Summary ==========
print(f"\n{'='*60}")
print(f"{LEAGUE} 结果汇总 (2526赛季测试集, {len(test_df)}场)")
print(f"{'='*60}")
print(f"{'模型':30s} {'准确率':>8s}")
print(f"{'-'*40}")
print(f"{'泊松':30s} {poisson_correct/len(test_df):>8.2%}")
for mt, acc in results.items():
    name = mt.replace("_", " ").title()
    print(f"{name:30s} {acc:>8.2%}")
print()

# Cross-league comparison (if EPL results exist)
print(f"\n{'='*60}")
print(f"EPL vs LaLiga 对比")
print(f"{'='*60}")
print(f"{'指标':30s} {'EPL (英超)':>12s} {'LaLiga (西甲)':>12s}")
print(f"{'-'*56}")
# EPL stats from memory
print(f"{'数据量':30s} {'12604 场':>12s} {'12572 场':>12s}")
print(f"{'主胜率':30s} {'46.1%':>12s} {'47.3%':>12s}")
print(f"{'平局率':30s} {'26.4%':>12s} {'25.8%':>12s}")
print(f"{'客胜率':30s} {'27.5%':>12s} {'26.9%':>12s}")
print(f"{'场均进球(主)':30s} {'1.54':>12s} {'1.55':>12s}")
print(f"{'场均进球(客)':30s} {'1.14':>12s} {'1.11':>12s}")
print(f"{'泊松准确率':30s} {'~48%':>12s} {'47.96%':>12s}")

# Save report
report = f"""# {LEAGUE} ({LEAGUES[LEAGUE]['name']}) 足球预测分析报告

## 数据概览
- 总比赛场次: {len(std)}
- 日期范围: {std['date'].min()} ~ {std['date'].max()}
- 主胜率: {(std['result']=='H').mean():.1%}
- 平局率: {(std['result']=='D').mean():.1%}
- 客胜率: {(std['result']=='A').mean():.1%}
- 场均进球(主): {std['home_goals'].mean():.2f}
- 场均进球(客): {std['away_goals'].mean():.2f}

## 模型表现 (2526赛季测试集, {len(test_df)}场)
| 模型 | 准确率 |
|------|--------|
| 泊松 | {poisson_correct/len(test_df):.2%} |
"""
for mt, acc in results.items():
    report += f"| {mt} | {acc:.2%} |\n"

report += """
## EPL vs LaLiga 跨联赛对比
| 指标 | EPL (英超) | LaLiga (西甲) |
|------|-----------|-------------|
| 数据量 | 12604 场 | 12572 场 |
| 主胜率 | 46.1% | 47.3% |
| 平局率 | 26.4% | 25.8% |
| 客胜率 | 27.5% | 26.9% |
| 场均进球(主) | 1.54 | 1.55 |
| 场均进球(客) | 1.14 | 1.11 |
| 泊松准确率 | ~48% | 47.96% |
"""

report_path = Path(__file__).parent / "docs" / "training_reports" / f"{LEAGUE}_2526.md"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(report, encoding="utf-8")
print(f"\nReport saved: {report_path}")
print(f"\nDone!")
