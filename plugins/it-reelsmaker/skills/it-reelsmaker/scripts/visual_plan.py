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
    python scripts/visual_plan.py keep-clear edit/4821 --remove 2      # the 2nd zone as numbered in visual_plan.md
    python scripts/visual_plan.py keep-clear edit/4821 --from 23.4 --to 26.7 --box 404,1038,632,652 --what presenter \
        --matte host --own-face 595,1120,181,233     # the presenter layer from matte.py place (it prints this line)
    python scripts/visual_plan.py hide-subs edit/4821 --from 23.4 --to 26.7 --why "presenter over a scene"
    python scripts/visual_plan.py hide-subs edit/4821 --remove 1       # numbered in visual_plan.md
    python scripts/visual_plan.py remove edit/4821 c03 [b01 ...]       # take inserts out of the plan (to change one: remove, add)
    python scripts/visual_plan.py validate edit/4821        # errors -> exit code 1; warnings -> exit code 0
    python scripts/visual_plan.py md edit/4821              # visual_plan.md: show it to the person before the render
    python scripts/visual_plan.py shade edit/4821           # the "Typewriter" darkening for 4.5:1 -> reel.json subtitles_shade
    python scripts/visual_plan.py export edit/4821 --remotion reels [--name 4821]

--at: a second on the timeline (5.2), a span (s03, its start) or a word (word:paint#1, the start of its nth occurrence).
Insert statuses: planned -> ready (the file is prepared) | pending (waiting for a code scene or for the person's
approval) | skipped (declined: the main footage stays, the reason is in fallback). Only ready inserts go into the
render; an unfilled code-scene brief (gen) on an insert that is not ready is a warning, not an error.
Settings come from edit/<id>/reel.json (reelcfg.py save); the plan holds only a snapshot, and validate refreshes it.
`init --set` saves the keys to reel.json. keep-clear without a plan creates a plan with no inserts (a graphics registry).
keep-clear --matte NAME marks a presenter layer (matte.py place prints the command): its span counts in the coverage,
--own-face is the presenter's own face (validate and faces.py audit don't flag it in its own zone), and export copies
edit/<id>/matte/NAME.webm to public/<id>/. hide-subs: windows where a per-video composition hides the subtitles
(a presenter, an accent title): export adds them to props.hideSubtitles, faces.py audit reads them.
Coverage is the union of the intervals of all inserts (B-roll and memes, popups included, and presenter layers);
coverage and spacing are errors.
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
overlay/split/window scenes to keep_clear (faces.py audit sees them), and records the render's subtitle band in the plan
(subtitles_band: the top below the measured chin), which faces.py audit checks.
The "framed" format (reel.json -> format: framed, optional window and label; references/techniques.md): a horizontal
rough cut in a rounded window on the style's field. The camera is clamped to the window (as the kit draws it), boxes
and the subtitle band stay inside the window's text area (reels_common.framed_area: with no label the field above the
window joins it; reel.json -> subtitles_at: below puts the subtitle band on the field under the window instead,
reels_common.framed_sub_area), scenes are overlay or full (full covers the window), and export writes props.framed (the
window, the label, the rough cut's size, the field color, where the subtitles go) so ReelKit draws the layout itself. validate checks that faces.json was
measured in the source geometry and that the rough cut is horizontal.
The "scenes only" format (init --scenes-only --duration N): no speech spans, --at in seconds only, every scene is full,
scene coverage >= 95 %; transitions are cuts (the texts hand over at the join, as the kit draws it) and more than 4 frames
of empty field at a join is a warning; export --props: video "", empty captions with the duration, subtitles none.
"""
import argparse, contextlib, datetime, filecmp, hashlib, json, math, re, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (CORNER_BOX, FRAMED_HOOK_MIN, FRAMED_LABEL_UP, FRAMED_RADIUS, FRAMED_SUB_GAP, MEME_SIZES, NUMBER_RE, SUB_BAND, SUB_BLOCK_H, SUB_MAX_TOP,
                          SUB_TOP_KIT, budget, cam_fit, edit_dir, editing_json, effective, forbidden_hits, framed_area, framed_sub_area,
                          framed_at, framed_issues, framed_source, framed_view, inside, load_config, load_json, locked,
                          media_kind, online, parse_sets, probe, project_root, safe_slug, save_json, tokens, utf8_stdio,
                          warn)

SCENE_MODES = ["overlay", "split", "panel", "window", "full"]  # a scene's default mode: the first of its own list
KINDS = {"broll": {"modes": ["replace", "window"], "prefix": "b"}, "meme": {"modes": ["popup", "cutaway"], "prefix": "m"},
         "scene": {"modes": SCENE_MODES, "prefix": "c"},
         "callout": {"modes": ["overlay"], "prefix": "l"}}  # a label pointing at an object (references/callouts.md)
# B-roll "window" (the Inserts component of the Remotion template): the box inserts[].box in 1080x1920 screen
# coordinates; without a box the template uses WINDOW_DEFAULT.
# Safe zone: right of x 960 are the UI buttons, above y 220 and below 1500 are the UI and the subtitles
WINDOW_DEFAULT = [60, 250, 900, 675]
WINDOW_ZONE = (0, 220, 960, 1500)
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
    English text. Words are separated by "|", letters by spaces, "_" is a space; any other token that is not a
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

# --- Designed scenes ---------------------------------------------------------------------------------------
# need: lines = text.lines; variant = one of variants; source; value; items; media; interaction
SCENE_TYPES = {
    "hook": {"modes": ["overlay", "split", "full"], "need": ["lines", "variant"], "variants": ["slam", "type", "stack", "counter"]},
    "quote": {"modes": ["overlay", "split", "full"], "need": ["lines", "source"]},
    "slogan": {"modes": ["full", "split"], "need": ["lines"]},
    "stat": {"modes": ["overlay", "split", "full"], "need": ["value", "lines", "source"]},
    "list": {"modes": ["overlay", "panel", "split", "full"], "need": ["items"]},  # overlay: items on plates, the speaker stays
    "contrast": {"modes": ["overlay", "split", "full"], "need": ["lines"]},
    "word": {"modes": ["overlay", "split", "panel", "full"], "need": ["lines"], "variants": ["grid-pick", "funnel", "timeline", "icon"]},
    "chat": {"modes": ["split", "full", "window"], "need": ["items"]},
    "ui": {"modes": ["split", "full", "window"], "need": ["media", "interaction"]},
    "cta": {"modes": ["overlay", "full"], "need": ["lines"], "variants": ["tap", "comment", "bio"]},
    "cover": {"modes": ["full"], "need": ["lines"]},
}
# Out of the menu (review 2026-10-17, wave 3): the kit draws them, but none is in a finished video yet. The agent offers
# one only where the content asks for it, and the plan and the scene command say "experimental" (references/scenes.md).
EXPERIMENTAL_SCENES = ("word", "chat", "ui")
EXPERIMENTAL_MODES = ("split", "panel", "window")
SCENE_SOURCES = ["speech", "brief", "brand", "client", "agent"]
SCENE_SOUNDS = ["card", "type", "tap", "hit", "paper", "bell", "none"]  # bell: payoff, a number lands, the logo (scenes.md)
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
        sys.exit(f"no plan: {plan_path(e)}; run visual_plan.py validate (a plain edit) or init (with inserts) first")
    return p


# what a rebuilt plan (init, init --force) keeps from the old one besides keep_clear: the last export's hook, corner
# logo and end (review 2026-10-18: init after an export lost them, the next export dropped the card), the subtitle band
# the render has, the subtitles hidden by a per-video composition
KEEP_ON_INIT = ("export", "hook", "corner", "end_card", "subtitles_band", "hide_subtitles")


def ensure_plan(e):
    """No plan yet and inserts and designed scenes off: a plan without inserts is created on the spot (as keep-clear
    does), so a plain edit needs no `init` before validate, md or export. Inserts or scenes on and no plan: still an
    error, since `init` is where they are planned."""
    s, prov, doc, bdir, brand = current_settings(e)
    eff, why = effective(s)
    inserts_on = eff.get("broll") or eff.get("memes") or s.get("use_scenes")
    old = load_json(plan_path(e)) if plan_path(e).is_file() else None
    if old is not None:
        if old.get("auto") and inserts_on:  # made by keep-clear or a plain edit, before inserts were turned on
            sys.exit(f"{plan_path(e)} was made without inserts and they are on now: run visual_plan.py init (it keeps "
                     f"keep_clear and the last export's choices)")
        return
    if inserts_on:
        sys.exit(f"no plan: {plan_path(e)}; inserts or designed scenes are on, so run visual_plan.py init first")
    if not load_json(e / "captions.json"):  # review 2026-10-18: a plan without it exported "captions": null to the kit
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
            hints.append("pointing at an object -> B-roll of the object, or a callout on it if the object is in the frame and the dot can stay on it: a still shot, or followed by track.py (experimental, references/callouts.md)")
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


def experimental(i):
    """' (experimental)' for a designed scene of an experimental type or in an experimental mode, else ''."""
    exp = i.get("kind", "scene") == "scene" and (i.get("type") in EXPERIMENTAL_SCENES or i.get("mode") in EXPERIMENTAL_MODES)
    return " (experimental)" if exp else ""


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
        plan.update({k: old[k] for k in KEEP_ON_INIT if k in (old or {})})  # the last export's finish, the subtitle band
        for d in load_defects(e)[0]:  # defects.py: a span with a bad picture gets the cover hint
            for g in plan["segments"]:
                if g["start"] < d["end"] and g["end"] > d["start"]:
                    g["hints"].append(f"picture {d['id']}: {d['kind']} {fmt_t(d['start'])}-{fmt_t(d['end'])} -> cover it "
                                      f"(full or code scene, replacing B-roll, cutaway) or accept it")
        if (old or {}).get("accepted_defects"):
            plan["accepted_defects"] = old["accepted_defects"]
        save_json(plan_path(e), plan)
    eff, why, dur = plan["effective"], plan["fallback"], plan["duration"]
    print(f"plan: {plan_path(e)}: {len(plan['segments'])} spans, {fmt_t(dur)}"
          + (f"; keep_clear kept ({len(plan['keep_clear'])})" if plan["keep_clear"] else ""))
    b = plan["budget"]
    scenes = bool(s.get("use_scenes"))  # T3: "inserts are off" was printed with designed scenes on
    if not eff.get("broll") and not eff.get("memes") and not scenes:
        print("inserts are off: the plan has only the main footage (the edit runs as without inserts)")
    else:
        print(f"budget ({s['intensity']}): up to {b['broll_max'] if eff.get('broll') else 0} B-roll, "
              f"up to {b.get('memes_max', 0) if eff.get('memes') else 0} memes, designed scenes {'on' if scenes else 'off'}, "
              f"inserts <= {b['coverage_max_s']} s in total (full, split, panel and window scenes count), "
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
        plan.update({k: old[k] for k in KEEP_ON_INIT if k in (old or {})})
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


def text_zone(e):
    """(x0, y0, x1, y1) where boxes may go: the safe zone (WINDOW_ZONE), or in the "framed" format the window's text
    area (reels_common.framed_area), and the zone's name for messages."""
    fr = framed_at(e)
    if fr:
        return tuple(framed_area(fr)), "the framed window's text area"
    return WINDOW_ZONE, "the safe zone"


def faces_seen(e, plan, data, t0, t1, cam=None, shots_ok=True):
    """The rough cut's faces in [t0, t1] where the viewer sees them -> (boxes, how). Through camera.json at each
    sample's time, as the kit renders it and faces.py audit checks it (how "camera.json"); else through the static
    cam (how "cam") or as measured (None). "Framed": relative to the window's center, the camera clamped to the window
    (T7: the full-frame clamp turned a shot at cx 820 into cx 540 and keep-clear missed a face faces.py check found),
    and clipped to it (beyond the window a face is not on screen)."""
    import faces as fc
    if not data:
        return [], None
    fr = fc.window(data)
    shots = plan_camera(e, plan) if shots_ok else []
    if shots:
        geo = camera_view(e, data)
        st, end = data.get("step", 0.25), plan_duration(e, plan) or shots[-1]["t"] + 1.0
        return [b for smp in data["samples"] if t0 - st <= smp["t"] <= t1 + st
                for b in fc.screen_faces(smp["faces"], camera_at(shots, smp["t"], end, view=geo), fr)], "camera.json"
    return fc.screen_faces(fc.between(data, t0, t1), cam, fr), ("cam" if cam else None)


def window_issues(e, plan, ins, box, fdata=None):
    """Problems with a window box: the safe zone (the framed window's text area), the face (faces.json through
    camera.json, else through the insert's --cam, with MARGIN), keep_clear."""
    import faces as fc
    (x0, y0, x1, y1), zone = text_zone(e)
    x, y, w, h = box
    out = []
    if x < x0 or y < y0 or x + w > x1 or y + h > y1:
        out.append(f"window {box} leaves {zone} x {x0}-{x1}, y {y0}-{y1}")
    t0, t1 = ins["start"], ins["start"] + ins["dur"]
    data = fdata if fdata is not None else fc.load(e)
    # the face on screen: through camera.json at each sample's time, as the kit renders it and faces.py audit checks it;
    # the insert's own static --cam only without camera.json (and the split layout's fixed speaker frame). T3: a hook box
    # with --cam 1,540,960 passed validate and failed the render audit: the shot's push-in lifted the face into its margin
    faces_, how = faces_seen(e, plan, data, t0, t1, ins.get("cam"), shots_ok=ins.get("mode") != "split")
    shots = how == "camera.json"
    hit = [f for f in faces_ if fc.inter(box, fc.grow(f, fc.MARGIN))]
    if hit:
        out.append(f"window {box} covers the face {fc.union(hit)} (margin {fc.MARGIN} px, "
                   + ("with the camera of camera.json)" if shots else "with the camera)" if ins.get("cam") else
                      "without a camera: if the span has a push-in, add ... --cam z,cx,cy)"))
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


def layout_frames(tr, T, way):
    """Frames of a layout change, as layoutFrames in the scene kit (kit/scenes/tones.ts)."""
    if tr == "cut":
        return 0
    if tr == "flash":  # a hard cut under the light flash (LightFlash.tsx): no layout frames
        return 0
    if tr == "whip":
        return 5
    return min(14, max(8, T.get("in", 14))) if way == "in" else min(10, max(6, T.get("out", 9)))


def scene_timeline(sc, T, mode, fps, words, only=False):
    """Frames of a scene from its start, as sceneTimeline in the scene kit (kit/scenes/tones.ts): a smooth transition
    over a pause becomes a cut ("over a pause, a hard cut"), lead/tail are 0.6 of the layout change (except overlay).
    only ("scenes only"): every smooth transition is a cut: there is no speaker to move and the field is the
    background, so the text enters from the scene's first frame and has left by its last (T6: 14-15 empty frames of
    bare field at every join, the old text's exit tail plus the new one's lead)."""
    n = max(1, jround(sc["dur"] * fps))
    tin = sc.get("transition_in") or T.get("transition", "cut")
    tout = sc.get("transition_out") or T.get("transition", "cut")
    if only:
        tin = "cut" if tin in ("fade", "slide", "whip") else tin
        tout = "cut" if tout in ("fade", "slide", "whip") else tout
    elif words:
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
    if typ == "cta":  # as CtaAction.tsx draws each variant
        var = sc.get("variant") or "tap"
        it = sc.get("interaction") or {}
        own = (it.get("text") or "").strip()
        if var == "tap":  # the head is the first line; the button (or the clarifier) comes in at lead + 6
            return lead + 6 + inF if (own or len(lines) > 1) else lead + inF
        if var == "comment":  # the head, the comment field at lead + 6, then the code word is typed (2 frames a character)
            quoted = next((m.group(1) for m in (re.search(r"[\u00ab\"\u201e\u201c]([^\u00bb\"\u201d]+)[\u00bb\"\u201d]", x)
                                                for x in lines) if m), None)
            word = own or quoted or (lines[1] if len(lines) > 1 else "")
            head = len(lines) if (own or quoted) else 1
            ti = it.get("t")
            t0 = (max(lead + inF + 4, jround((ti - sc["start"]) * fps)) if isinstance(ti, (int, float))
                  else lead + inF + 4)
            return max(lead + (head - 1) * 4 + inF, lead + 6 + inF, t0 + 2 * len(word))
        # bio: the head (the lines without the link) and the profile row at lead + 6
        link = own or next((x for x in lines if re.fullmatch(r"\S+\.[a-z\u0430-\u044f]{2,}(/\S*)?|@\S+|https?://\S+",
                                                               x.strip(), re.I)), "")
        head = len([x for x in lines if x != link])
        return max(lead + max(0, head - 1) * 4 + inF, lead + 6 + inF)
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


# Picture defects (defects.py -> faces_defects.json): a stretch where the sound is good and the picture is not. An insert
# that covers one says so (`add … --covers d03`); only a full scene, a replacing B-roll (a code scene is one) or a
# cutaway meme takes the face off screen: overlay, split, panel and window leave it there. The insert has to be on
# screen from COVER_PAD before the defect to COVER_PAD after it, its entrance finished by then and its exit not yet
# begun (a fade or a slide shows the defect through it), and ready (export takes only ready inserts); a defect left on
# purpose is accepted with a reason (`accept`), for that stretch only. references/inserts.md, "Covering a bad
# stretch".
COVER_PAD = 0.25
INSERT_IN = {"whip": 5, "slide": 8, "fade": 7}  # frames of an insert's entrance, and of its exit (kit/Inserts.tsx look())


def load_defects(e):
    """faces_defects.json -> (defects, a warning or None)."""
    path = Path(e) / "faces_defects.json"
    data = load_json(path)
    if not data:
        return [], None
    cut = Path(e) / "final.mp4"
    stale = cut.is_file() and cut.stat().st_mtime > path.stat().st_mtime + 1
    return data.get("defects") or [], (f"{path.name} is older than the rough cut: run defects.py {Path(e).name} again"
                                       if stale else None)


def hides_face(i):
    k, m = i.get("kind"), i.get("mode")
    return (k == "scene" and m == "full" and i.get("type") != "cover") or (k == "broll" and m == "replace") \
        or (k == "meme" and m == "cutaway")


def hidden_span(i, s, doc, cap, fps=30):
    """(from, to): the seconds the insert really hides what is under it: after its entrance (0 for a cut; a scene's
    layout change, an insert's fade or slide) and before its exit starts (review: a slide out began during the defect
    while the full length counted)."""
    if i.get("kind") == "scene":
        tones = {k: v for k, v in (doc.get("scene_tones") or {}).items() if not k.startswith("_")}
        T = tones.get(scene_tone(i, s)) or tones.get("calm") or {"in": 14, "out": 9}
        tl = scene_timeline(i, T, i.get("mode"), fps, (cap or {}).get("words") or [])
        fin, fout = layout_frames(tl["tin"], T, "in"), layout_frames(tl["tout"], T, "out")
    else:
        fin = INSERT_IN.get(i.get("transition_in") or "cut", 0)
        fout = INSERT_IN.get(i.get("transition_out") or "cut", 0)
    return i["start"] + fin / fps, i["start"] + i["dur"] - fout / fps


def same_defect(acc, d):
    """An acceptance holds only for the defect it was given for: defects.py numbers them again on every run, and after
    a re-cut d01 can be another stretch (review)."""
    return acc.get("kind") == d["kind"] and abs(acc.get("start", -9) - d["start"]) <= 0.15 \
        and abs(acc.get("end", -9) - d["end"]) <= 0.15


def defect_issues(e, plan, s, doc, cap):
    """-> (errors, warnings, {defect id: how it is handled}) for the picture defects of edit/<id>. A ready insert covers
    a defect (export takes only ready ones); a planned one marked --covers is checked now and counts once it is ready."""
    defects, stale = load_defects(e)
    errs, warns, state = [], ([stale] if stale else []), {}
    if not defects:
        return errs, warns, state
    by_id = {d["id"]: d for d in defects}
    acc = plan.get("accepted_defects") or {}
    live = [i for i in plan.get("inserts", []) if i.get("status") != "skipped"]
    planned = {}
    D = float(plan.get("duration") or (cap or {}).get("duration") or 1e9)
    pad = lambda d: (max(0.0, d["start"] - COVER_PAD), min(D, d["end"] + COVER_PAD))  # the margin stops at the video's ends
    for i in live:
        for did in i.get("covers") or []:
            d = by_id.get(did)
            if not d:
                errs.append(f"{i['id']}: covers {did}, which faces_defects.json does not have")
                continue
            a, b = pad(d)
            if not hides_face(i):
                errs.append(f"{i['id']}: covers {did} ({d['kind']} {fmt_t(d['start'])}-{fmt_t(d['end'])}), but "
                            f"{i['kind']} {i.get('mode')} leaves the face on screen: a full scene, a replacing B-roll or "
                            f"a code scene, or a cutaway meme hides it")
                continue
            on, off = hidden_span(i, s, doc, cap)
            if on > a + 1e-6 or off < b - 1e-6:
                why = []
                if on > i["start"] + 1e-6:
                    why.append(f"its {i.get('transition_in')} entrance shows the defect through it: enter by a cut")
                if off < i["start"] + i["dur"] - 1e-6:
                    why.append(f"its {i.get('transition_out')} exit starts before that: leave by a cut or later")
                errs.append(f"{i['id']}: covers {did} ({fmt_t(d['start'])}-{fmt_t(d['end'])}) from {fmt_t(on)} to "
                            f"{fmt_t(off)}: it must hide the face {COVER_PAD} s before and after "
                            f"({fmt_t(a)}-{fmt_t(b)})" + ("; " + "; ".join(why) if why else ""))
                continue
            if i.get("status") == "ready":
                state[did] = f"covered by {i['id']}"
            else:
                planned.setdefault(did, i["id"])
    for d in defects:
        if d["id"] in state:
            continue
        ac = acc.get(d["id"])
        if ac and same_defect(ac, d):
            state[d["id"]] = f"accepted: {ac.get('why', '')}"
            continue
        a, b = pad(d)
        by = next((i for i in live if i.get("status") == "ready" and hides_face(i)
                   and hidden_span(i, s, doc, cap)[0] <= a + 1e-6 and hidden_span(i, s, doc, cap)[1] >= b - 1e-6), None)
        if by:  # a ready insert already hides it, without saying so
            state[d["id"]] = f"covered by {by['id']}"
            continue
        if d["id"] in planned:
            state[d["id"]] = f"to be covered by {planned[d['id']]} (not ready yet)"
            warns.append(f"{d['id']}: {d['kind']} {fmt_t(d['start'])}-{fmt_t(d['end'])}: {planned[d['id']]} will cover it "
                         f"once it is ready (until then the export leaves the defect on screen)")
            continue
        state[d["id"]] = "open"
        if ac:
            warns.append(f"{d['id']}: the acceptance was given for another stretch ({ac.get('kind')} "
                         f"{fmt_t(ac.get('start', 0))}-{fmt_t(ac.get('end', 0))}; defects.py numbered them again after "
                         f"a re-cut): look at this one and accept it again or cover it")
        warns.append(f"{d['id']}: {d['kind']} {fmt_t(d['start'])}-{fmt_t(d['end'])} ({d.get('detail', '')})"
                     + (f" under «{d['words'][:40]}»" if d.get("words") else "")
                     + f": cover it (add … --covers {d['id']}: a full or code scene, a replacing B-roll or a cutaway, "
                       f"entering and leaving by a cut) or accept it (visual_plan.py accept {Path(e).name} {d['id']} --why …)")
    return errs, warns, state


def cmd_accept(a):
    e = edit_dir(a.edit)
    ensure_plan(e)  # a plain edit has no init (SKILL.md step 7a)
    defects, _ = load_defects(e)
    by_id = {d["id"]: d for d in defects}
    with editing_plan(e) as plan:
        acc = plan.setdefault("accepted_defects", {})
        for did in a.ids:
            if a.remove:
                acc.pop(did, None)
                print(f"{did}: no longer accepted")
                continue
            d = by_id.get(did)
            if not d:
                sys.exit(f"{did}: not in {e / 'faces_defects.json'} (defects.py {e.name})")
            if not (a.why or "").strip():
                sys.exit("--why: say why it stays (a natural glance, a gesture, the only take)")
            acc[did] = {"why": a.why.strip(), "kind": d["kind"], "start": d["start"], "end": d["end"]}
            print(f"{did}: {d['kind']} {fmt_t(d['start'])}-{fmt_t(d['end'])} accepted: {a.why.strip()}")


def default_box(mode):
    return {"overlay": WINDOW_DEFAULT, "split": SPLIT_BOX, "window": WINDOW_SCENE_BOX}.get(mode)


def hides_subtitles(sc):
    """Subtitles are hidden (as in SceneLayer of the scene kit): split/panel/window/full and slogan always; hook, quote
    and list by default (the scene text repeats the speech; a list over the video replaces it, two texts at once don't
    read) unless hide_subtitles=false is explicit; the rest per hide_subtitles."""
    if sc.get("mode") in ("split", "panel", "window", "full") or sc.get("type") == "slogan":
        return True
    if sc.get("type") in ("hook", "quote", "list") and sc.get("hide_subtitles") is not False:
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
    (x0, y0, x1, y1), zone = text_zone(e)
    x, y, w, h = box
    out = []
    if x < x0 or y < y0 or x + w > x1 or y + h > y1:
        out.append(f"box {box} leaves {zone} x {x0}-{x1}, y {y0}-{y1}")
    win = SPEAKER_WINDOW.get(sc.get("side") or "right", SPEAKER_WINDOW["right"])  # as speakerTarget in the kit: right by default
    if fc.inter(box, win):
        out.append(f"box {box} covers the speaker's window {win} (the face must stay visible)")
    t0, t1 = sc["start"], sc["start"] + sc["dur"]
    for k in p.get("keep_clear", []):
        if k["start"] < t1 and k["end"] > t0 and fc.inter(box, k["box"]):
            out.append(f"the box covers '{k.get('what', 'graphics')}' {k['box']}")
    return out


def overlay_slots(e, plan, sc):
    """Candidate boxes for an overlay scene without --box: the two full-width window slots, then the low headroom
    bands (a band from the zone's top down to MARGIN above the highest face the viewer sees during the scene, camera.json
    applied, when it is at least HEADROOM_MIN tall, and the fixed HEADROOM_BAND; the taller first), then the 4:3 slots.
    Scene text reads across the width: 1789 got a 480x360 corner box over the chest when the slots came first."""
    import faces as fc
    bands = [HEADROOM_BAND]
    (x0, y0, x1, _), _z = text_zone(e)
    seen, _how = faces_seen(e, plan, fc.load(e), sc["start"], sc["start"] + sc["dur"], sc.get("cam"))
    if seen:
        top, y, x = max(250, y0), min(f[1] for f in seen) - fc.MARGIN, max(60, x0)
        if y - top >= HEADROOM_MIN:
            bands.append([x, top, min(900, x1 - x), y - top])
    return WINDOW_SLOTS[:2] + sorted(bands, key=lambda b: -b[3]) + WINDOW_SLOTS[2:]


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
    variants = spec.get("variants") or []
    # T1: a hook added without --variant passed here and failed only at validate
    if ("variant" in spec["need"] and not a.variant) or (a.variant and variants and a.variant not in variants):
        sys.exit(f"scene {a.type}: --variant {'is required' if not a.variant else a.variant + ' is not one of them'}: "
                 f"{', '.join(variants)}")
    if a.variant and not variants:
        sys.exit(f"scene {a.type} has no variants: drop --variant")

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
        # the first mode of the type's own list: a slogan is full, not the experimental split (wave 3); the others
        # were already the first of their list
        mode = a.mode or ("full" if only else spec["modes"][0])
        if mode not in SCENE_MODES:
            sys.exit(f"scene mode {mode}: allowed {', '.join(SCENE_MODES)}")
        if only and mode != "full":  # T6: accepted here, refused only by validate
            sys.exit(f"'scenes only' format: there is no speaker, so the mode is full only, not {mode}")
        if mode not in spec["modes"]:
            sys.exit(f"scene {a.type}: mode {mode} is not for it (allowed: {', '.join(spec['modes'])})")
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
              "sound": a.sound, "hide_subtitles": bool(a.hide_subtitles) or mode in ("split", "panel", "window", "full") or a.type in ("slogan", "hook", "quote", "list"),
              "status": "planned", "fallback": "main footage"}
        if a.type == "cover" and a.frame_at is not None:
            sc["frame_at"] = round(a.frame_at, 3)  # the video second under the cover (the cover composition, export -> cover.frameAt)
        if a.cam:
            sc["cam"] = [float(x) for x in a.cam.split(",")]
        if getattr(a, "covers", None):
            sc["covers"] = list(a.covers)
        if not only and mode in ("overlay", "split", "window") and sc["box"] is None:
            if mode == "overlay":  # the first free slot, as for a B-roll window, then a low band in the headroom
                slots = overlay_slots(e, plan, sc)
                sc["box"] = next((b for b in slots if not scene_box_issues(e, plan, sc, b)), None)
                if sc["box"] is None:  # 1789: WINDOW_DEFAULT was saved on the face and failed only at validate
                    why = scene_box_issues(e, plan, sc, WINDOW_DEFAULT)
                    sys.exit(f"scene {a.type} overlay at {fmt_t(start)}: no free box among {len(slots)} candidates "
                             f"(the default {WINDOW_DEFAULT}: {'; '.join(why)}). Set --box x,y,w,h (faces.py zones "
                             f"shows the free zones), another --mode, or move the scene")
            else:
                sc["box"] = default_box(mode)
        if sc["box"] and not only and mode in ("overlay", "split", "window"):
            for m in scene_box_issues(e, plan, sc, sc["box"]):
                warn(f"{sc['id']}: {m}: validate will not pass it; set --box or move the scene")
        plan["inserts"].append(sc)
        plan["inserts"].sort(key=lambda i: i["start"])
    if experimental(sc):
        print(f"{sc['id']}: {a.type} {mode} is experimental (the kit draws it, not yet checked in a finished video): say so "
              f"in the plan and look at its storyboard frame")
    print(f"{sc['id']}: scene {a.type} {mode} {fmt_t(start)} +{a.dur} s ({sc['segment'] or '-'}), tone {tone}, "
          f"transition {sc['transition_in']}/{sc['transition_out']}: {a.what}"
          + (f"; box {sc['box']}" if sc.get("box") else "") + ". Status planned -> ready after validate.")


