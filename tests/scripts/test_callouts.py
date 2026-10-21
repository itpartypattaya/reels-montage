"""Callouts (a dot on an object, a leader line, a label plate): visual_plan.py `--kind callout` and the kit's
CalloutLayer. The requirement behind every test: the label must point at the object where the viewer sees it, so its
anchor is projected through the same camera and drift the kit draws the video with, and the plan check refuses a
callout that would land on a face, the subtitles or the app's UI, leave the frame, or sit on a picture that is not there.
"""
import json
import math
import shutil
import subprocess

import pytest

from conftest import CORE, ffmpeg, needs_ffmpeg, needs_pillow, run_script, write_json
from test_plan import captions, faces_json, load_plan, plan_project

KIT = CORE.parent / "assets" / "remotion-kit"


def _node_strips_types():
    """node 22.6+ runs a .ts file by stripping its types (on by default from 23.6; 22.6-23.5 need a flag)."""
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-p", "process.versions.node"], capture_output=True, text=True)
    major, minor = (int(v) for v in r.stdout.strip().split(".")[:2])
    return (major, minor) >= (23, 6)


HAS_NODE = _node_strips_types()
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node 23.6+ is needed (it runs the kit's TypeScript as is)")

FACE = [380, 600, 260, 340]  # x 380-640, y 600-940: a talking head in the upper middle


def vp():
    import visual_plan
    return visual_plan


# ── the projection: where a point of the rough cut is on screen ──

def test_anchor_lands_where_the_kit_draws_the_frame_point():
    v = vp()
    segs = [{"i": 0, "out_start": 0.0, "out_dur": 4.0}, {"i": 1, "out_start": 4.0, "out_dur": 4.0}]
    # no camera: the template's drift scales each segment around the frame's center, 1 -> 1.05 on even segments and
    # 1.05 -> 1 on odd ones (ReelKit Footage)
    assert v.anchor_on_screen(1040, 960, 2.0, [], segs, True, 8.0) == pytest.approx((1052.5, 960.0))
    assert v.anchor_on_screen(540, 1160, 4.0, [], segs, True, 8.0) == pytest.approx((540.0, 1170.0))  # odd: from 1.05
    # no drift and no camera (a per-video choice): the point stays
    assert v.anchor_on_screen(700, 1100, 2.0, [], segs, False, 8.0) == pytest.approx((700.0, 1100.0))
    # camera.json: x' = (x - cx) * z + 540 (references/camera.md), the shot's own push-in growing over the shot
    shots = [{"t": 0.0, "z": 1.2, "cx": 540.0, "cy": 960.0, "drift": 0.0, "whip": False}]
    assert v.anchor_on_screen(640, 1160, 1.0, shots, segs, False, 8.0) == pytest.approx((660.0, 1200.0))
    shots = [{"t": 0.0, "z": 1.0, "cx": 540.0, "cy": 960.0, "drift": 0.1, "whip": False}]
    assert v.anchor_on_screen(740, 960, 4.0, shots, segs, False, 8.0) == pytest.approx((750.0, 960.0))


CASES = [  # shared control points: Python and the kit must agree on every one
    {"x": 300, "y": 1150, "t": t, "camera": cam, "drift": drift, "end": 9.0,
     "segments": [{"i": 0, "out_start": 0.0, "out_dur": 3.0}, {"i": 1, "out_start": 3.0, "out_dur": 3.5},
                  {"i": 2, "out_start": 6.5, "out_dur": 2.5}]}
    for t in (0.0, 1.3, 3.0, 4.1, 6.49, 6.51, 8.9)
    for cam, drift in (([], True), ([], False),
                       ([{"t": 0.5, "z": 1.15, "cx": 600.0, "cy": 900.0, "drift": 0.04, "whip": False},
                         {"t": 4.0, "z": 1.3, "cx": 420.0, "cy": 1100.0, "drift": 0.0, "whip": True},
                         {"t": 6.5, "z": 1.05, "cx": 540.0, "cy": 960.0, "drift": 0.02, "whip": False}], False))
] + [{"x": 980, "y": 260, "t": 4.0 + k / 30, "camera": [
    {"t": 0.0, "z": 1.0, "cx": 540.0, "cy": 960.0, "drift": 0.0, "whip": False},
    {"t": 4.0, "z": 1.3, "cx": 900.0, "cy": 300.0, "drift": 0.05, "whip": True}],  # the clamp at the frame's corner
    "drift": False, "end": 9.0, "segments": []} for k in range(9)]


def run_kit(fn, cases, tmp_path):
    """The kit's own TypeScript (kit/anchor.ts) on the cases, run by node: [result, …]."""
    src = (KIT / "kit" / "anchor.ts").as_uri()
    data = tmp_path / "cases.json"
    data.write_text(json.dumps(cases), encoding="utf-8")
    code = ("const m = await import(process.argv[1]); const fs = await import('node:fs');"
            "const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));"
            f"console.log(JSON.stringify(cases.map((c) => m.{fn})));")
    r = subprocess.run(["node", "--input-type=module", "-e", code, src, str(data)], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_python_and_the_kit_project_anchors_the_same(tmp_path):
    v = vp()
    kit = run_kit("anchorOnScreen(c.x, c.y, c.t, c.camera, c.segments, c.drift, c.end)", CASES, tmp_path)
    for c, k in zip(CASES, kit):
        py = v.anchor_on_screen(c["x"], c["y"], c["t"], c["camera"], c["segments"], c["drift"], c["end"])
        assert [k["x"], k["y"]] == pytest.approx(list(py), abs=0.01), c


GEO = [{"x": x, "y": y, "side": side, "below": below, "w": w, "sub": sub, "variant": vr, "r": r, "to": to}
       for x, y in ((300, 1150), (900, 700)) for side in ("left", "right") for below in (False, True)
       for w, sub in ((248, True), (400, False))
       for vr, r, to in (("tag", 0, None), ("line", 0, None), ("badge", 0, None), ("ring", 73.5, None),
                         ("dimension", 0, [x + 310, y - 120]), ("dimension", 0, [x + 40, y + 400]))]


def flat(x):
    """Every number of a nested structure, in order (pytest.approx compares flat lists only)."""
    if isinstance(x, dict):
        return [v for k in sorted(x) for v in flat(x[k])]
    if isinstance(x, (list, tuple)):
        return [v for y in x for v in flat(y)]
    return [x]


@needs_node
def test_python_and_the_kit_lay_out_a_callout_the_same(tmp_path):
    # every variant: the plan checks the boxes and lines where the kit draws them
    v = vp()
    kit = run_kit("calloutGeometry(c.x, c.y, c.side, c.below, c.w, c.sub, c.variant, c.r, c.to)", GEO, tmp_path)
    for c, k in zip(GEO, kit):
        py = v.callout_geometry(c["x"], c["y"], c["side"], c["below"], c["w"], c["sub"], c["variant"], c["r"], c["to"])
        assert sorted(k) == sorted(py) and flat(k) == pytest.approx(flat(py)), c


PATHS = [{"path": p, "anchor": [500, 900], "t": t}
         for p in (None, [[0, 300, 1100]], [[0.5, 300, 1100, 1, 1], [1.5, 420, 1000, 0, 1.4], [2.0, 450, 980, 1]])
         for t in (0.0, 0.5, 0.9, 1.5, 1.75, 2.0, 3.0)]


@needs_node
def test_python_and_the_kit_move_an_anchor_the_same(tmp_path):
    # keys, a track, a person: the dot is where the plan checked it, its fade and a ring's scale too
    v = vp()
    kit = run_kit("pathAt(c.path, c.anchor, c.t)", PATHS, tmp_path)
    for c, k in zip(PATHS, kit):
        assert [k["x"], k["y"], k["v"], k["s"]] == pytest.approx(list(v.path_at(c["path"], c["anchor"], c["t"]))), c
    zs = run_kit("zoomAt(c.t, c.camera, c.segments, c.drift, c.end)", CASES, tmp_path)
    for c, z in zip(CASES, zs):
        assert z == pytest.approx(v.zoom_at(c["t"], c["camera"], c["segments"], c["drift"], c["end"])), c


@needs_node
def test_python_and_the_kit_time_the_entrance_the_same(tmp_path):
    v = vp()
    cases = [{"tin": tin, "sub": sub} for tin in (0, 5, 8, 10, 14, 16, 18) for sub in (False, True)]
    kit = run_kit("calloutEntrance(c.tin, c.sub)", cases, tmp_path)
    assert kit == [v.callout_entrance(c["tin"], c["sub"]) for c in cases]


def test_a_label_in_a_script_without_capitals_keeps_its_size():
    # Fable review: Thai and Chinese letters were counted as narrow punctuation, the label came out narrow and the kit
    # shrank the title to fit it (Thai ~38 px, Chinese ~21 px instead of 52)
    v = vp()
    pad = 2 * v.CALLOUT["pad_x"]
    assert v.callout_width(["โซฟา"]) >= 4 * 0.6 * 52 + pad  # Thai "sofa", 4 letters
    assert v.callout_width(["沙发"]) >= 2 * 1.0 * 52 + pad  # Chinese "sofa": two full-width characters


def test_the_label_points_away_from_its_dot():
    v = vp()
    g = v.callout_geometry(300, 1150, "right", False, 248, True)
    x, y, w, h = g["plate"]
    assert g["elbow"][0] > 300 and g["elbow"][1] < 1150  # up and to the right
    assert x == g["end"][0] and y < g["end"][1] < y + h  # the line meets the plate's side, at the title
    g = v.callout_geometry(300, 1150, "left", True, 248, False)
    x, y, w, h = g["plate"]
    assert g["elbow"][0] < 300 and g["elbow"][1] > 1150 and x + w == g["end"][0]


# ── the plan: add, validate, export ──

def add(project, *args, check=True):
    return run_script("visual_plan.py", "add", "edit/4821", "--kind", "callout", *args, cwd=project, check=check)


def validate(project):
    return run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)


def callout_project(project, reel=None):
    e = plan_project(project, reel)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    faces_json(e, list(FACE))
    return e


LAPTOP = ["--variant", "tag", "--lines", "LAPTOP", "WORK MACHINE", "--what", "the laptop on the desk",
          "--why", "names the tool he talks about"]


def test_a_callout_is_added_planned_and_becomes_ready(project):
    e = callout_project(project)
    r = add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    assert "experimental" in r.stdout
    c = next(i for i in load_plan(e)["inserts"] if i["kind"] == "callout")
    assert c["id"] == "l01" and c["status"] == "planned" and c["variant"] == "tag" and c["anchor"] == [300, 1150]
    assert c["side"] == "right" and c["text"]["lines"] == ["LAPTOP", "WORK MACHINE"] and c["w"] > 0
    r = validate(project)
    assert r.returncode == 0, r.stdout
    assert next(i for i in load_plan(e)["inserts"] if i["kind"] == "callout")["status"] == "ready"


def test_a_callout_takes_the_side_with_room_by_default(project):
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "860,1150", *LAPTOP)
    assert next(i for i in load_plan(e)["inserts"] if i["kind"] == "callout")["side"] == "left"


