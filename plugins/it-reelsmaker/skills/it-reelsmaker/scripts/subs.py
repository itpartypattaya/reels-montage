# -*- coding: utf-8 -*-
"""Subtitles in another language, and subtitle files (.srt) for the platforms.

    python scripts/subs.py phrases edit/<id> --lang en      # edit/<id>/subs/en.json: the phrases to translate
    python scripts/subs.py apply   edit/<id> --lang en      # check the translation → edit/<id>/captions-en.json
    python scripts/subs.py srt     edit/<id> [--lang en] [-o out/x.en.srt]   # a subtitle file (original or translation)

phrases — the speech of the finished rough cut (captions.json) split into phrases: at the end of a sentence, at a cut
          between segments, at a pause over 0.5 s, and at the latest after 16 words. Each phrase gets an id, its times
          and its words ("src"); "text" is the translation, empty for a new phrase. Run again after a re-cut: a phrase
          whose words did not change keeps its translation, a changed one is emptied and listed.
          The translation is written into "text" by the agent itself in the session (it knows the brand's voice and
          forbidden words from rules.md), or by a translation service of the person's choice; one phrase of the
          translation per phrase of the speech, never merged or split, so the times stay true. Names, numbers and terms
          stay as they are said; keep it as short as the speech (reading time, below).
apply   — checks the translation (every phrase translated, the source still matches captions.json, reading speed) and
          writes captions-<lang>.json in the captions.json format: the phrase's time is shared among its translated
          words by their length, so every subtitle mode of the kit shows the translation on the same rhythm (a
          translated word does not land exactly on its spoken word: the languages differ). Reading speed, counted
          over the time the phrase is on screen: a warning when the translation is over 17 characters per second and
          harder to read than the original subtitle; an error over 25 and 15 % over the original (fast speech is fast
          in any language, so only a translation slower to read than the original counts).
          Then: reel.json "subtitles_lang": "<lang>" → visual_plan.py export uses captions-<lang>.json for the subtitles.
srt     — SubRip subtitles for upload to the platform (YouTube, a player; on Instagram the captions are auto-made):
          the phrases with their times, up to 2 lines of 42 characters; --lang takes the translation.
"""
import argparse, hashlib, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import edit_dir, load_json, save_json, utf8_stdio, warn

SENTENCE_END = re.compile(r"[.!?…]['\")»”]*$")
MAX_WORDS, PAUSE = 16, 0.5
CPS_WARN, CPS_MAX = 17.0, 25.0
LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")


def phrases_of(cap):
    """[{id, start, end, src, seg}] from captions.json words, in order."""
    words = [w for w in cap.get("words", []) if str(w.get("text", "")).strip()]
    out, cur = [], []

    def flush():
        if cur:
            out.append({"start": round(cur[0]["start"], 3), "end": round(cur[-1]["end"], 3),
                        "src": " ".join(str(w["text"]).strip() for w in cur), "seg": cur[0].get("seg")})
            cur.clear()

    for k, w in enumerate(words):
        prev = words[k - 1] if k else None
        if cur and prev is not None and (w.get("seg") != prev.get("seg") or w["start"] - prev["end"] > PAUSE):
            flush()
        cur.append(w)
        if SENTENCE_END.search(str(w["text"]).strip()) or len(cur) >= MAX_WORDS:
            flush()
    flush()
    for k, p in enumerate(out, 1):
        p["id"] = f"p{k:03d}"
    return out


def fingerprint(cap):
    return hashlib.sha1(repr([(w.get("text"), w.get("start"), w.get("end")) for w in cap.get("words", [])]).encode()).hexdigest()[:12]


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
    old = {p["src"]: p.get("text", "") for p in (load_json(f) or {}).get("phrases", []) if p.get("text")}
    ps = phrases_of(cap)
    kept, todo = 0, []
    for p in ps:
        p["text"] = old.get(p["src"], "")
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
    """(phrases, errors, warnings) of a translation file against the current captions.json."""
    doc = load_json(f)
    if not doc:
        sys.exit(f"no {f}: run subs.py phrases first")
    ps, errs, warns = doc.get("phrases", []), [], []
    cur = {p["src"]: p for p in phrases_of(cap)}
    if doc.get("captions") != fingerprint(cap):
        stale = [p["id"] for p in ps if p["src"] not in cur]
        if stale or len(ps) != len(cur):
            errs.append(f"the rough cut changed since the phrases were made ({', '.join(stale[:8]) or 'other phrases'}):"
                        f" run subs.py phrases again (unchanged phrases keep their translation)")
    for k, p in enumerate(ps):
        t = str(p.get("text") or "").strip()
        if not t:
            errs.append(f"{p['id']} is not translated: {p['src']}")
            continue
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


def timed_words(p):
    """The translated phrase's words over the phrase's time, by length (+1 for the space)."""
    ws = str(p["text"]).split()
    tot = sum(len(w) + 1 for w in ws)
    t, out = p["start"], []
    for w in ws:
        d = (p["end"] - p["start"]) * (len(w) + 1) / tot
        out.append({"text": w, "start": round(t, 3), "end": round(t + d, 3), "type": "word",
                    **({"seg": p["seg"]} if p.get("seg") is not None else {})})
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
                    "language": a.lang, "captions": fingerprint(cap)})
    print(f"{out}: {len(ps)} phrase(s), {len(words)} word(s)" + (f"; {len(warns)} warning(s)" if warns else "")
          + f". For the render: reel.json \"subtitles_lang\": \"{a.lang}\", then visual_plan.py export")


def srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def two_lines(t, width=42):
    if len(t) <= width:
        return [t]
    ws, best = t.split(), None
    for k in range(1, len(ws)):  # the most even split into two lines, rather after a comma or a colon
        l1, l2 = " ".join(ws[:k]), " ".join(ws[k:])
        score = max(len(l1), len(l2)) - (8 if l1[-1] in ",;:" and max(len(l1), len(l2)) <= width else 0)
        if best is None or score < best[0]:
            best = (score, [l1, l2])
    return best[1] if best else [t]


def cmd_srt(a):
    e = edit_dir(a.edit)
    cap = load_cap(e)
    if a.lang:
        ps, errs, _ = check(e, subs_file(e, a.lang), cap)
        if errs:
            print("\n".join(f"  error: {x}" for x in errs))
            sys.exit(f"{len(errs)} problem(s): fix the translation first (subs.py apply shows the same)")
        texts = [p["text"].strip() for p in ps]
    else:
        ps = phrases_of(cap)
        texts = [p["src"] for p in ps]
    out = Path(a.output) if a.output else e / f"subtitles{'.' + a.lang if a.lang else ''}.srt"
    out.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for k, (p, t) in enumerate(zip(ps, texts), 1):
        nxt = ps[k]["start"] if k < len(ps) else p["end"] + 0.5
        end = min(nxt, p["end"] + 0.4)  # held a moment after the last word, like the kit's subtitles
        blocks.append(f"{k}\n{srt_time(p['start'])} --> {srt_time(end)}\n" + "\n".join(two_lines(t)) + "\n")
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
