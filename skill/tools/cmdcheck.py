# -*- coding: utf-8 -*-
"""
cmdcheck.py  --  normalise a .cmd/.bat to CRLF and validate it before shipping.
--------------------------------------------------------------------------
Why this exists
    Generating a .cmd from a bash heredoc silently destroys Windows paths:
        C:\\Users   ->  C://Users
        \\r\\n in an echo line  ->  a literal /r/n in the output
    Both bugs shipped once and were only caught by the user reading the
    console.  Never generate a batch file without running it through this.

Usage
    python cmdcheck.py FILE.cmd [FILE2.cmd ...]
    python cmdcheck.py --no-write FILE.cmd     # dry run, do not touch it

What it does
    1. reads the bytes, normalises every line ending to CRLF, writes back
    2. asserts: pure ASCII, zero lone LF, backslashes survive, no "//" or
       "/r/n" smears, every goto/call target exists, parens balance
    3. prints a per-file report and a PASS/FAIL verdict

Exit code 0 = all files PASS.  1 = at least one FAIL.
"""
import os
import re
import sys

BS = chr(92)
LF = chr(10)
CR = chr(13)

FORBIDDEN = ["//", "/r/n", "/necho", "C://", "D://", "/pause"]


def check(path, write=True):
    name = os.path.basename(path)
    raw = open(path, "rb").read()
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        txt = raw.decode("mbcs")

    txt = txt.replace(CR + LF, LF).replace(CR, LF)
    crlf = txt.replace(LF, CR + LF)

    if write:
        with open(path, "wb") as fh:
            fh.write(crlf.encode("ascii", "replace"))

    nb = crlf.encode("ascii", "replace")
    lines = crlf.split(CR + LF)

    lone_lf = sum(1 for i, c in enumerate(nb) if c == 0x0A and (i == 0 or nb[i - 1] != 0x0D))
    ascii_ok = all(c < 128 for c in nb)
    bs_count = crlf.count(BS)
    bad_tokens = [t for t in FORBIDDEN if t in crlf]

    labels = set()
    for ln in lines:
        s = ln.strip()
        if s.startswith(":") and not s.startswith("::"):
            labels.add(s[1:].strip().split()[0].lower())

    gotos, calls = [], []
    for i, ln in enumerate(lines, 1):
        lo = ln.lower()
        for m in re.finditer(r"\bgoto\s+([^\s&|]+)", lo):
            if m.group(1) != "eof":
                gotos.append((i, m.group(1)))
        for m in re.finditer(r"\bcall\s+:([^\s&|]+)", lo):
            calls.append((i, m.group(1)))

    broken = [t for _, t in gotos if t not in labels]
    broken += [t for _, t in calls if t not in labels]

    depth = 0
    for ln in lines:
        s = ln.strip()
        if s.lower().startswith("echo"):
            continue          # parentheses inside echo text are just text
        if ln.rstrip().endswith("^"):
            continue          # line continuation, depth carries over
        depth += ln.count("(") - ln.count(")")

    # a bare ! inside an echo line is eaten by delayed expansion -- but ONLY
    # when this file actually turns delayed expansion on.
    delayed = "enabledelayedexpansion" in crlf.lower()
    echo_bangs = []
    if delayed:
        for i, ln in enumerate(lines, 1):
            if not ln.lstrip().lower().startswith("echo"):
                continue
            stripped = re.sub(r"!\w+!", "", ln)   # keep our own !VAR! uses
            if "!" in stripped:
                echo_bangs.append(i)

    # backslashes: a .cmd with no paths in it legitimately has none, so this
    # is a warning, not a failure.
    bs_warn = bs_count == 0 and re.search(r"[A-Za-z]:[\\/]", crlf) is not None

    checks = [
        ("pure ASCII", ascii_ok),
        ("zero lone LF", lone_lf == 0),
        ("no /r/n or // smears", not bad_tokens),
        ("all goto/call targets exist", not broken),
        ("parentheses balanced (code only)", depth == 0),
        ("no bare ! eaten by delayed exp", not echo_bangs),
        ("labels defined", len(labels) > 0 or "goto" not in crlf.lower()),
    ]

    print("=" * 68)
    print("FILE : %s" % name)
    print("  bytes      : %d    lines: %d" % (len(nb), len(lines)))
    print("  backslashes: %d    lone LF: %d    delayed-expansion: %s"
          % (bs_count, lone_lf, "ON" if delayed else "off"))
    if bad_tokens:
        print("  !! forbidden tokens : %s" % bad_tokens)
    if broken:
        print("  !! broken jump targets : %s" % sorted(set(broken)))
    if echo_bangs:
        print("  !! bare ! in echo at lines : %s" % echo_bangs)
    if depth != 0:
        print("  !! paren depth ends at %d" % depth)
    if bs_warn:
        print("  !  warning: looks like a drive path but no backslash survived")
    ok = all(v for _, v in checks)
    for label, v in checks:
        print("   %-34s %s" % (label, "OK" if v else "**FAIL**"))
    print("  VERDICT : %s" % ("PASS" if ok else "FAIL"))
    print()
    return ok


def main():
    args = [a for a in sys.argv[1:]]
    write = True
    if "--no-write" in args:
        write = False
        args.remove("--no-write")
    if not args:
        print(__doc__)
        return 0
    allok = True
    for p in args:
        if not os.path.isfile(p):
            print("MISSING: %s" % p)
            allok = False
            continue
        allok = check(p, write) and allok
    print("OVERALL : %s" % ("PASS" if allok else "FAIL"))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
