"""Download World Cup historical and current data from football-data.co.uk"""
import requests, csv, io, json
from pathlib import Path

raw_dir = Path(__file__).parent.parent / 'data' / 'raw'
raw_dir.mkdir(parents=True, exist_ok=True)

# 1) Download 2022 WC
r = requests.get('https://www.football-data.co.uk/mmz4281/2223/WC.csv', timeout=30)
with open(raw_dir / 'WC_2022.csv', 'wb') as f:
    f.write(r.content)
print(f'WC_2022.csv: {len(r.content)} bytes, {len(r.text.splitlines())} rows')

# 2) Try 2014 and 2018 with different codes
wc_urls = [
    ('https://www.football-data.co.uk/mmz4281/1415/WC.csv', 'WC_2014.csv'),
    ('https://www.football-data.co.uk/mmz4281/1819/WC.csv', 'WC_2018.csv'),
    ('https://www.football-data.co.uk/mmz4281/1422/WC.csv', 'WC_2014a.csv'),
    ('https://www.football-data.co.uk/mmz4281/1822/WC.csv', 'WC_2018a.csv'),
]
for url, name in wc_urls:
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(raw_dir / name, 'wb') as f:
                f.write(r.content)
            print(f'{name}: {len(r.content)} bytes, {len(r.text.splitlines())} rows')
        else:
            print(f'{name}: status={r.status_code}')
    except Exception as e:
        print(f'{name}: ERROR {e}')

# 3) Check fixtures for 2026 WC matches
r = requests.get('https://www.football-data.co.uk/fixtures.csv', timeout=30)
text = r.content.decode('utf-8-sig')
reader = csv.DictReader(io.StringIO(text))
wc_fixtures = [row for row in reader if row.get('Div','').startswith('WC')]
print(f'\n2026 WC fixtures in fixtures.csv: {len(wc_fixtures)}')
if wc_fixtures:
    for f in wc_fixtures[:5]:
        dt = f.get('Date','?')
        ht = f.get('HomeTeam','?')
        at = f.get('AwayTeam','?')
        h = f.get('B365H','?')
        d = f.get('B365D','?')
        a = f.get('B365A','?')
        print(f'  {dt} {ht} vs {at}  H={h} D={d} A={a}')
    with open(raw_dir / 'WC_2026_fixtures.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=reader.fieldnames)
        w.writeheader()
        w.writerows(wc_fixtures)
    print(f'Saved {len(wc_fixtures)} fixtures')

# 4) Check mmz4281/2526 for live WC data
try:
    r = requests.get('https://www.football-data.co.uk/mmz4281/2526/WC.csv', timeout=15)
    if r.status_code == 200:
        with open(raw_dir / 'WC_2026_live.csv', 'wb') as f:
            f.write(r.content)
        print(f'WC_2026_live.csv: {len(r.content)} bytes, {len(r.text.splitlines())} rows')
    else:
        print(f'WC_2526 live: {r.status_code}')
except Exception as e:
    print(f'WC_2526 live: ERROR {e}')

print('\nDone downloading WC data')
