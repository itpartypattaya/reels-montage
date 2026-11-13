# -*- coding: utf-8 -*-
"""Is the footage usable? Hints about the bad stretches of a clip before it goes under a voice-over or into a
no-speech reel (references/no-speaker.md, "Is the footage usable"). Hints only: every finding is a candidate with its
reason and the status "unchecked"; nothing is excluded, no project file is changed. The person (or the agent, on the
contact sheet and the clip) decides.

    python scripts/picture.py scan <clip or folder> ... [--window FROM-TO] [--size 480] [--json] [--out FILE]
    python scripts/picture.py scan --edit edit/<id> [<clip> ...]   # the video's picture sources, with its seconds

What it looks for (seconds of the clip):
  shake    the camera jitters: the high-frequency part of its frame-to-frame shift (a clip from the hand, a bumped
           tripod); a smooth pan or something moving across a still shot is not shake
  restless the camera stands, but the whole picture moves unevenly (people fidgeting, water, leaves): a softer hint
  tail     an editing app's ending: a cut near the end, then black, a frozen frame or another picture to the end
  black    black frames (not at the end); freeze: a frozen picture (not at the end)
  dark     a dark stretch; bright: an overexposed one (a large share of the frame clipped white)
  speech   speech-like sound in the clip's own sound: someone may be talking (lips that would not match a
           voice-over); with a face turned to the camera, speaking to the camera
  turn     a face turns to the camera (references/no-speaker.md: a person who turns around under a voice-over)
  faces    more faces than the clip usually has: strangers? They are hidden only under an opaque full scene for their
           whole window (0.25 s on each side) or shown after the person's yes: a panel or a window does not hide them
What it could not judge is listed as "not assessed", never passed in silence: the motion of a picture without detail
(a sky, a wall, darkness), the turn of a face too small to judge (a wide shot), faces without the face model, a clip
without sound.

With --edit edit/<id>: the clip names of cut.json and, once the rough cut exists, every candidate also gets the
seconds of the finished video where that stretch is on screen (each picture shot's start and speed; a clip used twice
is on screen twice) -> edit/<id>/picture_scan.json. A strangers candidate there carries the window to hide.

How: one ffmpeg run per clip decodes the frames 15 a second, scaled to 480 px on the long side (--size), straight into
this script through a pipe: no frame is written out as an image. Per frame: the brightness (mean, the share of black
and of clipped white pixels), the difference from the previous frame, the correlation of a coarse 24 px picture with
the previous one (a cut; blind to brightness, so an exposure jump is not one), and the shift from the previous frame
by phase correlation (whitened, a Gaussian low-pass, a Gaussian fit of the peak: a tenth of a pixel is measured): of
the whole frame and, for the camera, the median of 3 x 3 blocks (someone moving across part of the frame does not
move the median). The path is the sum of the shifts; what a 0.5 s smoothing removes from it is the jitter. Faces every
0.5 s with the YuNet model faces.py uses (the head turn as defects.py measures it). The sound: the voice band's level
every 10 ms; speech has syllables (its level dips and rises 3-8 times a second by 10 dB and more), a pool or the wind
does not.
Calibrated on 13 phone and camera clips (25 min: tripods, a bumped tripod, hand-held stairs, a pan, a walk on a beach,
a sky, a pool far away, a two-person interview in profile, a talking head): the camera's jitter of a tripod stays
under 0.012 % of the frame, a walk following someone 0.03 %, hand-held stairs 0.06-0.4 % (SHAKE 0.04 %). The whole
picture of a still shot moves 0.004-0.014 % when calm, 0.017-0.03 % with fidgeting people or waves, 0.05 % and more
with a close talking head (RESTLESS 0.016 % over 2 s).
The measurements are kept in <project>/_picture_scan/, keyed by the file's path, size and modification time and the
scan's settings: a second scan of the same clip reads them (--fresh measures again). A 1080p clip takes about two
thirds of its length to scan, a 4K one about its length (on a laptop with 8 GB), --size 960 (far faces) about 3.5
times longer; --window FROM-TO scans one stretch of a long clip.

Needs numpy and ffmpeg; the faces need OpenCV and the face model (as faces.py), and are listed as not assessed
without them.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import VIDEO_EXT, edit_dir, load_json, probe, project_root, save_json, utf8_stdio  # noqa: E402

ALGO = 4          # the measurement's version: a new one measures every clip again
SIZE = 480        # px: the long side of the analysed frame
FPS = 15          # analysed frames a second
FACE_STEP = 0.5   # s between the face samples
LOWPASS = 0.12    # cycles a pixel: the Gaussian weight of the phase correlation's spectrum
PC_MIN = 0.3      # the correlation peak (1 = the same picture moved): below it there is nothing to follow
SMOOTH_S = 0.5    # s: the camera's intended path is the path smoothed over this
SHAKE_WIN_S = 0.6  # s: the jitter's RMS window
SHAKE = 0.04      # % of the long side: the camera's jitter above it is shake (tripods 0.001-0.012, a walk
                  # following someone 0.03, hand-held stairs 0.06-0.4)
RESTLESS = 0.016  # % of the long side: the whole picture's jitter over RESTLESS_S above it is restless (a tripod shot
RESTLESS_S = 2.0  # whose people fidget 0.017-0.028 against 0.004-0.014 calm)
BRIDGE_S = 0.3    # s: frames with nothing to follow this short inside a stretch are bridged
MIN_S = {"shake": 1.0, "restless": 2.0, "black": 0.4, "freeze": 1.0, "dark": 1.0, "bright": 1.0, "speech": 1.0,
         "faces": 1.0, "turn": 1.0}
FACE_GAP_S = 1.0  # a face missed for this long (the detector blinks on small faces) does not break its run
GAP_S = 0.35      # a hole this long inside a run does not break it
UNMEASURED_MIN_S = 0.5
BLACK_PIX, BLACK_SHARE = 26, 0.97   # a frame is black: this share of its pixels darker than BLACK_PIX
DARK = 42         # mean brightness (0-255) of a dark frame
CLIP_PIX, BRIGHT_SHARE, BRIGHT_MEAN = 250, 0.22, 225  # overexposed: this share clipped, or a mean this bright
FREEZE_ABS, FREEZE_REL = 0.15, 0.25  # frozen: a difference under both 0.15 and a quarter of the clip's median
CUT_CORR = 0.4    # a cut: the coarse picture correlates with the previous one less than this (brightness apart)
THUMB = 24        # px: the long side of the coarse picture for the cut
THUMB_EVERY = 7   # frames between the coarse pictures kept for the tail check (about 0.5 s)
FLAT = 3.0        # a coarse picture with less contrast than this (0-255) is flat (black, a white card)
TAIL_S = 6.0      # s: a cut this close to the end, then another picture to it, is an editor's tail
END_EPS = 0.3     # s: a stretch ending this close to the clip's end reaches it
SR = 16000
VOICE_BAND = (300.0, 3400.0)
SOUND_PIECE_S = 30.0               # s of sound analysed at a time (a 2-hour clip stays in a few MB)
HOP_S, WIN_S = 0.25, 1.5            # the sound's hints: one every 0.25 s over 1.5 s around it
SPEECH_DYN = 9.0                    # dB: the voice band's swing (90th minus 15th percentile) of speech
SPEECH_MOD = 0.45                   # share of the level's modulation at the syllable rate (2.5-8 Hz)
SPEECH_OVER = 12.0                  # dB above the clip's noise floor
SPEECH_ABS = -60.0                  # dBFS: quieter than this is no speech
SMALL_FACE = 22   # px of the analysed frame: a narrower face is too small to judge its turn
COUNT = 0.7       # detector score of a face that counts (a far face scores 0.7-0.8; false ones are filtered first)
TURN_GAP_S = 1.5  # s: a face facing the camera within this after facing away has turned to it
COVER_PAD = 0.25  # s: a strangers window is hidden this much before and after (vp_defects.COVER_PAD)

TIP = {
    "shake": "from the hand: take a steadier stretch, or keep it only if the motion is meant",
    "restless": "under text or a slow push it reads as fidgeting: a quieter stretch, if there is one",
    "tail": "an editing app's outro: end the shot before it",
    "black": "black frames: start or end the shot outside them",
    "freeze": "a frozen picture: start or end the shot outside it",
    "dark": "dark: lift it with the source's look, or take another stretch",
    "bright": "overexposed: the clipped white cannot be brought back; take another stretch",
}


# --- decoding ------------------------------------------------------------------------------------------------------

def coarse_corr(a, b):
    """Correlation of two coarse pictures, brightness and contrast apart: 1 the same, 0 unrelated; two flat ones
    (black after black) are the same, a flat one after a picture is not."""
    import numpy as np
    sa, sb = float(a.std()), float(b.std())
    if sa < FLAT or sb < FLAT:
        return 1.0 if sa < FLAT and sb < FLAT and abs(float(a.mean()) - float(b.mean())) < 30 else 0.0
    return float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb))


def new_picture(fr, cut):
    """Is the picture after a cut unlike anything before it in the clip? (A light switched on near the end is a cut
    to every frame-to-frame measure, but the picture after it was seen before.)"""
    import numpy as np
    th = [(t, np.array(c, dtype=float)) for t, c in zip(fr["t"], fr.get("thumb") or []) if c is not None]
    after = [c for t, c in th if t > cut + 0.05]
    before = [c for t, c in th if t < cut - 0.3]
    if not after or not before:
        return True
    return max(coarse_corr(x, y) for x in after for y in before) < 1 - CUT_CORR


def frame_size(w, h, size=SIZE):
    """(w, h) of the analysed frame: the long side `size`, both even."""
    k = size / max(w, h)
    return max(2, round(w * k / 2) * 2), max(2, round(h * k / 2) * 2)


def window_args(a, b):
    return (["-ss", f"{a:.3f}"] if a > 0 else []), ["-t", f"{b - a:.3f}"]


def read_exact(f, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = f.read(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return bytes(buf)


class Shifts:
    """Frame-to-frame shift of the whole frame by phase correlation: the cross-power spectrum of the two frames,
    whitened, weighted by a Gaussian low-pass (fine noise and the compression's block grid would pull the peak to
    zero), back to space; the peak's place is the shift, refined to a fraction of a pixel by a Gaussian fit, and its
    height (1 for the same picture moved) says whether there was anything to follow."""

    def __init__(self, w, h):
        import numpy as np
        self.np = np
        self.w, self.h = w, h
        self.win = np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)
        fy = np.fft.fftfreq(h)[:, None]
        fx = np.fft.rfftfreq(w)[None, :]
        self.lp = np.exp(-(fx * fx + fy * fy) / (2 * LOWPASS ** 2))
        self.norm = float(np.fft.irfft2(self.lp, s=(h, w))[0, 0])  # the peak of a picture against itself
        self.prev = None

    def peak(self, r):
        np = self.np
        h, w = r.shape
        iy, ix = np.unravel_index(int(np.argmax(r)), r.shape)
        v = float(r[iy, ix])

        def sub(c, m, at):  # Gaussian fit through three points along one axis; the correlation wraps around
            c0, c1, c2 = (max(at(k % m), 1e-9) for k in (c - 1, c, c + 1))
            l0, l1, l2 = np.log(c0), np.log(c1), np.log(c2)
            den = l0 - 2 * l1 + l2
            off = 0.5 * (l0 - l2) / den if den < -1e-9 else 0.0
            return c + max(-0.5, min(0.5, off))

        fy = sub(iy, h, lambda k: float(r[k, ix]))
        fx = sub(ix, w, lambda k: float(r[iy, k]))
        if fy > h / 2:
            fy -= h
        if fx > w / 2:
            fx -= w
        return fx, fy, v

    def step(self, g):
        """-> (dx, dy, ok) from the previous frame (the picture's content moved by dx, dy px); ok False: nothing to
        follow (too little detail, a cut, the first frame)."""
        np = self.np
        cur = np.fft.rfft2((g - g.mean()) * self.win)
        prev, self.prev = self.prev, cur
        if prev is None:
            return 0.0, 0.0, False
        cross = cur * np.conj(prev)
        r = np.fft.irfft2(cross / (np.abs(cross) + 1e-9) * self.lp, s=(self.h, self.w)) / self.norm
        dx, dy, v = self.peak(r)
        return (dx, dy, True) if v >= PC_MIN else (0.0, 0.0, False)


class BlockShifts:
    """The camera's own shift: the median of the shifts of 3 x 3 blocks (Shifts on each), at least 3 of them with
    something to follow. A person or an object moving across part of the frame moves a few blocks, not the median."""

    def __init__(self, w, h, n=3):
        bw, bh = w // n, h // n
        self.boxes = [(x * bw, y * bh, bw, bh) for y in range(n) for x in range(n)]
        self.parts = [Shifts(bw, bh) for _ in self.boxes]

    def step(self, g):
        import numpy as np
        got = []
        for (x, y, bw, bh), sh in zip(self.boxes, self.parts):
            dx, dy, ok = sh.step(np.ascontiguousarray(g[y:y + bh, x:x + bw]))
            if ok:
                got.append((dx, dy))
        if len(got) < 3:
            return 0.0, 0.0, False
        return float(np.median([d[0] for d in got])), float(np.median([d[1] for d in got])), True


def face_detector(w, h):
    """(a YuNet detector for w x h frames, None) or (None, why it is unavailable)."""
    import faces as fc
    ok, why = fc.available()
    if not ok:
        return None, why
    try:
        import cv2
        try:
            cv2.setLogLevel(2)  # errors only: the DNN backend's notes are not the person's business
        except Exception:
            pass
        return cv2.FaceDetectorYN_create(str(fc.model_path()), "", (w, h), 0.6), None
    except Exception as ex:  # an old OpenCV without YuNet, a broken model file
        return None, f"OpenCV could not load the face model ({str(ex)[:120]})"


def measure_picture(path, a, b, w, h, fps=FPS, faces=True):
    """The frames of path between a and b: per frame stats and shifts, faces every FACE_STEP s."""
    import numpy as np
    det, why = face_detector(w, h) if faces else (None, "off (--no-faces)")
    pre, dur = window_args(a, b)
    cmd = ["ffmpeg", "-v", "error", "-nostdin", *pre, "-i", str(path), *dur, "-map", "0:v:0", "-an", "-sn", "-dn",
           "-vf", f"fps={fps},scale={w}:{h}:flags=area,format=bgr24", "-f", "rawvideo", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    n = w * h * 3
    sh, cam = Shifts(w, h), BlockShifts(w, h)
    cols = {k: [] for k in ("t", "mean", "lo", "hi", "diff", "hist", "corr", "dx", "dy", "ok", "wx", "wy",
                                    "wok", "thumb")}
    fsamples, next_face = [], a
    prev_g, prev_h, prev_c, k = None, None, None, 0
    tw, th = max(2, w * THUMB // max(w, h)), max(2, h * THUMB // max(w, h))
    lum = np.array([0.114, 0.587, 0.299], dtype=np.float32)
    try:
        while True:
            buf = read_exact(proc.stdout, n)
            if len(buf) < n:
                break
            bgr = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            g = bgr.astype(np.float32) @ lum
            t = a + k / fps
            hist = np.bincount(np.minimum(g, 255).astype(np.uint8).ravel() >> 3, minlength=32) / g.size
            dx, dy, ok = cam.step(g)
            wx, wy, wok = sh.step(g)
            cols["t"].append(round(t, 3))
            cols["mean"].append(round(float(g.mean()), 2))
            cols["lo"].append(round(float((g < BLACK_PIX).mean()), 4))
            cols["hi"].append(round(float((g >= CLIP_PIX).mean()), 4))
            cols["diff"].append(round(float(np.abs(g - prev_g).mean()), 3) if prev_g is not None else None)
            cols["hist"].append(round(float(np.abs(hist - prev_h).sum()), 4) if prev_h is not None else None)
            c = g[:h - h % th, :w - w % tw].reshape(th, h // th, tw, w // tw).mean(axis=(1, 3))
            cols["corr"].append(round(coarse_corr(prev_c, c), 3) if prev_c is not None else None)
            cols["thumb"].append([int(v) for v in c.ravel()] if k % THUMB_EVERY == 0 else None)
            cols["dx"].append(round(dx, 3))
            cols["dy"].append(round(dy, 3))
            cols["ok"].append(1 if ok else 0)
            cols["wx"].append(round(wx, 3))
            cols["wy"].append(round(wy, 3))
            cols["wok"].append(1 if wok else 0)
            if det is not None and t + 1e-6 >= next_face:
                _, f = det.detect(np.ascontiguousarray(bgr))
                fsamples.append({"t": round(t, 3), "faces": [[round(float(v), 1) for v in r[:4]] + [round(float(r[14]), 3)]
                                                              + [round(float(v), 1) for v in r[4:14]]
                                                              for r in (f if f is not None else [])]})
                next_face += FACE_STEP
            prev_g, prev_h, prev_c, k = g, hist, c, k + 1
    finally:
        proc.stdout.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        proc.wait()
    if proc.returncode != 0 and not cols["t"]:
        sys.exit(f"ffmpeg could not decode {path}: {err.strip()[-300:]}")
    fdata = {"step": FACE_STEP, "frame": [w, h], "samples": fsamples} if det is not None else None
    return cols, fdata, why if det is None else None


def measure_sound(path, a, b):
    """The voice band's level of the clip's sound every 10 ms, dBFS -> {t0, rate, db}. None: no sound. Judged per
    window by speech_flags(), so a stretch read from the kept measurement of the whole clip is judged as if it were
    measured alone (its own noise floor)."""
    import numpy as np
    pre, dur = window_args(a, b)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", *pre, "-i", str(path), *dur, "-vn", "-ac", "1", "-ar",
                             str(SR), "-f", "s16le", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    nfft, hop = 400, SR // 100
    win = np.hanning(nfft).astype(np.float32)
    fr = np.fft.rfftfreq(nfft, 1.0 / SR)
    band_bins = (fr >= VOICE_BAND[0]) & (fr <= VOICE_BAND[1])
    norm = float((win.astype(np.float64) ** 2).sum()) * nfft / 2
    piece = max(nfft, int(SOUND_PIECE_S * SR)) // hop * hop
    buf = np.zeros(0, np.float32)
    out, total = [], 0
    try:
        while True:  # the sound piece by piece: the memory stays that of one piece however long the clip
            raw = read_exact(proc.stdout, piece * 2)
            if raw:
                total += len(raw) // 2
                buf = np.concatenate([buf, np.frombuffer(raw[:len(raw) // 2 * 2], np.int16).astype(np.float32) / 32768.0])
            if len(buf) >= nfft:
                nfr = 1 + (len(buf) - nfft) // hop
                idx = np.arange(nfft)[None, :] + hop * np.arange(nfr)[:, None]
                spec = np.abs(np.fft.rfft(buf[idx] * win, axis=1)) ** 2
                band = spec[:, band_bins].sum(axis=1)
                out.extend(round(float(v), 1) for v in 10 * np.log10(band / norm + 1e-12))  # ~dBFS of the band
                buf = buf[nfr * hop:]
            if not raw:
                break
    finally:
        proc.stdout.close()
        proc.wait()
    if total < SR // 2:
        return None
    return {"t0": round(a, 3), "rate": 100, "db": out}


def speech_flags(snd):
    """{t0, rate, db} -> per HOP_S: speech-like or not {hop, win, floor, t, speech, level}."""
    import numpy as np
    band_db = np.array(snd["db"], dtype=float)
    a, nfr = snd["t0"], len(band_db)
    if nfr < 50:
        return None
    floor = float(np.percentile(band_db, 10))
    per = round(HOP_S * 100)
    half = round(WIN_S * 50)
    mf = np.fft.rfftfreq(2 * half, 0.01)
    syl, allm = (mf >= 2.5) & (mf <= 8.0), (mf >= 0.5) & (mf <= 15.0)
    ts, flags, info = [], [], []
    for s in range(0, nfr, per):
        c = s + per // 2
        seg = band_db[max(0, c - half):min(nfr, c + half)]
        own = band_db[s:s + per]
        if len(seg) < half:
            break
        p90, p15 = float(np.percentile(seg, 90)), float(np.percentile(seg, 15))
        m = seg - seg.mean()
        pw = np.abs(np.fft.rfft(m * np.hanning(len(m)), n=2 * half)) ** 2
        mod = float(pw[syl].sum() / (pw[allm].sum() + 1e-12))
        voiced = float((own > floor + SPEECH_OVER).mean()) if len(own) else 0.0
        sp = (p90 - p15 >= SPEECH_DYN and mod >= SPEECH_MOD and p90 >= floor + SPEECH_OVER and p90 >= SPEECH_ABS
              and voiced >= 0.3)
        ts.append(round(a + s / 100, 3))
        flags.append(bool(sp))
        info.append([round(p90, 1), round(p90 - p15, 1), round(mod, 2), round(voiced, 2)])
    return {"hop": HOP_S, "win": WIN_S, "floor": round(floor, 1), "t": ts, "speech": flags, "level": info}


# --- the cache -----------------------------------------------------------------------------------------------------

def cache_file(project, path):
    p = Path(path).resolve()
    h = hashlib.sha1(str(p).lower().encode("utf-8")).hexdigest()[:10]
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in p.stem)[:40]
    return Path(project) / "_picture_scan" / f"{stem}-{h}.json"


def cache_key(path, size, fps, faces, sound):
    import faces as fc
    st = Path(path).stat()
    model = None
    if faces and fc.available()[0]:
        mp = fc.model_path()
        st_m = mp.stat()
        model = f"{mp.resolve()}:{st_m.st_size}:{st_m.st_mtime_ns}"
    return {"v": ALGO, "path": str(Path(path).resolve()), "mtime_ns": st.st_mtime_ns, "bytes": st.st_size,
            "size": size, "fps": fps, "faces": model if faces else "off", "sound": bool(sound)}


def slice_meas(m, a, b):
    """The measurement cut to a..b (the cache may hold a longer window)."""
    out = dict(m, window=[a, b])
    fr = m.get("frames")
    if fr:
        keep = [k for k, t in enumerate(fr["t"]) if a - 1e-6 <= t < b - 1e-6]
        out["frames"] = {c: [fr[c][k] for k in keep] for c in fr}
        if keep and out["frames"]["diff"]:
            out["frames"]["diff"][0] = None
            out["frames"]["hist"][0] = None
            out["frames"]["ok"][0] = 0
    if m.get("faces"):
        out["faces"] = dict(m["faces"], samples=[s for s in m["faces"]["samples"] if a - 1e-6 <= s["t"] < b - 1e-6])
    if m.get("sound"):
        s = m["sound"]
        i0 = max(0, round((a - s["t0"]) * s["rate"]))
        i1 = max(i0, round((b - s["t0"]) * s["rate"]))
        out["sound"] = dict(s, t0=round(s["t0"] + i0 / s["rate"], 3), db=s["db"][i0:i1])
    return out


def measure(path, window=None, size=SIZE, fps=FPS, faces=True, sound=True, fresh=False, project=None):
    """-> (measurement, cached?) of one clip over window (a, b) or the whole clip."""
    pr = probe(path)
    if not (pr.get("w") and pr.get("h")):
        sys.exit(f"{path}: no video stream (picture.py scans clips; photos are judged on the contact sheet)")
    D = float(pr.get("dur") or 0.0)
    a, b = window if window else (0.0, D)
    a, b = max(0.0, a), min(D, b) if D else b
    if b - a < 0.5:
        sys.exit(f"{path}: the window {a:.2f}-{b:.2f} s is too short (the clip has {D:.2f} s)")
    key = cache_key(path, size, fps, faces, sound)
    cf = cache_file(project or project_root(), path)
    old = load_json(cf) if cf.is_file() and not fresh else None
    if old and old.get("key") == key:
        ca, cb = old["meas"]["window"]
        if ca <= a + 1e-3 and cb >= b - 1e-3:
            return slice_meas(old["meas"], a, b), True
    w, h = frame_size(pr["w"], pr["h"], size)
    cols, fdata, fwhy = measure_picture(path, a, b, w, h, fps, faces)
    snd = measure_sound(path, a, b) if sound and pr.get("has_audio") else None
    meas = {"window": [round(a, 3), round(b, 3)], "dur": round(D, 3), "fps": fps, "frame": [w, h], "frames": cols,
            "faces": fdata, "faces_why": fwhy, "sound": snd,
            "sound_why": None if snd else ("no sound" if not pr.get("has_audio") else
                                           ("off (--no-sound)" if not sound else "the sound is too short"))}
    save_json(cf, {"key": key, "meas": meas})
    return meas, False


# --- from measurements to candidates -------------------------------------------------------------------------------

def runs(flags, gap):
    """[(i, j)] runs of True; a hole of up to `gap` samples inside a run does not break it."""
    out, i, n = [], 0, len(flags)
    while i < n:
        if not flags[i]:
            i += 1
            continue
        j = i
        k = i + 1
        while k < n and k - j - 1 <= gap:
            if flags[k]:
                j = k
            k += 1
        out.append((i, j))
        i = j + 1
    return out


def spans(ts, flags, step, min_s, gap_s=GAP_S, end=None):
    """[(start, end)] of the runs of flagged samples (sample k covers ts[k]..ts[k] + step), at least min_s long."""
    out = []
    for i, j in runs(flags, max(0, round(gap_s / step))):
        a, b = ts[i], ts[j] + step
        if end is not None:
            b = min(b, end)
        if b - a >= min_s - 1e-9:
            out.append((round(a, 2), round(b, 2)))
    return out


def smooth(x, k):
    """Centered moving average of x over 2k+1 samples; the ends are mirrored through the end point, so a straight
    path (a steady pan) stays straight to its ends."""
    import numpy as np
    if k <= 0 or len(x) < 3:
        return x.copy()
    k = min(k, len(x) - 1)
    pad = np.concatenate([2 * x[0] - x[k:0:-1], x, 2 * x[-1] - x[-2:-k - 2:-1]])
    c = np.cumsum(np.concatenate([[0.0], pad]))
    return (c[2 * k + 1:] - c[:-2 * k - 1]) / (2 * k + 1)


def jitter(fr, fps, long_side, cols=("dx", "dy", "ok")):
    """-> (per-frame jitter in % of the long side, per-frame "measured") from the shifts: the camera path (the sum of
    the shifts) minus its SMOOTH_S smoothing, its RMS over SHAKE_WIN_S. A frame with nothing to follow inside a
    measured stretch (up to BRIDGE_S) takes the shift its neighbours suggest instead of breaking the stretch."""
    import numpy as np
    ok = [bool(v) for v in fr[cols[2]]]
    n = len(ok)
    score, measured = np.zeros(n), [False] * n
    k_s, k_w = max(1, round(SMOOTH_S * fps / 2)), max(1, round(SHAKE_WIN_S * fps / 2))
    for i, j in runs(ok, max(0, round(BRIDGE_S * fps))):
        if (j - i + 1) / fps < MIN_S["shake"]:
            continue
        idx = np.arange(i, j + 1)
        good = np.array([ok[q] for q in idx])
        for q in idx:
            measured[q] = True
        for axis in cols[:2]:
            v = np.array(fr[axis][i:j + 1], dtype=float)
            v[~good] = np.interp(idx[~good], idx[good], v[good])
            pos = np.cumsum(v)
            res = pos - smooth(pos, k_s)
            score[i:j + 1] = np.maximum(score[i:j + 1], np.sqrt(smooth(res * res, k_w).clip(min=0)) / long_side * 100)
    return score, measured


def shake_hints(fr, fps, long_side, end):
    """-> (shake spans, restless spans, unmeasured spans). Shake: the camera's own jitter (the blocks' median shift).
    Restless: the camera stands but the whole picture jitters (people fidget, branches toss), over RESTLESS_S."""
    import numpy as np
    t = fr["t"]
    step = 1.0 / fps
    score, measured = jitter(fr, fps, long_side)
    shaky = [measured[q] and score[q] > SHAKE for q in range(len(t))]
    found = []
    speed = [((fr["dx"][q] ** 2 + fr["dy"][q] ** 2) ** 0.5) / long_side * 100 for q in range(len(t))]
    for a, b in spans(t, shaky, step, MIN_S["shake"], end=end):
        ks = [q for q, x in enumerate(t) if a - 1e-6 <= x < b - 1e-6]
        moving = [q for q in ks if speed[q] > SHAKE]  # the window's RMS reaches past the shaking: trim to the motion
        if not moving:
            continue
        a, b = t[moving[0]], min(b, t[moving[-1]] + step)
        if b - a < MIN_S["shake"] - 1e-9:
            continue
        vals = [float(score[q]) for q, x in enumerate(t) if a - 1e-6 <= x < b - 1e-6]
        found.append((a, b, max(vals) if vals else 0.0, float(np.median(vals)) if vals else 0.0))
    restless = []
    if "wx" in fr:
        whole, wmeas = jitter(fr, fps, long_side, ("wx", "wy", "wok"))
        avg = smooth(whole, max(1, round(RESTLESS_S * fps / 2)))
        flag = [wmeas[q] and avg[q] > RESTLESS and not shaky[q] for q in range(len(t))]
        for a, b in spans(t, flag, step, MIN_S["restless"], end=end):
            vals = [float(avg[q]) for q, x in enumerate(t) if a - 1e-6 <= x < b - 1e-6]
            restless.append((a, b, max(vals) if vals else 0.0, float(np.median(vals)) if vals else 0.0))
    first = [False] + [not v for v in measured[1:]]  # the first frame has no shift: not "unmeasured"
    unmeasured = spans(t, first, step, UNMEASURED_MIN_S, gap_s=0.15, end=end)
    return found, restless, unmeasured


def picture_hints(m):
    """-> (candidates, not assessed) from the per-frame measurements."""
    fr = m["frames"]
    if not fr or not fr["t"]:
        return [], []
    a, b = m["window"]
    fps = m["fps"]
    step = 1.0 / fps
    t = fr["t"]
    n = len(t)
    long_side = max(m["frame"])
    reaches_end = b >= (m.get("dur") or b) - END_EPS
    black = [fr["lo"][k] >= BLACK_SHARE for k in range(n)]
    diffs = sorted(d for d in fr["diff"] if d is not None)
    med = diffs[len(diffs) // 2] if diffs else 0.0
    fz = min(FREEZE_ABS, FREEZE_REL * med) if med > 0 else FREEZE_ABS
    frozen = [fr["diff"][k] is not None and fr["diff"][k] < fz and not black[k] for k in range(n)]
    # a cut: the coarse picture is another one (an exposure jump keeps it: the correlation ignores brightness)
    cuts = [t[k] for k in range(1, n) if fr["corr"][k] is not None and fr["corr"][k] < CUT_CORR]
    dark = [fr["mean"][k] < DARK and not black[k] for k in range(n)]
    bright = [fr["hi"][k] >= BRIGHT_SHARE or fr["mean"][k] >= BRIGHT_MEAN for k in range(n)]
    out, notes = [], []

    def add(kind, s, e, why):
        out.append({"kind": kind, "start": s, "end": e, "why": why})

    tail = None
    if reaches_end:
        endrun = []
        for kind, flags in (("black", black), ("frozen", frozen)):
            for s, e in spans(t, flags, step, MIN_S["black" if kind == "black" else "freeze"], end=b):
                if e >= b - END_EPS:
                    endrun.append((s, kind))
        if endrun:
            s, kind = min(endrun)
            c = [x for x in cuts if s - 0.6 <= x <= s + 0.2]
            s = min(c) if c else s
            tail = (s, f"{'a cut, then ' if c else ''}{'black' if kind == 'black' else 'a frozen picture'} to the end")
        else:
            late = [x for x in cuts if b - x <= TAIL_S and x > a + 1.0 and new_picture(fr, x)]
            if late:
                s = max(late)
                tail = (s, f"a cut at {s:.2f} s, then another picture to the end ({b - s:.1f} s)")
    if tail:
        add("tail", round(tail[0], 2), round(b, 2), tail[1] + ": an editing app's outro (CapCut and the like)?")
    end_of_body = tail[0] if tail else b

    def outside_tail(s, e):
        return (s, min(e, end_of_body)) if s < end_of_body - 0.2 else None

    for kind, flags, why in (("black", black, "black frames"), ("freeze", frozen, "a frozen picture"),
                             ("dark", dark, None), ("bright", bright, None)):
        for s, e in spans(t, flags, step, MIN_S[kind], end=b):
            se = outside_tail(s, e)
            if not se or se[1] - se[0] < MIN_S[kind] - 1e-9:
                continue
            ks = [k for k in range(n) if se[0] - 1e-6 <= t[k] < se[1] - 1e-6]
            if kind == "dark":
                why = f"dark: mean brightness {sum(fr['mean'][k] for k in ks) / len(ks):.0f} of 255"
            elif kind == "bright":
                why = (f"overexposed: {max(fr['hi'][k] for k in ks):.0%} of the frame clipped white, mean "
                       f"{sum(fr['mean'][k] for k in ks) / len(ks):.0f} of 255")
            add(kind, se[0], se[1], why)
    found, restless, unmeasured = shake_hints(fr, fps, long_side, b)
    for s, e, peak, mid in found:
        se = outside_tail(s, e)
        if se and se[1] - se[0] >= MIN_S["shake"] - 1e-9:
            add("shake", se[0], se[1], f"the camera shakes: {mid:.3f} % of the frame (up to {peak:.3f} %), a tripod "
                                       f"stays under {SHAKE} %")
    for s, e, peak, mid in restless:
        se = outside_tail(s, e)
        if se and se[1] - se[0] >= MIN_S["restless"] - 1e-9:
            add("restless", se[0], se[1], f"the camera stands but the picture is restless: {mid:.3f} % of the frame "
                                          f"(up to {peak:.3f} %, a calm shot under {RESTLESS} %): people or things "
                                          f"move a lot")
    hidden = [(c["start"], c["end"]) for c in out if c["kind"] in ("tail", "black")]
    for s, e in unmeasured:
        if any(s >= x - 0.2 and e <= y + 0.2 for x, y in hidden):
            continue
        notes.append({"what": "shake", "start": s, "end": e,
                      "why": "too little detail to measure the motion (a sky, a wall, darkness, a blur): look at it"})
    return out, notes


def main_face(fs):
    return max(fs, key=lambda f: f[2] * f[3]) if fs else None


def face_hints(fdata, end=None):
    """-> (candidates, not assessed, summary) from the face samples {step, frame, samples: [{t, faces}]}."""
    import defects
    import faces as fc
    smp = fdata.get("samples") or []
    step = fdata.get("step") or FACE_STEP
    w = (fdata.get("frame") or [SIZE, SIZE])[0]
    if not smp:
        return [], [], {"usual_faces": 0, "max_faces": 0}
    times = [s["t"] for s in smp]
    keep, _ = fc.clean_frames([[f[:5] for f in s["faces"]] for s in smp], times, step, width=w)
    clean = []
    for s, kk in zip(smp, keep):
        ks = [[round(v, 6) for v in q[:5]] for q in kk]
        clean.append([f for f in s["faces"] if [round(v, 6) for v in f[:5]] in ks])
    count = [sum(1 for f in fs if f[4] >= COUNT) for fs in clean]
    srt = sorted(count)
    usual = srt[(3 * len(srt)) // 4]  # the upper quartile: a person seen a quarter of the time is "usual" (a small
    # face is found only now and then), a passer-by for a few seconds is not
    out, notes = [], []
    for a, b in spans(times, [c > usual for c in count], step, MIN_S["faces"], gap_s=FACE_GAP_S, end=end):
        top = max(c for t, c in zip(times, count) if a - 1e-6 <= t < b - 1e-6)
        out.append({"kind": "faces", "start": a, "end": b,
                    "why": f"{top} faces, usually {usual}: strangers? If they may not be shown, mark cut.json "
                           f"sources.<name>.strangers [[{a:.2f}, {b:.2f}]]: they are hidden only under an opaque full "
                           f"scene over the whole window, {COVER_PAD} s before and after (a panel or a window does not "
                           f"hide them), or shown after the person's yes"})
    states = [defects.turn_state(main_face(fs), min_w=SMALL_FACE) if fs else (None, None, None) for fs in clean]
    st = [s[0] for s in states]
    for a, b in spans(times, [s == "small" for s in st], step, 1.0, gap_s=FACE_GAP_S, end=end):
        notes.append({"what": "turn", "start": a, "end": b,
                      "why": "faces too small to judge a turn (a wide shot): look at it yourself, or scan again with "
                              "--size 960 (slower)"})
    # a turn: the face looked away for a while, then faces the camera for a while (single samples flicker)
    away = spans(times, [s == "away" for s in st], step, MIN_S["turn"], gap_s=step, end=end)
    facing_runs = spans(times, [s == "facing" for s in st], step, MIN_S["turn"], gap_s=step, end=end)
    for a, b in facing_runs:
        # the away run ends at its last sample + step; the samples sit on the frame grid (0, 0.533, 1.0 ...), so
        # the next run may start a little before that
        before = [y for x, y in away if x < a - 1e-6 and y <= a + step + 1e-6 and a - y <= TURN_GAP_S + 1e-6]
        if not before:
            continue
        k = times.index(min(times, key=lambda t: abs(t - a)))
        eyes = states[k][2] or 0.0
        out.append({"kind": "turn", "start": a, "end": b,
                    "why": f"a face turns to the camera at {a:.2f} s (eyes {eyes:.2f} of the face width apart after "
                           f"looking away; a person who turns around reads as looking at the viewer)"})
    return out, notes, {"usual_faces": usual, "max_faces": max(count) if count else 0, "facing": facing_runs}


def sound_hints(snd, facing=()):
    if not snd or not snd.get("t"):
        return []
    out = []
    for a, b in spans(snd["t"], snd["speech"], snd["hop"], MIN_S["speech"], gap_s=0.5):
        cam = sum(max(0.0, min(b, y) - max(a, x)) for x, y in facing) >= 0.5 * (b - a)
        out.append({"kind": "speech", "start": a, "end": b,
                    "why": "speech-like sound in the clip's own sound: someone may be talking"
                           + (", with a face turned to the camera: speaking to the camera?" if cam else "")
                           + " Under a voice-over the lips would not match: look at it (or transcribe it)"})
    return out


def candidates(m):
    """-> {"candidates", "unassessed", "faces"} of one measurement; every candidate "unchecked"."""
    cs, notes = picture_hints(m) if m.get("frames") else ([], [])
    facing, finfo = (), None
    if m.get("faces"):
        fc_, fn, finfo = face_hints(m["faces"], end=m["window"][1])
        cs += fc_
        notes += fn
        facing = finfo.get("facing") or ()
    else:
        notes.append({"what": "faces", "start": m["window"][0], "end": m["window"][1],
                      "why": f"turns and strangers not checked: {m.get('faces_why') or 'no face samples'}"})
    snd, why = m.get("sound"), m.get("sound_why") or "no sound"
    if snd and "db" in snd:
        snd = speech_flags(snd)
        why = why if snd else "the stretch is too short"
    if snd:
        cs += sound_hints(snd, facing)
    else:
        notes.append({"what": "speech", "start": m["window"][0], "end": m["window"][1],
                      "why": f"speech not checked: {why}"})
    for c in cs:
        c["status"] = "unchecked"
        if c["kind"] in TIP and TIP[c["kind"]] not in c["why"]:
            c["why"] += f"; {TIP[c['kind']]}"
    cs.sort(key=lambda c: (c["start"], c["kind"]))
    return {"candidates": cs, "unassessed": notes, "faces": finfo}


def to_reel(cands, shots, source, duration=None):
    """Adds "in_reel" to each candidate: [{shot, start, end}] wherever the clip's stretch is on screen in the finished
    video (each shot's start and speed; a clip used twice is on screen twice). A strangers candidate also gets the
    window to hide (COVER_PAD on each side, within the video)."""
    from pic_track import source_windows
    D = float(duration) if duration else None
    for c in cands:
        wins = []
        for i, w0, w1 in source_windows(shots, source, c["start"], c["end"]):
            w = {"shot": i, "start": round(w0, 3), "end": round(w1, 3)}
            if c["kind"] == "faces":
                w["hide_from"] = round(max(0.0, w0 - COVER_PAD), 3)
                w["hide_to"] = round(min(D, w1 + COVER_PAD) if D else w1 + COVER_PAD, 3)
            wins.append(w)
        c.setdefault("in_reel", []).extend(wins)
    return cands


# --- the command ---------------------------------------------------------------------------------------------------

def parse_window(s):
    try:
        a, b = (float(x) for x in s.replace(",", ".").split("-", 1))
    except ValueError:
        sys.exit(f"--window {s}: FROM-TO in seconds of the clip, e.g. 30-75")
    if b <= a:
        sys.exit(f"--window {s}: TO must be after FROM")
    return a, b


def clip_files(paths):
    out = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            out += sorted(q for q in p.iterdir() if q.suffix.lower() in VIDEO_EXT)
        elif p.is_file():
            out.append(p)
        else:
            sys.exit(f"no file or folder {p}")
    return out


def edit_sources(e, project):
    """cut.json of the video -> {resolved file: [source names]} of its video sources."""
    from cut import resolve
    cut = load_json(e / "cut.json", {}) or {}
    by = {}
    for name, sv in (cut.get("sources") or {}).items():
        f = sv.get("file") if isinstance(sv, dict) else sv
        if not f:
            continue
        p = resolve(f, project, e)
        if p.suffix.lower() in VIDEO_EXT and p.is_file():
            by.setdefault(str(p.resolve()).lower(), (p, []))[1].append(name)
    return by


def show(rep):
    for s in rep["sources"]:
        names = f" ({', '.join(s['names'])})" if s.get("names") else ""
        print(f"{s['file']}{names}: {s['window'][0]:.2f}-{s['window'][1]:.2f} s, frames {s['frame'][0]}x"
              f"{s['frame'][1]} {'(cached)' if s['cached'] else '(measured)'}")
        mine = [c for c in rep["candidates"] if c["file"] == s["file"]]
        for c in mine:
            reel = "; ".join(f"video {w['start']:.2f}-{w['end']:.2f}" + (f" (hide {w['hide_from']:.2f}-{w['hide_to']:.2f})"
                                                                            if "hide_from" in w else "")
                             for w in c.get("in_reel") or [])
            print(f"  {c['id']}  {c['kind']:<7} {c['start']:7.2f}-{c['end']:7.2f} s  {c['why']}"
                  + (f"  [{reel}]" if reel else ""))
        if not mine:
            print("  no candidates")
        for u in [u for u in rep["unassessed"] if u["file"] == s["file"]]:
            print(f"  not assessed: {u['what']} {u['start']:.2f}-{u['end']:.2f} s: {u['why']}")
        if s.get("faces"):
            print(f"  faces: usually {s['faces']['usual_faces']}, at most {s['faces']['max_faces']}")
    if rep["candidates"]:
        print("Hints only, all unchecked: look at each one on the clip and decide; nothing was excluded. Faces smaller "
              "than about 2 % of the frame are not found at all: strangers far away are for the eye "
              "(references/no-speaker.md, \"Is the footage usable\").")


def cmd_scan(a):
    project = project_root()
    e = edit_dir(a.edit) if a.edit else None
    by = edit_sources(e, project) if e else {}
    files = clip_files(a.paths) if a.paths else [p for p, _ in by.values()]
    if not files:
        sys.exit("nothing to scan: name clips or folders, or --edit edit/<id> with video sources in cut.json")
    try:
        import numpy  # noqa: F401
    except ImportError:
        print("picture.py scan needs numpy (pip install numpy): look at the clips by eye")
        return
    window = parse_window(a.window) if a.window else None
    cap = load_json(e / "captions.json", {}) if e else None
    shots = None
    if cap:
        from pic_track import pic_shots
        shots = pic_shots(cap)
    rep = {"version": ALGO, "sources": [], "candidates": [], "unassessed": []}
    n = 0
    for f in files:
        if not a.json:
            print(f"scanning {f} ...", file=sys.stderr, flush=True)
        m, cached = measure(f, window, a.size, FPS, faces=not a.no_faces, sound=not a.no_sound, fresh=a.fresh,
                            project=project)
        res = candidates(m)
        names = (by.get(str(f.resolve()).lower()) or (None, []))[1]
        for name in names:
            if shots is not None:
                to_reel(res["candidates"], shots, name, (cap or {}).get("duration"))
        for c in res["candidates"]:
            n += 1
            c["id"] = f"c{n:02d}"
            c["file"] = str(f)
            if names:
                c["names"] = names
        for u in res["unassessed"]:
            u["file"] = str(f)
        rep["sources"].append({"file": str(f), "names": names, "window": m["window"], "dur": m["dur"],
                               "frame": m["frame"], "cached": cached, "faces": res["faces"]})
        rep["candidates"] += res["candidates"]
        rep["unassessed"] += res["unassessed"]
    if e and not cap:
        rep["note"] = f"no captions.json in {e} yet: after cut.py, scan again for the seconds of the finished video"
    if e:
        save_json(e / "picture_scan.json", rep)
    if a.out:
        save_json(Path(a.out), rep)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False))
        return
    show(rep)
    if rep.get("note"):
        print(rep["note"])
    if e:
        print(f"{e / 'picture_scan.json'}: {len(rep['candidates'])} candidate(s)")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan", help="hints about the bad stretches of clips")
    p.add_argument("paths", nargs="*", help="clips or folders of clips")
    p.add_argument("--edit", help="edit/<id>: its cut.json names and the finished video's seconds")
    p.add_argument("--window", help="FROM-TO seconds of the clip (one stretch of a long clip)")
    p.add_argument("--size", type=int, default=SIZE, help=f"px of the long side of the analysed frame ({SIZE})")
    p.add_argument("--no-faces", action="store_true")
    p.add_argument("--no-sound", action="store_true")
    p.add_argument("--model", help="the YuNet model file (as faces.py)")
    p.add_argument("--fresh", action="store_true", help="measure again, ignore the kept measurements")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("--out", help="also write the report to this file")
    p.set_defaults(fn=cmd_scan)
    a = ap.parse_args()
    if getattr(a, "model", None):
        import faces as fc
        fc.MODEL = a.model
    a.fn(a)


if __name__ == "__main__":
    main()
