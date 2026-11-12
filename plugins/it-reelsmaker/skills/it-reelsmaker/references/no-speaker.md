# No-speaker reels: the two-track contract

> **DRAFT.** This file fixes the data contract before any code changes (core "phase 0"). Phase 0 changes no
> behaviour: every existing talking-head and "scenes only" output stays byte for byte the same, except the new
> `shots` field. SKILL.md does not link this file yet; it ships together with the voice-over release, where the
> user-facing part (voice-over, mixed video, no-speech reel, photos) is added below the contract.

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

*Open:* rename the JSON key instead (for example `picture`) if the owner prefers; the contract is otherwise the same.

## `reel.json → voice`

| Value | Meaning | Clock of the video |
|---|---|---|
| `on_camera` (default; also when the key is absent) | the voice belongs to a person seen speaking in the picture — today's behaviour | the kept speech |
| `off_camera` | a voice-over: recorded apart, or a speaker who is not shown while speaking | the kept speech |
| `none` | no-speech reel: no voice at all; text, sound effects and music carry it | the reading time of the text blocks |

`voice` is the **sound mode**, not a statement about faces: a person may be on screen in any mode. The existing
`speaker` field (labels A/B, long-form) is unrelated and keeps its meaning. A video may still mix modes along its
timeline: `voice` is the default of the video, `picture` blocks in `cut.json` (phase 1) override the picture of a
stretch.

## `shots[]`: the picture track

One record per stretch of the finished rough cut with one continuous picture source:

| Field | Type | Meaning |
|---|---|---|
| `i` | int | occurrence number, unique in the list, in timeline order. When the picture follows the sound it equals the `i` of the sound segment it copies (the camera's `src_to_out(seg=…)` and the kit's drift parity read it) |
| `kind` | `video` \| `photo` \| `fill` | `fill`: the style's background, no source file |
| `source` | string \| null | the source name from `cut.json → sources` (phase 1: or a picture-only source); `null` for `fill` |
| `src_start`, `src_end` | seconds | the source window. For `video`: real source seconds, `src_end > src_start`. For `photo` and `fill`: **conventional coordinates** `src_start = 0`, `src_end = out_dur` |
| `speed` | number | playback speed of the source window (`video`); `1.0` for `photo` and `fill` |
| `out_start`, `out_dur` | seconds | where the shot sits on the finished timeline; whole frames at the video's fps |
| `move` | `none` \| `still` \| `push` \| `pull` \| `pan` | motion baked into the shot. `none`: the shot carries no motion of its own and the virtual camera may act on it (every copied shot). Anything else: the camera and the drift are off on this shot (one motion layer) |
| `look` | string \| null | the look key applied to this shot's source (phase 1: per-source color); `null` = the video's look |

Rules:

- **Order and cover.** Sorted by `out_start`; no gaps, no overlaps; `shots[0].out_start = 0`; the last shot ends at
  `captions.json → duration`. Times are rounded the same way as the sound segments (3 decimals, on the frame grid).
- **Conventional coordinates.** On `photo` and `fill` the source seconds are not real time. Nothing may map a source
  second into such a shot: the camera's `src_to_out()` skips them, defect and face lookups by source second skip them.
  The division by `src_end − src_start` stays safe because the width equals `out_dur > 0`.
- **Copy rule (phase 0, and phase 1 without a `picture` block).** `cut.py` writes `shots` as a copy of the sound
  segments: same `i`, `source`, `src_start`, `src_end`, `speed`, `out_start`, `out_dur`; `kind = "video"`,
  `move = "none"`, `look = null`. Exception: a sound segment from an **audio-only source** (a recorded voice file,
  no video stream) has no picture to copy; its stretch becomes a `fill` shot (`source = null`, conventional
  coordinates), and the scenes drawn over it are its picture (purpose `graphic`).
- **Fallback.** A reader falls back to `segments` **only when `shots` is absent from the file** (a rough cut made before
  this contract). An explicit empty list means "no picture" and is never replaced by `segments`.
