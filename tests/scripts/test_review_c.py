"""Group C of the 2026-11-17 review (findings 17-41): each test is the case that went wrong, run on the fixed code."""
import json
import re
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from conftest import CORE, ffmpeg, make_video, needs_ffmpeg, needs_pillow, run_script, write_json
from test_callouts import needs_node
from test_library import library
from test_longform import cards, series, words_of  # noqa: F401 (series is a fixture)
from test_media import band_db
from test_plan import captions, load_plan, plan_project
from test_transcribe import STUBS
from test_voice_over import WORDS, picture_c

KIT = CORE.parent / "assets" / "remotion-kit"


def no_traceback(r):
    return "Traceback" not in (r.stdout + r.stderr)


# --- 17-22: the cut, the sound, the transcript -----------------------------------------------------------------------

def test_a_copied_picture_starts_on_the_segments_own_frame():
    # #17: frame 38 at 30 fps is 1.26667 s, written 1.267 in src_start; the copy seeked to 1.267, past frame 38, and the
    # fps grid filled the first slot with a copy of frame 39 (seen on a source with frame numbers)
    import cut_picture
    seg = [{"i": 0, "source": "main", "src_start": 1.267, "src_end": 7.267, "out_start": 0.0, "out_dur": 6.0,
            "speed": 1.0, "_s": 38 / 30, "_e": 218 / 30, "_n": 180, "_fps": 30}]
    shots, _ = cut_picture.resolve(picture_c([{"from": 4, "to": 6, "shots": [{"source": "pic"}]}]), seg, WORDS, 6.0)
    copy = next(g for g in shots if g.get("_copy"))
    assert copy["_s"] == pytest.approx(38 / 30, abs=1e-9), copy["_s"]


