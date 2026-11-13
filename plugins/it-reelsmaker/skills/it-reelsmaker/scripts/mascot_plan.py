"""The brand mascot in the visual plan (references/mascot.md): its geometry, its pose track on the words, the mouth
from mouth.json, the plan checks and the per-frame plan the kit plays. Used by visual_plan.py and mascot.py, with no
command line of its own.

The plan's field (mascot.py plan writes it):
    "mascot": {"x": null, "y": null, "scale": null,   # the anchor (the point between the eyes) on screen; null: placed
               "facing": 1,                           #   in the lower left, above the subtitle band
               "from": 0.0, "to": null,               # on screen (seconds of the edit; to null: the video's end)
               "track": [{"at": "word:look#1", "t": 3.42, "pose": "point_left"}],   # pose changes on words
               "speaks": null}                        # [[a, b), ...] where the mouth moves; null: the whole narration
Everything is resolved here, in Python, at stage (props.mascot.frames); the kit only plays it.
"""
import hashlib, math, re
from pathlib import Path

from reels_common import SUB_BAND, brand_file, load_json
from vp_core import jround, resolve_at
from vp_scenes import scene_keep_entries, scene_tone

POSES = ["neutral", "talk", "point_left", "point_right", "point_up", "palm", "think", "surprise", "celebrate", "shrug",
         "wink"]
# a pose the mascot does not have -> the first it has of these; "name*" is that pose mirrored, only for a symmetric one
SUBST = {"talk": ["neutral"], "point_left": ["point_right*", "palm"], "point_right": ["point_left*", "palm"],
         "point_up": ["palm"], "palm": ["talk"], "think": ["talk"], "surprise": ["celebrate", "palm"],
         "celebrate": ["surprise", "palm"], "shrug": ["palm"], "wink": ["neutral"]}
LEVELS = ("off", "calm", "full")  # reel-defaults.json -> brand_tones.<preset>.mascot
LOUD = ("punchy", "hype", "parody")  # scene tones that may bounce (with brand_tones.<preset>.overshoot: true)
MIN_GAP_S = 0.8     # pose changes at most this often
EDGE_S = 0.3        # a gesture this close to a scene's entrance or exit competes with it (SKILL.md section 4)
BAND_GAP = 30       # px between the mascot's lowest point and the subtitle band
DEFAULT_H = 540     # px: the placed mascot's height when the room allows it
EASE_FRAMES, BOUNCE_FRAMES = 12, 14
BLINK_FRAMES = 3
TALK_MIN = 0.08     # an opening under this reads as a closed mouth (the kit's `talking`)
W, H = 1080, 1920


def level(s):
    """off | calm | full: how much mascot the brand tone allows."""
    v = (s.get("brand_tone") or {}).get("mascot")
    return v if v in LEVELS else "calm"


def geometry(brand, bdir):
    """The brand's mascot -> ({kind, box (w, h), anchor (x, y), poses, symmetric}, None) or (None, why)."""
    m = (brand or {}).get("mascot")
    slug = (brand or {}).get("slug") or "<slug>"
    if not isinstance(m, dict) or m.get("kind") not in ("drawn", "atlas"):
        return None, f"the brand has no mascot: brand.py mascot {slug} --drawn <component in the Remotion project>"
    src = m
    if m["kind"] == "atlas":
        p = brand_file(m.get("rig"), bdir) if m.get("rig") and bdir else None
        src = load_json(p, None) if p else None
        if not isinstance(src, dict):
            return None, f"the brand's mascot atlas {m.get('rig')} is not readable (mascot.py atlas writes it)"
        src = {"box": src.get("box"), "anchor": src.get("anchor"), "poses": list((src.get("poses") or {}).keys()),
               "symmetric": src.get("symmetric")}
    try:
        bw, bh = (float(v) for v in src["box"])
        ax, ay = (float(v) for v in src["anchor"])
        poses = [str(p) for p in src.get("poses") or []]
    except (KeyError, TypeError, ValueError):
        return None, (f"the brand's mascot has no box/anchor/poses: brand.py mascot {slug} --drawn {m.get('component')} "
                      f"reads them from the component")
    if bw <= 0 or bh <= 0 or not poses:
        return None, "the brand's mascot box is empty or it has no poses"
    return {"kind": m["kind"], "box": (bw, bh), "anchor": (ax, ay), "poses": poses,
            "symmetric": bool(src.get("symmetric"))}, None


