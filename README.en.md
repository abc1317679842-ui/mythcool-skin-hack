# Myth.Cool Skin Hack

> **Don't replace the vendor app — patch its skin at runtime.**
>
> Add data fields, restyle widgets and re-layout the built-in skin of Myth.Cool
> (the official app for Valkyrie PC-case LCDs and AIO coolers) — with **zero file
> modification**, fully reversible, and with the official app, its skin store and
> touch input **kept intact**.

[中文](README.md) · English

---

## Companion AI skill

Don't want to read the docs and measure coordinates yourself? This repo ships a
companion AI skill package, [`skill/`](skill/) — install it into your AI agent
and just say "add a mainboard temperature field" or "show memory in GB".

- **WorkBuddy**: copy to `~/.workbuddy/skills/mythcool-skin-injector/`
- **Claude Code**: copy to `~/.claude/skills/mythcool-skin-injector/`

The skill is not tied to specific hardware: the injection chain targets the
Myth.Cool app itself, **fully proven on a Valkyrie VK03 case screen (360×960)**;
other Myth.Cool devices (AIO cooler screens, other case screens) share the same
mechanism and will most likely work — re-measure the geometry with the bundled
probe tool. See [`skill/README.md`](skill/README.md).

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
| Dependency on the vendor app | ✅ none at all | ❌ **hard dependency** — vendor stops updating / changes the rendering stack or V8 → this project **breaks with it, possibly silently** (see below) |

**One line:** they *replace* the app; this project *modifies* it.

### Version-upgrade self-check (do this after every official app update) ★

The injection chain resolves **V8 MSVC mangled symbol names** (`?GetCurrent@Isolate@v8@@...`)
inside the Myth.Cool main process via Frida — these names are **tightly coupled to the V8
version**. When the vendor ships a new Electron/V8, the names change:

- **v20+**: missing symbols are reported explicitly — `SYM MISS` in the log,
  `"symMiss": true` in `last_result.json`, exit code 3. **No silent failure.**
- **v19 and earlier**: fails silently — everything looks fine but injection never succeeds.

After an official update: restart Myth.Cool, check the tail of `log\inject.log` for
`SYM MISS`; if present, re-dump symbols with `Module.enumerateExports` (match demangled
names like `Isolate::GetCurrent`), fill them back into the `Syms` table, run `synchk.py`,
then deploy. Also: `ProcessNotRespondingError` on attach usually means the **target process
runs elevated** while your terminal doesn't — check that before blaming symbols.

---

## Features

- 🎛 **Full control over the built-in skin** — position, size, color, spacing, order
- ➕ **New data fields** — mainboard temp/voltage, memory temp, VRAM temp, memory/VRAM in GB…
- 🔄 **Own refresh tick** — aligned with the native 3 s beat, value-deduplicated so it never fights Vue
- 🚀 **Auto-start** — a scheduled task checks every minute and re-patches when the
  process changed **or when the injector itself changed**. Sub-second per check.
  (v22 dropped the "pid unchanged -> skip" shortcut: it silently swallowed every
  injector update. Correctness beats the few hundred milliseconds it saved.)
- 🪟 **No window flash** — launched via `wscript.exe` (GUI subsystem) with a hidden child
- 🧩 **Idempotent** — only acts when the process or the injector changed; failures are never booked, so it retries
- 🎨 **Skin-aware** — layout applies only to the skins you list. Switch to another skin
  (including **custom skins** and anything unrecognised) and every change is **undone**
- 🩹 **Self-healing** — switching skins recreates the page and wipes the patch; a guard
  in the main process notices and **re-applies immediately**
- 🔥 **Hot tuning** — edit `tune.json`, saved = live. No restart, no reinstall, no UAC
- ♻️ **Fully reversible** — delete the task and the folder, nothing left behind

## Requirements

- Windows 10 / 11
- Official **Myth.Cool** installed and working
- **Python 3.9+** on PATH (the installer builds a private venv; if no base Python is found it
  falls back to the bundled embedded runtime -- the injector **resolves the interpreter at
  runtime**, hard-coding either layout breaks the other with `FATAL missing python`)

## Supported devices

> ⚠️ **Skin ids are device-specific.** The built-in ids (`AeeBiCui`, `DreamMonitoring`,
> `FallFlower2` — mode 31 / 29 / 30) were measured on **one** VK03 unit. Official skins get
> added and removed, and different devices ship with different defaults, so copying them
> to another machine will most likely match nothing.
> Run `skill/tools/probe_skins.py` (read-only) first: it lists the skins actually installed,
> their root class and mode number, and prints a ready-to-paste `_skinRules` block.
> Unrecognised = **left untouched** on purpose (safe default, not a failure).

Everything Myth.Cool drives, in principle — only the layout numbers in `tune.json`
need re-measuring per skin:

| Kind | Series |
|---|---|
| AIO liquid coolers | **E** / **V** / **B / B-GT** / **GLA** / **N** series (LCD models) |
| Air coolers | **R** / **AL** / **ML** / **DX** series (LCD models) |
| Case screens | **VK02** / **VK03** / **VK03-TOU** / **VK05** |

USB ids: case screens `345F:9132` (MS9132), AIO screens `374A:A021`.

## Known issue: occasional flicker-to-black (**separate topic, not a feature of this project**)

> This section is about **diagnosing a phenomenon**, not about what this project does.
> The flicker is not caused by the injector being active, and none of it belongs to the
> skin-patching workflow — the related tool (`freeze-anim/`) is a standalone diagnostic.

