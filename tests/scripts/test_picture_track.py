"""The picture track of a rough cut (captions.json -> shots) apart from its sound (captions.json -> segments).

Requirements, in words (the two-track contract, core phase 0):
- cut.py writes the picture track next to the sound: one picture shot per sound segment, the same occurrence number,
  source and times, kind "video", no motion of its own; the sound records stay exactly as they were.
- A rough cut made before the picture track (no "shots" key) is read as before: its segments are its picture.
  An explicit empty list means "no picture" and is never replaced by the segments.
- Everything that asks "which picture is on screen at second t, and where does the picture jump" follows the picture
  shots, even where they cut elsewhere than the sound: the angle changes for faces and subtitles, the face zones without
  a plan, the camera's source seconds, the drift, the callout tracks and their fingerprint, the callout context, the
  plan's "hide the join" and "long shot" hints. Long-form camera planning refuses a picture that is not its sound.
- The picture's fingerprint (picture_id) is separate from the sound cut's (cut_id): a copy has none; a changed
  picture is recorded in the plan and reported without rebuilding the plan's speech spans.
"""
import json
from pathlib import Path

import pytest

from conftest import needs_ffmpeg, run_script, write_json
from test_callouts import KIT, needs_node

KIT_ANCHOR = KIT / "kit" / "anchor.ts"

FPS = 30

# the sound cuts at 3.0 s (source a, then b); the picture cuts at 2.0 s and 4.5 s (a, then c, then a again)
SOUND = [{"i": 0, "source": "a", "src_start": 10.0, "src_end": 13.0, "out_start": 0.0, "out_dur": 3.0, "speed": 1.0,
          "beat": "hook"},
         {"i": 1, "source": "b", "src_start": 20.0, "src_end": 23.0, "out_start": 3.0, "out_dur": 3.0, "speed": 1.0,
          "beat": "end"}]
PICTURE = [{"i": 0, "kind": "video", "source": "a", "src_start": 10.0, "src_end": 12.0, "speed": 1.0, "out_start": 0.0,
            "out_dur": 2.0, "move": "none", "look": None},
           {"i": 1, "kind": "video", "source": "c", "src_start": 50.0, "src_end": 52.5, "speed": 1.0, "out_start": 2.0,
            "out_dur": 2.5, "move": "none", "look": None},
           {"i": 2, "kind": "video", "source": "a", "src_start": 14.5, "src_end": 16.0, "speed": 1.0, "out_start": 4.5,
            "out_dur": 1.5, "move": "none", "look": None}]


def divergent():
    return {"duration": 6.0, "segments": [dict(g) for g in SOUND], "shots": [dict(g) for g in PICTURE],
            "picture_id": "0123456789ab", "words": []}


def edit_with(project, cap, name="p"):
    e = project / "edit" / name
    write_json(e / "captions.json", cap)
    return e


# --- what cut.py writes -------------------------------------------------------------------------------------------

@needs_ffmpeg
def test_cut_writes_the_picture_track_as_a_copy_of_the_sound(project):
    from test_media import cut_project
    e = cut_project(project)
    run_script("cut.py", "edit/4821", cwd=project)
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    edl = json.loads((e / "edl.json").read_text(encoding="utf-8"))
    want = [{"i": g["i"], "kind": "video", "source": g["source"], "src_start": g["src_start"], "src_end": g["src_end"],
             "speed": g["speed"], "out_start": g["out_start"], "out_dur": g["out_dur"], "move": "none", "look": None}
            for g in cap["segments"]]
    assert cap["shots"] == want and edl["shots"] == want
    assert "picture_id" not in cap  # a copy has no picture fingerprint
    # the sound records keep their shape: speech checks and speech_mask --edl read only them
    assert list(cap) == ["duration", "segments", "shots", "words", "leveling"]
    assert [list(r) for r in edl["ranges"]] == [["source", "start", "end", "speed", "beat"]] * 3


# --- reading the picture track -----------------------------------------------------------------------------------

