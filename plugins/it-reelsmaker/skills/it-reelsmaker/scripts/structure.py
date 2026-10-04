# -*- coding: utf-8 -*-
"""Structure of a video before the cut plan: which lines could open it, how it could end, whether the start is slow,
and whether this source was edited before. A draft for the agent, not a decision: the script sees signs in the
transcript and the audio (a question, an answer, a repeat for emphasis, a number, a beat after a line, clean silence at
the edges); what is funny, controversial or strong is the agent's call (references/structure.md).

    python scripts/structure.py suggest edit/<id> [--source KEY | --transcript F] [--from S --to S] [--audio W] [--json]
    python scripts/structure.py history edit/<id> | <source file>

suggest reads the word-level transcript of ONE source (cut.json -> sources -> transcript, else
edit/<id>/transcripts/<stem>.json) on the source timeline. Several sources in cut.json (two cameras), or several
transcripts and no cut.json: name one with --source KEY (the cut.json key) or --transcript F; the script lists the
choices instead of guessing (T2: it silently took the newest transcript, the other angle, 87.8 s long, and analyzed
--from 59 --to 108 on it). Two cameras: run it per source, or on the main angle. It splits the transcript into
phrases (sentence end, pause > 0.5 s, speaker change, at most 40 words) and prints:
  • the phrases with their signs and whether each can be cut out cleanly: >= 0.1 s of silence at both edges by the
    audio level (speech_mask.py), not by the transcript, which drifts by 0.1-0.8 s. Where two phrases' transcript
    times touch (faster-whisper glues a pause into a word: the word ends where the next starts), the edge between
    them is the speech mask's silence nearest to that boundary, split at its middle (T5: 7 of 9 phrases had "no
    clean edge" though the mask had >= 0.4 s of silence between almost all of them); that silence needs the same
    >= 0.1 s of raw silence as any edge (T7: a 0.24 s pause, a 0.18 s gap in the widened mask, was "no clean edge"
    while speech_mask.py cut it cleanly and the --edl check gave no warning);
  • teaser candidates: a short list by signs (3-12 words, 0.8-4.5 s of speech, no word with an estimated time or a
    retake sign, not trailing off; clean edges, a whole sentence and a beat after it rank higher) of lines from later in
    the video that could open it (a cold open), with the exact "ranges" entry for cut.json (or "no clean edge": only
    together with a neighbor) and the risk when the line is the payoff of the ending.
    The script cannot judge meaning: the agent picks the line by meaning, from the list or from any clean phrase;
  • the slow start: speech before the first question or strong line, looked for in the first third of the speech
    only (T5: it pointed at the video's last line, 37.8 s in); a number in the opening seconds (a price, a result)
    is a strong opening already;
  • the ending: the last line, a payoff after a question, the beat after it;
  • earlier edits of the same source (history): a folder whose cut.json names the source, whose transcripts/ has
    its transcript, or whose project.md names the file itself (stem + a video extension, "sunrise.mp4", or a camera
    name like IMG_1234 alone); a bare word in the notes is not the source (T5: a brand with the same name as the file
    counted another video's notes).
--from/--to (source seconds) analyze one fragment of a long recording: the teasers, the slow start and the ending are
looked for inside it, while the neighbors outside still bound the clean edges.
It writes edit/<id>/structure.json. Nothing is cut: the variants go into the cut plan (SKILL.md, step 3a) and the
person chooses.
"""
import argparse, json, re, sys, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import NUMBER_RE, VIDEO_EXT, edit_dir, load_json, project_root, save_json, speaker_of, utf8_stdio, warn
from cut import punct_only
from transcribe import join_hyphen_parts

