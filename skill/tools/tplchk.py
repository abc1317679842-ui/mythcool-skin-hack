# -*- coding: utf-8 -*-
"""装机脚本体检：静态查 cmd 解析陷阱 + 动态验断言方向。

为什么需要它：.cmd 没法在沙箱里端到端跑（cmd.exe 转发被拦），但
「脚本里那些断言到底会不会放行 / 拦住」必须能证明，不能靠"跑一遍看着没报错"。
更要紧的是——2026-09-29 那次 abort 已经证明：脚本能跑完不代表断言方向对。

分两层：

  A. 静态 —— 解析生成的 .cmd，查那几类会让 cmd 解析跑偏的写法
     S1  纯 ASCII（含非 ASCII 会被 cmd 按代码页搞乱）
     S2  全 CRLF
     S3  不得出现 findstr（按控制台代码页读文件，对 UTF-8+CJK 不可靠）
     S4  不得出现 if 括号块（括号提前闭合块的经典陷阱）
     S5  echo 正文不得有裸 ">"（会被当重定向）
     S6  echo 正文不得有裸括号（一旦落进块内就提前闭合）
     S7  goto / 标签闭合（跳去不存在的标签 = 脚本静默跑偏）
     S8  不得对回退点 %BAK% 做删除（会把唯一回退点顶掉）
     S9  不得再用 -Command 一行流（长命令行嵌套括号是解析隐患）
     S10 引用的 .ps1 与源文件必须真实存在

  B. 动态 —— 把 .cmd 里引用的 .ps1 拿真实文件跑一遍，核对退出码方向
     D1  verify_markers.ps1  对「应放行的源」+ -Neg   -> 必须 0
     D2  verify_markers.ps1  对「应拦住的源」         -> 必须非 0
     D3  verify_markers.ps1  对「应拦住的源」+ -Neg   -> 必须非 0（BAKKEEP 确认路径）
     D4  check_beat.ps1      对 v18 数组样例          -> 必须 0
     D5  check_beat.ps1      对 v17 对象样例          -> 必须非 0

用法：
  <python> "<本文件>" <install.cmd> <VER> <应放行的源> <应拦住的源> [临时目录]

  临时目录可省略（自动选：本机约定路径 → 系统临时目录）；只用来放 D4/D5 的两个样例，
  跑完自动删。

退出码：0 全绿 / 1 有问题 / 2 用法错
"""
import io
import os
import re
import subprocess
import sys
import tempfile

# 临时目录：第 6 个参数 > 本机约定路径（存在才用）> 系统临时目录。
# 约定路径缺失时自动退回系统 temp，保证换机器也能跑。
TMP_LOCAL = u'D:\\\u6d4b\u8bd5\u4e34\u65f6\u6587\u4ef6\u5939'
TMP_DEFAULT = TMP_LOCAL if os.path.isdir(TMP_LOCAL) else tempfile.gettempdir()


