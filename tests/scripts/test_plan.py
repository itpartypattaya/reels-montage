"""visual_plan.py and reelcfg.py on an invented rough cut: spans, hints, scenes, rules, settings layers."""
import json

from conftest import CORE, make_video, needs_ffmpeg, run_script, write_json

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


def test_a_recut_of_the_same_length_is_followed_and_offsets_kept(project):
    # review of #8: only a new length triggered the refresh, and a scene added with --offset lost it
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "quote", "--mode", "split",
               "--at", "word:speed#1", "--offset", "-0.2", "--dur", "2.0", "--lines", "Remember this: speed wins",
               "--source", "speech", "--what", "the key line", "--why", "the main idea", cwd=project)
    sc = next(i for i in load_plan(e)["inserts"] if i["kind"] == "scene")
    assert sc["offset"] == -0.2
    start0 = sc["start"]
    cap = captions()
    for w in cap["words"]:  # the same length, the words of the 5th line 0.5 s later
        if w["seg"] == 4:
            w["start"], w["end"] = round(w["start"] + 0.5, 3), round(w["end"] + 0.5, 3)
    write_json(e / "captions.json", cap)
    run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    sc = next(i for i in load_plan(e)["inserts"] if i["kind"] == "scene")
    assert abs(sc["start"] - (start0 + 0.5)) < 0.001  # moved with its word, the -0.2 offset kept


def faces_json(e, box, dur=30.0):
    """A face measurement: the same face all through the video (faces.py format, already filtered)."""
    from faces import FILTER_V
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": FILTER_V},
                                  "samples": [{"t": k * 0.25, "faces": [box + [0.95]]} for k in range(int(dur / 0.25) + 1)]})


def test_a_list_over_the_video_keeps_the_speaker(project):
    # Real case: a 3-item list in a skit, and shrinking the speakers to a panel was out of place there. In overlay the
    # list takes a free zone off the face, the speaker is not moved, the subtitles step aside while it is on.
    from faces import MARGIN
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    face = [380, 700, 260, 340]  # the head in the middle: the big headroom slot (y 250-925) would touch it
    faces_json(e, face)
    items = [{"text": "First", "at": "word:first#1"}, {"text": "Check", "at": "word:check#1"},
             {"text": "The resume", "at": "word:resume#1"}]
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "list", "--at", "word:first#1",
               "--dur", "3.4", "--items-json", json.dumps(items), "--what", "three steps on plates",
               "--why", "the steps without shrinking the speaker", cwd=project)
    sc = next(i for i in load_plan(e)["inserts"] if i["kind"] == "scene")
    assert sc["mode"] == "overlay" and sc["hide_subtitles"]  # a list's default mode now keeps the face
    x, y, w, h = sc["box"]
    fx, fy, fw, fh = face
    assert x + w <= fx - MARGIN or x >= fx + fw + MARGIN or y + h <= fy - MARGIN or y >= fy + fh + MARGIN
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert load_plan(e)["inserts"][0]["status"] == "ready"
    # the same checks as for any overlay: a box on the face is an error
    plan = load_plan(e)
    plan["inserts"][0]["box"] = [60, 600, 900, 400]
    write_json(e / "visual_plan.json", plan)
    bad = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert bad.returncode == 1 and "covers the face" in bad.stdout


def test_a_list_over_the_video_exports_its_box_and_the_subtitle_gap(project):
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    faces_json(e, [380, 1000, 260, 340])  # a low head: the list goes into the headroom
    items = [{"text": "First", "at": "word:first#1"}, {"text": "Check", "at": "word:check#1"},
             {"text": "The resume", "at": "word:resume#1"}]
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "list", "--mode", "overlay",
               "--at", "word:first#1", "--dur", "3.4", "--items-json", json.dumps(items), "--lines", "How we hire",
               "--what", "three steps on plates", "--why", "the steps without shrinking the speaker", cwd=project)
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    write_json(rem / "package.json", {"name": "reels"})
    run_script("brand.py", "export", "acme", "--remotion", rem, cwd=project)
    (e / "final.mp4").write_bytes(b"a rough cut")  # export only copies it
    run_script("visual_plan.py", "export", "edit/4821", "--remotion", rem, "--props", rem / "props.json", cwd=project)
    props = json.loads((rem / "props.json").read_text(encoding="utf-8"))
    sp = props["scenes"][0]
    assert sp["type"] == "list" and sp["mode"] == "overlay" and sp["hide_subtitles"] is True
    assert sp["box"] == [60, 250, 900, 675] and [round(i["t"], 1) for i in sp["items"]] == [3.0, 3.8, 4.6]
    assert props["hideSubtitles"] == [[sp["start"], round(sp["start"] + sp["dur"], 3)]]
    keep = [k for k in load_plan(e)["keep_clear"] if k.get("scene") == sp["id"]]
    assert keep and keep[0]["box"] == sp["box"] and keep[0]["mode"] == "overlay"  # faces.py audit sees the list


