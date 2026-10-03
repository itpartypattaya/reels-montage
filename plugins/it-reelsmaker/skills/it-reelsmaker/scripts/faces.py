# -*- coding: utf-8 -*-
"""Faces in frame (YuNet model): where the head is, by measurement, not by eye. For subtitles, cards, the hook, end
cards and memes.

The skill's rule "no text on a face, chin above the subtitles" is checked here:
  scan   - faces across the whole rough cut (or any video) every 0.25 s -> edit/<id>/faces.json (1080x1920 coordinates);
  zones  - per span: where the head is, how much room there is in the "headroom" zone (above the head) and the "chest"
           zone (between the chin and the subtitles), at the sides, and whether the chin runs into the subtitles, with
           the camera plan applied (--cam z,cx,cy);
  check  - whether a given card / hook / end card (x,y,w,h) covers a face in a given interval;
  audit  - the finished render (after camera and graphics): faces against the subtitle band (where speech is heard and
           no scene hides the subtitles), the keep_clear zones (cards, hook, CTA, registered by visual_plan.py
           keep-clear; designed scenes overlay/split/window by visual_plan.py export, and ready scenes are also read
           straight from the plan) and memes; the top of the head cut off by the frame edge.

    python scripts/faces.py scan edit/<id> [--video <file>] [--step 0.25] [--geometry auto|cover|source] [--frame x,y,w,h]
    python scripts/faces.py zones edit/<id> [--cam 1.2,540,990] [--sub 1250,1430] [--frame x,y,w,h]
    python scripts/faces.py check edit/<id> --box 60,300,760,300 --from 3.7 --to 9.6 [--cam 1.1,540,1000] [--what "hook"] [--frame ...]
    python scripts/faces.py audit out/<render>.mp4 --edit edit/<id> [--sub 1250,1430]       # step 9, before showing the person
    any command: --raw - without the false-face filter; --model <file> - the YuNet model

False "faces": YuNet sometimes sees a face in knees, hands or clothing folds, most often in the subtitle zone. This is
not a flaw in the shot: such boxes are discarded by the plausibility filter (filter_faces) on scan and when reading
older faces.json files; they are kept in samples[].rejected with a reason and never reach the zones, the audit or the
memes. --raw shows them without the filter.

Model: face_detection_yunet_2023mar.onnx from the opencv_zoo project on GitHub (opencv/opencv_zoo,
models/face_detection_yunet/, 232,589 bytes). The plugin does not download it: download it yourself, keep it outside
the plugin folder and pass its path with --model, the REELS_FACE_MODEL environment variable or "face_model" in
it-reelsmaker.json (a relative path there is relative to the project folder).
OpenCV 4.8 or newer in the Python that runs this script: pip install opencv-python-headless.
No model or no OpenCV: the commands say so and exit with code 0; faces are then checked by eye on frames.
Remotion camera: screen = (x - cx)*z + 540, (y - cy)*z + 960 (references/faces.md, section 2).

A horizontal source in the "framed" format (references/techniques.md): final.mp4 stays 1920x1080, and a centered 9:16
cover would give coordinates that are not on screen and lose a second speaker at the edge. So scan measures such a
video IN ITS SOURCE GEOMETRY (--geometry auto: horizontal -> source, otherwise cover as before) and writes
"geometry": "source", the source "w"/"h" and the "frame" window to faces.json (FRAME by default: a 1030x1240 window at
(25, 340)). load() returns the boxes already in the window's screen coordinates: the video is a cover in the window,
centered; the camera works relative to the window, and the window center is (540, 960), so the formula is the same
(cx, cy in screen coordinates). zones/check clip faces to the window (beyond its edge a face is not visible); --frame
sets another window.
"""
import argparse, importlib.util, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import edit_dir, load_json, probe, project_root, project_settings, run, save_json, utf8_stdio, warn

