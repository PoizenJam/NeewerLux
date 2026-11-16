# NeewerLux sequence format (format 1)

A sequence is a timed light show: a list of cues, each starting at a fixed time and
driving some of the lights. Sequences are meant to be written by hand, by the timeline
editor (on the desktop and in the web dashboard), or generated per song by a program or an AI model. This document is the
complete contract: anything that follows it plays, and anything that breaks it is
rejected with an error message naming the cue and field.

## Where sequences live and how they play

- Saved sequences are JSON files in `light_prefs/sequences/`, one sequence per file. The
  file name doesn't matter; the `name` field does. Names are matched case-insensitively.
- Play one from the Sequences tab, or over HTTP (see the end of
  this document). A sequence can also be sent inline with a play request and is then
  never saved.
- Before saving or playing a generated sequence, send it to the validate action:
  `POST /NeewerLux/sequence` with `{"action": "validate", "sequence": {...}}`. The reply
  lists `errors` (the sequence won't play) and `warnings` (it will, but something looks
  wrong, such as a target that matches no connected light).

## Top level

| Field | Required | Type and range | Meaning |
|---|---|---|---|
| `format` | no | `1` | Format version. Omit or set to 1. |
| `name` | yes | string | Unique name. Saving over an existing name needs `"overwrite": true`. |
| `duration_ms` | yes | integer, 1 to 86400000 | Length of the sequence. Cues starting at or after it never play. |
| `cues` | yes | non-empty list | See below. Order doesn't matter; timing comes from `at_ms`. |
| `fps` | no | integer, 1 to 30 | Updates per second during fades and clips. Default: the Sequence frame rate in Global Preferences (20). Cue starts are not rounded to frames. |
| `end` | no | `"revert"`, `"hold"` or `"preset:N"` | What the lights do at the end. `revert` (default): back to the state they were in before the sequence started, usually a preset. `hold`: stay on the last frame. `preset:3`: recall preset 3. |
| `pause_mode` | no | `"revert"` or `"freeze"` | While paused: `revert` (default) puts the lights back to their pre-sequence state and resumes the show exactly where it stopped; `freeze` holds the current frame. |
| `fade_in_ms` | no | integer, 0 to 10000 | How long the lights take to fade into the sequence when it starts. The sequence holds its first frame for that long, then plays from `start_ms` with its cues exactly as written (lights it picks up or drops later follow their cues, with no extra fade). Default: Fade in in Global Preferences (0, a cut). |
| `handback_fade_ms` | no | integer, 0 to 10000 | How long the lights take to fade back when this sequence lets go of them (when it ends, stops or pauses with `revert`). Default: Fade back in Global Preferences (500 ms). 0 cuts. |
| `on_interrupt` | no | `"continue"` or `"pause"` | While an effect or override animation is playing: `continue` (default) keeps the sequence clock running underneath, so lights rejoin in sync with the song; `pause` stops the clock until the interruption ends. |
| `description`, `artist`, `song`, `notes` | no | string | Shown in lists or ignored; `artist` and `song` also find the sequence for play by artist and song. A draft from a song fills them in from the file's tags or its `Artist - Title` file name. |
| `tempo` | no | `{"bpm": number, "offset_ms": integer}` | Written by the timeline editor so it can draw beat lines and snap cues to beats (`offset_ms` is when the first beat falls). Playback ignores it: cue times are always plain milliseconds. |
| `sections` | no | list of `{"start_ms", "end_ms", "label", "level", "group", "kind"}` | Song sections (from a song draft, or written by hand; `group` is optional: sections with the same letter are the same part of the song repeating; `kind` is optional: NeewerLux's name when `label` is another section finder's). The timeline editors draw them above the ruler, coloured by `level` (1 quiet, 2 medium, 3 loud), and Change tempo moves them with the cues. Playback ignores them. |
| `palette` | no | any | Reserved for a later version (palette slots). Accepted and ignored now. |

## Cues

