# -*- coding: utf-8 -*-
"""cut.py's picture of its own: a voice-over over other clips and photos, on the whole video or on a stretch of it.
Part of cut.py, with no command line of its own: `python scripts/cut.py edit/<id>` takes this way by itself when cut.json
has a "picture" block (or mixes a sound-only recording with videos). references/no-speaker.md is the full contract.

    "picture": [{"from": "start" | 2.4 | "word:sea#1", "to": "end" | 9.0 | "word:street#1",
                 "shots": [{"source": "pool", "start": 1.0, "dur": 2.5, "speed": 1.0, "fit": "cover",
                            "focus": [0.5, 0.5], "move": "still", "what": "the pool, wide", "why": "the place"},
                           {"source": "sea", "until": "word:street#1", "move": "push"},
                           {"source": "street"}]},
                {"from": "end", "to": 24.0, "shots": [{"fill": true, "what": "the punchline's field", "why": "..."}]}]

Times are seconds of the finished video, "start", "end" (the end of the sound) or "word:<text>#<n>" (the n-th time the
word is said on the edit timeline: the picture cuts where it starts). Outside the blocks the picture is the sound
source's own video at the seconds of its sound, as before; a sound-only recording there has no picture of its own: the
style's background (a "fill" shot) that scenes are drawn over. A source used only in "shots" is a picture source: no
transcript, never opened by speech_mask.py --edl (edl.json -> picture_sources); its own sound is not used.

The order is load -> resolve -> balance -> encode. resolve() works out the whole picture before anything is encoded:
whole frames, every block covered with no gap and no overlap, "until" wins over "dur", the last shot of a block runs to
its end, a clip shorter than its shot is an error with numbers (never a freeze frame or a repeat). The last block may
run past the end of the sound (a text tail with no voice): the sound is padded with silence to its end.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pic_track import MOVES, copy_shot
from reels_common import IMAGE_EXT, run, warn

FITS = ("cover", "contain")
BLACK = "black"  # the fill shot in final.mp4: the scenes drawn over it are its picture


class PictureError(ValueError):
    """A picture block that does not resolve: cut.py prints it and stops before encoding anything."""


def kind_of(sv):
    """A cut.json source as a picture: "photo", "video" or "audio" (a sound-only file: no picture)."""
    if Path(sv["path"]).suffix.lower() in IMAGE_EXT:
        return "photo"
    return "audio" if (sv.get("info") or {}).get("w") is None else "video"


def blocks_of(raw, sources):
    """cut.json "picture" -> the blocks, their shape checked (the times are resolved later, on the edit timeline)."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PictureError('picture is a list of blocks: [{"from": ..., "to": ..., "shots": [...]}]')
    out = []
    for k, b in enumerate(raw):
        if not isinstance(b, dict) or "from" not in b or "to" not in b:
            raise PictureError(f'picture[{k}]: a block needs "from", "to" and "shots"')
        shots = b.get("shots")
        if not isinstance(shots, list) or not shots:
            raise PictureError(f"picture[{k}] has no shots")
        for j, sh in enumerate(shots):
            if not isinstance(sh, dict):
                raise PictureError(f"picture[{k}] shot {j}: a shot is an object")
            if sh.get("fill"):
                continue
            name = sh.get("source")
            if name not in sources:
                raise PictureError(f"picture[{k}] shot {j}: no source {name!r} in cut.json sources "
                                   f"({', '.join(sources)})")
            if kind_of(sources[name]) == "audio":
                raise PictureError(f"picture[{k}] shot {j}: {name!r} is a sound-only file: it has no picture")
            if (sh.get("move") or "none") not in MOVES:
                raise PictureError(f"picture[{k}] shot {j}: move {sh.get('move')!r} (one of {', '.join(MOVES)})")
            if (sh.get("fit") or "cover") not in FITS:
                raise PictureError(f"picture[{k}] shot {j}: fit {sh.get('fit')!r} (cover or contain)")
            fo = sh.get("focus", [0.5, 0.5])
            if not (isinstance(fo, list) and len(fo) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in fo)):
                raise PictureError(f"picture[{k}] shot {j}: focus is [x, y], each 0..1")
            for field in ("start", "dur", "speed"):
                if field in sh and not (isinstance(sh[field], (int, float)) and not isinstance(sh[field], bool)
                                        and math.isfinite(sh[field])):
                    raise PictureError(f"picture[{k}] shot {j}: {field} must be a number")
            sp = float(sh.get("speed", 1.0))
            if not 0.5 <= sp <= 2.0:
                raise PictureError(f"picture[{k}] shot {j}: speed {sp:g} is outside 0.5..2.0")
            if float(sh.get("start", 0.0)) < 0:
                raise PictureError(f"picture[{k}] shot {j}: start must be 0 or more")
        out.append(b)
    return out