W, H = 1080, 1920
MODEL = None         # --model; otherwise REELS_FACE_MODEL; otherwise it-reelsmaker.json -> face_model (model_path())
MODEL_FILE = "face_detection_yunet_2023mar.onnx"
MODEL_HELP = (f"download {MODEL_FILE} yourself from the opencv_zoo project on GitHub (opencv/opencv_zoo, folder "
              f"models/face_detection_yunet/; direct file: https://media.githubusercontent.com/media/opencv/opencv_zoo/"
              f"main/models/face_detection_yunet/{MODEL_FILE}), keep it outside the plugin folder and pass its path: "
              f"--model <file>, the REELS_FACE_MODEL environment variable or \"face_model\" in it-reelsmaker.json")
MARGIN = 60          # margin around a face for any graphics
UI_TOP, UI_BOTTOM, UI_RIGHT = 220, 420, 120
SUB = (1290, 1400)   # default subtitle band (top 1290, card about 100 px); for your video pass --sub top,bottom
SUB_MAX_TOP = 1390   # never lower the subtitles below this: the bottom 420 px is the UI zone
FRAME = (25, 340, 1030, 1240)  # the "framed" window for a horizontal source (references/techniques.md), x, y, w, h
SRC_LONG = 960       # measuring in source geometry: the long side of the frame for YuNet (like 540x960 for vertical)

# False-face filter. Measured on a seated monologue (246 samples): a real face has score 0.94-0.95, h/w about 1.37; a
# false one on knees and hands has score 0.60-0.76, h/w 0.81-0.96, twice as wide as the face and right below the chin.
# A confident face (>= STRONG) is never discarded; a weak one only if it is below a face of the same person or two
# indirect signs agree (false_reason).
STRONG = 0.85
MIN_ASPECT = 1.05    # a YuNet face box is taller than wide (1.2-1.5); "square" or "landscape" means knees, hands, cloth
SIZE_RANGE = (0.35, 1.8)  # width relative to the median of the video's confident faces (camera zoom gives up to x1.3)
LOCAL_S = 2.0       # size comparison window, s: the camera plan and B-roll change the face size
FILTER_V = 5         # 2: signs combined, "below a face" with a horizontal check, local median; 3: "below the chin" sign;
                     # 4: far below a face and smaller than it; 5: "appeared once" up to score 0.8

DETECT = r"""
import cv2, json, sys
d = cv2.FaceDetectorYN_create(sys.argv[1], '', (320, 320), float(sys.argv[2]))
out = []
for p in json.load(sys.stdin):
    im = cv2.imread(p)
    if im is None:
        out.append([]); continue
    h, w = im.shape[:2]
    d.setInputSize((w, h))
    _, f = d.detect(im)
    out.append([[float(v) for v in r[:4]] + [float(r[14])] for r in (f if f is not None else [])])
print(json.dumps(out))
"""


def model_path():
    """The YuNet model file: --model, else REELS_FACE_MODEL, else it-reelsmaker.json -> face_model (relative to the
    project folder). None: not set. An unexpanded ${...} value (a plugin setting left empty) counts as not set."""
    for v in (MODEL, os.environ.get("REELS_FACE_MODEL")):
        if v and not str(v).startswith("${"):
            return Path(v).expanduser().resolve()
    v = project_settings().get("face_model")
    if v and not str(v).startswith("${"):
        p = Path(v).expanduser()
        return p if p.is_absolute() else (project_root() / p).resolve()
    return None


def available():
    m = model_path()
    if not m:
        return False, "no face model is set: " + MODEL_HELP
    if not m.is_file():
        return False, f"no model file {m}: " + MODEL_HELP
    if importlib.util.find_spec("cv2") is None:
        return False, (f"OpenCV is not installed for this Python ({sys.executable}); install it: "
                       f"pip install opencv-python-headless")
    return True, ""


