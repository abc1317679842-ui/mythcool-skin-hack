# Myth.Cool Skin Hack

> **Don't replace the vendor app — patch its skin at runtime.**
>
> Add data fields, restyle widgets and re-layout the built-in skin of Myth.Cool
> (the official app for Valkyrie PC-case LCDs and AIO coolers) — with **zero file
> modification**, fully reversible, and with the official app, its skin store and
> touch input **kept intact**.

[中文](README.md) · English

---

## What it is

Myth.Cool is the official software for the whole Valkyrie line of LCD-equipped
hardware (E / V / B / B-GT / GLA / N series AIO coolers, R / AL / ML / DX series
air coolers, VK02 / VK03 / VK03-TOU / VK05 case screens).

Its skins are locked down: fixed layout, fixed set of data fields, memory/VRAM
shown only as a percentage. The skins live inside `webapp.gpk`, which is
**integrity-checked** — editing the file breaks the whole skin.

This project uses **Frida runtime injection** instead: a small script is pushed
into the Myth.Cool Electron main process, which forwards a patch to the renderer
(the skin page). The patch consists of

1. a `<style>` element (layout, font sizes, colors, positions)
2. a few self-created DOM nodes (new data fields)
3. a 3-second refresh tick so the new fields keep updating

**Everything lives in memory. No files written, no gpk touched, no USB driver
changed.** A scheduled task re-applies the patch whenever Myth.Cool restarts
(boot / wake from sleep / manual restart).

---

## How it differs from the "replace the vendor app" projects ★

Several open-source projects take the other route — bypass Myth.Cool entirely and
drive the USB display directly:

| Project | Lang | Route |
|---|---|---|
| [ZGMFX01A/MythCool-Lite](https://github.com/ZGMFX01A/MythCool-Lite) | Rust | Full replacement, own driver stack |
| [itsmylife44/LcdFusion](https://github.com/itsmylife44/LcdFusion) | C# | Direct USB, needs Zadig to rebind the driver |
| [codehz/msdisplay](https://github.com/codehz/msdisplay) | Python | Linux userspace driver |
| [kerbalwzy/lcdcanvas](https://github.com/kerbalwzy/lcdcanvas) | Python | Themed drawing framework |

Those are a better fit if you want to get rid of the vendor app entirely, or want
the (much lower) resource usage they advertise.

**This project is a better fit if you want to keep the vendor app:**

| | Replacement route | **This project** |
|---|---|---|
| Official features (sensors, skin store, RGB, fan control) | ❌ must close the app | ✅ **kept** |
| Official skins (incl. paid/collab ones) | ❌ unusable | ✅ **still work** |
| USB driver | ⚠️ Zadig rebind required | ✅ **untouched** |
| Touch / native interaction | ⚠️ may break | ✅ **kept** |
| File modification | — | ✅ **none** |
| Reversibility | uninstall driver | ✅ delete one scheduled task |
| Adding fields to the built-in skin | ❌ build your own panel | ✅ **add directly** |
| Live tweaking | recompile / restart | ✅ **edit a JSON, effective in 1s** |

**One line:** they *replace* the app; this project *modifies* it.

---

## Features

- 🎛 **Full control over the built-in skin** — position, size, color, spacing, order
- ➕ **New data fields** — mainboard temp/voltage, memory temp, VRAM temp, memory/VRAM in GB…
- 🔄 **Own refresh tick** — aligned with the native 3 s beat, value-deduplicated so it never fights Vue
- 🚀 **Auto-start** — a scheduled task checks every minute; ~120 ms per check, ~0.07 % of one core
- 🪟 **No window flash** — launched via `wscript.exe` (GUI subsystem) with a hidden child
- 🧩 **Idempotent** — only acts when the process actually changed; failures are never booked, so it retries
- 🔥 **Hot tuning** — edit `tune.json`, saved = live. No restart, no reinstall, no UAC
- ♻️ **Fully reversible** — delete the task and the folder, nothing left behind

## Requirements

- Windows 10 / 11
- Official **Myth.Cool** installed and working
- **Python 3.9+** on PATH (the installer builds a private venv and installs frida)

## Supported devices

Everything Myth.Cool drives, in principle — only the layout numbers in `tune.json`
need re-measuring per skin:

| Kind | Series |
|---|---|
| AIO liquid coolers | **E** / **V** / **B / B-GT** / **GLA** / **N** series (LCD models) |
| Air coolers | **R** / **AL** / **ML** / **DX** series (LCD models) |
| Case screens | **VK02** / **VK03** / **VK03-TOU** / **VK05** |

USB ids: case screens `345F:9132` (MS9132), AIO screens `374A:A021`.

## Keywords

Valkyrie · Myth.Cool · case screen · sub display · secondary LCD · AIO cooler display ·
LCD skin · runtime skin patching · Frida injection · Electron patch · add sensor fields ·
memory & VRAM in GB · mainboard / memory / VRAM temperature · case mod · PC modding ·
hardware monitor overlay · VK02 · VK03 · VK03-TOU · VK05 · MS9132 · 345F:9132

(中文关键词见 [README.md](README.md#关键词))

## Install

1. Download this repo anywhere (not a temp folder)
2. **Right-click → Run as administrator**: `tools\Install.bat`
3. The skin should visibly change right away

## Docs

All documentation is currently written in Chinese, with English summaries where it
matters. Start here:

| Doc | Content |
|---|---|
| [`docs/01-原理.md`](docs/01-原理.md) | Why injection; the V8 injection chain; why frida can detach |
| [`docs/02-使用与调参.md`](docs/02-使用与调参.md) | Install, `tune.json` reference, measuring positions |
| [`docs/03-持久化.md`](docs/03-持久化.md) | Scheduled-task design: idempotency, no window, performance |
| [`docs/04-踩坑合集.md`](docs/04-踩坑合集.md) | ★ **15 real pitfalls**, each with symptom → cause → fix |

## Disclaimer

- This project modifies a **running process's memory only**. It does not modify,
  copy or redistribute any file, binary or asset belonging to Myth.Cool / Valkyrie.
- "Valkyrie", "Myth.Cool" are used descriptively to indicate compatibility.
  Not an official product; no affiliation or endorsement.
- Injecting into a third-party process carries a theoretical stability risk.
  Use at your own discretion.

## License

MIT — see [LICENSE](LICENSE)
