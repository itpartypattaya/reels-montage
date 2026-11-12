# -*- coding: utf-8 -*-
"""cut.py's branch for a sound-only source: a narration recorded on a phone (m4a, wav, mp3, ogg, opus), no picture.
Part of cut.py, with no command line of its own: `python scripts/cut.py edit/<id>` takes this branch by itself when
every source in cut.json has sound and no video stream.

The same cut.json as for a video (ranges, takes, pauses, speed, fix/fix_at/retime/keep, level) and the same captions:
the words land on the edit timeline exactly as for a rough cut. What differs:
  - the result is edit/<id>/voice.wav (48 kHz stereo, 16-bit), the narration on the edit timeline, instead of
    final.mp4; there is no look, no white balance and no extract (there is no picture);
  - each piece is cut from the source with its 30 ms fades into WAV and the pieces are joined without a lossy step;
    speech leveling runs on the joined narration as for a video (level.py);
  - captions.json -> "voice": {"file", "sha1", "rate", "frames", "fps", "stamp"}; the stamp is the sources' and
    transcripts' hashes + cut.json's hash + fps + --speed + leveling. A run with the same stamp and an unchanged
    voice.wav prints "cached" and rebuilds nothing (--force rebuilds);
  - edl.json as for a video, so speech_mask.py --edl checks the edges on the sources.
captions.json -> segments and edl.json -> ranges are the SOUND pieces, as for a video. The picture of such a video is
the designed scenes (visual_plan.py init --scenes-voice): it has no segments of its own.
Warnings: a recording whose quietest moments are only BED_GAP_DB under its speech has a steady background under the
voice (music, a loud room): it stays under every word of the video; record the narration clean, music goes in at
mastering (master_audio.py --music).
"""
import hashlib, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from level import describe as describe_level, level_audio
from reels_common import load_json, run, save_json, warn

RATE = 48000
FADE = 0.03         # s: the fade at every cut, as cut.py's
MIN_VOICE = 1.0     # s: a sound-only source shorter than this is no narration (cut.py load_cut says so)
BED_GAP_DB = 18.0   # dB: speech (90th percentile of 50 ms windows) this close to the quiet ones (10th): a steady bed
SILENT_DB = -120.0  # dB: a window of digital silence (astats gives -inf)


def sha1_file(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def stamp_of(c, e, speed_arg, level):
    """What the voice is made from: a change in any of it rebuilds voice.wav and captions.json."""
    tr = {n: (sha1_file(sv["transcript"]) if Path(sv["transcript"]).is_file() else None)
          for n, sv in sorted(c["sources"].items())}
    return {"sources": {n: sha1_file(sv["path"]) for n, sv in sorted(c["sources"].items())}, "transcripts": tr,
            "cut": sha1_file(e / "cut.json"), "fps": c["fps"], "speed": speed_arg, "level": bool(level)}


def is_cached(e, stamp):
    v = (load_json(e / "captions.json") or {}).get("voice") or {}
    f = e / "voice.wav"
    return (v.get("stamp") == stamp and f.is_file() and (e / "edl.json").is_file() and v.get("sha1") == sha1_file(f))


def levels_db(path):
    """RMS of 50 ms windows over the whole file, dB (digital silence: SILENT_DB)."""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-ac", "1", "-af",
             "aresample=48000,asetnsamples=2400,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
             "-f", "null", "-"], check=False)
    out = []
    for x in re.findall(r"RMS_level=(-?[\d.]+|-inf)", r.stderr):
        out.append(SILENT_DB if x == "-inf" else max(SILENT_DB, float(x)))
    return out


def background_warnings(c):
    """A narration over music (or a loud steady room): its quietest windows are only BED_GAP_DB under its speech."""
    for name, sv in c["sources"].items():
        v = sorted(levels_db(sv["path"]))
        if len(v) < 20:
            continue
        lo, hi = v[int(len(v) * 0.10)], v[int(len(v) * 0.90)]
        if hi > -50 and hi - lo < BED_GAP_DB:
            warn(f"{name}: {Path(sv['path']).name} has a steady background under the voice (music or a loud room: its "
                 f"quietest moments are only {hi - lo:.0f} dB under the speech). It stays under every word of the video: "
                 f"record the narration in a quiet place without music; music goes in at mastering (master_audio.py --music)")


def encode_piece(c, g, out):
    """One range of the source -> WAV on the edit timeline: speed (atempo, pitch kept), padded/trimmed to the planned
    frames, 30 ms fades at both ends (otherwise clicks), 48 kHz stereo."""
    sv = c["sources"][g["source"]]
    s, t, n, speed = g["_s"], g["_e"], g["_n"], sv["speed"]
    d = n / c["fps"]
    fade = min(FADE, d / 4)
    af = ("aformat=sample_rates=48000:channel_layouts=stereo," + (f"atempo={speed}," if speed != 1.0 else "")
          + f"apad,atrim=0:{d:.15g},afade=t=in:st=0:d={fade:.15g},afade=t=out:st={d - fade:.15g}:d={fade:.15g}")
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.15g}", "-t", f"{t - s + 0.2:.15g}", "-i", sv["path"], "-vn",
         "-af", af, "-c:a", "pcm_s16le", "-ar", str(RATE), "-ac", "2", out])


