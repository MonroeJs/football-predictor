"""
SQLite 数据库 — 比赛数据、结果追踪、赔率历史

三张表:
  matches          — 比赛预测 + 实际结果 + 投注记录
  odds_history     — 赔率变动日志
  stats_snapshots  — 每日统计快照
"""
import sqlite3, json, csv, os
from pathlib import Path
from datetime import datetime, date
from typing import Optional

DB_DIR = Path(__file__).parent.parent / 'data'
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / 'worldcup.db'


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            group_name TEXT NOT NULL DEFAULT '',
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            b365h REAL DEFAULT 0,
            b365d REAL DEFAULT 0,
            b365a REAL DEFAULT 0,
            predicted_winner TEXT DEFAULT '',
            confidence REAL DEFAULT 0,
            tier TEXT DEFAULT '',
            suggested_stake REAL DEFAULT 0,

            -- 实际结果（开赛后录入）
            actual_winner TEXT DEFAULT '',
            home_goals INTEGER DEFAULT NULL,
            away_goals INTEGER DEFAULT NULL,
            result_confirmed INTEGER DEFAULT 0,

            -- 投注记录
            bet_placed INTEGER DEFAULT 0,
            bet_amount REAL DEFAULT 0,
            bet_profit REAL DEFAULT 0,

            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS odds_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            b365h_old REAL,
            b365d_old REAL,
            b365a_old REAL,
            b365h_new REAL,
            b365d_new REAL,
            b365a_new REAL,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (match_id) REFERENCES matches(id)
        );

        CREATE TABLE IF NOT EXISTS stats_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            total_predictions INTEGER DEFAULT 0,
            correct_predictions INTEGER DEFAULT 0,
            accuracy REAL DEFAULT 0,
            total_bets REAL DEFAULT 0,
            total_profit REAL DEFAULT 0,
            snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 方便查询
        CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
        CREATE INDEX IF NOT EXISTS idx_matches_tier ON matches(tier);
        CREATE INDEX IF NOT EXISTS idx_odds_history_match ON odds_history(match_id);
    """)
    conn.commit()
    conn.close()
    print(f'  DB initialized: {DB_PATH}')


def import_from_csv(csv_path: Path) -> int:
    """从 run_wc_odds.csv 导入比赛到数据库"""
    import pandas as pd
    init_db()

    df = pd.read_csv(csv_path)
    conn = get_conn()

    count = 0
    for _, row in df.iterrows():
        date_val = row.get('date', '')
        home = row.get('home', '')
        away = row.get('away', '')
        group_val = row.get('group', '')
        h_odds = float(row['B365H']) if str(row.get('B365H', '0')).strip() else 0
        d_odds = float(row['B365D']) if str(row.get('B365D', '0')).strip() else 0
        a_odds = float(row['B365A']) if str(row.get('B365A', '0')).strip() else 0

        # 计算预测
        from src.betting_system import get_confidence_tier
        total_implied = sum(1.0 / max(o, 0.01) for o in [h_odds, d_odds, a_odds])
        probs = {
            'H': (1.0 / max(h_odds, 0.01)) / total_implied,
            'D': (1.0 / max(d_odds, 0.01)) / total_implied,
            'A': (1.0 / max(a_odds, 0.01)) / total_implied,
        }
        max_outcome = max(probs, key=probs.get)
        max_prob = probs[max_outcome]
        tier = get_confidence_tier(max_prob)

        stake = 0
        if tier.value in ('Max',): stake = 80
        elif tier.value in ('Elite',): stake = 50
        elif tier.value in ('VHigh',): stake = 30

        # 检查是否已存在
        existing = conn.execute(
            "SELECT id FROM matches WHERE date=? AND home_team=? AND away_team=?",
            (date_val, home, away)
        ).fetchone()

        if existing:
            # 更新赔率
            conn.execute("""
                UPDATE matches SET b365h=?, b365d=?, b365a=?,
                    predicted_winner=?, confidence=?, tier=?, suggested_stake=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (h_odds, d_odds, a_odds, max_outcome, max_prob, tier.value, stake, existing['id']))
        else:
            conn.execute("""
                INSERT INTO matches (date, group_name, home_team, away_team,
                    b365h, b365d, b365a,
                    predicted_winner, confidence, tier, suggested_stake)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date_val, group_val, home, away,
                  h_odds, d_odds, a_odds,
                  max_outcome, max_prob, tier.value, stake))
            count += 1

    conn.commit()
    conn.close()
    print(f'  Imported: {count} new matches')
    return count


def import_odds_rows(rows: list[dict]) -> int:
    """从内存中的 odds rows 导入比赛到数据库（绕过 CSV 文件读写，避免 Windows 文件锁）"""
    from src.betting_system import get_confidence_tier
    init_db()
    conn = get_conn()

    count = 0
    for row in rows:
        date_val = row.get('date', '')
        home = row.get('home', '')
        away = row.get('away', '')
        group_val = row.get('group', '')
        h_odds = float(row['B365H']) if str(row.get('B365H', '0')).strip() else 0
        d_odds = float(row['B365D']) if str(row.get('B365D', '0')).strip() else 0
        a_odds = float(row['B365A']) if str(row.get('B365A', '0')).strip() else 0

        total_implied = sum(1.0 / max(o, 0.01) for o in [h_odds, d_odds, a_odds])
        probs = {
            'H': (1.0 / max(h_odds, 0.01)) / total_implied,
            'D': (1.0 / max(d_odds, 0.01)) / total_implied,
            'A': (1.0 / max(a_odds, 0.01)) / total_implied,
        }
        max_outcome = max(probs, key=probs.get)
        max_prob = probs[max_outcome]
        tier = get_confidence_tier(max_prob)

        stake = 0
        if tier.value in ('Max',): stake = 80
        elif tier.value in ('Elite',): stake = 50
        elif tier.value in ('VHigh',): stake = 30

        existing = conn.execute(
            "SELECT id FROM matches WHERE date=? AND home_team=? AND away_team=?",
            (date_val, home, away)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE matches SET b365h=?, b365d=?, b365a=?,
                    predicted_winner=?, confidence=?, tier=?, suggested_stake=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (h_odds, d_odds, a_odds, max_outcome, max_prob, tier.value, stake, existing['id']))
        else:
            conn.execute("""
                INSERT INTO matches (date, group_name, home_team, away_team,
                    b365h, b365d, b365a,
                    predicted_winner, confidence, tier, suggested_stake)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date_val, group_val, home, away,
                  h_odds, d_odds, a_odds,
                  max_outcome, max_prob, tier.value, stake))
            count += 1

    conn.commit()
    conn.close()
    print(f'  DB imported: {count} new, {len(rows) - count} updated')
    return count


