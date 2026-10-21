# Callouts: a label pointing at an object (experimental)

A dot on an object in the frame, a leader line drawn from it, and a label that wipes in from the line: the object's
name on the style's marker plate, an optional short detail in small caps under it. Designed in code in the brand's
colors and fonts; the kit's `CalloutLayer` draws it from the plan, with no per-video composition.

**Experimental**: checked on one real talking-head clip (a static tripod shot with camera.json push-ins: the dot stayed
on the object, the label read, `textcheck.py` and the render's face audit found nothing), not yet in a published
video. Offer it
only where the content names objects in the frame, with the word "experimental" in the plan.

## When it helps

A tour or a review that names things: a room (sofa, kitchen, view), a desk setup, a product, a dish and its price, the
tools on a workbench. One callout per named object, on the word that names it. Not for abstract ideas (a `word` scene),
not for a thesis (a card), not for the speaker's name (a caps label on a card or the framed label).

**The picture must hold still under the dot.** The anchor is a point of the rough cut: it follows the virtual camera
and the template's drift exactly, but not the footage's own movement. A tripod shot, a static detail shot or a pause in
a handheld walk is fine; a walking pan moves the object away from the dot within a quarter of a second (a real
apartment tour: the sofa moved 200+ px per 0.25 s). Pick a still stretch of 2–3 s, or leave the object without a
callout; `add` and validate measure it (below).

## Offering it

A callout is offered only when three things hold for a moment of the video, and the offer names those moments:

1. **The words name a thing the viewer sees right then**: a room, a piece of furniture, a dish, a device, a tool.
   In step 7 the agent finds such moments in the transcript itself (“here”, “look”, “this is”, a named object); in
   step 7a the plan's hint “pointing at an object” marks the same signal on its spans. A thing that is named but not
   in the frame gets B-roll or a card, not a callout.
2. **The picture holds still under the thing** for 2–3 s: a tripod shot, a detail shot, a pause in a handheld walk.
   Look at the frame at that word first; `add` then measures it (the mean change of the picture under the dot, of 255:
   up to 10 holds still, above 25 the object leaves the dot and validate refuses it; measured on real clips: a wall or
   a painting on a tripod 1–6, a handheld walk through a room 56–117, a microphone in a gesturing hand 92).
3. **There is room** for the label clear of the face and the subtitles (validate checks it).

**Where in the skill.** Step 7, the techniques question: callouts are not a standing option. When at least one moment
passes all three, they become an option that names the objects and the moments, for example “Callouts on objects
(experimental): ‘sofa’ 0:16, ‘the view’ 0:19 — a dot, a line and a label in the brand's colors”; recommend them for a
tour, a review, a setup or a dish, not for a talking head with nothing to show. When things are named but the shot
moves under them, there is no option: one line under the question says why (“callouts won't hold here: the camera
moves past the objects”), and B-roll or a card is offered for that moment if it helps. Step 7a: each chosen callout
goes into the plan on the word that names the object, with its anchor read from that frame and the label's words
shown to the person exactly as they will appear. Before the render, each callout's storyboard frame (`board.py`)
is looked at; after it, the stills at each callout (`check.py`).

**How many.** One per object, on its word; 1–3 in 30 s (a calm or premium brand tone: 1–2 in the whole video); never
two entering together, never more than two on screen. None under the hook headline (the first 2.4 s) and none on the
CTA or the end card. A label names, it does not explain: one to three words and a short detail.

**Not offered (yet):** an object the speaker holds or moves, a person, a walking pan, the framed format, a slide or a
screen recording (a `ui` scene points better there).

## Adding one

```
visual_plan.py add edit/<id> --kind callout --variant tag --at word:sofa#1 --dur 2.6 --anchor 620,280 \
    --lines "SOFA" "LIVING ROOM" [--side left|right] [--below] [--tone calm] [--source speech --source-ref "…"] \
    --what "the sofa by the window" --why "names the furniture she talks about"
```

- `--anchor X,Y`: the object's point on the 1080×1920 rough cut (`final.mp4`), read from a still of that moment
  (`faces.py` stills or `board.py`): an edge or a corner of the object reads better than its middle.
- `--lines`: the subject (one to three words) and an optional detail; the label is ~360 px for a 7-letter word with a
  12-character detail, at most 640 px. Text in the subtitles' language; translated subtitles do not translate it.
- `--side`: the label's side; without it, the side where the label stays in the safe zone. `--below`: under the dot.
- A number on the label (price, size, year) needs `--source`; `agent` is a warning to verify.
- The callout moves with its word when the rough cut changes (`at` is kept), like a scene.

## Layout and motion

Every number is in `kit/anchor.ts` and repeated in `visual_plan.py` (`CALLOUT`, `CALLOUT_TIMES`); a test runs both on
the same points.

- The dot: a 28 px disc in the plate's ink with the marker color inside (no glow or outline). The line: 5 px, the
  marker color, 90 px at 45° to the elbow, then 48 px level to the label, which it meets at the title's middle.
- The title plate: 70 px high, the heading font at 52 px / 700 on the style's marker plate (`look.mark` / `onMark`).
  The detail plate under it: 50 px, the body font at 34 px / 600, caps, +0.12 em, on the primary color.
- Entrance, at the calm tone: the dot frames 0–6, the line draws 3–11, the title wipes 8–18, the detail 11–21, the wipe
  running away from the line. Other tones scale it by their own entrance (punchy 8/14, hype 5/14, parody at once).
  Exit: a 6-frame fade. The dot pulses twice only where the brand tone allows overshoot.
- One at a time: a second callout enters at least 0.6 s after the first, at most two on screen.

## What validate checks

On screen every 0.25 s of the callout, through camera.json or the drift, as the kit draws it:

- the dot inside the frame (error), outside the app's UI zones (warning); the label inside x 40–960, y 220–1500;
- the label clear of every face by 60 px, the line clear of every face by 20 px (a dot on a face is a warning: pointing
  at a person is not checked yet);
- the label and the line off the subtitle band (except where the plan hides the subtitles: hide-subs, a scene that
  hides them); the label, the dot and the line off the other graphics (keep_clear, overlay scenes, windows, popup memes,
  the corner logo, the hook headline at its own height) and off each other;
- no camera shot change inside the callout (the dot would jump with the picture);
- the picture under the dot holds still (error above 25 of 255, a warning above 10; not measured without
  `final.mp4` or ffmpeg, then check the stills);
- not over a scene or an insert that moves or covers the rough cut (split, panel, window, full, a ready replacing
  B-roll, a ready cutaway meme): the dot would point at nothing;
- the reading time after the entrance and before the fade (the scenes' floor: 0.8 s up to 3 words);
- the times the kit draws: from frame round(start × 30), for round(dur × 30) frames;
- refused for now: the framed format, a horizontal rough cut without it, and the "scenes only" format.

A callout that passes becomes `ready`; export writes it to `props.callouts` and its label, per 0.25 s, to `keep_clear`,
so `faces.py audit` checks the render and the memes or windows placed later keep off it. `textcheck.py` measures the
label as `callout:<id>`. The cover (`ReelCover`) does not draw callouts.

## Not yet

Tracking a moving object, keyframed anchors, the variants without a plate, with a ring or with a dimension line, the
framed format, a callout pointing at a person: planned, not built.