def test_a_label_on_the_face_is_refused(project):
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,820", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "l01" in r.stdout and "face" in r.stdout, r.stdout


def test_a_leader_line_across_the_face_is_refused(project):
    # the dot under the face's right corner, the label right of the face and clear of it: the line still cuts the
    # face's corner on its way up
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "575,1000", "--side", "right", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "line" in r.stdout and "face" in r.stdout, r.stdout


def test_a_callout_on_the_subtitles_is_refused(project):
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "200,1380", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "subtitle" in r.stdout, r.stdout


def test_a_dot_off_the_frame_and_a_label_in_the_ui_are_refused(project):
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "1100,1150", "--side", "left", *LAPTOP)
    add(project, "--at", "word:speed#1", "--dur", "2.4", "--anchor", "860,1150", "--side", "right", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1, r.stdout
    assert "l01" in r.stdout and "frame" in r.stdout
    assert "l02" in r.stdout and "safe zone" in r.stdout


def test_a_camera_push_in_is_taken_into_account(project):
    # the same callout passes on the plain frame; a push-in of camera.json carries its dot past the frame's edge
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "950,1150", "--side", "left", *LAPTOP)
    assert validate(project).returncode == 0
    write_json(e / "camera.json", {"shots": [{"at": 0, "z": 1.5, "cx": 540, "cy": 960}]})
    r = validate(project)
    assert r.returncode == 1 and "l01" in r.stdout and "frame" in r.stdout, r.stdout


def test_a_shot_change_under_a_callout_is_refused(project):
    e = callout_project(project)
    write_json(e / "camera.json", {"shots": [{"at": 0, "z": 1.0, "cx": 540, "cy": 960},
                                             {"at": 5.0, "z": 1.1, "cx": 540, "cy": 960}]})
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)  # 4.6-7.0 s
    r = validate(project)
    assert r.returncode == 1 and "shot" in r.stdout, r.stdout


