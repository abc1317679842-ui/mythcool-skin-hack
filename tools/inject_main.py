"""Myth.Cool Skin Hack - the injector

Pushes a patch into the Myth.Cool (Electron) main process, which forwards it to
the renderer (the skin page) via webContents.executeJavaScript.

Once injected we detach: the CSS / DOM / timers living in the renderer, and the
tune.json hot-reload watcher living in the main process, do NOT depend on the
frida session. So this is an "inject once, stays effective" design.

Usage:
    python inject_main.py <pid>   # explicit main-process pid (what Inject.ps1 passes)
    python inject_main.py         # fall back to enumerating MythCool.exe

Exit codes: 0 = injected OK, 1 = failed, 2 = process not found
"""
import json
import os
import sys
import time

import frida

ROOT = os.path.dirname(os.path.abspath(__file__))
LOGD = os.path.join(ROOT, 'log')
OUT = os.path.join(LOGD, 'last_result.json')
LOGF = os.path.join(LOGD, 'inject.log')
BEATF = os.path.join(LOGD, 'last_beat.json')
TUNEF = os.path.join(ROOT, 'tune.json')
TUNEA = os.path.join(LOGD, 'tune_ack.txt')

try:
    os.makedirs(LOGD, exist_ok=True)
except Exception:
    pass


