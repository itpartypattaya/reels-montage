# -*- coding: utf-8 -*-
"""A more accurate transcript: the words from a cloud recognizer, their timing from the core's local transcriber.
Part of the it-reelsmaker-online add-on; run through the core:

    python <core scripts>/addon.py transcribe edit/<id> <source> --provider openai [--language ru] [--yes]
    python <core scripts>/addon.py transcribe edit/<id> <source> --price                 # only the price, nothing is sent
    python <core scripts>/addon.py transcribe edit/<id> <source> --words cloud --yes      # no local model: cloud timing

Why two sources. Measured on a 97 s phone video (Russian): OpenAI's gpt-transcribe wrote the cleanest text (it caught
a word the local model dropped and a case ending it got wrong), but it returns no time for words; whisper-1 returns
word times, but they were off by more than 0.15 s for one word in five (a word's start placed on its last sound),
while the local faster-whisper times matched the audio. Subtitles and edges need the time, so by default
(--words local) the local transcript stays the skeleton and the cloud text is laid onto it:
  - the same word: local time, the cloud's spelling and punctuation;
  - a different word in the same place: local time, the cloud's word (the local one is kept in "local");
  - a word only the cloud heard: a time between its neighbours, marked "est": true;
  - words only the local model has: kept as they are (often a repeat of a retake the cloud tidied away: SKILL.md
    step 3), listed in the report as places to listen to.
--words cloud: whisper-1's own word times (when there is no local model); slower and less precise subtitles.

The audio sent is the core's edit/<id>/audio16k-<source stem>.wav (16 kHz mono on the video's timeline: a phone MOV's
sound track can start ~0.1 s after the picture). The result goes into edit/<id>/transcripts/<source stem>.json, the
file the core reads; the local transcript is kept as <stem>.local.json, an older transcript of another kind as
<stem>.prev.json, the provider's raw answer as <stem>.<provider>.raw.json (no key in any of them).

Providers (references/sources.md): openai — text gpt-transcribe ($0.0045 per minute), word times whisper-1 ($0.006
per minute, only with --words cloud); files up to 25 MB (about 13 minutes of this WAV).

Paid: it runs with --yes, or without it when the person set `transcription_provider` in the project defaults or the
video's reel.json (their standing choice). Otherwise it prints the price and exits. No key, no network, no credits:
a warning, exit code 2, and the local command to use instead (the edit continues with the core's transcriber).
REELS_OFFLINE=1: no network at all.
"""
import argparse, difflib, json, re, shutil, sys, unicodedata, urllib.error, urllib.request, uuid
from pathlib import Path
from types import SimpleNamespace

from reels_common import edit_dir, load_config, load_json, locked, project_root, save_json, utf8_stdio, warn
from reels_online import UA, api_key, err_text, offline, open_url, read_json_response
import transcribe as core
from transcribe import check_doc, resolve_src, source_wav

OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"
PROVIDERS = {
    "openai": {"key": "OPENAI_API_KEY", "text_model": "gpt-transcribe", "text_usd_min": 0.0045,
               "words_model": "whisper-1", "words_usd_min": 0.006, "max_bytes": 25 * 1000 * 1000},
}
LANG_CODES = {"russian": "ru", "english": "en", "ukrainian": "uk", "german": "de", "french": "fr", "spanish": "es",
              "italian": "it", "portuguese": "pt", "turkish": "tr", "thai": "th", "vietnamese": "vi", "chinese": "zh",
              "japanese": "ja", "korean": "ko", "polish": "pl", "kazakh": "kk", "arabic": "ar", "hindi": "hi",
              "indonesian": "id", "dutch": "nl"}
LOCAL = "python <core scripts>/transcribe.py edit/<id> <source>"


class NoService(RuntimeError):
    """The provider can't be used now (no key, offline, refused, out of credits): use the local transcriber."""