def detect(paths, scale=1.0, thr=0.6):
    """Faces in images -> [[ [x,y,w,h,score], ... ] per image], coordinates x scale. None: the detector is unavailable."""
    ok, why = available()
    if not ok:
        warn(f"face detection is unavailable: {why}")
        return None
    res = []
    for k in range(0, len(paths), 400):  # bounded detector output; paths travel through stdin
        chunk = [str(p) for p in paths[k:k + 400]]
        r = subprocess.run([sys.executable, "-c", DETECT, str(model_path()), str(thr)],
                           input=json.dumps(chunk), capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            warn("OpenCV did not run (OpenCV 4.8 or newer is needed for this model): "
                 + (r.stderr.strip().splitlines() or ["?"])[-1][:200])
            return None
        res += json.loads(r.stdout.strip().splitlines()[-1])
    return [[[round(v * scale) for v in f[:4]] + [round(f[4], 2)] for f in fr] for fr in res]


def grab(video, times, outdir, width=540):
    """Video frames at the given times, fitted into a 9:16 vertical (cover), `width` wide."""
    outdir.mkdir(parents=True, exist_ok=True)
    h = round(width * 16 / 9)
    paths = []
    for k, t in enumerate(times):
        p = outdir / f"{k:05d}.png"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
             "-vf", f"scale={width}:{h}:force_original_aspect_ratio=increase,crop={width}:{h}", p])
        paths.append(p)
    return paths


def grab_all(video, step, outdir, width=540, size=None):
    """Frames of the whole video every `step` seconds in one ffmpeg pass (fast). size=(w, h): the source geometry
    without a crop (horizontal "framed"), otherwise a 9:16 vertical cover `width` wide."""
    outdir.mkdir(parents=True, exist_ok=True)
    if size:
        vf = f"fps=1/{step},scale={size[0]}:{size[1]}"
    else:
        h = round(width * 16 / 9)
        vf = f"fps=1/{step},scale={width}:{h}:force_original_aspect_ratio=increase,crop={width}:{h}"
    run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf", vf, outdir / "%05d.png"])
    return sorted(outdir.glob("*.png"))


def scan_video(video, step=0.25, raw=False, geometry="auto", frame=None):
    """geometry: cover - the frame fills 1080x1920, centered (vertical rough cut, render); source - the source
    geometry (horizontal "framed" video, boxes in source pixels); auto - source for a horizontal video."""
    pr = probe(video)
    sw, sh = pr.get("w"), pr.get("h")
    if geometry == "auto":
        geometry = "source" if sw and sh and sw > sh else "cover"
    if geometry == "source" and not (sw and sh):
        sys.exit(f"could not read the size of {video}; measuring in source geometry is impossible")
    tmp = Path(tempfile.mkdtemp(prefix="faces-"))
    try:
        if geometry == "source":
            k = SRC_LONG / max(sw, sh)
            gw, gh = round(sw * k / 2) * 2, round(sh * k / 2) * 2
            paths = grab_all(video, step, tmp, size=(gw, gh))
            boxes = detect(paths, scale=sw / gw)
        else:
            paths = grab_all(video, step, tmp)
            boxes = detect(paths, scale=W / 540)
        if boxes is None:
            return None
        data = {"video": str(video), "step": step, "geometry": geometry, "w": sw if geometry == "source" else W,
                "h": sh if geometry == "source" else H, "model": model_path().name,
                "samples": [{"t": round(k * step, 3), "faces": b} for k, b in enumerate(boxes)]}
        if geometry == "source":
            data["frame"] = list(frame or FRAME)
        return data if raw else filter_faces(data)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def iou(a, b):
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / (a[2] * a[3] + b[2] * b[3] - i) if i else 0.0


