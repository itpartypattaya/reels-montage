"""longform.py (a long recording -> a series of clips) and the Remotion run folders of reels_common / kit.py."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

from conftest import CORE, make_video, needs_ffmpeg, probe_streams, run_script, write_json

import longform as lf
import reels_common as rc


# --- times, tokens, subtitles --------------------------------------------------------------------------------------

def test_seconds_and_timecodes():
    assert lf.seconds("03:07.5") == pytest.approx(187.5)
    assert lf.seconds("1:00:02") == pytest.approx(3602)
    assert lf.seconds(12) == 12.0 and lf.seconds("12,5") == 12.5 and lf.seconds(None) is None
    assert lf.tc(187.54) == "03:07.5" and lf.tc(3725) == "1:02:05.0"
    assert lf.tc(1079.99) == "18:00.0"  # not "17:60.0"


def test_tokens_fold_case_and_yo():
    assert lf.tokens_of("Hello, World! 80 %") == ["hello", "world", "80"]
    assert lf.tokens_of("\u0412\u0441\u0451") == ["\u0432\u0441\u0435"]  # a capital and the letter yo
    assert lf.same_token("recruiting", "recruiter") and not lf.same_token("sale", "sales")


SRT = """1
00:00:01,000 --> 00:00:03,500
Anna: Hello and welcome.

2
00:00:03,500 --> 00:00:06,000
[Music]

3
00:00:06,000 --> 00:00:09,000
Ben: So what do you look for?
"""

VTT_ROLLING = """WEBVTT
Kind: captions

00:00:01.000 --> 00:00:03.000 align:start position:0%
the first<00:00:01.500><c> line</c>

00:00:03.000 --> 00:00:03.010
the first line

00:00:03.010 --> 00:00:05.000
the first line
the second<00:00:03.500><c> one</c>

00:00:05.000 --> 00:00:05.010
the second one