def picture_sources(c):
    """Sources shown only in picture blocks (no range of the sound uses them)."""
    used = {sh.get("source") for b in c.get("picture") or [] for sh in b["shots"] if not sh.get("fill")}
    return [n for n in c["sources"] if n in used and not any(r["source"] == n for r in c.get("ranges") or [])]


def _anchor(v, words, fps, end_frames, label, clock=None):
    """A block's or shot's time -> a frame of the finished video. clock: a no-speech reel's timed text blocks
    ("block:<id>" is where that block starts, "block:<id>:end" where it ends)."""
    if v == "start":
        return 0
    if v == "end":
        return end_frames
    if isinstance(v, str) and v.startswith("block:"):
        bid, _, edge = v[6:].partition(":")
        blocks = (clock or {}).get("blocks") or {}
        if bid not in blocks or edge not in ("", "end"):
            raise PictureError(f"{label}: {v!r}: " + (f"no text block {bid!r} in script.json ({', '.join(blocks)})"
                                                      if blocks else "block:<id> names a text block of a no-speech "
                                                                     "reel (script.json)"))
        return round(blocks[bid][1 if edge else 0] * fps)
    if isinstance(v, str) and v.startswith("word:"):
        from vp_core import resolve_at
        try:
            t = resolve_at(v, {"segments": []}, {"words": words})
        except SystemExit as x:
            raise PictureError(f"{label}: {x}")
        return round(t * fps)
    try:
        t = float(v)
    except (TypeError, ValueError):
        raise PictureError(f'{label}: {v!r} is not a time (seconds, "start", "end" or "word:<text>#<n>")')
    if not math.isfinite(t) or t < 0:
        raise PictureError(f"{label}: {v!r} is not a time of the video")
    return round(t * fps)


def resolve(c, segments, words, total):
    """The whole picture track on the edit timeline -> (shots, the video's length in seconds). Each shot has the
    picture-track fields (pic_track.SHOT_KEYS) and its encoding details under "_" keys (frames, fit, focus, copy)."""
    F = c["fps"]
    S = round(total * F)
    sec = lambda f: round(f / F, 3)  # noqa: E731
    blocks = []
    for k, b in enumerate(blocks_of(c.get("picture"), c["sources"])):
        f0 = _anchor(b["from"], words, F, S, f"picture[{k}] from", c.get("clock"))
        f1 = _anchor(b["to"], words, F, S, f"picture[{k}] to", c.get("clock"))
        if f1 <= f0:
            raise PictureError(f"picture[{k}]: its end ({sec(f1)} s) is not after its start ({sec(f0)} s)")
        blocks.append((f0, f1, k, b))
    blocks.sort(key=lambda x: (x[0], x[1]))
    for (a0, a1, ka, _), (b0, b1, kb, _) in zip(blocks, blocks[1:]):
        if b0 < a1:
            raise PictureError(f"picture[{ka}] ({sec(a0)}-{sec(a1)} s) and picture[{kb}] ({sec(b0)}-{sec(b1)} s) overlap")
    if c.get("clock"):  # a no-speech reel: the picture is all there is, from 0 to the end of the text
        for f0, f1, k, _ in blocks:
            if f1 > S:
                raise PictureError(f'picture[{k}] runs past the end of the text ({sec(S)} s): end it at "end"')
        gaps = _uncovered(0, S, sorted((f0, f1) for f0, f1, _, _ in blocks))
        if gaps:
            raise PictureError("the picture leaves " + ", ".join(f"{sec(x)}-{sec(y)} s" for x, y in gaps)
                               + ' uncovered: a no-speech reel has nothing else on screen; add a shot, or a '
                                 '{"fill": true} shot for a stretch drawn only with scenes')
    for n, (f0, f1, k, _) in enumerate(blocks):
        if f0 > S:
            raise PictureError(f"picture[{k}] starts at {sec(f0)} s, after the sound ends ({sec(S)} s): the gap would "
                               f"have nothing on screen; start it at \"end\"")
        if f1 > S and n != len(blocks) - 1:
            raise PictureError(f"picture[{k}] runs past the end of the sound ({sec(S)} s): only the last block may (a "
                               f"tail with no voice)")
    V = max([S] + [f1 for _, f1, _, _ in blocks])
    pieces = []
    for f0, f1, k, b in blocks:
        cur = f0
        for j, sh in enumerate(b["shots"]):
            label = f"picture[{k}] shot {j}"
            if "until" in sh:
                end = _anchor(sh["until"], words, F, S, f"{label} until", c.get("clock"))
            elif "dur" in sh:
                end = cur + round(float(sh["dur"]) * F)
            elif j == len(b["shots"]) - 1:
                end = f1
            else:
                raise PictureError(f"{label}: give it dur or until (only the last shot of a block runs to the block's end)")
            if end <= cur:
                raise PictureError(f"{label} ends at {sec(end)} s, not after it starts ({sec(cur)} s)")
            if end > f1:
                raise PictureError(f"picture[{k}]: its shots run {(end - f1) / F:.2f} s past the block's end "
                                   f"({sec(f1)} s): shorten shot {j}")
            pieces.append((cur, end, block_shot(c, sh, end - cur, label)))
            cur = end
        if cur < f1:
            raise PictureError(f"picture[{k}]: its shots leave {(f1 - cur) / F:.2f} s of the block uncovered (to "
                               f"{sec(f1)} s): give the last shot no dur (it runs to the block's end) or a longer one")
    covered = sorted((f0, f1) for f0, f1, _, _ in blocks)
    audio_only = {n for n, sv in c["sources"].items() if kind_of(sv) == "audio"}
    for g in sorted(segments, key=lambda x: x["out_start"]):
        a = round(g["out_start"] * F)
        n = round(g["out_dur"] * F)
        for x, y in _uncovered(a, a + n, covered):
            sp = g.get("speed") or 1.0
            s0 = g["src_start"] + (x - a) / F * sp
            shot = copy_shot({**g, "src_start": round(s0, 3), "src_end": round(s0 + (y - x) / F * sp, 3),
                              "out_start": sec(x), "out_dur": sec(y - x)}, audio_only)
            sv = c["sources"].get(g["source"]) or {}
            if shot["kind"] == "video":
                shot["look"] = sv.get("look_id")
            pieces.append((x, y, {**shot, "_copy": True, "_s": s0}))
    pieces.sort(key=lambda p: p[0])
    shots = []
    for i, (x, y, sh) in enumerate(pieces):
        shots.append({**sh, "i": i, "out_start": sec(x), "out_dur": sec(y - x), "_f0": x, "_n": y - x})
    return shots, sec(V)


