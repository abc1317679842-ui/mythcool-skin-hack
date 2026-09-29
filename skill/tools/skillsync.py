# -*- coding: utf-8 -*-
"""skillsync.py -- 让「仓库里的技能包」与「本机已安装的技能」保持【逐字节一致】

为什么需要它：
  同一份技能会存在两个地方：
    ① 仓库  <repo>\\skill\\               （分发给别人 / 推 GitHub 的那份）
    ② 本机  ~/.workbuddy/skills/<name>\\   （AI 实际加载的那份）
  两边各改一点就会漂移。2026-09-30 实测漂过一次，而且不止 SKILL.md：
    · SKILL.md  本机那份还停在 v19，仓库那份已经讲到 v22
    · tools/    7 个脚本两处内容不同（repochk.py 6699 vs 8009、synchk/tplchk/gen_finalize 全是旧版）
  单靠"记得两边改"是不行的，所以给命令 + 让 repochk 顺手警告。

用法：
  python skillsync.py                 # 只检查（默认），列出两处不一致的文件
  python skillsync.py --to-local      # 仓库 -> 本机：镜像（含新增文件）
  python skillsync.py --to-repo       # 本机 -> 仓库：只回灌【两处都有】的文件（避免把本机专属工具推上仓库）
  python skillsync.py --local <目录>  # 手工指定本机技能目录
退出码: 0 一致 / 1 不一致 / 2 找不到本机技能 / 3 出错

注意：
  · `--to-local` 是**镜像**：仓库有什么就抄什么，本机多出来的文件不动（那些是本机专属的，
    比如闪黑排查期的工具，仓库里本来就没有）。
  · `--to-repo` 只覆盖两处**都有**的文件 —— 本机专属文件不会被误推到公开仓库。
  · 跳过 `__pycache__/` 与 `_` 开头的临时产物。
"""
import hashlib
import io
import os
import shutil
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_SKILL_DIR = os.path.normpath(os.path.join(HERE, '..'))
REPO_SKILL = os.path.join(REPO_SKILL_DIR, 'SKILL.md')
REPO_TOOLS = os.path.join(REPO_SKILL_DIR, 'tools')

NAME = 'mythcool-injector'
CANDIDATES = [
    os.path.expanduser('~/.workbuddy/skills/%s' % NAME),
    os.path.expanduser('~/.claude/skills/%s' % NAME),
]


def skip(fn):
    return fn.startswith('_') or fn == '__pycache__'


def files_of(d, sub=None):
    """返回 {相对路径: 绝对路径}"""
    out = {}
    base = os.path.join(d, sub) if sub else d
    if not os.path.isdir(base):
        return out
    for fn in sorted(os.listdir(base)):
        if skip(fn):
            continue
        p = os.path.join(base, fn)
        if os.path.isfile(p):
            out[(sub + '/' + fn) if sub else fn] = p
    return out


def sha(p):
    return hashlib.sha256(io.open(p, 'rb').read()).hexdigest()


def collect(root):
    m = files_of(root)
    m.update(files_of(root, 'tools'))
    m.pop('SKILL.md', None)
    m['SKILL.md'] = os.path.join(root, 'SKILL.md')
    return {k: v for k, v in m.items() if os.path.isfile(v)}


def find_local(explicit=None):
    if explicit:
        return explicit if os.path.isdir(explicit) else None
    for c in CANDIDATES:
        if os.path.isdir(c):
            return c
    return None


def main():
    args = sys.argv[1:]
    mode = 'check'
    if '--to-local' in args:
        mode = 'to-local'
    elif '--to-repo' in args:
        mode = 'to-repo'
    explicit = None
    if '--local' in args:
        i = args.index('--local')
        if i + 1 >= len(args):
            print('--local 后面要跟目录'); return 3
        explicit = args[i + 1]

    if not os.path.isfile(REPO_SKILL):
        print('找不到仓库技能正文:', REPO_SKILL); return 3
    local = find_local(explicit)
    if not local:
        print('找不到本机已安装的技能目录。试过:')
        for c in CANDIDATES:
            print('  ', c)
        return 2

    R, L = collect(REPO_SKILL_DIR), collect(local)
    common = sorted(set(R) & set(L))
    diff = [k for k in common if sha(R[k]) != sha(L[k])]
    only_repo = sorted(set(R) - set(L))
    only_local = sorted(set(L) - set(R))

    print('仓库技能 : %s   (%d 个文件)' % (REPO_SKILL_DIR, len(R)))
    print('本机技能 : %s   (%d 个文件)' % (local, len(L)))
    print('  内容不同 (%d): %s' % (len(diff), ' '.join(diff) or '无'))
    print('  只在仓库 (%d): %s' % (len(only_repo), ' '.join(only_repo) or '无'))
    print('  只在本机 (%d): %s' % (len(only_local), ' '.join(only_local) or '无（这些是仓库里本来就没有的，不动）'))

    if mode == 'to-local':
        n = 0
        for k, src in R.items():
            dst = os.path.join(local, k.replace('/', os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if (not os.path.isfile(dst)) or sha(src) != sha(dst):
                shutil.copyfile(src, dst); n += 1
        print('→ 已用仓库版镜像本机技能，更新 %d 个文件' % n); return 0

    if mode == 'to-repo':
        n = 0
        for k in common:
            if sha(R[k]) != sha(L[k]):
                shutil.copyfile(L[k], R[k]); n += 1
        print('→ 已把本机版回灌仓库（仅两处都有的文件），更新 %d 个文件' % n); return 0

    if not diff and not only_repo:
        print('→ 一致 ✅'); return 0
    print('→ 【不一致】用 --to-local（以仓库为准）或 --to-repo（以本机为准）收敛')
    return 1


if __name__ == '__main__':
    sys.exit(main())