def test_one_subtitle_band_for_faces_validate_and_the_render(project):
    # T1: faces.py had its own band (1290-1400): zones offered a "chest" down to y 1270, where validate rejected a card
    # (band 1250-1430), and faces.py audit without --sub checked a band the render did not have
    import faces
    import meme_layout
    import reels_common
    assert faces.SUB == reels_common.SUB_BAND == tuple(meme_layout.layout()["subtitles_band"])
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    faces_json(e, [380, 600, 260, 340])  # chin at 940
    run_script("faces.py", "zones", "edit/4821", cwd=project)
    chest = json.loads((e / "faces_zones.json").read_text(encoding="utf-8"))["segments"][0]["chest"]
    assert chest == [1000, reels_common.SUB_BAND[0] - 20]
    y0, y1 = chest
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "quote", "--mode", "overlay",
               "--at", "5.0", "--dur", "3.0", "--lines", "A card", "on the chest", "--source", "agent",
               "--box", f"60,{y0},900,{y1 - y0}", "--what", "a card at the chest", "--why", "the zone faces.py offers",
               cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "subtitle band" not in r.stdout, r.stdout
    # the render's band: export puts the top below the chin and records it for the audit
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    write_json(rem / "package.json", {"name": "reels"})
    run_script("brand.py", "export", "acme", "--remotion", rem, cwd=project)
    (e / "final.mp4").write_bytes(b"a rough cut")
    run_script("visual_plan.py", "export", "edit/4821", "--remotion", rem, "--props", rem / "props.json",
               "--force", cwd=project)
    props = json.loads((rem / "props.json").read_text(encoding="utf-8"))
    top = props["subtitlesTop"]
    assert top == reels_common.SUB_BAND[0]  # the chin (+ drift) is far above the band
    # T4: the band is the two-line block the kit can draw in this mode (a three-line phrase ran past 1430)
    h = reels_common.SUB_BLOCK_H[props["subtitles"]]
    assert h <= reels_common.SUB_BAND[1] - reels_common.SUB_BAND[0]
    assert load_plan(e)["subtitles_band"] == [top, top + h]
    assert faces.sub_band(e, rendered=True) == (top, top + h) and faces.sub_band(e) == reels_common.SUB_BAND


def test_plan_editing_commands(project):
    # T1: visual_plan.json was edited by hand five times (no command to change or remove an insert or a zone), a hook
    # without --variant was accepted and failed only at validate, and md did not show the per-video cards
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    hook = ["visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "hook", "--mode", "overlay", "--at", "0.2",
            "--dur", "2.0", "--lines", "Hiring today", "--what", "the hook", "--why", "a weak start"]
    r = run_script(*hook, cwd=project, check=False)
    assert r.returncode != 0 and "slam, type, stack, counter" in r.stderr
    assert not [i for i in load_plan(e)["inserts"]]
    run_script(*hook, "--variant", "slam", cwd=project)
    run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "3.0", "--to", "5.0", "--box", "60,300,700,200",
               "--what", "card 'check the resume'", cwd=project)
    run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "12.0", "--to", "14.0", "--box", "60,300,700,200",
               "--what", "card 'two out of three'", cwd=project)
    run_script("visual_plan.py", "md", "edit/4821", cwd=project)
    md = (e / "visual_plan.md").read_text(encoding="utf-8")
    assert "## Graphics zones (keep_clear)" in md and "2. 0:12.00-0:14.00 card 'two out of three'" in md
    r = run_script("visual_plan.py", "keep-clear", "edit/4821", "--remove", "1", cwd=project)
    assert "card 'check the resume'" in r.stdout
    assert [k["what"] for k in load_plan(e)["keep_clear"]] == ["card 'two out of three'"]
    assert run_script("visual_plan.py", "keep-clear", "edit/4821", "--remove", "5", cwd=project, check=False).returncode
    r = run_script("visual_plan.py", "remove", "edit/4821", "c01", cwd=project)
    assert "removed c01" in r.stdout and not load_plan(e)["inserts"]
    assert run_script("visual_plan.py", "remove", "edit/4821", "c01", cwd=project, check=False).returncode


def test_quote_mismatch_counts_the_words_that_are_there(project):
    # T1: "1 of 5 words matched" for a quote with one word changed: the count stopped at the first difference
    plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "quote", "--mode", "split",
               "--at", "word:test#1", "--dur", "4.2", "--lines", "Test what they think,", "not what they remember",
               "--source", "speech", "--what", "a misquote", "--why", "test", cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "not verbatim" in r.stdout and "(7 of 8 words found there in this order)" in r.stdout


