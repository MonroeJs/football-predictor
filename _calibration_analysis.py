"""深入分析：模型校准 vs 赔率隐含概率"""
import json, numpy as np
from collections import defaultdict
from pathlib import Path

# 从 ucl 回测加载数据
import sys
sys.path.insert(0, '.')
from run_ucl_backtest import load_ucl
from src.betting_system import KellyCalculator, get_confidence_tier

df = load_ucl('2526')
kelly = KellyCalculator()

# 检查模型概率 vs 实际胜率
# 这里 prob_H/prob_D/prob_A 是市场隐含概率
tier_results = defaultdict(lambda: {'total': 0, 'correct': 0, 'prob_sum': 0.0})

for _, row in df.iterrows():
    probs = [row['prob_H'], row['prob_D'], row['prob_A']]
    max_prob = max(probs)
    pred = ['H','D','A'][np.argmax(probs)]
    tier = get_confidence_tier(max_prob).value
    
    tier_results[tier]['total'] += 1
    tier_results[tier]['prob_sum'] += max_prob
    if pred == row['result']:
        tier_results[tier]['correct'] += 1

print('=== 市场隐含概率 vs 实际胜率 ===')
print(f"{'分层':8s} {'场次':>5s} {'avg_prob':>9s} {'实际胜率':>9s} {'偏差':>7s}")
print('-' * 40)
for t in ['Max','Elite','VHigh','High','Medium','Low']:
    r = tier_results.get(t)
    if r and r['total'] > 0:
        avg_prob = r['prob_sum'] / r['total']
        accuracy = r['correct'] / r['total']
        bias = accuracy - avg_prob
        print(f'{t:8s} {r["total"]:>5d} {avg_prob:.1%} {accuracy:.1%} {bias:+.1%}')

print('\n')

# 现在看关键时刻：calibration factor 被 clamp 在 1.0 以下
print('=== 当前校准逻辑问题 ===')
print('''
在 ConfidenceBettingSystem.evaluate_bet() 中:

    raw_cal = self.calibration_factors.get(tier.value, 1.0)
    cal_factor = min(raw_cal, 1.0)  # NEVER amplify
    model_prob = model_probs[pred_outcome] * cal_factor
    model_prob = min(model_prob, 0.92)

问题：如果模型是"保守型"（预测 65% 但实际赢 78%），
     校准因子应该 > 1.0 来上调概率。
     但 `min(raw_cal, 1.0)` 强制只能降不能升。
''')

# 模拟修正后的效果
print('=== 模拟修正：如果校准因子 = 实际胜率 / 平均预测概率 ===')
for t in ['Max','Elite','VHigh','High','Medium','Low']:
    r = tier_results.get(t)
    if r and r['total'] > 0:
        avg_prob = r['prob_sum'] / r['total']
        accuracy = r['correct'] / r['total']
        if avg_prob > 0:
            cal = accuracy / avg_prob  # 正确校准因子
            print(f'{t:8s}: avg_prob={avg_prob:.1%}  accuracy={accuracy:.1%}  → 校准因子={cal:.3f} {"(需要上调)" if cal > 1 else ("(需要下调)" if cal < 1 else "(完美)")}')
