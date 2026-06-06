"""
Final attempt: Get J1 2026 data
"""
import sys, re, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import pandas as pd

RAW_DIR = Path(__file__).parent.parent / 'data' / 'raw'

# 1. Check flashscore for embedded data
print('=== Flashscore analysis ===')
with open(RAW_DIR / 'debug_flashscore.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# Count various patterns
from collections import Counter
terms = {
    'home team name': r'homeTeamName["\']\s*:\s*["\']([^"\']+)',
    'away team name': r'awayTeamName["\']\s*:\s*["\']([^"\']+)',
    'home score': r'homeScore["\']\s*:\s*(\d+)',
    'away score': r'awayScore["\']\s*:\s*(\d+)',
    'match date': r'startDate["\']\s*:\s*["\']([^"\']+)',
}
for label, pattern in terms.items():
    matches = re.findall(pattern, text)
    print(f'{label}: {len(matches)} matches')
    if matches:
        print(f'  Samples: {matches[:5]}')

# Look for structured JSON match data
json_patterns = [
    r'"homeTeam":\{"id":\d+,"name":"[^"]+',
    r'"id":\d+,"homeTeam":[^}]+"awayTeam"',
    r'"league":\{"id":\d+,"name":"[^"]*J1[^"]*'
]
for pat in json_patterns:
    matches = re.findall(pat, text)
    print(f'JSON match data ({pat[:30]}): {len(matches)}')

# 2. Try the jleague.co data - it might have a JSON API
print('\n=== jleague.co API ===')
api_urls = [
    'https://www.jleague.co/api/competitions?year=2026',
    'https://www.jleague.co/api/fixtures?year=2026&competition=j1',
    'https://www.jleague.co/api/standings?year=2026&competition=j1',
    'https://www.jleague.co/api/clubs?year=2026',
]
headers = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.jleague.co/',
}
for api_url in api_urls:
    try:
        r = requests.get(api_url, timeout=15, headers=headers)
        if r.status_code == 200 and len(r.content) > 50:
            try:
                data = r.json()
                if isinstance(data, list):
                    print(f'[OK] {api_url}: list of {len(data)}')
                    print(f'  First: {json.dumps(data[0])[:200]}')
                elif isinstance(data, dict):
                    print(f'[OK] {api_url}: dict with keys {list(data.keys())[:5]}')
            except:
                print(f'[TXT] {api_url}: {r.text[:200]}')
        else:
            print(f'[NO] {api_url}: {r.status_code} ({len(r.content)}B)')
    except Exception as e:
        print(f'[ERR] {api_url}: {e}')

# 3. Try footballdatabase.com with different approach
print('\n=== footballdatabase ===')
try:
    r = requests.get('https://footballdatabase.com/league-scores-tables/japan-j-league-2026',
                     timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
    if r.status_code == 200:
        text2 = r.text
        # Save for debugging
        with open(RAW_DIR / 'debug_fdb.txt', 'w', encoding='utf-8') as f:
            f.write(text2[:100000])
        # Look for team names and scores  
        teams = re.findall(r'class="[^"]*team[^"]*"[^>]*>([^<]+)', text2)
        print(f'Teams found: {len(teams)}')
        if teams:
            print(f'  First 20: {teams[:20]}')
    else:
        print(f'Status: {r.status_code}')
except Exception as e:
    print(f'Error: {e}')
