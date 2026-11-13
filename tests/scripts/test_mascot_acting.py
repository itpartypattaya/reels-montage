"""The mascot's acting: a pose change hidden by a blink, the blink's own shape and rhythm (references/mascot.md →
Motion, references/mascot-atlas.md → In the kit).

Requirements:
- a pose change that changes the picture is hidden by a blink: the eyes are fully shut on the change's own frame and
  the next one, the frames where the atlas swaps its pictures, and half shut on the frame before and the frame after;
  a change that the viewer cannot see (a stand-in drawing the same pose) gets no blink;
- a planned blink keeps half a second away from the blink of a pose change (two blinks in a row read as a tic);
- every blink is half shut, shut, shut, half shut (four frames at 30 fps, as long at another frame rate); about one
  blink in five is a double blink; the blinks come every 2.6-4.6 s; the same video gets the same blinks every time;
- a module written before the eyelid had degrees still sees its yes/no blink, on the frames the lids are at least
  half shut;
- at a lower frame rate a blink keeps its four frames (the swap needs both shut ones) and the two blinks of a double
  blink never run into one: two open frames between them at least;
- the kit: the atlas swaps its pictures only while the eyes are shut: the new picture half over the old on the
  change's first frame, the old one half under the new on the second, then the new one alone; a pose with a drawn
  blink frame shows it half over the open picture on the half-shut frames and alone on the shut ones; a plan written
  before this (no lid, no since) still plays: the lid follows the old yes/no blink and the picture switches halfway
  through the change.
"""
import json
import subprocess

import pytest

from test_callouts import KIT, needs_node

GEO = {"box": (400, 520), "anchor": (200, 170), "poses": ["neutral", "palm", "think"], "symmetric": False}
CALM = {"brand_tone": {"overshoot": False, "mascot": "calm", "scene_tone": "calm"}, "scene_tone": "calm"}


def plan_frames(track, dur=10.0, fps=30, vid="v1", geo=GEO):
    """Every frame's entry of the per-frame plan (the kit holds an entry until the next one)."""
    import mascot_plan as vm
    m = {"track": [{"t": t, "pose": p} for t, p in track], "from": 0.0, "to": dur, "facing": 1}
    plan = {"id": vid, "duration": dur, "inserts": []}
    fr = vm.frames_of(m, plan, CALM, geo, [0.0] * int(dur * fps), fps)
    out, j = [], 0
    for f in range(int(round(dur * fps))):
        while j + 1 < len(fr) and fr[j + 1]["f"] <= f:
            j += 1
        out.append(fr[j])
    return out


def lid(e):
    """How shut the eyes are; a plan without the lid reads its yes/no blink as fully shut."""
    return e.get("lid", 1.0 if e["blink"] else 0.0)


def runs(frames):
    """[(first frame, [lids])] of every stretch of frames with the eyes not fully open."""
    out, cur = [], None
    for f, e in enumerate(frames):
        v = lid(e)
        if v > 0:
            if cur is None:
                cur = (f, [])
                out.append(cur)
            cur[1].append(v)
        else:
            cur = None
    return out


def test_a_pose_change_is_hidden_by_a_blink_shut_where_the_picture_swaps():
    fr = plan_frames([(2.0, "palm")])  # frame 60
    assert [lid(fr[f]) for f in range(57, 65)] == [0, 0, 0.5, 1, 1, 0.5, 0, 0]
    # the frames the atlas swaps on (since 0 and 1) are the shut ones; since counts while the change eases (12 frames)
    # and four frames more, for a drawn mascot's parts that follow it (test_mascot_overlap.py)
    assert [fr[f].get("since") for f in range(59, 79)] == [None] + list(range(17)) + [None, None]
    assert fr[61]["pose"] == "palm" and fr[61]["prev"] == "neutral"


def test_a_change_the_viewer_cannot_see_gets_no_blink():
    # the mascot has no talk pose: talk is drawn as neutral, the picture does not change
    fr = plan_frames([(2.0, "talk")], geo={**GEO, "poses": ["neutral"]})
    assert fr[60]["pose"] == "neutral"
    assert all(lid(fr[f]) == 0 for f in range(54, 67)), [lid(fr[f]) for f in range(54, 67)]


def test_a_planned_blink_keeps_half_a_second_from_a_change_blink():
    fps = 30
    track, t, poses = [], 1.0, ["palm", "think", "neutral"]
    while t < 58:  # a change every 1.1 s: every planned blink falls near one
        track.append((round(t, 2), poses[len(track) % 3]))
        t += 1.1
    fr = plan_frames(track, dur=60.0, vid="busy")
    change = set()
    for tc, _ in track:
        fc = round(tc * fps)
        assert [lid(fr[f]) for f in range(fc - 1, fc + 3)] == [0.5, 1, 1, 0.5], tc
        change.update(range(fc - 1, fc + 3))
    other = [f for f, e in enumerate(fr) if lid(e) > 0 and f not in change]
    near = [f for f in other if any(abs(f - c) < 0.5 * fps for c in change)]
    assert not near, near[:10]


def test_every_blink_is_half_shut_twice_and_shut_twice_and_old_modules_see_it():
    fr = plan_frames([], dur=120.0, vid="long")
    shape = [0.5, 1, 1, 0.5]
    rs = runs(fr)
    assert rs
    for _, lids in rs:
        assert lids == shape, lids
    # the yes/no blink of a module written before the lid: on the frames at least half shut
    assert all(e["blink"] == (lid(e) >= 0.5) for e in fr)


