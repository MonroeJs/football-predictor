"""Verify all fixes are working"""
import urllib.request, re

r = urllib.request.urlopen('http://127.0.0.1:5001/wc2026', timeout=20)
h = r.read().decode('utf-8')

print(f'Status: {r.status}')
print(f'Size: {len(h)}B')
print(f'Script balance: {h.count("<script")} / {h.count("</script>")}')
print(f'RefreshOdds: {"refreshOdds" in h}')
print(f'NavPills: {"navPills" in h}')
print(f'RecordResult: {"recordResult" in h}')
print(f'ResultModal: {"resultModal" in h}')
sections = re.findall(r'data-sec="([^"]+)"', h)
print(f'Sections: {sections}')
