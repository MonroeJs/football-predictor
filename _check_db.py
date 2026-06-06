import sqlite3
conn = sqlite3.connect('data/worldcup.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print('Tables:', tables)
for t in tables:
    cur.execute(f'PRAGMA table_info({t[0]})')
    cols = cur.fetchall()
    print(f'\n{t[0]} columns: {[c[1] for c in cols]}')
    cur.execute(f'SELECT * FROM {t[0]} LIMIT 5')
    rows = cur.fetchall()
    for r in rows:
        print(f'  {r}')
conn.close()
