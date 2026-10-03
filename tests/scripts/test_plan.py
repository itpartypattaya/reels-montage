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


def test_export_refuses_a_folder_that_is_not_a_remotion_project(project):
    e = project / "edit" / "4821"
    e.mkdir(parents=True)
    write_json(e / "visual_plan.json", {"id": "4821", "brand": "acme", "duration": 10, "inserts": []})
    wrong = project / "not-remotion"
    wrong.mkdir()
    r = run_script("visual_plan.py", "export", "edit/4821", "--remotion", wrong, "--force", cwd=project, check=False)
    assert r.returncode != 0 and "not a Remotion project" in (r.stdout + r.stderr)
    assert not (wrong / "src").exists() and not (wrong / "public").exists()


def test_project_defaults_layer_and_command(project):
    plan_project(project)
    (project / "edit" / "4821" / "reel.json").write_text('{"intensity": "active"}', encoding="utf-8")
    run_script("reelcfg.py", "defaults", "--set", "brand=acme", "use_memes=true", "intensity=minimal", cwd=project)
    doc = json.loads((project / "reel-defaults.json").read_text(encoding="utf-8"))
    assert doc["settings"] == {"brand": "acme", "use_memes": True, "intensity": "minimal"}
    r = run_script("reelcfg.py", "show", "edit/4821", "--json", cwd=project)
    shown = json.loads(r.stdout[r.stdout.index("{"):])
    assert shown["settings"]["brand"] == "acme" and shown["provenance"]["brand"] in ("project", "reel.json")
    assert shown["provenance"]["intensity"] == "reel.json"  # the video's reel.json still wins
    assert shown["provenance"]["use_scenes"] == "defaults"
    run_script("reelcfg.py", "defaults", "--unset", "use_memes", cwd=project)
    doc = json.loads((project / "reel-defaults.json").read_text(encoding="utf-8"))
    assert "use_memes" not in doc["settings"]
    out = run_script("reelcfg.py", "defaults", cwd=project).stdout
    assert "reel-defaults.json" in out and '"brand": "acme"' in out


def test_project_defaults_labels_reach_brand_tones(project):
    write_json(project / "reel-defaults.json", {"brand_tones": {"expert": {"label": "Expert (mine)"}}})
    import importlib, reels_common
    importlib.reload(reels_common)
    doc = reels_common.load_defaults(project)
    assert doc["brand_tones"]["expert"]["label"] == "Expert (mine)"
    assert doc["brand_tones"]["expert"].get("for")  # the rest of the preset is kept (deep merge)


def test_project_defaults_beat_tone_guesses_but_not_its_caps(project):
    plan_project(project)
    (project / "edit" / "4821" / "reel.json").write_text('{"brand": "acme"}', encoding="utf-8")
    run_script("reelcfg.py", "defaults", "--set", "use_memes=true", "intensity=minimal", "meme_size=l", cwd=project)
    r = run_script("reelcfg.py", "show", "edit/4821", "--json", cwd=project)
    shown = json.loads(r.stdout[r.stdout.index("{"):])
    s, prov = shown["settings"], shown["provenance"]
    assert s["use_memes"] is True and prov["use_memes"] == "project"   # the expert preset would say no
    assert s["intensity"] == "minimal" and prov["intensity"] == "project"
    assert s["meme_size"] == "s" and prov["meme_size"].startswith("tone:")  # expert caps memes at s


def test_plan_follows_a_rebuilt_rough_cut(project):
    # A recut (other edges, another length) left the plan with the old length and spans; a scene placed by a word
    # must move with its word, and validate must not judge it against the old length.
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "contrast", "--mode", "overlay",
               "--at", "word:check#1", "--dur", "2.0", "--lines", "resume", "thinking", "--box", "60,250,900,200",
               "--what", "contrast", "--why", "test", cwd=project)
    cap = captions()
    for w in cap["words"]:
        w["start"], w["end"] = round(w["start"] + 0.3, 3), round(w["end"] + 0.3, 3)
    cap["duration"] = 30.3
    write_json(e / "captions.json", cap)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "the rough cut changed" in r.stdout and "moved with their words: c01" in r.stdout
    plan = load_plan(e)
    assert plan["duration"] == 30.3 and abs(plan["inserts"][0]["start"] - 4.1) < 0.001  # "check" 3.8 + 0.3
