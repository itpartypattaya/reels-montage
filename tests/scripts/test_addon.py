"""The online add-on as the core sees it: link, runner, defaults, fallback reasons, key masking. No network:
every run sets REELS_OFFLINE=1 and an empty keys file."""
import json

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
