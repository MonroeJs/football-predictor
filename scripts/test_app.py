"""Test Flask app"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from wc_app import app
from datetime import datetime

@app.context_processor
def inject_datetime():
    return {'datetime': datetime}

with app.test_client() as c:
    r = c.get('/')
    print(f'GET / status={r.status_code} length={len(r.data)}')
    if r.status_code == 200:
        body = r.data.decode('utf-8')
        checks = ['2026', 'VHigh', 'Elite', 'Max', '世界杯', '预测', 'Group']
        for check in checks:
            if check in body:
                print(f'  OK: contains "{check}"')
            else:
                print(f'  MISSING: "{check}"')
    else:
        print(f'ERROR response: {r.data.decode()[:200]}')
