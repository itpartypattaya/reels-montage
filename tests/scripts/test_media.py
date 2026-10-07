"""Scripts that work on video and sound: rough cut, speech mask, mastering, cover frame. Synthetic media only."""
import json
import subprocess

from conftest import ffmpeg, make_speech, make_video, needs_ffmpeg, needs_pillow, probe_streams, run_script, write_json

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
def test_cut_removes_a_word_with_an_empty_fix(project):
    # T2: a word only the local model heard ("you" in "that you will close") could not be taken out of the subtitles:
    # fix and fix_at only replaced words
    import cut
    e = cut_project(project)
    doc = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    doc["fix_at"].append({"text": "recruter", "at": 1.0, "to": ""})
    write_json(e / "cut.json", doc)
    r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project)
    assert "words 4 of 6" in r.stdout
    c = cut.load_cut(e, project)
    _, caps, _ = cut.timeline(c, cut.load_words(c))
    assert [w["text"] for w in caps] == ["Hello", "everything", "tail", "end"]
    doc["fix"] = {"tail": ""}  # every occurrence
    write_json(e / "cut.json", doc)
    c = cut.load_cut(e, project)
    assert [w["text"] for w in cut.timeline(c, cut.load_words(c))[1]] == ["Hello", "everything", "end"]


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
def test_a_plosive_burst_before_a_phrase_stays_in_the_cut(project):
    # "Podpisyval": a 40 ms "P" burst, a 120 ms closure, then the vowel; min_run alone dropped the burst and the
    # edge cut the consonant off. The burst belongs to the phrase that follows it.
    make_speech(project / "p.wav", [(1.0, 1.04), (1.16, 2.5)], 4)
    r = run_script("speech_mask.py", "p.wav", "--spans", "0.6-3.0", "--json", cwd=project)
    (s, e), = json.loads(r.stdout.strip().splitlines()[-1])["ranges"]
    assert abs(s - 0.98) < 0.04 and abs(e - 2.53) < 0.06

@needs_ffmpeg
def test_master_audio_hits_the_loudness_target(project):
    make_video(project / "render.mp4", 360, 640, 6.0)
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    r = run_script("master_audio.py", "master.mp4", "--check", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr


@needs_ffmpeg
@needs_pillow
def test_master_with_cover_is_one_file_with_its_cover_next_to_it(project):
    # The cover used to be four optional steps after the master and a second "-final.mp4", and it was forgotten:
    # --cover builds the master with frame 0 = the cover and the cover art inside, and puts the jpg next to it
    import subprocess
    from PIL import Image
    make_video(project / "render.mp4", 360, 640, 3.0)
    Image.new("RGB", (1080, 1920), (200, 30, 30)).save(project / "cover.jpg")
    r = run_script("master_audio.py", "render.mp4", "-o", "out/acme-tip-20261007-master.mp4", "--cover", "cover.jpg",
                   cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    master = project / "out" / "acme-tip-20261007-master.mp4"
    assert (project / "out" / "acme-tip-20261007-cover.jpg").is_file()
    assert not list((project / "out").glob("*final*"))
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:stream_disposition=attached_pic",
                          "-of", "json", str(master)], capture_output=True, text=True).stdout
    assert [s["disposition"]["attached_pic"] for s in json.loads(out)["streams"]] == [0, 0, 1]
    before, after = probe_streams(project / "render.mp4"), probe_streams(master)
    assert abs(float(before["video"]["duration"]) - float(after["video"]["duration"])) < 0.001
    from conftest import ffmpeg
    for n in (0, 1):  # the video stream itself (-map 0:v:0), not the 1080x1920 cover art ffmpeg would pick by size
        ffmpeg("-i", master, "-map", "0:v:0", "-vf", rf"select='eq(n\,{n})'", "-fps_mode", "passthrough", "-frames:v", "1",
               project / f"f{n}.png")
    red = lambda n: Image.open(project / f"f{n}.png").convert("RGB").resize((1, 1)).getpixel((0, 0))
    assert red(0)[0] > 150 and red(0)[1] < 90  # frame 0 is the red cover
    assert not (red(1)[0] > 150 and red(1)[1] < 90)  # frame 1 is the render
    r = run_script("master_audio.py", str(master), "--check", cwd=project, check=False)
    assert r.returncode == 0 and "cover art: embedded" in r.stdout, r.stdout + r.stderr
    # remastering from the sidecar itself (PR review: ffmpeg refused to write its own input)
    side = project / "out" / "acme-tip-20261007-cover.jpg"
    size = side.stat().st_size
    r = run_script("master_audio.py", "render.mp4", "-o", "out/acme-tip-20261007-master.mp4", "--cover", str(side),
                   cwd=project, check=False)
    assert r.returncode == 0 and "kept as it is" in r.stdout and side.stat().st_size == size, r.stdout + r.stderr
    # without a cover: made as before, with a warning
    r = run_script("master_audio.py", "render.mp4", "-o", "plain.mp4", cwd=project, check=False)
    assert r.returncode == 0 and "no cover" in r.stdout
    r = run_script("master_audio.py", "render.mp4", "-o", "x.mp4", "--cover", "missing.jpg", cwd=project, check=False)
    assert r.returncode != 0 and not (project / "x.mp4").exists()


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


