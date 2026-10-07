# -*- coding: utf-8 -*-
"""Audio mastering of a finished render: −14 LUFS, true peak ≤ −1 dBFS, music set below the voice.

    python scripts/master_audio.py out/render.mp4 -o out/<brand>-<slug>-<date>-master.mp4 --cover edit/<id>/cover.jpg
    python scripts/master_audio.py out/render.mp4 -o out/master.mp4                # no cover: a warning
    python scripts/master_audio.py out/render.mp4 -o out/master.mp4 --music track.mp3 [--gap 15] \\
        [--music-start 12.4 | --drop-at 24.1 --drop-in-track 61.0] [--duck 21.3-23.9[:-14] ...]
    python scripts/master_audio.py track.mp3 --find-drops          # where the drops are in a track (candidates)
    python scripts/master_audio.py out/master.mp4 --check          # only the acceptance check of a finished master
    python scripts/master_audio.py out/old-master.mp4 --check --no-loudness   # scene sounds only, mastered before the tag
    python scripts/master_audio.py out/render.mp4 -o out/master.mp4 --sfx edit/<id>/sfx.json   # + scene sound accents

Voice chain (the render's audio, together with the sound effects):
  measure the noise floor → noise reduction ONLY if the floor is louder than −50 dBFS (on a clean recording it causes
  artifacts) → highpass 80 Hz → two-pass loudnorm to −14 LUFS, TP −1.5, headroom for AAC (single-pass drifts off target).
Scene sounds (--sfx, if any): the kit does not play them (types.ts: "sound is chosen at mixing"); they are mixed into the
  render's audio before the voice chain, each placed by the start of its sound, not of the file, with its peak
  `below_voice_db` (15) under the voice peak unless `gain_db` is set:
    {"below_voice_db": 15, "sounds": [{"file": "<library>/hit.ogg", "at": 0.10, "start": 0.0, "what": "hook enters"}]}
  at: the second of the video; start: the sound start in the file (the library catalog's "sound start" column); file:
  absolute or relative to the project folder (or to the sfx.json folder).
Music (if any): the bed is normalized to an absolute target (gap 15 dB → −24 LUFS, 13 → −22,
  17 → −26), ducks under the voice with a sidechain (ratio 3, threshold 0.10, attack 20, release 380),
  and the final mix is brought to −14 LUFS again. The track is cut by meaning: the track's drop (its sharpest rise,
  --find-drops) lands on the final phrase (--drop-at, --drop-in-track).
Ducking under a key line (--duck A-B[:dB], repeatable, seconds of the render): the music goes down by dB (−14 by
  default) for that window, with 0.2 s fades on both sides, so the line is heard in near silence; it is applied to
  the music after the sidechain, before the mix, and the voice is not touched. Two different things: "duck the music
  under the key line" (--duck) and "the track's drop" (a loud moment of the track itself, placed with --drop-at).
The video is not re-encoded: the audio goes into the finished render (-c:v copy), +faststart.
The cover (--cover edit/<id>/cover.jpg, picked with poster.py pick): the master is built with it in one run — frame 0
  replaced by the cover (poster.py bake: the only re-encode, frame count and durations checked), the sound mastered, the
  cover embedded as cover art (poster.py attach: the file manager's thumbnail) — and the cover is saved next to the
  master as a picture for uploading it by hand: <name>-cover.jpg (out/x-master.mp4 -> out/x-cover.jpg). One file goes
  out, the master; there is no separate "-final.mp4". Without --cover the master is made as before, with a warning:
  messengers show its first frame and file managers a random one.
At the end, the acceptance check from the checklist (SKILL.md): −14 ±0.7 LUFS, true peak ≤ −1 dBFS, audio = video track
(and video = input). Exit code: 0, the check passed; 1, it failed, a measurement failed or ffmpeg failed.
No voice and no music (the "scenes only" format): a few scene sounds over silence are not a −14 LUFS track, so the
loudness is not required, the true peak and the durations are; a render with no sound and no --sfx is copied as is
(no audio track, only the durations count). Such a master carries the mp4 comment tag "it-reelsmaker master: …" and
--check reads it and applies the same rule (poster.py attach copies the tag); for a file mastered before the tag:
--check --no-loudness.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import local_media_args

TARGET, TP = -14.0, -1.0
TP_PROC = -1.5   # loudnorm target with headroom for AAC: the encoder adds ~0.2 dB or more to the true peak
                 # (measured: −1.0 dBFS in PCM → −0.8 after aac 256k), and the acceptance check runs on the finished file
LUFS_TOL = 0.7    # −14 ±0.7 LUFS
TP_EPS = 0.05     # ebur128 prints the peak to 0.1: "−1.0" with a −1 target passes, "−0.9" does not
DUR_TOL = 0.1     # audio vs. video track and video vs. input, s
TAG = "it-reelsmaker master: "  # mp4 comment of a master the −14 LUFS rule does not apply to (--check reads it back)
TAG_NO_VOICE = TAG + "no voice, scene sounds only (no -14 LUFS target)"
TAG_NO_SOUND = TAG + "no sound track (scenes only)"


def run(args):
    r = subprocess.run(local_media_args(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + r.stderr[-1500:])
    return r


def dur(p, stream="v"):
    """Duration of the VIDEO track (stream="a": the audio track): a render's audio can be a fraction of a second longer
    than the video, and the master is cut to the video. No audio track: None."""
    out = run(["ffprobe", "-v", "error", "-select_streams", f"{stream}:0", "-show_entries", "stream=duration",
               "-of", "csv=p=0", p]).stdout.strip().strip(",")
    if stream == "a":
        try:
            return float(out)
        except ValueError:
            return None
    if not out or out == "N/A":
        out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).stdout
    return float(out)


def noise_floor(p):
    """Noise floor: the 10th percentile of RMS over 50 ms windows (the pauses between words), dBFS."""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", p, "-vn", "-ac", "1", "-af",
             "asetnsamples=2400,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
             "-f", "null", "-"])
    v = sorted(float(x) for x in re.findall(r"RMS_level=(-?[\d.]+)", r.stderr) if x not in ("-inf",))
    return v[int(len(v) * 0.10)] if v else -90.0


def loudnorm_2pass(inp, out, pre, target):
    """Two-pass loudnorm in linear mode; pre: the filters before normalization."""
    f1 = (pre + "," if pre else "") + f"loudnorm=I={target}:TP={TP_PROC}:LRA=11:print_format=json"
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", inp, "-vn", "-af", f1, "-f", "null", "-"])
    m = json.loads(r.stderr[r.stderr.rfind("{"): r.stderr.rfind("}") + 1])
    f2 = (pre + "," if pre else "") + (
        f"loudnorm=I={target}:TP={TP_PROC}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
        f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    run(["ffmpeg", "-y", "-hide_banner", "-i", inp, "-vn", "-af", f2, "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", out])
    return float(m["input_i"])


def measure(p):
    """Integrated loudness and true peak via ebur128; (None, None) if the measurement failed."""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", p, "-af", "ebur128=peak=true", "-f", "null", "-"])
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    tp = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", r.stderr)
    try:
        return float(i[-1]), float(tp[-1])
    except (IndexError, ValueError):
        return None, None


def master_tag(p):
    """The file's mp4 comment when it is this script's no-voice tag (TAG_NO_VOICE / TAG_NO_SOUND), else None."""
    out = run(["ffprobe", "-v", "error", "-show_entries", "format_tags=comment", "-of", "default=nw=1:nk=1", p]).stdout.strip()
    return out if out.startswith(TAG) else None


def acceptance(p, d_in=None, loudness=True, sound=True):
    """Acceptance check of the master by the checklist → (measurement line, list of failures). d_in: the input's video
    duration; loudness=False: no −14 LUFS requirement (scene sounds over silence), the true peak is still checked;
    sound=False: no audio track by design (a silent "scenes only" video), only the durations are checked."""
    dv, da = dur(p), dur(p, "a")
    if not sound and da is None:
        fails = [f"video {dv:.2f} s ≠ input {d_in:.2f} s"] if d_in is not None and abs(dv - d_in) > DUR_TOL else []
        return f"no audio track (a video without sound), video {dv:.2f} s", fails
    i1, tp1 = measure(p)
    fails = []
    if i1 is None or tp1 is None:
        fails.append("the ebur128 measurement failed: loudness and peak are unknown")
    else:
        if loudness and abs(i1 - TARGET) > LUFS_TOL + 1e-6:
            fails.append(f"loudness {i1:.1f} LUFS is outside {TARGET:.0f} ±{LUFS_TOL}")
        if tp1 > TP + TP_EPS + 1e-6:
            fails.append(f"true peak {tp1:.1f} dBFS is above {TP:.0f} dBFS")
    if da is None:
        fails.append("the file has no audio track")
    elif abs(da - dv) > DUR_TOL:
        fails.append(f"audio {da:.2f} s ≠ video track {dv:.2f} s")
    if d_in is not None and abs(dv - d_in) > DUR_TOL:
        fails.append(f"video {dv:.2f} s ≠ input {d_in:.2f} s")
    line = (f"{'?' if i1 is None else f'{i1:.1f}'} LUFS, true peak {'?' if tp1 is None else f'{tp1:.1f}'} dBFS, "
            f"video {dv:.2f} s, audio {'—' if da is None else f'{da:.2f}'} s" + (f" (input {d_in:.2f} s)" if d_in is not None else ""))
    return line, fails


def report(line, fails):
    print(f"output: {line} → {'OK' if not fails else 'ACCEPTANCE CHECK FAILED'}")
    for x in fails:
        print("✗ " + x)
    return 1 if fails else 0


def find_drops(track):
    """Drop candidates: the sharpest rise of short-term loudness (3 s window) within 1.5 s."""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", track, "-af", "ebur128=metadata=1,"
             "ametadata=print:key=lavfi.r128.S", "-f", "null", "-"])
    pts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    s = [float(x) for x in re.findall(r"lavfi\.r128\.S=(-?[\d.]+)", r.stderr)]
    pairs = list(zip(pts, s))
    cands = []
    for k, (t, v) in enumerate(pairs):
        prev = [pv for pt, pv in pairs[max(0, k - 150):k] if t - pt <= 1.5]
        # during the first 4 s the S window is still filling, and a rise "from silence" is an intro, not a drop
        if prev and v > -60 and t >= 4 and min(prev) > -45:
            cands.append((v - min(prev), t, v))
    cands.sort(reverse=True)
    picked = []
    for rise, t, v in cands:
        if all(abs(t - p[1]) > 8 for p in picked):
            picked.append((rise, t, v))
        if len(picked) == 3:
            break
    for rise, t, v in sorted(picked, key=lambda x: x[1]):
        print(f"drop candidate ~{t:.1f} s: rise of {rise:.1f} LU to {v:.1f} LUFS(S)")


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--music")
    ap.add_argument("--gap", type=float, default=15.0, help="voice − music gap, dB (13 louder … 17 quieter)")
    ap.add_argument("--music-start", type=float, default=None, help="the second of the track to start from")
    ap.add_argument("--drop-at", type=float, help="the second of the video to land the drop on (the final phrase)")
    ap.add_argument("--drop-in-track", type=float, help="the second of the drop in the track (see --find-drops)")
    ap.add_argument("--find-drops", action="store_true")
    ap.add_argument("--check", action="store_true", help="only the acceptance check of a finished master, no processing")
    ap.add_argument("--no-loudness", action="store_true", help="with --check: no −14 LUFS requirement (scene sounds over "
                                                               "silence, a master made before the tag); the peak still counts")
    ap.add_argument("--no-denoise", action="store_true")
    ap.add_argument("--sfx", help="edit/<id>/sfx.json: scene sound accents mixed in before mastering")
    ap.add_argument("--duck", action="append", default=[], metavar="A-B[:dB]",
                    help="duck the music under a key line: seconds of the render, dB down (default 14), repeatable")
    ap.add_argument("--cover", help="edit/<id>/cover.jpg (poster.py pick): frame 0, the embedded cover art and "
                                    "<name>-cover.jpg next to the master, in this run")
    a = ap.parse_args()
    if a.find_drops:
        find_drops(a.input)
        return
    if a.check:
        tag = master_tag(a.input)
        loud = not (a.no_loudness or tag)
        if not loud:
            print(f"no voice: the −14 LUFS rule does not apply ({'--no-loudness' if a.no_loudness else tag}); the true "
                  f"peak and the durations are checked")
        print("cover art: " + ("embedded" if has_cover_art(a.input) else
                                "none (master_audio.py ... --cover edit/<id>/cover.jpg builds the master with it)"))
        sys.exit(report(*acceptance(a.input, loudness=loud, sound=tag != TAG_NO_SOUND)))
    if not a.output:
        sys.exit("-o <output.mp4> is required")
    if a.cover and not Path(a.cover).is_file():
        sys.exit(f"cover not found: {a.cover} (poster.py pick edit/<id> --render <render> -o edit/<id>/cover.jpg)")
    if a.cover and Path(a.output).resolve() == Path(a.input).resolve():
        sys.exit("-o must differ from the input")
    if not a.cover:
        print("⚠ no cover (--cover): the master's frame 0 is the render's first frame (what messengers show) and a file "
              "manager picks a random frame; poster.py pick edit/<id> --render <render> -o edit/<id>/cover.jpg, then "
              "master again with --cover edit/<id>/cover.jpg")

    a.ducks = parse_ducks(a.duck)
    if a.ducks and not a.music:
        print("⚠ --duck needs --music: there is no music to duck, ignored")
    tmp = tempfile.mkdtemp(prefix="master_")
    try:
        code = with_cover(a, tmp) if a.cover else master(a, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(code)


def poster(*args):
    """poster.py bake / attach in a child process: their own checks decide (exit code 1 = do not deliver)."""
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "poster.py"), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr).strip()
    if out:
        print("\n".join("  " + line for line in out.splitlines()))
    return r.returncode


def has_cover_art(p):
    r = subprocess.run(local_media_args(["ffprobe", "-v", "error", "-show_entries",
                                         "stream=codec_type:stream_disposition=attached_pic", "-of", "json", str(p)]),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return any((s.get("disposition") or {}).get("attached_pic") for s in json.loads(r.stdout).get("streams", []))
    except ValueError:
        return False


def cover_jpg_of(output):
    """The cover picture next to the master: out/x-master.mp4 -> out/x-cover.jpg (out/x.mp4 -> out/x-cover.jpg)."""
    p = Path(output)
    stem = p.stem[:-len("-master")] if p.stem.endswith("-master") else p.stem
    return p.with_name(stem + "-cover.jpg")


def with_cover(a, tmp):
    """The master with its cover in one run: bake frame 0 -> master the sound -> attach the cover art -> the jpg."""
    out, cover = Path(a.output), Path(a.cover)
    baked = os.path.join(tmp, "cover.mp4")
    print(f"cover: frame 0 <- {cover.name} (poster.py bake)")
    if poster("bake", a.input, "--cover", cover, "-o", baked):
        print("the cover could not be put into frame 0: no master was made; check the cover and the render")
        return 1
    a.input, a.output = baked, os.path.join(tmp, "master.mp4")
    code = master(a, tmp)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"cover: embedded as cover art (poster.py attach) -> {out}")
    if poster("attach", a.output, "--cover", cover, "-o", out):
        return 1
    jpg = cover_jpg_of(out)
    if jpg.resolve() == cover.resolve():  # remastering from the sidecar itself: ffmpeg can't write its own input (PR review)
        print(f"cover picture for uploading it by hand: {jpg} (the cover given, kept as it is)")
    else:
        run(["ffmpeg", "-y", "-hide_banner", "-i", str(cover), "-frames:v", "1", "-q:v", "2", str(jpg)])
        print(f"cover picture for uploading it by hand: {jpg}")
    print("file:", str(out) + ("" if not code else " — do not publish it; deal with the failure first"))
    return code


DUCK_DB = -14.0   # dB: the music under a key line, against the bed around it ("near silence", references/library.md)
DUCK_FADE = 0.2   # s: the fade down before the window and back up after it


def parse_ducks(specs):
    """--duck "A-B[:dB]" -> [(A, B, dB)]: the window in seconds of the render and how far down (a negative dB; "14"
    and "-14" mean the same)."""
    out = []
    for spec in specs:
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?::\s*([+-]?\d+(?:\.\d+)?))?\s*", spec)
        if not m or float(m.group(2)) <= float(m.group(1)):
            sys.exit(f"--duck {spec!r}: expected START-END[:dB] in seconds of the render, END after START (21.3-23.9:-14)")
        db = -abs(float(m.group(3))) if m.group(3) is not None else DUCK_DB
        out.append((float(m.group(1)), float(m.group(2)), db))
    return out


def duck_filter(ducks, D):
    """An ffmpeg volume filter that ducks the music in each window (linear DUCK_FADE fades outside it), or "" without
    windows. A window that starts after the video's end is an error; one that runs over it is clipped."""
    terms = []
    for a0, b0, db in ducks:
        if a0 >= D:
            sys.exit(f"--duck {a0:g}-{b0:g}: starts after the video's end ({D:.2f} s)")
        g, f, b0 = 10 ** (db / 20), DUCK_FADE, min(b0, D)
        k = f"min(clip((t-{a0 - f:.3f})/{f},0,1),clip(({b0 + f:.3f}-t)/{f},0,1))"
        terms.append(f"(1-{1 - g:.6f}*{k})")
        print(f"music ducked under a key line: {a0:.2f}-{b0:.2f} s by {db:.0f} dB (fades {f:g} s)")
    return f"volume='{'*'.join(terms)}':eval=frame" if terms else ""


