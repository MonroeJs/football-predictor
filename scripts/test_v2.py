"""Test v2 web app"""
import urllib.request, json

r = urllib.request.urlopen('http://127.0.0.1:5000/', timeout=10)
html = r.read().decode('utf-8')
print(f'Main page: {r.status} ({len(html)}B)')

checks = [
    '今日推荐', '全部赛程', '日历视图', '分组出线',
    '分级含义', '数据概览', '历史回测',
    'chartTier', 'chartStakes', 'chartGroups', 'chartScatter',
    'nav-pills-custom', 'hero-stats', 'glass-card',
    'Monte Carlo', 'adv-bar',
]
for term in checks:
    ok = term in html
    print(f'  {ok}: {term}')

# Test APIs
for path in ['/api/stats', '/api/group-probs', '/api/today', '/api/calendar']:
    try:
        r = urllib.request.urlopen(f'http://127.0.0.1:5000{path}', timeout=5)
        data = json.loads(r.read())
        if isinstance(data, dict):
            print(f'  OK: {path} ({len(data)} keys)')
        elif isinstance(data, list):
            print(f'  OK: {path} ({len(data)} items)')
    except Exception as e:
        print(f'  ERR: {path}: {e}')
