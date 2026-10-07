# Brands: saved profiles, choosing one before the edit, a new brand from a minimum

The skill edits videos for any brand. Everything that sets brands apart lives in the profile: colors, fonts, logos, LUT, styles, bans, who approves, insert settings. The pipeline (cutting, camera, subtitles, mastering) is the same for every brand.

## Where they live

A brand is a folder `<PROJECT_ROOT>/brands/<slug>/` in the editing project (the template is `assets/brand-template/` in the skill folder):

| What | Why |
|---|---|
| `brand.json` | the machine part: colors by role, fonts, logos, LUT, default style and subtitles, bans, meme policy, meme size, insert defaults, who approves, account type |
| `rules.md` | rules in words: what is allowed and what is not, bans, voice + a log of brand-level revisions (`brand.py rule`) |
| `guide.md` | the brand's video guide: palette roles, typography, signature elements, motion, imagery bans, where video departs from the static guidelines; set in `brand.json → guide` |
| `cta.md` | the brand's own CTA library with exact texts; set in `brand.json → cta_library`; structure and generic templates: `references/cta.md` |
| other `.md` | any other brand document (a recurring skit format, a series template), linked from `rules.md` |
| `assets/` | logos, LUT, font files: the brand is self-contained and moves as one folder |

`brand.py show <slug>` lists the rules, the video guide, the CTA library and the other documents it finds (✗: set in the profile, but the file is missing). The agent reads `rules.md` and `guide.md` before any graphics and `cta.md` at the brief's CTA question.

Profiles live in the project, not in the plugin: a plugin update doesn't touch them, and you can keep the brand folder in your own git. Profiles from the old version (`~/.claude/skills/reels-montage/brands/`, before 1.0) move into `<PROJECT_ROOT>/brands/` as they are.

**The `{{…}}` placeholders in SKILL.md** are fields of the selected brand's profile:

| Placeholder | Profile field |
|---|---|
| `{{BRAND}}`, `{{VOICE}}`, `{{TAGLINE}}` | `name`, `voice`, `tagline` |
| `{{DARK}}`, `{{ACCENT}}`, `{{LIGHT}}` | `colors.primary`, `colors.accent`, `colors.light` |
| `{{MUTED}}`, `{{MARKER}}`, `{{INK}}` | `colors.extra.muted`; `colors.extra.marker` (the marker color); `colors.extra.ink`, alias `on_marker` (text on the marker). If the brand doesn't set a marker, `{{MARKER}}` = `colors.accent` and `{{INK}}` = `colors.text_on_accent`; its own marker without `ink` gets near-black `#111111` text |
| `{{FONT_HEADING}}`, `{{FONT_TEXT}}`, `{{FONT_SERIF}}` | `fonts.heading`, `fonts.body`, `fonts.serif` (optional: the serif of “Editorial”; the kit takes it for that style's headings when `looks.editorial.heading` is not set: `brand.py set <slug> fonts.serif.family="Playfair Display" fonts.serif.weights=[600,700] fonts.serif.source=google`). The general way to give any style its fonts is `looks.<style>.heading` / `.body`. The kit loads the upright faces of a Google font only: an italic (Editorial's “serif italic”) is loaded in the per-video composition (`loadFont("italic", { weights, subsets })` from the same `@remotion/google-fonts` module), otherwise the browser slants the upright face; a local font's italic files (`fonts.<role>.italic`) are loaded |
| `{{LOGO_DARK_BG}}`, `{{LOGO_LIGHT_BG}}`, `{{LOGO_MARK}}` | `logos.on_dark`, `logos.on_light`, `logos.mark_on_dark` |
| `{{FORBIDDEN_IMAGES}}`, `{{FORBIDDEN_WORDS}}` | `forbidden_imagery` (+ `_en`, for English-language searches and prompts), `forbidden_words` |
| `{{SITE}}`, `{{HANDLE}}`, `{{CODE_WORD}}` | `cta.site`, `cta.handle`, `cta.code_word` |
| `{{APPROVER}}`, `{{ACCOUNT_TYPE}}` | `approver`, `account` |

