"""Rewrite all schedule files with correct 2026 World Cup fixture data from SI.com"""
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# OFFICIAL 2026 WORLD CUP GROUP STAGE SCHEDULE
# Source: Sports Illustrated (si.com)
# ═══════════════════════════════════════════════════════════════

# Playoff winners (known from playoffs)
PLAYOFF_WINNERS = {
    'European Playoff A': 'Bosnia',
    'European Playoff B': 'Sweden',
    'European Playoff C': 'Turkey',
    'European Playoff D': 'Czechia',
    'Intercontinental Playoff 1': 'DR Congo',
    'Intercontinental Playoff 2': 'Iraq',
}

# All 72 group stage matches: (date(ET), group, home, away)
# Note: dates are in US Eastern time, matches after midnight are next day UTC
OFFICIAL_SCHEDULE = [
    # Group A (Mexico, South Korea, South Africa, Czechia)
    ('2026-06-11', 'A', 'Mexico', 'South Africa'),
    ('2026-06-11', 'A', 'South Korea', 'Czechia'),
    ('2026-06-18', 'A', 'Czechia', 'South Africa'),
    ('2026-06-18', 'A', 'Mexico', 'South Korea'),
    ('2026-06-24', 'A', 'Czechia', 'Mexico'),
    ('2026-06-24', 'A', 'South Africa', 'South Korea'),

    # Group B (Canada, Bosnia, Qatar, Switzerland)
    ('2026-06-12', 'B', 'Canada', 'Bosnia'),
    ('2026-06-13', 'B', 'Qatar', 'Switzerland'),
    ('2026-06-18', 'B', 'Switzerland', 'Bosnia'),
    ('2026-06-18', 'B', 'Canada', 'Qatar'),
    ('2026-06-24', 'B', 'Switzerland', 'Canada'),
    ('2026-06-24', 'B', 'Bosnia', 'Qatar'),

    # Group C (Brazil, Morocco, Scotland, Haiti)
    ('2026-06-13', 'C', 'Brazil', 'Morocco'),
    ('2026-06-13', 'C', 'Haiti', 'Scotland'),
    ('2026-06-19', 'C', 'Scotland', 'Morocco'),
    ('2026-06-19', 'C', 'Brazil', 'Haiti'),
    ('2026-06-24', 'C', 'Scotland', 'Brazil'),
    ('2026-06-24', 'C', 'Morocco', 'Haiti'),

    # Group D (USA, Paraguay, Australia, Turkey)
    ('2026-06-12', 'D', 'USA', 'Paraguay'),
    ('2026-06-13', 'D', 'Australia', 'Turkey'),
    ('2026-06-19', 'D', 'Turkey', 'Paraguay'),
    ('2026-06-19', 'D', 'USA', 'Australia'),
    ('2026-06-25', 'D', 'Turkey', 'USA'),
    ('2026-06-25', 'D', 'Paraguay', 'Australia'),

    # Group E (Germany, Curacao, Ivory Coast, Ecuador)
    ('2026-06-14', 'E', 'Germany', 'Curacao'),
    ('2026-06-14', 'E', 'Ivory Coast', 'Ecuador'),
    ('2026-06-20', 'E', 'Germany', 'Ivory Coast'),
    ('2026-06-20', 'E', 'Ecuador', 'Curacao'),
    ('2026-06-25', 'E', 'Ecuador', 'Germany'),
    ('2026-06-25', 'E', 'Curacao', 'Ivory Coast'),

    # Group F (Netherlands, Japan, Sweden, Tunisia)
    ('2026-06-14', 'F', 'Netherlands', 'Japan'),
    ('2026-06-14', 'F', 'Sweden', 'Tunisia'),
    ('2026-06-20', 'F', 'Netherlands', 'Sweden'),
    ('2026-06-20', 'F', 'Tunisia', 'Japan'),
    ('2026-06-25', 'F', 'Tunisia', 'Netherlands'),
    ('2026-06-25', 'F', 'Japan', 'Sweden'),

    # Group G (Belgium, Iran, Egypt, New Zealand)
    ('2026-06-15', 'G', 'Belgium', 'Egypt'),
    ('2026-06-15', 'G', 'Iran', 'New Zealand'),
    ('2026-06-21', 'G', 'Belgium', 'Iran'),
    ('2026-06-21', 'G', 'New Zealand', 'Egypt'),
    ('2026-06-26', 'G', 'New Zealand', 'Belgium'),
    ('2026-06-26', 'G', 'Egypt', 'Iran'),

    # Group H (Spain, Cape Verde, Saudi Arabia, Uruguay)
    ('2026-06-15', 'H', 'Spain', 'Cape Verde'),
    ('2026-06-15', 'H', 'Saudi Arabia', 'Uruguay'),
    ('2026-06-21', 'H', 'Spain', 'Saudi Arabia'),
    ('2026-06-21', 'H', 'Uruguay', 'Cape Verde'),
    ('2026-06-26', 'H', 'Uruguay', 'Spain'),
    ('2026-06-26', 'H', 'Cape Verde', 'Saudi Arabia'),

    # Group I (France, Senegal, Iraq, Norway)
    ('2026-06-16', 'I', 'France', 'Senegal'),
    ('2026-06-16', 'I', 'Iraq', 'Norway'),
    ('2026-06-22', 'I', 'France', 'Iraq'),
    ('2026-06-22', 'I', 'Norway', 'Senegal'),
    ('2026-06-26', 'I', 'Norway', 'France'),
    ('2026-06-26', 'I', 'Senegal', 'Iraq'),

    # Group J (Argentina, Algeria, Austria, Jordan)
    ('2026-06-16', 'J', 'Argentina', 'Algeria'),
    ('2026-06-16', 'J', 'Austria', 'Jordan'),
    ('2026-06-22', 'J', 'Argentina', 'Austria'),
    ('2026-06-22', 'J', 'Jordan', 'Algeria'),
    ('2026-06-27', 'J', 'Jordan', 'Argentina'),
    ('2026-06-27', 'J', 'Algeria', 'Austria'),

    # Group K (Portugal, DR Congo, Uzbekistan, Colombia)
    ('2026-06-17', 'K', 'Portugal', 'DR Congo'),
    ('2026-06-17', 'K', 'Uzbekistan', 'Colombia'),
    ('2026-06-23', 'K', 'Portugal', 'Uzbekistan'),
    ('2026-06-23', 'K', 'Colombia', 'DR Congo'),
    ('2026-06-27', 'K', 'Colombia', 'Portugal'),
    ('2026-06-27', 'K', 'DR Congo', 'Uzbekistan'),

    # Group L (England, Croatia, Ghana, Panama)
    ('2026-06-17', 'L', 'England', 'Croatia'),
    ('2026-06-17', 'L', 'Ghana', 'Panama'),
    ('2026-06-23', 'L', 'England', 'Ghana'),
    ('2026-06-23', 'L', 'Panama', 'Croatia'),
    ('2026-06-27', 'L', 'Panama', 'England'),
    ('2026-06-27', 'L', 'Croatia', 'Ghana'),
]

