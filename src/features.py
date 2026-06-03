"""
特征工程 — 从历史比赛数据生成预测特征
"""

import pandas as pd
import numpy as np
from typing import Optional

from config import FEATURE_CONFIG
from src.utils import logger


def calc_elo_ratings(df: pd.DataFrame, k: int = 32, initial_rating: float = 1500) -> pd.DataFrame:
    """
    计算球队 Elo 评分

    按时间顺序迭代比赛，更新每支球队的 Elo 评分。
    返回带 elo_home / elo_away 列的 DataFrame。
    """
    df = df.sort_values("date").reset_index(drop=True)
    ratings: dict[str, float] = {}
    elo_home_list = []
    elo_away_list = []

    def expected_score(r_a: float, r_b: float) -> float:
        # 限制差值防止溢出
        diff = np.clip((r_b - r_a) / 400.0, -10, 10)
        return 1.0 / (1.0 + 10.0 ** diff)

    for _, row in df.iterrows():
        home = row["home_team"]
        away = row["away_team"]

        r_home = ratings.get(home, initial_rating)
        r_away = ratings.get(away, initial_rating)

        elo_home_list.append(r_home)
        elo_away_list.append(r_away)

        # 比赛结果
        home_goals = row["home_goals"]
        away_goals = row["away_goals"]

        if home_goals > away_goals:
            s_home, s_away = 1.0, 0.0
        elif home_goals < away_goals:
            s_home, s_away = 0.0, 1.0
        else:
            s_home, s_away = 0.5, 0.5

        e_home = expected_score(r_home, r_away)
        e_away = 1.0 - e_home

        # 考虑净胜球的目标差异因子
        # 标准做法：净胜球越大，K 因子增幅越大，但不依赖评分差
        goal_diff = abs(home_goals - away_goals)
        mov = 1.0 + (goal_diff - 1) * 0.1  # 每多1球多10%权重
        mov = max(mov, 1.0)

        ratings[home] = r_home + k * mov * (s_home - e_home)
        ratings[away] = r_away + k * mov * (s_away - e_away)

    df = df.copy()
    df["elo_home"] = elo_home_list
    df["elo_away"] = elo_away_list
    return df


