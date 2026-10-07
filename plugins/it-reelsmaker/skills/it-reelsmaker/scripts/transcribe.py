# -*- coding: utf-8 -*-
"""Word-level transcript with faster-whisper, in the format the other scripts read.

    python scripts/transcribe.py edit/4821 IMG_4821.MOV [--model medium] [--language ru]   # -> edit/4821/transcripts/IMG_4821.json
    python scripts/transcribe.py snip edit/4821 IMG_4821.MOV --from 12.3 --to 16.8          # re-transcribe a <= 5 s piece
    python scripts/transcribe.py splice edit/4821 edit/4821/snip/IMG_4821_12.30-16.80.json  # put a snip into the transcript
    python scripts/transcribe.py check edit/4821/transcripts/IMG_4821.json                  # is a transcript in the right format
    python scripts/transcribe.py audio edit/4821 IMG_4821.MOV                               # only the aligned WAV, for your own transcriber
    python scripts/transcribe.py rate edit/4821 [--source front]                            # speech rate of the rough cut

The transcript is cached: a second run with the same source prints "cached" and does nothing (--force redoes it).
The audio goes into edit/<id>/audio16k-<source stem>.wav (16 kHz mono; speech_mask.py reads the same file). Everything runs on this
computer: the audio never leaves it.

Your own transcriber (a cloud one, for example): give it the WAV from `audio`, not the video file. A phone MOV's sound
track can start ~0.1 s after the picture; a tool that pulls the audio out of the video itself gets every word ~0.1 s
early, and edges set by those words clip word endings. Then put its output into edit/<id>/transcripts/<source stem>.json
and run `check`.

Format (the same as other common word-level tools, so you can use your own transcriber instead and only run `check`):
    {"language_code": "ru", "text": "...", "words": [{"text": "Hello", "start": 0.52, "end": 0.9, "type": "word"}, ...]}
start/end in seconds of the source; optional "speaker" per word ("speaker_id", the name other tools use, is read the
same way; cut.py writes "speaker"). faster-whisper has no speaker labels, and on one microphone a diarizer mixes the
two people up: tell them apart by the lips (SKILL.md step 2) and put the speakers into cut.json ("speaker" per range,
"speakers" for a switch inside one; cut.py --help); items with another "type" (spacing, audio events) are ignored.

snip: a suspicious spot (a merged retake, a stretched word) cut out with a run-up from silence and transcribed alone,
without the context of the whole video (condition_on_previous_text off). The language is --language, else the one of
the source's cached transcript (a 5 s piece is too short to detect it reliably). The prompt is a short sample of
speech with fillers and repeats IN THAT LANGUAGE (English and Russian), so Whisper keeps them; for another or an
unknown language there is no prompt, and --no-prompt turns it off. Never a prompt in another language: Whisper copies
it into the text (T5: an English "verbatim" instruction with --language ru came back as "Verbatim, 1 000 EUR" instead
of the Russian words). On a 10 s piece a repeat still collapses into one word, on 5 s it does not; keep pieces <= 5 s.
The result goes into edit/<id>/snip/ with times on the source timeline. A word fragment at an edge is never visible to
Whisper in any mode: only speech_mask.py --edl catches it.

splice: the snip's words replace the main transcript's words inside a window (default: the snip's own from/to;
--from/--to narrow it). A word belongs to the window by its middle. The main transcript is the one cut.json names
for the snip's source ("transcript"), else edit/<id>/transcripts/<source stem>.json; the doc's other keys stay, a
"splices" list records each splice, and the state before it is kept as <stem>.presplice.json (-2, -3, ... when an
earlier, different backup is there: a backup is never overwritten). The result goes through `check` before it is
saved. Then rebuild the cut (cut.py): its words come from the transcript.

rate: syllables per second = the vowels of the transcript's words / the speech time by the speech mask
(speech_mask.py: speech windows only, pauses do not count), measured on the rough cut final.mp4 per source and per
segment (captions.json); what step 5 compares between two cameras. Measure on the cut speech, not on the source: the
rate on a whole source mixes in phrases the cut drops (T2: the source estimate and the cut differed, and the cut is
what the viewer hears; a take spoken faster shows up as one segment above the others). Vowels: Latin and Cyrillic
letters (one vowel = one syllable in Russian; English is overestimated a little, the same for both cameras). A number
written in digits ("270", "1,5", "10%") has no vowels to count but takes time to say: such words are left out of both
the vowels and the speech time (the mask windows under the word), and the output says how many (T5: a price in
digits read 2.18 syllables/s on a segment spoken at the video's usual pace).

Needs faster-whisper (`pip install faster-whisper`). The model is not downloaded by this script: if it is not on this
computer yet, the script prints the one command that downloads it. Defaults: medium, int8, CPU (~2.5 min per 96 s of
audio on a laptop); small is faster and less accurate; large does not fit a laptop with 8 GB.
"""
import argparse, json, os, re, sys, uuid, wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import ANALYSIS_AF, audio_offset, edit_dir, load_json, locked, probe, project_root, run, save_json, utf8_stdio, warn

