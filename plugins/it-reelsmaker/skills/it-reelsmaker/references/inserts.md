# Inserts: B-roll, code scenes, memes

Inserts are an optional layer on top of the regular edit. If everything is off, the edit runs as it would without them: main footage, shot-size changes, graphics from the brief. Decisions about inserts are made in the **visual plan** (step 7a) before the Remotion code; the render only executes the plan.

**Designed scenes** (hook, quote, slogan, number, list, CTA, cover; `kind: "scene"`, ids `c01`…) live in the same plan and budget: the `full`, `split`, `panel` and `window` modes count toward coverage together with B-roll, `overlay` counts like a card, through `keep_clear`. Everything about scenes: `references/scenes.md`. The **brand tone** (`brand.json → tone`, `references/brands.md`) sits between the skill defaults and the profile's `inserts` and sets the ceilings: memes, transitions, light flashes, whips, full-frame scenes.

## Settings

Stored in the video's `edit/<id>/reel.json`. Layers apply in order, and each one overrides the previous:
1. skill defaults (below);
2. `brand.json → inserts` of the selected brand;
3. the video's `reel.json`;
4. words from the prompt.

```json
{
 "brand": "<slug>",
 "intensity": "moderate",
 "use_broll": true,
 "use_project_footage": true,
 "use_local_footage": true,
 "use_generated_footage": true,
 "use_scenes": false,
 "use_memes": false,
 "use_local_memes": true,
 "meme_size": "m",
 "broll_priority": ["project", "local", "generated"],
 "meme_priority": ["local"],
 "footage_dirs": ["footage", "broll"],
 "library_dirs": ["⟨YOURS: asset library, see SKILL.md section 11⟩"],
 "memes_dirs": ["memes"]
}
```

The online-sources add-on `it-reelsmaker-online` adds its own keys (`use_online_footage`, `use_online_memes`, `generation_engines`, `generate_now`, providers) and plugs online sources into these priorities. Without the add-on, these keys are ignored.

What each setting does:

| Key | Meaning |
|---|---|
| `use_broll` | B-roll at all |
| `use_project_footage` / `use_local_footage` | B-roll sources: project, library |
| `use_generated_footage` | code scenes in Remotion |
| `use_scenes` | designed scenes (`references/scenes.md`); on when chosen in step 0 or asked for in the prompt |
| `use_memes`, `use_local_memes` | memes, and your own meme library |
| `meme_size` | pop-up meme size: `s` / `m` / `l` |
| `intensity` | `minimal` / `moderate` / `active` |

**Turn everything off** (as without inserts): `use_broll=false`, `use_scenes=false`, `use_memes=false`.

**What actually turns on.** Before the plan, the agent checks what is really available: an enabled source that isn't there (empty folders, no library catalog, the Remotion project doesn't build) turns itself off, and the reason goes into the report. This is not an error: the edit proceeds with what is available.

## Intensity: a ceiling, not a target

| | minimal | moderate (default) | active |
|---|---|---|---|
| B-roll | up to 1 per 30 s | up to 3 per 30 s | up to 6 per 30 s |
| Memes per video | up to 1 | up to 2 | up to 4 |
| Inserts as a share of video length | ≤ 10 % | ≤ 22 % | ≤ 40 % |
| Between inserts | ≥ 6 s | ≥ 3.5 s | ≥ 2 s |

**Coverage** is the union of the intervals of all inserts that go into the video (B-roll in any mode and memes, pop-ups included); overlapping ones are not counted twice. Coverage and spacing that break these limits are **errors** in the plan check, not warnings. Zero inserts is a normal outcome.

## When an insert is needed

An insert goes in only if it answers the question “why” in one of five ways:
1. **Understanding.** It shows the object, action or place being talked about.
2. **Cut.** It hides the seam between takes or a ragged spot. The B-roll starts before the cut and ends after it.
3. **Pace.** It changes the picture in a long segment (> 6 s without a cut) where a shot-size change has already been used.
4. **Hook.** A detail instead of the talking head in the first 1.5 s.
5. **Meme.** It amplifies a joke, irony, an emotion or the recognition of a specific line.

