"""The "framed" format end to end (a horizontal source in a window drawn by the kit): reel.json keys, the camera clamped
to the window in every script, export props, the checks that keep text inside the window. Test run T7 found the format
in faces.py only: no reel.json key, export wrote nothing, the scripts clamped the camera to the full frame."""
import json

from conftest import run_script, write_json
from test_plan import load_plan, plan_project

SRC = (1080, 608)  # a horizontal rough cut, as in T7 (1080x608): the cover in the default window is x2.04


def framed_faces(e, box, dur=30.0, w=SRC[0], h=SRC[1]):
    """A face measurement in source geometry (faces.py scan of a horizontal video), the same face all through."""
    from faces import FILTER_V
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": FILTER_V}, "geometry": "source", "w": w, "h": h,
                                  "frame": [25, 340, 1030, 1240],
                                  "samples": [{"t": k * 0.25, "faces": [box + [0.95]]} for k in range(int(dur / 0.25) + 1)]})


def framed_project(project, **reel):
    return plan_project(project, {"format": "framed", "use_scenes": True, **reel})


def test_reelcfg_saves_the_framed_format_and_refuses_a_bad_window(project):
    e = plan_project(project)
    r = run_script("reelcfg.py", "save", "edit/4821", "--set", "format=framed", "label=Candidate interview", cwd=project)
    assert "unknown key" not in r.stderr, r.stderr  # T7: "unknown key format, saving it as is"
    reel = json.loads((e / "reel.json").read_text(encoding="utf-8"))
    assert reel["format"] == "framed" and reel["label"] == "Candidate interview"
    shown = run_script("reelcfg.py", "show", "edit/4821", cwd=project).stdout
    assert "format: framed, window [25, 340, 1030, 1240], label “Candidate interview”" in shown, shown
    bad = run_script("reelcfg.py", "save", "edit/4821", "--set", "window=[0,0,300,300]", cwd=project, check=False)
    assert bad.returncode != 0 and "not saved" in bad.stderr and "at least 540x540" in bad.stderr
    bad = run_script("reelcfg.py", "save", "edit/4821", "--set", "format=wide", cwd=project, check=False)
    assert bad.returncode != 0 and "one of full, framed" in bad.stderr
    assert json.loads((e / "reel.json").read_text(encoding="utf-8"))["format"] == "framed"  # nothing changed


def test_the_camera_is_clamped_to_the_window_as_the_kit_draws_it():
    # T7: camera_at clamped a framed shot to the full frame (cx 820 -> 540): validate looked 280 px off the face
    import reels_common as rc
    import visual_plan as vp
    shots = [{"t": 0.0, "z": 1.0, "cx": 820.0, "cy": 960.0, "drift": 0.0, "whip": False}]
    assert vp.camera_at(shots, 1.0, 5.0)[1] == 540  # the full frame: cx within [540, 540] at z 1
    view = rc.framed_view(rc.FRAMED_WINDOW, SRC)
    z, cx, cy = vp.camera_at(shots, 1.0, 5.0, view=view)
    assert (z, cx) == (1.0, 820.0) and abs(cy - 960) < 1e-6
    # the window never shows past the video: the cover is 2202.6 px wide from x -561.3
    assert abs(vp.camera_at([{**shots[0], "cx": 2000.0}], 1.0, 5.0, view=view)[1] - (-561.3158 + 2202.6316 - 515)) < 0.01
    assert rc.cam_fit(1.2, 0, 0) == (1.2, 450.0, 800.0)  # the full-frame rule unchanged


def test_keep_clear_validate_and_faces_check_agree_on_a_framed_shot(project):
    # T7: keep-clear (through camera.json) said "the face is not touched" while faces.py check --cam 1,820,960 said
    # "covers a face": the plan scripts clamped the framed camera to the full frame
    e = framed_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    framed_faces(e, [700, 150, 80, 110])  # on screen x 866-1029, y 646-870 at the base shot
    write_json(e / "camera.json", {"shots": [{"at": 0.0, "z": 1.0, "cx": 820, "cy": 960}]})  # the face moves to x 586-749
    box = ["--box", "560,600,200,150", "--from", "0.5", "--to", "2"]
    r = run_script("faces.py", "check", "edit/4821", *box, "--cam", "1,820,960", cwd=project, check=False)
    assert r.returncode == 1 and "covers a face" in r.stdout, r.stdout
    r = run_script("visual_plan.py", "keep-clear", "edit/4821", *box, "--what", "probe", cwd=project)
    assert "touches the face" in r.stdout and "camera.json" in r.stdout, r.stdout
    run_script("visual_plan.py", "keep-clear", "edit/4821", "--remove", "1", cwd=project)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "quote", "--mode", "overlay", "--at", "5.0",
               "--dur", "3.0", "--lines", "A card", "on the face", "--source", "agent", "--box", "560,600,300,300",
               "--what", "a card", "--why", "test", cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert r.returncode == 1 and "covers the face" in r.stdout and "camera.json" in r.stdout, r.stdout


def test_audit_side_cuts_use_the_window_edges(project):
    # T7: load() had already turned the source geometry into "screen", so side_cuts skipped its framed branch and
    # clamped the shot to the full frame: a false "face cut at the side" (exit 1) with the face inside the window
    import faces
    e = framed_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    framed_faces(e, [780, 150, 80, 110])  # x 1029-1192 at the base shot: past the window's right edge (1055)
    write_json(e / "camera.json", {"shots": [{"at": 0.0, "z": 1.0, "cx": 820, "cy": 960}]})  # x 749-912: inside
    assert faces.side_cuts(e, load_plan(e)) == []
    # a shot that leaves the face across the window's right edge (x 969-1132) is a real cut by the window
    write_json(e / "camera.json", {"shots": [{"at": 0.0, "z": 1.0, "cx": 820, "cy": 960},
                                             {"at": 10.0, "z": 1.0, "cx": 600, "cy": 960}]})
    cuts = faces.side_cuts(e, load_plan(e))
    assert cuts and min(cuts) == 10.0


