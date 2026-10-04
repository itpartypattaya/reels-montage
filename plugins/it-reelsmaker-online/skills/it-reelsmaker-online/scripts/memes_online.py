# -*- coding: utf-8 -*-
"""Online memes for the it-reelsmaker core: Openverse (Creative Commons images cleared for commercial use) and GIPHY
(a reference link only). Part of the it-reelsmaker-online add-on; run through the core:

    python <core scripts>/addon.py memes search "facepalm" [--provider openverse|giphy] [--limit 8]   # candidates online
    python <core scripts>/addon.py memes fetch openverse:<id> [--yes]   # download a CC image into memes/online/
                       # only after the person approves the visual plan; only CC0 / PDM / CC BY / CC BY-SA (no NC, no ND);
                       # the license and the attribution go into the sidecar

After fetch: python <core scripts>/memes.py index, then memes.py set <id> description=... emotion=...; from there the
meme is searched, prepared and placed like a local one (rights cc), and its attribution goes into inserts/credits.json.
GIPHY and KLIPY forbid downloading their content and burning it into commercial videos: a reference link only (put the
GIF on as a sticker in the app's own editor, or re-shoot the meme yourself). The Tenor API closed on 2026-06-30.
The file type is read from the downloaded bytes, not from the link (T5: two emoji sets came as SVG text under a .jpg
name, and Pillow could not open them). A vector image (SVG) is kept as .svg with its sidecar but is not usable yet:
memes.py reads PNG, JPG, WebP and GIF, and there is no SVG renderer in this toolset that works without native
libraries. Search marks SVG results; prefer a raster one, or convert the SVG yourself to <same name>.png next to the
sidecar. Anything that is not an image (an error page) is deleted.
A network error is a warning, not a failure: the edit continues without the meme. REELS_OFFLINE=1: no network at all.
"""
import argparse, re, sys, urllib.parse
from pathlib import Path

from reels_common import project_root, save_json, utf8_stdio, warn
from reels_online import api_key, download, err_text, http_json, offline
from memes import memes_root

# Openverse: commercial use and adaptation (crop, scale, placing into a video) are allowed: no NC and no ND
OPENVERSE_OK = {"cc0", "pdm", "by", "by-sa"}


def sniff(path):
    """The real file type by its first bytes: ".png", ".jpg", ".gif", ".webp", ".svg" or None (not an image)."""
    head = Path(path).read_bytes()[:2048]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    text = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if (text.startswith(b"<?xml") or text.startswith(b"<svg") or text.startswith(b"<!doctype svg")) and b"<svg" in text:
        return ".svg"
    return None


def is_svg(r):
    return (str(r.get("filetype") or "").lower() == "svg"
            or Path(urllib.parse.urlparse(r.get("url") or "").path).suffix.lower() == ".svg")


def online_search(query, provider, limit):
    if offline():
        warn("REELS_OFFLINE=1: online memes skipped")
        return []
    try:
        if provider == "openverse":
            q = urllib.parse.urlencode({"q": query, "license_type": "commercial,modification", "page_size": limit,
                                        "mature": "false"})
            d = http_json("https://api.openverse.org/v1/images/?" + q, cache_hours=24)
            return [{"provider": "openverse", "id": r["id"], "title": r.get("title"), "url": r.get("url"),
                     "page_url": r.get("foreign_landing_url"), "w": r.get("width"), "h": r.get("height"),
                     "license": f"CC {(r.get('license') or '').upper()} {r.get('license_version') or ''}".strip(),
                     "author": r.get("creator"), "attribution": r.get("attribution"), "embed": True, "svg": is_svg(r)}
                    for r in d.get("results", []) if (r.get("license") or "").lower() in OPENVERSE_OK]
        if provider == "giphy":
            key = api_key("GIPHY_API_KEY")
            if not key:
                warn("giphy: no GIPHY_API_KEY key")
                return []
            q = urllib.parse.urlencode({"api_key": key, "q": query, "limit": limit, "rating": "g", "lang": "en"})
            d = http_json("https://api.giphy.com/v1/gifs/search?" + q)
            return [{"provider": "giphy", "id": r["id"], "title": r.get("title"), "page_url": r.get("url"),
                     "w": (r.get("images", {}).get("original") or {}).get("width"),
                     "h": (r.get("images", {}).get("original") or {}).get("height"),
                     "license": "GIPHY: personal non-commercial use only; never burned in", "author": r.get("username"),
                     "embed": False} for r in d.get("data", [])]
        warn(f"no meme provider {provider}")
    except Exception as ex:
        warn(f"{provider}: error ({err_text(ex)}); the meme is not needed, the edit continues")
    return []


