# Changelog

What changed in IT Reelsmaker Online. The newest version is on top.

## 1.4.2

- With an older core plugin, the cloud transcript and the subtitle translation now say “needs it-reelsmaker
  ≥ 1.5.0 (update the core plugin)” instead of failing with a Python traceback.
- Cut-out on your own server: when the server setting is empty, the command is run without `--host` (an empty value
  broke it), and the host comes from the project settings.
- The add-on is offered only when you name a cloud service, an API, paid generation, stock or online sources, or
  your own server; a plain “transcribe”, “translate the subtitles” or “cut out the person” stays with the core,
  which does it on your computer.
- The settings layers are listed in the core's full order (with the brand tone and your project defaults).

## 1.4.1

- Cloud transcript: a hyphenated word the cloud wrote whole (“no-no-no.”) no longer leaves the local model's pieces
  (“-no -no.”) behind as extra words, which showed twice in the subtitles (with the core 1.6.0).
- Cloud transcript: the note about words longer than 1 s (a sign of a merged retake) is printed once, not a second
  time for the merged transcript.
- Cloud transcript: words only the cloud heard at the very start get a short time just before the first word the
  local model heard, not a zero-length 0.00-0.00 that the subtitles could not show.
- Online memes: a downloaded file is named by what it really is, not by its link. Emoji sets often come as SVG,
  which used to be saved as a broken `.jpg`; now an SVG stays `.svg` next to its license file with a note to convert
  it to PNG, the search marks SVG results so you can pick a picture instead, and an error page is not saved at all.

## 1.4.0

- **Subtitle translation through an API**: Claude, OpenAI or Gemini translate the video's phrases in the brand's
  voice, within the time each phrase is on screen, and the core checks the result (needs the core 1.5.0). Only the
  subtitle text is sent. By default Claude still translates in the session, for free.

## 1.3.0

- **A more accurate transcript.** `addon.py transcribe` keeps the word times of the local transcript (they match the
  audio) and lays OpenAI's text onto them: fewer wrong words in the subtitles, missed words added, and the words only
  the local model heard listed as places to listen to (often a retake). About $0.005 per minute of speech, only after
  your “yes” or your standing choice in the project settings. No key, no network: the local transcript stays.

## 1.2.0

- **Add API keys safely.** `reels_online.py keys set <NAME>` in your own terminal: the key is typed with hidden input, never passes through the chat, and is saved to a file readable by you only. `keys list` shows what is set (masked), `keys remove` deletes a key.

## 1.1.0

- **Works through the core's scripts.** Link the add-on to your project once; stock footage then shows up in the core's footage search, and the add-on's own commands (online memes, paid generation, server cut-out) run through the core.
- **Figure cut-out on your own server.** When a cut-out is too heavy for your laptop, it runs on a server you control over SSH; frames go only there and are deleted after the job.
- **Off until you turn it on.** Online sources stay off until you enable them for a video or the project; downloads and paid runs still wait for your approval of the plan.

## 1.0.0

- First release: vertical stock footage (Pixabay, Pexels, Magnific), CC-licensed memes (Openverse; GIPHY as reference only) and paid video generation through fal.ai, all after the visual plan is approved.
