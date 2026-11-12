# NeewerLux HTTP API

The contract for anything that drives NeewerLux over HTTP: Stream Deck plugins, Streamer.bot, scripts, the web dashboard. This is API version **2** (NeewerLux 1.3.3 and later). Version 1 is everything before: those clients keep working, because version 2 only adds.

## Basics

- **Base URL:** `http://<host>:<port>`, port 8080 unless changed in Global Preferences. Turn the server on from the toolbar, or have it start with the app.
- **Access:** no authentication. Requests are accepted only from IP addresses matching the allowlist in Global Preferences (by default `127.0.0.1`, `192.168.` and `10.`); others get `403`. Don't expose the port to the internet.
- **CORS:** every response allows any origin (`Access-Control-Allow-Origin: *`), and `OPTIONS` preflight requests are answered, so browser pages on other origins can call the API.
- **Feature detection:** `list_json`, `status_json` and `POST /NeewerLux/settings {"action": "get"}` include `"apiVersion"`. A response without it comes from API version 1. Additions bump the version; existing fields are not removed or changed in meaning.
- **Old path:** `/NeewerLite-Python/` is accepted in place of `/NeewerLux/` for GET commands, `batch` and `animate`.

### Identifying lights

Wherever a light is named (`light=`, the `light` field of a batch command, animation and sequence targets), any of these work:

| Form | Example | Meaning |
|---|---|---|
| ID | `1`, `91` | The light's preferred ID if it has one (Light Preferences), otherwise its row number. Simulated lights use 91 to 95. |
| Name | `Key Light` | The custom name, case-insensitive |
| MAC address | `AA:BB:CC:DD:EE:FF` | On macOS, the GUID Bluetooth reports instead |
| All | `*` or `all` | Every light |
| Role or position | `@key`, `@fill`, `@rim`, `@background`, `@practical`, `@left`, `@centre`, `@right`, `@front`, `@beside`, `@back`, `@low`, `@middle`, `@high`, `@eyeline`, `@all` | From each light's show settings; dots combine them (`@rim.left`, `@back.left.high`). Sides are the streamer's left and right facing the camera; front is between the streamer and the camera |
| A list | `1;3;@rim` | Any mix, separated by `;` |

### The flash guard

