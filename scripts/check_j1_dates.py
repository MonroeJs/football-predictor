"""Check J1 date parsing"""
import sys; sys.path.insert(0, '.')
from src.leagues.j_league import JLeague

league = JLeague()
df = league.load_matches()

# Check latest season
seasons = sorted(df['season'].unique())
latest = seasons[-1]
sdf = df[df['season'] == latest]
print(f'Latest season: {latest}, {len(sdf)} matches')
print(f'Date range: {sdf["date"].min()} to {sdf["date"].max()}')
print(f'\nBy month:')
print(sdf['date'].dt.month.value_counts().sort_index())
print(f'\nFirst 5:')
print(sdf[['date','home_team','away_team']].head())
print(f'\nLast 5:')
print(sdf[['date','home_team','away_team']].tail())
