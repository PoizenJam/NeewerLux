# Changelog — NeewerLux

All changes relative to upstream [NeewerLite-Python v0.12d](https://github.com/taburineagle/NeewerLite-Python).

## v1.0.0 — 2026-03-20

First public release. Complete rewrite of UI, preset system, animation engine, threading model, and WebUI.

### Preset Editor (New)
- **Visual Preset Editor** — table-based dialog matching the animation editor's layout. Entry table with color-coded mode cells, toolbar (Add/Duplicate/Delete/Up/Down/Copy/Paste), and a shared editor panel with GradientSlider controls.
- **Per-light entries** — presets can target individual lights or "All Lights". Each entry has independent mode (CCT/HSI/Scene) and parameter settings.
- **Target guardrails** — "All Lights" auto-disabled when multiple entries exist. Duplicate target selection prevented across entries.
- **Copy/paste** — copies mode + parameter values (not target), enabling quick replication of settings across light entries.
- **Duplicate Preset** — right-click context menu option, deep-copies preset data and name with "(copy)" suffix.
- Ships with 8 default presets: Warm Studio, Daylight, Cool White, Candlelight, Red Alert, Blue Mood, Purple Haze, Green Screen.

### Animation System — 101 Presets
- **79 new animation presets** added (101 total, up from 22 in PJ5), organized by category:
  - Emergency: Police Flash, Ambulance, Fire Truck, Hazard
  - Rock Performance: Guitar Solo, Drum Solo, Metal Mosh, Encore, Power Ballad, Spotlight, Rock Anthem, Concert Build
  - Holidays: Christmas, Halloween, Valentine's, Easter, Hanukkah, New Year's Eve, St. Patrick's, Fourth of July
  - Practical/Studio: Interview, Warm Studio, Focus, Reading Light, Product Photo, Film Noir, Key Fill Rim, Dawn Simulator, Magic Hour, Golden Hour
  - Multi-Light Utility: Color Chase, Ping Pong, Ripple, Alternating Flash, Gradient Sweep, Warm Cascade, Identify Lights
  - Ambient/Smooth: Sunset Beach, Deep Sea, Cyberpunk, Synthwave, Romance, Aurora Multi, Matrix, Underwater, and many more
- **Identify Lights** — CCT-only utility animation that blinks each light N times matching its ID (1-4) for easy identification.
- Animations grouped in UI by category with bold non-selectable section headers.

### Animation Editor Enhancements
- **Light filter combo** — "Show light:" dropdown above the keyframe table. Switches which light's parameters are displayed across all table rows for multi-light animations.
- **GradientSlider controls** — replaced spinboxes with visual gradient sliders (hue rainbow, saturation white→red, brightness black→white, CCT warm→cool) that dynamically switch gradients, suffixes, and endpoint labels based on mode.
- **Copy/paste between keyframes** — Copy button grabs current light's params from selected frame, Paste applies to another frame's current light.
- **Scene dropdown** — named scene selector (Police, Ambulance, Fire Truck, etc.) replaces raw number input in ANM/Scene mode.
- **Dynamic suffix fix** — GradientSlider `setSuffix()` method ensures value labels show correct units (°, %, 00K) when switching between modes.

### GradientSlider Widget (New)
- **Reusable widget** in `neewerlux_ui.py` — gradient bar + slider + value label + min/max endpoint labels, all in a grid layout so the gradient and slider share exact column width.
- Used consistently across the main GUI CCT/HSI tabs, Preset Editor, and Animation Editor.
- Supports `setSuffix()`, `setGradientStops()`, `setMinMaxLabels()`, `setRange()`, `setValue()`.

### SpinBoxWithButtons Widget (New)
- **DPI-safe spinbox** — `QSpinBox(NoButtons)` with external `QPushButton("+")` / `QPushButton("-")` placed outside the spinbox frame, eliminating the overlap/click-through issue at 150%+ scaling that affected Qt's built-in PlusMinus and UpDownArrows styles.
- `SizePolicy.Expanding` vertically so buttons match spinbox height.
- Used for animation tab controls: Loops, Rate, Brightness.

### Global CCT Range
- **User-editable CCT bounds** in Global Preferences (2700K–8500K, default 3200K–5600K).
- Flows to CCT tab slider, Preset Editor, and Animation Editor.
- Per-light CCT range overrides in Light Preferences take precedence.
- Full prefs pipeline: global var → UI spinbox → save/load → prefsParser.

### CCT Clamping
- **Software-side CCT clamping** on all BLE write paths (`writeToLight`, `parallelWriteToLights`).
- `clampCCTForLight()` checks temp against the light's effective range (per-light override or global default).
- Honors the existing "Incompatible command handling" setting: Convert mode clamps to nearest boundary, Ignore mode skips the light.
- `hsiToCCTByteVal()` now maps hue to the global CCT range instead of hardcoded 32–56.

### Thread Safety
- **`_updateResultSignal`** — dedicated `QtSignal(str, str, str, str)` for update checker results, replacing the unreliable `QTimer.singleShot` approach from a background thread. Button always re-enables regardless of success/failure/404.
- **`_tableUpdateSignal`** / **`_logSignal`** — all 16+ background-thread `setTheTable` calls and log writes use Qt signals.

### Update Checker
- **GUI** — "Check for Updates" button on the Info tab. Hits GitHub Releases API in a background thread, shows green/blue/orange banner with download link.
- **WebUI** — "Check for Updates" button in the collapsible Info card, same GitHub API via `fetch()`.
- Version constant `NEEWERLUX_VERSION` defined once, referenced everywhere.

### UI Polish
- **Select All button** — light table corner widget replaced with a visible styled "☐ All" button with hover effect and tooltip.
- **Combo box dropdown arrows** — `QComboBox::down-arrow` CSS triangle added to both dark and light themes globally, fixing blank dropdown indicators.
- **"Bri:" → "Brightness:"** — full label on animation tab.
- **Info tab** — `QTextBrowser` with `setOpenExternalLinks(True)` for clickable links. Added Releases link.
- **Log tab** — Consolas 9pt, clear/save buttons, buffered file writes (flush every 10s or 50 lines), auto-scroll only when at bottom, background thread log throttled to ~30s intervals.

### Build & Distribution
- **PyInstaller spec** (`NeewerLux.spec`) — `--onedir` build with `--collect-all bleak` for WinRT DLLs, `.ico` icon, excludes unused PySide6 modules.
- **GitHub Actions CI** (`.github/workflows/release.yml`) — triggered on `v*` tags, builds exe on `windows-latest`, packages with `light_prefs/`, creates GitHub Release with download.
- **Console visibility** — exe built with `console=True`, but `hideConsoleOnLaunch` defaults to `True` for frozen exe builds and `False` for source. Toggle in Global Preferences.
- `.bat` launchers removed — exe replaces them entirely.
- `requirements.txt` — `PySide6>=6.5.0`, `bleak>=0.21.0`.
- `.gitignore` — ignores runtime files, keeps shipped defaults tracked.

### Naming & Compatibility
- Full rename NeewerLite → NeewerLux throughout codebase.
- `pyside_exec()` compatibility wrapper for PySide2/6 `exec()` API difference.
- `shiboken` bare import crash fix, `setWeight` crash fix, stdout/stderr redirect for pythonw.exe.
- Broadened exception handling throughout.

---

## v0.12d-PJ5 — 2026-03-04

### UI Overhaul
- **Dark/Light theme toggle** — full QSS theme system with PoizenJam brand colors. Toggle via moon/sun button in the toolbar.
- **System tray integration** — closing the window minimizes to system tray. Double-click to restore. Tray context menu: Show/Hide, Toggle HTTP Server, Show/Hide Console, Quit.
- **Console window management** — hide/show the Windows console window from the tray menu.
- **Scene button highlighting** — QSS property-based `activeScene` styling for dark/light theme compatibility.

### HTTP Server
- **GUI HTTP toggle** — start/stop HTTP server from toolbar without restarting.
- **Modern web dashboard** — full themed control panel at `http://localhost:8080/` with light table, sliders, animation browser, command log, and API reference.
- **JSON API endpoint** — `list_json` returns structured JSON with light status, animation list, and playback state.

### Animation Editor
- **Visual keyframe editor** — color-coded keyframe table, per-frame controls with live color preview, add/duplicate/delete/reorder, synced JSON tab.

### New Files
- `neewerlux_theme.py` — dark/light QSS theme definitions
- `neewerlux_webui.py` — modern web dashboard HTML/JS
- `neewerlux_anim_editor.py` — visual keyframe editor dialog

## v0.12d-PJ4 — 2026-03-04

### Light Aliases
- **Preferred ID in Light Preferences** — persistent light aliasing via custom name + preferred ID (0-99). GUI reorders by preferred ID. Aliases work in animations, HTTP commands, and all command paths.

### Animation Performance
- **Parallel BLE writes** — `asyncio.gather()` for simultaneous multi-light commands.
- **Status column restored** — live animation values displayed in main light table.

### New Animation Presets (6 ambient)
- Campfire, Candlelight, Ocean Waves, Thunderstorm, Northern Lights, Lava Lamp (22 total).

## v0.12d-PJ3 — 2026-03-03

### Animation Performance
- Parallel BLE writes, removed double-blocking, throttled GUI updates, 10ms poll granularity, frame drop logging.
- **Brightness scaling** — new Bri: spinbox (5-100%) scales playback brightness.
- **9 new presets** — Concert Sweep, Bass Drop, Neon Nights, Stage Wash, Fire Flicker, Sunset Fade, DJ Pulse, Blackout Flash, Retrowave.
- Fixed smooth presets using `hold_ms: 0` for continuous motion.
- Fixed HTTP GET animate syntax error, resolved bleak deprecation.

## v0.12d-PJ2 — 2026-03-02

### Animation Engine
- Keyframe animation system with hold/fade timing, HSI shortest-path interpolation, loop wraparound fading, worker wake optimization, auto-stop, rate control.
- 7 initial presets, 6 template generators, JSON editor, HTTP GET/POST API.
- Fixed worker thread stutter from `animationRunning` skip bug.

## v0.12d-PJ1 — 2026-03-01

### Core Features
- Paginated presets with forward/back navigation, user-settable names.
- PySide6 migration with PySide2 fallback.
- Auto-reconnect on wake, batch HTTP commands, stale lock cleanup.