def plog(*a):
    """同时写 log\\inject.log（累积时间线）和 stdout（手动跑时直接看）"""
    s = ' '.join(str(x) for x in a)
    try:
        with open(LOGF, 'a', encoding='utf-8') as f:
            f.write('[%s][py] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), s))
    except Exception:
        pass
    try:
        print(s, flush=True)
    except Exception:
        pass


def _excepthook(tp, val, tb):
    """未捕获异常也必须落进日志 —— 计划任务跑的时候是隐藏窗口，看不到 traceback"""
    try:
        import traceback
        plog('未捕获异常:\n' + ''.join(traceback.format_exception(tp, val, tb)))
    except Exception:
        pass


sys.excepthook = _excepthook


PATCH = r'''
(function () {
  var LOG = [], RES = { v: 13 };

  /* ===== 节拍统计：谁触发的刷新、各触发源几次 ===== */
  var BEAT = { times: [], src: {}, first: 0, last: 0, ver: 13 };
  window.__MTC_BEAT = BEAT;
  function mark(src) {
    try {
      var t = Date.now();
      if (!BEAT.first) BEAT.first = t;
      BEAT.last = t;
      BEAT.src[src] = (BEAT.src[src] || 0) + 1;
      BEAT.times.push([t, src]);
      if (BEAT.times.length > 300) BEAT.times.shift();
    } catch (e) {}
  }

  /* ===== 清掉历史版本残留的样式元素 ===== */
  var STALE = ['__mtc_v10css', '__mtc_v11css', '__mtc_v12css', '__mtc_v13css',
               '__probe_css', '__probe_css2', '__mtc_tune'];
  function cleanOld() {
    var n = 0, i, e;
    for (i = 0; i < STALE.length; i++) {
      while ((e = document.getElementById(STALE[i]))) {
        try { e.parentNode.removeChild(e); n++; } catch (er) { break; }
      }
    }
    return n;
  }

  /* ★ 默认值 = 用户已确认的定稿排版
       refresh_ms: 我加的 5 项的自带节拍，默认 3000（与原生屏幕节拍对齐）
                   ★ 可热调：改 tune.json 的 refresh_ms 立即生效，不用重跑 bat */
  var DEF = {
    ix: 160, iy: 150, idy: 38,
    minw: 124, vm: 3, vg: 8, vfs: 24, lw: 4.4, ifs: 20,
    tops: { mbt: 150, memt: 188, vrt: 226 }, hide: ['mbv'],
    css: '', refresh_ms: 3000
  };
  var CFG = {};
  function loadCfg() {
    var k;
    for (k in DEF) CFG[k] = DEF[k];
    var T = window.__MTC_TUNE;
    if (T) {
      if (typeof T === 'string') { try { T = JSON.parse(T); } catch (e) { T = null; } }
      if (T) for (k in DEF) if (T[k] !== undefined && T[k] !== null) CFG[k] = T[k];
    }
    RES.cfg = { ix: CFG.ix, iy: CFG.iy, idy: CFG.idy, minw: CFG.minw, vm: CFG.vm,
                vg: (typeof CFG.vg === 'string' ? '<string:' + CFG.vg.length + '>' : CFG.vg),
                vfs: CFG.vfs, lw: CFG.lw, hide: CFG.hide, tops: CFG.tops,
                cssLen: String(CFG.css || '').length, refresh_ms: CFG.refresh_ms };
    return CFG;
  }
  loadCfg();

  function log(s) { LOG.push(String(s)); if (LOG.length > 40) LOG.shift(); }
  function getD() { try { return JSON.parse(localStorage.getItem('bg_sensor_data') || '{}') || {}; } catch (e) { return {}; } }

  function hideBtns() {
    var b = document.querySelectorAll('.icon_box, .appitem');
    for (var i = 0; i < b.length; i++) b[i].style.display = 'none';
    return b.length;
  }

  function instCSS() {
    RES.cleaned = cleanOld();
    var s = document.createElement('style');
    s.id = '__mtc_v13css';
    (document.head || document.documentElement).appendChild(s);
    s.textContent = [
      '.icon_box,.appitem{display:none !important;}',
      '.ProgressBar.outside.AeeAndCui .progressbox{display:none !important;width:0 !important;min-width:0 !important;max-width:0 !important;flex:0 0 0 !important;overflow:hidden !important;}',
      '.ProgressBar.outside.AeeAndCui .el-progress.el-progress--line{display:none !important;}',
      '.ProgressBar.outside.AeeAndCui{display:flex !important;flex-direction:row !important;justify-content:flex-start !important;align-items:baseline !important;gap:6px !important;width:auto !important;min-width:0 !important;max-width:none !important;}',
      '.ProgressBar.outside.AeeAndCui>p{white-space:nowrap !important;word-break:keep-all !important;margin:0 !important;padding:0 !important;font-size:19px !important;color:#9fd6ff !important;flex:0 0 auto !important;}',
      '.ProgressBar.outside.AeeAndCui>span:not(.mtc-inline){white-space:nowrap !important;word-break:keep-all !important;display:inline-block !important;font-size:26px !important;color:#ffffff !important;font-weight:700 !important;flex:0 0 auto !important;margin:0 !important;min-width:' + CFG.minw + 'px !important;}',
      '.mtc-inline{margin-left:' + CFG.vm + 'px !important;white-space:nowrap !important;flex:0 0 auto !important;font-size:' + CFG.vfs + 'px !important;color:#9fd6ff !important;}',
      '.mtc-inline .mtc-iv{color:#ffffff !important;font-weight:700 !important;font-size:' + CFG.vfs + 'px !important;margin-left:' + CFG.vg + 'px !important;}',
      '.mtc-it{position:absolute;font-size:' + CFG.ifs + 'px !important;color:#ffffff !important;white-space:nowrap !important;z-index:9998 !important;line-height:1.15 !important;}',
      '.mtc-it b{color:#9fd6ff !important;font-weight:400 !important;font-size:' + CFG.ifs + 'px !important;margin-right:4px !important;display:inline-block !important;min-width:' + CFG.lw + 'em !important;}',
      '.mtc-it .mtc-val{color:#ffffff !important;font-weight:700 !important;font-size:' + CFG.ifs + 'px !important;}',
      /* ★ 正式注入口：任意 CSS 追加在样式表最后，能压过前面所有同权规则 */
      String(CFG.css || '')
    ].join('');
  }

  function vals() {
    var d = getD();
    var cpu = d.cpu || {}, gpu = d.gpu || {}, mb = d.mainboard || {}, mem = d.memory || {};
    function f(v, unit, dec) {
      if (v === null || v === undefined || isNaN(parseFloat(v))) return '--';
      var x = parseFloat(v);
      return (dec ? x.toFixed(dec) : Math.round(x)) + unit;
    }
    return {
      cpu_v: f(cpu.voltage, 'V', 2), gpu_v: f(gpu.voltage, 'V', 2),
      mb_t: f(mb.temp, 'C'), mb_v: f(mb.voltage, 'V', 2),
      mem_t: f(mem.temp, 'C'), vram_t: f(gpu.mem_temp, 'C')
    };
  }

  var ROLE = new WeakMap(), vmCache = null, memTotal = null;
  function findVmOnce(field) {
    /* 实例被 Vue 销毁/替换后要允许重新找，否则重建后钩子全废 */
    if (vmCache && vmCache.$data && !vmCache._isDestroyed && vmCache.$el && document.contains(vmCache.$el)) return vmCache;
    vmCache = null;
    var els = document.querySelectorAll('*'), i;
    for (i = 0; i < els.length; i++) {
      var v = els[i].__vue__;
      if (v && v.$data && Object.prototype.hasOwnProperty.call(v.$data, field)) { vmCache = v; return v; }
    }
    return null;
  }
  function memTotalGB() {
    if (memTotal === null) {
      var vm = findVmOnce('memory_ram_max');
      memTotal = (vm && vm.$data) ? parseFloat(vm.$data.memory_ram_max) : NaN;
    }
    return isNaN(memTotal) ? null : memTotal;
  }
  var MBRE = /(\d+(?:\.\d+)?)\s*M\s*[\/|]\s*(\d+(?:\.\d+)?)\s*M/i;
  function gpuGB() {
    var d = getD(), gl = d.gpu_list && d.gpu_list[0];
    if (!gl) return null;
    var m = MBRE.exec(String(gl.mem_usage_mb || ''));
    if (m) return { used: (+m[1]) / 1024, total: (+m[2]) / 1024 };
    if (typeof gl.mem_usage === 'number' && gl.mem_size) return { used: gl.mem_size * gl.mem_usage / 100 / 1024, total: gl.mem_size / 1024 };
    return null;
  }
  function memGB() {
    var d = getD(), mu = (d.memory || {}).usage, t = memTotalGB();
    if (typeof mu !== 'number' || !t) return null;
    return { used: t * mu / 100, total: t };
  }
  function fmtG(g) { return g.used.toFixed(1) + '/' + Math.round(g.total) + 'G'; }

  function rows() { return document.querySelectorAll('.ProgressBar.outside.AeeAndCui'); }

  function fixRows() {
    var mem = memGB(), gpu = gpuGB(), v = vals();
    var bars = rows();
    for (var i = 0; i < bars.length; i++) {
      var bar = bars[i], p = bar.querySelector('p');
      var all = bar.querySelectorAll('span'), sp = null, j;
      for (j = 0; j < all.length; j++) { if (String(all[j].className || '').indexOf('mtc-inline') === -1) { sp = all[j]; break; } }
      if (!p || !sp) continue;
      var txt = (p.textContent || '').trim();
      var role = ROLE.get(bar);
      if (!role) {
        if (txt === 'DRAM' || txt === '\u5185\u5b58') role = 'mem';
        else if (txt === 'VRAM' || txt === '\u663e\u5b58') role = 'gpu';
        if (role) ROLE.set(bar, role);
      }
      if (!role) continue;
      var zh = (role === 'mem') ? '\u5185\u5b58' : '\u663e\u5b58';
      if (txt !== zh) p.textContent = zh;
      var g = (role === 'mem') ? mem : gpu;
      if (g) { var w = fmtG(g); if ((sp.textContent || '').trim() !== w) sp.textContent = w; }
      var key = (role === 'mem') ? 'cpu_v' : 'gpu_v';
      var lab = (role === 'mem') ? 'CPU' : 'GPU';
      var iv = bar.querySelector('.mtc-inline');
      if (!iv) { iv = document.createElement('span'); iv.className = 'mtc-inline'; bar.appendChild(iv); }
      var want = lab + '<span class="mtc-iv">' + v[key] + '</span>';
      if (iv.innerHTML !== want) iv.innerHTML = want;
    }
  }

  /* ★ 只给「网络上下行」这两个块关掉 clip-path（绝不用宽选择器！）
     背景：皮肤 chunk-common.css 里 .hardware-infor[data-v-b5fe9c4a] 带
       -webkit-clip-path: polygon(0 0,9% 100%,100% 100%,91% 0)
     那个 9% 斜角本来是切它自己的紫色渐变底(linear-gradient(90deg,#a196f3,...))的；
     但本皮肤把该块 background 设成 transparent 却没撤斜角，于是它只剩一个作用：
     把最右 9% 的文字斜着削掉 —— 实测 MB/s 末尾的 s 被削 5.6px。
     而且斜切区 = 块宽的 9%，数字越长块越宽、削得越多（这就是「S 越显示越少」的真因）。
     ★ 为什么不用 CSS 选择器：.hardware-infor.outside.AeeAndCui 不只匹配这两个块 ——
       mainpage 里 CPU/GPU 监控项(num=1) 的 customClass 同样是 "AeeAndCui img_back"，
       用宽选择器会把它们一起改掉（2026-09-28 就这么把右边组件搞坏的：
       left:auto;right:-11px 把它们拽走、width:auto 把它们自带的背景图裁掉）。
       所以这里按「块内 span 文本 === MB/s」精准识别，逐元素写 inline style。
       inline !important 优先级高于样式表 !important，能压过皮肤那条规则。 */
  function fixNetClip() {
    var els = document.querySelectorAll('.hardware-infor.outside.AeeAndCui');
    var n = 0, i;
    for (i = 0; i < els.length; i++) {
      var e = els[i], sp = e.querySelector('span');
      if (!sp) continue;
      if (String(sp.textContent || '').trim() !== 'MB/s') continue;
      try {
        if (e.style.getPropertyValue('clip-path') !== 'none') {
          e.style.setProperty('clip-path', 'none', 'important');
          e.style.setProperty('-webkit-clip-path', 'none', 'important');
          n++;
        }
      } catch (err) {}
    }
    return n;
  }

  var ITEMS = [
    { id: 'mbt', label: '\u4e3b\u677f\u6e29\u5ea6', key: 'mb_t' },
    { id: 'mbv', label: '\u4e3b\u677f\u7535\u538b', key: 'mb_v' },
    { id: 'memt', label: '\u5185\u5b58\u6e29\u5ea6', key: 'mem_t' },
    { id: 'vrt', label: '\u663e\u5b58\u6e29\u5ea6', key: 'vram_t' }
  ];
  function build() {
    var host = document.querySelector('.AeeCui') || document.body;
    var v = vals();
    for (var i = 0; i < ITEMS.length; i++) {
      var it = ITEMS[i];
      var el = document.querySelector('[data-mtc="' + it.id + '"]');
      if (!el) {
        el = document.createElement('div');
        el.className = 'mtc-it';
        el.setAttribute('data-mtc', it.id);
        host.appendChild(el);
      }
      var hidden = !!(CFG.hide && CFG.hide.indexOf(it.id) !== -1);
      el.style.display = hidden ? 'none' : '';
      var top = (CFG.tops && CFG.tops[it.id] !== undefined && CFG.tops[it.id] !== null)
        ? CFG.tops[it.id] : (CFG.iy + i * CFG.idy);
      el.style.left = CFG.ix + 'px';
      el.style.top = top + 'px';
      var html = '<b>' + it.label + '</b><span class="mtc-val">' + v[it.key] + '</span>';
      if (el.innerHTML !== html) el.innerHTML = html;
    }
  }

  /* ===== ★ 统一刷新入口：数字/电压(fixRows) 与 3 项(build) 必须一起走 ===== */
  var lastRefresh = 0;
  function refresh(src) {
    var now = Date.now();
    if (now - lastRefresh < 80) { mark('dup'); return; }
    lastRefresh = now;
    try { fixRows(); } catch (e) { log('r1 ' + e); }
    try { build(); } catch (e) { log('r2 ' + e); }
    try { fixNetClip(); } catch (e) { log('r3 ' + e); }
    mark(src || 'manual');
  }
  window.__mtc_refresh = refresh;

  /* ===================================================================
     ★★★ v13 核心：自带节拍
     v12 的 refresh() 只剩 $watch 一条活路 ⇒ 内存/显存占用不变时，
     我加的 5 项会一直冻住（哪怕主板温度涨了 10 度）。
     这里给 refresh() 一个**自己的 3 秒节拍**，与原生屏幕节拍（3000ms）对齐：
       · 和皮肤自带组件"同时跳"，视觉一致
       · 不依赖任何外部触发源，绝不会冻住
       · 成本可忽略：每 3 秒 JSON.parse(2.3KB) + 十几次 textContent 赋值 ≈ <0.1ms
         （对比原生那次同步 IPC getSensorInfo() 的 2~15ms，便宜三个数量级）
     安全性：fixRows()/build() 内部**本来就有值去重**（if (txt!==zh) / if (el.innerHTML!==html)），
             值不变就不碰 DOM ⇒ 不会和 Vue patch 抢 DOM。
     ⇒ 间隔可热调：改 tune.json 的 refresh_ms 立即生效（不用重跑 bat）
     =================================================================== */
  function startTick() {
    var ms = parseInt(CFG.refresh_ms, 10);
    if (!ms || ms < 200) ms = 3000;
    if (window.__mtc_v13timer) { try { clearInterval(window.__mtc_v13timer); } catch (e) {} }
    window.__mtc_v13timer = setInterval(function () { refresh('tick'); }, ms);
    window.__mtc_v13ms = ms;
    return ms;
  }

  /* ===== 触发源（补充）：Vue $watch —— 值变了能更快响应，不冲突 ===== */
  function hookUpdates() {
    var vm = findVmOnce('gpumemload');
    if (!vm || !vm.$watch) return false;
    vm.__mtc_hooked = true;   /* 把旧版本(v10/v11)的守卫占住，别让它们再重复 hook */
    if (vm.__mtc_v13hooked) return true;
    try { vm.$watch('gpumemload', function () { refresh('watch:gpu'); }); } catch (e) { log('w1 ' + e); }
    try { vm.$watch('memoryloads', function () { refresh('watch:mem'); }); } catch (e) { log('w2 ' + e); }
    vm.__mtc_v13hooked = true;   /* ★ 自己的守卫必须独立命名 */
    return true;
  }

  /* ===================================================================
     触发源（补充）：MutationObserver —— Vue 重建 DOM 时把我们加的东西复活
     ★ v12 的 bug：条件第三项写的 `.hardware-infor[style*="clip-path"]`，
       但 fixNetClip() 把网络块设成 `clip-path:none` 之后，style 字符串里**仍然含
       "clip-path"** ⇒ 选择器照样匹配 ⇒ `!matches` 恒 false ⇒ 三项全 false ⇒
       **MO 从来没触发过**。v13 把第三项改成"网络块是否存在"（真的会消失才触发）。
     ★ 另外先 disconnect 掉旧 MO 再重建，避免 v12 留下的那个僵尸观察器还在跑。
     =================================================================== */
  function watchDom() {
    try {
      if (window.__mtc_mo) {
        try { window.__mtc_mo.disconnect(); } catch (e) {}
        window.__mtc_mo = null;
      }
      var host = document.querySelector('.AeeCui') || document.body;
      if (!host) return false;
      var mo = new MutationObserver(function () {
        try {
          /* 只有"我们的东西不见了"才动手，避免和自己写的 DOM 打架 */
          if (!document.querySelector('[data-mtc="vrt"]')
              || !document.querySelector('.mtc-inline')
              || !document.querySelector('.hardware-infor.outside.AeeAndCui:not(.img_back)')) {
            refresh('mutate');
          }
        } catch (e) {}
      });
      mo.observe(host, { childList: true, subtree: true });
      window.__mtc_mo = mo;
      return true;
    } catch (e) { log('mo ' + e); return false; }
  }

  function applyAll() {
    loadCfg(); instCSS(); hideBtns(); refresh('apply'); startTick(); hookUpdates(); watchDom();
  }
  window.__mtc_apply = function () { try { applyAll(); } catch (e) { log('apply ' + e); } return RES; };

  applyAll();
  /* ★ 页面里唯一的常驻定时器 = startTick() 的那一个（3 秒，可热调） */

  function rc(el) { var r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; }
  function nearGap(a, b) {
    var pa = [[a.l, a.t], [a.r, a.t], [a.l, a.b], [a.r, a.b]], pb = [[b.l, b.t], [b.r, b.t], [b.l, b.b], [b.r, b.b]];
    var min = 1e9, u, v;
    for (u = 0; u < 4; u++) for (v = 0; v < 4; v++) {
      var dx = pa[u][0] - pb[v][0], dy = pa[u][1] - pb[v][1], d = Math.sqrt(dx * dx + dy * dy);
      if (d < min) min = d;
    }
    return +min.toFixed(1);
  }
  RES.check = [];
  var _b = rows(), q, z;
  for (q = 0; q < _b.length; q++) {
    var _p = _b[q].querySelector('p'), _al = _b[q].querySelectorAll('span'), _s = null;
    for (z = 0; z < _al.length; z++) { if (String(_al[z].className || '').indexOf('mtc-inline') === -1) { _s = _al[z]; break; } }
    var _iv = _b[q].querySelector('.mtc-inline');
    if (!_p || !_s) continue;
    RES.check.push({
      label: String(_p.textContent).slice(0, 8),
      num: String(_s.textContent).slice(0, 16),
      numBoxW: Math.round(_s.getBoundingClientRect().width),
      numTextW: _s.offsetWidth,
      gapLabelNum: nearGap(rc(_p), rc(_s)),
      gapNumVolt: _iv ? nearGap(rc(_s), rc(_iv)) : null,
      labelFS: getComputedStyle(_p).fontSize,
      numFS: getComputedStyle(_s).fontSize,
      inlineFS: _iv ? getComputedStyle(_iv).fontSize : null,
      voltFS: (_iv && _iv.querySelector('.mtc-iv')) ? getComputedStyle(_iv.querySelector('.mtc-iv')).fontSize : null,
      voltText: _iv ? String(_iv.textContent).slice(0, 12) : null
    });
  }
  RES.items = (function () {
    var a = [], ii;
    for (ii = 0; ii < ITEMS.length; ii++) {
      var e = document.querySelector('[data-mtc="' + ITEMS[ii].id + '"]');
      if (e) a.push({ id: ITEMS[ii].id, left: e.style.left, top: e.style.top, disp: e.style.display });
    }
    return a;
  })();
  RES.vals = vals(); RES.mem = memGB(); RES.gpu = gpuGB(); RES.log = LOG;
  RES.beat = { src: BEAT.src, n: BEAT.times.length, first: BEAT.first, last: BEAT.last };
  RES.hooks = {
    tick: !!window.__mtc_v13timer,
    tickMs: window.__mtc_v13ms || null,
    vue: !!(vmCache && vmCache.__mtc_v13hooked),
    domObserver: !!window.__mtc_mo
  };
  return JSON.stringify(RES);
})();
'''

MAIN = r'''
(function () {
  var out = { steps: [], results: [], injected: false };
  function step(s) { out.steps.push(String(s)); }
  var req = null, fs = null, electron = null;
  try { req = process.mainModule.require.bind(process.mainModule); } catch (e) { step('req ' + e); }
  try { fs = req('fs'); } catch (e) {}
  try { electron = req('electron'); } catch (e) { step('el ' + e); }
  var OUTPATH = 'OUTJSON';
  var TUNEPATH = 'TUNEPATHX';
  var TUNEACK = 'TUNEACKX';
  var BEATPATH = 'BEATPATHX';
  function write() { try { fs.writeFileSync(OUTPATH, JSON.stringify(out, null, 2)); } catch (e) {} }
  if (!electron) { step('no electron module'); write(); return 'x'; }

  var W = null, last = '';

  function pushTune(t) {
    if (!W) return;
    var code = 'window.__MTC_TUNE=' + t + ';(window.__mtc_apply||function(){})();';
    try { W.webContents.executeJavaScript(code); } catch (e) { step('push ' + e); }
    try { fs.writeFileSync(TUNEACK, new Date().toISOString() + '  pushed ' + t.length + ' bytes\n'); } catch (e) {}
  }

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

  function arm(w) {
    /* 注入后无条件先推一次 tune -> 以后改 tune.json 就完全复原配置 */
    try {
      var t0 = fs.readFileSync(TUNEPATH, 'utf8');
      if (t0) { JSON.parse(t0); last = t0; pushTune(t0); step('initial tune push ok'); }
    } catch (e) { step('initial tune push skip: ' + e); }

    /* 热调监听：改 tune.json -> 1.2 秒内生效。不用重启、不用提权、不用跑 bat。 */
    try {
      fs.watchFile(TUNEPATH, { interval: 1200 }, function (cur, prev) {
        if (!cur || cur.mtimeMs === prev.mtimeMs) return;
        var t = '';
        try { t = fs.readFileSync(TUNEPATH, 'utf8'); } catch (e) { return; }
        if (!t || t === last) return;
        try { JSON.parse(t); } catch (e) { return; }
        last = t; pushTune(t);
      });
      step('tune watcher armed');
    } catch (e) { step('watch ' + e); }

    /* 6 秒后轻量回读：确认节拍在跑（后台版不截图，要快） */
    try {
      setTimeout(function () {
        try {
          w.webContents.executeJavaScript(
            'JSON.stringify({beat:window.__MTC_BEAT?window.__MTC_BEAT.src:null,ms:window.__mtc_v13ms||null,timer:!!window.__mtc_v13timer})'
          ).then(function (s) { try { fs.writeFileSync(BEATPATH, String(s)); } catch (e) {} })
           .catch(function () {});
        } catch (e) {}
      }, 6000);
      step('beat dump armed (6s)');
    } catch (e) { step('beat ' + e); }
  }

  /* ★ 等 mainpage 窗口：计划任务可能比窗口更早触发（开机/睡醒/手动重启）
       每 2 秒查一次，最多 60 次 = 120 秒 */
  var tries = 0;
  function loop() {
    var w = findW();
    if (!w) {
      tries++;
      if (tries >= 60) { step('TIMEOUT: no mainpage after ' + (tries * 2) + 's'); write(); return; }
      setTimeout(loop, 2000);
      return;
    }
    W = w;
    var u = ''; try { u = w.webContents.getURL(); } catch (e) {}
    step('found mainpage after ' + (tries * 2) + 's: ' + u);
    w.webContents.executeJavaScript(PATCHCODE).then(function (r) {
      out.injected = true;
      out.results.push({ ok: true, raw: String(r) });
      write();
      arm(w);
    }).catch(function (e) {
      out.results.push({ ok: false, err: String(e) });
      write();
    });
  }
  loop();
  return 'ok';
})();
'''

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

# ============================================================
# 主流程
# ============================================================
# ============================================================
# 目标进程
# ============================================================
# Inject.ps1 用「父进程不在 MythCool 集合里」这个判据挑出真正的主进程，
# 作为第 1 个参数传进来 —— 这是最可靠的路径。
# 为什么不用自己枚举：
#   · Electron 会派生一堆 MythCool.exe 辅助进程（--type=gpu-process / renderer），
#     它们和主进程的 StartTime 一模一样，按启动时间排序区分不出来；
#   · 非提权时高完整性进程的 CommandLine 读不到（access denied），
#     按 --type= 过滤同样会失效 —— 实测 frida 在非提权下只暴露了那个
#     gpu-process（pid 16708），attach 上去连 require 都没有，白跑。
target = None
if len(sys.argv) > 1:
    try:
        target = int(sys.argv[1])
    except Exception:
        target = None

cands = []
if target:
    cands = [target]
    plog('目标 pid=%d（由 Inject.ps1 指定）' % target)
else:
    dev = frida.get_local_device()
    procs = [p for p in dev.enumerate_processes() if 'myth' in p.name.lower()]
    if not procs:
        plog('没看到 Myth.Cool 进程 -> exit 2（由 Inject.ps1 决定下一轮重试）')
        sys.exit(2)
    picked = []
    for p in procs:
        argv = []
        try:
            argv = (p.parameters or {}).get('argv') or []
        except Exception:
            pass
        if any(a.startswith('--type=') for a in argv):
            continue
        picked.append(p)
    if not picked:
        picked = list(procs)
    picked.sort(key=lambda x: x.pid)
    cands = [p.pid for p in picked]
    plog('未指定 PID，回退枚举：候选 %s' % cands)

ok = False
for pid in cands:
    plog('attach pid=%d' % pid)
    msgs = []
    session = None
    got = False
    try:
        session = frida.attach(pid)
        main_src = (MAIN.replace('OUTJSON', OUT.replace('\\', '\\\\'))
                        .replace('TUNEPATHX', TUNEF.replace('\\', '\\\\'))
                        .replace('TUNEACKX', TUNEA.replace('\\', '\\\\'))
                        .replace('BEATPATHX', BEATF.replace('\\', '\\\\')))
        js = JS.replace('__MAIN__', json.dumps(main_src)).replace('__PATCH__', json.dumps(PATCH))
        sc = session.create_script(js)
        sc.on('message', lambda m, d: msgs.append(m))
        for f in (OUT, BEATF):
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        sc.load()
        time.sleep(4)
        # JS 侧最多等 120 秒窗口 —— 这里给 150 秒
        for _ in range(75):
            if os.path.exists(OUT):
                got = True
                break
            time.sleep(2)
        for m in msgs:
            pl = m.get('payload')
            plog('  ' + (pl.get('m') if isinstance(pl, dict) else str(pl)))
        if got:
            # 节拍回读是注入后 6 秒落盘，最多再等 24 秒
            for _ in range(12):
                if os.path.exists(BEATF):
                    break
                time.sleep(2)
    except Exception as e:
        plog('  attach 失败 %s %s' % (type(e).__name__, e))
    finally:
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass

    if got and os.path.exists(OUT):
        try:
            d = json.load(open(OUT, encoding='utf-8'))
        except Exception as e:
            plog('  结果文件解析失败: %s' % e)
            d = {}
        for s in d.get('steps', []):
            plog('  · ' + str(s))
        for r in d.get('results', []):
            if r.get('ok'):
                raw = r.get('raw') or ''
                plog('  OK 注入成功，返回 %d 字节' % len(raw))
                try:
                    j = json.loads(raw)
                    plog('  参数: %s' % json.dumps(j.get('cfg'), ensure_ascii=False))
                    plog('  钩子: %s | 清掉残留样式 %s 个'
                         % (json.dumps(j.get('hooks'), ensure_ascii=False), j.get('cleaned')))
                    for c in j.get('check') or []:
                        plog('    [%s %s] 标签->数字=%spx 数字->电压=%spx | 字号 标签%s/数字%s/电压%s'
                             % (c.get('label'), c.get('num'), c.get('gapLabelNum'),
                                c.get('gapNumVolt'), c.get('labelFS'), c.get('numFS'), c.get('voltFS')))
                    for it in j.get('items') or []:
                        plog('    项 %-5s left=%-7s top=%-7s display=%s'
                             % (it.get('id'), it.get('left'), it.get('top'), it.get('disp') or '(显示)'))
                except Exception as e:
                    plog('  解析返回失败: %s | 前 300 字: %s' % (e, raw[:300]))
            else:
                plog('  ERR ' + str(r.get('err'))[:300])
        if d.get('injected'):
            ok = True
        break

if os.path.exists(BEATF):
    try:
        plog('  节拍回读: %s' % open(BEATF, encoding='utf-8').read().strip())
    except Exception:
        pass

plog('结果: %s' % ('成功' if ok else '失败'))
sys.exit(0 if ok else 1)
