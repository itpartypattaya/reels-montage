"""mascot.py and the plan's mascot: the mouth follows the recorded narration (the track the viewer hears), the plan's
pose track follows the words, and the mascot never lands on the subtitles, the app's buttons or another graphic.

Requirements (references/mascot.md):
- in a pause the mouth is closed on every frame; noise with no speech never opens it; one loud click does not squash
  the normalization of the speech around it;
- the envelope has exactly as many frames as the narration has on the kit's frame grid (round half up, as the kit
  rounds), for a 16 kHz mono and a 48 kHz stereo file alike;
- a narration re-cut to the same length makes the old mouth.json stale: stage refuses it;
- the mouth may only speak inside the narration; a pose placed on a word that a re-cut removed is an error naming it;
- the mascot on the subtitle band, in the right-hand buttons column, or at a brand tone without a mascot is an error;
  a gesture right at a scene's entrance is a warning;
- poses change at most once per 0.8 s; a brand tone that allows no bounce never overshoots.
"""
import json
import re

import pytest

from conftest import CORE, ffmpeg, needs_ffmpeg, run_script, write_json
from test_plan import LINES, captions, load_plan, plan_project

COMPONENT = """import React from "react";
import type { MascotFrame } from "../kit/mascot/types";
export const box = { width: 400, height: 520, anchor: [200, 170] };
export const poses = ["neutral", "talk", "point_left", "palm", "think", "celebrate"];
export const render = (f: MascotFrame) => <g />;
"""


def tone(path, spans, dur, rate=16000, stereo=False, amp=0.3, extra=""):
    """A narration stand-in: a 300 Hz tone inside the spans [(a, b), ...], silence elsewhere; extra adds to the
    expression (a click, say)."""
    on = "+".join(f"between(t,{a},{b})" for a, b in spans) or "0"
    e = f"{amp}*sin(2*PI*300*t)*({on}){extra}"
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-f", "lavfi", "-i", f"aevalsrc='{e}|{e}':s={rate}:d={dur}" if stereo else f"aevalsrc='{e}':s={rate}:d={dur}",
           path)
    return path


def mouth(project, e, *extra):
    run_script("mascot.py", "mouth", f"edit/{e.name}", *extra, cwd=project)
    return json.loads((e / "mouth.json").read_text(encoding="utf-8"))


def inside(m, a, b):
    """Frames whose whole window lies inside [a, b] seconds."""
    fps = m["fps"]
    return [f for f in range(m["frames"]) if f / fps >= a and (f + 1) / fps <= b]


@needs_ffmpeg
def test_a_pause_keeps_the_mouth_closed_on_every_frame(project):
    e = project / "edit" / "v1"
    tone(e / "voice.wav", [(0.5, 1.5), (2.5, 3.5)], 4.0)
    m = mouth(project, e)
    pause = inside(m, 1.5, 2.5)  # every frame whose window lies in the pause, the ones next to speech too
    assert pause and all(m["open"][f] == 0 for f in pause), [m["open"][f] for f in pause]
    speech = inside(m, 0.6, 1.4)
    assert max(m["open"][f] for f in speech) > 0.5  # and it does open while the tone sounds


@needs_ffmpeg
def test_noise_without_speech_never_opens_the_mouth(project):
    e = project / "edit" / "v2"
    e.mkdir(parents=True)
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=r=16000:a=0.02:d=3:s=7", e / "voice.wav")
    m = mouth(project, e)
    assert m["frames"] == 90 and not any(m["open"])
    # the same noise under speech: the noise-only stretch stays closed
    ffmpeg("-f", "lavfi", "-i", "aevalsrc='0.3*sin(2*PI*300*t)*between(t,0.3,1.2)':s=16000:d=3", "-f", "lavfi",
           "-i", "anoisesrc=r=16000:a=0.02:d=3:s=7", "-filter_complex", "[0][1]amix=inputs=2:normalize=0",
           e / "voice.wav")
    m = mouth(project, e)
    assert not any(m["open"][f] for f in inside(m, 1.3, 3.0))
    assert max(m["open"][f] for f in inside(m, 0.4, 1.1)) > 0.5


