"""
数据加载模块 — 从 football-data.co.uk 下载、本地 CSV 读取、合成数据生成
"""

import pandas as pd
import numpy as np
import requests
from pathlib import Path
from io import StringIO
from datetime import datetime

from config import LEAGUES, RAW_DIR, FD_URL_TEMPLATE, SEASON_CODES, ODDS_COLUMNS
from src.utils import logger, parse_date


def download_league_data(
    league_key: str,
    season_codes: list[str] | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """
    从 football-data.co.uk 下载指定联赛的历史数据

    Args:
        league_key: 联赛键名 (EPL, LaLiga, SerieA, Bundesliga, Ligue1)
        season_codes: 赛季代码列表，如 ['2425', '2324']
        force: 是否强制重新下载

    Returns:
        合并后的 DataFrame
    """
    if league_key not in LEAGUES:
        raise ValueError(f"未知联赛: {league_key}，可选: {list(LEAGUES.keys())}")

    code = LEAGUES[league_key]["code"]
    season_codes = season_codes or SEASON_CODES

    all_dfs = []
    for season in season_codes:
        local_path = RAW_DIR / f"{league_key}_{season}.csv"

        if local_path.exists() and not force:
            logger.info(f"  读取本地缓存: {local_path.name}")
            df = pd.read_csv(local_path)
        else:
            url = FD_URL_TEMPLATE.format(season=season, code=code)
            logger.info(f"  下载 {league_key} {season}: {url}")
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                # 足彩数据不同赛季列数不一样，只读我们需要的核心列
                df = pd.read_csv(StringIO(resp.text), on_bad_lines='skip')
                # 保留核心列 + 博彩赔率列
                core_cols = ['Div','Date','Time','HomeTeam','AwayTeam',
                             'FTHG','FTAG','FTR',
                             'HTHG','HTAG','HTR',
                             'HS','AS','HST','AST','HC','AC',
                             'HF','AF','HY','AY','HR','AR']
                # 收集所有赔率列
                odds_cols = []
                for cat in ['close', 'open']:
                    for col in ODDS_COLUMNS.get(cat, []):
                        if col in df.columns:
                            odds_cols.append(col)
                keep = [c for c in core_cols if c in df.columns] + odds_cols
                df = df[keep]
                df.to_csv(local_path, index=False)
                logger.info(f"    已保存到 {local_path.name} ({len(df)} 行)")
            except requests.RequestException as e:
                logger.warning(f"    下载失败: {e}")
                continue

        if not df.empty:
            df["league"] = league_key
            df["season_code"] = season
            all_dfs.append(df)

    if not all_dfs:
        logger.warning(f"{league_key}: 未下载到任何数据")
        return pd.DataFrame()

    result = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"{league_key}: 共 {len(result)} 条记录")
    return result


