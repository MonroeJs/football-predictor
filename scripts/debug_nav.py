"""Debug nav pills vs sections"""
import sys; sys.path.insert(0,'.')
from app import app
import re

with app.test_client() as c:
    r = c.get('/wc2026')
    html = r.data.decode('utf-8')

# Check nav buttons vs section IDs
sections = re.findall(r'data-sec="([^"]+)"', html)
sec_ids = re.findall(r'id="sec-([^"]+)"', html)

print('Nav buttons:', sections)
print('Sections:', sec_ids)
print(f'Match: {sorted(sections) == sorted(sec_ids)}')

# Also check the CSS - .sec has display:none but only when JS runs
# Check if the active section shows
if 'sec active' in html or 'class="sec active"' in html:
    print('Has active section')
else:
    print('No active section found!')

# Check the first nav button is active
if 'class="active"' in html:
    print('Has active nav button')
else:
    print('WARNING: No active nav button!')
