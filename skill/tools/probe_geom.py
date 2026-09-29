# -*- coding: utf-8 -*-
"""
只读几何探测 v2 —— 走和 inject_main.py 完全相同的通道：
  frida attach 主进程 -> 在 Node 里用 electron.webContents.executeJavaScript
  -> 页面执行只读诊断 JS -> 结果写文件。

不做任何 DOM 写入，不推 tune 配置。
产物（写到【当前工作目录】）：probe_geom.json / probe_geom_page.json / probe_geom.log

用法（无需提权，当前终端权限即可 attach）：
  C:\\ProgramData\\MythCoolInject\\python\\python.exe "<本文件>" [pid]
"""
import json
import os
import sys
import time

import frida

# ★ 输出到当前工作目录，不硬编码带日期的工作区路径
_CWD = os.getcwd()
OUT = os.path.join(_CWD, 'probe_geom.json')
PAGE_OUT = os.path.join(_CWD, 'probe_geom_page.json')
LOGP = os.path.join(_CWD, 'probe_geom.log')

_lines = []


def plog(m):
    s = time.strftime('%H:%M:%S ') + str(m)
    _lines.append(s)
    print(s)
    try:
        with open(LOGP, 'w', encoding='utf-8') as f:
            f.write('\n'.join(_lines))
    except Exception:
        pass


# ============ 页面内只读诊断（在 renderer 里跑） ============
DIAG = r'''(function () {
  function cs(el, p) { try { return getComputedStyle(el)[p]; } catch (e) { return 'ERR'; } }
  function desc(el) {
    if (!el) return '(null)';
    var s = el.nodeName;
    if (el.id) s += '#' + el.id;
    if (el.className && typeof el.className === 'string') s += '.' + el.className.trim().replace(/\s+/g, '.');
    return s;
  }
  function box(el) {
    if (!el) return null;
    var r = el.getBoundingClientRect();
    return { l: +r.left.toFixed(1), t: +r.top.toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1) };
  }
  function info(el, name) {
    if (!el) return { name: name, found: false };
    return {
      name: name, found: true, tag: desc(el), box: box(el),
      position: cs(el, 'position'),
      transform: cs(el, 'transform'),
      transformOrigin: cs(el, 'transformOrigin'),
      left: cs(el, 'left'), top: cs(el, 'top'),
      width: cs(el, 'width'), height: cs(el, 'height'),
      display: cs(el, 'display'),
      writingMode: cs(el, 'writingMode'),
      direction: cs(el, 'direction'),
      flexDirection: cs(el, 'flexDirection'),
      overflow: cs(el, 'overflow'),
      zIndex: cs(el, 'zIndex'),
      offsetParent: desc(el.offsetParent)
    };
  }

  var out = { ok: true };
  var mAll = document.querySelector('.mainAll');
  var mJx = document.querySelector('.mainpage_jx');
  var mJx1 = document.querySelector('.mainpage_jx1');
  var mPage = document.querySelector('.mainpage');

  out.whichRotate = {
    jx: !!mJx, jx1: !!mJx1, plain: !!mPage,
    active: mJx ? 'mainpage_jx(rotate 90deg)' : (mJx1 ? 'mainpage_jx1(rotate 270deg)' : (mPage ? 'mainpage(none)' : 'none'))
  };
  out.chain = {
    html: info(document.documentElement, 'html'),
    body: info(document.body, 'body'),
    mainAll: info(mAll, '.mainAll'),
    mainpage_jx: info(mJx, '.mainpage_jx'),
    mainpage_jx1: info(mJx1, '.mainpage_jx1'),
    mainpage: info(mPage, '.mainpage')
  };

  out.ancestorsOfJx = [];
  (function () {
    var e = mJx || mJx1 || mPage, n = 0;
    while (e && n < 12) { out.ancestorsOfJx.push(info(e, desc(e))); e = e.parentElement; n++; }
  })();

  var acs = document.querySelectorAll('.AeeCui');
  out.aeecuiCount = acs.length;
  out.aeecui0 = info(acs[0], '.AeeCui[0]');
  if (acs[0] && mJx) out.aeecui0.insideJx = mJx.contains(acs[0]);
  if (acs[0] && mJx1) out.aeecui0.insideJx1 = mJx1.contains(acs[0]);

  var L = document.getElementById('__mtc_layer');
  out.layer = info(L, '#__mtc_layer');
  if (L) {
    out.layer.parent = desc(L.parentNode);
    if (mJx) out.layer.insideJx = mJx.contains(L);
    if (mJx1) out.layer.insideJx1 = mJx1.contains(L);
    if (mAll) out.layer.insideMainAll = mAll.contains(L);
    out.layer.styleText = (L.getAttribute('style') || '').slice(0, 300);
  }

  out.items = [];
  var ids = ['mbt', 'mbv', 'memt', 'vrt'];
  for (var i = 0; i < ids.length; i++) {
    var e = document.querySelector('[data-mtc="' + ids[i] + '"]');
    var o = info(e, ids[i]);
    if (e) {
      o.inJx = mJx ? mJx.contains(e) : null;
      o.parentTag = desc(e.parentNode);
      o.styleLeft = e.style.left; o.styleTop = e.style.top;
      o.text = String(e.textContent || '').slice(0, 20);
      /* 文字方向判定：比宽高比 —— 横排文字宽>高，竖排反之 */
      var r = e.getBoundingClientRect();
      o.ratioWH = r.height > 0 ? +(r.width / r.height).toFixed(2) : null;
    }
    out.items.push(o);
  }

  out.refBlocks = [];
  var c1 = document.querySelectorAll('.hardware-infor.outside.AeeAndCui');
  for (var j = 0; j < c1.length && j < 6; j++) {
    var oo = info(c1[j], 'net' + j + ':' + String(c1[j].textContent || '').trim().slice(0, 10));
    oo.inJx = mJx ? mJx.contains(c1[j]) : null;
    out.refBlocks.push(oo);
  }

  out.progressRows = [];
  var c2 = document.querySelectorAll('.ProgressBar.outside.AeeAndCui');
  for (var k = 0; k < c2.length; k++) {
    var op = info(c2[k], 'row' + k + ':' + String((c2[k].querySelector('p') || {}).textContent || '').trim());
    op.inJx = mJx ? mJx.contains(c2[k]) : null;
    out.progressRows.push(op);
  }

  out.viewport = {
    w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio,
    bodyClientW: document.body.clientWidth, bodyClientH: document.body.clientHeight,
    bodyOffsetW: document.body.offsetWidth, bodyOffsetH: document.body.offsetHeight
  };

  /* axisTest：用现有 vrt 元素的 style.left/top 与渲染 rect 对照，
     判断当前坐标系是"旋转"还是"未旋转"。 */
  out.axisTest = (function () {
    var e = document.querySelector('[data-mtc="vrt"]');
    if (!e) return null;
    var r = e.getBoundingClientRect();
    return {
      styleLeft: e.style.left, styleTop: e.style.top,
      rectL: +r.left.toFixed(1), rectT: +r.top.toFixed(1),
      rectW: +r.width.toFixed(1), rectH: +r.height.toFixed(1),
      hint: 'styleLeft=169 -> rectL=' + r.left.toFixed(1) + ' ; styleTop=226 -> rectT=' + r.top.toFixed(1)
    };
  })();

  return JSON.stringify(out);
})()'''

