# Structure: how the video starts, holds and ends

Step 3a of SKILL.md. The cut plan used to offer only “which phrases stay, in what order”. The order is a choice in
itself: the same 35 seconds work very differently with the strongest line first or in its place. This file is the
menu of structure mechanics; `structure.py suggest edit/<id>` finds the candidates in the transcript and the audio,
and the agent offers **2–3 variants** to the person before the cut plan. Nothing here is a default except the
original order: a mechanic goes in only when the person picks it.

## How to offer it

1. Name the format of the video in one line (insight, case study, skit, intro, interview…; section 5 of SKILL.md):
   the hook mechanics depend on it.
2. Run `structure.py suggest edit/<id>` (`--from/--to` in source seconds when the video takes one fragment of a long
   recording; with two cameras `--source KEY` per camera, or the main angle: the script lists the sources instead of
   guessing): the phrases with their signs (question, answer, repeat for emphasis, exclamation, number, beat after),
   whether each can be cut out cleanly (≥ 0.1 s of silence at both edges by the audio level; the range runs from the
   line's first word to its last, a pause inside the line is not an edge; where two phrases' word times touch, as
   faster-whisper often writes them, the edge is the audio's silence nearest to that boundary), teaser candidates with
   the exact `ranges` entry, the slow start (looked for in the first third of the speech only; a number in the opening
   seconds, a price or a result, is a strong opening already), the ending, and **earlier edits of the same source**: a
   folder whose `cut.json` or `transcripts/` has the file, or whose notes name the file itself (`sunrise.mp4`, a camera
   name like `IMG_1234`), not a word it shares with a brand (read their notes first: what was chosen then, what the
   person changed).
3. Read the transcript yourself: the script sees signs, not meaning. What is funny, controversial, surprising or the
   payoff is your call.
4. Build 2–3 variants; each is “start → middle → end”, the final length, why it works for this video, and the risk.
   For a skit or a dialogue, a teaser variant is always among them. The first option is the recommendation.
5. One `AskUserQuestion` with the variants; put the order of lines with timecodes in each option's `preview`, so the
   person sees the shape, not only a name. The answer goes into the cut plan (step 5) as “Start and ending”.

## Start

| Mechanic | What | When it works | When not | Risk |
|---|---|---|---|---|
| **In order** | the video starts where the speech starts | the first line is already a hook (a question, a claim, a number) | a greeting, “so, hi”, a warm-up | a slow first second loses the viewer |
| **Cut the slow start** | start at the first question or strong line (`slow start` in the report) | ≥ 3 s of greeting or warm-up before it | the warm-up holds a name or context the rest needs | the viewer misses who is speaking: a role tag or the hook card can carry it |
| **Teaser (cold open)** | a strong line from later plays first (1–4 s), then the video from its start; the line is heard again in its place | skits, dialogues, interviews, reactions: the line raises a question the video answers | the line is the payoff of the ending; it needs context to make sense | the teaser gives away the punchline (the report marks a late line); a teaser longer than ~4 s is a second intro |
| **Proof first** | a story, a case or a number moves before the claim it proves | the story is short and surprising on its own | the story only makes sense after the claim (the usual case) | the logic breaks: say what is lost in the plan |
| **Question loop** | open with a question the video answers at the end | insights, how-tos | there is no clear answer in the speech | the answer must actually come; no clickbait |
| **Detail first** | the first 1–1.5 s is a detail shot (hands, the object, a screen) under the first line | B-roll or a cutaway from the same footage (`extract` in `cut.json`, with a `"what"` that describes it: `footage.py plan-search` finds it as project footage, `pick` takes it in the cut's color as it is) exists | nothing on screen raises a question | a stock-looking detail is worse than the face |

A teaser in the edit:
- `cut.json`: the teaser is the first range, cut from the source by the edges the script gave (never by the transcript);
  the same source seconds appear again later in their place. `cut.py` treats the repeat as a new occurrence.
- `camera.json`: a shot on a repeated source second names its occurrence with `"seg"` (the index of the range).
- Visual plan: anchor graphics to the occurrence you mean (`word:<word>#2` for the line in its place). Keep the teaser
  clean, with no meme and no headline: the line is the hook. A hook headline over the next lines is a second hook; offer
  one or the other.
- Subtitles show the line both times: that is right, the viewer hears it twice.

## Middle

| Mechanic | What | When |
|---|---|---|
| **Beat before the payoff** | keep 0.2–0.5 s of silence before the punchline or the key answer, even with tight pacing | comedy, a reveal, an answer after a question; state it as a number in the plan |
| **Re-hook** | at ~40–50 % of the length, a line or a card that restarts interest (“and here is the strange part”) | videos over ~35 s; only with a line that really is there |
| **Reaction** | the listener's face on the other's line: a medium shot shifted toward the listener (a skit: never a close-up on one, `skit.md`) | dialogues; the reaction is visible in the frame |
| **Punch-in on the main line** | a fast push-in on the key line | 1–3 times per video, within the brand tone |
| **Pictures on the beats** | the picture changes every 1.5–3.5 s (shot size, card, insert) | always: a shot held 4 s or more reads as stuck |

## Ending

| Mechanic | What | When |
|---|---|---|
| **Payoff with a hold** | end on the punchline or the answer, hold the reaction (a smile, a look) 0.4–1 s, no card | entertainment, skits; a logo can sit small over the last 1.5 s |
| **CTA** | a card or a `cta` scene with one call to action | the video has a clear next step (`cta.md`) |
| **Logo sting** | 2–3 s of the logo with the brand line, no CTA | the CTA is spoken, the brand should stay in memory |
| **Pull-out** | the camera pulls out to the wide shot on the last line | the final thought, the situation as a whole |
| **Callback** | the last line or the CTA returns to the hook (the same object, word or situation) | a hook in the scene itself (`shooting.md`) |
| **Loop** | the last line runs into the first, so a replay feels seamless | short videos (< 20 s) where the first and last lines connect; check the join by ear |
| **Question to the viewer** | the speaker asks the viewer (“and you?”) before the CTA | insights and opinions that invite comments |

Hold the reaction after the last word rather than cutting on it: a cut on the final syllable sounds clipped.

## A 20–30 s video in beats (a guide, not a template)

| Seconds | Picture | What is heard | Text | Sound |
|---|---|---|---|---|
| 0–1.5 | detail, or medium with a slow push-in, or the teaser | the hook | subtitles or a hook card | a soft hit, or nothing |
| 1.5–4 | wide | the context: what this is about | subtitles | — |
| 4–5 | punch-in | main point 1 | an accent word | whoosh |
| 5–8 | medium | the point unfolds | subtitles | — |
| 8–11 | detail or close-up | the words it illustrates, a short reaction | subtitles | soft hit |
| 11–15 | wide or medium | main point 2 | 1–2 accent words | pop |
| 15–19 | close-up with a slow push-in | CTA or the payoff | the CTA word in color | music ducked under the key line |
| 19–23 | pull-out to wide | the conclusion | subtitles | — |

About ten picture changes in 20–25 s. With a burned-in licensed track, duck the music under the key line or the CTA
(the line in silence is heard) and bring it back after: `master_audio.py --duck`; the track's drop (its loud moment)
is placed separately, on the final phrase (`references/library.md`).

## Skit: the hook is the mechanics

The first frame shows who is who and what is at stake (role tags, the scale if the video is about an assessment), and
the first line heard is the most controversial one: with a teaser, that line from later. When the video is a verdict,
the scale on screen from the start turns it into a game: the viewer guesses the verdict and stays to check (`skit.md`).
