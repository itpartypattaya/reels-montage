# IT Reelsmaker Online

An optional add-on for [IT Reelsmaker](../it-reelsmaker/README.md). It adds three online sources to the visual plan of a video edit, and one heavy step on your own server:

- **vertical stock footage**: Pixabay, Pexels and Magnific;
- **CC-licensed memes** from Openverse; GIPHY is used as a reference only;
- **paid AI video generation** through fal.ai: Veo, Kling and LTX;
- **a more accurate transcript**: OpenAI's text laid onto the local word times (fewer wrong words in subtitles);
- **subtitle translation** through Claude, OpenAI or Gemini (by default Claude translates in the session, free);
- **figure cut-out on your own server** over SSH, when it is too heavy for your laptop.

The core plugin works without this add-on. Install the add-on only if you want these sources. Every download and every paid generation waits until you approve the visual plan, which lists the source, the size in MB and the price.

## Install

```bash
claude plugin marketplace add https://github.com/itpartypattaya/reels-montage.git
```

```bash
claude plugin install it-reelsmaker-online@itparty
```

The core plugin `it-reelsmaker` is installed with it as a dependency.

Then link the add-on to your editing project, once and again after each add-on update. Claude does it for you on the first online request; by hand it is `python <add-on>/skills/it-reelsmaker-online/scripts/reels_online.py link` in the project folder. Online sources stay off until you turn them on for a video or the project.

## Keys

Add your own API keys in your terminal, one at a time. The key is typed with hidden input, never passes through the chat, and goes into `~/.config/it-reelsmaker/keys.env` (readable by you only; `REELS_KEYS_FILE` picks another file):

```bash
python <add-on scripts>/reels_online.py keys set PEXELS_API_KEY
```

`keys list` shows which keys are set (values masked), `keys remove <NAME>` deletes one. Environment variables work too and take precedence over the file. The keys:

- `PIXABAY_API_KEY`
- `PEXELS_API_KEY`
- `MAGNIFIC_API_KEY`
- `FAL_KEY`
- `GIPHY_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

Plugin settings can't hold these keys: Claude Code keeps protected plugin settings away from the commands Claude runs, so the add-on's scripts could not read them. Openverse needs no key. The skill never prints keys and masks them in its output and in saved errors. Without a key, that source simply switches off.

Enable sources per video in `edit/<id>/reel.json`, for example `"use_online_footage": true`, or just ask: “find stock footage for the coffee scene”.

## Examples

- “Use online stock for the B-roll in video 4821, moderate intensity.”
- “Generate a 6-second insert of hands sorting printed CVs. Show me the price first.”
- “Find a CC-licensed reaction meme for the line about missed deadlines.”
- “Transcribe video 4821 through OpenAI.”
- “Translate the subtitles of 4821 into German through Gemini.”

## Data and network

When a source is enabled, these requests leave your computer:

- **Stock and meme sites** receive your search queries.
- **fal.ai** receives your generation prompts and, if you choose, a start frame.
- **OpenAI**, only for a cloud transcript you asked for: the speech audio of the video.
- **Groq**, only if you set it as the fallback (`transcription_fallback=groq`) or ask for it: the same speech audio, for the transcript text.
- **Anthropic, OpenAI or Google**, only for a subtitle translation you asked for: the subtitle text.
- **Services that need a key** receive their own API key with each request; Openverse needs none.
- **Your own server**, only if you set one for cut-outs: frames of the span go there over your SSH client and are deleted after the job.

Downloaded files are saved in your project. Each provider's own terms and privacy policy apply. See [PRIVACY.md](PRIVACY.md).

Photorealistic AI inserts need the “AI info” label when you publish on Instagram. Stock and CC attribution goes into the post caption; the skill records it in `credits.json`.

## Support

[GitHub Issues](https://github.com/itpartypattaya/reels-montage/issues) or mr.a.vaskov@gmail.com.

## License

[MIT](LICENSE).

Paid submissions reserve `gen.job` under the plan lock before contacting fal. A `submitting` or `unknown` state never resubmits automatically: check the provider dashboard, then restore the request ID and queue URLs to resume, or clear the job by hand only after confirming that no paid request was accepted. Resumed fal jobs use only `FAL_KEY`; other saved providers are refused. Downloaded raw clips are bound to their request ID, so an older clip cannot satisfy a new job. Requests and redirects require HTTPS; credentials are stripped on an origin change, and fal queue hosts are checked at every hop. JSON responses are limited to 20 MB and downloads use unique temporary files.
