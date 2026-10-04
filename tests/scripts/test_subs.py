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


def test_repeated_phrases_keep_their_own_translations(project):
    # Codex review: two identical phrases translated differently collapsed into the last one on the next `phrases`
    e = plan_project(project)
    cap = captions()  # the first line said twice: segment 1 repeats segment 0
    s0 = [w for w in cap["words"] if w["seg"] == 0]
    dup = [{**w, "seg": 1, "start": round(w["start"] + 3.0, 3), "end": round(w["end"] + 3.0, 3)} for w in s0]
    cap["words"] = sorted([w for w in cap["words"] if w["seg"] != 1] + dup, key=lambda w: w["start"])
    write_json(e / "captions.json", cap)
    run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    f = e / "subs" / "de.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    assert doc["phrases"][0]["src"] == doc["phrases"][1]["src"]
    doc["phrases"][0]["text"], doc["phrases"][1]["text"] = "Los.", "Gehen."
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    doc = json.loads(f.read_text(encoding="utf-8"))
    assert [p["text"] for p in doc["phrases"][:2]] == ["Los.", "Gehen."]


def test_export_refuses_subtitles_of_a_changed_translation(project):
    # Codex review: after a refused apply the old captions-<lang>.json was still taken by the export
    e = plan_project(project)
    run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    translate(e)
    run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project)
    import visual_plan
    assert visual_plan.subtitles_in(e, "de")
    doc = json.loads((e / "subs" / "de.json").read_text(encoding="utf-8"))
    doc["phrases"][0]["text"] = ""  # an edit that the next apply refuses
    (e / "subs" / "de.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project, check=False).returncode != 0
    with pytest.raises(SystemExit, match="translation in subs/de.json changed"):
        visual_plan.subtitles_in(e, "de")


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


def long_sentence_captions():
    """One 18-word sentence in a segment (the 16-word limit leaves its last two words alone), then a short sentence of
    its own before the next phrase."""
    text = ("I have filled roles in many fields like sales and marketing and finance and many other business areas. "
            "Yes. We help companies hire the right people").split()
    words, t = [], 0.0
    for w in text:
        words.append({"text": w, "start": round(t, 3), "end": round(t + 0.3, 3), "seg": 0})
        t += 0.33
    return {"duration": 12.0, "segments": [{"i": 0, "src_start": 0, "src_end": 12, "out_start": 0, "out_dur": 12}],
            "words": words}


def test_a_phrase_too_short_to_read_joins_its_neighbor():
    # T3: the 16-word limit left "areas." and "business." alone: one-word translations and 0.46-0.59 s subtitles
    import subs
    ps = subs.phrases_of(long_sentence_captions())
    assert [len(p["src"].split()) for p in ps] == [18, 8]  # the tail joins its sentence, "Yes." joins the next phrase
    assert ps[0]["src"].endswith("business areas.") and ps[1]["src"].startswith("Yes. We help")
    # translations made for the old split are joined, not lost
    old = [{"src": " ".join(ps[0]["src"].split()[:16]), "text": "Ich habe Stellen in vielen Bereichen besetzt"},
           {"src": "business areas.", "text": "und mehr."}, {"src": ps[1]["src"], "text": "Ja. Wir helfen."}]
    got = subs.take_translations(subs.phrases_of(long_sentence_captions()), old)
    assert [p["text"] for p in got] == ["Ich habe Stellen in vielen Bereichen besetzt und mehr.", "Ja. Wir helfen."]


def test_srt_lines_fit_the_width_and_keep_a_number_with_its_word():
    # T3: lines of 54-59 characters (a phrase longer than two lines was put in two anyway) and "more than five / years"
    import subs
    lines = subs.two_lines("Now I work with the ACME24 team and help companies find the right people")
    assert all(len(x) <= 42 for x in lines) and not lines[0].endswith(" and")  # the most even split was after "and"
    ru = subs.two_lines("Я Анна, рекрутер "
                        "с опытом более пяти "
                        "лет и представляю ACME24 "
                        "в Испании.")
    assert all(len(x) <= 42 for x in ru) and not ru[0].endswith("пяти")  # not torn after "pyati"
    words = [{"text": w, "start": k * 0.4, "end": k * 0.4 + 0.3, "glue": False} for k, w in enumerate(
        "Over the years I have filled roles in many fields: sales, IT, construction, marketing, accounting and other areas.".split())]
    parts = subs.pieces(words)
    texts = [subs.joined(p) for p in parts]
    assert len(parts) == 2 and texts[0].endswith("fields:")  # split at the colon, both halves fit two lines
    assert all(len(x) <= 42 for t in texts for x in subs.two_lines(t))


def test_srt_of_a_long_phrase_is_several_subtitles_timed_by_its_words(project):
    e = plan_project(project)
    write_json(e / "captions.json", long_sentence_captions())
    run_script("subs.py", "srt", "edit/4821", cwd=project)
    blocks = (e / "subtitles.srt").read_text(encoding="utf-8").strip().split("\n\n")
    assert len(blocks) == 3  # the 18-word sentence (102 characters) in two subtitles, then the next phrase
    assert all(len(line) <= 42 for b in blocks for line in b.split("\n")[2:])
    assert blocks[1].split("\n")[1].startswith("00:00:02,970 --> ")  # the second piece starts on its first word


def test_translated_words_carry_their_phrase(project):
    # the kit hides a translated phrase that a scene covers for the most part (T3: "company really needs." after one)
    e = plan_project(project)
    run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    translate(e)
    run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project)
    words = json.loads((e / "captions-de.json").read_text(encoding="utf-8"))["words"]
    assert {w["phrase"] for w in words} == {f"p{k:03d}" for k in range(1, 7)}


