"""transcribe.py with a stand-in faster-whisper (tests/scripts/stubs): format, cache, snip offsets, format check."""
import json
from pathlib import Path

from conftest import make_video, needs_ffmpeg, run_script, write_json

STUBS = {"PYTHONPATH": str(Path(__file__).resolve().parent / "stubs")}


@needs_ffmpeg
def test_transcript_format_and_cache(project):
    make_video(project / "IMG_4821.MOV", 360, 640, 4.0)
    r = run_script("transcribe.py", "edit/4821", "IMG_4821.MOV", cwd=project, env=STUBS)
    doc = json.loads((project / "edit" / "4821" / "transcripts" / "IMG_4821.json").read_text(encoding="utf-8"))
    assert [w["text"] for w in doc["words"]] == ["Hello", "big", "world."]
    assert doc["words"][0] == {"text": "Hello", "start": 0.5, "end": 0.9, "type": "word", "p": 0.98}
    assert (project / "edit" / "4821" / "audio16k-IMG_4821.wav").is_file()
    assert "merged retake" in r.stderr  # the stretched word is flagged
    r = run_script("transcribe.py", "edit/4821", "IMG_4821.MOV", cwd=project, env=STUBS)
    assert r.stdout.startswith("cached")


@needs_ffmpeg
def test_snip_times_are_on_the_source_timeline(project):
    make_video(project / "IMG_4821.MOV", 360, 640, 8.0)
    run_script("transcribe.py", "snip", "edit/4821", "IMG_4821.MOV", "--from", "3.0", "--to", "6.0", cwd=project, env=STUBS)
    doc = json.loads((project / "edit" / "4821" / "snip" / "IMG_4821_3.00-6.00.json").read_text(encoding="utf-8"))
    assert doc["words"][0]["start"] == 3.5


@needs_ffmpeg
def test_snip_prompt_is_in_the_transcript_language(project):
    # T5: an English "verbatim" prompt with --language ru came back as "Verbatim, 1 000 EUR" instead of the Russian
    # words. The prompt is now in the language of the piece (--language, else the cached transcript's), or none
    import transcribe
    make_video(project / "IMG_4821.MOV", 360, 640, 8.0)
    write_json(project / "edit" / "4821" / "transcripts" / "IMG_4821.json", {"language_code": "ru", "words": []})

    def snip(*extra):
        run_script("transcribe.py", "snip", "edit/4821", "IMG_4821.MOV", "--from", "3.0", "--to", "6.0", *extra,
                   cwd=project, env=STUBS)
        return json.loads((project / "edit" / "4821" / "snip" / "IMG_4821_3.00-6.00.json").read_text(encoding="utf-8"))
    doc = snip()
    assert doc["language_code"] == "ru" and doc["prompt"] == transcribe.snip_prompt("ru")
    assert doc["prompt"].startswith("Ну") and not any("a" <= ch.lower() <= "z" for ch in doc["prompt"])
    assert snip("--language", "en")["prompt"] == transcribe.snip_prompt("en")
    assert snip("--language", "de")["prompt"] is None  # no sample for German: no prompt rather than an English one
    assert snip("--no-prompt")["prompt"] is None
    assert transcribe.snip_prompt("en-US") == transcribe.snip_prompt("en") and transcribe.snip_prompt(None) is None


@needs_ffmpeg
def test_missing_model_is_not_downloaded(project):
    make_video(project / "IMG_4821.MOV", 360, 640, 2.0)
    r = run_script("transcribe.py", "edit/4821", "IMG_4821.MOV", "--model", "missing", cwd=project, env=STUBS, check=False)
    assert r.returncode != 0 and "download_model('missing')" in r.stderr


def test_check_catches_a_broken_transcript(project):
    good = write_json(project / "good.json", {"words": [{"text": "a", "start": 0.1, "end": 0.3, "type": "word"},
                                                       {"text": " ", "start": 0.3, "end": 0.4, "type": "spacing"},
                                                       {"text": "b", "start": 0.4, "end": 0.6}]})
    assert run_script("transcribe.py", "check", good, cwd=project).returncode == 0
    bad = write_json(project / "bad.json", {"words": [{"text": "a", "start": 2.0, "end": 1.0}, {"text": "b", "start": 0.1}]})
    r = run_script("transcribe.py", "check", bad, cwd=project, check=False)
    assert r.returncode == 1 and "end 1.0 before start 2.0" in r.stdout