def test_the_picture_falls_back_to_the_segments_only_when_shots_are_absent():
    import pic_track as pt
    old = {"duration": 6.0, "segments": [dict(g) for g in SOUND], "words": []}
    got = pt.pic_shots(old)
    assert [(g["i"], g["kind"], g["source"], g["out_start"], g["out_dur"], g["move"]) for g in got] == \
        [(0, "video", "a", 0.0, 3.0, "none"), (1, "video", "b", 3.0, 3.0, "none")]
    assert pt.pic_shots(divergent()) == PICTURE
    assert pt.pic_shots({"duration": 6.0, "segments": [dict(g) for g in SOUND], "shots": []}) == []
    assert pt.follows_sound(old) and not pt.follows_sound(divergent())


def test_the_angle_changes_are_the_picture_joins(project):
    import faces as fc
    e = edit_with(project, divergent())
    assert fc.source_cuts(e) == [2.0, 4.5]  # not the sound's 3.0


def test_face_zones_without_a_plan_are_per_picture_shot(project):
    import faces as fc
    e = edit_with(project, divergent())
    assert fc.segments_of(e) == [("k00", 0.0, 2.0, "hook"), ("k01", 2.0, 4.5, "hook"), ("k02", 4.5, 6.0, "end")]


def test_subtitle_faces_stay_on_their_picture_angle(project):
    # the picture changes at 2.1 s, the sound at 3.0 s: a face of the other shot must not leak over the join (the join
    # sits between two face samples, 2.0 and 2.25, as joins usually do)
    import faces as fc
    import textcheck as tc
    from test_board import props
    e = project / "edit" / "t"
    samples = [{"t": k * 0.25, "faces": [[400, 400, 280, 360, 0.95] if k * 0.25 < 2.1 else [100, 1000, 200, 260, 0.95]]}
               for k in range(25)]
    write_json(e / "faces.json", {"video": "final.mp4", "step": 0.25, "geometry": "cover", "w": 1080, "h": 1920,
                                  "samples": samples, "filter": {"v": fc.FILTER_V}})
    cap = divergent()
    cap["shots"][0]["out_dur"] = cap["shots"][0]["src_end"] - 10.0 + 0.1
    cap["shots"][1]["out_start"], cap["shots"][1]["out_dur"] = 2.1, 2.4
    near = tc.face_source(e, {}, props(captions=cap), FPS)
    assert near(2.05) and all(f == [370, 370, 340, 420] for f in near(2.05))
    assert near(2.15) and all(f == [70, 970, 260, 320] for f in near(2.15))


def test_a_face_sample_on_the_join_belongs_to_the_shot_it_starts(project):
    # a face sample taken exactly at a picture join (2.0 s here; joins land on the 0.25 s sample grid whenever the cut
    # does) is the next shot's face: before the join it is not on screen, so it must not count there
    import faces as fc
    import textcheck as tc
    from test_board import props
    e = project / "edit" / "t"
    samples = [{"t": k * 0.25, "faces": [[400, 400, 280, 360, 0.95] if k * 0.25 < 2.0 else [100, 1000, 200, 260, 0.95]]}
               for k in range(25)]
    write_json(e / "faces.json", {"video": "final.mp4", "step": 0.25, "geometry": "cover", "w": 1080, "h": 1920,
                                  "samples": samples, "filter": {"v": fc.FILTER_V}})
    near = tc.face_source(e, {}, props(captions=divergent()), FPS)
    assert near(1.9) and all(f == [370, 370, 340, 420] for f in near(1.9))  # not the 2.0 s sample of the next shot
    assert near(2.0) and all(f == [70, 970, 260, 320] for f in near(2.0))  # at the join: the new shot's face
    assert near(1.95) and all(f == [370, 370, 340, 420] for f in near(1.95))


def test_picture_defects_are_sorted_by_the_picture_source(project, monkeypatch):
    import defects
    import faces as fc
    e = edit_with(project, divergent())
    (e / "final.mp4").write_bytes(b"a rough cut")
    seen = {}
    monkeypatch.setattr(defects, "scan", lambda video, step: {"step": step, "samples": []})
    monkeypatch.setattr(fc, "model_path", lambda: Path("yunet.onnx"))

    def spy(data, segs, words=(), turn=None, blur=None):
        seen["segs"] = segs
        return [], {"on_camera": False, "with_face": 0, "samples": 0}
    monkeypatch.setattr(defects, "find", spy)
    monkeypatch.setattr("sys.argv", ["defects.py", str(e)])
    defects.main()
    assert seen["segs"] == PICTURE
    assert [defects.source_at(seen["segs"], t) for t in (1.0, 2.5, 5.0)] == ["a", "c", "a"]


