# -*- coding: utf-8 -*-
"""Speech leveling over the whole rough cut: every piece and every stretch of speech at one loudness.

Why. master_audio.py brings the whole track to −14 LUFS, but the differences inside it stay: two takes recorded in
different places (a real case: 4.5 dB between a garden and an indoor take, heard at every switch), a take recorded
closer to the phone, a speaker who leans back or turns away in the middle of a long piece. The ear hears each of
them as a jump. cut.py runs this step by itself after joining the audio (cut.json "level": false or cut.py
--no-level turns it off); it can also be run on a finished rough cut:

    python scripts/level.py edit/<id> --check     # only measure final.mp4: speech level per source and per piece
    python scripts/level.py edit/<id>             # level final.mp4 again in place (the video is copied)

How (measured on the speech only, so pauses and room noise never set the gain):
  - the envelope: RMS over 10 ms windows of a 16 kHz mono copy, the same analysis as speech_mask.py; speech = windows
    at or above the speech threshold of their own source (the source's speech level, its 95th percentile, − 20 dB, at
    most −30 dBFS, at least −60: a silent file has no speech, not quiet speech). Per source, not one for the video: a
    take 20+ dB quieter than the loudest would fall under a shared threshold whole and get no gain at all;
  - the level of a stretch = the power mean of its speech windows (like LUFS, which is a gated power mean);
  - each piece of the cut (captions.json segments) gets its own level; a piece with under 1 s of speech takes the level
    of its source (too little to measure). The target is the mean of the sources' speech levels in dB, weighted by
    their speech time (a power mean would lean to the loudest take);
  - inside a piece the local level is measured over ±1.5 s of speech and corrects the piece's gain by at most ±4 dB
    (a speaker turning away, a phrase said closer to the phone); a stress on one word does not move a 3 s window much;
  - the gain holds through pauses (no speech within 0.3 s) instead of following the noise, is smoothed over ±0.4 s and
    changes inside a piece by at most 3 dB per second; between pieces it may step: a join is on silence with a 30 ms
    fade (cut.py), so the step is not heard;
  - limits: ±8 dB in total; the sample peak after leveling, measured over every channel at the file's own rate (a mono
    16 kHz copy under-reads it), stays 2 dB under full scale (room for the AAC encode), otherwise every gain is
    lowered by the excess: the level is evened, not raised;
  - the gain curve is applied with ffmpeg amultiply (the audio times a 48 kHz gain track), the video is copied.
Report: the speech level per source and per piece before and after, the largest gain; captions.json -> "leveling".
"""
import argparse, json, os, subprocess, sys, tempfile, wave
from array import array
from math import log10, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import edit_dir, load_json, local_media_args, project_root, save_json, utf8_stdio, warn

HOP = 0.010          # s: analysis window, as in speech_mask.py
MIN_SPEECH = 1.0     # s of speech: less than this in a piece -> its source's level
LOCAL = 1.5          # s: half-width of the local level window inside a piece
LOCAL_MIN = 0.6      # s of speech in the local window, otherwise no local correction there
IN_MAX = 4.0         # dB: the largest correction of the local level against the piece's level
MAX_GAIN = 8.0       # dB: the largest gain either way
HOLD = 0.3           # s: no speech this close -> a pause: the gain holds
SMOOTH = 0.4         # s: half-width of the moving average of the gain
SLEW = 3.0           # dB per s inside a piece
PEAK_LIMIT = -2.0    # dBFS sample peak after the gain (all channels, own rate): room for the AAC encode
QUIETEST = -60.0     # dBFS: nothing quieter is speech (silence, a source without sound: its threshold sinks with it)
SR_OUT = 48000


def pmean(dbs):
    """Power mean of dB values (None for an empty list)."""
    if not dbs:
        return None
    return 10 * log10(sum(10 ** (x / 10) for x in dbs) / len(dbs))


