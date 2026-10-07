# -*- coding: utf-8 -*-
"""Check the editing environment in one command: what is installed, what is missing, how to install it on this OS.

    python scripts/doctor.py [--remotion reels] [--json]

Required (exit code 1 if missing): Python 3.9+, ffmpeg and ffprobe with libx264 and the loudnorm filter.
Recommended: Pillow (contact sheets, covers, logos), Node.js 18+ and a Remotion project (graphics and render).
Optional, per feature: faster-whisper and its model (transcribe.py), OpenCV and the YuNet face model (faces.py),
rembg and its model (matte.py), libvpx-vp9 in ffmpeg (cut-out figure with alpha).
Nothing is installed or downloaded by this script: it only prints the commands.
The Remotion project comes from --remotion, else it-reelsmaker.json -> remotion_dir.
"""
import argparse, importlib.util, json, os, platform, re, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kit import KIT, kit_version, script_cmd
from reels_common import online, project_root, project_settings, utf8_stdio

OS = {"Windows": "windows", "Darwin": "macos"}.get(platform.system(), "linux")
PY = Path(sys.executable).name if OS != "windows" else "python"
INSTALL = {
    "ffmpeg": {"windows": "winget install Gyan.FFmpeg", "macos": "brew install ffmpeg", "linux": "sudo apt install ffmpeg"},
    "node": {"windows": "winget install OpenJS.NodeJS.LTS", "macos": "brew install node", "linux": "sudo apt install nodejs npm"},
    "pillow": f"{PY} -m pip install Pillow",
    "opencv": f"{PY} -m pip install opencv-python-headless",
    "faster-whisper": f"{PY} -m pip install faster-whisper",
    "whisper-model": f"{PY} -c \"from faster_whisper import download_model; download_model('medium')\"",
    "rembg": f"{PY} -m pip install \"rembg[cpu,cli]\"",
    "rembg-model": "rembg d u2net_human_seg",
    "remotion": f"{script_cmd('kit.py')} new reels (a starter project with the kit), then npm install in that folder",
    "face-model": f"download face_detection_yunet_2023mar.onnx ({script_cmd('faces.py')} --help says where) and set "
                  "face_model in it-reelsmaker.json",
}

rows = []


def add(name, level, ok, found="", fix=""):
    """level: required / recommended / optional."""
    if isinstance(fix, dict):
        fix = fix.get(OS, "")
    rows.append({"name": name, "level": level, "ok": bool(ok), "found": found, "fix": "" if ok else fix})


