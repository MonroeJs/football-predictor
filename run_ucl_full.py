"""
欧冠 25/26 完整赛季投注系统回测

使用市场赔率隐含概率作为"预测信号" + 置信度分层 + Kelly资金管理。
修复了自引用edge=0的问题: 低赔方策略直接投注市场最爱。
"""
import sys, warnings, json
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')

from pathlib import Path
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

from src.betting_system import (
    KellyCalculator, get_confidence_tier, ConfidenceTier,
    BettingResult, TierStats, export_results,
)

from config import RAW_DIR

# ═══════════════════════════════════════════════════════════════
# 1. 数据加载
# ═══════════════════════════════════════════════════════════════

def load_ucl_data(season='2526'):
    """加载欧冠数据"""
    path = RAW_DIR / f'UCL_{season}.csv'
    if not path.exists():
        # 从football-data下载再存
        import requests
        from io import StringIO
        url = f'https://www.football-data.co.uk/mmz4281/{season}/EC.csv'
        r = requests.get(url, timeout=30)
        text = r.content.decode('utf-8-sig')
        df = pd.read_csv(StringIO(text))
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    else:
        df = pd.read_csv(path)
    
    std = pd.DataFrame()
    std['date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
    std['home_team'] = df['HomeTeam'].astype(str)
    std['away_team'] = df['AwayTeam'].astype(str)
    std['home_goals'] = pd.to_numeric(df['FTHG'], errors='coerce')
    std['away_goals'] = pd.to_numeric(df['FTAG'], errors='coerce')
    std['result'] = df['FTR']
    std['B365H'] = pd.to_numeric(df['B365H'], errors='coerce')
    std['B365D'] = pd.to_numeric(df['B365D'], errors='coerce')
    std['B365A'] = pd.to_numeric(df['B365A'], errors='coerce')
    
    # 过滤无赔率/无结果的比赛
    std = std.dropna(subset=['B365H', 'result'])
    std = std[std['home_goals'].notna()]
    std = std[std['result'].isin(['H', 'D', 'A'])]
    std = std.sort_values('date').reset_index(drop=True)
    
    # 市场隐含概率
    for k, col in [('H', 'B365H'), ('D', 'B365D'), ('A', 'B365A')]:
        std[f'imp_{k}'] = 1.0 / std[col].clip(lower=1.01)
    total = std['imp_H'] + std['imp_D'] + std['imp_A']
    for k in ['H', 'D', 'A']:
        std[f'prob_{k}'] = std[f'imp_{k}'] / total
    
    # 市场最爱 (赔率最低的)
    odds_cols = ['B365H', 'B365D', 'B365A']
    outcomes = ['H', 'D', 'A']
    fav_idx = std[odds_cols].idxmin(axis=1).map({c: o for c, o in zip(odds_cols, outcomes)})
    std['favorite'] = fav_idx
    std['fav_odds'] = std.apply(lambda r: r[f'B365{r["favorite"]}'], axis=1)
    std['fav_prob'] = std.apply(lambda r: r[f'prob_{r["favorite"]}'], axis=1)
    
    return std


# ═══════════════════════════════════════════════════════════════
# 2. 投注回测引擎
# ═══════════════════════════════════════════════════════════════

@dataclass
class BetRecord:
    match_id: str
    date: str
    tier: str
    bet_on: str
    actual: str
    odds: float
    prob: float
    stake: float
    profit: float
    won: bool
    correct_pred: bool


def backtest_favorite_strategy(
    df,
    initial_bankroll=10000.0,
    stake_per_bet=10.0,
    min_tier='VHigh',
    use_kelly=False,
    verbose=True,
):
    """
    低赔方策略：投注每场比赛的市场最爱
    
    策略逻辑：
    - 找出市场赔率最低方（市场最爱）
    - 计算置信度分层
    - 如果达到 min_tier 门槛，投注
    - 固定或 Kelly 资金管理
    """
    kc = KellyCalculator()
    bankroll = initial_bankroll
    max_bankroll = initial_bankroll
    min_bankroll = initial_bankroll
    
    tier_order = ['Max', 'Elite', 'VHigh', 'High', 'Medium', 'Low']
    min_idx = tier_order.index(min_tier) if min_tier in tier_order else 0
    
    records = []
    bankroll_history = [{'iter': 0, 'bankroll': bankroll, 'event': 'init'}]
    
    total_bets = 0
    total_staked = 0
    total_profit = 0
    won_bets = 0
    
    for i, (_, row) in enumerate(df.iterrows()):
        fav = row['favorite']
        prob = row['fav_prob']
        odds = row['fav_odds']
        actual = row['result']
        
        tier = get_confidence_tier(prob)
        tier_ok = tier_order.index(tier.value) <= min_idx
        
        # 统计预测准确率（不管是否投注）
        pred_correct = (fav == actual)
        
        bet_on = None
        bet_stake = 0.0
        bet_profit = 0.0
        won = None
        
        if tier_ok and odds > 1.0 and bankroll > 0:
            bet_on = fav
            total_bets += 1
            
            if use_kelly:
                kelly_frac = kc.kelly_fraction(prob, odds)
                # 分层调整
                tier_fracs = {
                    ConfidenceTier.MAX: 0.50,
                    ConfidenceTier.ELITE: 0.40,
                    ConfidenceTier.VERY_HIGH: 0.30,
                    ConfidenceTier.HIGH: 0.15,
                    ConfidenceTier.MEDIUM: 0.05,
                    ConfidenceTier.LOW: 0.0,
                }
                adj_frac = kelly_frac * tier_fracs.get(tier, 0.25)
                # 最低 Kelly 分数：如果正期望但 Kelly 太小，强制投最小注
                min_kelly = 0.005  # 0.5% of bankroll minimum
                effective_frac = max(adj_frac, min_kelly) if kelly_frac > 0.001 else adj_frac
                cap = bankroll * 0.10
                bet_stake = min(bankroll * effective_frac, cap)
            else:
                bet_stake = min(stake_per_bet, bankroll)
            
            bet_stake = round(max(bet_stake, 0), 2)
            
            if bet_stake > 0:
                if bet_on == actual:
                    won = True
                    bet_profit = bet_stake * (odds - 1)
                    won_bets += 1
                else:
                    won = False
                    bet_profit = -bet_stake
                
                bankroll += bet_profit
                total_staked += bet_stake
                total_profit += bet_profit
        
        max_bankroll = max(max_bankroll, bankroll)
        min_bankroll = min(min_bankroll, bankroll)
        
        records.append(BetRecord(
            match_id=f"{row['home_team']} vs {row['away_team']}",
            date=str(row['date'])[:10],
            tier=tier.value,
            bet_on=bet_on,
            actual=actual,
            odds=odds,
            prob=prob,
            stake=bet_stake,
            profit=round(bet_profit, 2),
            won=won,
            correct_pred=pred_correct,
        ))
        
        bankroll_history.append({
            'iter': i + 1,
            'bankroll': round(bankroll, 2),
            'event': 'bet' if bet_on else 'skip',
            'profit': round(bet_profit, 2),
        })
    
    # 计算指标
    total_matches = len(records)
    win_rate = won_bets / total_bets if total_bets > 0 else 0
    roi = total_profit / total_staked if total_staked > 0 else 0
    drawdown = _calc_drawdown(bankroll_history)
    kelly_roi = (bankroll - initial_bankroll) / initial_bankroll
    
    # 分层统计
    tier_stats = {}
    tier_pred_acc = {}
    
    for t in tier_order:
        t_records = [r for r in records if r.tier == t]
        t_bets = [r for r in t_records if r.bet_on is not None]
        
        # 预测准确率
        if t_records:
            tier_pred_acc[t] = round(
                sum(1 for r in t_records if r.correct_pred) / len(t_records), 4
            )
        
        # 投注统计
        if t_bets:
            staked = sum(r.stake for r in t_bets)
            profit = sum(r.profit for r in t_bets)
            twon = sum(1 for r in t_bets if r.won)
            tier_stats[t] = TierStats(
                tier=t,
                total_bets=len(t_bets),
                won=twon,
                lost=len(t_bets) - twon,
                accuracy=twon / len(t_bets) if t_bets else 0,
                total_staked=round(staked, 2),
                total_profit=round(profit, 2),
                roi=round(profit / staked, 4) if staked > 0 else 0,
                avg_odds=round(np.mean([r.odds for r in t_bets]), 4),
                avg_edge=0,
            )
    
    # 汇总
    summary = {
        'total_matches': total_matches,
        'total_bets': total_bets,
        'bet_rate': f'{total_bets/total_matches:.1%}' if total_matches else '0%',
        'win_rate': f'{win_rate:.1%}',
        'total_staked': f'{total_staked:.0f}',
        'total_profit': f'{total_profit:+.0f}',
        'roi': f'{roi:.2%}',
        'avg_odds': f'{np.mean([r.odds for r in records if r.bet_on]):.2f}' if total_bets else 'N/A',
        'kelly_roi': f'{kelly_roi:.2%}',
        'final_bankroll': f'{bankroll:.0f}',
        'bankroll_change': f'{bankroll - initial_bankroll:+.0f}',
        'drawdown': f'{drawdown:.1%}',
        'tier_performance': {
            t: {
                'bets': s.total_bets,
                'win_rate': f'{s.accuracy:.1%}',
                'roi': f'{s.roi:.2%}',
                'profit': f'{s.total_profit:+.0f}',
            }
            for t, s in sorted(tier_stats.items())
        },
        'prediction_accuracy_by_tier': {
            t: f'{a:.1%}' for t, a in sorted(tier_pred_acc.items())
        },
    }
    
    return {
        'summary': summary,
        'tier_stats': tier_stats,
        'tier_prediction_accuracy': tier_pred_acc,
        'total_matches': total_matches,
        'total_bets': total_bets,
        'bets_placed_pct': round(total_bets / total_matches, 4) if total_matches else 0,
        'total_staked': round(total_staked, 2),
        'total_profit': round(total_profit, 2),
        'roi': round(roi, 4),
        'initial_bankroll': initial_bankroll,
        'final_bankroll': round(bankroll, 2),
        'max_bankroll': round(max_bankroll, 2),
        'min_bankroll': round(min_bankroll, 2),
        'drawdown': round(drawdown, 4),
        'win_rate': round(win_rate, 4),
        'kelly_roi': round(kelly_roi, 4),
        'records': records,
        'bankroll_history': bankroll_history,
    }, records


def _calc_drawdown(history):
    """最大回撤"""
    values = [h['bankroll'] for h in history]
    if not values:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            max_dd = max(max_dd, dd)
    return max_dd


# ═══════════════════════════════════════════════════════════════
# 3. 输出
# ═══════════════════════════════════════════════════════════════

def print_summary(result, label=''):
    """美观输出"""
    s = result['summary']
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  全局统计:")
    print(f"    总比赛:    {s['total_matches']} 场")
    print(f"    投注场次:  {s['total_bets']} ({s['bet_rate']})")
    print(f"    胜率:      {s['win_rate']}")
    print(f"    总投注额:  {s['total_staked']}")
    print(f"    总盈亏:    {s['total_profit']}")
    print(f"    ROI:       {s['roi']}")
    print(f"    平均赔率:  {s['avg_odds']}")
    print(f"    最大回撤:  {s['drawdown']}")
    print(f"\n  资金变化:")
    print(f"    初始资金:  {result['initial_bankroll']:.0f}")
    print(f"    最终资金:  {s['final_bankroll']}")
    print(f"    Kelly ROI: {s['kelly_roi']}")
    print(f"    资金变化:  {s['bankroll_change']}")
    
    print(f"\n  预测准确率分层:")
    print(f"  {'分层':12s} {'场次':>6s} {'准确率':>8s}")
    print(f"  {'─'*28}")
    for t in ['Max', 'Elite', 'VHigh', 'High', 'Medium', 'Low']:
        if t in result['tier_prediction_accuracy']:
            n = sum(1 for r in result['records'] if r.tier == t)
            print(f"  {t:12s} {n:>6d} {result['tier_prediction_accuracy'][t]:>7.1%}")
    
    print(f"\n  投注分层统计:")
    print(f"  {'分层':12s} {'投注':>5s} {'胜率':>7s} {'ROI':>7s} {'盈亏':>10s} {'投注额':>10s}")
    print(f"  {'─'*52}")
    for t in ['Max', 'Elite', 'VHigh', 'High', 'Medium', 'Low']:
        if t in result['tier_stats']:
            ts = result['tier_stats'][t]
            print(f"  {t:12s} {ts.total_bets:>5d} {ts.accuracy:>6.1%} {ts.roi:>6.2%} "
                  f"{ts.total_profit:>+10.0f} {ts.total_staked:>10.0f}")
    
    total_bets = result['total_bets']
    if total_bets:
        print(f"  {'─'*52}")
        print(f"  合计: {total_bets:>5d}投 {result['win_rate']:>6.1%} "
              f"{result['roi']:>6.2%} {result['total_profit']:>+10.0f} {result['total_staked']:>10.0f}")


def save_result(result, path='betting_results/ucl_2526.json'):
    """保存结果"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        'summary': result['summary'],
        'tier_stats': {t: asdict(s) for t, s in result['tier_stats'].items()},
        'tier_prediction_accuracy': result['tier_prediction_accuracy'],
        'bankroll_history': result['bankroll_history'],
        'records_preview': [
            {
                'match': r.match_id,
                'tier': r.tier,
                'bet_on': r.bet_on,
                'actual': r.actual,
                'odds': r.odds,
                'prob': r.prob,
                'stake': r.stake,
                'profit': r.profit,
                'won': r.won,
            }
            for r in result['records'][-100:]
        ],
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'\n结果已导出: {path}')


# ═══════════════════════════════════════════════════════════════
# 4. 主流程
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('=' * 60)
    print('  欧冠 25/26 完整赛季投注重测')
    print('=' * 60)
    
    print('\n加载数据...')
    df = load_ucl_data('2526')
    print(f'  欧冠 2526 赛季: {len(df)} 场比赛')
    
    # 结果分布
    res_dist = df['result'].value_counts(normalize=True)
    print(f'  结果分布: H={res_dist.get("H",0):.1%} D={res_dist.get("D",0):.1%} A={res_dist.get("A",0):.1%}')
    
    # ── 策略 A: 低赔方 + 全部层级（含低置信度） ──
    print(f'\n{"="*60}')
    print(f'  策略 A: 低赔方 · 全部层级 (10单位固定)')
    print(f'{"="*60}')
    result_all, records_all = backtest_favorite_strategy(
        df, initial_bankroll=10000, stake_per_bet=10,
        min_tier='Low', use_kelly=False,
    )
    print_summary(result_all, '低赔方 · 全部层级')
    
    # ── 策略 B: 低赔方 + VHigh+ 仅高置信度 ──
    print(f'\n{"="*60}')
    print(f'  策略 B: 低赔方 · VHigh+ 仅高置信度 (10单位固定)')
    print(f'{"="*60}')
    result_vhigh, records_vhigh = backtest_favorite_strategy(
        df, initial_bankroll=10000, stake_per_bet=10,
        min_tier='VHigh', use_kelly=False,
    )
    print_summary(result_vhigh, '低赔方 · VHigh+')
    
    # ── 策略 C: 低赔方 + VHigh+ + Kelly ──
    print(f'\n{"="*60}')
    print(f'  策略 C: 低赔方 · VHigh+ · Kelly 资金管理')
    print(f'{"="*60}')
    result_kelly, records_kelly = backtest_favorite_strategy(
        df, initial_bankroll=10000, stake_per_bet=10,
        min_tier='VHigh', use_kelly=True,
    )
    print_summary(result_kelly, '低赔方 · VHigh+ · Kelly')
    
    # ── 策略 D: 低赔方 + Elite+ 超精选 ──
    print(f'\n{"="*60}')
    print(f'  策略 D: 低赔方 · Elite+ 超精选 (10单位固定)')
    print(f'{"="*60}')
    result_elite, records_elite = backtest_favorite_strategy(
        df, initial_bankroll=10000, stake_per_bet=10,
        min_tier='Elite', use_kelly=False,
    )
    print_summary(result_elite, '低赔方 · Elite+')
    
    # ── 汇总对比 ──
    print(f'\n\n{"="*60}')
    print(f'  欧冠 2526 投注重测汇总')
    print(f'{"="*60}')
    print(f"  {'策略':45s} {'投注':>5s} {'胜率':>7s} {'ROI':>8s} {'盈亏':>12s} {'回撤':>7s}")
    print(f"  {'─'*86}")
    
    for label, r in [
        ('A: 低赔方 · 全部层级', result_all),
        ('B: 低赔方 · VHigh+', result_vhigh),
        ('C: 低赔方 · VHigh+ · Kelly', result_kelly),
        ('D: 低赔方 · Elite+', result_elite),
    ]:
        s = r['summary']
        print(f"  {label:43s} {s['total_bets']:>5d} "
              f"{s['win_rate']:>7s} {s['roi']:>8s} "
              f"{s['total_profit']:>12s} {s['drawdown']:>7s}")
    
    # 保存
    save_result(result_vhigh, 'betting_results/ucl_2526_vhigh.json')
    save_result(result_kelly, 'betting_results/ucl_2526_kelly.json')
    
    print(f'\n分析完成!')
