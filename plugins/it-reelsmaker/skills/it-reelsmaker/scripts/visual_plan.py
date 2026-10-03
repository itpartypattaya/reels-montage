# -*- coding: utf-8 -*-
"""The visual plan of a video (step 7a): editing decisions kept apart from the render.

The plan is edit/<id>/visual_plan.json (+ visual_plan.md for the person). Spans are built from the phrases in
captions.json (the timeline of the finished rough cut); each has a timecode, the line, the main footage and hints.
Inserts (B-roll, memes) are a separate list: an insert may cover the join of two spans (that is how B-roll hides a cut).
The agent makes the decisions (what to show and why); the script computes the budget from the intensity, checks the
rules and hands the inserts over to Remotion.

    python scripts/visual_plan.py init edit/4821 [--set use_memes=true intensity=minimal] [--force]
    python scripts/visual_plan.py add  edit/4821 --kind broll --at "word:resume#1" --dur 1.6 \\
        --what "hands flipping through a printed resume" --why "illustrates the word, hides the s03/s04 cut" \\
        [--query "hands flipping resume paper"] [--source auto|project|local|generated] [--mode replace|window]
    python scripts/visual_plan.py add  edit/4821 --kind meme --at s07 --dur 1.2 --what "a statue shrugs" \\
        --why "irony about the 'perfect candidate'" --mode popup
    python scripts/visual_plan.py add  edit/4821 --kind scene --type quote --mode split --at "word:think#1" --dur 2.6 \\
        --lines "Test how they think," "not what they remember" [--accent think] [--label "NAME / ROLE"] [--source speech] \\
        [--tone calm] [--variant slam] [--items-json '[{"text":"...","at":"word:...#1"}]'] [--value-json '{"to":12}'] \\
        [--media inserts/ui-01.png] [--interaction-json '{"kind":"tap","target":[540,900],"at":"word:...#1"}'] \\
        [--box x,y,w,h] [--side left|right] [--sound card] [--hide-subtitles] --what "..." --why "..."
    python scripts/visual_plan.py init edit/promo1 --scenes-only --duration 22 [--brand acme]   # a promo without footage
    python scripts/visual_plan.py keep-clear edit/4821 --from 3.7 --to 9.6 --box 60,400,760,420 --what "price card"
    python scripts/visual_plan.py validate edit/4821        # errors -> exit code 1; warnings -> exit code 0
    python scripts/visual_plan.py md edit/4821              # visual_plan.md: show it to the person before the render
    python scripts/visual_plan.py export edit/4821 --remotion reels [--name 4821]

--at: a second on the timeline (5.2), a span (s03, its start) or a word (word:paint#1, the start of its nth occurrence).
Insert statuses: planned -> ready (the file is prepared) | pending (waiting for a code scene or for the person's
approval) | skipped (declined: the main footage stays, the reason is in fallback). Only ready inserts go into the
render; an unfilled code-scene brief (gen) on an insert that is not ready is a warning, not an error.
Settings come from edit/<id>/reel.json (reelcfg.py save); the plan holds only a snapshot, and validate refreshes it.
`init --set` saves the keys to reel.json. keep-clear without a plan creates a plan with no inserts (a graphics registry).
Coverage is the union of the intervals of all inserts (B-roll and memes, popups included); coverage and spacing are errors.
--source online (online footage and memes) needs the online-sources add-on it-reelsmaker-online; without it the online
source is unavailable.

Designed scenes (kind scene, ids c01...; references/scenes.md): types hook, quote, slogan, stat, list, contrast, word,
chat, ui, cta, cover; modes overlay, split, panel, window, full. A scene has no file: validate sets it to ready when its
fields are valid (an error -> planned). Checks: required fields and the mode for the type, the scene tone is one of the
brand's tones, the reading-time floor for the scene tone, a quote from the speech is verbatim per captions.json, a stat
has a source, contrast of the brand colors, coverage (full/split/panel/window together with B-roll), the
overlay/split/window box (face, safe zone, keep_clear), no two scenes at once, not over a meme, only cta in the last 2 s.
The brand tone's ceilings (memes, transitions, flash/whip, full) are errors; reel.json -> tone_override: true turns them
into warnings (going louder on explicit request, noted in the report). export --props writes props.scenes and adds the
overlay/split/window scenes to keep_clear (faces.py audit sees them).
The "scenes only" format (init --scenes-only --duration N): no speech spans, --at in seconds only, every scene is full,
scene coverage >= 95 %; export --props: video "", empty captions with the duration, subtitles none.
"""
import argparse, contextlib, datetime, filecmp, hashlib, json, math, re, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (MEME_SIZES, budget, edit_dir, editing_json, effective, forbidden_hits, inside, load_config,
                          load_json, locked, media_kind, online, parse_sets, probe, safe_slug, save_json, tokens,
                          utf8_stdio, warn)

SCENE_MODES = ["overlay", "split", "panel", "window", "full"]  # order = default preference (the face stays)
KINDS = {"broll": {"modes": ["replace", "window"], "prefix": "b"}, "meme": {"modes": ["popup", "cutaway"], "prefix": "m"},
         "scene": {"modes": SCENE_MODES, "prefix": "c"}}
# B-roll "window" (the Inserts component of the Remotion template): the box inserts[].box in 1080x1920 screen
# coordinates; without a box the template uses WINDOW_DEFAULT.
# Safe zone: right of x 960 are the UI buttons, above y 220 and below 1500 are the UI and the subtitles
WINDOW_DEFAULT = [60, 250, 900, 675]
WINDOW_ZONE = (0, 220, 960, 1500)
WINDOW_SLOTS = [WINDOW_DEFAULT, [60, 820, 900, 675]] + [[x, y, w, h] for w, h in ((600, 450), (480, 360))  # 4:3, larger -> smaller
                                                       for y in (250, 1500 - h) for x in (60, 960 - w - 60)]
TRANSITIONS = ["cut", "whip", "fade", "flash", "slide"]
SOURCES = ["project", "local", "online", "generated"]  # online: only with the online add-on (reels_common.online())
STATUSES = ["planned", "ready", "pending", "skipped"]
GEN_FIELDS = ["subject", "action", "camera", "composition", "lighting", "mood", "start", "end"]  # the code-scene brief


def _ru(spec):
    """Russian words for the speech patterns below, written as Unicode code points so that this file stays plain
    English text. Words are separated by "|", letters by spaces, "_" is a space; any other token that is not a
    three-digit hex code point (regex syntax such as + or -) is copied as is."""
    return "|".join("".join(" " if t == "_" else chr(int(t, 16)) if re.fullmatch(r"4[0-9a-f]{2}", t) else t
                            for t in w.split()) for w in spec.split("|"))


_YO, _YE = chr(0x451), chr(0x435)  # Russian yo -> ye: both spellings match
_RU_AZ = _ru("430 - 44f")  # the Russian lowercase letters, for character classes

