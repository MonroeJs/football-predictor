"""Check what J1 predictions look like"""
import sys; sys.path.insert(0, '.')
from src.leagues.j_league import JLeague

league = JLeague()
preds = league.get_predictions()
print(f'Total predictions: {len(preds)}')
print(f'\nDate range: {preds[0]["date"] if preds else "none"} to {preds[-1]["date"] if preds else "none"}')
print(f'\nSample:')
for p in preds[:5]:
    print(f'  {p["date"]} {p["home"][:16]} vs {p["away"][:16]} | tier={p["tier"]} | stake={p["suggested_stake"]}')
print('...')
for p in preds[-3:]:
    print(f'  {p["date"]} {p["home"][:16]} vs {p["away"][:16]} | tier={p["tier"]} | stake={p["suggested_stake"]}')
