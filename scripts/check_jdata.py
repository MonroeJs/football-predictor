"""Check J-League data availability"""
import requests

urls = [
    ('https://www.football-data.co.uk/mmz4281/2526/J1.csv', 'J1 2526'),
    ('https://www.football-data.co.uk/mmz4281/2425/J1.csv', 'J1 2425'),
    ('https://www.football-data.co.uk/mmz4281/2324/J1.csv', 'J1 2324'),
    ('https://www.football-data.co.uk/mmz4281/2223/J1.csv', 'J1 2223'),
    ('https://www.football-data.co.uk/mmz4281/2526/J2.csv', 'J2 2526'),
]

for url, label in urls:
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and len(r.content) > 100:
            lines = r.text.split('\n')
            print(f'OK: {label} - {len(r.content)}B, {len(lines)} rows')
            print(f'  Cols: {lines[0][:150]}')
            # Check columns for B365 odds
            if 'B365H' in lines[0]:
                print('  Has Bet365 odds: YES')
            else:
                print('  Has Bet365 odds: NO')
            print(f'  Sample: {lines[1][:150]}')
        else:
            print(f'NO: {label} - status={r.status_code}')
    except Exception as e:
        print(f'ERR: {label} - {e}')
