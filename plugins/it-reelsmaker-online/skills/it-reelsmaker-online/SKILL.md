---
name: it-reelsmaker-online
description: >
  Online sources for it-reelsmaker video edits: vertical stock footage (Pixabay, Pexels, Magnific), CC-licensed
  memes (Openverse; GIPHY as reference only), paid AI video generation (Veo, Kling, LTX via fal.ai) for B-roll, and
  figure cut-outs on your own server over SSH.
  Use only inside an it-reelsmaker edit, when the person enabled online footage, online memes or model generation
  in reel.json or asked for it directly: "find stock footage", "generate an insert", "online memes", "cut out the
  figure on my server". Every download
  and every paid run happens only after the person approves the visual plan with source, size and price.
---

# Online sources for it-reelsmaker

An add-on to the `it-reelsmaker` skill. It plugs three online sources into the core's visual plan (step 7a and the core skill's inserts reference): stock footage, online memes and a video model. It is never used without the core. Everything not described here follows the core's rules: why an insert is needed, the intensity budget, meme size and placement, clip preparation and plan checks.

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
- **Network and keys.** Check offline mode and the key **before every** network action, not only at search time. Keys come from environment variables or from a file outside the project (`references/sources.md`). Mask API keys, authorization headers and `key=`/`token=` in URLs in all output and saved errors; keys are never written to project files or git.
- **Stock.** Download only what was selected. Record attribution in `edit/<id>/inserts/credits.json` and in the post caption. Never present a stock person as “our client or candidate”: stock licenses forbid implied endorsement.
- **Online memes.** Embed only CC0, PDM, CC BY and CC BY-SA, with attribution; check the license on the image's detail page. GIPHY is a reference only (an Instagram sticker or a re-shoot). Film stills, celebrity photos and other people's memes featuring people — never.
- **Generation.** Prompt fields and template, checks, and “money is never spent twice” — `references/generation.md`.
- **AI label.** A photorealistic insert from a model → turn on the “AI info” label when publishing (Meta rules). Stylized code graphics don't need it.
- **Brand restrictions** (`forbidden_imagery`, `forbidden_imagery_en`) apply to stock queries and generation prompts.

## Figure cut-out on your own server

The core cuts the figure out on this computer (`matte.py`; the cut-out reference of the core skill, `figure.md`). On a weak laptop the same step can run on a server you control: `addon.py matte cut … --host ${user_config.matte_host}` (the add-on setting; if it still reads `${user_config…}`, it is not set: the script then takes `matte.host` from `it-reelsmaker.json` or `REELS_MATTE_HOST`, otherwise ask the person once and write `matte.host` there). Frames of the span go to that host as one JPG archive over your own SSH client, the WebM with alpha comes back, and the temporary files are removed there, on error too. The server needs `rembg` with the `u2net_human_seg` model (its path on the server: `matte.server_rembg`, or `matte.rembg` when you never cut out locally); one cut-out at a time under a server-side lock, with a memory check. Nothing goes anywhere else.

## References

| File | When |
|---|---|
| `references/sources.md` | connecting stock, video models and online memes: terms, prices, endpoints, keys |
| `references/generation.md` | model generation: prompt fields and template, checks, run rules, AI label |

Paid submissions reserve `gen.job` under the plan lock before contacting fal. A `submitting` or `unknown` state never resubmits automatically: check the provider dashboard, then restore the request ID and queue URLs to resume, or clear the job by hand only after confirming that no paid request was accepted. Resumed fal jobs use only `FAL_KEY`; other saved providers are refused. Downloaded raw clips are bound to their request ID, so an older clip cannot satisfy a new job. Requests and redirects require HTTPS; credentials are stripped on an origin change, and fal queue hosts are checked at every hop. JSON responses are limited to 20 MB and downloads use unique temporary files.
