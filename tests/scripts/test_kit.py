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


def test_split_scene_sits_on_the_style_field():
    # IMG_0135 (04.10): a list in split mode shrank the speaker onto the dark primary background while its text was
    # colored for the style's light field (looks.v2.field), so past items vanished
    src = (KIT / "ReelKit.tsx").read_text(encoding="utf-8")
    assert "backgroundColor: (g ? p.framed?.field : null) ?? look.field ?? p.brand.colors.primary" in src


def test_t1_kit_fixes_are_in_the_source():
    # T1 (kit 1.6.0, checked on stills, not in pytest: there is no Remotion here); these lines keep them from sliding back
    parts = (KIT / "kit" / "scenes" / "parts.tsx").read_text(encoding="utf-8")
    # the accent of a hook over the video was on the same marker plate as the rest of the lines
    assert "const lightPlates = !!p.plates && accLine >= 0 && !!p.chip;" in parts
    assert "...(vis >= s.length ? plate : {}), ...accStyle" in parts
    reel = (KIT / "ReelKit.tsx").read_text(encoding="utf-8")
    # the end card with a CTA had no brand line, and its CTA plate ran under the buttons column (x 1016)
    assert "const tag = !sting && p.brand.tagline" in reel and "const TEXT_W = 840;" in reel
    assert reel.count("maxWidth: TEXT_W") == 3 and "maxWidth: 960" not in reel.split("const EndCard")[1].split("export const ReelKit")[0]
    layer = (KIT / "kit" / "scenes" / "SceneLayer.tsx").read_text(encoding="utf-8")
    # a slogan in the brand style filled the frame with the accent color instead of the brand field
    assert 'const sloganSurf = p.look.field || p.look.style === "brand" ? S.field : S.mark;' in layer
    subs = (KIT / "kit" / "Subtitles.tsx").read_text(encoding="utf-8")
    # a word still being said when a scene ended lost its subtitles (0.4-0.6 s gaps after two scenes)
    assert "w.start >= a && w.end <= b" in subs


def test_kit_comments_point_to_existing_references():
    # T2: kit comments sent the reader to references/effects.md (sections 6-9), a file that does not exist
    refs = CORE.parent / "references"
    missing = []
    for f in KIT.rglob("*.ts*"):
        for name in re.findall(r"\b([a-z][a-z0-9-]*)\.md\b", f.read_text(encoding="utf-8")):
            if not (refs / f"{name}.md").exists() and name not in ("SKILL", "README", "CHANGELOG"):
                missing.append(f"{f.relative_to(KIT).as_posix()}: {name}.md")
    assert not missing, missing


def test_kit_presenter_never_dissolves_and_the_flash_is_the_documented_one():
    # T2: Presenter faded the whole layer in (~5 frames) and out (8 frames) over the video, a muddy double exposure
    # (scenes.md: two busy layouts are never crossfaded); the kit's flash was a 3-frame solid white, while
    # techniques.md describes a warm 6-10 frame screen-blended spot peaking at 0.55
    pres = (KIT / "kit" / "Presenter.tsx").read_text(encoding="utf-8")
    code = "\n".join(line.split("//")[0] for line in pres.splitlines())  # the code, not the comments
    assert "opacity" not in code  # the layer cuts, only the figure (or the window) moves
    flash = (KIT / "kit" / "LightFlash.tsx").read_text(encoding="utf-8")
    frames = int(re.search(r"FLASH_FRAMES = (\d+)", flash).group(1))
    peak = float(re.search(r"FLASH_PEAK = ([\d.]+)", flash).group(1))
    assert 6 <= frames <= 10 and peak == 0.55 and 'mixBlendMode: "screen"' in flash
    tech = (CORE.parent / "references" / "techniques.md").read_text(encoding="utf-8")
    assert "6–10-frame" in tech and "0 → 0.55 → 0" in tech
    for f in ("Inserts.tsx", "scenes/SceneLayer.tsx"):
        src = (KIT / "kit" / f).read_text(encoding="utf-8")
        assert "FlashAt" in src and "#FFFFFF" not in src and "0.85 * " not in src, f


