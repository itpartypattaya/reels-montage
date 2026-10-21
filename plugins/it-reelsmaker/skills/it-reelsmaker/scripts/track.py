# -*- coding: utf-8 -*-
"""Follow an object of the rough cut under a callout's dot (references/callouts.md, experimental): a handheld shot or
a pan moves the object away from a still dot; this finds where it goes and gives the callout a path the kit draws.

    python scripts/track.py edit/<id> l01 [--dry]

How: the callout's frames of final.mp4 (every frame of the 30 fps rough cut, at half size, gray, each frame's brightness levelled against the
phone's exposure changes); corners found in a 120 px circle around the anchor, followed frame to frame by optical flow
(Lucas-Kanade, pyramids), each kept only if following it back lands within 1 px of where it started (forward-backward);
the dot moves with the common similarity transform (RANSAC: shift, turn and scale; the scale grows a ring) of the half
of the points nearest to it, so the wall around a small object does not outvote it, or with their median shift when too
few agree; points that do not move with the dot drop out; new corners are found around the dot when fewer than 60 % are left.
The track breaks at every joint of the rough cut inside the callout (captions.json segments: the picture jumps there),
and where the points are lost (fewer than 4 agree, or the dot leaves the frame): the dot is held 0.3 s, then fades out,
and stays hidden to the callout's end; at a joint the dot fades out by the joint's frame instead (the picture
changes whole there). Rows every 2 frames, smoothed over 5 frames, go into the callout as "path"
(path_by "track") with a fingerprint of the rough cut, the anchor and the callout's time: when one changes, validate
asks for a new track. A track that stays within 40 px of the anchor and within 10 % of its size is not a path: the
callout keeps a still anchor at its median point.

Set the anchor (visual_plan.py add --anchor) on the object at the callout's first frame: an edge, a corner or a print
on it, not a flat surface (no corners: nothing to follow). validate then measures the picture along the path: a track
that slipped off the object is refused like a still dot on a moving picture.

Needs OpenCV and numpy in this Python (pip install opencv-python-headless) and ffmpeg.
Exit code: 0 - tracked (or --dry); 1 - not tracked (no OpenCV, no rough cut, nothing to follow).
"""
import argparse, importlib.util, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import edit_dir, load_json, utf8_stdio

FPS = 30
HALF = 2            # the frames are tracked at 540x960
ROI = 60            # px at half size: corners within 120 px of the anchor
MIN_POINTS = 6
LOST_POINTS = 4
FB_PX = 1.0         # forward-backward error, px at half size
RESEED = 0.6
HOLD_S = 0.3        # a lost object: the dot stays this long, then fades
FADE_S = 0.2
STILL_PX = 40       # px of the rough cut: a smaller track is a still anchor
SCALE_STILL = 0.1   # ... and a size change under 10 %
MAX_DUR = 20.0


def frames_of(video, start, dur, level=True):
    """The callout's frames: [H x W uint8], 30 a second, 540x960 gray (the frame stretched to 1080x1920 first, as the
    kit draws it)."""
    import numpy as np
    w, h = 1080 // HALF, 1920 // HALF
    # every frame as it is (no fps filter: it shifts frames on a rough cut whose first frame is not at 0; validate
    # samples the same frames, visual_plan._frames every=6)
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(video), "-vf",
                        f"scale=1080:1920,scale={w}:{h}:flags=area,format=gray", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-"], capture_output=True, timeout=600)
    n = len(r.stdout) // (w * h)
    if r.returncode != 0 or n < 2:
        return None
    a = np.frombuffer(r.stdout[:n * w * h], dtype=np.uint8).reshape(n, h, w)
    if not level:
        return list(a)
    # the phone's exposure: each frame levelled to the first one's mean brightness
    m0 = float(a[0].mean())
    return [np.clip(f.astype(np.float32) - float(f.mean()) + m0, 0, 255).astype(np.uint8) for f in a]


def corners(cv2, np, img, p):
    mask = np.zeros_like(img)
    cv2.circle(mask, (int(round(p[0])), int(round(p[1]))), ROI, 255, -1)
    pts = cv2.goodFeaturesToTrack(img, maxCorners=80, qualityLevel=0.01, minDistance=4, mask=mask)
    return pts if pts is not None else np.zeros((0, 1, 2), np.float32)


def scale_step(m):
    """The size change of one frame's similarity transform m, or None when it is not believable for one frame (a hand
    over the object, noise): within 0.8-1.25 (Antigravity review: the scale was multiplied with no limit)."""
    ds = float((m[0, 0] ** 2 + m[1, 0] ** 2) ** 0.5)
    return ds if 0.8 <= ds <= 1.25 else None


