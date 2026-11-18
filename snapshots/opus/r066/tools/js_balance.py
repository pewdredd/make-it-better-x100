# Проверка главного <script> в index.html без node: строки, шаблоны `${}`, регулярки, комментарии и баланс скобок.
#   python3 tools/js_balance.py index.html
# Это не полноценный парсер, но ловит то, что чаще всего ломает весь сайт: незакрытую скобку, кавычку или шаблон.
import sys, re
src = open(sys.argv[1], encoding='utf8').read()
start = src.index('<script>\n', src.index('</dialog>')) + 9
end = src.rindex('</script>')
s = src[start:end]
base_line = src[:start].count('\n') + 1
stack = []
i, n = 0, len(s)
PAIRS = {')': '(', ']': '[', '}': '{'}
OPEN_TPL = '$' + '{'
last_sig = ''


def line(p):
    return base_line + s[:p].count('\n')


def err(msg, p):
    print('ERR', msg, 'line', line(p))
    sys.exit(1)


mode = ['code']
while i < n:
    c = s[i]
    if mode[-1] == 'tpl':
        if c == '\\':
            i += 2; continue
        if c == '`':
            mode.pop(); last_sig = 'a'; i += 1; continue
        if s.startswith(OPEN_TPL, i):
            mode.append('code'); stack.append((OPEN_TPL, i)); i += 2; last_sig = '{'; continue
        i += 1; continue
    if c in ' \t\r\n':
        i += 1; continue
    if s.startswith('//', i):
        j = s.find('\n', i); i = n if j < 0 else j; continue
    if s.startswith('/*', i):
        i = s.find('*/', i) + 2; continue
    if c in '"\'':
        j = i + 1
        while s[j] != c:
            if s[j] == '\\':
                j += 1
            elif s[j] == '\n':
                err('newline in string', i)
            j += 1
        i = j + 1; last_sig = 'a'; continue
    if c == '`':
        mode.append('tpl'); i += 1; continue
    if c == '/':
        if last_sig in ('', '(', ',', '=', ':', '[', '!', '&', '|', '?', '{', '}', ';', '+', '-', '*', '%', '<', '>', '~', '^') \
                or re.search(r'\b(return|typeof|case|in|of)\s*$', s[max(0, i - 10):i]):
            j = i + 1; cls = False
            while True:
                ch = s[j]
                if ch == '\\':
                    j += 2; continue
                if ch == '\n':
                    err('newline in regex', i)
                if ch == '[':
                    cls = True
                elif ch == ']':
                    cls = False
                elif ch == '/' and not cls:
                    break
                j += 1
            j += 1
            while j < n and s[j].isalpha():
                j += 1
            i = j; last_sig = 'a'; continue
        i += 1; last_sig = '/'; continue
    if c in '([{':
        stack.append((c, i))
    elif c in ')]}':
        if not stack:
            err('unmatched ' + c, i)
        o, p = stack.pop()
        if o == OPEN_TPL:
            if c != '}':
                err('bad close inside template: ' + c, i)
            mode.pop(); i += 1; last_sig = 'a'; continue
        if o != PAIRS[c]:
            err(f'mismatch {o} (line {line(p)}) vs {c}', i)
    last_sig = 'a' if (c.isalnum() or c in '_$') else c
    i += 1
if stack:
    err('unclosed ' + stack[-1][0], stack[-1][1])
if len(mode) != 1:
    err('unclosed template', n - 1)
print('balanced ok, lines', base_line, '-', base_line + s.count('\n'))
