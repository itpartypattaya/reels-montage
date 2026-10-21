# Callouts: a label pointing at an object (experimental)

A mark on an object in the frame, a leader line drawn from it, and a label that wipes in from the line, designed in
code in the brand's colors and fonts; the kit's `CalloutLayer` draws it from the plan, with no per-video composition.
Five variants: `tag` (the name on the style's marker plate, a short detail in small caps under it), `line` (the name
over the line, no plate), `badge` (a number in a circle), `ring` (a ring around the object instead of the dot),
`dimension` (a measuring line between two points). The dot stays still, follows keys set by hand, follows the object
tracked by `track.py`, or follows a person's face.

**Experimental**: a still `tag` was checked on one real talking-head clip (a static tripod shot with camera.json
push-ins: the dot stayed on the object, the label read, `textcheck.py` and the render's face audit found nothing);
`track.py` on a real handheld tour (a tower on a pan: on it to the joint of the rough cut, then faded); none of it in a
published video yet. Offer it only where the content names objects in the frame, with the word "experimental" in the
plan.

## When it helps

A tour or a review that names things: a room (sofa, kitchen, view), a desk setup, a product, a dish and its price, the
tools on a workbench; the host's name as they appear. One callout per named object, on the word that names it. Not
for abstract ideas (a `word` scene), not for a thesis (a card).

| variant | for | text |
|---|---|---|
| `tag` | an object and a characteristic (the default) | 1–3 words, an optional short detail |
| `line` | the same, lighter, for a premium or calm brand | only over a dark or busy picture (validate measures it) |
| `badge` | a price, a rating, a count | a number, an optional word under it (a source is required) |
| `ring` | an object among others: the ring shows which one | as `tag`, plus `--radius` around the object |
| `dimension` | a size: a desk's width, a room's length | the measure (a source is required); two still points |

**The dot must stay on the object.** The anchor is a point of the rough cut: it follows the virtual camera and the
template's drift exactly, and the footage's own movement only through keys or a track:

- a tripod shot, a static detail or a pause in a handheld walk: a still anchor;
- a slow pan along an object (a shelf, a facade): two or three `--keys`;
- a handheld walk or pan where the object stays in view: `track.py` follows it (it holds through a pan of ~400 px/s
  that keeps the object in frame; it gives up where the object leaves the frame or blurs past recognition);
- a person: `--person left|right|center`, the dot on the shoulder under their face (faces.json).

A whip pan that throws the object out of frame within a second is not for a callout: B-roll or a card.

## Offering it

A callout is offered only when three things hold for a moment of the video, and the offer names those moments:

1. **The words name a thing the viewer sees right then**: a room, a piece of furniture, a dish, a device, a tool, the
   host. In step 7 the agent finds such moments in the transcript itself (“here”, “look”, “this is”, a named object);
   in step 7a the plan's hint “pointing at an object” marks the same signal on its spans. A thing that is named but
   not in the frame gets B-roll or a card, not a callout.
2. **The dot can stay on the thing** for 2–3 s: it holds still, or a track or keys follow it (above). Look at the
   frame at that word first; `add` then measures the picture under the dot (the mean change of the picture around it,
   of 255: up to 10 holds still, above 25 the object leaves the dot; measured on real clips: a wall or a painting on a
   tripod 1–6, a handheld walk through a room 56–117, a microphone in a gesturing hand 92, a tracked tower on a fast
   handheld pan 6–12). When it says the picture moves, run `track.py` before giving up on the callout.
3. **There is room** for the label clear of the face and the subtitles (validate checks it).

**Where in the skill.** Step 7, the techniques question: callouts are not a standing option. When at least one moment
passes all three, they become an option that names the objects and the moments, for example “Callouts on objects
(experimental): ‘sofa’ 0:16, ‘the view’ 0:19 — a dot, a line and a label in the brand's colors”; recommend them for a
tour, a review, a setup or a dish, not for a talking head with nothing to show. When things are named but the shot
whips past them, there is no option: one line under the question says why (“callouts won't hold here: the camera
whips past the objects”), and B-roll or a card is offered for that moment if it helps. Step 7a: each chosen callout
goes into the plan on the word that names the object, with its anchor read from that frame, the variant chosen by the
table above and the label's words shown to the person exactly as they will appear. Before the render, each callout's
storyboard frame (`board.py`) is looked at; after it, the stills at each callout (`check.py`).

**How many.** One per object, on its word; 1–3 in 30 s (a calm or premium brand tone: 1–2 in the whole video); never
two entering together, never more than two on screen. None under the hook headline (the first 2.4 s) and none on the
CTA or the end card. A label names, it does not explain: one to three words and a short detail.

**Not offered (yet):** an object the speaker holds and turns (the track loses it), the framed format, a slide or a
screen recording (a `ui` scene points better there).

## Adding one

```
visual_plan.py add edit/<id> --kind callout --variant tag --at word:sofa#1 --dur 2.6 --anchor 620,280 \
    --lines "SOFA" "LIVING ROOM" [--side left|right] [--below] [--tone calm] [--source speech --source-ref "…"] \
    --what "the sofa by the window" --why "names the furniture she talks about"
```

- `--anchor X,Y`: the object's point on the 1080×1920 rough cut (`final.mp4`) at the callout's first frame, read from a
  still of that moment (`faces.py` stills or `board.py`): an edge, a corner or a print of the object reads better than
  its middle, and gives a track something to hold on to.
- `--lines`: the subject (one to three words) and an optional detail; the label is ~360 px for a 7-letter word with a
  12-character detail, at most 640 px. Text in the subtitles' language; translated subtitles do not translate it.
- `--side`: the label's side; without it, the side where the label stays in the safe zone. `--below`: under the dot.
- A number on the label (price, size, year) needs `--source`; `agent` is a warning to verify.
- The callout moves with its word when the rough cut changes (`at` is kept), like a scene.

The other variants and anchors:

```
… --variant badge --lines "$49" "PER MONTH" --source speech …       # a circle 150-260 px across
… --variant ring --radius 90 …                                        # the ring's radius on the rough cut
… --variant dimension --anchor 150,1150 --to 650,1150 --lines "120 CM" --source speech …
… --variant line …                                                    # no plate: validate measures the contrast
… --keys 0:300,1150 1.2:420,1140 2.4:540,1150 …                      # T:X,Y from the callout's start; T:- hides it
… --person left|right|center --lines "ANNA" "HOST" …                  # faces.json needed (faces.py scan)
```

**Tracking** (`track.py edit/<id> l01 [--dry]`, OpenCV and numpy in the Python that runs it): add the callout with its
anchor on the object at its first frame, then run it. It follows the corners around the anchor frame by frame
(optical flow, each point checked by following it back), moves the dot by the common shift, turn and scale of the
points nearest to it (the wall around a small object does not outvote it; the scale grows a ring), and writes the path into the callout (`path`, `path_by: track`). It stops at a joint of the rough cut
(the dot fades out by the joint) and where the object is lost (held 0.3 s, then faded); a dot hidden for more than
20 % of the callout is a warning: shorten it. A track that stays within 40 px of the anchor and within 10 % of its size is not a
path: the callout keeps a still anchor. The track remembers the rough cut, the anchor and the callout's time: when one changes (a new
cut, a moved word), validate asks to run `track.py` again. `remove` and `add` again to change the anchor.

