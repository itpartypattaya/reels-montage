"""codescene.py: code-scene briefs, scaffold into the user's Remotion project, ingest of a finished clip. A brief for a
video model stays pending without the online add-on."""
import json

from conftest import CORE, make_video, needs_ffmpeg, run_script, write_json
from test_plan import load_plan, plan_project

BRIEF = {"subject": "a funnel of six cards narrowing to one", "action": "cards slide in and five fade out",
         "camera": "static", "composition": "centered, top two thirds", "lighting": "flat brand colors",
         "mood": "calm, precise", "start": "six cards in a grid", "end": "one card in the center"}


def generated_plan(project):
    plan_project(project, {"use_broll": True, "use_generated_footage": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    for at, what in (("s02", "a funnel of cards"), ("s04", "a crowd of candidates")):
        run_script("visual_plan.py", "add", "edit/4821", "--kind", "broll", "--at", at, "--dur", "1.6", "--what", what,
                   "--why", "illustrates the line", "--source", "generated", cwd=project)
    e = project / "edit" / "4821"
    plan = load_plan(e)
    b1, b2 = plan["inserts"]
    b1["gen"] = {"engine": "code", **BRIEF}
    b2["gen"] = {"engine": "model", **BRIEF, "subject": "a crowd of people in an office"}
    b1["status"] = b2["status"] = "pending"
    write_json(e / "visual_plan.json", plan)
    return e, b1["id"], b2["id"]


def test_manifest_writes_briefs_and_holds_model_inserts(project):
    e, code_id, model_id = generated_plan(project)
    run_script("codescene.py", "manifest", "edit/4821", cwd=project, check=False)
    man = json.loads((e / "generated" / "manifest.json").read_text(encoding="utf-8"))
    text = json.dumps(man)
    assert code_id in text and (e / "generated" / "briefs.md").is_file()
    held = next(i for i in load_plan(e)["inserts"] if i["id"] == model_id)
    assert held["status"] == "pending" and "add-on" in held.get("fallback", "")


def test_scaffold_goes_into_the_users_project_not_the_plugin(project):
    e, code_id, _ = generated_plan(project)
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    (rem / "src" / "Root.tsx").write_text("export const RemotionRoot = () => null;\n", encoding="utf-8")
    write_json(rem / "package.json", {"name": "reels"})
    r = run_script("codescene.py", "scaffold", "edit/4821", code_id, "--remotion", rem, cwd=project, check=False)
    assert r.returncode != 0 and "brand.py export" in r.stdout + r.stderr  # the brand comes first
    run_script("brand.py", "export", "acme", "--remotion", rem, cwd=project)
    run_script("codescene.py", "scaffold", "edit/4821", code_id, "--remotion", rem, cwd=project)
    assert list((rem / "src" / "gen").glob("*.tsx"))
    r = run_script("codescene.py", "scaffold", "edit/4821", code_id, "--remotion", CORE.parent, cwd=project, check=False)
    assert r.returncode != 0  # never into the plugin folder


@needs_ffmpeg
def test_ingest_picks_up_a_finished_clip(project):
    e, code_id, _ = generated_plan(project)
    make_video(e / "generated" / f"{code_id}.mp4", 1080, 1920, 2.0, audio=False)
    run_script("codescene.py", "ingest", "edit/4821", cwd=project, check=False)
    ins = next(i for i in load_plan(e)["inserts"] if i["id"] == code_id)
    assert ins["status"] == "ready" and (e / ins["file"]).is_file()
