"""The mascot's pose change as acting: overlapping action and follow-through (references/mascot.md → Motion,
references/mascot-sample.md).

Requirements:
- a calm change (any tone but a loud one with a full mascot) eases out over 12 frames exactly as before;
- with a loud scene tone and a full mascot a change is a click: it reaches its pose two frames after it begins (three
  quarters of the way after one) and holds it,
  with no overshoot; where the brand tone also overshoots, the click swings past the pose and back, a wobble that
  fades out within the change (never more than an eighth of the move past it);
- the plan keeps `since` four frames after a change has eased (and on the frame it ends), and says how it moves (`ease`), so the parts of a
  drawn mascot can follow at their own pace: the kit gives the module the change's progress for a part that lags
  up to four frames behind it (the eyes with it, the arms after, the hands and elbows last), read from the plan
  itself, also where the plan ends before the change has; the latest part lands with the last frame of `since`, for
  every kind of change;
- a module written before (it blends with `poseAt`) gets the same k as before; a part with no lag moves with the
  change; a plan staged before (no `ease`) plays with no lags at all.
"""
import json
import subprocess

from test_callouts import KIT, needs_node

GEO = {"box": (400, 520), "anchor": (200, 170), "poses": ["neutral", "palm"], "symmetric": False}
CALM = {"brand_tone": {"mascot": "calm", "overshoot": False, "scene_tone": "calm"}, "scene_tone": "calm"}
LOUD = {"brand_tone": {"mascot": "full", "overshoot": False, "scene_tone": "punchy"}, "scene_tone": "punchy"}
BOUNCY = {"brand_tone": {"mascot": "full", "overshoot": True, "scene_tone": "punchy"}, "scene_tone": "punchy"}
FC = 60  # the change at 2.0 s


def plan(s, dur=4.0):
    import mascot_plan as vm
    m = {"track": [{"t": 2.0, "pose": "palm"}], "from": 0.0, "to": dur, "facing": 1}
    return vm.frames_of(m, {"id": "o", "duration": dur, "inserts": []}, s, GEO, [0.0] * int(dur * 30), 30)


def at(fr, f):
    return [x for x in fr if x["f"] <= f][-1]


def test_a_calm_change_eases_out_over_twelve_frames_as_before():
    fr = plan(CALM)
    ks = [at(fr, FC + i)["k"] for i in range(14)]
    want = [round(1 - (1 - min(1, i / 12)) ** 3, 3) for i in range(14)]
    assert ks == want, ks
    assert {at(fr, FC + i).get("ease") for i in range(16)} == {"out"}


def test_a_loud_change_clicks_into_its_pose_and_holds_it():
    fr = plan(LOUD)
    ks = [at(fr, FC + i)["k"] for i in range(10)]
    assert ks[:3] == [0, 0.75, 1] and all(k == 1 for k in ks[2:]), ks
    assert at(fr, FC)["ease"] == "snap"


def test_where_the_tone_overshoots_the_click_swings_past_and_settles():
    fr = plan(BOUNCY)
    ks = [at(fr, FC + i)["k"] for i in range(20)]
    assert ks[2] == 1 and max(ks) > 1.03 and max(ks) <= 1.125, ks
    past = [i for i, k in enumerate(ks) if k > 1]
    back = [i for i, k in enumerate(ks) if k < 1 and i > 2]
    assert past and back and past[0] < back[0], ks  # past the pose first, then back under it
    assert all(abs(k - 1) < 0.01 for k in ks[14:]), ks[14:]
    assert at(fr, FC)["ease"] == "settle"


def test_since_runs_four_frames_past_the_change():
    for s, n in ((CALM, 12), (LOUD, 2), (BOUNCY, 14)):
        fr = plan(s)
        since = [at(fr, f).get("since") for f in range(FC - 1, FC + n + 6)]
        assert since == [None] + list(range(n + 5)) + [None], (s["scene_tone"], since)


FRAME = KIT / "kit" / "mascot" / "frame.ts"
RIG = KIT / "kit" / "mascot" / "rig.ts"


