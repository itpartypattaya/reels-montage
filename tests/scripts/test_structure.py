"""structure.py: phrase signs, clean edges by the speech mask, teaser candidates, history of a source."""
import json

from conftest import make_speech, needs_ffmpeg, run_script, write_json

# a made-up dialogue: (phrase, start, end); each phrase is one tone burst in the audio
DIALOGUE = [("So, are you ready?", 0.5, 1.6), ("Yes.", 2.0, 2.3), ("What will you do later?", 2.8, 3.9),
            ("No, no, no, never that!", 4.5, 6.0), ("And why?", 6.4, 7.0), ("Because it is hard.", 7.5, 8.6),
            ("Then what?", 9.0, 9.6), ("A rich husband.", 10.2, 11.3), ("Sure.", 12.0, 12.3)]


def words_of(rows):
    out = []
    for text, s, e in rows:
        toks = text.split()
        step = (e - s) / len(toks)
        out += [{"text": t, "start": round(s + k * step, 3), "end": round(s + (k + 1) * step, 3), "type": "word"}
                for k, t in enumerate(toks)]
    return out


def setup(project, rows, bursts, dur=13.0, vid="0002", src="IMG_7777.MOV"):
    e = project / "edit" / vid
    (e / "transcripts").mkdir(parents=True)
    write_json(e / "transcripts" / "IMG_7777.json", {"language_code": "en", "source": src, "words": words_of(rows)})
    make_speech(e / "audio16k-IMG_7777.wav", bursts, dur)
    return e


@needs_ffmpeg
def test_signs_teasers_and_ending(project):
    e = setup(project, DIALOGUE, [(s, e) for _, s, e in DIALOGUE])
    r = run_script("structure.py", "suggest", "edit/0002", cwd=project)
    doc = json.loads((e / "structure.json").read_text(encoding="utf-8"))
    ps = doc["phrases"]
    assert "question" in ps[0]["signs"] and "answer" in ps[1]["signs"]
    strong = ps[3]
    assert {"repeat", "exclaim", "answer"} <= set(strong["signs"]) and strong["clean"]
    # the strongest later line is the first teaser, with cut edges from the audio: onset - 20 ms, end + 30 ms
    assert doc["teasers"][0] == 3
    assert abs(strong["range"][0] - 4.48) < 0.04 and abs(strong["range"][1] - 6.03) < 0.04
    # the payoff of the ending is listed too, with the risk of giving it away
    assert doc["ending"]["payoff"] == 7 and 7 in doc["teasers"]
    assert "gives the ending away" in r.stdout
    assert doc["ending"]["last"] == 8


@needs_ffmpeg
def test_no_clean_edge_in_continuous_speech(project):
    rows = [("First part here.", 1.0, 2.0), ("Second part now!", 2.04, 3.0), ("A pause, then this.", 3.6, 4.6)]
    e = setup(project, rows, [(1.0, 2.0), (2.04, 3.0), (3.6, 4.6)], dur=5.5)
    run_script("structure.py", "suggest", "edit/0002", cwd=project)
    ps = json.loads((e / "structure.json").read_text(encoding="utf-8"))["phrases"]
    # 40 ms between the first two phrases is a dip, not a pause: neither can be cut out alone
    assert ps[0]["clean"] is False and ps[1]["clean"] is False and ps[1]["range"] is None
    assert ps[2]["clean"] is True


@needs_ffmpeg
def test_slow_start_and_hyphenated_words(project):
    # the strong line is looked for in the first third of the speech (T5), so the video goes on after the question
    rows = [("Hello everyone, welcome to the channel.", 0.5, 4.5), ("Is it hard?", 5.0, 5.8),
            ("It is, at the very start, and then it gets easier.", 6.6, 10.0),
            ("Practice every day and it all becomes simple enough.", 10.6, 14.5)]
    e = setup(project, rows, [(s, t) for _, s, t in rows], dur=15.0)
    doc_t = json.loads((e / "transcripts" / "IMG_7777.json").read_text(encoding="utf-8"))
    doc_t["words"] += [{"text": "no", "start": 5.9, "end": 6.0, "type": "word"},
                       {"text": "-no.", "start": 6.0, "end": 6.1, "type": "word"}]
    doc_t["words"].sort(key=lambda w: w["start"])
    write_json(e / "transcripts" / "IMG_7777.json", doc_t)
    r = run_script("structure.py", "suggest", "edit/0002", cwd=project)
    doc = json.loads((e / "structure.json").read_text(encoding="utf-8"))
    assert doc["slow_start_s"] == 4.5 and "slow start" in r.stdout
    assert any(p["text"].endswith("no-no.") for p in doc["phrases"])


