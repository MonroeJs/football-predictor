"""
获取最新的 J1 联赛数据
尝试多个来源
"""
import requests, csv, io, re
from pathlib import Path
import pandas as pd

RAW_DIR = Path(__file__).parent.parent / 'data' / 'raw'

def try_source(name, url, **kwargs):
    """尝试从一个数据源下载"""
    try:
        r = requests.get(url, timeout=30, **kwargs)
        if r.status_code == 200 and len(r.content) > 1000:
            text = r.content.decode('utf-8-sig', errors='replace')
            lines = text.split('\n')
            print(f'[OK] {name}: {len(r.content)}B, {len(lines)} rows')
            # Save
            safe_name = name.replace('/', '_').replace(':', '')
            path = RAW_DIR / f'{safe_name}.csv'
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            return text
        else:
            print(f'[NO] {name}: status={r.status_code}')
    except Exception as e:
        print(f'[ERR] {name}: {e}')
    return None

# 1. Try re-downloading JP.csv (might have been updated)
try_source('JP_fresh', 'https://www.football-data.co.uk/new/JP.csv')

# 2. Try with allow_redirects=True
try_source('JP_redirect', 'https://www.football-data.co.uk/mmz4281/2526/J1.csv', allow_redirects=True)

# 3. Try different season codes for J1
for season in ['2526', '2627']:
    for code in ['J1', 'JP', 'JPN']:
        url = f'https://www.football-data.co.uk/mmz4281/{season}/{code}.csv'
        try_source(f'J1_{season}_{code}', url, allow_redirects=True)

# 4. Check what data we got
for f in RAW_DIR.glob('*.csv'):
    if 'JP' in f.name or 'J1' in f.name:
        df = pd.read_csv(f)
        print(f'\n{f.name}:')
        print(f'  Shape: {df.shape}')
        seasons = df.get('Season', df.get('season_code', 'N/A'))
        if isinstance(seasons, pd.Series):
            print(f'  Seasons: {sorted(seasons.unique())}')
        dates = df.get('Date', 'N/A')
        if isinstance(dates, pd.Series) and len(dates) > 0:
            try:
                parsed = pd.to_datetime(dates, dayfirst=True, errors='coerce')
                print(f'  Date range: {parsed.min()} to {parsed.max()}')
            except:
                print(f'  Date sample: {dates.iloc[0]} to {dates.iloc[-1]}')
