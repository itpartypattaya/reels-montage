# Changelog

What changed in IT Reelsmaker, written for the people who use it. The newest version is on top. The skill shows a short “What's new” note from this file once, on the first edit after an update.

## 1.6.0

- **How the video starts and ends is now offered, not assumed.** Before the cut plan the skill reads the transcript
  for strong lines and offers 2–3 structure variants with their length and risk: in order, without the slow start,
  or a **teaser** (a strong line from later plays first, then the video from its start), and an ending on the payoff,
  a call to action or a logo. A skit or a dialogue always gets a teaser option. Before, the skill knew “a skit opens
  with its most controversial line” but never proposed it.
- `structure.py suggest` marks the lines that can open the video, checks by the audio which of them can be cut out
  cleanly and gives their exact cut edges; it also warns when a teaser would give the punchline away.
- **An earlier edit of the same source is found**: `structure.py history` shows what was chosen then.
- The menu of structure mechanics (`references/structure.md`): teaser, cutting the slow start, proof first, a beat
  before the punchline, re-hook, ending on the payoff with a hold, callback, loop, and a 20–30 s video in beats.
- **Videos no longer come out too warm after the brand look.** The color is balanced to neutral by measurement,
  before the look, in every video: `balance.py` runs frames of the cut through the same look, finds the correction
  that makes walls, white clothes and other grays neutral, shows the frames before and after and writes it into the
  cut. Before, the correction was set by eye, and a brand LUT that pulls blue down turned the whole video yellow.
- A list can now appear **over the video without shrinking the speakers** (`overlay` mode): its items show up one
  by one on their words in the free space above the heads or at the chest, and the subtitles step aside meanwhile
  (kit 1.6.0: `kit.py update`).
- Fixes: a list or other scene that shrinks the speaker now sits on the style's own field (for example a light one)
  instead of the dark primary color, where dark text vanished (kit 1.6.0: `kit.py update`); a hyphenated word split
  by the transcriber (“no-no-no”) is one word again in the subtitles.
- **A teaser is cut out whole.** Its edges are the line's first and last words, not a pause inside the line, so a
  teaser no longer starts on the last word or stops before “and so?”; a line that runs into its neighbor without
  a real pause (0.1 s) is marked as one to cut only together with it; a long question is one line, not two halves.
  `structure.py suggest --from/--to` looks for teasers and the ending inside the part of a long recording you use.
- **Cover candidates come from real pauses.** `poster.py pick --sheet` takes its frames from pauses of 0.15 s and
  longer (a 60 ms dip between words put every frame mid-word) and marks the ones that fall on speech; `--t` on
  speech warns.
- **The brand style looks like the brand** (kit 1.6.0): a full-screen phrase sits on the brand's main color, not
  the accent; the end card with a call to action shows the brand line under the logo and keeps every line out of
  the buttons column on the right; a hook over the video shows its accent word on its own plate.
- **Subtitles come back right after a scene** (kit 1.6.0), on the word being said, instead of half a second later.
- **Editing the plan without opening its file**: `visual_plan.py remove` takes an insert out, `keep-clear --remove`
  takes a graphics zone out, `visual_plan.md` lists those zones with their texts, and a hook without a variant is
  refused when it is added, not later at the check.
- `balance.py` warns when a gain sits at the edge of what it may do: the cast may need more than a balance fix,
  look at the whites and the skin.
- The face zones, the plan check and the render audit share one subtitle band; the audit checks the band the
  render really has.
- **The color fix no longer goes the wrong way on scenes full of colored light** (sky or sea through windows, neon):
  `balance.py` refuses a correction that would make a cool picture cooler and says why. For such scenes it has an
  eyedropper, `--ref`: point it at a white T-shirt, a wall or paper, and that object comes out neutral after the look.
- **Presenter over a scene**: the layout cuts in and out and only the figure moves, instead of the whole picture
  dissolving over the video; the cut-out's check frame shows the figure again; the scale message gives the real face
  size on screen; a seated speaker cut by a table gets a warning with the line to cover; the presenter's span counts
  in the inserts' budget, its own face is no longer reported as covered, and its cut-out file is copied into the
  Remotion project by the export (kit 1.6.0: `kit.py update`).
