"""board.py (the storyboard sheet) and textcheck.py (text boxes on the frame): panel frames, the sampled render command,
the sheet, the probe log and the text checks. No Node here: Remotion is replaced by a stub."""
import json
import sys

import pytest

from conftest import CORE, needs_pillow, write_json

DOC = json.loads((CORE.parent / "assets" / "reel-defaults.json").read_text(encoding="utf-8"))
FPS = 30


def props(**kw):
    p = {"video": "t/video.mp4", "captions": {"duration": 20.0, "segments": [], "words": []}, "inserts": [], "scenes": [],
         "hook": None, "endCard": None, "camera": None}
    p.update(kw)
    return p


def scene(**kw):
    s = {"id": "c01", "type": "quote", "mode": "overlay", "start": 5.0, "dur": 3.0, "tone": "calm",
         "text": {"lines": ["One line"]}, "transition_in": "cut", "transition_out": "cut", "sound": "card"}
    s.update(kw)
    return s


def test_a_scene_panel_is_its_settled_frame_never_past_the_exit():
    import board as bd
    import visual_plan as vp
    sc = scene()
    T = DOC["scene_tones"]["calm"]
    tl = vp.scene_timeline(sc, T, "overlay", FPS, [], False)
    full = vp.text_full_on(sc, "quote", ["One line"], tl, FPS, [])
    pans = bd.panels(props(scenes=[sc]), {}, DOC, FPS)
    assert [p["frame"] for p in pans] == [150 + full + 9]  # the whole text on screen + 0.3 s
    assert pans[0]["label"] == "c01 quote/overlay" and pans[0]["sound"] == "card" and pans[0]["text"] == "One line"
    short = scene(dur=1.0)  # no room for + 0.3 s: the last settled frame
    tl = vp.scene_timeline(short, T, "overlay", FPS, [], False)
    assert bd.panels(props(scenes=[short]), {}, DOC, FPS)[0]["frame"] == 150 + tl["settle_to"] - 1


def test_a_list_panel_waits_for_its_last_item():
    import board as bd
    sc = scene(type="list", mode="full", dur=5.0, items=[{"text": "a", "t": 5.5}, {"text": "b", "t": 7.0}])
    T = DOC["scene_tones"]["calm"]
    p = bd.panels(props(scenes=[sc]), {}, DOC, FPS)[0]
    import visual_plan as vp
    tl = vp.scene_timeline(sc, T, "full", FPS, [], False)
    assert p["frame"] == 150 + min(max(tl["lead"], 60) + tl["inF"] + 9, tl["settle_to"] - 1)
    assert "a / b" in p["text"]


def test_panels_cover_hook_inserts_cards_end_card_and_shots():
    import board as bd
    pr = props(hook={"text": "Hook", "until": 2.4},
               inserts=[{"id": "b01", "kind": "broll", "mode": "replace", "start": 2.0, "dur": 2.0}],
               endCard={"line1": "Write to us", "line2": "link in bio", "seconds": 2.6},
               camera=[{"t": 0.0, "z": 1.0, "cx": 540, "cy": 960}, {"t": 10.0, "z": 1.2, "cx": 540, "cy": 800}])
    plan = {"inserts": [{"id": "b01", "what": "an office"}],
            "keep_clear": [{"start": 12.0, "end": 14.0, "box": [0, 0, 10, 10], "what": "a role tag"},
                           {"start": 5.0, "end": 8.0, "box": [0, 0, 10, 10], "scene": "c01"}]}
    pans = bd.panels(pr, plan, DOC, FPS)
    assert [p["label"] for p in pans] == ["hook", "b01 broll/replace", "card 1", "end card"]
    assert [p["frame"] for p in pans] == [33, 90, 390, 627]
    assert pans[1]["what"] == "an office" and pans[2]["what"] == "a role tag"
    assert pans[3]["text"] == "Write to us / link in bio"
    shots = bd.panels(pr, plan, DOC, FPS, shots=True)
    assert [p["frame"] for p in shots if p["label"].startswith("shot")] == [15, 315]


