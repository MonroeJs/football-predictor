"""
泊松分布预测模型 + Elo 概率融合

基于历史数据计算主客队预期进球，使用泊松分布预测比分概率。
按联赛分别计算场均进球，避免跨联赛数据稀释模型精度。

改进:
1. Dixon-Coles 低比分相关系数修正（提升平局预测能力）
2. 更稳健的攻击力/防守力计算（使用 Bayesian shrinkage）
3. Elo 概率融合（提升区分度）
"""

import numpy as np
import pandas as pd
from scipy.stats import poisson
from dataclasses import dataclass
from statistics import mean as _mean

from src.utils import logger


@dataclass
class PoissonPrediction:
    """泊松模型预测结果"""
    home_goals: float       # 预期主场进球
    away_goals: float       # 预期客场进球
    home_win_prob: float    # 主胜概率
    draw_prob: float        # 平局概率
    away_win_prob: float    # 客胜概率
    score_probs: dict       # {(h,a): prob} 比分概率


def _strength_with_shrinkage(
    team_avg: float,
    league_avg: float,
    n_matches: int,
    shrinkage_strength: float = 10.0,
) -> float:
    """
    Bayesian shrinkage: 将球队数据向联赛平均收缩
    
    球队比赛少时，数据不可靠，向联赛平均收缩。
    shrinkage_strength 越大，收缩越强（相当于先验的"虚拟比赛"数）。
    """
    return (team_avg * n_matches + league_avg * shrinkage_strength) / (n_matches + shrinkage_strength)


def calc_attack_defense_strength(
    df: pd.DataFrame,
    min_games: int = 3,
) -> tuple[dict, dict, dict[str, float], dict[str, float]]:
    """
    按联赛分别计算各球队的攻击力/防守力系数（带 Bayesian shrinkage）

    使用 shrinkage 防止比赛少的球队出现极端强度值。

    Returns:
        attack_strength:      {球队: 攻击力系数 (相对联赛平均)}
        defense_strength:     {球队: 防守力系数 (相对联赛平均)}
        avg_home_by_league:   {联赛: 场均主场进球}
        avg_away_by_league:   {联赛: 场均客场进球}
    """
    avg_home_by_league = df.groupby("league")["home_goals"].mean().to_dict()
    avg_away_by_league = df.groupby("league")["away_goals"].mean().to_dict()

    # 统计各球队的比赛场次（做 shrinkage 用）
    home_counts = df.groupby("home_team").size().to_dict()
    away_counts = df.groupby("away_team").size().to_dict()

    home_attack = {}
    home_defense = {}
    away_attack = {}
    away_defense = {}

    for league, group in df.groupby("league"):
        avg_h = avg_home_by_league.get(league, 1.5)
        avg_a = avg_away_by_league.get(league, 1.1)

        # 球队在联赛中的平均进球（用于 shrinkage 目标）
        for team, sub in group.groupby("home_team"):
            n = len(sub)
            if n < min_games:
                continue
            raw_attack = sub["home_goals"].mean() / avg_h if avg_h > 0 else 1.0
            home_attack[team] = _strength_with_shrinkage(raw_attack, 1.0, n)

            raw_defense = sub["away_goals"].mean() / avg_a if avg_a > 0 else 1.0
            home_defense[team] = _strength_with_shrinkage(raw_defense, 1.0, n)

        for team, sub in group.groupby("away_team"):
            n = len(sub)
            if n < min_games:
                continue
            raw_attack = sub["away_goals"].mean() / avg_a if avg_a > 0 else 1.0
            away_attack[team] = _strength_with_shrinkage(raw_attack, 1.0, n)

            raw_defense = sub["home_goals"].mean() / avg_h if avg_h > 0 else 1.0
            away_defense[team] = _strength_with_shrinkage(raw_defense, 1.0, n)

    # 合并主场/客场强度
    all_teams = set(home_attack.keys()) | set(away_attack.keys())
    attack_strength = {}
    defense_strength = {}

    for team in all_teams:
        ha = home_attack.get(team, 1.0)
        aa = away_attack.get(team, 1.0)
        n_home = home_counts.get(team, 0)
        n_away = away_counts.get(team, 0)
        total = n_home + n_away
        if total > 0:
            attack_strength[team] = (ha * n_home + aa * n_away) / total
        else:
            attack_strength[team] = (ha + aa) / 2

        hd = home_defense.get(team, 1.0)
        ad = away_defense.get(team, 1.0)
        if total > 0:
            defense_strength[team] = (hd * n_home + ad * n_away) / total
        else:
            defense_strength[team] = (hd + ad) / 2

    return attack_strength, defense_strength, avg_home_by_league, avg_away_by_league