def node(code, *args):
    r = subprocess.run(["node", "--input-type=module", "-e", code, *args], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def lagged(entries, frames, lags):
    """Per frame: the module's pose numbers through poseAtLagged and through poseAt, from the plan's entries."""
    code = ("const fr = await import(process.argv[1]); const rig = await import(process.argv[2]);"
            "const E = JSON.parse(process.argv[3]); const F = JSON.parse(process.argv[4]);"
            "const L = JSON.parse(process.argv[5]);"
            "const P = {neutral: {eye: 0, arm: 0, hand: 0, body: 0}, palm: {eye: 10, arm: 100, hand: 200, body: 50}};"
            "console.log(JSON.stringify(F.map((f) => { const x = fr.frameOf(fr.planAt(E, f), f / 30, 1, E, f);"
            " return {f, kLag: x.kLag ?? null, lag: rig.poseAtLagged(P, x, L), plain: rig.poseAt(P, x)}; })));")
    return node(code, FRAME.as_uri(), RIG.as_uri(), json.dumps(entries), json.dumps(frames), json.dumps(lags))


LAGS = {"eye": -2, "body": 0, "arm": 2, "hand": 3}  # a lag under 0 is read as 0: nothing runs ahead of a change


@needs_node
def test_the_parts_follow_the_change_at_their_own_pace():
    fr = plan(CALM)
    k = {f: at(fr, f)["k"] for f in range(FC - 5, FC + 30)}
    k_of = lambda g: 0 if g < FC else k[g]  # the change's own k on frame g (before it began: 0)
    out = {x["f"]: x for x in lagged(fr, list(range(FC, FC + 16)), LAGS)}
    for f in range(FC, FC + 16):
        got = out[f]["lag"]
        # each part is where the change was its lag ago: the arm two frames behind, the hand three, the eyes and the
        # body with it
        assert abs(got["body"] - 50 * k_of(f)) < 1e-6, (f, got)
        assert abs(got["eye"] - 10 * k_of(f)) < 1e-6, (f, got)
        assert abs(got["arm"] - 100 * k_of(f - 2)) < 1e-6, (f, got)
        assert abs(got["hand"] - 200 * k_of(f - 3)) < 1e-6, (f, got)
    # a frame into the change the eyes have moved and the hand has not
    assert out[FC + 1]["lag"]["hand"] == 0 and out[FC + 1]["lag"]["eye"] > 0


@needs_node
def test_the_latest_part_lands_on_the_last_frame_of_since():
    for s in (CALM, LOUD, BOUNCY):
        fr = plan(s)
        last = max(f for f in range(FC, FC + 30) if at(fr, f).get("since") is not None)
        out = {x["f"]: x for x in lagged(fr, [last - 1, last, last + 1], {"hand": 9, "arm": 3})}
        # the hand's lag is clamped to four: it lands on the last frame of since, the arm (three) a frame earlier
        assert out[last - 1]["lag"]["hand"] < 200 and out[last]["lag"]["hand"] == 200, out
        assert out[last - 1]["lag"]["arm"] == 100, out
        assert out[last + 1]["kLag"] is None  # settled: no lags any more, every part in the pose


@needs_node
def test_a_plan_that_ends_before_the_change_has_eased_keeps_the_parts_moving():
    # the mascot leaves the screen 0.2 s after the change: its last entries are still easing
    fr = plan(CALM, dur=2.2)
    last = fr[-1]["f"]
    out = {x["f"]: x for x in lagged(fr, [last - 1, last], {"arm": 2})}
    k = {f: at(fr, f)["k"] for f in range(FC, last + 1)}
    assert abs(out[last]["lag"]["arm"] - 100 * k[last - 2]) < 1e-6 and out[last]["lag"]["arm"] < 100, out


@needs_node
def test_a_module_written_before_and_a_plan_staged_before_play_as_before():
    fr = plan(CALM)
    out = lagged(fr, list(range(FC, FC + 14)), LAGS)
    for x in out:  # poseAt (a module written before) moves every part with the plan's k
        k = at(fr, x["f"])["k"]
        assert x["plain"] == {"eye": 10 * k, "arm": 100 * k, "hand": 200 * k, "body": 50 * k}, x
    # a plan staged before: since but no ease (kit 1.20.0-1.21.0): no lags, poseAtLagged is poseAt
    old = [{key: v for key, v in e.items() if key != "ease"} for e in fr]
    for x in lagged(old, list(range(FC, FC + 14)), LAGS):
        assert x["kLag"] is None and x["lag"] == x["plain"], x


@needs_node
def test_a_mascot_that_comes_on_while_a_change_moves_never_moves_a_part_backwards():
    # the change at 2.0 s, the mascot on screen from 2.1 s: the plan's entries start three frames into it
    import mascot_plan as vm
    m = {"track": [{"t": 2.0, "pose": "palm"}], "from": 2.1, "to": 4.0, "facing": 1}
    fr = vm.frames_of(m, {"id": "o", "duration": 4.0, "inserts": []}, CALM, GEO, [0.0] * 120, 30)
    first = fr[0]["f"]
    out = lagged(fr, list(range(first, first + 20)), {"hand": 4})
    hand = [x["lag"]["hand"] for x in out]
    assert all(b >= a - 1e-9 for a, b in zip(hand, hand[1:])), hand  # it never turns back
    assert abs(hand[0] - 200 * fr[0]["k"]) < 1e-6 and hand[-1] == 200, hand  # from where the plan starts, to the pose
