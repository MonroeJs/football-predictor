"""Deep debug of rendered JS"""
from wc_app import app

with app.test_client() as c:
    r = c.get('/')
    html = r.data.decode('utf-8')

# Find the last script block (main JS)
script_start = html.rfind('<script>')
script_end = html.rfind('</script>')
js = html[script_start+8:script_end]

print(f'=== JS block length: {len(js)} chars ===')

# 1. Check for common JS syntax errors
lines = js.split('\n')
for i, line in enumerate(lines):
    stripped = line.strip()
    # Skip empty lines and comments
    if not stripped or stripped.startswith('//'):
        continue
    # Check for template artifacts
    if '__' in stripped and stripped.count('__') >= 2:
        print(f'LINE {i+1}: Possible undefined Jinja2 artifact: {stripped[:80]}')
    # Check for "Variable" is not defined pattern
    if 'is not defined' in stripped.lower():
        print(f'LINE {i+1}: Reference error: {stripped[:80]}')

# 2. Check the pill handler
if 'querySelectorAll' in js:
    idx = js.find('querySelectorAll')
    handler_code = js[idx:idx+400]
    # Check for common errors
    if 'data-section' not in js:
        print('WARNING: data-section not in JS (but it should be in HTML)')
    print(f'\nPill handler (first 400 chars):\n{handler_code[:400]}\n')

# 3. Check chart init
if 'loadCharts' in js:
    idx = js.find('function loadCharts')
    chart_code = js[idx:idx+1200]
    print(f'loadCharts code:\n{chart_code[:1200]}\n')

# 4. Check for TIER_CN duplicates
tier_count = js.count('TIER_CN')
print(f'TIER_CN refs in JS: {tier_count}')

# 5. Check Chart.js CDN
if 'chart.js' in html.lower():
    idx = html.lower().find('chart.js')
    print(f'Chart.js CDN at: {html[idx-20:idx+60]}')

# 6. Check page structure
print(f'\ndata-section buttons: {html.count("data-section")}')
print(f'section-content divs: {html.count("section-content")}')

# 7. Check for the actual chart canvases
for cid in ['chartTier', 'chartStakes']:
    if cid in html:
        idx = html.find(cid)
        print(f'{cid} in HTML at {idx}: ..{html[idx-10:idx+30]}..')

# 8. Print the exact JS between document.ready and the first function
start_idx = js.find('(function')
if start_idx < 0:
    start_idx = 0
print(f'\n=== First 30 lines of JS ===')
for i, line in enumerate(lines[:30]):
    print(f'{i+1}: {line}')