def test_about_every_fifth_blink_is_double_and_the_rhythm_stays_human():
    fps = 30
    fr = plan_frames([], dur=600.0, vid="rhythm")
    starts = [f for f, _ in runs(fr)]
    series, doubles = [], 0  # a double blink: the second run starts within 0.4 s of the first
    for s in starts:
        if series and s - series[-1][-1] <= 0.4 * fps:
            series[-1].append(s)
            doubles += 1
        else:
            series.append([s])
    assert all(len(x) <= 2 for x in series)
    share = doubles / len(series)
    assert 0.1 <= share <= 0.3, share
    gaps = [(b[0] - a[0]) / fps for a, b in zip(series, series[1:])]
    assert min(gaps) >= 2.6 - 1.0 / fps and max(gaps) <= 4.6 + 1.0 / fps, (min(gaps), max(gaps))
    assert len(set(round(g, 1) for g in gaps)) > 8  # uneven, not one fixed beat


@pytest.mark.parametrize("fps", [15, 25])
def test_at_a_lower_frame_rate_a_blink_keeps_its_frames_and_double_blinks_stay_apart(fps):
    fr = plan_frames([(2.0, "palm")], dur=600.0, fps=fps, vid="rhythm")
    rs = runs(fr)
    assert all(lids == [0.5, 1, 1, 0.5] for _, lids in rs), [x for x in rs if x[1] != [0.5, 1, 1, 0.5]][:3]
    fc = round(2.0 * fps)
    assert lid(fr[fc]) == 1 and lid(fr[fc + 1]) == 1
    gaps = [b[0] - (a[0] + len(a[1])) for a, b in zip(rs, rs[1:])]
    assert min(gaps) >= 2, min(gaps)
    assert sum(1 for g in gaps if g < 0.4 * fps) > 10  # the double blinks are still there


def test_the_blinks_are_the_same_for_the_same_video():
    # a safeguard the plan relies on (no randomness between renders), already true before the change
    assert plan_frames([(2.0, "palm")], vid="a") == plan_frames([(2.0, "palm")], vid="a")
    assert plan_frames([], dur=30.0, vid="a") != plan_frames([], dur=30.0, vid="b")


def test_at_60_fps_the_blink_lasts_as_long_and_stays_shut_over_the_swap():
    fr = plan_frames([(2.0, "palm")], fps=60)
    fc = 120
    assert [lid(fr[f]) for f in range(fc - 3, fc + 6)] == [0, 0.5, 0.5, 1, 1, 1, 1, 0.5, 0.5]
    assert [fr[f].get("since") for f in (fc, fc + 1, fc + 2)] == [0, 1, 2]


# ── the kit ──

KIT_FRAME = KIT / "kit" / "mascot" / "frame.ts"


def run_kit(code, data):
    r = subprocess.run(["node", "--input-type=module", "-e", code, KIT_FRAME.as_uri(), json.dumps(data)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_the_atlas_swaps_its_pictures_under_the_shut_eyes():
    # the entries the plan writes for a change on frame 60 (the test above checks them): shut, shut, half shut
    entries = [{"f": 60 + i, "pose": "palm", "prev": "neutral", "k": k, "open": 0, "blink": True, "lid": v, "since": i}
               for i, (k, v) in enumerate(((0, 1), (0.23, 1), (0.42, 0.5)))]
    entries.append({"f": 72, "pose": "palm", "prev": "neutral", "k": 1, "open": 0, "blink": False, "lid": 0})
    code = ("const m = await import(process.argv[1]); const es = JSON.parse(process.argv[2]);"
            "console.log(JSON.stringify(es.map((e) => m.switchLayers(m.frameOf(e, e.f / 30, 1)))));")
    got = run_kit(code, entries)
    assert got == [[{"pose": "neutral", "opacity": 1}, {"pose": "palm", "opacity": 0.5}],
                   [{"pose": "neutral", "opacity": 0.5}, {"pose": "palm", "opacity": 1}],
                   [{"pose": "palm", "opacity": 1}],
                   [{"pose": "palm", "opacity": 1}]]
    # two pictures only on the frames whose eyes are shut
    assert [len(g) > 1 for g in got] == [e["lid"] == 1 for e in entries]


@needs_node
def test_a_drawn_blink_frame_shows_half_over_the_open_picture_on_the_half_shut_frames():
    code = ("const m = await import(process.argv[1]); const cs = JSON.parse(process.argv[2]);"
            "console.log(JSON.stringify(cs.map((c) => m.atlasEyes(...c))));")
    got = run_kit(code, [[0, True, False], [0.5, True, False], [1, True, False], [0.5, False, False],
                         [1, True, True]])
    assert got == [{"sprite": 0, "overlay": 0}, {"sprite": 0.5, "overlay": 0}, {"sprite": 1, "overlay": 0},
                   {"sprite": 0, "overlay": 0.5}, {"sprite": 0, "overlay": 1}]


@needs_node
def test_a_plan_from_before_the_lid_still_plays():
    old = [{"f": 0, "pose": "palm", "prev": "neutral", "k": 0.4, "open": 0.5, "blink": True},
           {"f": 1, "pose": "palm", "prev": "neutral", "k": 0.6, "open": 0, "blink": False}]
    code = ("const m = await import(process.argv[1]); const es = JSON.parse(process.argv[2]);"
            "console.log(JSON.stringify(es.map((e) => { const f = m.frameOf(e, e.f / 30, 1);"
            " return [f.lid, f.blink, f.talking, m.switchLayers(f).map((l) => l.pose)]; })));")
    assert run_kit(code, old) == [[1, True, True, ["neutral"]], [0, False, False, ["palm"]]]
