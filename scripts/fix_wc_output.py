"""Fix the print_predictions method in wc_predictor.py"""
from pathlib import Path

path = Path(__file__).parent.parent / 'src' / 'wc_predictor.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Line-by-line replacements
replacements = [
    # Header
    ('        print(f\'\n{"="*80}\')\n'
     '        print(\'  世界杯 2026 比赛预测\')\n'
     '        print(f\'{"="*80}\')\n'
     '        print(f\'  {"日期":10s} {"小组":4s} {"主队":16s} {"客队":16s}'
     ' {"预测":6s} {"置信度":8s} {"分级":8s} {"建议仓位":>10s}\')\n'
     '        print(f\'  {"─"*80}\')',
     
     '        print(f\'\n{"="*90}\')\n'
     '        print(\'  2026 世界杯小组赛预测\')\n'
     '        print(f\'{"="*90}\')\n'
     '        print(f\'  {"日期":10s} {"组":3s} {"主队":16s} {"客队":16s}'
     ' {"预测":6s} {"置信度":8s} {"分级":8s} {"赔率":6s} {"建议":>10s}\')\n'
     '        print(f\'  {"─"*90}\')'),
    
    # Row
    ('            outcome = {\'H\': \'主胜\', \'D\': \'平局\', \'A\': \'客胜\'}.get(p[\'predicted_outcome\'], \'?\')',
     '            outcome = {\'H\': \'主胜\', \'D\': \'平局\', \'A\': \'客胜\'}.get(p[\'predicted_outcome\'], \'?\')'),
    
    ('            stake = p.get(\'suggested_stake\', 0)',
     '            stake = p.get(\'suggested_stake\', 0)\n'
     '            fav_odds = p.get(\'fav_odds\', 0)'),
    
    ('            stake_str = f\'${stake:.0f}\' if stake > 0 else \'-\'',
     '            stake_str = f\'${stake:.0f}\' if stake > 0 else \'-\''),
    
    ('            print(f\'  {date:10s} {group:4s} {home:16s} {away:16s} \'\n'
     '                  f\'{outcome:6s} {conf:8s} {tier:8s} {stake_str:>10s}\')',
     '            print(f\'  {date:10s} {group:3s} {home:16s} {away:16s} \'\n'
     '                  f\'{outcome:6s} {conf:8s} {tier:8s} {fav_odds:<6.2f} {stake_str:>10s}\')'),
]

count = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        count += 1
        print(f'Replacement {count}: OK')
    else:
        print(f'Replacement failed for: {old[:60]}...')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nDone! Applied {count} replacements.')
