# Faces in frame: measured by a model, not by eye

The rule “no text on a face, chin above the subtitles” is checked with numbers. A face-detection model (YuNet) gives a face box on every frame. These boxes are used to compute:
- free zones for the hook and cards;
- subtitle height;
- meme placement;
- the render audit of the finished video.

## Installation

- **Model** — `face_detection_yunet_2023mar.onnx` from the official OpenCV repository, `opencv/opencv_zoo`, folder `models/face_detection_yunet/`, 232,589 bytes. Use the direct link to the file, not to a Git LFS pointer: `https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx`. Keep it outside the project, for example `~/.config/it-reelsmaker/models/face_detection_yunet.onnx`.
- **OpenCV ≥ 4.8**: `opencv-python-headless`. It does not have to be installed system-wide; you can run it through `uv run --with opencv-python-headless python …`. OpenCV 5 no longer ships Haar cascades; only `cv2.FaceDetectorYN` works.

```python
d = cv2.FaceDetectorYN_create(model_path, "", (320, 320), 0.6)  # confidence threshold 0.6
d.setInputSize((w, h)); _, faces = d.detect(img)                 # faces[i][:4] = x, y, w, h; faces[i][14] = score
```

No model: everything works as before — the agent looks at frames with a grid and sets the head box by hand.

## False “faces”: knees, hands, clothing folds

The model sometimes sees a face where there is none: in knees, folded hands, clothing folds. Most often this happens at the bottom of the frame, that is, in the subtitle zone. **This is not a flaw in the shot**; do not move graphics to avoid such boxes: they are discarded automatically.

**Real case.** A seated monologue: 246 samples, the real face in every one — confidence 0.94–0.95, the box taller than wide (h/w ≈ 1.37). Plus 37 “second faces” on knees and hands: confidence 0.60–0.76, the box almost square or landscape (h/w 0.81–0.96), twice as wide as the face and below the chin. Without the filter, the zone calculation reported “chin at 1766 — no room for subtitles”, and the render audit reported a false overlap with the subtitles.

**Plausibility filter** — applied when measuring and when reading any older measurement:
- a box with confidence **≥ 0.85** is always a face and is never discarded;
- a weak box is discarded if it is **directly below a face of the same person**: its top is below the chin of a confident face in that frame **and** its horizontal center is within that face ± half the face's width — hands, knees. A second person sitting alongside does not fall under this;
- otherwise no single indirect sign decides anything (a tilted head can look “square”, a face in B-roll is smaller). A box is discarded only when **two of three** signs agree:
  - **not face proportions** — h/w < 1.05 (a face box is taller than wide: 1.2–1.5);
  - **size unlike the faces around it** — width outside 0.35–1.8 of the median of confident faces in a ±2 s window (a shot change or B-roll does not break the comparison);
  - **appeared in a single sample** with confidence < 0.7 — the time-adjacent samples (no more than 1.5 steps away) have nothing at this spot. For several widely spaced frames (checking a meme on three frames) this rule is off.

A second real person in the frame (a two-person sketch, someone lower down at the side) passes: they are not under someone else's face, and their box has face proportions and a similar size.

Do not lose discarded boxes: store them separately (`samples[].rejected` with a reason), and in the measurement and audit reports add a line “discarded false ‘faces’: N (reason — count), interval”. A “no filter” mode is for debugging. If the filter threw out a real face (the person lay down or tilted their head strongly), the report shows it: “no face” where there is one — then check the frames by eye.

**Verified:** rough cut — all 37 false boxes discarded, none of the 246 confident ones discarded; render — 2 false boxes discarded, audit 0 overlaps (previously 1 false one); synthetic tests — knees and a hand under a face, a square-box “giant”, and knees in a frame with no confident face were discarded; a second person alongside, someone lower down at the side, a tilted “square” head, and a large box with normal proportions were kept.

## 1. Measurement on the rough cut (after `cut.py`)

1. Extract frames of `final.mp4` every 0.25 s in one ffmpeg pass: `fps=4,scale=540:960:force_original_aspect_ratio=increase,crop=540:960`. Half size: faster, and faces are found just as well.
2. Run YuNet on every frame, boxes ×2 → 1080×1920 coordinates.
3. Save to `edit/<id>/faces.json`: `{step, samples: [{t, faces: [[x,y,w,h,score], …]}]}`.

