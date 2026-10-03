"""Focused regressions for the script review; synthetic media and fake network only."""
import copy
import importlib
import io
import json
import math
import subprocess
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import ADDON, ffmpeg, make_video, needs_ffmpeg, run_script, write_json
import cut
import reels_common as common


@pytest.fixture
def online(monkeypatch):
    monkeypatch.syspath_prepend(str(ADDON))
    import reels_online
    monkeypatch.setattr(reels_online, "offline", lambda: False)
    return reels_online


@pytest.fixture
def generation(online):
    import genfootage
    return genfootage


@pytest.mark.parametrize("name", ["../../outside", "/outside", "C:\\outside", "bad/name"])
def test_extract_refuses_paths(tmp_path, name):
    with pytest.raises(SystemExit):
        cut.extract_path(tmp_path, name)
    with pytest.raises(SystemExit):
        cut.extract({"extract": {name: {"start": 0, "end": 1}}, "sources": {"main": {}}}, tmp_path)


@pytest.mark.parametrize("command", ["cut", "place"])
@pytest.mark.parametrize("name", ["../../outside", "/outside", "C:\\outside"])
def test_matte_refuses_paths(project, command, name):
    e = project / "edit" / "4821"
    e.mkdir()
    args = [command, e, "--name", name]
    args += ["--from", "0", "--to", "1"] if command == "cut" else ["--layout", "review"]
    r = run_script("matte.py", *args, cwd=project, check=False)
    assert r.returncode != 0 and ("invalid --name" in r.stderr or "Latin letters" in r.stderr)


