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
MOVES = ("none", "still", "push", "pull", "pan")  # a shot's own motion (cut.json picture, footage.prepare)
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
    # a narration cut (cut_voice.py, captions.json -> voice) copies its sound-only segments as the background
    want = copy_shots(cap.get("segments"), {g.get("source") for g in cap.get("segments") or []} if cap.get("voice") else ())
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


# --- the purpose of each stretch and where each rule applies (references/no-speaker.md) -----------------------------
# speaker  the person speaking is on screen: the voice is on camera and the shot is the sound source's own video at
#          the seconds of its sound
# picture  the main picture with no one speaking on screen: voice-over shots, other clips, photos
# graphic  a designed scene is the picture: a "fill" shot (the style's background), the whole "scenes only" video
# A scene, a B-roll or a meme laid over a speaker stretch is an insert: the rules of the speaker column hold for it.
PURPOSES = ("speaker", "picture", "graphic")
ALL = frozenset(PURPOSES)
RULES = {
    "coverage": {"speaker"},          # the insert budget, coverage_max (vp_validate)
    "full_in_a_row": {"speaker"},     # no two full scenes in a row (vp_scenes): the face disappears for too long
    "full_scenes_max": {"speaker"},   # the brand tone's ceiling of full scenes (vp_scenes.tone_issues)
    "hook_full": {"speaker"},         # a full hook at most hook_full_max_s (vp_scenes)
    "face_visible": {"speaker"},      # the speaker's face stays on screen
    "text_off_faces": {"speaker", "picture"},
    "ending": set(ALL),               # only the ending / CTA in the last seconds (a structure rule, not the face's)
    "reading": set(ALL), "tone": set(ALL), "facts": set(ALL), "no_slideshow": set(ALL),
    "strangers": {"picture"},         # strangers only under an opaque full scene (vp_defects.stranger_issues)
    "lips": {"picture"},              # lips moving under someone else's voice: a self-check item
}
SYNC = 1.0 / 30 + 0.002  # s: a shot of the sound source within a frame of its sound's seconds is the speaker speaking


def is_speaking(g, segments):
    """The shot is the sound source's own video at the seconds of its sound for its whole length (lips in sync with
    the voice): one sound segment holds the whole shot, at the same speed, from the same source second. Another speed
    drifts off the voice at once; a shot that runs on past its segment's end shows seconds that are not heard (review
    of PR #50: such a shot counted as the speaker and slipped past the strangers check)."""
    if g.get("kind", "video") != "video":
        return False
    gs = g.get("speed") or 1.0
    for s in segments or []:
        if s.get("source") != g.get("source"):
            continue
        a, d = s["out_start"], s["out_dur"]
        if not (a - 1e-6 <= g["out_start"] and g["out_start"] + g["out_dur"] <= a + d + 1e-6):
            continue
        sp = s.get("speed") or 1.0
        if abs(sp - gs) <= 1e-6 and abs(s["src_start"] + (g["out_start"] - a) * sp - g["src_start"]) <= SYNC:
            return True
    return False


def purposes(cap, voice="on_camera"):
    """[(out_start, out_end, purpose)] per picture shot, in timeline order. voice: reel.json -> voice; only on_camera
    has a speaker on screen."""
    cap = cap or {}
    segs = cap.get("segments") or []
    out = []
    for g in sorted(pic_shots(cap), key=lambda x: x["out_start"]):
        if g.get("kind") == "fill":
            p = "graphic"
        elif voice == "on_camera" and is_speaking(g, segs):
            p = "speaker"
        else:
            p = "picture"
        out.append((g["out_start"], round(g["out_start"] + g["out_dur"], 3), p))
    return out


def speaker_seconds(spans, a, b):
    """Seconds of [a, b) over speaker stretches."""
    return sum(max(0.0, min(b, y) - max(a, x)) for x, y, p in spans if p == "speaker")


def over_speaker(spans, a, b):
    """An insert over [a, b) lies (at least partly) over the speaker: the speaker's rules hold for it. A cut made
    before the picture track, or one with no shots at all, is all speaker as before."""
    if not spans:
        return True
    return speaker_seconds(spans, a, b) > 1e-6 or (b > spans[-1][1] and spans[-1][2] == "speaker")


def all_speaker(spans):
    return all(p == "speaker" for _, _, p in spans)


def speaker_parts(spans, a, b):
    """The parts of [a, b) over the speaker: [(from, to)]. All of it when every stretch is the speaker (a talking head,
    or a cut made before the picture track: the budget counts as it always did, the end card included)."""
    if not spans or all_speaker(spans):
        return [(a, b)]
    out = [(max(a, x), min(b, y)) for x, y, p in spans if p == "speaker" and min(b, y) > max(a, x)]
    if b > spans[-1][1] and spans[-1][2] == "speaker":
        out.append((max(a, spans[-1][1]), b))
    return out


def on_graphic(shots, t):
    """A scene starting at second t is drawn on the style's background (a fill shot): it is the whole picture there."""
    g = shot_at(shots, t)
    return bool(g) and g.get("kind") == "fill"


def own_motion(g):
    """The shot carries a motion of its own (move other than none): the virtual camera and the drift are off on it."""
    return bool(g) and (g.get("move") or "none") != "none"