SNIP_MAX = 5.0
# a sample of speech with fillers and repeats, in the transcript's own language: Whisper follows its style; a prompt in
# another language leaks into the text
SNIP_PROMPTS = {
    "en": "Umm, so, so I, I mean, like, you know, uh, it's, it's fine.",
    "ru": "\u041d\u0443, \u044d-\u044d, \u0432\u043e\u0442, \u0432\u043e\u0442, \u043a\u0430\u043a \u0431\u044b, "
          "\u043d\u0443, \u0442\u043e \u0435\u0441\u0442\u044c, \u044d\u0442\u043e \u0441\u0430\u043c\u043e\u0435.",
}


def snip_prompt(language):
    """The snip prompt for a language code ("ru", "en-US"), or None: no prompt rather than one in another language."""
    return SNIP_PROMPTS.get(str(language or "").lower().replace("_", "-").split("-")[0])


# three-letter codes another transcriber writes ("rus", "eng") -> the two-letter codes faster-whisper takes
ISO3 = {"rus": "ru", "eng": "en", "ukr": "uk", "deu": "de", "ger": "de", "fra": "fr", "fre": "fr", "spa": "es",
        "ita": "it", "por": "pt", "tur": "tr", "tha": "th", "vie": "vi", "zho": "zh", "chi": "zh", "jpn": "ja",
        "kor": "ko", "pol": "pl", "nld": "nl", "dut": "nl", "ara": "ar", "hin": "hi", "ind": "id", "swe": "sv",
        "ces": "cs", "cze": "cs", "kaz": "kk", "bel": "be", "heb": "he", "ell": "el", "gre": "el"}
# the codes Whisper models know (faster_whisper.tokenizer._LANGUAGE_CODES; not imported here: loading faster-whisper
# for a code check is slow, and in the tests it would replace the stub)
WHISPER_LANGS = set(
    "af am ar as az ba be bg bn bo br bs ca cs cy da de el en es et eu fa fi fo fr gl gu ha haw he hi hr ht hu hy id "
    "is it ja jw ka kk km kn ko la lb ln lo lt lv mg mi mk ml mn mr ms mt my ne nl nn no oc pa pl ps pt ro ru sa sd si "
    "sk sl sn so sq sr su sv sw ta te tg th tk tl tr tt uk ur uz vi yi yo yue zh".split())


def whisper_language(code):
    """A language code as faster-whisper takes it ("en-US" -> "en", "rus" -> "ru"), or None when it does not know it
    (a full name like "swedish" from the online add-on, a code outside its list): None lets the model detect it."""
    base = str(code or "").strip().lower().replace("_", "-").split("-")[0]
    base = ISO3.get(base, base)
    return base if base in WHISPER_LANGS else None


def snip_language(given, e, src):
    """The language of a snip: --language, else the language_code of the source's cached transcript (as faster-whisper
    takes it: review, "rus" from another transcriber made the model stop with "not a valid language code"), else None."""
    if given:
        return whisper_language(given) or given  # a code faster-whisper does not know: its own error names it
    doc = load_json(e / "transcripts" / f"{Path(src).stem}.json") or {}
    return whisper_language(doc.get("language_code"))


def resolve_src(arg, project, e):
    p = Path(arg)
    for cand in (p, project / p, e / p):
        if cand.is_file():
            return cand.resolve()
    sys.exit(f"no source file {arg} (looked in the current folder, {project} and {e})")


