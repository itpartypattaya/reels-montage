"""mascot_atlas.py atlas: a ready character picture (a sheet in a grid or a folder of poses) -> atlas.png + rig.json +
rig-check.png in the brand's folder.

What the person needs, in words:
- the background goes, the character stays whole: white eyes on a white background survive, a green background leaves
  no green fringe, an opaque white RGBA and a JPEG sheet work like a PNG;
- background enclosed by the character (between an arm and the body) is not guessed away: it is numbered on the check
  sheet and removed only when the agent confirms it with --holes;
- a grid that does not divide the sheet evenly is cut without pixels of the neighbor cell; an empty cell and a
  background that is not one flat color (a gradient, a photo) stop with a clear message;
- the head does not jump between poses: every pose is scaled and placed by its head, not by its silhouette;
- a folder of <pose>.png with <pose>-talk.png / <pose>-blink.png gives the pose its talk and blink frames, aligned to it.

The fixtures are drawn in code like a production sheet: a simple outlined character drawn at 4x and scaled down, so
its edges are antialiased into the background.
"""
import json
import re

import pytest

from conftest import needs_pillow, run_script, write_json

pytestmark = needs_pillow

SKIN = (240, 190, 150)
INK = (35, 25, 30)
SHIRT = (60, 90, 200)
GLOVE = (250, 200, 40)
WHITE = (255, 255, 255)
GREEN = (0, 177, 64)
SS = 4  # supersampling: drawn at 4x, scaled down -> antialiased edges as in a real drawing
CELL = (300, 400)


def _limb(d, pts, k, color, outline=True):
    if outline:
        d.line(pts, fill=INK + (255,), width=round(26 * k), joint="curve")
        for x, y in (pts[0], pts[-1]):
            r = 13 * k
            d.ellipse((x - r, y - r, x + r, y + r), fill=INK + (255,))
    d.line(pts, fill=color + (255,), width=round(18 * k), joint="curve")
    for x, y in pts:
        r = 9 * k
        d.ellipse((x - r, y - r, x + r, y + r), fill=color + (255,))


def _disc(d, x, y, r, fill, outline=None, ow=0):
    if outline is not None:
        d.ellipse((x - r - ow, y - r - ow, x + r + ow, y + r + ow), fill=outline + (255,))
    d.ellipse((x - r, y - r, x + r, y + r), fill=fill + (255,))


# Arms in character units (head radius 50), relative to the head center: shoulder -> elbow -> hand.
ARMS = {
    "neutral": [[(-55, 60), (-70, 120), (-75, 170)], [(55, 60), (70, 120), (75, 170)]],
    "point_up": [[(-55, 60), (-70, 120), (-75, 170)], [(55, 60), (95, 0), (95, -105)]],
    "celebrate": [[(-55, 60), (-95, 0), (-115, -85)], [(55, 60), (95, 0), (115, -85)]],
    "shrug": [[(-55, 60), (-105, 95), (-125, 30)], [(55, 60), (105, 95), (125, 30)]],
    # akimbo: the hand back on the hip encloses background between the arm and the body
    "palm": [[(-55, 60), (-70, 120), (-75, 170)], [(55, 62), (118, 112), (57, 165)]],
}


def character(pose="neutral", s=1.0, size=CELL, bg=WHITE + (255,), dx=0, dy=0, shirt=SHIRT, talk=False, blink=False,
              glove=GLOVE, glove_outline=True):
    """One pose on its own canvas (RGBA). s scales the whole character; dx, dy move it (in output px)."""
    from PIL import Image, ImageDraw
    W, H = size
    im = Image.new("RGBA", (W * SS, H * SS), bg)
    d = ImageDraw.Draw(im)
    k = s * SS
    cx, hy = (W / 2 + dx) * SS, (170 + dy) * SS

    def P(p):
        return (cx + p[0] * k, hy + p[1] * k)

    # body
    d.rounded_rectangle((cx - 59 * k, hy + 41 * k, cx + 59 * k, hy + 204 * k), radius=30 * k, fill=INK + (255,))
    d.rounded_rectangle((cx - 55 * k, hy + 45 * k, cx + 55 * k, hy + 200 * k), radius=27 * k, fill=shirt + (255,))
    for arm in ARMS[pose]:
        pts = [P(p) for p in arm]
        _limb(d, pts, k, shirt)
        hx, hy2 = pts[-1]
        _disc(d, hx, hy2, 14 * k, glove, INK if glove_outline else None, 4 * k)
    # head
    _disc(d, cx, hy, 48 * k, SKIN, INK, 4 * k)
    for ex in (-18, 18):
        x, y = cx + ex * k, hy - 5 * k
        if blink:
            d.arc((x - 13 * k, y - 10 * k, x + 13 * k, y + 10 * k), 20, 160, fill=INK + (255,), width=round(4 * k))
        else:
            d.ellipse((x - 16 * k, y - 19 * k, x + 16 * k, y + 19 * k), fill=INK + (255,))
            d.ellipse((x - 13 * k, y - 16 * k, x + 13 * k, y + 16 * k), fill=WHITE + (255,))
            d.ellipse((x - 6 * k, y - 4 * k, x + 6 * k, y + 8 * k), fill=(10, 10, 10, 255))
    mx, my = cx, hy + 25 * k
    if talk:
        d.ellipse((mx - 16 * k, my - 11 * k, mx + 16 * k, my + 11 * k), fill=INK + (255,))
        d.ellipse((mx - 8 * k, my + 2 * k, mx + 8 * k, my + 9 * k), fill=(230, 100, 120, 255))
    else:
        d.arc((mx - 17 * k, my - 12 * k, mx + 17 * k, my + 6 * k), 20, 160, fill=INK + (255,), width=round(4 * k))
    return im.resize((W, H), Image.LANCZOS)