def test_t3_kit_fixes_are_in_the_source():
    # T3 (kit 1.6.0, checked on stills in edit/test-t3/verify/fix-*; there is no Remotion here)
    subs = (KIT / "kit" / "Subtitles.tsx").read_text(encoding="utf-8")
    code = "\n".join(line.split("//")[0] for line in subs.splitlines())  # the code, not the comments
    # the darkening faded in over 0.25 s after a hidden window while the text came at once (3.6:1 on the first frames)
    # (T4: shadeAt takes the end of the speech plus the end card's fade-in, `end`)
    assert "const k = shadeAt(t, end, windows);" in code and "near / RAMP" not in code
    # the caret was a "|" character that read as the letter l
    assert "<Caret on={caret}" in code and ">|<" not in code
    # chunks were cut greedily at 52 characters, not by phrases and pauses
    assert "PAUSE = 0.25" in code and "noBreak(ws[k - 1].text, ws[k].text)" in code and "SHORT" not in code
    # a translated phrase mostly under a scene showed its random tail after it
    assert "covered.has(w.phrase)" in code
    phrase = (KIT / "kit" / "Phrase.tsx").read_text(encoding="utf-8")
    assert "export const noBreak" in phrase and "noBreak(w[k - 1], w[k])" in phrase  # one rule for cards and subtitles
    assert "text.split(\" \")" in phrase  # the glue() trap is documented next to it
    brand = (KIT / "kit" / "brand.ts").read_text(encoding="utf-8")
    # fonts.serif ({{FONT_SERIF}}) was documented but never read
    assert "serif?: BrandFont" in brand and 's === "editorial" ? b.fonts.serif ?? b.fonts.heading' in brand


def test_t4_kit_fixes_are_in_the_source():
    # T4 (kit 1.6.0, checked on stills in edit/test-t4/verify/fix-*; there is no Remotion here)
    import math
    import re
    import reels_common
    subs = (KIT / "kit" / "Subtitles.tsx").read_text(encoding="utf-8")
    code = "\n".join(line.split("//")[0] for line in subs.splitlines())
    # one color for every word: no speaker on a caption word, so two speakers needed two KitSubtitles in the composition
    assert "speaker?: string" in code and "speakers?: string[]" in code
    assert '(w.speaker ?? "") !== (prev.speaker ?? "")' in code  # a change of speaker ends a chunk
    assert code.count("voiceColor(brand, who(w))") == 2 and "backgroundColor: bg, color: ink" in code  # every mode
    assert "color: c.text_on_primary, opacity" not in code
    brand = (KIT / "kit" / "brand.ts").read_text(encoding="utf-8")
    assert "speakers?: string[]" in brand
    # a 56-character phrase wrapped into three lines (bottom 1455 under a band recorded as 1250-1430)
    assert "const MAX_LINES = 2" in code and "toLines(ws, g, font, ready, maxW).length <= MAX_LINES" in code
    # the band export records is the kit's own two-line block in each mode
    geo = {m: dict((k, float(v)) for k, v in re.findall(r"(\w+): ([\d.]+)", body))
           for m, body in re.findall(r"(plate|accent|typewriter): \{([^}]*)\}", code)}
    two = {m: (2 * (g["size"] * g["lh"] + g["padT"] + g["padB"]) + g["gap"] if m == "plate"
               else 2 * g["size"] * g["lh"] + g["padT"] + g["padB"]) for m, g in geo.items()}
    assert reels_common.SUB_BLOCK_H == {m: math.ceil(h) for m, h in two.items()}, two
    # the subtitles and their darkening vanished on the last frame of speech while the sting faded in over 8 frames
    assert "const end = captions.duration + Math.max(0, tail);" in code and "shadeAt(t, end, windows)" in code
    reel = (KIT / "ReelKit.tsx").read_text(encoding="utf-8")
    rcode = "\n".join(line.split("//")[0] for line in reel.splitlines())
    assert rcode.count("tail={tail}") == 2 and "interpolate(k, [0, STING_IN], [0, 1], clamp)" in rcode
    # the whip blur sat on the scaled layer: 6 px times the zoom
    assert "Math.min(WHIP_BLUR, cam.blur) / cam.z" in rcode and "blur(${cam.blur}px)" not in rcode