def read_need(n, R):
    """Reading-time floor: up to 3 words need 0.8 s settled; more need 0.3 s per word, but at least 1.2 s."""
    return R.get("short_s", 0.8) if n <= R.get("short_words", 3) else max(R.get("min_s", 1.2), R.get("per_word_s", 0.3) * n)


END_CARD_S = 2.6  # the end card / logo sting the kit appends after the rough cut (export --card / --sting)


def end_tail(a, plan):
    """Seconds the export appends after the rough cut (an end card or a logo sting): "the last 2 s" count from the end
    of the whole video (T5: a stat scene ending 1.95 s before the end of a 25.0 s cut was flagged, while a 2.6 s sting
    followed and the video was 27.6 s). During export: its --card/--sting/--no-end, else the last export's choice
    (finish_of); validate takes --card/--sting before the export, else what the last export recorded ("end_card")."""
    if getattr(a, "sting", False) or getattr(a, "card", None):
        return END_CARD_S
    if getattr(a, "cmd", None) == "export":
        return END_CARD_S if finish_of(a, plan)[0]["end"] else 0.0
    return float((plan.get("end_card") or {}).get("seconds") or 0.0)


def finish_of(a, plan):
    """What export draws around the cut: the hook headline, the corner logo, the end card or the logo sting. A flag sets
    it, --no-hook/--no-corner/--no-end take it off, and with neither the last export's choice stays (review 2026-10-17:
    a re-export for a late fix dropped the approved hook and end card, and the missing card changed the video's length).
    -> ({"hook": text|None, "corner": bool, "end": {"kind": "card", "lines": [...]}|{"kind": "sting"}|None},
        notes for the person, names of what was kept from the last export)."""
    last = dict(plan.get("export") or {})
    notes = []
    preset = (plan.get("settings") or {}).get("finish")  # a series preset's finish (reelcfg.py preset use)
    legacy = plan.get("corner") or plan.get("end_card") or plan.get("hook")  # markers of an export before 1.13
    if not last and not legacy and isinstance(preset, dict) and preset:  # only a video with no ending of its own
        last = {"hook": None, "corner": bool(preset.get("corner")), "end": preset.get("end")}
    elif not last:  # a plan exported before 1.13 kept only markers: the corner and a sting come back, texts cannot
        if plan.get("corner"):
            last["corner"] = True
        kind = (plan.get("end_card") or {}).get("kind")
        if kind == "sting":
            last["end"] = {"kind": "sting"}
        elif kind == "card" and not (getattr(a, "card", None) or getattr(a, "sting", False) or getattr(a, "no_end", False)):
            notes.append("the last export had an end card, but its lines are not stored: pass --card again (or --no-end)")
            last["end"] = {"kind": "card", "lines": None}  # still on: validate and this export count its 2.6 s
        if plan.get("hook") and not (getattr(a, "hook", None) or getattr(a, "no_hook", False)):
            notes.append("the last export had a hook headline, but its text is not stored: pass --hook again (or --no-hook)")
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


JOIN_EMPTY_MAX = 4  # frames: a "scenes only" join may show this much bare field (the exit's last frame and the
                    # entrance's first are nearly empty anyway); more reads as a pause (T6 had 14-15 at every join)


def text_frames(tl, s, tones, fps, only):
    """Where each scene's text is visible, in frames of the video → [(scene, first visible frame, frame after the last
    visible one)], by time: from the frame after its entrance starts (lead) to its exit's end (n - tail), as the kit
    draws it (an entrance at frame 0 is still transparent, an exit's last frame already is)."""
    out = []
    for x in sorted(tl, key=lambda v: v["start"]):
        T = tones.get(scene_tone(x, s)) or tones.get("calm") or {"in": 14, "out": 9}
        k = scene_timeline(x, T, x.get("mode"), fps, [], only)
        f0 = jround(x["start"] * fps)
        out.append((x, f0 + k["lead"] + 1, f0 + k["n"] - k["tail"]))
    return out


def scenes_only_cover(plan, s, doc):
    """"Scenes only": (seconds the scenes cover, seconds their text is on screen) for the validate summary."""
    tl = [x for x in plan.get("inserts", []) if x.get("kind") == "scene" and x.get("status") != "skipped"
          and x.get("type") in SCENE_TYPES and x.get("type") != "cover" and isinstance(x.get("dur"), (int, float))]
    fps = (doc.get("scenes") or {}).get("fps", 30)
    tones = {k: v for k, v in (doc.get("scene_tones") or {}).items() if not k.startswith("_")}

    def union(iv):
        tot, cur = 0.0, None
        for a0, a1 in sorted(iv):
            if cur and a0 <= cur[1] + 1e-6:
                cur[1] = max(cur[1], a1)
            else:
                tot += (cur[1] - cur[0]) if cur else 0.0
                cur = [a0, a1]
        return tot + ((cur[1] - cur[0]) if cur else 0.0)
    cov = union([(x["start"], x["start"] + x["dur"]) for x in tl])
    vis = union([(a / fps, b / fps) for _, a, b in text_frames(tl, s, tones, fps, True) if b > a])
    return cov, vis


def check_scenes(e, plan, s, doc, brand, fdata, cap, scenes, brolls, memes, tail=0.0):
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
    framed = None if only else framed_at(e)
    D = plan.get("duration") or 0.0
    tones = {k: v for k, v in (doc.get("scene_tones") or {}).items() if not k.startswith("_")}
    band = ml.layout(s, doc).get("subtitles_band", list(SUB_BAND))
    words_ok = bool((cap or {}).get("words"))

    def E(sc, msg):
        errs.append(f"{sc['id']}: {msg}")
        bad.add(sc["id"])

    def W(sc, msg):
        warns.append(f"{sc['id']}: {msg}")

    settled, needs = {}, {}
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
        elif framed and mode in ("split", "panel", "window") and typ != "cover":
            E(sc, f"the framed format: the kit draws overlay (inside the window) and full (covering the window) scenes, "
                  f"not {mode}: the speaker already sits in a window")
        elif mode not in spec["modes"]:  # "scenes only" too: the kit draws a type only in its own modes
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
        tl = scene_timeline(sc, T, mode, fps, cw, only)
        t0 = sc["start"]
        exit_t = t0 + tl["settle_to"] / fps
        label = str(text.get("label") or "")  # the caps label is on screen with the lines: it is read too (T6)
        spoken = " ".join(lines)  # what the speaker may say: the label is not spoken
        anchor_text = " ".join(([label] if label.strip() else []) + lines)
        nwords = len(norm_words(anchor_text))
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
            spoken = anchor_text
            full_on = max(t0 + tl["lead"] / fps, max(times)) + tl["inF"] / fps  # itemFrames in the kit: max(lead, its own time)
        elif typ == "stat":
            nwords += 1  # the number itself
        if nwords:
            need = read_need(nwords, R)
            rest = exit_t - full_on
            settled[sc["id"]], needs[sc["id"]] = rest, need
            lay = f", layout change {tl['lead']}/{tl['tail']} frames" if tl["lead"] or tl["tail"] else ""
            if rest + 1e-6 < need:
                E(sc, f"reading-time floor: '{anchor_text}' ({nwords} words) settled {max(rest, 0):.2f} s < {need:.2f} s "
                      f"(from {fmt_t(full_on)}, when the whole text is on screen, until it leaves at {fmt_t(exit_t)}; tone {tn}: "
                      f"in {tl['inF']} / out {tl['outF']} frames{lay}): cut the text or split the scene, don't speed it up")
            hit = find_spoken(spoken, cap, near=t0, window=(t0 - 4.0, t_end))[0] if words_ok else []
            if hit and exit_t + 1e-6 < hit[0][1] + hold:
                E(sc, f"'{spoken}' is heard until {fmt_t(hit[0][1])} but leaves at {fmt_t(exit_t)}: after the last "
                      f"word hold for at least {hold} s (tone {tn})")
        # 3. quote: verbatim per the transcript; client/brief need a reference
        if typ == "quote":
            k = src.get("kind")
            if k == "speech":
                if not words_ok:
                    E(sc, "a quote from the speech, but captions.json has no words: nothing to check it against")
                else:
                    hits, _ = find_spoken(" ".join(lines), cap)
                    lang = s.get("subtitles_lang")
                    if not hits and lang:  # a version with translated subtitles: the quote may be in their language
                        tr = load_json(e / f"captions-{lang}.json") or {}
                        hits = find_spoken(" ".join(lines), tr)[0] if tr.get("words") else []
                    if not hits:
                        E(sc, f"the quote is not verbatim: '{' '.join(lines)[:60]}' is not in captions.json as a run of words "
                              f"({near_match(' '.join(lines), cap)} of {len(norm_words(' '.join(lines)))} words found there "
                              f"in this order): take the words from the transcript"
                              + (f" or from the translated subtitles (captions-{lang}.json)" if lang else ""))
            elif k in ("client", "brief") and not str(src.get("ref") or "").strip():
                E(sc, f"a quote from {k}: source.ref is needed (where from: an email, the brief, a date)")
            elif k == "agent":
                W(sc, "the agent worded the quote: verify it and note it in the report")
        # 4. stat: a source is required (the error above); from the agent: verify. Any other text the agent took or
        #    worded itself (a hook, a contrast, a list from the client's site: T6) is "to verify" as well
        if typ == "stat" and src.get("kind") == "agent":
            W(sc, "a number from the agent (source agent): verify it and note it in the report")
        elif typ != "quote" and src.get("kind") == "agent":
            W(sc, "a text the agent took or worded itself (source agent): verify it with the person and note it in the "
                  "report (open items)")
        elif typ == "stat" and src.get("kind") in ("client", "brief") and not str(src.get("ref") or "").strip():
            W(sc, f"a number from {src['kind']}: give source.ref")
        # 8. the overlay/split/window box
        if not only and mode in ("overlay", "split", "window"):
            box = sc.get("box") or default_box(mode)
            for m in scene_box_issues(e, plan, sc, box, fdata):
                E(sc, m + ("" if sc.get("box") else " (the default box: set add ... --box)"))
            if mode == "overlay" and not hides_subtitles(sc) and fc.inter(box, [0, band[0], 1080, band[1] - band[0]]):
                E(sc, f"box {box} is on the subtitle band (y {band[0]}-{band[1]}): move it higher or set hide_subtitles")
            if typ == "hook" and mode == "overlay" and lines and (sc.get("variant") or "slam") in ("slam", "type"):
                # the kit's hook on plates: the font is the box height over the lines (1.21 per line with plates, the
                # label above takes 52 px), at most 96 px; the width may lower it further (measured in the render)
                size = min(96, int((box[3] - (52 if text.get("label") else 0)) / (len(lines) * 1.21)))
                need = FRAMED_HOOK_MIN if framed else 92
                if size < need:
                    W(sc, f"the hook lines come out at ~{size} px (box height {box[3]} for {len(lines)} line(s)), under "
                          f"{need} px: " + (f"in the framed format, start the box on the field above the window (no "
                                            f"label: the field joins the text area) or give it more of the window's "
                                            f"headroom; {FRAMED_HOOK_MIN} px is the floor inside the window"
                                            if framed else "the hook rule is 92-120 px: a taller box, or fewer lines"))
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
        if x["start"] + x["dur"] > D + tail - final + 1e-6 and x.get("type") not in ("cta", "outro"):
            E(x, f"in the last {final} s only cta is allowed (the ending and the call to action), but this is {x.get('type')}"
                 + (f" (the video ends at {D + tail:.2f} s with the {tail} s end card or sting)" if tail else ""))
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
    # a scene held no longer than its own reading floor needs is not a rival: an 8-word CTA needs 2.4 s whatever the hook
    # gets (T1 warned "hook 1.70 s < CTA 2.40 s" for exactly that)
    others = [v for k, v in settled.items() if k not in {x["id"] for x in tl if x.get("type") == "hook"}
              and v > needs.get(k, 0.0) + 0.1]
    if hooks and others and max(hooks) + 1e-6 < max(others):
        warns.append(f"the hook is settled for {max(hooks):.2f} s, less than another scene ({max(others):.2f} s, longer than "
                     f"its own reading floor): the hook should get the most")
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
        vis = text_frames(tl, s, tones, fps, only)
        for (x, a0, a1), (y, b0, b1) in zip(vis, vis[1:]):
            empty = b0 - a1  # frames of bare field between the old text leaving and the new one entering
            if empty > JOIN_EMPTY_MAX:
                warns.append(f"{x['id']} -> {y['id']}: {empty} frames of empty field at the join (the text of {x['id']} "
                             f"has left at {fmt_t(a1 / fps)}, {y['id']} shows from {fmt_t(b0 / fps)}): more than "
                             f"{JOIN_EMPTY_MAX}, start {y['id']} where {x['id']} ends")
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


