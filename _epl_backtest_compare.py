"""
EPL 回测：校准前 vs 校准后 — 快速演示 Kelly 触发效果
"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')

import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

from src.betting_system import (
    ConfidenceBettingSystem, get_confidence_tier, _print_results,
)

print('=' * 65)
print('  EPL 回测 — 校准前 vs 校准后')
print('=' * 65)

# 加载数据
path = Path('data/raw/E0_2526.csv')
df = pd.read_csv(path)
print(f'\nEPL 2526: {len(df)} 场比赛')

# 准备数据：用市场赔率模拟保守型模型（预测偏低 10%）
matches = []
for _, row in df.iterrows():
    result = row.get('FTR', '')
    if result not in ('H', 'D', 'A'):
        continue
    b365h = pd.to_numeric(row.get('B365H', np.nan), errors='coerce')
    b365d = pd.to_numeric(row.get('B365D', np.nan), errors='coerce')
    b365a = pd.to_numeric(row.get('B365A', np.nan), errors='coerce')
    if np.isnan(b365h) or b365h <= 1:
        continue
    
    # 市场隐含概率（去边际）
    imp = [1.0/max(o, 1.01) for o in (b365h, b365d, b365a)]
    total = sum(imp)
    market_probs = [p/total for p in imp]
    max_idx = np.argmax(market_probs)
    
    # 模拟保守型模型：预测概率 = 市场概率 × 0.88
    model_probs = [p * 0.88 for p in market_probs]
    
    matches.append({
        'home': row['HomeTeam'], 'away': row['AwayTeam'],
        'result': result,
        'model_H': model_probs[0], 'model_D': model_probs[1], 'model_A': model_probs[2],
        'odds_H': b365h, 'odds_D': b365d, 'odds_A': b365a,
        'pred': ['H','D','A'][max_idx],
    })

print(f'有效比赛: {len(matches)}')

# 用前半数据算校准因子，后半做测试
half = len(matches) // 2
train = matches[:half]
test = matches[half:]

tier_data = defaultdict(lambda: {'correct': 0, 'total': 0, 'conf_sum': 0.0})
for m in train:
    probs = [m['model_H'], m['model_D'], m['model_A']]
    conf = max(probs)
    tier = get_confidence_tier(conf).value
    pred = m['pred']
    tier_data[tier]['total'] += 1
    tier_data[tier]['conf_sum'] += conf
    if pred == m['result']:
        tier_data[tier]['correct'] += 1

cal_factors = {}
print(f'\n=== 校准因子计算 (前 {half} 场) ===')
for t in ['Low','Medium','High','VHigh','Elite','Max']:
    d = tier_data.get(t)
    if d and d['total'] > 0:
        avg_p = d['conf_sum']/d['total']
        acc = d['correct']/d['total']
        factor = min(acc/avg_p, 1.5) if avg_p > 0.01 else 1.0
        cal_factors[t] = factor
        print(f'  {t:8s}: {d["total"]:>4d}场  avg_conf={avg_p:.1%}  acc={acc:.1%}  factor={factor:.3f}')

# 旧行为：cap at 1.0
old_factors = {t: min(v, 1.0) for t, v in cal_factors.items()}

def run_backtest(cal_factors_dict, label):
    cbs = ConfidenceBettingSystem(
        initial_bankroll=10000, min_edge=0.01, use_kelly=True,
        calibration_factors=cal_factors_dict,
    )
    for m in test:
        probs = {'H': m['model_H'], 'D': m['model_D'], 'A': m['model_A']}
        odds = {'H': m['odds_H'], 'D': m['odds_D'], 'A': m['odds_A']}
        decision = cbs.evaluate_bet(probs, odds, f"{m['home']} vs {m['away']}", 'EPL', '2026', m['result'])
        cbs.settle_bet(decision)
    r = cbs.get_betting_stats()
    s = r.summary
    print(f'\n  {label}')
    print(f'    投注: {s["total_bets"]}/{s["total_matches"]} ({s["bet_rate"]})')
    print(f'    胜率: {s["win_rate"]}')
    print(f'    ROI: {s["roi"]}')
    print(f'    盈亏: {s["total_profit"]}')
    return r

print(f'\n{"─"*65}')
print(f'  回测结果 (后 {len(test)} 场)')
print(f'{"─"*65}')

r1 = run_backtest(old_factors, '场景1: 旧行为 (cal_factor ≤ 1.0)')
r2 = run_backtest(cal_factors, '场景2: 新行为 (cal_factor 放开)')

print(f'\n{"="*65}')
print(f'  对比')
print(f'{"="*65}')
print(f'  {"":35s} {"投注":>5s} {"胜率":>7s} {"ROI":>8s} {"盈亏":>10s}')
print(f'  {"─"*65}')
s1 = r1.summary; s2 = r2.summary
print(f'  {"旧行为 (factor≤1.0)":35s} {r1.total_bets:>5d} {r1.win_rate:>6.1%} {r1.roi:>7.2%} {r1.total_profit:>+9.0f}')
print(f'  {"新行为 (factor 放开)":35s} {r2.total_bets:>5d} {r2.win_rate:>6.1%} {r2.roi:>7.2%} {r2.total_profit:>+9.0f}')
print(f'  {"─"*65}')
diff_bets = r2.total_bets - r1.total_bets
diff_profit = r2.total_profit - r1.total_profit
print(f'  差异:                 {diff_bets:>+5d} 投                    {diff_profit:>+10.0f}')
