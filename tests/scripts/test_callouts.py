"""Callouts (a dot on an object, a leader line, a label plate): visual_plan.py `--kind callout` and the kit's
CalloutLayer. The requirement behind every test: the label must point at the object where the viewer sees it, so its
anchor is projected through the same camera and drift the kit draws the video with, and the plan check refuses a
callout that would land on a face, the subtitles or the app's UI, leave the frame, or sit on a picture that is not there.
"""
import json
import shutil
import subprocess

import pytest

from conftest import CORE, ffmpeg, needs_ffmpeg, run_script, write_json
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


GEO = [{"x": x, "y": y, "side": side, "below": below, "w": w, "sub": sub}
       for x, y in ((300, 1150), (900, 700)) for side in ("left", "right") for below in (False, True)
       for w, sub in ((248, True), (400, False))]


@needs_node
def test_python_and_the_kit_lay_out_a_callout_the_same(tmp_path):
    v = vp()
    kit = run_kit("calloutGeometry(c.x, c.y, c.side, c.below, c.w, c.sub)", GEO, tmp_path)
    for c, k in zip(GEO, kit):
        py = v.callout_geometry(c["x"], c["y"], c["side"], c["below"], c["w"], c["sub"])
        assert k == {key: pytest.approx(val) for key, val in py.items()}, c


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
