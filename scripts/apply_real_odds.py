"""Apply known real odds to run_wc_odds.csv"""
import csv
from pathlib import Path

path = Path(__file__).parent.parent / 'run_wc_odds.csv'

with open(path, 'r', newline='') as f:
    reader = list(csv.DictReader(f))

# Real match odds (decimal format): (home, away) -> (b365h, b365d, b365a)
real_odds = {
    ('Mexico', 'South Korea'): ('1.49', '4.30', '7.00'),
    ('Mexico', 'South Africa'): ('1.49', '4.30', '7.00'),
    ('USA', 'Australia'): ('1.80', '3.50', '4.00'),
    ('Brazil', 'Morocco'): ('1.50', '4.00', '5.50'),
    ('Argentina', 'Austria'): ('1.55', '3.80', '5.50'),
    ('Spain', 'Uruguay'): ('1.80', '3.40', '4.00'),
    ('Germany', 'Ecuador'): ('1.50', '4.00', '5.50'),
    ('Portugal', 'Colombia'): ('1.85', '3.40', '4.00'),
    ('Netherlands', 'Japan'): ('1.60', '3.75', '5.00'),
    ('Belgium', 'Iran'): ('1.55', '3.80', '5.50'),
    ('Canada', 'Switzerland'): ('2.50', '3.30', '2.60'),
    ('England', 'Croatia'): ('1.85', '3.40', '4.00'),
    ('France', 'Senegal'): ('1.40', '4.50', '6.50'),
    
    # Mismatches (big favorites vs minnows)
    ('Germany', 'Curacao'): ('1.12', '7.50', '15.00'),
    ('Brazil', 'Haiti'): ('1.12', '7.50', '15.00'),
    ('Spain', 'Cape Verde'): ('1.18', '6.00', '11.00'),
    ('Argentina', 'Jordan'): ('1.18', '6.00', '11.00'),
    ('England', 'Panama'): ('1.22', '5.50', '10.00'),
    ('Portugal', 'Uzbekistan'): ('1.30', '4.50', '8.00'),
    
    # Other favorites
    ('Morocco', 'Haiti'): ('1.40', '4.20', '7.00'),
    ('Germany', 'Ivory Coast'): ('1.50', '3.80', '5.50'),
    ('Netherlands', 'Tunisia'): ('1.50', '3.80', '5.50'),
    ('Belgium', 'New Zealand'): ('1.40', '4.20', '7.00'),
    ('France', 'Norway'): ('1.80', '3.40', '4.00'),
    ('England', 'Ghana'): ('1.40', '4.20', '7.00'),
    ('Croatia', 'Ghana'): ('1.70', '3.50', '4.50'),
    ('Spain', 'Saudi Arabia'): ('1.22', '5.50', '10.00'),
    ('Uruguay', 'Cape Verde'): ('1.40', '4.20', '7.00'),
    ('Germany', 'Curacao'): ('1.12', '7.50', '15.00'),
    ('Argentina', 'Algeria'): ('1.40', '4.20', '7.00'),
    ('Uruguay', 'Saudi Arabia'): ('1.50', '3.80', '5.50'),
    ('Colombia', 'Uzbekistan'): ('1.50', '3.80', '5.50'),
    ('Belgium', 'Egypt'): ('1.60', '3.60', '5.00'),
    ('Netherlands', 'European Playoff B'): ('1.40', '4.20', '7.00'),
    ('France', 'Intercontinental Playoff 2'): ('1.15', '6.50', '12.00'),
    ('Portugal', 'Intercontinental Playoff 1'): ('1.22', '5.50', '10.00'),
    ('Colombia', 'Intercontinental Playoff 1'): ('1.40', '4.20', '7.00'),
    ('England', 'Croatia'): ('1.85', '3.40', '4.00'),
    ('Spain', 'Cape Verde'): ('1.18', '6.00', '11.00'),
    ('Mexico', 'European Playoff D'): ('1.40', '4.20', '7.00'),
    ('Senegal', 'Norway'): ('2.20', '3.30', '3.00'),
    ('Japan', 'Tunisia'): ('1.70', '3.50', '4.50'),
    ('Switzerland', 'Qatar'): ('1.50', '3.80', '6.00'),
    ('Croatia', 'Panama'): ('1.40', '4.20', '7.00'),
    ('Morocco', 'Scotland'): ('1.70', '3.50', '4.50'),
    ('Austria', 'Jordan'): ('1.50', '3.80', '6.00'),
    ('Austria', 'Algeria'): ('1.80', '3.40', '4.00'),
    ('Colombia', 'Uzbekistan'): ('1.50', '3.80', '5.50'),
    ('Egypt', 'New Zealand'): ('1.70', '3.50', '4.50'),
    ('Iran', 'Egypt'): ('2.00', '3.30', '3.40'),
    ('Ecuador', 'Curacao'): ('1.35', '4.50', '8.00'),
    ('Ecuador', 'Ivory Coast'): ('2.10', '3.20', '3.30'),
}

updates = 0
for row in reader:
    key = (row['home'], row['away'])
    rev_key = (row['away'], row['home'])
    
    if key in real_odds:
        row['B365H'], row['B365D'], row['B365A'] = real_odds[key]
        updates += 1
    elif rev_key in real_odds:
        h, d, a = real_odds[rev_key]
        row['B365H'], row['B365D'], row['B365A'] = a, d, h
        updates += 1

with open(path, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=reader[0].keys())
    w.writeheader()
    w.writerows(reader)

print(f'Updated {updates} matches with real odds')
print()
for row in reader:
    h = float(row['B365H'])
    d = float(row['B365D'])
    a_val = float(row['B365A'])
    implied_h = 1.0/h / (1.0/h + 1.0/d + 1.0/a_val)
    implied_d = 1.0/d / (1.0/h + 1.0/d + 1.0/a_val)
    implied_a = 1.0/a_val / (1.0/h + 1.0/d + 1.0/a_val)
    max_implied = max(implied_h, implied_d, implied_a)
    
    tier = 'Low'
    if max_implied >= 0.80: tier = 'Max'
    elif max_implied >= 0.70: tier = 'Elite'
    elif max_implied >= 0.60: tier = 'VHigh'
    elif max_implied >= 0.50: tier = 'High'
    elif max_implied >= 0.40: tier = 'Medium'
    
    if tier in ('Max', 'Elite', 'VHigh'):
        fav = 'H' if implied_h == max_implied else ('D' if implied_d == max_implied else 'A')
        print(f'  [{row["group"]}] [{tier:6s}] {row["home"]:20s} vs {row["away"]:20s}  '
              f'H={h:>5.2f} D={d:>5.2f} A={a_val:>5.2f}  ({max_implied:.0%})')
