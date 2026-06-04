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
# (Also exported in wc_predictor.py as WC_2026_GROUPS)
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

N_SIMULATIONS = 5000    # 小组赛模拟次数（单次快速，有缓存）
FULL_SIMULATIONS = 50000 # 完整赛事模拟次数（后台预热用）
CACHE: dict = {}        # 缓存 {group_key: result}
TOURNEY_CACHE: dict = {}  # 缓存 calc_full_tournament() 结果
TOURNEY_CACHE_TIME: float = 0
import time as _time


# ─── Knockout stage constants ─────────────────────────────────

# Knockout round names (index 0=R32 … 5=Champion)
ROUND_NAMES = ['R32', 'R16', 'QF', 'SF', 'Final', 'Champion']

# Standard 32-team seeded bracket: seed-position pairs (1-indexed)
# Produces balanced halves so 1-vs-32 won't meet 2-vs-31 until the final.
R32_BRACKET = [
    (1, 32), (16, 17), (8, 25), (9, 24),
    (5, 28), (12, 21), (4, 29), (13, 20),
    (3, 30), (14, 19), (6, 27), (11, 22),
    (7, 26), (10, 23), (2, 31), (15, 18),
]

# ─── Elo ratings (mirrored from wc_predictor.TEAM_ELO) ────────
# Inlined here to avoid circular import risk.
TEAM_ELO = {
    'Argentina': 2084, 'France': 2076, 'Spain': 2068, 'England': 2055,
    'Brazil': 2047, 'Germany': 2038, 'Portugal': 2029, 'Netherlands': 2021,
    'Belgium': 1998, 'Croatia': 1992, 'Uruguay': 1987, 'USA': 1978,
    'Mexico': 1965, 'Japan': 1958, 'Switzerland': 1952, 'Colombia': 1948,
    'Morocco': 1942, 'Senegal': 1935, 'South Korea': 1928, 'Norway': 1925,
    'Austria': 1918, 'Ecuador': 1912, 'Egypt': 1908, 'Ivory Coast': 1898,
    'Australia': 1885, 'Algeria': 1878, 'Scotland': 1872, 'Ghana': 1865,
    'Paraguay': 1858, 'Iran': 1852, 'Canada': 1845, 'Tunisia': 1838,
    'Panama': 1822, 'Saudi Arabia': 1815, 'South Africa': 1802,
    'Qatar': 1795, 'New Zealand': 1788, 'Cape Verde': 1775,
    'Uzbekistan': 1768, 'Jordan': 1755, 'Haiti': 1728, 'Curacao': 1705,
    'Czechia': 1902, 'Bosnia': 1780, 'Sweden': 1785, 'Turkey': 1850,
    'DR Congo': 1750, 'Iraq': 1735,
}


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


# ═══════════════════════════════════════════════════════════════
# Knockout Stage — Monte Carlo Full Tournament
# ═══════════════════════════════════════════════════════════════