On by default, every light is kept to at most 3 flashes a second (the WCAG limit for photosensitive seizures): changes are spaced evenly, and one that would come too soon is held back and sent (as the light's latest value) once it's allowed. This applies to everything sent over HTTP, so a fast animation or a burst of commands plays slower than asked; `status_json` reports how many changes were held. It can be turned off in Global Preferences or with `set_global` `{"flashGuardEnabled": false}`. Lights marked as in the eye line can be given a stricter limit (`eyelineFlash`), which applies even with the guard off.

### Units

| Value | Range | Notes |
|---|---|---|
| `temp` | 3200 to 8500 (Kelvin) | Also accepted in hundreds of Kelvin (32 to 85) everywhere: a value over 100 is read as Kelvin. Each light is clamped to its own range (Light Preferences, or the global CCT range). |
| `hue` | 0 to 360 | degrees |
| `sat`, `bri` | 0 to 100 | percent; `bri` is also accepted as `brightness` or `intensity` on GET |
| `scene` | 1 to 9 | the light's built-in animated scenes (mode `ANM`, or `SCENE` on GET) |

Values outside a range are clamped. Brightness limits (per light, or the global ones) are then applied to everything except the desktop app's sliders, and a CCT-only light given an HSI or scene command gets the nearest white (or nothing, if Global Preferences says to ignore such commands).

### How commands reach the lights

Light commands (GET `light=`, GET `batch=`, POST batch) are stored per light and written by one background worker with a synchronized send. They are **never refused for being busy**: if a light already has a command waiting, the newer one replaces it and the light is written once with the latest value. A Stream Deck dial can send as fast as it likes; the light follows with the most recent value. A response of `"success": true` means the command was accepted and queued, not that the light confirmed it.

While an animation is playing on the override layer (the classic one-at-a-time slot), a light command stops it first, as the GUI does; lights the command doesn't name return to where they were before the animation. While a sequence or effect is driving a light, a light command for it doesn't interrupt the show: it becomes what that light returns to when the show ends. Locked lights take light commands immediately and ignore shows.

Scans, links and preset recalls use the worker for longer. If it's busy, they wait up to 5 seconds and are then skipped (logged).

## GET /NeewerLux/doAction?...

Parameters are joined with `&`. Add `nopage` to any command to get an empty response instead of an HTML page; scripts should always add it, and should not parse the HTML.

### Light commands

| Request | Effect |
|---|---|
| `light=1&mode=CCT&temp=5600&bri=80` | White at a colour temperature. On this form `temp` uses its first two digits, so `5600`, `56` and `5650` all mean 5600K. |
| `light=1&mode=HSI&hue=240&sat=100&bri=50` | Colour |
| `light=1&mode=SCENE&scene=3&bri=80` | Built-in scene (`ANM` also works) |
| `light=1&on` / `light=1&off` | Power |
| `batch=1:HSI:0:100:50;2:CCT:5600:80;3:OFF` | Different commands to different lights in one request: `light:mode:values`, segments separated by `;`. CCT values: `temp:bri`; HSI: `hue:sat:bri`; ANM/SCENE: `scene:bri`; `ON`/`OFF` take none. A MAC address works as the light. |

### Presets

| Request | Effect |
|---|---|
| `use_preset=3` | Recall preset 3 (1-based) |
| `save_preset=3` | Save the current state of every light into preset 3 |
| `add_preset` | Add an empty preset slot at the end |
| `delete_preset=3` | Delete preset 3; later presets move up one |

### Animations and layers

| Request | Effect |
|---|---|
| `animate=Name` | Play a saved animation on the override layer. Names match case-insensitively; URL-encode spaces as `%20`. |
| `animate=Name\|speed\|rate\|bri\|loop\|maxLoops\|revert\|layer\|queue\|target\|fadeIn\|fadeBack` | All fields after the name are optional and positional; leave one empty to skip it. Defaults: speed `1.0`, rate `5` updates per second, brightness `100` percent, loop from the animation file, maxLoops `0` (endless), revert from Global Preferences, layer `override`, queue `queue`, target the animation's own lights, fades from the animation file or else Global Preferences. Layer is `override`, `effect` or `show`; queue is `queue` or `replace` (effect layer); target is any light form above, such as `@rim`; fadeIn and fadeBack are milliseconds (0 cuts), for when it takes the lights and when it lets go. |
| `stop_animate` | Stop the override animation |
| `stop_layer=effect` | Stop a layer: `override`, `effect` (the queue moves on), `effect_all` (also clears the queue), `show`, `sound` (the sound mode, and its capture), or `all` (every one of them) |
| `list_animations` | HTML list (use `list_json` from scripts) |

Example, a five-loop strobe on the rim lights as an effect: `animate=Strobe|1|10|100|true|5||effect||@rim`

### Sequences

| Request | Effect |
|---|---|
| `sequence=play\|Example%20-%20Four%20Light%20Demo` | Play a saved sequence from the start; add `\|12000` to start 12 s in |
| `sequence=pause`, `sequence=resume`, `sequence=stop` | Pause returns the lights to where they were before the sequence; resume carries on from the same point |
| `sequence=seek\|65000` | Jump to 65 s |
| `sequence=position\|65120` | Sync to an external clock: offsets up to 250 ms are absorbed by running up to 5% fast or slow, larger ones jump |

### Sound modes

Lights following live audio ([SOUND_MODES.md](SOUND_MODES.md)). They play on the sound layer, under sequences and effects.

| Request | Effect |
|---|---|
| `sound=start\|Pulse` | Start a sound mode (replacing whatever sound is playing). `sound=start` alone starts the last one used. |
| `sound=start\|Colour Drift\|1;3` | Lights 1 and 3 follow Colour Drift; other lights keep following whatever sound they follow (any light target works, such as `@rim`) |
| `sound=mode\|Bands` | Switch the playing sound mode (also with `\|lights`) |
| `sound=stop` | Stop sound; its lights fade back |
| `sound=stop\|3` | Light 3 stops following sound; sound stops when no lights are left |

### Lights and connection

| Request | Effect |
|---|---|
| `discover` | Scan for lights (about 5 s) and link the ones found |
| `link=1` | Link one light; `link=all` links every known light |
| `custom_name=0\|Key%20Light` | Rename a light. The number is the light's 0-based position in the list (not its ID). |
| `list` | HTML list of lights and presets |

### list_json

`GET /NeewerLux/doAction?list_json` returns everything a controller needs to build its menus and show state:

```json
{
  "apiVersion": 2,
  "version": "1.3.3",
  "lights": [
    {
      "id": 1, "name": "Key", "mac": "AA:BB:CC:DD:EE:FF", "model": "NEEWER-RGB660 PRO",
      "linked": true, "simulated": false,
      "status": "(CCT MODE): TEMP: 4500K / BRI: 60",
      "power": "on", "channel": 1,
      "setting": {"mode": "CCT", "temp": 4500, "bri": 60},
      "output": {"mode": "CCT", "temp": 4500, "bri": 60, "color": "#ffdcbb"},
      "cctRange": [3200, 5600], "cctOnly": false,
      "role": "key", "side": "right", "depth": "front", "height": "middle", "aim": "you", "locked": false, "layer": "base"
    }
  ],
  "animations": [{"name": "Heartbeat", "description": "...", "frames": 4, "loop": true, "modes": ["HSI"]}],
  "animationPlaying": false, "currentAnimation": "",
  "presets": [{"index": 1, "name": "Stream", "custom": true}], "numPresets": 8,
  "sequences": [{"name": "Example - Four Light Demo", "duration_ms": 40000, "cues": 12, "description": "..."}]
}
```

Per light:

| Field | Meaning |
|---|---|
| `id` | What to send as `light` (preferred ID, or row number) |
| `status` | Display text, kept for version 1 clients. Don't parse it; use the fields below. |
| `power` | `"on"`, `"standby"`, or `null` when the light doesn't report it or hasn't been asked yet. From the light's last status reply, polled every few seconds while no show is running. |
| `channel` | The light's channel from the same reply, or `null` |
| `setting` | The last command the light was given, by any route (slider, preset, URL, batch), with `temp` in Kelvin. `{"mode": "OFF"}` when it was turned off. `null` if unknown. While a show drives the light this is the show's current frame. |
| `output` | What the light is actually showing: `setting` after the CCT-only conversion and brightness limits, plus `color`, an approximate `#rrggbb` for display. `null` if unknown. For simulated lights, built from what they received. |
| `cctRange` | The light's colour temperature range in Kelvin, as used for clamping |
| `cctOnly` | `true` for lights that only do white; colour commands are converted (or ignored) |
| `role`, `side`, `depth`, `height`, `aim`, `locked` | Show settings from Light Preferences |
| `layer` | What is driving the light now: `base` (sliders, presets, light commands), `sound` (a sound mode), `show` (a sequence), `effect` or `override` (animations) |

### status_json

`GET /NeewerLux/doAction?status_json` is the light-weight state for polling (the web dashboard reads it twice a second):

```json
{
  "apiVersion": 2,
  "layers": {"override": null, "effect": null, "show": null, "sound": null},
  "sequence": {"type": "sequence", "name": "Example - Four Light Demo", "state": "playing", "position_ms": 12034, "duration_ms": 40000},
  "lights": [{"id": 1, "name": "Key", "role": "key", "side": "right", "depth": "front", "height": "middle", "aim": "you", "locked": false, "layer": "show",
              "linked": true, "simulated": false, "mode": "HSI", "bri": 45, "color": "#b04ce0"}],
  "flashGuard": {"enabled": true, "held": 0, "eyeline": "same"},
  "stage": {"camera": "front"},
  "handbackFadeMs": 500,
  "fadeInMs": 0,
  "sound": {"available": true, "reason": "", "running": true, "mode": "Pulse", "params": {"sensitivity": 1.0, "range_db": 18, "floor": 15, "ceiling": 70, "smoothing": 0.5, "fps": 20, "cycle_s": 20, "palette": [{"hue": 265, "sat": 85}]},
            "assignments": [{"mode": "Pulse", "lights": null}, {"mode": "Colour Drift", "lights": [1]}],
            "lastMode": "Pulse", "device": "", "deviceName": "Speakers (Focusrite USB Audio)", "capturing": true, "error": "",
            "levels": {"level": 0.62, "low": 0.71, "mid": 0.55, "high": 0.4, "centroid": 0.48, "bpm": 124.2, "confidence": 0.81, "beat": 311, "silent": false, "rms_db": -18.4}}
}
```

`flashGuard` is `{"enabled": true, "held": 12, "eyeline": "same"}`: whether the flash guard is on, how many changes it has held back since NeewerLux started, and the eye-line setting. `stage.camera` is where the main camera is (for drawing a plan), and `handbackFadeMs` and `fadeInMs` the global fades.

`sound` is the sound mode state, as `POST /NeewerLux/sound` `status` returns it: whether sound modes can run here (`available`, and `reason` when not, such as the audio packages missing), whether one is `running`, which `mode` with which `params` (the latest started), the `assignments` (each playing mode and the IDs of the lights given to it, `null` for a mode on its own targets), the capture `device` (`""` = whatever the default output plays) and its name, a capture `error` if the device failed (it retries every 2 s), and the live `levels` (`null` when not capturing): `level`, `low`, `mid`, `high` and `centroid` from 0 to 1, `bpm` (0 until there's a tempo), the tempo `confidence`, `beat` (counts up on each beat), `silent` and `rms_db`.

`layers` holds whatever is playing on each layer (`null` when nothing is); the override entry includes `name`, `keyframe` and `keyframes`, the sound entry `name` and the levels. `sequence` is `null` when no sequence is loaded; `state` is `playing` or `paused`.

## POST endpoints

All take a JSON body (`Content-Type: application/json`) and answer `200` with JSON; failures are `"success": false` with `error` or `errors`. A malformed body gets `400`. Bodies are limited to 64 KB, except `/NeewerLux/sequence` (256 KB).

### POST /NeewerLux/batch

```json
{"commands": [
  {"light": "1", "mode": "CCT", "temp": 5600, "bri": 80},
  {"light": "@rim", "mode": "HSI", "hue": 300, "sat": 100, "bri": 60},
  {"light": "3", "mode": "ANM", "scene": 2, "bri": 50},
  {"light": "*", "mode": "ON"}
]}
```

Mode is `CCT`, `HSI`, `ANM`, `ON` or `OFF`. Missing values default to temp 5600, hue 240, sat 100, bri 100, scene 1. Same queueing and animation rules as GET light commands.

Response:

```json
{"success": true, "commands_processed": 4, "lights_updated": 4,
 "results": [{"light": "1", "mode": "CCT", "status": "ok", "targets": 1},
             {"light": "9", "mode": "HSI", "status": "error", "error": "Light not found"}]}
```

`"ok"` means queued. `targets` is how many lights the `light` value matched.

### POST /NeewerLux/animate

| Body | Effect |
|---|---|
| `{"action": "play", "name": "Concert Sweep", "speed": 1.0, "rate": 5, "brightness": 100, "loop": true, "maxLoops": 3, "revert": true}` | Play on the override layer. Optional `"target": "@rim"`, `"parallel": false` (one light at a time, the v1.3.0 path), `"fade_in_ms"` and `"handback_fade_ms"` (override the animation's and the global fades). On the override layer `revert` sets the Global Preferences option. |
| `{"action": "play", "name": "Heartbeat", "layer": "effect", "mode": "queue", "target": "@rim"}` | Play as an effect (`mode` `queue` or `replace`) or on the `show` layer; `revert` applies to this request only. `"result": "queue_full"` when the effect queue (10) is full. |
| `{"action": "stop"}` | Stop the override layer; `"layer": "effect"` (with `"clear_queue": true` to empty the queue), `"show"` or `"all"` |
| `{"action": "list"}` | `{"animations": [{"name", "description", "keyframes", "loop"}], "currently_playing"}` |
| `{"action": "status"}` | `{"running", "animation", "show"}` where `show` is the `status_json` body |
| `{"action": "create", "animation": {...}}` | Save an animation (same format as the files in `light_prefs/animations`), replacing any of the same name |
| `{"action": "get", "name": "Heartbeat"}` | The whole animation: `{"animation": {...}}` |
| `{"action": "save", "animation": {...}, "original": "Old Name", "overwrite": false}` | Save from an editor. Needs a name and at least one keyframe, and every light entry needs a `mode` of `HSI`, `CCT`, `SCENE` (or `ANM`; a built-in scene), `ON` or `OFF`; otherwise `errors` says which. `original` is the name it was opened under: a different name renames it. Saving over another animation needs `"overwrite": true`. |
| `{"action": "duplicate", "name": "Heartbeat"}` | Copy as "Heartbeat (copy)"; the reply's `animation` is the new name |
| `{"action": "delete", "name": "Heartbeat"}` | Delete it (stops it first if it's playing) |
| `{"action": "reload"}` | Re-read `light_prefs/animations`; the reply has `count` |

### POST /NeewerLux/sequence

| Body | Effect |
|---|---|
| `{"action": "play", "name": "...", "start_ms": 0}` | Play a saved sequence. Optional `"fade_in_ms"` and `"handback_fade_ms"` override the sequence's and the global fades for this play. |
| `{"action": "play", "sequence": {...}}` | Play one sent inline, without saving it |
| `{"action": "pause"}`, `{"action": "resume"}`, `{"action": "stop"}` | As on GET |
| `{"action": "seek", "ms": 65000}` | Jump |
| `{"action": "set_position", "ms": 65120}` | External clock sync; the reply says `"slew"` or `"jump"` |
| `{"action": "status"}` | The sequence part of `status_json` |
| `{"action": "list"}` | `{"sequences": [{"name", "duration_ms", "cues", "description"}]}` |
| `{"action": "reload"}` | Re-read `light_prefs/sequences`, then list |
| `{"action": "validate", "sequence": {...}}` | Check a sequence: `errors` and `warnings` |
| `{"action": "save", "sequence": {...}, "original": "Old Name", "overwrite": false}` | Validate and save. `original` is the name it was opened under: a different name renames it (the old file goes). Saving over another sequence needs `"overwrite": true`. |
| `{"action": "get", "name": "..."}` | The whole sequence: `{"sequence": {...}}` |
| `{"action": "delete", "name": "..."}` | Delete it (stops it first if it's playing) |
| `{"action": "editor", "targets": ["@rim", "1;2"]}` | What a timeline editor needs: `lights` in sweep order (`index`, `id`, `name`, `role`, `side`, `depth`, `height`, `simulated`), `targets` (the light IDs each given target drives now), `choices` (target suggestions with labels), `animations` and `presets` (count) |
| `{"action": "render", "name": "...", "step_ms": 50, "start_ms": 0, "end_ms": 60000}` | What each light would do, without playing: per-light colour changes and the cue list |
| `{"action": "render", "name": "...", "format": "png", "width": 1600}` | The same as an image strip (`image/png`). Needs the desktop window; without it the reply is an error and the JSON render still works. |

The sequence format, targets, render output and timing rules are in [SEQUENCE_FORMAT.md](SEQUENCE_FORMAT.md).

### POST /NeewerLux/sound

| Body | Effect |
|---|---|
| `{"action": "start", "mode": "Pulse"}` | Start a sound mode, replacing whatever sound is playing, and the capture. Optional `"lights"` (a light target such as `"1;3"` or `"@rim"`): only those lights follow this mode, leaving whatever sound they followed, and the rest of the sound layer plays on (starting it if nothing plays). Optional `"device"` (an `id` from `devices`; `""` = whatever the default output plays), `"params"` (top-level values for this play, as in `set`; `"palette"` can be a saved palette's name), `"fade_in_ms"` and `"handback_fade_ms"`. Without `mode` it starts the last one used. The mode and device are remembered. |
| `{"action": "mode", "mode": "Bands"}` | Switch the playing mode (fading between them), optionally with `"lights"`; an error when none is playing |
| `{"action": "set", "params": {"sensitivity": 1.5, "ceiling": 60}}` | Change a playing mode's `sensitivity`, `range_db`, `floor`, `ceiling`, `smoothing`, `palette` (colours, or a saved palette's name), `cycle_s`, `fps` or `parts` at once, without saving: the one named in `"mode"`, else the latest started. The reply has the `params` now in use. |
| `{"action": "stop"}` | Stop sound (its lights fade back) and the capture. With `"lights"`, only those lights stop following sound; it stops when none are left. |
| `{"action": "device", "device": "..."}` | Choose the capture device (remembered); takes effect at once if a mode is playing |
| `{"action": "devices"}` | `{"devices": [{"id", "name", "loopback"}], "device"}`: first `""` (the default output, followed when it changes), then each output's playback (`loopback` true) and each input |
| `{"action": "status"}` | The `sound` part of `status_json` |
| `{"action": "list"}`, `{"action": "reload"}` | `{"modes": [{"name", "description", "parts"}]}`; reload re-reads `light_prefs/sound_modes` first |
| `{"action": "get", "name": "Pulse"}` | The whole file: `{"mode": {...}}` |
| `{"action": "validate", "mode": {...}}` | Check one: `errors` and `warnings` (a target that matches no light right now) |
| `{"action": "save", "mode": {...}, "original": "Old Name", "overwrite": false}` | Validate and save. `original` renames; saving over another needs `"overwrite": true`. |
| `{"action": "delete", "name": "..."}` | Delete it (stops it first if it's playing) |
| `{"action": "palettes"}` | Saved palettes: `{"palettes": [{"name", "palette"}]}` |
| `{"action": "save_palette", "name": "Neon", "palette": [...], "overwrite": false}` | Save a palette to `light_prefs/palettes`; replacing one needs `"overwrite": true` |
| `{"action": "delete_palette", "name": "Neon"}` | Delete a saved palette |

When the audio packages aren't installed, `start` answers `"success": false` with the reason in `errors`; the file actions still work.

Light commands, batches and preset recalls that reach a light following sound take that light out of the sound layer and show at once; sound (and its capture) stops when no lights are left. An Off command reaches its light whatever is playing and takes it out of the sound mode, sequence or effect that was driving it until a later command switches it on; a show switches on a light that is off before it drives it.

### POST /NeewerLux/presets

The desktop's preset menu and editor. Preset numbers are 1-based. Every reply that changes something includes the preset as `preset` (or the whole list as `presets` after a delete), and the change is saved to `customLights.prefs` (when Remember presets on exit is on, as on the desktop).

| Body | Effect |
|---|---|
| `{"action": "list"}` | `{"presets": [preset, ...]}` |
| `{"action": "get", "index": 3}` | One preset: `{"index", "name", "custom", "global", "entries"}`. `custom` is false while it's still the factory default; `global` is true when it applies to whichever lights it's recalled on rather than to specific lights. |
| `{"action": "save", "index": 3, "name": "Stream", "entries": [...]}` | Replace its contents (and name, if given). Each entry: `{"target": "-1" or a light, "mode": "CCT"/"HSI"/"Scene", "bri", "temp" (Kelvin or hundreds), "hue", "sat", "scene"}`. One entry with target `"-1"` makes a global preset; entries per light make a snapshot. Optional `"fade_ms"`: how long recalling it fades in (`null` = the global Fade in). `list` and `get` report `fade_ms`. An entry read with `"off": true` (the light was off in the snapshot) keeps that when sent back. An entry for a single light can have `"sound": "Pulse"`: recalling the preset sets that light following the sound mode, its colour being what it returns to when sound stops (not written on recall). |
| `{"action": "rename", "index": 3, "name": "Stream"}` | Rename (empty clears; up to 20 characters) |
| `{"action": "move", "index": 3, "direction": "left"}` | Swap with its neighbour (`left` or `right`) |
| `{"action": "duplicate", "index": 3}` | Insert a copy after it, named "... (copy)" |
| `{"action": "delete", "index": 3}` | Delete; later presets move up. The last preset can't be deleted. |
| `{"action": "add"}` | Add an empty preset at the end |
| `{"action": "snapshot", "index": 3}` | Save every light's current state into it |
| `{"action": "recall", "index": 3}` | Recall it, as `use_preset=3` |

### POST /NeewerLux/settings

| Body | Effect |
|---|---|
| `{"action": "get"}` | `{"apiVersion", "global": {...}, "lights": [...], "roles", "sides", "simulatedRigs"}` |
| `{"action": "set_light", "light": 0, "settings": {"role": "key", "maxBri": 60}}` | Change one light's preferences. `light` is the 0-based `index` from `get` (an ID, name or MAC also works). Settings: `customName`, `preferredID` (0 to 99, 0 = automatic), `tempRange` (`[min, max]` Kelvin), `cctOnly`, `role`, `side` (`left`, `centre`, `right`), `depth` (`front`, `beside`, `back`), `height` (`low`, `middle`, `high`), `aim` (where it points: `you`, or `front`, `front-right`, `right`, `back-right`, `back`, `back-left`, `left`, `front-left` on the plan), `order` (0 to 99, 0 = automatic: by position, then ID), `eyeline`, `maxBri` and `minBri` (-1 = use the global limit, else 0 to 100), `locked`. Saved to the light's preferences file, as the desktop does. |
| `{"action": "set_global", "settings": {"envMaxBri": 80}}` | Change global preferences: `envMaxBri` (1 to 100), `envMinBri` (0 to 100), `seqFrameRate` (1 to 30), `effectMaxSeconds` (1 to 600), `globalCCTMin` and `globalCCTMax` (2700 to 8500), `cctFallbackMode` (`convert` or `ignore`), `simulatedLights` (0 to 4, next start), `simulatedCCTOnly` (next start), `flashGuardEnabled` (true or false), `eyelineFlash` (`same`, `gentler` = at most 1 flash a second, `calm` = one change every 2 seconds, for lights marked as in the eye line; applies even with the guard off), `handbackFadeMs` (0 to 5000: fade when an effect, sequence or animation lets go of a light; 0 cuts), `fadeInMs` (0 to 5000: fade when a preset is recalled or an animation or sequence takes lights over; 0 cuts), `cameraPosition` (`front`, `front-left`, `front-right`, `left`, `right`, `back-left`, `back`, `back-right`; drawn on the Stage plan). |

Every value in a request is checked before any is applied; a request with an invalid value changes nothing and lists the problems in `errors`. Network access, keyboard shortcuts and startup options can't be changed over HTTP. Changes show up in the desktop window straight away.

## Changes by API version

NeewerLux 1.4.0 adds, within version 2 (nothing changes for existing clients): the `sound` layer, `POST /NeewerLux/sound`, `sound=` requests, `stop_layer=sound` (and `all` includes it) and `sound` in `status_json` (with `assignments`: which lights follow which mode), sound on some lights only (`lights`, `sound=start|Mode|lights`, `sound=stop|lights`), saved palettes, colour `cycle` and `cycle_s`, and `sound` on preset entries.

**2** (NeewerLux 1.3.3): `apiVersion` and `version` fields; structured per-light state and `sequences` in `list_json`; JSON batch `temp` accepts Kelvin; light commands are coalesced per light instead of answered with "Server is busy"; POST batch stops an override animation like GET commands do; editing over HTTP: `/NeewerLux/presets`, animation `get`/`save`/`duplicate`/`delete`/`reload`, sequence `get`/`delete`/`editor` and renaming on save. Also part of this version, from 1.3.1 and 1.3.2: layers, sequences, `status_json`, `stop_layer`, `/NeewerLux/sequence` and `/NeewerLux/settings`.

**1** (NeewerLux 1.3.0 and earlier): GET commands, `list_json` without state, POST batch with `temp` in hundreds of Kelvin only, POST animate.
