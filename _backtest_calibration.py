"""
回测校准修复效果：校准前 vs 校准后

场景模拟：模型是保守型（预测 65% 但实际胜率 76%）
"""
import sys, json, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')

import numpy as np
from src.betting_system import (
    ConfidenceBettingSystem, KellyCalculator, run_tiered_backtest,
    export_results, get_confidence_tier, _print_results,
)
from src.betting_system import KellyCalculator as KC

print('=' * 65)
print('  校准修复效果对比 — 模拟 ML 模型场景')
print('=' * 65)

# ── 模拟数据 ──
# 假设模型预测概率是"保守型"：
# - 实际概率 = 模型预测 × 1.18（VHigh 层需要上调 18%）
# - 市场赔率反映真实概率
np.random.seed(42)
N = 500

matches = []
for i in range(N):
    # 随机生成真实概率
    true_prob = np.random.uniform(0.35, 0.75)
    
    # 市场赔率 ≈ 真实概率 + 3% 抽水
    margin = 0.03
    odds = 1.0 / (true_prob + margin)
    
    # 模型是保守型：预测概率 = 真实概率 / 1.15
    model_prob = true_prob / 1.15
    model_prob = min(model_prob, 0.80)
    
    # 决定结果（基于真实概率）
    outcome = 'H' if np.random.random() < true_prob else ('D' if np.random.random() < 0.5 else 'A')
    
    matches.append({
        'model_H': model_prob,
        'model_D': (1 - model_prob) * 0.55,
        'model_A': (1 - model_prob) * 0.45,
        'odds_H': odds,
        'odds_D': 1.0 / ((1 - true_prob) * 0.55 + margin),
        'odds_A': 1.0 / ((1 - true_prob) * 0.45 + margin),
        'result': outcome,
    })

# ── 场景 1：校准前（min_edge=0.03, 无校准因子）──
print(f'\n{"─"*65}')
print('  场景 1: 校准前 (默认配置，cal_factor ≤ 1.0)')
print(f'{"─"*65}')

class UncalibratedSystem(ConfidenceBettingSystem):
    """模拟旧的 evaluate_bet 行为（强行 cap 在 1.0）"""
    pass

cbs_before = ConfidenceBettingSystem(
    initial_bankroll=10000,
    min_edge=0.01,  # 设低一点，让校准有机会
    use_kelly=True,
)

bets_before = 0
for m in matches:
    probs = {'H': m['model_H'], 'D': m['model_D'], 'A': m['model_A']}
    odds = {'H': m['odds_H'], 'D': m['odds_D'], 'A': m['odds_A']}
    
    decision = cbs_before.evaluate_bet(
        probs, odds,
        f"Match {len(cbs_before.decisions)}",
        'Sim', '2026-01-01', m['result'],
    )
    cbs_before.settle_bet(decision)
    if decision.bet_on:
        bets_before += 1

result_before = cbs_before.get_betting_stats()
s = result_before.summary
print(f'  投注: {s["total_bets"]}/{s["total_matches"]} ({s["bet_rate"]})')
print(f'  胜率: {s["win_rate"]}')
print(f'  ROI: {s["roi"]}')
print(f'  总盈亏: {s["total_profit"]}')

# ── 场景 2：校准后（cal_factor 1.15）──
print(f'\n{"─"*65}')
print('  场景 2: 校准后 (VHigh 层 cal_factor=1.15)')
print(f'{"─"*65}')

cbs_after = ConfidenceBettingSystem(
    initial_bankroll=10000,
    min_edge=0.01,
    use_kelly=True,
    calibration_factors={'VHigh': 1.15, 'High': 1.04},
)

bets_after = 0
for m in matches:
    probs = {'H': m['model_H'], 'D': m['model_D'], 'A': m['model_A']}
    odds = {'H': m['odds_H'], 'D': m['odds_D'], 'A': m['odds_A']}
    
    decision = cbs_after.evaluate_bet(
        probs, odds,
        f"Match {len(cbs_after.decisions)}",
        'Sim', '2026-01-01', m['result'],
    )
    cbs_after.settle_bet(decision)
    if decision.bet_on:
        bets_after += 1

result_after = cbs_after.get_betting_stats()
s = result_after.summary
print(f'  投注: {s["total_bets"]}/{s["total_matches"]} ({s["bet_rate"]})')
print(f'  胜率: {s["win_rate"]}')
print(f'  ROI: {s["roi"]}')
print(f'  总盈亏: {s["total_profit"]}')

# ── 场景 3：用 compute_calibration_factors 自动计算──
print(f'\n{"─"*65}')
print('  场景 3: 自动计算校准因子 + 投注')
print(f'{"─"*65}')

# 先用一半数据计算校准因子
train = matches[:250]
test = matches[250:]

y_true = [m['result'] for m in train]
y_prob_list = [{'H': m['model_H'], 'D': m['model_D'], 'A': m['model_A']} for m in train]
tiers = []
for m in train:
    probs = [m['model_H'], m['model_D'], m['model_A']]
    max_prob = max(probs)
    tiers.append(get_confidence_tier(max_prob).value)

cal_factors = ConfidenceBettingSystem.compute_calibration_factors(
    y_true, y_prob_list, tiers, max_factor=1.5
)
print(f'  计算得到的校准因子:')
for t in ['Max','Elite','VHigh','High','Medium','Low']:
    if t in cal_factors:
        print(f'    {t}: {cal_factors[t]:.3f}')

cbs_auto = ConfidenceBettingSystem(
    initial_bankroll=10000,
    min_edge=0.01,
    use_kelly=True,
    calibration_factors=cal_factors,
)

for m in test:
    probs = {'H': m['model_H'], 'D': m['model_D'], 'A': m['model_A']}
    odds = {'H': m['odds_H'], 'D': m['odds_D'], 'A': m['odds_A']}
    
    decision = cbs_auto.evaluate_bet(
        probs, odds,
        f"Match {len(cbs_auto.decisions)}",
        'Sim', '2026-01-01', m['result'],
    )
    cbs_auto.settle_bet(decision)

result_auto = cbs_auto.get_betting_stats()
s = result_auto.summary
print(f'  投注: {s["total_bets"]}/{s["total_matches"]} ({s["bet_rate"]})')
print(f'  胜率: {s["win_rate"]}')
print(f'  ROI: {s["roi"]}')
print(f'  总盈亏: {s["total_profit"]}')

# ── 汇总 ──
print(f'\n{"="*65}')
print(f'  对比汇总')
print(f'{"="*65}')
print(f'  {"场景":30s} {"投注":>5s} {"胜率":>7s} {"ROI":>8s} {"盈亏":>10s}')
print(f'  {"─"*60}')
print(f'  {"1. 校准前 (默认)":30s} {result_before.total_bets:>5d} {result_before.win_rate:>6.1%} {result_before.roi:>7.2%} {result_before.total_profit:>+9.0f}')
print(f'  {"2. 校准后 (手动 1.15)":30s} {result_after.total_bets:>5d} {result_after.win_rate:>6.1%} {result_after.roi:>7.2%} {result_after.total_profit:>+9.0f}')
n_test = result_auto.total_matches
print(f'  {"3. 自动校准 (半数据)":30s} {result_auto.total_bets:>5d} {result_auto.win_rate:>6.1%} {result_auto.roi:>7.2%} {result_auto.total_profit:>+9.0f}')
