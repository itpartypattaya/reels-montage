# -*- coding: utf-8 -*-
"""Word-level transcript with faster-whisper, in the format the other scripts read.

    python scripts/transcribe.py edit/4821 IMG_4821.MOV [--model medium] [--language ru]   # -> edit/4821/transcripts/IMG_4821.json
    python scripts/transcribe.py snip edit/4821 IMG_4821.MOV --from 12.3 --to 16.8          # re-transcribe a <= 5 s piece
    python scripts/transcribe.py check edit/4821/transcripts/IMG_4821.json                  # is a transcript in the right format

The transcript is cached: a second run with the same source prints "cached" and does nothing (--force redoes it).
The audio goes into edit/<id>/audio16k-<source stem>.wav (16 kHz mono; speech_mask.py reads the same file). Everything runs on this
computer: the audio never leaves it.

Format (the same as other common word-level tools, so you can use your own transcriber instead and only run `check`):
    {"language_code": "ru", "text": "...", "words": [{"text": "Hello", "start": 0.52, "end": 0.9, "type": "word"}, ...]}
start/end in seconds of the source; optional "speaker_id" per word (faster-whisper has no speaker labels: for two
speakers on one microphone, tell them apart by the lips, SKILL.md step 2); items with another "type" (spacing,
audio events) are ignored.

snip: a suspicious spot (a merged retake, a stretched word) cut out with a run-up from silence and transcribed alone,
without the context of the whole video (condition_on_previous_text off, a "verbatim, with every repeat" prompt).
On a 10 s piece a repeat still collapses into one word, on 5 s it does not; keep pieces <= 5 s. The result goes into
edit/<id>/snip/ with times on the source timeline. A word fragment at an edge is never visible to Whisper in any mode:
only speech_mask.py --edl catches it.

Needs faster-whisper (`pip install faster-whisper`). The model is not downloaded by this script: if it is not on this
computer yet, the script prints the one command that downloads it. Defaults: medium, int8, CPU (~2.5 min per 96 s of
audio on a laptop); small is faster and less accurate; large does not fit a laptop with 8 GB.
"""
import argparse, json, os, sys, uuid, wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import edit_dir, load_json, locked, probe, project_root, run, save_json, utf8_stdio, warn

SNIP_MAX = 5.0
SNIP_PROMPT = "Verbatim, with every repeat, slip and filler word."


def resolve_src(arg, project, e):
    p = Path(arg)
    for cand in (p, project / p, e / p):
        if cand.is_file():
            return cand.resolve()
    sys.exit(f"no source file {arg} (looked in the current folder, {project} and {e})")


