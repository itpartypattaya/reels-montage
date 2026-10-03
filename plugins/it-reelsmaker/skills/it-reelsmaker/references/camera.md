# Virtual camera and word anchoring: code

The two helpers that keep a Remotion edit stable when the cut changes. The rules for shots are in SKILL.md, section 9.

## Shots in source time

The camera is `{ z, cx, cy }`: the scale and the frame point that ends up in the center. Shots are listed in **source time** and converted with `at(src)`, so a speed change in `cut.py` breaks nothing:
```ts
// file: source file (multicamera: the segment has a src field); seg: segment number, if that second appears in the video twice
const at = (src: number, file?: string, seg?: number) => {
  const pool = SEGS.filter((g) => (file === undefined || g.src === file) && (seg === undefined || g.i === seg));
  const hit = pool.filter((g) => src >= g.src_start - 0.001 && src <= g.src_end + 0.001);
  if (hit.length === 0) throw new Error(`at(${src}): this second was cut out, or wrong source file`);
  if (hit.length > 1) throw new Error(`at(${src}): this second is in several segments — pass seg`);
  const s = hit[0];
  return s.out_start + Math.max(0, src - s.src_start) * (s.out_dur / (s.src_end - s.src_start));
};
const W = { z: 1.0, cx: 540, cy: 960 }, M = { z: 1.1, cx: 540, cy: 1000 },
      C = { z: 1.2, cx: 540, cy: 990 },  P = { z: 1.28, cx: 540, cy: 1000 };
const SHOTS = [ { src: 0, cam: M, drift: 0.05 }, { src: 17.6, cam: P, whip: true }, /* … */ ];
// rendering: <div style={{ transform: `translate(${540 - cx*z}px, ${960 - cy*z}px) scale(${z})`,
//             transformOrigin: "0 0" }}><OffthreadVideo …/></div>
```

## Shot rules

- **Clamp the camera** so that its window never leaves the frame: `cx` within [540/z, 1080 − 540/z], `cy` within [960/z, 1920 − 960/z]. Otherwise an empty edge shows.
- Put the frame center slightly **below the eyes** (`cy` ≈ 990–1000 with the eyes at y 960): the chin stays above the subtitles. Check with the face zones for that camera (`faces.py zones --cam z,cx,cy`), then with the render audit.
- Use the **wide shot wherever a card is on screen**: the card needs the “headroom” zone.
- Change shots only in a gap between words of **≥ 0.1 s**; hold one shot size **no longer than 3–4 s**; every cut on a pause gets a shot-size change. Reference density: about 13 shots in 27 s, one every ~2 s; a 20–25 s video has about 10 picture changes.
- Meaning of the shot size: push-in on the main thought, a number, an emotion or a question to the viewer; close-up on the CTA and personal lines; wide on context and the final conclusion.
- Put shots on seconds that stay in the video (for example a segment's `src_start`): `at()` throws on a second that was cut out.
- If the face already fills about **half of the frame width**, there is no room to zoom: say so before editing and get the dynamics from cutaways and graphics.
- After any crop, the hands and objects the speaker talks about stay in frame.
- **Dynamics check:** the first 1–2 s are not a static wide shot (a detail, a close face, a push-in or the hook); the video uses at least three shot sizes.
- **Multiple cameras:** bring both speech rates to a common middle. Slowing below ×1 repeats frames (at ×0.915 about every 11th frame); on a static head this is invisible.
- Optional, untested and costly to render: real motion blur on a whip (ffmpeg at 180 fps averaged over 6 frames, or `@remotion/motion-blur`). Offer it only if the whip lacks punch.

## In the ReelKit template: `camera.json`

The kit draws these shots itself (kit 1.4.5): list them in `edit/<id>/camera.json`, and `visual_plan.py export --props`
turns them into `props.camera` (seconds of the finished video) and computes the subtitle top from the face measurement
with each shot's camera.
```json
{"shots": [
  {"src": 1.07, "z": 1.0, "cx": 540, "cy": 960, "drift": 0.02},
  {"at": "word:numbers#1", "z": 1.28, "cx": 460, "cy": 800, "whip": true},
  {"at": 41.6, "z": 1.2, "cx": 470, "cy": 960}
]}
```
A shot starts at `src` (a source second, stable when the speed changes; `seg` when that second appears twice), or at
`at` (a second or `word:<word>#n` of the finished video). `drift` is the push-in over the shot (+0.02–0.06), `whip`
replaces the cut with a 7-frame move and a light motion blur. The kit clamps the window to the frame. With no
`camera.json` the template keeps its plain slow drift. While a card sits on the chest (hook, contrast, CTA), keep `cy`
at 960 or lower the zoom: the chin must stay 60 px above the card; check the stills and the render audit.

## Zoom margin from a 4K source

The margin is counted from the resolution of `final.mp4`, not of the source. With `"scale": "auto"` (the default), `cut.py` scales a vertical 4K source down to 1080×1920, which leaves about ×1.3. To keep up to ~×2.0, build the rough cut at the source size (`"scale": "none"` in `cut.json`) and draw the video at 1080×1920 in Remotion; a 1440×2560 rough cut gives only ×1.33 without upscaling. Not verified: a 2160×3840 rough cut is heavy on an 8 GB machine (memory and render time), so offer it only when the video needs deep push-ins, and state the margin you will actually get.

A 720p source upscaled with lanczos needs light sharpening in `look.grade`, for example `unsharp=5:5:0.55:5:5:0.0`.

## Graphics on the spoken word

Anchor graphics **to the spoken word**, not to a second, so re-cutting shifts nothing:
```ts
const norm = (s: string) => s.toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
const atWord = (word: string, n = 1, offset = 0) => {
  const hits = WORDS.filter((w) => norm(w.text) === norm(word));
  if (hits.length < n) throw new Error(`no word “${word}” #${n}`);
  return hits[n - 1].start + offset;
};
```
Match ignoring edge punctuation and case: between runs, Whisper is inconsistent about punctuation attached to a word (Russian example: *eti*, “these”, comes out as “eti” in one run and “eti.” in another).
