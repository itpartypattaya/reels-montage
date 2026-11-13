"""A stand-in for a real narration cut tight: syllables of 130-260 ms with no pause between the words, each a consonant
(a hiss, a stop's short silence and burst, or a murmur) and a vowel, the vowels in the mix of everyday speech (the
open "a" most often), a voice built of its pitch's partials shaped by three formants in a chain, an optional room noise under
the whole track. Not a voice either, but closer to one than a steady tone: it has the dips, the clicks and the hiss
that made the mouth chatter on a real recording.

    info = dense_speech(path, f0=120, scale=1.0, seed=7)

writes a 16-bit mono WAV and returns {"words": [(start, end)], "syllables": [(start, end, vowel, (a, b))], "env":
the clean voice's RMS per 1/30 s frame, "sr": the sample rate}; (a, b) is the vowel's own stretch inside its syllable.
"""
import wave

import numpy as np

# formants (F1, F2, F3) of a man's vowels, Hz; a woman's are about 15-20 % higher (scale)
FORMANTS = {"a": (700, 1220, 2600), "o": (500, 850, 2500), "u": (320, 750, 2300),
            "e": (480, 1850, 2550), "i": (290, 2300, 3000), "y": (320, 1500, 2400)}
# everyday speech: the open "a" (and the reduced "o" read as one) most often
MIX = (("a", 0.40), ("o", 0.15), ("e", 0.15), ("i", 0.10), ("u", 0.10), ("y", 0.10))
BANDWIDTHS = (80, 100, 160)


def _gain(f, F, B):
    """The magnitude of a resonance at F with bandwidth B, at the frequency f (1 at f = 0)."""
    r = f / F
    return 1.0 / np.sqrt((1 - r * r) ** 2 + (f * B / (F * F)) ** 2)


def _hiss(rng, n, sr, lo, hi):
    """White noise kept to lo..hi Hz, unit RMS."""
    x = rng.standard_normal(n)
    spec = np.fft.rfft(x)
    fr = np.fft.rfftfreq(n, 1.0 / sr)
    spec[(fr < lo) | (fr > hi)] = 0
    y = np.fft.irfft(spec, n)
    return y / (np.sqrt(np.mean(y * y)) or 1.0)


def dense_speech(path, f0=120.0, scale=1.0, seed=7, dur=8.0, sr=48000, noise_db=None, lead_in=0.0):
    rng = np.random.default_rng(seed)
    names = [v for v, _ in MIX]
    weights = np.array([w for _, w in MIX])
    n = int(round((dur + lead_in + 0.5) * sr))
    voice = np.zeros(n)
    syllables, words = [], []
    t = lead_in
    word_start, left_in_word = t, int(rng.integers(1, 5))
    phase = 0.0
    while t < lead_in + dur:
        length = float(rng.uniform(0.13, 0.26))
        kind = rng.choice(["hiss", "stop", "murmur"], p=[0.35, 0.4, 0.25])
        cons = float(rng.uniform(0.03, 0.06))
        i0, i1 = int(t * sr), int((t + length) * sr)
        c1 = int((t + cons) * sr)
        loud = float(rng.uniform(0.35, 1.0))
        if kind == "hiss":
            lo, hi = (3500, 7500) if rng.random() < 0.6 else (1800, 5500)  # an "s" or a "sh"
            voice[i0:c1] += 0.12 * loud * _hiss(rng, c1 - i0, sr, lo, hi)
        elif kind == "stop":
            b = c1 - int(0.012 * sr)  # silence, then a 12 ms burst
            voice[b:c1] += 0.18 * loud * _hiss(rng, c1 - b, sr, 1500, 6000) * np.hanning(c1 - b)
        # the vowel: the pitch's partials up to 4 kHz shaped by the vowel's formants, a rise and fall of loudness
        v = names[int(rng.choice(len(names), p=weights / weights.sum()))]
        F = [x * scale for x in FORMANTS[v]]
        m = i1 - c1
        tt = np.arange(m) / sr
        pitch = f0 * (1 + 0.06 * np.sin(2 * np.pi * 0.9 * (t + tt)) + 0.01 * rng.standard_normal())
        ph = phase + 2 * np.pi * np.cumsum(pitch) / sr
        phase = float(ph[-1])
        tone = np.zeros(m)
        for h in range(1, int(4000 // f0) + 1):
            fh = h * f0
            # the vocal tract's resonances in a chain (their gains multiply), over a source falling 6 dB an octave
            g = float(np.prod([_gain(fh, Fk, Bk) for Fk, Bk in zip(F, BANDWIDTHS)])) / h
            tone += g * np.sin(h * ph)
        tone /= np.sqrt(np.mean(tone * tone)) or 1.0
        shape = np.sin(np.pi * np.linspace(0, 1, m)) ** 0.6
        if kind == "murmur":  # a nasal ("m", "n") before the vowel: a quieter low hum
            hum_n = c1 - i0
            hum = np.sin(2 * np.pi * f0 * np.arange(hum_n) / sr) * 0.15 * loud
            voice[i0:c1] += hum
        voice[c1:i1] += 0.32 * loud * tone * shape
        syllables.append((t, t + length, v, (t + cons, t + length)))
        t += length
        left_in_word -= 1
        if left_in_word == 0:  # the next word starts at once: the pauses were cut
            words.append((round(word_start, 3), round(t, 3)))
            word_start, left_in_word = t, int(rng.integers(1, 5))
    if left_in_word and t > word_start:
        words.append((round(word_start, 3), round(t, 3)))
    n = int(round((t + 0.05) * sr))  # the speech runs to the end: no pause to measure the noise on
    voice = voice[:n]
    per = sr / 30.0
    env = [float(np.sqrt(np.mean(voice[int(round(f * per)):int(round((f + 1) * per))] ** 2) or 0.0))
           for f in range(int(n / per))]
    out = voice.copy()
    if noise_db is not None:
        out += 10 ** (noise_db / 20.0) * _hiss(rng, n, sr, 60, sr / 2 - 1)
    pcm = np.clip(np.round(out * 32767), -32768, 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return {"words": words, "syllables": syllables, "env": env, "sr": sr}
