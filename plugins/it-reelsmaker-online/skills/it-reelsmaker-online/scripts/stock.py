# -*- coding: utf-8 -*-
"""Online stock footage for B-roll: Pixabay, Pexels, Magnific. The core's footage.py gets these sources through
reels_online.footage_providers() and uses them like its own (providers, search, plan-search, pick); this module is not
run on its own.

    pixabay   PIXABAY_API_KEY (the default): free, commercial use without attribution
    pexels    PEXELS_API_KEY: commercial use without attribution; issuing of new keys has been paused since 2026
    magnific  MAGNIFIC_API_KEY or FREEPIK_API_KEY: paid (credits), not tested live

Keys: environment variables or the keys file (reels_online.KEYS_FILE). REELS_OFFLINE=1: these sources are off.
Offline mode and the key are checked before every network action. A download happens only after the person approves
the visual plan (footage.py pick --yes).
"""
import re, urllib.parse
from pathlib import Path

from reels_common import score
from reels_online import api_key, download, http_json, offline


def cand(**kw):
    """A search candidate: the same fields as the core's footage.cand()."""
    base = {"provider": None, "id": None, "title": "", "path": None, "url": None, "page_url": None, "w": None, "h": None,
            "dur": None, "size_mb": None, "license": None, "author": None, "score": 0.0, "embed": True, "notes": ""}
    base.update(kw)
    return base


class Provider:
    name = "base"
    online = False
    key_env = None

    def available(self):
        if self.online and offline():
            return False, "REELS_OFFLINE=1"
        if self.key_env and not api_key(self.key_env):
            return False, f"no key {self.key_env}"
        return True, ""

    def search(self, query, o):
        return []

    def fetch(self, c, folder):
        return Path(c["path"])


class PixabayProvider(Provider):
    """pixabay.com/api/videos: free, commercial use without attribution; no orientation filter (we keep h > w);
    answers are cached for 24 h (an API requirement); bulk downloading is forbidden, so only the chosen clip is
    downloaded."""
    name, online, key_env = "pixabay", True, "PIXABAY_API_KEY"

    def search(self, query, o):
        q = urllib.parse.urlencode({"key": api_key(self.key_env), "q": query[:100], "per_page": 50, "safesearch": "true",
                                    "video_type": "film"})
        data = http_json("https://pixabay.com/api/videos/?" + q, cache_hours=24)
        res = []
        for h in data.get("hits", []):
            vids = h.get("videos", {})
            best = None
            for k in ("large", "medium", "small"):
                v = vids.get(k) or {}
                if v.get("url") and v.get("height", 0) > v.get("width", 0) and v.get("width", 0) >= 720:
                    best = (k, v)
                    break
            if not best or (o.get("min_dur") and h.get("duration", 0) < o["min_dur"]):
                continue
            k, v = best
            res.append(cand(provider=self.name, id=str(h["id"]), title=h.get("tags", ""), url=v["url"],
                            page_url=h.get("pageURL"), w=v.get("width"), h=v.get("height"), dur=h.get("duration"),
                            size_mb=round(v.get("size", 0) / 1e6, 1) or None, license="Pixabay Content License",
                            author=h.get("user"), score=score(query, h.get("tags", "")), notes=f"variant {k}"))
        return res

    def fetch(self, c, folder):
        return download(c["url"], folder / f"pixabay-{c['id']}.mp4")


class PexelsProvider(Provider):
    """api.pexels.com/v1/videos/search?orientation=portrait: commercial use without attribution (show a link to Pexels
    in the interface, not in the video). Issuing of new keys is paused (checked 2026-10-01)."""
    name, online, key_env = "pexels", True, "PEXELS_API_KEY"

    def search(self, query, o):
        q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "size": "medium", "per_page": 40})
        data = http_json("https://api.pexels.com/v1/videos/search?" + q, headers={"Authorization": api_key(self.key_env)},
                         cache_hours=24)
        res = []
        for v in data.get("videos", []):
            if o.get("min_dur") and v.get("duration", 0) < o["min_dur"]:
                continue
            files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"
                     and (f.get("height") or 0) > (f.get("width") or 0) and (f.get("width") or 0) >= 720]
            if not files:
                continue
            f = min(files, key=lambda f: abs((f.get("width") or 0) - 1080) + (0 if (f.get("width") or 0) >= 1080 else 5000))
            title = re.sub(r"[-/]", " ", urllib.parse.urlparse(v.get("url", "")).path.split("/")[-2] if v.get("url") else "")
            res.append(cand(provider=self.name, id=str(v["id"]), title=title, url=f["link"], page_url=v.get("url"),
                            w=f.get("width"), h=f.get("height"), dur=v.get("duration"), license="Pexels License",
                            author=(v.get("user") or {}).get("name"), score=score(query, title)))
        return res

    def fetch(self, c, folder):
        return download(c["url"], folder / f"pexels-{c['id']}.mp4")


class MagnificProvider(Provider):
    """api.magnific.com (formerly the Freepik API; Videvo moved there too): a vertical and 9:16 filter, paid (credits).
    NOT TESTED LIVE: the filter syntax and the response fields follow the documentation as of 2026-10-01."""
    name, online, key_env = "magnific", True, "MAGNIFIC_API_KEY"

    def search(self, query, o):
        q = urllib.parse.urlencode({"term": query, "filters[orientation]": "vertical", "filters[ai-generated][excluded]": 1})
        data = http_json("https://api.magnific.com/v1/videos?" + q, headers={"x-magnific-api-key": api_key(self.key_env)})
        res = []
        for v in data.get("data", []):
            res.append(cand(provider=self.name, id=str(v.get("id")), title=v.get("title") or v.get("name", ""),
                            page_url=v.get("url"), dur=v.get("duration"), license="Magnific (attribution on free items)",
                            score=score(query, v.get("title") or ""), notes="paid; the file link comes at download time"))
        return res

    def fetch(self, c, folder):
        d = http_json(f"https://api.magnific.com/v1/videos/{c['id']}/download",
                      headers={"x-magnific-api-key": api_key(self.key_env)})
        url = (d.get("data") or d).get("url")
        return download(url, folder / f"magnific-{c['id']}.mp4")


PROVIDERS = [PixabayProvider(), PexelsProvider(), MagnificProvider()]
