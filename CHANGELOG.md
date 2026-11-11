# NeewerLux changelog

Changes relative to upstream [NeewerLite-Python v0.12d](https://github.com/taburineagle/NeewerLite-Python).

## v1.3.2 - 2026-11-11

### Added
- **Simulated lights.** A rig of 1 to 4 virtual lights (key, fill, rim, ambient), plus an optional CCT-only light, set in Global Preferences or for one run with `--simulate` / `--simulate=N`. They take the same Bluetooth packets as real lights (including the split packets older CCT-only lights use), answer power and channel queries, get their own saved preferences with roles and IDs 91 to 95, and work alongside real lights. `--simulate-faults` makes them drop about 2% of writes and disconnect every few minutes, for testing reconnects.
- **Stage window** (toolbar button): one tile per light in sweep order with its approximate current colour, mode and brightness, and an outline showing which layer drives it. A colour swatch beside each light in the table, and `color`, `mode`, `bri`, `linked` and `simulated` per light in `status_json`.
- **Sequence render.** `render` on `POST /NeewerLux/sequence` plays a sequence on a simulated clock against the current lights, with brightness limits, Locked lights and the CCT-only fallback applied, and returns each light's colour changes and the cue list as JSON, or an image strip with `"format": "png"`. A Render button on the Sequences panel shows the strip.
- **Web dashboard parity.** The dashboard gets a Sequences panel (list, play, pause and resume, seek by clicking the progress bar, stop, render drawn in the browser so it works without the desktop window, reload), a live Stage view, colour swatches, roles and layers in the light table, the animation status, and Settings panels for each light's preferences (name, preferred ID, colour temperature range, CCT-only, role, side, sweep order, eye line, brightness limits, Locked) and the show-related global preferences (brightness limits, sequence frame rate, effect time limit, global CCT range, CCT-only handling, simulated lights). New `POST /NeewerLux/settings` (`get`, `set_light`, `set_global`) and a `reload` action on `/NeewerLux/sequence`. Network access, keyboard shortcuts and startup options stay desktop-only. Settings changed from the browser show up in the desktop window straight away. `tests/test_webui.py` drives the real dashboard in a headless browser (Qt WebEngine, part of PySide6).
- **Packet tests** (`tests/test_wire.py`): fixed byte vectors for every packet NeewerLux sends, and the simulator's decoder checked against the encoder. The test harness now runs on simulated lights, so status polling and notification subscriptions are tested too.

### Fixed
- **The default state for a newly found light had a wrong checksum** (`[120, 135, 2, 20, 56, 157]`; 157 belongs to 100% brightness, 20% needs 77). A light ignores such a packet, so reverting a light that had never been sent anything else did nothing. Also corrected in the initial slider value.
- **Status polling blocked the worker for about two seconds per round**: it waited a fixed 250 ms after each query although lights reply in a few milliseconds. It now checks for the reply every 25 ms (same timeout), and skips the power and channel reads as soon as a sequence or effect starts mid-round, so a show's first frames no longer wait behind the poll.
- A Bluetooth scan that fails (no adapter, or Bluetooth off) no longer stops the background thread; it is logged and simulated lights carry on.
- The Stage, swatches, `status_json` and renders show what each light was actually sent: a CCT-only light asked for a colour shows the white it was converted to, and a render's starting state goes through the same conversion and brightness limits. Requested values are still what presets and reverts use.
- Dim lights no longer look black or grey on screen: any lit light keeps at least 40% of its colour; 0% and off still show as dark.
- The shipped example sequence now gives a practical (CCT-only) light two colour cues, so it no longer sits still through the demo.
- The Info tab and the HTTP help page list sequence, layer and status commands.

## v1.3.1 - 2026-11-03

### Added
- **Sequences.** Timed light shows for songs: cues that set a colour with a fade, or play an animation stretched or looped to fit, on chosen lights. Files live in `light_prefs/sequences`; the format is documented in `docs/SEQUENCE_FORMAT.md` for hand-writing or generating per song. Play, pause, resume, stop, seek and an external position sync (small offsets slew at up to 5%, large ones jump) from the new Sequences panel on the Animations tab, from GET (`sequence=`) or POST `/NeewerLux/sequence`, which can also validate, save and list sequences and play one sent inline. A shipped example covers a four-light rig.
- **Return to the starting state.** When a sequence ends or is paused, the lights go back to the state they were in before it started, usually a preset; resuming carries on from the same point. A sequence can instead hold its last frame or recall a specific preset at the end.
- **Layers.** Animations can play as an *override* (the existing one-at-a-time behaviour, still the default for every URL, the GUI and the pedal), an *effect* (queued or cutting in, for Streamer.bot redeems, bits, subs and raids; forever-looping effects stop after a configurable 30 s), or a *show*. Each light follows the highest layer driving it, so an effect on some lights leaves the rest on the sequence, and the covered lights rejoin it in time when the effect ends. Sequences can instead pause while interrupted. `animate=` takes optional layer, queue mode and target fields; `stop_layer=` stops a layer; `status_json` reports layers, the effect queue, the sequence position and the layer driving each light.
- **Light roles.** Light Preferences sets a role (key, fill, rim, ambient, practical), side, sweep order and eye-line flag per light. Targets such as `@rim`, `@left`, `@rim.left`, `@eyeline` and `@all` work in animations, sequences, batch and HTTP commands, listed in sweep order.
- **Brightness limits.** A maximum and minimum brightness per light, with defaults in Global Preferences, applied to presets, HTTP commands, animations, effects and sequences in the Bluetooth write path. The manual sliders are exempt. A Locked light ignores sequences and effects and keeps its manual or preset state.
- **Offline tests** in `tests/`: a fake-Bluetooth harness, a comparison of every existing URL type against v1.3.0, behaviour tests for the features above, an offscreen GUI test and the pre-release static checks.

### Changed
- Animations now play from a fixed start time instead of a chain of sleeps, so they no longer drift. Their timing rules are unchanged (holds still step in 50 ms ticks and fades in whole steps of the update rate), and the frames each light receives for existing URLs match v1.3.0 exactly. Inside sequences, clips use exact timing.
- While a sequence or effect is driving a light, slider moves, presets and mode commands for that light become what it returns to afterwards instead of interrupting the show. Lights the show isn't using, and Locked lights, change immediately. Sequences only stop when told to.
- During a sequence, the background check still relinks lights that drop out (it was skipped during animations); only the power and channel reads are skipped.
- **Light models live in `light_models.toml`.** Colour ranges, CCT-only models, the Bluetooth name prefixes a scan looks for, the TL60 name correction and lights that skip the status poll are now data rather than code, so adding a model is a one-line edit. Adapted from [Lumiere](https://github.com/lugoues/lumiere).
- **Status polling keeps one notification subscription per light** instead of opening and closing two every few seconds, and each light's replies are kept separately so two lights answering at once can't mix them up. Adapted from Lumiere.

### Fixed
- **POST `/NeewerLux/batch` rarely reached the lights.** The handler cleared the queued send before the worker picked it up.
- **A command that stopped an animation could leave the other lights on the animation's last frame.** With "Revert on finish" on, sending a mode or preset command while an animation played logged the revert, but the new command overwrote it before it was sent. The revert now completes.
- POST `/NeewerLux/animate` with `play` and no name raised an error instead of returning one.
- RGB CB60, RGB C80 and RGB176 A1 lights now get their correct 2500-10000K range. Model names containing a space never matched their own entry.
- Release zips now include the LICENSE file.
- Animation status in the GUI was set from a background thread; it is now updated on the GUI thread.

## v1.3.0 - 2026-10-02

### Added
- **More Neewer models are detected.** Lights advertising as `NW-`, `NWR` or `SL` are now picked up alongside `NEEWER`, and the TL60 RGB has its colour range built in. Contributed by @Lain2077.
- **Heartbeat logging is optional.** The "Background Thread Running" line logged every 30 seconds is now a Logging preference, off by default.

### Changed
- **Upgrading keeps your presets.** The shipped presets are now a template, `light_prefs/customLights.prefs.default`, copied into place on first run and never over an existing file. Release zips no longer contain a preset file, so extracting a new release over an install leaves your presets alone. Resetting every preset is no longer undone on the next launch, and a read-only install folder falls back to reading the template. Contributed by @lugoues.
- **Reproducible builds.** Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`, and the release build fails if the two disagree. PySide6 is optional, so the headless modes install without Qt. Python 3.11 or newer is required. Contributed by @lugoues.
- The repository no longer tracks per-machine files (Visual Studio state, window position, personal presets). Contributed by @lugoues.
- Licensed MIT, matching upstream, with a LICENSE file in the repository.
- Em-dashes and arrows removed from interface and log text, and several comments that described the wrong line or a removed feature corrected.

### Fixed
- The README's source install instructions pointed at a `requirements.txt` that didn't exist.
- `NeewerLux-HTTP.bat` now says 8080 is only the default port.

## v1.2.0 - 2026-07-24

### Restored
v1.0.4 was packaged from an older copy of the code and silently dropped the following v1.0.3 features. They are back.
- **Mode-aware hotkeys.** Brightness and slider shortcuts act on each selected light according to its own mode, instead of only driving the sliders on the visible tab. One brightness nudge reaches CCT, HSI and Scene lights together; adjustments that don't apply to a light's mode are skipped. Respects Live Preview.
- **Configurable HTTP port** in Global Preferences (1024 to 65535, default 8080). Restart the server to apply.
- **Hotkey fields** no longer show Qt's built-in clear button as an empty square.

### Changed
- Both themes are generated from one stylesheet template and a set of colour tokens, replacing two hand-maintained copies. The palette went from 71 colours to 45, and corner radii follow a consistent scale on the desktop and the dashboard.
- The log and the JSON editor share one monospace font, with fallbacks for macOS and Linux.
- The Info tab is rewritten in plain sentences. The dashboard's About section, which duplicated it, now points to it instead.
- Decorative emoji removed from dashboard headings and buttons that already had text labels.

### Fixed
- The log had no focus outline, and the horizontal scrollbar had no hover state.
- Code cleanup: redundant guard clauses, an unused function, and a stale version comment that contradicted the real version.

## v1.1.0 - 2026-07-11

### Fixed
- **Idle CPU creep.** Left running for hours, CPU use climbed from near zero to 2-3% and reset on restart. The Log tab kept every line ever written, and each new line cost more as it grew. It now keeps the last 2,000 lines.

## v1.0.9 - 2026-06-11

### Fixed
- **Chained animations now revert.** Starting an animation while another was playing could leave the lights on the last frame instead of returning to how they were before the first animation. A timing race between the old and new animation threads, missed by the v1.0.4 and v1.0.6 attempts, is fixed.

## v1.0.8 - 2026-04-30

### Added
- **WebUI button** in the toolbar and tray menu, enabled while the HTTP server is running.

## v1.0.7 - 2026-04-30

### Changed
- The version number is defined once and used everywhere: title bar, Info tab, tray tooltip, dashboard, and console banner. It had been written out separately in 13 places.
- Global Preferences are grouped into sections: Startup and Connection, Control and Presets, Light Behaviour, HTTP Server, Window and Display, Logging, Filtering, and Keyboard Shortcuts.

## v1.0.6 - 2026-04-19

### Fixed
- Second attempt at the chained-animation revert. Incomplete; see v1.0.9.

## v1.0.5 - 2026-04-13

Version number correction for v1.0.4; no code changes.

## v1.0.4 - 2026-04-13

### Fixed
- First attempt at making a chain of animations revert to the state before the first one. Incomplete; see v1.0.9.

### Regressed
- This release was built from a copy of the code that predated v1.0.3, so mode-aware hotkeys and the configurable HTTP port were lost until v1.2.0.

## v1.0.3 - 2026-03-27

### Added
- Mode-aware hotkeys and a configurable HTTP port. Both were lost in v1.0.4 and restored in v1.2.0.

## v1.0.2 - 2026-03-22

### Added
- **Loop control over HTTP GET.** The `animate` value accepts `Name|speed|rate|brightness|loop|maxLoops|revert`, all optional after the name, so `?animate=Halloween|1.0|10|50|true|2|true` plays twice at half brightness and then reverts. Loop and revert were previously POST-only, which a Stream Deck can't send.

## v1.0.1 - 2026-03-22

Tagged on the same commit as v1.0.0, so both include these fixes.

### Fixed
- Animation names in HTTP requests are matched without regard to case. The request parser lowercases everything, so names with capitals never matched.
- The Windows executable's first connection attempt fails while Bluetooth initialises. A silent warm-up attempt now absorbs that failure, so the first thing you see is a successful connection rather than an error.

## v1.0.0 - 2026-03-22

First public release, with a Windows executable.

### Presets
- **Preset Editor.** Edit a preset as a table of entries, each targeting all lights or one light, with its own mode and values. Copy and paste settings between entries.
- Duplicate presets from the right-click menu.
- Eight presets ship by default: Warm Studio, Daylight, Cool White, Candlelight, Red Alert, Blue Mood, Purple Haze and Green Screen.

### Animations
- 101 built-in animations, up from 22, grouped by category in the list: emergency, performance, holidays, studio, multi-light utility and ambient.
- **Identify Lights** blinks each light a number of times matching its ID, to tell them apart.
- **Animation editor:** a "Show light" filter for multi-light animations, gradient sliders in place of number boxes, copy and paste between keyframes, and a named scene picker instead of scene numbers.

### Colour temperature
- **Global CCT range** in Global Preferences (2700K to 8500K, default 3200K to 5600K), used by the CCT tab and both editors. Per-light ranges in Light Preferences take precedence.
- Every write to a light is checked against its range. Depending on the "incompatible command" setting, out-of-range values are clamped to the nearest limit or the command is skipped.
- Colour animations on CCT-only lights map hue across the configured range rather than a fixed one.

### Interface
- Gradient sliders shared by the main window and both editors.
- Number boxes with separate plus and minus buttons, fixing overlapping arrows at 150% display scaling and above.
- A visible Select All button on the light table, and dropdown arrows that render in both themes.
- **Update checker** in the Info tab and the dashboard, using GitHub Releases.
- Info tab links open in the browser.
- Log tab with clear and save, written to file in batches, scrolling only when you're already at the bottom.
- Updates from the background thread reach the window through Qt signals, fixing occasional missed updates.

### Build and distribution
- Windows executable built with PyInstaller by GitHub Actions on each version tag, published as a draft release.
- The executable runs without a console window. The `.bat` launchers remain for running from source.
- `light_prefs` ships beside the executable and stays editable.

### Naming and compatibility
- Renamed from NeewerLite-Python to NeewerLux throughout.
- PySide6 and PySide2 both supported.
- Fixed crashes on some PySide6 versions, and output errors when launched with `pythonw.exe`.

---

## v0.12d-PJ5 - 2026-03-04

- **Dark and light themes,** switched from the toolbar.
- **System tray.** Closing the window minimises to the tray; the tray menu shows the window, toggles the HTTP server and console, and quits.
- **HTTP server toggle** in the toolbar, no restart needed.
- **Web dashboard** at `http://localhost:8080/` with the light table, sliders, animations, a command log, and an API reference.
- **`list_json`** returns light status, animations and playback state as JSON.
- **Visual animation editor** with a keyframe table, live colour preview, and a synced JSON tab.

## v0.12d-PJ4 - 2026-03-04

- **Light names and preferred IDs** in Light Preferences. The table orders lights by ID, and names work in animations and HTTP commands.
- **Parallel writes** update every light at once during animations.
- Live animation values shown in the light table.
- Six ambient animations: Campfire, Candlelight, Ocean Waves, Thunderstorm, Northern Lights, Lava Lamp.

## v0.12d-PJ3 - 2026-03-03

- Smoother animation playback: no double waiting, throttled table updates, and dropped frames are logged.
- Brightness scaling for animation playback (5 to 100%).
- Nine animations: Concert Sweep, Bass Drop, Neon Nights, Stage Wash, Fire Flicker, Sunset Fade, DJ Pulse, Blackout Flash, Retrowave.
- Fixed the HTTP GET animate syntax and a Bleak deprecation.

## v0.12d-PJ2 - 2026-03-02

- **Animation engine:** keyframes with hold and fade times, short-way hue fades, seamless looping, and adjustable update rate.
- Seven animations, six templates, a JSON editor, and HTTP control.

## v0.12d-PJ1 - 2026-03-01

- Paged presets with your own names.
- PySide6, with PySide2 as a fallback.
- Lights relink after the computer wakes, HTTP batch commands, and cleanup of a stale instance lock.
