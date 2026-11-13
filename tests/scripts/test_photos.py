"""Photo reels (references/no-speaker.md, "Photos"): photos as the picture of a voice-over or a no-speech reel.

What the person needs, in words:
- A phone photo shot sideways or mirrored (an EXIF orientation tag 2-8) looks the same everywhere: on the contact sheet
  the agent picks the focus from, in the sizes the scripts measure, in the prepared shot and in the face search, with
  any ffmpeg version (some turn a photo by its tag and some do not). A photo with no tag is prepared exactly as before.
- A photo shot may name its subject, an ROI (a region of the upright photo, or "face": the faces on it, a group as one
  box): a push ends on the ROI, a pull starts on it, a still frame centers it, a pan travels along it. The whole path
  is checked frame by frame: the ROI stays in frame on every frame (for a pan its height does), and an ROI that cannot
  fit even the whole 9:16 frame is an error with numbers and advice before anything is encoded. A push goes deeper
  than the usual slow push-in only as far as the photo's pixels allow (the deepest frame still has as many source
  pixels as the video frame), and never past x2. Without an ROI a shot moves as before.
- A small photo (its full 9:16 frame is less than 3/4 of the video frame wide) is shown whole on a blurred background
  with a warning, unless the shot says fit "cover" explicitly (then it stays, with a warning that it will be soft).
- A layout scene (panel, window) over a photo with an ROI frames the ROI where it is on screen, not a default face.
- Many photos in a row should not look like a slideshow: three or more photos in a row with the same motion, or four
  or more with no "hero" (none held longer than 1.5 times the others' median), are warnings in cut.py and validate.
  A deliberate photo reel (alternating motion, one hero) passes without a warning.
- An iPhone's HEIC (a grid of tiles, often stored on its side with HEIF's own rotation) is footage like a JPEG:
  indexed with its upright size, upright on the sheet, in a picture shot, a B-roll photo and cut.py; a scene given
  one gets an upright JPEG (the kit's browser shows no HEIC). A HEIC this ffmpeg cannot read (cut off mid-copy, an
  ffmpeg older than 7.1) stops with the photo's name and "export it as JPEG", never with one tile of it.
"""
import json
import subprocess

import pytest

from conftest import CORE, ffmpeg, needs_ffmpeg, needs_pillow, run_script, write_json

pytestmark = needs_pillow

W, H = 1080, 1920
QUAD = {"tl": (230, 20, 20), "tr": (20, 200, 20), "bl": (20, 20, 230), "br": (240, 240, 240)}
# the method that undoes each orientation's display transform (Pillow names), so a stored picture S with tag o
# displays as the upright R: S = R.transpose(INVERSE[o])
INVERSE = {2: "FLIP_LEFT_RIGHT", 3: "ROTATE_180", 4: "FLIP_TOP_BOTTOM", 5: "TRANSPOSE", 6: "ROTATE_90",
           7: "TRANSVERSE", 8: "ROTATE_270"}


