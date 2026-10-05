# Text in the frame: a phrase is one block, line breaks, subtitles

Supplements section 3 of `SKILL.md` (“the person is the main subject, text is support”). Applies to any text in the frame: hook, card, list, full-screen phrase, end card, subtitles.

## A phrase is one block

A real revision on a hook: “the gap between the lines is too big, it's one phrase, don't split it”. The lead-in hung near the top of the frame (y 250), and the big word sat 300 px lower, behind the head. The eye read two separate messages.

**The eye groups by distance.** Everything that reads in sequence as one thought sits closer together than it sits to neighboring elements. If the gap inside a phrase is the same as or larger than the space around it, the phrase falls apart.

| What | Rule |
|---|---|
| Lines of the same size | line pitch 1.0–1.1× the font size for an all-caps headline, 1.1–1.2× for cards (same-size cards sit flush against each other), 1.2–1.3× for subtitles. The pitch is set with line height, not with margins. The only exception is all caps without a card, trimmed to cap height (so that the gap to the other part is measured by the letters): there (trimmed with `lineHeight` ≈ 0.78) the pitch is topped up with a margin of ~0.27× the font size, that is with a margin |
| Parts of different sizes (lead-in + big word) | the gap between the bottom of the upper part and the top of the letters of the lower part is **15–25 px** and no more than **0.35× the font size of the smaller part**. Measure by visible edges (cards, the tops of capitals, x-height), not by block boxes |
| Font sizes in one phrase | no more than two. In a “lead-in + big word” hook the ratio is 1.6–2.8 (working example: 190 / 72). Emphasis on one word inside a line: ×1.3–1.6 |
| Axis | shared: both parts centered on one axis **or** on one left edge. The smaller part is no more than 15 % wider than the larger one |
| Distance to neighbors | from the phrase to another element (face, card, logo): at least **2× the internal gap** |
| Motion | the parts of one phrase live in one layer and one coordinate system: if the big word “lives” in the camera, so does the lead-in. They may appear word by word, but they share their place from the first frame |
| Zones | one phrase, one frame zone (the “headroom” zone or the “chest” zone, `faces.md`). If it doesn't fit, shorten the text or reduce the font size; don't spread the parts across the top and the bottom |

**Visible edge ≠ line box.** All caps without a card leaves empty space above and below the letters in the line, 0.15–0.25× the font size; trim an all-caps line to cap height (`lineHeight` ≈ 0.78 for Inter, Manrope, Onest). For lowercase, the visible top is the x-height, with ~0.35× the font size of empty space above it: compensate with a negative margin of ~0.2× the font size. Measured on Russian text: without compensation, “12 dney / do rezultata” (“12 days / to the result”) were 38 px apart instead of 15–25; with it, 25. Check with a pixel measurement of a still frame, not by the CSS.

**Inside a line:**
- no justification and no stretched spaces; one regular space;
- tracking for large caps is minus 1–3 % of the font size; small all-caps labels get plus 0.1–0.2 em; no letter-spacing on lowercase;
- a big all-caps word aligned left visually “drifts” right by the letter's side bearing: shift it left by 2–4 % of the font size.

**Line breaks by meaning, not by width:**
- short function words (prepositions, articles, conjunctions, negations) don't hang at the end of a line: glue them to the next word with a non-breaking space; a negation goes with its verb, and particles that lean on the previous word stay with it (Russian example: prepositions and conjunctions such as v, k, s, i, a, no, na, po, iz glue forward, ne “not” glues to its verb, and the particles li, zhe, by glue to the previous word);
- a number is not torn from its unit and its word: “12 days”, “60 %”, “3 questions”;
- a non-breaking space before a dash, and the dash is an em dash (—); quotation marks are the typographic ones for the language (“…” in English, «…» guillemets in Russian); an ellipsis is a single character (…);
- no hyphenated breaks; a line of one short word only if that word is the emphasis;
- split into lines by syntactic units: “Stop guessing / NUMBERS”, not “Stop / guessing NUMBERS”.

