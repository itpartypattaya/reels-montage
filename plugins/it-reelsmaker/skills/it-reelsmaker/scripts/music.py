# -*- coding: utf-8 -*-
"""Music composed in code for a video (numpy synthesis: no model, no sound file, no download) and its beats.json.

    python scripts/music.py --edit edit/<id> [--style groove] [--bpm 104] [--seed 2]   # reel.json -> music, script.json
    python scripts/music.py out.wav --dur 15.4 [--bpm 104] [--style groove|pulse|tension|ambient] \\
        [--stop 3.2 --resume 3.7] [--button 11.0] [--pause 6.9-7.8 ...] [--seed 1]

--edit: the length is the finished video's (captions.json duration + the end card or sting the stage adds), the
style, tempo, seed and markers come from reel.json -> music ({"source": "code", "style": "groove", "bpm": 104,
"markers": {"stop": "label", "resume": "translation", "button": "punchline"}}; a marker names a text block of
script.json by its id or role, or a second), the command line overrides them. It writes edit/<id>/music.wav and
edit/<id>/beats.json. With an output file instead: <out>.wav and <out>.beats.json.

Styles (instruments, rhythm, density; references/music.md):
  groove   kick on 1 and 3 with a pushed kick before 3, claps on 2 and 4, eighth hats, a bouncing bass on eighths and
           sixteenths, electric-piano stabs on the off-beats: dense, for a light comic series
  pulse    a soft kick on 1, a rim on 3, a plucked note on every beat, a pad chord per bar: calm, medium-low density
  tension  a ticking clock on sixteenths, a low pulsing bass on eighths, a drone and a riser per two bars: a timer
  ambient  slow pad swells over two bars, a soft bell every two bars, no drums: no marked beat (the grid is still
           written, "beat_marked": false, scenes need not land on it)
Markers (each lands on the nearest beat of the grid, then on a frame): --stop the "tape stops" (the last 0.45 s slow
down to nothing: the music stops on the beat, a turn in the text), --resume it comes back lighter (under reading),
--button an accent (kick, chord, cymbal) and then silence (the reaction), --pause A-B silence inside. A marker outside
the video, or closer than one beat to another, is an error; nothing is written.
The file: WAV PCM s16, 48 kHz, stereo, exactly round(duration * 48000) samples, the peak at -6 dBFS (headroom for the
master), never clipped. The same version, parameters and seed give the same bytes (beats.json -> params_id); another
seed another arrangement. beats.json (schema 1): the WAV's sha256, the samples, the beats heard (time, bar, position,
strong/weak), where the beat is heard ("active"), the silences meant to be there ("silence": stop, pause, button) and
each marker's requested and resolved time with the text block it serves. master_audio.py --music reads it.
"""
import argparse
import hashlib
import json
import math
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ALGO = "music.py 1"
SCHEMA = 1
RATE = 48000
FPS = 30
PEAK_DB = -6.0
BPM_RANGE = (70, 140)
STYLES = ("groove", "pulse", "tension", "ambient")
STOP_S = 0.45      # the tape-stop's slow-down before the stop marker
BUTTON_S = 1.8     # the button's accent rings this long, then silence
END_FADE_S = 0.25  # the music's own fade at the very end (the master adds none to code music)
START_S = 0.015    # it eases in from silence: a kick at full scale on the first sample made the master's AAC overshoot
# chord progressions per style (MIDI notes, one chord per bar); the seed picks one
PROGRESSIONS = {
    "groove": [[[50, 53, 57, 60], [55, 59, 62, 65], [48, 52, 55, 59], [57, 60, 64, 67]],
               [[52, 55, 59, 62], [57, 61, 64, 67], [50, 54, 57, 61], [55, 59, 62, 66]]],
    "pulse": [[[48, 55, 60, 64], [45, 52, 57, 60], [41, 48, 53, 57], [43, 50, 55, 59]],
              [[50, 57, 62, 65], [46, 53, 58, 62], [43, 50, 55, 58], [45, 52, 57, 61]]],
    "tension": [[[45, 52, 57, 58], [45, 52, 56, 57], [44, 51, 56, 57], [46, 53, 57, 58]],
                [[43, 50, 55, 56], [43, 50, 54, 55], [42, 49, 54, 55], [44, 51, 55, 56]]],
    "ambient": [[[48, 55, 62, 64, 71], [53, 60, 64, 69, 72], [45, 52, 59, 64, 67], [50, 57, 62, 65, 69]],
                [[47, 54, 61, 64, 66], [52, 59, 64, 66, 71], [49, 56, 61, 64, 68], [54, 61, 66, 69, 73]]],
}


