"""Fix JS structure - remove nested script tag"""
from pathlib import Path

path = Path(__file__).parent.parent / 'templates' / 'dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Find the problematic area: the main script block has an extra <script> tag inside
# The fix: find the last </script> in the file, work backwards
last_close = html.rfind('</script>')
last_open = html.rfind('<script>', 0, last_close)

print(f'Last script block: {last_open} to {last_close}')

# The content between last_open and last_close is the LAST script block
# But there might be a SECOND script block that was incorrectly inserted

# Check if there's a <script> between the second-to-last </script> and the last one
second_last_close = html.rfind('</script>', 0, last_open)
if second_last_close > 0:
    between = html[second_last_close+9:last_open]
    if '<script>' in between:
        print('Found nested script tag! Fixing...')
        # Remove the </script><script> pattern
        html = html.replace(
            '</script>\n<script>\n// Result recording',
            '\n// Result recording'
        )
        # Also remove any double </script>
        html = html.replace('</script>\n</script>', '</script>')

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Fixed JS structure')

# Verify
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()
opens = [i for i in range(len(html)) if html.startswith('<script', i)]
closes = [i for i in range(len(html)) if html.startswith('</script>', i)]
print(f'Script opens: {len(opens)}, closes: {len(closes)}')
print(f'Match: {len(opens) == len(closes)}')
