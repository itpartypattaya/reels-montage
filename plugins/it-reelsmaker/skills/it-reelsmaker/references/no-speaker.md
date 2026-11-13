# No-speaker reels: voice-over, the mixed video and the two-track contract

Read this when the voice of the video is not a person speaking in the frame: a voice note over silent wide shots, a
narration over photos, or a talking head with a stretch of voice-over in the middle. The first part is how to edit
such a video; the second is the data contract every script follows (the sound track and the picture track apart).

Not here yet: the **no-speech reel** (no voice at all, the text carries it, sounds and music always offered) and
**photo reels** with movement planned from the photo; until then a photo is a picture shot like a clip, and a video
with no voice is the "scenes only" format (`references/scenes.md`). No speech is ever synthesized: no voice -> the
person records a voice note on the phone (`references/shooting.md`) or the video goes without speech.

## Voice-over and the mixed video

**When.** The person sends a voice recording (a phone voice note `.ogg/.opus/.m4a`, a `.wav/.mp3`) and clips or
photos to put under it; or a talking head where part of the speech should play over other pictures (a place, a
product, a process): "head -> voice-over -> head", often with a text ending after the voice. One video folder, one
`cut.json`, one `cut.py` run: no black video under the voice, no second project for the picture, no hand mux.

**Step 0, in addition to the usual brief** (ask only what applies):
- who speaks: the narrator's name and role if a label is wanted, from the brief, never "the first face in the
  frame"; a narrator may not be on screen at all, and there may be two;
- may strangers be shown? For every clip with people who did not agree to be filmed, mark where they are (below);
- `reel.json -> voice`: `off_camera` when nobody is seen speaking (the whole video is voice-over; the subtitles stay
  on over full scenes), `on_camera` (the default) for a talking head with voice-over stretches.

**The cut list.** The sound is cut exactly as for a talking head: `ranges` over the voice recording (takes,
pauses, speed, `fix`, `keep`, `speech_mask.py --edl` for the edges). The picture goes into `picture` blocks:

```json
{"fps": 30,
 "sources": {"voice": {"file": "voice.ogg"},
             "pool":  {"file": "IMG_2210.MOV", "strangers": [[12.0, 19.5]]},
             "sea":   {"file": "sea.jpg", "strangers": []},
             "street": {"file": "IMG_2214.MOV", "strangers": "ok",
                        "look": {"correct": "colorchannelmixer=rr=0.96:bb=1.04"}}},
 "ranges": [{"source": "voice", "start": 0.62, "end": 9.80}, {"source": "voice", "start": 11.40, "end": 21.95}],
 "picture": [
   {"from": "start", "to": "end", "shots": [
     {"source": "pool", "start": 3.0, "until": "word:sea#1", "move": "still", "what": "the pool, wide", "why": "the place"},
     {"source": "sea", "dur": 2.5, "move": "push", "what": "the sea", "why": "the word sea"},
     {"source": "street", "start": 1.0, "what": "the street", "why": "the word street"}]},
   {"from": "end", "to": 24.0, "shots": [{"fill": true, "what": "the punchline's field", "why": "the voice is over"}]}]}
```