def test_a_long_cta_held_for_its_reading_floor_does_not_outrank_the_hook(project):
    # T1: "the hook is settled for 1.70 s, less than another scene (2.40 s)": the CTA's 8 words need 2.4 s by the
    # reading floor, the hook cannot win that. A scene held longer than its own floor still counts.
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "hook", "--mode", "overlay", "--at", "0.2",
               "--dur", "2.0", "--lines", "Hiring today", "--variant", "slam", "--what", "the hook", "--why", "a weak start",
               cwd=project)
    cta = ["visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "cta", "--mode", "overlay",
           "--at", "word:Subscribe#1", "--lines", "Subscribe and save this video", "for your next hire",
           "--what", "the CTA", "--why", "the ending"]
    run_script(*cta, "--dur", "3.65", cwd=project)  # 9 words need 2.7 s settled: 2.75 s, the floor
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "reading-time floor" not in r.stdout, r.stdout
    assert "the hook should get the most" not in r.stdout
    run_script("visual_plan.py", "remove", "edit/4821", "c02", cwd=project)
    run_script(*cta, "--dur", "4.6", cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "the hook should get the most" in r.stdout


def test_camera_source_by_file_name_stem_or_key(tmp_path):
    # T2: camera.json "source": "IMG_0983.MOV" (the documented form) failed the export: the rough cut's segments carry
    # the cut.json source key ("front"), and the file name never matched it
    import visual_plan as vp
    write_json(tmp_path / "cut.json", {"sources": {"front": {"file": "IMG_0983.MOV"}, "side": "IMG_1042.MOV"}})
    cap = {"duration": 8.0, "segments": [
        {"i": 0, "source": "front", "src_start": 60.0, "src_end": 64.0, "out_start": 0.0, "out_dur": 4.0},
        {"i": 1, "source": "side", "src_start": 60.0, "src_end": 64.0, "out_start": 4.0, "out_dur": 4.0}]}
    for source, t in (("IMG_0983.MOV", 1.0), ("IMG_1042", 5.0), ("front", 1.0), ("C:/footage/IMG_1042.MOV", 5.0)):
        write_json(tmp_path / "camera.json", {"shots": [{"src": 61.0, "source": source, "z": 1.1}]})
        assert vp.camera_shots(tmp_path, {"segments": []}, cap)[0]["t"] == t, source
    assert not vp.same_source("IMG_0983.MOV", "side", vp.source_files(tmp_path))


def test_hide_subs_reach_the_props_and_the_audit(project):
    # T2: a per-video composition hid the subtitles under a presenter; faces.py audit knew only the plan's scenes and
    # flagged "a face in the subtitle band" there. hide-subs keeps such windows in the plan
    import faces
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "hide-subs", "edit/4821", "--from", "23.4", "--to", "26.7", "--why", "presenter", cwd=project)
    plan = load_plan(e)
    assert plan["hide_subtitles"] == [{"start": 23.4, "end": 26.7, "why": "presenter"}]
    assert (23.4, 26.7) in faces.audit_zones(plan)[1]
    run_script("visual_plan.py", "md", "edit/4821", cwd=project)
    md = (e / "visual_plan.md").read_text(encoding="utf-8")
    assert "## Subtitles hidden (hide-subs)" in md and "0:23.40-0:26.70: presenter" in md
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    write_json(rem / "package.json", {"name": "reels"})
    run_script("brand.py", "export", "acme", "--remotion", rem, cwd=project)
    (e / "final.mp4").write_bytes(b"a rough cut")
    run_script("visual_plan.py", "export", "edit/4821", "--remotion", rem, "--props", rem / "props.json", cwd=project)
    assert json.loads((rem / "props.json").read_text(encoding="utf-8"))["hideSubtitles"] == [[23.4, 26.7]]
    run_script("visual_plan.py", "hide-subs", "edit/4821", "--remove", "1", cwd=project)
    assert load_plan(e)["hide_subtitles"] == []
    bad = run_script("visual_plan.py", "hide-subs", "edit/4821", "--from", "29.0", "--to", "31.0", cwd=project, check=False)
    assert bad.returncode != 0 and "outside the video" in bad.stderr


def test_a_presenter_layer_counts_in_the_coverage_and_its_face_is_its_own(project):
    # T2: the presenter over a scene (3.3 s) was left out of the coverage (39 % in the plan, 51 % on screen against a
    # ceiling of 40 %); its keep-clear zone from matte.py place holds the presenter's face, and validate and the audit
    # flagged it; its WebM was copied into public/ by hand
    import faces
    e = plan_project(project, {"use_scenes": True, "intensity": "active"})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    face = [380, 700, 260, 340]
    faces_json(e, face)
    (e / "matte").mkdir()
    (e / "matte" / "host.webm").write_bytes(b"a cut-out")
    r = run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "20.0", "--to", "23.3", "--box", "300,600,700,900",
                   "--what", "presenter", "--matte", "host", "--own-face", ",".join(map(str, face)), cwd=project)
    assert "touches the face" not in r.stdout and "presenter layer" in r.stdout
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert r.returncode == 0 and "touches the face" not in r.stdout, r.stdout + r.stderr
    keep = load_plan(e)["keep_clear"][0]
    assert keep["matte"] == "host" and keep["own_face"] == face
    assert faces.own_face(keep, face) and not faces.own_face(keep, [600, 1300, 200, 250])  # another face is still checked
    # a presenter layer longer than the ceiling (active: 40 % of 30 s = 12 s) is a coverage error
    run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "2.0", "--to", "15.0", "--box", "300,600,700,900",
               "--what", "presenter 2", "--matte", "host", cwd=project)
    bad = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert bad.returncode == 1 and "presenter layers included: 16.3 s" in bad.stdout, bad.stdout
    run_script("visual_plan.py", "keep-clear", "edit/4821", "--remove", "2", cwd=project)
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    write_json(rem / "package.json", {"name": "reels"})
    run_script("visual_plan.py", "export", "edit/4821", "--remotion", rem, cwd=project)
    assert (rem / "public" / "4821" / "host.webm").read_bytes() == b"a cut-out"


def test_md_prints_the_hints_and_an_enumeration_needs_short_parts_in_a_row(project):
    # T2: the hints of init were not in visual_plan.md; the list hint fired on clause commas (three short clauses
    # anywhere in the sentence) and not where the speech listed things
    import visual_plan as vp
    assert vp.enumeration("We need three things: patience, discipline and focus")
    assert vp.enumeration("apples, pears, plums")
    assert not vp.enumeration("And now the other way, recall a big deal, the one you were sure of, that you would "
                              "close, but then lost")
    assert not vp.enumeration("А теперь наоборот, вспомните крупную сделку, в которой вы были уверены, что вы "
                              "закроете, но в итоге потеряли.")
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "md", "edit/4821", cwd=project)
    md = (e / "visual_plan.md").read_text(encoding="utf-8")
    row = next(line for line in md.splitlines() if line.startswith("| s04 "))
    assert "hints: " in row and "a number -> a card works better than B-roll" in row


