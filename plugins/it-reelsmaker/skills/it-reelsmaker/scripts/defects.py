# -*- coding: utf-8 -*-
"""Picture defects on a stretch where the sound is good: the speaker turned away or looked down, the face lost, the
face blurred (motion, focus), someone else in the frame. Found on the rough cut, so the plan can cover them (a full
scene, a code scene, a replacing B-roll, a cutaway) or accept them knowingly (visual_plan.py accept).

    python scripts/defects.py edit/<id> [--video final.mp4] [--step 0.1] [--model <yunet.onnx>]

When: step 6, after the rough cut and `faces.py scan`; again after a re-cut. The plan (step 7a) and its check read
edit/<id>/faces_defects.json: an insert that covers a defect says so (`visual_plan.py add … --covers d03`).

How:
  1. Frames every --step (0.1 s) in one ffmpeg pass, the same YuNet model as faces.py, which also gives five points of
     each face (eyes, nose tip, mouth corners) and, here, the sharpness of the face (variance of the Laplacian of the
     face resized to 96 px wide). False faces (knees, hands) are dropped by faces.py's filter.
  2. The speaker's face is the one nearest the speaker's usual place (per source of the cut); the speaker's own norm,
     per source (another camera has another angle): medians of the head turn (nose against the middle of the eyes,
     in eye distances), of the head tilt, of the eye distance (in face widths) and of the sharpness. A source whose
     median eye distance is under FACING of the face width (a profile interview, a side view, a staged scene) does
     not face the camera: turns are not checked there; when no source faces the camera nothing is checked.
  3. A defect is a run of samples (a hole up to GAP_S does not break it), at least its kind's minimum long:
       turned    the head turned or tilted down: more than TURN eye distances off the speaker's median, or the eyes
                 closer than NARROW of their median distance (0.4 s);
       blur      the face (not turned) less than BLUR of its median sharpness (0.5 s);
       lost      no face where the speaker is, on camera before and after it (0.3 s; longer than 4 s is a stretch
                 without the speaker, reported as such);
       stranger  more sure faces (score >= SURE) than the video usually has (0.3 s).
     A video with a face in under 30 % of its samples has no speaker on camera: nothing to check.
     Calibrated on 12 videos (rough cuts and raw takes, 17 min checked by eye) and on copies with blur, a covered face
     and a pasted second face: 17 of 21 defects seen by eye found, all 42 injected and 11 of 12 mild blurs, no false
     alarm. Missed: a mild turn (under about 25 degrees), the head thrown back, a sideways roll; eyes looking down at
     notes with the head still are not seen at all (YuNet has no iris points), nor a blink.
  4. edit/<id>/faces_defects.json: d01, d02… with kind, start, end (seconds of the rough cut), what was measured and
     the words heard under it. A blink is not a defect.

No model or OpenCV: says so and exits 0, as faces.py does.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import edit_dir, load_json, probe, save_json, utf8_stdio, warn  # noqa: E402

STEP = 0.1
TURN = 0.3  # eye distances off the speaker's median: a head turned (nose sideways) or tilted down
NARROW = 0.8  # the eyes closer than this share of the speaker's median eye distance: the head turned sideways
BLUR = 0.5  # share of the median face sharpness
MIN_S = {"turned": 0.4, "blur": 0.5, "lost": 0.3, "stranger": 0.3}
GAP_S = 0.2  # a hole this long inside a run does not break it (noise of one or two samples)
LOST_MAX_S = 4.0  # a longer stretch without a face is a stretch without the speaker (cutaway, voice-over), not a slip
ON_CAMERA = 0.3  # a face in fewer samples than this: no speaker on camera
FACING = 0.35  # median eye distance in face widths: a frontal face has 0.42-0.50, a profile or side view under 0.3
NEAR = 2.0  # face widths from the speaker's usual place: a face farther away is someone else
SURE = 0.8  # YuNet score: only faces this sure count as someone else in the frame (a hand at the edge scores 0.6-0.7)
SHARP_W = 96  # px: faces are resized to this width before the sharpness is measured

DETECT = r"""
import cv2, json, sys
d = cv2.FaceDetectorYN_create(sys.argv[1], '', (320, 320), float(sys.argv[2]))
W = int(sys.argv[3])
out = []
for p in json.load(sys.stdin):
    im = cv2.imread(p)
    if im is None:
        out.append([]); continue
    h, w = im.shape[:2]
    d.setInputSize((w, h))
    _, f = d.detect(im)
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    fr = []
    for r in (f if f is not None else []):
        x, y, bw, bh = [int(round(v)) for v in r[:4]]
        x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + bw), min(h, y + bh)
        sharp = -1.0
        if x1 - x0 >= 8 and y1 - y0 >= 8:
            c = g[y0:y1, x0:x1]
            c = cv2.resize(c, (W, max(8, round(W * (y1 - y0) / (x1 - x0)))))
            sharp = float(cv2.Laplacian(c, cv2.CV_64F).var())
        fr.append([float(v) for v in r[:4]] + [float(r[14])] + [float(v) for v in r[4:14]] + [sharp])
    out.append(fr)