def test_inside_resolves_existing_parent(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks requires a Windows privilege")
    with pytest.raises(SystemExit):
        common.inside(root, root / "link" / "new.mp4")


def plan_for(source, ranges, fps=30):
    return {"fps": fps, "sources": {"main": {"speed": 1, "info": {"dur": 10}, "path": source}},
            "ranges": [{"source": "main", "beat": "", "start": a, "end": b} for a, b in ranges],
            "fix": {}, "fix_at": []}


def test_repeated_fragment_keeps_both_subtitles():
    c = plan_for(None, [(1, 2), (4, 5), (1, 2)])
    _, words, _ = cut.timeline(c, {"main": [{"text": "hook", "start": 1.2, "end": 1.5}]})
    assert [w["seg"] for w in words] == [0, 2]
    # The hook is also present when repeated inside a longer story span.
    c = plan_for(None, [(1, 2), (0, 3)])
    _, words, _ = cut.timeline(c, {"main": [{"text": "hook", "start": 1.2, "end": 1.5}]})
    assert [w["seg"] for w in words] == [0, 1]


def test_touching_ranges_assign_boundary_once():
    c = plan_for(None, [(0, 1), (1, 2)])
    _, words, _ = cut.timeline(c, {"main": [{"text": "edge", "start": 0.9, "end": 1.1}]})
    assert len(words) == 1


def test_word_across_a_removed_pause_is_shown_once():
    # The transcript put "signed" at 43.46-43.94, but the speech starts at 43.68; the cut drops the pause 43.50-43.67.
    c = plan_for(None, [(40, 43.5), (43.667, 44.433)])
    _, words, _ = cut.timeline(c, {"main": [{"text": "signed", "start": 43.46, "end": 43.94}]})
    assert [w["seg"] for w in words] == [1]


def test_hand_held_out_to_the_side_is_not_a_face():
    import faces
    face = [218, 496, 281, 403, 0.94]
    hand = [680, 1214, 364, 406, 0.61]  # a seated speaker's hand to the right, seen in one sample only
    keep, rej = faces.clean_frames([[face], [face, hand], [face]], times=[32.5, 32.75, 33.0], step=0.25)
    assert keep[1] == [face[:5]] and "below the chin" in rej[1][0][5]
    # a second person seated lower, seen in consecutive samples, stays
    other = [680, 1000, 280, 390, 0.8]
    keep, rej = faces.clean_frames([[face, other]] * 3, times=[1.0, 1.25, 1.5], step=0.25)
    assert keep[1] == [face[:5], other[:5]]
    # a small box far below the chin, score just over 0.7 (a hand on the knee, 26.5 s of a real video)
    small = [555, 1439, 158, 210, 0.71]
    face2 = [207, 485, 280, 432, 0.94]
    keep, rej = faces.clean_frames([[face2], [face2, small], [face2]], times=[26.25, 26.5, 26.75], step=0.25)
    assert keep[1] == [face2[:5]] and "far below" in rej[1][0][5]
    # a sofa cushion to the side, score 0.72, one sample
    cushion = [831, 1164, 226, 277, 0.72]
    face3 = [186, 464, 284, 411, 0.94]
    keep, rej = faces.clean_frames([[face3], [face3, cushion], [face3]], times=[39.0, 39.25, 39.5], step=0.25)
    assert keep[1] == [face3[:5]]


def test_camera_shots_from_source_seconds_words_and_seconds(tmp_path):
    import visual_plan as vp
    cap = {"segments": [{"i": 0, "src_start": 10.0, "src_end": 14.0, "out_start": 0.0, "out_dur": 2.0},
                        {"i": 1, "src_start": 20.0, "src_end": 24.0, "out_start": 2.0, "out_dur": 2.0}],
           "words": [{"text": "Numbers,", "start": 3.1, "end": 3.5}]}
    write_json(tmp_path / "camera.json", {"shots": [{"src": 21.0, "z": 1.2, "cy": 820},
                                                    {"at": "word:numbers#1", "z": 1.28, "whip": True},
                                                    {"at": 0, "z": 1.0}]})
    shots = vp.camera_shots(tmp_path, {"segments": []}, cap)
    assert [s["t"] for s in shots] == [0.0, 2.5, 3.1]  # src 21.0 -> 2.0 + 1.0 * (2.0 / 4.0)
    assert shots[2]["whip"] and shots[1]["cx"] == 540
    # the chin on screen follows the shot's camera: (911 - 820) * 1.2 + 960
    assert round(vp.chin_on_screen(911, 2.6, shots), 1) == 1069.2
    write_json(tmp_path / "camera.json", {"shots": [{"src": 19.9, "z": 1.1}]})  # just before a segment start: follows it
    assert vp.camera_shots(tmp_path, {"segments": []}, cap)[0]["t"] == 2.0
    write_json(tmp_path / "camera.json", {"shots": [{"src": 16.0, "z": 1.1}]})
    with pytest.raises(SystemExit, match="cut out"):
        vp.camera_shots(tmp_path, {"segments": []}, cap)


def test_zero_length_word_keeps_its_subtitle(tmp_path):
    # Whisper sometimes returns a short word with start == end ("какой" 14.70-14.70 before "результат" 14.70-15.18).
    write_json(tmp_path / "t.json", {"words": [{"text": "which", "start": 14.7, "end": 14.7},
                                               {"text": "result", "start": 14.7, "end": 15.18}]})
    c = plan_for(None, [(14, 16)])
    c["sources"]["main"]["transcript"] = tmp_path / "t.json"
    c["retime"] = []
    _, words, _ = cut.timeline(c, cut.load_words(c))
    assert [w["text"] for w in words] == ["which", "result"]
    assert words[0]["end"] > words[0]["start"]


@pytest.mark.parametrize("start,end", [(-1, 1), (0, 11), (0, 0.001), (math.nan, 1), (0, math.inf), (2, 1)])
def test_range_validation(start, end):
    with pytest.raises(SystemExit):
        cut.validate_range({"start": start, "end": end}, {"speed": 1, "info": {"dur": 10}}, 30, "test")


@pytest.mark.parametrize("fps", [0, -30, math.inf, math.nan])
def test_fps_validation(tmp_path, fps):
    write_json(tmp_path / "cut.json", {"fps": fps})
    with pytest.raises(SystemExit, match="fps"):
        cut.load_cut(tmp_path, tmp_path)


def test_geometry_refusal_before_encoding(tmp_path, monkeypatch):
    for name in ("a.mp4", "b.mp4"):
        (tmp_path / name).touch()
    write_json(tmp_path / "cut.json", {"scale": "none", "sources": {"a": "a.mp4", "b": "b.mp4"},
        "ranges": [{"source": "a", "start": 0, "end": 1}, {"source": "b", "start": 0, "end": 1}]})
    monkeypatch.setattr(cut, "probe", lambda p: {"w": 320 if p.name == "a.mp4" else 640, "h": 180, "dur": 2})
    with pytest.raises(SystemExit, match="geometry/SAR"):
        cut.load_cut(tmp_path, tmp_path)


def test_audio_trim_uses_frame_duration(tmp_path, monkeypatch):
    c = plan_for(None, [(0, 1 / 30)] * 100)
    segments, _, total = cut.timeline(c, {"main": []})
    assert abs(total - 100 / 30) < 1e-12
    (tmp_path / "clips").mkdir()
    calls = []
    monkeypatch.setattr(cut, "run", lambda args, **kw: calls.append(args))
    parts = [tmp_path / "clips" / f"seg_{k:03}.mp4" for k in range(100)]
    cut.join(tmp_path, parts, segments)
    graph = calls[1][calls[1].index("-filter_complex") + 1]
    assert "atrim=0:0.0333333333333333" in graph
    assert "atrim=0:0.0330" not in graph


@needs_ffmpeg
def test_frame_exact_total_and_apostrophe_path(tmp_path):
    e = tmp_path / "Anton's reels" / "edit" / "4821"
    e.mkdir(parents=True)
    source = make_video(e / "source.mp4", 64, 96, 1, color="blue")
    write_json(e / "cut.json", {"scale": "none", "sources": {"main": str(source)},
                              "ranges": [{"start": 0, "end": 1 / 30}] * 40})
    run_script("cut.py", e, cwd=e.parent.parent)
    assert cut.check_final(e / "final.mp4", 30, 40) == []
    assert cut.check_final(e / "final.mp4", 30, 20)
    assert "Anton's" not in (e / "clips" / "list.txt").read_text()
    assert not list(e.glob("*.part"))


@needs_ffmpeg
def test_two_transcription_sources_have_distinct_audio(project):
    import wave
    e = project / "edit" / "4821"
    e.mkdir()
    stubs = {"PYTHONPATH": str(Path(__file__).parent / "stubs")}
    for name, duration in (("first", 2), ("second", 3)):
        source = make_video(project / f"{name}.mp4", 64, 96, duration, color="blue")
        run_script("transcribe.py", e, source, cwd=project, env=stubs)
    with wave.open(str(e / "audio16k-first.wav")) as a, wave.open(str(e / "audio16k-second.wav")) as b:
        assert b.getnframes() > a.getnframes()
    assert not (e / "audio16k.wav").exists()
    assert not list(e.glob(".*.wav"))


def test_two_source_audio_selection_without_media_binary(project, monkeypatch):
    import transcribe
    e = project / "edit" / "4821"
    e.mkdir()
    monkeypatch.setattr(transcribe, "load_model", lambda *a: None)
    monkeypatch.setattr(transcribe, "probe", lambda p: {"dur": 1})
    monkeypatch.setattr(transcribe, "extract_audio", lambda src, out: out.write_bytes(src.read_bytes()))
    monkeypatch.setattr(transcribe, "words_of", lambda model, wav, lang: ("en", wav.read_text(),
        [{"text": wav.read_text(), "start": 0, "end": 0.5}]))
    for name in ("first", "second"):
        src = project / f"{name}.mp4"
        src.write_text(name)
        transcribe.cmd_full(SimpleNamespace(edit=str(e), source=str(src), force=False, model="local", compute="int8", language="en"))
        assert common.load_json(e / "transcripts" / f"{name}.json")["text"] == name
        assert (e / f"audio16k-{name}.wav").read_text() == name
    assert not (e / "audio16k.wav").exists()


def test_audio_extraction_publishes_unique_temp_atomically(tmp_path, monkeypatch):
    import transcribe
    out = tmp_path / "audio16k-source.wav"
    temps = []
    def encode(args):
        temp = Path(args[-1])
        assert temp != out and not out.exists()
        temps.append(temp)
        temp.write_bytes(b"audio")
    monkeypatch.setattr(transcribe, "run", encode)
    transcribe.extract_audio(tmp_path / "source.mp4", out)
    assert out.read_bytes() == b"audio" and not temps[0].exists()


def test_local_protocol_options_include_concat_and_skip_lavfi():
    args = common.local_media_args(["ffmpeg", "-f", "concat", "-safe", "0", "-i", "list.txt",
                                   "-f", "lavfi", "-i", "anullsrc", "-i", "a.mp4", "out.mp4"])
    assert args.count("-protocol_whitelist") == 2
    i = args.index("anullsrc")
    assert args[i - 2:i] == ["lavfi", "-i"]
    assert common.local_media_args(["ffprobe", "a.mp4"])[1:3] == ["-protocol_whitelist", "file,pipe"]


@pytest.mark.parametrize("module,helper", [("reels_common", "run"), ("patch_render", "run"),
    ("library_catalog", "run"), ("master_audio", "run"), ("poster", "sh")])
@pytest.mark.parametrize("tool", ["ffmpeg", "ffprobe"])
def test_subprocess_helpers_restrict_media_protocols(module, helper, tool, monkeypatch):
    mod = importlib.import_module(module)
    calls = []
    def execute(args, **kw):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", execute)
    getattr(mod, helper)([tool, "-i", "file.mp4", "out.mp4"] if tool == "ffmpeg" else [tool, "file.mp4"])
    args = calls[0]
    assert args[args.index("-protocol_whitelist") + 1] == "file,pipe"


def test_redirect_strips_credentials_and_query_keys(online):
    req = urllib.request.Request("https://a.test/start", headers={"Authorization": "Bearer secret",
        "x-api-key": "secret", "x-key": "secret", "Key": "secret", "Accept": "application/json"})
    redirected = online.SafeRedirect().redirect_request(req, None, 302, "Found", {},
        "https://b.test/end?key=secret&token=secret&keep=yes")
    assert {k.lower() for k in redirected.headers} == {"accept"}
    assert redirected.full_url == "https://b.test/end?keep=yes"
    same = online.SafeRedirect().redirect_request(req, None, 302, "Found", {}, "https://a.test/end")
    assert same.get_header("Authorization") == "Bearer secret"
    with pytest.raises(ValueError, match="HTTPS"):
        online.SafeRedirect().redirect_request(req, None, 302, "Found", {}, "http://b.test/")
    with pytest.raises(ValueError, match="allow-list"):
        online.SafeRedirect(lambda u: "a.test" in u).redirect_request(req, None, 302, "Found", {}, "https://b.test/")


def test_bounded_json_read(online, monkeypatch):
    monkeypatch.setattr(online, "MAX_JSON", 16)
    with pytest.raises(ValueError, match="20 MB"):
        online.read_json_response(io.BytesIO(b" " * 17))


def test_unique_download_parts(online, tmp_path, monkeypatch):
    dest = tmp_path / "clip.mp4"
    parts = []
    nested = [False]
    class Response(io.BytesIO):
        def read(self, n=-1):
            if not nested[0]:
                nested[0] = True
                parts.extend(tmp_path.glob("*.part"))
                online.download("https://test/second", dest)
            parts.extend(tmp_path.glob("*.part"))
            return super().read(n)
    monkeypatch.setattr(online, "open_url", lambda *a, **kw: Response(b"video"))
    online.download("https://test/first", dest)
    assert len(set(parts)) == 2
    assert dest.read_bytes() == b"video"
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("state", ["submitting", "unknown"])
def test_submitting_state_refuses_second_run(generation, tmp_path, monkeypatch, capsys, state):
    i = {"id": "b01", "kind": "broll", "source": "generated", "status": "pending",
         "gen": {"engine": "model", "job": {"state": state, "owner": "other"}}}
    plan = {"inserts": [i]}
    monkeypatch.setattr(generation, "edit_dir", lambda a: tmp_path)
    monkeypatch.setattr(generation, "plan_of", lambda e: (plan, ({}, None, None, None, None)))
    monkeypatch.setattr(generation, "effective", lambda s: ({"generate_now": True}, {}))
    monkeypatch.setattr(generation, "fal_submit", lambda *a: pytest.fail("second paid submit"))
    generation.cmd_run(SimpleNamespace(edit="4821", yes=True))
    assert "Check the provider dashboard" in capsys.readouterr().out
    write_json(tmp_path / "visual_plan.json", plan)
    assert generation.reserve_submit(tmp_path, copy.deepcopy(i)) is None


def test_submit_reservation_rechecks_fresh_plan(generation, tmp_path):
    i = {"id": "b01", "status": "pending", "gen": {"engine": "model"}}
    write_json(tmp_path / "visual_plan.json", {"inserts": [i]})
    first, second = copy.deepcopy(i), copy.deepcopy(i)
    assert generation.reserve_submit(tmp_path, first)
    assert generation.reserve_submit(tmp_path, second) is None
    saved = common.load_json(tmp_path / "visual_plan.json")["inserts"][0]["gen"]["job"]
    assert saved["state"] == "submitting" and saved["owner"] and saved["at"]


def test_resume_refuses_other_provider_before_key(generation, tmp_path, monkeypatch):
    i = {"id": "b01", "kind": "broll", "source": "generated", "status": "pending",
         "gen": {"engine": "model", "job": {"provider": "other", "request_id": "paid"}}}
    monkeypatch.setattr(generation, "edit_dir", lambda a: tmp_path)
    monkeypatch.setattr(generation, "plan_of", lambda e: ({"inserts": [i]}, ({}, None, None, None, None)))
    monkeypatch.setattr(generation, "effective", lambda s: ({"generate_now": True}, {}))
    monkeypatch.setattr(generation, "api_key", lambda k: pytest.fail("read unrelated key"))
    generation.cmd_run(SimpleNamespace(edit="4821", yes=True))


def test_new_job_does_not_reuse_old_raw(generation, tmp_path, monkeypatch):
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "b01.mp4").write_bytes(b"old")
    i = {"id": "b01", "gen": {"job": {"request_id": "new-request"}}}
    downloaded = []
    monkeypatch.setattr(generation, "fal_wait", lambda *a: "https://test/new")
    monkeypatch.setattr(generation, "download", lambda url, p: (p.write_bytes(b"new"), downloaded.append(p)))
    monkeypatch.setattr(generation, "safe_ingest", lambda e, i, p: p.read_bytes() == b"new")
    monkeypatch.setattr(generation, "put", lambda *a: None)
    generation.finish_job(tmp_path, i, "dummy")
    assert len(downloaded) == 1 and downloaded[0].name != "b01.mp4"
    assert i["gen"]["job"]["status"] == "DONE"


