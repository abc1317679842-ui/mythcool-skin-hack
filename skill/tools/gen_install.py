# -*- coding: utf-8 -*-
"""从 install_template.cmd 生成某一版的 Install_v<VER>.cmd。

为什么需要它：装机脚本必须【纯 ASCII + CRLF】，而且 cmd 的解析陷阱很多
（记事本存成 UTF-8-BOM、编辑器存成 LF、echo 行里的裸 > 被当重定向、
if 块里的裸括号提前闭合块）。用脚本生成 = 这些全由代码兜住，不靠人眼。

用法：
  <python> "<本文件>" <VER> [TAG] [SRC] [DST]
    VER  必填 目标版本号，如 18（装机断言 RES.ver = 18）
    TAG  可选 备份后缀，默认 v(N-1) -> inject_main.py.bak_<TAG>.py
    SRC  可选 注入源文件，默认 <PROJ>\\inject_main_v16_src.py
    DST  可选 输出路径，默认 <PROJ>\\Install_v<N>.cmd

退出码：0 成功 / 1 失败

★ 新增版本时：往 NOTES 里加一条 (changes, kept) 即可，其余自动。
"""
import io
import os
import re
import sys

PROJ = r'C:\ProgramData\MythCoolInject\workspace'
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, 'install_template.cmd')
VFY = os.path.join(HERE, 'verify_markers.ps1')
CHK = os.path.join(HERE, 'check_beat.ps1')

# NOTE: 这里每条都会变成一行 `echo   <内容>`，所以内容里
#   禁止裸括号（cmd 的块解析陷阱）、禁止裸 >（会被当重定向）。
#   所以条目编号一律写 "1." 而不是 "1)"。audit() 会兜住这条。
NOTES = {
    '18': (
        ['1. beat: forever ring buffer, 60s x keep 60 = 1h',
         '   was 10s x 120 self-kill, which kept only the LAST snapshot',
         '2. beat rows now carry now/first/last timestamps',
         '3. beat timer handle moved to module scope',
         '   a repeated arm no longer spawns a 2nd timer',
         '4. window gone -^> timer stops instead of spinning forever'],
        ['5. layer host -^> .mainpage_jx, inherits rotate 90deg',
         '6. STALE no longer deletes LIVE nodes',
         '7. style element reused + textContent dedup'],
    ),
}

OLD = r'''rem ============================================================
rem  MythCoolInject  install template   (v18 schema)
rem  --------------------------------
rem  BEFORE USE, edit the CONFIG block below:
rem    SRC  = the inject_main source file (absolute path)
rem    VER  = expected version number (grep "RES.ver = " in SRC)
rem    TAG  = backup suffix, e.g. v17 -> inject_main.py.bak_v17.py
rem    VFY  = verify_markers.ps1  (UTF-8 safe marker checker)
rem    CHK  = check_beat.ps1      (beat ring format checker)
rem
rem  Hard rules (learned the hard way, 2026-09-29):
rem    * keep this file PURE ASCII + CRLF -- cmd garbles non-ASCII
rem    * NO parenthesised if-blocks anywhere in this file. cmd counts
rem      parens to find where a block ends, so a single stray paren
rem      inside one terminates the block early and shifts every later
rem      command. A marker-check echo that mentioned a CSS transform
rem      was exactly that trap, and it aborted a perfectly good
rem      install. => every failure branch below uses "goto".
rem    * do NOT verify markers with findstr. findstr reads files
rem      through the console code page and misbehaves on UTF-8 files
rem      that contain CJK text. Use verify_markers.ps1 instead.
rem    * do NOT put PowerShell logic in a -Command one-liner here.
rem      A long command line with nested parens is a parsing hazard.
rem      Put the logic in a .ps1 and call it with -File.
rem    * NOTHING on disk is modified until the source has been
rem      verified. A failed check must leave the previous build
rem      untouched and the app still running it.
rem    * NEVER overwrite an existing rollback point. If the backup
rem      file already exists, keep it. Re-running the installer must
rem      not turn a genuine older build into a copy of the new one.
rem ============================================================
setlocal

rem ------------------- CONFIG -------------------
set SRC=C:\ProgramData\MythCoolInject\workspace\inject_main_v16_src.py
set VER=18
set TAG=v17
set VFY=C:\ProgramData\MythCoolInject\skill\tools\verify_markers.ps1
set CHK=C:\ProgramData\MythCoolInject\skill\tools\check_beat.ps1
rem ----------------------------------------------

set DST=C:\ProgramData\MythCoolInject\inject_main.py
set BAK=C:\ProgramData\MythCoolInject\inject_main.py.bak_%TAG%.py
set INJ=C:\ProgramData\MythCoolInject\Inject.ps1
set BEAT=C:\ProgramData\MythCoolInject\log\last_beat.json
set SHL=powershell.exe

echo ============================================================
echo   MythCoolInject  install  - expected version: v%VER%
echo ============================================================'''