@needs_ffmpeg
@needs_pillow
def test_poster_attach_embeds_cover_art_without_reencoding(project):
    # A file manager showed a random B-roll frame as the thumbnail: the cover goes into the file as cover art.
    import subprocess
    from PIL import Image
    make_video(project / "master.mp4", 360, 640, 2.0)
    Image.new("RGB", (1080, 1920), (200, 30, 30)).save(project / "cover.jpg")
    r = run_script("poster.py", "attach", "master.mp4", "--cover", "cover.jpg", "-o", "final.mp4", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:stream_disposition=attached_pic",
                          "-of", "json", str(project / "final.mp4")], capture_output=True, text=True).stdout
    assert [s["disposition"]["attached_pic"] for s in json.loads(out)["streams"]] == [0, 0, 1]
    before, after = probe_streams(project / "master.mp4"), probe_streams(project / "final.mp4")
    assert before["video"]["duration"] == after["video"]["duration"]


@needs_ffmpeg
def test_poster_cover_frame_is_taken_in_a_pause(project):
    # A face caught mid-word is distorted: the cover frame comes from a pause of the render's speech.
    import poster
    from conftest import ffmpeg
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=3", "-f", "lavfi",
           "-i", "sine=f=300:d=3,volume='if(between(t,1.6,1.9),0,1)':eval=frame", "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", project / "r.mp4")
    t, why = poster.in_pause(project / "r.mp4", 0.5, 2.8, "test")
    assert 1.65 <= t <= 1.85 and "pause" in why
    assert len(poster.candidates(project / "r.mp4", 0.5, 2.8)) >= 3


@needs_ffmpeg
def test_poster_a_dip_between_words_is_not_a_pause(project):
    # T1: 60 ms dips counted as pauses, all six --sheet candidates fell mid-word and --t on speech gave no warning.
    # A pause is a gap of the speech mask of at least 0.15 s (the pause-compression floor).
    import math
    import struct
    import wave
    import poster
    from conftest import ffmpeg
    rate, dur = 16000, 3.0
    on = lambda t: not (1.00 <= t < 1.06 or 1.60 <= t < 1.95)  # a 60 ms dip, then a 350 ms pause
    with wave.open(str(project / "a.wav"), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 300 * k / rate)) if on(k / rate) else 0)
                               for k in range(int(dur * rate))))
    ffmpeg("-f", "lavfi", "-i", f"testsrc2=size=360x640:rate=30:duration={dur}", "-i", project / "a.wav",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", project / "r.mp4")
    ps, _ = poster.pauses(project / "r.mp4", 0.5, 2.8)
    assert len(ps) == 1 and 1.55 <= ps[0][0] <= 1.7 and 1.85 <= ps[0][1] <= 2.0, ps
    cs = poster.candidates(project / "r.mp4", 0.5, 2.8)
    assert sum(ok for _, ok in cs) == 1 and next(t for t, ok in cs if ok) > 1.6
    (project / "edit" / "0001").mkdir()
    r = run_script("poster.py", "pick", "edit/0001", "--render", project / "r.mp4", "--t", "1.03", "-o",
                   project / "c.jpg", cwd=project)
    assert "--t 1.03 falls on speech" in r.stderr and "nearest pause" in r.stderr
    r = run_script("poster.py", "pick", "edit/0001", "--render", project / "r.mp4", "--t", "1.78", "-o",
                   project / "c.jpg", cwd=project)
    assert "falls on speech" not in r.stderr


@needs_ffmpeg
def test_poster_without_faces_and_without_a_pause_early(project):
    # T5: a voice-over (no face in any frame) got "the face may be caught mid-word", and with no hook scene the
    # candidates were looked for in 0.5-3.0 s only, all on speech. The face warning needs a face near that second;
    # with no pause in 0.5-3.0 s the window widens to 0.5-8.0 s
    from conftest import ffmpeg
    from faces import FILTER_V
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=7", "-f", "lavfi",
           "-i", "sine=f=300:d=7,volume='if(between(t,4.6,5.4),0,1)':eval=frame", "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", project / "r.mp4")
    e = project / "edit" / "0001"
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": FILTER_V},
                                  "samples": [{"t": k * 0.25, "faces": []} for k in range(28)]})
    r = run_script("poster.py", "pick", "edit/0001", "--render", project / "r.mp4", "--t", "2.0", "-o",
                   project / "c.jpg", cwd=project)
    assert "mid-word" not in r.stderr
    r = run_script("poster.py", "pick", "edit/0001", "--render", project / "r.mp4", "-o", project / "c.jpg", cwd=project)
    t = float(r.stdout.split("cover: frame at ")[1].split(" s")[0])
    assert 4.6 <= t <= 5.4 and "widened to 0.5" in r.stdout, r.stdout
    r = run_script("poster.py", "pick", "edit/0001", "--render", project / "r.mp4", "--sheet", project / "s.jpg",
                   cwd=project)
    assert "widened to 0.5" in r.stdout and "(on speech)" in r.stdout and "mouth" not in r.stdout
    # a face near the second: the warning stays
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": FILTER_V},
                                  "samples": [{"t": k * 0.25, "faces": [[300, 400, 200, 260, 0.9]]} for k in range(28)]})
    r = run_script("poster.py", "pick", "edit/0001", "--render", project / "r.mp4", "--t", "2.0", "-o",
                   project / "c.jpg", cwd=project)
    assert "the face may be caught mid-word" in r.stderr


