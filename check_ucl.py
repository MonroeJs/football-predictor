"""Check if football-data.co.uk has UCL data"""
import pandas as pd, requests
from io import StringIO

for s in ['2526', '2425', '2324', '2223', '2122', '2021', '1920']:
    for code in ['EC', 'CL', 'UCL', 'E0', 'E1']:
        url = 'https://www.football-data.co.uk/mmz4281/{}/{}'.format(s, code) + '.csv'
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                df = pd.read_csv(StringIO(r.text), nrows=3)
                divs = df['Div'].unique() if 'Div' in df.columns else ['N/A']
                print('{} {}: {} rows, divs={}'.format(s, code, len(df), divs[:3]))
                if 'FTHG' in df.columns:
                    print('  Has results!')
                    print('  HomeTeam,FTHG,FTAG,FTR,AvgH,AvgD,AvgA:', 
                          [c for c in ['HomeTeam','AwayTeam','FTHG','FTAG','FTR','AvgH','AvgD','AvgA','B365H','B365D','B365A'] if c in df.columns])
        except:
            pass