def sheet(cells, rows, cols, size=None, bg=WHITE + (255,)):
    """Cells (RGBA canvases, None = empty) pasted on a grid whose lines fall at round(i * W / cols)."""
    from PIL import Image
    W, H = size or (CELL[0] * cols, CELL[1] * rows)
    im = Image.new("RGBA", (W, H), bg)
    for i, c in enumerate(cells):
        r, q = divmod(i, cols)
        x0, x1 = round(q * W / cols), round((q + 1) * W / cols)
        y0, y1 = round(r * H / rows), round((r + 1) * H / rows)
        if c is not None:
            im.paste(c.crop((0, 0, x1 - x0, y1 - y0)), (x0, y0))
    return im


@pytest.fixture
def brand(project):
    write_json(project / "brands" / "acme" / "brand.json", {"name": "Acme", "slug": "acme", "schema": 2})
    return project


def run_atlas(project, src, *args, check=True):
    return run_script("mascot_atlas.py", "atlas", "acme", src, *args, cwd=project, check=check)


def outputs(project):
    from PIL import Image
    d = project / "brands" / "acme" / "assets" / "mascot"
    rig = json.loads((d / "rig.json").read_text(encoding="utf-8"))
    return rig, Image.open(d / "atlas.png").convert("RGBA")


def cell_img(atlas, box):
    x, y, w, h = box
    return atlas.crop((x, y, x + w, y + h))


def count(im, pred):
    return sum(1 for p in im.getdata() if pred(p))


def white_opaque(p):
    return p[3] >= 250 and min(p[:3]) >= 235


def near(c, ref, tol):
    return max(abs(a - b) for a, b in zip(c[:3], ref)) <= tol


def white_blobs(im, min_area=50):
    """Connected patches of opaque white: (area, center x, center y), largest first."""
    w, h = im.size
    px = im.load()
    seen, out = set(), []
    for j in range(h):
        for i in range(w):
            if (i, j) in seen or not white_opaque(px[i, j]):
                continue
            stack, pts = [(i, j)], []
            seen.add((i, j))
            while stack:
                x, y = stack.pop()
                pts.append((x, y))
                for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= q[0] < w and 0 <= q[1] < h and q not in seen and white_opaque(px[q]):
                        seen.add(q)
                        stack.append(q)
            if len(pts) >= min_area:
                out.append((len(pts), sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
    return sorted(out, reverse=True)


def orange_marks(path):
    from PIL import Image
    return count(Image.open(path).convert("RGBA"), lambda p: near(p, (255, 120, 0), 10))


def head_in_box(rig, atlas, pose, frame="cell"):
    """The head as the pixels show it (skin color), in the shared box: the center of its extent and its width. Not the
    centroid: an open mouth takes skin pixels from the lower face and moves a centroid by ~2 px with no misplacement."""
    p = rig["poses"][pose]
    x, y, w, h = p[frame]
    ox, oy = p["offset"]
    im = cell_img(atlas, (x, y, w, h))
    px = im.load()
    xs, ys = [], []
    for j in range(h):
        for i in range(w):
            c = px[i, j]
            if c[3] >= 200 and near(c, SKIN, 18):
                xs.append(i)
                ys.append(j)
    assert xs, f"no head pixels in {pose}"
    return (ox + (min(xs) + max(xs)) / 2, oy + (min(ys) + max(ys)) / 2, max(xs) - min(xs) + 1)


# --- tests ----------------------------------------------------------------------------------------------------


def test_white_eyes_on_white_background_survive(brand, tmp_path):
    src = tmp_path / "hero.png"
    character().convert("RGB").save(src)
    r = run_atlas(brand, src)
    rig, atlas = outputs(brand)
    im = cell_img(atlas, rig["poses"]["neutral"]["cell"])
    # the eye whites: drawn white inside the head, the only white of the character
    eye_white = count(character(bg=(0, 0, 0, 255)), white_opaque)
    assert eye_white > 600
    assert count(im, white_opaque) >= 0.85 * eye_white
    # the background itself is gone: the cell's corners are transparent, and almost no opaque white is left beyond eyes
    w, h = im.size
    assert all(im.getpixel(p)[3] == 0 for p in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)])
    assert count(im, white_opaque) <= 1.15 * eye_white
    assert "brand.py" in r.stdout and "mascot acme --atlas assets/mascot/rig.json" in r.stdout
    assert (brand / "brands" / "acme" / "assets" / "mascot" / "rig-check.png").is_file()


