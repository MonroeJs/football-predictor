"""Analyze tonight's UCL Final with the betting system"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')

import pandas as pd
import numpy as np
from src.betting_system import KellyCalculator, get_confidence_tier, ConfidenceTier

df = pd.read_csv('data/raw/UCL_2526.csv')

# Find recent matches
print('=== 欧冠 2526 关键数据 ===')
print(f'总比赛: {len(df)}')

# Full season favorite betting analysis
kc = KellyCalculator()
results = []
for _, r in df.iterrows():
    if pd.isna(r['B365H']) or pd.isna(r['FTR']) or str(r['FTR']).strip() == '':
        continue
    odds = {'H': r['B365H'], 'D': r['B365D'], 'A': r['B365A']}
    fav = min(odds, key=odds.get)
    
    total = sum(1.0/max(o,1.01) for o in odds.values())
    probs = {k: (1.0/max(odds[k],1.01))/total for k in odds}
    
    max_prob = max(probs.values())
    tier = get_confidence_tier(max_prob).value
    
    actual = r['FTR']
    correct = fav == actual
    results.append({
        'match': f"{r['HomeTeam']} vs {r['AwayTeam']}",
        'fav': fav, 'actual': actual, 'correct': correct,
        'tier': tier, 'odds': odds[fav], 'prob': max_prob,
    })

res_df = pd.DataFrame(results)
print(f'\n=== 低赔方策略 (全场) ===')
total = len(res_df)
correct = res_df['correct'].sum()
print(f'总场次: {total}')
print(f'胜率:   {correct/total:.1%}')

# By tier
print(f'\n{"分层":12s} {"场次":>6s} {"胜率":>8s} {"avg赔率":>8s}')
print(f'{"─"*36}')
for t in ['Max', 'Elite', 'VHigh', 'High', 'Medium', 'Low']:
    td = res_df[res_df['tier'] == t]
    if len(td) > 0:
        acc = td['correct'].mean()
        avg_odds = td['odds'].mean()
        # Simulated flat stake
        stake = 10
        won = td['correct'].sum()
        lost = len(td) - won
        profit = won * stake * (td[td['correct']]['odds'] - 1).sum() - lost * stake
        roi_raw = profit / (len(td) * stake) if len(td) > 0 else 0
        print(f'{t:12s} {len(td):>6d} {acc:>7.1%} {avg_odds:>7.2f}')

# Profit analysis with flat stake
print(f'\n=== 低赔方投注盈亏 (VHigh+, 固定10单位) ===')
vhigh = res_df[res_df['tier'].isin(['VHigh', 'Elite', 'Max'])]
stake = 10
total_staked = len(vhigh) * stake
won_amount = vhigh[vhigh['correct']].apply(
    lambda r: stake * (r['odds'] - 1), axis=1
).sum()
lost_amount = len(vhigh[~vhigh['correct']]) * stake
profit = won_amount - lost_amount
roi = profit / total_staked if total_staked > 0 else 0

print(f'VHigh+ 场次: {len(vhigh)}')
print(f'胜率: {vhigh["correct"].mean():.1%}')
print(f'总投注: {total_staked:.0f}')
print(f'盈亏: {profit:+.0f}')
print(f'ROI: {roi:.2%}')

# Tonight's final analysis
print(f'\n{"="*60}')
print(f'  今晚欧冠决赛: PSG vs Arsenal')
print(f'{"="*60}')

# Market consensus odds
psg_odds, draw_odds, ars_odds = 2.37, 3.40, 3.10
total_implied = 1/psg_odds + 1/draw_odds + 1/ars_odds
print(f'\n博彩赔率 (Bet365 参考):')
print(f'  PSG 胜: {psg_odds:.2f} (隐含{1/psg_odds/total_implied:.1%})')
print(f'  平局:    {draw_odds:.2f} (隐含{1/draw_odds/total_implied:.1%})')
print(f'  Arsenal: {ars_odds:.2f} (隐含{1/ars_odds/total_implied:.1%})')

market_probs = {
    'H': (1/psg_odds)/total_implied,
    'D': (1/draw_odds)/total_implied,
    'A': (1/ars_odds)/total_implied,
}
market_odds = {'H': psg_odds, 'D': draw_odds, 'A': ars_odds}

print(f'\n投注系统分析:')
for outcome, prob in market_probs.items():
    odds = market_odds[outcome]
    tier = get_confidence_tier(prob)
    kelly_frac = kc.kelly_fraction(prob, odds)
    ev = kc.expected_value(prob, odds)
    edge = kc.edge(prob, odds)
    
    name = 'PSG' if outcome == 'H' else ('Draw' if outcome == 'D' else 'Arsenal')
    print(f'  {name:12s} 概率={prob:.1%} 赔率={odds:.2f} '
          f'Kelly={kelly_frac:.2%} 分层={tier.value} EV={ev:.1%}')

print(f'\n欧冠历史规律 (VHigh+ 低赔方):')
print(f'  全赛季 VHigh+ 低赔方胜率: {vhigh["correct"].mean():.1%}')
print(f'  ROI (固定注额): {roi:.2%}')
print(f'\n结论:')
print(f'  - 市场认为 PSG 略热门 (psg ~43% vs arsenal ~31%)')
print(f'  - 单场决赛无统计 edge，娱乐为主')
print(f'  - 如果要投，低赔方(PSG)的欧冠 VHigh+ 历史胜率 ~76%')
