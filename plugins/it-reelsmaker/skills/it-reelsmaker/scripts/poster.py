# -*- coding: utf-8 -*-
"""The video's cover and frame 0: previews in Telegram, WhatsApp and Slack take the file's first frame, Instagram
uses its own cover, and a file manager (Windows Explorer, macOS Finder) shows the embedded cover art, if the file has
one, otherwise a frame of its own choosing (a B-roll frame from the middle, say).

    python scripts/poster.py pick  edit/<id> --render out/x.mp4 [--t 3.2] -o edit/<id>/cover.jpg
    python scripts/poster.py pick  edit/<id> --render out/x.mp4 --sheet edit/<id>/cover-candidates.jpg   # look, then --t
    python scripts/poster.py bake  out/x.mp4 --cover edit/<id>/cover.jpg -o out/x-cover.mp4
    python scripts/poster.py guide edit/<id>/cover.jpg -o edit/<id>/cover-guide.png
    python scripts/poster.py attach out/x-master.mp4 --cover edit/<id>/cover.jpg -o out/x-final.mp4

pick  — a "settled" frame from the render: --t; otherwise from the visual plan, the hook scene's settled window
        (after its entrance and before its exit, by the scene tone, references/scenes.md), otherwise the cover scene's;
        otherwise 1.0 s → jpg q2. Within the window the frame is taken in a pause of the speech, measured on the
        render's sound: a face caught mid-word is distorted (an open mouth, a half-said vowel). No pause in the window:
        the quietest moment, with a note; --t inside speech: a warning with the nearest pause.
        A pause is not enough on its own: in pauses people blink and look down (a real case: the pause frame had
        half-closed eyes). --sheet saves up to 6 candidates from the window's pauses side by side, numbered left to
        right, with their seconds printed: pick the one with open eyes and a mouth at rest, then pick --t <second>.
        A cover with text over the frame is drawn by the ReelCover composition (`npx remotion still ReelCover cover.png --props=…`).
bake  — replaces ONLY frame 0 with the cover image (overlay enable='eq(n,0)'); video libx264 crf 18 preset slow yuv420p,
        audio copied, +faststart. Check: the frame count (ffprobe -count_frames) and the video and audio durations are
        the same before and after, and frame 0 = the cover; otherwise exit code 1 (do not deliver the file). Order:
        render → bake → master_audio.py (mastering copies the video without re-encoding, frame 0 is kept) → faces.py audit.
attach — embeds the cover as cover art (an attached picture, mp4 "covr"): what file managers show as the thumbnail.
        Nothing is re-encoded; the last step, after master_audio.py (mastering keeps only the first video stream).
        Check: the video and audio streams and durations are unchanged and the cover is in the file; otherwise exit 1.
guide — the same image with frames: the profile grid crop 3:4 (center 1080×1440, NOT CONFIRMED, check in the app)
        and 1:1 (center 1080×1080), in red the UI zones (top 0–220, bottom 1500–1920, right x > 960). The cover's
        hook must fit entirely inside 1:1 and stay out of the red.
"""
import argparse, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import local_media_args, edit_dir, load_config, load_json, utf8_stdio, warn

W, H = 1080, 1920
GRID_34 = (0, 240, 1080, 1440)   # 3:4 centered in the 9:16 frame, NOT CONFIRMED (Instagram profile grid)
GRID_11 = (0, 420, 1080, 1080)   # 1:1 centered
UI = [(0, 0, 1080, 220), (0, 1500, 1080, 420), (960, 220, 120, 1280)]  # UI: top, bottom, right column
PSNR_COVER = 25.0   # frame 0 vs. the cover: below this, the frame was not replaced
PSNR_KEEP = 35.0    # frame 1 vs. the source: below this, re-encoding visibly damaged the picture


def sh(args, what="ffmpeg"):
    r = subprocess.run(local_media_args([str(x) for x in args]), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"{what} failed (code {r.returncode}):\n" + (r.stderr or r.stdout)[-1500:])
    return r