def music_start(a):
    start = a.music_start
    if a.drop_at is not None and a.drop_in_track is not None:
        start = max(0.0, a.drop_in_track - a.drop_at)  # the track's drop lands on the final phrase
    return start or 0.0


def master_no_voice(a, tmp, D, why):
    """A render without sound (the "scenes only" format): loudnorm fails on silence (measured_I = −inf).
    Without --music and --sfx: skipped with a message, the file is copied as is; with --music: the music is mastered
    to −14 LUFS; scene sounds (--sfx) go onto the music, or onto silence, NO_VOICE_BELOW dB under its peak."""
    if not a.music and not sfx_sounds(a):
        # the silent track a render may carry is left out: the tag says "no sound track", and --check of a file with
        # a silent track fell through to the loudness measurement, which fails on silence (Codex review)
        run(["ffmpeg", "-y", "-hide_banner", "-i", a.input, "-map", "0", "-map", "-0:a", "-c", "copy",
             "-metadata", f"comment={TAG_NO_SOUND}", "-movflags", "+faststart", a.output])
        print(f"{why}: no voice and no effects, mastering skipped, the file is copied as is (+faststart)"
              + ("" if a.cover else f": {a.output}"))
        print("the −14 LUFS check does not apply to a video without sound: add music in the app when publishing, or a "
              "track with a commercial license via --music; scene sounds (--sfx) go onto silence, with the true peak "
              "checked and no −14 LUFS target")
        return 0
    final = os.path.join(tmp, "final.wav")
    if a.music:
        start = music_start(a)
        mcut = os.path.join(tmp, "music_cut.wav")
        # the track can end before the video: fade out at the end of the music itself, then silence up to D (apad);
        # otherwise -shortest in the mix would cut the video at the end of the track
        mlen = max(0.0, min(D, (dur(a.music, "a") or D) - start))
        if mlen < D - 0.05:
            print(f"⚠ the track from {start:.2f} s ends after {mlen:.1f} s, but the video is {D:.1f} s: silence at the end "
                  f"(take a longer track or start earlier: --music-start)")
        fade = min(1.2, mlen)
        duck = duck_filter(getattr(a, "ducks", []), D)
        run(["ffmpeg", "-y", "-hide_banner", "-ss", f"{start:.3f}", "-t", f"{D:.3f}", "-i", a.music, "-af",
             f"afade=t=in:d=0.5,afade=t=out:st={max(0, mlen - fade):.3f}:d={fade:.3f},apad=whole_dur={D:.3f}"
             + (f",{duck}" if duck else ""), "-ar", "48000", "-ac", "2", mcut])
        loudnorm_2pass(mcut, final, "", TARGET)
        print(f"{why}: no voice; the music from {start:.2f} s of the track, at {TARGET:.0f} LUFS")
        ref = peak_db(final)
    else:
        run(["ffmpeg", "-y", "-hide_banner", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{D:.3f}",
             "-c:a", "pcm_s16le", final])
        print(f"{why}: no voice and no music; the scene sounds go onto silence")
        ref = -1.0
    if sfx_sounds(a):
        mixed = mix_sfx(a, tmp, D, base=final, ref=ref, below=NO_VOICE_BELOW)
        # sounds that meet in phase add up over 0 dBFS: a limiter under the true-peak ceiling, as on the voice chain
        final = os.path.join(tmp, "final_limited.wav")
        run(["ffmpeg", "-y", "-hide_banner", "-i", mixed, "-af", f"alimiter=limit={10 ** ((TP - 0.5) / 20):.3f}:level=false",
             "-c:a", "pcm_s16le", final])
    # --check reads the tag: the same rule as here. With music the master needs -14 LUFS: a tag the input carries
    # (a silent master made earlier) is cleared, or ffmpeg copies it over and --check skips the loudness (Codex review)
    tag = (["-metadata", "comment="] if master_tag(a.input) else []) if a.music else ["-metadata", f"comment={TAG_NO_VOICE}"]
    run(["ffmpeg", "-y", "-hide_banner", "-i", a.input, "-i", final, "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest", *tag, "-movflags", "+faststart",
         a.output])
    if not a.music:  # a few accents over silence are not a −14 LUFS track; the true peak still counts
        print("scene sounds only: the −14 LUFS check does not apply (add music in the app when publishing, or a "
              "licensed track via --music); the true peak and the durations are checked")
    code = report(*acceptance(a.output, D, loudness=bool(a.music)))
    if not a.cover:
        print("file:", a.output + ("" if not code else " — do not publish it; deal with the failure first"))
    return code