def extract_audio(src, out, start=None, end=None):
    """16 kHz mono WAV on the video timeline (second t of the WAV = second t of the video, which cut.py cuts by),
    optionally a piece [start, end) of the source. A seek before -i already aligns the streams; the whole track goes
    through ANALYSIS_AF (a phone MOV's audio can start ~0.1 s after the video)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cut = (["-ss", f"{start:.3f}", "-to", f"{end:.3f}"] if start is not None else [])
    af = [] if start is not None else ["-af", ANALYSIS_AF]
    tmp = out.with_name(f".{out.stem}.{os.getpid()}.{uuid.uuid4().hex}.wav")
    try:
        run(["ffmpeg", "-v", "error", "-y", *cut, "-i", src, "-vn", "-ac", "1", "-ar", "16000", *af, "-c:a", "pcm_s16le", tmp])
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


HYPHENS = "-‐‑"  # hyphen-minus, hyphen, non-breaking hyphen (not the dashes of a pause: en dash, em dash)


def join_hyphen_parts(words):
    """Whisper splits a hyphenated word into tokens, the later ones starting with a hyphen ("no" "-no" "-no." for
    "no-no-no", "someone" in Russian as "kto" "-to"): joined back into one word spanning their times, so the subtitles
    don't show "no -no -no." and a cloud text with the whole word lays onto it. A lone hyphen stays a token."""
    out = []
    for w in words:
        t = str(w.get("text", ""))
        prev = out[-1] if out else None
        if (prev is not None and len(t) > 1 and t[0] in HYPHENS and w.get("type", "word") == "word"
                and prev.get("type", "word") == "word" and float(w["start"]) - float(prev["end"]) < 0.15):
            prev["text"] = str(prev["text"]) + t
            prev["end"] = w["end"]
            if "p" in prev or "p" in w:
                prev["p"] = min(float(prev.get("p", 1)), float(w.get("p", 1)))
            continue
        out.append(dict(w))
    return out


def words_of(model, wav, language, snip=False, offset=0.0, prompt=None):
    """faster-whisper -> (language, text, words) with times shifted by offset. prompt: a snip's initial prompt."""
    segments, info = model.transcribe(read_wav(wav), language=language, word_timestamps=True, beam_size=5,
                                      condition_on_previous_text=not snip, initial_prompt=prompt if snip else None)
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
    return info.language, " ".join(texts), join_hyphen_parts(words)


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
    # a note for a person to listen to (> 1.0 s); structure.py's "retake?" sign starts at 1.5 s, because a word of
    # 1.0-1.5 s is usually stretched over the pause after it (structure.LONG_WORD)
    long = [w for w in words if isinstance(w.get("start"), (int, float)) and isinstance(w.get("end"), (int, float))
            and w["end"] - w["start"] > 1.0]
    if long:
        out.append(f"note: {len(long)} word(s) longer than 1 s, a typical sign of a merged retake (SKILL.md step 3): "
                   + ", ".join(f"{w['text']} {w['start']:.2f}" for w in long[:5]))
    return out


def source_wav(e, src, force=False):
    """edit/<id>/audio16k-<stem>.wav on the video timeline, (re)made when missing, forced or made from another file
    → (wav, identity, audio offset). Call under locked(wav)."""
    identity = {"path": str(src.resolve()), "size": src.stat().st_size, "mtime_ns": src.stat().st_mtime_ns}
    off = audio_offset(src)
    stamp_doc = {**identity, "timeline": "video", "audio_offset": off}
    wav = e / f"audio16k-{src.stem}.wav"
    stamp = wav.with_suffix(".json")
    if not wav.exists() or force or load_json(stamp) != stamp_doc:
        extract_audio(src, wav)
        save_json(stamp, stamp_doc)
    return wav, identity, off


def cmd_audio(a):
    project = project_root()
    e = edit_dir(a.edit, project, create=True)
    src = resolve_src(a.source, project, e)
    with locked(e / f"audio16k-{src.stem}.wav", stale=86400):
        wav, _, off = source_wav(e, src, a.force)
    (e / "transcripts").mkdir(exist_ok=True)  # the folder the transcript is saved into
    print(f"{wav}: 16 kHz mono on the video timeline" + (f" (the sound track starts {off:.3f} s after the picture; "
          "aligned)" if off else "") + f". Give this file to your transcriber, save its output as "
          f"{e / 'transcripts' / (src.stem + '.json')} and run transcribe.py check on it.")


