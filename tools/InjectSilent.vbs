' ============================================================
'  Myth.Cool Skin Hack - launcher: no console window + cheap fast path
'
'  Called by the scheduled task \MythCoolInject every minute as:
'    wscript.exe //B //NoLogo "<install dir>\InjectSilent.vbs"
'
'  WHY A VBS LAUNCHER (and not just "powershell.exe -File ...")
'
'  1) NO WINDOW FLASH.
'     A task action of "powershell.exe -WindowStyle Hidden" STILL flashes a
'     console window: -WindowStyle is applied by PowerShell only AFTER Windows
'     has already allocated a console for the new process. wscript.exe is a
'     GUI-subsystem binary (no console of its own) and Run(..., 0, ...) starts
'     the child with a hidden window, so nothing ever appears on screen.
'
'  2) CHEAP FAST PATH.
'     Starting powershell.exe costs ~370 ms by itself. This script performs
'     the same pid comparison in plain VBScript first (one WMI query plus one
'     small text file). If the pid has not changed there is nothing to do and
'     we exit in ~120 ms without ever starting PowerShell.
'
'  SAFETY - the fast path can only ever SKIP work when it is certain:
'    * MythCool is not running AND the state file already says NONE, or
'    * the main pid equals the pid recorded in the state file.
'  Anything else - WMI error, unreadable state file, pid changed, MythCool
'  started, state file missing - falls through to Inject.ps1, which holds the
'  full logic and does all the logging.
'
'  Run(cmd, 0, True): 0 = hidden window; True = wait, so the task stays in
'  "Running" state for its whole duration (keeps IgnoreNew and
'  ExecutionTimeLimit effective).
'
'  ASCII only on purpose.
' ============================================================
Option Explicit
On Error Resume Next

Dim fso, ROOT, STATEF, PS1
Set fso = CreateObject("Scripting.FileSystemObject")

' everything lives next to this script - no hardcoded paths
ROOT   = fso.GetParentFolderName(WScript.ScriptFullName)
STATEF = ROOT & "\state\last_pid.txt"
PS1    = ROOT & "\Inject.ps1"

Dim f, last
Dim svc, q, o
Dim pids(63), ppids(63), n, i, j, isChild
Dim pid

' ---------- 1) read the booked pid ----------
' "@@" is a sentinel that can never equal a real pid or "NONE", so a
' missing/unreadable state file always falls through to PowerShell.
last = "@@"
If fso.FileExists(STATEF) Then
    Set f = fso.OpenTextFile(STATEF, 1, False)
    If Not f.AtEndOfStream Then last = Trim(f.ReadAll)
    f.Close
End If

' ---------- 2) find the MythCool MAIN process ----------
' The main process is the only MythCool.exe whose parent is not another
' MythCool.exe (Electron spawns gpu/renderer helpers).
pid = ""
n = 0
Err.Clear
Set svc = GetObject("winmgmts:\\.\root\cimv2")
Set q = svc.ExecQuery("SELECT ProcessId, ParentProcessId FROM Win32_Process WHERE Name='MythCool.exe'")

For Each o In q
    If n < 64 Then
        pids(n)  = o.ProcessId
        ppids(n) = o.ParentProcessId
    End If
    n = n + 1
Next

If Err.Number = 0 Then
    If n > 0 And n <= 64 Then
        For i = 0 To n - 1
            isChild = False
            For j = 0 To n - 1
                If ppids(i) = pids(j) Then isChild = True
            Next
            If Not isChild Then
                If pid = "" Then pid = CStr(pids(i))
            End If
        Next
    End If
End If

' ---------- 3) fast path: nothing to do ----------
If Err.Number = 0 Then
    If pid = "" And last = "NONE" Then WScript.Quit 0     ' not running, already noted
    If pid <> "" And pid = last Then WScript.Quit 0       ' already patched
End If

' ---------- 4) anything else: let PowerShell do the real work ----------
Err.Clear
Dim sh, rc
rc = 99
Set sh = CreateObject("WScript.Shell")
rc = sh.Run("powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File """ & PS1 & """", 0, True)
If Err.Number <> 0 Then rc = 99
WScript.Quit rc
