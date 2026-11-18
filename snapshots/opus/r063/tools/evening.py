# «Вечерний зал»: из style.css собирает evening.css — тёплую тёмную тему поверх всех правил.
#   python3 tools/evening.py style.css > evening.css      (перезапускать после правок style.css)
# Светлые фоны и рамки темнеют, тёмный текст светлеет (если у правила нет своего тёмного/среднего фона),
# SVG-иллюстрации (fill/stroke) и меловые доски не трогаем. Каскад сохраняется: каждое правило
# повторяется целиком (все background/border/color) с префиксом html.vz, в том же порядке.
import re, colorsys, sys
src = open(sys.argv[1]).read()
src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
ROOT = {'bg':'#f6efe6','ink':'#2a1d15','muted':'#7a6656','brand':'#6b3e26','accent':'#d9822b','card':'#fffaf3','line':'#e7dccd','ok':'#2f8a4f'}
NAMED = {'white':(255,255,255,1),'black':(0,0,0,1)}
COL = re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\b(?:white|black)\b')

def parse(t):
    t0 = t.lower()
    if t0 in NAMED: return NAMED[t0]
    if t0.startswith('#'):
        h = t0[1:]
        if len(h) in (3, 4): h = ''.join(c * 2 for c in h)
        if len(h) not in (6, 8): return None
        r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4)); a = int(h[6:8], 16) / 255 if len(h) == 8 else 1
        return r, g, b, a
    nums = re.findall(r'[\d.]+%?', t0)
    if len(nums) < 3: return None
    def ch(x): return float(x[:-1]) * 2.55 if x.endswith('%') else float(x)
    try:
        r, g, b = (ch(x) for x in nums[:3]); a = 1
        if len(nums) > 3: a = float(nums[3][:-1]) / 100 if nums[3].endswith('%') else float(nums[3])
    except ValueError:
        return None
    return r, g, b, a

def hls(c): return colorsys.rgb_to_hls(c[0]/255, c[1]/255, c[2]/255)
def lum(c): return hls(c)[1]
def out(h, l, s, a):
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s)))
    if a >= 0.999: return '#%02x%02x%02x' % (round(r*255), round(g*255), round(b*255))
    return 'rgba(%d,%d,%d,%.3g)' % (round(r*255), round(g*255), round(b*255), a)
def to_dark(c, base=.095, k=.5):
    h, l, s = hls(c)
    if s < .12: h, s = 28/360, .24
    else: s = min(s, .5) * .75
    return out(h, base + (1 - l) * k, s, c[3])
def to_light(c):
    h, l, s = hls(c)
    if s < .12: h, s = 30/360, .2
    else: s = min(s, .55)
    return out(h, .93 - l * .55, s, c[3])

def resolve(v):
    return re.sub(r'var\(--(bg|ink|muted|brand|accent|card|line|ok)\)', lambda m: ROOT[m.group(1)], v)

def remap(v, fn):
    def rep(m):
        c = parse(m.group(0))
        if c is None: return m.group(0)
        r = fn(c); return m.group(0) if r is None else r
    return COL.sub(rep, v)

def light(c): return lum(c) > .6 and c[3] > 0.02
PAGE = (0xf6, 0xef, 0xe6)  # фон страницы → ровно цвет вечернего зала, чтобы «вырезы» под фон не проступали
def bg_f(c):
    if tuple(round(x) for x in c[:3]) == PAGE: return out(*colorsys.rgb_to_hls(0x15/255, 0x10/255, 0x0c/255), c[3])
    return to_dark(c) if light(c) else None
def bd_f(c): return to_dark(c, .2, .5) if light(c) else None
def sh_f(c):
    if light(c) and c[3] > .85: return to_dark(c)
    if lum(c) < .5 and c[3] < 1: return 'rgba(0,0,0,%.3g)' % min(1, c[3] * 1.4)
    return None
def tx_f(c): return to_light(c) if lum(c) < .45 else None

PROPS = re.compile(r'^(color|background.*|border(?!-radius|-collapse|-spacing).*|outline.*|box-shadow|text-decoration.*|column-rule.*)$')

def split_top(s, sep, opens='(', closes=')'):
    parts, d, cur = [], 0, ''
    for ch in s:
        if ch in opens: d += 1
        elif ch in closes: d -= 1
        if ch == sep and d == 0: parts.append(cur); cur = ''
        else: cur += ch
    parts.append(cur); return parts

