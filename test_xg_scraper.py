"""
测试 xG 爬虫 — 抓取 EPL 一个赛季看看数据质量
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from src.xg_scraper import fetch_xg_for_season, FBREF_LEAGUES

# 只测 EPL 一个赛季，快速看数据
df = fetch_xg_for_season("EPL", "2025-2026", delay=0)

if df is not None:
    print(f"EPL 2025-26: {len(df)} 场比赛")
    print(f"列: {list(df.columns)}")
    print(f"\n前5条:")
    for _, r in df.head(5).iterrows():
        print(f"  {r['home_team']:20s} vs {r['away_team']:20s} "
              f"比分={r['home_goals']}-{r['away_goals']} "
              f"xG={r['xg_home']:.2f}-{r['xg_away']:.2f} "
              f"结果={r['result']}")
    print(f"\nxG 范围: home=[{df['xg_home'].min():.2f}, {df['xg_home'].max():.2f}], "
          f"away=[{df['xg_away'].min():.2f}, {df['xg_away'].max():.2f}]")
else:
    print("xG 爬取失败")

# 再测一个赛季看对比
print("\n--- EPL 2024-2025 ---")
df2 = fetch_xg_for_season("EPL", "2024-2025", delay=0)
if df2 is not None:
    print(f"共 {len(df2)} 场")
    print(f"前3条:")
    for _, r in df2.head(3).iterrows():
        print(f"  {r['home_team']:20s} vs {r['away_team']:20s} "
              f"xG={r['xg_home']:.2f}-{r['xg_away']:.2f} 比分={r['home_goals']}-{r['away_goals']}")
else:
    print("xG 爬取失败")
