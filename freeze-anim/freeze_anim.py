# -*- coding: utf-8 -*-
"""freeze_anim.py —— AeeBiCui(博物馆1) 动态静态化 · 独立诊断工具

★ 与皮肤注入器(mythcool-injector v22)完全分离：
  · 不读不写 tune.json —— 不占用注入器的 css 通道，注入器热调/换肤撤销都碰不到它
  · 不改 inject_main_v22_final.py / Inject.ps1 / InjectSilent.vbs / 技能
  · 自己的样式元素 id=__mtc_freeze（不在注入器 cleanOld 的 STALE 清单里，
    undoAll 也不删它）—— 两套工具互不干扰
  · 手动运行，不进计划任务。Myth.Cool 重启（新 pid）后需重跑一次

做什么（第一轮 · 最小变量）：
  · 页面加一张样式表：*{animation:none !important;}*{transition:none !important;}
    —— 18 个常驻旋转元素停转、0.5s 过渡直接跳变；元素仍在合成树（能区分
    「动」的锅 vs「少画了东西」的锅）
  · GIF 人物仍会动（GIF 不是 CSS 动画）、轮播仍会每 5s 跳页（那是 JS 改 inline
    transform）—— 刻意不做，保持第一轮变量最小
  · 只对 AeeBiCui 生效：页面内每 2.5s 自检，识别到别的皮肤自动摘掉样式表，
    切回来自动补上（识别判据与注入器同款：.mainpage_jx 首子节点 class 含 AeeCui）
  · 页面重建自愈（主进程守卫）：app.on('web-contents-created')+did-finish-load
    + 10s 兜底轮询，皮肤切换销毁重建页面后 10s 内自动重新冻结

用法（用部署好的 venv python，它有 frida）：
  C:\\ProgramData\\MythCoolInject\\python\\python.exe freeze_anim.py          # 冻结
  C:\\ProgramData\\MythCoolInject\\python\\python.exe freeze_anim.py undo     # 解除
  C:\\ProgramData\\MythCoolInject\\python\\python.exe freeze_anim.py status   # 只查状态

退出码：0=成功 1=失败 2=没找到 Myth.Cool 进程 3=V8 符号缺失
"""
import json
import os
import sys
import time

import frida

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '_freeze_out.json')

# ---------- 页面侧：冻结 ----------
PATCH = r'''
(function () {
  var RES = { tool: 'freeze', act: 'apply', ver: 1 };
  var CSS = '*{animation:none !important;}*{transition:none !important;}';
  function jx() { return document.querySelector('.mainpage_jx') || document.querySelector('.mainpage_jx1'); }
  function isAee() {
    try { if (document.querySelector('.AeeCui')) return true; } catch (e) {}
    try {
      var j = jx(), c = j && j.children[0];
      if (c) return /(^|\s)AeeCui(\s|$)/.test(String(c.className || ''));
    } catch (e2) {}
    return false;
  }
  function findEl() { return document.getElementById('__mtc_freeze'); }
  function addEl() {
    var s = findEl();
    if (!s) {
      s = document.createElement('style');
      s.id = '__mtc_freeze';
      (document.head || document.documentElement).appendChild(s);
    }
    if (s.__mtcF !== CSS) { s.__mtcF = CSS; s.textContent = CSS; }
  }
  function delEl() {
    var s = findEl();
    while (s) { try { s.parentNode.removeChild(s); } catch (e) { break; } s = findEl(); }
  }
  var root = jx() && jx().children[0] ? String(jx().children[0].className || '') : '(no jx)';
  RES.skinRoot = isAee() ? 'AeeBiCui' : root;

  /* 供主进程守卫探测/重放；页面 2.5s 自检也走它 */
  window.__mtcFreezeApply = function () {
    try {
      var on = isAee();
      if (on) { addEl(); } else { delEl(); }
      return JSON.stringify({ on: on, style: !!findEl() });
    } catch (e) { return JSON.stringify({ err: String(e) }); }
  };
  if (window.__mtcFreezeTick) { try { clearInterval(window.__mtcFreezeTick); } catch (e1) {} }
  window.__mtcFreezeTick = setInterval(window.__mtcFreezeApply, 2500);
  window.__mtcFreezeApply();
  RES.style = !!findEl();
  RES.tick = true;
  return JSON.stringify(RES);
})()
'''