@needs_ffmpeg
def test_one_loud_click_does_not_squash_the_speech(project):
    e = project / "edit" / "v3"
    # speech at 0.1, a 20 ms click ten times louder in the pause
    tone(e / "voice.wav", [(0.5, 2.0), (3.0, 4.5)], 5.0, amp=0.1,
         extra="+1.0*sin(2*PI*1000*t)*between(t,2.5,2.52)")
    m = mouth(project, e)
    speech = sorted(m["open"][f] for f in inside(m, 0.6, 1.9) + inside(m, 3.1, 4.4))
    assert speech[len(speech) // 2] >= 0.8, speech[:5]  # the median speech frame opens the mouth nearly fully


@needs_ffmpeg
@pytest.mark.parametrize("rate,stereo", [(16000, False), (48000, True)])
def test_the_frame_count_follows_the_kits_rounding(project, rate, stereo):
    # 2.15 s = 64.5 frames at 30 fps: the kit rounds half up to 65 (Math.round); floor or banker's rounding give 64
    e = project / "edit" / f"v{rate}"
    tone(e / "voice.wav", [(0.2, 1.0), (1.4, 2.0)], 2.15, rate=rate, stereo=stereo)
    m = mouth(project, e)
    assert m["frames"] == 65 and len(m["open"]) == 65 and m["fps"] == 30
    assert max(m["open"][f] for f in inside(m, 0.3, 0.9)) > 0.5
    assert not any(m["open"][f] for f in inside(m, 1.05, 1.35))


# ── the plan's mascot ──

def mascot_project(project, reel=None, tone_preset="expert"):
    """A 30 s edit with captions, a narration track matching its lines, a brand with a drawn mascot."""
    e = plan_project(project, reel)
    b = json.loads((project / "brands" / "acme" / "brand.json").read_text(encoding="utf-8"))
    b["tone"] = {"preset": tone_preset, "overrides": {}}
    write_json(project / "brands" / "acme" / "brand.json", b)
    rem = project / "reels"
    write_json(rem / "package.json", {"name": "reels"})
    (rem / "src" / "mascot").mkdir(parents=True)
    (rem / "src" / "mascot" / "Sprout.tsx").write_text(COMPONENT, encoding="utf-8")
    write_json(project / "it-reelsmaker.json", {"remotion_dir": "reels"})
    run_script("brand.py", "mascot", "acme", "--drawn", "src/mascot/Sprout.tsx", cwd=project)
    spans = []
    for line, start in LINES:
        spans.append((start, round(start + 0.4 * len(line.split()), 2)))
    tone(e / "voice.wav", spans, 30.0)
    return e, rem


def validate(project, e):
    return run_script("visual_plan.py", "validate", f"edit/{e.name}", cwd=project, check=False)


@needs_ffmpeg
def test_a_same_length_recut_makes_the_mouth_stale(project):
    e, rem = mascot_project(project)
    run_script("mascot.py", "plan", "edit/4821", "--pose", "word:resume#1=point_left", cwd=project)
    run_script("mascot.py", "mouth", "edit/4821", cwd=project)
    run_script("brand.py", "stage", "acme", "--remotion", rem, cwd=project)
    (e / "final.mp4").write_bytes(b"a rough cut")
    run_script("visual_plan.py", "stage", "edit/4821", "--remotion", rem, "--props", rem / "props.json", cwd=project)
    props = json.loads((rem / "props.json").read_text(encoding="utf-8"))
    assert props["mascot"]["kind"] == "drawn" and props["mascot"]["module"] == "acme"
    # the narration re-cut: the same length, the phrases elsewhere
    tone(e / "voice.wav", [(1.0, 4.0), (9.0, 15.0)], 30.0)
    r = run_script("visual_plan.py", "stage", "edit/4821", "--remotion", rem, "--props", rem / "props.json",
                   cwd=project, check=False)
    assert r.returncode != 0 and "mascot.py mouth" in (r.stdout + r.stderr), r.stdout + r.stderr


@needs_ffmpeg
def test_the_staged_mascot_is_closed_in_pauses_and_after_the_narration(project):
    e, rem = mascot_project(project)
    run_script("mascot.py", "plan", "edit/4821", "--pose", "word:resume#1=point_left", "--pose", "word:speed#1=palm",
               cwd=project)
    m = mouth(project, e)
    run_script("brand.py", "stage", "acme", "--remotion", rem, cwd=project)
    (e / "final.mp4").write_bytes(b"a rough cut")
    run_script("visual_plan.py", "stage", "edit/4821", "--remotion", rem, "--props", rem / "props.json", cwd=project)
    mp = json.loads((rem / "props.json").read_text(encoding="utf-8"))["mascot"]
    fr = mp["frames"]

    def at(f):  # the entry that holds on frame f (the kit plays them so)
        return [x for x in fr if x["f"] <= f][-1]
    assert fr[0]["f"] == round(mp["from"] * 30)
    # the pause between the 1st and 2nd lines (2.6-3.0 s) and the tail after the last word
    assert all(at(f)["open"] == 0 for f in range(80, 89))
    assert all(at(f)["open"] == 0 for f in range(round(28.0 * 30), round(mp["to"] * 30)))
    assert any(at(f)["open"] > 0.3 for f in range(round(0.3 * 30), round(2.4 * 30)))
    # the pose changes on its word ("resume" at 4.6 s) and eases in without a bounce (expert: no overshoot)
    f0 = round(4.6 * 30)
    assert at(f0 - 1)["pose"] == "neutral" and at(f0 + 20)["pose"] == "point_left" and at(f0 + 20)["prev"] == "neutral"
    ks = [at(f)["k"] for f in range(f0, f0 + 20)]
    assert ks == sorted(ks) and max(ks) == 1 and ks[0] < 0.5
    # the anchor is placed above the subtitle band, in the left half, and the plan keeps the mascot clear
    assert mp["y"] < 1250 and mp["x"] < 540 and 0 < mp["scale"]
    assert any(k.get("mascot") for k in load_plan(e)["keep_clear"])


def test_overshoot_needs_a_loud_scene_tone_and_a_brand_that_bounces(project):
    import mascot_plan as vm
    geo = {"box": (400, 520), "anchor": (200, 170), "poses": ["neutral", "palm"], "symmetric": False}
    m = {"track": [{"t": 1.0, "pose": "palm"}], "from": 0.0, "to": 3.0, "facing": 1}
    plan = {"id": "x", "duration": 3.0, "inserts": []}
    calm = {"brand_tone": {"overshoot": False, "mascot": "full", "scene_tone": "punchy"}, "scene_tone": "punchy"}
    loud = {"brand_tone": {"overshoot": True, "mascot": "full", "scene_tone": "punchy"}, "scene_tone": "punchy"}
    quiet_scene = {"brand_tone": {"overshoot": True, "mascot": "full", "scene_tone": "calm"}, "scene_tone": "calm"}
    capped = {"brand_tone": {"overshoot": True, "mascot": "calm", "scene_tone": "punchy"}, "scene_tone": "punchy"}
    kmax = lambda s: max(x["k"] for x in vm.frames_of(m, plan, s, geo, [0.0] * 90, 30))
    assert kmax(calm) == 1 and kmax(quiet_scene) == 1 and kmax(capped) == 1
    assert kmax(loud) > 1


@needs_ffmpeg
def test_speaking_past_the_narration_is_an_error(project):
    e, rem = mascot_project(project)
    run_script("mascot.py", "plan", "edit/4821", "--speaks", "0-31.5", cwd=project)
    run_script("mascot.py", "mouth", "edit/4821", cwd=project)
    r = validate(project, e)
    assert r.returncode == 1 and "speaks" in r.stdout and "past the narration" in r.stdout, r.stdout


def test_a_pose_word_lost_in_a_recut_is_an_error_naming_it(project):
    e = plan_project(project)
    run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    run_script("mascot.py", "plan", "edit/4821", "--pose", "word:resume#1=point_left", "--speaks", "none", cwd=project)
    cap = captions()
    for w in cap["words"]:
        if w["text"] == "resume":
            w["text"] = "CV"
    write_json(e / "captions.json", cap)
    r = validate(project, e)
    assert r.returncode == 1 and "resume" in r.stdout and "mascot" in r.stdout, r.stdout


def test_a_pose_follows_its_word_in_a_recut_and_init_keeps_the_mascot(project):
    e = plan_project(project)
    run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    run_script("mascot.py", "plan", "edit/4821", "--pose", "word:resume#1=point_left", "--speaks", "none", cwd=project)
    assert load_plan(e)["mascot"]["track"][0]["t"] == 4.6
    cap = captions()
    for w in cap["words"]:
        if w["seg"] == 1:
            w["start"], w["end"] = round(w["start"] + 0.5, 3), round(w["end"] + 0.5, 3)
    write_json(e / "captions.json", cap)
    validate(project, e)
    assert load_plan(e)["mascot"]["track"][0]["t"] == 5.1
    run_script("visual_plan.py", "init", "edit/4821", "--force", cwd=project)
    assert load_plan(e)["mascot"]["track"][0]["at"] == "word:resume#1"


@needs_ffmpeg
def test_the_mascot_on_the_subtitles_the_buttons_or_at_premium_is_an_error(project):
    e, rem = mascot_project(project)
    run_script("mascot.py", "mouth", "edit/4821", cwd=project)
    run_script("mascot.py", "plan", "edit/4821", "--at", "300,1100", "--scale", "1", cwd=project)
    r = validate(project, e)
    assert r.returncode == 1 and "subtitle band" in r.stdout, r.stdout
    run_script("mascot.py", "plan", "edit/4821", "--at", "860,700", "--scale", "1", cwd=project)
    r = validate(project, e)
    assert r.returncode == 1 and "UI zone" in r.stdout and "right" in r.stdout, r.stdout
    run_script("mascot.py", "plan", "edit/4821", "--auto-place", cwd=project)
    r = validate(project, e)
    assert "error: mascot" not in r.stdout, r.stdout
    b = json.loads((project / "brands" / "acme" / "brand.json").read_text(encoding="utf-8"))
    b["tone"] = {"preset": "premium", "overrides": {}}
    write_json(project / "brands" / "acme" / "brand.json", b)
    r = validate(project, e)
    assert r.returncode == 1 and "premium" in r.stdout and "no mascot" in r.stdout, r.stdout


@needs_ffmpeg
def test_poses_change_at_most_every_0_8_s_and_unknown_poses_are_refused(project):
    e, rem = mascot_project(project)
    run_script("mascot.py", "mouth", "edit/4821", cwd=project)
    run_script("mascot.py", "plan", "edit/4821", "--pose", "5.0=palm", "--pose", "5.5=think", cwd=project)
    r = validate(project, e)
    assert r.returncode == 1 and "0.8 s" in r.stdout, r.stdout
    r = run_script("mascot.py", "plan", "edit/4821", "--pose", "9.0=moonwalk", cwd=project, check=False)
    assert r.returncode != 0 and "moonwalk" in r.stderr


@needs_ffmpeg
def test_a_gesture_at_a_scene_entrance_is_a_warning(project):
    e, rem = mascot_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "contrast", "--mode", "overlay",
               "--at", "12.0", "--dur", "2.0", "--lines", "resume", "thinking", "--box", "60,250,900,200",
               "--what", "contrast", "--why", "test", cwd=project)
    run_script("mascot.py", "mouth", "edit/4821", cwd=project)
    run_script("mascot.py", "plan", "edit/4821", "--pose", "12.1=palm", cwd=project)
    r = validate(project, e)
    assert "warning: mascot" in r.stdout and "entrance" in r.stdout, r.stdout
    assert "error: mascot" not in r.stdout, r.stdout