SENTENCE_END = re.compile(r"[.!?…]['\")»”]*$")
# a phrase here is a unit of meaning, not a subtitle line: a 16-word cap split a 22-word question into two halves,
# and neither half could be cut out cleanly
MAX_WORDS, PAUSE = 40, 0.5
BEAT = 0.6          # a pause after a line this long leaves room for a reaction: a payoff sign
CLEAN = 0.10        # silence needed at a cut edge (SKILL.md step 3: a phrase is cut out of speech only with >= 0.1 s)
FPS = 30
TEASER_MIN, TEASER_MAX = 0.8, 4.5   # seconds: shorter is not a line, longer is not a hook
SLOW_START = 3.0    # seconds of speech before the first question or strong line
HYPHENS = "-‐‑"
DRIFT = 0.8         # recognizers place word edges 0.1-0.8 s off: the search window for a phrase's real edge
INNER = 0.15        # an edge past the 2nd word's start (or before the penultimate word's end) by more is inside the phrase
# a word this long is a retake merged into one word (SKILL.md step 3). transcribe.py check_doc notes words over 1.0 s:
# that note is for a person to listen to; here a word of 1.0-1.5 s is usually a word stretched over the pause before
# the next phrase (faster-whisper), which the "retake?" sign would put off a clean teaser
LONG_WORD = 1.5
TEASER_WORDS = (3, 12)  # an interjection ("OK, let's go") is not a line; a longer one is not a hook
GLUED = 0.1         # transcript times of two phrases closer than this touch: the pause between them is in a word
MASK_WIDEN = 4      # 10 ms windows: the speech mask is widened by ~30 ms each side, so raw silence reaches past its gap
EARLY = 1 / 3       # the slow start looks for its strong line in this share of the speech, never near the end
UNFINISHED = re.compile(r"(\.\.\.|…)['\")»”]*$")  # a cut-off word or a line that trails off
NORM = re.compile(r"[^\w]+", re.U)


def norm(t):
    return NORM.sub("", str(t).lower())


def join_punct(words):
    """Punctuation tokens joined to their word, as cut.py lays them into the subtitles: an opening quote or bracket
    to the next word, anything else to the previous one. A lone dash counted as a word and, of no length, as a
    retake sign: "Sales — that is life." lost its place among the teasers."""
    out, prefix = [], ""
    for w in words:
        t = str(w["text"]).strip()
        if punct_only(t):
            if unicodedata.category(t[0]) in ("Ps", "Pi"):
                prefix += t
            elif out:
                out[-1] = dict(out[-1], text=str(out[-1]["text"]).rstrip()
                               + (" " if unicodedata.category(t[0]) == "Pd" else "") + t)
            continue
        out.append(dict(w, text=prefix + t) if prefix else w)
        prefix = ""
    return out


def phrases(words, breaks=()):
    """Words on the source timeline -> [{i, start, end, text, words, speaker, inner, est, suspect, unfinished}]. inner:
    (the 2nd word's start, the penultimate word's end), how far inside the phrase a real edge may sit. est: words whose
    time is estimated (the online add-on lays a cloud word the local model did not hear between its neighbors);
    suspect: words with a retake sign (longer than LONG_WORD, or of no length: a repeat the recognizer collapsed);
    unfinished: the last word trails off ("..."). breaks: times where a phrase must end (the --from/--to fragment)."""
    out, cur = [], []

    def flush():
        if cur:
            out.append({"start": round(float(cur[0]["start"]), 3), "end": round(float(cur[-1]["end"]), 3),
                        "text": " ".join(str(w["text"]).strip() for w in cur), "words": len(cur),
                        "speaker": speaker_of(cur[0]),
                        "inner": (float(cur[1]["start"]), float(cur[-2]["end"])) if len(cur) > 1 else None,
                        "est": sum(1 for w in cur if w.get("est")),
                        "suspect": [str(w["text"]).strip() for w in cur
                                    if not 0.02 <= float(w["end"]) - float(w["start"]) <= LONG_WORD],
                        "unfinished": bool(UNFINISHED.search(str(cur[-1]["text"]).strip()))})
            cur.clear()

    for k, w in enumerate(words):
        prev = words[k - 1] if k else None
        if cur and prev is not None and (float(w["start"]) - float(prev["end"]) > PAUSE
                                         or speaker_of(w) != speaker_of(prev)
                                         or any(float(prev["start"]) < b <= float(w["start"]) for b in breaks)):
            flush()
        cur.append(w)
        if SENTENCE_END.search(str(w["text"]).strip()) or len(cur) >= MAX_WORDS:
            flush()
    flush()
    for k, p in enumerate(out):
        p["i"] = k
    return out


