"""Quick test for new template"""
import sys; sys.path.insert(0,'.')
from wc_app import app

with app.test_client() as c:
    r = c.get('/')
    html = r.data.decode('utf-8')

checks = [
    ('navPills handler', 'navPills'),
    ('chartTier canvas', 'chartTier'),
    ('chartStakes canvas', 'chartStakes'),
    ('Group probs fetch', 'group-probs'),
    ('TIER_CN in context', 'TIER_CN'),
    ('data-sec attribute', 'data-sec'),
    ('section with active', 'sec active'),
    ('Chinese 至尊', '至尊'),
    ('Chinese 精选', '精选'),
    ('Chinese 高信', '高信'),
    ('Chart.js loaded', 'chart.js'),
]
for label, term in checks:
    ok = term in html
    print(f'  {"OK" if ok else "ERR"}: {label}')
print(f'  Page: {r.status_code} ({len(html)}B)')
