"""Check fixtures for WC data"""
import csv, io, requests

r = requests.get('https://www.football-data.co.uk/fixtures.csv', timeout=15)
text = r.content.decode('utf-8-sig')
reader = csv.DictReader(io.StringIO(text))
divs = set()
int_rows = []
for row in reader:
    divs.add(row.get('Div',''))
    ht = row.get('HomeTeam','').lower()
    at = row.get('AwayTeam','').lower()
    for team in ['france','england','brazil','argentina','spain','germany','portugal','netherlands']:
        if team in ht:
            int_rows.append(row)
            break

print('Unique Div values:', sorted(divs))
print('Potential international matches:', len(int_rows))
for row in int_rows[:5]:
    print(f'  {row["Div"]} {row["Date"]} {row["HomeTeam"]} vs {row["AwayTeam"]}')

# Check 'new' directory
for url in ['https://www.football-data.co.uk/new/WC.csv',
            'https://www.football-data.co.uk/new/EC.csv',
            'https://www.football-data.co.uk/new/INT.csv']:
    try:
        r = requests.get(url, timeout=10)
        print(f'{url}: status={r.status_code}')
        if r.status_code == 200 and len(r.text) > 100:
            lines = r.text.splitlines()
            print(f'  First line: {lines[0][:100]}')
            print(f'  Rows: {len(lines)}')
    except Exception as e:
        print(f'{url}: ERROR {e}')