def repeated(text):
    """A repeat for emphasis: one word three times ("no, no, no", "no-no-no", "very very very")."""
    toks = [norm(t) for t in re.split(r"[\s" + re.escape(HYPHENS) + r"]+", text) if norm(t)]
    return any(toks[k] == toks[k + 1] == toks[k + 2] for k in range(len(toks) - 2))


def signs(ps, end_of_speech, m=None):
    """Signs, the gap after each phrase and its score. The gap is the transcript's, except where the transcript
    times touch (faster-whisper glued the pause into a word): there it is the speech mask's silence at that boundary,
    as for the clean edges (T5: two lines 1 s apart by the audio read "gap 0.0" with no beat)."""
    for k, p in enumerate(ps):
        t = p["text"].strip()
        prev = ps[k - 1] if k else None
        nxt = ps[k + 1] if k + 1 < len(ps) else None
        s = []
        if t.endswith("?"):
            s.append("question")
        if t.endswith("!"):
            s.append("exclaim")
        if repeated(t):
            s.append("repeat")
        if NUMBER_RE.search(t):  # a number of its own, not the digits of a name (T3: a brand name with digits gave the sign)
            s.append("number")
        if prev and prev["text"].strip().endswith("?") and not t.endswith("?"):
            s.append("answer")
        gap = (nxt["start"] - p["end"]) if nxt else (end_of_speech - p["end"])
        if nxt is not None and m is not None and gap < GLUED:
            pe, _, _, qs = bounds(m, p, nxt)
            gap = max(gap, qs - pe)
        if nxt is None or gap >= BEAT:
            s.append("beat")
        p["signs"] = s
        p["gap_after"] = round(gap, 2) if nxt else None
        p["score"] = (2 * ("repeat" in s) + 2 * ("exclaim" in s) + ("answer" in s) + ("number" in s)
                      + ("beat" in s) + (p["words"] <= 8))
    return ps


# ---- clean edges by the speech mask ----

def load_mask(wav):
    """(speech mask, quiet, hop) or None. The mask gives where speech starts and ends; `quiet` measures the silence at
    an edge: the raw 10 ms level under the threshold, except a voiceless sound the mask took into a word (a final
    "s" is quiet in the level but is speech). The mask itself is widened by ±30 ms and grown through short sounds, so
    its gaps are not the silence SKILL.md step 3 counts. A stray hiss outside the mask (the tail of a "zh") is not
    speech: counting it broke the silence after a clean line."""
    import speech_mask as sm
    env, hf = sm.load_envs(str(wav))
    if not env:
        return None
    sdb = sm.smax(env)
    srt = sorted(x for x in sdb if x > -90)
    p95 = srt[int(len(srt) * 0.95)] if srt else -20
    thr, vl = min(-30.0, p95 - 20), sm.voiceless(hf)
    mask = sm.speech_mask(sdb, thr, vl=vl)
    quiet = [x < thr and not (mask[k] and vl and vl[k]) for k, x in enumerate(env)]
    return mask, quiet, sm.HOP


def clean_before(quiet, i, need):
    """>= need quiet windows right before the sound of the speech span that starts at mask index i (the file's start
    counts as silence)."""
    r = next((m for m in range(i, min(len(quiet), i + 10)) if not quiet[m]), i)  # the mask starts ~30 ms early
    k = r
    while k > 0 and quiet[k - 1] and r - k < need:
        k -= 1
    return r - k >= need or k == 0


def clean_after(quiet, j, need):
    """>= need quiet windows right after the sound of the speech span that ends at mask index j (or the file's end)."""
    r = next((m for m in range(j - 1, max(-1, j - 11), -1) if not quiet[m]), j - 1)  # the mask ends ~30 ms late
    k = r + 1
    while k < len(quiet) and quiet[k] and k - r - 1 < need:
        k += 1
    return k - r - 1 >= need or k >= len(quiet)


