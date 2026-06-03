"""
xG 数据获取模块 — 从 Understat 拉取预期进球数据

Understat 提供五大联赛的每场比赛 xG 数据。
API: GET https://understat.com/getLeagueData/{league}/{season_year}

Understat 联赛名映射:
    EPL -> EPL
    LaLiga -> La liga
    SerieA -> Serie A
    Bundesliga -> Bundesliga
    Ligue1 -> Ligue 1

赛季年份: 2025 = 2025/2026赛季, 2024 = 2024/2025, 以此类推
"""

import re
import json
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests

from config import RAW_DIR, SEASON_CODES
from src.utils import logger


# Understat 联赛名映射
UNDERSTAT_LEAGUES = {
    "EPL":       "EPL",
    "LaLiga":    "La liga",
    "SerieA":    "Serie A",
    "Bundesliga": "Bundesliga",
    "Ligue1":    "Ligue 1",
}


def _season_to_year(season_code: str) -> int:
    """将赛季码转为赛季起始年份
    2425 -> 2024 (代表 2024/2025 赛季)
    1617 -> 2016
    """
    prefix = int(season_code[:2])
    # 14xx = 2014+, 25xx = 2025+, 但 14 也可能是 1914
    # 安全方式：对所有 prefix >= 10 用 2000 基准
    # Understat 数据从 2014 年开始
    if prefix >= 10:  # 10 ~ 99 都视为 20xx
        return 2000 + prefix
    else:  # 00 ~ 09 或更早
        return 2000 + prefix


def _year_to_season_code(year: int) -> str:
    """将 2024 转为 2425"""
    y2 = year + 1
    y1_short = str(year)[-2:]
    y2_short = str(y2)[-2:]
    return f"{y1_short}{y2_short}"


