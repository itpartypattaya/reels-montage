"""Fixes found while editing two videos (core 1.7.1): false faces at the frame edge, the overlay box on the face, the
cut list's fix fields, words the cloud transcript only estimated, splicing a snip into the transcript, merge advice at
a join, the pacing alias, the add --mode check, export without --props, audit's argument order."""
import json

from conftest import make_speech, needs_ffmpeg, run_script, write_json
from test_media import cut_project
from test_plan import faces_json, load_plan, plan_project


# 1. false faces at the frame edge

def test_a_weak_box_cut_by_the_frame_edge_is_not_a_face():
    # 1789: a 0.68 box on a shoulder at the left edge had one sign (its size) and passed; its "chin" at 1939 lowered
    # the subtitles to the limit
    import faces
    face = [415, 641, 269, 353, 0.93]
    shoulder = [-30, 884, 501, 890, 0.68]
    keep, rej = faces.clean_frames([[face, shoulder]] * 3, times=[54.0, 54.25, 54.5], step=0.25)
    assert keep[1] == [face] and "cut by the frame edge" in rej[1][0][5]
    # the same box away from the edge keeps its single sign: plausible
    inside = [300, 884, 501, 890, 0.68]
    keep, _ = faces.clean_frames([[face, inside]] * 3, times=[54.0, 54.25, 54.5], step=0.25)
    assert keep[1] == [face, inside]
    # a strong box at the edge stays: the other person of a two-person skit after a push-in
    other = [-20, 700, 300, 400, 0.9]
    keep, _ = faces.clean_frames([[face, other]] * 3, times=[1.0, 1.25, 1.5], step=0.25)
    assert keep[1] == [face, other]
    # the right edge in source geometry: the frame width is the file's
    right = [1700, 500, 230, 140, 0.7]  # landscape box at the right edge of a 1920 px source
    keep, rej = faces.clean_frames([[[800, 300, 200, 270, 0.95], right]] * 3, times=[0, 0.25, 0.5], step=0.25, width=1920)
    assert len(keep[1]) == 1 and "cut by the frame edge" in rej[1][0][5]


def test_an_older_faces_json_is_filtered_again_on_reading(project):
    import faces
    e = plan_project(project)
    face, shoulder = [415, 641, 269, 353, 0.93], [-30, 884, 501, 890, 0.68]
    write_json(e / "faces.json", {"step": 0.25, "geometry": "cover", "w": 1080, "h": 1920, "filter": {"v": 5},
                                  "samples": [{"t": k * 0.25, "faces": [face, shoulder]} for k in range(4)]})
    data = faces.load(e)
    assert all(s["faces"] == [face] for s in data["samples"]) and data["filter"]["v"] == faces.FILTER_V


def test_subtitles_follow_only_confident_faces(project, capsys):
    # 1789: top 1390 from a weak box; the real face's chin needed 1250
    import faces
    import visual_plan as vp
    from reels_common import load_config
    e = plan_project(project)
    face, low = [400, 600, 260, 360, 0.95], [700, 1100, 200, 280, 0.8]  # a weak plausible box below, off the column
    write_json(e / "faces.json", {"step": 0.25, "filter": {"v": faces.FILTER_V}, "geometry": "cover", "w": 1080,
                                  "h": 1920, "samples": [{"t": k * 0.25, "faces": [face, low]} for k in range(8)]})
    assert faces.load(e)["samples"][0]["faces"] == [face, low]  # the filter keeps it
    top, _ = vp.subtitle_top(e, load_config(e)[0], None)
    assert top == 1250
    out = capsys.readouterr().out
    assert "box [400, 600, 260, 360, 0.95] at " in out  # which box set the lowest chin


# 2. the overlay scene box

def add_hook(project, check=True):
    return run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "hook", "--variant", "slam",
                      "--mode", "overlay", "--at", "0.2", "--dur", "2.0", "--lines", "Hiring", "--what", "w", "--why", "y",
                      cwd=project, check=check)


def test_an_overlay_scene_takes_a_band_in_the_headroom(project):
    # 1789: every window slot hit a face that sits high; WINDOW_DEFAULT was saved on it with only a warning
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    faces_json(e, [380, 640, 300, 420])
    add_hook(project)
    sc = next(i for i in load_plan(e)["inserts"] if i["kind"] == "scene")
    assert sc["box"] == [60, 250, 900, 330]  # from y 250 down to 60 px above the face (not a 480x360 box on the chest)


