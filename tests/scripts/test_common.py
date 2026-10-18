"""reels_common: defaults and overlays, project folder, safe names, brand tone, settings layers, fallback logic."""
import json
import re
from pathlib import Path

import pytest

import reels_common as rc
from conftest import CORE, run_script, write_json


def test_defaults_have_every_tone_and_no_private_or_online_keys(project):
    doc = rc.load_defaults()
    tones = [k for k in doc["brand_tones"] if not k.startswith("_")]
    assert tones == rc.TONE_PRESETS
    s = doc["settings"]
    assert s["brand"] is None
    assert s["library_dirs"] == []
    assert s["generation_engines"] == ["code"]
    for key in ("use_online_footage", "use_online_memes", "generate_now", "online_footage_providers"):
        assert key not in s, key


def test_overlay_file_wins_over_defaults(project, monkeypatch, tmp_path):
    over = write_json(tmp_path / "overlay.json", {"settings": {"intensity": "active", "brand": "acme"}})
    monkeypatch.setenv("REELS_DEFAULTS_OVERLAY", str(over))
    s = rc.load_defaults()["settings"]
    assert s["intensity"] == "active" and s["brand"] == "acme"
    assert "use_broll" in s  # deep merge keeps the rest


def test_project_root_order(project, monkeypatch, tmp_path):
    sub = project / "edit" / "4821"
    sub.mkdir()
    assert rc.project_root(sub) == project  # nearest folder with edit/ or brands/
    other = tmp_path / "elsewhere"
    other.mkdir()
    write_json(other / rc.SETTINGS_FILE, {"project_root": "../proj"})
    assert rc.project_root(other) == project.resolve()  # it-reelsmaker.json -> project_root
    monkeypatch.setenv("REELS_PROJECT", str(other))
    assert rc.project_root(sub) == other.resolve()  # the env variable wins


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".hidden", "x" * 70, "a b"])
def test_safe_slug_rejects_paths(bad):
    with pytest.raises(SystemExit):
        rc.safe_slug(bad)


def test_safe_slug_accepts_plain_names():
    assert rc.safe_slug("acme-2_b") == "acme-2_b"


def test_parse_sets_types():
    assert rc.parse_sets(["a=true", "b=off", "c=null", "d=3", "e=[1,2]", "f=text"]) == {
        "a": True, "b": False, "c": None, "d": 3, "e": [1, 2], "f": "text"}


def test_migrate_brand_adds_expert_tone_once():
    b = {"name": "Acme"}
    notes = rc.migrate_brand(b)
    assert b["schema"] == 2 and b["tone"]["preset"] == "expert" and notes
    assert rc.migrate_brand(b) == []


def test_tone_rules_calm_motion_disables_overshoot(project):
    rules, note = rc.tone_rules({"tone": {"preset": "premium"}}, slug="acme")
    assert rules["preset"] == "premium" and note is None
    assert rules.get("overshoot") is False and rules.get("shake") is False


def test_unknown_tone_falls_back_with_a_note(project):
    rules, note = rc.tone_rules({"tone": {"preset": "loud"}}, slug="acme")
    assert rules["preset"] == rc.TONE_DEFAULT and "unknown tone" in note


def test_settings_layers(project):
    bdir = project / "brands" / "acme"
    write_json(bdir / "brand.json", {"name": "Acme", "slug": "acme", "schema": 2,
                                     "tone": {"preset": "bold", "overrides": {}}, "inserts": {"use_broll": True}})
    e = project / "edit" / "4821"
    write_json(e / "reel.json", {"brand": "acme", "intensity": "minimal"})
    s, prov, *_ = rc.load_config(e, {"use_memes": False})
    assert s["brand"] == "acme" and s["brand_tone"]["preset"] == "bold"
    assert (s["use_broll"], prov["use_broll"]) == (True, "brand:acme")
    assert (s["intensity"], prov["intensity"]) == ("minimal", "reel.json")
    assert (s["use_memes"], prov["use_memes"]) == (False, "override")


def test_a_brand_tone_never_turns_inserts_on(project):
    # Review 2026-10-17 (Fable P1): B-roll was on in every tone preset and memes in friendly and bold, so a plain edit
    # held only while the agent remembered to save false; now inserts come only from the person's choice
    e = project / "edit" / "4821"
    for preset in ("premium", "warm", "expert", "story", "tech", "friendly", "drive", "bold"):
        write_json(project / "brands" / "acme" / "brand.json", {"name": "Acme", "slug": "acme", "schema": 2,
                                                                "tone": {"preset": preset, "overrides": {}}})
        write_json(e / "reel.json", {"brand": "acme"})
        s, prov, *_ = rc.load_config(e)
        assert (s["use_broll"], s["use_memes"], s["use_scenes"]) == (False, False, False), (preset, prov)
    write_json(e / "reel.json", {"brand": "acme", "use_broll": True, "use_memes": True})
    s, prov, *_ = rc.load_config(e)
    assert (s["use_broll"], prov["use_broll"], s["use_memes"]) == (True, "reel.json", True)