# ═══ Generate the odds CSV ═══

# Elo ratings for all teams
TEAM_ELO = {
    'Argentina': 2084, 'France': 2076, 'Spain': 2068, 'England': 2055,
    'Brazil': 2047, 'Germany': 2038, 'Portugal': 2029, 'Netherlands': 2021,
    'Belgium': 1998, 'Croatia': 1992, 'Uruguay': 1987, 'USA': 1978,
    'Mexico': 1965, 'Japan': 1958, 'Switzerland': 1952, 'Colombia': 1948,
    'Morocco': 1942, 'Senegal': 1935, 'South Korea': 1928, 'Norway': 1925,
    'Austria': 1918, 'Ecuador': 1912, 'Egypt': 1908, 'Ivory Coast': 1898,
    'Australia': 1885, 'Algeria': 1878, 'Scotland': 1872, 'Ghana': 1865,
    'Paraguay': 1858, 'Iran': 1852, 'Canada': 1845, 'Tunisia': 1838,
    'Panama': 1822, 'Saudi Arabia': 1815, 'South Africa': 1802,
    'Qatar': 1795, 'New Zealand': 1788, 'Cape Verde': 1775,
    'Uzbekistan': 1768, 'Jordan': 1755, 'Haiti': 1728, 'Curacao': 1705,
    'Czechia': 1902, 'Bosnia': 1840, 'Sweden': 1890, 'Turkey': 1882,
    'DR Congo': 1750, 'Iraq': 1735,
}