- **The light flash is the one the guide describes**: a short warm brightening centered on the cut, not a white frame
  (kit 1.6.0: `kit.py update`).
- **Two cameras**: the structure check asks which camera to analyze instead of silently taking the last transcript;
  `transcribe.py rate` measures syllables per second on the cut, per camera and per segment; camera shots may name
  their file as well as its key; the face zones never mix the two angles.
- A cutaway from your own footage gets the same color as the cut around it.
- A word only the local model heard can be removed from the subtitles (`"to": ""` in the cut list's fixes).
- Fewer false alarms: a breath at a cut edge is no longer reported as a cut consonant (a final “s” still is);
  subtitles hidden by your own composition are recorded in the plan (`visual_plan.py hide-subs`) and the face check
  knows about them. `visual_plan.md` shows the hints for each line; the list hint no longer fires on ordinary commas;
  chat bubbles are at least 40 px.
- **A teaser no longer doubles a word.** When a line from later plays first, a word the transcript stretched over the
  pause before another piece used to show up in both; now every word is shown once per pass through the source, in
  any order of the pieces (a line deliberately played twice still gets its subtitles twice). A dash the recognizer
  returns as a word joins the word before it instead of lighting up on its own.
- **Subtitles read better** (kit 1.6.0: `kit.py update`): chunks follow sentences, pauses and punctuation instead of
  a 52-character cut, a short word or a number never ends a chunk or a line; the darkening behind “Typewriter” is at
  full strength from the first frame after a scene (it used to fade in while the text was already there); the caret
  is a thin bar in the accent color, no longer a “|” that read as the letter l; a translated phrase that a scene
  covers for most of its time is hidden whole instead of showing its last words.
- **The darkening is measured**: `visual_plan.py shade` finds the value that makes “Typewriter” text readable (4.5:1)
  on the lightest frame and prints the setting; `subtitles_shade` is now a known setting.
- **Subtitle files and translations**: a one- or two-word phrase joins its neighbor (no more 0.5 s subtitles and
  one-word translations; existing translations are joined, not lost); `.srt` lines keep to 42 characters, a longer
  phrase becomes several subtitles, and a number stays with its word. A quote scene written in the subtitle language
  is checked against the translation.
- **The plan check sees the camera**: graphics over the video are checked against the face through `camera.json`,
  as the render shows it, so a box the render audit would flag is caught before the render.
- “Editorial” takes its headings in the brand's serif (`fonts.serif`) in the kit; brand names with digits are no
  longer taken for numbers; `visual_plan.py init` no longer says “inserts are off” when designed scenes are on.
- **Subtitles in each speaker's color** (kit 1.6.0: `kit.py update`). In a two-person video you say who speaks in
  the cut list (`"speaker"` per range, `"speakers"` for a switch inside one: on one microphone the speakers are told
  apart by their lips), and every subtitle mode colors the words by speaker: the first in the usual colors, the
  second in the accent, or your own colors (`colors.speakers` in the brand). Before, the guide asked for it and
  nothing could do it: a skit needed two subtitle layers in its own composition.
- **Music ducked under a key line**: `master_audio.py --duck 21.3-23.9` lowers the music (−14 dB by default) while
  the line plays and brings it back, the voice untouched. The guides now tell this apart from the track's drop, its
  loud moment placed on the final phrase.
- **A quiet word is no longer cut out silently.** A short word spoken a few dB under the speech threshold looked
  like a pause and vanished from the sound and the subtitles; the cut now names such a word (“check by ear”), and the
  speech check flags a short pause with a sound just under the threshold.
- **“Typewriter” never takes three lines** (kit 1.6.0): a phrase too long for two lines is split into two subtitles
  where it reads as two, and two lines are balanced instead of leaving one word on the second; the band recorded for
  the face check is what the kit can draw.
- **A whip's blur no longer grows with the zoom** (kit 1.6.0): it is the same short 6 px at its peak at any shot
  size (at ×1.3 it was 7.8 px). At the very end, the subtitles stay while the logo sting fades in over them
  instead of vanishing as it starts.
- Smaller fixes: the render audit flags a face cut at the side of the frame (in a skit, the other person after a
  push-in); teaser candidates leave out interjections, lines with an estimated word and broken takes, and say that
  the choice is by meaning; `balance.py` no longer says “already neutral” about grays no gain could fix; the list
  hint finds a list set off by dashes; `keep-clear` checks the face through `camera.json`; `reelcfg.py show` lists
  designed scenes; the cut length is printed rounded.
- **A cutaway made from your own video keeps its color.** A clip cut out of the source for “detail first” (`extract`
  in the cut list) is already in the cut's color; picking it as B-roll no longer applies the look a second time (a
  white wall came out pink). Such a clip is now found as project footage under any name, and its `"what"` in the cut
  list describes it.