def test_text_over_the_mascot_is_an_error_in_textcheck():
    import textcheck as tc
    log = ('RK_TEXT {"f": 0, "b": [["scene:c01/0.1", "Big claim", 100, 800, 500, 90, 1, 1]], '
           '"m": [[60, 700, 400, 520, 1]]}\n'
           'RK_TEXT {"f": 3, "b": [["scene:c01/0.1", "Big claim", 100, 300, 500, 90, 1, 1]], '
           '"m": [[60, 700, 400, 520, 1]]}\n')
    marks = tc.parse_mascots(log)
    assert marks == {0: [(60, 700, 400, 520, 1)], 3: [(60, 700, 400, 520, 1)]}
    per = tc.parse_log(log)
    on = tc.mascot_frame_issues(per[0], marks[0])
    assert ("error", "on the mascot") in [(i[0], i[1]) for i in on]
    assert not tc.mascot_frame_issues(per[3], marks[3])
    # a problem that lasts: the runs report it with its time, like any other textcheck problem
    runs = tc.check_mascot({f: per[0] for f in range(0, 30, 3)}, {f: marks[0] for f in range(0, 30, 3)}, 3, 30)
    assert runs and runs[0]["kind"] == "on the mascot" and runs[0]["level"] == "error"


# ── Codex review of the branch ──

