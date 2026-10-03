# -*- coding: utf-8 -*-
"""The it-reelsmaker-online add-on: settings, API keys, network helpers and commands for the it-reelsmaker core.

The core is the only entry point. It loads this module as a library (reels_common.online()) and runs the add-on's
commands through its runner addon.py. Link the add-on to a project once, and again after each add-on update (the
plugin folder path contains the version):

    python <add-on scripts>/reels_online.py link [--project DIR]     # online_scripts -> <project>/it-reelsmaker.json
    python <add-on scripts>/reels_online.py unlink [--project DIR]   # remove that key
    python <core scripts>/addon.py memes|gen|matte|transcribe ...    # the add-on's commands, run through the core
    python <add-on scripts>/reels_online.py keys list                 # which keys are set (values masked)
    python <add-on scripts>/reels_online.py keys set PEXELS_API_KEY   # in your own terminal: hidden input
    python <add-on scripts>/reels_online.py keys remove PEXELS_API_KEY

API keys: environment variables, otherwise the file in REELS_KEYS_FILE or ~/.config/it-reelsmaker/keys.env
(KEY=value lines; keep it outside the project and git). Put keys there with `keys set` in your own terminal: the value
is typed hidden, never passes through the chat, and the file is readable by you only. Keys are never printed: every
error passes through scrub().
REELS_OFFLINE=1: no network at all (cached answers still work).
link and unlink use the standard library only and do not import the core.
"""
import argparse, contextlib, hashlib, json, os, re, sys, time, urllib.parse, urllib.request, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTINGS_FILE = "it-reelsmaker.json"
KEYS_FILE = Path(os.environ.get("REELS_KEYS_FILE", str(Path.home() / ".config" / "it-reelsmaker" / "keys.env")))
CACHE = Path.home() / ".cache" / "it-reelsmaker"
MAX_DL_MB = 300


