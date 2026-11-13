"""The visual plan's core: its constants and speech patterns, the plan file and the settings snapshot, building
the spans, time and text helpers, and the ending (hook, end card, sting, corner logo) a stage keeps. Part of visual_plan.py, with no command line
of its own: the other scripts take these names from visual_plan."""
import contextlib, datetime, hashlib, math, re, sys
from pathlib import Path

from reels_common import (NUMBER_RE, budget, editing_json, effective, load_config, load_json, locked, probe,
                          save_json, warn)
from pic_track import pic_shots, shots_of_words


SCENE_MODES = ["overlay", "split", "panel", "window", "full"]  # a scene's default mode: the first of its own list
KINDS = {"broll": {"modes": ["replace", "window"], "prefix": "b"}, "meme": {"modes": ["popup", "cutaway"], "prefix": "m"},
         "scene": {"modes": SCENE_MODES, "prefix": "c"},
         "callout": {"modes": ["overlay"], "prefix": "l"}}  # a label pointing at an object (references/callouts.md)
# B-roll "window" (the Inserts component of the Remotion template): the box inserts[].box in 1080x1920 screen
# coordinates; without a box the template uses WINDOW_DEFAULT.
# Safe zone: right of x 960 are the UI buttons, above y 220 and below 1500 are the UI and the subtitles (the defaults:
# a project's own UI zone moves them, reels_common.ui_zone; a window may touch the left edge)
WINDOW_DEFAULT = [60, 250, 900, 675]
WINDOW_SLOTS = [WINDOW_DEFAULT, [60, 820, 900, 675]] + [[x, y, w, h] for w, h in ((600, 450), (480, 360))  # 4:3, larger -> smaller
                                                       for y in (250, 1500 - h) for x in (60, 960 - w - 60)]
# overlay scenes also try low bands in the headroom: every slot above is 360+ px tall and lands on a face that sits
# high (1789: all slots hit the face, WINDOW_DEFAULT was saved on it with only a warning)
HEADROOM_BAND = [60, 250, 900, 310]
HEADROOM_MIN = 160  # px: a computed headroom band lower than this holds no scene text
TRANSITIONS = ["cut", "whip", "fade", "flash", "slide"]
SOURCES = ["project", "local", "online", "generated"]  # online: only with the online add-on (reels_common.online())
STATUSES = ["planned", "ready", "pending", "skipped"]
GEN_FIELDS = ["subject", "action", "camera", "composition", "lighting", "mood", "start", "end"]  # the code-scene brief


def _ru(spec):
    """Russian words for the speech patterns below, written as Unicode code points so that this file stays plain
    English text. Words are separated by "|", letters by spaces, "_" is a space; any other item that is not a
    three-digit hex code point (regex syntax such as + or -) is copied as is."""
    return "|".join("".join(" " if t == "_" else chr(int(t, 16)) if re.fullmatch(r"4[0-9a-f]{2}", t) else t
                            for t in w.split()) for w in spec.split("|"))


_YO, _YE = chr(0x451), chr(0x435)  # Russian yo -> ye: both spellings match
_RU_AZ = _ru("430 - 44f")  # the Russian lowercase letters, for character classes

# Speech patterns for the span hints: English words, plus Russian ones written as code points (see _ru); the comment
# above each pattern glosses its Russian words. Add words of your speaker's language the same way.
# numbers: a number of its own (reels_common.NUMBER_RE: "12", "60%", "$100", not the digits of a name such as "ACME24"),
# one ... ten, hundred, two hundred, thousand*, million*, percent*, half*
NUM_RE = re.compile(NUMBER_RE.pattern + r"|\b(two|three|four|five|six|seven|eight|nine|ten|hundred\w*|thousand\w*|million\w*|percent\w*|"
                    r"half|halves|"
                    + _ru(r"43e 434 438 43d|43e 434 43d 430|434 432 430|434 432 435|442 440 438|447 435 442 44b 440 435|"
                          r"43f 44f 442 44c|448 435 441 442 44c|441 435 43c 44c|432 43e 441 435 43c 44c|"
                          r"434 435 432 44f 442 44c|434 435 441 44f 442 44c|441 442 43e|434 432 435 441 442 438|"
                          r"442 44b 441 44f 447 \w*|43c 438 43b 43b 438 43e 43d \w*|43f 440 43e 446 435 43d 442 \w*|"
                          r"43f 43e 43b 43e 432 438 43d \w*") + r")\b", re.I)
