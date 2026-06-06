"""Check J1 odds availability by month"""
import sys; sys.path.insert(0, '.')
from src.leagues.j_league import JLeague

league = JLeague()
df = league.load_matches()

# Check odds by month in latest season
seasons = sorted(df['season'].unique())
sdf = df[df['season'] == seasons[-1]].copy()
sdf['month'] = sdf['date'].dt.month

print('Matches with odds by month (latest season):')
odds_by_month = sdf.groupby('month').agg(
    total=('B365H', 'count'),
    with_odds=('B365H', lambda x: x.notna().sum())
)
print(odds_by_month)

print(f'\nTotal with odds: {sdf["B365H"].notna().sum()} / {len(sdf)}')
print(f'\nMonth range of odds-bearing matches:')
odds_matches = sdf[sdf['B365H'].notna()]
if len(odds_matches) > 0:
    print(f'  {odds_matches["date"].min()} to {odds_matches["date"].max()}')
    print(f'  By month:')
    print(odds_matches.groupby('month').size())
