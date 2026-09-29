---
name: mythcool-skin-injector
description: |-
  调试/修改/部署 MythCoolInject —— Myth.Cool（机箱副屏、水冷头等设备的驱动与皮肤软件）的皮肤注入技能。
  注入链路作用于 Myth.Cool 应用本身（Electron + frida + 页面 JS），不绑定具体硬件：
  用户已在瓦尔基里 VK03 机箱副屏（360×960，AeeBiCui 等皮肤）全套实测成功，
  其他 Myth.Cool 设备（水冷头、其他型号机箱屏等）未逐一实测，但机制相同、大概率通用。
  涵盖：给皮肤加显示项（主板温度、内存/显存占用绝对值 GB 等）、改数值/字号/位置/颜色、元素转 90 度、
  注入失败、注入后重启失效、tune.json 热调不生效、改源后校验与装机部署、版本升级与回滚。
  Debug, modify and deploy the MythCoolInject skin injector for screens driven by Myth.Cool
  (chassis rear screens, water-cooling blocks, etc.). The injector targets the Myth.Cool Electron
  app itself, not specific hardware: fully proven on a Valkyrie VK03 360x960 chassis screen with
  custom skins; other Myth.Cool devices share the same mechanism and will most likely work too.
  触发词 / triggers: 副屏、机箱屏、水冷头、Myth.Cool、MythCool、MythCoolInject、注入器、皮肤注入、
  AeeBiCui、tune.json、refresh_ms、VK03、Valkyrie、瓦尔基里、inject_main、rear screen、skin injector。
agent_created: true
---

# mythcool-skin-injector — Myth.Cool 皮肤注入器

给 Myth.Cool 驱动的设备屏幕（机箱副屏、水冷头等）加自定义监控项的注入系统，
是 [mythcool-skin-hack](../) 仓库的配套技能。加载本技能后，AI 智能体（WorkBuddy / Claude Code 等支持
SKILL.md 约定的助手）即可按下面沉淀的实战经验安全地改皮肤、调坐标、装机部署、热调参数。

**适用范围**：注入链路（frida attach → Myth.Cool 主进程 → mainpage.html 页面内执行 JS）
作用于 Myth.Cool 应用本身，**不绑定具体硬件**。用户已在**瓦尔基里 VK03 机箱 360×960 副屏**上
全套实测成功；其他 Myth.Cool 设备（水冷头、其他型号机箱屏等）未逐一实测，但机制相同、
**大概率通用** —— 只是分辨率 / 旋转方向 / 皮肤 CSS 类名等几何细节因设备而异，
用 §3 的 `probe_geom.py` 探针对你的设备实测一遍即可，工具与流程完全复用。

> 注入后出现任何显示异常（含「偶尔闪黑」类现象）：先按 §6 排查指南定位，别急着归因注入器 —— 注意事项见 §6 末尾。

## 0. 四条铁律

1. **整套皮肤 UI 装在 `rotate(90deg)` 的坐标系里。** 副屏物理是竖屏（VK03 实测 360×960），Myth.Cool 把内容转 90° 让人横看。**任何自定义元素只要脱离 `.mainpage_jx` 子树，方向和位置就会差 90°。** 其他设备分辨率可能不同，但 rotate 坐标系机制相同 —— 几何以你设备的实测为准（§3 探针）。详见 §2。
2. **`C:\ProgramData\MythCoolInject\` 目录可新建文件，但已存在的文件改不了（ACL）。** `cp` 覆盖、`open(path,'wb')` 一律 `PermissionError`。⇒ **部署/覆盖必须由用户在管理员终端跑 .cmd**；AI 只能备份、只读、写新文件。
3. **别猜，看数据。** 注入器有固定的状态出口（见 §6 表格）：`log\inject.log` / `log\last_result.json` / `log\tune_ack.txt` / `state\last_pid.txt`。先读文件再下结论；探针（§3）只在文件数据对不上时才跑。
4. **`tune.json` 带 UTF-8 BOM。** 任何 `JSON.parse` / `readFileSync` 后直接 parse 的路径都必须先剥 BOM，否则静默失败（表现：改参数从来不生效）。

## 1. 架构速查

```
C:\ProgramData\MythCoolInject\
  inject_main.py      ← 注入主体（Python，内含 3 段 JS：PATCH / MAIN / JS）
  Inject.ps1          ← 幂等入口，param([switch]$Force,[switch]$Probe)，末尾 exit 0
  InjectSilent.vbs    ← 无窗口调用 Inject.ps1
  Register-Task.ps1   ← 注册计划任务（每 1 分钟跑一次 Inject.ps1，按 PID 幂等跳过）
  tune.json           ← 热调参数（带 BOM！）改它 1.2 秒内生效，不用重跑脚本
  python\python.exe   ← 自带 Python 3.13 + frida
  log\inject.log      ← 注入日志（每次注入 ~20 行，[py] / [PS] 两种前缀）
  log\last_result.json← 注入时写一次的几何快照，运行期不回写
  log\tune_ack.txt    ← 每次热调推送的确认
  state\last_pid.txt  ← 幂等状态：已注入的 pid
