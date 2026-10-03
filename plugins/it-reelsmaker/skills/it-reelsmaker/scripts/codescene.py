# -*- coding: utf-8 -*-
"""Code scenes for B-roll: footage the agent writes itself as a Remotion component (motion design written in code).

Motion graphics, diagrams, 3D objects, interfaces, abstractions, symbolic objects in the brand colors: 1080×1920,
about 6 s, rendered on this computer. Free; needs only a Remotion project. An insert with source "generated" in
visual_plan.json carries a brief in `gen`; for code scenes `gen.engine` is "code". Inserts with engine "model" are
handled by the online-sources add-on `it-reelsmaker-online`; without it they stay pending and the main footage stays.

    python scripts/codescene.py manifest edit/<id>                 # generated/manifest.json + briefs.md for the inserts
    python scripts/codescene.py validate edit/<id>                 # brief fields, text in the frame, imagery the brand forbids
    python scripts/codescene.py scaffold edit/<id> b02 --remotion reels   # scene stub src/gen/<Comp>.tsx + registry
    python scripts/codescene.py render   edit/<id> b02 --remotion reels   # render the scene -> generated/b02.mp4 -> ingest
    python scripts/codescene.py ingest   edit/<id>                 # pick up clips generated/<insert>.mp4 (also ones put there by hand)

Brief fields (insert.gen in visual_plan.json):
  engine (code|model), subject, action, camera, composition, lighting, mood, start, end, [setting], [style], [seconds], [use_from]
"""
import argparse, math, os, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import SKILL, edit_dir, effective, forbidden_hits, locked, online, rel, save_json, save_text, utf8_stdio, warn

FIELDS = ["subject", "action", "camera", "composition", "lighting", "mood", "start", "end"]
CODE_STYLE = "clean flat motion graphics in the brand colors, calm easing, no photorealism"
MODEL_HOLD = 'engine "model" needs the online-sources add-on it-reelsmaker-online; the main footage stays'


def txt(v):
    """A brief field as text: only a non-empty string counts (null, numbers, lists mean "not filled")."""
    return v.strip() if isinstance(v, str) else ""


def num(v, default):
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return None


def _cp(words):
    """Words given as Unicode code points (keeps this file plain English text)."""
    return ["".join(chr(int(c, 16)) for c in w.split()) for w in words]


# Text in the frame, also in Russian (the stems for "inscription", "text", "logo"), as code points.
_RU_TEXT = _cp(["43d 430 434 43f 438 441", "442 435 43a 441 442", "43b 43e 433 43e 442 438 43f"])
TEXT_RE = re.compile(r"\b(text|caption|subtitle|letters|words|logo|sign that reads|title|typography|"
                     + "|".join(_RU_TEXT) + r")\b", re.I)


def plan_of(e):
    """The plan, read only, plus the current settings (reel.json is the only source; the snapshot in the plan is not
    applied). Writing goes through put(): under the lock, on a fresh copy of the plan; renders and ffmpeg run outside
    the lock."""
    from visual_plan import current_settings, load_plan
    plan = load_plan(e)
    return plan, current_settings(e, plan)


INS_KEYS = ("status", "fallback", "file", "src_in", "credit", "gen")


def put(e, i, keys=INS_KEYS):
    from footage import put_insert
    return put_insert(e, i, keys)


def gen_inserts(plan):
    return [i for i in plan["inserts"] if i["kind"] == "broll" and i.get("source") == "generated"]


def engine_of(i, eff):
    """The insert's engine: gen.engine; otherwise "code" when code scenes are on, else "model"."""
    return (i.get("gen") or {}).get("engine") or ("code" if eff.get("generated_code") else "model")


def scene_words(g):
    """All the scene's text fields in one string (for the checks)."""
    return " ".join(txt(g.get(f)) for f in FIELDS + ["setting", "style"])