def edge_in(m, t, before, lo=0.0, latest=None):
    """Where the speech of a phrase starting near t (transcript time) begins, with >= CLEAN of silence before it:
    the EARLIEST such onset within -0.5..+DRIFT s, before `before` (the phrase's end) and not earlier than `lo` (the
    previous phrase's end: an onset there is the neighbor's, and a range from it would take its words along). The
    nearest one was taken before, and a 0.14 s pause before the last word ("It does not mean | sold.") became the
    phrase's start, cutting off three words. An onset past `latest` (the 2nd word's start + INNER) is inside the
    phrase: None, as for continuous speech."""
    mask, quiet, hop = m
    need = int(round(CLEAN / hop))
    for i in range(max(0, int(max(t - 0.5, lo) / hop)), min(len(mask), int(min(t + DRIFT, before) / hop) + 1)):
        if mask[i] and (i == 0 or not mask[i - 1]) and clean_before(quiet, i, need):  # i == 0: the file's start
            return None if latest is not None and i * hop > latest else i * hop
    return None


def edge_out(m, t, after, hi=None, earliest=None):
    """Where the speech of a phrase ending near t ends, with >= CLEAN of silence after it (or the end of the file):
    the LATEST such end within -DRIFT..+0.5 s, after `after` (the phrase's start) and not later than `hi` (the next
    phrase's start). An end before `earliest` (the penultimate word's end - INNER) is inside the phrase: None."""
    mask, quiet, hop = m
    need = int(round(CLEAN / hop))
    top = t + 0.5 if hi is None else min(t + 0.5, hi)
    n = len(mask)
    for j in range(min(n, int(top / hop)), max(0, int(max(t - DRIFT, after) / hop)) - 1, -1):
        if j >= 1 and mask[j - 1] and (j == n or not mask[j]) and clean_after(quiet, j, need):  # j == n: the file's end
            return None if earliest is not None and j * hop < earliest else j * hop
    return None


def snap(t):
    return round(round(t * FPS) / FPS, 3)


def quiet_run(quiet, lo, hi):
    """The longest run of raw quiet 10 ms windows in [lo, hi)."""
    best = cur = 0
    for k in range(max(0, lo), min(len(quiet), hi)):
        cur = cur + 1 if quiet[k] else 0
        best = max(best, cur)
    return best


def mask_gap(m, lo_t, hi_t, near):
    """The speech mask's silence lying inside (lo_t, hi_t) nearest to `near` with >= CLEAN of raw silence in it ->
    (start, end) or None. The same rule as a phrase edge (clean_before/clean_after) and the cut that speech_mask.py
    makes: the mask is widened by ~30 ms each side, so its gap is ~60 ms shorter than the pause, and a minimum on the
    mask's own gap (it was 2 x CLEAN) rejected a 0.24 s pause, a 0.18 s gap in the mask (T7)."""
    mask, quiet, hop = m
    need = int(round(CLEAN / hop))
    best, k, stop = None, max(1, int(lo_t / hop)), min(len(mask), int(hi_t / hop) + 1)
    while k < stop:
        if mask[k]:
            k += 1
            continue
        j = k
        while j < len(mask) and not mask[j]:
            j += 1
        a, b = k * hop, j * hop
        if a >= lo_t - 1e-9 and b <= hi_t + 1e-9 and quiet_run(quiet, k - MASK_WIDEN, j + MASK_WIDEN) >= need:
            d = 0.0 if a <= near <= b else min(abs(a - near), abs(b - near))
            if best is None or d < best[0]:
                best = (d, a, b)
        k = j
    return best[1:] if best else None


def bounds(m, p, q):
    """The boundary between consecutive phrases p and q -> (where p's speech ends by the transcript or the mask, the
    latest end allowed for p, the earliest start allowed for q, where q's speech starts). Normally the transcript
    times with 50 ms of slack. When they touch (< GLUED apart: faster-whisper glued the pause into a word), the
    mask's silence nearest to the boundary between p's penultimate word and q's second word, split at its middle;
    no such silence: the transcript times (continuous speech stays "no clean edge")."""
    plain = (p["end"], q["start"] + 0.05, p["end"] - 0.05, q["start"])
    if m is None or q["start"] - p["end"] >= GLUED:
        return plain
    lo_t = p["inner"][1] if p.get("inner") else p["start"]
    hi_t = q["inner"][0] if q.get("inner") else q["end"]
    g = mask_gap(m, lo_t, hi_t, (p["end"] + q["start"]) / 2)
    if not g:
        return plain
    mid = (g[0] + g[1]) / 2
    return g[0], mid, mid, g[1]