```

**注入链路（三段）**：

```
Inject.ps1  ──挑出主进程 pid──▶  inject_main.py
                                    │ frida.attach(mainPid)
                                    ▼
                              Node/Electron 环境（JS 段：用 V8 C++ 符号编译执行）
                                    │ process.mainModule.require('electron')
                                    ▼
                              MAIN 段：BrowserWindow.getAllWindows() 找 mainpage.html
                                    │ webContents.executeJavaScript(PATCHCODE)
                                    ▼
                              PATCH 段：页面内真正干活的代码
                                          改 CSS / 加 DOM / 起节拍 / 挂 MO
```

**主进程判定**：`Inject.ps1` 用「父进程不在 MythCool 集合里」挑真正的主进程（Electron 派生一堆同启动时间的 `--type=gpu-process`，非提权读不到 CommandLine，按时间排序分不出来）。

**定稿源**：`tools/inject_main_v20_final.py`（`RES = { v: 20 }`）。改代码只改这个文件。
**版本号三处同值**（Python 头 `VER = N` / `RES = { v: N }` / `RES.ver = N`），synchk 强制断言，漏改一处直接 FAIL。

### ★ v20 变更（2026-09-30，外部评审采纳）

| 项 | 内容 |
|---|---|
| **A1 符号显式报错** | V8 mangled 符号（`?GetCurrent@Isolate@v8@@...`，与 Electron/V8 版本强耦合）找不到时：日志报 `SYM MISS` + `last_result.json` 写 `symMiss: true` + **exit 3**。旧版静默失败无诊断。**官方软件更新后的第一失效点**，自检步骤见仓库 README「版本升级自检」 |
| **A2 日志双值** | `initial tune push sent rms(文件)=N [将clamp到>=3500]` 与 `push ack: rms(生效)=N [原值被抬到3500]` —— 不再只有一个会骗人的数 |
| **A3 删 tick 死参数** | `tick` 从不在 DEF 里，从未生效过；docs/02 旧说法已纠错 |
| **B1 宿主拒绝降级** | `layerHost()` 找不到 `.mainpage_jx`/`.mainpage_jx1` 时不再静默挂进非旋转宿主（`.mainAll`/`.mainpage`/body，方向全错），改为 `RES.warn = 'hostFallbackBlocked'` + 拒绝挂载 |
| **B2 窗口存活检查** | `pushTune` 前查 `W.isDestroyed()`，坏了重跑 `findW()` —— 重插屏/分辨率切换后热调不再打在死窗口上 |

## 2. ★★ 坐标系 —— 最容易翻车的地方

**源码铁证**（`webapp_src/windows__pages__assets__css__mainpage.716c380e.css`）：

```css
.mainpage_jx  { transform:rotate(90deg);  position:absolute; top:300px; left:-300px }
.mainpage_jx1 { transform:rotate(270deg); position:absolute; top:300px; left:-300px }
.mainpage     { /* 非机箱模式，不转 */ }
```

JS 侧（`mainpage.9bcc6901.js`）按 `device360_960Rotate === 0 ? "mainpage_jx" : "mainpage_jx1"` 选类。

**实测几何（2026-09-29，360×960 @dpr1）**：

| 元素 | position | computed W×H | transform | transform-origin | offsetParent | rect |
|---|---|---|---|---|---|---|
| `.mainpage_jx` | absolute | **960×360** | rotate(90deg) | `480px 180px` | BODY | 0,0,360,960 |
| `.AeeCui`（皮肤行容器） | relative | **960×360** | none | `480px 180px` | **`.mainpage_jx`** | 0,0,360,960 |
| `#__mtc_layer`（正确做法） | absolute | 960×360 | none | 480px 180px | **`.mainpage_jx`** | 0,0,360,960 |

