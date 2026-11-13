# The brand mascot: a character drawn in code, animated to your recording

A small character in the brand's colors stands in the lower left of the video, opens its mouth to your recorded narration, blinks, breathes and gestures on chosen words (points at a scene, shows a palm, thinks, celebrates). It is drawn in code as a Remotion component; nothing is generated: the mouth follows the loudness of your own voice.

**When to offer it.** When the brand already has a mascot (`brand.json → mascot`, `reelcfg.py show` prints it) or the person asks for one. A brand without one sees it as one item of the inserts question marked new, only in a video with no speaker on screen (scenes over a voice, a voice-over over your shots, a promo) and at a tone other than `premium`: “a brand mascot: drawn in your colors, or your own character picture brought to life” (the second is `references/mascot-atlas.md`); chosen → draw it (or cut the picture) before the plan, shown to the person on the sample sheet. It is a menu item (SKILL.md section 1), off by default. It suits videos where the speaker is not on screen: scenes over your recorded narration, or voice-over footage. A mascot beside a live speaker, several characters, and a mouth timed by syllables with no recording are not part of it.

**The brand tone decides** (`reel-defaults.json → brand_tones.<preset>.mascot`): `off` for `premium` (validate refuses it; `tone_override` turns that into a warning noted in the report), `calm` for `expert`, `tech`, `warm` and `story`, `full` for `friendly`, `drive` and `bold`. A brand changes it like any tone field: `brand.py tone <slug> <preset> --field mascot=calm`.

## The pipeline

