"""Test page for bugs"""
import sys; sys.path.insert(0,'.')
from app import app
import re

with app.test_client() as c:
    r = c.get('/wc2026')
    html = r.data.decode('utf-8')

    # 1. Check for unrendered Jinja2 variables
    unrendered = re.findall(r'{{[^}]+}}', html)
    if unrendered:
        print(f'UNRENDERED Jinja2 vars ({len(unrendered)}):')
        for v in unrendered[:15]:
            print(f'  {v[:80]}')
    else:
        print('OK: No unrendered Jinja2 vars')

    # 2. Check for common elements
    for label, term in [
        ('tracking tab', 'data-sec="track"'),
        ('tracking section', 'sec-track'),
        ('result modal', 'resultModal'),
        ('recordResult JS', 'recordResult'),
        ('submitResult JS', 'submitResult'),
    ]:
        if term in html:
            print(f'OK: {label}')
        else:
            print(f'MISS: {label}')

    # 3. Show section IDs to verify all exist
    sections = re.findall(r'id="sec-([^"]+)"', html)
    print(f'\nSections found: {sections}')
    
    # 4. Check for cross-leakage in other leagues (skip EPL - slow ML)
    r2 = c.get('/')
    html2 = r2.data.decode('utf-8')
    has_track = 'data-sec="track"' in html2
    print(f'{"BUG" if has_track else "OK"}: Root page has tracking tab = {has_track}')
    
    # 5. Print first 500 chars for quick inspect
    print(f'\nPage size: {len(html)} bytes')
    print(f'First 500 chars:')
    print(html[:500])
