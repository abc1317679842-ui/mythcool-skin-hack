# -*- coding: utf-8 -*-
"""校验 inject_main 源文件：Python 语法 + 三段 JS 语法 + 关键标记 + STALE 洁净断言。

用法：
  <python> "<本文件>" <inject_main 源文件路径>

退出码：0 全绿 / 1 有问题
"""
import ast
import json
import re
import subprocess
import sys
import os
import glob
import tempfile

if len(sys.argv) < 2:
    print('用法: <python> "%s" <inject_main 源文件路径>' % os.path.abspath(__file__))
    sys.exit(2)
SRC = sys.argv[1]

# ★ node 变体名不固定：先试 versions\current，再 Glob 兜底
def find_node():
    base = os.path.join(os.path.expanduser('~'), '.workbuddy', 'binaries', 'node', 'versions')
    cur = os.path.join(base, 'current', 'node.exe')
    if os.path.exists(cur):
        return cur
    cands = sorted(glob.glob(os.path.join(base, '*', 'node.exe')))
    return cands[-1] if cands else None

NODE = find_node()
TMP = os.path.join(tempfile.gettempdir(), 'mtc_synchk')

if not os.path.exists(SRC):
    print('[FAIL] 源文件不存在: %s' % SRC)
    sys.exit(2)
if not NODE:
    print('[FAIL] 找不到 node.exe（已试 versions\\current 与 Glob 兜底）')
    print('       没有 node 就无法做 JS 语法校验 —— 请先确认 binaries/node 是否完好')
    sys.exit(2)
print('node = %s' % NODE)

src = open(SRC, encoding='utf-8').read()
print('文件 %s  长度 %d' % (SRC, len(src)))

# 1) Python 语法
try:
    ast.parse(src)
    print('[OK] Python AST')
except SyntaxError as e:
    print('[FAIL] Python: %s line %s' % (e, e.lineno))
    sys.exit(1)

# 2) 取三段
blocks = {}
for name in ('PATCH', 'MAIN', 'JS'):
    m = re.search(r"^%s = r'''\n(.*?)\n'''" % name, src, re.S | re.M)
    if not m:
        print('[FAIL] 找不到 %s 块' % name)
        sys.exit(1)
    blocks[name] = m.group(1)
    print('  块 %-6s %d 字节' % (name, len(blocks[name])))

os.makedirs(TMP, exist_ok=True)

