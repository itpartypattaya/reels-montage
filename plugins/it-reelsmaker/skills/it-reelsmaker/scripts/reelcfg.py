# -*- coding: utf-8 -*-
"""Edit settings of a video: brand, style, inserts (B-roll, code scenes, memes), intensity, and what will actually
turn on.

Layers (the right one overrides the left): assets/reel-defaults.json ← brand tone defaults (brand.json → tone, a
brand_tones preset) ← the project's own reel-defaults.json ← brand profile (inserts) ← edit/<id>/reel.json ← --set. The brand tone also sets the ceilings (memes,
transitions, full scenes); to go beyond them on explicit request: reelcfg.py save edit/<id> --set tone_override=true
(violations become warnings).

    python scripts/reelcfg.py show edit/4821 [--set use_memes=true intensity=active] [--json]
    python scripts/reelcfg.py save edit/4821 --set brand=acme style=v2 use_broll=false use_memes=false
    python scripts/reelcfg.py save edit/4821 --set format=framed label="CANDIDATE INTERVIEW" [window=[25,340,1030,1240]]
    python scripts/reelcfg.py defaults [--set brand=acme use_memes=false] [--unset use_memes]   # the project's defaults

`show` prints the resulting settings, where each key comes from, and the fallback: what turns off by itself (for
example online sources when the online-sources add-on `it-reelsmaker-online` is not installed) and why. This is not an
error: editing continues with what is available.
`save` adds keys to edit/<id>/reel.json (only the ones given; defaults are not copied there); it creates the folder
edit/<id> if it doesn't exist yet. reel.json is the only source of the video's settings: visual_plan.py takes them
from here.
format=framed: a horizontal source in a rounded window on the style's field, with an optional caps label above it
(references/techniques.md); window (x, y, w, h on the 1080x1920 screen) and label are its options. The kit draws it
from the props that visual_plan.py export writes; faces.py and visual_plan.py read the same window.
`defaults` shows or edits <project>/reel-defaults.json: your defaults for every video of the project (default brand,
inserts, library folders, ...), in the same format as the plugin's assets/reel-defaults.json, only the keys you change.
--set/--unset touch the "settings" keys; other sections (intensity and brand tone labels in your language, ...) are
edited in the file by hand. The file stays in the project: plugin updates never touch it.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (PROJECT_DEFAULTS, SETTING_KEYS_BOOL, edit_dir, editing_json, effective, framed_issues,
                          framed_of, is_project, load_config, load_json, online, parse_sets, project_root, tone_summary,
                          utf8_stdio, warn)

KNOWN = set(SETTING_KEYS_BOOL) | {"brand", "style", "subtitles", "intensity", "broll_priority", "meme_priority",
                                  "footage_dirs", "memes_dirs", "generation_engines", "library_dirs", "meme_size",
                                  "scene_tone", "tone_override", "subtitles_lang", "subtitles_shade",
                                  "format", "window", "label"}  # format: "framed" (window, label) or "full"


def addon_keys(name):
    """Setting keys added by the online-sources add-on (its module's <name> list); empty when it is not installed."""
    return list(getattr(online(), name, None) or ())


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
                        + " (the kit draws the window)" if fr else "full frame (vertical)")
          + "".join("\n  ⚠ " + m for m in framed_issues(s)))
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


def cmd_save(a):
    over = parse_sets(a.set)
    known = KNOWN | set(addon_keys("SETTING_KEYS_BOOL")) | set(addon_keys("SETTING_KEYS"))
    for k in over:
        if k not in known:
            warn(f"unknown key {k}, saving it as is")
    e = edit_dir(a.edit, create=True)  # step 0 of a new video: the edit/<id> folder doesn't exist yet
    if {"format", "window", "label"} & set(over):  # the framed format's keys are checked together, before saving
        bad = framed_issues({**(load_json(e / "reel.json", {}) or {}), **over})
        if bad:
            sys.exit("not saved: " + "; ".join(bad))
        new = {**(load_json(e / "reel.json", {}) or {}), **over}
        if new.get("format") != "framed" and (new.get("window") is not None or new.get("label")):
            warn("window and label are options of format framed: without format=framed the kit ignores them")
    with editing_json(e / "reel.json", {}) as reel:
        reel.update(over)
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
    known = KNOWN | set(addon_keys("SETTING_KEYS_BOOL")) | set(addon_keys("SETTING_KEYS"))
    for k in list(over) + list(a.unset or []):
        if k not in known:
            warn(f"unknown key {k}, saving it as is")
    with editing_json(f, {}) as doc:
        s = doc.setdefault("settings", {})
        s.update(over)
        gone = [k for k in (a.unset or []) if s.pop(k, None) is not None]
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
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