def test_two_panels_on_one_frame_become_one():
    import board as bd
    pr = props(inserts=[{"id": "b01", "kind": "broll", "mode": "replace", "start": 2.0, "dur": 2.0},
                        {"id": "m01", "kind": "meme", "mode": "corner", "start": 2.0, "dur": 2.0}])
    pans = bd.panels(pr, {}, DOC, FPS)
    assert len(pans) == 1 and pans[0]["label"] == "b01 broll/replace + m01 meme/corner"


def test_the_sampled_render_is_one_remotion_call_on_the_first_n_frames(project, monkeypatch):
    # Remotion clamps a frozen frame to the composition's length, so the composition keeps the video's length and the
    # render takes its first n frames: frame k shows frames[k]
    import board as bd
    calls = []

    class R:
        returncode, stdout, stderr = 0, "", ""

    def run(cmd, cwd=None, **kw):
        calls.append((cmd, cwd))
        for k in range(3):
            (project / "frames" / f"element-{k}.jpeg").write_bytes(b"jpg")
        return R()
    monkeypatch.setattr(bd.subprocess, "run", run)
    pf = write_json(project / "edit" / "t" / "board-props.json", bd.sample_props(props(), [9, 300, 30]))
    assert json.loads(pf.read_text(encoding="utf-8"))["sample"] == {"frames": [9, 300, 30]}
    imgs, _ = bd.render_frames(project / "reels", "ReelKit", "edit/t/board-props.json", 3, project / "frames", 0.3334)
    cmd = calls[0][0]
    assert cmd[1:5] == ["--no", "remotion", "render", "ReelKit"] and "--sequence" in cmd and "--frames=0-2" in cmd
    assert f"--props={pf.resolve()}" in cmd and "--muted" in cmd
    assert [p.name for p in imgs] == ["element-0.jpeg", "element-1.jpeg", "element-2.jpeg"]
    probe = bd.sample_props(props(), [0, 3], probe=True, media=False)["sample"]
    assert probe == {"frames": [0, 3], "probe": True, "media": False}


@needs_pillow
def test_the_sheet_numbers_the_panels_and_pages_them(tmp_path):
    from PIL import Image
    import board as bd
    imgs = []
    for k in range(7):
        p = tmp_path / f"element-{k}.jpeg"
        Image.new("RGB", (360, 640), (40 * k, 80, 120)).save(p)
        imgs.append(p)
    pans = [{"frame": 30 * k, "label": f"c0{k} quote/overlay", "text": "текст", "sound": "card",
             "tin": "fade", "tout": "cut", "what": ""} for k in range(7)]
    pages = bd.sheet(imgs, pans, tmp_path / "board", FPS, cols=3, per_page=6)
    assert [p.name for p in pages] == ["board-01.jpg", "board-02.jpg"]
    with Image.open(pages[0]) as a, Image.open(pages[1]) as b:
        assert a.size == (3 * 360 + 4 * 8, 2 * (640 + 50) + 3 * 8) and b.size == (3 * 360 + 4 * 8, 640 + 50 + 2 * 8)
    assert bd.ascii_only("те x") == "?? x"


# ── textcheck ──

def box(key, x, y, w, h, a=1.0, v=1.0, text="text"):
    return [key, text, x, y, w, h, a, v]


def test_the_probe_log_is_read_through_remotion_noise():
    import textcheck as tc
    line = lambda f, b: f"\x1b[40m Tab 1, src/kit/Sample.tsx:52 \x1b[49m \x1b[90mRK_TEXT {json.dumps({'f': f, 'b': b})}\x1b[39m"
    log = "\n".join([
        "Rendered 3/9",
        line(3, [box("sub/0", 60, 1250, 800, 68)]),
        f'[1011/235452:INFO:CONSOLE:33] "RK_TEXT {json.dumps({"f": 6, "b": []})}", source: http://localhost:3000/bundle.js (29)',
        line(3, [box("sub/0", 60, 1250, 810, 68)]),  # echoed: the last one wins
        "RK_TEXT {broken",
    ])
    got = tc.parse_log(log)
    assert sorted(got) == [3, 6] and got[3][0][4] == 810 and got[6] == []