def upright_ref(w=300, h=400):
    """An upright picture whose four quadrants have four colors: any turn or mirror shows."""
    from PIL import Image
    im = Image.new("RGB", (w, h))
    for (x0, y0), c in zip(((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2)), QUAD.values()):
        im.paste(c, (x0, y0, x0 + w // 2, y0 + h // 2))
    return im


def tagged(path, ref, o):
    """Store ref as a phone would: the pixels as the sensor read them and the orientation tag o that turns them back."""
    from PIL import Image
    stored = ref if o == 1 else ref.transpose(getattr(Image.Transpose, INVERSE[o]))
    ex = Image.Exif()
    if o != 1:
        ex[0x0112] = o
    kw = {"exif": ex.tobytes()} if o != 1 else {}
    if path.suffix.lower() in (".jpg", ".jpeg"):
        kw["quality"] = 95
    stored.save(path, **kw)
    return path


def frame_rgb(f, t=None, k=None, size=(108, 192)):
    """One frame of a video (at second t, or frame k) shrunk to size, as rows of RGB tuples."""
    sel = ["-ss", f"{t:.3f}"] if t is not None else []
    vf = f"select=eq(n\\,{k}),scale={size[0]}:{size[1]}" if k is not None else f"scale={size[0]}:{size[1]}"
    r = subprocess.run(["ffmpeg", "-v", "error", *sel, "-i", str(f), "-vf", vf, "-frames:v", "1", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    b = r.stdout
    return [[tuple(b[(y * size[0] + x) * 3:(y * size[0] + x) * 3 + 3]) for x in range(size[0])] for y in range(size[1])]


def near(c, ref, tol=60):
    return all(abs(a - b) <= tol for a, b in zip(c, ref))


def quadrants_of(rows):
    h, w = len(rows), len(rows[0])
    return {"tl": rows[h // 4][w // 4], "tr": rows[h // 4][3 * w // 4], "bl": rows[3 * h // 4][w // 4],
            "br": rows[3 * h // 4][3 * w // 4]}


# --- EXIF orientation: one upright photo everywhere ----------------------------------------------------------------

@pytest.mark.parametrize("ext", [".jpg", ".png", ".webp"])
def test_the_orientation_tag_is_read_from_every_photo_format(tmp_path, ext):
    import reels_common
    ref = upright_ref()
    for o in range(1, 9):
        p = tagged(tmp_path / f"o{o}{ext}", ref, o)
        assert reels_common.photo_orientation(p) == o, (ext, o)
    (tmp_path / f"broken{ext}").write_bytes(b"\xff\xd8\xff\xe1\x00\x10Exif\x00\x00MM\x00*")  # a cut-off header
    assert reels_common.photo_orientation(tmp_path / f"broken{ext}") == 1
    (tmp_path / f"empty{ext}").write_bytes(b"")
    assert reels_common.photo_orientation(tmp_path / f"empty{ext}") == 1


def test_the_upright_photo_is_the_one_a_phone_shows_for_every_orientation(tmp_path):
    from PIL import ImageOps
    import reels_common
    ref = upright_ref()
    for o in range(1, 9):
        p = tagged(tmp_path / f"o{o}.png", ref, o)  # lossless: the pixels compare exactly
        from PIL import Image
        oracle = ImageOps.exif_transpose(Image.open(p)).convert("RGB")  # how a phone and a browser show it
        assert list(oracle.getdata()) == list(ref.getdata()), o  # the fixture itself is right
        up = reels_common.upright_image(p)
        assert up.size == ref.size and list(up.convert("RGB").getdata()) == list(ref.getdata()), o
        assert reels_common.upright_size(p) == ref.size, o


@needs_ffmpeg
def test_a_sideways_phone_photo_has_its_upright_size(tmp_path):
    import reels_common
    ref = upright_ref(300, 400)
    side = tagged(tmp_path / "side.jpg", ref, 6)
    flat = tagged(tmp_path / "flat.jpg", ref, 1)
    assert (reels_common.probe(side)["w"], reels_common.probe(side)["h"]) == (300, 400)
    assert (reels_common.probe(flat)["w"], reels_common.probe(flat)["h"]) == (300, 400)


@needs_ffmpeg
@pytest.mark.parametrize("o", [2, 3, 5, 6, 7, 8])
def test_a_prepared_photo_shot_shows_the_photo_upright(tmp_path, o):
    import footage
    ref = upright_ref(1200, 1600)
    p = tagged(tmp_path / f"o{o}.jpg", ref, o)
    for strict in (True, False):  # a picture shot of cut.json and a B-roll photo
        out = tmp_path / f"o{o}-{strict}.mp4"
        footage.prepare(p, out, 0.5, strict=strict, move="still" if strict else None)
        q = quadrants_of(frame_rgb(out, k=0))
        assert all(near(q[k], QUAD[k]) for k in QUAD), (o, strict, q)


@needs_ffmpeg
def test_an_ffmpeg_that_ignores_the_tag_gets_the_right_turn(tmp_path):
    """An older ffmpeg does not apply the tag: the scripts then turn the photo with their own filter. Shown here with
    the tag hidden from this ffmpeg (-noautorotate) and the frame read straight into a PNG."""
    from PIL import Image
    import reels_common
    ref = upright_ref(300, 400)
    for o in range(2, 9):
        p = tagged(tmp_path / f"o{o}.png", ref, o)
        out = tmp_path / f"u{o}.png"
        ffmpeg("-noautorotate", "-i", p, "-vf", reels_common.ORIENT_VF[o], "-frames:v", "1", out)
        assert list(Image.open(out).convert("RGB").getdata()) == list(ref.getdata()), o


@needs_ffmpeg
def test_a_photo_with_no_tag_is_given_to_ffmpeg_as_before(tmp_path):
    import reels_common
    p = tagged(tmp_path / "flat.jpg", upright_ref(), 1)
    assert reels_common.photo_input(p) == ([], "")


@needs_ffmpeg
def test_the_scripts_turn_the_photo_only_when_ffmpeg_will_not(tmp_path, monkeypatch):
    import reels_common
    p = tagged(tmp_path / "o6.jpg", upright_ref(), 6)
    monkeypatch.setattr(reels_common, "ffmpeg_turns", lambda f: False)  # an older ffmpeg: it ignores the tag
    assert reels_common.photo_input(p) == ([], "transpose=1")
    monkeypatch.setattr(reels_common, "ffmpeg_turns", lambda f: True)  # a newer one turns it itself: no second turn
    assert reels_common.photo_input(p) == ([], "")


@needs_ffmpeg
def test_this_ffmpeg_is_asked_whether_it_turns_a_photo(tmp_path):
    """The answer is read from the file as this ffmpeg decodes it, not guessed from a version number: a turned
    photo prepared by the scripts is upright either way (test_a_prepared_photo_shot_shows_the_photo_upright), and a
    photo without a tag is never reported as turned."""
    import reels_common
    flat = tagged(tmp_path / "flat.jpg", upright_ref(), 1)
    assert reels_common.ffmpeg_turns(flat) is False


def test_a_jpeg_with_fill_bytes_before_its_exif_keeps_its_orientation(tmp_path):
    """Review of phase 3: a JPEG may pad a marker with 0xFF bytes; Pillow reads the tag through them."""
    import reels_common
    from PIL import Image
    p = tagged(tmp_path / "o6.jpg", upright_ref(), 6)
    b = p.read_bytes()
    i = b.index(bytes([0xFF, 0xE1]))
    padded = tmp_path / "padded.jpg"
    padded.write_bytes(b[:i] + bytes([0xFF, 0xFF]) + b[i + 1:])
    assert Image.open(padded).getexif().get(0x0112) == 6  # the fixture is a JPEG Pillow still reads the tag of
    assert reels_common.photo_orientation(padded) == 6


@needs_ffmpeg
def test_the_contact_sheet_and_the_index_show_a_photo_upright(project):
    (project / "photos").mkdir()
    tagged(project / "photos" / "side.jpg", upright_ref(300, 400), 6)
    run_script("footage.py", "index", "--dir", "photos", cwd=project)
    from PIL import Image
    sheet = Image.open(project / "_footage_index" / "photos-sheet-00.jpg").convert("RGB")
    # the strip's first thumbnail: 300x400 shrunk into 160 px wide -> 160x213 at the top left
    assert near(sheet.getpixel((30, 40)), QUAD["tl"]) and near(sheet.getpixel((130, 40)), QUAD["tr"])
    assert near(sheet.getpixel((30, 170)), QUAD["bl"]) and near(sheet.getpixel((130, 170)), QUAD["br"])
    idx = json.loads((project / "footage_index.json").read_text(encoding="utf-8"))
    assert (idx["photos/side.jpg"]["w"], idx["photos/side.jpg"]["h"]) == (300, 400)


# --- the ROI and the path of the move ------------------------------------------------------------------------------

def inside(win, box, eps=0.51):
    x, y, w, h = win
    x0, y0, x1, y1 = box
    return x - eps <= x0 and y - eps <= y0 and x1 <= x + w + eps and y1 <= y + h + eps


def in_image(win, size, eps=0.51):
    x, y, w, h = win
    return x >= -eps and y >= -eps and x + w <= size[0] + eps and y + h <= size[1] + eps


def aspect_ok(win):
    return abs(win[2] / win[3] - W / H) < 0.01


def roi_px(roi, size):
    return (roi[0] * size[0], roi[1] * size[1], roi[2] * size[0], roi[3] * size[1])


def test_a_push_ends_on_the_roi_and_keeps_it_in_frame_on_every_frame():
    import photo_move as pm
    size, roi, n = (3000, 4000), (0.55, 0.2, 0.75, 0.32), 90
    p = pm.plan(size, (W, H), n, "push", roi=roi)
    box = roi_px(roi, size)
    first, last = pm.window(p, 0), pm.window(p, n - 1)
    assert first[3] == pytest.approx(4000, abs=1) or first[2] == pytest.approx(3000, abs=1)  # the whole 9:16 frame
    assert last[2] < first[2] / 1.2  # it really goes in
    assert last[2] >= W - 0.5  # no deeper than the photo's pixels
    assert first[2] / last[2] <= 2.0 + 1e-6
    for k in range(n):
        win = pm.window(p, k)
        assert inside(win, box) and in_image(win, size) and aspect_ok(win), (k, win)
    # the ROI with some room around it at the end, not glued to the frame's edges
    x, y, w, h = last
    assert box[0] - x > 0.05 * w and (x + w) - box[2] > 0.05 * w


def test_a_pull_is_the_push_backwards_and_a_still_frame_centers_the_roi():
    import photo_move as pm
    size, roi, n = (3000, 4000), (0.55, 0.2, 0.75, 0.32), 60
    push, pull = pm.plan(size, (W, H), n, "push", roi=roi), pm.plan(size, (W, H), n, "pull", roi=roi)
    for k in range(n):
        assert pm.window(pull, k) == pytest.approx(pm.window(push, n - 1 - k), abs=1e-6)
    roi = (0.45, 0.2, 0.6, 0.32)  # centered at 1575 px: the 2250 px frame around it is not clamped by the edges
    still = pm.plan(size, (W, H), n, "still", roi=roi)
    assert pm.window(still, 0) == pytest.approx(pm.window(still, n - 1))
    x, y, w, h = pm.window(still, 0)
    box = roi_px(roi, size)
    assert inside((x, y, w, h), box)
    assert x + w / 2 == pytest.approx((box[0] + box[2]) / 2, abs=2)  # centered (not clamped here)


def test_a_pan_travels_along_a_wide_group_and_keeps_its_height_in_frame():
    import photo_move as pm
    size, roi, n = (4000, 3000), (0.1, 0.35, 0.9, 0.65), 120
    p = pm.plan(size, (W, H), n, "pan", roi=roi)
    box = roi_px(roi, size)
    xs = [pm.window(p, k)[0] for k in range(n)]
    assert xs == sorted(xs) and xs[-1] - xs[0] > 0.3 * size[0]  # left to right, a real travel
    for k in range(n):
        x, y, w, h = pm.window(p, k)
        assert aspect_ok((x, y, w, h)) and in_image((x, y, w, h), size)
        assert y <= box[1] + 0.5 and box[3] <= y + h + 0.5  # the group's height is in frame on every frame
        assert box[0] - 0.15 * w <= x and x + w <= box[2] + 0.15 * w  # it stays on the group
    first, last = pm.window(p, 0), pm.window(p, n - 1)
    assert first[0] <= box[0] and last[0] + last[2] >= box[2]  # it starts at the group's left end and ends at its right


def test_a_pan_over_a_subject_that_fits_keeps_all_of_it_in_frame():
    import photo_move as pm
    size, roi, n = (4000, 3000), (0.45, 0.3, 0.55, 0.5), 90
    p = pm.plan(size, (W, H), n, "pan", roi=roi)
    box = roi_px(roi, size)
    for k in range(n):
        assert inside(pm.window(p, k), box)
    assert pm.window(p, n - 1)[0] - pm.window(p, 0)[0] > 0.05 * pm.window(p, 0)[2]


def test_a_pan_over_a_subject_almost_as_wide_as_the_frame_keeps_all_of_it():
    """Review of phase 3: an ROI 1600 px wide in a 1688 px frame went the "wide" way and lost 81 px at each end."""
    import photo_move as pm
    size, roi, n = (4000, 3000), (0.3, 0.3, 0.7, 0.5), 90
    p = pm.plan(size, (W, H), n, "pan", roi=roi)
    box = roi_px(roi, size)
    for k in range(n):
        assert inside(pm.window(p, k), box), k
    assert pm.check(p) == []


def test_a_push_on_a_photo_with_few_pixels_stays_at_the_usual_slow_push_in():
    import photo_move as pm
    size, roi, n = (1500, 2000), (0.45, 0.45, 0.5, 0.5), 60  # the full frame is 1125 px wide: no room to go in
    p = pm.plan(size, (W, H), n, "push", roi=roi)
    first, last = pm.window(p, 0), pm.window(p, n - 1)
    assert first[2] / last[2] == pytest.approx(1 + pm.MOVE_Z, abs=0.005)
    big = pm.plan((6000, 8000), (W, H), n, "push", roi=(0.5, 0.5, 0.51, 0.505))  # a tiny ROI on a huge photo
    assert pm.window(big, 0)[2] / pm.window(big, n - 1)[2] == pytest.approx(2.0, abs=1e-3)  # the x2 ceiling


@pytest.mark.parametrize("move", ["push", "pull", "still", "none"])
def test_an_roi_that_cannot_fit_the_frame_is_an_error_with_numbers(move):
    import photo_move as pm
    with pytest.raises(pm.PhotoError) as x:
        pm.plan((4000, 3000), (W, H), 60, move, roi=(0.05, 0.45, 0.95, 0.55))
    msg = str(x.value)
    assert "3600" in msg and "1688" in msg and "pan" in msg and "contain" in msg, msg


def test_a_small_photo_is_shown_whole_unless_cover_is_asked_for():
    import photo_move as pm
    fit, warns = pm.fit_for((600, 800), (W, H), None)
    assert fit == "contain" and warns and "small" in warns[0]
    fit, warns = pm.fit_for((600, 800), (W, H), "cover")
    assert fit == "cover" and warns and "soft" in warns[0]
    assert pm.fit_for((3000, 4000), (W, H), None) == ("cover", [])
    assert pm.fit_for((600, 800), (W, H), "contain") == ("contain", [])


@needs_ffmpeg
def test_the_rendered_push_follows_its_path_on_a_sideways_photo(tmp_path):
    """The red subject is where the path puts it on the first, middle and last frame: the plan and the picture agree,
    and the ROI is given on the upright photo though the file is stored sideways."""
    from PIL import Image, ImageDraw
    import footage
    import photo_move as pm
    size, roi, n = (1600, 2400), (0.6, 0.15, 0.85, 0.3), 45
    ref = Image.new("RGB", size, (40, 40, 40))
    ImageDraw.Draw(ref).rectangle(roi_px(roi, size), fill=(230, 20, 20))
    p = tagged(tmp_path / "side.jpg", ref, 6)
    out = tmp_path / "push.mp4"
    footage.prepare(p, out, n / 30, strict=True, move="push", roi=roi)
    plan = pm.plan(size, (W, H), n, "push", roi=roi)
    for k in (0, n // 2, n - 1):
        x, y, w, h = pm.on_screen(plan, k)
        rows = frame_rgb(out, k=k, size=(W // 10, H // 10))
        cx, cy = round((x + w / 2) / 10), round((y + h / 2) / 10)
        assert near(rows[cy][cx], (230, 20, 20)), (k, rows[cy][cx])
        ox = round(max(0, x - 40) / 10)  # just left of the subject: the gray wall
        assert near(rows[cy][ox], (40, 40, 40), 40), (k, rows[cy][ox])


def test_the_rendered_crop_never_shaves_the_roi(monkeypatch):
    """Review of phase 3: a crop rounded to whole pixels on its own could cut up to a pixel off the ROI's edge. The crop
    the renderer asks for holds the planned window (and so the ROI) on every side."""
    import re
    import footage
    import photo_move as pm
    for size, roi, move in (((4000, 3007), (1200.49 / 4000, 0.3, 2891.9275 / 4000, 0.5), "still"),
                            ((3001, 4003), (0.4011, 0.2017, 0.5513, 0.3019), "push"),
                            ((3001, 4003), (0.4011, 0.2017, 0.5513, 0.3019), "pull")):
        p = pm.plan(size, (W, H), 45, move, roi=roi)
        body = footage.roi_body(p, "", W, H, 30)
        cw, ch, cx, cy = map(int, re.search(r"crop=(\d+):(\d+):(\d+):(\d+)", body).groups())
        big = max((p["start"], p["end"]), key=lambda v: v[2])
        assert cx <= big[0] + 1e-6 and cy <= big[1] + 1e-6, (move, body)
        assert cx + cw >= big[0] + big[2] - 1e-6 and cy + ch >= big[1] + big[3] - 1e-6, (move, body)


@needs_ffmpeg
def test_a_small_photo_shown_whole_is_not_blown_up(tmp_path):
    """A 600x800 photo with a white border: shown whole at most x1.25 (750 px wide, centered), not stretched to 1080."""
    from PIL import Image, ImageDraw
    import footage
    im = Image.new("RGB", (600, 800), (230, 20, 20))
    ImageDraw.Draw(im).rectangle((0, 0, 599, 799), outline=(255, 255, 255), width=12)
    p = tmp_path / "small.jpg"
    im.save(p, quality=95)
    out = tmp_path / "small.mp4"
    footage.prepare(p, out, 0.5, strict=True, fit="contain", move="still")
    rows = frame_rgb(out, k=0, size=(W // 4, H // 4))
    y = H // 8  # a row through the middle of the frame
    xs = [x for x in range(W // 4) if min(rows[y][x]) > 200]  # the white border's columns
    assert xs and abs(xs[0] * 4 - (W - 750) / 2) <= 12 and abs(xs[-1] * 4 - (W + 750) / 2) <= 12, xs


def test_the_face_roi_is_the_box_around_every_face_of_the_upright_photo(tmp_path, monkeypatch):
    import cut_picture
    import faces
    seen = {}

    def fake_detect(paths, scale=1.0, thr=0.6):
        from PIL import Image
        seen["size"] = Image.open(paths[0]).size
        return [[[100, 200, 80, 100, 0.95], [400, 250, 90, 110, 0.93]]]

    monkeypatch.setattr(faces, "detect", fake_detect)
    p = tagged(tmp_path / "group.jpg", upright_ref(1200, 1600), 6)
    roi = cut_picture.face_roi(p, "picture[0] shot 1")
    assert seen["size"] == (720, 960)  # the faces are looked for on the upright photo
    assert roi == pytest.approx((100 / 720, 200 / 960, 490 / 720, 360 / 960), abs=1e-3)
    monkeypatch.setattr(faces, "detect", lambda paths, scale=1.0, thr=0.6: [[]])
    with pytest.raises(cut_picture.PictureError) as x:
        cut_picture.face_roi(p, "picture[0] shot 1")
    assert "roi" in str(x.value) and "picture[0] shot 1" in str(x.value)
    monkeypatch.setattr(faces, "detect", lambda paths, scale=1.0, thr=0.6: None)  # no detector
    with pytest.raises(cut_picture.PictureError):
        cut_picture.face_roi(p, "picture[0] shot 1")


# --- through cut.py ------------------------------------------------------------------------------------------------

def photo_project(project, shots, words=(("one", 0.6, 0.9),), voice_dur=6.0):
    """A voice note over photos: one cut.json with a picture block."""
    from test_voice_over import voice_note
    from PIL import Image, ImageDraw
    voice_note(project / "voice.ogg", voice_dur + 1.0)
    for k in range(8):
        im = Image.new("RGB", (2400, 3200), (40 + 20 * k, 60, 80))
        ImageDraw.Draw(im).rectangle((1300, 600, 1900, 1100), fill=(230, 20, 20))
        tagged(project / f"p{k}.jpg", im, 6 if k % 3 == 0 else 1)
    e = project / "edit" / "ph"
    write_json(e / "transcripts" / "voice.json",
               {"words": [{"text": t, "start": a, "end": b, "type": "word"} for t, a, b in words]})
    sources = {"voice": {"file": "voice.ogg"}, **{f"p{k}": {"file": f"p{k}.jpg", "strangers": []} for k in range(8)}}
    write_json(e / "cut.json", {"fps": 30, "sources": sources, "ranges": [{"source": "voice", "start": 0.5,
                                                                         "end": 0.5 + voice_dur}],
                                "picture": [{"from": "start", "to": "end", "shots": shots}], "balance": False})
    return e


@needs_ffmpeg
def test_a_photo_shot_with_an_roi_keeps_where_its_subject_is_on_screen(project):
    roi = [1300 / 2400, 600 / 3200, 1900 / 2400, 1100 / 3200]
    e = photo_project(project, [{"source": "p0", "dur": 2.0, "move": "push", "roi": roi},
                                {"source": "p1", "dur": 2.0, "move": "still"},
                                {"source": "p2", "move": "pan"}])
    run_script("cut.py", "edit/ph", cwd=project)
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    g0, g1 = cap["shots"][0], cap["shots"][1]
    import photo_move as pm
    assert g0["kind"] == "photo" and g0["roi_path"]["n"] == 60
    ax, ay, aw, ah = pm.screen_at(g0["roi_path"], 0.0)
    bx, by, bw, bh = pm.screen_at(g0["roi_path"], 1.0)
    assert bw > aw * 1.2 and 0 <= bx and bx + bw <= W  # it grew on screen and stayed in frame
    assert "roi_path" not in g1  # a shot with no ROI keeps the fields it always had
    edl = json.loads((e / "edl.json").read_text(encoding="utf-8"))
    assert edl["shots"][0]["roi_path"] == g0["roi_path"]


@needs_ffmpeg
def test_an_roi_that_does_not_fit_stops_cut_py_before_encoding(project):
    e = photo_project(project, [{"source": "p1", "move": "push", "roi": [0.0, 0.4, 1.0, 0.6]}])
    r = run_script("cut.py", "edit/ph", cwd=project, check=False)
    assert r.returncode != 0 and "pan" in (r.stdout + r.stderr)
    assert not (e / "final.mp4").exists() and not (e / "clips").exists()


@needs_ffmpeg
def test_cut_py_refuses_a_malformed_roi_before_encoding(project):
    for bad in ([0.5, 0.5, 0.4, 0.6], [0, 0, 1], "faces", [0, 0, 1.2, 1]):
        photo_project(project, [{"source": "p1", "move": "push", "roi": bad}])
        r = run_script("cut.py", "edit/ph", "--dry-run", cwd=project, check=False)
        assert r.returncode != 0 and "roi" in (r.stdout + r.stderr), bad


def slides(*spec):
    """Picture shots from (kind, move, seconds) in timeline order."""
    out, t = [], 0.0
    for i, (kind, move, d) in enumerate(spec):
        out.append({"i": i, "kind": kind, "source": f"s{i}", "src_start": 0.0, "src_end": d, "speed": 1.0,
                    "out_start": round(t, 3), "out_dur": d, "move": move, "look": None})
        t += d
    return out


def test_a_row_of_photos_with_the_same_motion_or_no_hero_is_a_slideshow_warning():
    from pic_track import slideshow_issues
    same = slideshow_issues(slides(("photo", "push", 1.5), ("photo", "push", 3.0), ("photo", "push", 1.5),
                                   ("photo", "still", 1.5)))
    assert len(same) == 1 and "same motion" in same[0] and "0" in same[0] and "2" in same[0]
    standing = slideshow_issues(slides(("photo", "none", 1.5), ("photo", "still", 1.5), ("photo", "none", 3.0)))
    assert len(standing) == 1 and "same motion" in standing[0]  # none and still both stand
    metronome = slideshow_issues(slides(("photo", "push", 1.5), ("photo", "still", 1.5), ("photo", "pull", 1.5),
                                        ("photo", "pan", 1.5), ("photo", "push", 1.6)))
    assert len(metronome) == 1 and "hero" in metronome[0]
    deliberate = slides(("photo", "push", 1.5), ("photo", "still", 1.5), ("photo", "pull", 3.5), ("photo", "pan", 1.5),
                        ("photo", "push", 1.5))
    assert slideshow_issues(deliberate) == []
    broken = slides(("photo", "push", 1.5), ("photo", "push", 1.5), ("video", "none", 2.0), ("photo", "push", 1.5),
                    ("photo", "push", 1.5))
    assert slideshow_issues(broken) == []  # a clip between them breaks the row


@needs_ffmpeg
def test_cut_py_and_validate_warn_about_a_slideshow(project):
    shots = [{"source": f"p{k}", "dur": 1.5, "move": "push"} for k in range(4)] + [{"source": "p4", "move": "push"}]
    e = photo_project(project, shots, voice_dur=7.5)
    r = run_script("cut.py", "edit/ph", "--dry-run", cwd=project)
    assert "slideshow" in (r.stdout + r.stderr)
    run_script("cut.py", "edit/ph", cwd=project)
    write_json(project / "brands" / "acme" / "brand.json",
               {"name": "Acme", "slug": "acme", "schema": 2, "tone": {"preset": "expert", "overrides": {}},
                "colors": {"bg": "#0B3D2E", "accent": "#F2C14E", "text": "#FFFFFF"}})
    write_json(e / "reel.json", {"brand": "acme", "use_scenes": True, "voice": "off_camera"})
    run_script("visual_plan.py", "init", "edit/ph", "--force", cwd=project)
    v = run_script("visual_plan.py", "validate", "edit/ph", cwd=project, check=False)
    assert "warning: slideshow" in v.stdout, v.stdout


# --- a layout scene over a photo frames its subject ----------------------------------------------------------------

def test_a_window_scene_over_a_photo_frames_its_roi_not_a_face(project):
    """Where the subject is at the scene's middle, exactly as the rendered push puts it there: a push moves the window
    in a straight line, so the subject's place on screen is not a straight line between its first and last place."""
    import photo_move as pm
    import vp_scenes
    e = project / "edit" / "s"
    shots = slides(("video", "none", 4.0), ("photo", "push", 6.0), ("video", "none", 6.0))
    path = pm.plan((6000, 8000), (W, H), 180, "push", roi=(0.45, 0.2, 0.55, 0.3))
    shots[1]["roi_path"] = pm.record(path)
    write_json(e / "captions.json", {"duration": 16.0, "segments": [], "shots": shots, "words": []})
    # a measured face elsewhere on the screen: the ROI the editor chose wins over it
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": 6}, "samples": [
        {"t": t / 4, "faces": [[700, 300, 200, 260, 0.95]]} for t in range(64)]})
    box = vp_scenes.scene_face(e, {"start": 5.0, "dur": 2.0})  # its middle, 6.0 s, is frame 60 of the photo's 180
    assert box == [round(v) for v in pm.on_screen(path, 60)]
    first, last = pm.on_screen(path, 0), pm.on_screen(path, 179)
    straight = [a + (b - a) * 60 / 179 for a, b in zip(first, last)]
    assert max(abs(a - b) for a, b in zip(box, straight)) > 5  # the straight line between the ends would miss it
    assert vp_scenes.scene_face(e, {"start": 0.5, "dur": 2.0}) == [700, 300, 200, 260]  # over a clip: the face


def test_the_picture_fingerprint_of_a_cut_without_an_roi_is_unchanged():
    import hashlib
    from pic_track import SHOT_KEYS, picture_id
    shots = slides(("photo", "push", 2.0), ("photo", "still", 3.0))
    cap = {"duration": 5.0, "segments": [{"i": 0, "source": "v", "src_start": 0.0, "src_end": 5.0, "out_start": 0.0,
                                          "out_dur": 5.0, "speed": 1.0}], "shots": shots}
    before = hashlib.sha1(repr((5.0, [tuple(g.get(k) for k in SHOT_KEYS) for g in shots])).encode()).hexdigest()[:12]
    assert picture_id(cap) == before  # plans made before this version stay valid
    import photo_move as pm
    shots[0]["roi_path"] = pm.record(pm.plan((3000, 4000), (W, H), 60, "push", roi=(0.4, 0.2, 0.6, 0.3)))
    with_roi = picture_id(cap)
    assert with_roi != before  # an ROI is a different picture
    shots[0]["roi_path"] = pm.record(pm.plan((3000, 4000), (W, H), 60, "push", roi=(0.4, 0.2, 0.6, 0.35)))
    assert picture_id(cap) not in (before, with_roi)  # and a changed ROI too


# --- HEIC: an iPhone's default photo format -------------------------------------------------------------------------

def iphone_heic(path, side=1080):
    """A HEIC as an iPhone saves a photo taken upright: two tiles side by side (red, blue), stored on its side with
    HEIF's rotation (irot 3). Upright it is side x 2*side, red on top and blue below."""
    from heif import make_heic
    return make_heic(path, ["red", "blue"], side, side, rotation=3)


_HEIC_READS = []


def heic_reads(tmp):
    """Does this ffmpeg join an iPhone HEIC's tiles into the photo (ffmpeg 7.1+)? Ubuntu 24.04's ffmpeg 6.1 cannot
    read it, Ubuntu 26.04's gives one tile. A test that needs the photo read skips on such an ffmpeg (the tool lacks
    the feature, like a missing ffmpeg); test_a_heic_is_the_whole_photo_or_a_clear_stop holds everywhere."""
    if not _HEIC_READS:
        f = iphone_heic(tmp / "probe.HEIC", side=64)
        out = tmp / "probe.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(f), "-frames:v", "1", str(out)], capture_output=True)
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                            str(out)], capture_output=True, text=True) if out.is_file() else None
        _HEIC_READS.append(bool(r) and r.stdout.strip() == "64,128")
    if not _HEIC_READS[0]:
        pytest.skip("this ffmpeg does not join HEIC tiles (needs ffmpeg 7.1 or newer)")


@needs_ffmpeg
def test_a_heic_is_the_whole_photo_or_a_clear_stop(project):
    # Ubuntu 26.04's ffmpeg gave one 320x320 tile of a 640x320 photo, with no error: on any ffmpeg the scripts get the
    # whole photo upright or stop with the way out (export as JPEG), never a tile
    import reels_common
    p = iphone_heic(project / "IMG_0004.HEIC", side=160)
    try:
        jpg = reels_common.photo_file(p)
    except reels_common.UnreadablePhoto as ex:
        assert "IMG_0004.HEIC" in str(ex) and "JPEG" in str(ex)
        return
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(jpg)],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "160,320", r.stdout


@needs_ffmpeg
@needs_pillow
def test_an_iphone_heic_is_indexed_upright_with_its_upright_size(project, tmp_path):
    # "HEIC is not read: export JPEG": an iPhone's photos were skipped by the index, so the agent never saw them
    heic_reads(tmp_path)
    import reels_common
    iphone_heic(project / "photos" / "IMG_0001.HEIC", side=320)
    run_script("footage.py", "index", "--dir", "photos", cwd=project)
    idx = json.loads((project / "footage_index.json").read_text(encoding="utf-8"))
    assert (idx["photos/IMG_0001.HEIC"]["w"], idx["photos/IMG_0001.HEIC"]["h"]) == (320, 640), idx
    from PIL import Image
    sheet = Image.open(project / "_footage_index" / "photos-sheet-00.jpg").convert("RGB")
    # the strip's first thumbnail: 320x640 shrunk into 160 px wide -> 160x320 at the top left
    assert near(sheet.getpixel((80, 60)), (255, 0, 0)) and near(sheet.getpixel((80, 260)), (0, 0, 255))
    info = reels_common.probe(project / "photos" / "IMG_0001.HEIC")
    assert (info["w"], info["h"]) == (320, 640)


@needs_ffmpeg
def test_a_prepared_heic_shot_shows_the_photo_upright(project, tmp_path):
    # ffmpeg reads an iPhone's HEIC as a grid of tiles and refuses a filter on it ("Simple and complex filtering cannot
    # be used together"): the shot must still come out, upright, as a picture shot and as a B-roll photo
    heic_reads(tmp_path)
    import footage
    p = iphone_heic(project / "IMG_0002.HEIC")
    for strict in (True, False):
        out = project / f"h-{strict}.mp4"
        footage.prepare(p, out, 0.5, strict=strict, move="still" if strict else None)
        rows = frame_rgb(out, k=0)
        h, w = len(rows), len(rows[0])
        assert near(rows[h // 4][w // 2], (255, 0, 0)) and near(rows[3 * h // 4][w // 2], (0, 0, 255)), strict


@needs_ffmpeg
@needs_pillow
def test_cut_py_makes_a_photo_reel_from_an_iphone_heic(project, tmp_path):
    heic_reads(tmp_path)
    e = photo_project(project, [{"source": "h", "dur": 2.0, "move": "still"}, {"source": "p1", "move": "still"}])
    iphone_heic(project / "h.HEIC")
    cut = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    cut["sources"]["h"] = {"file": "h.HEIC", "strangers": []}
    write_json(e / "cut.json", cut)
    run_script("cut.py", "edit/ph", cwd=project)
    rows = frame_rgb(e / "final.mp4", t=1.0)
    h, w = len(rows), len(rows[0])
    assert near(rows[h // 4][w // 2], (255, 0, 0)) and near(rows[3 * h // 4][w // 2], (0, 0, 255))


@needs_ffmpeg
def test_a_broken_heic_is_an_error_that_names_the_file_and_the_way_out(project):
    # a photo cut off mid-copy (a messenger download that stopped): a clear stop, not a traceback or a tile of it
    import footage
    p = iphone_heic(project / "IMG_0003.HEIC", side=320)
    p.write_bytes(p.read_bytes()[:len(p.read_bytes()) // 2])  # cut through its tiles
    with pytest.raises(SystemExit) as ex:
        footage.prepare(p, project / "x.mp4", 0.5, strict=True, move="still")
    assert "IMG_0003.HEIC" in str(ex.value) and "JPEG" in str(ex.value)


@needs_ffmpeg
@needs_pillow
def test_a_heic_given_to_a_scene_reaches_the_kit_as_an_upright_jpeg(project, tmp_path):
    heic_reads(tmp_path)
    # the kit renders in a browser, which shows no HEIC: a screenshot or photo taken as a scene's media is its JPEG
    from test_plan import plan_project
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    iphone_heic(project / "shot.HEIC", side=320)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "ui", "--mode", "split",
               "--at", "word:test#1", "--dur", "3.0", "--media", str(project / "shot.HEIC"), "--interaction-json",
               '{"kind": "tap", "target": [160, 320], "at": "word:test#1"}', "--source", "agent", "--what", "the screen", "--why", "shows it",
               cwd=project)
    plan = json.loads((e / "visual_plan.json").read_text(encoding="utf-8"))
    media = [i["media"] for i in plan["inserts"] if i.get("media")]
    assert media and media[0]["file"].endswith(".jpg") and media[0]["kind"] == "image", media
    from PIL import Image
    im = Image.open(e / media[0]["file"]).convert("RGB")
    assert im.size == (320, 640) and near(im.getpixel((160, 100)), (255, 0, 0)), im.size
