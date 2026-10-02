# -*- coding: utf-8 -*-
"""B-roll sources: the project's own footage -> a local library -> online sources (only with the online-sources
add-on it-reelsmaker-online) -> generated inserts (codescene.py).

A source is a class with search(query, opts) -> [candidates] and fetch(candidate, folder) -> file. The add-on plugs
its sources into PROVIDERS. Any source error (no network, the service is down) is a warning and an empty list with
exit code 0: the edit continues with what there is.

    python scripts/footage.py providers [--edit edit/<id>]           # which sources are available, and why not
    python scripts/footage.py index [--dir footage ...]              # index of the project's videos + contact sheets for descriptions
    python scripts/footage.py describe IMG_4821.MOV "wide shot, a person at a desk" [--tags office,desk] [--exclude]
    python scripts/footage.py search "pool view balcony" [--edit edit/<id>] [--providers project,local] [--limit 6]
    python scripts/footage.py plan-search edit/<id>                  # candidates for every B-roll insert of the plan, by source priority
    python scripts/footage.py pick edit/<id> b01 [--candidate 0] [--in 2.0] [--lut brand] [--yes]   # fetch/take + prepare -> ready
    python scripts/footage.py prepare <file> --out edit/<id>/inserts/b01.mp4 --dur 1.6 [--in 2.0] [--fit cover|contain]
                       [--focus 0.5,0.4] [--speed 0.8] [--lut brand|<hald.png> --lut-strength 0.7] [--edit edit/<id>]

Online sources and their terms are described by the add-on. A download from an online source happens only after the
person approves the visual plan (the plan lists the source and the file size): `pick --yes`.
"""
import argparse, json, re, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (IMAGE_EXT, VIDEO_EXT, brand_file, edit_dir, editing_json, effective, library_dirs, load_config,
                          load_json, online, probe, project_root, rel, run, save_json, score, utf8_stdio, warn)

MAX_PAD_S = 0.5  # how much a short source may be stretched with a freeze frame (tpad clone); more -> other footage
EXCLUDE_DIRS = {"edit", "node_modules", "out", "_catalog", ".git", "plans", "memes"}


def err_text(ex, limit=160):
    """An error for output and JSON: type + text. With the online add-on loaded, secrets are masked first (a source's
    error may contain them), then the text is cut."""
    ext = online()
    return f"{type(ex).__name__}: {(ext.scrub(ex) if ext else str(ex))[:limit]}"


# --- Library rights: a ban for THIRD-PARTY RIGHTS applies to every brand ------------------------------------
VERDICT_WORDS = {"ok", "caution", "no", "check license"}
RIGHTS_RE = re.compile(r"image rights|likeness|third[- ]party rights|someone else's rights|celebrit|famous|politic|"
                       r"(?:film|movie) stills?|frames? from (?:a |the )?(?:film|movie)|stock (?:people|person|models?)|"
                       r"real (?:people|person)", re.I)


def verdict_columns(entry):
    """The catalog's verdict columns (one per brand, ...): fields whose value is a verdict."""
    return {k: v for k, v in (entry or {}).items() if isinstance(v, str) and v in VERDICT_WORDS and k != "why"}


def rights_blocked(verdicts, why="", explicit=None):
    """True: a "no" for third-party rights (celebrities, film stills, stock people); no brand may embed it.
    explicit: the catalog's rights_block field, if set by hand."""
    if explicit:
        return True
    return any(v == "no" for v in (verdicts or {}).values()) and bool(RIGHTS_RE.search(why or ""))


def cand(**kw):
    base = {"provider": None, "id": None, "title": "", "path": None, "url": None, "page_url": None, "w": None, "h": None,
            "dur": None, "size_mb": None, "license": None, "author": None, "score": 0.0, "embed": True, "notes": ""}
    base.update(kw)
    return base


# --- Sources ------------------------------------------------------------------------------------------------

class Provider:
    """A footage source. Duck-typed: the online add-on's sources have the same name, online, key_env, available(),
    search() and fetch(), and check their own availability."""
    name = "base"
    online = False
    key_env = None

    def available(self):
        return True, ""

    def search(self, query, o):
        return []

    def fetch(self, c, folder):
        return Path(c["path"])