**Keys** (`--keys`): straight between keys, held before the first and after the last; `T:-` fades the dot out toward
that key and keeps it hidden until the next one. For a slow, even pan; a handheld shot needs a track.

**A person** (`--person`): faces.json has no identity, so the person is the face on the `left`, the `right` or in the
`center` of the frame, picked in every sample (0.25 s) and smoothed; the dot goes to the shoulder on the label's side
(0.85 of the face's width out from its middle, 1.25 of its height down), the label to the open side of the frame.
Where no face is found the dot is hidden. Two people crossing each other swap: check the stills.

## Layout and motion

Every number is in `kit/anchor.ts` and repeated in `visual_plan.py` (`CALLOUT`, `CALLOUT_TIMES`); a test runs both on
the same points, for every variant and for moving anchors.

- The dot: a 28 px disc in the plate's ink with the marker color inside (no glow or outline). The line: 5 px, the
  marker color, 90 px at 45° to the elbow, then 48 px level to the label, which it meets at the title's middle.
- `tag`: the title plate 70 px high, the heading font at 52 px / 700 on the style's marker plate (`look.mark` /
  `onMark`); the detail plate under it: 50 px, the body font at 34 px / 600, caps, +0.12 em, on the primary color.
- `line`: the level line runs on under the title, the title stands on it in the brand's `text_on_primary`, the detail
  hangs under it; no plate, no shadow.
