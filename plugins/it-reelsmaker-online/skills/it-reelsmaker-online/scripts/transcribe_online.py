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
  - a word only the cloud heard: a time between its neighbours, marked "est": true (before the first matched word:
    just before it, or in its head when the local model put it at 0.00; never 0.00-0.00);
  - words only the local model has: kept as they are (often a repeat of a retake the cloud tidied away: SKILL.md
    step 3), listed in the report as places to listen to.
--words cloud: whisper-1's own word times (when there is no local model); slower and less precise subtitles.

The audio sent is the core's edit/<id>/audio16k-<source stem>.wav (16 kHz mono on the video's timeline: a phone MOV's
sound track can start ~0.1 s after the picture). The result goes into edit/<id>/transcripts/<source stem>.json, the
file the core reads; the local transcript is kept as <stem>.local.json, an older transcript of another kind as
<stem>.prev.json, the provider's raw answer as <stem>.<provider>.raw.json (no key in any of them).

Providers (references/sources.md): openai — text gpt-transcribe ($0.0045 per minute), word times whisper-1 ($0.006
per minute, only with --words cloud); groq — text only, whisper-large-v3-turbo ($0.04 per hour; a free tier), a
fallback when OpenAI is out of credits or unreachable. Groq's own word times are not used: on the same 97 s video they
were off from the audio-checked local times by more than 0.15 s for 45 % of the words (large-v3: 36 %, whisper-1: 21 %),
and they lost half of the pauses between phrases; its text was as good as gpt-transcribe's (one wrong word in 187).
Files up to 25 MB (about 13 minutes of this WAV).
Fallback: `transcription_fallback=groq` in the settings (reelcfg.py defaults --set ...) — when the main provider fails
(no key, no credits, no network) and a GROQ_API_KEY is set, the text comes from Groq instead, on the same local times.