@needs_ffmpeg
def test_a_track_shorter_than_the_video_fades_out_at_its_own_end(project):
    # #18: under a voice, the music faded at the video's end; a 3 s track under a 6 s video stopped dead at 3 s
    ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=360x640:r=30:d=6", "-f", "lavfi", "-i", "sine=f=300:d=6,volume=0.3",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", project / "render.mp4")
    ffmpeg("-f", "lavfi", "-i", "sine=f=3000:d=3,volume=0.5", project / "track.wav")
    r = run_script("master_audio.py", "render.mp4", "--music", "track.wav", "--no-denoise", "-o", "out.mp4",
                   cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ends after 3.0 s" in r.stdout, r.stdout
    music = "highpass=f=2000,highpass=f=2000"
    full, tail = band_db(project / "out.mp4", 1.0, 1.5, music), band_db(project / "out.mp4", 2.75, 2.95, music)
    assert tail <= full - 8, (full, tail)  # faded down before the track's end, not cut at full level


@needs_ffmpeg
def test_two_hundred_and_fifty_segments_join_into_one_sound(tmp_path):
    # #19: each piece is "-protocol_whitelist file,pipe -i <path>" plus its filter, ~190 of them passed the Windows
    # command-line limit (32767) and the cut failed; the join now runs in batches
    import cut_voice
    e = tmp_path / ("edit-with-a-long-folder-name-" * 2) / "4821"
    clips = e / "clips"
    clips.mkdir(parents=True)
    one = clips / "piece.wav"
    ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=0.1:sample_rate=48000", "-ac", "2", "-c:a", "pcm_s16le", one)
    parts = []
    for k in range(250):
        parts.append(clips / f"seg_{k:03d}_with_a_long_name.wav")
        shutil.copy(one, parts[-1])
    joined, _ = cut_voice.join_pieces(e, parts, [{"source": "a", "_n": 3, "_fps": 30}] * 250, False)
    with wave.open(str(joined)) as w:
        assert w.getframerate() == 48000 and w.getnframes() == 250 * 4800  # 250 x 0.1 s, sample-exact


def test_check_refuses_times_written_as_text(project):
    # #20: "start": "1.2" passed check (float() takes the text) and cut.py failed on it
    f = write_json(project / "t.json", {"words": [{"text": "a", "start": "0.1", "end": "0.3"}]})
    r = run_script("transcribe.py", "check", f, cwd=project, check=False)
    assert r.returncode == 1 and "not numbers" in r.stdout, r.stdout


def test_check_names_a_transcript_that_is_not_an_object(project):
    # #21: a JSON list made check fail with a traceback instead of the format error
    f = write_json(project / "t.json", [{"text": "a", "start": 0.1, "end": 0.3}])
    r = run_script("transcribe.py", "check", f, cwd=project, check=False)
    assert r.returncode == 1 and 'no "words" list' in r.stdout and no_traceback(r), r.stdout + r.stderr


@needs_ffmpeg
def test_an_asked_model_or_language_is_not_answered_from_the_cache(project):
    # #22: a transcript cached with medium was "cached" for --model small and --language ru too: nothing changed
    make_video(project / "IMG_4821.MOV", 360, 640, 3.0)
    doc = lambda: json.loads((project / "edit/4821/transcripts/IMG_4821.json").read_text(encoding="utf-8"))
    run = lambda *x: run_script("transcribe.py", "edit/4821", "IMG_4821.MOV", *x, cwd=project, env=STUBS)
    run()
    assert doc()["model"] == "faster-whisper medium int8"
    r = run("--model", "small")
    assert not r.stdout.startswith("cached") and doc()["model"] == "faster-whisper small int8", r.stdout
    assert run().stdout.startswith("cached")  # no model asked: the small one's transcript is kept, not redone
    r = run("--model", "small", "--language", "ru")
    assert not r.stdout.startswith("cached") and doc()["language_code"] == "ru", r.stdout
    assert run("--model", "small", "--language", "ru").stdout.startswith("cached")


# --- 23-29: the plan, the picture ------------------------------------------------------------------------------------

@needs_ffmpeg
@needs_pillow
def test_min_dur_holds_for_the_project_and_the_libraries(project):
    # #23: --min-dur reached only the online sources; a 2 s library clip came back for a 3 s insert
    library(project)
    run_script("library_catalog.py", cwd=project)
    make_video(project / "pool_party.mp4", 360, 640, 2.0, audio=False)
    run_script("footage.py", "index", cwd=project)
    def found(prov, d):
        out = run_script("footage.py", "search", "pool", "--providers", prov, "--min-dur", d, "--json", cwd=project).stdout
        return [c["id"] for c in json.loads(out[out.rindex("\n[") + 1:])]

    assert "clips/pool_view.mp4" in found("local", "1") and "clips/pool_view.mp4" not in found("local", "3")
    assert "pool_party.mp4" in found("project", "1") and "pool_party.mp4" not in found("project", "3")


def test_a_recut_that_drops_an_inserts_word_names_the_insert(project):
    # #24: "the word 'resume' occurs 0 time(s)" did not say which insert lost it
    e = plan_project(project, {"use_broll": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "broll", "--at", "word:resume#1", "--dur", "1.5",
               "--what", "hands with a resume", "--why", "illustrates the resume", "--source", "project", cwd=project)
    b0 = load_plan(e)["inserts"][0]
    cap = captions()
    for w in cap["words"]:
        if w["text"].lower().startswith("resume"):
            w["text"] = "summary"
    write_json(e / "captions.json", cap)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert r.returncode != 0 and b0["id"] in r.stderr and "lost the word" in r.stderr, r.stdout + r.stderr
    assert load_plan(e)["inserts"][0] == b0  # nothing saved half moved


@needs_ffmpeg
@needs_pillow
def test_a_gray_video_has_no_alpha(project):
    # #25: alpha was "an a in pix_fmt": gray, pal8 and bayer_* counted as transparent
    library(project)
    ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=320x320:r=30:d=1", "-c:v", "png", "-pix_fmt", "gray",
           project / "assets" / "clips" / "gray_pool.mov")  # png in mov keeps gray
    run_script("library_catalog.py", cwd=project)
    cat = json.loads((project / "assets" / "_catalog" / "catalog.json").read_text(encoding="utf-8"))
    files = {x["path"]: x for x in (cat["files"] if isinstance(cat, dict) else cat)}
    assert files["clips/gray_pool.mov"]["pix"] == "gray" and files["clips/gray_pool.mov"]["alpha"] is False


@needs_pillow
def test_a_smaller_index_leaves_no_old_contact_sheets(project):
    # #26: 13 files made 3 sheets; after 8 went away the index made 1 and kept the 2 old ones, showing gone files
    from PIL import Image
    photos = project / "photos"
    photos.mkdir()
    for k in range(13):
        Image.new("RGB", (120, 160), (20 * k, 80, 120)).save(photos / f"p{k:02d}.jpg")
    run_script("footage.py", "index", "--dir", "photos", cwd=project)
    sheets = lambda: sorted(p.name for p in (project / "_footage_index").glob("photos-sheet-*.jpg"))
    assert sheets() == ["photos-sheet-00.jpg", "photos-sheet-01.jpg", "photos-sheet-02.jpg"]
    for k in range(5, 13):
        (photos / f"p{k:02d}.jpg").unlink()
    run_script("footage.py", "index", "--dir", "photos", cwd=project)
    assert sheets() == ["photos-sheet-00.jpg"]


def test_use_from_zero_is_the_clips_first_frame(tmp_path, monkeypatch):
    # #27: use_from: 0 was read as "not set" and the clip started 0.3 s in
    import codescene
    import footage
    seen = []
    monkeypatch.setattr(footage, "prepare", lambda src, out, dur, start, *a, **k: seen.append(start) or {})
    e = tmp_path / "e"
    (e / "inserts").mkdir(parents=True)
    for use_from, want in ((0, 0.0), (None, 0.3), (1.5, 1.5)):
        codescene.ingest_one(e, {"id": "g1", "dur": 2.0, "gen": {"use_from": use_from, "engine": "code"}}, e / "raw.mp4")
        assert seen[-1] == want, (use_from, seen)


def test_input_typos_are_named_not_tracebacks(project):
    # #28: a letter in --box, a wrong --at, a field without "=" and a wrong meme slot ended in a traceback
    plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    r = run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "1", "--to", "2", "--box", "10,20,x,40",
                   "--what", "logo", cwd=project, check=False)
    assert r.returncode != 0 and "--box 10,20,x,40: 4 numbers" in r.stderr and no_traceback(r), r.stderr
    r = run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "1", "--to", "2", "--box", "10,20,40",
                   "--what", "logo", cwd=project, check=False)
    assert r.returncode != 0 and "4 numbers" in r.stderr and no_traceback(r), r.stderr
    r = run_script("visual_plan.py", "add", "edit/4821", "--kind", "broll", "--at", "3,5", "--dur", "1",
                   "--what", "x", "--why", "y", cwd=project, check=False)
    assert r.returncode != 0 and "--at 3,5:" in r.stderr and no_traceback(r), r.stderr
    write_json(project / "memes" / "_index.json", {"shrug": {"path": "memes/shrug.png"}})
    r = run_script("memes.py", "change", "shrug", "rights", cwd=project, check=False)
    assert r.returncode != 0 and "expected field=value" in r.stderr and no_traceback(r), r.stderr
    import meme_layout
    with pytest.raises(SystemExit) as x:
        meme_layout.slot_box("middle", 200, 200, meme_layout.layout())
    assert "--slot middle" in str(x.value.code)


