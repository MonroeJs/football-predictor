"""批量爬取全部 xG 数据"""
from src.xg_scraper import fetch_all_understat
import time

start = time.time()
result = fetch_all_understat(delay=0.3)
elapsed = time.time() - start

print(f"爬取完成: {elapsed:.0f}s")
total = 0
for league, df in result.items():
    avg_xg_h = df["xg_home"].mean()
    print(f"  {league}: {len(df)} 条 (xG home {avg_xg_h:.2f} avg)")
    total += len(df)
print(f"总计: {total} 条")