def extract_audio(src, out, start=None, end=None):
    """16 kHz mono WAV, optionally a piece [start, end) of the source."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cut = (["-ss", f"{start:.3f}", "-to", f"{end:.3f}"] if start is not None else [])
    tmp = out.with_name(f".{out.stem}.{os.getpid()}.{uuid.uuid4().hex}.wav")
    try:
        run(["ffmpeg", "-v", "error", "-y", *cut, "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", tmp])
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            tmp.unlink()
    return out


def load_model(name, compute):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper is not installed: pip install faster-whisper (or run this script with "
                 "uv run --with faster-whisper python scripts/transcribe.py ...)")
    try:
        return WhisperModel(name, device="cpu", compute_type=compute, local_files_only=True)
    except Exception as ex:  # not downloaded yet, or a broken cache
        sys.exit(f"the {name} model is not on this computer yet ({type(ex).__name__}). Download it once yourself:\n"
                 f"    python -c \"from faster_whisper import download_model; download_model('{name}')\"\n"
                 f"then run this command again.")


def read_wav(wav):
    """The 16 kHz mono 16-bit WAV that ffmpeg made -> float32 samples. faster-whisper gets samples, not a file, so it
    never decodes audio itself: its PyAV decoder breaks with some PyAV versions (faster-whisper 1.2.1 + PyAV 19)."""
    import numpy as np  # installed with faster-whisper
    with wave.open(str(wav), "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2):
            sys.exit(f"{wav}: expected 16 kHz mono 16-bit audio")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def words_of(model, wav, language, snip=False, offset=0.0):
    """faster-whisper -> (language, text, words) with times shifted by offset."""
    segments, info = model.transcribe(read_wav(wav), language=language, word_timestamps=True, beam_size=5,
                                      condition_on_previous_text=not snip, initial_prompt=SNIP_PROMPT if snip else None)
    words, texts, last = [], [], 0.0
    for seg in segments:
        texts.append(seg.text.strip())
        for w in seg.words or []:
            t = w.word.strip()
            if not t:
                continue
            words.append({"text": t, "start": round(w.start + offset, 3), "end": round(w.end + offset, 3), "type": "word",
                          "p": round(float(getattr(w, "probability", 0) or 0), 3)})
        if seg.end - last >= 10 and not snip:
            print(f"  ... {seg.end:.0f} s", file=sys.stderr)
            last = seg.end
    return info.language, " ".join(texts), words


def check_doc(doc):
    """Problems of a transcript in this format: a list of strings (empty when it is fine)."""
    if not isinstance(doc, dict) or not isinstance(doc.get("words"), list):
        return ['no "words" list']
    out, prev = [], -1.0
    words = [w for w in doc["words"] if isinstance(w, dict) and w.get("type", "word") == "word"]
    if not words:
        out.append("no words")
    for k, w in enumerate(words):
        if not str(w.get("text", "")).strip():
            out.append(f"word {k}: empty text")
        try:
            s, e = float(w["start"]), float(w["end"])
        except (KeyError, TypeError, ValueError):
            out.append(f"word {k}: start/end missing or not numbers")
            continue
        if e < s:
            out.append(f"word {k} {w.get('text')!r}: end {e} before start {s}")
        if s + 0.05 < prev:
            out.append(f"word {k} {w.get('text')!r}: starts at {s}, before the previous word ({prev}); words must be in order")
        prev = max(prev, s)
    long = [w for w in words if isinstance(w.get("start"), (int, float)) and isinstance(w.get("end"), (int, float))
            and w["end"] - w["start"] > 1.0]
    if long:
        out.append(f"note: {len(long)} word(s) longer than 1 s, a typical sign of a merged retake (SKILL.md step 3): "
                   + ", ".join(f"{w['text']} {w['start']:.2f}" for w in long[:5]))
    return out


def cmd_full(a):
    project = project_root()
    e = edit_dir(a.edit, project, create=True)
    src = resolve_src(a.source, project, e)
    out = e / "transcripts" / f"{src.stem}.json"
    identity = {"path": str(src.resolve()), "size": src.stat().st_size, "mtime_ns": src.stat().st_mtime_ns}
    if out.exists() and not a.force and (load_json(out) or {}).get("source_identity") == identity:
        print(f"cached: {out} (--force to transcribe again)")
        return
    wav = e / f"audio16k-{src.stem}.wav"
    stamp = wav.with_suffix(".json")
    with locked(wav, stale=86400):
        if not wav.exists() or a.force or load_json(stamp) != identity:
            extract_audio(src, wav)
            save_json(stamp, identity)
        model = load_model(a.model, a.compute)
        dur = probe(src).get("dur") or 0
        print(f"transcribing {src.name} ({dur:.0f} s) with {a.model} {a.compute} ...", file=sys.stderr)
        lang, text, words = words_of(model, wav, a.language)
    doc = {"language_code": lang, "text": text, "words": words, "source": src.name, "source_identity": identity,
           "model": f"faster-whisper {a.model} {a.compute}"}
    save_json(out, doc)
    problems = [p for p in check_doc(doc) if not p.startswith("note:")]
    notes = [p for p in check_doc(doc) if p.startswith("note:")]
    for n in notes:
        warn(n[6:])
    print(f"{out}: {len(words)} words, language {lang}" + (f"; problems: {'; '.join(problems)}" if problems else ""))


def cmd_snip(a):
    project = project_root()
    e = edit_dir(a.edit, project, create=True)
    src = resolve_src(a.source, project, e)
    if a.end <= a.start:
        sys.exit("--to must be after --from")
    if a.end - a.start > SNIP_MAX:
        warn(f"the piece is {a.end - a.start:.1f} s: above {SNIP_MAX:.0f} s a repeat may still collapse into one word")
    name = f"{src.stem}_{a.start:.2f}-{a.end:.2f}"
    wav = extract_audio(src, e / "snip" / f"{name}.wav", a.start, a.end)
    model = load_model(a.model, a.compute)
    lang, text, words = words_of(model, wav, a.language, snip=True, offset=a.start)
    save_json(e / "snip" / f"{name}.json", {"language_code": lang, "text": text, "words": words, "source": src.name,
                                           "from": a.start, "to": a.end})
    print(f"{a.start:.2f}-{a.end:.2f}: {text}")
    for w in words:
        print(f"  {w['start']:8.2f} {w['end']:8.2f}  {w['text']}")


def cmd_check(a):
    doc = load_json(a.file)
    if doc is None:
        sys.exit(f"cannot read {a.file} as JSON")
    problems = check_doc(doc)
    errors = [p for p in problems if not p.startswith("note:")]
    for p in problems:
        print(("  " if p.startswith("note:") else "  error: ") + p)
    n = len([w for w in doc.get("words", []) if isinstance(w, dict) and w.get("type", "word") == "word"])
    print(f"{a.file}: {n} words, {'OK' if not errors else f'{len(errors)} problem(s)'}")
    sys.exit(1 if errors else 0)


def main():
    utf8_stdio()
    argv = sys.argv[1:]
    cmds = {"snip", "check"}
    if argv and argv[0] not in cmds and not argv[0].startswith("-"):
        argv = ["full"] + argv  # the main mode needs no command word: transcribe.py edit/<id> <source>
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--model", default="medium", help="faster-whisper model name or folder (default medium)")
        p.add_argument("--compute", default="int8", help="compute type (default int8)")
        p.add_argument("--language", help="language code, e.g. ru, en (default: detected)")

    p = sub.add_parser("full", help="the whole source -> edit/<id>/transcripts/<name>.json")
    p.add_argument("edit"); p.add_argument("source"); p.add_argument("--force", action="store_true")
    common(p); p.set_defaults(fn=cmd_full)
    p = sub.add_parser("snip", help="re-transcribe a <= 5 s piece without context")
    p.add_argument("edit"); p.add_argument("source")
    p.add_argument("--from", dest="start", type=float, required=True); p.add_argument("--to", dest="end", type=float, required=True)
    common(p); p.set_defaults(fn=cmd_snip)
    p = sub.add_parser("check", help="is a transcript (yours or this script's) in the right format")
    p.add_argument("file"); p.set_defaults(fn=cmd_check)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