**关键推论**：
- `.AeeCui` 的 `offsetParent` 就是 `.mainpage_jx`、`left/top=0`、无 transform ⇒ **`.AeeCui` 局部系 ≡ `.mainpage_jx` 局部系**
- 所以浮层挂 `.mainpage_jx` 内 + `left:0;top:0;width:100%;height:100%` ⇒ **与 `.AeeCui` 完全重合**，元素的 `left/top` 数值**一个都不用改**
- **DOM 的 `left` 映射到用户视角的纵向（y），`top` 映射到横向（x）**。例：`tops={mbt:150,memt:188,vrt:226}` 是三个**横向**位置，视觉上竖向排列

**用户视角换算**（截图是 360×960 需 `rotate(90, expand=True)` 才是用户视角）：

```
用户 x' ∈ [ rect.top , rect.top + rect.height ]
用户 y' ∈ [ 360 - rect.left - rect.width , 360 - rect.left ]
```

**踩过的坑**：浮层挂 `document.body` + `position:fixed` ⇒ 脱离 rotate 子树 ⇒ 元素竖排、整体方向差 90°。**浮层绝不能挂 body。**

## 3. 工具速查（都在 `tools/`）

| 工具 | 用途 | 用法 | 需要提权 |
|---|---|---|---|
| `probe_geom.py` | **只读几何探针**，拿页面实时状态 + 方向健康自动判定 | `<MythCoolInject>\python\python.exe "<本文件>" [pid]` | **否** |
| `synchk.py` | 改完源码后的静态校验（AST + 三段 JS + CORE 标记 + 版本号一致性 + STALE 洁净断言） | `<python> "<本文件>" <源文件路径>` | 否 |
| `tplchk.py` | **装机脚本体检**：静态 10 项查 cmd 解析陷阱 + 动态 5 项拿真实文件核断言退出码方向 | `<python> "<本文件>" <install.cmd> <VER> <应放行源> <应拦住源>` | 否 |
| `gen_install.py` | **从模板生成某一版装机脚本**（保证纯 ASCII + CRLF + CONFIG 正确，并自动跑 trap audit）；新增版本只需往脚本里的 `NOTES` 字典加一条 | `<python> "<本文件>" <VER> [TAG] [SRC] [DST]` | 否 |
| `verify_markers.ps1` | UTF-8 安全的标记校验器，**取代 findstr**。`-Neg` 跑反向断言。退出码 0=全绿 / 1=缺必需 / 2=有违禁 / 3=文件不存在 | `powershell -File "<本文件>" -Path <源> -Ver <VER> [-Neg]` | 否 |
| `cmdcheck.py` | **交付 .cmd 前的强制校验器**：转 CRLF + 断言纯 ASCII / 零裸 LF / 所有 goto·call 目标存在 / 括号配平 / 无被延迟展开吃掉的裸 `!` | `<python> cmdcheck.py FILE.cmd [FILE2 ...] [--no-write]` | 否 |
| `Finalize_v19.cmd` | **v19 存档**（已被 v20 取代） | — | **是** |
| `Finalize_v20.cmd` | **★★★ 一键定稿包（清场 + 部署 v20 + 重注入）**：管理员终端跑一次。回退点自动升级为 `bak_v19`（从 v19 存档快照，bak_v17 保留作深回退）；验收两项：log 无 `SYM MISS`（用 logscan.ps1，UTF-8 安全）+ 无 `last_beat.json`。已过干跑验证 | `"<本文件>"`（**管理员终端**） | **是** |
| `logscan.ps1` | UTF-8 安全的日志子串检查（替代 findstr）：`-Path <log> -Need "SYM MISS"`。退出码 0=未找到 / 1=找到 / 3=文件读不到 | `powershell -File "<本文件>" -Path <log> -Need <子串>` | 否 |
| `gen_finalize.py` | 上面那个的**生成器**（复用 `gen_install.audit()` 做 cmd 陷阱审计） | `<python> "<本文件>"` | 否 |
| `inject_main_v19_final.py` | **v19 存档**（`RES = { v: 19 }`），已被 v20 取代，仅作回退 | — | 否 |
| `inject_main_v20_final.py` | **v20 定稿源（权威副本）**，`RES = { v: 20 }`。改代码改这个文件 | — | 否 |
| `install_template.cmd` | 装机包模板（**先验源** → 备份〔已有回退点则不覆盖〕 → 覆盖 → 强制重注入 → 回滚提示）。**不要手改**，用 `gen_install.py` 生成 | — | **是** |