# Speech patterns for the span hints: English words, plus Russian ones written as code points (see _ru); the comment
# above each pattern glosses its Russian words. Add words of your speaker's language the same way.
# numbers: one ... ten, hundred, two hundred, thousand*, million*, percent*, half*
NUM_RE = re.compile(r"\d|\b(two|three|four|five|six|seven|eight|nine|ten|hundred\w*|thousand\w*|million\w*|percent\w*|"
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

# --- Designed scenes ---------------------------------------------------------------------------------------
# need: lines = text.lines; variant = one of variants; source; value; items; media; interaction
SCENE_TYPES = {
    "hook": {"modes": ["overlay", "split", "full"], "need": ["lines", "variant"], "variants": ["slam", "type", "stack", "counter"]},
    "quote": {"modes": ["overlay", "split", "full"], "need": ["lines", "source"]},
    "slogan": {"modes": ["full", "split"], "need": ["lines"]},
    "stat": {"modes": ["overlay", "split", "full"], "need": ["value", "lines", "source"]},
    "list": {"modes": ["panel", "split", "full"], "need": ["items"]},
    "contrast": {"modes": ["overlay", "split", "full"], "need": ["lines"]},
    "word": {"modes": ["overlay", "split", "panel"], "need": ["lines"], "variants": ["grid-pick", "funnel", "timeline", "icon"]},
    "chat": {"modes": ["split", "full", "window"], "need": ["items"]},
    "ui": {"modes": ["split", "full", "window"], "need": ["media", "interaction"]},
    "cta": {"modes": ["overlay", "full"], "need": ["lines"], "variants": ["tap", "comment", "bio"]},
    "cover": {"modes": ["full"], "need": ["lines"]},
}
SCENE_SOURCES = ["speech", "brief", "brand", "client", "agent"]
SCENE_SOUNDS = ["card", "type", "tap", "hit", "paper", "none"]
CHAT_FROM = ["me", "them", "system"]
INTERACTIONS = ["tap", "type", "cursor", "swipe"]
COVER_MODES = ("full", "split", "panel", "window")  # scenes that cover the speaker's frame: they count toward coverage
SPLIT_BOX = [60, 220, 900, 660]          # split: the scene on top, y 220-880
SPLIT_CAM = [0.56, 540.0, 107.143]       # split: the speaker x0.56 centered, top of the video at y 900: the "camera" for the rough cut's faces
WINDOW_SCENE_BOX = [60, 250, 900, 700]   # window: the scene content above the speaker's window
SPEAKER_WINDOW = {"left": [40, 1000, 360, 480], "right": [600, 1000, 360, 480]}  # the speaker's 360x480 window (Presenter in the scene kit)
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
        sys.exit(f"no plan: {plan_path(e)}; run visual_plan.py init first")
    return p


@contextlib.contextmanager
def editing_plan(e):
    """with editing_plan(e) as plan: ... the plan under a lock (parallel sessions), written atomically.
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
    such keys are moved to reel.json once, so that there is a single source of truth."""
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
    segs = cap.get("segments", [])
    cut_starts = {round(g["out_start"], 2) for g in segs if g.get("out_start", 0) > 0.05}
    long_cuts = {g["i"]: g["out_dur"] for g in segs if g.get("out_dur", 0) > 6.0}
    plan_segs = []
    phs = phrases(cap, lim)
    for n, ph in enumerate(phs):
        start = 0.0 if n == 0 else round(ph[0]["start"], 3)
        end = round(phs[n + 1][0]["start"], 3) if n + 1 < len(phs) else round(dur or ph[-1]["end"], 3)
        text = " ".join(w["text"].strip() for w in ph)
        cuts = sorted({w.get("seg") for w in ph if w.get("seg") is not None})
        hints = []
        if any(start - 0.3 <= c <= start + 0.3 for c in cut_starts):
            hints.append("a segment join at the start: B-roll will hide the cut")
        for c in cuts:
            if c in long_cuts:
                hints.append(f"a {long_cuts[c]:.1f} s segment without a cut: room for a change of picture")
                break
        if NUM_RE.search(text):
            hints.append("a number -> a card works better than B-roll")
        if POINT_RE.search(text):
            hints.append("pointing at an object -> B-roll of the object")
        if EMO_RE.search(text):
            hints.append("emotion or irony: room for a meme, if memes are on")
        if n == 0:
            hints.append("hook: the first 1.5 s decide whether people keep watching")
        if dur and end >= dur - 3.0:
            hints.append("ending/CTA: no memes here")
        hints += scene_hints(n, len(phs), text, start, end, cuts, long_cuts)
        plan_segs.append({"id": f"s{n + 1:02d}", "start": start, "end": end, "text": text, "cut_segs": cuts,
                          "main": "main shot", "camera": "", "graphics": "", "hints": hints, "notes": ""})
    plan = {"schema": 1, "id": e.name, "created": datetime.datetime.now().isoformat(timespec="minutes"),
            "duration": dur, "segments": plan_segs, "inserts": [], "keep_clear": [],
            **({"captions_id": cut_id(cap)} if cap.get("words") is not None else {})}
    snapshot(plan, s, prov, eff, why, doc)
    return plan


def scene_hints(n, total, text, start, end, cuts, long_cuts):
    """Hints for "a scene the video lacks" (references/scenes.md). A hint is not a decision: a scene has its own what
    and why."""
    out = []
    if n == 0 and (FILLER_RE.match(text.strip()) or (end - start > 2.0 and not NUM_RE.search(text) and "?" not in text)):
        out.append("scene:hook - a weak start (a filler word, or > 2 s without a number or a question) -> a hook scene")
    if NUM_RE.search(text):
        out.append("scene:stat - a number in the speech -> a stat scene (a source is required)")
    parts = [x for x in re.split(r"[,;]", text) if x.strip()]
    if LIST_RE.search(text) or (len(parts) >= 3 and sum(1 for x in parts if len(x.split()) <= 3) >= 3):
        out.append("scene:list - an enumeration -> a list scene (items on their own words)")
    if QUOTE_RE.search(text):
        out.append("scene:quote - someone else's words -> a quote scene (verbatim, with a source)")
    if SLOGAN_RE.search(text):
        out.append("scene:slogan - the main thought -> a slogan scene (one per video)")
    if UI_RE.search(text):
        out.append("scene:ui - a website, service or bot is mentioned -> a ui scene (your own screenshots, fictional data)")
    if n == total - 1 and CTA_RE.search(text):
        out.append("scene:cta - a call to action with no action on screen -> a cta scene")
    if any(c in long_cuts for c in cuts) and ABSTRACT_RE.search(text):
        out.append("scene:word - a long segment with an abstraction -> a word scene (a weak hint)")
    return out


def cmd_init(a):
    if a.scenes_only:
        return init_scenes_only(a)
    e = edit_dir(a.edit)
    cap = load_json(e / "captions.json")
    if not cap:
        sys.exit(f"no {e / 'captions.json'}: the visual plan is built after the rough cut (step 6)")
    over = parse_sets(a.set)
    if a.brand:
        over["brand"] = safe_slug(a.brand, "--brand")
    with locked(plan_path(e)):
        old = load_json(plan_path(e))
        if old and old.get("inserts") and not a.force:
            sys.exit(f"the plan already exists: {plan_path(e)} (--force rebuilds it; the inserts are lost, keep_clear stays)")
        if over:  # the single source of settings is reel.json: --set is saved there, not only in the plan's snapshot
            with editing_json(e / "reel.json", {}) as reel:
                reel.update(over)
            print(f"{e / 'reel.json'}: " + ", ".join(f"{k}={v}" for k, v in over.items()))
        s, prov, doc, bdir, brand = current_settings(e, old)
        plan = build_plan(e, cap, s, prov, doc)
        plan["keep_clear"] = (old or {}).get("keep_clear", [])
        save_json(plan_path(e), plan)
    eff, why, dur = plan["effective"], plan["fallback"], plan["duration"]
    print(f"plan: {plan_path(e)}: {len(plan['segments'])} spans, {fmt_t(dur)}"
          + (f"; keep_clear kept ({len(plan['keep_clear'])})" if plan["keep_clear"] else ""))
    b = plan["budget"]
    if not eff.get("broll") and not eff.get("memes"):
        print("inserts are off: the plan has only the main footage (the edit runs as without inserts)")
    else:
        print(f"budget ({s['intensity']}): up to {b['broll_max'] if eff.get('broll') else 0} B-roll, "
              f"up to {b.get('memes_max', 0) if eff.get('memes') else 0} memes, inserts <= {b['coverage_max_s']} s in total, "
              f">= {b.get('min_gap_s')} s between inserts. This is a ceiling, not a target.")
    for k, r in why.items():
        if r != "off" and k in ("online_footage", "generate_now", "online_memes") and s.get({"online_footage": "use_online_footage",
                                                                                         "generate_now": "generate_now",
                                                                                         "online_memes": "use_online_memes"}[k]):
            print(f"  fallback: {k} - {r}")


def init_scenes_only(a):
    """A promo without footage: a plan with no speech spans, scenes at absolute times; captions.json is not needed."""
    e = edit_dir(a.edit, create=True)
    if not a.duration or a.duration <= 0:
        sys.exit("--scenes-only needs --duration in seconds (15-25, best 18-22)")
    over = parse_sets(a.set)
    if a.brand:
        over["brand"] = safe_slug(a.brand, "--brand")
    with locked(plan_path(e)):
        old = load_json(plan_path(e))
        if old and old.get("inserts") and not a.force:
            sys.exit(f"the plan already exists: {plan_path(e)} (--force rebuilds it; the inserts are lost)")
        if over:
            with editing_json(e / "reel.json", {}) as reel:
                reel.update(over)
            print(f"{e / 'reel.json'}: " + ", ".join(f"{k}={v}" for k, v in over.items()))
        s, prov, doc, bdir, brand = current_settings(e, old)
        plan = build_plan(e, {"duration": round(float(a.duration), 3), "segments": [], "words": []}, s, prov, doc)
        plan["format"] = "scenes-only"
        save_json(plan_path(e), plan)
    so = (doc.get("scenes") or {}).get("scenes_only") or {}
    lo, hi = so.get("duration", [15, 25])
    print(f"'scenes only' plan: {plan_path(e)}: {fmt_t(plan['duration'])}, brand {s['brand']}, scene tone {s.get('scene_tone')}")
    if not lo <= plan["duration"] <= hi:
        warn(f"length {plan['duration']} s is outside {lo}-{hi} s (best {'-'.join(map(str, so.get('optimum', [18, 22])))} s)")
    print("storyboard: hook 2-3 s -> reveal 2-4 s -> 2-3 strong moments -> punchline/cta 2-4 s; scenes back to back "
          "(coverage >= 95 %), all in full mode, --at in seconds (3.0)")


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
    return float(at)


def window_issues(e, plan, ins, box, fdata=None):
    """Problems with a window box: the safe zone, the face (faces.json through the insert's camera, with MARGIN),
    keep_clear."""
    import faces as fc
    x0, y0, x1, y1 = WINDOW_ZONE
    x, y, w, h = box
    out = []
    if x < x0 or y < y0 or x + w > x1 or y + h > y1:
        out.append(f"window {box} leaves the safe zone x {x0}-{x1}, y {y0}-{y1}")
    t0, t1 = ins["start"], ins["start"] + ins["dur"]
    faces_ = [fc.cam_box(b, ins.get("cam")) for b in fc.between(fdata if fdata is not None else fc.load(e), t0, t1)]
    hit = [f for f in faces_ if fc.inter(box, fc.grow(f, fc.MARGIN))]
    if hit:
        out.append(f"window {box} covers the face {fc.union(hit)} (margin {fc.MARGIN} px, "
                   + ("with the camera)" if ins.get("cam") else "without a camera: if the span has a push-in, add ... --cam z,cx,cy)"))
    for k in plan.get("keep_clear", []):
        if k["start"] < t1 and k["end"] > t0 and fc.inter(box, k["box"]):
            out.append(f"the window covers '{k.get('what', 'graphics')}' {k['box']}")
    return out


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


def layout_frames(tr, T, way):
    """Frames of a layout change, as layoutFrames in the scene kit (kit/scenes/tones.ts)."""
    if tr == "cut":
        return 0
    if tr == "flash":
        return 3
    if tr == "whip":
        return 5
    return min(14, max(8, T.get("in", 14))) if way == "in" else min(10, max(6, T.get("out", 9)))


def scene_timeline(sc, T, mode, fps, words):
    """Frames of a scene from its start, as sceneTimeline in the scene kit (kit/scenes/tones.ts): a smooth transition
    over a pause becomes a cut ("over a pause, a hard cut"), lead/tail are 0.6 of the layout change (except overlay)."""
    n = max(1, jround(sc["dur"] * fps))
    tin = sc.get("transition_in") or T.get("transition", "cut")
    tout = sc.get("transition_out") or T.get("transition", "cut")
    if words:
        a, b = sc["start"], sc["start"] + sc["dur"]
        speaking = lambda t0, t1: any(w["start"] < t1 and w["end"] > t0 for w in words)
        if tin in ("fade", "slide", "whip") and not speaking(a, a + layout_frames(tin, T, "in") / fps):
            tin = "cut"
        if tout in ("fade", "slide", "whip") and not speaking(b - layout_frames(tout, T, "out") / fps, b):
            tout = "cut"
    lay = mode != "overlay"
    lead = jround(0.6 * layout_frames(tin, T, "in")) if lay else 0
    tail = jround(0.6 * layout_frames(tout, T, "out")) if lay else 0
    inF, outF = T.get("in", 14), T.get("out", 9)
    return {"n": n, "lead": lead, "tail": tail, "inF": inF, "outF": outF, "settle_to": n - tail - outF,
            "tin": tin, "tout": tout}


def word_times(toks, words, t0, t1):
    """As wordTimes in the scene kit (kit/scenes/parts.tsx): each word of the scene is the first identical spoken word
    after the previous one, only within the scene's window (t0 - 0.3 ... t1). -> [second or None]."""
    ws = [(t, w["start"]) for w in words if t0 - 0.3 <= w["start"] <= t1 for t in norm_words(w.get("text", ""))]
    j, out = 0, []
    for tok in toks:
        q = (norm_words(tok) or [""])[0]
        hit = None
        for i in range(j, len(ws)):
            if ws[i][0] == q:
                j, hit = i + 1, ws[i][1]
                break
        out.append(hit)
    return out


def text_full_on(sc, typ, lines, tl, fps, words):
    """The frame (from the scene start) when the whole scene text is on screen and the entrance is over, as the scene
    kit draws it (kit/scenes/*.tsx): lines with a stagger, the typed hook, the number counter, the slogan and stack
    words on their spoken words, the second line of contrast."""
    lead, inF, nl = tl["lead"], tl["inF"], max(1, len(lines))
    stagger = 2 if inF <= 8 else 4
    var = sc.get("variant") or "slam"

    def by_words(toks, step):
        own = word_times(toks, words, sc["start"], sc["start"] + sc["dur"])
        last = lead
        for k, t in enumerate(own):
            last = max(last, lead + k * step if t is None else jround((t - sc["start"]) * fps))
        return last + inF

    if typ == "hook":
        if var == "type":
            return lead + max(inF, min(sum(len(x) for x in lines) * 1.5, 30))
        if var == "counter":
            return max(lead + max(inF, 24), lead + 6 + (nl - 1) * stagger + inF)
        if var == "stack":
            return by_words(" ".join(lines).split(), max(4, jround(inF * 0.6)))
        return lead + (nl - 1) * stagger + inF
    if typ == "slogan":
        flat = " ".join(lines).split()
        return by_words(flat, max(4, min(10, jround(tl["n"] * 0.3 / max(1, len(flat))))))
    if typ == "quote":
        return lead + 3 + (nl - 1) * 4 + inF
    if typ == "stat":
        return max(lead + max(inF, 24), lead + 8 + (nl - 1) * 4 + inF)
    if typ == "cta":
        return lead + (nl - 1) * 4 + inF
    if typ == "word":
        return lead + 10 + (nl - 1) * 4 + inF
    if typ == "contrast" and len(lines) == 2:
        own = word_times(lines[0].split() + lines[1].split(), words, sc["start"], sc["start"] + sc["dur"])
        t2 = own[len(lines[0].split())]
        if t2 is None:
            it = (sc.get("items") or [None, None])[1] if len(sc.get("items") or []) > 1 else None
            t2 = it.get("t") if isinstance(it, dict) and isinstance(it.get("t"), (int, float)) else None
        read = max(jround(0.6 * fps), jround(0.35 * (tl["settle_to"] - lead - inF)))
        f2 = max(lead + inF + 6, jround((t2 - sc["start"]) * fps) if t2 is not None else lead + inF + read)
        return f2 + inF
    return lead + inF


def scene_tone(sc, s):
    bt = s.get("brand_tone") or {}
    return sc.get("tone") or s.get("scene_tone") or bt.get("scene_tone") or "calm"


def default_box(mode):
    return {"overlay": WINDOW_DEFAULT, "split": SPLIT_BOX, "window": WINDOW_SCENE_BOX}.get(mode)


def hides_subtitles(sc):
    """Subtitles are hidden (as in SceneLayer of the scene kit): split/panel/window/full and slogan always; hook and
    quote by default (the scene text repeats the speech) unless hide_subtitles=false is explicit; the rest per
    hide_subtitles."""
    if sc.get("mode") in ("split", "panel", "window", "full") or sc.get("type") == "slogan":
        return True
    if sc.get("type") in ("hook", "quote") and sc.get("hide_subtitles") is not False:
        return True
    return bool(sc.get("hide_subtitles"))


def without_own(plan, sc):
    """The plan for checking a scene box: without the scene's own keep_clear entry (export writes it)."""
    return {**plan, "keep_clear": [k for k in plan.get("keep_clear", []) if k.get("scene") != sc.get("id")]}


def scene_box_issues(e, plan, sc, box, fdata=None):
    """The box of an overlay/split/window scene: safe zone, face, keep_clear, as for a B-roll window (window_issues).
    split: the rough cut's faces are recomputed as for the speaker at x0.56 at the bottom (SPLIT_CAM); window: the
    rough cut is not visible on screen, so the speaker's window (SPEAKER_WINDOW) is checked: the scene must not cover it."""
    import faces as fc
    mode = sc.get("mode")
    p = without_own(plan, sc)
    if mode != "window":
        probe_ = dict(sc)
        if mode == "split":
            probe_["cam"] = SPLIT_CAM
        return window_issues(e, p, probe_, box, fdata)
    x0, y0, x1, y1 = WINDOW_ZONE
    x, y, w, h = box
    out = []
    if x < x0 or y < y0 or x + w > x1 or y + h > y1:
        out.append(f"box {box} leaves the safe zone x {x0}-{x1}, y {y0}-{y1}")
    win = SPEAKER_WINDOW.get(sc.get("side") or "right", SPEAKER_WINDOW["right"])  # as speakerTarget in the kit: right by default
    if fc.inter(box, win):
        out.append(f"box {box} covers the speaker's window {win} (the face must stay visible)")
    t0, t1 = sc["start"], sc["start"] + sc["dur"]
    for k in p.get("keep_clear", []):
        if k["start"] < t1 and k["end"] > t0 and fc.inter(box, k["box"]):
            out.append(f"the box covers '{k.get('what', 'graphics')}' {k['box']}")
    return out


def scene_keep_entries(plan):
    """keep_clear entries for ready overlay/split/window scenes: the box in screen coordinates (for faces.py audit)."""
    out = []
    for sc in plan.get("inserts", []):
        if sc.get("kind") != "scene" or sc.get("status") != "ready" or sc.get("type") == "cover":
            continue
        mode = sc.get("mode")
        if mode not in ("overlay", "split", "window") or plan.get("format") == "scenes-only":
            continue
        k = {"start": sc["start"], "end": round(sc["start"] + sc["dur"], 3), "box": sc.get("box") or default_box(mode),
             "what": f"scene {sc['id']} {sc.get('type')} ({mode})", "scene": sc["id"], "mode": mode}
        if mode == "split":
            k["cam"] = SPLIT_CAM
        elif mode == "overlay" and sc.get("cam"):
            k["cam"] = sc["cam"]
        out.append(k)
    return out


def item_time(it, plan, cap):
    if it.get("t") is not None:
        return float(it["t"])
    if it.get("at") is not None:
        return resolve_at(str(it["at"]), plan, cap)
    return None


def add_scene(a):
    e = edit_dir(a.edit)
    cap = load_json(e / "captions.json", {})
    if not a.type:
        sys.exit("scene: --type is required (" + ", ".join(SCENE_TYPES) + ")")
    spec = SCENE_TYPES[a.type]

    def js(v, what):
        if v is None:
            return None
        try:
            return json.loads(v)
        except Exception as x:
            sys.exit(f"{what}: not JSON ({x})")
    items, value, inter = js(a.items_json, "--items-json"), js(a.value_json, "--value-json"), js(a.interaction_json, "--interaction-json")
    if a.source not in SCENE_SOURCES + ["auto"]:
        sys.exit(f"scene: --source is where the text comes from ({', '.join(SCENE_SOURCES)}), not {a.source}")
    media = None
    if a.media:
        mp = Path(a.media) if Path(a.media).is_absolute() else (e / a.media if (e / a.media).exists() else Path(a.media))
        if mp.exists() and not is_inside(mp, e):  # someone else's file -> a copy in inserts/; a different file with the same name is not overwritten
            dst_dir = e / "inserts"
            dst_dir.mkdir(parents=True, exist_ok=True)
            k, dst = 1, dst_dir / mp.name
            while dst.exists() and not filecmp.cmp(mp, dst, shallow=False):
                k += 1
                dst = dst_dir / f"{mp.stem}-{k}{mp.suffix}"
            if not dst.exists():
                shutil.copy2(mp, dst)
            mp = dst
            print(f"scene media -> {mp}")
        rel_ = mp.resolve().relative_to(e.resolve()).as_posix() if mp.exists() else a.media
        media = {"file": rel_, "kind": "video" if media_kind(rel_) == "video" else "image"}
    with editing_plan(e) as plan:
        only = plan.get("format") == "scenes-only"
        if only and not re.fullmatch(r"-?\d+(\.\d+)?", a.at.strip()):
            sys.exit("'scenes only' format: there is no speech, so --at is in seconds only (3.0)")
        s, prov, doc, bdir, brand = current_settings(e, plan)
        start = round(resolve_at(a.at, plan, cap) + a.offset, 3)
        mode = a.mode or ("full" if only else next(m for m in SCENE_MODES if m in spec["modes"]))
        if mode not in SCENE_MODES:
            sys.exit(f"scene mode {mode}: allowed {', '.join(SCENE_MODES)}")
        for it in items or []:  # item times: by spoken words (or seconds)
            if isinstance(it, dict) and it.get("t") is None and it.get("at") is not None:
                if only and str(it["at"]).startswith("word:"):
                    sys.exit("'scenes only' format: an item's at is in seconds only")
                it["t"] = round(item_time(it, plan, cap), 3)
        if isinstance(inter, dict) and inter.get("t") is None and inter.get("at") is not None:
            inter["t"] = round(item_time(inter, plan, cap), 3)
        tone = a.tone or scene_tone({}, s)
        tr_default = ((doc.get("scene_tones") or {}).get(tone) or {}).get("transition", "cut")
        tr_in = a.transition or tr_default
        n = 1 + max([int(i["id"][1:]) for i in plan["inserts"] if i["id"].startswith("c") and i["id"][1:].isdigit()] or [0])
        seg = next((g for g in plan["segments"] if g["start"] <= start < g["end"]), None)
        sc = {"id": f"c{n:02d}", "kind": "scene", "type": a.type, "mode": mode, "variant": a.variant,
              "segment": seg["id"] if seg else None, "start": start, "dur": a.dur, "at": a.at, **({"offset": a.offset} if a.offset else {}), "tone": a.tone,
              "text": {"lines": a.lines or [], "accent": a.accent, "label": a.label},
              "items": items, "value": value, "media": media, "interaction": inter,
              "box": [int(float(x)) for x in a.box.split(",")] if a.box else None, "side": a.side,
              "source": {"kind": a.source, "ref": a.source_ref} if a.source in SCENE_SOURCES else None,
              "what": a.what, "why": a.why, "transition_in": tr_in, "transition_out": a.transition_out or tr_in,
              "sound": a.sound, "hide_subtitles": bool(a.hide_subtitles) or mode in ("split", "panel", "window", "full") or a.type in ("slogan", "hook", "quote"),
              "status": "planned", "fallback": "main footage"}
        if a.type == "cover" and a.frame_at is not None:
            sc["frame_at"] = round(a.frame_at, 3)  # the video second under the cover (the cover composition, export -> cover.frameAt)
        if a.cam:
            sc["cam"] = [float(x) for x in a.cam.split(",")]
        if not only and mode in ("overlay", "split", "window") and sc["box"] is None:
            if mode == "overlay":  # the first free slot, as for a B-roll window
                sc["box"] = next((b for b in WINDOW_SLOTS if not scene_box_issues(e, plan, sc, b)), WINDOW_DEFAULT)
            else:
                sc["box"] = default_box(mode)
        if sc["box"] and not only and mode in ("overlay", "split", "window"):
            for m in scene_box_issues(e, plan, sc, sc["box"]):
                warn(f"{sc['id']}: {m}: validate will not pass it; set --box or move the scene")
        plan["inserts"].append(sc)
        plan["inserts"].sort(key=lambda i: i["start"])
    print(f"{sc['id']}: scene {a.type} {mode} {fmt_t(start)} +{a.dur} s ({sc['segment'] or '-'}), tone {tone}, "
          f"transition {sc['transition_in']}/{sc['transition_out']}: {a.what}"
          + (f"; box {sc['box']}" if sc.get("box") else "") + ". Status planned -> ready after validate.")


def read_need(n, R):
    """Reading-time floor: up to 3 words need 0.8 s settled; more need 0.3 s per word, but at least 1.2 s."""
    return R.get("short_s", 0.8) if n <= R.get("short_words", 3) else max(R.get("min_s", 1.2), R.get("per_word_s", 0.3) * n)


def check_scenes(e, plan, s, doc, brand, fdata, cap, scenes, brolls, memes):
    """Scene checks (references/scenes.md, the plan check). -> (errors, warnings, ids of scenes with errors)."""
    errs, warns, bad = [], [], set()
    if not [x for x in scenes if x.get("type") != "cover"]:
        if plan.get("format") == "scenes-only":
            errs.append("'scenes only': the plan has no scenes; the video would be an empty frame in the brand color")
        if not scenes:
            return errs, warns, bad
    import faces as fc
    import meme_layout as ml
    conf = doc.get("scenes") or {}
    R = conf.get("reading") or {}
    fps = conf.get("fps", 30)
    only = plan.get("format") == "scenes-only"
    D = plan.get("duration") or 0.0
    tones = {k: v for k, v in (doc.get("scene_tones") or {}).items() if not k.startswith("_")}
    band = ml.layout(s, doc).get("subtitles_band", [1250, 1430])
    words_ok = bool((cap or {}).get("words"))

    def E(sc, msg):
        errs.append(f"{sc['id']}: {msg}")
        bad.add(sc["id"])

    def W(sc, msg):
        warns.append(f"{sc['id']}: {msg}")

    settled = {}
    for sc in scenes:
        typ, mode = sc.get("type"), sc.get("mode")
        spec = SCENE_TYPES.get(typ)
        if not spec:
            E(sc, f"unknown scene type {typ!r} (allowed: {', '.join(SCENE_TYPES)})")
            continue
        if sc.get("status") not in STATUSES:
            E(sc, f"status {sc.get('status')} (must be one of {STATUSES})")
        # 1. mode, required fields, scene tone
        if mode not in SCENE_MODES:
            E(sc, f"mode {mode} (allowed: {', '.join(SCENE_MODES)})")
        elif only and mode != "full":
            E(sc, f"'scenes only' format: there is no speaker, so the mode is full only, not {mode}")
        elif not only and mode not in spec["modes"]:
            E(sc, f"mode {mode} is not for {typ} (allowed: {', '.join(spec['modes'])})")
        text = sc.get("text") or {}
        lines = [str(x) for x in (text.get("lines") or []) if str(x).strip()]
        if "lines" in spec["need"] and not lines:
            E(sc, "no text (text.lines)")
        variants = spec.get("variants")
        if "variant" in spec["need"] and sc.get("variant") not in variants:
            E(sc, f"variant required: {', '.join(variants)} (now {sc.get('variant')})")
        elif sc.get("variant") and variants and sc["variant"] not in variants:
            E(sc, f"variant {sc['variant']} is not for {typ} (allowed: {', '.join(variants)})")
        src = sc.get("source") or {}
        if "source" in spec["need"] and not src.get("kind"):
            E(sc, "no source (source: speech|brief|brand|client|agent): where the text or number comes from")
        elif src.get("kind") and src["kind"] not in SCENE_SOURCES:
            E(sc, f"source {src['kind']} (allowed: {', '.join(SCENE_SOURCES)})")
        if typ == "stat":
            v = sc.get("value") or {}
            num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
            if not num(v.get("to")) or (v.get("from") is not None and not num(v["from"])):
                E(sc, "no number: value {from, to, prefix, suffix, decimals}, with to as a number")
            dec = v.get("decimals")
            if dec is not None and not (isinstance(dec, int) and not isinstance(dec, bool) and 0 <= dec <= 4):
                E(sc, f"value.decimals {dec!r}: an integer 0-4 (digits after the decimal point)")
            for k in ("prefix", "suffix"):
                if v.get(k) is not None and not isinstance(v[k], str):
                    E(sc, f"value.{k}: a string, not {type(v[k]).__name__}")
        if typ == "hook" and len(norm_words(" ".join(lines))) > 6:
            E(sc, f"hook of {len(norm_words(' '.join(lines)))} words > 6: a hook is 2-6 words (longer: quote or slogan)")
        items = sc.get("items") or []
        times = []
        need_items = "items" in spec["need"]
        if need_items and len(items) < 2:
            E(sc, f"{len(items)} item(s): at least 2 are needed (items)")
        for k, it in enumerate(items):  # items are checked for any scene: export writes their times for the kit
            if not isinstance(it, dict):
                E(sc, f"item {k + 1}: not an object")
                continue
            if typ != "contrast" and not str(it.get("text", "")).strip():  # for contrast an item is only the time of the second line
                E(sc, f"item {k + 1}: no text")
                continue
            try:
                t = item_time(it, plan, cap)
            except SystemExit as x:
                E(sc, f"item {k + 1}: {x}")
                t = None
            if t is None:
                if need_items:
                    E(sc, f"item {k + 1}: no at or t (when it appears)")
            elif need_items:
                times.append(t)
            if typ == "chat" and it.get("from") not in CHAT_FROM:
                E(sc, f"item {k + 1}: from {it.get('from')!r} (must be {', '.join(CHAT_FROM)})")
        if typ == "list" and len(items) > 5:
            W(sc, f"{len(items)} items: 3-5 work better in a list")
        media = sc.get("media") or {}
        if "media" in spec["need"] and not media.get("file"):
            E(sc, "no media.file: a screenshot or a screen recording")
        if media.get("file"):
            mf = (e / media["file"]).resolve()
            if not is_inside(mf, e):
                E(sc, f"media {media['file']} is outside the video folder: put it in {e.name}/inserts/ (add --media copies it for you)")
            elif not mf.exists():
                E(sc, f"media file {media['file']} not found")
        if typ == "word" and not media.get("file") and not sc.get("variant"):
            E(sc, f"word: media or a variant is needed ({', '.join(variants)})")
        inter = sc.get("interaction") or {}
        if "interaction" in spec["need"]:
            if inter.get("kind") not in INTERACTIONS:
                E(sc, f"interaction.kind {inter.get('kind')!r} (must be {', '.join(INTERACTIONS)})")
            elif inter["kind"] == "type" and not str(inter.get("text", "")).strip():
                E(sc, "interaction type: text is needed (what gets typed)")
            elif inter["kind"] != "type" and not (isinstance(inter.get("target"), list) and len(inter["target"]) == 2
                                                  and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                          for v in inter["target"])):
                E(sc, f"interaction {inter['kind']}: target [x, y] as numbers is needed")
        if typ == "contrast" and len(lines) != 2:
            E(sc, f"contrast: text.lines = [before, after], but there are {len(lines)} lines")
        if typ == "cta" and len(lines) > 2:
            E(sc, f"cta: 1-2 lines, but there are {len(lines)}")
        if len((sc.get("why") or "").strip()) < 8:
            E(sc, "no 'why': a scene for the sake of a scene is not allowed")
        if not (sc.get("what") or "").strip():
            E(sc, "no 'what' (what is in frame)")
        for t in ("transition_in", "transition_out"):
            if sc.get(t) not in TRANSITIONS:
                E(sc, f"transition {sc.get(t)} (allowed: {', '.join(TRANSITIONS)})")
        if sc.get("sound") and sc["sound"] not in SCENE_SOUNDS:
            E(sc, f"sound {sc['sound']} (allowed: {', '.join(SCENE_SOUNDS)})")
        tn = scene_tone(sc, s)
        T = tones.get(tn)
        if not T:
            E(sc, f"unknown scene tone {tn!r} (available: {', '.join(tones)})")
            T = tones.get("calm") or {"in": 14, "out": 9, "hold": 0.4}
        if not isinstance(sc.get("dur"), (int, float)) or sc["dur"] <= 0:
            E(sc, f"duration {sc.get('dur')}")
            continue
        if typ == "cover":  # the cover is a still only (poster.py, the cover composition): neither in the video nor in the budget
            continue
        t_end = sc["start"] + sc["dur"]
        if sc["start"] < -1e-6 or t_end > D + 0.05:
            E(sc, f"runs past the video ({fmt_t(sc['start'])} + {sc['dur']} s, video {fmt_t(D)})")
        if typ == "hook" and mode == "full" and not only and sc["dur"] > conf.get("hook_full_max_s", 1.5) + 1e-6:
            E(sc, f"full hook {sc['dur']} s > {conf.get('hook_full_max_s', 1.5)} s: the face disappears in the most "
                  f"important seconds (shorter, or overlay/split)")
        # 2. the reading-time floor: counted from the frame when the whole text is on screen and the entrance is over
        #    (as the scene kit draws it: text_full_on); spoken text doesn't leave earlier than the tone's hold after
        #    the last word. Timing: sceneTimeline in kit/scenes/tones.ts (a transition over a pause -> a cut).
        hold = T.get("hold", 0.4)
        cw = cap.get("words") if words_ok else []
        tl = scene_timeline(sc, T, mode, fps, cw)
        t0 = sc["start"]
        exit_t = t0 + tl["settle_to"] / fps
        anchor_text, nwords = " ".join(lines), len(norm_words(" ".join(lines)))
        full_on = t0 + text_full_on(sc, typ, lines, tl, fps, cw) / fps
        if inter and (inter.get("t") is not None or inter.get("at") is not None):
            try:
                ti = item_time(inter, plan, cap)
            except SystemExit as x:
                E(sc, f"interaction: {x}")
                ti = None
            if ti is not None:  # typing: 1.5 frames per character (Ui in the kit), a tap or a cursor ~0.4 s
                busy = len(str(inter.get("text") or "")) * 1.5 / fps if inter.get("kind") == "type" else 0.4
                if ti < t0 - 1e-6 or ti + busy > exit_t + 1e-6:
                    E(sc, f"interaction at {fmt_t(ti)} (+{busy:.1f} s) is outside the scene {fmt_t(t0)}-{fmt_t(exit_t)}: "
                          f"it won't appear or will be cut off")
        if times:
            gap = R.get("item_gap_s", 0.6)
            for k in range(1, len(times)):
                if times[k] - times[k - 1] < gap - 1e-6:
                    E(sc, f"items {k} and {k + 1} are {times[k] - times[k - 1]:.2f} s apart < {gap} s: too frequent")
            for k, t in enumerate(times):
                if t < sc["start"] - 1e-6 or t > exit_t + 1e-6:
                    E(sc, f"item {k + 1} at {fmt_t(t)} is outside the scene {fmt_t(sc['start'])}-{fmt_t(exit_t)}")
            last = [it for it in items if isinstance(it, dict)][-1]
            anchor_text, nwords = str(last.get("text", "")), len(norm_words(last.get("text", "")))
            full_on = max(t0 + tl["lead"] / fps, max(times)) + tl["inF"] / fps  # itemFrames in the kit: max(lead, its own time)
        elif typ == "stat":
            nwords += 1  # the number itself
        if nwords:
            need = read_need(nwords, R)
            rest = exit_t - full_on
            settled[sc["id"]] = rest
            lay = f", layout change {tl['lead']}/{tl['tail']} frames" if tl["lead"] or tl["tail"] else ""
            if rest + 1e-6 < need:
                E(sc, f"reading-time floor: '{anchor_text[:40]}' ({nwords} words) settled {max(rest, 0):.2f} s < {need:.2f} s "
                      f"(from {fmt_t(full_on)}, when the whole text is on screen, until it leaves at {fmt_t(exit_t)}; tone {tn}: "
                      f"in {tl['inF']} / out {tl['outF']} frames{lay}): cut the text or split the scene, don't speed it up")
            hit = find_spoken(anchor_text, cap, near=t0, window=(t0 - 4.0, t_end))[0] if words_ok else []
            if hit and exit_t + 1e-6 < hit[0][1] + hold:
                E(sc, f"'{anchor_text[:40]}' is heard until {fmt_t(hit[0][1])} but leaves at {fmt_t(exit_t)}: after the last "
                      f"word hold for at least {hold} s (tone {tn})")
        # 3. quote: verbatim per the transcript; client/brief need a reference
        if typ == "quote":
            k = src.get("kind")
            if k == "speech":
                if not words_ok:
                    E(sc, "a quote from the speech, but captions.json has no words: nothing to check it against")
                else:
                    hits, best = find_spoken(" ".join(lines), cap)
                    if not hits:
                        E(sc, f"the quote is not verbatim: '{' '.join(lines)[:60]}' is not in captions.json as a run of words "
                              f"({best} of {len(norm_words(' '.join(lines)))} words matched): take the words from the transcript")
            elif k in ("client", "brief") and not str(src.get("ref") or "").strip():
                E(sc, f"a quote from {k}: source.ref is needed (where from: an email, the brief, a date)")
            elif k == "agent":
                W(sc, "the agent worded the quote: verify it and note it in the report")
        # 4. stat: a source is required (the error above); from the agent: verify
        if typ == "stat" and src.get("kind") == "agent":
            W(sc, "a number from the agent (source agent): verify it and note it in the report")
        elif typ == "stat" and src.get("kind") in ("client", "brief") and not str(src.get("ref") or "").strip():
            W(sc, f"a number from {src['kind']}: give source.ref")
        # 8. the overlay/split/window box
        if not only and mode in ("overlay", "split", "window"):
            box = sc.get("box") or default_box(mode)
            for m in scene_box_issues(e, plan, sc, box, fdata):
                E(sc, m + ("" if sc.get("box") else " (the default box: set add ... --box)"))
            if mode == "overlay" and not hides_subtitles(sc) and fc.inter(box, [0, band[0], 1080, band[1] - band[0]]):
                E(sc, f"box {box} is on the subtitle band (y {band[0]}-{band[1]}): move it higher or set hide_subtitles")
        if accent := text.get("accent"):
            if norm_words(accent) and " ".join(norm_words(accent)) not in " ".join(norm_words(" ".join(lines))):
                W(sc, f"accent '{accent}' is not found in the lines")
    # 5. contrast of the brand color pairs the scenes draw with: large text >= 3.0
    from brand import contrast
    c = (brand or {}).get("colors") or {}
    tl = [x for x in scenes if x.get("type") in SCENE_TYPES and x.get("type") != "cover"]
    for fg, bg in (("text_on_primary", "primary"), ("text_on_accent", "accent"), ("light", "primary")):
        if c.get(fg) and c.get(bg):
            k = contrast(c[fg], c[bg])
            if k < 3.0:
                errs.append(f"scenes: contrast of {fg} {c[fg]} on {bg} {c[bg]} = {k} < 3.0: large scene text is not readable "
                            f"(brand.py set {(brand or {}).get('slug')} colors.{fg}=...)")
                bad.update(x["id"] for x in scenes)
    # 6, 9. time: no two scenes at once, not over a meme, no full scenes in a row, only cta at the end
    tl.sort(key=lambda x: x["start"])
    for k, x in enumerate(tl):
        for y in tl[k + 1:]:
            if overlap(x, y) > 1e-6:
                errs.append(f"{x['id']} and {y['id']}: two scenes at once")
                bad.update((x["id"], y["id"]))
        for m in memes:
            if overlap(x, m) > 1e-6:
                E(x, f"overlaps meme {m['id']}: a scene and a meme never at the same time")
        for b in brolls:
            if overlap(x, b) > 0.05:
                W(x, f"at the same time as B-roll {b['id']}: a scene over B-roll, check it with a still frame")
        final = conf.get("final_s", 2.0)
        if x["start"] + x["dur"] > D - final + 1e-6 and x.get("type") not in ("cta", "outro"):
            E(x, f"in the last {final} s only cta is allowed (the ending and the call to action), but this is {x.get('type')}")
    fulls = [x for x in tl if x.get("mode") == "full"]
    if not only:
        gap_need = conf.get("full_gap_s", 2.0)
        for x, y in zip(fulls, fulls[1:]):
            gap = y["start"] - (x["start"] + x["dur"])
            if gap < gap_need - 1e-6:
                errs.append(f"{x['id']} and {y['id']}: two full scenes in a row (gap {max(gap, 0):.1f} s < {gap_need} s): "
                            f"the face disappears for too long")
                bad.update((x["id"], y["id"]))
    hooks = [settled[x["id"]] for x in tl if x.get("type") == "hook" and x["id"] in settled]
    others = [v for k, v in settled.items() if k not in {x["id"] for x in tl if x.get("type") == "hook"}]
    if hooks and others and max(hooks) + 1e-6 < max(others):
        warns.append(f"the hook is settled for {max(hooks):.2f} s, less than another scene ({max(others):.2f} s): the hook should get the most")
    if only:
        so = conf.get("scenes_only") or {}
        lo, hi = so.get("duration", [15, 25])
        if not lo <= D <= hi:
            warns.append(f"'scenes only': length {D} s is outside {lo}-{hi} s (best {'-'.join(map(str, so.get('optimum', [18, 22])))} s)")
        cov, cur = 0.0, None
        for x0, x1 in sorted((x["start"], x["start"] + x["dur"]) for x in tl):
            if cur and x0 <= cur[1] + 1e-6:
                cur[1] = max(cur[1], x1)
            else:
                cov += (cur[1] - cur[0]) if cur else 0.0
                cur = [x0, x1]
        cov += (cur[1] - cur[0]) if cur else 0.0
        need = so.get("coverage_min", 0.95)
        if D and cov / D < need - 1e-6:
            errs.append(f"'scenes only': scenes cover {cov:.1f} of {D} s ({cov / D * 100:.0f} %) < {need * 100:.0f} %: "
                        f"put the scenes back to back, with no empty frame")
        if tl and (tl[0].get("type") != "hook" or tl[0]["start"] > 0.05):
            warns.append("'scenes only': storyboard: the first scene is a hook starting at 0 s")
    return errs, warns, bad