def run_ps(args):
    """跑一个 powershell 命令，返回 (rc, 合并输出)。"""
    p = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy',
                        'Bypass', '-File'] + args,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw = p.stdout
    for enc in ('utf-8', 'gbk'):
        try:
            return p.returncode, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return p.returncode, raw.decode('utf-8', 'replace')


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        return 2

    cmd_path, ver, good_src, bad_src = sys.argv[1:5]
    tmpdir = sys.argv[5] if len(sys.argv) > 5 else TMP_DEFAULT

    fails = []
    warns = []

    print('装机脚本: %s' % cmd_path)
    print('预期版本: v%s' % ver)
    print('应放行  : %s' % good_src)
    print('应拦住  : %s' % bad_src)
    print()

    # ---------------- A. 静态 ----------------
    print('--- A. 静态检查 ---')

    if not os.path.exists(cmd_path):
        print('  [FAIL] S0 脚本不存在')
        return 1

    raw = open(cmd_path, 'rb').read()
    txt = raw.decode('ascii', 'replace')
    lines = txt.replace('\r\n', '\n').split('\n')

    def chk(cond, tag, msg):
        if cond:
            print('  [ok]   %s %s' % (tag, msg))
        else:
            print('  [FAIL] %s %s' % (tag, msg))
            fails.append(tag)

    chk(max(raw) < 128, 'S1', '纯 ASCII')
    chk(raw.count(b'\r\n') > 0 and raw.count(b'\r\n') == raw.count(b'\n'),
        'S2', '全 CRLF')

    low = txt.lower()
    # ★v20 修正：只拦 findstr【命令调用】，rem 注释里的提及不算
    # （Finalize 模板的 HARD RULES 注释本身就写着 "do not verify markers with findstr"）
    fn_lines = [i for i, ln in enumerate(lines, 1)
                if 'findstr' in ln.lower() and not ln.strip().lower().startswith('rem')]
    chk(not fn_lines, 'S3', '无 findstr 命令（rem 注释除外）%s' % ('' if not fn_lines else ' 行=%s' % fn_lines))

    blocky = [i for i, ln in enumerate(lines, 1)
              if re.match(r'^\s*if\s+.*\(\s*$', ln)]
    chk(not blocky, 'S4', '无 if 括号块%s' % ('' if not blocky else ' 行=%s' % blocky))

    bad_gt, bad_par = [], []
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().lower().startswith('rem'):
            continue
        idx = ln.lower().find('echo')
        if idx < 0:
            continue
        body = ln[idx + 4:]
        if '>' in body.replace('^>', ''):
            bad_gt.append(i)
        for c in '()':
            if c in body.replace('^' + c, ''):
                bad_par.append(i)
    chk(not bad_gt, 'S5', 'echo 无裸 ">"%s' % ('' if not bad_gt else ' 行=%s' % bad_gt))
    chk(not bad_par, 'S6', 'echo 无裸括号%s' % ('' if not bad_par else ' 行=%s' % bad_par))

    labels = set(m.group(1).lower() for m in
                 (re.match(r'^\s*:(\w+)', ln) for ln in lines) if m)
    gotos = set()
    for ln in lines:
        m = re.match(r'^\s*goto\s+(\w+)', ln, re.I)
        if m:
            gotos.add(m.group(1).lower())
    if 'eof' in gotos:
        gotos.discard('eof')
    dangling = sorted(gotos - labels)
    chk(not dangling, 'S7', 'goto 标签闭合%s' % ('' if not dangling else ' 悬空=%s' % dangling))

    bak_del = [i for i, ln in enumerate(lines, 1)
               if '%BAK%' in ln and re.search(r'\b(del|erase|rmdir)\b', ln, re.I)]
    chk(not bak_del, 'S8', '未对回退点做删除%s' % ('' if not bak_del else ' 行=%s' % bak_del))

    chk(' -Command ' not in txt, 'S9', '无 -Command 一行流')

    refs = {}
    for ln in lines:
        m = re.match(r'^\s*set\s+(VFY|CHK|SRC|INJ)=(.+?)\s*$', ln)
        if m:
            refs[m.group(1)] = m.group(2)
    miss = [k for k, v in refs.items() if not os.path.exists(v)]
    for k in sorted(refs):
        print('        %-4s= %s' % (k, refs[k]))
    chk(not miss, 'S10', '引用的文件都存在%s' % ('' if not miss else ' 缺=%s' % miss))

    if refs.get('SRC') and os.path.abspath(refs['SRC']) != os.path.abspath(good_src):
        print('  [warn] 脚本里的 SRC 与本次传入的应放行源不是同一个文件')
        warns.append('SRC-mismatch')

    vfy = refs.get('VFY')
    chk_ps = refs.get('CHK')
    print('  静态结论: %s' % ('PASS' if not fails else 'FAIL %s' % fails))
    print()

    # ---------------- B. 动态 ----------------
    print('--- B. 动态检查（跑 .ps1 核退出码方向）---')

    if not vfy or not os.path.exists(vfy):
        print('  [SKIP] 找不到 verify_markers.ps1，跳过 D1-D3')
        fails.append('D-skip')
    else:
        rc, out = run_ps([vfy, '-Path', good_src, '-Ver', ver, '-Neg'])
        print('  D1 好源 +Neg     rc=%-2s  %s' % (rc, 'OK' if rc == 0 else 'FAIL'))
        if rc != 0:
            print(''.join('        ' + l + '\n' for l in out.splitlines()))
            fails.append('D1')

        rc, out = run_ps([vfy, '-Path', bad_src, '-Ver', ver])
        print('  D2 旧源           rc=%-2s  %s' % (rc, 'OK' if rc != 0 else 'FAIL'))
        if rc == 0:
            print('        -> 旧源竟然通过了 v%s 必需要素，断言方向反了' % ver)
            fails.append('D2')

        rc, out = run_ps([vfy, '-Path', bad_src, '-Ver', ver, '-Neg'])
        print('  D3 旧源 +Neg      rc=%-2s  %s' % (rc, 'OK' if rc != 0 else 'FAIL'))
        if rc == 0:
            print('        -> BAKKEEP 会误报"回退点已经是新版"')
            fails.append('D3')

    if not chk_ps or not os.path.exists(chk_ps):
        # ★v20 修正：check_beat.ps1 是 v18 时代的 beat 校验器，v19 起已废弃。
        # 脚本不引用它 = 正常演进，不算 FAIL（只有脚本【引用了】而文件缺失才该 FAIL，
        # 那种情况已被 S10 覆盖）。
        if re.search(r'check_beat\.ps1', txt, re.I):
            print('  [FAIL] 脚本引用 check_beat.ps1 但文件不存在')
            fails.append('D-skip-ref')
        else:
            print('  [SKIP] check_beat.ps1 不存在且脚本未引用（v19+ 正常）—— D4-D5 不适用')
    else:
        if not os.path.isdir(tmpdir):
            os.makedirs(tmpdir)
        f_arr = os.path.join(tmpdir, '_tplchk_arr.json')
        f_obj = os.path.join(tmpdir, '_tplchk_obj.json')
        io.open(f_arr, 'w', encoding='ascii').write(
            '[{"now":1,"src":{"tick":5},"moFires":5,"moOk":5},'
            '{"now":2,"src":{"tick":9},"moFires":9,"moOk":9}]')
        io.open(f_obj, 'w', encoding='ascii').write(
            '{"src":{"apply":1,"dup":1,"tick":300},"moFires":180,"moOk":180}')
        try:
            rc, out = run_ps([chk_ps, '-Path', f_arr])
            print('  D4 数组样例       rc=%-2s  %s' % (rc, 'OK' if rc == 0 else 'FAIL'))
            if rc != 0:
                print(''.join('        ' + l + '\n' for l in out.splitlines()))
                fails.append('D4')
            else:
                for l in out.splitlines():
                    if l.strip():
                        print('        ' + l.strip())

            rc, out = run_ps([chk_ps, '-Path', f_obj])
            print('  D5 对象样例       rc=%-2s  %s' % (rc, 'OK' if rc != 0 else 'FAIL'))
            if rc == 0:
                print('        -> v17 对象格式竟然被认成 v18 数组，断言方向反了')
                fails.append('D5')
        finally:
            for f in (f_arr, f_obj):
                try:
                    os.remove(f)
                except OSError:
                    pass

    print()
    print('=== 结论 ===')
    if warns:
        print('warn: %s' % ', '.join(warns))
    if fails:
        print('总体: FAIL  %s' % fails)
        return 1
    print('总体: PASS —— 静态无解析陷阱，动态断言方向正确')
    return 0


if __name__ == '__main__':
    sys.exit(main())
