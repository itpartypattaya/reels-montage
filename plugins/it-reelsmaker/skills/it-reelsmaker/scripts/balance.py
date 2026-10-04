# -*- coding: utf-8 -*-
"""White balance measured, not judged by eye: the channel gains for look.correct (before the LUT) that make the grays
of the GRADED video neutral.

    python scripts/balance.py edit/<id> [--frames 6] [--write] [--json]
    python scripts/balance.py edit/<id> --ref [KEY:]SECOND,X,Y,W,H [--ref ...] [--write]
    python scripts/balance.py edit/<id> --still [KEY:]SECOND        (the frame to find a --ref box on)

Why the graded result and not the source: a LUT shifts the balance of whatever goes into it, and on a warm face the
shift is easy to miss. Real case: a 720p phone video on an overcast balcony, brand LUT at 60%: the LUT pulled blue
down and the video read yellow (mean R/B 1.27, near-gray pixels R 183 G 180 B 177). A correction before the LUT,
colorchannelmixer rr 0.96 bb 1.05, gave R/B 1.15 and natural skin, the white wall neutral; bb 1.08 already turned
the picture cool and magenta. On the same video this script suggests rr 0.97 bb 1.06 (6 frames): R/B 1.15.

Automatic mode (how it works; seconds: everything runs on one small still, not on the video):
  • N frames spread evenly over the kept ranges of cut.json, each scaled the way cut.py scales its source, then to
    360 px wide, side by side in one still;
  • the still goes through the same chain as the rough cut (cut.py: correction, LUT at lut_mix, grade) with a
    candidate colorchannelmixer at the front of look.correct; other filters already there (exposure, a green-cast
    fix) stay after it, and a previous colorchannelmixer with only rr/gg/bb is replaced;
  • measured on the graded still at half size: mean RGB, mean R/B and the near-gray pixels of that candidate's result
    (60 < max < 235 and max − min < 0.18·max: walls, overcast sky, white and gray clothes, paper);
  • the goal: near-gray neutral, |B − R| ≤ 2 and |G − (R+B)/2| ≤ 2 levels of 255; within that tolerance a mild pull
    of the overall R/B toward 1 (skin and warm surfaces keep the whole frame warmer than its grays), an unchanged
    brightness and the smallest gains decide; gg moves only when a green or magenta cast is left after rr and bb;
    every gain within 0.90..1.12, in steps of 0.01 (a gain that ends on that edge is reported: the cast may need more
    than a balance fix);
  • a candidate counts only while its measurement stays the same kind of measurement: at least 70% of the near-gray
    share of the picture with no fix (and at least 1% of the pixels). A correction moves pixels in and out of the
    near-gray set; one that pushes the dominant gray object out "wins" on a small random rest;
  • the direction is checked: a suggestion that makes the picture cooler while it already reads cool (mean R/B below
    1, or near-gray B > R), or warmer while its grays read warm, is refused, with a pointer to --ref;
  • two probe gains give a linear model and its answer is the start; then a search in steps of 0.01 on measured
    candidates (the near-gray set changes with every candidate, so the model alone is not trusted): about 10-20
    passes of the still. Grays already neutral and a best fix of one step: no fix (one step is within the noise of
    the 8-bit chain and differs between ffmpeg builds).
Real case for the share and direction checks: an interview at a laptop in front of panoramic windows (sky, sea,
glass: mean R/B 0.72, the white T-shirt the main near-gray object, 11% of the pixels). Without them the search
suggested rr 0.90 bb 1.04: the T-shirt turned so blue it left the near-gray set (11% -> 4%), the rest read "neutral",
and the picture got colder (R/B 0.61). A correction by the T-shirt by hand went the other way: rr 1.08 gg 0.97 bb 0.90.

Reference patch (--ref, the eyedropper): when the frame is dominated by colored light (sky or sea through windows,
neon, a colored wall, mixed daylight and lamps) its near-gray pixels are not a reliable reference; name an object
known to be white or gray instead: a white T-shirt or shirt, a white or gray wall, paper, a gray card, a white
laptop (not skin, not the sky, not a window, not a clipped highlight). --ref SECOND,X,Y,W,H: the source second and a
box in the frame as cut.py scales that source (1080x1920 for a vertical video); with several sources, KEY:SECOND
(the source key in cut.json) or a second inside a kept range of only one source. Several --ref are averaged, each
with the same weight (a shaded and a lit part of the same shirt is a good pair). The gains (rr, gg, bb) make the
patch's mean neutral after the full chain (LUT included) with its brightness kept. Find the box on the still that
--still [KEY:]SECOND writes (edit/<id>/verify/still-<key>-<second>.png, scaled as cut.py scales that source, its size
printed): a frame grabbed from the source itself is at the source's own size (720x1280 for a 720p phone video), and a
box measured on it lands on another object of the 1080x1920 frame.

Prints the measurements with no balance fix, with the current look.correct and with the suggestion (with --ref: the
patch numbers too), and the suggested "correct" string; writes edit/<id>/verify/balance.png (rows: the same frames
with no fix, current, suggested; the reference frames first, the patch marked; needs Pillow, otherwise numbers
only): look at the grays and the skin. --write puts the suggestion into cut.json -> look.correct (other keys kept);
then rebuild the rough cut with cut.py. Fewer than 1% near-gray pixels: no automatic suggestion, use --ref.
"""
import argparse, json, math, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cut import load_cut, lut_inputs, video_graph
from reels_common import edit_dir, editing_json, local_media_args, project_root, rel, utf8_stdio, warn

