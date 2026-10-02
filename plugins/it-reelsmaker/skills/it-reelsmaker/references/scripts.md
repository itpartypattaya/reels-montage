# Scripts: which one for which step

The plugin ships Python scripts for every repeatable step. **Run them; don't rewrite them for a video.** Everything
that differs between videos lives in JSON files of the video (`edit/<id>/cut.json`, `reel.json`, `visual_plan.json`),
not in code. Each script prints its full help with `--help`.

## How to run

```bash
cd {{PROJECT_ROOT}}
python "${CLAUDE_SKILL_DIR}/scripts/<name>.py" <command> [args]
```

- Use `python3` where `python` is Python 2 or missing; on Windows `py -3` also works. Python 3.9+ and ffmpeg/ffprobe
  in PATH. Pillow (`pip install Pillow`) for contact sheets, covers, brand logos and meme previews; OpenCV
  (`pip install opencv-python-headless`) only for face measurement.
- Run from the project folder: the scripts find it as the current folder or above (the nearest folder with `edit/` or
  `brands/`, or `it-reelsmaker.json -> project_root`), or from `REELS_PROJECT`. `edit/<id>` arguments are relative to it.
- The scripts write only into the project (and the Remotion project you name), never into the plugin folder.
- Exit codes: `0` done (warnings start with an exclamation mark and don't stop the edit); `1` a check failed (plan errors, a
  rough cut whose video and audio don't line up, a master that missed the target): fix it before going on.
- Several sessions in one project are safe: shared JSON is written atomically under a lock.

## By step

| Step | Script | Commands |
|---|---|---|
| 0 | `doctor.py` | the environment in one command: what is missing and the install command for this OS (exit 1 if a required program is missing) |
| 0 | `brand.py` | `list`, `show <slug>`, `new --name … --colors … [--tone …]`, `logo`, `rule`, `set`, `tone <slug> <preset>`, `use <slug> --edit edit/<id>`, `export <slug> --remotion <dir>` |
| 0 | `reelcfg.py` | `show edit/<id> [--json]` (settings, where each comes from, what will actually turn on and why not); `save edit/<id> --set key=value …` |
| 2, 3 | `transcribe.py` | `edit/<id> <source> [--model medium] [--language ru]` (faster-whisper, cached in `transcripts/`); `snip edit/<id> <source> --from … --to …` (a <= 5 s piece without context, for retakes); `check <file>` (your own transcriber's output) |
| 3, 6 | `speech_mask.py` | `<audio.wav> --spans 0.5-4.6,4.7-9.6 [--density natural]` (edges by audio → `"ranges"` for `cut.json`); `--edl edit/<id>/edl.json` (check every edge of the rough cut, exit 1 on warnings) |
| 6 | `cut.py` | `edit/<id> --dry-run` (segments, lengths, words), then `edit/<id>` → `final.mp4`, `captions.json`, `edl.json`; the cut list format is in `--help` |
| 6, 8, 9 | `faces.py` | `scan edit/<id>`, `zones edit/<id> [--cam z,cx,cy]`, `check edit/<id> --box x,y,w,h --from … --to …`, `audit out/<render>.mp4 --edit edit/<id>`; the model path via `--model {{FACE_MODEL}}` or `face_model` in `it-reelsmaker.json` |
| 7a | `visual_plan.py` | `init`, `add` (B-roll, meme, designed scene), `keep-clear`, `validate` (exit 1 on errors), `md` (the table for the person), `export --remotion <dir>` |
| 7a | `footage.py` | `index` + `describe` (the project's own footage), `search`, `plan-search edit/<id>`, `pick edit/<id> <insert>`, `prepare` |
| 7a | `codescene.py` | `manifest`, `validate`, `scaffold edit/<id> <insert> --remotion <dir>`, `render …`, `ingest edit/<id>` |
| 7a | `memes.py` | `index`, `set`, `search`, `prepare`, `place edit/<id> <insert>` |
| 8 | `matte.py` | `cut edit/<id> --from … --to … [--width 720] [--dry]` (figure cut-out on this computer with your rembg → WebM with alpha, edge data, check frame); `place edit/<id> --name host --layout review` (presenter layout) |
| 8 | `phone_screen_rect.py` | `<frame.png> [width]`: the screen rectangle of a phone mockup |
| 9 | `patch_render.py` | `out/<render>.mp4 --comp Reel<id> --from 12.3 --to 13.1`: re-render and splice a segment (late spot fixes) |
| 9 | `poster.py` | `pick edit/<id> --render out/x.mp4 -o cover.jpg`, `guide cover.jpg -o cover-guide.png`, `bake out/x.mp4 --cover cover.jpg -o out/x-cover.mp4` (cover in frame 0) |
| 9 | `master_audio.py` | `out/render.mp4 -o out/master.mp4 [--music track.mp3]`, `--check`, `--find-drops` |
| 11 | `library_catalog.py` | `--dir {{ASSETS_DIR}}`: catalog, overview sheets and verdicts of your own asset library |
| — | `addon.py` | runs the commands of the online-sources add-on, if it is installed and linked (`addon.py` alone lists them) |

## The rough cut list (`edit/<id>/cut.json`)

```json
{
 "speed": 1.15,
 "sources": {"main": {"file": "IMG_4821.MOV"}},
 "look": {"lut": "brand", "lut_mix": 0.6, "grade": "eq=contrast=1.05:saturation=1.04"},
 "ranges": [{"start": 1.567, "end": 12.967, "beat": "hook"}, {"start": 14.767, "end": 20.767, "beat": "the answer"}],
 "fix": {"Akme": "Acme"},
 "retime": [{"text": "shortlist", "at": 16.16, "start": 16.10, "end": 16.62}]
}
```

`ranges` come from `speech_mask.py` (it prints them in this form). Two cameras: two `sources`, each with its own
`speed`, and `"source"` in every range. Cutaways from the same footage: `"extract": {"broll_view": {"start": 36.5,
"end": 41.5}}`. Transcription fixes go into `fix` (every occurrence) or `fix_at` (one occurrence near a second).

## What the scripts don't do

The Remotion composition code (camera, graphics, subtitles: `references/camera.md`, `references/scenes.md`) is
written by the agent per video. A different transcriber is fine: its output only has to pass `transcribe.py check`.

Audio extraction writes `edit/<id>/audio16k-<source stem>.wav` for each source, with source identity metadata next to it. Pass that WAV to `speech_mask.py`. Older projects may still use `audio16k.wav` as a legacy input; new transcriptions never reuse it. Cut ranges must be finite, inside the source (one frame of end tolerance), and contain at least one output frame. Segment output sizes must match; SAR is normalized to 1:1. Extract and matte names must be safe local names.