def test_zones_never_mix_two_camera_angles(project):
    # T2: span k02 of the side angle got a union box [593, 879, 208, 208] with a front-angle sample from just before
    # its cut; zones now split at the segment boundaries where the source changes
    from faces import FILTER_V
    e = project / "edit" / "4821"
    front, side = [590, 830, 190, 260], [700, 920, 90, 120]
    write_json(e / "captions.json", {"duration": 4.0, "words": [], "segments": [
        {"i": 0, "source": "front", "src_start": 10.0, "src_end": 12.0, "out_start": 0.0, "out_dur": 2.1},
        {"i": 1, "source": "side", "src_start": 40.0, "src_end": 42.0, "out_start": 2.1, "out_dur": 1.9}]})
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": FILTER_V}, "samples": [
        {"t": k * 0.25, "faces": [(front if k * 0.25 < 2.1 else side) + [0.95]]} for k in range(17)]})
    run_script("faces.py", "zones", "edit/4821", cwd=project)
    z = {s["id"]: s for s in json.loads((e / "faces_zones.json").read_text(encoding="utf-8"))["segments"]}
    assert z["k00"]["face"] == front and z["k01"]["face"] == side
    # a span across the cut is split, each piece with its own angle
    write_json(e / "visual_plan.json", {"segments": [{"id": "s01", "start": 0.0, "end": 4.0, "text": "one span"}]})
    run_script("faces.py", "zones", "edit/4821", cwd=project)
    z = {s["id"]: s for s in json.loads((e / "faces_zones.json").read_text(encoding="utf-8"))["segments"]}
    assert z["s01a"]["face"] == front and z["s01b"]["face"] == side and z["s01b"]["start"] == 2.1


def test_zones_say_no_face_for_a_long_span_without_one(project):
    # T5: a face in one span of the video made every faceless span (up to 5.7 s) say "shorter than the scan step";
    # a span with samples and no face is "no face in this span", only a span with no sample keeps the old reason
    from faces import FILTER_V
    e = project / "edit" / "4821"
    face = [590, 830, 190, 260]
    write_json(e / "captions.json", {"duration": 8.0, "words": [], "segments": [
        {"i": 0, "source": "main", "src_start": 0.0, "src_end": 6.0, "out_start": 0.0, "out_dur": 6.0},
        {"i": 1, "source": "main", "src_start": 20.0, "src_end": 22.0, "out_start": 6.0, "out_dur": 2.0}]})
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": FILTER_V}, "samples": [
        {"t": k * 0.25, "faces": [face + [0.95]] if 6.5 <= k * 0.25 <= 7.5 else []} for k in range(33)]})
    write_json(e / "visual_plan.json", {"segments": [{"id": "s01", "start": 0.0, "end": 5.7, "text": "a long span"},
                                                     {"id": "s02", "start": 5.7, "end": 6.0, "text": "short"},
                                                     {"id": "s03", "start": 6.0, "end": 8.0, "text": "a face"}]})
    r = run_script("faces.py", "zones", "edit/4821", cwd=project)
    z = {s["id"]: s for s in json.loads((e / "faces_zones.json").read_text(encoding="utf-8"))["segments"]}
    assert z["s01"].get("no_face") and not z["s01"].get("unmeasured") and z["s03"]["face"] == face
    line = next(x for x in r.stdout.splitlines() if x.startswith("s01"))
    assert "no face in this span" in line and "scan step" not in line


def test_reelcfg_knows_every_default_key(project):
    # T3: subtitles_shade (documented, in reel-defaults.json) was saved with "unknown key"
    import reelcfg
    defaults = json.loads((CORE.parent / "assets" / "reel-defaults.json").read_text(encoding="utf-8"))
    assert set(defaults["settings"]) <= reelcfg.KNOWN
    plan_project(project)
    r = run_script("reelcfg.py", "save", "edit/4821", "--set", "subtitles_shade=0.4", cwd=project)
    assert "unknown key" not in r.stderr


def test_init_counts_designed_scenes_as_inserts(project):
    # T3: "inserts are off: the plan has only the main footage" with use_scenes on
    plan_project(project, {"use_scenes": True, "use_broll": False, "use_memes": False})
    r = run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    assert "inserts are off" not in r.stdout and "designed scenes on" in r.stdout
    plan_project(project, {"use_scenes": False, "use_broll": False, "use_memes": False})
    r = run_script("visual_plan.py", "init", "edit/4821", "--force", cwd=project)
    assert "inserts are off" in r.stdout


def test_digits_inside_a_name_are_not_a_number():
    # T3: a brand name with digits gave "a number -> a card", scene:stat and the structure sign "number"
    import structure
    import visual_plan as vp
    assert not vp.NUM_RE.search("I represent ACME24 in Spain, B2B and COVID-19")
    for t in ("we closed 12 roles", "60% of them", "for $100", "the 3rd year", "Two out of three", "24/7"):
        assert vp.NUM_RE.search(t), t
    hints = vp.scene_hints(1, 3, "I represent ACME24 in Spain", 3.0, 6.0, [1], {})
    assert not any(h.startswith("scene:stat") for h in hints)
    ps = [{"text": "I am Anna from ACME24.", "start": 0.0, "end": 2.0, "words": 5},
          {"text": "We closed 40 roles.", "start": 2.5, "end": 4.0, "words": 4}]
    structure.signs(ps, 5.0)
    assert "number" not in ps[0]["signs"] and "number" in ps[1]["signs"]


