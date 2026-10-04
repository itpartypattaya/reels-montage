"""addon.py transcribe: the cloud's text laid onto the local word times (or whisper-1's own times). No network: the
request function is replaced by canned answers, and every failure path is checked for the key leaking out."""
import io
import json
import urllib.error

import pytest

from conftest import ADDON, needs_ffmpeg
from test_transcribe import late_audio_video

KEY = "sk-test-secret-value-0123456789"
TEXT = "Привет, мир. Чем конкретнее — тем лучше! Сколько?"
LOCAL = [("Привет", 1.1, 1.4), ("мир", 1.45, 1.7), ("Чем", 1.9, 2.05), ("конкретно", 2.05, 2.5), ("тем", 2.6, 2.7),
         ("лучше", 2.7, 2.95)]
WHISPER = {"task": "transcribe", "language": "russian", "duration": 3.0, "text": TEXT,
           "words": [{"word": w, "start": s, "end": e} for w, s, e in LOCAL]}


@pytest.fixture
def online(project, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ADDON))
    import reels_online
    import transcribe_online
    monkeypatch.setattr(reels_online, "KEYS_FILE", tmp_path / "cfg" / "keys.env")
    monkeypatch.setattr(reels_online, "_KEYS", None)
    for n in reels_online.known_keys():
        monkeypatch.delenv(n, raising=False)
    monkeypatch.delenv("REELS_OFFLINE", raising=False)
    return transcribe_online


def run(mod, *args):
    with pytest.raises(SystemExit) as ex:
        mod.main(["edit/4821", "IMG_4821.MOV", "--provider", "openai", *args])
    return ex.value.code


def words(rows):
    return [{"text": w, "start": s, "end": e, "type": "word"} for w, s, e in rows]


def local_transcript(project, rows=LOCAL):
    """The core's local transcript of IMG_4821.MOV, as transcribe.py would have written it."""
    src = project / "IMG_4821.MOV"
    ident = {"path": str(src.resolve()), "size": src.stat().st_size, "mtime_ns": src.stat().st_mtime_ns}
    f = project / "edit" / "4821" / "transcripts" / "IMG_4821.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"language_code": "ru", "words": words(rows), "source_identity": ident,
                             "model": "faster-whisper medium int8"}, ensure_ascii=False), encoding="utf-8")
    return f


def test_text_without_spaces_is_laid_by_characters(online):
    # Codex review: a Chinese phrase has no spaces, so the whole cloud text was taken for one word
    out, rep = online.lay_text(words([("你好", 1.0, 1.4), ("世姐", 1.4, 1.9)]), "你好世界。")
    assert [(w["text"], w["start"]) for w in out] == [("你好", 1.0), ("世界。", 1.4)]
    assert out[1]["local"] == "世姐" and rep["fixed"] == [(1.4, "世姐", "世界。")] and rep["same"] == 1


def test_hyphenated_word_is_not_doubled(online):
    # IMG_0135 (04.10): the cloud wrote "не-не-не." as one word, the local model "не" "-не" "-не."; the tails stayed as
    # "local only" and the subtitles read "не-не-не. -не -не."
    import transcribe as core
    local = core.join_hyphen_parts(words([("HR,", 10.86, 11.32), ("не", 11.44, 11.74), ("-не", 11.74, 11.98),
                                          ("-не.", 11.98, 12.26), ("Это", 12.42, 12.64)]))
    assert [(w["text"], w["start"], w["end"]) for w in local][1] == ("не-не-не.", 11.44, 12.26)
    out, rep = online.lay_text(local, "HR, не-не-не. Это")
    assert [w["text"] for w in out] == ["HR,", "не-не-не.", "Это"] and not rep["local_only"]


def test_cloud_text_on_local_times(online):
    out, rep = online.lay_text(words(LOCAL), TEXT)
    assert [w["text"] for w in out] == ["Привет,", "мир.", "Чем", "конкретнее", "тем", "лучше!", "Сколько?"]
    assert out[3]["local"] == "конкретно" and (out[3]["start"], out[3]["end"]) == (2.05, 2.5)  # corrected, local time
    assert out[6].get("est") and out[6]["start"] >= out[5]["start"]  # only the cloud heard it: time estimated
    assert rep["same"] == 5 and len(rep["fixed"]) == 1 and len(rep["added"]) == 1
    # a repeat only the local model kept (a retake the cloud tidied away) stays, and is listed to listen to
    rows = LOCAL[:2] + [("Чем", 1.75, 1.85)] + LOCAL[2:]
    out, rep = online.lay_text(words(rows), TEXT)
    assert len(out) == 8 and rep["local_only"] and rep["local_only"][0][1] == "Чем"
    starts = [w["start"] for w in out]
    assert starts == sorted(starts)
    # a word heard as a completely different one between matching neighbours is replaced, not doubled
    out, rep = online.lay_text(words([("I", 0.1, 0.2), ("have", 0.25, 0.4), ("four", 0.45, 0.7), ("apples", 0.75, 1.1)]),
                               "I have five apples.")
    assert [w["text"] for w in out] == ["I", "have", "five", "apples."] and out[2]["start"] == 0.45
    assert rep["fixed"] == [(0.45, "four", "five")] and not rep["added"] and not rep["local_only"]


