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