def test_validate_checks_an_overlay_box_through_camera_json(project):
    # T3: validate checked a hook box against the faces with the static --cam and passed; the render audit flagged it:
    # the camera.json push-in lifted the face into the box's margin. validate now sees the faces as the render does.
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    faces_json(e, [380, 700, 260, 340])  # the head top at y 700
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "quote", "--mode", "overlay",
               "--at", "5.0", "--dur", "3.0", "--lines", "A card", "above the head", "--source", "agent",
               "--box", "60,300,900,300", "--cam", "1,540,960", "--what", "a card above the head", "--why", "the headroom",
               cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "covers the face" not in r.stdout, r.stdout  # 300 + 300 = 600 < 700 - 60
    write_json(e / "camera.json", {"shots": [{"at": 0.0, "z": 1.0}, {"at": 4.5, "z": 1.3, "cx": 540, "cy": 960}]})
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert r.returncode == 1 and "covers the face" in r.stdout and "camera.json" in r.stdout  # (700-960)*1.3+960 = 622
    import visual_plan as vp
    shots = [{"t": 0.0, "z": 1.0, "cx": 540, "cy": 960, "drift": 0.1, "whip": False}]
    assert vp.camera_at(shots, 5.0, 10.0)[0] == 1.05  # the push-in grows over the shot, as in the kit


@needs_ffmpeg
def test_shade_measures_the_darkening_for_the_lightest_frame(project):
    # T3: no tool for the "Typewriter" darkening; the kit default (0.35) and the docs (0.15-0.25) disagreed
    e = plan_project(project)
    write_json(e / "captions.json", {"duration": 2.0, "segments": [], "words": [
        {"text": "light", "start": 0.2, "end": 0.8, "seg": 0}, {"text": "shirt", "start": 0.9, "end": 1.6, "seg": 0}]})
    make_video(e / "final.mp4", w=1080, h=1920, dur=2.0, audio=False, color="0xB4B4B4")
    r = run_script("visual_plan.py", "shade", "edit/4821", cwd=project)
    value = float(r.stdout.split("reel.json subtitles_shade: ")[1].split()[0])
    assert 0.3 <= value <= 0.7, r.stdout  # a light gray needs a real darkening
    assert "--set subtitles_shade=" in r.stdout
    make_video(e / "final.mp4", w=1080, h=1920, dur=2.0, audio=False, color="0x202020")
    r = run_script("visual_plan.py", "shade", "edit/4821", cwd=project)
    assert "reel.json subtitles_shade: 0.00" in r.stdout  # a dark background needs none


@needs_ffmpeg
def test_shade_measures_a_text_zone_with_a_flat_darkening(project):
    # T5: a "bold" style put white text in the headroom; shade measured only the subtitle band, so the darkening for
    # the scenes' zone was measured by hand. --zone / --scene measure any text zone (flat darkening, 3:1 by default)
    from conftest import ffmpeg
    e = plan_project(project)
    write_json(e / "captions.json", {"duration": 2.0, "segments": [], "words": [
        {"text": "light", "start": 0.2, "end": 0.8, "seg": 0}]})
    # a light top half (a white wall) over a dark bottom half
    ffmpeg("-f", "lavfi", "-i", "color=c=0xD0D0D0:s=1080x960:r=30:d=2", "-f", "lavfi", "-i",
           "color=c=0x202020:s=1080x960:r=30:d=2", "-filter_complex", "[0][1]vstack", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", e / "final.mp4")
    write_json(e / "visual_plan.json", {"id": "4821", "duration": 2.0, "segments": [], "inserts": [
        {"id": "c01", "kind": "scene", "type": "stat", "mode": "overlay", "status": "ready", "start": 0.5, "dur": 1.0,
         "box": [60, 250, 900, 500]}]})
    r = run_script("visual_plan.py", "shade", "edit/4821", "--scene", "c01", "--color", "#FFFFFF", cwd=project)
    top = float(r.stdout.split("a flat darkening of ")[1].split()[0])
    assert 0.3 <= top <= 0.75 and "target 3.0:1" in r.stdout and "subtitles_shade" not in r.stdout, r.stdout
    r = run_script("visual_plan.py", "shade", "edit/4821", "--zone", "60,1100,900,400", "--color", "#FFFFFF", cwd=project)
    assert "a flat darkening of 0.00" in r.stdout, r.stdout  # the dark bottom needs none
    r = run_script("visual_plan.py", "shade", "edit/4821", "--scene", "c01", "--target", "4.5", "--color", "#FFFFFF",
                   cwd=project)
    assert float(r.stdout.split("a flat darkening of ")[1].split()[0]) > top  # body-size text needs more


def test_an_enumeration_set_off_by_dashes_and_not_a_correlative(project):
    # T4: "scene:list" landed on "as at work, so in life" (split at "and", a lone "so" counted as an item) while the
    # real list, set off by dashes, got none
    import visual_plan as vp
    assert vp.enumeration("This feeling — to feel people, understand their needs, find their pains — never left.")
    assert vp.enumeration("Вот это чувство — чувствовать людей, понимать их потребности, выявлять боли — оно "
                          "абсолютно никуда не ушло.")
    assert not vp.enumeration("skills that help in any field, as at work, so and in life")
    assert not vp.enumeration("скиллы, которые пригодятся в любой сфере, как в рабочей, так и в жизни.")
    assert vp.enumeration("We need three things: patience, discipline and focus")


def test_keep_clear_without_cam_checks_the_face_through_camera_json(project):
    # T4: keep-clear without --cam checked the box against the uncropped frame; validate already used camera.json
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    faces_json(e, [380, 700, 260, 340])  # the head top at y 700
    box = ["--box", "60,300,900,300", "--what", "a card above the head"]
    r = run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "5", "--to", "8", *box, cwd=project)
    assert "the face is not touched" in r.stdout and "without a camera" in r.stdout, r.stdout
    write_json(e / "camera.json", {"shots": [{"at": 0.0, "z": 1.0}, {"at": 4.5, "z": 1.3, "cx": 540, "cy": 960}]})
    r = run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "5", "--to", "8", *box, cwd=project)
    assert "touches the face" in r.stdout and "camera.json" in r.stdout, r.stdout  # (700-960)*1.3+960 = 622 < 600+60
    r = run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "5", "--to", "8", *box, "--cam", "1,540,960",
                   cwd=project)
    assert "the face is not touched" in r.stdout and "with the camera)" in r.stdout  # an explicit --cam still wins