@needs_ffmpeg
def test_hybrid_run_keeps_local_times_and_files(online, project, monkeypatch, capsys):
    late_audio_video(project / "IMG_4821.MOV")
    local = local_transcript(project)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    sent = []

    def fake(wav, key, model, language=None, prompt=None, words=False):
        sent.append((wav.name, key, model, words))
        return {"text": TEXT, "usage": {"type": "duration", "seconds": 3}}
    monkeypatch.setattr(online, "openai_call", fake)

    assert run(online) == 0 and not sent  # paid: without --yes only the price
    assert "--yes" in capsys.readouterr().out
    assert run(online, "--yes") == 0
    assert sent == [("audio16k-IMG_4821.wav", KEY, "gpt-transcribe", False)]  # the aligned WAV, the text model
    doc = json.loads(local.read_text(encoding="utf-8"))
    assert doc["model"] == "openai gpt-transcribe text + faster-whisper timing" and doc["timeline"] == "video"
    assert [w["text"] for w in doc["words"]][:4] == ["Привет,", "мир.", "Чем", "конкретнее"]
    assert doc["words"][3]["start"] == 2.05 and doc["audio_offset"] > 0.05
    keep = local.parent / "IMG_4821.local.json"
    assert json.loads(keep.read_text(encoding="utf-8"))["model"].startswith("faster-whisper")
    assert (local.parent / "IMG_4821.openai.raw.json").is_file()
    import transcribe
    assert not [p for p in transcribe.check_doc(doc) if not p.startswith("note:")]
    out = capsys.readouterr().out
    assert "конкретно → конкретнее" in out and "+ Сколько?" in out and KEY not in out
    assert run(online, "--yes") == 0 and len(sent) == 1 and "cached" in capsys.readouterr().out
    assert run(online, "--yes", "--force") == 0 and len(sent) == 2  # again: the local skeleton comes from .local.json


@needs_ffmpeg
def test_cloud_word_times_without_a_local_model(online, project, monkeypatch):
    late_audio_video(project / "IMG_4821.MOV")
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setattr(online, "openai_call", lambda wav, key, model, language=None, prompt=None, words=False:
                        WHISPER if (model, words) == ("whisper-1", True) else pytest.fail("whisper-1 with word times"))
    assert run(online, "--yes", "--words", "cloud") == 0
    doc = json.loads((project / "edit" / "4821" / "transcripts" / "IMG_4821.json").read_text(encoding="utf-8"))
    assert doc["model"] == "openai whisper-1" and doc["language_code"] == "ru"
    assert [w["text"] for w in doc["words"]][:2] == ["Привет,", "мир."]


@needs_ffmpeg
def test_no_local_model_asks_again_for_the_dearer_word_times(online, project, monkeypatch, capsys):
    late_audio_video(project / "IMG_4821.MOV")
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setattr(online.core, "cmd_full", lambda a: (_ for _ in ()).throw(SystemExit("faster-whisper is not installed")))
    monkeypatch.setattr(online, "openai_call", lambda *a, **k: pytest.fail("nothing is sent at a price not agreed"))
    assert run(online, "--yes") == 2
    out = capsys.readouterr().out
    assert "whisper-1" in out and "--words cloud --yes" in out and "nothing was sent" in out
    # a local transcript with no words is no skeleton either: no made-up times from zero
    local_transcript(project, rows=[])  # found as the local transcript: the local model is not run
    assert run(online, "--yes") == 2 and "--words cloud --yes" in capsys.readouterr().out