def substitute(pose, geo):
    """-> (the pose drawn, mirrored): the mascot's own pose, else the table's stand-in, else neutral."""
    have = geo["poses"]
    if pose in have:
        return pose, False
    for alt in SUBST.get(pose, []):
        if alt.endswith("*"):
            if geo.get("symmetric") and alt[:-1] in have:
                return alt[:-1], True
        elif alt in have:
            return alt, False
    return ("neutral" if "neutral" in have else have[0]), False


# ── the narration and its mouth ──

def voice_track(e):
    """The track the viewer hears, on the edit's timeline: voice.wav (scenes over a recorded narration), else the rough
    cut's own audio (final.mp4, which stage copies to public/<id>/video.mp4)."""
    for name in ("voice.wav", "final.mp4"):
        if (Path(e) / name).is_file():
            return Path(e) / name
    return None


def file_stamp(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return "sha256:" + h.hexdigest()


def speech_words(e):
    """[(start, end)] of the spoken words in edit/<id>/captions.json (the edit's timeline)."""
    cap = load_json(Path(e) / "captions.json", {}) or {}
    return [(float(w["start"]), float(w["end"])) for w in cap.get("words") or []
            if isinstance(w, dict) and w.get("start") is not None and w.get("end") is not None
            and str(w.get("text", "")).strip()]


def words_stamp(words):
    """The words' times the mouth was gated by: a new transcript of the same audio makes mouth.json stale too."""
    return "sha256:" + hashlib.sha256(";".join(f"{a:.3f}-{b:.3f}" for a, b in words).encode()).hexdigest()


def load_mouth(e, fps=30):
    """-> (mouth.json or None, problem or None). Stale: its track changed (the stamp), the track is not the one the
    viewer hears now, or another frame rate."""
    e = Path(e)
    m = load_json(e / "mouth.json", None)
    if not isinstance(m, dict) or not isinstance(m.get("open"), list):
        return None, "no mouth.json"
    src = Path(m.get("source") or "")
    src = src if src.is_absolute() else e / src
    if not m.get("explicit") and voice_track(e) and voice_track(e).resolve() != src.resolve():
        return m, f"mouth.json was measured on {src.name}, the narration is now {voice_track(e).name}"
    if not src.is_file():
        return m, f"mouth.json: its track {src} is gone"
    if m.get("stamp") != file_stamp(src):
        return m, f"mouth.json is stale: {src.name} changed since it was measured"
    if m.get("words_stamp") and m["words_stamp"] != words_stamp(speech_words(e)):
        return m, "mouth.json is stale: the words of captions.json changed since it was measured"
    if int(m.get("fps") or 0) != fps:
        return m, f"mouth.json is at {m.get('fps')} fps, the kit at {fps}"
    return m, None


def voice_end(e, plan, mouth):
    if mouth:
        return mouth["frames"] / float(mouth["fps"])
    return float(plan.get("duration") or 0.0) if voice_track(e) else 0.0


# ── where it stands ──

def subtitle_band(plan, s, doc=None):
    """[top, bottom] of the subtitle band the mascot keeps clear of, or None without subtitles. One place to ask:
    the band the last stage recorded, else the layout's."""
    if plan.get("format") == "scenes-only" or str(s.get("subtitles") or "") == "none":
        return None
    if plan.get("subtitles_band"):
        return list(plan["subtitles_band"])
    import meme_layout as ml
    return list(ml.layout(s, doc).get("subtitles_band") or SUB_BAND)


def ui_safe_of(s, doc=None):
    import meme_layout as ml
    return ml.layout(s, doc)["safe"]


def placement(m, geo, band, safe):
    """-> (x, y, scale) of the anchor: the plan's own, else the lower left above the subtitle band (or above the UI
    zone with no subtitles), as tall as the room allows up to DEFAULT_H."""
    bw, bh = geo["box"]
    ax, ay = geo["anchor"]
    bottom = (band[0] - BAND_GAP) if band else (H - safe["bottom"])
    left = safe["left"] + 20
    sc = m.get("scale")
    if not sc:
        sc = min(DEFAULT_H, bottom - safe["top"] - 40) / bh
        sc = round(max(0.1, min(sc, (W / 2 - left) / bw)), 3)
    x = m.get("x") if m.get("x") is not None else math.ceil(left + (ax if m.get("facing", 1) == 1 else bw - ax) * sc)
    y = m.get("y") if m.get("y") is not None else math.floor(bottom - (bh - ay) * sc)
    return x, y, float(sc)


def rect(x, y, sc, geo, facing=1):
    """[x, y, w, h] of the mascot's box on screen; mirrored around the anchor when facing is -1."""
    bw, bh = geo["box"]
    ax, ay = geo["anchor"]
    x0 = x - (ax if facing == 1 else bw - ax) * sc
    return [x0, y - ay * sc, bw * sc, bh * sc]


def union(rs):
    x0, y0 = min(r[0] for r in rs), min(r[1] for r in rs)
    x1, y1 = max(r[0] + r[2] for r in rs), max(r[1] + r[3] for r in rs)
    return [math.floor(x0), math.floor(y0), math.ceil(x1) - math.floor(x0), math.ceil(y1) - math.floor(y0)]


def hits(a, b):
    return min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1])


