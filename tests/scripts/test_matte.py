"""matte.py: the local cut-out refuses cleanly without rembg or its model and never downloads; the add-on's server
cut-out refuses without a host. No server is contacted."""
import json

from conftest import ADDON, ffmpeg, make_video, needs_ffmpeg, needs_pillow, run_script, write_json


def test_rembg_looks_for_its_models_where_the_check_found_them(project, monkeypatch, tmp_path):
    # Codex review of 1.22: matte.models moved the pre-check to that folder, while rembg itself still looked in its
    # default one (it reads U2NET_HOME), so a model kept only there passed the check and then was not found
    import os
    import subprocess
    import sys
    from types import SimpleNamespace
    import matte
    models = tmp_path / "rembg-models"
    models.mkdir()
    write_json(project / "it-reelsmaker.json", {"matte": {"models": str(models)}})
    (project / "edit" / "4821").mkdir(parents=True)
    src = tmp_path / "cut" / "frames"
    src.mkdir(parents=True)
    seen = {}
    real_run = subprocess.run

    def first_call(cmd, *args, **kw):  # the rembg call: what a process started now sees, then stop the cut
        seen["home"] = real_run([sys.executable, "-c", "import os; print(os.environ.get('U2NET_HOME') or '')"],
                                capture_output=True, text=True, check=True).stdout.strip()
        raise matte.Fail("stopped by the test")

    monkeypatch.setattr(matte.subprocess, "run", first_call)
    monkeypatch.setattr(matte, "free_mb", lambda: None)  # this machine's free memory is not what is tested
    eng = matte.Local(SimpleNamespace(model="u2net_human_seg", edit="edit/4821", rembg=sys.executable))
    try:
        eng.run(src, 30, 60, 5, tmp_path / "cut" / "out.webm")
    except matte.Fail:
        pass
    finally:
        os.unsetenv("U2NET_HOME")
    assert seen.get("home") == str(models)


def test_rembg_looks_in_the_default_folder_the_check_used(project, monkeypatch, tmp_path):
    # PR #35 review (P2): with no matte.models the pre-check looks in ~/.u2net, while rembg inherited a U2NET_HOME
    # from the launching environment and looked elsewhere: a model in ~/.u2net passed the check, and rembg did not
    # find it (a download, or a failure offline)
    import os
    import subprocess
    import sys
    from types import SimpleNamespace
    import matte
    elsewhere = tmp_path / "another-tool-models"
    elsewhere.mkdir()
    monkeypatch.setenv("U2NET_HOME", str(elsewhere))  # set by another tool in the user's shell
    (project / "edit" / "4821").mkdir(parents=True)
    src = tmp_path / "cut" / "frames"
    src.mkdir(parents=True)
    seen = {}
    real_run = subprocess.run

    def first_call(cmd, *args, **kw):
        seen["home"] = real_run([sys.executable, "-c", "import os; print(os.environ.get('U2NET_HOME') or '')"],
                                capture_output=True, text=True, check=True).stdout.strip()
        raise matte.Fail("stopped by the test")

    monkeypatch.setattr(matte.subprocess, "run", first_call)
    monkeypatch.setattr(matte, "free_mb", lambda: None)
    eng = matte.Local(SimpleNamespace(model="u2net_human_seg", edit="edit/4821", rembg=sys.executable))
    try:
        eng.run(src, 30, 60, 5, tmp_path / "cut" / "out.webm")
    except matte.Fail:
        pass
    assert seen.get("home") == str(matte.model_file("u2net_human_seg").parent)
    assert seen.get("home") != str(elsewhere)


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
    write_json(project / "it-reelsmaker.json", {"online_scripts": str(ADDON)})  # the add-on's link command writes this
    env = {"REELS_OFFLINE": "1", "REELS_KEYS_FILE": str(tmp_path / "none.env")}  # the add-on's own switches
    r = run_script("addon.py", "matte", "cut", "edit/4821", "--from", "0.5", "--to", "2.0", cwd=project, env=env, check=False)
    assert r.returncode == 1 and "no server for the cut-out" in (r.stdout + r.stderr)