def test_audit_flags_a_face_cut_at_the_side_of_the_frame(project, monkeypatch, capsys):
    # T4: the audit looked only for a cut-off top of the head; in a two-person skit the risk of a push-in is the other
    # person's face cut at the side. A box at the edge of the render is flagged, and so is a face that faces.json and
    # camera.json put past the edge (the render's detector may not see half a face)
    import argparse
    import faces
    import pytest
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": faces.FILTER_V}, "samples": [
        {"t": k * 0.25, "faces": [[230, 830, 115, 160, 0.95], [690, 835, 115, 155, 0.95]]} for k in range(41)]})
    render = {"step": 0.25, "samples": [{"t": 1.0, "faces": [[200, 800, 120, 160, 0.95], [960, 800, 120, 160, 0.95]]},
                                        {"t": 1.25, "faces": [[200, 800, 120, 160, 0.95], [700, 800, 120, 160, 0.95]]}]}
    monkeypatch.setattr(faces, "scan_video", lambda *a, **k: render)
    args = argparse.Namespace(render="render.mp4", edit="edit/4821", step=0.25, raw=False, sub=None, no_subs=True)
    with pytest.raises(SystemExit):
        faces.cmd_audit(args)
    out = capsys.readouterr().out
    assert "a face cut at the side of the frame (the camera's crop): 1.00 s" in out, out
    assert "by the camera" not in out  # no camera.json: nothing to predict
    # a close-up on the left person: the right face goes past the edge, by faces.json through the camera
    write_json(e / "camera.json", {"shots": [{"at": 0.0, "z": 1.0}, {"at": 5.0, "z": 1.7, "cx": 470, "cy": 990}]})
    render["samples"] = [{"t": 1.0, "faces": [[200, 800, 120, 160, 0.95]]}]
    with pytest.raises(SystemExit):
        faces.cmd_audit(args)
    out = capsys.readouterr().out
    assert "by the camera (faces.json through camera.json): 5.00-10.00 s" in out, out
    assert "(the camera's crop)" not in out
    assert faces.side_cuts(e, load_plan(e))[0] == 5.0


def test_reelcfg_lists_designed_scenes_in_what_turns_on(project):
    # T4: "what will actually turn on" did not list the designed scenes
    plan_project(project, {"use_scenes": True})
    r = run_script("reelcfg.py", "show", "edit/4821", cwd=project)
    row = next(line for line in r.stdout.splitlines() if "designed scenes" in line)
    assert "yes" in row
    plan_project(project, {"use_scenes": False})
    r = run_script("reelcfg.py", "show", "edit/4821", cwd=project)
    assert "use_scenes=false" in next(line for line in r.stdout.splitlines() if "designed scenes" in line)


def test_add_meme_copies_the_rights_from_the_meme_index(project):
    # T5: validate said "the meme's rights are unknown" for an own meme and a CC one until memes.py prepare ran:
    # add --meme-id did not copy the rights from the meme index
    e = plan_project(project, {"use_memes": True, "use_local_memes": True})
    write_json(project / "brands" / "acme" / "brand.json",
               {"name": "Acme", "slug": "acme", "schema": 2, "tone": {"preset": "expert", "overrides": {}},
                "colors": {"bg": "#0B3D2E", "accent": "#F2C14E", "text": "#FFFFFF"}, "memes_policy": "strict"})
    write_json(project / "memes" / "_index.json", {
        "feet-on-desk": {"path": "memes/feet-on-desk.png", "rights": "own", "description": "feet on the desk"},
        "heart-eyes": {"path": "memes/online/openverse-0c57de66.png", "rights": "cc", "attribution": "Twemoji, CC BY"}})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    for mid, at in (("feet-on-desk", "s03"), ("heart-eyes", "s05")):
        run_script("visual_plan.py", "add", "edit/4821", "--kind", "meme", "--at", at, "--dur", "1.0", "--what", mid,
                   "--why", "a reaction", "--meme-id", mid, cwd=project)
    r = run_script("visual_plan.py", "add", "edit/4821", "--kind", "meme", "--at", "s02", "--dur", "1.0", "--what", "x",
                   "--why", "y", "--meme-id", "not-indexed", cwd=project)
    assert "not in the meme index" in r.stderr
    rights = {i["meme_id"]: i["rights"] for i in load_plan(e)["inserts"]}
    assert rights == {"feet-on-desk": "own", "heart-eyes": "cc", "not-indexed": None}
    v = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    bad = [x for x in (v.stdout + v.stderr).splitlines() if "rights are unknown" in x]
    assert len(bad) == 1 and "m03" in bad[0], v.stdout  # only the meme the index does not know


