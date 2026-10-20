"""cut.json "keep" (core 1.19.0, kit 1.12.0): a phrase the subtitles never split. An English test: the 5-word punchline
"it was just admin admin" went over two plates (Plate holds at most 4 words / 26 characters) and read in two beats.
cut.py marks the caption words, subs.py keeps the group in one phrase, the kit never ends a block inside it."""
import json

from conftest import needs_ffmpeg, run_script, write_json
from test_kit import KIT
from test_media import cut_project
from test_plan import plan_project


def keep_cut(project, keep):
    e = cut_project(project)
    doc = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    doc["keep"] = keep
    write_json(e / "cut.json", doc)
    return e


@needs_ffmpeg
def test_cut_marks_the_keep_words_and_dry_run_lists_them(project):
    import cut
    # the caption words: Hello, recruiter (fix of "recruter" 1.0), everything (fix_at of "all" 2.0), tail, end
    e = keep_cut(project, [{"text": "recruter", "at": 1.01, "words": 3}])
    c = cut.load_cut(e, project)
    words = cut.load_words(c)
    _, caps, _ = cut.timeline(c, words)
    groups, problems = cut.mark_keep(c, words, caps)
    assert [w.get("keep") for w in caps] == [None, "k1", "k1", "k1", None] and not problems
    assert groups[0][:2] == ("k1", "recruiter everything tail") and groups[0][3] == 3
    r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project)
    assert "keep k1: «recruiter everything tail» (3 words at" in r.stdout and "warning" not in r.stderr.lower(), r.stderr


@needs_ffmpeg
def test_cut_names_a_keep_mark_that_matches_nothing_and_honours_its_source(project):
    import cut
    e = keep_cut(project, [{"text": "recruiter", "at": 1.0, "words": 2},  # the fixed text: the transcript says "recruter"
                           {"text": "tail", "at": 4.5, "words": 3},        # only 2 words left after it
                           {"text": "Hello", "at": 0.45, "words": 2, "source": "side"}])  # another source's word
    c = cut.load_cut(e, project)
    words = cut.load_words(c)
    _, caps, _ = cut.timeline(c, words)
    groups, problems = cut.mark_keep(c, words, caps)
    assert [g[0] for g in groups] == ["k2"] and [w.get("keep") for w in caps][-2:] == ["k2", "k2"]
    assert any("keep[0]" in x and "no such word" in x for x in problems)
    assert any("keep[1]" in x and "only 2 of 3" in x for x in problems)
    assert any("keep[2]" in x and "no such word" in x for x in problems)
    r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project)
    assert "keep[0] «recruiter» at 1.0: no such word" in r.stderr


@needs_ffmpeg
def test_cut_checks_the_keep_entries(project):
    for bad, said in (({"text": "tail", "at": 4.5, "words": 3}, "keep is a list"),
                      ([{"text": "tail", "at": 4.5}], "keep[0]"),
                      ([{"text": "tail", "at": 4.5, "words": 1}], "words: 2 or more"),
                      ([{"text": "tail", "at": 4.5, "words": "3"}], "keep[0]"),
                      ([{"text": "tail", "at": 4.5, "words": 2, "source": "nope"}], "unknown source")):
        keep_cut(project, bad)
        r = run_script("cut.py", "edit/4821", "--dry-run", cwd=project, check=False)
        assert r.returncode == 1 and said in r.stderr and "Traceback" not in r.stderr, (bad, r.stderr)


def punch_captions():
    """A sentence, then the punchline over a pause of 0.6 s inside it and a sentence end before its last word: without
    the mark, subs.py would cut it in three."""
    said = [("So", 0.0), ("what", 0.3), ("was", 0.6), ("the", 0.9), ("password?", 1.2),
            ("It", 2.0), ("was", 2.3), ("just", 2.6), ("admin.", 3.5), ("Admin.", 3.8), ("Really", 4.6), ("simple", 4.9),
            ("stuff", 5.2), ("there", 5.5)]
    words = [{"text": t, "start": s, "end": round(s + 0.25, 3), "seg": 0, "src": s} for t, s in said]
    for w in words[5:10]:
        w["keep"] = "k1"
    return {"duration": 6.0, "segments": [{"i": 0, "src_start": 0, "src_end": 6, "out_start": 0, "out_dur": 6}],
            "words": words}


