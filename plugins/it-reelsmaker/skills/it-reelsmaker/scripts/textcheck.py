# -*- coding: utf-8 -*-
"""Text on the frame, measured in the browser: text cut off by the frame or by its box, two texts on top of each
other, text in the app's UI zones, text on a face. It sees whatever the composition draws, a per-video one included,
which the plan check (visual_plan.py validate) cannot.

    python scripts/textcheck.py edit/4821 [--props edit/4821/reelkit-props.json] [--remotion reels] [--comp ReelKit]
        [--step 3] [--keep-log]

When: after `visual_plan.py export … --props` (step 8), with the storyboard sheet (board.py), before the full render;
again after any fix of text or layout. Takes seconds: 15 s for a 58 s video.

How:
  1. One Remotion call over every --step-th frame (default 3 = 0.1 s): the props get `sample` (kit/Sample.tsx, kit
     1.10.0+) with probe on and media off (the rough cut, B-roll, memes and screen recordings are not drawn: text does
     not depend on them), at 1/10 scale, with --log=verbose. On each frame <TextProbe> logs the boxes of the text on
     screen in 1080x1920 pixels: its group (data-rk: sub, hook, label, endcard, scene:<id>; plus its block), opacity,
     the share left visible by the boxes that clip it.
  2. Checks, on text at least 25 % opaque, and only a problem that lasts 0.3 s or more (entrances and exits move text
     through the edges and over each other for a few frames):
       error    off the frame — more than 4 px of a box past the frame's edge;
       error    overlap — two different texts share more than 10 % of the smaller box (its core: without the top and
                bottom fifth of the line box, which run above and below the letters);
       error    on a face — a box over a measured face (faces.json, through the props' camera as the kit draws it) with a 30 px
                margin, as `faces.py audit` takes it; not where the rough cut is covered or moved (a full or split
                scene, a replacing B-roll, a cutaway meme, a presenter layer) and not on the end card;
       warning  clipped — less than 98 % of the box is visible inside the boxes that clip it;
       warning  UI zone — above y 220, below y 1500 or right of x 960 (the app's caption, buttons and likes column).
  3. Report lines `✗ kind a-b s group «text»`, edit/<id>/textcheck.json; exit code 1 on errors, and on a pass with
     frames missing from the log (a gap would hide a problem: the check is then incomplete, not passed). Faces come from the
     rough cut's faces.json (faces.py scan); without it the face check is skipped and the report says so.

The kit's own text carries data-rk groups; in a per-video composition text without one is grouped by its block, and
the composition needs <Sampled sample={p.sample}> around its content (it adds the probe).
"""
import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board as bd  # noqa: E402
from reels_common import edit_dir, load_json, save_json  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROBE = "RK_TEXT "
W, H = 1080, 1920
EDGE = 4  # px past the frame: rounding and anti-aliasing are not "off the frame"
OVERLAP = 0.10  # share of the smaller box's core
CORE = 0.2  # a line box runs above the capitals and below the baseline: overlaps are judged on the box without its top
#             and bottom fifth (kit/Sample.tsx measures `visible` the same way). A caps label 10 px above a heading
#             overlapped it by its line box, not by a letter
VISIBLE = 0.98  # share of a box left by the boxes that clip it
ALPHA = 0.25  # text fainter than this is fading in or out
MIN_RUN_S = 0.3
UI_TOP, UI_BOTTOM, UI_RIGHT = 220, 1500, 960
FACE_PX = 30  # = faces.CHECK_MARGIN, the checks' tolerance (faces.py imports cv2: read lazily there)


def parse_log(text):
    """Remotion's verbose output -> {frame: [box…]}; a box is (key, text, x, y, w, h, alpha, visible). A frame logged
    twice (Remotion echoes the browser's console) keeps its last line."""
    dec = json.JSONDecoder()
    out = {}
    for line in text.splitlines():
        i = line.find(PROBE)
        if i < 0:
            continue
        try:
            obj, _ = dec.raw_decode(line[i + len(PROBE):])
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("f"), int):
            out[obj["f"]] = [tuple(b) for b in obj.get("b") or [] if isinstance(b, list) and len(b) >= 8]
    return out


def group(key):
    return key.split("/", 1)[0] or "(no group)"


def ident(key):
    """What a problem is tracked by across frames: the subtitles are one element (each phrase is a new block, and a
    card over the subtitle band is one problem, not one per phrase); anything else is its group and block."""
    return "sub" if group(key) == "sub" else key


