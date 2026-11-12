# Sound modes

A sound mode makes lights follow whatever is playing, live: game audio, music, a mix. NeewerLux listens to an audio device, analyses the sound as it arrives, and a sound mode turns that analysis into light, aimed at lights by role or position. Sound modes are saved as JSON files in `light_prefs/sound_modes/`, one per file, like animations and sequences, so you can copy a shipped one and make your own.

Sound modes need the optional audio packages (`uv sync --group audio`, already included in the Windows download). Without them the feature is hidden.

## Where the sound comes from

By default NeewerLux listens to whatever your computer's default output is playing (Windows loopback capture: no cable or virtual device needed), and follows the default if you change it. You can pick any other output to listen to, or any input instead (a microphone, an audio interface's inputs or its own loopback channel). The choice is remembered.

## How it plays

A sound mode runs on its own **sound** layer, underneath everything else:

- Sequences, stream effects and animations play over it on the lights they drive, and give those lights back to it when they end, with their Fade back. A song's sequence starting while a sound mode runs takes over the lights it uses; when it ends, the sound mode carries on.
- Lights a mode doesn't aim at stay as they are. The shipped modes leave the key light alone.
- Recalling a preset, moving a slider or sending a colour to one of the lights a sound mode drives stops the sound mode: what you just set takes over at once, and its other lights fade back. Commands to lights it doesn't drive leave it playing.
- Switching a light off works whatever is playing: it takes that light out of the sound mode (or a sequence or effect) until you switch it on again, and the others carry on. A light that is off when a sound mode, sequence or effect takes it is switched on first.
- Brightness limits, Locked lights and the CCT-only fallback apply as for everything else.
- Starting a sound mode uses its Fade in (else the global one); stopping it hands the lights back with its Fade back (else the global one). Switching to another mode fades between them the same way.
- A sound mode keeps each light to at most 2 flashes in any second by itself (the flash guard's limit is 3), so it swells and steps rather than strobes. It judges brightness swings as if the light were white, so a CCT-only light showing a colour as white stays within the limit too.
- It writes to a light only when what it shows changes enough to see, at most `fps` times a second.

## The analysis

Every 21 ms or so NeewerLux measures:

| Value | Range | What it is |
|---|---|---|
| `level` | 0 to 1 | How loud it is, against the loudest of the last few seconds, on a decibel scale (30 dB below that peak reads as 0). Quiet and loud material both use the whole range; silence is 0. |
| `low`, `mid`, `high` | 0 to 1 | The same for the bass (below 250 Hz), the middle (250 Hz to 4 kHz) and the treble (above 4 kHz). |
| `centroid` | 0 to 1 | How bright the sound is: low for bass-heavy sound, high for cymbals and hiss (the spectral centroid, 150 Hz to 6 kHz on a log scale). |
| beats | | A tempo estimate (60 to 200 BPM) and a beat clock that keeps time through short gaps and stops in silence. |

## The file

```json
{
  "format": 1,
  "name": "Pulse",
  "description": "Brightness follows how loud it is.",
  "sensitivity": 1.0,
  "floor": 15,
  "ceiling": 70,
  "smoothing": 0.5,
  "palette": [{"hue": 265, "sat": 85}],
  "parts": [
    {"target": "@rim;@background;@practical", "drive": "level", "colour": 0}
  ]
}
```

| Field | Required | Values | Meaning |
|---|---|---|---|
| `format` | no | `1` | File format version. |
| `name` | yes | text | Shown in the lists; also the file name. |
| `description` | no | text | Shown as a tooltip. |
| `sensitivity` | no | 0.1 to 5 (1) | Multiplies the analysis values before they're used: above 1 reacts more, below 1 less. |
| `range_db` | no | 6 to 30 (18) | How far under the loudest recent moment counts as 0, in dB: the smaller, the further the lights swing for the same music. 30 uses the analysis as it is. |
| `floor` | no | 0 to 100 (10) | Brightness, percent, when the driving value is 0 (silence settles here). |
| `ceiling` | no | 0 to 100 (75) | Brightness at full. Not below `floor`. |
| `smoothing` | no | 0 to 1 (0.5) | How slowly lights fall back and colours drift: 0 is quick (about 0.1 s), 1 is slow (about 1.6 s). Rises are always quick (60 ms). |
| `fps` | no | 1 to 30 | Updates a second. Default: the Sequence frame rate in Global Preferences (20). |
| `palette` | no | list | Colours, either all `{"hue": 0-360, "sat": 0-100}` or all `{"temp": 2700-10000}` (Kelvin). Default: one blue. |
| `fade_in_ms`, `handback_fade_ms` | no | 0 to 10000 | This mode's Fade in and Fade back; without them the global ones apply. |
| `parts` | yes | list | What each group of lights does (below). Later parts win where they overlap. |

Each part:

| Field | Required | Values | Meaning |
|---|---|---|---|
| `target` | yes | light target | Which lights, as anywhere else: `@rim`, `@background.left`, `@back.high`, `1;3`, `@all`, joined with `;`. Listed in sweep order. |
| `drive` | no | `level` (default), `low`, `mid`, `high`, `beat` | What sets the brightness. `beat` jumps to full on each beat and falls back by `smoothing`. |
| `colour` | no | palette index (0), `centroid`, `beat` | A fixed palette colour; a colour along the palette set by `centroid` (first entry for bass-heavy sound, last for bright); or the next palette colour on each step, blended over 0.4 s. |
| `chase` | no | `true` / `false` (false) | Step through the part's lights one at a time on the beat (every other beat above 150 BPM): the current light rises, the others fall back. The brightest step scales with the level. |
| `floor`, `ceiling` | no | 0 to 100 | This part's own brightness range. |

Hue blends take the short way round the colour wheel. Avoid palettes that cross saturated red (hues within 20 of 0) back and forth: changes to and from saturated red count as flashes.

## Shipped modes

| Mode | What it does |
|---|---|
| Pulse | Brightness follows the level, in one colour, on the rim, background and practical lights. |
| Bands | Lows on the background, mids on the rim, highs on the fill (pale and gentle, since the fill lights your face). |
| Beat Chase | Steps through the rim, background and practical lights in sweep order on the beat, changing colour each step. |
| Colour Drift | Colour follows the centroid (blues for bass-heavy sound, magentas for bright), brightness the level. |
| Warm Glow | White only, 2900 to 4300 K, for colour-temperature lights: warm and dim when it's quiet, brighter and cooler when it's bright. |

A second example, the shipped Bands:

```json
{
  "format": 1,
  "name": "Bands",
  "sensitivity": 1.0,
  "floor": 10,
  "ceiling": 75,
  "smoothing": 0.4,
  "palette": [{"hue": 270, "sat": 90}, {"hue": 200, "sat": 90}, {"hue": 45, "sat": 25}],
  "parts": [
    {"target": "@background", "drive": "low", "colour": 0},
    {"target": "@rim", "drive": "mid", "colour": 1},
    {"target": "@fill", "drive": "high", "colour": 2, "floor": 30, "ceiling": 50}
  ]
}
```

## Controlling it

On the desktop, the **Sound** tab: what to listen to (also in Global Preferences, Lights and shows), the mode, Start and Stop, sliders for sensitivity, range, floor, ceiling and smoothing, the palette, the lights each part drives and what drives them, live meters and the tempo, and Save, Save as, Revert and Delete. Changes show on the lights at once while that mode plays, and are kept only when you save. The web dashboard has the same **Sound** card.

Over HTTP: `POST /NeewerLux/sound` with `start`, `stop`, `mode`, `set` (change sensitivity, range, floor, ceiling, smoothing, palette, fps or parts while it plays, without saving), `device`, `devices`, `status` (including the live levels and tempo) and the file actions `list`, `get`, `save`, `delete`, `validate`, `reload`; or `GET /NeewerLux/doAction?sound=start|Pulse`. See [HTTP_API.md](HTTP_API.md).
