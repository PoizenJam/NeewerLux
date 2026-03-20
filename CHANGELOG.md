# Changelog — NeewerLux

All changes relative to upstream [NeewerLite-Python v0.12d](https://github.com/taburineagle/NeewerLite-Python).

## v0.12d-PJ5 — 2026-03-04

### UI Overhaul
- **Dark/Light theme toggle** — full QSS theme system with PoizenJam brand colors (#9100ff purple + #00ff91 green). Stream Guardian-inspired aesthetic with proper styling for all widgets including tables, tabs, sliders, buttons, scrollbars, and tooltips. Toggle via moon/sun button in the toolbar.
- **System tray integration** — closing the window minimizes to system tray instead of quitting. Double-click tray icon to restore. Tray context menu provides Show/Hide, Toggle HTTP Server, Show/Hide Console, and Quit.
- **Console window management** — hide/show the Windows console window (cmd.exe) from the tray menu, eliminating the need for AutoHotkey workarounds.
- **Scene button highlighting** — replaced inline `setStyleSheet` calls with QSS property-based `activeScene` styling that works correctly with both dark and light themes.

### HTTP Server
- **GUI HTTP toggle** — start/stop the HTTP server directly from the toolbar button without restarting the program. Runs as a daemon thread. Button shows live ON/OFF state with green/grey indicator styling.
- **Modern web dashboard** — navigating to `http://localhost:8080/` now serves a full PoizenJam-themed control panel with live light table, CCT/HSI/Scene controls with sliders, animation browser with play/stop, command log, and collapsible API reference. All controls use the existing HTTP API endpoints.
- **JSON API endpoint** — new `list_json` endpoint returns structured JSON with light status, animation list, and playback state for the web dashboard (with HTML fallback for legacy clients).

### Animation Editor
- **Visual keyframe editor** — the Edit button now opens a full visual editor (pj_anim_editor.py) with a color-coded keyframe table, per-frame mode/parameter controls with live color preview, add/duplicate/delete/reorder frame buttons, and a synced JSON tab for power users. Falls back to the original JSON-only editor if the module is missing.

### Launchers
- `NeewerLux.bat` — launches the GUI via `pythonw` (no console window) with `python` fallback
- `NeewerLux-HTTP.bat` — launches HTTP-only mode on port 8080

### New Files
- `pj_theme.py` — dark/light QSS theme definitions
- `pj_webui.py` — modern web dashboard HTML/JS
- `pj_anim_editor.py` — visual keyframe editor dialog

## v0.12d-PJ4 — 2026-03-04

### Light Aliases
- **Preferred ID in Light Preferences** — the existing Light Preferences tab now includes a "Preferred ID" spinbox (0-99, 0=auto). Combined with the existing custom name field, this provides persistent light aliasing through the same prefs sidecar files that already store custom names, CCT ranges, and last-used parameters. No separate configuration file needed.
- **GUI reorder by preferred ID** — lights with preferred IDs are automatically sorted to the top of the table in ID order. The vertical row headers show each light's effective ID (preferred ID if set, else row number), so the numbers in the GUI match the IDs used in animations and HTTP commands.
- Aliases are rebuilt from prefs files on startup and refreshed immediately when preferences are saved or a custom name is set via HTTP.
- `returnLightIndexesFromMacAddress()` rewritten to resolve alias names (case-insensitive), preferred IDs, discovery-order numeric IDs, and raw MAC addresses. Works everywhere: animation keyframes, HTTP batch commands, all existing command paths.

### Animation Performance
- **Parallel BLE writes** — animation frames now send to all lights simultaneously via `asyncio.gather()`. With 4 lights, per-frame BLE time drops from ~200ms to ~50ms. Toggle-able via "Parallel" checkbox or HTTP `"parallel"` param for legacy adapter compatibility.
- **Status column restored** — the `psend` (parallel send) worker handler now calls `updateStatus()` + `setTheTable()` after each write, so the main light table shows live animation values again. This was an oversight in PJ3's parallel write implementation.

### GUI Fixes
- **Animations tab layout reworked** — fixed overlapping text between Loop/Parallel checkboxes, gave Export/Import JSON buttons adequate width (106px), repositioned all controls with proper spacing.
- **Speed tooltip added** — explains that the multiplier affects both hold and fade durations.
- **Rate tooltip updated** — now mentions that with Parallel enabled, throughput is ~15 updates/s regardless of light count.
- **Consistent label convention** — Speed:, Rate:, Bri: all use colons.

### New Animation Presets (6 ambient)
- **Campfire** — multi-light staggered warm flicker with independent per-light timing.
- **Candlelight** — gentle warm candle flicker with subtle hue and brightness movement.
- **Ocean Waves** — slow blue-green-teal undulation simulating ocean light reflections.
- **Thunderstorm** — dark moody blue ambient with random-feeling bright white lightning flashes.
- **Northern Lights** — slow-moving greens and purples across 4 independently addressed lights.
- **Lava Lamp** — deep saturated colors slowly morphing through reds, magentas, and purples.

Total preset count: 22 (up from 16 in PJ3).

## v0.12d-PJ3 — 2026-03-03

### Animation Performance
- **Parallel BLE writes** — animation frames now send commands to all lights simultaneously via `asyncio.gather()` instead of sequentially. With 4 lights, per-frame BLE time drops from ~200ms to ~50ms. Toggle-able via "Parallel" checkbox or HTTP `"parallel"` param for legacy adapter compatibility.
- **Removed double-blocking in `animationSendFrame`** — the function previously waited for the worker to be free, signaled it, then waited *again* for completion. The second wait was unnecessary (the next call's first wait handles sequencing) and was doubling effective per-frame latency.
- **Throttled GUI status updates** — `animStatusLabel.setText()` was being called from the animation thread on every keyframe. Cross-thread Qt widget calls can block on the GUI event loop, introducing stutters. Now throttled to max once per second.
- **10ms poll granularity** — worker-busy polling reduced from 50ms to 10ms sleep intervals, cutting average wait from ~25ms to ~5ms.
- **Frame drop logging** — dropped frames are now logged (`"Animation frame dropped: worker busy"`) instead of silently skipped.

### Animation Features
- **Brightness scaling** — new "Bri:" spinbox on the Animations tab (5-100%) scales all brightness values at playback time without modifying the animation JSON. Available via GUI, HTTP GET (`|brightness` as 4th pipe param), and HTTP POST (`"brightness"` or `"bri"` key, 0-100).
- **9 new animation presets** — Concert Sweep, Bass Drop, Neon Nights, Stage Wash, Fire Flicker, Sunset Fade, DJ Pulse, Blackout Flash, Retrowave.
- **Fixed smooth presets** — Rainbow Gradient, Color Cycle, Color Wash, Breathe, and Rainbow Chase all had `hold_ms` values (200-2000ms) creating unintentional pauses between transitions. All smooth presets now use `hold_ms: 0` for continuous motion.

### Bug Fixes
- **Fixed HTTP GET animate syntax error** — a misindented `briScale` try/except block would have crashed any GET animate request.
- **Bleak deprecation resolved properly** — removed global `FutureWarning` suppression; the actual deprecated `BLEDevice.rssi` call was already replaced with `AdvertisementData.rssi` via `return_adv=True` in the scanner. The `warnings` import is retained only for the scoped suppression in the old-Bleak fallback path.

## v0.12d-PJ2 — 2026-03-02

### Animation Engine
- **Keyframe animation system** — daemon thread running at configurable rate, iterating JSON keyframes with hold/fade timing, sending BLE commands via the worker thread's `threadAction` mechanism.
- **HSI shortest-path interpolation** — hue fades take the short way around the 360° wheel.
- **Loop wraparound fading** — added `prevFrameIndex` tracking so looping from the last keyframe back to frame 0 interpolates smoothly instead of snapping. Auto-borrows the last keyframe's `fade_ms` when frame 0 has `fade_ms: 0`.
- **Worker thread wake optimization** — replaced `time.sleep(0.25)` polling with `workerWakeEvent.wait(timeout=0.25)` so the animation thread can wake the worker immediately after setting `threadAction`.
- **Animation auto-stop** — selecting a preset, moving a slider, or sending a non-animation HTTP command stops any running animation and resets GUI button states.
- **Rate control** — renamed from "FPS" to "Rate" with tooltip explaining BLE throughput constraints by light count.
- **7 initial presets** — Police Flash, Strobe, Color Cycle, Rainbow Gradient, Rainbow Chase, Color Wash, Breathe.
- **6 template generators** — GUI dialogs for creating new animations from parameterized templates.
- **JSON editor** — inline editor tab for direct animation authoring.
- **HTTP GET/POST animation API** — remote play/stop/list control with speed, rate, and loop parameters.

### Bug Fixes
- **Worker thread stutter** — `if animationRunning: continue` inside the status-check block was skipping `threadAction` processing, causing 2-3 second gaps. Fixed by wrapping status checks in `if not animationRunning:` instead.

## v0.12d-PJ1 — 2026-03-01

### Core Features
- **Paginated presets** — arbitrary preset count with forward/back page navigation, replacing the fixed grid.
- **User-settable preset names** — middle-click any preset button to rename it. Names persist in the prefs file.
- **PySide6 migration** — full PySide2→PySide6 migration with transparent PySide2 fallback. `pyside_exec()` helper for API compatibility.
- **Auto-reconnect on wake** — background worker thread monitors connections and re-links lights after sleep/wake.
- **Batch HTTP commands** — send different parameters to different lights in a single HTTP request.
- **Stale lock file cleanup** — orphaned `.lock` files removed on startup.
