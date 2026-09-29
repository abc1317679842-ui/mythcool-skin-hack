# -*- coding: utf-8 -*-
"""皮肤探测 —— 换机器 / 换 Myth.Cool 版本后，先跑这个，再写 tune.json。

为什么必须有它：
  注入器内置的默认识别规则（AeeCui / DreamMonitoring / FallFlower2，编号 31/29/30）
  是【一台 VK03 + 一个特定 Myth.Cool 版本】上实测出来的。官方皮肤会增删、
  第三方皮肤会被收录/下架、不同设备的默认皮肤也不同 —— 换个机器照抄必然认不出来。
  认不出来会怎样：detectSkin() 返回 unknown -> 不在 skins 白名单 -> 【不动界面】。
  这是故意设计的安全行为（宁可不动，不可乱改），所以表现是"注入了但没效果"。

它做什么（全部只读）：
  1. 读出当前皮肤：根容器 class + 官方编号(mode)
  2. 列出本机【已安装/已下载】的皮肤（Vue 的 downloaded1..32 标志）
  3. 给出可直接粘进 tune.json 的 _skinRules / skins 骨架

怎么用：
  1) 跑一次：拿到当前皮肤的类名与编号
  2) 在 Myth.Cool 里切到下一套皮肤，再跑一次 —— 每套都记下来
  3) 把结果写进 tune.json 顶层的 _skinRules，并在 skins 里给要改造的皮肤填数值

用法: python probe_skins.py [pid]
"""
import sys, os, json, time

import frida

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- 渲染进程里跑的探测代码（只读） ----------
PATCH = r'''
(function () {
  var r = {};
  try {
    var jx = document.querySelector('.mainpage_jx') || document.querySelector('.mainpage_jx1');
    r.jxFound = !!jx;
    if (jx) {
      r.jxKids = [];
      for (var i = 0; i < jx.children.length; i++) {
        var k = jx.children[i];
        r.jxKids.push(k.tagName + '.' + String(k.className || '').split(/\s+/).join('.'));
      }
      r.curRootClass = jx.children[0] ? String(jx.children[0].className || '') : null;
    }
  } catch (e) { r.jxErr = String(e); }

  /* 官方编号：localStorage.waterLocal[*].mode */
  try {
    var wl = JSON.parse(localStorage.getItem('waterLocal') || '{}');
    r.modes = {};
    for (var k in wl) r.modes[k] = (wl[k] || {}).mode;
  } catch (e) { r.modeErr = String(e); }
  try { r.curSnCode = localStorage.getItem('curSnCode'); } catch (e) {}

  /* 已安装皮肤：Vue 上的 downloadedN 标志（N=1..32） */
  try {
    var all = document.querySelectorAll('*'), vm = null;
    for (var i = 0; i < all.length && i < 3000; i++) {
      if (all[i].__vue__ && all[i].__vue__.curentMode !== undefined) { vm = all[i].__vue__; break; }
    }
    if (vm) {
      r.curentMode = vm.curentMode;
      r.screenHeight = vm.screenHeight;
      r.downloaded = [];
      for (var n = 1; n <= 32; n++) {
        if (vm['downloaded' + n]) r.downloaded.push(n);
      }
    } else { r.vueErr = 'no vue instance with curentMode'; }
  } catch (e) { r.vueErr = String(e); }

  /* 页面上所有"像皮肤根"的 class（深度 1~2，带大写字母开头的候选） */
  try {
    var cand = {}, els = document.querySelectorAll('.mainpage_jx > *, .mainpage_jx1 > *');
    for (var i = 0; i < els.length; i++) {
      var cl = String(els[i].className || '').split(/\s+/);
      for (var j = 0; j < cl.length; j++) if (cl[j]) cand[cl[j]] = (cand[cl[j]] || 0) + 1;
    }
    r.rootCandidates = cand;
  } catch (e) {}

  return JSON.stringify(r);
})()
'''

# ---------- Node 主进程：找 mainpage 窗口并执行探测 ----------
MAIN = r'''
(function () {
  var out = { steps: [], results: [], injected: false };
  function step(s) { out.steps.push(String(s)); }
  var req = null, fs = null, electron = null;
  try { req = process.mainModule.require.bind(process.mainModule); } catch (e) {}
  try { fs = req('fs'); } catch (e) {}
  try { electron = req('electron'); } catch (e) { step('electron: ' + e); }
  var OUTPATH = 'OUTJSON';
  function write() { try { fs.writeFileSync(OUTPATH, JSON.stringify(out, null, 2)); } catch (e) {} }
  if (!electron) { step('no electron module'); write(); return 'x'; }
  function findW() {
    var wins = [];
    try { wins = electron.BrowserWindow.getAllWindows(); } catch (e) { return null; }
    for (var i = 0; i < wins.length; i++) {
      var u = '';
      try { u = wins[i].webContents.getURL(); } catch (e) {}
      if (u.indexOf('mainpage.html') !== -1) return wins[i];
    }
    return null;
  }
  var tries = 0;
  (function loop() {
    var w = findW();
    if (!w) {
      tries++;
      if (tries >= 60) { step('TIMEOUT: 找不到 mainpage 窗口（Myth.Cool 没开？副屏没连？）'); write(); return; }
      setTimeout(loop, 2000);
      return;
    }
    w.webContents.executeJavaScript(PATCHCODE).then(function (res) {
      out.injected = true; out.results.push({ ok: true, raw: String(res) }); write();
    }).catch(function (e) {
      out.results.push({ ok: false, err: String(e) }); write();
    });
  })();
  return 'ok';
})();
'''

