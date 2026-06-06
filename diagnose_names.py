"""
诊断：找出两个数据源中不匹配的球队名
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

import pandas as pd
from src.data_loader import download_league_data, standardize_dataframe
from src.xg_scraper import fetch_xg_from_understat

raw = download_league_data("EPL")
std = standardize_dataframe(raw)
fdb_teams = set(std["home_team"].unique()) | set(std["away_team"].unique())

xg = fetch_xg_from_understat("EPL", 2025)
us_teams = set(xg["home_team"].unique()) | set(xg["away_team"].unique())

print("football-data teams:", sorted(fdb_teams))
print()
print("Understat teams:", sorted(us_teams))
print()

def norm(n):
    return n.lower().replace(" ", "").replace("-", "").replace("'", "").replace("&", "")

fdb_norm = {norm(t): t for t in fdb_teams}
us_norm = {norm(t): t for t in us_teams}

matched = set(fdb_norm.keys()) & set(us_norm.keys())
unmatched_fdb = set(fdb_norm.keys()) - set(us_norm.keys())
unmatched_us = set(us_norm.keys()) - set(fdb_norm.keys())

print(f"Matched: {len(matched)}")
print(f"Unmatched FDB: {len(unmatched_fdb)}")
for n in sorted(unmatched_fdb):
    print(f"  FDB: {fdb_norm[n]}")
print(f"Unmatched US: {len(unmatched_us)}")
for n in sorted(unmatched_us):
    print(f"  US: {us_norm[n]}")
