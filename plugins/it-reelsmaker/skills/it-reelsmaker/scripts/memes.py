# -*- coding: utf-8 -*-
"""The meme layer: the project's own memes folder and the asset library -> no meme. Online memes (Creative Commons
images cleared for commercial use) come only with the online-sources add-on it-reelsmaker-online.

A meme goes in only if it amplifies a joke, an emotion, irony or the meaning of a specific line, never "to liven things
up". Rights come before the find: a commercial video burns in only memes with rights own / licensed / cc / library.

    python scripts/memes.py index [--dir memes assets/reactions]   # index + contact sheets memes/_index/sheet-*.jpg
    python scripts/memes.py set <id> description="a statue shrugs" emotion=confusion,irony rights=licensed \\
                       use_when="when expectations don't match reality"
    python scripts/memes.py search "confusion the candidate didn't get it" [--edit edit/<id>] [--limit 5] [--emotion confusion]
    python scripts/memes.py prepare <id> --edit edit/<id> --insert m01 [--mode popup|cutaway]   # -> inserts/m01.*, status ready
    python scripts/memes.py place edit/<id> m01 [--face x,y,w,h [--face x,y,w,h]|--no-face] [--size s|m|l] [--slot auto|top-left|...]
                       # size and position: not on the face, subtitles, UI or graphics; preview inserts/m01-place.jpg
    python scripts/addon.py memes search|fetch ...                  # online memes: only with the online-sources add-on

Own folders: memes_dirs (default memes/) or --dir. A sidecar next to the file (optional): <name>.json
{"description","tags","emotion","use_when","rights","source"} or <name>.txt (a description). The asset library
(library_dirs and the assets_dir setting): memes tagged in <library>/_catalog/memes.json, next to the catalog of
library_catalog.py. Rights: own: made by you; licensed: there is a license; cc: Creative Commons
(attribution in the post description); library: per the asset library catalog's verdict; unknown: not known (a brand
with memes_policy=strict won't take such a meme); blocked: forbidden by third-party rights (set from the catalog), never
burned in by any brand.
"""
import argparse, datetime, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (GIF_EXT, IMAGE_EXT, VIDEO_EXT, edit_dir, editing_json, effective, library_dirs, load_config, load_json, media_kind,
                          online, probe, project_root, rel, run, score, tokens, utf8_stdio, warn)
from footage import put_insert, rights_blocked, save_credit, verdict_columns

RIGHTS_OK = {"own", "licensed", "cc", "library"}  # library: the asset library, rights per the catalog's verdict
# "blocked": the catalog forbids it for third-party rights (a celebrity, a film still, stock people): no brand burns it in
CREDIT_KEYS = ("attribution", "license", "license_version", "license_url", "creator", "creator_url")


def is_blocked(m):
    return m.get("rights") == "blocked" or rights_blocked(m.get("verdicts"), m.get("verdict_why", ""), m.get("rights_block"))


def memes_root(project):
    return project / "memes"


def index_path(project):
    return memes_root(project) / "_index.json"


def slug(s):
    # an id from a file name: Latin and Cyrillic letters and digits stay, everything else becomes "-"
    s = re.sub(r"[^0-9a-z\N{CYRILLIC SMALL LETTER A}-\N{CYRILLIC SMALL LETTER YA}\N{CYRILLIC SMALL LETTER IO}]+", "-",
               s.lower()).strip("-")
    return s[:48] or "meme"


