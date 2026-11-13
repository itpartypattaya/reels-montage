# -*- coding: utf-8 -*-
"""The path of a photo shot's own motion when the shot names its subject (an ROI). Geometry only, no ffmpeg: cut.py
plans the path before anything is encoded (an ROI that cannot stay in frame stops it there), footage.prepare renders
the same path, and the subject's place on screen goes into captions.json (shots -> roi_path, record) for the scenes.

All sizes are of the UPRIGHT photo (reels_common.upright_size: the EXIF orientation applied). A window is (x, y, w, h)
in its pixels with the video frame's aspect; the frame k of n shows window(path, k), a straight line from the first
window to the last.

    push   the whole 9:16 frame around the ROI -> the ROI with MARGIN around it, as deep as the photo's pixels allow
           (the deepest window keeps at least the video frame's width in source pixels) and never past ZMAX; never
           shallower than the usual slow push-in (1 + MOVE_Z) unless the ROI fills the frame
    pull   the push backwards
    still, none   the whole 9:16 frame centered on the ROI
    pan    left to right at the whole frame's height: along a wide ROI from its left end to its right end (its height
           stays in frame), or across a subject that fits (all of it stays in frame)

The whole path is checked: the ROI (for a pan its height) is inside every window, and every window inside the photo.
"""

MOVE_Z = 0.06    # the usual slow push-in, pull and pan of a photo (footage.prepare, a shot with no ROI)
ZMAX = 2.0       # the deepest push: half the whole frame's width
MARGIN = 0.12    # room around the ROI at the deepest frame of a push, of the ROI's size on each side
PAN_ROOM = 0.10  # a pan starts and ends this much (of the window's width) past a wide ROI's ends, or inside a narrow one
PAN_MIN = 0.05   # a pan that travels less than this part of the window's width is no pan
SMALL = 0.75     # a photo whose whole 9:16 frame is narrower than this part of the video frame is small
MAX_UP = 1.25    # a photo shown whole ("contain") is enlarged at most this much: a small one stays sharp, smaller


class PhotoError(ValueError):
    """A photo shot whose ROI cannot stay in frame: cut.py prints it and stops before encoding."""


def full_frame(size, out):
    """(w, h) of the largest window with the video frame's aspect inside the photo."""
    a = out[0] / out[1]
    if size[0] / size[1] > a:
        return size[1] * a, float(size[1])
    return float(size[0]), size[0] / a


def fit_for(size, out, fit):
    """A photo shot's fit and the warnings: a small photo is shown whole, at most MAX_UP its own size, on a blurred
    background ("contain") unless the shot asks for "cover", which then stays, soft. -> (fit, [warning])."""
    w, _ = full_frame(size, out)
    if w >= SMALL * out[0] - 1e-9 or fit == "contain":
        return fit or "cover", []
    if fit is None:
        return "contain", [f"the photo is small for the frame ({size[0]}x{size[1]}: its 9:16 frame is {w:.0f} px wide "
                           f"for a {out[0]} px video): it is shown whole, at most x{MAX_UP:g} its own size, on a blurred "
                           f"background; \"fit\": \"cover\" fills the frame anyway, soft"]
    return "cover", [f"the photo is small for the frame ({size[0]}x{size[1]}): \"cover\" enlarges it x{out[0] / w:.1f} "
                     f"and it will look soft; a larger original, or no \"fit\" (it is then shown whole)"]


def _place(cx, cy, w, h, size):
    """A w x h window centered on (cx, cy) as far as the photo allows."""
    return (min(max(cx - w / 2, 0.0), size[0] - w), min(max(cy - h / 2, 0.0), size[1] - h), w, h)