@needs_ffmpeg
def test_slow_start_never_points_at_the_end_and_a_number_opens(project):
    # T5: a voice-over tour said "slow start: 37.8 s ... offer to start there", i.e. start at the video's last line,
    # while phrase #0 with the price was not "strong". A number in the opening seconds is a strong opening, and the
    # strong line is looked for in the first third of the speech only
    rows = [("Guys, the price of this flat is 1 million 270 thousand baht.", 0.5, 4.0),
            ("Here is the flat that needs only a little bit of renovation.", 4.3, 8.0),
            ("Paint the walls and treat them against the damp and that is all.", 8.3, 13.0),
            ("With a view like this you can change the furniture as well.", 13.3, 18.0),
            ("26 square meters.", 18.6, 20.0)]
    e = setup(project, rows, [(s, t) for _, s, t in rows], dur=21.0)
    r = run_script("structure.py", "suggest", "edit/0002", cwd=project)
    doc = json.loads((e / "structure.json").read_text(encoding="utf-8"))
    assert doc["strong_first"] == 0 and doc["slow_start_s"] == 0.0 and "slow start" not in r.stdout
    # no strong line in the first third: no hint to start late, a note to judge the first line by meaning
    rows[0] = ("Guys, here is a flat in a quiet complex right by the sea.", 0.5, 4.0)
    write_json(e / "transcripts" / "IMG_7777.json", {"language_code": "en", "source": "IMG_7777.MOV",
                                                     "words": words_of(rows)})
    r = run_script("structure.py", "suggest", "edit/0002", cwd=project)
    doc = json.loads((e / "structure.json").read_text(encoding="utf-8"))
    assert doc["slow_start_s"] is None and doc["strong_first"] is None
    assert "slow start" not in r.stdout and "no question, number or strong line" in r.stdout


@needs_ffmpeg
def test_clean_edges_by_the_mask_when_transcript_times_touch(project):
    # T5: faster-whisper glued the pauses into words (a word ends where the next phrase starts), and 7 of 9 phrases
    # had "no clean edge" although the speech mask had >= 0.4 s of silence between almost all of them. The real end
    # sits ~1 s before the transcript's (beyond the drift window) and the next onset just before the transcript's
    e = project / "edit" / "0002"
    (e / "transcripts").mkdir(parents=True)
    w = [("One", 0.5, 0.8), ("two", 0.8, 1.2), ("three.", 1.2, 2.7),       # speech 0.5-1.5, the pause glued in
         ("Four", 2.7, 3.0), ("five", 3.0, 3.3), ("six.", 3.3, 4.8),        # speech 2.6-3.6: starts 0.1 s early
         ("Seven", 4.8, 5.1), ("eight", 5.1, 5.4), ("nine.", 5.4, 5.7)]     # speech 4.7-5.7
    write_json(e / "transcripts" / "IMG_7777.json", {"language_code": "en", "source": "IMG_7777.MOV", "words": [
        {"text": t, "start": s, "end": x, "type": "word"} for t, s, x in w]})
    make_speech(e / "audio16k-IMG_7777.wav", [(0.5, 1.5), (2.6, 3.6), (4.7, 5.7)], 6.5)
    run_script("structure.py", "suggest", "edit/0002", cwd=project)
    ps = json.loads((e / "structure.json").read_text(encoding="utf-8"))["phrases"]
    assert [p["clean"] for p in ps] == [True, True, True], [(p["text"], p["range"]) for p in ps]
    # the edges sit in the silences (frame-snapped, with the 20-30 ms margins), not at the touching transcript times
    assert abs(ps[0]["range"][1] - 1.55) < 0.08 and abs(ps[1]["range"][0] - 2.58) < 0.08
    assert abs(ps[1]["range"][1] - 3.65) < 0.08 and abs(ps[2]["range"][0] - 4.68) < 0.08


