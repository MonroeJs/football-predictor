"""Download and analyze J-League data"""
from pathlib import Path
import requests
import pandas as pd
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

url = 'https://www.football-data.co.uk/new/JP.csv'
r = requests.get(url, timeout=30)
text = r.content.decode('utf-8-sig')  # Handle BOM

# Save to raw
raw_dir = Path(__file__).parent.parent / 'data' / 'raw'
raw_dir.mkdir(parents=True, exist_ok=True)
with open(raw_dir / 'JP_2526.csv', 'w', encoding='utf-8') as f:
    f.write(text)

df = pd.read_csv(raw_dir / 'JP_2526.csv')
print(f'J1 League data loaded')
print(f'Shape: {df.shape}')
print(f'Columns: {list(df.columns)}')
print(f'\nFirst 5 columns: {list(df.columns[:20])}')
print(f'\nSample rows:')
print(df[['Div','Date','HomeTeam','AwayTeam','FTHG','FTAG','FTR','B365H','B365D','B365A']].head())
print(f'\nDivisions: {df["Div"].unique()}')
print(f'\nTeams ({df["HomeTeam"].nunique()}):')
print(sorted(df['HomeTeam'].unique()))
print(f'\nSeasons: {df["season"].unique() if "season" in df.columns else "No season column"}')