@needs_ffmpeg
def test_voiceless_ending_stays_in_the_cut(project):
    # A final "s": quiet overall (under the threshold), loud in the high band. The phrase must end after it.
    from conftest import ffmpeg
    ffmpeg("-f", "lavfi", "-i", "sine=f=300:d=4,volume='if(between(t,1,2),1,0)':eval=frame",
           "-f", "lavfi", "-i", "anoisesrc=d=4:c=white:a=0.02,highpass=f=4000,volume='if(between(t,2,2.15),1,0.02)':eval=frame",
           "-filter_complex", "[0][1]amix=inputs=2:normalize=0", "-ar", 16000, "-ac", 1, project / "s.wav")
    r = run_script("speech_mask.py", "s.wav", "--spans", "0.6-3.0", "--json", cwd=project)
    (s, e), = json.loads(r.stdout.strip().splitlines()[-1])["ranges"]
    assert e >= 2.15, e


@needs_ffmpeg
def test_master_audio_mixes_scene_sounds(project):
    # The kit does not play scene sounds: master_audio --sfx mixes them in before the voice chain.
    from conftest import ffmpeg
    make_video(project / "render.mp4", 360, 640, 4.0)
    ffmpeg("-f", "lavfi", "-i", "sine=f=1500:d=0.3", project / "hit.wav")
    write_json(project / "sfx.json", {"sounds": [{"file": "hit.wav", "at": 2.0, "what": "test"}]})
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", "--sfx", "sfx.json", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "scene sounds: 1" in r.stdout and "hit.wav at 2.00 s" in r.stdout


def onset_s(path, thr=-30.0):
    """The first 10 ms window above thr dBFS in a file's audio, in seconds."""
    import math
    import subprocess
    import wave
    from array import array
    w = path.with_suffix(".probe.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", str(w)], check=True)
    with wave.open(str(w), "rb") as f:
        data = array("h", f.readframes(f.getnframes()))
    for k in range(0, len(data) - 160, 160):
        rms = math.sqrt(sum(v * v for v in data[k:k + 160]) / 160) / 32768
        if rms > 0 and 20 * math.log10(rms) > thr:
            return k / 16000
    return None


@needs_ffmpeg
def test_scene_sounds_on_a_silent_render_and_a_late_sound_start(project):
    # review of #8: a render with no voice skipped --sfx; a sound whose start in its file is later than its cue landed late
    from conftest import ffmpeg
    make_video(project / "render.mp4", 360, 640, 4.0, audio=False)
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-f", "lavfi", "-i", "sine=f=1500:d=0.3",
           "-filter_complex", "[0]atrim=0:1[s];[s][1]concat=n=2:v=0:a=1", project / "late.wav")  # the hit at 1.0 s
    write_json(project / "sfx.json", {"sounds": [{"file": "late.wav", "at": 0.5, "start": 1.0, "what": "hook"}]})
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", "--sfx", "sfx.json", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "scene sounds: 1" in r.stdout and "onto silence" in r.stdout
    t = onset_s(project / "master.mp4")
    assert t is not None and abs(t - 0.5) < 0.05  # the file's head trimmed: the hit lands on its cue
    # Codex review: three loud hits in phase over silence add up past 0 dBFS; the limiter and the true-peak check hold
    from conftest import ffmpeg as ff
    ff("-f", "lavfi", "-i", "sine=f=1000:d=0.3,volume=0.9", project / "loud.wav")
    write_json(project / "sfx.json", {"sounds": [{"file": "loud.wav", "at": 1.0, "gain_db": 0} for _ in range(3)]})
    r = run_script("master_audio.py", "render.mp4", "-o", "master2.mp4", "--sfx", "sfx.json", cwd=project, check=False)
    assert r.returncode == 0 and "true peak" in r.stdout and "→ OK" in r.stdout, r.stdout + r.stderr


