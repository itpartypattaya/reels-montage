# -*- coding: utf-8 -*-
"""Speech mask from loudness: where someone speaks, where the pauses are, where to put a cut edge.

Cut points come from the audio, not from the transcript: recognizers drift at word boundaries by 0.1–0.8 s, while
the loudness envelope is a measured fact. Whisper answers "what was said", the mask answers "where exactly".

    python scripts/speech_mask.py edit/<id>/audio16k-IMG_4821.wav --spans 0.5-4.6,4.7-9.6 [--density natural] [--fps 30]
    python scripts/speech_mask.py --edl edit/<id>/edl.json      # check the edges of an assembled rough cut

--spans: rough intervals from the cut plan (from the transcript), one per phrase/take.
For each one the script:
  • refines the edges: first speech − 20 ms, last speech + 30 ms;
  • compresses inner pauses ≥160 ms to 50 ms (natural pacing: ≥400 → 220 ms);
  • warns about a pause >1 s inside (a seam between two takes of the phrase), about an edge that cuts through
    speech, and about short speech at the start/end with a pause after it (the tail of another phrase);
  • prints ready "ranges" for cut.json (points on the frame grid) and the remaining silence as a number.
Without --spans it prints every speech span in the file.

--edl: every edge of a finished rough cut, from its edl.json (each segment's source is taken from "sources").
Catches a fragment of the neighboring word at an edge, which Whisper cannot see: it attributes the fragment to the
word it expects. Real case (Russian speech): an edge landed in a 40 ms dip inside "poteryali" ("lost"); the 0.23 s
tail "-(te)ryali" plus 0.31 s of silence got into the segment and was recognized as the next word, and "teryali" was
heard twice in the video while the re-transcription was green.

Algorithm (checked against real cutting errors):
  env = RMS over 10 ms windows in dBFS; sdb = rolling max over ±30 ms;
  speech = sdb ≥ threshold AND a continuous span ≥ 110 ms;
  voiceless-ending pickup: if a window above the threshold lies within 250 ms after a span, extend the span to it.
The default threshold is −30 dBFS for a normal recording level. For quiet recordings (phone far away) it is lowered
automatically: speech level (95th percentile) − 20 dB, but no higher than −30.
"""
import argparse, json, os, subprocess, sys, tempfile, wave
from array import array
from math import log10, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import ANALYSIS_AF, local_media_args

HOP = 0.010


def load_env(path):
    """dBFS envelope over 10 ms windows. An empty list: there is no audio, or it is shorter than one window."""
    return load_envs(path)[0]