def area(b):
    return max(0.0, b[4]) * max(0.0, b[5])


def core(b):
    return (b[0], b[1], b[2], b[3] + CORE * b[5], b[4], (1 - 2 * CORE) * b[5])


def inter_area(a, b):
    w = min(a[2] + a[4], b[2] + b[4]) - max(a[2], b[2])
    h = min(a[3] + a[5], b[3] + b[5]) - max(a[3], b[3])
    return w * h if w > 0 and h > 0 else 0.0


def hits(rect, b):
    x, y, w, h = rect
    return min(x + w, b[2] + b[4]) > max(x, b[2]) and min(y + h, b[3] + b[5]) > max(y, b[3])


def face_source(e, plan, props, fps):
    """-> faces_at(t) giving the screen face boxes at second t (the rough cut's faces through the camera), or None
    without faces.json. The camera and the framed window are the props' own (what the checked render will draw:
    ReelKit's Footage reads props.camera, not camera.json). The samples come from t's own camera angle: next to a
    change of source the nearest sample on the other side is not used (review: a face of the other angle, up to a
    0.25 s step away, gave "on a face" where that face is not on screen)."""
    import faces as fc
    import visual_plan as vp
    fdata = fc.load(e)
    if not fdata or not fdata.get("samples"):
        return None
    shots = sorted(props.get("camera") or [], key=lambda x: x["t"])
    view = vp.camera_view(e, fdata) if props.get("framed") else None
    win = fc.window(fdata)
    dur = float(props["captions"]["duration"])
    hidden = fc.covered(plan)
    cuts = sorted(g["out_start"] for p, g in zip(props["captions"].get("segments") or [],
                                                  (props["captions"].get("segments") or [])[1:])
                  if g.get("source") != p.get("source"))
    st = fdata.get("step", 0.25)

    def faces_at(t):
        if t >= dur or any(a - 1e-6 <= t <= b + 1e-6 for a, b in hidden):
            return []
        lo = max([t - st] + [c for c in cuts if c <= t + 1e-6])
        hi = min([t + st] + [c - 1e-6 for c in cuts if c > t + 1e-6])
        boxes = [f[:4] for x in fdata["samples"] if lo - 1e-6 <= x["t"] <= hi + 1e-6 for f in x["faces"]]
        cam = vp.camera_at(shots, t, dur, fps, view) if shots else None
        return [fc.grow(b, fc.CHECK_MARGIN) for b in fc.screen_faces(boxes, cam, win)]  # the checks' tolerance
    return faces_at


def frame_issues(boxes, faces):
    """One frame -> [(level, kind, subject, text, detail)]; subject identifies the same problem across frames."""
    out = []
    seen = [b for b in boxes if b[6] >= ALPHA]
    for b in seen:
        key, text, x, y, w, h, _a, vis = b[:8]
        past = max(-x, -y, x + w - W, y + h - H)
        if past > EDGE:
            out.append(("error", "off the frame", ident(key), text, f"{round(past)} px past the edge"))
        elif vis < VISIBLE:
            out.append(("warning", "clipped", ident(key), text, f"{round(vis * 100)} % visible in its box"))
        zones = [n for n, r in (("top", (0, 0, W, UI_TOP)), ("bottom", (0, UI_BOTTOM, W, H - UI_BOTTOM)),
                                ("right", (UI_RIGHT, 0, W - UI_RIGHT, H))) if hits(r, b)]
        if zones:
            out.append(("warning", "UI zone", ident(key), text, "/".join(zones)))
        if faces and any(hits(f, b) for f in faces):
            out.append(("error", "on a face", ident(key), text, f"a measured face + {FACE_PX} px"))
    for i, a in enumerate(seen):
        for b in seen[i + 1:]:
            if a[0] == b[0]:
                continue
            ca, cb = core(a), core(b)
            if inter_area(ca, cb) > OVERLAP * min(area(ca), area(cb)) > 0:
                if ident(a[0]) == ident(b[0]):  # two lines of the subtitles: their own layout
                    continue
                first, other = (a, b) if ident(a[0]) <= ident(b[0]) else (b, a)
                k1, k2, t = ident(first[0]), ident(other[0]), first[1]
                out.append(("error", "overlap", f"{k1} | {k2}", t, f"with {group(other[0])} «{other[1][:24]}»"))
    return out