def check_callouts(e, plan, s, doc, fdata, callouts, brolls, memes, scenes, corner=False, hook=False, motions=None):
    """Callout checks (references/callouts.md), on screen at every 0.25 s of each one, through the camera or the drift
    the video is drawn with; corner, hook: whether this run draws the corner logo and the hook headline (end_now; hook
    may be its text, for its height); motions: fresh measurements of the picture under the dots, by id, for validate
    to keep. -> (errors, warnings, ids of callouts with errors)."""
    errs, warns, bad = [], [], set()
    if not callouts:
        return errs, warns, bad
    import faces as fc
    import meme_layout as ml

    def E(c, msg):
        errs.append(f"{c['id']}: {msg}")
        bad.add(c["id"])

    def W(c, msg):
        warns.append(f"{c['id']}: {msg}")

    only = plan.get("format") == "scenes-only"
    fr = None if only else framed_at(e)
    ctx = callout_context(e, plan, fdata)
    segs, shots, drift, end = ctx[:4]
    fps = (doc.get("scenes") or {}).get("fps", 30)
    R = (doc.get("scenes") or {}).get("reading") or {}
    tones = {k: v for k, v in (doc.get("scene_tones") or {}).items() if not k.startswith("_")}
    lb = ml.layout(s, doc).get("subtitles_band", list(SUB_BAND))
    pb = plan.get("subtitles_band") or lb  # the band export measured for the render, and the layout's
    band = [min(lb[0], pb[0]), max(lb[1], pb[1])] if (s.get("subtitles") or "accent") != "none" else None
    zx0, zy0, zx1, zy1 = CALLOUT_ZONE
    step = (fdata or {}).get("step", 0.25)
    keep = [k for k in plan.get("keep_clear", []) if not k.get("callout")]
    # where the rough cut is not on screen as the anchor has it: a scene that moves or covers it, a replacing B-roll,
    # a cutaway meme
    cover = [x for x in scenes if x.get("mode") in COVER_MODES and x.get("type") != "cover"]
    # B-roll and memes only when ready: export renders nothing else, the main footage stays (Fable review)
    cover += [x for x in brolls + memes if x.get("mode") in ("replace", "cutaway") and x.get("status") == "ready"]
    # where the subtitles are hidden their band is free: hide-subs windows and scenes that hide them
    hidden = [tuple(h) for h in hidden_windows(plan)] + [(x["start"], x["start"] + x["dur"]) for x in scenes
                                                         if x.get("type") != "cover" and hides_subtitles(x)]
    # the hook headline at its own height: its lines of up to 14 characters, ~121 px each (ReelKit Hook, Mark)
    hook_box = [HOOK_BOX[0], HOOK_BOX[1], HOOK_BOX[2], 121 * (hook_lines(hook) if isinstance(hook, str) else 2)]
    # a horizontal rough cut without the framed format: the kit lays it as a band, the anchor is not where it points
    src = None if (only or fr) else framed_source(e)
    horizontal = bool(src and src[0] > src[1])
    boxes = [(x, x.get("box") or default_box("overlay")) for x in scenes if x.get("mode") == "overlay" and x.get("type") != "cover"]
    boxes += [(x, x["box"]) for x in brolls + memes if x.get("mode") in ("window", "popup") and x.get("box")]
    geo = {}
    for c in callouts:
        lines = [str(x) for x in ((c.get("text") or {}).get("lines") or []) if str(x).strip()]
        if c.get("status") not in STATUSES:
            E(c, f"status {c.get('status')} (must be one of {STATUSES})")
        if c.get("variant") not in CALLOUT_VARIANTS:
            E(c, f"variant {c.get('variant')!r} (allowed: {', '.join(CALLOUT_VARIANTS)})")
        if not 1 <= len(lines) <= 2:
            E(c, "text.lines: the subject, and an optional second line")
            continue
        a_ = c.get("anchor")
        if not _point(a_):
            E(c, "no anchor [x, y] on the rough cut")
            continue
        vr = c.get("variant")
        why = path_issue(c.get("path"), c.get("dur"))
        if why:
            E(c, why)
            continue
        if c.get("person") and c["person"] not in CALLOUT_PEOPLE:
            E(c, f"person {c['person']!r} (one of {', '.join(CALLOUT_PEOPLE)})")
            continue
        if c.get("person") and c.get("path"):
            E(c, "both a person and a path: the dot follows one of them")
            continue
        if vr == "dimension":
            if not _point(c.get("to")):
                E(c, "a dimension needs its second point (--to X,Y)")
                continue
            if c.get("path") or c.get("person"):
                E(c, "a dimension measures between two still points: no keys, track or person")
                continue
        elif c.get("to"):
            W(c, f"'to' is only for a dimension: the {vr} ignores it")
        if vr == "ring" and not (isinstance(c.get("radius"), (int, float))
                                 and CALLOUT_RING[0] <= c["radius"] <= CALLOUT_RING[1]):
            E(c, f"a ring needs its radius around the object (--radius {CALLOUT_RING[0]}-{CALLOUT_RING[1]} px of the rough cut)")
            continue
        if c.get("side") not in ("left", "right"):
            E(c, f"side {c.get('side')!r} (left or right)")
            continue
        if not all(isinstance(c.get(k), (int, float)) for k in ("start", "dur")) or c["dur"] <= 0:
            E(c, f"no start or duration (start {c.get('start')!r}, dur {c.get('dur')!r})")
            continue
        if only:
            E(c, "'scenes only': there is no footage to point at")
            continue
        if fr:
            E(c, "the framed format: callouts are drawn over the full frame only for now; take it off, or point at the "
                 "object with a scene")
            continue
        if horizontal:
            E(c, f"the rough cut is horizontal ({src[0]}x{src[1]}) without the framed format: the kit lays it as a band "
                 f"across the middle and the dot would miss the object")
            continue
        t0, t1 = callout_span(c, fps)
        if t0 < 0 or t1 > (plan.get("duration") or 0) + 0.05:
            E(c, f"runs past the video ({fmt_t(t0)} + {c['dur']} s, video {fmt_t(plan.get('duration') or 0)})")
        if not (c.get("what") or "").strip() or len((c.get("why") or "").strip()) < 8:
            E(c, "no 'what' or 'why': a callout for the sake of a callout is not allowed")
        w = c.get("w") or callout_width(lines, vr)
        if vr == "badge" and w > CALLOUT["badge_max"]:
            E(c, f"the badge is ~{w} px across (> {CALLOUT['badge_max']}): a number and a word, not a phrase; a tag "
                 f"holds a longer label")
        elif w > CALLOUT_MAX_W:
            E(c, f"the label is ~{w} px wide (> {CALLOUT_MAX_W}): a name and a short detail, not a sentence")
        if vr == "dimension" and math.hypot(c["to"][0] - a_[0], c["to"][1] - a_[1]) < 80:
            E(c, "the dimension's two points are less than 80 px apart: nothing to measure on screen")
        # a moving anchor: a person from faces.json, a track that still matches the rough cut, and seen most of the time
        if c.get("person"):
            pp = callout_path(c, ctx)
            if pp is None:
                E(c, "a callout on a person needs faces.json (faces.py scan): the dot follows the face")
                continue
            if not pp:
                E(c, f"no face in faces.json over {fmt_t(t0)}-{fmt_t(t1)}: there is no person to point at")
                continue
        if c.get("path_by") == "track" and (Path(e) / "final.mp4").is_file() and c.get("track_key") != track_key(e, c):
            E(c, "the rough cut, the anchor or the callout's time changed since track.py followed the object: run "
                 f"track.py edit/{Path(e).name} {c['id']} again")
        path = callout_path(c, ctx)
        if path:
            ts_ = callout_times(c)
            seen = sum(1 for t in ts_ if path_at(path, a_, t - t0)[2] >= 0.5) / max(1, len(ts_))
            if seen == 0:
                E(c, "the anchor is hidden over the whole callout: nothing would be drawn")
                continue
            if seen < CALLOUT_SEEN:
                W(c, f"the dot is hidden {round((1 - seen) * 100)} % of the callout (the object lost or out of the "
                     f"shot): shorten it to the stretch where it is seen")
        src = c.get("source") or {}
        if re.search(r"\d", " ".join(lines)) or NUM_RE.search(" ".join(lines).lower()):
            if not src.get("kind"):
                E(c, "a number on the label needs its source (--source speech|brief|brand|client|agent, --source-ref)")
            elif src["kind"] == "agent":
                W(c, "a number the agent wrote itself: to verify before the render")
        tn = c.get("tone") or scene_tone({}, s)
        if tones and tn not in tones:
            E(c, f"tone {tn!r} (allowed: {', '.join(tones)})")
        # the reading time: fully on screen after the entrance and before the fade
        tin = (tones.get(tn) or {}).get("in", CALLOUT_TIMES["calm_in"])
        busy = (callout_entrance(tin, len(lines) > 1) + (CALLOUT_TIMES["out"] if tin else 0)) / fps
        n_words = len(" ".join(lines).split())
        need = read_need(n_words, R)
        if c["dur"] - busy < need - 1e-6:
            E(c, f"too short to read: {max(0.0, c['dur'] - busy):.2f} s fully on screen after the entrance and before "
                 f"the fade, {need} s needed for {n_words} word(s): dur >= {need + busy:.1f} s")
        # a cut inside it, or a whip still moving the picture when it starts (7 frames from the shot)
        cuts = [sh["t"] for k, sh in enumerate(shots) if t0 + 1e-6 < sh["t"] < t1 - 1e-6
                or (k and sh.get("whip") and sh["t"] - 1e-6 <= t0 < sh["t"] + 7 / fps)]
        if cuts:
            E(c, f"the camera changes shot at {', '.join(f'{x:g}' for x in cuts)} s inside the callout: the dot would "
                 f"jump with the picture; end it before the shot or start it after")
        moved, why = (picture_motion(e, c, fresh=motions, ctx=ctx) if not c.get("person") or vr == "line"
                      else (None, "person"))
        # a person's dot follows the face detector, not a point of the picture: its motion is not checked, but its
        # text with no plate is (Codex review: the contrast sat inside the branch a person skips)
        if not c.get("person") and (moved is None or moved > CALLOUT_STILL):
            (E if moved is not None and moved > CALLOUT_MOVES else W)(c, motion_note(moved, why, callout_moves(c)))
        if vr == "line":
            ink = ((motions or {}).get(c["id"]) or c.get("motion") or {}).get("ink") if moved is not None else None
            if ink is None:
                W(c, "the text's contrast against the picture is not measured: check the stills")
            elif ink < CALLOUT_INK:
                E(c, f"the text with no plate reads poorly over the picture here (contrast {ink:g}:1, at least "
                     f"{CALLOUT_INK:g}:1): take the tag variant, or another anchor or side")
        for x in cover:
            if overlap(x, c) > 1e-6:
                E(c, f"on screen with {x['id']} ({x['kind']} {x.get('mode')}): the rough cut is covered or moved there, "
                     f"the dot would point at nothing")
        # on screen over its whole time: frame, safe zone, faces, the subtitles, the other graphics
        found = {}
        geo[c["id"]] = {}
        for t in callout_times(c, path=path):
            g = callout_at(c, t, ctx)
            if g["v"] <= 0:  # hidden: the anchor is lost there, nothing is drawn
                continue
            geo[c["id"]][t] = g
            (px, py), plate = g["dot"], g["plate"]
            segs_ = [tuple(sg) for sg in g["segs"]]
            rr = g["r"]
            dotbox = [px - rr, py - rr, 2 * rr, 2 * rr]
            # the dot's center (a dimension's two ends); a ring whole (Codex review: only its center was checked)
            # a dimension: its ends and the ends of its ticks (Codex bot review, PR 33: the ticks went past the edge)
            ends = ([(px - rr, py - rr), (px + rr, py + rr)] if vr == "ring" else
                    [tuple(q) for sg in g["segs"] for q in sg] if vr == "dimension" else [(px, py)])
            what = {"ring": "ring", "dimension": "dimension"}.get(vr, "dot")
            if any(not (0 <= x_ <= 1080 and 0 <= y_ <= 1920) for x_, y_ in ends):
                found.setdefault("frame", (t, f"the {what} ({px:.0f}, {py:.0f}) leaves the frame"))
            elif any(y_ < fc.UI_TOP or y_ > fc.H - fc.UI_BOTTOM or x_ > fc.W - fc.UI_RIGHT for x_, y_ in ends):
                found.setdefault("ui-dot", (t, f"the {what} ({px:.0f}, {py:.0f}) is in the app's UI zone"))
            x, y, pw, ph = plate
            if x < zx0 or y < zy0 or x + pw > zx1 or y + ph > zy1:
                found.setdefault("zone", (t, f"the label {[round(v) for v in plate]} leaves the safe zone x {zx0}-{zx1}, "
                                             f"y {zy0}-{zy1}: try the other --side, --below, or another anchor"))
            near = [f for smp in (fdata or {}).get("samples", []) if abs(smp["t"] - t) <= step / 2 + 1e-6
                    for f in smp["faces"]]
            for f in [_screen_box(f[:4], t, shots, segs, drift, end) for f in near]:
                if fc.inter(plate, fc.grow(f, fc.MARGIN)):
                    found.setdefault("face", (t, f"the label covers the face {[round(v) for v in f]} (margin {fc.MARGIN} px)"))
                own = (f[0] <= px <= f[0] + f[2] and f[1] <= py <= f[1] + f[3]) or (vr == "ring" and fc.inter(dotbox, f))
                if own:
                    found.setdefault("person", (t, "the dot is on a face: to point at a person, use --person (the dot "
                                                   "then goes to the shoulder); look at the stills"))
                elif any(_seg_hits(p, q, f, CALLOUT_LINE_MARGIN) for p, q in segs_):
                    found.setdefault("line", (t, f"the leader line crosses the face {[round(v) for v in f]}: put the "
                                                 f"label on the other side or under the dot"))
            if band and not any(h0 - 1e-6 <= t <= h1 + 1e-6 for h0, h1 in hidden):
                sub = [0, band[0], 1080, band[1] - band[0]]
                if fc.inter(plate, sub) or fc.inter(dotbox, sub) or any(_seg_hits(p, q, sub) for p, q in segs_):
                    found.setdefault("subs", (t, f"on the subtitle band (y {band[0]}-{band[1]}): move the anchor's label up"))
            # the other graphics: the label, and the dot and the line too (a popup meme is drawn over a callout and
            # would hide its dot; Antigravity review); a ring: its whole circle
            def covers(b):
                return fc.inter(plate, b) or fc.inter(dotbox, b) or any(_seg_hits(p, q, b) for p, q in segs_)
            for k in keep:
                if k["start"] <= t <= k["end"] and covers(k["box"]):
                    found.setdefault("keep", (t, f"the callout runs into '{k.get('what', 'graphics')}' {k['box']}"))
            for x_, b in boxes:
                if x_["start"] <= t <= x_["start"] + x_["dur"] and covers(b):
                    found.setdefault(f"box-{x_['id']}", (t, f"the callout runs into {x_['id']} ({x_['kind']}) {b}"))
            # the whole callout, as with the other graphics: it is drawn over the logo and the hook (PR 32 review)
            if corner and covers(list(CORNER_BOX)):
                found.setdefault("corner", (t, f"the callout covers the corner logo {list(CORNER_BOX)}"))
            if hook and t < 2.4 and covers(hook_box):
                found.setdefault("hook", (t, "the callout covers the hook headline (first 2.4 s)"))
        for key, (t, msg) in found.items():
            (W if key in ("ui-dot", "person") else E)(c, f"at {t:g} s {msg}")
    # one at a time, at most two at once, and apart
    live = sorted([c for c in callouts if c["id"] in geo], key=lambda c: c["start"])
    for k, b in enumerate(live):
        before = [a for a in live[:k] if a["start"] + a["dur"] > b["start"] + 1e-6]
        for a in before:
            if b["start"] - a["start"] < CALLOUT_GAP_S - 1e-6:
                E(b, f"enters {b['start'] - a['start']:.1f} s after {a['id']}: callouts come one at a time, "
                     f"at least {CALLOUT_GAP_S} s apart")
            # every sample of either while both are on screen (Codex review: their own grids may share none), and
            # each one's line against the other's label
            lo, hi = b["start"], min(a["start"] + a["dur"], b["start"] + b["dur"])
            ts = sorted({t for t in list(geo[a["id"]]) + list(geo[b["id"]]) + [lo, hi - 0.001] if lo <= t < hi})

            def clash(t):
                ga, gb = callout_at(a, t, ctx), callout_at(b, t, ctx)
                if ga["v"] <= 0 or gb["v"] <= 0:  # one of them hidden there
                    return False
                la, lb = [tuple(sg) for sg in ga["segs"]], [tuple(sg) for sg in gb["segs"]]
                # the dots and rings too (Codex bot review, PR 33: a big ring around the other label passed)
                ma, mb = [[g["dot"][0] - g["r"], g["dot"][1] - g["r"], 2 * g["r"], 2 * g["r"]] for g in (ga, gb)]
                if (any(fc.inter(m, x) for m, x in ((ma, gb["plate"]), (mb, ga["plate"]), (ma, mb)))
                        or any(_seg_hits(p, q, m) for ls, m in ((la, mb), (lb, ma)) for p, q in ls)):
                    return True
                return (fc.inter(ga["plate"], gb["plate"])
                        or any(_seg_hits(p, q, g2["plate"]) for ls, g2 in ((la, gb), (lb, ga)) for p, q in ls)
                        or any(_segs_cross(s1, s2) for s1 in la for s2 in lb))  # two lines crossing
            hit = next((t for t in ts if clash(t)), None)
            if hit is not None:
                E(b, f"at {hit:g} s runs into {a['id']}: their labels or lines overlap")
        if len(before) + 1 > CALLOUT_AT_ONCE:
            E(b, f"{len(before) + 1} callouts at once from {fmt_t(b['start'])} (at most {CALLOUT_AT_ONCE})")
    return errs, warns, bad


def end_now(a, plan):
    """What follows the cut, whether the corner logo and the hook headline are drawn, for THIS run: export's own
    --card/--sting/--corner/--hook, validate's flags, else what the last export recorded (Codex review: a first export
    --card was not counted, and an export without a card after one with it still counted the old card). Export keeps
    the last export's choice unless a flag changes it (finish_of).
    -> (end kind or None, corner, hook)."""
    if getattr(a, "cmd", None) == "export":
        fin = finish_of(a, plan)[0]
        return (fin["end"] or {}).get("kind"), fin["corner"], bool(fin["hook"])
    if getattr(a, "card", None):
        kind = "card"
    elif getattr(a, "sting", False):
        kind = "sting"
    else:
        kind = (plan.get("end_card") or {}).get("kind")
    # a standalone validate also trusts the last export's record
    corner = bool(getattr(a, "corner", False)) or bool(plan.get("corner"))
    hook = bool(getattr(a, "hook", None)) or bool(plan.get("hook"))
    return kind, corner, hook


