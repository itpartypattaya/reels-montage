"""The "scenes + recorded voice" format: a narration recorded on a phone (sound only) is cut like a video's sound and
becomes a video of designed scenes over that narration. Synthetic sound only: tone bursts stand in for the phrases."""
import array
import json
import os
import wave

from conftest import ffmpeg, make_video, needs_ffmpeg, probe_streams, run_script, write_json

# the narration: phrases as tone bursts on a 48 kHz stereo phone recording (m4a), with the transcript of their words
BURSTS = [(0.5, 1.3), (3.0, 3.8), (4.5, 5.3), (6.5, 7.3)]  # "hello there", a bad take, its retake, "the end"
WORDS = [("Hello", 0.5, 0.9), ("there", 0.9, 1.3), ("first", 3.0, 3.4), ("take", 3.4, 3.8),
         ("second", 4.5, 4.9), ("take", 4.9, 5.3), ("the", 6.5, 6.8), ("end", 6.8, 7.3)]
# the cut: the long pause after "there" and the bad take go; 1.2 s per range, x1.2 -> 1.0 s each on the edit timeline
RANGES = [[0.3, 1.5], [4.3, 5.5], [6.3, 7.5]]


def phone_voice(path, dur=8.0, bursts=BURSTS, bed=None):
    """A phone narration: AAC in m4a, stereo, 48 kHz; bed: a steady tone under the voice at this level (music)."""
    on = "+".join(f"between(t,{a},{b})" for a, b in bursts)
    voice = f"sine=f=300:d={dur}:sample_rate=48000,volume='0.5*({on})':eval=frame"
    if bed is None:
        ffmpeg("-f", "lavfi", "-i", voice, "-ac", "2", "-ar", "48000", "-c:a", "aac", "-b:a", "128k", path)
    else:
        ffmpeg("-f", "lavfi", "-i", voice, "-f", "lavfi", "-i", f"sine=f=523:d={dur}:sample_rate=48000,volume={bed}",
               "-filter_complex", "[0:a][1:a]amix=inputs=2:normalize=0[a]", "-map", "[a]", "-ac", "2", "-ar", "48000",
               "-c:a", "aac", "-b:a", "128k", path)
    return path


def voice_project(project, speed=1.2, ranges=RANGES, **kw):
    phone_voice(project / "narration.m4a", **kw)
    e = project / "edit" / "v1"
    write_json(e / "transcripts" / "narration.json",
               {"words": [{"text": t, "start": a, "end": b, "type": "word"} for t, a, b in WORDS]})
    write_json(e / "cut.json", {"fps": 30, "speed": speed, "sources": {"main": {"file": "narration.m4a"}},
                                "ranges": [{"start": a, "end": b} for a, b in ranges]})
    return e


def envelope(path, step=0.005):
    """Mean absolute level per `step` seconds of a 16-bit WAV (both channels), 0..1."""
    with wave.open(str(path), "rb") as w:
        rate, ch = w.getframerate(), w.getnchannels()
        data = array.array("h", w.readframes(w.getnframes()))
    n = int(rate * step) * ch
    return [sum(abs(x) for x in data[k:k + n]) / max(1, len(data[k:k + n])) / 32768 for k in range(0, len(data), n)]


def level(env, a, b, step=0.005):
    part = env[int(a / step):int(b / step)]
    return sum(part) / max(1, len(part))


def onsets(env, step=0.005):
    """Seconds where the sound rises over a third of its peak after a quiet stretch."""
    out, quiet, thr = [], True, max(env) / 3
    for k, v in enumerate(env):
        if quiet and v > thr:
            out.append(round(k * step, 3))
        quiet = v <= thr * 0.5 if not quiet else v <= thr
    return out