| Field | Required | Type and range | Meaning |
|---|---|---|---|
| `at_ms` | yes (defaults to 0) | integer, 0 or more | When the cue starts, in ms from the start of the sequence. |
| `target` | no | string, default `"*"` | Which lights. See Targets. |
| `state` | one of `state`, `clip` or `sound` | object | Set a colour, optionally with a fade. |
| `clip` | one of `state`, `clip` or `sound` | object or string | Play an existing animation, stretched or looped to fill the cue. |
| `sound` | one of `state`, `clip` or `sound` | object or string | Hand the lights to a sound mode for the cue's length: they follow live sound. See Sound cues. |
| `duration_ms` | clip and sound: yes; state: no | integer | Clip: how long the clip plays (1 or more). Sound: how long the lights follow the sound mode (1 or more). State: 0 or omitted means hold until a later cue changes that light; a positive value ends the cue after that long, and the light goes back to the look it had before the cue (or its pre-sequence state). |
| `palette` | no | any | Reserved (per-cue palette override). Ignored now. |
| `label`, `comment` | no | string | Ignored; useful for people reading the file. |

### State cues

```json
{"at_ms": 0, "target": "@fill", "state": {"mode": "HSI", "hue": 280, "sat": 100, "bri": 60, "fade_ms": 1500}}
{"at_ms": 0, "target": "@key", "state": {"mode": "CCT", "temp": 45, "bri": 70}}
```

| Field | Mode | Range | Default |
|---|---|---|---|
| `mode` | both | `"HSI"` or `"CCT"` | required |
| `hue` | HSI | 0 to 360 degrees | 0 |
| `sat` | HSI | 0 to 100 | 100 |
| `bri` | both | 0 to 100 (percent) | 100 |
| `temp` | CCT | 32 to 85, in hundreds of kelvin (56 = 5600K) | 56 |
| `fade_ms` | both | 0 or more | 0 |

A fade starts from whatever the light was showing in this sequence just before the cue
(or, for the first cue on a light, the state it had before the sequence started) and runs
at the sequence's `fps`. Hue fades take the short way round the colour wheel. A fade
between HSI and CCT can't blend, so the light switches at the start of the cue.

Each light's own limits still apply on top: its colour temperature range, its brightness
ceiling and floor (Light Preferences, or the global defaults), and whether it can only do
CCT (HSI cues are converted or skipped for those lights, per Global Preferences).

### Clip cues

```json
{"at_ms": 12000, "duration_ms": 8000, "target": "@all", "clip": {"name": "Color Chase", "fit": "loop", "speed": 1.5, "brightness": 70}}
{"at_ms": 30000, "duration_ms": 4000, "target": "@rim", "clip": "Heartbeat"}
```

| Field | Range | Default | Meaning |
|---|---|---|---|
| `name` | an existing animation | required | Case-insensitive. A bare string is shorthand for `{"name": ...}`. |
| `fit` | `"stretch"` or `"loop"` | `"stretch"` | `stretch`: one pass of the animation is stretched or squeezed to exactly `duration_ms`. `loop`: the animation plays at its own speed (times `speed`) and repeats until `duration_ms` ends. |
| `speed` | 0.05 to 20 | 1 | Playback speed, `loop` only. |
| `brightness` | 0 to 100 | 100 | Scales every brightness in the clip. |

The list of animation names comes from `POST /NeewerLux/animate` with
`{"action": "list"}`, or `GET /NeewerLux/doAction?list_animations`. Inside sequences, clips
play with exact keyframe timing and continuous fades sampled at the sequence `fps`.
Animation files can also set `fade_in_ms` and `handback_fade_ms` (the same meanings, for when the
animation takes lights and lets them go); clips inside a sequence use the sequence's fades instead.
Animations played on their own also use exact keyframe timing (since 1.3.3; before, holds
were rounded down to 50 ms), with fades moving in steps at the animation's rate.

How a clip's lights map onto the target: animations name their lights `*`, `1`, `2`, `3`,
`4` and so on. In a clip, `*` means every light in the target, and the numbers are
positions within the target: `1` is the first target light, `2` the second. An `@` target
is in sweep order; a list such as `@fill;@rim` is in the order written.
If the target has more lights than the clip has numbers, the numbers repeat (a 2-light
clip on 4 lights gives 1, 2, 1, 2). If it has fewer, the extra numbers go unused. A clip
key that names a specific light (a name, MAC address or `@role`) only applies if that
light is inside the target.

### Sound cues

