# NeewerLux

A cross-platform Neewer LED light control app for streamers and content creators. Features a keyframe animation engine with 101 presets, multi-light preset editor, visual animation editor, WebUI dashboard, and BLE parallel writes.

Fork of [NeewerLite-Python](https://github.com/taburineagle/NeewerLite-Python) (v0.12d) by [@taburineagle](https://github.com/taburineagle), originally based on [NeewerLite](https://github.com/keefo/NeewerLite) by [@keefo](https://github.com/keefo) (Xu Lian).

**NeewerLux is not affiliated with or endorsed by Neewer.**

**Supported lights:** GL1, NL140, SNL1320, SNL1920, SNL480, SNL530, **SNL660**, SNL960, SRP16, SRP18, WRP18, ZRP16, BH30S, CB60, CL124, RGB C80, RGB CB60, RGB1000, RGB1200, RGB140, RGB168, RGB176 A1, RGB512, RGB800, SL-90, RGB1, **RGB176**, RGB18, RGB190, RGB450, **RGB480**, RGB530 PRO, RGB530, RGB650, **RGB660 PRO**, RGB660, RGB960, RGB-P200, RGB-P280, SL-70, **SL-80**, ZK-RY

---

## Installation

### Windows Executable (Recommended)
1. Download `NeewerLux-x.x.x-win64.zip` from the [Releases](https://github.com/poizenjam/NeewerLux/releases) page
2. Extract to any folder
3. Run `NeewerLux.exe`

Preset and animation files are in the `light_prefs/` folder alongside the executable and can be edited manually with any text editor.

### Running from Source
Requires Python 3.8+:
```
pip install -r requirements.txt
python NeewerLux.py
```

---

## Features

### Custom Animation System

A full keyframe-based animation engine that drives Neewer lights through timed color sequences with smooth interpolation. Animations are stored as JSON files in `light_prefs/animations/` and can target individual lights by MAC address, numeric ID, alias name, or all lights with the `"*"` wildcard.

Each keyframe specifies a hold time (how long to dwell on the color), a fade time (how long to transition from the previous keyframe), and per-light color parameters in HSI, CCT, or Scene modes. The engine handles shortest-path hue interpolation around the 360° color wheel so transitions between, say, red (0°) and magenta (300°) go the short way rather than sweeping through the entire spectrum.

**Playback controls:**
- **Speed** — multiplier applied to all timing values (0.25x to 4x)
- **Rate** — BLE updates per second during fades (1-30, default 5; with Parallel enabled, ~15 is achievable regardless of light count)
- **Brightness** — scales all brightness values at playback time without modifying the animation file (5-100%)
- **Loop** — continuous playback with seamless wraparound fading between last and first keyframe
- **Parallel writes** — sends BLE commands to all lights simultaneously using `asyncio.gather()` instead of sequentially, reducing per-frame time from ~50ms×N to ~50ms regardless of light count (toggle-able for legacy adapter compatibility)

**101 built-in animation presets** across categories:

| Category | Examples |
|----------|---------|
| Emergency | Police Flash, Ambulance, Fire Truck, Hazard |
| Rock Performance | Guitar Solo, Drum Solo, Metal Mosh, Encore, Power Ballad, Spotlight, Rock Anthem, Concert Build |
| Holidays | Christmas, Halloween, Valentine's, Easter, Hanukkah, New Year's Eve, St. Patrick's, Fourth of July |
| Practical/Studio | Interview, Warm Studio, Focus, Reading Light, Product Photo, Film Noir, Key Fill Rim, Dawn Simulator, Magic Hour, Golden Hour |
| Multi-Light Utility | Color Chase, Ping Pong, Ripple, Alternating Flash, Gradient Sweep, Warm Cascade, Identify Lights |
| Smooth/Ambient | Concert Sweep, Neon Nights, Retrowave, Stage Wash, Fire Flicker, Campfire, Candlelight, Sunset Fade, Ocean Waves, Northern Lights, Lava Lamp, Breathe, Color Wash, Color Cycle, Rainbow Gradient, Rainbow Chase, and many more |

Six template generators are available from the GUI for creating new animations. Animations can also be authored in the Visual Editor or JSON Editor.

### Animation Editor

A full visual editor for creating and editing animation keyframes:
- Color-coded keyframe table showing mode, parameters, hold/fade timing, and light count per frame
- **Light filter combo** — switch which light's parameters are displayed in the keyframe table for multi-light animations
- Per-light parameter editing with **+ Light** / **- Light** buttons within each keyframe
- **GradientSlider controls** — hue rainbow, saturation, brightness, and CCT sliders with visual gradient bars matching the main GUI, dynamic suffixes, endpoint labels, and value readouts that switch based on mode
- Scene dropdown for built-in animation modes
- Live color preview bar
- Copy/paste settings between keyframes
- Add, duplicate, delete, and reorder frames
- Synced JSON editor tab for power users
- Size persistence across sessions

### Preset System

Presets are displayed as an 8-column scrollable button grid with right-click context menu:
- **Save Current Settings** — capture current slider positions
- **Edit Preset** — opens the visual Preset Editor
- **Rename** — custom preset names (also via middle-click)
- **Move Left/Right** — reorder presets
- **Duplicate Preset** — deep-copy with "(copy)" suffix
- **Delete Preset**

Ships with 8 default presets: Warm Studio, Daylight, Cool White, Candlelight, Red Alert, Blue Mood, Purple Haze, Green Screen.

### Preset Editor

A visual editor for configuring preset settings, matching the animation editor's layout:
- Entry table showing target, mode, and parameter summary with color-coded mode cells
- Toolbar: Add Entry, Duplicate, Delete, Move Up/Down, Copy, Paste
- **GradientSlider controls** — same visual gradient bars as the main GUI and animation editor
- Scene dropdown with named scenes
- Per-light targeting with guardrails: "All Lights" disabled when multiple entries exist, duplicate targets prevented
- Copy/paste copies mode + values (not target), enabling quick setup of similar settings across lights
- Live color preview bar
- Size persistence across sessions

### Global CCT Range

Configurable minimum/maximum color temperature bounds in Global Preferences (2700K–8500K, default 3200K–5600K). Applies to the CCT tab, Preset Editor, and Animation Editor. Per-light CCT range overrides in Light Preferences take precedence for individual lights.

### CCT Clamping & Incompatibility Handling

Software-side enforcement of CCT temperature bounds on all BLE write paths:
- **Convert/Clamp** — out-of-range values clamped to the light's effective range
- **Ignore/Skip** — out-of-range commands silently dropped

Also handles HSI/Scene commands sent to CCT-only lights. Ensures consistent behavior across mixed light setups.

### Light Aliases (Preferred ID)

The **Light Preferences** tab includes a **Preferred ID** field (0-99) alongside the custom name:
- GUI table reorders so preferred-ID lights appear first, in ID order
- Animation keyframes can use names (e.g., `"Key"`, `"Fill"`) as light targets
- HTTP batch commands work with names: `?batch=Key:HSI:0:100:50;Fill:CCT:56:80`
- Preferred IDs resolve consistently regardless of BLE discovery order

### WebUI Dashboard

A browser-based control panel at `http://localhost:8080/`:
- Live light table with status
- CCT/HSI/Scene controls with sliders
- Preset grid with add/delete endpoints
- Animation browser with categorized sections and play/stop
- Update checker
- Collapsible API reference

### HTTP Animation API

**GET:** `http://server:port/NeewerLux/doAction?animate=Concert%20Sweep|2.0|10|50`

**POST** to `/NeewerLux/doAction`:
```json
{
  "action": "play",
  "name": "Concert Sweep",
  "speed": 1.0,
  "loop": true,
  "rate": 10,
  "brightness": 50,
  "parallel": true
}
```

### Additional Features

- **Thread safety** — all background-to-GUI updates via Qt signals
- **Update checker** — GitHub Releases API, displayed in GUI and WebUI
- **Instance lock** — PID-based with stale lock detection
- **Log tab** — thread-safe buffered file writes, auto-scroll, clear/save
- **Info tab** — quick start guide, HTTP API reference, clickable links
- **Console management** — auto-hidden for exe builds, toggle in preferences
- **System tray integration** — minimize to tray on close, context menu
- **Dark/light theme** — full QSS theme system
- **PySide6 compatibility** — PySide2 fallback preserved
- **Auto-reconnect on wake** — background worker re-links lights after sleep
- **Parallel BLE writes** — `asyncio.gather()` for simultaneous multi-light commands

---

## Repository

https://github.com/poizenjam/NeewerLux/

## License

Same as upstream — see [NeewerLite-Python](https://github.com/taburineagle/NeewerLite-Python) for license details.