def follow(frames, p0, breaks):
    """The dot over the frames from p0 (half size) -> [(x, y, seen, scale)] per frame; breaks: frame indices where the
    picture jumps (the track stops there)."""
    import cv2
    import numpy as np
    pts = corners(cv2, np, frames[0], p0)
    if len(pts) < MIN_POINTS:
        return None, len(pts)
    n0 = len(pts)
    p, s = np.array(p0, dtype=np.float64), 1.0
    out = [(p[0], p[1], True, s)]
    lk = dict(winSize=(21, 21), maxLevel=3, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
    lost = False
    for k in range(1, len(frames)):
        if not lost and k in breaks:
            lost = True
        if not lost:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(frames[k - 1], frames[k], pts, None, **lk)
            back, st2, _ = cv2.calcOpticalFlowPyrLK(frames[k], frames[k - 1], nxt, None, **lk)
            fb = np.linalg.norm((pts - back).reshape(-1, 2), axis=1)
            good = (st.ravel() == 1) & (st2.ravel() == 1) & (fb < FB_PX)
            if good.sum() < LOST_POINTS:
                lost = True
            else:
                a, b = pts[good].reshape(-1, 2), nxt[good].reshape(-1, 2)
                # the motion of the points nearest the dot, not of most of the circle: a box smaller than the circle
                # moved and the wall around it won the vote (Codex review); the points that do not move with it drop out
                near = np.argsort(np.linalg.norm(a - p, axis=1))[:max(MIN_POINTS, (len(a) + 1) // 2)]
                an, bn = a[near], b[near]
                m, inl = (cv2.estimateAffinePartial2D(an, bn, method=cv2.RANSAC, ransacReprojThreshold=2.0)
                          if len(an) >= MIN_POINTS else (None, None))
                ds = scale_step(m) if m is not None and inl is not None and inl.sum() >= MIN_POINTS else None
                if ds is not None:
                    p = m @ np.array([p[0], p[1], 1.0])
                    s *= ds
                    keep = np.linalg.norm(a @ m[:, :2].T + m[:, 2] - b, axis=1) < 2.0
                    b = b[keep] if keep.sum() >= MIN_POINTS else bn[inl.ravel() == 1]
                else:
                    p = p + np.median(bn - an, axis=0)
                pts = b.reshape(-1, 1, 2).astype(np.float32)
                h, w = frames[k].shape
                if not (0 <= p[0] < w and 0 <= p[1] < h):
                    lost = True
                elif len(pts) < max(RESEED * n0, LOST_POINTS + 2):  # before too few are left to go on
                    more = corners(cv2, np, frames[k], p)
                    if len(more) >= MIN_POINTS:
                        pts, n0 = more, len(more)
        out.append((p[0], p[1], not lost, s))
    return out, n0


def rows_of(track, fps=FPS, joint=False):
    """Per-frame dots -> path rows [t, x, y, v, s] every 2 frames (and the last), x, y on the 1080x1920 rough cut,
    smoothed over 5 frames where seen; after a loss: held HOLD_S, faded over FADE_S, then hidden. joint: the track
    ended at a joint of the rough cut, where the picture changes whole: the fade ends on the joint's frame (held past
    it, the dot stood 0.3 s over another shot; a real tour, a tower over a cut to the street)."""
    seen = [k for k, r in enumerate(track) if r[2]]
    last = seen[-1] if seen else 0
    if joint and last < len(track) - 1:
        f0 = (last + 1) / fps - FADE_S  # the fade: over the joint's last FADE_S
        vis = lambda k: 1.0 if k / fps <= f0 else max(0.0, 1 - (k / fps - f0) / FADE_S)
        marks = [(max(0.0, f0), 1.0), ((last + 1) / fps, 0.0)]
    else:
        vis = lambda k: 1.0 if k <= last or (k - last) / fps <= HOLD_S else max(0.0, 1 - ((k - last) / fps - HOLD_S) / FADE_S)
        marks = [(last / fps + HOLD_S, 1.0), (last / fps + HOLD_S + FADE_S, 0.0)]
    xs, ys = [], []
    for k in range(len(track)):
        j = min(k, last)
        h = min(2, j, last - j)  # a centered window, narrower at the ends (a one-sided one pulled the ends along)
        near = [track[i] for i in range(j - h, j + h + 1)]
        xs.append(sum(float(r[0]) for r in near) / len(near) * HALF)
        ys.append(sum(float(r[1]) for r in near) / len(near) * HALF)
    rows = []
    for k in sorted(set(range(0, len(track), 2)) | {len(track) - 1}):
        rows.append([round(k / fps, 3), round(xs[k], 1), round(ys[k], 1), round(vis(k), 2), round(float(track[min(k, last)][3]), 3)])
    if last < len(track) - 1:  # the moments the fade starts and ends, exactly
        for t, v in marks:
            if t < (len(track) - 1) / fps:
                j = min(last, int(t * fps))
                rows.append([round(t, 3), round(xs[j], 1), round(ys[j], 1), v, round(float(track[j][3]), 3)])
        rows = sorted({r[0]: r for r in rows}.values(), key=lambda r: r[0])
    return rows


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description="Follow the object under a callout's dot (references/callouts.md)")
    ap.add_argument("edit")
    ap.add_argument("id", help="the callout, e.g. l01")
    ap.add_argument("--dry", action="store_true", help="track and report, keep the plan as it is")
    a = ap.parse_args()
    import visual_plan as vp
    for mod, pip in (("cv2", "opencv-python-headless"), ("numpy", "numpy")):
        if importlib.util.find_spec(mod) is None:
            sys.exit(f"{mod} is not installed for this Python ({sys.executable}): pip install {pip}")
    if not shutil.which("ffmpeg"):
        sys.exit("no ffmpeg on PATH")
    e = edit_dir(a.edit)
    video = e / "final.mp4"
    if not video.is_file():
        sys.exit(f"no {video}: the rough cut is tracked (cut.py)")
    plan = load_json(vp.plan_path(e)) or {}
    c = next((i for i in plan.get("inserts", []) if i.get("id") == a.id), None)
    if not c or c.get("kind") != "callout":
        sys.exit(f"{a.id}: no such callout in the plan")
    if c.get("person"):
        sys.exit(f"{a.id}: it points at a person, its dot follows the face (faces.json); nothing to track")
    if c.get("variant") == "dimension":
        sys.exit(f"{a.id}: a dimension measures between two still points; nothing to track")
    if not vp._point(c.get("anchor")):
        sys.exit(f"{a.id}: no anchor: set --anchor on the object at the callout's first frame")
    t0, t1 = vp.callout_span(c)
    if t1 - t0 > MAX_DUR:
        sys.exit(f"{a.id}: {t1 - t0:.1f} s: a callout longer than {MAX_DUR:g} s is not tracked")
    frames = frames_of(video, t0, t1 - t0)
    if not frames:
        sys.exit(f"{video} did not decode over {t0:.2f}-{t1:.2f} s")
    cap = load_json(e / "captions.json", {}) or {}
    breaks = {round((g["out_start"] - t0) * FPS) for g in cap.get("segments", []) if t0 + 0.02 < g["out_start"] < t1 - 0.02}
    ax, ay = c["anchor"]
    track, n = follow(frames, (ax / HALF, ay / HALF), breaks)
    if track is None:
        sys.exit(f"{a.id}: nothing to follow at ({ax}, {ay}): {n} corner(s) within 120 px (at least {MIN_POINTS}); "
                 f"put the anchor on an edge, a corner or a print of the object, not a flat surface")
    seen = [r for r in track if r[2]]
    amp = max(((r[0] * HALF - ax) ** 2 + (r[1] * HALF - ay) ** 2) ** 0.5 for r in seen)
    lost_at = next((k for k, r in enumerate(track) if not r[2]), None)
    joint = lost_at is not None and lost_at in breaks
    rows = rows_of(track, joint=joint)
    scales = [r[3] for r in seen]
    print(f"{a.id}: {len(seen)} of {len(track)} frames followed ({n} points), up to {amp:.0f} px from the anchor, "
          f"scale {min(scales):.2f}-{max(scales):.2f}"
          + (f"; at {t0 + lost_at / FPS:.2f} s a joint of the rough cut: the dot fades out by it" if joint else
             f"; lost at {t0 + lost_at / FPS:.2f} s (the points no longer agree): the dot holds {HOLD_S:g} s, then fades"
             if lost_at is not None else ""))
    if lost_at is not None and lost_at / max(1, len(track) - 1) < vp.CALLOUT_SEEN:
        print(f"warning: the dot is seen only {lost_at / (len(track) - 1) * 100:.0f} % of the callout: shorten it to "
              f"{lost_at / FPS:.1f} s or move it")
    if a.dry:
        return
    with vp.editing_plan(e) as p2:
        x = next(i for i in p2["inserts"] if i.get("id") == a.id)
        for k in ("path", "path_by", "track_key", "motion"):
            x.pop(k, None)
        # still: no shift and no change of size either (a box growing in place keeps its path: a ring grows with it)
        if amp < STILL_PX and lost_at is None and max(abs(v - 1) for v in scales) < SCALE_STILL:
            mx = sorted(r[0] for r in seen)[len(seen) // 2] * HALF
            my = sorted(r[1] for r in seen)[len(seen) // 2] * HALF
            x["anchor"] = [round(mx), round(my)]
            print(f"{a.id}: the object holds still (within {STILL_PX} px): a still anchor at {x['anchor']}, no path")
        else:
            x.update(path=rows, path_by="track")
            x["track_key"] = vp.track_key(e, x)
            print(f"{a.id}: a path of {len(rows)} points written (path_by track); run visual_plan.py validate")


if __name__ == "__main__":
    main()
