"""Update dashboard template with tracking tab and results"""
from pathlib import Path

path = Path(__file__).parent.parent / 'templates' / 'dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Add tracking tab to nav pills (only for WC)
old_nav = '<button data-sec="groups"><i class="bi bi-diagram-3"></i>分组</button>'
new_nav = old_nav + '\n{% if data.league.key == "wc2026" %}\n  <button data-sec="track"><i class="bi bi-graph-up-arrow"></i>追踪</button>\n{% endif %}'
html = html.replace(old_nav, new_nav)
print('1. Nav pills updated')

# 2. Add tracking section after groups section
old_groups = '{% endif %}\n</div>\n</div>\n\n<!-- RIGHT SIDEBAR -->'
new_track = '''{% endif %}

<!-- TRACK (only WC) -->
{% if data.league.key == "wc2026" %}
<div id="sec-track" class="sec">
  <div class="card-box">
    <div class="ct d-flex justify-content-between">
      <span><i class="bi bi-graph-up-arrow me-1"></i>实时追踪</span>
      <span style="font-size:.7rem;color:var(--muted)">开赛后自动更新</span>
    </div>
    
    <!-- Stats cards -->
    <div class="hero" style="grid-template-columns:repeat(4,1fr);margin-bottom:1rem">
      <div><div class="val" style="color:var(--blu)">{{ track_stats.total|default(0) }}</div><div class="lbl">已录入</div></div>
      <div><div class="val" style="color:var(--grn)">{{ track_stats.correct|default(0) }}</div><div class="lbl">命中</div></div>
      <div><div class="val" style="color:var(--gold)">{{ track_stats.accuracy|default("N/A") }}</div><div class="lbl">准确率</div></div>
      <div><div class="val" style="color:var(--purp)">{{ "%.0f"|format(track_stats.bets.total_profit|default(0)) }}</div><div class="lbl">盈亏(Y)</div></div>
    </div>
    
    <!-- By tier -->
    {% if track_stats.by_tier %}
    <div class="mb-3">
      <div style="font-size:.8rem;font-weight:600;color:var(--text2);margin-bottom:8px">分级准确率</div>
      {% for t in ['Max','Elite','VHigh','High','Medium','Low'] %}
      {% if t in track_stats.by_tier %}
      {% set ts = track_stats.by_tier[t] %}
      <div class="d-flex justify-content-between align-items-center mb-1" style="font-size:.75rem">
        <span class="badge-t t-{{ t }}">{{ TIER_CN.get(t,t) }}</span>
        <span style="color:var(--text2)">{{ ts.total }}场</span>
        <span style="color:{% if '+' in ts.accuracy %}var(--grn){% else %}var(--red){% endif %}">{{ ts.accuracy }}</span>
      </div>
      {% endif %}
      {% endfor %}
    </div>
    {% endif %}
    
    <!-- Match results list -->
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
          <td>
            {% if is_done %}
            <strong>{{ {'H':m.home_team[:8]+'胜','D':'平局','A':m.away_team[:8]+'胜'}.get(m.actual_winner,'?') }}</strong>
            {% if m.home_goals is not none and m.away_goals is not none %}
            ({{ m.home_goals|int }}-{{ m.away_goals|int }})
            {% endif %}
            {% elif is_future %}
            <span style="color:var(--muted)">未开始</span>
            {% else %}
            <span style="color:var(--gold)">等待录入</span>
            {% endif %}
          </td>
          <td>
            {% if is_done %}
            {% if m.actual_winner == m.predicted_winner %}
            <span style="color:var(--grn);font-weight:700">命中</span>
            {% else %}
            <span style="color:var(--red);font-weight:700">未中</span>
            {% endif %}
            {% else %}
            <span style="color:var(--muted)">-</span>
            {% endif %}
          </td>
          <td>
            {% if not is_future and not is_done %}
            <button class="btn btn-sm btn-outline-success" style="font-size:.7rem;padding:.1rem .4rem"
                    onclick="recordResult({{ m.id }},'{{ m.home_team }}','{{ m.away_team }}')">录入</button>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    
    {% if track_stats.trend %}
    <div class="mt-3">
      <div style="font-size:.8rem;font-weight:600;color:var(--text2);margin-bottom:8px">准确率趋势</div>
      <canvas id="chartTrend" style="max-height:150px;width:100%"></canvas>
    </div>
    {% endif %}
  </div>
</div>
{% endif %}

<!-- RIGHT SIDEBAR -->
'''
html = html.replace(old_groups, new_track)
print('2. Tracking section added')

