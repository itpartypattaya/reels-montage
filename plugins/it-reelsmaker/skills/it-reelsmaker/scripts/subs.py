# -*- coding: utf-8 -*-
"""Subtitles in another language, and subtitle files (.srt) for the platforms.

    python scripts/subs.py phrases edit/<id> --lang en      # edit/<id>/subs/en.json: the phrases to translate
    python scripts/subs.py apply   edit/<id> --lang en      # check the translation → edit/<id>/captions-en.json
    python scripts/subs.py srt     edit/<id> [--lang en] [-o out/x.en.srt]   # a subtitle file (original or translation)

phrases — the speech of the finished rough cut (captions.json) split into phrases: at the end of a sentence, at a cut
          between segments, at a pause over 0.5 s, and at the latest after 16 words; a phrase too short to read on its
          own (under 3 words or 1 s) joins its neighbor in the same segment when no pause over 0.5 s separates them (a
          sentence's tail cut off by the word limit joins its sentence). Each phrase gets an id, its times and its
          words ("src"); "text" is the translation, empty for a new phrase. Run again after a re-cut: a phrase whose
          words did not change keeps its translation (phrases that became one get their translations joined), a
          changed one is emptied and listed.
          The translation is written into "text" by the agent itself in the session (it knows the brand's voice and
          forbidden words from rules.md), or by a translation service of the person's choice; one phrase of the
          translation per phrase of the speech, never merged or split, so the times stay true. Names, numbers and terms
          stay as they are said; keep it as short as the speech (reading time, below).
apply   — checks the translation (every phrase translated, the source still matches captions.json, reading speed) and
          writes captions-<lang>.json in the captions.json format: the phrase's time is shared among its translated
          words by their length, so every subtitle mode of the kit shows the translation on the same rhythm (a
          translated word does not land exactly on its spoken word: the languages differ). The phrase times always
          come from the current captions.json, so a re-cut that only shifted the words needs just apply again.
          Languages written without spaces (Chinese, Japanese, Thai, Lao, Khmer, Burmese): mark the word boundaries
          with "|" in the translation ("我们|今天|聊聊"); the words are then shown without spaces between them, one
          by one with the speech. Without the marks such a phrase is refused: it would come up all at once.
          Reading speed, counted
          over the time the phrase is on screen: a warning when the translation is over 17 characters per second and
          harder to read than the original subtitle; an error over 25 and 15 % over the original (fast speech is fast
          in any language, so only a translation slower to read than the original counts).
          Then: reel.json "subtitles_lang": "<lang>" → visual_plan.py export uses captions-<lang>.json for the subtitles.
srt     — SubRip subtitles for upload to the platform (YouTube, a player; on Instagram the captions are auto-made):
          the phrases with their times, up to 2 lines of 42 characters; a phrase longer than that becomes several
          subtitles (split at a sentence end or a comma nearest the middle, timed by its words; a translation by
          length). A line never ends with a short function word or a number torn from its word ("five / years"),
          as on the cards (typography.md, "Line breaks"); --lang takes the translation.
"""
import argparse, hashlib, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import SHORT_WORDS, bare, edit_dir, load_json, no_break, save_json, utf8_stdio, warn

SENTENCE_END = re.compile(r"[.!?…]['\")»”]*$")
MAX_WORDS, PAUSE = 16, 0.5
# a phrase this short joins its neighbor (T3: the 16-word limit left "areas." and "business." alone: one-word
# translations and 0.46-0.59 s subtitles)
MIN_WORDS, MIN_S = 3, 1.0
WIDTH = 42  # characters per line of an .srt subtitle, 2 lines at most
CPS_WARN, CPS_MAX = 17.0, 25.0
# scripts written without spaces between words: CJK ideographs, kana, Thai, Lao, Khmer, Myanmar
NO_SPACE = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u0e00-\u0e7f\u0e80-\u0eff"
                      "\u1780-\u17ff\u1000-\u109f]")
UNMARKED = 12  # characters of such a script in a row with no "|" or space: an unmarked phrase
LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")


def joinable(a, b):
    """Two neighboring phrases (lists of words) may be one: the same segment and speaker, no pause over PAUSE between
    them."""
    return (a[-1].get("seg") == b[0].get("seg") and a[-1].get("speaker") == b[0].get("speaker")
            and b[0]["start"] - a[-1]["end"] <= PAUSE)


def too_short(g):
    return len(g) < MIN_WORDS or g[-1]["end"] - g[0]["start"] < MIN_S


