"""
小组出线概率计算 — Monte Carlo 模拟

对每组4支队伍，基于赔率模拟 100,000 次小组赛，
统计各队小组头名和出线（前二）概率。

原理：
  1. 从赔率反推每场的 胜/平/负 概率
  2. 对每场比赛，按概率随机生成结果
  3. 用泊松分布模拟进球数（基于赔率隐含期望进球）
  4. 积分排名 → 记录出线队伍
  5. 重复 N 次 → 统计频率
"""
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

# 2026 世界杯各小组队伍
GROUPS = {
    'A': ['Mexico', 'South Korea', 'South Africa', 'Czechia'],
    'B': ['Canada', 'Bosnia', 'Qatar', 'Switzerland'],
    'C': ['Brazil', 'Morocco', 'Scotland', 'Haiti'],
    'D': ['USA', 'Paraguay', 'Australia', 'Turkey'],
    'E': ['Germany', 'Curacao', 'Ivory Coast', 'Ecuador'],
    'F': ['Netherlands', 'Japan', 'Sweden', 'Tunisia'],
    'G': ['Belgium', 'Iran', 'Egypt', 'New Zealand'],
    'H': ['Spain', 'Cape Verde', 'Saudi Arabia', 'Uruguay'],
    'I': ['France', 'Senegal', 'Iraq', 'Norway'],
    'J': ['Argentina', 'Algeria', 'Austria', 'Jordan'],
    'K': ['Portugal', 'DR Congo', 'Uzbekistan', 'Colombia'],
    'L': ['England', 'Croatia', 'Ghana', 'Panama'],
}

# 小组内比赛配对模板 (index -> (home_idx, away_idx))
# 标准循环赛顺序
GROUP_MATCHUPS = [
    (0, 1), (2, 3),  # MD1
    (0, 2), (1, 3),  # MD2
    (0, 3), (1, 2),  # MD3
]

N_SIMULATIONS = 5000    # 每次计算模拟次数（5k 足够稳定，±1%）
CACHE: dict = {}        # 缓存 {group_key: result}


def warm_cache():
    """预加载缓存（在后台线程或导入时调用）"""
    import threading
    def _warm():
        calc_all_groups(force_refresh=True)
    t = threading.Thread(target=_warm, daemon=True)
    t.start()
    return t


def odds_to_probs(b365h: float, b365d: float, b365a: float) -> tuple[float, float, float]:
    """赔率 → 隐含概率（去除抽水）"""
    total = 1.0 / max(b365h, 1.01) + 1.0 / max(b365d, 1.01) + 1.0 / max(b365a, 1.01)
    return (1.0 / max(b365h, 1.01) / total,
            1.0 / max(b365d, 1.01) / total,
            1.0 / max(b365a, 1.01) / total)


def expected_goals_from_odds(h_prob: float, d_prob: float, a_prob: float) -> tuple[float, float]:
    """从胜平负概率近似估计期望进球数"""
    # 用比分概率反推期望进球
    # 常见模型：总期望进球 ≈ 2.5 * (1 + 0.3*(max_prob - 0.33))
    max_prob = max(h_prob, a_prob)
    total_xg = 2.5 * (1.0 + 0.3 * (max_prob - 0.33))
    
    # 按实力分配
    strength_ratio = max(h_prob / max(a_prob, 0.01), a_prob / max(h_prob, 0.01))
    if h_prob > a_prob:
        home_xg = total_xg * (0.55 + 0.1 * min(strength_ratio - 1, 2))
        away_xg = total_xg - home_xg
    else:
        away_xg = total_xg * (0.55 + 0.1 * min(strength_ratio - 1, 2))
        home_xg = total_xg - away_xg
    
    return max(0.2, home_xg), max(0.2, away_xg)


def simulate_match(h_xg: float, a_xg: float) -> tuple[int, int]:
    """模拟一场比赛的比分（泊松分布）"""
    home_goals = np.random.poisson(h_xg)
    away_goals = np.random.poisson(a_xg)
    return home_goals, away_goals


def get_match_result(h_goals: int, a_goals: int) -> str:
    """比分 → 比赛结果"""
    if h_goals > a_goals:
        return 'H'
    elif h_goals < a_goals:
        return 'A'
    else:
        return 'D'