def profile_issues(e, plan, s, brand, cap, scenes, memes, tail, corner=False, end_kind=None, hook=False):
    """The video profile's automatic checklist items (references/profiles.md; reel-defaults.json -> profiles):
    -> (errors, warnings, {item id: "ok" | "warn" | "error" | "check" | "validate"}). Only the paid-ad safe zone and
    meme rights in an ad are errors; the rest are warnings, the person decides. "check": the agent confirms it (the
    report's Supports name what was skipped); "validate": an existing check of validate covers it."""
    pr = s.get("profile_rules")
    if not pr:
        return [], [], {}
    errs, warns, st = [], [], {}
    only = plan.get("format") == "scenes-only"
    D = float(plan.get("duration") or 0.0)
    total = D + tail
    words = [w for w in (cap or {}).get("words") or [] if isinstance(w, dict) and w.get("start") is not None]
    timeline = [x for x in scenes if x.get("type") != "cover"]
    tag = f"profile {pr['id']}"

    def put(item, ok, msg, err=False):
        if ok:
            st[item] = "ok"
        else:
            st[item] = "error" if err else "warn"
            (errs if err else warns).append(f"{item} ({tag}): {msg}")

    cards = 1 if end_kind == "card" else 0
    ctas = [x for x in timeline if x.get("type") == "cta"]
    said = lambda w: str(w.get("text") or w.get("word") or "")  # captions.json words: text (older: word)
    spoken = " ".join(said(w) for w in words if float(w["start"]) >= D * 0.6)
    for item, check in (pr.get("checklist") or {}).items():
        if check is None:
            st[item] = "check"
        elif check == "validate":
            st[item] = "validate"
        elif check == "start":
            if only:
                st[item] = "check"
                continue
            first = float(words[0]["start"]) if words else None
            early = [x for x in timeline if float(x.get("start", 99)) <= 0.5]
            put(item, hook or early or (first is not None and first <= 1.0),
                f"the first word starts at {first if first is None else round(first, 2)} s and no scene opens the "
                f"video: a slow start (cut the lead-in, or open with a hook scene or the export --hook headline; "
                f"validate --hook when the export will have one)")
        elif check == "length":
            lo, hi = pr.get("length") or (None, None)
            put(item, not lo or lo - 0.5 <= total <= hi + 0.5,
                f"the video is {total:.1f} s, the {pr.get('format') or pr['id']} range is {lo}-{hi} s (a soft range: "
                f"say why in the report, or recut)")
        elif check == "cta_count":
            n = len(ctas) + cards
            put(item, n <= pr.get("cta_max", 1),
                f"{n} CTAs (scenes {', '.join(x['id'] for x in ctas) or '-'}{', the end card' if cards else ''}) > "
                f"{pr.get('cta_max', 1)} per video: one call to action"
                + (" (two only for a job opening: content_format offer)" if pr.get("cta_max", 1) < 2 else ""))
        elif check == "cta_present":
            put(item, ctas or cards or CTA_RE.search(spoken.lower()),
                "no CTA: no cta scene, no end card (export --card) and none spoken in the last 40 % of the video")
        elif check == "brand_early":
            n = float(pr.get("brand_by_s") or 3)
            names = [x for x in {str(brand.get("name") or ""), *(brand.get("aliases") or [])} if str(x).strip()]
            line = lambda t: " " + " ".join(norm_words(t)) + " "  # whole words: "Acme" in "acme's" yes, in "acmes" no
            keys = [line(x) for x in names if norm_words(x)]
            heard = line(" ".join(said(w) for w in words if float(w["start"]) <= n))
            seen = line(" ".join(scene_text(x) for x in timeline if float(x.get("start", 99)) <= n))
            hit = corner or any(k in heard or k in seen for k in keys)
            hit = hit or any(x.get("type") == "cover" for x in timeline if float(x.get("start", 99)) <= n)
            put(item, hit, f"the brand ({', '.join(names) or 'no name in brand.json'}) is not heard or seen by {n:g} s: "
                           f"say it, show it in the hook or a scene, or add the corner logo (export --corner; "
                           f"validate --corner)")
        elif check == "safe_zone":
            z = pr.get("safe_zone")
            if not z:
                continue
            x0, y0, x1, y1 = z
            bad = []
            boxes = [(m["id"], m["box"]) for m in memes if m.get("box") and m.get("mode") == "popup"]
            boxes += [(x["id"], x.get("box") or default_box(x.get("mode"))) for x in timeline
                      if x.get("mode") in ("overlay", "split", "window") and (x.get("box") or default_box(x.get("mode")))]
            boxes += [(k.get("what") or "keep-clear", k["box"]) for k in plan.get("keep_clear", [])
                      if k.get("box") and not k.get("scene") and not k.get("matte") and not k.get("callout")]
            # callouts from the plan itself, where the render puts their labels: their keep_clear entries come only
            # with export, after this check (PR 32 review: a first export of an ad let a label out of the zone)
            ctx = callout_context(e, plan)
            for c in plan.get("inserts", []):
                if (c.get("kind") != "callout" or c.get("status") == "skipped" or not _point(c.get("anchor"))
                        or not all(isinstance(c.get(k), (int, float)) for k in ("start", "dur")) or c["dur"] <= 0):
                    continue  # broken fields: check_callouts reports them (Antigravity review: a KeyError here)
                bs = [g["plate"] for g in (callout_at(c, t, ctx) for t in callout_times(c)) if g["v"] > 0]
                if not bs:
                    continue
                x_, y_ = min(b[0] for b in bs), min(b[1] for b in bs)
                boxes.append((f"callout {c['id']}", [round(x_), round(y_), round(max(b[0] + b[2] for b in bs) - x_),
                                                     round(max(b[1] + b[3] for b in bs) - y_)]))
            for name, b in boxes:
                if b[0] < x0 or b[1] < y0 or b[0] + b[2] > x1 or b[1] + b[3] > y1:
                    bad.append(f"{name} {list(b)}")
            # the subtitles: export lifts them into the zone itself (a band an earlier export recorded lower is not
            # blocked: Codex review); only a block taller than the zone can't fit
            h = SUB_BLOCK_H.get(str(s.get("subtitles") or "accent"), max(SUB_BLOCK_H.values()))
            if not only and y1 - y0 < h:
                bad.append(f"the subtitles ({h} px) do not fit between y {y0} and {y1}")
            fr = None if only else framed_at(e)
            if corner and not fr:  # export puts it at the zone's top for this profile (props.cornerTop)
                cx, cy, cw, ch = CORNER_BOX
                b = [cx, max(cy, y0), cw, ch]
                if b[0] < x0 or b[0] + b[2] > x1 or b[1] + b[3] > y1:
                    bad.append(f"the corner logo {b}")
            elif corner and fr and fr["window"][1] - 12 - 112 < y0:
                bad.append(f"the corner logo above the framed window (y {fr['window'][1] - 12 - 112}): drop --corner, or move "
                           f"the window down (reel.json window y >= {y0 + 124})")
            if fr and fr.get("label") and max(220, fr["window"][1] - FRAMED_LABEL_UP) < y0:
                bad.append(f"the framed label above the window (y {max(220, fr['window'][1] - FRAMED_LABEL_UP)}): move the "
                           f"window down (window y >= {y0 + FRAMED_LABEL_UP}) or drop the label")
            put(item, not bad, f"outside the ad safe zone x {x0}-{x1}, y {y0}-{y1} (the platform's caption and button "
                               f"cover the rest): " + "; ".join(bad), err=True)
            fulls = [x["id"] for x in timeline if x.get("mode") in ("full", "panel")]
            if fulls:
                warns.append(f"{item} ({tag}): full-frame scenes {', '.join(fulls)}: check their text against the safe "
                             f"zone on a still frame")
        elif check == "rights":
            # only the memes carry their rights in the plan: a bad one is an error; B-roll and music are not seen
            # here, so the item never passes automatically (Codex review: "ok" read as cleared for everything)
            bad = [m["id"] for m in memes if m.get("rights") not in ("own", "licensed", "cc")]
            if bad:
                put(item, False, f"memes {', '.join(bad)} without known rights (own, licensed or cc) in a paid ad: "
                                 f"replace them or mark them skipped", err=True)
            else:
                st[item] = "check"
        else:
            st[item] = "check"
    return errs, warns, st


def meme_rights(meme_id):
    """A meme's rights from the meme index (memes.py index), so validate knows them before memes.py prepare (T5:
    "rights are unknown" for an own meme and a CC one). blocked: forbidden by third-party rights. None: no id, or the
    meme is not indexed yet (a warning)."""
    if not meme_id:
        return None
    import memes
    m = (load_json(memes.index_path(project_root())) or {}).get(meme_id)
    if m is None:
        warn(f"--meme-id {meme_id}: not in the meme index (memes.py index); its rights stay unknown until memes.py prepare")
        return None
    return "blocked" if memes.is_blocked(m) else m.get("rights") or "unknown"


def add_callout(a):
    """A callout: a dot at --anchor (a point of the 1080x1920 rough cut), a leader line, a label with 1-2 lines; the
    dot may move along --keys, follow a --person's face (faces.json), or be tracked later (track.py); the variants
    (references/callouts.md) add --radius (ring) and --to (dimension). The side with room is taken unless --side says;
    validate checks it on screen over its whole time."""
    variant = a.variant or "tag"
    if variant not in CALLOUT_VARIANTS:
        sys.exit(f"callout --variant {a.variant}: allowed {', '.join(CALLOUT_VARIANTS)}")
    lines = [x.strip() for x in (a.lines or []) if x.strip()]
    if not 1 <= len(lines) <= 2:
        sys.exit("callout --lines: the subject, and an optional second line (a detail)")

    def point(s, flag):
        try:
            x_, y_ = (int(round(float(v))) for v in str(s).split(","))
        except ValueError:
            sys.exit(f"callout {flag} X,Y: a point on the 1080x1920 rough cut")
        return [x_, y_]
    if sum(bool(v) for v in (a.keys, a.person)) > 1:
        sys.exit("callout: --keys or --person, not both (the dot follows one path)")
    path = parse_keys(a.keys, a.dur) if a.keys else None
    if a.person and a.person not in CALLOUT_PEOPLE:
        sys.exit(f"callout --person {a.person}: one of {', '.join(CALLOUT_PEOPLE)}")
    if a.anchor:
        x, y = point(a.anchor, "--anchor")
    elif path:
        x, y = next([round(r[1]), round(r[2])] for r in path if (r[3] if len(r) > 3 else 1) > 0)
    elif not a.person:
        sys.exit("callout --anchor X,Y: the point of the object on the 1080x1920 rough cut (or --keys, or --person)")
    to = point(a.to, "--to") if a.to else None
    if variant == "dimension" and (not to or path or a.person):
        sys.exit("callout --variant dimension: --anchor and --to, the two still ends of what is measured")
    if variant == "ring" and not (a.radius and CALLOUT_RING[0] <= a.radius <= CALLOUT_RING[1]):
        sys.exit(f"callout --variant ring: --radius {CALLOUT_RING[0]}-{CALLOUT_RING[1]}, the ring around the object "
                 f"in px of the rough cut")
    if a.source not in SCENE_SOURCES + ["auto"]:
        sys.exit(f"callout --source {a.source}: where the text comes from ({', '.join(SCENE_SOURCES)})")
    e = edit_dir(a.edit)
    cap = load_json(e / "captions.json", {})
    w = callout_width(lines, variant)
    with editing_plan(e) as plan:
        start = resolve_at(a.at, plan, cap)
        n = 1 + max([int(i["id"][1:]) for i in plan["inserts"] if i["id"].startswith("l") and i["id"][1:].isdigit()] or [0])
        seg = next((g for g in plan["segments"] if g["start"] <= start < g["end"]), None)
        c = {"id": f"l{n:02d}", "kind": "callout", "variant": variant, "segment": seg["id"] if seg else None,
             "at": a.at, "offset": a.offset, "start": round(start + a.offset, 3), "dur": a.dur, "mode": "overlay",
             "anchor": None, "side": a.side, "below": bool(a.below), "text": {"lines": lines},
             "w": w, "tone": a.tone, "what": a.what, "why": a.why, "status": "planned",
             "source": {"kind": a.source, "ref": a.source_ref} if a.source in SCENE_SOURCES else None}
        if path:
            c.update(path=path, path_by="keys")
        if to:
            c["to"] = to
        if variant == "ring":
            c["radius"] = a.radius
        if a.person:
            import faces as fc
            fdata = fc.load(e)
            if not fdata:
                sys.exit("callout --person: no faces.json; run faces.py scan edit/<id> first (the dot follows the face)")
            c["person"] = a.person
            pr, pl = person_path(dict(c, side="right"), fdata), person_path(dict(c, side="left"), fdata)
            if not pr:
                sys.exit(f"callout --person: no face in faces.json over {fmt_t(c['start'])}-{fmt_t(c['start'] + a.dur)}")
            # the label away from the nearer edge of the frame: the shoulder on that side has room for it
            fx = next((r[1] + q[1]) / 2 for r, q in zip(pr, pl) if r[3] > 0)  # the face's middle
            c["side"] = c["side"] or ("right" if fx < 540 else "left")
            rows = person_path(c, fdata)
            x, y = next([round(r[1]), round(r[2])] for r in rows if r[3] > 0)
        c["anchor"] = [x, y]
        c["side"] = c["side"] or callout_side(x, w)
        moved, why = (None, "person") if a.person else picture_motion(e, c, keep=True, ctx=callout_context(e, plan))
        plan["inserts"].append(c)
        plan["inserts"].sort(key=lambda i: i["start"])
    if not (0 <= x <= 1080 and 0 <= y <= 1920):
        warn(f"{c['id']}: the anchor ({x}, {y}) is off the 1080x1920 frame: validate will not pass it")
    how = (f"following the {a.person} face's shoulder" if a.person else f"along {len(path)} keys" if path
           else f"to {tuple(to)}" if to else "")
    ink = (c.get("motion") or {}).get("ink")
    print(f"{c['id']}: callout {variant} (experimental: check the storyboard frames) {fmt_t(c['start'])} +{a.dur} s: "
          f"“{' / '.join(lines)}” at ({x}, {y}){' ' + how if how else ''}, label {c['side']}"
          f"{' below' if c['below'] else ''}, ~{w} px {'across' if variant == 'badge' else 'wide'}; "
          + ("the dot follows the face detector (faces.json)" if a.person else motion_note(moved, why, callout_moves(c)))
          + (f"; the text's contrast over the picture {ink:g}:1 (at least {CALLOUT_INK:g}:1)" if ink is not None else "")
          + ("; a moving object: track.py follows it (references/callouts.md)"
             if moved is not None and moved > CALLOUT_MOVES and not callout_moves(c) else ""))


def parse_keys(keys, dur):
    """--keys T:X,Y ... (T: seconds from the callout's start; T:- hides the dot from there, until the next key) ->
    path rows [t, x, y, v]: the dot slides straight between keys, fades out toward a hidden key and back in."""
    rows = []
    for k in keys:
        t_, _, xy = str(k).partition(":")
        try:
            t = round(float(t_), 3)
            if xy.strip() == "-":
                if not rows:
                    sys.exit(f"--keys {k}: the first key needs a point")
                rows.append([t, rows[-1][1], rows[-1][2], 0])
                continue
            x_, y_ = (round(float(v)) for v in xy.split(","))
        except ValueError:
            sys.exit(f"--keys {k}: T:X,Y (seconds from the callout's start, a point of the rough cut) or T:- (hidden)")
        rows.append([t, x_, y_, 1])
    why = path_issue(rows, dur)
    if why:
        sys.exit(f"--keys: {why}")
    return rows


