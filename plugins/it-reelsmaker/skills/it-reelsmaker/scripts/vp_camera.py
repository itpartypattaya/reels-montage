"""The visual plan's camera: the rough cut's shots, the virtual camera at a moment, and where the subtitles
stand on screen under it. Part of visual_plan.py, with no command line
of its own: the other scripts take these names from visual_plan."""
import sys
from pathlib import Path

from reels_common import (SUB_BAND, SUB_MAX_TOP, SUB_TOP_KIT, cam_fit, framed_at, framed_source, framed_view,
                          load_json)
from vp_core import (resolve_at)


def source_files(e):
    """cut.json sources: {name: file}, so that a shot may name its source by the name or by the file."""
    doc = load_json(Path(e) / "cut.json", {}) or {}
    out = {}
    for k, v in (doc.get("sources") or {}).items():
        f = v.get("file") if isinstance(v, dict) else v
        if f:
            out[str(k)] = str(f)
    return out


def same_source(a, b, files=None):
    """A shot's "source" names a segment's source: the same path, file name or stem, or the cut.json name of that
    file (captions.json segments carry the name; T2: "source": "<file>.MOV" against segments of "front" failed
    the stage)."""
    a, b = str(a or ""), str(b or "")
    if not (a and b):
        return False

    def names(x):
        out = {x, Path(x).name, Path(x).stem}
        if files and x in files:
            out |= {files[x], Path(files[x]).name, Path(files[x]).stem}
        return out
    return bool(names(a) & names(b))


def src_to_out(src, cap, seg=None, source=None, files=None, quiet=False):
    """A source second -> the second of the finished video (captions.json segments; references/camera.md, at()).
    source: the shot's file or source name, for a cut from several cameras whose source seconds overlap."""
    pool = [g for g in cap.get("segments", []) if (seg is None or g["i"] == seg)
            and (source is None or same_source(source, g.get("source"), files))]
    if source is not None and not pool:
        sys.exit(f"camera.json: no segment of the rough cut comes from {source}")
    hit = [g for g in pool if g["src_start"] - 0.001 <= src <= g["src_end"] + 0.001]
    if not hit:
        # an edge moved by a few frames (a recut): a shot set on a segment start lands just before it; it follows
        nxt = [g for g in pool if src < g["src_start"] <= src + 0.25]
        if not nxt:
            sys.exit(f"camera.json: source second {src} was cut out")
        g = min(nxt, key=lambda x: x["src_start"])
        if not quiet:
            print(f"camera.json: source second {src} is cut out; the shot starts with the next segment ({g['src_start']})")
        return g["out_start"]
    if len(hit) > 1:
        sys.exit(f"camera.json: source second {src} is in several segments ({[g['i'] for g in hit]}): add \"source\" "
                 f"(the file) or \"seg\"")
    g = hit[0]
    return g["out_start"] + max(0.0, src - g["src_start"]) * g["out_dur"] / (g["src_end"] - g["src_start"])


def subtitles_in(e, lang):
    """captions-<lang>.json (subs.py apply) for the subtitles, checked against the current rough cut."""
    import subs
    f = e / f"captions-{lang}.json"
    doc = load_json(f)
    cap = load_json(e / "captions.json") or {}
    if not doc:
        sys.exit(f"subtitles_lang={lang}: no {f}; translate first: subs.py phrases {e} --lang {lang}, then subs.py apply")
    if doc.get("captions") != subs.fingerprint(cap):
        sys.exit(f"subtitles_lang={lang}: the rough cut changed after the translation: subs.py phrases {e} --lang {lang} "
                 f"(unchanged phrases keep their translation), translate the emptied ones, subs.py apply")
    if doc.get("translation") != subs.translation_id(load_json(subs.subs_file(e, lang))):
        sys.exit(f"subtitles_lang={lang}: the translation in subs/{lang}.json changed after {f.name} was made (or the "
                 f"last apply refused it): subs.py apply {e} --lang {lang}")
    print(f"subtitles: {lang} ({f.name})")
    return doc


def camera_shots(e, plan, cap, quiet=False):
    """edit/<id>/camera.json -> ReelKit props.camera: shots in seconds of the finished video, sorted.
    {"shots": [{"src": 12.4 | "at": "word:resume#1" | 3.2, "z": 1.1, "cx": 540, "cy": 1000, "drift": 0.03, "whip": false}]}
    src: a source second (stable when the speed changes), with "source": "cam-a.mov" (a path, file name or stem,
    or the source name of cut.json) on a cut from several files; at: a second or a word of the finished video."""
    doc = load_json(e / "camera.json", None)
    if not doc:
        return []
    shots, files = [], source_files(e)
    for k, sh in enumerate(doc.get("shots", [])):
        t = (src_to_out(float(sh["src"]), cap, sh.get("seg"), sh.get("source"), files, quiet) if "src" in sh
             else resolve_at(str(sh.get("at", 0)), plan, cap))
        z = float(sh.get("z", 1.0))
        if z < 1:
            sys.exit(f"camera.json shot {k}: z {z} < 1 would show the frame edge")
        shots.append({"t": round(t, 3), "z": z, "cx": float(sh.get("cx", 540)), "cy": float(sh.get("cy", 960)),
                      "drift": float(sh.get("drift", 0)), "whip": bool(sh.get("whip"))})
    return sorted(shots, key=lambda x: x["t"])


