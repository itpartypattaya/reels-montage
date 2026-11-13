# A narration in a cloned voice (ElevenLabs)

`addon.py voice` (script `voice_online.py`). The rules for the person are in the skill; this is how it works.

## Files

| File | What |
|---|---|
| `~/.config/it-reelsmaker/voices.json` | voices by local name: `voice_id`, `owner: "self"`, `consent` {kind, version, text, purpose, at}, `created_by_addon`, `verification` (`ok` / `required`). Next to the keys file, readable by its owner only; never in a project, brand or git |
| `edit/<id>/voice_script.json` | `{voice, language, blocks: [{id, text, pause_after?}], model?, settings?, output_format?, normalization?, context?}` |
| `edit/<id>/voice_gen.json` | `plan` (id, credits per block), `attempts` by request fingerprint, `cleared`, `build` (trims, offsets, pauses) |
| `edit/<id>/generated/voice/` | every paid answer kept whole (`<fp>-<run>.response.json`: headers + body), each block's 48 kHz WAV and its words |
| `edit/<id>/generated/narration.wav` | the joined narration (48 kHz mono); not `voice.wav`, which is the core's output |
| `edit/<id>/transcripts/narration.json` | its words in the core's transcript format, `model: "elevenlabs:<model>:alignment"` |
| `edit/<id>/transcripts/narration.check.json` | `voice check`: a separate recognition, never the main transcript |

## The request and the “yes”

A block's request is the voice, the model, the output format, the text normalization, the voice settings, the text and
the neighbouring blocks' text (`previous_text` / `next_text`, for intonation; `"context": false` turns it off). Its
fingerprint is a hash of exactly what is sent. `voice plan` lists the blocks with no answer yet, their ceiling in
credits (characters × the model's rate) and a plan id over those fingerprints; `voice run --yes --plan <id>` refuses if
the current plan differs, and checks the block again under the lock right before sending it. So the “yes” never covers
a changed text, voice, setting or neighbour. Pauses (`pause_after`) are not part of the request: `voice build` joins
the blocks again for free.

Before each block the balance (`GET /v1/user/subscription`, `character_limit − character_count`) must cover its
ceiling: without the key's User read permission the run stops before sending. The balance check and the request of a
block are one step for the whole account, under a lock next to the keys file (`elevenlabs-spend.lock`): a second run,
of any reel, waits up to 4 minutes and then stops before sending, so two runs never spend the same credits. The answer's `character-cost` header is
compared with the ceiling; more → the run stops and says so. The live charge was about 0.4 credit per character
(2026-11-13); `plan` shows it as the likely price next to the ceiling. The balance shows a charge minutes later, so a
run also subtracts its own charges from the balance it read first.

## States of a request

`submitting` (reserved under the lock before sending) → `received` (the whole answer is on disk, written atomically,
with `request-id` and `character-cost`) → `saved` (audio decoded, words taken out) → `done` (in the built narration).

- A failure after the request left this computer (timeout, broken connection, an HTTP error not confirmed as free, an
  answer that cannot be saved or is not whole) → `unknown`, never sent again by itself. Only statuses confirmed live as
  not charged release the block (`NOT_CHARGED`: 401 and 404, see `sources.md`).
- A run stopped after the answer was written but before its state: the next run finds the `submitting` reservation with
  its answer file and takes it up without paying again.
- `voice recover edit/<id> <block> --history <item id>`: the audio and the timings of one history item that matches the
  block's text, voice, model and output format (and its request id when known); an item that does not match leaves
  the block `unknown`. The history's audio costs nothing and its item keeps `alignments` (checked 2026-11-13), so the
  block is taken out like a fresh answer. An item without timings: they come from recognizing that audio locally (the
  core's transcribe), the script's words laid onto them (`timing: asr`).
- `voice clear edit/<id> <block> --not-charged`: only after the person found no accepted request in the history; the
  block can then be planned and paid again. A `submitting` reservation younger than 15 minutes is refused: its request
  may still be on its way.

## Words and joining

Each alignment keeps its own characters and times (`alignment` for the text as sent, `normalized_alignment` for what
was read); they are never mixed by index. Words are the script's whitespace runs; a word's time is from its first to its
last letter, digit or spoken sign such as % (quotes and full stops have no sound); a lone dash joins the previous word. Where the read text
differs from the script, the stretch is matched explicitly: the same number of words one to one; one number, sign or
abbreviation takes the time of the words it was read as; several such words read as a different number of words
(“25 kg”) are an error, since which word is which would be a guess: write numbers and units in words; a word spoken but
not in the script is an error too. Then every word must
have a finite time inside the block's audio, in order.

The live alignment starts the first character at 0.0 s over the silence before the voice: the first word starts where
its sound rises over a tenth of the block's peak. Output `mp3_44100_128` (default) or `pcm_24000`; both decode to
exactly the alignment's length. Each block is decoded to 48 kHz mono PCM, trimmed to 0.05 s before its first word and 0.25 s after its last, faded for
5 ms at the cuts, and followed by a pause (0.45 s after a sentence end, 0.25 s otherwise, `pause_after` up to 1 s).
Blocks join by sample counts; the trims, offsets and pauses are recorded in `build`, and the word times shift by exactly
those. Loudness is not touched: the core levels and masters it.

## The contract with the core

`build` writes `reel.json → voice: off_camera` and in `cut.json` the source `narration` (`generated/narration.wav`,
its transcript, speed 1) with one range over its whole length. If `cut.json` already has ranges of other sources, the
narration's range is not added (the message says what to add). Then the core's own path: picture blocks or
`cut.py` → `voice.wav`, then `visual_plan.py init edit/<id> --scenes-voice` for scenes over it.