class MusicError(ValueError):
    """A request music.py cannot play: printed, nothing written."""


# --- instruments (each returns a mono float array) ----------------------------------------------------------------

def _np():
    import numpy as np
    return np


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _t(dur):
    np = _np()
    return np.arange(max(1, int(dur * RATE))) / RATE


def _env(t, attack, decay):
    np = _np()
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / decay)


def _hp(x, k=1):
    """A crude high-pass: k first differences (a brighter noise)."""
    np = _np()
    for _ in range(k):
        x = np.diff(x, prepend=x[:1])
    return x / (np.abs(x).max() + 1e-9)


def kick(rng, amp=1.0, soft=False):
    np = _np()
    t = _t(0.32)
    f = 46 + (95 if soft else 120) * np.exp(-t / 0.03)
    body = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t / (0.14 if soft else 0.2))
    click = _hp(rng.standard_normal(len(t)), 2) * np.exp(-t / 0.002) * (0.05 if soft else 0.12)
    return amp * (body + click)


def clap(rng, amp=1.0):
    np = _np()
    t = _t(0.2)
    x = _hp(rng.standard_normal(len(t)), 1)
    e = sum(np.where(t >= d, np.exp(-(t - d) / 0.012), 0) for d in (0.0, 0.009, 0.018)) * 0.5 + np.exp(-t / 0.06) * 0.6
    return amp * x * e


def hat(rng, amp=1.0, length=0.05):
    t = _t(length)
    return amp * _hp(rng.standard_normal(len(t)), 3) * _env(t, 0.0005, length / 3)


def rim(rng, amp=1.0):
    np = _np()
    t = _t(0.08)
    tone = np.sin(2 * np.pi * 1700 * t) * np.exp(-t / 0.012)
    return amp * (tone + 0.4 * _hp(rng.standard_normal(len(t)), 2) * np.exp(-t / 0.006))


def tick(rng, amp=1.0):
    np = _np()
    t = _t(0.03)
    return amp * (np.sin(2 * np.pi * 3200 * t) * np.exp(-t / 0.004) + 0.3 * _hp(rng.standard_normal(len(t)), 3)
                  * np.exp(-t / 0.002))


def cymbal(rng, amp=1.0, length=1.4):
    np = _np()
    t = _t(length)
    return amp * _hp(rng.standard_normal(len(t)), 3) * _env(t, 0.001, length / 3.5) * np.minimum(1, (length - t) / 0.05)


def bass(m, dur, amp=1.0):
    """A plucked bass: a few harmonics, the upper ones fading first."""
    np = _np()
    t = _t(dur)
    f = mtof(m)
    x = sum(np.sin(2 * np.pi * f * k * t) / k ** 1.3 * np.exp(-t / (0.45 / k)) for k in range(1, 7))
    return amp * 0.7 * x * np.minimum(1, t / 0.004) * np.minimum(1, np.maximum(0, dur - t) / 0.015)


def keys(ms, dur, amp=1.0):
    """An electric-piano stab: two-operator FM, its brightness fading."""
    np = _np()
    t = _t(dur)
    out = sum(np.sin(2 * np.pi * mtof(m) * t + 1.4 * np.exp(-t / 0.1) * np.sin(2 * np.pi * mtof(m) * t)) for m in ms)
    return amp * out / len(ms) * np.exp(-t / 0.5) * np.minimum(1, t / 0.003) * np.minimum(1, np.maximum(0, dur - t) / 0.03)


def pad(ms, dur, amp=1.0, attack=0.6):
    """A soft pad: slightly detuned partials, a slow attack and release."""
    np = _np()
    t = _t(dur)
    out = 0
    for m in ms:
        for det in (-0.06, 0.06):
            f = mtof(m + det)
            out = out + sum(np.sin(2 * np.pi * f * k * t + k) / k ** 1.8 for k in range(1, 4))
    e = np.minimum(1, t / attack) * np.minimum(1, np.maximum(0, dur - t) / min(attack, dur / 2))
    return amp * out / (2 * len(ms)) * e


