# -*- coding: utf-8 -*-
"""Catalog of your own asset library (sound effects, music, icons, short videos) for the it-reelsmaker skill.

Why: a library folder can hold hundreds of files named like IMG_xxxx. The agent should not open them one by one.
This script reads each file once and records its technical data and your verdict; after that the agent reads
_catalog/catalog.md and the overview sheets.

    python scripts/library_catalog.py                    # update (only changed files are measured again)
    python scripts/library_catalog.py --full             # measure everything again
    python scripts/library_catalog.py --dir <folder> [--verdicts <file>]

The folder: --dir; otherwise every folder in library_dirs (reel settings: defaults, brand inserts) and in
it-reelsmaker.json -> assets_dir (a relative path there is relative to the project folder).

Output in <folder>/_catalog/: catalog.json (everything), catalog.md (to read), sheets/*.jpg + *.txt (overview sheets
of images and videos, 80 per sheet: number on the sheet -> file -> verdict). verdicts.json and memes.json (the
reaction-meme annotation) in _catalog/ are yours: the script never changes them.

What is recorded:
  audio (wav, mp3, m4a, flac, aac, ogg): duration, sound start (silence at the start of the file), peak and mean
    loudness; kind "music" in a top folder named Music (or when the library folder itself is named so), else "sfx";
  images and videos (png, jpg, jpeg, webp; mp4, mov, webm, gif): size, background by the corners (transparent /
    green chroma key / black / white / other), alpha, duration of a video;
  verdict, why and rights_block, from your verdicts file.

Verdicts file: --verdicts FILE, by default <folder>/_catalog/verdicts.json if it exists. The plugin ships no
verdicts: they are yours, for your brand. Paths are relative to the library folder, with forward slashes:

    {
     "defaults": {
      "sfx/whoosh": ["ok", "whip, shot change, card fly-in"],
      "sfx/hits": ["caution", "soft ones on a punch-in; hard ones only for a loud brand tone"],
      "icons/misc": ["caution", "mixed folder: look before use"]
     },
     "files": {
      "icons/misc/IMG_0001.png": {"verdict": "no", "why": "a film still: third-party rights", "rights_block": true},
      "sfx/whoosh/long_whoosh.wav": {"verdict": "caution", "why": "long tail: trim it to 0.5 s"}
     }
    }

  defaults - a rule per folder, [verdict, why]; it covers subfolders too, and the longest matching folder wins;
  files    - exceptions per file: verdict, why and optionally rights_block: true, a ban for third-party rights
             (celebrities, politicians, film stills, stock people) that applies to every brand;
  verdicts - "ok", "caution", "no", "check license".
A file that no rule covers gets "caution" ("no rule for this folder"). Without a verdicts file no entry has a
verdict, and the catalog still lists the technical data. Each catalog entry keeps its verdict in the "verdict" field:
to apply verdicts given for style reasons to a brand, set "asset_verdicts": "verdict" in its brand.json; a "no" for
third-party rights applies to every brand anyway.

Needs ffmpeg and ffprobe in PATH and Pillow (pip install Pillow).
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # --help works without Pillow; a run says what to install
    Image = ImageDraw = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import local_media_args, load_config, load_json, locked, project_root, project_settings, save_json, save_text, utf8_stdio, warn

ROOT = None   # the library folder being cataloged (main)
OUT = None    # ROOT / "_catalog"
AUDIO = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}
VIDEO = {".mp4", ".mov", ".webm", ".gif"}
IMAGE = {".png", ".jpg", ".jpeg", ".webp"}
VERDICT_WORDS = ("ok", "caution", "no", "check license")
# Top folder names that hold music (case-insensitive); any other audio is a sound effect. The last one is the Russian
# word for "music", given as Unicode code points so that this file stays plain English text.
MUSIC_DIRS = {"music", "musik", "musique", "musica", "".join(chr(int(c, 16)) for c in "43c 443 437 44b 43a 430".split())}


def run(args):
    return subprocess.run(local_media_args(args), capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe(p):
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,width,height,pix_fmt:format=duration", "-of", "json", str(p)])
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def audio_info(p):
    d = probe(p)
    dur = float(d.get("format", {}).get("duration", 0) or 0)
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-af",
             "silencedetect=noise=-45dB:d=0.01,volumedetect", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    onset = ends[0] if starts and starts[0] <= 0.01 and ends else 0.0
    mx = re.search(r"max_volume: (-?[\d.]+) dB", r.stderr)
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return {"dur": round(dur, 2), "onset": round(onset, 3),
            "peak_db": float(mx.group(1)) if mx else None, "mean_db": float(mean.group(1)) if mean else None}


def audio_kind(rel):
    """music: the file lies in a top folder named Music (or the library folder itself is named so); else sfx."""
    top = rel.split("/")[0] if "/" in rel else ""
    return "music" if {top.casefold(), ROOT.name.casefold()} & MUSIC_DIRS else "sfx"


def bg_of(im):
    """Background by the corners: transparent / green chroma key / black / white / other."""
    im = im.convert("RGBA").resize((64, 64))
    px = [im.getpixel(xy) for xy in [(1, 1), (62, 1), (1, 62), (62, 62)]]
    if all(a < 20 for *_, a in px):
        return "transparent"
    r, g, b = [sum(c[i] for c in px) / 4 for i in range(3)]
    if g > 180 and r < 90 and b < 90:
        return "green chroma key"
    if max(r, g, b) < 30:
        return "black"
    if min(r, g, b) > 225:
        return "white"
    return "other"


def grab_frame(p, t):
    """A video frame at second t -> RGBA or None. A temp file of its own per call, and the exit code is checked:
    a shared frame file showed the PREVIOUS asset's frame for a short or broken video."""
    fd, tmp = tempfile.mkstemp(prefix="library_catalog_", suffix=".png")
    os.close(fd)
    try:
        for ss in dict.fromkeys((max(0.0, t), 0.0)):  # nothing at t (the video is shorter): the first frame
            r = run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ss:.3f}", "-i", str(p), "-frames:v", "1", tmp])
            if r.returncode == 0 and os.path.getsize(tmp) > 0:
                try:
                    with Image.open(tmp) as im:
                        return im.convert("RGBA")
                except Exception:
                    pass
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def placeholder(T, text="no frame"):
    im = Image.new("RGBA", (T, T), (60, 60, 60, 255))  # not red: a real asset can be red
    ImageDraw.Draw(im).text((8, T // 2 - 6), text, fill=(255, 255, 255, 255))
    return im


def visual_info(p):
    ext = p.suffix.lower()
    info = {}
    if ext in VIDEO:
        d = probe(p)
        v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
        info.update(w=v.get("width"), h=v.get("height"), pix=v.get("pix_fmt"),
                    dur=round(float(d.get("format", {}).get("duration", 0) or 0), 2))
        im = grab_frame(p, min(1.0, (info["dur"] or 2) / 2))
        info["bg"] = bg_of(im) if im is not None else "?"
        if im is None:
            info["frame"] = "not grabbed"  # a broken file or one ffmpeg can't read: look at it by hand
        info["alpha"] = bool(info.get("pix") and "a" in info["pix"].replace("yuv", "").replace("nv", ""))
    else:
        try:
            with Image.open(p) as im:
                info.update(w=im.width, h=im.height)
                rgba = im.convert("RGBA")
                info["alpha"] = rgba.getchannel("A").getextrema()[0] < 250
                info["bg"] = bg_of(rgba)
        except Exception:  # a broken image must not stop the whole catalog
            info.update(w=None, h=None, alpha=False, bg="?", frame="unreadable")
    return info


def _pair(v, where):
    """A verdict from the file: [verdict, why], {"verdict": ..., "why": ...} or "verdict" -> (verdict, why)."""
    if isinstance(v, dict):
        word, why = v.get("verdict"), v.get("why", "")
    elif isinstance(v, (list, tuple)) and v:
        word, why = v[0], (v[1] if len(v) > 1 else "")
    else:
        word, why = v, ""
    word = str(word or "").strip().lower()
    if word not in VERDICT_WORDS:
        warn(f"verdicts file, {where}: unknown verdict {word!r} (use {', '.join(VERDICT_WORDS)})")
    return word or None, str(why or "")


def load_verdicts(path):
    """Your verdicts file -> {"file", "defaults": {folder: (verdict, why)}, "files": {path: {verdict, why,
    rights_block}}}; None: there is no file."""
    if not path or not Path(path).is_file():
        return None
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as ex:
        sys.exit(f"the verdicts file {path} is not valid JSON: {ex}")
    if not isinstance(doc, dict):
        sys.exit(f"the verdicts file {path} must hold an object with \"defaults\" and \"files\"")
    key = lambda k: str(k).replace("\\", "/").strip("/")
    out = {"file": str(path), "defaults": {}, "files": {}}
    for k, v in (doc.get("defaults") or {}).items():
        out["defaults"][key(k)] = _pair(v, f"defaults {k!r}")
    for k, v in (doc.get("files") or {}).items():
        word, why = _pair(v, f"files {k!r}")
        out["files"][key(k)] = {"verdict": word, "why": why,
                                "rights_block": bool(isinstance(v, dict) and v.get("rights_block"))}
    return out


def rights_block(rel, verdicts):
    """An explicit ban for third-party rights (celebrities, politicians, film stills, stock people): the rights_block
    field of a per-file verdict. It applies to every brand: the footage and meme scripts never take such assets."""
    return bool(verdicts and (verdicts["files"].get(rel) or {}).get("rights_block"))


def verdict(rel, verdicts):
    if not verdicts:
        return None, ""
    if rel in verdicts["files"]:
        v = verdicts["files"][rel]
        return v["verdict"], v["why"]
    for k in sorted(verdicts["defaults"], key=len, reverse=True):
        if rel.startswith(k + "/"):
            return tuple(verdicts["defaults"][k])
    return ("caution", "no rule for this folder")


def thumb(p, T=150, dur=None):
    try:
        if p.suffix.lower() in VIDEO:
            im = grab_frame(p, min(1.0, (dur or 2) / 2))
            im = placeholder(T) if im is None else im
        else:
            im = Image.open(p).convert("RGBA")
    except Exception:
        im = placeholder(T, "unreadable")
    im.thumbnail((T, T))
    bg = Image.new("RGBA", (T, T), (128, 128, 128, 255))
    d = ImageDraw.Draw(bg)
    for y in range(0, T, 15):
        for x in range(0, T, 15):
            if (x // 15 + y // 15) % 2:
                d.rectangle([x, y, x + 14, y + 14], fill=(170, 170, 170, 255))
    bg.alpha_composite(im, ((T - im.width) // 2, (T - im.height) // 2))
    return bg


def sheets(entries, out=None):
    sd = (out or OUT) / "sheets"
    sd.mkdir(parents=True, exist_ok=True)
    for f in sd.iterdir():
        f.unlink()
    by = {}
    for e in entries:
        if e["kind"] == "visual":
            by.setdefault(e["folder"], []).append(e)
    T, cols = 150, 10
    for folder, items in by.items():
        name = "top" if folder == "." else folder.replace("/", "_")
        for page in range(0, len(items), 80):
            chunk = items[page:page + 80]
            rows = (len(chunk) + cols - 1) // cols
            sheet = Image.new("RGB", (cols * T, rows * (T + 14)), (255, 255, 255))
            d = ImageDraw.Draw(sheet)
            for i, e in enumerate(chunk):
                x, y = (i % cols) * T, (i // cols) * (T + 14)
                sheet.paste(thumb(ROOT / e["path"], T, e.get("dur")).convert("RGB"), (x, y))
                mark = {"no": (200, 0, 0), "caution": (200, 120, 0), "check license": (200, 120, 0)}.get(
                    e["verdict"], (0, 120, 0)) if e["verdict"] else (110, 110, 110)
                d.rectangle([x, y + T, x + T - 1, y + T + 13], fill=mark)
                d.text((x + 3, y + T + 1), str(page + i), fill=(255, 255, 255))
            stem = f"{name}_{page // 80}"
            sheet.save(sd / f"{stem}.jpg", quality=80)
            (sd / f"{stem}.txt").write_text("\n".join(
                f"{page + i}\t{e['path']}\t{e['verdict'] or '-'}" for i, e in enumerate(chunk)), encoding="utf-8")


def fmt_md(entries, verdicts=None):
    L = ["# Asset library catalog", "",
         "Built by `scripts/library_catalog.py` of the it-reelsmaker skill. Do not edit by hand: every run rebuilds it.",
         (f"Verdicts: `{verdicts['file']}` (a rule per folder plus exceptions per file); to change one, edit that file "
          f"and run the script again." if verdicts else
          "No verdicts yet: the entries list technical data only. To add them, create `_catalog/verdicts.json` "
          "(the format is in `python scripts/library_catalog.py --help`) and run the script again."),
         "Images and videos: pick by eye on the overview sheets `sheets/*.jpg` (the stripe under a picture: green - ok, "
         "orange - caution or check license, red - no, gray - no verdict; number -> file in the .txt next to it).",
         "Audio: place a sound by its sound start, not by the start of the file.", ""]
    by = {}
    for e in entries:
        by.setdefault(e["folder"], []).append(e)
    for folder in sorted(by):
        items = by[folder]
        L.append(f"## {folder if folder != '.' else '(top level)'} ({len(items)})")
        L.append("")
        sounds = [e for e in items if e["kind"] in ("sfx", "music")]
        pics = [e for e in items if e["kind"] == "visual"]
        if sounds:
            L.append("| file | dur, s | sound start, s | peak, dB | mean, dB | verdict |")
            L.append("|---|---|---|---|---|---|")
            for e in sounds:
                L.append(f"| {Path(e['path']).name} | {e.get('dur')} | {e.get('onset')} | {e.get('peak_db')} | "
                         f"{e.get('mean_db')} | {e['verdict'] or '-'}{' (rights)' if e.get('rights_block') else ''} |")
            if verdicts:
                fv = verdict(folder + "/", verdicts)  # the folder's own rule, not a per-file exception
                L += ["", f"Folder verdict: {fv[0]} - {fv[1]}"]
            if sounds[0]["kind"] == "music":
                L += ["", "Music: a track burned into a video needs a commercial license; without one, render without "
                          "music and pick the track in the app when publishing."]
            L.append("")
        if pics:
            L.append("| # | file | size | background | dur | verdict | why |")
            L.append("|---|---|---|---|---|---|---|")
            for i, e in enumerate(pics):
                L.append(f"| {i} | {Path(e['path']).name} | {e.get('w')}x{e.get('h')} | {e.get('bg')} | "
                         f"{e.get('dur', '')} | {e['verdict'] or '-'}{' (rights)' if e.get('rights_block') else ''} | "
                         f"{e['why']} |")
            L.append("")
    return "\n".join(L)


def build(full=False, vfile=None):
    """Catalog ROOT into OUT."""
    OUT.mkdir(exist_ok=True)
    verdicts = load_verdicts(vfile or OUT / "verdicts.json")
    cache_f = OUT / "catalog.json"
    cache = {} if full or not cache_f.exists() else \
        {e["path"]: e for e in load_json(cache_f, [])}
    entries = []
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and "_catalog" not in p.relative_to(ROOT).parts[:-1])
    for n, p in enumerate(files):
        rel = p.relative_to(ROOT).as_posix()
        ext = p.suffix.lower()
        kind = audio_kind(rel) if ext in AUDIO else "visual" if ext in VIDEO | IMAGE else None
        if not kind:
            continue
        st = p.stat()
        old = cache.get(rel)
        if old and old.get("size") == st.st_size and old.get("mtime") == int(st.st_mtime):
            e = old
        else:
            e = {"path": rel, "folder": str(Path(rel).parent.as_posix()), "kind": kind,
                 "size": st.st_size, "mtime": int(st.st_mtime)}
            e.update(audio_info(p) if kind in ("sfx", "music") else visual_info(p))
            print(f"{n + 1}/{len(files)} {rel}", flush=True)
        e["verdict"], e["why"] = verdict(rel, verdicts)
        if rights_block(rel, verdicts):
            e["rights_block"] = True
        else:
            e.pop("rights_block", None)  # a lifted ban must not stay from the cache
        entries.append(e)
    with tempfile.TemporaryDirectory(prefix=".build-", dir=OUT) as work:
        work = Path(work)
        sheets(entries, work)
        with locked(cache_f):
            sd = OUT / "sheets"
            sd.mkdir(exist_ok=True)
            wanted = {p.name for p in (work / "sheets").iterdir()}
            for p in (work / "sheets").iterdir():
                os.replace(p, sd / p.name)
            for p in sd.iterdir():
                if p.name not in wanted:
                    p.unlink()
            save_text(OUT / "catalog.md", fmt_md(entries, verdicts))
            save_json(cache_f, entries)
    cnt = {}
    for e in entries:
        cnt[(e["kind"], e["verdict"] or "-")] = cnt.get((e["kind"], e["verdict"] or "-"), 0) + 1
    print(f"done: {OUT}: {len(entries)} files;", ", ".join(f"{k[0]}/{k[1]}: {v}" for k, v in sorted(cnt.items()))
          + ("" if verdicts else "; no verdicts file (see --help)"))


def library_roots(arg=None):
    """Folders to catalog: --dir; otherwise library_dirs from the reel settings and it-reelsmaker.json -> assets_dir
    (a relative path is relative to the project folder; an unexpanded ${...} value counts as not set)."""
    if arg:
        p = Path(arg).expanduser()
        if not p.is_dir():
            sys.exit(f"no folder {p}")
        return [p.resolve()]
    project = project_root()
    dirs = load_config(project=project)[0].get("library_dirs") or []
    dirs = [dirs] if isinstance(dirs, str) else list(dirs)
    out = []
    for v in dirs + [project_settings(project).get("assets_dir")]:
        if not v or str(v).startswith("${"):
            continue
        p = Path(str(v)).expanduser()
        p = (p if p.is_absolute() else project / p).resolve()
        if not p.is_dir():
            warn(f"the asset folder {p} does not exist; skipped")
        elif p not in out:
            out.append(p)
    if not out:
        sys.exit("no asset library folder: pass --dir <folder>, or set assets_dir in it-reelsmaker.json "
                 "(or library_dirs in the reel settings)")
    return out


def main(argv=None):
    global ROOT, OUT
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", help="the library folder (default: library_dirs and assets_dir from the settings)")
    ap.add_argument("--verdicts", help="your verdicts file (default: <folder>/_catalog/verdicts.json if it exists)")
    ap.add_argument("--full", action="store_true", help="measure every file again, not only the changed ones")
    a = ap.parse_args(argv)
    if Image is None:
        sys.exit(f"Pillow is not installed for this Python ({sys.executable}); install it: pip install Pillow")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} is not found in PATH; install ffmpeg (it includes ffprobe)")
    if a.verdicts and not Path(a.verdicts).is_file():
        sys.exit(f"no verdicts file {a.verdicts}")
    for root in library_roots(a.dir):
        ROOT, OUT = root, root / "_catalog"
        print(f"library: {ROOT}", flush=True)
        build(a.full, a.verdicts)


if __name__ == "__main__":
    main()
