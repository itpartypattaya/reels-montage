# -*- coding: utf-8 -*-
"""Edit settings of a video: brand, style, inserts (B-roll, code scenes, memes), intensity, and what will actually
turn on.

Layers (the right one overrides the left): assets/reel-defaults.json ← brand tone (brand.json → tone, a brand_tones
preset) ← brand profile (inserts) ← edit/<id>/reel.json ← --set. The brand tone also sets the ceilings (memes,
transitions, full scenes); to go beyond them on explicit request: reelcfg.py save edit/<id> --set tone_override=true
(violations become warnings).

    python scripts/reelcfg.py show edit/4821 [--set use_memes=true intensity=active] [--json]
    python scripts/reelcfg.py save edit/4821 --set brand=acme style=v2 use_broll=false use_memes=false

`show` prints the resulting settings, where each key comes from, and the fallback: what turns off by itself (for
example online sources when the online-sources add-on `it-reelsmaker-online` is not installed) and why. This is not an
error: editing continues with what is available.
`save` adds keys to edit/<id>/reel.json (only the ones given; defaults are not copied there); it creates the folder
edit/<id> if it doesn't exist yet. reel.json is the only source of the video's settings: visual_plan.py takes them
from here.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (SETTING_KEYS_BOOL, edit_dir, editing_json, effective, load_config, online, parse_sets,
                          tone_summary, utf8_stdio, warn)

KNOWN = set(SETTING_KEYS_BOOL) | {"brand", "style", "subtitles", "intensity", "broll_priority", "meme_priority",
                                  "footage_dirs", "memes_dirs", "generation_engines", "library_dirs", "meme_size",
                                  "scene_tone", "tone_override"}


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
            ("  online (add-on)", "online_memes")]
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
    with editing_json(e / "reel.json", {}) as reel:
        reel.update(over)
    print(f"{e / 'reel.json'}: " + ", ".join(f"{k}={v}" for k, v in over.items()))
    from visual_plan import refresh_plan
    if refresh_plan(e):
        print("the settings snapshot in visual_plan.json is updated")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show"); p.add_argument("edit", nargs="?"); p.add_argument("--set", nargs="*")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("save"); p.add_argument("edit"); p.add_argument("--set", nargs="+", required=True); p.set_defaults(fn=cmd_save)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
