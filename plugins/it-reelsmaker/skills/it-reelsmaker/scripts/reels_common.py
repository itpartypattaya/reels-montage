# -*- coding: utf-8 -*-
"""Shared helpers for the skill's scripts: project paths, brands, video settings, ffmpeg, word search.

Imported by the other scripts (brand.py, reelcfg.py, visual_plan.py, footage.py, memes.py, ...). Standard library
only. No network access and no credentials here: online sources live in the it-reelsmaker-online add-on, which this
module loads only when it is installed (see online()).
"""
import contextlib, importlib, json, math, os, re, subprocess, sys, time, uuid
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
DEFAULTS_FILE = SKILL / "assets" / "reel-defaults.json"
# A personal copy of the skill can keep its own defaults next to the shared ones (deep-merged on top);
# the published plugin has no such file.
DEFAULTS_LOCAL = SKILL / "assets" / "reel-defaults.local.json"
SETTINGS_FILE = "it-reelsmaker.json"
# Your own defaults for a project: <project>/reel-defaults.json, the same format, only the keys you change. It lives
# in the project, never in the plugin folder (an update replaces that folder).
PROJECT_DEFAULTS = "reel-defaults.json"

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
GIF_EXT = {".gif"}


def utf8_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def warn(msg):
    print("! " + msg, file=sys.stderr)


_WARNED = set()


def warn_once(msg):
    """Warn once per process (load_config is called several times per command)."""
    if msg not in _WARNED:
        _WARNED.add(msg)
        warn(msg)


