"""Fix UI: Chinese tier names, redesign sidebar"""
from pathlib import Path

path = Path(__file__).parent.parent / 'templates' / 'wc_dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Add Chinese tier display map in JS
html = html.replace(
    'const TIER_COLORS = {',
    'const TIER_CN = {Max:"顶级",Elite:"精选",VHigh:"高信",High:"关注",Medium:"观望",Low:"放弃"};\nconst TIER_COLORS = {'
)

# 2. Replace all tier badge displays with Chinese names
# In tables: {{ p.tier }} where it's a badge label
html = html.replace(
    '<span class="badge-tier tier-{{ p.tier }}">{{ p.tier }}</span>',
    '<span class="badge-tier tier-{{ p.tier }}">{{ TIER_CN[p.tier] if p.tier in TIER_CN else p.tier }}</span>'
)

# 3. Replace sidebar charts with useful content
old_charts = '''        <!-- Charts -->
        <div class="glass-card">
            <div class="card-title"><i class="bi bi-bar-chart-fill me-1"></i>数据概览</div>
            <div class="charts-grid">
                <div class="chart-cell">
                    <div class="chart-title">置信度分布</div>
                    <canvas id="chartTier"></canvas>
                </div>
                <div class="chart-cell">
                    <div class="chart-title">每日推荐(Y)</div>
                    <canvas id="chartStakes"></canvas>
                </div>
                <div class="chart-cell">
                    <div class="chart-title">分组热度(Elo)</div>
                    <canvas id="chartGroups"></canvas>
                </div>
                <div class="chart-cell">
                    <div class="chart-title">赔率-置信度</div>
                    <canvas id="chartScatter"></canvas>
                </div>
            </div>
        </div>'''

new_charts = '''        <!-- Confidence Pie (single large chart) -->
        <div class="glass-card">
            <div class="card-title"><i class="bi bi-pie-chart me-1"></i>置信度分布</div>
            <canvas id="chartTier" style="max-height:170px;width:100%"></canvas>
        </div>

        <!-- Top 5 Picks -->
        <div class="glass-card">
            <div class="card-title"><i class="bi bi-star-fill text-warning me-1"></i>热门推荐 TOP 5</div>
            {% set top_bets = predictions|selectattr('suggested_stake')|list|sort(attribute='suggested_stake', reverse=True) %}
            {% if top_bets %}
            {% for p in top_bets[:5] %}
            <div class="d-flex justify-content-between align-items-center mb-2" style="background:rgba(30,41,59,0.5);border-radius:8px;padding:0.5rem 0.8rem">
                <div>
                    <div style="font-size:0.8rem;font-weight:600">{{ p.home[:12] }} vs {{ p.away[:12] }}</div>
                    <div style="font-size:0.65rem;color:var(--text-secondary)">{{ p.date[5:10] }} | {{ p.confidence }} | +{{ "%.2f"|format(p.fav_odds) }}</div>
                </div>
                <div style="text-align:right">
                    <div style="font-size:0.85rem;font-weight:700;color:var(--accent-green)">{{ "%.0f"|format(p.suggested_stake) }}Y</div>
                    <div><span class="badge-tier tier-{{ p.tier }}">{{ TIER_CN[p.tier] if p.tier in TIER_CN else p.tier }}</span></div>
                </div>
            </div>
            {% endfor %}
            {% else %}
            <div style="text-align:center;padding:1rem;color:var(--text-muted);font-size:0.8rem">暂无推荐</div>
            {% endif %}
        </div>

        <!-- Daily Stakes Chart -->
        <div class="glass-card">
            <div class="card-title"><i class="bi bi-graph-up me-1"></i>每日推荐金额</div>
            <canvas id="chartStakes" style="max-height:130px;width:100%"></canvas>
        </div>'''

if old_charts in html:
    html = html.replace(old_charts, new_charts)
    print('1. Charts section replaced')
else:
    print('WARNING: old charts not found!')

# 4. Update legend to Chinese names  
html = html.replace(
    "('Max', '置信度>=80%', '80\\u00a5', 'var(--accent-purple)'),",
    "('\\u81f3\\u5c0a', '\\u7f6e\\u4fe1\\u5ea6>=80%', '80\\u00a5', 'var(--accent-purple)'),"
)
html = html.replace("'Elite', '置信度>=70%'", "'\\u7cbe\\u9009', '\\u7f6e\\u4fe1\\u5ea6>=70%'")
html = html.replace("'VHigh', '置信度>=60%'", "'\\u9ad8\\u4fe1', '\\u7f6e\\u4fe1\\u5ea6>=60%'")
html = html.replace("'High', '置信度>=50%'", "'\\u5173\\u6ce8', '\\u7f6e\\u4fe1\\u5ea6>=50%'")
html = html.replace("'Medium', '置信度40-50%'", "'\\u89c2\\u671b', '\\u7f6e\\u4fe1\\u5ea6 40-50%'")
html = html.replace("'Low', '置信度<40%'", "'\\u653e\\u5f03', '\\u7f6e\\u4fe1\\u5ea6<40%'")
print('2. Legend updated')

# 5. Update backtest text
html = html.replace('WC2022 Elite', 'WC2022 \\u7cbe\\u9009')
print('3. Backtest text updated')

# 6. Remove group elo chart JS
html = html.replace(
    "const groupCtx = document.getElementById('chartGroups');",
    "/* removed */"
)
# Find and remove the entire group chart block
import re
html = re.sub(
    r'\/\* removed \*/\n.*?group elo chart.*?\n.*?// 4\) Scatter',
    '// 3) [removed]',
    html,
    flags=re.DOTALL
)

# 7. Remove scatter chart JS
scatter_start = html.find("const scatterCtx = document.getElementById('chartScatter')")
scatter_end = html.find("function loadCharts", scatter_start)
if scatter_start >= 0:
    # Find the end of the scatter block (before the catch)
    block_end = html.find("// Load charts", scatter_start)
    html = html[:scatter_start] + html[block_end:]
    print('4. Removed scatter chart JS')

# 8. Update the tier distribution chart to be bigger
html = html.replace("chartTier", "chartTier", 1)  # no-op

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)

print('\\nDone!')
