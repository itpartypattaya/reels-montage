# A long recording → a series of clips

A podcast, webinar, interview or talk of 10–90 minutes, usually horizontal, turned into a series of vertical clips of 15–60 s. The script is `scripts/longform.py`; each clip ends up as an ordinary video folder `edit/<series>-<id>/`, finished by the usual steps of SKILL.md.

**What it is not:** no virality score (nothing shows such a score predicts views; low-scored clips of the services that use one often do better than their "winners"), no fixed number of clips, no clip the person has not approved on the list. Clips are chosen by meaning, from the transcript, and checked by the script where something can be measured.

## Why automatic clips go to the bin, and what this process does instead

The services that cut long videos into clips throw away 20–40 % of what they make (vendor tests; no independent measurement). The reasons named in reviews, and the answer here:

| Why a clip is useless | Here |
|---|---|
| a fixed number of clips per upload: a talk has 5–8 truly standalone moments, the rest is filler | no quota: as many cards as pass the checks, plus a reserve |
| a window of fixed length: the clip starts mid-argument and stops before the payoff | a piece is named by its first and last **words**; the script warns when it starts or ends mid-sentence |
| the moment needs what was said before ("as I said", "that's why", an answer without its question) | the script warns about back-references in the first words; the card says why it stands alone |
| only one continuous stretch: the best clip is often a setup at 03:07 and its payoff at 19:58, without the host's "wow" in between | a card joins 2–4 pieces; the host's lines are cut or kept on purpose (`host`) |
| the tool does not know the brand: politics, a former employer's name, a private topic | `excluded` stretches are errors; private topics are marked as risks for the person's consent |
| the wrong speaker in the frame, wrong subtitles, a cut inside a word | the speaker of each piece is checked; edges are set by audio later (`speech_mask.py`) |
| a bad clip is seen only after the render | the person approves a list of cards before anything is cut or rendered |

## The process

**L0. The brief of the series** (one `AskUserQuestion`, `standard`): the goal (what the series is for and for whom), the rubrics (2–3 kinds of clips, each may get its own caps label in the framed format), the brand, what to exclude (topics, names, stretches), who is the main speaker. Then the series preset: if one exists, `reelcfg.py preset use` is done per clip by `extract`; otherwise finish the first clip, save it with `reelcfg.py preset save <name> --from edit/<series>-<id>` and set `"preset"` in `longform.json`.