def cmd_add(a):
    if a.kind == "scene":
        return add_scene(a)
    if a.kind == "callout":
        return add_callout(a)
    if a.source not in SOURCES + ["auto"]:
        sys.exit(f"--source {a.source}: for {a.kind} allowed {', '.join(SOURCES + ['auto'])}")
    if a.source == "online" and not online():  # online sources come only with the online add-on
        sys.exit("--source online: the online add-on is not installed; use auto, project, local or generated")
    if a.mode and a.mode not in KINDS[a.kind]["modes"]:  # a wrong mode was saved and failed only at validate
        sys.exit(f"{a.kind} --mode {a.mode}: allowed {', '.join(KINDS[a.kind]['modes'])}"
                 + ("; full frame for B-roll is `replace`" if a.kind == "broll" else ""))
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
            ins.update({"meme_id": a.meme_id, "position": a.position, "rights": meme_rights(a.meme_id), "audio": False})
        if a.source == "generated":
            ins["gen"] = {k: "" for k in GEN_FIELDS}
        if a.cam:
            ins["cam"] = [float(x) for x in a.cam.split(",")]
        if a.covers:
            ins["covers"] = list(a.covers)
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
    ensure_plan(e)  # md and export validate first, so all three work on a plain edit without `init`
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
    tail = end_tail(a, plan)  # an end card or a sting after the cut: "the last 2 s" are the whole video's
    ins = plan.get("inserts", [])
    brolls = [i for i in ins if i["kind"] == "broll" and i["status"] != "skipped"]
    memes = [i for i in ins if i["kind"] == "meme" and i["status"] != "skipped"]
    scenes = [i for i in ins if i["kind"] == "scene" and i["status"] != "skipped"]
    callouts = [i for i in ins if i["kind"] == "callout" and i["status"] != "skipped"]
    only = plan.get("format") == "scenes-only"
    timeline = [x for x in scenes if x.get("type") != "cover"]  # the cover is a still only
    # scenes that cover the speaker's frame count toward coverage together with B-roll (not in "scenes only")
    covering = [] if only else [x for x in timeline if x.get("mode") in COVER_MODES]
    # since 1.13 a brand tone no longer turns B-roll or memes on: a plan made before keeps its inserts once they are
    # chosen for the video (the hint), instead of a bare error on a re-render
    if brolls and not s.get("use_broll"):
        errs.append(f"the plan has {len(brolls)} B-roll, but use_broll=false (a brand tone no longer turns it on: "
                    f"reelcfg.py save edit/{e.name} --set use_broll=true, or remove the B-roll)")
    if memes and not s.get("use_memes"):
        errs.append(f"the plan has {len(memes)} meme(s), but use_memes=false (a brand tone no longer turns them on: "
                    f"reelcfg.py save edit/{e.name} --set use_memes=true, or remove the memes)")
    if len(brolls) > bud["broll_max"]:
        errs.append(f"B-roll {len(brolls)} > the budget of {bud['broll_max']} for intensity {s['intensity']}")
    if len(memes) > bud.get("memes_max", 0):
        errs.append(f"memes {len(memes)} > the budget of {bud.get('memes_max')} for intensity {s['intensity']}")
    # coverage is the share of the video where any insert is on screen: B-roll and memes in both modes (popups too);
    # simultaneous inserts are not counted twice (a union of intervals)
    # a presenter over a scene (keep-clear --matte, from matte.py place) covers the speaker's frame like a scene: T2
    # left it out and the plan read 39 % while the video had 51 % against a ceiling of 40 %
    layers = [] if only else [(k["start"], k["end"]) for k in plan.get("keep_clear", []) if k.get("matte")]
    cover, cur = 0.0, None
    for x0, x1 in sorted([(i["start"], i["start"] + i["dur"]) for i in brolls + memes + covering] + layers):
        if cur and x0 <= cur[1]:
            cur[1] = max(cur[1], x1)
        else:
            cover += (cur[1] - cur[0]) if cur else 0.0
            cur = [x0, x1]
    cover += (cur[1] - cur[0]) if cur else 0.0
    cutaways = [m for m in memes if m.get("mode") == "cutaway"]
    import faces as fc
    fdata = fc.load(e)
    fr = None if only else framed_at(e)
    errs += [f"reel.json: {m}" for m in framed_issues(load_json(e / "reel.json", {}) or {})]
    if not only:
        # the framed format and the measurement agree: faces.json in source geometry, a horizontal rough cut
        src = framed_source(e)
        if fr and fdata and not fdata.get("source"):
            errs.append("format framed, but faces.json was measured as a 9:16 cover: run faces.py scan again (a "
                        "horizontal rough cut is measured in its source geometry and mapped into the window)")
        elif not fr and fdata and fdata.get("source"):
            warns.append("faces.json is in source geometry (a horizontal rough cut), but reel.json has no format framed: "
                         "the kit would lay the video as a band across the middle; reelcfg.py save edit/<id> --set "
                         "format=framed")
        if fr and src and src[0] <= src[1]:
            warns.append(f"format framed with a vertical rough cut ({src[0]}x{src[1]}): the window only makes the face "
                         f"smaller; framed is for a horizontal source")
        elif not fr and src and src[0] > src[1]:
            warns.append(f"the rough cut is horizontal ({src[0]}x{src[1]}): without format framed the kit lays it as a "
                         f"band across the middle; reelcfg.py save edit/<id> --set format=framed")
    for k in plan.get("keep_clear", []) if fdata else []:
        if k.get("mode") == "window" or k.get("matte") or k.get("callout"):
            # a callout's label is checked with its callout (check_callouts); a scene window or a presenter layer: the rough cut isn't visible there; the face on screen is the speaker's
            # own (in the window, or the cut-out figure itself)
            continue
        kc = k.get("cam")
        # the face where the render puts it: camera.json at each sample's time, so a zone over a camera change is
        # checked shot by shot (a scene's entry keeps one static camera for its whole span); the split layout's fixed
        # speaker frame keeps its own; without camera.json, the zone's --cam
        faces_, how = faces_seen(e, plan, fdata, k["start"], k["end"], kc, shots_ok=k.get("mode") != "split")
        hit = [b for b in faces_ if fc.inter(k["box"], fc.grow(b, fc.MARGIN))]
        if hit:
            warns.append(f"'{k.get('what')}' {k['box']} touches the face {fc.union(hit)} on the rough cut "
                         f"({'with the camera of camera.json' if how == 'camera.json' else 'with the camera' if kc else 'without a camera: pass --cam to keep-clear'}): "
                         f"check it with a still frame, or with faces.py audit after the render")
    cmax = (doc.get("meme_layout") or {}).get("cutaway_max", 1)
    if len(cutaways) > cmax:
        errs.append(f"full-frame memes (cutaway) {len(cutaways)} > {cmax} per video")
    if cover > bud["coverage_max_s"] + 0.01:
        errs.append(f"inserts take {cover:.1f} s > {bud['coverage_max_s']} s ({int(bud['coverage_max'] * 100)} % of the video)"
                    + (f"; presenter layers included: {sum(b - a for a, b in layers):.1f} s" if layers else ""))
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
        if i["kind"] in ("scene", "callout"):  # scenes and callouts: check_scenes and check_callouts below
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
            if src == "generated" and not s.get("use_code_scenes"):
                errs.append(f"{tag}: code scenes are off (use_code_scenes=false)")
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
            if i["start"] + i["dur"] > plan["duration"] + tail - 2.0:
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
    se, sw, bad = check_scenes(e, plan, s, doc, brand, fdata, cap, scenes, brolls, memes, tail)
    errs += se
    warns += sw
    end_kind, corner_now, hook_now = end_now(a, plan)
    hook_text = (getattr(a, "hook", None) if isinstance(getattr(a, "hook", None), str)
                 else (plan.get("export") or {}).get("hook"))
    motions = {}
    ce, cw, cbad = check_callouts(e, plan, s, doc, fdata, callouts, brolls, memes, scenes, corner_now,
                                  (hook_text or True) if hook_now else False, motions)
    errs += ce
    warns += cw
    bad.update(cbad)
    for m, ids in tone_issues(s, doc, brolls, memes, timeline + callouts, only):
        if s.get("tone_override"):  # going past the tone on explicit request: a warning, the reason goes into the report
            warns.append(m + " (tone_override: the brand tone is exceeded; note it in the report)")
        else:
            errs.append(m + " (to go past it on explicit request: reelcfg.py save ... --set tone_override=true)")
            bad.update(ids)
    pe, pw, pst = profile_issues(e, plan, s, brand, cap if scenes else (load_json(e / "captions.json", {}) or {}),
                                 scenes, memes, tail, corner_now, end_kind, hook_now)
    errs += pe
    warns += pw
    # scene and callout status: there is no file, so ready when the fields are valid; an error -> planned
    drawn = scenes + callouts
    moves = {x["id"]: ("planned" if x["id"] in bad else "ready") for x in drawn if x["status"] in ("planned", "ready")}
    moves = {k: v for k, v in moves.items() if next(x for x in drawn if x["id"] == k)["status"] != v}
    if moves:
        # the status is written under a second lock: if another session changed the scene meanwhile, its status is left alone
        bare = lambda x: {k: v for k, v in x.items() if k not in ("status", "motion")}
        snap = {x["id"]: bare(x) for x in drawn}
        stale = []
        with editing_plan(e) as p2:
            for x in p2["inserts"]:
                if x.get("kind") in ("scene", "callout") and x["id"] in moves and x.get("status") in ("planned", "ready"):
                    if bare(x) != snap.get(x["id"]):
                        stale.append(x["id"])
                        continue
                    x["status"] = moves[x["id"]]
        for k in stale:
            moves.pop(k, None)
            warns.append(f"{k}: the scene changed during the check: its status was left alone, run validate again")
        for x in drawn:
            if x["id"] in moves:
                if not quiet:
                    print(f"{x['id']}: {x['status']} -> {moves[x['id']]}")
                x["status"] = moves[x["id"]]
    if motions:  # the picture under the dots, measured now: kept while the anchor, the time and final.mp4 stay
        with editing_plan(e) as p2:
            for x in p2["inserts"]:
                m = motions.get(x["id"]) if x.get("kind") == "callout" else None
                if m and [x.get("anchor"), x.get("start"), x.get("dur")] == m["key"][:3]:
                    x["motion"] = m
    if not only:  # picture defects (defects.py): covered, accepted, or a warning
        de, dw, _ = defect_issues(e, plan, s, doc, load_json(e / "captions.json", {}))
        errs += de
        warns += dw
    if not quiet:
        for m in errs:
            print("error: " + m)
        for m in warns:
            print("warning: " + m)
        ready = sum(1 for i in ins if i["status"] == "ready")
        if only:  # T6 printed the B-roll budget (coverage 0.0/4.84 s) and no scene coverage
            sc_cov, txt = scenes_only_cover(plan, s, doc)
            D = plan["duration"] or 1.0
            cov_line = (f"scenes cover {sc_cov:.1f} of {plan['duration']} s ({sc_cov / D * 100:.0f} %), text on screen "
                        f"{txt:.1f} s ({txt / D * 100:.0f} %)")
        else:
            cov_line = (f"B-roll {len(brolls)}/{bud['broll_max']}, memes {len(memes)}/{bud.get('memes_max')}, "
                        f"coverage {cover:.1f}/{bud['coverage_max_s']} s")
        print(f"total: {len(ins)} insert(s) (ready {ready}), {cov_line}; "
              + (f"{len(callouts)} callout(s) (experimental, ready {sum(1 for x in callouts if x['status'] == 'ready')}); "
                 if callouts else "")
              + (f"{len(timeline)} scene(s) (ready {sum(1 for x in timeline if x['status'] == 'ready')}, "
                 + ("'scenes only' format" if only else
                    f"full {sum(1 for x in timeline if x.get('mode') == 'full')}/"
                    f"{(s.get('brand_tone') or {}).get('full_scenes_max')}") + "); " if scenes else "")
              + f"{len(errs)} error(s), {len(warns)} warning(s)"
              + (f"; the video is {plan['duration'] + tail:.2f} s with the {tail} s end card or sting" if tail else ""))
        if pst:
            pr = s["profile_rules"]
            mark = {"ok": "ok", "warn": "WARN", "error": "ERROR", "validate": "ok (validate)", "check": "-"}
            print(f"profile {pr['id']} ({pr['label']}" + (f", format {pr['format']}" if pr.get("format") else "")
                  + "): " + ", ".join(f"{k} {mark[v]}" for k, v in pst.items() if v != "check"))
            todo = [k for k, v in pst.items() if v == "check"]
            if todo:
                print(f"  confirm by eye (references/profiles.md); name the skipped ones under Supports: {', '.join(todo)}")
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
        L += ["Format: **scenes only** (a promo without footage): no speech spans, scenes by time; between scenes the "
              "transition is a cut (one text leaves by its scene's last frame, the next enters from its first).", ""]
    elif framed_at(e):
        fr = framed_at(e)
        L += [f"Format: **framed** (a horizontal source in a window drawn by the kit): window {fr['window']}"
              + (f", label “{fr['label']}”" if fr["label"] else ", no label") + f"; text area {framed_area(fr)}"
              + (f"; subtitles below the window, band {framed_sub_area(fr)}" if fr["subtitles_at"] == "below" else "")
              + ".", ""]
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
        sn = "; ".join(f"**{i['id']}** {i.get('type')} {i['mode']}{experimental(i)}: {scene_text(i)} ({i['dur']} s, {i['status']})"
                       for i in over if i["kind"] == "scene") or "-"
        sn = "; ".join([sn] * (sn != "-") + [f"**{i['id']}** callout “{' / '.join((i.get('text') or {}).get('lines') or [])}” "
                                             f"({i['dur']} s, {i['status']})" for i in over if i["kind"] == "callout"]) or "-"
        tr = "; ".join(f"{i['id']}: {i['transition_in']}/{i['transition_out']}" for i in over if "transition_in" in i) or "cut"
        main = g["main"] + (f", {g['camera']}" if g.get("camera") else "") + (f"; graphics: {g['graphics']}" if g.get("graphics") else "")
        com = "; ".join(filter(None, [g.get("notes", "")] + [f"{i['id']}: {i['why']}" for i in over]
                               + ([f"hints: {', '.join(g['hints'])}"] if g.get("hints") else [])))
        txt = g["text"] if len(g["text"]) < 90 else g["text"][:87] + "..."
        L.append(f"| {g['id']} | {fmt_t(g['start'])}-{fmt_t(g['end'])} | {txt} | {main} | {br} | {mm} | {sn} | {tr} | {com} |")
    if ins:
        L += ["", "## Inserts", ""]
        for i in ins:
            if i["kind"] == "scene":
                src = i.get("source") or {}
                L.append(f"- **{i['id']}** scene {i.get('type')} {fmt_t(i['start'])} +{i['dur']} s, {i['mode']}{experimental(i)}, tone "
                         f"{scene_tone(i, s)}: {scene_text(i)}. What: {i['what']}. Why: {i['why']}. "
                         + (f"Source: {src.get('kind')}{' (' + src['ref'] + ')' if src.get('ref') else ''}. " if src else "")
                         + f"Transition {i.get('transition_in')}/{i.get('transition_out')}"
                         + (", subtitles hidden" if hides_subtitles(i) else "") + f". Status: {i['status']}")
                continue
            if i["kind"] == "callout":
                src = i.get("source") or {}
                L.append(f"- **{i['id']}** callout {i.get('variant')} (experimental) {fmt_t(i['start'])} +{i['dur']} s: "
                         f"“{' / '.join((i.get('text') or {}).get('lines') or [])}”, "
                         + (f"dot on the {i['person']} person's shoulder" if i.get("person") else
                            f"dot from {i.get('anchor')} along {len(i['path'])} {'track points' if i.get('path_by') == 'track' else 'keys'}"
                            if i.get("path") else f"from {i.get('anchor')} to {i.get('to')}" if i.get("to") else
                            f"dot at {i.get('anchor')}")
                         + (f", ring r {i.get('radius'):g}" if i.get("radius") else "") + ", label "
                         f"{i.get('side')}{' below' if i.get('below') else ''}, tone {scene_tone(i, s)}. What: {i['what']}. "
                         f"Why: {i['why']}. " + (f"Source: {src.get('kind')}{' (' + src['ref'] + ')' if src.get('ref') else ''}. "
                                                 if src else "") + f"Status: {i['status']}")
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
        if any(experimental(i) for i in ins if i["kind"] == "scene"):
            L += ["", "**Experimental** scenes or modes: the kit draws them, but none is checked in a finished video yet; "
                      "look at their storyboard frames (`board.py`) before the full render."]
    keep = plan.get("keep_clear") or []
    if keep:  # cards, the hook, the CTA drawn per video: their texts are shown before the render too (SKILL.md step 8)
        L += ["", "## Graphics zones (keep_clear)", ""]
        L += [f"{n}. {fmt_t(k['start'])}-{fmt_t(k['end'])} {k.get('what', '')} box {k.get('box')}"
              + (f", camera {k['cam']}" if k.get("cam") else "")
              + (f", presenter layer {k['matte']} (counts in the coverage)" if k.get("matte") else "")
              + (f" (scene {k['scene']}, written by export)" if k.get("scene") else "")
              for n, k in enumerate(keep, 1) if not k.get("callout")]
        # a callout's label has a zone per 0.25 s for the audit: one line here (Fable review: ~10 lines a callout)
        L += [f"- callout {c} label: its box every 0.25 s on screen, written by export (`remove {c}` takes the callout)"
              for c in dict.fromkeys(k["callout"] for k in keep if k.get("callout"))]
        L += ["", "Remove a zone: `visual_plan.py keep-clear edit/<id> --remove N`."]
    defects, _ = load_defects(e)
    if defects:  # what the person sees about the picture: each defect and how it is handled
        s_, _p, doc_, _b, _br = current_settings(e, plan)
        _e, _w, state = defect_issues(e, plan, s_, doc_, load_json(e / "captions.json", {}))
        L += ["", "## Picture defects (defects.py)", ""]
        L += [f"- {d['id']} {d['kind']} {fmt_t(d['start'])}-{fmt_t(d['end'])}"
              + (f" «{d['words']}»" if d.get("words") else "") + f": {state.get(d['id'], 'open')}" for d in defects]
    hs = plan.get("hide_subtitles") or []
    if hs:
        L += ["", "## Subtitles hidden (hide-subs)", ""]
        L += [f"{n}. {fmt_t(h['start'])}-{fmt_t(h['end'])}" + (f": {h['why']}" if h.get("why") else "")
              for n, h in enumerate(hs, 1)]
        L += ["", "Remove a window: `visual_plan.py hide-subs edit/<id> --remove N`."]
    L += ["", f"Check: {len(errs)} error(s), {len(warns)} warning(s)."]
    L += [f"- error: {m}" for m in errs] + [f"- warning: {m}" for m in warns]
    out = e / "visual_plan.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out)


def scene_text(i):
    """The scene text on one line, for md, in full (the person approves every word on screen; T6 cut list items off
    at 70 characters) and with its caps label."""
    t = " / ".join((i.get("text") or {}).get("lines") or [])
    label = str((i.get("text") or {}).get("label") or "").strip()
    if i.get("items"):
        t = (t + ": " if t else "") + "; ".join(str(x.get("text", "")) for x in i["items"] if isinstance(x, dict))
    if i.get("type") == "stat" and i.get("value"):
        v = i["value"]
        t = f"{v.get('prefix', '')}{v.get('to')}{v.get('suffix', '')} " + t
    t = t or (i.get("interaction") or {}).get("text") or i.get("what", "")
    return (f"[{label}] " if label else "") + f"'{t}'"


def cmd_keep(a):
    """A zone that memes and windows don't cover: a card, the hook, the CTA, an object in hand. --remove N takes zones out
    (numbered as in visual_plan.md, from 1)."""
    e = edit_dir(a.edit)
    if a.remove:
        with editing_plan(e) as plan:
            keep = plan.get("keep_clear") or []
            bad = [n for n in a.remove if not 1 <= n <= len(keep)]
            if bad:
                sys.exit(f"keep_clear has {len(keep)} zone(s) (visual_plan.md numbers them): no {', '.join(map(str, bad))}")
            own = [n for n in a.remove if keep[n - 1].get("scene") or keep[n - 1].get("callout")]
            if own:
                k0 = keep[own[0] - 1]
                what = "a scene" if k0.get("scene") else "a callout"
                sys.exit(f"zone {', '.join(map(str, own))} belongs to {what} and export writes it back: remove {what} "
                         f"(visual_plan.py remove {a.edit} {k0.get('scene') or k0.get('callout')}) or move it")
            gone = [keep[n - 1] for n in sorted(set(a.remove))]
            plan["keep_clear"] = [k for n, k in enumerate(keep, 1) if n not in set(a.remove)]
        for k in gone:
            print(f"keep_clear removed: {k.get('what', '')} {k.get('box')} {fmt_t(k['start'])}-{fmt_t(k['end'])}")
        return
    if a.start is None or a.end is None or not a.box or not a.what:
        sys.exit("keep-clear: --from, --to, --box and --what are needed (or --remove N)")
    box = [int(x) for x in a.box.split(",")]
    entry = {"start": a.start, "end": a.end, "box": box, "what": a.what}
    if a.cam:  # the span's camera, so that validate checks the face where the viewer sees it
        entry["cam"] = [float(x) for x in a.cam.split(",")]
    if a.matte:  # a presenter layer (matte.py place): coverage, its WebM copied by export
        entry["matte"] = safe_slug(a.matte, "--matte", dots=True)
        if not (e / "matte" / f"{entry['matte']}.webm").exists():
            warn(f"no {e / 'matte' / (entry['matte'] + '.webm')}: export has nothing to copy until matte.py cut makes it")
    if a.own_face:  # the presenter's own face on screen: not a no-go for its own layer
        entry["own_face"] = [int(x) for x in a.own_face.split(",")]
        if len(entry["own_face"]) != 4:
            sys.exit("--own-face: x,y,w,h")
    with locked(plan_path(e)):
        plan = load_json(plan_path(e))
        if plan is None:  # inserts are off and no plan was built: a plan without inserts is created (a graphics registry)
            s, prov, doc, bdir, brand = current_settings(e)
            plan = auto_plan(e, load_json(e / "captions.json"), s, prov, doc)
            print(f"there was no plan: created {plan_path(e)} without inserts (spans and keep_clear only)")
        plan.setdefault("keep_clear", []).append(entry)
        save_json(plan_path(e), plan)
    print(f"keep_clear: {a.what} {box} {fmt_t(a.start)}-{fmt_t(a.end)}")
    import faces as fc
    data = fc.load(e)
    if data and a.matte:  # a presenter layer: the rough cut is not visible under it, the face in it is the presenter's own
        print("presenter layer: counts in the inserts' coverage; the face in it is the presenter's own (not checked)")
    elif data:
        # the face where the viewer sees it: --cam for this zone, else camera.json at each sample's time (as validate
        # and the render audit see it; T4: keep-clear without --cam checked the box against the uncropped frame)
        cam = [float(x) for x in a.cam.split(",")] if a.cam else None
        faces_, how_ = faces_seen(e, plan, data, a.start, a.end, cam, shots_ok=not cam)
        shots = how_ == "camera.json"
        hit = [b for b in faces_ if fc.inter(box, fc.grow(b, fc.MARGIN))]
        how = ", with the camera" if cam else ", with the camera of camera.json" if shots else ", without a camera"
        print(f"warning: '{a.what}' touches the face (margin {fc.MARGIN} px{how}): {fc.union(hit)}: move it to a zone "
              f"from faces.py zones" if hit else f"the face is not touched (per faces.json{how})")


def cmd_hide(a):
    """Windows where the subtitles are hidden by something the plan doesn't hold as a scene (a presenter over a scene, an
    accent title in a per-video composition): export puts them into props.hideSubtitles, faces.py audit reads them.
    --remove N takes windows out (numbered as in visual_plan.md, from 1)."""
    e = edit_dir(a.edit)
    ensure_plan(e)  # a plain edit has no init (SKILL.md step 7a)
    with editing_plan(e) as plan:
        hs = plan.setdefault("hide_subtitles", [])
        if a.remove:
            bad = [n for n in a.remove if not 1 <= n <= len(hs)]
            if bad:
                sys.exit(f"hide_subtitles has {len(hs)} window(s) (visual_plan.md numbers them): no {', '.join(map(str, bad))}")
            gone = [hs[n - 1] for n in sorted(set(a.remove))]
            plan["hide_subtitles"] = [h for n, h in enumerate(hs, 1) if n not in set(a.remove)]
        else:
            if a.start is None or a.end is None or a.end <= a.start:
                sys.exit("hide-subs: --from and --to (--to after --from) are needed, or --remove N")
            dur = plan.get("duration")
            if dur and (a.start < 0 or a.end > float(dur) + 0.05):
                sys.exit(f"hide-subs: {a.start}-{a.end} is outside the video (0-{dur})")
            gone = []
            hs.append({"start": round(a.start, 3), "end": round(a.end, 3), **({"why": a.why} if a.why else {})})
            hs.sort(key=lambda h: h["start"])
    for h in gone:
        print(f"hide_subtitles removed: {fmt_t(h['start'])}-{fmt_t(h['end'])} {h.get('why', '')}".rstrip())
    if not a.remove:
        print(f"hide_subtitles: {fmt_t(a.start)}-{fmt_t(a.end)}" + (f" ({a.why})" if a.why else "")
              + "; export puts it into props.hideSubtitles, faces.py audit reads it")


def hidden_windows(plan):
    """The plan's own subtitle-hide windows (hide-subs), as [start, end]."""
    return [[h["start"], h["end"]] for h in plan.get("hide_subtitles") or []]


def cmd_remove(a):
    """Take inserts (B-roll, memes, scenes) out of the plan, with the zones export wrote for those scenes. To change an
    insert: remove it and add it again (T1 edited visual_plan.json by hand five times for want of this)."""
    e = edit_dir(a.edit)
    with editing_plan(e) as plan:
        have = {i["id"] for i in plan["inserts"]}
        missing = [x for x in a.ids if x not in have]
        if missing:
            sys.exit(f"no insert {', '.join(missing)} in the plan (there are: {', '.join(sorted(have)) or 'none'})")
        gone = [i for i in plan["inserts"] if i["id"] in a.ids]
        plan["inserts"] = [i for i in plan["inserts"] if i["id"] not in a.ids]
        if plan.get("keep_clear"):
            plan["keep_clear"] = [k for k in plan["keep_clear"] if k.get("scene") not in a.ids and k.get("callout") not in a.ids]
    for i in gone:
        print(f"removed {i['id']}: {i['kind']} {i.get('type') or i.get('mode')} {fmt_t(i['start'])} +{i['dur']} s: {i['what']}")
    print("files the inserts used stay where they are; validate and export again")


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


def source_files(e):
    """cut.json sources: {key: file}, so that a shot may name its source by the key or by the file."""
    doc = load_json(Path(e) / "cut.json", {}) or {}
    out = {}
    for k, v in (doc.get("sources") or {}).items():
        f = v.get("file") if isinstance(v, dict) else v
        if f:
            out[str(k)] = str(f)
    return out


def same_source(a, b, files=None):
    """A shot's "source" names a segment's source: the same path, file name or stem, or the cut.json key of that
    file (captions.json segments carry the key; T2: "source": "<file>.MOV" against segments of "front" failed
    the export)."""
    a, b = str(a or ""), str(b or "")
    if not (a and b):
        return False

    def names(x):
        out = {x, Path(x).name, Path(x).stem}
        if files and x in files:
            out |= {files[x], Path(files[x]).name, Path(files[x]).stem}
        return out
    return bool(names(a) & names(b))


def src_to_out(src, cap, seg=None, source=None, files=None, quiet=False):
    """A source second -> the second of the finished video (captions.json segments; references/camera.md, at()).
    source: the shot's file or source key, for a cut from several cameras whose source seconds overlap."""
    pool = [g for g in cap.get("segments", []) if (seg is None or g["i"] == seg)
            and (source is None or same_source(source, g.get("source"), files))]
    if source is not None and not pool:
        sys.exit(f"camera.json: no segment of the rough cut comes from {source}")
    hit = [g for g in pool if g["src_start"] - 0.001 <= src <= g["src_end"] + 0.001]
    if not hit:
        # an edge moved by a few frames (a recut): a shot set on a segment start lands just before it; it follows
        nxt = [g for g in pool if src < g["src_start"] <= src + 0.25]
        if not nxt:
            sys.exit(f"camera.json: source second {src} was cut out")
        g = min(nxt, key=lambda x: x["src_start"])
        if not quiet:
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
    if doc.get("translation") != subs.translation_id(load_json(subs.subs_file(e, lang))):
        sys.exit(f"subtitles_lang={lang}: the translation in subs/{lang}.json changed after {f.name} was made (or the "
                 f"last apply refused it): subs.py apply {e} --lang {lang}")
    print(f"subtitles: {lang} ({f.name})")
    return doc


def camera_shots(e, plan, cap, quiet=False):
    """edit/<id>/camera.json -> ReelKit props.camera: shots in seconds of the finished video, sorted.
    {"shots": [{"src": 12.4 | "at": "word:resume#1" | 3.2, "z": 1.1, "cx": 540, "cy": 1000, "drift": 0.03, "whip": false}]}
    src: a source second (stable when the speed changes), with "source": "cam-a.mov" (a path, file name or stem,
    or the source key of cut.json) on a cut from several files; at: a second or a word of the finished video."""
    doc = load_json(e / "camera.json", None)
    if not doc:
        return []
    shots, files = [], source_files(e)
    for k, sh in enumerate(doc.get("shots", [])):
        t = (src_to_out(float(sh["src"]), cap, sh.get("seg"), sh.get("source"), files, quiet) if "src" in sh
             else resolve_at(str(sh.get("at", 0)), plan, cap))
        z = float(sh.get("z", 1.0))
        if z < 1:
            sys.exit(f"camera.json shot {k}: z {z} < 1 would show the frame edge")
        shots.append({"t": round(t, 3), "z": z, "cx": float(sh.get("cx", 540)), "cy": float(sh.get("cy", 960)),
                      "drift": float(sh.get("drift", 0)), "whip": bool(sh.get("whip"))})
    return sorted(shots, key=lambda x: x["t"])


