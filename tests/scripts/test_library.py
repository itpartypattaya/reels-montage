"""Your own assets: the library catalog with your verdicts, B-roll from the library, memes with rights."""
import json

from conftest import ffmpeg, make_video, needs_ffmpeg, needs_pillow, run_script, write_json

VERDICTS = {"defaults": {"sfx/whoosh": ["ok", "shot change"], "icons/misc": ["caution", "look first"],
                         "clips": ["ok", "own clips"]},
            "files": {"clips/celebrity_pool.mp4": {"verdict": "no", "why": "a celebrity: third-party rights",
                                                   "rights_block": True}}}


def library(project):
    lib = project / "assets"
    (lib / "sfx" / "whoosh").mkdir(parents=True)
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=0.5", "-f", "lavfi", "-i", "sine=f=900:d=0.4",
           "-filter_complex", "[0][1]concat=n=2:v=0:a=1", lib / "sfx" / "whoosh" / "swish.wav")
    from PIL import Image
    (lib / "icons" / "misc").mkdir(parents=True)
    Image.new("RGBA", (200, 200), (0, 0, 0, 0)).save(lib / "icons" / "misc" / "star.png")
    make_video(lib / "clips" / "pool_view.mp4", 1080, 1920, 2.0, audio=False, color="teal")
    make_video(lib / "clips" / "celebrity_pool.mp4", 1080, 1920, 2.0, audio=False, color="navy")
    write_json(project / "it-reelsmaker.json", {"assets_dir": "assets"})
    return lib


@needs_ffmpeg
@needs_pillow
def test_catalog_without_and_with_verdicts(project):
    lib = library(project)
    run_script("library_catalog.py", cwd=project)  # the folder comes from assets_dir
    cat = json.loads((lib / "_catalog" / "catalog.json").read_text(encoding="utf-8"))
    files = {e["path"]: e for e in (cat["files"] if isinstance(cat, dict) else cat)}
    assert set(files) == {"sfx/whoosh/swish.wav", "icons/misc/star.png", "clips/pool_view.mp4", "clips/celebrity_pool.mp4"}
    assert all(e.get("verdict") is None for e in files.values())  # the plugin ships no verdicts
    assert abs(files["sfx/whoosh/swish.wav"]["onset"] - 0.5) < 0.05  # sound start, not file start
    write_json(lib / "_catalog" / "verdicts.json", VERDICTS)
    run_script("library_catalog.py", "--full", cwd=project)
    cat = json.loads((lib / "_catalog" / "catalog.json").read_text(encoding="utf-8"))
    files = {e["path"]: e for e in (cat["files"] if isinstance(cat, dict) else cat)}
    assert files["icons/misc/star.png"]["verdict"] == "caution"
    assert files["clips/celebrity_pool.mp4"]["rights_block"] is True
    assert (lib / "_catalog" / "catalog.md").is_file() and list((lib / "_catalog" / "sheets").glob("*.jpg"))


@needs_ffmpeg
@needs_pillow
def test_library_broll_hides_third_party_rights(project):
    library(project)
    write_json(project / "assets" / "_catalog" / "verdicts.json", VERDICTS)
    run_script("library_catalog.py", cwd=project)
    r = run_script("footage.py", "search", "pool", "--providers", "local", "--json", cwd=project)
    found = json.loads(r.stdout[r.stdout.rindex("\n[") + 1:])
    paths = [c["id"] for c in found]
    assert "clips/pool_view.mp4" in paths and "clips/celebrity_pool.mp4" not in paths


@needs_ffmpeg
@needs_pillow
def test_memes_rights_and_strict_brand(project):
    from PIL import Image
    memes = project / "memes"
    memes.mkdir()
    for name, rights in (("shrug", "own"), ("facepalm", "unknown")):
        Image.new("RGB", (300, 300), (200, 200, 50)).save(memes / f"{name}.png")
        write_json(memes / f"{name}.json", {"description": f"a statue {name}", "emotion": "confusion", "rights": rights})
    run_script("memes.py", "index", cwd=project)
    r = run_script("memes.py", "search", "statue confusion", cwd=project)
    assert "shrug" in r.stdout and "facepalm" in r.stdout
    write_json(project / "brands" / "acme" / "brand.json", {"name": "Acme", "slug": "acme", "schema": 2,
                                                            "tone": {"preset": "bold"}, "memes_policy": "strict"})
    write_json(project / "edit" / "4821" / "reel.json", {"brand": "acme"})
    r = run_script("memes.py", "search", "statue confusion", "--edit", "edit/4821", cwd=project)
    assert "shrug" in r.stdout and "facepalm" not in r.stdout.split("hidden")[0]