def build_head(ver, tag, src):
    lines = [
        'setlocal',
        'set SRC=%s' % src,
        'set VER=%s' % ver,
        'set TAG=%s' % tag,
        'set VFY=%s' % VFY,
        'set CHK=%s' % CHK,
        r'set DST=C:\ProgramData\MythCoolInject\inject_main.py',
        r'set BAK=C:\ProgramData\MythCoolInject\inject_main.py.bak_%TAG%.py',
        r'set INJ=C:\ProgramData\MythCoolInject\Inject.ps1',
        r'set BEAT=C:\ProgramData\MythCoolInject\log\last_beat.json',
        'set SHL=powershell.exe',
        '',
        'echo ============================================================',
        'echo   MythCoolInject  v%s  install' % ver,
    ]
    if ver in NOTES:
        chg, kept = NOTES[ver]
        lines.append('echo   ---- v%s changes ----' % ver)
        lines += ['echo   ' + s for s in chg]
        lines.append('echo   ---- earlier fixes kept ----')
        lines += ['echo   ' + s for s in kept]
    lines.append('echo ============================================================')
    return '\n'.join(lines)


def audit(new):
    """生成物自检：把 cmd 的经典解析陷阱挡在交付之前。

    规则（全部来自 2026-09-29 那次 abort 事故）：
      R1  echo 正文里禁止裸 ">"       会被当重定向，静默写文件
      R2  echo 正文里禁止裸括号        一旦该 echo 落进括号块就会提前闭合块
      R3  禁止任何以 "(" 结尾的 if 行  括号块一律用 goto 取代

    注意 R1/R2 扫的是「行内任意位置的 echo」（含 if ... echo ... 形式），
    不是只看行首 —— 只查行首会漏掉 `if errorlevel 1 echo ...` 这类写法。
    rem 行豁免（注释里的括号不会被执行）。
    """
    bad = []
    for i, ln in enumerate(new.split('\n'), 1):
        low = ln.lower()
        if low.lstrip().startswith('rem'):
            continue
        idx = low.find('echo')
        if idx < 0:
            continue
        body = ln[idx + 4:]
        if '>' in body.replace('^>', ''):
            bad.append('L%d bare ">" in echo [R1]: %s' % (i, ln.strip()))
        for ch in '()':
            if ch in body.replace('^' + ch, ''):
                bad.append('L%d bare "%s" in echo [R2]: %s' % (i, ch, ln.strip()))
    for i, ln in enumerate(new.split('\n'), 1):
        if re.match(r'^\s*if\s+.*\(\s*$', ln):
            bad.append('L%d parenthesised if-block is forbidden [R3]: %s' % (i, ln.strip()))
    return bad


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    ver = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else 'v%d' % (int(ver) - 1)
    src = sys.argv[3] if len(sys.argv) > 3 else os.path.join(PROJ, 'inject_main_v16_src.py')
    dst = sys.argv[4] if len(sys.argv) > 4 else os.path.join(PROJ, 'Install_v%s.cmd' % ver)

    for label, p in (('source', src), ('template', TEMPLATE),
                     ('verifier', VFY), ('beat checker', CHK)):
        if not os.path.exists(p):
            print('FAIL: %s not found: %s' % (label, p))
            return 1

    tpl = io.open(TEMPLATE, encoding='ascii', newline=None).read()
    if OLD not in tpl:
        print('FAIL: template header block not found')
        print('      -> 模板头部被改过？同步更新本脚本的 OLD 常量')
        return 1

    new = tpl.replace(OLD, build_head(ver, tag, src))

    bad = audit(new)
    if bad:
        print('FAIL: generated script has cmd parsing traps:')
        for b in bad:
            print('   ' + b)
        return 1

    io.open(dst, 'w', encoding='ascii', newline='\r\n').write(new)

    raw = io.open(dst, 'rb').read()
    ok_crlf = raw.count(b'\r\n') > 0 and raw.count(b'\r\n') == raw.count(b'\n')
    ok_ascii = max(raw) < 128
    print('written   : %s' % dst)
    print('bytes     : %d' % len(raw))
    print('lines     : %d' % new.count('\n'))
    print('CRLF      : %s' % ('OK' if ok_crlf else 'FAIL'))
    print('pure ascii: %s' % ('OK' if ok_ascii else 'FAIL'))
    print('trap audit: OK  (no bare > / bare parens in echo, no if-blocks)')
    print('verifier  : %s' % VFY)
    print('beat ck   : %s' % CHK)
    return 0 if (ok_crlf and ok_ascii) else 1


if __name__ == '__main__':
    sys.exit(main())
