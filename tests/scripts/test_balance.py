"""balance.py: white balance measured on the graded still: a warm cast in the source or in the LUT is neutralized
before the LUT, a neutral source is left alone, --write keeps the rest of cut.json."""
import json

from conftest import ffmpeg, needs_ffmpeg, run_script, write_json

TOL = 2.0  # balance.py: near-gray |B - R| and |G - (R+B)/2| that read as neutral

# a scene: a skin-like field (not near-gray: it keeps the whole frame warm) with a gray card in the middle
SKIN, CARD = "0xB07858", "0x8C8C8C"


def scene(path, tint=None, dur=2.0):
    """A 360x640 video: the skin field, the gray card, optionally a tint over everything (the camera's cast)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    chain = "[0:v][1:v]overlay=100:180" + (f",{tint}" if tint else "") + ",format=yuv420p[v]"
    ffmpeg("-f", "lavfi", "-i", f"color=c={SKIN}:s=360x640:r=30:d={dur}", "-f", "lavfi", "-i", f"color=c={CARD}:s=160x280:r=30:d={dur}",
           "-filter_complex", chain, "-map", "[v]", "-c:v", "libx264", "-crf", "12", path)
    return path


def setup(project, tint=None, look=None, **extra):
    scene(project / "IMG_5000.MOV", tint)
    cut = {"fps": 30, "sources": {"main": {"file": "IMG_5000.MOV"}},
           "ranges": [{"start": 0.2, "end": 0.9, "beat": "one"}, {"start": 1.1, "end": 1.8, "beat": "two"}], **extra}
    if look is not None:
        cut["look"] = look
    write_json(project / "edit" / "5000" / "cut.json", cut)
    return project / "edit" / "5000"


def balance(project, *args):
    return json.loads(run_script("balance.py", "edit/5000", "--frames", "3", "--json", *args, cwd=project).stdout)


def row(doc, label):
    return next(r for r in doc["rows"] if r["label"] == label)


@needs_ffmpeg
def test_a_warm_source_is_balanced_on_its_grays(project):
    setup(project, tint="colorchannelmixer=rr=1.07:bb=0.93")
    doc = balance(project)
    before = row(doc, "no balance fix")
    assert before["cast"][0] < -15  # the card reads yellow: B - R ~ -19
    after = row(doc, "suggested")
    assert all(abs(x) <= TOL for x in after["cast"]) and doc["neutral"]
    rr, gg, bb = doc["gains"]
    assert rr < 0.97 and bb > 1.03 and gg == 1.0  # warm: red down, blue up, green untouched
    assert doc["suggested"] == f"colorchannelmixer=rr={rr:.2f}:bb={bb:.2f}"
    assert after["rb"] < before["rb"] and after["gray"] and before["share"] > 0.15


@needs_ffmpeg
def test_a_warming_lut_is_compensated_before_it(project):
    # the source is neutral, the LUT pulls blue down (the real case): the fix goes in front of the LUT
    ffmpeg("-f", "lavfi", "-i", "haldclutsrc=8", "-vf", "colorchannelmixer=rr=1.05:bb=0.9", "-frames:v", "1",
           project / "warm-hald.png")
    setup(project, look={"lut": "warm-hald.png", "lut_mix": 0.6, "grade": "eq=contrast=1.05"})
    doc = balance(project)
    assert row(doc, "no balance fix")["cast"][0] < -5  # the card reads yellow through the LUT: B - R ~ -7
    assert all(abs(x) <= TOL for x in row(doc, "suggested")["cast"])
    assert doc["gains"][0] <= 1.0 < doc["gains"][2]


@needs_ffmpeg
def test_a_neutral_source_gets_no_correction(project):
    setup(project)
    r = run_script("balance.py", "edit/5000", "--frames", "3", cwd=project)
    assert "no balance fix needed" in r.stdout and 'suggested: no "correct"' in r.stdout
    doc = balance(project)
    assert doc["gains"] == [1.0, 1.0, 1.0] and doc["suggested"] == "" and doc["neutral"]


@needs_ffmpeg
def test_write_replaces_only_the_gains_and_keeps_the_rest(project):
    # an old balance fix and an exposure fix: the old gains are replaced, the exposure stays after the new ones
    e = setup(project, tint="colorchannelmixer=rr=1.07:bb=0.93",
              look={"correct": "colorchannelmixer=rr=0.99,eq=brightness=0.01", "lut_mix": 0.6, "grade": "eq=contrast=1.05"},
              fix={"recruter": "recruiter"})
    doc = balance(project, "--write")
    assert doc["written"] and row(doc, "current")["correct"] == "colorchannelmixer=rr=0.99,eq=brightness=0.01"
    cut = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    assert cut["look"]["correct"] == doc["suggested"] and doc["suggested"].endswith(",eq=brightness=0.01")
    assert cut["look"]["correct"].startswith("colorchannelmixer=rr=0.9")
    assert cut["look"]["lut_mix"] == 0.6 and cut["look"]["grade"] == "eq=contrast=1.05"
    assert cut["fix"] == {"recruter": "recruiter"} and len(cut["ranges"]) == 2
    # measured again with the written fix: the grays are neutral and there is nothing more to write
    again = balance(project, "--write")
    assert all(abs(x) <= TOL for x in row(again, "current")["cast"])
    assert not again["written"] and again["suggested"] == cut["look"]["correct"]


@needs_ffmpeg
def test_no_suggestion_without_gray_pixels(project):
    e = setup(project)
    scene(project / "IMG_5000.MOV", tint="colorchannelmixer=rr=1.0:gg=0.6:bb=0.3")  # nothing near-gray is left
    doc = balance(project, "--write")
    assert doc["suggested"] is None and doc["gains"] is None and not doc["written"]
    assert "look" not in json.loads((e / "cut.json").read_text(encoding="utf-8"))


def test_a_candidate_with_too_few_grays_is_not_neutral():
    # Codex review: the near-gray share was checked only before the correction; a candidate that pushes almost
    # all near-gray pixels out of the set read "neutral" on the random rest and could be written
    import balance
    m = {"mean": [120, 118, 110], "rb": 1.09, "y": 118, "gray": [150.0, 150.5, 151.0], "share": 0.001}
    assert not balance.enough(m) and not balance.ok(m)
    assert balance.score((1.04, 1.0, 1.02), m, 118, (0.2, 1e4, 0.2)) >= 2 * balance.BIG
    m["share"] = 0.05
    assert balance.ok(m)


@needs_ffmpeg
def test_a_gain_at_the_limit_is_flagged(project):
    # T1: bb landed on 1.12, the top of the search, with R/B still 1.21: the grays read neutral, but the fix did all it
    # may, and that is worth a look by eye (mixed light, a strong LUT)
    setup(project, tint="colorchannelmixer=bb=0.86")  # blue down: the card still near-gray, the fix wants bb ~1.16
    r = run_script("balance.py", "edit/5000", "--frames", "3", cwd=project)
    assert "bb 1.12 is at the limit of the search" in r.stderr, r.stdout + r.stderr
    assert "bb 1.12" in balance(project)["at_limit"]


def test_a_candidate_must_keep_most_of_the_near_gray_set():
    # T2: at rr 0.90 the blue-lit white T-shirt left the near-gray set (11% -> 4%) and the colder picture "won" on the
    # rest; a candidate now keeps at least KEEP of the uncorrected share
    import balance
    m = {"mean": [77.0, 112.4, 126.4], "rb": 0.61, "y": 105, "gray": [77.9, 82.4, 82.6], "share": 0.04}
    assert balance.enough(m) and not balance.enough(m, share0=0.11)
    assert balance.score((0.90, 1.0, 1.04), m, 104, (0.2, 1e4, 0.2), share0=0.11) >= 2 * balance.BIG
    m["share"] = 0.08  # 73% of 11%: still the same kind of measurement
    assert balance.enough(m, share0=0.11)


def test_a_suggestion_that_deepens_the_cast_is_refused():
    import balance
    base = {"rb": 0.72, "gray": [105.8, 114.7, 113.9]}  # T2: sky and sea through the windows, the grays blue
    assert "cooler" in balance.wrong_way(base, {"rb": 0.61, "gray": [77.9, 82.4, 82.6]})
    assert balance.wrong_way(base, {"rb": 0.86, "gray": [129.4, 140.6, 142.4]}) is None  # warming: fine
    # the balcony case: warm grays, the fix cools the frame toward 1.15 (a skin frame is warm when right)
    warm = {"rb": 1.27, "gray": [182.9, 182.0, 176.7]}
    assert balance.wrong_way(warm, {"rb": 1.15, "gray": [156.3, 156.5, 158.1]}) is None
    assert "warmer" in balance.wrong_way(warm, {"rb": 1.35, "gray": [190, 180, 165]})
    # a close-up under cool light: the frame mean is above 1 (skin), the grays blue: warming it further is right
    skin = {"rb": 1.10, "gray": [150, 155, 160]}
    assert balance.wrong_way(skin, {"rb": 1.18, "gray": [155, 155, 155]}) is None


def test_ref_parses_the_source_and_rounds_the_box():
    import balance
    import pytest
    c = {"sources": {"front": {"scale": "scale=1080:1920", "info": {"dur": 100}},
                     "side": {"scale": "scale=1080:1920", "info": {"dur": 100}}},
         "ranges": [{"source": "front", "start": 0, "end": 10}, {"source": "side", "start": 5, "end": 20}]}
    assert balance.parse_ref("12,820,1050,90,110", c) == {"source": "side", "t": 12.0, "box": (820, 1050, 90, 110)}
    assert balance.parse_ref("front:7,11,13,21,21", c)["box"] == (10, 12, 20, 20)  # even: 2x2 chroma inside the patch
    with pytest.raises(SystemExit, match="several sources"):
        balance.parse_ref("7,10,10,20,20", c)  # 7 s is kept from both angles: which one?
    with pytest.raises(SystemExit, match="inside the 1080x1920 frame"):
        balance.parse_ref("front:7,1000,1800,200,200", c)
    with pytest.raises(SystemExit, match="no source 'back'"):
        balance.parse_ref("back:7,10,10,20,20", c)


SKY, SHIRT = "0x5A8CC8", "0xA2AAB8"  # a window full of sky; a white T-shirt in its blue light


def window_scene(path, dur=2.0):
    """A 360x640 video: sky over the top half, the skin field below, a blue-lit white T-shirt card."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-f", "lavfi", "-i", f"color=c={SKIN}:s=360x640:r=30:d={dur}",
           "-f", "lavfi", "-i", f"color=c={SKY}:s=360x320:r=30:d={dur}",
           "-f", "lavfi", "-i", f"color=c={SHIRT}:s=120x160:r=30:d={dur}",
           "-filter_complex", "[0:v][1:v]overlay=0:0[a];[a][2:v]overlay=120:400,format=yuv420p[v]",
           "-map", "[v]", "-c:v", "libx264", "-crf", "12", path)
    return path