During development the author's case screen occasionally flickered to black for
tens to a few hundred milliseconds and recovered on its own, content intact.
After millisecond-level USB-stream log analysis, injector on/off A/B testing,
a clean reinstall, system-event forensics, skin comparison and **unpacking the
skin package to see what's actually inside it** — as of 2026-09-30 the status is:

> ### ⚠️ **The root cause was NOT found.** What follows is progress, not a conclusion.

- **Established facts**: ① the offending skin (AeeBiCui "Museum 1") has **a full-screen
  animated layer as its bottommost layer** (reproducible by unpacking the package);
  ② after freezing **only that layer**, **6–7 hours of testing turned up no recurrence**
  (previously several times per day / within hours).
- **★ The key distinction is not "is anything animated" but "*which layer*" is animated.**
  **Stock skins have animation too** (particles and other upper-layer effects), but their
  **bottommost layer is not a full-screen animated layer**; AeeBiCui's is **one full-screen
  animated layer covering everything**. In this test **only that bottom layer was frozen —
  the upper GIFs, particles, carousel and number refresh all kept animating** — and the
  flicker stopped appearing. That points at **"this layer's position/level is special"**,
  not at "any animation causes flicker".
- **"Why this layer flickers" = unknown**, and **no low-level evidence for this layer was
  ever captured** (the author decided not to dig further).
- **Several possibilities** are listed in docs/05 §4.6, but they are **unverified
  speculation — do not cite them as conclusions**.
- **Transport/hardware side is ruled out**: the USB stream heartbeat is perfect
  at the exact moment of a flicker; injector log and system events are clean.
- **The clean reinstall only mitigates** (flicker returned the same evening
  after a reinstall). Cheapest step, still worth doing, but don't expect it to
  solve the problem alone.
- Public reports of "black screens" are **not necessarily the same phenomenon**:
  some accompany full-system freezes, some were screen-batch defects (there is
  at least one "replaced by support, fixed" report). Compare carefully before
  blaming anything.
- The observation window was only **6–7 hours**, not a long-term verification;
  skins differ per device, so **this says nothing about your machine**.

If you want to investigate this yourself: docs/05 gives a **reusable triage
recipe** (first identify *which layer* flickers → unpack the skin to see whether its
bottom layer is one full-screen animated layer → freeze only that layer as an A/B
test → compare against a stock skin → …).
Tools live in [`freeze-anim/`](freeze-anim/) and
[`tools/gpk_dump.py`](tools/gpk_dump.py) — standalone, reversible, read-only.
**This repo does not freeze any skin's animations by default** — whether to do
so is your call, see docs/05 §4.7.

Full write-up (phenomenon classification, layer-by-layer analysis, the freeze
A/B test, **possible causes (unverified)**, ruled-out causes, sourced case table, triage
order) in [`docs/05-闪黑排查.md`](docs/05-闪黑排查.md) (Chinese).

## Keywords

Valkyrie · Myth.Cool · case screen · sub display · secondary LCD · AIO cooler display ·
LCD skin · runtime skin patching · Frida injection · Electron patch · add sensor fields ·
memory & VRAM in GB · mainboard / memory / VRAM temperature · case mod · PC modding ·
hardware monitor overlay · VK02 · VK03 · VK03-TOU · VK05 · MS9132 · 345F:9132

**flicker / blackout**
screen flicker · flicker to black · black screen · screen goes black briefly ·
screen flashing · display flickering · LCD blackout · secondary screen flicker ·
case screen blackouts · screen flicker troubleshooting · flicker caused by injector?

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
| [`docs/03-持久化.md`](docs/03-持久化.md) | Scheduled-task design: idempotency (PID + injector hash), no window, **self-healing after the page is rebuilt**, performance |
| [`docs/04-踩坑合集.md`](docs/04-踩坑合集.md) | ★ **32 real pitfalls**, each with symptom → cause → fix |
| [`docs/05-闪黑排查.md`](docs/05-闪黑排查.md) | **Standalone flicker-triage write-up (cause not found)**: classification, layer-by-layer analysis, skin-package unpacking, the bottom-layer-only freeze A/B test, **possible causes (unverified)**, ruled-out causes, sourced cases, triage order |
| [`freeze-anim/`](freeze-anim/) | Flicker diagnostic tool (**independent of the injector**): freeze / undo / status the CSS animations of one skin, for A/B testing whether flicker comes from page animation |

## Uninstall

First check what the task is actually called on your machine (older installers
used a different name):

```bat
schtasks /Query /FO LIST | findstr /i MythCool
```

```bat
schtasks /Delete /TN MythCoolInject /F
rmdir /s /q C:\ProgramData\MythCoolInject
```

**Scheduled tasks used by this project**: `MythCoolInject` (older installers may
have registered the legacy name `MythCoolSkinHack` — either name is fine to
delete, there is no third one). If your machine also
has `MythCoolScreenFix` / `MythCoolFix` (`C:\ProgramData\MythCoolFix\`) — that is a
**separate** wake-from-sleep repair tool (restarts Myth.Cool after sleep), **not part of
this project**. The two coexist fine: after it restarts Myth.Cool, this project's task
re-injects within a minute.

## Disclaimer

- This project modifies a **running process's memory only**. It does not modify,
  copy or redistribute any file, binary or asset belonging to Myth.Cool / Valkyrie.
- "Valkyrie", "Myth.Cool" are used descriptively to indicate compatibility.
  Not an official product; no affiliation or endorsement.
- Injecting into a third-party process carries a theoretical stability risk.
  Use at your own discretion.

## License

MIT — see [LICENSE](LICENSE)
