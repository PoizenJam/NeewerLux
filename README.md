# NeewerLux

A Neewer LED light control app based on [NeewerLite-Python](https://github.com/taburineagle/NeewerLite-Python) (v0.12d) by @taburineagle, adding keyframe-based custom animations, light aliasing, paginated preset management, PySide6 support, and various quality-of-life improvements for multi-light streaming setups.

The upstream project is an unofficial cross-platform Neewer LED light control app written in Python, supporting GUI, CLI, and HTTP server modes. Read the upstream manual here: https://github.com/taburineagle/NeewerLite-Python/wiki

**Supported lights:** GL1, NL140, SNL1320, SNL1920, SNL480, SNL530, **SNL660**, SNL960, SRP16, SRP18, WRP18, ZRP16, BH30S, CB60, CL124, RGB C80, RGB CB60, RGB1000, RGB1200, RGB140, RGB168, RGB176 A1, RGB512, RGB800, SL-90, RGB1, **RGB176**, RGB18, RGB190, RGB450, **RGB480**, RGB530 PRO, RGB530, RGB650, **RGB660 PRO**, RGB660, RGB960, RGB-P200, RGB-P280, SL-70, **SL-80**, ZK-RY

## Fork Features

### Custom Animation System

A full keyframe-based animation engine that drives Neewer lights through timed color sequences with smooth interpolation. Animations are stored as JSON files in `light_prefs/animations/` and can target individual lights by MAC address, numeric ID, alias name, or all lights with the `"*"` wildcard.

Each keyframe specifies a hold time (how long to dwell on the color), a fade time (how long to transition from the previous keyframe), and per-light color parameters in HSI, CCT, or ANM modes. The engine handles shortest-path hue interpolation around the 360° color wheel so transitions between, say, red (0°) and magenta (300°) go the short way rather than sweeping through the entire spectrum.

**Playback controls:**

- **Speed** — multiplier applied to all timing values (0.25x to 4x)
- **Rate** — BLE updates per second during fades (1-30, default 5; with Parallel enabled, ~15 is achievable regardless of light count)
- **Brightness** — scales all brightness values at playback time without modifying the animation file (5-100%)
- **Loop** — continuous playback with seamless wraparound fading between last and first keyframe
- **Parallel writes** — sends BLE commands to all lights simultaneously using `asyncio.gather()` instead of sequentially, reducing per-frame time from ~50ms×N to ~50ms regardless of light count (toggle-able for legacy adapter compatibility)

**22 built-in animation presets:**

| Preset | Type | Description |
|--------|------|-------------|
| Police Flash | Instant | Alternating red/blue across light pairs |
| Strobe | Instant | Rapid white on/off flash |
| DJ Pulse | Instant | Fast alternating colors, 2-on/2-off per beat |
| Blackout Flash | Dramatic | Dark silence → sudden bright reveal → fade out |
| Bass Drop | Hybrid | Bright flash impact that decays to near-dark |
| Thunderstorm | Ambient | Dark moody blue with sudden bright lightning flashes |
| Concert Sweep | Smooth | Wide color sweeps between warm/cool, mirror-paired across lights |
| Neon Nights | Smooth | Cyberpunk magenta/cyan opposing pair crossfade |
| Retrowave | Smooth | Synthwave purple/pink/blue moody palette |
| Stage Wash | Smooth | Slow theatrical rotation — each light cycles through different colors |
| Fire Flicker | Ambient | Irregular warm tone and brightness variation |
| Campfire | Ambient | Multi-light staggered warm flicker |
| Candlelight | Ambient | Gentle warm candle flicker with subtle movement |
| Sunset Fade | Ambient | Amber → red → purple → deep blue → amber |
| Ocean Waves | Ambient | Slow blue-green undulation simulating ocean light |
| Northern Lights | Ambient | Slow-moving greens and purples like an aurora |
| Lava Lamp | Ambient | Deep saturated colors slowly morphing |
| Breathe | Smooth | Warm CCT brightness pulse |
| Color Wash | Smooth | Slow warm/cool tone flow |
| Color Cycle | Smooth | Full spectrum hue rotation |
| Rainbow Gradient | Smooth | Cinematic full spectrum sweep |
| Rainbow Chase | Smooth | 90° offset hue rotation staggered across 4 lights |

Six template generators are available from the GUI for creating new animations: Police Flash, Color Cycle, Strobe, Breathe, Color Wash, and Rainbow Chase. Animations can also be authored directly in the JSON editor tab.

### Light Aliases (Preferred ID)

The existing **Light Preferences** tab now includes a **Preferred ID** field alongside the custom name. When set, the custom name and preferred ID are used as aliases throughout the system, so lights can be addressed consistently regardless of BLE discovery order.

To configure: select a light in the table, go to the **Light Preferences** tab, set a custom name (e.g. "Key"), set a preferred ID (e.g. 1), and click **Save Preferences**.

With aliases configured:
- The GUI table automatically reorders so preferred-ID lights appear first, in ID order — row numbers match effective IDs
- Animation keyframes can use `"Key"`, `"Fill"`, etc. as light targets instead of numeric IDs
- HTTP batch commands work with names: `?batch=Key:HSI:0:100:50;Fill:CCT:56:80`
- Preferred IDs always resolve to the same physical lights regardless of connection order
- Setting Preferred ID to 0 means auto (uses position in the table)

### HTTP Animation API

Animations can be controlled remotely via both GET and POST endpoints.

**GET** — append parameters with `|` separator:
```
http://server:port/NeewerLux/doAction?animate=Concert%20Sweep|2.0|10|50
```
Format: `animate=Name|speed|rate|brightness`

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

Other POST actions: `"stop"` to halt playback, `"list"` to enumerate available animations.

### Paginated Presets

Preset buttons are now paginated with forward/back navigation, supporting an arbitrary number of stored presets beyond the original fixed grid. Presets can be renamed by middle-clicking the preset button, and custom names are persisted across sessions.

### PySide6 Migration

The GUI has been migrated from PySide2 to PySide6, with a transparent fallback to PySide2 for environments where PySide6 is unavailable. The `pyside_exec()` helper handles the `exec()` API change between versions.

### Auto-Reconnect on Wake

A background worker thread monitors light connections and automatically re-links lights that disconnect during system sleep/wake cycles, without requiring manual intervention.

### Additional Improvements

- **Batch HTTP commands** — send different HSI/CCT/ANM parameters to different lights in a single HTTP request
- **Stale lock file cleanup** — automatically removes orphaned `.lock` files on startup
- **Bleak deprecation fix** — uses `AdvertisementData.rssi` instead of the deprecated `BLEDevice.rssi`
- **Animation auto-stop** — selecting a preset, moving a slider, or sending a non-animation HTTP command automatically stops any running animation

## Requirements

- Python 3.8+
- PySide6 (preferred) or PySide2
- bleak (BLE communication)

## Usage

Same as upstream — see the [NeewerLite-Python wiki](https://github.com/taburineagle/NeewerLite-Python/wiki) for general usage. Animation features are accessible from the **Animations** tab in the GUI, or via the HTTP API documented above.

## Repository

https://github.com/poizenjam/NeewerLux/