@needs_ffmpeg
def test_ref_neutralizes_the_patch_and_writes(project):
    # T2: panoramic windows, the white T-shirt read blue; by the T-shirt the fix warms (rr up, bb down), as the
    # correction made by hand did (rr 1.08 gg 0.97 bb 0.90)
    e = setup(project, look={"lut_mix": 0.6})
    window_scene(project / "IMG_5000.MOV")
    # the source is 360x640: cut.py scales it to 1080x1920, so the T-shirt card is at x 360..720, y 1200..1680
    doc = balance(project, "--ref", "0.5,420,1260,240,360", "--write")
    assert doc["mode"] == "ref" and doc["refs"][0]["box"] == [420, 1260, 240, 360]
    before, after = row(doc, "no balance fix")["patch"], row(doc, "suggested")["patch"]
    assert before["cast"][0] > 15  # B - R of the T-shirt: blue
    assert all(abs(x) <= TOL for x in after["cast"]) and doc["neutral"]
    rr, gg, bb = doc["gains"]
    assert rr > 1.0 > bb
    assert doc["written"]
    cut = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    assert cut["look"]["correct"] == doc["suggested"] and cut["look"]["lut_mix"] == 0.6


@needs_ffmpeg
def test_the_automatic_mode_never_cools_a_cool_picture(project):
    # the same window scene in the automatic mode: it may warm or refuse, never suggest a bluer picture
    e = setup(project)
    window_scene(project / "IMG_5000.MOV")
    doc = balance(project, "--write")
    base = row(doc, "no balance fix")
    assert base["rb"] < 1
    if doc["suggested"] is None:
        assert doc["refused"] and not doc["written"] and "look" not in json.loads((e / "cut.json").read_text("utf-8"))
    else:
        assert row(doc, "suggested")["rb"] >= base["rb"]