print(json.dumps(out))
"""


def detect_points(paths, thr=0.6):
    """Faces with points -> per image [[x, y, w, h, score, rex, rey, lex, ley, nx, ny, rmx, rmy, lmx, lmy, sharp]]."""
    import faces as fc
    ok, why = fc.available()
    if not ok:
        warn(f"face detection is unavailable: {why}")
        return None
    res = []
    for k in range(0, len(paths), 400):
        chunk = [str(p) for p in paths[k:k + 400]]
        r = subprocess.run([sys.executable, "-c", DETECT, str(fc.model_path()), str(thr), str(SHARP_W)],
                           input=json.dumps(chunk), capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            warn("OpenCV did not run: " + (r.stderr.strip().splitlines() or ["?"])[-1][:200])
            return None
        res += json.loads(r.stdout.strip().splitlines()[-1])
    return res


def scan(video, step=STEP):
    """-> {"step", "samples": [{"t", "faces": [[…16 values]]}]} with false faces dropped, or None without a model."""
    import faces as fc
    pr = probe(video)
    sw, sh = pr.get("w"), pr.get("h")
    tmp = Path(tempfile.mkdtemp(prefix="defects-"))
    try:
        if sw and sh and sw > sh:  # a horizontal source: its own geometry, long side 960 (faces.py SRC_LONG)
            k = fc.SRC_LONG / max(sw, sh)
            gw = round(sw * k / 2) * 2
            paths = fc.grab_all(video, step, tmp, size=(gw, round(sh * k / 2) * 2))
        else:
            gw = 540  # faces.py grab_all: a 540x960 cover
            paths = fc.grab_all(video, step, tmp)
        raw = detect_points(paths)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if raw is None:
        return None
    times = [round(k * step, 3) for k in range(len(raw))]
    keep, _ = fc.clean_frames([[f[:5] for f in fr] for fr in raw], times, step, width=gw)
    samples = []
    for t, fr, kk in zip(times, raw, keep):
        kept = [f for f in fr if [round(v, 6) for v in f[:5]] in [[round(v, 6) for v in q[:5]] for q in kk]]
        samples.append({"t": t, "faces": kept})
    return {"step": step, "samples": samples}


def pose(f):
    """(turn, tilt, eyes) of a face: the nose tip against the middle of the eyes, in eye distances, and the eye distance
    in face widths (0.42-0.50 for a frontal face, less as the head turns). turn and tilt are None when the eyes are too
    close to measure them (a profile)."""
    rex, rey, lex, ley, nx, ny = f[5:11]
    iod = ((lex - rex) ** 2 + (ley - rey) ** 2) ** 0.5
    eyes = iod / f[2] if f[2] > 0 else 0.0
    if iod < 4:
        return None, None, eyes
    return (nx - (rex + lex) / 2) / iod, (ny - (rey + ley) / 2) / iod, eyes


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def source_at(segs, t):
    for g in segs:
        if g["out_start"] - 1e-6 <= t < g["out_start"] + g["out_dur"] + 1e-6:
            return g.get("source") or "main"
    return "main"


def anchors(smp, srcs):
    """The speaker's usual place per source: medians of the centre and the width of the largest face of each sample."""
    by = {}
    for s, src in zip(smp, srcs):
        if s["faces"]:
            by.setdefault(src, []).append(max(s["faces"], key=lambda g: g[2] * g[3]))
    return {src: (median([f[0] + f[2] / 2 for f in fs]), median([f[1] + f[3] / 2 for f in fs]),
                  median([f[2] for f in fs])) for src, fs in by.items()}


