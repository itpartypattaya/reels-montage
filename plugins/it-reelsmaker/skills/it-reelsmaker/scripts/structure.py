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
  • take candidates by the text ("retakes"): two stretches of speech that say the same words, an opening said again,
    a word said twice; each pair with its times, clean ranges and a confidence. The phrases of the earlier member are
    flagged "take?" and left out of the teasers. The script never picks the take to keep (SKILL.md step 3: real
    edits kept the first as often as the last). With --from/--to, the pairs that touch the fragment;
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
looked for inside it, while the neighbors outside still bound the clean edges. The audio is read only for the fragment
and AUDIO_ROOM around it (a 90-minute WAV takes minutes to read whole): the threshold comes from that stretch, and a take
member farther out gets no clean range.
It writes edit/<id>/structure.json. Nothing is cut: the variants go into the cut plan (SKILL.md, step 3a) and the
person chooses.
"""
import argparse, json, re, sys, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (NUMBER_RE, STEM_LEN, VIDEO_EXT, edit_dir, load_json, project_root, restart_at, save_json,
                          significant, speaker_of, stem as stem_of, take_words, utf8_stdio, warn)
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
AUDIO_ROOM = 5.0    # s of audio read past --from/--to: the neighbor phrases that bound the fragment's clean edges
UNFINISHED = re.compile(r"(\.\.\.|…)['\")»”]*$")  # a cut-off word or a line that trails off
CUT_OFF = re.compile(r"(\.\.\.|…|[-‐‑–—])$")  # a word the transcript marks cut off: "skil...", "skil-"
NORM = re.compile(r"[^\w]+", re.U)
# takes by the text (retakes): starting points, set by a calibration on real recordings
TAKE_PAUSE = 0.85    # s: a pause this long ends a stretch compared as one take
TAKE_SENTENCE = 7.5  # s: a sentence end ends the stretch once it runs this long
TAKE_LONG = 16.0     # s: ...and it ends anyway at this length
EST_RUN = 3          # words in a row with estimated times: a take only the cloud heard, a stretch of its own
TAKE_NEXT, TAKE_SPAN = 8, 75.0   # a stretch is compared with the next 8 within 75 s
SIGNATURE = 18       # the first significant stems of a stretch that are compared
TAKE_HIGH, TAKE_MIN, TAKE_LOW = 0.45, 0.34, 0.24  # Jaccard of the signatures: a take, high; a take; to review
FALSE_START = (6.0, 12.0)  # s: a broken opening shorter than this, said again within this
REPEAT_RUN, REPEAT_SIG = 3, 2  # a run of words said again: this many words, this many significant (+1 mid-stretch)
STUTTER_GAP, PREFIX_GAP = 0.5, 1.0  # s: a word said twice within this; a cut-off word and the whole one within this


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

def load_mask(wav, start=None, end=None):
    """(speech mask, quiet, hop) or None. The mask gives where speech starts and ends; `quiet` measures the silence at
    an edge: the raw 10 ms level under the threshold, except a voiceless sound the mask took into a word (a final
    "s" is quiet in the level but is speech). The mask itself is widened by ±30 ms and grown through short sounds, so
    its gaps are not the silence SKILL.md step 3 counts. A stray hiss outside the mask (the tail of a "zh") is not
    speech: counting it broke the silence after a clean line.
    start/end (seconds): read only that stretch of the WAV; the lists still count windows from the file's start (the
    windows before the stretch are silence with no speech), so every index below is the file's."""
    import speech_mask as sm
    env, hf, t0 = sm.load_span(str(wav), start, end)
    if not env:
        return None
    sdb = sm.smax(env)
    srt = sorted(x for x in sdb if x > -90)
    p95 = srt[int(len(srt) * 0.95)] if srt else -20
    thr, vl = min(-30.0, p95 - 20), sm.voiceless(hf)
    mask = sm.speech_mask(sdb, thr, vl=vl)
    quiet = [x < thr and not (mask[k] and vl and vl[k]) for k, x in enumerate(env)]
    pad = int(round(t0 / sm.HOP))
    return [False] * pad + mask, [True] * pad + quiet, sm.HOP


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
    time (no estimated word), no retake sign, not in the earlier member of a take pair (retakes), and it does not trail
    off. T4 offered an interjection with an estimated word and the fragment of a broken take while a clean statement
    was left out."""
    return (p["words"] >= lo and not p.get("est") and not p.get("suspect") and not p.get("take")
            and not p.get("unfinished"))


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


# ---- takes: the same words said again (SKILL.md step 3) ----
# Another source of take candidates besides the stretched word ("retake?"): two stretches of speech that say the same
# words, an opening said again, a word said twice. The script lists the pairs and never picks the take to keep: real
# edits kept the first take as often as the last, and that is the agent's call by the rules of step 3.

def take_segments(words, toks):
    """Words -> stretches of speech compared as takes: [{w0, w1 (word indexes, w1 excluded), start, end, stems}].
    Not phrases(): those end at every sentence end, and two one-sentence phrases matched on a single word. A stretch
    ends at a pause over TAKE_PAUSE, at a sentence end once it runs TAKE_SENTENCE, at TAKE_LONG, at a speaker change,
    and at either edge of a run of EST_RUN words with estimated times: the online add-on lays a take the local model
    merged as cloud words of ~0.02 s with no pause between them, so no pause marks where that take begins.
    toks: take_words of each word."""
    n = len(words)
    cuts, k = set(), 0
    while k < n:
        j = k
        while j < n and words[j].get("est"):
            j += 1
        if j - k >= EST_RUN:
            cuts |= {k, j}
        k = max(j, k + 1)
    out, w0 = [], 0
    for k in range(1, n + 1):
        if k < n:
            prev, w = words[k - 1], words[k]
            run = float(prev["end"]) - float(words[w0]["start"])
            if not (k in cuts or float(w["start"]) - float(prev["end"]) > TAKE_PAUSE or speaker_of(w) != speaker_of(prev)
                    or run >= TAKE_LONG or (run >= TAKE_SENTENCE and SENTENCE_END.search(str(prev["text"]).strip()))):
                continue
        out.append({"w0": w0, "w1": k, "start": float(words[w0]["start"]), "end": float(words[k - 1]["end"]),
                    "stems": [stem_of(t) for x in range(w0, k) for t in toks[x] if significant(t)]})
        w0 = k
    return out


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def lead(a, b):
    """How many stems two stretches open with in the same order."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def stream_repeats(words, toks, opens=()):
    """An opening broken off and said again inside the speech ("If you want to grow your skills | If you want to grow
    your abilities"): a run of REPEAT_RUN words or more said again within FALSE_START[1] s -> [(i, j, e)]: word
    indexes of the two runs' first words and the word after the second run. Words are compared by their stems, so a
    cut-off word matches the whole one; a run said again right after itself is a take too (two takes 0.5 s apart are
    one stretch for take_segments). The run needs 3 significant words, or 2 when the second run opens a stretch
    (opens: word indexes after a pause): "choose those who know" said twice in a closing pair of lines is rhetoric."""
    flat = [(k, t) for k, ts in enumerate(toks) for t in ts]
    key = [stem_of(t) if significant(t) else t for _, t in flat]
    out, seen = [], set()
    for i in range(len(flat)):
        t0 = float(words[flat[i][0]]["start"])
        for j in range(i + 1, len(flat)):
            if float(words[flat[j][0]]["start"]) - t0 > FALSE_START[1]:
                break
            if key[j] != key[i] or (i - 1, j - 1) in seen:
                continue
            n = 0
            while j + n < len(flat) and i + n < j and key[i + n] == key[j + n]:
                n += 1
            sig = sum(1 for _, t in flat[i:i + n] if significant(t))
            opening = flat[j][0] in opens and flat[j - 1][0] != flat[j][0]  # the first word of a stretch, from its start
            if n >= REPEAT_RUN and sig >= REPEAT_SIG + (not opening):
                out.append((flat[i][0], flat[j][0], flat[j + n - 1][0] + 1))
                seen |= {(i + x, j + x) for x in range(n)}
                break
    return out