@needs_ffmpeg
def test_grays_off_neutral_that_no_gain_improves_are_not_called_neutral(project, monkeypatch, capsys):
    # T4: a cool frame with sky through the windows: no gain the search tried made the grays better, so the best gains
    # were none; balance.py warned "even the best gains leave the grays off neutral" and then printed "no balance fix
    # needed: the grays of the graded video are already neutral", and "next: --write" with nothing to write
    import sys
    import balance
    e = setup(project, look={"correct": "colorchannelmixer=rr=1.07:gg=0.99:bb=0.93"})
    base = {"mean": [109.5, 123.1, 130.6], "rb": 0.84, "y": 120.0, "gray": [138.2, 154.5, 161.2], "share": 0.115}
    one = (1.0, 1.0, 1.0)
    monkeypatch.setattr(balance, "make_still", lambda c, times, tmp: tmp / "still.png")
    monkeypatch.setattr(balance, "balance", lambda c, still: ("", base, None, one, {one: base}))
    monkeypatch.setattr(balance, "comparison", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["balance.py", "edit/5000", "--frames", "3", "--write"])
    balance.main()
    out, err = capsys.readouterr()
    assert "already neutral" not in out and "next:" not in out
    assert "not neutral, and the search found no gain" in err and "B-R +23.0" in err and "--ref" in err
    assert "even the best gains" not in err  # said once
    assert "not written" in out
    cut = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    assert cut["look"]["correct"] == "colorchannelmixer=rr=1.07:gg=0.99:bb=0.93"  # --write left the hand correction


