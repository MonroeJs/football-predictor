"""分析 Understat JS 找 API 入口"""
import requests, re

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Get league JS
url = 'https://understat.com/js/league.min.js?t=1765269520'
resp = requests.get(url, headers=headers, timeout=10)
js = resp.text
print(f'JS length: {len(js)}')

# Find URLs in JS
urls = re.findall(r'["\']([^"\']*understat[^"\']*)["\']', js)
for u in set(urls):
    print(f'  Found URL: {u}')

# Find AJAX/fetch patterns
for pattern in ['getJSON', 'ajax', 'fetch', 'loadData', 'getData', 'teamData', 'matchData']:
    idx = js.find(pattern)
    if idx >= 0:
        start = max(0, idx-100)
        end = min(len(js), idx+200)
        print(f'\nFound "{pattern}" at pos {idx}:')
        print(f'  ...{js[start:end]}...')
        print()