def test_history_needs_the_file_name_not_a_word_in_the_notes(project):
    # T5: "tairai" the brand name in another video's notes counted as the same source tairai.mp4
    write_json(project / "edit" / "0002" / "cut.json", {"sources": {"main": {"file": "sunrise.mp4"}}})
    (project / "edit" / "0003").mkdir()
    (project / "edit" / "0003" / "project.md").write_text(
        "# 0003\nBrand `sunrise`, source IMG_0567.MOV, render sunrise-promo-2026-10-01.mp4\n", encoding="utf-8")
    (project / "edit" / "0004").mkdir()
    (project / "edit" / "0004" / "project.md").write_text("# 0004\nSource: `sunrise.mp4`, cold open.\n", encoding="utf-8")
    write_json(project / "edit" / "0005" / "transcripts" / "sunrise_old.json", {"words": []})
    out = run_script("structure.py", "history", "edit/0002", cwd=project).stdout
    assert "edit/0004 (project.md)" in out and "0003" not in out and "0005" not in out


def test_history_finds_earlier_edits_of_the_source(project):
    write_json(project / "edit" / "0001" / "cut.json", {"sources": {"main": {"file": "IMG_7777.MOV"}}})
    (project / "edit" / "0001" / "project.md").write_text("# 0001\nCold open on the strongest line.\n", encoding="utf-8")
    (project / "edit" / "project.md").write_text("## Session 1\n**Strategy:** img_7777, a cold open.\n", encoding="utf-8")
    write_json(project / "edit" / "0003" / "cut.json", {"sources": {"main": {"file": "IMG_1234.MOV"}}})
    write_json(project / "edit" / "0002" / "cut.json", {"sources": {"main": {"file": "IMG_7777.MOV"}}})
    r = run_script("structure.py", "history", "edit/0002", cwd=project)
    out = r.stdout
    assert "edit/0001 (cut.json): Cold open on the strongest line." in out
    assert "edit (project.md): **Strategy:** img_7777" in out and "0003" not in out and "0002" not in out
    r = run_script("structure.py", "history", "IMG_1234.MOV", cwd=project)
    assert "edit/0003 (cut.json)" in r.stdout


@needs_ffmpeg
def test_edge_stays_between_the_neighbor_phrases(project):
    # Codex review: in continuous speech the onset of the previous phrase was taken as this phrase's clean start,
    # and the teaser range carried the neighbor's words along
    rows = [("Is it?", 1.0, 1.4), ("Yes it is.", 1.45, 2.0), ("Later.", 3.0, 3.5)]
    e = setup(project, rows, [(1.0, 2.0), (3.0, 3.5)], dur=4.5)
    run_script("structure.py", "suggest", "edit/0002", cwd=project)
    ps = json.loads((e / "structure.json").read_text(encoding="utf-8"))["phrases"]
    assert ps[1]["clean"] is False and ps[1]["range"] is None
    assert ps[2]["clean"] is True


@needs_ffmpeg
def test_transcript_path_relative_to_the_video_folder(project):
    # Codex review: cut.json may name the transcript relative to edit/<id> (as cut.py resolves it); another
    # transcript in transcripts/ must not be taken instead
    e = setup(project, DIALOGUE[:3], [(s, e) for _, s, e in DIALOGUE[:3]], dur=5.0)
    write_json(e / "transcripts" / "B.json", {"language_code": "en", "source": "B.MOV",
                                              "words": words_of([("Other video.", 0.5, 1.0)])})
    (e / "custom.json").write_text((e / "transcripts" / "IMG_7777.json").read_text(encoding="utf-8"), encoding="utf-8")
    (e / "transcripts" / "IMG_7777.json").unlink()
    write_json(e / "cut.json", {"sources": {"main": {"file": "IMG_7777.MOV", "transcript": "custom.json"}}})
    run_script("structure.py", "suggest", "edit/0002", cwd=project)
    doc = json.loads((e / "structure.json").read_text(encoding="utf-8"))
    assert doc["transcript"].endswith("custom.json") and doc["phrases"][0]["text"] == "So, are you ready?"