class ProjectProvider(Provider):
    """The project's own videos and photos: videos in the project folder + videos and photos in the footage_dirs
    folders. Photos only from footage_dirs on purpose: the project folder also holds covers, screenshots and
    exported frames, which must not turn into B-roll. Descriptions live in footage_index.json."""
    name = "project"

    def files(self, o):
        root = o["project"]
        out = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT]
        for d in o["settings"].get("footage_dirs", []):
            dd = root / d
            if dd.is_dir():
                out += [p for p in dd.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT | IMAGE_EXT]
        if o.get("edit"):
            out += [p for p in o["edit"].glob("broll*") if p.suffix.lower() in VIDEO_EXT]
        main = set()
        edl = load_json(o["edit"] / "edl.json", {}) if o.get("edit") else {}
        for v in (edl.get("sources") or {}).values():
            main.add(Path(v).name.lower())
        # finished renders (<brand>-<slug>-YYYY-MM-DD[-master].mp4) are not sources
        render = re.compile(r"\d{4}-\d{2}-\d{2}(-master)?\.mp4$", re.I)
        return [p for p in out if p.name.lower() not in main and not render.search(p.name)]

    def search(self, query, o):
        idx = load_json(o["project"] / "footage_index.json", {})
        res = []
        for p in self.files(o):
            r = rel(p, o["project"])
            meta = idx.get(r, {})
            if meta.get("exclude"):
                continue
            text = " ".join([p.stem, meta.get("description", ""), " ".join(meta.get("tags", []))])
            sc = score(query, text)
            note = "" if meta.get("description") else "no description: look at the contact sheet (footage.py index)"
            if sc > 0 or not meta.get("description"):
                res.append(cand(provider=self.name, id=r, title=meta.get("description") or p.name, path=str(p),
                                w=meta.get("w"), h=meta.get("h"), dur=meta.get("dur"),
                                size_mb=round(p.stat().st_size / 1e6, 1), license="own footage", score=sc, notes=note))
        return res


class LocalProvider(Provider):
    """Shared libraries (library_dirs): a library with a catalog (_catalog/catalog.json, library_catalog.py) is
    searched by its catalog, the others by file names. Videos only on purpose: images in a library are icons and
    graphics for scenes, and memes are picked by memes.py; photos for B-roll go into footage_dirs."""
    name = "local"

    def search(self, query, o):
        res = []
        verdict_field = (o.get("brand") or {}).get("asset_verdicts")
        for d in library_dirs(o["project"], o["settings"]):
            root = (o["project"] / d)
            if not root.is_dir():
                continue
            cat = load_json(root / "_catalog" / "catalog.json")
            if cat:
                for e in cat:
                    p = root / e["path"]
                    if e.get("kind") != "visual" or p.suffix.lower() not in VIDEO_EXT:
                        continue
                    # a ban for third-party rights: always; a style verdict: only if the brand sets its own column
                    if rights_blocked(verdict_columns(e), e.get("why", ""), e.get("rights_block")):
                        continue
                    v = e.get(verdict_field) if verdict_field else None
                    if v == "no":
                        continue
                    sc = score(query, e["path"].replace("/", " ") + " " + e.get("why", ""))
                    if sc <= 0:
                        continue
                    res.append(cand(provider=self.name, id=e["path"], title=e["path"], path=str(p), w=e.get("w"),
                                    h=e.get("h"), dur=e.get("dur"), size_mb=round(e.get("size", 0) / 1e6, 1),
                                    license="project library (license per catalog)", score=sc,
                                    notes=(f"verdict {verdict_field}: {v} - {e.get('why')}" if v else "") +
                                          (f"; background {e.get('bg')}" if e.get("bg") else "")))
            else:
                for p in root.rglob("*"):
                    if p.is_file() and p.suffix.lower() in VIDEO_EXT:
                        sc = score(query, rel(p, root).replace("/", " "))
                        if sc > 0:
                            res.append(cand(provider=self.name, id=rel(p, o["project"]), title=p.name, path=str(p),
                                            size_mb=round(p.stat().st_size / 1e6, 1), license="unknown", score=sc))
        return res


def _online_providers():
    """The online add-on's sources, if it is linked. A broken add-on must not break local editing."""
    ext = online()
    if not ext:
        return []
    try:
        return list(ext.footage_providers())
    except Exception as ex:
        warn(f"the online add-on's sources did not load ({type(ex).__name__}: {str(ex)[:160]}); "
             f"continuing with local sources")
        return []