def _uncovered(a, b, covered):
    """[a, b) minus the covered frame intervals."""
    out, cur = [], a
    for x, y in covered:
        if y <= cur or x >= b:
            continue
        if x > cur:
            out.append((cur, x))
        cur = max(cur, y)
    if cur < b:
        out.append((cur, b))
    return out


def block_shot(c, sh, n, label):
    """One shot of a picture block (n frames) -> its picture-track record."""
    F = c["fps"]
    d = round(n / F, 3)
    base = {"_fit": sh.get("fit") or "cover", "_focus": tuple(sh.get("focus") or (0.5, 0.5)), "_what": sh.get("what"),
            "_why": sh.get("why")}
    if sh.get("fill"):
        return {"kind": "fill", "source": None, "src_start": 0.0, "src_end": d, "speed": 1.0, "move": "none",
                "look": None, **base}
    name = sh["source"]
    sv = c["sources"][name]
    move = sh.get("move") or "none"
    if kind_of(sv) == "photo":
        return {"kind": "photo", "source": name, "src_start": 0.0, "src_end": d, "speed": 1.0, "move": move,
                "look": sv.get("look_id"), **base}
    start, speed = float(sh.get("start", 0.0)), float(sh.get("speed", 1.0))
    src_dur = float((sv.get("info") or {}).get("dur") or 0.0)
    have = max(0.0, (src_dur - start) / speed)
    if have + 0.5 / F < n / F:
        raise PictureError(f"{label} ({name}, {Path(sv['path']).name}): needs {n / F:.2f} s from {start:.2f} s at "
                           f"speed {speed:g}, the file has {have:.2f} s usable (it is {src_dur:.2f} s long): a shorter "
                           f"shot, an earlier start or another clip (no freeze frame and no repeat is added)")
    return {"kind": "video", "source": name, "src_start": round(start, 3), "src_end": round(start + n / F * speed, 3),
            "speed": speed, "move": move, "look": sv.get("look_id"), **base}


def public(shots):
    """The shots as captions.json and edl.json keep them: the picture-track fields only (pic_track.SHOT_KEYS)."""
    from pic_track import SHOT_KEYS
    return [{k: g.get(k) for k in SHOT_KEYS} for g in shots]