def test_enclosed_background_is_numbered_and_removed_only_when_confirmed(brand, tmp_path):
    src = tmp_path / "sheet.png"
    sheet([character("neutral"), character("palm")], 1, 2).convert("RGB").save(src)
    r1 = run_atlas(brand, src, "--grid", "1x2", "--poses", "neutral,palm")
    holes = [(int(n), pose, int(x), int(y)) for n, pose, x, y in
             re.findall(r"hole (\d+) \(([\w-]+)\): at (\d+),(\d+)", r1.stdout)]
    # the drawn gap between the arm and the body of "palm": its center on the sheet
    gx, gy = CELL[0] + CELL[0] / 2 + 75, 170 + 112
    gap = [h for h in holes if h[1] == "palm" and abs(h[2] - gx) <= 14 and abs(h[3] - gy) <= 14]
    assert len(gap) == 1, r1.stdout
    rig, atlas = outputs(brand)
    eye = min(a for a, _, _ in white_blobs(cell_img(atlas, rig["poses"]["neutral"]["cell"])))  # one eye white
    blobs = white_blobs(cell_img(atlas, rig["poses"]["palm"]["cell"]))
    assert len(blobs) == 3, blobs  # two eyes and the gap, all kept: nothing is guessed away
    eye_y = min(y for _, _, y in blobs)
    assert any(y > eye_y + 50 and a > 150 for a, _, y in blobs)  # the gap, well below the eyes
    check = brand / "brands" / "acme" / "assets" / "mascot" / "rig-check.png"
    assert orange_marks(check) > 20  # the first run numbered the holes on its sheet

    r2 = run_atlas(brand, src, "--grid", "1x2", "--poses", "neutral,palm", "--holes", str(gap[0][0]))
    assert re.search(rf"hole {gap[0][0]} \(palm\).*removed", r2.stdout)
    rig, atlas = outputs(brand)
    blobs = white_blobs(cell_img(atlas, rig["poses"]["palm"]["cell"]))
    assert len(blobs) == 2, blobs  # the gap is gone ...
    assert all(abs(y - eye_y) <= 6 and a >= 0.85 * eye for a, _, y in blobs), (blobs, eye)  # ... both eyes stay whole
    marks = orange_marks(check)
    assert marks > 20
    # the check after a hand edit draws the sheet again: the hole numbers and warnings must stay on it
    run_script("mascot_atlas.py", "check", "acme", cwd=brand)
    assert orange_marks(check) >= 0.9 * marks

    bad = run_atlas(brand, src, "--grid", "1x2", "--poses", "neutral,palm", "--holes", "99", check=False)
    assert bad.returncode != 0 and "99" in bad.stderr


def test_green_background_leaves_no_green_fringe(brand, tmp_path):
    src = tmp_path / "green.png"
    character(bg=GREEN + (255,)).convert("RGB").save(src)
    run_atlas(brand, src)
    rig, atlas = outputs(brand)
    im = cell_img(atlas, rig["poses"]["neutral"]["cell"])
    green = [p for p in im.getdata() if p[3] >= 24 and p[1] - max(p[0], p[2]) > 24]
    assert not green, green[:10]
    assert count(im, lambda p: p[3] >= 250) > 20000  # the character itself is there


