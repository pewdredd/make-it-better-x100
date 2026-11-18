# проверка «Вечернего зала»: правила, где фон и текст заданы вместе, а контраст в evening.css < 3:1
#   python3 tools/evening_check.py evening.css
import re, sys
sys.path.insert(0, __import__('os').path.dirname(__file__))
src = open(sys.argv[1]).read()
COL = re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\b(?:white|black)\b')
def parse(t):
    t = t.lower()
    if t == 'white': return (255, 255, 255, 1)
    if t == 'black': return (0, 0, 0, 1)
    if t.startswith('#'):
        h = t[1:]
        if len(h) in (3, 4): h = ''.join(c * 2 for c in h)
        if len(h) not in (6, 8): return None
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + ((int(h[6:8], 16) / 255) if len(h) == 8 else 1,)
    n = re.findall(r'[\d.]+', t)
    return (float(n[0]), float(n[1]), float(n[2]), float(n[3]) if len(n) > 3 else 1) if len(n) >= 3 else None
def rl(c):
    f = lambda v: (v / 255 / 12.92) if v / 255 <= .03928 else ((v / 255 + .055) / 1.055) ** 2.4
    return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2])
def cr(a, b):
    x, y = sorted((rl(a), rl(b)), reverse=True); return (x + .05) / (y + .05)
bad = 0
for m in re.finditer(r'(html\.vz[^{}]*)\{([^{}]*)\}', src):
    sel, body = m.groups()
    fg = re.search(r'(?:^|;)color:([^;]+)', body); bg = re.search(r'background(?:-color)?:([^;]+)', body)
    if not fg or not bg: continue
    f = [parse(x.group(0)) for x in COL.finditer(fg.group(1))]; b = [parse(x.group(0)) for x in COL.finditer(bg.group(1))]
    f = [c for c in f if c and c[3] > .9]; b = [c for c in b if c and c[3] > .9]
    if not f or not b: continue
    r = min(cr(f[0], c) for c in b)
    if r < 3: bad += 1; print('%.1f' % r, sel[:90], '|', fg.group(1)[:30], '|', bg.group(1)[:50])
print('низкий контраст:', bad)