def test_a_callout_over_a_full_scene_is_refused(project):
    callout_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "slogan", "--at", "word:speed#1",
               "--dur", "2.0", "--lines", "speed wins", "--source", "speech", "--what", "the main thought",
               "--why", "a punch", cwd=project)
    add(project, "--at", "word:Remember#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "l01" in r.stdout and "c01" in r.stdout, r.stdout


def test_a_callout_too_short_to_read_is_refused(project):
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "1.0", "--anchor", "300,1150", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "read" in r.stdout, r.stdout


def test_callouts_come_one_at_a_time(project):
    callout_project(project)
    add(project, "--at", "4.6", "--dur", "3.0", "--anchor", "120,1150", *LAPTOP)
    add(project, "--at", "4.8", "--dur", "3.0", "--anchor", "900,250", "--side", "left", "--below", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "0.6 s" in r.stdout and "1 error(s)" in r.stdout, r.stdout  # that rule alone


def test_at_most_two_callouts_at_once(project):
    callout_project(project)
    add(project, "--at", "4.0", "--dur", "4.0", "--anchor", "120,1050", "--side", "right", "--below", *LAPTOP)
    add(project, "--at", "4.7", "--dur", "3.0", "--anchor", "900,1150", "--side", "left", *LAPTOP)
    add(project, "--at", "5.4", "--dur", "2.4", "--anchor", "900,250", "--side", "left", "--below", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "at once" in r.stdout, r.stdout


def test_a_number_on_a_callout_needs_its_source(project):
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", "--variant", "tag",
        "--lines", "LAPTOP", "16 GB RAM", "--what", "the laptop", "--why", "the spec matters")
    r = validate(project)
    assert r.returncode == 1 and "source" in r.stdout, r.stdout


def test_the_framed_format_is_refused_for_now(project):
    callout_project(project, {"format": "framed"})
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "l01" in r.stdout and "framed" in r.stdout, r.stdout


def rough_cut(e, moving):
    """final.mp4: a still picture (color bars), or the same picture panning like a handheld walk through a room."""
    ffmpeg("-f", "lavfi", "-i", "smptebars=size=1080x1920:rate=30:duration=10" + (",scroll=h=0.004" if moving else ""),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", e / "final.mp4")


@needs_ffmpeg
def test_a_callout_on_a_moving_picture_is_refused(project):
    # a real apartment tour shot by hand: the sofa moved 200+ px per 0.25 s, a dot set on it pointed at the wall
    # a moment later. The dot follows the camera, not the footage, so the picture under it must hold still
    e = callout_project(project)
    rough_cut(e, moving=True)
    r = add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    assert "moves" in r.stdout
    r = validate(project)
    assert r.returncode == 1 and "l01" in r.stdout and "moves under the dot" in r.stdout, r.stdout


@needs_ffmpeg
def test_a_still_picture_under_the_dot_passes(project):
    e = callout_project(project)
    rough_cut(e, moving=False)
    r = add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    assert "holds still" in r.stdout
    r = validate(project)
    assert r.returncode == 0 and "moves under the dot" not in r.stdout, r.stdout


@needs_ffmpeg
def test_a_callout_planned_before_the_rough_cut_becomes_ready_with_it(project):
    # Codex review: validate measured the picture and kept the measurement in the callout in memory, so the "did the
    # plan change during the check" guard saw a change and never saved the status: the callout stayed planned
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)  # no final.mp4 yet
    rough_cut(e, moving=False)
    r = validate(project)
    assert r.returncode == 0, r.stdout
    assert next(i for i in load_plan(e)["inserts"] if i["kind"] == "callout")["status"] == "ready", r.stdout


@needs_ffmpeg
def test_motion_is_measured_on_the_frame_the_kit_draws(project):
    # the kit stretches the rough cut to 1080x1920; a 720x1280 file was cropped at 1080x1920 coordinates (Codex review)
    # a 720x1280 file: still, but for a band panning at its bottom (y 980-1280 of 1280). The dot at (300, 1150) of the
    # 1080x1920 frame is on the still part (y 767 of the file); the same numbers read in the file land in the band
    e = callout_project(project)
    ffmpeg("-f", "lavfi", "-i", "smptebars=size=720x1280:rate=30:duration=10", "-f", "lavfi",
           "-i", "smptebars=size=720x300:rate=30:duration=10,scroll=h=0.01", "-filter_complex", "[0][1]overlay=0:980",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", e / "final.mp4")
    r = add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    assert "holds still" in r.stdout, r.stdout
    r = validate(project)
    assert r.returncode == 0 and "moves under the dot" not in r.stdout, r.stdout


def test_an_unmeasured_picture_is_named(project):
    e = callout_project(project)
    (e / "final.mp4").write_bytes(b"not a video")
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    r = validate(project)
    assert "not measured" in r.stdout, r.stdout


def test_two_callouts_overlapping_between_samples_are_refused(project):
    # [4.0, 6.0) and [5.9, 8.3) share no 0.25 s sample: the overlap in their last 0.1 s went unseen (Codex review)
    callout_project(project)
    add(project, "--at", "4.0", "--dur", "2.0", "--anchor", "300,1150", *LAPTOP)
    add(project, "--at", "5.9", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "runs into" in r.stdout, r.stdout


def test_the_first_callouts_line_under_the_second_label_is_refused(project):
    # the later label sits on the earlier callout's line, the later line is clear of the earlier label: only the
    # later line was checked against the earlier label (Codex review)
    callout_project(project)
    add(project, "--at", "4.0", "--dur", "3.0", "--anchor", "600,1200", "--side", "left", *LAPTOP)
    add(project, "--at", "4.7", "--dur", "2.3", "--anchor", "720,1225", "--side", "left", "--variant", "tag",
        "--lines", "TV", "--what", "the TV", "--why", "names the screen he points at")
    r = validate(project)
    assert r.returncode == 1 and "runs into" in r.stdout, r.stdout


def test_the_hook_of_this_export_is_checked(project):
    # validate --hook says the export will draw a hook headline: a label in its box is refused then, not only after
    # a previous export stored the hook in the plan (Codex review)
    callout_project(project)
    add(project, "--at", "0.4", "--dur", "2.0", "--anchor", "200,470", *LAPTOP)  # label y 345-465: above the face
    r = validate(project)
    assert r.returncode == 0, r.stdout
    r = run_script("visual_plan.py", "validate", "edit/4821", "--hook", cwd=project, check=False)
    assert r.returncode == 1 and "hook" in r.stdout, r.stdout


def test_a_whip_into_the_callouts_first_frames_is_refused(project):
    # a whip that starts with the callout moves the picture under the dot for 7 frames (Codex review)
    e = callout_project(project)
    write_json(e / "camera.json", {"shots": [{"at": 0, "z": 1.0, "cx": 540, "cy": 960},
                                             {"at": "word:resume#1", "z": 1.15, "cx": 540, "cy": 960, "whip": True}]})
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "shot" in r.stdout, r.stdout


def test_graphics_over_the_dot_are_refused(project):
    # a card zone over the dot, clear of the label: a popup meme or a card drawn there would hide the dot (Antigravity
    # review: only the label was checked against the other graphics)
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    # 15 px under-left of the dot's center: on the dot's disc, off the line (it leaves the dot up and to the right)
    run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "4", "--to", "8", "--box", "280,1155,15,15",
               "--what", "a card", cwd=project)
    r = validate(project)
    assert r.returncode == 1 and "l01" in r.stdout and "runs into 'a card'" in r.stdout, r.stdout


def test_two_crossing_lines_are_refused(project):
    # the lines cross, the labels and each line's own label stay apart (Antigravity review)
    callout_project(project)
    add(project, "--at", "4.0", "--dur", "3.0", "--anchor", "300,1150", "--side", "right", *LAPTOP)
    add(project, "--at", "4.7", "--dur", "2.3", "--anchor", "400,1150", "--side", "left", "--variant", "tag",
        "--lines", "TV", "--what", "the TV", "--why", "names the screen he points at")
    r = validate(project)
    assert r.returncode == 1 and "l02" in r.stdout and "runs into l01" in r.stdout, r.stdout


def test_a_hand_edited_callout_without_a_duration_is_reported(project):
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    plan = load_plan(e)
    next(i for i in plan["inserts"] if i["kind"] == "callout").pop("dur")
    write_json(e / "visual_plan.json", plan)
    r = validate(project)
    assert r.returncode == 1 and "no start or duration" in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr


def export(project, e, *extra):
    rem = project / "reels"
    (rem / "src").mkdir(parents=True, exist_ok=True)
    write_json(rem / "package.json", {"name": "reels"})
    run_script("brand.py", "export", "acme", "--remotion", rem, cwd=project)
    (e / "final.mp4").write_bytes(b"a rough cut")  # export only copies it
    r = run_script("visual_plan.py", "export", "edit/4821", "--remotion", rem, "--props", rem / "props.json", *extra,
                   cwd=project, check=False)
    return r, (json.loads((rem / "props.json").read_text(encoding="utf-8")) if (rem / "props.json").exists() else None)


def test_export_hands_ready_callouts_to_the_kit_and_their_labels_to_the_audit(project):
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    r, props = export(project, e)
    assert r.returncode == 0, r.stdout + r.stderr
    c = props["callouts"][0]
    assert c["id"] == "l01" and c["variant"] == "tag" and c["anchor"] == [300, 1150] and c["side"] == "right"
    assert c["lines"] == ["LAPTOP", "WORK MACHINE"] and c["w"] > 0 and c["start"] == pytest.approx(4.6)
    assert props["inserts"] == []  # not a file insert
    keep = [k for k in load_plan(e)["keep_clear"] if k.get("callout") == "l01"]
    assert keep and keep[0]["start"] == pytest.approx(4.6) and keep[-1]["end"] == pytest.approx(7.0)
    # the label's box where the render puts it: the anchor through the template's drift, the label at its offset
    v = vp()
    ax, ay = v.anchor_on_screen(300, 1150, 4.6, [], captions()["segments"], True, 30.0)
    px, py, pw, ph = v.callout_geometry(ax, ay, "right", False, c["w"], True)["plate"]
    x, y, w, h = keep[0]["box"]
    assert x <= px + 1 and y <= py + 1 and x + w >= px + pw - 1 and y + h >= py + ph - 1
    # a second export does not stack the entries
    export(project, e)
    assert len([k for k in load_plan(e)["keep_clear"] if k.get("callout") == "l01"]) == len(keep)


@needs_ffmpeg
def test_validate_keeps_the_measurement_of_the_picture(project):
    # Fable review: a callout added before the rough cut was measured again by ffmpeg on every validate
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    rough_cut(e, moving=False)
    assert validate(project).returncode == 0
    c = next(i for i in load_plan(e)["inserts"] if i["kind"] == "callout")
    assert c["status"] == "ready" and c["motion"]["v"] <= vp().CALLOUT_STILL


def test_a_callout_is_one_line_of_the_plan_and_one_frame_of_the_board(project):
    # Fable review: its label's zones (one per 0.25 s) came out as ~10 "card" frames of the storyboard and ~10 lines
    # of the plan's graphics zones; the storyboard had no frame of the callout itself
    import board
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    r, props = export(project, e)
    plan = load_plan(e)
    assert len([k for k in plan["keep_clear"] if k.get("callout")]) > 1  # the audit still gets every 0.25 s
    from reels_common import load_config
    pans = board.panels(props, plan, load_config(e)[2], 30)
    assert not [p for p in pans if p["label"].startswith("card")], [p["label"] for p in pans]
    own = [p for p in pans if p["label"].startswith("l01")]
    assert len(own) == 1 and own[0]["frame"] >= round(4.6 * 30) + 18  # once the label is fully on screen
    run_script("visual_plan.py", "md", "edit/4821", cwd=project)
    md = (e / "visual_plan.md").read_text(encoding="utf-8")
    assert md.count("callout l01 label") == 1, md


def test_the_checked_time_is_the_frames_the_kit_draws(project):
    # Codex review: the kit starts a callout on frame round(start * 30); the checks and its zones used the raw second
    e = callout_project(project)
    add(project, "--at", "4.61", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    export(project, e)
    keep = [k for k in load_plan(e)["keep_clear"] if k.get("callout") == "l01"]
    assert keep[0]["start"] == pytest.approx(138 / 30) and keep[-1]["end"] == pytest.approx((138 + 72) / 30)


def test_an_insert_that_will_not_render_does_not_block_a_callout(project):
    # Fable review: a planned B-roll without its file falls back to the main footage, so the dot still has its object
    callout_project(project, {"use_broll": True})
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "broll", "--at", "word:resume#1", "--dur", "1.5",
               "--what", "hands with a resume", "--why", "illustrates the resume", "--source", "project", cwd=project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    r = validate(project)
    assert "on screen with b01" not in r.stdout, r.stdout


def test_a_callout_where_the_subtitles_are_hidden_may_use_their_band(project):
    # Fable review: the subtitle band was checked even where the plan hides the subtitles
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "200,1380", *LAPTOP)
    assert "subtitle band" in validate(project).stdout
    run_script("visual_plan.py", "hide-subs", "edit/4821", "--from", "4.5", "--to", "7.1", "--why", "the callout",
               cwd=project)
    r = validate(project)
    assert "subtitle band" not in r.stdout, r.stdout


def test_a_three_line_hook_is_checked_at_its_height(project):
    # Fable review: the hook was taken as two lines (y 300-560); a long hook breaks into three (14 characters a line)
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    add(project, "--at", "0.3", "--dur", "2.0", "--anchor", "200,720", *LAPTOP)  # label y 595-715, no faces measured
    # 3+ lines of up to 14 characters: the export that would draw it refuses the label under it
    r, _ = export(project, e, "--hook", "Hiring is broken and here is why")
    assert r.returncode != 0 and "covers the hook" in r.stdout + r.stderr, r.stdout + r.stderr


@needs_ffmpeg
def test_a_horizontal_rough_cut_without_the_framed_format_is_refused(project):
    # Fable review: the kit lays a horizontal video as a band across the middle, the anchor was projected as full frame
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    ffmpeg("-f", "lavfi", "-i", "smptebars=size=1920x1080:rate=30:duration=10", "-c:v", "libx264", "-pix_fmt",
           "yuv420p", e / "final.mp4")
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "l01" in r.stdout and "horizontal" in r.stdout, r.stdout


def test_a_new_callout_is_checked_against_the_ad_safe_zone(project):
    # Codex bot review (PR 32): the profile's zone read the callout's keep_clear entries, which only export writes, after
    # the check: on the first export of a paid ad a label above the ad zone (y 269) passed
    callout_project(project, {"profile": "ad"})
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "200,380", *LAPTOP)  # label top ~255
    r = validate(project)
    assert "AD-1" in r.stdout and "callout l01" in r.stdout, r.stdout


def test_a_line_across_the_corner_logo_is_refused(project):
    # Codex bot review (PR 32): the corner logo and the hook were checked against the label only; the line crossing the
    # logo passed, and the callout is drawn over it
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "900,400", "--side", "left", *LAPTOP)
    assert validate(project).returncode == 0
    r = run_script("visual_plan.py", "validate", "edit/4821", "--corner", cwd=project, check=False)
    assert r.returncode == 1 and "corner logo" in r.stdout, r.stdout


def test_frames_are_rounded_as_the_kit_rounds_them(project):
    # Codex bot review (PR 32): Python's round() takes a half to even (0.15 s -> frame 4), the kit's Math.round takes it
    # up (frame 5); the last drawn frame escaped the checks
    e = callout_project(project)
    add(project, "--at", "0.15", "--dur", "2.15", "--anchor", "300,1150", *LAPTOP)
    export(project, e)
    keep = [k for k in load_plan(e)["keep_clear"] if k.get("callout") == "l01"]
    # the zones keep times to the millisecond
    assert keep[0]["start"] == pytest.approx(5 / 30, abs=1e-3) and keep[-1]["end"] == pytest.approx((5 + 65) / 30, abs=1e-3)


def test_a_callout_with_errors_stays_out_of_the_render(project):
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,820", *LAPTOP)  # on the face
    r, props = export(project, e, "--force")
    assert props["callouts"] == [] and "l01" in r.stdout


def test_the_kit_draws_callouts_and_tags_their_text():
    reel = (KIT / "ReelKit.tsx").read_text(encoding="utf-8")
    layer = (KIT / "kit" / "Callout.tsx").read_text(encoding="utf-8")
    assert "<CalloutLayer" in reel and "callouts?: CalloutSpec[] | null" in reel
    assert 'data-rk={`callout:${' in layer  # textcheck groups and checks the label's text
    # the video and the callouts are placed by one camera: ReelKit draws the footage with kit/anchor.ts
    assert 'from "./kit/anchor"' in reel


# ── a moving anchor: keys by hand, track.py, a person ──

PAN = 100  # px a second: the picture pans to the right like a handheld shot


def panning_cut(e, dur=10, pan=PAN, offset=0.0):
    """final.mp4: a still textured picture (blurred noise) the camera pans across, pan px a second to the right: an
    object at x at second 0 is at x + pan * t."""
    import numpy as np
    from PIL import Image, ImageFilter
    w = 1080 + pan * dur + 40
    # blobs of ~8-30 px, like the things in a room (fine noise averages out in the 120 px patch the check compares)
    noise = np.random.default_rng(7).integers(0, 256, (1920 // 8, w // 8), dtype=np.uint8)
    Image.fromarray(noise).resize((w, 1920), Image.BICUBIC).filter(ImageFilter.GaussianBlur(1)).save(e / "pan.png")
    ffmpeg("-loop", "1", "-framerate", "30", "-i", e / "pan.png", "-t", dur, "-vf",
           f"crop=1080:1920:x='{w - 1080}-t*{pan}':y=0,format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
           *(["-output_ts_offset", offset] if offset else []), e / "final.mp4")


LAMP = ["--variant", "tag", "--lines", "LAMP", "--what", "the lamp on the shelf", "--why", "names the lamp she shows"]


def callout(e, n=0):
    return [i for i in load_plan(e)["inserts"] if i["kind"] == "callout"][n]


def has_cv2():
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


needs_cv2 = pytest.mark.skipif(not (has_cv2() and shutil.which("ffmpeg")), reason="OpenCV, numpy and ffmpeg are needed")
def has_numpy_pil():
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


needs_pan = pytest.mark.skipif(not (shutil.which("ffmpeg") and has_numpy_pil()), reason="ffmpeg, numpy and Pillow")


@needs_cv2
def test_a_tracked_dot_follows_a_panning_picture(project):
    # a handheld pan: a still dot is refused (the object leaves it); track.py follows the object and the dot stays on it
    e = callout_project(project)
    panning_cut(e)
    add(project, "--at", "7.0", "--dur", "2.4", "--anchor", "300,1150", "--side", "right", *LAMP)
    r = validate(project)
    assert r.returncode == 1 and "moves under the dot" in r.stdout, r.stdout
    r = run_script("track.py", "edit/4821", "l01", cwd=project)
    c = callout(e)
    assert c["path_by"] == "track" and c["track_key"], r.stdout
    v = vp()
    for t in (0.0, 1.0, 2.3):  # where the object really is: x + PAN * t (the picture's own motion)
        x, y, vis, _ = v.path_at(c["path"], c["anchor"], t)
        assert vis == 1 and x == pytest.approx(300 + PAN * t, abs=6) and y == pytest.approx(1150, abs=6), (t, x, y)
    r = validate(project)
    # a path on its object holds still along it: not even "changes a little" (10-25 of 255)
    assert r.returncode == 0 and "under the dot" not in r.stdout, r.stdout


@needs_cv2
def test_a_track_is_checked_on_the_frames_it_followed(project):
    # a real rough cut's first frame sat at 0.021 s: resampled to 5 a second, the check took frames 2, 8, 14... while
    # the track followed 0, 6, 12... (2 frames: 27 px on a fast pan) and read a good track as a slipping one. Here
    # every frame has its own brightness (2 x its number), so the frames compared are known exactly
    import track
    e = callout_project(project)
    ffmpeg("-f", "lavfi", "-i", "nullsrc=s=1080x1920:r=30:d=10,geq=lum='2*N':cb=128:cr=128", "-c:v", "libx264",
           "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv420p", "-output_ts_offset", "0.021", e / "final.mp4")
    c = {"id": "l01", "start": 1.0, "dur": 1.6}  # frames 30-78: luma 60-156
    followed = track.frames_of(e / "final.mp4", 1.0, 1.6, level=False)
    checked, why = vp().path_frames(e / "final.mp4", c)
    assert why is None and len(checked) >= 8
    # both start on the rough cut's first frame at or after the callout's start: frame 30 (at 1.021 s), luma 60, which
    # is (60 - 16) * 255 / 219 = 51.2 on the full-range gray scale ffmpeg converts to
    assert float(followed[0].mean()) == pytest.approx((60 - 16) * 255 / 219, abs=0.6)
    for k, buf in enumerate(checked):
        assert sum(buf) / len(buf) == pytest.approx(float(followed[6 * k].mean()), abs=0.6), k


@needs_cv2
def test_a_track_breaks_at_a_joint_of_the_rough_cut(project):
    # the rough cut jumps at 6.5 s (a joint of two spans): the object is elsewhere after it, the dot must not slide on
    e = callout_project(project)
    panning_cut(e)
    add(project, "--at", "5.0", "--dur", "2.4", "--anchor", "300,1150", "--side", "right", *LAMP)  # 5.0-7.4 s
    r = run_script("track.py", "edit/4821", "l01", cwd=project)
    assert "joint" in r.stdout, r.stdout
    c = callout(e)
    v = vp()
    assert v.path_at(c["path"], c["anchor"], 1.2)[2] == 1  # 6.2 s: on the object, before the joint
    # gone by the joint's frame: held on, it stood over the next shot (a real tour: a tower over a cut to the street)
    assert v.path_at(c["path"], c["anchor"], 1.5)[2] == 0


@needs_cv2
def test_a_track_of_an_older_rough_cut_is_refused(project):
    e = callout_project(project)
    panning_cut(e)
    add(project, "--at", "7.0", "--dur", "2.4", "--anchor", "300,1150", "--side", "right", *LAMP)
    run_script("track.py", "edit/4821", "l01", cwd=project)
    assert validate(project).returncode == 0
    panning_cut(e, dur=12)  # the rough cut is cut again
    r = validate(project)
    assert r.returncode == 1 and "track.py" in r.stdout, r.stdout


@needs_cv2
def test_a_still_object_keeps_a_still_anchor(project):
    e = callout_project(project)
    panning_cut(e)
    r = run_script("track.py", "edit/4821", "l01", cwd=project, check=False)
    assert r.returncode == 1 and "no such callout" in r.stderr
    panning_cut(e, pan=0)  # the same textured picture, held still
    add(project, "--at", "7.0", "--dur", "2.4", "--anchor", "300,1150", "--side", "right", *LAMP)
    r = run_script("track.py", "edit/4821", "l01", cwd=project, check=False)
    assert "path" not in callout(e) and "holds still" in r.stdout, r.stdout + r.stderr


@needs_cv2
def test_a_flat_surface_has_nothing_to_follow(project):
    e = callout_project(project)
    ffmpeg("-f", "lavfi", "-i", "color=c=gray:size=1080x1920:rate=30:duration=10", "-c:v", "libx264", "-pix_fmt",
           "yuv420p", e / "final.mp4")
    add(project, "--at", "7.0", "--dur", "2.4", "--anchor", "300,1150", "--side", "right", *LAMP)
    r = run_script("track.py", "edit/4821", "l01", cwd=project, check=False)
    assert r.returncode == 1 and "nothing to follow" in r.stderr and "path" not in callout(e), r.stdout + r.stderr


def test_the_patch_follows_the_dot_between_pixels():
    # a path moves by fractions of a pixel of the measuring frame (360 px wide, 3 px of the 1080 frame each): a patch
    # snapped to whole pixels was up to 1.5 px off and read a path on its object as a slipping one
    v = vp()
    ramp = bytes(x % 256 for _ in range(640) for x in range(360))  # brightness = the pixel's column
    a = v._patch(ramp, 300.0, 960)
    b = v._patch(ramp, 301.5, 960)  # half a pixel of the measuring frame to the right
    assert sum(b) / len(b) - sum(a) / len(a) == pytest.approx(0.5)

@needs_pan
def test_keys_by_hand_follow_a_slow_pan(project):
    # the same pan, followed by two keys at the object's place: the picture holds still along the path
    e = callout_project(project)
    panning_cut(e, dur=20)
    add(project, "--at", "7.0", "--dur", "2.4", "--keys", "0:300,1150", f"2.4:{300 + PAN * 2.4:.0f},1150",
        "--side", "right", *LAMP)
    c = callout(e)
    assert c["anchor"] == [300, 1150] and c["path_by"] == "keys" and len(c["path"]) == 2
    r = validate(project)
    assert r.returncode == 0 and "under the dot" not in r.stdout, r.stdout
    # keys that miss the object: the patch along them changes, the callout is refused
    add(project, "--at", "17.0", "--dur", "2.4", "--keys", "0:300,1150", "2.4:300,1151", "--side", "right", *LAMP)
    r = validate(project)
    assert r.returncode == 1 and "l02" in r.stdout and "slips off" in r.stdout, r.stdout


def test_a_hidden_key_hides_the_dot_and_validate_counts_it(project):
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--keys", "0:300,1150", "0.5:-", "--side", "right", *LAPTOP)
    v = vp()
    c = callout(e)
    assert v.path_at(c["path"], c["anchor"], 0.25)[2] == pytest.approx(0.5)  # fading toward the hidden key
    r = validate(project)
    assert "hidden" in r.stdout and "%" in r.stdout, r.stdout  # seen ~20 % of the time
    r = add(project, "--at", "word:speed#1", "--dur", "2.4", "--keys", "0:300,1150", "1:x", *LAPTOP, check=False)
    assert r.returncode != 0 and "--keys" in r.stderr


def test_the_label_moves_with_its_dot_in_the_zones(project):
    # keys carry the label across the frame: the audit's zones follow it, not the first position
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--keys", "0:150,1150", "2.4:400,1150", "--side", "right",
        *LAPTOP)
    _, props = export(project, e)
    assert props["callouts"][0]["path"] == [[0, 150, 1150, 1], [2.4, 400, 1150, 1]]
    keep = [k for k in load_plan(e)["keep_clear"] if k.get("callout") == "l01"]
    assert keep[-1]["box"][0] > keep[0]["box"][0] + 200


def test_a_label_carried_into_the_face_by_its_keys_is_refused(project):
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--keys", "0:100,1150", "2.4:300,820", "--side", "right",
        *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "face" in r.stdout, r.stdout


# ── variants ──

def test_a_badge_holds_a_number_in_a_circle(project):
    e = callout_project(project)
    # the circle stands taller than a tag's plate: the dot lower and further left, the badge clear of the face
    r = add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "150,1200", "--variant", "badge",
            "--lines", "$49", "PER MONTH", "--source", "speech", "--source-ref", "the price he says",
            "--what", "the price", "--why", "the price is the point")
    assert "across" in r.stdout, r.stdout
    c = callout(e)
    assert vp().CALLOUT["badge_min"] <= c["w"] <= vp().CALLOUT["badge_max"]
    g = vp().callout_geometry(150, 1200, c["side"], False, c["w"], True, "badge")
    assert g["plate"][2] == g["plate"][3] == c["w"]  # a circle's box
    r = validate(project)
    assert r.returncode == 0, r.stdout


def test_a_badge_is_not_a_phrase(project):
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", "--variant", "badge",
        "--lines", "BEST PRICE", "ON THE MARKET TODAY", "--what", "a claim", "--why", "a claim he makes")
    r = validate(project)
    assert r.returncode == 1 and "badge" in r.stdout and "across" in r.stdout, r.stdout


