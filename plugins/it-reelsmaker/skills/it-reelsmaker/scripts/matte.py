# -*- coding: utf-8 -*-
"""Cut out the speaker's figure with rembg for "text behind the person" and "presenter over a scene"
(references/figure.md).

  cut    - frames of a span of the rough cut (JPG) -> rembg on this computer -> a WebM with alpha and edge cleanup
           (1 px erosion, blur, centered averaging of the mask over 3 frames against flicker), plus the figure's box
           from the alpha, the source-edge cuts and a check frame: edit/<id>/matte/<name>.webm, .json, -check.png
  place  - where and at what scale to put the figure in the "review" / "stream" layout: scale from the presenter's
           face height (faces.json), side from the source-edge cuts, the figure's and the face's box on screen,
           checks -> props for the Presenter component.

    python scripts/matte.py cut edit/<id> --from 12.4 --to 19.0 [--width 1080] [--name host] [--video <file>] [--rembg <command>] [--dry]
    python scripts/matte.py place edit/<id> --name host --layout review [--side auto|left|right] [--face 260]

Exit code: 0 - done (or --dry); 1 - no cut-out, a check not performed, or the layout breaks the rules.
--width: 1080 (default) for the hook and for a presenter over a scene. place never scales the figure above its
size in the 1080x1920 frame (x1.0: an upscaled cut-out has soft, stepped edges), and the Presenter component shows
the WebM at 1080 x scale whatever its pixel width: a 720 cut-out at x1.0 is upscaled x1.5. 720 only when place gives
a scale of 0.66 or less (the face in the rough cut at least 1.5 x the layout's target, a close-up); place warns when
a cut-out is shown above its own pixels. Speed: about 1 s per 1080x1920 frame on a CPU (about 0.5 s at 720), plus
about 45 s to start the model; --dry prints the estimate.

rembg is yours to install, best in a separate venv (about 810 MB): pip install "rembg[cpu,cli]". The command:
--rembg, else the REELS_MATTE_REMBG environment variable, else it-reelsmaker.json -> matte.rembg
(e.g. {"matte": {"rembg": "~/venvs/rembg/bin/rembg"}}), else rembg on PATH.
The plugin never downloads models: download u2net_human_seg (about 170 MB) once yourself with
rembg d u2net_human_seg; rembg keeps it in U2NET_HOME or ~/.u2net. This Python needs Pillow (the figure's box).
Model: u2net_human_seg only (about 1.5 GB of memory): larger models need more memory than a small machine has.
Before a run the free memory and disk of this computer are checked. Cut-outs run one at a time per project (a lock
file edit/.matte.lock); memory is checked again under the lock. --wait: minutes to wait for the lock (default 20).
A computer with little memory: the online-sources add-on it-reelsmaker-online can run the same cut-out on your own
server (python scripts/addon.py matte cut ...).
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import local_media_args, inside, safe_slug, edit_dir, load_json, locked, probe, project_settings, run, save_json, utf8_stdio, warn

W, H = 1080, 1920
SEC_PER_MPX = 0.5     # about 1 s per 1080x1920 frame (2.07 Mpx) on a CPU at low priority
UI_BOTTOM = 420       # the bottom of the frame under the Reels UI: the presenter's face stays above it
UI_RIGHT = 120
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")      # --name goes into file names: safe characters only

# Layouts (references/figure.md, section 2). face: the target height of the YuNet face box on screen, px.
LAYOUTS = {
    "review": {"face": 260, "panel": [40, 230, 1000, 900], "overlap": 120,
               "note": "the scene in a panel at the top, the presenter at the bottom by the edge, over the panel's bottom"},
    "stream": {"face": 170, "panel": [0, 0, 1080, 1920], "overlap": 0,
               "note": "the scene fills the frame, the presenter small in a bottom corner"},
}

BBOX = r"""
import json, sys
from pathlib import Path
from PIL import Image
fs = sorted(Path(sys.argv[1]).glob('*.png'))
u = None; heads = []
for p in fs:
    a = Image.open(p).getchannel('A').point(lambda v: 255 if v > 128 else 0)
    b = a.getbbox()
    if not b: continue
    heads.append(b[1])
    u = b if u is None else (min(u[0], b[0]), min(u[1], b[1]), max(u[2], b[2]), max(u[3], b[3]))
