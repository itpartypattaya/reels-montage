# -*- coding: utf-8 -*-
"""Rough cut from a cut list: segments, speed-up, color, subtitles on the new timeline.

Everything that differs between videos lives in edit/<id>/cut.json, so no new code is written per video:

    python scripts/cut.py edit/4821 --dry-run        # check the cut list: segments, lengths, total, words per segment
    python scripts/cut.py edit/4821 [--speed 1.15]   # build final.mp4 + captions.json + edl.json

cut.json (paths are relative to the project root, or to edit/<id>, or absolute):
    {
     "fps": 30,
     "speed": 1.15,
     "sources": {"main": {"file": "IMG_4821.MOV", "transcript": "edit/4821/transcripts/IMG_4821.json"}},
     "look": {"correct": "colorbalance=rs=-0.02", "lut": "brand", "lut_mix": 0.6, "grade": "eq=contrast=1.05"},
     "scale": "auto",
     "ranges": [{"source": "main", "start": 1.567, "end": 12.967, "beat": "hook"},
                {"start": 14.767, "end": 20.767, "beat": "the answer"}],
     "fix": {"recruter": "recruiter"},
     "fix_at": [{"text": "all", "at": 16.16, "to": "everything"}],
     "retime": [{"text": "Hi", "at": 0.0, "start": 0.68, "end": 0.84}],
     "extract": {"broll_pool": {"source": "main", "start": 25.75, "end": 27.05}}
    }

sources     one or more source files; each may set its own "speed" (two angles recorded at different paces).
            "transcript": word timings ({"words": [{"text", "start", "end", "type"}]}); by default
            edit/<id>/transcripts/<file stem>.json. Without a transcript the cut is built without subtitles.
ranges      segments in source seconds, in the order of the video; edges from speech_mask.py. "source" may be
            left out when there is only one source. Edges are snapped to the frame grid.
look        color in two steps. "correct": an ffmpeg filter chain that fixes this source (white balance, green
            cast, exposure), applied BEFORE the LUT; "lut": "brand" (the HALD LUT of the video's brand,
            brand.json -> lut.hald) or a HALD image file; "lut_mix" its strength 0..1 (start at 0.5-0.7 and compare
            face stills before and after); "grade": a filter chain applied AFTER the LUT (contrast, sharpness).
            Without "look" the color stays as shot.
scale       "auto": a vertical source that is not 1080x1920 is scaled (and cropped if its aspect is not 9:16) to
            1080x1920 with lanczos; a horizontal source keeps its size (the framed format places it in Remotion);
            "none": never scale.
fix, fix_at transcription fixes: every occurrence of a word, or one occurrence near a source second (±0.02 s).
retime      exact timings of key words measured on the waveform: (word, transcript start) -> (start, end).
extract     extra clips from the sources for Remotion (cutaways from the same footage), same color, no sound:
            edit/<id>/<name>.mp4.

How it is built (checked on real renders):
  - each segment is encoded on its own: -ss/-t, setpts for the speed-up, fps, color, atempo (pitch kept),
    30 ms audio fades at every cut (otherwise clicks);
  - video and audio are joined SEPARATELY: the video with the concat demuxer and -c copy (it starts at exactly 0),
    the audio with the concat filter, each segment padded and trimmed to its video length, one AAC encode, then
    mux with -c copy +faststart. A combined concat of segments with AAC audio shifts the video start by ~21 ms
    (AAC priming), and Remotion then fails with "No frame found at position";
  - at the end: video and audio start at 0 and have the same duration, otherwise exit code 1.
Output in edit/<id>/: final.mp4, captions.json (segments src_start/src_end/out_start/out_dur + words on the new
timeline), edl.json (sources and ranges for speech_mask.py --edl), clips/ (intermediate segments).
"""
import argparse, json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import brand_file, edit_dir, inside, load_config, load_json, probe, project_root, run, safe_slug, save_json, utf8_stdio, warn

FADE = 0.03
MIN_WORD = 0.08  # s: the shortest word on the subtitle timeline
LUT_MIX = 0.6


def resolve(p, project, e):
    """A path from cut.json: absolute, or relative to the project root, or to the video folder."""
    p = Path(str(p))
    if p.is_absolute():
        return p
    for base in (project, e):
        if (base / p).exists():
            return base / p
    return project / p