def false_reason(f, strong, med, near):
    """Why a weak box is not a face; None: it is plausible. strong: confident faces in the same frame,
    med: median width of confident faces within +-LOCAL_S (None: nothing to compare with),
    near: boxes of the time-adjacent samples (None: frames are not consecutive, the "appeared once" rule is off).
    One indirect sign decides nothing: a tilted head can be "square", a face in B-roll is smaller.
    Discard if the box is right below a face of the same person, or if two of three signs agree."""
    x, y, w, h, sc = f[:5]
    if sc >= STRONG:
        return None
    cx = x + w / 2
    for s in strong:  # below the chin, center within this person's "column" (face +- half its width): hands, knees
        if y > s[1] + 0.9 * s[3] and s[0] - 0.5 * s[2] <= cx <= s[0] + 1.5 * s[2]:
            return "below a face of the same person (hands, knees)"
    for s in strong:  # far below the chin and clearly smaller than the face above: a hand or an object (26.5 s, score 0.71)
        if y > s[1] + 1.5 * s[3] and w < 0.75 * s[2]:
            return "far below a face and smaller than it (a hand or an object)"
    signs = []
    if any(y > s[1] + 0.9 * s[3] for s in strong):  # a hand held out to the side is outside the column
        signs.append("below the chin of a face in the frame")
    if w > 0 and h / w < MIN_ASPECT:
        signs.append("not face proportions")
    if med and not SIZE_RANGE[0] * med <= w <= SIZE_RANGE[1] * med:
        signs.append("size unlike the faces around it")
    if sc < 0.8 and near is not None and not any(iou(f, n) > 0.3 for n in near):  # 0.72: a sofa cushion, one sample
        signs.append("appeared in a single sample")
    return " + ".join(signs) if len(signs) >= 2 else None