def scene_text(g, seconds, style, accents=""):
    """The scene description from the gen fields: what is in the frame, how it moves, the camera, the light, the mood.
    `style` is used when gen.style is empty; `accents` is added after the mood."""
    miss = [f for f in FIELDS if not txt(g.get(f))]
    if miss:
        raise ValueError(f"not filled: {', '.join(miss)}")
    g = {**g, **{f: txt(g.get(f)) for f in FIELDS + ["setting", "style"]}}
    style = g.get("style") or style
    end = g["end"] if re.search(r"\bhold", g["end"], re.I) else g["end"] + ", holding still for the final second"
    lines = [
        f"Vertical 9:16 {g['composition']}.",
        f"Subject: {g['subject']}.",
        f"Action: begins with {g['start']}; over {seconds} seconds {g['action']}; ends with {end}.",
        f"Camera: {g['camera']}, smooth, single continuous shot, no cuts.",
        f"Setting & light: {g['setting'] + ', ' if g.get('setting') else ''}{g['lighting']}.",
        f"Mood & style: {g['mood']}{accents}, {style}.",
        "Clean frame: no on-screen text, no captions, no logos, no watermarks, no brand names; "
        "keep the key subject in the middle third (top and bottom are covered by app interface).",
    ]
    return "\n".join(lines)


def check(i, brand, lim_seconds=None):
    """Checks of the gen fields shared by both engines -> (errors, warnings)."""
    g = i.get("gen") or {}
    errs, warns = [], []
    miss = [f for f in FIELDS if not txt(g.get(f))]
    if miss:
        errs.append(f"{i['id']}: not filled: {', '.join(miss)} (a non-empty string is needed)")
    bad = [f for f in ("setting", "style") if g.get(f) not in (None, "") and not isinstance(g.get(f), str)]
    if bad:
        errs.append(f"{i['id']}: {', '.join(bad)} must be a string")
    text = scene_words(g)
    negated = r"\b(no|without)\s+(\w+\s+){0,2}(text|words|letters|logos?)\b|\binstead of (\w+\s+)?(text|words)\b|\bblank\b"
    if TEXT_RE.search(re.sub(negated, " ", text, flags=re.I)):
        warns.append(f"{i['id']}: the scene description has text or a logo in it; text goes on as a layer of the "
                     f"video (Remotion), not inside the scene")
    for f in forbidden_hits(brand, text):
        warns.append(f"{i['id']}: looks like imagery the brand forbids: “{f}”")
    sec, use_from = num(g.get("seconds"), 6), num(g.get("use_from"), 0.3)
    if sec is None or use_from is None:
        errs.append(f"{i['id']}: seconds and use_from must be numbers")
    elif sec < i["dur"] + use_from:
        errs.append(f"{i['id']}: the clip ({int(sec)} s) is shorter than the insert ({i['dur']} s) + use_from")
    return errs, warns


def base_item(i, engine, sec, errs, warns):
    """The manifest entry fields shared by both engines."""
    return {"id": i["id"], "engine": engine, "segment": i.get("segment"), "start": i["start"], "dur_in_video": i["dur"],
            "seconds": sec, "aspect": "9:16", "what": i["what"], "why": i["why"], "fields": i.get("gen") or {},
            "status": i["status"], "file": i.get("file"), "errors": errs, "warnings": warns}


def md_head(i, engine, sec):
    return [f"## {i['id']} · {engine} · {i['start']:.2f} s +{i['dur']} s (clip {sec} s)", "",
            f"**What:** {i['what']}  ", f"**Why:** {i['why']}", ""]


def md_tail(errs, warns):
    return [f"- ✗ {m}" for m in errs] + [f"- ⚠ {m}" for m in warns] + [""]