def test_validate_checks_the_measurement_and_the_rough_cut_match_the_format(project):
    e = framed_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    from test_plan import faces_json
    faces_json(e, [380, 700, 260, 340])  # a 9:16 cover measurement under a framed video
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert r.returncode == 1 and "measured as a 9:16 cover" in r.stdout, r.stdout
    framed_faces(e, [700, 150, 80, 110])
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert r.returncode == 0 and "9:16 cover" not in r.stdout and "source geometry" not in r.stdout, r.stdout
    reel = json.loads((e / "reel.json").read_text(encoding="utf-8"))
    reel.pop("format")
    write_json(e / "reel.json", reel)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "source geometry" in r.stdout and "format=framed" in r.stdout, r.stdout


def test_framed_scenes_stay_in_the_window_and_the_hook_gets_a_floor(project):
    e = framed_project(project, label="Candidate interview")
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    framed_faces(e, [700, 150, 80, 110])  # face top at y 646 on screen
    add = ["visual_plan.py", "add", "edit/4821", "--kind", "scene", "--source", "agent", "--why", "a test of the zone"]
    run_script(*add, "--type", "quote", "--mode", "split", "--at", "8.0", "--dur", "3.0", "--lines", "A quote",
               "--what", "a split quote", cwd=project)
    # a two-line hook in the window's headroom (y 360-530): ~70 px lines, under the 76 px floor inside the window
    run_script(*add, "--type", "hook", "--variant", "slam", "--mode", "overlay", "--at", "0.2", "--dur", "2.4",
               "--lines", "Which deals", "to ask about?", "--box", "60,360,900,170", "--what", "the hook", cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    out = r.stdout
    assert "the framed format: the kit draws overlay" in out and "not split" in out, out
    assert "c02: the hook lines come out at ~70 px" in out and "start the box on the field above the window" in out, out
    # with the label, the field above the window is the label's: a box there leaves the text area
    run_script("visual_plan.py", "remove", "edit/4821", "c01", "c02", cwd=project)
    run_script(*add, "--type", "hook", "--variant", "slam", "--mode", "overlay", "--at", "0.2", "--dur", "2.4",
               "--lines", "Which deals", "to ask about?", "--box", "60,230,900,320", "--what", "the hook", cwd=project)
    out = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False).stdout
    assert "leaves the framed window's text area x 60-960, y 360-1500" in out, out
    # no label: the field joins the text area, and the same box gets 96 px lines with no warning
    reel = json.loads((e / "reel.json").read_text(encoding="utf-8"))
    reel.pop("label")
    write_json(e / "reel.json", reel)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert r.returncode == 0 and "text area" not in r.stdout and "hook lines" not in r.stdout, r.stdout


def test_export_writes_the_framed_layout_for_the_kit(project):
    import reels_common as rc
    e = framed_project(project, label="Candidate interview", style="v2")
    bj = project / "brands" / "acme" / "brand.json"
    write_json(bj, {**json.loads(bj.read_text(encoding="utf-8")), "looks": {"v2": {"field": "#F4EEE3"}}})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    framed_faces(e, [700, 150, 80, 110])
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    write_json(rem / "package.json", {"name": "reels"})
    run_script("brand.py", "export", "acme", "--remotion", rem, cwd=project)
    (e / "final.mp4").write_bytes(b"a rough cut")  # export only copies it; the size comes from faces.json
    r = run_script("visual_plan.py", "export", "edit/4821", "--remotion", rem, "--props", rem / "props.json",
                   "--subtitles", "plate", cwd=project)
    assert "framed: window [25, 340, 1030, 1240], source 1080x608" in r.stdout, r.stdout
    props = json.loads((rem / "props.json").read_text(encoding="utf-8"))
    # the field around the window is the style's (brand.looks.v2.field), as the kit's own field
    assert props["framed"] == {"window": [25, 340, 1030, 1240], "label": "Candidate interview", "source": [1080, 608],
                               "radius": 50, "field": "#F4EEE3"}
    # the subtitle block the render has stays inside the window's text area, and the audit checks that band
    a = rc.framed_area(rc.framed_of({"format": "framed", "label": "x"}))
    top, bottom = load_plan(e)["subtitles_band"]
    assert props["subtitlesTop"] == top and a[1] <= top and bottom <= a[3]
    # no format: no framed props
    reel = json.loads((e / "reel.json").read_text(encoding="utf-8"))
    reel.pop("format")
    write_json(e / "reel.json", reel)
    run_script("visual_plan.py", "export", "edit/4821", "--remotion", rem, "--props", rem / "props.json", "--force",
               cwd=project)
    assert "framed" not in json.loads((rem / "props.json").read_text(encoding="utf-8"))


def test_scan_and_load_take_the_window_from_reel_json(project):
    # one window for every script: a window moved in reel.json maps the stored source geometry anew (no new scan)
    import faces
    e = framed_project(project, window=[40, 400, 1000, 1100])
    framed_faces(e, [700, 150, 80, 110])
    d = faces.load(e)
    assert d["frame"] == [40, 400, 1000, 1100] and faces.window(d) == [40, 400, 1000, 1100]
    k = max(1000 / 1080, 1100 / 608)
    assert abs(d["map"]["scale"] - round(k, 5)) < 1e-6