TILE_W = 360            # px: each frame's width in the measured still
SHEET_W = 1600          # px: the comparison image's width at most
LIMITS = (0.90, 1.12)   # gains beyond this are not a balance fix: the source needs another correction
TOL = 2.0               # near-gray |B − R| and |G − (R+B)/2| that read as neutral, levels of 255
GRAY_MIN = 0.01         # share of near-gray pixels below which the measurement means nothing
KEEP = 0.7              # a candidate keeps at least this part of the uncorrected near-gray share (see enough())
TURN = 0.01             # relative change of the mean R/B that counts as a move in the direction check
PROBE = 0.04            # gain step for the linear model: wide enough to average the noise of the near-gray set
MEAN_PULL = 0.08        # weight of the overall warmth, 100·ln(R/B), within the tolerance (see score())
BRIGHTNESS = 1.0        # weight of the brightness change, 100·ln(Y/Y0): a balance fix keeps the exposure
SIZE = 0.2              # weight of each gain's distance from 1 (in %): the smallest correction that does the job
GG_SIZE = 0.6           # gg costs more: it moves only for a green or magenta cast
FIXED = 1e4             # the weight that keeps a gain at 1
MOVES = 12              # steps of the measured search
STEP = 0.01             # the search's step: one step on grays already neutral is measurement noise (see balance())
BIG = 1e6               # the score of a candidate whose grays are off neutral: worse than any neutral one
REF_HINT = ("balance on a known white or gray object instead: balance.py {edit} --ref SECOND,X,Y,W,H (a white "
            "T-shirt or shirt, a white or gray wall, paper, a gray card; not skin, the sky, a window or a clipped "
            "highlight), or by eye on stills by the whites and the skin")


def ffmpeg(args, capture=False):
    r = subprocess.run(local_media_args(["ffmpeg", "-v", "error", "-y", *map(str, args)]), capture_output=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + r.stderr.decode("utf-8", "replace")[-1500:])
    return r.stdout if capture else None


def split_filters(chain):
    """A filter chain split at its top-level commas (a quoted argument may hold a comma)."""
    out, cur, quote, esc = [], "", False, False
    for ch in chain or "":
        if esc:
            cur, esc = cur + ch, False
        elif ch == "\\":
            cur, esc = cur + ch, True
        elif ch == "'":
            cur, quote = cur + ch, not quote
        elif ch == "," and not quote:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    return [f for f in out if f]


def is_gain_mixer(f):
    """colorchannelmixer with only rr/gg/bb set: a balance fix (this script's own, or one made by hand)."""
    name, _, args = f.partition("=")
    keys = [a.partition("=")[0].strip() for a in args.split(":") if a.strip()]  # a positional value is not a key
    return name.strip() == "colorchannelmixer" and bool(keys) and all(k in ("rr", "gg", "bb") for k in keys)


def mixer(g):
    """The colorchannelmixer for gains (rr, gg, bb); empty when all are 1."""
    parts = [f"{k}={v:.2f}" for k, v in zip(("rr", "gg", "bb"), g) if abs(v - 1) > 1e-9]
    return "colorchannelmixer=" + ":".join(parts) if parts else ""


def correct_with(g, rest):
    return ",".join(filter(None, [mixer(g), rest]))


def frame_times(c, n):
    """n moments spread evenly over the kept ranges, in the video's order: [(source, source second)]."""
    total = sum(r["end"] - r["start"] for r in c["ranges"])
    out = []
    for k in range(n):
        pos = (k + 0.5) * total / n
        for r in c["ranges"]:
            d = r["end"] - r["start"]
            if pos <= d:
                out.append((r["source"], r["start"] + pos))
                break
            pos -= d
    return out


def frame_size(sv):
    """The frame size after cut.py's scaling of this source."""
    return (1080, 1920) if sv["scale"] else (sv["info"].get("w") or 1080, sv["info"].get("h") or 1920)


