"""longform.py camera (a camera.json proposal for a framed clip) and the --from/--to windows of speech_mask.py and
structure.py (a long WAV read only where it is needed)."""
import json
import math
import os
import time
import wave
from array import array
from pathlib import Path

import pytest

from conftest import run_script, write_json

import longform as lf
import speech_mask as sm
import structure as st


# --- a synthetic framed clip: two pieces of a 1920x1080 interview, two people at the sides ---------------------------

SRC_W, SRC_H = 1920, 1080
LEFT, RIGHT = 600, 1450          # face centers in the source's pixels (screen x ~127 and ~1103 in the default window
TWO_SHOT = (785, 1230)           # ... and a two-shot that fits the window: screen x ~339 and ~850)


def clip_words(segs, host_turns=()):
    """Words of 0.3 s with 0.05 s between them, a 0.3 s pause and a full stop after every 6th word; the host speaks
    in host_turns [(t0, t1)] of the video, the guest otherwise."""
    words = []
    for g in segs:
        t, k = g["out_start"] + 0.1, 0
        while t + 0.3 <= g["out_start"] + g["out_dur"] - 0.05:
            k += 1
            end_of = k % 6 == 0
            w = {"text": "word" + (str(k) + "." if end_of else str(k)), "start": round(t, 3), "end": round(t + 0.3, 3),
                 "src": round(g["src_start"] + (t - g["out_start"]), 3), "seg": g["i"]}
            if any(a <= t < b for a, b in host_turns):
                w["speaker"] = "host"
            words.append(w)
            t += 0.3 + (0.3 if end_of else 0.05)
    return words


def framed_clip(project, faces_at=(LEFT, RIGHT), host_turns=(), series=True, name="talk-01"):
    """edit/talk-01: a framed clip of two pieces (a: 8 s, b: 8 s), its captions and a faces.json in source geometry."""
    e = project / "edit" / name
    segs = [{"i": 0, "source": "a", "src_start": 5.0, "src_end": 13.0, "out_start": 0.0, "out_dur": 8.0, "speed": 1.0},
            {"i": 1, "source": "b", "src_start": 3.0, "src_end": 11.0, "out_start": 8.0, "out_dur": 8.0, "speed": 1.0}]
    write_json(e / "reel.json", {"format": "framed"})
    write_json(e / "cut.json", {"sources": {"a": {"file": "src/a.mp4"}, "b": {"file": "src/b.mp4"}}, "ranges": []})
    write_json(e / "captions.json", {"duration": 16.0, "segments": segs, "words": clip_words(segs, host_turns)})
    samples = []
    for k in range(64):
        faces = [[x - 45, 200, 90, 120, 0.92] for x in faces_at]
        samples.append({"t": round(k * 0.25, 3), "faces": faces})
    write_json(e / "faces.json", {"step": 0.25, "geometry": "source", "w": SRC_W, "h": SRC_H,
                                  "frame": [25, 340, 1030, 1240], "samples": samples})
    if series:
        write_json(project / "edit" / "talk" / "longform.json", {"clips": {"01": {"folder": f"edit/{name}"}}})
        write_json(project / "edit" / "talk" / "clips.json", {"clips": [{"id": "01", "speaker": "guest", "host": "keep"}]})
    return e


def camera(project, *args, ok=True):
    return run_script("longform.py", "camera", "edit/talk-01", *args, cwd=project, check=ok)


def test_face_groups_split_people_by_x():
    samples = [{"t": k * 0.25, "faces": [[100 + (k % 3), 600, 90, 120, 0.9], [1100, 590, 95, 125, 0.9]]}
               for k in range(40)]
    samples[3]["faces"].append([560, 1400, 60, 50, 0.62])  # one stray box: under 5 % of the faces, noise
    g = lf.face_groups(samples, [(0, 100)])
    assert [round(x["x"]) for x in g] == [146, 1148] and g[0]["n"] == 40
    one = lf.face_groups([{"t": k * 0.25, "faces": [[300 + 8 * k, 600, 90, 120, 0.9]]} for k in range(40)], [(0, 100)])
    assert len(one) == 1  # one person moving across the frame is one group
    assert lf.side_names(2) == ["left", "right"] and lf.side_names(4) == ["1", "2", "3", "4"]