def test_camera_source_seconds_map_through_the_picture(project):
    import vp_camera
    assert vp_camera.src_to_out(51.0, divergent(), source="c") == pytest.approx(3.0)
    assert vp_camera.src_to_out(15.0, divergent(), source="a") == pytest.approx(5.0)


def test_a_fill_shot_takes_no_source_second(project):
    import vp_camera
    # the voice runs 0-4 s from source seconds 0-4; the picture shows source a 0-2 s, then a style background
    cap = {"duration": 4.0, "picture_id": "x",
           "segments": [{"i": 0, "source": "a", "src_start": 0.0, "src_end": 4.0, "out_start": 0.0, "out_dur": 4.0}],
           "shots": [{"i": 0, "kind": "video", "source": "a", "src_start": 0.0, "src_end": 2.0, "speed": 1.0,
                      "out_start": 0.0, "out_dur": 2.0, "move": "none", "look": None},
                     {"i": 1, "kind": "fill", "source": None, "src_start": 0.0, "src_end": 2.0, "speed": 1.0,
                      "out_start": 2.0, "out_dur": 2.0, "move": "none", "look": None}]}
    # 1.0 is also a conventional coordinate of the fill shot: it is not a second "several segments" hit
    assert vp_camera.src_to_out(1.0, cap) == pytest.approx(1.0)
    with pytest.raises(SystemExit):  # source second 3.0 is heard, but not shown: the camera has nothing to point at
        vp_camera.src_to_out(3.0, cap)


def test_a_track_breaks_at_the_picture_joins():
    import track
    assert track.breaks_in(divergent(), 1.0, 5.0) == {round(1.0 * track.FPS), round(3.5 * track.FPS)}


def test_the_track_fingerprint_follows_the_picture(project):
    import vp_callouts as vc
    e = edit_with(project, divergent())
    (e / "final.mp4").write_bytes(b"a rough cut")
    c = {"anchor": [300, 1150], "start": 1.0, "dur": 2.0}
    k0 = vc.track_key(e, c)
    cap = divergent()
    cap["shots"][1]["out_start"], cap["shots"][0]["out_dur"] = 2.3, 2.3  # the picture re-cut; the sound did not move
    write_json(e / "captions.json", cap)
    assert vc.track_key(e, c) != k0


def test_the_callout_context_carries_the_picture(project):
    import vp_callouts as vc
    e = edit_with(project, divergent())
    assert vc.callout_context(e, {"duration": 6.0})[0] == PICTURE


def test_plan_hints_look_at_the_picture_joins(project):
    from test_plan import LINES, captions, load_plan, plan_project
    e = plan_project(project)
    cap = captions()
    # one picture join at 12.0 s; both picture shots are long, though every sound segment is 4 s
    cap["shots"] = [{"i": 0, "kind": "video", "source": None, "src_start": 0.0, "src_end": 12.0, "speed": 1.0,
                     "out_start": 0.0, "out_dur": 12.0, "move": "none", "look": None},
                    {"i": 1, "kind": "video", "source": None, "src_start": 40.0, "src_end": 58.0, "speed": 1.0,
                     "out_start": 12.0, "out_dur": 18.0, "move": "none", "look": None}]
    cap["picture_id"] = "0123456789ab"
    write_json(e / "captions.json", cap)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    plan = load_plan(e)
    hints = {round(g["start"], 1): " ".join(g.get("hints", [])) for g in plan["segments"]}
    joins = sorted(t for t, h in hints.items() if "a segment join at the start" in h)
    assert joins == [12.0], hints
    assert "a 12.0 s segment without a cut" in hints[3.0] and "a 18.0 s segment without a cut" in hints[17.0], hints
    assert len(LINES) == len(plan["segments"])


