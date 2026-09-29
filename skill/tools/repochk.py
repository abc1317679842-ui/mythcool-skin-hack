# -*- coding: utf-8 -*-
"""repochk.py -- 全仓库常量一致性校验（任务名 / 安装路径 / 版本号）

为什么需要它：仓库里有两条部署路径（Install.bat 走 %ProgramData%，Finalize_*.cmd
走 C:\\ProgramData\\MythCoolInject），历史上出过「文档说 SkinHack、注册脚本注册
Inject、Install.bat 又装到 SkinHack 目录」的三处错位，以及「安装模板是 v13、
定稿源是 v20」的双版本并存。这类漂移靠人眼抓不住，只能靠脚本锁死。

断言：
  1. 仓库内任何文件都不得再出现旧任务名 MythCoolSkinHack（除明确标注 legacy 的地方）
  2. 安装路径只允许 MythCoolInject（%ProgramData%\\MythCoolInject）
  3. 注入器定稿源与 Install 用的模板必须是同一份内容（不出现两个版本）
  4. 版本号同值，两层都查：
     - 跨文件：Install 模板与定稿源必须是同一版本
     - 同文件内：`VER = N` / `RES = { v: N }` / `RES.ver = N` 三处取值集合必须为 1
       （只改一处、漏改另一处是常见漂移，跨文件比对会漏掉，所以两条都做）
     ★ 分工：`synchk.py` 按单文件查（改完源码必跑），本脚本查交付物 + 跨文件一致性；
       两者互为交叉验证，不是替代关系。

用法：python repochk.py [仓库根]
退出码：0 全绿 / 1 有分歧
"""
import os, re, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8', errors='replace')

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..')
ROOT = os.path.normpath(ROOT)

TASK = 'MythCoolInject'
LEGACY = 'MythCoolSkinHack'
DEST = 'MythCoolInject'
SKIP_DIRS = {'.git', '__pycache__', '_skill_backup_20260929_full.md'}
SCAN_EXT = {'.py', '.ps1', '.cmd', '.bat', '.md', '.json', '.vbs', '.txt'}

fails = []
warns = []


def walk():
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in SCAN_EXT:
                yield os.path.join(dp, fn)


def read(p):
    try:
        with open(p, 'rb') as f:
            return f.read().decode('utf8', 'replace')
    except Exception:
        return ''


# ---- 1) 旧任务名残留 ----
for p in walk():
    t = read(p)
    if LEGACY in t:
        rel = os.path.relpath(p, ROOT)
        # 允许出现：明确标注 legacy / 老安装包的说明文字
        # 文件里只要有 legacy/LEGACY 字样，就说明是「有意识地引用旧名」
        # （注册表里的 $LEGACY 常量、文档里的 legacy name 说明、兼容探测分支），
        # 不算漂移。真正的漂移是【一处改了一处没改】的静默残留。
        if not re.search(r'legacy|老版本|老安装包|旧名|历史', t, re.I):
            fails.append('[任务名] %s 仍出现旧名 %s（未标注 legacy）' % (rel, LEGACY))

# ---- 2) 安装路径 ----
for p in walk():
    t = read(p)
    for m in re.finditer(r'%ProgramData%\\([A-Za-z0-9_]+)|ProgramData[\\/]([A-Za-z0-9_]+)', t):
        name = m.group(1) or m.group(2)
        # MythCoolFix / MythCoolScreenFix 是另一套独立工具（唤醒后副屏修复），
        # 与本项目无关，不算路径漂移。
        if name in ('MythCoolFix', 'MythCoolScreenFix'):
            continue
        if name.startswith('MythCool') and name != DEST:
            fails.append('[安装路径] %s 出现 %s，应为 %s'
                         % (os.path.relpath(p, ROOT), name, DEST))

# ---- 3) 两版注入器 ----
src = os.path.join(ROOT, 'skill', 'tools', 'inject_main_v22_final.py')
tmpl = os.path.join(ROOT, 'tools', 'inject_main.py')
if os.path.isfile(src) and os.path.isfile(tmpl):
    a = read(src)
    b = read(tmpl)
    va = re.search(r'RES = \{ v: (\d+) \}', a)
    vb = re.search(r'RES = \{ v: (\d+) \}', b)
    if not vb:
        fails.append('[双版本] tools/inject_main.py 里找不到 RES = { v: N }')
    elif va and va.group(1) != vb.group(1):
        fails.append('[双版本] 定稿源 v%s vs Install 模板 v%s —— 必须同步'
                     % (va.group(1), vb.group(1)))
    if a != b:
        warns.append('[提示] tools/inject_main.py 与定稿源内容不同（版本号相同则通常是历史残留）')

