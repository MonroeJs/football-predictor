"""
世界杯 2026 预测面板 — Flask Web App v2
新增：图表 API、今日推荐、日历、小组出线
"""
import sys, json, csv, io
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

import pandas as pd
import numpy as np
from flask import Flask, render_template, jsonify, request

sys.path.insert(0, str(Path(__file__).parent.absolute()))
from src.wc_predictor import WCPredictor, TEAM_ELO
from src.betting_system import get_confidence_tier, ConfidenceTier
from src.group_probs import calc_all_groups, calc_full_tournament, GROUPS as WC_GROUPS

# 预热 Monte Carlo 缓存（首次导入时计算，后续 API 直接返回）
print('Pre-warming Monte Carlo cache...')
calc_all_groups(force_refresh=True)
print('Cache ready.')
from datetime import datetime as dt_module

app = Flask(__name__)

# ─── 数据加载 ────────────────────────────────────────────────

def load_predictions():
    """从 CSV 加载当前预测数据"""
    csv_path = Path(__file__).parent / 'run_wc_odds.csv'
    if not csv_path.exists():
        return []
    
    df = pd.read_csv(csv_path)
    predictor = WCPredictor()
    matches = df.to_dict('records')
    
    predictions = []
    for m in matches:
        for k in ['B365H', 'B365D', 'B365A']:
            val = m.get(k)
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            try:
                m[k] = float(val)
            except (ValueError, TypeError):
                continue
        
        if not all(k in m and isinstance(m[k], (int, float)) and m[k] > 0.1 
                   for k in ['B365H', 'B365D', 'B365A']):
            continue
        
        result = predictor.predict_match(m['home'], m['away'], 
                                         float(m['B365H']), 
                                         float(m['B365D']), 
                                         float(m['B365A']))
        result['group'] = m.get('group', '?')
        result['date'] = m.get('date', '')
        result['home_elo'] = TEAM_ELO.get(m['home'], 1800)
        result['away_elo'] = TEAM_ELO.get(m['away'], 1800)
        predictions.append(result)
    
    predictions.sort(key=lambda x: (x.get('date', ''), 
                                     -float(x['confidence'].rstrip('%')) / 100))
    return predictions

def get_backtest_data():
    """获取回测结果"""
    predictor = WCPredictor()
    predictor.load_historical_data()
    results = {}
    for year in ['2022', '2014']:
        if year in predictor.historical_data:
            r = predictor.analyze_odds_backtest(predictor.historical_data[year], f'WC {year}')
            results[year] = r
    return results

def get_calendar_data(predictions):
    """按日期分组的日历数据"""
    calendar = defaultdict(list)
    for p in predictions:
        d = p.get('date', '')[:10]
        if d:
            calendar[d].append(p)
    return dict(sorted(calendar.items()))

def get_chart_stats(predictions):
    """图表统计数据"""
    # 置信度分布
    tier_counts = defaultdict(int)
    for p in predictions:
        tier_counts[p['tier']] += 1
    
    # 每日推荐金额
    daily_stakes = defaultdict(float)
    daily_bets = defaultdict(int)
    for p in predictions:
        d = p.get('date', '')[:10]
        if d and p.get('suggested_stake', 0) > 0:
            daily_stakes[d] += p['suggested_stake']
            daily_bets[d] += 1
    
    # 赔率-置信度散点
    scatter_data = []
    for p in predictions:
        conf = float(p['confidence'].rstrip('%')) / 100
        scatter_data.append({
            'x': p.get('fav_odds', 0),
            'y': conf,
            'tier': p['tier'],
            'label': f"{p['home'][:8]} vs {p['away'][:8]}",
        })
    
    return {
        'tier_counts': dict(tier_counts),
        'daily_stakes': [{'date': k, 'stake': v, 'bets': daily_bets[k]} 
                         for k, v in sorted(daily_stakes.items())],
        'scatter': scatter_data,
    }

# ═══ Routes ═══════════════════════════════════════════════════

@app.route('/')
def dashboard():
    """主面板"""
    predictions = load_predictions()
    backtest = get_backtest_data()
    calendar = get_calendar_data(predictions)
    stats = get_chart_stats(predictions)
    
    # 今日
    today_str = date.today().isoformat()[:10]
    today_matches = [p for p in predictions if p.get('date', '').startswith(today_str)]
    
    # 统计汇总
    total_recommended = sum(1 for p in predictions if p.get('suggested_stake', 0) > 0)
    total_stake = sum(p.get('suggested_stake', 0) for p in predictions)
    
    # 淘汰赛概率
    from src.group_probs import TOURNEY_CACHE
    tournament_probs = None
    if TOURNEY_CACHE:
        tournament_probs = calc_full_tournament()
    
    # 构建统一 data dict（匹配 dashboard.html）
    data = {
        'league': {
            'key': 'wc2026',
            'name': '2026 FIFA World Cup',
            'data_source': '赔率驱动 (run_wc_odds.csv)',
            'show_groups': True,
            'show_standings': False,
        },
        'predictions': predictions,
        'standings': {
            'groups': calc_all_groups(),
            'teams_by_group': WC_GROUPS,
        },
        'calendar': calendar,
        'tier_counts': stats.get('tier_counts', {}),
        'total_recommended': total_recommended,
        'total_stake': total_stake,
        'tournament_probs': tournament_probs,
    }
    
    return render_template('dashboard.html',
        data=data,
        today_matches=today_matches,
        all_leagues={'wc2026': '2026 FIFA World Cup'},
        TIER_CN={
            'Max': '至尊', 'Elite': '精选', 'VHigh': '高信',
            'High': '关注', 'Medium': '观望', 'Low': '放弃',
        },
        now=datetime.now(),
        json=json,
        track_stats={},
        wc_matches=[],
    )

@app.route('/api/predictions')
def api_predictions():
    """所有预测"""
    return jsonify(load_predictions())

@app.route('/api/today')
def api_today():
    """当日比赛"""
    predictions = load_predictions()
    today_str = date.today().isoformat()[:10]
    return jsonify([p for p in predictions if p.get('date', '').startswith(today_str)])

@app.route('/api/calendar')
def api_calendar():
    """日历数据"""
    predictions = load_predictions()
    cal = get_calendar_data(predictions)
    return jsonify(cal)

@app.route('/api/stats')
def api_stats():
    """图表统计数据"""
    predictions = load_predictions()
    return jsonify(get_chart_stats(predictions))

@app.route('/api/group-probs')
def api_group_probs():
    """小组出线概率（使用缓存）"""
    results = calc_all_groups(force_refresh=False)
    return jsonify(results)

@app.context_processor
def inject_helpers():
    return {
        'datetime': dt_module,
        'dt_module': dt_module,
        'json': json,
        'TIER_CN': {
            'Max': '至尊',
            'Elite': '精选',
            'VHigh': '高信',
            'High': '关注',
            'Medium': '观望',
            'Low': '放弃',
        },
        'TEAM_ELO': TEAM_ELO,
    }

def _prewarm_tournament():
    """后台预热淘汰赛模拟"""
    import threading
    def _warm():
        print('[Warmup] Pre-warming tournament Monte Carlo...')
        from src.group_probs import calc_full_tournament
        calc_full_tournament(force_refresh=True)
        print('[Warmup] Tournament cache ready.')
    t = threading.Thread(target=_warm, daemon=True)
    t.start()

if __name__ == '__main__':
    _prewarm_tournament()
    app.run(host='127.0.0.1', port=5001, debug=True)
