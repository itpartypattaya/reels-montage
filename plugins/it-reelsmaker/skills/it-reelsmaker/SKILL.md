---
name: it-reelsmaker
description: >
  Edit vertical short videos (Reels, Shorts, TikTok) from talking-head, two-person or horizontal footage, or make a
  brand promo with no footage: local transcription, pauses and retakes cut by audio, virtual camera and on-brand
  motion graphics in Remotion, word-timed subtitles, subtitle translation, .srt files, designed scenes drawn in
  code (hook, quote, number, list, CTA, cover), optional inserts (B-roll, code scenes, memes), cutting out the
  person, face-aware layout, −14 LUFS mastering, 1080×1920 render. Saved brand profiles with colors, fonts, logos
  and tone. Use when asked to edit, cut, assemble or fix a vertical video: “edit a reel”, “video for <brand>”, “make
  a Reel/Short from IMG_xxxx.MOV”, “add subtitles / a hook / a quote / an end card / a cover / B-roll / memes”,
  “translate the subtitles”, “a promo without footage”, “new brand”, “the video jumps back”, fixes to a finished
  video. Not for long horizontal edits, plain format conversion or compression. Needs ffmpeg, Node.js with Remotion
  and Python.
---

# Editing vertical videos — IT Reelsmaker

> **How to use.** A Claude Code plugin: a depersonalized version of a working skill built on real videos, with its techniques, styles and verified numbers kept. You don't need to edit SKILL.md: your own choices go into the plugin settings, the project defaults (`reel-defaults.json`) and the brand folder. The **⟨YOURS: …⟩** marks below are places taken from the brand profile (`brand.json`, `rules.md`) or decided in the brief.
>
> **Brands** live in the project folder: `{{PROJECT_ROOT}}/brands/<slug>/` holds the `brand.json` profile, the `rules.md` design rules, the `assets/` files (logos, LUTs, fonts) and, if the brand has them, its video guide `guide.md`, CTA library `cta.md` and other documents. Template: `${CLAUDE_SKILL_DIR}/assets/brand-template/`. Before editing, the agent asks which brand the video is for. `{{NAME}}` placeholders are fields of the selected brand's profile (table: `references/brands.md`).
>
> Long sections live in `references/` (table at the end). **Scripts** for every repeatable step (rough cut, speech mask, faces, visual plan, inserts, brands, cover, mastering) are in `${CLAUDE_SKILL_DIR}/scripts/`: run them from `{{PROJECT_ROOT}}`, don't rewrite them for a video; what differs between videos goes into the video's JSON files. Which script for which step: `references/scripts.md`.
>
> **Language.** Talk to the person in their language and translate any fixed labels from this file (style and tone names, question options, plan and report headings). On-screen text (hook, cards, scenes, CTA, subtitles) is in the language of the video, not of these instructions.

---

## 0. Environment, settings, brands

**Environment comes first in the session.** The skill works where the agent runs commands and sees files on your computer, that is, in Claude Code. Run `python "${CLAUDE_SKILL_DIR}/scripts/doctor.py"` from the project folder (or `python3`, `py -3`): it checks ffmpeg, Python, Pillow, Node.js, the Remotion project, the transcriber, the face model and rembg, and prints the install command for this OS for anything missing; exit code 1 means a required program is missing. No Remotion project yet → `kit.py new <folder>` creates one with the kit wired in (then `npm install` in that folder); an existing project → `kit.py check --remotion {{REMOTION_DIR}}`, and `kit.py update` if the kit is missing or older. No tool for commands and files (claude.ai chat, Cowork without computer access) → say it plainly: “Editing runs in Claude Code on your computer: it needs ffmpeg, Node.js with Remotion and Python 3”, and do not pretend to edit. One program missing → name what to install and what won't work without it (without Remotion: graphics and rendering; without Python 3.9+: every script, from the rough cut to mastering). Pillow (`pip install Pillow`) is needed for contact sheets, covers and logos; OpenCV only for face measurement.

**Project settings** come from the plugin settings (Claude Code asks for them when the plugin is enabled; change them with `/config`):

```text
PROJECT_ROOT  = ${user_config.project_root}
REMOTION_DIR  = ${user_config.remotion_dir}
ASSETS_DIR    = ${user_config.assets_dir}      empty = no library of your own (section 11)
FACE_MODEL    = ${user_config.face_model}      empty = faces checked frame by frame (references/faces.md)
```

A value that is empty or still reads `${user_config.…}` (the skill was not installed as a plugin, or the setting is not set) → take it from `it-reelsmaker.json` in the project folder (the current folder or its parent); if that is missing too, ask once (project folder, Remotion project) and write it there. The other way round, a plugin setting that is set (expanded, not empty) while `it-reelsmaker.json` lacks it or holds another value → write it into `it-reelsmaker.json` under the same key (`project_root`, `remotion_dir`, `assets_dir`, `face_model`), keeping the other keys: the scripts read only that file, never the plugin settings. Further in the text: `{{PROJECT_ROOT}}`, `{{REMOTION_DIR}}`, `{{ASSETS_DIR}}`, `{{FACE_MODEL}}`.

**What's new after an update.** Once the project folder is known and before the editing questions, read `version` from `${CLAUDE_SKILL_DIR}/../../.claude-plugin/plugin.json` and `last_seen_version` from `{{PROJECT_ROOT}}/it-reelsmaker.json` (create the file if needed and keep its other keys). Compare versions as numbers, part by part (1.10.0 is newer than 1.9.0). The installed version is newer → show one short block “What's new in X.Y”: at most 4 points from the `${CLAUDE_SKILL_DIR}/../../CHANGELOG.md` entries newer than the last seen version and not newer than the installed one, in the person's language and without technical detail; then write the installed version there. No `last_seen_version`: if the project already has `edit/` or `brands/`, it was used with 1.0.0, which kept no record, so take 1.0.0 as the last seen; an empty project → write the version silently. Something can't be read (no `plugin.json` at that path, as in a manual copy of the skill, no version, no CHANGELOG entry) → skip this step and write nothing. Never update the plugin yourself: how to update is in the README.

