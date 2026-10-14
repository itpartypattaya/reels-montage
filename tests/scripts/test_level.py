"""Speech leveling (level.py, run by cut.py): pieces and stretches inside a piece brought to one speech level."""
import json
import subprocess

from conftest import ffmpeg, needs_ffmpeg, run_script, write_json

import level as L

HOP = L.HOP


def env_of(spans, n_sec, floor=-60.0):
    """An envelope: dB per 10 ms window; spans = [(start, end, dB)] of speech, the rest at the noise floor."""
    env = [floor] * int(round(n_sec / HOP))
    for a, b, db in spans:
        for i in range(int(round(a / HOP)), int(round(b / HOP))):
            env[i] = db
    return env


def at(g, t):
    return g[int(round(t / HOP))]


def test_two_sources_at_different_levels_meet_at_one_level():
    # piece 1 (source a) speaks at -20 dB, piece 2 (source b) at -28 dB, each 4 s with a pause inside
    env = env_of([(0.2, 1.8, -20), (2.2, 3.8, -20), (4.2, 5.8, -28), (6.2, 7.8, -28)], 8.0)
    g, rep = L.gain_curve(env, [("a", 0.0, 4.0), ("b", 4.0, 4.0)])
    after_a, after_b = -20 + at(g, 1.0), -28 + at(g, 5.0)
    assert abs(after_a - after_b) < 0.5
    assert abs(rep["sources"]["a"]["after_db"] - rep["sources"]["b"]["after_db"]) < 0.5
    assert rep["sources"]["a"]["before_db"] == -20 and rep["sources"]["b"]["before_db"] == -28


def test_a_take_more_than_20_db_quieter_is_still_leveled():
    # a shared threshold (-20 - 20 = -40) would put the -41 dB take under it whole: no speech, no gain
    env = env_of([(0.2, 3.8, -20), (4.2, 7.8, -41)], 8.0, floor=-75.0)
    g, rep = L.gain_curve(env, [("a", 0.0, 4.0), ("b", 4.0, 4.0)])
    assert rep["sources"]["b"]["before_db"] == -41
    assert at(g, 6.0) >= L.MAX_GAIN - 0.01 and at(g, 2.0) <= -L.MAX_GAIN + 0.01   # both to the middle, both capped
    assert rep["threshold_db"]["b"] < rep["threshold_db"]["a"]


def test_a_pause_holds_the_gain_of_the_speech_around_it():
    env = env_of([(0.2, 1.8, -24), (2.6, 3.8, -24)], 4.0)
    g, _ = L.gain_curve(env, [("a", 0.0, 4.0)])
    # the pause 1.8-2.6 is not raised above the gain of the speech next to it
    assert max(g[int(1.9 / HOP):int(2.5 / HOP)]) <= max(at(g, 1.0), at(g, 3.0)) + 0.01


def test_a_speaker_turning_away_inside_a_piece_is_corrected_gently():
    # one 12 s piece: 6 s at -20, then 6 s at -26 (turned away); speech without pauses
    env = env_of([(0.0, 6.0, -20), (6.0, 12.0, -26)], 12.0)
    g, _ = L.gain_curve(env, [("a", 0.0, 12.0)])
    gap_before = 6.0
    gap_after = (-20 + at(g, 2.0)) - (-26 + at(g, 10.0))
    assert gap_after < gap_before - 3.0          # most of the drop evened out
    assert at(g, 10.0) - at(g, 2.0) <= 2 * L.IN_MAX + 0.01   # the local correction is limited
    steps = [abs(g[i + 1] - g[i]) for i in range(len(g) - 1)]
    assert max(steps) <= L.SLEW * HOP + 1e-9     # no jump inside a piece


