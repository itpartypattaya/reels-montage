# Changelog

What changed in IT Reelsmaker, written for the people who use it. The newest version is on top. The skill shows a short “What's new” note from this file once, on the first edit after an update.

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
