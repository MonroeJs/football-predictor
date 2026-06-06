"""Verify all three fixes"""
import urllib.request, json

r = urllib.request.urlopen('http://127.0.0.1:5000/api/predictions', timeout=5)
data = json.loads(r.read())

# 1. Check Group A opener is Mexico vs South Africa
print('=== Group A matches (fix: opener should be Mexico vs South Africa) ===')
for p in data:
    if p.get('group') == 'A':
        d = p['date'][5:10] if len(p.get('date',''))>=10 else '??-??'
        stake = p.get('suggested_stake', 0)
        print(f'  {d} {p["home"]:20s} vs {p["away"]:20s}  {p["tier"]:7s}  {p["confidence"]:>5s}  {stake:.0f}')

print()

# 2. Check stakes are in yuan amounts
print('=== All recommended bets (fix: stakes should be 30/50/80) ===')
for p in data:
    s = p.get('suggested_stake', 0)
    if s > 0:
        d = p['date'][5:10] if len(p.get('date',''))>=10 else '??-??'
        g = p.get('group','?')
        h = p['home'][:16]
        a = p['away'][:16]
        t = p['tier']
        print(f'  {d} [{g}] {h:16s} vs {a:16s}  {t:>6s}  {s:.0f}')

print()
print(f'Total predictions: {len(data)}')
print(f'Recommended bets: {sum(1 for p in data if p.get("suggested_stake",0) > 0)}')

# 3. Check the page has legend
r2 = urllib.request.urlopen('http://127.0.0.1:5000/', timeout=5)
html = r2.read().decode('utf-8')
checks = {
    '分级含义': 'Tier legend',
    'VHigh': 'VHigh tier',
    '置信度': 'Confidence text',
    '30¥': '30 yuan stake',
    '50¥': '50 yuan stake',
    '80¥': '80 yuan stake',
    '建议(¥)': 'Column header with yuan',
}
for text, label in checks.items():
    status = 'OK' if text in html else 'MISSING'
    print(f'  {status}: {label} ({text})')