def test_subs_never_splits_a_keep_group_and_carries_a_whole_one(project):
    import subs
    ps = subs.phrases_of(punch_captions())
    assert [p["src"] for p in ps] == ["So what was the password?", "It was just admin. Admin.", "Really simple stuff there"]
    assert ps[1]["keep"] == "k1" and "keep" not in ps[0] and "keep" not in ps[2]
    e = plan_project(project)
    write_json(e / "captions.json", punch_captions())
    run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    f = e / "subs" / "de.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    for p, t in zip(doc["phrases"], ["Wie hieß das Passwort?", "Einfach admin. Admin.", "Ganz einfach"]):
        p["text"] = t
    write_json(f, doc)
    r = run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project)
    de = json.loads((e / "captions-de.json").read_text(encoding="utf-8"))["words"]
    assert [w.get("keep") for w in de] == [None] * 4 + ["k1"] * 3 + [None] * 2
    assert "keep k1" not in r.stderr


def test_subs_names_a_keep_group_inside_a_longer_phrase(project):
    cap = punch_captions()
    for w in cap["words"][5:10]:
        del w["keep"]
    for w in cap["words"][10:12]:  # "Really simple" inside "Really simple stuff there"
        w["keep"] = "k2"
    e = plan_project(project)
    write_json(e / "captions.json", cap)
    run_script("subs.py", "phrases", "edit/4821", "--lang", "de", cwd=project)
    f = e / "subs" / "de.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    for p in doc["phrases"]:
        p["text"] = "Ein Satz hier."
    write_json(f, doc)
    r = run_script("subs.py", "apply", "edit/4821", "--lang", "de", cwd=project)
    assert "keep k2 «Really simple» is part of the phrase" in r.stderr and "not carried" in r.stderr
    assert not any(w.get("keep") for w in json.loads((e / "captions-de.json").read_text(encoding="utf-8"))["words"])


def test_srt_does_not_split_a_keep_group():
    import subs
    text = "Over the years I have filled roles in many fields: sales, IT, construction, marketing, accounting and other areas."
    words = [{"text": w, "start": k * 0.4, "end": k * 0.4 + 0.3, "glue": False} for k, w in enumerate(text.split())]
    assert subs.joined(subs.pieces(words)[0]).endswith("fields:")  # the usual split, at the colon
    for w in words[9:12]:  # "fields: sales, IT,"
        w["keep"] = "k1"
    parts = subs.pieces(words)
    assert len(parts) == 2 and any("fields: sales, IT," in subs.joined(p) for p in parts)


def test_the_kit_keeps_a_group_on_one_block():
    subs = (KIT / "kit" / "Subtitles.tsx").read_text(encoding="utf-8")
    assert "keep?: string" in subs and "export const inKeep" in subs
    # buildChunks: no phrase ends inside a group, and a group that is the whole run stays one chunk past the limits
    assert "!inKeep(prev, w)" in subs and "!inKeep(w, words[k + 1])" in subs
    assert "if (inKeep(ws[best - 1], ws[best])) return [ws];" in subs
    # bestSplit avoids a group first; fit() splits a group over two lines as if it had no mark, with a warning
    assert "const score = [inKeep(ws[k - 1], ws[k]) ? 1 : 0," in subs
    assert "buildChunks(ws.map(({ keep: _k, ...w }) => w), maxWords, maxChars)" in subs
    assert "does not fit two lines: split as usual" in subs
    # two lines of a group are shown together, lifted above the bottom, not one at a time
    assert "!kept && top + height(g, size, lines.length) > bottom" in subs
    ver = (KIT / "kit" / "version.ts").read_text(encoding="utf-8")
    assert 'KIT_VERSION = "1.12.0"' in ver