def plan_camera(e, plan):
    """camera.json shots for the checks (validate): [] without camera.json, or when it does not resolve (export
    reports that)."""
    if not (Path(e) / "camera.json").is_file():
        return []
    try:
        return camera_shots(e, plan, load_json(Path(e) / "captions.json", {}) or {}, quiet=True)
    except SystemExit:
        return []


def camera_view(e, fdata=None):
    """The camera's clamp geometry (reels_common.cam_fit) for edit/<id>: in the "framed" format the window and the
    rough cut's cover in it (as faces.py maps faces and the kit draws the video); None: the whole frame."""
    fr = framed_at(e)
    if not fr:
        return None
    import faces as fc
    v = fc.view(fdata) if fdata and fdata.get("source") else None
    if v is None:
        src = framed_source(e)
        v = framed_view(fr["window"], src) if src else (fr["window"], fr["window"])
    return v


def camera_at(shots, t, end, fps=30, view=None):
    """The virtual camera (z, cx, cy) at second t, as ReelKit's cameraAt draws it: the shot's push-in (drift) grows
    over the shot, a whip blends from the previous shot over 7 frames, the window never shows past the video
    (view: the "framed" window, camera_view; None: the whole frame). None before the first shot (the frame as is)."""
    i = max((k for k, s in enumerate(shots) if s["t"] <= t + 1e-6), default=-1)
    if i < 0:
        return None

    def fit(z, cx, cy):
        return cam_fit(z, cx, cy, view)

    def shot_at(k, tt):
        s = shots[k]
        nxt = shots[k + 1]["t"] if k + 1 < len(shots) else end
        p = min(max((tt - s["t"]) / max(0.01, nxt - s["t"]), 0.0), 1.0)
        return fit(s["z"] * (1 + s.get("drift", 0) * p), s["cx"], s["cy"])

    cam = shot_at(i, t)
    p = (t - shots[i]["t"]) * fps / 7
    if not shots[i].get("whip") or i == 0 or p >= 1:
        return cam
    prev, k = shot_at(i - 1, shots[i]["t"]), 1 - (1 - max(0.0, p)) ** 3
    return tuple(a + (b - a) * k for a, b in zip(prev, cam))


def chin_on_screen(y, t, shots, view=None):
    """Where a source y lands on screen at second t: the shot's camera at its deepest drift (camera.md formula), clamped
    like the kit (view: the "framed" window, whose center the camera works around)."""
    s = next((x for x in reversed(shots) if x["t"] <= t + 1e-6), None)
    if not s:
        return y
    z, _, cy = cam_fit(s["z"] * (1 + s["drift"]), s["cx"], s["cy"], view)
    c = view[0][1] + view[0][3] / 2 if view else 960
    return (y - cy) * z + c


# ── Callouts (references/callouts.md, experimental): a dot on an object of the rough cut, a leader line, a label ──
# kit/anchor.ts holds the same numbers and functions (tests/scripts/test_callouts.py runs it with node against these)
CALLOUT = {"dot": 14, "core": 8, "stroke": 5, "reach": 90, "run": 48, "title_h": 70, "title_size": 52, "sub_h": 50,
           "sub_size": 34, "pad_x": 18, "tick": 16, "gap": 14, "badge_min": 150, "badge_max": 260, "badge_sub": 26}
CALLOUT_TIMES = {"dot": (0, 6), "line": (3, 11), "title": (8, 18), "sub": (11, 21), "out": 6, "calm_in": 14}
CALLOUT_VARIANTS = ["tag", "line", "badge", "ring", "dimension"]
CALLOUT_PEOPLE = ["left", "right", "center"]  # --person: which face of the frame, per sample (faces.json has no identity)
CALLOUT_RING = (24, 400)  # ring --radius, px of the rough cut
CALLOUT_INK = 3.0        # line: the text's contrast against the lightest (or darkest) 5 % of the picture under it
CALLOUT_SEEN = 0.8       # a moving anchor: the share of the callout's time its dot is visible, below it a warning
CALLOUT_MAX_W = 640      # px: a wider label is a sentence, not a name
CALLOUT_ZONE = (40, 220, 960, 1500)  # the label: the safe zone, 40 px off the left edge
CALLOUT_GAP_S = 0.6      # a second callout enters no sooner than this after the first (one element at a time)
CALLOUT_AT_ONCE = 2
CALLOUT_LINE_MARGIN = 20  # px around a face that the leader line keeps out of
HOOK_BOX = [60, 300, 900, 242]  # the kit's hook headline (ReelKit Hook: 100 px lines from y 300), first 2.4 s
DRIFT = 0.05


def drift_zoom(segs, t):
    """The template's drift at second t (no camera), as ReelKit's Footage draws it (kit/anchor.ts driftZoom): each span
    of the rough cut scales around the frame's center, 1 -> 1.05 on even spans and back on odd ones."""
    seg = next((g for g in segs if g["out_start"] <= t < g["out_start"] + g["out_dur"]), segs[-1] if segs else None)
    if not seg:
        return 1.0
    k = min(max((t - seg["out_start"]) / max(1e-6, seg["out_dur"]), 0.0), 1.0)
    return 1 + DRIFT * k if seg["i"] % 2 == 0 else 1 + DRIFT - DRIFT * k


def anchor_on_screen(x, y, t, shots, segs, drift, end, fps=30):
    """Where point (x, y) of the full-frame rough cut is on screen at second t (kit/anchor.ts anchorOnScreen): through
    camera.json's shots (x' = (x - cx) * z + 540, references/camera.md), else the template's drift, else in place."""
    if shots:
        cam = camera_at(shots, t, end, fps)
        if cam:
            z, cx, cy = cam
            return (x - cx) * z + 540, (y - cy) * z + 960
        return float(x), float(y)
    z = drift_zoom(segs, t) if drift else 1.0
    return 540 + (x - 540) * z, 960 + (y - 960) * z


def screen_to_frame(x, y, t, shots, segs, drift, end, fps=30):
    """anchor_on_screen backwards: the point of the rough cut that is at (x, y) on screen at second t."""
    if shots:
        cam = camera_at(shots, t, end, fps)
        if cam:
            z, cx, cy = cam
            return (x - 540) / z + cx, (y - 960) / z + cy
        return float(x), float(y)
    z = drift_zoom(segs, t) if drift else 1.0
    return 540 + (x - 540) / z, 960 + (y - 960) / z


def zoom_at(t, shots, segs, drift, end, fps=30):
    """The rough cut's scale on screen at second t (kit/anchor.ts zoomAt): a ring's radius grows with it."""
    if shots:
        cam = camera_at(shots, t, end, fps)
        return cam[0] if cam else 1.0
    return drift_zoom(segs, t) if drift else 1.0


def path_at(path, anchor, t):
    """A moving anchor at t seconds from the callout's start (kit/anchor.ts pathAt): rows [t, x, y, v, s] - the point
    on the rough cut, its visibility 0..1 and the object's scale - straight between rows, held past the ends.
    -> (x, y, v, s); without a path the anchor itself."""
    if not path:
        return float(anchor[0]), float(anchor[1]), 1.0, 1.0

    def row(r):
        return float(r[1]), float(r[2]), float(r[3]) if len(r) > 3 else 1.0, float(r[4]) if len(r) > 4 else 1.0
    if t <= path[0][0]:
        return row(path[0])
    for k in range(1, len(path)):
        if t <= path[k][0]:
            a, b = row(path[k - 1]), row(path[k])
            p = (t - path[k - 1][0]) / max(1e-6, path[k][0] - path[k - 1][0])
            return tuple(u + (w - u) * p for u, w in zip(a, b))
    return row(path[-1])


def callout_geometry(px, py, side, below, w, sub, variant="tag", r=0, to=None):
    """The callout around its anchor on screen (px, py), by variant (kit/anchor.ts calloutGeometry): tag - 45° to the
    elbow, level to the plate, which the line meets at the title's middle, the label `side` of the dot, up (or down,
    `below`); line - the level line going on under the title, no plate; badge - a circle of diameter w at the line's
    end; ring - a ring of radius r instead of the dot, the line leaving it at 45°; dimension - a line to `to` with end
    ticks, the label at its middle. segs: the drawn segments; r: the dot's or the ring's radius."""
    sy = 1 if below else -1
    h = CALLOUT["title_h"] + (CALLOUT["sub_h"] if sub else 0)
    if variant == "dimension" and to:
        qx, qy = to
        ln = max(1e-6, math.hypot(qx - px, qy - py))
        nx, ny = -(qy - py) / ln * CALLOUT["tick"], (qx - px) / ln * CALLOUT["tick"]
        mx, my = (px + qx) / 2, (py + qy) / 2
        # above (or under) a lying measure, beside an upright one, on `side` (Antigravity review: on the line)
        plate = ([mx + CALLOUT["gap"] if side != "left" else mx - CALLOUT["gap"] - w, my - h / 2, w, h]
                 if abs(qy - py) > abs(qx - px) else
                 [mx - w / 2, my + CALLOUT["gap"] if below else my - CALLOUT["gap"] - h, w, h])
        return {"dot": [px, py], "elbow": [mx, my], "end": [qx, qy], "plate": plate,
                "segs": [[[px, py], [qx, qy]], [[px - nx, py - ny], [px + nx, py + ny]],
                         [[qx - nx, qy - ny], [qx + nx, qy + ny]]],
                "r": 0}
    sx = -1 if side == "left" else 1
    ring = variant == "ring"
    ox, oy = (px + sx * r * math.sqrt(0.5), py + sy * r * math.sqrt(0.5)) if ring else (px, py)
    ex, ey = ox + sx * CALLOUT["reach"], oy + sy * CALLOUT["reach"]
    hx = ex + sx * CALLOUT["run"]
    x0 = hx if sx > 0 else hx - w
    end = [hx + sx * w, ey] if variant == "line" else [hx, ey]
    plate = ([x0, ey - CALLOUT["title_h"], w, h] if variant == "line" else [x0, ey - w / 2, w, w] if variant == "badge"
             else [x0, ey - CALLOUT["title_h"] / 2, w, h])
    return {"dot": [px, py], "elbow": [ex, ey], "end": end, "plate": plate,
            "segs": [[[ox, oy], [ex, ey]], [[ex, ey], end]], "r": r if ring else CALLOUT["dot"]}


def callout_entrance(tone_in, sub):
    """Frames until the callout is fully on screen at a tone whose scene entrance is tone_in frames (kit/anchor.ts)."""
    return math.ceil((CALLOUT_TIMES["sub"][1] if sub else CALLOUT_TIMES["title"][1]) * tone_in / CALLOUT_TIMES["calm_in"])


_WIDE = "WM" + _ru("428 429 416 42e 424 42b 41c")  # the widest capitals (Latin, and Russian Sh, Shch, Zh, Yu, F, Y, M)


def _text_w(text, size, upper=False, track=0.0):
    """A generous width of a line of text: the kit fits the text into the width given (fitSize), so a guess on the wide
    side keeps the drawn label inside the checked box."""
    import unicodedata
    w = 0.0
    for ch in (text.upper() if upper else text):
        if unicodedata.category(ch).startswith("M"):  # a combining mark (Thai vowels above, accents) takes no width
            continue
        f = (0.28 if ch == " " else 0.92 if ch in _WIDE else 0.62 if ch.isdigit() else
             (0.72 if ord(ch) > 0x7F else 0.68) if ch.isupper() else 0.58 if ch.islower() else
             # letters with no case (Thai, Arabic, Devanagari; CJK full width) and other non-ASCII signs (Fable
             # review: counted as 0.4 em, the label came out narrow and the kit shrank the title to fit it)
             (1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.62) if ord(ch) > 0x7F else 0.4)
        w += (f + track) * size
    return w


def callout_width(lines, variant="tag"):
    """The label's width, px: the title at 52 px bold, a second line in 34 px caps (+0.12 em), and the plate's padding;
    a badge: the circle's diameter, the number in 78 % of it and the caption (26 px caps, under the number, where the
    circle is ~90 % of its diameter wide) in 80 %, at least badge_min."""
    if variant == "badge":
        t = _text_w(lines[0], CALLOUT["title_size"]) / 0.78 if lines else 0.0
        s = _text_w(lines[1], CALLOUT["badge_sub"], upper=True, track=0.08) / 0.8 if len(lines) > 1 else 0.0
        return int(math.ceil(max(CALLOUT["badge_min"], t, s)))
    t = _text_w(lines[0], CALLOUT["title_size"]) if lines else 0.0
    s = _text_w(lines[1], CALLOUT["sub_size"], upper=True, track=0.12) if len(lines) > 1 else 0.0
    return int(math.ceil(max(t, s) + 2 * CALLOUT["pad_x"]))


def callout_side(x, w):
    """The side with room for the label (right first): the one where it stays inside the safe zone."""
    off = CALLOUT["reach"] + CALLOUT["run"]
    right, left = CALLOUT_ZONE[2] - (x + off + w), (x - off - w) - CALLOUT_ZONE[0]
    return "right" if right >= 0 or right >= left else "left"


def _seg_hits(p, q, box, m=0):
    """Does segment p-q pass through box (x, y, w, h) grown by m? Sampled every 4 px."""
    x, y, w, h = box[0] - m, box[1] - m, box[2] + 2 * m, box[3] + 2 * m
    n = max(1, int(math.hypot(q[0] - p[0], q[1] - p[1]) / 4))
    return any(x <= p[0] + (q[0] - p[0]) * k / n <= x + w and y <= p[1] + (q[1] - p[1]) * k / n <= y + h
               for k in range(n + 1))


def _segs_cross(s1, s2):
    """Do two segments ((x, y), (x, y)) cross or touch?"""
    (a, b), (c, d) = s1, s2

    def side(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 1e-9) - (v < -1e-9)

    def on(p, q, r):
        return min(p[0], q[0]) - 1e-9 <= r[0] <= max(p[0], q[0]) + 1e-9 and min(p[1], q[1]) - 1e-9 <= r[1] <= max(p[1], q[1]) + 1e-9
    d1, d2, d3, d4 = side(c, d, a), side(c, d, b), side(a, b, c), side(a, b, d)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    return any(x == 0 and on(*seg, pt) for x, seg, pt in ((d1, (c, d), a), (d2, (c, d), b), (d3, (a, b), c), (d4, (a, b), d)))


def _screen_box(b, t, shots, segs, drift, end):
    """A rough-cut box (x, y, w, h) on screen at second t, through the same camera or drift as an anchor."""
    x0, y0 = anchor_on_screen(b[0], b[1], t, shots, segs, drift, end)
    x1, y1 = anchor_on_screen(b[0] + b[2], b[1] + b[3], t, shots, segs, drift, end)
    return [x0, y0, x1 - x0, y1 - y0]


def callout_span(c, fps=30):
    """The seconds the kit draws a callout over: from frame round(start * fps), for round(dur * fps) frames (Codex
    review: the checks and the zones used the raw seconds)."""
    f0 = jround(c["start"] * fps)  # Math.round, as the kit counts frames (PR 32 review: round() took halves to even)
    return f0 / fps, (f0 + jround(c["dur"] * fps)) / fps


def callout_times(c, step=0.25, path=None):
    """The moments a callout is checked at: its start, every step on the grid, just before its end, and the times of
    its path's rows (between rows it moves straight, so its extremes are there; Codex review: a key between two samples
    carried the label onto a face and back unseen)."""
    t0, t1 = callout_span(c)
    ts = {round(t0, 3), round(t1 - 0.001, 3)} | {round(k * step, 3) for k in range(math.ceil(t0 / step), math.floor(t1 / step) + 1)
                                                if t0 <= k * step < t1}
    ts |= {round(t0 + r[0], 3) for r in (path or []) if t0 <= t0 + r[0] < t1}
    return sorted(ts)


# The picture under the dot must hold still: the anchor follows the virtual camera, not the footage's own movement.
# Measured on real clips (mean change of a 120 px patch from its first frame, levels of 255): a wall, a painting, a
# plant on a tripod shot 1-6; a handheld walk through a room 56-117; a microphone in a gesturing hand 92
CALLOUT_STILL = 10
CALLOUT_MOVES = 25


def _frames(f, start, dur, vf, size, fps=4, every=None):
    """The rough cut's frames over [start, start + dur], fps a second, through the filter vf, as raw bytes of `size`
    each -> (frames, why): why is None when at least 80 % of them decoded. every=N: every N-th frame of the 30 fps rough
    cut itself, counted from the first one at start, with no resampling - the frames track.py follows (a rough cut whose
    first frame sits at 0.021 s had the fps filter pick the frame before, 1/30 s off: 13 px on a fast pan)."""
    import subprocess
    if every:
        fps = 30 / every
    sel = (["-vf", "select=not(mod(n\\," + str(every) + "))," + vf, "-fps_mode", "passthrough"] if every
           else ["-vf", f"fps={fps},{vf}"])
    try:
        out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(f),
                              *sel, "-f", "rawvideo", "-"], capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as err:
        return [], f"ffmpeg failed ({type(err).__name__})"
    frames = [out.stdout[k:k + size] for k in range(0, len(out.stdout) - size + 1, size)]
    if out.returncode != 0 or len(frames) < max(2, int(dur * fps * 0.8)):
        return frames, f"final.mp4 did not decode ({len(frames)} of ~{int(dur * fps)} frames)"
    return frames, None


def path_frames(f, c):
    """The frames a moving anchor is checked on: every 6th of those track.py follows (5 a second), 360x640 gray."""
    return _frames(f, callout_span(c)[0], c["dur"], "scale=360:640,format=gray", 360 * 640, every=6)


def _patch(buf, x, y, W=360, n=40, scale=1.0):
    """An n x n patch of a W-wide gray frame around (x, y) of the 1080x1920 frame (3 px of it per pixel), sampled
    between pixels (bilinear): a path moves the patch by fractions of a pixel, and whole pixels alone made a path that
    follows its object exactly look like a slipping one. scale: the object's size against the first frame (a track's),
    the patch grows with it (Codex review: a box growing in place read as a slip at 25.7). Kept inside the frame."""
    H = len(buf) // W
    half = n / 2 * scale
    cx = min(max(x / 3, half), W - 1 - half)
    cy = min(max(y / 3, half), H - 1 - half)
    out = []
    for j in range(n):
        v = min(max(cy + (j - n / 2) * scale, 0.0), H - 1.001)
        iv, fv = int(v), v - int(v)
        r0, r1 = iv * W, (iv + 1) * W
        for i in range(n):
            u = min(max(cx + (i - n / 2) * scale, 0.0), W - 1.001)
            iu, fu = int(u), u - int(u)
            p = buf[r0 + iu] + (buf[r0 + iu + 1] - buf[r0 + iu]) * fu
            q = buf[r1 + iu] + (buf[r1 + iu + 1] - buf[r1 + iu]) * fu
            out.append(p + (q - p) * fv)
    return out


def _stat(p):
    return [p.stat().st_size, p.stat().st_mtime_ns] if p.is_file() else None


def callout_moves(c):
    """Whether the callout's anchor is more than one still point: a path (keys, a track) or a second point."""
    return bool(c.get("path") or c.get("to"))


def _point(p):
    return isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                       and math.isfinite(v) for v in p)


def path_issue(path, dur=None):
    """What is wrong with a callout's path (rows [t, x, y, v, s] from its start, t rising, v 0..1, s > 0), or None."""
    if path is None:
        return None
    if not isinstance(path, list) or not path:
        return "path: a list of rows [t, x, y, visibility, scale]"
    prev = None
    for r in path:
        if not (isinstance(r, list) and 3 <= len(r) <= 5
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in r)):
            return f"path row {r!r}: [t, x, y] and optionally the visibility 0..1 and the scale"
        if prev is not None and r[0] <= prev:
            return f"path: the times must rise ({r[0]:g} after {prev:g})"
        if len(r) > 3 and not 0 <= r[3] <= 1 or len(r) > 4 and r[4] <= 0:
            return f"path row {r!r}: the visibility is 0..1, the scale above 0"
        if r[0] < 0 or (isinstance(dur, (int, float)) and r[0] > dur + 0.05):
            return f"path: t {r[0]:g} is outside the callout (0-{dur} s from its start)"
        prev = r[0]
    return None


def track_key(e, c):
    """What a track was made from (track.py): the anchor, the callout's time, final.mp4 and the joints of the rough cut
    (captions.json spans: the track breaks there; Antigravity review: spans re-cut over the same file kept an old
    track valid); another one -> track again."""
    f = Path(e) / "final.mp4"
    st = f.stat() if f.is_file() else None
    joints = [g.get("out_start") for g in (load_json(Path(e) / "captions.json", {}) or {}).get("segments", [])]
    return [c.get("anchor"), c.get("start"), c.get("dur"), st.st_size if st else None, st.st_mtime_ns if st else None,
            hashlib.sha1(json.dumps(joints).encode()).hexdigest()[:12]]