**Subtitle colors per speaker** (a two-person video): `colors.speakers`, an optional list in the order of the sorted speaker labels (`brand.py set <slug> colors.speakers='["#F7F9FB","#8FDCDD"]'`). Without it the first speaker keeps the subtitle mode's own colors and the second takes `colors.accent`; a dark accent over the “Typewriter” darkening needs a lighter tint here (measure: `visual_plan.py shade edit/<id> --color <hex>`).

## Your settings in the project

The plugin folder is replaced on every update, so nothing personal is written there. Your choices live in the project:

| What | Where | How |
|---|---|---|
| defaults for every video of the project: default brand (`settings.brand`), inserts on/off, `library_dirs`, your own labels for intensity and brand tones in your language, … | `{{PROJECT_ROOT}}/reel-defaults.json` | `reelcfg.py defaults` |
| everything about one brand: profile, rules, video guide, CTA library, other documents | `{{PROJECT_ROOT}}/brands/<slug>/` | `brand.py`, the files themselves |
| project-wide notes: folder layout, which Python to run, servers, lessons from past videos, the person's ready prompts | the project's `CLAUDE.md` | by hand; Claude Code reads it by itself |

**Project defaults.** `reel-defaults.json` has the same format as the plugin's `assets/reel-defaults.json`, but holds only the keys you change. It is deep-merged over the plugin's file: nested objects key by key, lists replaced whole. For example:

```json
{"settings": {"brand": "acme", "use_scenes": true, "library_dirs": ["library"]},
 "intensity": {"moderate": {"label": "⟨your word for “moderate”⟩"}},
 "brand_tones": {"expert": {"label": "⟨your name for the expert tone⟩"}}}
```

- `reelcfg.py defaults`: print the project defaults file (or say there is none yet);
- `reelcfg.py defaults --set brand=acme use_scenes=true`: write `settings` keys (the file is created if needed);
- `reelcfg.py defaults --unset use_scenes`: remove keys, so the plugin's default applies again;
- `--set` and `--unset` touch only the `settings` keys; labels and other sections are edited in the file by hand;
- `reelcfg.py show edit/<id>` marks the keys that come from this file as `project`.

**Layers** (the right one overrides the left): plugin defaults ← online add-on defaults (if installed) ← the brand tone preset's defaults (`intensity`, `use_broll`, `use_memes`, `scene_tone`) ← the project's `reel-defaults.json` ← the file named in `REELS_DEFAULTS_OVERLAY` ← brand profile `inserts` ← `edit/<id>/reel.json` ← words in the prompt. Your project defaults beat the preset's guesses, but not its ceilings: `meme_size` stays capped by the tone, and `visual_plan.py validate` still enforces the tone's limits (number of memes, transitions, full-frame scenes).

## Step 0: choose the brand

1. List the saved brands. The most recently used come first (`last_used`).
2. If the brand is clear from the prompt or the folder, don't ask. A default brand in the project defaults (`settings.brand`) counts as clear unless the prompt names another one.
3. If it isn't clear, make the first question of the step 0 `AskUserQuestion` offer the 3 most recent brands. A new brand comes in through “Other”: a name and 1–3 colors, then the **brand tone** (section below).
4. Write the brand to `edit/<id>/reel.json` and update `last_used` in the profile.
5. Read the brand's `rules.md` and its video guide (`guide.md`, if set) before doing any graphics; its CTA library (`cta.md`) at the brief.

## A new brand from a minimum

