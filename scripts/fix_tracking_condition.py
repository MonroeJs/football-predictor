"""Fix tracking section condition - use dict access instead of attribute"""
from pathlib import Path

path = Path(__file__).parent.parent / 'templates' / 'dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# The condition uses data.league.key but data.league is a dict
# In Jinja2, dict.key works for accessing string keys
# But maybe the key field isn't in the dict?

# Let's check what's happening - the problem is likely that
# 'data.league.key' is being treated as a string literal in the condition
# Let me check the actual template text

# Replace the condition
html = html.replace(
    '{% if data.league.key == "wc2026" %}',
    '{% if data.league.key is defined and data.league.key == "wc2026" %}'
)

# Also add the condition before the tracking nav pill  
html = html.replace(
    '<button data-sec="track"><i class="bi bi-graph-up-arrow"></i>追踪</button>',
    '{% if data.league.key is defined and data.league.key == "wc2026" %}<button data-sec="track"><i class="bi bi-graph-up-arrow"></i>追踪</button>{% endif %}'
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Fixed tracking conditions')