def seated_figure(path, w=270, h=480, dur=1.0):
    """A WebM with alpha: a head and a wide torso that ends at y 300 of 480 (a table line), no source edge touched."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-f", "lavfi", "-i", f"color=c=0xC09070:s={w}x{h}:r=30:d={dur}", "-f", "lavfi", "-i",
           f"color=c=black:s={w}x{h}:r=30:d={dur}", "-filter_complex",
           "[1:v]drawbox=x=110:y=120:w=50:h=60:color=white:t=fill,drawbox=x=60:y=190:w=150:h=110:color=white:t=fill,"
           "format=gray[m];[0:v][m]alphamerge,format=yuva420p", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
           "-auto-alt-ref", "0", "-b:v", "1M", path)
    return path


def placed(project, width=1080):
    import faces
    e = project / "edit" / "4821"
    webm = seated_figure(e / "matte" / "host.webm")
    write_json(e / "matte" / "host.json", {"from": 1.0, "to": 2.0, "fps": 30, "frames": 30, "width": width,
                                           "bbox": [240, 480, 840, 1200], "head_top": 480, "webm": str(webm)})
    # the presenter's face is 216 px high: the review target 260 needs x1.2, and the figure is never scaled up
    write_json(e / "faces.json", {"step": 0.25, "geometry": "cover", "w": 1080, "h": 1920, "filter": {"v": faces.FILTER_V},
                                  "samples": [{"t": round(1.0 + k * 0.25, 2), "faces": [[440, 500, 190, 216, 0.95]]}
                                              for k in range(5)]})
    return e


@needs_ffmpeg
def test_place_reports_the_face_on_screen_and_the_table_cut(project):
    # T2: "face 216 -> 260 px" at x1.0 (the face stayed 216); the body ended at the table line inside the source
    # (touch 0/0/0/0) and that line stood in the middle of the review layout; the presenter's own face was flagged
    # by validate and audit in its own keep-clear zone
    e = placed(project)
    r = run_script("matte.py", "place", "edit/4821", "--name", "host", "--layout", "review", cwd=project)
    assert "216 px -> 216 px on screen; the target 260 px needs x1.20" in r.stdout, r.stdout
    assert "the figure ends inside its own frame" in r.stdout and "Hide it behind an opaque element" in r.stdout
    assert "--matte host --own-face 440," in r.stdout
    meta = json.loads((e / "matte" / "host.json").read_text(encoding="utf-8"))
    assert meta["touch"]["inner"] == 30 and meta["touch"]["bottom"] == 0
    assert 1180 <= meta["touch"]["inner_y"][1] <= 1210  # the table line: y 300 of 480 -> 1200
    keep = meta["place"]["keep_clear"]
    assert keep["matte"] == "host" and keep["own_face"][:2] == [440, meta["place"]["props"]["y"] + 500]
    assert meta["place"]["inner_cut_screen"][1] < 1920


@needs_ffmpeg
def test_place_warns_when_a_narrow_cut_out_is_upscaled(project):
    placed(project, width=720)
    r = run_script("matte.py", "place", "edit/4821", "--name", "host", "--layout", "review", cwd=project)
    assert "the cut-out is 720 px wide and is shown at 1080 px: x1.50" in r.stdout


@needs_pillow
@needs_ffmpeg
def test_the_check_frame_shows_the_figure(project, tmp_path):
    # T2: the check frame had only the two backgrounds: after -ss the figure's first frame came a few ms after 0
    # (1.65 s is off the frame grid), the color backgrounds at 0, and overlay's first frame had no figure
    import matte
    from PIL import Image
    webm = seated_figure(tmp_path / "fig.webm", dur=3.0)
    out = tmp_path / "check.png"
    assert matte.check_frame(webm, 1.65, out).returncode == 0
    im = Image.open(out).convert("RGB")
    assert im.size == (1080, 960)
    for x0 in (0, 540):  # the torso (60..210 of 270 -> 120..420 of 540) on the light and on the dark background
        r, g, b = im.getpixel((x0 + 270, 480))
        assert abs(r - 0xC0) < 20 and abs(b - 0x70) < 20, (x0, (r, g, b))
