"""Clear test data from database"""
import sys; sys.path.insert(0, '.')
from src.database import get_conn

conn = get_conn()
conn.execute("""
    UPDATE matches SET 
        result_confirmed=0, 
        actual_winner='', 
        home_goals=NULL, 
        away_goals=NULL, 
        bet_placed=0, 
        bet_amount=0, 
        bet_profit=0 
    WHERE result_confirmed=1
""")
conn.commit()
affected = conn.total_changes
conn.close()
print(f'Cleared test data ({affected} rows affected)')
