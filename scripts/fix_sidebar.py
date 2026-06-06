"""Fix sidebar: rename tiers, replace charts with useful content"""
from pathlib import Path

# 1. Fix tier naming in wc_predictor.py
path1 = Path(__file__).parent.parent / 'src' / 'wc_predictor.py'
with open(path1, 'r', encoding='utf-8') as f:
    content = f.read()

# In the predict_match method, tier_stakes uses tier.value
# The ConfidenceTier enum values are Low, Medium, High, VHigh, Elite, Max
# We don't change the enum, just the display names in HTML

# But the _get_analysis_text method uses tier.value for display
# Let's just leave the Python code as-is and fix the display in HTML/JS

# 2. Fix tier display in wc_app.py - add tier name mapping
path2 = Path(__file__).parent.parent / 'wc_app.py'
with open(path2, 'r', encoding='utf-8') as f:
    content = f.read()

# Add tier name mapping to template context
old_inject = (
    "@app.context_processor\n"
    "def inject_helpers():\n"
    "    return {\n"
    "        'datetime': dt_module,\n"
    "        'dt_module': dt_module,\n"
    "        'json': json,\n"
    "    }"
)
new_inject = (
    "@app.context_processor\n"
    "def inject_helpers():\n"
    "    return {\n"
    "        'datetime': dt_module,\n"
    "        'dt_module': dt_module,\n"
    "        'json': json,\n"
    "        'tier_names': {\n"
    "            'Max': 'max',\n"
    "            'Elite': 'elite',\n"
    "            'VHigh': 'vhigh',\n"
    "            'High': 'high',\n"
    "            'Medium': 'medium',\n"
    "            'Low': 'low',\n"
    "        },\n"
    "    }"
)
assert old_inject in content, "inject_helpers not found!"
content = content.replace(old_inject, new_inject)
with open(path2, 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated wc_app.py template context')

# 3. Rewrite the template with Chinese tier names and improved sidebar
path3 = Path(__file__).parent.parent / 'templates' / 'wc_dashboard.html'
with open(path3, 'r', encoding='utf-8') as f:
    html = f.read()

# Replace English tier names with Chinese in display
replacements = [
    # Badge styles
    ('tier-Max {', 'tier-Max {'),
    ('tier-Elite {', 'tier-Elite {'),
    ('tier-VHigh {', 'tier-VHigh {'),
    ('tier-High {', 'tier-High {'),
    # Tier labels in legend
    ('Max', '至尊'),
    ('Elite', '精选'),
    ('VHigh', '高信'),
    ('High', '关注'),
    ('Medium', '观望'),
    ('Low', '放弃'),
]

# But we need to be careful - only replace display text, not CSS classes or variable names
# The tier names appear as:
# 1. Badge text: {{ p.tier }} → need CSS class to stay English, display to be Chinese
# 2. Legend list
# 3. Chart data labels

# Better approach: add a JS mapping for display names
# And in HTML templates, use a tier_display dict

# Let me just add a Jinja2 filter or dict for tier display names
# Find the section where tier badges are rendered in the match table

# Actually, the simplest approach: add a tier_display dict to the HTML template and use it
# Or even simpler: just change the display text in the legend and keep the badges as-is
# since the tier name is mostly shown as a CSS class badge "Max" which looks fine

print('Tier renaming will be handled in the template rewrite')

print('\nDone - need to rewrite template sidebar')
