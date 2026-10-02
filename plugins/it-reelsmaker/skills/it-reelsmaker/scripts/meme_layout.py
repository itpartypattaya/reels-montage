# -*- coding: utf-8 -*-
"""Size and position of a pop-up meme in the 1080×1920 frame.

Rules (assets/reel-defaults.json → meme_layout; the size comes from the meme_size setting):
  • size: preset s 300 / m 380 / l 460 px on the long side (≈ 28 / 35 / 43 % of the frame width); never more than
    460: a meme must not take half the screen; full-frame only in cutaway mode (0.6–1.2 s, at most one per video);
  • position: one of the slots at the frame edge: top left/right/center, middle left/right, above the subtitles;
  • not allowed: on the face (+60 px around it), on the subtitle band (y 1250–1430), in the UI zones (top 220,
    bottom 420, right 120 px), on the video's active graphics (keep_clear in the plan: cards, hook, CTA).
Face: found automatically with the YuNet model (faces.py: a measurement of the whole rough cut in faces.json, or three
frames of the meme); without the model, the agent looks at frames with a grid (inserts/<id>-grid.jpg) and passes
--face x,y,w,h. No face in the frame: --no-face.

A library for memes.py and visual_plan.py; it has no command line of its own.
"""
import json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import load_defaults, probe, run, warn

W, H = 1080, 1920


def layout(settings=None, doc=None):
    doc = doc or load_defaults()
    L = dict(doc.get("meme_layout") or {})
    L.setdefault("sizes", {"s": 300, "m": 380, "l": 460})
    L.setdefault("max_side", 460)
    L.setdefault("safe", {"top": 220, "bottom": 420, "right": 120, "left": 40})
    L.setdefault("subtitles_band", [1250, 1430])
    L.setdefault("face_margin", 60)
    L.setdefault("edge_margin", 60)
    L.setdefault("slots", ["top-left", "top-right", "top-center", "mid-left", "mid-right", "low-left", "low-right"])
    L["size"] = (settings or {}).get("meme_size") or (doc.get("settings") or {}).get("meme_size") or "m"
    return L


def inter(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return min(ax + aw, bx + bw) > max(ax, bx) and min(ay + ah, by + bh) > max(ay, by)


def grow(r, m):
    x, y, w, h = r
    return [x - m, y - m, w + 2 * m, h + 2 * m]


def fit(aspect, side):
    """The meme's size with the long side `side` at the aspect ratio aspect = w/h."""
    if aspect >= 1:
        return side, max(1, round(side / aspect))
    return max(1, round(side * aspect)), side


def slot_box(slot, w, h, L):
    s, e = L["safe"], L["edge_margin"]
    left = max(s["left"], e)
    right = W - s["right"] - 20 - w
    top = s["top"] + 30
    low = L["subtitles_band"][0] - 40 - h
    mid = round((top + low) / 2)
    x = {"left": left, "right": right, "center": round((left + W - s["right"] - 20 - w) / 2)}
    y = {"top": top, "mid": mid, "low": low}
    vert, horiz = slot.split("-")
    return [x[horiz], y[vert], w, h]


def check_box(box, L, faces=(), keep=()):
    """A list of violations (empty: the position is fine)."""
    x, y, w, h = box
    s = L["safe"]
    out = []
    if max(w, h) > L["max_side"] + 1:
        out.append(f"meme {w}×{h} px is above the ceiling of {L['max_side']} px (≈{round(w * h / (W * H) * 100)} % of the frame): make it smaller")
    if x < s["left"] or y < s["top"] or x + w > W - s["right"] or y + h > H - s["bottom"]:
        out.append(f"meme {box} enters a UI zone (top {s['top']}, bottom {s['bottom']}, right {s['right']} px)")
    b0, b1 = L["subtitles_band"]
    if inter(box, [0, b0, W, b1 - b0]):
        out.append(f"the meme covers the subtitle band (y {b0}–{b1})")
    for f in faces or []:
        if inter(box, grow(f, L["face_margin"])):
            out.append(f"the meme covers the face {f} (with a {L['face_margin']} px margin)")
    for k in keep or []:
        if inter(box, k["box"]):
            out.append(f"the meme covers \"{k.get('what', 'graphics')}\" {k['box']}")
    return out


def choose(L, aspect, faces, keep, size=None, slot=None):
    """The first fitting slot: the side opposite the face; top before middle and low; if it doesn't fit, a smaller size."""
    order = ["l", "m", "s"]
    start = order.index(size or L["size"]) if (size or L["size"]) in order else 1
    fx = sum(f[0] + f[2] / 2 for f in faces) / len(faces) if faces else None
    for sz in order[start:]:
        side = L["sizes"][sz]
        if aspect < 0.6 or aspect > 1.67:  # a narrow or wide meme with the same long side comes out tiny
            side = min(L["max_side"], round(side * 1.3))
        w, h = fit(aspect, side)
        forced = slot not in (None, "", "auto")
        slots = [slot] if forced else list(L["slots"])
        if fx is not None and not forced:
            far = "left" if fx > W / 2 else "right"
            slots.sort(key=lambda s_: (0 if s_.endswith(far) else 1 if s_.endswith("center") else 2,
                                       ["top", "mid", "low"].index(s_.split("-")[0])))
        for sl in slots:
            box = slot_box(sl, w, h, L)
            if not check_box(box, L, faces, keep):
                return box, sz, sl
    return None


def frames(edit, t0, t1, outdir):
    src = Path(edit) / "final.mp4"
    outdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, t in enumerate((t0 + 0.05, (t0 + t1) / 2, max(t0, t1 - 0.05))):
        p = outdir / f"f{k}.png"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
             "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", p])
        paths.append(p)
    return paths