# pointing at an object: here, look, have a look, here (place), I'll show, I'm showing
POINT_RE = re.compile(r"\b(here|look|watch|show you|showing|"
                      + _ru(r"432 43e 442|441 43c 43e 442 440 438 442 435|43f 43e 441 43c 43e 442 440 438 442 435|"
                            r"437 434 435 441 44c|43f 43e 43a 430 436 443|43f 43e 43a 430 437 44b 432 430 44e")
                      + r")\b", re.I)
# emotion or irony: imagine, honestly, funny, horror*, nightmare, seriously (two spellings), suddenly, of course, well
EMO_RE = re.compile(r"!|\b(imagine|honestly|funny|horribl\w*|terribl\w*|awful|nightmare|seriously|suddenly|of course|"
                    r"wow|"
                    + _ru(r"43f 440 435 434 441 442 430 432 44c 442 435|447 435 441 442 43d 43e|441 43c 435 448 43d 43e|"
                          r"443 436 430 441 \w*|43a 43e 448 43c 430 440|441 435 440 44c 451 437 43d 43e|"
                          r"441 435 440 44c 435 437 43d 43e|432 43d 435 437 430 43f 43d 43e|43a 43e 43d 435 447 43d 43e|"
                          r"43d 443") + r")\b", re.I)
# More speech patterns: English, plus Russian as code points (see the note above NUM_RE).
# filler words at the start: well, so (two words), here, in short, listen, look, hi, hello, so, by the way, anyway,
# uh+, uhm+, m+
FILLER_RE = re.compile(r"^(so|well|okay|ok|like|you know|um+|uh+|er+|hm+|m+|anyway|basically|listen|look|hi|hey|hello|"
                       r"by the way|"
                       + _ru(r"43d 443|438 442 430 43a|442 430 43a|432 43e 442|43a 43e 440 43e 447 435|"
                             r"441 43b 443 448 430 439 442 435|441 43c 43e 442 440 438 442 435|43f 440 438 432 435 442|"
                             r"437 434 440 430 432 441 442 432 443 439 442 435|437 43d 430 447 438 442|43a 441 442 430 442 438|"
                             r"432 _ 43e 431 449 435 43c|44d +|44d 43c +|43c +") + r")\b", re.I)
# list markers: firstly (two spellings), secondly, thirdly, first, second, third
LIST_RE = re.compile(r"\b(first of all|firstly|secondly|thirdly|number one|step one|first(?=\s*,)|second(?=\s*,)|"
                     r"third(?=\s*,)|"
                     + _ru(r"432 43e - 43f 435 440 432 44b 445|432 43e _ 43f 435 440 432 44b 445|"
                           r"432 43e - 432 442 43e 440 44b 445|432 - 442 440 435 442 44c 438 445|43f 435 440 432 43e 435|"
                           r"432 442 43e 440 43e 435|442 440 435 442 44c 435") + r")\b", re.I)
# someone else's words: said*, says, they say, writes, they write, wrote*; or quotation marks
QUOTE_RE = re.compile(r"\b(said|says|tells|told|writes|wrote|"
                      + _ru(r"441 43a 430 437 430 43b \w*|433 43e 432 43e 440 438 442|433 43e 432 43e 440 44f 442|"
                            r"43f 438 448 435 442|43f 438 448 443 442|43d 430 43f 438 441 430 43b \w*")
                      + r")\b|[\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}\""
                        r"\N{LEFT DOUBLE QUOTATION MARK}\N{RIGHT DOUBLE QUOTATION MARK}]", re.I)
# the main thought: the main thing, the point, remember; that's why
SLOGAN_RE = re.compile(r"\b(the main thing|the point is|remember this|keep in mind|the bottom line|"
                       + _ru(r"433 43b 430 432 43d 43e 435|441 443 442 44c|437 430 43f 43e 43c 43d 438 442 435")
                       + r")\b|that['\N{RIGHT SINGLE QUOTATION MARK}]s why|this is why|" + _ru(r"432 43e 442 _ 43f 43e 447 435 43c 443"), re.I)