def tone_issues(s, doc, brolls, memes, scenes, only=False):
    """The brand tone's ceilings (references/brands.md, "Brand tone"): memes, transitions, flash/whip, full, scene tones.
    -> [(message, insert ids)]. In validate they are errors; with reel.json -> tone_override, warnings."""
    bt = s.get("brand_tone") or {}
    if not bt:
        return []
    name = f"brand tone {bt.get('preset')}"
    out = []
    m = bt.get("memes") or {}
    if memes:
        if m.get("allowed") is False:
            out.append((f"{name} doesn't allow memes, but the plan has {len(memes)}", [x["id"] for x in memes]))
        elif m.get("max") is not None and len(memes) > m["max"]:
            out.append((f"{len(memes)} memes > {m['max']}: the ceiling of {name}", []))
        import meme_layout as ml
        sizes = ml.layout(s, doc)["sizes"]
        cap = m.get("size_max")
        for x in memes:
            if x.get("mode") == "cutaway" and not m.get("cutaway"):
                out.append((f"{x['id']}: a full-frame meme (cutaway): {name} doesn't allow it", [x["id"]]))
            if cap in sizes and x.get("box") and x.get("mode") == "popup" and max(x["box"][2], x["box"][3]) > sizes[cap] + 1:
                out.append((f"{x['id']}: meme {max(x['box'][2], x['box'][3])} px > size {cap} ({sizes[cap]} px): the ceiling of {name}",
                            [x["id"]]))
        if cap in MEME_SIZES and s.get("meme_size") in MEME_SIZES and MEME_SIZES.index(s["meme_size"]) > MEME_SIZES.index(cap):
            out.append((f"meme_size {s['meme_size']} > {cap}: the ceiling of {name}", []))
    allowed = bt.get("transitions") or TRANSITIONS
    flash, whip = [], []
    for x in brolls + memes + scenes:
        for t in ("transition_in", "transition_out"):
            v = x.get(t)
            if v and v in TRANSITIONS and v not in allowed:
                out.append((f"{x['id']}: transition {v}: {name} allows only {', '.join(allowed)}", [x["id"]]))
            (flash if v == "flash" else whip if v == "whip" else []).append(x["id"])
    if bt.get("flash_max") is not None and len(flash) > bt["flash_max"]:
        out.append((f"light flashes (flash) {len(flash)} > {bt['flash_max']}: the ceiling of {name}", sorted(set(flash))))
    if bt.get("whip_max") is not None and len(whip) > bt["whip_max"]:
        out.append((f"whip transitions {len(whip)} > {bt['whip_max']}: the ceiling of {name}", sorted(set(whip))))
    fulls = [x for x in scenes if x.get("mode") == "full"]
    if not only and bt.get("full_scenes_max") is not None and len(fulls) > bt["full_scenes_max"]:
        out.append((f"full scenes {len(fulls)} > {bt['full_scenes_max']}: the ceiling of {name}", [x["id"] for x in fulls]))
    st = bt.get("scene_tones") or []
    for x in scenes:
        tn = scene_tone(x, s)
        if st and tn not in st:
            out.append((f"{x['id']}: scene tone {tn} is not one of the brand's tones ({', '.join(st)}): the ceiling of {name}", [x["id"]]))
    return out


