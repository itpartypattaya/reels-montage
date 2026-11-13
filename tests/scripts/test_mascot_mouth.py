"""The mascot's mouth as speech: open by the loudness of the recorded voice and wide or round by its spectrum, drawn
over the pose's own expression (references/mascot.md → The mouth, How Claude draws).

Requirements:
- on a vowel with its energy high in the spectrum (the "ee" of "see") the mouth is wide, on one with its energy low
  (the "oo" of "too") it is round; the same for a low and a high voice; a recording of one vowel only never turns
  the scale over: it stays near neutral (its own small changes are not stretched into wide and round, and with no
  second vowel to compare there is no telling an "ee" from an "oo" of another voice);
- in ordinary speech (the open "a" most often, a consonant's hiss between the syllables) the mouth is not mostly round:
  the "a" reads neutral, an "ee" wide, an "oo" round, for a low and a high voice;
- where nobody speaks the width is neutral (0.5), whatever sound is there;
- on a narration cut tight (syllables back to back, no pause, the dips and clicks of real speech) the mouth never
  jumps: from one frame to the next its opening changes by a quarter at most, in steps of a quarter; it never shuts
  for a single frame between two open ones; a picture mascot's drawn talk frame never flashes for one frame; and it
  still follows the syllables (it opens fully on the loud ones,
  moves with the voice's loudness, a frame early);
- the mouth opens one frame before the sound and shuts one frame before the sound stops (it starts to close earlier,
  a quarter a frame), also where the plan's own speaking spans start and end with the sound;
- a track with no pauses still has its noise floor measured, on its quietest short moments, and the gate follows it;
  digital silence (an edit's own gap) is not the room's noise;
- a mouth.json measured by an older version (one axis; levels of a third) is stale: stage asks to measure it again;
- the per-frame plan carries the width; the kit reads a plan from before as neutral width;
- the kit's mouthPath keeps the pose's expression while the mouth speaks: the corners stay at its height (and where it
  put them at a neutral width), the upper lip keeps its curve, a wide mouth is wider and flatter than a round one.

These signals are stand-ins (a few partials at the formants of two vowels; speechlike.py: syllables of six vowels
and three kinds of consonant, cut tight), not a voice: the thresholds are checked on real recordings by hand (the
CHANGELOG has the numbers), which the tests cannot do.
"""
import json
import subprocess

import pytest

from conftest import ffmpeg, needs_ffmpeg, run_script, write_json
from speechlike import dense_speech
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
    assert got["ee"] >= 0.5 >= got["oo"], got
    assert 0.25 <= got["oo"] and got["ee"] <= 0.75, got  # near neutral, not stretched to either end


@pytest.mark.parametrize("shift_db", [-20, -10, 0, 10])
def test_a_voice_with_quieter_or_louder_highs_still_gets_a_wide_ee_and_a_round_oo(shift_db):
    # a real voice's highs sit lower or higher overall than the stand-ins' (another voice, another microphone): the
    # scale follows the recording, not a fixed level (the tilts of the stand-in "ee" and "oo", moved by shift_db)
    import mascot as M
    tilts = [2.7 + shift_db] * 20 + [None] * 5 + [-15.1 + shift_db] * 20
    w = M.widths(tilts, len(tilts))
    assert w[10] == 1.0 and w[35] == 0.0 and w[22] == 0.5, (w[10], w[35], w[22])


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


def tight_cut(project, name, **kw):
    """A tight cut of dense speech (speechlike.py) with its words in captions.json, measured: (mouth.json, info)."""
    e = project / "edit" / name
    info = dense_speech(e / "voice.wav", **kw)
    write_json(e / "captions.json", {"words": [{"text": "w", "start": a, "end": b} for a, b in info["words"]]})
    return mouth(project, e), info