# a product interface: website*, app*, service*, bot*; in the profile
UI_RE = re.compile(r"\b(website\w*|sites?|apps?|application\w*|service\w*|bots?|"
                   + _ru(r"441 430 439 442 \w*|43f 440 438 43b 43e 436 435 43d 438 \w*|441 435 440 432 438 441 \w*|"
                         r"431 43e 442 \w*")
                   + r")\b|in (?:the|my|our) profile|link in (?:the )?bio|" + _ru(r"432 _ 43f 440 43e 444 438 43b 435"), re.I)
# a call to action: write (two forms), subscribe, save, leave, go to, press, put (a like)
CTA_RE = re.compile(r"\b(write|message|dm|comment|subscribe|follow|save|leave|click|tap|press|hit|head to|go to|"
                    + _ru(r"43d 430 43f 438 448 438 442 435|43f 438 448 438 442 435|43f 43e 434 43f 438 448 438 442 435 441 44c|"
                          r"441 43e 445 440 430 43d 438 442 435|43e 441 442 430 432 44c 442 435|"
                          r"43f 435 440 435 445 43e 434 438 442 435|436 43c 438 442 435|441 442 430 432 44c 442 435")
                    + r")\b", re.I)
# an abstract noun by its suffix
ABSTRACT_RE = re.compile(r"\b[a-z]{3,}(ness|ity|ities|tion|tions|sion|sions|ism|isms|ment|ments|ence|ance)\b|\b["
                         + _ru(r"430 - 44f 451") + r"]{3,}("
                         + _ru(r"43e 441 442 44c|43e 441 442 438|43d 438 435|43d 438 44f|446 438 44f|446 438 438|"
                               r"438 437 43c|441 442 432 43e|441 442 432 430") + r")\b", re.I)


def plan_path(e):
    return e / "visual_plan.json"


def load_plan(e):
    p = load_json(plan_path(e))
    if p is None:
        sys.exit(f"no plan: {plan_path(e)}; run visual_plan.py validate (a plain edit) or init (with inserts) first")
    return p


# what a rebuilt plan (init, init --force) keeps from the old one besides keep_clear: the last stage's hook, corner
# logo and end (review 2026-10-18: init after a stage lost them, the next stage dropped the card), the subtitle band
# the render has, the subtitles hidden by a per-video composition, the brand mascot (its pose track follows the words)
KEEP_ON_INIT = ("finish", "hook", "corner", "end_card", "subtitles_band", "hide_subtitles", "mascot")
# plan formats whose picture is designed scenes only (no footage): "scenes only" (a promo, no speech) and "scenes +
# voice" (a narration cut by cut.py into voice.wav: reel.json -> voice off_camera, subtitles from its words)
NO_FOOTAGE = ("scenes-only", "scenes-voice")
VOICE_MAX_S = 70  # s: a "scenes + voice" video longer than this may not render on an 8 GB laptop (SKILL.md section 15)


def no_footage(plan):
    """The plan's picture is designed scenes only: no rough cut on screen, no faces, camera or framed window."""
    return (plan or {}).get("format") in NO_FOOTAGE


def format_label(plan):
    return {"scenes-voice": "'scenes + voice'", "silent": "'no speech'"}.get((plan or {}).get("format"), "'scenes only'")


def ensure_plan(e):
    """No plan yet and inserts and designed scenes off: a plan without inserts is created on the spot (as keep-clear
    does), so a plain edit needs no `init` before validate, md or stage. Inserts or scenes on and no plan: still an
    error, since `init` is where they are planned."""
    s, prov, doc, bdir, brand = current_settings(e)
    eff, why = effective(s)
    inserts_on = eff.get("broll") or eff.get("memes") or s.get("use_scenes")
    old = load_json(plan_path(e)) if plan_path(e).is_file() else None
    if old is not None:
        if old.get("auto") and inserts_on:  # made by keep-clear or a plain edit, before inserts were turned on
            sys.exit(f"{plan_path(e)} was made without inserts and they are on now: run visual_plan.py init (it keeps "
                     f"keep_clear and the last stage's choices)")
        return
    if inserts_on:
        sys.exit(f"no plan: {plan_path(e)}; inserts or designed scenes are on, so run visual_plan.py init first")
    if not load_json(e / "captions.json"):  # review 2026-10-18: a plan without it staged "captions": null to the kit
        sys.exit(f"no {e / 'captions.json'}: the plan follows the rough cut, build it first (cut.py)")
    with locked(plan_path(e)):
        if load_json(plan_path(e)) is None:
            save_json(plan_path(e), auto_plan(e, load_json(e / "captions.json"), s, prov, doc))
            print(f"there was no plan: created {plan_path(e)} without inserts (inserts and scenes are off)")


