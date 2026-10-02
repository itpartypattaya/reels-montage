# Privacy policy — IT Reelsmaker

Effective date: 2 October 2026. Maintainer: IT Party Pattaya, https://github.com/itpartypattaya. Contact: mr.a.vaskov@gmail.com or [GitHub Issues](https://github.com/itpartypattaya/reels-montage/issues).

## What the plugin collects

Nothing. IT Reelsmaker is a set of instructions and local scripts for Claude Code. The scripts make no network requests. It has no server, no analytics and no telemetry, and the maintainer receives no data from it.

## Where your data is processed

The editing programs (ffmpeg, Remotion, Python scripts) run on your computer. Claude processes the conversation and the material included in it through Anthropic, and an optional step may use a cloud service, as listed below. Sending frames to your own server for figure cut-outs is a feature of the separate online add-on, which has its own privacy policy. Your source videos, transcripts, cut plans, face measurements (`faces.json`), renders and brand profiles stay in the project folder you choose. They stay there until you delete them.

## When data leaves your computer

| Destination | What is sent | When |
|---|---|---|
| Anthropic (Claude) | The conversation, including transcript text, file excerpts and video frames that Claude reads | Always, as in any Claude Code session. [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy) applies |
| A cloud transcription service | The audio of your video | Only if you choose a cloud transcriber instead of the default local `faster-whisper`. That service's privacy policy applies |
| npm, PyPI, browser distribution hosts, Google Fonts, Hugging Face, GitHub | Standard download requests, which include your IP address | When you install Remotion and Python packages, when Remotion downloads its own headless browser on the first render, when fonts load at render time, and when the models for the features you use download (faster-whisper, YuNet, rembg) |

## People in your videos

The face model (YuNet) finds the position and size of faces so that text doesn't cover them. It does not recognize or identify anyone, and it runs locally. Get consent from the people on camera before you publish a video.

## Children

The plugin is not directed at people under 18.

## Changes

Changes to this policy are published in this repository; the file history shows every version.