def test_a_ring_needs_its_size_and_grows_with_the_camera(project):
    e = callout_project(project)
    r = add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", "--variant", "ring", *LAPTOP[2:],
            check=False)
    assert r.returncode != 0 and "--radius" in r.stderr
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1200", "--variant", "ring", "--radius", "60",
        *LAPTOP[2:])
    r = validate(project)
    assert r.returncode == 0, r.stdout
    v = vp()
    write_json(e / "camera.json", {"shots": [{"at": 0, "z": 1.2, "cx": 540, "cy": 960}]})
    g = v.callout_at(callout(e), 5.0, v.callout_context(e, load_plan(e)))
    assert g["r"] == pytest.approx(72)  # 60 x 1.2
    o = g["segs"][0][0]  # the line leaves the ring's edge, not its center
    assert math.hypot(o[0] - g["dot"][0], o[1] - g["dot"][1]) == pytest.approx(72)


def test_a_ring_over_a_face_is_named(project):
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "250,700", "--variant", "ring", "--radius", "150",
        "--side", "left", "--below", *LAPTOP[2:])
    r = validate(project)
    assert "on a face" in r.stdout, r.stdout


def test_a_dimension_measures_between_two_points(project):
    e = callout_project(project)
    r = add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "150,1150", "--variant", "dimension",
            "--lines", "120 CM", "--source", "speech", "--what", "the desk's width", "--why", "the size matters",
            check=False)
    assert r.returncode != 0 and "--to" in r.stderr
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "150,1150", "--to", "650,1150",
        "--variant", "dimension", "--lines", "120 CM", "--source", "speech", "--what", "the desk's width",
        "--why", "the size matters")
    c = callout(e)
    g = vp().callout_geometry(150, 1150, c["side"], False, c["w"], False, "dimension", 0, [650, 1150])
    x, y, w, h = g["plate"]
    assert x + w / 2 == pytest.approx(400) and y + h < 1150  # centered over the line's middle
    r = validate(project)
    assert r.returncode == 0, r.stdout
    _, props = export(project, e)
    assert props["callouts"][0]["to"] == [650, 1150]


