"""Generate 2026 WC odds CSV using Elo ratings + bookmaker margin"""
import csv, math
from pathlib import Path

# Elo ratings (approximate, May 2026)
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
    'Denmark': 1940, 'Italy': 1932, 'Poland': 1905, 'Ukraine': 1892,
    'Turkey': 1882, 'Slovakia': 1865, 'Romania': 1855,
    'Czechia': 1902, 'Bosnia': 1840, 'Jamaica': 1742,
    'Iraq': 1735, 'Bolivia': 1720, 'Congo': 1750,
}

playoff_resolve = {
    'European Playoff A': ('Italy', 1932),
    'European Playoff B': ('Poland', 1905),
    'European Playoff C': ('Turkey', 1882),
    'European Playoff D': ('Czechia', 1902),
    'Intercontinental Playoff 1': ('Jamaica', 1742),
    'Intercontinental Playoff 2': ('Iraq', 1735),
}

schedule = [
    ('2026-06-11', 'A', 'Mexico', 'South Africa'),
    ('2026-06-11', 'A', 'South Korea', 'Czechia'),
    ('2026-06-18', 'A', 'Czechia', 'South Africa'),
    ('2026-06-18', 'A', 'Mexico', 'South Korea'),
    ('2026-06-24', 'A', 'Czechia', 'Mexico'),
    ('2026-06-24', 'A', 'South Africa', 'South Korea'),
    ('2026-06-12', 'B', 'Canada', 'Bosnia'),
    ('2026-06-13', 'B', 'Qatar', 'Switzerland'),
    ('2026-06-18', 'B', 'Switzerland', 'Bosnia'),
    ('2026-06-18', 'B', 'Canada', 'Qatar'),
    ('2026-06-24', 'B', 'Switzerland', 'Canada'),
    ('2026-06-24', 'B', 'Bosnia', 'Qatar'),
    ('2026-06-13', 'C', 'Brazil', 'Morocco'),
    ('2026-06-13', 'C', 'Haiti', 'Scotland'),
    ('2026-06-19', 'C', 'Scotland', 'Morocco'),
    ('2026-06-19', 'C', 'Brazil', 'Haiti'),
    ('2026-06-24', 'C', 'Scotland', 'Brazil'),
    ('2026-06-24', 'C', 'Morocco', 'Haiti'),
    ('2026-06-12', 'D', 'USA', 'Paraguay'),
    ('2026-06-13', 'D', 'Australia', 'Turkey'),
    ('2026-06-19', 'D', 'Turkey', 'Paraguay'),
    ('2026-06-19', 'D', 'USA', 'Australia'),
    ('2026-06-25', 'D', 'Turkey', 'USA'),
    ('2026-06-25', 'D', 'Paraguay', 'Australia'),
    ('2026-06-14', 'E', 'Germany', 'Curacao'),
    ('2026-06-14', 'E', 'Ivory Coast', 'Ecuador'),
    ('2026-06-20', 'E', 'Germany', 'Ivory Coast'),
    ('2026-06-20', 'E', 'Ecuador', 'Curacao'),
    ('2026-06-25', 'E', 'Ecuador', 'Germany'),
    ('2026-06-25', 'E', 'Curacao', 'Ivory Coast'),
    ('2026-06-14', 'F', 'Netherlands', 'Japan'),
    ('2026-06-14', 'F', 'Sweden', 'Tunisia'),
    ('2026-06-20', 'F', 'Netherlands', 'Sweden'),
    ('2026-06-20', 'F', 'Tunisia', 'Japan'),
    ('2026-06-25', 'F', 'Tunisia', 'Netherlands'),
    ('2026-06-25', 'F', 'Japan', 'Sweden'),
    ('2026-06-15', 'G', 'Belgium', 'Egypt'),
    ('2026-06-15', 'G', 'Iran', 'New Zealand'),
    ('2026-06-21', 'G', 'Belgium', 'Iran'),
    ('2026-06-21', 'G', 'New Zealand', 'Egypt'),
    ('2026-06-26', 'G', 'New Zealand', 'Belgium'),
    ('2026-06-26', 'G', 'Egypt', 'Iran'),
    ('2026-06-15', 'H', 'Spain', 'Cape Verde'),
    ('2026-06-15', 'H', 'Saudi Arabia', 'Uruguay'),
    ('2026-06-21', 'H', 'Spain', 'Saudi Arabia'),
    ('2026-06-21', 'H', 'Uruguay', 'Cape Verde'),
    ('2026-06-26', 'H', 'Uruguay', 'Spain'),
    ('2026-06-26', 'H', 'Cape Verde', 'Saudi Arabia'),
    ('2026-06-16', 'I', 'France', 'Senegal'),
    ('2026-06-16', 'I', 'Iraq', 'Norway'),
    ('2026-06-22', 'I', 'France', 'Iraq'),
    ('2026-06-22', 'I', 'Norway', 'Senegal'),
    ('2026-06-26', 'I', 'Norway', 'France'),
    ('2026-06-26', 'I', 'Senegal', 'Iraq'),
    ('2026-06-16', 'J', 'Argentina', 'Algeria'),
    ('2026-06-16', 'J', 'Austria', 'Jordan'),
    ('2026-06-22', 'J', 'Argentina', 'Austria'),
    ('2026-06-22', 'J', 'Jordan', 'Algeria'),
    ('2026-06-27', 'J', 'Jordan', 'Argentina'),
    ('2026-06-27', 'J', 'Algeria', 'Austria'),
    ('2026-06-17', 'K', 'Portugal', 'DR Congo'),
    ('2026-06-17', 'K', 'Uzbekistan', 'Colombia'),
    ('2026-06-23', 'K', 'Portugal', 'Uzbekistan'),
    ('2026-06-23', 'K', 'Colombia', 'DR Congo'),
    ('2026-06-27', 'K', 'Colombia', 'Portugal'),
    ('2026-06-27', 'K', 'DR Congo', 'Uzbekistan'),
    ('2026-06-17', 'L', 'England', 'Croatia'),
    ('2026-06-17', 'L', 'Ghana', 'Panama'),
    ('2026-06-23', 'L', 'England', 'Ghana'),
    ('2026-06-23', 'L', 'Panama', 'Croatia'),
    ('2026-06-27', 'L', 'Panama', 'England'),
    ('2026-06-27', 'L', 'Croatia', 'Ghana'),
]

