# Cut-out figure: text behind the person and presenter over a scene

The speaker is cut out of their frame (a mask on every frame) and used in two ways:
- **text behind the person** — a big word behind the head but in front of the background, on the hook;
- **presenter over a scene** — the speaker stands in front of a different picture: a screen recording, a video under review, a website, B-roll, a code scene. As in reviews, breakdowns and streams.

Both techniques are used when the brief calls for them, not by default.

## 1. Cutting out the figure

**Tool** — `rembg` (`pip install "rembg[cpu,cli]"` into a separate venv, ~810 MB), model `u2net_human_seg` (~170 MB, trained for people). Install it yourself (best in a separate venv) and download the model once: `rembg d u2net_human_seg`; the plugin never downloads models. It runs on this computer, at low priority. Segmentation is heavy: on a laptop with 8 GB, cut out at 720 px wide where the figure is shown smaller (presenter over a scene) and keep spans short. Running the cut-out on your own server over SSH is a feature of the online add-on `it-reelsmaker-online` (it follows the same steps and adds a server-side queue and memory check).

**Pipeline** — `matte.py cut edit/<id> --from 12.4 --to 19.0 [--width 720] [--name host]` (`--dry` gives the frame count and the time estimate; `matte.py place` computes the presenter layout, section 2). What it does:
1. Frames of the span come **from `final.mp4`**, not from the source: the mask must match the cut and sped-up video frame for frame. If the speed in `cut.json` changed, rebuild the mask. Extract them as JPG (`-q:v 2`) into a temporary folder.
2. `rembg p -m u2net_human_seg in/ out/`.
3. **Build the WebM with alpha** from the cut-out frames and clean up the mask edge:
   ```text
   split[c][a];[a]alphaextract,erosion,gblur=sigma=0.8,tmix=frames=3:weights='1 2 1'[m];[c][m]alphamerge,format=yuva420p
   -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 -b:v 3M
   ```
   A 1 px erosion removes the gray fringe left from the old background, the blur removes the “staircase”, and averaging the alpha over 3 frames removes flicker on the hair contour. **The averaging is centered**: `tmix` averages the current frame and the two previous ones, so the mask is shifted one frame back (`…tmix…,trim=start_frame=1,setpts=PTS-STARTPTS,tpad=stop=1:stop_mode=clone`); otherwise on a fast gesture the contour lags behind the hand. `ffprobe` will show `yuv420p` + the tag `alpha_mode=1` — this is normal: VP9 alpha is stored separately. Decode such a file in ffmpeg only with `-c:v libvpx-vp9`; the built-in decoder loses the alpha.
4. Next to it, record the figure's box from the alpha, the top of the head, and **which source edges the figure touches** (section 3) — as a frame count, not a fraction: a single frame with a source-edge cut on a long span must not get lost in rounding.
5. Remove the temporary frames — on error too.

**Reliability:** cut-outs run one at a time under a project lock (two at once double the memory); before a run and again under the lock the script checks free memory: model + ~1 GB of headroom; the run's exit code is 0 only when everything is done (no alpha, edge cuts not checked or a failed check frame → non-zero). “Edge-cut check not performed” ≠ “no edge cuts”: without edge-cut data, do not compute the layout.

**Time** (4 CPU cores): ~1 s per 1080×1920 frame, ~0.5 s at 720p, plus ~45 s for model startup and transfer. A 3 s hook at 1080 takes about 2.5 min; 1 s of presenter at 720 about a minute. State the estimate in the brief before the run.

**Model memory — before launch.** There is one working model, `u2net_human_seg`; it fits in ~1.5 GB. The script runs only measured models (a “model → peak memory” table); a new model would first be measured on 1–2 frames under supervision. Running out of memory stalls the whole computer, and on a shared machine it hits other programs too.

**Check frame — mandatory.** The middle of the span over a light and a dark background side by side. A fringe shows on one of the backgrounds, while **stuck furniture, a piece of wall, a cushion** show on both. Real case: `u2net_human_seg` left the back of a gray armchair behind the shoulder in the mask — on a different scene that becomes a “ghost”. What to do: a technique where the leftover is not visible (text behind the person — the background is the same), the “window” layout (section 2), and when shooting — the speaker in front of a wall, not against the back of an armchair.

