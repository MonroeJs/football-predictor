"""Test tracking tab rendering"""
import sys; sys.path.insert(0,'.')
from app import app

with app.test_client() as c:
    r = c.get('/wc2026')
    html = r.data.decode('utf-8')
    print('sec-track:', 'sec-track' in html)
    print('resultModal:', 'resultModal' in html)
    print('tracking tab:', 'data-sec="track"' in html)
    print('tracking text:', '实时追踪' in html)
    
    # Check if the league key condition is working
    # Look for what's after the if condition
    idx = html.find('data.league')
    if idx >= 0:
        print(f'data.league at {idx}: {html[idx:idx+50]}')
    else:
        # Check rendered template
        # Maybe data.league doesn't have key?
        print('data.league not found in rendered HTML')
        print('Looking for "track":')
        tidx = html.find('data-sec="track"')
        if tidx >= 0:
            print(f'Found at {tidx}')
        sidx = html.find('sec-track')
        if sidx >= 0:
            print(f'sec-track at {sidx}')
        else:
            # Check the raw template for the condition
            with open('templates/dashboard.html', 'r') as f:
                tmpl = f.read()
            cidx = tmpl.find('league.key')
            if cidx >= 0:
                print(f'\nIn template: {tmpl[cidx-20:cidx+60]}')