def _elo_win_prob(rating_a: float, rating_b: float) -> float:
    """根据 Elo 评分差计算预期胜率（含平局因子）"""
    diff = np.clip((rating_b - rating_a) / 400.0, -10, 10)
    return 1.0 / (1.0 + 10.0 ** diff)


def _dc_correction(i: int, j: int, lam: float, mu: float, rho: float) -> float:
    """
    Dixon-Coles 低比分相关系数 tau
    
    修正独立泊松在低比分时的概率偏差。
    当 rho < 0 时，增加 0-0 概率，微调 0-1/1-0/1-1 概率。
    
    Reference: Dixon & Coles (1997), "Modelling Association Football Scores..."
    """
    if i == 0 and j == 0:
        return 1.0 - lam * mu * rho
    elif i == 0 and j == 1:
        return 1.0 + lam * rho
    elif i == 1 and j == 0:
        return 1.0 + mu * rho
    elif i == 1 and j == 1:
        return 1.0 + rho
    else:
        return 1.0


def predict_match_poisson(
    home_team: str,
    away_team: str,
    attack_strength: dict,
    defense_strength: dict,
    avg_home_by_league: dict[str, float],
    avg_away_by_league: dict[str, float],
    league: str | None = None,
    max_goals: int = 6,
    elo_home: float | None = None,
    elo_away: float | None = None,
    home_advantage: float = 0.06,
    rho: float = -0.13,
) -> PoissonPrediction:
    """
    使用泊松分布（Dixon-Coles 修正）预测单场比赛

    Args:
        home_advantage: 主场优势因子（0.06 = 约 6% 额外进球）
        rho: Dixon-Coles 低比分相关系数（负值 = 增加低比分平局概率）

    当提供 Elo 评分时，使用自适应融合权重提升预测精度。
    """
    if league and league in avg_home_by_league:
        avg_h = avg_home_by_league[league]
        avg_a = avg_away_by_league[league]
    else:
        avg_h = float(_mean(avg_home_by_league.values())) if avg_home_by_league else 1.5
        avg_a = float(_mean(avg_away_by_league.values())) if avg_away_by_league else 1.1

    # 预期进球
    lambda_home = (
        avg_h
        * attack_strength.get(home_team, 1.0)
        * defense_strength.get(away_team, 1.0)
        * (1.0 + home_advantage)
    )
    lambda_away = (
        avg_a
        * attack_strength.get(away_team, 1.0)
        * defense_strength.get(home_team, 1.0)
    )

    lambda_home = np.clip(lambda_home, 0.05, 6.0)
    lambda_away = np.clip(lambda_away, 0.05, 5.0)

    # ---- 泊松 + Dixon-Coles 比分概率矩阵 ----
    goal_range = np.arange(max_goals + 1)
    home_probs = poisson.pmf(goal_range, lambda_home)
    away_probs = poisson.pmf(goal_range, lambda_away)

    # 逐元素计算修正概率
    prob_matrix = np.zeros((max_goals + 1, max_goals + 1))
    for i in goal_range:
        for j in goal_range:
            tau = _dc_correction(int(i), int(j), lambda_home, lambda_away, rho)
            prob_matrix[i, j] = tau * home_probs[i] * away_probs[j]

    # 归一化（Dixon-Coles 修正后概率和不为 1）
    total_sum = prob_matrix.sum()
    if total_sum > 0:
        prob_matrix /= total_sum

    # 从概率矩阵计算胜平负
    where_hw = np.tril(prob_matrix, -1).sum()  # HOME win (i > j)
    where_d = np.trace(prob_matrix)            # DRAW (i == j)
    where_aw = np.triu(prob_matrix, 1).sum()   # AWAY win (j > i)

    # 比分概率
    score_probs = {}
    for i in goal_range:
        for j in goal_range:
            p = float(prob_matrix[i, j])
            if p > 0.002:
                score_probs[(int(i), int(j))] = p

    poisson_hw = where_hw
    poisson_d = where_d
    poisson_aw = where_aw

    # ---- 融合 Elo 概率 ----
    if elo_home is not None and elo_away is not None:
        elo_home_win = _elo_win_prob(elo_home, elo_away)
        elo_away_win = 1.0 - elo_home_win

        # 用泊松的平局概率做平局基线
        elo_draw = poisson_d

        total_elo = elo_home_win + elo_draw + elo_away_win
        elo_hw_norm = elo_home_win / total_elo
        elo_d_norm = elo_draw / total_elo
        elo_aw_norm = elo_away_win / total_elo

        # 自适应融合权重：
        # 当两队实力接近时（Elo差 < 100），泊松权重更高（依赖数据）
        # 当实力差大时，Elo 权重更高（捕捉长期趋势）
        elo_diff = abs(elo_home - elo_away)
        alpha = np.clip(0.5 + 0.1 * (elo_diff / 100), 0.45, 0.70)
        # alpha = 泊松权重, (1-alpha) = Elo 权重

        prob_hw = alpha * poisson_hw + (1 - alpha) * elo_hw_norm
        prob_d = alpha * poisson_d + (1 - alpha) * elo_d_norm
        prob_aw = alpha * poisson_aw + (1 - alpha) * elo_aw_norm

        total_prob = prob_hw + prob_d + prob_aw
        prob_hw /= total_prob
        prob_d /= total_prob
        prob_aw /= total_prob
    else:
        prob_hw = poisson_hw
        prob_d = poisson_d
        prob_aw = poisson_aw

    return PoissonPrediction(
        home_goals=round(lambda_home, 2),
        away_goals=round(lambda_away, 2),
        home_win_prob=round(prob_hw, 4),
        draw_prob=round(prob_d, 4),
        away_win_prob=round(prob_aw, 4),
        score_probs=dict(sorted(score_probs.items(), key=lambda x: -x[1])[:10]),
    )


