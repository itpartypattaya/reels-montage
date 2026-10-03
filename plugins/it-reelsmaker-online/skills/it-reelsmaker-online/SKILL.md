---
name: it-reelsmaker-online
description: >
  Online sources for it-reelsmaker video edits: vertical stock footage (Pixabay, Pexels, Magnific), CC-licensed
  memes (Openverse; GIPHY as reference only), paid AI video generation (Veo, Kling, LTX via fal.ai) for B-roll,
  a more accurate transcript (cloud text on the local word times, OpenAI), subtitle translation through Claude,
  OpenAI or Gemini, and figure cut-outs on your own server over SSH.
  Use only inside an it-reelsmaker edit, when the person enabled online footage, online memes, model generation or
  cloud transcription in the settings or asked for it directly: "find stock footage", "generate an insert", "online
  memes", "transcribe it through OpenAI", "translate the subtitles through Gemini", "cut out the figure on my
  server". Every download
  and every paid run happens only after the person approves the visual plan with source, size and price.
---

# Online sources for it-reelsmaker

An add-on to the `it-reelsmaker` skill. It plugs three online sources into the core's visual plan (step 7a and the core skill's inserts reference): stock footage, online memes and a video model; and a cloud recognizer into the core's step 2 (transcript). It is never used without the core. Everything not described here follows the core's rules: why an insert is needed, the intensity budget, meme size and placement, clip preparation and plan checks.

## Connect it to the project

The core's scripts are the only entry point; they load this add-on as a library. Link it to the editing project once, and again after every add-on update (the plugin folder changes with the version; the core then warns that the add-on is not found):

```bash
cd {{PROJECT_ROOT}}
python "${CLAUDE_SKILL_DIR}/scripts/reels_online.py" link
```