def test_a_dimension_too_short_or_off_the_frame_is_refused(project):
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", "--to", "340,1150",
        "--variant", "dimension", "--lines", "5 CM", "--source", "speech", "--what", "a gap", "--why", "the gap matters")
    add(project, "--at", "word:speed#1", "--dur", "2.4", "--anchor", "300,1150", "--to", "1200,1150",
        "--variant", "dimension", "--lines", "3 M", "--source", "speech", "--what", "a wall", "--why", "the wall matters")
    r = validate(project)
    assert r.returncode == 1 and "80 px" in r.stdout and "l02" in r.stdout and "frame" in r.stdout, r.stdout


@needs_ffmpeg
def test_text_with_no_plate_must_read_over_the_picture(project):
    # the line variant draws its text in the brand's light color straight on the picture: refused over a white wall,
    # passes over a dark one
    e = callout_project(project)
    ffmpeg("-f", "lavfi", "-i", "color=c=white:size=1080x1920:rate=30:duration=10", "-c:v", "libx264", "-pix_fmt",
           "yuv420p", e / "final.mp4")
    # the title stands on the line (35 px higher than a tag's plate): the dot lower, clear of the face
    r = add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1200", "--variant", "line", *LAPTOP[2:])
    assert "contrast" in r.stdout, r.stdout
    r = validate(project)
    assert r.returncode == 1 and "reads poorly" in r.stdout, r.stdout
    ffmpeg("-f", "lavfi", "-i", "color=c=0x202020:size=1080x1920:rate=30:duration=10", "-c:v", "libx264", "-pix_fmt",
           "yuv420p", e / "final.mp4")
    r = validate(project)
    assert r.returncode == 0 and "reads poorly" not in r.stdout, r.stdout


