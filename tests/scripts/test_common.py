"""reels_common: defaults and overlays, project folder, safe names, brand tone, settings layers, fallback logic."""
import json
import re
from pathlib import Path

import pytest

import reels_common as rc
from conftest import CORE, write_json


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


def test_online_sources_are_off_without_the_add_on(project):
    eff, why = rc.effective({"use_broll": True, "use_online_footage": True, "use_memes": True, "use_online_memes": True,
                             "use_generated_footage": True, "use_project_footage": True})
    assert eff["broll"] and eff["project_footage"] and eff["generated_code"]
    assert not eff["online_footage"] and not eff["online_memes"] and not eff["generate_now"]
    assert why["online_footage"] == "the online add-on is not installed"
    assert eff["online_footage_providers"] == []


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
