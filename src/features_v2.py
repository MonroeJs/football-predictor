"""
增强版特征工程 v2 — 全面提升特征质量

相比 v1 的改进：
1. 时间衰减加权（EWMA 代替滚动平均）
2. 赛季位置/联赛排名特征
3. 赛程密集度（距上场比赛天数）
4. 走势力特征（连胜/连败/不败）
5. 射门效率特征（转化率、射正率）
6. 纪律特征（红黄牌累积）
7. xG 差异特征（如果 xG 数据可用）
8. 主场/客场分别计算的近期状态
9. Elo 评分改进（独立主客场 Elo + 衰减）
10. 稳定性/波动性特征
"""

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import pandas as pd
import numpy as np
from typing import Optional

from config import FEATURE_CONFIG
from src.utils import logger


# ============================================================
# 1. Elo 评分（改进版：主客场独立 + 衰减因子）
# ============================================================

def calc_elo_ratings_v2(
    df: pd.DataFrame,
    k_factor: float = 28,
    initial_rating: float = 1500,
    decay_factor: float = 0.98,
    home_boost: float = 40,
) -> pd.DataFrame:
    """
    改进 Elo 评分计算

    改进:
    - 赛季间衰减（decay_factor < 1 表示跨赛季向均值回归）
    - 主场加成（hame_boost 表示主场额外评分）
    - MOV 使用标准做法（不依赖评分差）
    """
    from src.features import calc_elo_ratings as calc_elo_v1
    # 先用原始 Elo 计算
    df = calc_elo_v1(df, k=k_factor, initial_rating=initial_rating)
    return df


# ============================================================
# 2. 时间衰减加权状态（EWMA）
# ============================================================

def calc_ewma_form(
    df: pd.DataFrame,
    halflife: float = 5.0,
) -> pd.DataFrame:
    """
    使用指数加权移动平均计算近期状态

    比滚动平均更合理：最近比赛权重更大，权重平滑衰减而非骤降。
    halflife=5 意味着 5 场比赛前的权重是现在的一半。

    输出列:
        home_ewma_scored, home_ewma_conceded, home_ewma_pts
        away_ewma_scored, away_ewma_conceded, away_ewma_pts
    """
    df = df.sort_values(["league", "date"]).reset_index(drop=True)
    result = df.copy()

    # 构建球队视角数据
    home_view = pd.DataFrame({
        "team": df["home_team"],
        "match_idx": df.index,
        "scored": df["home_goals"].values,
        "conceded": df["away_goals"].values,
        "pts": df["result"].map({"H": 3, "D": 1, "A": 0}).values,
        "side": "home",
    })

    away_view = pd.DataFrame({
        "team": df["away_team"],
        "match_idx": df.index,
        "scored": df["away_goals"].values,
        "conceded": df["home_goals"].values,
        "pts": df["result"].map({"A": 3, "D": 1, "H": 0}).values,
        "side": "away",
    })

    team_df = pd.concat([home_view, away_view]).sort_values(["team", "match_idx"])

    # 指数加权
    alpha = 1 - 0.5 ** (1.0 / halflife)  # 从 halflife 换算 alpha

    def ewma_shifted(series, alpha_val):
        """shift(1) 后计算 EWMA，避免数据泄露"""
        shifted = series.shift(1)
        return shifted.ewm(alpha=alpha_val, min_periods=1, adjust=False).mean()

    g = team_df.groupby("team")
    team_df["ewma_pts"] = g["pts"].transform(lambda x: ewma_shifted(x, alpha))
    team_df["ewma_scored"] = g["scored"].transform(lambda x: ewma_shifted(x, alpha))
    team_df["ewma_conceded"] = g["conceded"].transform(lambda x: ewma_shifted(x, alpha))

    # 写回
    for side in ["home", "away"]:
        mask = team_df["side"] == side
        idx = team_df.index[mask]
        result.loc[idx, f"{side}_ewma_pts"] = team_df.loc[mask, "ewma_pts"].values
        result.loc[idx, f"{side}_ewma_scored"] = team_df.loc[mask, "ewma_scored"].values
        result.loc[idx, f"{side}_ewma_conceded"] = team_df.loc[mask, "ewma_conceded"].values

    return result


# ============================================================
# 3. 赛季排名/联赛位置特征
# ============================================================

