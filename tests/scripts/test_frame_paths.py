"""The face detectors read frames from a folder with a non-ASCII name (a Cyrillic Windows user name puts the temp folder
there). Before 1.38.2 cv2.imread returned None on such a path on Windows, and every frame read as "no face": the video
counted as a voice-over and text went over the face. The detector itself is replaced by a stub that finds one face on
any image it is given: what is checked is that the frame reaches it."""
import importlib
import json
import subprocess
import sys

import pytest

from conftest import _has

needs_cv2 = pytest.mark.skipif(not _has("cv2"), reason="OpenCV is not installed")

STUB = """
import cv2, numpy as np
class _Stub:
    def setInputSize(self, size):
        pass
    def detect(self, im):
        r = np.zeros((1, 15), np.float32)
        r[0, :4] = [10, 20, 30, 40]
        r[0, 14] = 0.9
        return 1, r
cv2.FaceDetectorYN_create = lambda *a: _Stub()
"""
ARGS = {"faces": ["model.onnx", "0.6"], "defects": ["model.onnx", "0.6", "96"]}


def detect(module, paths):
    m = importlib.import_module(module)
    return subprocess.run([sys.executable, "-c", STUB + m.DETECT, *ARGS[module]], input=json.dumps([str(p) for p in paths]),
                          capture_output=True, text=True, timeout=120)


def write_png(path):
    import cv2
    import numpy as np
    ok, buf = cv2.imencode(".png", np.full((64, 64, 3), 128, np.uint8))
    assert ok
    path.write_bytes(buf.tobytes())


@needs_cv2
@pytest.mark.parametrize("module", ["faces", "defects"])
def test_frame_in_a_non_ascii_folder_reaches_the_detector(tmp_path, module):
    folder = tmp_path / "Антон" / "кадры"
    folder.mkdir(parents=True)
    write_png(folder / "00000.png")
    r = detect(module, [folder / "00000.png", folder / "00001.png"])  # the second frame: ffmpeg made none
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert len(out) == 2
    assert len(out[0]) == 1, "the frame was not read: it counted as a frame without a face"
    assert out[1] == []


@needs_cv2
@pytest.mark.parametrize("module", ["faces", "defects"])
def test_a_frame_that_does_not_decode_stops_the_run(tmp_path, module):
    # a broken frame is an error, not a frame without a face
    bad = tmp_path / "00000.png"
    bad.write_bytes(b"not a png")
    r = detect(module, [bad])
    assert r.returncode != 0
    assert "could not decode the frame" in r.stderr
