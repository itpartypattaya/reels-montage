# Privacy policy — IT Reelsmaker Online

Effective date: 2 October 2026. Maintainer: IT Party Pattaya, https://github.com/itpartypattaya. Contact: mr.a.vaskov@gmail.com or [GitHub Issues](https://github.com/itpartypattaya/reels-montage/issues).

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
| Anthropic, OpenAI or Google Gemini (subtitle translation) | the subtitle text of the video, the brand's voice and forbidden words, your API key | https://www.anthropic.com/legal/privacy · https://openai.com/policies/ · https://policies.google.com/privacy |
| Your own server (figure cut-out) | frames of the rough cut's span (JPG), over your SSH client | your server, your policy; temporary files are deleted after each job |

Your API keys are stored on your computer, in environment variables or a file outside the project (`keys set` writes it readable by you only and reads the key with hidden input in your terminal, so it never passes through the chat or Claude). Each key is sent only to its own provider, for authentication, and is never written to project files or git. Downloaded clips and images are saved in your project folder; their licenses and attribution go into `credits.json`.
