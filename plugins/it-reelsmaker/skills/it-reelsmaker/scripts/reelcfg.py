# -*- coding: utf-8 -*-
"""Edit settings of a video: brand, style, inserts (B-roll, code scenes, memes), intensity, and what will actually
turn on.

Layers: the one list is references/brands.md ("Layers"); `show` prints where each value comes from. The brand tone also sets the ceilings (memes,
transitions, full scenes); to go beyond them on explicit request: reelcfg.py save edit/<id> --set tone_override=true
(violations become warnings).

    python scripts/reelcfg.py show edit/4821 [--set use_memes=true intensity=active] [--json]
    python scripts/reelcfg.py save edit/4821 --set brand=acme style=v2 use_broll=false use_memes=false
    python scripts/reelcfg.py save edit/4821 --set profile=educational content_format=list
    python scripts/reelcfg.py save edit/4821 --set format=framed label="CANDIDATE INTERVIEW" [window=[25,340,1030,1240]]
    python scripts/reelcfg.py defaults [--set brand=acme use_memes=false] [--unset use_memes]   # the project's defaults
    python scripts/reelcfg.py save edit/4821 --set workflow=quick     # quick / standard (default) / full (SKILL.md, section 6)
    python scripts/reelcfg.py preset save weekly-tips --from edit/4821    # a series preset from a finished video
    python scripts/reelcfg.py preset use weekly-tips edit/4822            # the next video of the series
    python scripts/reelcfg.py preset list

`show` prints the resulting settings, where each key comes from, and the fallback: what turns off by itself (for
example online sources when the online-sources add-on `it-reelsmaker-online` is not installed) and why. This is not an
error: editing continues with what is available.
`save` adds keys to edit/<id>/reel.json (only the ones given; defaults are not copied there); it creates the folder
edit/<id> if it doesn't exist yet. reel.json is the only source of the video's settings: visual_plan.py takes them
from here.
profile=<id> (educational, entertaining, expert-clip, promo, ad) and content_format=<id> (insight, list, case, story,
skit, testimonial, intro, offer, review, event, interview, scenes-only): the video's goal and its form; the profile's
defaults sit after the project's and under the brand tone's ceiling, and visual_plan.py validate checks its checklist
(references/profiles.md). content_format alone brings its default profile. A profile is opt-in: the skill saves one
only when the person asks for it, or profile=ad for a paid ad.
format=framed: a horizontal source in a rounded window on the style's field, with an optional caps label above it
(references/techniques.md); window (x, y, w, h on the 1080x1920 screen) and label are its options. The kit draws it
from the props that visual_plan.py export writes; faces.py and visual_plan.py read the same window.
`defaults` shows or edits <project>/reel-defaults.json: your defaults for every video of the project (default brand,
inserts, library folders, ...), in the same format as the plugin's assets/reel-defaults.json, only the keys you change.
--set/--unset touch the "settings" keys; other sections (intensity and brand tone labels in your language, ...) are
edited in the file by hand. The file stays in the project: plugin updates never touch it.
workflow=quick|standard|full: how many questions and stops the agent makes (SKILL.md, section 6); standard by default.
`preset` keeps a series' answers in <project>/presets/<name>.json: the video's settings (brand, style, subtitles,
inserts, profile, format and label, workflow, ...) and its finish (corner logo, end card or sting with the card's
lines, from the last export); `use` writes them into the next video's reel.json, and visual_plan.py export draws that
finish until the video's own export changes it. Measured values (subtitles_shade, window), a one-off tone_override
and the hook stay per video.
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (PROJECT_DEFAULTS, RENAMED, SETTING_KEYS_BOOL, to_new_names, edit_dir, editing_json,
                          effective, framed_issues, renamed,
                          framed_of, is_project, load_config, load_defaults, load_json, online, parse_sets, profiles_of,
                          project_root, save_json, tone_summary, utf8_stdio, warn)
from reels_common import find_brand

KNOWN = set(SETTING_KEYS_BOOL) | {"brand", "style", "subtitles", "intensity", "broll_priority", "meme_priority",
                                  "footage_dirs", "memes_dirs", "generation_engines", "library_dirs", "meme_size",
                                  "scene_tone", "tone_override", "subtitles_lang", "subtitles_shade",
                                  "format", "window", "label", "subtitles_at",  # format: "framed" (window, label, subtitles_at) or "full"
                                  "profile", "content_format",  # the video's goal and its form (references/profiles.md)
                                  "workflow"}  # stops and questions (SKILL.md, section 6)
WORKFLOWS = ("quick", "standard", "full")
# what a series preset does not carry: values measured on this video's frames, a one-off permission to go past the
# brand tone (review 2026-10-18: it became the series' rule), the plan's own copies, and the finish (kept apart)
PER_VIDEO = {"subtitles_shade": "measured on this video", "window": "measured on this video",
             "tone_override": "a one-off permission for this video", "brand_snapshot": "a copy kept by the plan",
             "notes": "this video's notes", "finish": "kept apart as the preset's finish"}
PRESETS = "presets"  # <project>/presets/<name>.json


def addon_keys(name):
    """Setting keys added by the online-sources add-on (its module's <name> list); empty when it is not installed."""
    return list(getattr(online(), name, None) or ())


def profile_line(s, prov):
    """The video's profile and content format, with their length, CTA and checklist (references/profiles.md)."""
    pr = s.get("profile_rules")
    if not pr:
        return ("profile: — (none: no profile checklist; set one: reelcfg.py save edit/<id> --set profile=<id> or "
                "content_format=<id>; references/profiles.md)")
    src = prov.get("profile") or ("content_format " + str(s.get("content_format")))
    lo, hi = pr.get("length") or (None, None)
    parts = [f"profile: {pr['id']} ({pr['label']}) ← {src}",
             f"format: {pr['format'] or '—'}", f"length {lo}–{hi} s" if lo else "",
             f"CTA ≤ {pr['cta_max']}" + (", required" if pr.get("cta_required") else ""),
             f"brand by {pr['brand_by_s']} s" if pr.get("brand_by_s") else "",
             f"safe zone {pr['safe_zone']}" if pr.get("safe_zone") else "",
             "checklist " + ", ".join(pr.get("checklist") or {})]
    return "; ".join(x for x in parts if x) + "".join("\n  ⚠ " + n for n in pr.get("notes") or [])


def cmd_show(a):
    e = edit_dir(a.edit) if a.edit else None
    over = parse_sets(a.set)
    s, prov, doc, bdir, brand = load_config(e, over)
    eff, why = effective(s)
    if a.json:
        print(json.dumps({"settings": s, "provenance": prov, "effective": eff, "fallback": why,
                          "brand_dir": str(bdir) if bdir else None}, ensure_ascii=False, indent=1))
        return
    print(f"brand: {s['brand']} ({brand.get('name') if brand else 'NOT FOUND'})"
          f"   style: {s.get('style') or (brand or {}).get('styles', {}).get('default') or '—'}"
          f"   subtitles: {s.get('subtitles') or (brand or {}).get('subtitles_default') or '—'}")
    fr = framed_of(s)
    print("format: " + (f"framed, window {fr['window']}" + (f", label “{fr['label']}”" if fr["label"] else ", no label")
                        + (", subtitles below the window" if fr["subtitles_at"] == "below" else "")
                        + " (the kit draws the window)" if fr else "full frame (vertical)")
          + "".join("\n  ⚠ " + m for m in framed_issues(s)))
    print(profile_line(s, prov))
    print(f"workflow: {s.get('workflow') or 'standard'} ← {prov.get('workflow', '—')} (quick / standard / full: the "
          f"questions and stops before the master, SKILL.md section 6)"
          + (f"; series finish: {finish_line(s['finish'])}" if s.get("finish") else ""))
    bt = s.get("brand_tone") or {}
    print(f"brand tone: {tone_summary(bt)}" + ("  [tone_override: the tone's ceilings are only warnings]" if s.get("tone_override") else ""))
    st = s.get("scene_tone")
    if st and st not in (bt.get("scene_tones") or []):
        print(f"  ⚠ the video's scene tone {st} is not one of the brand's tones ({', '.join(bt.get('scene_tones') or [])}): validate won't pass it without tone_override")
    else:
        print(f"video scene tone: {st or '—'} ← {prov.get('scene_tone', '—')}")
    lvl = (doc.get("intensity") or {}).get(s["intensity"], {})
    print(f"intensity: {s['intensity']} ({lvl.get('label', '')}): up to {lvl.get('broll_per_30s')} B-roll per 30 s, "
          f"up to {lvl.get('memes_max')} memes, inserts ≤ {int(lvl.get('coverage_max', 0) * 100)} % of the length, "
          f"≥ {lvl.get('min_gap_s')} s between inserts  ← {prov.get('intensity', '—')}")
    print("settings:")
    for k in SETTING_KEYS_BOOL + addon_keys("SETTING_KEYS_BOOL"):
        print(f"  {k:<22} {str(s.get(k)):<6} ← {prov.get(k, '—')}")
    print("what will actually turn on:")
    rows = [("B-roll", "broll"), ("  from project footage", "project_footage"), ("  from the local library", "local_footage"),
            ("  online footage (add-on)", "online_footage"), ("  code scenes (Remotion)", "generated_code"),
            ("  add-on footage: prompts", "generated_prompts"), ("  add-on footage: run", "generate_now"), ("memes", "memes"), ("  local folder", "local_memes"),
            ("  online (add-on)", "online_memes"), ("designed scenes (kit)", "scenes")]
    for label, k in rows:
        mark = "yes" if eff.get(k) else "no "
        print(f"  {label:<28} {mark} {('— ' + why[k]) if k in why and not eff.get(k) else ''}")
    if eff.get("online_footage_providers"):
        print("  online footage sources: " + ", ".join(eff["online_footage_providers"]))
    print(f"B-roll priority: {' → '.join(s.get('broll_priority', []))}; memes: {' → '.join(s.get('meme_priority', []))} → none")


def bad_workflow(over):
    if over.get("workflow") is not None and over["workflow"] not in WORKFLOWS:
        sys.exit(f"not saved: unknown workflow {over['workflow']!r} (known: {', '.join(WORKFLOWS)})")


def finish_line(f):
    f = f if isinstance(f, dict) else {}
    end = f.get("end") if isinstance(f.get("end"), dict) else {}
    kind = {"card": "end card “" + " / ".join(end.get("lines") or []) + "”", "sting": "logo sting"}.get(end.get("kind"),
                                                                                                     "no end card")
    return kind + (", corner logo" if f.get("corner") else "")


def preset_path(name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", name or ""):
        sys.exit(f"preset name {name!r}: lowercase letters, digits, dots, dashes and underscores")
    project = project_root()
    if not is_project(project):
        sys.exit(f"no editing project here ({project}: no edit/, brands/ or it-reelsmaker.json); run it from the project "
                 f"folder or set REELS_PROJECT")
    return project / PRESETS / f"{name}.json"


def finish_from(e, own):
    """The video's ending for a preset: its last export; a plan exported before 1.13 gives the corner logo and a sting
    back from its markers (a card's lines were not stored); else the finish its reel.json got from a preset.
    -> (finish, note or None)."""
    plan = load_json(e / "visual_plan.json", {}) or {}
    if plan.get("export"):
        exp = plan["export"]
        return {"corner": bool(exp.get("corner")), "end": exp.get("end")}, None
    kind = (plan.get("end_card") or {}).get("kind")
    if plan.get("corner") or kind:
        note = ("its end card's lines were not stored (exported before 1.13): the series gets no card; give it with "
                "--card at the next video's export") if kind == "card" else None
        return {"corner": bool(plan.get("corner")), "end": {"kind": "sting"} if kind == "sting" else None}, note
    fin = own.get("finish") if isinstance(own.get("finish"), dict) else {}
    return {"corner": bool(fin.get("corner")), "end": fin.get("end")}, (None if fin else "that video has no export yet: "
                                                                        "no ending in the preset")


def cmd_preset(a):
    """A series preset: the answers of one video kept for the next ones (<project>/presets/<name>.json)."""
    if a.action == "list":
        d = project_root() / PRESETS
        files = sorted(d.glob("*.json")) if d.is_dir() else []
        if not files:
            print(f"no presets yet ({d}); make one: reelcfg.py preset save <name> --from edit/<id>")
        for f in files:
            doc = load_json(f, {}) or {}
            st = doc.get("settings") or {}
            print(f"  {f.stem:<24} brand {st.get('brand') or '—'}, style {st.get('style') or '—'}, subtitles "
                  f"{st.get('subtitles') or '—'}, workflow {st.get('workflow') or 'standard'}; "
                  f"{finish_line(doc.get('finish'))}")
        return
    f = preset_path(a.name)
    if a.action == "save":
        if not a.source:
            sys.exit("preset save needs --from edit/<id>: the video whose answers the series keeps")
        e = edit_dir(a.source)
        own = renamed(load_json(e / "reel.json", {}) or {})
        settings = {k: v for k, v in own.items() if k not in PER_VIDEO}
        if not settings:
            sys.exit(f"{e / 'reel.json'}: no settings to keep (step 0 saves them with reelcfg.py save)")
        finish, note = finish_from(e, own)  # the hook is the video's own line, never the series'
        save_json(f, {"settings": settings, "finish": finish, "from": e.name})
        print(f"{f}: " + ", ".join(f"{k}={v}" for k, v in settings.items()) + f"; {finish_line(finish)}")
        left = [f"{k} ({PER_VIDEO[k]})" for k in own if k in PER_VIDEO and k != "finish"]
        if left:
            print("  not carried: " + ", ".join(left))
        if note:
            print("  " + note)
        return
    doc = load_json(f, None)
    if doc is None:
        sys.exit(f"no preset {a.name} ({f}); reelcfg.py preset list")
    if not a.edit:
        sys.exit("preset use needs the video: reelcfg.py preset use <name> edit/<id>")
    e = edit_dir(a.edit, create=True)
    settings = {k: v for k, v in renamed(doc.get("settings") or {}).items() if k not in PER_VIDEO}  # edited by hand
    over = {**settings, **({"finish": doc["finish"]} if isinstance(doc.get("finish"), dict) else {})}
    with editing_json(e / "reel.json", {}) as reel:
        was = renamed(reel)
        changed = [f"{k} {was[k]} → {v}" for k, v in settings.items() if k in was and was[k] != v]
        reel.update(over)
        to_new_names(reel)
    print(f"{e / 'reel.json'}: preset {a.name}: " + ", ".join(f"{k}={v}" for k, v in settings.items())
          + f"; {finish_line(doc.get('finish'))}")
    if changed:
        print("  changed this video's own choices: " + ", ".join(changed))
    slug = settings.get("brand")
    if slug and find_brand(slug, project_root())[1] is None:
        warn(f"the preset's brand {slug} is not in this project (brand.py list)")
    if (load_json(e / "visual_plan.json", {}) or {}).get("export"):
        print("  this video was exported already: its own ending stays; --card / --sting / --corner change it")
    from visual_plan import refresh_plan
    if refresh_plan(e):
        print("the settings snapshot in visual_plan.json is updated")


def cmd_save(a):
    over = parse_sets(a.set)
    if "finish" in over:
        sys.exit("not saved: finish is the series preset's ending (reelcfg.py preset use); a video's own ending is set "
                 "with visual_plan.py export --card / --sting / --corner")
    known = KNOWN | set(addon_keys("SETTING_KEYS_BOOL")) | set(addon_keys("SETTING_KEYS"))
    for k in over:
        if k not in known:
            warn(f"unknown key {k}, saving it as is")
    pr, fm = profiles_of(load_defaults() or {})
    for k, known_ids in (("profile", pr), ("content_format", fm)):
        if over.get(k) is not None and over[k] not in known_ids:
            sys.exit(f"not saved: unknown {k} {over[k]!r} (known: {', '.join(known_ids)}; references/profiles.md)")
    bad_workflow(over)
    e = edit_dir(a.edit, create=True)  # step 0 of a new video: the edit/<id> folder doesn't exist yet
    if {"format", "window", "label", "subtitles_at"} & set(over):  # the framed format's keys are checked together, before saving
        bad = framed_issues({**(load_json(e / "reel.json", {}) or {}), **over})
        if bad:
            sys.exit("not saved: " + "; ".join(bad))
        new = {**(load_json(e / "reel.json", {}) or {}), **over}
        if new.get("format") != "framed" and (new.get("window") is not None or new.get("label") or new.get("subtitles_at")):
            warn("window, label and subtitles_at are options of format framed: without format=framed the kit ignores them")
    with editing_json(e / "reel.json", {}) as reel:
        reel.update(over)
        to_new_names(reel)
    print(f"{e / 'reel.json'}: " + ", ".join(f"{k}={v}" for k, v in over.items()))
    if "style" in over:  # the brand's allowed styles are its rule (references/brands.md): saved, but said aloud
        _, _, _, _, brand = load_config(e)
        allowed = ((brand or {}).get("styles") or {}).get("allowed") or []
        if allowed and str(over["style"]) not in allowed:
            warn(f"style {over['style']} is not in the brand's allowed styles ({', '.join(allowed)}; brand.json -> "
                 f"styles.allowed): a brand rule. Saved as asked; confirm it with the brand owner or pick an allowed one, "
                 f"and note the choice in project.md")
    from visual_plan import refresh_plan
    if refresh_plan(e):
        print("the settings snapshot in visual_plan.json is updated")


def cmd_defaults(a):
    project = project_root()
    f = project / PROJECT_DEFAULTS
    if not (a.set or a.unset):
        doc = load_json(f, None)
        if doc is None:
            print(f"{f}: no project defaults yet (the plugin's defaults apply); create: reelcfg.py defaults --set key=value")
        else:
            print(f"{f}:")
            print(json.dumps(doc, ensure_ascii=False, indent=1))
        return
    if not is_project(project):
        sys.exit(f"no editing project here ({project}: no edit/, brands/ or it-reelsmaker.json); run it from the project "
                 f"folder or set REELS_PROJECT")
    over = parse_sets(a.set or [])
    bad_workflow(over)
    known = KNOWN | set(addon_keys("SETTING_KEYS_BOOL")) | set(addon_keys("SETTING_KEYS"))
    unset = [RENAMED.get(k, k) for k in (a.unset or [])]
    for k in list(over) + unset:
        if k not in known:
            warn(f"unknown key {k}, saving it as is")
    with editing_json(f, {}) as doc:
        s = doc.setdefault("settings", {})
        s.update(over)
        to_new_names(s)
        gone = []
        for k in unset:  # an old name goes with its new one
            if any([s.pop(x, None) is not None for x in [k] + [o for o, n in RENAMED.items() if n == k]]):
                gone.append(k)
    if over:
        print(f"{f}: " + ", ".join(f"{k}={v}" for k, v in over.items()))
    if gone:
        print(f"{f}: removed {', '.join(gone)} (the plugin's defaults apply again)")
    print("the brand profile, the brand tone and each video's reel.json still override these defaults")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show"); p.add_argument("edit", nargs="?"); p.add_argument("--set", nargs="*")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("save"); p.add_argument("edit"); p.add_argument("--set", nargs="+", required=True); p.set_defaults(fn=cmd_save)
    p = sub.add_parser("defaults", help="show or edit the project's own defaults (<project>/reel-defaults.json)")
    p.add_argument("--set", nargs="+"); p.add_argument("--unset", nargs="+"); p.set_defaults(fn=cmd_defaults)
    p = sub.add_parser("preset", help="a series preset: save one video's answers, use them for the next ones")
    p.add_argument("action", choices=["save", "use", "list"]); p.add_argument("name", nargs="?")
    p.add_argument("edit", nargs="?", help="use: the video to apply the preset to")
    p.add_argument("--from", dest="source", help="save: the video whose answers the preset keeps")
    p.set_defaults(fn=cmd_preset)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