def video_info(p, count=False):
    """fps, frame count (count=True: an exact count by the decoder), video and audio durations, size, color tags."""
    args = ["ffprobe", "-v", "error", "-select_streams", "v:0"] + (["-count_frames"] if count else []) + [
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames,nb_read_frames,duration,color_space,color_primaries,"
        "color_transfer,color_range", "-of", "json", p]
    s = (json.loads(sh(args, "ffprobe").stdout or "{}").get("streams") or [{}])[0]
    num, den = (s.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    frames = s.get("nb_read_frames") if count else s.get("nb_frames")
    a = json.loads(sh(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration", "-of", "json", p],
                      "ffprobe").stdout or "{}").get("streams") or []
    fl = lambda v: float(v) if v not in (None, "N/A", "") else None
    return {"w": s.get("width"), "h": s.get("height"), "fps": fps, "frames": int(frames) if str(frames or "").isdigit() else None,
            "vdur": fl(s.get("duration")), "has_audio": bool(a), "adur": fl(a[0].get("duration")) if a else None,
            "color": {k: s.get(k) for k in ("color_space", "color_primaries", "color_transfer", "color_range")
                      if s.get(k) and s.get(k) != "unknown"}}


def psnr(a, b):
    r = subprocess.run(local_media_args(["ffmpeg", "-v", "info", "-i", str(a), "-i", str(b), "-lavfi",
                        "[1:v][0:v]scale2ref[b][a];[a][b]psnr", "-f", "null", "-"]),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"average:(inf|[0-9.]+)", r.stderr)
    return 0.0 if not m else float("inf") if m.group(1) == "inf" else float(m.group(1))


def frame_png(video, n, out):
    sh(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf", f"select='eq(n\\,{n})'", "-fps_mode", "passthrough",
        "-frames:v", "1", out], f"ffmpeg (frame {n})")
    return out


# ─── pick ───────────────────────────────────────────────────────────────────────────────────────────

