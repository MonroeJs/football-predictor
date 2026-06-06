"""
快速诊断：泊松模型准确率测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

import pandas as pd
import numpy as np
from src.utils import logger
from src.data_loader import download_league_data, standardize_dataframe
from src.poisson import calc_attack_defense_strength, predict_match_poisson

# 1. 加载EPL数据
logger.info("=== 加载 EPL 数据 ===")
raw = download_league_data("EPL")
std = standardize_dataframe(raw)
logger.info(f"标准化后: {len(std)} 条")

# 2. 拆分训练/测试
train = std[std["season_code"] < "2425"].copy()
test = std[std["season_code"] >= "2425"].copy()
logger.info(f"训练: {len(train)} 场, 测试: {len(test)} 场")

# 3. 计算攻防强度
attack, defense, avg_h, avg_a = calc_attack_defense_strength(train)
logger.info(f"联赛场均进球: home={avg_h.get('EPL', 'N/A')}, away={avg_a.get('EPL', 'N/A')}")

# 4. 测试
correct, total = 0, 0
home_c, home_t = 0, 0
draw_c, draw_t = 0, 0
away_c, away_t = 0, 0
pred_counts = {"H": 0, "D": 0, "A": 0}

for _, row in test.iterrows():
    pred = predict_match_poisson(
        row["home_team"], row["away_team"],
        attack, defense, avg_h, avg_a,
        league=row.get("league"),
    )
    result = (
        "H" if pred.home_win_prob > max(pred.draw_prob, pred.away_win_prob)
        else ("D" if pred.draw_prob > pred.away_win_prob else "A")
    )
    actual = row["result"]
    correct += (result == actual)
    total += 1
    pred_counts[result] += 1
    
    if actual == "H": home_c += (result == "H"); home_t += 1
    elif actual == "D": draw_c += (result == "D"); draw_t += 1
    else: away_c += (result == "A"); away_t += 1

logger.info(f"\n=== 结果 ===")
logger.info(f"总准确率: {correct/total:.2%} ({correct}/{total})")
logger.info(f"主胜准确率: {home_c/home_t:.2%} ({home_c}/{home_t})")
logger.info(f"平局准确率: {draw_c/draw_t:.2%} ({draw_c}/{draw_t})")
logger.info(f"客胜准确率: {away_c/away_t:.2%} ({away_c}/{away_t})")
logger.info(f"预测分布: H={pred_counts['H']} ({pred_counts['H']/total:.1%}), "
            f"D={pred_counts['D']} ({pred_counts['D']/total:.1%}), "
            f"A={pred_counts['A']} ({pred_counts['A']/total:.1%})")

# 5. 看几个具体预测
print("\n=== 具体预测示例 ===")
for _, row in test.head(10).iterrows():
    pred = predict_match_poisson(
        row["home_team"], row["away_team"],
        attack, defense, avg_h, avg_a,
        league=row.get("league"),
    )
    result = (
        "H" if pred.home_win_prob > max(pred.draw_prob, pred.away_win_prob)
        else ("D" if pred.draw_prob > pred.away_win_prob else "A")
    )
    actual = row["result"]
    ok = "OK" if result == actual else "NO"
    print(f"  {ok} {row['home_team']:20s} vs {row['away_team']:20s} "
          f"进球={row['home_goals']}-{row['away_goals']} "
          f"实际={actual} 预测={result} "
          f"lambda_home={pred.home_goals:.2f} lambda_away={pred.away_goals:.2f} "
          f"P(H)={pred.home_win_prob:.2f} P(D)={pred.draw_prob:.2f} P(A)={pred.away_win_prob:.2f}")