def test_zoom_ceiling_by_the_source_rows():
    from reels_common import framed_view
    win = [25, 340, 1030, 1240]
    assert lf.zoom_ceiling(framed_view(win, (1920, 1080)), 1080)[0] == pytest.approx(1.13)
    assert lf.zoom_ceiling(framed_view(win, (1280, 720)), 720)[0] == pytest.approx(1.06)
    assert lf.zoom_ceiling(framed_view(win, (3840, 2160)), 2160)[0] == pytest.approx(1.3)
    full = [0, 0, 1080, 1920]  # the 9:16 crop: 1920 / 1080 = x1.78 already, so only the low push-in is left
    z, base = lf.zoom_ceiling(framed_view(full, (1920, 1080)), 1080)
    assert z == pytest.approx(1.06) and base == pytest.approx(1920 / 1080)


def test_group_of_needs_a_side_for_two_people():
    two = [{"x": 127}, {"x": 1103}]
    assert lf.group_of("guest", [{"x": 500}], {}) == 0  # one person: no question
    assert lf.group_of("guest", two, {}) is None
    assert lf.group_of("Guest", two, {"guest": "right"}) == 1
    assert lf.group_of("guest", two, {"guest": "1"}) == 0
    assert lf.group_of("guest", [{"x": 1}, {"x": 2}, {"x": 3}], {"guest": "right"}) == 2


def test_camera_asks_who_sits_where(project):
    framed_clip(project)
    r = camera(project, ok=False)
    assert r.returncode == 1 and "who sits where is not known for: guest" in r.stdout
    assert "--side guest=left" in r.stdout and "nothing written" in r.stdout
    assert not (project / "edit" / "talk-01" / "camera.json").exists()


def test_camera_proposal_follows_the_rules(project):
    import visual_plan as vp
    e = framed_clip(project, host_turns=[(3.0, 3.4), (10.0, 12.4)])  # a short "wow" in a, a host turn of 2.4 s in b
    r = camera(project, "--side", "guest=left,host=right")
    assert "not written: run again with --write" in r.stdout and not (e / "camera.json").exists()
    camera(project, "--side", "guest=left,host=right", "--write")
    doc = json.loads((e / "camera.json").read_text(encoding="utf-8"))
    shots = doc["shots"]
    assert doc["proposed"]["rev"] == lf.shots_rev(shots)
    assert all(s["source"] in ("a", "b") for s in shots)  # two pieces with overlapping seconds: every shot names its own
    assert [s["size"] for s in shots[:4]] == ["wide", "medium", "close", "medium"]
    assert max(s["z"] * (1 + s.get("drift", 0)) for s in shots) <= 1.13 + 1e-6  # within the window's zoom margin
    assert shots[0].get("drift") and shots[0]["z"] == 1.0  # no static wide opening
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    out = vp.camera_shots(e, {}, cap, quiet=True)  # the export resolves every shot, in order
    ts = [s["t"] for s in out]
    assert ts[0] == 0.0 and ts == sorted(ts) and len(set(ts)) == len(ts)
    assert any(abs(t - 8.0) < 1e-3 for t in ts)  # the change of piece is always a shot change
    holds = [b - a for a, b in zip(ts, ts[1:] + [16.0])]
    assert min(holds) >= 1.0 and max(holds) <= 4.0
    who = {s["who"] for s in shots if s["source"] == "b"}
    assert "host" in who  # the 2.4 s host turn gets its shot ...
    host = next(s for s in shots if s["who"] == "host")
    guest = next(s for s in shots if s["who"] == "guest" and s["size"] == host["size"])
    assert host["cx"] > guest["cx"] + 300  # ... framed on the right
    assert not any(s["who"] == "host" and s["source"] == "a" for s in shots)  # the 0.4 s "wow" is heard, not shown
    m = json.loads((project / "edit" / "talk" / "longform.json").read_text(encoding="utf-8"))
    assert m["sides"] == {"guest": "left", "host": "right"}  # once per series
    r = camera(project, "--write")  # the series' sides; the untouched proposal may be replaced
    assert "the series, longform.json" in r.stdout


