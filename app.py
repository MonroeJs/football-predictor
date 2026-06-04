"""
统一 Flask App — 支持多联赛切换

访问:
  /              → 默认联赛 (wc2026)
  /epl           → 英超
  /j1            → J1 联赛
  /wc2026        → 世界杯
  /api/...       → JSON API
"""
import sys, json, os
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

import pandas as pd
from flask import Flask, render_template, jsonify, request

sys.path.insert(0, str(Path(__file__).parent.absolute()))

from src.leagues import REGISTRY, get_league, list_leagues
from src.betting_system import get_confidence_tier

# Import all league modules so they register
import src.leagues.epl
import src.leagues.j_league
import src.leagues.wc_2026

# Database
from src.database import init_db, import_from_csv, get_matches, get_today_matches
from src.database import update_result, get_stats, refresh_odds
from pathlib import Path

app = Flask(__name__)

# Init DB on startup
init_db()
# Import WC odds if available
wc_csv = Path(__file__).parent / 'run_wc_odds.csv'
if wc_csv.exists():
    import_from_csv(wc_csv)

PORT = int(os.environ.get('PORT', 5001))

# ─── 数据层 ────────────────────────────────────────────────

def load_league_data(league_key: str) -> dict:
    """加载一个联赛的所有数据"""
    league = get_league(league_key)
    if not league:
        return {'error': f'League "{league_key}" not found'}

    predictions = league.get_predictions()
    standings = league.get_standings()
    info = league.get_info()

    # 赛事概率（世界杯淘汰赛/夺冠）
    tournament_probs = None
    if hasattr(league, 'get_tournament_probs'):
        tournament_probs = league.get_tournament_probs()

    # 统计
    tier_counts = defaultdict(int)
    total_stake = 0
    total_recommended = 0
    for p in predictions:
        t = p.get('tier', '')
        if t in ['Max', 'Elite', 'VHigh', 'High', 'Medium', 'Low']:
            tier_counts[t] += 1
        if p.get('suggested_stake', 0) > 0:
            total_recommended += 1
            total_stake += p['suggested_stake']

    # 日历
    calendar = defaultdict(list)
    for p in predictions:
        d = p.get('date', '')[:10]
        if d:
            calendar[d].append(p)

    return {
        'league': info,
        'predictions': predictions,
        'standings': standings,
        'calendar': dict(sorted(calendar.items())),
        'tier_counts': dict(tier_counts),
        'total_recommended': total_recommended,
        'total_stake': total_stake,
        'tournament_probs': tournament_probs,
    }

# ─── 路由 ──────────────────────────────────────────────────

TIER_CN = {'Max':'至尊','Elite':'精选','VHigh':'高信','High':'关注','Medium':'观望','Low':'放弃'}

@app.route('/')
def index():
    """默认页面 — 跳转到世界杯"""
    return dashboard('wc2026')

@app.route('/<league_key>')
def dashboard(league_key):
    """联赛面板"""
    data = load_league_data(league_key)
    if 'error' in data:
        return data['error'], 404

    today_str = date.today().isoformat()[:10]
    today_matches = [p for p in data['predictions']
                     if p.get('date', '').startswith(today_str)]

    # 结果追踪数据（仅世界杯）
    track_stats = {}
    wc_matches = []
    if league_key == 'wc2026':
        track_stats = get_stats()
        wc_matches = get_matches()

    return render_template('dashboard.html',
        data=data,
        today_matches=today_matches,
        all_leagues=list_leagues(),
        TIER_CN=TIER_CN,
        now=datetime.now(),
        json=json,
        track_stats=track_stats,
        wc_matches=wc_matches,
    )

@app.route('/api/<league_key>/predictions')
def api_predictions(league_key):
    """预测 API"""
    data = load_league_data(league_key)
    return jsonify(data.get('predictions', []))

@app.route('/api/<league_key>/standings')
def api_standings(league_key):
    """积分榜 / 出线概率 API"""
    data = load_league_data(league_key)
    return jsonify(data.get('standings', {}))

@app.route('/api/<league_key>/calendar')
def api_calendar(league_key):
    """日历 API"""
    data = load_league_data(league_key)
    return jsonify(data.get('calendar', {}))

@app.route('/api/leagues')
def api_leagues():
    """列出所有联赛"""
    return jsonify(list_leagues())


# ═══ 结果追踪 API ══════════════════════════════════════

@app.route('/api/wc2026/matches')
def api_wc_matches():
    """世界杯比赛列表（含已录入结果）"""
    date_filter = request.args.get('date', '')
    matches = get_matches(date_filter)
    return jsonify(matches)


@app.route('/api/wc2026/stats')
def api_wc_stats():
    """世界杯追踪统计"""
    return jsonify(get_stats())


@app.route('/api/wc2026/result', methods=['POST'])
def api_record_result():
    """录入比赛结果"""
    data = request.get_json()
    match_id = data.get('match_id')
    winner = data.get('winner', '')
    home_goals = data.get('home_goals')
    away_goals = data.get('away_goals')
    if not match_id or not winner:
        return jsonify({'error': 'match_id and winner required'}), 400
    update_result(match_id, winner, home_goals, away_goals)
    return jsonify({'status': 'ok'})


@app.route('/api/wc2026/refresh-odds', methods=['POST'])
def api_refresh_odds():
    """手动刷新赔率 — 从 football-data.co.uk 爬取最新数据"""
    from scripts.update_live_odds import main as fetch_live_odds
    result = fetch_live_odds()
    return jsonify(result)

# ─── 模板上下文 ────────────────────────────────────────────

@app.context_processor
def inject_globals():
    return {
        'datetime': datetime,
        'TIER_CN': TIER_CN,
        'int': int,
    }

# ─── 启动 ──────────────────────────────────────────────────

def start_scheduler():
    """定时赔率更新（每天 10:00 和 14:00）"""
    import threading, time
    def _run():
        while True:
            now = datetime.now()
            if now.hour in [10, 14] and now.minute == 0:
                print(f'[{now.strftime("%H:%M")}] Scheduled odds update...')
                try:
                    from scripts.update_live_odds import main as fetch_live
                    fetch_live()
                except Exception as e:
                    print(f'  Scheduled update error: {e}')
                time.sleep(61)
            time.sleep(30)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    print('[Scheduler] Odds auto-update: daily 10:00, 14:00')

def _prewarm_tournament():
    """后台预热世界杯淘汰赛模拟（避免首次请求等待 40s）"""
    import threading
    def _warm():
        print('[Warmup] Pre-warming WC tournament Monte Carlo...')
        from src.group_probs import calc_full_tournament
        calc_full_tournament(force_refresh=True)
        print('[Warmup] Tournament cache ready.')
    t = threading.Thread(target=_warm, daemon=True)
    t.start()

if __name__ == '__main__':
    print('Available leagues:', list_leagues())
    # 后台预热 ML 模型
    from scripts.warmup_models import warmup_all
    warmup_all(background=True)
    
    # 后台预热世界杯淘汰赛
    _prewarm_tournament()
    
    # 定时赔率更新
    start_scheduler()
    
    app.run(host='127.0.0.1', port=PORT, debug=True)
