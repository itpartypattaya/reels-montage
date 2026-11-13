# Music composed in code: music.py and beats.json

Read this when a video takes music made in code (most often a no-speech reel, `references/no-speaker.md`), or when
scenes should land on the music's beats. Short sound effects stay in `references/library.md`; this file is the music
and its contract.

## What it is

`scripts/music.py` writes the music of one video with numpy: oscillators, noise and envelopes in a few hundred lines,
no model, no sound file, no download, no license question (it is yours). It is designed for the video: exactly its
length, a tempo the scenes can use, and markers where the text turns. It does not replace a good licensed track; it is
the option when the person has none, and the track picked in the app at publishing stays an option too.

```bash
python scripts/music.py --edit edit/<id>                      # reel.json -> music, script.json's blocks, the length
python scripts/music.py --edit edit/<id> --seed 2             # another arrangement of the same request
python scripts/music.py out/try.wav --dur 15.4 --bpm 104 --style pulse --stop 3.2 --resume 3.7 --button 11.0
```

`--edit` writes `edit/<id>/music.wav` and `edit/<id>/beats.json`. Its length is the finished video's: `captions.json
-> duration` plus the end card or sting the stage adds (2.6 s). The answers come from `reel.json -> music`:

```json
{"music": {"source": "code", "style": "groove", "bpm": 104, "seed": 1,
           "markers": {"stop": "label", "resume": "translation", "button": "punchline"}}}
```

`source`: `code` (music.py), `own` (a licensed track, burned in), `app` (a track picked in the app when publishing:
the video is mastered with its sound effects only and the report reminds to pick it), `none` (no music, on purpose).
A marker names a text block of `script.json` by its id or its role, or a second. A series preset keeps the whole
`music` object; set one field with `reelcfg.py save edit/<id> --set music.style=pulse`.

## Styles

They differ in instruments, rhythm and density, not only in tempo.

| Style | Instruments | Rhythm | Density | For |
|---|---|---|---|---|
| `groove` | kick, claps, hats, a bouncing bass, electric-piano stabs | kick on 1 and 3 with a pushed kick before 3, claps on 2 and 4, eighth hats, bass on eighths and sixteenths | dense | a light comic series, a list of quick points |
| `pulse` | a soft kick, a rim, a plucked note, a pad | kick on 1, rim on 3, a plucked note on every beat, one chord per bar | medium-low | a calm explainer, a product, a place |
| `tension` | a ticking clock, a low bass, a drone, a riser | ticks on sixteenths, bass on eighths, a drone and a riser per two bars | medium, nervous | a deadline, a countdown, "before / after" |
| `ambient` | pad swells, a soft bell | none marked: a swell over two bars, a bell every two bars | low | a mood, a sunset, a quiet ending; the scenes need not land on its grid |

The tempo is 70-140 bpm (104 is the default). The seed picks the chord progression and the small variations: the same
request with another `--seed` is another arrangement in the same style.

**Listen before the render.** The sound of each style is checked by ear, not by a test: play `music.wav` to the person
(or say where it lies), then render.

## Markers

Each marker lands on the nearest beat of the grid (beat k at k × 60 / bpm seconds of the video), then on a frame.

- `stop` — the tape stops: the last 0.45 s slow down to nothing and the music stops on the beat: a turn in the text
  ("TRANSLATING:", a label). Silence follows until `resume`.
- `resume` — the music comes back, lighter (no kick in `groove`, no rim in `pulse`), under the reading.
- `button` — the punchline's accent: a kick, a held chord and a cymbal, gone after 1.8 s; then silence for the
  reaction until the end.
- `pause A-B` — a silence inside (a comic pause), repeatable.

A marker outside the video, two markers closer than one beat, a `resume` without a `stop`, a `stop` or `resume` after
the `button`, or a tempo out of range is an error: nothing is written.

## The file

WAV PCM 16-bit, 48 kHz, stereo; exactly `round(duration × 48000)` samples; the peak at −6 dBFS (headroom for the
master's loudness and the scene sounds), never clipped; a 15 ms ease-in from silence (a kick on the very first sample
made the master's AAC overshoot) and its own 0.25 s fade at the very end unless a button or a stop
ended it. The same version of the algorithm, the same parameters and the same seed give the same bytes.

## beats.json (schema 1)

| Field | Meaning |
|---|---|
| `schema`, `algo` | `1`, `"music.py 1"`: the contract and the algorithm's version |
| `time`, `music_start` | times are seconds of the finished video, the end card included; the music starts at the video's 0 (`master_audio.py --music-start` is refused for it) |
| `wav`, `wav_sha256`, `rate`, `samples`, `duration` | the WAV it belongs to: validate and the master compare the hash and the length |
| `bpm`, `style`, `seed`, `params_id`, `beat_marked` | the request and its fingerprint; `beat_marked: false` for `ambient` |
| `beats` | the beats that are heard: `{n, t, bar, pos, strength}` (`strong` on 1 of a bar, `weak` elsewhere); none while the music is stopped, paused or after the button |
| `active` | `[from, to]` stretches where the beat is heard |
| `silence` | the silences meant to be there: `{from, to, why}` with `why` `stop`, `pause` or `button` |
| `markers` | `{kind, requested, at, beat, block}`: the requested second, where it landed, the beat number and the `script.json` block it serves (`pause`: also `end_requested`, `end`) |
| `rounding` | the rule: the nearest beat, then a frame |

## How the plan uses it

- **Reading wins over the grid.** `visual_plan.py script edit/<id> --bpm 104` times the text blocks on the music's grid:
  each block runs on to the next beat after its reading is done, never ends earlier. Without `--bpm` the blocks keep
  their reading length and the markers land on the beat nearest to each block's start.
- Scenes may be placed by `--at beat:N` (the N-th heard beat, from 1), `--at marker:button` or `--at block:<id>`.
- `visual_plan.py validate` reads `edit/<id>/beats.json`: it must belong to `music.wav` (the hash), last as long as
  the video with its end card, and its markers must serve blocks of the script at their present times; otherwise run
  `music.py --edit` again.
- "Beat" (`references/scenes.md`): music made in code counts as burned-in music with rights.

## The master

`master_audio.py <render> -o <master> --music edit/<id>/music.wav --edit edit/<id>`: the WAV's beats.json is found
next to it (`beats.json` naming it, or `<name>.beats.json`). The master refuses music whose hash or length is not
this video's and music silent where beats.json has it playing; it adds no fades of its own (the music shaped its
start, stops, button and end); after the scene sounds (`--sfx`) the whole mix is brought back to −14 LUFS with the
true peak under −1 dBFS, checked on the finished AAC. The silence after a button or in a pause is meant, never "the
music ran out". A licensed track under a no-speech reel must last to the end of the video (another stretch with
`--music-start`, a longer track, a repeat agreed with the person, or `music.source: none`).

## Words

Say "composed in code" or "designed in code" (as the scenes): the music is written by the script, not taken from a
model. The core never synthesizes speech.