def plan_camera(e, plan):
    """camera.json shots for the checks (validate): [] without camera.json, or when it does not resolve (stage
    reports that)."""
    if not (Path(e) / "camera.json").is_file():
        return []
    try:
        return camera_shots(e, plan, load_json(Path(e) / "captions.json", {}) or {}, quiet=True)
    except SystemExit:
        return []


def camera_view(e, fdata=None):
    """The camera's clamp geometry (reels_common.cam_fit) for edit/<id>: in the "framed" format the window and the
    rough cut's cover in it (as faces.py maps faces and the kit draws the video); None: the whole frame."""
    fr = framed_at(e)
    if not fr:
        return None
    import faces as fc
    v = fc.view(fdata) if fdata and fdata.get("source") else None
    if v is None:
        src = framed_source(e)
        v = framed_view(fr["window"], src) if src else (fr["window"], fr["window"])
    return v


def camera_at(shots, t, end, fps=30, view=None):
    """The virtual camera (z, cx, cy) at second t, as ReelKit's cameraAt draws it: the shot's push-in (drift) grows
    over the shot, a whip blends from the previous shot over 7 frames, the window never shows past the video
    (view: the "framed" window, camera_view; None: the whole frame). None before the first shot (the frame as is)."""
    i = max((k for k, s in enumerate(shots) if s["t"] <= t + 1e-6), default=-1)
    if i < 0:
        return None

    def fit(z, cx, cy):
        return cam_fit(z, cx, cy, view)

    def shot_at(k, tt):
        s = shots[k]
        nxt = shots[k + 1]["t"] if k + 1 < len(shots) else end
        p = min(max((tt - s["t"]) / max(0.01, nxt - s["t"]), 0.0), 1.0)
        return fit(s["z"] * (1 + s.get("drift", 0) * p), s["cx"], s["cy"])

    cam = shot_at(i, t)
    p = (t - shots[i]["t"]) * fps / 7
    if not shots[i].get("whip") or i == 0 or p >= 1:
        return cam
    prev, k = shot_at(i - 1, shots[i]["t"]), 1 - (1 - max(0.0, p)) ** 3
    return tuple(a + (b - a) * k for a, b in zip(prev, cam))


def chin_on_screen(y, t, shots, view=None):
    """Where a source y lands on screen at second t: the shot's camera at its deepest drift (camera.md formula), clamped
    like the kit (view: the "framed" window, whose center the camera works around)."""
    s = next((x for x in reversed(shots) if x["t"] <= t + 1e-6), None)
    if not s:
        return y
    z, _, cy = cam_fit(s["z"] * (1 + s["drift"]), s["cx"], s["cy"], view)
    c = view[0][1] + view[0][3] / 2 if view else 960
    return (y - cy) * z + c


def subtitle_top(e, s, cam, quiet=False):
    """The subtitles' top as the render puts it -> (top, band): below the measured chin (faces.json) through the
    camera, or allowing for the template's drift (up to x1.05 toward the frame center) without one."""
    import faces as fc
    import meme_layout as ml
    band = ml.layout(s).get("subtitles_band") or list(SUB_BAND)
    fdata = fc.load(e)
    top = SUB_TOP_KIT
    if fdata:
        geo = camera_view(e, fdata)
        # no camera: the template's drift (up to x1.05) toward the frame's center, or the framed window's (the kit's
        # fitCamera around the window center; Codex review: a custom window was scaled around y 960)
        cy = geo[0][1] + geo[0][3] / 2 if geo else 960
        boxes = [(s_["t"], b) for s_ in fdata["samples"] for b in s_["faces"]]
        # a weak box that got through the filter is still not trusted with the subtitles while confident faces exist (1789:
        # a 0.68 box on a shoulder gave a "chin" at 1939 and the top 1390; the real face's chin needed 1250)
        sure = [(t, b) for t, b in boxes if len(b) > 4 and b[4] >= fc.STRONG]
        boxes = sure or boxes
        chins = [(chin_on_screen(b[1] + b[3], t, cam, geo) if cam else (b[1] + b[3] - cy) * 1.05 + cy, t, b)
                 for t, b in boxes]
        if chins:
            low, lt, lb = max(chins, key=lambda c: c[0])
            need = round(low + fc.SUB_FACE_GAP)
            top = max(band[0], min(SUB_MAX_TOP, need))
            if not quiet:
                print(f"subtitles: top at y {top} (chin down to {round(low)} per faces.json: box "
                      f"{[round(v, 2) for v in lb[:5]]} at {lt:g} s)"
                      + (f"; WARNING: even at {SUB_MAX_TOP} the chin touches the subtitles: use a wider shot or a lower "
                         f"camera" if need > SUB_MAX_TOP else ""))
    return top, band
