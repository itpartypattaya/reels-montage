"""The mascot's mouth as speech: open by the loudness of the recorded voice and wide or round by its spectrum, drawn
over the pose's own expression (references/mascot.md → The mouth, How Claude draws).

Requirements:
- on a vowel with its energy high in the spectrum (the "ee" of "see") the mouth is wide, on one with its energy low
  (the "oo" of "too") it is round; the same for a low and a high voice, since each recording is measured against itself;
- where nobody speaks the width is neutral (0.5), whatever sound is there;
- the opening has four levels (shut, a third, two thirds, full) and a level, once reached inside speech, holds at
  least two frames: the mouth does not flutter;
- the mouth opens one frame before the sound and shuts one frame before the sound stops;
- a mouth.json measured by the older version (one axis) is stale: stage asks to measure it again;
- the per-frame plan carries the width; the kit reads a plan from before as neutral width;
- the kit's mouthPath keeps the pose's expression while the mouth speaks: the corners stay where the expression put
  them, a wide mouth is wider and flatter than a round one at the same opening.

These signals are stand-ins built of a few partials at the formants of two vowels, not a voice: the thresholds still
have to be checked on real recordings (a man's and a woman's voice), which the tests cannot do.
"""
import json
import subprocess

import pytest

from conftest import ffmpeg, needs_ffmpeg, run_script, write_json
from test_callouts import KIT, needs_node
from test_mascot import mascot_project

# (F1, F2) of the two vowels, Hz, for a voice of a man; a woman's are about 15 % higher
EE, OO = (300, 2300), (320, 800)


def vowel_expr(spans, f0, scale=1.0, amp=0.3):
    """An aevalsrc expression: inside each (a, b, vowel) a voiced sound: the pitch f0 and its partials near the
    vowel's two formants, as a vowel's spectrum has them; silence elsewhere."""
    parts = []
    for a, b, (f1, f2) in spans:
        f1, f2 = f1 * scale, f2 * scale
        h1, h2 = max(1, round(f1 / f0)), max(2, round(f2 / f0))
        tone = (f"(0.25*sin(2*PI*{f0}*t)+0.6*sin(2*PI*{h1 * f0}*t)+0.3*sin(2*PI*{(h1 + 1) * f0}*t)"
                f"+0.45*sin(2*PI*{h2 * f0}*t)+0.2*sin(2*PI*{(h2 + 1) * f0}*t))")
        parts.append(f"{tone}*between(t,{a},{b})")
    return f"{amp}*({'+'.join(parts)})/1.8"


def record(path, expr, dur, rate=48000):
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-f", "lavfi", "-i", f"aevalsrc='{expr}':s={rate}:d={dur}", path)
    return path


def mouth(project, e):
    run_script("mascot.py", "mouth", f"edit/{e.name}", cwd=project)
    return json.loads((e / "mouth.json").read_text(encoding="utf-8"))


def frames(m, a, b):
    fps = m["fps"]
    return [f for f in range(m["frames"]) if f / fps >= a and (f + 1) / fps <= b]