def merge_short(groups):
    """Phrases too short to read alone join a neighbor: a sentence's tail cut off by the word limit joins its
    sentence, a short sentence of its own joins the next phrase (or the previous one at the end)."""
    k = 0
    while k < len(groups):
        g = groups[k]
        if too_short(g):
            prev = groups[k - 1] if k else None
            nxt = groups[k + 1] if k + 1 < len(groups) else None
            if prev and joinable(prev, g) and not SENTENCE_END.search(str(prev[-1]["text"]).strip()):
                prev.extend(groups.pop(k))
                continue
            if nxt and joinable(g, nxt):
                g.extend(groups.pop(k + 1))
                continue
            if prev and joinable(prev, g):
                prev.extend(groups.pop(k))
                continue
        k += 1
    return groups


def phrases_of(cap, keep_words=False):
    """[{id, start, end, src, seg, speaker}] from captions.json words, in order; a speaker change ends a phrase (the
    kit colors subtitles per speaker); keep_words: also the words ("_words")."""
    words = [w for w in cap.get("words", []) if str(w.get("text", "")).strip()]
    groups, cur = [], []
    for k, w in enumerate(words):
        prev = words[k - 1] if k else None
        if cur and prev is not None and (w.get("seg") != prev.get("seg") or w.get("speaker") != prev.get("speaker")
                                         or w["start"] - prev["end"] > PAUSE):
            groups.append(cur)
            cur = []
        cur.append(w)
        if SENTENCE_END.search(str(w["text"]).strip()) or len(cur) >= MAX_WORDS:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    out = []
    for k, g in enumerate(merge_short(groups), 1):
        out.append({"start": round(g[0]["start"], 3), "end": round(g[-1]["end"], 3),
                    "src": " ".join(str(w["text"]).strip() for w in g), "seg": g[0].get("seg"), "id": f"p{k:03d}",
                    **({"speaker": g[0]["speaker"]} if g[0].get("speaker") else {}),
                    **({"_words": g} if keep_words else {})})
    return out


def take_translations(ps, old):
    """The translations of an earlier phrase list (old: [{src, text}] in order) for the phrases ps, matched by their
    words in order (the same phrase said twice may be translated twice differently: one each). A phrase that is
    several old ones joined (the short-phrase rule, a re-cut) gets their translations joined, when all have one."""
    pool = [[str(p.get("src", "")), str(p.get("text") or "").strip(), False] for p in old]
    for p in ps:
        hit = next((o for o in pool if not o[2] and o[0] == p["src"]), None)
        if hit:
            hit[2] = True
            p["text"] = hit[1]
            continue
        p["text"] = ""
        for i in range(len(pool)):
            j, src = i, ""
            while j < len(pool) and not pool[j][2] and len(src) < len(p["src"]):
                src = (src + " " + pool[j][0]).strip()
                j += 1
            if j - i > 1 and src == p["src"] and all(o[1] for o in pool[i:j]):
                p["text"] = " ".join(o[1] for o in pool[i:j])
                for o in pool[i:j]:
                    o[2] = True
                break
    return ps


def fingerprint(cap):
    """The rough cut a translation belongs to: the words with their times and speakers, the length and the segments
    (the kit takes the render length from the duration). Codex review: speakers corrected in cut.json with the words
    unchanged kept the old fingerprint, and the translated captions kept the old colors. Without speakers the value is
    the one 1.5.0 wrote, so an earlier translation stays valid."""
    segs = [(s.get("out_start"), s.get("out_dur"), s.get("src_start"), s.get("src_end")) for s in cap.get("segments", [])]
    words = [(w.get("text"), w.get("start"), w.get("end")) + ((w["speaker"],) if w.get("speaker") else ())
             for w in cap.get("words", [])]
    key = (cap.get("duration"), segs, words) + ((list(cap["speakers"]),) if cap.get("speakers") else ())
    return hashlib.sha1(repr(key).encode()).hexdigest()[:12]


def translation_id(doc):
    """Which translation: the phrases' words and their translations (subs/<lang>.json)."""
    return hashlib.sha1(repr([(p.get("src"), p.get("text")) for p in (doc or {}).get("phrases", [])]).encode()).hexdigest()[:12]


def subs_file(e, lang):
    if not LANG.match(lang or ""):
        sys.exit(f"--lang {lang!r}: a language code like en, de, pt-BR")
    return e / "subs" / f"{lang}.json"


def load_cap(e):
    cap = load_json(e / "captions.json")
    if not cap or not cap.get("words"):
        sys.exit(f"no words in {e / 'captions.json'}: subtitles come after the rough cut (cut.py)")
    return cap