@needs_ffmpeg
def test_project_broll_gets_the_rough_cut_look(project):
    # T2: a cutaway from the same shoot (pick) came out without the rough cut's balance and LUT, a different color
    # from the cut around it; prepare --grade ran before the LUT, so it could not be used for the look either
    e = project / "edit" / "5000"
    for name in ("IMG_5000.MOV", "IMG_5001.MOV"):  # the speaker and a cutaway of the same shoot, the same color
        make_video(project / name, 360, 640, 2.0, color="0x8C7864")
    ffmpeg("-f", "lavfi", "-i", "haldclutsrc=8", "-vf", "colorchannelmixer=bb=0.8", "-frames:v", "1", project / "cool.png")
    write_json(e / "cut.json", {"fps": 30, "sources": {"main": {"file": "IMG_5000.MOV"}},
                                "look": {"correct": "colorchannelmixer=rr=0.85", "lut": "cool.png", "lut_mix": 0.7,
                                         "grade": "eq=brightness=0.04"},
                                "ranges": [{"start": 0.2, "end": 1.5}]})
    cand = {"provider": "project", "id": "IMG_5001.MOV", "path": str(project / "IMG_5001.MOV"), "license": "own footage"}
    write_json(e / "visual_plan.json", {"id": "5000", "inserts": [
        {"id": "b01", "kind": "broll", "status": "planned", "start": 0.3, "dur": 1.0, "candidates": [cand]},
        {"id": "b02", "kind": "broll", "status": "planned", "start": 0.3, "dur": 1.0, "candidates": [cand]}]})
    run_script("cut.py", "edit/5000", cwd=project)
    r = run_script("footage.py", "pick", "edit/5000", "b01", cwd=project)
    assert "look as the rough cut (correct colorchannelmixer=rr=0.85, LUT cool.png at 70%, grade eq=brightness=0.04)" in r.stdout
    run_script("footage.py", "pick", "edit/5000", "b02", "--no-look", cwd=project)

    def center(f):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(f), "-frames:v", "1", "-vf",
                              "crop=8:8:536:956,scale=1:1:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        return list(raw[:3])
    cut, look, plain = center(e / "final.mp4"), center(e / "inserts" / "b01.mp4"), center(e / "inserts" / "b02.mp4")
    assert all(abs(a - b) <= 3 for a, b in zip(cut, look)), (cut, look)
    assert max(abs(a - b) for a, b in zip(cut, plain)) > 10, (cut, plain)  # without the look: visibly another color


def center_rgb(f, t=0.5):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(f), "-frames:v", "1", "-vf",
                          "crop=8:8:536:956,scale=1:1:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return list(raw[:3])


def extract_project(project):
    """A video whose cut.json has a look and a cutaway extract ("pool_view") made from its own source."""
    e = project / "edit" / "5100"
    make_video(project / "IMG_5100.MOV", 360, 640, 3.0, color="0xC8C8C8")  # a white wall
    write_json(e / "cut.json", {"fps": 30, "sources": {"main": {"file": "IMG_5100.MOV"}},
                                "look": {"correct": "colorchannelmixer=rr=0.8:bb=1.15", "grade": "eq=saturation=1.3"},
                                "ranges": [{"start": 0.2, "end": 1.5}],
                                "extract": {"pool_view": {"start": 1.6, "end": 2.9}}})
    write_json(e / "reel.json", {"use_broll": True, "use_project_footage": True, "use_local_footage": False,
                                 "use_generated_footage": False})
    run_script("cut.py", "edit/5100", cwd=project)
    return e


@needs_ffmpeg
def test_a_cut_extract_is_picked_without_a_second_look(project):
    # T5: pick applied the rough cut's look again to a cutaway cut.py had already graded ("extract"): the white
    # building came out pink. The candidate here has no "graded" mark (a plan from before the fix): the path decides
    e = extract_project(project)
    ext = e / "pool_view.mp4"
    cand = {"provider": "project", "id": "edit/5100/pool_view.mp4", "path": str(ext), "license": "own footage"}
    write_json(e / "visual_plan.json", {"id": "5100", "inserts": [
        {"id": "b01", "kind": "broll", "status": "planned", "start": 0.3, "dur": 1.0, "candidates": [cand]}]})
    r = run_script("footage.py", "pick", "edit/5100", "b01", cwd=project)
    assert "already in the rough cut's color" in r.stdout and "look as the rough cut" not in r.stdout
    src, picked = center_rgb(ext), center_rgb(e / "inserts" / "b01.mp4")
    assert all(abs(a - b) <= 3 for a, b in zip(src, picked)), (src, picked)
    # prepare --look on the extract does not grade it again either
    r = run_script("footage.py", "prepare", str(ext), "--out", str(e / "inserts" / "b02.mp4"), "--dur", "1.0",
                   "--look", "edit/5100", cwd=project)
    assert "no second look" in r.stdout
    assert all(abs(a - b) <= 3 for a, b in zip(src, center_rgb(e / "inserts" / "b02.mp4")))