def pluck(m, dur, amp=1.0):
    np = _np()
    t = _t(dur)
    f = mtof(m)
    x = sum(np.sin(2 * np.pi * f * k * t) / k ** 1.6 * np.exp(-t / (0.35 / k ** 0.7)) for k in range(1, 6))
    return amp * x * np.minimum(1, t / 0.002) * np.minimum(1, np.maximum(0, dur - t) / 0.02)


def bell(m, dur, amp=1.0):
    np = _np()
    t = _t(dur)
    f = mtof(m)
    return amp * np.sin(2 * np.pi * f * t + 2.0 * np.exp(-t / 0.4) * np.sin(2 * np.pi * f * 3.5 * t)) * _env(t, 0.004, dur / 3)


def drone(m, dur, amp=1.0):
    np = _np()
    t = _t(dur)
    lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.5 * t)
    x = np.sin(2 * np.pi * mtof(m) * t) + 0.5 * np.sin(2 * np.pi * mtof(m + 7) * t)
    return amp * x * lfo * np.minimum(1, t / 0.3) * np.minimum(1, np.maximum(0, dur - t) / 0.3)


def riser(rng, dur, amp=1.0):
    np = _np()
    t = _t(dur)
    return amp * _hp(rng.standard_normal(len(t)), 2) * (t / dur) ** 2


# --- arrangement --------------------------------------------------------------------------------------------------

def put(buf, x, at, pan=0.0, end=None):
    """Add x at second `at` (panned -1..1), cut at sample `end` (a stop, a pause, the button)."""
    np = _np()
    i = int(round(at * RATE))
    j = min(buf.shape[1], i + len(x), end if end is not None else buf.shape[1])
    if i < 0 or j <= i:
        return
    x = x[: j - i]
    a = (pan + 1) * math.pi / 4
    buf[0, i:j] += x * math.cos(a) * math.sqrt(2)
    buf[1, i:j] += x * math.sin(a) * math.sqrt(2)


def play(style, buf, rng, prog, beat, k0, k1, start=None, cut=None, light=False):
    """The style's pattern on beats k0 .. k1 - 1 of the grid (by number, never by a rounded second: Codex review, a
    beat at 8.654 s played before a button marker rounded to 8.667 s). start: the first event no earlier than this
    second (a resume marker on its frame); cut: nothing sounds past this second. light = the part under reading."""
    end = int(round(cut * RATE)) if cut is not None else None
    for k in range(k0, k1):
        at = k * beat if (start is None or k != k0) else max(k * beat, start)
        bar, pos = k // 4, k % 4
        ch = prog[bar % len(prog)]
        root = ch[0] - 12 if ch[0] >= 48 else ch[0]
        v = 0.85 + 0.15 * rng.random()  # a hand's velocity
        if style == "groove":
            if not light and pos in (0, 2):
                put(buf, kick(rng, 0.95 * v), at, 0, end)
            if not light and pos == 1:
                put(buf, kick(rng, 0.55 * v), at + beat * 0.75, 0, end)  # the pushed kick before 3
            if pos in (1, 3):
                put(buf, clap(rng, (0.4 if light else 0.6) * v), at, 0.2, end)
            for h in (0.0, 0.5):
                if not light:
                    put(buf, hat(rng, 0.12 if h else 0.09), at + h * beat, 0.35, end)
            for h, step in ((0.0, 0), (0.5, 7), (0.75, 12)):
                if light and h == 0.75:
                    continue
                put(buf, bass(root + step, beat * (0.45 if h else 0.4), 0.8 * v), at + h * beat, -0.05, end)
            if not light and pos in (1, 3):
                put(buf, keys(ch, beat * 0.45, 0.4), at + 0.5 * beat, -0.3, end)
        elif style == "pulse":
            if pos == 0:
                put(buf, kick(rng, (0.5 if light else 0.75) * v, soft=True), at, 0, end)
                put(buf, pad(ch, beat * 4, 0.22), at, 0, end)
            if pos == 2 and not light:
                put(buf, rim(rng, 0.25 * v), at, -0.2, end)
            put(buf, pluck(ch[(pos + bar) % len(ch)] + 12, beat * 0.9, 0.32 * v), at, 0.25 * (pos - 1.5) / 1.5, end)
        elif style == "tension":
            for q in range(4):
                put(buf, tick(rng, (0.16 if q else 0.26) * v), at + q * beat / 4, 0.3, end)
            for h in (0.0, 0.5):
                put(buf, bass(root, beat * 0.4, (0.55 if light else 0.75) * v), at + h * beat, 0, end)
            if pos == 0 and bar % 2 == 0:
                put(buf, drone(root, beat * 8, 0.25), at, 0, end)
                if not light:
                    put(buf, riser(rng, beat * 8, 0.08), at, 0.1, end)
        else:  # ambient: swells and bells, no drums
            if (pos == 0 and bar % 2 == 0) or k == k0:  # on its own first beat too: back at once after a resume
                put(buf, pad(ch, beat * 8, 0.3, attack=beat * 2.5 if k != k0 or k0 == 0 else beat), at, 0, end)
                put(buf, bell(ch[-1] + 12, beat * 4, 0.12 * v), at + beat * 0.02, 0.3, end)


