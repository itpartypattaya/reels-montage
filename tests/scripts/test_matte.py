"""matte.py: the local cut-out refuses cleanly without rembg or its model and never downloads; the add-on's server
cut-out refuses without a host. No server is contacted."""
import json

from conftest import ADDON, ffmpeg, make_video, needs_ffmpeg, needs_pillow, run_script, write_json


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