@needs_ffmpeg
def test_the_project_setting_is_the_standing_choice(online, project, monkeypatch):
    late_audio_video(project / "IMG_4821.MOV")
    local_transcript(project)
    (project / "reel-defaults.json").write_text(json.dumps({"settings": {"transcription_provider": "openai"}}),
                                                encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setattr(online, "openai_call", lambda *a, **k: {"text": TEXT})
    with pytest.raises(SystemExit) as ex:
        online.main(["edit/4821", "IMG_4821.MOV"])  # no --provider, no --yes: the person's setting
    assert ex.value.code == 0
    doc = json.loads((project / "edit" / "4821" / "transcripts" / "IMG_4821.json").read_text(encoding="utf-8"))
    assert doc["model"].startswith("openai gpt-transcribe")


@needs_ffmpeg
def test_no_key_offline_and_refusals_keep_the_local_transcript(online, project, monkeypatch, capsys):
    late_audio_video(project / "IMG_4821.MOV")
    local = local_transcript(project)
    before = local.read_text(encoding="utf-8")
    assert run(online, "--yes") == 2  # no key
    err = capsys.readouterr().err
    assert "keys set OPENAI_API_KEY" in err and "transcribe.py" in err
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("REELS_OFFLINE", "1")
    assert run(online, "--yes") == 2 and "REELS_OFFLINE" in capsys.readouterr().err
    monkeypatch.delenv("REELS_OFFLINE")

    def refused(req, timeout, allowed=None):
        assert req.full_url.startswith("https://api.openai.com/") and allowed(req.full_url)
        body = json.dumps({"error": {"message": f"Incorrect API key provided: {KEY}", "code": "invalid_api_key"}})
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(body.encode()))
    monkeypatch.setattr(online, "open_url", refused)
    assert run(online, "--yes") == 2
    err = capsys.readouterr().err
    assert "HTTP 401" in err and "invalid_api_key" in err and KEY not in err
    assert json.loads(local.read_text(encoding="utf-8"))["words"] == json.loads(before)["words"]  # nothing lost


@needs_ffmpeg
def test_runner_knows_the_command(project, tmp_path):
    from conftest import run_script
    env = {"REELS_OFFLINE": "1", "REELS_KEYS_FILE": str(tmp_path / "k.env")}
    run_script("reels_online.py", "link", "--project", project, cwd=project, env=env, scripts=ADDON)
    assert "transcribe" in run_script("addon.py", cwd=project, env=env).stdout
    late_audio_video(project / "IMG_4821.MOV")
    r = run_script("addon.py", "transcribe", "edit/4821", "IMG_4821.MOV", "--provider", "openai", "--price",
                   cwd=project, env=env)
    assert "gpt-transcribe" in r.stdout and "≈ $0.000" in r.stdout


@needs_ffmpeg
def test_a_long_word_note_is_printed_once(online, project, monkeypatch, capsys):
    # T1: "N word(s) longer than 1 s" came twice: from the core's local run and again for the merged transcript
    from conftest import ROOT
    monkeypatch.syspath_prepend(str(ROOT / "tests" / "scripts" / "stubs"))  # faster-whisper: "Hello big world."
    late_audio_video(project / "IMG_4821.MOV")
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setattr(online, "openai_call", lambda wav, key, model, language=None, prompt=None, words=False:
                        {"text": "Hello big world.", "usage": {"type": "duration", "seconds": 3}})
    assert run(online, "--yes", "--language", "en") == 0
    err = capsys.readouterr().err
    assert err.count("longer than 1 s") == 1, err


def test_cloud_words_before_the_first_local_word_get_a_real_time(online):
    # T2: the cloud heard a short phrase at the very start that the local model did not, and the local model put its
    # first word at 0.00: the cloud words got 0.00-0.00 (zero length at the very start)
    out, rep = online.lay_text(words([("вы", 0.0, 0.32), ("сказали", 0.32, 0.8)]), "Я знаю, вы сказали")
    assert [w["text"] for w in out] == ["Я", "знаю,", "вы", "сказали"]
    lead = out[:2]
    assert all(w.get("est") and w["end"] - w["start"] >= 0.06 for w in lead), lead
    assert lead[0]["start"] >= 0.0 and lead[1]["end"] <= out[2]["start"] < out[2]["end"]
    assert not out[2].get("est") and out[3]["start"] == 0.32  # the matched words keep the local times otherwise
    # with room before the first word: just before it, short
    out, _ = online.lay_text(words([("вы", 1.5, 1.8), ("сказали", 1.8, 2.3)]), "Я знаю, вы сказали")
    assert out[0]["start"] == 0.9 and out[1]["end"] == 1.5 and out[2]["start"] == 1.5