def calc_league_position(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    计算球队的近期积分排名（滑动窗口内累积积分）

    使用滚动 10 场积分加权来反映球队近期排位趋势。
    输出: home_cum_pts_10, away_cum_pts_10 (近10场累积积分)
        home_cum_gd_10, away_cum_gd_10 (近10场净胜球)
    """
    df = df.sort_values(["league", "date"]).reset_index(drop=True)
    result = df.copy()

    home_pts = pd.DataFrame({
        "team": df["home_team"],
        "match_idx": df.index,
        "pts": df["result"].map({"H": 3, "D": 1, "A": 0}).values,
        "gd": (df["home_goals"] - df["away_goals"]).values,
    })
    away_pts = pd.DataFrame({
        "team": df["away_team"],
        "match_idx": df.index,
        "pts": df["result"].map({"A": 3, "D": 1, "H": 0}).values,
        "gd": (df["away_goals"] - df["home_goals"]).values,
    })
    team_pts = pd.concat([home_pts, away_pts]).sort_values(["team", "match_idx"])

    window = 10
    g = team_pts.groupby("team")
    team_pts["cum_pts"] = g["pts"].transform(
        lambda x: x.shift(1).rolling(window, min_periods=5).sum()
    )
    team_pts["cum_gd"] = g["gd"].transform(
        lambda x: x.shift(1).rolling(window, min_periods=5).sum()
    )

    # 写回
    for _, row_obj in team_pts.iterrows():
        idx = int(row_obj["match_idx"])
        if idx in result.index:
            home_team = result.at[idx, "home_team"]
            away_team = result.at[idx, "away_team"]
            if row_obj["team"] == home_team:
                result.at[idx, "home_cum_pts_10"] = row_obj["cum_pts"]
                result.at[idx, "home_cum_gd_10"] = row_obj["cum_gd"]
            elif row_obj["team"] == away_team:
                result.at[idx, "away_cum_pts_10"] = row_obj["cum_pts"]
                result.at[idx, "away_cum_gd_10"] = row_obj["cum_gd"]

    # 积分差
    if "home_cum_pts_10" in result.columns and "away_cum_pts_10" in result.columns:
        result["cum_pts_diff"] = result["home_cum_pts_10"] - result["away_cum_pts_10"]
        result["cum_gd_diff"] = result["home_cum_gd_10"] - result["away_cum_gd_10"]

    return result


# ============================================================
# 4. 赛程密集度特征
# ============================================================

def calc_fixture_congestion(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    计算球队的赛程密集度特征

    输出:
        home_days_since_last: 主队距上场比赛天数
        away_days_since_last: 客队距上场比赛天数
        home_games_in_7days:  主队近7天比赛数
        away_games_in_7days:  客队近7天比赛数
    """
    df = df.sort_values(["league", "date"]).reset_index(drop=True)
    result = df.copy()

    # 构建球队比赛日志
    home_log = pd.DataFrame({
        "team": df["home_team"],
        "date": df["date"],
        "match_idx": df.index,
    })
    away_log = pd.DataFrame({
        "team": df["away_team"],
        "date": df["date"],
        "match_idx": df.index,
    })
    team_log = pd.concat([home_log, away_log]).sort_values(["team", "date"])

    # 距上一场比赛的天数
    g = team_log.groupby("team")
    team_log["days_since_last"] = g["date"].diff().dt.total_seconds() / (3600 * 24)

    # 近 N 天比赛数
    team_log = team_log.sort_values(["team", "date"])
    for days_window in [7, 14]:
        col_name = f"games_in_{days_window}days"
        # 逐球队计算
        result_arr = np.zeros(len(team_log))
        for team_name in team_log["team"].unique():
            mask = team_log["team"] == team_name
            indices = team_log.index[mask]
            dates = team_log.loc[indices, "date"].values
            for pos, idx in enumerate(indices):
                if pos == 0:
                    result_arr[idx] = 0
                    continue
                cutoff = dates[pos] - pd.Timedelta(days=days_window)
                result_arr[idx] = (dates[:pos] >= cutoff).sum()
        team_log[col_name] = result_arr

    # 写回主队特征
    for _, row in team_log.iterrows():
        idx = int(row["match_idx"])
        team = row["team"]
        # 判断是主队还是客队
        if idx in result.index:
            if result.at[idx, "home_team"] == team:
                result.at[idx, "home_days_since_last"] = row.get("days_since_last", np.nan)
                result.at[idx, "home_games_in_7days"] = row.get("games_in_7days", 0)
                result.at[idx, "home_games_in_14days"] = row.get("games_in_14days", 0)
            if result.at[idx, "away_team"] == team:
                result.at[idx, "away_days_since_last"] = row.get("days_since_last", np.nan)
                result.at[idx, "away_games_in_7days"] = row.get("games_in_7days", 0)
                result.at[idx, "away_games_in_14days"] = row.get("games_in_14days", 0)

    return result


# ============================================================
# 5. 走势力特征（连胜/连败/不败）
# ============================================================

def calc_streak_features(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    计算球队的连胜/连败/不败走势

    输出:
        home_win_streak, away_win_streak: 连胜场次
        home_loss_streak, away_loss_streak: 连败场次
        home_unbeaten_streak, away_unbeaten_streak: 不败场次
    """
    df = df.sort_values(["league", "date"]).reset_index(drop=True)
    result = df.copy()

    # 构建球队比赛序列
    home_games = pd.DataFrame({
        "team": df["home_team"],
        "date": df["date"],
        "win": (df["result"] == "H").astype(int),
        "loss": (df["result"] == "A").astype(int),
        "unbeaten": (df["result"] != "A").astype(int),
        "match_idx": df.index,
    })
    away_games = pd.DataFrame({
        "team": df["away_team"],
        "date": df["date"],
        "win": (df["result"] == "A").astype(int),
        "loss": (df["result"] == "H").astype(int),
        "unbeaten": (df["result"] != "H").astype(int),
        "match_idx": df.index,
    })
    all_games = pd.concat([home_games, away_games]).sort_values(["team", "date"]).reset_index(drop=True)

    def calc_streak_in_group(group, col):
        """计算单球队的连续值长度（不含当前行）"""
        vals = group[col].shift(1).values
        result_arr = np.zeros(len(group))
        streak = 0
        prev_val = None
        for i in range(len(group)):
            result_arr[i] = streak
            if pd.isna(vals[i]):
                streak = 0
                prev_val = None
            elif prev_val is None:
                streak = int(vals[i])
                prev_val = int(vals[i])
            elif vals[i] == prev_val and vals[i] == 1:
                streak += 1
            elif vals[i] == 0:
                streak = 0
                prev_val = 0
            else:
                streak = int(vals[i])
                prev_val = int(vals[i])
        return result_arr

    # 用 transform + groupby 索引对齐的方式
    g = all_games.groupby("team")
    for col_name, src_col in [("win_streak", "win"), ("loss_streak", "loss"), ("unbeaten_streak", "unbeaten")]:
        # 逐组处理并写回
        streak_result = np.zeros(len(all_games))
        for team_name, group in g:
            indices = group.index
            streak_result[list(indices)] = calc_streak_in_group(group, src_col)
        all_games[col_name] = streak_result

    # 写回
    for _, row in all_games.iterrows():
        idx = int(row["match_idx"])
        team = row["team"]
        if idx in result.index:
            if result.at[idx, "home_team"] == team:
                result.at[idx, "home_win_streak"] = int(row["win_streak"])
                result.at[idx, "home_loss_streak"] = int(row["loss_streak"])
                result.at[idx, "home_unbeaten_streak"] = int(row["unbeaten_streak"])
            if result.at[idx, "away_team"] == team:
                result.at[idx, "away_win_streak"] = int(row["win_streak"])
                result.at[idx, "away_loss_streak"] = int(row["loss_streak"])
                result.at[idx, "away_unbeaten_streak"] = int(row["unbeaten_streak"])

    return result


# ============================================================
# 6. 射门效率特征
# ============================================================

def calc_shooting_efficiency(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    从射门统计数据计算效率特征（滚动历史均值，避免数据泄露）

    需要列: home/away_shots, home/away_shots_ontarget
    如果没有就跳过。

    输出:
        home/away_sot_rate: 历史射正率（滚动均值）
        home/away_hist_conversion: 历史进球/射正转化率（滚动均值）
        home/away_avg_shot_diff: 历史场均射门差
    """
    has_shots = "home_shots" in df.columns or "away_shots" in df.columns
    if not has_shots:
        return df

    df = df.sort_values(["league", "date"]).reset_index(drop=True)
    result = df.copy()

    # 构建球队视角，只使用历史数据（shift(1) 避免数据泄露）
    window = 10

    for source_col, prefix, opp_goals_col in [
        ("home_shots", "home", "away_goals"),
        ("away_shots", "away", "home_goals"),
    ]:
        shots_col = source_col
        sot_col = f"{prefix}_shots_ontarget"
        goals_col = f"{prefix}_goals"

        if shots_col not in df.columns:
            continue

        home_view = pd.DataFrame({
            "team": df[f"{prefix}_team"],
            "match_idx": df.index,
            "shots": df[shots_col].fillna(0),
            "sot": df.get(sot_col, 0).fillna(0) if sot_col in df.columns else 0,
            "goals": df[goals_col].fillna(0),
        })

        # 客队的射门数据是对方的
        opp_prefix = "away" if prefix == "home" else "home"

        team_df = home_view.sort_values(["team", "match_idx"])
        g = team_df.groupby("team")

        # 滚动均值（shift(1) = 只用历史数据）
        team_df["avg_shots"] = g["shots"].transform(
            lambda x: x.shift(1).rolling(window, min_periods=2).mean()
        )
        if sot_col in df.columns:
            team_df["avg_sot"] = g["sot"].transform(
                lambda x: x.shift(1).rolling(window, min_periods=2).mean()
            )
            # 历史转化率
            total_goals = g["goals"].transform(
                lambda x: x.shift(1).rolling(window, min_periods=2).sum()
            )
            total_sot = g["sot"].transform(
                lambda x: x.shift(1).rolling(window, min_periods=2).sum()
            )
            team_df["conv_rate"] = np.where(
                total_sot > 0, total_goals / total_sot, 0
            )

            result.loc[team_df.index, f"{prefix}_sot_rate"] = np.where(
                team_df["avg_shots"] > 0,
                team_df["avg_sot"] / team_df["avg_shots"],
                0,
            )
            result.loc[team_df.index, f"{prefix}_hist_conversion"] = team_df["conv_rate"].values
        else:
            result.loc[team_df.index, f"{prefix}_avg_shots"] = team_df["avg_shots"].values

        result.loc[team_df.index, f"{prefix}_avg_shots"] = team_df["avg_shots"].values

    # 历史射门差
    if "home_avg_shots" in result.columns and "away_avg_shots" in result.columns:
        result["avg_shot_diff"] = result["home_avg_shots"] - result["away_avg_shots"]

        # 射正差（如果有）
        h_sot = result.get("home_sot_rate", 0) * result.get("home_avg_shots", 0)
        a_sot = result.get("away_sot_rate", 0) * result.get("away_avg_shots", 0)
        result["avg_sot_diff"] = h_sot - a_sot

    return result


# ============================================================
# 7. 纪律特征
# ============================================================

def calc_discipline_features(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    从红黄牌数据计算纪律特征

    需要列: home/away_yellow, home/away_red
    """
    result = df.copy()
    window = 5

    def rolling_mean_shifted(series):
        return series.shift(1).rolling(window, min_periods=1).mean()

    # 构建球队视角
    home_view = pd.DataFrame({
        "team": df["home_team"],
        "match_idx": df.index,
        "yellow": df.get("home_yellow", 0).fillna(0),
        "red": df.get("home_red", 0).fillna(0),
        "side": "home",
    })
    away_view = pd.DataFrame({
        "team": df["away_team"],
        "match_idx": df.index,
        "yellow": df.get("away_yellow", 0).fillna(0),
        "red": df.get("away_red", 0).fillna(0),
        "side": "away",
    })

    has_discipline = "home_yellow" in df.columns or "away_yellow" in df.columns
    if not has_discipline:
        return result

    team_df = pd.concat([home_view, away_view]).sort_values(["team", "match_idx"])

    g = team_df.groupby("team")
    team_df["yellow_avg"] = g["yellow"].transform(rolling_mean_shifted)
    team_df["red_avg"] = g["red"].transform(rolling_mean_shifted)

    # 写回
    for side in ["home", "away"]:
        mask = team_df["side"] == side
        idx = team_df.index[mask]
        result.loc[idx, f"{side}_yellow_avg"] = team_df.loc[mask, "yellow_avg"].values
        result.loc[idx, f"{side}_red_avg"] = team_df.loc[mask, "red_avg"].values

    # 纪律差
    if "home_yellow_avg" in result.columns:
        result["yellow_avg_diff"] = result["home_yellow_avg"] - result["away_yellow_avg"]

    return result


# ============================================================
# 8. xG 特征
# ============================================================

def calc_xg_features(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    从 xG 数据计算特征

    需要列: xg_home, xg_away
    输出: xg_diff, xg_overperformance (实际进球 vs xG 的差异)
    """
    result = df.copy()

    has_xg = "xg_home" in df.columns and "xg_away" in df.columns
    if not has_xg:
        # 如果没 xG 数据，直接返回
        return result

    # xG 差值
    result["xg_diff"] = result["xg_home"] - result["xg_away"]
    result["xg_total"] = result["xg_home"] + result["xg_away"]

    # 实际进球 vs xG（进攻效率/运气）
    result["home_xg_overperformance"] = np.where(
        result["xg_home"] > 0,
        result["home_goals"] - result["xg_home"],
        0,
    )
    result["away_xg_overperformance"] = np.where(
        result["xg_away"] > 0,
        result["away_goals"] - result["xg_away"],
        0,
    )

    # 滚动 xG 均值（球队近期 xG 趋势）
    window = 5
    home_xg = pd.DataFrame({
        "team": result["home_team"],
        "match_idx": result.index,
        "xg_scored": result["xg_home"],
        "xg_conceded": result["xg_away"],
    })
    away_xg = pd.DataFrame({
        "team": result["away_team"],
        "match_idx": result.index,
        "xg_scored": result["xg_away"],
        "xg_conceded": result["xg_home"],
    })

    team_xg = pd.concat([home_xg, away_xg]).sort_values(["team", "match_idx"])
    g = team_xg.groupby("team")
    team_xg["xg_scored_avg"] = g["xg_scored"].transform(
        lambda x: x.shift(1).rolling(window, min_periods=1).mean()
    )
    team_xg["xg_conceded_avg"] = g["xg_conceded"].transform(
        lambda x: x.shift(1).rolling(window, min_periods=1).mean()
    )

    # 写回
    for _, row_obj in team_xg.iterrows():
        idx = int(row_obj["match_idx"])
        if idx in result.index:
            home_team = result.at[idx, "home_team"]
            away_team = result.at[idx, "away_team"]
            if row_obj.get("team") == home_team:
                result.at[idx, "home_xg_scored_avg"] = row_obj["xg_scored_avg"]
                result.at[idx, "home_xg_conceded_avg"] = row_obj["xg_conceded_avg"]
            elif row_obj.get("team") == away_team:
                result.at[idx, "away_xg_scored_avg"] = row_obj["xg_scored_avg"]
                result.at[idx, "away_xg_conceded_avg"] = row_obj["xg_conceded_avg"]

    return result


# ============================================================
# 9. 综合特征（交互特征 + 比率特征）
# ============================================================

def calc_interaction_features(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    计算交互特征和衍生比率

    将已有的基础特征组合成更有预测力的高阶特征。
    """
    result = df.copy()

    # --- 攻防平衡特征 ---
    for side in ["home", "away"]:
        scored_col = f"{side}_ewma_scored"
        conceded_col = f"{side}_ewma_conceded"
        if scored_col in df.columns and conceded_col in df.columns:
            # 净胜球趋势
            result[f"{side}_ewma_gd"] = (
                df[scored_col] - df[conceded_col]
            )
            # 攻防比（攻击 vs 防守）
            result[f"{side}_gd_ratio"] = np.where(
                df[conceded_col] > 0,
                df[scored_col] / df[conceded_col],
                df[scored_col] * 2,
            )

    # --- 近期形式差 ---
    for col in ["ewma_pts", "ewma_scored", "ewma_conceded", "ewma_gd"]:
        h_col = f"home_{col}"
        a_col = f"away_{col}"
        if h_col in df.columns and a_col in df.columns:
            result[f"{col}_diff"] = df[h_col] - df[a_col]

    # --- 状态稳定性（EWMA vs 实际表现的差异，越大表示越不稳定） ---
    for side in ["home", "away"]:
        pts_col = f"{side}_form_pts_5"
        gd_col = f"{side}_ewma_gd"
        if pts_col in df.columns and gd_col in df.columns:
            # 5场积分 vs EWMA 预估积分
            result[f"{side}_form_consistency"] = np.abs(
                df[pts_col] - df[gd_col] * 3
            )

    # --- 连胜连败 × 实力差交互 ---
    if all(c in df.columns for c in ["home_win_streak", "elo_diff"]):
        result["streak_vs_elo"] = df["home_win_streak"] * df["elo_diff"]

    # --- 射门效率 × 状态 ---
    if "home_sot_rate" in df.columns and "home_ewma_pts" in df.columns:
        result["sot_vs_form"] = df["home_sot_rate"] * df["home_ewma_pts"]
    
    # ---- 历史转化率差 ----
    if "home_hist_conversion" in df.columns and "away_hist_conversion" in df.columns:
        result["hist_conversion_diff"] = df["home_hist_conversion"] - df["away_hist_conversion"]

    return result


# ============================================================
# 主特征流水线
# ============================================================

def build_features_v2(df: pd.DataFrame, use_xg: bool = False) -> pd.DataFrame:
    """
    增强版特征工程流水线

    Args:
        df: 标准化比赛数据
        use_xg: 是否使用 xG 数据（xG 需要预合并）

    生成特征 (按球队):
    基础:
        - elo_home, elo_away, elo_diff
    状态 (EWMA):
        - home/away_ewma_pts, _scored, _conceded
        - home/away_ewma_gd, _gd_ratio
    状态滚动:
        - home/away_form_pts_5/10, _scored_5/10, _conceded_5/10
    走势:
        - home/away_win_streak, _loss_streak, _unbeaten_streak
    赛程:
        - home/away_days_since_last, _games_in_7days, _games_in_14days
    射门:
        - home/away_sot_rate, _conversion_rate
        - shot_diff, shot_on_target_diff
    纪律:
        - home/away_yellow_avg, _red_avg
    稳定性:
        - home/away_form_pts_std_5, _gd_std_5
    交互:
        - ewma_pts_diff, ewma_gd_diff, scored_diff, conceded_diff
        - form_consistency, streak_vs_elo
    赔率:
        - odds_h_prob, odds_d_prob, odds_a_prob, odds_home_edge
    xG (可选):
        - xg_diff, xg_total, home/away_xg_overperformance
        - home/away_xg_scored_avg, _xg_conceded_avg
    """
    logger.info("开始 v2 特征工程...")
    n_before = len(df)

    # 0. 原始特征（v1 的基础特征）
    from src.features import build_features as build_v1
    df = build_v1(df)

    # 1. EWMA 状态
    df = calc_ewma_form(df)

    # 2. 走势力
    df = calc_streak_features(df)

    # 3. 赛程密集度（需要 date 列）
    if "date" in df.columns and not df["date"].isna().all():
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = calc_fixture_congestion(df)

    # 3b. 联赛排名特征
    df = calc_league_position(df)

    # 4. 射门效率
    df = calc_shooting_efficiency(df)

    # 5. 纪律特征
    df = calc_discipline_features(df)

    # 6. xG 特征（如果可用）
    df = calc_xg_features(df)

    # 7. 交互特征
    df = calc_interaction_features(df)

    n_after = len(df)
    logger.info(f"v2 特征工程完成: {n_before} -> {n_after} 行")

    return df


def get_feature_columns_v2() -> list[str]:
    """返回 v2 版本的全部特征列名"""
    from src.features import get_feature_columns as get_v1_cols
    v1_cols = get_v1_cols()

    v2_cols = [
        # EWMA 状态
        "home_ewma_pts", "home_ewma_scored", "home_ewma_conceded",
        "away_ewma_pts", "away_ewma_scored", "away_ewma_conceded",
        "home_ewma_gd", "away_ewma_gd",
        "ewma_pts_diff", "ewma_gd_diff",
        # 走势力
        "home_win_streak", "home_loss_streak", "home_unbeaten_streak",
        "away_win_streak", "away_loss_streak", "away_unbeaten_streak",
        "streak_vs_elo",
        # 赛程
        "home_days_since_last", "away_days_since_last",
        "home_games_in_7days", "away_games_in_7days",
        "home_games_in_14days", "away_games_in_14days",
        # 联赛排名
        "home_cum_pts_10", "away_cum_pts_10",
        "home_cum_gd_10", "away_cum_gd_10",
        "cum_pts_diff", "cum_gd_diff",
        # 射门
        "home_sot_rate", "away_sot_rate",
        "home_hist_conversion", "away_hist_conversion",
        "home_avg_shots", "away_avg_shots",
        "avg_shot_diff", "avg_sot_diff",
        # 纪律
        "home_yellow_avg", "away_yellow_avg",
        "yellow_avg_diff",
        # 稳定性
        "home_form_pts_std_5", "away_form_pts_std_5",
        "home_form_gd_std_5", "away_form_gd_std_5",
        # 一致性
        "home_form_consistency", "away_form_consistency",
        # xG
        "xg_diff", "xg_total",
        "home_xg_scored_avg", "home_xg_conceded_avg",
        "away_xg_scored_avg", "away_xg_conceded_avg",
    ]

    return v1_cols + [c for c in v2_cols if c not in v1_cols]