Paid: it runs with --yes, or without it when the person set `transcription_provider` in the project defaults or the
video's reel.json (their standing choice). Otherwise it prints the price and exits. No key, no network, no credits:
a warning, exit code 2, and the local command to use instead (the edit continues with the core's transcriber).
REELS_OFFLINE=1: no network at all.
"""
import argparse, difflib, json, re, shutil, sys, unicodedata, urllib.error, urllib.request, uuid
from pathlib import Path
from types import SimpleNamespace

try:  # the core's modules: an older core lacks some of them, which would otherwise end in a traceback
    from reels_common import edit_dir, load_config, load_json, locked, project_root, save_json, utf8_stdio, warn
    import transcribe as core
    from transcribe import check_doc, resolve_src, source_wav
except ImportError as exc:
    sys.exit(f"the cloud transcript needs it-reelsmaker >= 1.5.0 (update the core plugin): {exc}")
from reels_online import UA, api_key, err_text, offline, open_url, read_json_response

OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"  # OpenAI-compatible: the same multipart request
PROVIDERS = {
    "openai": {"key": "OPENAI_API_KEY", "url": OPENAI_URL, "host": "https://api.openai.com/",
               "text_model": "gpt-transcribe", "text_usd_min": 0.0045,
               "words_model": "whisper-1", "words_usd_min": 0.006, "max_bytes": 25 * 1000 * 1000},
    # text only: Groq's word times were off by > 0.15 s for 36-45 % of the words on a 97 s Russian video (2026-10-07)
    "groq": {"key": "GROQ_API_KEY", "url": GROQ_URL, "host": "https://api.groq.com/",
             "text_model": "whisper-large-v3-turbo", "text_usd_min": round(0.04 / 60, 5),
             "words_model": None, "words_usd_min": None, "max_bytes": 25 * 1000 * 1000,
             "no_words": "Groq's word times are not used: on a 97 s Russian video they were off from the audio-checked "
                         "local times by more than 0.15 s for 36-45 % of the words and lost half of the pauses "
                         "between phrases; it gives the text, laid on the local word times (--words local)"},
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


def provider_call(name, wav, key, model, language=None, prompt=None, words=False):
    """The provider's transcription endpoint (OpenAI's request shape; Groq takes the same)."""
    if name == "openai":
        return openai_call(wav, key, model, language, prompt, words=words)
    p = PROVIDERS[name]
    fields = [("model", model), ("response_format", "json"), ("temperature", "0")]
    if language:
        fields.append(("language", language))
    if prompt:
        fields.append(("prompt", prompt))
    body, ctype = multipart(fields, [("file", Path(wav).name, Path(wav).read_bytes(), "audio/wav")])
    return post(p["url"], body, {"Authorization": f"Bearer {key}", "Content-Type": ctype}, 600,
                lambda url: str(url).startswith(p["host"]))


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


# scripts written without spaces between words: CJK ideographs, kana, Thai, Lao, Khmer, Myanmar
NO_SPACE = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u0e00-\u0e7f\u0e80-\u0eff"
                      "\u1780-\u17ff\u1000-\u109f]")


def lay_chars(words, text):
    """A text without spaces (Chinese, Japanese, Thai...): there are no words to match, so the cloud's characters are
    matched to the local words' characters and each local word keeps its time with the cloud's characters in it
    (a character only the cloud heard joins the word before it; punctuation follows its character)."""
    lc, owner = [], []
    for k, w in enumerate(words):
        for ch in norm(w["text"]):
            lc.append(ch); owner.append(k)
    cc, punct = [], []
    for ch in text or "":
        if norm(ch):
            cc.append(ch); punct.append("")
        elif not ch.isspace() and cc:
            punct[-1] += ch
    dest = [None] * len(cc)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, lc, [norm(c) for c in cc], autojunk=False).get_opcodes():
        for q, j in enumerate(range(j1, j2)):
            if op in ("equal", "replace") and i2 > i1:
                dest[j] = owner[min(i1 + q * (i2 - i1) // (j2 - j1), i2 - 1)]
            elif owner:  # insert: into the word before (or the first word)
                dest[j] = owner[max(0, i1 - 1)] if i1 > 0 else owner[0]
    texts = ["" for _ in words]
    for j, c in enumerate(cc):
        if dest[j] is not None:
            texts[dest[j]] += c + punct[j]
    out, rep = [], {"same": 0, "fixed": [], "added": [], "local_only": []}
    for w, t in zip(words, texts):
        if not t:
            out.append(dict(w))
            if norm(w["text"]):
                rep["local_only"].append((w["start"], w["text"]))
        elif norm(t) == norm(w["text"]):
            out.append({**w, "text": t}); rep["same"] += 1
        else:
            out.append({**w, "text": t, "local": w["text"]}); rep["fixed"].append((w["start"], w["text"], t))
    return out, rep


def lay_text(words, text):
    """(words with the text's spelling and punctuation, report). words: timed [{text, start, end, ...}] in order."""
    letters = [ch for ch in text or "" if norm(ch)]
    if letters and sum(bool(NO_SPACE.match(ch)) for ch in letters) >= 0.3 * len(letters):
        return lay_chars(words, text)
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
        lo = seq[k - 1]["end"] if k else (max(0.0, seq[e]["start"] - 0.3 * n) if e < len(seq) else 0.0)
        hi = seq[e]["start"] if e < len(seq) else lo + 0.3 * n
        if hi - lo < 0.06 * n and k:  # no gap: the cloud word sits in the previous word's tail
            lo = max(seq[k - 1]["start"], hi - 0.2 * n)
            seq[k - 1]["end"] = round(max(seq[k - 1]["start"], lo), 3)
        elif hi - lo < 0.06 * n and e < len(seq):
            # before the first matched word with no room (the local model put that word at 0.00): the cloud words take
            # the head of it, short, and it starts after them; before, they got 0.00-0.00 (T2: a phrase at the start)
            first = seq[e]
            lo, hi = first["start"], first["start"] + min(0.2 * n, max(0.08 * n, (first["end"] - first["start"]) / 2))
            first["start"] = round(hi, 3)
            first["end"] = round(max(first["end"], hi + 0.06), 3)
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
    return provider in (str(s.get("transcription_provider") or "").lower(),
                        str(s.get("transcription_fallback") or "").lower())


def fallback_of(e, provider):
    """The fallback provider from the settings (transcription_fallback), when it is another one and has its key."""
    try:
        fb = str(load_config(e)[0].get("transcription_fallback") or "").lower()
    except Exception:
        return None
    return fb if fb in PROVIDERS and fb != provider and api_key(PROVIDERS[fb]["key"]) else None


NOTED = set()  # starts of the long words the core's local run has just warned about (see cmd_run)


def long_starts(doc):
    """Starts of the words longer than 1 s: check_doc's note about a merged retake."""
    return {round(float(w["start"]), 2) for w in (doc or {}).get("words", []) if isinstance(w, dict)
            and w.get("type", "word") == "word" and isinstance(w.get("start"), (int, float))
            and isinstance(w.get("end"), (int, float)) and w["end"] - w["start"] > 1.0}


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
    doc = load_json(keep)
    NOTED.update(long_starts(doc))  # the core printed its note on these words
    return doc


def cmd_run(a):
    NOTED.clear()
    project = project_root()
    e = edit_dir(a.edit, project, create=True)
    src = resolve_src(a.source, project, e)
    p = PROVIDERS[a.provider]
    out = e / "transcripts" / f"{src.stem}.json"
    if a.words == "cloud" and not p["words_model"]:
        warn(f"{a.provider}: {p['no_words']}")
        return 2
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
    fb = None if cloud_words else fallback_of(e, a.provider)
    if not key and not fb:
        warn(f"{a.provider}: no {p['key']} key: the person adds it in their own terminal with reels_online.py keys set "
             f"{p['key']}. The edit goes on with the local transcriber: {LOCAL}")
        return 2
    base = None if cloud_words else local_words(e, src, identity, a)
    if base is not None and not any(w.get("type", "word") == "word" and str(w.get("text", "")).strip()
                                    for w in base.get("words", [])):
        base = None  # the local model heard no words: no times to lay the text on (they would be made up)
    if base is None and not cloud_words:  # no local model: the cloud's own word times cost more, so ask again
        print(f"no local word times, so they would come from {a.provider} {p['words_model']} at "
              f"≈ ${secs / 60 * p['words_usd_min']:.3f} instead of ≈ ${price:.3f}: nothing was sent. After the "
              f"person agrees: --words cloud --yes; or install the local transcriber (doctor.py)")
        return 2
    used = a.provider
    try:
        if not key:
            raise NoService(f"no {p['key']} key")
        raw = provider_call(a.provider, wav, key, model, a.language, a.prompt, words=cloud_words)
    except NoService as ex:
        if not fb:
            warn(f"{a.provider} {model}: {ex}. The edit goes on with the local transcriber: {LOCAL}")
            if base is not None and not out.exists():
                save_json(out, base)
            return 2
        # the person's standing fallback (transcription_fallback): the text from it, on the same local word times
        q = PROVIDERS[fb]
        warn(f"{a.provider} {model}: {ex}. Fallback: {fb} {q['text_model']} (text only, the local word times; "
             f"≈ ${secs / 60 * q['text_usd_min']:.4f})")
        used, model, price = fb, q["text_model"], secs / 60 * q["text_usd_min"]
        label = f"{fb} {model} text + faster-whisper timing"
        try:
            raw = provider_call(fb, wav, api_key(q["key"]), model, a.language, a.prompt)
        except NoService as ex2:
            warn(f"{fb} {model}: {ex2}. The edit goes on with the local transcriber: {LOCAL}")
            if base is not None and not out.exists():
                save_json(out, base)
            return 2
    save_json(e / "transcripts" / f"{src.stem}.{used}.raw.json", raw)
    text = str(raw.get("text") or "").strip()
    if cloud_words:
        timed = [{"text": str(w.get("word", "")).strip(), "start": round(float(w["start"]), 3),
                  "end": round(float(w["end"]), 3), "type": "word"}
                 for w in raw.get("words") or [] if str(w.get("word", "")).strip()]
        words, rep = lay_text(timed, text)
        lang = a.language or LANG_CODES.get(str(raw.get("language") or "").lower(), raw.get("language") or "")
    else:
        local = [w for w in base["words"] if w.get("type", "word") == "word"]
        # a hyphenated word split by the local model ("no" "-no" "-no.") is one word again before the cloud text lays on
        # it, or its tails stay as "local only" and show twice; a local transcript cached by an older core has them split
        join = getattr(core, "join_hyphen_parts", None)
        words, rep = lay_text(join(local) if join else local, text)
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
    if out.exists() and not str(old.get("model", "")).startswith(("faster-whisper", a.provider, used)):
        out.replace(out.with_name(f"{src.stem}.prev.json"))
    save_json(out, doc)
    for n in problems:
        # the same long words on the same times: the local run has just named them, once is enough (the note came twice)
        if "longer than 1 s" in n and long_starts(doc) <= NOTED:
            continue
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
                    help="word times: local (default, the core's transcriber) or cloud (whisper-1; not for groq)")
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
