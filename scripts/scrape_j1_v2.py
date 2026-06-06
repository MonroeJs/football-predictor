"""
Get 2026 J1 data - try multiple approaches
"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import pandas as pd

RAW_DIR = Path(__file__).parent.parent / 'data' / 'raw'

def save_debug(name, text):
    path = RAW_DIR / f'debug_{name}.txt'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text[:50000])
    print(f'  Saved debug: {path}')

# 1. Flashfootball archive - look for embedded data
print('=== Flashfootball ===')
r = requests.get('https://www.flashfootball.com/japan/j1-league/archive/', 
                 timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
if r.status_code == 200:
    text = r.text
    print(f'Got {len(text)}B')
    save_debug('flashfootball', text)
    
    # Look for various data patterns
    for pattern in [
        r'"homeName":"[^"]+","awayName":"[^"]+"',
        r'"ht":\d+,"at":\d+',
        r'class="[^"]*match[^"]*"[^>]*>',
        r'data-id="\d+"',
        r'score["\']:\s*["\']\d+-\d+',
    ]:
        matches = re.findall(pattern, text)
        print(f'  Pattern "{pattern[:30]}": {len(matches)} matches')
        if matches:
            print(f'    Samples: {matches[:3]}')

# 2. Try flashfootball results page for current season
print('\n=== Flashfootball results ===')
r2 = requests.get('https://www.flashfootball.com/japan/j1-league/results/', 
                  timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
if r2.status_code == 200:
    print(f'Got {len(r2.text)}B')
    save_debug('flashfootball_results', r2.text)
    # Look for match data
    matches = re.findall(r'<a[^>]*href="/japan/j1-league/[^"]*"[^>]*>', r2.text)
    print(f'  Match links: {len(matches)}')

# 3. Try API endpoints
print('\n=== API endpoints ===')
apis = [
    'https://www.flashfootball.com/api/competition/1199/',
    'https://www.flashfootball.com/api/competition/1199/matches/',
    'https://footballapi.flashfootball.com/api/competition/1199/matches/',
]
for api_url in apis:
    try:
        r3 = requests.get(api_url, timeout=10, 
                         headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        print(f'{api_url}: {r3.status_code} ({len(r3.content)}B)')
        if r3.status_code == 200 and r3.headers.get('content-type','').startswith('application/json'):
            data = r3.json()
            if isinstance(data, list):
                print(f'  {len(data)} items')
                if data:
                    print(f'  First: {json.dumps(data[0], indent=2)[:500]}')
    except Exception as e:
        print(f'{api_url}: error - {e}')

# 4. Worldfootball - try different URL
print('\n=== Worldfootball ===')
for path in ['/competition/jpn-j1-league/', '/competition/jpn-j1-league-2026/',
             '/competition/jpn-j1-league/ergebnisse/']:
    try:
        r4 = requests.get(f'https://www.worldfootball.net{path}', 
                         timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        print(f'{path}: {r4.status_code} ({len(r4.content)}B)')
        if r4.status_code == 200:
            save_debug(f'wfb_{path.replace("/","_")}', r4.text)
    except Exception as e:
        print(f'{path}: {e}')