PROVIDERS = {p.name: p for p in (ProjectProvider(), LocalProvider(), *_online_providers())}


def put_insert(e, i, keys, when=None):
    """Write the fields `keys` of insert i into the plan under the lock, re-reading the plan (parallel sessions):
    other sessions' changes to other inserts and fields are not lost. Downloads, ffmpeg and generation run before
    the call, not under the lock. when(cur) -> False: the insert was changed in another session, don't overwrite it.
    A key missing from i deletes the field."""
    from visual_plan import editing_plan
    with editing_plan(e) as plan:
        cur = next((x for x in plan["inserts"] if x["id"] == i["id"]), None)
        if cur is None:
            warn(f"{i['id']}: the insert is no longer in the plan (deleted in another session); result not written")
            return False
        if when and not when(cur):
            warn(f"{i['id']}: the insert was changed in another session while this ran; not overwriting it")
            return False
        for k in keys:
            if k in i:
                cur[k] = i[k]
            else:
                cur.pop(k, None)
    return True


def context(edit=None, overrides=None):
    project = project_root()
    e = edit_dir(edit) if edit else None
    s, prov, doc, bdir, brand = load_config(e, overrides)
    eff, why = effective(s)
    return {"project": project, "edit": e, "settings": s, "brand": brand, "brand_dir": bdir, "eff": eff, "why": why}


def order(o):
    """Sources in B-roll priority order, given the settings and availability."""
    out = []
    for src in o["settings"].get("broll_priority", []):
        if src == "project" and o["eff"].get("project_footage"):
            out.append("project")
        elif src == "local" and o["eff"].get("local_footage"):
            out.append("local")
        elif src == "online" and o["settings"].get("use_broll") and o["settings"].get("use_online_footage"):
            out += [p for p in o["settings"].get("online_footage_providers", []) if p in PROVIDERS]
    return out


def safe_search(name, query, o):
    p = PROVIDERS.get(name)
    if not p:
        warn(f"no source {name}")
        return []
    ok, why = p.available()
    if not ok:
        warn(f"{name}: skipped ({why})")
        return []
    try:
        res = p.search(query, o)
        return sorted(res, key=lambda c: -c["score"])
    except Exception as ex:
        warn(f"{name}: search error ({err_text(ex)}); skipping it, the edit continues")
        return []


def show(cands, limit):
    for k, c in enumerate(cands[:limit]):
        print(f"  [{k}] {c['provider']:<8} {c['score']:.2f}  {str(c.get('w') or '?')}×{str(c.get('h') or '?')} "
              f"{(str(round(c['dur'], 1)) + ' s') if c.get('dur') else '':<7} {str(c.get('size_mb') or '?')} MB  "
              f"{c['title'][:60]}" + (f"  ({c['notes']})" if c.get("notes") else ""))


# --- Commands -----------------------------------------------------------------------------------------------

def cmd_providers(a):
    o = context(a.edit)
    for name, p in PROVIDERS.items():
        ok, why = p.available()
        used = name in order(o)
        print(f"{name:<9} {'available' if ok else 'unavailable'}{'' if ok else ': ' + why}"
              f"{'' if used else ' (not used in this video: off in the settings or not in the list)'}")