def auto_plan(e, cap, s, prov, doc):
    """A plan without inserts made on the way (a plain edit, keep-clear before init), marked so that validate asks for
    init once inserts are turned on."""
    plan = build_plan(e, cap, s, prov, doc)
    plan["auto"] = True
    return plan


@contextlib.contextmanager
def editing_plan(e):
    """with editing_plan(e) as plan: ... the plan under a lock (parallel runs), written atomically.
    For footage.py / memes.py / codescene.py: keep only a quick edit inside, no downloads or renders."""
    with locked(plan_path(e)):
        plan = load_plan(e)
        yield plan
        save_json(plan_path(e), plan)


def snapshot(plan, s, prov, eff, why, doc):
    """A snapshot of the current settings in the plan (for md and for people). The source of truth is reel.json via
    load_config, not the snapshot. True: the snapshot changed."""
    new = {"brand": s["brand"], "settings": s, "provenance": prov, "effective": eff, "fallback": why,
           "budget": budget(plan.get("duration") or 0, s, doc)}
    changed = any(plan.get(k) != v for k, v in new.items())
    plan.update(new)
    return changed


def current_settings(e, plan=None):
    """The video's current settings: reel.json (+ brand, defaults). Older plans kept `init --set` only in the snapshot;
    such settings are moved to reel.json once, so that there is a single source of truth."""
    s, prov, doc, bdir, brand = load_config(e)
    old = (plan or {}).get("settings") or {}
    move = {k: v for k, v in old.items() if ((plan or {}).get("provenance") or {}).get(k) == "override"
            and prov.get(k) not in ("reel.json", "override") and s.get(k) != v}
    if move:
        with editing_json(e / "reel.json", {}) as reel:
            for k, v in move.items():
                reel.setdefault(k, v)
        warn("settings from `init --set` moved to reel.json: " + ", ".join(f"{k}={v}" for k, v in move.items()))
        s, prov, doc, bdir, brand = load_config(e)
    return s, prov, doc, bdir, brand


def refresh_plan(e):
    """After reelcfg.py save / brand.py use: refresh the settings snapshot in the plan, if there is a plan.
    True: refreshed."""
    with locked(plan_path(e)):
        plan = load_json(plan_path(e))
        if plan is None:
            return False
        s, prov, doc, bdir, brand = current_settings(e, plan)
        eff, why = effective(s)
        if not snapshot(plan, s, prov, eff, why, doc):
            return False
        save_json(plan_path(e), plan)
        return True


def plan_duration(e, plan):
    if plan.get("duration"):
        return float(plan["duration"])
    cap = load_json(e / "captions.json") or {}
    if cap.get("duration"):
        return float(cap["duration"])
    if (e / "final.mp4").exists():
        return probe(e / "final.mp4").get("dur")
    return None


def fmt_t(t):
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


def phrases(cap, lim):
    words = [w for w in cap.get("words", []) if str(w.get("text", "")).strip()]
    out, cur = [], []
    for k, w in enumerate(words):
        if cur:
            prev = cur[-1]
            gap = w["start"] - prev["end"]
            sentence = re.search(r"[.?!\N{HORIZONTAL ELLIPSIS}]$", prev["text"].strip())
            cut = w.get("seg") != prev.get("seg")
            too_long = w["end"] - cur[0]["start"] > lim["phrase_max_s"]
            if gap > lim["pause_split_s"] or sentence or (cut and gap > 0.12) or too_long:
                out.append(cur)
                cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    merged = []
    for ph in out:
        if merged and (ph[-1]["end"] - ph[0]["start"] < lim["phrase_min_s"] or
                       merged[-1][-1]["end"] - merged[-1][0]["start"] < lim["phrase_min_s"]) \
                and ph[-1]["end"] - merged[-1][0]["start"] <= lim["phrase_max_s"] + 1.0:
            merged[-1] = merged[-1] + ph
        else:
            merged.append(ph)
    return merged