def test_an_overlay_scene_with_no_free_box_asks_for_one(project):
    e = plan_project(project, {"use_scenes": True})
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    faces_json(e, [300, 300, 480, 900])  # a face from y 300 to 1200: no slot and no band is free
    r = add_hook(project, check=False)
    assert r.returncode != 0 and "--box" in r.stderr, r.stdout + r.stderr
    assert not [i for i in load_plan(e)["inserts"] if i["kind"] == "scene"]


# 3, 4. cut.py: fix fields, estimated words

@needs_ffmpeg
def test_cut_fix_fields_are_checked_and_fix_takes_pairs(project):
    import cut
    e = cut_project(project)
    doc = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    doc["fix"] = [["recruter", "recruiter"]]  # a list of pairs crashed with an AttributeError
    write_json(e / "cut.json", doc)
    c = cut.load_cut(e, project)
    assert c["fix"] == {"recruter": "recruiter"}
    _, caps, _ = cut.timeline(c, cut.load_words(c))
    assert "recruiter" in [w["text"] for w in caps]
    for key, bad, said in (("fix_at", {"text": "all", "at": 2.0, "to": "x"}, "fix_at is a list"),
                           ("fix_at", [{"text": "all", "to": "x"}], "fix_at[0]"),
                           ("retime", [{"text": "Hello", "at": 0.5, "start": 0.9, "end": 0.4}], "end after start"),
                           ("fix", "recruiter", "fix is")):
        d = {**doc, key: bad}
        write_json(e / "cut.json", d)
        r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project, check=False)
        assert r.returncode == 1 and said in r.stderr and "Traceback" not in r.stderr, (key, r.stderr)


@needs_ffmpeg
def test_cut_names_words_the_cloud_transcript_only_estimated(project):
    # 1094: a cloud-only "Prichyom" 33.12 and "k" 1.46 went into the subtitles without a word
    e = cut_project(project)
    tr = json.loads((e / "transcripts" / "IMG_4821.json").read_text(encoding="utf-8"))
    for w in tr["words"]:
        if w["text"] in ("tail", "gap"):
            w["est"] = True
    write_json(e / "transcripts" / "IMG_4821.json", tr)
    r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project)
    assert "«tail» (main 4.50) was heard only by the cloud transcript" in r.stderr, r.stderr
    assert "«gap»" not in r.stderr  # not in the cut: nothing to listen to
    doc = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    doc["fix_at"].append({"text": "tail", "at": 4.5, "to": ""})  # removed: no longer named
    write_json(e / "cut.json", doc)
    r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project)
    assert "heard only by the cloud" not in r.stderr


# 5. transcribe.py splice

MAIN = {"language_code": "ru", "text": "one two three four", "source": "IMG_4821.MOV", "model": "x",
        "words": [{"text": "one", "start": 0.5, "end": 0.9, "type": "word"},
                  {"text": "twotwo", "start": 1.0, "end": 2.6, "type": "word"},  # a merged retake
                  {"text": "maybe", "type": "word", "est": True, "start": 2.6, "end": 2.8},
                  {"text": "four", "start": 3.5, "end": 3.9, "type": "word"}]}
SNIP = {"language_code": "ru", "text": "two two", "source": "IMG_4821.MOV", "from": 0.95, "to": 3.2,
        "words": [{"text": "two", "start": 1.0, "end": 1.4, "type": "word"},
                  {"text": "two", "start": 2.1, "end": 2.5, "type": "word"}]}


def test_splice_puts_a_snip_into_the_transcript(project):
    e = project / "edit" / "4821"
    write_json(e / "transcripts" / "IMG_4821.json", MAIN)
    write_json(e / "snip" / "IMG_4821_0.95-3.20.json", SNIP)
    r = run_script("transcribe.py", "splice", "edit/4821", "edit/4821/snip/IMG_4821_0.95-3.20.json", cwd=project)
    assert "removed 2 (twotwo maybe), added 2 (two two)" in r.stdout, r.stdout
    doc = json.loads((e / "transcripts" / "IMG_4821.json").read_text(encoding="utf-8"))
    assert [w["text"] for w in doc["words"]] == ["one", "two", "two", "four"]
    assert doc["model"] == "x" and doc["splices"][0]["snip"] == "IMG_4821_0.95-3.20.json"
    assert json.loads((e / "transcripts" / "IMG_4821.presplice.json").read_text(encoding="utf-8")) == MAIN
    # a second splice keeps the first backup and writes the next one
    r = run_script("transcribe.py", "splice", "edit/4821", "IMG_4821_0.95-3.20.json", "--from", "3.4", "--to", "4.0",
                   cwd=project, check=False)
    assert r.returncode != 0 and "leaves the snip's piece" in r.stderr  # the snip did not hear 3.4-4.0: four stays
    write_json(e / "snip" / "IMG_4821_3.40-4.00.json", {**SNIP, "from": 3.4, "to": 4.0,
                                                         "words": [{"text": "for", "start": 3.5, "end": 3.9, "type": "word"}]})
    run_script("transcribe.py", "splice", "edit/4821", "IMG_4821_3.40-4.00.json", cwd=project)
    assert json.loads((e / "transcripts" / "IMG_4821.presplice.json").read_text(encoding="utf-8")) == MAIN
    second = json.loads((e / "transcripts" / "IMG_4821.presplice-2.json").read_text(encoding="utf-8"))
    assert [w["text"] for w in second["words"]] == ["one", "two", "two", "four"]