def _version():
    try:
        doc = json.loads((HERE.parents[2] / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        return str(doc.get("version") or "1")
    except Exception:
        return "1"


UA = f"it-reelsmaker/{_version()}"

# --- Settings the add-on adds to the core's reel settings ----------------------------------------------------
SETTING_KEYS_BOOL = ["use_online_footage", "generate_now", "use_online_memes"]
SETTING_KEYS = ["online_footage_providers", "online_meme_providers", "generation_provider", "generation_model",
                "generation_seconds", "transcription_provider"]
# Deep-merged by the core's load_defaults() on top of its assets/reel-defaults.json (lists are replaced whole).
# Online sources and paid generation stay off until a video's reel.json, the brand or the prompt turns them on.
DEFAULTS = {
    "settings": {
        "use_online_footage": False,
        "generate_now": False,
        "use_online_memes": False,
        "broll_priority": ["project", "local", "online", "generated"],
        "meme_priority": ["local", "online"],
        "online_footage_providers": ["pixabay", "pexels"],
        "online_meme_providers": ["openverse", "giphy"],
        "generation_engines": ["code", "model"],
        "generation_provider": "fal",
        "generation_model": "veo3.1-fast",
        "generation_seconds": 6,
    }
}
# command -> add-on module; the core runs it: python <core scripts>/addon.py <command> [args...]
COMMANDS = {"memes": "memes_online", "gen": "genfootage", "matte": "matte_server", "transcribe": "transcribe_online"}

# --- API keys: environment variables, otherwise KEYS_FILE -------------------------------------------------------
FOOTAGE_KEYS = {"pixabay": "PIXABAY_API_KEY", "pexels": "PEXELS_API_KEY", "magnific": "MAGNIFIC_API_KEY", "coverr": "COVERR_API_KEY"}
KEY_ALIASES = {"MAGNIFIC_API_KEY": ["FREEPIK_API_KEY"]}
MEME_KEYS = {"giphy": "GIPHY_API_KEY", "openverse": None}  # openverse: no key (anonymous, about 100 requests a day)
GEN_KEYS = {"fal": "FAL_KEY", "replicate": "REPLICATE_API_TOKEN", "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY", "runway": "RUNWAYML_API_SECRET"}
TRANSCRIBE_KEYS = {"openai": "OPENAI_API_KEY"}

_KEYS = None


def _load_keys():
    global _KEYS
    if _KEYS is None:
        _KEYS = {}
        if KEYS_FILE.is_file():
            for line in KEYS_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    _KEYS[k.strip()] = v.strip().strip('"').strip("'")
    return _KEYS


KEY_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def known_keys():
    """Every key name the add-on reads, aliases included."""
    names = {v for d in (FOOTAGE_KEYS, MEME_KEYS, GEN_KEYS, TRANSCRIBE_KEYS) for v in d.values() if v}
    names |= {a for v in KEY_ALIASES.values() for a in v}
    return sorted(names)


def _mask(v):
    return f"set, ends ...{v[-4:]}" if len(v) >= 12 else "set"


def _keys_lines():
    return KEYS_FILE.read_text(encoding="utf-8").splitlines() if KEYS_FILE.is_file() else []


def _write_keys(lines):
    """Atomic write of the keys file, readable by its owner only (POSIX mode 600; on Windows the file stays in your
    user profile, which other users can't read by default)."""
    created = not KEYS_FILE.parent.exists()
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if created and os.name != "nt":  # only a folder made here; an existing one (a project, /tmp) keeps its rights
        os.chmod(KEYS_FILE.parent, 0o700)
    tmp = KEYS_FILE.with_name(f".{KEYS_FILE.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        os.replace(tmp, KEYS_FILE)
    finally:
        if tmp.exists():
            tmp.unlink()
    if os.name != "nt":
        os.chmod(KEYS_FILE, 0o600)


def _key_name(name):
    if not KEY_NAME_RE.match(name or ""):
        sys.exit(f"{name!r} is not a key name (capital letters, digits and _, like PEXELS_API_KEY)")
    if name not in known_keys():
        print(f"note: the add-on does not read {name}; known keys: {', '.join(known_keys())}")
    return name


def cmd_keys_list(a):
    file_keys = _load_keys()
    print(f"keys file: {KEYS_FILE}" + ("" if KEYS_FILE.is_file() else " (not created yet)"))
    for n in sorted(set(known_keys()) | set(file_keys)):
        env, fv = os.environ.get(n), file_keys.get(n)
        state = (_mask(env) + " (environment)") if env else (_mask(fv) + " (file)") if fv else "not set"
        print(f"  {n:24} {state}")


def cmd_keys_set(a):
    name = _key_name(a.name)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.exit("keys set reads the key with hidden input, so run it yourself in a terminal (not through Claude): "
                 f"python {Path(__file__).resolve()} keys set {name}. This way the key never passes through the chat.")
    import getpass
    value = getpass.getpass(f"{name} (input hidden, Enter to cancel): ").strip()
    if not value:
        sys.exit("nothing typed: the key was not changed")
    if any(c in value for c in "\r\n"):
        sys.exit("the key contains a line break: not saved")
    with file_lock(KEYS_FILE):
        lines = [l for l in _keys_lines() if l.split("=", 1)[0].strip() != name]
        lines.append(f"{name}={value}")
        _write_keys(lines)
    global _KEYS
    _KEYS = None
    print(f"{name}: saved to {KEYS_FILE} ({_mask(value)})")
    if os.environ.get(name):
        print(f"note: the environment variable {name} is also set and takes precedence over the file")


def cmd_keys_remove(a):
    name = _key_name(a.name)
    with file_lock(KEYS_FILE):
        lines = _keys_lines()
        kept = [l for l in lines if l.split("=", 1)[0].strip() != name]
        if len(kept) == len(lines):
            print(f"{name}: not in {KEYS_FILE}")
            return
        _write_keys(kept)
    global _KEYS
    _KEYS = None
    print(f"{name}: removed from {KEYS_FILE}")
    if os.environ.get(name):
        print(f"note: the environment variable {name} is still set")


def api_key(name):
    for n in [name, *KEY_ALIASES.get(name, [])]:
        v = os.environ.get(n) or _load_keys().get(n)
        if v:
            return v
    return None


def offline():
    return os.environ.get("REELS_OFFLINE", "").lower() in ("1", "true", "yes")


# --- What actually turns on: the online half of the core's effective() --------------------------------------

def effective_online(s, put, eff):
    """Online footage, model prompts, paid generation and online memes, given keys and the network. Every "no" gets a
    reason through put(name, ok, reason); the lists of usable providers go into eff."""
    broll = s.get("use_broll", False)
    online = broll and s.get("use_online_footage")
    keyed = [p for p in s.get("online_footage_providers", []) if FOOTAGE_KEYS.get(p) and api_key(FOOTAGE_KEYS[p])]
    if online and offline():
        put("online_footage", False, "REELS_OFFLINE=1")
    elif online and not keyed:
        put("online_footage", False, "no key for any provider (" +
            ", ".join(FOOTAGE_KEYS.get(p, p) for p in s.get("online_footage_providers", [])) + ")")
    else:
        put("online_footage", online, "off")
    eff["online_footage_providers"] = keyed if eff["online_footage"] else []
    gen = broll and s.get("use_generated_footage")
    engines = s.get("generation_engines") or ["code", "model"]
    put("generated_prompts", gen and "model" in engines, "off" if not gen else "the model engine is not allowed")
    prov = s.get("generation_provider")
    model_ok = gen and "model" in engines
    gen_ready = model_ok and s.get("generate_now") and prov and GEN_KEYS.get(prov) and api_key(GEN_KEYS[prov]) and not offline()
    reason = ("off" if not model_ok else
              "generate_now=false: prompts only" if not s.get("generate_now") else
              "generation_provider is not set" if not prov else
              f"no key {GEN_KEYS.get(prov, prov)}" if not api_key(GEN_KEYS.get(prov, "")) else
              "REELS_OFFLINE=1" if offline() else "off")
    put("generate_now", gen_ready, reason)
    memes = eff.get("memes")  # the core has already applied the brand tone's meme ban
    mo = memes and s.get("use_online_memes")
    mkeyed = [p for p in s.get("online_meme_providers", []) if p in MEME_KEYS and (MEME_KEYS[p] is None or api_key(MEME_KEYS[p]))]
    if mo and offline():
        put("online_memes", False, "REELS_OFFLINE=1")
    elif mo and not mkeyed:
        put("online_memes", False, "no key (" + ", ".join(str(MEME_KEYS.get(p) or p) for p in s.get("online_meme_providers", [])) + ")")
    else:
        put("online_memes", mo, "off")
    eff["online_meme_providers"] = mkeyed if eff["online_memes"] else []


# --- Safe error text: API keys never reach the output or JSON ---------------------------------------------------
SECRET_ENVS = ["PIXABAY_API_KEY", "PEXELS_API_KEY", "MAGNIFIC_API_KEY", "FREEPIK_API_KEY", "COVERR_API_KEY", "FAL_KEY",
               "GIPHY_API_KEY", "REPLICATE_API_TOKEN", "GEMINI_API_KEY", "OPENAI_API_KEY", "RUNWAYML_API_SECRET"]
_SECRET_RES = [
    (re.compile(r"(?i)([?&;](?:api[_-]?key|key|token|access[_-]?token|sig|signature)=)[^&\s'\"#]+"), r"\1***"),
    (re.compile(r"(?i)\b(authorization|x-[\w-]*api-key|x-api-key|api[_-]?key)(['\"]?\s*[:=]\s*['\"]?)"
                r"(?:(?:key|bearer|token|basic)\s+)?[^\s'\",}]+"), r"\1\2***"),
    (re.compile(r"(?i)\b(key|bearer)\s+[A-Za-z0-9_\-:.]{16,}"), r"\1 ***"),
]


def _secret_values():
    try:
        file_keys = _load_keys()
    except Exception:
        file_keys = {}
    names = set(SECRET_ENVS) | {k for k in list(os.environ) + list(file_keys) if re.search(r"KEY|TOKEN|SECRET", k, re.I)}
    vals = set()
    for n in names:
        for v in (os.environ.get(n), file_keys.get(n)):
            if not v:
                continue
            for x in {v, v.strip(), repr(v)[1:-1], *v.splitlines()}:
                if len(x.strip()) >= 6:
                    vals.add(x.strip())
    return sorted(vals, key=len, reverse=True)


def scrub(text):
    """Remove key values (environment and the keys file), authorization headers and key=/token= in URLs from text."""
    t = str(text)
    for v in _secret_values():
        t = t.replace(v, "***")
    for rx, sub in _SECRET_RES:
        t = rx.sub(sub, t)
    return t


def err_text(ex, limit=160):
    """An error for output and JSON: type + text without secrets (masked first, then cut)."""
    return f"{type(ex).__name__}: {scrub(ex)[:limit]}"


# --- Network ----------------------------------------------------------------------------------------------------

class Offline(RuntimeError):
    pass


def ensure_online():
    if offline():
        raise Offline("REELS_OFFLINE=1: network access is off")


MAX_JSON = 20 << 20
SECRET_HEADERS = {"authorization", "x-api-key", "x-key", "key"}
SECRET_QUERY = {"key", "api_key", "apikey", "api-key", "x-api-key", "x-key", "token", "access_token", "authorization"}


def checked_url(url, allowed=None):
    u = urllib.parse.urlsplit(str(url))
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("only HTTPS URLs without embedded credentials are allowed")
    if allowed and not allowed(url):
        raise ValueError("URL host is outside the allow-list")
    return u


def origin(u):
    return u.scheme, u.hostname.lower(), u.port or 443


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Validate every hop and remove credentials when the origin changes."""
    def __init__(self, allowed=None):
        self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = checked_url(req.full_url, self.allowed)
        new = checked_url(newurl, self.allowed)
        changed = origin(old) != origin(new)
        if changed:
            query = [(k, v) for k, v in urllib.parse.parse_qsl(new.query, keep_blank_values=True)
                     if k.lower() not in SECRET_QUERY]
            newurl = urllib.parse.urlunsplit(new._replace(query=urllib.parse.urlencode(query)))
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if changed and redirected is not None:
            for store in (redirected.headers, redirected.unredirected_hdrs):
                for k in list(store):
                    if k.lower() in SECRET_HEADERS:
                        del store[k]
        return redirected


def open_url(req, timeout, allowed=None):
    ensure_online()
    checked_url(req.full_url, allowed)
    return urllib.request.build_opener(SafeRedirect(allowed)).open(req, timeout=timeout)


def read_json_response(response):
    raw = response.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError("JSON response exceeds 20 MB")
    return json.loads(raw.decode("utf-8"))


@contextlib.contextmanager
def file_lock(path, timeout=30):
    """Standalone cross-process lock; abandoned locks require manual removal."""
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() - started > timeout:
                raise TimeoutError(f"busy file: {path}; remove {lock} only if its owner has stopped")
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.unlink()


def http_json(url, headers=None, timeout=15, cache_hours=0):
    checked_url(url)
    key = hashlib.sha1((url + json.dumps(headers or {}, sort_keys=True)).encode()).hexdigest()
    cf = CACHE / "http" / f"{key}.json"
    if cache_hours and cf.exists() and time.time() - cf.stat().st_mtime < cache_hours * 3600:
        return json.loads(cf.read_text(encoding="utf-8"))
    ensure_online()  # the cache is not the network; everything else only when the network is allowed
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with open_url(req, timeout) as r:
        data = read_json_response(r)
    if cache_hours:
        cf.parent.mkdir(parents=True, exist_ok=True)
        _write_json(cf, data)
    return data


def download(url, dest, headers=None, timeout=60):
    ensure_online()
    checked_url(url)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.{uuid.uuid4().hex}.part")
    try:
        with open_url(req, timeout) as r, open(tmp, "xb") as f:
            total = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DL_MB << 20:
                    raise RuntimeError(f"the file is larger than {MAX_DL_MB} MB: stopped")
                f.write(chunk)
        with file_lock(dest):
            tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink()
    return dest


def footage_providers():
    """Online stock footage sources (stock.py) for the core's footage.py PROVIDERS."""
    import stock
    return list(stock.PROVIDERS)


# --- Color in words (for video model prompts: they don't understand HEX) ----------------------------------------

def color_name(h):
    import colorsys
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hu, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.12 or l < 0.06 or l > 0.95:
        return "black" if l < 0.15 else "white" if l > 0.85 else "dark gray" if l < 0.4 else "light gray" if l > 0.7 else "gray"
    deg = hu * 360
    names = [(15, "red"), (40, "orange"), (65, "yellow"), (150, "green"), (195, "teal"), (225, "blue"), (260, "indigo"),
             (290, "purple"), (335, "pink"), (360, "red")]
    name = next(n for d, n in names if deg <= d)
    if name == "blue" and l < 0.25:
        name = "navy blue"
    if s < 0.4 and l > 0.55 and name in ("orange", "yellow", "red"):
        return "sand beige"
    if s < 0.35:
        return "muted " + name
    pre = "deep " if l < 0.25 and name != "navy blue" else "pale " if l > 0.8 else "bright " if s > 0.85 and l > 0.45 else ""
    return pre + name


# --- link / unlink: standalone, standard library only -----------------------------------------------------------

def _read_json(f):
    try:
        return json.loads(Path(f).read_text(encoding="utf-8"))
    except ValueError as ex:
        sys.exit(f"{f}: not valid JSON ({ex}); fix it by hand first")


def _write_json(f, obj):
    tmp = f.with_name(f".{f.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, f)
    finally:
        if tmp.exists():
            tmp.unlink()


def find_project(arg=None):
    """The project folder, found the way the core's project_root() finds it: REELS_PROJECT; else --project; else
    project_root from it-reelsmaker.json in the current folder or above; else the nearest folder upwards with edit/ or
    brands/; else the current folder."""
    env = os.environ.get("REELS_PROJECT")
    if env:
        if arg and Path(arg).resolve() != Path(env).resolve():
            print(f"note: REELS_PROJECT is set, so the core uses {Path(env).resolve()}; --project {arg} is ignored")
        return Path(env).resolve()
    if arg:
        return Path(arg).resolve()
    p = Path.cwd().resolve()
    for q in [p, *p.parents]:
        f = q / SETTINGS_FILE
        if f.is_file():
            root = (_read_json(f) or {}).get("project_root")
            if root and not str(root).startswith("${"):
                return (q / root).resolve()
            break
    for q in [p, *p.parents]:
        if (q / "edit").is_dir() or (q / "brands").is_dir():
            return q
    return p


def _settings(a):
    project = find_project(a.project)
    if not project.is_dir():
        sys.exit(f"no such project folder: {project}")
    f = project / SETTINGS_FILE
    doc = _read_json(f) if f.is_file() else {}
    if not isinstance(doc, dict):
        sys.exit(f"{f}: expected a JSON object; fix it by hand first")
    return f, doc


def cmd_link(a):
    f, _ = _settings(a)
    with file_lock(f):
        doc = _read_json(f) if f.exists() else {}
        doc["online_scripts"] = str(HERE)
        _write_json(f, doc)
    print(f"{f}: online_scripts = {HERE}")
    print("Run link again after each add-on update: the add-on folder path contains its version.")
    env = os.environ.get("REELS_ONLINE_SCRIPTS")
    if env and Path(env).resolve() != HERE:
        print(f"note: REELS_ONLINE_SCRIPTS={env} is set and takes precedence over this link")


def cmd_unlink(a):
    f, _ = _settings(a)
    with file_lock(f):
        doc = _read_json(f) if f.exists() else {}
        if "online_scripts" not in doc:
            print(f"{f}: the add-on was not linked")
            return
        doc.pop("online_scripts")
        _write_json(f, doc)
    print(f"{f}: online_scripts removed; the core now works without online sources")


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="reels_online.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, what in (("link", cmd_link, "write online_scripts (this folder) into <project>/it-reelsmaker.json"),
                           ("unlink", cmd_unlink, "remove online_scripts from <project>/it-reelsmaker.json")):
        p = sub.add_parser(name, help=what)
        p.add_argument("--project", help="the project folder (default: found from the current folder)")
        p.set_defaults(fn=fn)
    kp = sub.add_parser("keys", help="API keys in the keys file: list, set (hidden input), remove")
    ks = kp.add_subparsers(dest="keys_cmd", required=True)
    ks.add_parser("list", help="which keys are set; values are masked").set_defaults(fn=cmd_keys_list)
    for name, fn, what in (("set", cmd_keys_set, "type a key with hidden input (run it in your own terminal)"),
                           ("remove", cmd_keys_remove, "delete a key from the keys file")):
        q = ks.add_parser(name, help=what)
        q.add_argument("name", help="the key name, like PEXELS_API_KEY or FAL_KEY")
        q.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