**Brands**: `{{PROJECT_ROOT}}/brands/<slug>/` (`brand.json` + `rules.md` + `assets/`), as many as you like, managed with `brand.py` (`list`, `new`, `show`, `tone`, `rule`, `use`, `export`):
- **minimum**: a name, 1–3 colors and the **brand tone**, one of eight presets from `premium` to `bold` (`references/brands.md`, with how to offer eight in a 4-option question). The tone sets the limits for the brand's videos right away: which memes are allowed, how many cutaways, how loud the techniques can be (light flash, whip, shake, full-frame scenes) and the scene tones; louder only on explicit request for a video (`tone_override`). “Change the brand tone” rewrites it in the profile at any time. The agent works out color roles, text contrast, fonts that cover your language's script and the logo search itself;
- **older files**: a `brand.json` or `it-reelsmaker.json` with an older `schema` is brought up to date once, with a `.bak` copy and one line saying what changed (`references/migrations.md`);
- **brand documents**: `rules.md` (rules in words, bans, voice), `guide.md` (the brand's video guide: palette roles, typography, signature elements, motion, imagery bans; `brand.json → guide`), `cta.md` (the brand's CTA library with exact texts; `brand.json → cta_library`), other `.md` documents linked from `rules.md`; `brand.py show <slug>` lists what it finds;
- **revisions** (yours or the client's) and anything the person says about the brand as a whole go into the brand folder, not into one video's notes: a rule or ban → `rules.md` with a date (`brand.py rule`), a CTA → `cta.md`, a visual decision → `guide.md` (`references/brands.md`); the brand's next video already knows them;
- profiles live in your project, not in the plugin, so a plugin update does not touch them. **Moving from an old version:** if `~/.claude/skills/reels-montage/brands/<slug>/` exists (versions before 1.0 were installed by cloning), offer to move those folders to `{{PROJECT_ROOT}}/brands/`.

**Craft rules and how far to trust them** (`references/playbook.md`): measurement (scripts, thresholds) is kept apart from taste (hook, pace, shots, text). The person's own rules live in the brand's `rules.md` (owner decisions, dated) and in the optional project playbook `{{PROJECT_ROOT}}/playbook.md` (cards with an ID, scope, reason, source and trust: owner ⭐ · verified on edited videos 🟢 · external advice ⚪); read both before the plan. Rules disagree → scope first, then owner → verified → external, else ask. A guide or someone's video to learn from goes into `{{PROJECT_ROOT}}/refs/` and is reconciled rule by rule, conflicts shown to the person; a correction that repeats, or comes with “always”, becomes a rule.

**Video settings** (`reelcfg.py show` / `save`): `edit/<id>/reel.json` holds the brand, style, inserts (`use_broll`, `use_generated_footage` = code scenes, `use_scenes` = designed scenes, `use_memes`, `use_local_memes`, …), intensity (`minimal` / `moderate` by default / `active`) and meme size. Everything about inserts: `references/inserts.md`. Online sources belong to the online-sources add-on `it-reelsmaker-online`: without it the related settings are ignored. The skill does not offer the add-on on its own: it is named only in `doctor.py`'s status row and as an option for a cut-out too heavy for this computer (section 15, `matte.py`, `references/figure.md`), and otherwise only when the person asks about online sources.

**Your own settings live in your project, never in the plugin folder** (an update replaces it). Project defaults: `{{PROJECT_ROOT}}/reel-defaults.json`, the format of the plugin's `assets/reel-defaults.json` with only the keys you change (default brand `settings.brand`, inserts on/off, intensity, `library_dirs`, your labels for intensity and brand tones…), edited with `reelcfg.py defaults [--set key=value …] [--unset key …]`; layers: plugin ← add-on ← brand tone defaults ← project ← `REELS_DEFAULTS_OVERLAY` ← brand `inserts` ← `reel.json` ← prompt; the brand tone's ceilings still apply (`references/brands.md`, “Your settings in the project”). Project-wide notes (folder layout, which Python to run, servers, lessons from past videos, the person's ready prompts) go into the project's `CLAUDE.md`, which Claude Code reads by itself.

---

## 1. The main rule: the template is a menu, not a checklist

Everything described below (logo, end card, hook headline, cards, focus brackets, role tags, verdict scale, “save” bookmark, music, B-roll, code scenes, designed scenes, memes, special techniques) is a **set of possible techniques**, not a required package. A video has only a clean edit with shot-size changes, plus subtitles, unless something else was chosen in step 0 (inserts) or the brief (step 7), or stated directly in the prompt. The settings files are not that choice: the brand tone turns B-roll (and for some tones memes) on by default, so step 0 saves whatever was not chosen as `false`. Carrying everything over makes a video noisy and templated.

**Only the quality rules always apply:**
- no text on a face; nothing important in the UI zones (grid below);
- graphics and highlights start on their word (±2 frames); timing comes from the transcript, not by eye;
- one typography style and one accent color per video;
- no leftover takes or slips in the final video;
- brand voice `{{VOICE}}`, with no `{{FORBIDDEN_WORDS}}` and no `{{FORBIDDEN_IMAGES}}`, in graphics, B-roll, code scenes and memes alike;
- an insert (B-roll, meme, designed scene) only with an answer to “why”, within the intensity budget and within the brand tone; film stills, celebrities and memes without rights are never burned in;
- facts in graphics only from a source: a quote verbatim from the speech, a number from the speaker, the brief or the client;
- any download and any paid action only after the person's approval (“yes”) of a visual plan with source, size and price;
- publishing only after a “yes” from `{{APPROVER}}`.

## 2. Frame grid 1080×1920

| Zone | What |
|---|---|
| y 0–220 | social app UI, nothing important |
| y 1500–1920 | caption, buttons, username, nothing important |
| x 960–1080 | likes and comments; text stays out |
| face (measured) | no-go zone for any text, 60 px margin |
| y ≈1250–1390 | subtitles: top = measured chin + 30 px; at the edge away from the speaker or bottom left; centered only if it doesn't fit otherwise |

Where the head is comes **from the face-detection model's measurement**, not by eye (`references/faces.md`; false “faces” on knees and hands are not a frame error and are dropped by the filter): faces across the whole rough cut every 0.25 s → for each span, the room in the “headroom” zone (from y 250 to face top − 60) for the hook and cards, in the “chest” zone (from chin + 60 down to the subtitles) and at the sides, plus the subtitle height. The chin stays above the subtitles in every camera shot: zoom is calculated by formula (screen = (x − cx)·z + 540). No model → check frame by frame.

## 3. Styles — one per video

Choosing the style is **the first question, before any editing** (step 0): the subtitle position, the room in the “headroom” zone and the camera shots depend on it. A previous choice is not inherited. Colors from different styles are not mixed.

| Style | Look | Good for |
|---|---|---|
| **“Marker”** | `{{FONT_TEXT}}`, dark `{{INK}}` text on a `{{MARKER}}` marker bar, light thesis cards, no outlines or shadows | monologues, intro videos, skits. A good default |
| **“Brand”** | `{{DARK}}` + `{{ACCENT}}`, `{{FONT_HEADING}}` + `{{FONT_TEXT}}`, focus brackets ⌜⌝⌞⌟ (the kit draws them inside `stat`, `word` and `cta` scenes; on a word over the video, a per-video component), accent marker bar | job openings, case studies, anything where recognizability matters |
| **“Minimal”** | bold white capitals bottom left in 2–3 lines, one accent word in color ⟨YOURS: example olive #B3BC6E⟩ | business insight, “confident and clean” |
| **“Editorial”** | serif `{{FONT_SERIF}}` + sans-serif, beige accent ⟨YOURS: example #E6C999⟩; the kit sets its headings in `fonts.serif` (or `looks.editorial.heading`), the cards and scenes themselves in a per-video composition | testimonials, stories, magazine tone |
| **“Bold”** | white black-weight capitals, key word in black on a lime marker bar ⟨YOURS: example #D4E79E⟩, the bar fills from left to right over 6–8 frames | provocative hook, controversial claim |
| **“Glass”** | glass cards `{{DARK}}` 35–45%, blur 12–16 px, glowing dividers | skits only; breaks the “no glow” rule, so only by explicit choice |

**Fonts: check that the font covers your language's script (for example Cyrillic or Vietnamese diacritics) in the font file itself.** Verified Cyrillic check: Satoshi and General Sans have no Cyrillic; Manrope, Inter, Inter Tight, Onest, Playfair Display and Cormorant Garamond do. The paid Canela and Neue Montreal have not been checked. Load fonts via `@remotion/google-fonts` with subsets for the scripts you need, for example `subsets: ["latin"]` or `subsets: ["cyrillic","latin"]`.

### Typography principle: “the person is the main subject, text is support”

- 3–6 words on screen at most; large; lots of breathing room; readable within the first second; no more than 2–3 short lines at once;
- **no outlines, glow or shadows** (a dated 2021–2022 look). Unreadable on a light background → a soft gradient darkening of the lower third, not an outline; its strength is measured, not guessed: `visual_plan.py shade edit/<id>` gives the value for 4.5:1 on the lightest frame (`reel.json → subtitles_shade`, kit default 0.35). The kit draws this darkening only under “Typewriter” subtitles; in “Accent” mode on a light background use “Bar” (plate) subtitles or a backing; for text in another zone (a style's white text in the headroom) `shade … --scene <id>` or `--zone x,y,w,h`;
- text at the side or bottom, aligned to an edge, not centered; text never covers hands holding an object, a screen or the product;
- an important word gets the accent color **or** a ×1.3–1.6 size, not both;
- hook: no more than 6 words, one accent word;
- **a phrase is one block**: parts of one thought (lead-in and big word, heading and caption) sit tight together, 15–25 px between visible edges, on a shared axis, in one zone of the frame, moving together; short function words (prepositions, articles, negations) and numbers do not dangle at the end of a line. Details: `references/typography.md`.

### Subtitle modes

By default, subtitles cover all speech: videos are often watched without sound. “Selective” (the key phrase only) on request.

- **“Bar”**: a 3–6 word phrase (≤ ~26 characters per line) on a `{{MARKER}}` marker bar; words are added as they are spoken.
- **“Accent”**: 2–3 words, `{{FONT_TEXT}}` 800, 64–72 px, the word being spoken in the style's accent color. Loud, for quick insights.
- **“Typewriter”**: the whole phrase in 1–2 lines, 52–58 px; upcoming words at 30% opacity, spoken words appear as they are said, a caret (a thin bar in the accent color); color per speaker. Quieter and more premium, for skits and calm videos. Split by phrases and pauses (up to ~52 characters as a whole), not by a character limit.

Hide subtitles when on-screen text replaces them: a hook with a headline, a list card, a full-screen phrase, the end card. A card at the bottom of the frame: raise the subtitles above it or hide them for its duration.

**Subtitles in another language** (on request or chosen in the brief): `subs.py phrases edit/<id> --lang <code>` lists the speech by phrases; you translate each phrase in `subs/<code>.json` yourself (one phrase of translation per phrase of speech; the brand's voice and forbidden words apply; names, numbers and terms as said; as short as the speech), then `subs.py apply` checks it (reading speed: about 17 characters per second, never harder to read than the original subtitle) and writes `captions-<code>.json`, and `reel.json → "subtitles_lang"` puts it into the render. The font must cover that language's script; in a script written without spaces (Chinese, Japanese, Thai…) mark the word boundaries with `|`. Scenes still land on the spoken words. **Scene texts in a translated version:** write the hook, quote, slogan and CTA texts in the subtitle language too (a quote from the speech is then checked word for word against the translated subtitles), or keep them in the speech language and say why in the plan; a translated phrase that a scene covers for most of its time is hidden whole, not shown as a tail. `subs.py srt [--lang <code>]` gives a `.srt` file for platforms that take one (2 lines of 42 characters at most; a longer phrase becomes several subtitles). A re-cut keeps the translations of unchanged phrases; the export refuses a translation of an older cut.

On top of subtitles, if the brief asks for them: “accent titles”, 2–4 key words per video shown larger, on a separate layer, on their word; the kit cannot take one word out of a subtitle line, so hide the subtitles for the title's moment (`hide_subtitles` on its card or scene), or the word appears twice. At most one word per video in color (usually the CTA).

## 4. Brand in motion

**Brand elements that animate well** ⟨YOURS: replace with your own⟩:
- **focus brackets** ⌜⌝⌞⌟ close in on a key word or number over 0.4–0.5 s, like a viewfinder (the kit has them inside `stat`, `word` and `cta` scenes; brackets on a spoken word over the video are a per-video component, `references/brands.md`, “In Remotion”);
- **marker bar**: a 6–8 px vertical bar to the left of the card that grows with the text;
- **a grid of cards** from which one stands out (for “from 200 → 5”);
- **all-caps labels with 0.2 em letter spacing** above the card heading: `CASE STUDY`, `INSIGHT`, ⟨YOURS⟩.

**Motion** (one reading of “calm, precise, premium”; ⟨YOURS: change it if the brand is energetic⟩):
- entrance: smooth deceleration (`Easing.out(Easing.cubic)` or `spring` with `damping ≥ 200`), 12–16 frames;
- exit is faster: 8–10 frames, opacity plus a 20–40 px shift;
- no bounces, shakes, spins, glitch, neon or gradients;
- no more than one animated element on screen at a time, not counting subtitles.

**Where video departs from the static brand guidelines:** hook 92–120 px, cards 54–64 px, subtitles 54–72 px (otherwise unreadable on a phone); a shot change every 1.5–4 s is normal even for a “calm” brand; a live speaker on screen, not stock footage.

## 5. Video formats ⟨YOURS: keep the ones you need, add your own⟩

| Format | Essence | Typical graphics (optional) | Length |
|---|---|---|---|
| Insight | one expert thought | hook, 2–3 thesis cards, ending | 30–60 s |
| Case study | problem → how it was solved → result | big number in brackets, a “funnel” of cards | 30–45 s |
| Job opening / offer | an open position or a product | card: role, city, terms, 2–3 points, CTA | 15–30 s |
| Testimonial | a client quote | quotation marks, name and role in caps | 15–25 s |
| Intro video | who I am → what I do → how I'm different → CTA | “NAME · ROLE” label, question hook, chips on their words | 25–35 s |
| Skit / “Verdict” | two-person dialogue, expert conclusion | role tags, “Reject / Consider / Offer” scale ⟨YOURS: your own scale⟩ | 45–70 s |
| Interview / Zoom | a segment of a horizontal recording | “framed” format (section 10) | 30–60 s |

**End card** (if chosen): `{{DARK}}` or light background, logo, `{{TAGLINE}}`, CTA. 2.4–3 s. A separate option is a **logo sting without a CTA** (2–3 s), when the call to action is spoken.

**Hooks in the brand voice** ⟨YOURS: your own examples⟩. Specifics instead of promises: “12 days from brief to result. Here's what sped it up”, “Why a résumé tells you almost nothing about sales”. Not suitable: loud promises, “Stop losing money”. For skits the hook is the mechanics, with no headline: the video opens with the most controversial line.

## 6. Pipeline

Three tools in sequence: **transcription and cut plan** (locally faster-whisper, or your own transcription tool) → **the cut script `cut.py`** (segments, color, speed-up, subtitles on the finished video's timeline) → **Remotion** (camera, graphics, subtitles, render) → **audio mastering**.

File layout per video: `{{PROJECT_ROOT}}/edit/<id>/` with `cut.json`, `reel.json`, `project.md` (session · strategy · brief · decisions · open items), `transcripts/`, `final.mp4`, `captions.json`; in Remotion, `public/<id>/video.mp4`, plus `src/Reel<id>.tsx` only when the video needs its own composition (the kit's `ReelKit` with props covers the rest). `<id>` is the source file number; a promo without footage gets a short name (`promo-<brand>`) and skips steps 1–6 (`references/scenes.md`, the “scenes only” format). Start a new video from a copy of the last successful one, not from scratch.

### Step 0. Brand, style, subtitles, inserts — the first `AskUserQuestion`
- **Brand.** If it is clear from the prompt, the folder or the project defaults (`settings.brand`), take its profile; otherwise offer the 3 most recent saved brands, and a new one via “Other” (name and colors). Read the brand's `rules.md` and its video guide `guide.md` (if set) before any graphics.
- **Style.** Show the style table, 3–4 options (the tool's limit), with the recommendation for this video first and a one-line explanation.
- **Subtitle mode.**
- **Inserts** (`multiSelect`, if the prompt says nothing): B-roll from project materials and the library · code scenes in Remotion (diagram, interface, symbolic object; free) · designed scenes (hook, quote, number, list, CTA; `references/scenes.md`) · memes from your own folder and the library (if the brand tone allows them; `friendly` and `bold` recommend this option, but it is still the person's choice). With the online-sources add-on `it-reelsmaker-online` installed, online sources are added as well (with a price where they cost money). Whatever is not chosen is saved as `false` explicitly, because the brand tone switches B-roll, and for `friendly` and `bold` memes, on by default: nothing chosen → `reelcfg.py save edit/<id> --set use_broll=false use_scenes=false use_memes=false`, then check with `reelcfg.py show`. Code scenes without B-roll footage: `use_broll=true`, `use_project_footage=false`, `use_local_footage=false`, `use_generated_footage=true` (code scenes are B-roll inserts; `references/inserts.md`). Intensity and scene tone follow the brand tone unless stated otherwise.

Limit: 4 questions; if the brand is clear, don't ask about it. Horizontal source → offer the “framed” format right away. Answers go into `edit/<id>/reel.json` and `project.md`.

### Step 1. Analyze the source
`ffprobe`: resolution, fps, duration, **rotation tag** (for a phone MOV, the size stored in the file differs from the size after decoding). Larger than ~300 MB or 4K → make a working copy, but keep the zoom margin in mind (step 4). Before the plan:
- **whether the source was already sped up** by its author in an editor: a rate above ~9 syllables/s (measured on Russian speech) means it is already sped up; set your own speed-up to ×1.0. It needs the words, so estimate it right after step 2: syllables per second = the vowels of the transcript's words ÷ the speech time (pauses don't count); `transcribe.py rate edit/<id>` measures it exactly on the rough cut after `cut.py`, per source and per segment (numbers written in digits are left out of both the vowels and the time, and it says how many);
- **editor intro, watermark, black frames** at the start and end: leave them out;
- **below 720p**: zoom no deeper than ~×1.06, get dynamics from cutaways and graphics, and say so right away;
- **was this source edited before**: `structure.py history <source>` finds other `edit/` folders with the same file; read their notes (what was chosen, what the person changed) before offering anything.

### Step 2. Word-level transcript
With timings for every word; for two speakers, with speaker labels (on a single microphone they get mixed up, so identify speakers by their lips and write them into `cut.json`: `"speaker"` per range, `"speakers"` for a switch inside one; the kit then colors the subtitles per speaker in every mode, `references/skit.md`). Cache the transcript and do not rerun it. By default, locally with faster-whisper medium int8 (~2.5 min per 96 s of audio): `transcribe.py edit/<id> <source>` (cached in `edit/<id>/transcripts/`; your own tool gets the WAV from `transcribe.py audio edit/<id> <source>`, never the video file, and its output is checked with `transcribe.py check`); a cloud recognizer only if the person chose and connected it themselves (the video's audio then goes to that service; with the online add-on, `addon.py transcribe` lays a cloud text onto these local word times, the add-on's skill has the rules). All recognizers drift at word boundaries by 0.1–0.8 s, which is why cut edges are set by audio (step 6). Audio: `edit/<id>/audio16k-<source stem>.wav`, on the video's timeline (a phone MOV's sound track can start ~0.1 s after the picture; audio extracted without that lands every cut early and clips word endings); legacy `audio16k.wav` is still a valid speech-mask input.

### Step 3. Takes and slips — before the plan
Speakers often record their lines in several takes, and Whisper **merges a repeat into one stretched word**. A missed take in the video looks like “the video jumps back”. Signs:
1. **a stretched word** > ~1 s (a normal one is 0.2–0.7 s), especially with ≥ 0.3 s of silence inside; false alarms: a long first word often includes the silence before it, and a ~1 s word can include a pause before the word;
2. **a repeat in meaning** of a phrase or its beginning;
3. **restart words**: “so”, “I mean”, “that is”, “no”, “stop”, “let me start over”, or the same in the speaker's language; a cut-off word;
4. **a pause > 1 s mid-thought**: often the seam between two attempts.

For a suspicious spot, cut out a segment **no longer than 5 s, with a run-up from silence**, and re-transcribe it separately (`transcribe.py snip edit/<id> <source> --from … --to …`: no context of the whole video, the transcript's language, a short sample of speech with fillers in that language as the prompt; a prompt in another language leaks into the text). On a 10-second segment the repeat still collapses. When the snip hears the spot right, put its words into the main transcript with `transcribe.py splice edit/<id> edit/<id>/snip/<name>.json` (they replace the words inside the snip's window; a backup `<stem>.presplice.json` is kept), then rebuild the cut. Transcribing the finished video as a whole structurally cannot see repeats.

**Which take to use:**
- the speaker cancelled themselves out loud → discard the take;
- the speaker **approved** themselves (“that one's good”) → use the **previous** take;
- a whole phrase beats a broken one, even if the broken one is worded more precisely;
- by default, the last take;
- all broken → the most complete one; cover the joins with a shot-size change or a slide scene;
- a slip corrected mid-phrase (“much more interesting, much more important”) → keep the corrected wording and cut the wrong one;
- of two takes, the first goes out whole, together with its restart word (“so,”);
- a long skit with whole trial runs and chatter between takes → take the last clean take whole and splice in good pieces from other takes only where needed;
- clothing rustle can stay above the threshold for almost a second and look like speech; it is caught by an empty spot in the transcript and by the frames.

The cut edge is the start of the next take's sound minus 30–50 ms; check on the waveform that the first sound is not clipped. Unclear which take is better → put both in the plan and let the person decide.
In the cut plan, list the takes and slips found, with source timecodes; if none were found, say so and list the signs that were checked.

**Cutting a phrase out of continuous speech** is possible only if there is ≥ 0.1 s of silence at both of its edges; no pause (a 50 ms dip) → cut it together with the neighboring phrase and say so in the plan. A **noisy background** (street, balcony, air conditioner, noise floor around −38 dBFS) is taken for speech by the speech detector, and edge-check warnings can be false; cross-check against the transcript (nothing there where the “speech” is) and by ear.

**Where to place the edge:**
- in the **longest silence** between words, not at the first dip: a 30–60 ms dip in connected speech is inside a word, not a pause;
- if the edge is followed by a short sound < 0.35 s, then silence ≥ 0.2 s, and only then speech, the short sound is the **tail of the previous word**; place the edge after the silence;
- do **not move** an edge from the speech detector **to match Whisper timing**: Whisper drifts by 0.2–0.6 s; settle a disputed edge by looking at the waveform ±0.5 s;
- **do not cut between takes inside one phrase** if neither take has ≥ 0.1 s of silence at the join; take the whole phrase from one take.

**Whisper cannot see a word fragment at an edge in any mode**: not on the whole file, not on a short segment, not with a prompt “with word fragments”. It does not drop the fragment; it attributes it to the word it expects, so the tail of a word at the start of a segment is recognized as the next word. Real case (Russian speech): the edge landed in a 40 ms dip inside *poteryali* (“lost”), the 0.23 s tail *‑(te)ryali* got into the segment and was recognized as the following *Na* (“On”), and in the video *teryali* was heard twice, while the text-based checks were green. Only the audio-based edge check (step 6) catches this.

### Step 3a. Structure: how it starts and ends — offered, not decided
The order of the lines is a choice of its own: the same speech works very differently with the strongest line first. Name the video's format in one line (section 5), run `structure.py suggest edit/<id>` (`--from/--to` in source seconds when the video takes one fragment of a long recording; phrases with their signs, which can be cut out cleanly by audio, teaser candidates with exact `ranges`, a slow start, the payoff and ending, earlier edits of the source), read the transcript yourself (the script sees signs, not meaning), with two cameras run it per source (`--source KEY`, a key of `cut.json → sources`; before the cut list exists, `--transcript edit/<id>/transcripts/<stem>.json`) or on the main angle (it lists the sources rather than guess), and offer **2–3 structure variants** in one `AskUserQuestion`: each is start → middle → end with its length, why, and risk, with the order of lines and timecodes in the option's `preview`; the recommendation first. Start: in order · cut the slow start · **teaser** (a strong line from later plays first, then the video from its start) · proof first · question loop · detail first. Ending: payoff with a hold · CTA · logo sting · pull-out · callback to the hook · loop. **A skit or a dialogue always gets a teaser variant**; a teaser of the ending's payoff gives the punchline away, so say so. The menu with when and when not: `references/structure.md`.

### Step 4. Zoom margin and camera plan
A shot-size change is the main source of dynamics and the best way to hide a cut. Calculate **before** the plan:
- **by quality**: below 720p → ~×1.06; 720p → up to ×1.28 (with lanczos upscaling + light sharpening); 1080p → ~×1.3; vertical 4K → up to ~×2.0 only with a rough cut at the source size (not verified; `references/camera.md`); horizontal 4K with a vertical crop → ~×1.12 (the vertical crop keeps 1215 px of width); the “framed” window first enlarges the source by window height ÷ source rows (×1.15 for 1080 rows, ×1.72 for 720), and the push-in counts on top of that base: 1080p leaves ≈ ×1.13, 720p and below ≤ ×1.06 (`references/techniques.md`);
- **by framing**: in a close-up the top of the head is not cut off, the eyes are near the upper third, the chin is above the subtitles; with two people, two-shots only; a medium shot shifted toward one person is fine, a close-up on one cuts the other's face (`references/skit.md`).

A limit below ~×1.15 → the camera will not give any dynamics; say so before editing.

### Step 5. Cut plan → “yes”
In one message: **start and ending** (the variant chosen in step 3a, with the teaser's source timecodes if any), phrase order (what stays, what goes, **what was rejected and why**), takes and slips, **pacing** (“tight”: pauses up to 50 ms, `speech_mask.py --density max`, the default; “natural”: up to 220 ms, `--density natural`) and **filler words** (keep / remove; by default keep: speech sounds livelier), each with a recommendation, speed-up via atempo with pitch preserved (insight monologue ×1.15–1.25, skit and calm delivery ×1.1–1.15; above ×1.3 sounds rushed), final length, zoom margin, transcription fixes, and **Supports**: the decisions that shape the video, each with the rule behind it (file › section or card ID, and its trust), what was not applied or departed from and why (`references/playbook.md`). **No cutting without a “yes”.** The message looks like the cut plan in `references/examples.md`.

**Multiple cameras:** measure the speech rate for each source (syllables per second, step 1) and even them out with a separate speed for each; the rates that count are measured on the cut speech (`transcribe.py rate edit/<id>` after `cut.py`), adjust and rebuild. Real case: the sources measured 9.56 vs 7.55 syllables/s (27% apart) → ×0.915 and ×1.095, and the cut speech came out at 8.56 and 8.54; the source figures are only the first estimate. A take spoken faster than the rest shows up as one segment above the others: give it its own source key (the same file) with its own speed. No more than two **phrases** from the same angle in a row (count phrases, not the pieces a compressed pause splits a phrase into), and two in a row must differ in shot size; a phrase comes whole from one take; show the chain of angles in the plan.

### Step 6. Rough cut — `cut.py` + `cut.json`
The video's cut list goes into `edit/<id>/cut.json`: sources (several cameras, each with its own speed), `ranges` (source segments with a beat), `speed`, `look` (brand LUT and its strength, a color filter chain), `fix` / `fix_at` (transcription fixes), `retime` (exact timings of key words), `extract` (cutaways from the same footage); format: `references/scripts.md`. `cut.py edit/<id> --dry-run` shows segments, lengths and words; `cut.py edit/<id>` builds `final.mp4`, `captions.json` (segments `src_start/src_end/out_start/out_dur` + words with `start/end` on the new timeline) and `edl.json`. The script encodes each segment separately with 30 ms audio fades at every cut and joins **video and audio separately** (a combined concat with AAC audio shifts the video start by ~21 ms, and Remotion then fails with “No frame found at position …”); it exits with code 1 unless video and audio both start at 0 and have the same duration.

**Segment edges come from the audio, not the transcript** (`speech_mask.py`; it prints the `ranges` for `cut.json`; the algorithm, verified: matches a manual cut to within ±40 ms):
```text
env    = RMS over 10 ms windows, dBFS
sdb    = rolling max of env over ±30 ms     # a dip inside a word does not become a pause
speech = sdb ≥ threshold AND the span lasts ≥ 110 ms   # a breath (−36…−42 dBFS) does not pass
threshold = −30 dBFS; for quiet recordings: min(−30, speech level p95 − 20 dB)
voiceless-ending pickup: a short burst within 250 ms after a span is part of the word
        (but the start of the next full span is a stop)
plosive-onset pickup: a short burst within 200 ms before a span is the start of its word (a 40 ms “p”, then the closure)
segment edge = first speech − 20 ms … last speech + 30 ms, snapped to the frame grid
pause compression: ≥160 ms → keep 50 ms (tight = --density max, the default; natural = --density natural: ≥400 → 220). Threshold no lower than 150 ms:
        a shorter unstressed syllable is indistinguishable from a pause
        (Russian example: “poka vy spite”, “while you sleep”, became “ka vy spite”)
warn: pause >1 s inside a segment (seam between takes); short speech at the start, then a pause (tail of another take)
```
The algorithm does not see meaningful silence (a smile at the end, a pause before a punchline); add it by hand. State the remaining silence as a number (≤ ~150 ms with “tight”).

**Color (`look` in `cut.json`) in two steps:** correction for the specific source (white balance, green cast, exposure; `look.correct`, applied before the LUT), then the “look”: your own LUT at 50–100% strength. **White balance to neutral is measured in every video, not judged by eye:** once `ranges` and `look` are set, `balance.py edit/<id> --write` (then `cut.py`) runs the frames through the same look and puts into `look.correct` the gains that make the grays of the *graded* result neutral; check `verify/balance.png` (grays and skin). Measure the graded result, not the raw source: a brand LUT shifts the balance too (real case: it pulled blue down and the whole video read yellow; a correction before the LUT fixed it, the same LUT stayed). Always check `verify/balance.png` by eye; a frame dominated by colored light (sky or sea through windows, neon, mixed light), a refusal or no suggestion → `balance.py edit/<id> --ref SECOND,X,Y,W,H --write` on a white or gray object (white T-shirt, wall, paper; the box in pixels of the frame `--still SECOND` writes). An example look that works well on phone footage: `eq=contrast=1.07:saturation=1.05, vibrance=0.13, curves=master='0/0 0.25/0.225 0.5/0.5 0.8/0.83 1/1'`. vibrance above ~0.15 pushes skin toward orange. You can build your own LUT from an approved grade: `ffmpeg -f lavfi -i haldclutsrc=8 -frames:v 1 -vf "<look chain>" look-hald8.png`, then `haldclut` in ffmpeg (or convert the hald to `.cube` for CapCut). Strength via blending: `split[a][b];[b][1:v]haldclut[l];[a][l]blend=all_mode=normal:all_opacity=0.7`. ⟨YOURS: path to the brand LUT⟩

After assembling the rough cut, two mandatory checks, both before rendering:
1. output subtitles: is there an identical sequence of 3+ words at adjacent cuts (a whole missed take);
2. **the edges of all segments by audio** (`speech_mask.py --edl edit/<id>/edl.json`: each segment's source is taken from `edl.json`, exit code 1 on warnings). The “edge inside a word” decision is made on the **raw** envelope, not on the mask: the mask widens speech by ±30 ms and stretches endings, so it would raise false alarms. What is checked:
```text
check window 0.3 s on the far side of the edge; “loud window” = env ≥ threshold (10 ms windows)
edge inside a word : ≥15 loud windows within 0.3 s AND the nearest loud window ≤ 80 ms from the edge
                    → a 30–60 ms dip was taken for a pause; suggest an edge in the next silence
fragment at edge   : by the mask, the first speech span after the edge is shorter than 0.35 s, then silence ≥ 0.2 s
                    → tail of the previous word (or start of the next one, at the end); edge ≈ after the silence − 50 ms
edge too tight     : sound closer than 30 ms to the edge, with silence on the far side
                    → the cut fade (15–30 ms) will eat a consonant; move the edge by 40–50 ms
```
Each warning is a reason to listen and look at the waveform, not an automatic fix (“a short sound followed by silence” can also be a standalone short word, such as the Russian “A”, “and”). On verified videos: a clean cut gave 0 warnings in 7 segments; a multicamera cut gave 1 in 14, a real one (an edge tight against a “k”); the double *teryali* case is caught.

Then **face measurement** on `final.mp4` (`faces.py scan` and `zones`, `references/faces.md`): `faces.json` (false “faces” on knees and hands dropped, with the count in the report) and zones per span. This feeds the camera plan (chin above the subtitles in close-ups), the brief (is there enough “headroom” zone for the chosen style) and the graphics layout.

### Step 7. Graphics brief — one `AskUserQuestion` before the Remotion code
The recommendation for this video goes first. Don't ask about what the prompt already says. At most 4 options per question, the most relevant ones.
1. **Logo**, every time: none / mark in the corner for the whole video / only on the end card / both. This answers where the logo is, not what the ending is: whether the end card carries a CTA is question 2.
2. **End card and CTA**: up to 3 CTAs chosen by format, transcript and audience, the brand's own library (`cta.md`) first, then the plugin's (section 8), with the exact wording from the library (a text adapted to this audience is shown next to the original and called adapted). A CTA already spoken in the speech does not remove these options: it only adds the answers “a card on the spoken words”, “CTA by voice only”, and a logo sting (2–3 s, no CTA). An entertaining video can also end on its payoff with a hold and no card (the logo small over the last 1.5 s, if question 1 asked for one). The agent does not pick the CTA on its own (`references/cta.md`, “How to offer it”).
3. **Techniques** (`multiSelect`): hook headline (with a teaser the line itself is the hook: offer one or the other) · hook as a question · text behind the person (needs a figure cut-out; give a time estimate) · presenter over a scene (overview, review, stream; only if there is something to show) · thesis cards · focus brackets (on a word over the video: a per-video component) · role tags · verdict scale · “save” bookmark · punch-in · icons for theses · phone mockup on the CTA · light flash · slide scene · full-screen phrase. Recommend only what follows from the content. B-roll, code scenes, designed scenes and memes are not asked about here: they are turned on in step 0 and decided in the visual plan (step 7a); with designed scenes on, the hook, full-screen phrase, list and CTA are made as `hook` / `slogan` / `list` / `cta` scenes.
4. **Sound**: none / sound accents on events / accents + music, with specific picks from the library (section 11); with music, duck the music under the key line or the CTA (`master_audio.py --duck`); the track's drop, its loud moment, is another thing and lands on the final phrase.

Answers go into the video's `project.md`; they are not inherited by the next video. An answer about the brand as a whole (a ban, a preferred CTA, a format) goes into the brand folder instead (section 0). Do not silently resolve contradictory answers.
If after the cut the chosen style doesn't fit the frame (for example no headroom for cards), say so here and offer a replacement.

### Step 7a. Visual plan — insert decisions before rendering
All inserts off (`use_broll`, `use_scenes`, `use_memes` all false) → still run `visual_plan.py init edit/<id>` (the export in step 8 needs the plan) and skip the rest of 7a. Otherwise (`references/inserts.md`):
1. `visual_plan.py init edit/<id>`: spans by phrase on the rough-cut timeline + hints (segment join, long segment, number, reference to an object, emotion, hook, CTA) + intensity budget. A “scenes only” promo has no rough cut: `visual_plan.py init edit/promo-<brand> --scenes-only --duration 20 --brand <slug>` (seconds, 15–25, best 18–22), then scenes at absolute times.
2. Decide where an insert **really helps**: understanding, a cut, dynamics, the hook, or emotion for a meme. Each one gets a “what” and a “why”, with the moment given by a word (`visual_plan.py add … --at "word:resume#1"`). Numbers and lists go on cards or `stat` / `list` scenes; the ending and the CTA get no memes. Designed scenes (`references/scenes.md`) go in the same plan: gaps in the video suggest `scene:*`, text is verbatim from the speech or has a source, the default mode keeps the face, and the plan check enforces the reading-time floor and the brand tone's ceilings.
3. Sources by priority (`footage.py plan-search edit/<id>`, `memes.py search`; an insert with no candidate is skipped with the way back, `plan-search --retry` or `--insert ID --query "…"`): B-roll: project → library → code scene → main footage; memes: your own folder and library → none. With the online-sources add-on `it-reelsmaker-online` installed, online sources join the chain, following the add-on's rules.
4. **Show the plan table to the person** (`visual_plan.py md`) together with the card texts and, if any, the list of downloads (source, MB) and paid actions (≈ $). Wait for a “yes”.
5. After the “yes”: take the footage (`footage.py pick`, which prepares it: 1080×1920, 30 fps, no audio, exactly the required length), make the code scenes (`codescene.py scaffold` → write the scene → `render`), prepare and place the memes (`memes.py prepare`, `place`: size and position by the rules, faces by the measurement), validate the plan (`visual_plan.py validate`, 0 errors) and hand it to Remotion (`visual_plan.py export`).
Inserts that did not land (`pending`, `skipped`) do not go into the video: the main footage stays, and the reason goes into the report.

### Step 8. Remotion
Start from the kit's `ReelKit` composition: `brand.py export <slug> --remotion {{REMOTION_DIR}}` (the brand into the Remotion project, once per brand and after brand edits), then `visual_plan.py export edit/<id> --remotion {{REMOTION_DIR}} --props edit/<id>/reelkit-props.json [--hook "text"]` (copies the rough cut to `public/`, writes brand, captions, inserts and scenes as props; `--hook`: a hook headline the kit shows for the first 2.4 s), then `npx remotion render ReelKit out/<name>.mp4 --props=<absolute path>/edit/<id>/reelkit-props.json` in the Remotion project (an absolute path: Remotion reads a relative one from the Remotion folder, which can be a subfolder of the project, and fails); the cover is `ReelCover` with the same props. The kit also draws the virtual camera (shots from `edit/<id>/camera.json`, `references/camera.md`), all three subtitle modes, a logo sting (`export --sting`) and the “framed” format for a horizontal source (`reelcfg.py save edit/<id> --set format=framed`: the window, its caps label, the camera clamped to the window, scenes and subtitles inside it; `references/techniques.md`). Write a per-video composition only for what the kit does not cover, and reuse the kit's components in it. The kit draws the “Marker” (and `v2`) and “Brand” styles itself (the “Brand” focus brackets only inside `stat`, `word` and `cta` scenes: brackets on a word over the video need a per-video composition); “Minimal”, “Editorial”, “Bold” and “Glass” fall back to “Marker” with a warning, so they need a per-video composition (`references/brands.md`, “In Remotion”: styles, `looks`, fonts). The plan check times scenes by the kit's own animations (`references/scenes.md`, reading-time floor), so the composition keeps its entrances at or under them.
Camera (section 9) → B-roll → only the chosen elements → memes → subtitles. Composition 1080×1920, 30 fps, as long as the video (plus the end card, if any). Each element enters **on its own word**, not in a batch. Card texts are written from the meaning of the line and **shown before rendering**: they almost always get edited.
- The brand in code comes from the profile: colors `brand.colors.*`, fonts by family name, logos from the brand's `assets/`. Do not write HEX values or font names into the video's code.
- Graphics positions come from the face-measurement zones (with the span's camera): hook and cards in the “headroom” zone or the “chest” zone, subtitles no higher than the recommended top. Record every card, hook and CTA card over the video in the plan as a `keep_clear` zone (interval + box + the span's camera): that way it is checked against the face right away, memes do not cover it, and the render audit sees it. A list in a close-up lacks “headroom” → raise the camera all the way to the top of the source (`cy = 960 / z`).
- **A phrase is one block** (`references/typography.md`): lead-in tight against the big word, a shared axis, one coordinate system.
- **A cut-out figure on another scene or cutaway** (`references/figure.md`): where the figure touches the edge of its source frame (arm, elbow, lower body), that edge must coincide with the edge of our frame; **a chopped-off arm in the middle of the screen is a defect**. Arm at the left edge of the source → the figure goes only against the left edge of the video; touches both sides or the top → do not put it in a corner. A source-edge cut can be hidden only by the frame edge or an opaque element on top, not by feathering.

### Step 9. Check, render, mastering
- stills (`npx remotion still ReelKit --props=<absolute path>/edit/<id>/reelkit-props.json --frame=N out/still-N.png`; `Reel<id>` only for a per-video composition) at every graphics entrance and every camera shot; for designed scenes, a settled frame (postable as a picture) and a mid-transition frame (no muddy double exposure); at the start and middle of every insert (a meme reads and is off the face, B-roll has no third-party logos);
- render → preview to the person → revisions → only then the master. Run the render as a separate command, checking the exit code and the file time; don't chain `render | tail && master`: `tail` hides a render failure, and the master will silently be built from the old file;
- **a late spot fix** that does not shift timing (a word in a subtitle, a card text, an element's position): not a full render but a re-render of a segment (`patch_render.py out/<render>.mp4 --comp ReelKit --props <absolute path>/edit/<id>/reelkit-props.json --from … --to …`; when the fix is in the props, run `visual_plan.py export … --props` again first; `--comp Reel<id>` only for a per-video composition). The range is widened to the neighboring keyframes [K1, K2), Remotion draws only those (`--frames=K1-(K2-1) --muted`), and the segment is spliced in without re-encoding (if the codec parameters match) or with it; the audio is the old track, whole (if the fix touches audio, a full render is better: Remotion's audio render goes through all frames anyway, so the gain is small). Check: frame count and duration unchanged, timestamps even (every frame at n/fps; this is what catches “stutter”), frames at the joins compared with the old ones by frame number, not by time (PSNR ≥ 35 dB; for static neighboring frames the “best match” is random, so count it as a shift only if the neighboring frame is better by more than 1 dB), and the sheet of joins checked by eye. Measured on a one-minute video: full render 8–10 min, a ~100-frame patch without re-encoding 40–52 s (outside the patch, frames are bit-identical), with re-encoding ~2.5 min. Re-cutting, speed or length changes: full render only;
- **contact sheet** of the finished file, 12 frames in one image: `ffmpeg -i out.mp4 -vf "fps=1/<duration/12>,scale=200:356,tile=6x2" -frames:v 1 sheet.png`; it shows whether the picture changes, whether the top of the head is cut off, whether text covers the mouth;
- **render audit** of faces before showing the video to the person (`faces.py audit out/<render>.mp4 --edit edit/<id>`, `references/faces.md`, section 5): faces after the camera against the subtitle band (where speech is heard), the `keep_clear` zones and memes, plus a cut-off top of the head; fix any overlaps and re-render;
- **cover in frame 0** (optional): a settled frame in a pause of the speech, eyes open (`poster.py pick --sheet`, then `--t`) → `cover.jpg`, replace only frame 0, frame count and duration unchanged, before mastering (`poster.py pick` / `guide` / `bake`, `references/scenes.md`); after mastering, `poster.py attach` embeds the same cover as cover art: without it a file manager shows a random frame (a B-roll shot) as the thumbnail. Order: render → `faces.py audit` on the render → `poster.py pick` / `bake` → `master_audio.py` → `poster.py attach`;
- **audio mastering, always** (section 12, `master_audio.py`), with an acceptance check: failing any checklist item (LUFS, true peak, duration) → non-zero exit code; do not deliver the master. A “scenes only” promo with no voice and no music: effects over silence have no −14 LUFS target, the true peak and durations are checked, and `--check` reads the master's tag and applies the same rule (`references/scenes.md`).

### Step 10. Delivery
Show **measurable results, not “it got better”** (format: the report in `references/examples.md`): duration, remaining silence in ms, master loudness and peak, how many cuts and takes were removed, how many inserts and from where (and which ones did not land, with the reason), and the **Supports** of the finished video (decision → rule → trust; departures; checklist items skipped), so a disliked result points to the rule to change. Found a defect nobody asked about → say so and fix it. Update `project.md`. **On-screen facts need a source**: a number, place, price, contact or promise comes from the speaker's words or from the client; anything the agent took on its own (from a website, “from general knowledge”, by default) goes into “open items” as “to verify”. Attribution for CC files (and stock footage, if any) goes into the post description. A post caption `caption.txt` (1–3 sentences in the brand voice, the same CTA) follows `references/scenes.md`, on a “yes” from `{{APPROVER}}`.

## 7. Two-person skit / “Verdict”

Role tags above the heads, a verdict scale, subtitles colored per speaker, a “save” bookmark, two-shots with rare punch-ins and a frame layout for two people: `references/skit.md`. A library, not a template: the scale only if the video is about an assessment.

## 8. CTA library ⟨YOURS: fill in contacts, remove what you don't need⟩

One CTA per video (exception: a job opening, with apply + recommend), a calm invitation with no “Urgent” or “Hurry up”, two lines on the card: the main line (52–60 px; the kit's full-frame end card draws it up to 64 px / 800) and a clarifier (34–38 px, in a muted color). The codes (`dm`, `dm-word`, `comment-word`, `site`, `bio`, `apply`, `save`, `follow`, …), their texts, audiences and formats: `references/cta.md`; a brand's own library (`brands/<slug>/cta.md`) is offered first. Promises only if they are kept; “Link in bio” only if the link is already there.

## 9. Virtual camera and word anchoring (Remotion)

The camera is `{ z, cx, cy }` (scale and the frame point in the center), with shots listed in **source time** and converted by `at(src)`, so a speed change in `cut.py` breaks nothing. Graphics are anchored **to the spoken word** (`atWord(word, n)`), matching ignoring edge punctuation and case. Code for both: `references/camera.md`.
- `drift`: a slow push-in of +2–6% within a shot; `whip`: a 7-frame transition with `Easing.out(cubic)` and a `sin(πp)·6 px` blur, 1–3 times per video, never above the brand tone's ceiling (none for `premium`, up to 6 for `bold`; `references/brands.md`);
- change shots on the pause between phrases, a shot lasts 1.4–3.5 s; cycle wide → medium → close-up → medium; punch-in on the main point; CTA: close-up with a slow push-in; ending: pull-out;
- **on silence, a hard cut**: a smooth transition over a pause reads as sluggish.

## 10. Special techniques (all per the brief)

Each only if the brief chose it; numbers, layouts, risks and which ones are not yet verified in a finished video: `references/techniques.md` (the cut-out itself: `references/figure.md`). **Cut-out figure**; **text behind the person** (only when the headroom can't hold the hook; the main risk is contrast); **presenter over a scene** (review, stream, window); the **“framed” format** for a horizontal source (a ~1030×1240 window); a **phone mockup on the CTA**; a **light flash** instead of a transition (within the brand tone's ceiling); a **slide scene** to cover choppy speech; a **full-screen key phrase** (1–2 per video, not on the hook or the CTA). **LUT**: see step 6.

**Designed scenes** (`references/scenes.md`): hook, quote, slogan, number, list, before → after, message thread, interface, CTA, cover, drawn in code in brand colors, on a spoken word; the `overlay` / `split` / `panel` / `window` modes keep the face, `full` within the brand tone's ceiling (1–3). **A promo without footage** is the “scenes only” format: 15–25 s, hook → reveal → 2–3 strong moments → ending/CTA, with no source analysis, transcript or cut.

## 11. Your own library of sounds, music and icons (optional)

An `{{ASSETS_DIR}}` folder with sounds, music, icons and memes, used through a catalog (sound start, loudness, background, brand verdict, overview sheets, a meme annotation; `library_catalog.py --dir {{ASSETS_DIR}}`), not by browsing files: `references/library.md`. In every video:
- sound effects: no more than one every 2–3 s, placed by the start of the sound, not of the file, 12–18 dB below voice peaks;
- icons: flat pictograms; service logos only when the service is named; `{{FORBIDDEN_IMAGES}}`, celebrities and film stills are a no; one at a time, 180–320 px, not on the face;
- **music: license first** ⟨YOURS: `{{ACCOUNT_TYPE}}`⟩: a burned-in track needs a commercial license; the safe default is a render without music and a track picked in the app when publishing.

## 12. Audio mastering — every video

Without mastering, finished videos came out between −33 and −17 LUFS, some with clipping. The chain (script `master_audio.py`):
- measure the noise floor → noise reduction (`afftdn`) **only if the floor is louder than −50 dBFS**: on a clean recording it causes artifacts;
- `highpass=f=80`;
- **two-pass** `loudnorm` to **−14 LUFS**, true peak **−1 dBFS**, `linear=true` (single-pass drifts off target); with no voice and no music (scenes only, effects over silence) no −14 target, the peak still ≤ −1 dBFS;
- the audio is put into the render **without re-encoding the video**: `-map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 256k -movflags +faststart -shortest`;
- a final `ebur128` measurement and a duration check **against the video track** (the render's audio can be a fraction of a second longer than the video).

**Music, if burned in:** level by the gap to the voice, sidechain, `amix` only with `normalize=0` (otherwise the voice quietly drops), the music ducked under the key line (`--duck`), the track's drop on the final phrase, then −14 LUFS again: `references/library.md`, “Music in the mix”.

## 13. Pre-delivery checklist

- [ ] The video has only what the brief chose; the brand comes from the profile (colors, fonts, logo); brand-level revisions are recorded in the brand folder (`rules.md`, `cta.md`, `guide.md`)
- [ ] No text on a face: the render audit of faces shows 0 overlaps (subtitles, `keep_clear` cards, memes) + stills every ~2 s or the contact sheet; nothing in the UI zones (top 220, bottom 420, right 120 px)
- [ ] Inserts (if on): each has a “why”, the intensity budget is kept, the plan was shown before rendering; B-roll has no third-party logos and no stock people “playing the client”; downloads and paid actions only after a “yes”, attribution recorded
- [ ] Meme: on its line, rights known, no more than 460 px on the long side, at the edge of the frame, not over the face, subtitles or cards; no more than one full-frame meme
- [ ] Graphics start on their word (±2 frames); hard cuts where there is silence
- [ ] The picture changes every 1.5–3.5 s; close-ups are not blurry; the top of the head is not cut off
- [ ] One style and one accent color; ≤ 6 words in a card or hook headline (designed scenes follow the reading-time floor); no outline or glow (unless the style calls for it)
- [ ] A phrase is one block: parts of one thought tight together, shared axis, one zone; on a still at 25% size it reads as a single mass
- [ ] Text is readable on a phone: headings ≥ 92–96 px, subtitles ≥ 54–64 px
- [ ] The logo is not distorted; on a dark background, the light (white) variant; there is one CTA and it works
- [ ] No leftover takes or slips; no repeats at cuts; the first sound is not clipped; remaining silence stated as a number
- [ ] All segment edges checked by audio (`--edl`): no edge inside a word, no fragments of neighboring words, no edges tight against sound
- [ ] White balance measured on the graded result (`balance.py`): grays neutral, the correction before the LUT; skin natural on `verify/balance.png`
- [ ] Audio has no clicks; master at −14 ±0.7 LUFS (scenes only without voice or music: not required), peak ≤ −1 dBFS, duration = video, `+faststart`; the mastering acceptance check passed (code 0); in the rough cut, video and audio `start_time` = 0
- [ ] Sound effects on their events; burned-in music only with a commercial license; with music, the voice is always louder
- [ ] No icons with a “no” verdict; service logos only when the service is named
- [ ] Special techniques: light flashes within the brand tone's ceiling (`flash_max`; 1–2 is typical); text behind the person reads without an outline, lead-in tight against the word; the mask check frame was reviewed (no furniture or wall); cut-out figure on a scene: not a single chopped-off arm inside the frame, face above the UI; skin looks natural after the LUT; no third-party data on the phone screen or in the scene
- [ ] On-screen facts come from the speaker or the client; anything the agent sourced itself is in “open items”
- [ ] Designed scenes (if any): within the brand tone; quotes verbatim, numbers sourced; reading-time floor kept; the face is not covered in `overlay` / `split`; settled and mid-transition frames reviewed
- [ ] The video makes sense without sound
- [ ] `edit/<id>/project.md` is up to date: session · strategy · brief · decisions · open items
- [ ] Consent from the people on screen; **publishing only after a “yes” from `{{APPROVER}}`**

## 14. Shooting that makes editing possible (a memo for the speaker)

Vertical 4K with room above the head, side light, lines phrase by phrase in takes, 2–3 detail shots, a lavalier for each person in a skit: the memo to send before the shoot is `references/shooting.md`.

## 15. Machine limits ⟨YOURS⟩

On a laptop with 8 GB: one Remotion Studio at a time, videos up to ~60–70 s; longer than 90 s or a heavy figure cut-out needs a stronger machine (the online add-on can run the cut-out on your own server). Local Whisper: medium int8, not large. Cut-out models: measure peak memory before running, and run them one at a time (`references/figure.md`).

**Remotion project dependencies:** `remotion`, `@remotion/cli`, `@remotion/google-fonts`, `@remotion/layout-utils` (text width measurement); all `@remotion/*` packages at exactly the same version as `remotion` (`npm install --save-exact @remotion/layout-utils@<remotion version>`). Measure width only after the fonts have loaded (otherwise the fallback font's width gets cached).

Several agent sessions in one editing folder are normal: write JSON (video settings, plan, indexes, profiles) atomically (temp file + replace) and under a lock over the read–modify–write cycle, with long operations (downloads, ffmpeg) outside the lock; don't touch other people's videos, edit shared Remotion files (`Root.tsx`, shared components) surgically, and put test compositions in a separate entry point and delete them after the check.

## 16. References — when to read

| File | When |
|---|---|
| `references/scripts.md` | any step: which script does it, how to run it, the `cut.json` format |
| `references/brands.md` | step 0 and any graphics: your settings in the project (`reel-defaults.json`, layers, `CLAUDE.md`), brand profiles and documents (rules, video guide, CTA library), a new brand from the minimum, logos, rules from revisions, styles in brand colors and in the kit, fonts, `{{…}}` placeholders |
| `references/scenes.md` | steps 0, 7a, 8–10: designed scenes (catalog, modes, tones, fields, reading-time floor, facts, transitions, sound), promo without footage, cover, post caption; a sample component in `references/scene-sample.md` |
| `references/inserts.md` | step 0 (inserts) and 7a: settings, intensity, when an insert is needed, priority and fallback, visual plan, modes and transitions, code scenes, memes: rights, size and placement |
| `references/faces.md` | steps 6, 8, 9: face measurement with the YuNet model, false “faces” and the filter, zones for the hook, cards and subtitles accounting for the camera, card checks, render audit |
| `references/figure.md` | cut-out figure: the cut-out pipeline and model memory, check frame, presenter over a scene (layouts), source-edge cuts, text behind the person |
| `references/typography.md` | any on-screen text: a phrase as one block, gaps and line breaks, subtitles (contrast, splitting, when to hide), transcription |
| `references/camera.md` | step 8: code for shots in source time (`at`) and graphics on the spoken word (`atWord`) |
| `references/techniques.md` | step 7 techniques: text behind the person, presenter over a scene, framed format, phone mockup, light flash, slide scene, full-screen phrase |
| `references/skit.md`, `references/cta.md` | a two-person skit; the CTA library for the end card and the `cta` scene (how to offer it, audience and format per CTA) |
| `references/library.md` | section 11: your own library, its catalog, sounds for events, music in the mix |
| `references/shooting.md` | before the shoot: the memo for the speaker |
| `references/structure.md` | step 3a: start, middle and ending mechanics (teaser, slow start, proof first, beat before the payoff, re-hook, payoff with a hold, callback, loop), how to offer them, a 20–30 s video in beats |
| `references/examples.md` | steps 5 and 10: what the cut plan and the delivery report look like |
| `references/playbook.md` | before the plan and at delivery: measurement vs taste, trust levels, the project playbook cards, conflicts, “Supports”, learning from a guide or a video, turning corrections into rules |
| `references/pitfalls.md` | something went wrong in steps 6–9: symptom → cause → what to do |
| `references/migrations.md` | step 0: bringing older brand profiles and settings up to date |
| `assets/brand-template/` | brand profile template (`brand.json`, `rules.md`, `assets/`); copy into `{{PROJECT_ROOT}}/brands/<slug>/` |