**A manual option for quality, outside the script:** if `u2net_human_seg` cut the figure out poorly (furniture, ragged hair) **and** the machine has ≥ 7 GB of free memory, `birefnet-portrait` (973 MB) can be tried by hand with rembg. On CPU it takes ~6.6 GB per 720p frame: on a machine with 8 GB the process was killed for lack of memory on the very first frame.

## 2. Presenter over a scene

**Status:** tested on a 1 s piece, not yet verified in a finished video; check the stills of every layout with extra care.

**When to offer it.** The speaker talks about something that can be shown: “look at this résumé”, “this is what the page looks like”, “let's break down this video”. The scene must exist. Not on the hook (a large face matters more there), 3–15 s at a time, 1–3 times per video. The background behind the speaker is calm and does not blend with their hair and clothing.

| Layout | What it looks like | Presenter | When |
|---|---|---|---|
| **“Review”** | the scene in a rounded panel at the top (~x 40, y 230, 1000×900, radius ~36), below it a background in the brand color | cut out, at the edge, face 230–300 px; **forehead at the panel's bottom edge**, the hair slightly overlaps the panel — this shows depth; the body goes off the bottom of the frame | the scene needs to be examined: a document, a website, someone else's video |
| **“Stream”** | the scene fills the frame | cut out, small, in a bottom corner, face 150–190 px; the corner of the scene under it is darkened with a soft radial gradient (~38 %) | a dynamic scene that is not read in fine detail |
| **“Window”** | the scene fills the frame | **no cut-out**: the speaker's video in a rounded window 360×480 in a bottom corner (position set separately, by default above the UI), framed on the face, optionally a thin ring in the brand color | busy background, furniture in the mask, a long segment, the server is busy. Free and instant |

**Scale and placement — by calculation, not by eye.** Scale = target face height / the **median** face height of the presenter from the measurement (`references/faces.md`): in each sample take the largest face, over the span take the median. The union box of all faces does not work for scale: head movement and a second person inflate it, and the presenter comes out smaller. The figure's video is placed in a corner so that its **source-edge cuts coincide with the frame edges** (section 3). In “review” the figure is shifted down until the forehead reaches the bottom edge of the panel; the bottom of the video must still not be higher than the bottom of the frame. Checks: chin above the UI (y ≤ 1500), face not under the like-button column (x ≤ 960), in “review” the face does not overlap the panel. Record the figure's box in `keep_clear` so that memes and cards do not land on it.

**To make the figure fit in and read well:**
- **long segments**: estimate first (`matte.py cut … --dry`); more than ~15 min of cut-out time → cut out only where the scene is really needed, or use the “window” layout;
- **warm speaker on a cold scene**: warm the scene slightly, not the speaker;
- **separation by composition, not effects**: overlapping the panel edge, a darkened corner, a solid brand background. An outline, glow or shadow around the figure falls under the same ban as for text;
- **matching light and color**: the figure already has the video's color (it comes from `final.mp4`); match the scene to it — dim a white screen recording to ~90 %, otherwise it “blows out” the face next to it;
- **the face stays clear**: nothing closer than 60 px to the face;
- **subtitles** in “review” go on the free side next to the head (width ≤ 420 px, y 1150–1450), or are hidden if the scene itself has text; in “stream” and “window” — the usual band, if it does not touch the figure;
- **the important part of the scene** is on the side opposite the presenter; point to it with focus brackets or a highlight on the word;
- **entrance** — the panel drops by ~60 px, the figure rises from below over 12–16 frames, `Easing.out(cubic)`; **exit** is faster, ~8 frames; a segment boundary on a pause is a hard cut;
- **sound** comes from the main video, the figure is `muted`; the scene's sound is off;
- **someone else's video in the scene** — briefly (up to ~10 s in a row), with the source credited; other people's faces and personal data are covered.

## 3. Source-edge cuts — no chopped-off arm on screen

Where the figure touches the edge of **its own** frame — an arm or elbow at a side edge, the body at the bottom, hair at the top — the cut-out has a straight cut. In its own video this is invisible: the frame edge is there. On a different scene or a cutaway, a cut in the middle of the screen looks like a **chopped-off arm** and gives away the edit at once.