def corr(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5


VOICES = pytest.mark.parametrize("f0,scale,seed", [(115, 1.0, 7), (215, 1.17, 11)], ids=["low voice", "high voice"])


@needs_ffmpeg
@VOICES
def test_on_a_tight_cut_the_mouth_steps_by_quarters_and_never_jumps(project, f0, scale, seed):
    m, info = tight_cut(project, "tight", f0=f0, scale=scale, seed=seed)
    o = m["open"]
    assert set(o) <= {0.0, 0.25, 0.5, 0.75, 1.0}, sorted(set(o))
    jumps = [(f, o[f - 1], o[f]) for f in range(1, len(o)) if abs(o[f] - o[f - 1]) > 0.25 + 1e-9]
    assert not jumps, jumps[:10]


@needs_ffmpeg
@VOICES
def test_on_a_tight_cut_the_mouth_never_shuts_for_a_single_frame(project, f0, scale, seed):
    m, info = tight_cut(project, "tight", f0=f0, scale=scale, seed=seed)
    o = m["open"]
    blinks = [f for f in range(1, len(o) - 1) if o[f] == 0 and o[f - 1] > 0 and o[f + 1] > 0]
    assert not blinks, blinks


@needs_ffmpeg
@VOICES
def test_on_a_tight_cut_a_picture_mascots_talk_frame_never_flashes_for_one_frame(project, f0, scale, seed):
    import re
    m, info = tight_cut(project, "tight", f0=f0, scale=scale, seed=seed)
    # the atlas shows its drawn talk frame from OPEN_FRAME: no frame alone on either side of it
    at = float(re.search(r"const OPEN_FRAME = ([0-9.]+)", (KIT / "kit" / "mascot" / "AtlasMascot.tsx")
                         .read_text(encoding="utf-8")).group(1))
    talk = [x >= at for x in m["open"]]
    flashes = [f for f in range(1, len(talk) - 1) if talk[f - 1] == talk[f + 1] != talk[f]]
    assert not flashes, flashes


@needs_ffmpeg
@VOICES
def test_on_a_tight_cut_the_mouth_still_follows_the_syllables(project, f0, scale, seed):
    m, info = tight_cut(project, "tight", f0=f0, scale=scale, seed=seed)
    o, env = m["open"], info["env"]
    n = min(len(o), len(env)) - 4
    # the mouth against the voice's own loudness, the voice moved by s frames: the best match is one frame early
    by_lag = {s: corr([o[f] for f in range(4, n)], [env[f + s] for f in range(4, n)]) for s in range(-3, 4)}
    best = max(by_lag, key=by_lag.get)
    assert best == 1 and by_lag[1] >= 0.8, by_lag
    # it opens fully on the loud syllables and uses at least three levels between (with no pause it need not shut)
    assert max(o) == 1.0 and len({x for x in o if 0 < x < 1}) >= 3, sorted(set(o))


@needs_ffmpeg
@VOICES
def test_ordinary_speech_is_not_mostly_round(project, f0, scale, seed):
    m, info = tight_cut(project, "mix", f0=f0, scale=scale, seed=seed)
    fps, o, w = m["fps"], m["open"], m["wide"]
    by_vowel = {}
    for a, b, v, (va, vb) in info["syllables"]:
        # the vowel's own frames, shown a frame early, its first and last two frames left out (the shape moves there)
        fr = [f - 1 for f in range(int(va * fps) + 2, int(vb * fps) - 1) if 0 < f < len(w) and o[f - 1] >= 0.5]
        by_vowel.setdefault(v, []).extend(w[f] for f in fr)
    shown = [x for v in by_vowel.values() for x in v]
    round_share = sum(1 for x in shown if x < 0.5) / len(shown)
    assert round_share <= 0.4, round_share
    assert median(by_vowel["a"]) == 0.5, sorted(by_vowel["a"])
    # the front vowels never read rounder than the back ones (how far apart they read depends on the voice: the bands
    # measure a real voice's vowels only roughly)
    # (equal is allowed: a width stuck at neutral passes here, test_ee_is_wide_and_oo_is_round_... catches that one)
    front = by_vowel.get("i", []) + by_vowel.get("e", [])
    back = by_vowel.get("u", []) + by_vowel.get("o", [])
    assert median(front) >= median(back), (sorted(front), sorted(back))


@needs_ffmpeg
@pytest.mark.parametrize("noise_db", [-55, -42])
def test_a_track_with_no_pauses_has_its_noise_floor_measured(project, noise_db):
    m, info = tight_cut(project, f"floor{-noise_db}", noise_db=noise_db)
    assert m.get("floor_from") == "short windows" and m["floor_db"] is not None, (m.get("floor_from"), m["floor_db"])
    assert abs(m["floor_db"] - noise_db) <= 3, m["floor_db"]
    assert m["gate_db"] == max(-50.0, round(m["floor_db"] + 10, 1)), (m["floor_db"], m["gate_db"])


@pytest.mark.parametrize("words", [None, [(0.0, 0.4), (0.4, 0.8), (0.8, 1.2)]], ids=["no words", "words, no pause"])
def test_digital_silence_reads_as_silence_and_does_not_gate_the_voice_out(words):
    import math
    from array import array
    import mascot as M
    sr, fps = 16000, 30
    # a generated voice with digital zeros between its syllables (and no room at all): the quietest moments are those
    # zeros, not the voice, so the gate stays at the absolute floor and the voice opens the mouth
    a = array("h", (int(9000 * math.sin(2 * math.pi * 200 * i / sr)) if i % 6400 < 4800 else 0
                    for i in range(int(1.2 * sr))))  # 0.3 s of voice, 0.1 s of zeros
    opens, _, info = M.envelope(a, sr, fps, words)
    assert info["gate_db"] == -50.0 and (info["floor_db"] is None or info["floor_db"] <= -100), info
    assert max(opens) == 1.0, opens


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
    # version 2 had the width but levels of a third (they jumped); version 1 had no width
    write_json(e / "mouth.json", {**m, "version": 2})
    assert "older" in (vm.load_mouth(e)[1] or ""), vm.load_mouth(e)[1]
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


def test_the_plans_speaking_span_keeps_the_frame_the_mouth_opens_early():
    import mascot_plan as vm
    geo = {"box": (400, 520), "anchor": (200, 170), "poses": ["neutral"], "symmetric": False}
    # the sound in [1, 2) s: mouth.json opens on frame 29 and shuts after frame 58
    opens = [0.0] * 29 + [0.667] * 30 + [0.0] * 31
    m = {"track": [], "from": 0.0, "to": 3.0, "facing": 1, "speaks": [[1.0, 2.0]]}
    plan = {"id": "s", "duration": 3.0, "inserts": []}
    fr = vm.frames_of(m, plan, {"brand_tone": {"mascot": "calm"}}, geo, opens, 30, None, [0.5] * 90)
    at = lambda f: [x for x in fr if x["f"] <= f][-1]
    assert [at(f)["open"] > 0 for f in (28, 29, 58, 59)] == [False, True, True, False]


@pytest.mark.parametrize("span,first,last", [((1.01, 2.01), 29, 59), ((1.0, 4.4), 29, 130)])
def test_a_speaking_span_off_the_frame_grid_keeps_the_lead_and_ends_on_its_frame(span, first, last):
    # mouth.json moves the mouth a frame early; a span the plan names in seconds (not on the 1/30 s grid, or one whose
    # end is not a sum of whole frames in floating point) gates the same frames the sound would
    import mascot_plan as vm
    geo = {"box": (400, 520), "anchor": (200, 170), "poses": ["neutral"], "symmetric": False}
    m = {"track": [], "from": 0.0, "to": 5.0, "facing": 1, "speaks": [list(span)]}
    plan = {"id": "g", "duration": 5.0, "inserts": []}
    fr = vm.frames_of(m, plan, {"brand_tone": {"mascot": "calm"}}, geo, [0.667] * 150, 30, None, [0.5] * 150)
    at = lambda f: [x for x in fr if x["f"] <= f][-1]
    talking = [f for f in range(150) if at(f)["open"] > 0]
    assert (talking[0], talking[-1]) == (first, last), (talking[0], talking[-1])
    assert talking == list(range(first, last + 1))


def test_a_speaking_span_that_cuts_into_speech_does_not_make_the_mouth_jump():
    # the plan's own spans start and end inside a loud stretch (and leave one frame out between two of them): the
    # mouth still opens and closes a quarter a frame there
    import mascot_plan as vm
    geo = {"box": (400, 520), "anchor": (200, 170), "poses": ["neutral"], "symmetric": False}
    m = {"track": [], "from": 0.0, "to": 2.0, "facing": 1, "speaks": [[0.2, 0.4], [13 / 30, 0.8]]}
    plan = {"id": "c", "duration": 2.0, "inserts": []}
    fr = vm.frames_of(m, plan, {"brand_tone": {"mascot": "calm"}}, geo, [1.0] * 60, 30, None, [0.5] * 60)
    o = [[x for x in fr if x["f"] <= f][-1]["open"] for f in range(60)]
    assert all(abs(o[f] - o[f - 1]) <= 0.25 + 1e-9 for f in range(1, 60)), o
    assert max(o) == 1.0 and o[30] == 0, o  # it still opens fully inside a span, and is shut after the last one


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