def cut_id(cap):
    """Which rough cut: the length, the segment timeline and the word times (a re-cut of the same length counts)."""
    segs = [(g.get("source"), g.get("src_start"), g.get("src_end"), g.get("out_start"), g.get("out_dur"))
            for g in cap.get("segments", [])]
    words = [(w.get("text"), w.get("start"), w.get("end")) for w in cap.get("words", [])]
    return hashlib.sha1(repr((cap.get("duration"), segs, words)).encode()).hexdigest()[:12]


def build_plan(e, cap, s, prov, doc):
    """A plan from captions.json: spans by phrases, no inserts. cap=None: a minimal plan (keep_clear only), when cards
    are registered before the rough cut with subtitles, or without inserts."""
    eff, why = effective(s)
    lim = doc.get("limits", {})
    cap = cap or {}
    dur = float(cap["duration"]) if cap.get("duration") else plan_duration(e, {})
    # "hide the join" and "a long shot" are about the PICTURE (pic_track.py): where it jumps and how long it holds
    shots = pic_shots(cap)
    cut_starts = {round(g["out_start"], 2) for g in shots if (g.get("out_start") or 0) > 0.05}
    long_cuts = {g["i"]: g["out_dur"] for g in shots if (g.get("out_dur") or 0) > 6.0}
    plan_segs = []
    phs = phrases(cap, lim)
    for n, ph in enumerate(phs):
        start = 0.0 if n == 0 else round(ph[0]["start"], 3)
        end = round(phs[n + 1][0]["start"], 3) if n + 1 < len(phs) else round(dur or ph[-1]["end"], 3)
        text = " ".join(w["text"].strip() for w in ph)
        cuts = sorted({w.get("seg") for w in ph if w.get("seg") is not None})  # the sound segments of the phrase
        under = sorted(shots_of_words(ph, cap), key=lambda i: (i is None, i))  # the picture shots under it
        hints = []
        if any(start - 0.3 <= c <= start + 0.3 for c in cut_starts):
            hints.append("a segment join at the start: B-roll will hide the cut")
        for c in under:
            if c in long_cuts:
                hints.append(f"a {long_cuts[c]:.1f} s segment without a cut: room for a change of picture")
                break
        if NUM_RE.search(text):
            hints.append("a number -> a card works better than B-roll")
        if POINT_RE.search(text):
            hints.append("pointing at an object -> B-roll of the object, or a callout on it if the object is in the frame and the dot can stay on it: a still shot, or followed by track.py (experimental, references/callouts.md)")
        if EMO_RE.search(text):
            hints.append("emotion or irony: room for a meme, if memes are on")
        if n == 0:
            hints.append("hook: the first 1.5 s decide whether people keep watching")
        if dur and end >= dur - 3.0:
            hints.append("ending/CTA: no memes here")
        hints += scene_hints(n, len(phs), text, start, end, under, long_cuts)
        plan_segs.append({"id": f"s{n + 1:02d}", "start": start, "end": end, "text": text, "cut_segs": cuts,
                          "main": "main shot", "camera": "", "graphics": "", "hints": hints, "notes": ""})
    plan = {"schema": 1, "id": e.name, "created": datetime.datetime.now().isoformat(timespec="minutes"),
            "duration": dur, "segments": plan_segs, "inserts": [], "keep_clear": [],
            **({"captions_id": cut_id(cap)} if cap.get("words") is not None else {}),
            **({"picture_id": cap["picture_id"]} if cap.get("picture_id") else {})}  # pic_track.py: none for a copy
    snapshot(plan, s, prov, eff, why, doc)
    return plan


AND_RE = re.compile(r"\s(?:and|or|" + _ru("438|438 43b 438") + r")\s", re.I)  # and, or (Russian: i, ili)


def enumeration(text):
    """Three or more SHORT parts in a row (up to 3 words each), split at commas, semicolons, colons, dashes and a
    standalone "and"/"or": "patience, discipline and focus". Counting short parts anywhere caught clause commas (T2:
    "and now the other way round, recall a big deal, which you were sure, that you would close, but lost" - three
    short clauses, no list); in a list the short parts stand next to each other. A part needs a word of 4+ letters: a
    lone short word ("so" in "as at work, so in life", split at its "and") is a link, not an item (T4: that span got
    the list hint while the real list, set off by dashes - "this feeling - to feel people, understand their needs,
    find their pains - never left" - got none)."""
    parts = [x for x in re.split(r"[,;:—–]|\s-\s", AND_RE.sub(",", f" {text} ")) if x.strip()]
    run = best = 0
    for x in parts:
        words = [w for w in x.split() if re.search(r"\w", w)]
        run = run + 1 if words and len(words) <= 3 and any(len(re.sub(r"\W", "", w)) >= 4 for w in words) else 0
        best = max(best, run)
    return best >= 3