def test_long_form_camera_refuses_a_picture_that_is_not_its_sound():
    import longform as lf
    from test_longform_camera import SRC_H, SRC_W
    data = {"step": 0.25, "frame": [25, 340, 1030, 1240], "source": {"w": SRC_W, "h": SRC_H},
            "samples": [{"t": k * 0.25, "faces": [[250, 600, 100, 130, 0.9]]} for k in range(25)]}
    cap = divergent()
    cap["words"] = [{"text": "one", "start": 0.5, "end": 1.0, "seg": 0}, {"text": "two", "start": 3.5, "end": 4.0, "seg": 1}]
    old = {k: v for k, v in cap.items() if k not in ("shots", "picture_id")}
    lf.camera_plan(Path("."), data, old, {}, "guest")  # a cut whose picture is its sound: planned as before
    with pytest.raises(SystemExit) as ex:
        lf.camera_plan(Path("."), data, cap, {}, "guest")
    assert "picture" in str(ex.value)


# --- the picture's fingerprint ------------------------------------------------------------------------------------

def test_the_sound_fingerprint_ignores_the_picture():
    # a guard: shots and picture_id must never change cut_id, or every old plan would rebuild its spans
    from vp_core import cut_id
    cap = divergent()
    plain = {k: v for k, v in cap.items() if k not in ("shots", "picture_id")}
    assert cut_id(cap) == cut_id(plain)


def test_picture_id_is_none_for_a_copy_and_moves_with_the_picture():
    import pic_track as pt
    copy = {"duration": 6.0, "segments": [dict(g) for g in SOUND], "words": []}
    copy["shots"] = pt.copy_shots(copy["segments"])
    assert pt.picture_id(copy) is None
    p0 = pt.picture_id(divergent())
    assert p0 and len(p0) == 12
    moved = divergent()
    moved["shots"][2]["src_start"] = 14.0
    assert pt.picture_id(moved) != p0


def test_validate_records_a_new_picture_without_rebuilding_the_spans(project):
    from test_plan import captions, load_plan, plan_project
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    before = load_plan(e)
    assert "picture_id" not in before  # a copy: nothing new in the plan
    cap = captions()
    cap["shots"] = [{"i": 0, "kind": "video", "source": None, "src_start": 0.0, "src_end": 30.0, "speed": 1.0,
                     "out_start": 0.0, "out_dur": 30.0, "move": "none", "look": None}]
    cap["picture_id"] = "0123456789ab"
    write_json(e / "captions.json", cap)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    plan = load_plan(e)
    assert plan["picture_id"] == "0123456789ab"
    assert plan["segments"] == before["segments"] and plan["captions_id"] == before["captions_id"]
    assert "picture" in r.stdout


# --- the kit -------------------------------------------------------------------------------------------------------

@needs_node
def test_the_kit_reads_the_same_picture_track(tmp_path):
    import subprocess
    cases = [divergent(), {"duration": 6.0, "segments": SOUND, "words": []},
             {"duration": 6.0, "segments": SOUND, "shots": [], "words": []}]
    data = tmp_path / "cases.json"
    data.write_text(json.dumps(cases), encoding="utf-8")
    code = ("const m = await import(process.argv[1]); const fs = await import('node:fs');"
            "const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));"
            "console.log(JSON.stringify(cases.map((c) => [m.picShots(c).map((g) => [g.i, g.out_start, g.out_dur]),"
            " [1.0, 2.5, 5.0].map((t) => m.driftZoom(m.picShots(c), t))])));")
    r = subprocess.run(["node", "--input-type=module", "-e", code, KIT_ANCHOR.as_uri(), str(data)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got[0][0] == [[0, 0.0, 2.0], [1, 2.0, 2.5], [2, 4.5, 1.5]]
    assert got[1][0] == [[0, 0.0, 3.0], [1, 3.0, 3.0]]
    assert got[2][0] == []
    import vp_callouts as vc
    assert got[0][1] == pytest.approx([vc.drift_zoom(PICTURE, t) for t in (1.0, 2.5, 5.0)])
