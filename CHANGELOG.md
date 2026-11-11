# NeewerLux changelog

Changes relative to upstream [NeewerLite-Python v0.12d](https://github.com/taburineagle/NeewerLite-Python).

## v1.3.3 - 2026-11-11

### Added
- **Flash guard, on by default.** Every light is kept to at most 3 flashes a second, the WCAG limit for photosensitive seizures: changes are spaced evenly, so a fast strobe plays as a slower, steady one (not three quick flashes and a pause), and a held-back final value is sent as soon as it's allowed. It counts big brightness changes and changes to and from saturated red, applies to animations, sequences, effects, presets and HTTP commands (only the desktop sliders are exempt), and leaves a little margin for Bluetooth timing. In Global Preferences and the web dashboard's Settings; turning it off asks first. `status_json` reports it and how many changes it held back, and sequence renders report each light's flash rate (the timeline editors warn when a sequence goes over). The light's built-in scenes run inside the light and can't be limited.
- **Light positions: depth and height, picked on a grid.** Light Preferences (desktop and web dashboard) replaces the Side list with a 3 x 3 grid seen from your seat facing the camera (your left to right; front at the top, beside you, back at the bottom) and a low, middle or high height, with the other lights shown in their cells. New targets `@front`, `@beside`, `@back`, `@low`, `@middle` and `@high` combine with roles and sides (`@back.left.high`, `@rim.high`). Sweep order on Auto now follows position (left to right, then front to back, then low to high) instead of ID. Each light can also say which way it points (at you by default, or one of eight directions), and Global Preferences records where the main camera is. `set_light`, `list_json`, `status_json`, the settings API and sequence renders carry `depth`, `height` and `aim`; the light's file gains these fields only when they're set.
- **Stage views: Plan (the default), Height and Strip**, in the Stage window, the web Stage and both timeline editors' previews. Plan puts each light in its place on the same grid, with you drawn from above in the middle, the camera where you put it, the light's height as one to three bars and a faint beam the way it points. Height uses the same columns with high, middle and low rows. The desktop window remembers its view, size and place, and the first time sizes itself to your lights.
- **Smooth transitions.** Global Preferences has **Fade in** (default 0: when a preset is recalled, or an animation or sequence takes lights over, including one animation replacing another) and **Fade back** (default 0.5 s: when an effect ends and the sequence takes back over, a sequence ends, stops or reverts on pause, or an animation stops). Each preset (`fade_ms`, in the preset editors), animation (`fade_in_ms` and `handback_fade_ms`, in the animation editors) and sequence (the same two, in the timeline editors' settings) can set its own, which wins over the global; `animate=` (two new trailing fields) and the animation and sequence play requests can override both for one play. The desktop sliders and manual light commands stay instant, and a manual command during a fade lands at once. Brightness stays continuous across mode changes: HSI to CCT fades the saturation to white first, CCT to HSI starts white and brings the colour in, and scenes fade their brightness before switching. A sequence ending on a preset fades to that preset. Fades only ever smooth the change into and out of an item, never what happens inside it: an animation or sequence is held on its first frame while it fades in and then runs from its start, so its keyframes and cues play exactly as written (hard cuts stay hard cuts); a light a running sequence picks up or drops part-way through follows its own cues; and restarting the animation that is already playing cuts.
- **Gentler flashes for eye-line lights** (Global Preferences, off by default): lights marked "In my eye line" can be held to at most 1 flash a second, or one change every 2 seconds, even with the flash guard off.
- **Play marker on renders.** While the rendered sequence plays, a line shows where it is; clicking the strip seeks there. Desktop and web dashboard.
- **Sequences tab.** Sequences move off the Animations tab to a tab of their own, with the list, transport, Render, Reload, the editor buttons and the selected sequence's details. Clearing the light selection no longer moves you off the Animations or Global Preferences tab (it switched to the disabled CCT tab), and the Sequences tab stays put too.
- **Starter sequences:** Intro Build, Outro Wind-down, Raid Welcome, Countdown and Song Skeleton (sections at 120 BPM), all aimed at roles. **+New**, on the desktop and the web dashboard, offers a blank sequence or a copy of a starter.
- **Timeline editor for sequences**, on the desktop (+New and Edit under the Sequences list) and in the web dashboard. One track per light in sweep order; cues sit on every light they drive and move as one. Double-click a track to add a cue, drag to move, drag the right edge for the length and the top notch for the fade, Ctrl or Shift for several. Snap to a time grid or, with a tempo, to beats, half beats or bars (the tempo is saved in the file as `tempo` and playback ignores it). A properties panel for the selected cue (start, lights, colour or clip, fade, length, label), sequence settings (frame rate, end, pause and interrupt behaviour, artist, song, description), undo and redo, copy, paste and duplicate, check, save and save as (saving under a new name renames). A band under each track shows what the light will really do. Play previews on screen in a Stage view; **Send to lights** plays the edit through the real lights from the playhead and follows edits while playing. Cues for lights that aren't connected show on a "No matching light" track. Duplicate and Delete join +New and Edit under the Sequences list.
- **Web dashboard editors to match the desktop.** Presets get the desktop's right-click menu (recall, save the current lights here, edit, rename, move left or right, duplicate, delete) and preset editor. Animations get New, Edit, Duplicate and Delete with the same keyframe editor and a JSON view, plus Export (download a file), Import (from a file) and Reload, and the Parallel play option.
- **Editing over HTTP:** `POST /NeewerLux/presets` (list, get, save, rename, move, duplicate, delete, add, snapshot, recall), animation `get`, `save` (with renaming), `duplicate`, `delete` and `reload`, and sequence `get`, `delete`, `editor` and renaming on `save`. All documented in `docs/HTTP_API.md`.
- **`docs/HTTP_API.md`**, the full HTTP contract: every endpoint, parameter, unit and response shape, how lights are named, and how commands are queued.
- **Structured light state in `list_json`** (API version 2): `power`, `channel`, `setting` (the last command, colour temperature in Kelvin), `output` (what the light is actually showing, with an approximate colour), `cctRange`, `cctOnly`, role, side, Locked and the driving layer per light, plus the sequence list. The display string `status` stays for older clients.
- **`apiVersion`** (now 2) and `version` in `list_json`, `status_json` and the settings API, so controllers can tell what a NeewerLux supports.

### Changed
- **The Ambient role is now Background**, which is what it means here: the light on the wall or set behind you. Targets are `@background`; the shipped sequences use it. A light saved as ambient loads as Background (lights without a role already counted as it), and Rim is labelled "Rim / back". Your own animations and sequences that target `@ambient` need changing to `@background`. Role tooltips (desktop and web) say what each role is for, including Practical, a light that is visible in shot.
- **Animations play with exact timing.** v1.3.0 rounded every hold down to a multiple of 50 ms (at least 50 ms), so a 130 ms hold played as 100 ms and speeds between about 2.2 and 4.4 times gave Strobe the same 50 ms holds. Holds and fades now last as long as the file says, divided by the speed; fades still move in steps at the animation's rate.
- **Apply Settings only shows on the CCT, HSI and Scene tabs** (with live preview off), since it only sends those sliders; on other tabs it looked like it applied the tab.
- **Save Global Preferences is highlighted while there are unsaved changes**, on the desktop and in the web dashboard, so a setting that hasn't been saved (the flash guard, say) is obvious.
- **Editors open taller** (most of the screen height) on the desktop and in the web dashboard, so the light list and keyframes show without resizing; the desktop editors still remember the size you leave them at, but no smaller than the new minimum.
- **Preferences reorganised.** Light Preferences is two columns: the light itself (name, ID, colour temperature range, CCT-only, brightness limits, Locked, eye line) and its part in shows (role, sweep order, the position grid with height and aim). Global Preferences is split into General, Lights and shows, Simulation and HTTP, and Shortcuts, with Reset and Save always in view. The web dashboard's Settings follow the same grouping and have a Settings button at the top of the page.

### Fixed
- **Spin box arrows can be clicked again.** On Windows the text area of a styled spin box covers its up arrow, so many settings (Light Preferences, Global Preferences, the editors) could only go down. Every spin box now has - and + buttons beside it instead of Qt's arrows, and a GUI test fails if any spin box in the app uses Qt's own arrows or has no room to show its value (Qt 6.12 also blanks the value of a box without arrows).
- **`"SCENE"` works in animation keyframes.** Built-in scenes had to be written `"ANM"`; `"SCENE"`, the name used elsewhere, saved and then silently never played. Both now work, and a keyframe with an unknown mode or none is refused when saved (HTTP, the web editor and the desktop JSON editor) and reported when loaded.
- **Saving Light Preferences keeps you there.** It reloaded the light table, which cleared the selection and switched to the Animations tab; the light now stays selected on Light Preferences.
- The web dashboard labelled the eye-line setting "At eye level"; it means lights in your eye line, as on the desktop.
- **JSON batch colour temperatures in Kelvin.** `"temp": 5600` was clamped to 85 and set 8500K; values over 100 are now read as Kelvin, as the GET batch string already did.
- **Light commands are no longer turned away when NeewerLux is busy.** POST batch answered "Server is busy" whenever another command was in progress, and GET light commands waited up to 5 seconds and were then dropped. Light commands from GET, GET batch, POST batch and the brightness hotkeys now go into a per-light queue: a newer command for a waiting light replaces the older one, and each light is written once with its latest value. Rapid Stream Deck presses and dials no longer lose commands, and never cause more writes than were requested.
- **POST batch stops an override animation**, as GET light commands always have; before, the animation's next frame overwrote the batch. Sequences and effects keep running, and the batch becomes what their lights return to.
- Read-only requests the web dashboard repeats (sequence and animation `list` and `status`, settings `get`, and the editor's renders) no longer write a log line each time, and the dashboard takes the sequence list from the light data it already polls instead of asking separately every 5 seconds.
- **Light commands and sequence starts no longer wait behind status polling.** The worker reads each light's power and channel every few seconds, one light at a time; with slow replies (real lights, or Windows' 15.6 ms timer) a round can take a second or more, and queued commands waited for all of it. A queued command or a starting show now cuts the round short (the lights keep their last reported status until the next round). With 60 ms replies, the worst wait fell from about 1 s to under 0.1 s for a command and about 0.12 s for a sequence's first cue.
- **Shipped animations slowed to stay under 3 flashes a second** at their default speed: Strobe, Metal Mosh, Panic, Drum Solo, DJ Pulse, Fire Truck, Ambulance, Alternating Flash and Fire Flicker (timings stretched by 1.25 to 3 times; the look is otherwise unchanged). Strobe's description says so.
- Saving a sequence removes any other file holding a sequence of the same name, so a reload no longer brings back an old version.
- HTTP preset and animation changes refreshed the desktop window from the HTTP thread; they now go through Qt signals. Preset changes over HTTP are also saved when the app runs without its window.
- Editing a snapshot preset in the desktop preset editor turned entries for lights that were off into on; they now stay off.

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