@needs_ffmpeg
@needs_pillow
def test_plan_search_scores_by_the_query_and_finds_an_extract(project):
    # T5: search "pool бассейн" found the extract at 0.50, plan-search scored the long "what" + "query" together,
    # fell under --min-score and skipped the insert at once; the extract (not named broll*) was not project footage;
    # describing it needed the index, and index --dir overwrote the shared contact sheets
    e = extract_project(project)
    insert = {"id": "b01", "kind": "broll", "status": "planned", "start": 0.3, "dur": 1.0, "source": "auto",
              "what": "бассейн комплекса с видом на море и пальмами", "query": "sunset beach"}
    write_json(e / "visual_plan.json", {"id": "5100", "inserts": [insert]})
    r = run_script("footage.py", "plan-search", "edit/5100", cwd=project)
    plan = json.loads((e / "visual_plan.json").read_text(encoding="utf-8"))
    assert plan["inserts"][0]["status"] == "skipped" and "--retry" in r.stdout and "--query" in r.stdout
    # another query for this insert: found by the query alone, the same score as `search`
    r = run_script("footage.py", "plan-search", "edit/5100", "--insert", "b01", "--query", "pool бассейн", cwd=project)
    b01 = json.loads((e / "visual_plan.json").read_text(encoding="utf-8"))["inserts"][0]
    assert b01["status"] == "planned" and b01["query"] == "pool бассейн"
    assert b01["candidate"]["id"] == "edit/5100/pool_view.mp4" and b01["candidate"]["score"] == 0.5
    assert b01["candidate"]["graded"] is True
    s = run_script("footage.py", "search", "pool бассейн", "--edit", "edit/5100", "--providers", "project", cwd=project)
    assert "0.50" in s.stdout and "pool_view.mp4" in s.stdout
    # the shared sheets stay as they are when one folder is indexed; describe takes a file the index does not know
    (project / "_footage_index").mkdir()
    (project / "_footage_index" / "sheet-00.jpg").write_bytes(b"shared")
    r = run_script("footage.py", "index", "--dir", "edit/5100/clips", cwd=project)
    assert (project / "_footage_index" / "sheet-00.jpg").read_bytes() == b"shared"
    assert list((project / "_footage_index").glob("edit-5100-clips-sheet-*.jpg"))
    run_script("footage.py", "describe", "edit/5100/pool_view.mp4", "бассейн, пальмы", cwd=project)
    idx = json.loads((project / "footage_index.json").read_text(encoding="utf-8"))
    assert idx["edit/5100/pool_view.mp4"]["description"] == "бассейн, пальмы"
    # --retry searches again for an insert plan-search skipped
    insert2 = dict(insert, id="b02", query="", what="пальмы у воды")
    write_json(e / "visual_plan.json", {"id": "5100", "inserts": [dict(insert2, status="skipped",
                                                                     fallback="no footage in any enabled source: main footage")]})
    run_script("footage.py", "plan-search", "edit/5100", "--retry", cwd=project)
    b02 = json.loads((e / "visual_plan.json").read_text(encoding="utf-8"))["inserts"][0]
    assert b02["status"] == "planned" and b02["candidate"]["id"] == "edit/5100/pool_view.mp4"


def test_a_breath_at_an_edge_is_not_a_voiceless_consonant():
    # T2: --edl flagged two edges --spans had made: a breath at -51...-55 dBFS (threshold -46) sits in the high band
    # too, 8-10 dB under the speech's high band; a final "s" sits within ~2 dB of it and must still be caught
    import speech_mask as sm
    env = [-75.0] * 400
    hf = [-80.0] * 400
    for i in range(50, 200):  # speech: loud overall, with its own high band
        env[i], hf[i] = -20.0, -45.0
    thr = -40.0

    def warnings(level):
        e2, h2 = env[:], hf[:]
        for i in range(200, 216):  # hiss right after the speech, under the threshold overall
            e2[i], h2[i] = -55.0, level
        vl = sm.voiceless(h2)
        mask = sm.speech_mask(sm.smax(e2), thr, vl=vl)
        return " ".join(sm.edge_warnings(e2, mask, thr, 0.4, 2.07, vl, h2))
    assert "cuts a voiceless sound" in warnings(-46.0)       # a final "s": at the speech's high-band level
    assert "cuts a voiceless sound" not in warnings(-56.0)   # a breath: 11 dB under it