def cmd_full(a):
    project = project_root()
    e = edit_dir(a.edit, project, create=True)
    src = resolve_src(a.source, project, e)
    out = e / "transcripts" / f"{src.stem}.json"
    identity = {"path": str(src.resolve()), "size": src.stat().st_size, "mtime_ns": src.stat().st_mtime_ns}
    wav = e / f"audio16k-{src.stem}.wav"
    if out.exists() and not a.force and (load_json(out) or {}).get("source_identity") == identity:
        print(f"cached: {out} (--force to transcribe again)")
        return
    with locked(wav, stale=86400):
        wav, identity, off = source_wav(e, src, a.force)
        model = load_model(a.model, a.compute)
        dur = probe(src).get("dur") or 0
        print(f"transcribing {src.name} ({dur:.0f} s) with {a.model} {a.compute} ...", file=sys.stderr)
        lang, text, words = words_of(model, wav, a.language)
    doc = {"language_code": lang, "text": text, "words": words, "source": src.name, "source_identity": identity,
           "model": f"faster-whisper {a.model} {a.compute}", "timeline": "video", "audio_offset": off}
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
    language = snip_language(a.language, e, src)
    prompt = None if a.no_prompt else snip_prompt(language)
    wav = extract_audio(src, e / "snip" / f"{name}.wav", a.start, a.end)
    model = load_model(a.model, a.compute)
    lang, text, words = words_of(model, wav, language, snip=True, offset=a.start, prompt=prompt)
    save_json(e / "snip" / f"{name}.json", {"language_code": lang, "text": text, "words": words, "source": src.name,
                                           "from": a.start, "to": a.end, "prompt": prompt})
    how = (f"language {language}" if language else "language detected on the piece (pass --language)") + (
        f", a {language} prompt with fillers" if prompt else ", no prompt")
    print(f"{a.start:.2f}-{a.end:.2f} ({how}): {text}")
    for w in words:
        print(f"  {w['start']:8.2f} {w['end']:8.2f}  {w['text']}")


def main_transcript(e, project, stem):
    """The transcript cut.py reads for a source stem: cut.json's "transcript" for the source whose file has this stem,
    else edit/<id>/transcripts/<stem>.json."""
    from cut import resolve
    for sv in ((load_json(e / "cut.json") or {}).get("sources") or {}).values():
        sv = {"file": sv} if isinstance(sv, str) else sv
        if isinstance(sv, dict) and sv.get("file") and Path(str(sv["file"])).stem == stem and sv.get("transcript"):
            return resolve(sv["transcript"], project, e)
    return e / "transcripts" / f"{stem}.json"


def in_window(w, t0, t1):
    """A transcript item belongs to a splice window by its middle (an item without times: no)."""
    try:
        mid = (float(w["start"]) + float(w["end"])) / 2
    except (KeyError, TypeError, ValueError):
        return False
    return t0 <= mid < t1


def splice_words(doc, snip_words, t0, t1):
    """The doc's items inside [t0, t1) replaced with the snip's words inside it -> (new items, removed, added)."""
    items = doc.get("words") or []
    removed = [w for w in items if isinstance(w, dict) and in_window(w, t0, t1)]
    added = [dict(w) for w in snip_words if isinstance(w, dict) and in_window(w, t0, t1)]
    kept = [w for w in items if not (isinstance(w, dict) and in_window(w, t0, t1))]
    # the order by start time: any float-compatible start (an outside transcript may write "12.5"), and an item with no
    # time stays after the item before it rather than jumping to the top (Codex review: numeric strings sorted first)
    def start(w):
        try:
            return float(w["start"])
        except (KeyError, TypeError, ValueError):
            return None
    seq, last = [], -1.0
    for w in kept:
        t = start(w) if isinstance(w, dict) else None
        last = t if t is not None else last
        seq.append((last, w))
    for w in added:
        t = start(w)
        seq.append((t if t is not None else last, w))
    return [w for _, w in sorted(seq, key=lambda x: x[0])], removed, added


def backup_path(f, doc):
    """<stem>.presplice.json, or -2, -3, ... when a different earlier backup is there; None: the same state is kept."""
    k = 1
    while True:
        b = f.with_name(f"{f.stem}.presplice{'' if k == 1 else f'-{k}'}.json")
        if not b.exists():
            return b
        if load_json(b) == doc:
            return None
        k += 1