def calc_recent_form(
    df: pd.DataFrame,
    n_games: int = 5,
) -> pd.DataFrame:
    """
    向量化计算近期状态特征

    思路: 将每场比赛拆成主队视角和客队视角两行,
    按球队 groupby + shift + rolling 向量化计算,
    再写回原 DataFrame.
    """
    import warnings
    warnings.filterwarnings("ignore", category=FutureWarning)

    df = df.sort_values(["league", "date"]).reset_index(drop=True)
    result = df.copy()
    prefix = f"_{n_games}"

    # 构建"球队视角"数据: 每场比赛变两行 (主队视角, 客队视角)
    home_view = pd.DataFrame({
        "team": df["home_team"],
        "date": df["date"],
        "scored": df["home_goals"].values,
        "conceded": df["away_goals"].values,
        "pts": df["result"].map({"H": 3, "D": 1, "A": 0}).values,
        "side": "home",
    }, index=df.index)

    away_view = pd.DataFrame({
        "team": df["away_team"],
        "date": df["date"],
        "scored": df["away_goals"].values,
        "conceded": df["home_goals"].values,
        "pts": df["result"].map({"A": 3, "D": 1, "H": 0}).values,
        "side": "away",
    }, index=df.index)

    team_df = pd.concat([home_view, away_view]).sort_values(["team", "date"])

    # 按球队分组, shift(1) 排除当前场次, rolling 计算
    g = team_df.groupby("team")
    team_df["roll_pts"] = g["pts"].transform(
        lambda x: x.shift(1).rolling(n_games, min_periods=1).sum()
    )
    team_df["roll_scored"] = g["scored"].transform(
        lambda x: x.shift(1).rolling(n_games, min_periods=1).mean()
    )
    team_df["roll_conceded"] = g["conceded"].transform(
        lambda x: x.shift(1).rolling(n_games, min_periods=1).mean()
    )

    # 写回结果
    for side, prefix_col in [("home", "home"), ("away", "away")]:
        mask = team_df["side"] == side
        idx = team_df.index[mask]
        result.loc[idx, f"{prefix_col}_form_pts{prefix}"] = team_df.loc[mask, "roll_pts"].values
        result.loc[idx, f"{prefix_col}_form_scored{prefix}"] = team_df.loc[mask, "roll_scored"].values
        result.loc[idx, f"{prefix_col}_form_conceded{prefix}"] = team_df.loc[mask, "roll_conceded"].values

    return result


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    完整特征工程流水线

    生成特征:
    1. Elo 评分
    2. 近期状态 (近5场、近10场)
    3. 攻击力/防守力指数
    4. 博彩赔率隐含概率
    5. 状态稳定性（波动性）
    6. 衍生特征
    """
    logger.info("开始特征工程...")
    n_before = len(df)

    # 1. Elo 评分
    df = calc_elo_ratings(df)
    df["elo_diff"] = df["elo_home"] - df["elo_away"]

    # 2. 近期状态
    for n in FEATURE_CONFIG["recent_games"]:
        df = calc_recent_form(df, n_games=n)

    # 3. 状态稳定性特征
    for n in FEATURE_CONFIG["recent_games"]:
        df = calc_form_consistency(df, n_games=n)

    # 4. 博彩赔率特征
    df = calc_odds_features(df)

    # 5. 攻击力/防守力指数
    df["home_attack_power"] = df["home_form_scored_5"] / (
        df["away_form_conceded_5"].replace(0, np.nan)
    )
    df["away_attack_power"] = df["away_form_scored_5"] / (
        df["home_form_conceded_5"].replace(0, np.nan)
    )

    # 6. 综合特征
    if "home_form_pts_5" in df.columns and "away_form_pts_5" in df.columns:
        df["form_pts_diff"] = df["home_form_pts_5"] - df["away_form_pts_5"]

    if "home_form_scored_5" in df.columns and "away_form_scored_5" in df.columns:
        df["scored_diff"] = df["home_form_scored_5"] - df["away_form_scored_5"]
        df["conceded_diff"] = df["home_form_conceded_5"] - df["away_form_conceded_5"]

    # 过滤特征不足的行
    min_matches = FEATURE_CONFIG["min_matches_for_features"]
    df = df.dropna(subset=["elo_diff", "home_form_pts_5", "away_form_pts_5"], how="any")

    n_after = len(df)
    logger.info(f"特征工程完成: {n_before} → {n_after} 行 (滤除 {n_before - n_after} 行)")

    return df


def calc_odds_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    从博彩赔率计算隐含概率特征

    将赔率转化为隐含概率，并计算市场隐含的胜率差、odd movement 等特征。
    """
    from config import ODDS_COLUMNS

    df = df.copy()

    def implied_prob(odds):
        """赔率 → 隐含概率 (含去边际化)"""
        if pd.isna(odds) or odds <= 1:
            return None
        return 1.0 / odds

    # 1. 使用 Avg 赔率（多家博彩公司平均）计算隐含概率
    close_cols = ODDS_COLUMNS.get("close", [])

    # 从不同博彩公司取赔率，优先 Avg，次选 B365，再次 WH
    h_col = "AvgH" if "AvgH" in df.columns else ("B365H" if "B365H" in df.columns else None)
    d_col = "AvgD" if "AvgD" in df.columns else ("B365D" if "B365D" in df.columns else None)
    a_col = "AvgA" if "AvgA" in df.columns else ("B365A" if "B365A" in df.columns else None)

    if h_col and d_col and a_col and h_col in df.columns:
        # 赔率 → 隐含概率
        df["odds_h_prob"] = df[h_col].apply(implied_prob)
        df["odds_d_prob"] = df[d_col].apply(implied_prob)
        df["odds_a_prob"] = df[a_col].apply(implied_prob)

        # 去边际化（归一化）
        total = df["odds_h_prob"] + df["odds_d_prob"] + df["odds_a_prob"]
        df["odds_h_prob"] = df["odds_h_prob"] / total
        df["odds_d_prob"] = df["odds_d_prob"] / total
        df["odds_a_prob"] = df["odds_a_prob"] / total

        # 市场隐含优势差
        df["odds_home_edge"] = df["odds_h_prob"] - df["odds_a_prob"]
        df["odds_draw_edge"] = df["odds_d_prob"]

    # 2. 计算开盘→收盘的赔率变化（如果有开盘赔率）
    open_cols = ODDS_COLUMNS.get("open", [])
    if "AvgCH" in df.columns and "AvgH" in df.columns:
        df["odds_movement_h"] = df["AvgH"] - df["AvgCH"]
        df["odds_movement_d"] = df["AvgD"] - df["AvgCD"]
        df["odds_movement_a"] = df["AvgA"] - df["AvgCA"]
    elif "B365CH" in df.columns and "B365H" in df.columns:
        df["odds_movement_h"] = df["B365H"] - df["B365CH"]
        df["odds_movement_d"] = df["B365D"] - df["B365CD"]
        df["odds_movement_a"] = df["B365A"] - df["B365CA"]

    # 3. 隐含总进球（从大小球赔率）
    if "B365>2.5" in df.columns:
        over = df["B365>2.5"].apply(implied_prob)
        under = df["B365<2.5"].apply(implied_prob)
        total_prob = over + under
        df["odds_over_prob"] = over / total_prob

    return df