def test_the_last_two_seconds_count_from_the_end_card(project):
    # T5: a scene ending 1.95 s before the end of a 25.0 s cut was flagged "only cta in the last 2 s", while a 2.6 s
    # logo sting followed it and the video was 27.6 s. validate --sting/--card, or what export recorded, moves the end
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "quote", "--mode", "overlay",
               "--at", "26.5", "--dur", "2.0", "--lines", "Save this video", "--source", "agent",
               "--box", "60,250,900,300", "--what", "a closing line", "--why", "the payoff", cwd=project)
    rule = "only cta is allowed"
    assert rule in run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False).stdout
    r = run_script("visual_plan.py", "validate", "edit/4821", "--sting", cwd=project, check=False)
    assert rule not in r.stdout and "the video is 32.60 s" in r.stdout
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    write_json(rem / "package.json", {"name": "reels"})
    run_script("visual_plan.py", "export", "edit/4821", "--remotion", rem, "--sting", cwd=project)
    assert load_plan(e)["end_card"] == {"kind": "sting", "seconds": 2.6}
    assert rule not in run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False).stdout
    run_script("visual_plan.py", "export", "edit/4821", "--remotion", rem, "--force", cwd=project)  # no sting now
    assert "end_card" not in load_plan(e)
    assert rule in run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False).stdout


def test_reelcfg_warns_about_a_style_the_brand_does_not_allow(project):
    # T5: style=bold was saved silently although brand.json -> styles.allowed had only marker, brand and minimal
    plan_project(project)
    b = json.loads((project / "brands" / "acme" / "brand.json").read_text(encoding="utf-8"))
    b["styles"] = {"default": "marker", "allowed": ["marker", "brand", "minimal"]}
    write_json(project / "brands" / "acme" / "brand.json", b)
    r = run_script("reelcfg.py", "save", "edit/4821", "--set", "style=bold", cwd=project)
    assert "not in the brand's allowed styles (marker, brand, minimal" in r.stderr
    assert json.loads((project / "edit" / "4821" / "reel.json").read_text(encoding="utf-8"))["style"] == "bold"
    r = run_script("reelcfg.py", "save", "edit/4821", "--set", "style=minimal", cwd=project)
    assert "allowed styles" not in r.stderr


# --- T6: a "scenes only" promo (no footage, no speech) ---

def promo_project(project, tone="cinematic"):
    plan_project(project)
    run_script("visual_plan.py", "init", "edit/promo1", "--scenes-only", "--duration", "20", "--brand", "acme",
               "--set", f"scene_tone={tone}", "use_scenes=true", cwd=project)
    return project / "edit" / "promo1"


def promo_add(project, *args, check=True):
    return run_script("visual_plan.py", "add", "edit/promo1", "--kind", "scene", *args, cwd=project, check=check)


def test_scenes_only_refuses_a_mode_at_add_and_word_is_full(project):
    # T6: `add --mode split` was accepted in "scenes only" and refused only by validate; `word` had no full mode while
    # every scene of the format is full (validate passed it, the kit warned)
    e = promo_project(project)
    items = json.dumps([{"text": "One", "t": 1.0}, {"text": "Two", "t": 2.0}])
    r = promo_add(project, "--type", "list", "--mode", "split", "--at", "0", "--dur", "3", "--items-json", items,
                  "--what", "a list", "--why", "the three steps", check=False)
    assert r.returncode != 0 and "full only" in r.stderr and not load_plan(e)["inserts"]
    promo_add(project, "--type", "word", "--variant", "grid-pick", "--at", "0", "--dur", "3.0", "--lines",
              "200 resumes, 3 finalists", "--value-json", '{"to": 3}', "--what", "a grid of cards",
              "--why", "the shortlist made visual")
    assert load_plan(e)["inserts"][0]["mode"] == "full"
    out = run_script("visual_plan.py", "validate", "edit/promo1", cwd=project, check=False).stdout
    assert "is not for word" not in out and "full only" not in out, out
    # a video with a speaker: a mode the type does not have is refused when it is added
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    r = run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "slogan", "--mode", "overlay",
                   "--at", "s05", "--dur", "2.5", "--lines", "Speed wins", "--what", "the line", "--why",
                   "the main thought", cwd=project, check=False)
    assert r.returncode != 0 and "mode overlay is not for it" in r.stderr