def cmd_splice(a):
    project = project_root()
    e = edit_dir(a.edit, project)
    sp = next((c for c in (Path(a.snip), project / a.snip, e / a.snip, e / "snip" / a.snip) if c.is_file()), None)
    if sp is None:
        sys.exit(f"no snip file {a.snip} (looked in the current folder, {project}, {e} and {e / 'snip'})")
    snip = load_json(sp)
    if not isinstance(snip, dict) or not isinstance(snip.get("words"), list):
        sys.exit(f"{sp}: not a transcript (no \"words\" list); make it with transcribe.py snip")
    m = re.fullmatch(r"(.+)_(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", sp.stem)
    stem = Path(str(snip["source"])).stem if snip.get("source") else (m.group(1) if m else None)
    if not stem:
        sys.exit(f"{sp}: the snip names no source (\"source\"): cannot tell which transcript it belongs to")
    try:
        t0 = float(a.start if a.start is not None else snip["from"])
        t1 = float(a.end if a.end is not None else snip["to"])
    except (KeyError, TypeError, ValueError):
        sys.exit(f"{sp}: no \"from\"/\"to\" in the snip: give the window with --from and --to (source seconds)")
    if t1 <= t0:
        sys.exit("--to must be after --from")
    lo, hi = snip.get("from"), snip.get("to")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and (t0 < lo - 1e-6 or t1 > hi + 1e-6):
        # the snip heard only its own piece: outside it the main words would go with nothing in their place
        sys.exit(f"the window {t0:.2f}-{t1:.2f} leaves the snip's piece {lo:.2f}-{hi:.2f}: keep --from/--to inside it")
    inwin = [w for w in snip["words"] if in_window(w, t0, t1)]
    bad = [p for p in check_doc({"words": inwin}) if inwin and not p.startswith("note:")]
    if bad:
        sys.exit(f"{sp}: " + "; ".join(bad))
    f = main_transcript(e, project, stem)
    with locked(f):
        doc = load_json(f)
        if not isinstance(doc, dict) or not isinstance(doc.get("words"), list):
            sys.exit(f"no main transcript {f} for the snip's source {stem} (a snip of the rough cut, final.mp4, has no "
                     f"transcript to go into: snip the source file)")
        words, removed, added = splice_words(doc, snip["words"], t0, t1)
        if not removed and not added:
            sys.exit(f"{t0:.2f}-{t1:.2f} s: no words in the window, neither in {f.name} nor in the snip: nothing to do")
        new = {**doc, "words": words, "splices": (doc.get("splices") or []) + [
            {"snip": sp.name, "from": round(t0, 3), "to": round(t1, 3), "removed": len(removed), "added": len(added)}]}
        problems = [p for p in check_doc(new) if not p.startswith("note:")]
        if problems:
            sys.exit(f"the spliced transcript does not pass check, nothing saved: {'; '.join(problems)}")
        b = backup_path(f, doc)
        if b:
            save_json(b, doc)
        save_json(f, new)
    txt = lambda ws: " ".join(str(w.get("text", "")) for w in ws if w.get("type", "word") == "word") or "-"
    print(f"{f}: {t0:.2f}-{t1:.2f} s from {sp.name}: removed {len(removed)} ({txt(removed)}), added {len(added)} "
          f"({txt(added)})" + (f"; before: {b.name}" if b else "; the backup of this state is already there"))
    for n in check_doc(new):
        if n.startswith("note:"):
            warn(n[6:])
    print("next: rebuild the cut (cut.py) so the subtitles take the new words")


VOWELS = set("aeiouAEIOU" + "".join(chr(c) for c in (0x430, 0x435, 0x451, 0x438, 0x43e, 0x443, 0x44b, 0x44d,
                                                     0x44e, 0x44f, 0x456, 0x457, 0x454)))  # Cyrillic a e yo i o u y e yu ya i yi ye


def vowels(text):
    return sum(1 for ch in str(text) if ch.lower() in VOWELS)


def is_number(text):
    """A word written in digits only ("270", "1,5", "10%", "$50"): no letters and at least one digit."""
    t = str(text)
    return bool(re.search(r"\d", t)) and not re.search(r"[^\W\d_]", t)


def masked(mask, hop, spans):
    """Mask windows (speech) inside the union of spans [(start, end)] in seconds."""
    on, cur = 0, None
    for a, b in sorted(spans) + [(float("inf"), float("inf"))]:
        if cur and a <= cur[1]:
            cur[1] = max(cur[1], b)
            continue
        if cur:
            on += sum(mask[max(0, int(round(cur[0] / hop))):max(0, int(round(cur[1] / hop)))])
        cur = [a, b]
    return on * hop


