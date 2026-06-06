"""Show database info"""
import sqlite3
conn = sqlite3.connect('data/worldcup.db')
conn.row_factory = sqlite3.Row

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Tables:', [t['name'] for t in tables])

for table in [t['name'] for t in tables]:
    count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'  {table}: {count} rows')
    
print()
print('Sample matches:')
for row in conn.execute('SELECT id, date, home_team, away_team, tier, result_confirmed, actual_winner FROM matches LIMIT 5'):
    d = dict(row)
    print(f'  {d["id"]:>3d}  {d["date"]}  {d["home_team"][:14]:14s} vs {d["away_team"][:14]:14s}  {str(d["tier"]):>6s}  conf={d["result_confirmed"]}  winner={d["actual_winner"]}')

conn.close()
