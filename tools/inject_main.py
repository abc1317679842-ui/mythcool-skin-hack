# -*- coding: utf-8 -*-
"""Myth.Cool 副屏注入 —— 常驻自动版（计划任务用）

v20 变更（2026-09-30，外部评审采纳项）：
  A1. V8 符号解析失败时显式报 SYM MISS 并退出 3 —— 不再静默失败
      （旧版符号找不到 -> NativeFunction 拿到垃圾 -> agent 中止，每分钟白试无诊断）。
      Python 侧识别后在 last_result.json 写 symMiss: true。版本升级第一失效点。
  A2. refresh_ms 日志区分「文件原值 / 生效值」（v15 保险丝会把 <3500 抬到 3500，
      旧日志只打原值，3000 看起来生效了其实没有）；注释里的「默认 3000 与原生对齐」
      是 v13 时代残留的假话，一并清除。
  A3. 删除 tick 死参数（不在 DEF 里，loadCfg 从不拷贝，docs/02 的说法是错的）。
  A4. 版本号三处（VER 常量 / RES={v:N} / RES.ver=N）必须同值，synchk.py 强制断言。
  B1. layerHost 找不到旋转坐标系宿主（.mainpage_jx/.mainpage_jx1）时不再静默降级
      到 .mainAll/.mainpage/body（方向全错），改为 RES.warn 标红 + 拒绝挂载。
  B2. pushTune 前检查窗口存活（isDestroyed），销毁则重找 —— 重插屏/分辨率切换后
      热调不再打在死窗口上。
  P3 修订（2026-09-30 第二轮评审）：SYM MISS 只淘汰当前候选，不再整单否决 ——
      无 PID 回退模式下候选可能混入子进程；全部候选 miss 且无一成功才 exit 3；
      miss 候选检测到 error 消息即止损，不再白等 150 秒。调用侧（Inject.ps1）
      同步：rc=3 -> SYMFAIL:<pid> 停止重试，MythCool 重启（新 pid）自动重试一次。

与手动调试版 phase30_v13.py 的差异（★ 布局逻辑 100% 相同，一个字没改）：
  1. 路径全部落在 C:\\ProgramData\\MythCoolInject\\，不再依赖 WorkBuddy 会话目录
     （会话目录删掉也不影响）
  2. 不做截图、不做 21 秒节拍回读 —— 后台跑要快（正常约 20 秒收工）
  3. MAIN 里加了「等 mainpage 窗口出现」的轮询（最多 120 秒）
     —— 计划任务可能比窗口更早触发：开机登录 / 睡醒后被 Fix.ps1 拉起 / 手动重启
  4. 退出码：0=注入成功（调用方才写 last_pid 记账）
             1=有进程但注入失败（不记账 → 下一轮自动重试）
             2=没找到 MythCool 进程（不记账）
             3=全部候选 V8 符号缺失（SYM MISS）—— 官方软件换了 Electron/V8 大版本，
               重试无意义（调用侧 SYMFAIL 停试），先跑符号探测（见 SKILL.md「版本升级自检」）
  5. 日志 append 到 log\\inject.log，带 [时间][py] 前缀
     （Inject.ps1 写的那份带 [PS] 前缀，同一文件对照看）
  6. ★ 注入完成即 detach —— renderer 里的 CSS/DOM/定时器、以及主进程里的
     fs.watchFile 热调监听，都**不依赖 frida 会话**，所以是「一次注入、长期有效」。
     frida 进程退出不影响已注入的效果。

输出：log\\last_result.json / log\\tune_ack.txt
"""
import json
import os
import sys
import time

import frida

VER = 20   # ★ 版本单一来源之一；synchk.py 强制本行与 PATCH 段 RES={v:N}/RES.ver=N 三处同值