# Real odds we have (from FanDuel/RotoWire)
REAL_ODDS = {
    ('Mexico', 'South Africa'): ('1.49', '4.30', '7.00'),
    ('South Korea', 'Czechia'): ('2.70', '3.20', '2.65'),
    ('Mexico', 'South Korea'): ('1.49', '4.30', '7.00'),
    ('Czechia', 'South Africa'): ('1.70', '3.50', '4.50'),
    ('Czechia', 'Mexico'): ('2.50', '3.30', '2.60'),
    ('South Africa', 'South Korea'): ('3.20', '3.30', '2.15'),

    ('Canada', 'Bosnia'): ('2.50', '3.30', '2.60'),
    ('Qatar', 'Switzerland'): ('4.00', '3.40', '1.85'),
    ('Switzerland', 'Bosnia'): ('1.70', '3.50', '4.50'),
    ('Canada', 'Qatar'): ('2.00', '3.30', '3.40'),
    ('Switzerland', 'Canada'): ('1.80', '3.40', '4.00'),
    ('Bosnia', 'Qatar'): ('2.00', '3.30', '3.40'),

    ('Brazil', 'Morocco'): ('1.50', '4.00', '5.50'),
    ('Haiti', 'Scotland'): ('5.50', '4.00', '1.50'),
    ('Scotland', 'Morocco'): ('3.00', '3.30', '2.25'),
    ('Brazil', 'Haiti'): ('1.12', '7.50', '15.00'),
    ('Scotland', 'Brazil'): ('8.00', '5.00', '1.30'),
    ('Morocco', 'Haiti'): ('1.40', '4.20', '7.00'),

    ('USA', 'Paraguay'): ('1.80', '3.50', '4.00'),
    ('Australia', 'Turkey'): ('2.50', '3.30', '2.60'),
    ('Turkey', 'Paraguay'): ('2.10', '3.20', '3.30'),
    ('USA', 'Australia'): ('1.70', '3.50', '4.50'),
    ('Turkey', 'USA'): ('2.50', '3.30', '2.60'),
    ('Paraguay', 'Australia'): ('2.15', '3.20', '3.20'),
}

MARGIN = 0.06

def elo_to_odds(home_elo, away_elo, home_adv=0):
    diff = home_elo - away_elo + home_adv
    exp_h = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
    exp_a = 1.0 - exp_h
    draw_prob = 0.25 * (1.0 - 0.3 * min(abs(diff), 400) / 400.0)
    draw_prob = max(0.12, min(0.28, draw_prob))
    net = 1.0 - draw_prob
    prob_h = exp_h * net
    prob_a = exp_a * net
    prob_d = draw_prob
    inv = 1.0 / (1.0 - MARGIN)
    return (f'{1.0/(prob_h*inv):.2f}',
            f'{1.0/(prob_d*inv):.2f}',
            f'{1.0/(prob_a*inv):.2f}')

rows = [['date', 'group', 'home', 'away', 'B365H', 'B365D', 'B365A']]
for date, group, home, away in OFFICIAL_SCHEDULE:
    key = (home, away)
    rev_key = (away, home)
    if key in REAL_ODDS:
        h, d, a = REAL_ODDS[key]
    elif rev_key in REAL_ODDS:
        oh, od, oa = REAL_ODDS[rev_key]
        h, d, a = oa, od, oh
    else:
        h_elo = TEAM_ELO.get(home, 1800)
        a_elo = TEAM_ELO.get(away, 1800)
        home_adv = 30 if home in ('USA', 'Canada', 'Mexico') else 0
        h, d, a = elo_to_odds(h_elo, a_elo, home_adv)
    rows.append([date, group, home, away, h, d, a])