def peak_db(p):
    m = re.search(r"max_volume: (-?[\d.]+) dB", run(["ffmpeg", "-hide_banner", "-nostats", "-i", p, "-af", "volumedetect",
                                                      "-f", "null", "-"]).stderr)
    return float(m.group(1)) if m else None


NO_VOICE_BELOW = 6.0  # no voice: an accent sits this much under the music's peak (or under −1 dBFS over silence)


def sfx_sounds(a):
    """The sounds of --sfx (a list, empty without --sfx)."""
    if not a.sfx:
        return []
    doc = json.load(open(a.sfx, encoding="utf-8"))
    return (doc.get("sounds", []) if isinstance(doc, dict) else doc) or []


def mix_sfx(a, tmp, D, base=None, ref=None, below=None):
    """The audio (the render's, or base) with the scene sounds of --sfx mixed in (a WAV), or it unchanged without
    --sfx. Each sound's peak: `below` dB under the reference peak (the voice's; ref when given)."""
    src = base or a.input
    sounds = sfx_sounds(a)
    if not sounds:
        return src
    doc = json.load(open(a.sfx, encoding="utf-8"))
    voice = ref if ref is not None else peak_db(src)
    if below is None:
        below = float((doc.get("below_voice_db") if isinstance(doc, dict) else None) or 15)
    base = [Path.cwd(), Path(a.sfx).resolve().parent]
    ins, chains = ["-i", src], []
    for k, s in enumerate(sounds, 1):
        f = next((b / s["file"] for b in base if (b / s["file"]).is_file()), Path(s["file"]))
        if not f.is_file():
            sys.exit(f"--sfx: no sound file {s['file']}")
        at, start = float(s["at"]), float(s.get("start") or 0)
        if not 0 <= at < D:
            sys.exit(f"--sfx: {f.name} at {at} s is outside the video (0–{D:.2f} s)")
        gain = s.get("gain_db")
        if gain is None:
            gain = (voice - below) - (peak_db(str(f)) or 0)
        ins += ["-i", str(f)]
        # the file's sound start lands on `at`: delayed when it comes later, the file's head trimmed when earlier
        place = (f"adelay=delays={round((at - start) * 1000)}:all=1" if at >= start else
                 f"atrim=start={start - at:.3f},asetpts=PTS-STARTPTS")
        chains.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,{place},volume={float(gain):.1f}dB[s{k}]")
        print(f"sound: {f.name} at {at:.2f} s ({s.get('what') or ''}), gain {float(gain):+.1f} dB")
    out = os.path.join(tmp, "with_sfx.wav")
    fc = (";".join(chains) + f";[0:a]aresample=48000,aformat=channel_layouts=stereo[v];[v]" + "".join(f"[s{k}]" for k in range(1, len(sounds) + 1))
          + f"amix=inputs={len(sounds) + 1}:normalize=0:duration=first[a]")
    run(["ffmpeg", "-y", "-hide_banner", *ins, "-filter_complex", fc, "-map", "[a]", "-c:a", "pcm_s16le", out])
    print(f"scene sounds: {len(sounds)}, {below:.0f} dB under the reference peak ({voice:.1f} dBFS)")
    return out


