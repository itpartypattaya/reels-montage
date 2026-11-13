"""picture.py scan (references/no-speaker.md, "Is the footage usable"): hints about bad stretches of a clip, before
it goes under a voice-over or into a no-speech reel.

What the person needs, in words:
- A clip shot from the hand (the picture jitters) gets a "shake" candidate over the jittery seconds. The same picture
  from a tripod (only sensor noise), a smooth pan and a still picture with something moving across it get no alarm.
- A picture with too little detail to measure the motion on (a clear sky, a wall) is listed as "shake not assessed",
  not passed silently and not flagged as shake.
- The tail an editing app adds (a cut to its outro, black or a frozen last frame) is a "tail" candidate from the
  cut to the end. Black or frozen stretches elsewhere are candidates too.
- A dark stretch and an overexposed stretch are candidates at their seconds.
- Speech-like sound in the clip's own sound is a "speech" hint (someone may be talking: the lips would not match a
  voice-over); a steady noise (a pool, wind) and silence are not. A clip without sound says so.
- Faces: more faces than the clip usually has is a "faces" candidate (strangers?), with the advice that they are
  hidden only under an opaque full scene for their whole window, never a panel; a face that turns to the camera is a
  "turn" candidate; a face too small to judge (a wide shot) is listed as "turn not assessed", never quietly skipped.
- Every candidate has its reason and the status "unchecked"; the scan itself excludes nothing and changes no file of
  the project (cut.json, footage_index.json).
- --window scans only that stretch, the times stay seconds of the clip.
- A second scan of an unchanged file reads its cache; a changed file (another size or time) is measured again.
- No frame is written out as an image (the laptop has 8 GB and little disk to spare): the frames go through a pipe,
  decoded at about 480 px.
- With an edit (--edit edit/<id>), every candidate also gets the seconds of the finished video where that stretch of
  the clip is on screen: through each shot's start and speed, and once per shot when the clip is used twice; a
  "faces" candidate gets the window to hide (0.25 s on each side).
- defects.py's turn measure is one function both scripts use: a frontal face faces the camera, a profile does not, a
  face too small has no verdict.
"""
import json
import os
import shutil
from pathlib import Path

import pytest

from conftest import CORE, ffmpeg, needs_ffmpeg, run_script, write_json

pytestmark = needs_ffmpeg

W, H = 540, 960


# --- fixtures: small clips made by ffmpeg, as a phone gives them (H.264, 30 fps, a vertical frame) ------------------

def background(d, w=1100, h=1300):
    """A still, detailed picture bigger than the frame (a room, a street): one frame of testsrc2 made coarser and
    noisier, so it has texture everywhere."""
    p = d / "bg.png"
    if not p.is_file():
        ffmpeg("-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=1:duration=1",
               "-vf", "noise=alls=40:allf=u,gblur=sigma=1.2", "-frames:v", "1", p)
    return p


def shot(d, name, x="200", y="160", dur=8.0, vf_after="", noise=True):
    """A clip cut out of the still background by a moving crop window: x, y are ffmpeg expressions of t (the camera
    path); sensor noise on every frame unless noise=False."""
    out = d / name
    vf = f"crop={W}:{H}:x='{x}':y='{y}'" + (",noise=alls=8:allf=t" if noise else "") + (f",{vf_after}" if vf_after else "")
    ffmpeg("-loop", "1", "-framerate", "30", "-i", background(d), "-t", dur, "-vf", vf, "-r", "30",
           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out)
    return out


JITTER = "{a}*sin(2*PI*6.1*t)+{b}*sin(2*PI*3.7*t+1.3)+{c}*sin(2*PI*9.3*t+0.4)"


def jitter(a=7, b=5, c=3):
    return JITTER.format(a=a, b=b, c=c)


def scan(*args, project=None, env=None, check=True):
    r = run_script("picture.py", "scan", *args, "--json", cwd=project, env=env, check=check)
    return r


def report(*args, project=None, env=None):
    r = scan(*args, project=project, env=env)
    return json.loads(r.stdout), r


def cands(rep, kind=None):
    return [c for c in rep["candidates"] if kind is None or c["kind"] == kind]


