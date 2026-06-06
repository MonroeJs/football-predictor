"""
Get 2026 J1 data from accessible sources
"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import pandas as pd

RAW_DIR = Path(__file__).parent.parent / 'data' / 'raw'

def fetch_json(url, name, **kwargs):
    try:
        r = requests.get(url, timeout=20, **kwargs)
        if r.status_code == 200:
            data = r.json()
            print(f'[OK] {name}: {json.dumps(data)[:500]}')
            return data
        print(f'[NO] {name}: {r.status_code}')
    except Exception as e:
        print(f'[ERR] {name}: {e}')
    return None

# 1. Try footballdatabase.com
print('=== footballdatabase ===')
r = requests.get('https://footballdatabase.com/league-scores-tables/japan-j-league-2026',
                 timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
if r.status_code == 200:
    text = r.text
    # Look for table data
    tables = re.findall(r'<tr[^>]*>(.*?)</tr>', text, re.DOTALL)
    print(f'  {len(tables)} table rows')
    # Look for standings
    standings = re.findall(r'<td[^>]*class="[^"]*team[^"]*"[^>]*>(.*?)</td>', text, re.DOTALL)
    print(f'  {len(standings)} team entries')
    if standings:
        print(f'  First: {standings[0][:100]}')

# 2. Try jleague.co fixtures page (might have match data)
print('\n=== jleague.co fixtures ===')
r2 = requests.get('https://www.jleague.co/fixtures/',
                  timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
if r2.status_code == 200:
    text = r2.text
    print(f'  {len(text)}B')
    # Look for match data in JSON/script tags
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, re.DOTALL)
    import json as j
    for s in scripts[:10]:
        if 'matches' in s[:200] or 'fixtures' in s[:200]:
            print(f'  Script with matches: {len(s)} chars')
            print(f'  First 300: {s[:300]}')

# 3. Try flashscore API
print('\n=== flashscore ===')
r3 = requests.get('https://www.flashscore.com/football/japan/j1-league/',
                  timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
if r3.status_code == 200:
    text = r3.text
    print(f'  {len(text)}B')
    save_path = RAW_DIR / 'debug_flashscore.txt'
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(text[:100000])
    # Check for __NEXT_DATA__
    nd_match = re.search(r'__NEXT_DATA__\s*=\s*({.*?});', text, re.DOTALL)
    if nd_match:
        print(f'  Found __NEXT_DATA__ ({len(nd_match.group(1))} chars)')
        data = json.loads(nd_match.group(1))
        print(f'  Keys: {list(data.keys())}')

# 4. Try a simple Google Sheets export approach - some sites have CSV exports
print('\n=== Other CSV sources ===')
csv_urls = [
    ('footystats', 'https://footystats.org/japan/j1-league/datasets'),
]
for name, url in csv_urls:
    try:
        r4 = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        print(f'{name}: {r4.status_code} ({len(r4.content)}B)')
    except Exception as e:
        print(f'{name}: {e}')