# 3. Add result recording modal
old_sidebar = '<!-- RIGHT SIDEBAR -->'
result_modal = '''<!-- Result Recording Modal -->
<div class="modal fade" id="resultModal" tabindex="-1">
  <div class="modal-dialog modal-sm modal-dialog-centered">
    <div class="modal-content" style="background:var(--card);color:var(--text);border:1px solid var(--card-border)">
      <div class="modal-header border-0 pb-0">
        <h6 class="modal-title" id="resultModalLabel">录入结果</h6>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <p id="resultMatchName" style="font-size:.9rem;font-weight:600"></p>
        <div class="d-flex gap-2 mb-3">
          <div class="flex-fill text-center">
            <div style="font-size:.8rem;color:var(--text2)" id="resultHomeName">主队</div>
            <button class="btn btn-outline-success btn-sm mt-1 result-btn" data-winner="H">主胜</button>
          </div>
          <div class="flex-fill text-center">
            <div style="font-size:.8rem;color:var(--text2)">平局</div>
            <button class="btn btn-outline-warning btn-sm mt-1 result-btn" data-winner="D">平</button>
          </div>
          <div class="flex-fill text-center">
            <div style="font-size:.8rem;color:var(--text2)" id="resultAwayName">客队</div>
            <button class="btn btn-outline-danger btn-sm mt-1 result-btn" data-winner="A">客胜</button>
          </div>
        </div>
        <div class="row g-2 mb-2">
          <div class="col-6">
            <label style="font-size:.75rem;color:var(--text2)" id="resultHomeGoalsLabel">主队进球</label>
            <input type="number" id="resultHomeGoals" class="form-control form-control-sm" min="0" max="20" value="0" style="background:#1e293b;color:var(--text);border-color:var(--card-border)">
          </div>
          <div class="col-6">
            <label style="font-size:.75rem;color:var(--text2)" id="resultAwayGoalsLabel">客队进球</label>
            <input type="number" id="resultAwayGoals" class="form-control form-control-sm" min="0" max="20" value="0" style="background:#1e293b;color:var(--text);border-color:var(--card-border)">
          </div>
        </div>
      </div>
      <div class="modal-footer border-0 pt-0">
        <button class="btn btn-sm btn-secondary" data-bs-dismiss="modal" style="font-size:.8rem">取消</button>
        <button class="btn btn-sm btn-primary" onclick="submitResult()" style="font-size:.8rem">确认录入</button>
      </div>
    </div>
  </div>
</div>

<!-- RIGHT SIDEBAR -->
'''
html = html.replace(old_sidebar, result_modal)
print('3. Result modal added')

# 4. Add JS for result recording
old_js_end = '</script>\n</body>\n</html>'
new_js = '''<script>
// Result recording
var currentResultMatchId = null;

function recordResult(matchId, homeTeam, awayTeam) {
  currentResultMatchId = matchId;
  document.getElementById('resultMatchName').textContent = homeTeam + ' vs ' + awayTeam;
  document.getElementById('resultHomeName').textContent = homeTeam;
  document.getElementById('resultAwayName').textContent = awayTeam;
  document.getElementById('resultHomeGoals').value = 0;
  document.getElementById('resultAwayGoals').value = 0;
  document.getElementById('resultHomeGoalsLabel').textContent = homeTeam.slice(0,10) + ' 进球';
  document.getElementById('resultAwayGoalsLabel').textContent = awayTeam.slice(0,10) + ' 进球';
  
  // Highlight selection
  document.querySelectorAll('.result-btn').forEach(function(b) { b.classList.remove('active'); });
  
  var modal = new bootstrap.Modal(document.getElementById('resultModal'));
  modal.show();
}

document.querySelectorAll('.result-btn').forEach(function(btn) {
  btn.addEventListener('click', function() {
    document.querySelectorAll('.result-btn').forEach(function(b) { b.classList.remove('active'); });
    this.classList.add('active');
  });
});

function submitResult() {
  var activeBtn = document.querySelector('.result-btn.active');
  if (!activeBtn) { alert('请选择比赛结果'); return; }
  var winner = activeBtn.getAttribute('data-winner');
  var homeGoals = parseInt(document.getElementById('resultHomeGoals').value) || 0;
  var awayGoals = parseInt(document.getElementById('resultAwayGoals').value) || 0;
  
  fetch('/api/wc2026/result', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      match_id: currentResultMatchId,
      winner: winner,
      home_goals: homeGoals,
      away_goals: awayGoals
    })
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.status === 'ok') {
      location.reload();
    } else {
      alert('录入失败: ' + JSON.stringify(data));
    }
  }).catch(function(e) { alert('错误: ' + e); });
}

// Accuracy trend chart
setTimeout(function() {
  var tc = document.getElementById('chartTrend');
  if (!tc) return;
  fetch('/api/wc2026/stats').then(function(r){ return r.json(); }).then(function(data){
    if (data.trend && data.trend.length > 1) {
      var labels = data.trend.map(function(d){ return d.date.slice(5); });
      var acc = data.trend.map(function(d){ return d.accuracy * 100; });
      new Chart(tc, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: '准确率 %',
            data: acc,
            borderColor: '#22c55e',
            backgroundColor: 'rgba(34,197,94,0.1)',
            fill: true,
            tension: 0.3,
            pointRadius: 3,
          }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { font: {size:9}, color: '#cbd5e1' } },
            y: { grid: { color: 'rgba(255,255,255,0.04)' }, min: 0, max: 100, ticks: { font: {size:9}, color: '#cbd5e1', callback: function(v){ return v+'%'; } } }
          }
        }
      });
    }
  }).catch(function(e){});
}, 1000);
</script>
</body>
</html>'''
html = html.replace(old_js_end, new_js)
print('4. Tracking JS added')

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('\nDone!')