def cmd_phrases(a):
    e = edit_dir(a.edit)
    cap = load_cap(e)
    f = subs_file(e, a.lang)
    ps = take_translations(phrases_of(cap), (load_json(f) or {}).get("phrases", []))
    kept, todo = 0, []
    for p in ps:
        kept += bool(p["text"])
        if not p["text"]:
            todo.append(p)
    save_json(f, {"lang": a.lang, "from": cap.get("language") or "", "captions": fingerprint(cap), "phrases": ps})
    print(f"{f}: {len(ps)} phrase(s); translated already {kept}, to translate {len(todo)}")
    for p in todo[:60]:
        print(f"  {p['id']} {p['start']:7.2f}  {p['src']}")
    if todo:
        print(f"write the translation into \"text\" of each phrase (one phrase each), then: subs.py apply {a.edit} --lang {a.lang}")


def check(e, f, cap):
    """(phrases, errors, warnings): the phrases of the CURRENT captions.json (their times) with the translations of the
    file, matched by their words in order; a phrase whose words changed in a re-cut has no translation."""
    doc = load_json(f)
    if not doc:
        sys.exit(f"no {f}: run subs.py phrases first")
    errs, warns = [], []
    ps = take_translations(phrases_of(cap), doc.get("phrases", []))
    for k, p in enumerate(ps):
        t = p["text"].replace("|", "")
        if not t:
            errs.append(f"{p['id']} is not translated: {p['src']}" + ("" if doc.get("captions") == fingerprint(cap) else
                        f" (the rough cut changed: subs.py phrases {e} --lang {doc.get('lang')} lists what to translate)"))
            continue
        if re.search(f"(?:{NO_SPACE.pattern}){{{UNMARKED},}}", t) and "|" not in p["text"]:
            errs.append(f"{p['id']}: a script written without spaces: mark the word boundaries with | so the words "
                        f"follow the speech (otherwise the whole phrase comes up at once): '{t}'")
        # on screen from its first word until the next phrase (at most 0.4 s after its last word), as the kit shows it
        nxt = ps[k + 1]["start"] if k + 1 < len(ps) else p["end"] + 0.4
        dur = max(0.3, min(nxt, p["end"] + 0.4) - p["start"])
        cps, src = len(t) / dur, len(p["src"]) / dur
        # fast speech is fast in any language: only a translation harder to read than the original subtitle counts
        if cps > max(CPS_MAX, src * 1.15):
            errs.append(f"{p['id']} {p['start']:.2f}: {cps:.0f} characters per second (the original {src:.0f}), "
                        f"nobody reads that: shorten '{t}'")
        elif cps > max(CPS_WARN, src):
            warns.append(f"{p['id']} {p['start']:.2f}: {cps:.0f} characters per second (the original {src:.0f}): "
                         f"shorter reads easier: '{t}'")
    return ps, errs, warns


def units(text):
    """[(word, glue)]: the words of a translation; glue = no space before it ("|" marks a boundary inside a run of a
    script written without spaces)."""
    out = []
    for chunk in str(text).split():
        for k, w in enumerate(x for x in chunk.split("|") if x):
            out.append((w, k > 0))
    return out


def plain(text):
    return " ".join("".join(chunk.split("|")) for chunk in str(text).split())


def timed_words(p):
    """The translated phrase's words over the phrase's time, by length (+1 for the space). "phrase": the phrase id, so
    the kit hides a whole translated phrase that a scene covers for the most part (a random tail of it after the
    scene does not read)."""
    ws = units(p["text"])
    tot = sum(len(w) + 1 for w, _ in ws)
    t, out = p["start"], []
    for w, glue in ws:
        d = (p["end"] - p["start"]) * (len(w) + 1) / tot
        out.append({"text": w, "start": round(t, 3), "end": round(t + d, 3), "type": "word", "phrase": p["id"],
                    **({"glue": True} if glue else {}), **({"seg": p["seg"]} if p.get("seg") is not None else {}),
                    **({"speaker": p["speaker"]} if p.get("speaker") else {})})
        t += d
    return out


def cmd_apply(a):
    e = edit_dir(a.edit)
    cap = load_cap(e)
    ps, errs, warns = check(e, subs_file(e, a.lang), cap)
    for w in warns:
        warn(w)
    if errs:
        print("\n".join(f"  error: {x}" for x in errs))
        sys.exit(f"{len(errs)} problem(s): captions-{a.lang}.json is not written")
    words = [w for p in ps for w in timed_words(p)]
    out = e / f"captions-{a.lang}.json"
    save_json(out, {"duration": cap.get("duration"), "segments": cap.get("segments", []), "words": words,
                    **({"speakers": cap["speakers"]} if cap.get("speakers") else {}),
                    "language": a.lang, "captions": fingerprint(cap),
                    "translation": translation_id(load_json(subs_file(e, a.lang)))})
    print(f"{out}: {len(ps)} phrase(s), {len(words)} word(s)" + (f"; {len(warns)} warning(s)" if warns else "")
          + f". For the render: reel.json \"subtitles_lang\": \"{a.lang}\", then visual_plan.py export")


def srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def two_lines(t, width=WIDTH):
    """A subtitle in at most two lines of `width`: the most even split that fits, rather after a comma, a colon or a
    sentence end; never after a short function word or a number torn from its word (reels_common.no_break, the same
    rules as glue() on the cards). T3: lines of 54-59 characters and "more than five / years"."""
    if len(t) <= width or " " not in t:
        return [t]
    ws, best = t.split(), None
    for k in range(1, len(ws)):
        l1, l2 = " ".join(ws[:k]), " ".join(ws[k:])
        over = max(0, len(l1) - width) + max(0, len(l2) - width)
        # rather after punctuation, or before a conjunction or a preposition (a new clause starts there)
        bonus = 8 if l1[-1] in ",;:.!?…" else 4 if bare(ws[k]) in SHORT_WORDS else 0
        score = (over, no_break(ws[k - 1], ws[k]), max(len(l1), len(l2)) - bonus)
        if best is None or score < best[0]:
            best = (score, [l1, l2])
    return best[1]


def fits(t, width=WIDTH):
    return all(len(x) <= width for x in two_lines(t, width))


def joined(units_):
    return "".join(("" if k == 0 or u["glue"] else " ") + u["text"] for k, u in enumerate(units_))


def pieces(units_, width=WIDTH):
    """A phrase's words ([{text, start, end, glue}]) -> runs that each fit two lines: split at the strongest boundary
    (a sentence end, then a colon, a semicolon or a dash, then a comma) where both halves fit and neither is a scrap
    of a few characters; the most even such split; never inside what glue() keeps together."""
    t = joined(units_)
    if len(units_) < 2 or fits(t, width) or " " not in t:
        return [units_]
    best = None
    for k in range(1, len(units_)):
        a, b = joined(units_[:k]), joined(units_[k:])
        end = units_[k - 1]["text"].rstrip()[-1:]
        strength = 3 if end in ".!?…" else 2 if end in ";:—–" else 1 if end == "," else 0
        score = (no_break(units_[k - 1]["text"], units_[k]["text"]), not (fits(a, width) and fits(b, width)),
                 min(len(a), len(b)) < 16, -strength, abs(len(a) - len(b)))
        if best is None or score < best[0]:
            best = (score, k)
    k = best[1]
    return pieces(units_[:k], width) + pieces(units_[k:], width)


def cmd_srt(a):
    e = edit_dir(a.edit)
    cap = load_cap(e)
    if a.lang:
        ps, errs, _ = check(e, subs_file(e, a.lang), cap)
        if errs:
            print("\n".join(f"  error: {x}" for x in errs))
            sys.exit(f"{len(errs)} problem(s): fix the translation first (subs.py apply shows the same)")
        runs = [[{"text": w["text"], "start": w["start"], "end": w["end"], "glue": bool(w.get("glue"))}
                 for w in timed_words(p)] for p in ps]  # a translation: its words timed by length
    else:
        ps = phrases_of(cap, keep_words=True)
        runs = [[{"text": str(w["text"]).strip(), "start": w["start"], "end": w["end"], "glue": False}
                 for w in p["_words"]] for p in ps]
    out = Path(a.output) if a.output else e / f"subtitles{'.' + a.lang if a.lang else ''}.srt"
    out.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for k, (p, run_) in enumerate(zip(ps, runs), 1):
        nxt = ps[k]["start"] if k < len(ps) else p["end"] + 0.5
        parts = pieces(run_)
        for j, part in enumerate(parts):
            start = p["start"] if j == 0 else part[0]["start"]
            # held a moment after the last word, like the kit's subtitles; a piece of a long phrase until the next piece
            end = parts[j + 1][0]["start"] if j + 1 < len(parts) else min(nxt, p["end"] + 0.4)
            blocks.append(f"{len(blocks) + 1}\n{srt_time(start)} --> {srt_time(end)}\n"
                          + "\n".join(two_lines(joined(part))) + "\n")
    out.write_text("\n".join(blocks), encoding="utf-8")
    print(f"{out}: {len(blocks)} subtitle(s)")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("phrases", help="the phrases to translate → edit/<id>/subs/<lang>.json")
    p.add_argument("edit"); p.add_argument("--lang", required=True); p.set_defaults(fn=cmd_phrases)
    p = sub.add_parser("apply", help="check the translation → edit/<id>/captions-<lang>.json")
    p.add_argument("edit"); p.add_argument("--lang", required=True); p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("srt", help="a SubRip subtitle file, original or translated")
    p.add_argument("edit"); p.add_argument("--lang"); p.add_argument("-o", "--output"); p.set_defaults(fn=cmd_srt)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
