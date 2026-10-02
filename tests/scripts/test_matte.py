"""matte.py: the local cut-out refuses cleanly without rembg or its model and never downloads; the add-on's server
cut-out refuses without a host. No server is contacted."""
from conftest import ADDON, make_video, needs_ffmpeg, run_script


def rough_cut(project):
    make_video(project / "edit" / "4821" / "final.mp4", 1080, 1920, 3.0)


@needs_ffmpeg
def test_dry_run_estimates_without_rembg(project):
    rough_cut(project)
    r = run_script("matte.py", "cut", "edit/4821", "--from", "0.5", "--to", "2.0", "--dry", cwd=project)
    assert "45 frames" in r.stdout


@needs_ffmpeg
def test_local_cut_needs_rembg(project):
    rough_cut(project)
    r = run_script("matte.py", "cut", "edit/4821", "--from", "0.5", "--to", "2.0", "--rembg", "no-such-rembg",
                   cwd=project, check=False)
    assert r.returncode == 1 and "rembg" in (r.stdout + r.stderr)


@needs_ffmpeg
def test_server_cut_needs_a_host(project, tmp_path):
    rough_cut(project)
    env = {"REELS_ONLINE_SCRIPTS": str(ADDON), "REELS_OFFLINE": "1", "REELS_KEYS_FILE": str(tmp_path / "none.env")}
    r = run_script("addon.py", "matte", "cut", "edit/4821", "--from", "0.5", "--to", "2.0", cwd=project, env=env, check=False)
    assert r.returncode == 1 and "no server for the cut-out" in (r.stdout + r.stderr)
