# -*- coding: utf-8 -*-
"""A long horizontal recording (a podcast, webinar or interview, 10-90 min) -> a series of vertical clips.

    python scripts/longform.py init edit/talk talk.mp4 [--preset weekly]   # the series folder edit/talk/
    python scripts/transcribe.py edit/talk talk.mp4                         # the whole recording, word by word
    python scripts/longform.py import edit/talk talk.en.vtt                 # or subtitles you have (no Whisper)
    python scripts/longform.py outline edit/talk [--chunk 600]              # the transcript in short lines, by parts
      ... the agent writes edit/talk/clips.json: one card per clip (references/longform.md) ...
    python scripts/longform.py check edit/talk [--clip 03]                  # find each card's pieces, check them
    python scripts/longform.py sheet edit/talk                              # edit/talk/series.md for the person
    python scripts/longform.py mark edit/talk 01 03 05 --as approved        # what the person said yes to
    python scripts/longform.py extract edit/talk 03 [--pad 3]               # edit/talk-03/: a normal video folder
    python scripts/longform.py status edit/talk                             # every card: where it stands, disk

Why this way (references/longform.md has the whole process):
  - choosing is cheap, finishing is not: on a real 36-minute interview the list of 15 clips took ~5 M cached tokens,
    each finished clip ~10 M and ~30 min, in a session that kept the whole series in its context. So the series gets
    one list and one "yes", and each clip is finished in a fresh context from its own folder;
  - no virality score: nothing shows it predicts views. A card says what the clip is about, its hook, its ending and
    why; this script checks what can be measured, the person decides the rest on the list;
  - the clips of the services that cut long videos are thrown away in 20-40 % of cases (vendor tests): a moment
    without its context, a cut before the payoff, a fixed number of clips. Here a card names its pieces by their
    first and last words (the transcript resolves the seconds), can join 2-4 pieces of the recording, and an
    excluded stretch (a topic the brand does not touch) is an error, not a warning;
  - each clip becomes an ordinary video folder edit/<series>-<id>/ with the pieces as their own files (a 90-minute
    file through speech_mask.py or faces.py costs minutes and gigabytes per clip), their WAVs and their transcripts
    cut out of the whole one, so the clip needs no new Whisper run, and the rest of the plugin works on it unchanged.

Files: edit/<series>/longform.json (the recording, the preset, the extracted clips), cues.json (imported subtitles),
transcripts/<stem>.json (transcribe.py), outline/part-NN.md, clips.json (the cards), series.md (the list).

clips.json (written by the agent; times as seconds or "mm:ss.s"):
    {"goal": "…", "length": [15, 60], "blockers": ["rights to the recording: …"],
     "rubrics": {"insight": {"label": "INSIGHT"}},
     "excluded": [{"start": "03:51", "end": "04:27", "why": "politics"}],
     "clips": [{"id": "01", "title": "…", "rubric": "insight", "wave": 1, "status": "proposed",
                "parts": [{"from_words": "first words of the piece", "to_words": "its last words", "near": "03:07"},
                          {"start": "19:58.7", "end": "20:11.0"}],
                "hook": "…", "why": "…", "ending": "…", "speaker": "guest", "host": "cut", "risks": ["…"],
                "allow": ["overlap:06"], "settings": {"label": "STORY"}}]}
A piece is named by its words (from_words, to_words, with near: where to look, ±20 s) or by seconds (start, end: a
timecode the person gave). check writes what it found into "resolved" and its findings into "check"; it never changes
what the agent wrote. A card the person approved goes back to "proposed" when its pieces move (a new transcript).
Errors (exit code 1): a piece not found, found twice (say more words or give near), end before start, outside the
recording, inside an excluded stretch. Warnings, with the words and seconds as evidence: the piece starts or ends
mid-sentence (only when the transcript has punctuation), its first words point back ("as I said", "that's why"),
the clip is outside the length, two cards share more than 3 s (allow "overlap:<id>"), two cards say much the same
(allow "dup:<id>"), the speaker changes inside a piece (the host's "wow": cut it or keep it, host: keep).
"""
import argparse, hashlib, json, math, os, re, subprocess, sys, time, unicodedata, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (NUMBER_RE, edit_dir, editing_json, is_project, load_json, locked, probe, project_root,
                          project_settings, rel, run, safe_slug, save_json, speaker_of, utf8_stdio, warn)

HERE = Path(__file__).resolve().parent
SCHEMA = 1
PAD = 3.0            # s of the recording kept around each piece: room for speech_mask.py to set the real edges
CHUNK = 600          # s per outline part: ~4-6 k tokens of text, read in one go
NEAR_WINDOW = 20.0   # s around "near" where a piece's words are looked for (timecodes from subtitles are ±1-2 s)
TO_SPAN = 240.0      # s after a piece's start where its last words are looked for
MATCH_MIN = 0.6      # share of a piece's words that must be found in order
TIE = 0.05           # two finds closer than this in score are a tie ...
TIE_NEAR = 5.0       # ... unless one is this much closer to "near"
OVERLAP_MAX = 3.0    # s two cards may share without a warning
DUP_MIN = 0.5        # word overlap of two cards' texts read as "much the same"
LENGTH = (15.0, 60.0)
BEAT_GAP = 2.0       # s of silence before a line: a possible seam between topics (outline mark)
SENTENCE_END = re.compile(r"[.!?…]['\")»”]*$")
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
STATUSES = ("proposed", "approved", "reserve", "rejected")
BACKREF_FIRST = set("he she they it this that these those also because which then so and but "
                    "\u043e\u043d \u043e\u043d\u0430 \u043e\u043d\u0438 \u043e\u043d\u043e \u044d\u0442\u043e \u044d\u0442\u043e\u0442 \u044d\u0442\u0430 \u044d\u0442\u0438 \u0442\u043e\u0442 \u0442\u0430 \u0442\u0435 \u0442\u0430\u043c \u0442\u043e\u0433\u0434\u0430 \u0442\u043e\u0436\u0435 \u0442\u0430\u043a\u0436\u0435 \u043f\u043e\u0442\u043e\u043c\u0443 \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u0438 \u0430 \u043d\u043e".split())
BACKREF_PHRASES = [tuple(p.split()) for p in (
    "as i said", "as i mentioned", "like i said", "as we discussed", "going back to", "that's why", "that is why",
    "this is why", "back to", "the other one", "\u043a\u0430\u043a \u044f \u0433\u043e\u0432\u043e\u0440\u0438\u043b", "\u043a\u0430\u043a \u044f \u0433\u043e\u0432\u043e\u0440\u0438\u043b\u0430", "\u043a\u0430\u043a \u044f \u0443\u0436\u0435 \u0433\u043e\u0432\u043e\u0440\u0438\u043b",
    "\u043a\u0430\u043a \u044f \u0443\u0436\u0435 \u0433\u043e\u0432\u043e\u0440\u0438\u043b\u0430", "\u043a\u0430\u043a \u044f \u0441\u043a\u0430\u0437\u0430\u043b", "\u043a\u0430\u043a \u044f \u0441\u043a\u0430\u0437\u0430\u043b\u0430", "\u043a\u0430\u043a \u043c\u044b \u0433\u043e\u0432\u043e\u0440\u0438\u043b\u0438", "\u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u044f\u0441\u044c \u043a", "\u0432\u043e\u0442 \u043f\u043e\u044d\u0442\u043e\u043c\u0443",
    "\u0438\u043c\u0435\u043d\u043d\u043e \u043f\u043e\u044d\u0442\u043e\u043c\u0443", "\u0442\u0430\u043a \u0432\u043e\u0442")]
