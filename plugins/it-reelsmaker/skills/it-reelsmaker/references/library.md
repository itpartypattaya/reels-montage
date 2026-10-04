# Your own library of sounds, music and icons

Optional. Read it when `{{ASSETS_DIR}}` is set: how to catalog the library, pick icons and sounds, and mix burned-in music.

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
- for images and video: size, background (transparent / green chroma key / black / white / other);
- **your verdict** (`ok` / `caution` / `no` / `check license` + reason) from your own file `_catalog/verdicts.json`: a rule per folder (`defaults`, the longest matching folder wins) and per-file exceptions (`files`, optionally `rights_block: true` for third-party rights); the format with an example is in `library_catalog.py --help`. The plugin ships no verdicts: without the file, the catalog lists technical data only. With the file, a file that no rule covers gets `caution` (“no rule for this folder”). A disputed file inside a folder with a rule goes into `files` as an exception, not into a new folder rule. A third-party rights ban for every brand is only the explicit `rights_block: true` field: a `no` whose reason says “film still” does not set it. Music is recognized by a top folder named Music;
- **overview sheets** of images and videos, 80 per sheet, with a colored verdict stripe (gray: no verdict): pick an icon by eye from the sheet. A cell reading “no frame” or “unreadable” is a file that could not be decoded. The cells are 150 px thumbnails, and a verdict given from a sheet can be wrong: open a doubtful file at full size before using it;
- **reaction memes** (emotion pictograms, statues, “hand gestures”): a separate `memes.json` annotation next to the catalog (written by you or the agent; a catalog rebuild never touches it) with description, emotion and “when it fits”. Then a meme is found by the meaning of the line (“the candidate didn't understand the question” → a figure with question marks), and its rights by the catalog verdict (`references/inserts.md`, “Memes”).

**Icons:** flat pictograms are the safest option; service logos only when the service is named in the speech or the CTA; `{{FORBIDDEN_IMAGES}}`, real celebrities, politicians, film stills and meme stills are a no. One icon at a time, 180–320 px, not on the face. Copy **only the chosen files** into Remotion's `public/`, and compress large PNGs. Green background → `chromakey=0x00FF00:0.18:0.06,despill=type=green,format=yuva420p` into WebM VP9 with alpha; black background → `mixBlendMode: "screen"`.

An icon supports the thesis; it does not repeat the subtitle word for word. One icon style per video: don't mix flat pictograms with 3D or collage; collage-style icons only in the “Editorial” style. Pictograms: white over video, black on a light card. Neon or glowing icons break the “no glow” rule: only in the “Glass” style. Shrink large PNGs to about 2× their on-screen size. A green fringe after chroma keying → raise the second `chromakey` value by 0.02–0.04 and check a still again; on black, `mixBlendMode: "screen"` or `colorkey=0x000000:0.1:0.05`. A GIF becomes a WebM VP9 with alpha the same way (`format=yuva420p`, without `chromakey`).

**No sounds of your own yet?** A starter pack of 260 short CC0 sound effects (hits, whooshes, clicks, UI sounds, typing; Kenney and an OpenGameArt keyboard pack, commercial use without attribution) is in the repository's releases: https://github.com/itpartypattaya/reels-montage/releases/tag/sfx-cc0-1 (`it-reelsmaker-sfx-cc0.zip`, 2 MB, with `LICENSE.txt`). The person downloads it and unpacks the `cc0-sfx` folder into `{{ASSETS_DIR}}` (the plugin never downloads anything itself); then run `library_catalog.py`, and a folder rule `"cc0-sfx": ["ok", "CC0"]` in `verdicts.json` marks the whole pack. Bright game-like sounds from it (`casino/`, glitches) are still “caution” by taste.

**Sounds for events:** the Remotion kit does not play the scenes' `sound`; list the chosen files in `edit/<id>/sfx.json` (`{"sounds": [{"file": …, "at": <second of the video>, "start": <sound start from the catalog>, "what": …}]}`; `at` from the plan: the scene's start, its spoken word, a tap's time) and master with `master_audio.py --sfx edit/<id>/sfx.json`: they are mixed in before the voice chain, 15 dB under the voice peak.

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

**Music: license first.** ⟨YOURS: `{{ACCOUNT_TYPE}}`⟩. An Instagram business account only has access to the royalty-free Meta Sound Collection library in the app, and a track burned into the video must have a **commercial** license. Commercial tracks, slowed/reverb versions of other people's songs, files from download sites: do not burn them in. A safe default: render without music and pick the track in the app when publishing. A “check license” verdict is not a permission: open the track's page and check commercial use and attribution; a license written for one platform's audio library must be read separately for other platforms.

## Music in the mix

**Music, if burned in** (not yet verified in a finished video; listen to the whole master before delivery):
- mix music only with `master_audio.py`, never inside Remotion: Remotion has no sidechain, so a static bed either buries the voice or disappears;
- **duck the music under the key line**: the phrase before the CTA or the punchline goes out in near silence, `master_audio.py … --duck 21.3-23.9` (seconds of the render, −14 dB by default, `:-20` for deeper, 0.2 s fades; repeatable), applied to the music only; match the music's tempo to the pace of the edit;
- set the level **by the gap to the voice**, not by a percentage of track volume: a 15 dB gap → bed at −24 LUFS (13 → −22, 17 → −26);
- sidechain on the voice: `sidechaincompress=threshold=0.10:ratio=3:attack=20:release=380`;
- trap: `sidechaincompress` outputs about a second less than it received, so the final hit silently disappears. `apad` both inputs, `atrim` the output, check the duration;
- `amix` only with `normalize=0`, otherwise the voice quietly drops;
- **cut the track to the meaning**: find **the track's drop**, its loud moment (the sharpest rise in short-term loudness over 1.5 s, not in the first 4 s: `--find-drops`), and land it on the final phrase: `--drop-at <phrase second> --drop-in-track <drop second>` (offset = drop time − phrase time). Not the same as ducking: the drop is the music getting louder where the track does, the duck is the music held down under a line;
- bring the final mix to −14 LUFS again.
