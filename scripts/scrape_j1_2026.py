"""
Scrape 2026 J1 League data from alternative sources
"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from bs4 import BeautifulSoup
import pandas as pd

RAW_DIR = Path(__file__).parent.parent / 'data' / 'raw'


def scrape_worldfootball():
    """Try worldfootball.net for 2026 J1 results"""
    url = 'https://www.worldfootball.net/competition/jpn-j1-league/'
    try:
        r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            tables = soup.find_all('table', class_='standard_tabelle')
            print(f'Found {len(tables)} tables')
            for i, t in enumerate(tables[:3]):
                rows = t.find_all('tr')
                print(f'  Table {i}: {len(rows)} rows')
                if rows:
                    cells = rows[0].find_all(['th','td'])
                    print(f'    Header: {[c.get_text(strip=True) for c in cells[:8]]}')
                    if len(rows) > 1:
                        cells = rows[1].find_all(['th','td'])
                        print(f'    First row: {[c.get_text(strip=True) for c in cells[:8]]}')
        else:
            print(f'worldfootball: {r.status_code}')
    except Exception as e:
        print(f'worldfootball error: {e}')


def scrape_flashfootball():
    """Try flashfootball.com for J1 2026 archive"""
    url = 'https://www.flashfootball.com/japan/j1-league/archive'
    try:
        r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200:
            print(f'flashfootball: {len(r.text)}B')
            # Look for match data in JSON
            matches = re.findall(r'"homeName":"([^"]+)","awayName":"([^"]+)"', r.text)
            scores = re.findall(r'"homeScore":(\d+),"awayScore":(\d+)', r.text)
            print(f'  Found {len(matches)} matches in JSON')
            if matches:
                print(f'  Sample: {matches[0]} -> {scores[0] if scores else "no score"}')
        else:
            print(f'flashfootball: {r.status_code}')
    except Exception as e:
        print(f'flashfootball error: {e}')


def scrape_soccerpunter():
    """Try soccerpunter.com for J1 2026 results with odds"""
    url = 'https://www.soccerpunter.com/season/26810/Japan-J1-League-2026-2027/'
    try:
        r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200 and len(r.text) > 5000:
            print(f'soccerpunter: {len(r.text)}B')
            # Look for match rows
            matches = re.findall(r'class="[^"]*match[^"]*"[^>]*>(.*?)</tr>', r.text, re.DOTALL)
            print(f'  Found {len(matches)} match rows')
            if matches:
                print(f'  Sample: {matches[0][:200]}')
        else:
            print(f'soccerpunter: {r.status_code}')
    except Exception as e:
        print(f'soccerpunter error: {e}')


def scrape_jleague():
    """Try the official J.League site for 2026 results"""
    # The official site has an API
    url = 'https://data.jleague.jp/data/competition/top/top_match_list.json'
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            print(f'jleague API: {len(data)} entries')
            print(f'Sample: {json.dumps(data[:2], indent=2)}')
        else:
            print(f'jleague: {r.status_code}')
    except Exception as e:
        print(f'jleague error: {e}')


# Run all scrapers
print('=== Scraping J1 2026 data ===\n')
scrape_worldfootball()
print()
scrape_flashfootball()
print()
scrape_soccerpunter()
print()
scrape_jleague()
