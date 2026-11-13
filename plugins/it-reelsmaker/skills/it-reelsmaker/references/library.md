# Your own library of sounds, music and icons

Optional. Read it when `{{ASSETS_DIR}}` is set, or when a video gets sound effects without a library (“Sounds synthesized in code”): how to catalog the library, pick icons and sounds, and mix burned-in music.

You can set up an `{{ASSETS_DIR}}` folder, roughly like this ⟨YOURS: your own categories⟩:
```text
ASSETS_DIR/
  Sounds/     Whoosh · Click · Marker · Paper · Keyboard · Phone · Clock · Hit · Riser · Bass · …
  Music/      Calm · Inspiring · Upbeat · Dark
  Icons/      People (pictograms) · Hands · Smartphone (phone frames) · Apps (logos) · …
  App icons/  animated logos (often on a green background)
```
**Work through a catalog, not by browsing files** (names like `IMG_xxxx` tell you nothing). `library_catalog.py` (`--dir {{ASSETS_DIR}}`, or the library folders from the settings) reads each file once and records the following; later runs measure only changed files, `--full` measures everything again:
- for audio: duration, **sound start** (how much silence there is at the start of the file — it matters), peak and mean loudness;
- for images and video: size, background (transparent / green screen / black / white / other);
- **your verdict** (`ok` / `caution` / `no` / `check license` + reason) from your own file `_catalog/verdicts.json`: a rule per folder (`defaults`, the longest matching folder wins) and per-file exceptions (`files`, optionally `rights_block: true` for third-party rights); the format with an example is in `library_catalog.py --help`. The plugin ships no verdicts: without the file, the catalog lists technical data only. With the file, a file that no rule covers gets `caution` (“no rule for this folder”). A disputed file inside a folder with a rule goes into `files` as an exception, not into a new folder rule. A third-party rights ban for every brand is only the explicit `rights_block: true` field: a `no` whose reason says “film still” does not set it. Music is recognized by a top folder named Music;
- **overview sheets** of images and videos, 80 per sheet, with a colored verdict stripe (gray: no verdict): pick an icon by eye from the sheet. A cell reading “no frame” or “unreadable” is a file that could not be decoded. The cells are 150 px thumbnails, and a verdict given from a sheet can be wrong: open a doubtful file at full size before using it;
- **reaction memes** (emotion pictograms, statues, “hand gestures”): a separate `memes.json` annotation next to the catalog (written by you or the agent; a catalog rebuild never touches it) with description, emotion and “when it fits”. Then a meme is found by the meaning of the line (“the candidate didn't understand the question” → a figure with question marks), and its rights by the catalog verdict (`references/inserts.md`, “Memes”).

**Icons:** flat pictograms are the safest option; service logos only when the service is named in the speech or the CTA; `{{FORBIDDEN_IMAGES}}`, real celebrities, politicians, film stills and meme stills are a no. One icon at a time, 180–320 px, not on the face. Copy **only the chosen files** into Remotion's `public/`, and compress large PNGs. Green background → `chromakey=0x00FF00:0.18:0.06,despill=type=green,format=yuva420p` into WebM VP9 with alpha; black background → `mixBlendMode: "screen"`.

An icon supports the thesis; it does not repeat the subtitle word for word. One icon style per video: don't mix flat pictograms with 3D or collage; collage-style icons only in the “Editorial” style. Pictograms: white over video, black on a light card. Neon or glowing icons break the “no glow” rule: only in the “Glass” style. Shrink large PNGs to about 2× their on-screen size. A green fringe after chroma keying → raise the second `chromakey` value by 0.02–0.04 and check a still again; on black, `mixBlendMode: "screen"` or `colorkey=0x000000:0.1:0.05`. A GIF becomes a WebM VP9 with alpha the same way (`format=yuva420p`, without `chromakey`).

**No sounds of your own yet?** A starter pack of 260 short CC0 sound effects (hits, whooshes, clicks, UI sounds, typing; Kenney and an OpenGameArt keyboard pack, commercial use without attribution) is in the repository's releases: https://github.com/itpartypattaya/reels-montage/releases/tag/sfx-cc0-1 (`it-reelsmaker-sfx-cc0.zip`, 2 MB, with `LICENSE.txt`). The person downloads it and unpacks the `cc0-sfx` folder into `{{ASSETS_DIR}}` (the plugin never downloads anything itself); then run `library_catalog.py`, and a folder rule `"cc0-sfx": ["ok", "CC0"]` in `verdicts.json` marks the whole pack. Bright game-like sounds from it (`casino/`, glitches) are still “caution” by taste.

**Sounds for events:** the Remotion kit does not play the scenes' `sound`; list the chosen files in `edit/<id>/sfx.json` (`{"sounds": [{"file": …, "at": <second of the video>, "start": <sound start from the catalog>, "what": …}]}`; `at` from the plan: the scene's start, its spoken word, a tap's time) and master with `master_audio.py` (it mixes in `edit/<id>/sfx.json` by itself): they are mixed in before the voice chain, 15 dB under the voice peak.

| Event | Sound |
|---|---|
| whip, shot change, card fly-in | whoosh (on the 2–4 main ones, not on every one) |
| marker bar appears | marker |
| list item, chip | click (≤ 3–4 in a row) |
| card, document | paper |
| “Typewriter” subtitles | keyboard, quiet |
| CTA “send me a message” | phone notification |
| deadlines | clock |
| accent word appears | pop, click, light hit |
| shot change, B-roll | soft hit |
| punch-in on the main point | soft hit (hard hits and bass only for a loud brand tone) |
| build-up before a reveal | riser, short and quiet |

No more than one effect every 2–3 s. **Place by the start of the sound, not of the file:** `Sequence from = event frame − sound start`, otherwise the hit will be late (a whoosh can start with 1.8 s of silence). Effects 12–18 dB below voice peaks: set the gain from the sound's peak in the catalog before listening, then judge by ear; trim long tails to 0.3–0.8 s with a fade.

Loud or game-like sounds (glitch, error, heavy hits, dice, chips) count as “caution”: only for the `bold` tone or an ironic moment. For a calm brand tone, 4–8 sounds per 30–60 s of video. Trim long tails to 0.3–0.8 s with a 50–100 ms fade. For repeated and calm moments, take sounds with no sharp ringing highs; a sound with an unknown license gives way to a similar CC0 one. In Remotion, trim the start of a file with `trimBefore` (in frames; `startFrom` is deprecated).

**Craft** (starting values after [HyperFrames](https://github.com/heygen-com/hyperframes), Apache-2.0; not yet checked on our videos):
- **only what is seen sounds:** a click on a real tap, a whoosh on a cut or a big fast card, a pop on a badge or a number, a riser into an impact once, on the payoff. A sound with no event on screen is noise;
- **the sound's attack lands one frame after the picture** (`at` = the event second + 1/fps; the file's sound start stays in `start`, and `master_audio.py` puts that point on `at` by itself, so do not subtract it again): the eye takes in the event first, and a sound even slightly ahead of the picture reads as out of sync;
- **two or three takes of a repeated sound in turn:** the same whoosh on every cut is the surest sign of a template. Alternate files from the library, or vary a synthesized one (below: ±10–15 % in pitch and length);
- a low hit below ~150 Hz is lost on a phone speaker: give it a click or a short noise on top, or take a brighter sound.

**Sounds synthesized in code** (no files, no license questions; the alternative to the starter pack). A short WAV per sound made with ffmpeg's `aevalsrc` / `anoisesrc` in the video's folder, then into `sfx.json` like any other file (its sound start is 0). The recipes below were checked to render; the levels differ, `master_audio.py` sets every effect under the voice anyway. Listen to each before use.

| Sound | Recipe |
|---|---|
| pop (badge, number, accent word) | a rising chirp 520 → 1420 Hz over 0.12 s, fast decay: `aevalsrc='0.9*sin(2*PI*(520*t+450*t*t/0.12))*exp(-18*t)':s=44100:d=0.12,afade=t=out:st=0.10:d=0.02` |
| thud (stamp, soft hit) | a falling chirp 95 → 55 Hz over 0.3 s plus a little noise, dulled above 900 Hz: `aevalsrc='(0.8*sin(2*PI*(95*t-20*t*t/0.3))+0.25*(2*random(0)-1))*exp(-10*t)':s=44100:d=0.3,lowpass=f=900,afade=t=out:st=0.25:d=0.05` |
| click (tap, list item) | 30 ms of noise with a 2400 Hz tone: `aevalsrc='(0.5*(2*random(0)-1)+0.5*sin(2*PI*2400*t))*exp(-160*t)':s=44100:d=0.03` |
| ding (done, check mark) | 2637 + 5274 Hz, ~0.35 s decay: `aevalsrc='(0.6*sin(2*PI*2637*t)+0.3*sin(2*PI*5274*t))*exp(-8*t)':s=44100:d=0.6,afade=t=in:d=0.003,afade=t=out:st=0.5:d=0.1` |
| whoosh (cut, card fly-in) | pink noise around 1.5 kHz, swelling and fading as sin²: `anoisesrc=c=pink:d=0.5:a=0.8:r=44100,bandpass=f=1500:w=1.2,volume='pow(sin(PI*t/0.5),2)':eval=frame` |
| rise (build-up) | a chirp 300 → 1200 Hz over 0.7 s, swelling: `aevalsrc='0.6*sin(2*PI*(300*t+900*t*t/(2*0.7)))*t/0.7':s=44100:d=0.7,afade=t=out:st=0.62:d=0.08` |
| marker (marker bar drawn) | noise around 3 kHz pulsing at 38 Hz: `aevalsrc='(2*random(0)-1)*(0.5+0.5*sin(2*PI*38*t))*0.5':s=44100:d=0.4,bandpass=f=3000:w=1,afade=t=in:d=0.03,afade=t=out:st=0.32:d=0.08` |

Run each as `ffmpeg -f lavfi -i "<recipe>" -ac 2 edit/<id>/sfx/<name>.wav`. A chirp from f0 to f1 over T seconds is `sin(2*PI*(f0*t + (f1-f0)*t*t/(2*T)))`; change f0, f1 and T for the second and third take. Keep the brand tone's density (`sfx` in the tone table) and the 2–3 s spacing above.

**Music: license first.** ⟨YOURS: `{{ACCOUNT_TYPE}}`⟩. An Instagram business account only has access to the royalty-free Meta Sound Collection library in the app, and a track burned into the video must have a **commercial** license. Commercial tracks, slowed/reverb versions of other people's songs, files from download sites: do not burn them in. A safe default: render without music and pick the track in the app when publishing. A “check license” verdict is not a permission: open the track's page and check commercial use and attribution; a license written for one platform's audio library must be read separately for other platforms.

## Music in the mix

**Music, if burned in** (not yet verified in a finished video; listen to the whole master before delivery):
- mix music only with `master_audio.py`, never inside Remotion: Remotion has no sidechain, so a static bed either buries the voice or disappears;
- **duck the music under the main line**: the phrase before the CTA or the punchline goes out in near silence, `master_audio.py … --duck 21.3-23.9` (seconds of the render, −14 dB by default, `:-20` for deeper, 0.2 s fades; repeatable), applied to the music only; match the music's tempo to the pace of the edit;
- set the level **by the gap to the voice**, not by a percentage of track volume: a 15 dB gap → bed at −24 LUFS (13 → −22, 17 → −26);
- sidechain on the voice: `sidechaincompress=threshold=0.10:ratio=3:attack=20:release=380`;
- trap: `sidechaincompress` outputs about a second less than it received, so the final hit silently disappears. `apad` both inputs, `atrim` the output, check the duration;
- `amix` only with `normalize=0`, otherwise the voice quietly drops;
- **cut the track to the meaning**: find **the track's drop**, its loud moment (the sharpest rise in short-term loudness over 1.5 s, not in the first 4 s: `--find-drops`), and land it on the final phrase: `--drop-at <phrase second> --drop-in-track <drop second>` (offset = drop time − phrase time). Not the same as ducking: the drop is the music getting louder where the track does, the duck is the music held down under a line;
- **no single moment to land?** Take the track's fullest stretch instead of its quiet intro: momentary loudness every 100 ms, `ffmpeg -i track.mp3 -af "asetnsamples=n=4410,ebur128=metadata=1,ametadata=print:key=lavfi.r128.M:file=m.txt" -f null -` (4410 samples = 100 ms at 44.1 kHz; set n = rate / 10), then the window as long as the video with the highest mean (values below −60, and `-inf`, count as −60; the window ends inside the track) → `--music-start <its start>`. The momentary value covers 400 ms, so the found start can be 0.2–0.4 s late: move it back onto the nearest beat by ear. Shorter than the video from there → say so and loop the track or start earlier, don't leave silence at the end;
- bring the final mix to −14 LUFS again.