def sentence_repeats(words, toks):
    """A whole sentence said again word for word within TAKE_SPAN ("Worked with objections." twice, the second time
    with another question after it): [(i, i1, j, j1)] word ranges. REPEAT_RUN words or more, REPEAT_SIG significant.
    Needs the transcript's punctuation: a transcript without it has no sentences here."""
    sents, s0 = [], 0
    for k, w in enumerate(words):
        if SENTENCE_END.search(str(w["text"]).strip()):
            sents.append((s0, k + 1))
            s0 = k + 1
    out = []
    for x, (i, i1) in enumerate(sents):
        ka = [stem_of(t) if significant(t) else t for k in range(i, i1) for t in toks[k]]
        if len(ka) < REPEAT_RUN or sum(1 for k in range(i, i1) for t in toks[k] if significant(t)) < REPEAT_SIG:
            continue
        for j, j1 in sents[x + 1:]:
            if float(words[j]["start"]) - float(words[i]["start"]) > TAKE_SPAN:
                break
            if [stem_of(t) if significant(t) else t for k in range(j, j1) for t in toks[k]] == ka:
                out.append((i, i1, j, j1))
                break
    return out


def stutters(words, toks):
    """A word said twice in a row (within STUTTER_GAP), or cut off and said whole (a start of 3-5 letters that trails
    off in the transcript, "skil...", and the next word begins with, within PREFIX_GAP) -> [(k, k2)] word indexes.
    Not a word said three times in a row (a repeat for emphasis, the "repeat" sign), not a doubled word written with a
    hyphen ("long-long ago" is one word), not a function word ("no, no"), not two forms of one word ("from sales,
    sales stay with you"), and not a short word the next one begins with when nothing marks it cut off (Russian "each
    other" is such a pair, "feeling | to feel" another)."""
    flat = [(k, t) for k, ts in enumerate(toks) for t in ts]
    out = []
    for x in range(len(flat) - 1):
        (k, a), (k2, b) = flat[x], flat[x + 1]
        if k == k2 or not significant(a):
            continue
        gap = float(words[k2]["start"]) - float(words[k]["end"])
        if a == b and gap < STUTTER_GAP:
            if not any(flat[y][1] == a for y in (x - 1, x + 2) if 0 <= y < len(flat)):
                out.append((k, k2))
        elif (len(a) <= STEM_LEN and len(b) > len(a) and b.startswith(a) and gap < PREFIX_GAP
              and CUT_OFF.search(str(words[k]["text"]).strip())):
            out.append((k, k2))
    return out


