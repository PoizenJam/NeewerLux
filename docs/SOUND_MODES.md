# Sound modes

A sound mode makes lights follow whatever is playing, live: game audio, music, a mix. NeewerLux listens to an audio device, analyses the sound as it arrives, and a sound mode turns that analysis into light, aimed at lights by role or position. Sound modes are saved as JSON files in `light_prefs/sound_modes/`, one per file, like animations and sequences, so you can copy a shipped one and make your own.

Sound modes need the optional audio packages (`uv sync --group audio`, already included in the Windows download). Without them the feature is hidden.

## Where the sound comes from

By default NeewerLux listens to whatever your computer's default output is playing (Windows loopback capture: no cable or virtual device needed), and follows the default if you change it. You can pick any other output to listen to, or any input instead (a microphone, an audio interface's inputs or its own loopback channel). The choice is remembered.

## How it plays

A sound mode runs on its own **sound** layer, underneath everything else:

- Sequences, stream effects and animations play over it on the lights they drive, and give those lights back to it when they end, with their Fade back. A song's sequence starting while a sound mode runs takes over the lights it uses; when it ends, the sound mode carries on.
- Lights a mode doesn't aim at stay as they are. The shipped modes leave the key light alone.
- A mode can also be put on chosen lights only (**On selected** on the desktop, **On target lights** on the web, `lights` over HTTP, or a preset). Those lights leave whatever sound they followed and the rest carry on, so different lights can follow different modes at once. A light given to a mode follows the first part whose target includes it, or the first part if none does; a chase steps through the lights it was given in sweep order.
- Recalling a preset, moving a slider or sending a colour to a light that follows sound takes that light out of the sound layer: what you just set shows at once, and the other lights carry on. When no lights are left, sound stops (and stops listening). Commands to lights that don't follow sound leave it playing.
- Switching a light off works whatever is playing: it takes that light out of the sound layer (or a sequence or effect) until you switch it on again, and the others carry on. A light that is off when a sound mode, sequence or effect takes it is switched on first.
- Brightness limits, Locked lights and the CCT-only fallback apply as for everything else.
- Starting a sound mode uses its Fade in (else the global one); stopping it hands the lights back with its Fade back (else the global one). Switching to another mode fades between them the same way.
- A sound mode keeps each light to at most 2 flashes in any second by itself (the flash guard's limit is 3), so it swells and steps rather than strobes. It judges swings twice, as if the light were white (so a CCT-only light showing a colour as white stays within the limit) and on the light's real colour (so a colour step at the same brightness, yellow to blue, counts too).
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
| `tags` | no | list of words | What the mode is like, shown under its description and used by draft styles to pick fitting modes. Shipped modes carry one energy (`calm`, `lively`, `intense`) and one feel (`smooth`, `punchy`, `hard`), plus colour words (`neon`, `warm`, `cool`, `white`, `rainbow`, `pastel`, `moody`, `colourful`, `retro`) and `chase` for chases. Any words can be used. |
| `sensitivity` | no | 0.1 to 5 (1) | Multiplies the analysis values before they're used: above 1 reacts more, below 1 less. |
| `range_db` | no | 6 to 30 (18) | How far under the loudest recent moment counts as 0, in dB: the smaller, the further the lights swing for the same music. 30 uses the analysis as it is. |
| `floor` | no | 0 to 100 (10) | Brightness, percent, when the driving value is 0. When the sound stops, every light settles exactly here (a chase's lit light too), easing down at the `smoothing` speed. |
| `ceiling` | no | 0 to 100 (75) | Brightness at full. Not below `floor`. |
| `smoothing` | no | 0 to 1 (0.5) | How slowly lights fall back and colours drift: 0 is quick (about 0.1 s), 1 is slow (about 1.6 s). Rises are always quick (60 ms). |
| `fps` | no | 1 to 30 | Updates a second. Default: the Sequence frame rate in Global Preferences (20). |
| `palette` | no | list | Colours, either all `{"hue": 0-360, "sat": 0-100}` or all `{"temp": 2700-10000}` (Kelvin). Default: one blue. The parts pick from it (below). |
| `cycle_s` | no | seconds (20) | How long a part with colour `cycle` takes to go round the whole palette. At least 4, and at least one second per palette colour, so a cycle drifts rather than flashes. |
| `fade_in_ms`, `handback_fade_ms` | no | 0 to 10000 | This mode's Fade in and Fade back; without them the global ones apply. |
| `parts` | yes | list | What each group of lights does (below). Later parts win where they overlap. |

Each part:

| Field | Required | Values | Meaning |
|---|---|---|---|
| `target` | yes | light target | Which lights, as anywhere else: `@rim`, `@background.left`, `@back.high`, `1;3`, `@all`, joined with `;`. Listed in sweep order. |
| `drive` | no | `level` (default), `low`, `mid`, `high`, `beat` | What sets the brightness. `beat` jumps to full on each beat and falls back by `smoothing`. |
| `colour` | no | palette index (0), `cycle`, `beat`, `centroid` | A fixed palette colour; `cycle`: round the palette and back to its first colour over `cycle_s`, blending between colours (a palette of one colour goes once round the colour wheel, keeping its saturation; one white stays put); `beat`: the next palette colour on each step, blended over 0.4 s; `centroid`: a colour along the palette set by the centroid (first entry for bass-heavy sound, last for bright). |
| `chase` | no | `true` / `false` (false) | Step through the part's lights one at a time on the beat (every other beat above 150 BPM): the current light rises, the others fall back. The brightest step scales with the level; in silence the lit light falls to the floor too. |
| `floor`, `ceiling` | no | 0 to 100 | This part's own brightness range. |

Hue blends take the short way round the colour wheel. Avoid palettes that cross saturated red (hues within 20 of 0) back and forth: changes to and from saturated red count as flashes.

## Saved palettes

Palettes can be saved on their own, in `light_prefs/palettes/` (`{"format": 1, "name": "Neon", "palette": [...]}`), and loaded into any mode: **Saved palettes** on the Sound tab and card, or by name in `start` and `set` over HTTP (`"params": {"palette": "Neon"}`). Loading one replaces the mode's colours in the working copy; Save keeps it in the mode. Shipped: Neon, Sunset, Ocean, Rainbow (red, green and blue, which `cycle` turns into a full rainbow) and Warm Whites.

## Shipped modes

62 modes ship, in three groups by feel. None drives the key light; Bands touches the fill only with pale, gentle highs. All stay at or under 2 flashes a second on every light, judged on their colours and as if white.

**Hard chases and blinks.** Smoothing 0 and floor 0: lights snap fully on and fully off. Each light still flashes at most twice a second.

| Mode | Tags | What it does |
|---|---|---|
| Background Chase | lively, hard, chase, cool | The background and practical lights chase hard on the beat; the rim follows the level smoothly. |
| Bass Floor | intense, hard, moody | The background slams on and off with the bass; the rim follows the level smoothly. |
| Beat Blink | intense, hard, neon | Every light on with each beat and off between, the colour stepping on each beat. |
| Hard Chase | intense, hard, chase, neon | Steps through the rim, background and practical lights on the beat, fully on then fully off, changing colour each step. |
| Hard Chase Amber | intense, hard, chase, warm | Hard Chase in ambers and golds, like stage lamps. |
| Hard Chase Cyan | intense, hard, chase, cool | Hard Chase in one colour: a single cyan light jumping round the room on the beat. |
| Hard Chase Ice | intense, hard, chase, cool | Hard Chase in pale icy blues. |
| Hard Chase Plus Glow | lively, hard, chase, neon | The rim chases hard on the beat while the background and practical lights glow with the level underneath. |
| Hard Chase Rainbow | intense, hard, chase, rainbow | Hard Chase whose colour moves round the whole colour wheel over 16 seconds. |
| Hat Blink | intense, hard, cool | Lights blink with the hi-hats and cymbals: quick and bright on busy tops, dark when they stop. |
| Hype | intense, hard, chase, neon | Everything at once: a hard chase on the rim, the background blinking with the kick, colours stepping on the beat. |
| Kick Blink | intense, hard, neon | Every light flashes on with the kick drum and snaps off between kicks, in magenta. |
| Kick Blink Duo | intense, hard, neon | Kick Blink in two colours: purple on the background, cyan on the rim and practical lights. |
| Metal Hits | intense, hard, cool | Cold white-blue blinks on every kick, with purple underneath on the background. |
| Split Blink | intense, hard, neon | The background blinks with the kick, the rim and practical lights with the hi-hats. |
| Stutter | intense, hard, neon | Hard on and off with the level, in violet and pink, for glitchy and broken beats. |
| Treble Top | lively, hard, cool | The rim and practical lights snap with the treble over a smooth background wash. |
| White Chase | intense, hard, chase, white | White only (5600 K): Hard Chase for colour-temperature lights. |

**Chases and pulses.** Quick, punchy movement with some smoothing.

| Mode | Tags | What it does |
|---|---|---|
| Bass Pulse | lively, punchy, moody | Brightness swells with the bass, in deep purple. |
| Beat Chase | lively, punchy, chase, neon | Steps through the rim, background and practical lights in sweep order on the beat, changing colour each step (every other beat above 150 BPM). |
| Beat Colours | lively, punchy, neon | Brightness follows the level; the colour steps to the next neon colour on every beat. |
| Boss Fight | intense, punchy, moody | Purple and orange, punchy on loud hits: big and dramatic. |
| Club Steps | lively, punchy, neon | The background cycles slowly through club colours while the rim steps on the beat. |
| Disco | intense, punchy, retro | Yellow, magenta and cyan, brightness on the beat and the colour stepping with it. |
| Double Pulse | lively, punchy, neon | Bass on the background, mids on the rim and practical lights, in two colours. |
| Eerie | calm, punchy, moody | Sickly greens and a little violet, twitching with the sound: horror and suspense. |
| Ember Pulse | lively, punchy, warm | Bass swells in deep orange and amber. |
| Firelight | calm, punchy, warm | Ambers and oranges flickering with the sound, like a fire. |
| Heartbeat | lively, punchy, pastel | A pink glow that thumps with the kick and relaxes between. |
| Primary Steps | lively, punchy, colourful | Blue, green and yellow stepping on the beat, brightness with the level. |
| Punchy Pulse | intense, punchy, cool | Pulse with a fast response and a wide range: every hit shows. |
| Rainbow Steps | lively, punchy, rainbow | Red-free primaries stepping on the beat: green, blue, yellow. |
| Rock Stage | intense, punchy, warm | Warm amber and cool white, punchy on the hits, the colour changing on the beat, like a rock stage wash. |
| Synthwave Steps | lively, punchy, neon, retro | Hot pink, purple and cyan stepping on the beat. |
| Treble Sparkle | lively, punchy, cool | The rim and practical lights sparkle with the treble while the background follows the bass slowly. |

**Smooth.** Brightness follows the music smoothly: steady pulses, washes, drifts and slow cycles.

| Mode | Tags | What it does |
|---|---|---|
| Ambient | calm, smooth, cool | Teals and blues cycling over a minute and a half, gently following the level. |
| Aurora | calm, smooth, cool | Greens, teals and violet drifting like northern lights. |
| Bands | lively, smooth, colourful | Lows on the background, mids on the rim, highs on the fill (kept pale and gentle, since it lights your face). |
| Candlelight | calm, smooth, warm, white | White only, 2700 to 3200 K, dim and slow: a candle-warm room that barely notices the music. |
| Colour Drift | calm, smooth, cool | Colour follows the brightness of the sound (deep blues for bass-heavy passages, magentas for bright ones); brightness follows the level. |
| Cool White Pulse | lively, smooth, white, cool | White only at 6500 K, brightness following the level. |
| Cozy | calm, smooth, warm, pastel | Soft warm amber, low and slow. |
| Daylight Breathe | calm, smooth, white | White only, 4300 to 5600 K, gently breathing with the level. |
| Deep Ocean | calm, smooth, cool, moody | Deep blues that shift with the brightness of the sound. |
| Forest | calm, smooth, cool | Greens that move with the brightness of the sound. |
| Gold Pulse | lively, smooth, warm | Brightness follows the level in warm gold. |
| Green Pulse | lively, smooth, cool | Brightness follows the level in green. |
| Just Chatting | calm, smooth, pastel | Teal and lavender, very gentle: the room moves a little with background music. |
| Lava Lamp | calm, smooth, warm | Orange and magenta blobs of colour, slowly cycling. |
| Lo-fi | calm, smooth, pastel, retro | Faded pastels cycling slowly, soft brightness: lo-fi beats and study streams. |
| Low and High | lively, smooth, neon | Bass on the background in purple, treble on the rim and practical lights in cyan. |
| Midnight | calm, smooth, moody | Very dim blues, barely moving: the music in the background, not the lights. |
| Orange Glow | lively, smooth, warm | One warm orange, following the level. |
| Pulse | lively, smooth, moody | Brightness follows how loud it is, in one colour, on the rim, background and practical lights (key and fill stay as they are). |
| Slow Wash | calm, smooth, cool | Blues and teals cycling slowly round over a minute, the brightness breathing with the level. |
| Soft Pulse | calm, smooth, cool | A slow, narrow pulse: the lights breathe with the music rather than jump. |
| Split Drift | calm, smooth, colourful | The background drifts through cool colours while the rim drifts through warm ones. |
| Sunset Drift | calm, smooth, warm | Oranges, golds and pinks, warmer for bassy passages and pinker for bright ones. |
| Three Way | lively, smooth, colourful | Bass on the background, mids on the rim, treble on the practical lights. |
| Twilight | calm, smooth, moody | Dim purples and blues cycling slowly, for late-night sets. |
| Vapor Wash | calm, smooth, neon, retro | Pink, cyan and violet cycling: synthwave and vaporwave colours. |
| Warm Glow | calm, smooth, warm, white | White only, for colour-temperature lights: warm and dim when it's quiet or bass-heavy, a little brighter and cooler when it's bright. |

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

On the desktop, the **Sound** tab (after Scene): what to listen to (also in Global Preferences, Lights and shows), the mode, Start, On selected and Stop, sliders for sensitivity, range, floor, ceiling and smoothing, the palette with its cycle time and saved palettes, the lights each part drives and what drives them, live meters and the tempo, and Save, Save as, Revert and Delete. Changes show on the lights at once while that mode plays (on any lights), and are kept only when you save. Picking lights in the light list while on the Sound tab doesn't switch tabs or send them the sliders' colour. The web dashboard has the same **Sound** card.

If the device stops working (unplugged, a driver error), NeewerLux keeps trying it every 2 seconds and carries on by itself when it's back; Refresh lists the devices again and tries at once.

A snapshot preset can set lights following a sound mode: the **Sound** column in the preset editors (desktop and web), for single lights. The light's colour in the preset is what it returns to when sound stops; recalling the preset doesn't write that colour, since a write would take the light out of the sound layer. Saving a snapshot while sound plays saves the lights that follow it.

Over HTTP: `POST /NeewerLux/sound` with `start`, `stop`, `mode` (each with optional `lights`), `set` (change sensitivity, range, floor, ceiling, smoothing, palette, cycle_s, fps or parts while it plays, without saving; `mode` names which playing mode), `device`, `devices`, `status` (including the live levels, the tempo and which lights follow which mode), the file actions `list`, `get`, `save`, `delete`, `validate`, `reload`, and the palette actions `palettes`, `save_palette`, `delete_palette`; or `GET /NeewerLux/doAction?sound=start|Pulse`, `sound=start|Colour Drift|1;3`, `sound=stop|3`. See [HTTP_API.md](HTTP_API.md).