The kit has both, in `src/kit/Phrase.tsx`; use them for every card. **`Phrase`** sets a phrase as one block: you give the lines with their font sizes (`lines={[{ text, size, weight, bg }, …]}`, `align`, `maxWidth`); the gap between parts is computed from the smaller font size, each line is glued and its font size reduced if it doesn't fit `maxWidth`. **`glue()`** inserts non-breaking spaces: a short function word with the next word, a number with its unit or word, before a dash; it keeps manual line breaks and existing non-breaking spaces, turns “ - ” into an em dash, and glues “60 % growth” the same way as “60% growth”. Its lists of short words (the `SHORT` and `AFTER` sets) hold Russian and English, and its number words (`NUM_WORDS`) hold both languages in every form (“five years” stays together like “5 years”); for another language, add that language's prepositions, articles and particles. The same rule (`noBreak`) splits the subtitles into chunks and lines, and `subs.py srt` follows it in Python. **The trap:** a glued pair is one token with a non-breaking space inside, so a per-video composition that splits a glued line on a normal space (`text.split(" ")`) to color the accent word or time each word to the speech silently loses that accent and that timing: the word is not found. Split the raw text into words first and glue only what you draw, or split on `/[  ]/`. **Width comes from a real measurement with the font** (`@remotion/layout-utils`, `measureText`): a line that doesn't fit the frame width with margins gets a smaller font size, so a long word or a glued chain never runs off the frame. Measure only after the fonts have loaded.

**Check.** A still frame with the phrase, scaled down to 25 %: the phrase reads as one blob. Two blobs with empty space between them mean the gap is too big.

## Reading-time floor