def test_camera_never_replaces_a_file_edited_by_hand(project):
    e = framed_clip(project)
    camera(project, "--side", "guest=left", "--write")
    doc = json.loads((e / "camera.json").read_text(encoding="utf-8"))
    doc["shots"][1]["cx"] += 40
    write_json(e / "camera.json", doc)
    r = camera(project, "--write", ok=False)
    assert r.returncode == 1 and "edited by hand: not replaced" in r.stdout
    assert json.loads((e / "camera.json").read_text(encoding="utf-8")) == doc
    write_json(e / "camera.json", {"shots": [{"src": 5.0, "source": "a", "z": 1.0, "cx": 540, "cy": 960}]})
    assert "camera.json is yours" in camera(project).stdout  # a file written by hand from the start


def test_camera_wide_shot_holds_a_two_shot(project):
    framed_clip(project, faces_at=TWO_SHOT)
    camera(project, "--side", "guest=left", "--write")
    shots = json.loads((project / "edit" / "talk-01" / "camera.json").read_text(encoding="utf-8"))["shots"]
    wide = [s for s in shots if s["size"] == "wide"]
    close = [s for s in shots if s["size"] == "close"]
    # the pair spans screen x ~287-902 (60 px of room): the wide shot near its middle (~594), leaning 15 % toward the
    # guest (~556); the close-up on the guest's face (~339)
    assert wide and all(550 <= s["cx"] <= 562 for s in wide)
    assert all(abs(s["cx"] - 339) <= 5 for s in close)


def test_camera_refuses_what_it_cannot_frame(project):
    e = framed_clip(project, series=False)
    write_json(e / "reel.json", {"format": "full"})
    r = camera(project, ok=False)
    assert r.returncode == 1 and "for the framed format" in r.stderr
    write_json(e / "reel.json", {"format": "framed"})
    (e / "final.mp4").write_bytes(b"0")
    old = time.time() - 60
    os.utime(e / "faces.json", (old, old))
    r = camera(project, ok=False)
    assert r.returncode == 1 and "older than final.mp4" in r.stderr
    os.utime(e / "faces.json", None)
    r = camera(project, ok=False)  # no series: the speaker is "speaker", two people, no side
    assert "who sits where is not known for: speaker" in r.stdout


# --- a long WAV read only where it is needed --------------------------------------------------------------------------

BURSTS = [(2.0, 4.5), (5.0, 7.0), (20.0, 23.4), (23.6, 26.0), (30.0, 31.0)]


def tone_wav(path, bursts, dur, rate=16000):
    n = int(dur * rate)
    data = array("h", [0]) * n
    for a, b in bursts:
        for k in range(int(a * rate), min(n, int(b * rate))):
            data[k] = int(16000 * math.sin(2 * math.pi * 300 * k / rate))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())
    return path


def test_load_span_gives_the_windows_of_a_whole_read(tmp_path):
    wav = str(tone_wav(tmp_path / "long.wav", BURSTS, 40.0))
    env, hf = sm.load_envs(wav)
    for a, b in ((19.0, 27.0), (19.005, 27.0), (0.0, 3.0), (38.0, 45.0)):
        e2, h2, t0 = sm.load_span(wav, a, b)
        k = int(round(t0 / sm.HOP))
        assert t0 == pytest.approx(math.floor(a / sm.HOP + 1e-9) * sm.HOP)  # on the file's own 10 ms grid
        assert e2 == env[k:k + len(e2)] and h2 == hf[k:k + len(h2)]  # the same windows, the high band included
    assert len(sm.load_span(wav, 19.0, 27.0)[0]) == 800
    assert sm.segments([False, True, True, False], t0=10.0) == [(10.01, 10.03)]