@needs_ffmpeg
def test_a_phone_narration_is_cut_by_its_ranges_into_a_voice_track(project):
    # Requirement: a narration with no picture is cut like a video's sound: the ranges keep the phrases, the pause and
    # the bad take are gone, the speed-up applies, and the voice the viewer hears lines up with the subtitle words
    # (within a frame) on the edit timeline. There is no picture, so there is no final.mp4: edit/<id>/voice.wav.
    e = voice_project(project)
    r = run_script("cut.py", "edit/v1", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (e / "final.mp4").exists()
    st = probe_streams(e / "voice.wav")
    assert "video" not in st and float(st["audio"].get("start_time", 0)) == 0  # a WAV has no start offset field
    with wave.open(str(e / "voice.wav"), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (48000, 2, 2)
        assert abs(w.getnframes() / 48000 - 3.0) < 1 / 30  # 3 ranges x 36 frames / 1.2 = 90 frames
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    assert cap["duration"] == 3.0
    got = [(w["text"], w["start"]) for w in cap["words"]]
    assert got == [("Hello", 0.167), ("there", 0.5), ("second", 1.167), ("take", 1.5), ("the", 2.167), ("end", 2.417)]
    assert cap["voice"]["file"] == "voice.wav" and cap["voice"]["stamp"]["fps"] == 30
    # the sound under the words: each phrase starts where its first word does (three control words, +-1 frame) and the
    # removed take is not heard
    env = envelope(e / "voice.wav")
    starts = onsets(env)
    for word in ("Hello", "second", "the"):
        t = next(w["start"] for w in cap["words"] if w["text"] == word)
        assert any(abs(o - t) <= 1 / 30 for o in starts), (word, t, starts)
    assert len(starts) == 3, starts
    for a, b in ((0.3, 0.7), (1.3, 1.7), (2.3, 2.7)):
        assert level(env, a, b) > 0.5 * max(env)
    # edges are checked on the sources as for a video: edl.json for speech_mask.py --edl
    edl = json.loads((e / "edl.json").read_text(encoding="utf-8"))
    assert [(x["start"], x["end"]) for x in edl["ranges"]] == [tuple(x) for x in RANGES]
    r = run_script("speech_mask.py", "--edl", e / "edl.json", cwd=project, check=False)
    assert "Traceback" not in r.stderr, r.stderr


@needs_ffmpeg
def test_a_second_run_with_nothing_changed_is_cached(project):
    # Requirement: running the cut again on the same recording, transcript and cut.json does not rebuild the voice
    # (the stamp: the source's hash + cut.json + fps); a change in cut.json rebuilds it.
    e = voice_project(project)
    run_script("cut.py", "edit/v1", cwd=project)
    before = os.stat(e / "voice.wav").st_mtime_ns
    r = run_script("cut.py", "edit/v1", cwd=project)
    assert "cached" in r.stdout, r.stdout
    assert os.stat(e / "voice.wav").st_mtime_ns == before
    doc = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    doc["ranges"] = doc["ranges"][:2]
    write_json(e / "cut.json", doc)
    r = run_script("cut.py", "edit/v1", cwd=project)
    assert "cached" not in r.stdout
    assert json.loads((e / "captions.json").read_text(encoding="utf-8"))["duration"] == 2.0
    # a source recorded again under the same name is a different recording
    phone_voice(project / "narration.m4a", bursts=BURSTS[:3])
    assert "cached" not in run_script("cut.py", "edit/v1", cwd=project).stdout


@needs_ffmpeg
def test_a_too_short_or_empty_recording_stops_with_a_clear_message(project):
    # Requirement: a 0.2 s recording and an empty file stop with a message that says what is wrong with the file,
    # not with a range error or a traceback; a picture-only option (extract) on a sound-only cut is refused.
    e = project / "edit" / "v1"
    ffmpeg("-f", "lavfi", "-i", "sine=f=300:d=0.2:sample_rate=48000", "-ac", "2", "-c:a", "aac", project / "short.m4a")
    write_json(e / "cut.json", {"fps": 30, "sources": {"main": {"file": "short.m4a"}}, "ranges": [{"start": 0.0, "end": 0.2}]})
    r = run_script("cut.py", "edit/v1", cwd=project, check=False)
    assert r.returncode != 0 and "Traceback" not in r.stderr
    assert "too short" in r.stderr and "0.2" in r.stderr, r.stderr
    (project / "empty.m4a").write_bytes(b"")
    write_json(e / "cut.json", {"fps": 30, "sources": {"main": {"file": "empty.m4a"}}, "ranges": [{"start": 0.0, "end": 1.0}]})
    r = run_script("cut.py", "edit/v1", cwd=project, check=False)
    assert r.returncode != 0 and "Traceback" not in r.stderr
    assert "empty.m4a" in r.stderr and "no sound" in r.stderr, r.stderr
    e2 = voice_project(project)
    doc = json.loads((e2 / "cut.json").read_text(encoding="utf-8"))
    doc["extract"] = {"broll": {"start": 1.0, "end": 2.0}}
    write_json(e2 / "cut.json", doc)
    r = run_script("cut.py", "edit/v1", "--dry-run", cwd=project, check=False)
    assert r.returncode != 0 and "extract" in r.stderr and "no picture" in r.stderr, r.stderr


@needs_ffmpeg
def test_music_under_the_narration_is_named(project):
    # Requirement: a narration recorded over music (or a loud steady background) gets a warning: the bed would sit
    # under every word of the video, and music goes in at mastering. A clean recording gets none.
    voice_project(project, bed=0.08)
    r = run_script("cut.py", "edit/v1", "--dry-run", cwd=project)
    assert "background" in r.stderr, r.stderr
    voice_project(project)
    r = run_script("cut.py", "edit/v1", "--dry-run", cwd=project)
    assert "background" not in r.stderr, r.stderr


# --- the plan of a "scenes + voice" video ---

def voice_cut(project, dur=12.0):
    """What cut.py writes for a narration: voice.wav and captions.json with the words and the voice stamp."""
    e = project / "edit" / "v1"
    e.mkdir(parents=True, exist_ok=True)
    ffmpeg("-f", "lavfi", "-i", f"sine=f=300:d={dur}:sample_rate=48000", "-ac", "2", "-c:a", "pcm_s16le", e / "voice.wav")
    lines = [("Most resumes look the same", 0.3), ("Here is how we read them", 3.2), ("Three checks in one call", 6.4),
             ("Save this for your next hire", 9.4)]
    words = []
    for k, (line, t) in enumerate(lines):
        for w in line.split():
            words.append({"text": w, "start": round(t, 3), "end": round(t + 0.3, 3), "seg": 0, "src": round(t, 3)})
            t += 0.35
    write_json(e / "captions.json", {"duration": dur, "segments": [{"i": 0, "source": "main", "src_start": 0.0,
                                                                     "src_end": dur, "out_start": 0.0, "out_dur": dur}],
                                     "words": words, "voice": {"file": "voice.wav", "sha1": "x", "stamp": {"fps": 30}}})
    write_json(project / "brands" / "acme" / "brand.json",
               {"name": "Acme", "slug": "acme", "schema": 2, "tone": {"preset": "expert", "overrides": {}},
                "colors": {"bg": "#0B3D2E", "accent": "#F2C14E", "text": "#FFFFFF"}})
    write_json(e / "reel.json", {"brand": "acme", "use_scenes": True})
    return e


def plan_of(e):
    return json.loads((e / "visual_plan.json").read_text(encoding="utf-8"))


def add(project, *args, check=True):
    return run_script("visual_plan.py", "add", "edit/v1", "--kind", "scene", *args, cwd=project, check=check)


@needs_ffmpeg
def test_init_scenes_voice_takes_the_length_and_words_of_the_narration(project):
    # Requirement: init --scenes-voice builds a plan on the narration's cut: its length (not the 15-25 s of a promo),
    # its phrases (scenes land on spoken words), the format named in the plan and in visual_plan.md. A plain init on a
    # narration, or --scenes-voice on a cut with a picture, says which one to use.
    e = voice_cut(project, dur=40.0)
    r = run_script("visual_plan.py", "init", "edit/v1", cwd=project, check=False)
    assert r.returncode != 0 and "--scenes-voice" in r.stderr, r.stdout + r.stderr
    r = run_script("visual_plan.py", "init", "edit/v1", "--scenes-voice", cwd=project)
    plan = plan_of(e)
    assert plan["format"] == "scenes-voice" and plan["duration"] == 40.0 and plan["segments"]
    assert "outside" not in r.stderr  # no 15-25 s limit
    # the sound mode of the video is the narration off camera (reel.json -> voice), the plan's format is its picture
    assert json.loads((e / "reel.json").read_text(encoding="utf-8"))["voice"] == "off_camera"
    add(project, "--type", "hook", "--variant", "slam", "--at", "word:Most#1", "--dur", "2.6", "--lines", "Resumes",
        "look the same", "--source", "speech", "--what", "the hook", "--why", "the narration's first line")
    sc = plan_of(e)["inserts"][0]
    assert sc["mode"] == "full" and sc["start"] == 0.3 and not sc["hide_subtitles"]
    run_script("visual_plan.py", "md", "edit/v1", cwd=project)
    assert "scenes + recorded voice" in (e / "visual_plan.md").read_text(encoding="utf-8")
    # a narration over ~70 s does not fit a laptop's render: a warning
    voice_cut(project, dur=80.0)
    r = run_script("visual_plan.py", "init", "edit/v1", "--scenes-voice", "--force", cwd=project)
    assert "70" in r.stderr, r.stderr
    # a cut with a picture (final.mp4, no voice stamp) is not a narration
    e2 = project / "edit" / "4821"
    write_json(e2 / "captions.json", {"duration": 10.0, "segments": [], "words": []})
    r = run_script("visual_plan.py", "init", "edit/4821", "--scenes-voice", cwd=project, check=False)
    assert r.returncode != 0 and "cut.py" in r.stderr, r.stderr


@needs_ffmpeg
def test_stage_puts_the_voice_and_its_subtitles_into_the_props(project):
    # Requirement: the props of a "scenes + voice" video carry the narration (a file in public/ the kit plays) and the
    # real words; the subtitles stay on, including over full scenes, unless a scene sets hide_subtitles.
    e = voice_cut(project)
    run_script("visual_plan.py", "init", "edit/v1", "--scenes-voice", cwd=project)
    add(project, "--type", "hook", "--variant", "slam", "--at", "word:Most#1", "--dur", "2.6", "--lines", "Resumes",
        "look the same", "--source", "speech", "--what", "the hook", "--why", "the narration's first line")
    add(project, "--type", "quote", "--at", "word:Three#1", "--dur", "2.8", "--lines", "Three checks in one call",
        "--source", "speech", "--hide-subtitles", "--what", "the quote", "--why", "the method in one line")
    r = run_script("visual_plan.py", "validate", "edit/v1", cwd=project, check=False)
    assert r.returncode == 0, r.stdout
    rem = project / "reels"
    (rem / "src").mkdir(parents=True)
    write_json(rem / "package.json", {"name": "reels"})
    run_script("brand.py", "stage", "acme", "--remotion", rem, cwd=project)
    run_script("visual_plan.py", "stage", "edit/v1", "--remotion", rem, "--props", rem / "props.json", cwd=project)
    props = json.loads((rem / "props.json").read_text(encoding="utf-8"))
    assert props["video"] == "" and props["voice"] == "v1/voice.wav" and props["voiceMode"] == "off_camera"
    assert (rem / "public" / "v1" / "voice.wav").read_bytes() == (e / "voice.wav").read_bytes()
    assert props["captions"]["words"] and props["captions"]["duration"] == 12.0
    assert props["subtitles"] != "none"
    hook, quote = props["scenes"]
    assert hook["mode"] == "full" and hook["hide_subtitles"] is False
    assert quote["hide_subtitles"] is True
    assert props["hideSubtitles"] == [[quote["start"], round(quote["start"] + quote["dur"], 3)]]
    assert plan_of(e)["subtitles_band"][0] == props["subtitlesTop"]
    # Codex review: the copy in public/ followed size and time only; a narration cut again to the same length (same
    # size) within a second kept the old voice under the new captions
    old = (e / "voice.wav").stat()
    ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=12:sample_rate=48000", "-ac", "2", "-c:a", "pcm_s16le", e / "voice2.wav")
    os.replace(e / "voice2.wav", e / "voice.wav")
    os.utime(e / "voice.wav", ns=(old.st_atime_ns, old.st_mtime_ns))
    assert (e / "voice.wav").stat().st_size == old.st_size
    run_script("visual_plan.py", "stage", "edit/v1", "--remotion", rem, "--props", rem / "props.json", cwd=project)
    assert (rem / "public" / "v1" / "voice.wav").read_bytes() == (e / "voice.wav").read_bytes()


@needs_ffmpeg
def test_validate_keeps_scene_text_off_the_subtitle_band_and_counts_scenes_as_the_picture(project):
    # Requirement: the narration's subtitles stay on over full scenes, so a scene box that reaches the subtitle band is
    # an error (unless that scene hides the subtitles); full scenes are the picture of this format, so they don't count
    # against the inserts' coverage or the brand tone's full-scene ceiling.
    e = voice_cut(project)
    run_script("visual_plan.py", "init", "edit/v1", "--scenes-voice", cwd=project)
    add(project, "--type", "hook", "--variant", "slam", "--at", "word:Most#1", "--dur", "2.8", "--lines", "Resumes",
        "look the same", "--source", "speech", "--what", "the hook", "--why", "the narration's first line")
    add(project, "--type", "list", "--at", "word:Here#1", "--dur", "3.0", "--lines", "How we read them",
        "--items-json", json.dumps([{"text": "The call", "t": 3.6}, {"text": "The task", "t": 4.4}]),
        "--source", "speech", "--what", "two steps", "--why", "the method step by step")
    add(project, "--type", "stat", "--at", "word:Three#1", "--dur", "2.8", "--lines", "checks in one call",
        "--value-json", '{"to": 3}', "--source", "speech", "--what", "the number", "--why", "the method's size")
    add(project, "--type", "cta", "--at", "word:Save#1", "--dur", "2.6", "--lines", "Save this", "--source", "agent",
        "--what", "the ask", "--why", "the call to action")
    r = run_script("visual_plan.py", "validate", "edit/v1", cwd=project, check=False)
    assert r.returncode == 0, r.stdout
    assert "inserts take" not in r.stdout and "full scenes 4 >" not in r.stdout, r.stdout
    plan = plan_of(e)
    plan["inserts"][1]["box"] = [60, 900, 900, 500]  # down to y 1400: over the subtitles
    write_json(e / "visual_plan.json", plan)
    r = run_script("visual_plan.py", "validate", "edit/v1", cwd=project, check=False)
    assert r.returncode == 1 and "c02" in r.stdout and "subtitle band" in r.stdout, r.stdout
    # Codex review: the text ends 40 px above the subtitles (band from y 1290 before a stage): a box down to y 1270
    # touches no subtitle but breaks the gap, and a box under the subtitles is outside the scene's zone
    for box in ([60, 250, 900, 1020], [60, 1460, 900, 30]):
        plan = plan_of(e)
        plan["inserts"][1]["box"] = box
        write_json(e / "visual_plan.json", plan)
        r = run_script("visual_plan.py", "validate", "edit/v1", cwd=project, check=False)
        assert r.returncode == 1 and "c02" in r.stdout and "subtitle band" in r.stdout, (box, r.stdout)
    plan = plan_of(e)
    plan["inserts"][1]["box"] = [60, 250, 900, 1000]  # ends at y 1250: allowed
    write_json(e / "visual_plan.json", plan)
    assert "subtitle band" not in run_script("visual_plan.py", "validate", "edit/v1", cwd=project, check=False).stdout
    plan = plan_of(e)
    plan["inserts"][1]["box"] = [60, 900, 900, 500]
    plan["inserts"][1]["hide_subtitles"] = True
    write_json(e / "visual_plan.json", plan)
    r = run_script("visual_plan.py", "validate", "edit/v1", cwd=project, check=False)
    assert "subtitle band" not in r.stdout, r.stdout
    # the picture is scenes over a narration: the voice can't be on camera
    run_script("reelcfg.py", "save", "edit/v1", "--set", "voice=on_camera", cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/v1", cwd=project, check=False)
    assert r.returncode == 1 and "voice=off_camera" in r.stdout, r.stdout
    r = run_script("reelcfg.py", "save", "edit/v1", "--set", "voice=offcamera", cwd=project, check=False)
    assert r.returncode != 0 and "on_camera" in r.stderr, r.stderr


def test_the_kit_plays_the_voice_and_keeps_full_scene_text_where_validate_expects_it():
    # Requirement: the kit plays props.voice, keeps the subtitles over full scenes with voiceMode off_camera, and ends a
    # full scene's text at the same y the plan check assumes (one gap in both, the same default zone)
    import re
    from conftest import CORE
    import vp_scenes
    kit = CORE.parent / "assets" / "remotion-kit"
    reel = (kit / "ReelKit.tsx").read_text(encoding="utf-8")
    layer = (kit / "kit" / "scenes" / "SceneLayer.tsx").read_text(encoding="utf-8")
    assert "<Html5Audio src={staticFile(p.voice)}" in reel
    frame = reel[reel.index("const ReelKitFrame"):reel.index("export const reelKitDefaults")]
    assert "<Voice p={p} />" in frame  # Codex review: the component alone, never mounted, passed the check
    # Codex review: with the voice off camera the typewriter darkening goes over the full scene's field, not under it
    assert "offCamera ? shadeLayer : null" in frame and frame.index("<SceneLayer") < frame.index("offCamera ? shadeLayer : null")
    assert "sceneHideIntervals(p.scenes, offCamera)" in reel
    gap = re.search(r"export const VOICE_SUB_GAP = (\d+);", reel)
    assert gap and int(gap.group(1)) == vp_scenes.VOICE_SUB_GAP
    assert "offCamera ? s.hide_subtitles === true" in layer
    # the zone ends at the lowest bound of the scene: the subtitles' (textBottom) or the mascot's (mascotTop)
    assert "const subs = textBottom != null && !s.hide_subtitles ? textBottom : null;" in layer
    assert "{ x: 60, y: 250, w: 900, h: Math.max(1, Math.min(1200, (bottom ?? 0) - 250)) }" in layer
    assert vp_scenes.voice_stage([1290, 1458]) == [60, 250, 900, 1290 - vp_scenes.VOICE_SUB_GAP - 250]


def test_a_sound_only_source_is_a_source_file_for_the_notes():
    # Requirement: structure.py's history and notes see a narration file (voice.m4a) as a source, as they see IMG_1.MOV
    import reels_common
    import structure
    assert {".m4a", ".wav", ".mp3", ".ogg", ".opus"} <= reels_common.AUDIO_EXT
    assert structure.names_file("the take from voice.m4a was better", "voice")


@needs_ffmpeg
def test_a_scenes_voice_render_without_its_voice_is_not_mastered(project):
    # Requirement: a "scenes + voice" render is mastered like any video with a voice (-14 LUFS, no "no voice" tag);
    # a render of that video with no voice (the narration did not reach it) is refused, never passed as a silent
    # promo.
    e = project / "edit" / "v1"
    write_json(e / "visual_plan.json", {"id": "v1", "format": "scenes-voice", "duration": 6.0, "inserts": []})
    make_video(project / "silent.mp4", 360, 640, 6.0, audio=False)
    r = run_script("master_audio.py", "silent.mp4", "-o", "master.mp4", "--edit", e, cwd=project, check=False)
    assert r.returncode != 0 and "voice" in (r.stdout + r.stderr) and not (project / "master.mp4").exists(), r.stdout
    import master_audio
    make_video(project / "render.mp4", 360, 640, 6.0)
    r = run_script("master_audio.py", "render.mp4", "-o", "master.mp4", "--edit", e, cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert master_audio.master_tag(str(project / "master.mp4")) is None
    r = run_script("master_audio.py", "master.mp4", "--check", cwd=project, check=False)
    assert r.returncode == 0 and "does not apply" not in r.stdout, r.stdout
