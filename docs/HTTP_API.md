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
| Role or side | `@key`, `@fill`, `@rim`, `@ambient`, `@practical`, `@left`, `@centre`, `@right`, `@eyeline`, `@all` | From each light's show settings; `@rim.left` means both |
| A list | `1;3;@rim` | Any mix, separated by `;` |

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
| `animate=Name\|speed\|rate\|bri\|loop\|maxLoops\|revert\|layer\|queue\|target` | All fields after the name are optional and positional; leave one empty to skip it. Defaults: speed `1.0`, rate `5` updates per second, brightness `100` percent, loop from the animation file, maxLoops `0` (endless), revert from Global Preferences, layer `override`, queue `queue`, target the animation's own lights. Layer is `override`, `effect` or `show`; queue is `queue` or `replace` (effect layer); target is any light form above, such as `@rim`. |
| `stop_animate` | Stop the override animation |
| `stop_layer=effect` | Stop a layer: `override`, `effect` (the queue moves on), `effect_all` (also clears the queue), `show`, or `all` |
| `list_animations` | HTML list (use `list_json` from scripts) |

Example, a five-loop strobe on the rim lights as an effect: `animate=Strobe|1|10|100|true|5||effect||@rim`

### Sequences

| Request | Effect |
|---|---|
| `sequence=play\|Example%20-%20Four%20Light%20Demo` | Play a saved sequence from the start; add `\|12000` to start 12 s in |
| `sequence=pause`, `sequence=resume`, `sequence=stop` | Pause returns the lights to where they were before the sequence; resume carries on from the same point |
| `sequence=seek\|65000` | Jump to 65 s |
| `sequence=position\|65120` | Sync to an external clock: offsets up to 250 ms are absorbed by running up to 5% fast or slow, larger ones jump |

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
      "role": "key", "side": "right", "locked": false, "layer": "base"
    }
  ],
  "animations": [{"name": "Heartbeat", "description": "...", "frames": 4, "loop": true, "modes": ["HSI"]}],
  "animationPlaying": false, "currentAnimation": "",
  "presets": [{"index": 1, "name": "Stream", "custom": true}], "numPresets": 8,
  "sequences": [{"name": "Example - Four Light Demo", "duration_ms": 40000, "description": "..."}]
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
| `role`, `side`, `locked` | Show settings from Light Preferences |
| `layer` | What is driving the light now: `base` (sliders, presets, light commands), `show` (a sequence), `effect` or `override` (animations) |

### status_json

`GET /NeewerLux/doAction?status_json` is the light-weight state for polling (the web dashboard reads it twice a second):

```json
{
  "apiVersion": 2,
  "layers": {"override": null, "effect": null, "show": null},
  "sequence": {"type": "sequence", "name": "Example - Four Light Demo", "state": "playing", "position_ms": 12034, "duration_ms": 40000},
  "lights": [{"id": 1, "name": "Key", "role": "key", "side": "right", "locked": false, "layer": "show",
              "linked": true, "simulated": false, "mode": "HSI", "bri": 45, "color": "#b04ce0"}]
}
```

`layers` holds whatever is playing on each layer (`null` when nothing is); the override entry includes `name`, `keyframe` and `keyframes`. `sequence` is `null` when no sequence is loaded; `state` is `playing` or `paused`.

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
| `{"action": "play", "name": "Concert Sweep", "speed": 1.0, "rate": 5, "brightness": 100, "loop": true, "maxLoops": 3, "revert": true}` | Play on the override layer. Optional `"target": "@rim"`, `"parallel": false` (one light at a time, the v1.3.0 path). On the override layer `revert` sets the Global Preferences option. |
| `{"action": "play", "name": "Heartbeat", "layer": "effect", "mode": "queue", "target": "@rim"}` | Play as an effect (`mode` `queue` or `replace`) or on the `show` layer; `revert` applies to this request only. `"result": "queue_full"` when the effect queue (10) is full. |
| `{"action": "stop"}` | Stop the override layer; `"layer": "effect"` (with `"clear_queue": true` to empty the queue), `"show"` or `"all"` |
| `{"action": "list"}` | `{"animations": [{"name", "description", "keyframes", "loop"}], "currently_playing"}` |
| `{"action": "status"}` | `{"running", "animation", "show"}` where `show` is the `status_json` body |
| `{"action": "create", "animation": {...}}` | Save an animation (same format as the files in `light_prefs/animations`) |

