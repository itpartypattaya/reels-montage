# -*- coding: utf-8 -*-
"""The picture track of a rough cut, apart from its sound. Imported by the other scripts; no command line.

captions.json -> segments are the SOUND pieces of the rough cut (speech checks, leveling, subtitles, speech_mask.py
--edl read them). captions.json -> shots are the PICTURE shots: what is on screen, from which source and which seconds.
Everything that asks "which picture is at second t, and where does the picture jump" (faces, the camera's source
seconds, the drift, callout tracks, picture defects, the plan's join hints) reads the shots through pic_shots().

A picture shot: {i, kind, source, src_start, src_end, speed, out_start, out_dur, move, look}
  i          occurrence number in timeline order; a copy keeps the i of the sound segment it copies
  kind       "video" | "photo" | "fill" (the style's background, no source file)
  source     the source name from cut.json (None for "fill")
  src_*      the source window; on "photo" and "fill" conventional coordinates 0..out_dur, never a real second
  speed      playback speed of the window (1.0 on "photo" and "fill")
  out_*      where the shot sits on the finished timeline
  move       "none" (no motion of its own: the virtual camera and the drift may act) | "still" | "push" | "pull" | "pan"
  look       the look applied to this shot's source, None = the video's look

Words used in code: "picture shots" (this track) and "camera shots" (camera.json): never a bare "shots".

cut.py writes the shots as a copy of the sound segments while no picture of its own is put over the sound. A rough cut
made before the picture track has no "shots" key: its segments are its picture. An explicit empty list means "no
picture" and is never replaced by the segments.
"""
import hashlib

SHOT_KEYS = ("i", "kind", "source", "src_start", "src_end", "speed", "out_start", "out_dur", "move", "look")
CONVENTIONAL = ("photo", "fill")  # kinds whose source seconds are conventional coordinates, not time


def copy_shot(g, audio_only=()):
    """One sound segment -> the picture shot that shows it. A segment from an audio-only source (a recorded voice, no
    video stream) has no picture of its own: a "fill" shot, and the scenes drawn over it are its picture."""
    if g.get("source") in audio_only:
        d = g.get("out_dur")
        return {"i": g.get("i"), "kind": "fill", "source": None, "src_start": 0.0, "src_end": d, "speed": 1.0,
                "out_start": g.get("out_start"), "out_dur": d, "move": "none", "look": None}
    return {"i": g.get("i"), "kind": "video", "source": g.get("source"), "src_start": g.get("src_start"),
            "src_end": g.get("src_end"), "speed": g.get("speed"), "out_start": g.get("out_start"),
            "out_dur": g.get("out_dur"), "move": "none", "look": None}


def copy_shots(segments, audio_only=()):
    """The picture track of a cut whose picture is its sound: one shot per sound segment, the same order."""
    return [copy_shot(g, audio_only) for g in segments or []]


def pic_shots(cap):
    """captions.json -> its picture shots: "shots" when the key exists (an empty list too), else its segments."""
    cap = cap or {}
    if "shots" in cap:
        return list(cap.get("shots") or [])
    return copy_shots(cap.get("segments"))


def follows_sound(cap):
    """True when the picture is a plain copy of the sound segments (or the cut predates the picture track)."""
    cap = cap or {}
    if "shots" not in cap:
        return True
    want = copy_shots(cap.get("segments"))
    have = cap.get("shots") or []
    return len(want) == len(have) and all({k: a.get(k) for k in SHOT_KEYS} == {k: b.get(k) for k in SHOT_KEYS}
                                          for a, b in zip(want, have))


def picture_id(cap):
    """The picture's fingerprint, apart from the sound cut's (vp_core.cut_id): None while the picture follows the sound,
    so a copy changes nothing for the plans made before the picture track."""
    if follows_sound(cap):
        return None
    shots = [tuple(g.get(k) for k in SHOT_KEYS) for g in pic_shots(cap)]
    return hashlib.sha1(repr(((cap or {}).get("duration"), shots)).encode()).hexdigest()[:12]


def shot_at(shots, t):
    """The picture shot on screen at second t (a join belongs to the shot it starts); past the end, the last one."""
    hit = [g for g in shots if g["out_start"] - 1e-6 <= t < g["out_start"] + g["out_dur"] - 1e-6]
    return hit[-1] if hit else (shots[-1] if shots else None)


def source_changes(cap):
    """Seconds where the picture's source changes (another camera angle, another place) in timeline order."""
    shots = sorted(pic_shots(cap), key=lambda g: g["out_start"])
    return [g["out_start"] for p, g in zip(shots, shots[1:]) if g.get("source") != p.get("source")]


def shots_of_words(words, cap):
    """The picture shots (their i) under these words: through each word's sound segment while the picture follows the
    sound (exact: the copy keeps the i), else by the word's start time."""
    if follows_sound(cap):
        return {w.get("seg") for w in words if w.get("seg") is not None}
    shots = pic_shots(cap)
    out = set()
    for w in words:
        g = shot_at(shots, w["start"]) if w.get("start") is not None else None
        if g is not None:
            out.add(g.get("i"))
    return out


def maps_source_time(g):
    """Can a source second land in this shot? Not on a photo or a background: their seconds are conventional."""
    return g.get("kind", "video") not in CONVENTIONAL
