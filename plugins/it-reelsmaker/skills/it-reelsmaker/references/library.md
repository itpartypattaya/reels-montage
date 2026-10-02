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
**Work through a catalog, not by browsing files** (names like `IMG_xxxx` tell you nothing). A small script reads each file once and records:
- for audio: duration, **sound start** (how much silence there is at the start of the file — it matters), peak and mean loudness;
- for images and video: size, background (transparent / green chroma key / black / white);
- **brand verdict** (OK / caution / no + reason): a per-folder rule and per-file exceptions in a separate JSON;
- **overview sheets** of icons, 80 per sheet, with a colored verdict stripe: pick an icon by eye from the sheet;
- **reaction memes** (emotion pictograms, statues, “hand gestures”): a separate `memes.json` annotation next to the catalog with description, emotion and “when it fits”. Then a meme is found by the meaning of the line (“the candidate didn't understand the question” → a figure with question marks), and its rights by the catalog verdict (`references/inserts.md`, “Memes”).

**Icons:** flat pictograms are the safest option; service logos only when the service is named in the speech or the CTA; `{{FORBIDDEN_IMAGES}}`, real celebrities, politicians, film stills and meme stills are a no. One icon at a time, 180–320 px, not on the face. Copy **only the chosen files** into Remotion's `public/`, and compress large PNGs. Green background → `chromakey=0x00FF00:0.18:0.06,despill=type=green,format=yuva420p` into WebM VP9 with alpha; black background → `mixBlendMode: "screen"`.

**Sounds for events:**

| Event | Sound |
|---|---|
| whip, shot change, card fly-in | whoosh (on the 2–4 main ones, not on every one) |
| marker bar appears | marker |
| list item, chip | click (≤ 3–4 in a row) |
| card, document | paper |
| “Typewriter” subtitles | keyboard, quiet |
| CTA “send me a message” | phone notification |
| deadlines | clock |

No more than one effect every 2–3 s. **Place by the start of the sound, not of the file:** `Sequence from = event frame − sound start`, otherwise the hit will be late (a whoosh can start with 1.8 s of silence). Effects 12–18 dB below voice peaks; trim long tails to 0.3–0.8 s with a fade.

**Music: license first.** ⟨YOURS: `{{ACCOUNT_TYPE}}`⟩. An Instagram business account only has access to the royalty-free Meta Sound Collection library in the app, and a track burned into the video must have a **commercial** license. Commercial tracks, slowed/reverb versions of other people's songs, files from download sites: do not burn them in. A safe default: render without music and pick the track in the app when publishing.

## Music in the mix

**Music, if burned in:**
- set the level **by the gap to the voice**, not by a percentage of track volume: a 15 dB gap → bed at −24 LUFS (13 → −22, 17 → −26);
- sidechain on the voice: `sidechaincompress=threshold=0.10:ratio=3:attack=20:release=380`;
- trap: `sidechaincompress` outputs about a second less than it received, so the final hit silently disappears. `apad` both inputs, `atrim` the output, check the duration;
- `amix` only with `normalize=0`, otherwise the voice quietly drops;
- **cut the track to the meaning**: find the drop (the sharpest rise in short-term loudness over 1.5 s, not in the first 4 s) and land it on the final phrase: offset = drop time − phrase time;
- bring the final mix to −14 LUFS again.