def test_lost_submit_response_is_unknown_and_never_resubmits(generation, tmp_path, monkeypatch):
    i = {"id": "b01", "kind": "broll", "source": "generated", "status": "pending",
         "dur": 3, "gen": {"engine": "model", "seconds": 4}}
    path = write_json(tmp_path / "visual_plan.json", {"inserts": [i]})
    monkeypatch.setattr(generation, "edit_dir", lambda a: tmp_path)
    monkeypatch.setattr(generation, "plan_of", lambda e: (common.load_json(path), ({}, None, None, None, None)))
    monkeypatch.setattr(generation, "effective", lambda s: ({"generate_now": True}, {}))
    monkeypatch.setattr(generation, "api_key", lambda k: "dummy")
    monkeypatch.setattr(generation, "offline", lambda: False)
    monkeypatch.setattr(generation, "check", lambda *a: ([], []))
    monkeypatch.setattr(generation, "build_prompt", lambda *a: "test")
    monkeypatch.setattr(generation, "err_text", lambda *a: "lost response")
    monkeypatch.setattr(generation, "put", lambda *a: None)
    calls = []
    def submit(*args):
        calls.append(args)
        job = common.load_json(path)["inserts"][0]["gen"]["job"]
        assert job["state"] == "submitting"  # durable before the external call
        raise TimeoutError("lost response")
    monkeypatch.setattr(generation, "fal_submit", submit)
    generation.cmd_run(SimpleNamespace(edit="4821", yes=True))
    assert common.load_json(path)["inserts"][0]["gen"]["job"]["state"] == "unknown"
    generation.cmd_run(SimpleNamespace(edit="4821", yes=True))
    assert len(calls) == 1


