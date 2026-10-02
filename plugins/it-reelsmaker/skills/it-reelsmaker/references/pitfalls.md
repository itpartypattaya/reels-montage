# Known pitfalls: symptom → cause → what to do

Read this when something goes wrong in steps 6–9 (rough cut, graphics, render, mastering). Each row comes from a real video edited with this skill; the details are left out on purpose. The step or section in the last column is where SKILL.md describes the fix in full.

| Symptom | Cause | What to do | Where |
|---|---|---|---|
| The render fails with “No frame found at position …” | the rough cut's video does not start at 0: one shared concat of segments with AAC audio shifts the video by ~0.02 s | glue video and audio separately; check that `ffprobe` shows `start_time` = 0 for both and equal durations | step 6 |
| “The video jumps back” | a missed retake: Whisper merged the repeated phrase into one stretched word | look for words longer than ~1 s, re-transcribe a ≤ 5 s segment with a run-up from silence, keep one take | step 3 |
| A word is heard twice after a cut, while the text checks are green | the edge landed in a 30–60 ms dip inside a word; Whisper gave the word's tail to the next word | check every edge by audio, put edges in the longest silence between words | steps 3, 6 |
| The first sound of a phrase is clipped | the edge was moved to match Whisper's timing, which drifts by 0.2–0.6 s | edge = start of the next sound minus 30–50 ms, settled on the waveform ±0.5 s | step 3 |
| After the speed-up the speaker sounds rushed | the author had already sped up the source in a phone editor (above ~9 syllables/s) | measure the speech rate first; already fast → speed 1.0 | step 1 |
| A phone video comes out sideways or squashed | the rotation tag: the size stored in the file differs from the size after decoding | read the rotation in `ffprobe` and work with the decoded size | step 1 |
| Text sits on the chin or the mouth in some shots | the position was set by eye, or the camera zoom moved the head | measure the faces after the camera; run the face audit on the render and fix every overlap | step 9, `faces.md` |
| Subtitles jump up, or a card avoids an empty corner | false “faces” in knees, folded hands or clothing folds | filter detections by confidence and shape; the report says how many were dropped | `faces.md` |
| Furniture or a piece of wall moves with the cut-out figure | the segmentation mask took objects touching the person | look at the check frame on a light and a dark background before the layout; otherwise use the window layout | `figure.md` |
| Letters turn into boxes or a different font | the font doesn't cover the language's script | pick fonts that cover the script; check a still with the real text | `brands.md` |
| Lines run off the frame although the measured width fits | the text was measured before the font loaded, with the fallback font's widths | measure only after the brand fonts are loaded; hold the render until then | `typography.md` |
| Subtitles are unreadable on a white shirt or wall | 15–25 % darkening is not enough on a light background | tune on the lightest still: 42–60 % darkening, or a backing plate | `typography.md` |
| The master was built from an old render | the render was piped into `tail` and chained to the master: `tail` hides a failed render | run the render as its own command, check its exit code and the file time | step 9 |
| The voice quietly drops in the mix | `amix` without `normalize=0` | always `amix … normalize=0`, then bring the mix to −14 LUFS again | section 12 |
| A cut-out or a long render runs out of memory | segmentation of full-size frames is heavy; a larger portrait model needed ~6.6 GB per frame and was killed | run cut-outs on `{{HEAVY_SERVER}}`, at 720 px wide, with the light human-segmentation model; one Remotion Studio at a time | section 15, `figure.md` |

A new pitfall goes in as one row in the same format, with no names, brands, video numbers or servers.