def cmd_online(a):
    res = online_search(a.query, a.provider, a.limit)
    if not res:
        print("nothing online (or unavailable) -> no meme: keep the shot; that is fine")
        return
    for k, r in enumerate(res):
        print(f"  [{k}] {r['provider']}:{r['id']} {r.get('w')}×{r.get('h')} {r['license']} | {r.get('title') or ''} | {r.get('page_url')}"
              + ("" if r["embed"] else "  <- REFERENCE ONLY: a sticker in the app's own editor, or re-shoot it")
              + ("  <- SVG: not usable until converted to PNG; prefer a raster result" if r.get("svg") else ""))


def cmd_fetch(a):
    prov, _, rid = a.ref.partition(":")
    if prov != "openverse":
        sys.exit(f"{prov}: downloading to burn it in is not allowed (the service's terms): a reference link only")
    if not re.fullmatch(r"[0-9A-Za-z-]{8,64}", rid or ""):
        sys.exit(f"openverse: unexpected id '{rid}': expected a UUID from addon.py memes search")
    if not a.yes:
        sys.exit("download only after the person approves the visual plan; repeat with --yes")
    if offline():  # the network ban is checked right before the request, not only at search time
        warn("REELS_OFFLINE=1: download skipped, the meme is not prepared; the edit continues without it")
        return
    try:
        r = http_json(f"https://api.openverse.org/v1/images/{urllib.parse.quote(rid, safe='')}/")
    except Exception as ex:
        warn(f"openverse: could not get the item ({err_text(ex)}); the meme is not prepared, the edit continues")
        return
    lic = (r.get("license") or "").lower()
    if lic not in OPENVERSE_OK:
        warn(f"openverse {rid}: the license '{lic or 'not given'}' does not allow commercial use and adaptation "
             f"(allowed: {', '.join(sorted(OPENVERSE_OK))}); not downloading; the meme is not needed, the edit continues")
        return
    if not r.get("url"):
        warn(f"openverse {rid}: the item has no file link; the meme is not prepared")
        return
    project = project_root()
    base = memes_root(project) / "online" / f"openverse-{rid[:8]}"
    part = base.with_name(base.name + ".download")  # the name comes from the bytes, not from the link
    try:
        download(r["url"], part)
    except Exception as ex:
        warn(f"openverse {rid}: download failed ({err_text(ex)}); the meme is not prepared, the edit continues")
        return
    kind = sniff(part)
    if kind is None:
        part.unlink(missing_ok=True)
        warn(f"openverse {rid}: the file is not an image (PNG, JPG, GIF, WebP or SVG); deleted; the meme is not "
             f"prepared, the edit continues")
        return
    dest = base.with_suffix(kind)
    part.replace(dest)
    ver = r.get("license_version") or ""
    attribution = r.get("attribution") or (
        f"“{r.get('title') or 'untitled'}” by {r.get('creator') or 'an unknown author'}, "
        f"{'CC0' if lic == 'cc0' else 'Public Domain Mark' if lic == 'pdm' else f'CC {lic.upper()} {ver}'.strip()}"
        + (f" ({r.get('license_url')})" if r.get("license_url") else ""))
    save_json(dest.with_suffix(".json"), {"description": r.get("title") or "", "rights": "cc", "source": r.get("foreign_landing_url"),
                                          "license": lic, "license_version": ver, "license_url": r.get("license_url"),
                                          "creator": r.get("creator"), "creator_url": r.get("creator_url"),
                                          "attribution": attribution,
                                          "tags": [t.get("name") for t in (r.get("tags") or []) if t.get("name")][:10]})
    if kind == ".svg":
        warn(f"{dest.name} is a vector image (SVG), the link said nothing of it: memes.py reads PNG, JPG, WebP and GIF, "
             f"so it is not usable yet. Take a raster result instead, or convert it yourself to {dest.stem}.png "
             f"(at least 600 px, transparent background kept) next to {dest.stem}.json, which holds the license and "
             f"the attribution; then memes.py index")
        return
    print(f"{dest} (CC {lic.upper()} {ver}; a sidecar with the attribution); next: memes.py index, then memes.py set "
          f"<id> description=... emotion=...")


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="addon.py memes", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--provider", default="openverse", choices=["openverse", "giphy"])
    p.add_argument("--limit", type=int, default=8); p.set_defaults(fn=cmd_online)
    p = sub.add_parser("fetch"); p.add_argument("ref"); p.add_argument("--yes", action="store_true"); p.set_defaults(fn=cmd_fetch)
    a = ap.parse_args(argv)
    a.fn(a)
