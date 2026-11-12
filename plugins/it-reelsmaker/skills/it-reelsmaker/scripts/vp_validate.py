"""The visual plan's validate command and the video profile checks it runs. Part of visual_plan.py, with no command line
of its own: the other scripts take these names from visual_plan."""
import re

from reels_common import (CORNER_BOX, FRAMED_LABEL_UP, SUB_BLOCK_H, budget, edit_dir, effective, forbidden_hits,
                          framed_at, framed_issues, framed_source, load_json, locked, online, probe, save_json)
from vp_core import (CTA_RE, GEN_FIELDS, KINDS, SOURCES, STATUSES, TRANSITIONS, WINDOW_DEFAULT, build_plan,
                     current_settings, cut_id, editing_plan, end_now, end_tail, ensure_plan, fmt_t, load_plan,
                     norm_words, plan_duration, plan_path, resolve_at, snapshot)
from vp_scenes import (COVER_MODES, check_scenes, default_box, faces_seen, scene_text, scenes_only_cover, tone_issues,
                       window_issues)
from vp_defects import (defect_issues)
from vp_callouts import (_point, callout_at, callout_context, callout_times, check_callouts)


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
                f"video: a slow start (cut the lead-in, or open with a hook scene or the stage --hook headline; "
                f"validate --hook when the stage will have one)")
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
                "no CTA: no cta scene, no end card (stage --card) and none spoken in the last 40 % of the video")
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
                           f"say it, show it in the hook or a scene, or add the corner logo (stage --corner; "
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
            # with stage, after this check (PR 32 review: a first stage of an ad let a label out of the zone)
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
            # the subtitles: stage lifts them into the zone itself (a band an earlier stage recorded lower is not
            # blocked: Codex review); only a block taller than the zone can't fit
            h = SUB_BLOCK_H.get(str(s.get("subtitles") or "accent"), max(SUB_BLOCK_H.values()))
            if not only and y1 - y0 < h:
                bad.append(f"the subtitles ({h} px) do not fit between y {y0} and {y1}")
            fr = None if only else framed_at(e)
            if corner and not fr:  # stage puts it at the zone's top for this profile (props.cornerTop)
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
            # here, so the item never succeeds automatically (Codex review: "ok" read as cleared for everything)
            bad = [m["id"] for m in memes if m.get("rights") not in ("own", "licensed", "cc")]
            if bad:
                put(item, False, f"memes {', '.join(bad)} without known rights (own, licensed or cc) in a paid ad: "
                                 f"replace them or mark them skipped", err=True)
            else:
                st[item] = "check"
        else:
            st[item] = "check"
    return errs, warns, st


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
    from mascot_plan import follow as mascot_follow  # the mascot's poses on words (a lost word: validate names it)
    moved += [f"mascot {at}" for at in mascot_follow(plan, cap)]
    save_json(plan_path(e), plan)
    if not quiet:
        print(f"the rough cut changed ({old:.2f} -> {plan['duration']:.2f} s): spans rebuilt"
              + (f"; moved with their words: {', '.join(moved)}" if moved else "")
              + (f"; placed by seconds, check them: {', '.join(by_seconds)}" if by_seconds else ""))


def cmd_validate(a, quiet=False):
    e = edit_dir(a.edit)
    ensure_plan(e)  # md and stage validate first, so all three work on a plain edit without `init`
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
                         f"({'with the camera of camera.json' if how == 'camera.json' else 'with the camera' if kc else 'without a camera: give keep-clear --cam'}): "
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
                    # (memes.py place --cam writes i["cam"]; None means no camera). No cam field (an old plan): the
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
                 else (plan.get("finish") or {}).get("hook"))
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
        # the status is written under a second lock: if another run changed the scene meanwhile, its status is left alone
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
    from mascot_plan import issues as mascot_issues  # the brand mascot (references/mascot.md)
    me, mw = mascot_issues(e, plan, s, doc, brand, bdir, (doc.get("scenes") or {}).get("fps", 30))
    errs += me
    warns += mw
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
