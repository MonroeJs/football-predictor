"""Fix: nav pills + add refresh button"""
from pathlib import Path

path = Path(__file__).parent.parent / 'templates' / 'dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Fix nav pills - the click handler might be broken by multiple scripts
# Check if Bootstrap's button handling is interfering
# Let's check the actual JS structure
idx = html.rfind('<script>')
idx2 = html.rfind('</script>')
print(f'Script block: {idx} to {idx2} ({idx2-idx} chars)')
print(f'Found navPills: {"navPills" in html[idx:idx2]}')

# 2. Add refresh odds button in tracking section  
old_track_header = '''      <span><i class="bi bi-graph-up-arrow me-1"></i>实时追踪</span>
      <span style="font-size:.7rem;color:var(--muted)">开赛后自动更新</span>'''
new_track_header = '''      <span><i class="bi bi-graph-up-arrow me-1"></i>实时追踪</span>
      <span style="font-size:.7rem;color:var(--muted)">
        <button class="btn btn-sm btn-outline-primary me-2" onclick="refreshOdds()" style="font-size:.7rem;padding:.1rem .4rem">
          <i class="bi bi-arrow-clockwise"></i> 刷新赔率
        </button>
        开赛后自动更新
      </span>'''
html = html.replace(old_track_header, new_track_header)
if old_track_header not in html:
    print('Track header replaced')
else:
    print('Track header replacement failed?')

# 3. Add refreshOdds JS function before the closing script
refresh_js = '''
function refreshOdds() {
  var btn = event.target;
  btn.disabled = true;
  btn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> 刷新中...';
  fetch('/api/wc2026/refresh-odds', {method:'POST'})
    .then(function(r){ return r.json(); })
    .then(function(data){
      btn.innerHTML = '<i class="bi bi-check"></i> 已更新 '+data.updated+' 场';
      setTimeout(function(){ btn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> 刷新赔率'; btn.disabled = false; }, 2000);
    })
    .catch(function(e){ btn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> 失败'; btn.disabled = false; });
}
'''
html = html.replace('</script>\n</body>', refresh_js + '</script>\n</body>')
if '</script>\n</body>' not in html:
    print('Refresh JS added')
else:
    print('Refresh JS replacement failed')

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('\nDone')
