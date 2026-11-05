"""The app's UI zone (where Reels, Shorts and TikTok draw their buttons and caption) is one setting: the project's
reel-defaults.json -> meme_layout.safe. A project that raises it (TikTok's bottom UI is taller) gets it in every check
and layout, not only in the memes' (review 2026-10-30: memes followed it, while textcheck, B-roll windows, callouts,
faces and matte kept 220 / 420 / 120 px)."""
import json

import pytest

from conftest import run_script, write_json
from test_callouts import LAPTOP, add, callout_project, validate
from test_plan import load_plan

TIKTOK = {"meme_layout": {"safe": {"top": 320, "bottom": 520, "right": 120, "left": 40}}}  # UI from y 1400


def box(key, x, y, w, h):
    return (key, "text", x, y, w, h, 1.0, 1.0)


def test_textcheck_warns_about_text_in_the_projects_ui_zone(project):
    import textcheck as tc
    low = [box("x/1", 60, 1420, 400, 60)]  # y 1420-1480: above the default 1500, inside a 520 px bottom UI
    assert ("UI zone", "x/1") not in [(i[1], i[2]) for i in tc.frame_issues(low, None)]
    write_json(project / "reel-defaults.json", TIKTOK)
    assert ("UI zone", "x/1") in [(i[1], i[2]) for i in tc.frame_issues(low, None)]


def test_a_broll_window_stays_out_of_the_projects_ui_zone(project):
    import visual_plan as vp
    e = project / "edit" / "t"
    e.mkdir()
    write_json(project / "reel-defaults.json", TIKTOK)
    zone, _ = vp.text_zone(e)
    assert zone[1] == 320 and zone[3] == 1400, zone


def test_a_callout_label_in_the_projects_ui_zone_is_refused(project):
    e = callout_project(project)
    add(project, "--at", "word:resume#1", "--dur", "2.4", "--anchor", "300,1150", *LAPTOP)
    assert validate(project).returncode == 0  # the default zone: the label fits
    c = next(i for i in load_plan(e)["inserts"] if i["kind"] == "callout")
    right_edge = 300 + 90 + 48 + c["w"]  # the dot, the reach and the run of the leader line, then the plate
    write_json(project / "reel-defaults.json",
               {"meme_layout": {"safe": {"top": 220, "bottom": 420, "right": 1080 - right_edge + 30, "left": 40}}})
    r = validate(project)
    assert r.returncode == 1 and "l01" in r.stdout and "safe zone" in r.stdout, r.stdout


def test_the_free_zones_start_under_the_projects_top_ui(project):
    pytest.importorskip("cv2")
    import faces as fc
    write_json(project / "reel-defaults.json", TIKTOK)
    z = fc.zone_report(None, [1250, 1430])
    assert z["ceiling"][0] == 320 + 30, z


def test_text_in_the_projects_left_ui_zone_is_warned_about(project):
    # Codex review: textcheck checked the top, the bottom and the right, never the left side a project can set
    import textcheck as tc
    write_json(project / "reel-defaults.json", {"meme_layout": {"safe": {"left": 200}}})
    assert ("UI zone", "x/1") in [(i[1], i[2]) for i in tc.frame_issues([box("x/1", 60, 600, 100, 60)], None)]


def test_the_free_zones_end_above_the_projects_bottom_ui(project):
    # Codex review: with a bottom UI above the subtitles the chest zone still ran down to the subtitles
    pytest.importorskip("cv2")
    import faces as fc
    write_json(project / "reel-defaults.json", {"meme_layout": {"safe": {"bottom": 900}}})  # UI from y 1020
    z = fc.zone_report([380, 600, 260, 340], [1250, 1430])
    assert z["chest"] is None or z["chest"][1] <= 1020, z


def test_another_project_file_gives_its_own_zone(project, tmp_path):
    # Codex review: the zone was kept by the files' times only, so a second file written in the same instant
    # returned the first one's zone (then an overlay file; since 1.22 there are only the project files)
    import os
    from reels_common import ui_safe
    other = tmp_path / "other"
    (other / "edit").mkdir(parents=True)
    a, b = project / "reel-defaults.json", other / "reel-defaults.json"
    write_json(a, {"meme_layout": {"safe": {"bottom": 520}}})
    write_json(b, {"meme_layout": {"safe": {"bottom": 620}}})
    os.utime(b, ns=(a.stat().st_atime_ns, a.stat().st_mtime_ns))
    assert ui_safe(project)["bottom"] == 520
    assert ui_safe(other)["bottom"] == 620


def test_a_project_without_its_own_zone_keeps_the_platform_one(project):
    from reels_common import ui_safe
    assert ui_safe() == {"top": 220, "bottom": 420, "right": 120, "left": 40}
    write_json(project / "reel-defaults.json", {"meme_layout": {"safe": {"bottom": 520}}})  # one side only
    assert ui_safe() == {"top": 220, "bottom": 520, "right": 120, "left": 40}