def late_audio_video(path, lead=0.1):
    """A video whose audio track starts `lead` s after the picture (like a phone MOV); a tone burst at 1.0 s of the audio
    track, so at 1.0 + lead s of the video."""
    from conftest import ffmpeg
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=3", "-itsoffset", lead, "-f", "lavfi",
           "-i", "sine=f=440:d=3,volume='if(between(t,1,1.5),1,0)':eval=frame", "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path)
    return path


def onset(env, thr=-30.0):
    return next(k for k, v in enumerate(env) if v > thr) * 0.01


@needs_ffmpeg
def test_analysis_audio_is_on_the_video_timeline(project):
    # A phone MOV's audio started 0.1 s after the video: the extracted audio ran ahead, and every edge measured on it
    # landed 0.1 s early in cut.py (word endings clipped in every take). Now the WAV, the --edl check and snip agree.
    import speech_mask
    import transcribe
    from reels_common import audio_offset
    src = late_audio_video(project / "IMG_4821.MOV")
    assert 0.05 < audio_offset(src) < 0.11  # the container says 0.076 here: AAC encoder delay, hence first_pts in extraction
    wav = transcribe.extract_audio(src, project / "a.wav")
    assert abs(onset(speech_mask.load_env(str(wav))) - 1.1) <= 0.03
    assert abs(onset(speech_mask.load_env(str(src))) - 1.1) <= 0.03  # speech_mask --edl reads the source itself
    piece = transcribe.extract_audio(src, project / "p.wav", 0.5, 2.0)  # a snip: second 0 of the piece = 0.5 of the video
    assert abs(onset(speech_mask.load_env(str(piece))) + 0.5 - 1.1) <= 0.03


@needs_ffmpeg
def test_audio_command_gives_your_own_transcriber_the_aligned_wav(project):
    # A cloud transcriber that pulls the audio out of a phone MOV itself gets every word ~0.1 s early; `audio` makes
    # the WAV on the video timeline (no model needed), the same file full transcription and speech_mask.py use.
    import speech_mask
    src = late_audio_video(project / "IMG_4821.MOV")
    (project / "edit" / "4821").mkdir(parents=True)
    r = run_script("transcribe.py", "audio", "edit/4821", "IMG_4821.MOV", cwd=project)
    wav = project / "edit" / "4821" / "audio16k-IMG_4821.wav"
    assert wav.is_file() and "video timeline" in r.stdout and "transcripts" in r.stdout
    assert (project / "edit" / "4821" / "transcripts").is_dir()  # the advertised folder exists to save into
    assert abs(onset(speech_mask.load_env(str(wav))) - 1.1) <= 0.03
    stamp = json.loads(wav.with_suffix(".json").read_text(encoding="utf-8"))
    assert stamp["timeline"] == "video" and stamp["audio_offset"] > 0.05
    mtime = wav.stat().st_mtime_ns
    run_script("transcribe.py", "audio", "edit/4821", "IMG_4821.MOV", cwd=project)
    assert wav.stat().st_mtime_ns == mtime  # the same source: the WAV is not made again


def test_hyphen_parts_join_into_one_word():
    import transcribe  # conftest puts the core scripts on the path
    w = lambda t, s, e: {"text": t, "start": s, "end": e, "type": "word", "p": 0.9}
    out = transcribe.join_hyphen_parts([w("no", 1.0, 1.2), w("-no", 1.2, 1.4), w("-no.", 1.4, 1.6), w("Well", 1.9, 2.1),
                                        w("-", 2.15, 2.2), w("then", 2.25, 2.4), w("-ish", 3.0, 3.2)])
    assert [(x["text"], x["start"], x["end"]) for x in out] == [("no-no-no.", 1.0, 1.6), ("Well", 1.9, 2.1), ("-", 2.15, 2.2),
                                                                ("then", 2.25, 2.4), ("-ish", 3.0, 3.2)]