def test_rejected_submit_releases_reservation(generation, tmp_path, monkeypatch):
    import urllib.error
    i = {"id": "b01", "kind": "broll", "source": "generated", "status": "pending",
         "dur": 3, "gen": {"engine": "model", "seconds": 4}}
    path = write_json(tmp_path / "visual_plan.json", {"inserts": [i]})
    monkeypatch.setattr(generation, "edit_dir", lambda a: tmp_path)
    monkeypatch.setattr(generation, "plan_of", lambda e: (common.load_json(path), ({}, None, None, None, None)))
    monkeypatch.setattr(generation, "effective", lambda s: ({"generate_now": True}, {}))
    monkeypatch.setattr(generation, "api_key", lambda k: "dummy")
    monkeypatch.setattr(generation, "offline", lambda: False)
    monkeypatch.setattr(generation, "check", lambda *a: ([], []))
    monkeypatch.setattr(generation, "build_prompt", lambda *a: "test")
    calls = []
    def submit(*args):
        calls.append(args)
        raise urllib.error.HTTPError("https://queue.fal.run/x", 401, "Unauthorized", {}, None)
    monkeypatch.setattr(generation, "fal_submit", submit)
    generation.cmd_run(SimpleNamespace(edit="4821", yes=True))
    saved = common.load_json(path)["inserts"][0]
    assert "job" not in saved["gen"] and "nothing was charged" in saved["fallback"]
    generation.cmd_run(SimpleNamespace(edit="4821", yes=True))
    assert len(calls) == 2  # a definite rejection may be retried