def test_opaque_white_rgba_and_jpeg_sheets_work(brand, tmp_path):
    png = tmp_path / "rgba.png"
    character().save(png)  # RGBA, every pixel opaque, white background
    run_atlas(brand, png)
    rig, atlas = outputs(brand)
    im = cell_img(atlas, rig["poses"]["neutral"]["cell"])
    solid_png = count(im, lambda p: p[3] >= 250)
    eye_white = count(character(bg=(0, 0, 0, 255)), white_opaque)
    assert im.getpixel((0, 0))[3] == 0
    assert count(im, white_opaque) >= 0.85 * eye_white

    jpg = tmp_path / "sheet.jpg"
    character().convert("RGB").save(jpg, quality=85)
    run_atlas(brand, jpg)
    rig, atlas = outputs(brand)
    im = cell_img(atlas, rig["poses"]["neutral"]["cell"])
    assert im.getpixel((0, 0))[3] == 0
    assert abs(count(im, lambda p: p[3] >= 250) - solid_png) <= 0.06 * solid_png
    assert count(im, lambda p: p[3] >= 250 and min(p[:3]) >= 225) >= 0.75 * eye_white


def test_uneven_grid_cuts_without_neighbor_pixels(brand, tmp_path):
    from PIL import ImageDraw
    colors = [(200, 40, 40), (40, 160, 60), (150, 60, 190)]
    W, H = 3 * CELL[0] + 2, CELL[1] + 1  # 902 x 401: the lines fall between pixels
    cells = []
    for i, c in enumerate(colors):
        im = character("neutral", shirt=c, size=(CELL[0] + 1, CELL[1] + 1))
        x1 = round((i + 1) * W / 3) - round(i * W / 3)
        ImageDraw.Draw(im).rectangle((x1 - 14, 330, x1 - 1, 350), fill=c + (255,))  # content up to the grid line
        cells.append(im)
    src = tmp_path / "uneven.png"
    sheet(cells, 1, 3, size=(W, H)).convert("RGB").save(src)
    run_atlas(brand, src, "--grid", "1x3", "--poses", "neutral,shrug,palm")
    rig, atlas = outputs(brand)
    for i, pose in enumerate(["neutral", "shrug", "palm"]):
        im = cell_img(atlas, rig["poses"][pose]["cell"])
        own = count(im, lambda p: p[3] >= 128 and near(p, colors[i], 30))
        assert own > 1000
        for j, c in enumerate(colors):
            if j != i:
                stray = count(im, lambda p, c=c: p[3] >= 128 and near(p, c, 40))
                assert stray == 0, f"{pose} has {stray} px of cell {j + 1}"


def test_empty_cell_is_an_error_with_its_number(brand, tmp_path):
    src = tmp_path / "gap.png"
    sheet([character("neutral"), None, character("shrug")], 1, 3).convert("RGB").save(src)
    r = run_atlas(brand, src, "--grid", "1x3", "--poses", "neutral,palm,shrug", check=False)
    assert r.returncode != 0
    assert "cell 2" in r.stderr and "palm" in r.stderr
    assert not (brand / "brands" / "acme" / "assets" / "mascot" / "rig.json").exists()


