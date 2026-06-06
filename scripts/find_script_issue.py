"""Find script tag mismatch"""
import urllib.request, re

r = urllib.request.urlopen('http://127.0.0.1:5001/wc2026', timeout=15)
html = r.read().decode('utf-8')

# Find all script positions
for m in re.finditer(r'<script[^>]*>', html):
    print(f'OPEN {m.start()}: {m.group()[:60]}')
    # Find next close
    close = html.find('</script>', m.end())
    if close >= 0:
        content = html[m.end():close]
        print(f'  Content: {content[:80]}')
        print(f'  Close at: {close}')
    else:
        print(f'  NO CLOSE FOUND!')

# Find all closes
for m in re.finditer(r'</script>', html):
    print(f'CLOSE {m.start()}: ...')