For the hook, cards, designed scenes and the end card: everything that doesn't run in sync with the speech like a subtitle. Time is counted “settled”: the text is fully on screen and not yet leaving.
- 1–3 words: at least 0.8 s; a phrase: 0.3 s per word, at least 1.2 s; the hook gets the most;
- the floor counts from the moment the whole text is on screen: after its entrance, or from the last word if the text builds up word by word on the speech;
- text the speaker says stays at least 0.3–0.5 s after the last spoken word (a designed scene: its tone's hold, `references/scenes.md`);
- items one by one: no faster than 0.6 s apart;
- fast in, then hold: pace comes from motion and cuts, not from text that leaves before it can be read; if it doesn't fit, cut the text or split it, don't speed it up.

## Style specs (starting values; tune on a live frame)

- **“Marker”**: the marker bar is a line background (`box-decoration-break: clone`), square corners, no shadow. Hook ~92 px bold; card text 54–58 px semibold; labels 26 px all caps, +0.2 em, muted gray. Thesis cards on a light backing at ~94 % opacity, square corners. In a list, the item being spoken sits on the marker bar, the past items stay on light plates, with no outline (the kit's `list` scene, `references/scenes.md`). Subtitles at x 60 in the kit's sizes: “Bar” (plate) 60 px / 700, “Accent” 66 px / 800, “Typewriter” 56 px / 500.
- **“Minimal”**: a dense bold grotesque (for example Manrope 800 or Inter Tight 800–900), 2–3 lines bottom left.
- **“Editorial”**: a serif for the key words (for example Playfair Display or Cormorant Garamond) + one sans (for example Manrope); secondary words in a thin sans or in serif italic.
- **“Bold”**: Inter Tight 900 or Onest 800, capitals; the marker bar has square corners and no shadow.
- **“Typewriter”** subtitles: regular or medium weight (the kit: 500); the soft shadow of the original look only on explicit choice. In the kit, readability comes from a soft darkening of the lower part of the frame, drawn only in this mode (`reel.json → subtitles_shade`, kit default 0.35); measure it with `visual_plan.py shade edit/<id>`: the subtitle band of the rough cut through the camera, the lightest frames, the smallest value that gives the text 4.5:1 (over a white T-shirt a real video needed 0.50). It sits below the scenes, so cards are not darkened, and it is at full strength whenever text is on screen (it fades only inside the windows where the subtitles are hidden). The caret is a thin bar in the style's accent color, not a “|” character (that read as the letter l).
- **Fonts:** at most two families per video (“Editorial”: one serif + one sans); no third font. Weights: headings 600, big numbers 800, subtitles 700–800 (“Typewriter” 500), body text 500, small all-caps labels 600 with +0.2 em.

## Subtitles

**Contrast without an outline.** A soft gradient darkening of the lower third, its strength measured on the **lightest** background behind the subtitles: `visual_plan.py shade edit/<id>` prints the contrast for each value and the reel.json value that reaches 4.5:1. A dark background needs little (0.15–0.25); light clothing, a laptop or a white wall needs more (real videos: 0.42, 0.50, 0.60; at 0.34–0.48 a white T-shirt was unreadable); when even 0.90 doesn't reach 4.5:1 (a white wall), use the plate subtitles or a backing instead of darkening. The kit draws this darkening (`subtitles_shade`) only under “Typewriter” subtitles: “Accent” subtitles on a light background need the “Bar” (plate) mode or a backing instead. Text in another zone (a style whose white text sits in the headroom, a card without a plate): `visual_plan.py shade edit/<id> --scene c01` measures that scene's box over its time, `--zone x,y,w,h [--from S --to S]` any box, as a flat darkening against 3:1 (large text; `--target 4.5` for body-size text). It measures the rough cut: where a B-roll insert replaces it under the text, check the insert's frames on a still.

**“Typewriter” splits by phrases, not by a character limit:** the boundary is the end of a sentence or a pause (0.25 s or more); a phrase of up to ~52 characters stays whole, in 2 lines; a longer one is split at the most noticeable pause or punctuation (a colon before a list, then a comma) nearest the middle; a part doesn't end with a short function word or a number, and no part is a single word when it can be avoided. The kit does this for every mode (“Bar” and “Accent” with their own limits); a line inside a chunk moves a short word down with its neighbor. A block is never more than two lines: a phrase that measures three at the mode's size (a real one: 56 characters at 56 px) is split again by the same rules, and two lines are balanced rather than filled greedily (no single word on the second line); a change of speaker ends a chunk too. A 40-character limit left tails: one or two words torn from their phrase, alone on a line; a greedy 52-character cut split “in different | fields:”.

**When to hide them.** Text in the frame replaces subtitles: a hook with a headline, a list card, a full-screen phrase, the end card. The subtitles are hidden for the element's whole interval plus 0.05 s, with no fade in the middle of a word; during the hidden interval draw nothing, including the tail of the previous group.

**The bottom of the subtitle block stays at y ≤ 1500** (below that is the UI). If two lines don't fit when they start from the top position the chin requires, the group runs **one line at a time**, and the top is not raised; if even one line doesn't fit, the block is raised.

**“Bar” grows word by word:** line positions are computed in advance from the real font width, words not yet spoken are invisible, and lines don't jump.

**Speech recognition in subtitles:**
- re-transcription also confuses short words such as prepositions (Russian example: v kotoroy “in which” vs. k kotoroy “to which”): listen to doubtful ones; if you can't hear it with confidence, put it in “open items” with a timecode;
- check brand terms separately. Russian example: on a sped-up version the recognizer heard “sledov” (“traces”) instead of “lidov” (“leads”);
- restore letters and diacritics that the recognizer drops, everywhere (Russian example: the letter yo in vsyo, yeshchyo, poymyote, which the recognizer writes as ye).

**Subtitles in another language** (`subs.py`): the translation goes phrase for phrase, so each translated phrase keeps the time of the spoken one and the kit's modes work unchanged; inside the phrase the words are spread by length, so a translated word does not land exactly on its spoken one (the languages differ; “Bar” and “Accent” still read naturally, “Typewriter” best). Reading speed: up to 17 characters per second is comfortable, above 25 nobody reads it; a fast speaker is fast in the original too (a real video ran at 20–33 characters per second in its own language), so the check compares the translation with the original subtitle and asks to shorten only what reads harder than it. Check that the font covers the new script (Cyrillic, Greek, Vietnamese diacritics; Thai, Arabic, Hindi and CJK need another font family). Chinese, Japanese, Thai, Lao, Khmer and Burmese put no spaces between words: the translation marks the boundaries with `|` (`我们|今天|聊聊`), the words come up one by one without spaces, and `apply` refuses an unmarked phrase, which would come up all at once. The translated subtitles go to the template separately (`subtitleCaptions`): designed scenes keep timing on the spoken words. Because a translated phrase is spread over its time by length, a scene that covers most of it would leave a random tail after it; the kit hides such a phrase whole (more than half of it under the scene). Scene texts are written in the subtitle language too (a quote from the speech is then checked against the translation), or kept in the speech language with the reason in the plan.

**Color emoji** (especially flags) are not set as characters: Chrome on Windows doesn't draw flags. Use SVG or PNG.
