"""The visual plan's picture defects (defects.py -> faces_defects.json): which inserts cover them, and accept. Part of visual_plan.py, with no command line
of its own: the other scripts take these names from visual_plan."""
import sys
from pathlib import Path

from reels_common import (edit_dir, load_json)
from vp_core import (editing_plan, ensure_plan, fmt_t)
from vp_scenes import (layout_frames, scene_timeline, scene_tone)


# Picture defects (defects.py -> faces_defects.json): a stretch where the sound is good and the picture is not. An insert
# that covers one says so (`add … --covers d03`); only a full scene, a replacing B-roll (a code scene is one) or a
# cutaway meme takes the face off screen: overlay, split, panel and window leave it there. The insert has to be on
# screen from COVER_PAD before the defect to COVER_PAD after it, its entrance finished by then and its exit not yet
# begun (a fade or a slide shows the defect through it), and ready (stage takes only ready inserts); a defect left on
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
    a defect (stage takes only ready ones); a planned one marked --covers is checked now and counts once it is ready."""
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
                         f"once it is ready (until then the stage leaves the defect on screen)")
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


# Strangers in a picture source (references/no-speaker.md): people who did not agree to be filmed (a pool, a street).
# For every source shown as the main picture (a voice-over shot, purpose "picture") the person says once, in cut.json,
# whether strangers are in it: sources.<name>.strangers = [] (none), [[from, to], ...] (source seconds where they are)
# or "ok" (they may be shown). A marked stretch is on screen wherever a shot shows those source seconds; an opaque
# insert (a full scene, a replacing B-roll, a cutaway meme: hides_face) must hide it from COVER_PAD before to COVER_PAD
# after, entering and leaving by then. Not answered, or not hidden: an error, the video is not released. A face
# detector only suggests candidates for the marks; the marks are the person's.
def stranger_issues(e, plan, s, doc, cap):
    """-> [error] for the strangers of the picture sources of edit/<id>."""
    from pic_track import purposes
    from reels_common import voice_mode
    cut = load_json(Path(e) / "cut.json", {}) or {}
    srcs = cut.get("sources") or {}
    shots = {g["i"]: g for g in (cap or {}).get("shots") or []}
    if not shots:
        return []
    spans = purposes(cap, voice_mode(s))
    shown = [g for g in sorted(shots.values(), key=lambda x: x["out_start"])
             if g.get("kind") in ("video", "photo") and any(abs(a - g["out_start"]) < 1e-6 and p == "picture"
                                                            for a, _, p in spans)]
    errs, D = [], float(plan.get("duration") or (cap or {}).get("duration") or 1e9)
    live = [i for i in plan.get("inserts", []) if i.get("status") != "skipped" and hides_face(i)]
    asked = set()
    for g in shown:
        name = g.get("source")
        sv = srcs.get(name)
        marks = sv.get("strangers") if isinstance(sv, dict) else None
        if marks is None:
            if name not in asked:
                asked.add(name)
                errs.append(f"strangers: say whether people who may not be shown are in the picture source {name!r}: "
                            f"cut.json sources.{name}.strangers = [] (none), [[from, to], ...] (its seconds where they "
                            f"are: they get hidden under a full scene) or \"ok\" (they may be shown)")
            continue
        if marks == "ok" or not marks:
            continue
        if not isinstance(marks, list) or not all(isinstance(m, list) and len(m) == 2 for m in marks):
            errs.append(f"strangers: cut.json sources.{name}.strangers is [] , [[from, to], ...] or \"ok\"")
            continue
        for a, b in marks:
            if g["kind"] == "photo":
                w0, w1 = g["out_start"], g["out_start"] + g["out_dur"]
            else:
                x, y = max(float(a), g["src_start"]), min(float(b), g["src_end"])
                if y <= x:
                    continue
                sp = g.get("speed") or 1.0
                w0, w1 = g["out_start"] + (x - g["src_start"]) / sp, g["out_start"] + (y - g["src_start"]) / sp
            p0, p1 = max(0.0, w0 - COVER_PAD), min(D, w1 + COVER_PAD)
            by = [i for i in live if hidden_span(i, s, doc, cap)[0] <= p0 + 1e-6 and hidden_span(i, s, doc, cap)[1] >= p1 - 1e-6]
            if any(i.get("status") == "ready" for i in by):
                continue
            errs.append(f"strangers: {name} {float(a):.2f}-{float(b):.2f} s is on screen at {w0:.2f}-{w1:.2f} s: hide it "
                        f"under a full scene (or a replacing B-roll, a cutaway) from {p0:.2f} to {p1:.2f} s, entering "
                        f"and leaving by a cut" + (f" ({by[0]['id']} covers it once it is ready)" if by else "")
                        + "; or cut that stretch out of the shot")
    return errs
