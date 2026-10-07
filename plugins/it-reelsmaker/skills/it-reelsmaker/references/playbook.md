# Playbook: craft rules, how far to trust them, and why a video came out as it did

A video is built from two kinds of knowledge, kept apart on purpose:

- **measurement** — speech thresholds, cut edges by the audio, the ffmpeg graph, face zones, −14 LUFS: scripts measure it
  and tests cover it. When it is wrong, it is a bug: fix the script;
- **taste** — the hook, pace, shot sizes, text on screen, structure, inserts: it depends on the video, and guides disagree.
  When the person dislikes a result, the question is which taste rule produced it.

Mixed together, a disliked video cannot be traced to its cause, and the whole video gets redone. Kept apart and labeled,
the rule behind the decision is found and fixed, and the next video already knows it.

Measurement lives in `references/scripts.md`, `faces.md`, `camera.md`, `pitfalls.md` and sections 2 and 12 of SKILL.md.
Taste lives in `structure.md`, `techniques.md`, `typography.md`, `scenes.md`, `inserts.md`, `cta.md`, `skit.md`,
`shooting.md`, the style parts of `brands.md`, and in the person's own files below.

## How far to trust a rule

| Trust | Mark | Where it lives | What it is |
|---|---|---|---|
| **owner** | ⭐ | the brand's `rules.md` (each rule dated, `brand.py rule`), the brand tone once the owner chose or confirmed it, a card marked `owner` in the project playbook, the project's `CLAUDE.md` | a decision of the person or the brand owner, with its date |
| **verified** | 🟢 | a card marked `verified` in the project playbook; in this skill's references, a rule that cites a real case or a test run | checked on edited videos |
| **external** | ⚪ | the rest of the craft guidance in the references; a card marked `external`; files in `refs/`; a default nobody confirmed (a brand tone still marked `unconfirmed` in `brand.json`) | advice from guides, articles, other people's videos, the plugin's defaults |

The plugin's references are replaced on every update: the person's own rules never go there, they go into the project
(below) or the brand folder.

## The project playbook (optional)

`{{PROJECT_ROOT}}/playbook.md`: the person's craft rules for all their videos, as cards. A rule about one brand goes into
that brand's `rules.md` instead (`brand.py rule <slug> "…" --why "…" --scope "…"`).

```markdown
### PACE-1 · The picture changes every 1.5–3.5 s
- Applies to: dynamic reels, talking head. Not for: a calm explainer (one idea per shot, PACE-2).
- Why: viewers get bored when the frame does not change, not because the person stands still.
- Source: verified — two edited talking-head videos (2026-10); external — a breakdown of a creator's reel.
- Trust: verified
```

- The ID is a short topic in capitals plus a number (`HOOK`, `PACE`, `SHOT`, `TEXT`, `SUBS`, `SOUND`, `COLOR`, `END`, or
  the person's own) and never changes, so a plan written months ago still points to the same rule.
- A rule is never deleted. A retired one keeps its ID and gets a line: `Retired 2026-11-02: why`.
- `lessons.md` or a similar file the person already keeps is read the same way; offer to turn its entries into cards once,
  not by default.

## When rules disagree

1. **Scope first.** Two rules usually disagree because they are about different videos (a dynamic reel and an explainer):
   the one whose “applies to” fits this video wins.
2. **Then trust:** owner → verified → external. A brand rule (owner) beats a general one.
3. **Still a tie, or an owner rule against a fresh verified result:** ask the person, with both rules and their sources.
   Their answer becomes an `owner` card (or a brand rule) with the date.

## Supports: each decision with its rule

The cut plan (step 5) and the delivery report (step 10) do not say “I did it this way”; they list the decisions a person
might question (structure, pace, shot sizes, on-screen text, inserts, color, sound) with what supports them:

```text
Supports
- Teaser “Anything but sales” first → structure.md › Start: Teaser (external) + brand rules.md 2026-10-04 (owner)
- A shot change every ~2.5 s → playbook PACE-1 (verified)
- List over the video, speakers unchanged → brand rules.md 2026-10-04 (owner)
- No meme on the punchline → no rule: judgment (the line works on its own)
Not applied: HOOK-2 (a hook headline) — the teaser is the hook; two hooks compete.
Departed from: PACE-1 at 12–16 s — the list holds 3.4 s for its reading time (scenes.md, reading-time floor).
Checklist: skipped “music” (no licensed track chosen).
```

- Cite the file and section (or the card ID) and the trust. A decision with no rule says `no rule: judgment` and why:
  if the person agrees, it may become a card.
- Keep it to the decisions that shape the video, 4–10 lines, not every setting.
- When the person dislikes something, the support line shows which rule to change: change the rule (with its date and
  reason), then the video.

## How the base grows

- **A guide, an article or someone else's video to learn from:** save it as is into `{{PROJECT_ROOT}}/refs/` with its
  source and date. Then go through its rules one by one against the references and the project playbook:
  - it matches a rule → add it as another source of that card;
  - it contradicts one → change nothing on your own: show the person both, with their scopes, and record the choice
    as an `owner` card;
  - it is new → a new card marked `external`.
  Report the result in three lines: matched, in conflict (waiting for the person), new.
- **A correction while editing:** apply it to the video first. It becomes a rule when it comes up again on another video,
  or the person says it is always so (“always”, “never”, “from now on”): about one brand → the brand's `rules.md`;
  about editing in general → an `owner` card.
- **A rule that held on a video the person approved:** an `external` card becomes `verified`, with the video as its source.
