# -*- coding: utf-8 -*-
"""The storyboard sheet: a settled frame of every scene, insert, graphics card, the hook and the end card in one
picture, numbered, before the full render. The person answers by number ("3 and 7: redo"), and a full render (8-10 min
per minute of video on a laptop) runs once the sheet is approved.

    python scripts/board.py edit/4821 [--props edit/4821/reelkit-props.json] [--remotion reels] [--comp ReelKit]
        [--shots] [--transitions] [--defects] [--cols 5] [--per-page 20] [--scale 0.3334]

When: after `visual_plan.py export … --props` (step 8), before the full render (`kit.py render`). Again after fixes: it is cheap.

How:
  1. Panels from the props the render will use (scene times, tones and transitions as exported) and the plan (what
     each insert and card is): a scene at the moment its whole text is on screen + 0.3 s (the timing validate uses,
     kit/scenes/tones.ts), never past its settled window; B-roll, a meme, a graphics card (keep_clear) at their middle;
     the hook headline and the end card once settled. --shots adds a frame per camera shot, --transitions the middle of
     every smooth scene entrance (a muddy double exposure shows there), --defects the middle of every picture defect
     of defects.py with how it is handled (covered by …, accepted, open).
  2. One Remotion call renders them all: the props get `sample.frames`, frame k of the composition shows frame
     frames[k] of the video, frozen (kit/Sample.tsx, kit 1.10.0+), `render --sequence --frames=0-(n-1)`. Measured on a
     58 s video: 4 frames in 9 s, the same 4 as separate stills in 41 s, bit-identical to them. A per-video composition
     (--comp Reel<id>) needs <Sampled sample={p.sample}> around its content.
  3. The sheet: --cols columns of 360x640 panels, a caption under each (number, time, what, sound, transitions; Latin
     letters only: Pillow's built-in font has no Cyrillic) and the number large on the panel; more than --per-page
     panels go to further pages. board.md holds the same numbers with the full on-screen texts.

Output: edit/<id>/board/board-01.jpg (-02, ...), edit/<id>/board/board.md; frames and props in edit/<id>/board/.
"""
import argparse
import math
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import edit_dir, load_json, project_root, project_settings, remotion_tmp, save_json  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SETTLE_S = 0.3  # after the whole text is on screen: the frame the person judges, as a post would show it
END_CARD_S = 2.6  # the kit's default end card length (ReelKit.tsx)


def npx():
    return shutil.which("npx") or shutil.which("npx.cmd") or "npx"


def remotion_dir(given):
    """--remotion, else it-reelsmaker.json -> remotion_dir (relative to the project folder)."""
    rem = given or project_settings().get("remotion_dir")
    if not rem or str(rem).startswith("${"):
        sys.exit("no Remotion project: pass --remotion <folder> (or set remotion_dir in it-reelsmaker.json)")
    p = Path(rem)
    p = (p if p.is_absolute() else project_root() / p).resolve()
    if not ((p / "package.json").is_file() and (p / "src").is_dir()):
        sys.exit(f"{p} is not a Remotion project (no package.json or src/)")
    return p


def props_path(e, given):
    p = Path(given) if given else e / "reelkit-props.json"
    if not p.is_file():
        sys.exit(f"no props: {p} (visual_plan.py export {e.name} --remotion … --props {p})")
    return p.resolve()


def total_frames(props, fps):
    """The video's frames as the kit counts them (reelKitMetadata): the rough cut plus the end card."""
    v = round(float(props["captions"]["duration"]) * fps)
    card = props.get("endCard")
    return max(1, v + (round(float(card.get("seconds") or END_CARD_S) * fps) if card else 0))


def sample_props(props, frames, probe=False, media=True):
    out = dict(props)
    out["sample"] = {"frames": [int(f) for f in frames], **({"probe": True} if probe else {}), **({} if media else {"media": False})}
    return out


