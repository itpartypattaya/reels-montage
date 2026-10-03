# -*- coding: utf-8 -*-
"""Audio mastering of a finished render: −14 LUFS, true peak ≤ −1 dBFS, music set below the voice.

    python scripts/master_audio.py out/render.mp4 -o out/master.mp4
    python scripts/master_audio.py out/render.mp4 -o out/master.mp4 --music track.mp3 [--gap 15] \\
        [--music-start 12.4 | --drop-at 24.1 --drop-in-track 61.0]
    python scripts/master_audio.py track.mp3 --find-drops          # where the drops are in a track (candidates)
    python scripts/master_audio.py out/master.mp4 --check          # only the acceptance check of a finished master
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
  and the final mix is brought to −14 LUFS again. The track is cut by meaning: the drop lands on the final phrase.
The video is not re-encoded: the audio goes into the finished render (-c:v copy), +faststart.
At the end, the acceptance check from the checklist (SKILL.md): −14 ±0.7 LUFS, true peak ≤ −1 dBFS, audio = video track
(and video = input). Exit code: 0, the check passed; 1, it failed, a measurement failed or ffmpeg failed.
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


def acceptance(p, d_in=None):
    """Acceptance check of the master by the checklist → (measurement line, list of failures). d_in: the input's video
    duration."""
    i1, tp1 = measure(p)
    dv, da = dur(p), dur(p, "a")
    fails = []
    if i1 is None or tp1 is None:
        fails.append("the ebur128 measurement failed: loudness and peak are unknown")
    else:
        if abs(i1 - TARGET) > LUFS_TOL + 1e-6:
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
    ap.add_argument("--no-denoise", action="store_true")
    ap.add_argument("--sfx", help="edit/<id>/sfx.json: scene sound accents mixed in before mastering")
    a = ap.parse_args()
    if a.find_drops:
        find_drops(a.input)
        return
    if a.check:
        sys.exit(report(*acceptance(a.input)))
    if not a.output:
        sys.exit("-o <output.mp4> is required")

    tmp = tempfile.mkdtemp(prefix="master_")
    try:
        code = master(a, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(code)


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
        run(["ffmpeg", "-y", "-hide_banner", "-i", a.input, "-map", "0", "-c", "copy", "-movflags", "+faststart", a.output])
        print(f"{why}: no voice and no effects, mastering skipped, the file is copied as is (+faststart): {a.output}")
        print("the −14 LUFS check does not apply to a video without sound: add music in the app when publishing, or a "
              "track with a commercial license via --music; with scene sounds, mastering goes the usual way")
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
        run(["ffmpeg", "-y", "-hide_banner", "-ss", f"{start:.3f}", "-t", f"{D:.3f}", "-i", a.music, "-af",
             f"afade=t=in:d=0.5,afade=t=out:st={max(0, mlen - fade):.3f}:d={fade:.3f},apad=whole_dur={D:.3f}",
             "-ar", "48000", "-ac", "2", mcut])
        loudnorm_2pass(mcut, final, "", TARGET)
        print(f"{why}: no voice; the music from {start:.2f} s of the track, at {TARGET:.0f} LUFS")
        ref = peak_db(final)
    else:
        run(["ffmpeg", "-y", "-hide_banner", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{D:.3f}",
             "-c:a", "pcm_s16le", final])
        print(f"{why}: no voice and no music; the scene sounds go onto silence")
        ref = -1.0
    if sfx_sounds(a):
        final = mix_sfx(a, tmp, D, base=final, ref=ref, below=NO_VOICE_BELOW)
    run(["ffmpeg", "-y", "-hide_banner", "-i", a.input, "-i", final, "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
         a.output])
    if not a.music:  # a few accents over silence are not a −14 LUFS track
        print(f"file: {a.output} (scene sounds only: the −14 LUFS check does not apply; add music in the app when "
              f"publishing, or a licensed track via --music)")
        return 0
    code = report(*acceptance(a.output, D))
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
        # sidechaincompress outputs about a second less than it receives → apad on both inputs, atrim on the output
        fc = (f"[0:a]apad=pad_dur=2,asplit=2[v][sc];"
              f"[1:a]apad=pad_dur=2,afade=t=in:d=0.5,afade=t=out:st={max(0, D - 1.2):.3f}:d=1.2[m];"
              f"[m][sc]sidechaincompress=threshold=0.10:ratio=3:attack=20:release=380[md];"
              f"[v][md]amix=inputs=2:duration=first:normalize=0,atrim=0:{D:.3f}[a]")
        run(["ffmpeg", "-y", "-hide_banner", "-i", voice, "-i", mus, "-filter_complex", fc, "-map", "[a]",
             "-c:a", "pcm_s16le", mix])
        final = os.path.join(tmp, "final.wav")
        loudnorm_2pass(mix, final, "", TARGET)  # the final mix back to −14
        mix = final
        print(f"music: from {start:.2f} s of the track, bed {mtarget:.0f} LUFS, gap ~{a.gap:.0f} dB, sidechain 3:1")

    run(["ffmpeg", "-y", "-hide_banner", "-i", a.input, "-i", mix, "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
         a.output])
    code = report(*acceptance(a.output, D))
    print("file:", a.output + ("" if not code else " — do not publish it; deal with the failure first"))
    return code


if __name__ == "__main__":
    main()
