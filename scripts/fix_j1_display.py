"""Fix J1 display: warn about data lag, show all matches"""
from pathlib import Path

path = Path(__file__).parent.parent / 'src' / 'leagues' / 'j_league.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add odds availability note to get_predictions - before the fallback section
old = (
    "        # Fallback: odds-based (same as WC)\n"
    "        from src.betting_system import get_confidence_tier\n"
    "        df_odds = df[df['B365H'].notna()].tail(20)"
)
new = (
    "        # Fallback: odds-based (same as WC)\n"
    "        from src.betting_system import get_confidence_tier\n"
    "        # Note: /new/JP.csv only has Bet365 odds for recent months\n"
    "        # Earlier matches without odds are shown without betting recommendation\n"
    "        df_odds = df[df['B365H'].notna()].tail(20)"
)
if old in content:
    content = content.replace(old, new)
else:
    print('WARNING: old text not found!')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

# Also add a note to get_predictions result
# Show all recent matches, not just those with odds
old2 = "results = []\n        for _, row in df_odds.iterrows():"
new2 = (
    "results = []\n"
    "        # Show last 20 matches total (with or without odds)\n"
    "        for _, row in df.tail(40).iterrows():\n"
    "            has_odds = pd.notna(row.get('B365H'))\n"
    "            if has_odds:\n"
    "                odds = {'H': row['B365H'], 'D': row['B365D'], 'A': row['B365A']}\n"
    "                total = sum(1.0/max(o, 1.01) for o in odds.values())\n"
    "                probs = {k: (1.0/max(odds[k], 1.01))/total for k in odds}\n"
    "                max_outcome = max(probs, key=probs.get)\n"
    "                max_prob = probs[max_outcome]\n"
    "                tier = get_confidence_tier(max_prob)\n"
    "                stake = 30 if tier.value in ('VHigh',) else (50 if tier.value == 'Elite' else (80 if tier.value == 'Max' else 0))\n"
    "            else:\n"
    "                max_outcome = ''\n"
    "                max_prob = 0\n"
    "                tier = type('t',(),{'value':'Low'})()\n"
    "                stake = 0\n"
    "            \n"
    "            results.append({\n"
    "                'date': str(row['date'].date()) if pd.notna(row['date']) else '',\n"
    "                'home': row['home_team'],\n"
    "                'away': row['away_team'],\n"
    "                'home_team': row['home_team'],\n"
    "                'away_team': row['away_team'],\n"
    "                'predicted_outcome': max_outcome,\n"
    "                'confidence': f'{max_prob:.1%}' if max_prob > 0 else 'N/A',\n"
    "                'tier': tier.value,\n"
    "                'fav_odds': odds[max_outcome] if has_odds else 0,\n"
    "                'suggested_stake': stake,\n"
    "            })"
)

if old2 in content:
    content = content.replace(old2, new2)
    print('Replaced odds-based loop')
else:
    print('WARNING: old loop text not found!')

# Also remove the old loop continuation
# Find and remove the old data.append code that comes after
old_append = (
    "            results.append({\n"
    "                'date': str(row['date'].date()) if pd.notna(row['date']) else '',\n"
    "                'home': row['home_team'],\n"
    "                'away': row['away_team'],\n"
    "                'home_team': row['home_team'],\n"
    "                'away_team': row['away_team'],\n"
    "                'predicted_outcome': max_outcome,\n"
    "                'confidence': f'{max_prob:.1%}',\n"
    "                'tier': tier.value,\n"
    "                'fav_odds': odds[max_outcome],\n"
    "                'suggested_stake': 30 if tier.value in ('VHigh',) else (50 if tier.value == 'Elite' else (80 if tier.value == 'Max' else 0)),\n"
    "            })"
)
if old_append in content:
    content = content.replace(old_append, '')
    print('Removed old append')
else:
    print('WARNING: old append not found (may already be removed)')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('\nDone')
