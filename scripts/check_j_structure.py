"""Check J-League data structure"""
from pathlib import Path
import pandas as pd

path = Path(__file__).parent.parent / 'data' / 'raw' / 'JP_2526.csv'
df = pd.read_csv(path)

print(f'Shape: {df.shape}')
print(f'Columns: {list(df.columns)}')
print()

# Show some data
cols = ['Country', 'League', 'Season', 'Date', 'Home', 'Away', 'HG', 'AG', 'Res']
print('Sample:')
pd.set_option('display.max_columns', None)
print(df[cols].head(10))

# Check odds columns  
odds_cols = [c for c in df.columns if '365' in c or 'B365' in c]
print(f'\nBet365 odds columns: {odds_cols}')
if odds_cols:
    print(df[odds_cols].head())

# Check unique teams
print(f'\nTeams: {sorted(df["Home"].unique())}')
print(f'\nSeasons: {sorted(df["Season"].unique())}')
print(f'\nLeagues: {df["League"].unique()}')

# Results distribution
print(f'\nResult distribution:')
print(df['Res'].value_counts())
