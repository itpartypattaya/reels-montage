"""The online add-on as the core sees it: link, runner, defaults, fallback reasons, key masking. No network:
every run sets REELS_OFFLINE=1 and an empty keys file."""
import json
from pathlib import Path

import pytest

from conftest import ADDON, make_video, needs_ffmpeg, run_script, write_json

OFF = {"REELS_OFFLINE": "1"}


def env(tmp_path, **extra):
    return {**OFF, "REELS_KEYS_FILE": str(tmp_path / "no-keys.env"), **extra}


def link(project, tmp_path):
    run_script("reels_online.py", "link", "--project", project, cwd=project, env=env(tmp_path), scripts=ADDON)
    return json.loads((project / "it-reelsmaker.json").read_text(encoding="utf-8"))


def test_link_and_unlink_keep_other_settings(project, tmp_path):
    write_json(project / "it-reelsmaker.json", {"face_model": "models/yunet.onnx"})
    cfg = link(project, tmp_path)
    assert cfg["face_model"] == "models/yunet.onnx"
    assert (ADDON / "reels_online.py").samefile(f"{cfg['online_scripts']}/reels_online.py")
    run_script("reels_online.py", "unlink", "--project", project, cwd=project, env=env(tmp_path), scripts=ADDON)
    cfg = json.loads((project / "it-reelsmaker.json").read_text(encoding="utf-8"))
    assert "online_scripts" not in cfg and cfg["face_model"] == "models/yunet.onnx"


def test_runner_without_the_add_on_explains_how_to_link(project, tmp_path):
    r = run_script("addon.py", "memes", "search", "facepalm", cwd=project, env=env(tmp_path), check=False)
    assert r.returncode != 0 and "link" in r.stderr


def test_runner_lists_commands_once_linked(project, tmp_path):
    link(project, tmp_path)
    r = run_script("addon.py", cwd=project, env=env(tmp_path))
    assert "commands:" in r.stdout and "gen" in r.stdout and "memes" in r.stdout and "matte" in r.stdout


def test_add_on_defaults_and_reasons(project, tmp_path):
    link(project, tmp_path)
    write_json(project / "edit" / "4821" / "reel.json", {"use_broll": True, "use_online_footage": True,
                                                       "use_generated_footage": True, "generate_now": True})
    r = run_script("reelcfg.py", "show", "edit/4821", "--json", cwd=project, env=env(tmp_path))
    out = r.stdout
    assert "REELS_OFFLINE=1" in out  # online footage and paid generation are off, with the reason
    r = run_script("reelcfg.py", "save", "edit/4821", "--set", "use_online_memes=true", cwd=project, env=env(tmp_path))
    assert "unknown" not in (r.stdout + r.stderr).lower()  # the add-on's keys are known once it is linked


@needs_ffmpeg
def test_stock_providers_listed_but_unavailable_offline(project, tmp_path):
    link(project, tmp_path)
    make_video(project / "IMG_4821.MOV", 360, 640, 2.0)
    r = run_script("footage.py", "providers", cwd=project, env=env(tmp_path))
    lines = {l.split()[0]: l for l in r.stdout.splitlines() if l.strip()}
    assert "project" in lines and "local" in lines
    for name in ("pixabay", "pexels"):
        assert name in lines and "REELS_OFFLINE" in lines[name]


def test_keys_never_reach_the_output(project, tmp_path):
    keys = tmp_path / "keys.env"
    keys.write_text("PIXABAY_API_KEY=sk_test_1234567890abcdef\n", encoding="utf-8")
    code = ("import reels_online as o; "
            "print(o.scrub('GET https://x.test/api/?key=sk_test_1234567890abcdef&q=pool Authorization: Bearer abcdefghijklmnopqrstuv'))")
    import subprocess, sys, os
    e = {**os.environ, "REELS_KEYS_FILE": str(keys), "PYTHONPATH": str(ADDON), **OFF}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=e, check=True).stdout
    assert "sk_test_1234567890abcdef" not in out and "abcdefghijklmnopqrstuv" not in out and "***" in out