# ---------- 页面侧：解除 ----------
UNDO = r'''
(function () {
  var RES = { tool: 'freeze', act: 'undo', ver: 1 };
  var n = 0;
  try { if (window.__mtcFreezeTick) { clearInterval(window.__mtcFreezeTick); n++; } } catch (e) {}
  window.__mtcFreezeTick = null;
  try {
    var s = document.getElementById('__mtc_freeze');
    while (s) { s.parentNode.removeChild(s); n++; s = document.getElementById('__mtc_freeze'); }
  } catch (e2) {}
  try { delete window.__mtcFreezeApply; n++; } catch (e3) {}
  RES.removed = n;
  RES.styleGone = !document.getElementById('__mtc_freeze');
  return JSON.stringify(RES);
})()
'''

# ---------- 页面侧：只查状态 ----------
STATUS = r'''
(function () {
  var j = document.querySelector('.mainpage_jx') || document.querySelector('.mainpage_jx1');
  var c = j && j.children[0];
  return JSON.stringify({
    skinRoot: c ? String(c.className || '') : null,
    style: !!document.getElementById('__mtc_freeze'),
    applyFn: typeof window.__mtcFreezeApply,
    tick: !!window.__mtcFreezeTick
  });
})()
'''

# ---------- Node 主进程 ----------
MAIN = r'''
(function () {
  var out = { steps: [], results: [], injected: false };
  function step(s) { out.steps.push(String(s)); }
  var req = null, fs = null, electron = null;
  try { req = process.mainModule.require.bind(process.mainModule); } catch (e) { step('req ' + e); }
  try { fs = req('fs'); } catch (e) {}
  try { electron = req('electron'); } catch (e) { step('el ' + e); }
  var OUTPATH = 'OUTJSON';
  var ACT = '__ACT__';   /* apply | undo | status */
  function write() { try { fs.writeFileSync(OUTPATH, JSON.stringify(out, null, 2)); } catch (e) {} }
  if (!electron) { step('no electron module'); write(); return 'x'; }

  function isAlive(x) { try { return !!x && !x.isDestroyed(); } catch (e) { return false; } }
  function findW() {
    var wins = [];
    try { wins = electron.BrowserWindow.getAllWindows(); } catch (e) { return null; }
    for (var i = 0; i < wins.length; i++) {
      var u = '';
      try { u = wins[i].webContents.getURL(); } catch (e2) {}
      if (u.indexOf('mainpage.html') !== -1) return wins[i];
    }
    return null;
  }

  if (ACT === 'apply') {
    /* 总开关放主进程 global：undo 跑一次置 false，守卫立刻全部哑火。
       守卫本体（事件+10s轮询）装过一次就复用，绝不重复安装。 */
    try { global.__MTC_FREEZE_ARMED = true; } catch (e0) {}
    try {
      if (global.__MTC_FREEZE_GUARD_ON !== true) {
        global.__MTC_FREEZE_GUARD_ON = true;
        var app = electron.app || (electron.default && electron.default.app);
        if (app && app.on) {
          app.on('web-contents-created', function (ev, wc) {
            try {
              wc.on('did-finish-load', function () {
                setTimeout(function () {
                  try {
                    if (global.__MTC_FREEZE_ARMED !== true) return;
                    var u = ''; try { u = wc.getURL(); } catch (e) {}
                    if (u.indexOf('mainpage.html') === -1) return;
                    wc.executeJavaScript('(function(){return typeof window.__mtcFreezeApply;})()')
                      .then(function (t) { if (t !== 'function') repatch(wc, 'did-finish-load'); })
                      .catch(function () {});
                  } catch (e) {}
                }, 1200);
              });
            } catch (e) {}
          });
          step('guard: web-contents-created armed');
        }
        setInterval(function () {
          try {
            if (global.__MTC_FREEZE_ARMED !== true) return;
            var w = findW();
            if (!isAlive(w)) return;
            w.webContents.executeJavaScript('(function(){return typeof window.__mtcFreezeApply;})()')
              .then(function (t) { if (t !== 'function') repatch(w.webContents, 'watchdog'); })
              .catch(function () {});
          } catch (e) {}
        }, 10000);
        step('guard: watchdog armed (10s)');
      } else {
        step('guard already on (reuse)');
      }
    } catch (eg) { step('guard fail: ' + eg); }
  }
  if (ACT === 'undo') {
    try { global.__MTC_FREEZE_ARMED = false; step('armed -> false (守卫已哑火)'); } catch (eu) {}
  }

  function repatch(wc, why) {
    if (!isAlive(wc)) return;
    try {
      wc.executeJavaScript(PATCHCODE).then(function () {
        step('re-freeze ok (' + why + ')');
      }).catch(function (e) { step('re-freeze fail (' + why + '): ' + e); });
    } catch (e) { step('re-freeze throw: ' + e); }
  }

  var CODE = (ACT === 'apply') ? PATCHCODE : (ACT === 'undo' ? UNDOCODE : STATUSCODE);
  var tries = 0;
  (function loop() {
    var w = findW();
    if (!w) {
      tries++;
      if (tries >= 15) { step('TIMEOUT: 找不到 mainpage 窗口（Myth.Cool 没开？副屏没连？）'); write(); return; }
      setTimeout(loop, 2000);
      return;
    }
    step('found mainpage');
    w.webContents.executeJavaScript(CODE).then(function (r) {
      out.injected = true; out.results.push({ ok: true, raw: String(r) }); write();
    }).catch(function (e) { out.results.push({ ok: false, err: String(e) }); write(); });
  })();
  return 'ok';
})()
'''

