"""defects.py (picture defects on the rough cut): the classification of face samples into turned / blur / lost /
stranger runs. No model and no video here: the samples are built by hand, as defects.scan() returns them."""
import pytest

import defects as df

STEP = 0.1
SPEAKER = (200, 300, 140, 190)  # x, y, w, h of the speaker's face in a 540x960 frame


def face(box=SPEAKER, score=0.93, turn=0.1, tilt=0.62, eyes=0.46, sharp=100.0):
    """A face as scan() gives it: [x, y, w, h, score, right eye, left eye, nose, right mouth, left mouth, sharpness];
    turn and tilt in eye distances, eyes = the eye distance in face widths."""
    x, y, w, h = box
    iod = eyes * w
    mx, my = x + w / 2, y + 0.4 * h
    rex, lex = mx - iod / 2, mx + iod / 2
    nx, ny = mx + turn * iod, my + tilt * iod
    return [x, y, w, h, score, rex, my, lex, my, nx, ny, mx - iod / 2, my + 1.2 * iod, mx + iod / 2, my + 1.2 * iod,
            sharp]


def data(n, at=lambda i: [face()]):
    """n samples every STEP seconds; at(i) -> the faces of sample i."""
    return {"step": STEP, "samples": [{"t": round(i * STEP, 3), "faces": at(i)} for i in range(n)]}


def within(i, a, b):
    return a <= i * STEP + 1e-9 < b


def kinds(out):
    return [(d["kind"], d["start"], d["end"]) for d in out]


def test_a_turned_head_long_enough_is_one_defect():
    d = data(100, lambda i: [face(turn=0.9 if within(i, 3.0, 4.0) else 0.1)])
    out, info = df.find(d, [])
    assert kinds(out) == [("turned", 3.0, 4.0)]
    assert out[0]["id"] == "d01" and info["on_camera"]


def test_a_glance_shorter_than_the_minimum_is_ignored():
    short = df.MIN_S["turned"] - 2 * STEP
    d = data(100, lambda i: [face(turn=0.9 if within(i, 3.0, 3.0 + short) else 0.1)])
    assert df.find(d, [])[0] == []


def test_looking_down_and_turning_sideways_with_the_nose_centred_are_turned_too():
    down = data(100, lambda i: [face(tilt=1.3 if within(i, 2.0, 3.0) else 0.62)])
    side = data(100, lambda i: [face(eyes=0.25 if within(i, 5.0, 6.0) else 0.46)])
    assert kinds(df.find(down, [])[0]) == [("turned", 2.0, 3.0)]
    assert kinds(df.find(side, [])[0]) == [("turned", 5.0, 6.0)]


def test_looking_up_is_not_turned():
    d = data(100, lambda i: [face(tilt=0.2 if within(i, 2.0, 3.0) else 0.62)])
    assert df.find(d, [])[0] == []


def test_one_calm_sample_inside_a_run_does_not_split_it():
    d = data(100, lambda i: [face(turn=0.1 if i == 35 else (0.9 if within(i, 3.0, 4.0) else 0.1))])
    assert kinds(df.find(d, [])[0]) == [("turned", 3.0, 4.0)]


def test_a_blurred_face_is_blur_and_a_turned_face_is_not_compared_for_sharpness():
    blur = data(100, lambda i: [face(sharp=20.0 if within(i, 4.0, 5.0) else 100.0)])
    assert kinds(df.find(blur, [])[0]) == [("blur", 4.0, 5.0)]
    both = data(100, lambda i: [face(turn=0.9, sharp=20.0) if within(i, 4.0, 5.0) else face()])
    assert kinds(df.find(both, [])[0]) == [("turned", 4.0, 5.0)]


def test_a_lost_face_between_faces_is_a_defect():
    d = data(100, lambda i: [] if within(i, 5.0, 5.6) else [face()])
    out = df.find(d, [])[0]
    assert kinds(out) == [("lost", 5.0, 5.6)] and out[0]["detail"] == "no face"


def test_no_face_at_the_very_start_or_end_is_not_a_slip():
    d = data(100, lambda i: [] if i < 8 or i >= 95 else [face()])
    assert df.find(d, [])[0] == []