@needs_pillow
def test_tags_written_as_one_string_in_a_sidecar_are_tags(project):
    # #29: "tags": "cat, fail" by hand became the tags c, a, t, f, i, l
    from PIL import Image
    memes = project / "memes"
    memes.mkdir()
    Image.new("RGB", (300, 300), (200, 200, 50)).save(memes / "oops.png")
    write_json(memes / "oops.json", {"tags": "cat, fail", "emotion": "surprise"})
    run_script("memes.py", "index", cwd=project)
    e = json.loads((memes / "_index.json").read_text(encoding="utf-8"))["oops"]
    assert {"cat", "fail"} <= set(e["tags"]) and "c" not in e["tags"] and e["emotion"] == ["surprise"], e


# --- 30-35: shared ---------------------------------------------------------------------------------------------------

def test_a_field_under_an_empty_one_is_set(project):
    # #30: lut.hald=... on a brand with "lut": null failed in set_path
    run_script("brand.py", "new", "--name", "Acme", "--colors", "#0B3D2E,#F2C14E", "--slug", "acme", cwd=project)
    f = project / "brands" / "acme" / "brand.json"
    b = json.loads(f.read_text(encoding="utf-8"))
    b["lut"] = None
    write_json(f, b)
    r = run_script("brand.py", "change", "acme", "lut.hald=assets/lut.png", cwd=project, check=False)
    assert r.returncode == 0 and no_traceback(r), r.stdout + r.stderr
    assert json.loads(f.read_text(encoding="utf-8"))["lut"]["hald"] == "assets/lut.png"


