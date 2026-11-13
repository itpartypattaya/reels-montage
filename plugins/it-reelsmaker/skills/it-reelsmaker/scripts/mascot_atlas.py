# -*- coding: utf-8 -*-
"""Animate a ready character picture: a sheet of poses (or a folder of them) -> the atlas the kit's AtlasMascot plays.

    python mascot_atlas.py atlas <brand> <sheet.png|jpg> [--grid RxC] [--poses neutral,point_up,…] [--holes 3,7]
                           [--symmetric] [--head X,Y,W] [--tol 38]
    python mascot_atlas.py atlas <brand> <folder>      (<pose>.png, optional <pose>-talk.png and <pose>-blink.png)
    python mascot_atlas.py check <brand> [--fix]

The picture is the brand's own illustration (references/mascot-atlas.md). `atlas` writes into
brands/<brand>/assets/mascot/: atlas.png (every pose cut out, scaled and packed), rig.json (the format the kit reads)
and rig-check.png (the sheet to check by eye). It never edits brand.json: it prints the brand.py command for that.

Cells: --grid RxC reads the sheet row by row (rows x columns); --poses names every cell in that order, from the
pose dictionary (neutral, talk, point_left, point_right, point_up, palm, think, surprise, celebrate, shrug, wink),
<pose>-talk / <pose>-blink for a pose's mouth-open and eyes-closed frames, "-" for a cell to skip. neutral is
required: its head sets the size of every pose. A grid that does not divide the sheet evenly is cut inward with a
margin off the lines. An empty cell is an error with its number.

Background: a transparent one is kept as drawn. A flat one (white, green…) is removed by a fill from the cell's
border, so white eyes on a white background stay. Background color enclosed by the character (between an arm and the
body) is only numbered on rig-check.png; --holes 3,7 removes the numbers you confirm. A light part of the character
that touches the background is warned about on the sheet. A gradient, texture or photo background is refused.

The head, not the silhouette, places the poses: the point between the eyes and the head width of neutral are
guessed (or given with --head X,Y,W in sheet pixels), every other pose's head is found by matching neutral's, and the
pose is scaled and moved so its head lands on the same point. The eyes, mouth and skin color are starting guesses:
open rig-check.png, fix "eyes", "mouth", "mouthW", "skin", "ink" in rig.json, then run `check <brand> --fix`, which
re-places the poses from the edited eyes and draws the sheet again. Needs Pillow.
"""
import argparse, math, os, re, sys, uuid
from pathlib import Path

from reels_common import IMAGE_EXT, find_brand, load_json, project_root, rel, save_json, utf8_stdio, warn

POSES = ["neutral", "talk", "point_left", "point_right", "point_up", "palm", "think", "surprise", "celebrate",
         "shrug", "wink"]
VARIANTS = ("talk", "blink")
TOL, SOFT = 38, 36          # background distance (max channel difference): <= TOL is background, a soft edge above
MAX_CELL = 1000             # px: a taller cell is scaled down before work (the kit never shows the mascot that big)
MAX_BOX = 1200              # px: the shared box's height at most (the subtitles start at y 1290)
GUTTER = 4                  # px of transparency between frames in the atlas
GRAY = 128                  # the matching works on the picture flattened on this gray
FLAT_SHARE = 0.6            # this share of the cell's border within FLAT_DIST of its median = a flat background
FLAT_DIST = 16
GRADIENT_SHARE = 0.06    # more of the filled background than this at over half the tolerance = not flat
HOLE_MIN = 0.002            # an enclosed patch of background color is numbered from this share of the figure
OUTLINE_SHARE = 0.6         # a drawing with a dark outline on this share of its edge is checked for open spots
OUT_DIR = Path("assets") / "mascot"
HEAD_MAX = 0.5             # the head is looked for in the top half of the neutral figure
HAND_MAX = 0.12             # a piece of the middle column shorter than this share of the figure is a hand, not the head
OUTLINE_LUMA = 90           # an outline pixel: darker than this, from the head's edge inward
SHOULDER_GROWTH = 1.15     # the run widening by this past its narrowest row = the shoulders: the head ends there
EYE_TO_MOUTH = 0.32        # the mouth this share of the head's height below the eyes (a guess, checked on the sheet)
EYE_SPREAD = 0.2           # with no eyes found: each eye this share of the head's width from the middle
MOUTH_WIDTH = 0.25         # the overlay mouth this share of the head's width


def die(msg):
    sys.exit(msg)


# --- small image helpers ------------------------------------------------------------------------------------

def _pil():
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat
    except ImportError:
        die("mascot_atlas.py needs Pillow: python -m pip install Pillow")
    return Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat


Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat = _pil()
ONE = bytes([0] + [255] * 255)  # bytes.translate table: any non-zero byte -> 255


def mask_img(buf, size):
    return Image.frombytes("L", size, bytes(buf).translate(ONE))


def mask_bytes(img):
    return bytearray(img.point(lambda v: 1 if v else 0).tobytes())


def dilate(img, r):
    for _ in range(r):
        img = img.filter(ImageFilter.MaxFilter(3))
    return img


def m_and(a, b):
    return ImageChops.darker(a, b)


def m_not(a):
    return ImageChops.invert(a)


def n_on(img):
    return img.histogram()[255] if img.mode == "L" else 0


def hexc(c):
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in c[:3])


