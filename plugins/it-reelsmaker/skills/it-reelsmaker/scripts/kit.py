"""The Remotion kit: a starter project for new users and updates of the kit in an existing project.

  python scripts/kit.py new reels                # a new Remotion project in ./reels with the kit wired in
  python scripts/kit.py check --remotion reels   # is the kit there, which version, which files differ
  python scripts/kit.py update --remotion reels  # copy the plugin's kit over the project's copy (backup first)

What the kit is: src/ReelKit.tsx (the ReelKit and ReelCover compositions: the rough cut, subtitles, brand, inserts,
designed scenes, all from props written by `visual_plan.py export --props`) and src/kit/ (its components). The
starter project adds package.json with pinned versions (all @remotion/* packages at the same version as remotion),
tsconfig.json, remotion.config.ts, src/index.ts, src/Root.tsx (ReelKit, ReelCover and the code scenes from
src/gen/registry.ts), and empty src/brands/, src/plans/, public/.

The script never runs npm and never touches the network: after `new` it prints the install command. `update`
replaces only the kit's own files (src/ReelKit.tsx, src/kit/**); Root.tsx, src/gen/, brands, plans and public/ stay
yours. Files it replaces are copied to .kit-backup/<time>/ first. With a project folder (edit/, brands/ or
it-reelsmaker.json), `new` writes remotion_dir into it-reelsmaker.json unless it is already set.
"""
import argparse, json, os, re, shutil, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import SETTINGS_FILE, SKILL, editing_json, is_project, project_root, utf8_stdio

KIT = SKILL / "assets" / "remotion-kit"
STARTER = SKILL / "assets" / "remotion-starter"
KIT_FILES = ("ReelKit.tsx", "kit")  # replaced by update; everything else in the project belongs to the person
VERSION_RE = re.compile(r'KIT_VERSION\s*=\s*"([^"]+)"')
TEXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".json", ".css", ".md", ".txt"}
HERE = Path(__file__).resolve().parent


def script_cmd(name):
    """How to run a script of this folder from anywhere: hints are run from the project folder, where a relative
    `scripts/<name>` does not exist. The interpreter's name and the script's real path, quoted."""
    py = "python" if os.name == "nt" else (Path(sys.executable).name or "python3")
    return f'{py} "{HERE / name}"'


def content(p):
    """File bytes; text files with LF line endings, so a CRLF copy (a Windows checkout with autocrlf) is the same file."""
    b = Path(p).read_bytes()
    return b.replace(b"\r\n", b"\n") if Path(p).suffix.lower() in TEXT else b


def put(src, dst):
    """Copy a plugin file into the project, text with LF line endings."""
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_bytes(content(src))


def kit_version(root):
    f = Path(root) / "kit" / "version.ts"
    m = VERSION_RE.search(f.read_text(encoding="utf-8")) if f.is_file() else None
    return m.group(1) if m else None


def newer(a, b):
    """Version a is newer than b (numbers part by part: 1.10.0 > 1.9.0); unknown versions compare as not newer."""
    try:
        return tuple(int(x) for x in str(a).split(".")) > tuple(int(x) for x in str(b).split("."))
    except ValueError:
        return False


def kit_files(root):
    """Relative paths of the kit's own files under root (src/ of a project, or the plugin's kit folder)."""
    root = Path(root)
    out = []
    for name in KIT_FILES:
        p = root / name
        if p.is_file():
            out.append(Path(name))
        elif p.is_dir():
            out += sorted(q.relative_to(root) for q in p.rglob("*") if q.is_file())
    return out


def outside_plugin(p):
    plugin = os.path.normcase(str(SKILL.parents[1]))
    try:
        within = os.path.commonpath([plugin, os.path.normcase(str(p))]) == plugin
    except ValueError:  # different drives
        within = False
    if within:
        sys.exit(f"{p} is inside the plugin folder (it is replaced on every update); use a folder of your own")
    return p


def remotion_project(arg):
    rem = outside_plugin(Path(arg).resolve())
    if not (rem / "package.json").is_file() or not (rem / "src").is_dir():
        sys.exit(f"not a Remotion project (no package.json or src/): {rem}; a new one: kit.py new <folder>")
    return rem


def diff(rem):
    """(missing, changed, extra) kit files of the project against the plugin's kit."""
    src = rem / "src"
    ours, theirs = set(kit_files(KIT)), set(kit_files(src))
    missing = sorted(ours - theirs)
    changed = sorted(p for p in ours & theirs if content(KIT / p) != content(src / p))  # line endings don't count
    extra = sorted(theirs - ours)
    return missing, changed, extra


def copy_kit(dst_src, files):
    for p in files:
        put(KIT / p, dst_src / p)


def remember(rem):
    """Write remotion_dir into the project's it-reelsmaker.json (only inside an editing project, only if unset)."""
    project = project_root()
    if not is_project(project):
        return
    with editing_json(project / SETTINGS_FILE, {}) as s:
        cur = s.get("remotion_dir")
        if cur and not str(cur).startswith("${"):
            if Path(project / cur).resolve() != rem:
                print(f"{SETTINGS_FILE}: remotion_dir stays {cur} (already set)")
            return
        try:
            value = rem.relative_to(project).as_posix()
        except ValueError:
            value = str(rem)
        s["remotion_dir"] = value
    print(f"{project / SETTINGS_FILE}: remotion_dir = {value}")