When an insert is not needed:
- **A number, a list, a wording.** A card works better.
- **The face and intonation matter more.** That's the CTA, a personal story, a punchline.
- **Other graphics are already on screen.**
- **The final 2 s.** Memes don't go here.
- **An insert for the sake of an insert.** The `why` field is required on every insert.

## Priority and fallback

**B-roll:** project → library → code scene → otherwise main footage (status `skipped`). With the online-sources add-on `it-reelsmaker-online` installed, online sources join the priority chain.

**Memes:** your own folder and library → no meme (online memes cleared for commercial use come only with the online-sources add-on `it-reelsmaker-online`). Memes are not generated unless that was asked for separately.

**Failures.** Any source error is a warning, not a crash: a missing file, a broken file, a code scene that didn't build. The edit always reaches the render. Inserts that did not become `ready` don't go into the render, and the report says so.

## Visual plan (step 7a)

`edit/<id>/visual_plan.json` is for the agent, `visual_plan.md` is a table for the person: timecode · line · main footage · B-roll · meme · transition · comment.

**Spans.** These are phrases from `captions.json`. A new span starts:
- at a pause > 0.25 s;
- at the end of a sentence;
- at a segment join (if the pause is > 0.12 s);
- when a phrase is longer than 4.5 s.

Spans shorter than 1.2 s merge with their neighbors.