def load_envs(path):
    """(broadband envelope, high-band envelope), both dB over 10 ms windows. The high band is the energy of the second
    difference of the signal (about +6 dB at 4 kHz, -36 dB at 300 Hz): voiceless consonants (s, sh, ch, f) are quiet in
    the broadband level and loud there."""
    tmp = None
    try:
        if not path.lower().endswith(".wav"):
            # a separate file per call: a shared speech_mask_16k.wav got replaced by a parallel check of another video
            fd, tmp = tempfile.mkstemp(prefix="speech_mask_", suffix=".wav")
            os.close(fd)
            # on the video timeline, the one cut.py cuts by (a phone MOV's audio can start ~0.1 s after the video)
            r = subprocess.run(local_media_args(["ffmpeg", "-v", "error", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                                "-af", ANALYSIS_AF, "-c:a", "pcm_s16le", tmp]), capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                sys.exit(f"ffmpeg could not read the audio of {path}: {r.stderr.strip()[-300:]}")
            path = tmp
        with wave.open(path, "rb") as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                sys.exit("needs a mono 16-bit wav (ffmpeg -ac 1 -ar 16000 -c:a pcm_s16le)")
            sr = w.getframerate()
            data = array("h", w.readframes(w.getnframes()))
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
    n = int(sr * HOP)
    env, hf = [], []
    for i in range(0, len(data) - n + 1, n):
        s = h = 0
        p1 = data[i - 1] if i else 0
        p2 = data[i - 2] if i > 1 else 0
        for v in data[i:i + n]:
            s += v * v
            d = v - 2 * p1 + p2
            h += d * d
            p2, p1 = p1, v
        rms, hrms = sqrt(s / n) / 32768, sqrt(h / n) / 32768
        env.append(20 * log10(rms) if rms > 1e-6 else -120.0)
        hf.append(20 * log10(hrms) if hrms > 1e-6 else -120.0)
    return env, hf


VL_ABOVE = 15.0   # dB above the high-band noise floor: a voiceless consonant (measured: a final "s" 22 dB over cafe noise)
VL_TAIL, VL_HEAD = 0.250, 0.200   # how far a phrase may extend into a voiceless sound after it / before it


def voiceless(hf):
    """Windows with a voiceless sound: the high band VL_ABOVE over its floor (the 20th percentile of the file)."""
    if not hf:
        return []
    floor = sorted(hf)[int(len(hf) * 0.2)]
    return [x >= floor + VL_ABOVE for x in hf]


def smax(env, k=3):
    out = []
    for i in range(len(env)):
        out.append(max(env[max(0, i - k): i + k + 1]))
    return out


def speech_mask(sdb, thr, min_run=0.110, tail=0.250, head=0.200, vl=None):
    loud = [x >= thr for x in sdb]
    mask = [False] * len(loud)
    i = 0
    runs = []
    while i < len(loud):
        if loud[i]:
            j = i
            while j < len(loud) and loud[j]:
                j += 1
            if (j - i) * HOP >= min_run:
                runs.append([i, j])
            i = j
        else:
            i += 1
    # voiceless-ending pickup happens inside the mask, not by trimming the interval's edges.
    # The end is extended only through short "bursts" (under 110 ms): that is a voiceless syllable.
    # The start of the next full speech span is a stop, otherwise the pauses between words would not be compressed.
    t = int(tail / HOP)
    run_start = {r[0] for r in runs}
    for r in runs:
        k = r[1]
        while True:
            nxt = next((m for m in range(k, min(len(loud), k + t)) if loud[m]), None)
            if nxt is None or nxt in run_start:
                break
            while nxt < len(loud) and loud[nxt] and nxt not in run_start:
                nxt += 1
            if nxt in run_start:
                break
            k = nxt
        r[1] = k
    # plosive-onset pickup, the mirror of the above: a short burst up to 200 ms before a span is the start of its first
    # word (Russian "Podpisyval": a 40 ms "P" burst, then a 120 ms closure, then the vowel). Without it the burst falls
    # under min_run and the edge cuts the consonant off. It never reaches back into the previous span.
    h = int(head / HOP)
    prev_end = 0
    for r in runs:
        k = r[0]
        while True:
            lo = max(prev_end, k - h)
            prv = next((m for m in range(k - 1, lo - 1, -1) if loud[m]), None)
            if prv is None:
                break
            while prv - 1 >= lo and loud[prv - 1]:
                prv -= 1
            k = prv
        r[0] = k
        prev_end = r[1]
    # voiceless edges: a final "s" or an initial "ch" sits under the broadband threshold but is part of the word
    # (a real case: "biznes" lost its "s", "chem" its "ch"); runs grow through high-band windows, never into a neighbor
    if vl:
        for k_, r in enumerate(runs):
            nxt = runs[k_ + 1][0] if k_ + 1 < len(runs) else len(loud)
            prv = runs[k_ - 1][1] if k_ else 0
            e, lim = r[1], min(nxt, r[1] + int(VL_TAIL / HOP))
            while e < lim and vl[e]:
                e += 1
            s_, lim = r[0], max(prv, r[0] - int(VL_HEAD / HOP))
            while s_ > lim and vl[s_ - 1]:
                s_ -= 1
            r[0], r[1] = s_, e
    for a, b in runs:
        for m in range(a, b):
            mask[m] = True
    return mask


def segments(mask, a=0, b=None):
    b = len(mask) if b is None else min(b, len(mask))  # the interval stays within the mask (an edge past the end of the file)
    out, i = [], max(0, a)
    while i < b:
        if mask[i]:
            j = i
            while j < b and mask[j]:
                j += 1
            out.append((i * HOP, j * HOP))
            i = j
        else:
            i += 1
    return out


def snap(t, fps):
    return round(t * fps) / fps


TAIL_MAX = 0.35  # a fragment of another word shorter than this...
TAIL_GAP = 0.20  # ...and separated from the wanted speech by at least this much silence
WORD_MIN = 15    # 10 ms windows: this many loud windows within 0.3 s on the other side of an edge make a word, not a breath or click
NEAR = 8         # windows: a loud sound closer than 80 ms past the edge means the edge is inside a word (a 40 ms dip is not a pause)
FADE = 3         # windows: sound closer than 30 ms to the edge means the cut.py fade (30 ms) will eat a consonant


def edge_warnings(env, mask, thr, s, e, vl=None):
    """Problems at the edges of segment [s, e] of the source.

    env is the raw envelope (dBFS), used for "where there really is sound"; mask is the speech mask, used for fragments.
    The mask widens speech by ±30 ms and extends voiceless endings, so "an edge inside a mask span" is a false alarm
    by itself; the raw level on the other side of the edge decides.
    """
    out = []
    n = len(env)
    if n == 0:  # an empty file or shorter than a 10 ms window: the mask is empty, the edges can't be checked
        return [f"the source has no audio (empty or shorter than {HOP * 1000:.0f} ms): edge {s:.2f}–{e:.2f} can't be checked"]
    if s >= n * HOP:
        return [f"segment {s:.2f}–{e:.2f} starts past the end of the source audio ({n * HOP:.2f} s)"]
    si, ei = max(0, min(n - 1, int(round(s / HOP)))), max(0, min(n - 1, int(round(e / HOP))))
    loud = lambda i: 0 <= i < n and env[i] >= thr
    hiss = lambda i: bool(vl) and 0 <= i < len(vl) and vl[i]

    # ── start ──
    before = [i for i in range(max(0, si - 30), si) if loud(i)]
    if len(before) >= WORD_MIN and before[-1] >= si - NEAR:
        msg = (f"start {s:.2f} is inside a word: speech until {(before[-1] + 1) * HOP:.2f}, "
               f"the dip between them is {s - (before[-1] + 1) * HOP:.2f} s, that is not a pause")
        segs = segments(mask, si, min(n, si + int(1.0 / HOP)))
        if len(segs) > 1 and segs[0][1] - s < TAIL_MAX and segs[1][0] - segs[0][1] >= TAIL_GAP:
            msg += (f"; the segment picks up a fragment {s:.2f}–{segs[0][1]:.2f}, then silence "
                    f"{segs[1][0] - segs[0][1]:.2f} s: the tail of the previous word; start ≈ {segs[1][0] - 0.05:.2f}")
        out.append(msg)
    else:
        segs = segments(mask, si, min(n, si + int(1.0 / HOP)))
        if len(segs) > 1:
            d, gap = segs[0][1] - max(s, segs[0][0]), segs[1][0] - segs[0][1]
            if d < TAIL_MAX and gap >= TAIL_GAP:
                out.append(f"short sound at the start {max(s, segs[0][0]):.2f}–{segs[0][1]:.2f} ({d:.2f} s) and silence {gap:.2f} s "
                           f"— the tail of another word or a separate short word? listen; without the tail, start ≈ {segs[1][0] - 0.05:.2f}")
        if si >= FADE and any(loud(i) for i in range(si, si + FADE)) and not any(loud(i) for i in range(si - 5, si)):  # at the file's edge there is nowhere earlier to go
            out.append(f"start {s:.2f} is right at the onset of sound: the 30 ms fade will soften the first consonant; start ≈ {s - 0.04:.2f}")
    if hiss(si) and hiss(si - 1) and hiss(si - 2):
        k = si
        while k > 0 and hiss(k - 1) and si - k < 25:
            k -= 1
        out.append(f"start {s:.2f} cuts a voiceless sound (s, sh, ch, f) that begins at {k * HOP:.2f}: start ≈ {k * HOP - 0.03:.2f}")

    # ── end ──
    if e > n * HOP + HOP:
        out.append(f"end {e:.2f} is past the end of the source audio ({n * HOP:.2f} s)")
        return out
    after =[i for i in range(ei + 1, min(n, ei + 31)) if loud(i)]
    if len(after) >= WORD_MIN and after[0] <= ei + NEAR:
        msg = (f"end {e:.2f} is inside a word: speech from {after[0] * HOP:.2f}, "
               f"dip {after[0] * HOP - e:.2f} s, that is not a pause")
        segs = segments(mask, max(0, ei - int(1.0 / HOP)), ei + 1)
        if len(segs) > 1 and e - segs[-1][0] < TAIL_MAX and segs[-1][0] - segs[-2][1] >= TAIL_GAP:
            msg += f"; the segment picks up the start of the next word {segs[-1][0]:.2f}–{e:.2f}; end ≈ {segs[-2][1] + 0.07:.2f}"
        out.append(msg)
    else:
        segs = segments(mask, max(0, ei - int(1.0 / HOP)), ei + 1)
        if len(segs) > 1:
            d, gap = min(e, segs[-1][1]) - segs[-1][0], segs[-1][0] - segs[-2][1]
            if d < TAIL_MAX and gap >= TAIL_GAP:
                out.append(f"short sound at the end {segs[-1][0]:.2f}–{min(e, segs[-1][1]):.2f} ({d:.2f} s) after silence {gap:.2f} s "
                           f"— the start of the next phrase? end ≈ {segs[-2][1] + 0.07:.2f}")
        if any(loud(i) for i in range(ei - FADE + 1, ei + 1)) and not any(loud(i) for i in range(ei + 1, ei + 6)):
            out.append(f"end {e:.2f} is right at the end of sound: the 30 ms fade will eat the ending; end ≈ {e + 0.05:.2f}")
    if hiss(ei - 1) and hiss(ei) and hiss(ei + 1):
        k = ei
        while hiss(k + 1) and k - ei < 25:
            k += 1
        out.append(f"end {e:.2f} cuts a voiceless sound (s, sh, ch, f) that lasts until {(k + 1) * HOP:.2f}: end ≈ {(k + 1) * HOP + 0.04:.2f}")
    return out


def check_edl(path, thr_arg):
    edl = json.load(open(path, encoding="utf-8"))
    cache, bad = {}, 0
    for k, r in enumerate(edl["ranges"]):
        src = r["source"]
        if src not in cache:
            env, hf = load_envs(edl["sources"][src])
            sdb, vl = smax(env), voiceless(hf)
            srt = sorted(x for x in sdb if x > -90)
            p95 = srt[int(len(srt) * 0.95)] if srt else -20
            thr = thr_arg if thr_arg is not None else min(-30.0, p95 - 20)
            cache[src] = (env, speech_mask(sdb, thr, vl=vl), thr, vl)
        env, mask, thr, vl = cache[src]
        w = edge_warnings(env, mask, thr, r["start"], r["end"], vl)
        bad += bool(w)
        print(f"{k:2d} {src} {r['start']:.2f}–{r['end']:.2f}" + ("  ok" if not w else "".join("\n    ⚠ " + x for x in w)))
    print(f"\nedges with warnings: {bad} of {len(edl['ranges'])}")
    return bad


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", nargs="?")
    ap.add_argument("--edl", help="edit/<id>/edl.json: check the edges of every segment of the rough cut")
    ap.add_argument("--spans", default="")
    ap.add_argument("--density", choices=["max", "natural"], default="max")
    ap.add_argument("--thr", type=float, default=None, help="speech threshold, dBFS (auto by default)")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    pmin, keep = (0.160, 0.050) if a.density == "max" else (0.400, 0.220)
    if a.edl:
        sys.exit(1 if check_edl(a.edl, a.thr) else 0)
    if not a.audio:
        ap.error("needs audio or --edl")

    env, hf = load_envs(a.audio)
    vl = voiceless(hf)
    if not env:
        sys.exit(f"{a.audio} has no audio (empty or shorter than {HOP * 1000:.0f} ms): can't build the mask")
    sdb = smax(env)
    srt = sorted(x for x in sdb if x > -90)
    p95 = srt[int(len(srt) * 0.95)] if srt else -20
    thr = a.thr if a.thr is not None else min(-30.0, p95 - 20)
    mask = speech_mask(sdb, thr, vl=vl)
    print(f"speech level (p95) {p95:.1f} dBFS, threshold {thr:.1f} dBFS, pacing {a.density}: "
          f"pauses ≥{int(pmin * 1000)} ms → {int(keep * 1000)} ms", file=sys.stderr)

    if not a.spans:
        for s, e in segments(mask):
            print(f"{s:7.2f}–{e:7.2f}  {e - s:5.2f} s")
        return

    ranges, report, residual = [], [], 0.0
    for span in a.spans.split(","):
        s0, e0 = (float(x) for x in span.split("-"))
        segs = segments(mask, int(s0 / HOP), min(len(mask), int(e0 / HOP) + 1))
        if not segs:
            report.append(f"{s0:.2f}-{e0:.2f}: no speech found: threshold? rustle? check the frames")
            continue
        warn = []
        gaps = [(segs[k][1], segs[k + 1][0]) for k in range(len(segs) - 1)]
        for g0, g1 in gaps:
            if g1 - g0 > 1.0:
                warn.append(f"pause {g1 - g0:.2f} s inside at {g0:.2f}: possibly a seam between two takes of the phrase")
        if len(segs) > 1 and segs[0][1] - segs[0][0] < 0.8 and segs[1][0] - segs[0][1] > 0.6:
            warn.append(f"short speech at the start {segs[0][0]:.2f}–{segs[0][1]:.2f} and a pause after it: the tail of another take?")
        warn += edge_warnings(env, mask, thr, s0, e0, vl)  # an edge cuts speech / a 0.2–0.35 s fragment (missed by the rule above)
        # pause compression: from a pause ≥pmin keep `keep` (half on each side)
        pieces, cur_s = [], segs[0][0] - 0.020
        for (g0, g1) in gaps:
            if g1 - g0 >= pmin:
                pieces.append((cur_s, g0 + keep / 2))
                cur_s = g1 - keep / 2
            else:
                residual = max(residual, g1 - g0)
        pieces.append((cur_s, segs[-1][1] + 0.030))
        for p0, p1 in pieces:
            p0, p1 = snap(max(0, p0), a.fps), snap(p1, a.fps)
            if p1 - p0 > 1 / a.fps:
                ranges.append((round(p0, 3), round(p1, 3)))
        residual = max(residual, keep)
        report.append(f"{s0:.2f}-{e0:.2f}: {len(pieces)} segments, speech {segs[0][0]:.2f}–{segs[-1][1]:.2f}"
                      + ("".join("\n    ⚠ " + w for w in warn)))
    total = sum(e - s for s, e in ranges)
    print("\n".join(report))
    print(f"\ntotal: {len(ranges)} segments, {total:.2f} s before speed-up; "
          f"max remaining silence inside a segment {int(residual * 1000)} ms "
          f"(+ segment joins: ~{int((0.020 + 0.030) * 1000)} ms)")
    if a.json:
        print(json.dumps({"threshold": thr, "ranges": ranges, "residual_ms": int(residual * 1000)}))
    else:
        print('"ranges": [')
        print(",\n".join(f'  {{"start": {s:.3f}, "end": {e:.3f}, "beat": ""}}' for s, e in ranges))
        print(']   <- for edit/<id>/cut.json; add "source" to each range when there are several sources')


if __name__ == "__main__":
    main()