def band_db(path, t0, t1, flt):
    """RMS of one band of a file's audio over t0..t1, dBFS (flt: an ffmpeg filter that keeps the band)."""
    import re
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-ac", "1", "-af",
                        f"atrim={t0}:{t1},{flt},astats=measure_overall=RMS_level:measure_perchannel=0",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return float(re.findall(r"RMS level dB:\s*(-?[\d.]+)", r.stderr)[-1])


@needs_ffmpeg
def test_master_audio_ducks_the_music_under_a_key_line(project):
    # T4: the docs said "drop the music under the key line" and there was no tool for it (a pre-ducked copy of the
    # track was made by hand); --duck lowers the music in a window of the render and leaves the voice alone
    from conftest import ffmpeg
    ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=360x640:r=30:d=6", "-f", "lavfi", "-i", "sine=f=300:d=6,volume=0.3",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", project / "render.mp4")
    ffmpeg("-f", "lavfi", "-i", "sine=f=3000:d=9,volume=0.5", project / "track.wav")
    common = ["render.mp4", "--music", "track.wav", "--no-denoise"]
    r = run_script("master_audio.py", *common, "-o", "plain.mp4", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    r = run_script("master_audio.py", *common, "-o", "ducked.mp4", "--duck", "2.0-3.6", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "music ducked under a key line: 2.00-3.60 s by -14 dB" in r.stdout
    music, voice = "highpass=f=2000,highpass=f=2000", "lowpass=f=800,lowpass=f=800"
    plain, ducked = project / "plain.mp4", project / "ducked.mp4"
    inside = band_db(ducked, 2.3, 3.3, music) - band_db(plain, 2.3, 3.3, music)
    outside = band_db(ducked, 4.2, 5.0, music) - band_db(plain, 4.2, 5.0, music)
    assert -15.5 <= inside <= -12.5, inside              # the asked 14 dB inside the window
    assert abs(outside) <= 1.0, outside                  # the bed around it as before
    assert abs(band_db(ducked, 2.3, 3.3, voice) - band_db(plain, 2.3, 3.3, voice)) <= 0.5  # the voice untouched
    r = run_script("master_audio.py", *common, "-o", "x.mp4", "--duck", "3-2", cwd=project, check=False)
    assert r.returncode != 0 and "END after START" in (r.stdout + r.stderr)


@needs_ffmpeg
def test_cut_carries_speakers_and_names_a_word_in_a_removed_pause(project):
    # T4: subtitles per speaker had no way through: no speaker field on a caption word, cut.json could not say who
    # speaks (two people on one microphone, identified by the lips), the transcript's "speaker_id" was not read; and a
    # quiet syllable the speech mask took for a pause was dropped from the sound and the subtitles without a word
    import cut
    e = cut_project(project)
    tr = json.loads((e / "transcripts" / "IMG_4821.json").read_text(encoding="utf-8"))
    tr["words"][0]["speaker_id"] = "S1"  # a transcriber's own label ("Hello")
    write_json(e / "transcripts" / "IMG_4821.json", tr)
    doc = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    doc["ranges"] = [{"source": "main", "start": 0.4, "end": 3.0, "beat": "hook"},
                     {"source": "main", "start": 3.25, "end": 6.6, "beat": "end", "speaker": "B",
                      "speakers": [{"from": 5.9, "to": 6.6, "speaker": "A"}]}]
    write_json(e / "cut.json", doc)
    r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project)
    # "gap" (3.05-3.2) sits in the 0.25 s the cut removes between the two ranges: named, with what to do
    assert 'the word "gap" (main 3.05-3.20) falls in the 3.00-3.25 gap' in r.stderr and "--thr" in r.stderr, r.stderr
    assert "words per speaker: A 1, B 1, S1 1" in r.stdout, r.stdout
    c = cut.load_cut(e, project)
    _, caps, _ = cut.timeline(c, cut.load_words(c))
    who = {w["text"]: w.get("speaker") for w in caps}
    assert who == {"Hello": "S1", "recruiter": None, "everything": None, "tail": "B", "end": "A"}, who
    assert cut.speakers_of(caps) == ["A", "B", "S1"]
    # a word in a long gap (a line dropped on purpose) or removed with "to": "" is not named
    doc["fix_at"].append({"text": "gap", "at": 3.05, "to": ""})
    write_json(e / "cut.json", doc)
    assert "falls in the" not in run_script("cut.py", "edit/4821", "--dry-run", cwd=project).stderr
    bad = dict(doc, ranges=[dict(doc["ranges"][1], speakers=[{"from": 6.0, "speaker": "A"}])])
    write_json(e / "cut.json", bad)
    r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project, check=False)
    assert r.returncode != 0 and "speakers[0] needs" in (r.stdout + r.stderr)