def describe(shots, c):
    """--dry-run: the picture shots, one line each."""
    lines = [f"picture: {len(shots)} shots"]
    for g in shots:
        src = g["source"] or "background"
        what = g.get("_what") or ("the speaker's own video" if g.get("_copy") and g["kind"] == "video" else "")
        window = f"{g['src_start']:.3f}-{g['src_end']:.3f}" if g["kind"] == "video" else g["kind"]
        lines.append(f"  {g['i']:>2} {src:<10} {window:<15} x{g['speed']:<5} -> {g['out_start']:>7.3f} +{g['out_dur']:.3f} s"
                     f"  {g['move']:<5} {what or ''}")
    return "\n".join(lines)


def geometry(c):
    """The video's size: the sound sources' video as cut.py scales it (they were checked to agree), else 1080x1920."""
    for r in c["ranges"]:
        sv = c["sources"][r["source"]]
        if kind_of(sv) == "video":
            return (1080, 1920) if sv["scale"] else (sv["info"]["w"], sv["info"]["h"])
    return 1080, 1920


def build(c, e, segments, shots, total_video, level=True):
    """final.mp4: the sound from the sound segments (padded with silence to the picture's end), the picture from the
    shots, then the mux, as cut.py join() does it (video and audio apart, AAC alone, -c copy). -> the leveling report."""
    import cut_voice
    import footage
    from cut import lut_inputs, video_graph
    F = c["fps"]
    clips = e / "clips"
    clips.mkdir(exist_ok=True)
    parts = []
    frames = round(total_video * F)
    n = round(frames / F * cut_voice.RATE)
    sound = clips / "sound.wav"
    leveling = None
    if not segments:  # a no-speech reel: a silent track of the picture's length (the master adds music and sounds)
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"anullsrc=r={cut_voice.RATE}:cl=stereo", "-af",
             f"atrim=end_sample={n}", "-c:a", "pcm_s16le", sound])
    for g in segments:
        out = clips / f"voice_{g['i']:02d}.wav"
        sv = c["sources"][g["source"]]
        if sv["info"].get("has_audio"):
            cut_voice.encode_piece(c, g, out)
        else:
            warn(f"{g['source']}: the source has no audio; segment {g['i']} gets silence")
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-t", f"{g['_n'] / F:.15g}", "-i",
                 "anullsrc=r=48000:cl=stereo", "-c:a", "pcm_s16le", out])
        parts.append(out)
    if segments:
        joined, leveling = cut_voice.join_pieces(e, parts, segments, level)
        run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-af", f"apad=whole_len={n},atrim=end_sample={n}",
             "-c:a", "pcm_s16le", "-ar", str(cut_voice.RATE), "-ac", "2", sound])
    w, h = geometry(c)
    files = []
    for g in shots:
        out = clips / f"shot_{g['i']:02d}.mp4"
        nf = g["_n"]
        if g["kind"] == "fill":
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={BLACK}:size={w}x{h}:rate={F}",
                 "-frames:v", str(nf), "-vf", "setsar=1,format=yuv420p", "-c:v", "libx264", "-preset", "medium",
                 "-crf", "16", out])
        elif g.get("_copy"):  # the sound source's own video at the seconds of its sound: the rough cut's own chain
            sv = c["sources"][g["source"]]
            look = sv.get("look") or c
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{g['_s']:.15g}", "-t", f"{nf / F * g['speed'] + 0.2:.15g}",
                 "-i", sv["path"], *lut_inputs(look), "-filter_complex", video_graph(c, sv, g["speed"]), "-map", "[v]",
                 "-an", "-frames:v", str(nf), "-c:v", "libx264", "-preset", "medium", "-crf", "16", out])
        else:
            sv = c["sources"][g["source"]]
            try:
                footage.prepare(sv["path"], out, nf / F, g["src_start"] if g["kind"] == "video" else 0.0, g["_fit"],
                                g["_focus"], g["speed"], look=sv.get("look") or c, strict=True, size=(w, h), fps=F,
                                move=g["move"])
            except footage.ShortSource as x:
                sys.exit(f"cut.json picture shot {g['i']}: {x}")
        files.append(out)
    lst = clips / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in files), encoding="utf-8")
    vtmp, atmp = clips / "video_only.mp4", clips / "audio_only.m4a"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-map", "0:v", "-c", "copy", vtmp])
    run(["ffmpeg", "-v", "error", "-y", "-i", sound, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", atmp])
    run(["ffmpeg", "-v", "error", "-y", "-i", vtmp, "-i", atmp, "-map", "0:v", "-map", "1:a", "-c", "copy",
         "-movflags", "+faststart", e / "final.mp4"])
    return leveling, frames