def test_line_puts_the_title_over_the_line_and_the_detail_under_it():
    v = vp()
    g = v.callout_geometry(300, 1150, "right", False, 248, True, "line")
    x, y, w, h = g["plate"]
    ly = g["end"][1]
    assert y + v.CALLOUT["title_h"] == pytest.approx(ly) and y + h > ly  # the title above, the detail under
    assert g["end"][0] == pytest.approx(x + w)  # the line runs on under the whole label


# ── a person ──

def test_a_callout_follows_a_persons_shoulder(project):
    # the speaker sits left of center: the dot goes to the shoulder on the open side, the label clear of the face
    e = callout_project(project)
    faces_json(e, [200, 500, 240, 300])
    r = add(project, "--at", "word:resume#1", "--dur", "2.4", "--person", "left", "--lines", "ANNA", "HOST",
            "--what", "the host", "--why", "names the host as she starts")
    c = callout(e)
    assert c["side"] == "right" and c["person"] == "left" and "shoulder" in r.stdout
    assert c["anchor"] == [round(200 + 120 + 0.85 * 240), round(500 + 1.25 * 300)]
    r = validate(project)
    assert r.returncode == 0, r.stdout
    _, props = export(project, e)
    assert props["callouts"][0]["path"] and props["callouts"][0]["path"][0][1:3] == pytest.approx(c["anchor"], abs=1)