def luma(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def flat(img):
    """RGBA -> L on a mid gray: what the matching compares (the alpha counts, the background does not)."""
    base = Image.new("RGBA", img.size, (GRAY, GRAY, GRAY, 255))
    return Image.alpha_composite(base, img).convert("L")


def save_png(img, p):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        img.save(tmp, format="PNG")
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1: one small bitmap font
        return ImageFont.load_default()


# --- connected regions on a 0/1 mask (scanline fill: runs found by bytes.find, in C) -------------------------

def fill(free, w, h, seeds):
    """Fill from seeds through 1-bytes of `free` (cleared as they are taken). Returns the runs [(row start, x0, x1)]."""
    runs, stack = [], list(seeds)
    while stack:
        i = stack.pop()
        if not free[i]:
            continue
        y = i // w
        row = y * w
        x0 = free.rfind(b"\x00", row, i)
        x0 = row if x0 < 0 else x0 + 1
        x1 = free.find(b"\x00", i, row + w)
        if x1 < 0:
            x1 = row + w
        free[x0:x1] = bytes(x1 - x0)
        runs.append((y, x0 - row, x1 - row))
        for ny in (y - 1, y + 1):
            if 0 <= ny < h:
                a, b = ny * w + x0 - row, ny * w + x1 - row
                j = free.find(b"\x01", a, b)
                while j >= 0:
                    stack.append(j)
                    e = free.find(b"\x00", j, b)
                    if e < 0:
                        break
                    j = free.find(b"\x01", e, b)
    return runs


def runs_mask(runs, size):
    w, h = size
    buf = bytearray(w * h)
    for y, x0, x1 in runs:
        buf[y * w + x0:y * w + x1] = b"\x01" * (x1 - x0)
    return buf


def runs_stats(runs):
    n = sx = sy = 0
    for y, x0, x1 in runs:
        k = x1 - x0
        n += k
        sx += (x0 + x1 - 1) * k / 2
        sy += y * k
    return n, (sx / n, sy / n) if n else (0, 0)


# --- input: a sheet in a grid or a folder of poses ----------------------------------------------------------

def parse_name(name, number):
    m = re.fullmatch(r"([a-z_]+?)(?:-(talk|blink))?", name)
    if not m or m.group(1) not in POSES:
        die(f"cell {number}: {name!r} is not a pose name; use one of {', '.join(POSES)}, "
            f"<pose>-talk, <pose>-blink or - to skip a cell")
    return m.group(1), m.group(2)


def open_rgba(p):
    try:
        im = Image.open(p)
        im.load()
    except Exception as x:
        die(f"cannot read {p}: {x}")
    if im.mode in ("P", "LA", "L", "I;16") and "transparency" in im.info:
        im = im.convert("RGBA")
    return im.convert("RGBA")


def read_cells(src, grid, poses):
    """[{number, name, pose, variant, img, origin (sheet px of the cell's top left), k (cell px per sheet px)}]"""
    src = Path(src)
    cells = []
    if src.is_dir():
        if grid or poses:
            die("--grid and --poses are for a sheet; a folder names its poses by file name")
        files = sorted(f for f in src.iterdir() if f.suffix.lower() in IMAGE_EXT and not f.name.startswith("."))
        if not files:
            die(f"no pictures in {src}: <pose>.png, <pose>-talk.png, <pose>-blink.png")
        named = []
        for f in files:
            pose, var = parse_name(f.stem.lower(), f.name)
            named.append((POSES.index(pose), VARIANTS.index(var) + 1 if var else 0, f, pose, var))
        for n, (_, _, f, pose, var) in enumerate(sorted(named, key=lambda t: t[:2]), 1):
            cells.append({"number": n, "name": f.stem.lower(), "pose": pose, "variant": var, "img": open_rgba(f),
                          "origin": (0, 0), "k": 1.0, "label": f.name})
    elif src.is_file():
        rows, cols = 1, 1
        if grid:
            m = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", grid)
            if not m or not int(m.group(1)) or not int(m.group(2)):
                die(f"--grid {grid!r}: rows x columns, like 3x3")
            rows, cols = int(m.group(1)), int(m.group(2))
        names = [s.strip().lower() for s in (poses or "neutral").split(",")]
        if len(names) != rows * cols:
            die(f"--poses names {len(names)} cells, the {rows}x{cols} grid has {rows * cols} (use - for a cell to skip)")
        sheet = open_rgba(src)
        W, H = sheet.size
        cw, ch = W / cols, H / rows
        m = max(2, round(0.01 * min(cw, ch)))  # off the grid lines: neighbors' antialiasing and drawn lines stay out
        for i, name in enumerate(names):
            if name == "-":
                continue
            r, q = divmod(i, cols)
            # the margin only off the grid lines inside the sheet: its outer edges are the picture's own
            x0 = math.ceil(q * cw) + (m if q else 0)
            x1 = math.floor((q + 1) * cw) - (m if q < cols - 1 else 0)
            y0 = math.ceil(r * ch) + (m if r else 0)
            y1 = math.floor((r + 1) * ch) - (m if r < rows - 1 else 0)
            if x1 - x0 < 16 or y1 - y0 < 16:
                die(f"cell {i + 1} is {x1 - x0}x{y1 - y0} px: check --grid")
            pose, var = parse_name(name, i + 1)
            cells.append({"number": i + 1, "name": name, "pose": pose, "variant": var,
                          "img": sheet.crop((x0, y0, x1, y1)), "origin": (x0, y0), "k": 1.0,
                          "label": f"cell {i + 1}"})
    else:
        die(f"no such file or folder: {src}")
    seen = set()
    for c in cells:
        if c["name"] in seen:
            die(f"{c['name']} is given twice")
        seen.add(c["name"])
    bases = {c["pose"] for c in cells if not c["variant"]}
    if "neutral" not in bases:
        die("neutral is required: its head sets the size and place of every pose (name a cell or a file neutral)")
    for c in cells:
        if c["variant"] and c["pose"] not in bases:
            die(f"{c['name']}: there is no {c['pose']} pose for this {c['variant']} frame")
        h = c["img"].height
        if h > MAX_CELL:
            k = MAX_CELL / h
            c["img"] = c["img"].resize((max(1, round(c["img"].width * k)), MAX_CELL), Image.LANCZOS)
            c["k"] = k
    return cells


def to_sheet(c, x, y):
    return (round(c["origin"][0] + x / c["k"]), round(c["origin"][1] + y / c["k"]))


# --- background ------------------------------------------------------------------------------------------------

def border(img, t=2):
    w, h = img.size
    out = []
    for box in ((0, 0, w, t), (0, h - t, w, h), (0, t, t, h - t), (w - t, t, w, h - t)):
        out += list(img.crop(box).getdata())
    return out


def median(vals):
    s = sorted(vals)
    return s[len(s) // 2]


def analyze(c, tol):
    """Find the background of one cell. Transparent: kept. Flat: the outer region by a fill from the border, the
    enclosed patches of its color as hole candidates. Anything else stops with advice."""
    img = c["img"]
    w, h = img.size
    ring = border(img)
    # a picture with real transparency is a transparent drawing, even cut close with the figure along its edges
    if sum(img.getchannel("A").histogram()[:16]) >= 0.01 * w * h:
        c["mode"] = "alpha"
        c["holes"] = []
        return
    bg = tuple(median([p[j] for p in ring]) for j in range(3))
    flat_share = sum(1 for p in ring if max(abs(p[j] - bg[j]) for j in range(3)) <= FLAT_DIST) / len(ring)
    where = f"{c['label']} ({c['name']})"
    if flat_share < FLAT_SHARE:
        die(f"{where}: the background is not one flat color (a gradient, a texture or a photo): it cannot be cut "
            f"out cleanly here. Export the character on a transparent PNG background, or on one flat color, and run "
            f"again.")
    rgb = img.convert("RGB")
    d = None
    for j, band in enumerate(rgb.split()):
        diff = ImageChops.difference(band, Image.new("L", (w, h), bg[j]))
        d = diff if d is None else ImageChops.lighter(d, diff)
    cand = bytearray(d.point(lambda v: 1 if v <= tol else 0).tobytes())
    free = bytearray(cand)
    seeds = [i for i in list(range(w)) + list(range((h - 1) * w, h * w)) + list(range(0, h * w, w))
             + list(range(w - 1, h * w, w)) if free[i]]
    outer = fill(free, w, h, seeds)
    outer_n = runs_stats(outer)[0]
    if outer_n < 0.08 * w * h:
        die(f"{where}: the background around the character was not found (it is not one flat color, or the "
            f"character fills the cell). Export it on a transparent PNG background and run again.")
    # the border can be flat while the background shades inward (a glow, a vignette, a floor shadow): then much of
    # the filled region sits far from the border's color, and the rest of the gradient would stay on the character
    outer_m = mask_img(runs_mask(outer, (w, h)), (w, h))
    hist = d.histogram(mask=outer_m)
    if sum(hist[tol // 2 + 1:]) > GRADIENT_SHARE * max(1, sum(hist)):
        die(f"{where}: the background is not one flat color (it shades toward the character: a glow, a gradient or "
            f"a shadow): it cannot be cut out cleanly here. Export the character on a transparent PNG background and "
            f"run again.")
    # a saturated green or blue background: the character has none of that color, so enclosed patches of it are
    # background too, and the spill is held down everywhere
    screen = max(bg) - min(bg) >= 80 and max(range(3), key=lambda j: bg[j]) in (1, 2)
    c.update(mode="color", bg=bg, d=d, outer=runs_mask(outer, (w, h)), screen=screen)
    # enclosed patches of the background color: numbered later, removed only when confirmed
    alpha_fig = (w * h - outer_n)
    holes, i = [], free.find(b"\x01")
    while i >= 0:
        runs = fill(free, w, h, [i])
        n, ctr = runs_stats(runs)
        if n >= max(12, HOLE_MIN * alpha_fig):
            holes.append({"runs": runs, "area": n, "at": ctr})
        i = free.find(b"\x01", i)
    holes.sort(key=lambda o: (round(o["at"][1]), o["at"][0]))
    c["holes"] = holes


def cut_out(c, remove, tol):
    """Apply the background found by analyze(): the outer region and the confirmed holes go, a soft edge around
    them, edge colors freed from the background's, the spill of a saturated (green/blue) background held down."""
    img = c["img"]
    if c["mode"] == "alpha":
        c["out"] = img
        return
    w, h = img.size
    gone = bytearray(c["outer"])
    for hole in c["holes"]:
        if hole["number"] in remove or c["screen"]:
            for y, x0, x1 in hole["runs"]:
                gone[y * w + x0:y * w + x1] = b"\x01" * (x1 - x0)
    gone_m = mask_img(gone, (w, h))
    band = m_and(dilate(gone_m, 2), m_not(gone_m))
    soft = c["d"].point(lambda v: 0 if v <= tol else 255 if v >= tol + SOFT else int(255 * (v - tol) / SOFT))
    r, g, b, a = img.split()
    a = ImageChops.darker(a, Image.composite(soft, Image.new("L", (w, h), 255), band))
    a = Image.composite(Image.new("L", (w, h), 0), a, gone_m)
    bg = c["bg"]
    # unmix the background out of the half-transparent edge: color = (seen - (1 - alpha) * background) / alpha
    rp, gp, bp, ap = r.load(), g.load(), b.load(), a.load()
    bb = band.tobytes()
    i = bb.find(b"\xff")
    while i >= 0:  # only the band's pixels: a few px around the cut
        x, y = i % w, i // w
        if 0 < ap[x, y] < 255:
            al = ap[x, y] / 255
            rp[x, y] = min(255, max(0, round((rp[x, y] - (1 - al) * bg[0]) / al)))
            gp[x, y] = min(255, max(0, round((gp[x, y] - (1 - al) * bg[1]) / al)))
            bp[x, y] = min(255, max(0, round((bp[x, y] - (1 - al) * bg[2]) / al)))
        i = bb.find(b"\xff", i + 1)
    if c["screen"]:  # despill: the screen's channel is held to the larger of the other two
        dom = max(range(3), key=lambda j: bg[j])
        zone = m_not(gone_m)
        ch = [r, g, b]
        others = ImageChops.lighter(*[ch[j] for j in range(3) if j != dom])
        ch[dom] = Image.composite(ImageChops.darker(ch[dom], others), ch[dom], zone)
        r, g, b = ch
    c["out"] = Image.merge("RGBA", (r, g, b, a))
    c["gone"] = gone_m


def open_spots(c):
    """A light part of the character that touched the background was taken with it. With a dark outline drawn
    around the figure, an edge stretch with no outline near it is such a spot. Returns [(x, y, length)] in cell px."""
    if c["mode"] != "color":
        return [], True
    out = c["out"]
    w, h = out.size
    fig = out.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
    edge = m_and(fig, dilate(c["gone"], 1))
    n_edge = n_on(edge)
    if not n_edge:
        return [], True
    L = out.convert("RGB").convert("L")
    ink_l = luma(c.get("ink_rgb") or (0, 0, 0))
    dark = m_and(L.point(lambda v: 255 if v <= max(50, ink_l + 45) else 0), fig)
    loose = m_and(edge, m_not(dilate(dark, 3)))
    n_loose = n_on(loose)
    if n_loose > (1 - OUTLINE_SHARE) * n_edge:
        return [], False  # no outline to go by
    # a spot is a thin line of edge pixels: pieces are joined through a 1 px dilation, then counted on the edge itself
    lp = mask_bytes(loose)
    free = mask_bytes(dilate(loose, 1))
    spots, i = [], free.find(b"\x01")
    while i >= 0:
        runs = fill(free, w, h, [i])
        n = sum(lp[y * w + x0:y * w + x1].count(1) for y, x0, x1 in runs)
        _, ctr = runs_stats(runs)
        if n >= max(8, 0.006 * n_edge):
            spots.append((ctr[0], ctr[1], n))
        i = free.find(b"\x01", i)
    return spots, True


# --- the head: guess on neutral, find on every other pose ---------------------------------------------------

def figure_box(img, thr=40):
    return img.getchannel("A").point(lambda v: 255 if v > thr else 0).getbbox()


def guess_head(img):
    """The head of the neutral pose, a guess the agent checks on the sheet: walk down the figure's middle column from
    its top, row by row, keeping the width of the opaque run on that column (a short piece of the column above the
    head, a raised hand, is passed over); the head is the stretch down to the narrowest row before the run widens into
    the shoulders. The eyes are the dark spots inside the face at mid-head, the mouth EYE_TO_MOUTH of the head below.
    A figure whose outline never narrows has no head to find this way: "sure" is False and the atlas command asks for
    --head. -> {"anchor": point between the eyes, "hw": head width, "eyes": [left, right] or None, "mouth": point,
    "sure": bool}"""
    left, top, right, bottom = figure_box(img)
    fig_h = bottom - top
    a = img.getchannel("A").load()
    # the middle column: where the figure's opaque mass is centered, so a raised arm on one side tips it little
    cols = [0] * (right - left)
    for y in range(top, bottom):
        for x in range(left, right):
            if a[x, y] > 40:
                cols[x - left] += 1
    mass = sum(cols)
    mid = left + (sum(k * n for k, n in enumerate(cols)) / mass if mass else (right - left) / 2)
    # the column's opaque stretches from the top; the first one long enough to be a head
    stretches, cur = [], []
    for y in range(top, bottom):
        run = row_run(img, mid, y)
        if run and run[0] <= mid < run[1]:
            cur.append((y, run))
        elif cur:
            stretches.append(cur)
            cur = []
    if cur:
        stretches.append(cur)
    widths = next((s for s in stretches if len(s) >= HAND_MAX * fig_h), stretches[0] if stretches else [])
    widths = widths[: max(2, int(fig_h * HEAD_MAX))]  # the head is in the first half of the figure's height at most
    fallback = {"anchor": ((left + right) / 2, top + 0.15 * fig_h), "hw": (right - left) * 0.5, "eyes": None,
                "mouth": ((left + right) / 2, top + 0.25 * fig_h), "sure": False}
    if not widths:
        return fallback
    # down the skull the run widens, then narrows to the chin or the neck; the first widening past that narrowest
    # row is the shoulders
    def width(k):
        return widths[k][1][1] - widths[k][1][0]
    wide_at, neck, narrow, shoulders = 0, len(widths) - 1, None, False
    for k in range(len(widths)):
        w = width(k)
        if narrow is None:
            if w >= width(wide_at):
                wide_at = k
            elif w < 0.97 * width(wide_at):
                narrow, neck = w, k
        elif w < narrow:
            narrow, neck = w, k
        elif w > narrow * SHOULDER_GROWTH:
            shoulders = True
            break
    if narrow is None:  # it only widened: no head outline to go by
        return fallback
    head_top, head_bot = widths[0][0], widths[neck][0]
    l0, r0 = widths[wide_at][1]
    hw, hx = r0 - l0, (l0 + r0) / 2
    hh = max(1, head_bot - head_top)
    eyes = dark_spots(img, mid, head_top + 0.3 * hh, head_top + 0.65 * hh, hx)
    if eyes:
        ax, ay = (eyes[0][0] + eyes[1][0]) / 2, (eyes[0][1] + eyes[1][1]) / 2
    else:
        ax, ay = hx, head_top + 0.5 * hh
    return {"anchor": (ax, ay), "hw": hw, "eyes": eyes, "mouth": (ax, ay + EYE_TO_MOUTH * hh),
            "sure": shoulders or narrow < 0.8 * hw}


def dark_spots(img, col, y0, y1, cx):
    """The two dark spots of a face (the eyes) in the rows y0..y1: on each row, inside the head's run through the
    column col with its outline left out (the dark pixels from each edge inward, however thick), the pixels much darker
    than the face; averaged on each side of cx. None when one side has too few."""
    lum = img.convert("RGB").convert("L").load()
    a = img.getchannel("A").load()
    rows = range(max(0, round(y0)), min(img.height, round(y1) + 1))
    face = []
    inner = {}
    for y in rows:
        run = row_run(img, col, y)
        if not run:
            continue
        l, r = run[0], run[1] - 1
        while l < r and lum[l, y] < OUTLINE_LUMA:
            l += 1
        while r > l and lum[r, y] < OUTLINE_LUMA:
            r -= 1
        l, r = l + 2, r - 2
        if r - l < 4:
            continue
        inner[y] = (l, r)
        face.extend(lum[x, y] for x in range(l, r + 1) if a[x, y] > 200)
    if not face:
        return None
    face.sort()
    cut = face[len(face) // 2] * 0.55
    sides = {-1: [0.0, 0.0, 0], 1: [0.0, 0.0, 0]}
    for y, (l, r) in inner.items():
        for x in range(l, r + 1):
            if a[x, y] > 200 and lum[x, y] < cut:
                s = sides[-1 if x < cx else 1]
                s[0] += x
                s[1] += y
                s[2] += 1
    need = max(3, len(face) // 400)
    if sides[-1][2] < need or sides[1][2] < need:
        return None
    return [(s[0] / s[2], s[1] / s[2]) for s in (sides[-1], sides[1])]


def row_run(img, x, y, thr=40):
    """The opaque run of row y that holds x (or the nearest one): the head's width at the eye line."""
    a = img.getchannel("A")
    yy = min(max(0, int(y)), img.height - 1)
    row = a.crop((0, yy, img.width, yy + 1)).tobytes()
    runs, start = [], None
    for i in range(len(row) + 1):
        on = i < len(row) and row[i] > thr
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append((start, i))
            start = None
    if not runs:
        return None
    return min(runs, key=lambda r: 0 if r[0] <= x < r[1] else min(abs(r[0] - x), abs(r[1] - x)))


def tpl_box(anchor, hw):
    ax, ay = anchor
    return (ax - 0.6 * hw, ay - 0.6 * hw, ax + 0.6 * hw, ay + 0.45 * hw)


def clamp_box(box, size):
    """The template box inside the picture: a crop past its edge would add black, not the matching gray."""
    x0, y0, x1, y1 = (round(v) for v in box)
    return [max(0, x0), max(0, y0), min(size[0], x1), min(size[1], y1)]


def _scan(hay, t, xr, yr):
    tw, th = t.size
    n = tw * th
    best = None
    for y in range(max(0, yr[0]), min(hay.height - th, yr[1]) + 1):
        for x in range(max(0, xr[0]), min(hay.width - tw, xr[1]) + 1):
            hist = ImageChops.difference(hay.crop((x, y, x + tw, y + th)), t).histogram()
            v = sum(i * c for i, c in enumerate(hist) if c) / n
            if best is None or v < best[0]:
                best = (v, x, y)
    return best


def find_head(hay, tpl, s_lo, s_hi):
    """Where tpl (L, on gray) sits in hay, and at what scale: coarse to fine. Returns (score, sx, sy, x, y) with
    the scale the resized template really has on each axis."""
    tw, th = tpl.size
    best, guess = None, None
    for size, step, spread, reach in ((16, 0.06, None, None), (48, 0.02, 0.06, 4), (None, 0.005, 0.02, 4)):
        f = min(1.0, size / tw) if size else 1.0
        H = hay if f == 1.0 else hay.resize((max(1, round(hay.width * f)), max(1, round(hay.height * f))), Image.BOX)
        lo, hi = (s_lo, s_hi) if guess is None else (max(s_lo, guess[0] - spread), min(s_hi, guess[0] + spread))
        cur = None
        s = lo
        while s <= hi + 1e-9:
            t = tpl.resize((max(4, round(tw * f * s)), max(4, round(th * f * s))), Image.BOX)
            if guess is None:
                xr, yr = (0, H.width), (0, H.height)
            else:
                gx, gy = guess[1] * f, guess[2] * f
                xr, yr = (round(gx) - reach, round(gx) + reach), (round(gy) - reach, round(gy) + reach)
            r = _scan(H, t, xr, yr)
            if r and (cur is None or r[0] < cur[0]):
                cur = (r[0], t.width / (tw * f), t.height / (th * f), r[1] / f, r[2] / f, s)
            s += step
        if cur is None:
            break
        best = cur
        guess = (cur[5], cur[3], cur[4])
    if best is None:
        return None
    return best[:5]


# --- colors ------------------------------------------------------------------------------------------------------

def ink_color(img):
    a = img.getchannel("A").point(lambda v: 255 if v >= 250 else 0)
    L = img.convert("RGB").convert("L")
    hist = L.histogram(mask=a)
    total = sum(hist)
    if not total:
        return (0, 0, 0)
    acc, cut = 0, 0
    for v, n in enumerate(hist):
        acc += n
        if acc >= 0.03 * total:
            cut = v
            break
    dark = m_and(L.point(lambda v: 255 if v <= cut + 4 else 0), a)
    st = ImageStat.Stat(img.convert("RGB"), mask=dark)
    return tuple(st.median)


def skin_color(img, mouth, mw, ink):
    """The face around the mouth: a ring above and beside it, without the dark lines."""
    x, y = mouth
    m = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(m)
    r1, r0 = 0.85 * mw, 0.45 * mw
    d.ellipse((x - r1, y - r1, x + r1, y + r1), fill=255)
    d.ellipse((x - r0, y - r0, x + r0, y + r0), fill=0)
    d.rectangle((x - r1 - 1, y + 0.2 * mw, x + r1 + 1, y + r1 + 1), fill=0)
    L = img.convert("RGB").convert("L")
    keep = L.point(lambda v: 255 if v > luma(ink) + 50 else 0)
    m = m_and(m_and(m, keep), img.getchannel("A").point(lambda v: 255 if v >= 250 else 0))
    if not n_on(m):
        return None
    return tuple(ImageStat.Stat(img.convert("RGB"), mask=m).median)


# --- build ---------------------------------------------------------------------------------------------------------

def layout(items, g):
    """Normalize every frame by its pose's head (and the global factor g), then the shared box."""
    for it in items:
        r = g / it["s"]
        x0, y0, x1, y1 = it["crop"]
        it["r"] = r
        it["size"] = (max(1, round((x1 - x0) * r)), max(1, round((y1 - y0) * r)))
        it["a"] = ((it["anchor"][0] - x0) * r, (it["anchor"][1] - y0) * r)
    poses = [it for it in items if not it["variant"]]
    ax = math.ceil(max(it["a"][0] for it in poses))
    ay = math.ceil(max(it["a"][1] for it in poses))
    for it in items:
        base = it if not it["variant"] else it["base"]
        it["offset"] = (round(ax - base["a"][0]), round(ay - base["a"][1]))
    bw = max(it["offset"][0] + it["size"][0] for it in poses)
    bh = max(it["offset"][1] + it["size"][1] for it in poses)
    return (ax, ay), (bw, bh)


def pack(items):
    total = sum((it["size"][0] + GUTTER) * (it["size"][1] + GUTTER) for it in items)
    width = max(max(it["size"][0] for it in items) + 2 * GUTTER, int(math.sqrt(total) * 1.15))
    x = y = GUTTER
    shelf = 0
    for it in items:
        w, h = it["size"]
        if x + w + GUTTER > width and x > GUTTER:
            x, y = GUTTER, y + shelf + GUTTER
            shelf = 0
        it["at"] = (x, y)
        x += w + GUTTER
        shelf = max(shelf, h)
    W = max(it["at"][0] + it["size"][0] for it in items) + GUTTER
    H = y + shelf + GUTTER
    atlas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for it in items:
        frame = it["cell"]["out"].crop(tuple(round(v) for v in it["crop"]))
        frame = frame.convert("RGBa").resize(it["size"], Image.LANCZOS).convert("RGBA")
        it["frame"] = frame
        atlas.paste(frame, it["at"])
    return atlas


def to_atlas(it, p):
    x0, y0 = it["crop"][:2]
    return (it["at"][0] + (p[0] - x0) * it["r"], it["at"][1] + (p[1] - y0) * it["r"])


def draw_check(atlas, rig, notes):
    """The atlas on light gray with every frame, the anchor cross, eye dots, the mouth bar, numbered holes and open
    spots; below it every pose placed in the shared box side by side, the anchor line across them."""
    W, H = atlas.size
    bw, bh = rig["box"]
    ax, ay = rig["anchor"]
    poses = list(rig["poses"].items())
    gap = 24
    strip_w = len(poses) * (bw + gap) + gap
    out = Image.new("RGBA", (max(W, strip_w), H + bh + 3 * gap), (228, 228, 228, 255))
    out.alpha_composite(atlas, (0, 0))
    d = ImageDraw.Draw(out)
    f = font(16)

    def cross(x, y, col, r=12):
        d.line((x - r, y, x + r, y), fill=col, width=2)
        d.line((x, y - r, x, y + r), fill=col, width=2)

    def marks(dx, dy, p):
        for ex, ey in p["eyes"]:
            d.ellipse((dx + ex - 4, dy + ey - 4, dx + ex + 4, dy + ey + 4), fill=(0, 200, 220, 255))
        mx, my = p["mouth"]
        mw = p["mouthW"]
        d.line((dx + mx - mw / 2, dy + my, dx + mx + mw / 2, dy + my), fill=(230, 0, 160, 255), width=3)

    for name, p in poses:
        for kind in ("cell", "talk", "blink"):
            if kind not in p:
                continue
            x, y, w, h = p[kind]
            d.rectangle((x - 1, y - 1, x + w, y + h), outline=(220, 40, 40, 255), width=1)
            d.text((x + 3, y + 2), name if kind == "cell" else f"{name}-{kind}", fill=(220, 40, 40, 255), font=f)
            cx, cy = p["cell"][:2]
            cross(x + ax - p["offset"][0], y + ay - p["offset"][1], (35, 70, 255, 255))
            marks(x - cx, y - cy, p)
    for n in notes:
        x, y = n["at"]
        col = (255, 120, 0, 255)
        r = 5 if n["kind"] == "hole" else 9
        label = (str(n["number"]) + ("" if n["removed"] else "?")) if n["kind"] == "hole" else "!"
        if n["kind"] == "hole":
            d.ellipse((x - r, y - r, x + r, y + r), outline=col, width=2)
        else:
            d.rectangle((x - r, y - r, x + r, y + r), outline=col, width=3)
        tx, ty = x + r + 3, y - 9
        d.rectangle(d.textbbox((tx, ty), label, font=f), fill=(255, 255, 255, 235))
        d.text((tx, ty), label, fill=col, font=f)
    top = H + 2 * gap
    d.line((0, top + ay, out.width, top + ay), fill=(35, 70, 255, 120), width=1)
    for i, (name, p) in enumerate(poses):
        x0 = gap + i * (bw + gap)
        d.rectangle((x0 - 1, top - 1, x0 + bw, top + bh), outline=(160, 160, 160, 255))
        x, y, w, h = p["cell"]
        out.alpha_composite(atlas.crop((x, y, x + w, y + h)), (x0 + p["offset"][0], top + p["offset"][1]))
        cross(x0 + ax, top + ay, (35, 70, 255, 255))
        marks(x0 + p["offset"][0] - x, top + p["offset"][1] - y, p)
        d.text((x0 + 3, top + bh + 3), name, fill=(60, 60, 60, 255), font=f)
    return out


def cmd_atlas(a):
    project = project_root()
    bdir, _ = find_brand(a.brand, project)
    if not bdir:
        die(f"no brand {a.brand!r} in {project / 'brands'}: create it first (brand.py new)")
    remove = set()
    if a.holes:
        try:
            remove = {int(v) for v in a.holes.split(",") if v.strip()}
        except ValueError:
            die(f"--holes {a.holes!r}: hole numbers from rig-check.png, like 3,7")
    cells = read_cells(a.source, a.grid, a.poses)
    for c in cells:
        analyze(c, a.tol)
    number = 0
    for c in cells:
        for hole in c["holes"]:
            number += 1
            hole["number"] = number
    unknown = sorted(remove - set(range(1, number + 1)))
    if unknown:
        die(f"--holes {','.join(map(str, unknown))}: no such hole; the sheet has "
            + (f"holes 1-{number}" if number else "no holes"))
    for c in cells:
        cut_out(c, remove, a.tol)
        box = figure_box(c["out"])
        area = n_on(c["out"].getchannel("A").point(lambda v: 255 if v >= 128 else 0))
        if not box or area < 0.003 * c["out"].width * c["out"].height:
            die(f"{c['label']} ({c['name']}) is empty: check --grid and --poses (the cells are read row by row)")
        c["box"] = box

    by = {c["name"]: c for c in cells}
    neutral = by["neutral"]
    if a.head:
        try:
            hx, hy, hw = (float(v) for v in a.head.split(","))
        except ValueError:
            die(f"--head {a.head!r}: X,Y,W in sheet pixels (the point between the eyes, the head width)")
        k = neutral["k"]
        g0 = guess_head(neutral["out"])
        anchor = ((hx - neutral["origin"][0]) * k, (hy - neutral["origin"][1]) * k)
        head = {"anchor": anchor, "hw": hw * k,
                "mouth": (anchor[0], anchor[1] + (g0["mouth"][1] - g0["anchor"][1]) * hw * k / g0["hw"])}
    else:
        head = guess_head(neutral["out"])
        if not head["sure"]:
            warn(f"{neutral['label']} (neutral): no head outline found (the figure never narrows below its top): the "
                 f"poses are placed by a rough guess; check the cross on rig-check.png and give the head with --head X,Y,W "
                 f"(sheet pixels: the point between the eyes, the head width)")
    hw = head["hw"]
    if hw < 12:
        die("the head of neutral was not found (narrower than 12 px): give it with --head X,Y,W")
    tb = clamp_box(tpl_box(head["anchor"], hw), neutral["out"].size)
    ref = flat(neutral["out"]).crop(tuple(tb))
    rel_anchor = (head["anchor"][0] - tb[0], head["anchor"][1] - tb[1])
    n_run = row_run(neutral["out"], *head["anchor"])

    items = []
    for c in cells:
        if c["variant"]:
            continue
        if c is neutral:
            s, anchor = 1.0, head["anchor"]
        else:
            m = find_head(flat(c["out"]), ref, 0.6, 1.6)
            if m is None:
                die(f"{c['label']} ({c['name']}): the head of neutral was not found in it")
            _, sx, sy, x, y = m
            s, anchor = (sx + sy) / 2, (x + rel_anchor[0] * sx, y + rel_anchor[1] * sy)
            # the match finds the head; its scale is noisy by a few %: the head's width at the eye line, measured
            # as on neutral, gives it exactly (unless an arm joins that row: then the two disagree, the match stays)
            run = row_run(c["out"], *anchor)
            if n_run and run:
                s_run = (run[1] - run[0]) / (n_run[1] - n_run[0])
                if abs(s_run - s) <= 0.06 * s:
                    hay = flat(c["out"])
                    t = ref.resize((max(4, round(ref.width * s_run)), max(4, round(ref.height * s_run))), Image.BOX)
                    best = _scan(hay, t, (round(x) - 4, round(x) + 4), (round(y) - 4, round(y) + 4))
                    if best:
                        sx, sy = t.width / ref.width, t.height / ref.height
                        s = s_run
                        anchor = (best[1] + rel_anchor[0] * sx, best[2] + rel_anchor[1] * sy)
        l, t, r, b = c["box"]
        items.append({"cell": c, "name": c["name"], "variant": None, "s": s, "anchor": anchor,
                      "crop": (l - 4, t - 4, r + 4, b + 4)})
    poses = {it["name"]: it for it in items}
    for c in cells:
        if not c["variant"]:
            continue
        base = poses[c["pose"]]
        bs = base["s"]
        tb = clamp_box(tpl_box(base["anchor"], hw * bs), base["cell"]["out"].size)
        tpl = flat(base["cell"]["out"]).crop(tuple(tb))
        m = find_head(flat(c["out"]), tpl, 0.92, 1.08)
        if m is None:
            die(f"{c['label']} ({c['name']}): the head of {c['pose']} was not found in it")
        _, sx, sy, x, y = m
        ra = (base["anchor"][0] - tb[0], base["anchor"][1] - tb[1])
        anchor = (x + ra[0] * sx, y + ra[1] * sy)
        rs = (sx + sy) / 2
        bx0, by0, bx1, by1 = base["crop"]
        x0 = round(anchor[0] - (base["anchor"][0] - bx0) * rs)
        y0 = round(anchor[1] - (base["anchor"][1] - by0) * rs)
        items.append({"cell": c, "name": c["name"], "variant": c["variant"], "base": base, "s": bs * rs,
                      "anchor": anchor, "crop": (x0, y0, x0 + round((bx1 - bx0) * rs), y0 + round((by1 - by0) * rs))})

    g = 1.0
    anchor, box = layout(items, g)
    if box[1] > MAX_BOX:
        g = MAX_BOX / box[1]
        anchor, box = layout(items, g)
    for it in items:  # a variant has its pose's size exactly
        if it["variant"]:
            it["size"] = it["base"]["size"]
            it["r"] = it["size"][0] / max(1e-6, it["crop"][2] - it["crop"][0])
    atlas = pack(items)

    # eyes and mouth: neutral's guess, carried to every pose through its head
    ex = EYE_SPREAD * hw
    n_eyes = head.get("eyes") or [(head["anchor"][0] - ex, head["anchor"][1]), (head["anchor"][0] + ex, head["anchor"][1])]
    n_mouth = head["mouth"]
    mouth_w = max(4, round(MOUTH_WIDTH * hw * g))
    rig_poses = {}
    notes = []
    for it in items:
        if it["variant"]:
            continue
        c = it["cell"]
        s = it["s"]

        def carry(p, it=it, s=s):
            return to_atlas(it, (it["anchor"][0] + (p[0] - head["anchor"][0]) * s,
                                 it["anchor"][1] + (p[1] - head["anchor"][1]) * s))
        eyes = [[round(v) for v in carry(p)] for p in n_eyes]
        mouth = [round(v) for v in carry(n_mouth)]
        frame = it["frame"]
        ink = ink_color(frame)
        loc = (mouth[0] - it["at"][0], mouth[1] - it["at"][1])
        skin = skin_color(frame, loc, mouth_w, ink) or (230, 190, 160)
        rig_poses[it["name"]] = {"cell": [it["at"][0], it["at"][1], it["size"][0], it["size"][1]],
                                 "offset": list(it["offset"]), "eyes": eyes, "mouth": mouth, "mouthW": mouth_w,
                                 "skin": hexc(skin), "ink": hexc(ink)}
        c["ink_rgb"] = ink
    for it in items:
        if it["variant"]:
            rig_poses[it["base"]["name"]][it["variant"]] = [it["at"][0], it["at"][1], it["size"][0], it["size"][1]]
            it["cell"]["ink_rgb"] = it["base"]["cell"].get("ink_rgb")
    order = sorted(rig_poses, key=POSES.index)
    rig = {"atlas": "atlas.png", "width": atlas.width, "height": atlas.height, "symmetric": bool(a.symmetric),
           "box": list(box), "anchor": list(anchor), "head": round(hw * g),
           "poses": {n: rig_poses[n] for n in order}}

    # report: holes, open spots
    by_cell = {id(it["cell"]): it for it in items}
    lines = []
    for c in cells:
        it = by_cell[id(c)]
        for hole in c["holes"]:
            sx, sy = to_sheet(c, *hole["at"])
            done = hole["number"] in remove or c["screen"]
            lines.append(f"hole {hole['number']} ({c['name']}): at {sx},{sy} on the sheet, {hole['area']} px, "
                         + ("removed" if done else "kept"))
            notes.append({"kind": "hole", "number": hole["number"], "removed": done, "at": to_atlas(it, hole["at"])})
        spots, outlined = open_spots(c)
        if not outlined:
            warn(f"{c['name']}: the drawing has no dark outline, so a light part touching the background cannot be "
                 f"told from it: check the edges on rig-check.png")
        for x, y, n in spots:
            sx, sy = to_sheet(c, x, y)
            warn(f"{c['name']}: a light part of the character touches the background at {sx},{sy} on the sheet and "
                 f"may have been cut with it (marked ! on rig-check.png); if so, give a transparent PNG or close its "
                 f"outline")
            notes.append({"kind": "spot", "at": to_atlas(it, (x, y))})

    out_dir = bdir / OUT_DIR
    check = draw_check(atlas, rig, notes)
    save_png(atlas, out_dir / "atlas.png")
    save_png(check, out_dir / "rig-check.png")
    save_json(out_dir / "rig-check.json", {"notes": notes})  # check draws the numbers and warnings again
    save_json(out_dir / "rig.json", rig)

    modes = {c["mode"] for c in cells}
    bgs = sorted({hexc(c["bg"]) for c in cells if c["mode"] == "color"})
    print(f"atlas: {rel(out_dir / 'atlas.png', project)} ({atlas.width}x{atlas.height}), box {box[0]}x{box[1]}, "
          f"anchor {anchor[0]},{anchor[1]}")
    print("background: " + ("transparent, kept" if modes == {"alpha"} else
                            f"flat {', '.join(bgs)}, removed" + (" (some cells transparent)" if "alpha" in modes else "")))
    nx, ny = to_sheet(neutral, *head["anchor"])
    print(f"head: neutral's {round(hw / neutral['k'])} px wide, the point between the eyes at {nx},{ny} on the sheet"
          + (" (given)" if a.head else " (a guess)"))
    for it in items:
        frames = [v for v in VARIANTS if v in rig["poses"].get(it["name"], {})]
        if not it["variant"]:
            print(f"pose {it['name']}: scaled x{it['r']:.2f}" + (f", with {' and '.join(frames)}" if frames else ""))
    for line in lines:
        print(line)
    if hw * g < 40:
        warn(f"the head is {round(hw * g)} px wide in the atlas: the character will look soft when it is large on "
             f"screen; a bigger picture helps")
    print(f"check: open {rel(out_dir / 'rig-check.png', project)}: on every pose the blue cross must sit between the "
          f"eyes, the dots on the eyes, the pink bar on the mouth; the poses below must keep the head on the line. "
          f"Fix eyes, mouth, mouthW, skin, ink in rig.json and run: python \"{Path(__file__).resolve()}\" check "
          f"{a.brand} --fix")
    if any(not n["removed"] for n in notes if n["kind"] == "hole"):
        print("holes: numbers with ? are kept; if one is background (between an arm and the body), run again with "
              "--holes <numbers>")
    print(f"next: python \"{Path(__file__).resolve().parent / 'brand.py'}\" mascot {a.brand} --atlas "
          f"{OUT_DIR.as_posix()}/rig.json")


# --- check: after editing rig.json by hand --------------------------------------------------------------------

def cmd_check(a):
    project = project_root()
    bdir, _ = find_brand(a.brand, project)
    if not bdir:
        die(f"no brand {a.brand!r}")
    d = bdir / OUT_DIR
    rig = load_json(d / "rig.json")
    if not rig or not (d / str(rig.get("atlas", "atlas.png"))).is_file():
        die(f"no atlas in {rel(d, project)}: run mascot_atlas.py atlas first")
    atlas = Image.open(d / rig["atlas"]).convert("RGBA")
    errors = []
    poses = rig.get("poses") or {}
    if "neutral" not in poses:
        errors.append("no neutral pose")
    W, H = atlas.size
    for name, p in poses.items():
        if name not in POSES:
            errors.append(f"{name}: not a pose name")
        for kind in ("cell", "talk", "blink"):
            if kind in p:
                x, y, w, h = p[kind]
                if x < 0 or y < 0 or x + w > W or y + h > H:
                    errors.append(f"{name}: {kind} is outside the atlas")
                if kind != "cell" and [w, h] != p["cell"][2:]:
                    errors.append(f"{name}: {kind} is not the size of the pose")
        if not 1 <= len(p.get("eyes") or []) <= 2:
            errors.append(f"{name}: eyes needs one or two points")
        for k in ("skin", "ink"):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(p.get(k, ""))):
                errors.append(f"{name}: {k} must be #rrggbb")
    if errors:
        die("rig.json: " + "; ".join(errors))
    ax, ay = rig["anchor"]
    off = []
    for name, p in poses.items():
        es = p["eyes"]
        mx, my = sum(e[0] for e in es) / len(es), sum(e[1] for e in es) / len(es)
        rx, ry = mx - p["cell"][0], my - p["cell"][1]
        dx, dy = ax - p["offset"][0] - rx, ay - p["offset"][1] - ry
        if abs(dx) > 1 or abs(dy) > 1:
            off.append((name, rx, ry, dx, dy))
    if off and a.fix:
        rels = {}
        for name, p in poses.items():
            es = p["eyes"]
            rels[name] = (sum(e[0] for e in es) / len(es) - p["cell"][0], sum(e[1] for e in es) / len(es) - p["cell"][1])
        nax = math.ceil(max(v[0] for v in rels.values()))
        nay = math.ceil(max(v[1] for v in rels.values()))
        for name, p in poses.items():
            p["offset"] = [round(nax - rels[name][0]), round(nay - rels[name][1])]
        rig["anchor"] = [nax, nay]
        rig["box"] = [max(p["offset"][0] + p["cell"][2] for p in poses.values()),
                      max(p["offset"][1] + p["cell"][3] for p in poses.values())]
        save_json(d / "rig.json", rig)
        print(f"placed again by the eyes: {', '.join(n for n, *_ in off)}; box {rig['box'][0]}x{rig['box'][1]}")
        off = []
    notes = (load_json(d / "rig-check.json") or {}).get("notes") or []
    save_png(draw_check(atlas, rig, notes), d / "rig-check.png")
    for name, rx, ry, dx, dy in off:
        warn(f"{name}: the eyes' midpoint is {math.hypot(dx, dy):.0f} px off the anchor; run check --fix to place "
             f"the pose by its eyes")
    print(f"check: {rel(d / 'rig-check.png', project)} drawn again; rig.json is "
          + ("consistent" if not off else "readable, poses off the anchor listed above"))
    return 1 if off else 0


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("atlas", help="cut a sheet or a folder of poses into atlas.png + rig.json + rig-check.png")
    p.add_argument("brand")
    p.add_argument("source", help="a sheet (PNG, JPG, WebP) or a folder of <pose>.png")
    p.add_argument("--grid", help="rows x columns of the sheet, like 3x3 (default 1x1)")
    p.add_argument("--poses", help="cell names row by row: neutral,point_up,…, <pose>-talk, <pose>-blink, - to skip")
    p.add_argument("--holes", help="numbers from rig-check.png of enclosed background to remove, like 3,7")
    p.add_argument("--symmetric", action="store_true", help="the character may be mirrored (nothing one-sided)")
    p.add_argument("--head", help="X,Y,W in sheet px: neutral's point between the eyes and head width (else guessed)")
    p.add_argument("--tol", type=int, default=TOL, help=f"background color distance, 0-255 (default {TOL})")
    c = sub.add_parser("check", help="after editing rig.json: validate it and draw rig-check.png again")
    c.add_argument("brand")
    c.add_argument("--fix", action="store_true", help="place every pose again so its eyes' midpoint is the anchor")
    a = ap.parse_args()
    if a.cmd == "atlas":
        cmd_atlas(a)
        return 0
    return cmd_check(a)


if __name__ == "__main__":
    sys.exit(main())
