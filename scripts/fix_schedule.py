"""Fix Group A schedule in all files"""
from pathlib import Path

# 1. Fix generate_wc_odds.py
path1 = Path(__file__).parent.parent / 'scripts' / 'generate_wc_odds.py'
with open(path1, 'r', encoding='utf-8') as f:
    content = f.read()

old = (
    "    # Group A\n"
    "    ('2026-06-11', 'A', 'Mexico', 'South Korea'),\n"
    "    ('2026-06-11', 'A', 'South Africa', 'European Playoff D'),\n"
    "    ('2026-06-16', 'A', 'South Korea', 'European Playoff D'),\n"
    "    ('2026-06-16', 'A', 'Mexico', 'South Africa'),\n"
    "    ('2026-06-21', 'A', 'Mexico', 'European Playoff D'),\n"
    "    ('2026-06-21', 'A', 'South Korea', 'South Africa'),"
)
new = (
    "    # Group A (Mexico, South Korea, South Africa, European Playoff D)\n"
    "    ('2026-06-11', 'A', 'Mexico', 'South Africa'),\n"
    "    ('2026-06-11', 'A', 'South Korea', 'European Playoff D'),\n"
    "    ('2026-06-16', 'A', 'Mexico', 'South Korea'),\n"
    "    ('2026-06-16', 'A', 'South Africa', 'European Playoff D'),\n"
    "    ('2026-06-21', 'A', 'Mexico', 'European Playoff D'),\n"
    "    ('2026-06-21', 'A', 'South Korea', 'South Africa'),"
)
assert old in content, "generate_wc_odds.py: old not found!"
content = content.replace(old, new)
with open(path1, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed generate_wc_odds.py')

# 2. Fix run_wc.py
path2 = Path(__file__).parent.parent / 'run_wc.py'
with open(path2, 'r', encoding='utf-8') as f:
    content = f.read()

old2 = (
    "    # Group A\n"
    "    {'date': '2026-06-11', 'group': 'A', 'home': 'Mexico', 'away': 'South Korea'},\n"
    "    {'date': '2026-06-11', 'group': 'A', 'home': 'South Africa', 'away': 'European Playoff D'},\n"
    "    {'date': '2026-06-16', 'group': 'A', 'home': 'Mexico', 'away': 'South Africa'},\n"
    "    {'date': '2026-06-16', 'group': 'A', 'home': 'South Korea', 'away': 'European Playoff D'},\n"
    "    {'date': '2026-06-21', 'group': 'A', 'home': 'Mexico', 'away': 'European Playoff D'},\n"
    "    {'date': '2026-06-21', 'group': 'A', 'home': 'South Korea', 'away': 'South Africa'},"
)
new2 = (
    "    # Group A (Mexico, South Korea, South Africa, European Playoff D)\n"
    "    {'date': '2026-06-11', 'group': 'A', 'home': 'Mexico', 'away': 'South Africa'},\n"
    "    {'date': '2026-06-11', 'group': 'A', 'home': 'South Korea', 'away': 'European Playoff D'},\n"
    "    {'date': '2026-06-16', 'group': 'A', 'home': 'Mexico', 'away': 'South Korea'},\n"
    "    {'date': '2026-06-16', 'group': 'A', 'home': 'South Africa', 'away': 'European Playoff D'},\n"
    "    {'date': '2026-06-21', 'group': 'A', 'home': 'Mexico', 'away': 'European Playoff D'},\n"
    "    {'date': '2026-06-21', 'group': 'A', 'home': 'South Korea', 'away': 'South Africa'},"
)
assert old2 in content, "run_wc.py: old not found!"
content = content.replace(old2, new2)
with open(path2, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed run_wc.py')
print('Done')