def fetch_xg_from_understat(
    league_key: str,
    season_year: int,
    delay: float = 0.5,
) -> pd.DataFrame | None:
    """
    从 Understat 获取指定联赛+赛季的 xG 数据

    Args:
        league_key: 'EPL', 'LaLiga' 等
        season_year: 赛季起始年份，如 2024 = 2024/2025
        delay: 请求间隔

    Returns:
        DataFrame 包含每场比赛的 xG 数据
    """
    if league_key not in UNDERSTAT_LEAGUES:
        raise ValueError(f"未知联赛: {league_key}")

    league_name = UNDERSTAT_LEAGUES[league_key]
    url = f"https://understat.com/getLeagueData/{league_name}/{season_year}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://understat.com/league/{league_name}/{season_year}",
    }

    logger.info(f"  获取 {league_key} {season_year}/{season_year+1}: {url}")

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning(f"    请求失败: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"    JSON 解析失败: {e}")
        return None

    if "dates" not in data:
        logger.warning(f"    响应中无 'dates' 字段")
        return None

    # Understat 日期格式: "2025-08-16 16:00:00"
    season_code = _year_to_season_code(season_year)

    records = []
    for match in data["dates"]:
        # 只处理已进行的比赛
        if not match.get("isResult"):
            continue

        h = match.get("h", {})
        a = match.get("a", {})
        goals = match.get("goals", {})
        xg = match.get("xG", {})

        home_team = h.get("title", "?")
        away_team = a.get("title", "?")

        # 比分
        home_goals = goals.get("h") if isinstance(goals, dict) else None
        away_goals = goals.get("a") if isinstance(goals, dict) else None

        if home_goals is None or away_goals is None:
            continue

        # 结果
        if home_goals > away_goals:
            result = "H"
        elif home_goals < away_goals:
            result = "A"
        else:
            result = "D"

        # xG
        xg_home = xg.get("h") if isinstance(xg, dict) else None
        xg_away = xg.get("a") if isinstance(xg, dict) else None

        if xg_home is None or xg_away is None:
            continue

        # 日期
        dt_str = match.get("datetime", "")
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                dt = pd.NaT

        records.append({
            "date": dt,
            "home_team": home_team,
            "away_team": away_team,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "result": result,
            "xg_home": float(xg_home),
            "xg_away": float(xg_away),
            "league": league_key,
            "season_code": season_code,
        })

    if not records:
        logger.warning(f"    未解析到有效数据")
        return None

    df = pd.DataFrame(records)
    logger.info(f"    获取 {len(df)} 条 xG 记录")

    time.sleep(delay)
    return df


def fetch_all_understat(
    season_codes: list[str] | None = None,
    delay: float = 0.5,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """
    爬取全部五大联赛的 xG 数据

    Args:
        season_codes: 赛季代码列表
        delay: 请求间隔
        force: 强制重新爬取

    Returns:
        {联赛: DataFrame}
    """
    season_codes = season_codes or SEASON_CODES

    # Understat 从 2014 年开始有数据，但我们用 1617 起
    recent_codes = [s for s in season_codes if int(s[:2]) >= 14]

    result = {}
    for league_key in UNDERSTAT_LEAGUES:
        league_dfs = []

        for sc in recent_codes:
            season_year = _season_to_year(sc)

            # 检查缓存
            cache_path = RAW_DIR / f"xg_{league_key}_{sc}.csv"
            if cache_path.exists() and not force:
                df = pd.read_csv(cache_path, parse_dates=["date"])
                logger.info(f"  [缓存] {league_key} {sc}: {len(df)} 条")
                league_dfs.append(df)
                continue

            df = fetch_xg_from_understat(league_key, season_year, delay=delay)
            if df is not None and not df.empty:
                df.to_csv(cache_path, index=False)
                league_dfs.append(df)

        if league_dfs:
            combined = pd.concat(league_dfs, ignore_index=True)
            result[league_key] = combined
            logger.info(f"{league_key}: 共 {len(combined)} 条 xG 记录")
        else:
            logger.warning(f"{league_key}: 未获取到 xG 数据")

    return result


# 球队名映射（football-data.co.uk -> Understat）
TEAM_NAME_MAP = {
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Man Utd": "Manchester United",
    "Newcastle": "Newcastle United",
    "Nott'm Forest": "Nottingham Forest",
    "Nottingham": "Nottingham Forest",
    "Wolves": "Wolverhampton Wanderers",
    "Sheffield United": "Sheffield United",
    "Brighton": "Brighton",
    "Leicester": "Leicester City",
    "Leeds": "Leeds United",
    "Southampton": "Southampton",
    "Stoke": "Stoke City",
    "West Brom": "West Bromwich Albion",
    "West Bromwich": "West Bromwich Albion",
    "Norwich": "Norwich City",
    "Middlesbrough": "Middlesbrough",
    "Hull": "Hull City",
    "Cardiff": "Cardiff City",
    "Swansea": "Swansea City",
    "Watford": "Watford",
    "Huddersfield": "Huddersfield Town",
    "Luton": "Luton Town",
    "Ipswich": "Ipswich Town",
    # La Liga
    "Alaves": "Alavés",
    "Ath Madrid": "Atlético Madrid",
    "Ath Bilbao": "Athletic Bilbao",
    "Real Madrid": "Real Madrid",
    "Barcelona": "Barcelona",
    "Valencia": "Valencia",
    "Sevilla": "Sevilla",
    "Sociedad": "Real Sociedad",
    "Villarreal": "Villarreal",
    "Betis": "Real Betis",
    "Osasuna": "Osasuna",
    "Espanol": "Espanyol",
    "Celta": "Celta Vigo",
    "Getafe": "Getafe",
    "Mallorca": "Mallorca",
    "Granada": "Granada",
    "Levante": "Levante",
    "Vallecano": "Rayo Vallecano",
    "Cadiz": "Cádiz",
    "Elche": "Elche",
    # Serie A
    "AC Milan": "Milan",
    "Inter Milan": "Inter",
    "AS Roma": "Roma",
    "Fiorentina": "Fiorentina",
    "Napoli": "Napoli",
    "Lazio": "Lazio",
    "Atalanta": "Atalanta",
    "Bologna": "Bologna",
    "Sassuolo": "Sassuolo",
    "Udinese": "Udinese",
    "Sampdoria": "Sampdoria",
    "Genoa": "Genoa",
    "Torino": "Torino",
    "Cagliari": "Cagliari",
    "Verona": "Hellas Verona",
    "Spezia": "Spezia",
    "Empoli": "Empoli",
    "Monza": "Monza",
    # Bundesliga
    "Bayern Munich": "Bayern München",
    "Dortmund": "Borussia Dortmund",
    "Leverkusen": "Bayer Leverkusen",
    "RB Leipzig": "RB Leipzig",
    "Leipzig": "RB Leipzig",
    "Borussia M'bach": "Borussia Mönchengladbach",
    "M'gladbach": "Borussia Mönchengladbach",
    "Gladbach": "Borussia Mönchengladbach",
    "Wolfsburg": "Wolfsburg",
    "Eintracht": "Eintracht Frankfurt",
    "Stuttgart": "Stuttgart",
    "Hoffenheim": "TSG Hoffenheim",
    "Freiburg": "SC Freiburg",
    "Mainz": "Mainz 05",
    "Augsburg": "Augsburg",
    "Hertha": "Hertha BSC",
    "Bremen": "Werder Bremen",
    "Union Berlin": "Union Berlin",
    "Cologne": "1. FC Köln",
    "Koln": "1. FC Köln",
    "Bochum": "Bochum",
    "Darmstadt": "Darmstadt 98",
    "Heidenheim": "Heidenheim",
    # Ligue 1
    "PSG": "Paris Saint Germain",
    "Marseille": "Marseille",
    "Monaco": "Monaco",
    "Lyon": "Lyon",
    "Lille": "Lille",
    "Nice": "Nice",
    "Rennes": "Rennes",
    "Lens": "Lens",
    "Strasbourg": "Strasbourg",
    "Nantes": "Nantes",
    "Montpellier": "Montpellier",
    "Toulouse": "Toulouse",
    "Angers": "Angers",
    "Bordeaux": "Bordeaux",
    "St Etienne": "Saint-Étienne",
    "St.Etienne": "Saint-Étienne",
    "Reims": "Reims",
    "Brest": "Brest",
    "Metz": "Metz",
    "Clermont": "Clermont Foot",
    "Ajaccio": "Ajaccio",
    "Troyes": "Troyes",
    "Auxerre": "Auxerre",
    "Le Havre": "Le Havre",
}


def merge_xg_to_data(df_std: pd.DataFrame, xg_dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    将 xG 数据合并到标准比赛数据中

    Args:
        df_std: 标准化比赛数据
        xg_dfs: {联赛: 含 xG 的 DataFrame}

    Returns:
        合并后的数据，新增 xg_home, xg_away 列
    """
    logger.info("合并 xG 数据...")
    df = df_std.copy()

    xg_combined = []
    for league_key, xg_df in xg_dfs.items():
        xg_df = xg_df.copy()
        xg_df["_league"] = league_key
        xg_combined.append(xg_df)

    if not xg_combined:
        logger.warning("无 xG 数据可合并")
        df["xg_home"] = None
        df["xg_away"] = None
        return df

    xg_all = pd.concat(xg_combined, ignore_index=True)

    # 球队名标准化：先映射简称，再统一格式
    def normalize_name(name):
        """标准化球队名用于匹配"""
        n = str(name).strip()
        # 先做简称映射
        if n in TEAM_NAME_MAP:
            n = TEAM_NAME_MAP[n]
        # 再统一格式
        return n.lower().replace(" ", "").replace("-", "").replace("'", "").replace(".", "").replace("&", "")

    df["_home_key"] = df["home_team"].apply(normalize_name)
    df["_away_key"] = df["away_team"].apply(normalize_name)
    xg_all["_home_key"] = xg_all["home_team"].apply(normalize_name)
    xg_all["_away_key"] = xg_all["away_team"].apply(normalize_name)

    match_count = 0
    for idx, row in df.iterrows():
        league = row["league"]
        ldf = xg_all[xg_all["_league"] == league]

        if ldf.empty:
            continue

        match = ldf[
            (ldf["_home_key"] == row["_home_key"]) &
            (ldf["_away_key"] == row["_away_key"])
        ]

        if not match.empty:
            df.at[idx, "xg_home"] = float(match.iloc[0]["xg_home"])
            df.at[idx, "xg_away"] = float(match.iloc[0]["xg_away"])
            match_count += 1

    df = df.drop(columns=["_home_key", "_away_key"], errors="ignore")

    match_pct = match_count / max(len(df), 1) * 100
    logger.info(f"xG 匹配: {match_count}/{len(df)} ({match_pct:.1f}%)")

    if "xg_home" not in df.columns:
        df["xg_home"] = None
        df["xg_away"] = None

    return df


def add_xg_to_pipeline(std: pd.DataFrame) -> pd.DataFrame:
    """从缓存加载 xG 并合并，没缓存则爬取"""
    from config import SEASON_CODES

    # 检查缓存
    has_cache = False
    for league_key in UNDERSTAT_LEAGUES:
        for sc in SEASON_CODES:
            if (RAW_DIR / f"xg_{league_key}_{sc}.csv").exists():
                has_cache = True
                break
        if has_cache:
            break

    if not has_cache:
        logger.info("无 xG 缓存，开始爬取...")
        xg_dfs = fetch_all_understat(delay=0.5, force=False)
    else:
        logger.info("从缓存加载 xG 数据...")
        xg_dfs = {}
        for league_key in UNDERSTAT_LEAGUES:
            league_dfs = []
            for sc in SEASON_CODES:
                cache_path = RAW_DIR / f"xg_{league_key}_{sc}.csv"
                if cache_path.exists():
                    df = pd.read_csv(cache_path, parse_dates=["date"])
                    league_dfs.append(df)
            if league_dfs:
                xg_dfs[league_key] = pd.concat(league_dfs, ignore_index=True)

    return merge_xg_to_data(std, xg_dfs)


if __name__ == "__main__":
    # 快速测试
    df = fetch_xg_from_understat("EPL", 2025)
    if df is not None:
        print(f"\nEPL 2025/26: {len(df)} 场比赛")
        print(f"xG 范围: home [{df['xg_home'].min():.2f}, {df['xg_home'].max():.2f}], "
              f"away [{df['xg_away'].min():.2f}, {df['xg_away'].max():.2f}]")
        print(f"\n前5场:")
        for _, r in df.head(5).iterrows():
            print(f"  {r['home_team']:20s} vs {r['away_team']:20s} "
                  f"比分={r['home_goals']}-{r['away_goals']} "
                  f"xG={r['xg_home']:.2f}-{r['xg_away']:.2f} 结果={r['result']}")
