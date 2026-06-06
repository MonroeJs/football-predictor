"""
Scrape J1 2026 from jleague.co official site
"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import pandas as pd

RAW_DIR = Path(__file__).parent.parent / 'data' / 'raw'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# 1. Fetch the standings page
print('=== J.League standings page ===')
r = requests.get('https://www.jleague.co/standings/j1/2026/', 
                 timeout=20, headers=headers)
if r.status_code == 200:
    text = r.text
    print(f'Got {len(text)}B')
    with open(RAW_DIR / 'debug_jleague.txt', 'w', encoding='utf-8') as f:
        f.write(text[:200000])
    
    # Look for team data
    teams = re.findall(r'data-club-name=["\']([^"\']+)', text)
    print(f'data-club-name: {len(teams)}')
    if teams:
        print(f'  Teams: {teams[:5]}')
    
    # Find any JSON data
    for script in re.findall(r'<script[^>]*>(.*?)</script>', text, re.DOTALL):
        if 'teams' in script[:500] or 'standings' in script[:500] or 'matches' in script[:500]:
            print(f'  Script with data: {len(script)} chars')
            print(f'  First 300: {script[:300]}')

# 2. Try the fixtures page for match results
print('\n=== J.League fixtures ===')
r2 = requests.get('https://www.jleague.co/fixtures/?competition=j1&year=2026',
                  timeout=20, headers=headers)
if r2.status_code == 200:
    text2 = r2.text
    print(f'Got {len(text2)}B')
    with open(RAW_DIR / 'debug_jleague_fixtures.txt', 'w', encoding='utf-8') as f:
        f.write(text2[:200000])
    
    # Look for match data patterns
    for pattern, label in [
        (r'data-date=["\']([^"\']+)', 'match dates'),
        (r'data-home-team=["\']([^"\']+)', 'home teams'),
        (r'data-away-team=["\']([^"\']+)', 'away teams'),
        (r'data-home-score=["\'](\d+)', 'home scores'),
        (r'data-away-score=["\'](\d+)', 'away scores'),
    ]:
        matches = re.findall(pattern, text2)
        print(f'{label}: {len(matches)} found')
        if matches:
            print(f'  Samples: {matches[:3]}')
    
    # Also check the Next.js JSON
    nd = re.search(r'__NEXT_DATA__\s*=\s*({.*?});', text2, re.DOTALL)
    if nd:
        data = json.loads(nd.group(1))
        # Try to find match data
        print(f'__NEXT_DATA__ keys: {list(data.keys())}')
