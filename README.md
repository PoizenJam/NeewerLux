# NeewerLux

Control Neewer Bluetooth LED lights from your computer, with presets, keyframe animations, and an HTTP server for driving it all from a browser or a Stream Deck.

NeewerLux is a fork of [NeewerLite-Python](https://github.com/taburineagle/NeewerLite-Python) (v0.12d) by Zach Glenwright ([@taburineagle](https://github.com/taburineagle)), which grew out of [NeewerLite](https://github.com/keefo/NeewerLite) by Xu Lian ([@keefo](https://github.com/keefo)).

NeewerLux is not affiliated with or endorsed by Neewer.

## Supported lights

Lights are detected by their Bluetooth name. Anything advertising as `NEEWER`, `NW-`, `NWR` or `SL` is picked up, and these models have known colour temperature ranges built in:

GL1, NL140, SNL1320, SNL1920, SNL480, SNL530, SNL660, SNL960, SRP16, SRP18, WRP18, ZRP16, BH30S, CB60, CL124, RGB C80, RGB CB60, RGB1000, RGB1200, RGB140, RGB168, RGB176, RGB176 A1, RGB512, RGB800, RGB1, RGB18, RGB190, RGB450, RGB480, RGB530, RGB530 PRO, RGB650, RGB660, RGB660 PRO, RGB960, RGB-P200, RGB-P280, SL-70, SL-80, SL-90, TL60 RGB, ZK-RY, Apollo.

A model that isn't on the list still connects; it just gets a default colour range, which you can override per light in Light Preferences.

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

## Remote control

Turn on the HTTP server from the toolbar, or have it start with the app in Global Preferences. The dashboard is at `http://localhost:8080/` (the port is configurable), and the toolbar's WebUI button opens it.

Every action is also a plain URL, which is how a Stream Deck or a script drives NeewerLux:

```
http://localhost:8080/NeewerLux/doAction?light=1&mode=CCT&temp=5600&bri=80
http://localhost:8080/NeewerLux/doAction?use_preset=3
http://localhost:8080/NeewerLux/doAction?animate=Halloween|1.0|10|50|true|2|true
http://localhost:8080/NeewerLux/doAction?stop_animate
```

The `animate` value is `Name|speed|rate|brightness|loop|maxLoops|revert`. Only the name is required. The example plays Halloween twice at half brightness, then puts the lights back how they were.

For richer control, POST JSON to `/NeewerLux/batch` (several lights in one request) or `/NeewerLux/animate`:

```json
{ "action": "play", "name": "Concert Sweep", "speed": 1.0, "loop": true, "maxLoops": 3, "revert": true }
```

The Info tab and the dashboard both carry the full command reference.

**Security:** the HTTP server has no authentication. Access is limited only by the IP allowlist in Global Preferences, which by default admits this machine and common private network ranges. Don't expose the port to the internet.

## Other details

- Closing the window minimises to the system tray by default; quit from the tray menu.
- Dark and light themes.
- Lights are relinked automatically after the computer wakes from sleep.
- Only one copy runs at a time.
- The Log tab shows activity and can save it to a file.
- The Windows executable has no console window. When running from source, Global Preferences can hide the console on launch.

## License

MIT. See [LICENSE](LICENSE).