SRT = "1\n00:00:01,000 --> 00:00:03,000\nПривет, это пример\n\n2\n00:00:04,000 --> 00:00:06,000\nвторая строка\n"


@needs_ffmpeg
def test_subtitles_in_utf16_are_read_and_cp1251_is_refused(series):
    # #31: a cp1251 or UTF-16 SRT was "imported" with U+FFFD in place of every letter
    project, _, _ = series
    (project / "u16.srt").write_bytes(SRT.encode("utf-16"))
    run_script("longform.py", "import", "edit/talk", "u16.srt", cwd=project)
    cues = (project / "edit" / "talk" / "cues.json").read_text(encoding="utf-8")
    assert "Привет" in cues and "�" not in cues
    (project / "w.srt").write_bytes(SRT.encode("cp1251"))
    r = run_script("longform.py", "import", "edit/talk", "w.srt", cwd=project, check=False)
    assert r.returncode != 0 and "not UTF-8" in r.stderr and no_traceback(r), r.stderr
    assert "Привет" in (project / "edit" / "talk" / "cues.json").read_text(encoding="utf-8")  # the good import stays


@needs_ffmpeg
def test_a_series_extract_that_stopped_halfway_sets_the_series_settings_on_the_next_run(series):
    # #32: the preset made reel.json, the --set failed; the next extract saw reel.json and never set the rest
    project, _, _ = series
    write_json(project / "presets" / "weekly.json", {"settings": {"subtitles": "plate"}, "finish": None})
    m = json.loads((project / "edit" / "talk" / "longform.json").read_text(encoding="utf-8"))
    write_json(project / "edit" / "talk" / "longform.json", {**m, "preset": "weekly"})
    part = [{"from_words": "A weak candidate blames", "to_words": "and the boss.", "near": 30}]
    cards(project, [{"id": "01", "title": "method", "status": "approved", "rubric": "insight", "parts": part,
                     "settings": {"profile": "no-such-profile"}}], rubrics={"insight": {"label": "INSIGHT"}})
    run_script("longform.py", "check", "edit/talk", cwd=project)
    run_script("longform.py", "mark", "edit/talk", "01", "--as", "approved", cwd=project)
    r = run_script("longform.py", "extract", "edit/talk", "01", cwd=project, check=False)
    assert r.returncode != 0 and "unknown profile" in (r.stdout + r.stderr), r.stdout + r.stderr
    reel = project / "edit" / "talk-01" / "reel.json"
    assert json.loads(reel.read_text(encoding="utf-8"))["subtitles"] == "plate"  # the preset got in before the stop
    cards(project, [{"id": "01", "title": "method", "status": "approved", "rubric": "insight", "parts": part}],
          rubrics={"insight": {"label": "INSIGHT"}})
    run_script("longform.py", "check", "edit/talk", cwd=project)  # the card changed: checked and approved again
    run_script("longform.py", "mark", "edit/talk", "01", "--as", "approved", cwd=project)
    run_script("longform.py", "extract", "edit/talk", "01", cwd=project)
    got = json.loads(reel.read_text(encoding="utf-8"))
    assert got["label"] == "INSIGHT" and got["format"] == "framed" and got["subtitles"] == "plate", got