TAG_RE = re.compile(r"\[(?:[^\]]{1,30})\]|\((?:applause|laughter|music|\u0430\u043f\u043b\u043e\u0434\u0438\u0441\u043c\u0435\u043d\u0442\u044b|\u0441\u043c\u0435\u0445|\u043c\u0443\u0437\u044b\u043a\u0430)\)|[♪♫]+", re.I)
MUSIC_RE = re.compile(r"music|\u043c\u0443\u0437\u044b\u043a|♪|♫", re.I)
SPEAKER_RE = re.compile(r"^\s*(?:>>\s*)?(?:\[|\()?([A-Z\u0410-\u042f\u0401][\w.'\- ]{0,28}?)(?:\]|\))?\s*:\s+(?=\S)")
VTT_TIME = re.compile(r"(\d+:)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d+:)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
INLINE_TAG = re.compile(r"<[^>]*>")


# --- small helpers ------------------------------------------------------------------------------------------------

def seconds(v, what="time"):
    """12.5, "12.5", "03:07", "03:07.5" or "1:03:07.5" -> seconds; None stays None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().replace(",", ".")
    try:
        if ":" not in s:
            return float(s)
        parts = [float(x) for x in s.split(":")]
    except ValueError:
        sys.exit(f"{what}: {v!r} is not seconds or mm:ss")
    out = 0.0
    for x in parts:
        out = out * 60 + x
    return out


def tc(t):
    """Seconds -> "mm:ss.s" ("h:mm:ss.s" past an hour)."""
    t = round(max(0.0, float(t)), 1)  # rounded first: 1079.99 s would show as "17:60.0"
    h, rest = divmod(t, 3600)
    m, s = divmod(rest, 60)
    return (f"{int(h)}:{int(m):02d}:{s:04.1f}" if h else f"{int(m):02d}:{s:04.1f}")


def norm_token(t):
    t = unicodedata.normalize("NFKC", t).lower().replace("\u0451", "\u0435")
    return t


def tokens_of(text):
    return [norm_token(t) for t in TOKEN_RE.findall(str(text))]


def same_token(a, b):
    if a == b:
        return True
    if len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]:  # a word in another form: the same first five letters
        return True
    return False


def ident(p):
    st = Path(p).stat()
    return {"path": str(Path(p).resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def fingerprint(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def series_dir(arg, create=False):
    e = edit_dir(arg, create=create)
    safe_slug(e.name, "series name")
    return e


def manifest(e):
    m = load_json(e / "longform.json")
    if not m:
        sys.exit(f"{e}: not a long recording's folder yet: longform.py init {e.name} <source>")
    return m


def source_path(e, m):
    f = Path(m["source"]["file"])
    p = f if f.is_absolute() else project_root() / f
    if not p.is_file():
        sys.exit(f"the recording {p} is not there any more (longform.json -> source.file)")
    return p.resolve()


# --- the transcript: word-level (transcribe.py) or cues (imported subtitles) ----------------------------------------

def transcript_file(e, m):
    return e / "transcripts" / f"{Path(m['source']['file']).stem}.json"


def stream(e, m):
    """The recording's text as tokens with times: from the word-level transcript when there is one, else from the
    imported cues (each cue's time shared evenly between its tokens: ±1-2 s). -> dict(kind, rev, words, tokens,
    punct, file)."""
    tf = transcript_file(e, m)
    words, kind, f = [], None, None
    doc = load_json(tf) if tf.is_file() else None
    if doc and doc.get("words"):
        from transcribe import join_hyphen_parts
        ws = [w for w in doc["words"] if w.get("type", "word") == "word" and str(w.get("text", "")).strip()]
        words = [{"text": str(w["text"]).strip(), "start": float(w["start"]), "end": float(w["end"]),
                  "speaker": speaker_of(w)} for w in join_hyphen_parts(ws)]
        kind, f = "words", tf
    else:
        cf = e / "cues.json"
        cues = (load_json(cf, {}) or {}).get("cues") or []
        for c in cues:
            parts = str(c["text"]).split()
            if not parts:
                continue
            d = (float(c["end"]) - float(c["start"])) / len(parts)
            for k, t in enumerate(parts):
                words.append({"text": t, "start": float(c["start"]) + k * d, "end": float(c["start"]) + (k + 1) * d,
                              "speaker": c.get("speaker")})
        if words:
            kind, f = "cues", cf
    if not words:
        sys.exit(f"no transcript of the recording yet: transcribe.py {e.name} <source> (word by word) or "
                 f"longform.py import {e.name} <subtitles.srt|.vtt>")
    toks = []
    for i, w in enumerate(words):
        for t in tokens_of(w["text"]):
            toks.append((t, i))
    ends = sum(1 for w in words if SENTENCE_END.search(w["text"]))
    st = f.stat()
    return {"kind": kind, "file": f, "rev": fingerprint([str(f.name), st.st_size, st.st_mtime_ns]),
            "words": words, "tokens": toks, "punct": ends >= max(1, len(words) // 80)}


# --- import: subtitles -> cues ----------------------------------------------------------------------------------

def _t(h, m, s, ms):
    return (int(h[:-1]) if h else 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_subtitles(text):
    """SRT or WebVTT -> [{start, end, lines}] (cue text with its markup still in the lines)."""
    out = []
    for block in re.split(r"\r?\n\s*\r?\n", text.replace("﻿", "")):
        lines = [l for l in block.splitlines()]
        for k, l in enumerate(lines):
            m = VTT_TIME.search(l)
            if m:
                g = m.groups()
                out.append({"start": _t(*g[:4]), "end": _t(*g[4:]), "lines": [x for x in lines[k + 1:]]})
                break
    return out


def clean_line(l):
    l = INLINE_TAG.sub("", l).replace("&nbsp;", " ").replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")
    return re.sub(r"\s+", " ", l).strip()


def cues_from(raw):
    """Subtitle cues -> clean cues: markup and sound tags out (kept as tags), "Name:" prefixes as the speaker, and the
    rolling captions of YouTube folded (each cue repeats the line before it, and 10 ms cues repeat it again)."""
    out, prev_last = [], None
    speaker = None
    for c in raw:
        lines = [clean_line(l) for l in c["lines"]]
        lines = [l for l in lines if l]
        if lines and prev_last is not None and lines[0] == prev_last:
            lines = lines[1:]
        if c["lines"]:
            last = [clean_line(l) for l in c["lines"] if clean_line(l)]
            prev_last = last[-1] if last else prev_last
        text, tags = [], []
        for l in lines:
            if l.startswith(">>"):
                speaker = None
            m = SPEAKER_RE.match(l)
            if m and not NUMBER_RE.fullmatch(m.group(1).strip()):
                speaker = m.group(1).strip()
                l = l[m.end():]
            l = l.lstrip(">").strip()
            for t in TAG_RE.findall(l):
                tags.append(t.strip("[]() ").lower() or "music")
            l = TAG_RE.sub(" ", l).strip()
            if l:
                text.append(l)
        t = re.sub(r"\s+", " ", " ".join(text)).strip()
        if not t:
            if out and tags:
                out[-1]["tags"] = sorted(set(out[-1].get("tags", []) + tags))
            if out and c["end"] > out[-1]["end"] and c["start"] - out[-1]["end"] < 0.5:
                out[-1]["end"] = round(c["end"], 3)
            if not out and tags:
                out.append({"start": round(c["start"], 3), "end": round(c["end"], 3), "text": "", "tags": tags})
            continue
        if out and out[-1]["text"] and t == out[-1]["text"]:
            out[-1]["end"] = round(max(out[-1]["end"], c["end"]), 3)
            continue
        cue = {"start": round(c["start"], 3), "end": round(max(c["end"], c["start"] + 0.05), 3), "text": t}
        if speaker:
            cue["speaker"] = speaker
        if tags:
            cue["tags"] = sorted(set(tags))
        out.append(cue)
    out = [c for c in out if c["text"] or c.get("tags")]
    for k, c in enumerate(out):
        c["i"] = k
        if k + 1 < len(out) and c["end"] > out[k + 1]["start"]:
            c["end"] = round(max(c["start"] + 0.05, out[k + 1]["start"]), 3)
    return out


def cues_from_json(doc):
    segs = doc.get("segments") if isinstance(doc, dict) else doc
    if not isinstance(segs, list):
        sys.exit("a JSON import is a list of {start, end, text[, speaker]} or {\"segments\": [...]} or a word-level "
                 "transcript {\"words\": [...]}")
    raw = []
    for s in segs:
        try:  # start/end/speaker, or the short names some diarizers write (s, e, spk; speaker_id)
            spk = next((s[k] for k in ("speaker", "spk", "speaker_id") if s.get(k) not in (None, "")), None)
            raw.append({"start": float(s["start"] if "start" in s else s["s"]),
                        "end": float(s["end"] if "end" in s else s["e"]), "text": str(s["text"]).strip(),
                        **({"speaker": str(spk)} if spk is not None else {})})
        except (KeyError, TypeError, ValueError, AttributeError):
            sys.exit(f"segment {json.dumps(s, ensure_ascii=False)[:120]}: needs start, end and text")
    out = []
    for k, s in enumerate(sorted(raw, key=lambda x: x["start"])):
        tags = [t.strip("[]() ").lower() for t in TAG_RE.findall(s["text"])]
        s["text"] = re.sub(r"\s+", " ", TAG_RE.sub(" ", s["text"])).strip()
        if tags:
            s["tags"] = sorted(set(tags))
        s["i"] = k
        out.append(s)
    return out


# --- commands -----------------------------------------------------------------------------------------------------

def cmd_init(a):
    project = project_root()
    if not is_project(project):
        sys.exit(f"no editing project here ({project}: no edit/, brands/ or it-reelsmaker.json)")
    src = Path(a.source)
    for cand in (src, project / src):
        if cand.is_file():
            src = cand.resolve()
            break
    else:
        sys.exit(f"no such file: {a.source}")
    e = series_dir(a.edit, create=True)
    pr = probe(src)
    if not pr.get("dur") or not pr.get("has_audio"):
        sys.exit(f"{src}: no duration or no sound track (ffprobe)")
    try:
        from reels_common import audio_offset
        off = audio_offset(src)
    except Exception:
        off = 0.0
    with editing_json(e / "longform.json", {}) as m:
        m.update({"schema": SCHEMA, "source": {"file": rel(src, project), "name": src.name, "identity": ident(src),
                                               "duration": round(pr["dur"], 3), "w": pr["w"], "h": pr["h"],
                                               "fps": pr["fps"], "audio_offset": off}})
        if a.preset:
            m["preset"] = a.preset
        m.setdefault("preset", None)
        m.setdefault("pad", PAD)
        m.setdefault("clips", {})
    horiz = pr["w"] and pr["h"] and pr["w"] > pr["h"]
    est = pr["dur"] * 2.5 / 1.6 / 60  # medium int8 on a laptop: ~2.5 min per 96 s
    print(f"{e / 'longform.json'}: {src.name}, {tc(pr['dur'])}, {pr['w']}x{pr['h']}, {pr['fps']} fps"
          + (" (horizontal: the clips use the framed format unless the preset says otherwise)" if horiz else ""))
    print("next, one of:\n"
          f"  transcribe.py {e.name} \"{rel(src, project)}\"   word by word, locally (~{est:.0f} min on a laptop; run it in "
          "the background, it is cached)\n"
          f"  longform.py import {e.name} <subtitles.srt|.vtt|.json>   subtitles you already have: no Whisper, ±1-2 s")


def cmd_import(a):
    e = series_dir(a.edit)
    m = manifest(e)
    f = Path(a.file)
    if not f.is_file():
        sys.exit(f"no such file: {f}")
    text = f.read_text(encoding="utf-8-sig", errors="replace")
    if f.suffix.lower() == ".json":
        doc = json.loads(text)
        if isinstance(doc, dict) and isinstance(doc.get("words"), list):
            from transcribe import check_doc
            errs = [x for x in check_doc(doc) if not x.startswith("note:")]
            if errs:
                sys.exit("not a valid word-level transcript:\n  " + "\n  ".join(errs[:10]))
            tf = transcript_file(e, m)
            if tf.exists() and not a.force:
                sys.exit(f"{tf} exists (a word-level transcript of the recording): --force replaces it")
            doc.setdefault("source", m["source"]["name"])
            doc.setdefault("timeline", "video")
            doc["model"] = doc.get("model") or f"imported from {f.name}"
            save_json(tf, doc)
            print(f"{tf}: {len(doc['words'])} words, word by word (it is used instead of any cues)")
            return
        cues = cues_from_json(doc)
    else:
        cues = cues_from(parse_subtitles(text))
    if not cues:
        sys.exit(f"{f}: no cues found (SRT, WebVTT or JSON segments)")
    dur = m["source"]["duration"]
    if cues[-1]["end"] > dur + 5:
        warn(f"the subtitles run to {tc(cues[-1]['end'])}, the recording is {tc(dur)}: another file or another cut?")
    save_json(e / "cues.json", {"from": f.name, "source": m["source"]["name"], "cues": cues})
    words = sum(len(c["text"].split()) for c in cues)
    music = sum(1 for c in cues if any(MUSIC_RE.search(t) for t in c.get("tags", [])))
    spk = sorted({c["speaker"] for c in cues if c.get("speaker")})
    print(f"{e / 'cues.json'}: {len(cues)} cues, {words} words, {tc(cues[0]['start'])}-{tc(cues[-1]['end'])}"
          + (f"; speakers: {', '.join(spk)}" if spk else "") + (f"; {music} cue(s) tagged music" if music else ""))
    if transcript_file(e, m).is_file():
        print(f"note: {transcript_file(e, m).name} (word by word) exists and is used first")


def outline_lines(e, m):
    """[(start, end, speaker, text, marks)] — phrases of the word-level transcript, or the cues."""
    s = stream(e, m)
    lines = []
    if s["kind"] == "words":
        from structure import join_punct, phrases
        for p in phrases(join_punct(s["words"])):
            lines.append([p["start"], p["end"], p.get("speaker"), p["text"], []])
    else:
        for c in (load_json(e / "cues.json", {}) or {}).get("cues") or []:
            marks = ["♪"] if any(MUSIC_RE.search(t) for t in c.get("tags", [])) else []
            lines.append([c["start"], c["end"], c.get("speaker"), c["text"], marks])
    for k, l in enumerate(lines):
        t = l[3].strip()
        if t.endswith("?"):
            l[4].append("?")
        elif k and lines[k - 1][3].strip().endswith("?"):
            l[4].append("→")
        if NUMBER_RE.search(t):
            l[4].append("#")
        if k and l[0] - lines[k - 1][1] >= BEAT_GAP:
            l[4].insert(0, "‖")
    return lines, s


def cmd_outline(a):
    e = series_dir(a.edit)
    m = manifest(e)
    lines, s = outline_lines(e, m)
    chunk = max(60.0, float(a.chunk))
    dur = m["source"]["duration"]
    n = max(1, int(-(-dur // chunk)))
    od = e / "outline"
    od.mkdir(exist_ok=True)
    for f in od.glob("part-*.md"):
        f.unlink()
    spk_time = {}
    for l in lines:
        if l[2]:
            spk_time[l[2]] = spk_time.get(l[2], 0) + (l[1] - l[0])
    index = []
    for k in range(n):
        t0, t1 = k * chunk, min(dur, (k + 1) * chunk)
        mine = [l for l in lines if t0 <= l[0] < t1]
        body = [f"# Part {k + 1} of {n}: {tc(t0)}–{tc(t1)} ({m['source']['name']}, {s['kind']})", ""]
        for l in mine:
            mark = " ".join(x for x in l[4] if x != "‖")
            body.append(("‖ " if "‖" in l[4] else "") + f"[{tc(l[0])}] " + (f"{l[2]}: " if l[2] else "") + l[3]
                        + (f"  {mark}" if mark else ""))
        text = "\n".join(body) + "\n"
        (od / f"part-{k + 1:02d}.md").write_text(text, encoding="utf-8")
        index.append((k + 1, t0, t1, len(mine), sum(len(l[3].split()) for l in mine), len(text)))
        if a.part == k + 1:
            print(text)
    if a.part:
        return
    print(f"{od}: {n} part(s) of {chunk / 60:g} min from the {'word-level transcript' if s['kind'] == 'words' else 'imported subtitles (±1-2 s)'}"
          + ("" if s["punct"] else "; no punctuation: sentence edges are not checked"))
    for k, t0, t1, nl, nw, nc in index:
        print(f"  part-{k:02d}.md  {tc(t0)}–{tc(t1)}  {nl} lines, {nw} words, ~{nc // 3500 + 1}k tokens")
    if spk_time:
        tot = sum(spk_time.values()) or 1
        print("speakers: " + ", ".join(f"{k} {v / tot:.0%}" for k, v in sorted(spk_time.items(), key=lambda x: -x[1])))
    print("marks: ‖ a pause of 2 s or more before the line (a possible seam) · ? a question · → its answer · # a number"
          " · ♪ music under the line. Read every part, note candidates per part, then choose across the parts.")


# --- check: resolve the cards' pieces --------------------------------------------------------------------------

def lcs_match(a, b):
    """Anchor tokens a against stream tokens b: -> (matched count, index in b of the first and last matched token,
    index in a of the first and last matched token)."""
    n, k = len(a), len(b)
    dp = [[0] * (k + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(k - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if same_token(a[i], b[j]) else max(dp[i + 1][j], dp[i][j + 1])
    i = j = 0
    first = last = a_first = a_last = None
    while i < n and j < k:
        if same_token(a[i], b[j]) and dp[i][j] == dp[i + 1][j + 1] + 1:
            if first is None:
                first, a_first = j, i
            last, a_last = j, i
            i, j = i + 1, j + 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return dp[0][0], first, last, a_first, a_last


EDGE_SLIP = 3  # unmatched first/last words of a phrase taken as misheard (≤ this many, no pause between)


def slip(words, toks, t, count, step):
    """Move a matched edge token t by up to `count` tokens (step -1: back, +1: on) over words the recognizer heard
    differently ("Vse, kovid" heard as "Soka net", a brand name in another script), stopping at a pause of 0.7 s.
    -> the word index of the new edge."""
    w = toks[t][1]
    for _ in range(min(count, EDGE_SLIP)):
        u = t + step
        if not 0 <= u < len(toks):
            break
        wu = toks[u][1]
        a, b = (words[wu], words[w]) if step < 0 else (words[w], words[wu])
        if wu != w and (b["start"] - a["end"] > 0.7 or SENTENCE_END.search(a["text"])):
            break  # a pause, or the end of the sentence before: that word is not the phrase's (the host's "great.")
        t, w = u, wu
    return w


def find_words(s, phrase, lo, hi, near=None, last=False):
    """Where in [lo, hi] s of the recording the phrase is said. -> (finds sorted best first, anchor length): each find
    {score, start, end, w0, w1} (w0/w1: indexes of the first and last matched word)."""
    a = tokens_of(phrase)
    if not a:
        return [], 0
    a = a[-12:] if last else a[:12]
    toks, words = s["tokens"], s["words"]
    span = len(a) + 3
    finds = []
    for i in range(len(toks)):
        w = words[toks[i][1]]
        if w["start"] < lo - 0.01 or w["start"] > hi:
            continue
        if not any(same_token(toks[i][0], x) for x in a[:3]):
            continue
        b = [t for t, _ in toks[i:i + span]]
        got, f0, f1, a0, a1 = lcs_match(a, b)
        score = got / len(a)
        if score < MATCH_MIN or f0 is None:
            continue
        w0, w1 = toks[i + f0][1], toks[i + f1][1]
        if not last and a0:  # the phrase's first words not found: they were likely misheard, take them in
            w0 = slip(words, toks, i + f0, a0, -1)
        if last and a1 < len(a) - 1:
            w1 = slip(words, toks, i + f1, len(a) - 1 - a1, +1)
        finds.append({"score": round(score, 3), "start": words[w0]["start"], "end": words[w1]["end"], "w0": w0, "w1": w1})
    best = {}
    for f in finds:  # one find per stretch: the best of the overlapping ones
        key = f["w1"] if last else f["w0"]
        if key not in best or f["score"] > best[key]["score"]:
            best[key] = f
    out = []
    for f in sorted(best.values(), key=lambda x: (-x["score"], abs(x["start"] - near) if near is not None else 0)):
        if not any(abs(f["start"] - g["start"]) < 1.0 for g in out):
            out.append(f)
    return out, len(a)


def pick(finds, near, what):
    """The find to use, or an error text when two are equally good (a phrase said twice: a retake, a refrain).
    near breaks the tie when one find is TIE_NEAR s closer to it than every other."""
    if not finds:
        return None, f"{what}: not found in the transcript"
    top = finds[0]
    tied = [top] + [f for f in finds[1:] if f["score"] >= top["score"] - TIE and abs(f["start"] - top["start"]) > 3]
    if len(tied) == 1:
        return top, None
    if near is not None:
        tied.sort(key=lambda f: abs(f["start"] - near))
        if abs(tied[1]["start"] - near) - abs(tied[0]["start"] - near) >= TIE_NEAR:
            return tied[0], None
    return None, (f"{what}: said more than once (" + ", ".join(tc(f["start"]) for f in sorted(tied, key=lambda f: f["start"])[:4])
                  + "): give more words or a closer near")


def snap_seconds(s, t0, t1):
    """A piece given in seconds -> the words inside it (word edges). -> (w0, w1) or (None, None)."""
    ws = s["words"]
    inside = [i for i, w in enumerate(ws) if w["end"] > t0 + 0.05 and w["start"] < t1 - 0.05]
    return (inside[0], inside[-1]) if inside else (None, None)


def resolve_part(s, p, dur, prev_end=None):
    """One piece -> (resolved dict or None, errors, notes)."""
    errs, notes = [], []
    near = seconds(p.get("near"), "near")
    near_end = seconds(p.get("near_end"), "near_end")
    if p.get("from_words"):
        lo, hi = (near - NEAR_WINDOW, near + NEAR_WINDOW) if near is not None else (0.0, dur)
        f, err = pick(find_words(s, p["from_words"], lo, hi, near)[0], near, f"«{p['from_words'][:40]}»")
        if err:
            return None, [err], notes
        w0, start = f["w0"], f["start"]
        if p.get("to_words"):
            if near_end is not None:
                lo2, hi2 = near_end - NEAR_WINDOW, near_end + NEAR_WINDOW
            else:
                lo2, hi2 = start, start + TO_SPAN
            finds = [g for g in find_words(s, p["to_words"], max(lo2, start), hi2, near_end, last=True)[0]
                     if g["w1"] >= w0]
            g, err = pick(finds, near_end, f"«{p['to_words'][-40:]}»")
            if err:
                return None, [err], notes
            w1 = g["w1"]
        else:
            return None, ["a piece named by words needs to_words too (its last words)"], notes
    elif p.get("start") is not None and p.get("end") is not None:
        t0, t1 = seconds(p["start"], "start"), seconds(p["end"], "end")
        if t1 <= t0:
            return None, [f"end {tc(t1)} is not after start {tc(t0)}"], notes
        if t0 < -0.5 or t1 > dur + 0.5:
            return None, [f"{tc(t0)}–{tc(t1)} is outside the recording (0–{tc(dur)})"], notes
        w0, w1 = snap_seconds(s, t0, t1)
        if w0 is None:
            return None, [f"no words between {tc(t0)} and {tc(t1)}"], notes
        moved = max(abs(s["words"][w0]["start"] - t0), abs(s["words"][w1]["end"] - t1))
        if moved > 1.0:
            notes.append(f"seconds {tc(t0)}–{tc(t1)} snapped to the words {tc(s['words'][w0]['start'])}–"
                         f"{tc(s['words'][w1]['end'])}")
    else:
        return None, ["a piece needs from_words + to_words (with near), or start + end"], notes
    ws = s["words"]
    r = {"start": round(ws[w0]["start"], 3), "end": round(ws[w1]["end"], 3), "w0": w0, "w1": w1,
         "first": " ".join(w["text"] for w in ws[w0:w0 + 6]), "last": " ".join(w["text"] for w in ws[max(w0, w1 - 5):w1 + 1])}
    if r["end"] <= r["start"]:
        errs.append(f"{tc(r['start'])}: the last words come before the first ones")
    return r, errs, notes


def quote(ws, i, j):
    return " ".join(w["text"] for w in ws[max(0, i):max(0, j)])


def check_card(s, card, others, excluded, length, dur):
    """-> (resolved parts or None, errors, warnings)."""
    errs, warns, res = [], [], []
    ws = s["words"]
    parts = card.get("parts") or []
    if not parts:
        return None, ["no parts"], warns
    for k, p in enumerate(parts):
        r, e1, notes = resolve_part(s, p, dur)
        lab = f"piece {chr(97 + k)}"
        errs += [f"{lab}: {x}" for x in e1]
        warns += [f"{lab}: {x}" for x in notes]
        if r is None:
            res.append(None)
            continue
        res.append(r)
        if r["end"] - r["start"] < 1.5:
            warns.append(f"{lab}: only {r['end'] - r['start']:.1f} s")
        for x in excluded:
            o = min(r["end"], x["end"]) - max(r["start"], x["start"])
            if o > 0.3:
                errs.append(f"{lab}: {o:.1f} s inside the excluded stretch {tc(x['start'])}–{tc(x['end'])}"
                            + (f" ({x['why']})" if x.get("why") else ""))
        if s["punct"]:
            w0, w1 = r["w0"], r["w1"]
            if w0 > 0 and not SENTENCE_END.search(ws[w0 - 1]["text"]) and ws[w0]["start"] - ws[w0 - 1]["end"] < 0.3:
                warns.append(f"{lab} starts mid-sentence at {tc(ws[w0]['start'])}: «…{quote(ws, w0 - 5, w0)} | "
                             f"{quote(ws, w0, w0 + 4)}»")
            if (w1 + 1 < len(ws) and not SENTENCE_END.search(ws[w1]["text"])
                    and ws[w1 + 1]["start"] - ws[w1]["end"] < 0.3):
                warns.append(f"{lab} ends mid-sentence at {tc(ws[w1]['end'])}: «{quote(ws, w1 - 3, w1 + 1)} | "
                             f"{quote(ws, w1 + 1, w1 + 5)}…»")
        spk = []
        for w in ws[r["w0"]:r["w1"] + 1]:
            if w.get("speaker") and (not spk or spk[-1][0] != w["speaker"]):
                spk.append((w["speaker"], w["start"]))
        if len(spk) > 1:
            warns.append(f"{lab}: the speaker changes inside it (" + ", ".join(f"{a} {tc(t)}" for a, t in spk[:5])
                         + ")" + ("" if card.get("host") == "keep" else ": cut the other voice or set host: keep"))
    if any(r is None for r in res):
        return None, errs, warns
    first = tokens_of(" ".join(w["text"] for w in ws[res[0]["w0"]:res[0]["w0"] + 6]))
    hit = next((" ".join(p) for p in BACKREF_PHRASES if any(tuple(first[i:i + len(p)]) == p for i in range(len(first)))), None)
    if not hit and first and first[0] in BACKREF_FIRST:
        hit = first[0]
    if hit:
        warns.append(f"the clip opens with «{hit}» («{res[0]['first']}»): does it make sense without what came before?")
    total = sum(r["end"] - r["start"] for r in res)
    lo, hi = length
    if not lo <= total <= hi:
        warns.append(f"{total:.0f} s of speech: outside {lo:g}–{hi:g} s (before the cut removes pauses)")
    allow = set(card.get("allow") or [])
    text = set(t for r in res for t in tokens_of(" ".join(w["text"] for w in ws[r["w0"]:r["w1"] + 1])) if len(t) >= 4)
    for o in others:
        if o["id"] == card["id"] or not o.get("_res"):
            continue
        shared = sum(max(0.0, min(r["end"], q["end"]) - max(r["start"], q["start"])) for r in res for q in o["_res"])
        if shared > OVERLAP_MAX and f"overlap:{o['id']}" not in allow:
            warns.append(f"shares {shared:.0f} s with card {o['id']} (allow \"overlap:{o['id']}\" if both are meant)")
        if text and o.get("_text"):
            j = len(text & o["_text"]) / max(1, len(text | o["_text"]))
            if j >= DUP_MIN and shared <= OVERLAP_MAX and f"dup:{o['id']}" not in allow:
                warns.append(f"says much the same as card {o['id']} ({j:.0%} of the words)")
    card["_text"] = text
    return res, errs, warns


def resolved_key(res):
    return fingerprint([[round(r["start"], 1), round(r["end"], 1)] for r in res]) if res else None


def load_cards(e):
    f = e / "clips.json"
    doc = load_json(f)
    if not doc or not isinstance(doc.get("clips"), list):
        sys.exit(f"no cards yet: {f} with {{\"clips\": [...]}} (references/longform.md)")
    ids = [str(c.get("id", "")) for c in doc["clips"]]
    for c in doc["clips"]:
        safe_slug(str(c.get("id", "")), "card id")
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        sys.exit(f"{f}: card ids repeat: {', '.join(dup)}")
    return f, doc


def cmd_check(a):
    e = series_dir(a.edit)
    m = manifest(e)
    s = stream(e, m)
    dur = m["source"]["duration"]
    f, _ = load_cards(e)
    n_err = 0
    with editing_json(f, {}) as doc:
        excluded = []
        for x in doc.get("excluded") or []:
            excluded.append({"start": seconds(x.get("start"), "excluded start"), "end": seconds(x.get("end"), "excluded end"),
                             "why": x.get("why")})
        length = tuple(float(v) for v in (doc.get("length") or LENGTH))
        cards = doc["clips"]
        for c in cards:  # first pass: every card's pieces, for the overlap and sameness checks
            res = []
            for p in c.get("parts") or []:
                r, _e, _n = resolve_part(s, p, dur)
                res.append(r)
            c["_res"] = res if res and all(res) else None
            if c["_res"]:
                c["_text"] = set(t for r in res for t in tokens_of(" ".join(w["text"] for w in s["words"][r["w0"]:r["w1"] + 1]))
                                 if len(t) >= 4)
        for c in cards:
            if a.clip and str(c["id"]) not in a.clip:
                continue
            res, errs, warns = check_card(s, c, cards, excluded, length, dur)
            for p, r in zip(c.get("parts") or [], res or [None] * len(c.get("parts") or [])):
                if r:
                    p["resolved"] = {"start": r["start"], "end": r["end"], "rev": s["rev"]}
                else:
                    p.pop("resolved", None)
            key = resolved_key(res)
            dropped = c.get("status") == "approved" and c.get("approved_rev") not in (None, key)
            if dropped:
                c["status"] = "proposed"
                warns.insert(0, "its pieces moved since the person approved it: approve it again")
            c["check"] = {"rev": s["rev"], "key": key, "errors": errs, "warnings": warns,
                          "length": round(sum(r["end"] - r["start"] for r in res), 1) if res else None}
            n_err += len(errs)
            head = f"{c['id']} {c.get('title', '')[:50]}"
            span = " + ".join(f"{tc(r['start'])}–{tc(r['end'])}" for r in res) if res else "—"
            print(f"{head}: {span}" + (f", {c['check']['length']:.0f} s" if res else "")
                  + (f"  [{c.get('status', 'proposed')}]"))
            for x in errs:
                print(f"   ERROR {x}")
            for x in warns:
                print(f"   warn  {x}")
        for c in cards:
            c.pop("_res", None)
            c.pop("_text", None)
    print(f"source of the times: {s['file'].name} ({'word by word' if s['kind'] == 'words' else 'subtitles, ±1-2 s'})"
          + ("" if s["punct"] else "; no punctuation: sentence edges not checked"))
    if n_err:
        print(f"{n_err} error(s): fix the cards (more words, a closer near, another piece) and run check again")
        return 1
    return 0


# --- sheet and mark -----------------------------------------------------------------------------------------------

def count(items, word):
    n = len(items or [])
    return f"{n} {word}" + ("" if n == 1 else "s")


def cmd_sheet(a):
    e = series_dir(a.edit)
    m = manifest(e)
    f, doc = load_cards(e)
    cards = doc["clips"]
    L = [f"# Series from {m['source']['name']} ({tc(m['source']['duration'])})", ""]
    if doc.get("goal"):
        L += [f"**Goal:** {doc['goal']}", ""]
    if doc.get("blockers"):
        L += ["**Before publishing:**"] + [f"- {b}" for b in doc["blockers"]] + [""]
    L += ["| # | Title | Rubric | Length | Wave | Status | Check |", "|---|---|---|---|---|---|---|"]
    for c in cards:
        ck = c.get("check") or {}
        mark = ("not checked" if not ck else count(ck.get("errors"), "error") if ck.get("errors")
                else count(ck.get("warnings"), "warning") if ck.get("warnings") else "ok")
        ln = f"~{ck['length']:.0f} s" if ck.get("length") else "—"
        L.append(f"| {c['id']} | {c.get('title', '')} | {c.get('rubric', '—')} | {ln} | {c.get('wave', '—')} | "
                 f"{c.get('status', 'proposed')} | {mark} |")
    L.append("")
    for c in cards:
        ck = c.get("check") or {}
        L += [f"## {c['id']} · {c.get('title', '')}", ""]
        for k, p in enumerate(c.get("parts") or []):
            r = p.get("resolved")
            when = f"{tc(r['start'])}–{tc(r['end'])}" if r else "not found"
            words = (f"«{p.get('from_words', '')}» … «{p.get('to_words', '')}»" if p.get("from_words")
                     else "by seconds")
            L.append(f"- piece {chr(97 + k)}: {when} — {words}")
        for key, label in (("hook", "Hook"), ("why", "Why"), ("ending", "Ending"), ("speaker", "Speaker"),
                           ("host", "The other voice")):
            if c.get(key):
                L.append(f"- {label}: {c[key]}")
        if c.get("risks"):
            L.append("- Risks: " + "; ".join(c["risks"]))
        for x in ck.get("errors") or []:
            L.append(f"- ⛔ {x}")
        for x in ck.get("warnings") or []:
            L.append(f"- ⚠ {x}")
        L.append("")
    if doc.get("excluded"):
        L += ["## Excluded", ""] + [f"- {tc(seconds(x.get('start')))}–{tc(seconds(x.get('end')))}: {x.get('why', '')}"
                                    for x in doc["excluded"]] + [""]
    out = e / "series.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"{out}: {len(cards)} card(s); show it to the person, then: longform.py mark {e.name} <ids> --as approved")


def cmd_mark(a):
    e = series_dir(a.edit)
    f, _ = load_cards(e)
    if a.status not in STATUSES:
        sys.exit(f"--as: {', '.join(STATUSES)}")
    done, refused = [], []
    with editing_json(f, {}) as doc:
        by = {str(c["id"]): c for c in doc["clips"]}
        for i in a.ids:
            c = by.get(str(i))
            if c is None:
                refused.append(f"{i}: no such card")
                continue
            if a.status == "approved":
                ck = c.get("check") or {}
                if not ck or ck.get("errors") or not ck.get("key"):
                    refused.append(f"{i}: " + ("not checked yet (longform.py check)" if not ck else "has errors"))
                    continue
                c["approved_rev"] = ck["key"]
            c["status"] = a.status
            done.append(str(i))
    if done:
        print(f"{f}: {', '.join(done)} → {a.status}")
    for x in refused:
        print("  not marked: " + x)
    return 1 if refused else 0


# --- extract ------------------------------------------------------------------------------------------------------

def cut_piece(src, t0, dur, out):
    """[t0, t0 + dur) of the recording -> its own file, re-encoded (frame-exact), into a temp name, then replaced."""
    tmp = out.with_name(f".{out.stem}.{os.getpid()}.{uuid.uuid4().hex[:6]}{out.suffix}")
    try:
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
             "-map", "0:v:0", "-map", "0:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(tmp)])
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            tmp.unlink()


def slice_doc(parent, t0, t1, lang, ident_, off, frag_name):
    """The parent transcript's words inside [t0, t1), on the piece's own timeline (t - t0)."""
    words = []
    for w in parent.get("words") or []:
        if w.get("type", "word") != "word":
            continue
        s0, s1 = float(w["start"]), float(w["end"])
        if s0 >= t0 - 0.005 and s1 <= t1 + 0.005:
            words.append({**w, "start": round(max(0.0, s0 - t0), 3), "end": round(min(t1 - t0, s1 - t0), 3)})
    return {"language_code": lang, "text": " ".join(str(w["text"]).strip() for w in words), "words": words,
            "source": frag_name, "source_identity": ident_, "model": f"{parent.get('model') or 'transcript'} (slice)",
            "timeline": "video", "audio_offset": off,
            "slice_of": {"source": parent.get("source"), "start": round(t0, 3), "end": round(t1, 3)}}


def reelcfg(*args):
    r = subprocess.run([sys.executable, str(HERE / "reelcfg.py"), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"reelcfg.py {' '.join(map(str, args))} failed:\n{(r.stderr or r.stdout)[-800:]}")
    return r.stdout.strip()


def cmd_extract(a):
    project = project_root()
    e = series_dir(a.edit)
    m = manifest(e)
    src = source_path(e, m)
    if ident(src) != m["source"]["identity"]:
        warn(f"{src.name} changed since longform.py init (size or time): the transcript's times may not fit it")
    f, doc = load_cards(e)
    card = next((c for c in doc["clips"] if str(c["id"]) == str(a.id)), None)
    if card is None:
        sys.exit(f"no card {a.id} in {f}")
    s = stream(e, m)
    ck = card.get("check") or {}
    if not a.force:
        if ck.get("rev") != s["rev"] or not ck.get("key"):
            sys.exit(f"card {a.id} was not checked against the current transcript: longform.py check {e.name}")
        if ck.get("errors"):
            sys.exit(f"card {a.id} has errors (longform.py check): fix them first")
        if card.get("status") != "approved":
            sys.exit(f"card {a.id} is {card.get('status', 'proposed')}: the person approves the list first "
                     f"(longform.py mark {e.name} {a.id} --as approved), or --force")
    parts = [p.get("resolved") for p in card.get("parts") or []]
    if not parts or not all(parts):
        sys.exit(f"card {a.id}: its pieces are not resolved (longform.py check)")
    cid = f"{e.name}-{safe_slug(str(card['id']), 'card id')}"
    ce = project / "edit" / cid
    (ce / "src").mkdir(parents=True, exist_ok=True)
    (ce / "transcripts").mkdir(exist_ok=True)
    pad = float(a.pad if a.pad is not None else m.get("pad", PAD))
    fps = float(m["source"].get("fps") or 30)
    dur_src = float(m["source"]["duration"])
    tf = transcript_file(e, m)
    parent = load_json(tf) if s["kind"] == "words" else None
    lang = (parent or {}).get("language_code") or a.language
    inputs = fingerprint([m["source"]["identity"], [[p["start"], p["end"]] for p in parts], pad, s["rev"]])
    rec = (m.get("clips") or {}).get(str(card["id"])) or {}
    pieces = []
    from transcribe import check_doc, source_wav
    for k, p in enumerate(parts):
        key = chr(97 + k)
        t0 = max(0.0, math.floor((p["start"] - pad) * fps) / fps)
        t1 = min(dur_src, p["end"] + pad)
        frag = ce / "src" / f"{cid}{key}.mp4"  # the folder's name: short and safe, whatever the recording is called
        old = next((x for x in rec.get("pieces") or [] if x.get("key") == key), None)
        fresh = (rec.get("inputs") == inputs and old and frag.is_file() and old.get("identity") == ident(frag))
        if not fresh:
            print(f"piece {key}: {tc(t0)}–{tc(t1)} of {src.name} -> {rel(frag, project)} ...", flush=True)
            cut_piece(src, t0, t1 - t0, frag)
        pr = probe(frag)
        with locked(ce / f"audio16k-{frag.stem}.wav", stale=86400):
            wav, fid, off = source_wav(ce, frag)
        out = ce / "transcripts" / f"{frag.stem}.json"
        how = "slice"
        if parent is not None:
            d = slice_doc(parent, t0, t0 + (pr.get("dur") or (t1 - t0)), lang, fid, off, frag.name)
            errs = [x for x in check_doc(d) if not x.startswith("note:")]  # a long word is a note, not a fault
            if errs:
                sys.exit(f"the slice of piece {key} is not a valid transcript: {errs[0]}")
            save_json(out, d)
        else:
            how = "whisper"
            cur = load_json(out) if out.is_file() else None
            if not cur or cur.get("source_identity") != fid:
                print(f"piece {key}: no word-level transcript of the recording, transcribing the piece (medium) ...",
                      flush=True)
                cmd = [sys.executable, str(HERE / "transcribe.py"), str(ce), str(frag), "--model", a.model]
                if lang:
                    cmd += ["--language", lang]
                r = subprocess.run(cmd)
                if r.returncode != 0:
                    sys.exit(f"transcribe.py failed on piece {key}")
        local = local_edges(load_json(out) or {}, card["parts"][k], p, t0)
        pieces.append({"key": key, "file": rel(frag, project), "transcript": rel(out, project), "offset": round(t0, 3),
                       "end": round(t1, 3), "start_in": local[0], "end_in": local[1], "identity": ident(frag),
                       "words": how, "wav": rel(wav, project)})
    wrote = write_cut(ce, project, card, pieces)
    new_reel = not (ce / "reel.json").is_file()
    if new_reel:
        applied = []
        if m.get("preset"):
            print(reelcfg("preset", "use", m["preset"], str(ce)))
            applied.append(f"preset {m['preset']}")
        sets = {}
        rub = (doc.get("rubrics") or {}).get(card.get("rubric") or "") or {}
        for k2 in ("label", "profile", "content_format"):
            if rub.get(k2):
                sets[k2] = rub[k2]
        sets.update(card.get("settings") or {})
        now = load_json(ce / "reel.json", {}) or {}
        w, h = m["source"].get("w") or 0, m["source"].get("h") or 0
        if w > h and "format" not in sets and "format" not in now:
            sets["format"] = "framed"
        if sets:
            print(reelcfg("save", str(ce), "--set", *[f"{k2}={v if not isinstance(v, (list, dict)) else json.dumps(v)}"
                                                     for k2, v in sets.items()]))
    pm = ce / "project.md"
    if not pm.exists():
        lines = [f"# {card.get('title') or cid}", "",
                 f"Clip {card['id']} of the series {e.name}: from the long recording {m['source']['name']}, "
                 + ", ".join(f"piece {x['key']} {tc(x['offset'])}–{tc(x['end'])} ({x['file']})" for x in pieces) + ".",
                 "Times in cut.json are seconds of each piece's own file; the recording's second = piece offset + "
                 "the piece's second.", "", "## Card", ""]
        for key, label in (("hook", "Hook"), ("why", "Why"), ("ending", "Ending"), ("speaker", "Speaker"),
                           ("host", "Host lines")):
            if card.get(key):
                lines.append(f"- {label}: {card[key]}")
        if card.get("risks"):
            lines.append("- Risks: " + "; ".join(card["risks"]))
        lines += ["", "## Decisions", "", "## Open items", ""]
        pm.write_text("\n".join(lines), encoding="utf-8")
    with editing_json(e / "longform.json", {}) as mm:
        mm.setdefault("clips", {})[str(card["id"])] = {"folder": rel(ce, project), "inputs": inputs, "pad": pad,
                                                       "pieces": pieces, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    print(f"{rel(ce, project)}: {len(pieces)} piece(s), words by {'slice of the whole transcript' if parent is not None else 'Whisper on each piece'}"
          + ("; cut.json written (rough edges from the words)" if wrote == "new" else
             "; cut.json kept as it was" + ("" if wrote == "same" else " — its sources differ from the new pieces, check them"))
          + ("; reel.json from the series" if new_reel else ""))
    print(f"next: speech_mask.py on each piece for the real edges -> cut.json ranges, then the usual steps from 5 "
          f"(cut plan, cut.py, faces, export, check.py, kit.py render) in {rel(ce, project)}")


def local_edges(doc, part, res, t0):
    """The piece's first and last words on its own timeline: the anchors found again in its own transcript (a Whisper
    run on the piece hears the edges better than subtitles did), else the resolved seconds minus the offset."""
    ws = [w for w in doc.get("words") or [] if w.get("type", "word") == "word" and str(w.get("text", "")).strip()]
    guess = (round(res["start"] - t0, 3), round(res["end"] - t0, 3))
    if not ws or not part.get("from_words"):
        return guess
    s = {"words": [{"text": str(w["text"]).strip(), "start": float(w["start"]), "end": float(w["end"]),
                    "speaker": speaker_of(w)} for w in ws]}
    s["tokens"] = [(t, i) for i, w in enumerate(s["words"]) for t in tokens_of(w["text"])]
    a, _ = find_words(s, part["from_words"], guess[0] - 4, guess[0] + 4, guess[0])
    b, _ = find_words(s, part.get("to_words") or "", guess[1] - 4, guess[1] + 4, guess[1], last=True)
    st = a[0]["start"] if a else guess[0]
    en = b[0]["end"] if b else guess[1]
    return (round(st, 3), round(en, 3)) if en > st else guess


def write_cut(ce, project, card, pieces):
    """cut.json for the clip: a source per piece and a range per piece from its words (rough: speech_mask.py sets the
    real edges). An existing cut.json is never overwritten. -> "new" | "same" | "differs"."""
    f = ce / "cut.json"
    sources = {x["key"]: {"file": x["file"], "transcript": x["transcript"]} for x in pieces}
    if f.is_file():
        cur = load_json(f, {}) or {}
        same = {k: v.get("file") for k, v in (cur.get("sources") or {}).items()} == {k: v["file"] for k, v in sources.items()}
        return "same" if same else "differs"
    ranges = [{"source": x["key"], "start": max(0.0, round(x["start_in"] - 0.05, 3)), "end": round(x["end_in"] + 0.08, 3),
               "beat": f"piece {x['key']}"} for x in pieces]
    save_json(f, {"fps": 30, "sources": sources, "ranges": ranges})
    return "new"


# --- status -------------------------------------------------------------------------------------------------------

def newer(a, b):
    try:
        return Path(a).stat().st_mtime >= Path(b).stat().st_mtime - 1
    except OSError:
        return False


def stage(ce):
    """The stages of a clip folder by its files: (label, state) with state ok / stale / —."""
    out = []
    cut, final = ce / "cut.json", ce / "final.mp4"
    props, board, render, cover = ce / "reelkit-props.json", ce / "board" / "board.md", ce / "render.json", ce / "cover.jpg"
    out.append(("cut", "—" if not final.is_file() else "ok" if newer(final, cut) else "stale"))
    out.append(("export", "—" if not props.is_file() else "ok" if newer(props, final) else "stale"))
    out.append(("board", "—" if not board.is_file() else "ok" if newer(board, props) else "stale"))
    rj = load_json(render, {}) or {}
    out.append(("render", "—" if not rj else "FAILED" if not rj.get("ok") else "ok" if newer(render, props) else "stale"))
    out.append(("cover", "ok" if cover.is_file() else "—"))
    return out


def cmd_status(a):
    from reels_common import dir_size, remotion_leftovers, tmp_root
    project = project_root()
    e = series_dir(a.edit)
    m = manifest(e)
    cf = e / "clips.json"
    doc = load_json(cf, {}) or {}
    cards = doc.get("clips") or []
    s = None
    try:
        s = stream(e, m)
    except SystemExit:
        pass
    print(f"{m['source']['name']} ({tc(m['source']['duration'])}); transcript: "
          + ("none yet" if not s else f"{s['file'].name} ({'word by word' if s['kind'] == 'words' else 'subtitles'})")
          + f"; preset: {m.get('preset') or '—'}")
    used = []
    total_mb = 0.0
    for c in cards:
        ck = c.get("check") or {}
        chk = ("not checked" if not ck else "STALE (transcript changed)" if s and ck.get("rev") != s["rev"]
               else f"{len(ck.get('errors') or [])} errors" if ck.get("errors") else "ok")
        rec = (m.get("clips") or {}).get(str(c["id"]))
        line = f"  {c['id']:<4} {str(c.get('title', ''))[:34]:<34} {c.get('status', 'proposed'):<9} check {chk}"
        if rec:
            ce = project / rec["folder"]
            parts = [p.get("resolved") for p in c.get("parts") or []]
            cur = (fingerprint([m["source"]["identity"], [[p["start"], p["end"]] for p in parts], rec_pad(m, rec), s["rev"]])
                   if s and parts and all(parts) else None)
            ex = "ok" if cur == rec.get("inputs") else "STALE (card or transcript changed: extract again)"
            line += f"; extracted {ex}; " + ", ".join(f"{k} {v}" for k, v in stage(ce))
            for p in rec.get("pieces") or []:
                used.append((p["offset"], p["end"]))
            if ce.is_dir():
                total_mb += dir_size(ce) / (1 << 20)
        print(line)
    if used:
        used.sort()
        merged = [list(used[0])]
        for a0, a1 in used[1:]:
            if a0 <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], a1)
            else:
                merged.append([a0, a1])
        sec = sum(b - a_ for a_, b in merged)
        print(f"recording used by extracted clips: {sec / 60:.1f} min of {m['source']['duration'] / 60:.1f} "
              f"({len(merged)} stretch(es)); clip folders {total_mb:.0f} MB")
    rem = project_settings(project).get("remotion_dir")
    if rem and not str(rem).startswith("${"):
        pub = (Path(rem) if Path(rem).is_absolute() else project / rem) / "public"
        if pub.is_dir():
            mine = [pub / Path(r["folder"]).name for r in (m.get("clips") or {}).values() if (pub / Path(r["folder"]).name).is_dir()]
            mb = sum(dir_size(p) for p in mine) / (1 << 20)
            print(f"Remotion public/: {len(mine)} clip folder(s) of this series, {mb:.0f} MB (renders through kit.py "
                  f"copy only their own clip's files)")
    left = remotion_leftovers(measure=False)
    own = dir_size(tmp_root()) / (1 << 20) if tmp_root().is_dir() else 0
    print(f"temp: {len(left)} Remotion leftover folder(s) older than a day" + (" (kit.py clean-temp)" if left else "")
          + (f"; this plugin's run folders {own:.0f} MB" if own >= 1 else ""))


def rec_pad(m, rec):
    """The pad an extracted clip was cut with (its record keeps it)."""
    return float(rec.get("pad", m.get("pad", PAD)))


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("edit"); p.add_argument("source"); p.add_argument("--preset")
    p = sub.add_parser("import"); p.add_argument("edit"); p.add_argument("file"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("outline"); p.add_argument("edit"); p.add_argument("--part", type=int)
    p.add_argument("--chunk", type=float, default=CHUNK, help="seconds per part (default 600)")
    p = sub.add_parser("check"); p.add_argument("edit"); p.add_argument("--clip", nargs="+")
    p = sub.add_parser("sheet"); p.add_argument("edit")
    p = sub.add_parser("mark"); p.add_argument("edit"); p.add_argument("ids", nargs="+")
    p.add_argument("--as", dest="status", required=True, choices=STATUSES)
    p = sub.add_parser("extract"); p.add_argument("edit"); p.add_argument("id")
    p.add_argument("--pad", type=float, help=f"seconds kept around each piece (default {PAD:g})")
    p.add_argument("--model", default="medium", help="Whisper model for pieces when the recording has no word-level transcript")
    p.add_argument("--language", help="the speech language for Whisper on the pieces")
    p.add_argument("--force", action="store_true", help="extract a card that is not approved or not checked")
    p = sub.add_parser("status"); p.add_argument("edit")
    a = ap.parse_args()
    fn = {"init": cmd_init, "import": cmd_import, "outline": cmd_outline, "check": cmd_check, "sheet": cmd_sheet,
          "mark": cmd_mark, "extract": cmd_extract, "status": cmd_status}[a.cmd]
    sys.exit(fn(a) or 0)


if __name__ == "__main__":
    main()
