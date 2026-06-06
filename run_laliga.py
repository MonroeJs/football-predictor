"""
LaLiga（西甲）专项训练与评估 — 用 EPL 之外的另一联赛数据跑模型
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.absolute()))

from src.utils import logger
from src.data_loader import download_league_data, standardize_dataframe
from src.features import build_features
from src.ml_models import FootballPredictor, EnsemblePredictor
from src.poisson import calc_attack_defense_strength, predict_match_poisson, evaluate_poisson_model
from config import LEAGUES, TRAIN_SEASONS, MODELS_DIR

LEAGUE = "LaLiga"
print(f"\n{'='*60}")
print(f"{LEAGUE} ({LEAGUES[LEAGUE]['name']}) — 全流程分析")
print(f"{'='*60}")

# 1. 加载所有赛季数据
raw = download_league_data(LEAGUE, force=False)
std = standardize_dataframe(raw)
print(f"\n标准化后: {len(std)} 条记录")

# 2. 特征工程
df = build_features(std)
print(f"特征工程后: {len(df)} 条记录")

# 3. 数据概览
print(f"\n{'='*60}")
print(f"【{LEAGUE} 数据概览】")
print(f"{'='*60}")
print(f"总比赛场次: {len(df)}")
print(f"日期范围: {df['date'].min()} ~ {df['date'].max()}")
print(f"\n结果分布:")
print(f"  主胜: {(df['result']=='H').sum()} ({(df['result']=='H').mean():.1%})")
print(f"  平局: {(df['result']=='D').sum()} ({(df['result']=='D').mean():.1%})")
print(f"  客胜: {(df['result']=='A').sum()} ({(df['result']=='A').mean():.1%})")
print(f"\n场均进球:")
print(f"  主场: {df['home_goals'].mean():.2f}")
print(f"  客场: {df['away_goals'].mean():.2f}")

# 4. 划分训练集 / 测试集
test_cutoff = "2526"
train_df = df[df["season_code"] < test_cutoff].copy()
test_df = df[df["season_code"] >= test_cutoff].copy()
print(f"\n划分: 训练 {len(train_df)} 场, 测试 {len(test_df)} 场")

# 5. 泊松评估
print(f"\n{'='*60}")
print(f"【泊松模型评估 — {LEAGUE}】")
print(f"{'='*60}")
attack, defense, avg_h_by_league, avg_a_by_league = calc_attack_defense_strength(train_df)
poisson_eval = evaluate_poisson_model(df)

# 测试集泊松评估
poisson_test_correct = 0
for _, row in test_df.iterrows():
    pred = predict_match_poisson(
        row["home_team"], row["away_team"],
        attack, defense, avg_h_by_league, avg_a_by_league,
        league=row["league"],
        elo_home=row.get("elo_home"),
        elo_away=row.get("elo_away"),
    )
    pick = ("H" if pred.home_win_prob > max(pred.draw_prob, pred.away_win_prob)
            else ("D" if pred.draw_prob > pred.away_win_prob else "A"))
    if pick == row["result"]:
        poisson_test_correct += 1

print(f"\n测试集 ({len(test_df)} 场): 泊松准确率 = {poisson_test_correct}/{len(test_df)} = {poisson_test_correct/len(test_df):.2%}")

# 6. ML 模型训练
print(f"\n{'='*60}")
print(f"【ML 模型训练 — {LEAGUE}】")
print(f"{'='*60}")

models_config = [
    ("random_forest", "Random Forest"),
    ("logistic_regression", "Logistic Regression"),
    ("gradient_boosting", "Gradient Boosting"),
]

predictors = []
for mt, mt_name in models_config:
    print(f"\n训练 {mt_name}...")
    p = FootballPredictor(model_type=mt, league=LEAGUE)
    tr = p.train(train_df, use_tscv=True)
    if "error" not in tr:
        predictors.append(p)
        p.save()
        print(f"  [OK] 保存: {MODELS_DIR / f'{LEAGUE}_{mt}_v1.pkl'}")
    else:
        print(f"  [FAIL] 失败: {tr['error']}")

# 7. 测试集评估
print(f"\n{'='*60}")
print(f"【测试集评估 — {LEAGUE} {test_cutoff}赛季】")
print(f"{'='*60}")

for p in predictors:
    correct = 0
    for _, row in test_df.iterrows():
        feat = {c: row[c] for c in p.feature_names if c in row.index}
        try:
            pred = p.predict(feat)
            if pred.predicted == row["result"]:
                correct += 1
        except Exception:
            pass
    acc = correct / len(test_df) * 100
    print(f"  {p.model_type:25s}: {correct:3d}/{len(test_df):3d} = {acc:.2f}%")

# 集成预测
if len(predictors) >= 2:
    ensemble = EnsemblePredictor(predictors)
    ensemble_correct = 0
    for _, row in test_df.iterrows():
        feat = {c: row[c] for c in predictors[0].feature_names if c in row.index}
        try:
            pred = ensemble.predict(feat)
            if pred.predicted == row["result"]:
                ensemble_correct += 1
        except Exception:
            pass
    acc = ensemble_correct / len(test_df) * 100
    print(f"  {'Ensemble (集成)':25s}: {ensemble_correct:3d}/{len(test_df):3d} = {acc:.2f}%")

# 8. 对比汇总
print(f"\n{'='*60}")
print(f"【{LEAGUE} 模型对比汇总】")
print(f"{'='*60}")
print(f"{'模型':25s} {'准确率':>10s}  {'说明'}")
print(f"{'-'*50}")
print(f"{'泊松 (全部)':25s} {poisson_eval['accuracy']:>10.2%}  全数据上的整体表现")
print(f"{'泊松 (测试集)':25s} {poisson_test_correct/len(test_df):>10.2%}  {test_cutoff}赛季测试集")
for p in predictors:
    correct = sum(1 for _, row in test_df.iterrows()
                  if p.predict({c: row[c] for c in p.feature_names if c in row.index}).predicted == row["result"])
    print(f"{p.model_type:25s} {correct/len(test_df):>10.2%}  {test_cutoff}赛季测试集")

if len(predictors) >= 2:
    ensemble = EnsemblePredictor(predictors)
    ec = sum(1 for _, row in test_df.iterrows()
             if ensemble.predict({c: row[c] for c in predictors[0].feature_names if c in row.index}).predicted == row["result"])
    print(f"{'Ensemble (集成)':25s} {ec/len(test_df):>10.2%}  {test_cutoff}赛季测试集")

# 保存结果报告
report = f"""
# {LEAGUE} ({LEAGUES[LEAGUE]['name']}) 足球预测分析报告

