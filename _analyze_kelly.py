"""Analyze backtest results to understand why Kelly doesn't trigger"""
import json
from collections import defaultdict

with open('betting_results/ucl_2526_backtest.json') as f:
    data = json.load(f)

decisions = data.get('decisions_preview', [])
print(f'总比赛: {len(decisions)}')

# Edge distribution by tier
tier_edges = defaultdict(list)
tier_odds = defaultdict(list)
tier_probs = defaultdict(list)
for d in decisions:
    t = d.get('tier', '?')
    e = d.get('edge', 0)
    tier_edges[t].append(e)
    tier_odds[t].append(d.get('odds', 0))
    tier_probs[t].append(d.get('confidence', 0))

print(f'\n=== Edge 值分布 (按分层) ===')
print(f"{'分层':8s} {'场次':>5s} {'avg_edge':>9s} {'max_edge':>9s} {'>3%':>6s} {'>2%':>6s} {'avg_odds':>9s} {'avg_conf':>9s}")
print('-' * 60)
for tier in ['Max', 'Elite', 'VHigh', 'High', 'Medium', 'Low']:
    edges = tier_edges.get(tier, [])
    if edges:
        avg_e = sum(edges) / len(edges)
        max_e = max(edges)
        above_3 = sum(1 for e in edges if e > 0.03)
        above_2 = sum(1 for e in edges if e > 0.02)
        avg_o = sum(tier_odds[tier]) / len(tier_odds[tier])
        avg_p = sum(tier_probs[tier]) / len(tier_probs[tier])
        print(f'{tier:8s} {len(edges):>5d} {avg_e:.3f} {max_e:.3f} {above_3:>6d} {above_2:>6d} {avg_o:.2f} {avg_p:.1%}')

# Check the specific condition chain
print(f'\n=== 条件链分析 ===')
print(f'min_edge (全局): 0.03')
print(f'min_edge_by_tier thresholds:')
print(f'  Low: 999, Medium: 0.05, High: 0.04, VHigh: 0.03, Elite: 0.02, Max: 0.02')
print(f'  → 实际门槛 = max(0.03, tier_threshold)')
print(f'  → Medium: 0.05, High: 0.04, VHigh/Elite/Max: 0.03')

# For VHigh tier specifically
vhigh = tier_edges.get('VHigh', [])
print(f'\n=== VHigh 层详情 ({len(vhigh)} 场) ===')
vhigh_positive = [e for e in vhigh if e > 0]
vhigh_above_3 = [e for e in vhigh if e > 0.03]
print(f'  positive edge: {len(vhigh_positive)}/{len(vhigh)}')
print(f'  above 3%: {len(vhigh_above_3)}/{len(vhigh)}')
if vhigh_positive:
    print(f'  avg edge (positive only): {sum(vhigh_positive)/len(vhigh_positive):.3f}')

elite = tier_edges.get('Elite', [])
print(f'\n=== Elite 层详情 ({len(elite)} 场) ===')
elite_positive = [e for e in elite if e > 0]
elite_above_3 = [e for e in elite if e > 0.03]
print(f'  positive edge: {len(elite_positive)}/{len(elite)}')
print(f'  above 3%: {len(elite_above_3)}/{len(elite)}')
if elite_positive:
    print(f'  avg edge (positive only): {sum(elite_positive)/len(elite_positive):.3f}')