A sound cue hands its lights to a sound mode (see SOUND_MODES.md) for its `duration_ms`,
then lets the next cue take over. `sound` is a mode name, or an object with `mode` (the
name) and any of the mode's values to change for this cue: `sensitivity`, `range_db`,
`floor`, `ceiling`, `smoothing`, `curve`, `palette` (a list of colours or a saved
palette's name), `cycle_s`, `fps` and `parts`.

```json
{"at_ms": 32000, "duration_ms": 16000, "target": "@rim;@background;@practical", "sound": {"mode": "Hard Chase", "palette": "Neon"}}
```

The cue plays inside the sequence: no Fade in or Fade back at its edges (as for any cue),
and a state cue with a fade after it fades from the last thing the sound mode showed. A
light the cue covers follows the first part of the mode whose target includes it, or else
the mode's first part, so a mode's parts can still split the cue's lights (bass on the
background, treble on the rim). While a sequence with sound cues plays, NeewerLux listens
on the sound device chosen for sound modes, and stops listening when it ends (unless a
sound mode is playing). The mode keeps itself under 2 flashes a second, and the flash
guard still applies.

A render can't hear the song, so in renders (and the timeline editors' previews, which
come from a render) a sound cue's mode reacts to a steady beat instead: a kick on every beat
and a hi-hat between, at the sequence's `tempo` (120 BPM without one). Its lights are
marked `"sound"` as their source and hatched in the render image and the editors, since
the real show follows whatever is playing.

### Which cue wins

For each light, at each moment, the cue that started most recently (latest `at_ms`; ties
go to the later cue in the list) and is still active drives the light. A state cue with
no `duration_ms` stays active until the end of the sequence, so it acts as the light's
"current look": a later clip plays over it, and when the clip ends the light goes back to
that look. A light no active cue covers isn't driven by the sequence and shows its
pre-sequence state.

## Targets

A target is one or more of these, separated by `;`. The result is the union, in the
order written (`@fill;@background;@rim` puts the fill first, which matters for clips):

| Target | Lights |
|---|---|
| `*` or `all` | every light, in discovery order |
| `1`, `2`, ... | a light by number (its Preferred ID if set, otherwise its row) |
| `Key Light` | a light by its custom name |
| `D0:A8:9E:6B:20:84` | a light by MAC address |
| `@key`, `@fill`, `@rim`, `@background`, `@practical` | lights with that role (Light Preferences). Lights without a role count as background. Rim is also called a back or hair light; a practical is a light that is visible in shot. |
| `@left`, `@centre` (or `@center`), `@right` | lights on that side: the streamer's left and right, facing the camera |
| `@front`, `@beside`, `@back` | lights at that depth: between the streamer and the camera, level with them, behind them |
| `@low`, `@middle`, `@high` | lights at that height |
| `@eyeline` | lights flagged as being in the streamer's eye line |
| `@all` | every light, in sweep order |
| `@rim.left` | intersection: rim lights on the left. Any roles, sides, depths, heights and `eyeline` can be combined with dots: `@back.left.high`. |

`@` targets list lights in sweep order (Light Preferences, Sweep order; Auto sorts by position,
left to right, then front to back, then low to high, then by ID),
which is what makes `Color Chase` on `@all` travel left to right if sweep order is set that
way. Prefer roles over numbers in generated sequences: they survive lights being
renumbered or replaced.

## Generating sequences (guidance for programs and AI models)

- Output one JSON object exactly as specified. No comments, no trailing commas.
- Times are integer milliseconds from the start of the song. If you have song sections
  with start and end times (as RockSniffer provides), start cues at section starts and
  size clips to section lengths.
- Set a base look first: a state cue at `at_ms` 0 on `*` or on each role, with no
  `duration_ms`, so every light is driven from the start.
- Use `@key` sparingly and dimly, or not at all: the key light is usually on the
  streamer's face, may be Locked (Locked lights ignore sequences and effects entirely), and
  has a brightness ceiling. The same goes for `@eyeline`.
- Use clips for movement (chases, pulses, strobes) and state cues with fades for colour
  changes. Prefer animation names from the list endpoint; unknown names are errors.
- NeewerLux does not limit flashing. For viewers with photosensitive epilepsy, follow
  WCAG 2.3.1: no more than three flashes (a bright-dark pair counts as one) per second
  when the swing is more than about 10 brightness points, and avoid rapid alternation
  involving saturated red.
- Validate with the validate action and fix every error before saving.
- Then render it (below) and look at the result: long stretches where nothing changes,
  lights that never get a cue, or the key light swinging around are easy to spot in the
  data, and easier still in the image strip if you can read images.

### JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "NeewerLux sequence, format 1",
  "type": "object",
  "required": ["name", "duration_ms", "cues"],
  "properties": {
    "format": {"const": 1},
    "name": {"type": "string", "minLength": 1},
    "duration_ms": {"type": "integer", "minimum": 1, "maximum": 86400000},
    "fps": {"type": "integer", "minimum": 1, "maximum": 30},
    "end": {"type": "string", "pattern": "^(revert|hold|preset:[1-9][0-9]*)$"},
    "pause_mode": {"enum": ["revert", "freeze"]},
    "on_interrupt": {"enum": ["continue", "pause"]},
    "fade_in_ms": {"type": "integer", "minimum": 0, "maximum": 10000},
    "handback_fade_ms": {"type": "integer", "minimum": 0, "maximum": 10000},
    "description": {"type": "string"},
    "artist": {"type": "string"},
    "song": {"type": "string"},
    "notes": {"type": "string"},
    "tempo": {},
    "palette": {},
    "sections": {},
    "cues": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["at_ms"],
        "properties": {
          "at_ms": {"type": "integer", "minimum": 0},
          "duration_ms": {"type": "integer", "minimum": 0},
          "target": {"type": "string", "minLength": 1},
          "palette": {},
          "label": {"type": "string"},
          "comment": {"type": "string"},
          "state": {
            "type": "object",
            "required": ["mode"],
            "properties": {
              "mode": {"enum": ["HSI", "CCT"]},
              "hue": {"type": "integer", "minimum": 0, "maximum": 360},
              "sat": {"type": "integer", "minimum": 0, "maximum": 100},
              "bri": {"type": "integer", "minimum": 0, "maximum": 100},
              "temp": {"type": "integer", "minimum": 32, "maximum": 85},
              "fade_ms": {"type": "integer", "minimum": 0}
            }
          },
          "sound": {
            "oneOf": [
              {"type": "string", "minLength": 1},
              {"type": "object", "required": ["mode"], "properties": {"mode": {"type": "string", "minLength": 1}}}
            ]
          },
          "clip": {
            "oneOf": [
              {"type": "string", "minLength": 1},
              {
                "type": "object",
                "required": ["name"],
                "properties": {
                  "name": {"type": "string", "minLength": 1},
                  "fit": {"enum": ["stretch", "loop"]},
                  "speed": {"type": "number", "minimum": 0.05, "maximum": 20},
                  "brightness": {"type": "integer", "minimum": 0, "maximum": 100}
                }
              }
            ]
          }
        },
        "oneOf": [
          {"required": ["state"]},
          {"required": ["clip", "duration_ms"]},
          {"required": ["sound", "duration_ms"]}
        ]
      }
    }
  }
}
```

The validator also checks that each clip names an existing animation and each sound cue
an existing sound mode (with values in range), which a schema can't, and treats a clip or
sound `duration_ms` of 0 as an error.

### Example

A 40-second demo for a four-light rig (front right key, front left fill, rear right rim,
rear left background). It ships as `light_prefs/sequences/Example - Four Light Demo.json`.

```json
{
  "format": 1,
  "name": "Example - Four Light Demo",
  "description": "40 s demo: warm intro, colour build, chase, rim pulses, calm ending",
  "duration_ms": 40000,
  "fps": 20,
  "end": "revert",
  "cues": [
    {"at_ms": 0, "target": "@key", "state": {"mode": "CCT", "temp": 45, "bri": 55, "fade_ms": 1000}, "label": "key stays a soft, steady white"},
    {"at_ms": 0, "target": "@fill;@background;@rim", "state": {"mode": "CCT", "temp": 35, "bri": 30, "fade_ms": 2000}},
    {"at_ms": 4000, "target": "@fill", "state": {"mode": "HSI", "hue": 280, "sat": 90, "bri": 45, "fade_ms": 3000}},
    {"at_ms": 4000, "target": "@background", "state": {"mode": "HSI", "hue": 200, "sat": 90, "bri": 45, "fade_ms": 3000}},
    {"at_ms": 6000, "target": "@rim", "state": {"mode": "HSI", "hue": 320, "sat": 100, "bri": 60, "fade_ms": 2000}},
    {"at_ms": 12000, "duration_ms": 10000, "target": "@fill;@background;@rim", "clip": {"name": "Color Chase", "fit": "loop", "speed": 1.0, "brightness": 70}, "label": "chase over the three colour lights"},
    {"at_ms": 22000, "target": "@fill;@background", "state": {"mode": "HSI", "hue": 30, "sat": 100, "bri": 50, "fade_ms": 1500}},
    {"at_ms": 24000, "duration_ms": 6000, "target": "@rim", "clip": {"name": "Heartbeat", "fit": "loop", "brightness": 80}},
    {"at_ms": 32000, "target": "@fill;@background;@rim", "state": {"mode": "CCT", "temp": 35, "bri": 25, "fade_ms": 4000}, "label": "calm ending before revert"}
  ]
}
```

## Drafting from a song

**From song...** on the Sequences tab (desktop) or **From song** on the dashboard's Sequences card analyses a song file and drafts a sequence for it; over HTTP it's the `analyze` and `draft` actions (and `POST /NeewerLux/song` for uploads), see [HTTP_API.md](HTTP_API.md). It needs the audio extras (numpy and soundfile) and reads WAV, FLAC, MP3, OGG and AIFF.

The analysis finds the length, the tempo and where the first beat falls (assuming a steady tempo, as most produced music has), the beat grid and bars, a loudness curve and sections: places where the sound changes, on bar lines, favouring 4- and 8-bar phrases, at least 4 and at most 32 bars long. Two kinds of change count: in loudness, bass, kick, treble, brightness and busyness, and in timbre and harmony (a new riff or chord loop at the same loudness, found by comparing every bar with every other). Sections that sound alike are the same part of the song coming back and share a `group` letter (A, B, C, in the order they first appear), so a draft can give a repeated part the same look. Each section gets a level from how loud, busy and kick-heavy it is compared with the rest of the song (1 quiet, 2 medium, 3 loud) and a suggested name, only a starting point. The names describe how sections compare within the song, as in electronic music, rather than loudness alone. **Drop** is the most intense part of the song with the kick in (and a slightly less intense repeat of it), so even a song that is loud throughout has one; **Build** rises into a Drop or something fuller (brighter and busier or louder towards its end, as a riser, filter sweep or drum roll is; the last bars of a longer section become a Build of their own when they rise like this); **Breakdown** has less than half the song's usual kick; **Intro** runs from the start until the beat comes in, and **Outro** from where it goes after the last fuller part to the end; anything else with the kick in is **Groove**. Hover over a section in the song view or the timeline editors to see its full name, times, length, part and level; names are drawn only where they fit.

**Another section finder (optional).** Global Preferences > Lights and shows > Song section finder command runs another program on each song to find its sections, such as an AI model you install yourself. NeewerLux doesn't include one: the one known to work, the All-In-One Music Structure Analyzer (`allin1`, MIT licence; installed in a Python environment of its own as its README describes), needs PyTorch and several gigabytes, takes a minute or more per song without a graphics card, and was trained on pop songs, so its labels are intro, verse, chorus, bridge and outro. Give the command line with `{song}` for the song's path and `{out}` for a folder it may write into, for example `C:\allin1\Scripts\allin1.exe "{song}" -o "{out}"`. It runs without a shell (the song's path is passed as one argument), in that folder, which is removed afterwards, for at most 10 minutes. It answers with JSON, on its output or in a `.json` file in the folder: a list of segments, or an object with `segments`, each with `start` and `end` in seconds (or `start_ms` and `end_ms`) and a `label`. Its boundaries are moved to the nearest bar line and its label is kept as the section's `ai_label` (shown on hover); tempo, beats, names, levels and parts still come from NeewerLux. With **Name sections with the section finder's labels** ticked, its label (capitalised) becomes the section's `label` instead, and NeewerLux's name is kept as `kind` (shown on hover), which draft styles go by. Untick **Use the section finder command** to go back to the built-in analysis without clearing the command. If it fails, the built-in sections are used and the reason is shown. The setting is on the desktop only, like the network settings, since it runs a program on the computer. If the beat ticks drawn over the waveform don't match the song, correct the tempo (x 1/2 and x 2 fix the commonest mistake, counting double or half the beats) and when the first bar falls; the sections move to the nearest bar line.

### Draft styles

A draft is shaped by a **draft style**: pick one in the From song dialog, or type genres (most important first, as a music database lists them, for example `thrash metal, metal`) and **Pick** chooses the style whose genres fit best. Over HTTP, `draft` takes `"style"` by name (or a whole style object), or `"genre"`/`"genres"` instead, and `style_for` answers which style fits some genres, so an outside program that looks up a song's artist can choose one.

The draft drives `@fill`, `@rim`, `@background` and `@practical` (only the roles the rig has; unassigned lights count as background), never `@key`. It sets `tempo` (offset on the first bar) and `sections`, and labels each section's first cue. Each section plays the behaviour its style gives its kind: the section's `kind` when it has one, else its label (`Intro`, `Groove`, `Build`, `Drop`, `Breakdown`, `Outro`; names from other section finders map across, verse to Groove, chorus to Drop, bridge to Breakdown; anything else counts as Groove). The behaviours:

| Behaviour | What it does |
|---|---|
| `fade_up` | Starts dark and fades up to the look over the section. |
| `fade_down` | Fades from the look down to dark by the section's end. |
| `hold` | One look for the section, arriving on its first beat. |
| `drift` | Dim, with slow colour changes every four bars. |
| `colour_bars` | A new colour every bar (every other bar below level 3); brightness follows the energy. |
| `pulse` | The rim pulses on the beat over a darker look (every beat at level 3, every other at level 2, none at level 1); colour changes every four bars. |
| `build` | Pulses on rim, background and practical every two bars, then every bar, half bar and beat, while the light rises, then a blackout on the last beat (the fill drops to its lowest). |
| `hit_chase` | Everything hits full on the first beat, then a chase across rim, background and practical, a new colour each bar. |
| `animation` | Plays an animation from the section's pool on the colour lights, looped at a speed (0.5 to 2) that makes one loop a whole number of beats. |
| `sound` | Hands the colour lights to a sound mode from the section's pool for the section (a sound cue), with the style's palette when the mode's parts fit it. |

A kind can list several behaviours: sections of that kind take them in turn, while a part that repeats (the same `group`) plays the same behaviour, colours and pool pick each time, so the song gets variety without the chorus changing look every time it returns. Brightness follows the song's energy bar by bar between the style's intensity limits (from the analysis's energy curve and the section's level). Pulses and chase steps never come faster than twice a second per light, animations are only drawn if they stay at or under 2 flashes a second at their speed (firmware scenes never), and sound modes keep themselves to 2; the tests draft every shipped style at 60 to 200 BPM and check every light stays at or under 2.5 (handing over between sections adds a little), with the flash guard's 3 as the backstop.

Styles are JSON files in `light_prefs/draft_styles/`, edited with **Styles...** in the From song dialog (desktop and dashboard) or over HTTP (`draft_styles`, `save_draft_style`, `delete_draft_style`). 26 ship: Subtle, Concert and Neon; Rock, Prog Rock, Metal, Punk, Pop, Ballad, Folk, Jazz, Classical, Hip Hop, Disco Funk; House, Techno, Trance, Drum and Bass, Dubstep, Synthwave, Ambient, Lo-fi; and for streams that aren't music, Just Chatting, Cozy, Horror and Hype. The format:

```json
{
  "format": 1,
  "name": "Metal",
  "description": "Blood red, fire and cold white at full intensity.",
  "genres": ["metal", "heavy metal", "thrash metal"],
  "palette": [{"hue": 355, "sat": 75}, {"hue": 25, "sat": 90}, {"hue": 210, "sat": 15}],
  "intensity": "high",
  "use_animations": true,
  "use_sound_modes": true,
  "sections": {
    "Groove": {"behaviour": ["pulse", "sound"], "sound_modes": {"tags": ["hard"]}},
    "Drop": {"behaviour": ["hit_chase", "sound"], "sound_modes": {"tags": ["hard"]}},
    "Breakdown": {"behaviour": "hit_chase"}
  }
}
```

| Field | Required | Value |
|---|---|---|
| `format` | no | 1 |
| `name` | yes | The style's name. |
| `description` | no | Shown under the style's name. |
| `genres` | no | Genres it suits, matched by Pick and `style_for` (exact names count most, then one containing the other, then shared words; the word "music" is ignored, so `electronic music` matches `electronic`). Generic electronic genres (`electronic`, `edm`, `dance`) pick House. |
| `palette` | yes | The name of a saved palette (`light_prefs/palettes/`), or a list of colours: all `{"hue", "sat"}` or all `{"temp"}` in Kelvin (3200 to 8500 in a sequence). Each section takes the next colours round it; the fill gets a pale version. |
| `intensity` | no | `low`, `medium` (default) or `high`: how bright the colour lights get (rim at most 45, 75 or 100%). |
| `use_animations`, `use_sound_modes` | no | `true` (default) or `false`: whether `animation` and `sound` behaviours may be used. When one can't (turned off, or nothing in its pool qualifies), the section takes the kind's other behaviours, or its default. |
| `sections` | no | Per kind (`Intro`, `Groove`, `Build`, `Drop`, `Breakdown`, `Outro`): `behaviour` (one or a list) and the pools `animations` and `sound_modes`. A kind left out uses its default: Intro `fade_up`, Groove `pulse`, Build `build`, Drop `hit_chase`, Breakdown `drift`, Outro `fade_down`. |

A pool is `{"tags": [...], "exclude": [...], "names": [...]}`: an animation or sound mode is in it when it has every tag in `tags` and none in `exclude`, or when `names` lists it (with `names` and no `tags`, only those). An empty pool allows everything. The shipped animations and sound modes are tagged with one energy (`calm`, `lively`, `intense`), one feel (`smooth`, `punchy`, `hard`) and colour words (`warm`, `cool`, `white`, `neon`, `colourful`, `rainbow`, `moody`, `pastel`, `retro`, and `chase` for chases), so a Ballad that asks for `calm` and excludes `hard` and `intense` can never draw a metal breakdown. The editors write a pool as one line: tags, `-tags` to exclude, and names, separated by commas (`calm, -warm, Heartbeat`), and show how many items it matches.

The draft opens unsaved in the timeline editor.

## Changing the tempo

**Change tempo...** in the timeline editor (Change tempo on the web) sets a new BPM and, when the sequence already has one, can move and stretch the cues so they stay on the same beats: every cue start, length and fade, the sections and the sequence length scale by the old tempo over the new one, measured from the first beat, and looping clips speed up or slow down by the same amount. It's one edit (undo puts it back) and only changes the file: playback still runs in real time.

## Controlling sequences

GET (Stream Deck, Streamer.bot "Fetch URL"; arguments are lowercased, names match
case-insensitively, and spaces in names must be sent as `%20`):

```
/NeewerLux/doAction?sequence=play|Example%20-%20Four%20Light%20Demo|0   name, optional start ms
/NeewerLux/doAction?sequence=pause
/NeewerLux/doAction?sequence=resume
/NeewerLux/doAction?sequence=stop
/NeewerLux/doAction?sequence=seek|65000                           jump to 65 s
/NeewerLux/doAction?sequence=position|65120                       sync: slews up to 5% for offsets up to 250 ms, jumps beyond
/NeewerLux/doAction?status_json                                   layers, effect queue, sequence position, layer per light
```

POST `/NeewerLux/sequence` (body up to 256 KB):

```
{"action": "play", "name": "Example - Four Light Demo", "start_ms": 0}
{"action": "play", "sequence": { ...a whole sequence... }}          inline, never saved
{"action": "pause"} / {"action": "resume"} / {"action": "stop"}
{"action": "seek", "ms": 65000}
{"action": "set_position", "ms": 65120}                             reply says "slew" or "jump"
{"action": "status"}
{"action": "list"}
{"action": "reload"}                                                re-reads light_prefs/sequences, then lists
{"action": "validate", "sequence": {...}}
{"action": "save", "sequence": {...}, "overwrite": false}
{"action": "render", "name": "...", "step_ms": 50, "start_ms": 0, "end_ms": 60000}
{"action": "render", "sequence": {...}, "format": "png", "width": 1600}
{"action": "analyze", "path": "C:\\Music\\Song.mp3"}                     tempo, beats, bars, energy, sections
{"action": "draft", "analysis": {...}, "style": "Concert", "name": "Song"}  a drafted sequence, saved with "save": true
```

### Following an outside clock

A program that knows where a song is (a game's song tracker, a DAW bridge, a media player plug-in) can drive a sequence: play it by name, or by `artist` and `song` (the fields in the file), with `watchdog_ms`, then send `set_position` with the song's position as it goes, a few times a second. Small differences are absorbed by running up to 5% fast or slow, large ones jump. When positions stop coming for `watchdog_ms` (the song was paused, or the program closed), the sequence pauses as Pause does and its state reads `waiting`; the next position carries on from there. Pause, Resume and Stop work as usual. Give such sequences Fade in 0, since a fade in delays the start. See `play` in [HTTP_API.md](HTTP_API.md). A play request can also set `brightness` (percent), scaling the whole show for that play: a song played late at night, say.

### Render

Render plays a sequence on a simulated clock against the lights NeewerLux currently has
(real or simulated) and reports what each light would show, without sending anything and
without waiting in real time. Each light's CCT-only fallback, brightness limits and Locked
flag are applied, and lights no cue covers show their current state, exactly as in
playback. Optional fields: `step_ms` (sampling interval, default one frame at the
sequence's `fps`), `start_ms` and `end_ms`.

The default JSON reply:

```
{"success": true, "sequence": "...", "duration_ms": 40000, "start_ms": 0, "end_ms": 40000, "step_ms": 50,
 "lights": [{"id": "1", "name": "Key Light", "role": "key", "side": "right", "depth": "front", "height": "middle", "locked": false, "simulated": false}, ...],
 "changes": {"1": [[0, "#ffd5b0", 55, "CCT", "sequence"], [32000, "#ffd5b0", 30, "CCT", "sequence"], ...], ...},
 "cues": [{"index": 0, "at_ms": 0, "duration_ms": 0, "target": "@key", "kind": "state", "what": "CCT 4500K 55%, fade 1000 ms", "label": "..."}, ...],
 "flashes": {"limit": 3, "worst": 2.0, "worstRed": 2.0, "lights": {"1": {"flashes": 0.5, "red": 0.0}, ...}},
 "warnings": []}
