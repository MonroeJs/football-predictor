"""Fix UI v3 - Chinese tier names and redesigned sidebar"""
from pathlib import Path

path = Path(__file__).parent.parent / 'templates' / 'wc_dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Add Chinese tier mapping to JS
html = html.replace(
    'const TIER_COLORS = {',
    'const TIER_CN = {Max:"顶级",Elite:"精选",VHigh:"高信",High:"关注",Medium:"观望",Low:"放弃"};\nconst TIER_COLORS = {'
)

# 2. Replace badge text in HTML templates
html = html.replace(
    '{{ p.tier }}</span>',
    '{{ TIER_CN[p.tier] if p.tier in TIER_CN else p.tier }}</span>'
)

# 3. Find and replace the sidebar charts section
marker1 = '<!-- Charts -->'
marker2 = '<!-- Tier Legend -->'

start = html.find(marker1)
end = html.find(marker2)

if start >= 0 and end >= 0:
    new_sidebar = (
        '        <!-- Confidence Pie (single large chart) -->\n'
        '        <div class="glass-card">\n'
        '            <div class="card-title"><i class="bi bi-pie-chart me-1"></i>置信度分布</div>\n'
        '            <canvas id="chartTier" style="max-height:170px;width:100%"></canvas>\n'
        '        </div>\n'
        '\n'
        '        <!-- Top 5 Picks -->\n'
        '        <div class="glass-card">\n'
        '            <div class="card-title"><i class="bi bi-star-fill text-warning me-1"></i>热门推荐 TOP 5</div>\n'
        '            {% set top_bets = predictions|selectattr(\'suggested_stake\')|list|sort(attribute=\'suggested_stake\', reverse=True) %}\n'
        '            {% if top_bets %}\n'
        '            {% for p in top_bets[:5] %}\n'
        '            <div class="d-flex justify-content-between align-items-center mb-2" style="background:rgba(30,41,59,0.5);border-radius:8px;padding:0.5rem 0.8rem">\n'
        '                <div>\n'
        '                    <div style="font-size:0.8rem;font-weight:600">{{ p.home[:12] }} vs {{ p.away[:12] }}</div>\n'
        '                    <div style="font-size:0.65rem;color:var(--text-secondary)">{{ p.date[5:10] }} | {{ p.confidence }} | +{{ "%.2f"|format(p.fav_odds) }}</div>\n'
        '                </div>\n'
        '                <div style="text-align:right">\n'
        '                    <div style="font-size:0.85rem;font-weight:700;color:var(--accent-green)">{{ "%.0f"|format(p.suggested_stake) }}Y</div>\n'
        '                    <div><span class="badge-tier tier-{{ p.tier }}">{{ TIER_CN[p.tier] if p.tier in TIER_CN else p.tier }}</span></div>\n'
        '                </div>\n'
        '            </div>\n'
        '            {% endfor %}\n'
        '            {% else %}\n'
        '            <div style="text-align:center;padding:1rem;color:var(--text-muted);font-size:0.8rem">暂无推荐</div>\n'
        '            {% endif %}\n'
        '        </div>\n'
        '\n'
        '        <!-- Daily Stakes Chart -->\n'
        '        <div class="glass-card">\n'
        '            <div class="card-title"><i class="bi bi-graph-up me-1"></i>每日推荐金额</div>\n'
        '            <canvas id="chartStakes" style="max-height:130px;width:100%"></canvas>\n'
        '        </div>\n'
        '        \n'
    )
    html = html[:start] + new_sidebar + html[end:]
    print('1. Sidebar charts section replaced')
else:
    print(f'WARNING: markers not found! start={start}, end={end}')

# 4. Update legend to Chinese names
html = html.replace(
    "('Max', '\u7f6e\u4fe1\u5ea6>=80%', '80\u00a5', 'var(--accent-purple)'),",
    "('\u81f3\u5c0a', '\u7f6e\u4fe1\u5ea6>=80%', '80\u00a5', 'var(--accent-purple)'),"
)
html = html.replace("'Elite', '\u7f6e\u4fe1\u5ea6>=70%'", "'\u7cbe\u9009', '\u7f6e\u4fe1\u5ea6>=70%'")
html = html.replace("'VHigh', '\u7f6e\u4fe1\u5ea6>=60%'", "'\u9ad8\u4fe1', '\u7f6e\u4fe1\u5ea6>=60%'")
html = html.replace("'High', '\u7f6e\u4fe1\u5ea6>=50%'", "'\u5173\u6ce8', '\u7f6e\u4fe1\u5ea6>=50%'")
html = html.replace("'Medium', '\u7f6e\u4fe1\u5ea6 40-50%'", "'\u89c2\u671b', '\u7f6e\u4fe1\u5ea6 40-50%'")
html = html.replace("'Low', '\u7f6e\u4fe1\u5ea6<40%'", "'\u653e\u5f03', '\u7f6e\u4fe1\u5ea6<40%'")
print('2. Legend updated')

# 5. Update backtest text
html = html.replace('WC2022 \u7cbe\u9009', 'WC2022 \u7cbe\u9009')  # already done by the badge replacement
html = html.replace('WC2022 Elite', 'WC2022 \u7cbe\u9009')
print('3. Backtest text updated')

# 6. Remove scatter and group chart JS since those canvases are gone
# Find and remove the group chart section
import re

# Remove the group chart block
html = re.sub(
    r"const groupCtx = document\.getElementById\('chartGroups'\);\n.*?(?=const scatterCtx|// Load charts)",
    '',
    html,
    flags=re.DOTALL
)

# Remove the scatter chart block
html = re.sub(
    r"const scatterCtx = document\.getElementById\('chartScatter'\);\n.*?(?=function loadCharts|setTimeout)",
    '',
    html,
    flags=re.DOTALL
)

print('4. Removed unused chart JS')

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)

print('\nDone!')