def render_frames(rem, comp, props_file, n, outdir, scale, fmt="jpeg", log="error"):
    """Frames 0..n-1 of a sampled composition into outdir (cleared first). -> (sorted image paths, Remotion output)."""
    outdir = Path(outdir)
    if outdir.exists():
        for f in outdir.iterdir():
            if f.is_file():
                f.unlink()
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [npx(), "--no", "remotion", "render", comp, str(outdir), "--sequence", f"--frames=0-{n - 1}",
           f"--image-format={fmt}", f"--scale={scale}", "--muted", f"--log={log}", f"--props={Path(props_file).resolve()}"]
    try:
        with remotion_tmp(rem, props_file, comp, quiet=True) as (env, extra):  # its temp files go when it ends
            r = subprocess.run(cmd + extra, cwd=rem, env=env, capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
    except OSError as x:
        sys.exit(f"cannot run npx ({x}): Node.js with Remotion is needed (doctor.py)")
    txt = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        plain = re.sub(r"\x1b\[[0-9;]*m", "", txt)
        keep = [l for l in plain.splitlines() if l.strip() and not re.match(r"\s*(at |\d+: )", l)]
        hint = ("\nhint: props.sample needs kit 1.10.0+ (kit.py check / update); a per-video composition needs "
                "<Sampled sample={p.sample}> around its content" if "sample" in plain.lower() else "")
        sys.exit(f"Remotion render failed (code {r.returncode}):\n" + "\n".join(keep[-12:]) + hint)
    num = lambda p: int(re.findall(r"\d+", p.stem)[-1]) if re.findall(r"\d+", p.stem) else -1
    imgs = sorted((p for p in outdir.iterdir() if p.suffix.lower() in (".jpeg", ".jpg", ".png")), key=num)
    return imgs, txt


def ascii_only(s):
    return re.sub(r"[^\x20-\x7e]", "?", str(s))


def fmt_s(t):
    return f"{t:.1f}s"


def panels(props, plan, doc, fps, shots=False, transitions=False, defects=()):
    """-> [{frame, label, text, sound, tin, tout, what}] sorted by frame; one panel per frame. defects: picture defects
    (defects.py) as [(defect, how it is handled)], a panel at the middle of each."""
    import visual_plan as vp
    tones = {k: v for k, v in (doc.get("scene_tones") or {}).items() if not k.startswith("_")}
    words = (props.get("captions") or {}).get("words") or []
    only = not props.get("video")
    total = total_frames(props, fps)
    what = {i.get("id"): i for i in plan.get("inserts", [])}
    out = []

    def add(frame, label, text="", sound="", tin="", tout="", note=""):
        out.append({"frame": max(0, min(total - 1, int(frame))), "label": label, "text": text, "sound": sound or "",
                    "tin": tin or "", "tout": tout or "", "what": note})

    hook = props.get("hook")
    if hook and hook.get("text"):
        until = round(float(hook.get("until") or 2.4) * fps)
        add(min(until - 9, 33), "hook", hook["text"], note="hook headline")
    for sc in props.get("scenes") or []:
        if sc.get("type") == "cover":
            continue
        # the tone as the kit picks it (tones.ts pickTone): the scene's own → the video's (props.sceneTone) → the
        # brand's → calm (review: a scene without its own tone was timed as calm while the kit drew the video's tone)
        own = [x for x in (sc.get("tone"), props.get("sceneTone"), ((props.get("brand") or {}).get("tone") or {}).get("scene_tone"))
               if x in tones]
        T = tones.get(own[0] if own else "calm") or {"in": 14, "out": 9}
        mode, typ = sc.get("mode"), sc.get("type")
        tl = vp.scene_timeline(sc, T, mode, fps, words, only)
        lines = (sc.get("text") or {}).get("lines") or []
        need = "items" in (vp.SCENE_TYPES.get(typ) or {}).get("need", [])
        times = [it["t"] for it in sc.get("items") or [] if isinstance(it, dict) and isinstance(it.get("t"), (int, float))]
        if need and times:  # itemFrames in the kit: an item enters at max(lead, its own time)
            full = max(tl["lead"], vp.jround((max(times) - sc["start"]) * fps)) + tl["inF"]
        else:
            full = vp.text_full_on(sc, typ, lines, tl, fps, words)
        k = max(0, min(full + vp.jround(SETTLE_S * fps), tl["settle_to"] - 1, tl["n"] - 1))
        start = vp.jround(sc["start"] * fps)
        body = " / ".join(lines + [str(it.get("text", "")) for it in sc.get("items") or [] if isinstance(it, dict) and it.get("text")])
        note = (what.get(sc.get("id")) or {}).get("what") or ""
        add(start + k, f"{sc.get('id')} {typ}/{mode}", body, sc.get("sound"), tl["tin"], tl["tout"], note)
        if transitions and tl["tin"] != "cut":
            # the most blended frame: the middle of the layout change (split/panel/window/full: the speaker moves
            # away), or of the content's own entrance in overlay, which changes no layout (review: it was halved twice)
            lay = vp.layout_frames(tl["tin"], T, "in") if mode != "overlay" else 0
            add(start + (lay // 2 if lay else tl["lead"] + tl["inF"] // 2), f"{sc.get('id')} in:{tl['tin']} (mid)", body,
                tin=tl["tin"], note="mid-transition")
    for ins in props.get("inserts") or []:
        mid = (float(ins["start"]) + float(ins["dur"]) / 2) * fps
        add(mid, f"{ins.get('id')} {ins.get('kind')}/{ins.get('mode') or ''}".rstrip("/"),
            tin=ins.get("transition_in"), tout=ins.get("transition_out"), note=(what.get(ins.get("id")) or {}).get("what") or "")
    # a callout once it is fully on screen (its label's zones per 0.25 s are for the audit, not cards)
    for c in props.get("callouts") or []:
        tone = c.get("tone") or props.get("sceneTone") or "calm"
        tin = (tones.get(tone) or {}).get("in", vp.CALLOUT_TIMES["calm_in"])
        add(round(float(c["start"]) * fps) + vp.callout_entrance(tin, len(c.get("lines") or []) > 1), f"{c['id']} callout",
            " / ".join(c.get("lines") or []), note=(what.get(c["id"]) or {}).get("what") or "")
    for n, kc in enumerate([k for k in plan.get("keep_clear", []) if not k.get("scene") and not k.get("callout")], 1):
        add((float(kc["start"]) + float(kc["end"])) / 2 * fps, f"card {n}", note=kc.get("what") or "")
    if shots:
        cam = props.get("camera") or []
        for i, sh in enumerate(cam):
            nxt = cam[i + 1]["t"] if i + 1 < len(cam) else props["captions"]["duration"]
            add((float(sh["t"]) + min(0.5, (float(nxt) - float(sh["t"])) / 2)) * fps, f"shot z{float(sh.get('z', 1)):.2f}",
                note="camera shot")
    for d, how in defects:
        add((d["start"] + d["end"]) / 2 * fps, f"{d['id']} {d['kind']}", d.get("words") or "", note=how)
    card = props.get("endCard")
    if card:
        v = round(float(props["captions"]["duration"]) * fps)
        add(v + 27, "end card" if card.get("line1") else "logo sting",
            " / ".join(x for x in (card.get("line1"), card.get("line2")) if x), note="ending")
    merged = {}
    for p in sorted(out, key=lambda x: x["frame"]):  # two panels on one frame are one picture: one panel, both labels
        if p["frame"] in merged:
            m = merged[p["frame"]]
            m["label"] += f" + {p['label']}"
            m["text"] = " | ".join(x for x in (m["text"], p["text"]) if x)
        else:
            merged[p["frame"]] = dict(p)
    return list(merged.values())


def font(size):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1: one fixed size
        return ImageFont.load_default()


def sheet(images, pans, base, fps, cols=5, per_page=20, cw=360):
    """Tile the panels into pages of `per_page`: base-01.jpg, base-02.jpg… -> [paths]."""
    from PIL import Image, ImageDraw
    cap_h, gap = 50, 8
    pages = []
    f_cap, f_num = font(16), font(34)
    for pi in range(math.ceil(len(pans) / per_page)):
        chunk = list(zip(images, pans))[pi * per_page:(pi + 1) * per_page]
        ch = round(cw * 16 / 9)
        rows = math.ceil(len(chunk) / cols)
        W, H = cols * cw + (cols + 1) * gap, rows * (ch + cap_h) + (rows + 1) * gap
        page = Image.new("RGB", (W, H), (17, 17, 17))
        d = ImageDraw.Draw(page)
        for k, (img, p) in enumerate(chunk):
            n = pi * per_page + k + 1
            x, y = gap + (k % cols) * (cw + gap), gap + (k // cols) * (ch + cap_h + gap)
            with Image.open(img) as im:
                page.paste(im.convert("RGB").resize((cw, ch)), (x, y))
            d.rectangle([x, y, x + 64, y + 46], fill=(0, 0, 0))
            d.text((x + 8, y + 4), str(n), fill=(255, 255, 255), font=f_num)
            line1 = ascii_only(f"{fmt_s(p['frame'] / fps)}  {p['label']}")
            bits = [f"sfx:{p['sound']}" if p["sound"] else "", f"in:{p['tin']}" if p["tin"] else "", f"out:{p['tout']}" if p["tout"] else ""]
            line2 = ascii_only("  ".join(b for b in bits if b) or p["what"])
            d.text((x + 4, y + ch + 6), line1[:44], fill=(235, 235, 235), font=f_cap)
            d.text((x + 4, y + ch + 27), line2[:44], fill=(170, 170, 170), font=f_cap)
        out = Path(f"{base}-{pi + 1:02d}.jpg")
        page.save(out, quality=88)
        pages.append(out)
    return pages


def board_md(e, pans, pages, fps):
    rows = ["| # | Time | What | On screen | Sound | In / out |", "|---|---|---|---|---|---|"]
    cell = lambda s: str(s).replace("|", "/").replace("\n", " ")
    for n, p in enumerate(pans, 1):
        what = p["label"] + (f" ({p['what']})" if p["what"] else "")
        rows.append(f"| {n} | {fmt_s(p['frame'] / fps)} | {cell(what)} | {cell(p['text'])} | {p['sound']} | "
                    f"{p['tin'] or '-'} / {p['tout'] or '-'} |")
    head = (f"# Storyboard: {e.name}\n\nSheet: " + ", ".join(f"`{x.name}`" for x in pages) +
            ". Answer by number: which panels to redo and how.\n\n")
    (e / "board" / "board.md").write_text(head + "\n".join(rows) + "\n", encoding="utf-8")


NOTHING = "nothing to put on the sheet"  # check.py reads this line: the step passes, there is nothing to show


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit")
    ap.add_argument("--props", help="the props the render will use (default edit/<id>/reelkit-props.json)")
    ap.add_argument("--remotion", help="the Remotion project (default: it-reelsmaker.json -> remotion_dir)")
    ap.add_argument("--comp", default="ReelKit", help="composition (a per-video Reel<id> must wrap its content in <Sampled>)")
    ap.add_argument("--shots", action="store_true", help="also a frame per camera shot")
    ap.add_argument("--transitions", action="store_true", help="also the middle of every smooth scene entrance")
    ap.add_argument("--defects", action="store_true", help="also the middle of every picture defect (defects.py): is it covered")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--per-page", type=int, default=20)
    ap.add_argument("--scale", type=float, default=0.3334, help="render scale (0.3334: 360x640 panels)")
    a = ap.parse_args()
    try:
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("Pillow is needed for the sheet: pip install Pillow")
    import visual_plan as vp
    e = edit_dir(a.edit)
    pf = props_path(e, a.props)
    props = load_json(pf)
    plan = vp.load_plan(e) if vp.plan_path(e).is_file() else {}
    _s, _prov, doc, _bdir, _brand = vp.current_settings(e, plan)
    fps = (doc.get("scenes") or {}).get("fps", 30)
    found = []
    if a.defects:
        d_all, stale = vp.load_defects(e)
        if stale:
            print("warning: " + stale)
        _e, _w, state = vp.defect_issues(e, plan, _s, doc, load_json(e / "captions.json", {}) or {})
        found = [(d, state.get(d["id"], "open")) for d in d_all]
    pans = panels(props, plan, doc, fps, a.shots, a.transitions, found)
    if not pans:  # a clip with no graphics passes (English test talk: check.py failed its board step on one)
        print(f"{NOTHING}: no hook, scenes, inserts, cards or end card in the props, so no sheet "
              "(--shots adds the camera shots)")
        return
    rem = remotion_dir(a.remotion)
    bdir = e / "board"
    bdir.mkdir(exist_ok=True)
    sp = bdir / "board-props.json"
    save_json(sp, sample_props(props, [p["frame"] for p in pans]))
    t0 = time.time()
    imgs, _ = render_frames(rem, a.comp, sp, len(pans), bdir / "frames", a.scale)
    if len(imgs) != len(pans):
        sys.exit(f"Remotion wrote {len(imgs)} frames for {len(pans)} panels in {bdir / 'frames'}")
    for old in bdir.glob("board-[0-9][0-9].jpg"):
        old.unlink()
    pages = sheet(imgs, pans, bdir / "board", fps, a.cols, a.per_page, cw=360)
    board_md(e, pans, pages, fps)
    print(f"{len(pans)} panel(s), rendered in {time.time() - t0:.0f} s")
    for n, p in enumerate(pans, 1):
        print(f"  {n:>2}  {fmt_s(p['frame'] / fps):>6}  {p['label']}" + (f"  — {p['text'][:60]}" if p["text"] else ""))
    print("sheet: " + ", ".join(str(x) for x in pages))
    print(f"table: {bdir / 'board.md'}  (show both; the person answers by panel number)")


if __name__ == "__main__":
    main()