def test_a_scene_quote_in_the_subtitle_language_is_checked_against_the_translation(project):
    # T3: scene texts stayed in the speech language in the English version; written in English, a quote from the speech
    # must still be verbatim - against the translated subtitles
    e = plan_project(project, {"use_scenes": True, "subtitles_lang": "de"})
    run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    translate(e)
    run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project)
    run_script("visual_plan.py", "init", "edit/4821", cwd=project)
    run_script("visual_plan.py", "add", "edit/4821", "--kind", "scene", "--type", "quote", "--mode", "full",
               "--at", "6.5", "--dur", "3.4", "--lines", "Sie sagte:", "prüft, wie sie denken", "--source", "speech",
               "--what", "her words", "--why", "the key thought", cwd=project)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "not verbatim" not in r.stdout, r.stdout
    plan = json.loads((e / "visual_plan.json").read_text(encoding="utf-8"))
    plan["inserts"][0]["text"]["lines"] = ["Sie sagte:", "denkt nach"]
    write_json(e / "visual_plan.json", plan)
    r = run_script("visual_plan.py", "validate", "edit/4821", cwd=project, check=False)
    assert "not verbatim" in r.stdout and "captions-de.json" in r.stdout


def test_translated_subtitles_keep_the_speakers():
    # T4: the kit colors subtitles per speaker; a translated phrase must not mix two speakers and keeps its speaker
    import subs
    words = [{"text": t, "start": a, "end": b, "seg": 0, "speaker": s} for t, a, b, s in [
        ("So", 0.0, 0.3, "B"), ("it", 0.3, 0.5, "B"), ("helped", 0.5, 0.8, "B"), ("you", 0.8, 1.2, "B"),
        ("yes,", 1.2, 1.6, "A"), ("it", 1.6, 1.8, "A"), ("helped", 1.8, 2.2, "A"), ("a", 2.2, 2.3, "A"),
        ("lot.", 2.3, 2.8, "A")]]
    ps = subs.phrases_of({"words": words, "speakers": ["A", "B"]})
    # no pause and no sentence end between them: only the change of speaker ends the first phrase
    assert [(p["src"], p["speaker"]) for p in ps] == [("So it helped you", "B"), ("yes, it helped a lot.", "A")]
    ps[0]["text"], ps[1]["text"] = "Es hat dir also geholfen", "ja, sehr."
    assert {w["speaker"] for w in subs.timed_words(ps[1])} == {"A"}
    # a phrase too short to read alone does not join another speaker's
    short = words[:2] + words[4:]
    assert [p["speaker"] for p in subs.phrases_of({"words": short})] == ["B", "A"]