def test_a_callout_follows_the_person_it_names_when_they_move(project):
    # the person walks right across the frame: the dot goes with the face (faces.json), not where it started
    e = callout_project(project)
    from faces import FILTER_V
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": FILTER_V}, "samples": [
        {"t": k * 0.25, "faces": [[100 + 20 * k, 500, 240, 300, 0.95]]} for k in range(121)]})
    add(project, "--at", "4.0", "--dur", "2.4", "--person", "center", "--side", "right", "--lines", "ANNA",
        "--what", "the host", "--why", "names the host as she walks")
    v = vp()
    c = callout(e)
    path = v.callout_path(c, v.callout_context(e, load_plan(e)))
    x0, x1 = v.path_at(path, c["anchor"], 0)[0], v.path_at(path, c["anchor"], 2.0)[0]
    assert x1 - x0 == pytest.approx(20 * 8, abs=3)  # 8 samples later, 20 px each


def test_a_person_callout_without_a_face_is_refused(project):
    e = callout_project(project)
    (e / "faces.json").unlink()
    r = add(project, "--at", "word:resume#1", "--dur", "2.4", "--person", "left", "--lines", "ANNA", "--what", "the host",
            "--why", "names the host", check=False)
    assert r.returncode != 0 and "faces.json" in r.stderr


def test_the_kit_moves_and_varies_callouts():
    layer = (KIT / "kit" / "Callout.tsx").read_text(encoding="utf-8")
    for s in ("pathAt(", "zoomAt(", 'variant === "badge"', 'variant === "line"', 'variant === "ring"', 'variant === "dimension"'):
        assert s in layer, s


# ── PR review (Codex CLI) ──