def out(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        return (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return ""


def has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def check_python():
    v = sys.version_info
    add("Python 3.9+", "required", v >= (3, 9), f"{v.major}.{v.minor}.{v.micro}", "install Python 3.9 or newer from python.org")


def check_ffmpeg():
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    m = re.search(r"ffmpeg version (\S+)", out(["ffmpeg", "-hide_banner", "-version"])) if ff else None
    add("ffmpeg", "required", ff, m.group(1) if m else "", INSTALL["ffmpeg"])
    add("ffprobe", "required", fp, "", INSTALL["ffmpeg"])
    if not ff:
        return
    enc, flt = out(["ffmpeg", "-hide_banner", "-encoders"]), out(["ffmpeg", "-hide_banner", "-filters"])
    add("ffmpeg: libx264", "required", "libx264" in enc, "", "an ffmpeg build with libx264 (the packages above have it)")
    add("ffmpeg: loudnorm, haldclut", "required", "loudnorm" in flt and "haldclut" in flt, "",
        "a full ffmpeg build (the packages above have it)")
    add("ffmpeg: libvpx-vp9 (figure with alpha)", "optional", "libvpx-vp9" in enc, "", "a full ffmpeg build")


def check_python_packages():
    add("Pillow", "recommended", has_module("PIL"), "", INSTALL["pillow"])
    add("OpenCV (faces.py)", "optional", has_module("cv2"), "", INSTALL["opencv"])
    fw = has_module("faster_whisper")
    # the model itself is not looked up: its download cache is where access tokens live too, and the plugin directory
    # holds a plugin that reads that folder for review (1.9.1). transcribe.py loads it from disk only (local_files_only)
    # and stops when it is missing, so the one-time download command is always shown (PR review)
    add("faster-whisper (transcribe.py)", "optional", fw,
        "the model is not checked here; download it once before the first transcript: " + INSTALL["whisper-model"] if fw else "",
        INSTALL["faster-whisper"] + "; then the model, once: " + INSTALL["whisper-model"])


def check_node(remotion):
    node = shutil.which("node")
    v = out(["node", "--version"]).strip() if node else ""
    major = int(re.match(r"v(\d+)", v).group(1)) if re.match(r"v(\d+)", v) else 0
    add("Node.js 18+", "recommended", major >= 18, v, INSTALL["node"])
    if not remotion:
        add("Remotion project", "recommended", False, "not set", "set remotion_dir in it-reelsmaker.json or pass "
            "--remotion; a new one: " + INSTALL["remotion"])
        return
    pkg = Path(remotion) / "package.json"
    try:
        deps = json.loads(pkg.read_text(encoding="utf-8"))
        deps = {**deps.get("dependencies", {}), **deps.get("devDependencies", {})}
    except (OSError, ValueError):
        deps = {}
    ver = deps.get("remotion")
    add("Remotion project", "recommended", ver, f"{remotion} (remotion {ver})" if ver else str(remotion),
        "no remotion in package.json; a new project: " + INSTALL["remotion"])
    if not ver:
        return
    odd = {k: v for k, v in deps.items() if k.startswith("@remotion/") and v.lstrip("^~") != ver.lstrip("^~")}
    add("@remotion/* = remotion version", "recommended", not odd and not ver.startswith(("^", "~")),
        ", ".join(f"{k} {v}" for k, v in odd.items()) or ver,
        f"pin every @remotion/* package to exactly {ver.lstrip('^~')}: npm install --save-exact remotion@{ver.lstrip('^~')} "
        f"@remotion/cli@{ver.lstrip('^~')} ...")
    add("node_modules installed", "recommended", (Path(remotion) / "node_modules" / "remotion").is_dir(), "",
        f"cd {remotion} && npm install")
    have, ship = kit_version(Path(remotion) / "src"), kit_version(KIT)
    add("ReelKit in the project", "recommended", have == ship, f"kit {have or 'not found'}, plugin {ship}",
        f"{script_cmd('kit.py')} update --remotion \"{Path(remotion).resolve()}\" (replaced files are backed up first)")


def check_models(settings):
    fm = os.environ.get("REELS_FACE_MODEL") or settings.get("face_model") or ""
    if str(fm).startswith("${"):
        fm = ""
    p = Path(str(fm)).expanduser() if fm else None
    if p and not p.is_absolute():
        p = project_root() / p
    add("YuNet face model", "optional", p and p.is_file(), str(p) if p else "not set", INSTALL["face-model"])
    rb = shutil.which("rembg")
    add("rembg (matte.py)", "optional", rb, "", INSTALL["rembg"])
    home = Path(os.environ.get("U2NET_HOME") or Path.home() / ".u2net")
    add("rembg model u2net_human_seg", "optional", (home / "u2net_human_seg.onnx").is_file(), str(home), INSTALL["rembg-model"])


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--remotion", help="the Remotion project folder (default: it-reelsmaker.json -> remotion_dir)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    project = project_root()
    settings = project_settings(project)
    remotion = a.remotion or settings.get("remotion_dir")
    if remotion and str(remotion).startswith("${"):
        remotion = None
    if remotion and not Path(remotion).is_absolute():
        remotion = str(project / remotion)
    check_python()
    check_ffmpeg()
    check_python_packages()
    check_node(remotion)
    check_models(settings)
    ext = online()
    add("online add-on (optional)", "optional", ext, str(Path(ext.__file__).parent) if ext else "not linked",
        "only if you want online sources: install it-reelsmaker-online and run its link command")
    missing = [r for r in rows if r["level"] == "required" and not r["ok"]]
    if a.json:
        print(json.dumps({"os": OS, "project": str(project), "checks": rows, "ok": not missing}, ensure_ascii=False, indent=1))
    else:
        print(f"project: {project}   os: {OS}")
        for r in rows:
            mark = "ok  " if r["ok"] else {"required": "MISS", "recommended": "miss", "optional": "--  "}[r["level"]]
            print(f"  {mark} {r['name']:<40} {r['found']}")
            if r["fix"]:
                print(f"       -> {r['fix']}")
        print("required: all present" if not missing else f"required missing: {', '.join(r['name'] for r in missing)}")
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
