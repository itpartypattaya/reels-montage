# Text in the frame: a phrase is one block, line breaks, subtitles

Supplements section 3 of `SKILL.md` (“the person is the main subject, text is support”). Applies to any text in the frame: hook, card, list, full-screen phrase, end card, subtitles.

## A phrase is one block

A real revision on a hook: “the gap between the lines is too big, it's one phrase, don't split it”. The lead-in hung near the top of the frame (y 250), and the big word sat 300 px lower, behind the head. The eye read two separate messages.

**The eye groups by distance.** Everything that reads in sequence as one thought sits closer together than it sits to neighboring elements. If the gap inside a phrase is the same as or larger than the space around it, the phrase falls apart.

| What | Rule |
|---|---|
| Lines of the same size | line pitch 1.0–1.1× the font size for an all-caps headline, 1.1–1.2× for cards (same-size cards sit flush against each other), 1.2–1.3× for subtitles. The pitch is set with line height, not with margins. The only exception is all caps without a card, trimmed to cap height (so that the gap to the other part is measured by the letters): there the pitch is topped up with a margin |
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

It is handy to keep a “phrase” component in the Remotion template (lines with font sizes → the gap is computed from the font size) and a “glue” function that inserts non-breaking spaces, and to use them for every card. The glue keeps manual line breaks and existing non-breaking spaces, turns “ - ” into an em dash, and glues “60 % growth” the same way as “60% growth”. **Width comes from a real measurement with the font** (`@remotion/layout-utils`, `measureText`): a line that doesn't fit the frame width with margins gets a smaller font size, so a long word or a glued chain never runs off the frame. Measure only after the fonts have loaded.

**Check.** A still frame with the phrase, scaled down to 25 %: the phrase reads as one blob. Two blobs with empty space between them mean the gap is too big.

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