def test_json_saved_with_a_bom_is_read(tmp_path):
    # #33: a file saved by Notepad or PowerShell starts with a BOM, and load_json failed on it
    from reels_common import load_json
    f = tmp_path / "reel.json"
    f.write_bytes(b"\xef\xbb\xbf" + json.dumps({"brand": "acme"}).encode("utf-8"))
    assert load_json(f) == {"brand": "acme"}


def test_a_bare_id_is_the_videos_folder_not_a_footage_folder_of_that_name(project, monkeypatch):
    # #34: `4821` found the project's own folder 4821 (the shoot's footage) before edit/4821
    from reels_common import edit_dir
    (project / "4821").mkdir()
    (project / "edit" / "4821").mkdir(parents=True)
    monkeypatch.chdir(project)
    assert edit_dir("4821", project) == (project / "edit" / "4821").resolve()
    assert edit_dir("edit/4821", project) == (project / "edit" / "4821").resolve()
    assert edit_dir(str(project / "4821"), project) == (project / "4821").resolve()  # a path is still that path


def test_a_kit_newer_than_the_plugin_is_answered_with_a_plugin_update(project):
    # #35: doctor said "kit.py update", and kit.py refuses to roll a newer kit back
    run_script("kit.py", "new", "reels", cwd=project)
    ver = project / "reels" / "src" / "kit" / "version.ts"
    ver.write_text(re.sub(r'"[\d.]+"', '"99.0.0"', ver.read_text(encoding="utf-8")), encoding="utf-8")
    r = run_script("doctor.py", "--json", cwd=project, check=False)
    row = {c["name"]: c for c in json.loads(r.stdout)["checks"]}["ReelKit in the project"]
    assert not row["ok"] and "update the it-reelsmaker plugin" in row["fix"] and "kit.py" not in row["fix"].split(":")[0], row


# --- 36-37: the kit --------------------------------------------------------------------------------------------------

@needs_node
def test_the_subtitles_hide_in_the_frames_the_scene_plays(tmp_path):
    # #36: a scene at 1.01 s began on frame 30 (round), the subtitle hid from 1.01 s (frame 31): one frame of subtitle
    # over the scene's field; both now count the same frames
    code = ("const m = await import(process.argv[1]);"
            "console.log(JSON.stringify([m.sceneFrames({start: 1.01, dur: 2.0}, 30), m.sceneFrames({start: 2.0, dur: 0.01}, 30)]));")
    r = subprocess.run(["node", "--input-type=module", "-e", code, (KIT / "kit" / "series.ts").as_uri()],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [{"from": 30, "frames": 60}, {"from": 60, "frames": 1}]
    layer = (KIT / "kit" / "scenes" / "SceneLayer.tsx").read_text(encoding="utf-8")
    assert "from={sceneFrames(s, fps).from} durationInFrames={sceneFrames(s, fps).frames}" in layer
    assert "const f = sceneFrames(s, fps); return [f.from / fps, (f.from + f.frames) / fps]" in layer
    assert "sceneHideIntervals(p.scenes, offCamera, KIT_FPS)" in (KIT / "ReelKit.tsx").read_text(encoding="utf-8")


def test_an_action_without_a_time_is_left_to_the_kit(tmp_path):
    # #37: with no time the stage wrote the scene's start, and the kit tapped on frame 8 while the screen slid in
    from vp_scenes import scene_export
    base = {"id": "c01", "type": "ui", "mode": "full", "start": 4.0, "dur": 3.0, "text": {"lines": ["Try it"]}}
    sp = scene_export({**base, "interaction": {"kind": "tap", "target": [540, 900]}}, tmp_path, tmp_path / "pub", "x",
                      {"segments": []}, {"words": []}, {})
    assert "t" not in sp["interaction"], sp["interaction"]
    sp = scene_export({**base, "interaction": {"kind": "tap", "target": [540, 900], "t": 5.2}}, tmp_path,
                      tmp_path / "pub", "x", {"segments": []}, {"words": []}, {})
    assert sp["interaction"]["t"] == 5.2