@needs_ffmpeg
def test_speech_mask_flags_a_short_pause_with_a_sound_just_under_the_threshold(project):
    # T4: a quiet syllable at -35..-40 dBFS under a -33.6 threshold read as a pause, and the ranges --spans printed cut
    # it out without a warning
    from conftest import ffmpeg

    def wav(name, quiet):
        loud = "between(t,0.5,2)+between(t,2.4,4)"
        expr = f"if({loud},0.5,if(between(t,2.12,2.27),{quiet},0))*sin(2*PI*300*t)"
        ffmpeg("-f", "lavfi", "-i", f"aevalsrc='{expr}':s=16000:d=5", "-ac", 1, project / name)
    wav("syllable.wav", 0.0376)  # -31.5 dBFS RMS: within 3 dB under the -30 threshold
    wav("silence.wav", 0.0)
    r = run_script("speech_mask.py", "syllable.wav", "--spans", "0.3-4.2", cwd=project)
    assert "within 3 dB under the threshold: a quiet syllable or a breath" in r.stdout, r.stdout + r.stderr
    r = run_script("speech_mask.py", "silence.wav", "--spans", "0.3-4.2", cwd=project)
    assert "quiet syllable" not in r.stdout
    import speech_mask as sm
    env = [-80.0] * 100
    env[40:46] = [-31.0] * 6  # 60 ms within 3 dB under -30
    assert sm.quiet_syllable(env, -30.0, 0.30, 0.70, 0.16) == 60
    assert sm.quiet_syllable(env, -30.0, 0.30, 1.20, 0.16) == 0  # a long pause is not a syllable's room


def test_patch_render_gives_remotion_an_absolute_props_path(project, monkeypatch):
    # T5: a relative --props went to Remotion as is; Remotion runs in its own project folder, so it answered
    # "neither valid JSON nor a file path". The path is made absolute from the current folder; inline JSON is kept
    import sys
    import pytest
    import patch_render as pr
    write_json(project / "edit" / "t5" / "reelkit-props.json", {"video": "t5/video.mp4"})
    (project / "out").mkdir()
    (project / "out" / "t5.mp4").write_bytes(b"a render")
    calls = []

    class Stop(Exception):
        pass

    def run(cmd, cwd=None, what=""):
        calls.append((cmd, cwd))
        raise Stop
    monkeypatch.setattr(pr, "find_remotion", lambda old, given: project / "reels")
    monkeypatch.setattr(pr, "probe_video", lambda p: {"fps": 30, "frames": 90, "width": 1080, "height": 1920})
    monkeypatch.setattr(pr, "keyframes", lambda p, fps: [0, 30, 60])
    monkeypatch.setattr(pr, "run", run)
    for props, want in (("edit/t5/reelkit-props.json", str((project / "edit" / "t5" / "reelkit-props.json").resolve())),
                        ('{"video": "x.mp4"}', '{"video": "x.mp4"}')):
        monkeypatch.setattr(sys, "argv", ["patch_render.py", "out/t5.mp4", "--comp", "TestT5", "--from", "1.2", "--to",
                                          "1.8", "--props", props])
        with pytest.raises(Stop):
            pr.main()
        assert f"--props={want}" in calls[-1][0]
    monkeypatch.setattr(sys, "argv", ["patch_render.py", "out/t5.mp4", "--comp", "TestT5", "--from", "1.2", "--to", "1.8",
                                      "--props", "edit/t5/missing.json"])
    with pytest.raises(SystemExit, match="no such file"):
        pr.main()


@needs_ffmpeg
def test_poster_pick_on_a_render_without_sound(project):
    # T6: a "scenes only" render has no audio track, and pick crashed in the speech mask ("does not contain any
    # stream"); without sound it takes the settled frame of the hook scene (else, in "scenes only", the first scene)
    make_video(project / "r.mp4", 360, 640, 6.0, audio=False)
    e = project / "edit" / "promo1"
    write_json(e / "reel.json", {"scene_tone": "cinematic"})
    hook = {"id": "c01", "kind": "scene", "type": "hook", "mode": "full", "start": 0.0, "dur": 2.6, "status": "ready"}
    write_json(e / "visual_plan.json", {"id": "promo1", "format": "scenes-only", "duration": 6.0, "segments": [],
                                        "inserts": [hook]})
    r = run_script("poster.py", "pick", "edit/promo1", "--render", project / "r.mp4", "-o", project / "c.jpg", cwd=project)
    assert "cover: frame at 1.40 s" in r.stdout and "no sound track" in r.stdout, r.stdout
    assert (project / "c.jpg").is_file()
    r = run_script("poster.py", "pick", "edit/promo1", "--render", project / "r.mp4", "--sheet", project / "s.jpg",
                   cwd=project)
    assert "(on speech)" not in r.stdout and "no face in these frames" in r.stdout, r.stdout
    run_script("poster.py", "pick", "edit/promo1", "--render", project / "r.mp4", "--t", "2.0", "-o", project / "c.jpg",
               cwd=project)
    stat = dict(hook, type="stat", dur=3.0)  # no hook and no cover scene: the first scene
    write_json(e / "visual_plan.json", {"id": "promo1", "format": "scenes-only", "duration": 6.0, "segments": [],
                                        "inserts": [stat]})
    r = run_script("poster.py", "pick", "edit/promo1", "--render", project / "r.mp4", "-o", project / "c.jpg", cwd=project)
    assert "c01 stat (cinematic)" in r.stdout, r.stdout