def button(buf, rng, style, prog, at):
    """The punchline's accent: kick, a held chord and a cymbal, all gone by BUTTON_S."""
    np = _np()
    end = int(round((at + BUTTON_S) * RATE))
    ch = prog[0]
    if style != "ambient":
        put(buf, kick(rng, 1.0), at, 0, end)
        put(buf, cymbal(rng, 0.18), at, 0.3, end)
    put(buf, keys(ch + [ch[0] + 12], BUTTON_S - 0.05, 0.75) if style != "ambient" else
        bell(ch[-1] + 12, BUTTON_S - 0.05, 0.35), at, -0.1, end)
    put(buf, bass(ch[0] - 12, BUTTON_S * 0.7, 0.9), at, 0, end)
    i, j = int(round(at * RATE)), min(buf.shape[1], end)
    if j > i:
        n = j - i
        tail = np.ones(n)
        f = min(n, int(0.3 * RATE))
        tail[n - f:] = np.linspace(1, 0, f)
        buf[:, i:j] *= tail


def tape_stop(buf, at):
    """The last STOP_S before `at` slow down to nothing (the tape stops), silence from `at` on (until a resume)."""
    np = _np()
    i1 = int(round(at * RATE))
    i0 = max(0, i1 - int(STOP_S * RATE))
    n = i1 - i0
    if n > 10:
        seg = buf[:, i0:i1].copy()
        rate = np.linspace(1.0, 0.0, n) ** 1.4
        pos = np.cumsum(rate)
        pos = pos / pos[-1] * (n * 0.55)
        for c in range(2):
            buf[c, i0:i1] = np.interp(pos, np.arange(n), seg[c]) * np.linspace(1, 0, n) ** 0.5
    buf[:, i1:] = 0


# --- the request: markers on the grid -----------------------------------------------------------------------------

def on_beat(t, beat):
    """A requested second -> the nearest beat, on a frame."""
    k = round(t / beat)
    return k, round(round(k * beat * FPS) / FPS, 3)