# ── the track ──

def span(m, plan):
    t0 = float(m.get("from") or 0.0)
    t1 = float(m["to"]) if m.get("to") is not None else float(plan.get("duration") or 0.0)
    return t0, t1


def changes(m, geo):
    """The pose changes in time order: [(t, asked, drawn, mirrored)]."""
    out = []
    for it in sorted([x for x in m.get("track") or [] if x.get("t") is not None], key=lambda x: float(x["t"])):
        drawn, mir = substitute(it["pose"], geo) if it.get("pose") in POSES else ("neutral", False)
        out.append((float(it["t"]), it.get("pose"), drawn, mir))
    return out


def tone_at(t, plan, s):
    """The scene tone at second t: the scene on screen then, else the video's."""
    for sc in plan.get("inserts", []):
        if (sc.get("kind") == "scene" and sc.get("status") != "skipped" and sc.get("type") != "cover"
                and sc["start"] - 1e-6 <= t < sc["start"] + sc["dur"]):
            return scene_tone(sc, s)
    return s.get("scene_tone") or (s.get("brand_tone") or {}).get("scene_tone") or "calm"


def bounces(t, plan, s):
    """A pose change may overshoot only with a loud scene tone, a brand tone that bounces and a full mascot."""
    bt = s.get("brand_tone") or {}
    return level(s) == "full" and bool(bt.get("overshoot")) and tone_at(t, plan, s) in LOUD


def ease(p, bounce):
    p = min(1.0, max(0.0, p))
    if bounce:
        c = 1.70158
        q = p - 1
        return 1 + (c + 1) * q ** 3 + c * q ** 2
    return 1 - (1 - p) ** 3


