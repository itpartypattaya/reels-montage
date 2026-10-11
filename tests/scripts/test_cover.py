"""Covering a bad picture (defects.py -> faces_defects.json) in the visual plan: hints, --covers, accept, validate, md."""
import json

from conftest import run_script, write_json
from test_plan import load_plan, plan_project

DEFECT = {"id": "d01", "kind": "turned", "start": 12.4, "end": 12.9, "detail": "turn +0.52 eye distances off the median",
          "words": "Two out of three"}


def setup(project, reel=None):
    e = plan_project(project, {"use_broll": True, "use_scenes": True, **(reel or {})})
    write_json(e / "faces_defects.json", {"step": 0.1, "on_camera": True, "defects": [DEFECT]})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    return e


def validate(project):
    return run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)


def lines(r, kind):
    return [l for l in r.stdout.splitlines() if l.startswith(kind) and "d01" in l]


def broll(project, *extra, at="12.0", dur="1.3", ready=True):
    r = run_script("visual_plan.py", "add", "edit/4821", "--kind", "broll", "--at", at, "--dur", dur,
                   "--what", "an office", "--why", "covers a glance away", *extra, cwd=project, check=False)
    if ready:  # as footage.py pick leaves it: export takes only ready inserts
        e = project / "edit" / "4821"
        plan = load_plan(e)
        plan["inserts"][-1].update(status="ready", file="inserts/b.mp4")
        write_json(e / "visual_plan.json", plan)
    return r


def test_an_open_defect_is_a_hint_and_a_warning_and_accept_takes_it(project):
    e = setup(project)
    hints = " ".join(h for g in load_plan(e)["segments"] for h in g["hints"])
    assert "picture d01: turned" in hints
    r = validate(project)
    assert lines(r, "warning:") and "accept" in lines(r, "warning:")[0]
    bad = run_script("visual_plan.py", "accept", "edit/4821", "d01", cwd=project, check=False)
    assert bad.returncode != 0 and "--why" in bad.stderr
    run_script("visual_plan.py", "accept", "edit/4821", "d01", "--why", "a natural glance at the notes", cwd=project)
    assert not lines(validate(project), "warning:")
    run_script("visual_plan.py", "md", "edit/4821", cwd=project)
    md = (e / "visual_plan.md").read_text(encoding="utf-8")
    assert "## Picture defects" in md and "d01 turned" in md and "accepted: a natural glance" in md
    run_script("visual_plan.py", "init", "edit/4821", "--force", cwd=project)  # a rebuilt plan keeps the acceptance
    assert load_plan(e)["accepted_defects"]["d01"]["why"] == "a natural glance at the notes"


def test_a_replacing_b_roll_entering_by_a_cut_covers_it(project):
    e = setup(project)
    broll(project, "--covers", "d01")
    assert load_plan(e)["inserts"][0]["covers"] == ["d01"]
    r = validate(project)
    assert not lines(r, "warning:") and not lines(r, "error:")
    run_script("visual_plan.py", "md", "edit/4821", cwd=project)
    assert "covered by b01" in (e / "visual_plan.md").read_text(encoding="utf-8")


def test_an_insert_that_hides_the_face_covers_it_even_unmarked(project):
    setup(project)
    broll(project)
    assert not lines(validate(project), "warning:")


def test_covers_that_do_not_cover(project):
    e = setup(project)
    broll(project, "--covers", "d01", at="12.3", dur="1.0")  # starts 0.1 s before the defect: no margin
    r = validate(project)
    assert r.returncode == 1 and "must hide the face 0.25 s before and after" in lines(r, "error:")[0]
    run_script("visual_plan.py", "remove", "edit/4821", "b01", cwd=project)
    broll(project, "--covers", "d01", "--transition", "fade", at="12.1", dur="1.2")  # its fade runs over the defect
    r = validate(project)
    assert "enter by a cut" in lines(r, "error:")[0]
    run_script("visual_plan.py", "remove", "edit/4821", "b01", cwd=project)
    broll(project, "--covers", "d01", "--mode", "window")  # a window leaves the face on screen
    assert "leaves the face on screen" in lines(validate(project), "error:")[0]
    run_script("visual_plan.py", "remove", "edit/4821", "b01", cwd=project)
    broll(project, "--covers", "d07")
    assert any("covers d07, which faces_defects.json does not have" in l for l in validate(project).stdout.splitlines())
    assert json.loads((e / "faces_defects.json").read_text(encoding="utf-8"))["defects"][0]["id"] == "d01"


def test_a_planned_insert_does_not_cover_yet_and_an_exit_slide_shows_the_defect(project):
    # review: a planned B-roll counted as covering, though export takes only ready ones; a slide out starting during
    # the defect passed because the full length counted
    e = setup(project)
    broll(project, "--covers", "d01", ready=False)
    w = lines(validate(project), "warning:")
    assert w and "will cover it once it is ready" in w[0]
    run_script("visual_plan.py", "remove", "edit/4821", "b01", cwd=project)
    broll(project, "--covers", "d01", "--transition-out", "slide", at="12.0", dur="1.16")
    err = lines(validate(project), "error:")
    assert err and "exit starts before that" in err[0]


def test_an_acceptance_holds_for_its_stretch_only(project):
    # review: defects.py numbers the defects again after a re-cut; the old d01's acceptance hid another stretch
    e = setup(project)
    run_script("visual_plan.py", "accept", "edit/4821", "d01", "--why", "a glance", cwd=project)
    assert not lines(validate(project), "warning:")
    moved = dict(DEFECT, kind="blur", start=20.0, end=20.6)
    write_json(e / "faces_defects.json", {"step": 0.1, "on_camera": True, "defects": [moved]})
    w = lines(validate(project), "warning:")
    assert any("accept it again" in l for l in w) and any("d01: blur" in l for l in w)


def test_the_margin_stops_at_the_ends_of_the_video(project):
    # PR review: a defect in the first 0.25 s could never be covered: the margin ran before frame 0
    e = setup(project)
    write_json(e / "faces_defects.json", {"step": 0.1, "on_camera": True,
                                          "defects": [dict(DEFECT, start=0.1, end=0.6)]})
    broll(project, "--covers", "d01", at="0.0", dur="1.0")
    r = validate(project)
    assert not lines(r, "error:") and not lines(r, "warning:")