def picture_motion(e, c, keep=False, fresh=None, ctx=None, color=None):
    """How much the rough cut changes under the callout's dot over its time: the largest mean difference of a 120 px
    patch around the anchor, 4 times a second, from its first frame (levels of 255), on the frame stretched to
    1080x1920 as the kit draws it. A moving anchor (keys, a track): the patch follows the path, from its first visible
    frame, so a path that slips off its object shows the same way as a still dot on a moving picture; a dimension: both
    ends. -> (value, None), or (None, why) when it cannot be measured. keep (add): the value goes into the callout
    ("motion") and is reused while the anchor, the time and final.mp4 stay the same; fresh (validate): a fresh
    measurement goes there by id instead, and validate keeps it in the plan under its own lock (Codex review: an
    in-memory one blocked the status from being saved; Fable review: without it ffmpeg ran on every validate).
    The `line` variant (text with no plate) also gets "ink": its text's contrast against the picture under it (ctx:
    callout_context, for the camera; color: the text's, else the brand's text_on_primary)."""
    import hashlib
    f = Path(e) / "final.mp4"
    if not f.is_file():
        return None, "no final.mp4"
    if not shutil.which("ffmpeg"):
        return None, "no ffmpeg"
    st = f.stat()
    key = [c["anchor"], c["start"], c["dur"], st.st_size, st.st_mtime_ns]
    line = c.get("variant") == "line"
    if line and color is None:
        color = (((load_config(e)[4] or {}).get("colors") or {}).get("text_on_primary") or "#FFFFFF")
    extra = ([c.get("path"), c.get("to")] if callout_moves(c) else []) + ([
        c.get("side"), bool(c.get("below")), c.get("w"), (c.get("text") or {}).get("lines"), color,
        ctx[1] if ctx else None, ctx[2] if ctx else None, c.get("person"),
        _stat(Path(e) / "faces.json") if c.get("person") else None] if line else [])
    if extra:
        key.append(hashlib.sha1(json.dumps(extra, sort_keys=True, default=str).encode()).hexdigest()[:16])
    if (c.get("motion") or {}).get("key") == key:
        return c["motion"]["v"], None
    if not callout_moves(c):
        r, n = 60, 40
        x0 = min(max(0, int(c["anchor"][0]) - r), 1080 - 2 * r)
        y0 = min(max(0, int(c["anchor"][1]) - r), 1920 - 2 * r)
        frames, why = _frames(f, c["start"], c["dur"], f"scale=1080:1920,crop={2 * r}:{2 * r}:{x0}:{y0},scale={n}:{n},format=gray", n * n)
        if why:
            return None, why
        v = round(max(sum(abs(a - b) for a, b in zip(frames[0], fr)) / (n * n) for fr in frames[1:]), 1)
    else:
        # every 6th frame of the 30 fps rough cut (5 a second), the frames track.py follows, so the moment sampled is
        # the moment of the path (at 4 a second every other sample fell between frames: ~2 px on a pan, a "slip")
        frames, why = path_frames(f, c)
        if why:
            return None, why
        pts = [lambda t: path_at(c.get("path"), c["anchor"], t)]
        if c.get("to"):
            pts.append(lambda t: (c["to"][0], c["to"][1], 1.0, 1.0))
        v = 0.0
        for pt in pts:
            ref = None
            for k, buf in enumerate(frames):
                x, y, vis, sc = pt(k / 5)
                if vis < 0.5:  # hidden there: the object is lost or out of the shot
                    continue
                p = _patch(buf, x, y, scale=sc)
                # each patch against its own mean: a phone brightens or darkens the whole picture as it pans, which
                # is not the path slipping (Antigravity review: +0.12 brightness read as 28 of 255)
                mp = sum(p) / len(p)
                p = [q - mp for q in p]
                if ref is None:
                    ref = p
                    continue
                v = max(v, sum(abs(a - b) for a, b in zip(ref, p)) / len(p))
        v = round(v, 1)
    rec = {"v": v, "key": key}
    if line:
        rec["ink"] = label_contrast(f, c, ctx, color)
    if keep:
        c["motion"] = rec
    if fresh is not None:
        fresh[c["id"]] = rec
    return v, None


def label_contrast(f, c, ctx, color):
    """The `line` variant's text against the picture under its label, as the kit draws it (through the camera or the
    drift, the label moving with its anchor): per frame 4 times a second, the contrast (WCAG) of the text color against
    the lightest and the darkest 5 % of the label's box -> the lowest, or None when it cannot be measured."""
    try:
        tr, tg, tb = (int(str(color).lstrip("#")[k:k + 2], 16) / 255 for k in (0, 2, 4))
    except ValueError:
        return None
    lt = srgb_lum(tr, tg, tb)
    W, H = 270, 480
    frames, why = _frames(f, callout_span(c)[0], c["dur"], f"scale={W}:{H}:flags=area,format=rgb24", W * H * 3)
    if why or not ctx:
        return None
    segs, shots, drift, end = ctx[:4]
    t0 = callout_span(c)[0]
    worst = None
    for k, buf in enumerate(frames):
        t = t0 + k / 4
        g = callout_at(c, t, ctx)
        if g["v"] <= 0:
            continue
        x, y, w, h = g["plate"]
        lums = []
        for yy in range(int(y), int(y + h), 6):
            for xx in range(int(x), int(x + w), 8):
                fx, fy = screen_to_frame(xx, yy, t, shots, segs, drift, end)
                if not (0 <= fx < 1080 and 0 <= fy < 1920):
                    continue
                o = (int(fy / 4) * W + int(fx / 4)) * 3
                lums.append(srgb_lum(buf[o] / 255, buf[o + 1] / 255, buf[o + 2] / 255))
        if not lums:
            continue
        lums.sort()
        for lb in (lums[int(len(lums) * 0.05)], lums[min(len(lums) - 1, int(len(lums) * 0.95))]):
            cr = (max(lt, lb) + 0.05) / (min(lt, lb) + 0.05)
            worst = cr if worst is None else min(worst, cr)
    return None if worst is None else round(worst, 2)


def motion_note(v, why=None, moving=False):
    """The measurement in words, for add and validate; moving: the dot follows a path (keys, a track)."""
    if v is None:
        return f"the picture under the dot is not measured ({why}): check it on the stills"
    if v <= CALLOUT_STILL:
        return f"the picture under the dot holds still ({v:g} of 255)" + (" along its path" if moving else "")
    if v <= CALLOUT_MOVES:
        return f"the picture under the dot changes a little ({v:g} of 255): someone passes or the light changes? check the stills"
    if moving:
        return (f"the picture under the dot changes along its path ({v:g} of 255, still is <= {CALLOUT_STILL}): the "
                f"path slips off the object (keys too far apart, a track that lost it, the object turning): fix the "
                f"keys, track it again, or shorten the callout")
    return (f"the picture moves under the dot ({v:g} of 255, still is <= {CALLOUT_STILL}): the object leaves the dot "
            f"(a handheld shot, a moving hand): follow it with track.py or --keys (references/callouts.md), pick a still "
            f"stretch, or B-roll or a card instead")


def hook_lines(text, n=14):
    """How many lines the kit's hook headline takes: Phrase.tsx breakLines over glue, words that must not part
    (reels_common.no_break) kept together, lines of up to n characters."""
    from reels_common import no_break
    lines = 0
    for para in str(text).split("\n"):
        w, toks = para.split(), []
        for k, x in enumerate(w):
            if toks and no_break(w[k - 1], x):
                toks[-1] += " " + x
            else:
                toks.append(x)
        cur = None
        for tok in toks:
            if cur is not None and len(cur) + 1 + len(tok) <= n:
                cur += " " + tok
            else:
                lines += cur is not None
                cur = tok
        lines += cur is not None
    return max(1, lines)


def callout_context(e, plan, fdata=None):
    """What places a callout on screen: (captions' spans, camera.json shots, drift on, the video's length, a cache of
    the people's paths with faces.json, read when a callout points at a person)."""
    cap = load_json(Path(e) / "captions.json", {}) or {}
    shots = plan_camera(e, plan)
    return (cap.get("segments") or [], shots, not shots, plan.get("duration") or cap.get("duration") or 0.0,
            {"e": e, "faces": fdata, "paths": {}})


# --person: the dot goes to the shoulder on the label's side, under the face: 0.85 of the face's width out from its
# middle, 1.25 of its height down from its top (a label clear of the face, its line clear of it too)
PERSON_SIDE, PERSON_DOWN = 0.85, 1.25


def person_path(c, fdata):
    """A callout pointing at a person: the shoulder on the label's side of the face picked in each sample of faces.json
    (the left, the right or the central face of the frame: the measurement has no identity), averaged with the
    neighbouring samples; where there is no face the dot is hidden and held. -> rows [t, x, y, v] from the callout's
    start; [] when no sample has a face; None without faces.json."""
    if not fdata:
        return None
    t0, t1 = callout_span(c)
    st = fdata.get("step", 0.25)
    sx = -1 if c.get("side") == "left" else 1
    pick = {"left": lambda f: f[0] + f[2] / 2, "right": lambda f: -(f[0] + f[2] / 2),
            "center": lambda f: abs(f[0] + f[2] / 2 - 540)}.get(c.get("person"), lambda f: -f[2] * f[3])
    pts = []
    for smp in fdata.get("samples", []):
        if not t0 - st - 1e-6 <= smp["t"] <= t1 + st + 1e-6:
            continue
        f = min(smp["faces"], key=pick) if smp["faces"] else None
        pts.append((smp["t"], (f[0] + f[2] / 2 + sx * PERSON_SIDE * f[2], f[1] + PERSON_DOWN * f[3]) if f else None))
    seen = [k for k, (_, p) in enumerate(pts) if p]
    if not seen:
        return []
    rows = []
    for k, (t, p) in enumerate(pts):
        if p:
            near = [pts[j][1] for j in (k - 1, k, k + 1) if 0 <= j < len(pts) and pts[j][1]]
            rows.append([round(t - t0, 3), round(sum(q[0] for q in near) / len(near), 1),
                         round(sum(q[1] for q in near) / len(near), 1), 1])
        else:  # held where the face was last (or first) seen
            j = max([s for s in seen if s < k] or [min(seen)])
            q = rows[j][1:3] if j < k else list(pts[j][1])
            rows.append([round(t - t0, 3), round(q[0], 1), round(q[1], 1), 0])
    return rows


def callout_path(c, ctx):
    """The anchor's path: keys or a track from the plan, or a person's from faces.json (cached in ctx)."""
    if not c.get("person"):
        return None if path_issue(c.get("path"), c.get("dur")) else c.get("path")  # a broken one: validate names it
    cache = ctx[4]
    k = (c["id"], c.get("person"), c.get("side"), c.get("start"), c.get("dur"))
    if k not in cache["paths"]:
        if cache["faces"] is None:
            import faces as fc
            cache["faces"] = fc.load(cache["e"]) or {}
        cache["paths"][k] = person_path(c, cache["faces"])
    return cache["paths"][k]


def callout_at(c, t, ctx):
    """The callout's geometry on screen at second t, with "v": how visible it is there (0: hidden, the anchor lost)."""
    segs, shots, drift, end = ctx[:4]
    lines = (c.get("text") or {}).get("lines") or []
    x, y, v, sc = path_at(callout_path(c, ctx), c["anchor"], t - callout_span(c)[0])
    ax, ay = anchor_on_screen(x, y, t, shots, segs, drift, end)
    to = (anchor_on_screen(c["to"][0], c["to"][1], t, shots, segs, drift, end)
          if c.get("variant") == "dimension" and _point(c.get("to")) else None)
    r = (c.get("radius") or 0) * sc * zoom_at(t, shots, segs, drift, end)
    g = callout_geometry(ax, ay, c.get("side"), bool(c.get("below")), c.get("w") or callout_width(lines, c.get("variant")),
                         len(lines) > 1, c.get("variant") or "tag", r, to)
    g["v"] = v
    return g


def callout_keep_entries(e, plan):
    """keep_clear entries for ready callouts: the label's box on screen per 0.25 s, for faces.py audit and for the
    memes, windows and scenes the plan places later."""
    ctx = callout_context(e, plan)
    out = []
    for c in plan.get("inserts", []):
        if c.get("kind") != "callout" or c.get("status") != "ready":
            continue
        ts = callout_times(c, path=callout_path(c, ctx))
        for k, t0 in enumerate(ts[:-1]):
            t1 = ts[k + 1]
            gs = [callout_at(c, t, ctx) for t in (t0, (t0 + t1) / 2, t1)]
            boxes = [g["plate"] for g in gs if g["v"] > 0]  # not where its anchor is lost and the callout hidden
            if not boxes:
                continue
            x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
            x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
            box = [math.floor(x0), math.floor(y0), math.ceil(x1) - math.floor(x0), math.ceil(y1) - math.floor(y0)]
            end = round(callout_span(c)[1], 3) if k == len(ts) - 2 else t1
            out.append({"start": t0, "end": end, "box": box, "what": f"callout {c['id']} label", "callout": c["id"]})
    return out


def subtitle_top(e, s, cam, quiet=False):
    """The subtitles' top as the render puts it -> (top, band): below the measured chin (faces.json) through the
    camera, or allowing for the template's drift (up to x1.05 toward the frame center) without one."""
    import faces as fc
    import meme_layout as ml
    band = ml.layout(s).get("subtitles_band") or list(SUB_BAND)
    fdata = fc.load(e)
    top = SUB_TOP_KIT
    if fdata:
        geo = camera_view(e, fdata)
        # no camera: the template's drift (up to x1.05) toward the frame's center, or the framed window's (the kit's
        # fitCamera around the window center; Codex review: a custom window was scaled around y 960)
        cy = geo[0][1] + geo[0][3] / 2 if geo else 960
        boxes = [(s_["t"], b) for s_ in fdata["samples"] for b in s_["faces"]]
        # a weak box that passed the filter is still not trusted with the subtitles while confident faces exist (1789:
        # a 0.68 box on a shoulder gave a "chin" at 1939 and the top 1390; the real face's chin needed 1250)
        sure = [(t, b) for t, b in boxes if len(b) > 4 and b[4] >= fc.STRONG]
        boxes = sure or boxes
        chins = [(chin_on_screen(b[1] + b[3], t, cam, geo) if cam else (b[1] + b[3] - cy) * 1.05 + cy, t, b)
                 for t, b in boxes]
        if chins:
            low, lt, lb = max(chins, key=lambda c: c[0])
            need = round(low + fc.SUB_FACE_GAP)
            top = max(band[0], min(SUB_MAX_TOP, need))
            if not quiet:
                print(f"subtitles: top at y {top} (chin down to {round(low)} per faces.json: box "
                      f"{[round(v, 2) for v in lb[:5]]} at {lt:g} s)"
                      + (f"; WARNING: even at {SUB_MAX_TOP} the chin touches the subtitles: use a wider shot or a lower "
                         f"camera" if need > SUB_MAX_TOP else ""))
    return top, band


# "Typewriter" darkening (shade): its contrast target and the geometry of the kit (Subtitles.tsx: the gradient starts
# 220 px above the subtitles' top and is full at 40 % of its height; two lines of 56 px at line height 1.22 from x 60)
SHADE_TARGET = 4.5
SHADE_LINES = round(2 * 56 * 1.22)
SHADE_X = (60, 940)


_LIN = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (k / 1023 for k in range(1024))]


def srgb_lum(r, g, b):
    """Relative luminance of an sRGB color given as 0..1 channels (WCAG), through a 1024-step table."""
    return 0.2126 * _LIN[int(r * 1023 + 0.5)] + 0.7152 * _LIN[int(g * 1023 + 0.5)] + 0.0722 * _LIN[int(b * 1023 + 0.5)]


