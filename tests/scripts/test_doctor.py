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
    pinned = names["@remotion/* = remotion version"]
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