def test_final_check_refuses_nonfinite_or_shortened_streams(monkeypatch):
    def answer(video_duration, audio_duration, frames):
        return SimpleNamespace(stdout=json.dumps({"streams": [
            {"codec_type": "video", "start_time": "0", "duration": video_duration, "nb_read_frames": frames},
            {"codec_type": "audio", "start_time": "0", "duration": audio_duration}]}))
    for result in (answer("nan", "nan", 30), answer("0.5", "0.5", 15)):
        monkeypatch.setattr(cut, "run", lambda *a, **k: result)
        assert cut.check_final("final.mp4", 30, 30)


def test_faces_paths_use_stdin_not_argv(monkeypatch):
    import faces
    monkeypatch.setattr(faces, "available", lambda: (True, ""))
    monkeypatch.setattr(faces, "model_path", lambda: Path("model.onnx"))
    calls = []
    def detect(args, **kw):
        paths = json.loads(kw["input"])
        calls.append(args)
        assert len(args) == 5 and len(paths) <= 400
        return SimpleNamespace(returncode=0, stdout=json.dumps([[] for _ in paths]))
    monkeypatch.setattr(faces.subprocess, "run", detect)
    assert len(faces.detect([Path("long-project-path") / ("a" * 200) / f"{k}.png" for k in range(1001)])) == 1001
    assert len(calls) == 3