@needs_ffmpeg
def test_speech_with_no_pauses_still_opens_the_mouth(project):
    # a steady narration covered by words from start to end: its quietest tenth is speech, not noise
    e = project / "edit" / "v4"
    tone(e / "voice.wav", [(0.0, 3.0)], 3.0)
    write_json(e / "captions.json", {"duration": 3.0, "segments": [], "words": [
        {"text": w, "start": round(0.5 * k, 2), "end": round(0.5 * k + 0.5, 2)} for k, w in
        enumerate(["one", "steady", "line", "with", "no", "pause"])]})
    m = mouth(project, e)
    assert sum(1 for o in m["open"] if o > 0.5) > 60, m["speech_frames"]


@needs_ffmpeg
def test_new_words_on_the_same_audio_make_the_mouth_stale(project):
    import mascot_plan as vm
    e, rem = mascot_project(project)
    run_script("mascot.py", "mouth", "edit/4821", cwd=project)
    assert vm.load_mouth(e)[1] is None
    cap = captions()
    for w in cap["words"]:
        if w["seg"] == 2:
            w["start"], w["end"] = round(w["start"] + 1.0, 3), round(w["end"] + 1.0, 3)
    write_json(e / "captions.json", cap)
    m, problem = vm.load_mouth(e)
    assert problem and "captions" in problem