```

`flashes` is the most flashes any light makes in any one second (`worst` for big brightness
changes, `worstRed` for changes to and from saturated red), checked before the flash guard. If
either is over `limit`, the flash guard (on by default) will hold some changes back during
playback, so the show won't look as written. Generated sequences should stay at or under it.

Each change is `[time_ms, colour, brightness, mode, source]`, listed only when something
changes; `source` is `sequence` when a cue drives the light and `base` when it shows its
pre-sequence state. Colours are approximate screen colours (brightness included), meant
for judging a show, not for colour matching.

`"format": "png"` returns the same render as an image strip, one row per light with cue
starts marked. The image needs the NeewerLux window running; a headless `--http` install
returns an error saying so and the JSON form still works.

## Effects and other animations on top of a sequence

Animations can play on three layers. Each light follows the highest layer that is
driving it; lower layers keep running underneath, and when a higher layer lets go of a
light (it ends, or a sequence reverts on pause), the light goes back to the lower layer's
current frame with the Fade back of the item that let go (0 cuts).

| Layer | What it's for | Behaviour |
|---|---|---|
| override (highest) | the Stream Deck pedal, the GUI Play button, every `animate` URL without a layer | One at a time, as in v1.3.0: a new one replaces the old, and "Revert on finish" (the global setting, which the `revert` field still changes) decides whether lights go back afterwards. |
| effect | channel point redeems, bits, subs, raids: anything Streamer.bot triggers | Queued (up to 10 waiting) or `replace` to cut in. Forever-looping effects stop after the Looping effect time limit (default 30 s). `revert` applies to that request only. |
| show | sequences, or an animation used as a background look | One at a time. |
| sound | a sound mode following live audio ([SOUND_MODES.md](SOUND_MODES.md)); not for animations | One mode, or several on different lights. A bed under everything: a song's sequence takes the lights it uses and gives them back when it ends. |

Below them all is the base layer: the sliders, presets and plain `mode=` commands. While
a sequence or effect drives a light, a base change to that light doesn't show; it becomes
the state the light returns to when the sequence or effect lets go. Locked lights always
show the base layer.

NeewerLux doesn't know what triggered an animation; the layer and queue mode come from
the request, so each Streamer.bot action picks them:

```
/NeewerLux/doAction?animate=Strobe|1|10|100|true|5||effect||@rim        effect layer, queued, rim lights only
/NeewerLux/doAction?animate=Police%20Flash|1|10|100|true|3||effect|replace   cut in ahead of the queue
/NeewerLux/doAction?stop_layer=effect                                     stop the current effect (the queue moves on)
/NeewerLux/doAction?stop_layer=effect_all                                 stop it and clear the queue
/NeewerLux/doAction?stop_layer=override                                   same as stop_animate
/NeewerLux/doAction?stop_layer=show                                       stop whatever is on the show layer, including a sequence
/NeewerLux/doAction?stop_layer=all                                        stop all three layers and clear the queue
```

The `animate` value is `Name|speed|rate|brightness|loop|maxLoops|revert|layer|queue|target`;
every field after the name is optional, and empty fields take their defaults. POST
`/NeewerLux/animate` takes the same as JSON keys `layer`, `mode` (`queue` or `replace`),
`target` and `revert`, and `{"action": "stop", "layer": "effect", "clear_queue": true}`.