def cmd_rate(a):
    """Syllables per second of the rough cut, per source and per segment (see the module help)."""
    import speech_mask as sm
    e = edit_dir(a.edit)
    cap = load_json(e / "captions.json")
    if not cap or not (e / "final.mp4").exists():
        sys.exit(f"{e}: no captions.json or final.mp4: build the rough cut first (cut.py)")
    env, hf = sm.load_envs(str(e / "final.mp4"))
    sdb = sm.smax(env)
    srt = sorted(x for x in sdb if x > -90)
    thr = min(-30.0, (srt[int(len(srt) * 0.95)] if srt else -20) - 20)
    mask = sm.speech_mask(sdb, thr, vl=sm.voiceless(hf))
    segs = [g for g in cap.get("segments", []) if not a.source or g.get("source") == a.source]
    if not segs:
        sys.exit(f"no segment of source {a.source!r} (sources: {', '.join(sorted({g.get('source') for g in cap.get('segments', [])}))})")
    rows, total = [], {}
    for g in segs:
        g0, g1 = g["out_start"], g["out_start"] + g["out_dur"]
        lo, hi = int(round(g0 / sm.HOP)), int(round(g1 / sm.HOP))
        ws = [w for w in cap.get("words", []) if w.get("seg") == g["i"]]
        nums = [w for w in ws if is_number(w["text"])]
        # a number in digits: its vowels are not in the text, so its time is left out too
        cut = masked(mask, sm.HOP, [(max(g0, float(w["start"])), min(g1, float(w["end"]))) for w in nums
                                    if min(g1, float(w["end"])) > max(g0, float(w["start"]))])
        speech = max(0.0, sum(mask[lo:hi]) * sm.HOP - cut)
        v = sum(vowels(w["text"]) for w in ws if not is_number(w["text"]))
        rows.append((g, v, speech, [str(w["text"]) for w in nums], cut))
        t = total.setdefault(g.get("source"), [0, 0.0, 0, 0, 0.0])
        t[0] += v; t[1] += speech; t[2] += 1; t[3] += len(nums); t[4] += cut
    print(f"speech rate on the rough cut (syllables/s = vowels / speech time by the speech mask, threshold {thr:.1f} dBFS;"
          f" numbers in digits are left out of both)")
    for src, (v, speech, n, nn, ns) in total.items():
        print(f"  {src}: {v / speech if speech else 0:.2f}  ({v} vowels, {speech:.2f} s of speech, {n} segment(s)"
              + (f"; {nn} number(s) in digits left out with their {ns:.2f} s" if nn else "") + ")")
    print("per segment:")
    for g, v, speech, nums, cut in rows:
        print(f"  {g['i']:2d} {g.get('source', ''):<8} {g['out_start']:7.2f}+{g['out_dur']:.2f}  "
              f"{v / speech if speech else 0:5.2f}  ({v} vowels, {speech:.2f} s"
              + (f"; without {', '.join(nums)}: {cut:.2f} s" if nums else "") + f")  {g.get('beat', '')}")
    if a.json:
        print(json.dumps({"threshold": round(thr, 1), "sources": {k: {"rate": round(v / sp, 2) if sp else None, "vowels": v,
                                                                       "speech_s": round(sp, 2), "segments": n,
                                                                       "numbers": nn, "numbers_s": round(ns, 2)}
                                                                   for k, (v, sp, n, nn, ns) in total.items()},
                          "segments": [{"i": g["i"], "source": g.get("source"), "rate": round(v / sp, 2) if sp else None,
                                        "numbers": nums} for g, v, sp, nums, _ in rows]}, ensure_ascii=False))


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
    cmds = {"snip", "splice", "check", "audio", "rate"}
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
    p.add_argument("--no-prompt", action="store_true", help="no initial prompt (the default prompt is in the transcript's language)")
    common(p); p.set_defaults(fn=cmd_snip)
    p = sub.add_parser("splice", help="put a snip's words into the main transcript, inside a window")
    p.add_argument("edit"); p.add_argument("snip", help="the snip's JSON (edit/<id>/snip/<name>.json)")
    p.add_argument("--from", dest="start", type=float, help="window start, source seconds (default: the snip's from)")
    p.add_argument("--to", dest="end", type=float, help="window end, source seconds (default: the snip's to)")
    p.set_defaults(fn=cmd_splice)
    p = sub.add_parser("audio", help="only edit/<id>/audio16k-<name>.wav on the video timeline, for your own transcriber")
    p.add_argument("edit"); p.add_argument("source"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_audio)
    p = sub.add_parser("check", help="is a transcript (yours or this script's) in the right format")
    p.add_argument("file"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("rate", help="syllables per second of the rough cut, per source and segment (step 5)")
    p.add_argument("edit"); p.add_argument("--source", help="only this cut.json source key")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_rate)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