def load_cut(e, project, speed_arg=None):
    """cut.json, checked and with every default filled in. Errors stop the script with a clear message."""
    f = e / "cut.json"
    cut = load_json(f)
    if not isinstance(cut, dict):
        sys.exit(f"no cut list: {f} (see python scripts/cut.py --help for its format)")
    try:
        fps = float(cut.get("fps", 30))
    except (ValueError, TypeError):
        sys.exit("cut.json: fps must be a finite positive number")
    if not math.isfinite(fps) or fps <= 0:
        sys.exit("cut.json: fps must be a finite positive number")
    fps = int(fps) if fps.is_integer() else fps
    speed = float(speed_arg or cut.get("speed") or 1.0)
    srcs = cut.get("sources") or {}
    if not srcs:
        sys.exit("cut.json: no sources")
    sources = {}
    for name, sv in srcs.items():
        sv = {"file": sv} if isinstance(sv, str) else dict(sv)
        if not sv.get("file"):
            sys.exit(f"cut.json: source {name!r} has no file")
        path = resolve(sv["file"], project, e)
        if not path.is_file():
            sys.exit(f"cut.json: source {name!r}: no file {path}")
        sp = float(speed_arg or sv.get("speed") or speed)
        if not 0.5 <= sp <= 2.0:
            sys.exit(f"cut.json: source {name!r}: speed {sp} is outside 0.5..2.0")
        tr = sv.get("transcript")
        tr = resolve(tr, project, e) if tr else e / "transcripts" / f"{path.stem}.json"
        sources[name] = {"path": path, "speed": sp, "transcript": tr, "info": probe(path)}
    ranges = []
    for k, r in enumerate(cut.get("ranges") or []):
        src = r.get("source") or (next(iter(sources)) if len(sources) == 1 else None)
        if src not in sources:
            sys.exit(f"cut.json: range {k}: source {r.get('source')!r} is not in sources")
        s, t = validate_range(r, sources[src], fps, f"range {k}")
        ranges.append({"source": src, "start": s, "end": t, "beat": r.get("beat", "")})
    if not ranges:
        sys.exit("cut.json: no ranges")
    look = cut.get("look") or {}
    grade = (look.get("grade") or "").strip().strip(",")
    correct = (look.get("correct") or "").strip().strip(",")
    for name, chain in (("grade", grade), ("correct", correct)):
        if any(c in chain for c in ";[]"):
            sys.exit(f"cut.json: look.{name} must be a plain filter chain (no ';' or '[...]' labels)")
    lut = look.get("lut")
    if lut == "brand":
        _, _, _, bdir, brand = load_config(e)
        hald = ((brand or {}).get("lut") or {}).get("hald")
        lut = brand_file(hald, bdir, project) if hald else None
        if not lut:
            warn("look.lut = brand, but the video's brand has no HALD LUT (brand.json -> lut.hald): no LUT")
    elif lut:
        lut = resolve(lut, project, e)
        if not lut.is_file():
            warn(f"look.lut: no file {lut}: no LUT")
            lut = None
    scale = cut.get("scale", "auto")
    if scale not in ("auto", "none"):
        sys.exit("cut.json: scale must be \"auto\" or \"none\"")
    for name, sv in sources.items():
        sv["scale"] = scale_filter(sv["info"], scale, name)
    geometry = set()
    for r in ranges:
        sv = sources[r["source"]]
        info = sv["info"]
        w, h = (1080, 1920) if sv["scale"] else (info.get("w"), info.get("h"))
        if not w or not h:
            sys.exit("cut.json: cannot determine output geometry")
        geometry.add((w, h, "1:1"))  # video_graph normalizes SAR after scaling
    if len(geometry) != 1:
        sys.exit("cut.json: mismatched output geometry/SAR across segments")
    extras = cut.get("extract") or {}
    for name, x in extras.items():
        extract_path(e, name)
        src = x.get("source") or (next(iter(sources)) if len(sources) == 1 else None)
        if src not in sources:
            sys.exit(f"cut.json: extract {name}: unknown source")
        validate_range(x, sources[src], fps, f"extract {name}")
    return {"fps": fps, "speed": speed, "sources": sources, "ranges": ranges, "grade": grade, "correct": correct,
            "lut": str(lut) if lut else None, "lut_mix": float(look.get("lut_mix", LUT_MIX)),
            "fix": cut.get("fix") or {}, "fix_at": cut.get("fix_at") or [], "retime": cut.get("retime") or [],
            "extract": extras}