def cmd_index(a):
    from PIL import Image, ImageDraw
    project = project_root()
    s, *_ = load_config(None)
    dirs = [project / d for d in (a.dir or s.get("memes_dirs", ["memes"]))]
    root = memes_root(project)
    root.mkdir(exist_ok=True)
    # 1) the slow part (ffprobe, images, sidecars) runs without locking the index
    scanned = []
    for d in dirs:
        if not d.is_dir():
            warn(f"no folder {d}")
            continue
        for p in sorted(d.rglob("*")):
            if not p.is_file() or p.name.startswith("_") or "_index" in p.parts or p.suffix.lower() not in IMAGE_EXT | GIF_EXT | VIDEO_EXT:
                continue
            kind = media_kind(p)
            info = probe(p) if kind in ("video", "gif") else {}
            w = h = None
            alpha = False
            if kind == "image":
                try:
                    im = Image.open(p)
                    w, h = im.size
                    alpha = im.mode in ("RGBA", "LA") and im.getextrema()[-1][0] < 250
                except Exception:
                    pass
            side = {}
            if p.with_suffix(".json").exists() and p.suffix.lower() != ".json":
                side = load_json(p.with_suffix(".json"), {})
            elif p.with_suffix(".txt").exists():
                side = {"description": p.with_suffix(".txt").read_text(encoding="utf-8").strip()}
            scanned.append((p, kind, info, w, h, alpha, side))
    # 2) the merge into the index runs under the lock, on the fresh file (memes.py set edits from another session are kept)
    with editing_json(index_path(project), {}) as idx:
        merge_index(idx, project, s, scanned)
    write_sheets(project, root, idx)


def merge_index(idx, project, s, scanned):
    by_path = {v["path"]: k for k, v in idx.items()}
    seen = set()
    for p, kind, info, w, h, alpha, side in scanned:
        r = rel(p, project)
        mid = by_path.get(r) or slug(p.stem)
        while mid in idx and idx[mid]["path"] != r:
            mid += "-2"
        e = idx.get(mid, {})
        e.update({"path": r, "type": kind, "w": w or info.get("w"), "h": h or info.get("h"),
                  "dur": round(info["dur"], 2) if info.get("dur") else None, "has_audio": bool(info.get("has_audio")),
                  "alpha": alpha})
        e["tags"] = sorted(set(e.get("tags", [])) | set(tokens(p.stem)) | set(side.get("tags", [])))
        for k in ("description", "emotion", "use_when", "rights", "source", *CREDIT_KEYS):
            if side.get(k) and not e.get(k):
                e[k] = side[k]
        e.setdefault("description", "")
        e.setdefault("emotion", [])
        e.setdefault("use_when", "")
        e.setdefault("rights", "unknown")
        e.setdefault("added", datetime.date.today().isoformat())
        idx[mid] = e
        seen.add(mid)
    # libraries with a catalog (<library>/_catalog, library_catalog.py): memes are tagged in _catalog/memes.json, the
    # verdict and rights come from catalog.json
    for lib in library_dirs(project, s):
        cdir = project / lib / "_catalog"
        ann = (load_json(cdir / "memes.json", {}) or {}).get("items", {})
        cat = {e["path"]: e for e in (load_json(cdir / "catalog.json", []) or [])}
        for path, m in ann.items():
            c = cat.get(path)
            p = project / lib / path
            if not c or not p.exists():
                continue
            r = rel(p, project)
            mid = by_path.get(r) or slug(Path(lib).name + "-" + Path(path).parent.name + "-" + p.stem)
            while mid in idx and idx[mid]["path"] != r:
                mid += "-2"
            e = idx.get(mid, {})
            verdicts = verdict_columns(c)  # all the catalog's verdict columns (one per brand), not just one brand's
            blocked = rights_blocked(verdicts, c.get("why", ""), c.get("rights_block"))
            e.update({"path": r, "type": media_kind(p), "w": c.get("w"), "h": c.get("h"), "dur": c.get("dur"),
                      "has_audio": False, "alpha": c.get("alpha") or c.get("bg") == "transparent",
                      "description": m.get("description", ""), "emotion": m.get("emotion", []),
                      "use_when": m.get("use_when", ""), "rights": "blocked" if blocked else "library", "library": lib,
                      "sheet": m.get("sheet"), "verdicts": verdicts, "verdict_why": c.get("why", "")})
            e["tags"] = sorted(set(tokens(Path(path).parent.name)) | set(tokens(m.get("description", ""))))
            e.setdefault("added", datetime.date.today().isoformat())
            idx[mid] = e
            seen.add(mid)
    gone = [k for k in idx if k not in seen and not (project / idx[k]["path"]).exists()]
    for k in gone:
        del idx[k]


