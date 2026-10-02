"""visual_plan.py and reelcfg.py on an invented rough cut: spans, hints, scenes, rules, settings layers."""
import json

from conftest import run_script, write_json

LINES = [  # (words, start of the first word) - an invented talk about hiring, 30 s
    ("So today we talk about hiring", 0.2),
    ("First, we check the resume", 3.0),
    ("She said: test how they think, not what they remember", 6.5),
    ("Two out of three candidates fail this step", 12.0),
    ("Remember this: speed wins", 17.0),
    ("Subscribe and save this video", 25.0),
]


def captions():
    words, t = [], 0.0
    for k, (line, start) in enumerate(LINES):
        t = start
        for w in line.split():
            words.append({"text": w, "start": round(t, 3), "end": round(t + 0.35, 3), "seg": k, "src": round(t, 3)})
            t += 0.4
    segs = [{"i": k, "src_start": s, "src_end": s + 4, "out_start": s, "out_dur": 4.0} for k, (_, s) in enumerate(LINES)]
    return {"duration": 30.0, "segments": segs, "words": words}


def plan_project(project, reel=None):
    e = project / "edit" / "4821"
    write_json(e / "captions.json", captions())
    write_json(project / "brands" / "acme" / "brand.json",
               {"name": "Acme", "slug": "acme", "schema": 2, "tone": {"preset": "expert", "overrides": {}},
                "colors": {"bg": "#0B3D2E", "accent": "#F2C14E", "text": "#FFFFFF"}})
    write_json(e / "reel.json", {"brand": "acme", **(reel or {})})
    return e


def load_plan(e):
    return json.loads((e / "visual_plan.json").read_text(encoding="utf-8"))


def test_init_builds_spans_with_scene_hints(project):
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    plan = load_plan(e)
    assert len(plan["segments"]) == len(LINES)
    hints = {g["id"]: " ".join(g.get("hints", [])) for g in plan["segments"]}
    text = json.dumps(plan["segments"], ensure_ascii=False)
    assert "scene:hook" in text      # a filler start
    assert "scene:list" in text      # "First, ..."
    assert "scene:quote" in text     # "She said"
    assert "scene:stat" in text      # "Two out of three"
    assert "scene:slogan" in text    # "Remember this"
    assert "scene:cta" in text       # the last line asks to subscribe
    assert hints


def test_scene_quote_must_be_verbatim(project):
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "quote", "--mode", "split",
               "--at", "word:test#1", "--dur", "4.2", "--lines", "Test how they think,", "not what they remember",
               "--source", "speech", "--what", "the quote", "--why", "the main idea", cwd=project)
    ok = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "quote", "--mode", "split",
               "--at", "word:Two#1", "--dur", "3.0", "--lines", "Nobody passes this step",
               "--source", "speech", "--what", "a misquote", "--why", "test", cwd=project)
    bad = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert bad.returncode == 1 and "not verbatim" in bad.stdout


def test_online_source_is_refused_without_the_add_on(project):
    plan_project(project, {"use_broll": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    r = run_script("visual_plan.py", "add", "edit/4821", "--kind", "broll", "--at", "s02", "--dur", "1.5",
                   "--what", "hands with a resume", "--why", "illustrates", "--source", "online", cwd=project, check=False)
    assert r.returncode != 0 and "add-on is not installed" in (r.stdout + r.stderr)


def test_md_and_scenes_only_promo(project):
    plan_project(project)
    run_script("visual_plan.py", "init", "edit/promo1", "--scenes-only", "--duration", "20", "--brand", "acme", cwd=project)
    e = project / "edit" / "promo1"
    assert load_plan(e)["segments"] == []
    run_script("visual_plan.py", "md", "edit/promo1", cwd=project)
    assert (e / "visual_plan.md").is_file()


def test_reelcfg_show_and_save(project):
    plan_project(project)
    r = run_script("reelcfg.py", "show", "edit/4821", "--json", cwd=project)
    shown = json.loads(r.stdout[r.stdout.index("{"):])
    assert shown  # settings with their sources
    run_script("reelcfg.py", "save", "edit/4821", "--set", "use_memes=false", "intensity=minimal", cwd=project)
    reel = json.loads((project / "edit" / "4821" / "reel.json").read_text(encoding="utf-8"))
    assert reel["brand"] == "acme" and reel["use_memes"] is False and reel["intensity"] == "minimal"
    r = run_script("reelcfg.py", "save", "edit/4821", "--set", "use_online_footage=true", cwd=project, check=False)
    assert "unknown" in (r.stdout + r.stderr).lower()  # an add-on key without the add-on