def plan(size, out, n, move, roi, fit="cover"):
    """The path of a photo shot with an ROI ([x0, y0, x1, y1], parts of the upright photo) -> {"kind", "move", "size",
    "out", "n", "start", "end", "box", "warnings"}; None without an ROI or on a contained photo (the motion as before).
    Raises PhotoError when the ROI cannot stay in frame."""
    if roi is None or fit == "contain":
        return None
    sw, sh = size
    a = out[0] / out[1]
    box = (roi[0] * sw, roi[1] * sh, roi[2] * sw, roi[3] * sh)
    bw, bh = box[2] - box[0], box[3] - box[1]
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    fw, fh = full_frame(size, out)
    move = move or "none"
    warns = []
    base = {"move": move, "size": (sw, sh), "out": tuple(out), "n": n, "box": box, "warnings": warns}

    def too_big(what):
        return PhotoError(f"the ROI is {bw:.0f}x{bh:.0f} px and the whole {out[0]}x{out[1]} frame of this {sw}x{sh} "
                          f"photo only {fw:.0f}x{fh:.0f} px: {what}. A pan (\"move\": \"pan\") travels along a wide "
                          f"ROI, \"fit\": \"contain\" shows the whole photo, or give a smaller ROI")

    if move == "pan":
        w, h = fw, fh
        if sw - w < PAN_MIN * w:  # a photo as narrow as the frame: the usual pan's zoom gives it room to travel
            w, h = fw / (1 + MOVE_Z), fh / (1 + MOVE_Z)
        if bh > h + 0.5:
            raise too_big("its height cannot stay in frame during a pan")
        y = min(max(cy - h / 2, 0.0), sh - h)
        m = PAN_ROOM * w
        if bw > w:  # wider than the frame (a group, a panorama): along it, end to end
            x0, x1 = box[0] - m, box[2] + m - w
        else:  # a subject that fits: it crosses the frame and stays whole in it all along (the room shrinks with it)
            lo, hi = box[2] - w, box[0]  # the windows that hold all of it
            mm = min(m, max(0.0, (hi - lo - PAN_MIN * w) / 2))  # room at the ends, but never below the least travel
            x0, x1 = lo + mm, hi - mm
        x0, x1 = (min(max(v, 0.0), sw - w) for v in (x0, x1))
        if x1 - x0 < PAN_MIN * w:
            raise PhotoError(f"the photo ({sw}x{sh}) has no room to pan along its ROI: {x1 - x0:.0f} px of travel "
                             f"for a {w:.0f} px frame; a push or a still frame, or a wider photo")
        return {**base, "kind": "pan", "start": (x0, y, w, h), "end": (x1, y, w, h)}

    if bw > fw + 0.5 or bh > fh + 0.5:
        raise too_big("it cannot stay in frame")
    start = _place(cx, cy, fw, fh, size)
    if move in ("none", "still"):
        return {**base, "kind": "still", "start": start, "end": start}
    tw = max(bw * (1 + 2 * MARGIN), bh * (1 + 2 * MARGIN) * a)  # the ROI with room around it, at the frame's aspect
    z = min(fw / tw, ZMAX, fw / out[0])  # as deep as the ROI asks, the ceiling and the pixels allow
    z = max(z, 1 + MOVE_Z)
    if fw / z + 0.5 < bw or fh / z + 0.5 < bh:  # even the usual push-in would cut the ROI: it fills the frame
        z = max(1.0, min(fw / bw, fh / bh))
        warns.append(f"the ROI fills the frame ({bw:.0f}x{bh:.0f} px of {fw:.0f}x{fh:.0f}): the {move} barely moves; a "
                     f"still frame, or a smaller ROI")
    ew, eh = fw / z, fh / z
    ex, ey, _, _ = _place(cx, cy, ew, eh, size)
    ex = min(max(ex, start[0]), start[0] + start[2] - ew)  # inside the whole frame: one straight path between them
    ey = min(max(ey, start[1]), start[1] + start[3] - eh)
    end = (ex, ey, ew, eh)
    if move == "pull":
        start, end = end, start
    return {**base, "kind": "zoom", "start": start, "end": end}


def window(p, k):
    """The window of frame k (0..n-1) of the path."""
    t = k / (p["n"] - 1) if p["n"] > 1 else 0.0
    return tuple(a + (b - a) * t for a, b in zip(p["start"], p["end"]))


def on_screen(p, k):
    """Where the ROI is on screen at frame k: (x, y, w, h) in video pixels."""
    x, y, w, h = window(p, k)
    s = p["out"][0] / w
    b = p["box"]
    return ((b[0] - x) * s, (b[1] - y) * s, (b[2] - b[0]) * s, (b[3] - b[1]) * s)


def record(p):
    """The path as captions.json keeps it (shots -> roi_path): the ROI and the first and last windows in photo pixels,
    the frames and the video size. The place on screen at any frame follows from it exactly (screen_at); two boxes on
    screen would not: the window moves in a straight line, so its scale, and the subject on screen, do not."""
    r2 = lambda v: [round(float(x), 3) for x in v]  # noqa: E731
    return {"kind": p["kind"], "roi": r2(p["box"]), "from": r2(p["start"]), "to": r2(p["end"]), "n": p["n"],
            "size": list(p["size"]), "out": list(p["out"])}


def screen_at(r, t):
    """Where the ROI of a recorded path (record) is on screen at the part t (0..1) of its shot: (x, y, w, h)."""
    p = {"kind": r["kind"], "box": tuple(r["roi"]), "start": tuple(r["from"]), "end": tuple(r["to"]), "n": r["n"],
         "size": tuple(r["size"]), "out": tuple(r["out"])}
    k = min(r["n"] - 1, max(0, int(t * r["n"])))
    return on_screen(p, k)


def check(p):
    """The whole path, frame by frame: the ROI (for a pan its height) in every window, every window in the photo.
    -> [problem]; plan() builds paths that pass, this is the proof for the shot's record."""
    out, (sw, sh), b = [], p["size"], p["box"]
    for k in range(p["n"]):
        x, y, w, h = window(p, k)
        if x < -0.5 or y < -0.5 or x + w > sw + 0.5 or y + h > sh + 0.5:
            out.append(f"frame {k}: the window leaves the photo")
        across = p["kind"] != "pan" or b[2] - b[0] <= w  # a pan along a wide ROI keeps only its height in frame
        if b[1] < y - 0.5 or b[3] > y + h + 0.5 or across and (b[0] < x - 0.5 or b[2] > x + w + 0.5):
            out.append(f"frame {k}: the ROI leaves the frame")
        if out:
            break
    return out
