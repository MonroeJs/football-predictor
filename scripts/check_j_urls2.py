"""Find J-League URLs"""
import requests, re

r = requests.get('https://www.football-data.co.uk/mmz4281/2526/J1.csv', 
                 timeout=10, allow_redirects=True)
suggestions = re.findall(r'href="([^"]+\.csv)', r.text)
print('Suggested files:', suggestions[:15])

# Also check the data directory listing
r2 = requests.get('https://www.football-data.co.uk/mmz4281/2526/', 
                  timeout=10)
if r2.status_code == 200:
    files = re.findall(r'href="([^"]+\.csv)', r2.text)
    j_files = [f for f in files if 'J' in f.upper()]
    print(f'\nAll files with J: {j_files}')
    print(f'\nTotal files: {len(files)}')

# Try other Japan codes
for code in ['JP', 'JA', 'JPN', 'JLG', 'JLEAGUE', 'J1L', 'J2L']:
    url = f'https://www.football-data.co.uk/mmz4281/2526/{code}.csv'
    try:
        r3 = requests.get(url, timeout=5)
        if r3.status_code == 200 and len(r3.content) > 500:
            print(f'\nFOUND: {url} - {len(r3.content)}B')
            print(f'  First: {r3.text.split(chr(10))[0][:120]}')
    except:
        pass