def test_a_long_stretch_without_a_face_is_named_a_stretch_without_the_speaker():
    d = data(200, lambda i: [] if within(i, 5.0, 5.0 + df.LOST_MAX_S + 1) else [face()])
    out = df.find(d, [])[0]
    assert [x["kind"] for x in out] == ["lost"]
    assert "without the speaker" in out[0]["detail"]


def test_someone_else_in_the_frame_is_a_stranger_and_a_doubtful_face_is_not():
    other = (20, 600, 100, 130)
    d = data(100, lambda i: [face(), face(box=other)] if within(i, 6.0, 7.0) else [face()])
    out = df.find(d, [])[0]
    assert kinds(out) == [("stranger", 6.0, 7.0)] and "2 faces" in out[0]["detail"]
    weak = data(100, lambda i: [face(), face(box=other, score=0.65)] if within(i, 6.0, 7.0) else [face()])
    assert df.find(weak, [])[0] == []


def test_a_face_far_from_the_speaker_does_not_stand_in_for_the_lost_speaker():
    other = (10, 700, 100, 130)
    d = data(100, lambda i: [face(box=other)] if within(i, 4.0, 4.6) else [face()])
    out = df.find(d, [])[0]
    assert ("lost", 4.0, 4.6) in kinds(out)
    assert out[0]["detail"] == "no face where the speaker is"


def test_each_source_has_its_own_norm():
    # the second camera sees the head from another angle: its own median, so no defect
    segs = [{"out_start": 0.0, "out_dur": 5.0, "source": "a"}, {"out_start": 5.0, "out_dur": 5.0, "source": "b"}]
    d = data(100, lambda i: [face(turn=0.1)] if i < 50 else [face(turn=0.7)])
    out, info = df.find(d, segs)
    assert out == []
    assert round(info["norms"]["a"]["turn"], 2) == 0.1 and round(info["norms"]["b"]["turn"], 2) == 0.7
    # one source for both: the second half is turned against the shared norm
    one = data(140, lambda i: [face(turn=0.1)] if i < 100 else [face(turn=0.7)])
    assert kinds(df.find(one, [])[0]) == [("turned", 10.0, 14.0)]


def test_a_source_in_profile_is_not_checked_for_turns():
    segs = [{"out_start": 0.0, "out_dur": 6.0, "source": "front"}, {"out_start": 6.0, "out_dur": 4.0, "source": "side"}]
    d = data(100, lambda i: [face()] if i < 60 else [face(eyes=0.22, turn=0.9 if i % 7 else 0.1)])
    out, info = df.find(d, segs)
    assert out == []
    assert info["norms"]["front"]["facing"] and not info["norms"]["side"]["facing"]


def test_no_speaker_on_camera_nothing_to_check():
    d = data(100, lambda i: [face()] if i < 100 * df.ON_CAMERA - 5 else [])
    out, info = df.find(d, [])
    assert out == [] and info["on_camera"] is False


def test_a_speaker_who_never_faces_the_camera_nothing_to_check():
    d = data(100, lambda i: [face(eyes=0.2, turn=0.8 + 0.5 * (i % 3))])
    out, info = df.find(d, [])
    assert out == [] and info["on_camera"] is False and info["facing"] is False


def test_the_words_heard_under_a_defect_are_attached():
    words = [{"text": "before", "start": 2.0, "end": 2.9}, {"text": "under", "start": 3.1, "end": 3.5},
             {"text": "edge", "start": 3.9, "end": 4.3}, {"text": "after", "start": 4.5, "end": 5.0}]
    d = data(100, lambda i: [face(turn=0.9 if within(i, 3.0, 4.0) else 0.1)])
    assert df.find(d, [], words)[0][0]["words"] == "under edge"


@pytest.mark.parametrize("turn,found", [(0.2, True), (0.6, False)])
def test_the_turn_threshold_can_be_given(turn, found):
    d = data(100, lambda i: [face(turn=0.5 if within(i, 3.0, 4.0) else 0.1)])
    assert bool(df.find(d, [], turn=turn)[0]) is found


def test_pose_is_none_for_a_profile_and_reads_the_points_otherwise():
    t, l, e = df.pose(face(turn=0.3, tilt=0.7, eyes=0.45))
    assert (round(t, 2), round(l, 2), round(e, 2)) == (0.3, 0.7, 0.45)
    assert df.pose(face(eyes=0.02))[:2] == (None, None)
