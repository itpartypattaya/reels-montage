# Examples: a cut plan and a delivery report

Two messages as the person should see them: the cut plan of step 5 and the report of step 10. The data is made up (the brand Acme, the file `IMG_4821.MOV`, a speaker with no name), but the numbers agree with each other. They show the format and the level of detail, not how to edit. Write in the person's language.

## Cut plan (step 5)

> **IMG_4821.MOV → a Reel for Acme.** Source: 72.4 s, 2160×3840 after rotation, 30 fps; the author did not speed it up (7.4 syllables/s).
>
> **Start and ending** (chosen from three variants, step 3a): the slow start is cut, so the video opens on the first strong line, “Most hiring managers test memory, not thinking” (0:03.4), and ends on the call to action with a pull-out. Not chosen: a teaser of “I hired the one who failed the test” (0:41.2–0:43.0, clean edges): it is the payoff of the story and would give it away; proof first (the interview story before the claim): it needs the claim to make sense.
>
> **What stays.** 11 of 15 phrases, in the original order.
>
> **What goes:**
> - 0:00–0:03.2 “So, um, hi everyone”: a slow start before the hook;
> - 0:21.6–0:27.9 the first take of “test how they think”: the speaker stopped and said “let me say that again”, so the second take (0:28.3–0:33.0) stays;
> - 0:46.0–0:49.5 an aside about the weather: off topic;
> - 1:05.2–1:08.0 the call to action said a second time: the first one is cleaner.
>
> **Takes and slips.** At 0:52.1 the word “candidates” lasts 1.4 s with a 0.4 s silence inside: a re-transcribed 5-second segment shows two takes, and the last one stays.
>
> **Pacing:** tight, pauses up to 50 ms. **Filler words:** 6 removed (“um”, “you know”); one “like” at 0:40.2 stays, because there is no silence on either side of it to cut.
>
> **Speed:** ×1.15 with the pitch preserved (an insight monologue). **Final length:** ≈ 41.8 s (48.1 s of kept speech ÷ 1.15).
>
> **Camera:** the 4K source allows a zoom up to ×1.3 with no visible softening. Wide → medium → close-up, a punch-in on “thinking”, a close-up with a slow push-in on the call to action.
>
> **Transcript fixes:** “Akme” → “Acme”, “short list” → “shortlist”.
>
> **Supports** (`references/playbook.md`):
> - Profile: none · format insight (`references/profiles.md`: no profile was asked for, the format guides the length, 30–60 s); one CTA;
> - the slow start cut, the video opens on the claim → `structure.md` › Start: Cut the slow start (external);
> - pauses up to 50 ms, ×1.15 → SKILL.md step 5, an insight monologue (external) + brand `rules.md` 2026-09-12 “tight pace” (owner);
> - a shot change every 1.5–3.5 s, punch-in on the main word → playbook PACE-1 (verified);
> - the teaser not used → `structure.md` › Start: Teaser, “not when the line is the payoff” (external).
> Not applied: a hook headline (HOOK-2) — the opening line is the hook.
>
> Cut it like this? A “yes” starts the cut; anything else, tell me what to change.

## Self-review before the preview (step 9)

Before the person sees a render, review it as a stranger would and fix what you find. The protocol follows the review rules of [HyperFrames](https://github.com/heygen-com/hyperframes) (Apache-2.0), retold for this pipeline.

- **What to look at.** The storyboard sheet and the 12-frame contact sheet, plus two views they miss: every join at ±0.2 s (`kit.py still` on the frames on both sides of a cut and of a scene's entrance and exit), and the whole video scaled to a phone screen 360 px wide (`ffmpeg -i out/<render>.mp4 -vf scale=360:-2 edit/<id>/verify/phone.mp4`): what does not read there will not read on a phone. Where subagents are available, one with no context of the edit watches the same frames and answers two questions: what is this video about, and where did it stop making sense.
- **One line per note:** `time · where · problem → fix`, for example `0:12.4 · hook, line 2 · ends on “to”, the word dangles → glue “to” to the next word`. No “looks good” and no score out of 10: a note without a fix is not finished.
- **Priority.** P0 blocks the preview and always comes with a ready fix: text on a face or in a UI zone, a leftover take, a word cut in half, a fact with no source, a brand ban broken. P1 is fixed when it is cheap: a join that jumps, a hold too short to read, a scene that repeats its neighbor. P2 goes into “open items” of the report.
- **Two rounds at most** of fix → check again. What still fails after the second round goes into the report as “passed with warnings”, with its note lines, instead of a third quiet round.

These notes are the agent's own. The person's revisions still go through the defect table (SKILL.md step 9).

## Delivery report (step 10)

> **Ready: `edit/4821/out/acme-hiring-master.mp4`** (41.8 s, 1080×1920, 30 fps).
>
> **Edit:** 23 segments; 2 retakes and 6 filler words removed; remaining silence between phrases ≤ 48 ms, 0.31 s in total; every segment edge checked by audio, no fragments of neighboring words.
>
> **Sound:** −14.1 LUFS, true peak −1.3 dBFS, the audio is as long as the video; the mastering check succeeded.
>
> **On screen:** subtitles in the accent style; a hook headline (0:00–2.6); a `quote` scene in `overlay` mode (0:15.2–18.8), verbatim from the speech at 0:28.3 of the source; one B-roll shot from the project (the office, 0:31.0–33.2); an end card with the call to action. The face audit shows 0 overlaps.
>
> **Did not land:** a B-roll shot of a team meeting at 0:12: nothing suitable in the project or the library, so the main footage stays.
>
> **Open items:** the number “3×” on the card is the speaker's (0:37.5), no check needed; the master carries the cover as cover art, and `…-cover.jpg` lies next to it for uploading by hand.
>
> **Caption** (`caption.txt`, waits for the approver's “yes”): “Most interviews test what candidates remember. Ours test how they think. Message us ‘SHORTLIST’ to see how it works.”
>
> **Noticed on the way:** the source has a 2-frame black flash at 0:47.2 from the camera; it falls inside the aside that was cut, so it is not in the video.
>
> **Supports:** the `quote` scene in `overlay` → `scenes.md` › Quote (external) + brand `rules.md` 2026-09-20 “quotes only verbatim” (owner); subtitles in the accent style → chosen in step 0; no meme → the brand tone `expert`, confirmed by the brand owner (owner; a tone the plugin set by default, still marked `unconfirmed`, is only external). Departed from PACE-1 at 0:15–18.8: the quote holds 3.6 s for its reading time (`scenes.md`, reading-time floor). Profile: none, so no profile checklist (with one, its items: done in `validate`, confirmed on the draft, skipped by id). Checklist skipped: music (no licensed track chosen).
