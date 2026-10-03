# External sources: stock footage, video generation, memes — terms, prices, keys

Research as of 2026-10-01, based on the services' documentation. Prices and terms change month to month, so before the first paid run open the model's or plan's page.

**All external services are optional dependencies.** The skill works without them: footage comes from the project and the asset library, generation is done with code, memes come from your own folder and the asset library.

## Keys

Keys are read from environment variables or from a file outside the skill and outside the project, for example `~/.config/it-reelsmaker/keys.env` with `NAME=value` lines. The person adds a key in their own terminal: `reels_online.py keys set <NAME>` (hidden input, the file readable by its owner only); `keys list` shows what is set with values masked, `keys remove <NAME>` deletes one. Keys are never printed and never go into the repository.

| Variable | Service | Used for |
|---|---|---|
| `PIXABAY_API_KEY` | Pixabay | default online stock |
| `PEXELS_API_KEY` | Pexels | second stock |
| `MAGNIFIC_API_KEY` (or `FREEPIK_API_KEY`) | Magnific (formerly Freepik, + Videvo) | paid stock with a 9:16 filter |
| `FAL_KEY` | fal.ai | model generation: Veo / Kling / LTX |
| `GIPHY_API_KEY` | GIPHY | meme references only |
| `OPENAI_API_KEY` | OpenAI | cloud transcript text (gpt-transcribe; whisper-1 word times only with `--words cloud`); subtitle translation |
| `ANTHROPIC_API_KEY` | Anthropic | subtitle translation (Claude) |
| `GEMINI_API_KEY` | Google AI Studio | subtitle translation (Gemini) |
| — | Openverse | CC images, no key (about 100 requests a day anonymously) |

Offline mode (a variable such as `REELS_OFFLINE=1`) turns the network off entirely.

## Speech recognition (transcript)

Checked 2026-10-04 on a 97 s phone video in Russian against the local faster-whisper medium transcript:

| Model | Word times | Text on the test video | Price |
|---|---|---|---|
| OpenAI `gpt-transcribe` | no (json / text only) | the cleanest: fixed a case ending and a wrong word, caught 2 words the local model dropped | $0.0045 / min |
| OpenAI `gpt-4o-transcribe` | no | 3 errors the others did not make | ~$0.006 / min |
| OpenAI `whisper-1` | yes (`verbose_json`, `timestamp_granularities[]=word`) | 1 wrong word; heard one retake repeat the others merged; times off by > 0.15 s for 40 of 187 words | $0.006 / min |
| Google Gemini | guessed by the model, not measured | — | — |
| Anthropic Claude | no audio input in the API | — | — |

Hence the default: the local word times with `gpt-transcribe`'s text laid onto them. Upload limit 25 MB per file
(`mp3, mp4, mpeg, mpga, m4a, wav, webm`). Endpoint `https://api.openai.com/v1/audio/transcriptions`, multipart,
`Authorization: Bearer`. OpenAI's API data policy: https://openai.com/policies/

## Subtitle translation (language models)

Model names checked 2026-10-04 on the providers' model pages; each takes `--model` for another one.

| Provider | Default model | Endpoint | Key header |
|---|---|---|---|
| Anthropic | `claude-sonnet-5-5` | `POST https://api.anthropic.com/v1/messages` (`anthropic-version: 2023-06-01`) | `x-api-key` |
| OpenAI | `gpt-6.1-sol` (cheaper: `gpt-6-luna`) | `POST https://api.openai.com/v1/responses`, JSON schema output | `Authorization: Bearer` |
| Google | `gemini-3.8-flash` (cheaper: `gemini-3.5-flash-lite`) | `POST https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent`, `responseMimeType: application/json` | `x-goog-api-key` |