def test_online_sources_are_off_without_the_add_on(project):
    eff, why = rc.effective({"use_broll": True, "use_online_footage": True, "use_memes": True, "use_online_memes": True,
                             "use_code_scenes": True, "use_project_footage": True})
    assert eff["broll"] and eff["project_footage"] and eff["generated_code"]
    assert not eff["online_footage"] and not eff["online_memes"] and not eff["generate_now"]
    assert why["online_footage"] == "the online add-on is not installed"
    assert eff["online_footage_providers"] == []


def test_the_old_name_of_code_scenes_is_still_read_in_every_layer(project):
    # 1.15: use_generated_footage -> use_code_scenes (the old name read as AI generation in a core with none)
    assert rc.renamed({"use_generated_footage": False, "use_broll": True}) == {"use_code_scenes": False, "use_broll": True}
    assert rc.renamed({"use_generated_footage": False, "use_code_scenes": True}) == {"use_code_scenes": True}
    e = project / "edit" / "4821"
    write_json(e / "reel.json", {"use_broll": True, "use_generated_footage": False})
    s, prov, *_ = rc.load_config(e)
    assert s["use_code_scenes"] is False and prov["use_code_scenes"] == "reel.json"
    assert s["use_generated_footage"] is False  # the mirror the add-on <= 1.4.5 reads
    assert not rc.effective(s)[0]["generated_code"]
    write_json(project / rc.PROJECT_DEFAULTS, {"settings": {"use_generated_footage": False}})
    write_json(e / "reel.json", {"use_broll": True})
    s, prov, *_ = rc.load_config(e)
    assert s["use_code_scenes"] is False and prov["use_code_scenes"] == "project"
    s, prov, *_ = rc.load_config(e, overrides={"use_generated_footage": True})
    assert s["use_code_scenes"] is True and prov["use_code_scenes"] == "override"
    # review 2026-10-18 (Codex): a profile's own settings with the old name
    write_json(project / rc.PROJECT_DEFAULTS, {"profiles": {"educational": {"settings": {"use_generated_footage": False}}}})
    write_json(e / "reel.json", {"use_broll": True, "profile": "educational"})
    s, prov, *_ = rc.load_config(e)
    assert s["use_code_scenes"] is False and prov["use_code_scenes"] == "profile:educational"
    assert s["use_generated_footage"] is False and not rc.effective(s)[0]["generated_code"]


def test_reelcfg_writes_the_new_name_of_code_scenes(project):
    e = project / "edit" / "4821"
    write_json(e / "reel.json", {"use_broll": True, "use_generated_footage": False})
    r = run_script("reelcfg.py", "save", "edit/4821", "--set", "use_generated_footage=true", cwd=project)
    assert "is now use_code_scenes" in (r.stdout + r.stderr) and "unknown key" not in (r.stdout + r.stderr)
    reel = json.loads((e / "reel.json").read_text(encoding="utf-8"))
    assert reel["use_code_scenes"] is True and "use_generated_footage" not in reel
    write_json(e / "reel.json", {"use_broll": True, "use_generated_footage": False})  # review 2026-10-18 (Codex)
    run_script("reelcfg.py", "save", "edit/4821", "--set", "intensity=minimal", cwd=project)
    reel = json.loads((e / "reel.json").read_text(encoding="utf-8"))
    assert reel["use_code_scenes"] is False and "use_generated_footage" not in reel  # another key saved: still renamed
    write_json(project / rc.PROJECT_DEFAULTS, {"settings": {"use_generated_footage": False}})
    run_script("reelcfg.py", "defaults", "--unset", "use_code_scenes", cwd=project)
    assert json.loads((project / rc.PROJECT_DEFAULTS).read_text(encoding="utf-8"))["settings"] == {}
    run_script("reelcfg.py", "preset", "save", "series", "--from", "edit/4821", cwd=project)
    preset = json.loads((project / "presets" / "series.json").read_text(encoding="utf-8"))
    assert preset["settings"]["use_code_scenes"] is False and "use_generated_footage" not in preset["settings"]


def test_memes_blocked_by_brand_tone_unless_override(project):
    s = {"use_memes": True, "use_local_memes": True, "brand_tone": {"preset": "premium", "memes": {"allowed": False}}}
    eff, why = rc.effective(s)
    assert not eff["memes"] and "doesn't allow memes" in why["memes"]
    eff, _ = rc.effective({**s, "tone_override": True})
    assert eff["memes"]


def test_word_search_matches_stems():
    assert rc.score("pool view", "IMG_1 pool with a view of the sea") == 1.0
    assert rc.score("balconies", "balcony at night") == 1.0  # common stem
    assert rc.score("pool", "kitchen") == 0.0


def test_missing_add_on_path_warns_and_stays_offline(project, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("REELS_ONLINE_SCRIPTS", str(tmp_path / "gone"))
    assert rc.online() is None
    assert "not found" in capsys.readouterr().err


def test_core_scripts_have_no_network_imports():
    bad = re.compile(r"^\s*(?:import|from)\s+(?:requests|urllib|http\.client|httpx|aiohttp|socket)\b", re.M)
    for f in CORE.glob("*.py"):
        assert not bad.search(f.read_text(encoding="utf-8")), f.name
