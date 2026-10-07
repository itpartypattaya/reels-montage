"""Video profiles (references/profiles.md): the profile layer under the brand tone, the brand's own tone for a
profile, the checklist items visual_plan.py validate checks, and the profiles.md <-> reel-defaults.json ids."""
import json
import re

from conftest import CORE, run_script, write_json
from test_plan import captions, load_plan, plan_project


def settings_of(project, edit="edit/4821"):
    r = run_script("reelcfg.py", "show", edit, "--json", cwd=project)
    return json.loads(r.stdout)


def test_no_profile_keeps_the_old_behaviour(project):
    plan_project(project)
    s = settings_of(project)["settings"]
    assert s["profile_rules"] is None and s["intensity"] == "moderate"
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "profile " not in r.stdout


def test_a_content_format_brings_its_profile_under_the_brand_tone(project):
    # the 0135 case: an entertaining skit at a calm expert brand; the profile asks for active and punchy, the tone
    # holds moderate and allows no punchy, so the first allowed tone of the profile's list is taken
    plan_project(project, {"content_format": "skit"})
    j = settings_of(project)
    s, prov = j["settings"], j["provenance"]
    pr = s["profile_rules"]
    assert pr["id"] == "entertaining" and pr["format"] == "skit" and pr["length"] == [45, 70]
    assert s["intensity"] == "moderate" and prov["intensity"] == "profile:entertaining"
    assert s["scene_tone"] == "deadpan" and s["use_memes"] is True
    assert any("holds moderate" in n for n in pr["notes"])
    out = run_script("reelcfg.py", "show", "edit/4821", cwd=project).stdout
    assert "profile: entertaining" in out and "holds moderate" in out


def test_tone_override_lifts_the_profiles_intensity(project):
    plan_project(project, {"content_format": "skit", "tone_override": True})
    s = settings_of(project)["settings"]
    assert s["intensity"] == "active" and s["scene_tone"] == "punchy"


def test_the_brands_own_tone_for_a_profile_needs_no_override(project):
    plan_project(project, {"profile": "entertaining"})
    run_script("brand.py", "tone", "acme", "drive", "--profile", "entertaining", cwd=project)
    b = json.loads((project / "brands" / "acme" / "brand.json").read_text(encoding="utf-8"))
    assert b["tone"]["preset"] == "expert" and b["tone"]["by_profile"] == {"entertaining": "drive"}
    s = settings_of(project)["settings"]
    assert s["brand_tone"]["preset"] == "drive" and s["brand_tone"]["base_preset"] == "expert"
    assert s["intensity"] == "active" and s["scene_tone"] == "punchy" and not s["profile_rules"]["notes"]
    # another profile keeps the main tone, and changing the main tone keeps the profile's
    write_json(project / "edit" / "4821" / "reel.json", {"brand": "acme", "profile": "educational"})
    assert settings_of(project)["settings"]["brand_tone"]["preset"] == "expert"
    run_script("brand.py", "tone", "acme", "warm", cwd=project)
    b = json.loads((project / "brands" / "acme" / "brand.json").read_text(encoding="utf-8"))
    assert b["tone"]["preset"] == "warm" and b["tone"]["by_profile"] == {"entertaining": "drive"}
    # the main tone's preset removes the profile's own
    run_script("brand.py", "tone", "acme", "warm", "--profile", "entertaining", cwd=project)
    b = json.loads((project / "brands" / "acme" / "brand.json").read_text(encoding="utf-8"))
    assert "by_profile" not in b["tone"]
    r = run_script("brand.py", "tone", "acme", "bold", "--profile", "nope", cwd=project, check=False)
    assert r.returncode != 0 and "educational" in (r.stdout + r.stderr)


def test_save_refuses_an_unknown_profile(project):
    plan_project(project)
    r = run_script("reelcfg.py", "save", "edit/4821", "--set", "profile=viral", cwd=project, check=False)
    assert r.returncode != 0 and "not saved" in (r.stdout + r.stderr)
    r = run_script("reelcfg.py", "save", "edit/4821", "--set", "content_format=reel", cwd=project, check=False)
    assert r.returncode != 0
    run_script("reelcfg.py", "save", "edit/4821", "--set", "profile=ad", "content_format=offer", cwd=project)


def test_an_ad_checks_the_safe_zone_the_brand_and_the_length(project):
    e = plan_project(project, {"profile": "ad", "use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    # a list card low in the frame: inside the organic grid, but under the ad's caption and button
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "contrast", "--mode", "overlay",
               "--at", "word:check#1", "--dur", "2.0", "--lines", "resume", "thinking", "--box", "60,1050,900,200",
               "--what", "contrast", "--why", "test", cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert r.returncode == 1
    assert "AD-1 (profile ad): outside the ad safe zone" in r.stdout
    assert "AD-2 (profile ad): the brand (Acme) is not heard or seen by 3 s" in r.stdout
    assert "ALL-2 ok" in r.stdout  # 30 s fits the ad's 15-34 s
    assert "AD-9 ok" in r.stdout  # "Subscribe and save" is spoken at the end
    assert "confirm by eye" in r.stdout and "AD-3" in r.stdout
    # the corner logo from the first frame counts as the brand seen
    r = run_script("visual_plan.py", "validate", "edit/4821", "--corner", cwd=project, check=False)
    assert "AD-2 ok" in r.stdout


def test_a_promo_hears_the_brand_and_counts_ctas(project):
    e = plan_project(project, {"profile": "promo", "use_scenes": True})
    cap = captions()
    cap["words"][1]["text"] = "Acme"  # "So Acme we talk about hiring": the brand at 0.6 s
    write_json(e / "captions.json", cap)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    for at in ("word:Subscribe#1", "word:hiring#1"):
        run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "cta", "--mode", "overlay",
                   "--at", at, "--dur", "3.0", "--lines", "Write to us", "--what", "the CTA", "--why", "the ending",
                   cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "PROMO-1 ok" in r.stdout
    assert "ALL-3 (profile promo): 2 CTAs" in r.stdout
    # a job opening takes two (apply + recommend)
    write_json(e / "reel.json", {"brand": "acme", "profile": "promo", "content_format": "offer", "use_scenes": True})
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "ALL-3 ok" in r.stdout


def test_a_slow_start_is_flagged(project):
    e = plan_project(project, {"profile": "educational"})
    cap = captions()
    for w in cap["words"]:
        w["start"], w["end"] = round(w["start"] + 1.5, 3), round(w["end"] + 1.5, 3)
    write_json(e / "captions.json", cap)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "ALL-1 (profile educational): the first word starts at 1.7 s" in r.stdout


def test_profiles_md_and_the_defaults_name_the_same_items():
    doc = json.loads((CORE.parent / "assets" / "reel-defaults.json").read_text(encoding="utf-8"))
    md = (CORE.parent / "references" / "profiles.md").read_text(encoding="utf-8")
    ids = set((doc["profiles"]["common_checklist"]).keys())
    for k, v in doc["profiles"].items():
        if not k.startswith("_") and k != "common_checklist":
            ids |= set(v["checklist"])
            assert f"`{k}`" in md, k
    for k in doc["content_formats"]:
        if not k.startswith("_"):
            assert f"`{k}`" in md, k
            assert doc["content_formats"][k]["profile"] in doc["profiles"]
    in_md = set(re.findall(r"\*\*([A-Z]+-\d+)\*\*", md))
    assert in_md == ids, (sorted(in_md - ids), sorted(ids - in_md))