def cmd_add(a):
    if a.kind == "scene":
        return add_scene(a)
    if a.source not in SOURCES + ["auto"]:
        sys.exit(f"--source {a.source}: for {a.kind} allowed {', '.join(SOURCES + ['auto'])}")
    if a.source == "online" and not online():  # online sources come only with the online add-on
        sys.exit("--source online: the online add-on is not installed; use auto, project, local or generated")
    a.transition = a.transition or "cut"
    e = edit_dir(a.edit)
    cap = load_json(e / "captions.json", {})
    with editing_plan(e) as plan:
        start = resolve_at(a.at, plan, cap)
        kind = a.kind
        pre = KINDS[kind]["prefix"]
        n = 1 + max([int(i["id"][1:]) for i in plan["inserts"] if i["id"].startswith(pre)] or [0])
        mode = a.mode or KINDS[kind]["modes"][0]
        seg = next((g for g in plan["segments"] if g["start"] <= start < g["end"]), None)
        ins = {"id": f"{pre}{n:02d}", "kind": kind, "segment": seg["id"] if seg else None, "start": round(start + a.offset, 3),
               "dur": a.dur, "mode": mode, "what": a.what, "why": a.why, "query": a.query or "",
               "source": a.source, "candidate": None, "file": None, "src_in": 0.0,
               "transition_in": a.transition, "transition_out": a.transition_out or ("cut" if a.transition == "cut" else a.transition),
               "status": "planned", "fallback": "main footage", "credit": None}
        if kind == "meme":
            ins.update({"meme_id": a.meme_id, "position": a.position, "rights": None, "audio": False})
        if a.source == "generated":
            ins["gen"] = {k: "" for k in GEN_FIELDS}
        if a.cam:
            ins["cam"] = [float(x) for x in a.cam.split(",")]
        if kind == "broll" and mode == "window":  # the window box: the given one or the first free slot
            if a.box:
                ins["box"] = [int(float(x)) for x in a.box.split(",")]
            else:
                ins["box"] = next((b for b in WINDOW_SLOTS if not window_issues(e, plan, ins, b)), WINDOW_DEFAULT)
            for m in window_issues(e, plan, ins, ins["box"]):
                warn(f"{ins['id']}: {m}: validate will not pass it; set --box or move the insert")
        plan["inserts"].append(ins)
        plan["inserts"].sort(key=lambda i: i["start"])
    print(f"{ins['id']}: {kind} {mode} {fmt_t(ins['start'])} +{a.dur} s ({ins['segment']}): {a.what}"
          + (f"; window {ins['box']}" if ins.get("box") and kind == "broll" else ""))


