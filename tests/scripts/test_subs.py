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
