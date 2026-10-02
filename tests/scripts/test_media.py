"""Scripts that work on video and sound: rough cut, speech mask, mastering, cover frame. Synthetic media only."""
import json

from conftest import make_speech, make_video, needs_ffmpeg, needs_pillow, probe_streams, run_script, write_json

TRANSCRIPT = {"words": [
    {"text": "Hello", "start": 0.5, "end": 0.9, "type": "word"},
    {"text": " ", "start": 0.9, "end": 1.0, "type": "spacing"},
    {"text": "recruter", "start": 1.0, "end": 1.6, "type": "word"},
    {"text": "all", "start": 2.0, "end": 2.3, "type": "word"},
    {"text": "gap", "start": 3.05, "end": 3.2, "type": "word"},
    {"text": "tail", "start": 4.5, "end": 5.2, "type": "word"},
    {"text": "end", "start": 6.0, "end": 6.4, "type": "word"}]}


def cut_project(project, look=None):
    make_video(project / "IMG_4821.MOV", 720, 1280, 8.0)
    make_video(project / "IMG_4822.MOV", 1080, 1920, 5.0, audio=False, color="blue")
    e = project / "edit" / "4821"
    write_json(e / "transcripts" / "IMG_4821.json", TRANSCRIPT)
    cut = {"fps": 30, "speed": 1.2,
           "sources": {"main": {"file": "IMG_4821.MOV"}, "side": {"file": "IMG_4822.MOV", "speed": 1.0}},
           "ranges": [{"source": "main", "start": 0.4, "end": 3.0, "beat": "hook"},
                      {"source": "side", "start": 1.0, "end": 2.5, "beat": "angle"},
                      {"source": "main", "start": 4.4, "end": 6.6, "beat": "end"}],
           "fix": {"recruter": "recruiter"}, "fix_at": [{"text": "all", "at": 2.0, "to": "everything"}],
           "retime": [{"text": "Hello", "at": 0.5, "start": 0.45, "end": 0.95}],
           "extract": {"broll_x": {"source": "main", "start": 7.0, "end": 7.8}}}
    if look:
        cut["look"] = look
    write_json(e / "cut.json", cut)
    return e


@needs_ffmpeg
def test_cut_dry_run_counts_words(project):
    cut_project(project)
    r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project)
    assert "segments 3, words 5 of 6, total 5.5 s" in r.stdout
    assert not (project / "edit" / "4821" / "final.mp4").exists()


@needs_ffmpeg
def test_cut_builds_a_clean_rough_cut(project):
    from conftest import ffmpeg
    ffmpeg("-f", "lavfi", "-i", "haldclutsrc=8", "-frames:v", "1", project / "hald.png")
    e = cut_project(project, {"correct": "colorbalance=rs=-0.02", "lut": "hald.png", "lut_mix": 0.6, "grade": "eq=contrast=1.05"})
    run_script("cut.py", "edit/4821", cwd=project)
    st = probe_streams(e / "final.mp4")
    v, a = st["video"], st["audio"]
    assert (v["width"], v["height"]) == (1080, 1920)  # a 720x1280 source is scaled
    assert float(v["start_time"]) == 0 and float(a["start_time"]) == 0
    assert abs(float(v["duration"]) - 5.5) < 0.034 and abs(float(a["duration"]) - float(v["duration"])) < 0.034
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    assert [w["text"] for w in cap["words"]] == ["Hello", "recruiter", "everything", "tail", "end"]
    assert cap["words"][0]["start"] == 0.042  # retimed 0.45 -> (0.45 - 0.4) / 1.2
    assert [g["out_start"] for g in cap["segments"]] == [0.0, 2.167, 3.667]
    edl = json.loads((e / "edl.json").read_text(encoding="utf-8"))
    assert [r["source"] for r in edl["ranges"]] == ["main", "side", "main"] and edl["speeds"]["side"] == 1.0
    assert (e / "broll_x.mp4").is_file() and "audio" not in probe_streams(e / "broll_x.mp4")


@needs_ffmpeg
def test_cut_rejects_a_range_from_an_unknown_source(project):
    e = cut_project(project)
    cut = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    cut["ranges"][0]["source"] = "nope"
    write_json(e / "cut.json", cut)
    r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project, check=False)
    assert r.returncode != 0 and "not in sources" in r.stderr


@needs_ffmpeg
def test_speech_mask_finds_phrases_and_prints_cut_ranges(project):
    make_speech(project / "a.wav", [(0.5, 2.0), (2.6, 4.5)], 6)
    r = run_script("speech_mask.py", "a.wav", "--spans", "0.3-4.8", "--json", cwd=project)
    data = json.loads(r.stdout.strip().splitlines()[-1])
    (s1, e1), (s2, e2) = data["ranges"]
    assert abs(s1 - 0.48) < 0.05 and abs(e1 - 2.03) < 0.06 and abs(s2 - 2.58) < 0.06 and abs(e2 - 4.53) < 0.06
    r = run_script("speech_mask.py", "a.wav", "--spans", "0.3-4.8", cwd=project)
    assert '"ranges": [' in r.stdout and '"beat": ""' in r.stdout


@needs_ffmpeg
def test_master_audio_hits_the_loudness_target(project):
    make_video(project / "render.mp4", 360, 640, 6.0)
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    r = run_script("master_audio.py", "master.mp4", "--check", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr


@needs_ffmpeg
@needs_pillow
def test_poster_bake_replaces_only_frame_zero(project):
    from PIL import Image
    make_video(project / "render.mp4", 1080, 1920, 3.0)
    Image.new("RGB", (1080, 1920), (200, 30, 30)).save(project / "cover.jpg")
    r = run_script("poster.py", "bake", "render.mp4", "--cover", "cover.jpg", "-o", "baked.mp4", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    before, after = probe_streams(project / "render.mp4"), probe_streams(project / "baked.mp4")
    assert abs(float(before["video"]["duration"]) - float(after["video"]["duration"])) < 0.001