def test_text_checks_on_one_frame():
    import textcheck as tc
    kinds = lambda boxes, faces=None: sorted((i[1], i[2]) for i in tc.frame_issues([tuple(b) for b in boxes], faces))
    assert kinds([box("hook/0", 60, 300, 800, 100)]) == []
    assert kinds([box("hook/0", 700, 300, 500, 100)]) == [("UI zone", "hook/0"), ("off the frame", "hook/0")]
    assert kinds([box("hook/0", 60, 300, 800, 100, v=0.9)]) == [("clipped", "hook/0")]
    assert kinds([box("hook/0", 60, 300, 800, 100, a=0.1)]) == []  # fading in: not judged
    assert kinds([box("x/1", 60, 1400, 400, 150)]) == [("UI zone", "x/1")]  # below y 1500
    # two texts on top of each other; two lines of the subtitles are their own layout
    assert kinds([box("hook/0", 60, 300, 800, 100), box("scene:c01/2", 100, 330, 500, 100)]) == [("overlap", "hook/0 | scene:c01/2")]
    assert kinds([box("sub/0", 60, 1250, 800, 70), box("sub/1", 60, 1300, 800, 70)]) == []
    assert kinds([box("hook/0", 60, 300, 800, 100), box("scene:c01/2", 60, 395, 800, 100)]) == []  # touching, not overlapping
    assert kinds([box("hook/0", 60, 300, 800, 100)], faces=[[300, 250, 300, 300]]) == [("on a face", "hook/0")]
    # promo T6: a small caps label 10 px above a heading overlapped the heading's line box, not a letter of it
    assert kinds([box("scene:c05/0", 60, 520, 120, 30), box("scene:c05/1", 60, 540, 600, 100)]) == []


def test_a_problem_counts_when_it_lasts_a_third_of_a_second():
    import textcheck as tc
    off = lambda: [tuple(box("sub/0", 700, 1250, 500, 68))]
    ok = lambda: [tuple(box("sub/0", 60, 1250, 500, 68))]
    per = {f: (off() if f in (30, 33) else ok()) for f in range(0, 120, 3)}  # 0.2 s: an exit animation
    assert tc.check(per, None, 3, FPS) == []
    per = {f: (off() if 30 <= f <= 42 else ok()) for f in range(0, 120, 3)}  # 0.5 s
    issues = tc.check(per, None, 3, FPS)
    assert [(i["kind"], i["start"], i["end"]) for i in issues if i["level"] == "error"] == [("off the frame", 1.0, 1.5)]
    # each subtitle phrase is a new block, still one problem
    per = {f: [tuple(box(f"sub/{f // 30}", 700, 1250, 500, 68))] for f in range(0, 60, 3)}
    assert len([i for i in tc.check(per, None, 3, FPS) if i["kind"] == "off the frame"]) == 1


def test_faces_are_not_checked_where_the_rough_cut_is_covered(project, monkeypatch):
    import faces as fc
    import textcheck as tc
    e = project / "edit" / "t"
    write_json(e / "faces.json", {"video": "final.mp4", "step": 0.25, "geometry": "cover", "w": 1080, "h": 1920,
                                  "samples": [{"t": k * 0.25, "faces": [[400, 400, 280, 360, 0.95]]} for k in range(41)],
                                  "filter": {"v": fc.FILTER_V}})
    plan = {"inserts": [{"id": "b01", "kind": "broll", "mode": "replace", "status": "ready", "start": 2.0, "dur": 2.0}]}
    faces_at = tc.face_source(e, plan, props(captions={"duration": 10.0, "segments": [], "words": []}), FPS)
    assert faces_at(1.0) and all(f == [370, 370, 340, 420] for f in faces_at(1.0))  # the face + 30 px
    assert faces_at(3.0) == []  # under a replacing B-roll
    assert faces_at(10.5) == []  # the end card