@needs_ffmpeg
def test_master_check_applies_the_no_voice_rule(project):
    # T6: master_audio accepted a "scenes only" master (scene sounds over silence: no -14 LUFS rule, the true peak is
    # checked), while --check of the same file demanded -14 LUFS and failed
    from conftest import ffmpeg
    make_video(project / "render.mp4", 360, 640, 4.0, audio=False)
    ffmpeg("-f", "lavfi", "-i", "sine=f=1500:d=0.3", project / "hit.wav")
    write_json(project / "sfx.json", {"sounds": [{"file": "hit.wav", "at": 1.0, "what": "the hook"}]})
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", "--sfx", "sfx.json", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    r = run_script("master_audio.py", "master.mp4", "--check", cwd=project, check=False)
    assert r.returncode == 0 and "does not apply" in r.stdout and "→ OK" in r.stdout, r.stdout + r.stderr
    # the tag survives the cover art (poster.py attach copies the file's metadata)
    ffmpeg("-f", "lavfi", "-i", "color=c=red:size=360x640", "-frames:v", "1", project / "cover.jpg")
    run_script("poster.py", "attach", "master.mp4", "--cover", "cover.jpg", "-o", "final.mp4", cwd=project)
    assert run_script("master_audio.py", "final.mp4", "--check", cwd=project, check=False).returncode == 0
    # a master made before the tag: the loudness fails, --no-loudness applies the rule by hand
    ffmpeg("-i", project / "master.mp4", "-map", "0", "-c", "copy", "-map_metadata", "-1", project / "old.mp4")
    r = run_script("master_audio.py", "old.mp4", "--check", cwd=project, check=False)
    assert r.returncode == 1 and "loudness" in r.stdout
    r = run_script("master_audio.py", "old.mp4", "--check", "--no-loudness", cwd=project, check=False)
    assert r.returncode == 0 and "→ OK" in r.stdout
    # no voice and no effects: copied without sound, and --check knows it is a video without sound
    run_script("master_audio.py", "render.mp4", "-o", "silent.mp4", cwd=project)
    r = run_script("master_audio.py", "silent.mp4", "--check", cwd=project, check=False)
    assert r.returncode == 0 and "no audio track" in r.stdout, r.stdout + r.stderr


@needs_ffmpeg
def test_music_clears_the_no_voice_tag(project):
    # Codex review: a silent master tagged "no sound track" and mastered again with --music kept the tag (ffmpeg copies
    # the first input's metadata), and --check then skipped the -14 LUFS rule for a master with music
    import master_audio
    from conftest import ffmpeg
    make_video(project / "render.mp4", 360, 640, 4.0, audio=False)
    run_script("master_audio.py", "render.mp4", "-o", "silent.mp4", cwd=project)
    assert master_audio.master_tag(str(project / "silent.mp4"))
    ffmpeg("-f", "lavfi", "-i", "sine=f=300:d=9,volume=0.5", project / "track.wav")
    r = run_script("master_audio.py", "silent.mp4", "-o", "music.mp4", "--music", "track.wav", cwd=project, check=False)
    assert (project / "music.mp4").exists(), r.stdout + r.stderr
    assert master_audio.master_tag(str(project / "music.mp4")) is None


@needs_ffmpeg
def test_a_silent_track_is_left_out_of_a_master_tagged_without_sound(project):
    # Codex review (PR #13): a render with a silent audio track was copied with that track and tagged "no sound
    # track"; --check saw the tag, but with a track present it measured the loudness of silence and failed
    from conftest import ffmpeg
    ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=360x640:r=30:d=3", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
           "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", project / "render.mp4")
    run_script("master_audio.py", "render.mp4", "-o", "silent.mp4", cwd=project)
    assert "audio" not in probe_streams(project / "silent.mp4")
    r = run_script("master_audio.py", "silent.mp4", "--check", cwd=project, check=False)
    assert r.returncode == 0 and "no audio track" in r.stdout, r.stdout + r.stderr