# ---------- frida：用 V8 符号把 MAIN 打进【Node 主 isolate】 ----------
# 注意：frida 自己的脚本上下文里没有 process/electron（实测 'process' is not defined），
# 必须走注入器同款通道：取 V8 符号 -> Script::Compile -> Run。
JS = r'''
var MAINCODE = __MAIN__;
var PATCHCODE = __PATCH__;
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
  var code = MAINCODE.replace('PATCHCODE', JSON.stringify(PATCHCODE));
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
    if len(sys.argv) > 1:
        return int(sys.argv[1])
    dev = frida.get_local_device()
    procs = [p for p in dev.enumerate_processes() if 'myth' in p.name.lower()]
    if not procs:
        print('没看到 Myth.Cool 进程 —— 先打开软件')
        sys.exit(2)
    # 主进程 = 父进程不是 MythCool.exe 的那个（与 Inject.ps1 同款判据）
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
    pid = pick_pid()
    out = os.path.join(HERE, '_probe_skins.out.json')
    try:
        os.remove(out)
    except Exception:
        pass
    msgs = []
    got = False
    sess = frida.attach(pid)
    js = JS.replace('__MAIN__', json.dumps(MAIN.replace('OUTJSON', out.replace('\\', '\\\\')))) \
           .replace('__PATCH__', json.dumps(PATCH))
    sc = sess.create_script(js)
    sc.on('message', lambda m, d: msgs.append(m))
    sc.load()
    for _ in range(70):
        if os.path.exists(out):
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
              'SYM MISS 说明官方换了 Electron/V8 大版本，见 SKILL.md 版本升级自检。')
        return 1

    d = json.load(open(out, encoding='utf-8'))
    try:
        os.remove(out)          # 中间产物不留痕（保持 tools/ 干净，别把临时文件推上仓库）
    except Exception:
        pass
    for s in d.get('steps', []):
        print('·', s)
    for r in d.get('results', []):
        if not r.get('ok'):
            print('ERR', str(r.get('err'))[:300])
            continue
        j = json.loads(r['raw'])

        print('\n===== 当前皮肤 =====')
        print('  根容器 class : %s' % j.get('curRootClass'))
        print('  官方编号 mode: %s   (来自 localStorage.waterLocal[%s].mode)'
              % (j.get('modes'), j.get('curSnCode')))
        print('  Vue curentMode: %s   屏幕高度: %s' % (j.get('curentMode'), j.get('screenHeight')))
        print('  .mainpage_jx 子节点: %s' % j.get('jxKids'))

        print('\n===== 本机已安装的皮肤（downloaded 标志） =====')
        dl = j.get('downloaded') or []
        print('  dial 编号: %s' % (dl if dl else '(没读到，可能 Vue 实例没找到)'))
        if j.get('vueErr'):
            print('  [注] %s' % j['vueErr'])

        print('\n===== 候选根 class（.mainpage_jx 的直接子节点） =====')
        for k, v in (j.get('rootCandidates') or {}).items():
            print('  .%s  x%s' % (k, v))

        root = (j.get('curRootClass') or '').split()
        mode = None
        try:
            mode = list((j.get('modes') or {}).values())[0]
        except Exception:
            pass
        print('\n===== 建议写进 tune.json 的内容 =====')
        print('''  在 tune.json【顶层】加 _skinRules（认不出来就靠它）：
    "_skinRules": {
      "byClass": { "%s": "你的皮肤id" },
      "byMode":  { "%s": "你的皮肤id" }
    }
  再在 skins 里给要改造的皮肤开一段（不改造的就 _skip: true）：
    "skins": { "你的皮肤id": { "ix":160, "iy":150, "idy":38, "css":"" } }
''' % (root[0] if root else '这里填本次探测到的根class', mode if mode is not None else '这里填本次探测到的编号'))
        print('  ★ 每套皮肤都要【切过去再跑一次本脚本】才能拿到它自己的类名与编号。')
        print('  ★ 认不出来 = 注入器不动界面（安全行为），不会乱改。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