def peaks(path, n):
    """Sample peak in dBFS per 10 ms window over every channel at the file's own rate, n windows. The peak is measured on
    the audio that gets amplified: a mono 16 kHz copy under-reads it (channels that partly cancel, high-frequency
    transients cut by the resampling), and a click raised over full scale would clip for good. Float samples, so a
    peak already over full scale is seen as such."""
    r = subprocess.run(local_media_args(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                                         "stream=sample_rate,channels", "-of", "csv=p=0", str(path)]),
                       capture_output=True, text=True)
    try:
        sr, ch = (int(x) for x in r.stdout.strip().split(",")[:2])
    except ValueError:
        raise RuntimeError(f"ffprobe found no audio stream in {path}")
    r = subprocess.run(local_media_args(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "f32le", "-acodec", "pcm_f32le",
                                         "-"]), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read the audio of {path}: {r.stderr.decode('utf-8', 'replace').strip()[-300:]}")
    data = array("f")
    data.frombytes(r.stdout[:len(r.stdout) // 4 * 4])
    if sys.byteorder != "little":
        data.byteswap()
    k = int(sr * HOP) * ch
    out = []
    for i in range(n):
        chunk = data[i * k:(i + 1) * k]
        p = max(abs(min(chunk)), abs(max(chunk))) if chunk else 0.0
        out.append(20 * log10(p) if p > 1e-6 else -120.0)
    return out


def analyze(path):
    """(rms_db, peak_db) per 10 ms window: the RMS of a mono 16 kHz copy (speech detection, as in speech_mask.py), the
    peak over every channel at the file's own rate (headroom, see peaks())."""
    fd, tmp = tempfile.mkstemp(prefix="level_", suffix=".wav")
    os.close(fd)
    try:
        r = subprocess.run(local_media_args(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                                             "-c:a", "pcm_s16le", tmp]), capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg could not read the audio of {path}: {r.stderr.strip()[-300:]}")
        with wave.open(tmp, "rb") as w:
            sr = w.getframerate()
            data = array("h", w.readframes(w.getnframes()))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    n = int(sr * HOP)
    rms = []
    for i in range(0, len(data) - n + 1, n):
        x = sqrt(sum(v * v for v in data[i:i + n]) / n) / 32768
        rms.append(20 * log10(x) if x > 1e-6 else -120.0)
    return rms, peaks(path, len(rms))


def speech_threshold(env):
    """The speech threshold of an envelope (the windows of one source)."""
    srt = sorted(env)
    p95 = srt[int(len(srt) * 0.95)] if srt else -20
    return max(QUIETEST, min(-30.0, p95 - 20))


def _windows(segs, n):
    """[(source, a, b)] window index ranges of the pieces, clipped to the envelope."""
    out = []
    for src, start, dur in segs:
        a = max(0, min(n, int(round(start / HOP))))
        b = max(a, min(n, int(round((start + dur) / HOP))))
        out.append((src, a, b))
    return out


def thresholds(env, wins):
    """{source: speech threshold} from the windows of each source's pieces."""
    by = {}
    for src, a, b in wins:
        by.setdefault(src, []).extend(env[a:b])
    return {k: speech_threshold(v) for k, v in by.items()}


def speech_flags(env, wins, thr):
    """True for a speech window: at or above the threshold of the source whose piece holds it."""
    sp = [False] * len(env)
    for src, a, b in wins:
        t = thr[src]
        for i in range(a, b):
            sp[i] = env[i] >= t
    return sp


def gain_curve(env, segs, peak=None):
    """Gain in dB per 10 ms window + a report. env: dB per window; segs: [(source, out_start, out_dur)] in seconds."""
    n = len(env)
    wins = _windows(segs, n)
    thr = thresholds(env, wins)
    sp = speech_flags(env, wins, thr)
    by_src = {}
    for src, a, b in wins:
        by_src.setdefault(src, []).extend(env[i] for i in range(a, b) if sp[i])
    src_level = {k: pmean(v) for k, v in by_src.items()}
    # the target: the sources' levels in dB weighted by their speech time. A power mean of all the speech would lean to
    # the loudest take (a −20 and a −41 dB take give −23: the loud one barely moves, the quiet one hits the limit)
    weighted = [(lv, len(by_src[k])) for k, lv in src_level.items() if lv is not None]
    total = sum(w for _, w in weighted)
    target = sum(lv * w for lv, w in weighted) / total if total else None
    g = [0.0] * n
    report = {"threshold_db": {k: round(v, 1) for k, v in thr.items()}, "target_db": None if target is None else round(target, 2), "pieces": [],
              "sources": {}}
    if target is None:
        return g, report
    lin = [10 ** (x / 10) if s else 0.0 for x, s in zip(env, sp)]
    cs, cn = [0.0], [0]
    for v, s in zip(lin, sp):
        cs.append(cs[-1] + v)
        cn.append(cn[-1] + (1 if s else 0))
    k_loc, k_hold, k_sm = int(LOCAL / HOP), int(HOLD / HOP), int(SMOOTH / HOP)
    slew = SLEW * HOP
    for src, a, b in wins:
        if b <= a:
            report["pieces"].append({"source": src, "level_db": None, "gain_db": 0.0})
            continue
        cnt = cn[b] - cn[a]
        lvl = 10 * log10((cs[b] - cs[a]) / cnt) if cnt * HOP >= MIN_SPEECH else src_level.get(src)
        lvl = target if lvl is None else lvl
        base = max(-MAX_GAIN, min(MAX_GAIN, target - lvl))
        raw = [None] * (b - a)
        for i in range(a, b):
            lo, hi = max(a, i - k_hold), min(b, i + k_hold + 1)
            if cn[hi] - cn[lo] == 0:
                continue  # a pause: filled from the neighbors below
            lo, hi = max(a, i - k_loc), min(b, i + k_loc + 1)
            c = cn[hi] - cn[lo]
            dev = 0.0
            if c * HOP >= LOCAL_MIN:
                dev = max(-IN_MAX, min(IN_MAX, 10 * log10((cs[hi] - cs[lo]) / c) - lvl))
            raw[i - a] = max(-MAX_GAIN, min(MAX_GAIN, base - dev))
        # pauses hold the gain: forward fill, then the start of the piece from its first speech
        last = None
        for j in range(len(raw)):
            if raw[j] is None:
                raw[j] = last
            else:
                last = raw[j]
        first = next((x for x in raw if x is not None), base)
        raw = [first if x is None else x for x in raw]
        # moving average, then the slew limit both ways
        m = len(raw)
        pre = [0.0]
        for x in raw:
            pre.append(pre[-1] + x)
        sm = [(pre[min(m, j + k_sm + 1)] - pre[max(0, j - k_sm)]) / (min(m, j + k_sm + 1) - max(0, j - k_sm)) for j in range(m)]
        for j in range(1, m):
            sm[j] = max(sm[j - 1] - slew, min(sm[j - 1] + slew, sm[j]))
        for j in range(m - 2, -1, -1):
            sm[j] = max(sm[j + 1] - slew, min(sm[j + 1] + slew, sm[j]))
        g[a:b] = sm
        report["pieces"].append({"source": src, "level_db": round(lvl, 2), "gain_db": round(base, 2)})
    if peak:
        over = max((p + x for p, x in zip(peak, g)), default=-120) - PEAK_LIMIT
        if over > 0:
            g = [x - over for x in g]
            report["peak_trim_db"] = round(over, 2)
    for src, lv in src_level.items():
        idx = [i for s, a, b in wins if s == src for i in range(a, b) if sp[i]]
        after = pmean([env[i] + g[i] for i in idx])
        report["sources"][src] = {"before_db": None if lv is None else round(lv, 2),
                                  "after_db": None if after is None else round(after, 2)}
    report["max_gain_db"] = round(max((abs(x) for x in g), default=0.0), 2)
    return g, report


def gain_track(g, path, duration):
    """A mono 48 kHz float WAV of linear gain, linear between window centers; length = duration."""
    total = int(round(duration * SR_OUT))
    per = int(SR_OUT * HOP)
    lin = [10 ** (x / 20) for x in g] or [1.0]
    out = array("f")
    for k in range(len(lin)):
        a = lin[k]
        b = lin[k + 1] if k + 1 < len(lin) else a
        step = (b - a) / per
        out.extend(a + step * j for j in range(per))
    if len(out) < total:
        out.extend([lin[-1]] * (total - len(out)))
    del out[total:]
    # 32-bit float WAV by hand (the wave module writes only PCM integers)
    data = out.tobytes() if sys.byteorder == "little" else (out.byteswap() or out).tobytes()
    with open(path, "wb") as f:
        f.write(b"RIFF" + (36 + len(data)).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
                + (3).to_bytes(2, "little") + (1).to_bytes(2, "little") + SR_OUT.to_bytes(4, "little")
                + (SR_OUT * 4).to_bytes(4, "little") + (4).to_bytes(2, "little") + (32).to_bytes(2, "little")
                + b"data" + len(data).to_bytes(4, "little") + data)


def duration_of(path):
    r = subprocess.run(local_media_args(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                         str(path)]), capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def apply(audio_in, audio_out, g):
    """audio_in (any ffmpeg audio) times the gain curve -> audio_out (AAC 192k, 48 kHz stereo, as cut.py writes it)."""
    fd, gw = tempfile.mkstemp(prefix="level_gain_", suffix=".wav")
    os.close(fd)
    try:
        gain_track(g, gw, duration_of(audio_in))
        fc = ("[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a];"
              "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono,pan=stereo|c0=c0|c1=c0[g];"
              "[a][g]amultiply[o]")
        r = subprocess.run(local_media_args(["ffmpeg", "-v", "error", "-y", "-i", str(audio_in), "-i", gw, "-filter_complex",
                                             fc, "-map", "[o]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                                             str(audio_out)]), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg amultiply failed: {r.stderr.strip()[-300:]}")
    finally:
        try:
            os.remove(gw)
        except OSError:
            pass


def level_audio(audio_in, audio_out, segs):
    """Measure, plan and apply; returns the report. segs: [(source, out_start, out_dur)]."""
    env, peak = analyze(audio_in)
    g, rep = gain_curve(env, segs, peak)
    apply(audio_in, audio_out, g)
    return rep


def describe(rep):
    s = rep.get("sources") or {}
    parts = [f"{k} {v['before_db']} -> {v['after_db']} dB" for k, v in s.items()]
    gains = [p["gain_db"] for p in rep.get("pieces", []) if p.get("level_db") is not None]
    span = f"pieces {min(gains):+.1f}..{max(gains):+.1f} dB" if gains else "no speech"
    trim = f", peak trim -{rep['peak_trim_db']} dB" if rep.get("peak_trim_db") else ""
    thr = rep.get("threshold_db") or {}
    thr = ", ".join(f"{k} {v}" for k, v in thr.items()) if isinstance(thr, dict) else thr
    return (f"speech leveling: target {rep.get('target_db')} dB (speech thresholds {thr}); "
            + "; ".join(parts) + f"; {span}; largest gain {rep.get('max_gain_db')} dB{trim}")


def measure(path, segs):
    """Speech level per source and per piece of a file, no change: {source: dB}, [piece dB]."""
    env, _ = analyze(path)
    wins = _windows(segs, len(env))
    thr = thresholds(env, wins)
    per_src, pieces = {}, []
    for src, a, b in wins:
        v = [env[i] for i in range(a, b) if env[i] >= thr[src]]
        per_src.setdefault(src, []).extend(v)
        pieces.append(None if len(v) * HOP < MIN_SPEECH else round(pmean(v), 2))
    return {k: (None if not v else round(pmean(v), 2)) for k, v in per_src.items()}, pieces


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", help="the video folder, edit/<id>")
    ap.add_argument("--check", action="store_true", help="only measure final.mp4, change nothing")
    a = ap.parse_args()
    e = edit_dir(a.edit, project_root())
    cap = load_json(e / "captions.json")
    final = e / "final.mp4"
    if not isinstance(cap, dict) or not final.is_file():
        sys.exit(f"no rough cut in {e}: run cut.py first")
    segs = [(s["source"], s["out_start"], s["out_dur"]) for s in cap.get("segments", [])]
    src, pieces = measure(final, segs)
    print("speech level per source (dB): " + ", ".join(f"{k} {v}" for k, v in src.items()))
    print("per piece: " + ", ".join("-" if p is None else str(p) for p in pieces))
    if a.check:
        return
    tmp = e / "clips" / "final_level.mp4"
    (e / "clips").mkdir(exist_ok=True)
    au = e / "clips" / "audio_level.m4a"
    rep = level_audio(final, au, segs)
    r = subprocess.run(local_media_args(["ffmpeg", "-v", "error", "-y", "-i", str(final), "-i", str(au), "-map", "0:v", "-map",
                                         "1:a", "-c", "copy", "-movflags", "+faststart", str(tmp)]), capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg mux failed: {r.stderr.strip()[-300:]}")
    os.replace(tmp, final)
    cap["leveling"] = rep
    save_json(e / "captions.json", cap)
    print(describe(rep))
    if len(rep.get("sources", {})) > 1:
        after = [v["after_db"] for v in rep["sources"].values() if v["after_db"] is not None]
        if after and max(after) - min(after) > 1.0:
            warn("the sources still differ by more than 1 dB: a gain limit was reached (±8 dB), listen")


if __name__ == "__main__":
    main()
