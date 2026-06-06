"""Test v2 features"""
import urllib.request, json

# 1. Page has tracking tab
html = urllib.request.urlopen('http://127.0.0.1:5001/wc2026').read().decode('utf-8')
terms = ['data-sec="track"', 'id="sec-track"', 'id="resultModal"', '实时追踪', '追踪']
for t in terms:
    print(f'  {t}: {t in html}')

# 2. Stats API  
r = urllib.request.urlopen('http://127.0.0.1:5001/api/wc2026/stats')
data = json.loads(r.read())
print(f'\n  Stats API: {r.status}, total={data["total"]}')

# 3. Matches API
r = urllib.request.urlopen('http://127.0.0.1:5001/api/wc2026/matches')
data = json.loads(r.read())
print(f'  Matches API: {r.status}, count={len(data)}')
print(f'  First: {data[0]["date"]} {data[0]["home_team"]} vs {data[0]["away_team"]}')
