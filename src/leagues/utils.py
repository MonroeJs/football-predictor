"""
联赛数据处理工具 — 标准化不同数据格式
"""
from pathlib import Path
import pandas as pd
import numpy as np

from config import RAW_DIR, FD_URL_TEMPLATE


def standardize_european(df: pd.DataFrame) -> pd.DataFrame:
    """标准化欧洲联赛格式 (HomeTeam, AwayTeam, FTHG, FTAG, FTR)

    columns: Div, Date, Time, HomeTeam, AwayTeam, FTHG, FTAG, FTR, HTHG, HTAG, HTR, Referee, ..., B365H, B365D, B365A
    """
    std = pd.DataFrame()
    std['date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
    std['home_team'] = df['HomeTeam'].astype(str).str.strip()
    std['away_team'] = df['AwayTeam'].astype(str).str.strip()
    std['home_goals'] = pd.to_numeric(df['FTHG'], errors='coerce')
    std['away_goals'] = pd.to_numeric(df['FTAG'], errors='coerce')
    std['result'] = df['FTR'].str.strip()
    std['season'] = df.get('season_code', '')

    # Bet365 odds
    for col in ['B365H', 'B365D', 'B365A']:
        if col in df.columns:
            std[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            std[col] = np.nan

    # Closing odds (if available)
    for old, new in [('B365CH', 'b365h_close'), ('B365CD', 'b365d_close'), ('B365CA', 'b365a_close')]:
        if old in df.columns:
            std[new] = pd.to_numeric(df[old], errors='coerce')

    return std


def standardize_new_format(df: pd.DataFrame) -> pd.DataFrame:
    """标准化 'new' 目录格式 (Home, Away, HG, AG, Res)

    columns: Country, League, Season, Date, Time, Home, Away, HG, AG, Res, ..., B365CH, B365CD, B36CA
    """
    std = pd.DataFrame()

    # Date - handle dd/mm/YYYY or other formats
    if 'Date' in df.columns:
        std['date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
    else:
        std['date'] = pd.NaT

    std['home_team'] = df['Home'].astype(str).str.strip()
    std['away_team'] = df['Away'].astype(str).str.strip()
    std['home_goals'] = pd.to_numeric(df['HG'], errors='coerce')
    std['away_goals'] = pd.to_numeric(df['AG'], errors='coerce')
    std['result'] = df['Res'].str.strip()
    std['season'] = df.get('Season', '')
    std['league'] = df.get('League', '').astype(str).str.strip()

    # Bet365 closing odds (new format uses B365CH, B365CD, B36CA)
    if 'B365CH' in df.columns:
        std['B365H'] = pd.to_numeric(df['B365CH'], errors='coerce')
    if 'B365CD' in df.columns:
        std['B365D'] = pd.to_numeric(df['B365CD'], errors='coerce')
    if 'B36CA' in df.columns:
        std['B365A'] = pd.to_numeric(df['B36CA'], errors='coerce')

    # If no Bet365, try Pinnacle
    if std['B365H'].isna().all():
        for old, new_key in [('PSCH', 'B365H'), ('PSCD', 'B365D'), ('PSCA', 'B365A')]:
            if old in df.columns:
                std[new_key] = pd.to_numeric(df[old], errors='coerce')

    return std


def download_csv(url: str, label: str = '') -> pd.DataFrame:
    """下载 CSV 并返回 DataFrame
    自动处理 SSL 错误，降级到 verify=False
    """
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        r = requests.get(url, timeout=30, verify=True)
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
        print(f'  [{label}] SSL error, retrying without verify: {e}')
        try:
            r = requests.get(url, timeout=30, verify=False)
        except Exception as e2:
            print(f'  [{label}] download failed: {e2}')
            return pd.DataFrame()
    except Exception as e:
        print(f'  [{label}] download failed: {e}')
        return pd.DataFrame()
    
    if r.status_code != 200:
        print(f'  [{label}] download failed: {r.status_code}')
        return pd.DataFrame()

    # Try UTF-8 BOM first, then UTF-8, then ascii
    for encoding in ['utf-8-sig', 'utf-8', 'ascii']:
        try:
            text = r.content.decode(encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        text = r.content.decode('utf-8', errors='replace')

    if not text.strip():
        return pd.DataFrame()

    # Save to raw dir for caching
    safe_name = label.replace('/', '_').replace(':', '')
    raw_path = RAW_DIR / f'{safe_name}.csv'
    with open(raw_path, 'w', encoding='utf-8') as f:
        f.write(text)

    return pd.read_csv(raw_path)


def download_european(season_codes: list[str], league_code: str) -> pd.DataFrame:
    """下载欧洲联赛数据（标准 mmz4281 格式）"""
    dfs = []
    for season in season_codes:
        url = FD_URL_TEMPLATE.format(season=season, code=league_code)
        df = download_csv(url, f'{league_code}_{season}')
        if not df.empty:
            df['season_code'] = season
            dfs.append(df)

    if not dfs:
        return pd.DataFrame()
    raw = pd.concat(dfs, ignore_index=True)
    return standardize_european(raw)


def download_new_format(url: str, label: str) -> pd.DataFrame:
    """下载 'new' 目录格式数据（非欧洲联赛）"""
    df = download_csv(url, label)
    if df.empty:
        return df
    return standardize_new_format(df)
