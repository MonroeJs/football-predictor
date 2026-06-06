"""Fix backtest section: use Chinese tier names"""
from pathlib import Path
path = Path(__file__).parent.parent / 'templates' / 'wc_dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace(
    '<span class="badge-tier tier-{{ t }}">{{ t }}</span>',
    '<span class="badge-tier tier-{{ t }}">{{ TIER_CN.get(t, t) }}</span>'
)

# Also fix the legend's hardcoded TIER_CN references - replace English display with already-Chinese
# The legend was already updated in fix_ui_v3.py

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Fixed')