**Hints for a span** are a prompt to think, not a decision:
- segment join → B-roll will hide the cut;
- segment longer than 6 s without a cut;
- number → a card, not B-roll;
- pointing at an object (“here”, “look”, or the same in the speaker's language);
- emotion or irony (“!”, “imagine”, “nightmare”, or the same in the speaker's language);
- hook;
- ending or CTA.

**An insert in the plan:**

```json
{"id": "b01", "kind": "broll", "segment": "s03", "start": 7.58, "dur": 1.8, "mode": "replace",
 "what": "hands flipping through printed resumes", "why": "illustrates the words and hides the s02/s03 cut",
 "query": "hands flipping printed resume", "source": "project|local|generated",
 "candidate": {"provider": "…", "id": "…", "w": 1080, "h": 1920, "size_mb": 4.2, "license": "…"},
 "file": "inserts/b01.mp4", "transition_in": "cut", "transition_out": "cut",
 "status": "planned|ready|pending|skipped", "fallback": "main footage", "credit": {}}
```

It is handy to anchor the insert to a word: “start of the 1st occurrence of the word ‘resume’”. Then it doesn't drift after a re-cut.

**The only source of settings is the video's `reel.json`.** The settings snapshot in the plan is read-only, for the person, and updates itself; the plan check, search and generation read the current `reel.json`.

**Plan check:**
- settings are respected: no meme with `use_memes=false`, no disabled source;
- inserts that are not yet going into the render (`planned`, `pending`) and have no fallback are a warning, not an error: the edit reaches the render on main footage;
- a meme blocked by third-party rights is an error for any brand;
- the B-roll window is inside the safe zone (x 0–960, y 220–1500), not over the face and not over `keep_clear`; faces in screen coordinates, with the span's camera applied;
- the intensity budget is respected;
- durations are within limits;
- every insert has `what` and `why`;
- no two B-roll inserts overlap;
- `ready` files exist and are 1080×1920;
- no imagery forbidden for the brand;
- meme rights are known;
- meme size and placement are within the norm (below).

**Workflow:**
1. The plan is shown to the person in full; if the online-sources add-on `it-reelsmaker-online` added downloads or paid actions, it comes with their list (source, MB, ≈ $).
2. Rendering scenes, any download and any paid action happen **only after the person's approval (“yes”)**.

## Modes and transitions

| Mode | What | When |
|---|---|---|
| `replace` | full-frame B-roll, the voice carries on, subtitles on top | detail, object, place |
| `window` | a window in the insert box (default ~[60, 250, 900, 675]): the first box free of the face and graphics, always within the safe zone; no outline | when the reaction matters |
| `popup` | a pop-up meme at the edge of the frame (size and placement below); a light pictogram gets a `primary` backing at 0.88 | reaction to a line |
| `cutaway` | a full-frame meme, centered on a blurred background made from itself | a “punch”, 0.6–1.2 s, no more than one per video |

Duration:
- B-roll: 0.8–4 s, usually 1.2–2.5 s;
- pop-up meme: 0.8–1.8 s;
- full-frame meme: 0.6–1.2 s.

The default transition is `cut`: a hard cut looks like a camera change. The others:
- `whip`: 5 frames with blur;
- `fade`: 7 frames;
- `flash`: a 3-frame light flash;
- `slide`: 8 frames.

B-roll audio is always muted.

## Footage sources

**Project material.** These are other source files, in the `footage/` and `broll/` folders. The video's own source files and finished renders are excluded.

File names (`IMG_xxxx`) say nothing, so descriptions are written once:
1. **Index.** For each file: size, duration, and 3 frames (15/50/85 %) on a contact sheet.
2. **Descriptions.** The agent looks at the sheets and writes a description and tags for each file in `footage_index.json`.

After that, search runs on the words of the descriptions. An angle from the same shoot that didn't make the edit is ready-made B-roll.

**Library.** Vertical videos from the asset library catalog (SKILL.md, section 11) whose verdict for the brand is not “no”.

**Preparing any source.** The output is 1080×1920, 30 fps, yuv420p, no audio, exactly `dur` seconds:

| Variant | ffmpeg filter |
|---|---|
| `cover` (default) | `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)*fx:(ih-1920)*fy` |
| `contain` | the whole frame over its own blurred copy (`boxblur=30:3`) |
| photo | `zoompan`, slow push-in +6 % |
| slow motion | `setpts=(PTS-STARTPTS)/speed` |
| brand look | LUT at strength 0.7 via `split` + `haldclut` + `blend=all_opacity=0.7` |

Geometry (`cover`/`contain`, focus point) and color correction apply in every branch, photos included. **Short source:** check the length before and after ffmpeg. Up to 0.5 s short, the tail is held as a freeze frame with a warning; more than that is an error (the insert is `skipped` with a reason), not “done” with a short clip.

## Code scenes

Footage of your own that the agent writes itself as a Remotion component: motion graphics, diagrams, cards, interfaces, 3D objects, abstractions, symbolic objects in brand colors. It is free: rendering on a laptop takes ≈ 20 s per 6 s clip. A Remotion project is required. Photorealism (hands, places, atmosphere) is not done in code; that comes from main footage, project material or, with the online-sources add-on `it-reelsmaker-online`, online sources.

**Scene fields** (`gen` on the insert): `subject`, `action`, `composition`, `mood`, `start`, `end` describe what is in frame and how it moves; the optional `seconds` (default 6) and `use_from` set the second of the clip from which the insert is taken, default 0.3.

**A good scene:**
- one action and one camera move;
- a calm start and a calm end;
- the main thing in the middle third: the top 220 px and the bottom 420 px are covered by the UI;
- no text in the frame; text goes on as a layer of the video.

**How it works.** A Remotion component, 1080×1920, 30 fps, 6 s (180 frames). Colors come from the brand profile, motion is calm (easing out, no bounces). Example: “a fan of resume cards, one slides forward, the others fade, focus brackets close in around it”.
1. scenes are registered in a shared registry;
2. render with `npx remotion render <Comp> generated/<id>.mp4 --muted`;
3. a piece the length of the insert is cut out starting at `use_from`, and the status becomes `ready`.

A clip made by hand in any editor goes in as `edit/<id>/generated/<id>.mp4` and is picked up the same way.

## Memes

**Sources.**
- **Your own folder** `<project>/memes/`: images, GIFs, short videos. Next to a file you can put a sidecar `<name>.json` with the fields `description`, `tags`, `emotion`, `use_when`, `rights`, `source`.
- **Asset library.** Suitable reaction memes are tagged in the catalog in a separate `memes.json` file, so that a catalog rebuild doesn't overwrite it. The tags hold a description, an emotion and “when it fits”; rights come from the catalog verdict. Emotion pictograms, statues and “thumbs up/down” work well.
- **Online:** only with the online-sources add-on `it-reelsmaker-online`, CC images cleared for commercial use, with attribution.

**Index:** a shared `memes/_index.json` and contact sheets with a colored rights stripe.

**Search.** By description, emotion and “when it fits”. A match on emotion ranks above a match on a word.

**Rights:**
- `own`: made by you;
- `licensed`: there is a license;
- `cc`: Creative Commons, attribution in the post description;
- `library`: per the catalog verdict;
- `unknown`: not known;
- `blocked`: forbidden by third-party rights (a celebrity, a politician, a film still, stock or real people). This applies to **any** brand and any policy; such memes are hidden and never prepared. A brand's style bans apply only to the brand that sets its own verdicts.

CC meme attribution is carried through to `inserts/credits.json` (one entry per insert). With `memes_policy: strict`, memes with `unknown` rights are not used. Film stills, celebrity photos and other people's memes featuring people are never burned in: the rights belong to the studio and to the person in the photo, and there have been lawsuits.

**How to pick a meme:**
- it is understandable without sound;
- it holds for 1–1.5 s;
- it is not next to other graphics.

One good meme beats three.

### Meme size and placement

A meme is a side remark, not the main shot.

**Size.** Presets by the long side in a 1080×1920 frame:

| Size | Long side | Share of frame width |
|---|---|---|
| `s` | 300 px | ≈ 28 % |
| `m` | 380 px | ≈ 35 % |
| `l` | 460 px | ≈ 43 % |

- **The ceiling is 460 px**, about 10 % of the frame area: a meme never grows to half the screen.
- **A narrow or wide meme** (aspect ratio < 0.6 or > 1.67) gets its long side ×1.3, no higher than the ceiling.
- **Full-frame** is only `cutaway`.

**Slots.** At the frame edge:

| Slot | Position |
|---|---|
| `top-left`, `top-right`, `top-center` | y = 250 |
| `mid-left`, `mid-right` | midway between 250 and the bottom |
| `low-left`, `low-right` | above the subtitles: y = subtitle top − 40 − h |

Margins: left 60, right 140 (likes zone 120 + 20).

**Selection order.** The side opposite the face is tried first, the top before the middle and the bottom. If there is no room at the needed size, the meme shrinks. If there is no room even at `s`, no meme goes on this line.

**What a meme must not cover:**

| Zone | Bounds |
|---|---|
| face | box + 60 px, on frames at the start, middle and end of the meme |
| subtitles | the subtitle band |
| UI | top 220, bottom 420, right 120 px |
| video graphics | cards, hook, CTA, object in hand: the `keep_clear` zones in the plan (interval + box + what it is) |

**Face:** from face measurement (`faces.md`). Without a model: three frames with a 100 px grid in 1080×1920 coordinates; the agent looks at them and sets the head box.

**Preview.** Three frames with the no-go zones and the meme in the chosen box, to review before rendering.

**Tested on real videos.** The check rejected a 760×640 meme over the frame on three counts: above the ceiling, covering the subtitles, covering the face. On a wide shot the meme landed at the top, on the side opposite the face, at ≈4 % of the frame. On a close-up, a narrow 156×390 meme went in the top corner. When the face filled the whole top of the frame, no meme was placed.

## In Remotion

Two insert layers, from the plan data:
- **B-roll and `cutaway`:** right above the video, under the graphics.
- **Pop-up memes:** above the graphics, under the subtitles.

Each insert is a `<Sequence from={start·fps} durationInFrames={dur·fps}>`; video uses `OffthreadVideo muted`, images use `Img`.

It helps to have a universal video template that is assembled from props (`--props=<json>`) without code of its own: the rough cut, inserts, subtitles in brand colors and, optionally, a hook, a corner mark and an end card. Video-specific graphics stay in the video's own component.