def master(a, tmp):
    D = dur(a.input)
    if dur(a.input, "a") is None:
        return master_no_voice(a, tmp, D, "the render has no audio track")
    i0, tp0 = measure(a.input)
    if i0 is not None and (tp0 == float("-inf") or i0 <= -69.5):  # ebur128 gives −70 LUFS and a −inf peak on silence
        return master_no_voice(a, tmp, D, f"the render's audio is silence ({i0:.0f} LUFS)")
    if i0 is None:
        sys.exit(f"measuring the input failed (ebur128): is there audio in {a.input}?")
    nf = noise_floor(a.input)
    pre = "highpass=f=80"
    denoise = nf > -50 and not a.no_denoise
    if denoise:
        pre = "afftdn=nf=-50," + pre
    print(f"input: {i0:.1f} LUFS, peak {tp0:.1f} dBFS, noise floor {nf:.1f} dBFS → noise reduction {'YES' if denoise else 'no'}")

    voice = os.path.join(tmp, "voice.wav")
    loudnorm_2pass(mix_sfx(a, tmp, D), voice, pre, TARGET)
    mix = voice

    if a.music:
        # The music is normalized to an absolute target, not as a "percentage of the track's volume":
        # with the voice at −14 and a 15 dB gap, the bed is −24 LUFS... in the pauses. Under speech the sidechain
        # pushes it down further, so the bed itself is set to (−14 − gap + 5): 15 → −24, 13 → −22, 17 → −26.
        mtarget = TARGET - a.gap + 5
        start = music_start(a)
        mus = os.path.join(tmp, "music.wav")
        mcut = os.path.join(tmp, "music_cut.wav")
        run(["ffmpeg", "-y", "-hide_banner", "-ss", f"{start:.3f}", "-t", f"{D + 2:.3f}", "-i", a.music,
             "-ar", "48000", "-ac", "2", mcut])
        loudnorm_2pass(mcut, mus, "", mtarget)
        mix = os.path.join(tmp, "mix.wav")
        # sidechaincompress outputs about a second less than it receives → apad on both inputs, atrim on the output;
        # the key-line duck (--duck) goes after the sidechain, so the window is exactly that much below the bed
        duck = duck_filter(a.ducks, D)
        fc = (f"[0:a]apad=pad_dur=2,asplit=2[v][sc];"
              f"[1:a]apad=pad_dur=2,afade=t=in:d=0.5,afade=t=out:st={max(0, D - 1.2):.3f}:d=1.2[m];"
              f"[m][sc]sidechaincompress=threshold=0.10:ratio=3:attack=20:release=380"
              + (f",{duck}" if duck else "") + "[md];"
              f"[v][md]amix=inputs=2:duration=first:normalize=0,atrim=0:{D:.3f}[a]")
        run(["ffmpeg", "-y", "-hide_banner", "-i", voice, "-i", mus, "-filter_complex", fc, "-map", "[a]",
             "-c:a", "pcm_s16le", mix])
        final = os.path.join(tmp, "final.wav")
        loudnorm_2pass(mix, final, "", TARGET)  # the final mix back to −14
        mix = final
        print(f"music: from {start:.2f} s of the track, bed {mtarget:.0f} LUFS, gap ~{a.gap:.0f} dB, sidechain 3:1")

    clear = ["-metadata", "comment="] if master_tag(a.input) else []  # a voice master is checked for -14 LUFS
    run(["ffmpeg", "-y", "-hide_banner", "-i", a.input, "-i", mix, "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest", *clear, "-movflags", "+faststart",
         a.output])
    code = report(*acceptance(a.output, D))
    if not a.cover:
        print("file:", a.output + ("" if not code else " — do not publish it; deal with the failure first"))
    return code


if __name__ == "__main__":
    main()
