"""测试 Understat 数据获取"""
import requests, json, re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Try Understat league page
url = 'https://understat.com/league/EPL/2025'
resp = requests.get(url, headers=headers, timeout=10)
print(f'Status: {resp.status_code}, Length: {len(resp.text)}')

# Check for embedded JSON data
# Understat embeds data like: var teamsData = JSON.parse('...');
patterns = ['teamsData', 'datesData', 'playersData', 'matchesData', 'statsData', 'stats']
for p in patterns:
    count = resp.text.count(p)
    if count > 0:
        print(f'  Found "{p}": {count} times')

# Try to extract JSON data
match = re.search(r"var (teamsData|datesData)\s*=\s*JSON\.parse\('([^']+)'\)", resp.text)
if match:
    var_name = match.group(1)
    json_str = match.group(2).encode().decode('unicode_escape')
    data = json.loads(json_str)
    print(f'\n{var_name}: {type(data).__name__}')
    if isinstance(data, dict):
        print(f'  Keys count: {len(data)}')
        first_key = list(data.keys())[0]
        print(f'  First key: {first_key}')
        print(f'  First value keys: {list(data[first_key].keys())[:5]}')
else:
    # Try other patterns
    # Understat puts data in script tags
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, 'html.parser')
    scripts = soup.find_all('script')
    print(f'\nScript tags: {len(scripts)}')
    for i, s in enumerate(scripts):
        text = s.string or ''
        if len(text) > 100 and ('JSON' in text or 'teamsData' in text or 'match' in text.lower()):
            print(f'\nScript #{i} ({len(text)} chars):')
            print(text[:300])
            print('...')
            break
    
    # Try API endpoints
    api_urls = [
        'https://understat.com/league/EPL/2025?ajax=1',
        'https://understat.com/league/EPL',
        'https://api.understat.com/v1/league/EPL/2025',
    ]
    for api_url in api_urls:
        try:
            r = requests.get(api_url, headers=headers, timeout=5)
            print(f'\nAPI {api_url}: Status={r.status_code}, Length={len(r.text)}')
            if r.status_code == 200 and len(r.text) < 10000:
                print(f'  Content: {r.text[:200]}')
        except Exception as e:
            print(f'\nAPI {api_url}: Error: {e}')