def speaker_face(faces, anchor):
    """The speaker's face in a sample: the one nearest the speaker's usual place and no farther than NEAR face widths
    from it (a face elsewhere is someone else; the speaker is then lost)."""
    if not faces or not anchor:
        return None
    cx, cy, w = anchor
    dist = lambda f: ((f[0] + f[2] / 2 - cx) ** 2 + (f[1] + f[3] / 2 - cy) ** 2) ** 0.5  # noqa: E731
    f = min(faces, key=dist)
    return f if dist(f) <= NEAR * w else None


def runs(flags, kind, gap):
    """[(i, j)] index runs of samples flagged `kind`; a hole of up to `gap` samples inside a run does not break it."""
    out, i, n = [], 0, len(flags)
    while i < n:
        if kind not in flags[i]:
            i += 1
            continue
        j = k = i
        while k + 1 < n:
            nxt = next((m for m in range(k + 1, min(n, k + 2 + gap)) if kind in flags[m]), None)
            if nxt is None:
                break
            j = k = nxt
        out.append((i, j))
        i = j + 1
    return out


def find(data, segs, words=(), turn=None, blur=None):
    """Samples -> defects [{id, kind, start, end, detail, words}] and a summary of the norms. turn, blur: thresholds
    (default TURN, BLUR)."""
    turn = TURN if turn is None else turn
    blur = BLUR if blur is None else blur
    smp = data["samples"]
    step = data["step"]
    seen = sum(1 for s in smp if s["faces"])
    if not smp or seen < ON_CAMERA * len(smp):
        return [], {"on_camera": False, "with_face": seen, "samples": len(smp)}
    sure = [sum(1 for f in s["faces"] if f[4] >= SURE) for s in smp]
    usual = round(median([k for k in sure if k]) or 1)
    srcs = [source_at(segs, s["t"]) for s in smp]
    anc = anchors(smp, srcs)
    rows = []
    for s, src, k in zip(smp, srcs, sure):
        f = speaker_face(s["faces"], anc.get(src))
        rows.append({"t": s["t"], "src": src, "f": f, "n": k, "pose": pose(f) if f else None,
                     "sharp": f[15] if f and f[15] >= 0 else None})
    norms = {}
    for src in sorted(set(srcs)):
        rr = [r for r in rows if r["src"] == src and r["pose"]]
        eyes = median([r["pose"][2] for r in rr])
        norms[src] = {"turn": median([r["pose"][0] for r in rr]), "tilt": median([r["pose"][1] for r in rr]),
                      "eyes": eyes, "sharp": median([r["sharp"] for r in rr]),
                      "facing": bool(eyes and eyes >= FACING)}
    base = {"usual_faces": usual, "norms": norms, "samples": len(smp), "with_face": seen}
    if not any(nm["facing"] for nm in norms.values()):  # a profile interview, a side view, a staged scene
        return [], {"on_camera": False, "facing": False, **base}
    flags = []
    for r in rows:
        nm, fl, p = norms.get(r["src"]) or {}, {}, r["pose"]
        if p and nm.get("facing"):
            if p[0] is None:
                fl["turned"] = "the eyes are not apart: a profile"
            else:
                dt, dl, ne = p[0] - nm["turn"], p[1] - nm["tilt"], p[2] / nm["eyes"]
                if abs(dt) > turn or dl > turn or ne < NARROW:
                    fl["turned"] = (f"turn {dt:+.2f}, tilt {dl:+.2f} eye distances off the median, "
                                    f"eyes {ne:.0%} as far apart")
        if "turned" not in fl and r["sharp"] is not None and nm.get("sharp") and r["sharp"] < blur * nm["sharp"]:
            fl["blur"] = f"sharpness {r['sharp'] / nm['sharp']:.0%} of the median"  # a turned face is not compared
        if r["f"] is None:
            fl["lost"] = "no face" if not r["n"] else "no face where the speaker is"
        if r["n"] > usual:
            fl["stranger"] = f"{r['n']} faces, usually {usual}"
        flags.append(fl)
    out = []
    gap = max(0, round(GAP_S / step))
    for kind in ("turned", "blur", "lost", "stranger"):
        for i, j in runs(flags, kind, gap):
            a, b = rows[i]["t"], rows[j]["t"] + step
            ok = b - a >= MIN_S[kind] - 1e-9
            note = flags[(i + j) // 2].get(kind) or flags[i][kind]
            if kind == "lost":  # a face before and after; a long one is a stretch without the speaker
                if i == 0 or j == len(rows) - 1:
                    ok = False
                elif b - a > LOST_MAX_S:
                    note = "no face for long: a stretch without the speaker (cutaway, voice-over)?"
            if ok:
                heard = " ".join(w.get("text", "") for w in words if w["start"] < b and w["end"] > a).strip()
                out.append({"kind": kind, "start": round(a, 2), "end": round(b, 2), "detail": note, "words": heard})
    out.sort(key=lambda d: d["start"])
    for k, d in enumerate(out, 1):
        d["id"] = f"d{k:02d}"
    return out, {"on_camera": True, **base}


def main():
    import faces as fc
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit")
    ap.add_argument("--video", help="default edit/<id>/final.mp4")
    ap.add_argument("--step", type=float, default=STEP)
    ap.add_argument("--model", help="the YuNet model file (as faces.py)")
    a = ap.parse_args()
    fc.MODEL = a.model or None
    e = edit_dir(a.edit)
    video = Path(a.video) if a.video else e / "final.mp4"
    if not video.is_file():
        sys.exit(f"no video {video}: make the rough cut first (cut.py)")
    data = scan(video, a.step)
    if data is None:
        print("picture defects not measured (no model or OpenCV): look at the rough cut's frames by eye")
        return
    cap = load_json(e / "captions.json", {}) or {}
    defects, info = find(data, cap.get("segments") or [], cap.get("words") or [])
    save_json(e / "faces_defects.json", {"video": str(video), "step": a.step, "model": fc.model_path().name,
                                         **info, "defects": defects})
    if not info["on_camera"]:
        if info.get("facing") is False:
            print("the speaker does not face the camera in any source (a profile interview, a side view, a staged "
                  "scene): nothing to check")
        else:
            print(f"a face in {info['with_face']} of {info['samples']} samples: no speaker on camera, nothing to check")
        return
    print(f"{e / 'faces_defects.json'}: {len(defects)} defect(s) in {info['samples']} samples every {a.step} s")
    for d in defects:
        print(f"  {d['id']}  {d['kind']:<8} {d['start']:6.2f}-{d['end']:6.2f} s  {d['detail']}"
              + (f"  «{d['words'][:50]}»" if d["words"] else ""))
    if defects:
        print("cover each one in the plan (visual_plan.py add … --covers dNN: a full or code scene, a replacing B-roll, "
              "a cutaway, entering by a cut) or accept it (visual_plan.py accept dNN --why …); references/inserts.md")


if __name__ == "__main__":
    main()
