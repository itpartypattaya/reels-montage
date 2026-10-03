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
| — | Openverse | CC images, no key (about 100 requests a day anonymously) |

Offline mode (a variable such as `REELS_OFFLINE=1`) turns the network off entirely.

## Stock video

| Service | API and key | Vertical | Commercial use | Price |
|---|---|---|---|---|
| **Pixabay** | yes, free key | no filter, select by h > w | yes, no attribution | 0 |
| **Pexels** | yes; issuing new keys was paused (2026-10-01) | `orientation=portrait` | yes, no attribution | 0 |
| **Magnific** (Freepik, Videvo) | yes | `filters[orientation]=vertical`, 9:16, duration | free content — with attribution | credits |
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

**Source abstraction.** A provider does two things: `search(query) → candidates` and `fetch(candidate) → file`. A candidate is `{provider, id, title, url | path, page_url, w, h, dur, size_mb, license, author, score}`. A new stock is connected by adding one provider. A provider error means a warning and an empty list.

## Video generation by a model

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

**Fallback path** — the Gemini API directly (Veo). There the audio cannot be turned off, so it is stripped during preparation. Veo adds an invisible SynthID watermark.

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