ROOT = r'C:\ProgramData\MythCoolInject'
LOGD = os.path.join(ROOT, 'log')
OUT = os.path.join(LOGD, 'last_result.json')
LOGF = os.path.join(LOGD, 'inject.log')
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
  var LOG = [], RES = { v: 20 };   /* v20: A1 符号显式报错 / A2 日志双值 / B1 宿主拒绝降级 / B2 窗口存活检查；布局逻辑继承 v18 */

  /* ===== 清掉历史版本残留的样式元素 =====
     ★★★v17 关键修正：原列表里含 '__mtc_layer' 和 '__mtc_v13css' ——
     这两个是【当前版本正在用】的活节点！而 cleanOld() 每次 applyAll() 都会跑，
     applyAll() 又被 pushTune() 调用（tune.json 热调，fs.watchFile 每 1.2s 轮询，
     文件一变就推）。后果：
       删浮层 -> 4 个元素瞬间从 DOM 消失（一帧空白）
       删样式表 -> 所有排版规则失效一瞬（元素跳回原始位置）
       再由 ensureLayer()/instCSS() 重建 -> 元素重新挂载
     这就是「闪屏」最直接的一条成因链 —— 而且是【热调越频繁、闪得越勤】。
     修法：清理列表里【只留真正废弃的历史 id】，当前版本在用的必须剔除。
     （历史 id 都是 v10~v12 的，v13 起改用 __mtc_v13css，一直沿用到 v17。）
     ★ 命名约定：__mtc_v13css 这个 id 自 v13 起冻结，虽然名字带 v13 但它就是
     【当前版本在用的活节点 id】，不随主版本号升级改名 —— 改名 = 旧 id 进 STALE
     + 新 id 上线，必须两处同改，否则每次热调都触发一轮「删活节点->重建」闪屏。
     要改名就按这个迁移流程做，别只改一处。） */
  var STALE = ['__mtc_v10css', '__mtc_v11css', '__mtc_v12css',
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

  /* ★★★v17：浮层宿主改挂 .mainpage_jx（旋转子树）内 —— 一次修掉两个病。
     ── 病 1（方向）：v16 把浮层挂 document.body 下、position:fixed。
        实测（probe_geom 2026-09-29 12:59）：
          .mainpage_jx  position:absolute left:-300px top:300px
                        width:960px height:360px  transform:rotate(90deg)
                        transform-origin:480px 180px   box(0,0,360,960)
          .AeeCui       position:relative  width:960px height:360px
                        offsetParent:.mainpage_jx  insideJx:true   box(0,0,360,960)
          #__mtc_layer  position:fixed  width:360px height:960px
                        offsetParent:null  insideJx:false  transform:none
        即：整套皮肤 UI 装在 .mainpage_jx 的 rotate(90deg) 坐标系里（960×360 横版，
        转完视觉 360×960）。元素挂 .AeeCui 时 left=169 是【纵向】偏移、top=150 是【横向】。
        v16 把元素搬到 body 下的浮层 => 脱离 rotate => 坐标系转回来（left 变横向、
        top 变纵向）=> 三个元素竖着排开、整体方向差 90°。这就是用户看到的
        「主板/内存被调转了 90 度，往 CPU 功耗方向向上转了 90 度」。
     ── 病 2（闪屏）：rotate 会把 .mainpage_jx 提升为独立 GPU 合成层；
        body 下的 fixed 元素属于【另一个】合成层。两层刷新不同步 => 闪。
        元素留在 .mainpage_jx 子树内 = 与原生 UI 同一个合成层 => 同步刷新。
     做法：浮层 absolute 挂进 .mainpage_jx（继承 rotate，坐标系与 .AeeCui 完全等价），
          尺寸 100%×100% = 960×360 —— 元素的 left/top 数值【不用改】。
          同时它仍不是 Vue 声明的子节点，Vue re-render 不会主动碰它。
     fallback 链（v20 起）：.mainpage_jx → .mainpage_jx1 → 【拒绝】。
     旧版的 .mainAll → .mainpage → body 兜底已删 —— 那两个是非旋转坐标系
     （.mainpage 非机箱模式不转），静默挂进去方向全错且日志只说成功（隐患非保险）。 */
  function layerHost() {
    var h = document.querySelector('.mainpage_jx')
        || document.querySelector('.mainpage_jx1');
    if (h) return h;
    /* ★v20(B1)：旋转坐标系宿主都不在 = 页面结构变了或非机箱模式 —— 挂载布局必然
       全错，宁可不挂并显式标红，也不默默降级到方向不同的宿主。 */
    RES.warn = 'hostFallbackBlocked';
    log('HOST MISS: .mainpage_jx/.mainpage_jx1 都不在，拒绝降级挂载（v20 B1）');
    return null;
  }
  function ensureLayer() {
    var L = document.getElementById('__mtc_layer');
    var host = layerHost();
    if (!host) return null;
    if (L && L.parentNode === host) return L;   /* 已在正确宿主，幂等返回 */
    try {
      if (!L) {
        L = document.createElement('div');
        L.id = '__mtc_layer';
        log('layer created');
      }
      host.appendChild(L);      /* 首次创建 or 挂错宿主（body）时搬回来 */
      return L;
    } catch (e) { log('layer fail ' + e); return null; }
  }

  /* ★ 默认值 = 用户已确认的定稿排版
       refresh_ms: 新增 5 项的自带节拍。真实行为：DEF 4000；tune.json 传 <3500 的值
                   会被 v15 保险丝抬到 3500（除非 _allow_fast_tick:true）——
                   3000 永远不会真的生效（历史注释「与原生 3000 对齐」是 v13 残留假话）
                   ★ 可热调：改 tune.json 立即生效，不用重跑 bat */
  var DEF = {
    ix: 160, iy: 150, idy: 38,
    minw: 124, vm: 3, vg: 8, vfs: 24, lw: 4.4, ifs: 20,
    tops: { mbt: 150, memt: 188, vrt: 226 }, hide: ['mbv'],
    css: '', refresh_ms: 4000   /* v14: 3000->4000 错开原生节拍 */
  };
  var CFG = {};
  function loadCfg() {
    var k;
    for (k in DEF) CFG[k] = DEF[k];
    var T = window.__MTC_TUNE;
    if (T) {
      /* ★v15.1：剥 BOM 再解析。MAIN 侧已清洗过一道，这里是第二道 ——
         万一有别的路径（旧版本残留、手工注入）塞进带 BOM 的字符串，也能吃下。 */
      if (typeof T === 'string') {
        try { T = JSON.parse(String(T).replace(/^\uFEFF/, '').trim()); }
        catch (e) { T = null; }
      }
      if (T) for (k in DEF) if (T[k] !== undefined && T[k] !== null) CFG[k] = T[k];
    }
    /* ★v15 保险丝(B)：refresh_ms 下限保护。
       背景：hotpush 失败时 window.__MTC_TUNE 会残留【上一次注入】的旧值
       （实测 12:04 那次重注入就是残留了 11:51 的 3000），把 DEF 的 4000 覆盖掉。
       3000 与 Myth.Cool 原生刷新节拍【同频】→ 每 15 秒必然撞拍一次 → 残余闪。
       所以：只要拿到 <3500 的值，一律抬到 3500。3500 既避开 3000 整拍，
       又比 4000 早 0.5 秒响应，视觉上无差别。用户若真要 3000 可显式改
       tune.json 的 _allow_fast_tick = true 放行（默认不给）。 */
    var _rms = parseInt(CFG.refresh_ms, 10);
    if (!_rms || _rms < 200) _rms = 4000;
    var _allowFast = !!(T && T._allow_fast_tick);
    if (!_allowFast && _rms < 3500) { CFG._rmClamped = true; _rms = 3500; }
    CFG.refresh_ms = _rms;
    RES.cfg = { ix: CFG.ix, iy: CFG.iy, idy: CFG.idy, minw: CFG.minw, vm: CFG.vm,
                vg: (typeof CFG.vg === 'string' ? '<string:' + CFG.vg.length + '>' : CFG.vg),
                vfs: CFG.vfs, lw: CFG.lw, hide: CFG.hide, tops: CFG.tops,
                cssLen: String(CFG.css || '').length, refresh_ms: CFG.refresh_ms,
                rmClamped: !!CFG._rmClamped, tuneSrc: !!T };
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
    /* ★v17：复用同一个 <style>，不再每次新建。
       原写法每次 applyAll() 都 createElement+appendChild 一个新表：
         · 旧表不删 => 累积（热调几十次就几十个表）
         · 插入新表会触发一次样式重算，配合 cleanOld 的删除 = 排版闪一下
       改成：有就取回、没有才建；只改 textContent。同 id 原地替换不影响其他节点。 */
    var s = document.getElementById('__mtc_v13css');
    if (!s) {
      s = document.createElement('style');
      s.id = '__mtc_v13css';
      (document.head || document.documentElement).appendChild(s);
    }
    var _css = [
      '.icon_box,.appitem{display:none !important;}',
      '.ProgressBar.outside.AeeAndCui .progressbox{display:none !important;width:0 !important;min-width:0 !important;max-width:0 !important;flex:0 0 0 !important;overflow:hidden !important;}',
      '.ProgressBar.outside.AeeAndCui .el-progress.el-progress--line{display:none !important;}',
      '.ProgressBar.outside.AeeAndCui{display:flex !important;flex-direction:row !important;justify-content:flex-start !important;align-items:baseline !important;gap:6px !important;width:auto !important;min-width:0 !important;max-width:none !important;}',
      '.ProgressBar.outside.AeeAndCui>p{white-space:nowrap !important;word-break:keep-all !important;margin:0 !important;padding:0 !important;font-size:19px !important;color:#9fd6ff !important;flex:0 0 auto !important;}',
      '.ProgressBar.outside.AeeAndCui>span:not(.mtc-inline){white-space:nowrap !important;word-break:keep-all !important;display:inline-block !important;font-size:26px !important;color:#ffffff !important;font-weight:700 !important;flex:0 0 auto !important;margin:0 !important;min-width:' + CFG.minw + 'px !important;}',
      '.mtc-inline{margin-left:' + CFG.vm + 'px !important;white-space:nowrap !important;flex:0 0 auto !important;font-size:' + CFG.vfs + 'px !important;color:#9fd6ff !important;}',
      '.mtc-inline .mtc-iv{color:#ffffff !important;font-weight:700 !important;font-size:' + CFG.vfs + 'px !important;margin-left:' + CFG.vg + 'px !important;}',
      /* ★★★v17 核心：4 项(温度类)的【独立浮层】，挂进 .mainpage_jx 内。
         position:absolute（不是 fixed！）—— 就为继承 .mainpage_jx 的 rotate(90deg)
         坐标系；100%×100% 在该盒内 = 960×360，与 .AeeCui 完全同域
         => 元素的 left:169/top:150/188/226 语义原封不动，方向与位置全部复原。
         pointer-events:none 不挡点击；z-index 9998 与元素自身一致。
         ★ 曾用 position:fixed 挂 body —— 那会让元素脱离 rotate，方向差 90°，已废。 */
      '#__mtc_layer{position:absolute !important;left:0 !important;top:0 !important;width:100% !important;height:100% !important;pointer-events:none !important;z-index:9998 !important;margin:0 !important;padding:0 !important;overflow:visible !important;}',
      '.mtc-it{position:absolute;font-size:' + CFG.ifs + 'px !important;color:#ffffff !important;white-space:nowrap !important;z-index:9998 !important;line-height:1.15 !important;}',
      '.mtc-it b{color:#9fd6ff !important;font-weight:400 !important;font-size:' + CFG.ifs + 'px !important;margin-right:4px !important;display:inline-block !important;min-width:' + CFG.lw + 'em !important;}',
      '.mtc-it .mtc-val{color:#ffffff !important;font-weight:700 !important;font-size:' + CFG.ifs + 'px !important;}',
      /* ★ 正式注入口：任意 CSS 追加在样式表最后，能压过前面所有同权规则 */
      String(CFG.css || '')
    ].join('');
    /* ★v17：内容没变就别赋值。textContent 赋值（哪怕同值）会标脏样式表，
       触发一次全页样式重算 —— 热调频繁时就是持续掉帧/闪烁的来源之一。 */
    if (s.__mtc_css !== _css) { s.__mtc_css = _css; s.textContent = _css; }
    return _css.length;
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

  /* ★ v14 新增：DOM 改写守卫
     背景（2026-09-29 实测）：build()/fixRows() 会往 Vue 管理的容器里
     appendChild 我们的元素；appendChild 本身会触发 MutationObserver，
     于是 MO -> refresh() -> appendChild -> MO 形成自我触发循环，
     表现为副屏"闪黑"（间隔逐渐拉长直到收敛）。
     做法：任何由我们自己发起的 DOM 写入，全程置 guard=true；
     MO 回调看到 guard 就直接 return，不进入 refresh()。 */
  var MTC_GUARD = false;
  function withGuard(fn) {
    if (MTC_GUARD) return null;       /* 已在守卫内，避免重入 */
    MTC_GUARD = true;
    try { return fn(); } finally { MTC_GUARD = false; }
  }
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
      if (!iv) {
        withGuard(function () { iv = document.createElement('span'); iv.className = 'mtc-inline'; bar.appendChild(iv); });
      }
      if (iv) {
        var want = lab + '<span class="mtc-iv">' + v[key] + '</span>';
        if (iv.innerHTML !== want) iv.innerHTML = want;
      }
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
    /* ★v17：宿主改回 .mainpage_jx 子树内的浮层（见 ensureLayer 注释） */
    var host = ensureLayer() || layerHost();
    var v = vals();
    return withGuard(function () {
      for (var i = 0; i < ITEMS.length; i++) {
        var it = ITEMS[i];
        var el = document.querySelector('[data-mtc="' + it.id + '"]');
        if (!el) {
          el = document.createElement('div');
          el.className = 'mtc-it';
          el.setAttribute('data-mtc', it.id);
          host.appendChild(el);
        } else if (el.parentNode !== host) {
          /* 若元素还在旧宿主里（比如上一版本残留），搬到浮层。
             ★v16：不再静默吞异常 —— 搬迁失败必须可见（首轮就是被这里吞掉的）。 */
          try { host.appendChild(el); }
          catch (e) { log('move:' + it.id + ' ' + e); }
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
    });
  }

  /* ===== ★ 统一刷新入口：数字/电压(fixRows) 与 3 项(build) 必须一起走 ===== */
  var lastRefresh = 0;
  function refresh(src) {
    var now = Date.now();
    if (now - lastRefresh < 200) { return; }   /* v14: 80->200 抗MO连击 */
    lastRefresh = now;
    /* ★★★v16 严重回归修复（v15 引入）：
       v15 曾在这里【整体包了一层 withGuard】，理由是"三重防护闭环"。
       但那是个致命错误 —— withGuard 有重入短路：
         function withGuard(fn){ if (MTC_GUARD) return null; MTC_GUARD=true; ... }
       外层 refresh() 置 MTC_GUARD=true 后，内层 fixRows()/build() 各自的 withGuard
       【检测到重入，直接 return null，函数主体一次都不执行】！
       后果：4 个温度项的创建/搬迁/数值更新【全部静默失效】—— 这正是
       v16 首轮注入后 itemParents 仍显示 AeeCui（元素没搬进浮层）的真因。
       正确做法：只有【叶子级的 DOM 写入函数】包 withGuard，refresh() 不能包。
       fixNetClip 只改 style，而 MO 只观察 childList+subtree（不含 attributes），
       它不会触发 MO，无需 guard。 */
    try { fixRows(); } catch (e) { log('r1 ' + e); }
    try { build(); } catch (e) { log('r2 ' + e); }
    try { fixNetClip(); } catch (e) { log('r3 ' + e); }
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
    if (!ms || ms < 200) ms = 4000;   /* v15: 3000->4000，兜底值也错开原生 3000 节拍 */
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
      /* ★v16：观察目标从 .AeeCui 改为 document.body。
         为什么：4 项已搬到 body 下的独立浮层，而 Vue 改的是 .AeeCui ——
         两者都在 body 子树内，观察 body 才能同时覆盖到。
         性能：body 的变更通知会变多，但回调开头有 MTC_GUARD 短路 +
         「仅当我们的元素缺失才动手」的过滤，实际开销可忽略。 */
      var host = document.body || document.documentElement;
      if (!host) return false;
      var mo = new MutationObserver(function () {
        try {
          /* ★ v14：我们自己正在写 DOM 时直接忽略（切断自触发链） */
          if (MTC_GUARD) { return; }
          /* ★★ v15 重要修正：原条件「三项全 false 才算异常」是过度矫正 ——
             `.hardware-infor.outside.AeeAndCui:not(.img_back)` 是【皮肤自带的网络块】，
             正常情况下【永远存在】；`.mtc-inline` / `[data-mtc=vrt]` 是【我们自己】的元素，
             正常也在 ⇒ 三条件全 false ⇒ MO 回调【基本从不触发】⇒ 这条"复活"通路形同虚设，
             Vue 一旦清理掉我们的元素就【永久消失】，只能等下一轮 tick 的 build() 补救，
             中间会有一段可见的"缺块"。这就是"闪"的另一半来源。
             正确做法：任一关键元素缺失就立即补，但要带冷却，避免和 Vue 反复拉锯。 */
          var lack = (!document.querySelector('[data-mtc="vrt"]'))
                  || (!document.querySelector('.mtc-inline'))
                  || (!document.getElementById('__mtc_layer'))
                  || (document.querySelectorAll('.mtc-inline').length < 2);
          if (!lack) { return; }
          /* 冷却 250ms：低于此间隔不动手，防止「Vue 删→我补→Vue 又删」的死循环 */
          var now = (window.performance && performance.now) ? performance.now() : Date.now();
          if (window.__mtc_moLast && (now - window.__mtc_moLast) < 250) {
            return;
          }
          window.__mtc_moLast = now;
          refresh('mutate');
        } catch (e) {}
      });
      mo.observe(host, { childList: true, subtree: true });
      window.__mtc_mo = mo;
      return true;
    } catch (e) { log('mo ' + e); return false; }
  }

  function applyAll() {
    /* ★v17 计数：applyAll 到底被跑了几次？
       热调（tune.json 变）会走 pushTune -> __mtc_apply() -> 这里。
       若这个数在运行期持续增长，说明热调链路在反复触发 —— 那就是闪的直接来源。 */
    RES.applyN = (RES.applyN || 0) + 1;
    loadCfg(); instCSS(); hideBtns(); ensureLayer(); refresh('apply'); startTick(); hookUpdates(); watchDom();
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
  /* ★v15：整段自检包 try。
     原病：这段跑在 applyAll() 之后、return JSON.stringify(RES) 之前，
     内部大量 getBoundingClientRect()/getComputedStyle()/offsetWidth 会【强制同步布局】。
     若此时页面正在 re-render（Vue patch 中途）、或某行刚被移除，取到 null 就抛
     → 整个 PATCHCODE 的 Promise reject → MAIN 侧 .catch → arm() 被跳过
     → 热调链路从未武装 → 配置永远停留在上一次注入的旧值。
     （这就是 12:04 refresh_ms=3000 的直接成因链）
     自检数据只是给日志看的，绝不能让它影响主功能，所以整体兜住。 */
  try {
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
    RES.vals = vals();
  } catch (e) {
    log('selfcheck ' + e);
    if (!RES.check) RES.check = [];
    if (!RES.items) RES.items = [];
  }
  try { RES.mem = memGB(); } catch (e) { RES.mem = null; log('memGB ' + e); }
  try { RES.gpu = gpuGB(); } catch (e) { RES.gpu = null; log('gpuGB ' + e); }
  RES.log = LOG;
  try {
    RES.hooks = {
      tick: !!window.__mtc_v13timer,
      tickMs: window.__mtc_v13ms || null,
      vue: !!(typeof vmCache !== 'undefined' && vmCache && vmCache.__mtc_v13hooked),
      domObserver: !!window.__mtc_mo
    };
  } catch (e) { RES.hooks = { err: String(e) }; log('hooks ' + e); }
  RES.ver = 20;
  /* ★★★v17 诊断：验证浮层是否真的落在 .mainpage_jx 的旋转坐标系里。
     判据（v16 的实测值作对照）：
       v16 错态：layerParent=BODY, layerPos=fixed, layerInsideJx=false,
                 layerBox=360×960, item 的 rect 与 style.left/top 直接相等
       v17 应然：layerParent=DIV.mainpage_jx, layerPos=absolute, layerInsideJx=true,
                 layerBox(视觉)=0,0,360,960 且 offsetParent=.mainpage_jx,
                 item 的 rect 与 style.left/top 不再直接相等（被 rotate 映射过） */
  try {
    var _ac = document.querySelector('.AeeCui');
    var _jx = document.querySelector('.mainpage_jx') || document.querySelector('.mainpage_jx1');
    var _L = document.getElementById('__mtc_layer');
    var _pcs = _ac ? getComputedStyle(_ac) : null;
    var _lcs = _L ? getComputedStyle(_L) : null;
    var _lbox = null;
    if (_L) { var _lr = _L.getBoundingClientRect(); _lbox = { l: +_lr.left.toFixed(1), t: +_lr.top.toFixed(1), w: +_lr.width.toFixed(1), h: +_lr.height.toFixed(1) }; }
    var _items = [];
    for (var _i = 0; _i < ITEMS.length; _i++) {
      var _e = document.querySelector('[data-mtc="' + ITEMS[_i].id + '"]');
      var _ib = null;
      if (_e) { var _ir = _e.getBoundingClientRect(); _ib = { l: +_ir.left.toFixed(1), t: +_ir.top.toFixed(1), w: +_ir.width.toFixed(1), h: +_ir.height.toFixed(1) }; }
      _items.push({
        id: ITEMS[_i].id,
        parent: _e ? (_e.parentNode ? (_e.parentNode.id || _e.parentNode.className || _e.parentNode.nodeName) : '(noParent)') : '(missing)',
        inJx: (_e && _jx) ? _jx.contains(_e) : null,
        styleLeft: _e ? _e.style.left : null,
        styleTop: _e ? _e.style.top : null,
        rect: _ib
      });
    }
    RES.diag = {
      acPos: _pcs ? _pcs.position : '(no .AeeCui)',
      acInsideJx: (_ac && _jx) ? _jx.contains(_ac) : null,
      jxFound: !!_jx,
      jxTransform: _jx ? getComputedStyle(_jx).transform : null,
      layer: !!_L,
      layerParent: _L && _L.parentNode ? (_L.parentNode.tagName || '?') + (_L.parentNode.className ? '.' + String(_L.parentNode.className).split(' ')[0] : '') : null,
      layerPos: _lcs ? _lcs.position : null,
      layerInsideJx: (_L && _jx) ? _jx.contains(_L) : null,
      layerBox: _lbox,
      layerStyleLeft: _L ? _L.style.left : null,
      layerStyleTop: _L ? _L.style.top : null,
      layerStyleW: _L ? _L.style.width : null,
      layerStyleH: _L ? _L.style.height : null,
      items: _items,
      /* 是否"坐标直通"（未旋转系的标志）：style.left 与 rect.left 完全相等 */
      axisDirect: (function () {
        var e = document.querySelector('[data-mtc="vrt"]');
        if (!e) return null;
        var r = e.getBoundingClientRect();
        return { styleLeft: e.style.left, rectL: +r.left.toFixed(1), styleTop: e.style.top, rectT: +r.top.toFixed(1) };
      })(),
      bodyDirectChildren: (function () {
        var a = [], c = document.body ? document.body.children : [];
        for (var k = 0; k < c.length && k < 12; k++) a.push(c[k].id || c[k].className || c[k].nodeName);
        return a;
      })()
    };
  } catch (e) { RES.diag = { err: String(e) }; log('diag ' + e); }
  /* ★v15 最后一道闸：即使前面有任何未捕获异常，也保证 return 一个合法 JSON，
     绝不让 PATCHCODE 的 Promise reject —— arm() 已经提到 .then 外面，
     但这里再多一层，做到「注入必达、配置必推」。 */
  var _out = '';
  try { _out = JSON.stringify(RES); } catch (e) { _out = '{"v":15,"jsonErr":"' + String(e).replace(/"/g, "'") + '"}'; }
  return _out;
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

  /* ★★v15.1 关键修复：tune.json 带 UTF-8 BOM（EF BB BF），
     而 JS 的 JSON.parse 遇 BOM 直接抛 "Unexpected token \uFEFF"。
     实测 12:16:49 那次注入：
       "initial tune push skip: SyntaxError: Unexpected token \uFEFF in JSON at position 0"
     ⇒ 初始配置推送【一直失败】；热调回调里的 JSON.parse 同样失败
     ⇒ 用户改 tune.json 的调参【从来没有生效过】（这也是 refresh_ms 长期卡旧值的原因之二）。
     更危险的是 pushTune 会把文件原文【直接拼进 JS 代码】：
       window.__MTC_TUNE=<原文>;(window.__mtc_apply||function(){})();
     若原文带 BOM，这行本身语法就错 —— 连设置都完不成。
     所以必须在【读文件时】就剥掉 BOM + 校验可解析，双保险。 */
  function cleanJson(s) {
    if (!s) return null;
    /* 剥 BOM（含 U+FEFF 各种形态）与首尾空白 */
    s = String(s).replace(/^\uFEFF/, '').replace(/^\uFEFF/, '').trim();
    try { JSON.parse(s); return s; } catch (e) { return null; }
  }
  var OUTPATH = 'OUTJSON';
  var TUNEPATH = 'TUNEPATHX';
  var TUNEACK = 'TUNEACKX';
  function write() { try { fs.writeFileSync(OUTPATH, JSON.stringify(out, null, 2)); } catch (e) {} }
  if (!electron) { step('no electron module'); write(); return 'x'; }

  var W = null, last = '';

  function pushTune(t) {
    /* ★v20(B2)：窗口可能被销毁重建（重插屏 / 分辨率切换 / onDisplayAdded）。
       旧版只在启动时找一次 W，之后热调一直对死窗口 executeJavaScript ->
       只有 .catch 记一笔，热调永远静默失败。先验存活，坏了重找。 */
    if (W) {
      var dead = false;
      try { dead = W.isDestroyed(); } catch (e) { dead = true; }
      if (dead) { step('push: W 已销毁，重新找窗'); W = findW(); }
    }
    if (!W) { step('push skipped: W 为空'); return false; }
    /* ★v15.1：先剥 BOM + 校验可解析。原文直接拼进 JS 代码，
       带 BOM 会让整行语法错（连 window.__MTC_TUNE 都设不上）。 */
    var clean = cleanJson(t);
    if (!clean) { step('push aborted: tune.json 无法解析（BOM/语法错）'); return false; }
    var code = 'window.__MTC_TUNE=' + clean + ';(window.__mtc_apply||function(){})();';
    var ok = false;
    try {
      /* ★v15: 加 .then/.catch，把「送达确认」写进 steps。
         原来是 fire-and-forget，失败静默 —— 这正是 12:04 那次
         「配置没生效但看不出原因」的观测盲区。 */
      var pr = W.webContents.executeJavaScript(code);
      if (pr && pr.then) {
        pr.then(function (rr) {
          /* ★v20(A2)：这里打的 cfg.refresh_ms 是【生效值】（v15 保险丝 clamp 之后的），
             与 tune.json 文件原值可能不同 —— 看日志别拿它当文件值 */
          step('push ack: v=' + String(rr && rr.v) + ' rms(生效)=' + String(rr && rr.cfg && rr.cfg.refresh_ms) +
               (rr && rr.cfg && rr.cfg.rmClamped ? ' [原值被抬到3500]' : ''));
        }).catch(function (e) { step('push FAIL: ' + e); });
      }
      ok = true;
    } catch (e) { step('push ' + e); }
    try {
      fs.writeFileSync(TUNEACK,
        new Date().toISOString() + '  pushed ' + clean.length + ' bytes  entered=' + ok + '\n');
    } catch (e) {}
    return ok;
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
      var c0 = cleanJson(t0);        /* ★v15.1 剥 BOM */
      if (c0) {
        var _o = JSON.parse(c0);
        last = c0; pushTune(c0);
        /* ★v20(A2/A3)：只打【文件原值】，生效值看 push ack 的 rms(生效)；
           tick 参数已删（它从不在 DEF 里，是从未生效过的死参数） */
        step('initial tune push sent rms(文件)=' + _o.refresh_ms +
             (_o._allow_fast_tick ? ' [fast]' : ' [将clamp到>=3500]') +
             ' cssLen=' + String(_o.css || '').length);
      } else {
        step('initial tune push skip: 解析失败（BOM? 语法错?）rawLen=' + (t0 ? t0.length : 0));
      }
    } catch (e) { step('initial tune push skip: ' + e); }

    /* 热调监听：改 tune.json -> 1.2 秒内生效。不用重启、不用提权、不用跑 bat。 */
    try {
      fs.watchFile(TUNEPATH, { interval: 1200 }, function (cur, prev) {
        if (!cur || cur.mtimeMs === prev.mtimeMs) return;
        var t = '';
        try { t = fs.readFileSync(TUNEPATH, 'utf8'); } catch (e) { return; }
        var c = cleanJson(t);        /* ★v15.1 剥 BOM，否则热调永远静默失败 */
        if (!c || c === last) return;
        last = c; pushTune(c);
      });
      step('tune watcher armed');
    } catch (e) { step('watch ' + e); }

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
    }).catch(function (e) {
      out.results.push({ ok: false, err: String(e) });
      write();
    });
    /* ★v15 修复(A)：arm() 必须【无条件】调用，不能挂在 executeJavaScript 的 .then 里。
       原病的确定性证据（2026-09-29 12:04 那次重注入）：
         · inject.log 里【没有】initial tune push ok / tune watcher armed
         · tune_ack.txt 停在 11:51:07，12:04 之后零新记录
         · tune.json = 4000，但 last_result.json 的 cfg.refresh_ms = 3000
         · 源码 DEF.refresh_ms = 4000（cat -A 验过）→ 说明是 __MTC_TUNE 旧值覆盖了 DEF
       推论：PATCHCODE 的 Promise 因页面内异常 reject（applyAll 已跑完、RES 已填好，
       但最后那段 RES.check 的 getBoundingClientRect/getComputedStyle 强制同步布局
       可能抛异常）→ 走 .catch → arm() 被整个跳过 → 热调链路【从未武装】。
       后果：__MTC_TUNE 残留上一次注入的旧值，配置永远慢一拍。
       修法：无论如何都 arm()。它内部对 fs/electron 都有 try 兜底，重复调用安全
       （watchFile 注册前先看 last，不改文件不会重复推）。 */
    try { arm(w); } catch (e) { step('arm fail: ' + e); }
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
var MISS = [];
for (var k in Syms) {
  /* ★v20(A1)：逐符号校验。getGlobalExportByName 找不到时 frida 17 抛异常（safe 吞成
     'ERR...' 字符串）、旧版返回 NULL —— 两种情况都不能再往下走，否则 NativeFunction
     拿垃圾指针构造，agent 静默中止，计划任务每分钟白试且无诊断（版本升级第一失效点）。 */
  var p = safe(function () { return Module.getGlobalExportByName(Syms[k]); });
  if (p && typeof p !== 'string' && typeof p.isNull === 'function' && !p.isNull()) A[k] = p;
  else MISS.push(k);
}
if (MISS.length) {
  log('SYM MISS ' + MISS.join(',') + ' | 官方软件换了 Electron/V8 版本? 先跑符号探测，见 SKILL.md 版本升级自检');
  throw new Error('SYM MISS: ' + MISS.join(','));
}
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
sym_miss = False
for pid in cands:
    plog('attach pid=%d' % pid)
    msgs = []
    session = None
    got = False
    try:
        session = frida.attach(pid)
        main_src = (MAIN.replace('OUTJSON', OUT.replace('\\', '\\\\'))
                        .replace('TUNEPATHX', TUNEF.replace('\\', '\\\\'))
                        .replace('TUNEACKX', TUNEA.replace('\\', '\\\\')))
        js = JS.replace('__MAIN__', json.dumps(main_src)).replace('__PATCH__', json.dumps(PATCH))
        sc = session.create_script(js)
        sc.on('message', lambda m, d: msgs.append(m))
        try:
            if os.path.exists(OUT):
                os.remove(OUT)
        except Exception:
            pass
        sc.load()
        time.sleep(4)
        # JS 侧最多等 120 秒窗口 —— 这里给 150 秒
        # ★v20 修订(P3/R3)：只在【确认是 SYM MISS】时提前止损 —— agent 顶层 throw 后
        # 结果文件永远不会出现，等满 150 秒纯属浪费。其它 error（attach/加载类）
        # 保持原等待：结果文件仍可能出现，提前 break 会误杀一个本会成功的候选。
        for _ in range(75):
            if os.path.exists(OUT):
                got = True
                break
            if any('SYM MISS' in str(m.get('payload') or '') for m in msgs):
                break
            time.sleep(2)
        for m in msgs:
            pl = m.get('payload')
            plog('  ' + (pl.get('m') if isinstance(pl, dict) else str(pl)))
        # ★v20(A1)：符号缺失 = 版本升级第一失效点。显式落账（symMiss: true + exit 3），
        # 不留「下一轮重试」的假希望 —— 符号都变了，重试一万次也不会成功。
        # ★v20 修订(P3)：SYM MISS 只淘汰当前候选，不整单否决 —— 无 PID 回退模式下
        # cands 可能混入子进程，第一个候选 miss 不代表主进程也 miss。
        # 全部候选都 miss 且无一成功才 exit 3（见循环末尾 sym_miss and not ok）。
        allm = ' | '.join(
            (m.get('payload') or {}).get('m', '') if isinstance(m.get('payload'), dict)
            else str(m.get('payload') or '')
            for m in msgs)
        if 'SYM MISS' in allm:
            sym_miss = True
            plog('  候选 pid=%s 符号缺失，跳过（若所有候选都 miss 则最终 exit 3）' % pid)
            try:
                with open(OUT, 'w', encoding='utf-8') as f:
                    json.dump({'injected': False, 'symMiss': True, 'msg': allm[:500]}, f, ensure_ascii=False)
            except Exception as e:
                plog('  symMiss 落账失败: %s' % e)
            continue
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

if sym_miss and not ok:
    plog('结果: 全部候选 V8 符号缺失（exit 3）—— 官方软件可能换了 Electron/V8 大版本，先跑版本升级自检')
    sys.exit(3)
plog('结果: %s' % ('成功' if ok else '失败'))
sys.exit(0 if ok else 1)