def test_core_without_add_on_turns_online_off_with_a_reason(project, tmp_path):
    write_json(project / "edit" / "4821" / "reel.json", {"use_broll": True, "use_online_footage": True})
    r = run_script("reelcfg.py", "show", "edit/4821", cwd=project, env=env(tmp_path))
    line = next(l for l in r.stdout.splitlines() if "online footage" in l)
    assert " no " in line and "the online add-on is not installed" in line


def test_online_scripts_with_home_and_relative_paths(project, tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    import reels_common
    home = tmp_path / "home"
    (home / "addon").mkdir(parents=True)
    (home / "addon" / "reels_online.py").write_text("DEFAULTS = {}\n", encoding="utf-8")
    (project / "local-addon").mkdir()
    (project / "local-addon" / "reels_online.py").write_text("DEFAULTS = {}\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for value, where in (("~/addon", home / "addon"), ("local-addon", project / "local-addon")):
        write_json(project / "it-reelsmaker.json", {"online_scripts": value})
        monkeypatch.setattr(reels_common, "_ONLINE", None)
        sys.modules.pop("reels_online", None)  # a fake add-on: never left behind for the other tests
        mod = reels_common.online()
        assert mod is not None and Path(mod.__file__).parent.samefile(where)
        sys.path.remove(str(where if value.startswith("~") else project / value))
    write_json(project / "it-reelsmaker.json", {"online_scripts": "${user_config.online_scripts}"})
    monkeypatch.setattr(reels_common, "_ONLINE", None)
    assert reels_common.online() is None
    write_json(project / "it-reelsmaker.json", {"online_scripts": "~no-such-user-xyz/addon"})
    monkeypatch.setattr(reels_common, "_ONLINE", None)
    assert reels_common.online() is None  # an unknown ~user is "not found", not a crash
    sys.modules.pop("reels_online", None)


def _keys_module(monkeypatch, tmp_path):
    import sys
    monkeypatch.syspath_prepend(str(ADDON))
    import reels_online
    monkeypatch.setattr(reels_online, "KEYS_FILE", tmp_path / "cfg" / "keys.env")
    monkeypatch.setattr(reels_online, "_KEYS", None)
    for n in reels_online.known_keys():
        monkeypatch.delenv(n, raising=False)
    return reels_online


class _Tty:
    def isatty(self):
        return True


def test_keys_set_list_remove_keep_other_lines(monkeypatch, tmp_path, capsys):
    import getpass, os, stat, sys
    from types import SimpleNamespace
    ro = _keys_module(monkeypatch, tmp_path)
    ro.KEYS_FILE.parent.mkdir(parents=True)
    ro.KEYS_FILE.write_text("# my keys\nGIPHY_API_KEY=giphy-0000000000\n", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "  pexels-secret-value-1234  ")
    ro.cmd_keys_set(SimpleNamespace(name="PEXELS_API_KEY"))
    text = ro.KEYS_FILE.read_text(encoding="utf-8")
    assert "# my keys" in text and "GIPHY_API_KEY=giphy-0000000000" in text and "PEXELS_API_KEY=pexels-secret-value-1234" in text
    assert ro.api_key("PEXELS_API_KEY") == "pexels-secret-value-1234"
    out = capsys.readouterr().out
    assert "pexels-secret-value-1234" not in out and "...1234" in out
    ro.cmd_keys_list(SimpleNamespace())
    out = capsys.readouterr().out
    assert "secret" not in out and "PEXELS_API_KEY" in out and "(file)" in out
    if os.name != "nt":
        assert stat.S_IMODE(ro.KEYS_FILE.stat().st_mode) == 0o600
    ro.cmd_keys_remove(SimpleNamespace(name="PEXELS_API_KEY"))
    text = ro.KEYS_FILE.read_text(encoding="utf-8")
    assert "PEXELS" not in text and "GIPHY_API_KEY=giphy-0000000000" in text and ro.api_key("PEXELS_API_KEY") is None


def test_keys_set_refuses_without_a_terminal_and_bad_names(monkeypatch, tmp_path):
    import getpass, io, sys
    from types import SimpleNamespace
    ro = _keys_module(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("piped-secret\n"))
    monkeypatch.setattr(getpass, "getpass", lambda prompt: pytest.fail("must not read a key without a terminal"))
    with pytest.raises(SystemExit) as ex:
        ro.cmd_keys_set(SimpleNamespace(name="FAL_KEY"))
    assert "terminal" in str(ex.value) and not ro.KEYS_FILE.exists()
    with pytest.raises(SystemExit):
        ro.cmd_keys_set(SimpleNamespace(name="fal key; rm"))


def test_keys_set_leaves_an_existing_folder_alone(monkeypatch, tmp_path):
    import getpass, os, stat, sys
    from types import SimpleNamespace
    ro = _keys_module(monkeypatch, tmp_path)
    shared = tmp_path / "shared"
    shared.mkdir()
    if os.name != "nt":
        os.chmod(shared, 0o755)
    monkeypatch.setattr(ro, "KEYS_FILE", shared / "keys.env")
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "fal-secret-value-5678")
    ro.cmd_keys_set(SimpleNamespace(name="FAL_KEY"))
    assert ro.api_key("FAL_KEY") == "fal-secret-value-5678"
    if os.name != "nt":
        assert stat.S_IMODE(shared.stat().st_mode) == 0o755  # an existing folder keeps its rights
        assert stat.S_IMODE(ro.KEYS_FILE.stat().st_mode) == 0o600


def test_memes_fetch_reads_the_file_type_from_the_bytes(project, monkeypatch, tmp_path, capsys):
    # T5: Openverse gave two emoji sets as SVG text under a link that named no type; fetch saved them as .jpg, Pillow
    # could not open them and memes.py index would fail. Now: the type comes from the bytes; an SVG is kept as .svg
    # with its sidecar and a clear "convert it" message; a PNG under a .jpg link is saved as .png; junk is deleted
    monkeypatch.syspath_prepend(str(ADDON))
    monkeypatch.delenv("REELS_OFFLINE", raising=False)
    import memes_online as mo
    body = {}
    item = {"id": "0c57de66-1111-2222-3333-444455556666", "license": "by", "license_version": "4.0",
            "url": "https://upload.example.org/emoji/1f60d", "title": "Twemoji 1f60d", "creator": "Twitter",
            "foreign_landing_url": "https://example.org/1f60d"}
    monkeypatch.setattr(mo, "http_json", lambda url, **kw: dict(item))
    online = project / "memes" / "online"

    def download(url, dest, **kw):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(body["data"])
        return dest
    monkeypatch.setattr(mo, "download", download)

    def fetch(data):
        body["data"] = data
        mo.main(["fetch", f"openverse:{item['id']}", "--yes"])
        return capsys.readouterr()

    out = fetch(b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36"></svg>')
    assert (online / "openverse-0c57de66.svg").is_file() and not list(online.glob("*.jpg"))
    assert "vector image (SVG)" in out.err and "openverse-0c57de66.png" in out.err
    side = json.loads((online / "openverse-0c57de66.json").read_text(encoding="utf-8"))
    assert side["rights"] == "cc" and "Twemoji" in side["attribution"]
    (online / "openverse-0c57de66.svg").unlink()
    out = fetch(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
    assert (online / "openverse-0c57de66.png").is_file() and "memes.py index" in out.out
    (online / "openverse-0c57de66.png").unlink()
    out = fetch(b"<html><body>rate limited</body></html>")
    assert "not an image" in out.err and not [p for p in online.iterdir() if p.suffix != ".json"]
    # search marks an SVG result
    monkeypatch.setattr(mo, "http_json", lambda url, **kw: {"results": [dict(item, filetype="svg")]})
    mo.cmd_online(type("A", (), {"query": "heart eyes", "provider": "openverse", "limit": 4})())
    assert "SVG: not usable until converted" in capsys.readouterr().out