def test_history_reads_the_short_source_form(project):
    # Codex review: "sources": {"main": "A.mov"} is a valid cut.json; the history ignored it
    write_json(project / "edit" / "0001" / "cut.json", {"sources": {"main": "A.mov"}})
    write_json(project / "edit" / "0002" / "cut.json", {"sources": {"main": "A.mov"}})
    r = run_script("structure.py", "history", "edit/0002", cwd=project)
    assert "edit/0001 (cut.json)" in r.stdout


def tone_wav(path, bursts, dur, rate=16000):
    """A 300 Hz tone on exactly these spans (sample-accurate: ffmpeg's per-frame volume rounds edges to ~23 ms, too
    coarse for a 90 ms gap against a 100 ms one)."""
    import math
    import struct
    import wave
    n = int(dur * rate)
    on = bytearray(n)
    for a, b in bursts:
        for k in range(int(a * rate), min(n, int(b * rate))):
            on[k] = 1
    data = b"".join(struct.pack("<h", int(16000 * math.sin(2 * math.pi * 300 * k / rate)) if on[k] else 0)
                    for k in range(n))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)
    return path


def setup_exact(project, rows, bursts, dur):
    e = project / "edit" / "0002"
    (e / "transcripts").mkdir(parents=True)
    write_json(e / "transcripts" / "IMG_7777.json", {"language_code": "en", "source": "IMG_7777.MOV",
                                                     "words": words_of(rows)})
    tone_wav(e / "audio16k-IMG_7777.wav", bursts, dur)
    return e


def suggest(project, e, *args):
    r = run_script("structure.py", "suggest", "edit/0002", *args, cwd=project)
    return r, json.loads((e / "structure.json").read_text(encoding="utf-8"))


def test_teaser_range_keeps_the_last_word(project):
    # T1: the transcript ended a phrase 0.4 s before its last word ("...and you just | signed the deal?"); the
    # nearest clean end to that time was the pause before the last word, and the range cut it off. The latest
    # clean end before the next phrase is the phrase's end.
    rows = [("Earlier line here.", 0.5, 1.5), ("They brought them and you just signed.", 2.0, 3.4),
            ("Next one.", 4.6, 5.2)]
    e = setup_exact(project, rows, [(0.5, 1.5), (2.0, 3.2), (3.35, 3.8), (4.6, 5.2)], 6.0)
    _, doc = suggest(project, e)
    p = doc["phrases"][1]
    assert p["clean"] and abs(p["range"][0] - 1.95) < 0.04 and abs(p["range"][1] - 3.86) < 0.04


def test_line_running_into_the_next_is_not_clean(project):
    # T1: "Worked with objections, and so? | That does not mean sold." 90 ms apart. The first range ended at the
    # pause before "and so?" (dropping them), the second started at the pause before "sold" (one word of four).
    # 90 ms is not the 0.1 s of silence a cut needs: both are only cut out together.
    rows = [("Worked with objections, and so?", 1.0, 2.6), ("That does not mean sold.", 2.69, 3.6),
            ("Later on.", 4.5, 5.0)]
    e = setup_exact(project, rows, [(1.0, 1.9), (2.08, 2.6), (2.69, 3.2), (3.34, 3.6), (4.5, 5.0)], 5.8)
    _, doc = suggest(project, e)
    a, b = doc["phrases"][0], doc["phrases"][1]
    assert a["clean"] is False and a["range"] is None
    assert b["clean"] is False and b["range"] is None
    assert doc["phrases"][2]["clean"] is True


def test_long_question_stays_one_phrase(project):
    # T1: a 22-word question was split at 16 words (a subtitle-line cap) into two halves, neither cleanly cut out
    q = ("And do you show your value in the resume or just tell about your experience and what you did there "
         "every day?")
    e = setup_exact(project, [("Earlier line here.", 0.5, 1.5), (q, 2.0, 8.6)], [(0.5, 1.5), (2.0, 8.6)], 9.5)
    _, doc = suggest(project, e)
    assert len(doc["phrases"]) == 2
    p = doc["phrases"][1]
    assert p["words"] == 22 and "question" in p["signs"] and p["clean"]