def blinks(seed, t0, t1):
    """Blink times: every 2.6-4.6 s, the same for the same video (no randomness between renders)."""
    out, t, k = [], t0 + 1.2, 0
    while t < t1:
        out.append(t)
        h = int(hashlib.sha256(f"{seed}:{k}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        t += 2.6 + 2.0 * h
        k += 1
    return out


def speaking(m, plan, vend):
    """The half-open spans where the mouth moves: the plan's, else the whole narration while the mascot is on."""
    if m.get("speaks") is not None:
        return [(float(a), float(b)) for a, b in m["speaks"]]
    t0, t1 = span(m, plan)
    return [(t0, min(t1, vend))] if vend > t0 else []


def frames_of(m, plan, s, geo, opens, fps, speaks=None):
    """The per-frame plan the kit plays: entries {f, pose, prev, k, open, blink[, facing]}, each holding until the
    next one (an entry is written only where a value changes)."""
    t0, t1 = span(m, plan)
    f0, f1 = jround(t0 * fps), jround(t1 * fps)
    ch = changes(m, geo)
    facing = -1 if m.get("facing") == -1 else 1
    sp = speaks if speaks is not None else speaking(m, plan, len(opens) / float(fps))
    bl = [jround(t * fps) for t in blinks(plan.get("id") or "", t0, t1)]
    start, _ = substitute("neutral", geo)
    out, last = [], None
    for f in range(f0, max(f0 + 1, f1)):
        t = f / float(fps)
        cur = [c for c in ch if jround(c[0] * fps) <= f]
        if cur:
            c = cur[-1]
            fc = jround(c[0] * fps)
            prev = cur[-2][2] if len(cur) > 1 else start
            bounce = bounces(c[0], plan, s)
            k = ease((f - fc) / float(BOUNCE_FRAMES if bounce else EASE_FRAMES), bounce)
            pose, mir = c[2], c[3]
        else:
            pose, prev, k, mir = start, start, 1.0, False
        o = opens[f] if 0 <= f < len(opens) and any(a - 1e-9 <= t < b for a, b in sp) else 0.0
        blink = any(b <= f < b + BLINK_FRAMES for b in bl)
        e = {"pose": pose, "prev": prev, "k": round(k, 3), "open": round(float(o), 3), "blink": blink}
        if mir:
            e["facing"] = -facing
        if e != last:
            out.append({"f": f, **e})
            last = e
    return out


# ── follow the rough cut ──

def follow(plan, cap):
    """A re-cut: the mascot's poses placed on words move with them; a word that is gone is marked lost (validate
    names it). -> the ids (at) that moved."""
    moved = []
    for it in (plan.get("mascot") or {}).get("track") or []:
        at = str(it.get("at") or "")
        if not (at.startswith("word:") or re.fullmatch(r"s\d+", at)):
            continue
        try:
            t = round(resolve_at(at, plan, cap), 3)
        except SystemExit as x:
            it["lost"] = str(x)
            continue
        it.pop("lost", None)
        if it.get("t") is None or abs(t - float(it["t"])) > 0.001:
            moved.append(at)
            it["t"] = t
    return moved


# ── the checks ──

def keep_boxes(e, plan):
    """What the mascot keeps clear of, with their times: the plan's zones (cards, presenters, callout labels), the
    overlay/split/window scenes and the placed pop-up memes."""
    out = [k for k in plan.get("keep_clear", []) if not k.get("mascot") and not k.get("scene")]
    out += scene_keep_entries({**plan, "inserts": [{**i, "status": "ready"} if i.get("kind") == "scene"
                                                   and i.get("status") == "planned" else i
                                                   for i in plan.get("inserts", [])]})
    if not any(k.get("callout") for k in out) and any(i.get("kind") == "callout" and i.get("status") == "ready"
                                                      for i in plan.get("inserts", [])):
        try:
            from vp_callouts import callout_keep_entries
            out += callout_keep_entries(e, plan)
        except Exception:  # noqa: BLE001 - a callout that cannot be laid out is validate's own error
            pass
    for i in plan.get("inserts", []):
        if i.get("kind") == "meme" and i.get("status") != "skipped" and i.get("box"):
            out.append({"start": i["start"], "end": i["start"] + i["dur"], "box": i["box"], "what": f"meme {i['id']}"})
    return out


def issues(e, plan, s, doc, brand, bdir, fps=30):
    """visual_plan.py validate's mascot checks -> (errors, warnings)."""
    m = plan.get("mascot")
    if not m:
        return [], []
    errs, warns = [], []
    bt = s.get("brand_tone") or {}
    if level(s) == "off":
        msg = (f"mascot: the brand tone {bt.get('preset')} has no mascot (brand_tones.{bt.get('preset')}.mascot: off)")
        if s.get("tone_override"):
            warns.append(msg + " (tone_override: note it in the report)")
        else:
            errs.append(msg + " (to go past it on explicit request: reelcfg.py save ... --set tone_override=true)")
    for it in m.get("track") or []:  # the track's own faults, whatever the brand's mascot is
        if it.get("lost"):
            errs.append(f"mascot: the pose {it.get('pose')} was placed on {it.get('at')}, which the re-cut removed "
                        f"({it['lost']}): place it again (mascot.py plan ... --pose)")
        if it.get("pose") not in POSES:
            errs.append(f"mascot: unknown pose {it.get('pose')!r} (the dictionary: {', '.join(POSES)})")
    geo, why = geometry(brand, bdir)
    if not geo:
        return errs + [f"mascot: {why}"], warns
    D = float(plan.get("duration") or 0.0)
    t0, t1 = span(m, plan)
    if not (0 <= t0 < t1 <= D + 0.05):
        errs.append(f"mascot: on screen {t0}-{t1} s, the video is {D} s")
    for it in m.get("track") or []:
        if it.get("pose") in POSES and it["pose"] not in geo["poses"]:
            d, mir = substitute(it["pose"], geo)
            warns.append(f"mascot: it has no pose {it['pose']}: {d}{' mirrored' if mir else ''} is drawn at "
                         f"{it.get('t')} s")
        if it.get("t") is not None and not (t0 - 1e-6 <= float(it["t"]) < t1):
            warns.append(f"mascot: the pose {it.get('pose')} at {it['t']} s is outside its time on screen {t0}-{t1} s")
    ch = changes(m, geo)
    for a, b in zip(ch, ch[1:]):
        if b[0] - a[0] < MIN_GAP_S - 1e-6:
            errs.append(f"mascot: poses change at {a[0]} and {b[0]} s, {b[0] - a[0]:.2f} s apart: at most once per "
                        f"{MIN_GAP_S} s")
    mouth, problem = load_mouth(e, fps)
    vend = voice_end(e, plan, mouth)
    sp = speaking(m, plan, vend)
    for a, b in sp:
        if b <= a:
            errs.append(f"mascot: speaks [{a}, {b}) is empty")
        elif a < -1e-6 or b > vend + 1.0 / fps:
            errs.append(f"mascot: speaks [{a}, {b}) runs past the narration (it is {vend:.2f} s"
                        + ("" if voice_track(e) else ", no voice.wav or final.mp4") + ")")
    if sp and voice_track(e) and problem:
        warns.append(f"mascot: {problem}: run mascot.py mouth edit/{Path(e).name} (stage refuses it)")
    band = subtitle_band(plan, s, doc)
    safe = ui_safe_of(s, doc)
    x, y, sc = placement(m, geo, band, safe)
    facing = -1 if m.get("facing") == -1 else 1
    r = union([rect(x, y, sc, geo, facing)] + ([rect(x, y, sc, geo, -facing)] if any(c[3] for c in ch) else []))
    # r is rounded outward to whole pixels: a pixel of rounding is not a collision
    sides = [n for n, bad in (("left", r[0] + 1 < safe["left"]), ("top", r[1] + 1 < safe["top"]),
                              ("right", r[0] + r[2] - 1 > W - safe["right"]),
                              ("bottom", r[1] + r[3] - 1 > H - safe["bottom"])) if bad]
    if sides:
        errs.append(f"mascot {r}: in the UI zone ({'/'.join(sides)}; top {safe['top']}, bottom {safe['bottom']}, right "
                    f"{safe['right']}, left {safe['left']} px): move or scale it (mascot.py plan --at x,y --scale k)")
    if band and r[1] + r[3] - 1 > band[0] - BAND_GAP and r[1] < band[1]:
        errs.append(f"mascot {r}: on the subtitle band {band} (its lowest point must stay {BAND_GAP} px above y "
                    f"{band[0]}): mascot.py plan --auto-place, or a smaller --scale")
    for k in keep_boxes(e, plan):
        if k["start"] < t1 and k["end"] > t0 and hits(r, k["box"]):
            errs.append(f"mascot {r}: over {k.get('what')} {k['box']} at {k['start']:.1f}-{k['end']:.1f} s")
    scenes = [i for i in plan.get("inserts", []) if i.get("kind") == "scene" and i.get("status") != "skipped"
              and i.get("type") != "cover"]
    for sc_ in scenes:
        if sc_.get("mode") in ("full", "panel") and sc_["start"] < t1 and sc_["start"] + sc_["dur"] > t0:
            warns.append(f"mascot: drawn over the {sc_['mode']} scene {sc_['id']}: textcheck.py measures its text "
                         f"against the mascot (text on the mascot is an error)")
        for edge, name in ((sc_["start"], "entrance"), (sc_["start"] + sc_["dur"], "exit")):
            for c in ch:
                if abs(c[0] - edge) <= EDGE_S + 1e-6:
                    warns.append(f"mascot: the gesture {c[1]} at {c[0]} s is {abs(c[0] - edge):.2f} s from the "
                                 f"{name} of scene {sc_['id']} ({edge:.2f} s): two moves at once; move it "
                                 f"{EDGE_S} s or more away")
    return errs, warns


# ── stage ──

def atlas_rig(brand, bdir, staged_mascot, rem):
    """rig.json of the brand's atlas mascot, its content: the kit reads no files while it renders (AtlasMascot.tsx), so
    stage hands it the rig itself. The rig and the atlas image go as one pair: the copy brand.py stage put in public/
    next to the image, and the brand folder's rig must still be the same (an atlas cut again without brand.py stage
    would put the new frames over the old image). -> (rig, None) or (None, why)"""
    m = (brand or {}).get("mascot") or {}
    src = load_json(brand_file(m.get("rig"), bdir), None) if bdir else None
    if rem is None:  # no Remotion project known (a check outside stage): the brand's rig as it is
        return src, None
    staged = load_json(Path(rem) / "public" / str(staged_mascot.get("rig") or ""), None)
    if not isinstance(staged, dict):
        return None, (f"the staged atlas rig public/{staged_mascot.get('rig')} is missing: run brand.py stage "
                      f"{brand.get('slug')} --remotion {rem}")
    if src != staged:
        return None, (f"the brand's atlas changed since brand.py stage (rig.json differs from the copy in public/): "
                      f"run brand.py stage {brand.get('slug')} --remotion {rem}")
    return staged, None


def props_of(e, plan, s, doc, brand, bdir, staged, fps=30, rem=None):
    """props.mascot for the kit, or (None, why) when it cannot be staged."""
    m = plan.get("mascot")
    geo, why = geometry(brand, bdir)
    if not geo:
        return None, why
    sm = (staged or {}).get("mascot")
    if not isinstance(sm, dict) or sm.get("kind") != geo["kind"]:
        return None, (f"src/brands/{plan.get('brand')}.json has no {geo['kind']} mascot: run brand.py stage "
                      f"{plan.get('brand')} --remotion <Remotion project>")
    rig = None
    if geo["kind"] == "atlas":
        rig, why = atlas_rig(brand, bdir, sm, rem)
        if rig is None:
            return None, why
    mouth, problem = load_mouth(e, fps)
    vend = voice_end(e, plan, mouth)
    sp = speaking(m, plan, vend)
    if sp and (problem or not mouth):
        return None, f"{problem or 'no mouth.json'}: run mascot.py mouth edit/{Path(e).name} first"
    opens = (mouth or {}).get("open") or []
    band = subtitle_band(plan, s, doc)
    x, y, sc = placement(m, geo, band, ui_safe_of(s, doc))
    t0, t1 = span(m, plan)
    facing = -1 if m.get("facing") == -1 else 1
    out = {"kind": sm["kind"], "module": sm.get("module") or plan.get("brand"),
           **{k: sm[k] for k in ("rig", "atlas") if sm.get(k)},
           **({"rig": rig} if rig is not None else {}),
           "x": x, "y": y, "scale": sc, "facing": facing, "from": t0, "to": t1,
           "frames": frames_of(m, plan, s, geo, opens, fps, sp)}
    ch = changes(m, geo)
    box = union([rect(x, y, sc, geo, facing)] + ([rect(x, y, sc, geo, -facing)] if any(c[3] for c in ch) else []))
    return out, box


def stage_into(e, props, staged, rem=None):
    """visual_plan.py stage: props.mascot, resolved against the subtitle band this stage recorded; its box goes into
    the plan's keep_clear, so memes, scenes and faces.py audit keep clear of it. Refuses (exit) what it cannot stage."""
    import sys
    from vp_core import current_settings, editing_plan, load_plan
    plan = load_plan(e)
    s, _prov, doc, bdir, brand = current_settings(e, plan)
    mp, box = props_of(e, plan, {**s, "subtitles": props.get("subtitles")}, doc, brand, bdir, staged,
                       (doc.get("scenes") or {}).get("fps", 30), rem)
    if not mp:
        sys.exit(f"mascot: {box}; the template props are not written")
    props["mascot"] = mp
    with editing_plan(e) as p2:
        keep = [k for k in p2.get("keep_clear", []) if not k.get("mascot")]
        p2["keep_clear"] = keep + [{"start": mp["from"], "end": mp["to"], "box": box, "what": "mascot", "mascot": True}]
    print(f"mascot: {mp['kind']} \"{mp['module']}\" at {mp['x']},{mp['y']} x{mp['scale']}, {mp['from']}-{mp['to']} s, "
          f"{len(mp['frames'])} key frame(s); box {box} kept clear")