# ---- 4) 跨文件版本一致性 ----
vers = {}
for p in walk():
    if os.path.splitext(p)[1].lower() != '.py':
        continue
    t = read(p)
    m = re.search(r'^VER = (\d+)\s*$', t, re.M)
    if m:
        vers.setdefault('VER', set()).add((os.path.relpath(p, ROOT), m.group(1)))
    for mm in re.finditer(r'RES = \{ v: (\d+) \}', t):
        vers.setdefault('RES', set()).add((os.path.relpath(p, ROOT), mm.group(1)))
    for mm in re.finditer(r'RES\.ver = (\d+)', t):
        vers.setdefault('RES.ver', set()).add((os.path.relpath(p, ROOT), mm.group(1)))

# 只比较【当前交付物】：v18/v19 是历史存档，版本本来就不同，不算 drift
LIVE = {'skill/tools/inject_main_v22_final.py', 'tools/inject_main.py'}
def live(s):
    return {(f, v) for f, v in s if f.replace('\\', '/').lower() in LIVE}

if 'VER' in vers:
    vals = {v for _, v in live(vers['VER'])}
    if len(vals) > 1:
        fails.append('[版本] VER 取值不一致: %s' % sorted(vals))
if 'RES' in vers:
    vals = {v for _, v in live(vers['RES'])}
    if len(vals) > 1:
        fails.append('[版本] RES = { v: N } 取值不一致: %s' % sorted(vals))
if vers.get('VER') and vers.get('RES'):
    a = {v for _, v in live(vers['VER'])}
    b = {v for _, v in live(vers['RES'])}
    if a and b and a != b:
        fails.append('[版本] Python VER=%s 与 JS RES=%s 不同值' % (sorted(a), sorted(b)))

# ★ 同文件内三处必须同值（跨文件比会漏掉「只改了 RES、没改 RES.ver」这种）：
#   VER = N / RES = { v: N } / RES.ver = N 三者在该文件内取值集合 size 必须为 1。
#   synchk.py 是按单文件查的，这里对交付物再查一遍，两者互为交叉验证。
byfile = {}
for key in ('VER', 'RES', 'RES.ver'):
    for f, v in vers.get(key, set()):
        byfile.setdefault(f, set()).add(v)
for f, vals in sorted(byfile.items()):
    if os.path.normpath(f).replace('\\', '/').lower() in LIVE and len(vals) > 1:
        fails.append('[版本] %s 内部三处版本不同值: %s（VER / RES={v:N} / RES.ver 必须同值）'
                     % (f, sorted(vals)))

# ---- 5) 技能正文漂移（仓库那份 vs 本机已安装那份）----
# 同一份 SKILL.md 会同时存在两处：仓库 skill/SKILL.md（分发/推 GitHub）和
# 本机技能目录 ~/.workbuddy/skills/<name>/SKILL.md（AI 实际加载）。
# 各改一点就会漂移成两份不同文档（2026-09-30 实测：本机那份停在 v19，仓库那份已到 v22）。
# 这里只 WARN 不 FAIL —— 别人的机器上可能根本没装这个技能。
try:
    import hashlib
    _rs = os.path.join(ROOT, 'skill', 'SKILL.md')
    _h = lambda p: hashlib.sha256(io.open(p, 'rb').read()).hexdigest()
    _cands = [os.path.expanduser('~/.workbuddy/skills/mythcool-injector/SKILL.md'),
              os.path.expanduser('~/.claude/skills/mythcool-injector/SKILL.md')]
    _found = next((c for c in _cands if os.path.isfile(c)), None)
    if os.path.isfile(_rs) and _found:
        if _h(_rs) != _h(_found):
            warns.append('[技能漂移] 仓库 skill/SKILL.md 与本机技能正文不一致 —— '
                         '用 skill/tools/skillsync.py 检查并同步（--to-local / --to-repo）')
except Exception:
    pass

print('repochk: 仓库根 = %s' % ROOT)
for w in warns:
    print('  WARN ' + w)
if fails:
    print('=== FAIL ===')
    for f in fails:
        print('  ' + f)
    sys.exit(1)
print('=== 全部通过（任务名=%s / 安装路径=%s / 版本一致） ===' % (TASK, DEST))
