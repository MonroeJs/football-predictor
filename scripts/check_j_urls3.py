"""Find J-League data URLs"""
import requests, re

# Get raw HTML from japan.php
r = requests.get('https://www.football-data.co.uk/japan.php', timeout=15)
html = r.text
print(f'Page size: {len(html)} bytes')

# Find ALL links
links = re.findall(r'href="([^"]*)"', html)
csv_links = [l for l in links if '.csv' in l.lower()]
print(f'CSV links: {csv_links}')

# Find Japan-specific data files  
j_links = [l for l in links if 'j' in l.lower() or 'J' in l]
print(f'\nJapan-related links: {j_links[:20]}')

# Try to find J-League data in the "new" directory
for path in ['/new/JP.csv', '/new/J1.csv', '/japan/J1.csv']:
    url = f'https://www.football-data.co.uk{path}'
    r2 = requests.get(url, timeout=10)
    print(f'\n{url}: {r2.status_code} ({len(r2.content)}B)')
    if r2.status_code == 200 and len(r2.content) > 500:
        print(f'  First: {r2.text.split(chr(10))[0][:120]}')
