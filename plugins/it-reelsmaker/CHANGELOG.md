# Changelog

What changed in IT Reelsmaker, written for the people who use it. The newest version is on top. The skill shows a short “What's new” note from this file once, on the first edit after an update.

## 1.4.7

- Step 2 points to the online add-on's more accurate transcript (a cloud text laid onto the local word times) for
  people who have the add-on.
- Scene sounds also on a video without a voice (a promo of scenes only): onto the music or silence; a sound whose
  hit comes later in its file than its cue is trimmed to land on time.
- The visual plan follows a re-cut of the same length too, and a scene placed on a word with an offset keeps it.
- Camera shots on a cut from several cameras name their file (`"source"`); `transcribe.py audio` creates the
  transcripts folder it points to.

## 1.4.6

- **Your own transcriber gets the right audio.** `transcribe.py audio edit/<id> <source>` makes only the audio file
  on the video's timeline, with no local model. Give that file, not the video, to a transcriber of your choice: one
  that pulls the sound out of a phone video itself places every word about 0.1 s early, and cuts set by those words
  clip word endings.

## 1.4.5

- **Quiet consonants at phrase edges are kept**: the speech mask also listens to the high frequencies, so a final "s"
  or an initial "ch" (quiet in overall loudness) stays in the cut; the edge check names an edge that cuts one.
- **Word endings are no longer clipped on phone footage.** An iPhone video's sound track can start about 0.1 s after
  the picture; the audio the plugin analyzed ignored that, so every cut landed 0.1 s early and ate the end of the
  last word of each take. The analysis audio is now on the video's timeline, and a short consonant burst before a
  phrase (the "p" in a word that starts with a stop) stays in the cut.
- **Scene sounds get mixed in**: `master_audio.py --sfx edit/<id>/sfx.json` places each sound by its sound start,
  under the voice, before mastering (the template never played them).
- **The cover is not taken mid-word**: the frame comes from a pause in the speech, and `poster.py pick --sheet` shows the
  candidates so the one with open eyes can be chosen.
- **The file's thumbnail is your cover**: `poster.py attach` embeds the cover as cover art after mastering, so a file
  manager no longer shows a random frame.
- **The visual plan follows a rebuilt rough cut**: a new length and spans, and inserts placed by a word move with it.
- **The virtual camera is in the template.** Shot sizes, punch-ins and whips no longer need code of your own: list the
  shots in `edit/<id>/camera.json` (by a word, a second of the video or a source second), and the subtitles drop
  under the chin for every shot (kit 1.4.5).
- **“Typewriter” subtitles in the template**: the whole phrase, spoken words light up, a caret, a soft darkening
  behind it that you can make stronger over light clothing. Before, this mode quietly turned into “Accent”.
- **A cleaner ending**: a logo sting with the brand line (`export --sting`), a CTA card with a large main line and a
  small muted clarifier, end-card lines that never run past the frame.
- Fixes: a word stretched across a removed pause no longer shows twice in the subtitles, and short words with zero
  length no longer vanish from them; a hand held out to the side is no longer taken for a face; a code scene's clip
  length rounds up; `kit.py` ignores line endings and refuses to roll a newer project kit back to an older plugin.

## 1.4.4

- **Your own settings live in your project, not in the plugin.** `<project>/reel-defaults.json` holds your defaults
  for every video (default brand, inserts, library folders, labels in your language): `reelcfg.py defaults --set …`.
  Plugin updates never touch it; the brand profile and each video's settings still override it.
- **Brand documents next to the profile.** Besides `rules.md`, a brand folder can hold its own video guide
  (`guide.md`), its own CTA library with exact texts (`cta.md`) and any other brand documents linked from `rules.md`;
  `brand.py show` lists them, and the skill reads them before graphics and at the brief.
- Fixes: code scenes list all 8 required fields; the marker text color `ink` from the brand template now reaches the
  Remotion kit (kit 1.4.4); styles ReelKit draws itself are named; CTA, meme size, library catalog and verification
  notes filled in.