- **The B-roll search finds what the plain search finds.** The plan's search scores each insert by its search words,
  like `footage.py search`, instead of diluting them with the long description; an insert with nothing found says
  how to try again (`plan-search --retry`, or other words with `--insert b01 --query "…"`) instead of staying skipped.
  Describing a file the index has not seen yet works, and indexing one folder no longer overwrites the project's
  shared contact sheets.
- **Structure hints fit a voice-over.** The slow-start hint looks for a strong line in the first third of the video
  only, never at its end, and a price or another number in the opening line counts as a strong start. Lines whose
  word times touch (as the local transcriber often writes them) get their clean edges from the audio's pauses: on a
  real tour 7 of 9 lines can be cut out cleanly instead of 2. Another video's notes that only share a word with the
  source (a brand of the same name) are no longer reported as an earlier edit.
- **The last 2 seconds count from the real end.** With a logo sting or an end card after the cut, a scene shortly
  before the cut's end is no longer refused: `visual_plan.py validate --sting` (or `--card`) before the export, and
  the export records it. The CTA guide says what to do when two call lines don't fit the end of a voice-over.
- **Darkening for any text zone**: `visual_plan.py shade --scene c01` (or `--zone x,y,w,h`) measures how much to
  darken under text that sits outside the subtitles, for a style your own composition draws.
- **Speech rate with prices**: numbers written in digits are left out of the syllable count and its time, so a
  segment with a price no longer reads half as fast. A short re-transcription (`transcribe.py snip`) uses a prompt in
  the video's language, so an English instruction no longer turns up in Russian text.
- Smaller fixes: the face zones say “no face in this span” instead of “shorter than the scan step” for a long span
  without a face; a meme added with its id carries its rights into the plan (no “rights unknown” before preparing
  it); `patch_render.py --props` takes a relative path; the cover pick does not warn about a face when there is none
  and widens its window when the first seconds have no pause (`--window` to set it); saving a style the brand does
  not allow warns.
- **A promo without footage flows from scene to scene** (kit 1.6.0): in the “scenes only” format one scene's text
  leaves as the next one's enters, with no empty field between them (a 22 s promo had 89 empty frames, 14–15 at
  every join; now one frame per join). The check warns when a join still leaves more than 4 empty frames, and its
  summary gives how much of the video the scenes and their text cover.
- **Its cover and its sound are finished by the plugin.** The cover pick works on a render without a sound track
  (it used to crash) and takes the settled hook frame; the cover drawn without video sits on the style's field with
  only the accent word on the marker, like the scenes (it came out on the dark color with both lines highlighted).
  A master of scene sounds over silence passes the same acceptance check later (`master_audio.py --check`) that it
  passed when it was made: no −14 LUFS target without a voice or music, the peak still checked.
- **Scenes read better on a light field** (kit 1.6.0): the focus brackets around a number and the tap on a call to
  action button are drawn in a color that stands out from the field, the tap no longer covers a letter of the
  button, and a counting number keeps its unit next to it (“6 days”, not “6   days”).
