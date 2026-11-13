"""Voice-over and the mixed video (core phase 1 of the no-speaker reels): the picture cut apart from the sound.

Requirements, in words:
- A voice note recorded on a phone (Opus in OGG, silence before the first word) is the sound of the video, and silent
  wide shots, other clips and photos are its picture: one cut.json with a "picture" block, one cut.py run, one
  final.mp4. No black video under the voice, no second project for the picture, no hand mux. The sound keeps its own
  records (segments, ranges, speech_mask --edl); the picture is the shots; the picture's own sound is not heard.
- A picture block may cover only a stretch of a talking-head video (head -> voice-over -> head): outside the block the
  picture is the speaker's own video at the seconds of its sound, as before; the sound is the same as without the block.
- Time is resolved before anything is encoded: whole frames, the block covered with no gap and no overlap, "until"
  wins over "dur", the last shot of a block runs to its end. A clip shorter than its shot is an error with numbers
  ("needs 4.00 s, has 2.50 s"), never a silent freeze or a repeat. The video may end on a stretch with no voice (a
  text punchline on the background): the sound is padded with silence to the picture's end.
- The picture's clips are prepared strictly: no freeze frame for a short clip, the video's own size and fps, a photo
  that should stand still stands still. B-roll keeps its old behaviour.
- Color is a property of the place: a source may carry its own look, merged over the video's look; the white balance
  measures the frames of the picture (never a voice file), and a reference box on one place writes into that place.
- Every stretch has a purpose (speaker, picture, graphic; a scene over a speaker is an insert): the rules that protect
  the speaker's face (the insert budget, two full scenes in a row, the full hook, the full-scene ceiling) do not hold
  over a voice-over picture. Python and the kit derive the purposes the same way.
- Strangers in a picture source: the person says where they are (or that they may be shown); a marked stretch that no
  opaque full scene hides for its whole length blocks the video.
- A long-form clip folder that holds a voice-over picture is refused before anything in it is touched.
- One motion layer: on a shot with its own move the virtual camera and the drift are off.
"""
import json
import os
import subprocess
import time

import pytest

from conftest import CORE, ffmpeg, make_video, needs_ffmpeg, probe_streams, run_script, write_json
from test_callouts import KIT, needs_node

KIT_ANCHOR = KIT / "kit" / "anchor.ts"

# the voice note: silence before the first word, phrases as 300 Hz bursts, a pause inside the first range
VOICE_BURSTS = [(0.6, 1.4), (1.8, 3.3), (4.6, 6.8)]
VOICE_WORDS = [("Wide", 0.6, 0.9), ("shots", 0.9, 1.4), ("at", 1.8, 2.0), ("the", 2.0, 2.2), ("sea", 2.5, 2.9),
               ("and", 4.6, 4.9), ("the", 4.9, 5.1), ("street", 5.1, 6.0), ("today", 6.2, 6.8)]
VOICE_RANGES = [(0.5, 3.5), (4.5, 7.0)]  # 3.0 + 2.5 = 5.5 s on the edit timeline at speed 1


def voice_note(path, dur=8.0):
    """A Telegram-style voice note: Opus in OGG, mono 48 kHz, silent before 0.6 s."""
    on = "+".join(f"between(t,{a},{b})" for a, b in VOICE_BURSTS)
    ffmpeg("-f", "lavfi", "-i", f"sine=f=300:d={dur}:sample_rate=48000,volume='0.5*({on})':eval=frame",
           "-ac", "1", "-c:a", "libopus", "-b:a", "32k", path)
    return path


def photo(path, color="green", w=800, h=1200):
    ffmpeg("-f", "lavfi", "-i", f"color=c={color}:size={w}x{h}", "-frames:v", "1", path)
    return path


def loud_clip(path, color, w, h, dur, rate):
    """A silent-looking wide shot that does have its own loud sound (a pool, a street): it must not be heard."""
    ffmpeg("-f", "lavfi", "-i", f"color=c={color}:size={w}x{h}:rate={rate}:duration={dur}",
           "-f", "lavfi", "-i", f"sine=frequency=2000:duration={dur}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", path)
    return path


def vo_project(project, picture=None, extra_sources=None):
    voice_note(project / "voice.ogg")
    loud_clip(project / "pool.mp4", "red", 720, 1280, 4.0, 25)
    photo(project / "sea.jpg")
    loud_clip(project / "street.mov", "blue", 1920, 1080, 4.0, 30)
    e = project / "edit" / "vo"
    write_json(e / "transcripts" / "voice.json",
               {"words": [{"text": t, "start": a, "end": b, "type": "word"} for t, a, b in VOICE_WORDS]})
    sources = {"voice": {"file": "voice.ogg"}, "pool": {"file": "pool.mp4"}, "sea": {"file": "sea.jpg"},
               "street": {"file": "street.mov"}, **(extra_sources or {})}
    if picture is None:
        picture = [{"from": "start", "to": "end", "shots": [
            {"source": "pool", "start": 1.0, "until": "word:sea#1", "what": "the pool, wide", "why": "the place"},
            {"source": "sea", "dur": 1.5, "move": "push", "what": "the sea", "why": "the word sea"},
            {"source": "street", "start": 0.5, "what": "the street", "why": "the word street"}]}]
    write_json(e / "cut.json", {"fps": 30, "sources": sources, "ranges": [{"source": "voice", "start": a, "end": b}
                                                                         for a, b in VOICE_RANGES],
                                "picture": picture, "balance": False})
    return e


