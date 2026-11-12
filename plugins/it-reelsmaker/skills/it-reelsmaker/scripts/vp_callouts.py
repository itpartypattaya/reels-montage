"""The visual plan's callouts: the label's geometry on screen through the camera, its path over the
picture, add and check, and the zones a stage keeps clear for them. Part of visual_plan.py, with no command line
of its own: the other scripts take these names from visual_plan."""
import hashlib, json, math, re, shutil, sys
from pathlib import Path

from reels_common import (CORNER_BOX, LINE_FACE_MARGIN, SUB_BAND, edit_dir, framed_at, framed_source, load_config,
                          load_json, ui_safe, ui_zone, warn)
from vp_core import (NUM_RE, STATUSES, _ru, editing_plan, fmt_t, jround, overlap, read_need, resolve_at, srgb_lum)
from vp_camera import (camera_at, plan_camera)
from vp_scenes import (COVER_MODES, SCENE_SOURCES, default_box, hidden_windows, hides_subtitles, scene_tone)


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

    only = plan.get("format") in ("scenes-only", "scenes-voice")  # no rough cut on screen (vp_core.NO_FOOTAGE)
    fr = None if only else framed_at(e)
    ctx = callout_context(e, plan, fdata)
    segs, shots, drift, end = ctx[:4]
    fps = (doc.get("scenes") or {}).get("fps", 30)
    R = (doc.get("scenes") or {}).get("reading") or {}
    tones = {k: v for k, v in (doc.get("scene_tones") or {}).items() if not k.startswith("_")}
    lb = ml.layout(s, doc).get("subtitles_band", list(SUB_BAND))
    pb = plan.get("subtitles_band") or lb  # the band stage measured for the render, and the layout's
    band = [min(lb[0], pb[0]), max(lb[1], pb[1])] if (s.get("subtitles") or "accent") != "none" else None
    zx0, zy0, zx1, zy1 = ui_zone()  # the label: the safe zone, 40 px off the left edge by default
    ui = ui_safe()
    step = (fdata or {}).get("step", 0.25)
    keep = [k for k in plan.get("keep_clear", []) if not k.get("callout")]
    # where the rough cut is not on screen as the anchor has it: a scene that moves or covers it, a replacing B-roll,
    # a cutaway meme
    cover = [x for x in scenes if x.get("mode") in COVER_MODES and x.get("type") != "cover"]
    # B-roll and memes only when ready: stage renders nothing else, the main footage stays (Fable review)
    cover += [x for x in brolls + memes if x.get("mode") in ("replace", "cutaway") and x.get("status") == "ready"]
    # where the subtitles are hidden their band is free: hide-subs windows and scenes that hide them
    hidden = [tuple(h) for h in hidden_windows(plan)] + [(x["start"], x["start"] + x["dur"]) for x in scenes
                                                         if x.get("type") != "cover" and hides_subtitles(x, s)]
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
                E(c, "a dimension measures between two still points: no points, track or person")
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
            elif any(y_ < ui["top"] or y_ > fc.H - ui["bottom"] or x_ > fc.W - ui["right"] or x_ < ui["left"]
                     for x_, y_ in ends):  # the left side too (Codex review of 1.22)
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
                elif any(_seg_hits(p, q, f, LINE_FACE_MARGIN) for p, q in segs_):
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
                # the dots and rings too (Codex bot review, PR 33: a big ring around the other label got through)
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
        warn(f"{c['id']}: the anchor ({x}, {y}) is off the 1080x1920 frame: validate will refuse it")
    how = (f"following the {a.person} face's shoulder" if a.person else f"along {len(path)} points set by hand" if path
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
    """--keys T:X,Y ... (T: seconds from the callout's start; T:- hides the dot from there, until the next point) ->
    path rows [t, x, y, v]: the dot slides straight between points, fades out toward a hidden point and back in."""
    rows = []
    for k in keys:
        t_, _, xy = str(k).partition(":")
        try:
            t = round(float(t_), 3)
            if xy.strip() == "-":
                if not rows:
                    sys.exit(f"point {k} of --keys: the first one needs a position")
                rows.append([t, rows[-1][1], rows[-1][2], 0])
                continue
            x_, y_ = (round(float(v)) for v in xy.split(","))
        except ValueError:
            sys.exit(f"point {k} of --keys: T:X,Y (seconds from the callout's start, a point of the rough cut) or T:- (hidden)")
        rows.append([t, x_, y_, 1])
    why = path_issue(rows, dur)
    if why:
        sys.exit(f"{why} (the points of --keys)")
    return rows


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
CALLOUT_GAP_S = 0.6      # a second callout enters no sooner than this after the first (one element at a time)
CALLOUT_AT_ONCE = 2
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
    zx0, _, zx1, _ = ui_zone()
    right, left = zx1 - (x + off + w), (x - off - w) - zx0
    return "right" if right >= 0 or right >= left else "left"


def _seg_hits(p, q, box, m=0):
    """Does segment p-q go through box (x, y, w, h) grown by m? Sampled every 4 px."""
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
    its path's rows (between rows it moves straight, so its extremes are there; Codex review: a point between two samples
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
    """Whether the callout's anchor is more than one still point: a path (points, a track) or a second point."""
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
    1080x1920 as the kit draws it. A moving anchor (points, a track): the patch follows the path, from its first visible
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
    """The measurement in words, for add and validate; moving: the dot follows a path (points, a track)."""
    if v is None:
        return f"the picture under the dot is not measured ({why}): check it on the stills"
    if v <= CALLOUT_STILL:
        return f"the picture under the dot holds still ({v:g} of 255)" + (" along its path" if moving else "")
    if v <= CALLOUT_MOVES:
        return f"the picture under the dot changes a little ({v:g} of 255): someone walks by or the light changes? check the stills"
    if moving:
        return (f"the picture under the dot changes along its path ({v:g} of 255, still is <= {CALLOUT_STILL}): the "
                f"path slips off the object (points too far apart, a track that lost it, the object turning): fix the "
                f"points, track it again, or shorten the callout")
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
    """The anchor's path: points or a track from the plan, or a person's from faces.json (cached in ctx)."""
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