def clean_frames(frames, times=None, step=None):
    """Filter for a list of frames [[x,y,w,h,score], ...] -> (kept, discarded with a reason) per frame.
    times/step: sample times (a measurement with a step); then the size is compared with the faces within +-LOCAL_S
    (a shot change or B-roll does not break the comparison) and the "appeared once" rule works. Without times (three
    widely spaced frames of a meme) the size is compared across all frames and "appeared once" is off."""
    n = len(frames)
    strong_w = [[f[2] for f in fr if f[4] >= STRONG] for fr in frames]

    def median(ws):
        ws = sorted(ws)
        return ws[len(ws) // 2] if ws else None

    glob = median([w for ws in strong_w for w in ws])
    keep, rej = [], []
    for k, fr in enumerate(frames):
        strong = [f for f in fr if f[4] >= STRONG]
        if times is not None:
            med = median([w for j in range(n) if abs(times[j] - times[k]) <= LOCAL_S for w in strong_w[j]])
            gap = 1.5 * (step or 0.25)
            adj = [j for j in (k - 1, k + 1) if 0 <= j < n and abs(times[j] - times[k]) <= gap]
            near = [f for j in adj for f in frames[j]] if adj else None
        else:
            med, near = glob, None
        kk, rr = [], []
        for f in fr:
            why = false_reason(f, strong, med, near)
            (rr.append(list(f[:5]) + [why]) if why else kk.append(list(f[:5])))
        keep.append(kk)
        rej.append(rr)
    return keep, rej


def filter_faces(data):
    """faces.json -> faces holds only plausible boxes, false ones go to rejected. A repeat call recomputes from scratch."""
    raw = [s["faces"] + [r[:5] for r in s.get("rejected", [])] for s in data["samples"]]
    keep, rej = clean_frames(raw, [s["t"] for s in data["samples"]], data.get("step", 0.25))
    for s, kk, rr in zip(data["samples"], keep, rej):
        s["faces"] = kk
        if rr:
            s["rejected"] = rr
        else:
            s.pop("rejected", None)
    data["filter"] = {"v": FILTER_V, "strong": STRONG, "rejected": sum(len(r) for r in rej)}
    return data


def unfilter(data):
    for s in data["samples"]:
        s["faces"] = s["faces"] + [r[:5] for r in s.pop("rejected", [])]
    data.pop("filter", None)
    return data


def to_screen(data, frame):
    """Boxes in source geometry (geometry: source) -> the 1080x1920 screen: the video is a cover in the frame window
    (x, y, w, h), centered. frame (0, 0, 1080, 1920) is a centered 9:16 cover, as for the cut-out in matte.py.
    Changes data in place."""
    sw, sh = data["w"], data["h"]
    fx, fy, fw, fh = frame
    k = max(fw / sw, fh / sh)
    ox, oy = fx + (fw - sw * k) / 2, fy + (fh - sh * k) / 2
    m = lambda f: [round(ox + f[0] * k), round(oy + f[1] * k), round(f[2] * k), round(f[3] * k)] + list(f[4:])
    for s in data["samples"]:
        s["faces"] = [m(f) for f in s["faces"]]
        if s.get("rejected"):
            s["rejected"] = [m(r) for r in s["rejected"]]
    data.update(geometry="screen", source={"w": sw, "h": sh}, frame=list(frame), w=W, h=H,
                map={"scale": round(k, 5), "ox": round(ox, 1), "oy": round(oy, 1)})
    return data


def load(edit, raw=False, frame=None):
    """The rough cut's faces.json in 1080x1920 screen coordinates; false faces discarded (an older file without the
    filter is filtered on reading). A measurement in source geometry is mapped into the window: frame (x, y, w, h)
    from the argument, else from faces.json, else FRAME. A cover measurement (vertical, older files) needs no frame."""
    data = load_json(Path(edit) / "faces.json")
    if not data or "samples" not in data:
        return data
    if raw:
        unfilter(data)
    elif data.get("filter", {}).get("v") != FILTER_V:
        filter_faces(data)  # the filter does not depend on scale: compute in the file's coordinates
    if data.get("geometry") == "source":
        to_screen(data, frame or data.get("frame") or FRAME)
    return data


def window(data, frame=None):
    """The window that clips faces on screen: --frame, else the window of a source-geometry measurement; None: the
    whole frame."""
    fr = frame or (data or {}).get("frame")
    return list(fr) if fr else None


def clip(b, fr):
    """The part of box b (x, y, w, h) visible in window fr; None: the face is entirely beyond the window edge."""
    if not fr:
        return b
    x0, y0 = max(b[0], fr[0]), max(b[1], fr[1])
    x1, y1 = min(b[0] + b[2], fr[0] + fr[2]), min(b[1] + b[3], fr[1] + fr[3])
    return [x0, y0, x1 - x0, y1 - y0] if x1 > x0 and y1 > y0 else None


def rejected_summary(data):
    """A line "N discarded (reason: k, ...), t...-t..." for reports."""
    rs = [(s["t"], r[5]) for s in data["samples"] for r in s.get("rejected", [])]
    if not rs:
        return ""
    by = {}
    for _, why in rs:
        by[why] = by.get(why, 0) + 1
    return (f"discarded false \"faces\": {len(rs)} ({'; '.join(f'{k}: {v}' for k, v in by.items())}), "
            f"{min(t for t, _ in rs):.2f}-{max(t for t, _ in rs):.2f} s")


def between(data, t0, t1):
    """All faces (x,y,w,h) in the interval [t0, t1] from the measurement; includes the nearest samples at the edges."""
    if not data:
        return []
    st = data.get("step", 0.25)
    return [f[:4] for s in data["samples"] if t0 - st <= s["t"] <= t1 + st for f in s["faces"]]


def union(boxes):
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
    return [x0, y0, x1 - x0, y1 - y0]


def cam_box(b, cam, center=(540, 960)):
    """A face from the rough cut -> the screen after the virtual camera {z, cx, cy}. center: the center of the camera
    window (the whole frame and the "framed" window FRAME are both (540, 960); for your own --frame, its center)."""
    if not cam:
        return b
    z, cx, cy = cam
    return [round((b[0] - cx) * z + center[0]), round((b[1] - cy) * z + center[1]), round(b[2] * z), round(b[3] * z)]


def frame_center(fr):
    return (fr[0] + fr[2] / 2, fr[1] + fr[3] / 2) if fr else (540, 960)


def screen_faces(boxes, cam, fr):
    """Boxes (x, y, w, h) -> screen: the camera relative to the window, then clipped to the window (a face beyond the
    edge is not visible)."""
    out = [clip(cam_box(b[:4], cam, frame_center(fr)), fr) for b in boxes]
    return [b for b in out if b]


def inter(a, b):
    return min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1])


def grow(b, m):
    return [b[0] - m, b[1] - m, b[2] + 2 * m, b[3] + 2 * m]