def scene_hints(n, total, text, start, end, cuts, long_cuts):
    """Hints for "a scene the video lacks" (references/scenes.md). A hint is not a decision: a scene has its own what
    and why."""
    out = []
    if n == 0 and (FILLER_RE.match(text.strip()) or (end - start > 2.0 and not NUM_RE.search(text) and "?" not in text)):
        out.append("scene:hook - a weak start (a filler word, or > 2 s without a number or a question) -> a hook scene")
    if NUM_RE.search(text):
        out.append("scene:stat - a number in the speech -> a stat scene (a source is required)")
    if LIST_RE.search(text) or enumeration(text):
        out.append("scene:list - an enumeration -> a list scene (items on their own words)")
    if QUOTE_RE.search(text):
        out.append("scene:quote - someone else's words -> a quote scene (verbatim, with a source)")
    if SLOGAN_RE.search(text):
        out.append("scene:slogan - the main thought -> a slogan scene (one per video)")
    if UI_RE.search(text):
        out.append("scene:ui - a website, service or bot is mentioned -> a ui scene (your own screenshots, fictional data; "
                   "experimental: offer it only when the product is shown)")
    if n == total - 1 and CTA_RE.search(text):
        out.append("scene:cta - a call to action with no action on screen -> a cta scene")
    if any(c in long_cuts for c in cuts) and ABSTRACT_RE.search(text):
        out.append("scene:word - a long segment with an abstraction -> a word scene (a weak hint; experimental)")
    return out


def resolve_at(at, plan, cap):
    if re.fullmatch(r"s\d+", at):
        seg = next((g for g in plan["segments"] if g["id"] == at), None)
        if not seg:
            sys.exit(f"no span {at}")
        return seg["start"]
    m = re.fullmatch(r"word:(.+?)(?:#(\d+))?", at)
    if m:
        target, nth = m.group(1).lower().replace(_YO, _YE), int(m.group(2) or 1)
        hits = [w for w in cap.get("words", [])
                if re.sub(r"[^\w" + _RU_AZ + "-]", "", w["text"].lower().replace(_YO, _YE)) == target]
        if len(hits) < nth:
            sys.exit(f"the word '{target}' occurs {len(hits)} time(s), #{nth} is needed")
        return round(hits[nth - 1]["start"], 3)
    # a no-speech reel (validate keeps the copies in the plan): a text block, a beat or a marker of the code music
    m = re.fullmatch(r"(block|beat|marker):(.+)", at)
    if m:
        kind, ref = m.groups()
        if kind == "block":
            b = next((x for x in plan.get("script_timing") or [] if x["id"] == ref), None)
            if not b:
                sys.exit(f"no text block {ref!r} in the plan (script.json timed, visual_plan.py validate copies it)")
            return round(b["start"], 3)
        music = plan.get("music") or {}
        if kind == "beat":
            beats = music.get("beats") or []
            if not ref.isdigit() or not 1 <= int(ref) <= len(beats):  # the n-th heard beat, from 1 (as word:...#n)
                sys.exit(f"beat:{ref}: the music has {len(beats)} heard beat(s), numbered from 1 (beats.json)")
            return round(beats[int(ref) - 1], 3)
        marks = music.get("markers") or {}
        if ref not in marks:
            sys.exit(f"marker:{ref}: the music's markers are {', '.join(marks) or 'none'} (beats.json)")
        return round(marks[ref], 3)
    return float(at)


def norm_words(text):
    """Words for matching a quote against the transcript: lowercase, Russian yo -> ye, no punctuation."""
    return [w for w in re.split(r"[^0-9a-z" + _RU_AZ + "]+", str(text or "").lower().replace(_YO, _YE)) if w]