w, h = Image.open(fs[0]).size if fs else (0, 0)
print(json.dumps({"frames": len(fs), "w": w, "h": h, "bbox": u, "head_top_min": min(heads) if heads else None,
                  "empty": len(fs) - len(heads)}))
"""

# Alpha cleanup: 1 px erosion (the fringe of the old background), blur, averaging over 3 frames with weights 1-2-1.
# tmix mixes the current frame and the two previous ones, so the window's center is on frame n-1; trim shifts the mask
# one frame back so that the center matches the color (otherwise the contour lags behind a fast gesture), tpad adds
# the last frame back.
CLEAN = ("split[c][a];[a]alphaextract,erosion=threshold0=255:coordinates=255,gblur=sigma=0.8,"
         "tmix=frames=3:weights='1 2 1',trim=start_frame=1,setpts=PTS-STARTPTS,tpad=stop=1:stop_mode=clone[m];"
         "[c][m]alphamerge,format=yuva420p")


class Fail(Exception):
    pass


def edge_touch(webm, w=270, h=480, min_px=4):
    """Which source edges the figure touches: a hand, an elbow, a shoulder, the bottom of the body, the top of the head.
    Where the figure touches the edge, the cut-out has a straight cut: in the layout it must coincide with a frame
    edge, otherwise a chopped-off arm shows in the middle of the screen. min_px is on a 270x480 mask (4 px is about
    16 px at 1080x1920: a fingertip already counts).
    Also a cut inside the frame (inner_cut): inner = frames with it, inner_y = [where the bottom contour starts,
    the lowest point] in 1080x1920 source rows.
    -> ({left, right, top, bottom: the number of frames touching it, frames, inner[, inner_y]}, None) or (None,
    reason): no check."""
    r = subprocess.run(local_media_args(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", str(webm), "-vf",
                        f"alphaextract,scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "gray", "-"]),
                       capture_output=True)
    data, size = r.stdout, w * h
    n = len(data) // size
    if r.returncode != 0 or not n:
        return None, (r.stderr.decode("utf-8", "replace").strip()[-300:] or "ffmpeg produced no alpha frames")
    cnt = {"left": 0, "right": 0, "top": 0, "bottom": 0}
    inner, opaque = [], bytes(255 if v > 128 else 0 for v in range(256))
    for k in range(n):
        f = data[k * size:(k + 1) * size]
        g = f.translate(opaque)
        cut = inner_cut([g.count(255, y * w, (y + 1) * w) for y in range(h)], h)
        if cut:
            inner.append(cut)
        if sum(1 for y in range(h) if f[y * w] > 128) >= min_px:
            cnt["left"] += 1
        if sum(1 for y in range(h) if f[y * w + w - 1] > 128) >= min_px:
            cnt["right"] += 1
        if sum(1 for v in f[:w] if v > 128) >= min_px:
            cnt["top"] += 1
        if sum(1 for v in f[size - w:] if v > 128) >= min_px:
            cnt["bottom"] += 1
    cnt["inner"] = 0
    if inner and not cnt["bottom"]:  # the figure's bottom cut inside the source: the rows in 1080x1920
        cnt["inner"] = len(inner)
        cnt["inner_y"] = [round(min(c[0] for c in inner) * H / h), round(max(c[1] for c in inner) * H / h)]
    return {**cnt, "frames": n}, None


INNER_GAP = 8       # rows of the 270x480 mask (about 32 px at 1920): a figure ending this far above the source bottom
INNER_WIDE = 0.6    # ... and still this wide (of its widest row) near its bottom is cut by something in the frame


def inner_cut(rows, h):
    """A cut INSIDE the source frame: the figure ends well above the source bottom while still wide near its bottom
    (the bottom 20% of its height) - a table or a laptop in front of a seated speaker, not the narrow end of a body.
    rows: opaque pixels per row of one frame. -> (the row where the contour starts: the last row going down at 80% of
    the widest, the lowest opaque row) or None. Real case (T2): touch 0/0/0/0, yet the body ended at the table line,
    and in the review layout that line stood in the middle of the frame."""
    ys = [y for y in range(h) if rows[y] >= 4]
    if not ys or h - 1 - ys[-1] < INNER_GAP:
        return None
    top, low = ys[0], ys[-1]
    band = rows[max(top, low - (low - top) // 5): low + 1]
    widest = max(rows)
    if max(band) < INNER_WIDE * widest:
        return None
    y0 = max(y for y in range(rows.index(widest), low + 1) if rows[y] >= 0.8 * widest)
    return y0, low


def touched(touch, edge):
    """The edge is touched if at least one frame touches it (a frame count; a fraction in older files, also > 0)."""
    return (touch or {}).get(edge, 0) > 0


# Peak memory of a model on a CPU, MB. There is one working model, u2net_human_seg (~1.5 GB, measured).
# Any other model is not run: larger models need more memory than a small machine has.
MODEL_RAM = {"u2net_human_seg": 1500}
MEM_RESERVE = 1000    # MB on top of the model for everything else on the machine: low priority does not limit memory


def model_ok(model):
    """The model allow-list; None: allowed, otherwise the reason."""
    need = MODEL_RAM.get(model)
    if need is None:
        return (f"model {model} is not allowed: only {', '.join(MODEL_RAM)} (larger models need more memory than a "
                f"small machine has)")
    if need > 5000:
        return f"model {model} needs ~{need // 1000} GB of memory: use u2net_human_seg or the window layout"
    return None


def rembg_args(model, src, dst):
    """rembg arguments: a folder of frames -> a folder of PNG with alpha (same names, .png)."""
    return ["p", "-m", model, str(src), str(dst)]


def pack_cmd(fps, inp, dst):
    """ffmpeg: PNG frames with alpha -> a VP9 WebM with alpha and the edge cleanup (CLEAN). inp: the input arguments."""
    return ["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", str(fps), *inp, "-vf", CLEAN, "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "3M", "-row-mt", "1", str(dst)]


def model_file(model):
    """Where rembg keeps a model: U2NET_HOME, otherwise <XDG_DATA_HOME or the home folder>/.u2net."""
    base = os.environ.get("U2NET_HOME") or Path(os.environ.get("XDG_DATA_HOME") or Path.home()) / ".u2net"
    return Path(base).expanduser() / f"{model}.onnx"


def free_mb():
    """Available memory of this computer, MB (standard library only); None: it can't be measured here."""
    try:
        if sys.platform.startswith("linux"):
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
        elif sys.platform == "win32":
            import ctypes

            class MemStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                    (n, ctypes.c_ulonglong) for n in ("total", "avail", "total_page", "avail_page", "total_virt",
                                                      "avail_virt", "avail_ext")]
            m = MemStatus()
            m.dwLength = ctypes.sizeof(MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return m.avail // 2 ** 20
        elif sys.platform == "darwin":
            out = subprocess.run(local_media_args(["vm_stat"]), capture_output=True, text=True).stdout
            page = int(re.search(r"page size of (\d+)", out).group(1))
            pages = sum(int(m.group(1)) for m in re.finditer(r"Pages (?:free|inactive|speculative):\s+(\d+)", out))
            return pages * page // 2 ** 20
    except Exception:
        pass
    return None


class Local:
    """rembg on this computer (the cut command's default engine). The online add-on passes its own engine with the
    same check / run / cleanup methods to cmd_cut."""

    def __init__(self, a):
        self.model = a.model
        self.lock = edit_dir(a.edit).parent / ".matte"  # -> edit/.matte.lock: one cut-out at a time per project
        m = project_settings().get("matte")
        v = next((str(x) for x in (a.rembg, os.environ.get("REELS_MATTE_REMBG"), m.get("rembg") if isinstance(m, dict)
                                   else None) if x and not str(x).startswith("${")), "rembg")
        self.rembg = shutil.which(str(Path(v).expanduser()))
        if not self.rembg:
            sys.exit(f"rembg is not found ({v}). Install it yourself, best in a separate venv: pip install "
                     f"\"rembg[cpu,cli]\" (about 810 MB), then pass its path with --rembg, the REELS_MATTE_REMBG "
                     f"environment variable or {{\"matte\": {{\"rembg\": \"<path>\"}}}} in it-reelsmaker.json. "
                     f"Without rembg: the \"window\" layout (no cut-out)")

    def check(self, n_mpx, model):
        """Model, free memory and disk of this computer; None: go ahead, otherwise the reason."""
        why = model_ok(model)
        if why:
            return why
        f = model_file(model)
        if not f.is_file():
            return (f"the rembg model {f.name} is not in {f.parent}. The plugin never downloads models: download it "
                    f"once yourself (about 170 MB): rembg d {model}")
        need, mem = MODEL_RAM[model], free_mb()
        if mem is None:
            warn("the free memory of this computer can't be measured here; the memory check is skipped")
        elif mem < need + MEM_RESERVE:
            return (f"this computer has {mem} MB of free memory; model {model} needs ~{need} + {MEM_RESERVE} MB of "
                    f"headroom: close other programs, or run the cut-out on your own server with the online-sources add-on "
                    f"it-reelsmaker-online")
        disk = shutil.disk_usage(tempfile.gettempdir()).free // 2 ** 20
        if disk < n_mpx * 3 + 500:
            return f"{tempfile.gettempdir()} has {disk} MB free: too little"
        return None

    def run(self, src, fps, limit, wait, dst):
        """rembg + the WebM packaging under the project lock -> the figure's box (BBOX). src: the folder of JPG
        frames; limit: the time limit for rembg, s; wait: how long to wait for the lock, s."""
        res = src.parent / "out"
        res.mkdir(exist_ok=True)
        nice = ["nice", "-n", "19"] if os.name == "posix" and shutil.which("nice") else []
        with locked(self.lock, timeout=wait, stale=limit + 600):
            mem = free_mb()  # again under the lock: a previous cut-out has finished, other programs may have grown
            need = MODEL_RAM[self.model] + MEM_RESERVE
            if mem is not None and mem < need:
                raise Fail(f"not enough memory under the lock (free {mem} MB, needed {need}): wait and try again")
            print(f"rembg on this computer (up to {limit / 60:.0f} min)...", flush=True)
            try:
                r = subprocess.run(local_media_args([*nice, self.rembg, *rembg_args(self.model, src, res)]), capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=limit)
            except subprocess.TimeoutExpired:
                raise Fail(f"rembg did not finish in {round(limit)} s: a shorter span or --width 720")
            if r.returncode != 0:
                raise Fail(f"rembg failed (code {r.returncode}): {(r.stderr or r.stdout).strip()[-600:]}")
            if not any(res.glob("*.png")):
                raise Fail("rembg produced no frames")
            run([*nice, *pack_cmd(fps, ["-i", res / "%05d.png"], dst)])
        r = subprocess.run(local_media_args([sys.executable, "-c", BBOX, str(res)]), capture_output=True, text=True)
        if r.returncode != 0:
            raise Fail("the figure's box was not computed (this Python needs Pillow: pip install Pillow): "
                       + r.stderr.strip()[-300:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def cleanup(self):
        pass


def cmd_cut(a, engine=None):
    """engine: a class built from the arguments, with check(n_mpx, model), run(src, fps, limit, wait, dst) -> the
    figure's box, cleanup(); default Local (rembg on this computer)."""
    if not NAME_RE.match(a.name):
        sys.exit(f"--name {a.name!r}: Latin letters, digits, _ and - only (up to 40 characters): the name goes into "
                 f"file names")
    a.name = safe_slug(a.name, "--name", dots=True)
    e = edit_dir(a.edit)
    inside(e, e / "matte" / f"{a.name}.json", "matte output")
    inside(e, e / "matte" / f"{a.name}.webm", "matte output")
    inside(e, e / "matte" / f"{a.name}-check.png", "matte output")
    video = Path(a.video) if a.video else e / "final.mp4"
    if not video.exists():
        sys.exit(f"no {video}")
    pr = probe(video)
    fps = int(a.fps or round(pr["fps"] or 30) or 30)
    dur = a.end - a.start
    if dur <= 0:
        sys.exit("--to must be greater than --from")
    n = round(dur * fps)
    width = int(a.width)
    height = round(width * 16 / 9 / 2) * 2
    mpx = width * height / 1e6
    est = n * mpx * SEC_PER_MPX + 45  # + model start and transfer (measured: 30 frames at 720p took 62 s)
    print(f"span {a.start:.2f}-{a.end:.2f} s: {n} frames {width}x{height}, estimate about {est / 60:.1f} min"
          + (": long; cut out only the parts where the figure is really needed" if est > 900 else ""))
    if a.dry:
        return
    eng = (engine or Local)(a)
    why = eng.check(n * mpx, a.model)
    if why:
        warn(why)
        sys.exit("no cut-out; replace the technique (a slide scene or the window layout without a cut-out)")
    out = e / "matte"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"{a.name}.webm"
    tmp = Path(tempfile.mkdtemp(prefix="matte-"))
    t0 = time.time()
    try:
        # 1. JPG frames (a 1080x1920 PNG is many times larger: slower to move and to read)
        src = tmp / "in"
        src.mkdir()
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a.start:.3f}", "-to", f"{a.end:.3f}", "-i", video,
             "-vf", f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
             "-q:v", "2", src / "%05d.jpg"])
        frames = sorted(src.glob("*.jpg"))
        if not frames:
            raise Fail("ffmpeg produced no frames for the span")
        # 2. rembg + packaging with edge cleanup, one at a time; memory checked again under the lock
        limit = max(300, est * 3)
        info = eng.run(src, fps, limit, a.wait * 60, dst)
        if not info["frames"]:
            raise Fail("rembg produced no frames")
    except (Fail, RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as ex:
        sys.exit(f"no cut-out: {ex}")
    finally:
        eng.cleanup()
        shutil.rmtree(tmp, ignore_errors=True)
    k = W / info["w"]
    bbox = [round(v * k) for v in info["bbox"]] if info["bbox"] else None
    touch, terr = edge_touch(dst)
    meta = {"from": a.start, "to": a.end, "fps": fps, "frames": info["frames"], "width": width, "model": a.model,
            "video": str(video), "webm": str(dst), "empty_frames": info["empty"],
            "bbox": bbox, "head_top": round(info["head_top_min"] * k) if info["head_top_min"] is not None else None,
            "seconds": round(time.time() - t0), "touch": touch}
    save_json(out / f"{a.name}.json", meta)
    al = run(["ffprobe", "-v", "error", "-show_entries", "stream_tags=alpha_mode", "-of", "csv=p=0", dst], check=False).stdout.strip()
    print(f"{dst}: {info['frames']} frames in {meta['seconds']} s, alpha: {'yes' if al == '1' else 'NO'}; "
          f"figure (in 1080x1920 coordinates) {bbox}, top of the head y {meta['head_top']}"
          + (f"; frames without the figure: {info['empty']}" if info["empty"] else ""))
    errors = []
    if al != "1":
        errors.append("the WebM has no alpha (alpha_mode != 1): the figure would be a rectangle; rebuild it")
    if touch is None:
        errors.append(f"the source-edge check was not performed ({terr}): place will not work without it")
    # check frame: the middle of the span over a light and a dark background; a fringe shows on one of them, stuck
    # furniture or a piece of wall on both
    chk = out / f"{a.name}-check.png"
    r = check_frame(dst, dur / 2, chk)
    if r.returncode == 0 and chk.exists():
        print(f"check frame: {chk}: look at it before the layout: a fringe, furniture or wall in the mask, cut-off fingers")
    else:
        errors.append(f"the check frame was not built: {r.stderr.strip()[-300:]}")
    if touch:
        cut = [f"{k} ({touch[k]} of {touch['frames']} frames)" for k in ("left", "right", "top", "bottom") if touch[k]]
        if cut:
            print("source-edge cuts, the figure touches the edge: " + ", ".join(cut) + ". In the layout these edges of "
                  "the figure must coincide with the frame edges (matte.py place picks the side itself)")
        if touch.get("inner"):
            print(f"\u26a0 the figure ends inside its frame (a table or a laptop in front of it) in {touch['inner']} of "
                  f"{touch['frames']} frames, source y {touch['inner_y'][0]}-{touch['inner_y'][1]}: a straight cut that "
                  f"no source edge hides; matte.py place says where it lands on screen")
    for x in errors:
        print("✗ " + x)
    if errors:
        sys.exit(1)


def check_frame(webm, at, chk):
    """The figure at second `at` of the WebM over a light and a dark background, side by side (540x960 each).
    setpts=PTS-STARTPTS: after -ss the figure's first frame arrives a few ms after 0 (WebM keeps milliseconds, the
    span rarely starts on the frame grid), the color backgrounds start at 0, and overlay's first frame had only the
    backgrounds (T2: an empty check frame). The libvpx-vp9 decoder is required: the built-in vp9 decoder loses alpha."""
    return run(["ffmpeg", "-v", "error", "-y", "-c:v", "libvpx-vp9", "-ss", f"{at:.2f}", "-i", webm, "-f", "lavfi",
                "-i", "color=c=0xF4F4F2:s=540x960", "-f", "lavfi", "-i", "color=c=0x0B1A33:s=540x960", "-filter_complex",
                "[0:v]setpts=PTS-STARTPTS,scale=540:960,split[p1][p2];[1:v][p1]overlay=shortest=1[l];"
                "[2:v][p2]overlay=shortest=1[d];[l][d]hstack", "-frames:v", "1", chk], check=False)


def presenter_face(fdata, t0, t1):
    """The presenter's face over the span: in each sample the largest face (the presenter is closer to the camera than
    the background and B-roll), its height the median (head movement does not inflate the scale, as a union would);
    the box is the union of these faces, for the checks."""
    if not fdata:
        return None, None
    st = fdata.get("step", 0.25)
    main = [max(s["faces"], key=lambda f: f[2] * f[3])[:4] for s in fdata["samples"]
            if t0 - st <= s["t"] <= t1 + st and s["faces"]]
    if not main:
        return None, None
    hs = sorted(f[3] for f in main)
    x0 = min(f[0] for f in main); y0 = min(f[1] for f in main)
    x1 = max(f[0] + f[2] for f in main); y1 = max(f[1] + f[3] for f in main)
    return hs[len(hs) // 2], [x0, y0, x1 - x0, y1 - y0]


def cmd_place(a):
    import faces as fc
    if not NAME_RE.fullmatch(a.name):
        sys.exit(f"--name {a.name!r}: Latin letters, digits, _ and - only (up to 40 characters)")
    a.name = safe_slug(a.name, "--name", dots=True)
    e = edit_dir(a.edit)
    inside(e, e / "matte" / f"{a.name}.json", "matte output")
    inside(e, e / "matte" / f"{a.name}.webm", "matte output")
    meta = load_json(e / "matte" / f"{a.name}.json")
    if not meta:
        sys.exit(f"no {e / 'matte' / (a.name + '.json')}: run matte.py cut first")
    L = LAYOUTS[a.layout]
    # faces in the cut-out's coordinates: cut crops the video as a centered 9:16 cover, so a measurement in source
    # geometry (a horizontal "framed" video) is mapped into a full-frame window, not into the framed window
    face_h, face = presenter_face(fc.load(e, frame=(0, 0, W, H)), meta["from"], meta["to"])
    if not face:
        warn("no face on the span in faces.json (faces.py scan): scale by the figure's box")
    target = a.face or L["face"]
    if face_h:
        s = target / face_h
    else:
        b = meta["bbox"] or [0, 0, W, H]
        s = 0.62 * H / (b[3] - b[1]) * (0.75 if a.layout == "review" else 0.5)
    want = s
    s = round(min(s, 1.0), 3)
    # Source-edge cuts. Where the figure touches the edge of its own frame (an arm, an elbow, the bottom of the body),
    # the cut-out has a straight cut. It is allowed only on an edge of our frame: the corner's side follows the cut.
    touch = meta.get("touch")
    if (touch is None or "inner" not in touch) and meta.get("webm") and Path(meta["webm"]).exists():
        # no data, or an older file without the inner-cut check
        new, terr = edge_touch(meta["webm"])
        if new:
            touch = meta["touch"] = new
    if touch is None:
        sys.exit("✗ the source-edge check was not performed (no touch data and the webm can't be read): the layout is "
                 "not computed; rebuild with matte.py cut")
    tl, tr, tt, tb = (touched(touch, k) for k in ("left", "right", "top", "bottom"))
    issues = []
    side = a.side
    if side == "auto":
        side = "left" if tl and not tr else "right" if tr and not tl else ("right" if a.layout == "stream" else "left")
    # corner: the bottom of the figure's video = the bottom of the frame, its side edge = the frame's side edge (the
    # source-edge cuts go past the frame edge)
    ox = 0 if side == "left" else W - W * s
    oy = H - H * s
    if a.layout == "review" and face:
        # "review": the forehead at the panel's bottom edge (the hair overlaps the panel a little: depth), the body goes
        # off the bottom of the frame. If the bottom of the figure's video rises above the frame bottom (a cut shows), pin it down.
        px, py, pw, ph = L["panel"]
        oy = max(H - H * s, (py + ph - 10) - face[1] * s)
    # the cut check in screen coordinates, at any scale: every edge the figure touches lies on the frame edge or beyond
    if tl and tr and s < 1:
        issues.append("the figure touches both the left and the right source edge (arms spread): it can't go in a "
                      "corner, a cut would show on one side. Take a span without this gesture, the window layout or "
                      "a full-frame figure (x1)")
    else:
        if tl and ox > 0.5:
            issues.append(f"the figure touches the left source edge, but its left edge on screen is at x {round(ox)}: a "
                          f"chopped-off arm would show in the middle of the frame. Side left (or --side auto)")
        if tr and ox + W * s < W - 0.5:
            issues.append(f"the figure touches the right source edge, but its right edge on screen is at x "
                          f"{round(ox + W * s)}: a chopped-off arm in the middle of the frame. Side right (or --side auto)")
    if tt and oy > 0.5:
        issues.append(f"the top of the head or the hair touches the top of the source, but the top of the figure on "
                      f"screen is at y {round(oy)}: the cut above the head would show; take a span with the whole head "
                      f"in frame, or window")
    if tb and oy + H * s < H - 0.5:
        issues.append("the bottom of the figure is cut by the source, but the layout lifts it above the bottom of the "
                      "frame: move the figure down")
    to = lambda b: [round(ox + b[0] * s), round(oy + b[1] * s), round(b[2] * s), round(b[3] * s)]
    bb = meta["bbox"]
    fig = to([bb[0], bb[1], bb[2] - bb[0], bb[3] - bb[1]]) if bb else None
    fscr = to(face) if face else None
    # the face on screen is face_h x s: with the scale capped at x1.0 the target is not reached (T2 printed "216 ->
    # 260 px" while the face stayed 216)
    print(f"layout {a.layout} ({L['note']}), side {side}"
          + (" (picked by the source-edge cut)" if a.side == "auto" and (tl or tr) else "") + f": figure scale x{s}"
          + (f" (presenter's face {face_h} px -> {round(face_h * s)} px on screen"
             + (f"; the target {target} px needs x{want:.2f}, the figure is never scaled above x1.0" if want > s + 1e-3
                else "") + ")" if face_h else ""))
    print(f"  figure on screen {fig}; face area {fscr}")
    notes = []
    up = s * W / (meta.get("width") or W)
    if up > 1.02:
        notes.append(f"the cut-out is {meta.get('width')} px wide and is shown at {round(W * s)} px: x{up:.2f} of its "
                     f"own pixels, soft edges; cut it at --width 1080")
    inner = touch.get("inner_y") if touch.get("inner") else None
    line = None
    if inner:
        line = [round(oy + inner[0] * s), round(oy + inner[1] * s)]
        if line[0] < H - 0.5:
            notes.append(f"the figure ends inside its own frame (a table or a laptop: source y {inner[0]}-{inner[1]}, no "
                         f"source edge there): that cut shows on screen at y {line[0]}-{min(line[1], H)}. Hide it behind "
                         f"an opaque element across the whole width from y {line[0]} down (a plate in the background "
                         f"color, a lower third, the panel), or use the window layout")
    if fscr:
        if fscr[1] + fscr[3] > H - UI_BOTTOM:
            issues.append(f"the chin at {fscr[1] + fscr[3]} is in the UI zone (> {H - UI_BOTTOM}): a smaller --face, "
                          f"another side or layout")
        if a.layout == "review":
            px, py, pw, ph = L["panel"]
            if fscr[1] < py + ph - 30:
                issues.append(f"the face (top {fscr[1]}) overlaps the scene panel (bottom {py + ph}): a shorter panel "
                              f"or a smaller --face")
        if side == "right" and fscr[0] + fscr[2] > W - UI_RIGHT:
            issues.append("the face is under the like-button column on the right: side left")
    for x in issues + notes:
        print("  ⚠ " + x)
    props = {"src": f"<id>/{a.name}.webm", "from": meta["from"], "dur": round(meta["to"] - meta["from"], 3),
             "layout": a.layout, "side": side, "scale": s, "x": round(ox), "y": round(oy), "panel": L["panel"] if a.layout == "review" else None}
    # the zone of the presenter layer: its own face is not a no-go for it (validate and faces.py audit skip it), the
    # span counts in the inserts' coverage, and export copies the WebM to public/<id>/
    keep = {"start": meta["from"], "end": meta["to"], "box": fig, "what": f"presenter ({a.name})", "matte": a.name}
    if fscr:
        keep["own_face"] = fscr
    meta["place"] = {"props": props, "keep_clear": keep, "face_screen": fscr, "issues": issues, "notes": notes,
                     "inner_cut_screen": line}
    save_json(e / "matte" / f"{a.name}.json", meta)
    print(f"  Presenter props: {json.dumps(props, ensure_ascii=False)}")
    if fig:
        print(f"  keep-clear: python scripts/visual_plan.py keep-clear {a.edit} --from {meta['from']} --to {meta['to']} "
              f"--box {','.join(map(str, fig))} --what \"presenter\" --matte {a.name}"
              + (f" --own-face {','.join(map(str, fscr))}" if fscr else ""))
    if issues:
        sys.exit(1)


def parser(prog=None, doc=__doc__):
    """The command line (the online add-on builds its own on top of it). -> (parser, the cut subparser)."""
    ap = argparse.ArgumentParser(prog=prog, description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = cut = sub.add_parser("cut"); p.add_argument("edit")
    p.add_argument("--from", dest="start", type=float, required=True); p.add_argument("--to", dest="end", type=float, required=True)
    p.add_argument("--width", type=int, default=1080, help="1080 (default); 720 only when place gives a scale <= 0.66")
    p.add_argument("--fps", type=float)
    p.add_argument("--name", default="person"); p.add_argument("--video"); p.add_argument("--model", default="u2net_human_seg")
    p.add_argument("--wait", type=float, default=20, help="minutes to wait for the cut-out queue (one at a time)")
    p.add_argument("--rembg", help="the rembg command or its path (default: REELS_MATTE_REMBG, then matte.rembg in "
                                   "it-reelsmaker.json, then rembg on PATH)")
    p.add_argument("--dry", action="store_true"); p.set_defaults(fn=cmd_cut)
    p = sub.add_parser("place"); p.add_argument("edit"); p.add_argument("--name", default="person")
    p.add_argument("--layout", choices=list(LAYOUTS), default="review"); p.add_argument("--side", choices=["auto", "left", "right"], default="auto")
    p.add_argument("--face", type=int); p.set_defaults(fn=cmd_place)
    return ap, cut


def main(argv=None):
    utf8_stdio()
    ap, _ = parser()
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