- `badge`: the line ends at a circle of the marker color, 150–260 px across; the number at 52 px fitted to 78 % of it,
  the word under it at 26 px caps fitted to 80 %. The circle grows in from 40 %.
- `ring`: a 6 px ring of `--radius` (times the camera's zoom and the track's scale) drawn around in the dot's time; the
  line leaves it at 45°; a tag's label.
- `dimension`: a line between the two points with 32 px end ticks; the ticks land, the line grows from its middle to
  both ends, the label (a tag's plate) sits 14 px above its middle (`--below`: under it), or 14 px beside an
  upright measure, on `--side`.
- Entrance, at the calm tone: the dot frames 0–6, the line draws 3–11, the title wipes 8–18, the detail 11–21, the wipe
  running away from the line. Other tones scale it by their own entrance (punchy 8/14, hype 5/14, parody at once).
  Exit: a 6-frame fade; a hidden anchor fades it too. The dot pulses twice only where the brand tone allows overshoot.
- One at a time: a second callout enters at least 0.6 s after the first, at most two on screen.

## What validate checks

On screen every 0.25 s of the callout and at every row of its path, with the anchor where its path puts it, through camera.json or the drift, as
the kit draws it (a sample where the anchor is hidden is skipped):

- the dot (a dimension's two ends, a ring whole) inside the frame (error), outside the app's UI zones (warning),
  off the subtitle band; the label
  inside x 40–960, y 220–1500;
- the label clear of every face by 60 px, the line clear of every face by 20 px (a dot or a ring on a face is a
  warning: `--person` points at a person);
- the label and the line off the subtitle band (except where the plan hides the subtitles: hide-subs, a scene that
  hides them); the label, the dot or ring and the line off the other graphics (keep_clear, overlay scenes, windows,
  popup memes, the corner logo, the hook headline at its own height) and off each other;
- no camera shot change inside the callout (the dot would jump with the picture);
- the picture under the dot holds still, along its path for keys and a track, the patch growing with a track's scale
  (error above 25 of 255, a warning above 10; not measured without `final.mp4` or ffmpeg, then check the stills); a person's dot follows the face detector and
  is not measured;
- `line`: the text's contrast against the lightest and the darkest 5 % of the picture under it, at least 3:1;
- a track made on this rough cut, with this anchor and time; a dot seen at least 80 % of the callout (a warning);
- not over a scene or an insert that moves or covers the rough cut (split, panel, window, full, a ready replacing
  B-roll, a ready cutaway meme): the dot would point at nothing;
- the reading time after the entrance and before the fade (the scenes' floor: 0.8 s up to 3 words);
- the variant's own: a ring's radius 24–400, a badge no wider than 260 px, a dimension's two points at least 80 px
  apart and no keys, track or person on it;
- the times the kit draws: from frame round(start × 30), for round(dur × 30) frames;
- refused for now: the framed format, a horizontal rough cut without it, and the "scenes only" format.

A callout that passes becomes `ready`; export writes it to `props.callouts` (a person's path computed from faces.json)
and its label, per 0.25 s where it is drawn, to `keep_clear`, so `faces.py audit` checks the render and the memes or
windows placed later keep off it. `textcheck.py` measures the label as `callout:<id>`. The cover (`ReelCover`) does not
draw callouts.

## Not yet

The framed format; an object the speaker holds and turns; telling people apart (the face on the left, right or center
is picked per sample); a dimension on a moving shot.
