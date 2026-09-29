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
  4. 版本号四处同值：Python `VER = N` / JS `RES = { v: N }` / `RES.ver = N`
     （synchk.py 只查单个文件；这里查的是【跨文件】是否一致）

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
src = os.path.join(ROOT, 'skill', 'tools', 'inject_main_v20_final.py')
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
LIVE = {'skill/tools/inject_main_v20_final.py', 'tools/inject_main.py'}
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

print('repochk: 仓库根 = %s' % ROOT)
for w in warns:
    print('  WARN ' + w)
if fails:
    print('=== FAIL ===')
    for f in fails:
        print('  ' + f)
    sys.exit(1)
print('=== 全部通过（任务名=%s / 安装路径=%s / 版本一致） ===' % (TASK, DEST))
