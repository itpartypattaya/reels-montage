# -*- coding: utf-8 -*-
"""Re-render only a segment of a video with a fix and splice it into the finished render, instead of a full Remotion
render.

    python scripts/patch_render.py reels/out/<render>.mp4 --comp Reel4821 --from 19.2 --to 22.2
    python scripts/patch_render.py <render>.mp4 --comp Reel4821 --frames 576-666 [--in-place]
    python scripts/patch_render.py <render>.mp4 --comp Reel4821 --from 15 --to 19 --audio rerender   # the fix touches audio
    python scripts/patch_render.py <render>.mp4 --comp Reel4821 --from 19.2 --to 22.2 --mode reencode # splice with re-encoding

When: a single late fix that changes the picture in one place (a word in a subtitle, a card's text, an element's
position), while a full render takes 8-10 min on a laptop. Not for fixes that shift timing (re-cutting in cut.py,
speed, the length of a card): the number and order of frames must stay the same, otherwise only a full render.

How:
  1. In the finished render: fps, frame count and keyframes (IDR: in Remotion renders at most every 250 frames and at
     scene changes). The fix range is widened to the neighboring keyframes [K1, K2): there the stream can be cut
     without re-encoding.
  2. Remotion draws only frames K1...K2-1: `npx remotion render <comp> --frames=K1-(K2-1) --muted` (same codec and CRF).
  3. Splice:
     copy     - the old file is cut at the keyframes (segment muxer), the middle segment is replaced by the patch, concat
                without re-encoding; the codec parameters (avcC, resolution, pix_fmt) must match, otherwise reencode;
     reencode - old[0,K1) + patch + old[K2,end) through the concat filter, x264 crf 16 (~1-2 min per minute of video).
     auto (default) - copy; if the parameters don't match or the check fails, reencode with the same patch.
  4. Audio: keep (default) - the old file's whole audio as is (splicing AAC in pieces gives clicks and a shift);
     rerender - the whole video's audio from a separate Remotion audio render (`--codec=wav`), if the fix touches sound
     effects or speech. This is NOT fast: Remotion goes through all frames for audio too (measured: 4-5 min for a 65 s
     video vs 8-10 min for a full render), so for an audio fix the gain is small and a full render is simpler.
  5. Check (exit code 1 on failure): frame count and duration equal the old ones; at the frames next to the joins
     outside the fix (K1-1, K1, K2-1, K2) the new frame is compared with old frames n-1, n, n+1: the best match must be
     at n and >= 35 dB PSNR (a one-frame shift is a "stutter" at the join, caught here); the sheet of joins
     `<out>-seams.jpg` is for checking by eye.
  Then as usual: master_audio.py -> -master, faces.py audit.

Output by default: `<render>-patched.mp4`; `--in-place`: after a successful check the old file becomes
`<render>.prev.mp4` and the patched one takes its place (handy before master_audio.py). Temporary files go to a temp
folder and are deleted.
"""
import argparse, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import local_media_args

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PSNR_MIN = 35.0  # a frame redrawn by Remotion vs the old one: 41-45 dB in a measured case; neighbors catch a shift


def run(args, cwd=None, what="command"):
    r = subprocess.run(local_media_args(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        # the gist of the error is at the start; the tail is a Node/Rust stack trace, drop it
        txt = re.sub(r"\x1b\[[0-9;]*m", "", (r.stderr or "") + (r.stdout or ""))
        keep = [l for l in txt.splitlines() if l.strip() and not re.match(r"\s*(at |\d+: )", l)]
        sys.exit(f"{what} failed (code {r.returncode}):\n" + "\n".join(keep[:12]))
    return r


def probe_video(p):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
               "stream=width,height,pix_fmt,r_frame_rate,nb_read_packets,codec_name,profile,level",
               "-of", "default=nw=1", str(p)], what="ffprobe").stdout
    d = dict(l.split("=", 1) for l in out.strip().splitlines() if "=" in l)
    num, den = d["r_frame_rate"].split("/")
    d["fps"] = float(num) / float(den)
    d["frames"] = int(d["nb_read_packets"])
    return d


def has_audio(p):
    out = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
               str(p)], what="ffprobe").stdout
    return bool(out.strip())


def keyframes(p, fps):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey", "-show_entries",
               "frame=pts_time", "-of", "csv=p=0", str(p)], what="ffprobe").stdout
    ks = sorted({round(float(x.strip().strip(",")) * fps) for x in out.split() if x.strip().strip(",") not in ("", "N/A")})
    return ks


def extradata(p):
    """avcC/hvcC of the video stream: segments spliced without re-encoding must match it byte for byte."""
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_data", str(p)],
              what="ffprobe").stdout
    m = re.search(r"extradata=\s*\n((?:[0-9a-f]{8}:.*\n)+)", out)
    return m.group(1) if m else out[out.find("extradata"):][:4000]