def usable(p, lo=TEASER_WORDS[0]):
    """A phrase that can stand alone as a teaser or a payoff: at least `lo` words, every word heard with a measured
    time (no estimated word), no retake sign, and it does not trail off. T4 offered an interjection with an estimated
    word and the fragment of a broken take while a clean statement was left out."""
    return p["words"] >= lo and not p.get("est") and not p.get("suspect") and not p.get("unfinished")


def speech_len(p):
    """The phrase's length: its clean range when it has one (the transcript drifts by 0.1-0.8 s: T4's strong line ran
    4.88 s by the transcript and 4.43 s by the audio), else the transcript times."""
    r = p.get("range")
    return (r[1] - r[0]) if r else p["end"] - p["start"]


def teaser_rank(p):
    """The signs' score plus a point for clean edges and one for a whole sentence: the script cannot judge meaning,
    so a clean statement with a beat after it ranks with the lines that have louder signs."""
    whole = bool(SENTENCE_END.search(p["text"].strip())) and not p.get("unfinished")
    return p["score"] + bool(p.get("clean")) + whole


def cut_range(m, p, prev=None, nxt=None):
    """(start, end) for cut.json when the phrase can be cut out cleanly, else None. Edges like speech_mask.py: first
    speech - 20 ms, last speech + 30 ms, and never closer than 30 ms to the next phrase's speech. The edges stay
    between the neighbor phrases (by their transcript times, with 50 ms of slack): continuous speech with a dip
    before this phrase is not this phrase alone. Real case: "Worked with objections, and so?" ran into the next line
    with a 90 ms gap; its range ended at a pause before "and so?" and dropped them."""
    if m is None:
        return None
    mask, _, hop = m
    t_in, lo = p["start"], 0.0
    if prev:
        _, _, lo, t_in = bounds(m, prev, p)
    t_out, hi = p["end"], None
    if nxt:
        t_out, hi, _, _ = bounds(m, p, nxt)
    inner = p.get("inner")
    a = edge_in(m, t_in, p["end"] - 0.1, lo, inner[0] + INNER if inner else None)
    b = edge_out(m, t_out, (p["start"] if a is None else a) + 0.05, hi,  # a short word: after its real onset
                 inner[1] - INNER if inner else None)
    if a is None or b is None or b <= a:
        return None
    j = int(round(b / hop))  # b = j * hop: int() alone gives j - 1 for ~5% of j, the phrase's own speech
    nxt = next((x for x in range(j, len(mask)) if mask[x]), None)
    e = min(b + 0.03, len(mask) * hop) if nxt is None else min(b + 0.03, nxt * hop - 0.03)
    return snap(max(0.0, a - 0.02)), min(snap(e), round(len(mask) * hop, 3))


# ---- history: earlier edits of the same source ----

def source_files(cut):
    """The source file names of a cut.json: {"main": {"file": "A.mov"}} or the short form {"main": "A.mov"}."""
    out = []
    for s in (cut.get("sources") or {}).values():
        f = s.get("file") if isinstance(s, dict) else s if isinstance(s, str) else None
        if f:
            out.append(str(f))
    return out


def names_file(text, stem):
    """Whether notes name the source file itself, as a whole token: the stem with a video extension ("sunrise.mp4"),
    or a camera-like stem of letters and digits alone ("IMG_1234"). A plain word stem needs the extension: a brand or
    another file sharing it is not the source (T5: the brand of the same name, "sunrise-promo.mp4" another render)."""
    exts = "|".join(sorted(x.lstrip(".") for x in VIDEO_EXT))
    tail = r"(?:\.(?:" + exts + r"))" + ("?" if re.search(r"\d", stem) and re.search(r"[^\W\d_]", stem) else "")
    return bool(re.search(r"(?<![\w.\-])" + re.escape(stem) + tail + r"(?![\w\-]|\.\w)", text, re.I))