def overlap(a, b):
    return min(a["start"] + a["dur"], b["start"] + b["dur"]) - max(a["start"], b["start"])


def follow_rough_cut(e, plan, cap, s, prov, doc, quiet=False):
    """The rough cut was rebuilt (another length, segment timeline or word times): the spans and the length follow it, and inserts,
    scene items and interactions placed by a word or a span move with their words. Ones placed by seconds stay where
    they were: the report names them, check them."""
    old = float(plan["duration"])
    fresh = build_plan(e, cap, s, prov, doc)
    plan["duration"], plan["segments"] = fresh["duration"], fresh["segments"]
    plan["captions_id"] = cut_id(cap)
    moved, by_seconds = [], []
    for i in plan.get("inserts", []):
        at = str(i.get("at") or "")
        if at.startswith("word:") or re.fullmatch(r"s\d+", at):
            t0 = round(resolve_at(at, plan, cap) + float(i.get("offset") or 0), 3)  # --offset is kept
            if abs(t0 - i["start"]) > 0.001:
                moved.append(i["id"])
                i["start"] = t0
        else:
            by_seconds.append(i["id"])
        for it in [x for x in (i.get("items") or []) if isinstance(x, dict)] + [i.get("interaction") or {}]:
            if str(it.get("at") or "").startswith("word:"):
                it["t"] = round(resolve_at(str(it["at"]), plan, cap), 3)
    save_json(plan_path(e), plan)
    if not quiet:
        print(f"the rough cut changed ({old:.2f} -> {plan['duration']:.2f} s): spans rebuilt"
              + (f"; moved with their words: {', '.join(moved)}" if moved else "")
              + (f"; placed by seconds, check them: {', '.join(by_seconds)}" if by_seconds else ""))