The name, the colors and the **brand tone** are asked for (eight presets, see “Choosing from eight” below; the recommendation for the brand's field first). The agent infers the rest itself and says what it filled in:

- **Color roles:**
  - `primary`: the darkest (relative luminance < 0.25), otherwise near-black `#111418`;
  - `accent`: the most “vivid” of the rest, by saturation × brightness;
  - `light`: the lightest (> 0.75), otherwise `#FFFFFF`.
- **Text color on a background.** The first brand color with a WCAG contrast ≥ 4.5; the brand's own dark color is preferred over black. If `accent` on `primary` gives a contrast < 3, warn.
- **Materials.** The agent looks for them in `<project>/<slug>-brand/`, `<project>/brand/` and in any folders it is given:
  - logos: by `logo`, `mark`, `emblem` in the name (or the same word in the brand's language);
  - fonts: `.ttf/.otf/.woff2`;
  - LUT: `.cube` or hald `.png`;
  - brand book: `.pdf`;
  - past videos.
  Whatever it finds, it copies into `assets/`.
- **Fonts by family.** Group the found files by family and weight from the file name (Thin 100 … Black 900; italic is Italic/Oblique/`-It`): headings get the family with the boldest weight, body text gets the next one; italic is a separate style. Use the same words in the template's font loader, otherwise Light becomes 400.
- **Identical names:** compare by content (hash). A different file with the same name gets `-2`; assets already written are not overwritten. **Slug:** Latin letters, digits, `-`, `_` only; reject paths containing `..`.
- **Fonts.** If the brand has no fonts of its own, use Manrope + Inter, but only if they cover the brand's language (both cover Latin and Cyrillic). Otherwise choose fonts that cover the required script.
- **Rules.** The agent creates `rules.md` with the basics.

## Brand tone: what the brand's videos may do

The brand tone is one choice that immediately sets the limits for all of the brand's videos: **which memes are allowed, how many cutaways (B-roll and designed scenes) and how loud the visual techniques can be**. In the profile: `"tone": {"preset": "expert", "overrides": {}}`.

| Preset | For | Memes | Cutaways (intensity) | Techniques | Scene tones |
|---|---|---|---|---|---|
| `premium`: “Premium, restrained” | luxury, finance, law, premium B2B | none | minimal | quiet: cut and fade only, no light flash or whip, full-frame ≤ 1 | calm, deadpan, cinematic |
| `warm`: “Warm, caring” | medicine, psychology, wellness, children and family, nonprofits | none | moderate | soft: cut, fade and slide only; no light flash, whip, shake or bounce; full-frame ≤ 1 | calm, feature, cinematic |
| `expert`: “Expert, calm” | consulting, recruiting, education, B2B expertise | only on explicit request, ≤ 1, `s` | moderate | calm: whip ≤ 3, light flash ≤ 2 by choice, full-frame ≤ 2, no bounces | calm, feature, cinematic, deadpan |
| `story`: “Atmospheric, story-led” | travel, hotels, architecture, crafts, personal brands | none | active (lots of B-roll) | quiet over busy footage: whip ≤ 2, light flash ≤ 1, no shake or bounce, full-frame ≤ 3 | cinematic, calm, deadpan |
| `tech`: “Tech, precise” | SaaS, IT, fintech, software products and tools | only on explicit request, ≤ 2, `s` | moderate, mostly interface and number scenes | crisp: whip ≤ 4, light flash ≤ 1, no shake or bounce, full-frame ≤ 3 | feature, punchy, calm, deadpan |
| `friendly`: “Lively, friendly” | real estate, local business, lifestyle, communities | yes, ≤ 2, up to `m` | moderate | lively: soft overshoot, whip ≤ 4, light flash ≤ 2, full-frame ≤ 2 | punchy, feature, calm, deadpan |
| `drive`: “Energetic, sales-driven” | e-commerce, launches and sales, fitness, courses | yes, ≤ 1, up to `m`, not recommended by default | active | loud without jokes: whip ≤ 5, light flash ≤ 3, bounce, no shake, full-frame ≤ 3 | punchy, feature, cinematic, calm |
| `bold`: “Bold, with humor” | entertainment, events, provocative and humorous content | yes, ≤ 4, up to `l`, a full-frame meme is fine | active | loud: light shake, fast zooms, light flash ≤ 3, whip ≤ 6, full-frame ≤ 3, hype and parody tones on request | punchy, hype, parody, cinematic, deadpan |

The nearest neighbors differ on at least two of these: memes, cutaways, loudness, scene tones. `warm` has more cutaways than `premium` and feature cards, but no light flash and no memes; `story` is busy through footage, not through loud techniques; `tech` moves faster than `expert` (punchy scenes, more full-frame scenes) but, unlike `friendly`, never bounces; `drive` sells without jokes: no parody, hype or shake, and almost no memes.

The presets in full (exact values, for the plan check):

```json
{"premium":  {"intensity": "minimal",  "motion": "calm",      "memes": {"allowed": false, "default": false, "max": 0, "size_max": null, "cutaway": false},
              "transitions": ["cut", "fade"], "flash_max": 0, "whip_max": 0, "shake": false, "overshoot": false, "full_scenes_max": 1,
              "scene_tones": ["calm", "deadpan", "cinematic"], "scene_tone": "calm", "sfx": "sparse"},
 "expert":   {"intensity": "moderate", "motion": "calm",      "memes": {"allowed": true,  "default": false, "max": 1, "size_max": "s",  "cutaway": false},
              "transitions": ["cut", "fade", "whip", "slide", "flash"], "flash_max": 2, "whip_max": 3, "shake": false, "overshoot": false, "full_scenes_max": 2,
              "scene_tones": ["calm", "feature", "cinematic", "deadpan"], "scene_tone": "calm", "sfx": "sparse"},
 "friendly": {"intensity": "moderate", "motion": "lively",    "memes": {"allowed": true,  "default": true,  "max": 2, "size_max": "m",  "cutaway": false},
              "transitions": ["cut", "fade", "whip", "slide", "flash"], "flash_max": 2, "whip_max": 4, "shake": false, "overshoot": true, "full_scenes_max": 2,
              "scene_tones": ["punchy", "feature", "calm", "deadpan"], "scene_tone": "punchy", "sfx": "moderate"},
 "bold":     {"intensity": "active",   "motion": "energetic", "memes": {"allowed": true,  "default": true,  "max": 4, "size_max": "l",  "cutaway": true},
              "transitions": ["cut", "fade", "whip", "slide", "flash"], "flash_max": 3, "whip_max": 6, "shake": true, "overshoot": true, "full_scenes_max": 3,
              "scene_tones": ["punchy", "hype", "parody", "cinematic", "deadpan"], "scene_tone": "punchy", "sfx": "dense"},
 "warm":     {"intensity": "moderate", "motion": "calm",      "memes": {"allowed": false, "default": false, "max": 0, "size_max": null, "cutaway": false},
              "transitions": ["cut", "fade", "slide"], "flash_max": 0, "whip_max": 0, "shake": false, "overshoot": false, "full_scenes_max": 1,
              "scene_tones": ["calm", "feature", "cinematic"], "scene_tone": "calm", "sfx": "sparse"},
 "story":    {"intensity": "active",   "motion": "calm",      "memes": {"allowed": false, "default": false, "max": 0, "size_max": null, "cutaway": false},
              "transitions": ["cut", "fade", "slide", "whip", "flash"], "flash_max": 1, "whip_max": 2, "shake": false, "overshoot": false, "full_scenes_max": 3,
              "scene_tones": ["cinematic", "calm", "deadpan"], "scene_tone": "cinematic", "sfx": "moderate"},
 "tech":     {"intensity": "moderate", "motion": "lively",    "memes": {"allowed": true,  "default": false, "max": 2, "size_max": "s",  "cutaway": false},
              "transitions": ["cut", "fade", "slide", "whip", "flash"], "flash_max": 1, "whip_max": 4, "shake": false, "overshoot": false, "full_scenes_max": 3,
              "scene_tones": ["feature", "punchy", "calm", "deadpan"], "scene_tone": "feature", "sfx": "moderate"},
 "drive":    {"intensity": "active",   "motion": "energetic", "memes": {"allowed": true,  "default": false, "max": 1, "size_max": "m",  "cutaway": false},
              "transitions": ["cut", "fade", "slide", "whip", "flash"], "flash_max": 3, "whip_max": 5, "shake": false, "overshoot": true, "full_scenes_max": 3,
              "scene_tones": ["punchy", "feature", "cinematic", "calm"], "scene_tone": "punchy", "sfx": "dense"}}
```

How it works:
- **A ceiling, not a target.** The preset sets the defaults (intensity, B-roll on or off by `broll_default`, on in every preset; memes on by `memes.default`, which `friendly` and `bold` set; meme size; scene tone). These are settings, not the person's choice: a tone default stays on unless your project's `reel-defaults.json`, the profile's `inserts` or the video's `reel.json` says otherwise, which is why step 0 saves every insert the person did not choose as `false` and the ceilings the visual plan check enforces: number and size of memes, a full-frame meme, allowed transitions, number of light flashes and whips, number of full-frame scenes, scene tone. A violation is an error.
- **Settings layers:** skill defaults (with the add-on's) ← tone preset defaults ← the project's `reel-defaults.json` (section “Your settings in the project”) ← the file named in `REELS_DEFAULTS_OVERLAY` ← the video profile's defaults (`references/profiles.md`) ← the profile's `inserts` ← the video's `reel.json` ← words from the prompt. Ceilings: the preset plus `tone.overrides`, whatever the layers say; a video profile asking for more (an entertaining video's `active` intensity at an `expert` brand) is held at the tone's, and `reelcfg.py show` says so.
- **The brand's own tone for a video profile:** a brand that makes louder (or quieter) videos of one kind on purpose records it once, as the owner's decision: `brand.py tone <slug> drive --profile entertaining` writes `brand.json → tone.by_profile`, keeps the main tone for every other video, and the profile's videos take that preset as their ceiling with no per-video override (the main tone's `overrides` don't apply to it). The main tone's preset removes the entry; changing the main tone keeps it. Offer it when the person asks twice for a louder video of the same profile; the brand owner confirms.
- **Louder than the brand tone** only on the person's explicit request for this video: `reel.json → "tone_override": true`; violations become warnings and go into the report.
- **A custom tone** (“Other” in the question, described in words): the nearest preset plus field changes in `tone.overrides`.
- `memes_policy` (meme rights) and `motion`, if set explicitly in the profile, override the preset. A profile without a tone gets `expert` when it is brought up to date (`references/migrations.md`), with one line saying so and how to change it.
- The recommendation when creating a brand follows the field (the “For” column) and the brand voice: a bank or lawyer → `premium`; a clinic, psychologist or nonprofit → `warm`; an expert or an education project → `expert`; a hotel, travel or architecture brand → `story`; a SaaS or IT product → `tech`; a café, real estate agent or community → `friendly`; a shop, launch or fitness brand → `drive`; an event agency with a sense of humor → `bold`.

**Choosing from eight.** A question shows at most 4 options. So first show all eight in a short text table (name in the person's language, what it is for, what it allows), then ask one question with the 4 that fit the brand's field best, the recommendation first; any other preset can be typed by name in “Other”.

### Changing the brand tone

On request (“change the brand tone”, in any language):
1. Show the eight presets in a short text table: what each one changes (memes, cutaways, how loud the techniques are), the current one marked.
2. One question: the current tone, marked “current”, and the 3 that fit the brand's field best, labels in the person's language; any other preset by name in “Other”.
3. After the choice: copy `brand.json` to `brand.json.bak`, write the new `tone.preset` and keep `tone.overrides` and every other key. Confirm in one line, for example “Acme: tone changed from expert to friendly; the next videos follow it.” If `tone.overrides`, `motion` or `meme_size` set explicitly in the profile contradict the new tone, name them and offer to clear them (set them to `null`, as in the template), so the tone decides.

Plans of videos already edited stay as they are; a plan that breaks the new ceilings shows errors at its next check. This is not `tone_override`: that one is for a single video and leaves the profile as it is.

## Logos

The file is copied into `assets/`, and its role is written to `logos`. The role is determined from the file:

| Sign | Role |
|---|---|
| light | `on_dark`: for a dark background and over video |
| dark | `on_light` |
| near-square (0.75–1.33), or the word `mark`/`emblem` in the name (or the same word in the brand's language) | `mark_*`: a compact mark for the frame corner |

Where each one comes from in the frame:
- **Frame corner:** `mark_on_dark` → `on_dark`.
- **End card:** `on_dark` → `mark_on_dark`; with a CTA the kit sets the brand line (`tagline`) small under the logo, and a profile without a `tagline` gets the `on_dark_tagline` variant instead.
- **No logo:** the brand name is typeset on the card.
- **Corner mark** (if chosen in the brief): top right, just below the UI zone and left of the buttons column, for the whole video; the kit draws it 112 px at x 828–940, y 236–348, ~90 % opacity, and fades it out while a scene is on. Not top left: hooks, cards and lists are left-aligned from y 250 and would run into it. A brand that wants it elsewhere sets it in its `guide.md`, and the video gets a per-video composition.
- A logo is never stretched, never recolored beyond the variants in the profile, and never placed on a busy background without a backing plate.

A variant you recolored yourself (for example white made from a dark one) goes in only with a note in `unverified` and a question to the brand owner.

## Rules from revisions

A revision that applies to the brand rather than to one video is appended to `rules.md` → “Rules from revisions” with a date (`brand.py rule <slug> "…" [--why "…"] [--scope "…"]`: the reason and which videos it applies to, so a later disliked result can be traced back to it; such a rule is an owner decision in `references/playbook.md`). A revision becomes a brand rule when the person says it is always so, or when it comes up again on the brand's next video. Examples of such revisions: “cards only on the left”, “the mark goes on the card, not in the corner”, “accent only on numbers”. The brand's next video already knows it. Revisions for a single video stay in `edit/<id>/project.md`. If it's unclear what a revision applies to, ask in one line.

Whatever the person says about the brand as a whole goes into the brand folder, not into one video's notes:

| What was said | Where it goes |
|---|---|
| a rule or a ban (“never show money”, “no red”) | `rules.md`, via `brand.py rule` |
| a preferred CTA, an exact CTA text | the brand's `cta.md` (create it and set `brand.json → cta_library` if there is none) |
| a visual decision: palette roles, type, signature elements, motion | `guide.md` (set `brand.json → guide`) |
| a recurring format: a skit, a series template | its own `.md` in the brand folder, linked from `rules.md` |
| something for every video of the project, whatever the brand | `reel-defaults.json` (settings) or the project's `CLAUDE.md` (notes) |

## Styles for any brand

| Style | For the brand |
|---|---|
| **“Marker”** | `{{INK}}` text on a `{{MARKER}}` marker bar (`colors.extra.ink`, alias `on_marker`, on `colors.extra.marker`; without a marker of its own, `text_on_accent` on `accent`), the bar draws in from left to right; the default style for a new brand |
| **“Brand”** | `primary` backings, `accent` highlights, brand fonts |
| **“Minimal” / “Editorial” / “Bold”** | their own fonts and layout; the style's accent color is replaced with the brand's `accent` |
| **“Glass”** | glass `primary` cards, only for skits and only when chosen explicitly |

The list of allowed styles and the default style are set in `styles`, the subtitle mode in `subtitles_default`.

## In Remotion

The profile is copied into the Remotion project: the JSON to `src/brands/<slug>.json`, the logo and LUT files to `public/brands/<slug>/`. In the copied JSON, rewrite those paths relative to Remotion's `public/` folder (`assets/logo-white.png` → `brands/<slug>/logo-white.png`), otherwise `staticFile` won't find them. The video's code takes them from there:
- colors: `brand.colors.*`;
- fonts: a loader by family name (`@remotion/google-fonts/<Family>` with `subsets` for the scripts you need, for example `["latin"]` or `["cyrillic","latin"]`; local files via `FontFace`);
- logos: `staticFile(brand.logos.on_dark)`.

HEX codes and font names are never written into the video's code.

**Styles the kit draws.** `ReelKit` draws “Marker” (`marker`, and its variant `v2`, which sets every line in the body font) and “Brand” (`brand`) itself. `minimal`, `editorial`, `bold` and `glass` are drawn as “Marker” in brand colors with a console warning: for those styles, write a per-video composition that reuses the kit's components (`Phrase`, subtitles, inserts, scenes). The plan check still times scenes by the kit's own animations (the reading-time floor in `references/scenes.md`: the `stat` counter waits 24 frames, lines enter with a stagger), so the composition keeps its entrances at or under those, or the scene's `dur` grows by the difference. Text such a style puts over the video without a plate (white capitals in the headroom, say) needs a darkening measured for its zone: `visual_plan.py shade edit/<id> --scene <id>` (or `--zone x,y,w,h`). A style outside `styles.allowed` is the brand's rule broken: `reelcfg.py save` warns, ask the brand owner and record the choice in `project.md`. `brand.json → looks.<style>` overrides a style's look for this brand: `mark` (the marker color), `on_mark` (text on it), `field` (the field of full-frame scenes in this style, the primary color by default; on a light field the text is the primary color), `heading` and `body` (fonts, in the `fonts` format), for example `"looks": {"marker": {"mark": "#F5FAA4", "on_mark": "#111111"}}`.

**Focus brackets.** In the “Brand” style the kit draws focus brackets only inside `stat`, `word` and `cta` scenes. Brackets that close in on a spoken word over the video are a per-video composition: `ReelKit` plus a component that puts the kit's `Brackets` (`src/kit/scenes/parts.tsx`) around the word's box on its word; record that box in the plan's `keep_clear`.

**Fonts in the kit.** `src/kit/brand.ts` loads Google fonts by family name from its `GOOGLE` map, which knows 14 families: Inter, Manrope, Oswald, Montserrat, Onest, Inter Tight, Playfair Display, Roboto, Rubik, Unbounded, Golos Text, Nunito, Open Sans, PT Sans. An unknown family falls back to Inter with a warning. Another Google family is an import plus one entry in the `GOOGLE` map; `kit.py check` lists that file as changed, and `kit.py update` replaces `src/kit/` (backup in `.kit-backup/`), so add the entry again after an update. The kit requests only the `latin` and `cyrillic` subsets of a Google font: for another script (for example Vietnamese or Greek), add its subset in that loader or use font files. The brand's own font files: `"source": "local"` with `files` (upright faces) and `italic` (italic faces) in `brand.json → fonts`; the weight and style come from the file name (Thin 100 … Black 900; Italic, Oblique or `-It`).

## What else depends on the brand

- **Who approves publishing:** `approver`.
- **Music:** `music_policy`. For a business account, don't burn music in without a commercial license.
- **Brand tone:** `tone`: memes, cutaways, how loud the techniques are, scene tones (section “Brand tone”).
- **Memes:** `memes_policy`. With `strict`, only memes with known rights are used. Meme size is `meme_size` (no larger than the tone's ceiling): for a calm brand, `s`.
- **Icon library verdicts.** A “no” for rights reasons (film stills, celebrities, stock people; `rights_block` in the catalog) always applies. A “no” for style reasons applies only to a brand that adopts the catalog's verdicts: `"asset_verdicts": "verdict"` in its `brand.json` (`references/library.md`).
- **Forbidden imagery:** `forbidden_imagery` / `_en`. It applies to B-roll, code scenes and memes (and to the online sources of the online-sources add-on `it-reelsmaker-online`).
- **Insert defaults:** `inserts`. For example, `{"use_online_footage": false}` (a key of the online-sources add-on `it-reelsmaker-online`) for a brand whose guidelines forbid stock footage.
