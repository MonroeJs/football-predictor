"""Quick test"""
import urllib.request, re

html = urllib.request.urlopen('http://127.0.0.1:5000/').read().decode('utf-8')

# Badge text
matches = re.findall(r'badge-tier tier-\w+">([^<]+)', html)
print('Badges:', list(set(matches)))
print('section-content:', html.count('section-content'))
print('chartTier:', 'chartTier' in html)
print('chartStakes:', 'chartStakes' in html)
print('TIER_CN:', 'TIER_CN' in html)

# Check specific Chinese chars
for c in ['至尊', '精选', '高信', '关注', '观望', '放弃']:
    print(f'  {c}: {c in html}')