def elo_expected(rating_a: float, rating_b: float) -> float:
    """Elo expected score for team A vs team B (neutral venue)."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _simulate_knockout_match(team_a: str, team_b: str,
                              elo_map: dict[str, int]) -> str:
    """Simulate one knockout match using Elo probabilities. Returns winner."""
    elo_a = elo_map.get(team_a, 1800)
    elo_b = elo_map.get(team_b, 1800)
    prob_a = elo_expected(elo_a, elo_b)
    return team_a if np.random.random() < prob_a else team_b


def _simulate_knockout_round(teams_in_round: list[str],
                              matchups: list[tuple[int, int]],
                              elo_map: dict[str, int]) -> list[str]:
    """Simulate one round given matchups (index pairs into teams_in_round)."""
    winners = []
    for i, j in matchups:
        winner = _simulate_knockout_match(teams_in_round[i], teams_in_round[j], elo_map)
        winners.append(winner)
    return winners


def _simulate_all_groups_once(group_odds_dict: dict) -> list[dict]:
    """Simulate all 12 groups once and return detailed results per team.

    Returns: list of dicts with keys:
        team, points, gd, gf, group_rank (1-4), group
    """
    all_results = []

    for group_letter, teams in GROUPS.items():
        matches = group_odds_dict.get(group_letter, [])
        if len(matches) < 6:
            continue

        team_idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)

        # Parse match info
        match_info = []
        for home, away, h_odds, d_odds, a_odds in matches:
            hi = team_idx.get(home)
            ai = team_idx.get(away)
            if hi is None or ai is None:
                continue
            ph, pd_, pa_ = odds_to_probs(h_odds, d_odds, a_odds)
            h_xg, a_xg = expected_goals_from_odds(ph, pd_, pa_)
            match_info.append((hi, ai, ph, pd_, pa_, h_xg, a_xg))

        if len(match_info) < 6:
            continue

        points = [0] * n
        gd = [0] * n
        gf = [0] * n

        for hi, ai, ph, pd_, pa_, h_xg, a_xg in match_info:
            r = np.random.random()
            if r < ph:
                hg, ag = simulate_match(h_xg, a_xg)
                if hg <= ag:
                    hg, ag = ag + 1, ag
            elif r < ph + pd_:
                hg = np.random.poisson((h_xg + a_xg) / 2)
                ag = hg
            else:
                ag, hg = simulate_match(a_xg, h_xg)
                if ag <= hg:
                    ag, hg = hg + 1, hg

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

        ranking = sorted(range(n), key=lambda i: (points[i], gd[i], gf[i]), reverse=True)

        for rank, idx in enumerate(ranking):
            all_results.append({
                'team': teams[idx],
                'points': points[idx],
                'gd': gd[idx],
                'gf': gf[idx],
                'group_rank': rank + 1,
                'group': group_letter,
            })

    return all_results


def _select_knockout_teams(all_group_results: list[dict]) -> list[dict]:
    """From all group results, pick top 2 per group + 8 best 3rd-place teams.

    Returns: list of team dicts sorted by seed (points, GD, GF descending).
    """
    group_winners = [r for r in all_group_results if r['group_rank'] == 1]
    runners_up = [r for r in all_group_results if r['group_rank'] == 2]
    third_places = [r for r in all_group_results if r['group_rank'] == 3]

    # Best 8 third-placed teams
    third_places.sort(key=lambda r: (r['points'], r['gd'], r['gf']), reverse=True)
    best_third = third_places[:8]

    knockout_teams = group_winners + runners_up + best_third
    knockout_teams.sort(key=lambda r: (r['points'], r['gd'], r['gf']), reverse=True)

    return knockout_teams


def _simulate_knockout_bracket(seeded_teams: list[dict],
                                elo_map: dict[str, int]) -> dict[str, int]:
    """Full knockout bracket simulation.

    Args:
        seeded_teams: list of dicts sorted by seed (1..32), must have 'team' key
        elo_map: team -> Elo rating

    Returns:
        dict mapping team_name -> round_reached_index (0=R32 … 5=Champion)
    """
    r32_teams = [t['team'] for t in seeded_teams]
    r32_matchups = [(a - 1, b - 1) for a, b in R32_BRACKET]

    # R32 → R16
    r16_teams = _simulate_knockout_round(r32_teams, r32_matchups, elo_map)
    # R16 → QF: consecutive pairs
    qf_teams = _simulate_knockout_round(r16_teams,
                                         [(i, i + 1) for i in range(0, 16, 2)],
                                         elo_map)
    # QF → SF
    sf_teams = _simulate_knockout_round(qf_teams,
                                         [(i, i + 1) for i in range(0, 8, 2)],
                                         elo_map)
    # SF → Final
    final_teams = _simulate_knockout_round(sf_teams, [(0, 1), (2, 3)], elo_map)
    # Final → Champion
    champion = _simulate_knockout_match(final_teams[0], final_teams[1], elo_map)

    # Build result
    result = {team: 0 for team in r32_teams}  # all reach R32
    for team in r16_teams:
        result[team] = 1
    for team in qf_teams:
        result[team] = 2
    for team in sf_teams:
        result[team] = 3
    for team in final_teams:
        result[team] = 4
    result[champion] = 5

    return result


def simulate_full_tournament(n_simulations: int = FULL_SIMULATIONS) -> tuple[dict, dict, dict]:
    """Full tournament Monte Carlo simulation.

    Each iteration simulates all 12 groups, selects the 32 knockout teams,
    then runs the single-elimination bracket using Elo-based match probabilities.

    Returns:
        tuple of (champion_probs, round_probs, group_stage)
        - champion_probs: {team: championship_probability}
        - round_probs:    {team: {round_name: prob}}  (R32/R16/QF/SF/Final/Champion)
        - group_stage:    same format as calc_all_groups()
    """
    group_odds = load_group_odds()
    if not group_odds:
        return {}, {}, {}

    # Accumulators
    champion_count: dict[str, int] = {}
    round_counts: dict[str, list[int]] = {}  # team -> [r32, r16, qf, sf, final, champion]
    group_win_count: dict[str, int] = {}
    group_adv_count: dict[str, int] = {}

    all_teams = [t for teams in GROUPS.values() for t in teams]
    for team in all_teams:
        champion_count[team] = 0
        round_counts[team] = [0] * 6
        group_win_count[team] = 0
        group_adv_count[team] = 0

    for _ in range(n_simulations):
        # --- Group stage ---
        all_results = _simulate_all_groups_once(group_odds)

        # Track group stage
        for r in all_results:
            if r['group_rank'] == 1:
                group_win_count[r['team']] += 1
                group_adv_count[r['team']] += 1
            elif r['group_rank'] == 2:
                group_adv_count[r['team']] += 1

        # --- Select knockout teams ---
        seeded = _select_knockout_teams(all_results)
        if len(seeded) < 32:
            continue

        # All 32 qualified teams reach R32
        for s in seeded:
            round_counts[s['team']][0] += 1

        # --- Knockout bracket ---
        ko_result = _simulate_knockout_bracket(seeded, TEAM_ELO)

        for team, round_idx in ko_result.items():
            for r in range(1, round_idx + 1):
                round_counts[team][r] += 1
            if round_idx == 5:
                champion_count[team] += 1

    # Normalise
    n = float(n_simulations)
    champion_probs = {t: champion_count[t] / n for t in all_teams}

    round_probs: dict[str, dict[str, float]] = {}
    for team in all_teams:
        round_probs[team] = {
            ROUND_NAMES[i]: round_counts[team][i] / n for i in range(6)
        }

    group_stage: dict[str, dict] = {}
    for g, teams in GROUPS.items():
        group_stage[g] = {}
        for t in teams:
            group_stage[g][t] = {
                'win_group': group_win_count[t] / n,
                'advance': group_adv_count[t] / n,
            }

    return champion_probs, round_probs, group_stage


def calc_full_tournament(force_refresh: bool = False) -> dict:
    """Entry point: returns group stage + full tournament probabilities.

    Args:
        force_refresh: Force recalculation even if cache exists.

    Returns a dict with keys:
        'group_stage'    : same format as calc_all_groups()
        'knockout_probs' : {team: {round_name: probability}}
        'champion_probs' : {team: championship_probability}
    """
    global TOURNEY_CACHE, TOURNEY_CACHE_TIME
    now = _time.time()
    if TOURNEY_CACHE and not force_refresh and (now - TOURNEY_CACHE_TIME) < 3600:
        return TOURNEY_CACHE

    champion_probs, round_probs, group_stage = simulate_full_tournament()
    TOURNEY_CACHE = {
        'group_stage': group_stage,
        'knockout_probs': round_probs,
        'champion_probs': champion_probs,
    }
    TOURNEY_CACHE_TIME = now

    return TOURNEY_CACHE


def print_tournament_probs(champion_probs: dict,
                            round_probs: dict,
                            top_n: int = 20):
    """Print champion probabilities and top teams by round advancement."""
    # Champion table
    sorted_teams = sorted(champion_probs.items(), key=lambda x: x[1], reverse=True)

    print(f'\n{"="*70}')
    print(f'  *** 世界杯 2026 夺冠概率 Top {top_n} ***')
    print(f'{"="*70}')
    print(f'  {"队伍":20s} {"冠军":>8s} {"决赛":>8s} {"四强":>8s} {"八强":>8s} {"十六强":>8s}')
    print(f'  {"-"*70}')

    for team, champ_p in sorted_teams[:top_n]:
        rp = round_probs.get(team, {})
        champ_str = f'{champ_p * 100:.1f}%'
        final_str = f'{rp.get("Final", 0) * 100:.1f}%'
        sf_str = f'{rp.get("SF", 0) * 100:.1f}%'
        qf_str = f'{rp.get("QF", 0) * 100:.1f}%'
        r16_str = f'{rp.get("R16", 0) * 100:.1f}%'
        print(f'  {team:20s} {champ_str:>8s} {final_str:>8s} {sf_str:>8s} {qf_str:>8s} {r16_str:>8s}')


if __name__ == '__main__':
    import sys

    # Run full tournament if --full flag is passed, else just groups
    if '--full' in sys.argv:
        print('Running full tournament Monte Carlo (50,000 simulations)...')
        print('  This will simulate all groups + knockout bracket each iteration.\n')
        result = calc_full_tournament()

        # Print group stage
        gs = result.get('group_stage', {})
        if gs:
            print_group_probs(gs)

        # Print tournament probs
        print_tournament_probs(
            result.get('champion_probs', {}),
            result.get('knockout_probs', {}),
            top_n=48,
        )
    else:
        print('Calculating group probabilities...')
        results = calc_all_groups(force_refresh=True)
        print_group_probs(results)
        print('\nHint: run with --full for full tournament simulation')
