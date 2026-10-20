"""The Remotion kit: a starter project for new users and updates of the kit in an existing project.

  python scripts/kit.py new reels                # a new Remotion project in ./reels with the kit wired in
  python scripts/kit.py check --remotion reels   # is the kit there, which version, which files differ
  python scripts/kit.py update --remotion reels  # copy the plugin's kit over the project's copy (backup first)
  python scripts/kit.py render edit/4821 [--concurrency 2] [--out out/4821.mp4]   # the full render (SKILL.md step 9)
  python scripts/kit.py still edit/4821 --frame 120 [--comp ReelCover]             # one frame
  python scripts/kit.py clean-temp [--yes]       # old Remotion temp folders: listed; --yes removes them

render and still run Remotion in the Remotion project (it-reelsmaker.json -> remotion_dir, or --remotion) with the
video's props (edit/<id>/reelkit-props.json), each with a temp folder of its own that is removed when the run ends:
Remotion leaves its bundle (a full copy of public/), asset cache and Chrome profile in the system temp folder on
Windows (a real laptop: 571 folders, 33.5 GB in a month). A ReelKit / ReelCover run also reads a public/ of hard links
to only this video's files (--public-dir), not a copy of every video in public/. render writes the whole Remotion
output to edit/<id>/render.log, shows the progress, and fails (exit 1, edit/<id>/render.json "ok": false) unless the
exit code is 0 and the file is new and plays. A render that fails with Remotion's "No frame found at position" runs
once more by itself (says so; both attempts stay in render.log and in render.json "attempts"); any other failure is
not retried. "temp_cleanup": false in it-reelsmaker.json keeps Remotion's own ways.

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
import argparse, fnmatch, json, os, re, shlex, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (REMOTION_LEFTOVERS, SETTINGS_FILE, SKILL, edit_dir, editing_json, is_project, probe,
                          project_root, remotion_leftovers, remotion_tmp, remove_tree, save_json, sweep_tmp, tmp_root,
                          utf8_stdio)

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


PROGRESS_RE = re.compile(r"\b(Rendered|Encoded|Stitched)\b\D{0,12}(\d+)\s*/\s*(\d+)")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def npx():
    return shutil.which("npx") or shutil.which("npx.cmd") or "npx"


def run_logged(cmd, rem, env, log, mode="w"):
    """Run a Remotion command: every line into the log, on the screen only errors, warnings and the progress in steps
    of 20 %. mode "a" adds to the log (a second attempt). -> the exit code."""
    shown = {}
    with open(log, mode, encoding="utf-8", errors="replace") as f:
        p = subprocess.Popen(cmd, cwd=rem, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace")
        for line in p.stdout:  # universal newlines: a "\r" progress update counts as a line too
            f.write(line if line.endswith("\n") else line + "\n")
            plain = ANSI_RE.sub("", line).strip()
            m = PROGRESS_RE.search(plain)
            if m:
                k, n = int(m.group(2)), int(m.group(3))
                step = 5 * k // n if n else 0
                if shown.get(m.group(1)) != step:
                    shown[m.group(1)] = step
                    print(f"  {m.group(1).lower()} {k}/{n}", flush=True)
            elif plain and re.search(r"\b(error|warn\w*|fail\w*)\b", plain, re.I):
                print("  " + plain[:300], flush=True)
        return p.wait()


def log_tail(log, n=15):
    try:
        lines = [ANSI_RE.sub("", l).rstrip() for l in Path(log).read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return ""
    keep = [l for l in lines if l.strip() and not re.match(r"\s*(at |\d+: )", l)]
    return "\n".join(keep[-n:])


RETRY_ON = "No frame found at position"
RETRIES = 1  # extra attempts after a RETRY_ON failure
ATTEMPT_MARK = "===== kit.py: attempt"  # the line render.log gets before each further attempt


def retry_reason(log):
    """The line of the last attempt in the log that names RETRY_ON, or None: a render that failed with it is run once
    more by itself. Seen once on an 8 GB laptop (2026-10-20, a 34-min talk's clip): the same command passed when run
    again by hand; the cause is not known. Any other failure is not retried."""
    try:
        txt = Path(log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    parts = txt.split(ATTEMPT_MARK)
    # after a mark, its own line's rest is not the attempt's output (Codex review: it named the error and was taken for it)
    last = parts[-1].splitlines()[1:] if len(parts) > 1 else parts[-1].splitlines()
    line = next((ANSI_RE.sub("", l).strip() for l in last if RETRY_ON in l), None)
    return line[:200] if line else None


def cmd_render(a, still=False):
    """The full render (or one still) of a video with its props, through remotion_tmp(): the run's temp files are
    removed when it ends, and a ReelKit / ReelCover run reads a public/ of only this video's files. The render counts
    only with exit code 0 AND a new, non-empty file (SKILL.md step 9: a render | tail chain hid a failure, and the
    master was silently built from the old file)."""
    from board import props_path, remotion_dir  # noqa: E402 (board imports visual_plan's neighbors only when needed)
    e = edit_dir(a.edit)
    rem = remotion_dir(a.remotion)
    props = props_path(e, a.props)
    if still:
        out = Path(a.out).resolve() if a.out else e / "verify" / f"still-{a.comp}-{a.frame}.png"
        cmd = [npx(), "--no", "remotion", "still", a.comp, str(out), f"--props={props}", f"--frame={a.frame}"]
    else:
        out = Path(a.out).resolve() if a.out else rem / "out" / f"{e.name}.mp4"
        cmd = [npx(), "--no", "remotion", "render", a.comp, str(out), f"--props={props}"]
        if a.concurrency:
            cmd.append(f"--concurrency={a.concurrency}")
        if a.frames:
            cmd.append(f"--frames={a.frames}")
    cmd += shlex.split(a.extra or "")
    out.parent.mkdir(parents=True, exist_ok=True)
    log = e / ("still.log" if still else "render.log")
    t0 = time.time()
    attempts = []
    while True:
        t1 = time.time()
        try:
            with remotion_tmp(rem, props, a.comp) as (env, extra):
                code = run_logged(cmd + extra, rem, env, log, "a" if attempts else "w")
        except OSError as x:
            sys.exit(f"cannot run npx ({x}): Node.js with Remotion is needed (doctor.py)")
        why = retry_reason(log) if code != 0 and not still else None
        attempts.append({"code": code, "seconds": round(time.time() - t1, 1), **({"error": why} if why else {})})
        if not why or len(attempts) > RETRIES:
            break
        print(f"  the render failed with Remotion's \"{RETRY_ON}\" ({why}): a rerun of the same command passed before, "
              f"so it runs once more by itself (both attempts stay in {log.name})", flush=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"\n{ATTEMPT_MARK} {len(attempts) + 1} (the one before failed with Remotion's frame error) =====\n")
    fresh = out.is_file() and out.stat().st_mtime >= t0 - 1 and out.stat().st_size > 0
    took = time.time() - t0
    if still:
        if code != 0 or not fresh:
            sys.exit(f"the still failed (code {code}); log {log}:\n{log_tail(log)}")
        print(f"still: {out} (frame {a.frame}, {took:.0f} s)")
        return 0
    dur = probe(out).get("dur") if fresh else None
    save_json(e / "render.json", {"out": str(out), "comp": a.comp, "props": str(props), "ok": bool(code == 0 and dur),
                                  "code": code, "seconds": round(took, 1), "duration": dur, "attempts": attempts,
                                  "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    if code != 0 or not fresh or not dur:
        why = f"code {code}" + ("" if fresh else (", the file is from an earlier render" if out.exists() else ", no file"))
        sys.exit(f"the render failed ({why}); do not master it. Log {log}:\n{log_tail(log)}")
    print(f"render: {out} — {dur:.2f} s of video, {out.stat().st_size / (1 << 20):.1f} MB, in {took / 60:.1f} min "
          f"(log {log.name})")
    return 0


def cmd_clean_temp(a):
    """Old Remotion temp folders: this plugin's own run folders (always), and folders that runs outside the plugin
    left in the system temp folder (listed; removed with --yes)."""
    freed = sweep_tmp()
    if freed:
        print(f"removed {freed / (1 << 20):.0f} MB of this plugin's old run folders ({tmp_root()})")
    left = remotion_leftovers(a.hours)
    base = tempfile.gettempdir()
    if not left:
        print(f"no Remotion leftovers older than {a.hours:g} h in {base}")
        return 0
    total = sum(n for _, n in left)
    kinds = {}
    for q, _ in left:
        k = next((p for p in REMOTION_LEFTOVERS if fnmatch.fnmatch(q.name, p)), q.name)
        kinds[k] = kinds.get(k, 0) + 1
    print(f"{len(left)} folder(s), {total / (1 << 20):.0f} MB left by Remotion runs in {base}, unchanged for over "
          f"{a.hours:g} h: " + ", ".join(f"{k} × {n}" for k, n in sorted(kinds.items())))
    if not a.yes:
        print("remove them: kit.py clean-temp --yes (puppeteer_dev_chrome_profile-* folders can also belong to another "
              "program that drives Chrome: close it first; runs through this plugin remove their own files)")
        return 0
    gone, held, nbytes = 0, 0, 0
    for q, n in left:
        if remove_tree(q, wait=1):
            gone, nbytes = gone + 1, nbytes + n
        else:
            held += 1
    print(f"removed {gone} folder(s), {nbytes / (1 << 20):.0f} MB" + (f"; {held} still in use, left" if held else ""))
    return 0


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="a new Remotion project with the kit"); p.add_argument("dir"); p.add_argument("--name")
    p = sub.add_parser("check", help="compare the project's kit with the plugin's"); p.add_argument("--remotion", required=True)
    p = sub.add_parser("update", help="copy the plugin's kit into the project")
    p.add_argument("--remotion", required=True); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="also when the project's kit is newer (rolls it back)")
    for name in ("render", "still"):
        p = sub.add_parser(name, help="the full render of a video" if name == "render" else "one frame of a video")
        p.add_argument("edit"); p.add_argument("--remotion", help="default: it-reelsmaker.json -> remotion_dir")
        p.add_argument("--props", help="default: edit/<id>/reelkit-props.json")
        p.add_argument("--comp", default="ReelKit", help="ReelKit (default), ReelCover, or Reel<id>")
        p.add_argument("--out", help="render: default <remotion>/out/<id>.mp4; still: edit/<id>/verify/still-<comp>-<frame>.png")
        p.add_argument("--extra", help="more Remotion flags, quoted: \"--scale=0.5 --log=verbose\"")
        if name == "render":
            p.add_argument("--concurrency", type=int, help="Remotion's threads (1-2 on an 8 GB laptop with other apps open)")
            p.add_argument("--frames", help="a range of frames, A-B")
        else:
            p.add_argument("--frame", type=int, required=True)
    p = sub.add_parser("clean-temp", help="old Remotion temp folders: list them, --yes removes them")
    p.add_argument("--hours", type=float, default=24.0, help="only folders unchanged for this long (default 24)")
    p.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "still":
        return cmd_render(a, still=True)
    return {"new": cmd_new, "check": cmd_check, "update": cmd_update, "render": cmd_render,
            "clean-temp": cmd_clean_temp}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
