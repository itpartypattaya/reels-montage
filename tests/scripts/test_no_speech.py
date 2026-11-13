"""The no-speech reel (core phase 2 of the no-speaker reels): no voice at all, the text carries it.

Requirements, in words:
- reel.json -> voice: none. The video's clock is the text, not a voice: edit/<id>/script.json holds the text blocks of
  the brief word for word (stable ids, a role each: hook, setup, label, translation, punchline, cta). A block lasts as
  long as its scene needs to be read: the reading floor counts from the frame when the whole text is on screen and the
  entrance is over until the text starts to leave, exactly as the plan check counts it; one frame less would fail it.
  With a tempo the block may run on to the next beat, never end before its reading is done.
- cut.py builds such a video from silent clips with no sound source at all: picture blocks anchored to the text blocks
  ("block:<id>"), the clip's own color per place, a stretch with only graphics on the style's background. The rough cut
  is final.mp4 of exactly the text's length; captions.json is valid with no speech in it (segments [] and words [],
  the picture shots kept); edl.json has no sound to check. A stretch with no picture is an error with its seconds.
- visual_plan.py init --no-speech makes the scenes from the script, word for word; validate fails a scene whose text is
  not the script's, a block left out or shown twice, and a script edited after it was timed.
- Over a no-speech picture the rules that protect a speaker's face do not hold (the insert budget, the full hook's
  1.5 s, two full scenes in a row, the brand tone's ceiling of full scenes); the reading floor, the brand tone's
  transitions and "the end" still do. The video may end on its punchline (no CTA): the last block of the script.
- stage writes the format for the kit (props.format, never guessed from an empty video), no subtitles, the empty
  captions with the picture shots, no translated subtitles; the series' rubric label and the corner logo for the last
  seconds only are parameters of the video, kept by a series preset with the voice and the music.
- music.py composes the music in code (numpy, no model, no sound file): WAV PCM s16 48 kHz stereo, exactly the
  video's length in samples, the peak at most -6 dBFS and never clipped; the same parameters and seed give the same
  bytes, another seed another track. Styles differ in instruments, rhythm and density; the ambient one may have no
  marked beat. Markers stop/resume/button/pause land on beats; a marker outside the video or closer than a beat to
  another is an error. beats.json says what WAV it belongs to (its hash), the beats with their strength, where the beat
  is heard, the intended silences and every marker's requested and resolved time with the text block it serves.
- master_audio.py: the code music's own silence (after the button, a pause) is intended; a licensed track that ends
  before a no-speech video does is an error; music whose beats.json is another WAV's, or whose length is not the
  video's (end card included), is refused. After the scene sounds the mix is still -14 +-0.7 LUFS with the true peak
  under -1 dBFS, measured on the finished AAC. "A track in the app" masters with the sounds and says to pick the track.
- vp_core.resolve_at understands beat:N, marker:<kind> and block:<id>; doctor.py names numpy.
- The cover (poster.py pick) of a no-speech reel is the script's hook block, whatever it is drawn as, never the
  rubric label; nothing in it is timed to speech, since the sound is music.
"""
import json
import math
import subprocess
import wave

import pytest

from conftest import CORE, ffmpeg, make_video, needs_ffmpeg, probe_streams, run_script, write_json
from test_callouts import KIT, needs_node

BLOCKS = [
    {"id": "hook", "role": "hook", "lines": ["The ad says:", "no income ceiling"], "type": "hook", "variant": "slam",
     "what": "the hook over the office", "why": "the job ad's promise"},
    {"id": "label", "role": "label", "lines": ["TRANSLATING:"], "what": "the label on the field",
     "why": "the turn to the translation"},
    {"id": "translation", "role": "translation", "lines": ["We don't know yet what you will earn."],
     "what": "the translation over the sunset", "why": "what the ad means"},
    {"id": "punchline", "role": "punchline", "lines": ["But sell a lot,", "and you will earn a lot"], "hold": 1.0,
     "what": "the punchline, larger", "why": "the joke lands"},
]