def retakes(words, m=None):
    """Take candidates in a transcript -> [{kind, a, b, score, opening, est, confidence}]; a and b are the earlier and
    the later member, {start, end, text, range} (range: the member cut out cleanly by the audio, or None).
    kind "take": two stretches whose first SIGNATURE significant stems are alike (Jaccard >= TAKE_MIN, "high" from
    TAKE_HIGH; from TAKE_LOW with 2 of the first 4 stems shared: "review"); "false start": an opening said again,
    as a short stretch (< FALSE_START[0] s) whose 2-3 first stems open the next one within FALSE_START[1] s, or as a
    run of words said again inside the speech; "stutter": a word said twice or cut off and said whole. A restart word
    ("wait", "once more") at the seam raises the confidence. opening: the stems the two members open with."""
    toks = [take_words(w["text"]) for w in words]
    segs = take_segments(words, toks)
    found = []

    def add(kind, w0, w1, v0, v1, score, conf):
        sa = [stem_of(t) for x in range(w0, w1) for t in toks[x] if significant(t)]
        sb = [stem_of(t) for x in range(v0, v1) for t in toks[x] if significant(t)]
        seam = [t for x in list(range(max(w0, w1 - 3), w1)) + list(range(w1, v0) if v0 - w1 <= 6 else [])
                + list(range(v0, min(v1, v0 + 3))) for t in toks[x]]
        said = restart_at(seam)
        if said:
            conf = {"review": "medium", "medium": "high"}.get(conf, conf)
        found.append({"kind": kind, "a": member(words, w0, w1, m), "b": member(words, v0, v1, m),
                      "score": round(score, 2), "opening": lead(sa, sb),
                      "est": sum(1 for x in list(range(w0, w1)) + list(range(v0, v1)) if words[x].get("est")),
                      "confidence": conf, **({"restart": said} if said else {}), "_w": (w0, w1, v0, v1)})

    for i, a in enumerate(segs):
        sa = a["stems"][:SIGNATURE]
        for b in segs[i + 1:i + 1 + TAKE_NEXT]:
            if b["start"] - a["start"] > TAKE_SPAN:
                break
            sb = b["stems"][:SIGNATURE]
            if len(sa) < 2 or len(sb) < 2:  # one word alike is no take
                continue
            j = jaccard(sa, sb)
            if j >= TAKE_MIN:
                add("take", a["w0"], a["w1"], b["w0"], b["w1"], j, "high" if j >= TAKE_HIGH else "medium")
            elif j >= TAKE_LOW and len(set(sa[:4]) & set(sb[:4])) >= 2:
                add("take", a["w0"], a["w1"], b["w0"], b["w1"], j, "review")
            elif (lead(sa, sb) >= min(3, len(sa)) >= 2 and a["end"] - a["start"] < FALSE_START[0]
                  and b["start"] - a["end"] <= FALSE_START[1]):
                add("false start", a["w0"], a["w1"], b["w0"], b["w1"], j, "medium")
    seg_of = {k: s for s in segs for k in range(s["w0"], s["w1"])}
    for i, j, e in stream_repeats(words, toks, {s["w0"] for s in segs}):
        end = max(seg_of[j]["w1"], e)
        sa = [stem_of(t) for x in range(i, j) for t in toks[x] if significant(t)][:SIGNATURE]
        sb = [stem_of(t) for x in range(j, end) for t in toks[x] if significant(t)][:SIGNATURE]
        add("false start", i, j, j, end, jaccard(sa, sb), "medium")
    for i, i1, j, j1 in sentence_repeats(words, toks):
        add("take", i, i1, j, j1, 1.0, "review")
    for k, k2 in stutters(words, toks):
        add("stutter", k, k + 1, k2, k2 + 1, 1.0, "medium")
    # one spot found twice (a stretch pair and a run said again): the stronger reading stays
    rank = {"take": 0, "false start": 1, "stutter": 2}
    conf = {"high": 0, "medium": 1, "review": 2}
    found.sort(key=lambda r: (conf[r["confidence"]], rank[r["kind"]], -r["score"]))
    out = []
    for r in found:
        w0, w1, v0, v1 = r["_w"]
        if not any(w0 < x1 and x0 < w1 and v0 < y1 and y0 < v1 for x0, x1, y0, y1 in (q["_w"] for q in out)):
            out.append(r)
    out.sort(key=lambda r: (r["a"]["start"], r["b"]["start"]))
    for r in out:
        r.pop("_w")
    return out