def test_fragment_of_a_long_recording(project):
    # T1: 30 s of a 96 s source were chosen; the teasers and the ending came from outside them
    e = setup_exact(project, DIALOGUE, [(s, e) for _, s, e in DIALOGUE], 13.0)
    r, doc = suggest(project, e, "--from", "6.3", "--to", "11.5")
    assert [p["i"] for p in doc["phrases"]] == [4, 5, 6, 7] and doc["window"] == [6.3, 11.5]
    assert 4 not in doc["teasers"] and 3 not in doc["teasers"]
    assert doc["ending"] == {"last": 7, "payoff": 7}
    assert "fragment 6.3-11.5 s" in r.stdout


@needs_ffmpeg
def test_two_cameras_need_a_source_and_a_long_to_is_flagged(project):
    # T2: two angles in cut.json, no --transcript: the script silently took the newest transcript (the other angle,
    # 87.8 s long) and analyzed --from 59 --to 108 on it
    e = setup(project, DIALOGUE, [(s, e) for _, s, e in DIALOGUE])
    write_json(e / "transcripts" / "IMG_8888.json", {"language_code": "en", "source": "IMG_8888.MOV",
                                                     "words": words_of([("Another angle entirely.", 0.5, 2.0)])})
    write_json(e / "cut.json", {"sources": {"front": {"file": "IMG_7777.MOV"}, "side": {"file": "IMG_8888.MOV"}}})
    r = run_script("structure.py", "suggest", "edit/0002", cwd=project, check=False)
    assert r.returncode != 0 and "--source KEY" in r.stderr and "front (transcripts/IMG_7777.json)" in r.stderr
    assert "side (transcripts/IMG_8888.json)" in r.stderr
    r, doc = suggest(project, e, "--source", "front", "--to", "30")
    assert doc["transcript"].endswith("IMG_7777.json") and doc["phrases"][0]["text"] == "So, are you ready?"
    assert "--to 30.0 is past the last word of IMG_7777.json (12.3 s)" in r.stderr
    # no cut.json and two transcripts: the same refusal, with the files
    (e / "cut.json").unlink()
    r = run_script("structure.py", "suggest", "edit/0002", cwd=project, check=False)
    assert r.returncode != 0 and "IMG_7777.json, IMG_8888.json" in r.stderr


@needs_ffmpeg
def test_teasers_skip_estimated_and_broken_lines_and_keep_a_clean_statement(project):
    # T4: the teaser candidates were an interjection whose first word had an estimated time ("OK, let's go") and the
    # fragment of a broken take, while a clean whole statement with a beat after it was not listed; the payoff was the
    # interjection too
    rows = [("So tell me, did it help you?", 0.5, 2.0), ("OK, let's go.", 2.5, 3.6),
            ("I learned that sales left a hard mark on me.", 4.5, 7.3), ("And so I wanted to...", 8.0, 9.0),
            ("I as HR again prove", 9.5, 12.0), ("It is great.", 12.6, 13.4)]
    e = setup(project, rows, [(s, e) for _, s, e in rows], dur=14.5)
    tr = e / "transcripts" / "IMG_7777.json"
    doc = json.loads(tr.read_text(encoding="utf-8"))
    for w in doc["words"]:
        if w["text"] == "OK,":
            w["est"] = True  # the online add-on laid a cloud word the local model did not hear
        if w["text"] == "prove":
            w["start"] = 10.1  # a retake merged into one 1.9 s word
    write_json(tr, doc)
    r = run_script("structure.py", "suggest", "edit/0002", cwd=project)
    out = json.loads((e / "structure.json").read_text(encoding="utf-8"))
    ps = out["phrases"]
    assert ps[1]["est"] == 1 and ps[3]["unfinished"] and ps[4]["suspect"] == ["prove"]
    # the clean statement is listed; the interjection, the trailing-off line and the broken take are not (the last line
    # is listed too, with the risk of giving the ending away)
    assert 2 in out["teasers"] and not {1, 3, 4} & set(out["teasers"]), out["teasers"]
    assert ps[2]["clean"] and "beat" in ps[2]["signs"]
    assert out["ending"]["payoff"] is None  # the interjection is no payoff
    assert "cannot judge meaning" in r.stdout and "retake?" in r.stdout and "est" in r.stdout