def test_the_gain_is_limited_and_the_peak_is_kept_under_full_scale():
    env = env_of([(0.2, 3.8, -10), (4.2, 7.8, -40)], 8.0, floor=-75.0)
    g, rep = L.gain_curve(env, [("a", 0.0, 4.0), ("b", 4.0, 4.0)])
    assert max(abs(x) for x in g) <= L.MAX_GAIN + 1e-9
    # a quiet take with one loud click (peak -1 dBFS): raising the take would push the click over full scale
    env = env_of([(0.2, 3.8, -20), (4.2, 7.8, -30)], 8.0, floor=-75.0)
    peak = [x + 3 for x in env]
    peak[int(6.0 / HOP)] = -1.0
    g2, rep2 = L.gain_curve(env, [("a", 0.0, 4.0), ("b", 4.0, 4.0)], peak=peak)
    assert max(p + x for p, x in zip(peak, g2)) <= L.PEAK_LIMIT + 1e-6
    assert rep2.get("peak_trim_db", 0) > 0


def test_a_piece_with_too_little_speech_takes_its_source_level():
    env = env_of([(0.2, 3.8, -20), (4.1, 4.5, -32), (5.0, 8.8, -20)], 9.0)
    g, rep = L.gain_curve(env, [("a", 0.0, 4.0), ("a", 4.0, 0.8), ("a", 4.8, 4.2)])
    assert rep["pieces"][1]["level_db"] == rep["sources"]["a"]["before_db"]


def test_no_speech_means_no_gain():
    g, rep = L.gain_curve([-90.0] * 300, [("a", 0.0, 3.0)])
    assert set(g) == {0.0} and rep["target_db"] is None


def _source(path, volume, dur=6.0):
    """A test video whose sound is two tone 'phrases' (0.5-2.5 s, 3.5-5.5 s) at a given volume."""
    on = "between(t,0.5,2.5)+between(t,3.5,5.5)"
    ffmpeg("-f", "lavfi", "-i", f"testsrc2=size=720x1280:rate=30:duration={dur}",
           "-f", "lavfi", "-i", f"sine=frequency=220:duration={dur},volume='{volume}*if({on},1,0)':eval=frame",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path)


def _two_take_project(project, level=None):
    _source(project / "A.MOV", 0.5)
    _source(project / "B.MOV", 0.2)   # about 8 dB quieter
    e = project / "edit" / "lv"
    cut = {"fps": 30, "speed": 1.0, "sources": {"a": {"file": "A.MOV"}, "b": {"file": "B.MOV"}},
           "ranges": [{"source": "a", "start": 0.3, "end": 5.7}, {"source": "b", "start": 0.3, "end": 5.7}]}
    if level is not None:
        cut["level"] = level
    write_json(e / "cut.json", cut)
    return e


def _segs(e):
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    return cap, [(s["source"], s["out_start"], s["out_dur"]) for s in cap["segments"]]


@needs_ffmpeg
def test_cut_levels_two_takes_recorded_at_different_volumes(project):
    e = _two_take_project(project)
    r = run_script("cut.py", "edit/lv", cwd=project)
    assert "speech leveling:" in r.stdout
    cap, segs = _segs(e)
    before, _ = L.measure(e / "clips" / "audio_only.m4a", segs)
    after, _ = L.measure(e / "final.mp4", segs)
    assert before["a"] - before["b"] > 6
    assert abs(after["a"] - after["b"]) <= 1.0
    assert cap["leveling"]["sources"]["b"]["after_db"] is not None
    # level.py --check measures without changing anything
    r = run_script("level.py", "edit/lv", "--check", cwd=project)
    assert "speech level per source" in r.stdout


@needs_ffmpeg
def test_level_false_keeps_the_sound_as_joined(project):
    e = _two_take_project(project, level=False)
    r = run_script("cut.py", "edit/lv", cwd=project)
    assert "speech leveling" not in r.stdout
    cap, _ = _segs(e)
    assert "leveling" not in cap

    def md5(p):
        return subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:a", "-c", "copy", "-f", "md5", "-"],
                              capture_output=True, text=True, check=True).stdout.strip()
    assert md5(e / "final.mp4") == md5(e / "clips" / "audio_only.m4a")