- `probe_geom.py` / `synchk.py` / `tplchk.py` 的输出都写到**当前工作目录**，不硬编码路径
- `synchk.py` 的 node 路径走 `versions\current` + Glob 兜底，**不写死版本号**
- `probe_geom.py` 末尾会直接打印 `方向健康判定`：4 项全 `[OK]` = 方向正确；有 `[!!]` = 列出具体问题并 `exit 3`

> ⚠️ **跑 `probe_geom.py` 会让副屏画面闪一下 —— 这是 frida attach 短暂挂起主进程 + 强制同步布局的正常代价，不是故障。**
> 纪律：能读文件就不跑探针（§6 的数据出口已覆盖大部分问题）；探针只在「改完代码要验方向」或「文件数据对不上」时跑，一次跑完。

**方向判据速查**：

| 现象 | 含义 |
|---|---|
| `axisDirect.styleLeft` == `rectL` | **坐标直通 = 未旋转系 = 方向错了** |
| `styleLeft`(169) → `rectL`(111) | 被 rotate 映射过 ✅ 正确 |
| `layerInsideJx: true` + `layerParent: DIV.mainpage_jx` | 浮层位置正确 ✅ |
| 三元素 rect 的 `l` 递增、`t` 相同 | 用户视角里竖向排列 ✅ |

## 4. 改源 → 校验 → 装机

1. **改源**：只改 `tools/inject_main_v20_final.py`
2. **静态校验**：`python synchk.py <源>` —— AST + 三段 JS 各自 `node --check` + 关键标记计数 + STALE 洁净断言。**全绿才算改对**
3. **生成装机脚本**：`python gen_install.py <VER>`（**不要手改模板**）—— 保证纯 ASCII、CRLF、CONFIG 各行填对、自动跑 trap audit
4. **体检**：`python tplchk.py <装机脚本> <VER> <应放行源> <应拦住源>` —— 静态 10 项 + 动态 5 项全绿才能交付。动态项拿真实文件核对退出码方向（好源必须放行、旧源必须拦住），**别只跑正向** —— 只测「新的能过」的校验脚本可能是个永远返回 OK 的摆设
5. **交付**：用户在**管理员终端**跑装机脚本（v20 的一键定稿包需先用 `gen_finalize.py` 生成 `Finalize_v20.cmd`）

装机脚本六步（编号 `[N/6]`，**全程 goto，零括号块**）：

1. **先验源**：`verify_markers.ps1 -Neg` —— 一个字节都还没动就先确认源是对的，失败即 abort
2. **准备回退点**：`%BAK%` 已存在则**原样保留**（重跑不会把唯一回退点顶掉），不存在才从当前 `%DST%` 快照
3. 覆盖 `%DST%`；拷贝失败自动从 `%BAK%` 恢复
4. 强制重注入（`Inject.ps1 -Force`）
5. 清历史残留 + 等待落盘
6. 末尾打印回滚命令

**两条硬规矩**（生成器已强制，手写脚本时也要守）：

- 脚本必须**纯 ASCII + CRLF**；`echo` 行里的 `>` 写成 `^>`。**cmd 靠数括号找块尾** —— `if errorlevel 1 (` 块里一个多余 `)`（比如文案里的 `rotate(90deg)`）就会提前闭合块，后续命令语义全部错位 ⇒ 全程 goto、一个括号块都不留
- 校验器一律 `powershell -File x.ps1` 调用，**别把 PowerShell 逻辑塞进 `-Command` 一行流**；也别用 `findstr` 校验含 CJK 的 UTF-8 文件（按控制台代码页读，结果不可信）