def evaluate_poisson_model(
    df: pd.DataFrame,
    season_cutoff: str = "2324",
) -> dict:
    """评估泊松模型在历史数据上的表现（按联赛分别评估）"""
    train = df[df["season_code"] < season_cutoff].copy()
    test = df[df["season_code"] >= season_cutoff].copy()

    if len(train) < 50 or len(test) < 10:
        logger.warning("数据量不足，使用全部数据的 80% 做训练")
        split = int(len(df) * 0.8)
        train = df.iloc[:split].copy()
        test = df.iloc[split:].copy()

    logger.info(f"泊松模型: 训练 {len(train)} 场, 测试 {len(test)} 场")
    attack, defense, avg_h_by_league, avg_a_by_league = calc_attack_defense_strength(train)

    correct = 0
    total = 0
    home_win_correct = home_win_total = 0
    draw_correct = draw_total = 0
    away_win_correct = away_win_total = 0
    pred_counts = {}
    predictions = []

    for _, row in test.iterrows():
        pred = predict_match_poisson(
            row["home_team"], row["away_team"],
            attack, defense, avg_h_by_league, avg_a_by_league,
            league=row.get("league"),
            elo_home=row.get("elo_home"),
            elo_away=row.get("elo_away"),
        )
        actual_result = row["result"]
        predicted_result = (
            "H" if pred.home_win_prob > max(pred.draw_prob, pred.away_win_prob)
            else ("D" if pred.draw_prob > pred.away_win_prob else "A")
        )

        correct += (predicted_result == actual_result)
        total += 1
        pred_counts[predicted_result] = pred_counts.get(predicted_result, 0) + 1

        if actual_result == "H":
            home_win_total += 1
            home_win_correct += (predicted_result == "H")
        elif actual_result == "D":
            draw_total += 1
            draw_correct += (predicted_result == "D")
        else:
            away_win_total += 1
            away_win_correct += (predicted_result == "A")

        predictions.append({
            "home": row["home_team"],
            "away": row["away_team"],
            "actual": actual_result,
            "predicted": predicted_result,
            "home_win_prob": pred.home_win_prob,
            "draw_prob": pred.draw_prob,
            "away_win_prob": pred.away_win_prob,
            "lambda_home": round(pred.home_goals, 2),
            "lambda_away": round(pred.away_goals, 2),
        })

    accuracy = correct / total if total > 0 else 0
    home_acc = home_win_correct / home_win_total if home_win_total > 0 else 0
    draw_acc = draw_correct / draw_total if draw_total > 0 else 0
    away_acc = away_win_correct / away_win_total if away_win_total > 0 else 0

    results = {
        "total_matches": total,
        "accuracy": round(accuracy, 4),
        "home_win_accuracy": round(home_acc, 4),
        "draw_accuracy": round(draw_acc, 4),
        "away_win_accuracy": round(away_acc, 4),
        "prediction_distribution": pred_counts,
        "avg_lambda_home": round(np.mean([p["lambda_home"] for p in predictions]), 3),
        "avg_lambda_away": round(np.mean([p["lambda_away"] for p in predictions]), 3),
    }

    logger.info(
        f"泊松模型准确率: {accuracy:.2%} "
        f"(主胜={home_acc:.2%}, 平局={draw_acc:.2%}, 客胜={away_acc:.2%}) "
        f"预测分布: H={pred_counts.get('H',0)}, D={pred_counts.get('D',0)}, A={pred_counts.get('A',0)}"
    )
    return results
