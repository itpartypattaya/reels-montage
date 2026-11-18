"""doctor.py: one report of the environment; exit code 1 only when a required program is missing."""
import json

from conftest import HAS_FFMPEG, run_script, write_json


def test_report_lists_every_check_and_reads_the_remotion_project(project):
    rem = project / "reels"
    write_json(rem / "package.json", {"dependencies": {"remotion": "4.0.100", "@remotion/cli": "^4.0.99"}})
    write_json(project / "it-reelsmaker.json", {"remotion_dir": "reels"})
    r = run_script("doctor.py", "--json", cwd=project, check=False)
    doc = json.loads(r.stdout)
    names = {c["name"]: c for c in doc["checks"]}
    for n in ("Python 3.9+", "ffmpeg", "Pillow", "Node.js 18+", "Remotion project", "YuNet face model", "rembg (matte.py)"):
        assert n in names, n
    pinned = names["@remotion packages = remotion version"]
    assert not pinned["ok"] and "@remotion/cli" in pinned["found"]  # a caret range and a different version
    assert (r.returncode == 0) == doc["ok"] == HAS_FFMPEG


def test_fix_hints_name_the_real_script_paths(project):
    """The hints are run from the project folder, where a relative `python scripts/kit.py` does not exist."""
    import re
    from pathlib import Path
    r = run_script("doctor.py", "--json", cwd=project, check=False)
    fixes = " ".join(c["fix"] for c in json.loads(r.stdout)["checks"])
    paths = re.findall(r'"([^"]+\.py)"', fixes)
    assert any(Path(p).name == "kit.py" for p in paths), fixes  # no Remotion project: "kit.py new" is offered
    assert paths and all(Path(p).is_absolute() and Path(p).is_file() for p in paths), paths
    assert "python scripts/" not in fixes


def test_a_passing_check_is_remembered_for_this_version(project):
    # wave 2: doctor ran in every session; a pass is kept in it-reelsmaker.json -> doctor_ok, so the skill runs it again
    # only after an update or a tool error
    write_json(project / "it-reelsmaker.json", {"remotion_dir": "reels"})
    r = run_script("doctor.py", "--json", cwd=project, check=False)
    cfg = json.loads((project / "it-reelsmaker.json").read_text(encoding="utf-8"))
    rows = json.loads(r.stdout)["checks"]
    # review 2026-10-18 (Codex): recorded only when the render environment (recommended rows) is ready too
    if all(c["ok"] for c in rows if c["level"] in ("required", "recommended")):
        from conftest import CORE
        version = json.loads((CORE.parents[2] / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        assert cfg["doctor_ok"]["version"] == version and cfg["remotion_dir"] == "reels"
    else:
        assert "doctor_ok" not in cfg


def fake_ffmpeg(monkeypatch, version, help_text):
    """doctor's view of an ffmpeg on PATH: what the program prints for each question (the program is faked, the
    check is real)."""
    import shutil
    import doctor
    answers = {"-version": f"ffmpeg version {version} Copyright (c) 2000-2022 the FFmpeg developers",
               "-encoders": " V....D libx264  libx264 H.264\n V....D libvpx-vp9  libvpx VP9",
               "-filters": " ... loudnorm  A->A  EBU R128\n ... haldclut  VV->V  Hald CLUT",
               "-h": help_text}
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(doctor, "out", lambda cmd: answers[cmd[2]])
    monkeypatch.setattr(doctor, "rows", [])
    doctor.check_ffmpeg()
    return {r["name"]: r for r in doctor.rows}


def test_an_ffmpeg_without_fps_mode_is_named(monkeypatch):
    # review 2026-11-17 #16: five scripts pass -fps_mode (ffmpeg 5.1+); Ubuntu 22.04 ships 4.4, and doctor said all is fine
    rows = fake_ffmpeg(monkeypatch, "4.4.2-0ubuntu0.22.04.1", "-vsync  video sync method\n-r  set frame rate")
    bad = [r for r in rows.values() if not r["ok"]]
    assert len(bad) == 1 and bad[0]["level"] == "required" and "5.1" in bad[0]["fix"], rows
    rows = fake_ffmpeg(monkeypatch, "N-117000-g1a2b3c", "-fps_mode[:<stream_spec>]  set framerate mode")
    assert all(r["ok"] for r in rows.values()), rows