def cmd_manifest(a):
    e = edit_dir(a.edit)
    plan, (s, prov, doc, bdir, brand) = plan_of(e)
    eff, why = effective(s)
    ext = online()
    items, md, held = [], [f"# Code scene briefs: {plan['id']}", ""], []
    colors = {k: v for k, v in ((brand or {}).get("colors") or {}).items() if isinstance(v, str)}
    for i in gen_inserts(plan):
        g = i.setdefault("gen", {})
        engine = engine_of(i, eff)
        g["engine"] = engine
        # whole seconds, rounded up: a 2.86 s clip must not become 2 s and end up shorter than its insert
        sec = math.ceil(num(g.get("seconds"), None) or num(s.get("generation_seconds"), 6) or 6)
        g["seconds"] = sec
        errs, warns = check(i, brand)
        item = base_item(i, engine, sec, errs, warns)
        md += md_head(i, engine, sec)
        if engine == "model":
            if ext:
                note = f'engine "model" is handled by the online-sources add-on: python scripts/addon.py gen manifest {a.edit}'
            else:
                note = MODEL_HOLD
                if i["status"] != "ready":
                    i["status"], i["fallback"] = "pending", MODEL_HOLD
                    item["status"] = i["status"]
                    held.append(i)
            item["note"] = note
            md += [note + ".", ""]
        else:
            comp = comp_name(plan["id"], i["id"])
            item.update({"brief": scene_text(g, sec, CODE_STYLE) if not errs else None, "colors": colors,
                         "remotion": {"component": comp, "file": f"src/gen/{comp}.tsx"}})
            if item["brief"]:
                md += ["```text", item["brief"], "```", ""]
            if colors:
                md += ["Brand colors: " + ", ".join(f"{k} {v}" for k, v in colors.items())
                       + " (in the scene: brand.colors.<name>, not HEX values).  "]
            md += [f"Code scene: `{item['remotion']['file']}` (`codescene.py scaffold` -> write the scene -> `render`).", ""]
        items.append(item)
        md += md_tail(errs, warns)
    out = e / "generated"
    out.mkdir(exist_ok=True)
    save_json(out / "manifest.json", {"id": plan["id"], "brand": plan["brand"], "items": items})
    (out / "briefs.md").write_text("\n".join(md), encoding="utf-8")
    for i in gen_inserts(plan):
        put(e, i, ("gen", "status", "fallback") if i in held else ("gen",))  # engine/seconds into the fresh plan, locked
    n_model = sum(1 for x in items if x["engine"] == "model")
    print(f"{out / 'manifest.json'}: {len(items)} insert(s) ({len(items) - n_model} code, {n_model} model); "
          f"briefs: {out / 'briefs.md'}")
    for x in items:
        if x["engine"] == "model":
            print(f"· {x['id']}: {x['note']}")
    bad = [x for x in items if x["errors"]]
    for x in bad:
        for m in x["errors"]:
            print("✗ " + m)
    return 1 if bad else 0


def cmd_validate(a):
    e = edit_dir(a.edit)
    plan, (s, _, _, _, brand) = plan_of(e)
    eff, _ = effective(s)
    ext = online()
    n = 0
    for i in gen_inserts(plan):
        errs, warns = check(i, brand)
        n += len(errs)
        for m in errs:
            print("✗ " + m)
        for m in warns:
            print("⚠ " + m)
        if engine_of(i, eff) == "model":
            print(f"· {i['id']}: " + (f'engine "model": its own checks run in python scripts/addon.py gen validate {a.edit}'
                                      if ext else MODEL_HOLD))
    print(f"generated inserts: {len(gen_inserts(plan))}, errors: {n}")
    sys.exit(1 if n else 0)


def comp_name(pid, iid):
    return "Gen" + re.sub(r"[^A-Za-z0-9]", "", pid.title()) + iid


SCENE_TMPL = '''import React from "react";
import {{ AbsoluteFill, Easing, interpolate, useCurrentFrame }} from "remotion";
import brand from "../brands/{brand}.json";

// Code scene for edit/{pid}, insert {iid} ({dur} s in the video, clip {sec} s).
// What: {what}
// Why: {why}
// Scene: {fields}
// Rules: 1080x1920, 30 fps, NO text in the frame (text is a layer of the video), brand colors (brand.colors), one action
// and one camera move; the main thing in the middle third (the top 220 px and the bottom 420 px are covered by the UI);
// the first 0.3 s and the last second are calm (the insert takes a piece from the middle). Calm motion: easing out,
// no bounces. More: the it-reelsmaker skill, references/inserts.md, "Code scenes".

export const DURATION = {frames};
const clamp = {{ extrapolateLeft: "clamp", extrapolateRight: "clamp" }} as const;

export const {comp}: React.FC = () => {{
  const frame = useCurrentFrame();
  const cam = interpolate(frame, [0, DURATION], [1, 1.06], {{ ...clamp, easing: Easing.inOut(Easing.cubic) }});
  return (
    <AbsoluteFill style={{{{ backgroundColor: brand.colors.primary, overflow: "hidden" }}}}>
      <AbsoluteFill style={{{{ transform: `scale(${{cam}})` }}}}>
        {{/* scene: {what_short} */}}
      </AbsoluteFill>
    </AbsoluteFill>
  );
}};
'''