### POST /NeewerLux/sequence

| Body | Effect |
|---|---|
| `{"action": "play", "name": "...", "start_ms": 0}` | Play a saved sequence |
| `{"action": "play", "sequence": {...}}` | Play one sent inline, without saving it |
| `{"action": "pause"}`, `{"action": "resume"}`, `{"action": "stop"}` | As on GET |
| `{"action": "seek", "ms": 65000}` | Jump |
| `{"action": "set_position", "ms": 65120}` | External clock sync; the reply says `"slew"` or `"jump"` |
| `{"action": "status"}` | The sequence part of `status_json` |
| `{"action": "list"}` | `{"sequences": [{"name", "duration_ms", "cues", "description"}]}` |
| `{"action": "reload"}` | Re-read `light_prefs/sequences`, then list |
| `{"action": "validate", "sequence": {...}}` | Check a sequence: `errors` and `warnings` |
| `{"action": "save", "sequence": {...}, "overwrite": false}` | Validate and save |
| `{"action": "render", "name": "...", "step_ms": 50, "start_ms": 0, "end_ms": 60000}` | What each light would do, without playing: per-light colour changes and the cue list |
| `{"action": "render", "name": "...", "format": "png", "width": 1600}` | The same as an image strip (`image/png`). Needs the desktop window; without it the reply is an error and the JSON render still works. |

The sequence format, targets, render output and timing rules are in [SEQUENCE_FORMAT.md](SEQUENCE_FORMAT.md).

### POST /NeewerLux/settings

| Body | Effect |
|---|---|
| `{"action": "get"}` | `{"apiVersion", "global": {...}, "lights": [...], "roles", "sides", "simulatedRigs"}` |
| `{"action": "set_light", "light": 0, "settings": {"role": "key", "maxBri": 60}}` | Change one light's preferences. `light` is the 0-based `index` from `get` (an ID, name or MAC also works). Settings: `customName`, `preferredID` (0 to 99, 0 = automatic), `tempRange` (`[min, max]` Kelvin), `cctOnly`, `role`, `side`, `order` (0 to 99, 0 = automatic), `eyeline`, `maxBri` and `minBri` (-1 = use the global limit, else 0 to 100), `locked`. Saved to the light's preferences file, as the desktop does. |
| `{"action": "set_global", "settings": {"envMaxBri": 80}}` | Change global preferences: `envMaxBri` (1 to 100), `envMinBri` (0 to 100), `seqFrameRate` (1 to 30), `effectMaxSeconds` (1 to 600), `globalCCTMin` and `globalCCTMax` (2700 to 8500), `cctFallbackMode` (`convert` or `ignore`), `simulatedLights` (0 to 4, next start), `simulatedCCTOnly` (next start). |

Every value in a request is checked before any is applied; a request with an invalid value changes nothing and lists the problems in `errors`. Network access, keyboard shortcuts and startup options can't be changed over HTTP. Changes show up in the desktop window straight away.

## Changes by API version

**2** (NeewerLux 1.3.3): `apiVersion` and `version` fields; structured per-light state and `sequences` in `list_json`; JSON batch `temp` accepts Kelvin; light commands are coalesced per light instead of answered with "Server is busy"; POST batch stops an override animation like GET commands do. Also part of this version, from 1.3.1 and 1.3.2: layers, sequences, `status_json`, `stop_layer`, `/NeewerLux/sequence` and `/NeewerLux/settings`.

**1** (NeewerLux 1.3.0 and earlier): GET commands, `list_json` without state, POST batch with `temp` in hundreds of Kelvin only, POST animate.
