"""
实时赔率更新 — 从 football-data.co.uk 爬取最新世界杯赔率

数据来源 (按优先级):
  1. fixtures.csv — 即将开赛的比赛（含最新赔率）
  2. mmz4281/2526/WC.csv — 已结束的比赛（仅历史数据）
"""
import sys, csv, io, re
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import pandas as pd

RAW_DIR = Path(__file__).parent.parent / 'data' / 'raw'


def fetch_fixtures_odds() -> list[dict]:
    """从 fixtures.csv 爬取世界杯比赛的实时赔率"""
    print('Fetching latest odds from football-data.co.uk...')

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    # 尝试多个数据源
    sources = [
        ('fixtures.csv', 'https://www.football-data.co.uk/fixtures.csv'),
        ('new/WC.csv', 'https://www.football-data.co.uk/new/WC.csv'),
        ('mmz4281/2526/WC.csv', 'https://www.football-data.co.uk/mmz4281/2526/WC.csv'),
    ]

    all_matches = []

    for label, url in sources:
        try:
            r = requests.get(url, timeout=15, headers=headers)
            if r.status_code != 200:
                print(f'  [{label}] status={r.status_code}, skipped')
                continue

            text = r.content.decode('utf-8-sig', errors='replace')

            # 检查是否是 CSV 格式
            if 'Div' in text[:200] or 'Date' in text[:200]:
                lines = text.strip().split('\n')
                if len(lines) < 2:
                    print(f'  [{label}] {len(lines)} lines, too short')
                    continue

                reader = csv.DictReader(io.StringIO(text))
                matches = []
                for row in reader:
                    div = row.get('Div', '').strip()
                    home = row.get('HomeTeam', row.get('Home', '')).strip()
                    away = row.get('AwayTeam', row.get('Away', '')).strip()
                    date_str = row.get('Date', '').strip()

                    # 尝试解析 Bet365 赔率（不同格式列名不同）
                    b365h = _parse_odds(row.get('B365H', row.get('B365CH', '')))
                    b365d = _parse_odds(row.get('B365D', row.get('B365CD', '')))
                    b365a = _parse_odds(row.get('B365A', row.get('B36CA', '')))

                    # 只保留有赔率的 WC 比赛
                    if div.startswith('WC') and b365h and b365d and b365a:
                        matches.append({
                            'date': date_str,
                            'home': home,
                            'away': away,
                            'b365h': b365h,
                            'b365d': b365d,
                            'b365a': b365a,
                            'source': label,
                        })

                print(f'  [{label}] found {len(matches)} WC matches with odds')
                all_matches.extend(matches)

        except Exception as e:
            print(f'  [{label}] error: {e}')

    return all_matches


def _parse_odds(val) -> float:
    """安全解析赔率"""
    if not val:
        return 0.0
    try:
        v = float(val.strip())
        return v if v > 1.0 else 0.0
    except (ValueError, AttributeError):
        return 0.0


def update_db(matches: list[dict]) -> dict:
    """将爬到的赔率更新到数据库"""
    from src.database import get_conn, refresh_odds

    if not matches:
        return {'updated': 0, 'source': 'no data'}

    # 先把爬到的数据保存成 CSV
    csv_path = Path(__file__).parent.parent / 'data' / 'live_odds.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['date', 'group', 'home', 'away', 'B365H', 'B365D', 'B365A']
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for m in matches:
            w.writerow({
                'date': m['date'],
                'group': '',
                'home': m['home'],
                'away': m['away'],
                'B365H': m['b365h'],
                'B365D': m['b365d'],
                'B365A': m['b365a'],
            })

    # 用已有的 refresh_odds 更新数据库
    result = refresh_odds(csv_path)
    result['source'] = 'live'
    return result


def main():
    """主流程"""
    t0 = datetime.now()
    print(f'[{t0.strftime("%H:%M:%S")}] 开始更新赔率...')

    matches = fetch_fixtures_odds()
    result = update_db(matches)

    elapsed = (datetime.now() - t0).total_seconds()
    print(f'[{datetime.now().strftime("%H:%M:%S")}] 完成 ({elapsed:.1f}s)')
    print(f'  更新: {result["updated"]} 场比赛')
    print(f'  来源: {result.get("source", "unknown")}')

    # 如果没有新数据，给提示
    if result['updated'] == 0:
        print()
        print('⚠️  football-data.co.uk 还没有发布世界杯最新赔率。')
        print('   通常在开赛前 1-3 天会放出。')
        print('   临近 6月11日 再试，或者开赛当天会自动有数据。')

    return result


if __name__ == '__main__':
    main()