## 5. tune.json 常用参数

```jsonc
{
  "ix": 169,                    // DOM left（用户视角 = 纵向位置）
  "iy": 150, "idy": 38,         // DOM top / 行距（用户视角 = 横向位置）
  "tops": {"mbt":150,"memt":188,"vrt":226},   // 逐项覆盖 top
  "hide": ["mbv"],              // 隐藏某些项
  "ifs": 20, "lw": 4.4,         // 项字号 / 标签最小宽(em)
  "vfs": 22, "vm": 0, "vg": 6,  // 电压字号 / 左边距 / 与值间隔
  "minw": 0,
  "refresh_ms": 3500,           // 自带刷新节拍。★真实行为：<3500 一律被保险丝抬到 3500
                                // （除非 "_allow_fast_tick": true）—— 写 3000 不会生效，
                                // 日志 rms(文件) 与 rms(生效) 是两个数，别看混
  "tick": 7,                    // ⚠️ v20 起已删除：从不在 DEF 里、从未生效过的死参数
  "css": "..."                  // 追加 CSS，插在样式表最后（能压过同权规则）
}
```

**热调**：`fs.watchFile(tune.json, {interval:1200})` —— 改完 1.2 秒内生效，**不用重跑脚本、不用提权**。这是唯一常驻开销（每 1.2s 一次 `stat`）。

**改坏了一起不算事**：把 `tune.json` 换回默认值，或重启 Myth.Cool 即回原始皮肤。

## 6. 排查指南：注入后出问题，先看哪里

**数据出口（都不用提权，直接读）**：

| 文件 | 内容 | 什么时候看 |
|---|---|---|
| `log\inject.log` | 每次注入写 ~20 行：挑中的 pid、版本号、`清掉残留样式 N 个` | 怀疑没注入上 / 版本不对 |
| `log\last_result.json` | 注入时的几何快照（各元素 rect、`inJx`、`axisDirect`） | 元素位置 / 方向不对 |
| `log\tune_ack.txt` | 每次热调推送的确认（含 JSON 解析结果） | 改了 tune.json 没反应 |
| `state\last_pid.txt` | 上次注入的 pid | 区分「幂等跳过」还是「真没跑」 |

**症状 → 看哪里 → 常见原因**：

| 症状 | 看哪里 | 常见原因 |
|---|---|---|
| 原生数值照变，新元素不更新 | `inject.log` 版本号 vs 源 `RES.ver` | 改了源没 `-Force` 重注入；或 guard 重入短路（踩坑表 #1） |
| 改 `tune.json` 完全没反应 | `tune_ack.txt` 是否新增 | BOM 没剥（踩坑表 #3）；或文件没保存 |
| 元素转 90° / 位置错乱 | `last_result.json` 的 `inJx` / `layerParent` | 浮层挂错父节点（§2） |
| 热调越改越卡、画面频繁重排 | `inject.log` 是否反复出现注入行 | 热调风暴（`applyN` 持续增长）→ 撤销最近改动对照 |
| 需要给注入器归因（是否它引起的问题） | 管理员终端停用计划任务对照 10 分钟 | `schtasks /Change /TN <任务名> /DISABLE`（任务名以安装时为准，仓库默认 `MythCoolSkinHack`），对照完 `/ENABLE` 恢复 |

### ⚠️ 注意事项：副屏「偶尔闪黑」与注入器的关系

- **不能完全确认本注入器没有任何影响，但它大概率不是闪黑的主因。** 停用注入器期间闪黑照样发生；作者个人判断大概率是 Myth.Cool 软件自身的问题，但具体环节在用户侧很难查清。
- **开发者最后采取的方案（大概率能好）**：卸载 Myth.Cool → 用清理软件清干净残留 → 官网重装 → 重启 → 重开注入。做完后开启注入的数小时内未再发现闪黑（观察期未结束，不能打包票）。
- 遇到闪黑先做「停用注入器 10 分钟」对照再归因；详细排查记录与网上案例区分见仓库 `docs/05-闪黑排查.md`。

## 7. 改皮肤踩坑表（浓缩）

