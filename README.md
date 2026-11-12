# NeewerLux

Control Neewer Bluetooth LED lights from your computer, with presets, keyframe animations, and an HTTP server for driving it all from a browser or a Stream Deck.

NeewerLux is a fork of [NeewerLite-Python](https://github.com/taburineagle/NeewerLite-Python) (v0.12d) by Zach Glenwright ([@taburineagle](https://github.com/taburineagle)), which grew out of [NeewerLite](https://github.com/keefo/NeewerLite) by Xu Lian ([@keefo](https://github.com/keefo)).

NeewerLux is not affiliated with or endorsed by Neewer.

## Supported lights

Lights are detected by their Bluetooth name. Anything advertising as `NEEWER`, `NW-`, `NWR` or `SL` is picked up, and these models have known colour temperature ranges built in:

GL1, NL140, SNL1320, SNL1920, SNL480, SNL530, SNL660, SNL960, SRP16, SRP18, WRP18, ZRP16, BH30S, CB60, CL124, RGB C80, RGB CB60, RGB1000, RGB1200, RGB140, RGB168, RGB176, RGB176 A1, RGB512, RGB800, RGB1, RGB18, RGB190, RGB450, RGB480, RGB530, RGB530 PRO, RGB650, RGB660, RGB660 PRO, RGB960, RGB-P200, RGB-P280, SL-70, SL-80, SL-90, TL60 RGB, ZK-RY, Apollo.

A model that isn't on the list still connects; it just gets a default colour range, which you can override per light in Light Preferences. The model list itself is `light_models.toml`, if you want to add a model or correct a range.

## Installation

### Windows

1. Download `NeewerLux-<version>-Windows.zip` from [Releases](https://github.com/poizenjam/NeewerLux/releases).
2. Extract it anywhere.
3. Run `NeewerLux.exe`.

Your presets, animations and per-light settings live in the `light_prefs` folder next to the executable. They are plain text and safe to edit by hand or copy between installs. Release zips don't include a preset file, so extracting a newer release over an existing install keeps your presets.

### From source

Requires Python 3.11 or newer. Dependency versions are pinned in `uv.lock`.

With [uv](https://docs.astral.sh/uv/):

```
uv sync --locked
uv run NeewerLux.py
```

With pip:

```
pip install "PySide6>=6.7,<7" "bleak>=0.22,<4"
python NeewerLux.py
```

The command-line and HTTP-only modes (`--cli`, `--list`, `--http`) don't need Qt. To install without it:

```
uv sync --locked --no-default-groups
uv run --no-default-groups NeewerLux.py --http
```

`--no-default-groups` is needed on both commands, because `uv run` re-syncs first and would otherwise reinstall PySide6.

Sound modes need the optional audio packages (numpy, soundcard, soundfile); the Windows download includes them. From source: `uv sync --locked --group audio` (and `--group audio` on `uv run`), or `pip install numpy soundcard soundfile`. Without them sound modes are hidden and everything else works as before.

## Using it

### Controlling lights

Scan, connect, then use the CCT, HSI or Scene tab. In Light Preferences you can give each light a name and a fixed number. Named lights keep their place in the table, and the name works anywhere a light is targeted: animations, presets and HTTP commands.

Keyboard shortcuts for brightness and the sliders act on each selected light according to its own mode, so one brightness nudge reaches CCT, HSI and Scene lights together. All shortcuts are configurable in Global Preferences.

### Colour temperature limits

Global Preferences sets the CCT range your lights should stay within (2700K to 8500K, default 3200K to 5600K), and Light Preferences can override it per light. When a command falls outside a light's range, NeewerLux either clamps it to the nearest value the light can reach or skips it, whichever you choose. The same setting decides what happens when an HSI or Scene command reaches a CCT-only light.

### Presets

The preset buttons sit in a grid under the light table. Right-click one to save the current setup, edit, rename, reorder, duplicate or delete it; left-click recalls it; middle-click renames. A preset can set every light the same way or give each light its own settings, and the Preset Editor lays that out as a table.

Eight presets ship by default: Warm Studio, Daylight, Cool White, Candlelight, Red Alert, Blue Mood, Purple Haze and Green Screen.

### Animations

An animation is a list of keyframes. Each keyframe holds a colour for some time, fades from the previous one over some time, and can set different lights to different colours in HSI, CCT or Scene mode. Hue fades take the short way round the colour wheel. CCT-only lights follow colour animations by mapping hue to the nearest colour temperature.

101 animations ship with the app:

| Category | Examples |
|---|---|
| Emergency | Police Flash, Ambulance, Fire Truck, Hazard |
| Performance | Guitar Solo, Drum Solo, Metal Mosh, Encore, Power Ballad, Spotlight, Rock Anthem, Concert Build |
| Holidays | Christmas, Halloween, Valentines, Easter, Hanukkah, New Years Eve, St Patricks, Fourth of July |
| Studio | Interview, Warm Studio, Focus, Reading Light, Product Photo, Film Noir, Key Fill Rim, Dawn Simulator, Magic Hour, Golden Hour |
| Multi-light | Color Chase, Ping Pong, Ripple, Alternating Flash, Gradient Sweep, Warm Cascade, Identify Lights |
| Ambient | Neon Nights, Retrowave, Stage Wash, Campfire, Candlelight, Sunset Fade, Ocean Waves, Northern Lights, Lava Lamp, Breathe, and more |

Playback settings: speed (0.25x to 4x), update rate during fades (1 to 30 per second, default 5), brightness scaling (applied at playback, the file is unchanged), looping, and whether to return the lights to their previous state when the animation ends. With parallel writes on, every light is updated at once rather than one after another, which keeps fades smooth with several lights; turn it off if your Bluetooth adapter struggles.

New animations can start from one of six templates, or be built in the animation editor, which works on keyframes as a table with a live colour preview and a JSON tab for direct editing. Animation files are JSON in `light_prefs/animations` and target lights by name, number, MAC address, or `*` for all of them.

### Light roles and brightness limits

Light Preferences can give each light a role (key, fill, rim, background or practical), a position, a sweep order and an eye-line flag. The position is picked on a grid seen from your seat facing the camera: side (your left, centre, your right), depth (front, between you and the camera; beside you; or back, behind you), height (low, middle or high) and which way it points (at you by default). Where the main camera is goes in Global Preferences, Lights and shows; positions stay relative to you either way. Animations, sequences and HTTP commands can then target `@rim`, `@left`, `@back`, `@high`, combinations such as `@rim.left` or `@back.left.high`, `@eyeline` or `@all` instead of light numbers, so a show keeps working when lights are renumbered. Lights without a role count as background. Rim is the light behind you that outlines you (also called a back or hair light), background lights the wall or set behind you, and a practical is a light that is visible in shot, such as a tube on a shelf. With sweep order on Auto, sweeps run left to right, then front to back, then low to high.

Each light can also have a maximum and minimum brightness, and Global Preferences sets the defaults. The limits apply to presets, HTTP commands, animations, effects and sequences; only the manual sliders are exempt, so you can still go bright on purpose. A light marked Locked ignores sequences and effects entirely and stays on whatever you set by hand or by preset, which is useful for a key light.

### Sequences

A sequence is a timed light show for a song: cues that start at set times and either set a colour (with a fade) or play one of the animations, stretched or looped to fit, on some of the lights. Sequences are JSON files in `light_prefs/sequences` and play from the Sequences tab or over HTTP. Timing comes from a fixed start time rather than from a chain of waits, so a five-minute sequence stays in step with the song; the position can also be set from outside, for syncing to a game or song timer.

When a sequence ends, the lights go back to how they were before it started (usually a preset), unless the sequence says to hold its last frame or recall a particular preset. Pausing puts the lights back the same way, and resuming picks the show up exactly where it stopped.

The format is documented in full in [docs/SEQUENCE_FORMAT.md](docs/SEQUENCE_FORMAT.md), written so that a program or an AI model can generate sequences per song.

### The timeline editor

Five starter sequences ship alongside the example: an intro build, an outro wind-down, a raid welcome, a ten-second countdown and a song skeleton laid out in sections at 120 BPM. They aim at roles (`@key`, `@fill`, `@rim`, `@background`, `@practical`), so they work on any rig with roles set, and **+New** offers them as starting points.

**+New** or **Edit** on the Sequences tab opens the timeline editor: one track per light, in sweep order, with each cue drawn on the tracks of the lights it drives (a cue aimed at several lights shows on each, with a dashed outline, and moves as one). A thin band under each track shows what that light will really do, with its limits and the CCT-only conversion applied.

Double-click a track to add a cue there (it starts from the colour the light already has). Drag a cue to move it, its right edge to change its length, and the notch at its top to change its fade; Ctrl or Shift selects several. Snap to a time grid or, with a tempo set, to beats, half beats or bars. The panel on the right edits the selected cue: start, which lights, colour or clip, fade, length and label. Undo and redo, copy and paste at the playhead, and duplicate all have the usual shortcuts, and Space plays.

Play previews the edit on screen, in a Stage view under the timeline, without touching the lights. Tick **Send to lights** to play it through the real lights from the playhead; edits made while it plays are sent within a moment. Check validates the sequence, Save writes it (saving under a new name renames it), and Settings holds the frame rate, what happens at the end, while paused and during effects, and the artist, song and description. Cues whose lights aren't connected show on a "No matching light" track so they don't vanish. The web dashboard has the same editor.

### Sound modes

A sound mode makes lights follow whatever is playing, live: game audio, music, a mix. By default NeewerLux listens to what your computer's default output plays (no cable or virtual device needed); any other output or an input, such as an audio interface, can be picked instead. It measures loudness, bass, mids and treble, how bright the sound is and the beat, and the mode turns that into light on the lights it aims at, by role or position. Five come with it: **Pulse** (brightness follows the level), **Bands** (lows on the background, mids on the rim, highs on the fill), **Beat Chase** (steps through the lights on the beat), **Colour Drift** (colour follows how bright the sound is) and **Warm Glow** (white only, for colour-temperature lights). None of them touches the key light. Each has a sensitivity, a floor and ceiling brightness, smoothing and a palette (fixed colours, cycling, stepping on the beat or following the sound; palettes can be saved and reused), and they're JSON files in `light_prefs/sound_modes/` like animations, so you can make your own ([docs/SOUND_MODES.md](docs/SOUND_MODES.md)).

The **Sound** tab (and the dashboard's Sound card) picks what to listen to, the mode, and its sensitivity, range, floor, ceiling, smoothing, palette and lights, with live meters and the tempo; changes show on the lights at once and are saved when you choose. A mode can also go on chosen lights only, so different lights can follow different modes, and a snapshot preset can set lights following a mode. Sound plays on its own layer underneath sequences and effects: a song's sequence starting takes the lights it uses and hands them back with its Fade back when it ends, and stream effects play over it as they do over sequences. Recalling a preset or moving a slider on a light takes that light out of the sound layer (sound stops when no lights are left); switching a light off takes it out until it's switched on. Brightness limits, Locked lights, the CCT-only fallback and the flash guard all apply, and the modes keep themselves to 2 flashes a second, so they swell and step rather than strobe. Over HTTP: `sound=start|Pulse`, `sound=start|Colour Drift|1;3`, `sound=stop`, `POST /NeewerLux/sound`.

### Effects on top of a sequence

Animations can play on three layers above the sliders and presets. **Override** is the classic one-at-a-time slot that the GUI Play button, a Stream Deck button and any `animate` URL without a layer use. **Effect** is for things Streamer.bot triggers, such as redeems, bits, subs and raids: effects queue up behind each other or cut in, and a forever-looping effect stops after 30 seconds. **Show** holds the sequence. Each light follows the highest layer that is driving it, so an effect on the rim lights leaves the others on the sequence, and when the effect ends the rim lights rejoin the sequence in time with the song (with the effect's Fade back).

While a sequence or effect is driving a light, moving a slider or recalling a preset doesn't change that light straight away: the change becomes what the light returns to afterwards. Lights the sequence isn't using, and Locked lights, change immediately.

### Flash guard

Flashing light can trigger seizures in people with photosensitive epilepsy, in the room and on stream. The flash guard, on by default, keeps every light to at most 3 flashes a second, the WCAG limit: changes are spaced evenly (about a fifth of a second apart at most), so a fast strobe plays as a slower, steady one rather than bursts and pauses, and a value that was held back (the end of a strobe, the last position of a dial) is sent as soon as it's allowed. It counts big changes in brightness and changes to and from saturated red, and applies to animations, sequences, effects, presets and HTTP commands; only the desktop's sliders are exempt. Every shipped animation, sequence and preset stays under the limit at its default speed, and the timeline editor warns when a sequence would go over. It's in Global Preferences (and the web dashboard's Settings), and turning it off asks first.

The thresholds come from WCAG, which was written for screens; lights fill more of the view, so the guard lowers the risk without ruling it out. The light's built-in scenes (Police, Lightning, Paparazzi and so on) run inside the light and can't be limited.

### Simulated lights and the Stage window

Global Preferences can add a simulated rig of 1 to 4 lights (key, fill, rim, background), plus an optional CCT-only light, for trying sequences, effects, HTTP commands and Stream Deck buttons without hardware. Simulated lights take the same Bluetooth packets as real ones, answer status queries, and can be renamed, given roles and limits, and used alongside real lights. The setting takes effect at the next start; launching with `--simulate` (or `--simulate=2` and so on) does the same for one run, and `--simulate-faults` makes them drop the odd write and disconnect now and then, for testing reconnects.

The **Stage** button opens a window with one tile per light, in sweep order, showing roughly what each light is showing and which layer is driving it. Simulated lights show what they actually received; real lights show what was last sent to them, so a CCT-only light asked for a colour shows the white it was converted to. The light table also shows a colour swatch beside each light. Colours on screen are approximations of the real output, and dim lights are drawn brighter than a literal scale would (a panel at 5% is still obviously lit in a room); only 0% or off shows as dark. Tiles size themselves to the system font and display scaling; hover a tile for a name too long to fit. The Stage remembers its view, size and place; the first time it opens in **Plan** view, sized to your lights: the lights where they stand, on the same grid as Light Preferences (your left on the left, front at the top), with you in the middle, the camera where you put it, each light's height as one to three bars and a faint beam the way it points. **Height** view uses the same columns with high, middle and low rows; **Strip** is the older single row in sweep order. The web dashboard's Stage and both timeline editors' previews have the same views.

**Transitions.** Two fades in Global Preferences, Lights and shows (0 cuts):
- **Fade in** (default 0): when a preset is recalled, or an animation or sequence takes lights over, including one animation replacing another.
- **Fade back** (default 0.5 s): when an effect ends and the sequence takes back over, a sequence ends or reverts, or an animation stops.

Each preset (Fade in, in the preset editor), animation (Fade in and Fade back in the animation editor, or `fade_in_ms` and `handback_fade_ms` in the file) and sequence (the timeline editor's Settings) can set its own, which wins over the global setting; `animate=` and the play requests can override both for one play. The desktop sliders and manual light commands stay instant, and a manual command during a fade lands at once. Brightness stays continuous across a mode change: a colour fades towards white before a light switches to CCT, and a scene's brightness moves before it hands over. Fades only smooth the change into and out of an item, never what happens inside it: an animation or sequence holds its first frame while it fades in, then runs from the start exactly as written, and restarting the animation that is already playing cuts.

**Eye-line lights.** Lights marked "In my eye line" can be given gentler flashes in Global Preferences (at most one a second, or one change every two seconds), whether or not the flash guard is on. It's off by default.

The **Render** button on the Sequences tab draws a whole sequence as a strip, one row per light with time running left to right, without playing it. While that sequence plays, a marker shows where it is, and clicking the strip jumps there (on the desktop and the web dashboard). It applies each light's brightness limits, Locked flag and CCT-only fallback, so it shows what the lights would really do.

## Remote control

Turn on the HTTP server from the toolbar, or have it start with the app in Global Preferences. The dashboard is at `http://localhost:8080/` (the port is configurable), and the toolbar's WebUI button opens it. The dashboard covers what the desktop window does: lights with colour swatches, roles and layers, manual control, presets (with the right-click menu: save the current lights, edit, rename, move, duplicate, delete), animations (play with the same options, plus new, edit, duplicate, delete, export to a file, import from a file and reload, with the same keyframe editor and a JSON view), sequences (play, pause, resume, seek by clicking the progress bar, stop, render, reload, and the timeline editor), a live Stage view, and Settings (the Settings button at the top) for each light's preferences and the show-related global preferences. Network access, keyboard shortcuts and startup options can only be changed in the desktop app.

Every action is also a plain URL, which is how a Stream Deck or a script drives NeewerLux:

```
http://localhost:8080/NeewerLux/doAction?light=1&mode=CCT&temp=5600&bri=80
http://localhost:8080/NeewerLux/doAction?use_preset=3
http://localhost:8080/NeewerLux/doAction?animate=Halloween|1.0|10|50|true|2|true
http://localhost:8080/NeewerLux/doAction?stop_animate
```

The `animate` value is `Name|speed|rate|brightness|loop|maxLoops|revert`. Only the name is required. The example plays Halloween twice at half brightness, then puts the lights back how they were.

Three more optional fields choose a layer: `Name|speed|rate|brightness|loop|maxLoops|revert|layer|queue|target`. Layer is `override` (the default), `effect` or `show`; queue is `queue` (the default) or `replace`; target narrows the animation to some lights, such as `@rim`. On the effect and show layers, `revert` applies to that request only.

```
http://localhost:8080/NeewerLux/doAction?animate=Strobe|1|10|100|true|5||effect||@rim
http://localhost:8080/NeewerLux/doAction?stop_layer=effect_all
http://localhost:8080/NeewerLux/doAction?sequence=play|Example%20-%20Four%20Light%20Demo
http://localhost:8080/NeewerLux/doAction?sequence=pause
http://localhost:8080/NeewerLux/doAction?status_json
```

For richer control, POST JSON to `/NeewerLux/batch` (several lights in one request), `/NeewerLux/animate`, `/NeewerLux/sequence`, `/NeewerLux/sound` (sound modes) or `/NeewerLux/settings` (`get`, `set_light`, `set_global`):

```json
{ "action": "play", "name": "Concert Sweep", "speed": 1.0, "loop": true, "maxLoops": 3, "revert": true }
{ "action": "play", "name": "Heartbeat", "layer": "effect", "mode": "queue", "target": "@rim" }
```

`{"action": "render", "name": "...", "format": "png"}` on `/NeewerLux/sequence` returns the render strip as an image, and `"format": "json"` (the default) returns each light's colour changes over time, which is what a script or an AI model generating sequences should check its work against. `GET /NeewerLux/doAction?status_json` includes each light's current colour.

[docs/HTTP_API.md](docs/HTTP_API.md) is the full contract for controllers and scripts: every endpoint, parameter, unit and response, including the structured light state in `list_json` (power, channel, current setting and output, colour temperature range) and an `apiVersion` field for feature detection. [docs/SEQUENCE_FORMAT.md](docs/SEQUENCE_FORMAT.md) lists every sequence command and layer option.

Light commands are never turned away as busy: if a light already has a command waiting, the newer one replaces it, so a Stream Deck dial can send as fast as it likes. JSON colour temperatures can be given in Kelvin (`"temp": 5600`) or hundreds of Kelvin (`56`).

The Info tab and the dashboard both carry a command reference.

**Security:** the HTTP server has no authentication. Access is limited only by the IP allowlist in Global Preferences, which by default admits this machine and common private network ranges. Don't expose the port to the internet.

## Other details

- Closing the window minimises to the system tray by default; quit from the tray menu.
- Dark and light themes.
- Lights are relinked automatically after the computer wakes from sleep.
- Only one copy runs at a time.
- The Log tab shows activity and can save it to a file.
- The Windows executable has no console window. When running from source, Global Preferences can hide the console on launch.
- `tests/` holds offline tests that run the real code against stand-in lights; each file's header says how to run it.

## License

MIT. See [LICENSE](LICENSE).