def auto_faces(paths, edit=None, t0=None, t1=None, cam=None):
    """Faces for a meme: from edit/<id>/faces.json (faces.py scan, the whole rough cut), otherwise YuNet on three frames.
    cam = (z, cx, cy) if the video has a virtual camera at this spot. None: the detector is not available."""
    import faces as fc
    data = fc.load(edit) if edit else None
    if data is not None and t0 is not None:
        boxes = fc.between(data, t0, t1)
    else:
        found = fc.detect(paths, scale=1.0)
        if found is None:
            return None
        found, _ = fc.clean_frames(found)  # false "faces" on knees and hands are dropped
        boxes = [b[:4] for fr in found for b in fr]
    return [fc.cam_box(b, cam) for b in boxes]


def sheet(paths, out, L, faces=(), box=None, keep=(), meme=None):
    """Frames at the meme's start, middle and end (half size) with a 100 px grid in 1080×1920 coordinates and the
    no-go zones."""
    from PIL import Image, ImageDraw
    k = 0.5
    tiles = []
    for p in paths:
        im = Image.open(p).convert("RGB").resize((round(W * k), round(H * k)))
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        s = L["safe"]
        for r in ([0, 0, W, s["top"]], [0, H - s["bottom"], W, s["bottom"]], [W - s["right"], 0, s["right"], H]):
            d.rectangle([r[0] * k, r[1] * k, (r[0] + r[2]) * k, (r[1] + r[3]) * k], fill=(90, 90, 90, 110))
        b0, b1 = L["subtitles_band"]
        d.rectangle([0, b0 * k, W * k, b1 * k], fill=(255, 210, 0, 70))
        for kc in keep or []:
            x, y, w, h = kc["box"]
            d.rectangle([x * k, y * k, (x + w) * k, (y + h) * k], outline=(255, 140, 0, 255), width=3)
        for f in faces or []:
            x, y, w, h = grow(f, L["face_margin"])
            d.rectangle([x * k, y * k, (x + w) * k, (y + h) * k], outline=(255, 40, 40, 255), width=3)
        for g in range(100, max(W, H), 100):
            if g < W:
                d.line([g * k, 0, g * k, H * k], fill=(255, 255, 255, 60), width=1)
                d.text((g * k + 2, 2), str(g), fill=(255, 255, 255, 230))
            if g < H:
                d.line([0, g * k, W * k, g * k], fill=(255, 255, 255, 60), width=1)
                d.text((2, g * k + 2), str(g), fill=(255, 255, 255, 230))
        im = Image.alpha_composite(im.convert("RGBA"), ov)
        if box:
            x, y, w, h = box
            if meme and Path(meme).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                m = Image.open(meme).convert("RGBA")
                m.thumbnail((round(w * k), round(h * k)))
                im.alpha_composite(m, (round(x * k + (w * k - m.width) / 2), round(y * k + (h * k - m.height) / 2)))
            ImageDraw.Draw(im).rectangle([x * k, y * k, (x + w) * k, (y + h) * k], outline=(40, 220, 90, 255), width=4)
        tiles.append(im.convert("RGB"))
    sh = Image.new("RGB", (sum(t.width for t in tiles) + 10 * (len(tiles) - 1), tiles[0].height), (0, 0, 0))
    x = 0
    for t in tiles:
        sh.paste(t, (x, 0))
        x += t.width + 10
    out.parent.mkdir(parents=True, exist_ok=True)
    sh.save(out, quality=85)
    return out


def meme_aspect(path, fallback=1.0):
    p = Path(path) if path else None
    if p and p.exists():
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            from PIL import Image
            w, h = Image.open(p).size
            return w / h
        i = probe(p)
        if i.get("w") and i.get("h"):
            return i["w"] / i["h"]
    return fallback