def member(words, w0, w1, m=None):
    """A take member: words[w0:w1] -> {start, end, text, range}. range: cut out cleanly by the audio between the
    word before and the word after it (cut_range), or None."""
    span = {"start": float(words[w0]["start"]), "end": float(words[w1 - 1]["end"]),
            "inner": (float(words[w0 + 1]["start"]), float(words[w1 - 2]["end"])) if w1 - w0 > 1 else None}

    def one(k):
        return {"start": float(words[k]["start"]), "end": float(words[k]["end"]), "inner": None} \
            if 0 <= k < len(words) else None
    r = cut_range(m, span, one(w0 - 1), one(w1)) if m is not None else None
    return {"start": round(span["start"], 3), "end": round(span["end"], 3),
            "text": " ".join(str(words[k]["text"]).strip() for k in range(w0, w1)), "range": list(r) if r else None}


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
    win = None
    if a.start is not None or a.end is not None:
        win = (max(0.0, a.start - AUDIO_ROOM) if a.start is not None else None,
               a.end + AUDIO_ROOM if a.end is not None else None)
    m = load_mask(wav, *(win or (None, None))) if wav and wav.exists() else None
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
    # takes by the text, over the whole transcript: a take of a line inside the fragment may lie outside it
    takes = [r for r in retakes(words, m) if any(x["start"] < hi_t and x["end"] > lo_t for x in (r["a"], r["b"]))]
    for p in allp:  # the earlier member's phrases: "take?", never a teaser
        t = [k for k, r in enumerate(takes) if min(p["end"], r["a"]["end"]) - max(p["start"], r["a"]["start"]) > 0.05]
        if t:
            p["take"] = t
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
           "window": [a.start, a.end] if a.start is not None or a.end is not None else None,
           **({"audio_read": [win[0] or 0.0, win[1]]} if win and m is not None else {}), "phrases": ps,
           "retakes": takes, "teasers": [p["i"] for p in teasers], "slow_start_s": slow, "strong_first": strong["i"] if strong else None,
           "ending": {"last": last["i"], "payoff": payoff["i"] if payoff else None},
           "history": [{"dir": d, "why": w, "note": n} for d, w, n in hist]}
    save_json(e / "structure.json", out)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    print(f"{tp.name}: {len(ps)} phrases, speech {first:.2f}-{end_speech:.2f} s"
          + (f" (fragment {a.start if a.start is not None else 'start'}-{a.end if a.end is not None else 'end'} s"
             f" of {len(allp)} phrases)" if out["window"] else "")
          + ("" if m is not None else " (clean edges not checked: no audio)")
          + (f"; audio read {win[0] or 0:g}-{'end' if win[1] is None else format(win[1], 'g')} s only" if win and m is not None else ""))
    for p in ps:
        cl = "" if p["clean"] is None else ("clean" if p["clean"] else "no clean edge")
        flags = ((["est"] if p["est"] else []) + (["retake?"] if p["suspect"] else []) + (["take?"] if p.get("take") else [])
                 + (["unfinished"] if p["unfinished"] else []))
        print(f"  {p['i']:2d} {p['start']:7.2f}-{p['end']:6.2f}  {cl:13s} {','.join(p['signs'] + flags):24s} {p['text'][:70]}")
    print("  signs: question, exclaim, repeat (a word three times), number, answer (after a question), beat (a pause "
          f">= {BEAT} s after it); flags: est = a word whose time is estimated (a word the online add-on's transcript added "
          "between its neighbors: not heard by the local model, so its edges are a guess; not a teaser), retake? = a "
          f"word longer than {LONG_WORD} s or of no length (a merged retake), take? = in the earlier member of a take "
          "pair below (not a teaser), unfinished = the line trails off")
    print("\nTakes (candidates; which one to keep: SKILL.md step 3): the same words said again, by the text. take = two "
          "stretches alike, false start = an opening said again, stutter = a word said twice or cut off; the script "
          "does not pick the take to keep. A repeat the recognizer merged into one word is not here: see retake? above")
    if not takes:
        print("  none by the text")
    for r in takes:
        x, y = r["a"], r["b"]
        notes = [f"opening {r['opening']}"] + ([f"est {r['est']}"] if r["est"] else []) \
            + ([f"restart word “{r['restart']}”"] if r.get("restart") else [])
        print(f"  {r['kind']}, {r['confidence']} ({r['score']:.2f}; {', '.join(notes)})\n"
              f"      {x['start']:7.2f}-{x['end']:7.2f} “{x['text'][:70]}”"
              + (f" range {x['range'][0]:.3f}-{x['range'][1]:.3f}" if x["range"] else "") + "\n"
              f"      {y['start']:7.2f}-{y['end']:7.2f} “{y['text'][:70]}”"
              + (f" range {y['range'][0]:.3f}-{y['range'][1]:.3f}" if y["range"] else ""))
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