def cmd_shade(a):
    """The darkening behind "Typewriter" subtitles (reel.json subtitles_shade), measured: the rough cut's frames while
    the subtitles are on (spoken words, outside the windows where a scene hides them), the subtitle band through the
    camera of camera.json; for each value the contrast of the text color against the lightest 5 % of the band (the
    gradient as the kit draws it, blended over the frame as the browser does); the smallest value that gives
    SHADE_TARGET on the lightest frame. T3: the run guessed 0.55 for a white T-shirt; the docs said 0.15-0.25.
    --zone x,y,w,h or --scene ID measures any text zone instead (a style whose text sits in the headroom, like "bold"
    in a per-video composition: T5 measured it by hand): a FLAT darkening of the zone, on the frames of the scene's time
    (--scene) or --from/--to (else the whole video), against --target (3.0, large text, by default for a zone)."""
    import subprocess
    from reels_common import local_media_args
    e = edit_dir(a.edit)
    video = e / "final.mp4"
    if not video.exists():
        sys.exit(f"no {video}: the shade is measured on the rough cut (cut.py)")
    plan = load_json(plan_path(e)) or {}
    cap = load_json(e / "captions.json") or {}
    s, _, _, _, brand = load_config(e)
    color = a.color or ((brand or {}).get("colors") or {}).get("text_on_primary") or "#FFFFFF"
    try:
        tr, tg, tb = (int(color.lstrip("#")[k:k + 2], 16) / 255 for k in (0, 2, 4))
    except ValueError:
        sys.exit(f"--color {color!r}: a hex color like #FFFFFF")
    lt = srgb_lum(tr, tg, tb)
    if lt < 0.4:
        sys.exit(f"the text color {color} is dark: a darkening lowers its contrast; use a light backing instead")
    shots = plan_camera(e, plan)
    end = cap.get("duration") or plan_duration(e, plan) or 0
    zone, span, what = None, None, ""
    if a.scene:
        sc = next((i for i in plan.get("inserts", []) if i["id"] == a.scene and i.get("kind") == "scene"), None)
        if not sc:
            sys.exit(f"--scene {a.scene}: no such scene in the plan")
        kc = next((k for k in plan.get("keep_clear", []) if k.get("scene") == a.scene), None)
        zone = sc.get("box") or (kc or {}).get("box")
        if not zone:
            sys.exit(f"--scene {a.scene}: the scene has no box (a full-frame scene draws its own field); use --zone")
        span, what = (sc["start"], sc["start"] + sc["dur"]), f"scene {a.scene}"
    elif a.zone:
        try:
            zone = [int(float(v)) for v in a.zone.split(",")]
        except ValueError:
            zone = []
        if len(zone) != 4 or zone[2] <= 0 or zone[3] <= 0:
            sys.exit(f"--zone {a.zone}: x,y,w,h in 1080x1920")
        span, what = (a.start if a.start is not None else 0.0, a.end if a.end is not None else end), "the zone"
    target = a.target or (3.0 if zone else SHADE_TARGET)
    fr = framed_at(e)
    if fr and fr["subtitles_at"] == "below" and not zone:
        print("subtitles_at below: the subtitles sit on the field under the framed window, not over the video; no "
              "darkening is needed (the kit draws none there). Check the subtitle color against the field instead: "
              "export warns when they do not read")
        return
    top = a.top or (plan.get("subtitles_band") or [None])[0] or subtitle_top(e, s, shots, quiet=True)[0]
    if fr and not a.top:  # "framed": the block inside the window's text area, as export puts it (Codex review: before
        # the first export a short window [25,340,1030,800] was measured at y 1290, below the window, "no frame")
        a0, a1 = framed_sub_area(fr)[1], framed_sub_area(fr)[3]
        top = max(a0, min(top, a1 - SUB_BLOCK_H["typewriter"]))
    bottom = min(1500, top + SHADE_LINES)
    hidden = ([(i["start"], i["start"] + i["dur"]) for i in plan.get("inserts", []) if i.get("kind") == "scene"
               and i.get("status") == "ready" and i.get("type") != "cover" and hides_subtitles(i)]
              + [tuple(h) for h in hidden_windows(plan)])
    spoken = [(w["start"], w["end"] + 0.4) for w in cap.get("words", [])]
    W, H, fps = 270, 480, 4  # a quarter of the frame, 4 frames a second
    # where the rough cut lies on screen: the whole frame, or the "framed" window with the video's cover in it (a point
    # outside the window is the field, not the video, and is left out)
    geo = camera_view(e)
    win, (vx, vy, vw, vh) = geo if geo else ((0, 0, 1080, 1920), (0, 0, 1080, 1920))
    ccx, ccy = win[0] + win[2] / 2, win[1] + win[3] / 2
    if geo:
        src = framed_source(e) or (1080, 1920)
        W, H = max(2, round(src[0] / 4)), max(2, round(src[1] / 4))
    r = subprocess.run(local_media_args(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                                         f"fps={fps},scale={W}:{H}:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]),
                       capture_output=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + r.stderr.decode("utf-8", "replace")[-800:])
    size = W * H * 3
    g0, g1 = top - 220, top - 220 + 0.4 * (2140 - top)  # the gradient: 0 at g0, full from g1 down
    ys, xs = range(top, bottom, 4), range(SHADE_X[0], SHADE_X[1], 8)
    if zone:  # a flat darkening over the zone, not the subtitles' gradient
        x0, y0, zw, zh = zone
        ys, xs = range(max(0, y0), min(1920, y0 + zh), 4), range(max(0, x0), min(1080, x0 + zw), 8)
        g0, g1 = -2.0, -1.0
    frames = []
    for k in range(len(r.stdout) // size):
        t = k / fps
        if zone:
            if not span[0] <= t <= span[1]:
                continue
        elif not any(a0 <= t <= a1 for a0, a1 in spoken) or any(h0 <= t < h1 for h0, h1 in hidden):
            continue
        buf = r.stdout[k * size:(k + 1) * size]
        cam = camera_at(shots, t, end, view=geo) if shots else None
        z, cx, cy = cam or cam_fit(1.0, ccx, ccy, geo)
        px = []
        for y in ys:
            if not win[1] <= y < win[1] + win[3]:
                continue
            f = min(1.0, max(0.0, (y - g0) / (g1 - g0)))
            sy = min(H - 1, max(0, int(((y - ccy) / z + cy - vy) / vh * H)))
            for x in xs:
                if not win[0] <= x < win[0] + win[2]:
                    continue
                sx = min(W - 1, max(0, int(((x - ccx) / z + cx - vx) / vw * W)))
                o = (sy * W + sx) * 3
                px.append((buf[o] / 255, buf[o + 1] / 255, buf[o + 2] / 255, f))
        if px:
            frames.append((t, px))
    if not frames:
        sys.exit(f"no frame in {what} {span[0]:.2f}-{span[1]:.2f} s" if zone else
                 "no frame with subtitles on: no spoken words outside the hidden windows")
    def light(px, v):  # the lightest 5 % of the band under the darkening v
        lums = sorted(srgb_lum(rr * (1 - v * f), gg * (1 - v * f), bb * (1 - v * f)) for rr, gg, bb, f in px)
        return lums[min(len(lums) - 1, int(len(lums) * 0.95))]

    n_all, pick = len(frames), set()
    for v in (0.0, 0.5):  # the lightest frames, with and without a darkening (the gradient weighs the rows differently)
        pick |= {t for t, _ in sorted(frames, key=lambda fr: -light(fr[1], v))[:8]}
    frames = [fr for fr in frames if fr[0] in pick]
    current = s.get("subtitles_shade")
    values = sorted({round(v / 20, 2) for v in range(0, 19)} | ({float(current)} if current is not None else set()))
    rows = []
    for v in values:
        c, t = min(((lt + 0.05) / (light(px, v) + 0.05), t) for t, px in frames)
        rows.append((v, c, t))
    best = next((row for row in rows if row[1] >= target), None)
    if zone:
        print(f"shade: {what} x {zone[0]}-{zone[0] + zone[2]}, y {zone[1]}-{zone[1] + zone[3]}, {span[0]:.2f}-{span[1]:.2f} s, "
              f"{n_all} frames ({fps} a second{', the camera of camera.json' if shots else ''}); a flat darkening; text "
              f"{color}; the contrast against the lightest 5 % of the zone on the lightest frame (target {target}:1):")
    else:
        print(f"shade: the subtitle band y {top}-{bottom}, x {SHADE_X[0]}-{SHADE_X[1]}, {n_all} frames with subtitles on "
              f"({fps} a second{', the camera of camera.json' if shots else ''}; windows where scenes hide them left out); "
              f"text {color}; the contrast against the lightest 5 % of the band on the lightest frame:")
    for v, c, t in rows:
        if v in (0.0, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65) or (v == current and not zone) or (best and v == best[0]):
            mark = " <- reel.json now" if v == current and not zone else ""
            mark += " <- suggested" if best and v == best[0] else ""
            print(f"  {v:.2f}: {c:4.1f}:1 (the lightest frame {fmt_t(t)}){mark}")
    if not best:
        print(f"even 0.90 gives {rows[-1][1]:.1f}:1 < {target}:1: the background is too light for a darkening; "
              + ("put the text on a plate or a backing in the brand color" if zone else
                 "use the plate subtitles or a backing under them (references/typography.md)"))
        return
    if zone:
        print(f"{what}: a flat darkening of {best[0]:.2f} under the text ({best[1]:.1f}:1 >= {target}:1 on the lightest "
              f"frame {fmt_t(best[2])}); set it in the composition that draws this text")
        return
    print(f"reel.json subtitles_shade: {best[0]:.2f} ({best[1]:.1f}:1 >= {SHADE_TARGET}:1 on the lightest frame "
          f"{fmt_t(best[2])}) -> reelcfg.py save {a.edit} --set subtitles_shade={best[0]:.2f}")


def cmd_export(a):
    e = edit_dir(a.edit)
    errs, _ = cmd_validate(a, quiet=True)
    if errs and not a.force:
        for m in errs:
            print("error: " + m)
        sys.exit("the plan has errors: fix them (or use --force)")
    plan = load_plan(e)  # after validate the settings snapshot is current
    fin, notes, kept = finish_of(a, plan)  # hook, corner logo, end: this run's flags, else the last export's choice
    if notes:  # reviews 2026-10-18: a warning and a dropped card made the video 2.6 s shorter, and the next export was silent
        sys.exit("nothing exported, the plan is unchanged: " + "; ".join(notes))
    end = fin["end"] or {}
    if kept:
        print(f"kept from {'the last export' if plan.get('export') else 'the series preset'}: {', '.join(kept)} "
              f"(--no-hook, --no-corner, --no-end take them off)")
    rem = Path(a.remotion).resolve()
    if not (rem / "package.json").is_file() or not (rem / "src").is_dir():
        sys.exit(f"not a Remotion project (no package.json or src/): {rem}; nothing exported")
    name = safe_slug(a.name or plan["id"], "--name", dots=True)
    pub = inside(rem / "public", rem / "public" / name / "inserts", "inserts folder")
    out, skipped = [], []
    for i in plan["inserts"]:
        if i["kind"] in ("scene", "callout"):  # scenes and callouts: separate lists below
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
    callouts = []  # drawn by the kit's CalloutLayer from their fields (references/callouts.md)
    cctx = callout_context(e, plan)
    for i in plan["inserts"]:
        if i["kind"] != "callout":
            continue
        if i["status"] != "ready":
            sk.append(f"{i['id']} ({i['status']})")
            continue
        lines = (i.get("text") or {}).get("lines") or []
        callouts.append({"id": i["id"], "variant": i["variant"], "start": i["start"], "dur": i["dur"], "anchor": i["anchor"],
                         "path": callout_path(i, cctx) or None, "to": i.get("to"), "radius": i.get("radius"),
                         "side": i["side"], "below": bool(i.get("below")), "lines": lines,
                         "w": i.get("w") or callout_width(lines, i["variant"]), "tone": i.get("tone")})
    hide = sorted(hide + hidden_windows(plan))  # hide-subs: per-video compositions (a presenter, an accent title)
    # presenter layers (keep-clear --matte): the WebM goes next to the rough cut, where Presenter's src points
    # (matte.py place: "<id>/<name>.webm"); before, it was copied by hand
    for k in plan.get("keep_clear", []):
        if not k.get("matte"):
            continue
        m_src = e / "matte" / f"{safe_slug(k['matte'], 'keep_clear matte', dots=True)}.webm"
        m_dst = inside(rem / "public", rem / "public" / name / m_src.name, "matte copy")
        if not m_src.exists():
            warn(f"keep_clear '{k.get('what')}': no {m_src} (matte.py cut): the presenter has no figure to show")
            continue
        md = m_dst.stat() if m_dst.exists() else None
        if not md or md.st_size != m_src.stat().st_size or abs(md.st_mtime - m_src.stat().st_mtime) > 1:
            m_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(m_src, m_dst)
            print(f"matte: {m_src.name} -> public/{name}/{m_src.name}" + (" (updated)" if md else ""))
    # the plan's keep_clear: overlay/split/window scenes (a box on screen); validate (memes, windows) and faces.py audit see them
    # and the labels of ready callouts, per 0.25 s on screen
    entries = scene_keep_entries(plan) + callout_keep_entries(e, plan)
    if entries or any(k.get("scene") or k.get("callout") for k in plan.get("keep_clear", [])):
        with editing_plan(e) as p2:
            old = [k for k in p2.get("keep_clear", []) if not (k.get("scene") or k.get("callout"))]
            sc_k, co_k = scene_keep_entries(p2), callout_keep_entries(e, p2)
            new = old + sc_k + co_k
            if new != p2.get("keep_clear", []):
                p2["keep_clear"] = new
                print(f"keep_clear: {len(sc_k)} overlay/split/window scene(s), {len({k['callout'] for k in co_k})} "
                      f"callout label(s) (for faces.py audit)")
    save_json(rem / "src" / "plans" / f"{name}.json", {"id": name, "duration": plan["duration"], "inserts": out,
                                                     **({"scenes": scenes} if scenes else {})})
    print(f"src/plans/{name}.json: {len(out)} insert(s) go into the render" + (f"; no insert (fallback): {'; '.join(skipped)}" if skipped else "")
          + (f"; {len(scenes)} scene(s)" if scenes or any(x.startswith("c") for x in sk) else "")
          + (f"; {len(callouts)} callout(s)" if callouts else "") + (f" (not ready: {', '.join(sk)})" if sk else "")
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
                 "hideSubtitles": hide, "drift": True,
                 "hook": {"text": fin["hook"], "until": 2.4} if fin["hook"] else None, "corner": fin["corner"],
                 "endCard": {"line1": end["lines"][0], "line2": end["lines"][1] if len(end["lines"]) > 1 else None,
                             "seconds": END_CARD_S} if end.get("kind") == "card" else
                 {"line2": brand.get("tagline"), "seconds": END_CARD_S} if end.get("kind") == "sting" else None}
        cam = [] if only else camera_shots(e, plan, cap)
        if cam:
            props["camera"], props["drift"] = cam, False
            print(f"camera: {len(cam)} shot(s) from camera.json")
        import faces as fc
        top, band = subtitle_top(e, s, cam)
        fr = None if only else framed_at(e)
        if fr:
            # the framed format: ReelKit draws the window, the label and the video inside it (props.framed); the
            # field is the style's (brand.looks[style].field), else the primary color, as the kit's own field
            src = framed_source(e)
            if not src:
                sys.exit("format framed: the rough cut's size is unknown (no faces.json in source geometry, final.mp4 "
                         "unreadable): run faces.py scan, or rebuild final.mp4")
            look = ((brand.get("looks") or {}).get(str(props["style"] or "").lower()) or {})
            # a window over the whole screen is the 9:16 crop of the horizontal source: no rounded corners (the field
            # would show in the screen's corners)
            full = [int(v) for v in fr["window"]] == [0, 0, 1080, 1920]
            props["framed"] = {"window": fr["window"], "label": fr["label"], "source": list(src),
                               "radius": 0 if full else FRAMED_RADIUS,
                               "field": look.get("field") or (brand.get("colors") or {}).get("primary"),
                               **({"subtitles": "below"} if fr["subtitles_at"] == "below" else {})}
            print(f"framed: window {fr['window']}, source {src[0]}x{src[1]}"
                  + (f", label “{fr['label']}”" if fr["label"] else ", no label") + f", field {props['framed']['field']}"
                  + (", subtitles below the window" if fr["subtitles_at"] == "below" else ""))
        props["subtitlesTop"] = top
        if props["subtitles"] not in ("accent", "plate", "typewriter", "none"):
            mode = {"v2": "plate", "bar": "plate", "typewriter": "typewriter", "print": "typewriter"}.get(str(props["subtitles"]).lower())
            if not mode:
                warn(f"subtitles '{props['subtitles']}': the kit draws accent, plate and typewriter; accent is used")
            props["subtitles"] = mode or "accent"
        if not only:  # faces.py audit checks the render against the band it really has
            # the kit draws at most two lines (Subtitles.tsx): the band is the mode's two-line block from the top, above
            # the UI (T4: the band said 1250-1430 while a three-line phrase reached 1455)
            h = SUB_BLOCK_H.get(props["subtitles"], band[1] - band[0])
            low = fc.H - fc.UI_BOTTOM
            if fr:  # the subtitle block stays inside the window's text area (the kit lifts it the same way), or with
                # subtitles_at below right under the window, on the field (the chin is above it, inside the window)
                a0, a1 = framed_sub_area(fr)[1], framed_sub_area(fr)[3]
                low = min(low, a1)
                top = a0 if fr["subtitles_at"] == "below" else max(a0, min(top, a1 - h))
                props["subtitlesTop"] = top
                if fr["subtitles_at"] == "below" and props["subtitles"] == "typewriter":
                    from brand import contrast
                    ink = ((brand.get("colors") or {}).get("speakers") or [None])[0] or (brand.get("colors") or {}).get("text_on_primary") or "#FFFFFF"
                    field = props["framed"]["field"]
                    try:
                        ratio = contrast(ink, field) if field else None
                    except (ValueError, TypeError):
                        ratio = None
                    if ratio is not None and ratio < 4.5:
                        warn(f"subtitles below the window: the typewriter text {ink} on the field {field} is {ratio:.1f}:1 "
                             f"(4.5 needed): pick a darker field (brand.looks.<style>.field) or the plate mode")
            z = (s.get("profile_rules") or {}).get("safe_zone")
            if z and fin["corner"] and not fr:  # the corner logo inside the ad's zone (the kit's default top is 236)
                props["cornerTop"] = max(CORNER_BOX[1], z[1])
            below = bool(fr) and fr["subtitles_at"] == "below"
            if z and top + h > z[3] and below:  # never lifted into the window (Codex review): the window moves up
                warn(f"subtitles below the window: the block ends at y {top + h}, past the ad safe zone of profile "
                     f"{s['profile_rules']['id']} (y {z[3]}), and lifting it would put it over the picture: end the "
                     f"window at y <= {z[3] - h - FRAMED_SUB_GAP} (reelcfg.py save edit/<id> --set window=[...]), or "
                     f"keep the subtitles inside the window")
            elif z and top + h > z[3]:  # a paid ad: the platform's caption and button cover y > the safe zone's bottom
                lifted = max(z[1], z[3] - h)
                print(f"subtitles: lifted from y {top} to {lifted} for profile {s['profile_rules']['id']} (the ad safe "
                      f"zone ends at y {z[3]}); check the chin on the render: faces.py audit")
                top = lifted
                props["subtitlesTop"] = top
            with editing_plan(e) as p2:
                p2["subtitles_band"] = [top, min(low, top + h)]
        if s.get("subtitles_shade") is not None:
            props["subtitlesShade"] = float(s["subtitles_shade"])
        props["callouts"] = callouts  # callouts (kit/Callout.tsx); an older template ignores this prop
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
    else:  # a session ran export without --props and read the plans line as "done": no props, no render
        print(f"no --props: the template props (rough cut, subtitles, brand, scenes) are NOT written, the ReelKit render "
              f"needs them: add --props {(e / 'reelkit-props.json').as_posix()}")
    # what follows the cut, recorded once the export is through (during it end_tail() reads --sting/--card): validate
    # counts "the last 2 s" from the whole video's end. Codex review: written before the Remotion project check, a
    # failed export left an end card that the next validate counted
    # The full choice goes into "export" (the next export keeps it, finish_of); the markers are what validate and the
    # profile's items read (end_tail, end_now, profile_issues)
    with editing_plan(e) as p2:
        p2["export"] = fin
        for k, on in (("corner", fin["corner"]), ("hook", bool(fin["hook"]))):
            if on:
                p2[k] = True
            else:
                p2.pop(k, None)
        if end:
            p2["end_card"] = {"kind": end["kind"], "seconds": END_CARD_S}
        else:
            p2.pop("end_card", None)


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
    p.add_argument("--covers", nargs="+", metavar="DNN", help="picture defects this insert covers (defects.py: d01…)")
    g = p.add_argument_group("scene (--kind scene)")
    g.add_argument("--type", choices=list(SCENE_TYPES)); g.add_argument("--lines", nargs="+", metavar="LINE")
    g.add_argument("--accent"); g.add_argument("--label"); g.add_argument("--source-ref", help="where the text or number comes from")
    g.add_argument("--tone", help="the scene tone (calm, deadpan, cinematic, feature, punchy, hype, parody); without it, the video's tone")
    g.add_argument("--variant"); g.add_argument("--items-json"); g.add_argument("--value-json")
    g.add_argument("--media", help="a screenshot or a recording (copied to edit/<id>/inserts/)"); g.add_argument("--interaction-json")
    g.add_argument("--side", choices=["left", "right"], help="window (right by default) / panel (left): the speaker's side; callout: the label's side "
                        "(default: the one with room)")
    g.add_argument("--frame-at", type=float, help="cover: the video second under the cover (otherwise 1.0 s or poster.py pick)")
    g.add_argument("--sound", choices=SCENE_SOUNDS); g.add_argument("--hide-subtitles", action="store_true")
    g = p.add_argument_group("callout (--kind callout; also --variant tag|line|badge|ring|dimension, --lines, --side, "
                             "--tone, --source)")
    g.add_argument("--anchor", metavar="X,Y", help="the object's point on the 1080x1920 rough cut, where the dot goes")
    g.add_argument("--below", action="store_true", help="the label under the dot (default: above it)")
    g.add_argument("--keys", nargs="+", metavar="T:X,Y", help="a moving dot: points of the rough cut at seconds from the "
                   "callout's start, T:- hides it (a slow pan; a handheld shot: track.py)")
    g.add_argument("--person", choices=CALLOUT_PEOPLE, help="point at a person: the dot follows the shoulder under the "
                   "left, right or central face of faces.json")
    g.add_argument("--radius", type=float, help="ring: the ring's radius around the object, px of the rough cut")
    g.add_argument("--to", metavar="X,Y", help="dimension: the second end of what is measured")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("keep-clear"); p.add_argument("edit"); p.add_argument("--from", dest="start", type=float)
    p.add_argument("--to", dest="end", type=float); p.add_argument("--box", help="x,y,w,h in 1080x1920")
    p.add_argument("--what"); p.add_argument("--cam", help="z,cx,cy of the camera on this span")
    p.add_argument("--remove", type=int, nargs="+", metavar="N", help="remove zone N (numbered in visual_plan.md, from 1)")
    p.add_argument("--matte", help="a presenter layer: the matte.py name (counts in the coverage, export copies its WebM)")
    p.add_argument("--own-face", help="x,y,w,h: the presenter's own face on screen (not flagged in its own zone)")
    p.set_defaults(fn=cmd_keep)
    p = sub.add_parser("hide-subs", help="hide the subtitles in a window a per-video composition covers")
    p.add_argument("edit"); p.add_argument("--from", dest="start", type=float); p.add_argument("--to", dest="end", type=float)
    p.add_argument("--why"); p.add_argument("--remove", type=int, nargs="+", metavar="N",
                                            help="remove window N (numbered in visual_plan.md, from 1)")
    p.set_defaults(fn=cmd_hide)
    p = sub.add_parser("accept", help="leave a picture defect on purpose (defects.py), with a reason")
    p.add_argument("edit"); p.add_argument("ids", nargs="+", metavar="DNN"); p.add_argument("--why")
    p.add_argument("--remove", action="store_true", help="take the acceptance back")
    p.set_defaults(fn=cmd_accept)
    p = sub.add_parser("remove", help="take inserts out of the plan"); p.add_argument("edit")
    p.add_argument("ids", nargs="+", help="insert ids: c03, b01, m02")
    p.set_defaults(fn=cmd_remove)
    p = sub.add_parser("validate"); p.add_argument("edit")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--sting", action="store_true", help="a logo sting will follow the cut (export --sting): the last 2 s "
                                                        "count from the end of the whole video")
    g.add_argument("--card", action="store_true", help="an end card will follow the cut (export --card)")
    p.add_argument("--corner", action="store_true", help="the export will draw the corner logo (export --corner): the "
                                                         "brand counts as seen from the first frame")
    p.add_argument("--hook", action="store_true", help="the export will show a hook headline (export --hook): the video "
                                                       "counts as opening on its hook")
    p.set_defaults(fn=lambda a: sys.exit(1 if cmd_validate(a)[0] else 0))
    p = sub.add_parser("md"); p.add_argument("edit"); p.set_defaults(fn=cmd_md)
    p = sub.add_parser("shade", help="measure the darkening behind \"Typewriter\" subtitles (reel.json subtitles_shade)")
    p.add_argument("edit"); p.add_argument("--color", help="the subtitle text color (default: the brand's text_on_primary)")
    p.add_argument("--top", type=int, help="the subtitles' top y (default: the band export recorded, else the chin)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--zone", metavar="X,Y,W,H", help="measure a text zone instead of the subtitle band (a flat darkening)")
    g.add_argument("--scene", metavar="ID", help="measure the box of this scene, over its time (a flat darkening)")
    p.add_argument("--from", dest="start", type=float, help="--zone: from this second (default: the whole video)")
    p.add_argument("--to", dest="end", type=float, help="--zone: up to this second")
    p.add_argument("--target", type=float, help="the contrast to reach (default 4.5 for subtitles, 3.0 for a zone: large text)")
    p.set_defaults(fn=cmd_shade)
    p = sub.add_parser("export"); p.add_argument("edit"); p.add_argument("--remotion", required=True); p.add_argument("--name")
    p.add_argument("--force", action="store_true"); p.add_argument("--props", help="the props file for the template composition")
    p.add_argument("--subtitles", choices=["accent", "plate", "typewriter", "none"])
    # hook, corner logo and end are kept from the last export unless a flag changes them (finish_of)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--hook", help="the hook headline over the first 2.4 s (kept by later exports)")
    g.add_argument("--no-hook", action="store_true", help="take the hook headline off")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--card", nargs="+", metavar="LINE", help="the end card: 1-2 CTA lines")
    g.add_argument("--sting", action="store_true", help="a logo sting at the end: the logo with the brand line, 2.6 s, no CTA")
    g.add_argument("--no-end", action="store_true", help="take the end card or sting off")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--corner", action="store_true", help="the brand mark in the corner")
    g.add_argument("--no-corner", action="store_true", help="take the corner mark off")
    p.add_argument("--copy-video", action="store_true")
    p.set_defaults(fn=cmd_export)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