def join_pieces(e, parts, segments, level):
    """The pieces joined in order (each padded/trimmed to its frames), leveled (level.py) -> the narration WAV and the
    leveling report (None without leveling)."""
    clips = e / "clips"
    ains = sum((["-i", p] for p in parts), [])
    afc = "".join(f"[{k}:a]apad,atrim=0:{g['_n'] / g['_fps']:.15g},asetpts=PTS-STARTPTS[a{k}];" for k, g in enumerate(segments))
    afc += "".join(f"[a{k}]" for k in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]"
    joined = clips / "voice_joined.wav"
    run(["ffmpeg", "-v", "error", "-y", *ains, "-filter_complex", afc, "-map", "[a]", "-c:a", "pcm_s16le",
         "-ar", str(RATE), "-ac", "2", joined])
    if not level:
        return joined, None
    segs, t = [], 0.0
    for g in segments:
        d = g["_n"] / g["_fps"]
        segs.append((g["source"], t, d))
        t += d
    leveled = clips / "voice_level.wav"
    try:
        return leveled, level_audio(joined, leveled, segs)
    except RuntimeError as x:
        warn(f"speech leveling skipped: {x}")
        return joined, None


def check_voice(f, frames, fps):
    """voice.wav: 48 kHz, starts at 0, exactly the planned frames long (one sample per 1/RATE, +-1 frame)."""
    import json
    r = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,sample_rate,start_time,duration",
             "-of", "json", f], check=False)
    try:
        st = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
        start, dur, rate = float(st.get("start_time") or 0), float(st["duration"]), int(st["sample_rate"])
    except (KeyError, ValueError, TypeError, IndexError):
        return ["voice.wav is not readable"]
    out = []
    if rate != RATE:
        out.append(f"voice.wav is {rate} Hz, not {RATE}")
    if abs(start) > 0.001:
        out.append(f"voice.wav starts at {start} s, not 0")
    if abs(dur - frames / fps) > 1 / fps:
        out.append(f"voice.wav is {dur:.3f} s, the plan {frames / fps:.3f} s")
    return out


def build(c, e, segments, captions, total, extra, speed_arg=None, level=True, force=False):
    """The sound-only cut: voice.wav + captions.json + edl.json in edit/<id>, or "cached"."""
    stamp = stamp_of(c, e, speed_arg, level)
    if not force and is_cached(e, stamp):
        print(f"cached: {(e / 'voice.wav').name} and captions.json match the recording, its transcript and cut.json "
              f"(--force rebuilds them)")
        return
    clips = e / "clips"
    clips.mkdir(exist_ok=True)
    parts = []
    for g in segments:
        out = clips / f"voice_{g['i']:02d}.wav"
        encode_piece(c, g, out)
        parts.append(out)
    audio, leveling = join_pieces(e, parts, segments, level)
    if leveling:
        print(describe_level(leveling))
    frames = sum(g["_n"] for g in segments)
    n = round(frames / c["fps"] * RATE)
    voice = e / "voice.wav"
    tmp = e / f".voice.{os.getpid()}.wav"
    try:
        run(["ffmpeg", "-v", "error", "-y", "-i", audio, "-af", f"apad=whole_len={n},atrim=end_sample={n}",
             "-c:a", "pcm_s16le", "-ar", str(RATE), "-ac", "2", tmp])
        os.replace(tmp, voice)
    finally:
        if tmp.exists():
            tmp.unlink()
    for g in segments:
        for k in ("_s", "_e", "_n", "_fps"):
            g.pop(k)
    speeds = {name: sv["speed"] for name, sv in c["sources"].items()}
    # edl.json and captions.json in the format cut.py writes for a video (speech_mask.py --edl, visual_plan.py)
    save_json(e / "edl.json", {"version": 1, "sources": {name: str(sv["path"]) for name, sv in c["sources"].items()},
                               "speed": c["speed"], "speeds": speeds, "grade": "none",
                               "ranges": [{"source": g["source"], "start": g["src_start"], "end": g["src_end"],
                                           "speed": g["speed"], "beat": g["beat"]} for g in segments],
                               "total_duration_s": round(total, 3)})
    save_json(e / "captions.json", {"duration": round(total, 3), "segments": segments, "words": captions, **extra,
                                    **({"leveling": leveling} if leveling else {}),
                                    "voice": {"file": voice.name, "sha1": sha1_file(voice), "rate": RATE,
                                              "frames": frames, "fps": c["fps"], "stamp": stamp}})
    problems = check_voice(voice, frames, c["fps"])
    if problems:
        print("voice.wav check FAILED: " + "; ".join(problems))
        sys.exit(1)
    print(f"voice.wav ready: {round(total, 3)} s, the narration on the edit timeline; captions.json, edl.json written. "
          f"Next: python scripts/speech_mask.py --edl {(e / 'edl.json').as_posix()}, then visual_plan.py init "
          f"edit/{e.name} --scenes-voice")