@needs_ffmpeg
def test_rate_counts_vowels_over_the_speech_of_the_cut(project):
    # T2: SKILL.md compared "syllables per second" of two cameras without defining it, and the agent wrote its own
    # script; rate measures it on the rough cut: vowels of the words / speech time by the speech mask, per source
    from conftest import ffmpeg, make_speech, write_json
    e = project / "edit" / "4821"
    make_speech(project / "speech.wav", [(0.2, 1.2), (2.2, 2.7)], 3.0)
    e.mkdir(parents=True)
    ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=180x320:r=30:d=3", "-i", project / "speech.wav", "-shortest",
           "-c:v", "libx264", "-c:a", "aac", e / "final.mp4")
    write_json(e / "captions.json", {"duration": 3.0, "segments": [
        {"i": 0, "source": "front", "out_start": 0.0, "out_dur": 2.0, "beat": "one"},
        {"i": 1, "source": "side", "out_start": 2.0, "out_dur": 1.0, "beat": "two"}], "words": [
        {"text": "banana", "start": 0.2, "end": 0.7, "seg": 0}, {"text": "papaya,", "start": 0.7, "end": 1.2, "seg": 0},
        {"text": "мама", "start": 2.2, "end": 2.7, "seg": 1}]})  # Cyrillic "mama": 2 vowels
    r = run_script("transcribe.py", "rate", "edit/4821", "--json", cwd=project)
    doc = json.loads(r.stdout.strip().splitlines()[-1])
    front, side = doc["sources"]["front"], doc["sources"]["side"]
    assert front["vowels"] == 6 and 0.95 <= front["speech_s"] <= 1.15 and 5.2 <= front["rate"] <= 6.3
    assert side["vowels"] == 2 and 0.45 <= side["speech_s"] <= 0.65
    only = run_script("transcribe.py", "rate", "edit/4821", "--source", "side", cwd=project)
    assert "side:" in only.stdout and "front:" not in only.stdout


@needs_ffmpeg
def test_rate_leaves_numbers_in_digits_out_of_vowels_and_time(project):
    # T5: "1", "270", "100", "26" counted as words with 0 vowels but with their time: a segment with a price read
    # 2.18 syllables/s at the video's usual pace. A number in digits is left out of both, and the output says so
    from conftest import ffmpeg, make_speech, write_json
    e = project / "edit" / "4821"
    make_speech(project / "speech.wav", [(0.2, 0.7), (0.8, 1.8)], 2.5)
    e.mkdir(parents=True)
    ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=180x320:r=30:d=2.5", "-i", project / "speech.wav", "-shortest",
           "-c:v", "libx264", "-c:a", "aac", e / "final.mp4")
    write_json(e / "captions.json", {"duration": 2.5, "segments": [
        {"i": 0, "source": "main", "out_start": 0.0, "out_dur": 2.5, "beat": "price"}], "words": [
        {"text": "мама", "start": 0.2, "end": 0.7, "seg": 0}, {"text": "1 270", "start": 0.8, "end": 1.8, "seg": 0}]})
    r = run_script("transcribe.py", "rate", "edit/4821", "--json", cwd=project)
    doc = json.loads(r.stdout.strip().splitlines()[-1])
    main = doc["sources"]["main"]
    assert main["vowels"] == 2 and main["numbers"] == 1 and 0.85 <= main["numbers_s"] <= 1.1
    assert 0.4 <= main["speech_s"] <= 0.65 and main["rate"] >= 3.0  # only "mama" over its own time
    assert doc["segments"][0]["numbers"] == ["1 270"] and "numbers in digits are left out" in r.stdout


def test_snip_language_as_faster_whisper_takes_it(tmp_path):
    # review: "rus" from another transcriber (or "en-US", or the online add-on's "swedish") went to faster-whisper as
    # is and stopped it with "not a valid language code"; main passed None (detect)
    import transcribe
    assert transcribe.whisper_language("rus") == "ru" and transcribe.whisper_language("en-US") == "en"
    assert transcribe.whisper_language("swedish") is None and transcribe.whisper_language(None) is None
    write_json(tmp_path / "transcripts" / "A.json", {"language_code": "eng", "words": []})
    assert transcribe.snip_language(None, tmp_path, "A.MOV") == "en"
    assert transcribe.snip_language("ru-RU", tmp_path, "A.MOV") == "ru"