def flat_clip(path, color, w, h, dur, rate):
    """A silent wide shot with no audio stream at all."""
    ffmpeg("-f", "lavfi", "-i", f"color=c={color}:size={w}x{h}:rate={rate}:duration={dur}", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", path)
    return path


def brand(project):
    write_json(project / "brands" / "acme" / "brand.json",
               {"name": "Acme", "slug": "acme", "schema": 2, "tone": {"preset": "expert", "overrides": {}},
                "colors": {"bg": "#0B3D2E", "accent": "#F2C14E", "text": "#FFFFFF"}})


def silent_project(project, blocks=None, picture=None, reel=None):
    brand(project)
    flat_clip(project / "office.mp4", "blue", 720, 1280, 8.0, 30)
    flat_clip(project / "sunset.mov", "orange", 1920, 1080, 12.0, 25)
    e = project / "edit" / "s1"
    write_json(e / "reel.json", {"brand": "acme", "use_scenes": True, "voice": "none", **(reel or {})})
    write_json(e / "script.json", {"blocks": blocks or BLOCKS})
    if picture is None:
        picture = [
            {"from": "start", "to": "block:label", "shots": [
                {"source": "office", "start": 1.0, "speed": 0.8, "what": "the office, wide", "why": "the setup"}]},
            {"from": "block:label", "to": "block:translation", "shots": [
                {"fill": True, "what": "the style's field", "why": "the label alone"}]},
            {"from": "block:translation", "to": "end", "shots": [
                {"source": "sunset", "start": 0.5, "what": "the sunset", "why": "no ceiling"}]}]
    write_json(e / "cut.json", {"fps": 30, "sources": {
        "office": {"file": "office.mp4", "strangers": []},
        "sunset": {"file": "sunset.mov", "strangers": [], "look": {"correct": "colorchannelmixer=rr=0.6:gg=0.6:bb=0.6"}}},
        "picture": picture, "balance": False})
    return e


def timing(e):
    return json.loads((e / "script.json").read_text(encoding="utf-8"))["timing"]


def plan(e):
    return json.loads((e / "visual_plan.json").read_text(encoding="utf-8"))


def rgb_at(f, t):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(f), "-frames:v", "1", "-vf",
                        "scale=1:1:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return tuple(r.stdout[:3])


# --- the text clock -----------------------------------------------------------------------------------------------

def test_a_block_lasts_exactly_its_reading_floor_as_the_plan_check_counts_it(project):
    import vp_scenes
    from reels_common import load_config
    e = silent_project(project)
    run_script("visual_plan.py", "script", "edit/s1", cwd=project)
    tm = timing(e)
    assert [b["id"] for b in tm["blocks"]] == [b["id"] for b in BLOCKS]
    assert tm["blocks"][0]["start"] == 0.0
    for a, b in zip(tm["blocks"], tm["blocks"][1:]):  # back to back, whole frames
        assert math.isclose(a["start"] + a["dur"], b["start"], abs_tol=2e-3)
        assert abs(round(b["start"] * 30) - b["start"] * 30) < 0.05  # a frame (times keep 3 decimals)
    assert math.isclose(tm["duration"], tm["blocks"][-1]["start"] + tm["blocks"][-1]["dur"], abs_tol=2e-3)
    # each block's scene, at the block's length, passes the plan's own reading floor; one frame shorter it fails
    s, _, doc, _, br = load_config(e)
    import vp_script
    for blk, t in zip(BLOCKS, tm["blocks"]):
        sc = vp_script.scene_of(blk, t)
        hold = blk.get("hold", 0.0)
        for dur, ok in ((t["dur"] - hold, True), (t["dur"] - hold - 1 / 30, False)):
            x = {**sc, "start": 0.0, "dur": round(dur, 4)}
            errs, _, _ = vp_scenes.check_scenes(e, {"format": "silent", "duration": 30.0}, s, doc, br, None,
                                                {"words": []}, [x], [], [])
            floor = [m for m in errs if "reading-time floor" in m]
            assert (not floor) == ok, (blk["id"], dur, errs)


def test_with_a_tempo_a_block_runs_on_to_the_next_beat_and_is_never_shorter(project):
    e = silent_project(project)
    run_script("visual_plan.py", "script", "edit/s1", cwd=project)
    plain = {b["id"]: b["dur"] for b in timing(e)["blocks"]}
    run_script("visual_plan.py", "script", "edit/s1", "--bpm", "100", cwd=project)
    tm = timing(e)
    beat = 60 / 100
    assert tm["bpm"] == 100
    for b in tm["blocks"]:
        end = b["start"] + b["dur"]
        k = round(end / beat)
        assert abs(end - k * beat) <= 0.5 / 30 + 1e-6, (b, end)  # on a beat, to the frame
        assert b["dur"] >= plain[b["id"]] - 1e-6 or b["start"] > 0  # never shorter than reading needs
        assert b["start"] + b["dur"] >= b["start"] + b["read"] - 1e-6
    ends = [b["start"] + b["dur"] for b in tm["blocks"]]
    cum = 0.0
    for b, end in zip(tm["blocks"], ends):
        cum += plain[b["id"]]
        assert end >= cum - 1e-6 and end < cum + beat * len(ends) + 1e-6


def test_a_script_block_must_be_a_text_scene_with_a_unique_id(project):
    e = silent_project(project, blocks=[BLOCKS[0], {**BLOCKS[1], "id": "hook"}])
    r = run_script("visual_plan.py", "script", "edit/s1", cwd=project, check=False)
    assert r.returncode != 0 and "hook" in (r.stdout + r.stderr) and "twice" in (r.stdout + r.stderr)
    silent_project(project, blocks=[BLOCKS[0], {**BLOCKS[1], "type": "list"}])
    r = run_script("visual_plan.py", "script", "edit/s1", cwd=project, check=False)
    assert r.returncode != 0 and "list" in (r.stdout + r.stderr)
    silent_project(project, blocks=[BLOCKS[0], {**BLOCKS[1], "lines": []}])
    r = run_script("visual_plan.py", "script", "edit/s1", cwd=project, check=False)
    assert r.returncode != 0 and "label" in (r.stdout + r.stderr)


# --- the rough cut ----------------------------------------------------------------------------------------------

@needs_ffmpeg
def test_silent_clips_and_the_text_make_one_rough_cut_with_empty_captions(project):
    e = silent_project(project)
    run_script("visual_plan.py", "script", "edit/s1", cwd=project)
    tm = timing(e)
    r = run_script("cut.py", "edit/s1", cwd=project)
    assert "speech_mask" not in r.stdout  # nothing spoken to check
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    assert cap["segments"] == [] and cap["words"] == []
    assert math.isclose(cap["duration"], tm["duration"], abs_tol=2e-3)
    shots = cap["shots"]
    assert [g["source"] for g in shots] == ["office", None, "sunset"]
    lab = next(b for b in tm["blocks"] if b["id"] == "label")
    tr = next(b for b in tm["blocks"] if b["id"] == "translation")
    assert math.isclose(shots[1]["out_start"], lab["start"], abs_tol=2e-3)
    assert math.isclose(shots[2]["out_start"], tr["start"], abs_tol=2e-3)
    assert shots[0]["speed"] == 0.8 and shots[1]["kind"] == "fill"
    assert cap.get("picture_id")
    st = probe_streams(e / "final.mp4")
    assert (st["video"]["width"], st["video"]["height"]) == (1080, 1920)
    assert abs(float(st["video"]["duration"]) - tm["duration"]) < 0.05
    edl = json.loads((e / "edl.json").read_text(encoding="utf-8"))
    assert edl["ranges"] == [] and edl["sources"] == {} and set(edl["picture_sources"]) == {"office", "sunset"}
    # the office keeps the video's color, the sunset its own darker look
    office, sunset = rgb_at(e / "final.mp4", 0.5), rgb_at(e / "final.mp4", tr["start"] + 1.0)
    assert office[2] > 150 and sunset[0] < 200 and sunset[0] > sunset[2], (office, sunset)


@needs_ffmpeg
def test_a_stretch_of_a_no_speech_video_with_no_picture_is_an_error_with_its_seconds(project):
    e = silent_project(project, picture=[{"from": "start", "to": "block:translation", "shots": [
        {"source": "office", "start": 0.0, "what": "office", "why": "setup"}]}])
    run_script("visual_plan.py", "script", "edit/s1", cwd=project)
    r = run_script("cut.py", "edit/s1", "--dry-run", cwd=project, check=False)
    assert r.returncode != 0 and "uncovered" in (r.stdout + r.stderr), r.stdout + r.stderr
    assert not (e / "final.mp4").exists()


@needs_ffmpeg
def test_a_no_speech_cut_needs_its_text_timed_and_no_sound_ranges(project):
    e = silent_project(project)
    r = run_script("cut.py", "edit/s1", "--dry-run", cwd=project, check=False)  # script.json not timed yet
    assert r.returncode != 0 and "visual_plan.py script" in (r.stdout + r.stderr), r.stdout + r.stderr
    run_script("visual_plan.py", "script", "edit/s1", cwd=project)
    cut = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    write_json(e / "cut.json", {**cut, "ranges": [{"source": "office", "start": 0, "end": 3}]})
    r = run_script("cut.py", "edit/s1", "--dry-run", cwd=project, check=False)
    assert r.returncode != 0 and "voice" in (r.stdout + r.stderr) and "none" in (r.stdout + r.stderr)
    # a script edited after its timing: timed again before cutting
    write_json(e / "cut.json", cut)
    sc = json.loads((e / "script.json").read_text(encoding="utf-8"))
    sc["blocks"][2]["lines"] = ["We don't know yet what you will earn, honestly."]
    write_json(e / "script.json", sc)
    r = run_script("cut.py", "edit/s1", "--dry-run", cwd=project, check=False)
    assert r.returncode != 0 and "visual_plan.py script" in (r.stdout + r.stderr)


# --- the plan ---------------------------------------------------------------------------------------------------

def cut_and_init(project, e):
    run_script("visual_plan.py", "script", "edit/s1", cwd=project)
    run_script("cut.py", "edit/s1", cwd=project)
    run_script("visual_plan.py", "init", "edit/s1", "--no-speech", cwd=project)


def validate(project):
    r = run_script("visual_plan.py", "validate", "edit/s1", cwd=project, check=False)
    return r.returncode, r.stdout + r.stderr


@needs_ffmpeg
def test_init_no_speech_makes_the_scenes_from_the_script_word_for_word(project):
    e = silent_project(project)
    cut_and_init(project, e)
    p = plan(e)
    tm = timing(e)
    assert p["format"] == "silent" and p["segments"] == []
    sc = [i for i in p["inserts"] if i["kind"] == "scene"]
    assert [x["script"] for x in sc] == [b["id"] for b in BLOCKS]
    for x, b, t in zip(sc, BLOCKS, tm["blocks"]):
        assert x["text"]["lines"] == b["lines"]
        assert math.isclose(x["start"], t["start"], abs_tol=2e-3) and math.isclose(x["dur"], t["dur"], abs_tol=2e-3)
        assert x["source"]["kind"] == "brief"
    code, out = validate(project)
    assert code == 0, out


def test_by_default_the_clips_stay_on_screen_under_the_text():
    # a no-speech reel is cut from its clips: a block whose scene covered the frame (full) back to back with the next
    # would hide them for the whole video (2.4: not one frame of the footage was seen). By default the text lies over
    # the picture (overlay), or above it with the picture in the lower window where the type has no overlay (a slogan:
    # split); full only when the block asks for it ("graphics after the hook")
    import vp_script
    t = {"start": 0.0, "dur": 3.0}
    modes = [vp_script.scene_of(b, t)["mode"] for b in BLOCKS]
    assert modes == ["overlay", "overlay", "overlay", "split"]
    assert vp_script.scene_of({**BLOCKS[2], "mode": "full"}, t)["mode"] == "full"
    from vp_scenes import SCENE_TYPES
    for b in BLOCKS + [{"id": "c", "role": "cta", "lines": ["Write to us"]}, {**BLOCKS[0], "type": "contrast"}]:
        sc = vp_script.scene_of(b, t)
        assert sc["mode"] in SCENE_TYPES[sc["type"]]["modes"], sc


@needs_ffmpeg
def test_validate_holds_the_scenes_to_the_script(project):
    e = silent_project(project)
    cut_and_init(project, e)
    with open(e / "visual_plan.json", encoding="utf-8") as f:
        p = json.load(f)
    good = json.loads(json.dumps(p))

    def set_plan(x):
        write_json(e / "visual_plan.json", x)

    # a word changed in a scene (the agent "improved" the brief)
    p["inserts"][2]["text"]["lines"] = ["We don't know what you will earn."]
    set_plan(p)
    code, out = validate(project)
    assert code == 1 and "word for word" in out and "translation" in out, out
    # a block left out
    p = json.loads(json.dumps(good))
    p["inserts"] = [i for i in p["inserts"] if i.get("script") != "label"]
    set_plan(p)
    code, out = validate(project)
    assert code == 1 and "label" in out and "missing" in out, out
    # a block shown twice
    p = json.loads(json.dumps(good))
    p["inserts"][3]["script"] = "translation"
    set_plan(p)
    code, out = validate(project)
    assert code == 1 and "twice" in out, out
    # the script edited after its timing
    set_plan(good)
    sc = json.loads((e / "script.json").read_text(encoding="utf-8"))
    sc["blocks"][0]["lines"] = ["The ad says:", "no ceiling at all"]
    write_json(e / "script.json", sc)
    code, out = validate(project)
    assert code == 1 and "visual_plan.py script" in out, out


@needs_ffmpeg
def test_the_speakers_rules_do_not_hold_over_a_no_speech_picture_and_it_may_end_on_its_punchline(project):
    e = silent_project(project)
    cut_and_init(project, e)
    code, out = validate(project)
    assert code == 0, out
    for msg in ("full hook", "two full scenes in a row", "inserts take", "full scenes", "in the last"):
        assert msg not in out, (msg, out)
    # the reading floor still holds
    p = plan(e)
    p["inserts"][2]["dur"] = 0.6
    p["inserts"][3]["start"] = round(p["inserts"][2]["start"] + 0.6, 3)
    write_json(e / "visual_plan.json", p)
    code, out = validate(project)
    assert code == 1 and "reading-time floor" in out, out


@needs_ffmpeg
def test_the_hook_of_a_no_speech_reel_is_its_hook_block_not_a_label_drawn_as_a_hook(project):
    # the real series: the hook is a long quote (no hook scene can hold 9 words), the one-word label is drawn as a hook
    blocks = [{**BLOCKS[0], "type": "quote", "variant": None,
               "lines": ["When the job ad says:", "«We pay you with no ceiling at all»"]}] + BLOCKS[1:]  # read longest
    e = silent_project(project, blocks=blocks)
    run_script("visual_plan.py", "script", "edit/s1", "--bpm", "104", cwd=project)  # the blocks run on to the beat
    run_script("cut.py", "edit/s1", cwd=project)
    run_script("visual_plan.py", "init", "edit/s1", "--no-speech", cwd=project)
    code, out = validate(project)
    assert code == 0 and "the hook is settled" not in out, out
    # a hook block that really is read for less than another block still gets the warning
    p = plan(e)
    p["inserts"][3]["dur"] = round(p["inserts"][3]["dur"] + 3.0, 3)
    p["inserts"][3]["role"] = "point"  # held longer than it needs, and not the ending
    write_json(e / "visual_plan.json", p)
    import vp_scenes
    from reels_common import load_config
    s, _, doc, _, br = load_config(e)
    errs, warns, _ = vp_scenes.check_scenes(e, {**p, "duration": 40.0}, s, doc, br, None, {"words": []},
                                            [x for x in p["inserts"]], [], [])
    assert any("the hook is settled" in w for w in warns), warns


# --- stage and the kit ------------------------------------------------------------------------------------------

@needs_ffmpeg
def test_stage_gives_the_kit_the_format_empty_subtitles_and_the_series_marks(project):
    e = silent_project(project, reel={"subtitles_lang": "en", "rubric": "JOB AD TRANSLATOR", "corner_last_s": 1.5})
    cut_and_init(project, e)
    write_json(e / "captions-en.json", {"duration": 1.0, "segments": [], "words": [{"text": "x", "start": 0, "end": 1}]})
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    write_json(rem / "package.json", {"name": "reels"})
    run_script("brand.py", "stage", "acme", "--remotion", rem, cwd=project)
    run_script("visual_plan.py", "stage", "edit/s1", "--remotion", rem, "--props", rem / "props.json", "--corner",
               cwd=project)
    p = json.loads((rem / "props.json").read_text(encoding="utf-8"))
    tm = timing(e)
    assert p["format"] == "silent" and p["voiceMode"] == "none" and p["subtitles"] == "none"
    assert p["video"] == "s1/video.mp4"
    assert p["captions"]["segments"] == [] and p["captions"]["words"] == [] and len(p["captions"]["shots"]) == 3
    assert "subtitleCaptions" not in p
    assert p["rubric"] == {"text": "JOB AD TRANSLATOR", "from": 0.0, "to": tm["duration"]}
    assert p["corner"] is True and math.isclose(p["cornerFrom"], tm["duration"] - 1.5, abs_tol=2e-3)


@needs_ffmpeg
def test_a_scene_box_never_lies_under_the_rubric_label(project):
    # 2.4: the series' rubric (kit: a plate at y 228-288) covered the top of the hook's plate in the default overlay box
    e = silent_project(project, reel={"rubric": "JOB AD TRANSLATOR"})
    cut_and_init(project, e)
    p = plan(e)
    hook = p["inserts"][0]
    assert hook["mode"] == "overlay" and hook["box"] and hook["box"][1] >= 290, hook  # init put it below the label
    code, out = validate(project)
    assert code == 0, out
    p["inserts"][0]["box"] = [60, 250, 900, 675]  # the default overlay box, under the label
    write_json(e / "visual_plan.json", p)
    code, out = validate(project)
    assert code == 1 and "rubric" in out and "c01" in out, out


@needs_node
def test_the_kit_takes_the_format_from_the_props_and_shows_the_series_marks_in_their_seconds(tmp_path):
    series = KIT / "kit" / "series.ts"
    cases = [
        {"video": "", "captions": {"duration": 10}},
        {"video": "", "format": "scenes-only", "captions": {"duration": 10}},
        {"video": "v.mp4", "format": "silent", "captions": {"duration": 10}},
        {"video": "v.mp4", "captions": {"duration": 10}},
    ]
    data = tmp_path / "c.json"
    data.write_text(json.dumps(cases), encoding="utf-8")
    code = ("const m = await import(process.argv[1]); const fs = await import('node:fs');"
            "const cs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));"
            "const p = {captions: {duration: 10}, corner: true, cornerFrom: 8.5, rubric: {text: 'R', from: 0, to: 4}};"
            "console.log(JSON.stringify({only: cs.map((c) => m.scenesOnlyOf(c)),"
            " corner: [0, 254, 255, 299].map((f) => m.cornerOn(p, f, 30)), cornerAlways: m.cornerOn({...p, cornerFrom: null}, 0, 30),"
            " rubric: [0, 119, 120].map((f) => m.rubricOn(p, f, 30))}));")
    r = subprocess.run(["node", "--input-type=module", "-e", code, series.as_uri(), str(data)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got["only"] == [True, True, False, False]
    assert got["corner"] == [False, False, True, True] and got["cornerAlways"] is True
    assert got["rubric"] == [True, True, False]
    reel = (KIT / "ReelKit.tsx").read_text(encoding="utf-8")
    assert "scenesOnly={scenesOnlyOf(p)}" in reel and "scenesOnly={!p.video}" not in reel
    assert "<Rubric p={p}" in reel and "cornerOn(p, frame, KIT_FPS" in reel


@needs_ffmpeg
def test_a_series_preset_keeps_the_voice_the_music_and_the_marks(project):
    music = {"source": "code", "style": "groove", "bpm": 104,
             "markers": {"stop": "label", "resume": "translation", "button": "punchline"}}
    silent_project(project, reel={"music": music, "rubric": "JOB AD TRANSLATOR", "corner_last_s": 1.5})
    run_script("reelcfg.py", "preset", "save", "ads", "--from", "edit/s1", cwd=project)
    run_script("reelcfg.py", "preset", "use", "ads", "edit/s2", cwd=project)
    reel = json.loads((project / "edit" / "s2" / "reel.json").read_text(encoding="utf-8"))
    assert reel["voice"] == "none" and reel["music"] == music
    assert reel["rubric"] == "JOB AD TRANSLATOR" and reel["corner_last_s"] == 1.5
    r = run_script("reelcfg.py", "save", "edit/s2", "--set", "music.source=radio", cwd=project, check=False)
    assert r.returncode != 0 and "app" in (r.stdout + r.stderr)


# --- music in code ----------------------------------------------------------------------------------------------

def music(tmp_path, name, *args):
    out = tmp_path / f"{name}.wav"
    r = run_script("music.py", out, *args, check=False)
    return out, r


def read_wav(p):
    import numpy as np
    with wave.open(str(p)) as w:
        info = (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes())
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, w.getnchannels())
    return info, x


def beats_of(p):
    return json.loads(p.with_suffix(".beats.json").read_text(encoding="utf-8"))


def test_the_music_is_the_videos_length_in_samples_with_headroom_and_no_clipping(tmp_path):
    import numpy as np
    out, r = music(tmp_path, "m", "--dur", "13.37", "--bpm", "104", "--style", "groove", "--seed", "3")
    assert r.returncode == 0, r.stderr
    (ch, width, rate, n), x = read_wav(out)
    assert (ch, width, rate) == (2, 2, 48000)
    assert n == round(13.37 * 48000)
    peak = np.abs(x.astype(np.int32)).max() / 32768
    assert 20 * math.log10(peak) <= -6.0 + 1e-3
    assert np.abs(x.astype(np.int32)).max() < 32767
    assert peak > 0.25  # not a near-silent file either
    b = beats_of(out)
    assert b["schema"] == 1 and b["samples"] == n and b["rate"] == 48000
    import hashlib
    assert b["wav_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()


def test_the_same_parameters_and_seed_give_the_same_bytes_another_seed_another_track(tmp_path):
    a, _ = music(tmp_path, "a", "--dur", "8", "--bpm", "96", "--style", "pulse", "--seed", "1")
    b, _ = music(tmp_path, "b", "--dur", "8", "--bpm", "96", "--style", "pulse", "--seed", "1")
    c, _ = music(tmp_path, "c", "--dur", "8", "--bpm", "96", "--style", "pulse", "--seed", "2")
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes() != c.read_bytes()
    assert beats_of(a)["params_id"] == beats_of(b)["params_id"] != beats_of(c)["params_id"]


def test_the_markers_land_on_beats_and_the_beat_stops_where_the_music_does(tmp_path):
    out, r = music(tmp_path, "m", "--dur", "15", "--bpm", "100", "--style", "groove", "--stop", "3.2",
                   "--resume", "3.7", "--button", "11.0", "--pause", "7.0-7.8")
    assert r.returncode == 0, r.stderr
    b = beats_of(out)
    beat = 60 / 100
    marks = {m["kind"]: m for m in b["markers"]}
    for kind in ("stop", "resume", "button"):
        m = marks[kind]
        k = round(m["at"] / beat)
        assert abs(m["at"] - k * beat) <= 0.5 / b["fps"] + 1e-6, m
        assert abs(m["at"] * b["fps"] - round(m["at"] * b["fps"])) < 0.05  # on a frame (3 decimals)
        assert abs(m["at"] - m["requested"]) <= beat / 2 + 1e-6
    stop, resume, button = marks["stop"]["at"], marks["resume"]["at"], marks["button"]["at"]
    ts = [x["t"] for x in b["beats"]]
    assert not [t for t in ts if stop < t < resume - 1e-6], "a beat heard while the music is stopped"
    assert not [t for t in ts if t > button + 1e-6], "a beat after the button"
    assert {x["strength"] for x in b["beats"]} >= {"strong", "weak"}
    assert all(x["t"] == round(x["t"], 3) for x in b["beats"])
    why = {s["why"] for s in b["silence"]}
    assert {"stop", "pause", "button"} <= why
    # the file is really silent where beats.json says so, and sounds where the beat is heard
    import numpy as np
    _, x = read_wav(out)
    rms = lambda t0, t1: float(np.sqrt(np.mean((x[int(t0 * 48000):int(t1 * 48000)].astype(float) / 32768) ** 2)))  # noqa: E731
    assert rms(stop + 0.05, resume - 0.05) < 1e-4
    assert rms(button + 2.0, 15.0) < 1e-4
    assert rms(0.2, stop - 0.6) > 0.01 and rms(resume + 0.1, 6.9) > 0.005


@pytest.mark.parametrize("args, msg", [
    (["--button", "16"], "outside"),
    (["--stop", "4.0", "--resume", "4.3"], "closer than a beat"),
    (["--resume", "5"], "resume"),
    (["--bpm", "200"], "70"),
])
def test_a_marker_that_cannot_be_played_is_an_error(tmp_path, args, msg):
    base = ["--dur", "15", "--style", "groove"] + ([] if "--bpm" in args else ["--bpm", "100"])
    out, r = music(tmp_path, "m", *base, *args)
    assert r.returncode != 0 and msg in (r.stdout + r.stderr), r.stdout + r.stderr
    assert not out.exists()


def onsets(x, rate=48000, win=0.02):
    """Sharp rises of the level: the count of attacks per second. The level is the RMS over 20 ms (several periods of
    a low note: a 10 ms mean of |x| counted the ripple of a steady chord as 35 attacks a second); an attack is a window
    at least 1.5 times as loud as the one before and above a tenth of the loudest."""
    import numpy as np
    m = (x.astype(float) / 32768).mean(axis=1)
    n = int(rate * win)
    env = np.sqrt((m[: len(m) // n * n].reshape(-1, n) ** 2).mean(axis=1))
    hit = (env[1:] > 1.5 * env[:-1] + 1e-6) & (env[1:] > 0.1 * env.max())
    return int(np.sum(hit[1:] & ~hit[:-1])) / (len(m) / rate)


def test_the_attack_counter_hears_attacks_and_not_a_steady_chord():
    import numpy as np
    t = np.arange(48000 * 4) / 48000
    chord = (np.sin(2 * np.pi * 130.8 * t) + 0.5 * np.sin(2 * np.pi * 196 * t)) * 0.3
    hits = chord * 0
    for k in range(8):  # 2 attacks a second, decaying
        i = int(k * 0.5 * 48000)
        hits[i:] += np.exp(-(t[: len(t) - i]) / 0.05) * np.sin(2 * np.pi * 400 * t[: len(t) - i])
    st = lambda v: np.stack([v, v], 1).astype(np.float64) / np.abs(v).max() * 16000  # noqa: E731
    assert onsets(st(chord).astype(np.int16)) < 0.5
    assert 1.5 <= onsets(st(hits).astype(np.int16)) <= 2.5


def test_the_styles_differ_in_rhythm_and_density_and_the_ambient_may_have_no_beat(tmp_path):
    rates = {}
    for st in ("groove", "pulse", "tension", "ambient"):
        out, r = music(tmp_path, st, "--dur", "10", "--bpm", "100", "--style", st)
        assert r.returncode == 0, r.stderr
        rates[st] = onsets(read_wav(out)[1])
        assert beats_of(out)["style"] == st
        assert beats_of(out)["beat_marked"] is (st != "ambient")
    assert rates["ambient"] < rates["pulse"] < rates["groove"], rates
    assert rates["tension"] > rates["pulse"], rates
    files = [(tmp_path / f"{st}.wav").read_bytes() for st in rates]
    assert len(set(files)) == 4


@needs_ffmpeg
def test_the_music_follows_the_script_and_the_video_with_its_end_card(project):
    music_cfg = {"source": "code", "style": "groove", "bpm": 100,
                 "markers": {"stop": "label", "resume": "translation", "button": "punchline"}}
    e = silent_project(project, reel={"music": music_cfg})
    run_script("visual_plan.py", "script", "edit/s1", "--bpm", "100", cwd=project)
    run_script("cut.py", "edit/s1", cwd=project)
    run_script("visual_plan.py", "init", "edit/s1", "--no-speech", cwd=project)
    p = plan(e)
    p["end_card"] = {"kind": "sting", "seconds": 2.6}
    write_json(e / "visual_plan.json", p)
    r = run_script("music.py", "--edit", "edit/s1", cwd=project)
    tm = timing(e)
    b = json.loads((e / "beats.json").read_text(encoding="utf-8"))
    (_, _, rate, n), _ = read_wav(e / "music.wav")
    assert n == round((tm["duration"] + 2.6) * rate), r.stdout
    starts = {x["id"]: x["start"] for x in tm["blocks"]}
    marks = {m["kind"]: m for m in b["markers"]}
    assert marks["stop"]["block"] == "label" and math.isclose(marks["stop"]["requested"], starts["label"], abs_tol=2e-3)
    assert marks["button"]["block"] == "punchline"
    assert math.isclose(marks["resume"]["at"], starts["translation"], abs_tol=1 / 30 + 1e-6)
    # validate reads it: the beats belong to this WAV; another WAV under the same name is refused
    code, out = validate(project)
    assert code == 0, out
    raw = bytearray((e / "music.wav").read_bytes())  # a sample in the middle changed (the tail is the button's silence)
    raw[len(raw) // 2] ^= 0x55
    (e / "music.wav").write_bytes(bytes(raw))
    code, out = validate(project)
    assert code == 1 and "beats.json" in out, out


def test_resolve_at_takes_beats_markers_and_blocks():
    from vp_core import resolve_at
    plan_ = {"segments": [], "script_timing": [{"id": "label", "start": 2.4, "dur": 1.2}],
             "music": {"beats": [0.0, 0.6, 1.2, 1.8], "markers": {"button": 9.0, "stop": 2.4}}}
    assert resolve_at("beat:3", plan_, {}) == 1.2
    assert resolve_at("marker:button", plan_, {}) == 9.0
    assert resolve_at("block:label", plan_, {}) == 2.4
    for bad in ("beat:9", "marker:resume", "block:nope"):
        with pytest.raises(SystemExit):
            resolve_at(bad, plan_, {})


# --- the master ---------------------------------------------------------------------------------------------------

def render(path, d):
    """A render of a no-speech video: the picture and a silent sound track."""
    ffmpeg("-f", "lavfi", "-i", f"color=c=blue:size=360x640:rate=30:duration={d}", "-f", "lavfi", "-i",
           f"anullsrc=r=48000:cl=stereo", "-t", f"{d}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path)
    return path


def lufs(p):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-af", "ebur128=peak=true", "-f", "null",
                        "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    import re
    i = float(re.search(r"I:\s+(-?[\d.]+) LUFS", tail).group(1))
    tp = float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail).group(1))
    return i, tp


@needs_ffmpeg
def test_after_the_scene_sounds_the_master_is_still_minus_14_with_the_true_peak_under_minus_1(project):
    d = 12.0
    render(project / "render.mp4", d)
    run_script("music.py", project / "music.wav", "--dur", d, "--bpm", "100", "--style", "ambient", cwd=project)
    # a long loud effect (a crowd, a whoosh bed) under the quiet ambient music
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=d=8:c=pink:a=0.9", "-ar", "48000", "-ac", "2", project / "crowd.wav")
    write_json(project / "sfx.json", {"sounds": [{"file": "crowd.wav", "at": 2.0, "gain_db": 0, "what": "crowd"}]})
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", "--music", "music.wav", "--sfx", "sfx.json",
                   cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    i, tp = lufs(project / "master.mp4")
    assert abs(i - (-14.0)) <= 0.7 and tp <= -1.0 + 0.05, (i, tp, r.stdout)


def silent_master_project(project, reel_music, d=10.0):
    brand(project)
    e = project / "edit" / "s1"
    write_json(e / "reel.json", {"brand": "acme", "voice": "none", "music": reel_music})
    write_json(e / "visual_plan.json", {"format": "silent", "duration": d, "inserts": [], "segments": []})
    render(project / "render.mp4", d)
    return e


@needs_ffmpeg
def test_a_licensed_track_that_ends_before_a_no_speech_video_is_an_error(project):
    silent_master_project(project, {"source": "own"})
    ffmpeg("-f", "lavfi", "-i", "sine=f=220:d=6", "-ar", "48000", "-ac", "2", project / "short.wav")
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", "--music", "short.wav", "--edit", "edit/s1",
                   cwd=project, check=False)
    assert r.returncode == 1 and "music" in r.stdout and "ends" in r.stdout, r.stdout
    assert not (project / "master.mp4").exists()


@needs_ffmpeg
def test_the_code_musics_own_silence_is_intended_and_its_beats_must_be_this_wav(project):
    e = silent_master_project(project, {"source": "code"})
    run_script("music.py", e / "music.wav", "--dur", "10", "--bpm", "100", "--button", "6.0", cwd=project)
    (e / "music.beats.json").rename(e / "beats.json")
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", "--music", e / "music.wav", "--edit",
                   "edit/s1", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr  # 4 s of silence after the button: intended, not missing music
    # the length is the video's own (end card included): a track for another length is refused
    run_script("music.py", e / "music.wav", "--dur", "8", "--bpm", "100", cwd=project)
    (e / "music.beats.json").replace(e / "beats.json")
    r = run_script("master_audio.py", "render.mp4", "-o", "master2.mp4", "--music", e / "music.wav", "--edit",
                   "edit/s1", cwd=project, check=False)
    assert r.returncode == 1 and "music.py" in r.stdout, r.stdout
    # beats.json of another WAV
    run_script("music.py", e / "music.wav", "--dur", "10", "--bpm", "100", cwd=project)
    (e / "music.beats.json").replace(e / "beats.json")
    run_script("music.py", e / "music.wav", "--dur", "10", "--bpm", "100", "--seed", "9", cwd=project)
    (e / "music.beats.json").unlink()
    r = run_script("master_audio.py", "render.mp4", "-o", "master3.mp4", "--music", e / "music.wav", "--edit",
                   "edit/s1", cwd=project, check=False)
    assert r.returncode == 1 and "beats.json" in r.stdout, r.stdout


@needs_ffmpeg
def test_a_track_in_the_app_masters_the_sounds_and_says_to_pick_the_track(project):
    silent_master_project(project, {"source": "app"})
    ffmpeg("-f", "lavfi", "-i", "sine=f=900:d=0.3", "-ar", "48000", "-ac", "2", project / "tap.wav")
    write_json(project / "edit" / "s1" / "sfx.json", {"sounds": [{"file": str(project / "tap.wav"), "at": 1.0}]})
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", "--edit", "edit/s1", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "pick" in r.stdout and "app" in r.stdout
    # the brief chose music made in code, and none is given: an error, not a silent video
    silent_master_project(project, {"source": "code"})
    r = run_script("master_audio.py", "render.mp4", "-o", "master2.mp4", "--edit", "edit/s1", cwd=project, check=False)
    assert r.returncode == 1 and "--music" in r.stdout, r.stdout


def test_doctor_names_numpy_for_the_music():
    r = run_script("doctor.py", "--json", check=False)
    data = json.loads(r.stdout)
    names = " ".join(x["name"] for x in data["checks"]) if isinstance(data, dict) else " ".join(x["name"] for x in data)
    assert "numpy" in names and "music.py" in names


# --- the Codex review of 3794a93 (each one reproduces its finding) ---------------------------------------------------

@needs_ffmpeg
def test_a_block_whose_scene_is_skipped_or_pending_is_missing_from_the_screen(project):
    # Codex P1: stage exports only ready scenes; a skipped or pending block passed validate as "present"
    e = silent_project(project)
    cut_and_init(project, e)
    for status in ("skipped", "pending"):
        p = plan(e)
        p["inserts"][1]["status"] = status
        p["inserts"][1]["fallback"] = "the person declined it"
        write_json(e / "visual_plan.json", p)
        code, out = validate(project)
        assert code == 1 and "label" in out and "missing" in out, (status, out)


@needs_ffmpeg
def test_a_no_speech_render_with_some_sound_still_needs_its_music(project):
    # Codex P1: a render with any sound (a B-roll's own audio) took the voice path and skipped the music checks
    silent_master_project(project, {"source": "code"})
    ffmpeg("-f", "lavfi", "-i", "color=c=blue:size=360x640:rate=30:duration=10", "-f", "lavfi", "-i",
           "sine=f=500:d=10,volume=0.3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
           project / "render.mp4")
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", "--edit", "edit/s1", cwd=project, check=False)
    assert r.returncode == 1 and "--music" in r.stdout, r.stdout
    assert not (project / "master.mp4").exists()


@needs_ffmpeg
def test_a_rough_cut_cut_for_another_timing_of_the_same_length_is_stale(project):
    # Codex P2: init and validate compared only the length; two blocks swapped keep it, the block: joins move
    e = silent_project(project)
    cut_and_init(project, e)
    sc = json.loads((e / "script.json").read_text(encoding="utf-8"))
    sc["blocks"][2], sc["blocks"][3] = sc["blocks"][3], sc["blocks"][2]
    write_json(e / "script.json", sc)
    run_script("visual_plan.py", "script", "edit/s1", cwd=project)
    assert math.isclose(timing(e)["duration"], plan(e)["duration"], abs_tol=2e-3)  # the same length
    r = run_script("visual_plan.py", "init", "edit/s1", "--no-speech", "--force", cwd=project, check=False)
    assert r.returncode != 0 and "cut.py" in (r.stdout + r.stderr), r.stdout + r.stderr


def test_markers_on_neighbouring_beats_are_a_beat_apart_whatever_the_frame_rounding(tmp_path):
    # Codex P2: at 104 bpm beats 2 and 3 round to 1.167 and 1.733 s (0.567 s < a beat of 0.577 s): refused wrongly
    out, r = music(tmp_path, "m", "--dur", "8", "--bpm", "104", "--style", "groove", "--stop", "1.154", "--resume",
                   "1.731")
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_beats_heard_are_the_beats_played_on_one_grid(tmp_path):
    # Codex P2: active edges rounded to frames against unrounded beat times: a stopped beat was listed, a resumed one not
    import numpy as np
    out, r = music(tmp_path, "m", "--dur", "8", "--bpm", "104", "--style", "groove", "--stop", "1.154", "--resume",
                   "3.462")
    assert r.returncode == 0, r.stderr
    b = beats_of(out)
    ns = [x["n"] for x in b["beats"]]
    assert 2 not in ns and 6 in ns, ns  # beat 2 is the stop, beat 6 the resume
    _, x = read_wav(out)
    res = next(m["at"] for m in b["markers"] if m["kind"] == "resume")
    pre = x[int((res - 0.15) * 48000):int((res - 0.002) * 48000)]
    assert np.abs(pre.astype(int)).max() == 0  # silent until the resume beat


def test_ambient_comes_back_on_its_resume(tmp_path):
    # Codex P2: the ambient's swell started only every 8 beats: after a resume it stayed silent up to 1.2 s
    import numpy as np
    out, r = music(tmp_path, "m", "--dur", "10", "--bpm", "100", "--style", "ambient", "--stop", "2.4", "--resume", "3.6")
    assert r.returncode == 0, r.stderr
    _, x = read_wav(out)
    after = x[int(3.7 * 48000):int(4.6 * 48000)].astype(float) / 32768
    assert float(np.sqrt(np.mean(after ** 2))) > 0.003


@needs_node
def test_the_series_logo_of_the_last_seconds_shows_over_the_scenes(tmp_path):
    # Codex P2: a no-speech reel has scenes all along; the corner fading out under any scene hid the logo for good
    series = KIT / "kit" / "series.ts"
    code = ("const m = await import(process.argv[1]);"
            "console.log(JSON.stringify([m.cornerFade({cornerFrom: 8.5}, 1), m.cornerFade({format: 'silent'}, 1),"
            " m.cornerFade({}, 1), m.cornerFade({}, 0.25)]));")
    r = subprocess.run(["node", "--input-type=module", "-e", code, series.as_uri()], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [1, 1, 0, 0.75]
    reel = (KIT / "ReelKit.tsx").read_text(encoding="utf-8")
    assert "cornerFade(p, sceneActivity(p.scenes, frame, KIT_FPS))" in reel


@needs_ffmpeg
def test_code_music_starting_on_a_kick_masters_under_minus_1_after_the_aac(project):
    # 2.4 after the review: the music began on a kick straight out of digital silence; with no fade of the master the
    # AAC overshot at the file's start (true peak +1.3 dBFS, the acceptance failed). The track itself eases in.
    d = 14.433
    render(project / "render.mp4", d)
    run_script("music.py", project / "music.wav", "--dur", d, "--bpm", "104", "--style", "groove", "--stop", "3.467",
               "--resume", "5.2", "--button", "8.667", cwd=project)
    # the two effects of the real video: a click on the hook's first line and a card slide on the label
    ffmpeg("-f", "lavfi", "-i", "aevalsrc='(0.5*(2*random(0)-1)+0.5*sin(2*PI*2400*t))*exp(-160*t)':s=48000:d=0.03",
           "-ac", "2", project / "click.wav")
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=c=pink:d=0.4:a=0.8:r=48000,bandpass=f=1500:w=1.2", "-ac", "2",
           project / "slide.wav")
    write_json(project / "sfx.json", {"sounds": [{"file": "click.wav", "at": 0.15, "gain_db": -12},
                                                 {"file": "slide.wav", "at": 3.467, "gain_db": -9}]})
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", "--music", "music.wav", "--sfx", "sfx.json",
                   cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    i, tp = lufs(project / "master.mp4")
    assert abs(i + 14.0) <= 0.7 and tp <= -1.0 + 0.05, (i, tp)


def test_the_music_eases_in_from_silence(tmp_path):
    # the same finding measured on the WAV itself: its first millisecond must rise from silence (a 15 ms ease-in),
    # not jump to a kick at full scale (the AAC of the master overshot there by 2.8 dB on the real video's sounds)
    import numpy as np
    out, r = music(tmp_path, "m", "--dur", "14.433", "--bpm", "104", "--style", "groove", "--stop", "3.467",
                   "--resume", "5.2", "--button", "8.667")
    assert r.returncode == 0, r.stderr
    _, x = read_wav(out)
    a = np.abs(x.astype(float))
    assert a[:48].max() < 0.1 * a.max(), (a[:48].max(), a.max())


@needs_node
def test_the_series_logo_of_the_last_seconds_is_drawn_above_the_scenes(tmp_path):
    # Codex P2 on PR #57: cornerFade() kept the series' logo at full opacity, but the kit drew it BEFORE the scene layer,
    # so the punchline's opaque field (split: the top 900 px; full: the whole frame) covered it all the same. A logo
    # that stays over the scenes (a series' last seconds, a no-speech reel) is drawn above them; the corner logo of a
    # talking head still fades out under a scene, below it, as before.
    series = KIT / "kit" / "series.ts"
    code = ("const m = await import(process.argv[1]);"
            "console.log(JSON.stringify([m.cornerAbove({cornerFrom: 8.5}), m.cornerAbove({format: 'silent'}),"
            " m.cornerAbove({}), m.cornerAbove({cornerFrom: null})]));")
    r = subprocess.run(["node", "--input-type=module", "-e", code, series.as_uri()], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [True, True, False, False]
    reel = (KIT / "ReelKit.tsx").read_text(encoding="utf-8")
    frame = reel[reel.index("<SceneLayer scenes={p.scenes}") - 400:]
    scene = frame.index("<SceneLayer scenes={p.scenes}")
    below = frame.index("{cornerAbove(p) ? null : <Corner p={p} />}")
    above = frame.index("{cornerAbove(p) ? <Corner p={p} /> : null}")
    assert below < scene < above
    assert frame.count("<Corner p={p} />") == 2


def staged_project(project, reel=None):
    """A no-speech reel cut, planned and ready to stage (a Remotion folder with the brand's files)."""
    e = silent_project(project, reel=reel)
    cut_and_init(project, e)
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    write_json(rem / "package.json", {"name": "reels"})
    run_script("brand.py", "stage", "acme", "--remotion", rem, cwd=project)
    return e, rem


def stage(project, rem, *flags):
    return run_script("visual_plan.py", "stage", "edit/s1", "--remotion", rem, "--props", rem / "props.json", *flags,
                      cwd=project, check=False)


@needs_ffmpeg
def test_changing_the_ending_after_the_music_names_the_music_for_that_ending_and_it_stages(project):
    # Codex P2 on PR #57: music made for the video with its sting; then the sting is taken off. stage refused the old
    # track (right), but the music.py command it named read the OLD ending from the plan and made the same length
    # again: the next stage failed the same way, round and round. The refusal now names the music for the ending asked
    # for, music.py makes that length, and the stage goes through and records the new ending.
    e, rem = staged_project(project, reel={"music": {"source": "code", "style": "groove", "bpm": 100}})
    assert stage(project, rem, "--sting").returncode == 0
    assert plan(e)["end_card"]["seconds"] == 2.6
    run_script("music.py", "--edit", "edit/s1", cwd=project)  # made for the video with its sting
    d = timing(e)["duration"]
    (_, _, rate, n), _ = read_wav(e / "music.wav")
    assert n == round((d + 2.6) * rate)
    r = stage(project, rem, "--no-end")
    assert r.returncode != 0
    assert "music.py --edit edit/s1 --end none" in r.stdout + r.stderr, r.stdout + r.stderr
    run_script("music.py", "--edit", "edit/s1", "--end", "none", cwd=project)
    (_, _, rate, n), _ = read_wav(e / "music.wav")
    assert n == round(d * rate)
    r = stage(project, rem, "--no-end")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (plan(e).get("end_card") or {}).get("seconds")
    # and back: a sting asked for again names the music with the sting's length
    r = stage(project, rem, "--sting")
    assert r.returncode != 0 and "music.py --edit edit/s1 --end sting" in r.stdout + r.stderr, r.stdout + r.stderr
    run_script("music.py", "--edit", "edit/s1", "--end", "sting", cwd=project)
    (_, _, rate, n), _ = read_wav(e / "music.wav")
    assert n == round((d + 2.6) * rate)
    assert stage(project, rem, "--sting").returncode == 0


@needs_ffmpeg
def test_the_cover_of_a_no_speech_reel_is_its_hook_block_not_the_label_and_not_timed_to_speech(project):
    # 2.4 found it: poster.py pick took the frame of the rubric label ("TRANSLATING:", drawn as a hook scene) at 4.37 s,
    # not the video's hook (a long hook line is drawn as a quote), and said "in a pause of the speech" of a reel that
    # has no speech: the music's gaps were taken for pauses. In a no-speech reel the cover is the script's hook block,
    # the middle of its settled window, with nothing timed to speech (no "on speech" marks, no mid-word warning).
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=7", "-f", "lavfi",
           "-i", "sine=f=300:d=7,volume='if(between(t,3.6,3.9),0,1)':eval=frame", "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", project / "r.mp4")
    e = project / "edit" / "silent1"
    write_json(e / "reel.json", {"voice": "none", "scene_tone": "calm"})
    sc = {"kind": "scene", "mode": "overlay", "status": "planned"}
    write_json(e / "visual_plan.json", {"id": "silent1", "format": "silent", "duration": 7.0, "segments": [], "inserts": [
        dict(sc, id="c01", type="quote", role="hook", script="hook", start=0.0, dur=3.0),
        dict(sc, id="c02", type="hook", role="label", script="label", start=3.0, dur=1.6),
        dict(sc, id="c03", type="quote", role="translation", script="translation", start=4.6, dur=2.4)]})
    r = run_script("poster.py", "pick", "edit/silent1", "--render", project / "r.mp4", "-o", project / "c.jpg",
                   cwd=project)
    t = float(r.stdout.split("cover: frame at ")[1].split(" s")[0])
    # the hook's settled window, calm tone: 14 frames in, 9 out at 30 fps -> 0.47-2.70 s, its middle 1.58 s
    assert 1.5 <= t <= 1.7 and "c01" in r.stdout, r.stdout
    assert "pause of the speech" not in r.stdout and "quietest moment" not in r.stdout, r.stdout
    r = run_script("poster.py", "pick", "edit/silent1", "--render", project / "r.mp4", "--sheet", project / "s.jpg",
                   cwd=project)
    assert "(on speech)" not in r.stdout and "every candidate is on speech" not in r.stdout, r.stdout
    assert "c01" in r.stdout, r.stdout
    r = run_script("poster.py", "pick", "edit/silent1", "--render", project / "r.mp4", "--t", "2.0", "-o",
                   project / "c.jpg", cwd=project)
    assert "falls on speech" not in r.stderr and "mid-word" not in r.stderr, r.stderr