00:00:05.010 --> 00:00:07.000
the second one
and the third
"""


def test_srt_speakers_and_tags():
    cues = lf.cues_from(lf.parse_subtitles(SRT))
    assert [c["text"] for c in cues] == ["Hello and welcome.", "So what do you look for?"]
    assert cues[0]["speaker"] == "Anna" and cues[1]["speaker"] == "Ben"
    assert "music" in cues[0]["tags"]  # the tag-only cue marks the line before it


def test_vtt_rolling_captions_are_folded():
    cues = lf.cues_from(lf.parse_subtitles(VTT_ROLLING))
    assert [c["text"] for c in cues] == ["the first line", "the second one", "and the third"]
    assert cues[0]["start"] == 1.0 and cues[2]["end"] == 7.0
    assert all(a["end"] <= b["start"] for a, b in zip(cues, cues[1:]))


def test_json_segments_with_short_keys():
    cues = lf.cues_from_json([{"s": 1, "e": 2.5, "spk": "host", "text": " Hi [laughter]"}, {"start": 3, "end": 4, "text": "Yes"}])
    assert cues[0] == {"start": 1.0, "end": 2.5, "text": "Hi", "speaker": "host", "tags": ["laughter"], "i": 0}
    assert cues[1]["text"] == "Yes" and "speaker" not in cues[1]


# --- a synthetic recording with a word-level transcript --------------------------------------------------------------

SENTENCES = [
    ("host", "Welcome to the show, today we talk about hiring."),
    ("guest", "Thank you for having me here today."),
    ("host", "What do you look for in a sales candidate?"),
    ("guest", "I look at numbers first, because a strong seller always speaks in numbers."),
    ("guest", "As I said, the second thing is responsibility for the result."),
    ("guest", "A weak candidate blames marketing, leads and the boss."),
    ("host", "Wow, that is strong."),
    ("guest", "And one more thing: a strong seller asks questions back."),
    ("guest", "I look at numbers first, because a strong seller always speaks in numbers."),
    ("guest", "That is the whole method and it works every time."),
]


def words_of(sentences, t0=1.0, w=0.3, gap=0.7):
    out, t = [], t0
    for spk, s in sentences:
        for tok in s.split():
            out.append({"text": tok, "start": round(t, 3), "end": round(t + w - 0.05, 3), "type": "word", "speaker": spk})
            t += w
        t += gap
    return out, t


@pytest.fixture
def series(project):
    """A 50 s horizontal recording, its series folder (init) and a word-level transcript."""
    if not __import__("shutil").which("ffmpeg"):
        pytest.skip("ffmpeg is needed")
    src = make_video(project / "talk.mp4", w=320, h=180, dur=50)
    run_script("longform.py", "init", "edit/talk", "talk.mp4", cwd=project)
    words, _ = words_of(SENTENCES)
    blames = next(w for w in words if w["text"] == "blames")
    blames["end"] = round(blames["start"] + 1.2, 3)  # a stretched word: transcribe.check_doc notes it, not an error
    write_json(project / "edit" / "talk" / "transcripts" / "talk.json",
               {"language_code": "en", "text": "", "words": words, "source": "talk.mp4", "timeline": "video"})
    return project, src, words


def cards(project, clips, **extra):
    write_json(project / "edit" / "talk" / "clips.json", {"length": [3, 60], **extra, "clips": clips})


def check(project, *args, ok=True):
    return run_script("longform.py", "check", "edit/talk", *args, cwd=project, check=ok)


@needs_ffmpeg
def test_init_writes_the_recording(series):
    project, _, _ = series
    m = json.loads((project / "edit" / "talk" / "longform.json").read_text(encoding="utf-8"))
    assert m["source"]["file"] == "talk.mp4" and m["source"]["w"] == 320 and m["source"]["duration"] == pytest.approx(50, abs=0.1)


@needs_ffmpeg
def test_outline_parts_and_marks(series):
    project, _, _ = series
    r = run_script("longform.py", "outline", "edit/talk", "--chunk", "60", cwd=project)
    assert "part-01.md" in r.stdout and "speakers: guest" in r.stdout
    text = (project / "edit" / "talk" / "outline" / "part-01.md").read_text(encoding="utf-8")
    assert "host: What do you look for in a sales candidate?  ?" in text
    assert "guest: I look at numbers first" in text and "→" in text  # the answer to the question


@needs_ffmpeg
def test_check_resolves_words_and_reports(series):
    project, _, words = series
    cards(project, [
        {"id": "01", "title": "numbers", "parts": [
            {"from_words": "I look at numbers first", "to_words": "for the result.", "near": 11}]},
        {"id": "02", "title": "said twice", "parts": [
            {"from_words": "I look at numbers first, because", "to_words": "speaks in numbers."}]},
        {"id": "03", "title": "by seconds", "parts": [{"start": "00:30.0", "end": "00:36.0"}]},
    ], excluded=[{"start": 30.5, "end": 33, "why": "off topic"}])
    r = check(project, ok=False)
    assert r.returncode == 1
    doc = json.loads((project / "edit" / "talk" / "clips.json").read_text(encoding="utf-8"))
    c1, c2, c3 = doc["clips"]
    res = c1["parts"][0]["resolved"]
    first = next(w for w in words if w["text"] == "I")
    assert res["start"] == pytest.approx(first["start"]) and res["end"] > res["start"]
    assert not c1["check"]["errors"]
    assert any("said more than once" in x for x in c2["check"]["errors"])  # the same line twice, no near
    assert any("excluded stretch" in x for x in c3["check"]["errors"])
    assert "near" not in c1["parts"][0].get("resolved", {})  # the agent's fields stay as written
    assert c1["parts"][0]["from_words"] == "I look at numbers first"


@needs_ffmpeg
def test_check_warnings_backref_midsentence_speaker_overlap(series):
    project, _, _ = series
    cards(project, [
        {"id": "01", "parts": [{"from_words": "As I said, the second thing", "to_words": "leads and the boss.",
                                "near": 27}]},
        {"id": "02", "parts": [{"from_words": "the second thing is responsibility", "to_words": "that is strong.",
                                "near": 28}]},
    ])
    check(project)
    doc = json.loads((project / "edit" / "talk" / "clips.json").read_text(encoding="utf-8"))
    w1, w2 = (c["check"]["warnings"] for c in doc["clips"])
    assert any("opens with" in x and "as i said" in x for x in w1)
    assert any("starts mid-sentence" in x for x in w2)
    assert any("speaker changes" in x for x in w2)
    assert any("shares" in x and "card 01" in x for x in w2)
    doc["clips"][1]["allow"] = ["overlap:01"]
    write_json(project / "edit" / "talk" / "clips.json", doc)
    check(project)
    doc = json.loads((project / "edit" / "talk" / "clips.json").read_text(encoding="utf-8"))
    assert not any("shares" in x for x in doc["clips"][1]["check"]["warnings"])


@needs_ffmpeg
def test_mark_needs_a_clean_check_and_approval_drops_when_pieces_move(series):
    project, _, words = series
    cards(project, [{"id": "01", "parts": [{"from_words": "A weak candidate blames", "to_words": "and the boss.",
                                             "near": 30}]}])
    r = run_script("longform.py", "mark", "edit/talk", "01", "--as", "approved", cwd=project, check=False)
    assert r.returncode == 1 and "not checked" in r.stdout
    check(project)
    run_script("longform.py", "mark", "edit/talk", "01", "--as", "approved", cwd=project)
    tf = project / "edit" / "talk" / "transcripts" / "talk.json"
    doc = json.loads(tf.read_text(encoding="utf-8"))
    for w in doc["words"]:
        w["start"], w["end"] = w["start"] + 2.0, w["end"] + 2.0  # a new transcript: everything 2 s later
    time.sleep(0.05)
    write_json(tf, doc)
    r = check(project)
    c = json.loads((project / "edit" / "talk" / "clips.json").read_text(encoding="utf-8"))["clips"][0]
    assert c["status"] == "proposed" and "approve it again" in c["check"]["warnings"][0]


@needs_ffmpeg
def test_sheet_lists_cards_and_blockers(series):
    project, _, _ = series
    cards(project, [{"id": "01", "title": "Numbers first", "hook": "Sellers speak in numbers",
                     "parts": [{"from_words": "A weak candidate blames", "to_words": "and the boss.", "near": 30}]}],
          blockers=["rights to the recording"])
    check(project)
    run_script("longform.py", "sheet", "edit/talk", cwd=project)
    md = (project / "edit" / "talk" / "series.md").read_text(encoding="utf-8")
    assert "rights to the recording" in md and "| 01 | Numbers first |" in md and "Sellers speak in numbers" in md


@needs_ffmpeg
def test_extract_two_pieces_slice_and_rerun(series):
    project, src, words = series
    cards(project, [{"id": "01", "title": "method", "status": "approved", "rubric": "insight",
                     "parts": [{"from_words": "A weak candidate blames", "to_words": "and the boss.", "near": 30},
                               {"from_words": "That is the whole method", "to_words": "works every time.", "near": 47}]}],
          rubrics={"insight": {"label": "INSIGHT"}})
    check(project)
    run_script("longform.py", "mark", "edit/talk", "01", "--as", "approved", cwd=project)
    r = run_script("longform.py", "extract", "edit/talk", "01", "--pad", "1", cwd=project)
    ce = project / "edit" / "talk-01"
    frags = sorted((ce / "src").glob("*.mp4"))
    assert [f.name for f in frags] == ["talk-01a.mp4", "talk-01b.mp4"]
    st = probe_streams(frags[0])
    assert float(st["video"]["start_time"]) == pytest.approx(0, abs=0.05) and st["video"]["width"] == 320
    m = json.loads((project / "edit" / "talk" / "longform.json").read_text(encoding="utf-8"))
    rec = m["clips"]["01"]
    a = rec["pieces"][0]
    tr = json.loads((ce / "transcripts" / "talk-01a.json").read_text(encoding="utf-8"))
    weak = next(w for w in words if w["text"] == "A")
    got = next(w for w in tr["words"] if w["text"] == "A")
    assert got["start"] == pytest.approx(weak["start"] - a["offset"], abs=0.002)  # on the piece's own timeline
    assert tr["source_identity"]["path"] == str(frags[0].resolve()) and tr["slice_of"]["source"] == "talk.mp4"
    assert (ce / "audio16k-talk-01a.wav").is_file() and (ce / "audio16k-talk-01a.json").is_file()
    cut = json.loads((ce / "cut.json").read_text(encoding="utf-8"))
    assert set(cut["sources"]) == {"a", "b"} and [x["source"] for x in cut["ranges"]] == ["a", "b"]
    assert cut["ranges"][0]["start"] == pytest.approx(a["start_in"] - 0.05, abs=0.01)
    reel = json.loads((ce / "reel.json").read_text(encoding="utf-8"))
    assert reel["format"] == "framed" and reel["label"] == "INSIGHT"
    assert "talk.mp4" in (ce / "project.md").read_text(encoding="utf-8")
    # the transcript is a cache hit: transcribe.py never loads a model for the piece
    t = run_script("transcribe.py", "edit/talk-01", str(frags[0]), cwd=project)
    assert "cached" in t.stdout
    # cut.py takes the folder as it is
    d = run_script("cut.py", "edit/talk-01", "--dry-run", cwd=project)
    assert "segments 2" in d.stdout and "9 words  piece a" in d.stdout and "10 words  piece b" in d.stdout
    # a second extract with the same inputs does not cut again and keeps cut.json
    mt = frags[0].stat().st_mtime_ns
    (ce / "cut.json").write_text(json.dumps({**cut, "speed": 1.1}), encoding="utf-8")
    r2 = run_script("longform.py", "extract", "edit/talk", "01", "--pad", "1", cwd=project)
    assert frags[0].stat().st_mtime_ns == mt and "cut.json kept" in r2.stdout
    assert json.loads((ce / "cut.json").read_text(encoding="utf-8"))["speed"] == 1.1
    s = run_script("longform.py", "status", "edit/talk", cwd=project)
    assert "extracted ok" in s.stdout and "recording used" in s.stdout


@needs_ffmpeg
def test_reextract_rewrites_the_cut_and_makes_later_stages_stale(series):
    # review of PR #27: new pieces at the same paths kept the old cut.json (seconds of the old files), and status
    # still called the old rough cut, export and render current
    project, _, _ = series
    two = [{"from_words": "A weak candidate blames", "to_words": "and the boss.", "near": 30},
           {"from_words": "That is the whole method", "to_words": "works every time.", "near": 47}]
    cards(project, [{"id": "01", "parts": two}])
    check(project)
    run_script("longform.py", "mark", "edit/talk", "01", "--as", "approved", cwd=project)
    run_script("longform.py", "extract", "edit/talk", "01", "--pad", "1", cwd=project)
    ce = project / "edit" / "talk-01"
    cut = json.loads((ce / "cut.json").read_text(encoding="utf-8"))
    write_json(ce / "cut.json", {**cut, "speed": 1.1, "fix_at": [{"text": "A", "at": 1.0, "to": "a"}]})
    for f in ("final.mp4", "reelkit-props.json"):
        (ce / f).write_bytes(b"x")
    t = time.time()
    for p in list((ce / "src").glob("*.mp4")) + list((ce / "transcripts").glob("*.json")):
        os.utime(p, (t - 300, t - 300))
    for f, age in (("cut.json", 200), ("final.mp4", 100), ("reelkit-props.json", 50)):
        os.utime(ce / f, (t - age, t - age))
    s = run_script("longform.py", "status", "edit/talk", cwd=project)
    assert "cut ok, export ok" in s.stdout
    doc = json.loads((project / "edit" / "talk" / "clips.json").read_text(encoding="utf-8"))
    doc["clips"][0]["parts"][1]["to_words"] = "the whole method"  # a shorter second piece
    write_json(project / "edit" / "talk" / "clips.json", doc)
    check(project)
    run_script("longform.py", "mark", "edit/talk", "01", "--as", "approved", cwd=project)
    r = run_script("longform.py", "extract", "edit/talk", "01", "--pad", "1", cwd=project)
    assert "cut.json written anew" in r.stdout
    prev = list(ce.glob("cut.prev-*.json"))
    assert len(prev) == 1 and json.loads(prev[0].read_text(encoding="utf-8"))["speed"] == 1.1
    new = json.loads((ce / "cut.json").read_text(encoding="utf-8"))
    assert new["speed"] == 1.1 and "fix_at" not in new  # not seconds: kept; seconds of the old pieces: dropped
    assert new["ranges"][1]["end"] < cut["ranges"][1]["end"] - 1
    s = run_script("longform.py", "status", "edit/talk", cwd=project)
    assert "cut stale, export stale" in s.stdout
    r = run_script("longform.py", "extract", "edit/talk", "01", "--pad", "1", cwd=project)  # nothing changed now
    assert "cut.json kept as it was" in r.stdout and len(list(ce.glob("cut.prev-*.json"))) == 1


@needs_ffmpeg
def test_extract_refuses_unapproved_cards(series):
    project, _, _ = series
    cards(project, [{"id": "01", "parts": [{"from_words": "A weak candidate blames", "to_words": "and the boss.",
                                             "near": 30}]}])
    check(project)
    r = run_script("longform.py", "extract", "edit/talk", "01", cwd=project, check=False)
    assert r.returncode == 1 and "approves the list first" in r.stderr


# --- cut.py: fix_at / retime per source ----------------------------------------------------------------------------

def test_fix_at_with_a_source_touches_only_that_source():
    import cut
    fixes = cut.word_fixes([{"text": "um", "at": 1.0, "to": "", "source": "b"}], "fix_at", ("to",), {"a": {}, "b": {}})
    c = {"fix_at": fixes, "fix": {}}
    w = {"text": "um", "start": 1.0}
    assert cut.fixed(w, c, "a") == "um" and cut.fixed(w, c, "b") == ""
    with pytest.raises(SystemExit):
        cut.word_fixes([{"text": "um", "at": 1.0, "to": "", "source": "z"}], "fix_at", ("to",), {"a": {}})


# --- Remotion run folders ------------------------------------------------------------------------------------------

@pytest.fixture
def tmpbase(tmp_path, monkeypatch, project):
    base = tmp_path / "systemp"
    base.mkdir()
    monkeypatch.setattr(rc.tempfile, "gettempdir", lambda: str(base))
    return base


def test_run_folder_is_the_runs_temp_and_goes_away(tmpbase):
    with rc.remotion_tmp() as (env, args):
        d = Path(env["TEMP"])
        assert d.parent == tmpbase / "it-reelsmaker" and env["TMP"] == env["TMPDIR"] == str(d) and args == []
        (d / "remotion-webpack-bundle-x").mkdir()
        (d / "remotion-webpack-bundle-x" / "big.bin").write_bytes(b"0" * 1000)
    assert not d.exists()
    with pytest.raises(RuntimeError):
        with rc.remotion_tmp() as (env, _):
            d2 = Path(env["TEMP"])
            raise RuntimeError("the render failed")
    assert not d2.exists()


def test_public_of_only_this_videos_files(tmpbase, tmp_path):
    rem = tmp_path / "rem"
    for f in ("public/clip-01/video.mp4", "public/clip-01/inserts/b1.mp4", "public/brands/acme/logo.png",
              "public/clip-02/video.mp4", "public/video.mp4"):
        p = rem / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * 10)
    props = {"video": "clip-01/video.mp4", "brand": {"logo": "brands/acme/logo.png"}, "url": "https://a/b",
             "abs": "C:/x/y.mp4", "up": "../secret"}
    with rc.remotion_tmp(rem, props, "ReelKit") as (env, args):
        pub = Path(env["TEMP"]) / "public"
        assert args == [f"--public-dir={pub}"]
        got = sorted(p.relative_to(pub).as_posix() for p in pub.rglob("*") if p.is_file())
        assert got == ["brands/acme/logo.png", "clip-01/inserts/b1.mp4", "clip-01/video.mp4"]
    with rc.remotion_tmp(rem, props, "Reel4821") as (env, args):  # a per-video composition reads what it likes
        assert args == []


def test_cleanup_off_keeps_remotions_ways(tmpbase, project):
    write_json(project / "it-reelsmaker.json", {"temp_cleanup": False})
    with rc.remotion_tmp(None, None, None) as (env, args):
        assert env.get("TEMP") == os.environ.get("TEMP") and args == []
    assert not (tmpbase / "it-reelsmaker").exists()


def test_sweep_removes_old_and_pending_run_folders(tmpbase):
    root = tmpbase / "it-reelsmaker"
    old, young, pend = root / "r-1-old", root / "r-2-young", root / "r-3-held"
    for d in (old, young, pend):
        (d / "sub").mkdir(parents=True)
        (d / "sub" / "f").write_bytes(b"1" * 100)
    t = time.time() - rc.TMP_STALE_S - 60
    os.utime(old, (t, t))
    write_json(root / rc.TMP_PENDING, [str(pend)])
    freed = rc.sweep_tmp()
    assert not old.exists() and not pend.exists() and young.exists() and freed == 200
    assert not (root / rc.TMP_PENDING).exists()


def test_leftovers_are_listed_and_removed_only_on_yes(tmpbase, project, tmp_path):
    old = tmpbase / "puppeteer_dev_chrome_profile-abc"
    new = tmpbase / "remotion-webpack-bundle-new"
    other = tmpbase / "someone-elses-folder"
    for d in (old, new, other):
        d.mkdir()
        (d / "f").write_bytes(b"2" * 50)
    t = time.time() - 3 * 86400
    os.utime(old, (t, t))
    os.utime(other, (t, t))
    assert [p for p, _ in rc.remotion_leftovers()] == [old]
    env = {"TEMP": str(tmpbase), "TMP": str(tmpbase), "TMPDIR": str(tmpbase)}
    r = run_script("kit.py", "clean-temp", cwd=project, env=env)
    assert "1 folder(s)" in r.stdout and old.exists()
    r = run_script("kit.py", "clean-temp", "--yes", cwd=project, env=env)
    assert not old.exists() and new.exists() and other.exists() and "removed 1 folder" in r.stdout


def test_run_logged_keeps_everything_and_shows_progress(tmp_path, capsys):
    import kit
    code = ("import sys\nfor k in range(0, 101, 5):\n    print(f'Rendered {k}/100')\n"
            "print('Error: something broke', file=sys.stderr)\nprint('plain line')\n")
    log = tmp_path / "render.log"
    rc_ = kit.run_logged([sys.executable, "-c", code], tmp_path, dict(os.environ), log)
    out = capsys.readouterr().out
    assert rc_ == 0 and log.read_text(encoding="utf-8").count("Rendered") == 21
    assert out.count("rendered") == 6 and "Error: something broke" in out and "plain line" not in out
