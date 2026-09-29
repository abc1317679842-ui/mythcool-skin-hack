# skill/ — mythcool-skin-injector 配套技能

本目录是 [mythcool-skin-hack](../README.md) 的配套 AI 技能包，遵循主流智能体的 `SKILL.md` 约定
（WorkBuddy / Claude Code / 其他支持 Agent Skills 的助手）。

**适用范围**：技能针对的是 Myth.Cool 这套驱动/皮肤软件本身，不绑定具体硬件 ——
已在**瓦尔基里 VK03 机箱副屏（360×960）**上全套实测成功；其他 Myth.Cool 设备
（水冷头、其他型号机箱屏等）机制相同、大概率通用，几何细节用技能自带的探针工具实测即可。

## 安装

把整个 `skill/` 目录（或其内容）复制到你的智能体技能目录：

| 助手 | 技能目录 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/mythcool-skin-injector/` |
| Claude Code | `~/.claude/skills/mythcool-skin-injector/` |

## 前置条件

- Windows + 已安装 Myth.Cool（机箱副屏 / 水冷头等设备的驱动与皮肤软件）
- 注入器本体已部署（见仓库 README：`C:\ProgramData\MythCoolInject\`）
- 部署/覆盖注入器文件需要**管理员终端**；日常热调 `tune.json` 不需要

## 目录

- `SKILL.md` — 技能正文（架构速查 / 四条铁律 / 坐标系 / 工具表 / 改源-校验-装机流程 / tune.json 参数 / 排查指南 / 踩坑表 / 红旗清单）
- `tools/` — 校验与装机脚本（`synchk.py` 静态校验、`gen_install.py` 生成装机包、`cmdcheck.py` cmd 陷阱检查、`probe_geom.py` 几何探针等）
  - ⚠️ 工具内的本机绝对路径已替换为 `C:\ProgramData\MythCoolInject\skill` / `\workspace` 占位，
    首次使用前请按你的实际安装位置全局搜索替换