def cmd_new(a):
    rem = outside_plugin(Path(a.dir).resolve())
    if rem.exists() and (not rem.is_dir() or any(rem.iterdir())):
        sys.exit(f"{rem} exists and is not empty; for an existing Remotion project use kit.py update --remotion {a.dir}")
    name = re.sub(r"[^a-z0-9-]+", "-", (a.name or rem.name).lower()).strip("-") or "reels"
    for f in sorted(STARTER.rglob("*")):
        if f.is_file():
            r = f.relative_to(STARTER)
            d = rem / (".gitignore" if r.as_posix() == "gitignore.txt" else r)
            d.parent.mkdir(parents=True, exist_ok=True)
            if r.as_posix() == "package.json":
                pkg = json.loads(f.read_text(encoding="utf-8"))
                pkg["name"] = name
                d.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")
            else:
                put(f, d)
    copy_kit(rem / "src", kit_files(KIT))
    put(KIT / "gen" / "registry.ts", rem / "src" / "gen" / "registry.ts")
    for d in ("src/brands", "src/plans", "public"):
        (rem / d).mkdir(parents=True, exist_ok=True)
    print(f"created the Remotion project {rem} (kit {kit_version(KIT)})")
    remember(rem)
    print("next (downloads the packages from npm, ~300 MB; the first render also downloads Remotion's headless "
          f"browser):\n  cd \"{rem}\" && npm install\nthen check: {script_cmd('doctor.py')} --remotion \"{rem}\"")


def cmd_check(a):
    rem = remotion_project(a.remotion)
    missing, changed, extra = diff(rem)
    have, ship = kit_version(rem / "src"), kit_version(KIT)
    if not (rem / "src" / "ReelKit.tsx").is_file():
        print(f"no kit in {rem}: {script_cmd('kit.py')} update --remotion \"{rem}\" copies it")
        return 1
    print(f"kit in the project: {have or 'unknown version'}; in the plugin: {ship}")
    if newer(have, ship):
        # an older copy of the plugin (a catalog sync not yet updated) must not suggest rolling the project back
        print("the project's kit is newer than this plugin's: update the plugin; kit.py update would roll the kit back")
        return 0
    for label, files in (("missing", missing), ("differs", changed), ("not in the plugin's kit", extra)):
        for p in files:
            print(f"  {label}: src/{p.as_posix()}")
    cache_hint(rem)
    if missing or changed:
        print(f"update: {script_cmd('kit.py')} update --remotion \"{rem}\" (replaced files are backed up first)")
        return 1
    print("the kit matches the plugin")
    return 0


CACHE_LINE = "Config.setOffthreadVideoCacheSizeInBytes(384 * 1024 * 1024);"


def cache_hint(rem):
    """A project without a fixed video cache: Remotion sizes it from the RAM free at the start, and with little free
    it shrinks to a few MB and the render fails with "No frame found at position N" (a real 8 GB laptop case)."""
    cfg = Path(rem) / "remotion.config.ts"
    text = cfg.read_text(encoding="utf-8", errors="replace") if cfg.is_file() else ""
    if "setOffthreadVideoCacheSizeInBytes" not in text:
        print(f"note: {cfg.name} sets no video cache size; with little free RAM the render can fail with \"No frame "
              f"found at position N\". Add: {CACHE_LINE}")


def cmd_update(a):
    rem = remotion_project(a.remotion)
    have, ship = kit_version(rem / "src"), kit_version(KIT)
    if newer(have, ship) and not a.force:
        sys.exit(f"the kit in {rem} ({have}) is newer than this plugin's ({ship}): update the plugin instead; "
                 "--force rolls the kit back (replaced files are backed up first)")
    missing, changed, extra = diff(rem)
    if not missing and not changed:
        print(f"the kit in {rem} already matches the plugin ({kit_version(KIT)})")
        return
    for p in missing:
        print(f"  add: src/{p.as_posix()}")
    for p in changed:
        print(f"  replace: src/{p.as_posix()}")
    if a.dry_run:
        print("dry run: nothing written")
        return
    if changed:
        bak = rem / ".kit-backup" / time.strftime("%Y%m%d-%H%M%S")
        for p in changed:
            d = bak / "src" / p
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(rem / "src" / p, d)
        print(f"backup of the replaced files: {bak}")
    copy_kit(rem / "src", missing + changed)
    if not (rem / "src" / "gen" / "registry.ts").exists():
        put(KIT / "gen" / "registry.ts", rem / "src" / "gen" / "registry.ts")
        print("  add: src/gen/registry.ts")
    for p in extra:
        print(f"  left as is (not in the plugin's kit): src/{p.as_posix()}")
    root = rem / "src" / "Root.tsx"
    if not root.is_file() or "ReelKit" not in root.read_text(encoding="utf-8", errors="replace"):
        print(f"src/Root.tsx does not register ReelKit yet: see {STARTER / 'src' / 'Root.tsx'} for the compositions")
    print(f"kit {kit_version(KIT)} is in {rem}; check the types: npx tsc (in that folder)")


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="a new Remotion project with the kit"); p.add_argument("dir"); p.add_argument("--name")
    p = sub.add_parser("check", help="compare the project's kit with the plugin's"); p.add_argument("--remotion", required=True)
    p = sub.add_parser("update", help="copy the plugin's kit into the project")
    p.add_argument("--remotion", required=True); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="also when the project's kit is newer (rolls it back)")
    a = ap.parse_args(argv)
    return {"new": cmd_new, "check": cmd_check, "update": cmd_update}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