def cmd_validate(a, quiet=False):
    e = edit_dir(a.edit)
    # settings are the current ones from reel.json (reelcfg.py save), not the plan's snapshot; the snapshot is refreshed
    with locked(plan_path(e)):
        plan = load_plan(e)
        s, prov, doc, bdir, brand = current_settings(e, plan)
        eff, why = effective(s)
        if not plan.get("duration"):
            plan["duration"] = plan_duration(e, plan)
        cap0 = load_json(e / "captions.json") or {}
        if plan.get("format") != "scenes-only" and cap0.get("duration") and plan.get("duration"):
            if (abs(float(cap0["duration"]) - float(plan["duration"])) > 0.02
                    or plan.get("captions_id", cut_id(cap0)) != cut_id(cap0)):  # a re-cut of the same length too
                follow_rough_cut(e, plan, cap0, s, prov, doc, quiet)
            elif "captions_id" not in plan:  # a plan from before captions_id: it follows the cut it was checked on
                plan["captions_id"] = cut_id(cap0)
                save_json(plan_path(e), plan)
        if snapshot(plan, s, prov, eff, why, doc):
            save_json(plan_path(e), plan)
            if not quiet:
                print("the settings snapshot in the plan was refreshed from reel.json")
    lim = doc.get("limits", {})
    brand = brand or {}
    ext = online()  # online sources (footage, memes) are available only with the online add-on
    errs, warns = [], []
    if not plan.get("duration"):
        errs.append("the video length is unknown (no captions.json and no final.mp4): make the rough cut first")
        plan["duration"] = 0.0
    bud = budget(plan["duration"], s, doc)
    ins = plan.get("inserts", [])
    brolls = [i for i in ins if i["kind"] == "broll" and i["status"] != "skipped"]
    memes = [i for i in ins if i["kind"] == "meme" and i["status"] != "skipped"]
    scenes = [i for i in ins if i["kind"] == "scene" and i["status"] != "skipped"]
    only = plan.get("format") == "scenes-only"
    timeline = [x for x in scenes if x.get("type") != "cover"]  # the cover is a still only
    # scenes that cover the speaker's frame count toward coverage together with B-roll (not in "scenes only")
    covering = [] if only else [x for x in timeline if x.get("mode") in COVER_MODES]
    if brolls and not s.get("use_broll"):
        errs.append(f"the plan has {len(brolls)} B-roll, but use_broll=false")
    if memes and not s.get("use_memes"):
        errs.append(f"the plan has {len(memes)} meme(s), but use_memes=false")
    if len(brolls) > bud["broll_max"]:
        errs.append(f"B-roll {len(brolls)} > the budget of {bud['broll_max']} for intensity {s['intensity']}")
    if len(memes) > bud.get("memes_max", 0):
        errs.append(f"memes {len(memes)} > the budget of {bud.get('memes_max')} for intensity {s['intensity']}")
    # coverage is the share of the video where any insert is on screen: B-roll and memes in both modes (popups too);
    # simultaneous inserts are not counted twice (a union of intervals)
    cover, cur = 0.0, None
    for x0, x1 in sorted((i["start"], i["start"] + i["dur"]) for i in brolls + memes + covering):
        if cur and x0 <= cur[1]:
            cur[1] = max(cur[1], x1)
        else:
            cover += (cur[1] - cur[0]) if cur else 0.0
            cur = [x0, x1]
    cover += (cur[1] - cur[0]) if cur else 0.0
    cutaways = [m for m in memes if m.get("mode") == "cutaway"]
    import faces as fc
    fdata = fc.load(e)
    for k in plan.get("keep_clear", []) if fdata else []:
        if k.get("mode") == "window":  # a scene window: the rough cut isn't visible on screen, the face is in the speaker's window
            continue
        kc = k.get("cam")
        hit = [fc.cam_box(b, kc) for b in fc.between(fdata, k["start"], k["end"])
               if fc.inter(k["box"], fc.grow(fc.cam_box(b, kc), fc.MARGIN))]
        if hit:
            warns.append(f"'{k.get('what')}' {k['box']} touches the face {fc.union(hit)} on the rough cut "
                         f"({'with the camera' if kc else 'without a camera: pass --cam to keep-clear'}): "
                         f"check it with a still frame, or with faces.py audit after the render")
    cmax = (doc.get("meme_layout") or {}).get("cutaway_max", 1)
    if len(cutaways) > cmax:
        errs.append(f"full-frame memes (cutaway) {len(cutaways)} > {cmax} per video")
    if cover > bud["coverage_max_s"] + 0.01:
        errs.append(f"inserts take {cover:.1f} s > {bud['coverage_max_s']} s ({int(bud['coverage_max'] * 100)} % of the video)")
    act = sorted(brolls + memes, key=lambda i: i["start"])
    last = None  # the insert that ends later than all the previous ones
    for y in act:
        x = last
        if x is not None:
            gap = y["start"] - (x["start"] + x["dur"])
            if gap < -1e-6 and x["kind"] == y["kind"] == "broll":
                errs.append(f"{x['id']} and {y['id']} overlap")
            elif gap < -1e-6:
                warns.append(f"{x['id']} and {y['id']} at the same time: a meme over B-roll reads poorly")
            elif gap + 1e-6 < bud.get("min_gap_s", 0):
                errs.append(f"between {x['id']} and {y['id']} {gap:.1f} s < {bud.get('min_gap_s')} s for intensity "
                            f"{s['intensity']}: too frequent (move, remove or mark skipped)")
        if last is None or y["start"] + y["dur"] > last["start"] + last["dur"]:
            last = y
    for i in ins:
        tag = i["id"]
        if i["kind"] == "scene":  # scenes: check_scenes below
            continue
        k = KINDS.get(i["kind"])
        if not k:
            errs.append(f"{tag}: unknown kind {i['kind']}")
            continue
        if i["status"] not in STATUSES:
            errs.append(f"{tag}: status {i['status']} (must be one of {STATUSES})")
        if i["status"] == "skipped":
            if not i.get("fallback"):
                warns.append(f"{tag}: skipped with no reason in fallback")
            continue
        if i.get("mode") not in k["modes"]:
            errs.append(f"{tag}: mode {i.get('mode')} is not for {i['kind']} ({', '.join(k['modes'])})")
        for t in ("transition_in", "transition_out"):
            if i.get(t) not in TRANSITIONS:
                errs.append(f"{tag}: transition {i.get(t)} (allowed: {', '.join(TRANSITIONS)})")
        mn, mx = (lim["broll_min_s"], lim["broll_max_s"]) if i["kind"] == "broll" else (lim["meme_min_s"], lim["meme_max_s"])
        if not (mn - 1e-6 <= i["dur"] <= mx + 1e-6):
            errs.append(f"{tag}: duration {i['dur']} s is outside {mn}-{mx} s")
        if i["start"] < 0 or i["start"] + i["dur"] > plan["duration"] + 0.05:
            errs.append(f"{tag}: runs past the video ({fmt_t(i['start'])} + {i['dur']} s, video {fmt_t(plan['duration'])})")
        if len((i.get("why") or "").strip()) < 8:
            errs.append(f"{tag}: no 'why': an insert for the sake of an insert is not allowed")
        if not (i.get("what") or "").strip():
            errs.append(f"{tag}: no 'what' (what is in frame)")
        src = i.get("source")
        if i["kind"] == "broll":
            if src not in SOURCES + ["auto"]:
                errs.append(f"{tag}: source {src} (allowed: {', '.join(SOURCES)})")
            if src == "online" and not ext:
                errs.append(f"{tag}: the online source is unavailable: the online add-on is not installed "
                            f"(choose project, local or generated, or mark it skipped)")
            elif src == "online" and not s.get("use_online_footage"):
                errs.append(f"{tag}: online footage is off (use_online_footage=false)")
            elif src == "online" and not eff.get("online_footage") and i["status"] != "ready":
                warns.append(f"{tag}: online footage is unavailable ({why.get('online_footage')}) -> the next source or skipped")
            if src == "generated" and not s.get("use_generated_footage"):
                errs.append(f"{tag}: code scenes are off (use_generated_footage=false)")
            if i.get("mode") == "window":  # without a box the template uses WINDOW_DEFAULT, so that is what gets checked
                for m in window_issues(e, plan, i, i.get("box") or WINDOW_DEFAULT, fdata):
                    errs.append(f"{tag}: {m}" + ("" if i.get("box") else " (the default box: set add ... --box)"))
            if src == "generated" and i["status"] != "ready":
                # the brief must be complete before the code scene is made (codescene.py checks it too); an insert
                # that is not in the render -> fallback
                g = i.get("gen") or {}
                if g.get("engine") not in (None, "code") and not ext:  # the core makes code scenes only
                    warns.append(f"{tag}: gen.engine {g.get('engine')!r} is unavailable: the online add-on is not "
                                 f"installed (the core makes code scenes only, gen.engine code); until then the render "
                                 f"uses {i.get('fallback') or 'main footage'}")
                miss = [f for f in GEN_FIELDS if not isinstance(g.get(f), str) or not g[f].strip()]  # null or a number counts as "not filled"
                if miss:
                    warns.append(f"{tag}: the code-scene brief (gen) is not filled in ({', '.join(miss)}): fill it in "
                                 f"before codescene.py; until then the render uses {i.get('fallback') or 'main footage'}")
        else:
            import meme_layout as ml
            L = ml.layout(s, doc)
            lo, hi = L.get("popup_dur", [0.8, 1.8]) if i.get("mode") == "popup" else L.get("cutaway_dur", [0.6, 1.2])
            if not (lo - 1e-6 <= i["dur"] <= hi + 1e-6):
                errs.append(f"{tag}: meme {i['dur']} s: {i.get('mode')} needs {lo}-{hi} s")
            if i.get("mode") == "popup":
                if not i.get("box"):
                    (errs if i["status"] == "ready" else warns).append(
                        f"{tag}: position and size are not chosen: memes.py place {plan['id']} {tag}")
                else:
                    keep = [k for k in plan.get("keep_clear", []) if k["start"] < i["start"] + i["dur"] and k["end"] > i["start"]]
                    # everything in screen coordinates: the rough cut's faces (faces.json) -> through the meme's camera
                    # (memes.py place --cam writes i["cam"]; None means no camera). No cam key (an old plan): the
                    # coordinate system of the rough cut's faces is unknown, so with the meme's faces already checked
                    # an overlap with them is only a warning
                    measured = fc.between(fdata, i["start"], i["start"] + i["dur"])
                    known = "cam" in i
                    if known:
                        measured = [fc.cam_box(b, i["cam"]) for b in measured]
                    strict = known or i.get("faces") is None
                    for m in ml.check_box(i["box"], L, (i.get("faces") or []) + (measured if strict else []), keep):
                        errs.append(f"{tag}: {m}")
                    if not strict:
                        hit = [b for b in measured if fc.inter(i["box"], fc.grow(b, L["face_margin"]))]
                        if hit:
                            warns.append(f"{tag}: on the rough cut (without a camera) the meme touches the face {fc.union(hit)}: "
                                         f"if there is a push-in here, repeat memes.py place with --cam; otherwise check it "
                                         f"with a still frame")
                    if i.get("faces") is None:
                        warns.append(f"{tag}: the face is not checked (memes.py place with --face or --no-face)")
            if src == "online" and not ext:
                errs.append(f"{tag}: the online source is unavailable: the online add-on is not installed "
                            f"(choose a local meme, or mark it skipped)")
            elif src == "online" and not s.get("use_online_memes"):
                errs.append(f"{tag}: online memes are off (use_online_memes=false)")
            if i.get("embed") is False and i["status"] == "ready":
                errs.append(f"{tag}: a meme from a source that forbids burning it in ({src}): only as an in-app sticker")
            rights = i.get("rights")
            if rights == "blocked":  # blocked by third-party rights (a celebrity, a film still...): for any brand and policy
                errs.append(f"{tag}: a meme blocked by rights (rights=blocked): replace it or mark it skipped")
            elif rights in (None, "unknown"):
                if brand.get("memes_policy") == "strict":
                    errs.append(f"{tag}: the meme's rights are unknown and the brand policy is strict: own/licensed/cc is needed")
                else:
                    warns.append(f"{tag}: the meme's rights are unknown: a risk for a commercial account")
            if i["start"] + i["dur"] > plan["duration"] - 2.0:
                warns.append(f"{tag}: a meme in the last 2 s: the ending/CTA is better without a meme")
        text = " ".join([i.get("what", ""), i.get("query", ""), " ".join(str(v) for v in (i.get("gen") or {}).values())]).lower()
        for f in forbidden_hits(brand, text):
            warns.append(f"{tag}: resembles imagery the brand forbids: '{f}'")
        if i["status"] == "ready":
            f = (e / i["file"]) if i.get("file") else None
            if not f or not f.exists():
                errs.append(f"{tag}: status ready, but the file is missing ({i.get('file')})")
            elif i["kind"] == "broll":
                info = probe(f)
                if (info["w"], info["h"]) != (1080, 1920):
                    warns.append(f"{tag}: the file is {info['w']}x{info['h']}, 1080x1920 expected (footage.py prepare)")
                if info["dur"] and info["dur"] + 0.05 < i["dur"] + i.get("src_in", 0):
                    errs.append(f"{tag}: the file ({info['dur']:.2f} s) is shorter than the insert ({i['dur']} s)")
        if i["status"] in ("planned", "pending") and not str(i.get("fallback") or "").strip():
            warns.append(f"{tag}: no fallback given: until it is ready, the render uses the main footage")
        if i["status"] == "pending" and not quiet:
            warns.append(f"{tag}: waiting ({i.get('fallback') or 'a code scene or a file'}): it won't go into the render until it is ready")
    cap = load_json(e / "captions.json", {}) if scenes else {}
    se, sw, bad = check_scenes(e, plan, s, doc, brand, fdata, cap, scenes, brolls, memes)
    errs += se
    warns += sw
    for m, ids in tone_issues(s, doc, brolls, memes, timeline, only):
        if s.get("tone_override"):  # going past the tone on explicit request: a warning, the reason goes into the report
            warns.append(m + " (tone_override: the brand tone is exceeded; note it in the report)")
        else:
            errs.append(m + " (to go past it on explicit request: reelcfg.py save ... --set tone_override=true)")
            bad.update(ids)
    # scene status: there is no file, so ready when the fields are valid; an error -> planned
    moves = {x["id"]: ("planned" if x["id"] in bad else "ready") for x in scenes if x["status"] in ("planned", "ready")}
    moves = {k: v for k, v in moves.items() if next(x for x in scenes if x["id"] == k)["status"] != v}
    if moves:
        # the status is written under a second lock: if another session changed the scene meanwhile, its status is left alone
        bare = lambda x: {k: v for k, v in x.items() if k != "status"}
        snap = {x["id"]: bare(x) for x in scenes}
        stale = []
        with editing_plan(e) as p2:
            for x in p2["inserts"]:
                if x.get("kind") == "scene" and x["id"] in moves and x.get("status") in ("planned", "ready"):
                    if bare(x) != snap.get(x["id"]):
                        stale.append(x["id"])
                        continue
                    x["status"] = moves[x["id"]]
        for k in stale:
            moves.pop(k, None)
            warns.append(f"{k}: the scene changed during the check: its status was left alone, run validate again")
        for x in scenes:
            if x["id"] in moves:
                if not quiet:
                    print(f"{x['id']}: {x['status']} -> {moves[x['id']]}")
                x["status"] = moves[x["id"]]
    if not quiet:
        for m in errs:
            print("error: " + m)
        for m in warns:
            print("warning: " + m)
        ready = sum(1 for i in ins if i["status"] == "ready")
        print(f"total: {len(ins)} insert(s) (ready {ready}), B-roll {len(brolls)}/{bud['broll_max']}, "
              f"memes {len(memes)}/{bud.get('memes_max')}, coverage {cover:.1f}/{bud['coverage_max_s']} s; "
              + (f"{len(timeline)} scene(s) (ready {sum(1 for x in timeline if x['status'] == 'ready')}, "
                 + ("'scenes only' format" if only else
                    f"full {sum(1 for x in timeline if x.get('mode') == 'full')}/"
                    f"{(s.get('brand_tone') or {}).get('full_scenes_max')}") + "); " if scenes else "")
              + f"{len(errs)} error(s), {len(warns)} warning(s)")
    return errs, warns