def extract_path(e, name):
    return inside(e, e / f"{safe_slug(name, 'extract name')}.mp4", "extract output")


def validate_range(r, source, fps, label):
    try:
        s, t, dur = float(r["start"]), float(r["end"]), float(source["info"]["dur"])
    except (KeyError, TypeError, ValueError):
        sys.exit(f"cut.json: {label}: finite start/end and source duration required")
    if not all(math.isfinite(v) for v in (s, t, dur)) or s < 0 or t <= s or t > dur + 1 / fps:
        sys.exit(f"cut.json: {label}: invalid range or outside source duration")
    n = round((round(t * fps) - round(s * fps)) / source["speed"])
    if n < 1:
        sys.exit(f"cut.json: {label}: range must contain at least one output frame")
    return s, t


def scale_filter(info, mode, name):
    w, h = info.get("w"), info.get("h")
    if mode == "none" or not w or not h or (w, h) == (1080, 1920):
        return ""
    if w > h:
        warn(f"{name}: horizontal source {w}x{h} kept at its size (the framed format places it in Remotion)")
        return ""
    if abs(w / h - 9 / 16) < 0.01:
        return "scale=1080:1920:flags=lanczos"
    return "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920"


def video_graph(c, src, speed, out_label="v"):
    """filter_complex for the video: speed, fps, scale, source correction, LUT (input 1), grade, yuv420p."""
    chain = []
    if speed != 1.0:
        chain.append(f"setpts=(PTS-STARTPTS)/{speed}")
    chain.append(f"fps={c['fps']}")
    if src["scale"]:
        chain.append(src["scale"])
    if c.get("correct"):
        chain.append(c["correct"])
    head = "[0:v]" + ",".join(chain)
    tail = (f",{c['grade']}" if c["grade"] else "") + f",setsar=1,format=yuv420p[{out_label}]"
    if not c["lut"]:
        return head + tail
    mix = max(0.0, min(1.0, c["lut_mix"]))
    if mix >= 0.999:
        return head + "[p];[p][1:v]haldclut" + tail
    return head + f",split[a][b];[b][1:v]haldclut[l];[a][l]blend=all_mode=normal:all_opacity={mix:.2f}" + tail


def lut_inputs(c):
    return ["-loop", "1", "-i", c["lut"]] if c["lut"] else []


def load_words(c):
    """Words of every source's transcript with the retime fixes applied: {source: [word, ...]}."""
    out = {}
    for name, sv in c["sources"].items():
        doc = load_json(sv["transcript"])
        if not doc:
            warn(f"{name}: no transcript {sv['transcript']}: the cut is built without subtitles for this source")
            out[name] = []
            continue
        words = [dict(w) for w in doc.get("words", []) if w.get("type", "word") == "word" and str(w.get("text", "")).strip()]
        for w in words:
            for r in c["retime"]:
                if w["text"] == r["text"] and abs(w["start"] - float(r["at"])) < 0.02:
                    w["start"], w["end"] = float(r["start"]), float(r["end"])
            if w["end"] - w["start"] < MIN_WORD:  # Whisper gives some short words zero length; they would vanish
                w["end"] = w["start"] + MIN_WORD
        out[name] = words
    return out


def fixed(w, c):
    for r in c["fix_at"]:
        if w["text"] == r["text"] and abs(w["start"] - float(r["at"])) < 0.02:
            return r["to"]
    return c["fix"].get(w["text"], w["text"])