def ensure_registry(rem):
    reg = rem / "src" / "gen" / "registry.ts"
    if not reg.exists():
        reg.parent.mkdir(parents=True, exist_ok=True)
        save_text(reg, 'import React from "react";\n\n// Code scenes (codescene.py scaffold). Root.tsx registers them as compositions.\n'
                       'export type GenEntry = { id: string; component: React.FC; durationInFrames: number };\n\n'
                       'export const GEN: GenEntry[] = [\n];\n')
    return reg


def outside_plugin(rem):
    """The scene goes into the person's Remotion project, never into the plugin folder (it is replaced on update)."""
    plugin = os.path.normcase(str(SKILL.parents[1]))
    try:
        within = os.path.commonpath([plugin, os.path.normcase(str(rem))]) == plugin
    except ValueError:  # different drives
        within = False
    if within:
        sys.exit(f"--remotion {rem} is inside the plugin folder; use your own Remotion project")
    return rem


def root_hint(rem):
    """Root.tsx has to register the registry's scenes as compositions, otherwise render can't find them."""
    root = next((p for p in (rem / "src" / "Root.tsx", rem / "src" / "Root.jsx") if p.is_file()), None)
    if root and "gen/registry" in root.read_text(encoding="utf-8", errors="replace"):
        return None
    return (f"{rel(root, rem) if root else 'src/Root.tsx'} does not register code scenes yet; add there:\n"
            '  import { GEN } from "./gen/registry";\n'
            "  {GEN.map((g) => (<Composition key={g.id} id={g.id} component={g.component} "
            "durationInFrames={g.durationInFrames} fps={30} width={1080} height={1920} />))}")


def cmd_scaffold(a):
    e = edit_dir(a.edit)
    plan, _ = plan_of(e)
    i = next((x for x in plan["inserts"] if x["id"] == a.insert), None)
    if not i or i.get("source") != "generated":
        sys.exit(f"{a.insert}: no such insert with source=generated")
    rem = outside_plugin(Path(a.remotion).resolve())
    if not (rem / "src" / "brands" / f"{plan['brand']}.json").exists():
        sys.exit(f"no src/brands/{plan['brand']}.json; first run python scripts/brand.py export {plan['brand']} "
                 f"--remotion {a.remotion}")
    g = i.setdefault("gen", {})
    g["engine"] = "code"
    sec = math.ceil(num(g.get("seconds"), 6) or 6)
    comp = comp_name(plan["id"], i["id"])
    f = rem / "src" / "gen" / f"{comp}.tsx"
    if f.exists() and not a.force:
        print(f"{f} already exists; write the scene in it (--force overwrites it with the stub)")
    else:
        f.parent.mkdir(parents=True, exist_ok=True)
        fields = "; ".join(f"{k}: {g.get(k)}" for k in FIELDS if g.get(k))
        f.write_text(SCENE_TMPL.format(brand=plan["brand"], pid=plan["id"], iid=i["id"], dur=i["dur"], sec=sec,
                                       what=i["what"], why=i["why"], fields=fields or "(fill in gen in the plan)",
                                       frames=sec * 30, comp=comp, what_short=i["what"][:60]), encoding="utf-8")
    reg = rem / "src" / "gen" / "registry.ts"
    with locked(reg):
        ensure_registry(rem)
        t = reg.read_text(encoding="utf-8")
        if f'"{comp}"' not in t:
            t = t.replace('import React from "react";\n', f'import React from "react";\nimport {{ {comp}, DURATION as D_{comp} }} from "./{comp}";\n', 1)
            t = t.replace("\n];", f'\n  {{ id: "{comp}", component: {comp}, durationInFrames: D_{comp} }},\n];', 1)
            save_text(reg, t)
    g["remotion"] = {"component": comp, "file": rel(f, rem)}
    put(e, i, ("gen",))
    print(f"{f}\ncomposition {comp} in src/gen/registry.ts; next: write the scene, then "
          f"`codescene.py render {a.edit} {a.insert} --remotion {a.remotion}`")
    hint = root_hint(rem)
    if hint:
        print(hint)