def vdur(p):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0",
               str(p)], what="ffprobe").stdout.strip().strip(",")
    return float(out) if out and out != "N/A" else None


def npx():
    return shutil.which("npx") or shutil.which("npx.cmd") or "npx"


def find_remotion(render, given):
    if given:
        return Path(given).resolve()
    for d in [Path(render).resolve().parent, *Path(render).resolve().parents, Path.cwd()]:
        if (d / "package.json").exists() and (d / "src").is_dir():
            return d
    sys.exit("no Remotion project found; pass --remotion <folder>")


def frames_at(video, indices, outdir, tag):
    """Frames by NUMBER (select=eq(n,...), one decoder pass, stops at the last needed one) -> {n: png}.
    Not by time: in a spliced file the timestamps may shift, and seeking with -ss would fetch a neighboring frame,
    a false "shift"."""
    outdir.mkdir(parents=True, exist_ok=True)
    idx = sorted({i for i in indices if i >= 0})
    if not idx:
        return {}
    expr = "+".join(f"eq(n\\,{i})" for i in idx)
    pat = outdir / f"{tag}_%03d.png"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"select='{expr}'", "-fps_mode", "passthrough",
         "-frames:v", str(len(idx)), "-start_number", "0", str(pat)], what="ffmpeg (frames by number)")
    return {i: outdir / f"{tag}_{k:03d}.png" for k, i in enumerate(idx) if (outdir / f"{tag}_{k:03d}.png").exists()}


def psnr(a, b):
    r = subprocess.run(local_media_args(["ffmpeg", "-v", "info", "-i", str(a), "-i", str(b), "-lavfi", "psnr", "-f", "null", "-"]),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"average:(inf|[0-9.]+)", r.stderr)
    if not m:
        return 0.0
    return float("inf") if m.group(1) == "inf" else float(m.group(1))


def check(old, new, fps, n_old, points, edit_a, edit_b, work):
    """Frame count, duration and frame-by-frame match at the joins. Returns (ok, report lines)."""
    lines, ok = [], True
    meta = probe_video(new)
    if meta["frames"] != n_old:
        ok = False
        lines.append(f"✗ {meta['frames']} frames, was {n_old}")
    else:
        lines.append(f"✓ {n_old} frames, as before")
    # timestamps: every frame exactly at n/fps, otherwise the player shows a frame at the wrong time ("stutter") even though the numbers match
    pts = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0",
               str(new)], what="ffprobe").stdout.replace(",", " ").split()
    ts = sorted(float(x) for x in pts if x not in ("N/A",))
    dev = max((abs(t - i / fps) for i, t in enumerate(ts)), default=0.0)
    if dev > 0.5 / fps:
        ok = False
        lines.append(f"✗ timestamps drifted: up to {dev * 1000:.0f} ms off the frame grid")
    else:
        lines.append(f"✓ timestamps even (deviation {dev * 1000:.1f} ms)")
    d_old, d_new = vdur(old), vdur(new)
    if d_old and d_new and abs(d_old - d_new) > 1.5 / fps:
        ok = False
        lines.append(f"✗ duration {d_new:.3f} s, was {d_old:.3f} s")
    elif d_old and d_new:
        lines.append(f"✓ duration {d_new:.3f} s")
    pts = [n for n in points if 0 <= n < n_old and not (edit_a <= n <= edit_b)]
    olds = frames_at(old, [m for n in pts for m in (n - 1, n, n + 1) if m < n_old], work / "chk", "old")
    news = frames_at(new, pts, work / "chk", "new")
    for n in pts:
        if n not in news:
            ok = False
            lines.append(f"✗ frame {n}: could not be extracted from the new file")
            continue
        o = {m: olds[m] for m in (n - 1, n, n + 1) if m in olds}
        w = {n: news[n]}
        scores = {m: psnr(w[n], o[m]) for m in o}
        best = max(scores, key=lambda m: scores[m])
        val = scores.get(n, 0.0)
        txt = "inf" if val == float("inf") else f"{val:.1f} dB"
        # a shift only if a neighboring old frame matches noticeably better and itself differs from old frame n
        # (on still frames, such as a pause or the end of an insert, the neighbors are identical up to 79 dB and the
        # "best" among them is random)
        if best != n and scores[best] - val > 1.0 and psnr(o[n], o[best]) < 50 if n in o else False:
            ok = False
            lines.append(f"✗ frame {n}: matches old frame {best} ({scores[best]:.1f} dB), not {n} ({txt}): a shift at the join")
        elif val < PSNR_MIN:
            ok = False
            lines.append(f"✗ frame {n}: PSNR against the old one {txt} < {PSNR_MIN:.0f}")
        else:
            lines.append(f"✓ frame {n} ({n / fps:.2f} s): matches the old one, {txt}")
    return ok, lines