def parse_box(s):
    return [int(float(v)) for v in s.split(",")]


def parse_cam(s):
    return [float(v) for v in s.split(",")] if s else None


# --- Commands --------------------------------------------------------------------------------------------

def cmd_scan(a):
    e = edit_dir(a.edit)
    video = Path(a.video) if a.video else e / "final.mp4"
    data = scan_video(video, a.step, a.raw, a.geometry, parse_box(a.frame) if a.frame else None)
    if data is None:
        print("faces not measured (no model or OpenCV): check faces on frames by eye")
        return
    save_json(e / "faces.json", data)
    n = sum(1 for s in data["samples"] if s["faces"])
    many = sum(1 for s in data["samples"] if len(s["faces"]) > 1)
    print(f"{e / 'faces.json'}: {len(data['samples'])} samples every {a.step} s, a face in {n}"
          + (f", two or more in {many}" if many else "") + (": no faces (voice-over?)" if n == 0 else ""))
    if data["geometry"] == "source":
        print(f"geometry: source {data['w']}x{data['h']} (horizontal \"framed\"), window on screen {data['frame']}; "
              f"zones/check/visual_plan read the boxes already in the window's screen coordinates")
    if rejected_summary(data):
        print(rejected_summary(data) + ": not a flaw in the shot, they don't go into zones or the audit "
                                       "(faces.json -> rejected)")


def segments_of(e):
    plan = load_json(e / "visual_plan.json")
    if plan:
        return [(g["id"], g["start"], g["end"], g["text"]) for g in plan["segments"]]
    cap = load_json(e / "captions.json", {})
    return [(f"k{g['i']:02d}", g["out_start"], g["out_start"] + g["out_dur"], g.get("beat", "")) for g in cap.get("segments", [])]