Real case: in the “stream” layout the speaker's arm touched the left edge of the source, while the figure stood in the right corner — the cut arm hung in the middle of the frame. The figure should have been placed at the left border of the video.

**Rules:**
- **Every edge the figure touches coincides with a frame edge.** Arm at the left edge of the source → the figure only at the left edge of the frame, the left edge of its video = x 0. At the right edge → only on the right. Bottom of the body cut off → the bottom of the figure's video is no higher than the bottom of the frame; the excess goes past the edge.
- **Check in screen coordinates at any scale**: the figure's edge that the body touches lies on the frame edge or beyond it. This applies at ×1 scale too — in “review” the figure is shifted down, and a top cut would otherwise end up inside the frame.
- **Count touching over all frames of the span**, not one: an arm that reached the edge during a gesture in even one frame is already a cut. Algorithm: the alpha is downscaled to 270×480; ≥ 4 opaque pixels in the outermost column or row (≈ 16 px at 1080×1920; a fingertip already counts) → the edge is touched; the result is the number of frames touching each edge (older files may hold a fraction; any value above 0 means touched).
- **The script picks the side from the cut**, not by taste; a manual side that contradicts the cut is rejected with a hint.
- **Touching both side edges** (arms spread, a wide gesture) — do not place the figure in a corner: a cut will remain on one side. Options: a span without this gesture, a full-frame figure (×1), “window”.
- **A top cut** (hair touches the top of the source) is always visible when the figure is scaled down — use only a span where the head is fully in frame, or “window”.
- **A cut can be hidden only by the frame edge or by an opaque element over the figure** that covers the cut line entirely (a panel, a card). Feathering, darkening or a semi-transparent card do not hide a cut — the result is a “melting” arm.
- This applies to any insert of a cut-out figure over another picture: cutaways, B-roll with a presenter, slide scenes with a cut-out speaker. It does not apply to text behind the person: there the figure stays in its own frame in its own place.

**Check.** A still frame with the widest gesture of the span: not a single straight line on the arm, shoulder or body inside the frame.

## 4. Text behind the person (hook)

A big word stands behind the speaker's figure but in front of the background: the head and shoulders cover part of the letters, as on a magazine cover. The frame looks “designed” rather than shot on a phone.

**When.** **Only if there is no room above the head for the whole hook** (margin ≥ 60 px from the top of the head per the face measurement). Real case: the technique was built and worked technically, but it was removed — the letters behind the head read worse, there was enough room above the head, and the whole hook above the head turned out better. Further conditions: a hook headline of 1–2 words and a **calm, contrasting background behind the head** (a wall, sky, a window). A busy background, a person at the edge, or hair the same color as the background → a ragged contour; do not offer it. Duration — the hook only, 1.5–3 s.

**In Remotion**, three layers **inside one virtual-camera `<div>`** — otherwise on a push-in the text and the figure drift apart: video → big word → `<OffthreadVideo src="person.webm" transparent muted />`.

**Typography:**
- one or two words, 180–320 px, bold grotesque sans-serif; the word ≤ 960 px wide. A word of 8+ letters in caps does not fit at 180 px — the size drops to ~130 px, and that is fine; a shorter word is better;
- the figure covers no more than ~30 % of the word, and only the **bottom or middle** of the letters; the first and last letters are fully visible;
- **the lead-in and the big word are one phrase** (`typography.md`): the lead-in sits tight above the word (gap 15–25 px), centered on it, in front of the figure and in the same camera `<div>`. A real fix: the lead-in hung at the top of the frame and the word 300 px lower behind the head, and it read as two separate messages;
- **contrast**: light letters on a light wall disappear. Light background — dark text, dark background — white. Check on a still frame;
- the word's exit finishes before the mask ends, so that on the last frame the letters do not end up over the person.

**“Antithesis” variant.** Word 1 behind the head → in the pause before the second word, a line in the accent color strikes it through (8–10 frames) → word 1 moves down, word 2 rises into its place **on its own spoken word**, and the lead-in changes with it. A soft whoosh on the change. Each word gets its own font size so that both are ≤ 960 px.

**Check.** Still frames at the start, middle and end of the hook: the contour has no fringe, the text does not “jump” over the figure, the word reads.