def object_cut(e, move="", zoom=""):
    """final.mp4: a still textured wall with a textured box (200 px) on it, 10 s; move: the box's x over time (an
    ffmpeg expression of t), zoom: its size factor over time. The box is at (200..400, 1050..1250) at t = 7 s."""
    import numpy as np
    from PIL import Image, ImageFilter
    rng = np.random.default_rng(11)
    wall = rng.integers(0, 256, (1920 // 8, 1080 // 8), dtype=np.uint8)
    Image.fromarray(wall).resize((1080, 1920), Image.BICUBIC).filter(ImageFilter.GaussianBlur(1)).save(e / "wall.png")
    box = rng.integers(0, 256, (200 // 8, 200 // 8), dtype=np.uint8)
    Image.fromarray(box).resize((200, 200), Image.BICUBIC).save(e / "box.png")
    size = f"scale=w='200*({zoom})':h='200*({zoom})':eval=frame" if zoom else "null"
    x = move or "200"
    ffmpeg("-loop", "1", "-framerate", "30", "-t", "10", "-i", e / "wall.png", "-loop", "1", "-framerate", "30", "-t", "10",
           "-i", e / "box.png", "-filter_complex",
           f"[1]{size}[b];[0][b]overlay=x='{x}+100-overlay_w/2':y='1150-overlay_h/2':eval=frame,format=yuv420p",
           "-t", "10", "-c:v", "libx264", "-preset", "ultrafast", e / "final.mp4")


@needs_cv2
def test_the_track_follows_the_object_not_the_wall_behind_it(project):
    # Codex review: the ROI (120 px) took in the wall around a 200 px box; the motion of most corners won and the dot
    # stayed on the wall while the box moved 120 px
    e = callout_project(project)
    object_cut(e, move="200+50*(t-7)")
    add(project, "--at", "7.0", "--dur", "2.4", "--anchor", "300,1150", "--side", "right", *LAMP)
    run_script("track.py", "edit/4821", "l01", cwd=project)
    c = callout(e)
    x, y, vis, _ = vp().path_at(c.get("path"), c["anchor"], 2.3)
    assert x == pytest.approx(300 + 50 * 2.3, abs=8) and vis == 1, (x, y)


@needs_cv2
def test_a_track_of_a_growing_object_keeps_its_scale(project):
    # Codex review: a box growing in place (scale 1 -> 1.3, no shift) lost its path ("within 40 px": a still anchor), so
    # a ring around it did not grow; and the check compared fixed-size patches, reading the zoom as a slip
    e = callout_project(project)
    object_cut(e, zoom="1+0.125*max(0,t-7)")
    add(project, "--at", "7.0", "--dur", "2.4", "--anchor", "300,1150", "--variant", "ring", "--radius", "90",
        "--side", "right", *LAMP[2:])
    run_script("track.py", "edit/4821", "l01", cwd=project)
    c = callout(e)
    assert c.get("path_by") == "track", c
    assert vp().path_at(c["path"], c["anchor"], 2.3)[3] == pytest.approx(1 + 0.125 * 2.3, abs=0.05)
    r = validate(project)
    assert "slips off" not in r.stdout and "under the dot" not in r.stdout, r.stdout


def test_a_path_is_checked_between_the_samples_too(project):
    # Codex review: a key between two 0.25 s samples carried the label onto the face and back, unseen
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--keys", "0:300,1150", "0.45:300,1150", "0.5:400,800",
        "0.55:300,1150", "2.4:300,1150", "--side", "right", *LAPTOP)
    r = validate(project)
    assert r.returncode == 1 and "face" in r.stdout, r.stdout


def test_a_ring_is_checked_whole_against_the_frame_and_the_subtitles(project):
    # Codex review: only the ring's center was checked against the frame and the UI, and not the ring at all against
    # the subtitle band
    callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "200,1150", "--variant", "ring", "--radius", "220",
        "--side", "right", "--below", *LAPTOP[2:])
    add(project, "--at", "word:speed#1", "--dur", "2.4", "--anchor", "100,700", "--variant", "ring", "--radius", "150",
        "--side", "right", "--below", *LAPTOP[2:])
    r = validate(project)
    assert "l01" in r.stdout and "subtitle" in r.stdout, r.stdout
    assert "l02" in r.stdout and "leaves the frame" in r.stdout, r.stdout


@needs_ffmpeg
def test_text_with_no_plate_on_a_person_is_checked_too(project):
    # Codex review: the contrast check of the line variant sat inside the picture-motion branch a person skips
    e = callout_project(project)
    faces_json(e, [200, 500, 240, 300])
    ffmpeg("-f", "lavfi", "-i", "color=c=white:size=1080x1920:rate=30:duration=10", "-c:v", "libx264", "-pix_fmt",
           "yuv420p", e / "final.mp4")
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--person", "left", "--variant", "line", "--lines", "ANNA",
        "--what", "the host", "--why", "names the host as she starts")
    r = validate(project)
    assert r.returncode == 1 and "reads poorly" in r.stdout, r.stdout


def test_hand_edited_paths_and_points_are_reported_not_crashed(project):
    # Codex review: NaN in a path passed path_issue and crashed the geometry; a stray "to": [500] on a tag crashed
    # callout_at
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--keys", "0:300,1150", "2.4:400,1150", *LAPTOP)
    add(project, "--at", "word:speed#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    plan = load_plan(e)
    a, b = [i for i in plan["inserts"] if i["kind"] == "callout"]
    a["path"][1][1] = float("nan")
    b["to"] = [500]
    write_json(e / "visual_plan.json", plan)
    r = validate(project)
    assert "Traceback" not in r.stderr, r.stderr
    assert "l01" in r.stdout and "path" in r.stdout and "l02" in r.stdout, r.stdout


# ── PR review (Antigravity) ──

def test_a_broken_callout_in_an_ad_is_reported_not_crashed(project):
    # Antigravity review: the ad profile's safe-zone check read every callout's start and duration directly: a callout
    # with no duration crashed validate (KeyError) instead of being reported
    e = callout_project(project, {"profile": "ad"})
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    plan = load_plan(e)
    next(i for i in plan["inserts"] if i["kind"] == "callout").pop("dur")
    write_json(e / "visual_plan.json", plan)
    r = validate(project)
    assert "Traceback" not in r.stderr and "no start or duration" in r.stdout, r.stdout + r.stderr


def test_an_export_with_a_callout_broken_after_validate_does_not_crash(project):
    # Antigravity review: export read the callout's variant, side and anchor directly
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    assert validate(project).returncode == 0
    plan = load_plan(e)
    next(i for i in plan["inserts"] if i["kind"] == "callout").pop("side")
    write_json(e / "visual_plan.json", plan)
    r, props = export(project, e, "--force")
    assert "Traceback" not in r.stderr and props["callouts"] == [], r.stdout + r.stderr


def test_a_person_callout_without_its_faces_stays_out_of_the_render(project):
    # Antigravity review: with faces.json gone after validate, export wrote "path": null and the kit drew a still dot
    # where the person had been at the start
    e = callout_project(project)
    faces_json(e, [200, 500, 240, 300])
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--person", "left", "--lines", "ANNA", "--what", "the host",
        "--why", "names the host as she starts")
    assert validate(project).returncode == 0
    (e / "faces.json").unlink()
    r, props = export(project, e, "--force")
    assert props["callouts"] == [] and "Traceback" not in r.stderr, r.stdout + r.stderr


@needs_pan
def test_the_phones_exposure_is_not_a_slip(project):
    # Antigravity review: a phone brightens the picture as it pans; the patch along a path that follows its object
    # exactly was compared in raw levels and read the exposure as a slip
    e = callout_project(project)
    panning_cut(e)
    bright = e / "bright.mp4"
    ffmpeg("-i", e / "final.mp4", "-vf", "eq=brightness='0.12*min(1,max(0,t-7)/2.4)':eval=frame,format=yuv420p",
           "-c:v", "libx264", "-preset", "ultrafast", bright)
    bright.replace(e / "final.mp4")
    add(project, "--at", "7.0", "--dur", "2.4", "--keys", "0:300,1150", f"2.4:{300 + PAN * 2.4:.0f},1150",
        "--side", "right", *LAMP)
    r = validate(project)
    assert r.returncode == 0 and "under the dot" not in r.stdout, r.stdout


def test_a_vertical_dimension_keeps_its_label_off_its_line():
    # Antigravity review: the label was always above or under the middle, so on an upright measure it sat on the line
    v = vp()
    for side in ("left", "right"):
        g = v.callout_geometry(500, 600, side, False, 184, False, "dimension", 0, [500, 1300])
        assert not any(v._seg_hits(p, q, g["plate"]) for p, q in g["segs"]), (side, g["plate"])


def test_one_frame_cannot_change_a_tracked_size_wildly():
    # Antigravity review: the scale was multiplied frame by frame with no limit; one bad estimate (noise, a hand over
    # the object) could blow a ring up or shrink it to nothing
    import numpy as np
    import track
    assert track.scale_step(np.array([[1.02, 0, 0], [0, 1.02, 0]])) == pytest.approx(1.02)
    assert track.scale_step(np.array([[1.6, 0, 0], [0, 1.6, 0]])) is None
    assert track.scale_step(np.array([[0.5, 0, 0], [0, 0.5, 0]])) is None


def test_a_track_remembers_the_joints_it_broke_at(project):
    # Antigravity review: the fingerprint held final.mp4 only; spans re-cut with the same file left an old track valid
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    (e / "final.mp4").write_bytes(b"a rough cut")
    c = callout(e)
    k0 = vp().track_key(e, c)
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    cap["segments"][2]["out_start"] += 0.3
    write_json(e / "captions.json", cap)
    assert vp().track_key(e, c) != k0
