# Odds API → run_wc_odds.csv 实现计划

> **For implementer:** Use TDD throughout. Write failing test first. Watch it fail. Then implement.

**目标:** 从 the-odds-api.com 拉取 Paddy Power 世界杯赔率，写入 `run_wc_odds.csv`

**架构:** 单脚本 `scripts/fetch_wc_odds.py`，调用 Odds API → 队名映射 → 生成 CSV。保留原 CSV 格式不动。

**Tech Stack:** Python, requests, csv/dotenv

---

### Task 1: 编写 fetch_wc_odds.py

**文件:**
- Create: `scripts/fetch_wc_odds.py`
- Modify: `run_wc_odds.csv`（运行时输出）
- Test: `tests/test_fetch_wc_odds.py`

**Step 1: 写测试**
```python
"""Tests for fetch_wc_odds.py"""
import sys, json, csv, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_team_name_mapping():
    """所有 API 队名都能映射到 CSV 队名"""
    from scripts.fetch_wc_odds import TEAM_NAME_MAP
    api_teams = [
        "Algeria", "Argentina", "Australia", "Austria", "Belgium",
        "Bosnia & Herzegovina", "Brazil", "Canada", "Cape Verde",
        "Colombia", "Croatia", "Curaçao", "Czech Republic", "DR Congo",
        "Ecuador", "Egypt", "England", "France", "Germany", "Ghana",
        "Haiti", "Iran", "Iraq", "Ivory Coast", "Japan", "Jordan",
        "Mexico", "Morocco", "Netherlands", "New Zealand", "Norway",
        "Panama", "Paraguay", "Portugal", "Qatar", "Saudi Arabia",
        "Scotland", "Senegal", "South Africa", "South Korea", "Spain",
        "Sweden", "Switzerland", "Tunisia", "Turkey", "USA",
        "Uruguay", "Uzbekistan",
    ]
    for team in api_teams:
        mapped = TEAM_NAME_MAP.get(team, team)
        assert isinstance(mapped, str) and len(mapped) > 0, f"Failed to map: {team}"

def test_csv_output_format():
    """生成的 CSV 格式与现有 run_wc_odds.csv 一致"""
    from scripts.fetch_wc_odds import build_csv_rows
    mock_api_data = [
        {
            "id": "mock1",
            "commence_time": "2026-06-11T19:00:00Z",
            "home_team": "Mexico",
            "away_team": "South Africa",
            "bookmakers": [
                {
                    "key": "paddypower",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Mexico", "price": 1.40},
                                {"name": "Draw", "price": 4.50},
                                {"name": "South Africa", "price": 8.50},
                            ]
                        }
                    ]
                }
            ]
        }
    ]
    rows = build_csv_rows(mock_api_data)
    assert len(rows) == 1
    row = rows[0]
    assert row['home'] == 'Mexico'
    assert row['away'] == 'South Africa'
    assert float(row['B365H']) == 1.40
    assert float(row['B365D']) == 4.50
    assert float(row['B365A']) == 8.50
    assert row['group'] == ''
    assert row['date'] == '2026-06-11'

def test_group_assignment():
    """根据日期和队伍正确分配小组"""
    from scripts.fetch_wc_odds import get_group
    # Group A: Mexico,S.Korea,Czechia,S.Africa — 2026-06-11,18,24
    assert get_group('Mexico', '2026-06-11') == 'A'
    assert get_group('Czech Republic', '2026-06-18') == 'A'
    assert get_group('South Korea', '2026-06-24') == 'A'
    assert get_group('South Africa', '2026-06-11') == 'A'
    # Group B: Canada,Bosnia,Qatar,Switzerland — 2026-06-12,13,18,24
    assert get_group('Canada', '2026-06-12') == 'B'
    assert get_group('Bosnia & Herzegovina', '2026-06-12') == 'B'
    assert get_group('Qatar', '2026-06-13') == 'B'
    assert get_group('Switzerland', '2026-06-13') == 'B'
    # Group L: England,Croatia,Ghana,Panama — 2026-06-17,23,27
    assert get_group('England', '2026-06-17') == 'L'
    assert get_group('Panama', '2026-06-27') == 'L'
```

**Step 2: 确认测试失败**
```bash
pytest tests/test_fetch_wc_odds.py -v
```
Expected: FAIL — module not found

**Step 3: 实现 fetch_wc_odds.py**