def test_gradient_or_photo_background_is_refused(brand, tmp_path):
    import random
    from PIL import Image
    W, H = CELL
    grad = Image.new("RGBA", CELL)
    grad.putdata([(255 - y * 100 // H, 255 - y * 100 // H, 255 - y * 70 // H, 255) for y in range(H) for _ in range(W)])
    fig = character(bg=(0, 0, 0, 0))
    src = tmp_path / "gradient.png"
    Image.alpha_composite(grad, fig).convert("RGB").save(src)
    r = run_atlas(brand, src, check=False)
    assert r.returncode != 0 and "transparent PNG" in r.stderr

    rnd = random.Random(7)  # a "photo": soft color patches all over, like a blurred street behind the character
    blob = [(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), 255) for _ in range((W // 10) * (H // 10))]
    photo = Image.new("RGBA", (W // 10, H // 10))
    photo.putdata(blob)
    photo = photo.resize(CELL, Image.BICUBIC)
    src2 = tmp_path / "photo.jpg"
    Image.alpha_composite(photo, fig).convert("RGB").save(src2, quality=90)
    r = run_atlas(brand, src2, check=False)
    assert r.returncode != 0 and "transparent PNG" in r.stderr


def test_single_transparent_pose_works(brand, tmp_path):
    src = tmp_path / "solo.png"
    fig = character(bg=(0, 0, 0, 0))
    fig.save(src)
    r = run_atlas(brand, src)
    rig, atlas = outputs(brand)
    assert list(rig["poses"]) == ["neutral"]
    p = rig["poses"]["neutral"]
    for k in ("cell", "offset", "eyes", "mouth", "mouthW", "skin", "ink"):
        assert k in p, k
    assert rig["atlas"] == "atlas.png" and rig["symmetric"] is False
    assert len(rig["box"]) == 2 and len(rig["anchor"]) == 2
    assert re.fullmatch(r"#[0-9a-f]{6}", p["skin"]) and re.fullmatch(r"#[0-9a-f]{6}", p["ink"])
    skin = tuple(int(p["skin"][i:i + 2], 16) for i in (1, 3, 5))
    ink = tuple(int(p["ink"][i:i + 2], 16) for i in (1, 3, 5))
    assert near(skin, SKIN, 20) and near(ink, INK, 30)
    # the antialiased edge of a transparent drawing is kept as drawn, not keyed again
    soft_in = count(fig, lambda q: 0 < q[3] < 255)
    soft_out = count(cell_img(atlas, p["cell"]), lambda q: 0 < q[3] < 255)
    assert abs(soft_out - soft_in) <= 0.1 * soft_in
    brand_json = json.loads((brand / "brands" / "acme" / "brand.json").read_text(encoding="utf-8"))
    assert "mascot" not in brand_json  # the script prints the brand.py command, it does not edit the profile
    assert "--atlas assets/mascot/rig.json" in r.stdout

    run_atlas(brand, src, "--symmetric")
    assert outputs(brand)[0]["symmetric"] is True


def test_head_stays_put_across_poses(brand, tmp_path):
    cells = [character("neutral"), character("point_up"), character("celebrate"),
             character("shrug", s=0.85, dx=18, dy=14), character("palm", s=0.92, dx=-15, dy=-8)]
    names = "neutral,point_up,celebrate,shrug,palm"
    src = tmp_path / "poses.png"
    sheet(cells + [None], 2, 3).convert("RGB").save(src)
    run_atlas(brand, src, "--grid", "2x3", "--poses", names + ",-")
    rig, atlas = outputs(brand)
    nx, ny, nw = head_in_box(rig, atlas, "neutral")
    for pose in names.split(",")[1:]:
        x, y, w = head_in_box(rig, atlas, pose)
        assert abs(x - nx) <= 0.02 * nw and abs(y - ny) <= 0.02 * nw, (pose, x - nx, y - ny, nw)
        assert abs(w - nw) <= 0.03 * nw, (pose, w, nw)
    # the shared anchor is the point between the eyes of every pose
    ax, ay = rig["anchor"]
    for pose, p in rig["poses"].items():
        (x1, y1), (x2, y2) = p["eyes"]
        cx, cy = p["cell"][:2]
        assert abs(p["offset"][0] + (x1 + x2) / 2 - cx - ax) <= 1 and abs(p["offset"][1] + (y1 + y2) / 2 - cy - ay) <= 1


def test_folder_with_talk_and_blink_frames(brand, tmp_path):
    d = tmp_path / "poses"
    d.mkdir()
    character(bg=(0, 0, 0, 0)).save(d / "neutral.png")
    character(bg=(0, 0, 0, 0), talk=True, dx=9, dy=-6).save(d / "neutral-talk.png")  # drawn a little off: aligned back
    character(bg=(0, 0, 0, 0), blink=True).save(d / "neutral-blink.png")
    character("point_up", bg=(0, 0, 0, 0)).save(d / "point_up.png")
    run_atlas(brand, d)
    rig, atlas = outputs(brand)
    assert set(rig["poses"]) == {"neutral", "point_up"}
    n = rig["poses"]["neutral"]
    assert n["talk"][2:] == n["cell"][2:] and n["blink"][2:] == n["cell"][2:]
    assert "talk" not in rig["poses"]["point_up"] and "blink" not in rig["poses"]["point_up"]
    x, y, w = head_in_box(rig, atlas, "neutral")
    tx, ty, tw = head_in_box(rig, atlas, "neutral", "talk")
    assert abs(tx - x) <= 0.02 * w and abs(ty - y) <= 0.02 * w
    # the talk frame really is the open mouth: the pinkish tongue is there and not in the plain pose
    tongue = (230, 100, 120)
    assert count(cell_img(atlas, n["talk"]), lambda p: p[3] > 200 and near(p, tongue, 30)) > 30
    assert count(cell_img(atlas, n["cell"]), lambda p: p[3] > 200 and near(p, tongue, 30)) == 0

    character(bg=(0, 0, 0, 0)).save(d / "pointup.png")
    r = run_atlas(brand, d, check=False)
    assert r.returncode != 0 and "pointup" in r.stderr


def test_white_detail_touching_the_background_is_warned(brand, tmp_path):
    src = tmp_path / "gloves.png"
    character("celebrate", glove=WHITE, glove_outline=False).convert("RGB").save(src)
    r = run_atlas(brand, src, "--poses", "celebrate", check=False)
    # celebrate alone has no neutral: the head size comes from neutral, so this is an error first
    assert r.returncode != 0 and "neutral" in r.stderr
    src2 = tmp_path / "gloves-neutral.png"
    character("neutral", glove=WHITE, glove_outline=False).convert("RGB").save(src2)
    r = run_atlas(brand, src2)
    assert "light part" in r.stderr and "neutral" in r.stderr
    clean = tmp_path / "clean.png"
    character("neutral").convert("RGB").save(clean)
    r = run_atlas(brand, clean)
    assert "light part" not in r.stderr


def test_check_places_poses_again_by_edited_eyes(brand, tmp_path):
    """The eyes are a guess the agent corrects in rig.json; check --fix then moves each pose so the corrected point
    between its eyes is the shared anchor again, and draws the sheet again."""
    src = tmp_path / "two.png"
    sheet([character("neutral"), character("point_up")], 1, 2).convert("RGB").save(src)
    run_atlas(brand, src, "--grid", "1x2", "--poses", "neutral,point_up")
    path = brand / "brands" / "acme" / "assets" / "mascot" / "rig.json"
    rig = json.loads(path.read_text(encoding="utf-8"))
    for e in rig["poses"]["neutral"]["eyes"]:
        e[1] -= 9  # the real eye line is higher than the guess
    path.write_text(json.dumps(rig), encoding="utf-8")
    r = run_script("mascot_atlas.py", "check", "acme", cwd=brand, check=False)
    assert r.returncode == 1 and "neutral" in r.stderr and "point_up" not in r.stderr
    run_script("mascot_atlas.py", "check", "acme", "--fix", cwd=brand)
    rig = json.loads(path.read_text(encoding="utf-8"))
    ax, ay = rig["anchor"]
    for pose, p in rig["poses"].items():
        (x1, y1), (x2, y2) = p["eyes"]
        cx, cy = p["cell"][:2]
        assert abs(p["offset"][0] + (x1 + x2) / 2 - cx - ax) <= 1 and abs(p["offset"][1] + (y1 + y2) / 2 - cy - ay) <= 1
    assert run_script("mascot_atlas.py", "check", "acme", cwd=brand).returncode == 0


def test_tightly_cropped_transparent_picture_keeps_every_pixel(brand, tmp_path):
    """A transparent drawing cut close to the character (hands and hair touching the canvas edge) is still a
    transparent drawing: nothing is keyed out of it and no margin trims its edges."""
    fig = character("neutral", bg=(0, 0, 0, 0))
    fig = fig.crop((CELL[0] // 2 - 70, 110, CELL[0] // 2 + 70, 330))  # a bust: cut at the sides and the bottom
    src = tmp_path / "tight.png"
    fig.save(src)
    run_atlas(brand, src, "--poses", "neutral")
    rig, atlas = outputs(brand)
    solid_in = count(fig, lambda p: p[3] >= 128)
    solid_out = count(cell_img(atlas, rig["poses"]["neutral"]["cell"]), lambda p: p[3] >= 128)
    assert abs(solid_out - solid_in) <= 0.01 * solid_in, (solid_out, solid_in)


def test_flat_border_with_a_gradient_inside_is_refused(brand, tmp_path):
    """White at the edges, a gray glow behind the character: the border looks flat, the background is not."""
    from PIL import Image
    W, H = CELL
    cx, cy = W / 2, H / 2
    glow = Image.new("RGBA", CELL)
    glow.putdata([(lambda v: (v, v, v, 255))(round(min(255, 175 + 80 * (((x - cx) / cx) ** 2 + ((y - cy) / cy) ** 2))))
                  for y in range(H) for x in range(W)])
    src = tmp_path / "glow.png"
    Image.alpha_composite(glow, character(bg=(0, 0, 0, 0))).convert("RGB").save(src)
    r = run_atlas(brand, src, check=False)
    assert r.returncode != 0 and "transparent PNG" in r.stderr
