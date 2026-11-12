# Mascot from a ready character picture (PNG atlas)

When a brand already has its own character as an illustration, the kit can animate that picture instead of a mascot
drawn in code: `mascot_atlas.py atlas` cuts the poses out of the picture into one atlas, and the kit's `AtlasMascot`
shows the pose of the moment, opens the mouth to your recorded narration and blinks. Placement, timing and the mouth
track are the mascot engine's (the drawn mascot uses the same ones); this file covers the picture.

The approach comes from [skill-multik](https://github.com/artemiimillier/skill-multik) (MIT): a sheet of poses cut
into an atlas, guessed eyes and mouth, an overlay mouth and eyelid, optional talk and blink frames. Two things work
differently here: the background is removed by a fill from each cell's border instead of a color key over the whole
picture (which also took white eyes and white highlights on a white background), and every pose is placed by its head,
not by its silhouette.

## What the person brings

- **Their own illustration**: drawn by or for the brand, with the right to animate it. Not someone else's character,
  not a photo of a person. Making a character out of a photo is not part of this plugin.
- **One sheet in a grid** (rows x columns of equal cells, the same background in every cell, no grid lines or thin
  ones) or **a folder of PNG files named by pose**: `neutral.png`, `point_up.png`, …
- **Background**: a transparent PNG is best. One flat color works too: white, a green or blue screen. A gradient, a
  texture, a glow, a floor shadow or a photo behind the character is refused: export it on transparency.
- **Poses** from the dictionary: `neutral` (required: its head sets the size of every pose), `talk`, `point_left`,
  `point_right`, `point_up`, `palm`, `think`, `surprise`, `celebrate`, `shrug`, `wink`. The same character at about
  the same size, facing the same way, the head visible in every pose. A missing pose is replaced by the engine.
- **Talk and blink frames, recommended**: `<pose>-talk` (the same drawing with the mouth open) and `<pose>-blink`
  (eyes shut). Without them the kit draws an ellipse mouth and an eyelid over the picture.
- **Size**: the head at least ~80 px wide in the picture. Cells taller than 1000 px are scaled down first.

Say this to the person before they choose: **an overlay mouth over a drawn mouth looks worse than a drawn talk
frame.** On a face with a big drawn smile or outlined lips the ellipse sits on top of the drawing and reads as pasted
on. Two drawn frames per pose (mouth open, eyes shut) give a cleaner result than any overlay.

## Run

```bash
python "${CLAUDE_SKILL_DIR}/scripts/mascot_atlas.py" atlas <brand> sheet.png --grid 2x3 \
    --poses neutral,neutral-talk,neutral-blink,point_up,celebrate,-
python "${CLAUDE_SKILL_DIR}/scripts/mascot_atlas.py" atlas <brand> poses/        # a folder of <pose>.png
```

`--grid RxC` reads the sheet row by row; `--poses` names every cell in that order, `-` skips one. A single picture
needs neither (it is `neutral`). The script writes `brands/<brand>/assets/mascot/atlas.png`, `rig.json`,
`rig-check.png` and `rig-check.json` (the numbers and warnings, which `check` draws again), prints what it found and the `brand.py mascot <brand> --atlas assets/mascot/rig.json` command that
turns the mascot on in the profile. It does not edit `brand.json` itself. A run takes a few seconds per pose.

What it does:
1. **Cells.** A grid that does not divide the sheet evenly is cut inward, with a margin off the lines, so no pixel of
   a neighbor cell gets in. An empty cell stops the run with its number.
2. **Background.** A picture with real transparency is kept as drawn, even cut close to the figure. Flat: removed by a fill from the cell's border, with a soft edge, so
   white eyes on a white background stay. Background color **enclosed** by the character (between an arm and the
   body) cannot be told from a white detail (eye whites are enclosed too): every such patch is numbered on the check
   sheet and kept; `--holes 3,7` removes the ones you confirm. On a green or blue screen the character has none of
   that color, so enclosed screen color goes without asking and the spill is held down. A light part of the
   character touching the background (a white glove with no outline) goes with the background: an outline open
   there is marked with an exclamation mark on the sheet and warned about. A border of one color around a
   background that shades inward (a glow, a vignette) is refused like a gradient.
3. **The head places the poses.** On `neutral` the point between the eyes and the head width are guessed (the center
   of mass of the figure's top, the eye line at ~22 % of its height). Every other pose's head is found by matching
   neutral's head, its scale is taken from its width at the eye line (measured as on neutral), and the pose is
   scaled and moved so its head lands on the same point of the shared box: a raised
   arm changes the outline, not the head. Talk and blink frames are aligned to their pose's head the same way.
4. **Starting guesses**: eyes on the eye line, the mouth at ~34 % of the figure's height, its width from the head, the
   skin color from a ring around the mouth, the line color from the darkest lines.

## The check sheet: before the first render

The eyes, mouth and colors are guesses. Check them on every pose:
1. Open `rig-check.png`. At the top, the atlas: every frame outlined and named, a blue cross on the anchor (between
   the eyes), cyan dots on the eyes, a pink bar on the mouth (its length is `mouthW`). At the bottom, every pose in the
   shared box side by side with a blue line through the anchor: the head must sit on the same spot in all of them.
2. Orange circles `N?` are kept patches of background color. Eye whites are numbered too: leave them. A patch between
   an arm and the body is background: run `atlas` again with `--holes N` (the numbers stay the same for the same
   picture).
3. An orange exclamation mark: a light part may have been cut with the background. Get a transparent PNG, or a version with that
   outline closed.
4. Fix the guesses in `rig.json`, in atlas pixels: `eyes`, `mouth`, `mouthW`, `skin` (a sample of the face, `#rrggbb`),
   `ink` (the line color, used for the overlay mouth and the lashes). Then
   `python "${CLAUDE_SKILL_DIR}/scripts/mascot_atlas.py" check <brand> --fix` moves every pose so the point between
   its corrected eyes is the shared anchor, and draws the sheet again. Look again.
5. If the head of `neutral` was guessed wrong (the cross is not on the face, the poses come out at odd sizes), run
   `atlas` again with `--head X,Y,W`: the point between the eyes and the head width in sheet pixels (the `head:` line
   of the first run prints the guess to start from).
6. Add `--symmetric` only when the character may be shown mirrored: no text, logo or one-sided detail. Without it the
   kit never mirrors the picture.

## rig.json

```json
{"atlas": "atlas.png", "width": 701, "height": 887, "symmetric": false, "box": [300, 339], "anchor": [150, 132],
 "head": 104,
 "poses": {"neutral": {"cell": [4, 4, 195, 265], "offset": [53, 71], "eyes": [[82, 65], [119, 65]],
                       "mouth": [101, 95], "mouthW": 23, "skin": "#f0be96", "ink": "#170e14",
                       "talk": [4, 618, 195, 265]}}}
```

Rectangles are `[x, y, w, h]` and points `[x, y]` in atlas pixels; `offset` places the pose's frame in the shared
`box` so that its head is on `anchor`; `talk` and `blink` frames have the pose's size and offset; `head` is the head
width in the atlas.

## In the kit

`kit/mascot/AtlasMascot.tsx`, `atlasMascot(rig, atlasPath)`: one image of the whole atlas, cropped to the frame of the
pose of the moment.
- **Mouth**: the pose's talk frame from a medium opening; without one, an ellipse in the line color sized by the
  opening, a tongue when it opens wide.
- **Blink**: the pose's blink frame; without one (and over a talk frame), an eyelid in the skin color with a lash arc.
- **Pose change**: a switch of frame halfway through the change, no in-between drawing. Only where the brand tone
  allows a bounce (the change overshoots) the new pose settles from 97 % to full size.
- **Mirror**: only a `symmetric` picture.

## Limits

- No in-between drawings: every pose change is a cut. Keep changes rare and on meaning.
- A pose whose head is turned, hidden or drawn in another style is placed badly (its head does not match neutral's):
  leave it out or redraw it.
- A sheet with drop shadows, glow or a vignette is not one flat background: export the character on transparency.
