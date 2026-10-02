"""A stand-in for faster-whisper in tests: no model, no download. Every audio "says" the same three words."""
from types import SimpleNamespace


class WhisperModel:
    def __init__(self, name, device="cpu", compute_type="int8", local_files_only=False):
        if name == "missing":
            raise FileNotFoundError("model not cached")

    def transcribe(self, path, language=None, word_timestamps=True, beam_size=5, condition_on_previous_text=True,
                   initial_prompt=None):
        words = [SimpleNamespace(word=" Hello", start=0.5, end=0.9, probability=0.98),
                 SimpleNamespace(word=" big", start=1.0, end=2.4, probability=0.7),  # stretched: a merged retake
                 SimpleNamespace(word=" world.", start=2.5, end=2.9, probability=0.95)]
        seg = SimpleNamespace(text=" Hello big world.", start=0.5, end=2.9, words=words)
        return iter([seg]), SimpleNamespace(language=language or "en")
