"""The visual plan's shade command: the darkening behind "Typewriter" subtitles for 4.5:1 contrast. Part of visual_plan.py, with no command line
of its own: the other scripts take these names from visual_plan."""
import sys

from reels_common import (SUB_BLOCK_H, cam_fit, edit_dir, framed_at, framed_source, framed_sub_area, load_config,
                          load_json)
from vp_core import (fmt_t, plan_duration, plan_path, srgb_lum)
from vp_camera import (camera_at, camera_view, plan_camera, subtitle_top)
from vp_scenes import (hidden_windows, hides_subtitles)


# "Typewriter" darkening (shade): its contrast target and the geometry of the kit (Subtitles.tsx: the gradient starts
# 220 px above the subtitles' top and is full at 40 % of its height; two lines of 56 px at line height 1.22 from x 60)
SHADE_TARGET = 4.5
SHADE_LINES = round(2 * 56 * 1.22)
SHADE_X = (60, 940)


def cmd_shade(a):
    """The darkening behind "Typewriter" subtitles (reel.json subtitles_shade), measured: the rough cut's frames while
    the subtitles are on (spoken words, outside the windows where a scene hides them), the subtitle band through the
    camera of camera.json; for each value the contrast of the text color against the lightest 5 % of the band (the
    gradient as the kit draws it, blended over the frame as the browser does); the smallest value that gives
    SHADE_TARGET on the lightest frame. T3: the run guessed 0.55 for a white T-shirt; the docs said 0.15-0.25.
    --zone x,y,w,h or --scene ID measures any text zone instead (a style whose text sits in the headroom, like "bold"
    in a per-video composition: T5 measured it by hand): a FLAT darkening of the zone, on the frames of the scene's time
    (--scene) or --from/--to (else the whole video), against --target (3.0, large text, by default for a zone)."""
    import subprocess
    from reels_common import local_media_args
    e = edit_dir(a.edit)
    video = e / "final.mp4"
    if not video.exists():
        sys.exit(f"no {video}: the shade is measured on the rough cut (cut.py)")
    plan = load_json(plan_path(e)) or {}
    cap = load_json(e / "captions.json") or {}
    s, _, _, _, brand = load_config(e)
    color = a.color or ((brand or {}).get("colors") or {}).get("text_on_primary") or "#FFFFFF"
    try:
        tr, tg, tb = (int(color.lstrip("#")[k:k + 2], 16) / 255 for k in (0, 2, 4))
    except ValueError:
        sys.exit(f"--color {color!r}: a hex color like #FFFFFF")
    lt = srgb_lum(tr, tg, tb)
    if lt < 0.4:
        sys.exit(f"the text color {color} is dark: a darkening lowers its contrast; use a light backing instead")
    shots = plan_camera(e, plan)
    end = cap.get("duration") or plan_duration(e, plan) or 0
    zone, span, what = None, None, ""
    if a.scene:
        sc = next((i for i in plan.get("inserts", []) if i["id"] == a.scene and i.get("kind") == "scene"), None)
        if not sc:
            sys.exit(f"--scene {a.scene}: no such scene in the plan")
        kc = next((k for k in plan.get("keep_clear", []) if k.get("scene") == a.scene), None)
        zone = sc.get("box") or (kc or {}).get("box")
        if not zone:
            sys.exit(f"--scene {a.scene}: the scene has no box (a full-frame scene draws its own field); use --zone")
        span, what = (sc["start"], sc["start"] + sc["dur"]), f"scene {a.scene}"
    elif a.zone:
        try:
            zone = [int(float(v)) for v in a.zone.split(",")]
        except ValueError:
            zone = []
        if len(zone) != 4 or zone[2] <= 0 or zone[3] <= 0:
            sys.exit(f"--zone {a.zone}: x,y,w,h in 1080x1920")
        span, what = (a.start if a.start is not None else 0.0, a.end if a.end is not None else end), "the zone"
    target = a.target or (3.0 if zone else SHADE_TARGET)
    fr = framed_at(e)
    if fr and fr["subtitles_at"] == "below" and not zone:
        print("subtitles_at below: the subtitles sit on the field under the framed window, not over the video; no "
              "darkening is needed (the kit draws none there). Check the subtitle color against the field instead: "
              "stage warns when they do not read")
        return
    top = a.top or (plan.get("subtitles_band") or [None])[0] or subtitle_top(e, s, shots, quiet=True)[0]
    if fr and not a.top:  # "framed": the block inside the window's text area, as stage puts it (Codex review: before
        # the first stage a short window [25,340,1030,800] was measured at y 1290, below the window, "no frame")
        a0, a1 = framed_sub_area(fr)[1], framed_sub_area(fr)[3]
        top = max(a0, min(top, a1 - SUB_BLOCK_H["typewriter"]))
    bottom = min(1500, top + SHADE_LINES)
    hidden = ([(i["start"], i["start"] + i["dur"]) for i in plan.get("inserts", []) if i.get("kind") == "scene"
               and i.get("status") == "ready" and i.get("type") != "cover" and hides_subtitles(i, s)]
              + [tuple(h) for h in hidden_windows(plan)])
    spoken = [(w["start"], w["end"] + 0.4) for w in cap.get("words", [])]
    W, H, fps = 270, 480, 4  # a quarter of the frame, 4 frames a second
    # where the rough cut lies on screen: the whole frame, or the "framed" window with the video's cover in it (a point
    # outside the window is the field, not the video, and is left out)
    geo = camera_view(e)
    win, (vx, vy, vw, vh) = geo if geo else ((0, 0, 1080, 1920), (0, 0, 1080, 1920))
    ccx, ccy = win[0] + win[2] / 2, win[1] + win[3] / 2
    if geo:
        src = framed_source(e) or (1080, 1920)
        W, H = max(2, round(src[0] / 4)), max(2, round(src[1] / 4))
    r = subprocess.run(local_media_args(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                                         f"fps={fps},scale={W}:{H}:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]),
                       capture_output=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + r.stderr.decode("utf-8", "replace")[-800:])
    size = W * H * 3
    g0, g1 = top - 220, top - 220 + 0.4 * (2140 - top)  # the gradient: 0 at g0, full from g1 down
    ys, xs = range(top, bottom, 4), range(SHADE_X[0], SHADE_X[1], 8)
    if zone:  # a flat darkening over the zone, not the subtitles' gradient
        x0, y0, zw, zh = zone
        ys, xs = range(max(0, y0), min(1920, y0 + zh), 4), range(max(0, x0), min(1080, x0 + zw), 8)
        g0, g1 = -2.0, -1.0
    frames = []
    for k in range(len(r.stdout) // size):
        t = k / fps
        if zone:
            if not span[0] <= t <= span[1]:
                continue
        elif not any(a0 <= t <= a1 for a0, a1 in spoken) or any(h0 <= t < h1 for h0, h1 in hidden):
            continue
        buf = r.stdout[k * size:(k + 1) * size]
        cam = camera_at(shots, t, end, view=geo) if shots else None
        z, cx, cy = cam or cam_fit(1.0, ccx, ccy, geo)
        px = []
        for y in ys:
            if not win[1] <= y < win[1] + win[3]:
                continue
            f = min(1.0, max(0.0, (y - g0) / (g1 - g0)))
            sy = min(H - 1, max(0, int(((y - ccy) / z + cy - vy) / vh * H)))
            for x in xs:
                if not win[0] <= x < win[0] + win[2]:
                    continue
                sx = min(W - 1, max(0, int(((x - ccx) / z + cx - vx) / vw * W)))
                o = (sy * W + sx) * 3
                px.append((buf[o] / 255, buf[o + 1] / 255, buf[o + 2] / 255, f))
        if px:
            frames.append((t, px))
    if not frames:
        sys.exit(f"no frame in {what} {span[0]:.2f}-{span[1]:.2f} s" if zone else
                 "no frame with subtitles on: no spoken words outside the hidden windows")
    def light(px, v):  # the lightest 5 % of the band under the darkening v
        lums = sorted(srgb_lum(rr * (1 - v * f), gg * (1 - v * f), bb * (1 - v * f)) for rr, gg, bb, f in px)
        return lums[min(len(lums) - 1, int(len(lums) * 0.95))]

    n_all, pick = len(frames), set()
    for v in (0.0, 0.5):  # the lightest frames, with and without a darkening (the gradient weighs the rows differently)
        pick |= {t for t, _ in sorted(frames, key=lambda fr: -light(fr[1], v))[:8]}
    frames = [fr for fr in frames if fr[0] in pick]
    current = s.get("subtitles_shade")
    values = sorted({round(v / 20, 2) for v in range(0, 19)} | ({float(current)} if current is not None else set()))
    rows = []
    for v in values:
        c, t = min(((lt + 0.05) / (light(px, v) + 0.05), t) for t, px in frames)
        rows.append((v, c, t))
    best = next((row for row in rows if row[1] >= target), None)
    if zone:
        print(f"shade: {what} x {zone[0]}-{zone[0] + zone[2]}, y {zone[1]}-{zone[1] + zone[3]}, {span[0]:.2f}-{span[1]:.2f} s, "
              f"{n_all} frames ({fps} a second{', the camera of camera.json' if shots else ''}); a flat darkening; text "
              f"{color}; the contrast against the lightest 5 % of the zone on the lightest frame (target {target}:1):")
    else:
        print(f"shade: the subtitle band y {top}-{bottom}, x {SHADE_X[0]}-{SHADE_X[1]}, {n_all} frames with subtitles on "
              f"({fps} a second{', the camera of camera.json' if shots else ''}; windows where scenes hide them left out); "
              f"text {color}; the contrast against the lightest 5 % of the band on the lightest frame:")
    for v, c, t in rows:
        if v in (0.0, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65) or (v == current and not zone) or (best and v == best[0]):
            mark = " <- reel.json now" if v == current and not zone else ""
            mark += " <- suggested" if best and v == best[0] else ""
            print(f"  {v:.2f}: {c:4.1f}:1 (the lightest frame {fmt_t(t)}){mark}")
    if not best:
        print(f"even 0.90 gives {rows[-1][1]:.1f}:1 < {target}:1: the background is too light for a darkening; "
              + ("put the text on a plate or a backing in the brand color" if zone else
                 "use the plate subtitles or a backing under them (references/typography.md)"))
        return
    if zone:
        print(f"{what}: a flat darkening of {best[0]:.2f} under the text ({best[1]:.1f}:1 >= {target}:1 on the lightest "
              f"frame {fmt_t(best[2])}); set it in the composition that draws this text")
        return
    print(f"reel.json subtitles_shade: {best[0]:.2f} ({best[1]:.1f}:1 >= {SHADE_TARGET}:1 on the lightest frame "
          f"{fmt_t(best[2])}) -> reelcfg.py save {a.edit} --set subtitles_shade={best[0]:.2f}")