def write_sheets(project, root, idx):
    from PIL import Image, ImageDraw
    sd = root / "_index"
    sd.mkdir(exist_ok=True)
    for f in sd.glob("sheet-*"):
        f.unlink()
    T, cols = 180, 6
    items = sorted(idx.items())
    for page in range(0, len(items), 36):
        chunk = items[page:page + 36]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * T, rows * (T + 16)), (255, 255, 255))
        d = ImageDraw.Draw(sheet)
        lines = []
        for n, (mid, e) in enumerate(chunk):
            x, y = (n % cols) * T, (n // cols) * (T + 16)
            p = project / e["path"]
            try:
                if e["type"] in ("video", "gif"):
                    tmp = sd / "_f.png"
                    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(e.get('dur') or 1) / 2:.2f}", "-i", p, "-frames:v", "1", tmp])
                    im = Image.open(tmp).convert("RGBA")
                else:
                    im = Image.open(p).convert("RGBA")
                im.thumbnail((T, T))
                bg = Image.new("RGBA", (T, T), (200, 200, 200, 255))
                bg.alpha_composite(im, ((T - im.width) // 2, (T - im.height) // 2))
                sheet.paste(bg.convert("RGB"), (x, y))
            except Exception:
                d.rectangle([x, y, x + T - 1, y + T - 1], fill=(220, 0, 0))
            col = (0, 120, 0) if e.get("rights") in RIGHTS_OK else (200, 120, 0)
            d.rectangle([x, y + T, x + T - 1, y + T + 15], fill=col)
            d.text((x + 3, y + T + 2), f"{page + n} {e['type']}", fill=(255, 255, 255))
            lines.append(f"{page + n}\t{mid}\t{e['path']}\t{e.get('rights')}\t{e.get('description', '')}")
        sheet.save(sd / f"sheet-{page // 36:02d}.jpg", quality=82)
        (sd / f"sheet-{page // 36:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    if (sd / "_f.png").exists():
        (sd / "_f.png").unlink()
    nodesc = sum(1 for e in idx.values() if not e.get("description"))
    nblock = sum(1 for e in idx.values() if is_blocked(e))
    print(f"{index_path(project)}: {len(idx)} memes (without a description {nodesc}, rights unknown "
          f"{sum(1 for e in idx.values() if e.get('rights') not in RIGHTS_OK and not is_blocked(e))}, "
          f"blocked by third-party rights {nblock}); sheets: {sd}/sheet-*.jpg "
          f"(green stripe: rights cleared, orange: unknown or blocked)")


def cmd_set(a):
    project = project_root()
    with editing_json(index_path(project), {}) as idx:  # sys.exit inside: the index stays unchanged
        if a.id not in idx:
            sys.exit(f"no meme {a.id} (run memes.py index)")
        for it in a.pairs:
            k, v = it.split("=", 1)
            if k in ("emotion", "tags"):
                v = [x.strip() for x in v.split(",") if x.strip()]
            if k == "rights" and v not in RIGHTS_OK | {"unknown"}:
                sys.exit("rights: own | licensed | cc | library | unknown")
            idx[a.id][k] = v
    print(f"{a.id}: " + ", ".join(a.pairs))


def search(query, project, brand=None, limit=5, emotion=None):
    idx = load_json(index_path(project), {})
    strict = (brand or {}).get("memes_policy") == "strict"
    res, excluded = [], 0
    for mid, e in idx.items():
        text = " ".join([e.get("description", ""), " ".join(e.get("tags", [])), " ".join(e.get("emotion", [])),
                         e.get("use_when", "")])
        sc = score(query, text)
        if sc > 0 and score(query, " ".join(e.get("emotion", []))) > 0:
            sc = round(sc + 0.2, 3)  # the emotion matched: a meme about the same feeling, not just the same word
        if emotion and not any(score(emotion, x) for x in e.get("emotion", [])):
            continue
        if sc <= 0:
            continue
        if is_blocked(e):  # third-party rights: for any brand and any policy
            excluded += 1
            continue
        if strict and e.get("rights") not in RIGHTS_OK:
            excluded += 1
            continue
        vf = (brand or {}).get("asset_verdicts")
        v = (e.get("verdicts") or {}).get(vf) if vf else None
        if v == "no":
            excluded += 1
            continue
        e = {**e, "note": f"verdict {vf}: {v} - {e.get('verdict_why')}" if v == "caution" else ""}
        res.append({"id": mid, "score": sc, **e})
    res.sort(key=lambda x: -x["score"])
    return res[:limit], excluded


def cmd_search(a):
    project = project_root()
    e = edit_dir(a.edit) if a.edit else None
    s, prov, doc, bdir, brand = load_config(e)
    res, excl = search(a.query, project, brand, a.limit, a.emotion)
    if not res:
        print("no fitting meme in the local folders" + (f" ({excl} more would fit but are hidden: third-party rights, unknown rights under a strict policy, or the brand's verdict)" if excl else "")
              + (" -> online memes (add-on: addon.py memes search ...) or no meme: keep the shot" if online() else " -> no meme: keep the shot"))
        return
    for k, m in enumerate(res):
        print(f"  [{k}] {m['id']:<28} {m['score']:.2f} {m['type']:<5} {m.get('rights'):<8} {m.get('description') or m['path']}"
              + (f" | emotion: {', '.join(m['emotion'])}" if m.get("emotion") else "")
              + (f" | {m['note']}" if m.get("note") else ""))
    if excl:
        print(f"  (+{excl} hidden: blocked by third-party rights, rights unknown under the strict policy, or the brand's verdict \"no\")")


def prepare_meme(src, out_base, mode, dur, audio=False):
    """popup: an image -> PNG with the long side <= 460 px (alpha kept); a GIF or video -> MP4 <= 460 px, looped to dur.
    cutaway: a 1080×1920 MP4, the whole meme centered on a blurred background made from itself."""
    from PIL import Image
    kind = media_kind(src)
    if mode == "popup" and kind == "image":
        out = out_base.with_suffix(".png")
        im = Image.open(src).convert("RGBA")
        box = im.getchannel("A").getbbox()
        if box:
            im = im.crop(box)  # transparent margins throw off the scale
        k = min(460 / im.width, 460 / im.height, 3.0)  # the ceiling meme_layout max_side: a meme never takes half the screen
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out)
        return out
    out = out_base.with_suffix(".mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    inp = ["-loop", "1", "-t", f"{dur:.3f}", "-i", src] if kind == "image" else ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", src]
    if mode == "popup":
        vf = ("scale=w='min(460,iw)':h='min(460,ih)':force_original_aspect_ratio=decrease:flags=lanczos,"
              "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30,format=yuv420p")
        args = ["-vf", vf]
    else:
        args = ["-filter_complex",
                "[0:v]fps=30,split[f][g];[g]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:3,"
                "eq=brightness=-0.12[bg];[f]scale=1000:1600:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]", "-map", "[v]"]
        if audio and kind == "video":
            args += ["-map", "0:a?"]
    aud = ["-c:a", "aac", "-b:a", "160k"] if audio and kind == "video" else ["-an"]
    run(["ffmpeg", "-v", "error", "-y", *inp, *args, "-t", f"{dur:.3f}", "-r", "30", "-c:v", "libx264", "-crf", "18",
         *aud, "-movflags", "+faststart", out])
    return out


def cmd_prepare(a):
    from visual_plan import load_plan
    project = project_root()
    idx = load_json(index_path(project), {})
    m = idx.get(a.id)
    if not m:
        sys.exit(f"no meme {a.id}")
    if is_blocked(m):
        sys.exit(f"{a.id}: blocked by third-party rights ({m.get('verdict_why') or 'the catalog verdict'}); no brand may burn it in")
    e = edit_dir(a.edit)
    plan = load_plan(e)  # read only; ffmpeg runs outside the lock, the write goes through put_insert
    i = next((x for x in plan["inserts"] if x["id"] == a.insert and x["kind"] == "meme"), None)
    if not i:
        sys.exit(f"no meme insert {a.insert}")
    mode = a.mode or i.get("mode") or "popup"
    out = prepare_meme(project / m["path"], e / "inserts" / i["id"], mode, i["dur"], audio=bool(i.get("audio")))
    plate = False
    if out.suffix == ".png":
        from PIL import Image
        im = Image.open(out).convert("RGBA")
        px = [(r, g, b) for r, g, b, al in im.resize((64, 64)).getdata() if al > 128]
        light = sum(1 for r, g, b in px if (r + g + b) / 3 > 200) / max(1, len(px))
        plate = light > 0.6  # a light pictogram on a transparent background needs a backing, or it vanishes on a light frame
    i.update({"meme_id": a.id, "mode": mode, "file": rel(out, e), "rights": m.get("rights", "unknown"), "status": "ready",
              "plate": plate,
              "source": "online" if m["path"].startswith("memes/online/") else "local",
              "credit": {"meme": a.id, "path": m["path"], "rights": m.get("rights"), "source": m.get("source"),
                         **{k: m.get(k) for k in CREDIT_KEYS}}})
    if i["credit"].get("attribution") or m.get("rights") == "cc":
        # CC: attribution in the post description; it is collected into the same inserts/credits.json as B-roll credits
        if not i["credit"].get("attribution"):
            warn(f"{a.id}: rights cc but no attribution; add attribution to the meme's sidecar and run memes.py index again")
        save_credit(e, {"insert": i["id"], "kind": "meme", **i["credit"]})
    else:  # the meme was replaced with one that needs no credit: the insert's old attribution goes
        save_credit(e, None, insert=i["id"])
    put_insert(e, i, ("meme_id", "mode", "file", "rights", "status", "plate", "source", "credit"))
    print(f"{a.insert}: {a.id} -> {i['file']} ({mode}, rights {i['rights']})")


def cmd_place(a):
    """Size and position of a pop-up meme (meme_layout.py): a slot at the frame edge, clear of the face, subtitles, UI
    and graphics."""
    from visual_plan import current_settings, load_plan
    import meme_layout as ml
    e = edit_dir(a.edit)
    plan = load_plan(e)  # read only; frames and face detection run outside the lock, the write goes through put_insert
    i = next((x for x in plan["inserts"] if x["id"] == a.insert and x["kind"] == "meme"), None)
    if not i:
        sys.exit(f"no meme insert {a.insert}")
    if i.get("mode") == "cutaway":
        print(f"{a.insert}: cutaway: a full-frame meme, there is no position to choose (0.6-1.2 s, at most one per video)")
        return
    s, prov, doc, bdir, brand = current_settings(e, plan)  # reel.json is the only source (meme_size and the rest)
    cam = None
    if a.cam:
        try:
            cam = [float(v) for v in a.cam.split(",")]
        except ValueError:
            cam = []
        if len(cam) != 3:
            sys.exit(f"--cam {a.cam}: expected z,cx,cy")
    L = ml.layout(s, doc)
    t0, t1 = i["start"], i["start"] + i["dur"]
    keep = [k for k in plan.get("keep_clear", []) if k["start"] < t1 and k["end"] > t0]
    paths = ml.frames(e, t0, t1, e / "inserts" / f"_{i['id']}")
    if a.no_face:
        faces = []
    elif a.face:
        # --face a --face b and --face a b both work; action=append gives a list of groups
        faces = []
        for f in (x for grp in a.face for x in grp):
            try:
                box = [int(float(v)) for v in f.split(",")]
            except ValueError:
                box = []
            if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
                sys.exit(f"--face {f}: expected a box x,y,w,h in 1080×1920 coordinates")
            faces.append(box)
    else:
        faces = ml.auto_faces(paths, e, t0, t1, cam)
        if faces is not None:
            faces = [list(x) for x in {tuple(f) for f in faces}]
            fu = [min(f[0] for f in faces), min(f[1] for f in faces), max(f[0] + f[2] for f in faces), max(f[1] + f[3] for f in faces)] if faces else None
            print("faces (YuNet): " + (f"{len(faces)} boxes, together x {fu[0]}-{fu[2]}, y {fu[1]}-{fu[3]}" if faces else "none"))
    if faces is None:
        g = ml.sheet(paths, e / "inserts" / f"{i['id']}-grid.jpg", L, keep=keep)
        print(f"{a.insert}: the face position is unknown (the YuNet model is not available). Look at {g} (a 100 px grid in "
              f"1080×1920 coordinates) and repeat with --face x,y,w,h (the head box over all three frames; several "
              f"people: several --face) or with --no-face if there is no face in the frame")
        return
    aspect = ml.meme_aspect(e / i["file"] if i.get("file") else None,
                            fallback=(lambda m: (m.get("w") or 1) / (m.get("h") or 1))(
                                load_json(index_path(project_root()), {}).get(i.get("meme_id"), {})))
    res = ml.choose(L, aspect, faces, keep, a.size, a.slot)
    if not res:
        g = ml.sheet(paths, e / "inserts" / f"{i['id']}-grid.jpg", L, faces=faces, keep=keep)
        sys.exit(f"{a.insert}: no free room in any slot, even at size s: no meme here; move it to another line or use "
                 f"cutaway (full frame, short). Frames: {g}")
    box, size, slot = res
    i.update({"box": box, "meme_size": size, "slot": slot, "faces": faces, "cam": cam})  # cam: faces are checked in screen coordinates
    prev = ml.sheet(paths, e / "inserts" / f"{i['id']}-place.jpg", L, faces=faces, box=box, keep=keep,
                    meme=(e / i["file"]) if i.get("file") else None)
    put_insert(e, i, ("box", "meme_size", "slot", "faces", "cam"))
    print(f"{a.insert}: {slot}, {box[2]}×{box[3]} px (size {size}, ≈{round(box[2] * box[3] / (1080 * 1920) * 100)} % of the frame) "
          f"-> x {box[0]}, y {box[1]}; preview: {prev}")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("index"); p.add_argument("--dir", nargs="*"); p.set_defaults(fn=cmd_index)
    p = sub.add_parser("set"); p.add_argument("id"); p.add_argument("pairs", nargs="+"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--edit"); p.add_argument("--limit", type=int, default=5)
    p.add_argument("--emotion"); p.set_defaults(fn=cmd_search)
    p = sub.add_parser("prepare"); p.add_argument("id"); p.add_argument("--edit", required=True); p.add_argument("--insert", required=True)
    p.add_argument("--mode", choices=["popup", "cutaway"]); p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("place"); p.add_argument("edit"); p.add_argument("insert")
    p.add_argument("--face", nargs="+", action="append",
                   help="a face box x,y,w,h in 1080×1920 coordinates; several: --face a --face b or --face a b")
    p.add_argument("--no-face", action="store_true"); p.add_argument("--size", choices=["s", "m", "l"])
    p.add_argument("--slot", default="auto"); p.add_argument("--cam", help="z,cx,cy: the video's camera at this point")
    p.set_defaults(fn=cmd_place)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