def calc_form_consistency(df: pd.DataFrame, n_games: int = 5) -> pd.DataFrame:
    """
    计算近期状态的稳定性/波动性特征
    使用滚动标准差来衡量球队表现的稳定性
    """
    import warnings
    warnings.filterwarnings("ignore", category=FutureWarning)

    df = df.sort_values(["league", "date"]).reset_index(drop=True)
    result = df.copy()
    prefix = f"_{n_games}"

    # 构建球队视角数据
    home_view = pd.DataFrame({
        "team": df["home_team"],
        "date": df["date"],
        "pts": df["result"].map({"H": 3, "D": 1, "A": 0}).values,
        "gd": (df["home_goals"] - df["away_goals"]).values,
        "scored": df["home_goals"].values,
        "conceded": df["away_goals"].values,
        "side": "home",
    }, index=df.index)

    away_view = pd.DataFrame({
        "team": df["away_team"],
        "date": df["date"],
        "pts": df["result"].map({"A": 3, "D": 1, "H": 0}).values,
        "gd": (df["away_goals"] - df["home_goals"]).values,
        "scored": df["away_goals"].values,
        "conceded": df["home_goals"].values,
        "side": "away",
    }, index=df.index)

    team_df = pd.concat([home_view, away_view]).sort_values(["team", "date"])

    # 滚动标准差（表现波动性）
    g = team_df.groupby("team")
    team_df["roll_pts_std"] = g["pts"].transform(
        lambda x: x.shift(1).rolling(n_games, min_periods=2).std()
    )
    team_df["roll_gd_std"] = g["gd"].transform(
        lambda x: x.shift(1).rolling(n_games, min_periods=2).std()
    )
    team_df["roll_scored_std"] = g["scored"].transform(
        lambda x: x.shift(1).rolling(n_games, min_periods=2).std()
    )

    # 写回
    for side in ["home", "away"]:
        mask = team_df["side"] == side
        idx = team_df.index[mask]
        result.loc[idx, f"{side}_form_pts_std{prefix}"] = team_df.loc[mask, "roll_pts_std"].values
        result.loc[idx, f"{side}_form_gd_std{prefix}"] = team_df.loc[mask, "roll_gd_std"].values
        result.loc[idx, f"{side}_form_scored_std{prefix}"] = team_df.loc[mask, "roll_scored_std"].values

    return result


def get_feature_columns() -> list[str]:
    """返回用于 ML 的特征列名"""
    base = [
        "elo_home", "elo_away", "elo_diff",
        "home_form_pts_5", "home_form_scored_5", "home_form_conceded_5",
        "away_form_pts_5", "away_form_scored_5", "away_form_conceded_5",
        "home_attack_power", "away_attack_power",
        "form_pts_diff", "scored_diff", "conceded_diff",
        "home_form_pts_std_5", "away_form_pts_std_5",
        "home_form_scored_std_5", "away_form_scored_std_5",
    ]
    # 赔率特征（如果有的话）
    odds_feats = [
        "odds_h_prob", "odds_d_prob", "odds_a_prob",
        "odds_home_edge", "odds_draw_edge",
    ]
    return base + odds_feats