1. **The brand's mascot, once per brand.** Claude draws it as a component in the person's Remotion project (below; a starting point is `references/mascot-sample.md`), then: `brand.py mascot <slug> --drawn src/mascot/<Name>.tsx [--symmetric]` (reads its box and poses into `brand.json → mascot`) and `brand.py stage <slug> --remotion <dir>` (registers it in `src/gen/mascots.ts`, under the brand's slug, and writes `src/brands/<slug>.json → mascot`). `mascot.py check --brand <slug>` checks the file, its box and poses, the registration.
2. **The mouth, per video:** `mascot.py mouth edit/<id>` → `edit/<id>/mouth.json`. It reads the track the viewer hears on the edit's timeline: `voice.wav` (scenes over a recorded narration), else the rough cut's own audio `final.mp4` (the file stage copies to `public/<id>/video.mp4`); `--audio <file>` names another track on the same timeline. Run it again after any re-cut: stage refuses a stale one.
3. **The plan:** `mascot.py plan edit/<id> --pose "word:look#1=point_left" --pose "word:done#1=celebrate"` (a pose change on a word follows the word through a re-cut, like inserts), then `visual_plan.py validate`. Show it in the plan the person approves (step 7a): when it is on screen, its poses and their words.
4. **Stage and checks:** `visual_plan.py stage … --props` resolves everything into `props.mascot` (below) and keeps its box clear in the plan's `keep_clear`; `textcheck.py` flags text over the drawn figure; then the board and the render as usual.

## The contract

`src/kit/mascot/types.ts`:

```ts
export type MascotBox = { width: number; height: number; anchor: [number, number] }; // anchor = the point between the eyes, in box px
export type MascotFrame = { t: number; pose: string; prevPose: string; k: number; open: number; talking: boolean; blink: boolean; facing: 1 | -1 };
export type MascotRender = (f: MascotFrame) => React.ReactNode; // returns SVG/HTML inside the box
export type MascotModule = { box: MascotBox; poses: string[]; render: MascotRender };
```

A drawn mascot's module exports three things, the first two as literals (the scripts read them from the file):

```ts
export const box: MascotBox = { width: 520, height: 480, anchor: [260, 190] };
export const poses = ["neutral", "talk", "point_left", "palm", "think", "celebrate"];
export const render = (f: MascotFrame) => <svg width={520} height={480}>…</svg>;
```

- **The box holds the whole figure in every pose,** arms raised and pointing included: the plan checks the box, scaled, against the subtitles and the UI zones, so an arm that leaves it can land on them unchecked.
- **The anchor** is the point between the eyes: placement, scale and mirroring turn around it.
- `render` returns the drawing for one frame, sized to the box (an `<svg>` of the box's size, or HTML of that size). It is a pure function of the frame: no state, no timers, no random numbers (the render must be the same every time). `k` is the eased progress from `prevPose` to `pose` (may pass 1 only where a bounce is allowed); `open` 0–1 is the mouth; `blink` closes the eyes; `facing` −1 means mirrored, and the layer already mirrors the whole box.
- No text inside the mascot. No outline or drop shadow by default (the kit's rule); a sticker outline is part of the brand's own drawing if the brand wants one.

**Poses.** The dictionary: `neutral` (rest, the start of every track), `talk` (a small open gesture while explaining), `point_left` and `point_right` (at something on that side of the screen), `point_up` (at something above), `palm` (presenting), `think`, `surprise`, `celebrate`, `shrug`, `wink`. A mascot needs `neutral`; a pose it lacks is drawn by its stand-in and validate says so: `point_right` ↔ `point_left` mirrored (only with `--symmetric`, else `palm`), `point_up` → `palm`, `palm` → `talk`, `think` → `talk`, `surprise` ↔ `celebrate`, `shrug` → `palm`, `talk` and `wink` → `neutral`, anything else → `neutral`. A mirrored stand-in turns the whole figure at the start of its change (a turn, not a blend): draw the pose itself when the mascot points right often.

**Kinds.** `drawn` (this page) or `atlas` (a PNG atlas of a ready character picture cut by `mascot.py atlas`; `brand.py mascot <slug> --atlas assets/mascot/rig.json`, stage copies the rig and the image into `public/brands/<slug>/mascot/` like the logos; `visual_plan.py stage` puts the rig's content into `props.mascot.rig` and the kit draws it with `kit/mascot/AtlasMascot.tsx` from `MascotLayer.tsx → mascotModule`; `references/mascot-atlas.md`).

## How Claude draws a brand mascot

- **Simple shapes that read at 300–500 px tall on a phone:** one body shape, two dot or oval eyes, a mouth, two arms of two segments. Colors only from the brand profile (`import brand from "../brands/<slug>.json"`, `brand.colors`), never HEX values typed in, except a neutral ink for the features; a body that also reads over the video (check it on the board).
- **Poses as numbers** (arm angles, gaze, tilt, brows, smile) in a table, blended with `kit/mascot/rig.ts`: `poseAt(POSES, f, angles)` blends the previous pose into the current one by `f.k`, the angles by the shortest arc (`angMix`); `armPath(shoulder, {a1, a2}, l1, l2)` draws an arm of two segments; `mirrorArm` gives the other side.
- **The mouth** from `f.open`: closed (a smile line, its curve from the pose) below about 0.05, an opening that grows with `open` above it. **Blink** from `f.blink`.
- **Its character from the brand's tone and audience,** not a copy of another brand's mascot or of the sample: the sample is there for the conventions only, and every brand gets its own figure.
- Type-check it (`npx tsc` in the Remotion project), look at it on the storyboard (`board.py`), then register it (step 1 above).

## The plan's field and the per-frame plan

`visual_plan.json → mascot` (`mascot.py plan` writes it, `init` keeps it): `x`, `y`, `scale` (the anchor on screen; null: placed automatically), `facing`, `from`, `to` (seconds on screen; `to` null: the end of the rough cut, before the end card), `track` (`[{at, t, pose}]`), `speaks` (half-open spans `[a, b)` of the edit where the mouth moves; null: the whole narration; `--speaks none`: never).

**Placement** (`mascot.py plan --auto-place`, the default): the lower left, its lowest point 30 px above the subtitle band (the band the last stage recorded, else y 1250), as tall as the room allows up to 540 px, in the left half. With no subtitles (scenes only), above the bottom UI zone. **Under full scenes** (scenes over a voice, a promo: every scene is full and shares the frame with the mascot) a full scene's text ends 40 px above the mascot's top (the kit's zone from y 250 down to there, `props.mascot.top`), and the placement keeps that zone at least 540 px tall, so the mascot is lower and smaller there (about 390 px over the default subtitles). `--at X,Y --scale K` places the anchor by hand.

**The mouth** (`mascot.py mouth`): per frame of the kit's grid the RMS of the samples from `round(f·sr/fps)` to `round((f+1)·sr/fps)` (no drift over a minute); speech frames are 10 dB over the noise floor (measured between the words of `captions.json` when it has words, else on the quietest tenth of the track; with no pauses at all, −50 dBFS) and inside a word when there are words; the level is normalized by the 98th percentile of the speech frames only (silence and one loud click do not squash it), smoothed [1, 2, 1]/4, opened from 0.08 to fully at 0.63; every frame that is not speech is closed. `mouth.json` keeps the frame rate, the frame count (round half up, as the kit counts) and stamps of the track and of the words' times (a new transcript of the same audio makes it stale too).

**`props.mascot`** (stage): `{kind, module, [rig, atlas], x, y, scale, facing, from, to, frames}` (an atlas: `rig` is the content of `rig.json`, `atlas` the image's path inside `public/`); `frames` are entries `{f, pose, prev, k, open, blink, [facing]}`, each holding until the next one, written only where a value changes; the kit's `MascotLayer` finds the entry of the frame and only plays it. The mouth is closed outside `speaks` and after the narration ends.

## Motion

- **A pose change** eases out over 12 frames (SKILL.md section 4). It overshoots (14 frames, a soft bounce) only when three things hold: the brand tone's `mascot` is `full`, its `overshoot` is true, and the scene tone at that moment is loud (`punchy`, `hype`, `parody`). So `tech` (`punchy` allowed, no bounce) never bounces.
- **At most one pose change per 0.8 s** (an error), and none within 0.3 s of a scene's entrance or exit (a warning: two moves at once).
- **The exception to “one animated element at a time”:** the blink, the breath and the mouth are the mascot's background motion and do not count; a gesture does, hence the rule above.
- **Its entrance and exit:** a 10-frame rise and fade in, an 8-frame fade out.
- **One mascot per video,** counted by its presence, not by gestures.

## Layers and what the checks catch

The layer sits above the designed scenes and below callouts, memes and subtitles. `visual_plan.py validate`:
- error: a brand tone with `mascot: off`; no mascot in the brand; an unknown pose; a pose on a word the re-cut removed (naming it); pose changes under 0.8 s apart; `speaks` past the narration; the mascot's box (scaled, both sides if a pose is mirrored) in the UI zones (the project's `meme_layout.safe`), on the subtitle band (and the 30 px above it), over a scene's box, a callout's label, a placed meme or any `keep_clear` zone at the same time; a full scene at the same time left less than 540 px of text above it (y 250 down to 40 px above the mascot), or a full scene's own `--box` reaching down onto it;
- warning: a stand-in pose; a gesture at a scene's entrance or exit; drawn over a `panel` scene (its text is checked by `textcheck.py`); a stale `mouth.json`.

`visual_plan.py stage` refuses a missing or stale `mouth.json` (the narration re-cut, even to the same length) and a brand profile staged without its mascot. `textcheck.py` measures the drawn figure (`data-rk="mascot"`, the shapes, not the whole box) and reports text over it as an error, `on the mascot`.