def test_mascot_off_frees_its_box(project):
    e = plan_project(project)
    run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    run_script("mascot.py", "plan", "edit/4821", "--speaks", "none", cwd=project)
    plan = load_plan(e)
    plan["keep_clear"] = [{"start": 0, "end": 30, "box": [60, 700, 400, 520], "what": "mascot", "mascot": True}]
    write_json(e / "visual_plan.json", plan)
    run_script("mascot.py", "plan", "edit/4821", "--off", cwd=project)
    assert "mascot" not in load_plan(e) and not any(k.get("mascot") for k in load_plan(e).get("keep_clear", []))


def test_two_slugs_alike_get_two_names_in_the_registry(project):
    import brand
    rem = project / "reels"
    for s in ("acme-a", "acme_a"):
        brand.register_mascot(rem, s, f"src/mascot/{s}.tsx")
    reg = (rem / "src" / "gen" / "mascots.ts").read_text(encoding="utf-8")
    names = re.findall(r"^import \* as (\w+) from", reg, re.M)
    assert len(names) == 2 and len(set(names)) == 2, reg


@needs_ffmpeg
def test_an_atlas_mascot_reaches_the_kit_with_its_rig(project):
    # references/mascot-atlas.md: the kit reads no files while it renders, so stage puts rig.json's content into
    # props.mascot.rig (the atlas image stays a path inside public/), and the kit's one place for the module
    # (mascotModule) draws kind "atlas" with the atlas renderer instead of drawing nothing
    e, rem = mascot_project(project)
    d = project / "brands" / "acme" / "assets" / "mascot"
    pose = {"cell": [0, 0, 400, 520], "offset": [0, 0], "eyes": [[170, 160], [230, 160]], "mouth": [200, 230],
            "mouthW": 40, "skin": "#f2c9a0", "ink": "#222222"}
    rig = {"atlas": "atlas.png", "width": 800, "height": 520, "symmetric": False, "box": [400, 520],
           "anchor": [200, 170], "poses": {"neutral": pose, "palm": {**pose, "cell": [400, 0, 400, 520]}}}
    write_json(d / "rig.json", rig)
    (d / "atlas.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    run_script("brand.py", "mascot", "acme", "--atlas", "assets/mascot/rig.json", cwd=project)
    run_script("mascot.py", "plan", "edit/4821", "--pose", "word:resume#1=palm", cwd=project)
    run_script("mascot.py", "mouth", "edit/4821", cwd=project)
    run_script("brand.py", "stage", "acme", "--remotion", rem, cwd=project)
    (e / "final.mp4").write_bytes(b"a rough cut")
    run_script("visual_plan.py", "stage", "edit/4821", "--remotion", rem, "--props", rem / "props.json", cwd=project)
    mp = json.loads((rem / "props.json").read_text(encoding="utf-8"))["mascot"]
    assert mp["kind"] == "atlas" and mp["atlas"] == "brands/acme/mascot/atlas.png"
    assert isinstance(mp["rig"], dict) and mp["rig"]["poses"]["palm"]["cell"] == [400, 0, 400, 520]
    assert mp["rig"]["anchor"] == [200, 170] and mp["rig"]["symmetric"] is False
    layer = (CORE.parent / "assets" / "remotion-kit" / "kit" / "mascot" / "MascotLayer.tsx").read_text(encoding="utf-8")
    assert 'from "./AtlasMascot"' in layer
    body = layer[layer.index("export const mascotModule"):]
    body = body[: body.index("\n};") + 3]
    # kind "drawn" from the registry; past it, an atlas with a rig makes (and returns) the atlas module, nothing else
    assert 'if (p.kind === "drawn") return modules[p.module] ?? null;' in body
    assert body.count("return null") == 1 and "m = atlasMascot(p.rig, p.atlas);" in body
    assert body.replace("\r", "").rstrip().endswith("return m;\n};")
    atlas = (CORE.parent / "assets" / "remotion-kit" / "kit" / "mascot" / "AtlasMascot.tsx").read_text(encoding="utf-8")
    assert 'from "./types"' in atlas and "export type MascotFrame" not in atlas


@needs_ffmpeg
def test_an_atlas_rebuilt_after_brand_stage_is_refused(project):
    # the rig and the atlas image reach the kit as one staged pair: an atlas cut again in the brand folder without
    # brand.py stage would put the new rig's frames over the old image (wrong crops), so stage refuses it by name
    e, rem = mascot_project(project)
    d = project / "brands" / "acme" / "assets" / "mascot"
    pose = {"cell": [0, 0, 400, 520], "offset": [0, 0], "eyes": [[170, 160], [230, 160]], "mouth": [200, 230],
            "mouthW": 40, "skin": "#f2c9a0", "ink": "#222222"}
    rig = {"atlas": "atlas.png", "width": 800, "height": 520, "symmetric": True, "box": [400, 520],
           "anchor": [200, 170], "poses": {"neutral": pose, "palm": {**pose, "cell": [400, 0, 400, 520]}}}
    write_json(d / "rig.json", rig)
    (d / "atlas.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    run_script("brand.py", "mascot", "acme", "--atlas", "assets/mascot/rig.json", cwd=project)
    run_script("mascot.py", "plan", "edit/4821", "--pose", "word:resume#1=palm", cwd=project)
    run_script("mascot.py", "mouth", "edit/4821", cwd=project)
    run_script("brand.py", "stage", "acme", "--remotion", rem, cwd=project)
    (e / "final.mp4").write_bytes(b"a rough cut")
    rig["poses"]["palm"]["cell"] = [0, 520, 400, 520]  # cut again: the atlas grew a row
    rig["height"] = 1040
    write_json(d / "rig.json", rig)
    r = run_script("visual_plan.py", "stage", "edit/4821", "--remotion", rem, "--props", rem / "props.json",
                   cwd=project, check=False)
    assert r.returncode != 0 and "brand.py stage" in (r.stdout + r.stderr), r.stdout + r.stderr
    run_script("brand.py", "stage", "acme", "--remotion", rem, cwd=project)
    run_script("visual_plan.py", "stage", "edit/4821", "--remotion", rem, "--props", rem / "props.json", cwd=project)
    mp = json.loads((rem / "props.json").read_text(encoding="utf-8"))["mascot"]
    assert mp["rig"]["poses"]["palm"]["cell"] == [0, 520, 400, 520] and mp["rig"]["height"] == 1040