It writes `online_scripts` into the project's `it-reelsmaker.json` (`unlink` removes it). After that the core does the rest: `footage.py search`, `plan-search` and `pick` include the stock providers, `reelcfg.py show` reports what turns on and why not, and the add-on's own commands run through the core runner (`<core scripts>` is the core skill's `scripts/` folder):

| Command | What |
|---|---|
| `python <core scripts>/addon.py memes search "facepalm" [--provider openverse\|giphy]` | online meme candidates |
| `python <core scripts>/addon.py memes fetch openverse:<id> --yes` | download an approved CC image into `memes/online/` with its attribution |
| `python <core scripts>/addon.py gen manifest\|validate edit/<id>` | model prompts (`generated/prompts.md`, `prompts.json`) with the price |
| `python <core scripts>/addon.py gen run edit/<id> --yes` | paid generation, only after the approved price; the clip is picked up by the core's `codescene.py ingest` |
| `python <core scripts>/addon.py matte cut edit/<id> --from … --to … [--host H]` | figure cut-out on your own server (below) |
| `python <core scripts>/addon.py transcribe edit/<id> <source> --provider openai [--language ru] [--yes]` | a more accurate transcript (below); `--price` only names the price |
| `python <core scripts>/addon.py translate edit/<id> --to en --provider anthropic\|openai\|gemini [--yes]` | subtitle translation through an API (below) |

## Reel settings

Online sources are off until turned on for a video (`reelcfg.py save edit/<id> --set use_online_footage=true`) or for the whole project. Keys live in `edit/<id>/reel.json`, with the same layers as the core (defaults → `brand.json → inserts` → `reel.json` → words in the prompt):

```json
{
 "use_online_footage": true,
 "use_online_memes": false,
 "generation_engines": ["code", "model"],
 "generate_now": false,
 "broll_priority": ["project", "local", "online", "generated"],
 "meme_priority": ["local", "online"],
 "online_footage_providers": ["pixabay", "pexels"],
 "online_meme_providers": ["openverse"],
 "generation_provider": "fal",
 "generation_model": "veo3.1-fast",
 "generation_seconds": 6
}
```

| Key | Meaning |
|---|---|
| `use_online_footage` | online stock as a B-roll source |
| `use_online_memes` | online memes — CC with commercial use only |
| `generation_engines` | `code` — code scenes (core), `model` — a video model |
| `generate_now` | whether to start **paid** generation; without it only a ready prompt is written and the insert stays `pending` |
| `online_*_providers`, `generation_*` | providers, model and clip length (`references/sources.md`) |

**Priority.** B-roll: project → library → online stock → generation (code or model) → main footage. Memes: own folder and library → online CC → no meme.

**What actually turns on.** Before the plan, check availability: an enabled source with no key, no network or in offline mode switches itself off, and the reason goes into the report. A source failure (no key, no network, a 400/401/500 response) is a warning, not a crash: the edit always reaches the render with whatever is available.

## Rules

- **Only after a “yes”.** The plan is shown to the person with the list of downloads (source, MB) and paid runs (≈ $). Downloads and generation happen only after the person approves that plan. A first generation run without approval only names the price.
- **Network and keys.** Check offline mode and the key **before every** network action, not only at search time. Keys come from environment variables or from a file outside the project (`references/sources.md`). **Never ask the person to paste a key into the chat, and never run `keys set` yourself:** to add a key, the person runs `python <add-on scripts>/reels_online.py keys set <NAME>` in their own terminal (hidden input; it refuses to run without a terminal); you may run `keys list` (values masked) to see what is set. Mask API keys, authorization headers and `key=`/`token=` in URLs in all output and saved errors; keys are never written to project files or git.
- **Stock.** Download only what was selected. Record attribution in `edit/<id>/inserts/credits.json` and in the post caption. Never present a stock person as “our client or candidate”: stock licenses forbid implied endorsement.
- **Online memes.** Embed only CC0, PDM, CC BY and CC BY-SA, with attribution; check the license on the image's detail page. GIPHY is a reference only (an Instagram sticker or a re-shoot). Film stills, celebrity photos and other people's memes featuring people — never.
- **Generation.** Prompt fields and template, checks, and “money is never spent twice” — `references/generation.md`.
- **AI label.** A photorealistic insert from a model → turn on the “AI info” label when publishing (Meta rules). Stylized code graphics don't need it.
- **Brand restrictions** (`forbidden_imagery`, `forbidden_imagery_en`) apply to stock queries and generation prompts.

## Cloud transcript (core step 2)

The core transcribes on this computer; its word times match the audio, its words are sometimes wrong (a case
ending, a word dropped at a joint between takes, and wrong words become visible in burned-in subtitles). `addon.py
transcribe` keeps the local word times and lays a cloud recognizer's text onto them: the same word gets the cloud's
spelling and punctuation, a different word in its place is replaced (the local one kept in `local`), a word only the
cloud heard gets a time between its neighbours (`est: true`), and words only the local model heard stay: often the
repeat of a retake the cloud tidied away, so the report lists them as places to listen to (core step 3). Read the
report's lines before the cut plan. The local transcript is made first if missing and kept as `<stem>.local.json`.

- **Provider:** `openai`: text `gpt-transcribe` ($0.0045 per minute of audio). OpenAI's text models return no
  word times; its `whisper-1` does, but measured on real footage they were off by more than 0.15 s for one word in
  five, so they are used only without a local model (`--words cloud`, $0.006 per minute). Files up to 25 MB, about
  13 minutes of the core's 16 kHz WAV.
- **Audio:** the core's `edit/<id>/audio16k-<source stem>.wav`, on the video's timeline (never the video file).
  It leaves the computer: say so when offering it.
- **Paid, so only after a “yes”:** name the price (`--price`), run with `--yes`; or the person sets
  `transcription_provider=openai` in the project defaults (`reelcfg.py defaults --set …`) once, which is their
  standing choice for every video.
- **Fallback:** no key, no network, no credits, a refused request → a warning, exit code 2, the local transcript
  stays as it was; the edit goes on with it. Key: `OPENAI_API_KEY`, added by the person with `keys set`.

## Subtitle translation through an API

By default you translate the phrases yourself in the session (core: `subs.py`, free, nothing leaves the computer).
`addon.py translate` is for a translation the person wants from a particular model, or a second opinion: it sends
the phrases (text only) with the brand's `voice` and `forbidden_words`, asks for one translation per phrase within the
characters that can be read while it is on screen, in the speaker's form of address, writes them into the empty
phrases of `subs/<lang>.json` (`--force`: all) and runs the core check (`subs.py apply`). Read the printed pairs: a
model may shorten away meaning. Providers and default models: `anthropic` claude-sonnet-5-5, `openai` gpt-6.1-sol,
`gemini` gemini-3.8-flash (`--model` or the `translation_model` setting for another). A video is a few thousand
tokens, a cent or less; paid all the same: `--yes`, or the person's standing `translation_provider` setting. Keys:
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` (the person adds them with `keys set`). A phrase the model
skipped stays empty: translate it in the session, then `subs.py apply`.

## Figure cut-out on your own server

The core cuts the figure out on this computer (`matte.py`; the cut-out reference of the core skill, `figure.md`). On a weak laptop the same step can run on a server you control: `addon.py matte cut … --host ${user_config.matte_host}` (the add-on setting; if it still reads `${user_config…}`, it is not set: the script then takes `matte.host` from `it-reelsmaker.json` or `REELS_MATTE_HOST`, otherwise ask the person once and write `matte.host` there). Frames of the span go to that host as one JPG archive over your own SSH client, the WebM with alpha comes back, and the temporary files are removed there, on error too. The server needs `rembg` with the `u2net_human_seg` model (its path on the server: `matte.server_rembg`, or `matte.rembg` when you never cut out locally); one cut-out at a time under a server-side lock, with a memory check. Nothing goes anywhere else.

## References

| File | When |
|---|---|
| `references/sources.md` | connecting stock, video models and online memes: terms, prices, endpoints, keys |
| `references/generation.md` | model generation: prompt fields and template, checks, run rules, AI label |

Paid submissions reserve `gen.job` under the plan lock before contacting fal. A `submitting` or `unknown` state never resubmits automatically: check the provider dashboard, then restore the request ID and queue URLs to resume, or clear the job by hand only after confirming that no paid request was accepted. Resumed fal jobs use only `FAL_KEY`; other saved providers are refused. Downloaded raw clips are bound to their request ID, so an older clip cannot satisfy a new job. Requests and redirects require HTTPS; credentials are stripped on an origin change, and fal queue hosts are checked at every hop. JSON responses are limited to 20 MB and downloads use unique temporary files.