def pauses(render, t0, t1):
    """Pauses of the speech in [t0, t1] of the render: [(start, end)], at least 60 ms below the speech threshold
    (the louder of -45 dBFS and the 95th percentile of the window - 20 dB), 10 ms windows; plus the quietest moment."""
    import wave
    from array import array
    from math import log10, sqrt
    tmp = Path(tempfile.mkdtemp(prefix="poster-"))
    try:
        wav = tmp / "a.wav"
        sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t0):.3f}", "-to", f"{t1:.3f}", "-i", render, "-vn", "-ac", "1",
            "-ar", "16000", "-c:a", "pcm_s16le", wav], "ffmpeg (cover audio)")
        with wave.open(str(wav), "rb") as w:
            data = array("h", w.readframes(w.getnframes()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    n, env = 160, []
    for i in range(0, len(data) - n + 1, n):
        s = sum(v * v for v in data[i:i + n])
        r = sqrt(s / n) / 32768
        env.append(20 * log10(r) if r > 1e-6 else -120.0)
    if not env:
        return [], None
    thr = max(-45.0, sorted(env)[int(len(env) * 0.95)] - 20)
    out, k, base = [], 0, max(0.0, t0)
    while k < len(env):
        if env[k] < thr:
            j = k
            while j < len(env) and env[j] < thr:
                j += 1
            if (j - k) * 0.01 >= 0.06:
                out.append((base + k * 0.01, base + j * 0.01))
            k = j
        else:
            k += 1
    sm = [sum(env[max(0, i - 2):i + 3]) / len(env[max(0, i - 2):i + 3]) for i in range(len(env))]
    quiet = base + min(range(len(sm)), key=lambda i: sm[i]) * 0.01 + 0.005
    return out, quiet


def in_pause(render, a, b, why):
    """The middle of the longest speech pause inside [a, b] (one frame away from its edges) → (second, source)."""
    ps, quiet = pauses(render, a, b)
    ps = [(max(x, a), min(y, b)) for x, y in ps if min(y, b) - max(x, a) >= 0.06]
    if ps:
        x, y = max(ps, key=lambda g: g[1] - g[0])
        return round((x + y) / 2, 3), f"{why}, in a pause of the speech {x:.2f}–{y:.2f} s (the face is not mid-word)"
    if quiet is not None:
        return round(quiet, 3), f"{why}, the quietest moment: no pause in the window, check the face (mid-word?)"
    return round((a + b) / 2, 3), why


def candidates(render, a, b, k=6):
    """Up to k moments in [a, b]: the middles of the speech pauses (longest first), topped up evenly across the window."""
    ps, quiet = pauses(render, a, b)
    ps = sorted(((max(x, a), min(y, b)) for x, y in ps if min(y, b) - max(x, a) >= 0.06), key=lambda g: g[0] - g[1])
    out = [round((x + y) / 2, 3) for x, y in ps[:k]]
    step = (b - a) / (k + 1)
    for j in range(1, k + 1):
        if len(out) >= k:
            break
        m = round(a + j * step, 3)
        if all(abs(m - o) > 0.2 for o in out):
            out.append(m)
    return sorted(out)


def hook_window(e):
    """(start, end, source) of the hook scene's settled window (else the cover scene's), or None."""
    plan = load_json(e / "visual_plan.json") or {}
    scenes = [i for i in plan.get("inserts", []) if i.get("kind") == "scene" and i.get("status") != "skipped"]
    if not scenes:
        return None
    s, _, doc, _, _ = load_config(e)
    tones = doc.get("scene_tones") or {}
    fps = (doc.get("scenes") or {}).get("fps", 30)
    for typ in ("hook", "cover"):
        sc = min((x for x in scenes if x.get("type") == typ), key=lambda x: x["start"], default=None)
        if sc:
            tn = sc.get("tone") or s.get("scene_tone") or (s.get("brand_tone") or {}).get("scene_tone") or "calm"
            T = tones.get(tn) or {"in": 14, "out": 9}
            return sc["start"] + T["in"] / fps, sc["start"] + sc["dur"] - T["out"] / fps, f"{sc['id']} {typ} ({tn})"
    return None


def rest_time(e, render=None):
    """A frame in the "settled" window of the hook scene (else the cover scene) from the plan, in a pause of the speech
    when the render is given → (second, source) or (None, reason)."""
    plan = load_json(e / "visual_plan.json") or {}
    scenes = [i for i in plan.get("inserts", []) if i.get("kind") == "scene" and i.get("status") != "skipped"]
    if not scenes:
        return None, "no scenes in the plan"
    s, _, doc, _, _ = load_config(e)
    tones = doc.get("scene_tones") or {}
    fps = (doc.get("scenes") or {}).get("fps", 30)
    for typ in ("hook", "cover"):
        sc = min((x for x in scenes if x.get("type") == typ), key=lambda x: x["start"], default=None)
        if sc:
            tn = sc.get("tone") or s.get("scene_tone") or (s.get("brand_tone") or {}).get("scene_tone") or "calm"
            T = tones.get(tn) or {"in": 14, "out": 9}
            a, b = sc["start"] + T["in"] / fps, sc["start"] + sc["dur"] - T["out"] / fps
            why = f"the settled window of {sc['id']} {typ} ({tn}) {a:.2f}–{b:.2f} s"
            if b <= a:
                return round(sc["start"] + sc["dur"] / 2, 3), why
            return in_pause(render, a, b, why) if render else (round((a + b) / 2, 3), why)
    return None, "no hook or cover scene"


def cmd_pick(a):
    e = edit_dir(a.edit)
    render = Path(a.render)
    if not render.is_file():
        sys.exit(f"render not found: {render}")
    if a.sheet:
        win = hook_window(e)
        lo, hi = (win[0], win[1]) if win and win[1] > win[0] else (0.5, 3.0)
        ts = candidates(render, lo, hi)
        tmp = Path(tempfile.mkdtemp(prefix="poster-"))
        try:
            frames = []
            for j, tt in enumerate(ts):
                f = tmp / f"c{j}.jpg"
                sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{tt:.3f}", "-i", render, "-frames:v", "1", "-vf", "scale=300:-2", f])
                frames.append(f)
            out = Path(a.sheet)
            out.parent.mkdir(parents=True, exist_ok=True)
            ins = sum((["-i", f] for f in frames), [])
            sh(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex",
                "".join(f"[{j}]" for j in range(len(frames))) + f"hstack=inputs={len(frames)}" if len(frames) > 1 else "null",
                "-frames:v", "1", out])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        print(f"cover candidates ({'window ' + win[2] if win else 'no hook scene: 0.5–3.0 s'} {lo:.2f}–{hi:.2f} s), "
              f"left to right: " + ", ".join(f"{j + 1}: {tt:.2f} s" for j, tt in enumerate(ts)) + f" → {out}")
        print("pick the frame with open eyes and the mouth at rest, then: poster.py pick … --t <second> -o …/cover.jpg")
        return
    if not a.output:
        sys.exit("-o is needed (or --sheet for the candidates)")
    if a.t is not None:
        t, why = a.t, "--t"
        ps, _ = pauses(render, a.t - 1.0, a.t + 1.0)
        if not any(x <= a.t <= y for x, y in ps):
            near = min(((x + y) / 2 for x, y in ps), key=lambda m: abs(m - a.t), default=None)
            warn(f"--t {a.t:.2f} falls on speech: the face may be caught mid-word"
                 + (f"; the nearest pause is at {near:.2f} s" if near is not None else ""))
    else:
        t, why = rest_time(e, render)
        if t is None:
            t, why = 1.0, f"1.0 s by default ({why})"
    info = video_info(render)
    if info["vdur"]:
        t = max(0.0, min(t, info["vdur"] - 1.0 / info["fps"]))
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", render, "-frames:v", "1", "-q:v", "2", out])
    if not out.is_file():
        sys.exit(f"the frame was not saved: {out}")
    print(f"cover: frame at {t:.2f} s ({why}) → {out}")
    print(f"next: poster.py guide {out} -o {out.with_name(out.stem + '-guide.png')} to check the grid crop; "
          f"poster.py bake {render} --cover {out} -o <render>-cover.mp4")


# ─── bake ───────────────────────────────────────────────────────────────────────────────────────────

def cmd_bake(a):
    src, cover, out = Path(a.render), Path(a.cover), Path(a.output)
    for p, what in ((src, "render"), (cover, "cover")):
        if not p.is_file():
            sys.exit(f"{what} not found: {p}")
    if out.resolve() == src.resolve():
        sys.exit("-o must differ from the input (the input is needed for the comparison)")
    before = video_info(src, count=True)
    if not before["frames"] or not before["w"]:
        sys.exit(f"could not read the frames/size of {src}")
    w, h = before["w"], before["h"]
    fc = (f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=yuv420p[c];"
          f"[0:v][c]overlay=0:0:enable='eq(n\\,0)':eof_action=repeat,format=yuv420p[v]")
    color = []
    for k, flag in (("color_space", "-colorspace"), ("color_primaries", "-color_primaries"),
                    ("color_transfer", "-color_trc"), ("color_range", "-color_range")):
        if before["color"].get(k):
            color += [flag, before["color"][k]]
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"bake: {src.name} {w}×{h}, {before['frames']} frames, {before['fps']:.3f} fps — frame 0 ← {cover.name} "
          f"(libx264 crf 18, preset slow: a couple of minutes for a one-minute video)")
    sh(["ffmpeg", "-v", "error", "-y", "-i", src, "-i", cover, "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", *color, "-fps_mode", "passthrough",
        "-c:a", "copy", "-movflags", "+faststart", out], "ffmpeg (bake)")
    after = video_info(out, count=True)
    fails, notes = [], []
    if after["frames"] != before["frames"]:
        fails.append(f"{after['frames']} frames, was {before['frames']}")
    else:
        notes.append(f"{after['frames']} frames, as before")
    tol = 0.5 / before["fps"]
    if before["vdur"] is not None and (after["vdur"] is None or abs(after["vdur"] - before["vdur"]) > tol):
        fails.append(f"video {after['vdur']} s, was {before['vdur']:.3f} s")
    else:
        notes.append(f"video {after['vdur']:.3f} s, as before")
    if before["has_audio"]:
        if not after["has_audio"]:
            fails.append("the audio is gone")
        elif abs((after["adur"] or 0) - (before["adur"] or 0)) > 0.01:
            fails.append(f"audio {after['adur']} s, was {before['adur']} s")
        else:
            notes.append(f"audio {after['adur']:.3f} s, as before (copied)")
    tmp = Path(tempfile.mkdtemp(prefix="poster-"))
    try:
        f0 = frame_png(out, 0, tmp / "out0.png")
        ref = tmp / "cover-ref.png"  # reference with the same scale/crop as the replacement: a cover that is not 9:16 gives no false failure
        sh(["ffmpeg", "-v", "error", "-y", "-i", cover, "-vf",
            f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1", "-frames:v", "1", ref],
           "ffmpeg (cover reference)")
        p0 = psnr(f0, ref)
        (notes if p0 >= PSNR_COVER else fails).append(f"frame 0 vs. the cover: {p0:.1f} dB"
                                                      + ("" if p0 >= PSNR_COVER else f" < {PSNR_COVER:.0f}, not replaced"))
        if before["frames"] > 1:
            p1 = psnr(frame_png(out, 1, tmp / "out1.png"), frame_png(src, 1, tmp / "src1.png"))
            if p1 < PSNR_KEEP:
                warn(f"frame 1 vs. the source {p1:.1f} dB < {PSNR_KEEP:.0f}: re-encoding is visible (check by eye)")
            else:
                notes.append(f"frame 1 untouched: {'∞' if p1 == float('inf') else f'{p1:.1f}'} dB")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for n in notes:
        print("✓ " + n)
    for f in fails:
        print("✗ " + f)
    if fails:
        print(f"file {out}: do NOT deliver it, the check failed")
        sys.exit(1)
    print(f"done: {out} → next master_audio.py {out} -o <…>-master.mp4")


# ─── guide ──────────────────────────────────────────────────────────────────────────────────────────

def cmd_guide(a):
    src, out = Path(a.image), Path(a.output)
    if not src.is_file():
        sys.exit(f"image not found: {src}")
    info = video_info(src)
    w, h = info["w"] or W, info["h"] or H
    if abs(w / h - W / H) > 0.01:
        warn(f"the image is {w}×{h}, not 9:16: the frames are scaled from 1080×1920 and may not match")
    kx, ky = w / W, h / H
    box = lambda b: f"x={round(b[0] * kx)}:y={round(b[1] * ky)}:w={round(b[2] * kx)}:h={round(b[3] * ky)}"
    t = max(2, round(6 * kx))
    vf = ",".join([f"drawbox={box(z)}:color=red@0.35:t=fill" for z in UI]
                  + [f"drawbox={box(GRID_34)}:color=yellow@0.95:t={t}", f"drawbox={box(GRID_11)}:color=cyan@0.95:t={t}"])
    out.parent.mkdir(parents=True, exist_ok=True)
    sh(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", vf, "-frames:v", "1", out], "ffmpeg (guide)")
    print(f"{out}: yellow frame, the 3:4 profile grid (1080×1440 centered, y 240–1680), NOT CONFIRMED, check it in the "
          f"Instagram app; cyan, 1:1 (1080×1080, y 420–1500); red, the UI zones (top 0–220, "
          f"bottom 1500–1920, right x > 960). The cover's hook goes entirely inside 1:1 and outside the red.")


def cmd_attach(a):
    src, cover, out = Path(a.render), Path(a.cover), Path(a.output)
    for f, what in ((src, "video"), (cover, "cover")):
        if not f.is_file():
            sys.exit(f"{what} not found: {f}")
    if out.resolve() == src.resolve():
        sys.exit("-o must differ from the input")
    before = video_info(src)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="poster-"))
    try:
        jpg = tmp / "cover.jpg"  # a plain baseline JPEG at most 1080 px wide: the format every thumbnailer reads
        sh(["ffmpeg", "-v", "error", "-y", "-i", cover, "-vf", "scale='min(1080,iw)':-2", "-frames:v", "1", "-q:v", "2", jpg],
           "ffmpeg (cover jpeg)")
        sh(["ffmpeg", "-v", "error", "-y", "-i", src, "-i", jpg, "-map", "0:v:0", "-map", "0:a?", "-map", "1:v",
            "-c", "copy", "-disposition:v:1", "attached_pic", "-movflags", "+faststart", out], "ffmpeg (attach)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    after = video_info(out)
    r = sh(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:stream_disposition=attached_pic", "-of", "json", out],
           "ffprobe")
    pics = [s for s in json.loads(r.stdout).get("streams", []) if (s.get("disposition") or {}).get("attached_pic")]
    fails = []
    if not pics:
        fails.append("no cover art in the file")
    if after["frames"] != before["frames"] or abs((after["vdur"] or 0) - (before["vdur"] or 0)) > 0.01:
        fails.append(f"video changed: {after['frames']} frames / {after['vdur']} s, was {before['frames']} / {before['vdur']}")
    if before["has_audio"] and abs((after["adur"] or 0) - (before["adur"] or 0)) > 0.01:
        fails.append(f"audio {after['adur']} s, was {before['adur']} s")
    if fails:
        out.unlink(missing_ok=True)
        sys.exit("attach: " + "; ".join(fails))
    print(f"attach: cover art in {out} (video and audio copied, {after['frames']} frames, {after['vdur']:.3f} s); "
          "the thumbnail in a file manager may update only after its cache refreshes")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick", help="a \"settled\" frame from the render → jpg")
    p.add_argument("edit"); p.add_argument("--render", required=True); p.add_argument("--t", type=float)
    p.add_argument("-o", "--output"); p.add_argument("--sheet", help="save up to 6 candidate frames side by side")
    p.set_defaults(fn=cmd_pick)
    p = sub.add_parser("bake", help="replace frame 0 with the cover (frame count and duration stay the same)")
    p.add_argument("render"); p.add_argument("--cover", required=True); p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_bake)
    p = sub.add_parser("attach", help="embed the cover as cover art (the file manager thumbnail); after mastering")
    p.add_argument("render"); p.add_argument("--cover", required=True); p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_attach)
    p = sub.add_parser("guide", help="profile grid crop frames and UI zones over the cover")
    p.add_argument("image"); p.add_argument("-o", "--output", required=True); p.set_defaults(fn=cmd_guide)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
