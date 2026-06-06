"""Debug JS rendering issues"""
from wc_app import app
import re

with app.test_client() as c:
    r = c.get('/')
    html = r.data.decode('utf-8')

# Find the main script block
script_idx = html.rfind('<script>')
script_close = html.rfind('</script>')
js = html[script_idx+8:script_close]

print('=== Checking TIER_CN in rendered HTML ===')
# TIER_CN should be defined in JS and used in template
# Check if TIER_CN appears in badge text
for match in re.finditer(r'badge-tier tier-\w+\">([^<]+)</span>', html):
    print(f'Badge: [{match.group(1)}]')
    if not match.group(1).strip():
        print('WARNING: Empty badge text! TIER_CN not in Jinja2 context')
    break

print(f'\n=== JS block length: {len(js)} chars ===')
print(f'First 200: {js[:200]}')
print(f'\nPill handler check: {"data-section" in js}')
print(f'loadCharts check: {"loadCharts" in js}')

# Check for chartTier canvas in sidebar
tier_idx = html.find('id="chartTier"')
if tier_idx >= 0:
    print(f'\nchartTier canvas context: {html[tier_idx-30:tier_idx+50]}')

# Check if Chart.js loaded
print(f'\nChart.js: {"chart.js" in html.lower() or "Chart.js" in html}')

# Find TIER_CN in the actual template file (not rendered)
with open('templates/wc_dashboard.html', 'r', encoding='utf-8') as f:
    template = f.read()
    
# Check if {{ TIER_CN[ }} appears in template - this would be a Jinja2 error
if 'TIER_CN[' in template and 'TIER_CN' not in str(app.jinja_env.globals):
    # Check if the template has TIER_CN references
    idcs = [i for i in range(len(template)) if template[i:i+7] == 'TIER_CN']
    for idx in idcs:
        print(f'\nTIER_CN in template at {idx}: {template[max(0,idx-15):idx+25]}')

# Check jinja env
print(f'\nJinja undefined mode: {app.jinja_env.undefined}')
