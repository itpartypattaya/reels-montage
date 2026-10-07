![IT Reelsmaker](https://raw.githubusercontent.com/itpartypattaya/reels-montage/main/docs/img/banner.jpg)

# IT Reelsmaker

Turn a raw talking-head recording into a finished vertical video (Reels, Shorts, TikTok) without opening an editor. Claude Code cuts pauses and retakes by the audio, adds a virtual camera, on-brand graphics and word-timed subtitles in Remotion, checks that no text covers a face, masters the sound to −14 LUFS and renders 1080×1920, with the cover in the master and next to it as a picture. Nothing is cut before you approve the cut plan, and no inserts are rendered before you approve the visual plan.

The plugin is a skill built on real client videos: the thresholds and numbers in it come from practice. It works for videos in any language.

## How it works

![The IT Reelsmaker pipeline, from a raw recording to a master](https://raw.githubusercontent.com/itpartypattaya/reels-montage/main/docs/img/pipeline.png)

1. **Brand, style and inserts first.** Pick a saved brand profile (colors, fonts, logos, design rules) or create one from a name, 1–3 colors and a brand tone (one of eight, from premium and warm to drive and bold; you can change it later), which sets which memes are allowed, how many cutaways and how loud the techniques can be. Choose one of six styles and the subtitle mode.
2. **Word-level transcript**, then a search for retakes and slips.
3. **Cut plan → your “yes”.** The plan lists what stays, what goes and why, and offers 2–3 ways to start and end the video: in order, without the slow start, or a teaser (a strong line from later plays first). Nothing is cut before you approve.
4. **Rough cut** with ffmpeg: segment edges found by a speech mask (on a tested video they matched a manual cut within ±40 ms), color (white balance measured to neutral on the graded frames, before your LUT, not judged by eye), speed-up, subtitles on the new timeline. Then faces are measured across the whole cut.
5. **Graphics brief** in one question: logo, call to action, techniques, sound.
6. **Visual plan** for inserts (B-roll from your project or library, code scenes, designed scenes, memes), shown before any render.
7. **Remotion**: virtual camera, graphics on their spoken words, subtitles, render, and an audit of faces against text in the final file.
8. **Mastering** with an acceptance check, then a report in numbers: duration, remaining silence, loudness and peak, cuts and retakes removed.

Each video can have a **profile**: educational, entertaining, expert clip, promo or paid ad. It sets the video's defaults under your brand tone and brings a checklist the draft is checked against before you see it (a paid ad keeps all text inside the ad safe zone). The plan and the report list their **supports**: each decision next to the rule behind it and how far it is trusted (your decision, checked on your videos, or outside advice). Your own craft rules can live in a `playbook.md` in your project; a guide or a video you want to learn from is reconciled with them rule by rule, conflicts shown to you.

![Cutting by the sound: speech mask, edges and pause compression](https://raw.githubusercontent.com/itpartypattaya/reels-montage/main/docs/img/speech-mask.png)

![Face-aware layout: free zones, subtitle band and false-face filter](https://raw.githubusercontent.com/itpartypattaya/reels-montage/main/docs/img/face-layout.png)

## Designed scenes

A hook set large, a quote taken verbatim from the speech, the main thought as a punch, a number with a counter and its source, a list item by item, “before → after”, a message thread, an interface with a cursor, the call to action as an action, a cover in frame 0. Claude draws them in code in your brand's colors and fonts and places each one on its spoken word. By default the speaker's face stays in the frame: the scene sits in a free zone, above the speaker or beside them. The plan check counts reading time (0.8 s for a short line, 0.3 s per word in a phrase), compares quotes with the transcript and asks for a source for every number. A promo without footage uses the same scenes on their own, 15–25 s. The scene planning method is adapted from [brag](https://github.com/latent-spaces/brag) (MIT).

## Requirements

- [Claude Code](https://code.claude.com) on your computer. The skill runs local programs and reads your video files, so claude.ai chat and Cowork without computer access can't run it; in those apps it says so instead of pretending.
- `ffmpeg` and `ffprobe`.
- Node.js 18+ and a [Remotion](https://www.remotion.dev/) project. No project yet: `python scripts/kit.py new reels` creates one with the plugin's Remotion kit wired in, then run `npm install` in that folder. Remotion has its own license terms for companies.
- Python 3.9 or newer, for the plugin's scripts (rough cut, speech mask, visual plan, brands, cover, mastering), plus [Pillow](https://pypi.org/project/pillow/) (`pip install Pillow`) for contact sheets, covers and logos.
- A word-level transcriber. The default is local [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper).

Optional:
- the YuNet face model and OpenCV, for face-aware layout (setup in `skills/it-reelsmaker/references/faces.md`);
- `rembg` with the `u2net_human_seg` model, for text behind the person and a presenter over a scene. It runs on this computer; running it on your own server over SSH is part of the online add-on.

## Install

From this repository's marketplace:

```bash
claude plugin marketplace add https://github.com/itpartypattaya/reels-montage.git
```

```bash
claude plugin install it-reelsmaker@itparty
```

Without plugins, copy the folder `skills/it-reelsmaker/` to `~/.claude/skills/it-reelsmaker/`. The skill then asks for its settings in the first session.

## Configure

Claude Code asks for these settings when you enable the plugin; change them later with `/config`.

| Setting | What it is |
|---|---|
| Editing project folder | Where your videos are edited: `edit/<id>/` per video and `brands/<slug>/` brand profiles |
| Remotion project | The Remotion project used for the camera, graphics, subtitles and render |
| Asset library | Optional folder of your sound effects, music, icons and memes; a starter pack of 260 CC0 sound effects is in the [releases](https://github.com/itpartypattaya/reels-montage/releases/tag/sfx-cc0-1) |
| YuNet face model | Optional path to `face_detection_yunet_2023mar.onnx` |

Brand profiles live in your project, not in the plugin, so updates never touch them. Start one by saying “new brand — Acme, colors #0B1F3A and #FFB800, logo logo.svg”.

## Updates

- **Installed from the Claude directory** (Customize → Plugins): updates arrive by themselves. Claude Code syncs the plugin in the background, shows “Plugins changed. Run /reload-plugins to activate.”, and loads the new version in your next session.
- **Installed from this repository's marketplace:** auto-update is off by default for marketplaces outside Anthropic's own. Turn it on once: `/plugin` → **Marketplaces** → `itparty` → **Enable auto-update**. Or add the marketplace to your `~/.claude/settings.json` with auto-update on:

```json
{
  "extraKnownMarketplaces": {
    "itparty": {
      "source": { "source": "git", "url": "https://github.com/itpartypattaya/reels-montage.git" },
      "autoUpdate": true
    }
  }
}
```

  To update by hand, run these in your shell, then `/reload-plugins` in the session (or start a new one):

```bash
claude plugin marketplace update itparty
```

```bash
claude plugin update it-reelsmaker@itparty
```

What changed in each version is in [CHANGELOG.md](CHANGELOG.md). After an update, the skill shows a short “What's new” note once, on your first edit. The plugin never updates itself and makes no network requests to check for updates.

## Examples

- “Edit a reel from IMG_4821.MOV for Acme: tight pacing, Marker style, subtitles on.”
- “New brand: Northwind Coffee, colors #2E1F17 and #E8B04B, logo in brand/logo.svg.”
- “Change the brand tone for Acme: it feels too strict, make it livelier.”
- “Video 4821 jumps back around 0:18 — find the missed retake and fix the cut.”
- “Add a hook headline, two cards with the key points and an end card with a DM call to action to video 4821.”
- “Run the face audit on the final render and move anything that covers the speaker's face.”
- “Add designed scenes to video 4821: a big hook in the first 1.5 s, the quote about testing how people think, verbatim, and the three signs as a list. Keep the face visible. Show me the plan and texts first.”
- “Make a 20-second promo for Acme without footage: hook, what we do, three numbers from our site with sources, the end card with our site. Then a cover and a post caption.”

## Data and network

The plugin collects nothing and has no server or telemetry. Your videos, transcripts and brand profiles stay in your project folder. Data leaves your computer only in these cases:

- **Claude.** Like any Claude Code session, the conversation goes to Anthropic. That includes transcripts, file excerpts and the frames Claude looks at, under your Claude account terms.
- **A cloud transcriber.** Only if you choose one instead of local `faster-whisper`. Its own terms apply.
- **Dependency and model downloads.** npm packages for Remotion and its own headless browser downloaded on the first render; Python packages such as faster-whisper, OpenCV and rembg (PyPI); Google Fonts loaded by `@remotion/google-fonts` at render time; and the models for the features you use — faster-whisper (Hugging Face), the YuNet face model (GitHub) and the rembg segmentation model (downloaded by rembg on first use).

Face detection only finds face boxes for layout. It does not identify people. Get consent from the people on camera before you publish.

Details: [PRIVACY.md](PRIVACY.md).

## What it does not do

- No AI image, video or audio generation. Code scenes and designed scenes are motion graphics that Claude writes in Remotion.
- No publishing to social networks. You upload the master yourself.
- No face recognition or identification.

More online sources are available through the online-sources add-on `it-reelsmaker-online` in the same marketplace.

## Troubleshooting

- **The skill doesn't start.** Call it directly with `/it-reelsmaker:it-reelsmaker`, or describe the task with words like “edit a reel”.
- **The settings are empty.** Set them in `/config`. Or answer the first-session question, and the skill writes `it-reelsmaker.json` into your project.
- **Remotion fails with “No frame found at position …”.** The rough cut's video doesn't start at 0. Rebuild it with video and audio concatenated separately, as step 6 of the skill describes.
- **The text lands on a face.** Install the YuNet model for measured layout, or ask for the face audit on the render.
- **A cut-out shows furniture next to the person.** Check the check frame the skill renders, then use the “window” layout or reshoot against a wall.
- **The laptop runs out of memory.** Run one Remotion Studio at a time. Videos over 90 s and cut-outs are best on a stronger machine; cut-outs run at 720 px wide for a presenter over a scene.
- **Something else.** The skill keeps a table of known pitfalls with causes and fixes: [`references/pitfalls.md`](skills/it-reelsmaker/references/pitfalls.md).

## Support

Questions, bugs and security reports: [GitHub Issues](https://github.com/itpartypattaya/reels-montage/issues) or mr.a.vaskov@gmail.com.

## License

[MIT](LICENSE).