- **Where.** `captions.json → shots` (the kit and the Python checks) and `edl.json → shots` (the same records; the
  edge checker ignores them). In phase 1, sources used only for the picture are listed in `edl.json → picture_sources`
  so that `speech_mask.py --edl` never opens them; `ranges/sources` keep only sound.
- **Translated captions** (`captions-<lang>.json`) do not carry `shots`: they feed only the subtitles.

### One access function

`pic_shots(captions)` in a small new module (not in `reels_common.py`, which is already large): returns
`captions["shots"]` when the key exists, else `segments` normalised to the shot schema (`kind = "video"`,
`move = "none"`, `look = None`). The kit gets the same rule in one helper next to `driftZoom`. Every picture consumer
calls it; no consumer reads `segments` to find picture joins.

### Picture consumers (move to `pic_shots` in phase 0)

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

Moves in phase 1, not phase 0 (they read `cut.json → ranges` before the timeline exists): `balance.py`
(`frame_times()`, `ref_source()`, `frames_key()`) and `cut.auto_balance()`. Switching them in phase 0 would move the
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

1. **load** — read and check `cut.json`, probe the sources (phase 1: an audio-only source needs no picture geometry).
2. **resolve** — one stage computes the whole timeline before anything is encoded: the sound spans, the picture shots,
   explicit silence or `fill` intervals, and the length of animated scenes that set the clock. Whole frames, full
   cover, no gaps or overlaps; `until` wins over `dur`; a source shorter than its window is an error with numbers
   ("needs 4.2 s, has 3.1 s usable"), never a silent repeat or freeze.
3. **balance** — measures frames of the **resolved picture shots** (phase 1); in phase 0 it keeps measuring the ranges.
4. **encode** — the sound from the sound spans, the picture from the picture shots, then the mux.

In phase 0 the resolve stage only produces the copy, so the encoded output is unchanged.

Example that the contract must allow without a fake audio source (a mixed video ending without speech): the voice
ends at 21.4 s; a text punchline runs on a `fill` shot until 24.0 s over music. The sound track ends at 21.4 s and is
padded with silence; `shots` end at 24.0 s; `captions.json → duration` is 24.0.

## Interval purpose and where each rule applies

Every stretch of the timeline has a purpose, derived from `voice` and `shots` (never set by hand):

- `speaker` — the person speaking is on screen: `voice = on_camera` and the shot is a `video` of the sound source at
  the same source seconds as the sound segment.
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
| only the ending/CTA in the last 2 s (`vp_scenes`) | yes | no | no |
| the speaker's face stays visible | yes | no | no |
| text never covers a face in the picture | yes | yes | — |
| reading floor (after the text fully appears, before it leaves) | yes | yes | yes |
| brand tone: flashes, transitions, whip | yes | yes | yes |
| facts only from the source | yes | yes | yes |
| no slideshow | yes | yes | yes |
| strangers only under an opaque `full` for the whole marked window (blocking) | — | yes | — |
| lips moving under someone else's voice: a self-check item | — | yes | — |

The "scenes only" format is the case where every stretch is `graphic`: the rules it switches off today are exactly
the `speaker`-only rows. Python (`vp_scenes`, `vp_validate`) and the kit (`SceneLayer`, `tones.ts`) read the purpose
from the same props (`purpose` intervals instead of the `scenesOnly` flag alone), and one test checks both sides on
the same plan. The table is one dictionary in code, applied from phase 1; phase 0 only defines it.

## Phase 0 acceptance (regression)

- On every talking-head and "scenes only" fixture: `final.mp4`, `captions.json` and `edl.json` (apart from the new
  `shots` key), plans, props and renders are byte for byte the same; old plans validate as before.
- A fixture whose `shots` joins deliberately differ from the sound `segments`: every picture consumer listed above
  follows `shots`; every sound consumer keeps `segments`.
- A `captions.json` without `shots` (an old rough cut) behaves exactly as today; `"shots": []` is not replaced.
