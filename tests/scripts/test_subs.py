"""subs.py: phrases to translate, the translation checked and laid onto the phrase times, .srt files; the export
takes captions-<lang>.json when reel.json asks for it, and refuses a translation of an older rough cut."""
import json

import pytest

from conftest import run_script, write_json
from test_plan import captions, plan_project

EN_TO_DE = {
    "So today we talk about hiring": "Heute geht es ums Einstellen",
    "First, we check the resume": "Zuerst prüfen wir den Lebenslauf",
    "She said: test how they think, not what they remember": "Sie sagte: prüft, wie sie denken, nicht was sie wissen",
    "Two out of three candidates fail this step": "Zwei von drei Kandidaten scheitern hier",
    "Remember this: speed wins": "Merkt euch: Tempo gewinnt",
    "Subscribe and save this video": "Abonniert und speichert das Video",
}


def translate(e, table=EN_TO_DE):
    f = e / "subs" / "de.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    for p in doc["phrases"]:
        p["text"] = table.get(p["src"], p["text"])
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


def test_phrases_apply_and_srt(project):
    e = plan_project(project)
    r = run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    assert "6 phrase(s)" in r.stdout and "to translate 6" in r.stdout  # one per cut segment
    r = run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project, check=False)
    assert r.returncode != 0 and "p001 is not translated" in r.stdout
    doc = translate(e)
    run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project)
    de = json.loads((e / "captions-de.json").read_text(encoding="utf-8"))
    assert de["language"] == "de" and de["duration"] == 30.0
    first = [w for w in de["words"] if w["seg"] == 0]
    assert [w["text"] for w in first] == "Heute geht es ums Einstellen".split()
    p = doc["phrases"][0]
    assert first[0]["start"] == p["start"] and abs(first[-1]["end"] - p["end"]) < 0.01  # the phrase's own time
    starts = [w["start"] for w in de["words"]]
    assert starts == sorted(starts)
    run_script("subs.py", "srt", "edit/4821", "--lang", "de", cwd=project)
    srt = (e / "subtitles.de.srt").read_text(encoding="utf-8")
    assert srt.startswith("1\n00:00:00,200 --> ") and "Heute geht es ums Einstellen" in srt
    assert "Sie sagte: prüft, wie sie denken,\nnicht was sie wissen" in srt  # two even lines of <= 42
    run_script("subs.py", "srt", "edit/4821", cwd=project)
    assert "So today we talk about hiring" in (e / "subtitles.srt").read_text(encoding="utf-8")


def test_recut_keeps_unchanged_translations_and_export_refuses_a_stale_one(project, monkeypatch):
    e = plan_project(project, {"subtitles_lang": "de"})
    run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    translate(e)
    run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project)
    import visual_plan
    assert visual_plan.subtitles_in(e, "de")["language"] == "de"
    cap = captions()  # a re-cut: one word of the 4th phrase changed
    for w in cap["words"]:
        if w["text"] == "fail":
            w["text"] = "drop"
    write_json(e / "captions.json", cap)
    with pytest.raises(SystemExit, match="rough cut changed"):
        visual_plan.subtitles_in(e, "de")
    r = run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    assert "translated already 5, to translate 1" in r.stdout and "Two out of three candidates drop" in r.stdout


def test_reading_speed(project):
    e = plan_project(project)
    run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    long = dict(EN_TO_DE)
    long["Remember this: speed wins"] = "Merkt euch das bitte ganz genau, denn am Ende gewinnt immer die Geschwindigkeit"
    translate(e, long)
    r = run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project, check=False)
    assert r.returncode != 0 and "characters per second" in r.stdout and "shorten" in r.stdout
    long["Remember this: speed wins"] = "Merkt euch gut: Tempo gewinnt immer"
    translate(e, long)
    r = run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project)
    assert "characters per second" in r.stderr  # a warning only


def test_bad_language_code(project):
    plan_project(project)
    r = run_script("subs.py", "phrases", "edit/4821", "--lang", "../x", cwd=project, check=False)
    assert r.returncode != 0 and "language code" in r.stderr


def test_a_recut_of_timing_only_takes_the_new_times_and_length(project):
    # review: the fingerprint saw only the words, so a new length or segment timeline kept an old captions-<lang>.json
    e = plan_project(project, {"subtitles_lang": "de"})
    run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    translate(e)
    run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project)
    import visual_plan
    cap = captions()
    cap["duration"] = 31.5  # only the length changed
    write_json(e / "captions.json", cap)
    with pytest.raises(SystemExit, match="rough cut changed"):
        visual_plan.subtitles_in(e, "de")
    for w in cap["words"]:  # and every word 0.5 s later, the same words
        w["start"], w["end"] = round(w["start"] + 0.5, 3), round(w["end"] + 0.5, 3)
    write_json(e / "captions.json", cap)
    run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project)  # no new translation needed
    de = json.loads((e / "captions-de.json").read_text(encoding="utf-8"))
    assert de["duration"] == 31.5 and de["words"][0]["start"] == 0.7  # the current times, not the old phrase file's
    assert visual_plan.subtitles_in(e, "de")["duration"] == 31.5


def test_scripts_without_spaces_need_word_marks(project):
    e = plan_project(project)
    run_script("subs.py", "phrases", "edit/4821", "--lang", "zh", cwd=project)
    zh = {src: "好" for src in EN_TO_DE}
    zh["So today we talk about hiring"] = "我们今天来聊聊招聘这件事情吧"
    f = e / "subs" / "zh.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    for p in doc["phrases"]:
        p["text"] = zh[p["src"]]
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    r = run_script("subs.py", "apply", "edit/4821", "--lang", "zh", cwd=project, check=False)
    assert r.returncode != 0 and "mark the word boundaries with |" in r.stdout
    doc["phrases"][0]["text"] = "我们|今天|来|聊聊|招聘|这件|事情|吧"
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    run_script("subs.py", "apply", "edit/4821", "--lang", "zh", cwd=project)
    words = json.loads((e / "captions-zh.json").read_text(encoding="utf-8"))["words"]
    first = [w for w in words if w["seg"] == 0]
    assert [w["text"] for w in first][:3] == ["我们", "今天", "来"] and len(first) == 8
    assert "glue" not in first[0] and all(w.get("glue") for w in first[1:])  # shown without spaces between them
    run_script("subs.py", "srt", "edit/4821", "--lang", "zh", cwd=project)
    assert "我们今天来聊聊招聘这件事情吧" in (e / "subtitles.zh.srt").read_text(encoding="utf-8")
