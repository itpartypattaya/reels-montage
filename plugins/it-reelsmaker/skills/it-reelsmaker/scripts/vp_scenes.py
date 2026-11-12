"""The visual plan's designed scenes: their timing and reading time, boxes and free zones, add and check,
and what a stage hands the kit for them. Part of visual_plan.py, with no command line
of its own: the other scripts take these names from visual_plan."""
import filecmp, json, math, re, shutil, sys
from pathlib import Path

from reels_common import (FRAMED_HOOK_MIN, MEME_SIZES, SUB_BAND, SUB_BLOCK_H, SUB_TOP_KIT, edit_dir, framed_area,
                          framed_at, load_json, media_kind, probe, ui_zone, voice_mode, warn)
from vp_core import (HEADROOM_BAND, HEADROOM_MIN, SCENE_MODES, STATUSES, TRANSITIONS, WINDOW_DEFAULT, WINDOW_SLOTS,
                     current_settings, editing_plan, find_spoken, fmt_t, format_label, is_inside, item_time, jround,
                     near_match, no_footage, norm_words, overlap, plan_duration, read_need, resolve_at)
from vp_camera import (camera_at, camera_view, plan_camera)


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


def experimental(i):
    """' (experimental)' for a designed scene of an experimental type or in an experimental mode, else ''."""
    exp = i.get("kind", "scene") == "scene" and (i.get("type") in EXPERIMENTAL_SCENES or i.get("mode") in EXPERIMENTAL_MODES)
    return " (experimental)" if exp else ""


def text_zone(e):
    """(x0, y0, x1, y1) where boxes may go: the safe zone (ui_zone, from the left edge), or in the "framed" format the window's text
    area (reels_common.framed_area), and the zone's name for messages."""
    fr = framed_at(e)
    if fr:
        return tuple(framed_area(fr)), "the framed window's text area"
    return ui_zone(left=0), "the safe zone"


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
    # with --cam 1,540,960 got through validate and failed the render audit: the shot's push-in lifted the face into its margin
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
    wlist = [(t, w["start"]) for w in words if t0 - 0.3 <= w["start"] <= t1 for t in norm_words(w.get("text", ""))]
    j, out = 0, []
    for tok in toks:
        q = (norm_words(tok) or [""])[0]
        hit = None
        for i in range(j, len(wlist)):
            if wlist[i][0] == q:
                j, hit = i + 1, wlist[i][1]
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


def default_box(mode):
    return {"overlay": WINDOW_DEFAULT, "split": SPLIT_BOX, "window": WINDOW_SCENE_BOX}.get(mode)


VOICE_SUB_GAP = 40  # px: with the voice off camera a full scene's text ends this far above the subtitles' top (kit)


def subtitle_band_off_camera(plan, s):
    """With reel.json -> voice off_camera the subtitles stay on over full scenes: their band [top, bottom] (the one the
    last stage recorded, else the kit's default top with the mode's two-line block); None when the voice is on
    camera or the subtitles are off."""
    mode = str((s or {}).get("subtitles") or "accent")
    if voice_mode(s) != "off_camera" or mode == "none":
        return None
    b = (plan or {}).get("subtitles_band")
    if isinstance(b, list) and len(b) == 2:
        return [int(b[0]), int(b[1])]
    return [SUB_TOP_KIT, SUB_TOP_KIT + SUB_BLOCK_H.get(mode, max(SUB_BLOCK_H.values()))]


def voice_stage(band):
    """A full scene's zone with the voice off camera, as sceneStage in the kit draws it with textBottom: the safe
    zone's width from y 250 down to VOICE_SUB_GAP above the subtitles."""
    return [60, 250, 900, max(1, min(1200, band[0] - VOICE_SUB_GAP - 250))]


def hides_subtitles(sc, s=None):
    """Subtitles are hidden (as in SceneLayer of the scene kit): split/panel/window/full and slogan always; hook, quote
    and list by default (the scene text repeats the speech; a list over the video replaces it, two texts at once don't
    read) unless hide_subtitles=false is explicit; the rest per hide_subtitles. s: the video's settings; with reel.json
    -> voice off_camera (a narration) the subtitles stay on over every scene, full ones too, unless the scene sets
    hide_subtitles (its text repeats the narration): sceneHideIntervals in the kit with voiceMode off_camera."""
    if voice_mode(s) == "off_camera":
        return bool(sc.get("hide_subtitles"))
    if sc.get("mode") in ("split", "panel", "window", "full") or sc.get("type") == "slogan":
        return True
    if sc.get("type") in ("hook", "quote", "list") and sc.get("hide_subtitles") is not False:
        return True
    return bool(sc.get("hide_subtitles"))


