"""Final test"""
import urllib.request, re

r = urllib.request.urlopen('http://127.0.0.1:5001/wc2026', timeout=15)
html = r.read().decode('utf-8')

opens = len(re.findall(r'<script[^>]*>', html))
closes = len(re.findall(r'</script>', html))
print(f'Script: {opens} open, {closes} close, {"OK" if opens==closes else "MISMATCH!"}')
print(f'State: {r.status} ({len(html)}B)')
print(f'Nav: {"navPills" in html}')
print(f'Refresh: {"refreshOdds" in html}')
print(f'Record: {"recordResult" in html}')
