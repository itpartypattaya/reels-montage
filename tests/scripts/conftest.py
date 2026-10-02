"""Shared fixtures for the script tests. Every test works on synthetic data in a temporary folder: tiny videos and
sounds made by ffmpeg's lavfi sources, invented transcripts and brands. Nothing here depends on real footage.

Run from the repository root:
    python -m pytest tests/scripts -q
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "plugins" / "it-reelsmaker" / "skills" / "it-reelsmaker" / "scripts"
ADDON = ROOT / "plugins" / "it-reelsmaker-online" / "skills" / "it-reelsmaker-online" / "scripts"
sys.path.insert(0, str(CORE))

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")


def _has(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False


needs_pillow = pytest.mark.skipif(not _has("PIL"), reason="Pillow is not installed")


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An empty editing project (edit/ and brands/) as the current folder, with no add-on and no overlays."""
    root = tmp_path / "proj"
    (root / "edit").mkdir(parents=True)
    (root / "brands").mkdir()
    monkeypatch.chdir(root)
    for var in ("REELS_PROJECT", "REELS_ONLINE_SCRIPTS", "REELS_DEFAULTS_OVERLAY", "REELS_FACE_MODEL", "REELS_OFFLINE"):
        monkeypatch.delenv(var, raising=False)
    import reels_common
    monkeypatch.setattr(reels_common, "_ONLINE", None)
    return root


def run_script(name, *args, cwd=None, env=None, check=True, scripts=CORE):
    """Run a script as the user would: a fresh Python process, UTF-8 output."""
    e = {k: v for k, v in os.environ.items() if not k.startswith("REELS_")}
    e.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}, **(env or {}))
    r = subprocess.run([sys.executable, str(scripts / name), *map(str, args)], cwd=cwd, env=e,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise AssertionError(f"{name} {' '.join(map(str, args))} -> {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def make_video(path, w=720, h=1280, dur=6.0, audio=True, color=None):
    """A test-pattern video (or a flat color), optionally with a 440 Hz tone."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    src = f"color=c={color}:size={w}x{h}:rate=30:duration={dur}" if color else f"testsrc2=size={w}x{h}:rate=30:duration={dur}"
    args = ["-f", "lavfi", "-i", src]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", "-c:a", "aac", "-shortest"]
    ffmpeg(*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", path)
    return path


def make_speech(path, bursts, dur, rate=16000):
    """A WAV with tone bursts standing in for phrases: bursts = [(start, end), ...] in seconds."""
    on = "+".join(f"between(t,{a},{b})" for a, b in bursts)
    ffmpeg("-f", "lavfi", "-i", f"sine=f=300:d={dur},volume='if({on},1,0)':eval=frame", "-ar", rate, path)
    return path


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def probe_streams(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,start_time,duration",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return {s["codec_type"]: s for s in json.loads(r.stdout)["streams"]}