def resolve(dur, bpm, stop=None, resume=None, btn=None, pauses=(), blocks=None):
    """Markers -> their beats, checked. blocks: {kind: block id} for beats.json. -> markers [{kind, requested, at, ...}]."""
    if not BPM_RANGE[0] <= bpm <= BPM_RANGE[1]:
        raise MusicError(f"--bpm {bpm:g}: the tempo is {BPM_RANGE[0]}-{BPM_RANGE[1]} bpm")
    if not dur or dur <= 0:
        raise MusicError("--dur: the video's length in seconds")
    beat = 60.0 / bpm
    blocks = blocks or {}
    marks = []
    for kind, t in (("stop", stop), ("resume", resume), ("button", btn)):
        if t is None:
            continue
        if not 0 < t < dur:
            raise MusicError(f"--{kind} {t:g} s is outside the video (0-{dur:g} s)")
        k, at = on_beat(t, beat)
        if not 0 < at < dur:
            raise MusicError(f"--{kind} {t:g} s lands on the beat at {at:g} s, outside the video (0-{dur:g} s)")
        marks.append({"kind": kind, "requested": round(t, 3), "at": at, "beat": k, **({"block": blocks[kind]}
                                                                                    if kind in blocks else {})})
    for spec in pauses:
        try:
            a, b = (float(x) for x in str(spec).split("-"))
        except ValueError:
            raise MusicError(f"--pause {spec}: A-B in seconds (6.9-7.8)")
        if not 0 < a < b < dur:
            raise MusicError(f"--pause {spec}: outside the video (0-{dur:g} s) or not A < B")
        ka, ta = on_beat(a, beat)
        kb, tb = on_beat(b, beat)
        if kb <= ka:
            raise MusicError(f"--pause {spec}: shorter than a beat ({beat:.2f} s at {bpm:g} bpm)")
        marks.append({"kind": "pause", "requested": round(a, 3), "at": ta, "beat": ka, "end_requested": round(b, 3),
                      "end": tb, "end_beat": kb})
    # closer than a beat = on the same beat, by number (two neighbouring beats rounded to frames may be 0.567 s apart at
    # 104 bpm, a beat being 0.577 s: Codex review)
    times = sorted([(m["beat"], m["at"], m["kind"]) for m in marks]
                   + [(m["end_beat"], m["end"], "pause end") for m in marks if m["kind"] == "pause"])
    for (bx, x, kx), (by_, y, ky) in zip(times, times[1:]):
        if by_ - bx < 1 and not (kx == "pause" and ky == "pause end"):
            raise MusicError(f"{kx} at {x:g} s and {ky} at {y:g} s are closer than a beat ({beat:.2f} s at {bpm:g} "
                             f"bpm): move one, or pick another tempo")
    by = {m["kind"]: m for m in marks}
    if "resume" in by and "stop" not in by:
        raise MusicError("--resume needs --stop: the music resumes after it stops")
    if "stop" in by and "resume" in by and by["resume"]["at"] <= by["stop"]["at"]:
        raise MusicError(f"--resume ({by['resume']['at']:g} s) must come after --stop ({by['stop']['at']:g} s)")
    if "button" in by and any(m["at"] >= by["button"]["at"] for m in marks if m["kind"] in ("stop", "resume")):
        raise MusicError("--button is the last accent: stop and resume come before it")
    return sorted(marks, key=lambda m: m["at"])