@needs_ffmpeg
def test_a_short_pause_in_the_widened_mask_is_still_a_clean_edge(project):
    # T7: a 0.24 s pause (raw silence) between touching transcript times is a 0.18 s gap in the speech mask, which is
    # widened by ~30 ms on each side; requiring 0.2 s of MASK silence called the next phrase "no clean edge", while
    # speech_mask.py cut it cleanly and the --edl check gave no warning. The rule is the edges' own: >= 0.1 s of raw
    # silence. The transcript glued the pause into "three." and put "Four" 60 ms after the real onset
    e = project / "edit" / "0002"
    (e / "transcripts").mkdir(parents=True)
    w = [("One", 1.0, 1.4), ("two", 1.4, 1.8), ("three.", 1.8, 2.3),
         ("Four", 2.3, 2.6), ("five", 2.6, 2.9), ("six.", 2.9, 3.2)]
    write_json(e / "transcripts" / "IMG_7777.json", {"language_code": "en", "source": "IMG_7777.MOV", "words": [
        {"text": t, "start": s, "end": x, "type": "word"} for t, s, x in w]})
    make_speech(e / "audio16k-IMG_7777.wav", [(1.0, 2.0), (2.24, 3.2)], 4.0)
    r = run_script("structure.py", "suggest", "edit/0002", cwd=project)
    ps = json.loads((e / "structure.json").read_text(encoding="utf-8"))["phrases"]
    assert [p["clean"] for p in ps] == [True, True], [(p["text"], p["range"]) for p in ps]
    assert abs(ps[0]["range"][1] - 2.03) < 0.05 and abs(ps[1]["range"][0] - 2.2) < 0.05, ps
    # an 80 ms pause stays continuous speech: < 0.1 s of raw silence
    make_speech(e / "audio16k-IMG_7777.wav", [(1.0, 2.0), (2.08, 3.2)], 4.0)
    run_script("structure.py", "suggest", "edit/0002", cwd=project)
    ps = json.loads((e / "structure.json").read_text(encoding="utf-8"))["phrases"]
    assert ps[1]["clean"] is False
    # the output explains its flags (T7: "est" was printed with no explanation)
    assert "est = a word whose time is estimated" in r.stdout and "retake? = a word longer than 1.5 s" in r.stdout


def test_range_end_is_not_pulled_into_the_last_syllable_by_float_error():
    # review: the scan for the next speech started at int(b / hop), and b = j * hop reads as j - 1 for ~5% of j:
    # mask[j - 1] is the phrase's own speech, so the end came out 40 ms before it (cut.py's fade then hit the syllable)
    import structure
    hop = 0.01
    j = next(j for j in range(60, 400) if int(j * hop / hop) != j)
    mask = [20 <= k < j for k in range(j + 60)]
    r = structure.cut_range((mask, [not x for x in mask], hop), {"start": 0.2, "end": j * hop - 0.05, "inner": None})
    assert r and r[1] >= j * hop, (j, r)


def test_speech_at_the_file_edges_is_clean():
    # review: a clip trimmed tight to its first or last word had "no clean edge" there: the start and the end of the
    # file count as silence
    import structure
    hop, n = 0.01, 300
    mask = [k < 80 or k >= 200 for k in range(n)]
    m = (mask, [not x for x in mask], hop)
    first, last = {"start": 0.0, "end": 0.8, "inner": None}, {"start": 2.0, "end": 3.0, "inner": None}
    a, b = structure.cut_range(m, first, None, last), structure.cut_range(m, last, first, None)
    assert a and a[0] == 0.0 and abs(a[1] - 0.833) < 0.02, a
    assert b and abs(b[0] - 1.967) < 0.02 and b[1] == 3.0, b