def load_group_odds() -> dict:
    """从 run_wc_odds.csv 加载各小组比赛的赔率
    
    返回: {group: [(home, away, b365h, b365d, b365a), ...]}
    """
    csv_path = Path(__file__).parent.parent / 'run_wc_odds.csv'
    if not csv_path.exists():
        return {}
    
    df = pd.read_csv(csv_path)
    group_odds = {}
    
    for group in GROUPS:
        group_matches = df[df['group'] == group]
        matches = []
        for _, row in group_matches.iterrows():
            matches.append((
                row['home'], row['away'],
                float(row['B365H']), float(row['B365D']), float(row['B365A']),
            ))
        group_odds[group] = matches
    
    return group_odds


def simulate_group(group_teams: list[str], 
                   match_odds: list[tuple]) -> dict:
    """Monte Carlo 模拟一个小组
    
    参数:
        group_teams: 组内4队队名
        match_odds: [(home, away, b365h, b365d, b365a)]
        
    返回:
        {队名: {'win_group': 0.xx, 'advance': 0.xx}}
    """
    team_idx = {t: i for i, t in enumerate(group_teams)}
    n = len(group_teams)
    
    # 解析每场比赛涉及哪两队
    match_info = []
    for home, away, h_odds, d_odds, a_odds in match_odds:
        hi = team_idx.get(home)
        ai = team_idx.get(away)
        if hi is None or ai is None:
            continue
        ph, pd_, pa_ = odds_to_probs(h_odds, d_odds, a_odds)
        h_xg, a_xg = expected_goals_from_odds(ph, pd_, pa_)
        match_info.append((hi, ai, ph, pd_, pa_, h_xg, a_xg))
    
    if len(match_info) < 6:
        return {}
    
    # Monte Carlo
    win_group_count = {t: 0 for t in group_teams}
    advance_count = {t: 0 for t in group_teams}
    
    for _ in range(N_SIMULATIONS):
        points = [0] * n
        gd = [0] * n   # 净胜球
        gf = [0] * n   # 进球数
        
        for hi, ai, ph, pd_, pa_, h_xg, a_xg in match_info:
            # 随机决定结果
            r = np.random.random()
            if r < ph:
                # 主胜
                hg, ag = simulate_match(h_xg, a_xg)
                if hg <= ag:
                    hg, ag = ag + 1, ag  # 确保主胜
            elif r < ph + pd_:
                # 平局
                hg = np.random.poisson((h_xg + a_xg) / 2)
                ag = hg
            else:
                # 客胜
                ag, hg = simulate_match(a_xg, h_xg)
                if ag <= hg:
                    ag, hg = hg + 1, hg
            
            # 积分
            if hg > ag:
                points[hi] += 3
            elif hg < ag:
                points[ai] += 3
            else:
                points[hi] += 1
                points[ai] += 1
            
            gd[hi] += hg - ag
            gd[ai] += ag - hg
            gf[hi] += hg
            gf[ai] += ag
        
        # 排名
        ranking = sorted(range(n), key=lambda i: (points[i], gd[i], gf[i]), reverse=True)
        
        win_group_count[group_teams[ranking[0]]] += 1
        advance_count[group_teams[ranking[0]]] += 1
        advance_count[group_teams[ranking[1]]] += 1
    
    result = {}
    for team in group_teams:
        result[team] = {
            'win_group': win_group_count[team] / N_SIMULATIONS,
            'advance': advance_count[team] / N_SIMULATIONS,
        }
    
    return result


def calc_all_groups(force_refresh: bool = False) -> dict:
    """计算所有小组的出线概率
    
    返回: {group: {team: {'win_group': p, 'advance': p}}}
    """
    global CACHE
    
    if CACHE and not force_refresh:
        return CACHE
    
    group_odds = load_group_odds()
    if not group_odds:
        return {}
    
    results = {}
    for group, teams in GROUPS.items():
        matches = group_odds.get(group, [])
        if len(matches) < 6:
            print(f'  Group {group}: 赔率不足 ({len(matches)} matches)')
            continue
        
        result = simulate_group(teams, matches)
        if result:
            results[group] = result
    
    CACHE = results
    return results


def print_group_probs(results: dict):
    """打印小组出线概率"""
    for group in 'ABCDEFGHIJKL':
        if group not in results:
            continue
        
        print(f'\nGroup {group}:')
        teams = sorted(results[group].items(),
                       key=lambda x: x[1]['advance'], reverse=True)
        for team, probs in teams:
            w = probs['win_group'] * 100
            a = probs['advance'] * 100
            bar_len = int(a / 5)
            bar = '#' * bar_len + '.' * (20 - bar_len)
            print(f'  {team:16s}  {bar}  {a:5.1f}% (1st {w:.1f}%)')


if __name__ == '__main__':
    print('Calculating group probabilities (100k simulations per group)...')
    results = calc_all_groups(force_refresh=True)
    print_group_probs(results)