def decls(body):
    for p in split_top(body, ';'):
        if ':' in p:
            k, v = p.split(':', 1); k = k.strip().lower()
            if k: yield k, v.strip()

# тёмные контейнеры (меловая доска, ночной первый экран, сторис…) уже рассчитаны на тёмное —
# всё, что лежит внутри них, оставляем как есть: мелок на полочке доски должен остаться белым
GRAD = re.compile(r'(?:repeating-)?(?:linear|radial|conic)-gradient\((?:[^()]|\([^()]*\))*\)')
def base_bg(ds):
    # основной цвет фона: то, что вне градиентов; если фон — только градиент, то все его точки
    out, grad = [], []
    for k, v in ds:
        if not k.startswith('background') or k == 'background-image':
            if k == 'background-image': grad += [parse(x.group(0)) for x in COL.finditer(v)]
            continue
        out += [parse(x.group(0)) for x in COL.finditer(GRAD.sub('', v))]
        grad += [parse(x.group(0)) for g in GRAD.findall(v) for x in COL.finditer(g)]
    return [c for c in (out or grad) if c]

DARK = set()
def collect(s):
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', s):
        sel, body = m.group(1).strip(), m.group(2)
        if sel.startswith('@') or ',' in sel or ':' in sel: continue
        cs = [c for c in base_bg([(k, resolve(v)) for k, v in decls(body)]) if c[3] > .9]
        if cs and not all(light(c) for c in cs): DARK.add(sel)  # фон не перекрашиваем (тёмный, средний, предмет) — и начинку тоже
def inside_dark(s):
    return any(s.startswith(d) and len(s) > len(d) and s[len(d)] in ' >~+' for d in DARK)

def rule(sel, body):
    ds = [(k, resolve(v)) for k, v in decls(body) if PROPS.match(k)]
    if not ds: return ''
    if all(inside_dark(s.strip()) for s in split_top(sel, ',', '([', ')]') if s.strip()):
        ds = [(k, v) for k, v in decls(body) if PROPS.match(k)]
        return ','.join('html.vz ' + s.strip() for s in split_top(sel, ',', '([', ')]') if s.strip()) + '{' + ';'.join('%s:%s' % kv for kv in ds) + '}'
    solid_mid = any(c[3] > .5 and not light(c) for c in base_bg(ds))
    res = []
    for k, v in ds:
        if k.startswith('background'):
            cs = [c for c in (parse(m.group(0)) for m in COL.finditer(v)) if c and c[3] > .5]
            # градиент из светлого и среднего — это нарисованный предмет (монетка, пачка, клапан): не трогаем
            if not (any(light(c) for c in cs) and any(not light(c) for c in cs)): v = remap(v, bg_f)
        elif k == 'box-shadow': v = remap(v, sh_f)
        elif k == 'color':
            if not solid_mid: v = remap(v, tx_f)
        elif k.startswith(('border', 'outline', 'column-rule')): v = remap(v, bd_f)
        elif k.startswith('text-decoration'): v = remap(v, tx_f)
        res.append('%s:%s' % (k, v))
    sels = []
    for s in split_top(sel, ',', '([', ')]'):
        s = s.strip()
        if not s: continue
        if s.startswith(':root'): s = 'html.vz' + s[5:]
        elif re.match(r'html\b', s): s = 'html.vz' + s[4:]
        else: s = 'html.vz ' + s
        sels.append(s)
    return ','.join(sels) + '{' + ';'.join(res) + '}'

def walk(s):
    i, o = 0, []
    while True:
        j = s.find('{', i)
        if j < 0: break
        head = s[i:j].strip()
        d, k = 0, j
        while True:
            if s[k] == '{': d += 1
            elif s[k] == '}':
                d -= 1
                if d == 0: break
            k += 1
        inner = s[j+1:k]
        if head.startswith(('@media', '@supports')):
            r = walk(inner)
            if r: o.append(head + '{\n' + r + '\n}')
        elif not head.startswith('@'):
            r = rule(head, inner)
            if r: o.append(r)
        i = k + 1
    return '\n'.join(o)

print('/* «Вечерний зал» — собрано из style.css скриптом tools/evening.py, руками не править. Ручные правки темы — в tools/evening-hand.css */')
collect(src)
print(walk(src))
import os
print(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evening-hand.css')).read())