def find_spoken(text, cap, near=None, window=None):
    """Where the words of text run in a row in captions.json -> ([(start of the first, end of the last), ...], how many
    words in a row matched at the best place). near: the nearest to this time first; window (t0, t1): only starts
    inside the window."""
    q = norm_words(text)
    words = [w for w in (cap or {}).get("words", []) if str(w.get("text", "")).strip()]
    toks = [(t, k) for k, w in enumerate(words) for t in norm_words(w["text"])]
    seq = [t for t, _ in toks]
    hits, best = [], 0
    for i in range(len(seq)):
        n = 0
        while n < len(q) and i + n < len(seq) and seq[i + n] == q[n]:
            n += 1
        best = max(best, n)
        if q and n == len(q):
            t0, t1 = words[toks[i][1]]["start"], words[toks[i + n - 1][1]]["end"]
            if window is None or window[0] - 1e-6 <= t0 <= window[1] + 1e-6:
                hits.append((t0, t1))
    if near is not None:
        hits.sort(key=lambda h: abs(h[0] - near))
    return hits, best


def near_match(text, cap):
    """How many words of text the speech has in the same order at its best place (a window a little longer than the
    text, so one word added or changed in the middle still counts the rest). find_spoken's run stops at the first
    difference: T1 reported "1 of 5 words matched" for a quote with one word changed."""
    q = norm_words(text)
    seq = [t for w in (cap or {}).get("words", []) for t in norm_words(w.get("text", ""))]

    def lcs(a, b):
        prev = [0] * (len(b) + 1)
        for x in a:
            cur = [0]
            for j, y in enumerate(b):
                cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
            prev = cur
        return prev[-1]
    return max((lcs(q, seq[i:i + len(q) + 2]) for i in range(len(seq))), default=0)


def is_inside(p, root):
    """p is inside root (after resolve), not by a string startswith: "edit/48" does not accept "edit/4821"."""
    try:
        Path(p).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def jround(x):
    """Math.round from JS (0.5 rounds up): frames are counted the same way as in the scene kit."""
    return int(math.floor(x + 0.5))


def item_time(it, plan, cap):
    if it.get("t") is not None:
        return float(it["t"])
    if it.get("at") is not None:
        return resolve_at(str(it["at"]), plan, cap)
    return None


def read_need(n, R):
    """Reading-time floor: up to 3 words need 0.8 s settled; more need 0.3 s per word, but at least 1.2 s."""
    return R.get("short_s", 0.8) if n <= R.get("short_words", 3) else max(R.get("min_s", 1.2), R.get("per_word_s", 0.3) * n)


END_CARD_S = 2.6  # the end card / logo sting the kit appends after the rough cut (stage --card / --sting)


def end_tail(a, plan):
    """Seconds the stage appends after the rough cut (an end card or a logo sting): "the last 2 s" count from the end
    of the whole video (T5: a stat scene ending 1.95 s before the end of a 25.0 s cut was flagged, while a 2.6 s sting
    followed and the video was 27.6 s). During stage: its --card/--sting/--no-end, else the last stage's choice
    (finish_of); validate takes --card/--sting before the stage, else what the last stage recorded ("end_card")."""
    if getattr(a, "sting", False) or getattr(a, "card", None):
        return END_CARD_S
    if getattr(a, "cmd", None) == "stage":
        return END_CARD_S if finish_of(a, plan)[0]["end"] else 0.0
    return float((plan.get("end_card") or {}).get("seconds") or 0.0)


WHY_OLD_FINISH = "a plan staged before 1.22 keeps it under an older name that this version does not read, one staged before 1.13 not at all"