def get_matches(date_filter: str = '') -> list[dict]:
    """获取比赛列表"""
    conn = get_conn()
    if date_filter:
        rows = conn.execute(
            "SELECT * FROM matches WHERE date=? ORDER BY date, id",
            (date_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM matches ORDER BY date, id"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_matches() -> list[dict]:
    """获取今日比赛"""
    today = date.today().isoformat()
    return get_matches(today)


def update_result(match_id: int, actual_winner: str,
                  home_goals: int = None, away_goals: int = None):
    """录入比赛结果"""
    conn = get_conn()
    conn.execute("""
        UPDATE matches SET
            actual_winner=?, home_goals=?, away_goals=?,
            result_confirmed=1, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (actual_winner, home_goals, away_goals, match_id))
    conn.commit()

    # 记录统计快照
    _update_stats_snapshot(conn)
    conn.close()


def record_bet(match_id: int, amount: float):
    """记录实际投注"""
    conn = get_conn()
    match = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    if match and match['result_confirmed']:
        # 计算盈亏
        winner = match['actual_winner']
        predicted = match['predicted_winner']
        if winner == predicted:
            fav_odds = {'H': match['b365h'], 'D': match['b365d'], 'A': match['b365a']}.get(winner, 0)
            profit = amount * (fav_odds - 1)
        else:
            profit = -amount
    else:
        profit = 0

    conn.execute("""
        UPDATE matches SET bet_placed=1, bet_amount=?, bet_profit=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (amount, profit, match_id))
    conn.commit()
    conn.close()


def _update_stats_snapshot(conn):
    """更新每日统计快照"""
    today = date.today().isoformat()
    confirmed = conn.execute(
        "SELECT COUNT(*) as total, SUM(CASE WHEN actual_winner=predicted_winner THEN 1 ELSE 0 END) as correct "
        "FROM matches WHERE result_confirmed=1"
    ).fetchone()

    total = confirmed['total'] or 0
    correct = confirmed['correct'] or 0
    accuracy = correct / total if total > 0 else 0

    bets = conn.execute(
        "SELECT COUNT(*) as n, COALESCE(SUM(bet_amount),0) as total_bet, "
        "COALESCE(SUM(bet_profit),0) as total_profit "
        "FROM matches WHERE bet_placed=1"
    ).fetchone()

    conn.execute("""
        INSERT INTO stats_snapshots (date, total_predictions, correct_predictions, accuracy, total_bets, total_profit)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (today, total, correct, accuracy, bets['total_bet'] or 0, bets['total_profit'] or 0))
    conn.commit()


def get_stats() -> dict:
    """获取统计"""
    conn = get_conn()
    confirmed = conn.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN actual_winner=predicted_winner THEN 1 ELSE 0 END) as correct
        FROM matches WHERE result_confirmed=1
    """).fetchone()

    by_tier = conn.execute("""
        SELECT tier,
            COUNT(*) as total,
            SUM(CASE WHEN actual_winner=predicted_winner THEN 1 ELSE 0 END) as correct
        FROM matches WHERE result_confirmed=1
        GROUP BY tier
    """).fetchall()

    bets = conn.execute("""
        SELECT COUNT(*) as n, COALESCE(SUM(bet_amount),0) as total_bet,
               COALESCE(SUM(bet_profit),0) as total_profit
        FROM matches WHERE bet_placed=1
    """).fetchone()

    trend = conn.execute("""
        SELECT date, accuracy, total_bets, total_profit
        FROM stats_snapshots ORDER BY date
    """).fetchall()

    conn.close()

    total = confirmed['total'] or 0
    correct = confirmed['correct'] or 0

    return {
        'total': total,
        'correct': correct,
        'accuracy': f'{correct/total:.1%}' if total > 0 else 'N/A',
        'by_tier': {r['tier']: {'total': r['total'], 'correct': r['correct'],
                                 'accuracy': f'{r["correct"]/r["total"]:.1%}' if r['total'] > 0 else 'N/A'}
                    for r in by_tier},
        'bets': {
            'total_bets': bets['n'] or 0,
            'total_bet_amount': bets['total_bet'] or 0,
            'total_profit': bets['total_profit'] or 0,
        },
        'trend': [dict(r) for r in trend],
    }


def refresh_odds(csv_path: Path) -> dict:
    """刷新赔率 — 从 CSV 更新已有比赛的赔率，记录变动"""
    import pandas as pd
    df = pd.read_csv(csv_path)
    conn = get_conn()
    changes = 0

    for _, row in df.iterrows():
        date_val = row.get('date', '')
        home = row.get('home', '')
        away = row.get('away', '')
        h_new = float(row['B365H']) if str(row.get('B365H', '0')).strip() else 0
        d_new = float(row['B365D']) if str(row.get('B365D', '0')).strip() else 0
        a_new = float(row['B365A']) if str(row.get('B365A', '0')).strip() else 0

        existing = conn.execute(
            "SELECT id, b365h, b365d, b365a FROM matches WHERE date=? AND home_team=? AND away_team=?",
            (date_val, home, away)
        ).fetchone()

        if existing:
            old_h, old_d, old_a = existing['b365h'], existing['b365d'], existing['b365a']
            if abs(old_h - h_new) > 0.01 or abs(old_d - d_new) > 0.01 or abs(old_a - a_new) > 0.01:
                conn.execute("""
                    INSERT INTO odds_history (match_id, b365h_old, b365d_old, b365a_old, b365h_new, b365d_new, b365a_new)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (existing['id'], old_h, old_d, old_a, h_new, d_new, a_new))

                conn.execute("""
                    UPDATE matches SET b365h=?, b365d=?, b365a=?, updated_at=CURRENT_TIMESTAMP WHERE id=?
                """, (h_new, d_new, a_new, existing['id']))
                changes += 1

    conn.commit()
    conn.close()
    return {'updated': changes}


if __name__ == '__main__':
    init_db()
    print('Database ready')

    # Import from CSV if exists
    csv_path = Path(__file__).parent.parent / 'run_wc_odds.csv'
    if csv_path.exists():
        import_from_csv(csv_path)

    # Show stats
    print('Stats:', get_stats())
