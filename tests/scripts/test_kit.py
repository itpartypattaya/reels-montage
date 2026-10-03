"""kit.py: the starter Remotion project and kit updates; no npm, no network."""
import json
import re

import pytest

from conftest import CORE, run_script, write_json

PLUGIN_JSON = CORE.parents[2] / ".claude-plugin" / "plugin.json"
KIT = CORE.parent / "assets" / "remotion-kit"


def lf(b):
    return b.replace(b"\r\n", b"\n")


def test_kit_version_is_not_ahead_of_the_plugin():
    # The kit version changes only when the kit changes (a release without kit changes must not make every project
    # look outdated), so it may lag behind the plugin version, never lead it.
    ship = re.search(r'KIT_VERSION\s*=\s*"([^"]+)"', (KIT / "kit" / "version.ts").read_text(encoding="utf-8")).group(1)
    plugin = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]
    as_tuple = lambda v: tuple(int(x) for x in v.split("."))
    assert as_tuple(ship) <= as_tuple(plugin)


def test_new_creates_a_wired_project_and_remembers_it(project):
    run_script("kit.py", "new", "reels", cwd=project)
    rem = project / "reels"
    for f in ("package.json", "tsconfig.json", "remotion.config.ts", ".gitignore", "src/index.ts", "src/Root.tsx",
              "src/ReelKit.tsx", "src/kit/brand.ts", "src/kit/version.ts", "src/kit/scenes/index.ts", "src/gen/registry.ts"):
        assert (rem / f).is_file(), f
    for d in ("src/brands", "src/plans", "public"):
        assert (rem / d).is_dir(), d
    pkg = json.loads((rem / "package.json").read_text(encoding="utf-8"))
    deps = {**pkg["dependencies"], **pkg["devDependencies"]}
    assert pkg["name"] == "reels"
    assert all(v == deps["remotion"] for k, v in deps.items() if k.startswith("@remotion/"))
    assert not any(v.startswith(("^", "~")) for v in deps.values())
    assert json.loads((project / "it-reelsmaker.json").read_text(encoding="utf-8"))["remotion_dir"] == "reels"
    assert not (rem / "node_modules").exists()
    r = run_script("kit.py", "check", "--remotion", rem, cwd=project)
    assert "matches" in r.stdout


def test_new_refuses_a_non_empty_folder_and_the_plugin_folder(project):
    (project / "reels").mkdir()
    (project / "reels" / "x.txt").write_text("mine")
    r = run_script("kit.py", "new", "reels", cwd=project, check=False)
    assert r.returncode != 0 and "not empty" in r.stderr
    r = run_script("kit.py", "new", CORE.parent / "tmp-starter", cwd=project, check=False)
    assert r.returncode != 0 and "inside the plugin" in r.stderr
    assert not (CORE.parent / "tmp-starter").exists()


def test_update_backs_up_and_keeps_the_persons_files(project):
    run_script("kit.py", "new", "reels", cwd=project)
    rem = project / "reels"
    (rem / "src" / "kit" / "brand.ts").write_text("// edited by hand\n", encoding="utf-8")
    (rem / "src" / "kit" / "scenes" / "Quote.tsx").unlink()
    (rem / "src" / "Root.tsx").write_text("// mine, ReelKit\n", encoding="utf-8")
    (rem / "src" / "gen" / "registry.ts").write_text("// my scenes\n", encoding="utf-8")
    (rem / "src" / "kit" / "Mine.tsx").write_text("// mine\n", encoding="utf-8")
    r = run_script("kit.py", "check", "--remotion", rem, cwd=project, check=False)
    assert r.returncode == 1 and "differs: src/kit/brand.ts" in r.stdout and "missing: src/kit/scenes/Quote.tsx" in r.stdout
    r = run_script("kit.py", "update", "--remotion", rem, "--dry-run", cwd=project)
    assert (rem / "src" / "kit" / "brand.ts").read_text(encoding="utf-8") == "// edited by hand\n"
    run_script("kit.py", "update", "--remotion", rem, cwd=project)
    assert (rem / "src" / "kit" / "brand.ts").read_bytes() == lf((KIT / "kit" / "brand.ts").read_bytes())
    assert (rem / "src" / "kit" / "scenes" / "Quote.tsx").is_file()
    backups = list((rem / ".kit-backup").glob("*/src/kit/brand.ts"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == "// edited by hand\n"
    assert (rem / "src" / "Root.tsx").read_text(encoding="utf-8") == "// mine, ReelKit\n"
    assert (rem / "src" / "gen" / "registry.ts").read_text(encoding="utf-8") == "// my scenes\n"
    assert (rem / "src" / "kit" / "Mine.tsx").is_file()
    assert run_script("kit.py", "check", "--remotion", rem, cwd=project).returncode == 0


def test_line_endings_alone_are_not_a_difference(project):
    # A kit copied from a Windows checkout (autocrlf) has CRLF; the plugin from the marketplace has LF. Same files:
    # check must say they match and update must not replace (and back up) them.
    run_script("kit.py", "new", "reels", cwd=project)
    rem = project / "reels"
    kit = sorted((rem / "src" / "kit").rglob("*.ts*")) + [rem / "src" / "ReelKit.tsx"]
    assert all(b"\r\n" not in p.read_bytes() for p in kit)  # new projects get LF whatever the checkout has
    for p in kit:
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    r = run_script("kit.py", "check", "--remotion", rem, cwd=project)
    assert r.returncode == 0 and "matches" in r.stdout
    r = run_script("kit.py", "update", "--remotion", rem, cwd=project)
    assert "already matches" in r.stdout and not (rem / ".kit-backup").exists()
    assert b"\r\n" in (rem / "src" / "ReelKit.tsx").read_bytes()  # the person's copy is left as it is


def test_an_older_plugin_does_not_roll_the_kit_back(project):
    # Claude Desktop can still run an older catalog copy of the plugin while the project already has a newer kit.
    run_script("kit.py", "new", "reels", cwd=project)
    rem = project / "reels"
    ver = rem / "src" / "kit" / "version.ts"
    ver.write_text(re.sub(r'"[^"]+"', '"99.0.0"', ver.read_text(encoding="utf-8"), count=1), encoding="utf-8")
    r = run_script("kit.py", "check", "--remotion", rem, cwd=project)
    assert r.returncode == 0 and "newer than this plugin" in r.stdout
    r = run_script("kit.py", "update", "--remotion", rem, cwd=project, check=False)
    assert r.returncode != 0 and "newer than this plugin" in r.stderr
    assert "99.0.0" in ver.read_text(encoding="utf-8")
    run_script("kit.py", "update", "--remotion", rem, "--force", cwd=project)
    assert "99.0.0" not in ver.read_text(encoding="utf-8")


def test_update_refuses_a_folder_that_is_not_a_remotion_project(project):
    (project / "other").mkdir()
    r = run_script("kit.py", "update", "--remotion", project / "other", cwd=project, check=False)
    assert r.returncode != 0 and "not a Remotion project" in r.stderr
    assert not (project / "other" / "src").exists()


def test_doctor_reports_the_kit_version(project):
    run_script("kit.py", "new", "reels", cwd=project)
    r = run_script("doctor.py", "--json", cwd=project, check=False)
    names = {c["name"]: c for c in json.loads(r.stdout)["checks"]}
    assert names["ReelKit in the project"]["ok"]