## 数据概览
- 总比赛场次: {len(df)}
- 日期范围: {df['date'].min()} ~ {df['date'].max()}
- 主胜率: {(df['result']=='H').mean():.1%}
- 平局率: {(df['result']=='D').mean():.1%}
- 客胜率: {(df['result']=='A').mean():.1%}
- 场均进球(主): {df['home_goals'].mean():.2f}
- 场均进球(客): {df['away_goals'].mean():.2f}

## 模型表现 ({test_cutoff}赛季测试集, {len(test_df)}场)
| 模型 | 准确率 |
|------|--------|
| 泊松(全部数据) | {poisson_eval['accuracy']:.2%} |
| 泊松(测试集) | {poisson_test_correct/len(test_df):.2%} |
"""
for p in predictors:
    correct = sum(1 for _, row in test_df.iterrows()
                  if p.predict({c: row[c] for c in p.feature_names if c in row.index}).predicted == row["result"])
    report += f"| {p.model_type} | {correct/len(test_df):.2%} |\n"

if len(predictors) >= 2:
    ensemble = EnsemblePredictor(predictors)
    ec = sum(1 for _, row in test_df.iterrows()
             if ensemble.predict({c: row[c] for c in predictors[0].feature_names if c in row.index}).predicted == row["result"])
    report += f"| Ensemble (集成) | {ec/len(test_df):.2%} |\n"

report_path = Path(__file__).parent / "docs" / "training_reports" / f"{LEAGUE}_{test_cutoff}.md"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(report, encoding="utf-8")
print(f"\n✅ 报告已保存: {report_path}")

print(f"\n{'='*60}")
print(f"✅ {LEAGUE} 全流程分析完成！")
print(f"{'='*60}")