def timeline(c, words):
    """Assign words per occurrence; resolve boundaries only between adjacent source spans."""
    fps, segments, captions, offset = c["fps"], [], [], 0.0
    frames = 0
    for i, r in enumerate(c["ranges"]):
        sv = c["sources"][r["source"]]
        speed = sv["speed"]
        first, last = round(r["start"] * fps), round(r["end"] * fps)
        s, e = first / fps, last / fps
        n = round((last - first) / speed)
        d = n / fps
        segments.append({"i": i, "source": r["source"], "src_start": round(s, 3), "src_end": round(e, 3),
                         "out_start": round(offset, 3), "out_dur": round(d, 3), "speed": speed, "beat": r["beat"],
                         "_s": s, "_e": e, "_n": n, "_fps": fps})
        same = [(i, r)]
        for k in (i - 1, i + 1):
            if not 0 <= k < len(c["ranges"]):
                continue
            x = c["ranges"][k]
            # A restart in the source is a new occurrence, even when it overlaps the old one. The next span forward in
            # the source is the same occurrence, touching or not: a word the transcript stretches across the gap
            # between them goes to the span that holds more of it, not to both.
            earlier, later = (x, r) if k < i else (r, x)
            if x["source"] == r["source"] and later["start"] > earlier["start"] and later["end"] > earlier["end"]:
                same.append((k, x))
        for w in words[r["source"]]:
            ov = [(min(w["end"], x["end"]) - max(w["start"], x["start"]), k) for k, x in same]
            best = max(o for o, _ in ov)
            k_best = min(k for o, k in ov if o == best)
            mid = (w["start"] + w["end"]) / 2
            if not ((best > 0 and k_best == i) or (best <= 0 and s - 0.05 <= mid <= e + 0.05)):
                continue
            ws, we = min(max(w["start"], s), e), min(max(w["end"], s), e)
            if we - ws <= 0:
                continue
            captions.append({"text": fixed(w, c), "src": round(w["start"], 3), "start": round((ws - s) / speed + offset, 3),
                             "end": round((we - s) / speed + offset, 3), "seg": i})
        frames += n
        offset = frames / fps
    return segments, captions, offset


def encode_segment(c, g, out):
    sv = c["sources"][g["source"]]
    s, e, n, speed = g["_s"], g["_e"], g["_n"], sv["speed"]
    d = n / c["fps"]
    inputs = ["-ss", f"{s:.15g}", "-t", f"{e - s + 0.2:.15g}", "-i", sv["path"], *lut_inputs(c)]
    if sv["info"].get("has_audio"):
        a_in = "[0:a]aformat=sample_rates=48000:channel_layouts=stereo," + (f"atempo={speed}," if speed != 1.0 else "")
    else:
        k = 2 if c["lut"] else 1
        inputs += ["-f", "lavfi", "-t", f"{d + 0.1:.4f}", "-i", "anullsrc=r=48000:cl=stereo"]
        a_in = f"[{k}:a]"
        warn(f"{g['source']}: the source has no audio; segment {g['i']} gets silence")
    fade = min(FADE, d / 4)
    audio = a_in + f"apad,atrim=0:{d:.15g},afade=t=in:st=0:d={fade:.15g},afade=t=out:st={d - fade:.15g}:d={fade:.15g}[a]"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", video_graph(c, sv, speed) + ";" + audio,
         "-map", "[v]", "-map", "[a]", "-frames:v", str(n), "-t", f"{d:.15g}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out])


def join(e, parts, segments):
    """Video and audio joined separately (see the module docstring), then muxed into final.mp4."""
    clips = e / "clips"
    lst = clips / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    vtmp, atmp = clips / "video_only.mp4", clips / "audio_only.m4a"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-map", "0:v", "-c", "copy", vtmp])
    ains = sum((["-i", p] for p in parts), [])
    afc = "".join(f"[{k}:a]apad,atrim=0:{g['_n'] / g['_fps']:.15g},asetpts=PTS-STARTPTS[a{k}];" for k, g in enumerate(segments))
    afc += "".join(f"[a{k}]" for k in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]"
    run(["ffmpeg", "-v", "error", "-y", *ains, "-filter_complex", afc, "-map", "[a]", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", atmp])
    run(["ffmpeg", "-v", "error", "-y", "-i", vtmp, "-i", atmp, "-map", "0:v", "-map", "1:a", "-c", "copy",
         "-movflags", "+faststart", e / "final.mp4"])


def check_final(f, fps, expected_frames=None):
    """Check finite stream timing and the planned frame count and duration."""
    r = run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
             "stream=codec_type,start_time,duration,nb_read_frames", "-of", "json", f], check=False)
    try:
        streams = {s["codec_type"]: s for s in json.loads(r.stdout or "{}").get("streams", [])}
    except ValueError:
        streams = {}
    v, a = streams.get("video") or {}, streams.get("audio") or {}
    problems = []
    for name, s in (("video", v), ("audio", a)):
        if not s:
            problems.append(f"no {name} stream")
        else:
            try:
                start, duration = float(s["start_time"]), float(s["duration"])
                if not math.isfinite(start) or not math.isfinite(duration) or duration <= 0:
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                problems.append(f"{name} has invalid timing")
                continue
            if abs(start) > 0.001:
                problems.append(f"{name} starts at {start} s, not 0")
            if expected_frames is not None and abs(duration - expected_frames / fps) > 1 / fps:
                problems.append(f"{name} duration differs from plan")
    if not problems and v and a and abs(float(v["duration"]) - float(a["duration"])) > 1.0 / fps:
        problems.append(f"video {v.get('duration')} s and audio {a.get('duration')} s differ")
    if expected_frames is not None and v and str(v.get("nb_read_frames")) != str(expected_frames):
        problems.append(f"video frames {v.get('nb_read_frames')} differ from plan {expected_frames}")
    return problems