def test_t6_kit_fixes_are_in_the_source():
    # T6, a "scenes only" promo (kit 1.6.0, checked on stills and a render in edit/promo-hr24-test/verify/fix-*)
    code = lambda f: "\n".join(line.split("//")[0] for line in (KIT / f).read_text(encoding="utf-8").splitlines())
    reel = code("ReelKit.tsx")
    # the cover without video sat on the primary color, not the style's field the video's scenes use
    assert "backgroundColor: g ? framedField(p) : look.field ?? p.brand.colors.primary }}>" in reel.split("export const ReelCover")[1]
    assert "onField={!p.video}" in reel
    cover = code("kit/scenes/Cover.tsx")
    # the accent was not passed: both lines went on the marker plate
    assert "accent={text.accent}" in cover and "plates={!onField}" in cover
    stat = code("kit/scenes/Stat.tsx")
    # the focus brackets on a field took the marker color (yellow on cream, 1.05:1); the accent has >= 3:1 or is the text
    assert "surf.hiBg" not in stat and "color={surf.accent}" in stat
    cta = code("kit/scenes/CtaAction.tsx")
    # the tap ring on the field was the marker color (yellow on a yellow button) and the dot covered a letter
    assert 'tapDot("calc(100% - 0.5em)", "50%", surf.hiText' in cta and "solid ${surf.hiBg}" not in cta
    assert 'tapDot("62%", "58%")' not in cta
    parts = code("kit/scenes/parts.tsx")
    # the counting number sat at the left of a slot sized for the final value: "6   days"
    assert '<span style={{ position: "absolute", right: 0, top: 0 }}>{now}</span>' in parts
    tones = code("kit/scenes/tones.ts")
    # "scenes only": smooth transitions are cuts, no lead/tail of bare field at the joins; the flash has no layout frames
    assert "words: Word[], scenesOnly = false): Timeline" in tones and "if (scenesOnly) {" in tones
    assert 'if (t === "flash") return 0;' in tones
    layer = code("kit/scenes/SceneLayer.tsx")
    assert layer.count("fps, words, scenesOnly)") == 1 and "fps, p.words, p.scenesOnly)" in layer
    assert 'word: ["overlay", "split", "panel", "full"]' in layer


def test_t7_framed_is_drawn_by_the_kit():
    # T7: the kit had no "framed" layout (a horizontal video lay as a band across the middle, the camera clamped to the
    # full frame), so the run wrote its own composition and copied the kit's sting. Checked on stills of plain ReelKit
    # in edit/test-t7/verify/fix-1-* (pixel-identical to the run's composition); there is no Remotion here
    import reels_common as rc
    code = lambda f: "\n".join(line.split("//")[0] for line in (KIT / f).read_text(encoding="utf-8").splitlines())
    reel = code("ReelKit.tsx")
    assert "framed?: Framed | null" in reel and "if (p.framed) return <FramedFootage p={p} z={z} />;" in reel
    for name in ("FramedFootage", "FramedLabel", "EndCard", "Corner", "fitCamera", "framedGeometry", "STING_IN"):
        assert f"export const {name}" in reel, name
    # the same geometry as reels_common (faces.py, visual_plan.py): window, text pad, label row
    win = re.search(r"FRAMED_WINDOW = \[([\d, ]+)\]", reel).group(1)
    assert [int(v) for v in win.split(",")] == list(rc.FRAMED_WINDOW)
    assert f"const FRAMED_PAD = {rc.FRAMED_PAD};" in reel and f"const FRAMED_LABEL_UP = {rc.FRAMED_LABEL_UP};" in reel
    # the camera clamped to the window, as reels_common.cam_fit
    assert "cameraAt(p.camera, t, p.captions.duration, KIT_FPS, view)" in reel and "v.x + hx), v.x + v.w - hx)" in reel
    # Tailwind's preflight shrank a video wider than its parent (pitfalls.md): every footage video sets maxWidth none
    assert reel.count('maxWidth: "none", maxHeight: "none"') >= 2
    # the caps label: the body font, 600, 28 px, +0.2 em
    assert 'letterSpacing: "0.2em", textTransform: "uppercase"' in reel and "size: 28, font, weight: 600" in reel
    assert "<FramedLabel p={p} font={fonts.body} />" in reel
    # scenes, B-roll and subtitles inside the window
    assert reel.count("framed={g ? sceneBox(g) : null}") == 2 and reel.count("{...subArea}") == 2
    layer = code("kit/scenes/SceneLayer.tsx")
    assert "sceneStage(s, mode, fb?.area)" in layer and "clampStage(s, s.box, area ?? SAFE_STAGE" in layer
    assert "(scenesOnly || framed) && LAYOUT.includes(s.mode)" in layer
    subs = code("kit/Subtitles.tsx")
    assert "const bottom = area ? Math.min(SUB_BOTTOM, area.y + area.h) : SUB_BOTTOM;" in subs and "left: -clip.x" in subs
    ins = code("kit/Inserts.tsx")
    assert "framed ? areaBox(ins, framed.area) : windowBox(ins)" in ins