def unassessed(rep, what=None):
    return [u for u in rep["unassessed"] if what is None or u["what"] == what]


def overlap(c, a, b):
    return max(0.0, min(c["end"], b) - max(c["start"], a))


# --- shake ----------------------------------------------------------------------------------------------------------

def test_a_handheld_stretch_is_a_shake_candidate_and_the_still_part_is_not(project):
    j = jitter()
    clip = shot(project, "hand.mp4", x=f"200+if(between(t,3,6),{j},0)", y=f"160+if(between(t,3,6),{jitter(5, 4, 2)},0)")
    rep, _ = report(clip, project=project)
    shake = cands(rep, "shake")
    assert shake, rep
    assert sum(overlap(c, 3.0, 6.0) for c in shake) >= 2.4  # most of the jittery three seconds
    assert sum(overlap(c, 0.0, 2.5) + overlap(c, 6.5, 8.0) for c in shake) == 0  # nothing over the calm seconds


def test_a_tripod_shot_a_smooth_pan_and_a_moving_object_raise_no_alarm(project):
    tripod = shot(project, "tripod.mp4")
    pan = shot(project, "pan.mp4", x="40+55*t", y="160+8*t")
    box = project / "box.png"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=150x150:rate=1:duration=1", "-frames:v", "1", box)
    mover = project / "mover.mp4"
    ffmpeg("-loop", "1", "-framerate", "30", "-i", background(project), "-loop", "1", "-framerate", "30", "-i", box,
           "-t", 8, "-filter_complex",
           f"[0:v]crop={W}:{H}:200:160,noise=alls=8:allf=t[b];[b][1:v]overlay=x='20+45*t':y='380+60*sin(2*PI*0.5*t)'",
           "-r", "30", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", mover)
    for clip in (tripod, pan, mover):
        rep, _ = report(clip, project=project)
        assert not cands(rep, "shake"), (clip.name, rep["candidates"])
        assert not unassessed(rep, "shake"), (clip.name, rep["unassessed"])  # enough detail: measured, and calm


def test_a_picture_without_detail_is_shake_not_assessed_not_silence(project):
    sky = project / "sky.mp4"
    ffmpeg("-f", "lavfi", "-i", f"color=c=0x6fa8dc:size={W}x{H}:rate=30:duration=6", "-vf", "noise=alls=4:allf=t",
           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", sky)
    rep, _ = report(sky, project=project)
    assert not cands(rep, "shake")
    notes = unassessed(rep, "shake")
    assert notes and sum(n["end"] - n["start"] for n in notes) >= 5.0, rep["unassessed"]
    assert "detail" in notes[0]["why"]


# --- the editor's tail, black and frozen stretches ------------------------------------------------------------------

def test_a_cut_to_an_outro_at_the_end_is_a_tail_candidate(project):
    body = shot(project, "body.mp4", dur=5.0)
    clip = project / "outro.mp4"
    ffmpeg("-i", body, "-f", "lavfi", "-i", f"color=c=black:size={W}x{H}:rate=30:duration=2", "-f", "lavfi", "-i",
           "color=c=white:size=80x80:rate=30:duration=2", "-filter_complex",
           "[1:v][2:v]overlay=x='230+40*t':y='440'[o];[0:v]fps=30,setsar=1[a];[o]setsar=1[b];[a][b]concat=n=2:v=1[v]",
           "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", clip)
    rep, _ = report(clip, project=project)
    tail = cands(rep, "tail")
    assert len(tail) == 1, rep["candidates"]
    assert abs(tail[0]["start"] - 5.0) <= 0.15 and tail[0]["end"] >= 6.8
    assert not [c for c in rep["candidates"] if c["kind"] != "tail" and c["start"] < 4.8]  # the clip itself is fine


def test_a_frozen_last_frame_is_a_tail_and_a_plain_clip_has_none(project):
    body = shot(project, "body.mp4", dur=5.0)
    frozen = project / "frozen.mp4"
    ffmpeg("-i", body, "-vf", "tpad=stop_mode=clone:stop_duration=2", "-c:v", "libx264", "-crf", "18",
           "-pix_fmt", "yuv420p", frozen)
    rep, _ = report(frozen, project=project)
    tail = cands(rep, "tail")
    assert len(tail) == 1 and abs(tail[0]["start"] - 5.0) <= 0.2 and "froz" in tail[0]["why"], rep["candidates"]
    rep, _ = report(body, project=project)
    assert not cands(rep, "tail") and not cands(rep, "freeze") and not cands(rep, "black"), rep["candidates"]


def test_black_at_the_start_is_a_black_candidate_not_a_tail(project):
    body = shot(project, "body.mp4", dur=5.0)
    clip = project / "blackstart.mp4"
    ffmpeg("-f", "lavfi", "-i", f"color=c=black:size={W}x{H}:rate=30:duration=1", "-i", body, "-filter_complex",
           "[0:v]setsar=1[a];[1:v]fps=30,setsar=1[b];[a][b]concat=n=2:v=1[v]", "-map", "[v]", "-c:v", "libx264",
           "-crf", "18", "-pix_fmt", "yuv420p", clip)
    rep, _ = report(clip, project=project)
    black = cands(rep, "black")
    assert len(black) == 1 and black[0]["start"] <= 0.1 and abs(black[0]["end"] - 1.0) <= 0.15, rep["candidates"]
    assert not cands(rep, "tail")


# --- exposure --------------------------------------------------------------------------------------------------------

def test_a_dark_and_an_overexposed_stretch_are_candidates(project):
    # dark: a tenth of the light; overexposed: three times the light, the highlights washed out white
    clip = shot(project, "expo.mp4", vf_after="lutyuv=y='val*0.10':enable='between(t,1.5,3.5)',"
                                               "lutyuv=y='clip(val*3,16,235)':u=128:v=128:enable='between(t,5,7)'")
    rep, _ = report(clip, project=project)
    dark, bright = cands(rep, "dark"), cands(rep, "bright")
    assert len(dark) == 1 and overlap(dark[0], 1.5, 3.5) >= 1.6, rep["candidates"]
    assert len(bright) == 1 and overlap(bright[0], 5.0, 7.0) >= 1.6, rep["candidates"]
    rep, _ = report(shot(project, "plain.mp4"), project=project)
    assert not cands(rep, "dark") and not cands(rep, "bright")


# --- sound -----------------------------------------------------------------------------------------------------------

def with_sound(project, name, wav):
    clip = project / name
    ffmpeg("-i", shot(project, "pic-" + name), "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
           "-shortest", clip)
    return clip


def test_speech_in_the_clips_own_sound_is_a_hint_and_steady_noise_is_not(project):
    from speechlike import dense_speech
    talk = project / "talk.wav"
    dense_speech(talk, dur=3.5, lead_in=2.5, noise_db=-50)  # speech 2.5-6.0 s over a quiet room
    ffmpeg("-i", talk, "-af", "apad=whole_dur=8", "-ar", 48000, project / "talk8.wav")
    rep, _ = report(with_sound(project, "talk.mp4", project / "talk8.wav"), project=project)
    sp = cands(rep, "speech")
    assert sp and sum(overlap(c, 2.5, 6.0) for c in sp) >= 2.5, rep
    assert sum(overlap(c, 0.0, 2.0) + overlap(c, 6.6, 8.0) for c in sp) == 0
    pool = project / "pool.wav"
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.25:duration=8:seed=3", "-ar", 48000, pool)
    rep, _ = report(with_sound(project, "pool.mp4", pool), project=project)
    assert not cands(rep, "speech"), rep["candidates"]


def test_a_clip_without_sound_says_so(project):
    rep, r = report(shot(project, "mute.mp4"), project=project)
    assert not cands(rep, "speech")
    assert unassessed(rep, "speech") and "no sound" in unassessed(rep, "speech")[0]["why"]


# --- faces (the detector's samples built by hand, as for defects.py) -------------------------------------------------

def face(x, y, w, score=0.92, turn=0.0, eyes=0.45):
    """A face as the detector gives it: [x, y, w, h, score, right eye, left eye, nose, mouth corners]; turn in eye
    distances (nose against the middle of the eyes), eyes = the eye distance in face widths."""
    h = 1.25 * w
    iod = eyes * w
    mx, my = x + w / 2, y + 0.4 * h
    rex, lex = mx - iod / 2, mx + iod / 2
    nx, ny = mx + turn * iod, my + 0.6 * iod
    return [x, y, w, h, score, rex, my, lex, my, nx, ny, mx - iod / 2, my + 1.1 * iod, mx + iod / 2, my + 1.1 * iod]


def face_samples(n, at, step=0.5):
    return {"step": step, "frame": [270, 480], "samples": [{"t": round(i * step, 3), "faces": at(i)} for i in range(n)]}


def test_more_faces_than_usual_is_a_strangers_candidate_hidden_only_by_a_full_scene():
    import picture
    actor = face(100, 120, 60)
    fs = face_samples(20, lambda i: [actor] + ([face(20, 300, 50, eyes=0.44)] if 8 <= i < 12 else []))
    cs, notes, info = picture.face_hints(fs)
    st = [c for c in cs if c["kind"] == "faces"]
    assert len(st) == 1 and st[0]["start"] == 4.0 and st[0]["end"] == 6.0, cs
    assert "full" in st[0]["why"] and "panel" in st[0]["why"]
    assert info["usual_faces"] == 1 and info["max_faces"] == 2


def test_a_face_turning_to_the_camera_is_a_turn_candidate():
    import picture
    fs = face_samples(20, lambda i: [face(100, 120, 60, eyes=0.18 if i < 10 else 0.45, turn=0.0)])
    cs, notes, _ = picture.face_hints(fs)
    turns = [c for c in cs if c["kind"] == "turn"]
    assert len(turns) == 1 and abs(turns[0]["start"] - 5.0) <= 0.5 and "turn" in turns[0]["why"], cs
    away = face_samples(20, lambda i: [face(100, 120, 60, eyes=0.18)])  # a profile all along: nothing to flag
    assert not [c for c in picture.face_hints(away)[0] if c["kind"] == "turn"]


def test_a_face_too_small_to_judge_is_turn_not_assessed_not_a_quiet_pass():
    import picture
    fs = face_samples(20, lambda i: [face(100, 300, 9, eyes=0.18 if i < 10 else 0.45)])  # a wide shot: 9 px faces
    cs, notes, _ = picture.face_hints(fs)
    assert not [c for c in cs if c["kind"] == "turn"]
    small = [n for n in notes if n["what"] == "turn"]
    assert small and small[0]["start"] == 0.0 and small[0]["end"] == 10.0 and "small" in small[0]["why"], notes


def test_a_talking_face_with_speech_reads_as_speaking_to_the_camera():
    import picture
    fs = face_samples(16, lambda i: [face(100, 120, 60)])
    sound = {"hop": 0.5, "win": 2.0, "t": [i * 0.5 for i in range(16)], "speech": [4 <= i < 12 for i in range(16)]}
    meas = {"window": [0.0, 8.0], "dur": 8.0, "fps": 15, "frame": [270, 480], "frames": None, "faces": fs,
            "sound": sound}
    rep = picture.candidates(meas)
    sp = [c for c in rep["candidates"] if c["kind"] == "speech"]
    assert len(sp) == 1 and "camera" in sp[0]["why"], rep["candidates"]


def test_the_turn_measure_is_one_function_of_defects():
    import defects
    frontal = face(100, 120, 60, eyes=0.45)
    profile = face(100, 120, 60, eyes=0.18)
    tiny = face(100, 120, 9, eyes=0.45)
    assert defects.turn_state(frontal)[0] == "facing"
    assert defects.turn_state(profile)[0] == "away"
    assert defects.turn_state(tiny, min_w=20)[0] == "small"


# --- the contract: hints only, cache, window, no images, the finished video's seconds ------------------------------

def test_every_candidate_is_unchecked_with_a_reason_and_the_scan_changes_nothing(project):
    clip = shot(project, "hand.mp4", x=f"200+{jitter()}", y=f"160+{jitter(5, 4, 2)}", dur=5.0)
    e = project / "edit" / "v1"
    cut = {"fps": 30, "sources": {"hand": {"file": str(clip)}}, "ranges": [{"source": "hand", "start": 0, "end": 4}]}
    write_json(e / "cut.json", cut)
    write_json(project / "footage_index.json", {"hand.mp4": {"description": "", "tags": [], "exclude": False}})
    before = {p: p.read_bytes() for p in (e / "cut.json", project / "footage_index.json")}
    rep, _ = report(clip, project=project)
    assert rep["candidates"]
    for c in rep["candidates"]:
        assert c["status"] == "unchecked" and c["why"] and c["end"] > c["start"], c
    assert {p: p.read_bytes() for p in before} == before


def test_window_scans_only_that_stretch_in_the_clips_seconds(project):
    j = jitter()
    clip = shot(project, "hand.mp4", x=f"200+if(between(t,4,6),{j},0)", y="160", dur=9.0)
    rep, _ = report(clip, "--window", "3-7", project=project)
    assert rep["sources"][0]["window"] == [3.0, 7.0]
    shake = cands(rep, "shake")
    assert shake and all(3.0 - 1e-6 <= c["start"] and c["end"] <= 7.0 + 1e-6 for c in shake)
    assert sum(overlap(c, 4.0, 6.0) for c in shake) >= 1.5, shake


def test_a_second_scan_reads_the_cache_and_a_changed_file_is_measured_again(project):
    clip = shot(project, "c.mp4", dur=4.0)
    a, _ = report(clip, project=project)
    b, _ = report(clip, project=project)
    assert a["sources"][0]["cached"] is False and b["sources"][0]["cached"] is True
    assert a["candidates"] == b["candidates"]
    shot(project, "c2.mp4", x=f"200+{jitter()}", dur=4.0).replace(clip)  # another file under the same name
    c, _ = report(clip, project=project)
    assert c["sources"][0]["cached"] is False and cands(c, "shake")


def test_no_frame_is_written_as_an_image_and_frames_are_about_480_px(project, tmp_path):
    clip = project / "big.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=3", "-c:v", "libx264", "-preset",
           "ultrafast", "-pix_fmt", "yuv420p", clip)
    tmp = tmp_path / "temp"
    tmp.mkdir()
    rep, _ = report(clip, project=project, env={"TEMP": str(tmp), "TMP": str(tmp), "TMPDIR": str(tmp)})
    assert rep["sources"][0]["frame"] == [270, 480]
    images = [p for root in (tmp, project) for p in root.rglob("*") if p.suffix.lower() in (".png", ".jpg", ".bmp")]
    assert not [p for p in images if p.name != "bg.png"], images


def test_candidates_get_the_finished_videos_seconds_through_start_speed_and_repeats(project):
    j = jitter()
    clip = shot(project, "hand.mp4", x=f"200+if(between(t,4,6),{j},0)", dur=10.0)
    e = project / "edit" / "v1"
    write_json(e / "cut.json", {"fps": 30, "sources": {"hand": {"file": str(clip), "strangers": []}}})
    shots = [  # the clip twice: from its second 3 at speed 0.8 and from its second 4.5 at normal speed
        {"i": 0, "kind": "video", "source": "hand", "src_start": 3.0, "src_end": 6.2, "speed": 0.8, "out_start": 0.0,
         "out_dur": 4.0},
        {"i": 1, "kind": "fill", "source": None, "src_start": 0, "src_end": 1.0, "out_start": 4.0, "out_dur": 1.0},
        {"i": 2, "kind": "video", "source": "hand", "src_start": 4.5, "src_end": 5.5, "speed": 1.0, "out_start": 5.0,
         "out_dur": 1.0}]
    write_json(e / "captions.json", {"duration": 6.0, "segments": [], "words": [], "shots": shots})
    rep, _ = report("--edit", "edit/v1", project=project)
    shake = cands(rep, "shake")
    assert shake, rep
    c = max(shake, key=lambda x: overlap(x, 4.0, 6.0))
    a, b = max(c["start"], 3.0), min(c["end"], 6.2)
    first = [w for w in c["in_reel"] if w["shot"] == 0][0]
    assert first["start"] == pytest.approx((a - 3.0) / 0.8, abs=0.02)
    assert first["end"] == pytest.approx((b - 3.0) / 0.8, abs=0.02)
    second = [w for w in c["in_reel"] if w["shot"] == 2][0]
    assert second["start"] == pytest.approx(5.0 + max(c["start"], 4.5) - 4.5, abs=0.02)
    assert second["end"] == pytest.approx(5.0 + min(c["end"], 5.5) - 4.5, abs=0.02)
    assert (e / "picture_scan.json").is_file()


def test_reel_windows_of_a_strangers_candidate_carry_the_hiding_margin():
    import picture
    shots = [{"i": 0, "kind": "video", "source": "pool", "src_start": 10.0, "src_end": 14.0, "speed": 1.0,
              "out_start": 2.0, "out_dur": 4.0}]
    cs = [{"kind": "faces", "start": 11.0, "end": 12.0, "why": "x", "status": "unchecked"}]
    out = picture.to_reel(cs, shots, "pool", duration=6.0)
    w = out[0]["in_reel"][0]
    assert (w["start"], w["end"]) == (3.0, 4.0)
    assert (w["hide_from"], w["hide_to"]) == (2.75, 4.25)


# --- found by review (Codex, 13.11): each failed on the code before its fix --------------------------------------

def test_a_turn_is_found_at_the_decoders_own_face_cadence():
    """The faces are sampled on the 15 fps frame grid: 0, 0.533, 1.0, 1.533 ... s, not every 0.5 s exactly."""
    import picture
    times = []
    k, nxt = 0, 0.0
    while len(times) < 20:
        t = k / 15
        if t + 1e-6 >= nxt:
            times.append(round(t, 3))
            nxt += 0.5
        k += 1
    fs = {"step": 0.5, "frame": [270, 480],
          "samples": [{"t": t, "faces": [face(100, 120, 60, eyes=0.18 if t < 5.0 else 0.45)]} for t in times]}
    turns = [c for c in picture.face_hints(fs)[0] if c["kind"] == "turn"]
    assert len(turns) == 1 and abs(turns[0]["start"] - 5.0) <= 0.1, turns


def test_face_spans_stay_inside_the_scanned_window():
    import picture
    fs = face_samples(21, lambda i: [face(100, 120, 60)] + ([face(20, 300, 50)] if i >= 18 else []))  # 0..10.5 s
    meas = {"window": [0.0, 9.8], "dur": 10.2, "fps": 15, "frame": [270, 480], "frames": None,
            "faces": dict(fs, samples=[s for s in fs["samples"] if s["t"] < 9.8]), "sound": None}
    rep = picture.candidates(meas)
    assert all(c["end"] <= 9.8 + 1e-6 for c in rep["candidates"]), rep["candidates"]
    assert all(u["end"] <= 9.8 + 1e-6 for u in rep["unassessed"]), rep["unassessed"]


def test_speech_in_a_window_is_the_same_from_the_cache_and_fresh(project):
    from speechlike import dense_speech
    talk = project / "talk.wav"
    dense_speech(talk, dur=4.0, lead_in=4.0, noise_db=-50)  # silence 0-4 s, then speech 4-8 s
    clip = with_sound(project, "talk.mp4", talk)
    report(clip, project=project)  # the whole clip measured and kept
    cached, _ = report(clip, "--window", "4-8", project=project)
    fresh, _ = report(clip, "--window", "4-8", "--fresh", project=project)
    assert cached["sources"][0]["cached"] is True and fresh["sources"][0]["cached"] is False
    assert cands(cached, "speech") == cands(fresh, "speech")


def test_another_face_model_of_the_same_size_measures_again(project, tmp_path):
    import picture
    clip = shot(project, "c.mp4", dur=2.0)
    a, b = tmp_path / "a" / "m.onnx", tmp_path / "b" / "m.onnx"
    for p, fill in ((a, b"\x01"), (b, b"\x02")):
        p.parent.mkdir()
        p.write_bytes(fill * 1000)
    import faces as fc
    keys = []
    for m in (a, b):
        fc.MODEL = str(m)
        try:
            keys.append(picture.cache_key(clip, 480, 15, True, True)["faces"])
        finally:
            fc.MODEL = None
    assert keys[0] != keys[1]