def test_a_dash_token_is_not_a_word_or_a_retake():
    # review: faster-whisper returns a dash as a word; of no length, it read as a retake and the line left the teasers
    import structure
    words = [{"text": "Sales", "start": 1.0, "end": 1.4}, {"text": "—", "start": 1.4, "end": 1.4},
             {"text": "that", "start": 1.5, "end": 1.7}, {"text": "is", "start": 1.7, "end": 1.8},
             {"text": "life.", "start": 1.8, "end": 2.2}]
    p = structure.phrases(structure.join_punct(words))[0]
    assert p["text"] == "Sales — that is life." and p["words"] == 4 and not p["suspect"] and structure.usable(p)


@needs_ffmpeg
def test_a_missing_transcript_of_the_only_source_is_not_replaced_by_another(project):
    # review: cut.json names IMG_2; transcripts/ holds only an older take's IMG_1.json, which was analyzed silently
    e = setup(project, DIALOGUE[:3], [(s, e) for _, s, e in DIALOGUE[:3]], dur=5.0)
    write_json(e / "cut.json", {"sources": {"main": "IMG_2.MOV"}})
    r = run_script("structure.py", "suggest", "edit/0002", cwd=project, check=False)
    assert r.returncode != 0 and "IMG_2.json" in r.stderr and "no transcript" in r.stderr


@needs_ffmpeg
def test_a_broken_cut_json_elsewhere_does_not_stop_the_analysis(project):
    # review: a cut.json with a syntax error (or an editor's BOM) in another folder crashed suggest and history
    e = setup(project, DIALOGUE[:3], [(s, e) for _, s, e in DIALOGUE[:3]], dur=5.0)
    (project / "edit" / "0009").mkdir()
    (project / "edit" / "0009" / "cut.json").write_text("{bad", encoding="utf-8")
    r = run_script("structure.py", "suggest", "edit/0002", cwd=project)
    assert (e / "structure.json").exists() and "edit/0009/cut.json: not read" in r.stderr


def test_history_of_a_dotted_video_id(project):
    # review: "edit/reel.v2" was read as the source file "reel"
    write_json(project / "edit" / "reel.v2" / "cut.json", {"sources": {"main": "A.mov"}})
    write_json(project / "edit" / "0001" / "cut.json", {"sources": {"main": "A.mov"}})
    r = run_script("structure.py", "history", "edit/reel.v2", cwd=project)
    assert "edit/0001 (cut.json)" in r.stdout


@needs_ffmpeg
def test_beat_by_the_audio_and_the_source_in_the_teaser_range(project):
    # review: where faster-whisper glued the pause into a word, the beat after a line read the transcript gap (0.0)
    # though the audio had 1 s of silence; with --source the printed ranges entry had no "source" (cut.py needs it)
    e = project / "edit" / "0002"
    (e / "transcripts").mkdir(parents=True)
    w = [("Hello", 0.5, 0.8), ("there", 0.8, 1.2), ("friends.", 1.2, 2.7),
         ("Are", 2.7, 3.0), ("you", 3.0, 3.3), ("ready?", 3.3, 3.6),
         ("No,", 4.6, 4.9), ("no,", 4.9, 5.2), ("no!", 5.2, 5.6), ("Sure.", 6.6, 7.0)]
    write_json(e / "transcripts" / "IMG_7777.json", {"language_code": "en", "source": "IMG_7777.MOV", "words": [
        {"text": t, "start": s, "end": x, "type": "word"} for t, s, x in w]})
    make_speech(e / "audio16k-IMG_7777.wav", [(0.5, 1.5), (2.6, 3.6), (4.6, 5.6), (6.6, 7.0)], 8.0)
    write_json(e / "cut.json", {"sources": {"main": {"file": "IMG_7777.MOV"}, "side": {"file": "IMG_8888.MOV"}}})
    r, doc = suggest(project, e, "--source", "main")
    ps = doc["phrases"]
    assert "beat" in ps[0]["signs"] and ps[0]["gap_after"] > 0.9, ps[0]
    assert '"source": "main", "start":' in r.stdout