def multipart(fields, files):
    """multipart/form-data body: fields [(name, value)], files [(name, filename, bytes, content type)]."""
    b = uuid.uuid4().hex
    out = []
    for name, value in fields:
        out += [f"--{b}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n".encode(), str(value).encode(), b"\r\n"]
    for name, fname, data, ctype in files:
        out += [f"--{b}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{fname}\"\r\n"
                f"Content-Type: {ctype}\r\n\r\n".encode(), data, b"\r\n"]
    out.append(f"--{b}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={b}"


def openai_host_ok(url):
    return str(url).startswith("https://api.openai.com/")


def post(url, body, headers, timeout, allowed):
    """POST → JSON; the key never reaches the output (errors pass through err_text)."""
    if offline():
        raise NoService("REELS_OFFLINE=1: network access is off")
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, **headers}, method="POST")
    try:
        with open_url(req, timeout, allowed) as r:
            return read_json_response(r)
    except urllib.error.HTTPError as ex:
        try:
            detail = json.loads(ex.read(65536).decode("utf-8", "replace")).get("error") or {}
        except Exception:
            detail = {}
        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        code = detail.get("code") if isinstance(detail, dict) else None
        why = {401: "the key was refused", 403: "access denied", 429: "rate limit or no credits left"}.get(ex.code, "")
        raise NoService(err_text(RuntimeError(f"HTTP {ex.code} {why} {code or ''} {msg or ''}".strip()), 240)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        raise NoService(err_text(ex)) from None


def openai_call(wav, key, model, language=None, prompt=None, words=False):
    fields = [("model", model), ("response_format", "verbose_json" if words else "json")]
    if words:
        fields += [("timestamp_granularities[]", "word"), ("timestamp_granularities[]", "segment"), ("temperature", "0")]
    if language:
        fields.append(("language", language))
    if prompt:
        fields.append(("prompt", prompt))
    body, ctype = multipart(fields, [("file", Path(wav).name, Path(wav).read_bytes(), "audio/wav")])
    return post(OPENAI_URL, body, {"Authorization": f"Bearer {key}", "Content-Type": ctype}, 600, openai_host_ok)


# --- Laying text onto timed words -------------------------------------------------------------------------------

def norm(s):
    """A word for matching: lower case, letters and digits only (Cyrillic yo = ye)."""
    s = unicodedata.normalize("NFKC", s).lower().replace(chr(0x451), chr(0x435))
    return "".join(ch for ch in s if ch.isalnum())


def tokens(text):
    """The text's words with the punctuation stuck to them; a lone dash between words is not a word (dropped)."""
    return [t for t in re.findall(r"\S+", text or "") if norm(t)]


def pair(a, b):
    """Pairs (i, j) of similar words in order (a and b normalized), the best total similarity: a small LCS where two
    words count as the same when they share at least half of their letters (a case ending, a voiced/unvoiced swap)."""
    sim = lambda x, y: difflib.SequenceMatcher(None, x, y).ratio() if x and y else 0.0
    n, m = len(a), len(b)
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            s = sim(a[i], b[j])
            best[i][j] = max(best[i + 1][j], best[i][j + 1], best[i + 1][j + 1] + s if s >= 0.5 else 0.0)
    out, i, j = [], 0, 0
    while i < n and j < m:
        s = sim(a[i], b[j])
        if s >= 0.5 and abs(best[i][j] - (best[i + 1][j + 1] + s)) < 1e-9:
            out.append((i, j)); i += 1; j += 1
        elif best[i + 1][j] >= best[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def lay_text(words, text):
    """(words with the text's spelling and punctuation, report). words: timed [{text, start, end, ...}] in order."""
    toks = tokens(text)
    a, b = [norm(w["text"]) for w in words], [norm(t) for t in toks]
    seq, rep = [], {"same": 0, "fixed": [], "added": [], "local_only": []}  # seq: timed words and untimed cloud words
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            seq += [{**words[i], "text": toks[j]} for i, j in zip(range(i1, i2), range(j1, j2))]
            rep["same"] += i2 - i1
            continue
        pairs = pair(a[i1:i2], b[j1:j2])
        i, j = i1, j1
        for pi, pj in pairs + [(i2 - i1, j2 - j1)]:
            if i1 + pi - i == j1 + pj - j:  # as many words on each side between matched neighbours: one-for-one
                while i < i1 + pi:          # replacements, however different ("four" heard as "five")
                    seq.append({**words[i], "text": toks[j], "local": words[i]["text"]})
                    rep["fixed"].append((words[i]["start"], words[i]["text"], toks[j]))
                    i += 1; j += 1
            while i < i1 + pi:  # only the local model heard it: kept (often the repeat of a retake)
                seq.append(dict(words[i]))
                if a[i]:  # a lone dash the local model wrote as a word is not worth listening to
                    rep["local_only"].append((words[i]["start"], words[i]["text"]))
                i += 1
            while j < j1 + pj:  # only the cloud heard it: its time comes from the neighbours below
                seq.append({"text": toks[j], "type": "word", "est": True})
                j += 1
            if i < i2 and j < j2:
                seq.append({**words[i], "text": toks[j], "local": words[i]["text"]})
                rep["fixed"].append((words[i]["start"], words[i]["text"], toks[j]))
                i += 1; j += 1
    k = 0
    while k < len(seq):  # untimed runs: share the gap between the neighbours (or the previous word's tail)
        if "start" in seq[k]:
            k += 1
            continue
        e = k
        while e < len(seq) and "start" not in seq[e]:
            e += 1
        n = e - k
        lo = seq[k - 1]["end"] if k else (seq[e]["start"] - 0.3 * n if e < len(seq) else 0.0)
        hi = seq[e]["start"] if e < len(seq) else lo + 0.3 * n
        if hi - lo < 0.06 * n and k:  # no gap: the cloud word sits in the previous word's tail
            lo = max(seq[k - 1]["start"], hi - 0.2 * n)
            seq[k - 1]["end"] = round(max(seq[k - 1]["start"], lo), 3)
        lo = max(0.0, lo)
        step = max(0.0, hi - lo) / n
        for q in range(n):
            seq[k + q].update(start=round(lo + q * step, 3), end=round(lo + (q + 1) * step, 3))
        k = e
    rep["added"] = [(w["start"], w["text"]) for w in seq if w.get("est")]
    return seq, rep


def with_punctuation(words, text):
    """whisper-1 returns the words bare and the text with punctuation: the same laying, kept to the timed words."""
    return lay_text(words, text)[0]


# --- The run ----------------------------------------------------------------------------------------------------

def wav_seconds(wav):
    import wave
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / float(w.getframerate() or 16000)


def approved(e, provider):
    """--yes is not needed when the person chose this provider in the project defaults or the video's reel.json."""
    try:
        s = load_config(e)[0]
    except Exception:
        return False
    return str(s.get("transcription_provider") or "").lower() == provider


def local_words(e, src, identity, a):
    """The local transcript of this source (made now if missing) → doc, or None when there is no local model."""
    keep = e / "transcripts" / f"{src.stem}.local.json"
    out = e / "transcripts" / f"{src.stem}.json"
    for f in (keep, out):
        d = load_json(f) or {}
        if d.get("source_identity") == identity and str(d.get("model", "")).startswith("faster-whisper"):
            if f is out:
                shutil.copyfile(out, keep)
            return d
    prev = out.with_name(f"{src.stem}.prev.json")
    if out.exists():
        out.replace(prev)
    try:
        core.cmd_full(SimpleNamespace(edit=a.edit, source=a.source, force=True, model="medium", compute="int8",
                                      language=a.language))
    except SystemExit as ex:  # no faster-whisper or no model on this computer
        warn(f"no local transcript ({ex}); word times come from the cloud (--words cloud)")
        if prev.exists() and not out.exists():
            prev.replace(out)
        return None
    shutil.copyfile(out, keep)
    return load_json(keep)


def cmd_run(a):
    project = project_root()
    e = edit_dir(a.edit, project, create=True)
    src = resolve_src(a.source, project, e)
    p = PROVIDERS[a.provider]
    out = e / "transcripts" / f"{src.stem}.json"
    with locked(e / f"audio16k-{src.stem}.wav", stale=86400):
        wav, identity, off = source_wav(e, src)
    secs = wav_seconds(wav)
    cloud_words = a.words == "cloud"
    model = p["words_model"] if cloud_words else p["text_model"]
    price = secs / 60 * (p["words_usd_min"] if cloud_words else p["text_usd_min"])
    label = f"{a.provider} {model}" + ("" if cloud_words else " text + faster-whisper timing")
    old = load_json(out) or {}
    if out.exists() and not a.force and old.get("source_identity") == identity and old.get("model") == label:
        print(f"cached: {out} ({label}; --force to transcribe again)")
        return 0
    size = wav.stat().st_size
    print(f"{src.name}: {secs:.0f} s of audio, {size / 1e6:.1f} MB → {a.provider} {model}, ≈ ${price:.3f}")
    if size > p["max_bytes"]:
        warn(f"{a.provider} takes files up to {p['max_bytes'] / 1e6:.0f} MB: this audio is {size / 1e6:.1f} MB. "
             f"Transcribe it locally: {LOCAL}")
        return 2
    if a.price:
        return 0
    if not (a.yes or approved(e, a.provider)):
        print(f"paid: run again with --yes after the person agrees (≈ ${price:.3f}), or set "
              f"transcription_provider={a.provider} in the project defaults (reelcfg.py defaults --set ...)")
        return 0
    key = api_key(p["key"])
    if not key:
        warn(f"{a.provider}: no {p['key']} key: the person adds it in their own terminal with reels_online.py keys set "
             f"{p['key']}. The edit goes on with the local transcriber: {LOCAL}")
        return 2
    base = None if cloud_words else local_words(e, src, identity, a)
    if base is None and not cloud_words:  # no local model: the cloud's own word times cost more, so ask again
        print(f"no local transcript, so the word times would come from {a.provider} {p['words_model']} at "
              f"≈ ${secs / 60 * p['words_usd_min']:.3f} instead of ≈ ${price:.3f}: nothing was sent. After the "
              f"person agrees: --words cloud --yes; or install the local transcriber (doctor.py)")
        return 2
    try:
        raw = openai_call(wav, key, model, a.language, a.prompt, words=cloud_words)
    except NoService as ex:
        warn(f"{a.provider} {model}: {ex}. The edit goes on with the local transcriber: {LOCAL}")
        if base is not None and not out.exists():
            save_json(out, base)
        return 2
    save_json(e / "transcripts" / f"{src.stem}.{a.provider}.raw.json", raw)
    text = str(raw.get("text") or "").strip()
    if cloud_words:
        timed = [{"text": str(w.get("word", "")).strip(), "start": round(float(w["start"]), 3),
                  "end": round(float(w["end"]), 3), "type": "word"}
                 for w in raw.get("words") or [] if str(w.get("word", "")).strip()]
        words, rep = lay_text(timed, text)
        lang = a.language or LANG_CODES.get(str(raw.get("language") or "").lower(), raw.get("language") or "")
    else:
        words, rep = lay_text([w for w in base["words"] if w.get("type", "word") == "word"], text)
        lang = a.language or base.get("language_code") or ""
    doc = {"language_code": lang, "text": text, "words": words, "source": src.name, "source_identity": identity,
           "model": label, "timeline": "video", "audio_offset": off}
    problems = check_doc(doc)
    errors = [x for x in problems if not x.startswith("note:")]
    if errors:
        warn(f"{label}: the answer is not a usable transcript ({'; '.join(errors[:3])}); kept the raw answer. "
             f"Local: {LOCAL}")
        if base is not None and not out.exists():
            save_json(out, base)
        return 2
    if out.exists() and not str(old.get("model", "")).startswith(("faster-whisper", a.provider)):
        out.replace(out.with_name(f"{src.stem}.prev.json"))
    save_json(out, doc)
    for n in problems:
        warn(n[6:])
    print(f"{out}: {len(words)} words, language {lang}, {label}, ≈ ${price:.3f}")
    if not cloud_words:
        print(f"  {rep['same']} words agree; corrected {len(rep['fixed'])}, added {len(rep['added'])} "
              f"(time estimated), local only {len(rep['local_only'])}")
        for t, x, y in rep["fixed"][:12]:
            print(f"  {t:7.2f}  {x} → {y}")
        for t, y in rep["added"][:12]:
            print(f"  {t:7.2f}  + {y}")
        for t, x in rep["local_only"][:12]:
            print(f"  {t:7.2f}  only local: {x} (a retake repeat? listen: SKILL.md step 3)")
    return 0


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="addon.py transcribe", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit"); ap.add_argument("source")
    ap.add_argument("--provider", choices=sorted(PROVIDERS), help="default: transcription_provider from the settings")
    ap.add_argument("--words", choices=["local", "cloud"], default="local",
                    help="word times: local (default, the core's transcriber) or cloud (whisper-1)")
    ap.add_argument("--language", help="language code, e.g. ru, en (default: detected)")
    ap.add_argument("--prompt", help="a short text in the video's language and style (names, terms) the recognizer follows")
    ap.add_argument("--yes", action="store_true", help="the person agreed to the price")
    ap.add_argument("--price", action="store_true", help="only print the price; nothing is sent")
    ap.add_argument("--force", action="store_true", help="transcribe again even if this model already did")
    a = ap.parse_args(argv)
    if not a.provider:
        try:
            a.provider = str(load_config(edit_dir(a.edit, project_root(), create=True))[0].get("transcription_provider") or "")
        except Exception:
            a.provider = ""
        if a.provider not in PROVIDERS:
            sys.exit(f"--provider is needed ({', '.join(sorted(PROVIDERS))}), or transcription_provider in the settings")
    sys.exit(cmd_run(a))


if __name__ == "__main__":
    main()