- `from`, `to`, `until` are seconds of the finished video, `"start"`, `"end"` (the end of the sound) or
  `"word:<text>#<n>"` (the picture cuts where that word starts). A shot takes `dur` or `until` (`until` wins); the
  last shot of a block runs to the block's end. `start` is the clip's own second, `speed` 0.5-2.0 (a calm wide shot
  slowed to x0.8), `fit` `cover`/`contain`, `focus` [x, y], `move` `none` (the virtual camera may act) / `still` /
  `push` / `pull` / `pan` (the shot's own motion: the camera and the drift are off on it). `{"fill": true}`: the
  style's background, for a text ending after the voice or a stretch drawn only with scenes.
- Outside the blocks the picture is the speaker's own video at the seconds of its sound, as before. A stretch of a
  sound-only recording with no block over it has no picture: the background, named in a warning.
- `cut.py edit/<id> --dry-run` prints the picture shots. A clip shorter than its shot stops with numbers ("needs
  4.20 s from 3.00 s, the file has 3.10 s usable"): no freeze frame and no repeat is added. Every block must be
  covered exactly; only the last block may run past the voice (the sound is padded with silence there).
- The clips' own sound is not used (a pool, a street). Several takes of the voice in **different files** are not
  compared by `structure.py suggest`: read both reports side by side, pick the phrases, listen to every join (the
  background noise of two recordings differs, and it is not the only criterion).

**Color is a property of the place.** One balance does not fit an office and a sunset. `sources.<name>.look`
(`correct`, `lut`, `lut_mix`, `grade`) is merged over the video's `look` for that source only. `balance.py` measures
the frames of the **picture**, never the voice file: automatically over the shots whose places take the video's
look; `balance.py edit/<id> --ref <source>:<second>,X,Y,W,H --write` on one place (a white wall, paper) writes into
that place's own `look.correct` (`--source NAME` for the automatic mode on one place). A sky the automatic gain turned
purple is that case: use the eyedropper on the place.

**Strangers (blocking).** For every clip shown as the main picture, `sources.<name>.strangers` says once: `[]` none,
`[[from, to], ...]` its seconds where people who may not be shown are, or `"ok"` (they may be shown). Unanswered, or a
marked stretch not hidden under an opaque full scene (or a replacing B-roll, a cutaway) from 0.25 s before to 0.25 s
after, entering and leaving by a cut: `visual_plan.py validate` fails. A panel or a window over them does not hide
them. Better still, leave that stretch out of the shot. `defects.py` "more faces than usual" only suggests candidates.

**Lips under someone else's voice.** A person seen talking in a voice-over shot reads as dubbed: avoid it in the main
picture as in an insert (`references/inserts.md`). Detectors only hint, so the contact sheet is looked at by eye in
the self-review.

**What the checks do over a voice-over picture** (the purpose table below): the rules that protect the speaker's
face (the insert budget, no two full scenes in a row, the full hook's 1.5 s, the brand tone's ceiling of full scenes)
hold only over the speaker; reading time, the brand tone's transitions and flashes, facts from the source and "no
slideshow" hold everywhere. Faces for the subtitle zone and the cover are measured on `final.mp4`, that is on the
picture. The cover is a frame with a person (if any) and the hook fully in; a pause in the narration does not mean
the eyes in the picture are open: pick it on the sheet. The narrator's "NAME / ROLE" label is a scene's label or a
callout, taken from the brief; there is no separate scene type for it.

**Long recordings.** A voice-over clip of a long-form series is not supported: `longform.py extract` refuses a clip
folder with a `picture` block before changing anything in it, and `longform.py camera` refuses a picture that is not
its sound.

**Profiles.** With `voice: off_camera`, "said" in a checklist means said in the narration, and "the speaker in frame"
does not apply; `review` (a place or a product, often voice-over) uses everything above.

---

# The two-track contract

## Why

Until now the core knows two poles: the talking head (sound and picture come from the same file and the same
seconds) and "scenes only" (no sound source, no footage). Everything between them (a voice recorded apart from the
picture, silent wide shots, photos, a video that mixes a talking head with a voice-over stretch) needs the picture to
cut where the sound does not.

Today one record describes both: `captions.json → segments` and `edl.json → ranges` are the joins of the sound *and*
the joins of the picture. The contract below splits them into two tracks:

- the **sound track**: `captions.json → segments`, `edl.json → ranges/sources`. Unchanged. Speech checks, leveling,
  subtitles and `speech_mask.py --edl` keep reading only these.
- the **picture track**: a new `shots[]` list in `captions.json` and `edl.json`. Every consumer that asks "what is on
  screen at second t, from which file, and where does the picture jump" reads it through one access function.

## Naming: picture shots vs camera shots

The word "shot" is already used for the **virtual camera**: `camera.json → shots`, `vp_camera.camera_shots()`, the
kit's `Shot` type in `kit/anchor.ts`, and the `shots` member of the callout context. To keep the two apart:

- In JSON: `shots` in `captions.json` and `edl.json` (the picture track); `camera.json` keeps its own `shots`.
- In code and docs the picture track is always called **picture shots** (`pic_shots`, kit type `PictureShot`); the
  camera stays **camera shots**. A bare `shots` variable in new code is not allowed.

The JSON key stays `shots` (the owner's decision); in code the picture track is always `pic_shots` / `PictureShot`.

## `reel.json → voice`

| Value | Meaning | Clock of the video |
|---|---|---|
| `on_camera` (default; also when the key is absent) | the voice belongs to a person seen speaking in the picture — today's behaviour | the kept speech |
| `off_camera` | a voice-over: recorded apart, or a speaker who is not shown while speaking | the kept speech |
| `none` | no-speech reel: no voice at all; text, sound effects and music carry it | the reading time of the text blocks |

`voice` is the **sound mode**, not a statement about faces: a person may be on screen in any mode. The existing
`speaker` field (labels A/B, long-form) is unrelated and keeps its meaning. A video may still mix modes along its
timeline: `voice` is the default of the video, `picture` blocks in `cut.json` override the picture of a
stretch.

## `shots[]`: the picture track

One record per stretch of the finished rough cut with one continuous picture source:

| Field | Type | Meaning |
|---|---|---|
| `i` | int | occurrence number, unique in the list, in timeline order. When the picture follows the sound it equals the `i` of the sound segment it copies (the camera's `src_to_out(seg=…)` and the kit's drift parity read it) |
| `kind` | `video` \| `photo` \| `fill` | `fill`: the style's background, no source file |
| `source` | string \| null | the source name from `cut.json → sources` (or a picture-only source, used only in `picture` blocks); `null` for `fill` |
| `src_start`, `src_end` | seconds | the source window. For `video`: real source seconds, `src_end > src_start`. For `photo` and `fill`: **conventional coordinates** `src_start = 0`, `src_end = out_dur` |
| `speed` | number | playback speed of the source window (`video`); `1.0` for `photo` and `fill` |
| `out_start`, `out_dur` | seconds | where the shot sits on the finished timeline; whole frames at the video's fps |
| `move` | `none` \| `still` \| `push` \| `pull` \| `pan` | motion baked into the shot. `none`: the shot carries no motion of its own and the virtual camera may act on it (every copied shot). Anything else: the camera and the drift are off on this shot (one motion layer) |
| `look` | string \| null | the look key applied to this shot's source (the place's own color, `sources.<name>.look`); `null` = the video's look |

Rules:

- **Order and cover.** Sorted by `out_start`; no gaps, no overlaps; `shots[0].out_start = 0`; the last shot ends at
  `captions.json → duration`. Times are rounded the same way as the sound segments (3 decimals, on the frame grid).
- **Conventional coordinates.** On `photo` and `fill` the source seconds are not real time. Nothing may map a source
  second into such a shot: the camera's `src_to_out()` skips them, defect and face lookups by source second skip them.
  The division by `src_end − src_start` stays safe because the width equals `out_dur > 0`.
- **Copy rule (without a `picture` block).** `cut.py` writes `shots` as a copy of the sound
  segments: same `i`, `source`, `src_start`, `src_end`, `speed`, `out_start`, `out_dur`; `kind = "video"`,
  `move = "none"`, `look = null`. Exception: a sound segment from an **audio-only source** (a recorded voice file,
  no video stream) has no picture to copy; its stretch becomes a `fill` shot (`source = null`, conventional
  coordinates), and the scenes drawn over it are its picture (purpose `graphic`).
- **Fallback.** A reader falls back to `segments` **only when `shots` is absent from the file** (a rough cut made before
  this contract). An explicit empty list means "no picture" and is never replaced by `segments`.
- **Where.** `captions.json → shots` (the kit and the Python checks) and `edl.json → shots` (the same records; the
  edge checker ignores them). Sources used only for the picture are listed in `edl.json → picture_sources`
  so that `speech_mask.py --edl` never opens them; `ranges/sources` keep only sound.
- **Translated captions** (`captions-<lang>.json`) do not carry `shots`: they feed only the subtitles.

### One access function

`pic_shots(captions)` in a small new module (not in `reels_common.py`, which is already large): returns
`captions["shots"]` when the key exists, else `segments` normalised to the shot schema (`kind = "video"`,
`move = "none"`, `look = None`). The kit gets the same rule in one helper next to `driftZoom`. Every picture consumer
calls it; no consumer reads `segments` to find picture joins.

### Picture consumers (they read `pic_shots`)

Python: `faces.source_cuts()`, `faces.segments_of()` (its fallback branch), `textcheck.face_source()`,
`defects.find()`/`source_at()`, `vp_camera.src_to_out()` (called by `camera_shots()`), `track.main()` (track breaks),
`vp_callouts.track_key()`, `vp_callouts.callout_context()` (and through it `drift_zoom()`, `anchor_on_screen()`,
`screen_to_frame()`, `zoom_at()`), `vp_core.build_plan()` (the "hide the join" and "long shot" hints),
`longform.camera_plan()` (with `cut_points()`, `seg_at()`) — or an explicit refusal of a rough cut whose `shots`
differ from `segments`.

Kit: `ReelKit.tsx` (the drift of the video and the `segments` given to the callout layer), `kit/anchor.ts`
(`driftZoom`, `anchorOnScreen`, `zoomAt`), `Callout.tsx` (passes them through).

Stays on sound: `level.py`, `speech_mask.py --edl`, `subs.py`, `transcribe.py rate`, the word checks of `cut.py`
(`mark_keep`, `dropped_in_gaps`, `estimated_words`, `repeats_at_joins`, `hidden_at_edges`), `structure.py`.

Without a `picture` block `balance.py` (`frame_times()`, `ref_source()`, `frames_key()`) and `cut.auto_balance()`
keep reading `cut.json → ranges` (the picture is their copy); with one they measure the resolved picture shots
(`balance.picture_windows()`). Switching the plain case to the shots would move the
measured frames by rounding and invalidate every saved balance mark.

## `picture_id`: the picture's fingerprint

`cut_id()` stays the fingerprint of the **sound** cut (duration, segments, words). The picture gets its own:

- `picture_id` = a short hash of the duration and, per picture shot, `i, kind, source, src_start, src_end, speed,
  out_start, out_dur, move, look`.
- Written to `captions.json → picture_id` **only when `shots` is not a plain copy** of the sound segments. When it is
  a copy, there is no `picture_id`, old and new rough cuts compare equal, and nothing changes for existing plans.
- The visual plan stores the `picture_id` it was checked on next to `captions_id`. Absent on both sides = equal.
- **A new `picture_id` invalidates** what was measured on the picture: face samples and face zones, the camera's
  conversion of source seconds, callout tracks (`track_key` includes it), the board, picture defects, the balance
  measurement. It does **not** re-cut the plan's speech spans (`follow_rough_cut()` runs only on a new `cut_id`),
  the subtitles or the translation.
- A changed `cut_id` with the same `picture_id` (a voice re-cut under the same picture) keeps the picture data
  where the shots did not move.

## Order inside `cut.py`: load → resolve → balance → encode

Today `cut.main()` runs the automatic balance before `timeline()`. The contract fixes the order:

1. **load** — read and check `cut.json`, probe the sources (an audio-only source needs no picture geometry; the picture sources lie in the video's
   geometry as a cover).
2. **resolve** — one stage computes the whole timeline before anything is encoded: the sound spans, the picture shots,
   explicit silence or `fill` intervals, and the length of animated scenes that set the clock. Whole frames, full
   cover, no gaps or overlaps; `until` wins over `dur`; a source shorter than its window is an error with numbers
   ("needs 4.2 s, has 3.1 s usable"), never a silent repeat or freeze.
3. **balance** — measures frames of the **resolved picture shots**; without a `picture` block it measures the ranges (their copy)
   and runs before load, as it always did.
4. **encode** — the sound from the sound spans, the picture from the picture shots, then the mux.

Without a `picture` block the resolve stage only produces the copy, so the encoded output is the same as before
the picture track (byte for byte). With one, `cut_picture.py` builds the sound (each piece, leveled, padded with
silence to the picture's end) and the picture (each shot at the video's size and fps: the speaker's own video
through the rough cut's chain, a clip or photo through `footage.prepare(strict=True)`, a `fill` as the background)
apart, then muxes them.

Example that the contract must allow without a fake audio source (a mixed video ending without speech): the voice
ends at 21.4 s; a text punchline runs on a `fill` shot until 24.0 s over music. The sound track ends at 21.4 s and is
padded with silence; `shots` end at 24.0 s; `captions.json → duration` is 24.0.

## Interval purpose and where each rule applies

Every stretch of the timeline has a purpose, derived from `voice` and `shots` (never set by hand):

- `speaker` — the person speaking is on screen: `voice = on_camera` and the shot is a `video` of the sound source at
  the same source seconds as the sound segment, for its whole length: one sound segment holds the whole shot, at the
  same speed, from the same second (another speed, or a shot running on past its segment, is `picture`).
- `picture` — the main picture without a speaking face on screen: voice-over shots, silent shots, photos.
- `graphic` — a designed scene *is* the picture: a `fill` shot, a full-screen scene over `picture` in a no-speech
  reel, the whole "scenes only" video.
- `insert` — B-roll, a meme or a scene laid over a `speaker` stretch.

| Rule (where it lives today) | `speaker` / `insert` | `picture` | `graphic` |
|---|---|---|---|
| insert budget, `coverage_max` (`vp_validate`) | yes | no | no |
| no two `full` scenes in a row (`vp_scenes`) | yes | no | no |
| `full_scenes_max` of the brand tone (`vp_scenes`) | yes | no | no |
| a `full` hook at most 1.5 s (`vp_scenes`) | yes | no | no |
| only the ending/CTA in the last 2 s (`vp_scenes`) | yes | yes | yes |
| the speaker's face stays visible | yes | no | no |
| text never covers a face in the picture | yes | yes | — |
| reading floor (after the text fully appears, before it leaves) | yes | yes | yes |
| brand tone: flashes, transitions, whip | yes | yes | yes |
| facts only from the source | yes | yes | yes |
| no slideshow | yes | yes | yes |
| strangers only under an opaque `full` for the whole marked window (blocking) | — | yes | — |
| lips moving under someone else's voice: a self-check item | — | yes | — |

The "scenes only" format is the case where every stretch is `graphic`: the rules it switches off are the
`speaker`-only rows. The ending rule is a structure rule, not the face's: it holds everywhere (the no-speech reel will
decide its own ending). The table is one dictionary, `pic_track.RULES`; the purposes are derived by
`pic_track.purposes()` in Python and `picturePurposes()` in the kit (`kit/anchor.ts`) from the same props
(`captions.shots`, `voiceMode`), and a scene that starts on a `fill` shot is timed as in "scenes only" on both sides
(`on_graphic` / `onGraphic`: cuts instead of smooth transitions). One test checks both sides on the same data. Where a
scene or an insert lies partly over the speaker, the speaker's rules hold for it (the insert budget counts only its
seconds over the speaker).

## Regression

- On every talking-head and "scenes only" fixture: `final.mp4`, `captions.json` and `edl.json` (apart from the new
  `shots` key), plans, props and renders are byte for byte the same; old plans validate as before.
- A fixture whose `shots` joins deliberately differ from the sound `segments`: every picture consumer listed above
  follows `shots`; every sound consumer keeps `segments`.
- A `captions.json` without `shots` (an old rough cut) behaves exactly as today; `"shots": []` is not replaced.