def test_scene_timing_model_matches_the_kit_for_cta_and_scenes_only():
    import visual_plan as vp
    T = {"in": 16, "out": 10, "transition": "fade"}
    sc = {"start": 0.0, "dur": 3.9, "transition_in": "fade", "transition_out": "fade"}
    # T6: in "scenes only" the fade's lead and tail left 14-15 frames of bare field at every join; a smooth
    # transition there is a cut and the text's own entrance and exit carry the change (tones.ts sceneTimeline)
    tl = vp.scene_timeline(sc, T, "full", 30, [], True)
    assert (tl["lead"], tl["tail"], tl["tin"], tl["tout"]) == (0, 0, "cut", "cut")
    with_video = vp.scene_timeline(sc, T, "full", 30, [])  # a video with no words: the layout change stays
    assert (with_video["lead"], with_video["tail"]) == (8, 6)
    # T6: a cta counted its text on screen at lead + 4 + in, while the tap variant's button comes in at lead + 6 + in
    tap = dict(sc, variant="tap")
    assert vp.text_full_on(tap, "cta", ["Need sales people?", "Describe the job - example.com"], tl, 30, []) == 22
    assert vp.text_full_on(tap, "cta", ["Need sales people?"], tl, 30, []) == 16
    comment = dict(sc, variant="comment")  # the code word is typed after the field comes in: 2 frames a character
    assert vp.text_full_on(comment, "cta", ["Comment the word", "“PLAN”"], tl, 30, []) == 28
    bio = dict(sc, variant="bio")
    assert vp.text_full_on(bio, "cta", ["All the links in the profile", "example.com"], tl, 30, []) == 22
    # T6: the light flash is a hard cut under the flash in the kit (0 layout frames), the plan counted 3
    assert vp.layout_frames("flash", T, "in") == 0 == vp.layout_frames("flash", T, "out")


def test_scenes_only_check_counts_the_label_flags_agent_text_and_empty_joins(project):
    e = promo_project(project)
    # a hook of 2 words fits 0.8 s; with its 3-word caps label it is 5 words, 1.5 s (T6: the label was not counted)
    promo_add(project, "--type", "hook", "--variant", "slam", "--at", "0", "--dur", "1.8", "--lines", "Resumes lie",
              "--label", "ACME HIRING TODAY", "--source", "agent", "--sound", "bell", "--what", "the hook",
              "--why", "the client's problem in one line")
    long = "A structured interview built around the real sales situations of your market and your product"
    items = json.dumps([{"text": long, "t": 3.0}, {"text": "Behavioral analysis", "t": 4.0},
                        {"text": "The digital footprint", "t": 5.0}])
    promo_add(project, "--type", "list", "--at", "2.1", "--dur", "6.0", "--lines", "Three checks", "--items-json", items,
              "--source", "client", "--source-ref", "the brief", "--what", "the three checks", "--why", "what sets it apart")
    r = run_script("visual_plan.py", "validate", "edit/promo1", cwd=project, check=False)
    out = r.stdout
    assert "c01: reading-time floor: 'ACME HIRING TODAY Resumes lie' (5 words)" in out, out
    assert "c01: a text the agent took or worded itself (source agent)" in out
    assert "c02: a text the agent took" not in out
    # 0.3 s between the scenes: 10 frames of bare field at the join (T6 had 14-15 at every join with no gap at all)
    assert "c01 -> c02: 10 frames of empty field at the join" in out, out
    # the summary gives the scenes' coverage, not the B-roll budget (T6: "coverage 0.0/4.84 s")
    assert "scenes cover 7.8 of 20" in out and "text on screen" in out and "coverage 0.0/" not in out, out
    run_script("visual_plan.py", "md", "edit/promo1", cwd=project)
    md = (e / "visual_plan.md").read_text(encoding="utf-8")
    assert long in md and "[ACME HIRING TODAY] 'Resumes lie'" in md  # in full (T6: cut at 70 characters)


def test_validate_checks_a_zone_shot_by_shot_through_camera_json(project):
    # T7: a zone (a card's keep_clear, a scene's entry) keeps one static camera for its whole span; when camera.json
    # changes the shot inside it, the check saw only that one camera. Now it follows camera.json sample by sample
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    faces_json(e, [380, 700, 260, 340])  # the head top at y 700
    run_script("visual_plan.py", "keep-clear", "edit/4821", "--from", "3", "--to", "8", "--box", "60,300,900,300",
               "--what", "a card", "--cam", "1,540,960", cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "touches the face" not in r.stdout, r.stdout
    # the push-in starts in the middle of the zone: (700-960)*1.3+960 = 622, inside the card's 60 px margin
    write_json(e / "camera.json", {"shots": [{"at": 0.0, "z": 1.0}, {"at": 6.0, "z": 1.3, "cx": 540, "cy": 960}]})
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "'a card' [60, 300, 900, 300] touches the face" in r.stdout and "camera.json" in r.stdout, r.stdout


def test_side_cuts_skip_a_b_roll_that_replaces_the_frame(project):
    # review: a ready B-roll replacing the rough cut at 4-6 s gave "face cut at the side" for every sample there; an
    # insert that is not ready falls back to the main footage and still counts
    import faces
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": faces.FILTER_V}, "samples": [
        {"t": k * 0.25, "faces": [[230, 830, 115, 160, 0.95], [690, 835, 115, 155, 0.95]]} for k in range(41)]})
    write_json(e / "camera.json", {"shots": [{"at": 0.0, "z": 1.0}, {"at": 5.0, "z": 1.7, "cx": 470, "cy": 990}]})
    plan = load_plan(e)
    assert faces.side_cuts(e, plan)[0] == 5.0
    plan.setdefault("inserts", []).append({"id": "b01", "kind": "broll", "mode": "replace", "status": "ready",
                                           "start": 4.0, "dur": 3.0})
    cuts = faces.side_cuts(e, plan)
    assert cuts and cuts[0] == 7.0, cuts
    plan["inserts"][-1]["status"] = "planned"
    assert faces.side_cuts(e, plan)[0] == 5.0
