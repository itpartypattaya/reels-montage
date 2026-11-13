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
    python scripts/footage.py plan-search edit/<id> [--retry] [--insert b01 --query "pool view"]   # candidates for every B-roll insert, by source priority
    python scripts/footage.py pick edit/<id> b01 [--candidate 0] [--in 2.0] [--lut brand] [--no-look] [--yes]   # fetch/take + prepare -> ready
    python scripts/footage.py prepare <file> --out edit/<id>/inserts/b01.mp4 --dur 1.6 [--in 2.0] [--fit cover|contain]
                       [--focus 0.5,0.4] [--speed 0.8] [--lut brand|<hald.png> --lut-strength 0.7] [--edit edit/<id>]
                       [--look edit/<id>] [--grade <chain applied before the LUT>]

Color. A video from the project's own footage (the same shoot) gets the rough cut's look from cut.json, exactly as
cut.py applies it: look.correct (balance) -> the LUT at lut_mix -> look.grade (pick does it by itself; prepare with
--look edit/<id>; pick --no-look turns it off). Otherwise the cutaway differs in color from the cut around it. A
cutaway cut.py made with "extract" in cut.json (edit/<id>/<name>.mp4) is already in that color: it is project footage
too (found by search and plan-search, described by the extract's "what" or footage.py describe), and pick takes it as
it is, without a second look (T5: the look applied twice turned a white wall pink). Other footage (a library, online,
photos): --lut brand|<hald.png> at --lut-strength; --grade is a filter chain BEFORE that LUT (a correction, like
look.correct), not after it.

Search scores the share of the query's words found in a file's name, description and tags. plan-search scores each
B-roll insert by its "query" (its "what" when there is no query, or when the query finds nothing), with the same
scoring as search, and keeps candidates at --min-score 0.5 or more. An insert with no candidate is marked skipped
(the main footage stays) with the way back: describe the footage, then plan-search --retry, or try other words with
plan-search --insert b01 --query "...".

index of the whole project writes the shared contact sheets _footage_index/sheet-NN.jpg; index --dir writes sheets
named after those folders (_footage_index/<folder>-sheet-NN.jpg) and leaves the shared ones alone. describe takes a
file the index does not know yet (an extract, a new file): it adds it to footage_index.json first.

Online sources and their terms are described by the add-on. A download from an online source happens only after the
person approves the visual plan (the plan lists the source and the file size): `pick --yes`.
"""
import argparse, json, os, re, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (IMAGE_EXT, PHOTO_EXT, VIDEO_EXT, UnreadablePhoto, brand_file, edit_dir, editing_json, effective, library_dirs, load_config,
                          load_json, online, photo_input, probe, project_root, rel, run, save_json, score,
                          photo_file, upright_image, upright_size, utf8_stdio, warn)
from cut import extract_path, load_cut, look_chain, lut_inputs
from pic_track import MOVES  # a picture shot's own motion (cut.json picture)
import photo_move  # noqa: E402  the path of a photo shot with an ROI (cut.json picture shots -> roi)

NO_FOOTAGE = "no footage in any enabled source"  # plan-search's skip reason: --retry looks for these again
MAX_PAD_S = 0.5  # how much a short source may be stretched with a freeze frame (tpad clone); more -> other footage
EXCLUDE_DIRS = {"edit", "node_modules", "out", "_catalog", ".git", "plans", "memes"}


def err_text(ex, limit=160):
    """An error for output and JSON: type + text. With the online add-on loaded, its own filter cleans the text first (a
    source's error may quote its request), then the text is cut."""
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


def _key(p):
    return os.path.normcase(str(Path(p).resolve()))


def cut_extracts(e):
    """{path: (file, entry)} of the cutaways cut.py made from cut.json "extract" (edit/<id>/<name>.mp4) that
    exist. They come from the video's own source on purpose, already in the rough cut's look: valid project footage
    that needs no second look."""
    out = {}
    if not e:
        return out
    for name, x in ((load_json(Path(e) / "cut.json", {}) or {}).get("extract") or {}).items():
        try:
            p = extract_path(Path(e), name)
        except SystemExit:  # an unsafe name: cut.py refuses it too
            continue
        if p.is_file():
            out[_key(p)] = (p, {"name": name, **(x if isinstance(x, dict) else {})})
    return out


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
    folders + the video's cutaways cut.py made ("extract" in cut.json; older edit/<id>/broll* files too). Photos only
    from footage_dirs on purpose: the project folder also holds covers, screenshots and exported frames, which must
    not turn into B-roll. The video's own source files are left out (the cut already shows them) - except an extract,
    made from the source on purpose. Descriptions live in footage_index.json; an extract's "what" in cut.json counts as
    its description."""
    name = "project"

    def files(self, o):
        root = o["project"]
        out = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT]
        for d in o["settings"].get("footage_dirs", []):
            dd = root / d
            if dd.is_dir():
                out += [p for p in dd.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT | PHOTO_EXT]
        extras = cut_extracts(o.get("edit"))
        if o.get("edit"):
            out += [p for p in o["edit"].glob("broll*") if p.suffix.lower() in VIDEO_EXT]
        main = set()
        edl = load_json(o["edit"] / "edl.json", {}) if o.get("edit") else {}
        for v in list((edl.get("sources") or {}).values()) + list((edl.get("picture_sources") or {}).values()):
            main.add(Path(v).name.lower())
        # finished renders (<brand>-<slug>-YYYY-MM-DD[-master].mp4) are not sources
        render = re.compile(r"\d{4}-\d{2}-\d{2}(-master)?\.mp4$", re.I)
        keep = [p for p in out if p.name.lower() not in main and not render.search(p.name)]
        seen = {_key(p) for p in keep}
        return keep + [p for k, (p, _) in extras.items() if k not in seen]

    def search(self, query, o):
        idx = load_json(o["project"] / "footage_index.json", {})
        extras = cut_extracts(o.get("edit"))
        res = []
        for p in self.files(o):
            r = rel(p, o["project"])
            meta = idx.get(r, {})
            if meta.get("exclude"):
                continue
            x = (extras.get(_key(p)) or (None, None))[1]
            desc = meta.get("description") or (x or {}).get("what") or ""
            text = " ".join([p.stem, desc, " ".join(meta.get("tags", []))])
            sc = score(query, text)
            note = "" if desc else ("no description: footage.py describe, or \"what\" in the cut.json extract" if x
                                    else "no description: look at the contact sheet (footage.py index)")
            if x:
                note = "; ".join(filter(None, ["cut.py extract of this video, already in the rough cut's color", note]))
            if sc > 0 or not desc:
                res.append(cand(provider=self.name, id=r, title=desc or p.name, path=str(p),
                                w=meta.get("w"), h=meta.get("h"), dur=meta.get("dur"),
                                size_mb=round(p.stat().st_size / 1e6, 1), license="own footage", score=sc, notes=note,
                                **({"graded": True} if x else {})))
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
    """Write the listed fields of insert i into the plan under the lock, re-reading the plan (parallel runs):
    other runs' changes to other inserts and fields are not lost. Downloads, ffmpeg and generation run before
    the call, not under the lock. when(cur) -> False: the insert was changed in another run, don't overwrite it.
    A field missing from i deletes the field."""
    from visual_plan import editing_plan
    with editing_plan(e) as plan:
        cur = next((x for x in plan["inserts"] if x["id"] == i["id"]), None)
        if cur is None:
            warn(f"{i['id']}: the insert is no longer in the plan (deleted by another run); result not written")
            return False
        if when and not when(cur):
            warn(f"{i['id']}: the insert was changed by another run while this ran; not overwriting it")
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


def readable_photo(src):
    """The file ffmpeg reads for this source: a HEIC's upright JPEG (reels_common.photo_file), or a stop that names
    the photo and the way out when this ffmpeg cannot read it."""
    try:
        return photo_file(src)
    except UnreadablePhoto as ex:
        sys.exit(str(ex))


def photo_facts(p):
    """A photo's upright size (the EXIF orientation applied) for footage_index.json; no duration. A HEIC this ffmpeg
    cannot read: a warning, no size."""
    try:
        w, h = upright_size(p)
    except UnreadablePhoto as ex:
        warn(str(ex))
        w = h = None
    except Exception:
        w = h = None
    return {"w": w, "h": h, "dur": None}


def file_facts(p, info=None):
    """Size, duration and frame size of a file for footage_index.json (a photo upright)."""
    info = info or (probe(p) if p.suffix.lower() in VIDEO_EXT else photo_facts(p))
    return {"w": info.get("w"), "h": info.get("h"), "dur": round(info["dur"], 2) if info.get("dur") else None,
            "size_mb": round(p.stat().st_size / 1e6, 1)}


def sheet_prefix(dirs):
    """The contact sheets' name prefix: "" for the whole project (the shared sheet-NN.jpg), the folder names for
    index --dir, so indexing one folder never overwrites the shared sheets (T5: index --dir edit/<id> did)."""
    if not dirs:
        return ""
    return "-".join(re.sub(r"[^\w.]+", "-", str(d).strip("/\\")).strip("-.") or "dir" for d in dirs)[:80] + "-"


def cmd_index(a):
    from PIL import Image, ImageDraw
    project = project_root()
    o = context(None)
    files = ProjectProvider().files({**o, "edit": None})
    if a.dir:
        files = [p for d in a.dir for p in (project / d).rglob("*") if p.suffix.lower() in VIDEO_EXT | PHOTO_EXT]
    idxf = project / "footage_index.json"
    sheet_dir = project / "_footage_index"
    sheet_dir.mkdir(exist_ok=True)
    prefix = sheet_prefix(a.dir)
    tmp = sheet_dir / f"_f-{os.getpid()}.jpg"  # parallel runs don't share the frame file
    T, rows, facts = 160, [], {}
    for n, p in enumerate(files):
        r = rel(p, project)
        info = probe(p) if p.suffix.lower() in VIDEO_EXT else photo_facts(p)
        meta = file_facts(p, info)
        facts[r] = meta
        strip = Image.new("RGB", (T * 3, int(T * 16 / 9) + 18), (30, 30, 30))
        d = ImageDraw.Draw(strip)
        for k, frac in enumerate((0.15, 0.5, 0.85)):
            try:
                if p.suffix.lower() in VIDEO_EXT:
                    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(info['dur'] or 1) * frac:.2f}", "-i", p, "-frames:v", "1",
                         "-vf", f"scale={T}:-2", tmp])
                    im = Image.open(tmp).convert("RGB")
                else:
                    im = upright_image(p).convert("RGB")  # as the phone shows it and as prepare() uses it
                im.thumbnail((T, int(T * 16 / 9)))
                strip.paste(im, (k * T, 0))
            except Exception:
                pass
        d.text((4, strip.height - 16), f"{n}: {r} {info.get('w')}x{info.get('h')} {meta['dur']}s", fill=(255, 255, 0))
        rows.append(strip)
    tmp.unlink(missing_ok=True)
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
        sheet.save(sheet_dir / f"{prefix}sheet-{page // 6:02d}.jpg", quality=80)
    print(f"{idxf}: {len(files)} files; contact sheets: {sheet_dir}/{prefix}sheet-*.jpg. Look at them and describe: "
          f"footage.py describe <path> \"what is in the frame\" [--tags ...] [--exclude]")


def cmd_describe(a):
    project = project_root()
    idxf = project / "footage_index.json"
    ref_id = a.path.replace("\\", "/")
    f = next((q for q in (project / ref_id, Path(a.path)) if q.is_file()), None)
    if f is not None and rel(f, project) != str(f):
        ref_id = rel(f, project)  # the index entries are named by paths from the project folder
    with editing_json(idxf, {}) as idx:
        if ref_id not in idx:
            if f is None or f.suffix.lower() not in VIDEO_EXT | PHOTO_EXT:
                sys.exit(f"not in the index and no such video or photo in the project: {ref_id} (footage.py index)")
            idx[ref_id] = {**file_facts(f), "description": "", "tags": [], "exclude": False}  # a new file, an extract
        idx[ref_id]["description"] = a.text
        if a.tags:
            idx[ref_id]["tags"] = [t.strip() for t in a.tags.split(",") if t.strip()]
        idx[ref_id]["exclude"] = bool(a.exclude)
    print(f"{ref_id}: {a.text}")


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
    if a.query and len(a.insert or []) != 1:
        sys.exit("--query needs one --insert ID: the new words are for one insert")
    ids = set(a.insert or [])
    unknown = ids - {i["id"] for i in plan["inserts"]}
    if unknown:
        sys.exit(f"no insert {', '.join(sorted(unknown))} in the plan")

    def wanted(i):
        """A B-roll insert without a file that is still planned; with --retry (or named with --insert) also one this
        command skipped earlier for lack of footage."""
        if i["kind"] != "broll" or i.get("file") or (ids and i["id"] not in ids):
            return False
        return i["status"] == "planned" or (i["status"] == "skipped" and (a.retry or ids)
                                            and str(i.get("fallback", "")).startswith(NO_FOOTAGE))

    for i in plan["inserts"]:
        if not wanted(i):
            continue
        was = i["status"]
        if a.query:
            i["query"] = a.query
        src = i["source"]
        want = [src] if src in ("project", "local") else \
            [n for n in names if n not in ("project", "local")] if src == "online" else \
            [] if src == "generated" else names
        # the same scoring as `search`: the share of the QUERY's words found (T5: the long "what" + "query" diluted the
        # share, a file found by search at 0.50 fell under --min-score and the insert was skipped); "what" is the
        # fallback when there is no query or the query finds nothing
        queries = [q for q in dict.fromkeys([i.get("query"), i.get("what")]) if q and str(q).strip()]
        found, used, near = [], None, []
        for n in want:
            for q in queries:
                res = safe_search(n, q, {**o, "min_dur": i["dur"]})
                near += [c for c in res if 0 < c["score"] < a.min_score]
                res = [c for c in res if c["score"] >= a.min_score]
                if res:
                    found, used = res[:a.limit], n
                    break
            if found:
                break
        if found:
            i["candidates"], i["candidate"] = found, found[0]
            i["source"] = "online" if used not in ("project", "local") else used
            i["status"], i["fallback"] = "planned", i.get("fallback") if was == "planned" else "main footage"
            print(f"{i['id']}: {used}: {len(found)} candidates, best: {found[0]['title'][:60]} ({found[0]['score']})")
        elif src in ("auto", "generated") and (o["eff"].get("generated_code") or o["eff"].get("generated_prompts")):
            i["source"], i["status"] = "generated", "pending"
            i.setdefault("gen", {k: "" for k in GEN_FIELDS})
            i["fallback"] = "generated (codescene.py); main footage until there is a clip"
            print(f"{i['id']}: no ready footage -> generated (fill in gen, then codescene.py or addon.py gen)")
        else:
            i["status"] = "skipped"
            i["fallback"] = f"{NO_FOOTAGE}: main footage"
            best = max(near, key=lambda c: c["score"], default=None)
            print(f"{i['id']}: no footage at --min-score {a.min_score} for "
                  f"{' / '.join(repr(q) for q in queries) or 'an empty query'}, generation is off -> skipped (main "
                  f"footage)" + (f"; the closest: {best['title'][:50]} ({best['score']})" if best else ""))
            print(f"  to try again: describe the footage (footage.py describe <file> \"...\", or \"what\" in a cut.json "
                  f"extract), then footage.py plan-search {a.edit} --retry; other words: footage.py plan-search "
                  f"{a.edit} --insert {i['id']} --query \"...\"")
        put_insert(e, i, ("candidates", "candidate", "source", "status", "gen", "fallback", "query"),
                   when=lambda cur, was=was: cur.get("status") == was and not cur.get("file"))


def lut_chain(lut, strength):
    if not lut:
        return None
    s = max(0.0, min(1.0, strength))
    return f"split[a][b];[b][1:v]haldclut[l];[a][l]blend=all_mode=normal:all_opacity={s:.2f}" if s < 0.999 else "[0:v][1:v]haldclut"


class ShortSource(ValueError):
    """The source is too short for the insert: take other footage or a smaller --in."""


MOVE_Z = photo_move.MOVE_Z  # how far a push, a pull or a pan zooms over the shot (one number for both modules)


def move_zoompan(move, n, w, h, fps, fx, fy):
    """zoompan for a picture shot's own motion over n frames (d=1 per input frame of a video, d=n for a photo is
    given by the caller): push 1 -> 1+MOVE_Z towards the focus, pull back, pan from left to right at 1+MOVE_Z; None
    for "none" and "still" (the frame stands)."""
    if move in ("none", "still", None):
        return None
    last = max(1, n - 1)
    if move == "push":
        z, x, y = f"1+{MOVE_Z}*on/{last}", f"(iw-iw/zoom)*{fx}", f"(ih-ih/zoom)*{fy}"
    elif move == "pull":
        z, x, y = f"1+{MOVE_Z}-{MOVE_Z}*on/{last}", f"(iw-iw/zoom)*{fx}", f"(ih-ih/zoom)*{fy}"
    else:  # pan
        z, x, y = f"{1 + MOVE_Z}", f"(iw-iw/zoom)*on/{last}", f"(ih-ih/zoom)*{fy}"
    return f"zoompan=z='{z}':x='{x}':y='{y}':s={w}x{h}:fps={fps}"


def prepare(src, out, dur, start=0.0, fit="cover", focus=(0.5, 0.5), speed=1.0, lut=None, lut_strength=0.7, grade=None,
            look=None, strict=False, size=(1080, 1920), fps=30, move=None, roi=None):
    """Any video or photo source -> 1080×1920, 30 fps, yuv420p, no audio, exactly dur seconds.
    fit/focus/grade work for both video and photos (grade: before the LUT). look: the rough cut's look (cut.py
    load_cut: correct, lut, lut_mix, grade), applied by cut.py's own look_chain; it replaces lut/lut_strength.
    A video shorter than needed: a gap <= MAX_PAD_S is filled with a freeze of the last frame (with a warning), a
    larger one raises ShortSource; the result's length is checked after ffmpeg.
    strict (a picture shot of cut.json, cut_picture.py): no freeze at all (any shortfall raises ShortSource), the
    video's own size and fps, and the motion is the shot's move (MOVES): none/still keep the frame standing, a photo
    included; push, pull and pan move it. Without strict (B-roll) everything stays as above: a photo always pushes in.
    roi (strict, a photo, cover): the shot's subject, [x0, y0, x1, y1] of the upright photo: the move follows
    photo_move.plan(). A photo is always taken upright by its EXIF tag (reels_common.photo_input)."""
    if strict:
        return prepare_shot(src, out, dur, start, fit, focus, speed, look, size, fps, move or "none", roi)
    src, out = Path(src), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    src = readable_photo(src)
    is_img = src.suffix.lower() in IMAGE_EXT
    fx, fy = (max(0.0, min(1.0, float(v))) for v in focus)
    n = round(dur * 30)
    if is_img:
        # photo -> a clip with a slow push-in; cover: crop and push in towards focus, contain: the whole photo on a blurred background
        pre_in, turn = photo_input(src)  # upright by its EXIF tag whatever ffmpeg itself does with it
        head0 = f"[0:v]{turn}," if turn else "[0:v]"
        if fit == "cover":
            zp = f"zoompan=z='1+0.06*on/{n}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d={n}:s=1080x1920:fps=30"
            body = (f"{head0}scale=1296:2304:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop=1296:2304:(iw-1296)*{fx}:(ih-2304)*{fy},{zp}")
        else:
            zp = f"zoompan=z='1+0.03*on/{n}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={n}:s=1080x1920:fps=30"
            body = (f"{head0}format=rgba,split[f][g];[g]scale=1296:2304:force_original_aspect_ratio=increase,crop=1296:2304,"
                    f"boxblur=30:3,eq=brightness=-0.08[bg];[f]scale=1296:2304:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{zp}")
        inputs = [*pre_in, "-i", src]
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
    head = body + (f",{grade}" if grade else "")
    if look:  # the same look as the rough cut: cut.py's chain, the HALD image on input 1
        filt = look_chain(look, head, "v")
        inputs += lut_inputs(look)
    elif lut:
        lc = lut_chain(lut, lut_strength).replace("split[a][b]", "[v0]split[a][b]").replace("[0:v][1:v]haldclut", "[v0][1:v]haldclut")
        filt = head + ",setsar=1[v0];" + lc + ",format=yuv420p[v]"
        inputs += ["-i", lut]
    else:
        filt = head + ",setsar=1[v0];[v0]format=yuv420p[v]"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", filt, "-map", "[v]", "-an",
         "-frames:v", str(n), "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
         "-movflags", "+faststart", out])
    info = probe(out)
    if not info.get("dur") or info["dur"] + 0.05 < dur:
        out.unlink(missing_ok=True)
        raise ShortSource(f"{out.name}: {info.get('dur') or 0:.2f} s after preparing instead of {dur} s: "
                          f"take other footage or a smaller --in")
    return info


def usable(src_dur, start, speed):
    """Seconds of the finished video a clip gives from start at this speed."""
    return max(0.0, (float(src_dur) - start) / speed)


def prepare_shot(src, out, dur, start=0.0, fit="cover", focus=(0.5, 0.5), speed=1.0, look=None, size=(1080, 1920),
                 fps=30, move="none", roi=None):
    """prepare(strict=True): one picture shot of cut.json at the video's size and fps, exactly round(dur * fps) frames,
    no freeze frame, the shot's own move (MOVES). The color is the look of the shot's place (cut.py look_chain)."""
    src, out = Path(src), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if move not in MOVES:
        raise ValueError(f"move {move!r}: one of {', '.join(MOVES)}")
    w, h = (int(v) for v in size)
    n = round(dur * fps)
    fx, fy = (max(0.0, min(1.0, float(v))) for v in focus)
    src = readable_photo(src)
    is_img = src.suffix.lower() in IMAGE_EXT
    zp = move_zoompan(move, n, w, h, fps, fx, fy)
    # a moving frame is cut from a larger one, so the push-in never upscales its last frame
    bw, bh = (2 * round(w * 0.6), 2 * round(h * 0.6)) if zp else (w, h)

    def framing(head):
        if fit == "cover":
            return (f"{head}scale={bw}:{bh}:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop={bw}:{bh}:(iw-{bw})*{fx}:(ih-{bh})*{fy}")
        fg = f"scale={bw}:{bh}:force_original_aspect_ratio=decrease:flags=lanczos"
        if is_img:  # a small photo is not blown up past MAX_UP of its own size: smaller, sharp, on the blurred field
            pw, ph = upright_size(src)
            cap = photo_move.MAX_UP * bw / w  # MAX_UP on the screen = this many px of the working frame per photo px
            if min(bw / pw, bh / ph) > cap:
                fg = f"scale={2 * round(pw * cap / 2)}:{2 * round(ph * cap / 2)}:flags=lanczos"
        return (f"{head}split[f][g];[g]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
                f"boxblur=30:3,eq=brightness=-0.08[bg];[f]{fg}[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")

    path = photo_move.plan(upright_size(src), (w, h), n, move, roi, fit) if is_img and roi is not None else None
    if is_img:
        pre_in, turn = photo_input(src)  # upright by its EXIF tag whatever ffmpeg itself does with it
        inputs = [*pre_in, "-loop", "1", "-framerate", str(fps), "-t", f"{(n + 1) / fps:.4f}", "-i", src]
        if path is not None:
            body = roi_body(path, turn, w, h, fps)
        else:
            body = framing(f"[0:v]{turn},format=rgb24," if turn else "[0:v]format=rgb24,")
            body += f",fps={fps}" + (f",{zp.replace('zoompan=', 'zoompan=d=1:', 1)}" if zp else "")
    else:
        info = probe(src)
        src_dur = info.get("dur")
        if not src_dur or info.get("w") is None:
            raise ShortSource(f"{src.name}: no picture in the file")
        have = usable(src_dur, start, speed)
        if have + 0.5 / fps < dur:
            raise ShortSource(f"{src.name}: the shot needs {dur:.2f} s from {start:.2f} s at speed {speed:g}, the file "
                              f"has {have:.2f} s usable (it is {src_dur:.2f} s long): take a shorter shot, an earlier "
                              f"start or another clip (no freeze frame and no repeat is added)")
        pre = f"setpts=(PTS-STARTPTS)/{speed}," if speed != 1.0 else ""
        body = framing(f"[0:v]{pre}fps={fps},")
        if zp:
            body += "," + zp.replace("zoompan=", "zoompan=d=1:", 1)
        inputs = ["-ss", f"{start:.3f}", "-t", f"{dur * speed + 0.5:.3f}", "-i", src]
    if look:
        filt = look_chain(look, body, "v")
        inputs += lut_inputs(look)
    else:
        filt = body + ",setsar=1,format=yuv420p[v]"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", filt, "-map", "[v]", "-an", "-frames:v", str(n),
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-movflags", "+faststart", out])
    info = probe(out)
    if not info.get("dur") or info["dur"] + 0.5 / fps < dur:
        out.unlink(missing_ok=True)
        raise ShortSource(f"{out.name}: {info.get('dur') or 0:.2f} s after preparing instead of {dur:.2f} s: take "
                          f"another clip or a shorter shot")
    return info


def roi_body(p, turn, w, h, fps):
    """The filter chain of a photo shot that follows its ROI's path (photo_move.plan): the upright photo cut to the part
    the path crosses, enlarged so a window is 2w wide (half-pixel steps, no shake), then a zoom (zoompan: a straight
    line from the first window to the last) or a pan (a moving crop), down to w x h."""
    import math
    sw, sh = p["size"]
    (ax, ay, aw, ah), (bx, by, bw, bh) = p["start"], p["end"]
    last = max(1, p["n"] - 1)
    up = f"[0:v]{turn + ',' if turn else ''}format=rgb24"
    if p["kind"] == "pan":  # equal windows: the part both cross, enlarged, and a crop that moves across it
        ux0, uy0 = max(0, math.floor(min(ax, bx))), max(0, math.floor(min(ay, by)))
        ux1, uy1 = min(sw, math.ceil(max(ax + aw, bx + bw))), min(sh, math.ceil(max(ay + ah, by + bh)))
        k = 2 * w / aw
        ew, eh = 2 * round((ux1 - ux0) * k / 2), 2 * round((uy1 - uy0) * k / 2)
        kx, ky = ew / (ux1 - ux0), eh / (uy1 - uy0)  # the scale actually applied (the size is rounded to even)
        x = f"{(ax - ux0) * kx:.4f}+{(bx - ax) * kx:.4f}*n/{last}"
        y = f"{(ay - uy0) * ky:.4f}+{(by - ay) * ky:.4f}*n/{last}"
        return (f"{up},crop={ux1 - ux0}:{uy1 - uy0}:{ux0}:{uy0},scale={ew}:{eh}:flags=lanczos,fps={fps},"
                f"crop={2 * w}:{2 * h}:x='min({ew - 2 * w},max(0,{x}))':y='min({eh - 2 * h},max(0,{y}))',"
                f"scale={w}:{h}:flags=lanczos")
    gx, gy, gw, gh = p["start"] if aw >= bw else p["end"]  # the larger window holds the whole path
    # whole pixels around the window, never inside it: a rounded crop could shave the ROI's edge (review of phase 3)
    cx0, cy0 = max(0, math.floor(gx + 1e-6)), max(0, math.floor(gy + 1e-6))
    cx1, cy1 = min(sw, math.ceil(gx + gw - 1e-6)), min(sh, math.ceil(gy + gh - 1e-6))
    crop = f"crop={cx1 - cx0}:{cy1 - cy0}:{cx0}:{cy0}"
    if p["kind"] == "still":
        return f"{up},{crop},scale={w}:{h}:flags=lanczos,fps={fps}"
    sx, sy = 2 * w / (cx1 - cx0), 2 * h / (cy1 - cy0)  # enlarged px per photo px
    wexp = f"({aw * sx:.4f}+{(bw - aw) * sx:.4f}*on/{last})"  # the window's width in the enlarged part
    x = f"{(ax - cx0) * sx:.4f}+{(bx - ax) * sx:.4f}*on/{last}"
    y = f"{(ay - cy0) * sy:.4f}+{(by - ay) * sy:.4f}*on/{last}"
    return (f"{up},{crop},scale={2 * w}:{2 * h}:flags=lanczos,fps={fps},"
            f"zoompan=d=1:z='{2 * w}/{wexp}':x='{x}':y='{y}':s={w}x{h}:fps={fps}")


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


def rough_cut_look(e, strict=True):
    """The rough cut's look from cut.json (cut.py load_cut), or None when there is no cut list or no look. strict=False
    (pick, where the look is automatic): a cut.json that no longer loads (review: its source moved or archived after the
    rough cut) is a warning and no look, not the end of the pick."""
    if not e or not (e / "cut.json").is_file():
        return None
    try:
        c = load_cut(e, project_root())
    except SystemExit as ex:
        if strict:
            raise
        warn(f"{ex}: the rough cut's look (correct, LUT, grade) is not applied to this clip; restore the source or "
             f"grade the clip yourself (--no-look)")
        return None
    return c if (c["correct"] or c["lut"] or c["grade"]) else None


def look_text(c):
    return ", ".join(filter(None, [f"correct {c['correct']}" if c["correct"] else "",
                                   f"LUT {Path(c['lut']).name} at {round(c['lut_mix'] * 100)}%" if c["lut"] else "",
                                   f"grade {c['grade']}" if c["grade"] else ""]))


def cmd_prepare(a):
    focus = tuple(float(x) for x in a.focus.split(","))
    lut = a.lut
    look = None
    if a.look:
        if a.lut:
            sys.exit("--look takes the LUT from cut.json: drop --lut")
        le = edit_dir(a.look)
        look = rough_cut_look(le)
        if look and _key(a.src) in cut_extracts(le):
            look = None
            print(f"{Path(a.src).name}: a cut.py extract of {a.look}, already in the rough cut's color: no second look")
        elif not look:
            warn(f"--look {a.look}: no cut.json or no look in it; no color grading")
        else:
            print(f"look as the rough cut: {look_text(look)}")
    elif a.lut == "brand":
        e = edit_dir(a.edit) if a.edit else edit_for_out(a.out)
        if not e:
            warn("--lut brand: could not tell which video this is (no reel.json near --out); give --edit edit/<id>")
        _, _, _, bdir, brand = load_config(e)
        lut = resolve_lut("brand", brand, bdir, project_root())
    elif a.lut:
        lut = resolve_lut(a.lut, None, None, None)
    try:
        info = prepare(a.src, a.out, a.dur, a.start, a.fit, focus, a.speed, lut, a.lut_strength, a.grade, look)
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
    # the project's own video = the same shoot: the rough cut's look (balance, LUT, grade), as cut.py applies it -
    # once: a cut.py extract already has it (T5: applied again, a white wall came out pink)
    look, graded = None, False
    if c.get("provider") == "project" and not a.no_look and Path(raw).suffix.lower() in VIDEO_EXT:
        graded = bool(c.get("graded")) or _key(raw) in cut_extracts(e)
        look = None if graded else rough_cut_look(e, strict=False)
        ign = "; --lut is ignored for the project's own footage (--no-look to grade it yourself)" if a.lut else ""
        if graded:
            print(f"{a.insert}: a cut.py extract of this video, already in the rough cut's color: taken as it is{ign}")
        elif look:
            print(f"{a.insert}: look as the rough cut ({look_text(look)}){ign}")
    lut = None if look or graded else resolve_lut(a.lut, o.get("brand"), o.get("brand_dir"), o["project"])
    out = e / "inserts" / f"{i['id']}.mp4"
    focus = tuple(float(x) for x in a.focus.split(","))
    try:
        prepare(raw, out, i["dur"], a.start, a.fit, focus, a.speed, lut, a.lut_strength, look=look)
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
    p.add_argument("--min-score", type=float, default=0.5)
    p.add_argument("--retry", action="store_true", help="search again for inserts this command skipped for lack of footage")
    p.add_argument("--insert", nargs="+", metavar="ID", help="only these inserts (a skipped one is searched again)")
    p.add_argument("--query", help="with one --insert: new search words, saved to the insert")
    p.set_defaults(fn=cmd_plan_search)
    p = sub.add_parser("pick"); p.add_argument("edit"); p.add_argument("insert"); p.add_argument("--candidate", type=int, default=0)
    p.add_argument("--start", "--in", dest="start", type=float, default=0.0); p.add_argument("--fit", default="cover", choices=["cover", "contain"])
    p.add_argument("--focus", default="0.5,0.5"); p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--lut"); p.add_argument("--lut-strength", type=float, default=0.7); p.add_argument("--yes", action="store_true")
    p.add_argument("--no-look", action="store_true", help="the project's own footage without the rough cut's look")
    p.set_defaults(fn=cmd_pick)
    p = sub.add_parser("prepare"); p.add_argument("src"); p.add_argument("--out", required=True)
    p.add_argument("--dur", type=float, required=True); p.add_argument("--start", "--in", dest="start", type=float, default=0.0)
    p.add_argument("--fit", default="cover", choices=["cover", "contain"]); p.add_argument("--focus", default="0.5,0.5")
    p.add_argument("--speed", type=float, default=1.0); p.add_argument("--lut"); p.add_argument("--lut-strength", type=float, default=0.7)
    p.add_argument("--grade", help="a filter chain applied BEFORE the LUT (a correction)")
    p.add_argument("--edit", help="the video for --lut brand (otherwise found from the --out path)")
    p.add_argument("--look", metavar="EDIT", help="edit/<id>: that video's look from cut.json (correct, LUT, grade), as cut.py")
    p.set_defaults(fn=cmd_prepare)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