**L1. The recording.** `longform.py init edit/<series> <file> [--preset <name>]` measures it and writes `edit/<series>/longform.json`. Then the transcript, one of:
- `transcribe.py edit/<series> <file>`: word by word, locally, the default (`medium`; ~1.6× the recording's length on a laptop: 36 min → ~1 h, 90 min → ~2.3 h; run it in the background, it is cached). The clips then need no Whisper at all: their transcripts are cut out of this one;
- `longform.py import edit/<series> <file>`: subtitles or a transcript the person already has (`.srt`, `.vtt`, JSON segments `{start, end, text, speaker}`, or a word-level JSON). No waiting; times ±1–2 s, which is enough to choose; each clip's pieces are then transcribed on their own (`extract`). Rolling auto-captions (each cue repeats the previous line) are folded; `[Music]`-style tags are kept as marks; `Name:` prefixes become speakers.

A word-level transcript from a cloud recognizer is good enough to choose clips, but its word times drift around laughter, applause and long pauses (a 34-minute talk: ±0.3–1.5 s). In the clip that shows up as words missing from the subtitles or lit too early, and a phrase said twice with laughter in between can come back as one, which `structure.py` then cannot flag as a retake. On each clip, listen at the laughs and seams, and give the words there their real times in `cut.json → retime` (measured on the waveform; `cut.py` names the words it left out at the edges).

**L2. Reading.** `longform.py outline edit/<series>` writes the transcript as short lines into `edit/<series>/outline/part-NN.md`, 10 minutes per part (~4–6 k tokens each), and prints the index. Read **every** part; note candidates per part (time, the idea, the first and last words); then choose across the parts. Marks: `‖` a pause of 2 s or more before the line (a possible seam between topics), `?` a question, `→` its answer, `#` a number, `♪` music under the line.

**L3. The cards** in `edit/<series>/clips.json` (format below). What makes a candidate:
- **one idea that stands alone**: a viewer who saw nothing before understands it; a story with its setup, turn and payoff; a claim with its reason or proof;
- **a first line that works as the hook** (a strong claim, a number, a question the clip answers), or a teaser from later in the same clip (SKILL.md step 3a);
- **an ending**: the payoff with a hold, the conclusion, a punchline; never a trailing "and…";
- **length by format**: an insight 20–45 s, a story 30–60 s (`length` in clips.json);
- **variety**: no two cards on the same point; spread over the recording;
- **facts and names**: a number or a claim on screen only as the speaker said it; private topics (income, family, health, a client's name, a promise to clients) go into `risks` for the person's consent;
- **the host**: a question as the hook is fine; their "wow" between two pieces is cut (`host: cut`), unless it is the rhythm of the clip (`host: keep`).
Ranking is in words, not numbers: `wave` 1 (publish first), 2, 3, and `status: reserve` for the doubtful.

**L4. Check and the list.** `longform.py check edit/<series>` finds each piece in the transcript and checks it (below); fix the errors, look at the warnings. `longform.py sheet edit/<series>` writes `edit/<series>/series.md`: the table and every card with its pieces, hook, ending, risks and findings, and above them the blockers (rights to someone else's recording, consent of the people on screen, music under the speech). **One stop: the person answers on the list by number** ("1–6 and 9; 7 in reserve; 3 shorter"); `longform.py mark edit/<series> <ids> --as approved` (also `reserve`, `rejected`). A card whose pieces move later (a new transcript) loses the approval at the next check.

**L5. Extract.** `longform.py extract edit/<series> <id>` for an approved, checked card: each piece with ±3 s of room as its own file in `edit/<series>-<id>/src/` (re-encoded, frame-exact), its 16 kHz WAV (the same file `transcribe.py audio` makes), its transcript (cut out of the whole one and moved to the piece's own timeline, or Whisper on the piece when there is no word-level transcript of the recording), `cut.json` with a source per piece and rough ranges from the words, `reel.json` from the series preset plus the card's `settings` and the rubric's label (`format=framed` for a horizontal recording unless the preset says otherwise), and `project.md` with the card. Run again: unchanged inputs do nothing and keep your `cut.json`; a changed card, transcript or `--pad` re-cuts the pieces, and then `cut.json` is written anew from their words (its ranges, `fix_at` and `retime` were seconds of the old files; the old one stays as `cut.prev-<time>.json`, speed, look and `fix` are carried over) and `status` shows the rough cut and everything after it as stale; `reel.json` is never overwritten.

**L6. Each clip — in a fresh context.** A series in one long session costs most of its tokens in re-reading the context (a measured series: ~10 M cached tokens per clip, ~300 k context per call). Finish each clip in a new session or a subagent that starts from `edit/<series>-<id>/project.md` and the series preset, one clip after another (one render at a time on 8 GB): `speech_mask.py` on each piece for the real edges (`cut.json` → `ranges`, with `"source"` per range and per `fix_at` / `retime` entry), then SKILL.md from step 5 (cut plan, `cut.py`, `faces.py`, camera, export, `check.py`, `kit.py render`, cover, master). `workflow=quick` fits a series once its preset is set. `longform.py status edit/<series>` shows every card's stage (`ok`, `stale`: a later step is older than the one before it), the seconds of the recording already used and the disk.

## clips.json

```json
{
 "goal": "expert advice for employers + the founder's story",
 "length": [15, 60],
 "blockers": ["rights: the recording belongs to the host's channel", "consent of both people on screen"],
 "rubrics": {"insight": {"label": "INSIGHT"}, "story": {"label": "STORY", "content_format": "story"}},
 "excluded": [{"start": "03:51", "end": "04:27", "why": "politics"}],
 "clips": [
  {"id": "01", "title": "The deal that almost fell through", "rubric": "story", "wave": 1, "status": "proposed",
   "parts": [{"from_words": "So the client called me on a Friday", "to_words": "and I said give me one week", "near": "03:07"},
             {"from_words": "And that week changed everything", "to_words": "we still work together", "near": "19:58"}],
   "hook": "The client gave me one week", "why": "a story with its payoff 17 minutes later",
   "ending": "the payoff line, then a hold on the face", "speaker": "Anna", "host": "cut",
   "risks": ["a private topic: confirm with the speaker"], "allow": [], "settings": {}}
 ]
}
```

- `parts`: in the order of the clip (a teaser may come first). By words: `from_words` and `to_words` (5–10 words each, as said; the script matches them with tolerance for word forms and recognition slips, and when the very first or last words were heard differently, a name in another script for example, the edge still takes up to three of them in) and `near` (where to look, ±20 s; `near_end` for a long piece). By seconds: `start` and `end` (a timecode the person gave; snapped to the words inside). Times are seconds or `mm:ss.s`.
- `speaker`: who carries the clip, as the transcript labels people (a name from the subtitles, `S1`), or a plain word when it has no labels; `host`: what to do with the other voice inside the pieces, `cut` (their short interjections go at the cut) or `keep` (a question that is the hook, a dialogue).
- `allow`: warnings meant on purpose: `overlap:06` (shares more than 3 s with card 06), `dup:06` (says much the same).
- `settings`: extra `reel.json` keys for this clip only (`label`, `profile`, `style`, …); the rubric's `label`, `profile` and `content_format` apply to all its cards.
- The script adds `resolved` to each piece and `check` to each card; the agent does not write them.

## What check reports

**Errors** (exit code 1; a card with errors cannot be approved or extracted): a piece not found; found twice in the window (a retake, a refrain: more words or a closer `near`); end before start; outside the recording; inside an `excluded` stretch.

**Warnings** (with the words and seconds as evidence; the person decides on the list): starts or ends mid-sentence (only when the transcript has punctuation: plain auto-captions have none, and the check says so); the first words point back; the clip's speech is outside `length`; a piece shorter than 1.5 s; shares more than 3 s with another card; says much the same as another card (half of its longer words); the speaker changes inside a piece; seconds snapped more than 1 s.

## The camera of a framed clip

`longform.py camera edit/<series>-<id>` proposes `camera.json` once `cut.py` and `faces.py scan` have run (it reads `captions.json` and `faces.json`, and refuses a `faces.json` older than `final.mp4`). It is the hand-made camera of a measured 12-clip series turned into rules:
- **people**: the faces of each piece grouped left to right by their position (a group seen for less than a second in all and under 5 % of the faces is a false face, anyone seen longer is a person); **who sits where** is not measured (there is no active-speaker detection), so the first clip asks once: `--side guest=left,host=right` (labels as in the subtitles' speakers, or the card's `speaker`); `--write` keeps it in `longform.json` for every later clip. One person in the frame needs no answer;
- **when the shot changes**: on a join of the pieces (always, a change of piece too), on a speaker change when the new voice talks 1.5 s or more from its first word (a host's short "wow" is heard over the current shot and never decides whom a shot frames), otherwise on the best pause of 0.1 s or more 1.5–3.5 s into the shot, a sentence end over a comma and a long pause over a short one; a stretch with no such pause is held longer and reported (natural pacing for it, or a shot by hand);
- **shot sizes**: wide → medium → close → medium (SKILL.md section 9); the close-up centers the speaker's face slightly above the frame's center, the wide shot holds both faces when the window already shows both (it does not pan to a host sitting past its edge), else it leans from the speaker toward the middle of the picture; push-ins within the window's zoom margin (1080 rows: close ×1.13, medium ×1.08; 720 rows and below: ×1.06), a slow push-in on the first and last shots and on the wide ones, never past the margin;
- **every shot names its piece** (`"source"`) when the clip has several: their seconds overlap, and the export cannot tell them apart otherwise; `"seg"` when a second of one piece plays twice;
- it **prints** the shots (time, piece second, size, zoom, frame point, who, why); `--write` writes them with a stamp, and a later `--write` replaces only a file nobody touched: a `camera.json` written or edited by hand stays. Then `visual_plan.py export` and `check.py` (`board.py --shots`: a frame per shot) as usual.

Against the hand-made camera of the measured series (12 clips, 15–44 s, the side taken from the hand-made close-ups): the frame points per shot size a median 22 px apart across and 2 px up and down, at most ~100 px (a medium the hand-made camera kept centered); 127 shots against 100, since the hand-made one mostly alternated wide and close on the joins. Without a pause of 0.1 s in reach a shot holds up to 5–7 s (tight pacing; the hand-made camera held such stretches 6–10 s): the output names them.

## Cost of one recording

Measured on a 36-minute two-person interview:
- 12 clips finished one by one in one session, before this process: the list of 15 cards ~5 M cached tokens and ~40 k output; finishing ~10 M cached tokens and ~30 min per clip;
- this process, choosing in a fresh context from imported subtitles: 4 outline parts (~18 k tokens of text), 22 cards (17 + 5 in reserve) in ~13 min and ~210 k tokens; 11 of the 15 clips the person had approved by hand came back with at least half of their seconds;
- `extract` of a card with two pieces: ~2 min with Whisper on the pieces (no word-level transcript), ~30 s per piece cut out of a word-level one, ~1 s when nothing changed;
- local Whisper `medium` on a busy laptop: 2.3× the audio's length (1.6× when it runs alone);
- a 40 s clip in the framed format: the checks before the render 32 s, the render 3.9 min with `--concurrency 2`.

With a fresh context per clip and the series preset, the aim is ≤ 15–18 min and ≤ 4 M per clip: a 60-minute recording → 10 clips in ~3.5–4 h plus the transcript in the background. The transcript of the whole recording is CPU time, not the person's: run it first, read the subtitles meanwhile if there are any.

## Machine limits and pitfalls

- **Never run per-clip tools on the whole recording.** `faces.py` writes every frame as an image before measuring (gigabytes for 90 minutes): that is why each clip gets its pieces as files. `speech_mask.py` and `structure.py suggest` read a long WAV whole unless they get `--from`/`--to`: with them they read only that stretch (plus 1 s and 5 s of room), so a look at one moment of the recording's own WAV costs seconds, not minutes.
- **Renders one at a time**, `--concurrency 1–2` on 8 GB (`kit.py render`). Remotion copies its project's `public/` on every run; `kit.py render`, `board.py`, `textcheck.py` and `patch_render.py` give each run a `public/` of only that clip's files and remove the run's temp folder afterwards; `kit.py clean-temp` lists what other runs left.
- **Music under the speech** (a podcast intro, a background track): the speech detector and the denoiser mistake it for speech or noise; fewer cuts, `speech_mask.py --density natural`, `master_audio.py --no-denoise`, and the track's rights are one more blocker.
- **The host over the guest**: a line said over the other voice cannot be cut cleanly; keep it or end the piece earlier.
- **Speaker labels** from an imported diarization are ±1 s at the turns and can swap on one microphone; the speaker check is a hint, the picture decides.
- **Someone else's recording**: editing is fine, publishing waits for the rights and the consent of the people on screen (SKILL.md, section 1).