def zone_report(f, sub, fr=None):
    """Free zones of the frame for face f (camera already applied). fr: the "framed" window; the headroom and the sides
    are computed inside it."""
    if not f:
        top = max(UI_TOP + 30, fr[1]) if fr else UI_TOP + 30
        return {"face": None, "ceiling": [top, sub[0] - 40], "chest": None, "left": 960, "right": 960, "sub_ok": True}
    top = max(UI_TOP + 30, fr[1]) if fr else UI_TOP + 30
    lft, rgt = (fr[0], min(W - UI_RIGHT, fr[0] + fr[2])) if fr else (40, W - UI_RIGHT)
    fx0, fy0, fx1, fy1 = f[0] - MARGIN, f[1] - MARGIN, f[0] + f[2] + MARGIN, f[1] + f[3] + MARGIN
    ceil = [top, fy0] if fy0 - top >= 120 else None
    chest = [fy1, sub[0] - 20] if sub[0] - 20 - fy1 >= 120 else None
    return {"face": f, "ceiling": ceil, "chest": chest, "left": max(0, fx0 - lft), "right": max(0, rgt - fx1),
            "sub_ok": f[1] + f[3] + MARGIN // 2 <= sub[0], "cut_top": f[1] < (fr[1] if fr else 0)}


def cmd_zones(a):
    e = edit_dir(a.edit)
    frame = parse_box(a.frame) if a.frame else None
    data = load(e, a.raw, frame)
    if not data:
        sys.exit(f"no {e / 'faces.json'}; first run faces.py scan {a.edit}")
    sub = tuple(parse_box(a.sub)) if a.sub else SUB
    cam = parse_cam(a.cam)
    fr = window(data, frame)
    if fr:
        print(f"\"framed\" window {fr}: faces are clipped to the window, the camera is relative to its center")
    out = []
    if not a.raw and rejected_summary(data):
        print(rejected_summary(data) + "\n")
    print(f"{'span':<8} {'time':<13} {'face (x,y,w,h)':<22} {'headroom y':<12} {'chest y':<12} {'left':>6} {'right':>7}  subtitles")
    for sid, t0, t1, text in segments_of(e):
        fs = screen_faces(between(data, t0, t1), cam, fr)
        f = union(fs)
        z = zone_report(f, sub, fr)
        out.append({"id": sid, "start": t0, "end": t1, **z})
        ce = f"{z['ceiling'][0]}-{z['ceiling'][1]}" if z["ceiling"] else "none"
        ch = f"{z['chest'][0]}-{z['chest'][1]}" if z["chest"] else "none"
        need = f[1] + f[3] + MARGIN // 2 if f else 0
        flag = "ok" if z["sub_ok"] else (
            f"chin {f[1] + f[3]}: lower the subtitles to y >= {need}" if need <= SUB_MAX_TOP else
            f"chin {f[1] + f[3]}: no room for subtitles; a wider shot (smaller z) or camera cy +{need - SUB_MAX_TOP}")
        if z.get("cut_top"):
            flag += "; top of the head beyond the edge" + (" of the window" if fr else "")
        print(f"{sid:<8} {t0:5.2f}-{t1:5.2f}  {str(f) if f else '-':<22} {ce:<12} {ch:<12} {z['left']:>6} {z['right']:>7}  {flag}")
    save_json(e / "faces_zones.json", {"cam": cam, "sub": sub, "margin": MARGIN, "frame": fr, "segments": out})
    print(f"\nzones: {e / 'faces_zones.json'}. \"Headroom\": hook and cards above the head; \"chest\": between the chin "
          f"and the subtitles (needs >= 120 px); with a {MARGIN} px margin from the face. Camera: --cam z,cx,cy of the "
          f"span's shot size.")


def cmd_check(a):
    e = edit_dir(a.edit)
    frame = parse_box(a.frame) if a.frame else None
    data = load(e, a.raw, frame)
    if not data:
        sys.exit(f"no {e / 'faces.json'}; first run faces.py scan {a.edit}")
    box = parse_box(a.box)
    cam = parse_cam(a.cam)
    fr = window(data, frame)
    hits = [s["t"] for s in data["samples"] if a.start - 1e-6 <= s["t"] <= a.end + 1e-6
            for f in screen_faces(s["faces"], cam, fr) if inter(box, grow(f, MARGIN))]
    if hits:
        print(f"✗ {a.what or 'graphics'} {box} covers a face: {min(hits):.2f}-{max(hits):.2f} s ({len(hits)} samples)")
        sys.exit(1)
    print(f"ok: {a.what or 'graphics'} {box} does not touch a face (margin {MARGIN} px) in {a.start:.2f}-{a.end:.2f} s")


def audit_zones(plan):
    """What the audit checks against faces from the plan: keep_clear (cards + overlay/split/window scenes, written by
    visual_plan.py export; if export has not run yet, ready scenes are taken from the plan) and the windows where scenes
    hide the subtitles (split/full/slogan/hide_subtitles), where "a face in the subtitle band" is not an error.
    -> (keep, hidden)."""
    from visual_plan import hides_subtitles, scene_keep_entries
    keep = list(plan.get("keep_clear", []))
    have = {k.get("scene") for k in keep if k.get("scene")}
    keep += [k for k in scene_keep_entries(plan) if k["scene"] not in have]
    hidden = [(i["start"], i["start"] + i["dur"]) for i in plan.get("inserts", [])
              if i.get("kind") == "scene" and i.get("status") == "ready" and i.get("type") != "cover" and hides_subtitles(i)]
    return keep, hidden


def cmd_audit(a):
    """The finished render: faces after the camera against subtitles, cards and scenes (keep_clear) and memes."""
    e = edit_dir(a.edit)
    data = scan_video(Path(a.render), a.step, a.raw, geometry="cover")  # a 1080x1920 render is the screen itself
    if data is None:
        print("face audit skipped (no model or OpenCV): check still frames by eye")
        return
    save_json(e / "faces_render.json", data)
    sub = tuple(parse_box(a.sub)) if a.sub else SUB
    cap = load_json(e / "captions.json", {})
    plan = load_json(e / "visual_plan.json", {}) or {}
    spoken = [(w["start"], w["end"]) for w in cap.get("words", [])]
    keep, hidden = audit_zones(plan)
    memes = [i for i in plan.get("inserts", []) if i.get("kind") == "meme" and i.get("box") and i.get("status") == "ready"]
    issues = {}

    def add(kind, t):
        issues.setdefault(kind, []).append(t)

    for s in data["samples"]:
        t = s["t"]
        for f in s["faces"]:
            fb = f[:4]
            talking = any(a0 - 0.1 <= t <= a1 + 0.3 for a0, a1 in spoken)
            subs_on = not any(h0 <= t < h1 for h0, h1 in hidden)  # a scene hid the subtitles (split/full/slogan)
            if talking and subs_on and not a.no_subs and inter(fb, [0, sub[0], W, sub[1] - sub[0]]):
                add("face in the subtitle band (chin below their top)", t)
            for k in keep:
                if k["start"] <= t <= k["end"] and inter(k["box"], grow(fb, MARGIN // 2)):
                    add(f"\"{k.get('what', 'graphics')}\" on a face", t)
            for m in memes:
                if m["start"] <= t <= m["start"] + m["dur"] and inter(m["box"], grow(fb, MARGIN // 2)):
                    add(f"meme {m['id']} on a face", t)
            if fb[1] < 0:
                add("top of the head cut off by the frame edge", t)
    skipped = rejected_summary(data)
    if skipped:
        print(skipped + ": skipped, these are not faces (see the frames in faces_render.json -> rejected)")
    if not issues:
        print(f"face audit: {len(data['samples'])} frames every {a.step} s, no overlaps (subtitles, keep_clear cards: "
              f"{len(keep)}, memes: {len(memes)})")
        return
    for kind, ts in issues.items():
        spans, cur = [], [ts[0], ts[0]]
        for t in ts[1:]:
            if t - cur[1] <= a.step * 1.5:
                cur[1] = t
            else:
                spans.append(cur)
                cur = [t, t]
        spans.append(cur)
        print(f"✗ {kind}: " + ", ".join(f"{x:.2f}-{y:.2f} s" if y > x else f"{x:.2f} s" for x, y in spans))
    print("the audit does not see cards that were not registered with visual_plan.py keep-clear: check those on stills")
    sys.exit(1)


def main():
    global MODEL
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    FR = "the \"framed\" window on screen x,y,w,h (default 25,340,1030,1240 for a horizontal source)"
    p = sub.add_parser("scan"); p.add_argument("edit"); p.add_argument("--video"); p.add_argument("--step", type=float, default=0.25)
    p.add_argument("--geometry", choices=["auto", "cover", "source"], default="auto",
                   help="auto: a horizontal video is measured in its source geometry (source), otherwise cover 9:16")
    p.add_argument("--frame", help=FR); p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("zones"); p.add_argument("edit"); p.add_argument("--cam"); p.add_argument("--sub")
    p.add_argument("--frame", help=FR); p.set_defaults(fn=cmd_zones)
    p = sub.add_parser("check"); p.add_argument("edit"); p.add_argument("--box", required=True)  # noqa
    p.add_argument("--from", dest="start", type=float, required=True); p.add_argument("--to", dest="end", type=float, required=True)
    p.add_argument("--cam"); p.add_argument("--what"); p.add_argument("--frame", help=FR); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("audit"); p.add_argument("render"); p.add_argument("--edit", required=True)
    p.add_argument("--sub"); p.add_argument("--step", type=float, default=0.25); p.add_argument("--no-subs", action="store_true")
    p.set_defaults(fn=cmd_audit)
    for name, sp in sub.choices.items():
        sp.add_argument("--raw", action="store_true", help="without the false-face filter (debugging)")
        sp.add_argument("--model", help=f"the YuNet model file ({MODEL_FILE}); default: REELS_FACE_MODEL, "
                                        f"then face_model in it-reelsmaker.json")
    a = ap.parse_args()
    MODEL = a.model or None
    a.fn(a)


if __name__ == "__main__":
    main()