def test_speech_mask_window_matches_the_whole_file(tmp_path):
    wav = tone_wav(tmp_path / "long.wav", BURSTS, 40.0)

    def ranges(*args):
        r = run_script("speech_mask.py", wav, "--spans", "19.8-26.2", "--thr", "-30", "--json", *args)
        return json.loads(r.stdout.strip().splitlines()[-1])["ranges"], r

    whole, _ = ranges()
    part, r = ranges("--from", "19.5", "--to", "26.5")
    assert part == whole and part[0][0] == pytest.approx(19.95, abs=0.03)
    assert "read 18.50" in r.stderr  # the stretch and a second of room on each side
    listed = run_script("speech_mask.py", wav, "--from", "19", "--to", "27", "--thr", "-30").stdout.splitlines()
    every = run_script("speech_mask.py", wav, "--thr", "-30").stdout.splitlines()
    assert len(every) == 5 and listed == [x for x in every if 19 <= float(x.split("–")[0]) < 27]  # file seconds
    r = run_script("speech_mask.py", wav, "--from", "19", "--to", "25", "--spans", "19.8-26.2", check=False)
    assert r.returncode != 0 and "outside --from" in r.stderr


def test_edge_warning_times_stay_seconds_of_the_file(tmp_path):
    wav = str(tone_wav(tmp_path / "long.wav", BURSTS, 40.0))
    env, hf, t0 = sm.load_span(wav, 18.5, 27.5)
    mask = sm.speech_mask(sm.smax(env), -30.0, vl=sm.voiceless(hf))
    w = sm.edge_warnings(env, mask, -30.0, 21.0, 25.0, sm.voiceless(hf), hf, t0)
    env0, hf0 = sm.load_envs(wav)
    mask0 = sm.speech_mask(sm.smax(env0), -30.0, vl=sm.voiceless(hf0))
    assert w == sm.edge_warnings(env0, mask0, -30.0, 21.0, 25.0, sm.voiceless(hf0), hf0)
    assert w and "start 21.00 is inside a word" in w[0]


def test_structure_mask_window_keeps_the_file_indices(tmp_path):
    wav = tone_wav(tmp_path / "long.wav", BURSTS, 40.0)
    full = st.load_mask(wav)
    part = st.load_mask(wav, 15.0, 31.0)
    lo, hi = int(19.0 / sm.HOP), int(27.0 / sm.HOP)
    assert part[0][lo:hi] == full[0][lo:hi] and part[1][lo:hi] == full[1][lo:hi]
    assert not any(part[0][:int(14.0 / sm.HOP)])  # nothing was read before the stretch: no speech there


def test_structure_fragment_reads_only_its_audio(project):
    rows = [("Early line one.", 2.0, 4.5), ("Early line two.", 5.0, 7.0), ("So what did we learn today?", 20.0, 23.4),
            ("We learned a lot.", 23.6, 26.0), ("The end.", 30.0, 31.0)]
    e = project / "edit" / "0002"
    words = []
    for text, s, t in rows:
        toks = text.split()
        step = (t - s) / len(toks)
        words += [{"text": x, "start": round(s + k * step, 3), "end": round(s + (k + 1) * step, 3), "type": "word"}
                  for k, x in enumerate(toks)]
    write_json(e / "transcripts" / "LONG.json", {"language_code": "en", "source": "LONG.MOV", "words": words})
    tone_wav(e / "audio16k-LONG.wav", BURSTS, 40.0)
    run_script("structure.py", "suggest", "edit/0002", cwd=project)
    whole = json.loads((e / "structure.json").read_text(encoding="utf-8"))
    r = run_script("structure.py", "suggest", "edit/0002", "--from", "19", "--to", "27", cwd=project)
    part = json.loads((e / "structure.json").read_text(encoding="utf-8"))
    assert part["audio_read"] == [14.0, 32.0] and "audio read 14-32 s only" in r.stdout
    inside = {p["i"]: (p["clean"], p["range"]) for p in whole["phrases"] if 19 <= p["start"] < 27}
    assert {p["i"]: (p["clean"], p["range"]) for p in part["phrases"]} == inside
    assert all(p["clean"] for p in part["phrases"])