@needs_ffmpeg
def test_still_is_the_frame_a_ref_box_is_measured_in(project):
    # review: the docs said to find the --ref box on a frame grabbed from the source (360x640 here), while the box is
    # read in the frame as cut.py scales it (1080x1920): a box measured there landed on another object
    from PIL import Image
    e = setup(project)
    r = run_script("balance.py", "edit/5000", "--still", "0.5", cwd=project)
    f = e / "verify" / "still-main-0.50.png"
    assert f.exists() and "1080x1920" in r.stdout
    with Image.open(f) as im:
        assert im.size == (1080, 1920)


def test_one_step_on_neutral_grays_is_no_fix(monkeypatch):
    # CI on macOS: a neutral source got bb 1.01 (the mild pull of the warm frame's R/B within the tolerance), while
    # Windows measured that step moving R/B the wrong way: one step on grays already neutral is below what the 8-bit
    # chain measures, so no fix. A model where that step is measured "right" (as on macOS) must still give none
    import re
    import balance

    def gains(correct):
        g = dict(re.findall(r"(rr|gg|bb)=([\d.]+)", correct or ""))
        return [float(g.get(k, 1)) for k in ("rr", "gg", "bb")]

    def stats(correct):
        rr, gg, bb = gains(correct)
        return {"gray": [137.1 * rr, 137.0 * gg, 136.9 * bb], "share": 0.19, "rb": 1.72 * rr / bb, "y": 129.0,
                "mean": [165.0 * rr, 121.7 * gg, 96.0 * bb]}
    monkeypatch.setattr(balance, "graded", lambda c, still, correct, png=None, half=True: correct)
    monkeypatch.setattr(balance, "stats", stats)
    *_, best, seen = balance.balance({"correct": ""}, None)
    assert best == (1.0, 1.0, 1.0)
    assert any(g != (1.0, 1.0, 1.0) and balance.score(g, m, 129.0, (balance.SIZE, balance.FIXED, balance.SIZE), 0.19)
               < balance.score((1.0, 1.0, 1.0), seen[(1.0, 1.0, 1.0)], 129.0,
                               (balance.SIZE, balance.FIXED, balance.SIZE), 0.19) for g, m in seen.items())  # the pull
