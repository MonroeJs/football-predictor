"""Debug tracking condition"""
import sys; sys.path.insert(0,'.')
from app import app

with app.test_client() as c:
    r = c.get('/wc2026')
    html = r.data.decode('utf-8')

# Find tracking tab area
idx = html.find('data-sec="track"')
if idx > 0:
    start = max(0, idx - 300)
    end = min(len(html), idx + 100)
    print('=== Around tracking tab ===')
    print(html[start:end])

# Check for league.key text
if 'league.key' in html:
    print('\n=== league.key found ===')
    idx2 = html.find('league.key')
    print(html[max(0, idx2-50):idx2+50])

# Check if the sec-track section exists anywhere
if 'sec-track' in html:
    print('\n=== sec-track found ===')
    idx3 = html.find('sec-track')
    print(html[max(0, idx3-200):idx3+200])
else:
    print('\n=== sec-track NOT FOUND ===')

# Check for Jinja2 artifacts
for term in ['{%', '%}', '{{', '}}']:
    if term in html:
        print(f'\nJinja2 artifact "{term}" found in rendered HTML!')