| # | 症状 | 真因 | 修法 |
|---|---|---|---|
| 1 | 改代码后功能**静默失效**，数值照变但元素不更新 | `withGuard` 有重入短路（`if (GUARD) return null`），上层函数包了它，内层叶子函数的 `withGuard` **全部短路**，主体一次都没跑 | **只有叶子级 DOM 写入包 guard，上层调度函数绝不包** |
| 2 | **每次热调都闪一下**（改 tune.json 越勤闪得越密） | `cleanOld()` 的 `STALE` 列表里**误列了当前版本正在用的活节点**，每次 `applyAll()` 都把浮层和样式表删掉重建 | 清理列表**只留真正废弃的历史 id**；当前版本在用的必须剔除 |
| 3 | 改 `tune.json` **从来没生效过**；日志报 `Unexpected token \uFEFF` | 文件带 **UTF-8 BOM**，`JSON.parse` 拒吃 | 读文件即剥 BOM + 试 `JSON.parse` |
| 4 | 样式表**累积**（热调几十次就几十个 `<style>`） | `instCSS()` 每次 `createElement('style')` + `appendChild` | 改 `getElementById` 复用 + `textContent` **值比对去重**（同值赋值也会标脏样式表触发全页重算） |
| 5 | 注入后**没有任何 tune 推送日志**、热调链路从未武装 | `arm(w)` 被挂在 `executeJavaScript(...).then()` 里，Promise 因页面内异常 reject ⇒ 走 `.catch` ⇒ `arm()` 整个被跳过 | **`arm(w)` 无条件调用**，不挂 `.then`；页面侧自检段**整体包 try** |
| 6 | 明明注入成功却报"未确认" | `Copy-Item` 覆盖会把目标 mtime 设成**源文件**的 mtime，条件恒 false | 判据改成「日志长度变化 + tail 含成功字样 + 版本号」，**不要用 mtime** |
| 7 | 元素**方向转 90°** | 浮层挂 body 脱离 `.mainpage_jx` 的 rotate 子树 | **浮层挂 `.mainpage_jx` 内**，`position:absolute` + `100%×100%`（见 §2） |

## 8. 红旗清单（出现即停）

- 打算把浮层/DOM 节点挂到 `document.body` 或 `documentElement` 上
- 打算给上层调度函数（`refresh` / `applyAll`）包 `withGuard`
- 往 `STALE` 列表里加**当前版本正在用**的 id
- 用 `mtime` 做"注入是否成功"的判据
- 读完 `tune.json` 直接 `JSON.parse` 没剥 BOM
- 在没有 `.mainpage_jx` 兜底链的情况下写死 `body`
- 下"已验证修复"的结论，但手里没有 `last_result.json` / `inject.log` 的**当前数据**

## 9. 环境边界（VK03 实测）

| 项 | 结论 |
|---|---|
| `C:\ProgramData\MythCoolInject\` 目录 | **可新建**文件；**已存在的文件改不了**（ACL）⇒ 装机必须用户跑 .cmd |
| frida attach 主进程 | 当前终端权限够，**无需提权** |
| 副屏硬件（VK03 实测值，其他设备以实测为准） | `VID_345F&PID_9132&MI_03`（MS USB Display），360×960@60 |
| 目标页面 | `mythcool://<appid>/windows/pages/mainpage.html`（appid = `bd41175b47bf495092afff37c016a8e3`） |
| 皮肤源码（只读参考） | `<你的工作区>\webapp_src\`（gpk 已导出，**查皮肤行为优先读这里，比注入探测快且零风险**） |
| 幂等机制 | 计划任务每分钟跑 `Inject.ps1`，pid 未变则跳过。**改了源文件必须 `-Force` 才会重注入** |
| 重启后失效 | 覆盖了 `inject_main.py` 才算持久化。只跑源码注入 = 重启即回退 |

> ⚠️ **权限提示（通用）**：`C:\ProgramData\MythCoolInject\` 下已存在的文件受 ACL 保护，
> 普通终端改不动 ⇒ 装机/覆盖必须由用户在**管理员终端**跑生成的 .cmd；AI 只做备份、只读、只写新文件。
> 注入（frida attach）用注入器自带的 `python\python.exe`，普通权限即可，无需提权。
