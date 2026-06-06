"""Check J-League URLs"""
import requests, re

# First, get the raw HTML from japan.php page
url = 'https://www.football-data.co.uk/japan.php'
r = requests.get(url, timeout=15)
html = r.text
links = re.findall(r'href=["\']([^"\']*\.csv)["\']', html)
print('CSV links on japan.php:')
for l in links:
    print(f'  {l}')

# Try to construct full URL
if links:
    test_url = links[0]
    if test_url.startswith('http'):
        r2 = requests.get(test_url, timeout=10)
        print(f'\nTest download {test_url}: {r2.status_code} ({len(r2.content)}B)')
        if r2.status_code == 200 and len(r2.content) > 100:
            print(f'  First line: {r2.text.split(chr(10))[0][:120]}')
