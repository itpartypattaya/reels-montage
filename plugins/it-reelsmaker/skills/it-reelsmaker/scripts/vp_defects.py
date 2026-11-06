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