## 1.4.3

- **Transcription no longer breaks on some installs.** `transcribe.py` reads the audio itself and hands it to
  faster-whisper, so a faster-whisper and PyAV version mismatch (for example faster-whisper 1.2.1 with PyAV 19) can't
  stop it.
- Step 8 names `brand.py export` before `visual_plan.py export`.

## 1.4.2

- A starter pack of 260 CC0 sound effects (Kenney, OpenGameArt) in the repository's releases, with how to add it to
  your asset library: `references/library.md`.

## 1.4.1

- The online add-on's folder in `it-reelsmaker.json` (`online_scripts`) may start with `~` or be relative to the
  project folder; before, only a full path worked (the add-on's `link` command always wrote one).

## 1.4.0

- **The Remotion kit ships with the plugin**: `ReelKit` (rough cut, word-timed subtitles, brand, B-roll, memes,
  designed scenes, end card) and `ReelCover` (the cover still), driven by the props that `visual_plan.py export --props`
  writes. No more composition code written from scratch for every video.
- **`kit.py`**: `new <folder>` creates a starter Remotion project with the kit wired in (pinned package versions,
  `Root.tsx`, an empty registry for code scenes); `check` and `update` keep the kit in an existing project current,
  backing up any file they replace. Your `Root.tsx`, brands, plans and code scenes are never touched.
- `doctor.py` reports whether the project has the kit and whether its version matches the plugin.

## 1.3.0

- **Ready-made scripts.** The plugin now ships the tools Claude used to write for each project: the rough cut, cut edges by the sound, face measurement, the visual plan with its checks, B-roll and memes from your own folders, code scenes, brand profiles, the cover and mastering. Edits go faster and work the same way every time.
- **One cut list per video.** Segments, speed, color and transcript fixes go into one small file instead of new code. Two cameras with different speeds work too.
- **Stops on a real problem.** A rough cut whose picture and sound don't line up, a quote that isn't word for word, a master that missed the loudness target: the script stops and says what to fix.
- **Your files stay yours.** The scripts work only in your project folder and never go online.

## 1.2.0

- **Eight brand tones.** Besides premium, expert, friendly and bold there are now warm (medicine, psychology, family), story (travel, hotels, architecture), tech (software and IT) and drive (shops, launches, fitness). You see all eight with what each allows, and the skill recommends the ones that fit your field.
- **Change the brand tone any time.** Say “change the brand tone”: you pick a new one, the profile is updated and keeps everything else.
- **Older profiles update themselves.** A brand profile from 1.0 gets the expert tone, a backup copy and one line telling you what changed and how to change it.
- **Clearer reports and fewer surprises.** A worked example of the cut plan and the final report, and a table of known problems with their fixes.

## 1.1.0

- **Designed scenes.** A big hook, a verbatim quote, the main thought as a punch, a number with a counter, a list item by item, before and after, a message thread, an interface with a cursor, the call to action as an action, and a cover. They are drawn in your brand's colors, land on the spoken word and keep the speaker's face in frame by default.
- **Brand tone.** When you create a brand, pick premium, expert, friendly or bold. The tone sets which memes are allowed, how many cutaways a video gets and how loud the effects can be.
- **A promo without footage.** A 15–25 second video made of scenes only, with your brand profile, end card and mastering.
- **Text you can read.** On-screen text stays long enough to read, quotes are checked word for word against the transcript, and every number needs a source. Optional cover in frame 0 and a post caption.
- **Your language.** The skill talks to you in your language, including its fixed labels and questions; text in the video follows the language of the video.
- **What's new.** After an update, this note appears once on your first edit.

## 1.0.0

- First release in the Claude plugin directory: cut pauses and retakes by the sound, virtual camera and on-brand graphics in Remotion, word-timed subtitles, face-aware layout, optional B-roll, code scenes and memes, mastering to −14 LUFS and a 1080×1920 render.
