"""The mascot's mouth as speech: open by the loudness of the recorded voice and wide or round by its spectrum, drawn
over the pose's own expression (references/mascot.md → The mouth, How Claude draws).

Requirements:
- on a vowel with its energy high in the spectrum (the "ee" of "see") the mouth is wide, on one with its energy low
  (the "oo" of "too") it is round; the same for a low and a high voice; a recording of one vowel only never turns
  the scale over (its own small changes are not stretched into wide and round);
- where nobody speaks the width is neutral (0.5), whatever sound is there;
- the opening has four levels (shut, a third, two thirds, full) and a level, once reached inside speech, holds at
  least two frames: the mouth does not flutter;
- the mouth opens one frame before the sound and shuts one frame before the sound stops, also where the plan's own
  speaking spans start and end with the sound; a phrase that starts on the first frame keeps its first level two
  frames too;
- a mouth.json measured by the older version (one axis) is stale: stage asks to measure it again;
- the per-frame plan carries the width; the kit reads a plan from before as neutral width;
- the kit's mouthPath keeps the pose's expression while the mouth speaks: the corners stay at its height (and where it
  put them at a neutral width), the upper lip keeps its curve, a wide mouth is wider and flatter than a round one.

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
@pytest.mark.parametrize("f0,scale", [(110, 1.0), (210, 1.15)], ids=["low voice", "high voice"])
def test_a_recording_of_one_vowel_does_not_turn_the_scale_over(project, f0, scale):
    got = {}
    for name, v in (("ee", EE), ("oo", OO)):
        e = project / "edit" / f"one-{name}"
        record(e / "voice.wav", vowel_expr([(0.5, 3.5, v)], f0, scale), 4.0)
        m = mouth(project, e)
        got[name] = median([m["wide"][f] for f in frames(m, 0.7, 3.3)])
    assert got["ee"] >= 0.5 and got["oo"] <= 0.25 and got["ee"] > got["oo"], got


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
    assert not short_levels(m["open"]), short_levels(m["open"])[:10]


def short_levels(opens):
    """The first frames of open levels held a single frame and followed by another open level (a level the speech
    ends on may shut at once)."""
    out, f = [], 0
    while f < len(opens):
        g = f
        while g + 1 < len(opens) and opens[g + 1] == opens[f]:
            g += 1
        if opens[f] != 0 and g == f and g + 1 < len(opens) and opens[g + 1] != 0:
            out.append(f)
        f = g + 1
    return out


def test_a_phrase_from_the_first_frame_keeps_its_first_level_two_frames():
    import math
    from array import array
    import mascot as M
    sr, fps, n = 16000, 30, 20
    per = sr // fps
    # a word from the very start: one loud frame, then a softer voice (the level steps down after the first frames)
    a = array("h", (int((12000 if i < per else 4800) * math.sin(2 * math.pi * 220 * i / sr)) for i in range(n * per)))
    opens, wide, _ = M.envelope(a, sr, fps, [(0.0, n / fps)])
    assert opens[0] > 0 and len(set(opens)) > 1, opens
    assert not short_levels(opens), opens[:6]


def test_the_plans_speaking_span_keeps_the_frame_the_mouth_opens_early():
    import mascot_plan as vm
    geo = {"box": (400, 520), "anchor": (200, 170), "poses": ["neutral"], "symmetric": False}
    # the sound in [1, 2) s: mouth.json opens on frame 29 and shuts after frame 58
    opens = [0.0] * 29 + [0.667] * 30 + [0.0] * 31
    m = {"track": [], "from": 0.0, "to": 3.0, "facing": 1, "speaks": [[1.0, 2.0]]}
    plan = {"id": "s", "duration": 3.0, "inserts": []}
    fr = vm.frames_of(m, plan, {"brand_tone": {"mascot": "calm"}}, geo, opens, 30, None, [0.5] * 90)
    at = lambda f: [x for x in fr if x["f"] <= f][-1]
    assert [at(f)["open"] for f in (28, 29, 58, 59)] == [0, 0.667, 0.667, 0]


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
            " m.mouthPath({width: 50, curve: -6}, 0.6, 0.5), m.mouthPath(smile, 0.3, 0.5), m.mouthPath(smile, 1, 0.5)];"
            "console.log(JSON.stringify(r.map((x) => ({filled: x.filled, p: pts(x.d), w: x.width, h: x.height}))));")
    closed, wide, round_, frown, *neutral = node(code, KIT_RIG.as_uri())
    assert not closed["filled"] and wide["filled"] and round_["filled"]
    # the path starts at the left corner and its first curve ends at the right one: both on the expression's line
    for x in (closed, wide, round_, frown, *neutral):
        assert x["p"][1] == 0 and x["p"][5] == 0, x["p"]
    # at a neutral width the corners and the upper lip are the expression's, however far it opens
    for x in (closed, *neutral):
        assert x["p"][0] == -25 and x["p"][4] == 25 and x["p"][3] == 16, x["p"]
    assert frown["p"][3] == -12
    assert wide["w"] > round_["w"] and round_["h"] > wide["h"]