# ---------- frida agent：V8 符号通道（与注入器/probe_skins 同款，实测可用） ----------
JS = r'''
var MAINCODE = __MAIN__;
var PATCHCODE = __PATCH__;
var UNDOCODE = __UNDO__;
var STATUSCODE = __STATUS__;
function log(s) { send({ t: 'log', m: String(s) }); }
function safe(f) { try { return f(); } catch (e) { return 'ERR ' + e; } }
var Syms = {
  GetCurrent: '?GetCurrent@Isolate@v8@@SAPAV12@XZ',
  GetCurrentContext: '?GetCurrentContext@Isolate@v8@@QAE?AV?$Local@VContext@v8@@@2@XZ',
  NewFromUtf8: '?NewFromUtf8@String@v8@@SA?AV?$MaybeLocal@VString@v8@@@2@PAVIsolate@2@PBDW4NewStringType@2@H@Z',
  Compile: '?Compile@Script@v8@@SA?AV?$MaybeLocal@VScript@v8@@@2@V?$Local@VContext@v8@@@2@V?$Local@VString@v8@@@2@PAVScriptOrigin@2@@Z',
  Run: '?Run@Script@v8@@QAE?AV?$MaybeLocal@VValue@v8@@@2@V?$Local@VContext@v8@@@2@@Z',
  HsCtor: '??0HandleScope@v8@@QAE@PAVIsolate@1@@Z'
};
var A = {}, MISS = [];
for (var k in Syms) {
  var p = safe(function () { return Module.getGlobalExportByName(Syms[k]); });
  if (p && typeof p !== 'string' && typeof p.isNull === 'function' && !p.isNull()) A[k] = p;
  else MISS.push(k);
}
if (MISS.length) { log('SYM MISS ' + MISS.join(',')); throw new Error('SYM MISS: ' + MISS.join(',')); }
var GetCurrent = new NativeFunction(A.GetCurrent, 'pointer', []);
var GetCurrentContext = new NativeFunction(A.GetCurrentContext, 'void', ['pointer', 'pointer'], 'thiscall');
var HsCtor = new NativeFunction(A.HsCtor, 'void', ['pointer', 'pointer'], 'thiscall');
var NewFromUtf8 = new NativeFunction(A.NewFromUtf8, 'void', ['pointer', 'pointer', 'pointer', 'int', 'int']);
var Compile = new NativeFunction(A.Compile, 'void', ['pointer', 'pointer', 'pointer', 'pointer']);
var Run = new NativeFunction(A.Run, 'void', ['pointer', 'pointer', 'pointer'], 'thiscall');
var done = false;
function inject() {
  var iso = GetCurrent(); if (iso.isNull()) return false;
  var s1 = Memory.alloc(Process.pointerSize); s1.writePointer(ptr(0));
  GetCurrentContext(iso, s1);
  var ctx = s1.readPointer(); if (ctx.isNull()) return false;
  var hs = Memory.alloc(64); HsCtor(hs, iso);
  /* ★ 全局替换：MAIN 里 PATCHCODE 出现 2 次（repatch + 主循环）。
     String.replace 只换第一处 —— 第二处会残留成未定义标识符，
     repatch 一执行就 ReferenceError（v22 注入器同款隐患，见 2026-09-30 复盘）。
     必须用 split/join 做全局替换。 */
  var code = MAINCODE.split('PATCHCODE').join(JSON.stringify(PATCHCODE))
                     .split('UNDOCODE').join(JSON.stringify(UNDOCODE))
                     .split('STATUSCODE').join(JSON.stringify(STATUSCODE));
  var cstr = Memory.allocUtf8String(code);
  var s2 = Memory.alloc(Process.pointerSize); s2.writePointer(ptr(0));
  NewFromUtf8(s2, iso, cstr, 0, -1);
  var src = s2.readPointer(); if (src.isNull()) { log('str fail'); return false; }
  var s3 = Memory.alloc(Process.pointerSize); s3.writePointer(ptr(0));
  Compile(s3, ctx, src, ptr(0));
  var scr = s3.readPointer(); if (scr.isNull()) { log('compile fail'); return false; }
  var s4 = Memory.alloc(Process.pointerSize); s4.writePointer(ptr(0));
  Run(scr, s4, ctx);
  log('injected');
  return true;
}
function hookIt(n) {
  var a = safe(function () { return Module.getGlobalExportByName(n); });
  if (typeof a === 'string') return;
  Interceptor.attach(a, { onEnter: function () { if (done) return; try { if (inject()) done = true; } catch (e) { log('e ' + e); done = true; } } });
  log('hook ' + n);
}
hookIt('uv_timer_start');
hookIt('uv_async_send');
'''