def cmd_md(a):
    e = edit_dir(a.edit)
    errs, warns = cmd_validate(a, quiet=True)  # also refreshes the settings snapshot in the plan
    plan = load_plan(e)
    s, eff, why = plan["settings"], plan["effective"], plan.get("fallback", {})
    ins = plan["inserts"]
    ext = online()  # the online part of the header and the download list only with the online add-on
    L = [f"# Visual plan: {plan['id']}", "",
         f"Brand **{plan['brand']}**, length {fmt_t(plan['duration'])}, intensity **{s['intensity']}**, "
         f"B-roll {'on' if eff.get('broll') else 'off'}, memes {'on' if eff.get('memes') else 'off'}, "
         f"code scenes {'on' if eff.get('generated_code') else 'off'}"
         + (f", online footage {'yes' if eff.get('online_footage') else 'no'}" if ext else ""), ""]
    fb = [f"{k}: {v}" for k, v in why.items() if k in ("online_footage", "generate_now", "online_memes") and v != "off"]
    if fb:
        L += ["Fallback: " + "; ".join(fb), ""]
    if plan.get("format") == "scenes-only":
        L += ["Format: **scenes only** (a promo without footage): no speech spans, scenes by time.", ""]
    bt = s.get("brand_tone") or {}
    if bt:
        L += [f"Brand tone **{bt.get('preset')}** ({bt.get('label', '')}), scene tone {s.get('scene_tone') or bt.get('scene_tone')}"
              + (", **tone_override** (ceilings exceeded: noted in the report)" if s.get("tone_override") else ""), ""]
    if plan["segments"]:  # "scenes only": no speech spans, so no table; the scenes are listed below
        L += ["| # | Timecode | Line | Main footage | B-roll | Meme | Scene | Transition | Comment |",
              "|---|---|---|---|---|---|---|---|---|"]
    for g in plan["segments"]:
        over = [i for i in ins if overlap(i, {"start": g["start"], "dur": g["end"] - g["start"]}) > 0.05]
        br = "; ".join(f"**{i['id']}** {i['what']} ({i['source']}, {i['dur']} s, {i['mode']}, {i['status']})"
                       for i in over if i["kind"] == "broll") or "-"
        mm = "; ".join(f"**{i['id']}** {i['what']} ({i['dur']} s, {i['mode']}, {i['status']})"
                       for i in over if i["kind"] == "meme") or "-"
        sn = "; ".join(f"**{i['id']}** {i.get('type')} {i['mode']}: {scene_text(i)} ({i['dur']} s, {i['status']})"
                       for i in over if i["kind"] == "scene") or "-"
        tr = "; ".join(f"{i['id']}: {i['transition_in']}/{i['transition_out']}" for i in over) or "cut"
        main = g["main"] + (f", {g['camera']}" if g.get("camera") else "") + (f"; graphics: {g['graphics']}" if g.get("graphics") else "")
        com = "; ".join(filter(None, [g.get("notes", "")] + [f"{i['id']}: {i['why']}" for i in over]))
        txt = g["text"] if len(g["text"]) < 90 else g["text"][:87] + "..."
        L.append(f"| {g['id']} | {fmt_t(g['start'])}-{fmt_t(g['end'])} | {txt} | {main} | {br} | {mm} | {sn} | {tr} | {com} |")
    if ins:
        L += ["", "## Inserts", ""]
        for i in ins:
            if i["kind"] == "scene":
                src = i.get("source") or {}
                L.append(f"- **{i['id']}** scene {i.get('type')} {fmt_t(i['start'])} +{i['dur']} s, {i['mode']}, tone "
                         f"{scene_tone(i, s)}: {scene_text(i)}. What: {i['what']}. Why: {i['why']}. "
                         + (f"Source: {src.get('kind')}{' (' + src['ref'] + ')' if src.get('ref') else ''}. " if src else "")
                         + f"Transition {i.get('transition_in')}/{i.get('transition_out')}"
                         + (", subtitles hidden" if hides_subtitles(i) else "") + f". Status: {i['status']}")
                continue
            c = i.get("candidate") or {}
            L.append(f"- **{i['id']}** {i['kind']} {fmt_t(i['start'])} +{i['dur']} s, {i['mode']}: {i['what']}. "
                     f"Why: {i['why']}. Source: {i['source']}"
                     + (f" ({c.get('provider')}: {c.get('title') or c.get('id')}, {c.get('w')}x{c.get('h')}, "
                        f"{c.get('size_mb', '?')} MB, license {c.get('license', '?')})" if c else "")
                     + f". Status: {i['status']}" + (f" -> {i['fallback']}" if i["status"] in ("pending", "skipped") else ""))
        dl = [i for i in ins if ext and i.get("source") == "online" and (i.get("candidate") or {}).get("provider")
              and i["status"] != "ready"]
        if dl:
            L += ["", "**Download after the person's approval ('yes'):** " + "; ".join(
                f"{i['id']}: {i['candidate']['provider']} {i['candidate'].get('id')}, {i['candidate'].get('size_mb', '?')} MB"
                for i in dl)]
        if any(i.get("source") == "generated" for i in ins):
            L += ["", "Code-scene briefs: `generated/briefs.md` (`codescene.py manifest`)."]
    L += ["", f"Check: {len(errs)} error(s), {len(warns)} warning(s)."]
    L += [f"- error: {m}" for m in errs] + [f"- warning: {m}" for m in warns]
    out = e / "visual_plan.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out)


def scene_text(i):
    """The scene text on one line, for md."""
    t = " / ".join((i.get("text") or {}).get("lines") or [])
    if i.get("items"):
        t = (t + ": " if t else "") + "; ".join(str(x.get("text", "")) for x in i["items"] if isinstance(x, dict))
    if i.get("type") == "stat" and i.get("value"):
        v = i["value"]
        t = f"{v.get('prefix', '')}{v.get('to')}{v.get('suffix', '')} " + t
    t = t or (i.get("interaction") or {}).get("text") or i.get("what", "")
    return f"'{t[:70]}{'...' if len(t) > 70 else ''}'"


def cmd_keep(a):
    """A zone that memes and windows don't cover: a card, the hook, the CTA, an object in hand."""
    e = edit_dir(a.edit)
    box = [int(x) for x in a.box.split(",")]
    entry = {"start": a.start, "end": a.end, "box": box, "what": a.what}
    if a.cam:  # the span's camera, so that validate checks the face where the viewer sees it
        entry["cam"] = [float(x) for x in a.cam.split(",")]
    with locked(plan_path(e)):
        plan = load_json(plan_path(e))
        if plan is None:  # inserts are off and no plan was built: a plan without inserts is created (a graphics registry)
            s, prov, doc, bdir, brand = current_settings(e)
            plan = build_plan(e, load_json(e / "captions.json"), s, prov, doc)
            print(f"there was no plan: created {plan_path(e)} without inserts (spans and keep_clear only)")
        plan.setdefault("keep_clear", []).append(entry)
        save_json(plan_path(e), plan)
    print(f"keep_clear: {a.what} {box} {fmt_t(a.start)}-{fmt_t(a.end)}")
    import faces as fc
    data = fc.load(e)
    if data:
        cam = [float(x) for x in a.cam.split(",")] if a.cam else None
        hit = [b for b in fc.between(data, a.start, a.end) if fc.inter(box, fc.grow(fc.cam_box(b, cam), fc.MARGIN))]
        print(f"warning: '{a.what}' touches the face (margin {fc.MARGIN} px): {fc.union(hit)}: move it to a zone from faces.py zones"
              if hit else f"the face is not touched (per faces.json{', with the camera' if cam else ', without a camera'})")


def scene_face(e, sc):
    """The speaker's face over the scene's interval from faces.json (the 1080x1920 rough cut): the median of the
    largest face in each sample. No measurement -> None (the kit uses its default face)."""
    import faces as fc
    data = fc.load(e)
    if not data or "samples" not in data:
        return None
    st = data.get("step", 0.25)
    t0, t1 = sc["start"], sc["start"] + sc["dur"]
    boxes = [max((f[:4] for f in smp["faces"]), key=lambda b: b[2] * b[3]) for smp in data["samples"]
             if t0 - st <= smp["t"] <= t1 + st and smp.get("faces")]
    if not boxes:
        return None
    med = lambda k: sorted(b[k] for b in boxes)[len(boxes) // 2]
    return [int(med(0)), int(med(1)), int(med(2)), int(med(3))]


def scene_export(i, e, pub, name, plan, cap, s):
    """A scene -> SceneSpec for the scene kit (resolved time, tone and files; the planning fields are left out)."""
    sp = {k: i.get(k) for k in ("id", "type", "mode", "variant", "start", "dur", "value", "box", "side", "source",
                                "transition_in", "transition_out", "sound")}
    sp["tone"] = scene_tone(i, s)
    t = i.get("text") or {}
    sp["text"] = {k: v for k, v in {"lines": t.get("lines") or [], "accent": t.get("accent"), "label": t.get("label")}.items()
                  if v is not None}
    if i.get("items"):
        sp["items"] = []
        for it in i["items"]:
            x = {k: v for k, v in it.items() if k not in ("at", "t")}
            tt = item_time(it, plan, cap)
            if tt is not None:  # without a time the kit spreads the items evenly
                x["t"] = round(tt, 3)
            sp["items"].append(x)
    if i.get("face") or i.get("mode") in ("panel", "window"):  # framing the speaker in the window: by the measurement, not by an "average" face
        sp["face"] = i.get("face") or scene_face(e, i)
    if i.get("type") == "cover" and i.get("frame_at") is not None:
        sp["frameAt"] = i["frame_at"]
    if i.get("interaction"):
        x = {k: v for k, v in i["interaction"].items() if k != "at"}
        tt = item_time(i["interaction"], plan, cap)
        x["t"] = round(tt if tt is not None else i["start"], 3)
        sp["interaction"] = x
    m = i.get("media") or {}
    if m.get("file"):
        src = e / m["file"]
        pub.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, pub / src.name)
        sp["media"] = {"file": f"{name}/inserts/{src.name}", "kind": m.get("kind") or
                       ("video" if media_kind(src) == "video" else "image")}
        info = probe(src)  # the file's aspect ratio: without it the kit takes a screenshot for a 9:16 phone screen and the cursor misses
        if m.get("aspect") or (info.get("w") and info.get("h")):
            sp["media"]["aspect"] = m.get("aspect") or round(info["w"] / info["h"], 4)
    if i.get("mode") in ("overlay", "split", "window") and not sp.get("box"):
        sp["box"] = default_box(i["mode"])
    sp["hide_subtitles"] = hides_subtitles(i)

    def clean(o):  # optional fields without null: in SceneSpec they are simply absent
        return {k: clean(v) for k, v in o.items() if v is not None} if isinstance(o, dict) else o
    return clean(sp)


def same_source(a, b):
    """A shot's "source" names a segment's source file: the same path, file name or stem."""
    a, b = str(a or ""), str(b or "")
    return bool(a and b) and (a == b or Path(a).name == Path(b).name or Path(a).stem == Path(b).stem)


def src_to_out(src, cap, seg=None, source=None):
    """A source second -> the second of the finished video (captions.json segments; references/camera.md, at()).
    source: the shot's file, for a cut from several cameras whose source seconds overlap."""
    pool = [g for g in cap.get("segments", []) if (seg is None or g["i"] == seg)
            and (source is None or same_source(source, g.get("source")))]
    if source is not None and not pool:
        sys.exit(f"camera.json: no segment of the rough cut comes from {source}")
    hit = [g for g in pool if g["src_start"] - 0.001 <= src <= g["src_end"] + 0.001]
    if not hit:
        # an edge moved by a few frames (a recut): a shot set on a segment start lands just before it; it follows
        nxt = [g for g in pool if src < g["src_start"] <= src + 0.25]
        if not nxt:
            sys.exit(f"camera.json: source second {src} was cut out")
        g = min(nxt, key=lambda x: x["src_start"])
        print(f"camera.json: source second {src} is cut out; the shot starts with the next segment ({g['src_start']})")
        return g["out_start"]
    if len(hit) > 1:
        sys.exit(f"camera.json: source second {src} is in several segments ({[g['i'] for g in hit]}): add \"source\" "
                 f"(the file) or \"seg\"")
    g = hit[0]
    return g["out_start"] + max(0.0, src - g["src_start"]) * g["out_dur"] / (g["src_end"] - g["src_start"])


def subtitles_in(e, lang):
    """captions-<lang>.json (subs.py apply) for the subtitles, checked against the current rough cut."""
    import subs
    f = e / f"captions-{lang}.json"
    doc = load_json(f)
    cap = load_json(e / "captions.json") or {}
    if not doc:
        sys.exit(f"subtitles_lang={lang}: no {f}; translate first: subs.py phrases {e} --lang {lang}, then subs.py apply")
    if doc.get("captions") != subs.fingerprint(cap):
        sys.exit(f"subtitles_lang={lang}: the rough cut changed after the translation: subs.py phrases {e} --lang {lang} "
                 f"(unchanged phrases keep their translation), translate the emptied ones, subs.py apply")
    print(f"subtitles: {lang} ({f.name})")
    return doc


def camera_shots(e, plan, cap):
    """edit/<id>/camera.json -> ReelKit props.camera: shots in seconds of the finished video, sorted.
    {"shots": [{"src": 12.4 | "at": "word:resume#1" | 3.2, "z": 1.1, "cx": 540, "cy": 1000, "drift": 0.03, "whip": false}]}
    src: a source second (stable when the speed changes), with "source": "cam-a.mov" on a cut from several
    files; at: a second or a word of the finished video."""
    doc = load_json(e / "camera.json", None)
    if not doc:
        return []
    shots = []
    for k, sh in enumerate(doc.get("shots", [])):
        t = (src_to_out(float(sh["src"]), cap, sh.get("seg"), sh.get("source")) if "src" in sh
             else resolve_at(str(sh.get("at", 0)), plan, cap))
        z = float(sh.get("z", 1.0))
        if z < 1:
            sys.exit(f"camera.json shot {k}: z {z} < 1 would show the frame edge")
        shots.append({"t": round(t, 3), "z": z, "cx": float(sh.get("cx", 540)), "cy": float(sh.get("cy", 960)),
                      "drift": float(sh.get("drift", 0)), "whip": bool(sh.get("whip"))})
    return sorted(shots, key=lambda x: x["t"])


