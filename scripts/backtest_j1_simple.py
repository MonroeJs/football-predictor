"""
J1 联赛回测 — 赔率驱动策略（简单有效）
J1 只有比分+赔率，没有统计数据
"""
import sys, warnings
warnings.filterwarnings('ignore')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from src.leagues.j_league import JLeague
from src.betting_system import get_confidence_tier, KellyCalculator

print('=' * 60)
print('  J1 League Backtest - Odds-based Strategy')
print('=' * 60)

# Load
league = JLeague()
df = league.load_matches()

# Filter to matches with odds
df_odds = df[df['B365H'].notna()].copy()
print(f'Matches with odds: {len(df_odds)}')

# Backtest: follower favorite strategy (same as UCL/WC)
results = []
for _, row in df_odds.iterrows():
    odds = {'H': row['B365H'], 'D': row['B365D'], 'A': row['B365A']}
    fav = min(odds, key=odds.get)
    total = sum(1.0/max(o, 1.01) for o in odds.values())
    probs = {k: (1.0/max(odds[k], 1.01))/total for k in odds}
    max_prob = max(probs.values())
    tier = get_confidence_tier(max_prob)
    fav_odds = odds[fav]
    correct = (fav == row['result'])
    
    results.append({
        'tier': tier.value,
        'correct': correct,
        'odds': fav_odds,
        'prob': max_prob,
        'fav': fav,
        'actual': row['result'],
        'home': row['home_team'],
        'away': row['away_team'],
    })

res_df = pd.DataFrame(results)
print(f'\nTotal: {len(res_df)}, Correct: {res_df["correct"].sum()} ({res_df["correct"].mean():.1%})')

# By tier
print(f'\n{"Tier":10s} {"Matches":>8s} {"Accuracy":>10s} {"Avg Odds":>10s} {"ROI":>10s}')
print('-' * 50)

tier_order = ['Low', 'Medium', 'High', 'VHigh', 'Elite', 'Max']
for t in tier_order:
    td = res_df[res_df['tier'] == t]
    if len(td) == 0:
        continue
    acc = td['correct'].mean()
    won = td[td['correct']]
    lost = td[~td['correct']]
    profit = (won['odds'] - 1).sum() * 10 - len(lost) * 10
    roi = profit / (len(td) * 10) if len(td) > 0 else 0.0
    print(f'{t:10s} {len(td):>8d} {acc:>9.1%} {td["odds"].mean():>9.2f} {roi:>+9.2%}')

# Summary for high-confidence tiers
print(f'\n{"=" * 50}')
print('High-confidence summary (VHigh+):')
vhigh = res_df[res_df['tier'].isin(['VHigh', 'Elite', 'Max'])]
if len(vhigh) > 0:
    acc = vhigh['correct'].mean()
    won = vhigh[vhigh['correct']]
    lost = vhigh[~vhigh['correct']]
    profit = (won['odds'] - 1).sum() * 10 - len(lost) * 10
    roi = profit / (len(vhigh) * 10)
    print(f'  Matches: {len(vhigh)}')
    print(f'  Accuracy: {acc:.1%}')
    print(f'  Avg odds: {vhigh["odds"].mean():.2f}')
    print(f'  ROI: {roi:+.2%}')
else:
    print('  No high-confidence matches (rare in J1 without home advantage model)')