Only the subtitle text goes out (the phrases, the brand's voice and forbidden words). Checked live with OpenAI on a
61 s video (25 phrases, about 2,100 tokens): every phrase translated in one request; without the form-of-address
rule the polite Russian "you" became the informal German "du", hence the rule in the prompt.

## Stock video

| Service | API and key | Vertical | Commercial use | Price |
|---|---|---|---|---|
| **Pixabay** | yes, free key | no filter, select by h > w | yes, no attribution | 0 |
| **Pexels** | yes; issuing new keys was paused (2026-10-01) | `orientation=portrait` | yes, no attribution | 0 |
| **Magnific** (Freepik, Videvo) | yes; **not yet run live with a key** (the filter syntax and response fields follow the documentation) | `filters[orientation]=vertical`, 9:16, duration | free content — with attribution | credits |
| Coverr | yes | `is_vertical` in the response | commercial use forbidden on a free key | from $5/mo |
| Mixkit | no API | on the website only | yes | 0, manual |
| Vecteezy | yes | ? | Free: attribution, project budget ≤ $1,000 | $1 per clip |
| Shutterstock / Storyblocks / Getty / Adobe Stock | enterprise or paid; Shutterstock has no 9:16 | — | yes | by contract |

Pexels and Pixabay rules:
- **not allowed:**
  - selling a clip “as is”;
  - uploading it to other stock sites;
  - using clips with recognizable brands commercially;
  - showing recognizable people in a bad light;
  - creating the impression that a person endorses a product;
  - mass downloading;
- **Pixabay:** cache API responses for 24 h, limit 100 requests per minute;
- **Pexels:** 200 requests per hour.

Endpoints:
- **Pixabay:** `GET https://pixabay.com/api/videos/?key=…&q=…&video_type=film&per_page=50`. File — `hits[].videos.large|medium.url`, duration — `duration`, author — `user`, page — `pageURL`.
- **Pexels:** `GET https://api.pexels.com/v1/videos/search?query=…&orientation=portrait&size=medium`, header `Authorization: <key>`. File — `videos[].video_files[]`: mp4, h > w, width closest to 1080, field `link`.

**Source abstraction.** A provider does two things: `search(query) → candidates` and `fetch(candidate) → file`. A candidate is `{provider, id, title, url | path, page_url, w, h, dur, size_mb, license, author, score}`. A new stock is connected by adding one provider (steps: “Adding a source” below). A provider error means a warning and an empty list.

## Video generation by a model

**Status:** paid generation has not yet been run live with a key. The request fields follow the providers' documentation; treat the first paid run as a test as well: one short clip, then check the result and the charge.

| Model (via fal.ai) | 9:16 | Exactly 6 s | Start frame | Audio off | ≈ $ per 6 s |
|---|---|---|---|---|---|
| **Veo 3.1 Fast** | yes | yes (4/6/8) | yes | yes | **0.60** — a good default |
| Kling v3 Standard | yes | yes (3–15) | yes, start and end | yes | 0.50 |
| Veo 3.1 Lite (720p) | yes | yes | yes | yes | 0.18 — a cheap draft |
| LTX-2.3 (1080×1920 natively) | yes | yes (6/8/10) | yes | yes | 0.36–0.48 |
| Runway gen4.5 | 720×1280 only | 2–10 | yes | no audio at all | 0.72 |
| Luma Ray 3.2 | yes | no: 5 or 10 s | yes | — | 0.30 (5 s, 720p) |
| Seedance 2.0 | yes | yes | yes | yes | 1.45–1.82; rejects frames with realistic faces |
| Sora 2 | — | — | — | — | **API shut down by OpenAI on 2026-09-24** |

**Why through an aggregator (fal.ai):**
- one key for many models;
- one queue: `POST https://queue.fal.run/<model>` → `status_url` → `response_url` → `video.url`;
- the model is switched with a setting.

Models use different fields: the image is `image_url` or `start_image_url`, the duration is `"6s"` or `6`. A mapping table is needed. Turn audio off with `generate_audio: false` and, to be safe, strip it during preparation (`-an`).

**Fallback path** — the Gemini API directly (Veo). There the audio cannot be turned off, so it is stripped during preparation. Veo adds an invisible SynthID watermark. The script does not drive this path (it submits only to fal.ai): run the prompt by hand and put the clip at `generated/<insert>.mp4`.

**AI label.** Meta requires an “AI info” label on photorealistic video created or altered by AI. According to third-party sources, since summer 2026 ads with undisclosed AI are rejected.

## Online memes

| Service | API | Embed in a commercial video |
|---|---|---|
| **Openverse** | yes, no key, `license_type=commercial` | **yes**, with attribution (CC) |
| GIPHY | yes, free beta key | **no**: content is for personal non-commercial use only, files may not be stored — reference only |
| KLIPY | yes | no, explicitly forbidden |
| Tenor | shut down on 2026-06-30 | — |
| Imgflip / memegen.link | caption generators on other people's templates | no: the templates are other people's frames |
| Know Your Meme, Reddit, 9GAG | no API, or commercial use by contract | no |

**Openverse:** check the license on the image's **detail record** before downloading — take only CC0, PDM, CC BY, CC BY-SA (NC and ND — reject); save the license code and version, the link, the author and the attribution. Search: `GET https://api.openverse.org/v1/images/?q=…&license_type=commercial&page_size=20` → `results[].{id,title,url,foreign_landing_url,creator,license,license_version,attribution,width,height}`.

**Instagram.** The Reels editor offers GIPHY GIF stickers. This is a legal way to add someone else's GIF. Whether such a video can be promoted as an ad — sources contradict each other; check in the app.

**Rights.** There are precedents of lawsuits over memes used commercially. A movie still or a photo of a person in a brand's video reads as that person endorsing the brand.

## Adding a source

Before writing code, read the service's terms: commercial use, attribution, storing files, bulk downloading, request limits and caching. All scripts are in this add-on's `scripts/` folder; network calls go through `http_json()` and `download()` from `reels_online.py` (HTTPS only, keys scrubbed from errors, `cache_hours` for services that require caching).

**A stock provider** (`stock.py`):
1. Subclass `Provider`: set `name`, `online = True` and `key_env` (the key's variable name); write `search(query, o)`, which returns candidates built with `cand(...)` (with `license`, `author` and `page_url` filled in: attribution is taken from there), and `fetch(c, folder)`, which downloads the chosen clip and returns its path. `available()` already checks offline mode and the key.
2. Add an instance to `PROVIDERS` at the end of `stock.py`.
3. In `reels_online.py`, add `"<name>": "<KEY_VARIABLE>"` to `FOOTAGE_KEYS`: then `keys set` and `keys list` know the key, and `reelcfg.py show` counts the provider as available. A variable whose name has none of `KEY`, `TOKEN`, `SECRET` also goes into `SECRET_ENVS`, so its value is scrubbed from errors. A source with no key at all also needs a change in `effective_online()`, which counts only providers with a key.
4. Turn it on: the name in `online_footage_providers` (the video's `reel.json`, the brand's `inserts` or the project's `reel-defaults.json`), the key with `reels_online.py keys set <NAME>`; check with `footage.py providers --edit edit/<id>` (the core's script).

**A video model** (`genfootage.py`): add an entry to `MODELS`, keyed by the value of `generation_model`: `endpoint` (text-to-video) and `i2v` (image-to-video) on fal.ai, `image_key` (`image_url` or `start_image_url`), `duration` (seconds → the model's format: `str` or `lambda s: f"{s}s"`), `durations` (the allowed lengths), `usd_s` (price per second without audio, for the estimate shown before the “yes”), `neg` (whether it takes `negative_prompt`), an optional `note`. The request sends `prompt`, `aspect_ratio: "9:16"`, `duration`, `generate_audio: false`; an endpoint that names these differently needs a change in `cmd_run()`. Only fal.ai is driven (`PROVIDERS_SUPPORTED`): the other key names in `GEN_KEYS` (`REPLICATE_API_TOKEN`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `RUNWAYML_API_SECRET`) are known to `keys set` and `reelcfg.py show`, but no request is sent to those providers; a prompt for them is run by hand.

**A meme source** (`memes_online.py`):
1. A branch for the new name in `online_search()` that returns `{provider, id, title, url, page_url, w, h, license, author, attribution, embed}`. `embed: False` for a reference-only source (its terms forbid downloading or burning into a commercial video): search marks it “REFERENCE ONLY”, and it is never downloaded.
2. The name in the `--provider` choices in `main()`.
3. In `reels_online.py`, `"<name>": "<KEY_VARIABLE>"` (or `None` without a key) in `MEME_KEYS`, and the name in `online_meme_providers`.
4. `fetch` downloads only from Openverse, after checking the license on the item's detail record. A new source cleared for embedding needs its own branch there with the same license check and the same sidecar (`rights: "cc"`, license, attribution).