def ref_source(label, spec, key, sec, t, c):
    """The source key of a --ref or --still: KEY given, the only source, or the one whose kept range holds second t."""
    if key and key not in c["sources"]:
        sys.exit(f"{label} {spec!r}: no source {key!r} in cut.json (sources: {', '.join(c['sources'])})")
    if key:
        return key
    inside = sorted({r["source"] for r in c["ranges"] if r["start"] <= t <= r["end"]})
    if len(c["sources"]) == 1:
        return next(iter(c["sources"]))
    if len(inside) == 1:
        return inside[0]
    sys.exit(f"{label} {spec!r}: several sources; name one as KEY:{sec} (sources: {', '.join(c['sources'])})")


def write_still(c, spec, out_dir):
    """--still [KEY:]SECOND: the source frame at that second, scaled as cut.py scales it, as a PNG -> (path, w, h)."""
    key, _, sec = spec.strip().rpartition(":")
    try:
        t = float(sec)
    except ValueError:
        sys.exit(f"--still {spec!r}: expected [KEY:]SECOND")
    key = ref_source("--still", spec, key, sec, t, c)
    sv = c["sources"][key]
    if not 0 <= t <= float(sv["info"].get("dur") or 0):
        sys.exit(f"--still {spec!r}: second {t} is outside the source {key!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    f = out_dir / f"still-{key}-{t:.2f}.png"
    ffmpeg(["-ss", f"{t:.3f}", "-i", sv["path"], "-frames:v", "1", "-vf",
            ",".join(filter(None, [sv["scale"], "setsar=1"])), f])
    return (f, *frame_size(sv))


def parse_ref(spec, c):
    """--ref [KEY:]SECOND,X,Y,W,H -> {source, t, box}; the box rounded to even numbers (yuv420p keeps 2x2 chroma
    blocks inside the patch). Without KEY: the only source, or the one whose kept range holds that second."""
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 5:
        sys.exit(f"--ref {spec!r}: expected [KEY:]SECOND,X,Y,W,H")
    key, _, sec = parts[0].rpartition(":")
    try:
        t = float(sec)
        x, y, w, h = (int(round(float(v))) for v in parts[1:])
    except ValueError:
        sys.exit(f"--ref {spec!r}: SECOND, X, Y, W, H must be numbers")
    key = ref_source("--ref", spec, key, sec, t, c)
    sv = c["sources"][key]
    fw, fh = frame_size(sv)
    x, y = x - x % 2, y - y % 2
    w, h = w - w % 2, h - h % 2
    if w < 4 or h < 4 or x < 0 or y < 0 or x + w > fw or y + h > fh:
        sys.exit(f"--ref {spec!r}: the box must lie inside the {fw}x{fh} frame and be at least 4x4 px")
    if not 0 <= t <= float(sv["info"].get("dur") or 0):
        sys.exit(f"--ref {spec!r}: second {t} is outside the source {key!r}")
    return {"source": key, "t": t, "box": (x, y, w, h)}


def make_still(c, times, tmp):
    """The frames scaled as cut.py scales the source, then to TILE_W, side by side in one PNG."""
    files = []
    for k, (name, t) in enumerate(times):
        sv = c["sources"][name]
        vf = ",".join(filter(None, [sv["scale"], f"scale={TILE_W}:-2:flags=area", "setsar=1"]))
        f = tmp / f"frame{k}.png"
        ffmpeg(["-ss", f"{t:.3f}", "-i", sv["path"], "-frames:v", "1", "-vf", vf, f])
        files.append(f)
    still = tmp / "still.png"
    stack = "".join(f"[{k}:v]" for k in range(len(files))) + f"hstack=inputs={len(files)}" if len(files) > 1 else "null"
    ffmpeg([*sum((["-i", f] for f in files), []), "-filter_complex", stack, "-frames:v", "1", still])
    return still


def make_patches(c, refs, tmp):
    """The reference boxes cut from their frames at full size, side by side (padded to one height) in one PNG:
    the patch still and the column where each patch starts."""
    files, offsets, x0 = [], [], 0
    for k, r in enumerate(refs):
        sv = c["sources"][r["source"]]
        x, y, w, h = r["box"]
        f = tmp / f"patch{k}.png"
        vf = ",".join(filter(None, [sv["scale"], "setsar=1", f"crop={w}:{h}:{x}:{y}"]))
        ffmpeg(["-ss", f"{r['t']:.3f}", "-i", sv["path"], "-frames:v", "1", "-vf", vf, f])
        files.append(f)
        offsets.append(x0)
        x0 += w
    hmax = max(r["box"][3] for r in refs)
    pads = "".join(f"[{k}:v]pad={r['box'][2]}:{hmax}:0:0:black[p{k}];" for k, r in enumerate(refs))
    stack = pads + "".join(f"[p{k}]" for k in range(len(refs))) + (f"hstack=inputs={len(refs)}" if len(refs) > 1 else "null")
    still = tmp / "patches.png"
    ffmpeg([*sum((["-i", f] for f in files), []), "-filter_complex", stack, "-frames:v", "1", still])
    return still, offsets, x0


def graded(c, still, correct, png=None, half=True):
    """The still through cut.py's video chain with this correction: raw RGB (at half size unless half=False), or a
    PNG at full size."""
    cc = dict(c, correct=correct)
    graph = video_graph(cc, {"scale": ""}, 1.0)
    args = ["-i", still, *lut_inputs(cc), "-filter_complex"]
    if png:
        return ffmpeg([*args, graph, "-map", "[v]", "-frames:v", "1", png])
    graph += ";[v]" + ("scale=trunc(iw/4)*2:trunc(ih/4)*2:flags=area," if half else "") + "format=rgb24[m]"
    return ffmpeg([*args, graph, "-map", "[m]", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture=True)


def luma(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def stats(raw):
    """Mean RGB, R/B and luma of the graded still, and the mean RGB and share of its near-gray pixels."""
    n = len(raw) // 3
    mean = [sum(raw[k::3]) / n for k in range(3)]
    sr = sg = sb = cnt = 0
    for (r, g, b), k in Counter(zip(raw[0::3], raw[1::3], raw[2::3])).items():
        mx = max(r, g, b)
        if 60 < mx < 235 and mx - min(r, g, b) < 0.18 * mx:
            sr, sg, sb, cnt = sr + r * k, sg + g * k, sb + b * k, cnt + k
    return {"mean": mean, "rb": mean[0] / max(mean[2], 1e-6), "y": luma(mean),
            "gray": [sr / cnt, sg / cnt, sb / cnt] if cnt else None, "share": cnt / n}


def patch_stats(raw, refs, offsets, width):
    """Mean RGB of each reference patch in the graded patch still (a 2 px margin: a sharpening grade spreads the
    padding into the edge), their average (each patch the same weight) as "gray", and the share of clipped pixels."""
    rows = []
    for r, x0 in zip(refs, offsets):
        _, _, w, h = r["box"]
        m = min(2, w // 4, h // 4)
        s, n, clip = [0, 0, 0], 0, 0
        for yy in range(m, h - m):
            base = (yy * width + x0) * 3
            for xx in range(m, w - m):
                p = raw[base + xx * 3: base + xx * 3 + 3]
                s = [a + b for a, b in zip(s, p)]
                clip += max(p) >= 250
                n += 1
        rows.append({"rgb": [v / n for v in s], "clip": clip / n})
    gray = [sum(p["rgb"][k] for p in rows) / len(rows) for k in range(3)]
    return {"gray": gray, "y": luma(gray), "patches": rows, "clip": max(p["clip"] for p in rows), "share": 1.0}


def cast(m):
    """Near-gray B − R (blue/yellow) and G − (R+B)/2 (green/magenta), levels of 255: 0 = neutral."""
    r, g, b = m["gray"] or (0, 0, 0)
    return [b - r, g - (r + b) / 2]


def errors(m, y0):
    """What the solver drives to 0: the near-gray cast, the overall warmth 100·ln(R/B) and the brightness change
    100·ln(Y/Y0) against the picture with no fix."""
    return cast(m) + [100 * math.log(max(m["rb"], 1e-6)), 100 * math.log(max(m["y"], 1e-6) / max(y0, 1e-6))]


def enough(m, share0=0.0):
    """Enough near-gray pixels to mean anything, checked for every candidate: at least GRAY_MIN of the pixels and at
    least KEEP of the share with no fix (share0). A correction moves pixels in and out of the near-gray set; a
    candidate that pushes most of them out reads "neutral" on a random rest (T2: the blue-lit white T-shirt left the
    set at rr 0.90, 11% -> 4%, and the colder picture won)."""
    return m["gray"] is not None and m["share"] >= max(GRAY_MIN, KEEP * share0)


def ok(m, share0=0.0):
    return enough(m, share0) and all(abs(x) <= TOL for x in cast(m))


def weights(pull):
    return [1.0, 1.0, math.sqrt(pull), math.sqrt(BRIGHTNESS)]


def score(g, m, y0, sizes, share0=0.0):
    """Lower is better. Neutral grays (within TOL) beat everything else; among them the overall warmth, the
    brightness change and the size of the gains decide; without them, the smallest cast."""
    if not ok(m, share0):
        return BIG + sum(x * x for x in cast(m)) if enough(m, share0) else 2 * BIG
    e = [w * x for w, x in zip(weights(MEAN_PULL), errors(m, y0))]
    return sum(x * x for x in e) + sum((w * 100 * (x - 1)) ** 2 for w, x in zip(sizes, g) if w < FIXED)


def wrong_way(base, m):
    """Why a suggestion goes the wrong way, or None. A picture that already reads cool (mean R/B below 1: nothing
    in a person's frame but the light or a colored backdrop makes it blue; or its near-gray pixels blue) must not get
    cooler; one whose near-gray pixels read warm must not get warmer. A mean R/B above 1 alone is no cast: skin and
    warm surfaces keep a balanced frame warm (the balcony case: 1.15 when right)."""
    b_r = cast(base)[0] if base["gray"] else 0.0
    cool = base["rb"] < 1 or b_r > TOL
    warm = b_r < -TOL
    if cool and m["rb"] < base["rb"] * (1 - TURN):
        return f"it makes the picture cooler (mean R/B {base['rb']:.2f} -> {m['rb']:.2f}) while it already reads cool"
    if warm and m["rb"] > base["rb"] * (1 + TURN):
        return f"it makes the picture warmer (mean R/B {base['rb']:.2f} -> {m['rb']:.2f}) while its grays read warm"
    return None


def solve3(a, b):
    """a·x = b for a 3x3 system (Gaussian elimination with pivoting)."""
    m = [row[:] + [v] for row, v in zip(a, b)]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        if abs(m[i][i]) < 1e-12:
            return [0.0, 0.0, 0.0]
        for r in range(3):
            if r != i:
                f = m[r][i] / m[i][i]
                m[r] = [x - f * y for x, y in zip(m[r], m[i])]
    return [m[i][3] / m[i][i] for i in range(3)]


def clamp(g):
    return tuple(round(min(LIMITS[1], max(LIMITS[0], x)), 2) for x in g)


def model_step(g, m, y0, jac, sizes):
    """The gains that make the grays neutral on the linear model around the measured point g (the smallest such
    gains, the brightness kept), rounded to 0.01: where the measured search starts."""
    w = weights(0.0)
    e = [wi * x for wi, x in zip(w, errors(m, y0))]
    j = [[wi * x for x in row] for wi, row in zip(w, jac)]
    reg = [(s * 100) ** 2 for s in sizes]
    a = [[sum(row[r] * row[c] for row in j) + (reg[r] if r == c else 0) for c in range(3)] for r in range(3)]
    b = [-sum(row[r] * ek for row, ek in zip(j, e)) - reg[r] * (g[r] - 1) for r in range(3)]
    return clamp(x + dx for x, dx in zip(g, solve3(a, b)))


def balance(c, still):
    """Measure with no fix, probe, solve, search. Returns (the rest of look.correct, base, current or None, the best
    gains or None, {gains: measurement})."""
    rest = ",".join(f for f in split_filters(c["correct"]) if not is_gain_mixer(f))
    seen = {}

    def measure(g):
        if g not in seen:
            seen[g] = stats(graded(c, still, correct_with(g, rest)))
        return seen[g]

    one = (1.0, 1.0, 1.0)
    base = measure(one)
    current = stats(graded(c, still, c["correct"])) if c["correct"] != rest else None
    if base["share"] < GRAY_MIN:
        return rest, base, current, None, seen
    y0, share0 = base["y"], base["share"]
    e0 = errors(base, y0)
    jac = [[0.0] * 3 for _ in range(4)]

    def probe(k):
        m = measure(clamp(1 + PROBE if i == k else 1.0 for i in range(3)))
        if m["gray"]:
            for i, v in enumerate(errors(m, y0)):
                jac[i][k] = (v - e0[i]) / PROBE

    def search(g, axes, sizes):
        """Steps of 0.01 while a measured neighbor scores better: the near-gray set changes with every candidate,
        so the model only gives the start."""
        for _ in range(MOVES):
            near = [g] + [clamp(x + d if i == k else x for i, x in enumerate(g)) for k in axes for d in (-0.01, 0.01)]
            best = min(near, key=lambda h: score(h, measure(h), y0, sizes, share0))
            if best == g:
                break
            g = best
        return g

    # rr and bb first: a warm or cool cast; gg only when a green or magenta cast is left after them
    sizes = (SIZE, FIXED, SIZE)
    probe(0)
    probe(2)
    g = search(model_step(one, base, y0, jac, sizes), (0, 2), sizes)
    if not ok(seen[g], share0) and abs(cast(seen[g])[1]) > TOL:
        sizes = (SIZE, GG_SIZE, SIZE)
        probe(1)
        g = search(model_step(g, seen[g], y0, jac, sizes), (0, 1, 2), sizes)
    best = min(seen, key=lambda h: score(h, seen[h], y0, sizes, share0))
    # grays already neutral and a best fix of one step (0.01): below what the 8-bit chain measures, so no fix. CI on
    # macOS suggested bb 1.01 for a neutral source (the mild pull of a warm frame's R/B within the tolerance), while on
    # Windows the same step moved R/B the wrong way: the suggestion depended on the ffmpeg build, not on the picture
    if best != one and ok(base, share0) and all(abs(x - 1) <= STEP + 1e-9 for x in best):
        best = one
    return rest, base, current, best, seen


def balance_ref(c, patches, refs, offsets, width):
    """Gains (rr, gg, bb) that make the reference patches' mean neutral after the full chain, brightness kept:
    Newton steps on probed gains (the LUT bends the response), then steps of 0.01 on measured candidates.
    Returns (rest, base, current or None, best gains, {gains: patch measurement})."""
    rest = ",".join(f for f in split_filters(c["correct"]) if not is_gain_mixer(f))
    seen = {}

    def measure(g):
        if g not in seen:
            seen[g] = patch_stats(graded(c, patches, correct_with(g, rest), half=False), refs, offsets, width)
        return seen[g]

    one = (1.0, 1.0, 1.0)
    base = measure(one)
    current = patch_stats(graded(c, patches, c["correct"], half=False), refs, offsets, width) \
        if c["correct"] != rest else None
    y0 = base["y"]

    def err(m):
        return cast(m) + [100 * math.log(max(m["y"], 1e-6) / max(y0, 1e-6))]

    def cost(g):
        return sum(x * x for x in err(measure(g))) + 1e-3 * sum((100 * (x - 1)) ** 2 for x in g)

    g = one
    for _ in range(3):
        e = err(measure(g))
        if all(abs(x) <= TOL / 4 for x in e[:2]):
            break
        jac = [[0.0] * 3 for _ in range(3)]
        for k in range(3):
            d = PROBE if g[k] + PROBE <= LIMITS[1] else -PROBE
            h = tuple(x + d if i == k else x for i, x in enumerate(g))
            m = measure(h)  # not rounded: the probe is a measurement, not a candidate
            for i, v in enumerate(err(m)):
                jac[i][k] = (v - e[i]) / d
        nxt = clamp(x + dx for x, dx in zip(g, solve3(jac, [-x for x in e])))
        if nxt == g:
            break
        g = nxt
    for _ in range(MOVES):
        near = [g] + [clamp(x + d if i == k else x for i, x in enumerate(g)) for k in range(3) for d in (-0.01, 0.01)]
        best = min(near, key=cost)
        if best == g:
            break
        g = best
    return rest, base, current, g, seen


def row(label, m):
    e = cast(m)
    gray = " ".join(f"{v:5.1f}" for v in m["gray"]) + f"  {m['share']:4.0%}  {e[0]:+5.1f}  {e[1]:+5.1f}" \
        if m["gray"] else "  -"
    return f"  {label:<15}" + " ".join(f"{v:5.1f}" for v in m["mean"]) + f"  {m['rb']:4.2f}   {gray}"


def patch_row(label, p):
    e = cast(p)
    each = "  ".join(" ".join(f"{v:5.1f}" for v in q["rgb"]) for q in p["patches"])
    return f"  {label:<15}{each}   B-R {e[0]:+5.1f}  G-(R+B)/2 {e[1]:+5.1f}"


def comparison(c, still, rows, out, marks=()):
    """The graded frames, one row per correction, labeled with its numbers: what the numbers mean, for the eye.
    marks: (tile, (x, y, w, h) in the frame, frame width): the reference patches, outlined on every row."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        warn("Pillow is not installed for this Python: no comparison image, numbers only (pip install Pillow)")
        return None
    try:
        font = ImageFont.load_default(size=18)
    except TypeError:  # Pillow before 10.1: the small bitmap font
        font = ImageFont.load_default()
    ims = []
    for k, (label, correct, m, p) in enumerate(rows):
        f = Path(still).with_name(f"row{k}.png")
        graded(c, still, correct, png=f)
        with Image.open(f) as src:
            im = src.convert("RGB")
        d = ImageDraw.Draw(im)
        for tile, (x, y, w, h), fw in marks:
            s = TILE_W / fw
            box = (tile * TILE_W + x * s, y * s, tile * TILE_W + (x + w) * s, (y + h) * s)
            d.rectangle(box, outline=(255, 0, 255), width=3)
        if im.width > SHEET_W:  # small enough to open and to read in one look
            im = im.resize((SHEET_W, round(im.height * SHEET_W / im.width)), Image.LANCZOS)
        e = cast(m)
        text = f"{label}: R/B {m['rb']:.2f}" + (f", gray B-R {e[0]:+.1f}, G-(R+B)/2 {e[1]:+.1f}" if m["gray"] else "")
        if p:
            q = cast(p)
            text += f", patch B-R {q[0]:+.1f}, G-(R+B)/2 {q[1]:+.1f}"
        text += f"   {correct}" if correct else ""
        d = ImageDraw.Draw(im)
        box = d.textbbox((8, 6), text, font=font)
        d.rectangle((0, 0, box[2] + 8, box[3] + 6), fill=(0, 0, 0))
        d.text((8, 6), text, fill=(255, 255, 255), font=font)
        ims.append(im)
    sheet = Image.new("RGB", (max(i.width for i in ims), sum(i.height for i in ims)))
    y = 0
    for im in ims:
        sheet.paste(im, (0, y))
        y += im.height
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def as_json(label, correct, m, p=None):
    out = {"label": label, "correct": correct, "mean": [round(v, 1) for v in m["mean"]], "rb": round(m["rb"], 3),
           "gray": [round(v, 1) for v in m["gray"]] if m["gray"] else None, "share": round(m["share"], 3),
           "cast": [round(v, 2) for v in cast(m)] if m["gray"] else None}
    if p:
        out["patch"] = {"rgb": [round(v, 1) for v in p["gray"]], "cast": [round(v, 2) for v in cast(p)],
                        "patches": [[round(v, 1) for v in q["rgb"]] for q in p["patches"]]}
    return out


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", help="the video folder, edit/<id>, with cut.json")
    ap.add_argument("--frames", type=int, default=6, help="frames to measure, spread over the kept ranges (1..12, default 6)")
    ap.add_argument("--ref", action="append", default=[], metavar="[KEY:]SECOND,X,Y,W,H",
                    help="a white or gray object as the reference: source second and a box in the frame as cut.py "
                         "scales that source (1080x1920 for a vertical video); several allowed, averaged")
    ap.add_argument("--still", metavar="[KEY:]SECOND",
                    help="only write the frame at that source second, scaled as cut.py scales it, to find a --ref box on")
    ap.add_argument("--write", action="store_true", help="put the suggested correction into cut.json -> look.correct")
    ap.add_argument("--json", action="store_true", help="print the measurements and the suggestion as JSON")
    a = ap.parse_args()
    if not 1 <= a.frames <= 12:
        sys.exit("--frames must be 1..12")
    say = (lambda *x: None) if a.json else print
    project = project_root()
    e = edit_dir(a.edit, project)
    c = load_cut(e, project)
    if a.still:
        f, fw, fh = write_still(c, a.still, e / "verify")
        print(f"{rel(f, project)}: {fw}x{fh}, the frame a --ref box is measured in (X, Y, W, H in these pixels)")
        return
    refs = [parse_ref(s, c) for s in a.ref]
    spread = frame_times(c, a.frames)
    ref_times = list(dict.fromkeys((r["source"], r["t"]) for r in refs))
    times = ref_times + spread
    marks = [(ref_times.index((r["source"], r["t"])), r["box"], frame_size(c["sources"][r["source"]])[0]) for r in refs]
    hint = REF_HINT.format(edit=a.edit)
    look = ", ".join(filter(None, [
        f"LUT {Path(c['lut']).name} at {round(c['lut_mix'] * 100)}%" if c["lut"] else "no LUT",
        f"grade {c['grade']}" if c["grade"] else "", f"current correct {c['correct']}" if c["correct"] else ""]))
    say(f"balance: {len(spread)} frames over {len(c['ranges'])} ranges"
        + (f" + {len(ref_times)} reference frame(s), {len(refs)} patch(es)" if refs else "") + f"; {look}")
    refused = None
    with tempfile.TemporaryDirectory(prefix="balance-") as tmp:
        still = make_still(c, times, Path(tmp))
        if refs:
            patches, offsets, width = make_patches(c, refs, Path(tmp))
            rest, pbase, pcurrent, best, pseen = balance_ref(c, patches, refs, offsets, width)
            base = stats(graded(c, still, rest))
            current = stats(graded(c, still, c["correct"])) if c["correct"] != rest else None
            seen = {best: stats(graded(c, still, correct_with(best, rest)))}
            prow = {"no balance fix": pbase, "current": pcurrent, "suggested": pseen[best]}
        else:
            rest, base, current, best, seen = balance(c, still)
            prow = {}
            if best is not None and best != (1.0, 1.0, 1.0):
                refused = wrong_way(base, seen[best])
        rows = [("no balance fix", rest, base)] + ([("current", c["correct"], current)] if current else [])
        suggested = correct_with(best, rest) if best is not None else None
        if best is not None:
            rows.append(("suggested" if not refused else "refused", suggested, seen[best]))
        say(f"  {'':<15}mean R     G     B   R/B   near-gray R     G     B  share   B-R  G-(R+B)/2")
        for label, _, m in rows:
            say(row(label, m))
        if refs:
            say("  reference patch (mean R G B of each patch, then the cast of their average):")
            for label, _, _ in rows:
                say(patch_row(label, prow[label]))
        img = comparison(c, still, [(lb, cr, m, prow.get(lb)) for lb, cr, m in rows], e / "verify" / "balance.png",
                         marks)
    out = {"mode": "ref" if refs else "auto", "frames": [[n, round(t, 3)] for n, t in times],
           "rows": [as_json(lb, cr, m, prow.get(lb)) for lb, cr, m in rows], "suggested": None if refused else suggested,
           "gains": list(best) if best and not refused else None, "refused": refused,
           "neutral": bool(best and not refused and ok(prow["suggested"] if refs else seen[best],
                                                         0.0 if refs else base["share"])),
           "image": rel(img, project) if img else None, "written": False}
    if refs:
        out["refs"] = [{"source": r["source"], "t": r["t"], "box": list(r["box"])} for r in refs]
    if img:
        say(f"comparison: {out['image']} (rows top to bottom: {', '.join(r[0] for r in rows)}"
            + ("; the reference patches outlined" if refs else "") + ")")
    if best is None:
        say(f"no suggestion: {base['share']:.1%} of the pixels are near-gray (fewer than {GRAY_MIN:.0%}), nothing in "
            f"the frame is known to be gray; {hint}")
    elif refused:
        warn(f"refused: {mixer(best)}: {refused}; the frame is dominated by colored light (sky or sea through "
             f"windows, neon, a colored wall, mixed light) and its near-gray pixels are no reference; {hint}")
        say(f"no suggestion written; the refused gains are the last row of {out['image'] or 'the numbers above'}")
    else:
        final = prow["suggested"] if refs else seen[best]
        # T4: "even the best gains leave the grays off neutral" and then "no balance fix needed: the grays are already
        # neutral" for the same frame: the best gains were none because no gain the search tried made the grays
        # better (a warming probe pulled more sky into the near-gray set, a cooling one pushed most of it out), which
        # is not the same as neutral; say that once, write nothing, and point to the eyedropper
        helpless = best == (1.0, 1.0, 1.0) and not (ok(final) if refs else ok(final, base["share"]))
        out["no_gain_helps"] = helpless
        if refs:
            p = pseen[best]
            if p["clip"] > 0.2:
                warn(f"{p['clip']:.0%} of the reference pixels are clipped (a channel at 250+): a clipped white hides "
                     f"the cast; take a shaded part of the object")
            if p["y"] < 30:
                warn("the reference patch is very dark: noise decides its color; take a lit part of the object")
            if not ok(final) and not helpless:
                warn(f"the reference patch stays off neutral by more than {TOL:g} levels (limits {LIMITS[0]}.."
                     f"{LIMITS[1]}): is it really white or gray? A colored object cannot be a reference")
        elif not ok(final, base["share"]) and not helpless:
            warn(f"even the best gains leave the grays off neutral by more than {TOL:g} levels (limits "
                 f"{LIMITS[0]}..{LIMITS[1]}): the source needs more than a balance fix (mixed light, exposure); {hint}")
        # a gain on the edge of the search: the grays may read neutral, but the fix did all it may (T1: bb 1.12 and
        # R/B still 1.21); a stronger cast is mixed light or the LUT, which a balance gain hides rather than fixes
        edge = [f"{n} {x:g}" for n, x in zip(("rr", "gg", "bb"), best) if min(abs(x - L) for L in LIMITS) < 1e-6]
        out["at_limit"] = edge
        if edge:
            warn(f"{', '.join(edge)} is at the limit of the search ({LIMITS[0]}..{LIMITS[1]}): the cast may need more than "
                 f"a balance fix (mixed light, a strong LUT or its mix); check the whites and the skin by eye"
                 + (f" on {out['image']}" if out["image"] else "") + ("" if refs else f"; {hint}"))
        if helpless:
            cs = cast(final)
            warn(f"not neutral, and the search found no gain that brings the {'reference patch' if refs else 'grays'} "
                 f"closer (B-R {cs[0]:+.1f}, G-(R+B)/2 {cs[1]:+.1f} levels; neutral within {TOL:g}): nothing to write"
                 + ("; is the patch really white or gray? A colored object cannot be a reference" if refs else
                    "; the near-gray pixels are likely colored light (sky or a window) rather than gray things, so "
                    f"they are no reference; {hint}"))
        elif best == (1.0, 1.0, 1.0):
            say("no balance fix needed: " + ("the reference patch is already neutral" if refs else
                                             "the grays of the graded video are already neutral"))
        say(f'suggested: "correct": "{suggested}"' if suggested else 'suggested: no "correct"')
        if helpless:
            say("not written: a balance gain does not fix this frame")
        elif not refs and not enough(final, base["share"]):
            warn(f"the suggestion rests on {final['share']:.1%} near-gray pixels (fewer than {GRAY_MIN:.0%} or than "
                 f"{KEEP:.0%} of the share with no fix): not written; {hint}")
        elif not a.write:
            say(f"next: balance.py {a.edit} {' '.join('--ref ' + s for s in a.ref) + ' ' if refs else ''}--write "
                f"(or put it into cut.json by hand), then cut.py {a.edit}")
        elif suggested == c["correct"]:
            say("cut.json already has this correction: nothing to write")
        else:
            with editing_json(e / "cut.json", {}) as cut:
                lk = cut.get("look") if isinstance(cut.get("look"), dict) else {}
                if suggested:
                    lk["correct"] = suggested
                else:
                    lk.pop("correct", None)
                cut["look"] = lk
            out["written"] = True
            say(f"written: cut.json -> look.correct; rebuild the rough cut: cut.py {a.edit}")
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
