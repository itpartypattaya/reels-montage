# Privacy policy — IT Reelsmaker Online

Effective date: 2 October 2026; updated 7 October 2026 (Groq) and 13 November 2026 (ElevenLabs). Maintainer: IT Party Pattaya, https://github.com/itpartypattaya. Contact: mr.a.vaskov@gmail.com or [GitHub Issues](https://github.com/itpartypattaya/reels-montage/issues).

The add-on collects nothing. It has no server and no telemetry, and the maintainer receives no data from it. The core plugin's [privacy policy](../it-reelsmaker/PRIVACY.md) applies to everything else.

## Services the add-on contacts on your behalf

When a source is enabled, the agent may contact it while preparing the visual plan, to search for candidates and check metadata and licenses. Media downloads and paid generation start only after you approve the plan.

| Service | What is sent | Policy |
|---|---|---|
| Pixabay | search queries, your API key | https://pixabay.com/service/privacy/ |
| Pexels | search queries, your API key | https://www.pexels.com/privacy-policy/ |
| Magnific (Freepik) | search queries, your API key | https://www.freepik.com/legal/privacy |
| Openverse | search queries | https://openverse.org/privacy |
| GIPHY (reference only) | search queries, your API key | https://giphy.com/privacy |
| fal.ai | generation prompts, an optional start frame, your API key | https://fal.ai/privacy |
| OpenAI (cloud transcript) | the video's speech audio (16 kHz mono WAV), an optional prompt with names and terms, your API key | https://openai.com/policies/ |
| Groq (fallback transcript text, only with `transcription_fallback=groq` or `--provider groq`) | the same speech audio (16 kHz mono WAV), the language and the optional prompt, your API key | https://groq.com/privacy-policy/ |
| Anthropic, OpenAI or Google Gemini (subtitle translation) | the subtitle text of the video, the brand's voice and forbidden words, your API key | https://www.anthropic.com/legal/privacy · https://openai.com/policies/ · https://policies.google.com/privacy |
| ElevenLabs (narration in your cloned voice) | the script's text by blocks, each with the neighbouring blocks' text (`previous_text`/`next_text`) for intonation; the voice id; for a new clone (`voice clone`) your voice recordings and the voice's name; your API key | https://elevenlabs.io/privacy-policy |
| Your own server (figure cut-out) | frames of the rough cut's span (JPG), over your SSH client | your server, your policy; temporary files are deleted after each job |

Your API keys are stored on your computer, in environment variables or a file outside the project (`keys set` writes it readable by you only and reads the key with hidden input in your terminal, so it never passes through the chat or Claude). Each key is sent only to its own provider, for authentication, and is never written to project files or git. Downloaded clips and images are saved in your project folder; their licenses and attribution go into `credits.json`.

## A narration in your cloned voice (ElevenLabs)

Only your own voice, and only after you confirm it: the add-on records your consent, its wording version and time, per
voice. A clone is made from recordings you chose and listened to; they leave your computer for ElevenLabs, which keeps
them with no term stated for this use, and by its policy may use data for training unless you opt out: **turn that off
in your ElevenLabs account before uploading**. Zero retention is offered only on enterprise plans and not for cloning.

On your computer: the voices and the consent are in `voices.json` next to the keys file (`~/.config/it-reelsmaker/`,
readable by you only), never in the project, a brand or git; project files name the voice, not its id. The paid answers
(audio and timings), the joined `generated/narration.wav` and its transcript are saved in the video's folder.

`voice forget` removes the local record; `voice forget --remote` also deletes from ElevenLabs a voice the add-on itself
created. ElevenLabs does not state that deleting a voice deletes its samples or the history of what it read: ask
ElevenLabs if you need that. Platforms may require a label for realistic synthetic audio (Instagram's “AI info”;
TikTok's AI content label); the skill reminds you when you publish.
