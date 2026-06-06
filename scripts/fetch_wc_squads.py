"""
Fetch 2026 World Cup squads from Wikipedia

Parses the Wikipedia squad page and extracts player data for all 48 teams.
Output: data/wc_squads.json
"""
import sys, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from bs4 import BeautifulSoup

API_URL = 'https://en.wikipedia.org/w/api.php?action=parse&page=2026_FIFA_World_Cup_squads&format=json&prop=text'

TEAM_NAME_MAP = {
    'Czech Republic': 'Czechia',
    'United States': 'USA',
}

POSITION_MAP = {
    'GK': 'GK', 'Goalkeeper': 'GK',
    'DF': 'DF', 'Defender': 'DF',
    'MF': 'MF', 'Midfielder': 'MF',
    'FW': 'FW', 'Forward': 'FW',
}


def fetch_page() -> str:
    r = requests.get(API_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
    return r.json().get('parse', {}).get('text', {}).get('*', '')


def extract_squads(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, 'html.parser')
    squads = {}

    for h3 in soup.find_all('h3'):
        team_name = h3.get_text(strip=True)
        if not team_name or len(team_name) < 3:
            continue
        skip_words = ['Squads', 'References', 'External', 'Notes',
                      'Group', 'Knockout', 'Tournament', 'Player',
                      'Statistics', 'Coach', 'Manager']
        if any(w in team_name for w in skip_words):
            continue

        table = h3.find_next('table', class_='wikitable')
        if not table:
            continue

        players = []
        for row in table.find_all('tr')[1:]:
            cols = row.find_all(['td', 'th'])
            if len(cols) >= 7:
                try:
                    pos_text = cols[1].get_text(strip=True)
                    player = {
                        'number': cols[0].get_text(strip=True),
                        'position': POSITION_MAP.get(pos_text, pos_text),
                        'name': cols[2].get_text(strip=True),
                        'caps': _parse_int(cols[4].get_text(strip=True)),
                        'goals': _parse_int(cols[5].get_text(strip=True)),
                        'club': cols[6].get_text(strip=True),
                    }
                    if player['name']:
                        players.append(player)
                except (IndexError, ValueError):
                    continue

        if players:
            squads[team_name] = players

    return squads


def map_team_names(squads: dict) -> dict:
    mapped = {}
    for wiki_name, players in squads.items():
        our_name = TEAM_NAME_MAP.get(wiki_name, wiki_name)
        mapped[our_name] = players
    return mapped


def _parse_int(val: str) -> int:
    val = val.strip()
    try:
        return int(val)
    except ValueError:
        return 0


def main():
    t0 = datetime.now()
    print(f'[{t0.strftime("%H:%M:%S")}] Fetching WC squads from Wikipedia...')

    html = fetch_page()
    print(f'  Got {len(html):,} chars')

    squads = extract_squads(html)
    print(f'  Extracted {len(squads)} teams')

    squads = map_team_names(squads)

    total_players = sum(len(v) for v in squads.values())
    print(f'  Total players: {total_players}')

    output = Path(__file__).parent.parent / 'data' / 'wc_squads.json'
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(squads, f, indent=2, ensure_ascii=False)

    elapsed = (datetime.now() - t0).total_seconds()
    print(f'[{datetime.now().strftime("%H:%M:%S")}] Done ({elapsed:.1f}s)')
    print(f'  Saved to: {output}')

    for team, players in sorted(squads.items()):
        positions = {}
        for p in players:
            pos = p.get('position', '?')
            positions[pos] = positions.get(pos, 0) + 1
        pos_str = ', '.join(f'{k}={v}' for k, v in sorted(positions.items()))
        print(f'  {team:20s}: {len(players):2d} players | {pos_str}')


if __name__ == '__main__':
    main()