def load_json(p, default=None):
    p = Path(p)
    for _ in range(40):
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except PermissionError:  # Windows: another process is replacing the file right now (save_json -> os.replace)
            time.sleep(0.05)
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(p, obj):
    """Atomic write: a unique temp file in the same folder, then os.replace. A reader sees the old file or the new
    one, never half of it. Only locked() / editing_json() protect against losing someone else's update."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for k in range(60):
            try:
                os.replace(tmp, p)
                return
            except PermissionError:  # Windows: the file is open for reading in another process; wait
                if k == 59:
                    raise
                time.sleep(0.05)
    finally:
        if tmp.exists():
            tmp.unlink()


_HELD = {}


@contextlib.contextmanager
def locked(p, timeout=30.0, stale=120.0):
    """Lock a read-modify-write cycle between sessions: a <name>.lock file next to it, created exclusively.
    Re-entry in the same process doesn't wait. A lock older than `stale` seconds counts as abandoned (its process
    died) and is removed, so keep only quick work inside: no downloads, no renders."""
    key = os.path.normcase(os.path.abspath(p))
    if _HELD.get(key):
        _HELD[key] += 1
        try:
            yield
        finally:
            _HELD[key] -= 1
        return
    lk = Path(key + ".lock")
    lk.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    while True:
        try:
            fd = os.open(lk, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time():.0f}\n".encode())
            os.close(fd)
            break
        except (FileExistsError, PermissionError):
            try:
                if time.time() - lk.stat().st_mtime > stale:
                    warn(f"removing an abandoned lock {lk.name} (older than {stale:.0f} s)")
                    lk.unlink()
                    continue
            except OSError:
                pass
            if time.time() - t0 > timeout:
                sys.exit(f"the file has been busy in another session for over {timeout:.0f} s: {lk}; try again later "
                         f"(if no other session is running, delete this .lock)")
            time.sleep(0.1)
    _HELD[key] = 1
    try:
        yield
    finally:
        _HELD.pop(key, None)
        try:
            lk.unlink()
        except OSError:
            pass


@contextlib.contextmanager
def editing_json(p, default=None):
    """with editing_json(path, {}) as obj: ... reads under the lock, change obj in place, written atomically.
    An exception or sys.exit inside leaves the file unchanged."""
    with locked(p):
        obj = load_json(p, default)
        yield obj
        save_json(p, obj)


def _merge(base, over):
    """Deep merge of dicts: `over` wins (nested dicts are merged key by key)."""
    out = json.loads(json.dumps(base))
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def defaults_layers(project=None):
    """The defaults as (label, doc) layers, left to right: the skill's assets/reel-defaults.json; the online add-on's
    DEFAULTS if it is installed; a personal copy's assets/reel-defaults.local.json; the project's own
    <project>/reel-defaults.json ("project"); the file named in REELS_DEFAULTS_OVERLAY ("overlay")."""
    layers = [("defaults", load_json(DEFAULTS_FILE, {}) or {})]
    ext = online()
    if ext and isinstance(getattr(ext, "DEFAULTS", None), dict):
        layers.append(("defaults", ext.DEFAULTS))
    project = Path(project or project_root())
    for label, f in (("defaults", DEFAULTS_LOCAL), ("project", project / PROJECT_DEFAULTS),
                     ("overlay", os.environ.get("REELS_DEFAULTS_OVERLAY"))):
        if f and Path(f).is_file():
            doc = load_json(f, {})
            if not isinstance(doc, dict):
                warn(f"{f}: expected a JSON object like assets/reel-defaults.json; ignored")
                continue
            layers.append((label, doc))
    return layers


def load_defaults(project=None):
    """The merged defaults (see defaults_layers)."""
    doc = {}
    for _, layer in defaults_layers(project):
        doc = _merge(doc, layer)
    return doc


# --- Paths -----------------------------------------------------------------------------------------------

def _settings_file(start):
    for q in [start, *start.parents]:
        if (q / SETTINGS_FILE).is_file():
            return q / SETTINGS_FILE
    return None


def project_root(start=None):
    """The editing project folder: REELS_PROJECT; else project_root from it-reelsmaker.json in the current folder or
    above; else the nearest folder upwards with edit/ or brands/; else the current folder."""
    env = os.environ.get("REELS_PROJECT")
    if env:
        return Path(env).resolve()
    p = Path(start or os.getcwd()).resolve()
    f = _settings_file(p)
    if f:
        root = (load_json(f, {}) or {}).get("project_root")
        if root and not str(root).startswith("${"):
            return (f.parent / root).resolve()
    for q in [p, *p.parents]:
        if (q / "edit").is_dir() or (q / "brands").is_dir():
            return q
    return p


def project_settings(project=None):
    """it-reelsmaker.json of the project ({} if there is none)."""
    project = project or project_root()
    return load_json(Path(project) / SETTINGS_FILE, {}) or {}


def library_dirs(project, s):
    """The asset library folders: library_dirs from the reel settings, plus the plugin setting assets_dir
    (it-reelsmaker.json -> assets_dir). A relative path is relative to the project folder; an unexpanded ${...} value
    counts as not set. Used by footage.py, memes.py and library_catalog.py alike."""
    project = Path(project)
    dirs = s.get("library_dirs") or []
    out = [dirs] if isinstance(dirs, str) else list(dirs)
    extra = project_settings(project).get("assets_dir")
    if extra and not str(extra).startswith("${"):
        extra = str(Path(str(extra)).expanduser())
        if (project / extra).resolve() not in {(project / d).resolve() for d in out}:
            out.append(extra)
    return out


SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}")


def safe_slug(s, what="slug", dots=False):
    """A name that becomes part of a path (brand, video id): Latin letters, digits, "-", "_" (dots=True also allows
    ".", but not ".."). Otherwise `../x` or an absolute path would read and write outside brands/, edit/, public/."""
    s = str(s or "")
    if not (NAME_RE if dots else SLUG_RE).fullmatch(s) or ".." in s:
        sys.exit(f"invalid {what}: {s!r}: Latin letters, digits, '-' and '_' only{', and .' if dots else ''} "
                 f"(no spaces, / \\ or ..)")
    return s


def inside(root, p, what="path"):
    """Require the real path to stay inside root, including existing parents of new files."""
    r, q = os.path.normcase(str(Path(root).resolve())), os.path.normcase(str(Path(p).resolve()))
    try:
        ok = os.path.commonpath([r, q]) == r
    except ValueError:  # different drives
        ok = False
    if not ok:
        sys.exit(f"{what} {p} is outside {root}")
    return Path(p).resolve()


def is_project(project):
    project = Path(project)
    return bool(os.environ.get("REELS_PROJECT") or (project / "edit").is_dir() or (project / "brands").is_dir()
                or (project / SETTINGS_FILE).is_file())


def edit_dir(arg, project=None, create=False):
    """`edit/4821`, `4821` or an absolute path -> the video's folder.
    create=True: if the folder doesn't exist and the argument is `edit/<id>` or `<id>`, create edit/<id> in the
    project folder."""
    p = Path(arg)
    if p.is_dir():
        return p.resolve()
    project = project or project_root()
    for q in (project / arg, project / "edit" / arg):
        if q.is_dir():
            return q.resolve()
    if create:
        parts = Path(str(arg).replace("\\", "/")).parts
        rid = parts[1] if len(parts) == 2 and parts[0] == "edit" else parts[0] if len(parts) == 1 else None
        if rid is None:
            sys.exit(f"no video folder: {arg}; only edit/<id> or <id> in the project folder can be created")
        safe_slug(rid, "video id", dots=True)
        if not is_project(project):
            sys.exit(f"no video folder: {arg}, and no editing project was found (no edit/, brands/ or "
                     f"{SETTINGS_FILE} above {project}); run from the project folder or set REELS_PROJECT")
        q = project / "edit" / rid
        q.mkdir(parents=True, exist_ok=True)
        print(f"created the video folder: {q}")
        return q.resolve()
    sys.exit(f"no video folder: {arg}")


def rel(p, base):
    try:
        return Path(p).resolve().relative_to(Path(base).resolve()).as_posix()
    except ValueError:
        return str(p)


# --- The online add-on -------------------------------------------------------------------------------------

_ONLINE = None


def online():
    """The it-reelsmaker-online add-on module (reels_online), or None when it is not installed. Its scripts folder
    comes from REELS_ONLINE_SCRIPTS (the add-on's instructions tell Claude to set it) or from it-reelsmaker.json ->
    online_scripts. Without it, online sources and generation are simply off."""
    global _ONLINE
    if _ONLINE is None:
        _ONLINE = False
        d = os.environ.get("REELS_ONLINE_SCRIPTS") or project_settings().get("online_scripts")
        if d and str(d).startswith("${"):  # an unexpanded plugin setting counts as not set
            d = None
        if d:  # ~ is the home folder; a relative path is relative to the project folder
            try:
                d = Path(str(d)).expanduser()
            except RuntimeError:  # ~someone for a user this computer doesn't have: reported as not found below
                d = Path(str(d))
            d = str(d if d.is_absolute() else project_root() / d)
        if d and not Path(d, "reels_online.py").is_file():
            warn(f"the online add-on is not found in {d} (it was updated or removed); to use it again, run its "
                 f"link command in this project: python <add-on scripts>/reels_online.py link")
        elif d:
            sys.path.insert(0, str(Path(d)))
            try:
                _ONLINE = importlib.import_module("reels_online")
            except Exception as x:  # a broken add-on must not break offline editing
                warn(f"the online add-on did not load ({x}); continuing without online sources")
    return _ONLINE or None


# --- Brands -----------------------------------------------------------------------------------------------

def brand_roots(project=None):
    """Where profiles live: the project's brands/ first; a brands/ folder next to the skill only if it exists
    (a personal copy of the skill). The project's profile wins."""
    project = project or project_root()
    roots = [project / "brands"]
    if (SKILL / "brands").is_dir():
        roots.append(SKILL / "brands")
    return roots


def list_brands(project=None):
    seen, out = set(), []
    for root in brand_roots(project):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            f = d / "brand.json"
            if d.name.startswith("_") or not f.is_file() or d.name in seen:
                continue
            seen.add(d.name)
            out.append((d.name, d, load_json(f, {})))
    return out


def find_brand(slug, project=None):
    safe_slug(slug, "brand slug")
    for root in brand_roots(project):
        f = inside(root, root / slug / "brand.json", "brand profile")
        if f.is_file():
            return root / slug, load_json(f, {})
    return None, None


def brand_file(value, brand_dir, project=None):
    """A path from the profile: absolute; relative to the brand folder; to the project; to the skill."""
    if not value:
        return None
    p = Path(value)
    if p.is_absolute():
        return p if p.exists() else None
    project = project or project_root()
    for base in (brand_dir, project, SKILL):
        if base and (Path(base) / p).exists():
            return (Path(base) / p).resolve()
    return None


# --- Video settings ---------------------------------------------------------------------------------------

SETTING_KEYS_BOOL = ["use_broll", "use_project_footage", "use_local_footage", "use_generated_footage",
                     "use_scenes", "use_memes", "use_local_memes"]


def parse_value(v):
    low = v.strip().lower()
    if low in ("true", "yes", "on", "1"):
        return True
    if low in ("false", "no", "off", "0"):
        return False
    if low in ("null", "none"):
        return None
    try:
        return json.loads(v)
    except Exception:
        return v


def parse_sets(items):
    out = {}
    for it in items or []:
        if "=" not in it:
            sys.exit(f"--set expects key=value, got: {it}")
        k, v = it.split("=", 1)
        out[k.strip()] = parse_value(v)
    return out


TONE_PRESETS = ["premium", "warm", "expert", "story", "tech", "friendly", "drive", "bold"]  # quiet -> loud
TONE_DEFAULT = "expert"
BRAND_SCHEMA = 2  # 1 -> 2: brand tone (references/migrations.md)
MEME_SIZES = ["s", "m", "l"]


def migrate_brand(b):
    """Bring a profile up to the current schema: only add keys, never delete. -> list of "what changed" lines.
    Schema 1 (no schema, or 1) -> 2: tone, if missing, becomes expert."""
    notes = []
    if int(b.get("schema") or 1) < 2:
        if not isinstance(b.get("tone"), dict) or not b["tone"].get("preset"):
            b["tone"] = {"preset": TONE_DEFAULT, "overrides": {}}
            notes.append(f"the profile had no brand tone, so it is now {TONE_DEFAULT} (calm, memes only on request); "
                         f"to change it: brand.py tone <slug> <preset>")
        b["schema"] = 2
    return notes


def tone_rules(brand=None, doc=None, slug=None):
    """The brand tone, resolved: the preset from reel-defaults.json -> brand_tones, plus brand.json -> tone.overrides;
    an explicit brand.json -> motion overrides the preset's motion. Returns (rules, note): rules["preset"] is the
    preset name, note is a warning (tone not set / not confirmed / unknown) or None. No tone -> expert."""
    doc = doc if doc is not None else load_defaults()
    tones = {k: v for k, v in (doc.get("brand_tones") or {}).items() if not k.startswith("_")}
    t = (brand or {}).get("tone") or {}
    if isinstance(t, str):
        t = {"preset": t}
    preset, note = t.get("preset"), None
    who = f"'{slug or (brand or {}).get('slug') or '?'}'"
    if brand is not None and not preset:
        note = (f"brand {who} has no tone; using {TONE_DEFAULT}. Ask for the tone and save it: "
                f"brand.py tone <slug> {'|'.join(TONE_PRESETS)}")
    elif preset and preset not in tones:
        note = f"unknown tone for brand {who}: {preset!r} -> {TONE_DEFAULT} (available: {', '.join(tones)})"
        preset = None
    elif t.get("unconfirmed"):
        note = (f"the tone of brand {who} is not confirmed ({preset} by default); ask the brand owner: "
                f"brand.py tone <slug> {'|'.join(TONE_PRESETS)}")
    preset = preset or TONE_DEFAULT
    rules = _merge(tones.get(preset, {}), t.get("overrides") or {})
    rules["preset"] = preset
    if (brand or {}).get("motion"):  # an explicit motion in the profile overrides the preset
        rules["motion"] = brand["motion"]
    if rules.get("motion") == "calm":  # calm motion: no bounce or shake, unless set explicitly in overrides
        for k in ("overshoot", "shake"):
            if k not in (t.get("overrides") or {}):
                rules[k] = False
    if t.get("overrides"):
        rules["overrides"] = t["overrides"]
    return rules, note


def tone_settings(rules, doc):
    """Defaults of the brand-tone layer: intensity, use_broll, use_memes, meme_size (<= size_max), scene_tone."""
    out = {}
    if rules.get("intensity"):
        out["intensity"] = rules["intensity"]
    if "broll_default" in rules:
        out["use_broll"] = bool(rules["broll_default"])
    m = rules.get("memes") or {}
    if "default" in m:
        out["use_memes"] = bool(m["default"]) and m.get("allowed", True) is not False
    cap = m.get("size_max")
    if cap in MEME_SIZES:
        base = (doc.get("settings") or {}).get("meme_size") or "m"
        out["meme_size"] = base if base in MEME_SIZES and MEME_SIZES.index(base) <= MEME_SIZES.index(cap) else cap
    if rules.get("scene_tone"):
        out["scene_tone"] = rules["scene_tone"]
    return out


def tone_summary(rules):
    """One line about the brand tone for reelcfg.py show / brand.py show."""
    m = rules.get("memes") or {}
    if m.get("allowed") is False or not m.get("max"):
        memes = "no memes"
    else:
        memes = (f"memes <= {m.get('max')} ({m.get('size_max') or '-'}, "
                 f"{'on by default' if m.get('default') else 'only on request'}"
                 f"{', full-frame allowed' if m.get('cutaway') else ''})")
    tr = ", ".join(rules.get("transitions") or [])
    extra = [x for x, ok in (("overshoot", rules.get("overshoot")), ("shake", rules.get("shake"))) if ok]
    return (f"{rules.get('preset')} ({rules.get('label', '')}): {memes}, full <= {rules.get('full_scenes_max')}, "
            f"transitions {tr} (flash <= {rules.get('flash_max')}, whip <= {rules.get('whip_max')}), "
            f"scene tone {rules.get('scene_tone')} (allowed: {', '.join(rules.get('scene_tones') or [])}), "
            f"motion {rules.get('motion')}, technique loudness {rules.get('loudness')}"
            + (f", {' and '.join(extra)}" if extra else "")
            + (f"; overridden in the profile: {', '.join(rules['overrides'])}" if rules.get("overrides") else ""))


def load_config(edit=None, overrides=None, project=None):
    """Layers: skill defaults <- brand tone preset defaults (brand.json -> tone) <- the project's reel-defaults.json <-
    brand profile (inserts) <- edit/<id>/reel.json <- overrides (words from the prompt). settings["brand_tone"] is the resolved brand tone (the
    ceilings for visual_plan.py validate); it comes only from the profile, reel.json can't change it (going louder
    takes tone_override). Returns (settings, provenance, defaults_doc, brand_dir, brand)."""
    project = project or project_root()
    doc, prov = {}, {}
    for label, layer in defaults_layers(project):
        doc = _merge(doc, layer)
        for k in (layer.get("settings") or {}):
            prov[k] = label
    settings = dict(doc.get("settings", {}))
    reel = load_json(Path(edit) / "reel.json", {}) if edit else {}
    overrides = overrides or {}
    slug = overrides.get("brand") or reel.get("brand") or settings.get("brand")
    bdir, brand = find_brand(slug, project) if slug else (None, None)
    if slug and brand is None:
        warn(f"brand '{slug}' not found in {', '.join(str(r) for r in brand_roots(project))}; "
             f"create it: brand.py new --name ... --colors ...")
    rules, note = tone_rules(brand, doc, slug)
    if note:
        warn_once(note)
    for k, v in tone_settings(rules, doc).items():
        if prov.get(k) in ("project", "overlay") and k != "meme_size":
            continue  # your own project defaults beat the preset's guesses; meme_size is already capped by the tone
        settings[k], prov[k] = v, f"tone:{rules['preset']}"
    for k, v in ((brand or {}).get("inserts") or {}).items():
        settings[k], prov[k] = v, f"brand:{slug}"
    for k, v in reel.items():
        if k in ("brand_snapshot", "notes"):
            continue
        settings[k], prov[k] = v, "reel.json"
    for k, v in overrides.items():
        settings[k], prov[k] = v, "override"
    settings["brand"] = slug
    settings["brand_tone"] = rules
    prov["brand_tone"] = f"brand:{slug}" if brand and brand.get("tone") else f"tone:{rules['preset']} (not set)"
    if settings.get("intensity") not in (doc.get("intensity") or {}):
        warn(f"unknown intensity {settings.get('intensity')!r} -> moderate")
        settings["intensity"] = "moderate"
    return settings, prov, doc, bdir, brand


def effective(settings):
    """What will actually turn on. Every "no" has a reason (this is the fallback logic). Online sources and
    generation are decided by the online add-on when it is installed; without it they are off."""
    s = settings
    eff, why = {}, {}

    def put(name, ok, reason=""):
        eff[name] = bool(ok)
        if not ok and reason:
            why[name] = reason

    broll = s.get("use_broll", False)
    put("broll", broll, "use_broll=false")
    put("project_footage", broll and s.get("use_project_footage"), "off")
    put("local_footage", broll and s.get("use_local_footage"), "off")
    gen = broll and s.get("use_generated_footage")
    engines = s.get("generation_engines") or ["code"]
    put("generated_code", gen and "code" in engines, "off" if not gen else "the code engine is not allowed")
    memes = s.get("use_memes", False)
    bt = s.get("brand_tone") if isinstance(s.get("brand_tone"), dict) else {}
    if memes and (bt.get("memes") or {}).get("allowed") is False and not s.get("tone_override"):
        memes = False
        put("memes", False, f"brand tone {bt.get('preset')} doesn't allow memes (reel.json -> tone_override: true "
                            f"goes louder on explicit request)")
    else:
        put("memes", memes, "use_memes=false")
    put("local_memes", memes and s.get("use_local_memes"), "off")
    ext = online()
    if ext:
        ext.effective_online(s, put, eff)
    else:
        for name in ("online_footage", "generated_prompts", "generate_now", "online_memes"):
            asked = s.get({"online_footage": "use_online_footage", "online_memes": "use_online_memes"}.get(name, ""))
            put(name, False, "the online add-on is not installed" if asked else "off")
        eff["online_footage_providers"], eff["online_meme_providers"] = [], []
    return eff, why


def budget(duration, settings, doc):
    b = dict((doc.get("intensity") or {}).get(settings.get("intensity", "moderate"), {}))
    per = b.get("broll_per_30s", 3)
    b["broll_max"] = max(1, math.ceil(duration / 30.0 * per)) if per else 0
    b["coverage_max_s"] = round(duration * b.get("coverage_max", 0.2), 2)
    return b


# --- Media ------------------------------------------------------------------------------------------------

def local_media_args(args):
    """Limit media inputs to file/pipe; lavfi inputs have no file protocol options."""
    args = [str(a) for a in args]
    tool = Path(args[0]).stem.lower()
    if tool == "ffprobe":
        return [args[0], "-protocol_whitelist", "file,pipe", *args[1:]]
    if tool != "ffmpeg":
        return args
    out, fmt = [], None
    for i, arg in enumerate(args):
        if arg == "-f" and i + 1 < len(args):
            fmt = args[i + 1]
        if arg == "-i":
            if fmt != "lavfi":
                out.extend(["-protocol_whitelist", "file,pipe"])
            fmt = None
        out.append(arg)
    return out


def save_text(p, text):
    """Atomically publish UTF-8 text with LF endings; callers lock read-modify-write."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()


def run(args, check=True, quiet=False):
    r = subprocess.run(local_media_args(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"{Path(str(args[0])).name} failed:\n" + r.stderr[-1500:])
    return r


def audio_offset(p):
    """Seconds by which the audio track starts after the video track (negative: before), from the container; for
    the record only (extraction uses ANALYSIS_AF). A phone MOV often has 0.08-0.10 s: audio extracted without
    ANALYSIS_AF runs ahead of the video by that much, and every edge measured on it lands that much early in cut.py,
    which cuts by the video timeline (a real case: word endings clipped in every take)."""
    r = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time", "-of", "json", str(p)], check=False)
    try:
        st = {}
        for s in json.loads(r.stdout or "{}").get("streams", []):
            if s.get("codec_type") in ("video", "audio") and s.get("codec_type") not in st and s.get("start_time") not in (None, "N/A"):
                st[s["codec_type"]] = float(s["start_time"])
        return round(st["audio"] - st["video"], 6) if "audio" in st and "video" in st else 0.0
    except (ValueError, KeyError, TypeError):
        return 0.0


# Extracting a whole track for analysis: second t of the WAV = second t of the video. first_pts=0 pads (or trims) the
# start by the audio's real decoded timestamps, so the encoder delay of AAC is accounted for too (the start_time from
# audio_offset alone was 24 ms off on an ffmpeg-made file); 16 kHz mono is what speech_mask.py and Whisper read.
ANALYSIS_AF = "aresample=16000:async=1:first_pts=0"


def probe(p):
    """w, h, dur, fps, has_audio, vcodec, pix_fmt (the phone rotation tag applied)."""
    r = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(p)], check=False)
    try:
        d = json.loads(r.stdout or "{}")
    except Exception:
        d = {}
    info = {"w": None, "h": None, "dur": None, "fps": None, "has_audio": False, "vcodec": None, "pix_fmt": None}
    for s in d.get("streams", []):
        if s.get("codec_type") == "video" and info["w"] is None:
            w, h = s.get("width"), s.get("height")
            rot = 0
            for sd in s.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rot = abs(int(float(sd["rotation"])))
            if rot in (90, 270):
                w, h = h, w
            info.update(w=w, h=h, vcodec=s.get("codec_name"), pix_fmt=s.get("pix_fmt"),
                        sar=s.get("sample_aspect_ratio") or "1:1")
            fr = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1"
            try:
                a, b = fr.split("/")
                info["fps"] = round(float(a) / float(b), 3) if float(b) else None
            except Exception:
                pass
            if s.get("duration"):
                info["dur"] = float(s["duration"])
        elif s.get("codec_type") == "audio":
            info["has_audio"] = True
    if info["dur"] is None and d.get("format", {}).get("duration"):
        try:
            info["dur"] = float(d["format"]["duration"])
        except Exception:
            pass
    return info


def media_kind(p):
    ext = Path(p).suffix.lower()
    return "video" if ext in VIDEO_EXT else "image" if ext in IMAGE_EXT else "gif" if ext in GIF_EXT else None


# --- Word search (any language, no libraries) ----------------------------------------------------------------

# Short function words that carry no meaning in a search: English, plus the most common Russian ones given as
# Unicode code points (so that this file stays plain English text).
_RU_STOP = ("438", "432", "432 43e", "43d 430", "441", "441 43e", "43a", "43a 43e", "43f 43e", "438 437", "437 430",
            "43e 442", "434 43e", "443", "43e", "43e 431", "430", "43d 43e", "438 43b 438", "436 435", "43b 438",
            "43d 435", "43d 438", "442 43e", "44d 442 43e", "43a 430 43a", "447 442 43e", "434 43b 44f")
STOP = set("the a an of to in on and or for with is are be at by from as it this that".split()) | {
    "".join(chr(int(c, 16)) for c in w.split()) for w in _RU_STOP}
_YO, _YE = chr(0x451), chr(0x435)


def tokens(s):
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s or "")  # split camelCase file names before lowercasing
    s = s.lower().replace(_YO, _YE)  # Russian yo -> ye: both spellings match
    return [t for t in re.split(r"[\W_]+", s) if t and t not in STOP and len(t) > 1]


def _match(a, b):
    if a == b:
        return True
    n = min(len(a), len(b))
    return n >= 4 and a[:max(4, n - 2)] == b[:max(4, n - 2)]


def score(query, text):
    """Share of the query's words found in the text (a word matches by its stem: a common prefix of 4+ letters)."""
    q, t = tokens(query), set(tokens(text))
    if not q:
        return 0.0
    hit = sum(1 for a in q if any(_match(a, b) for b in t))
    return round(hit / len(q), 3)


def forbidden_hits(brand, text):
    """Which imagery the brand forbids (forbidden_imagery / _en) resembles the text. Words match allowing for
    endings (globe/globes), without false hits like hands ~ handshake."""
    tt = set(tokens(text))
    hits = []
    for f in (brand or {}).get("forbidden_imagery", []) + (brand or {}).get("forbidden_imagery_en", []):
        ft = tokens(f)

        def near(t):
            for t2 in tt:
                k = len(os.path.commonprefix([t, t2]))
                if abs(len(t) - len(t2)) <= 3 and k >= max(4, min(len(t), len(t2)) - 2):
                    return True
            return False
        if ft and all(near(t) for t in ft):
            hits.append(f)
    return hits