def median(v):
    s = sorted(v)
    return s[len(s) // 2]


@needs_ffmpeg
@pytest.mark.parametrize("f0,scale", [(110, 1.0), (210, 1.15)], ids=["low voice", "high voice"])
def test_ee_is_wide_and_oo_is_round_for_a_low_and_a_high_voice(project, f0, scale):
    e = project / "edit" / "v1"
    spans = [(0.5, 1.5, EE), (2.0, 3.0, OO), (3.5, 4.5, EE), (5.0, 6.0, OO)]
    record(e / "voice.wav", vowel_expr(spans, f0, scale), 6.5)
    m = mouth(project, e)
    ee = [m["wide"][f] for a, b, v in spans if v == EE for f in frames(m, a + 0.15, b - 0.15)]
    oo = [m["wide"][f] for a, b, v in spans if v == OO for f in frames(m, a + 0.15, b - 0.15)]
    assert median(ee) >= 0.75 and median(oo) <= 0.25, (median(ee), median(oo))


@needs_ffmpeg
def test_where_nobody_speaks_the_width_is_neutral(project):
    e = project / "edit" / "v2"
    # a quiet hiss under the whole track (a room, a fan) and two vowels on top of it
    expr = vowel_expr([(0.5, 1.5, EE), (2.5, 3.5, OO)], 120) + "+0.003*sin(2*PI*3100*t)"
    record(e / "voice.wav", expr, 4.0)
    m = mouth(project, e)
    assert len(m["wide"]) == m["frames"] == len(m["open"])
    quiet = frames(m, 1.6, 2.4) + frames(m, 3.6, 4.0)
    assert all(m["wide"][f] == 0.5 for f in quiet), [m["wide"][f] for f in quiet]


@needs_ffmpeg
def test_the_opening_has_four_levels_and_does_not_flutter(project):
    e = project / "edit" / "v3"
    # syllables: the loudness rises and falls five times a second inside two phrases
    voiced = vowel_expr([(0.5, 3.0, EE), (3.5, 6.0, OO)], 130, amp=1.0)
    record(e / "voice.wav", f"0.3*(0.55+0.45*sin(2*PI*5*t))*({voiced})", 6.5)
    m = mouth(project, e)
    lv = {0.0, 0.333, 0.667, 1.0}
    assert set(m["open"]) <= lv, sorted(set(m["open"]) - lv)
    assert len(set(m["open"])) >= 3  # it does use the levels between shut and full
    run, short = 1, []
    for f in range(1, m["frames"]):
        if m["open"][f] == m["open"][f - 1]:
            run += 1
            continue
        # a level held a single frame inside speech (not the one before the speech stops, which shuts at once)
        if run < 2 and m["open"][f] != 0 and f >= 2 and m["open"][f - 2] != 0:
            short.append(f - 1)
        run = 1
    assert not short, short[:10]


@needs_ffmpeg
def test_the_mouth_opens_a_frame_before_the_sound(project):
    e = project / "edit" / "v4"
    record(e / "voice.wav", vowel_expr([(1.0, 2.0, EE)], 120), 3.0)  # the sound starts on frame 30, stops after 59
    m = mouth(project, e)
    assert m["open"][28] == 0 and m["open"][29] > 0, m["open"][26:33]
    assert m["open"][58] > 0 and all(m["open"][f] == 0 for f in range(59, 70)), m["open"][55:62]


@needs_ffmpeg
def test_a_mouth_measured_by_the_older_version_is_stale(project):
    import mascot_plan as vm
    e, rem = mascot_project(project)
    run_script("mascot.py", "mouth", "edit/4821", cwd=project)
    assert vm.load_mouth(e)[1] is None
    m = json.loads((e / "mouth.json").read_text(encoding="utf-8"))
    m["version"] = 1
    m.pop("wide")
    write_json(e / "mouth.json", m)
    problem = vm.load_mouth(e)[1]
    assert problem and "older" in problem, problem  # the command is named by stage and validate, as for any stale mouth
    run_script("mascot.py", "plan", "edit/4821", "--pose", "word:resume#1=point_left", cwd=project)
    run_script("brand.py", "stage", "acme", "--remotion", rem, cwd=project)
    (e / "final.mp4").write_bytes(b"a rough cut")
    r = run_script("visual_plan.py", "stage", "edit/4821", "--remotion", rem, "--props", rem / "props.json",
                   cwd=project, check=False)
    assert r.returncode != 0 and "mascot.py mouth" in (r.stdout + r.stderr), r.stdout + r.stderr


def test_the_plan_carries_the_width_only_while_it_speaks():
    import mascot_plan as vm
    geo = {"box": (400, 520), "anchor": (200, 170), "poses": ["neutral"], "symmetric": False}
    m = {"track": [], "from": 0.0, "to": 3.0, "facing": 1, "speaks": [[0.0, 1.0]]}
    plan = {"id": "w", "duration": 3.0, "inserts": []}
    s = {"brand_tone": {"mascot": "calm"}, "scene_tone": "calm"}
    opens, wides = [0.667] * 90, [1.0] * 45 + [0.0] * 45
    fr = vm.frames_of(m, plan, s, geo, opens, 30, None, wides)
    at = lambda f: [x for x in fr if x["f"] <= f][-1]
    assert at(10)["wide"] == 1.0 and at(10)["open"] == 0.667
    assert at(50)["open"] == 0 and at(50)["wide"] == 0.5  # outside speaks: shut and neutral


KIT_FRAME = KIT / "kit" / "mascot" / "frame.ts"
KIT_RIG = KIT / "kit" / "mascot" / "rig.ts"


def node(code, *args):
    r = subprocess.run(["node", "--input-type=module", "-e", code, *args], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_the_kit_reads_a_plan_without_width_as_neutral():
    code = ("const m = await import(process.argv[1]);"
            "console.log(JSON.stringify([m.frameOf({f: 0, pose: 'neutral', prev: 'neutral', k: 1, open: 0.5,"
            " blink: false}, 0, 1).wide, m.frameOf({f: 0, pose: 'neutral', prev: 'neutral', k: 1, open: 0.5,"
            " blink: false, wide: 0.9}, 0, 1).wide]));")
    assert node(code, KIT_FRAME.as_uri()) == [0.5, 0.9]


@needs_node
def test_mouth_path_keeps_the_expression_while_it_speaks():
    code = ("const m = await import(process.argv[1]); const smile = {width: 50, curve: 8};"
            "const pts = (d) => d.match(/-?\\d+(\\.\\d+)?/g).map(Number);"
            "const r = [m.mouthPath(smile, 0, 0.5), m.mouthPath(smile, 0.6, 1), m.mouthPath(smile, 0.6, 0),"
            " m.mouthPath({width: 50, curve: -6}, 0.6, 0.5)];"
            "console.log(JSON.stringify(r.map((x) => ({filled: x.filled, p: pts(x.d), w: x.width, h: x.height}))));")
    closed, wide, round_, frown = node(code, KIT_RIG.as_uri())
    assert not closed["filled"] and wide["filled"] and round_["filled"]
    # the path starts at the left corner and its first curve ends at the right one: both on the expression's line
    for x in (closed, wide, round_, frown):
        assert x["p"][1] == 0 and x["p"][5] == 0, x["p"]
    # the smile's upper lip still dips below the corners while it speaks; a frown's rises above them
    assert wide["p"][3] > 0 and frown["p"][3] < 0
    assert wide["w"] > round_["w"] and round_["h"] > wide["h"]