def without_own(plan, sc):
    """The plan for checking a scene box: without the scene's own keep_clear entry (stage writes it)."""
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
        if mode not in ("overlay", "split", "window") or no_footage(plan):
            continue
        k = {"start": sc["start"], "end": round(sc["start"] + sc["dur"], 3), "box": sc.get("box") or default_box(mode),
             "what": f"scene {sc['id']} {sc.get('type')} ({mode})", "scene": sc["id"], "mode": mode}
        if mode == "split":
            k["cam"] = SPLIT_CAM
        elif mode == "overlay" and sc.get("cam"):
            k["cam"] = sc["cam"]
        out.append(k)
    return out


def add_scene(a):
    e = edit_dir(a.edit)
    cap = load_json(e / "captions.json", {})
    if not a.type:
        sys.exit("scene: --type is required (" + ", ".join(SCENE_TYPES) + ")")
    spec = SCENE_TYPES[a.type]
    variants = spec.get("variants") or []
    # T1: a hook added without --variant got through here and failed only at validate
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
        nofoot = no_footage(plan)  # "scenes only" or "scenes + voice": every scene is the picture, full
        if only and not re.fullmatch(r"-?\d+(\.\d+)?", a.at.strip()):
            sys.exit("'scenes only' format: there is no speech, so --at is in seconds only (3.0)")
        s, prov, doc, bdir, brand = current_settings(e, plan)
        start = round(resolve_at(a.at, plan, cap) + a.offset, 3)
        # the first mode of the type's own list: a slogan is full, not the experimental split (wave 3); the others
        # were already the first of their list
        mode = a.mode or ("full" if nofoot else spec["modes"][0])
        if mode not in SCENE_MODES:
            sys.exit(f"scene mode {mode}: allowed {', '.join(SCENE_MODES)}")
        if nofoot and mode != "full":  # T6: accepted here, refused only by validate
            sys.exit(f"{format_label(plan)} format: there is no speaker, so the mode is full only, not {mode}")
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
              "sound": a.sound, "hide_subtitles": bool(a.hide_subtitles) or (voice_mode(s) != "off_camera" and (
                  mode in ("split", "panel", "window", "full") or a.type in ("slogan", "hook", "quote", "list"))),
              "status": "planned", "fallback": "main footage"}
        if a.type == "cover" and a.frame_at is not None:
            sc["frame_at"] = round(a.frame_at, 3)  # the video second under the cover (the cover composition, stage -> cover.frameAt)
        if a.cam:
            sc["cam"] = [float(x) for x in a.cam.split(",")]
        if getattr(a, "covers", None):
            sc["covers"] = list(a.covers)
        if not nofoot and mode in ("overlay", "split", "window") and sc["box"] is None:
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
        if sc["box"] and not nofoot and mode in ("overlay", "split", "window"):
            for m in scene_box_issues(e, plan, sc, sc["box"]):
                warn(f"{sc['id']}: {m}: validate will refuse it; set --box or move the scene")
        plan["inserts"].append(sc)
        plan["inserts"].sort(key=lambda i: i["start"])
    if experimental(sc):
        print(f"{sc['id']}: {a.type} {mode} is experimental (the kit draws it, not yet checked in a finished video): say so "
              f"in the plan and look at its storyboard frame")
    print(f"{sc['id']}: scene {a.type} {mode} {fmt_t(start)} +{a.dur} s ({sc['segment'] or '-'}), tone {tone}, "
          f"transition {sc['transition_in']}/{sc['transition_out']}: {a.what}"
          + (f"; box {sc['box']}" if sc.get("box") else "") + ". Status planned -> ready after validate.")


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
        if no_footage(plan):
            errs.append(f"{format_label(plan)}: the plan has no scenes; the video would be an empty frame in the brand color")
        if not scenes:
            return errs, warns, bad
    import faces as fc
    import meme_layout as ml
    conf = doc.get("scenes") or {}
    R = conf.get("reading") or {}
    fps = conf.get("fps", 30)
    only = plan.get("format") == "scenes-only"
    nofoot = no_footage(plan)  # the scenes are the whole picture ("scenes only", "scenes + voice")
    framed = None if nofoot else framed_at(e)
    D = plan.get("duration") or 0.0
    tones = {k: v for k, v in (doc.get("scene_tones") or {}).items() if not k.startswith("_")}
    band = ml.layout(s, doc).get("subtitles_band", list(SUB_BAND))
    words_ok = bool((cap or {}).get("words"))
    voice_band = subtitle_band_off_camera(plan, s)

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
        elif nofoot and mode != "full":
            E(sc, f"{format_label(plan)} format: there is no speaker, so the mode is full only, not {mode}")
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
        for k, it in enumerate(items):  # items are checked for any scene: stage writes their times for the kit
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
        if typ == "hook" and mode == "full" and not nofoot and sc["dur"] > conf.get("hook_full_max_s", 1.5) + 1e-6:
            E(sc, f"full hook {sc['dur']} s > {conf.get('hook_full_max_s', 1.5)} s: the face disappears in the most "
                  f"important seconds (shorter, or overlay/split)")
        # 2. the reading-time floor: counted from the frame when the whole text is on screen and the entrance is over
        #    (as the scene kit draws it: text_full_on); spoken text doesn't leave earlier than the tone's hold after
        #    the last word. Timing: sceneTimeline in kit/scenes/tones.ts (a transition over a pause -> a cut).
        hold = T.get("hold", 0.4)
        cw = cap.get("words") if words_ok else []
        tl = scene_timeline(sc, T, mode, fps, cw, nofoot)
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
        if not nofoot and mode in ("overlay", "split", "window"):
            box = sc.get("box") or default_box(mode)
            for m in scene_box_issues(e, plan, sc, box, fdata):
                E(sc, m + ("" if sc.get("box") else " (the default box: set add ... --box)"))
            if mode == "overlay" and not hides_subtitles(sc, s) and fc.inter(box, [0, band[0], 1080, band[1] - band[0]]):
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
        if voice_band and mode == "full" and typ != "cover" and not hides_subtitles(sc, s):
            box = sc.get("box") or voice_stage(voice_band)
            if fc.inter(box, [0, voice_band[0], 1080, voice_band[1] - voice_band[0]]):
                E(sc, f"box {box} is on the subtitle band (y {voice_band[0]}-{voice_band[1]}): the narration's subtitles "
                      f"stay on over full scenes, so the scene text ends above y {voice_band[0] - VOICE_SUB_GAP} (a lower "
                      f"--box), or set --hide-subtitles when the scene's text repeats the narration")
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
                            f"(brand.py change {(brand or {}).get('slug')} colors.{fg}=...)")
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
    if not nofoot:
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
    if nofoot:
        so = conf.get("scenes_only") or {}
        lo, hi = so.get("duration", [15, 25])
        if only and not lo <= D <= hi:  # "scenes + voice": the narration's own length
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
            # "scenes + voice": between scenes the field still carries the narration's subtitles: a warning
            (errs if only else warns).append(
                f"{format_label(plan)}: scenes cover {cov:.1f} of {D} s ({cov / D * 100:.0f} %) < {need * 100:.0f} %: "
                f"put the scenes back to back, with no empty frame")
        vis = text_frames(tl, s, tones, fps, True)
        for (x, a0, a1), (y, b0, b1) in zip(vis, vis[1:]):
            empty = b0 - a1  # frames of bare field between the old text leaving and the new one entering
            if empty > JOIN_EMPTY_MAX:
                warns.append(f"{x['id']} -> {y['id']}: {empty} frames of empty field at the join (the text of {x['id']} "
                             f"has left at {fmt_t(a1 / fps)}, {y['id']} shows from {fmt_t(b0 / fps)}): more than "
                             f"{JOIN_EMPTY_MAX}, start {y['id']} where {x['id']} ends")
        if tl and (tl[0].get("type") != "hook" or tl[0]["start"] > (0.05 if only else 1.0)):
            warns.append(f"{format_label(plan)}: storyboard: the first scene is a hook starting at 0 s"
                         + ("" if only else " (or on the narration's first word)"))
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


def hidden_windows(plan):
    """The plan's own subtitle-hide windows (hide-subs), as [start, end]."""
    return [[h["start"], h["end"]] for h in plan.get("hide_subtitles") or []]


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
    sp["hide_subtitles"] = hides_subtitles(i, s)

    def clean(o):  # optional fields without null: in SceneSpec they are simply absent
        return {k: clean(v) for k, v in o.items() if v is not None} if isinstance(o, dict) else o
    return clean(sp)