def pick_pid():
    if len(sys.argv) > 2:
        return int(sys.argv[2])
    # ★ 首选：注入器日志里最近的 main-pid（Inject.ps1 用命令行判据选，实测选得对。
    #   纯「父进程不在集合」启发式会选到启动器/GPU 等非主进程 —— 2026-09-30 实测
    #   选了 19092（非主进程）attach 被拒 + 疑似把渲染干挂（屏幕定格）。）
    try:
        import re
        txt = open(r'C:\ProgramData\MythCoolInject\log\inject.log',
                   encoding='utf-8', errors='ignore').read()
        # 两种格式：MythCool started main-pid=X / MythCool restarted A -> X
        pids = re.findall(r'(?:main-pid=|restarted \d+ -> )(\d+)', txt)
        dev0 = frida.get_local_device()
        alive = {p.pid for p in dev0.enumerate_processes()}
        for cand in reversed(pids):
            if int(cand) in alive:
                print('从 inject.log 取最近主进程 pid=%s' % cand)
                return int(cand)
        print('日志里的 pid 都已不存在，改用启发式')
    except Exception:
        pass
    dev = frida.get_local_device()
    procs = [p for p in dev.enumerate_processes() if 'myth' in p.name.lower()]
    if not procs:
        print('没看到 Myth.Cool 进程 —— 先打开软件')
        sys.exit(2)
    ids = {p.pid for p in procs}
    cand = []
    for p in procs:
        ppid = None
        try:
            ppid = (p.parameters or {}).get('ppid')
        except Exception:
            pass
        if ppid is None or ppid not in ids:
            cand.append(p)
    if not cand:
        cand = list(procs)
    cand.sort(key=lambda x: x.pid)
    print('未指定 pid，自动挑主进程：候选 %s -> 用 %d' % ([p.pid for p in cand], cand[0].pid))
    return cand[0].pid


