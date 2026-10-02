# Designed scenes: hook, quote, slogan, number, list, CTA, cover

A designed scene is a frame, or part of a frame, drawn in code in Remotion with the brand's colors and fonts: a big hook, a quote, the main thought as a punch, a number with a counter, a list, “before → after”, a message thread, a product interface with a cursor, a CTA action, a cover. A scene is placed **on a spoken word** and goes through the same visual plan, the person's approval (“yes”), intensity budget and face check as B-roll. This is motion design in code: no model generates any image, video or audio.

How it differs from its neighbors:
- a **card** (`typography.md`) is short text over the shot, part of the video's graphics, not in the plan;
- a **code scene** (`inserts.md`) is an illustration **without text**, used like B-roll;
- a **designed scene** is about the text and its meaning: a visual delivery of a word the viewer is meant to read.

The planning method is adapted from the [brag](https://github.com/latent-spaces/brag) skill (MIT) for videos with a live speaker: tones, the storyboard as a contract, “show the thing”, a reading-time floor, facts only from a source, transition hygiene, a poster in frame 0, a post caption.

## When a scene is needed: gaps in the video

When the plan is built, spans get `scene:*` hints. A hint is a prompt to think, not a decision; every scene must have `what` and `why`.

| Hint | Sign in the speech | Scene |
|---|---|---|
| `scene:hook` | the first 1.5 s are weak: a filler word, a slow start, no question or number | `hook` |
| `scene:stat` | a number, price, deadline, percentage | `stat` (or a card if the number is secondary) |
| `scene:list` | “first”, “firstly”, three or more parallel items separated by commas (or the same in the speaker's language) | `list` (the `panel` mode also hides choppy cuts) |
| `scene:quote` | “said”, “says”, “writes”, someone else's words, a strong line from the speaker | `quote` |
| `scene:slogan` | “the main thing”, “the point is”, “remember”, “that's why”, a repeated thought | `slogan` (once per video) |
| `scene:ui` | website, app, service, bot, “in my profile” | `ui`, only with real screenshots or a screen recording |
| `scene:cta` | the last span with an action verb: message, follow, save | `cta` |
| `scene:word` | a segment > 6 s where a shot-size change was already used; an abstract idea with nothing to show | `word` or B-roll |

A scene is **not needed** when the face and intonation matter more (a personal story, a punchline), when other graphics are already on screen, or when a card is enough.

## Scene catalog

| type | On screen | Required | Modes |
|---|---|---|---|
| `hook` | a hook of 2–6 words, one accent word; variants `slam` (fast in, then holds), `type` (typed out), `stack` (words stack up), `counter` (a number) | `text.lines`, `variant` | overlay, split, full (≤ 1.5 s, fast tones only) |
| `quote` | a **verbatim** quote, quotation marks, an all-caps caption “NAME · ROLE” | `text.lines`, `source` | overlay, split, full |
| `slogan` | the main thought as a punch: a color field wipes in, words come in one by one on their spoken words (an evolution of the full-screen phrase) | `text.lines` | full, split |
| `stat` | a big number with a from → to counter, a caption, a source | `value`, `text.lines`, `source` | overlay, split, full |
| `list` | 3–5 items, each on its own word | `items` (≥ 2, each with `at` or `t`) | panel, split, full |
| `contrast` | “before → after”: the first word is crossed out, the second appears | `text.lines` = [before, after] | overlay, split, full |
| `word` | a word made visual: an icon from the library, a mini diagram, “200 → 5” as a grid of cards, a funnel, a timeline | `text.lines` (caption), `media` or `variant` | overlay, split, panel |
| `chat` | messages and notifications, one at a time | `items` (`from`: me / them / system) | split, full, window |
| `ui` | the product in use: entry → action → result; a cursor along a path, a tap ripple, a typing caret | `media`, `interaction` | split, full, window |
| `cta` | the CTA as an action: a tap on “Message”, a code word typed into a comment, a pointer to the link in the profile | `text.lines` (the 2 CTA lines), `variant`: tap / comment / bio | overlay, full |
| `cover` | a cover: the hook large over a frame of the video | `text.lines` | still only |

## Modes: the face stays in the frame

In a talking-head video the face and intonation are the main asset, so by default scenes **do not cover the face**.

| Mode | What | Subtitles |
|---|---|---|
| `overlay` | graphics over the shot in a free zone from the face measurement (“headroom” or “chest” zone), like a card; recorded in `keep_clear` | stay, unless the scene repeats the speech |
| `split` | the speaker scales to ×0.56 and moves down to the center (top of the video at y 900); the scene sits above in y 220–880 on a field in the style color | hidden: the scene's text replaces them |
| `panel` | a slide scene: the speaker at ×0.42 moves to the free edge, a panel comes in from the other side | hidden while the panel is on |
| `window` | the scene fills the frame, the speaker is in a rounded 360×480 window in a bottom corner | hidden |
| `full` | the scene fills the frame, the speaker is hidden, the voice continues | hidden |

In every mode except `overlay` the layout changes first (the speaker moves, or the field covers the frame): about 0.6 of the transition, ≈ 0.27 s for a fade, nothing for a cut. The text enters after it, and the same happens in reverse on the way out.

`full` stays within the brand tone's ceiling (1–3); two `full` scenes in a row (gap < 2 s) are not allowed; a `full` hook lasts at most 1.5 s, which only the fast tones fit (`feature`, `punchy`, `hype`, with a cut): in `calm`, `deadpan` and `cinematic` the entrance, the exit and 0.8 s of reading already take longer, so there the hook goes in `overlay` or `split`. Not on the CTA line (except the `cta` scene) and not in the last 2 s (that is for `cta` or a logo sting).

## Brand tone and scene tone

**Brand tone** (`brand.json → tone`, `references/brands.md`) is a ceiling: which memes are allowed, how many cutaways, how loud the techniques can be, and which scene tones are allowed.

**Scene tone** (`reel.json → scene_tone`; a scene can have its own `tone`) is the energy and pace of this video's scenes, chosen from those the brand tone allows:

| tone | In, frames | Out | Hold after the last word | Entrance motion | Default transition |
|---|---|---|---|---|---|
| `calm` | 14 | 9 | 0.4 s | rise 30 px + fade in, `Easing.out(cubic)` | fade |
| `deadpan` | 18 | 12 | 0.6 s | fade in only; lots of empty space, one thought at a time | fade |
| `cinematic` | 16 | 10 | 0.5 s | scale 0.95 → 1 + fade in, large type | fade |
| `feature` | 10 | 8 | 0.4 s | slide 60 px from the side, “feature cards” | slide |
| `punchy` | 8 | 6 | 0.3 s | slam: 1.08 → 1, a light overshoot if the brand tone allows it | cut |
| `hype` | 5 | 4 | 0.25 s | zoom 1.2 → 1, a 2–4 px shake for 6 frames (`bold` only) | cut |
| `parody` | 0 | 0 | 0.5 s | appears whole; the absurd played completely straight (`bold` only, on request) | cut |

Hook and ending formulas by tone:
- `calm`: the hook is a specific fact or observation; the ending is the name, the brand line, silence;
- `deadpan`: one quiet observation with no lead-in; the ending is just the name and a long hold;
- `cinematic`: a sweeping statement about the world, short sentences; the ending is the name slamming in full frame;
- `feature`: a feature name plus 1–2 details; the ending is the call to action;
- `punchy`: a question or observation that the next line pays off;
- `hype`: SHORT, ALL CAPS, one word or number per beat;
- `parody`: the problem stated completely seriously.

## Storyboard: scene fields

A scene is an entry in `edit/<id>/visual_plan.json` with `kind: "scene"` (ids `c01`, `c02`…). The plan is the contract: what appears, in what order and on which word is decided here, not in code.

```json
{"id": "c01", "kind": "scene", "type": "quote", "mode": "split", "at": "word:thinking#1", "start": 12.3, "dur": 3.6,
 "tone": null, "text": {"lines": ["Test how they think,", "not what they remember"], "accent": "think", "label": "NAME · ROLE"},
 "source": {"kind": "speech", "ref": "12.3–14.1"}, "what": "the quote large above the speaker",
 "why": "the main thought of the video", "transition_in": "fade", "transition_out": "cut", "sound": "hit",
 "hide_subtitles": true, "status": "planned"}
```

Check of this example: 8 words need 2.4 s settled; 3.6 s minus the entrance and exit of `calm` (14 + 9 frames ≈ 0.77 s) and minus the layout change of `split` before the text (fade, ≈ 0.27 s) leaves ≈ 2.57 s ✓; the scene leaves at 15.9 s, well after the last spoken word (14.1 s) plus the 0.4 s hold ✓.

Fields: `type`, `mode`, `at` or `start`, `dur`, `tone`, `text` (`lines`, `accent`, `label`), `items` (`text`, `at` or `t`, `from`), `value` (`from`, `to`, `prefix`, `suffix`, `decimals`), `media`, `interaction` (`kind`: tap / type / cursor / swipe, `target`, `text`, `at`), `box`, `source` (`kind`: speech / brief / brand / client / agent, `ref`), `what`, `why`, `transition_in`, `transition_out`, `sound`, `hide_subtitles`, `status` (planned → ready once the fields pass the check; skipped). A scene needs no file: it is drawn at render time from its fields.

Scene texts, like card texts, are **shown to the person before rendering** in the visual plan table.

**Plan check** (an error stops the edit until it is fixed):
1. the required fields for the type; the mode is allowed for the type; the scene tone is allowed by the brand tone;
2. the reading-time floor (below) for the scene tone;
3. `quote` with `source.kind = speech`: the lines, joined and normalized (case, letter variants and punctuation ignored), are a contiguous run of words in the transcript; otherwise “the quote is not verbatim”; `client` and `brief` need `source.ref`;
4. `stat` without `source` is an error; `source.kind = agent` is a warning, “to verify”, carried into the report;
5. contrast of the brand color pairs the scene writes text with (`primary`/`text_on_primary`, `accent`/`text_on_accent`, `light`/`primary`): large text ≥ 3.0;
6. budget: `full`, `split`, `panel`, `window` count toward intensity coverage together with B-roll; `overlay` counts like a card, through `keep_clear`; the number of `full` scenes and “not in a row”;
7. the brand tone's ceilings: memes, transitions, light flashes, whips, full-frame scenes;
8. `overlay`, `window`, `split` with a box get the same checks as a B-roll window: safe zone, face, `keep_clear`;
9. one scene at a time, a scene doesn't overlap a meme, only `cta` or a logo sting in the last 2 s.

## Scene rules

**Show the thing.** Material in order of preference: the real product in use (a screenshot, a screen recording, an object from the source footage) → a recreated interface element → an animated idea (a grid of cards, a funnel) → large typography. Abstract filler (gradients, particles, waves, a “tech background”) is not allowed: a still should be about this video, not any video.

**Reading-time floor.** “Settled” means the whole text is on screen and not yet leaving (`dur` minus the layout change, if any, and the tone's entrance and exit).
- 1–3 words: at least 0.8 s;
- a phrase: 0.3 s per word, at least 1.2 s; the hook gets the most;
- the floor counts from the moment the whole text is on screen: after the entrance, or from the last word if the text builds up word by word on the speech;
- text the speaker says doesn't leave earlier than the tone's hold after the last spoken word (0.25–0.6 s, table above): the viewer reads along while hearing it;
- items one by one: no faster than 0.6 s apart;
- fast in, then hold: pace comes from motion and cuts, not from text that leaves before it can be read;
- it doesn't fit → cut the text or split the scene; don't speed it up.

**Facts only from a source.** A claim (a name, number, capability, quote, price) comes from the speaker's words (a timecode), the brief, the brand profile or the client (`ref` says where). The framing is free: lead-ins, a joke, a question in the hook assert nothing. A quote from the speech is checked against the transcript **word for word**; if you want it shorter, take another line or make it a `slogan` without quotation marks. A number without a source is an error; one the agent found itself goes into “open items” as “to verify”.

**One by one, and as an action.** A set (items, messages, cards) appears one at a time, each on its own word. An action (tap, type, scroll) is shown with a cursor, a tap, a caret, not as a static screenshot. The sound matches the motion.

**Transitions.** Don't crossfade two busy layouts: you get a muddy double exposure. The old one leaves, then the new one enters, or the transition goes through the brand's background color. A transition over a pause is a hard cut. Stills both settled and **mid-transition**.

**Every still is postable.** If a settled frame of the scene wouldn't work as a picture for a post, the scene isn't ready.

**Data on screen.** Other people's names, emails, phone numbers and amounts in interface screenshots are replaced with fictional ones, and the plan says so.

## Scene sound

Sounds come from your own library `{{ASSETS_DIR}}`; CC0 packs are the easiest (no attribution, commercial use allowed); keep the license next to the files.

| Moment | Sound family |
|---|---|
| hook, reveal, change of section | soft low impact |
| card, item, message | card, paper, soft “drop” |
| typing | individual key presses, a different file for neighboring characters, quiet |
| tap, cursor, toggle | short click |
| payoff, number lands, logo | bell or glass, once |

The sound goes on the **start** of the motion (0–0.1 s before the first visible frame). In a sequence, sound the first, the last or the strongest item, not every one. Repeated sounds should have no sharp, ringing highs: they are fatiguing. Density follows the brand tone, and no more than one effect every 2–3 s.

**Beat.** Scenes are placed on the music's beat only if the music is burned in and has a commercial license: major moments within ±0.15 s of a strong beat, small ones within ±0.10 s of the grid, readable text on every other beat. Without burned-in music, the speech is the video's clock: the anchor is the word.

## The “scenes only” format: a promo without footage

A video with no talking head: the brand's texts, numbers and pictures, in scenes only. The brand profile, the CTA library, sounds, mastering and the cover all work as usual.
1. **Material.** The brand profile, the texts, numbers and screenshots the person provides (from their site, deck or product). First answer 6 questions: what it is, in one sentence; who it is for and what it does for them; what sets it apart; the strongest line or number (verbatim from a source); what real material to show; which tone.
2. **Storyboard:** hook 2–3 s → reveal 2–4 s → 2–3 strong moments → ending / CTA 2–4 s. 15–25 s in total, 18–22 is the sweet spot. Number of scenes by tone: `calm` and `deadpan` 3–4 with long holds, `feature` 4–6, `punchy` 4–5, `hype` 6–8. Add up the durations.
3. A plan without speech spans: scenes at absolute times, back to back, covering ≥ 95 % of the video; the first scene is the `hook`, from 0 s. All scenes are `full` (there is no speaker), so the rules that protect the face don't apply: the intensity budget and spacing, the `full` ceiling, “not two `full` in a row” and the 1.5 s limit on a `full` hook. Everything else does: the reading-time floor, facts from a source, transitions, the brand tone's scene tones and its transition, light flash and whip ceilings.
   Steps 1–6 (source analysis, transcript, takes, rough cut) are skipped: the video id is a short name such as `promo-<brand>`, and the work goes from the brand and the 6 answers straight to the storyboard (step 7a), then render, sound, cover.
4. Render with the same template, without video and without subtitles.
5. Sound: effects on events + music only with a commercial license; mastering as usual.

## Cover and frame 0

The preview of a video in messengers and most players is frame 0; social networks let you pick a cover on upload, but frame 0 still shows when the video is forwarded.
1. A `cover` scene or the strongest **settled** frame (the hook fully on screen, not mid-transition) → `edit/<id>/cover.jpg`.
2. Check the cover text against the profile-grid crop (centered in the frame) and the UI zones.
3. Replace **only frame 0**: `ffmpeg -i <render>.mp4 -i cover.jpg -filter_complex "[0:v][1:v]overlay=0:0:enable='eq(n,0)'[v]" -map "[v]" -map 0:a? -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -c:a copy -movflags +faststart <render>-cover.mp4`. Check: the frame count and the video and audio durations are the same before and after. Order: render → cover → mastering (mastering copies the video without re-encoding).
4. Deliver `cover.jpg` with the master, for uploading the cover by hand.

## Post caption: `caption.txt`

1–3 sentences that can be posted as is: in the brand voice and the video's tone, specific to the video, with the same CTA as the card, no “excited to share” and no clichés. Below it, the CC attribution lines and notes (consent of the people on camera). Approved by `{{APPROVER}}`.

| Tone | Template |
|---|---|
| calm | observation → the video's conclusion → CTA |
| deadpan | one dry sentence → the name |
| cinematic | the brand line or the main thought → CTA |
| feature | what's new → 2–3 details separated by commas → CTA |
| punchy | question → short answer → CTA |

## In Remotion

- One scene layer in the video's composition: above B-roll, below memes and subtitles; `split`, `panel` and `window` move the speaker's video, `full` covers the frame. Without video, it is the “scenes only” format.
- The brand comes only from the profile (colors by role, fonts by family name); typography follows “a phrase is one block” (`typography.md`). No outlines, glow, shadows or gradients; shake and overshoot only if the brand tone allows them.
- Scene tone: the table above, the same numbers in the plan and in code.
- A sample component: `references/scene-sample.md`.