def seams_sheet(new, fps, points, out_jpg, work):
    got = frames_at(new, points, work / "sheet", "s")
    frames = [got[n] for n in sorted(got)]
    if not frames:
        return None
    args = ["ffmpeg", "-v", "error", "-y"]
    for f in frames:
        args += ["-i", str(f)]
    if len(frames) == 1:
        fc = "[0:v]scale=270:-2"
    else:
        fc = "".join(f"[{k}:v]scale=270:-2[v{k}];" for k in range(len(frames)))
        fc += "".join(f"[v{k}]" for k in range(len(frames))) + f"hstack=inputs={len(frames)}"
    run(args + ["-filter_complex", fc, "-frames:v", "1", str(out_jpg)], what="ffmpeg (sheet of joins)")
    return out_jpg


def main():
    ap = argparse.ArgumentParser(description="re-render a segment of a video and splice it into the finished render")
    ap.add_argument("render", help="the finished Remotion render (not -master: rebuild the master after the patch)")
    ap.add_argument("--comp", required=True, help="the Remotion composition, e.g. Reel4821")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from", dest="t_from", type=float, help="start of the fix, s (render timeline)")
    g.add_argument("--frames", help="frames of the fix A-B (inclusive)")
    ap.add_argument("--to", dest="t_to", type=float, help="end of the fix, s")
    ap.add_argument("-o", "--out", help="output (default <render>-patched.mp4)")
    ap.add_argument("--in-place", action="store_true", help="after the check, replace the render; the old one -> .prev.mp4")
    ap.add_argument("--mode", choices=["auto", "copy", "reencode"], default="auto")
    ap.add_argument("--audio", choices=["keep", "rerender"], default="keep")
    ap.add_argument("--remotion", help="the Remotion project folder (default: searched upwards from the render)")
    ap.add_argument("--props", help="--props for Remotion")
    ap.add_argument("--keep-temp", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    old = Path(a.render).resolve()
    if not old.exists():
        sys.exit(f"no file {old}")
    if old.stem.endswith("-master"):
        print("⚠ this is a master: better patch the render itself, then rebuild the master with master_audio.py")
    rem = find_remotion(old, a.remotion)
    meta = probe_video(old)
    fps, n_old = meta["fps"], meta["frames"]
    if a.frames:
        A, B = (int(x) for x in a.frames.split("-"))
    else:
        if a.t_to is None:
            sys.exit("--to is needed together with --from")
        A, B = int(a.t_from * fps), int(round(a.t_to * fps))
    A, B = max(0, min(A, B)), min(n_old - 1, max(A, B))
    ks = keyframes(old, fps)
    k1 = max([k for k in ks if k <= A] or [0])
    k2 = min([k for k in ks if k > B] or [n_old])
    print(f"render: {old.name}: {n_old} frames, {fps:g} fps, {len(ks)} keyframes")
    print(f"fix: frames {A}-{B} ({A / fps:.2f}-{(B + 1) / fps:.2f} s) -> patch between keyframes {k1}-{k2 - 1} "
          f"({k1 / fps:.2f}-{k2 / fps:.2f} s, {k2 - k1} of {n_old} frames)")

    work = Path(tempfile.mkdtemp(prefix="patch_"))
    out = Path(a.out).resolve() if a.out else old.with_name(old.stem + "-patched.mp4")
    try:
        # 1. the patch in Remotion
        patch = work / "patch.mp4"
        cmd = [npx(), "--no", "remotion", "render", a.comp, str(patch), f"--frames={k1}-{k2 - 1}", "--muted", "--log=error"]
        if a.props:
            cmd.append(f"--props={a.props}")
        t = time.time()
        run(cmd, cwd=rem, what="patch render (Remotion)")
        pm = probe_video(patch)
        if pm["frames"] != k2 - k1:
            sys.exit(f"patch: {pm['frames']} frames instead of {k2 - k1}")
        for key in ("width", "height", "fps"):
            if pm[key] != meta[key]:
                sys.exit(f"the patch does not match the render in {key}: {pm[key]} ≠ {meta[key]}")
        print(f"patch rendered in {time.time() - t:.0f} s")

        # 2. audio
        audio_src = old if has_audio(old) else None
        if a.audio == "rerender":
            t = time.time()
            wav = work / "audio.wav"
            cmd = [npx(), "--no", "remotion", "render", a.comp, str(wav), "--codec=wav", "--log=error"]
            if a.props:
                cmd.append(f"--props={a.props}")
            run(cmd, cwd=rem, what="audio render (Remotion)")
            audio_src = wav
            print(f"audio re-rendered in {time.time() - t:.0f} s")

        def mux(video_only, dst):
            args = ["ffmpeg", "-v", "error", "-y", "-i", str(video_only)]
            if audio_src is not None:
                args += ["-i", str(audio_src), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"]
                args += ["-c:a", "copy"] if audio_src == old else ["-c:a", "aac", "-b:a", "320k"]
            else:
                args += ["-map", "0:v:0", "-c:v", "copy"]
            run(args + ["-movflags", "+faststart", str(dst)], what="ffmpeg (muxing with audio)")

        def build_copy():
            cuts = [k for k in (k1, k2) if 0 < k < n_old]
            segdir = work / "seg"
            segdir.mkdir()
            if cuts:
                run(["ffmpeg", "-v", "error", "-y", "-i", str(old), "-map", "0:v:0", "-c", "copy", "-f", "segment",
                     "-segment_frames", ",".join(map(str, cuts)), "-reset_timestamps", "1",
                     str(segdir / "s%03d.mp4")], what="ffmpeg (cutting at keyframes)")
            segs = sorted(segdir.glob("s*.mp4"))
            parts = []
            idx = 0
            if k1 > 0:
                parts.append(segs[idx]); idx += 1
            parts.append(patch); idx += 1 if cuts else 0
            if k2 < n_old:
                parts.append(segs[idx])
            ref = segs[1] if k1 > 0 and len(segs) > 1 else (segs[0] if segs else None)
            if ref is not None and extradata(ref) != extradata(patch):
                return None, "the codec parameters of the patch and the render don't match (avcC)"
            lst = work / "concat.txt"
            lst.write_text("".join(f"file '{p.relative_to(work).as_posix()}'\n" for p in parts), encoding="utf-8")
            vid = work / "video_copy.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(vid)],
                what="ffmpeg (splice without re-encoding)")
            dst = work / "out_copy.mp4"
            mux(vid, dst)
            return dst, None

        def build_reencode():
            fc, labels = "[0:v]split=2[o1][o2];", []
            if k1 > 0:
                fc += f"[o1]trim=end_frame={k1},setpts=PTS-STARTPTS[a];"
                labels.append("[a]")
            else:
                fc += "[o1]nullsink;"
            fc += "[1:v]setpts=PTS-STARTPTS[b];"
            labels.append("[b]")
            if k2 < n_old:
                fc += f"[o2]trim=start_frame={k2},setpts=PTS-STARTPTS[c];"
                labels.append("[c]")
            else:
                fc += "[o2]nullsink;"
            fc += "".join(labels) + f"concat=n={len(labels)}:v=1:a=0[v]"
            vid = work / "video_re.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-i", str(old), "-i", str(patch), "-filter_complex", fc, "-map", "[v]",
                 "-r", f"{fps:g}", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", meta["pix_fmt"],
                 str(vid)], what="ffmpeg (splice with re-encoding)")
            dst = work / "out_re.mp4"
            mux(vid, dst)
            return dst, None

        points = sorted({k1 - 1, k1, k2 - 1, k2})
        result, report, used = None, [], None
        if a.mode in ("auto", "copy"):
            t = time.time()
            dst, why = build_copy()
            if dst is None:
                print(f"⚠ copy is impossible: {why}" + (" -> reencode" if a.mode == "auto" else ""))
                if a.mode == "copy":
                    sys.exit(1)
            else:
                ok, report = check(old, dst, fps, n_old, points, A, B, work)
                print(f"copy: splice + check in {time.time() - t:.0f} s")
                if ok:
                    result, used = dst, "copy"
                elif a.mode == "copy":
                    print("\n".join(report))
                    sys.exit("✗ the copy check failed")
                else:
                    print("⚠ the copy check failed -> reencode:\n  " + "\n  ".join(l for l in report if l.startswith("✗")))
        if result is None:
            t = time.time()
            dst, _ = build_reencode()
            ok, report = check(old, dst, fps, n_old, points, A, B, work)
            print(f"reencode: splice + check in {time.time() - t:.0f} s")
            if not ok:
                print("\n".join(report))
                sys.exit("✗ the reencode check failed: a full render is needed")
            result, used = dst, "reencode"

        print("\n".join(report))
        if a.in_place:
            prev = old.with_name(old.stem + ".prev.mp4")
            if prev.exists():
                prev.unlink()
            os.replace(old, prev)
            shutil.move(str(result), str(old))
            final = old
            print(f"old render -> {prev.name}")
        else:
            shutil.move(str(result), str(out))
            final = out
        sheet = seams_sheet(final, fps, [p for p in points if 0 <= p < n_old], final.with_name(final.stem + "-seams.jpg"), work)
        print(f"done ({used}, {time.time() - t0:.0f} s): {final}")
        if sheet:
            print(f"joins (frames {', '.join(str(p) for p in points if 0 <= p < n_old)}): {sheet}")
        print("next: master_audio.py -> -master, faces.py audit")
    finally:
        if a.keep_temp:
            print(f"temporary files: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
