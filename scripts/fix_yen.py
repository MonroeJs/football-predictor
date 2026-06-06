"""Fix Y to yen sign in template"""
from pathlib import Path
path = Path(__file__).parent.parent / 'templates' / 'wc_dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()
# Replace the literal "Y" after stake with yen sign
# Only the one in the TOP 5 section
html = html.replace('%.0f"|format(p.suggested_stake) }}Y', '%.0f"|format(p.suggested_stake) }}\u00a5')
with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Fixed')