# ============ Node 侧桥（在 frida 注入的 Node 环境里跑） ============
MAIN = r'''
(function () {
  var out = { steps: [], data: null };
  function step(s) { out.steps.push(String(s)); }
  var req = null, fs = null, electron = null;
  try { req = process.mainModule.require.bind(process.mainModule); } catch (e) { step('req ' + e); }
  try { fs = req('fs'); } catch (e) {}
  try { electron = req('electron'); } catch (e) { step('el ' + e); }

  var OUTPATH = 'OUTJSON';
  function write() { try { fs.writeFileSync(OUTPATH, JSON.stringify(out, null, 2)); } catch (e) {} }
  if (!electron) { step('no electron'); write(); return 'x'; }

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
  function loop() {
    var w = findW();
    if (!w) {
      tries++;
      if (tries >= 30) { step('TIMEOUT no mainpage'); write(); return; }
      setTimeout(loop, 2000);
      return;
    }
    step('found mainpage');
    try {
      w.webContents.executeJavaScript(DIAGJS)
        .then(function (r) {
          step('diag ok len=' + String(r).length);
          out.data = String(r);
          write();
        })
        .catch(function (e) { step('diag FAIL ' + e); write(); });
    } catch (e) { step('exec ' + e); write(); }
  }
  loop();
  return 'ok';
})();
'''