MARGIN]

MARGIN = 0.06  # 6% bookmaker overround

def elo_to_probs(home_elo, away_elo, home_adv=0):
    """Elo diff -> probabilities"""
    diff = home_elo - away_elo + home_adv
    exp_h = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
    exp_a = 1.0 - exp_h
    draw_prob = 0.25 * (1.0 - 0.3 * min(abs(diff), 400) / 400.0)
    draw_prob = max(0.12, min(0.28, draw_prob))
    net = 1.0 - draw_prob
    prob_h = exp_h * net
    prob_a = exp_a * net
    prob_d = draw_prob
    # Add bookmaker margin
    inv = 1.0 / (1.0 - MARGIN)
    return prob_h * inv, prob_d * inv, prob_a * inv

def resolve(name):
    if name in TEAM_ELO:
        return name, TEAM_ELO[name]
    if name in playoff_resolve:
        return playoff_resolve[name]
    return name, 1800

rows = [['date', 'group', 'home', 'away', 'B365H', 'B365D', 'B365A']]
for date, group, home, away in schedule:
    h_name, h_elo = resolve(home)
    a_name, a_elo = resolve(away)
    home_adv = 30 if home in ('USA', 'Canada', 'Mexico') else 0
    ph, pd_, pa = elo_to_probs(h_elo, a_elo, home_adv)
    rows.append([date, group, home, away,
                 f'{1.0/ph:.2f}', f'{1.0/pd_:.2f}', f'{1.0/pa:.2f}'])

csv_path = Path(__file__).parent.parent / 'run_wc_odds.csv'
with open(csv_path, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerows(rows)

print(f'Generated {len(rows)-1} match odds to run_wc_odds.csv')
print()
print('Top matches (Elite+ tier):')
for r in rows[1:]:
    h = float(r[4])
    d = float(r[5])
    a = float(r[6])
    total = 1.0/h + 1.0/d + 1.0/a
    implied = {r[4]: 1.0/h/total, r[5]: 1.0/d/total, r[6]: 1.0/a/total}
    max_implied = max(implied.values())
    tier = 'Low'
    if max_implied >= 0.80: tier = 'Max'
    elif max_implied >= 0.70: tier = 'Elite'
    elif max_implied >= 0.60: tier = 'VHigh'
    elif max_implied >= 0.50: tier = 'High'
    if tier in ('VHigh', 'Elite', 'Max'):
        print(f'  [{r[1]}] {r[2]:20s} vs {r[3]:20s}  '
              f'{h:>6.2f}  {d:>6.2f}  {a:>6.2f}  ({tier}, {max_implied:.0%})')