def test_server_upload_timeout_closes_pipe_and_stops_both(online, tmp_path, monkeypatch):
    import matte_server as server
    processes = []
    class Process:
        def __init__(self, args, **kw):
            self.args, self.returncode = args, None
            self.stdout = io.BytesIO()
            processes.append(self)
        def communicate(self, timeout):
            assert timeout == 300
            assert processes[0].stdout.closed
            raise subprocess.TimeoutExpired(self.args, timeout)
        def poll(self):
            return self.returncode
        def terminate(self):
            self.returncode = -1
        def wait(self, timeout):
            return self.returncode
    monkeypatch.setattr(server, "ssh", lambda *a, **k: SimpleNamespace(stdout="/tmp/matte.abcdefgh\n"))
    monkeypatch.setattr(server.subprocess, "Popen", Process)
    engine = object.__new__(server.Server)
    with pytest.raises(subprocess.TimeoutExpired):
        engine.run(tmp_path, 30, 60, 60, tmp_path / "out.webm")
    assert processes[0].args[-1] == "." and len(processes[0].args) == 6
    assert all(p.returncode == -1 for p in processes)


def test_camera_shot_picks_its_source_file_on_a_multicamera_cut(tmp_path):
    # review of #8: source seconds of two cameras overlap; "source" picks the camera instead of a segment number
    import visual_plan as vp
    cap = {"segments": [{"i": 0, "source": "C:/x/cam-a.mov", "src_start": 10.0, "src_end": 14.0, "out_start": 0.0, "out_dur": 4.0},
                        {"i": 1, "source": "C:/x/cam-b.mov", "src_start": 11.0, "src_end": 15.0, "out_start": 4.0, "out_dur": 4.0}],
           "words": []}
    write_json(tmp_path / "camera.json", {"shots": [{"src": 12.0, "z": 1.1}]})
    with pytest.raises(SystemExit, match='add "source"'):
        vp.camera_shots(tmp_path, {"segments": []}, cap)
    write_json(tmp_path / "camera.json", {"shots": [{"src": 12.0, "source": "cam-b.mov", "z": 1.1}]})
    assert vp.camera_shots(tmp_path, {"segments": []}, cap)[0]["t"] == 5.0
