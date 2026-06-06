"""
欧冠投注重测 — 使用 Bet365 赔率分析
"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')

import pandas as pd
import numpy as np
from pathlib import Path

from src.betting_system import (
    ConfidenceBettingSystem, run_tiered_backtest_with_model_probs,
    get_confidence_tier, KellyCalculator, export_results,
    _print_results,
)

kelly = KellyCalculator()


def load_ucl(season='2526'):
    """从已下载的本地文件加载欧冠数据"""
    path = f'data/raw/UCL_{season}.csv'
    df = pd.read_csv(path)
    
    std = pd.DataFrame()
    std['season'] = season
    std['date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
    std['home_team'] = df['HomeTeam']
    std['away_team'] = df['AwayTeam']
    std['home_goals'] = pd.to_numeric(df['FTHG'], errors='coerce')
    std['away_goals'] = pd.to_numeric(df['FTAG'], errors='coerce')
    std['result'] = df['FTR']
    
    std['B365H'] = pd.to_numeric(df['B365H'], errors='coerce')
    std['B365D'] = pd.to_numeric(df['B365D'], errors='coerce')
    std['B365A'] = pd.to_numeric(df['B365A'], errors='coerce')
    
    std = std.dropna(subset=['B365H', 'result'])
    std = std[std['home_goals'].notna()]
    std = std.sort_values('date').reset_index(drop=True)
    
    # 隐含概率
    for k, col in [('H', 'B365H'), ('D', 'B365D'), ('A', 'B365A')]:
        std[f'ip_{k}'] = 1.0 / std[col]
    total = std['ip_H'] + std['ip_D'] + std['ip_A']
    std['prob_H'] = std['ip_H'] / total
    std['prob_D'] = std['ip_D'] / total
    std['prob_A'] = std['ip_A'] / total
    
    # 标记淘汰赛阶段
    std['is_knockout'] = std.apply(lambda r: 'Knockout' in str(r.get('Div','')), axis=1)
    
    return std


def backtest_ucl(df, name, cbs_kwargs=None):
    """执行 UCL 回测"""
    kwargs = {'initial_bankroll': 10000, 'min_edge': 0.02, 'use_kelly': True}
    if cbs_kwargs:
        kwargs.update(cbs_kwargs)
    
    y_prob = df[['prob_H', 'prob_D', 'prob_A']].values
    inv_label_map = {0: 'H', 1: 'D', 2: 'A'}
    
    result = run_tiered_backtest_with_model_probs(
        df, y_prob, inv_label_map,
        verbose=False, **kwargs,
    )
    return result


def strategy_favorite(df, stake=10):
    """投注市场赔率最低方（市场最爱）—— 固定注额"""
    cbs = ConfidenceBettingSystem(initial_bankroll=10000, min_edge=-999, use_kelly=False)
    
    for _, row in df.iterrows():
        odds = {'H': row['B365H'], 'D': row['B365D'], 'A': row['B365A']}
        fav = min(odds, key=odds.get)
        
        # 用市场隐含概率
        total = sum(1.0/max(o,1.01) for o in odds.values())
        mp = {k: (1.0/max(odds[k],1.01))/total for k in odds}
        confidence = mp[fav]
        tier = get_confidence_tier(confidence)
        
        # 只在 VHigh+ 投注
        if tier.value in ('Low', 'Medium'):
            continue
        
        actual = row['result']
        if actual not in ('H', 'D', 'A'):
            continue
        
        decision = cbs.evaluate_bet(
            mp, odds,
            f"{row['home_team']} vs {row['away_team']}",
            'UCL', str(row['date'])[:10], actual,
        )
        # Override: 固定金额
        if decision.bet_on is not None:
            decision.bet_stake = min(stake, cbs.bankroll * 0.05)
        cbs.settle_bet(decision)
    
    return cbs.get_betting_stats()


def strategy_home_bias(df):
    """纯主胜，固定注额"""
    cbs = ConfidenceBettingSystem(initial_bankroll=10000, min_edge=-999, use_kelly=False)
    
    for _, row in df.iterrows():
        mp = {'H': 0.48, 'D': 0.28, 'A': 0.24}
        odds = {'H': row['B365H'], 'D': row['B365D'], 'A': row['B365A']}
        actual = row['result']
        if actual not in ('H', 'D', 'A'):
            continue
        decision = cbs.evaluate_bet(
            mp, odds,
            f"{row['home_team']} vs {row['away_team']}",
            'UCL', str(row['date'])[:10], actual,
        )
        if decision.bet_on is not None:
            decision.bet_stake = 10.0
        cbs.settle_bet(decision)
    
    return cbs.get_betting_stats()


if __name__ == '__main__':
    print('=' * 60)
    print('  欧冠投注重测 — 25/26 赛季')
    print('=' * 60)
    
    df = load_ucl('2526')
    print(f'\n2526 赛季: {len(df)} 场比赛')
    
    # 结果分布
    res = df['result'].value_counts(normalize=True)
    print(f'结果分布: H={res.get("H",0):.1%} D={res.get("D",0):.1%} A={res.get("A",0):.1%}')
    
    # 分层预测准确率分析
    print(f'\n{"置信度分层预测准确率":^50}')
    print(f'  {"分层":12s} {"场次":>6s} {"准确率":>8s} {"avg赔率":>8s}')
    print(f'  {"─"*36}')
    
    for t in ['Max', 'Elite', 'VHigh', 'High', 'Medium', 'Low']:
        tier_matches = []
        for _, row in df.iterrows():
            probs = [row['prob_H'], row['prob_D'], row['prob_A']]
            max_prob = max(probs)
            tier = get_confidence_tier(max_prob).value
            if tier == t:
                pred = ['H','D','A'][np.argmax(probs)]
                correct = pred == row['result']
                odds_val = row[f'B365{pred}']
                tier_matches.append((correct, odds_val))
        
        if tier_matches:
            n = len(tier_matches)
            acc = sum(1 for c,_ in tier_matches) / n
            avg_odds = np.mean([o for _,o in tier_matches if o > 1])
            print(f'  {t:12s} {n:>6d} {acc:>7.1%} {avg_odds:>7.2f}')
    
    print('\n\n=== 投注策略对比 ===\n')
    
    # 策略 1: 市场隐含概率 + 投注系统
    print('=' * 50)
    print('  策略 1: 市场隐含概率 + Kelly (edge >= 2%)')
    print('=' * 50)
    r1 = backtest_ucl(df, 'market_odds')
    _print_results(r1)
    
    # 策略 2: 市场隐含概率 + 等额投注
    print('\n' + '=' * 50)
    print('  策略 2: 市场隐含概率 + 等额投注')
    print('=' * 50)
    r2 = backtest_ucl(df, 'flat_bet', {'use_kelly': False})
    _print_results(r2)
    
    # 策略 3: 低赔方 (VHigh+ 只投市场最爱)
    print('\n' + '=' * 50)
    print('  策略 3: 低赔方策略 (VHigh+，固定注额)')
    print('=' * 50)
    r3 = strategy_favorite(df, stake=10)
    _print_results(r3)
    
    # 策略 4: 主胜基准
    print('\n' + '=' * 50)
    print('  策略 4: 主胜基准 (固定注额)')
    print('=' * 50)
    r4 = strategy_home_bias(df)
    _print_results(r4)
    
    # 汇总表
    print('\n' + '=' * 60)
    print('  欧冠 2526 投注重测汇总')
    print('=' * 60)
    header = f"  {'策略':40s} {'投注':>5s} {'胜率':>7s} {'ROI':>8s} {'总盈亏':>12s}"
    print(header)
    print(f"  {'─'*74}")
    
    for name, r in [('市场隐含概率+Kelly', r1), ('市场隐含概率+等额', r2), ('低赔方(VHigh+)', r3), ('主胜基准', r4)]:
        s = r.summary
        nb = str(s['total_bets'])
        wr = str(s['win_rate'])
        ro = str(s['roi'])
        pr = str(s['total_profit'])
        print(f"  {name:38s} {nb:>5s} {wr:>7s} {ro:>8s} {pr:>12s}")
    
    # 导出
    export_path = Path('betting_results/ucl_2526_backtest.json')
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_results(r1, export_path)
    print(f'\n结果已导出: {export_path}')