# frida 侧：把 MAIN 编译执行（和 inject_main.py 的 JS 段同构）
JS = r'''
var MAINCODE = __MAIN__;
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
var A = {};
for (var k in Syms) A[k] = safe(function () { return Module.getGlobalExportByName(Syms[k]); });
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
  var code = MAINCODE;
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


def main():
    target = None
    if len(sys.argv) > 1:
        try:
            target = int(sys.argv[1])
        except Exception:
            target = None

    dev = frida.get_local_device()
    if target:
        cands = [target]
        plog('指定 pid=%d' % target)
    else:
        procs = [p for p in dev.enumerate_processes() if 'myth' in p.name.lower()]
        plog('发现 %d 个 myth 进程: %s' % (len(procs), [p.pid for p in procs]))
        if not procs:
            plog('没有 MythCool 进程')
            return 2
        cands = [p.pid for p in procs]

    if os.path.exists(OUT):
        try:
            os.remove(OUT)
        except Exception:
            pass

    got = False
    for pid in cands:
        session = None
        try:
            session = dev.attach(pid)
            plog('attach pid=%d ok' % pid)
            main_src = MAIN.replace('OUTJSON', OUT.replace('\\', '\\\\'))
            # 把 DIAG（JS 字符串字面量）塞进 Node 代码里
            main_src = main_src.replace('DIAGJS', json.dumps(DIAG))
            js = JS.replace('__MAIN__', json.dumps(main_src))
            sc = session.create_script(js)
            msgs = []
            sc.on('message', lambda m, d: msgs.append(m))
            sc.load()
            for _ in range(40):   # 最多 80 秒
                if os.path.exists(OUT):
                    got = True
                    break
                time.sleep(2)
            for m in msgs:
                pl = m.get('payload')
                plog('  ' + (pl.get('m') if isinstance(pl, dict) else str(pl)))
        except Exception as e:
            plog('attach pid=%d 失败 %s %s' % (pid, type(e).__name__, e))
        finally:
            if session is not None:
                try:
                    session.detach()
                except Exception:
                    pass
        if got:
            break

    if not got or not os.path.exists(OUT):
        plog('未拿到结果')
        return 1

    try:
        d = json.load(open(OUT, encoding='utf-8'))
    except Exception as e:
        plog('解析 OUT 失败: %s' % e)
        return 1
    for s in d.get('steps', []):
        plog('  · ' + str(s))
    raw = d.get('data')
    if not raw:
        plog('data 为空')
        return 1
    try:
        g = json.loads(raw)
    except Exception as e:
        plog('页面 JSON 解析失败: %s' % e)
        return 1

    # 把几何数据另存一份好读的
    with open(PAGE_OUT, 'w', encoding='utf-8') as f:
        json.dump(g, f, ensure_ascii=False, indent=2)
    plog('页面几何已存: %s' % PAGE_OUT)
    plog('=== 关键结论 ===')
    plog('旋转类: %s' % json.dumps(g.get('whichRotate'), ensure_ascii=False))
    plog('viewport: %s' % json.dumps(g.get('viewport'), ensure_ascii=False))
    plog('.mainpage_jx: %s' % json.dumps(g.get('chain', {}).get('mainpage_jx'), ensure_ascii=False))
    plog('.AeeCui[0]: %s' % json.dumps(g.get('aeecui0'), ensure_ascii=False))
    plog('#__mtc_layer: %s' % json.dumps(g.get('layer'), ensure_ascii=False))
    plog('axisTest: %s' % json.dumps(g.get('axisTest'), ensure_ascii=False))
    for it in g.get('items') or []:
        plog('item %s: inJx=%s parent=%s box=%s left=%s top=%s' %
             (it.get('name'), it.get('inJx'), it.get('parentTag'), json.dumps(it.get('box')), it.get('left'), it.get('top')))

    # ---- 方向健康自动判定（省得每次人肉比对） ----
    lay = g.get('layer') or {}
    ax = g.get('axisTest') or {}
    verdict = []
    if not lay.get('found'):
        verdict.append('[!!] 没找到 #__mtc_layer —— 注入没生效，或浮层被删')
    else:
        if lay.get('insideJx') is True:
            verdict.append('[OK] 浮层在 .mainpage_jx 旋转子树内')
        else:
            verdict.append('[!!] 浮层【不在】.mainpage_jx 内 -> 元素方向会差 90 度')
        if str(lay.get('position')) == 'absolute':
            verdict.append('[OK] 浮层 position=absolute')
        else:
            verdict.append('[!!] 浮层 position=%s（应为 absolute；fixed 会脱离旋转系）' % lay.get('position'))
        if str(lay.get('parent')) and 'mainpage_jx' in str(lay.get('parent')):
            verdict.append('[OK] 浮层父节点 = %s' % lay.get('parent'))
        else:
            verdict.append('[!!] 浮层父节点 = %s（应为 DIV.mainpage_jx）' % lay.get('parent'))
    if ax:
        direct = (str(ax.get('styleLeft')) == str(ax.get('rectL')) + 'px')
        if direct:
            verdict.append('[!!] 坐标直通（styleLeft==rectL）-> 处于未旋转系 -> 方向错')
        else:
            verdict.append('[OK] 坐标被 rotate 映射（styleLeft=%s -> rectL=%s）'
                           % (ax.get('styleLeft'), ax.get('rectL')))
    plog('--- 方向健康判定 ---')
    for v in verdict:
        plog('  ' + v)
    bad = [v for v in verdict if v.startswith('[!!]')]
    plog('判定结果: %s' % ('全部正常' if not bad else '存在 %d 项问题' % len(bad)))
    return 0 if not bad else 3


if __name__ == '__main__':
    try:
        rc = main()
    except Exception as e:
        plog('顶层异常: %s' % e)
        rc = 9
    sys.exit(rc)