def runs(per_frame, step, fps):
    """{frame: issues} -> problems lasting MIN_RUN_S or more: [{level, kind, subject, text, detail, start, end}]."""
    open_, done = {}, []
    frames = sorted(per_frame)
    for f in frames:
        now = {(i[1], i[2]): i for i in per_frame[f]}
        for k, i in now.items():
            r = open_.get(k)
            if r and f - r["last"] <= step:
                r["last"] = f
            else:
                if r:
                    done.append(r)
                open_[k] = {"issue": i, "first": f, "last": f}
        for k in [k for k in open_ if k not in now]:
            done.append(open_.pop(k))
    done += open_.values()
    out = []
    for r in done:
        if (r["last"] - r["first"] + step) / fps < MIN_RUN_S - 1e-9:
            continue
        lv, kind, subj, text, det = r["issue"]
        out.append({"level": lv, "kind": kind, "subject": subj, "group": " | ".join(group(s) for s in subj.split(" | ")),
                    "text": text, "detail": det, "start": round(r["first"] / fps, 2), "end": round((r["last"] + step) / fps, 2)})
    return sorted(out, key=lambda x: (x["level"] != "error", x["start"]))


def check(per_frame, faces_at, step, fps):
    return runs({f: frame_issues(b, faces_at(f / fps) if faces_at else None) for f, b in per_frame.items()}, step, fps)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit")
    ap.add_argument("--props", help="the props the render will use (default edit/<id>/reelkit-props.json)")
    ap.add_argument("--remotion", help="the Remotion project (default: it-reelsmaker.json -> remotion_dir)")
    ap.add_argument("--comp", default="ReelKit", help="composition (a per-video Reel<id> must wrap its content in <Sampled>)")
    ap.add_argument("--step", type=int, default=3, help="every Nth frame (3 = 0.1 s)")
    ap.add_argument("--keep-log", action="store_true", help="keep Remotion's log in edit/<id>/textcheck.log")
    a = ap.parse_args()
    import visual_plan as vp
    e = edit_dir(a.edit)
    pf = bd.props_path(e, a.props)
    props = load_json(pf)
    plan = vp.load_plan(e) if vp.plan_path(e).is_file() else {}
    _s, _prov, doc, _bdir, _brand = vp.current_settings(e, plan)
    fps = (doc.get("scenes") or {}).get("fps", 30)
    step = max(1, a.step)
    frames = list(range(0, bd.total_frames(props, fps), step))
    rem = bd.remotion_dir(a.remotion)
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="textcheck-") as tmp:
        sp = Path(tmp) / "probe-props.json"
        save_json(sp, bd.sample_props(props, frames, probe=True, media=False))
        _imgs, log = bd.render_frames(rem, a.comp, sp, len(frames), Path(tmp) / "frames", 0.1, log="verbose")
    if a.keep_log:
        (e / "textcheck.log").write_text(log, encoding="utf-8")
    per_frame = parse_log(log)
    if not per_frame:
        sys.exit("no text boxes in Remotion's output: the composition has no probe (kit 1.10.0+: kit.py check / update; "
                 "a per-video composition needs <Sampled sample={p.sample}>)")
    missing = sorted(set(frames) - set(per_frame))
    faces_at = None if props.get("video") == "" else face_source(e, plan, props, fps)
    issues = check(per_frame, faces_at, step, fps)
    errs = [i for i in issues if i["level"] == "error"]
    save_json(e / "textcheck.json", {"props": str(pf), "step": step, "frames": len(frames), "measured": len(per_frame),
                                     "missing": missing, "faces": faces_at is not None, "issues": issues})
    print(f"text measured on {len(per_frame)} of {len(frames)} frames (every {step}) in {time.time() - t0:.0f} s"
          + (f"; {len(missing)} frame(s) missing from the log" if missing else ""))
    if faces_at is None:
        print("faces: " + ("no speaker (scenes only)" if props.get("video") == "" else
                           "no faces.json, the face check is skipped (faces.py scan, references/faces.md)"))
    for i in issues:
        mark = "✗" if i["level"] == "error" else "!"
        print(f"  {mark} {i['kind']}: {i['start']:.1f}-{i['end']:.1f} s  {i['group']}  «{i['text'][:40]}»  ({i['detail']})")
    print(f"{len(errs)} error(s), {len(issues) - len(errs)} warning(s); {e / 'textcheck.json'}")
    if missing:  # a gap hides what is there and splits a lasting problem into short runs that do not count
        print(f"incomplete: frames {', '.join(map(str, missing[:8]))}{' …' if len(missing) > 8 else ''} were not measured; "
              f"run it again (--keep-log keeps Remotion's output)")
    if errs or missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
