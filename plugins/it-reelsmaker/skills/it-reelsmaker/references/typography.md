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

The kit has both, in `src/kit/Phrase.tsx`; use them for every card. **`Phrase`** sets a phrase as one block: you give the lines with their font sizes (`lines={[{ text, size, weight, bg }, …]}`, `align`, `maxWidth`); the gap between parts is computed from the smaller font size, each line is glued and its font size reduced if it doesn't fit `maxWidth`. **`glue()`** inserts non-breaking spaces: a short function word with the next word, a number with its unit or word, before a dash; it keeps manual line breaks and existing non-breaking spaces, turns “ - ” into an em dash, and glues “60 % growth” the same way as “60% growth”. Its list of short words (the `SHORT` and `AFTER` sets) is for Russian: for another language, add that language's prepositions, articles and particles. **Width comes from a real measurement with the font** (`@remotion/layout-utils`, `measureText`): a line that doesn't fit the frame width with margins gets a smaller font size, so a long word or a glued chain never runs off the frame. Measure only after the fonts have loaded.

**Check.** A still frame with the phrase, scaled down to 25 %: the phrase reads as one blob. Two blobs with empty space between them mean the gap is too big.

## Reading-time floor

For the hook, cards, designed scenes and the end card: everything that doesn't run in sync with the speech like a subtitle. Time is counted “settled”: the text is fully on screen and not yet leaving.
- 1–3 words: at least 0.8 s; a phrase: 0.3 s per word, at least 1.2 s; the hook gets the most;
- the floor counts from the moment the whole text is on screen: after its entrance, or from the last word if the text builds up word by word on the speech;
- text the speaker says stays at least 0.3–0.5 s after the last spoken word (a designed scene: its tone's hold, `references/scenes.md`);
- items one by one: no faster than 0.6 s apart;
- fast in, then hold: pace comes from motion and cuts, not from text that leaves before it can be read; if it doesn't fit, cut the text or split it, don't speed it up.

## Style specs (starting values; tune on a live frame)

- **“Marker”**: the marker bar is a line background (`box-decoration-break: clone`), square corners, no shadow. Hook ~92 px bold; card text 54–58 px semibold; labels 26 px all caps, +0.2 em, muted gray. Thesis cards on a light backing at ~94 % opacity, square corners. In a list, the item being spoken sits on the marker bar, the others get a thin dark outline at ~18 % opacity. Subtitles at x 60, ~58 px semibold.
- **“Minimal”**: a dense bold grotesque (for example Manrope 800 or Inter Tight 800–900), 2–3 lines bottom left.
- **“Editorial”**: a serif for the key words (for example Playfair Display or Cormorant Garamond) + one sans (for example Manrope); secondary words in a thin sans or in serif italic.
- **“Bold”**: Inter Tight 900 or Onest 800, capitals; the marker bar has square corners and no shadow.
- **“Typewriter”** subtitles: regular or medium weight; the soft shadow of the original look only on explicit choice. In the kit, readability comes from a soft darkening of the lower part of the frame (`reel.json → subtitles_shade`, 0.15–0.25 to start, 0.4–0.6 over light clothing or a light wall, judged by the lightest still); it sits below the scenes, so cards are not darkened.
- **Fonts:** at most two families per video (“Editorial”: one serif + one sans); no third font. Weights: headings 600, big numbers 800, subtitles 700–800, body text 500, small all-caps labels 600 with +0.2 em.

## Subtitles

**Contrast without an outline.** A soft gradient darkening of the lower third: **15–25 % is only a starting point**. On light clothing, a laptop or a white wall it isn't enough: real videos needed 42 % and 60 % (at 34–48 % on a white T-shirt the text was unreadable); on white walls, use a backing under the subtitles instead of darkening. Tune it on the still frame with the **lightest** background behind the subtitles.

**“Typewriter” splits by phrases, not by a character limit:** the boundary is the end of a sentence or a pause; a phrase of up to ~52 characters stays whole, in 2 lines; a longer one is split at the most noticeable pause nearest the middle; a part doesn't end with a short function word or a number. A 40-character limit left tails: one or two words torn from their phrase, alone on a line.

**When to hide them.** Text in the frame replaces subtitles: a hook with a headline, a list card, a full-screen phrase, the end card. The subtitles are hidden for the element's whole interval plus 0.05 s, with no fade in the middle of a word; during the hidden interval draw nothing, including the tail of the previous group.

**The bottom of the subtitle block stays at y ≤ 1500** (below that is the UI). If two lines don't fit when they start from the top position the chin requires, the group runs **one line at a time**, and the top is not raised; if even one line doesn't fit, the block is raised.

**“Bar” grows word by word:** line positions are computed in advance from the real font width, words not yet spoken are invisible, and lines don't jump.

**Speech recognition in subtitles:**
- re-transcription also confuses short words such as prepositions (Russian example: v kotoroy “in which” vs. k kotoroy “to which”): listen to doubtful ones; if you can't hear it with confidence, put it in “open items” with a timecode;
- check brand terms separately. Russian example: on a sped-up version the recognizer heard “sledov” (“traces”) instead of “lidov” (“leads”);
- restore letters and diacritics that the recognizer drops, everywhere (Russian example: the letter yo in vsyo, yeshchyo, poymyote, which the recognizer writes as ye).

**Color emoji** (especially flags) are not set as characters: Chrome on Windows doesn't draw flags. Use SVG or PNG.