def finish_of(a, plan):
    """What stage draws around the cut: the hook headline, the corner logo, the end card or the logo sting. A flag sets
    it, --no-hook/--no-corner/--no-end take it off, and with neither the last stage's choice stays (review 2026-10-17:
    a re-stage for a late fix dropped the approved hook and end card, and the missing card changed the video's length).
    -> ({"hook": text|None, "corner": bool, "end": {"kind": "card", "lines": [...]}|{"kind": "sting"}|None},
        notes for the person, names of what was kept from the last stage)."""
    last = dict(plan.get("finish") or {})
    notes = []
    preset = (plan.get("settings") or {}).get("finish")  # a series preset's finish (reelcfg.py preset use)
    legacy = plan.get("corner") or plan.get("end_card") or plan.get("hook")  # markers of a stage before 1.13
    rem, name = getattr(a, "remotion", None), getattr(a, "name", None) or plan.get("id")
    staged = bool(rem and name and (Path(rem) / "src" / "plans" / f"{name}.json").is_file())  # stage writes it each run
    if not last and not legacy and isinstance(preset, dict) and preset and staged:
        # staged before 1.22, which keeps the ending under another name: an ending switched off then left no marker, and
        # the preset would come back without a word (Codex review of 1.22, P1). This run's flags decide it, once
        if not (getattr(a, "corner", False) or getattr(a, "no_corner", False)):
            notes.append("this video was staged by an older version and its corner logo choice is not read: give "
                         "--corner or --no-corner")
        if not (getattr(a, "card", None) or getattr(a, "sting", False) or getattr(a, "no_end", False)):
            notes.append("this video was staged by an older version and its ending is not read: give --card, --sting "
                         "or --no-end")
    elif not last and not legacy and isinstance(preset, dict) and preset:  # only a video with no ending of its own
        last = {"hook": None, "corner": bool(preset.get("corner")), "end": preset.get("end")}
    elif not last:  # a plan staged before 1.22 (texts under an older name, not read) or before 1.13 (only markers):
        # the corner and a sting come back from the markers, texts cannot (review of 1.22: say why, not "not stored")
        if plan.get("corner"):
            last["corner"] = True
        kind = (plan.get("end_card") or {}).get("kind")
        if kind == "sting":
            last["end"] = {"kind": "sting"}
        elif kind == "card" and not (getattr(a, "card", None) or getattr(a, "sting", False) or getattr(a, "no_end", False)):
            notes.append("the last stage had an end card, but its lines are not read (" + WHY_OLD_FINISH + "): give --card "
                         "again (or --no-end)")
            last["end"] = {"kind": "card", "lines": None}  # still on: validate and this stage count its 2.6 s
        if plan.get("hook") and not (getattr(a, "hook", None) or getattr(a, "no_hook", False)):
            notes.append("the last stage had a hook headline, but its text is not read (" + WHY_OLD_FINISH + "): give --hook "
                         "again (or --no-hook)")
            last["hook"] = True
    kept = []
    if getattr(a, "no_hook", False):
        hook = None
    elif isinstance(getattr(a, "hook", None), str) and a.hook:
        hook = a.hook
    else:
        hook = last.get("hook")
        kept += ["hook"] if hook else []
    if getattr(a, "no_corner", False):
        corner = False
    elif getattr(a, "corner", False):
        corner = True
    else:
        corner = bool(last.get("corner"))
        kept += ["corner logo"] if corner else []
    card = getattr(a, "card", None)
    if getattr(a, "no_end", False):
        end = None
    elif isinstance(card, list) and card:
        end = {"kind": "card", "lines": list(card)}
    elif getattr(a, "sting", False):
        end = {"kind": "sting"}
    else:
        end = last.get("end")
        kept += [f"end ({end['kind']})"] if end else []
    return {"hook": hook, "corner": corner, "end": end}, notes, kept


def end_now(a, plan):
    """What follows the cut, whether the corner logo and the hook headline are drawn, for THIS run: stage's own
    --card/--sting/--corner/--hook, validate's flags, else what the last stage recorded (Codex review: a first stage
    --card was not counted, and a stage without a card after one with it still counted the old card). Stage keeps
    the last stage's choice unless a flag changes it (finish_of).
    -> (end kind or None, corner, hook)."""
    if getattr(a, "cmd", None) == "stage":
        fin = finish_of(a, plan)[0]
        return (fin["end"] or {}).get("kind"), fin["corner"], bool(fin["hook"])
    if getattr(a, "card", None):
        kind = "card"
    elif getattr(a, "sting", False):
        kind = "sting"
    else:
        kind = (plan.get("end_card") or {}).get("kind")
    # a standalone validate also trusts the last stage's record
    corner = bool(getattr(a, "corner", False)) or bool(plan.get("corner"))
    hook = bool(getattr(a, "hook", None)) or bool(plan.get("hook"))
    return kind, corner, hook


def overlap(a, b):
    return min(a["start"] + a["dur"], b["start"] + b["dur"]) - max(a["start"], b["start"])


_LIN = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (k / 1023 for k in range(1024))]


def srgb_lum(r, g, b):
    """Relative luminance of an sRGB color given as 0..1 channels (WCAG), through a 1024-step table."""
    return 0.2126 * _LIN[int(r * 1023 + 0.5)] + 0.7152 * _LIN[int(g * 1023 + 0.5)] + 0.0722 * _LIN[int(b * 1023 + 0.5)]