def history(project, stem, skip=None):
    """[(folder, why, first note line)] for edit folders that used a source with this stem."""
    out, low = [], stem.lower()
    root = Path(project) / "edit"
    if not root.is_dir():
        return out
    dirs = [root] + sorted(d for d in root.iterdir() if d.is_dir())
    for d in dirs:
        if skip and d.resolve() == Path(skip).resolve():
            continue
        why = []
        try:
            cut = load_json(d / "cut.json") or {}
        except (ValueError, OSError) as ex:  # a syntax error, a BOM from an editor: that folder is skipped, not fatal
            warn(f"{(d / 'cut.json').relative_to(project).as_posix()}: not read ({ex.__class__.__name__}): skipped")
            cut = {}
        if not isinstance(cut, dict):
            cut = {}
        if any(Path(f).stem.lower() == low for f in source_files(cut)):
            why.append("cut.json")
        tr = d / "transcripts"
        if tr.is_dir() and any(f.name.lower().split(".")[0] == low for f in tr.iterdir()):  # IMG_12 is not IMG_1234
            why.append("transcripts")
        note = d / "project.md"
        line = ""
        if note.exists():
            text = note.read_text(encoding="utf-8", errors="replace")
            if names_file(text, stem):
                why.append("project.md")
            line = next((ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")), "")[:200]
        if why:
            out.append((d.relative_to(project).as_posix(), why, line))
    return out


# ---- commands ----

def source_transcripts(e):
    """{cut.json source key: its transcript path}, resolved as cut.py does: the source's "transcript" (the project
    root, then the video folder), else edit/<id>/transcripts/<file stem>.json."""
    cut = load_json(e / "cut.json") or {}
    out = {}
    for key, s in (cut.get("sources") or {}).items():
        f = s.get("file") if isinstance(s, dict) else s if isinstance(s, str) else None
        tr = s.get("transcript") if isinstance(s, dict) else None
        if tr:
            p = Path(str(tr))
            for base in ([] if p.is_absolute() else [project_root(), e]):
                if (base / p).exists():
                    p = base / p
                    break
        else:
            p = e / "transcripts" / f"{Path(str(f or key)).stem}.json"
        out[str(key)] = p
    return out


def transcript_of(e, given=None, source=None):
    """The one transcript to analyze: --transcript; --source KEY; the only source of cut.json; without cut.json the
    only transcript in transcripts/. Several and no choice -> exit with the list (never the newest by guess)."""
    if given:
        return Path(given)
    srcs = source_transcripts(e)
    if source:
        if source not in srcs:
            sys.exit(f"--source {source}: not in cut.json (sources: {', '.join(srcs) or 'none'})")
        return srcs[source]
    if len(srcs) == 1:  # even when it is missing: the only transcript in transcripts/ may be another take's
        return next(iter(srcs.values()))
    if len(srcs) > 1:
        sys.exit(f"cut.json has {len(srcs)} sources: name the one to analyze with --source KEY (or --transcript F): "
                 + "; ".join(f"{k} ({p.relative_to(e).as_posix() if p.is_relative_to(e) else p}"
                             f"{'' if p.exists() else ', not transcribed yet'})" for k, p in srcs.items())
                 + ". Two cameras: run it per source, or on the main angle")
    skip = (".local.json", ".raw.json", ".prev.json")
    cands = sorted(f for f in (e / "transcripts").glob("*.json") if not f.name.endswith(skip)) \
        if (e / "transcripts").is_dir() else []
    if len(cands) > 1:
        sys.exit(f"{len(cands)} transcripts in {e / 'transcripts'}: name one with --transcript F: "
                 + ", ".join(f.name for f in cands))
    return cands[0] if cands else None


def cmd_suggest(a):
    e = edit_dir(a.edit)
    if a.transcript and a.source:
        sys.exit("--transcript or --source, not both")
    tp = transcript_of(e, a.transcript, a.source)
    if not tp or not tp.exists():
        sys.exit(f"{e}: no transcript{f' {tp}' if tp else ''}: transcribe.py {a.edit} <source> first (step 2)")
    doc = load_json(tp) or {}
    words = join_punct(join_hyphen_parts([w for w in doc.get("words", []) if w.get("type", "word") == "word"
                                          and str(w.get("text", "")).strip()]))
    if not words:
        sys.exit(f"{tp}: no words")
    stem = Path(str(doc.get("source") or tp.stem)).stem
    wav = Path(a.audio) if a.audio else next((p for p in (e / f"audio16k-{stem}.wav", e / "audio16k.wav") if p.exists()), None)
    m = load_mask(wav) if wav and wav.exists() else None
    if m is None:
        warn("no analysis audio (transcribe.py makes audio16k-<stem>.wav): clean edges are not checked")
    lo_t = a.start if a.start is not None else float("-inf")
    hi_t = a.end if a.end is not None else float("inf")
    if lo_t >= hi_t:
        sys.exit(f"--from {a.start} is not before --to {a.end}")
    last_t = float(words[-1]["end"])
    if a.end is not None and a.end > last_t + 2.0:
        warn(f"--to {a.end} is past the last word of {tp.name} ({last_t:.1f} s): is this the right source?")
    allp = signs(phrases(words, [t for t in (a.start, a.end) if t is not None]), float(words[-1]["end"]), m)
    for k, p in enumerate(allp):
        r = cut_range(m, p, allp[k - 1] if k else None, allp[k + 1] if k + 1 < len(allp) else None)
        p["clean"] = None if m is None else bool(r)
        p["range"] = list(r) if r else None
    for p in allp:  # after all ranges: a boundary reads both phrases' inner points
        p.pop("inner", None)
    # a fragment of a long recording: its phrases only, the neighbors outside it have bounded the edges above
    ps = [p for p in allp if lo_t <= p["start"] < hi_t]
    if not ps:
        sys.exit(f"{tp.name}: no speech between {a.start} and {a.end} s")
    end_speech = ps[-1]["end"]

    first = ps[0]["start"]
    early = first + EARLY * (end_speech - first)

    def opens(p):
        """A strong line: a question or a high score; a number (a price, a result) in the opening seconds too."""
        return ("question" in p["signs"] or p["score"] >= 3
                or ("number" in p["signs"] and p["start"] - first <= SLOW_START))
    # only in the first third: a strong line near the end is a teaser or the ending, not where the video starts
    strong = next((p for p in ps if p["start"] <= early and opens(p)), None)
    slow = round(strong["start"] - first, 2) if strong else None
    late = first + 0.66 * (end_speech - first)
    teasers = [p for p in ps if p is not ps[0] and p["start"] - first > 1.5 and usable(p)
               and p["words"] <= TEASER_WORDS[1] and TEASER_MIN <= speech_len(p) <= TEASER_MAX and teaser_rank(p) >= 2]
    teasers.sort(key=lambda p: (-teaser_rank(p), not p["clean"], p["start"]))
    payoff = next((p for p in reversed(ps) if "answer" in p["signs"] and usable(p)), None)
    top = teasers[:3]
    if payoff in teasers and payoff not in top:  # the payoff is always shown, with its risk: a teaser of it is a choice
        top.append(payoff)
    teasers = top
    for p in teasers:
        p["risk"] = "late in the video: if it is the payoff, a teaser gives the ending away" if p["start"] >= late else ""
    last = ps[-1]
    hist = history(project_root(), stem, skip=e)
    out = {"transcript": str(tp), "audio": str(wav) if wav else None,
           "window": [a.start, a.end] if a.start is not None or a.end is not None else None, "phrases": ps,
           "teasers": [p["i"] for p in teasers], "slow_start_s": slow, "strong_first": strong["i"] if strong else None,
           "ending": {"last": last["i"], "payoff": payoff["i"] if payoff else None},
           "history": [{"dir": d, "why": w, "note": n} for d, w, n in hist]}
    save_json(e / "structure.json", out)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    print(f"{tp.name}: {len(ps)} phrases, speech {first:.2f}-{end_speech:.2f} s"
          + (f" (fragment {a.start if a.start is not None else 'start'}-{a.end if a.end is not None else 'end'} s"
             f" of {len(allp)} phrases)" if out["window"] else "")
          + ("" if m is not None else " (clean edges not checked: no audio)"))
    for p in ps:
        cl = "" if p["clean"] is None else ("clean" if p["clean"] else "no clean edge")
        flags = (["est"] if p["est"] else []) + (["retake?"] if p["suspect"] else []) + (["unfinished"] if p["unfinished"] else [])
        print(f"  {p['i']:2d} {p['start']:7.2f}-{p['end']:6.2f}  {cl:13s} {','.join(p['signs'] + flags):24s} {p['text'][:70]}")
    print("  signs: question, exclaim, repeat (a word three times), number, answer (after a question), beat (a pause "
          f">= {BEAT} s after it); flags: est = a word whose time is estimated (a word the online add-on's transcript added "
          "between its neighbors: not heard by the local model, so its edges are a guess; not a teaser), retake? = a "
          f"word longer than {LONG_WORD} s or of no length (a merged retake), unfinished = the line trails off")
    print("\nteaser candidates: a short list by signs only (3-12 words, 0.8-4.5 s, no estimated or retake-suspect word; "
          "clean edges, a whole sentence and a beat after it rank higher). The script cannot judge meaning: pick the line "
          "by meaning, from here or from any clean phrase above")
    if not teasers:
        print("  none by the signs: the start in the original order, or a line the agent picks by meaning")
    for p in teasers:
        src = f'"source": {json.dumps(a.source, ensure_ascii=False)}, ' if a.source else ""
        rng = (f'{{{src}"start": {p["range"][0]:.3f}, "end": {p["range"][1]:.3f}, "beat": "teaser"}}' if p["range"]
               else "no clean edge: only together with a neighboring phrase")
        why = p["signs"] + (["whole sentence"] if SENTENCE_END.search(p["text"].strip()) else []) \
            + (["short"] if p["words"] <= 8 else [])
        print(f"  #{p['i']} {p['start']:.2f}-{p['end']:.2f} ({', '.join(why)}): {p['text'][:70]}\n"
              f"      ranges: {rng}" + (f"\n      risk: {p['risk']}" if p["risk"] else ""))
    if slow is not None and slow > SLOW_START:
        print(f"\nslow start: {slow:.1f} s of speech before the first question or strong line (#{strong['i']} at "
              f"{strong['start']:.2f}): offer to start there")
    elif strong is None:
        print(f"\nstart: no question, number or strong line by the signs in the first third (up to {early:.1f} s): judge "
              f"the first line by meaning; keep the order, or open with a teaser from the list")
    print(f"\nending: the last line #{last['i']} “{last['text'][:60]}”"
          + (f"; the payoff after a question #{payoff['i']} “{payoff['text'][:60]}”" if payoff else "")
          + "; hold the reaction after the last word rather than cutting on it")
    if hist:
        print("\nthis source was edited before: read those notes first (what was chosen, what the person changed)")
        for d, w, n in hist:
            print(f"  {d} ({', '.join(w)}): {n}")
    print(f"\n{e / 'structure.json'}")
    return 0


def cmd_history(a):
    target = Path(a.target)
    project = project_root()
    folder = target.is_dir() or (project / a.target).is_dir() or (project / "edit" / a.target).is_dir()
    if target.suffix and not folder:  # a source file
        stem, skip = target.stem, None
    else:
        e = edit_dir(a.target)
        cut = load_json(e / "cut.json") or {}
        files = [Path(f).stem for f in source_files(cut)]
        stem, skip = (files[0] if files else e.name), e
    hist = history(project, stem, skip=skip)
    if not hist:
        print(f"{stem}: no earlier edits found in edit/")
    for d, w, n in hist:
        print(f"{d} ({', '.join(w)}): {n}")
    return 0


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suggest")
    s.add_argument("edit")
    s.add_argument("--from", dest="start", type=float, help="source seconds: analyze the fragment from here")
    s.add_argument("--to", dest="end", type=float, help="source seconds: ...up to here")
    s.add_argument("--transcript", help="the transcript file to analyze")
    s.add_argument("--source", help="the cut.json source key whose transcript to analyze (two cameras: per source)")
    s.add_argument("--audio")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_suggest)
    h = sub.add_parser("history")
    h.add_argument("target", help="edit/<id> or a source file name")
    h.set_defaults(fn=cmd_history)
    a = ap.parse_args(argv)
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