def chin_on_screen(y, t, shots):
    """Where a source y lands on screen at second t: the shot's camera at its deepest drift (camera.md formula)."""
    s = next((x for x in reversed(shots) if x["t"] <= t + 1e-6), None)
    if not s:
        return y
    z = max(1.0, s["z"] * (1 + s["drift"]))
    cy = min(max(s["cy"], 960 / z), 1920 - 960 / z)
    return (y - cy) * z + 960


def cmd_export(a):
    e = edit_dir(a.edit)
    errs, _ = cmd_validate(a, quiet=True)
    if errs and not a.force:
        for m in errs:
            print("error: " + m)
        sys.exit("the plan has errors: fix them (or use --force)")
    plan = load_plan(e)  # after validate the settings snapshot is current
    rem = Path(a.remotion).resolve()
    if not (rem / "package.json").is_file() or not (rem / "src").is_dir():
        sys.exit(f"not a Remotion project (no package.json or src/): {rem}; nothing exported")
    name = safe_slug(a.name or plan["id"], "--name", dots=True)
    pub = inside(rem / "public", rem / "public" / name / "inserts", "inserts folder")
    out, skipped = [], []
    for i in plan["inserts"]:
        if i["kind"] == "scene":  # scenes: a separate list below
            continue
        if i["status"] != "ready":
            skipped.append(f"{i['id']} ({i['status']}) -> {i.get('fallback') or 'main footage'}")
            continue
        src = e / i["file"]
        pub.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, pub / src.name)
        out.append({"id": i["id"], "kind": i["kind"], "mode": i["mode"], "file": f"{name}/inserts/{src.name}",
                    "media": "image" if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") else "video",
                    "start": i["start"], "dur": i["dur"], "src_in": i.get("src_in", 0.0),
                    "transition_in": i["transition_in"], "transition_out": i["transition_out"],
                    "position": i.get("position"), "audio": i.get("audio", False), "plate": i.get("plate", False),
                    "box": i.get("box")})
    s = plan["settings"]
    cap = load_json(e / "captions.json", {})
    scenes, cover, hide, sk = [], None, [], []
    for i in plan["inserts"]:
        if i["kind"] != "scene":
            continue
        if i["status"] != "ready":
            sk.append(f"{i['id']} ({i['status']})")
            continue
        sp = scene_export(i, e, pub, name, plan, cap, s)
        if i.get("type") == "cover":
            cover = cover or sp
            continue
        scenes.append(sp)
        if sp.get("hide_subtitles"):
            hide.append([sp["start"], round(sp["start"] + sp["dur"], 3)])
    # the plan's keep_clear: overlay/split/window scenes (a box on screen); validate (memes, windows) and faces.py audit see them
    entries = scene_keep_entries(plan)
    if entries or any(k.get("scene") for k in plan.get("keep_clear", [])):
        with editing_plan(e) as p2:
            old = [k for k in p2.get("keep_clear", []) if not k.get("scene")]
            new = old + scene_keep_entries(p2)
            if new != p2.get("keep_clear", []):
                p2["keep_clear"] = new
                print(f"keep_clear: {len(new) - len(old)} overlay/split/window scene(s) (for faces.py audit)")
    save_json(rem / "src" / "plans" / f"{name}.json", {"id": name, "duration": plan["duration"], "inserts": out,
                                                     **({"scenes": scenes} if scenes else {})})
    print(f"src/plans/{name}.json: {len(out)} insert(s) go into the render" + (f"; no insert (fallback): {'; '.join(skipped)}" if skipped else "")
          + (f"; {len(scenes)} scene(s)" if scenes or sk else "") + (f" (not ready: {', '.join(sk)})" if sk else "")
          + ("; the cover: props.cover" if cover else ""))
    if a.props:
        # props of the universal template composition: rough cut, subtitles, brand, inserts;
        # `npx remotion render <Template> ... --props=<file>`
        brand = load_json(rem / "src" / "brands" / f"{safe_slug(plan['brand'], 'the plan brand')}.json")
        if not brand:
            sys.exit(f"no src/brands/{plan['brand']}.json: run brand.py export {plan['brand']} --remotion {a.remotion}")
        only = plan.get("format") == "scenes-only"
        vid, src_v = rem / "public" / name / "video.mp4", e / "final.mp4"
        if not only and not src_v.exists():
            sys.exit(f"no {src_v}: the rough cut is not built")
        # the rough cut copy is refreshed if final.mp4 was re-cut (a different size or modification time)
        st, dt = (src_v.stat() if not only else None), (vid.stat() if vid.exists() else None)
        if not only and (a.copy_video or not dt or dt.st_size != st.st_size or abs(dt.st_mtime - st.st_mtime) > 1):
            vid.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_v, vid)
            print(f"video: {src_v} -> public/{name}/video.mp4" + (" (updated)" if dt else ""))
        lang = plan["settings"].get("subtitles_lang")
        subs_cap = None if only or not lang else subtitles_in(e, lang)
        # the speech words stay in captions (scenes land on them, the render length is its duration); a translation
        # goes only to the subtitles
        props = {"video": "" if only else f"{name}/video.mp4",
                 "captions": {"duration": plan["duration"], "segments": [], "words": []} if only else load_json(e / "captions.json"),
                 **({"subtitleCaptions": subs_cap} if subs_cap else {}),
                 "brand": brand, "inserts": out,
                 "subtitles": a.subtitles or plan["settings"].get("subtitles") or brand.get("subtitles_default") or "accent",
                 "style": plan["settings"].get("style") or brand.get("style_default"),  # the current style from reel.json
                 "hideSubtitles": hide, "drift": True, "hook": {"text": a.hook, "until": 2.4} if a.hook else None,
                 "corner": bool(a.corner), "endCard": {"line1": a.card[0], "line2": a.card[1] if len(a.card) > 1 else None,
                                                       "seconds": 2.6} if a.card else
                 {"line2": brand.get("tagline"), "seconds": 2.6} if a.sting else None}
        cam = [] if only else camera_shots(e, plan, cap)
        if cam:
            props["camera"], props["drift"] = cam, False
            print(f"camera: {len(cam)} shot(s) from camera.json")
        # subtitles below the chin: the face measurement (faces.json), allowing for the template's drift (up to x1.05
        # toward the frame center)
        import faces as fc
        fdata = fc.load(e)
        if fdata:
            chins = ([chin_on_screen(b[1] + b[3], s_["t"], cam) for s_ in fdata["samples"] for b in s_["faces"]] if cam else
                     [(b[1] + b[3] - 960) * 1.05 + 960 for s_ in fdata["samples"] for b in s_["faces"]])
            if chins:
                need = round(max(chins) + fc.MARGIN // 2)
                props["subtitlesTop"] = max(1250, min(fc.SUB_MAX_TOP, need))
                print(f"subtitles: top at y {props['subtitlesTop']} (chin down to {round(max(chins))} per faces.json)"
                      + ("; WARNING: even at 1390 the chin touches the subtitles: use a wider shot or a lower camera" if need > fc.SUB_MAX_TOP else ""))
        if props["subtitles"] not in ("accent", "plate", "typewriter", "none"):
            mode = {"v2": "plate", "bar": "plate", "typewriter": "typewriter", "print": "typewriter"}.get(str(props["subtitles"]).lower())
            if not mode:
                warn(f"subtitles '{props['subtitles']}': the kit draws accent, plate and typewriter; accent is used")
            props["subtitles"] = mode or "accent"
        if s.get("subtitles_shade") is not None:
            props["subtitlesShade"] = float(s["subtitles_shade"])
        props["scenes"] = scenes  # designed scenes (the scene kit, SceneSpec); an older template ignores this prop
        props["sceneTone"] = s.get("scene_tone") or (s.get("brand_tone") or {}).get("scene_tone")
        if cover:
            props["cover"] = cover  # the cover is a separate still composition, not in the video's timeline
        if only:
            props["subtitles"], props["drift"] = "none", False
        if scenes:
            print(f"scenes: {len(scenes)} in props.scenes; subtitles hidden in {len(hide)} window(s)")
        save_json(Path(a.props), props)
        print(f"template props: {a.props}")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("edit"); p.add_argument("--set", nargs="*"); p.add_argument("--force", action="store_true")
    p.add_argument("--scenes-only", action="store_true", help="a promo without footage: a plan without speech, scenes only")
    p.add_argument("--duration", type=float, help="the length of a 'scenes only' video, s (15-25)")
    p.add_argument("--brand", help="the video's brand (saved to reel.json)")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("add"); p.add_argument("edit"); p.add_argument("--kind", choices=list(KINDS), required=True)
    p.add_argument("--at", required=True); p.add_argument("--offset", type=float, default=0.0)
    p.add_argument("--dur", type=float, required=True); p.add_argument("--what", required=True); p.add_argument("--why", required=True)
    p.add_argument("--query"); p.add_argument("--mode")
    p.add_argument("--source", default="auto", choices=SOURCES + ["auto"] + SCENE_SOURCES,
                   help="B-roll or meme: where the footage comes from (online needs the online add-on); scene: where the "
                        "text or number comes from (speech|brief|brand|client|agent)")
    p.add_argument("--transition", choices=TRANSITIONS, help="the entrance (B-roll and memes: cut; a scene: per the scene tone)")
    p.add_argument("--transition-out", choices=TRANSITIONS)
    p.add_argument("--meme-id"); p.add_argument("--position", default="top")
    p.add_argument("--box", help="the window box x,y,w,h (B-roll --mode window); without it, the first free slot")
    p.add_argument("--cam", help="z,cx,cy of the camera at this point: the rough cut's faces are checked in screen coordinates")
    g = p.add_argument_group("scene (--kind scene)")
    g.add_argument("--type", choices=list(SCENE_TYPES)); g.add_argument("--lines", nargs="+", metavar="LINE")
    g.add_argument("--accent"); g.add_argument("--label"); g.add_argument("--source-ref", help="where the text or number comes from")
    g.add_argument("--tone", help="the scene tone (calm, deadpan, cinematic, feature, punchy, hype, parody); without it, the video's tone")
    g.add_argument("--variant"); g.add_argument("--items-json"); g.add_argument("--value-json")
    g.add_argument("--media", help="a screenshot or a recording (copied to edit/<id>/inserts/)"); g.add_argument("--interaction-json")
    g.add_argument("--side", choices=["left", "right"], help="window (right by default) / panel (left): the speaker's side")
    g.add_argument("--frame-at", type=float, help="cover: the video second under the cover (otherwise 1.0 s or poster.py pick)")
    g.add_argument("--sound", choices=SCENE_SOUNDS); g.add_argument("--hide-subtitles", action="store_true")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("keep-clear"); p.add_argument("edit"); p.add_argument("--from", dest="start", type=float, required=True)
    p.add_argument("--to", dest="end", type=float, required=True); p.add_argument("--box", required=True, help="x,y,w,h in 1080x1920")
    p.add_argument("--what", required=True); p.add_argument("--cam", help="z,cx,cy of the camera on this span")
    p.set_defaults(fn=cmd_keep)
    p = sub.add_parser("validate"); p.add_argument("edit")
    p.set_defaults(fn=lambda a: sys.exit(1 if cmd_validate(a)[0] else 0))
    p = sub.add_parser("md"); p.add_argument("edit"); p.set_defaults(fn=cmd_md)
    p = sub.add_parser("export"); p.add_argument("edit"); p.add_argument("--remotion", required=True); p.add_argument("--name")
    p.add_argument("--force", action="store_true"); p.add_argument("--props", help="the props file for the template composition")
    p.add_argument("--subtitles", choices=["accent", "plate", "typewriter", "none"]); p.add_argument("--hook")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--card", nargs="+", metavar="LINE", help="the end card: 1-2 CTA lines")
    g.add_argument("--sting", action="store_true", help="a logo sting at the end: the logo with the brand line, 2.6 s, no CTA")
    p.add_argument("--corner", action="store_true", help="the brand mark in the corner"); p.add_argument("--copy-video", action="store_true")
    p.set_defaults(fn=cmd_export)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