def test_kit_line_break_words_match_the_scripts():
    # review: Phrase.tsx lacked "your", "this", Russian "cherez", "ili"… that reels_common breaks the .srt by, and broke
    # after a word ending in punctuation before a dash: the burned-in subtitles and the .srt broke lines differently
    import reels_common as rc
    src = (KIT / "kit" / "Phrase.tsx").read_text(encoding="utf-8")

    def words(name):
        body = re.search(r"const " + name + r" = new Set\(\[(.*?)\]\)", src, re.S).group(1)
        return {s.encode("ascii").decode("unicode_escape") for s in re.findall(r'"([^"]*)"', body)}
    assert words("SHORT") == rc.SHORT_WORDS
    assert words("AFTER") == rc.AFTER_WORDS
    assert "return false" in src.split("export const noBreak")[1].split("};")[0]  # punctuation allows the break


def test_framed_cover_corner_and_label():
    # review: ReelCover drew a framed video's frame full-screen (frame 0 jumped to another layout); the corner mark was
    # the light one on a light framed field; a long label ran under the corner mark
    reel = (KIT / "ReelKit.tsx").read_text(encoding="utf-8")
    cover = reel.split("export const ReelCover")[1].split("export const reelCoverDefaults")[0]
    assert "framedGeometry(p.framed)" in cover and "<FramedWindow" in cover and "<FramedLabel" in cover and "zoneIn(" in cover
    assert "const src = cornerLogo(p);" in reel and "mark_on_light" in reel.split("const cornerLogo")[1].split("};")[0]
    label = reel.split("export const FramedLabel")[1].split("};")[0]
    assert "1080 - 140 - cs - 16" in label


def test_update_hints_name_the_real_script_paths(project):
    """kit.py check and doctor.py print commands that work from the project folder: the script's real path, quoted."""
    from pathlib import Path
    run_script("kit.py", "new", "reels", cwd=project)
    rem = project / "reels"
    (rem / "src" / "kit" / "version.ts").write_text('export const KIT_VERSION = "1.0.0";\n', encoding="utf-8")
    r = run_script("kit.py", "check", "--remotion", "reels", cwd=project, check=False)
    hint = next(line for line in r.stdout.splitlines() if line.startswith("update:"))
    script = re.search(r'"([^"]+kit\.py)"', hint).group(1)
    assert Path(script).is_file() and Path(script).resolve() == (CORE / "kit.py").resolve()
    assert f'--remotion "{rem.resolve()}"' in hint
    r = run_script("doctor.py", "--json", cwd=project, check=False)
    fix = {c["name"]: c for c in json.loads(r.stdout)["checks"]}["ReelKit in the project"]["fix"]
    assert re.search(r'"([^"]+kit\.py)"', fix) and Path(re.search(r'"([^"]+kit\.py)"', fix).group(1)).is_file()


def test_new_project_fixes_the_video_cache_and_check_names_one_without(project):
    # "No frame found at position N" (a 1094 render on an 8 GB laptop): Remotion sized its video cache from the RAM free
    # at the start, a few MB with other apps open; a fixed 384 MB cache in remotion.config.ts fixed it
    run_script("kit.py", "new", "reels", cwd=project)
    cfg = project / "reels" / "remotion.config.ts"
    assert "setOffthreadVideoCacheSizeInBytes(384 * 1024 * 1024)" in cfg.read_text(encoding="utf-8")
    r = run_script("kit.py", "check", "--remotion", "reels", cwd=project, check=False)
    assert "sets no video cache size" not in r.stdout
    cfg.write_text('import { Config } from "@remotion/cli/config";\n', encoding="utf-8")
    r = run_script("kit.py", "check", "--remotion", "reels", cwd=project, check=False)
    assert "sets no video cache size" in r.stdout and "setOffthreadVideoCacheSizeInBytes" in r.stdout