def color_at(f, t):
    """The mean RGB of the frame at second t (the frame shrunk to one pixel)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(f), "-frames:v", "1", "-vf",
                        "scale=1:1:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return tuple(r.stdout[:3])


def frames_of(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames,r_frame_rate,width,height", "-of", "json", str(f)],
                       capture_output=True, text=True, check=True)
    s = json.loads(r.stdout)["streams"][0]
    return int(s["nb_read_frames"]), s["r_frame_rate"], s["width"], s["height"]


def loudness(f, t, d):
    """Peak level (dBFS) of the sound of f between t and t + d."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{t:.3f}", "-t", f"{d:.3f}", "-i", str(f), "-vn", "-af",
                        "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    line = next(x for x in r.stderr.splitlines() if "max_volume" in x)
    return float(line.split("max_volume:")[1].split("dB")[0])


def red(c):
    return c[0] > 150 and c[1] < 90 and c[2] < 90


def green(c):
    return c[1] > 90 and c[0] < 60 and c[2] < 60


def blue(c):
    return c[2] > 150 and c[0] < 90 and c[1] < 90


# --- one cut.json, one cut.py: a voice note over wide shots and a photo -------------------------------------------

@needs_ffmpeg
def test_a_voice_note_over_wide_shots_and_a_photo_is_one_rough_cut(project):
    e = vo_project(project)
    r = run_script("cut.py", "edit/vo", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    f = e / "final.mp4"
    n, rate, w, h = frames_of(f)
    assert (n, rate, w, h) == (165, "30/1", 1080, 1920)  # 5.5 s of voice, the video's size and fps
    st = probe_streams(f)
    assert abs(float(st["audio"]["duration"]) - 5.5) < 1 / 30 and abs(float(st["video"]["start_time"])) < 0.001
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    edl = json.loads((e / "edl.json").read_text(encoding="utf-8"))
    # the sound keeps its records: the voice's two ranges, its words on the edit timeline
    assert [(g["source"], g["src_start"], g["src_end"], g["out_start"], g["out_dur"]) for g in cap["segments"]] == \
        [("voice", 0.5, 3.5, 0.0, 3.0), ("voice", 4.5, 7.0, 3.0, 2.5)]
    assert [x["text"] for x in cap["words"]][:2] == ["Wide", "shots"] and cap["words"][0]["start"] == 0.1
    assert cap["duration"] == 5.5
    # the picture: three shots, the photo with conventional coordinates, cut where the word "sea" starts (2.0 s)
    assert cap["shots"] == [
        {"i": 0, "kind": "video", "source": "pool", "src_start": 1.0, "src_end": 3.0, "speed": 1.0, "out_start": 0.0,
         "out_dur": 2.0, "move": "none", "look": None},
        {"i": 1, "kind": "photo", "source": "sea", "src_start": 0.0, "src_end": 1.5, "speed": 1.0, "out_start": 2.0,
         "out_dur": 1.5, "move": "push", "look": None},
        {"i": 2, "kind": "video", "source": "street", "src_start": 0.5, "src_end": 2.5, "speed": 1.0, "out_start": 3.5,
         "out_dur": 2.0, "move": "none", "look": None}]
    assert edl["shots"] == cap["shots"] and cap.get("picture_id")
    # speech_mask --edl opens only the sound: the picture's files are listed apart
    assert list(edl["sources"]) == ["voice"] and set(edl["picture_sources"]) == {"pool", "sea", "street"}
    assert [r["source"] for r in edl["ranges"]] == ["voice", "voice"]
    # what is on screen: the pool, then the sea photo, then the street (a horizontal clip covered into 9:16)
    assert red(color_at(f, 1.0)) and green(color_at(f, 2.75)) and blue(color_at(f, 4.5))
    # the wide shots' own loud sound is not in the video: in the pause of the voice (0.9-1.3 s) it is quiet
    assert loudness(f, 0.95, 0.3) < -40
    assert loudness(f, 0.2, 0.5) > -35  # and the voice itself is there (the fixture's tone peaks at -24 dBFS)


@needs_ffmpeg
def test_a_dry_run_lists_the_picture_shots_and_encodes_nothing(project):
    e = vo_project(project)
    r = run_script("cut.py", "edit/vo", "--dry-run", cwd=project)
    assert "picture: 3 shots" in r.stdout and "sea" in r.stdout, r.stdout
    assert not (e / "final.mp4").exists() and not (e / "clips").exists()


# --- a picture block over a stretch of a talking head -------------------------------------------------------------

HEAD_WORDS = [("Hello", 0.5, 0.9), ("recruiter", 1.0, 1.6), ("all", 2.0, 2.3), ("gap", 3.05, 3.2), ("tail", 4.5, 5.2),
              ("end", 6.0, 6.4)]


def head_project(project, picture):
    make_video(project / "head.mov", 720, 1280, 8.0, color="blue")  # the speaker, with a 440 Hz tone as the voice
    loud_clip(project / "pool.mp4", "red", 720, 1280, 4.0, 25)
    e = project / "edit" / "mix"
    write_json(e / "transcripts" / "head.json",
               {"words": [{"text": t, "start": a, "end": b, "type": "word"} for t, a, b in HEAD_WORDS]})
    cut = {"fps": 30, "sources": {"main": {"file": "head.mov"}, "pool": {"file": "pool.mp4"}},
           "ranges": [{"source": "main", "start": 0.4, "end": 3.0}, {"source": "main", "start": 4.4, "end": 6.6}],
           "balance": False, "level": False}
    if picture is not None:
        cut["picture"] = picture
    write_json(e / "cut.json", cut)
    return e


@needs_ffmpeg
def test_a_picture_block_over_part_of_a_talking_head_keeps_the_speaker_around_it(project):
    e = head_project(project, None)
    run_script("cut.py", "edit/mix", cwd=project)
    plain = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    head_project(project, [{"from": "word:all#1", "to": "word:tail#1",
                            "shots": [{"source": "pool", "start": 0.0, "what": "the pool", "why": "the voice-over"}]}])
    r = run_script("cut.py", "edit/mix", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    # the sound is the same as without the block
    assert cap["segments"] == plain["segments"] and cap["words"] == plain["words"] and cap["duration"] == 4.8
    # the picture: the speaker to 1.6 s ("all"), the pool to 2.7 s ("tail"), the speaker again at its own seconds
    assert [(g["i"], g["kind"], g["source"], g["src_start"], g["src_end"], g["out_start"], g["out_dur"])
            for g in cap["shots"]] == [(0, "video", "main", 0.4, 2.0, 0.0, 1.6), (1, "video", "pool", 0.0, 1.1, 1.6, 1.1),
                                       (2, "video", "main", 4.5, 6.6, 2.7, 2.1)]
    f = e / "final.mp4"
    assert frames_of(f)[:2] == (144, "30/1")
    assert blue(color_at(f, 0.8)) and red(color_at(f, 2.2)) and blue(color_at(f, 3.5))
    st = probe_streams(f)
    assert abs(float(st["audio"]["duration"]) - 4.8) < 1 / 30


# --- time is resolved before anything is encoded ------------------------------------------------------------------

@needs_ffmpeg
def test_a_clip_shorter_than_its_shot_is_an_error_with_numbers_before_any_encoding(project):
    e = vo_project(project, picture=[{"from": "start", "to": "end", "shots": [
        {"source": "pool", "start": 1.5, "dur": 4.0}, {"source": "sea"}]}])
    for args in (("--dry-run",), ()):
        r = run_script("cut.py", "edit/vo", *args, cwd=project, check=False)
        assert r.returncode != 0
        assert "needs 4.00 s" in r.stderr and "2.50 s" in r.stderr and "pool.mp4" in r.stderr, r.stderr
    assert not (e / "final.mp4").exists() and not (e / "clips").exists() and not (e / "captions.json").exists()


def picture_c(blocks, sources=None, fps=30):
    """A loaded cut list for cut_picture.resolve: one 6.0 s sound segment of a talking head, a 10 s clip, a photo."""
    from pathlib import Path
    srcs = sources or {"main": {"path": Path("head.mov"), "speed": 1.0, "info": {"w": 1080, "h": 1920, "dur": 20.0,
                                                                                 "has_audio": True}},
                       "clip": {"path": Path("clip.mp4"), "speed": 1.0, "info": {"w": 1080, "h": 1920, "dur": 10.0}},
                       "pic": {"path": Path("pic.jpg"), "speed": 1.0, "info": {"w": 800, "h": 1200, "dur": 0.04}}}
    return {"fps": fps, "sources": srcs, "picture": blocks}


SEG = [{"i": 0, "source": "main", "src_start": 10.0, "src_end": 16.0, "out_start": 0.0, "out_dur": 6.0, "speed": 1.0}]
WORDS = [{"text": "one", "start": 1.0, "end": 1.4}, {"text": "two", "start": 2.5, "end": 2.9},
         {"text": "one", "start": 4.0, "end": 4.4}]


def resolved(blocks, segments=SEG):
    import cut_picture
    return cut_picture.resolve(picture_c(blocks), segments, WORDS, 6.0)


def spans(shots):
    return [(g["kind"], g["source"], g["out_start"], g["out_dur"]) for g in shots]


def test_the_picture_timeline_is_whole_frames_with_no_gap_and_no_overlap():
    # until wins over dur; the last shot runs to the block's end; a word anchor is the start of that word (its n-th)
    shots, total = resolved([{"from": 1.01, "to": "word:one#2", "shots": [
        {"source": "clip", "dur": 0.5, "until": "word:two#1"}, {"source": "pic"}]}])
    assert spans(shots) == [("video", "main", 0.0, 1.0), ("video", "clip", 1.0, 1.5), ("photo", "pic", 2.5, 1.5),
                            ("video", "main", 4.0, 2.0)]
    assert total == 6.0 and [g["i"] for g in shots] == [0, 1, 2, 3]
    # the speaker's shots keep the seconds of their sound; a clip's window is start + its length at its speed
    assert (shots[0]["src_start"], shots[0]["src_end"], shots[3]["src_start"], shots[3]["src_end"]) == (10.0, 11.0, 14.0, 16.0)
    assert (shots[1]["src_start"], shots[1]["src_end"]) == (0.0, 1.5)
    assert (shots[2]["src_start"], shots[2]["src_end"]) == (0.0, 1.5)  # a photo: conventional coordinates
    # whole frames: 0.333 s at 30 fps is 10 frames, the next shot starts on that frame
    shots, _ = resolved([{"from": 0, "to": 1, "shots": [{"source": "clip", "dur": 0.333}, {"source": "pic"}]}])
    assert spans(shots)[:2] == [("video", "clip", 0.0, 0.333), ("photo", "pic", 0.333, 0.667)]


@pytest.mark.parametrize("blocks, msg", [
    ([{"from": 1, "to": 3, "shots": [{"source": "clip"}, {"source": "pic"}]}], "only the last shot"),
    ([{"from": 1, "to": 3, "shots": [{"source": "clip", "dur": 1.0}, {"source": "pic", "dur": 1.5}]}], "0.50 s past"),
    ([{"from": 1, "to": 3, "shots": [{"source": "clip", "dur": 1.0}, {"source": "pic", "dur": 0.5}]}], "0.50 s of the block"),
    ([{"from": 1, "to": 3, "shots": [{"source": "pic"}]}, {"from": 2.5, "to": 4, "shots": [{"source": "pic"}]}], "overlap"),
    ([{"from": 3, "to": 2, "shots": [{"source": "pic"}]}], "after its start"),
    ([{"from": 6.5, "to": 8, "shots": [{"source": "pic"}]}], "nothing on screen"),
    ([{"from": 5, "to": 8, "shots": [{"source": "pic"}]}, {"from": 8, "to": 9, "shots": [{"source": "pic"}]}], "only the last"),
    ([{"from": 1, "to": 3, "shots": [{"source": "nope"}]}], "nope"),
    ([{"from": 1, "to": 3, "shots": [{"source": "clip", "move": "zoom"}]}], "move"),
    ([{"from": 1, "to": 3, "shots": []}], "no shots"),
])
def test_a_picture_block_that_does_not_cover_its_time_exactly_is_refused(blocks, msg):
    import cut_picture
    with pytest.raises(cut_picture.PictureError) as x:
        resolved(blocks)
    assert msg in str(x.value), str(x.value)


def test_a_sound_only_stretch_with_no_picture_block_is_the_background():
    from pathlib import Path
    srcs = {"voice": {"path": Path("v.ogg"), "speed": 1.0, "info": {"w": None, "h": None, "dur": 9.0, "has_audio": True}},
            "pic": {"path": Path("pic.jpg"), "speed": 1.0, "info": {"w": 800, "h": 1200, "dur": 0.04}}}
    import cut_picture
    seg = [{**SEG[0], "source": "voice", "src_start": 1.0, "src_end": 7.0}]
    shots, _ = cut_picture.resolve(picture_c([{"from": 2, "to": 4, "shots": [{"source": "pic"}]}], srcs), seg, WORDS, 6.0)
    assert spans(shots) == [("fill", None, 0.0, 2.0), ("photo", "pic", 2.0, 2.0), ("fill", None, 4.0, 2.0)]


@needs_ffmpeg
def test_a_voice_ending_runs_into_a_text_tail_without_a_fake_sound_source(project):
    # the voice ends at 5.5 s; a text punchline on the style's background runs to 7.5 s over silence (music later)
    e = vo_project(project, picture=[{"from": "start", "to": "end", "shots": [{"source": "pool", "start": 0.0, "dur": 2.0},
                                                                              {"source": "sea"}]},
                                     {"from": "end", "to": 7.5, "shots": [{"fill": True, "what": "the punchline's field",
                                                                           "why": "the voice is over"}]}])
    run_script("cut.py", "edit/vo", cwd=project)
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    assert cap["duration"] == 7.5 and sum(g["out_dur"] for g in cap["segments"]) == 5.5
    assert spans(cap["shots"])[-1] == ("fill", None, 5.5, 2.0)
    f = e / "final.mp4"
    st = probe_streams(f)
    assert frames_of(f)[0] == 225 and abs(float(st["audio"]["duration"]) - 7.5) < 1 / 30
    assert loudness(f, 5.8, 1.5) < -60  # the tail is silent: no sound source behind it


# --- the strict preparation of a picture shot ---------------------------------------------------------------------

@needs_ffmpeg
def test_a_picture_shot_is_prepared_strictly_and_b_roll_keeps_its_freeze(tmp_path):
    import footage
    clip = make_video(tmp_path / "c.mp4", 720, 1280, 3.0, audio=False, rate=25)
    # B-roll as before: a 0.3 s shortfall is filled with a freeze of the last frame
    info = footage.prepare(clip, tmp_path / "b.mp4", 3.3)
    assert info["dur"] >= 3.3 - 0.05 and (info["w"], info["h"]) == (1080, 1920)
    # a picture shot: no freeze, the shortfall is an error
    with pytest.raises(footage.ShortSource):
        footage.prepare(clip, tmp_path / "s.mp4", 3.3, strict=True)
    assert not (tmp_path / "s.mp4").exists()
    # the video's own geometry and fps (a horizontal framed talk at 25 fps), exactly its frames
    footage.prepare(clip, tmp_path / "h.mp4", 2.0, strict=True, size=(1920, 1080), fps=25)
    assert frames_of(tmp_path / "h.mp4") == (50, "25/1", 1920, 1080)


@needs_ffmpeg
def test_a_photo_stands_still_or_moves_as_its_shot_says(tmp_path):
    import footage
    pic = tmp_path / "p.png"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=800x1200", "-frames:v", "1", pic)

    def first_last(f):
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-vf", "scale=54:96", "-f", "rawvideo", "-pix_fmt",
                            "gray", "-"], capture_output=True, check=True)
        n = 54 * 96
        return r.stdout[:n], r.stdout[-n:]

    for move, same in (("still", True), ("none", True), ("push", False), ("pull", False), ("pan", False)):
        out = tmp_path / f"{move}.mp4"
        footage.prepare(pic, out, 1.0, strict=True, move=move)
        a, b = first_last(out)
        diff = sum(abs(x - y) for x, y in zip(a, b)) / len(a)
        assert (diff < 1.0) == same, (move, diff)
    # B-roll's photo keeps its slow push-in
    footage.prepare(pic, tmp_path / "broll.mp4", 1.0)
    a, b = first_last(tmp_path / "broll.mp4")
    assert sum(abs(x - y) for x, y in zip(a, b)) / len(a) > 1.0