def main():
    act = 'apply'
    if len(sys.argv) > 1 and sys.argv[1] in ('apply', 'undo', 'status'):
        act = sys.argv[1]
    pid = pick_pid()
    try:
        os.remove(OUT)
    except Exception:
        pass

    msgs = []
    got = False
    sess = frida.attach(pid)
    main_src = MAIN.replace('__ACT__', act).replace('OUTJSON', OUT.replace('\\', '\\\\'))
    js = (JS.replace('__MAIN__', json.dumps(main_src))
            .replace('__PATCH__', json.dumps(PATCH))
            .replace('__UNDO__', json.dumps(UNDO))
            .replace('__STATUS__', json.dumps(STATUS)))
    sc = sess.create_script(js)
    sc.on('message', lambda m, d: msgs.append(m))
    sc.load()
    for _ in range(60):
        if os.path.exists(OUT):
            got = True
            break
        time.sleep(0.5)
    try:
        sess.detach()
    except Exception:
        pass

    if not got:
        print('!! 没拿到结果：')
        for m in msgs[:8]:
            print('  -', m.get('type'), str(m.get('payload') or m.get('description'))[:300])
        print('  提示：Myth.Cool 主进程通常需要【管理员】权限才能 attach；'
              'SYM MISS 说明官方换了 Electron/V8 大版本。')
        return 1

    d = json.load(open(OUT, encoding='utf-8'))
    try:
        os.remove(OUT)   # 中间产物不留痕
    except Exception:
        pass
    for s in d.get('steps', []):
        print('·', s)

    ok = False
    for r in d.get('results', []):
        if not r.get('ok'):
            print('ERR', str(r.get('err'))[:300])
            continue
        j = json.loads(r['raw'])
        ok = True
        if act == 'apply':
            print('\n===== 冻结结果 =====')
            print('  当前皮肤 : %s' % j.get('skinRoot'))
            print('  样式表   : %s (__mtc_freeze: animation/transition 全部 !important 禁掉)' %
                  ('已安装' if j.get('style') else '未安装'))
            print('  页面自检 : %s（每 2.5s 查一次皮肤，非 AeeBiCui 自动摘除）' % ('已挂' if j.get('tick') else '未挂'))
            if j.get('style'):
                print('\n  ✓ 屏幕上动画应已停住（GIF 人物仍会动、轮播仍每 5s 跳页 —— 第一轮刻意不禁）')
                print('  · 页面重建自愈已装（主进程守卫，皮肤切换后 10s 内自动重新冻结）')
                print('  · Myth.Cool 重启后需重跑本脚本')
                print('  · 解除：python freeze_anim.py undo')
            else:
                print('\n  ? 当前皮肤不是 AeeBiCui，样式表未安装（这是正常行为：只对博物馆1生效）')
        elif act == 'undo':
            print('\n===== 解除结果 =====')
            print('  清掉 %s 项（样式表/定时器/入口函数），样式已消失=%s' %
                  (j.get('removed'), j.get('styleGone')))
            print('  ✓ 动画应已恢复（主进程守卫已哑火，不会再自动重新冻结）')
        else:
            print('\n===== 当前状态 =====')
            print('  皮肤根 class : %s' % j.get('skinRoot'))
            print('  冻结样式表   : %s' % ('在' if j.get('style') else '不在'))
            print('  入口函数     : %s' % j.get('applyFn'))
            print('  页面自检定时 : %s' % ('在' if j.get('tick') else '不在'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
