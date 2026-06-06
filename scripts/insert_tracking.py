"""Insert tracking section into template"""
from pathlib import Path

path = Path(__file__).parent.parent / 'templates' / 'dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    tmpl = f.read()

section = '''<!-- TRACK section -->
<div id="sec-track" class="sec">
  <div class="card-box">
    <div class="ct d-flex justify-content-between">
      <span><i class="bi bi-graph-up-arrow me-1"></i>实时追踪</span>
      <span style="font-size:.7rem;color:var(--muted)">开赛后自动更新</span>
    </div>
    <div class="hero" style="grid-template-columns:repeat(4,1fr);margin-bottom:1rem">
      <div><div class="val" style="color:var(--blu)">{{ track_stats.total|default(0) }}</div><div class="lbl">已录入</div></div>
      <div><div class="val" style="color:var(--grn)">{{ track_stats.correct|default(0) }}</div><div class="lbl">命中</div></div>
      <div><div class="val" style="color:var(--gold)">{{ track_stats.accuracy|default("N/A") }}</div><div class="lbl">准确率</div></div>
      <div><div class="val" style="color:var(--purp)">{{ "%.0f"|format(track_stats.bets.total_profit|default(0)) }}</div><div class="lbl">盈亏(Y)</div></div>
    </div>
    {% if track_stats.total is defined and track_stats.total > 0 and track_stats.by_tier %}
    <div class="mb-3">
      <div style="font-size:.8rem;font-weight:600;color:var(--text2);margin-bottom:8px">分级准确率</div>
      {% for t in ['Max','Elite','VHigh','High','Medium','Low'] %}{% if t in track_stats.by_tier %}{% set ts = track_stats.by_tier[t] %}
      <div class="d-flex justify-content-between align-items-center mb-1" style="font-size:.75rem">
        <span class="badge-t t-{{ t }}">{{ TIER_CN.get(t,t) }}</span>
        <span style="color:var(--text2)">{{ ts.total }}场</span>
        <span style="color:var(--grn)">{{ ts.accuracy }}</span>
      </div>
      {% endif %}{% endfor %}
    </div>
    {% endif %}
    <div style="max-height:40vh;overflow-y:auto">
      <table class="table table-dark mb-0" style="font-size:.8rem">
        <thead><tr style="color:var(--text2);position:sticky;top:0;background:var(--card)"><th>日期</th><th>对阵</th><th>预测</th><th>实际</th><th>结果</th><th>操作</th></tr></thead>
        <tbody>
        {% for m in wc_matches %}
        {% set is_future = m.date > now.strftime('%Y-%m-%d') %}
        {% set is_done = m.result_confirmed == 1 %}
        <tr>
          <td>{{ m.date[5:10] if m.date else '' }}</td>
          <td>{{ m.home_team[:12] }} vs {{ m.away_team[:12] }}</td>
          <td>{% if m.tier %}<span class="badge-t t-{{ m.tier }}">{{ TIER_CN.get(m.tier,m.tier) }}</span>{% else %}-{% endif %}</td>
          <td>{% if is_done %}<strong>{{ {'H':'主胜','D':'平局','A':'客胜'}.get(m.actual_winner,'?') }}</strong>{% if m.home_goals is not none and m.away_goals is not none %}({{ m.home_goals|int }}-{{ m.away_goals|int }}){% endif %}{% elif is_future %}<span style="color:var(--muted)">未开始</span>{% else %}<span style="color:var(--gold)">等待录入</span>{% endif %}</td>
          <td>{% if is_done %}{% if m.actual_winner == m.predicted_winner %}<span style="color:var(--grn);font-weight:700">命中</span>{% else %}<span style="color:var(--red);font-weight:700">未中</span>{% endif %}{% else %}<span style="color:var(--muted)">-</span>{% endif %}</td>
          <td>{% if not is_future and not is_done %}<button class="btn btn-sm btn-outline-success" style="font-size:.7rem;padding:.1rem .4rem" onclick="recordResult({{ m.id }},'{{ m.home_team }}','{{ m.away_team }}')">录入</button>{% endif %}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>

'''

insert_marker = '<!-- Result Recording Modal -->'
if insert_marker in tmpl:
    tmpl = tmpl.replace(insert_marker, section + insert_marker)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(tmpl)
    print('OK: Tracking section inserted')
else:
    print('ERROR: Marker not found!')
    # Try to find something else
    for marker in ['RIGHT SIDEBAR', 'Result Recording Modal']:
        if marker in tmpl:
            print(f'  Found: {marker}')