# --- color per source ---------------------------------------------------------------------------------------------

def luma(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


@needs_ffmpeg
def test_each_place_keeps_its_own_color_over_the_videos_look(project):
    voice_note(project / "voice.ogg")
    for name in ("office", "sunset"):
        make_video(project / f"{name}.mp4", 720, 1280, 4.0, audio=False, color="0x808080")
    e = project / "edit" / "col"
    write_json(e / "transcripts" / "voice.json",
               {"words": [{"text": t, "start": a, "end": b, "type": "word"} for t, a, b in VOICE_WORDS]})
    write_json(e / "cut.json", {
        "fps": 30, "balance": False, "look": {"grade": "eq=brightness=-0.2"},
        "sources": {"voice": {"file": "voice.ogg"}, "office": {"file": "office.mp4"},
                    "sunset": {"file": "sunset.mp4", "look": {"grade": "eq=brightness=0.3"}}},
        "ranges": [{"source": "voice", "start": 0.5, "end": 3.5}],
        "picture": [{"from": "start", "to": "end", "shots": [{"source": "office", "dur": 1.5}, {"source": "sunset"}]}]})
    run_script("cut.py", "edit/col", cwd=project)
    f = e / "final.mp4"
    office, sunset = luma(color_at(f, 0.7)), luma(color_at(f, 2.2))
    assert office < 100 < 160 < sunset, (office, sunset)  # the video's look on one place, the place's own on the other
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    assert cap["shots"][0]["look"] is None and isinstance(cap["shots"][1]["look"], str)


@needs_ffmpeg
def test_the_white_balance_measures_the_picture_and_a_reference_writes_into_its_place(project):
    e = vo_project(project)
    photo(project / "sea.jpg", color="0x9a8070")  # a warm gray wall
    r = run_script("balance.py", "edit/vo", "--json", "--frames", "4", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout[r.stdout.index("{"):])
    assert out["frames"] and {n for n, _ in out["frames"]} <= {"pool", "sea", "street"}, out["frames"]
    # an eyedropper on the wall of the sea photo: the correction belongs to that place, not to the whole video
    r = run_script("balance.py", "edit/vo", "--ref", "sea:0,100,100,200,200", "--write", cwd=project, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    cut = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    assert "colorchannelmixer" in cut["sources"]["sea"]["look"]["correct"], cut
    assert "correct" not in (cut.get("look") or {})


def test_a_balance_mark_follows_the_picture_and_old_marks_stay_valid():
    import balance
    old = {"sources": {"main": {"file": "a.mov"}}, "ranges": [{"source": "main", "start": 1.0, "end": 2.0}]}
    pic = dict(old, picture=[{"from": 0, "to": 1, "shots": [{"source": "main", "start": 5.0}]}])
    moved = dict(old, picture=[{"from": 0, "to": 1, "shots": [{"source": "main", "start": 6.0}]}])
    assert balance.frames_key(pic) != balance.frames_key(old) and balance.frames_key(pic) != balance.frames_key(moved)
    # a source's own look is measured on its own: it does not stale the video's mark
    own = dict(pic, sources={"main": {"file": "a.mov", "look": {"correct": "eq=gamma=1.1"}}})
    assert balance.frames_key(own)[0] == balance.frames_key(pic)[0]


# --- purposes and where each rule applies -------------------------------------------------------------------------

MIXED = {"duration": 16.0,
         "segments": [{"i": 0, "source": "main", "src_start": 2.0, "src_end": 18.0, "out_start": 0.0, "out_dur": 16.0,
                       "speed": 1.0}],
         "shots": [{"i": 0, "kind": "video", "source": "main", "src_start": 2.0, "src_end": 6.0, "speed": 1.0,
                    "out_start": 0.0, "out_dur": 4.0, "move": "none", "look": None},
                   {"i": 1, "kind": "video", "source": "pool", "src_start": 0.0, "src_end": 6.0, "speed": 1.0,
                    "out_start": 4.0, "out_dur": 6.0, "move": "still", "look": None},
                   {"i": 2, "kind": "fill", "source": None, "src_start": 0.0, "src_end": 2.0, "speed": 1.0,
                    "out_start": 10.0, "out_dur": 2.0, "move": "none", "look": None},
                   {"i": 3, "kind": "video", "source": "main", "src_start": 14.0, "src_end": 18.0, "speed": 1.0,
                    "out_start": 12.0, "out_dur": 4.0, "move": "none", "look": None}],
         "words": []}


def faster():
    """MIXED with its last shot from the sound's own second, but played at x2: the picture runs ahead of the voice."""
    c = json.loads(json.dumps(MIXED))
    c["shots"][3].update(speed=2.0, src_end=22.0)
    return c


def past_its_piece():
    """Two sound pieces (2-14 s, then 30-34 s of the source); one shot from 10 s runs on to 18 s across their join."""
    seg = MIXED["segments"][0]
    return {"duration": 16.0,
            "segments": [dict(seg, src_end=14.0, out_dur=12.0),
                         dict(seg, i=1, src_start=30.0, src_end=34.0, out_start=12.0, out_dur=4.0)],
            "shots": [dict(MIXED["shots"][0], src_end=10.0, out_dur=8.0),
                      dict(MIXED["shots"][0], i=1, src_start=10.0, src_end=18.0, out_start=8.0, out_dur=8.0)],
            "words": []}


def test_every_stretch_has_a_purpose_derived_from_the_voice_and_the_picture():
    import pic_track as pt
    assert pt.purposes(MIXED, "on_camera") == [(0.0, 4.0, "speaker"), (4.0, 10.0, "picture"), (10.0, 12.0, "graphic"),
                                               (12.0, 16.0, "speaker")]
    # a speaker's own video at other seconds than its sound is not the speaker speaking
    moved = json.loads(json.dumps(MIXED))
    moved["shots"][3]["src_start"], moved["shots"][3]["src_end"] = 30.0, 34.0
    assert pt.purposes(moved, "on_camera")[3][2] == "picture"
    # review of PR #50: the same file from the same second at another speed drifts off the voice at once, and a shot
    # that runs on past the end of its sound piece shows other seconds than the ones heard: neither is the speaker
    assert pt.purposes(faster(), "on_camera")[3][2] == "picture"
    assert pt.purposes(past_its_piece(), "on_camera")[1][2] == "picture"
    # the voice off camera: nobody speaks in the frame
    assert [p for _, _, p in pt.purposes(MIXED, "off_camera")] == ["picture", "picture", "graphic", "picture"]
    # a cut made before the picture track: all of it is the speaker
    old = {"duration": 16.0, "segments": MIXED["segments"]}
    assert pt.purposes(old, "on_camera") == [(0.0, 16.0, "speaker")]
    # the rules that protect the speaker's face hold only over the speaker; reading, tone and facts hold everywhere
    for rule in ("coverage", "full_in_a_row", "full_scenes_max", "hook_full", "face_visible"):
        assert pt.RULES[rule] == {"speaker"}, rule
    for rule in ("reading", "tone", "facts", "no_slideshow"):
        assert pt.RULES[rule] == {"speaker", "picture", "graphic"}, rule
    assert pt.RULES["strangers"] == {"picture"}
    assert pt.speaker_seconds(pt.purposes(MIXED, "on_camera"), 3.0, 13.0) == pytest.approx(2.0)


@needs_node
def test_the_kit_derives_the_same_purposes(tmp_path):
    import pic_track as pt
    moved = json.loads(json.dumps(MIXED))
    moved["shots"][3]["src_start"] = 30.0
    cases = [[MIXED, "on_camera"], [MIXED, "off_camera"], [moved, "on_camera"],
             [{"duration": 16.0, "segments": MIXED["segments"]}, None], [faster(), "on_camera"],
             [past_its_piece(), "on_camera"]]
    data = tmp_path / "cases.json"
    data.write_text(json.dumps(cases), encoding="utf-8")
    code = ("const m = await import(process.argv[1]); const fs = await import('node:fs');"
            "const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));"
            "console.log(JSON.stringify(cases.map(([c, v]) => [m.picturePurposes(c, v).map((x) => [x.start, x.end, x.purpose]),"
            " [1, 5, 11, 13].map((t) => m.onGraphic(m.picShots(c), t))])));")
    r = subprocess.run(["node", "--input-type=module", "-e", code, KIT_ANCHOR.as_uri(), str(data)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    for (c, v), (kit, graphic) in zip(cases, got):
        assert [tuple(x) for x in kit] == pt.purposes(c, v or "on_camera")
        assert graphic == [pt.on_graphic(pt.pic_shots(c), t) for t in (1, 5, 11, 13)]


def plan_project(project, shots, voice="on_camera", sources=None):
    """A rough cut whose captions.json carries these picture shots over one 16 s sound segment, and its plan."""
    e = project / "edit" / "p"
    words = []
    for k, t in enumerate([0.3, 2.0, 4.5, 6.0, 8.0, 10.5, 12.5, 14.5]):
        words.append({"text": f"word{k}", "start": t, "end": t + 0.4, "seg": 0, "src": t + 2.0})
    write_json(e / "captions.json", {**MIXED, "shots": shots, "words": words})
    write_json(e / "cut.json", {"sources": sources or {"main": {"file": "head.mov"}, "pool": {"file": "pool.mp4",
                                                                                              "strangers": []}},
                                "ranges": [{"source": "main", "start": 2.0, "end": 18.0}]})
    write_json(project / "brands" / "acme" / "brand.json",
               {"name": "Acme", "slug": "acme", "schema": 2, "tone": {"preset": "expert", "overrides": {}},
                "colors": {"bg": "#0B3D2E", "accent": "#F2C14E", "text": "#FFFFFF"}})
    write_json(e / "reel.json", {"brand": "acme", "use_scenes": True, "voice": voice})
    run_script("visual_plan.py", "init", "edit/p", "--force", cwd=project)
    return e


def scene(project, typ, at, dur, *lines, extra=()):
    run_script("visual_plan.py", "add", "edit/p", "--kind", "scene", "--type", typ, "--mode", "full", "--at", str(at),
               "--dur", str(dur), "--lines", *lines, "--source", "agent", "--what", f"a {typ}",
               "--why", "the voice-over's point", *(("--variant", "slam") if typ == "hook" else ()), *extra, cwd=project)


SPEAKER_ALL = [dict(MIXED["shots"][0], src_end=18.0, out_dur=16.0)]
PICTURE_FIRST = [dict(MIXED["shots"][1], out_start=0.0, out_dur=10.0, src_end=10.0),
                 dict(MIXED["shots"][3], src_start=12.0, out_start=10.0, out_dur=6.0, i=1)]


@needs_ffmpeg
def test_full_scenes_over_a_voice_over_picture_are_not_held_to_the_speakers_rules(project):
    def issues():
        r = run_script("visual_plan.py", "validate", "edit/p", cwd=project, check=False)
        return r.stdout + r.stderr

    plan_project(project, PICTURE_FIRST)
    scene(project, "hook", 0.3, 2.6, "Wide shots", "and a sea")
    scene(project, "quote", 3.2, 2.4, "The place speaks")
    scene(project, "quote", 5.8, 2.6, "For itself")
    out = issues()
    for msg in ("full hook", "two full scenes in a row", "inserts take", "full scenes 3 >"):
        assert msg not in out, (msg, out)
    # the same scenes over the speaker keep every rule that protects the face
    plan_project(project, SPEAKER_ALL)
    scene(project, "hook", 0.3, 2.6, "Wide shots", "and a sea")
    scene(project, "quote", 3.2, 2.4, "The place speaks")
    scene(project, "quote", 5.8, 2.6, "For itself")
    out = issues()
    for msg in ("full hook", "two full scenes in a row", "inserts take"):
        assert msg in out, (msg, out)


# --- strangers ----------------------------------------------------------------------------------------------------

STRANGER_SHOTS = [dict(MIXED["shots"][0]), dict(MIXED["shots"][1], src_start=0.5, src_end=6.5, move="none"),
                  dict(MIXED["shots"][3], i=2, src_start=12.0, src_end=18.0, out_start=10.0, out_dur=6.0)]


@needs_ffmpeg
def test_strangers_in_a_picture_source_block_the_video_until_a_full_scene_hides_them(project):
    def run():
        return run_script("visual_plan.py", "validate", "edit/p", cwd=project, check=False)

    # the person has not said whether strangers are in the pool shot: that is asked before anything else
    plan_project(project, STRANGER_SHOTS, sources={"main": {"file": "head.mov"}, "pool": {"file": "pool.mp4"}})
    r = run()
    assert r.returncode == 1 and "strangers" in r.stdout and "pool" in r.stdout, r.stdout
    # "may be shown": nothing to hide
    plan_project(project, STRANGER_SHOTS, sources={"main": {"file": "head.mov"}, "pool": {"file": "pool.mp4",
                                                                                          "strangers": "ok"}})
    assert "strangers" not in run().stdout
    # strangers at source seconds 1.5-2.5 of the pool: on screen 5.0-6.0 s of the video
    plan_project(project, STRANGER_SHOTS, sources={"main": {"file": "head.mov"},
                                                   "pool": {"file": "pool.mp4", "strangers": [[1.5, 2.5]]}})
    r = run()
    assert r.returncode == 1 and "5.00-6.00" in r.stdout and "strangers" in r.stdout, r.stdout
    # a full scene that only half covers them still blocks it
    scene(project, "quote", 5.4, 2.0, "Half of it", extra=("--transition", "cut", "--transition-out", "cut"))
    r = run()
    assert r.returncode == 1 and "5.00-6.00" in r.stdout, r.stdout
    # a full scene from before to after, entering and leaving by a cut, hides them
    plan = json.loads((project / "edit" / "p" / "visual_plan.json").read_text(encoding="utf-8"))
    sc = plan["inserts"][0]
    sc["start"], sc["dur"] = 4.5, 2.0
    write_json(project / "edit" / "p" / "visual_plan.json", plan)
    r = run()
    assert "strangers" not in r.stdout, r.stdout


# --- long form -----------------------------------------------------------------------------------------------------

@needs_ffmpeg
def test_long_form_extract_refuses_a_voice_over_clip_before_touching_its_folder(project):
    from test_longform import SENTENCES, cards, check, words_of
    make_video(project / "talk.mp4", w=320, h=180, dur=50)
    run_script("longform.py", "init", "edit/talk", "talk.mp4", cwd=project)
    words, _ = words_of(SENTENCES)
    write_json(project / "edit" / "talk" / "transcripts" / "talk.json",
               {"language_code": "en", "text": "", "words": words, "source": "talk.mp4", "timeline": "video"})
    two = [{"from_words": "A weak candidate blames", "to_words": "and the boss.", "near": 30},
           {"from_words": "That is the whole method", "to_words": "works every time.", "near": 47}]
    cards(project, [{"id": "01", "parts": two}])
    check(project)
    run_script("longform.py", "mark", "edit/talk", "01", "--as", "approved", cwd=project)
    run_script("longform.py", "extract", "edit/talk", "01", "--pad", "1", cwd=project)
    ce = project / "edit" / "talk-01"
    cut = json.loads((ce / "cut.json").read_text(encoding="utf-8"))
    cut["picture"] = [{"from": 1.0, "to": 2.0, "shots": [{"source": "a", "start": 0.0}]}]
    write_json(ce / "cut.json", cut)
    before = {p.relative_to(ce).as_posix(): p.read_bytes() for p in ce.rglob("*") if p.is_file()}
    doc = json.loads((project / "edit" / "talk" / "clips.json").read_text(encoding="utf-8"))
    doc["clips"][0]["parts"][1]["to_words"] = "the whole method"  # new pieces: extract would cut them again
    write_json(project / "edit" / "talk" / "clips.json", doc)
    check(project)
    run_script("longform.py", "mark", "edit/talk", "01", "--as", "approved", cwd=project)
    r = run_script("longform.py", "extract", "edit/talk", "01", "--pad", "1", cwd=project, check=False)
    assert r.returncode != 0 and "picture" in r.stderr and "not supported" in r.stderr, r.stdout + r.stderr
    after = {p.relative_to(ce).as_posix(): p.read_bytes() for p in ce.rglob("*") if p.is_file()}
    assert after == before  # the pieces, their transcripts and cut.json as they were, no cut.prev


# --- one motion layer ---------------------------------------------------------------------------------------------

MOVED = {"duration": 6.0, "segments": [{"i": 0, "source": "main", "src_start": 0.0, "src_end": 6.0, "out_start": 0.0,
                                        "out_dur": 6.0, "speed": 1.0}],
         "shots": [{"i": 0, "kind": "video", "source": "main", "src_start": 0.0, "src_end": 2.0, "speed": 1.0,
                    "out_start": 0.0, "out_dur": 2.0, "move": "none", "look": None},
                   {"i": 1, "kind": "photo", "source": "sea", "src_start": 0.0, "src_end": 2.0, "speed": 1.0,
                    "out_start": 2.0, "out_dur": 2.0, "move": "push", "look": None},
                   {"i": 2, "kind": "video", "source": "main", "src_start": 4.0, "src_end": 6.0, "speed": 1.0,
                    "out_start": 4.0, "out_dur": 2.0, "move": "none", "look": None}],
         "words": []}


def test_the_camera_is_off_on_a_shot_with_its_own_move(project):
    import vp_camera as vc
    import vp_callouts as cl
    e = project / "edit" / "cam"
    write_json(e / "captions.json", MOVED)
    write_json(e / "camera.json", {"shots": [{"at": 0, "z": 1.3, "cx": 540, "cy": 900, "drift": 0.05},
                                             {"at": 3.0, "z": 1.5, "cx": 500, "cy": 800}]})
    shots = vc.camera_shots(e, {"segments": []}, MOVED, quiet=True)
    # the push-in of the photo is the only motion from 2 to 4 s; after it the camera comes back where it was
    assert [(s["t"], s["z"]) for s in shots] == [(0.0, 1.3), (2.0, 1.0), (4.0, 1.5)]
    assert vc.camera_at(shots, 3.0, 6.0) == (1.0, 540.0, 960.0)
    # the template's drift: off on the moved shot, as before on the others
    assert cl.drift_zoom(MOVED["shots"], 3.0) == 1.0 and cl.drift_zoom(MOVED["shots"], 1.0) > 1.0


@needs_node
def test_the_kit_keeps_the_drift_off_on_a_moved_shot(tmp_path):
    import vp_callouts as cl
    data = tmp_path / "c.json"
    data.write_text(json.dumps(MOVED), encoding="utf-8")
    code = ("const m = await import(process.argv[1]); const fs = await import('node:fs');"
            "const c = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));"
            "console.log(JSON.stringify([1.0, 3.0, 5.0].map((t) => m.driftZoom(m.picShots(c), t))));")
    r = subprocess.run(["node", "--input-type=module", "-e", code, KIT_ANCHOR.as_uri(), str(data)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == pytest.approx([cl.drift_zoom(MOVED["shots"], t) for t in (1.0, 3.0, 5.0)])
    assert json.loads(r.stdout)[1] == 1.0


# --- the sound-only branch and the sound-only files -----------------------------------------------------------------

@needs_ffmpeg
def test_a_narration_cut_writes_its_picture_track_as_the_background(project):
    from test_scenes_voice import voice_project
    e = voice_project(project)
    run_script("cut.py", "edit/v1", cwd=project)
    cap = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    assert [g["kind"] for g in cap["shots"]] == ["fill"] * len(cap["segments"])
    assert [(g["out_start"], g["out_dur"]) for g in cap["shots"]] == [(g["out_start"], g["out_dur"]) for g in cap["segments"]]


@needs_ffmpeg
def test_a_recording_with_cover_art_is_a_sound_only_source(tmp_path):
    from reels_common import probe
    art = photo(tmp_path / "art.jpg", "red", 300, 300)
    ffmpeg("-f", "lavfi", "-i", "sine=f=300:d=3:sample_rate=48000", "-i", art, "-map", "0:a", "-map", "1:v",
           "-c:a", "aac", "-c:v", "mjpeg", "-disposition:v", "attached_pic", tmp_path / "memo.m4a")
    info = probe(tmp_path / "memo.m4a")
    assert info["w"] is None and info["has_audio"] and info["dur"] > 2.9