def test_splice_goes_into_the_transcript_cut_json_names(project):
    e = project / "edit" / "4821"
    write_json(e / "cut.json", {"sources": {"main": {"file": "IMG_4821.MOV", "transcript": "edit/4821/own/main.json"}},
                                "ranges": []})
    write_json(e / "own" / "main.json", MAIN)
    write_json(e / "snip" / "IMG_4821_0.95-3.20.json", SNIP)
    run_script("transcribe.py", "splice", "edit/4821", "IMG_4821_0.95-3.20.json", cwd=project)
    doc = json.loads((e / "own" / "main.json").read_text(encoding="utf-8"))
    assert [w["text"] for w in doc["words"]] == ["one", "two", "two", "four"]
    assert not (e / "transcripts" / "IMG_4821.json").exists()


def test_splice_refuses_a_snip_of_the_rough_cut(project):
    e = project / "edit" / "4821"
    write_json(e / "transcripts" / "IMG_4821.json", MAIN)
    write_json(e / "snip" / "final_1.00-3.00.json", {**SNIP, "source": "final.mp4"})
    r = run_script("transcribe.py", "splice", "edit/4821", "final_1.00-3.00.json", cwd=project, check=False)
    assert r.returncode != 0 and "no main transcript" in r.stderr


# 6, 7. speech_mask.py

def test_a_word_warning_at_a_tight_join_advises_to_merge():
    import speech_mask as sm
    ranges = [{"source": "main", "start": 0.5, "end": 3.0}, {"source": "main", "start": 3.1, "end": 5.0},
              {"source": "main", "start": 6.0, "end": 8.0}]
    end = "end 3.00 is inside a word: speech from 3.02, dip 0.02 s, that is not a pause"
    assert "merge ranges 0 and 1, or move both edges into a pause" in sm.at_join(end, 0, ranges)
    start = "start 3.10 is inside a word: speech until 3.08, the dip between them is 0.02 s, that is not a pause"
    assert "merge ranges 0 and 1" in sm.at_join(start, 1, ranges)
    assert sm.at_join(end.replace("3.00", "5.00"), 1, ranges) == ""  # the next range is 1 s later: a real cut
    assert sm.at_join("end 3.00 is right at the end of sound: the 30 ms fade will eat the ending", 0, ranges) == ""


@needs_ffmpeg
def test_density_tight_is_max(project):
    wav = make_speech(project / "a.wav", [(0.3, 1.0), (1.3, 2.0)], 2.5)
    r = run_script("speech_mask.py", wav, "--spans", "0.2-2.2", "--density", "tight", cwd=project)
    assert "pacing max" in r.stderr and "pauses ≥160 ms" in r.stderr


# 8-11. visual_plan.py add --mode, export without --props, faces.py audit

def test_add_checks_the_mode_per_kind(project):
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    r = run_script("visual_plan.py", "add", "edit/4821", "--kind", "broll", "--mode", "full", "--at", "1.0", "--dur", "2",
                   "--what", "w", "--why", "y", cwd=project, check=False)
    assert r.returncode != 0 and "full frame for B-roll is `replace`" in r.stderr
    assert not load_plan(e)["inserts"]


def test_export_without_props_says_so(project):
    e = plan_project(project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    write_json(rem / "package.json", {"name": "reels"})
    r = run_script("visual_plan.py", "export", "edit/4821", "--remotion", rem, cwd=project)
    assert "no --props" in r.stdout and "reelkit-props.json" in r.stdout
    assert not (e / "reelkit-props.json").exists()


def test_audit_names_the_argument_order(project):
    plan_project(project)
    r = run_script("faces.py", "audit", "edit/4821", "--edit", "edit/4821", cwd=project, check=False)
    assert r.returncode != 0 and "audit out/<render>.mp4 --edit edit/<id>" in r.stderr, r.stdout + r.stderr
