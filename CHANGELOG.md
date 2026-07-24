# Changelog, NeewerLux

All changes relative to upstream [NeewerLite-Python v0.12d](https://github.com/taburineagle/NeewerLite-Python).

## v1.2.0 - 2026-07-24

Restores three features lost to a packaging error, then a cleanup pass over the codebase and the interface.

### Restored
- **Mode-aware hotkeys**. Brightness and slider shortcuts now act on each selected light according to that light's own mode, rather than only driving the sliders on the currently visible tab. A brightness nudge reaches CCT, HSI and Scene lights in one press. Adjustments that don't apply to a light's mode are skipped, so a hue change leaves CCT lights alone and a saturation change leaves Scene lights alone. Respects the Live Preview setting.
- **Configurable HTTP port**. The server port is now set in Global Preferences (1024-65535, default 8080) and persists in the prefs file. Useful when 8080 is already taken. Restart the HTTP server to apply.
- **Hotkey field rendering**. The shortcut fields in Global Preferences no longer draw Qt's internal clear button as an empty square. The external X button was always the one that worked.

### Fixed
- Replaced four blocks of repeated `if mainWindow is not None:` guards, two of which nested the identical check inside itself.
- Removed a stale `## NeewerLux ver. 1.0.5` header comment that contradicted the real version constant and had no way to stay in sync. Version now lives in exactly one place.
- Merged the file banner back into one block; the version constants had been splitting it in two.
- Dropped the now-unused `changeSliderValue`, superseded by the mode-aware hotkey path.

### Code Comments
- Module docstrings now describe what each module is rather than narrating past refactors.
- Trimmed commentary that restated the line beneath it or recounted bug-hunt history.
- Removed em-dashes from code comments and from interface text.

### Theming
- **Both themes now generate from one template.** Dark and light were parallel stylesheets with 31 duplicated selectors, so every styling change had to be made twice and kept in sync by hand. There is now a single template plus two colour token tables.
- **Palette cut from 71 colours to 45.** The old set had 19 clusters of perceptually identical values, accumulated one widget at a time. The remaining 7 clusters are adjacent elevation steps, which is how depth works in a dark interface.
- **Accent tokens are real.** `ACCENT`, `ACCENT_HOVER` and `ACCENT_DIM` were defined and then never referenced; the values were hardcoded 27 times. The template now has no hardcoded colours at all, and re-tinting the interface is a two-line change.
- Border radius follows a scale rather than five ad hoc values. The web dashboard gained matching CSS variables.
- Fixed two inconsistencies found while consolidating: `QPlainTextEdit` had no focus style, and the horizontal scrollbar had no hover state while the vertical one did.

### Typography
- The log and the JSON editor used different monospace fonts at the same size. Both now use one stack with proper fallbacks for macOS and Linux.

### Interface Copy
- **Feature lists rewritten as prose.** Both the Info tab and the dashboard listed capabilities as bold-term-then-comma-separated-dump, 21 bullets in total. They now read as sentences that explain what something is for.
- **Removed the duplicate.** Nine of twelve feature bullets were byte-identical across the Info tab and the dashboard, so editing one silently drifted from the other. The dashboard now carries a short orientation note and points to the Info tab.
- **Removed decorative emoji** from eleven dashboard headers and buttons that already had text labels. The play, stop and refresh glyphs stay, since those carry meaning on their own.
- Dropped copy that said nothing: an update checker described as checking for updates, a dashboard listing itself as a feature, a log described as thread-safe, and a positioning line aimed at people who had already installed the app.
- Removed an internal widget class name from user-facing text, and a stray brand-purple heading that appeared exactly once in the interface.
- Stopped telling people that collapsible sections can be clicked.

## v1.1.0 - 2026-07-15

### Fixed
- **Idle CPU creep**. CPU would climb from near-zero to 2-3% over a long session and reset on restart. The Log tab used an uncapped `QTextEdit`, and the worker thread appends to it continuously, so the document grew without bound and every append and repaint got progressively more expensive. The Log tab now uses `QPlainTextEdit` with `setMaximumBlockCount(2000)`, which keeps the document size and its cost flat regardless of uptime.

## v1.0.9 - 2026-07-14

### Fixed
- **Chained animation revert**. Interrupting one animation with another left the lights stranded on the final frame instead of reverting to the pre-animation state. The stopping thread set `animationRunning = False` (releasing `stopAnimation()`) before it read the chain flag, so the flag could be cleared underneath it and the revert would run anyway, wiping the saved states. The flag is now read into a local before that release, making the decision immune to the race.

## v1.0.8 - 2026-07-14

### Added
- **Open WebUI** button in the toolbar and system tray menu, enabled only while the HTTP server is running.

## v1.0.7 - 2026-07-14

### Changed
- **Single-source versioning**. The version string was hardcoded in 13 places across 3 files. Everything now derives from `NEEWERLUX_VERSION`: title bar, Info tab, tray tooltip, WebUI header/footer/about, legacy HTTP pages, console banner, and the Windows AppUserModelID.
- **Global Preferences reorganized** into Startup & Connection, Control & Presets, Light Behaviour, HTTP Server, Window & Display, Logging, Filtering, and Keyboard Shortcuts. No settings added or removed.

## v1.0.4 - 2026-07-13

### Fixed
- **Chained animation revert (first attempt)**. Animations no longer re-capture the pre-animation state when interrupting a running animation, so a chain reverts to the state that preceded the whole chain rather than an intermediate frame. Superseded by v1.0.9, which fixed the underlying thread race this attempt missed.

## v1.0.3 - 2026-07-13

### Added
- Configurable HTTP port, mode-aware hotkeys, and a fix for the shortcut fields rendering an empty square.

> **These changes did not survive into the shipped code.** Subsequent releases were packaged from a base that predated them, silently reverting all three. They were restored in v1.2.0. If you are reading this history to understand behaviour, treat v1.0.3 through v1.1.0 as not having these features.

## v1.0.2 - 2026-07-13

### Added
- **Animation loop control over HTTP GET**. The `animate` endpoint accepts `Name|speed|rate|bri|loop|maxLoops|revert`. All fields after the name are positional and optional, so `?animate=Halloween|1.0|10|50|true|2|true` plays twice at 50% and reverts. Previously loop and revert were reachable only via the POST JSON endpoint, which hardware like a Stream Deck cannot send directly.

## v1.0.1 - 2026-07-13

### Fixed
- **Animation names over HTTP**. The argument parser lowercases GET parameters, but animation names are stored with their original casing, so every `?animate=` request failed to match. Name lookup is now case-insensitive on both the GET and POST paths.
- **First-connect error in the exe**. The first `BleakClient.connect()` reliably fails in frozen builds while the WinRT backend initializes. A silent warm-up connect now absorbs that failure before the real connect runs, and a genuine first-attempt failure shows "Connecting..." rather than an error.

## v1.0.0 - 2026-03-20

First public release. Complete rewrite of UI, preset system, animation engine, threading model, and WebUI.

### Preset Editor
- **Visual Preset Editor**. Table-based dialog matching the animation editor's layout. Entry table with color-coded mode cells, toolbar (Add/Duplicate/Delete/Up/Down/Copy/Paste), and a shared editor panel with GradientSlider controls.
- **Per-light entries**. Presets can target individual lights or "All Lights". Each entry has independent mode (CCT/HSI/Scene) and parameter settings.
- **Target guardrails**. "All Lights" auto-disabled when multiple entries exist. Duplicate target selection prevented across entries.
- **Copy/paste**. Copies mode + parameter values (not target), enabling quick replication of settings across light entries.
- **Duplicate Preset**. Right-click context menu option, deep-copies preset data and name with "(copy)" suffix.
- Ships with 8 default presets: Warm Studio, Daylight, Cool White, Candlelight, Red Alert, Blue Mood, Purple Haze, Green Screen.

### Animation Presets
- **79 new animation presets** added (101 total, up from 22 in PJ5), organized by category:
  - Emergency: Police Flash, Ambulance, Fire Truck, Hazard
  - Rock Performance: Guitar Solo, Drum Solo, Metal Mosh, Encore, Power Ballad, Spotlight, Rock Anthem, Concert Build
  - Holidays: Christmas, Halloween, Valentine's, Easter, Hanukkah, New Year's Eve, St. Patrick's, Fourth of July
  - Practical/Studio: Interview, Warm Studio, Focus, Reading Light, Product Photo, Film Noir, Key Fill Rim, Dawn Simulator, Magic Hour, Golden Hour
  - Multi-Light Utility: Color Chase, Ping Pong, Ripple, Alternating Flash, Gradient Sweep, Warm Cascade, Identify Lights
  - Ambient/Smooth: Sunset Beach, Deep Sea, Cyberpunk, Synthwave, Romance, Aurora Multi, Matrix, Underwater, and many more
- **Identify Lights**. CCT-only utility animation that blinks each light N times matching its ID (1-4) for easy identification.
- Animations grouped in UI by category with bold non-selectable section headers.

### Animation Editor
- **Light filter combo**. "Show light:" dropdown above the keyframe table. Switches which light's parameters are displayed across all table rows for multi-light animations.
- **GradientSlider controls**. Replaced spinboxes with visual gradient sliders (hue rainbow, saturation white→red, brightness black→white, CCT warm→cool) that dynamically switch gradients, suffixes, and endpoint labels based on mode.
- **Copy/paste between keyframes**. Copy button grabs current light's params from selected frame, Paste applies to another frame's current light.
- **Scene dropdown**. Named scene selector (Police, Ambulance, Fire Truck, etc.) replaces raw number input in ANM/Scene mode.
- **Dynamic suffix fix**. GradientSlider `setSuffix()` method ensures value labels show correct units (°, %, 00K) when switching between modes.

### Gradient Sliders
- **Reusable widget** in `neewerlux_ui.py`, gradient bar + slider + value label + min/max endpoint labels, all in a grid layout so the gradient and slider share exact column width.
- Used consistently across the main GUI CCT/HSI tabs, Preset Editor, and Animation Editor.
- Supports `setSuffix()`, `setGradientStops()`, `setMinMaxLabels()`, `setRange()`, `setValue()`.

### Number Inputs
- **DPI-safe spinbox**. `QSpinBox(NoButtons)` with external `QPushButton("+")` / `QPushButton("-")` placed outside the spinbox frame, eliminating the overlap/click-through issue at 150%+ scaling that affected Qt's built-in PlusMinus and UpDownArrows styles.
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

### Background Thread Handling
- **`_updateResultSignal`**. Dedicated `QtSignal(str, str, str, str)` for update checker results, replacing the unreliable `QTimer.singleShot` approach from a background thread. Button always re-enables regardless of success/failure/404.
- **`_tableUpdateSignal`** / **`_logSignal`**. All 16+ background-thread `setTheTable` calls and log writes use Qt signals.

### Update Checker
- **GUI**. "Check for Updates" button on the Info tab. Hits GitHub Releases API in a background thread, shows green/blue/orange banner with download link.
- **WebUI**. "Check for Updates" button in the collapsible Info card, same GitHub API via `fetch()`.
- Version constant `NEEWERLUX_VERSION` introduced, though the value stayed hardcoded in several other places until v1.0.7.

### Interface
- **Select All button**. Light table corner widget replaced with a visible styled "☐ All" button with hover effect and tooltip.
- **Combo box dropdown arrows**. `QComboBox::down-arrow` CSS triangle added to both dark and light themes globally, fixing blank dropdown indicators.
- **"Bri:" → "Brightness:"**. Full label on animation tab.
- **Info tab**. `QTextBrowser` with `setOpenExternalLinks(True)` for clickable links. Added Releases link.
- **Log tab**. Consolas 9pt, clear/save buttons, buffered file writes (flush every 10s or 50 lines), auto-scroll only when at bottom, background thread log throttled to ~30s intervals.

### Build & Distribution
- **PyInstaller spec** (`NeewerLux.spec`), `--onedir` build with `--collect-all bleak` for WinRT DLLs, `.ico` icon.
- **GitHub Actions CI** (`.github/workflows/release.yml`), triggered on `v*` tags, builds exe on `windows-latest`, packages with `light_prefs/`, creates a draft GitHub Release.
- **Console visibility**. Exe is built windowed (`console=False`); the "hide console on startup" preference applies only to source runs and is hidden in the exe.
- `.bat` launchers retained for source runs, excluded from the exe release zip.
- `light_prefs/` ships alongside the exe and stays user-editable.

### Naming & Compatibility
- Full rename NeewerLite → NeewerLux throughout codebase.
- `pyside_exec()` compatibility wrapper for PySide2/6 `exec()` API difference.
- `shiboken` bare import crash fix, `setWeight` crash fix, stdout/stderr redirect for pythonw.exe.
- Broadened exception handling throughout.

---

## v0.12d-PJ5 - 2026-03-04

### UI Overhaul
- **Dark/Light theme toggle**. Full QSS theme system with PoizenJam brand colors. Toggle via moon/sun button in the toolbar.
- **System tray integration**. Closing the window minimizes to system tray. Double-click to restore. Tray context menu: Show/Hide, Toggle HTTP Server, Show/Hide Console, Quit.
- **Console window management**. Hide/show the Windows console window from the tray menu.
- **Scene button highlighting**. QSS property-based `activeScene` styling for dark/light theme compatibility.

### HTTP Server
- **GUI HTTP toggle**. Start/stop HTTP server from toolbar without restarting.
- **Modern web dashboard**. Full themed control panel at `http://localhost:8080/` with light table, sliders, animation browser, command log, and API reference.
- **JSON API endpoint**. `list_json` returns structured JSON with light status, animation list, and playback state.

### Animation Editor
- **Visual keyframe editor**. Color-coded keyframe table, per-frame controls with live color preview, add/duplicate/delete/reorder, synced JSON tab.

### New Files
- `neewerlux_theme.py`, dark/light QSS theme definitions
- `neewerlux_webui.py`, modern web dashboard HTML/JS
- `neewerlux_anim_editor.py`, visual keyframe editor dialog

## v0.12d-PJ4 - 2026-03-04

### Light Aliases
- **Preferred ID in Light Preferences**. Persistent light aliasing via custom name + preferred ID (0-99). GUI reorders by preferred ID. Aliases work in animations, HTTP commands, and all command paths.

### Animation Performance
- **Parallel BLE writes**. `asyncio.gather()` for simultaneous multi-light commands.
- **Status column restored**. Live animation values displayed in main light table.

### New Animation Presets (6 ambient)
- Campfire, Candlelight, Ocean Waves, Thunderstorm, Northern Lights, Lava Lamp (22 total).

## v0.12d-PJ3 - 2026-03-03

### Animation Performance
- Parallel BLE writes, removed double-blocking, throttled GUI updates, 10ms poll granularity, frame drop logging.
- **Brightness scaling**. New Bri: spinbox (5-100%) scales playback brightness.
- **9 new presets**. Concert Sweep, Bass Drop, Neon Nights, Stage Wash, Fire Flicker, Sunset Fade, DJ Pulse, Blackout Flash, Retrowave.
- Fixed smooth presets using `hold_ms: 0` for continuous motion.
- Fixed HTTP GET animate syntax error, resolved bleak deprecation.

## v0.12d-PJ2 - 2026-03-02

### Animation Engine
- Keyframe animation system with hold/fade timing, HSI shortest-path interpolation, loop wraparound fading, worker wake optimization, auto-stop, rate control.
- 7 initial presets, 6 template generators, JSON editor, HTTP GET/POST API.
- Fixed worker thread stutter from `animationRunning` skip bug.

## v0.12d-PJ1 - 2026-03-01

### Core Features
- Paginated presets with forward/back navigation, user-settable names.
- PySide6 migration with PySide2 fallback.
- Auto-reconnect on wake, batch HTTP commands, stale lock cleanup.