def ingest_one(e, i, src):
    from footage import prepare
    g = i.get("gen") or {}
    out = e / "inserts" / f"{i['id']}.mp4"
    info = prepare(src, out, i["dur"], num(g.get("use_from"), 0.3) or 0.3)
    note = g.get("publish_note") if g.get("engine") == "model" else None  # set by the online-sources add-on
    i.update({"file": rel(out, e), "status": "ready", "src_in": 0.0,
              "credit": {"provider": "generated:" + g.get("engine", "?"), "model": g.get("model"), "raw": rel(src, e),
                         "license": "own clip" + (f" ({note})" if note else "")}})
    return info


def safe_ingest(e, i, src):
    """ingest_one without a crash: a short or broken clip -> the insert stays pending, the edit goes on."""
    from footage import err_text
    try:
        return ingest_one(e, i, src)
    except Exception as ex:
        i["status"], i["fallback"] = "pending", f"clip {Path(src).name} not prepared ({err_text(ex, 200)}); main footage"
        i.pop("file", None)
        warn(f"{i['id']}: {i['fallback']}")
        return None


def cmd_render(a):
    e = edit_dir(a.edit)
    plan, _ = plan_of(e)
    i = next((x for x in plan["inserts"] if x["id"] == a.insert), None)
    if not i:
        sys.exit(f"no insert {a.insert}")
    rem = Path(a.remotion).resolve()
    if not (rem / "package.json").is_file():
        sys.exit(f"not a Remotion project (no package.json): {rem}")
    comp = (i.get("gen") or {}).get("remotion", {}).get("component") or comp_name(plan["id"], i["id"])
    raw = e / "generated" / f"{i['id']}.mp4"
    raw.parent.mkdir(parents=True, exist_ok=True)
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    # --no: use the project's own Remotion, never install packages on the fly
    cmd = [npx, "--no", "remotion", "render", comp, str(raw), "--codec=h264", "--muted", "--log=error"]
    try:
        r = subprocess.run(cmd, cwd=rem, capture_output=True, text=True, encoding="utf-8", errors="replace")
        code, out, err = r.returncode, r.stdout, r.stderr
    except OSError as ex:  # npx is not installed or not on PATH
        code, out, err = 1, "", f"{npx}: {ex}"
    if code != 0 or not raw.exists():
        i["status"], i["fallback"] = "pending", "the scene render failed; main footage until it is fixed"
        put(e, i)
        print(out[-800:], err[-1500:])
        sys.exit(f"{a.insert}: render of {comp} failed")
    info = safe_ingest(e, i, raw)
    put(e, i)
    if info:
        print(f"{a.insert}: {comp} -> {raw.name} -> {i['file']} ({info['w']}×{info['h']}, {info['dur']:.2f} s) ready")


def cmd_ingest(a):
    e = edit_dir(a.edit)
    plan, _ = plan_of(e)
    done = left = 0
    for i in gen_inserts(plan):
        if i["status"] == "ready":
            continue
        cands = [p for ext in (".mp4", ".mov", ".webm") for p in [e / "generated" / f"{i['id']}{ext}"] if p.exists()]
        if not cands:
            left += 1
            continue
        info = safe_ingest(e, i, cands[0])
        if info and (i.get("gen") or {}).get("job"):  # a job of the online-sources add-on: done, never resumed
            i["gen"]["job"]["status"] = "DONE"
        put(e, i)
        if not info:
            left += 1
            continue
        done += 1
        print(f"{i['id']}: {cands[0].name} -> {i['file']} ({info['w']}×{info['h']}, {info['dur']:.2f} s) ready")
    print(f"picked up: {done}; waiting for a clip: {left} (they don't go into the render: main footage)")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("manifest"); p.add_argument("edit"); p.set_defaults(fn=lambda a: sys.exit(cmd_manifest(a)))
    p = sub.add_parser("validate"); p.add_argument("edit"); p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("scaffold"); p.add_argument("edit"); p.add_argument("insert"); p.add_argument("--remotion", required=True)
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_scaffold)
    p = sub.add_parser("render"); p.add_argument("edit"); p.add_argument("insert"); p.add_argument("--remotion", required=True)
    p.set_defaults(fn=cmd_render)
    p = sub.add_parser("ingest"); p.add_argument("edit"); p.set_defaults(fn=cmd_ingest)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