Speed: about 10 s per 30 s of video (≈110 frames). If there are no faces anywhere (voice-over), record exactly that: the graphics are unconstrained.

**Horizontal video in the “framed” format.** A centered 9:16 crop would cut off speakers at the sides (in a test, the two people in frame were found in 7 of 24 samples; in the source geometry, in 24 of 24). Measure horizontal video in its source geometry; in the measurement store the geometry, the source dimensions and the window (~x 25, y 340, 1030×1240). When reading, convert the boxes to screen coordinates of the window (the video fills the window as `cover`), and do not count faces beyond the window edge. The camera is relative to the window center. A finished render is measured as the screen.

## 2. Camera

The virtual camera `{z, cx, cy}` moves the face. Screen coordinates of a box:

```text
x' = (x − cx)·z + 540      y' = (y − cy)·z + 960      w' = w·z      h' = h·z
```

Everything below is computed for the shot size of a specific span of the plan. In a close-up the face is larger and lower.

## 3. Zones per span

For each span of the plan, take the union box of all faces over its duration, with the camera applied, and a margin of **60 px**. From it compute:

| Zone | How it is computed | Used for |
|---|---|---|
| “Headroom” | y from 250 to face top − 60, if ≥ 120 px | hook, cards |
| “Chest” | from chin + 60 to subtitle top − 20, if ≥ 120 px | cards, chips |
| Left | from 40 to face − 60 | cards, memes, icons |
| Right | from face + 60 to 960 (the right 120 px hold the like buttons) | cards, memes, icons |
| Subtitles | chin + 30 ≤ subtitle top | otherwise lower the subtitles to chin + 30, but not below y ≈ 1390 (the bottom 420 px is the UI zone); if they do not fit — a wide shot or a lower camera |
| Top of head | face top < 0 | cut off by the frame edge |

**Real case.** A close-up video intro: in the camera's close-ups the chin reached y ≈ 1320. The subtitles were at 1350, and the audit showed 0 overlaps. With subtitles at 1290 the chin would have run into them for almost the whole video. Hence the template rule: subtitle top = maximum chin (with camera drift) + 30, within 1250–1390.

## 4. Checking graphics

Every card, hook or CTA card over the video is entered in the plan as a `keep_clear` zone: interval, box `x,y,w,h` and what it is. The agent checks it right away against the faces over that interval, with the span's camera and a 60 px margin. If the card touches a face, it is moved to a zone from section 3. Memes do not cover these zones either. **Store the span's camera in the `keep_clear` entry itself** and use it when re-checking the plan: otherwise a card above the head in a zoomed-in shot (camera raised, face moved down) produces a false “touches the face”. Real case: 4 false warnings on list cards disappeared once the check started using the stored camera. A camera raised all the way to the top of the frame is `cy = 960 / z`: up to ~700 px frees up at the top for a list.

## 5. Render audit of the finished video

**When.** Before showing the video to the person.

**How.** The same measurement, but on the **render**: the camera, B-roll and graphics are already applied, so the faces are where the viewer sees them. Samples every 0.25 s are checked:
- **against the subtitle band** — wherever speech is heard and the subtitles are on: scenes that hide them and the plan's `hide-subs` windows (subtitles hidden by a per-video composition, `visual_plan.py hide-subs`) are left out. Pass the actual band: the top and bottom of the subtitle card;
- **against the `keep_clear` zones** — cards, hook, CTA; a presenter layer's own face (`keep-clear --own-face`) is not an overlap with its own zone;
- **against meme boxes**;
- **against the frame edge** — whether the top of the head is cut off.

Zones (`faces.py zones`) split a span at a change of camera angle (the rough cut's source changes): each piece gets the faces of its own angle, never a union of two (a wide shot's small face and a close-up's big one).

**Result.** Overlaps with timecodes, exit code 1 → fix and re-render. The audit does not see graphics that were not entered in `keep_clear`. Those are checked with still frames and the storyboard.

**Verified.** An approved video (subtitles at 1350): 107 frames, 0 overlaps. The same layout with subtitles at 1290: overlaps along almost the whole length. A card deliberately placed on a face was caught.

## 6. Memes

Face boxes for a meme are taken from `faces.json` over the meme's interval, with the span's camera. If there is no measurement, the model is run on three frames of the meme. Then a slot is chosen (`inserts.md` → “Meme size and placement”).

**Verified.** The model's boxes matched manual markup on a wide shot and on a close-up. The chosen slots were the same.
