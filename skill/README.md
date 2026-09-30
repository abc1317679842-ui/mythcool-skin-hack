# skill/ — mythcool-injector 配套技能

本目录是 [mythcool-skin-hack](../README.md) 的配套 AI 技能包，遵循主流智能体的 `SKILL.md` 约定
（WorkBuddy / Claude Code / 其他支持 Agent Skills 的助手）。

**适用范围**：技能针对的是 Myth.Cool 这套驱动/皮肤软件本身，不绑定具体硬件 ——
已在**瓦尔基里 VK03 机箱副屏（360×960）**上全套实测成功；其他 Myth.Cool 设备
（水冷头、其他型号机箱屏等）机制相同、大概率通用，几何细节用技能自带的探针工具实测即可。

## 安装

把整个 `skill/` 目录（或其内容）复制到你的智能体技能目录：

| 助手 | 技能目录 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/mythcool-injector/` |
| Claude Code | `~/.claude/skills/mythcool-injector/` |

> ⚠️ **本目录的 `SKILL.md` 与已安装的那份必须保持一致。**
> 同名的技能正文会同时存在于「仓库」和「本机技能目录」两处，各改一点就会漂移成两份不同文档
> （2026-09-30 实测过一次：本机那份还停在 v19、仓库那份已经讲到 v22）。
> 检查/同步用：
> ```bash
> python skill/tools/skillsync.py            # 只检查
> python skill/tools/skillsync.py --to-local # 以仓库为准，推到本机技能目录
> ```
> `repochk.py` 也会顺手警告不一致。

## 前置条件

- Windows + 已安装 Myth.Cool（机箱副屏 / 水冷头等设备的驱动与皮肤软件）
- 注入器本体已部署（见仓库 README：`C:\ProgramData\MythCoolInject\`）
- 部署/覆盖注入器文件需要**管理员终端**；日常热调 `tune.json` 不需要

## 目录

- `SKILL.md` — 技能正文（架构速查 / 六条铁律 / 坐标系 / **皮肤识别与分皮肤绑定** / **主进程自愈守卫** /
  工具表 / 改源-校验-装机流程 / tune.json 参数 / 反借口表 / 踩坑表 / 红旗清单 / 环境边界）
- `tools/` — 校验器与探针：
  - `synchk.py` 单文件静态校验（AST + 三段 JS + CORE 标记 + 版本三处同值 + STALE 洁净 + beat 移除）
  - `repochk.py` 交付物 + 跨文件一致性（任务名 / 安装路径 / 定稿源与装机模板同版本）
  - `probe_geom.py` 几何探针 · `probe_skins.py` **皮肤探测（换机器必跑，只读）**
  - `skillsync.py` 本文件与已安装技能正文的一致性检查/同步
  - `cmdcheck.py` cmd 陷阱检查 · `gen_install.py` / `tplchk.py` / `verify_markers.ps1` / `logscan.ps1`
    （后四个属于 v19/v20 的装机包流水线，v22 起交付改走「定稿源 + synchk + repochk + 手动 Copy-Item」，仍可用于审任何 `.cmd`）
  - ⚠️ `SKILL.md` 与工具里一律用**占位符**写路径，不写死某台机器：
    `<仓库目录>` = 本仓库位置 ｜ `<技能目录>` = 本技能安装位置 ｜ `<工作区>` = 你放源文件/产物的目录。
    首次使用前按你机器上的实际位置替换即可（`C:\ProgramData\MythCoolInject\` 是注入器固定运行时目录，不用换）。