def test_faces_follow_the_props_camera_and_stay_on_their_camera_angle(project):
    # review: the camera came from camera.json, not from the props the render draws; next to a change of source the
    # nearest sample of the other angle (up to a 0.25 s step away) put that angle's face on the frame
    import faces as fc
    import textcheck as tc
    e = project / "edit" / "t"
    samples = [{"t": k * 0.25, "faces": [[400, 400, 280, 360, 0.95] if k * 0.25 < 5.0 else [100, 1000, 200, 260, 0.95]]}
               for k in range(41)]
    write_json(e / "faces.json", {"video": "final.mp4", "step": 0.25, "geometry": "cover", "w": 1080, "h": 1920,
                                  "samples": samples, "filter": {"v": fc.FILTER_V}})
    cap = {"duration": 10.0, "words": [], "segments": [{"out_start": 0.0, "source": "a"}, {"out_start": 4.9, "source": "b"}]}
    zoom = [{"t": 0.0, "z": 2.0, "cx": 540, "cy": 580, "drift": 0, "whip": False}]
    faces_at = tc.face_source(e, {}, props(captions=cap, camera=zoom), FPS)
    assert faces_at(1.0)[0] == [230, 570, 620, 780]  # x (400-540)*2+540-30, y (400-580)*2+960-30: the props' camera
    near = tc.face_source(e, {}, props(captions=cap), FPS)
    assert near(4.8) and all(f == [370, 370, 340, 420] for f in near(4.8))  # angle a only, though 5.0 s is 0.2 s away
    assert all(f == [70, 970, 260, 320] for f in near(4.95))  # angle b from its cut on, not a's sample at 4.75


def test_a_check_with_frames_missing_from_the_log_does_not_pass(project, monkeypatch, capsys):
    import board as bd
    import textcheck as tc
    e = project / "edit" / "t"
    write_json(e / "reelkit-props.json", props(captions={"duration": 1.0, "segments": [], "words": []}))
    (project / "reels" / "src").mkdir(parents=True)
    (project / "reels" / "package.json").write_text("{}", encoding="utf-8")
    log = "\n".join(f"RK_TEXT {json.dumps({'f': f, 'b': [box('sub/0', 60, 1250, 500, 68)]})}" for f in range(0, 30, 3) if f != 12)
    monkeypatch.setattr(bd, "render_frames", lambda *a, **k: ([], log))
    monkeypatch.setattr(sys, "argv", ["textcheck.py", "edit/t", "--remotion", str(project / "reels")])
    with pytest.raises(SystemExit) as x:
        tc.main()
    assert x.value.code == 1 and "incomplete: frames 12 were not measured" in capsys.readouterr().out
    assert json.loads((e / "textcheck.json").read_text(encoding="utf-8"))["missing"] == [12]


def test_a_scene_without_its_own_tone_is_timed_by_the_videos_tone_and_mid_entrance_is_the_middle():
    # review: a scene with no tone was timed as calm while the kit drew props.sceneTone; the mid-entrance frame of an
    # overlay fade was halved twice (frame 3 of a 14-frame entrance instead of 7)
    import board as bd
    import visual_plan as vp
    sc = scene(tone=None)
    T = DOC["scene_tones"]["punchy"]
    tl = vp.scene_timeline(sc, T, "overlay", FPS, [], False)
    full = vp.text_full_on(sc, "quote", ["One line"], tl, FPS, [])
    assert bd.panels(props(scenes=[sc], sceneTone="punchy"), {}, DOC, FPS)[0]["frame"] == 150 + full + 9
    fade = scene(transition_in="fade")
    mids = [p for p in bd.panels(props(scenes=[fade]), {}, DOC, FPS, transitions=True) if p["what"] == "mid-transition"]
    assert [p["frame"] for p in mids] == [150 + DOC["scene_tones"]["calm"]["in"] // 2]
    split = scene(mode="split", transition_in="fade")
    mids = [p for p in bd.panels(props(scenes=[split]), {}, DOC, FPS, transitions=True) if p["what"] == "mid-transition"]
    assert [p["frame"] for p in mids] == [150 + vp.layout_frames("fade", DOC["scene_tones"]["calm"], "in") // 2]


def test_a_picture_defect_gets_a_panel_with_how_it_is_handled():
    import board as bd
    d = {"id": "d01", "kind": "turned", "start": 4.0, "end": 4.6, "words": "a glance away"}
    pans = bd.panels(props(), {}, DOC, FPS, defects=[(d, "covered by b01")])
    assert [(p["frame"], p["label"], p["what"], p["text"]) for p in pans] == [(129, "d01 turned", "covered by b01", "a glance away")]
