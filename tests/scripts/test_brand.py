"""brand.py: a brand profile in the user's project, its tone and settings; the plugin never writes into its own folder."""
import json

from conftest import CORE, needs_pillow, run_script, write_json


def brand_json(project, slug="acme"):
    return json.loads((project / "brands" / slug / "brand.json").read_text(encoding="utf-8"))


@needs_pillow
def test_new_brand_lives_in_the_project(project):
    run_script("brand.py", "new", "--name", "Acme", "--colors", "#0B3D2E,#F2C14E", "--slug", "acme", cwd=project)
    b = brand_json(project)
    assert b["name"] == "Acme" and b["schema"] == 2
    assert b["tone"]["preset"] == "expert" and b["tone"].get("unconfirmed")  # no --tone: ask the owner
    assert (project / "brands" / "acme" / "rules.md").is_file()
    assert not (CORE.parent / "brands").exists()


@needs_pillow
def test_new_brand_refuses_the_plugin_folder(project):
    r = run_script("brand.py", "new", "--name", "Acme", "--colors", "#0B3D2E", "--where", "skill", cwd=project, check=False)
    assert r.returncode != 0
    assert not (CORE.parent / "brands").exists()


@needs_pillow
def test_tone_and_set(project):
    run_script("brand.py", "new", "--name", "Acme", "--colors", "#0B3D2E,#F2C14E", "--slug", "acme", "--tone", "warm",
               cwd=project)
    run_script("brand.py", "tone", "acme", "bold", "--set", "memes.max=1", cwd=project)
    b = brand_json(project)
    assert b["tone"]["preset"] == "bold" and b["tone"]["overrides"] == {"memes": {"max": 1}}
    run_script("brand.py", "set", "acme", "inserts.use_broll=false", cwd=project)
    assert brand_json(project)["inserts"]["use_broll"] is False
    r = run_script("brand.py", "show", "acme", cwd=project)
    assert "bold" in r.stdout


def test_old_profile_is_migrated_on_its_first_edit_with_a_backup(project):
    write_json(project / "brands" / "old" / "brand.json", {"name": "Old", "slug": "old", "colors": {"accent": "#112233"}})
    run_script("brand.py", "show", "old", cwd=project)
    assert "schema" not in brand_json(project, "old")  # reading never rewrites the profile
    run_script("brand.py", "set", "old", "inserts.use_broll=false", cwd=project)
    b = brand_json(project, "old")
    assert b["schema"] == 2 and b["tone"]["preset"] == "expert" and b["inserts"]["use_broll"] is False
    assert (project / "brands" / "old" / "brand.json.bak").is_file()


def test_brand_show_lists_the_brands_own_documents(project):
    b = project / "brands" / "acme"
    write_json(b / "brand.json", {"name": "Acme", "slug": "acme", "schema": 2, "tone": {"preset": "expert"},
                                  "colors": {"primary": "#0B3D2E", "accent": "#F2C14E", "light": "#FFFFFF"},
                                  "rules": "rules.md", "guide": "guide.md", "cta_library": "cta.md"})
    for name in ("rules.md", "guide.md", "cta.md", "skit-format.md"):
        (b / name).write_text(f"# {name}\n", encoding="utf-8")
    out = run_script("brand.py", "show", "acme", cwd=project).stdout
    assert "video guide:" in out and "guide.md" in out and "CTA library:" in out and "cta.md" in out
    assert "other brand documents: skit-format.md" in out
    (b / "guide.md").unlink()
    assert "guide.md ✗" in run_script("brand.py", "show", "acme", cwd=project).stdout


def test_rule_goes_into_the_marked_revisions_section_in_any_language():
    import brand
    text = "# Rules\n\n## Revisions (in my language)\n<!-- revisions -->\n- 2026-01-01: old\n\n## Documents\n- guide.md\n"
    out = brand.add_rule(text, "- 2026-02-02: new")
    assert out.index("- 2026-02-02: new") < out.index("## Documents")
    assert out.index("- 2026-01-01: old") < out.index("- 2026-02-02: new")
    assert out.count("## Rules from revisions") == 0
    plain = brand.add_rule("# Rules\n\n## Rules from revisions\n- a\n", "- b")
    assert plain.endswith("- a\n- b\n")
    fresh = brand.add_rule("# Rules\n", "- c")
    assert "## Rules from revisions\n- c" in fresh


def test_rule_records_its_reason_and_scope(project):
    # 1.7.0 (references/playbook.md): a brand rule is an owner decision; with its reason and scope a disliked result
    # can be traced back to it
    write_json(project / "brands" / "acme" / "brand.json", {"name": "Acme", "slug": "acme", "schema": 2,
                                                            "colors": {"primary": "#0B3D2E", "accent": "#F2C14E"}})
    run_script("brand.py", "rule", "acme", "Lists over the video, never shrink the speakers",
               "--why", "the client found shrinking out of place", "--scope", "list scenes", cwd=project)
    text = (project / "brands" / "acme" / "rules.md").read_text(encoding="utf-8")
    assert ("Lists over the video, never shrink the speakers. Applies to: list scenes. "
            "Why: the client found shrinking out of place.") in text
    run_script("brand.py", "rule", "acme", "No red", cwd=project)  # the flags stay optional
    assert "No red\n" in (project / "brands" / "acme" / "rules.md").read_text(encoding="utf-8")
