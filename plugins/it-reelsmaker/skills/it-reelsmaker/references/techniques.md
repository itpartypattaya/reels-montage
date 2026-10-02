# Special techniques

Each one only if the brief chose it (step 7). The cut-out figure itself is in `references/figure.md`; designed scenes are in `references/scenes.md`.

**Cut-out figure**: everything is in `references/figure.md`: `rembg` cut-out on `{{HEAVY_SERVER}}` (frames from `final.mp4` as JPG; the WebM with alpha and edge cleanup is assembled on the server; a check frame on a light and a dark background shows furniture in the mask right away), source-edge cuts, layouts.

**Text behind the person (hook).** A big word behind the figure but in front of the background, like a magazine cover. Offer it only if there is no room above the head for the whole hook: with a free “headroom” zone, a regular hook above the head reads better. Needs a calm, contrasting background behind the head; 1.5–3 s. In Remotion, three layers **inside one camera div**: video → word → `<OffthreadVideo src="person.webm" transparent muted />`. The word is ≤ 960 px wide, the figure covers only the bottom or the middle of the letters (≤ ~30%), the lead-in sits tight above the word. **The main risk is contrast:** light letters on a light wall disappear. The “antithesis” variant: the word is crossed out during a pause and replaced by a second word when that word is spoken.

**Presenter over a scene** (overview, review, stream). The speaker is cut out and stands in front of a screen recording, the video being reviewed, or a code scene. Layouts: “review”: the scene in a panel at the top, the presenter's forehead at its bottom edge; “stream”: the scene fills the frame, a small presenter in a corner; “window”: no cut-out, the speaker's video in a rounded window. Scale by the face measurement, side by the source-edge cuts (no chopped-off arm in the frame), separation from the scene by composition, with no outline or shadow.

**“Framed” format** (horizontal source: Zoom, webinar, podcast). A window of ~1030×1240 at (25, 340), ~50 px corner radius with no feathering, background in the style color ⟨YOURS⟩; text only inside the window and above y 1500; a small all-caps label above the window. Do not scale to 1080×1920 in `cut.py`; the camera works relative to the window; change shots when the speaker changes.

**LUT**: see step 6.

**Phone mockup on the CTA.** A PNG phone frame with a transparent screen ⟨YOURS: frame files⟩, with a screen recording or screenshot of where the CTA leads underneath. Compute the screen rectangle from the frame's transparent area (look for the edges not at the center but at a quarter of the width: the notch gets in the way). Frame 480–600 px; entrance: a 40–60 px rise and `rotateY` 10–12° → 0 over 14–18 frames, no “spinning 3D”. Cover other people's personal data in the screenshot.

**Light flash instead of a transition.** A 6–10-frame flash in `screen` mode at a change of topic blocks, 1–2 per video, within the brand tone's ceiling (none for `premium`, up to 3 for `bold`). Procedurally: a radial warm-white spot with opacity 0 → 0.55 → 0. If the brand forbids light effects, don't use it.

**Slide scene**: covers choppy speech. The speaker shrinks to ~0.42 and slides to the free edge (background in the style color), a panel with the thesis slides in from the other side, points appear on their words. 1–2 times, 3–5 s, the panel no lower than y 1500.


**Full-screen key phrase**: a “punch”, 1–2 times per video. A field in the style color wipes in over 8–10 frames, a pictogram “draws itself”, 3–6 words come up from below one by one on their words. Hide subtitles for that time. Not on the hook and not on the CTA.