def extract(c, e):
    for name, x in c["extract"].items():
        src = x.get("source") or (next(iter(c["sources"])) if len(c["sources"]) == 1 else None)
        if src not in c["sources"]:
            warn(f"extract {name}: source {x.get('source')!r} is not in sources: skipped")
            continue
        sv = c["sources"][src]
        s, t = float(x["start"]), float(x["end"])
        out = extract_path(e, name)
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.4f}", "-t", f"{t - s:.4f}", "-i", sv["path"], *lut_inputs(c),
             "-filter_complex", video_graph(c, sv, 1.0), "-map", "[v]", "-an", "-frames:v", str(round((t - s) * c["fps"])),
             "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-movflags", "+faststart", out])
        print(f"extract: {out.name} ({t - s:.2f} s from {src})")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", help="the video folder, edit/<id>")
    ap.add_argument("--speed", type=float, help="speed-up for every source (overrides cut.json)")
    ap.add_argument("--dry-run", action="store_true", help="only print the segments, lengths and words; encode nothing")
    a = ap.parse_args()
    project = project_root()
    e = edit_dir(a.edit, project)
    c = load_cut(e, project, a.speed)
    words = load_words(c)
    segments, captions, total = timeline(c, words)
    for g in segments:
        nw = sum(1 for w in captions if w["seg"] == g["i"])
        print(f"  {g['i']:>2} {g['source']:<8} {g['src_start']:>8.3f}-{g['src_end']:<8.3f} x{g['speed']:<5} "
              f"-> {g['out_start']:>7.3f} +{g['out_dur']:.3f} s  {nw:>3} words  {g['beat']}")
    nall = sum(len(v) for v in words.values())
    print(f"segments {len(segments)}, words {len(captions)} of {nall}, total {total} s")
    if a.dry_run:
        return
    clips = e / "clips"
    clips.mkdir(exist_ok=True)
    parts = []
    for g in segments:
        out = clips / f"seg_{g['i']:02d}.mp4"
        encode_segment(c, g, out)
        parts.append(out)
    join(e, parts, segments)
    extract(c, e)
    expected_frames = sum(g["_n"] for g in segments)
    for g in segments:
        for k in ("_s", "_e", "_n", "_fps"):
            g.pop(k)
    speeds = {n: sv["speed"] for n, sv in c["sources"].items()}
    look = ", ".join(filter(None, [c["correct"], f"haldclut {Path(c['lut']).name} {round(c['lut_mix'] * 100)}%" if c["lut"] else "",
                                   c["grade"]]))
    save_json(e / "edl.json", {"version": 1, "sources": {n: str(sv["path"]) for n, sv in c["sources"].items()},
                               "speed": c["speed"], "speeds": speeds, "grade": look or "none",
                               "ranges": [{"source": g["source"], "start": g["src_start"], "end": g["src_end"],
                                           "speed": g["speed"], "beat": g["beat"]} for g in segments],
                               "total_duration_s": round(total, 3)})
    save_json(e / "captions.json", {"duration": round(total, 3), "segments": segments, "words": captions})
    problems = check_final(e / "final.mp4", c["fps"], expected_frames)
    if problems:
        print("final.mp4 check FAILED: " + "; ".join(problems))
        sys.exit(1)
    print(f"final.mp4 ready: {total} s; captions.json, edl.json written. Next: python scripts/speech_mask.py --edl "
          f"{(e / 'edl.json').as_posix()}")


if __name__ == "__main__":
    main()