def compose(dur, bpm, style, seed, marks):
    """-> (int16 stereo samples [n, 2], beats.json's beats, active, silence)."""
    np = _np()
    if style not in STYLES:
        raise MusicError(f"--style {style!r}: one of {', '.join(STYLES)}")
    rng = np.random.default_rng([seed, STYLES.index(style), int(bpm * 1000)])
    prog = PROGRESSIONS[style][int(rng.integers(len(PROGRESSIONS[style])))]
    beat = 60.0 / bpm
    n = int(round(dur * RATE))
    by = {m["kind"]: m for m in marks if m["kind"] != "pause"}
    pauses = [(m["at"], m["end"]) for m in marks if m["kind"] == "pause"]
    stop, resume, btn = (by.get(k, {}).get("at") for k in ("stop", "resume", "button"))
    ks, kr, kb = (by.get(k, {}).get("beat") for k in ("stop", "resume", "button"))
    k_end = int(math.ceil(dur / beat - 1e-9))  # the beats that start inside the video
    first_end = stop if stop is not None else (btn if btn is not None else dur)
    k1 = ks if ks is not None else (kb if kb is not None else k_end)
    buf = np.zeros((2, n + RATE))  # a second past the end: notes ring into it, then it is cut
    play(style, buf, rng, prog, beat, 0, k1)
    active = [[0.0, first_end]]
    heard = [(0, k1)]  # beat numbers heard: [from, to)
    silence = []
    if stop is not None:
        tape_stop(buf, min(stop, ks * beat))  # the beat on the stop itself never sounds
        if resume is not None:
            second_end = btn if btn is not None else dur
            k2 = kb if kb is not None else k_end
            part = np.zeros_like(buf)
            play(style, part, rng, prog, beat, kr, k2, start=resume, cut=second_end, light=True)
            buf += part
            active.append([resume, second_end])
            heard.append((kr, k2))
            silence.append({"from": stop, "to": resume, "why": "stop"})
        else:
            silence.append({"from": stop, "to": round(dur, 3), "why": "stop"})
    for m in [m for m in marks if m["kind"] == "pause"]:
        a, b, ka, kb2 = m["at"], m["end"], m["beat"], m["end_beat"]
        heard = [(x0, x1) for y0, y1 in heard for x0, x1 in ((y0, min(y1, ka)), (max(y0, kb2), y1)) if x1 > x0]
        i0, i1 = int(round(min(a, ka * beat) * RATE)), int(round(min(b, kb2 * beat) * RATE))
        f = int(0.02 * RATE)
        buf[:, max(0, i0 - f):i0] *= np.linspace(1, 0, min(f, i0))
        buf[:, i0:i1] = 0
        silence.append({"from": a, "to": b, "why": "pause"})
        out = []
        for x0, x1 in active:
            if b <= x0 or a >= x1:
                out.append([x0, x1])
                continue
            if a > x0:
                out.append([x0, a])
            if b < x1:
                out.append([b, x1])
        active = out
    if btn is not None:
        buf[:, int(round(btn * RATE)):] = 0
        button(buf, rng, style, prog, btn)
        silence.append({"from": round(min(dur, btn + BUTTON_S), 3), "to": round(dur, 3), "why": "button"})
    buf = buf[:, :n]
    f = min(n, int(START_S * RATE))
    buf[:, :f] *= np.linspace(0, 1, f)
    if btn is None and (stop is None or resume is not None):
        f = min(n, int(END_FADE_S * RATE))
        buf[:, n - f:] *= np.linspace(1, 0, f)
    peak = float(np.abs(buf).max())
    if peak <= 0:
        raise MusicError("the music came out silent: give it some time before the first stop")
    buf *= 10 ** (PEAK_DB / 20) / peak
    pcm = np.round(buf.T * 32767).astype("<i2")
    beats = []
    for k in range(k_end):  # heard by number, listed at the frame it lands on
        if any(x0 <= k < x1 for x0, x1 in heard):
            t = round(round(k * beat * FPS) / FPS, 3)
            beats.append({"n": k, "t": t, "bar": k // 4, "pos": k % 4, "strength": "strong" if k % 4 == 0 else "weak"})
    return pcm, beats, [[round(a, 3), round(b, 3)] for a, b in active], sorted(silence, key=lambda s: s["from"])


def write(out, beats_out, dur, bpm, style, seed, marks):
    """Compose, write the WAV and beats.json. -> beats.json's document."""
    pcm, beats, active, silence = compose(dur, bpm, style, seed, marks)
    params = {"algo": ALGO, "samples": int(pcm.shape[0]), "rate": RATE, "bpm": bpm, "style": style, "seed": seed,
              "markers": [{k: m[k] for k in ("kind", "requested", "at", "end") if k in m} for m in marks]}
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    from vp_script import sha256_of
    doc = {"schema": SCHEMA, "algo": ALGO,
           "time": "seconds of the finished video, end card included; the music starts at its 0",
           "music_start": 0.0, "wav": out.name, "wav_sha256": sha256_of(out), "rate": RATE, "samples": int(pcm.shape[0]),
           "duration": round(pcm.shape[0] / RATE, 6), "fps": FPS, "bpm": bpm, "style": style, "seed": seed,
           "beat_marked": style != "ambient",
           "params_id": hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12],
           "rounding": "a marker lands on the nearest beat of the grid (beat k at k * 60 / bpm s), then on a frame",
           "beats": beats, "active": active, "silence": silence, "markers": marks}
    beats_out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


# --- --edit: the video's own answers --------------------------------------------------------------------------------

def edit_request(a):
    """--edit edit/<id>: the length with the end card, reel.json -> music, the markers on script.json's blocks."""
    from types import SimpleNamespace
    from reels_common import edit_dir, load_config, load_json
    from vp_core import end_tail
    e = edit_dir(a.edit)
    cap = load_json(e / "captions.json") or {}
    plan = load_json(e / "visual_plan.json") or {}
    base = float(plan.get("duration") or cap.get("duration") or 0)
    if not base:
        sys.exit(f"no rough cut in {e}: the music is made for the finished length (cut.py first)")
    tail = end_tail(SimpleNamespace(cmd="music"), plan)
    s = load_config(e)[0]
    m = s.get("music") if isinstance(s.get("music"), dict) else {}
    if m.get("source") not in (None, "code"):
        print(f"note: reel.json -> music.source is {m['source']!r}, not code: making the music anyway (as asked)")
    tm, blocks = None, {}
    if (e / "script.json").is_file():
        from vp_script import timing_of
        _, tm = timing_of(e)
        blocks = {b["id"]: b for b in tm["blocks"]}
    bpm = a.bpm or m.get("bpm") or (tm or {}).get("bpm") or 104
    if tm and tm.get("bpm") and abs(float(tm["bpm"]) - float(bpm)) > 1e-6:
        print(f"⚠ the text is timed on {tm['bpm']:g} bpm, the music is {bpm:g} bpm: the blocks will not start on its "
              f"beats (visual_plan.py script edit/{e.name} --bpm {bpm:g})")
    marks, ids = {}, {}
    for kind in ("stop", "resume", "button"):
        v = getattr(a, kind)
        v = v if v is not None else (m.get("markers") or {}).get(kind)
        if v is None:
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            marks[kind] = float(v)
            continue
        ref = str(v)
        b = blocks.get(ref) or next((x for x in (tm or {}).get("blocks") or [] if x["role"] == ref), None)
        if b is None:
            try:
                marks[kind] = float(ref)
                continue
            except ValueError:
                sys.exit(f"music marker {kind}: {ref!r} is not a block id or role of script.json, nor a second")
        marks[kind], ids[kind] = b["start"], b["id"]
    pauses = list(a.pause or (m.get("markers") or {}).get("pause") or [])
    return (e / "music.wav", e / "beats.json", round(base + tail, 3), float(bpm), a.style or m.get("style") or "groove",
            a.seed if a.seed is not None else int(m.get("seed") or 1), marks, ids, pauses, tail)


def main():
    from reels_common import utf8_stdio
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?", help="the WAV to write (its beats.json goes next to it); with --edit: none")
    ap.add_argument("--edit", help="edit/<id>: the video's length, reel.json -> music, script.json's blocks")
    ap.add_argument("--dur", type=float, help="the video's length in seconds (the end card included)")
    ap.add_argument("--bpm", type=float, help=f"tempo {BPM_RANGE[0]}-{BPM_RANGE[1]} (default 104)")
    ap.add_argument("--style", choices=STYLES)
    ap.add_argument("--seed", type=int, help="another arrangement of the same request (default 1)")
    ap.add_argument("--stop", type=float, help="the tape stops here (a turn in the text)")
    ap.add_argument("--resume", type=float, help="the music comes back, lighter, under reading")
    ap.add_argument("--button", type=float, help="the punchline's accent, then silence for the reaction")
    ap.add_argument("--pause", action="append", metavar="A-B", help="silence inside, seconds A-B (repeatable)")
    a = ap.parse_args()
    if a.edit:
        if a.out or a.dur:
            sys.exit("--edit takes the length and the file from the video: drop the output and --dur")
        out, bout, dur, bpm, style, seed, req, ids, pauses, tail = edit_request(a)
    else:
        if not a.out or not a.dur:
            sys.exit("give the output WAV and --dur, or --edit edit/<id>")
        out = Path(a.out)
        bout = out.with_suffix(".beats.json")
        dur, bpm, style, seed, tail = a.dur, float(a.bpm or 104), a.style or "groove", a.seed if a.seed is not None else 1, 0
        req, ids, pauses = {k: getattr(a, k) for k in ("stop", "resume", "button")}, {}, a.pause or []
    try:
        marks = resolve(dur, bpm, req.get("stop"), req.get("resume"), req.get("button"), pauses, ids)
        doc = write(out, bout, dur, bpm, style, seed, marks)
    except MusicError as x:
        sys.exit(f"music.py: {x}; nothing written")
    print(f"{out}: {doc['duration']:.3f} s ({doc['samples']} samples, 48 kHz stereo s16, peak {PEAK_DB:g} dBFS), {style}, "
          f"{bpm:g} bpm, seed {seed}" + (f" (the video + {tail:g} s end card)" if tail else ""))
    for m in marks:
        print(f"  {m['kind']:<7} {m['requested']:>7.3f} -> {m['at']:.3f} s (beat {m['beat']})"
              + (f" .. {m['end']:.3f}" if m.get("end") is not None else "") + (f"  block {m['block']}" if m.get("block") else ""))
    print(f"{bout}: {len(doc['beats'])} beats heard, active {doc['active']}, silence "
          + (", ".join(f"{s['why']} {s['from']:g}-{s['to']:g}" for s in doc["silence"]) or "none"))
    print("listen to it before the render; another arrangement: --seed N; master_audio.py --music <wav> mixes it")


if __name__ == "__main__":
    main()