def cmd_index(a):
    from PIL import Image, ImageDraw
    project = project_root()
    o = context(None)
    files = ProjectProvider().files({**o, "edit": None})
    if a.dir:
        files = [p for d in a.dir for p in (project / d).rglob("*") if p.suffix.lower() in VIDEO_EXT | IMAGE_EXT]
    idxf = project / "footage_index.json"
    sheet_dir = project / "_footage_index"
    sheet_dir.mkdir(exist_ok=True)
    T, rows, facts = 160, [], {}
    for n, p in enumerate(files):
        r = rel(p, project)
        info = probe(p) if p.suffix.lower() in VIDEO_EXT else {"w": None, "h": None, "dur": None}
        meta = {"w": info["w"], "h": info["h"], "dur": round(info["dur"], 2) if info.get("dur") else None,
                "size_mb": round(p.stat().st_size / 1e6, 1)}
        facts[r] = meta
        strip = Image.new("RGB", (T * 3, int(T * 16 / 9) + 18), (30, 30, 30))
        d = ImageDraw.Draw(strip)
        for k, frac in enumerate((0.15, 0.5, 0.85)):
            tmp = sheet_dir / "_f.jpg"
            try:
                if p.suffix.lower() in VIDEO_EXT:
                    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(info['dur'] or 1) * frac:.2f}", "-i", p, "-frames:v", "1",
                         "-vf", f"scale={T}:-2", tmp])
                    im = Image.open(tmp).convert("RGB")
                else:
                    im = Image.open(p).convert("RGB")
                im.thumbnail((T, int(T * 16 / 9)))
                strip.paste(im, (k * T, 0))
            except Exception:
                pass
        d.text((4, strip.height - 16), f"{n}: {r} {info.get('w')}x{info.get('h')} {meta['dur']}s", fill=(255, 255, 0))
        rows.append(strip)
    if (sheet_dir / "_f.jpg").exists():
        (sheet_dir / "_f.jpg").unlink()
    with editing_json(idxf, {}) as idx:  # descriptions written by a parallel describe are not lost
        for r, meta in facts.items():
            cur = idx.setdefault(r, {})
            cur.update(meta)
            cur.setdefault("description", "")
            cur.setdefault("tags", [])
            cur.setdefault("exclude", False)
    for page in range(0, len(rows), 6):
        chunk = rows[page:page + 6]
        sheet = Image.new("RGB", (chunk[0].width * 2, chunk[0].height * ((len(chunk) + 1) // 2)), (0, 0, 0))
        for k, im in enumerate(chunk):
            sheet.paste(im, ((k % 2) * im.width, (k // 2) * im.height))
        sheet.save(sheet_dir / f"sheet-{page // 6:02d}.jpg", quality=80)
    print(f"{idxf}: {len(files)} files; contact sheets: {sheet_dir}/sheet-*.jpg. Look at them and describe: "
          f"footage.py describe <path> \"what is in the frame\" [--tags ...] [--exclude]")


def cmd_describe(a):
    project = project_root()
    idxf = project / "footage_index.json"
    key = a.path.replace("\\", "/")
    with editing_json(idxf, {}) as idx:
        if key not in idx:
            sys.exit(f"not in the index: {key} (run footage.py index first)")
        idx[key]["description"] = a.text
        if a.tags:
            idx[key]["tags"] = [t.strip() for t in a.tags.split(",") if t.strip()]
        idx[key]["exclude"] = bool(a.exclude)
    print(f"{key}: {a.text}")


def cmd_search(a):
    o = context(a.edit, {})
    o["min_dur"] = a.min_dur
    names = a.providers.split(",") if a.providers else order(o)
    if not names:
        print("B-roll is off or there is no source: no insert needed, keep the main footage")
        return
    allc = []
    for n in names:
        res = safe_search(n, a.query, o)
        allc += res[:a.limit]
        print(f"{n}: {len(res)}")
        show(res, a.limit)
    if a.json:
        print(json.dumps(allc, ensure_ascii=False, indent=1))


def cmd_plan_search(a):
    from visual_plan import GEN_FIELDS, current_settings, load_plan
    o = context(a.edit)
    e = o["edit"]
    plan = load_plan(e)  # read only; the search (maybe online) runs outside the lock, writes go through put_insert
    s, _, _, o["brand_dir"], o["brand"] = current_settings(e, plan)  # reel.json is the only source of settings
    o["settings"] = s
    o["eff"], o["why"] = effective(s)
    names = order(o)
    for i in plan["inserts"]:
        if i["kind"] != "broll" or i["status"] not in ("planned",) or i.get("file"):
            continue
        q_local = " ".join(filter(None, [i.get("what"), i.get("query")]))  # project descriptions: in the person's language
        q_online = i.get("query") or i.get("what")                           # online sources search in English
        want = [i["source"]] if i["source"] in ("project", "local") else \
            [n for n in names if n not in ("project", "local")] if i["source"] == "online" else \
            [] if i["source"] == "generated" else names
        found, used = [], None
        for n in want:
            q = q_local if n in ("project", "local") else q_online
            res = [c for c in safe_search(n, q, {**o, "min_dur": i["dur"]}) if c["score"] >= a.min_score]
            if res:
                found, used = res[:a.limit], n
                break
        if found:
            i["candidates"], i["candidate"] = found, found[0]
            i["source"] = "online" if used not in ("project", "local") else used
            print(f"{i['id']}: {used}: {len(found)} candidates, best: {found[0]['title'][:60]} ({found[0]['score']})")
        elif i["source"] in ("auto", "generated") and (o["eff"].get("generated_code") or o["eff"].get("generated_prompts")):
            i["source"], i["status"] = "generated", "pending"
            i.setdefault("gen", {k: "" for k in GEN_FIELDS})
            i["fallback"] = "generated (codescene.py); main footage until there is a clip"
            print(f"{i['id']}: no ready footage -> generated (fill in gen, then codescene.py or addon.py gen)")
        else:
            i["status"] = "skipped"
            i["fallback"] = "no footage in any enabled source: main footage"
            print(f"{i['id']}: no footage, generation is off -> skipped (main footage)")
        put_insert(e, i, ("candidates", "candidate", "source", "status", "gen", "fallback"),
                   when=lambda cur: cur.get("status") == "planned" and not cur.get("file"))


def lut_chain(lut, strength):
    if not lut:
        return None
    s = max(0.0, min(1.0, strength))
    return f"split[a][b];[b][1:v]haldclut[l];[a][l]blend=all_mode=normal:all_opacity={s:.2f}" if s < 0.999 else "[0:v][1:v]haldclut"


class ShortSource(ValueError):
    """The source is too short for the insert: take other footage or a smaller --in."""


def prepare(src, out, dur, start=0.0, fit="cover", focus=(0.5, 0.5), speed=1.0, lut=None, lut_strength=0.7, grade=None):
    """Any video or photo source -> 1080×1920, 30 fps, yuv420p, no audio, exactly dur seconds.
    fit/focus/grade work for both video and photos. A video shorter than needed: a gap <= MAX_PAD_S is filled with a
    freeze of the last frame (with a warning), a larger one raises ShortSource; the result's length is checked after
    ffmpeg."""
    src, out = Path(src), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    is_img = src.suffix.lower() in IMAGE_EXT
    fx, fy = (max(0.0, min(1.0, float(v))) for v in focus)
    n = round(dur * 30)
    if is_img:
        # photo -> a clip with a slow push-in; cover: crop and push in towards focus, contain: the whole photo on a blurred background
        if fit == "cover":
            zp = f"zoompan=z='1+0.06*on/{n}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d={n}:s=1080x1920:fps=30"
            body = (f"[0:v]scale=1296:2304:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop=1296:2304:(iw-1296)*{fx}:(ih-2304)*{fy},{zp}")
        else:
            zp = f"zoompan=z='1+0.03*on/{n}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={n}:s=1080x1920:fps=30"
            body = (f"[0:v]format=rgba,split[f][g];[g]scale=1296:2304:force_original_aspect_ratio=increase,crop=1296:2304,"
                    f"boxblur=30:3,eq=brightness=-0.08[bg];[f]scale=1296:2304:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{zp}")
        inputs = ["-i", src]
    else:
        pad = 0.0
        src_dur = probe(src).get("dur")
        if src_dur:
            if start >= src_dur - 0.05:
                raise ShortSource(f"{src.name}: --in {start:.2f} s is past the end of the file ({src_dur:.2f} s)")
            avail = (src_dur - start) / speed
            if avail + 1 / 30 < dur:
                short = dur - avail
                if short > MAX_PAD_S:
                    raise ShortSource(f"{src.name}: from {start:.2f} s only {avail:.2f} s remain at speed {speed}, "
                                      f"but the insert is {dur} s: take other footage or a smaller --in")
                pad = short + 0.1
                warn(f"{src.name}: {short:.2f} s short; the tail is filled with a freeze of the last frame")
        pre = [f"setpts=(PTS-STARTPTS)/{speed}"] if speed != 1.0 else []
        tail = [f"tpad=stop_mode=clone:stop_duration={pad:.3f}"] if pad else []
        if fit == "cover":
            geom = (f"scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop=1080:1920:(iw-1080)*{fx}:(ih-1920)*{fy}")
            body = "[0:v]" + ",".join(pre + [geom, "fps=30"] + tail)
        else:
            fg = ",".join(pre + ["scale=1080:1920:force_original_aspect_ratio=decrease", "fps=30"] + tail)
            body = (f"[0:v]{fg},split[f][g];[g]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                    f"boxblur=30:3,eq=brightness=-0.08[bg];[bg][f]overlay=(W-w)/2:(H-h)/2")
        inputs = ["-ss", f"{start:.3f}", "-t", f"{dur * speed + 0.5:.3f}", "-i", src]
    filt = body + (f",{grade}" if grade else "") + ",setsar=1[v0]"
    if lut:
        lc = lut_chain(lut, lut_strength).replace("split[a][b]", "[v0]split[a][b]").replace("[0:v][1:v]haldclut", "[v0][1:v]haldclut")
        filt += ";" + lc + ",format=yuv420p[v]"
        inputs += ["-i", lut]
    else:
        filt += ";[v0]format=yuv420p[v]"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", filt, "-map", "[v]", "-an",
         "-frames:v", str(n), "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
         "-movflags", "+faststart", out])
    info = probe(out)
    if not info.get("dur") or info["dur"] + 0.05 < dur:
        out.unlink(missing_ok=True)
        raise ShortSource(f"{out.name}: {info.get('dur') or 0:.2f} s after preparing instead of {dur} s: "
                          f"take other footage or a smaller --in")
    return info


def resolve_lut(arg, brand, brand_dir, project):
    """--lut brand -> the HALD LUT from the video's brand profile; a path -> that file. No LUT: a warning and no grading."""
    if not arg:
        return None
    if arg == "brand":
        hald = ((brand or {}).get("lut") or {}).get("hald")
        f = brand_file(hald, brand_dir, project) if hald else None
        if not f:
            warn("--lut brand: the video's brand has no HALD LUT (brand.json -> lut.hald); no color grading")
        return str(f) if f else None
    if not Path(arg).is_file():
        warn(f"--lut: no file {arg}; no color grading")
        return None
    return arg


def edit_for_out(out):
    """The video's folder from the --out path (edit/<id>/inserts/b01.mp4), for --lut brand without --edit."""
    for q in Path(out).resolve().parents:
        if (q / "reel.json").is_file() or (q / "visual_plan.json").is_file():
            return q
    return None


def cmd_prepare(a):
    focus = tuple(float(x) for x in a.focus.split(","))
    lut = a.lut
    if a.lut == "brand":
        e = edit_dir(a.edit) if a.edit else edit_for_out(a.out)
        if not e:
            warn("--lut brand: could not tell which video this is (no reel.json near --out); pass --edit edit/<id>")
        _, _, _, bdir, brand = load_config(e)
        lut = resolve_lut("brand", brand, bdir, project_root())
    elif a.lut:
        lut = resolve_lut(a.lut, None, None, None)
    try:
        info = prepare(a.src, a.out, a.dur, a.start, a.fit, focus, a.speed, lut, a.lut_strength, a.grade)
    except ShortSource as ex:
        sys.exit(f"✗ {ex}")
    print(f"{a.out}: {info['w']}×{info['h']}, {info['dur']:.2f} s")


def save_credit(e, credit, insert=None):
    """inserts/credits.json: one entry per insert (a repeated pick/prepare replaces the previous one); under the lock.
    credit=None: remove the entry of insert `insert` (it was replaced with own footage)."""
    f = e / "inserts" / "credits.json"
    iid = credit.get("insert") if credit else insert
    if not credit and not f.exists():
        return
    with editing_json(f, []) as credits:
        credits[:] = [c for c in (credits or []) if c.get("insert") != iid] + ([credit] if credit else [])


def cmd_pick(a):
    from visual_plan import load_plan
    o = context(a.edit)
    e = o["edit"]
    plan = load_plan(e)  # read only; download and ffmpeg run outside the lock, writes go through put_insert
    i = next((x for x in plan["inserts"] if x["id"] == a.insert), None)
    if not i:
        sys.exit(f"no insert {a.insert}")
    cands = i.get("candidates") or ([i["candidate"]] if i.get("candidate") else [])
    if not cands:
        sys.exit(f"{a.insert}: no candidates (footage.py plan-search)")
    if not 0 <= a.candidate < len(cands):
        sys.exit(f"{a.insert}: no candidate [{a.candidate}] (there are 0-{len(cands) - 1})")
    c = cands[a.candidate]
    p = PROVIDERS.get(c.get("provider"))
    if not p:
        sys.exit(f"{a.insert}: unknown source {c.get('provider')} (an online source needs the online add-on linked to "
                 f"this project)")
    if p.online:
        ok, why = p.available()  # offline mode and access are checked right before the network, not only at search time
        if not ok:
            i["status"], i["fallback"] = "skipped", f"cannot download now ({why}): main footage"
            put_insert(e, i, ("status", "fallback"))
            warn(f"{a.insert}: {i['fallback']}")
            return
        if not a.yes:
            sys.exit(f"{a.insert}: download {c['provider']} {c['id']} ({c.get('size_mb') or '?'} MB, {c.get('page_url')}): "
                     f"only after the person approves the visual plan; repeat with --yes")
    try:
        raw = p.fetch(c, e / "inserts" / "raw")
    except Exception as ex:
        i["status"], i["fallback"] = "skipped", f"download failed ({err_text(ex, 120)}): main footage"
        put_insert(e, i, ("status", "fallback"))
        warn(f"{a.insert}: {i['fallback']}")
        return
    lut = resolve_lut(a.lut, o.get("brand"), o.get("brand_dir"), o["project"])
    out = e / "inserts" / f"{i['id']}.mp4"
    focus = tuple(float(x) for x in a.focus.split(","))
    try:
        prepare(raw, out, i["dur"], a.start, a.fit, focus, a.speed, lut, a.lut_strength)
    except ShortSource as ex:
        i["status"], i["fallback"] = "skipped", f"{ex}; main footage for now"
        i.pop("file", None)
        put_insert(e, i, ("status", "fallback", "file"))
        warn(f"{a.insert}: {i['fallback']}")
        return
    i.update({"candidate": c, "file": rel(out, e), "src_in": 0.0, "status": "ready",
              "credit": {"provider": c["provider"], "id": c["id"], "author": c.get("author"), "page_url": c.get("page_url"),
                         "license": c.get("license")}})
    save_credit(e, i["credit"] | {"insert": i["id"], "file": rel(raw, e)} if p.online else None, insert=i["id"])
    put_insert(e, i, ("candidate", "file", "src_in", "status", "credit"))
    print(f"{a.insert}: ready -> {out} ({c['provider']} {c['id']})")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("providers"); p.add_argument("--edit"); p.set_defaults(fn=cmd_providers)
    p = sub.add_parser("index"); p.add_argument("--dir", nargs="*"); p.set_defaults(fn=cmd_index)
    p = sub.add_parser("describe"); p.add_argument("path"); p.add_argument("text"); p.add_argument("--tags")
    p.add_argument("--exclude", action="store_true"); p.set_defaults(fn=cmd_describe)
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--edit"); p.add_argument("--providers")
    p.add_argument("--limit", type=int, default=6); p.add_argument("--min-dur", type=float, default=0)
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_search)
    p = sub.add_parser("plan-search"); p.add_argument("edit"); p.add_argument("--limit", type=int, default=5)
    p.add_argument("--min-score", type=float, default=0.5); p.set_defaults(fn=cmd_plan_search)
    p = sub.add_parser("pick"); p.add_argument("edit"); p.add_argument("insert"); p.add_argument("--candidate", type=int, default=0)
    p.add_argument("--start", "--in", dest="start", type=float, default=0.0); p.add_argument("--fit", default="cover", choices=["cover", "contain"])
    p.add_argument("--focus", default="0.5,0.5"); p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--lut"); p.add_argument("--lut-strength", type=float, default=0.7); p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_pick)
    p = sub.add_parser("prepare"); p.add_argument("src"); p.add_argument("--out", required=True)
    p.add_argument("--dur", type=float, required=True); p.add_argument("--start", "--in", dest="start", type=float, default=0.0)
    p.add_argument("--fit", default="cover", choices=["cover", "contain"]); p.add_argument("--focus", default="0.5,0.5")
    p.add_argument("--speed", type=float, default=1.0); p.add_argument("--lut"); p.add_argument("--lut-strength", type=float, default=0.7)
    p.add_argument("--grade"); p.add_argument("--edit", help="the video for --lut brand (otherwise found from the --out path)")
    p.set_defaults(fn=cmd_prepare)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