# 3) JS 语法检查（把占位符换成合法内容）
def jscheck(name, code, extra_repl=None):
    c = code
    for k, v in (extra_repl or {}).items():
        c = c.replace(k, v)
    p = os.path.join(TMP, name + '.js')
    open(p, 'w', encoding='utf-8').write(c)
    r = subprocess.run([NODE, '--check', p], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode == 0:
        print('[OK] JS %s 语法' % name)
        return True
    print('[FAIL] JS %s:\n%s\n%s' % (name, r.stdout, r.stderr))
    return False

ok = True
# JS 块含 __MAIN__ / __PATCH__ 占位，替换成 'x' 即可
ok &= jscheck('JS', blocks['JS'], {'__MAIN__': '"x"', '__PATCH__': '"x"'})
ok &= jscheck('MAIN', blocks['MAIN'], {
    'OUTJSON': '"/tmp/o.json"', 'TUNEPATHX': '"/tmp/t.json"',
    'TUNEACKX': '"/tmp/a.txt"',
    'PATCHCODE': '"x"', 'DIAGJS': '"x"',
})
ok &= jscheck('PATCH', blocks['PATCH'])

# 4) 关键标记
# ★ 分两级：CORE 是【跨版本必须存在】的不变量；EXTRA 是当前版本特有的改动点。
#   CORE 缺失 = FAIL（说明拿到的是残缺/被截断的源，或改坏了地基）。
#   EXTRA 缺失 = WARN（可能只是版本演进了，人工确认一下）。
CORE = [
    ("ensureLayer", "浮层创建/搬迁函数"),
    ("mainpage_jx", "旋转坐标系宿主（挂 body 会差 90 度）"),
    ("cleanJson", "BOM 剥离（tune.json 带 BOM）"),
    ("MTC_GUARD", "MO 重入守卫（切断自触发链）"),
    ("var STALE", "历史残留清理列表"),
    ("function refresh", "统一刷新入口"),
]
EXTRA = [
    ("layerHost", "v17 宿主 fallback 链"),
    ("applyN", "v17 applyAll 计数"),
    ("v17 关键修正", "v17 cleanOld 修正说明"),
    ("s.__mtc_css !== _css", "v17 样式表内容去重"),
    ("__mtc_v13timer", "v13 自带节拍器（刷新节拍，与 beat 无关）"),
]
print('--- CORE 标记（缺失即 FAIL）---')
for mk, desc in CORE:
    n = src.count(mk)
    print('  [%s] %-24s x%d  (%s)' % ('OK ' if n else 'MISS', mk[:24], n, desc))
    if not n:
        ok = False

print('--- EXTRA 标记（缺失仅 WARN）---')
warn = 0
for mk, desc in EXTRA:
    n = src.count(mk)
    if not n:
        warn += 1
    print('  [%s] %-24s x%d  (%s)' % ('OK ' if n else 'WARN', mk[:24], n, desc))
if warn:
    print('  (有 %d 项缺失 —— 若是有意演进到新版本，忽略；否则检查改动是否漏了)' % warn)

# 4b) 版本号一致性（★v20 起三处）：Python 头 VER = N / RES = { v: N } / RES.ver = N
vers = set()
for pat in (r"^VER = (\d+)", r"RES = \{ v: (\d+) \}", r"RES\.ver = (\d+)"):
    for mm in re.finditer(pat, src, re.M):
        vers.add(mm.group(1))
if len(vers) == 1:
    print('[OK] 版本号一致（三处同值）: v%s' % list(vers)[0])
else:
    print('[FAIL] 版本号不一致（三处应为同一值: VER / RES={v:N} / RES.ver）: %s' % sorted(vers))
    ok = False

# 5) ★★★ 最关键的一条：STALE 里【不能】出现当前版本正在用的 id
#    历史事故：STALE 误列了 __mtc_layer / __mtc_v13css，导致每次 applyAll()
#    都把浮层和整张样式表删掉重建 -> 每次热调都闪一下。
#    通用判据：把"被 getElementById 读取"或"被 .id = 赋值"的 id 全找出来，
#    与 STALE 求交集 —— 交集非空即 FAIL（跨版本有效，不依赖硬编码 id）。
m = re.search(r"var STALE = \[(.*?)\];", src, re.S)
if m:
    stale_block = m.group(1)
    stale_ids = re.findall(r"'([^']+)'", stale_block)
    live_ids = set(re.findall(r"getElementById\('([^']+)'\)", src))
    live_ids |= set(re.findall(r"\.id\s*=\s*'([^']+)'", src))
    conflict = sorted(set(stale_ids) & live_ids)
    print('--- STALE 洁净断言 ---')
    print('  STALE 列表 : %s' % stale_ids)
    print('  当前活节点 : %s' % sorted(live_ids))
    if conflict:
        print('  [FAIL] STALE 与活节点冲突: %s' % conflict)
        print('         => 每次 applyAll() 都会删掉它们再重建，表现为「热调就闪」')
        ok = False
    else:
        print('  [OK] 无冲突')
else:
    print('[FAIL] 找不到 var STALE 定义')
    ok = False

# 6) 浮层搬迁逻辑（v17 起）：缺了只 WARN
if 'host.appendChild(L);' in src and 'L.parentNode === host' in src:
    print('[OK] ensureLayer 含搬迁逻辑（挂错宿主会搬回来）')
elif 'appendChild(L)' in src:
    print('[WARN] ensureLayer 只创建不搬迁 —— 若浮层挂错宿主不会自愈')
else:
    print('[WARN] 未见浮层搬迁逻辑')

# 7) ★ v19 起：beat 诊断机制必须【彻底不存在】
#    用户明确要求「不要开机就每分钟记录数据」——
#    指向 v18 主进程侧那个 setInterval(60000) + fs.writeFileSync 的 beat dump。
#    只要有一个特征串残留，就说明还有每分钟写盘的路径。
print('--- beat 移除断言（v19 起）---')
BEAT_TOKENS = ['window.__MTC_BEAT', 'BEATTIMER', 'RINGMAX', 'RING.push',
               '_beatDump', 'last_beat', 'var BEAT =', 'function mark(']
beatleft = [(t, src.count(t)) for t in BEAT_TOKENS if src.count(t)]
if beatleft:
    print('  [FAIL] beat 残留: %s' % beatleft)
    print('         => 主进程侧 setInterval(60000) + fs.writeFileSync 会每分钟写盘')
    ok = False
else:
    print('  [OK] beat 已彻底移除（%d 个特征串全部为 0）' % len(BEAT_TOKENS))

print('=== %s ===' % ('全部通过' if ok else '存在问题'))
sys.exit(0 if ok else 1)