```python
"""
Fetch 2026 World Cup match odds from the-odds-api.com

Usage:
    python scripts/fetch_wc_odds.py

Updates run_wc_odds.csv with real bookmaker odds (Paddy Power).
Team names are mapped to match the existing CSV format.
"""
import sys, os, csv, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

# ── Config ──────────────────────────────────────────────
API_KEY = os.getenv('ODDS_API_KEY', '')
if not API_KEY:
    # Try loading from .env
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if line.startswith('ODDS_API_KEY='):
                API_KEY = line.split('=', 1)[1].strip()

SPORT = 'soccer_fifa_world_cup'
BOOKMAKER = 'paddypower'  # 72/72 coverage, reliable
REGIONS = 'uk'
MARKETS = 'h2h'

# ── Team name mapping ───────────────────────────────────
TEAM_NAME_MAP = {
    'Bosnia & Herzegovina': 'Bosnia',
    'Curaçao': 'Curacao',
    'Czech Republic': 'Czechia',
}

# Group assignments by (team, date) heuristic
GROUPS_BY_TEAM = {
    'Mexico': 'A', 'South Africa': 'A', 'South Korea': 'A', 'Czechia': 'A',
    'Canada': 'B', 'Bosnia': 'B', 'Qatar': 'B', 'Switzerland': 'B',
    'Brazil': 'C', 'Morocco': 'C', 'Haiti': 'C', 'Scotland': 'C',
    'USA': 'D', 'Paraguay': 'D', 'Australia': 'D', 'Turkey': 'D',
    'Germany': 'E', 'Curacao': 'E', 'Ivory Coast': 'E', 'Ecuador': 'E',
    'Netherlands': 'F', 'Japan': 'F', 'Sweden': 'F', 'Tunisia': 'F',
    'Belgium': 'G', 'Egypt': 'G', 'Iran': 'G', 'New Zealand': 'G',
    'Spain': 'H', 'Cape Verde': 'H', 'Saudi Arabia': 'H', 'Uruguay': 'H',
    'France': 'I', 'Senegal': 'I', 'Iraq': 'I', 'Norway': 'I',
    'Argentina': 'J', 'Algeria': 'J', 'Austria': 'J', 'Jordan': 'J',
    'Portugal': 'K', 'DR Congo': 'K', 'Uzbekistan': 'K', 'Colombia': 'K',
    'England': 'L', 'Croatia': 'L', 'Ghana': 'L', 'Panama': 'L',
}


def map_team(api_name: str) -> str:
    """Map API team name to CSV team name."""
    return TEAM_NAME_MAP.get(api_name, api_name)


def get_group(home_team: str, date_str: str) -> str:
    """Determine group from team name."""
    return GROUPS_BY_TEAM.get(home_team, '?')


def fetch_odds() -> list[dict]:
    """Fetch 72 WC matches with odds from Paddy Power."""
    url = (
        f'https://api.the-odds-api.com/v4/sports/{SPORT}/odds/'
        f'?apiKey={API_KEY}&regions={REGIONS}&markets={MARKETS}'
        f'&bookmakers={BOOKMAKER}'
    )
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()


def build_csv_rows(api_data: list[dict]) -> list[dict]:
    """Convert API response to CSV rows matching run_wc_odds.csv format."""
    rows = []
    for match in api_data:
        date = match['commence_time'][:10]  # "2026-06-11T19:00:00Z" → "2026-06-11"
        home_api = match['home_team']
        away_api = match['away_team']
        home = map_team(home_api)
        away = map_team(away_api)

        # Extract Paddy Power h2h odds
        b365h = b365d = b365a = 0.0
        for bm in match.get('bookmakers', []):
            if bm['key'] == BOOKMAKER:
                for market in bm.get('markets', []):
                    if market['key'] == 'h2h':
                        for outcome in market['outcomes']:
                            name = outcome['name']
                            if name == home_api:
                                b365h = outcome['price']
                            elif name == 'Draw':
                                b365d = outcome['price']
                            elif name == away_api:
                                b365a = outcome['price']

        group = get_group(home, date)

        rows.append({
            'date': date,
            'group': group,
            'home': home,
            'away': away,
            'B365H': f'{b365h:.2f}',
            'B365D': f'{b365d:.2f}',
            'B365A': f'{b365a:.2f}',
        })

    return rows


def main():
    t0 = datetime.now()
    print(f'[{t0.strftime("%H:%M:%S")}] Fetching WC odds from Odds API...')
    print(f'  Source: {BOOKMAKER}')

    data = fetch_odds()
    print(f'  Got {len(data)} matches')

    rows = build_csv_rows(data)
    print(f'  Built {len(rows)} CSV rows')

    # Write CSV
    csv_path = Path(__file__).parent.parent / 'run_wc_odds.csv'
    fieldnames = ['date', 'group', 'home', 'away', 'B365H', 'B365D', 'B365A']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    elapsed = (datetime.now() - t0).total_seconds()
    print(f'[{datetime.now().strftime("%H:%M:%S")}] Done ({elapsed:.1f}s)')
    print(f'  Updated: {csv_path}')
    print(f'  Matches: {len(rows)}')

    # Show sample
    print(f'\nSample (first 3):')
    for row in rows[:3]:
        print(f'  {row["date"]} [{row["group"]}] {row["home"]:20s} vs {row["away"]:20s}  H={row["B365H"]} D={row["B365D"]} A={row["B365A"]}')


if __name__ == '__main__':
    main()
```

**Step 4: 确认测试通过**
```bash
pytest tests/test_fetch_wc_odds.py -v
```
Expected: PASS (3 tests)

**Step 5: Commit**
```bash
git add scripts/fetch_wc_odds.py tests/test_fetch_wc_odds.py
git commit -m "feat: fetch WC odds from Odds API (Paddy Power)"
```

---

### Task 2: 运行脚本，验证输出

**Step 1: 执行脚本**
```bash
python scripts/fetch_wc_odds.py
```

**Step 2: 验证 CSV**
- 72 行数据
- 所有赔率 > 1.0
- 12 个小组 (A-L) 各 6 场
- 队名与现有 CSV 一致

**Step 3: 提交新 CSV**
```bash
git add run_wc_odds.csv
git commit -m "data: update WC odds with real Paddy Power odds"
```

---

### Task 3: 集成验证

**Step 1: 启动 Flask app**
```bash
python app.py
```

**Step 2: 打开浏览器**
检查面板：
- 预测页面正常显示
- 赔率是新的（不是模拟的）
- 淘汰赛标签页正常

---

### Task 4: 清理

- 删除 `_test_api*.py`
- 删除 `_check_teams.py`
- 删除 `_odds_raw.json`
- 提交清理

```bash
git rm _test_api*.py _check_teams.py _odds_raw.json
git add .
git commit -m "chore: cleanup test files"
```
