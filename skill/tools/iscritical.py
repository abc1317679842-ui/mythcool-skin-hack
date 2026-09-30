# -*- coding: utf-8 -*-
"""
iscritical.py -- ask Windows directly whether dwm.exe is a CRITICAL process.

NtQueryInformationProcess(ProcessBreakOnTermination) == 1  =>  killing it
causes a bugcheck (CRITICAL_PROCESS_DIED).  Read-only, opens the handle with
PROCESS_QUERY_LIMITED_INFORMATION only.
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys

ntdll = ctypes.WinDLL("ntdll")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ProcessBreakOnTermination = 29


def pids_of(name):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name, "/FO", "CSV", "/NH"],
                         capture_output=True, shell=True).stdout
    txt = ""
    for enc in ("mbcs", "utf-8", "cp936"):
        try:
            txt = out.decode(enc)
            break
        except Exception:
            pass
    res = []
    for line in txt.splitlines():
        line = line.strip()
        if not line.startswith('"'):
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            res.append(int(parts[1]))
    return res


def is_critical(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None, "OpenProcess failed err=%d" % ctypes.get_last_error()
    try:
        val = ctypes.c_ulong(0)
        ret_len = ctypes.c_ulong(0)
        st = ntdll.NtQueryInformationProcess(
            wt.HANDLE(h), ProcessBreakOnTermination,
            ctypes.byref(val), ctypes.sizeof(val), ctypes.byref(ret_len))
        if st != 0:
            return None, "NtQueryInformationProcess status=0x%08X" % (st & 0xFFFFFFFF)
        return val.value, "ok"
    finally:
        kernel32.CloseHandle(wt.HANDLE(h))


print("=" * 62)
print(" Is the process CRITICAL?  (1 = killing it bugchecks Windows)")
print("=" * 62)
TARGETS = ["dwm.exe", "csrss.exe", "winlogon.exe", "services.exe", "explorer.exe",
           "MythCool.exe", "msdwatch.py", "pythonw.exe"]
for name in TARGETS:
    pids = pids_of(name)
    if not pids:
        print("  %-16s (not running)" % name)
        continue
    for pid in pids[:3]:
        v, msg = is_critical(pid)
        verdict = {0: "NO  - safe to terminate",
                   1: "YES - terminating it BUGCHECKS Windows"}.get(v, "? (%s)" % msg)
        print("  %-16s pid %-7d critical=%s   %s" % (name, pid, v, verdict))
print()