def download_all_leagues(
    season_codes: list[str] | None = None,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """下载全部五大联赛数据"""
    result = {}
    for key in LEAGUES:
        logger.info(f"--- 下载 {key} ({LEAGUES[key]['name']}) ---")
        result[key] = download_league_data(key, season_codes, force)
    return result


def standardize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    标准化 football-data.co.uk 数据格式

    输入列: Div, Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR, ...
    输出列: league, date, home_team, away_team, home_goals, away_goals, result
    """
    required = ["HomeTeam", "AwayTeam", "FTHG", "FTAG"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"缺少必要列: {col}，可用列: {list(df.columns)}")

    std = pd.DataFrame()
    std["league"] = df.get("league", "Unknown")
    std["season_code"] = df.get("season_code", "")
    std["division"] = df.get("Div", "")
    std["date_raw"] = df.get("Date", "")
    std["home_team"] = df["HomeTeam"].astype(str).str.strip()
    std["away_team"] = df["AwayTeam"].astype(str).str.strip()
    std["home_goals"] = pd.to_numeric(df["FTHG"], errors="coerce")
    std["away_goals"] = pd.to_numeric(df["FTAG"], errors="coerce")

    # 解析日期
    dates = df["Date"].astype(str).apply(parse_date)
    std["date"] = dates
    std["date_parsed"] = dates.notna()

    # 结果
    if "FTR" in df.columns:
        std["result"] = df["FTR"]
    else:
        std["result"] = std.apply(
            lambda r: "H" if r["home_goals"] > r["away_goals"]
            else ("A" if r["home_goals"] < r["away_goals"] else "D"),
            axis=1,
        )

    # 可选统计字段
    stat_cols = {
        "HS": "home_shots", "AS": "away_shots",
        "HST": "home_shots_ontarget", "AST": "away_shots_ontarget",
        "HC": "home_corners", "AC": "away_corners",
        "HF": "home_fouls", "AF": "away_fouls",
        "HY": "home_yellow", "AY": "away_yellow",
        "HR": "home_red", "AR": "away_red",
    }
    for src, dst in stat_cols.items():
        if src in df.columns:
            std[dst] = pd.to_numeric(df[src], errors="coerce")

    # 保留博彩赔率列（转换成数值）
    for cat in ['close', 'open']:
        for col in ODDS_COLUMNS.get(cat, []):
            if col in df.columns:
                std[col] = pd.to_numeric(df[col], errors="coerce")

    # 过滤无效行
    before = len(std)
    std = std.dropna(subset=["home_goals", "away_goals", "date"])
    std = std[std["home_goals"].between(0, 20)]
    std = std[std["away_goals"].between(0, 20)]
    after = len(std)

    if before != after:
        logger.info(f"  过滤掉 {before - after} 行无效数据")

    return std.sort_values("date").reset_index(drop=True)


def generate_sample_data(
    n_matches: int = 2000,
    seed: int = 42,
) -> pd.DataFrame:
    """
    生成合成比赛数据用于测试

    模拟五大联赛，基于真实足球统计分布：
    - 主场进球 ~ Poisson(1.5)
    - 客场进球 ~ Poisson(1.2)
    - 主胜 ~ 46%, 平局 ~ 27%, 客胜 ~ 27%
    """
    rng = np.random.default_rng(seed)
    league_keys = list(LEAGUES.keys())

    teams = {
        "EPL": ["Man City", "Arsenal", "Liverpool", "Man Utd", "Chelsea",
                "Tottenham", "Newcastle", "Aston Villa", "Brighton", "West Ham",
                "Crystal Palace", "Brentford", "Fulham", "Wolves", "Bournemouth",
                "Nottingham", "Everton", "Leicester", "Southampton", "Ipswich"],
        "LaLiga": ["Real Madrid", "Barcelona", "Atletico", "Sevilla", "Sociedad",
                   "Bilbao", "Betis", "Villarreal", "Valencia", "Osasuna"],
        "SerieA": ["Inter", "Milan", "Juventus", "Napoli", "Roma",
                   "Lazio", "Atalanta", "Fiorentina", "Bologna", "Torino"],
        "Bundesliga": ["Bayern", "Dortmund", "Leverkusen", "Leipzig", "Frankfurt",
                       "Stuttgart", "Gladbach", "Wolfsburg", "Freiburg", "Hoffenheim"],
        "Ligue1": ["PSG", "Marseille", "Monaco", "Lyon", "Lille",
                   "Nice", "Rennes", "Lens", "Strasbourg", "Nantes"],
    }

    # 球队实力评分 (用于生成更真实的数据)
    team_strength = {}
    for league, team_list in teams.items():
        base = rng.uniform(70, 95, len(team_list))
        base = np.sort(base)[::-1]  # 强队在前
        for team, strength in zip(team_list, base):
            team_strength[team] = strength

    records = []
    start_date = datetime(2020, 8, 1)

    # 排赛程: 每赛季每队主客各一场
    match_id = 0
    for season_offset in range(3):  # 3个赛季
        season_code = f"2{season_offset}20"
        base_date = start_date.replace(year=start_date.year + season_offset)

        for league_key in league_keys:
            league_teams = teams[league_key]
            n = len(league_teams)

            for i in range(n):
                for j in range(i + 1, n):
                    # 主客场各一场
                    for home_first in [True, False]:
                        home = league_teams[i] if home_first else league_teams[j]
                        away = league_teams[j] if home_first else league_teams[i]

                        s_home = team_strength[home]
                        s_away = team_strength[away]

                        # 预期进球基于实力差
                        home_adv = 0.4
                        strength_factor = (s_home - s_away) / 100
                        lambda_home = max(0.2, 1.5 + strength_factor + home_adv)
                        lambda_away = max(0.1, 1.2 - strength_factor)

                        home_goals = rng.poisson(lambda_home)
                        away_goals = rng.poisson(lambda_away)

                        # 生成日期: 简单递增
                        days_offset = match_id
                        try:
                            from datetime import timedelta
                            match_date = base_date + timedelta(days=days_offset)
                        except Exception:
                            # fallback
                            month = 8 + ((match_id * 7) // 200) % 10
                            if month > 12:
                                month -= 4
                            if month < 1:
                                month = 1
                            day = 1 + (match_id * 3) % 27
                            try:
                                match_date = base_date.replace(month=month, day=day)
                            except ValueError:
                                match_date = base_date.replace(month=8, day=1 + match_id % 28)

                        records.append({
                            "league": league_key,
                            "season_code": season_code,
                            "division": list(LEAGUES.keys()).index(league_key) + 1,
                            "date": match_date,
                            "home_team": home,
                            "away_team": away,
                            "home_goals": home_goals,
                            "away_goals": away_goals,
                            "result": "H" if home_goals > away_goals
                                      else ("A" if home_goals < away_goals else "D"),
                        })
                        match_id += 1

                        if len(records) >= n_matches:
                            break
                    if len(records) >= n_matches:
                        break
                if len(records) >= n_matches:
                    break
            if len(records) >= n_matches:
                break
        if len(records) >= n_matches:
            break

    df = pd.DataFrame(records[:n_matches])
    df["league"] = df["league"].astype(str)
    logger.info(f"生成 {len(df)} 条合成测试数据")
    return df


def load_data(
    data_source: str = "sample",
    league_keys: list[str] | None = None,
    n_sample: int = 2000,
    force_download: bool = False,
) -> pd.DataFrame:
    """
    统一数据入口：从指定源加载并标准化

    Args:
        data_source: "sample" | "download" | "csv"
        league_keys: 联赛列表，默认全部
        n_sample: 采样数量
        force_download: 强制重新下载

    Returns:
        标准化后的 DataFrame
    """
    league_keys = league_keys or list(LEAGUES.keys())

    if data_source == "sample":
        df = generate_sample_data(n_matches=n_sample)

    elif data_source == "download":
        all_dfs = []
        for key in league_keys:
            raw = download_league_data(key, force=force_download)
            if not raw.empty:
                std = standardize_dataframe(raw)
                all_dfs.append(std)
        df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()

    elif data_source == "csv":
        # 从本地 CSV 加载
        csv_path = RAW_DIR / "custom_data.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"未找到自定义数据: {csv_path}")
        raw = pd.read_csv(csv_path)
        df = standardize_dataframe(raw)

    else:
        raise ValueError(f"未知数据源: {data_source}，可选: sample/download/csv")

    if df.empty:
        logger.error("未加载到任何数据！")
    else:
        logger.info(f"数据加载完成: {len(df)} 条, {df['league'].nunique()} 个联赛")

    return df