- **The plan shows and checks what the viewer reads**: scene texts in `visual_plan.md` are in full (list items were
  cut off), the caps label counts toward the reading time, any text the agent took itself (a hook, a list from the
  client's site) is marked “to verify”, a mode a scene type cannot have is refused when it is added, the `word`
  scene can fill the frame, and a `bell` sound marks a payoff or a number landing.
- **A horizontal recording in a window, drawn by the template** (kit 1.6.0: `kit.py update`). Zoom calls, webinars
  and podcasts: say `format=framed` in the video's settings (`reelcfg.py save edit/<id> --set format=framed
  label="CANDIDATE INTERVIEW"`), and `ReelKit` draws a rounded window on the style's field with the caps label above
  it, the speaker inside with the camera moving within the window, and the scenes and subtitles inside the window.
  Before, the format existed only in the face measurement: the template laid the video as a band across the middle,
  and every such video needed its own composition with a copy of the logo sting.
- **The checks see the framed video as the viewer does**: a card next to the face is checked with the camera
  where the window puts it (a shot moved toward the speaker was checked as if centered, and a face under a card
  went unnoticed); the render check no longer reports a face “cut at the side” that sits inside the window.
- **Zoom margin for a horizontal source, said right**: the window already enlarges the picture (×1.15 for 1080p,
  ×1.72 for a typical 720p Zoom), so the push-in on top is small (≈ ×1.13 at 1080p, ≤ ×1.06 at 720p); the dynamics
  come from moving the frame toward the speaker. A hook that does not fit the window's headroom can start on the
  field above the window, or stay inside it at 76 px or more.
- **No stray word at the start of a cut piece**: the tail of a removed line that only touched the piece (“…example.”)
  no longer shows in the subtitles for the first frames; a word the transcript stretched over the following pause
  stays. A line after a short pause (a quarter of a second) is no longer marked “no clean edge” by the structure
  check, and its output explains its flags (`est`, `retake?`, `unfinished`). A word whose start the transcript
  stretched back over the pause before a piece stays too, and a word the cut leaves out at an edge is named (“check
  by ear”), so none disappears without a word.
- **The framed cover matches the video** (kit 1.6.0): `ReelCover` draws the window, the label and the field, so frame 0
  no longer jumps to a full-screen layout; the corner mark on a light field is the dark one, and the label stops
  before it. `balance.py --still SECOND` writes the frame a `--ref` box is measured in (a frame grabbed from a 720p
  source is smaller than the one the box refers to).
- Smaller fixes: a teaser's cut end no longer lands 40 ms inside the last syllable on some lines; the beat after a
  line is measured by the audio where the transcript glued the pause into a word; a dash token no longer counts as a
  word; `structure.py` keeps to the source cut.json names and skips a broken cut.json in another folder; a short
  re-transcription takes the language code of any transcriber (“rus”, “en-US”); the render audit no longer reports a
  face cut at the side under B-roll or a cutaway; picking project footage goes on without the look when the raw
  source has moved; the burned-in subtitles and the `.srt` break lines by the same short words; translated subtitles
  are rebuilt when only the speakers change; the darkening of a framed video is measured where its subtitles go;
  a silent master mastered again with music loses its “no sound” tag, so the loudness is checked.

## 1.5.0

- **Subtitles in another language.** `subs.py` splits the speech into phrases, Claude translates them in the
  session (in the brand's voice, as short as the speech), the plugin checks the reading speed and puts the
  translation on the same rhythm as the speech; one setting (`subtitles_lang`) burns it into the video. A re-cut
  keeps the translations of the phrases that did not change.
- **Subtitle files for the platforms**: `subs.py srt` makes a `.srt` of the original or the translation.
- Languages written without spaces (Chinese, Japanese, Thai…) are shown word by word too: the translation marks the
  word boundaries. Designed scenes keep landing on the spoken words when the subtitles are translated.
- The kit is 1.5.0 (translated subtitles, words without spaces): `kit.py update` in your Remotion project.

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
