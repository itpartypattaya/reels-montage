---
name: it-reelsmaker-online
description: >
  Online sources for it-reelsmaker video edits: vertical stock footage (Pixabay, Pexels, Magnific), CC-licensed
  memes (Openverse; GIPHY as reference only) and paid AI video generation (Veo, Kling, LTX via fal.ai) for B-roll.
  Use only inside an it-reelsmaker edit, when the person enabled online footage, online memes or model generation
  in reel.json or asked for it directly: "find stock footage", "generate an insert", "online memes". Every download
  and every paid run happens only after the person approves the visual plan with source, size and price.
---

# Online sources for it-reelsmaker

An add-on to the `it-reelsmaker` skill. It plugs three online sources into the core's visual plan (step 7a and the core skill's inserts reference): stock footage, online memes and a video model. It is never used without the core. Everything not described here follows the core's rules: why an insert is needed, the intensity budget, meme size and placement, clip preparation and plan checks.

## Reel settings

Keys live in `edit/<id>/reel.json`, with the same layers as the core (defaults → `brand.json → inserts` → `reel.json` → words in the prompt):

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

## References

| File | When |
|---|---|
| `references/sources.md` | connecting stock, video models and online memes: terms, prices, endpoints, keys |
| `references/generation.md` | model generation: prompt fields and template, checks, run rules, AI label |
