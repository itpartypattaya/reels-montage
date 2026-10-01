# Brands: saved profiles, choosing one before the edit, a new brand from a minimum

The skill edits videos for any brand. Everything that sets brands apart lives in the profile: colors, fonts, logos, LUT, styles, bans, who approves, insert settings. The pipeline (cutting, camera, subtitles, mastering) is the same for every brand.

## Where they live

A brand is a folder `<PROJECT_ROOT>/brands/<slug>/` in the editing project (the template is `assets/brand-template/` in the skill folder):

| What | Why |
|---|---|
| `brand.json` | the machine part: colors by role, fonts, logos, LUT, default style and subtitles, bans, meme policy, meme size, insert defaults, who approves, account type |
| `rules.md` | design rules in words + a log of rules from revisions |
| `assets/` | logos, LUT, font files: the brand is self-contained and moves as one folder |

Profiles live in the project, not in the plugin: a plugin update doesn't touch them, and you can keep the brand folder in your own git. Profiles from the old version (`~/.claude/skills/reels-montage/brands/`, before 1.0) move into `<PROJECT_ROOT>/brands/` as they are.

**The `{{…}}` placeholders in SKILL.md** are fields of the selected brand's profile:

| Placeholder | Profile field |
|---|---|
| `{{BRAND}}`, `{{TONE}}`, `{{TAGLINE}}` | `name`, `voice`, `tagline` |
| `{{DARK}}`, `{{ACCENT}}`, `{{LIGHT}}` | `colors.primary`, `colors.accent`, `colors.light` |
| `{{MUTED}}`, `{{MARKER}}`, `{{INK}}` | `colors.extra.muted`, `colors.extra.marker`, `colors.extra.ink`; if the brand doesn't set marker and ink, `{{MARKER}}` = `colors.accent` and `{{INK}}` = `colors.text_on_accent` |
| `{{FONT_HEADING}}`, `{{FONT_TEXT}}`, `{{FONT_SERIF}}` | `fonts.heading`, `fonts.body`, `fonts.serif` |
| `{{LOGO_DARK_BG}}`, `{{LOGO_LIGHT_BG}}`, `{{LOGO_MARK}}` | `logos.on_dark`, `logos.on_light`, `logos.mark_on_dark` |
| `{{FORBIDDEN_IMAGES}}`, `{{FORBIDDEN_WORDS}}` | `forbidden_imagery` (+ `_en`, for English-language searches and prompts), `forbidden_words` |
| `{{SITE}}`, `{{HANDLE}}`, `{{CODE_WORD}}` | `cta.site`, `cta.handle`, `cta.code_word` |
| `{{APPROVER}}`, `{{ACCOUNT_TYPE}}` | `approver`, `account` |

## Step 0: choose the brand

1. List the saved brands. The most recently used come first (`last_used`).
2. If the brand is clear from the prompt or the folder, don't ask.
3. If it isn't clear, make the first question of the step 0 `AskUserQuestion` offer the 3 most recent brands. A new brand comes in through “Other”: a name and 1–3 colors.
4. Write the brand to `edit/<id>/reel.json` and update `last_used` in the profile.
5. Read the brand's `rules.md` before doing any graphics.

## A new brand from a minimum

Only the name and the colors are required. The agent infers the rest itself and says what it filled in:

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

## Logos

The file is copied into `assets/`, and its role is written to `logos`. The role is determined from the file:

| Sign | Role |
|---|---|
| light | `on_dark`: for a dark background and over video |
| dark | `on_light` |
| near-square (0.75–1.33), or the word `mark`/`emblem` in the name (or the same word in the brand's language) | `mark_*`: a compact mark for the frame corner |

Where each one comes from in the frame:
- **Frame corner:** `mark_on_dark` → `on_dark`.
- **End card:** `on_dark` → `mark_on_dark`.
- **No logo:** the brand name is typeset on the card.

A variant you recolored yourself (for example white made from a dark one) goes in only with a note in `unverified` and a question to the brand owner.

## Rules from revisions

A revision that applies to the brand rather than to one video is appended to `rules.md` → “Rules from revisions” with a date. Examples of such revisions: “cards only on the left”, “the mark goes on the card, not in the corner”, “accent only on numbers”. The brand's next video already knows it. Revisions for a single video stay in `edit/<id>/project.md`. If it's unclear what a revision applies to, ask in one line.

## Styles for any brand

| Style | For the brand |
|---|---|
| **“Marker”** | `{{INK}}` text on a `{{MARKER}}` marker bar (`colors.extra.ink` on `colors.extra.marker`; if the brand doesn't set them, `text_on_accent` on `accent`), the bar draws in from left to right; the default style for a new brand |
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

## What else depends on the brand

- **Who approves publishing:** `approver`.
- **Music:** `music_policy`. For a business account, don't burn music in without a commercial license.
- **Memes:** `memes_policy`. With `strict`, only memes with known rights are used. Meme size is `meme_size`: for a calm brand, `s`.
- **Icon library verdicts.** A “no” for rights reasons (film stills, celebrities, stock people) always applies. A “no” for style reasons applies only to the brand it belongs to.
- **Forbidden imagery:** `forbidden_imagery` / `_en`. It applies to B-roll, code scenes and memes (and to the online sources of the online-sources add-on `it-reelsmaker-online`).
- **Insert defaults:** `inserts`. For example, `{"use_online_footage": false}` (a key of the online-sources add-on `it-reelsmaker-online`) for a brand whose guidelines forbid stock footage.
