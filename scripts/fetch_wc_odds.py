"""
Fetch 2026 World Cup match odds from the-odds-api.com

Usage:
    python scripts/fetch_wc_odds.py

Updates run_wc_odds.csv with real bookmaker odds (Paddy Power).
Team names are mapped to match the existing CSV format.
"""
import sys, os, csv
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

# ── Config ──────────────────────────────────────────────
API_KEY = os.getenv('ODDS_API_KEY', '')
if not API_KEY:
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if line.startswith('ODDS_API_KEY='):
                API_KEY = line.split('=', 1)[1].strip()

SPORT = 'soccer_fifa_world_cup'
BOOKMAKER = 'paddypower'
REGIONS = 'uk'
MARKETS = 'h2h'

# ── Team name mapping (API → CSV) ──────────────────────
TEAM_NAME_MAP = {
    'Bosnia & Herzegovina': 'Bosnia',
    'Curaçao': 'Curacao',
    'Czech Republic': 'Czechia',
}

# ── Group assignments (by team) ─────────────────────────
GROUPS_BY_TEAM = {
    'Mexico': 'A', 'South Africa': 'A', 'South Korea': 'A', 'Czechia': 'A',
    'Canada': 'B', 'Bosnia': 'B', 'Qatar': 'B', 'Switzerland': 'B',
    'Brazil': 'C', 'Morocco': 'C', 'Haiti': 'C', 'Scotland': 'C',
    'USA': 'D', 'Paraguay': 'D', 'Australia': 'D', 'Turkey': 'D',
    'Germany': 'E', 'Curacao': 'E', 'Ivory Coast': 'E', 'Ecuador': 'E',
    'Netherlands': 'F', 'Japan': 'F', 'Sweden': 'F', 'Tunisia': 'F',
    'Belgium': 'G', 'Egypt': 'G', 'Iran': 'G', 'New Zealand': 'G',
    'Spain': 'H', 'Cape Verde': 'H', 'Saudi Arabia': 'H', 'Uruguay': 'H',
    'France': 'I', 'Senegal': 'I', 'Iraq': 'I', 'Norway': 'I',
    'Argentina': 'J', 'Algeria': 'J', 'Austria': 'J', 'Jordan': 'J',
    'Portugal': 'K', 'DR Congo': 'K', 'Uzbekistan': 'K', 'Colombia': 'K',
    'England': 'L', 'Croatia': 'L', 'Ghana': 'L', 'Panama': 'L',
}


def map_team(api_name: str) -> str:
    """Map API team name to CSV team name."""
    return TEAM_NAME_MAP.get(api_name, api_name)


def get_group(home_team: str, date_str: str) -> str:
    """Determine group from team name."""
    return GROUPS_BY_TEAM.get(home_team, '?')


def fetch_odds() -> list[dict]:
    """Fetch 72 WC matches with odds from Paddy Power via Odds API."""
    url = (
        f'https://api.the-odds-api.com/v4/sports/{SPORT}/odds/'
        f'?apiKey={API_KEY}&regions={REGIONS}&markets={MARKETS}'
        f'&bookmakers={BOOKMAKER}'
    )
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()


def build_csv_rows(api_data: list[dict]) -> list[dict]:
    """Convert API response to CSV rows matching run_wc_odds.csv format."""
    rows = []
    for match in api_data:
        date = match['commence_time'][:10]
        home_api = match['home_team']
        away_api = match['away_team']
        home = map_team(home_api)
        away = map_team(away_api)

        b365h = b365d = b365a = 0.0
        for bm in match.get('bookmakers', []):
            if bm['key'] == BOOKMAKER:
                for market in bm.get('markets', []):
                    if market['key'] == 'h2h':
                        for outcome in market['outcomes']:
                            name = outcome['name']
                            if name == home_api:
                                b365h = outcome['price']
                            elif name == 'Draw':
                                b365d = outcome['price']
                            elif name == away_api:
                                b365a = outcome['price']

        group = get_group(home, date)
        rows.append({
            'date': date,
            'group': group,
            'home': home,
            'away': away,
            'B365H': f'{b365h:.2f}',
            'B365D': f'{b365d:.2f}',
            'B365A': f'{b365a:.2f}',
        })

    return rows


def main():
    t0 = datetime.now()
    print(f'[{t0.strftime("%H:%M:%S")}] Fetching WC odds from Odds API...')
    print(f'  Source: {BOOKMAKER}')
    print(f'  API Key: {API_KEY[:6]}...{API_KEY[-4:]}')

    data = fetch_odds()
    print(f'  Got {len(data)} matches')

    rows = build_csv_rows(data)
    rows.sort(key=lambda r: r['date'])
    print(f'  Built {len(rows)} CSV rows')

    csv_path = Path(__file__).parent.parent / 'run_wc_odds.csv'
    fieldnames = ['date', 'group', 'home', 'away', 'B365H', 'B365D', 'B365A']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    elapsed = (datetime.now() - t0).total_seconds()
    print(f'[{datetime.now().strftime("%H:%M:%S")}] Done ({elapsed:.1f}s)')
    print(f'  File: {csv_path}')
    print(f'  Matches: {len(rows)}')

    print(f'\nSample (first 3):')
    for row in rows[:3]:
        print(f'  {row["date"]} [{row["group"]}] {row["home"]:20s} vs {row["away"]:20s}  '
              f'H={row["B365H"]} D={row["B365D"]} A={row["B365A"]}')


if __name__ == '__main__':
    main()
