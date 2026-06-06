"""Fix team name mapping in squad data"""
import json
from pathlib import Path

TEAM_NAME_MAP = {
    'Bosnia and Herzegovina': 'Bosnia',
    'Curaçao': 'Curacao',
    'Czech Republic': 'Czechia',
    'South Korea': 'South Korea',
}

# Load both files
squads_path = Path(__file__).parent.parent / 'data' / 'wc_squads.json'
ratings_path = Path(__file__).parent.parent / 'data' / 'wc_player_ratings.json'

with open(squads_path, 'r', encoding='utf-8') as f:
    squads = json.load(f)
with open(ratings_path, 'r', encoding='utf-8') as f:
    ratings = json.load(f)

# Map names
mapped_squads = {}
for name, data in squads.items():
    new_name = TEAM_NAME_MAP.get(name, name)
    mapped_squads[new_name] = data

mapped_ratings = {}
for name, data in ratings.items():
    new_name = TEAM_NAME_MAP.get(name, name)
    mapped_ratings[new_name] = data

# Save back
with open(squads_path, 'w', encoding='utf-8') as f:
    json.dump(mapped_squads, f, indent=2, ensure_ascii=False)
with open(ratings_path, 'w', encoding='utf-8') as f:
    json.dump(mapped_ratings, f, indent=2, ensure_ascii=False)

print(f'Squads: {len(mapped_squads)} teams -> {sorted(mapped_squads.keys())[:10]}...')
print(f'Ratings: {len(mapped_ratings)} teams')