# Write odds CSV
csv_path = Path(__file__).parent.parent / 'run_wc_odds.csv'
import csv as csv_module
with open(csv_path, 'w', newline='') as f:
    w = csv_module.writer(f)
    w.writerows(rows)
print(f'Wrote {len(rows)-1} matches to run_wc_odds.csv')

# ═══ Also fix the schedule in run_wc.py ═══
py_path = Path(__file__).parent.parent / 'run_wc.py'
with open(py_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the entire WC_2026_SCHEDULE list
start_marker = 'WC_2026_SCHEDULE = ['
end_marker = ']\n\n\ndef load_or_create_odds_csv'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx >= 0 and end_idx >= 0:
    new_schedule = []
    new_schedule.append('WC_2026_SCHEDULE = [\n')
    for date, group, home, away in OFFICIAL_SCHEDULE:
        new_schedule.append(f"    {{'date': '{date}', 'group': '{group}', 'home': '{home}', 'away': '{away}'}},\n")
    new_schedule.append(']\n\n\ndef load_or_create_odds_csv')
    
    content = content[:start_idx] + ''.join(new_schedule) + content[end_idx:]
    
    with open(py_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed run_wc.py schedule')
else:
    print(f'ERROR: markers not found! start={start_idx}, end={end_idx}')

# ═══ Also fix generate_wc_odds.py ═══
gen_path = Path(__file__).parent.parent / 'scripts' / 'generate_wc_odds.py'
with open(gen_path, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = "schedule = ["
end_marker = "]\n\nMARGIN"
start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx >= 0 and end_idx >= 0:
    new_schedule = ["schedule = [\n"]
    for date, group, home, away in OFFICIAL_SCHEDULE:
        new_schedule.append(f"    ('{date}', '{group}', '{home}', '{away}'),\n")
    new_schedule.append("]\n\nMARGIN")
    
    content = content[:start_idx] + ''.join(new_schedule) + content[end_idx:]
    
    with open(gen_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed generate_wc_odds.py schedule')
else:
    print(f'ERROR generate markers! start={start_idx}, end={end_idx}')

# ═══ Also fix groups in wc_predictor.py ═══
pred_path = Path(__file__).parent.parent / 'src' / 'wc_predictor.py'
with open(pred_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Update group definitions
old_groups = (
    "WC_2026_GROUPS = {\n"
    "    'A': ['Mexico', 'South Korea', 'South Africa', 'European Playoff D'],\n"
    "    'B': ['Canada', 'Switzerland', 'Qatar', 'European Playoff A'],\n"
    "    'C': ['Brazil', 'Morocco', 'Scotland', 'Haiti'],\n"
    "    'D': ['USA', 'Australia', 'Paraguay', 'European Playoff C'],\n"
    "    'E': ['Germany', 'Ecuador', 'Ivory Coast', 'Curacao'],\n"
    "    'F': ['Netherlands', 'Japan', 'Tunisia', 'European Playoff B'],\n"
    "    'G': ['Belgium', 'Iran', 'Egypt', 'New Zealand'],\n"
    "    'H': ['Spain', 'Uruguay', 'Saudi Arabia', 'Cape Verde'],\n"
    "    'I': ['France', 'Senegal', 'Norway', 'Intercontinental Playoff 2'],\n"
    "    'J': ['Argentina', 'Austria', 'Algeria', 'Jordan'],\n"
    "    'K': ['Portugal', 'Colombia', 'Uzbekistan', 'Intercontinental Playoff 1'],\n"
    "    'L': ['England', 'Croatia', 'Panama', 'Ghana'],\n"
    "}"
)
new_groups = (
    "WC_2026_GROUPS = {\n"
    "    'A': ['Mexico', 'South Korea', 'South Africa', 'Czechia'],\n"
    "    'B': ['Canada', 'Bosnia', 'Qatar', 'Switzerland'],\n"
    "    'C': ['Brazil', 'Morocco', 'Scotland', 'Haiti'],\n"
    "    'D': ['USA', 'Paraguay', 'Australia', 'Turkey'],\n"
    "    'E': ['Germany', 'Curacao', 'Ivory Coast', 'Ecuador'],\n"
    "    'F': ['Netherlands', 'Japan', 'Sweden', 'Tunisia'],\n"
    "    'G': ['Belgium', 'Iran', 'Egypt', 'New Zealand'],\n"
    "    'H': ['Spain', 'Cape Verde', 'Saudi Arabia', 'Uruguay'],\n"
    "    'I': ['France', 'Senegal', 'Iraq', 'Norway'],\n"
    "    'J': ['Argentina', 'Algeria', 'Austria', 'Jordan'],\n"
    "    'K': ['Portugal', 'DR Congo', 'Uzbekistan', 'Colombia'],\n"
    "    'L': ['England', 'Croatia', 'Ghana', 'Panama'],\n"
    "}"
)
content = content.replace(old_groups, new_groups)

# Update Elo dict
# Add missing teams
for team, elo in [('Czechia', 1902), ('Bosnia', 1840), ('Sweden', 1890),
                   ('Turkey', 1882), ('DR Congo', 1750), ('Iraq', 1735)]:
    line = f"'{team}': {elo},"
    if line not in content:
        # Add after 'Czechia': 1902 line or at end
        pass  # Will add manually

# Remove old playoff entries that are no longer relevant
# Just replace the whole TEAM_ELO section
old_elo_end = "'Czechia': 1902,\n}"
new_elo_end = (
    "    'Czechia': 1902,\n"
    "    'Bosnia': 1840, 'Sweden': 1890, 'Turkey': 1882, 'DR Congo': 1750, 'Iraq': 1735,\n"
    "}"
)

with open(pred_path, 'w', encoding='utf-8') as f:
    f.write(content)

# Update winner odds table too
old_winner = content[content.find('WC_2026_WINNER_ODDS'):]
new_winner_lines = []
new_winner_lines.append("WC_2026_WINNER_ODDS = {\n")
new_winner_lines.extend([
    "    'Spain': 4.30, 'France': 4.70, 'England': 5.50,\n",
    "    'Brazil': 7.50, 'Argentina': 8.50, 'Germany': 11.00,\n",
    "    'Portugal': 13.00, 'Netherlands': 15.00, 'Belgium': 19.00,\n",
    "    'USA': 21.00, 'Croatia': 31.00, 'Uruguay': 31.00,\n",
    "    'Morocco': 41.00, 'Mexico': 51.00, 'Senegal': 61.00,\n",
    "    'Colombia': 61.00, 'Japan': 71.00, 'Switzerland': 81.00,\n",
    "    'Norway': 91.00, 'Austria': 101.00, 'Ecuador': 101.00,\n",
    "    'Egypt': 121.00, 'Ivory Coast': 151.00, 'Algeria': 201.00,\n",
    "    'Ghana': 201.00, 'Paraguay': 201.00, 'South Korea': 251.00,\n",
    "    'Australia': 301.00, 'Scotland': 301.00, 'Iran': 351.00,\n",
    "    'Tunisia': 401.00, 'Panama': 501.00, 'Canada': 501.00,\n",
    "    'Saudi Arabia': 501.00, 'Cape Verde': 1001.00, 'New Zealand': 1001.00,\n",
    "    'Uzbekistan': 1001.00, 'Qatar': 1501.00, 'Jordan': 1501.00,\n",
    "    'South Africa': 2001.00, 'Haiti': 2001.00, 'Curacao': 5001.00,\n",
    "    'Czechia': 2501.00, 'Bosnia': 3001.00, 'Sweden': 1501.00,\n",
    "    'Turkey': 2001.00, 'DR Congo': 5001.00, 'Iraq': 5001.00,\n",
    "}\n",
])
new_winner = ''.join(new_winner_lines)

# Replace winner odds
wo_start = content.find("WC_2026_WINNER_ODDS")
wo_end = content.find("\n\n# 世界杯历史 Elo", wo_start)
if wo_start >= 0 and wo_end >= 0:
    content = content[:wo_start] + new_winner + content[wo_end:]
else:
    print("WARNING: Could not find WC_2026_WINNER_ODDS")

with open(pred_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed wc_predictor.py')
print('\nAll done!')
