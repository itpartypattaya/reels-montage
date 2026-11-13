# -*- coding: utf-8 -*-
"""A narration in the person's own cloned voice through ElevenLabs, cut by the core as an off-camera voice.

Part of the it-reelsmaker-online add-on. The voice reads the reel's script block by block; the add-on joins the blocks
into edit/<id>/generated/narration.wav, writes its word timings as a core transcript and points cut.json at it, so the
core cuts it like a narration recorded on a phone (reel.json -> voice: off_camera). Paid: `plan` names the price in
credits and a plan id, and a run starts only with the person's "yes" to that very plan (`run --yes --plan <id>`).
Only the person's own voice, with their consent recorded per voice: picked from the account (`use`) or cloned from a
fresh clean recording (`clone`).

    python <core scripts>/addon.py voice list                                     # the account's voices (free)
    python <core scripts>/addon.py voice use <voice_id> --name me --consent own   # an existing voice of the account
    python <core scripts>/addon.py voice clone take.mp3 --name me --consent own [--yes]   # a new voice from a recording
    python <core scripts>/addon.py voice forget me [--remote --yes]               # remove the local record [and the voice]
    python <core scripts>/addon.py voice script edit/<id> --text script.txt --voice me [--language ru]
    python <core scripts>/addon.py voice plan edit/<id>                           # credits per block and the plan id
    python <core scripts>/addon.py voice run edit/<id> --yes --plan <plan id>     # paid: only after the person's "yes"
    python <core scripts>/addon.py voice status|build|check edit/<id>
    python <core scripts>/addon.py voice recover edit/<id> <block> --history <history item id>
    python <core scripts>/addon.py voice clear edit/<id> <block> --not-charged

Files: edit/<id>/voice_script.json (the text, by blocks), voice_gen.json (plan, attempts, build), generated/voice/
(each paid answer, kept whole), generated/narration.wav, transcripts/narration.json; the voices and the consent in
voices.json next to the keys file (~/.config/it-reelsmaker/), never in the project. Key: ELEVENLABS_API_KEY.
"""
import argparse, array, base64, datetime, difflib, hashlib, json, math, os, re, subprocess, sys, time, unicodedata
import urllib.error, uuid, wave
from pathlib import Path

try:  # the core's scripts folder is on sys.path when this runs through the core's addon.py
    from reels_common import (edit_dir, editing_json, effective, load_config, load_json, locked, project_root, rel, run,
                              safe_slug, save_json, utf8_stdio, warn)
except ImportError:
    sys.exit("run this through the core: python <it-reelsmaker scripts>/addon.py voice <command> ...")
import reels_online as ro

# --- What is known about the service (references/sources.md, with the date of the check) --------------------------
# One model in this version: its Russian and its timings are the documented baseline. Credits per character of the
# text, a ceiling; the real charge comes back in the answer's character-cost header and is compared with it.
# credits_per_char is the ceiling of the plan; seen_per_char is what the live service charged (character-cost header,
# 2026-11-13, Starter: 17 credits for 42 characters, 4 for 11 and 9, 66 for 165), shown as the likely price.
MODELS = {"eleven_multilingual_v2": {"credits_per_char": 1.0, "seen_per_char": 0.4, "max_chars": 10000,
                                     "language_code": False}}
RATES_CHECKED = "2026-11-13"
# output formats: the codec and the sample rate of the answer's audio. Both checked live on Starter (2026-11-13): the
# decoded length equals the alignment's last end in both
OUTPUT_FORMATS = {"mp3_44100_128": ("mp3", 44100), "pcm_24000": ("pcm", 24000)}
DEFAULT_FORMAT = "mp3_44100_128"
VOICE_SETTINGS = {"stability": (0.0, 1.0, 0.5), "similarity_boost": (0.0, 1.0, 0.75), "style": (0.0, 0.0, 0.0),
                  "use_speaker_boost": (None, None, True), "speed": (0.7, 1.2, 1.0)}
NORMALIZATION = ("auto", "on", "off")
BLOCK_MAX = 1000  # characters: a block is about a minute of speech, its answer far below the 20 MB limit
# HTTP statuses after which nothing was charged: only those confirmed on the live service (step 0, sources.md). Any
# other failure after the request left this computer is "unknown": not sent again by itself.
# checked live 2026-11-13: 401 (a key without the permission) and 404 voice_not_found (no character-cost header, no
# history item, the balance unchanged)
NOT_CHARGED = {401, 404}
STALE_SUBMIT = 900   # s: a `submitting` reservation younger than this may be a request in flight (its timeout is 180 s)
# One paid step at a time for the whole account (every reel, every terminal): the balance check and the request of a
# block happen under this lock, so two runs cannot both spend the same credits. A run waits SPEND_WAIT s for it.
SPEND_WAIT = 240

# --- Consent: per voice, own voice only in this version --------------------------------------------------------
CONSENT_VERSION = "own-voice/1 (2026-11-13)"
CONSENT_TEXT = ("this is my own voice; I am an adult; I agree that it reads the scripts of my own videos through "
                "ElevenLabs with this add-on")
PURPOSE = "narration of the owner's own videos"

# --- Joining blocks --------------------------------------------------------------------------------------------
SR = 48000            # every block is decoded to 48 kHz mono PCM; blocks are joined by sample counts
LEAD, TAIL = 0.05, 0.25  # seconds kept before the first word and after the last word of a block
FADE = 0.005          # a short fade at each trimmed edge (no click)
PAUSE_SENTENCE, PAUSE_PHRASE, PAUSE_MAX = 0.45, 0.25, 1.0
SPOKEN_SIGNS = set("%$€₽£№#&+=°")  # read aloud ("percent"): part of a word's time, unlike quotes and stops
SENTENCE_END = re.compile(r"[.!?…]['\"»”)\]]*\s*$")

SCRIPT, GEN = "voice_script.json", "voice_gen.json"


class ApiError(RuntimeError):
    def __init__(self, status, code, message, request_id=None):
        super().__init__(f"HTTP {status}" + (f" {code}" if code else "") + (f": {message}" if message else ""))
        self.status, self.code, self.message, self.request_id = status, code, message, request_id


class AlignError(ValueError):
    pass


class BrokenAnswer(AlignError):
    """The kept answer is not whole: paid, but nothing usable; the block becomes unknown (recover it from history)."""


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_s(iso):
    """Seconds since an now_iso() time; a missing or bad one counts as new (the safe side)."""
    try:
        t = datetime.datetime.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return 0.0
    return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()


YO, YE = chr(0x451), chr(0x435)  # the Cyrillic letters yo and ye: one is often written for the other


def canon(s):
    """A form for comparing text: lower case, yo as ye, one kind of quote and dash, no accents."""
    s = unicodedata.normalize("NFKC", str(s)).lower().replace(YO, YE)
    s = s.translate(str.maketrans({"«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "’": "'", "‘": "'",
                                   "–": "-", "—": "-", "‑": "-", "́": None}))
    return s


def bare(word):
    """A word without the punctuation around it, for matching."""
    return re.sub(r"^[\W_]+|[\W_]+$", "", canon(word))


def has_letters(token):
    return any(ch.isalnum() for ch in token)


# --- The API ---------------------------------------------------------------------------------------------------

PERMISSION_HINT = ("in ElevenLabs open Developers → API keys, edit this key and allow it (it needs: Text to Speech, "
                   "Voices read, User read for the balance, History read for recovery; Voices write only to clone or "
                   "delete a voice)")


def api_error(ex):
    """An urllib HTTPError -> ApiError with the service's code and a message without secrets."""
    try:
        raw = ex.read(64 << 10)
    except Exception:
        raw = b""
    code = msg = rid = None
    try:
        d = json.loads(raw.decode("utf-8", "replace")).get("detail")
        if isinstance(d, dict):
            code = d.get("status") or d.get("code")
            msg, rid = d.get("message"), d.get("request_id")
        elif isinstance(d, list) and d:
            msg = "; ".join(str(x.get("msg") or x) for x in d[:3] if isinstance(x, dict))
            code = "invalid_request"
        elif isinstance(d, str):
            msg = d
    except Exception:
        msg = raw[:200].decode("utf-8", "replace") if raw else ex.reason
    if code == "missing_permissions":
        msg = f"{msg} — {PERMISSION_HINT}"
    return ApiError(ex.code, code, ro.scrub(msg or "")[:400], rid)


def need_key():
    if ro.offline():
        sys.exit("REELS_OFFLINE=1: network access is off; ElevenLabs is not reachable")
    key = ro.api_key(ro.VOICE_KEYS["elevenlabs"])
    if not key:
        sys.exit("no ELEVENLABS_API_KEY: the person adds it in their own terminal: "
                 f"python {Path(ro.__file__).resolve()} keys set ELEVENLABS_API_KEY")
    return key


def api(method, path, key, body=None, content_type="application/json", timeout=60, limit=ro.MAX_JSON):
    """(status, headers, body bytes); an HTTP error -> ApiError."""
    try:
        return ro.elevenlabs(method, path, key, body, content_type, timeout, limit)
    except urllib.error.HTTPError as ex:
        raise api_error(ex) from None


def api_json(method, path, key, body=None, **kw):
    _, _, raw = api(method, path, key, body, **kw)
    return json.loads(raw.decode("utf-8"))


def spend_lock():
    """The account-wide lock file's base path (next to the keys file and voices.json)."""
    return ro.KEYS_FILE.parent / "elevenlabs-spend"


def balance(key):
    """Credits left in this billing period (usage-based overage is not counted: it costs extra money)."""
    sub = api_json("GET", "/v1/user/subscription", key, timeout=20)
    limit, used = sub.get("character_limit"), sub.get("character_count")
    if not isinstance(limit, (int, float)) or not isinstance(used, (int, float)):
        raise ApiError(200, "no_balance", "the subscription answer has no character_limit/character_count")
    return int(limit - used), sub


# --- Voices and consent: voices.json next to the keys file -----------------------------------------------------

def load_voices():
    f = ro.voices_file()
    try:
        doc = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except ValueError as ex:
        sys.exit(f"{f}: not valid JSON ({ex}); fix it by hand first")
    doc = doc if isinstance(doc, dict) else {}
    doc.setdefault("voices", {})
    return doc


def save_voices(doc):
    ro.write_private(ro.voices_file(), json.dumps(doc, ensure_ascii=False, indent=1) + "\n")


def voice_name(name):
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,39}$", str(name or "")):
        sys.exit(f"{name!r}: a voice name is lower-case letters, digits, - and _ (like me or anna)")
    return name


def consent_record():
    return {"kind": "own", "version": CONSENT_VERSION, "text": CONSENT_TEXT, "purpose": PURPOSE, "at": now_iso()}


def require_consent(a):
    if a.consent != "own":
        sys.exit("only the person's own voice in this version. Read this to the person and, after their explicit "
                 f"“yes”, repeat with --consent own: “{CONSENT_TEXT}”. Someone else's voice is not supported yet: it "
                 "needs that person's written consent and a way to withdraw it.")


def voice_record(name):
    """The local record of a voice usable for narration, or exit with the reason."""
    rec = load_voices()["voices"].get(name)
    if not rec:
        sys.exit(f"no voice {name!r} in {ro.voices_file()}: pick one with `voice use <voice_id> --name {name} "
                 f"--consent own` (`voice list` shows the account's voices)")
    c = rec.get("consent") or {}
    if rec.get("owner") != "self" or c.get("kind") != "own" or not c.get("at"):
        sys.exit(f"voice {name!r}: no recorded consent of its owner; record it again with voice use ... --consent own")
    if rec.get("verification") != "ok":
        sys.exit(f"voice {name!r}: ElevenLabs asks to verify this voice; finish the verification in the ElevenLabs "
                 f"account, then `voice use {rec.get('voice_id')} --name {name} --consent own` again")
    return rec


def cmd_list(a):
    key = need_key()
    try:
        voices = api_json("GET", "/v1/voices", key, timeout=30).get("voices") or []
    except ApiError as ex:
        sys.exit(f"ElevenLabs: {ex}")
    local = {r.get("voice_id"): n for n, r in load_voices()["voices"].items()}
    mine = [v for v in voices if v.get("category") != "premade"]
    print(f"{len(mine)} voice(s) of the account (and {len(voices) - len(mine)} ready-made library voices):")
    for v in mine:
        ver = (v.get("voice_verification") or {}).get("requires_verification")
        samples = v.get("samples") or []
        secs = sum(s.get("duration_secs") or 0 for s in samples)
        made = v.get("created_at_unix")
        made = datetime.datetime.fromtimestamp(made, datetime.timezone.utc).strftime("%Y-%m-%d") if made else "?"
        print(f"  {v.get('name')!r}  {v.get('voice_id')}  {v.get('category')}  created {made}  "
              f"samples {len(samples)} ({secs:.0f} s)  verification {'REQUIRED' if ver else 'not required'}"
              + (f"  local name: {local[v.get('voice_id')]}" if v.get("voice_id") in local else ""))
        if v.get("preview_url"):
            print(f"    listen: {v['preview_url']}")
    print("Let the person listen and say whose voice it is. Only their own voice: voice use <voice_id> --name <name> "
          "--consent own")


def cmd_use(a):
    require_consent(a)
    name = voice_name(a.name)
    if not re.match(r"^[A-Za-z0-9]{8,40}$", a.voice_id or ""):
        sys.exit(f"{a.voice_id!r} does not look like an ElevenLabs voice id (voice list shows them)")
    key = need_key()
    try:
        v = api_json("GET", f"/v1/voices/{a.voice_id}", key, timeout=30)
    except ApiError as ex:
        sys.exit(f"ElevenLabs: {ex}")
    if v.get("category") == "premade" or v.get("is_owner") is False:
        sys.exit(f"{a.voice_id} is not a voice of this account (a library or shared voice) — not the person's own voice")
    need = bool((v.get("voice_verification") or {}).get("requires_verification"))
    with ro.file_lock(ro.voices_file()):
        doc = load_voices()
        old = doc["voices"].get(name)
        if old and old.get("voice_id") != a.voice_id:
            sys.exit(f"the name {name!r} already stands for another voice; voice forget {name} first, or pick another name")
        doc["voices"][name] = {"voice_id": a.voice_id, "name": v.get("name"), "owner": "self",
                               "consent": consent_record(), "created_by_addon": bool((old or {}).get("created_by_addon")),
                               "verification": "required" if need else "ok", "added": (old or {}).get("added") or now_iso()}
        save_voices(doc)
    print(f"voice {name!r} = {v.get('name')!r} ({a.voice_id}); consent recorded ({CONSENT_VERSION}) in {ro.voices_file()}")
    if need:
        print("ElevenLabs asks to verify this voice: finish it in the account; narration with it is blocked until then")
    elif v.get("preview_url"):
        print(f"listen before the first reel: {v['preview_url']}")


def level_of(f):
    """(duration s, RMS dB, true peak dBTP) of a recording, measured by ffmpeg."""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(f), "-af",
             "ebur128=peak=true,astats=measure_overall=RMS_level:measure_perchannel=none", "-f", "null", "-"], check=False)
    err = r.stderr or ""
    rms = re.findall(r"RMS level dB:\s*(-?[\d.]+|-inf)", err)
    peak = re.search(r"True peak:\s*\n\s*Peak:\s*(-?[\d.]+|-inf)", err)
    dur = re.findall(r"time=(\d+):(\d+):([\d.]+)", err) or re.findall(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if not rms or not peak or not dur:
        raise RuntimeError(f"{f}: could not measure the recording (ffmpeg): {err[-300:]}")
    h, m, s = dur[-1]
    tofloat = lambda x: -math.inf if x == "-inf" else float(x)
    return int(h) * 3600 + int(m) * 60 + float(s), tofloat(rms[-1]), tofloat(peak.group(1))


def sample_problems(files):
    """(errors, warnings, total seconds) of the recordings for a clone: 1-3 min in all, every file >= 5 s, true peak
    at most -3 dBTP, RMS about -23..-18 dB. Who speaks is not checked: the person confirms it."""
    errs, warns, total = [], [], 0.0
    for f in files:
        if not Path(f).is_file():
            errs.append(f"{f}: no such file")
            continue
        try:
            dur, rms, peak = level_of(f)
        except RuntimeError as ex:
            errs.append(str(ex))
            continue
        total += dur
        if dur < 5:
            errs.append(f"{f}: {dur:.1f} s; every recording is at least 5 s")
        if peak > -3.0:
            errs.append(f"{f}: true peak {peak:.1f} dBTP, above -3 dBTP: record quieter or lower the level")
        if not -23.0 <= rms <= -18.0:
            warns.append(f"{f}: RMS {rms:.1f} dB, outside -23..-18 dB (long silences lower it; a clean, even level "
                         f"clones better)")
    if files and not errs and not 60 <= total <= 180:
        errs.append(f"{total:.0f} s in all; a clone needs 1-3 minutes of one clean voice")
    return errs, warns, total


def multipart(fields, files):
    boundary = "----itreels" + uuid.uuid4().hex
    out = []
    for k, v in fields:
        out += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8")]
    for k, path in files:
        name = Path(path).name.replace('"', "")
        out += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{name}\"\r\n"
                f"Content-Type: audio/mpeg\r\n\r\n".encode("utf-8"), Path(path).read_bytes(), b"\r\n"]
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def cmd_clone(a):
    require_consent(a)
    name = voice_name(a.name)
    if load_voices()["voices"].get(name):
        sys.exit(f"the name {name!r} is taken; voice forget {name} first, or pick another name")
    errs, warns, total = sample_problems(a.files)
    for w in warns:
        warn(w)
    if errs:
        sys.exit("not cloning:\n  " + "\n  ".join(errs))
    print(f"ready to clone {name!r} from {len(a.files)} recording(s), {total:.0f} s: they go to ElevenLabs and stay "
          "there with no stated term (PRIVACY.md); turn off the use of your data for training in the account settings "
          "BEFORE uploading. The person confirms the recording is only their own voice.")
    if not a.yes:
        print("This needs the person's explicit “yes”; then repeat with --yes")
        return
    key = need_key()
    tmp = Path(project_root()) / ".voice-clone-tmp" / uuid.uuid4().hex
    try:
        send = []
        for k, f in enumerate(a.files):
            f = Path(f)
            if f.suffix.lower() == ".mp3" and int(json.loads(run(["ffprobe", "-v", "error", "-show_entries",
                                                                   "format=bit_rate", "-of", "json", str(f)]).stdout
                                                              or "{}").get("format", {}).get("bit_rate") or 0) >= 128000:
                send.append(f)
                continue
            tmp.mkdir(parents=True, exist_ok=True)
            out = tmp / f"sample-{k + 1}.mp3"  # the service asks for MP3 >= 128 kbit/s
            run(["ffmpeg", "-v", "error", "-y", "-i", str(f), "-vn", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "192k",
                 str(out)])
            send.append(out)
        body, ctype = multipart([("name", name), ("remove_background_noise", "true" if a.remove_noise else "false"),
                                 ("description", "it-reelsmaker narration voice")], [("files", f) for f in send])
        try:
            res = api_json("POST", "/v1/voices/add", key, body, content_type=ctype, timeout=180)
        except ApiError as ex:
            sys.exit(f"ElevenLabs did not clone the voice: {ex}")
    finally:
        if tmp.exists():
            for f in tmp.iterdir():
                f.unlink()
            tmp.rmdir()
            try:
                tmp.parent.rmdir()
            except OSError:
                pass
    vid = res.get("voice_id")
    if not vid:
        sys.exit("ElevenLabs answered without a voice_id; check the account's voices (voice list)")
    need = bool(res.get("requires_verification") or res.get("library_voice_match"))
    with ro.file_lock(ro.voices_file()):
        doc = load_voices()
        doc["voices"][name] = {"voice_id": vid, "name": name, "owner": "self", "consent": consent_record(),
                               "created_by_addon": True, "verification": "required" if need else "ok", "added": now_iso()}
        save_voices(doc)
    print(f"voice {name!r} cloned: {vid}" + ("; ElevenLabs asks to verify it in the account before use" if need else ""))


def cmd_forget(a):
    name = voice_name(a.name)
    rec = load_voices()["voices"].get(name)
    if not rec:
        sys.exit(f"no voice {name!r} in {ro.voices_file()}")
    if a.remote:
        if not rec.get("created_by_addon"):
            sys.exit(f"{name!r} was not created by the add-on (it was picked with voice use): it is not deleted from "
                     f"ElevenLabs by this command; delete it in the account if you want to. Without --remote only the "
                     f"local record goes.")
        if not a.yes:
            print(f"ready to delete the voice {rec['voice_id']} from ElevenLabs (cannot be undone). This needs the "
                  f"person's explicit “yes”; then repeat with --yes")
            return
        key = need_key()
        try:
            api("DELETE", f"/v1/voices/{rec['voice_id']}", key, timeout=30)
        except ApiError as ex:
            if ex.status != 404:
                sys.exit(f"ElevenLabs did not delete the voice: {ex}")
        print(f"deleted from ElevenLabs: {rec['voice_id']}. That the samples and the history of the voice are deleted "
              f"too is not stated by the service (PRIVACY.md)")
    with ro.file_lock(ro.voices_file()):
        doc = load_voices()
        doc["voices"].pop(name, None)
        save_voices(doc)
    print(f"local record {name!r} removed" + ("" if a.remote else "; the voice stays in the ElevenLabs account"))


# --- The script: edit/<id>/voice_script.json ------------------------------------------------------------------

def split_blocks(text):
    """Paragraphs (blank lines) -> blocks of at most BLOCK_MAX characters; a long paragraph splits at sentences."""
    blocks = []
    for para in re.split(r"\n\s*\n", text.replace("\r\n", "\n").lstrip("﻿")):
        para = re.sub(r"\s+", " ", para).strip()
        if not para:
            continue
        cur = ""
        for sent in re.split(r"(?<=[.!?…])\s+", para):
            if len(sent) > BLOCK_MAX:
                sys.exit(f"a sentence of {len(sent)} characters (over {BLOCK_MAX}): split it: {sent[:60]}…")
            if cur and len(cur) + 1 + len(sent) > BLOCK_MAX:
                blocks.append(cur)
                cur = sent
            else:
                cur = f"{cur} {sent}".strip()
        if cur:
            blocks.append(cur)
    return blocks


def cmd_script(a):
    e = edit_dir(a.edit, create=True)
    f = e / SCRIPT
    if f.exists() and not a.force:
        sys.exit(f"{f} exists: edit it, or --force to write it again from the text")
    voice_name(a.voice)
    text = Path(a.text).read_text(encoding="utf-8")
    blocks = split_blocks(text)
    if not blocks:
        sys.exit(f"{a.text}: no text")
    doc = {"voice": a.voice, "language": a.language, "blocks": [{"id": f"b{k + 1}", "text": t}
                                                                 for k, t in enumerate(blocks)]}
    save_json(f, doc)
    print(f"{f}: {len(blocks)} block(s), {sum(len(b) for b in blocks)} characters; the text is read word for word: "
          f"check it, numbers best written in words (voice plan edit/<id> shows the price)")


def load_script(e):
    """The script, checked: (doc, problems)."""
    doc = load_json(e / SCRIPT)
    if not isinstance(doc, dict):
        sys.exit(f"no {e / SCRIPT}: voice script edit/<id> --text <file> --voice <name>")
    errs = []
    blocks = doc.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        errs.append("no blocks")
        blocks = []
    seen = set()
    for k, b in enumerate(blocks):
        if not isinstance(b, dict):
            errs.append(f"block {k}: not an object")
            continue
        bid, t = b.get("id"), b.get("text")
        if not re.match(r"^[A-Za-z0-9_-]{1,32}$", str(bid or "")) or bid in seen:
            errs.append(f"block {k}: id {bid!r} is missing, repeated or not a short slug")
        seen.add(bid)
        if not isinstance(t, str) or not t.strip():
            errs.append(f"block {bid}: no text")
        elif len(t) > BLOCK_MAX:
            errs.append(f"block {bid}: {len(t)} characters, over {BLOCK_MAX}: split it")
        elif any(unicodedata.category(ch) == "Cc" for ch in t):
            errs.append(f"block {bid}: control characters in the text")
        elif not has_letters(t):
            errs.append(f"block {bid}: no words in the text")
        p = b.get("pause_after")
        if p is not None and (not isinstance(p, (int, float)) or not 0 <= p <= PAUSE_MAX):
            errs.append(f"block {bid}: pause_after is seconds from 0 to {PAUSE_MAX}")
    if doc.get("language") is not None and not re.match(r"^[a-z]{2,3}$", str(doc["language"])):
        errs.append(f"language {doc['language']!r}: a code like ru or en")
    if errs:
        sys.exit(f"{e / SCRIPT}:\n  " + "\n  ".join(errs))
    return doc


def request_of(e, doc):
    """Everything that goes into the paid requests, checked: {voice, rec, model, format, ...,
    blocks: [{id, text, body, path, fingerprint, chars, credits}]}."""
    s, *_ = load_config(e)
    name = voice_name(doc.get("voice") or "")
    rec = voice_record(name)
    model = doc.get("model") or s.get("voice_model") or "eleven_multilingual_v2"
    if model not in MODELS:
        sys.exit(f"model {model!r} is not supported by the add-on yet (checked: {', '.join(MODELS)}); its rate and "
                 f"timings are unconfirmed")
    spec = MODELS[model]
    fmt = doc.get("output_format") or DEFAULT_FORMAT
    if fmt not in OUTPUT_FORMATS:
        sys.exit(f"output_format {fmt!r}: supported {', '.join(OUTPUT_FORMATS)}")
    norm = doc.get("normalization") or "auto"
    if norm not in NORMALIZATION:
        sys.exit(f"normalization {norm!r}: one of {', '.join(NORMALIZATION)}")
    vs = {k: d for k, (_, _, d) in VOICE_SETTINGS.items()}
    for layer in (s.get("voice_settings"), doc.get("settings")):
        for k, v in (layer or {}).items():
            if k not in VOICE_SETTINGS:
                sys.exit(f"voice setting {k!r} is unknown (known: {', '.join(VOICE_SETTINGS)})")
            lo, hi, _ = VOICE_SETTINGS[k]
            if lo is None:
                if not isinstance(v, bool):
                    sys.exit(f"voice setting {k}: true or false")
            elif not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
                why = " (above 0 it costs more, at a rate not confirmed)" if k == "style" else ""
                sys.exit(f"voice setting {k}={v!r}: from {lo} to {hi}{why}")
            vs[k] = v
    context = doc.get("context", True) is not False
    blocks = doc["blocks"]
    out = []
    for k, b in enumerate(blocks):
        if len(b["text"]) > spec["max_chars"]:
            sys.exit(f"block {b['id']}: over the model's {spec['max_chars']} characters")
        body = {"text": b["text"], "model_id": model, "voice_settings": vs, "apply_text_normalization": norm}
        if context and k > 0:
            body["previous_text"] = blocks[k - 1]["text"]
        if context and k + 1 < len(blocks):
            body["next_text"] = blocks[k + 1]["text"]
        if spec["language_code"] and doc.get("language"):
            body["language_code"] = doc["language"]
        path = f"/v1/text-to-speech/{rec['voice_id']}/with-timestamps?output_format={fmt}"
        fp = hashlib.sha256(json.dumps({"path": path, "body": body}, sort_keys=True, ensure_ascii=False)
                            .encode("utf-8")).hexdigest()
        out.append({"id": b["id"], "text": b["text"], "body": body, "path": path, "fingerprint": fp,
                    "chars": len(b["text"]), "credits": math.ceil(len(b["text"]) * spec["credits_per_char"]),
                    "pause_after": b.get("pause_after")})
    return {"voice": name, "rec": rec, "model": model, "format": fmt, "language": doc.get("language"),
            "settings": s, "blocks": out}


# --- Attempts: voice_gen.json -> attempts[fingerprint] ----------------------------------------------------------
# submitting (reserved before the request) -> received (the whole answer is on disk) -> saved (audio and timings
# taken out) -> done (in the built narration). A failure after the request left: unknown, never sent again by itself.

READY = ("received", "saved", "done")
UNRESOLVED = ("submitting", "unknown")


def gen_of(e):
    g = load_json(e / GEN, {}) or {}
    g.setdefault("attempts", {})
    return g


def plan_of(req, gen):
    """(blocks to buy, blocks ready, blocks blocked, plan id, total credits)."""
    buy, ready, blocked = [], [], []
    for b in req["blocks"]:
        at = gen["attempts"].get(b["fingerprint"])
        state = (at or {}).get("state")
        (ready if state in READY else blocked if state in UNRESOLVED else buy).append(b)
    total = sum(b["credits"] for b in buy)
    pid = hashlib.sha256(json.dumps({"voice": req["voice"], "consent": req["rec"]["consent"]["at"],
                                     "blocks": [[b["id"], b["fingerprint"], b["credits"]] for b in buy],
                                     "total": total}, sort_keys=True).encode()).hexdigest()[:12]
    return buy, ready, blocked, pid, total


def blocked_message(b, at):
    return (f"block {b['id']}: a paid request is {at.get('state')}" + (f" (request id {at['request_id']})"
                                                                       if at.get("request_id") else "")
            + f" ({at.get('error') or 'no answer recorded'}). It is not sent again by itself: look at the ElevenLabs "
              f"history; found it → voice recover edit/<id> {b['id']} --history <item id>; sure nothing was "
              f"charged → voice clear edit/<id> {b['id']} --not-charged")


def cmd_plan(a):
    e = edit_dir(a.edit)
    req = request_of(e, load_script(e))
    with editing_json(e / GEN, {}) as gen:
        gen.setdefault("attempts", {})
        buy, ready, blocked, pid, total = plan_of(req, gen)
        bal, why = None, None
        if buy:
            key = ro.api_key(ro.VOICE_KEYS["elevenlabs"])
            if ro.offline() or not key:
                why = "REELS_OFFLINE=1" if ro.offline() else "no ELEVENLABS_API_KEY"
            else:
                try:
                    bal, _ = balance(key)
                except (ApiError, OSError, ValueError) as ex:
                    why = ro.err_text(ex, 300)
        gen["plan"] = {"id": pid, "at": now_iso(), "voice": req["voice"], "model": req["model"], "format": req["format"],
                       "rates_checked": RATES_CHECKED, "credits_max": total, "balance": bal,
                       "blocks": [{"id": b["id"], "fingerprint": b["fingerprint"], "chars": b["chars"],
                                   "credits_max": b["credits"]} for b in buy]}
    print(f"voice {req['voice']!r}, model {req['model']} ({MODELS[req['model']]['credits_per_char']:g} credit per "
          f"character, rate checked {RATES_CHECKED}), {len(req['blocks'])} block(s):")
    for b in req["blocks"]:
        st = "ready (already paid)" if b in ready else "BLOCKED" if b in blocked else f"≤ {b['credits']} credits"
        print(f"  {b['id']}: {b['chars']} characters — {st}")
    for b in blocked:
        print("✗ " + blocked_message(b, gen["attempts"][b["fingerprint"]]))
    if not buy:
        print("nothing to buy" + (": voice build edit/<id> joins the ready blocks" if not blocked else ""))
        return
    seen = MODELS[req["model"]].get("seen_per_char")
    likely = f", likely about {math.ceil(sum(b['chars'] for b in buy) * seen)} (as charged {RATES_CHECKED})" if seen else ""
    print(f"plan {pid}: at most {total} credits for {len(buy)} block(s){likely}. The real charge comes back per block and "
          f"is compared with the ceiling; dollars only roughly, by the plan's price per credit")
    if bal is not None:
        print(f"balance: {bal} credits left in this period" + ("" if bal >= total else
                                                                "  ✗ NOT ENOUGH: the run would stop"))
    else:
        print(f"balance: not checked ({why}); the run checks it before every block and stops without it")
    if blocked:
        print("the blocked blocks must be resolved first")
    print(f"After the person's explicit “yes” to this price: voice run edit/<id> --yes --plan {pid}")


# --- Run ---------------------------------------------------------------------------------------------------------

def write_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def keep_headers(h):
    return {k: h[k] for k in ("request-id", "character-cost", "x-character-count", "history-item-id", "x-trace-id",
                              "content-type", "date") if k in h}


def reserve(e, b, approved_fp, owner, voice):
    """Reserve the block's request under the lock, checking again that it is the approved request: the script, the
    voice and its consent read now must give the same fingerprint. None: someone else has it."""
    with editing_json(e / GEN, {}) as gen:
        gen.setdefault("attempts", {})
        req = request_of(e, load_script(e))  # read again, under the lock
        cur = next((x for x in req["blocks"] if x["id"] == b["id"]), None)
        if cur is None or cur["fingerprint"] != approved_fp or req["voice"] != voice:
            sys.exit(f"block {b['id']}: the script, the voice or the settings changed after the plan; nothing sent. "
                     f"voice plan edit/<id> again and ask the person again")
        at = gen["attempts"].get(approved_fp)
        if at:
            print(f"block {b['id']}: already {at.get('state')} in another run; not sent")
            return None
        gen["attempts"][approved_fp] = {"block": b["id"], "state": "submitting", "owner": owner, "at": now_iso(),
                                        "credits_max": b["credits"], "plan": gen.get("plan", {}).get("id")}
    return owner


def update_attempt(e, fp, owner, **fields):
    with editing_json(e / GEN, {}) as gen:
        at = gen.setdefault("attempts", {}).get(fp)
        if not at or at.get("owner") != owner:
            raise RuntimeError(f"the reservation of {fp[:12]} changed in another run; check voice status")
        if fields.get("state") is None and "state" in fields:
            gen["attempts"].pop(fp)
            return
        at.update(fields)


def submit(e, b, key, owner):
    """Send one paid request. Returns True on an answer kept on disk; False when the run must stop."""
    fp = b["fingerprint"]
    try:
        status, headers, raw = api("POST", b["path"], key, b["body"], timeout=180)
    except ApiError as ex:
        if ex.status in NOT_CHARGED:
            update_attempt(e, fp, owner, state=None)
            print(f"✗ block {b['id']}: ElevenLabs refused the request ({ex}); nothing was charged")
            return False
        update_attempt(e, fp, owner, state="unknown", error=str(ex)[:300], request_id=ex.request_id, at_error=now_iso())
        print(f"✗ {blocked_message(b, {'state': 'unknown', 'error': str(ex)[:200], 'request_id': ex.request_id})}")
        return False
    except Exception as ex:  # timeout, a broken connection, a cut answer: the request may have been charged
        update_attempt(e, fp, owner, state="unknown", error=ro.err_text(ex, 300), at_error=now_iso())
        print(f"✗ {blocked_message(b, {'state': 'unknown', 'error': ro.err_text(ex, 160)})}")
        return False
    kept = keep_headers(headers)
    rid = kept.get("request-id")
    cost = kept.get("character-cost") or kept.get("x-character-count")
    resp = response_path(e, fp, owner)
    try:
        write_atomic(resp, json.dumps({"saved_at": now_iso(), "status": status, "headers": kept,
                                       "body_text": raw.decode("utf-8", "replace")}, ensure_ascii=False).encode("utf-8"))
    except OSError as ex:
        update_attempt(e, fp, owner, state="unknown", request_id=rid, character_cost=cost, at_error=now_iso(),
                       error=f"the answer came but could not be saved: {ro.err_text(ex, 160)}")
        print(f"✗ block {b['id']}: the paid answer (request id {rid}) could not be saved ({ro.err_text(ex, 120)}); "
              f"free some disk space, then voice recover edit/<id> {b['id']} --history <item id>")
        return False
    update_attempt(e, fp, owner, state="received", response=rel(resp, e), request_id=rid,
                   character_cost=int(cost) if str(cost or "").isdigit() else cost, received_at=now_iso())
    print(f"{b['id']}: answer received (request id {rid}, charged {cost if cost is not None else '?'} credits, "
          f"ceiling {b['credits']})")
    return True


def decode_audio(data, fmt, out):
    """The answer's audio bytes -> a 48 kHz mono 16-bit WAV; returns its sample count."""
    codec, rate = OUTPUT_FORMATS[fmt]
    out.parent.mkdir(parents=True, exist_ok=True)
    src = out.with_name(f".{out.stem}.{uuid.uuid4().hex[:8]}.{codec}")
    tmp = out.with_name(f".{out.stem}.{uuid.uuid4().hex[:8]}.wav")
    try:
        src.write_bytes(data)
        inp = ["-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", str(src)] if codec == "pcm" else ["-i", str(src)]
        run(["ffmpeg", "-v", "error", "-y", *inp, "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(tmp)])
        with wave.open(str(tmp), "rb") as w:
            n = w.getnframes()
        os.replace(tmp, out)
        return n
    finally:
        for f in (src, tmp):
            if f.exists():
                f.unlink()


def tokens_of(chars, starts, ends):
    """Whitespace-separated runs of an alignment: [(token, start, end)] with the times of its letters and digits."""
    out, cur = [], []
    for ch, s, t in list(zip(chars, starts, ends)) + [(" ", None, None)]:
        if ch.isspace():
            if cur:
                tok = "".join(c for c, _, _ in cur)
                timed = [(s0, t0) for c, s0, t0 in cur if c.isalnum() or c in SPOKEN_SIGNS] or \
                    [(s0, t0) for _, s0, t0 in cur]
                out.append((tok, timed[0][0], timed[-1][1]))
                cur = []
        else:
            cur.append((ch, s, t))
    return out


def check_alignment(al, what):
    if not isinstance(al, dict):
        raise AlignError(f"the answer has no {what}")
    ch, s, t = al.get("characters"), al.get("character_start_times_seconds"), al.get("character_end_times_seconds")
    if not (isinstance(ch, list) and isinstance(s, list) and isinstance(t, list)) or not len(ch) == len(s) == len(t):
        raise AlignError(f"{what}: characters and times differ in length")
    for k, (a, b) in enumerate(zip(s, t)):
        if not all(isinstance(x, (int, float)) and math.isfinite(x) and x >= 0 for x in (a, b)) or b < a:
            raise AlignError(f"{what}: character {k} {ch[k]!r} has times {a}..{b}")
    return [str(c) for c in ch], s, t


def words_for(text, al, nal=None):
    """The script's words with times. The alignment of the text itself first: same characters → their times. Where the
    answer's text differs (numbers spoken as words), a stretch is matched to the script's words explicitly; a stretch
    that cannot be matched is an error naming its place. Each alignment's characters go with its own times only."""
    script = [w for w in text.split() if w]
    errors = []
    for what, a in (("alignment", al), ("normalized_alignment", nal)):
        if a is None:
            continue
        try:
            ch, s, t = check_alignment(a, what)
            heard = tokens_of(ch, s, t)
            return attach(map_words(script, heard, what)), what
        except AlignError as ex:
            errors.append(str(ex))
    raise AlignError("; ".join(errors) or "the answer has no alignment")


def map_words(script, heard, what):
    """[(script word, start, end)] for every script word, from the heard tokens [(token, start, end)]."""
    a = [bare(w) for w in script]
    b = [bare(t) for t, _, _ in heard]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out += [(script[i], heard[j][1], heard[j][2]) for i, j in zip(range(i1, i2), range(j1, j2))]
            continue
        words, got = script[i1:i2], heard[j1:j2]
        # punctuation-only tokens on either side carry no sound of their own: they go with a neighbour
        if not [w for w in words if has_letters(w)]:
            spoken = [g[0] for g in got if has_letters(g[0])]
            if spoken:
                raise AlignError(f"{what}: “{' '.join(spoken)}” was spoken but is not in the script (after word {i1})")
            out += [(w, None, None) for w in words]
            continue
        if not [g for g in got if has_letters(g[0])]:
            raise AlignError(f"{what}: no sound for “{' '.join(words)}” (word {i1 + 1} of the script)")
        if len(words) == len(got):  # the same number of words spelled differently: one to one
            out += [(w, g[1], g[2]) for w, g in zip(words, got)]
            continue
        if len(words) == 1 and (re.search(r"[\d%$€₽№#@&+=/]", words[0]) or re.search(r"\w\.\w", words[0])):
            # one number, sign or abbreviation spoken as several words: it takes their whole time
            out.append((words[0], got[0][1], got[-1][2]))
            continue
        if len(words) > 1 and any(re.search(r"[\d%$€₽№#@&+=/]", w) for w in words):
            raise AlignError(f"{what}: “{' '.join(words)}” (word {i1 + 1}) was read as “{' '.join(g[0] for g in got)}”; "
                             f"which word is which is a guess: write the numbers and units in words in the script")
        raise AlignError(f"{what}: the script's “{' '.join(words)}” (word {i1 + 1}) does not match the spoken "
                         f"“{' '.join(g[0] for g in got)}”")
    return out


def attach(rows):
    """Punctuation-only words join a neighbour (the previous one, or the next one at the start): every word has
    letters or digits and a time."""
    out = []
    pending = ""
    for w, s, t in rows:
        if s is None or not has_letters(w):
            if out:
                out[-1]["text"] += " " + w
            else:
                pending = (pending + " " + w).strip()
            continue
        out.append({"text": (pending + " " + w).strip() if pending else w, "start": float(s), "end": float(t)})
        pending = ""
    return out


def parse_attempt(e, fp, at, fmt, text):
    """received -> saved: decode the kept answer and take out the words. Raises on a broken answer."""
    resp = e / at["response"]
    try:
        doc = json.loads(resp.read_text(encoding="utf-8"))
        body = json.loads(doc["body_text"])
        audio = base64.b64decode(body["audio_base64"], validate=True)
    except (OSError, ValueError, KeyError, TypeError) as ex:
        raise BrokenAnswer(f"the kept answer {resp.name} is not complete ({type(ex).__name__}): it was paid; recover "
                         f"the audio from the ElevenLabs history (voice recover)") from None
    wav = e / "generated" / "voice" / f"{fp[:16]}.wav"
    n = decode_audio(audio, fmt, wav)
    words, source = words_for(text, body.get("alignment"), body.get("normalized_alignment"))
    voice_onset(wav, words)
    dur = n / SR
    check_words(words, text, dur, f"block {at.get('block')}")
    al = e / "generated" / "voice" / f"{fp[:16]}.words.json"
    save_json(al, {"text": text, "words": words, "duration": round(dur, 4), "timing": source, "samples": n})
    return {"wav": rel(wav, e), "words": rel(al, e), "timing": source}


def voice_onset(wav, words, step=0.005):
    """The live alignment starts its first character at 0.0 s and stretches it over the silence before the voice
    (about 0.17 s, mp3 and PCM alike, 2026-11-13): the first word starts where its sound rises over a tenth of the
    block's peak, if that is inside the word."""
    samples = read_samples(wav)
    n = int(SR * step)
    env = [sum(abs(x) for x in samples[k:k + n]) / n for k in range(0, len(samples) - n + 1, n)]
    if not env or not words:
        return
    peak = max(env)
    onset = next((k * step for k, v in enumerate(env) if v > peak / 10), None)
    if onset is not None and words[0]["start"] < onset < words[0]["end"]:
        words[0]["start"] = round(onset, 4)


def check_words(words, text, dur, where):
    """Every script word has a finite time inside the audio, in order."""
    want = len([w for w in text.split() if has_letters(w)])
    if len(words) != want:
        raise AlignError(f"{where}: {len(words)} timed word(s) for {want} word(s) of the script")
    prev = -1.0
    for k, w in enumerate(words):
        s, t = w["start"], w["end"]
        if not (math.isfinite(s) and math.isfinite(t)) or t < s or s < 0:
            raise AlignError(f"{where}: word {k + 1} {w['text']!r} has times {s}..{t}")
        if t > dur + 0.05:
            raise AlignError(f"{where}: word {k + 1} {w['text']!r} ends at {t:.2f} s, after the audio ({dur:.2f} s)")
        if s + 0.05 < prev:
            raise AlignError(f"{where}: word {k + 1} {w['text']!r} starts before the previous word")
        prev = max(prev, s)


def response_path(e, fp, owner):
    return e / "generated" / "voice" / f"{fp[:16]}-{owner[-8:]}.response.json"


def promote(e):
    """A run that stopped after the answer was kept on disk but before its state was written: the reservation is still
    `submitting` and its answer file is there and whole (written atomically) -> received, nothing is paid again."""
    with editing_json(e / GEN, {}) as gen:
        for fp, at in (gen.get("attempts") or {}).items():
            f = response_path(e, fp, at.get("owner") or "")
            if at.get("state") == "submitting" and at.get("owner") and f.is_file():
                try:
                    kept = json.loads(f.read_text(encoding="utf-8")).get("headers") or {}
                except ValueError:
                    kept = {}
                cost = kept.get("character-cost") or kept.get("x-character-count")
                at.update(state="received", response=rel(f, e), request_id=kept.get("request-id"),
                          character_cost=int(cost) if str(cost or "").isdigit() else cost, received_at=now_iso(),
                          note="taken up after an interrupted run")


def settle(e, req):
    """Take out every received answer of the current blocks (free). Returns the blocks still not saved."""
    promote(e)
    left = []
    for b in req["blocks"]:
        fp = b["fingerprint"]
        at = gen_of(e)["attempts"].get(fp) or {}
        if at.get("state") == "received":
            try:
                if at.get("audio_only"):
                    got = parse_recovered(e, fp, at, req, b["text"])
                else:
                    got = parse_attempt(e, fp, at, req["format"], b["text"])
            except AlignError as ex:
                with editing_json(e / GEN, {}) as gen:
                    gen["attempts"][fp]["parse_error"] = str(ex)[:400]
                    if isinstance(ex, BrokenAnswer):
                        gen["attempts"][fp].update(state="unknown", error=str(ex)[:300])
                print(f"✗ block {b['id']}: {ex}")
                left.append(b)
                continue
            with editing_json(e / GEN, {}) as gen:
                cur = gen["attempts"][fp]
                cur.update(state="saved", saved_at=now_iso(), **got)
                cur.pop("parse_error", None)
            print(f"{b['id']}: audio and word timings saved ({got['timing']})")
        elif at.get("state") not in ("saved", "done"):
            left.append(b)
    return left


def cmd_run(a):
    e = edit_dir(a.edit)
    req = request_of(e, load_script(e))
    settle(e, req)  # answers already paid for: no "yes" needed, no money spent
    gen = gen_of(e)
    buy, ready, blocked, pid, total = plan_of(req, gen)
    for b in blocked:
        print("✗ " + blocked_message(b, gen["attempts"][b["fingerprint"]]))
    if blocked:
        sys.exit(2)
    if not buy:
        return build(e, req)
    if not a.yes:
        print(f"ready to voice {len(buy)} block(s), at most {total} credits (plan {pid}). This needs the person's "
              f"explicit “yes” to that price; then: voice run edit/<id> --yes --plan {pid}")
        return
    eff, why = effective(req["settings"])
    if not eff.get("generate_voice_now"):
        sys.exit(f"not started: generate_voice_now is off ({why.get('generate_voice_now')}); the person turns it on: "
                 f"reelcfg.py save edit/<id> --set generate_voice_now=true")
    approved = (gen.get("plan") or {}).get("id")
    if a.plan != pid or approved != pid:
        sys.exit(f"not started: the approved plan is {a.plan!r}, the current one is {pid!r}"
                 + ("" if approved == pid else " and was not shown with voice plan")
                 + ": the text, the voice, the settings or the price changed. voice plan edit/<id> again and ask the "
                   "person again")
    key = need_key()
    first_left, spent = None, 0  # the balance shows a charge minutes later (2026-11-13): count this run's own charges
    for b in buy:
        # the stale age is past the longest step (balance 20 s + request 180 s): only a dead run's lock is removed
        with locked(spend_lock(), timeout=SPEND_WAIT, stale=STALE_SUBMIT):
            try:
                left, _ = balance(key)
            except (ApiError, OSError, ValueError) as ex:
                sys.exit(f"stopped before block {b['id']}: the balance is not known ({ro.err_text(ex, 300)}); "
                         f"nothing sent")
            first_left = left if first_left is None else first_left
            left = min(left, first_left - spent)
            if left < b["credits"]:
                sys.exit(f"stopped before block {b['id']}: {left} credits left, it needs up to {b['credits']}; "
                         f"nothing sent")
            owner = reserve(e, b, b["fingerprint"], f"{os.getpid()}-{uuid.uuid4().hex}", req["voice"])
            if owner is None:
                continue
            if not submit(e, b, key, owner):
                sys.exit(2)
        at = gen_of(e)["attempts"][b["fingerprint"]]
        cost = at.get("character_cost")
        spent += cost if isinstance(cost, int) else b["credits"]
        stop = isinstance(cost, int) and cost > b["credits"]
        settle(e, {**req, "blocks": [b]})
        if stop:
            sys.exit(f"stopped: block {b['id']} was charged {cost} credits, over its ceiling of {b['credits']}; the plan "
                     f"is wrong somewhere: tell the person before going on")
    left = settle(e, req)
    if left:
        sys.exit(f"not built: block(s) {', '.join(b['id'] for b in left)} have no audio yet (voice status edit/<id>)")
    return build(e, req)


# --- Recovery and manual clearing ------------------------------------------------------------------------------

def find_block(req, block):
    b = next((x for x in req["blocks"] if x["id"] == block), None)
    if b is None:
        sys.exit(f"no block {block!r} in the script")
    return b


def cmd_recover(a):
    """An unknown attempt -> its audio and timings from the ElevenLabs history, only through one exact history item that
    matches the block's text, voice, model and format (and its request id when known). Free: the history's audio costs
    no credits (checked 2026-11-13), nothing is synthesized again."""
    e = edit_dir(a.edit)
    req = request_of(e, load_script(e))
    b = find_block(req, a.block)
    fp = b["fingerprint"]
    at = gen_of(e)["attempts"].get(fp) or {}
    if at.get("state") not in UNRESOLVED:
        sys.exit(f"block {b['id']}: nothing to recover (state {at.get('state') or 'none'})")
    if not re.match(r"^[A-Za-z0-9]{8,64}$", a.history or ""):
        sys.exit(f"{a.history!r} does not look like a history item id")
    key = need_key()
    try:
        item = api_json("GET", f"/v1/history/{a.history}", key, timeout=30)
    except ApiError as ex:
        sys.exit(f"ElevenLabs history: {ex}")
    bad = []
    if item.get("voice_id") != req["rec"]["voice_id"]:
        bad.append("another voice")
    if item.get("model_id") not in (None, req["model"]):
        bad.append(f"model {item.get('model_id')}")
    if (item.get("text") or "") != b["text"]:
        bad.append("another text")
    if at.get("request_id") and item.get("request_id") != at["request_id"]:
        bad.append(f"request id {item.get('request_id')} instead of {at['request_id']}")
    if item.get("output_format") not in (None, req["format"]):
        bad.append(f"output format {item.get('output_format')}")
    if bad:
        sys.exit(f"history item {a.history} is not this block's request ({', '.join(bad)}); the block stays unknown")
    try:
        _, h, audio = api("GET", f"/v1/history/{a.history}/audio", key, timeout=120)
    except ApiError as ex:
        sys.exit(f"ElevenLabs history audio: {ex}")
    ctype = (h.get("content-type") or "audio/mpeg").split(";")[0]
    if not ctype.startswith("audio/"):
        sys.exit(f"the history answered {ctype}, not audio; the block stays unknown")
    rid = item.get("request_id") or at.get("request_id")
    al = item.get("alignments") if isinstance(item.get("alignments"), dict) else {}
    if al.get("alignment") or al.get("normalized_alignment"):
        # a history item keeps the request's timings (checked 2026-11-13): the same answer as the lost one
        resp = e / "generated" / "voice" / f"{fp[:16]}-history.response.json"
        body = {"audio_base64": base64.b64encode(audio).decode(), "alignment": al.get("alignment"),
                "normalized_alignment": al.get("normalized_alignment")}
        write_atomic(resp, json.dumps({"saved_at": now_iso(), "status": 200, "source": "history",
                                       "headers": {"request-id": rid, "history-item-id": a.history},
                                       "body_text": json.dumps(body, ensure_ascii=False)},
                                      ensure_ascii=False).encode("utf-8"))
        fields = {"response": rel(resp, e)}
        how = "with its word timings"
    else:
        f = e / "generated" / "voice" / f"{fp[:16]}.history.mp3"
        write_atomic(f, audio)
        fields = {"audio_only": True, "audio": rel(f, e)}
        how = "without word timings: they come from recognizing this audio on this computer"
    with editing_json(e / GEN, {}) as gen:
        cur = gen["attempts"][fp]
        cur.update(state="received", history_item=a.history, request_id=rid, recovered_at=now_iso(), **fields)
        cur.pop("error", None)
    print(f"{b['id']}: recovered from history item {a.history} ({how}); nothing paid again")
    left = settle(e, req)
    if b in left:
        sys.exit(2)


def parse_recovered(e, fp, at, req, text):
    """Recovered audio without timings: the local recognizer's word times, the script's words laid onto them."""
    wav = e / "generated" / "voice" / f"{fp[:16]}.wav"
    n = decode_audio((e / at["audio"]).read_bytes(), "mp3_44100_128", wav)
    try:
        import transcribe as core_tr
        from transcribe_online import lay_text
    except ImportError as ex:
        raise AlignError(f"the core's transcribe.py is needed for the timings of recovered audio ({ex})")
    w16 = wav.with_name(f".{wav.stem}.16k.wav")
    try:
        run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ac", "1", "-ar", "16000", str(w16)])
        try:
            model = core_tr.load_model("medium", "int8")
        except SystemExit as ex:
            raise AlignError(f"no local recognizer for the timings: {ex}") from None
        _, _, heard = core_tr.words_of(model, w16, req.get("language"))
    finally:
        if w16.exists():
            w16.unlink()
    laid, _ = lay_text(heard, text)
    words = attach([(w["text"], w["start"], w["end"]) for w in laid])
    dur = n / SR
    check_words(words, text, dur, f"block {at.get('block')} (recovered)")
    al = e / "generated" / "voice" / f"{fp[:16]}.words.json"
    save_json(al, {"text": text, "words": words, "duration": round(dur, 4), "timing": "asr", "samples": n})
    return {"wav": rel(wav, e), "words": rel(al, e), "timing": "asr"}


def cmd_clear(a):
    e = edit_dir(a.edit)
    req = request_of(e, load_script(e))
    b = find_block(req, a.block)
    if not a.not_charged:
        sys.exit("clear only after the person checked the ElevenLabs history and found no accepted request for this "
                 "block: then --not-charged (a new run pays again)")
    with editing_json(e / GEN, {}) as gen:
        at = gen.setdefault("attempts", {}).get(b["fingerprint"])
        if not at or at.get("state") not in UNRESOLVED:
            sys.exit(f"block {b['id']}: no unknown request to clear")
        if at.get("state") == "submitting" and age_s(at.get("at")) < STALE_SUBMIT:
            sys.exit(f"block {b['id']}: its request may still be on its way (reserved {age_s(at.get('at')):.0f} s ago); "
                     f"clear it only when no run is going and at least {STALE_SUBMIT // 60} minutes have passed")
        gen.setdefault("cleared", []).append({**at, "fingerprint": b["fingerprint"], "cleared_at": now_iso()})
        gen["attempts"].pop(b["fingerprint"])
    print(f"block {b['id']}: the unknown request is cleared; voice plan edit/<id> names the price again")


# --- Build: join the blocks, write the transcript and the core's cut.json ------------------------------------------

def read_samples(f):
    with wave.open(str(f), "rb") as w:
        if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise RuntimeError(f"{f}: expected {SR} Hz mono 16-bit")
        data = array.array("h")
        data.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder == "big":
        data.byteswap()
    return data


def fade(piece, n):
    n = min(n, len(piece) // 2)
    for k in range(n):
        g = k / n
        piece[k] = int(piece[k] * g)
        piece[-1 - k] = int(piece[-1 - k] * g)


def pause_after(b):
    if b.get("pause_after") is not None:
        return min(PAUSE_MAX, max(0.0, float(b["pause_after"])))
    return PAUSE_SENTENCE if SENTENCE_END.search(b["text"]) else PAUSE_PHRASE


def build(e, req):
    gen = gen_of(e)
    parts, missing = [], []
    for b in req["blocks"]:
        at = gen["attempts"].get(b["fingerprint"]) or {}
        if at.get("state") not in ("saved", "done"):
            missing.append(b["id"])
        else:
            parts.append((b, at))
    if missing:
        sys.exit(f"not built: block(s) {', '.join(missing)} have no audio yet (voice plan / run)")
    out, words, layout = array.array("h"), [], []
    for k, (b, at) in enumerate(parts):
        samples = read_samples(e / at["wav"])
        doc = load_json(e / at["words"])
        ws = doc["words"]
        s0 = max(0, int(round((ws[0]["start"] - LEAD) * SR)))
        s1 = min(len(samples), int(round((ws[-1]["end"] + TAIL) * SR)))
        piece = samples[s0:s1]
        fade(piece, int(FADE * SR))
        start = len(out)
        shift = (start - s0) / SR
        words += [{"text": w["text"], "start": round(w["start"] + shift, 4), "end": round(w["end"] + shift, 4),
                   "type": "word", "block": b["id"]} for w in ws]
        out.extend(piece)
        gap = int(round(pause_after(b) * SR)) if k + 1 < len(parts) else 0
        out.extend(array.array("h", bytes(2 * gap)))
        layout.append({"id": b["id"], "fingerprint": b["fingerprint"], "trim": [round(s0 / SR, 4), round(s1 / SR, 4)],
                       "at": round(start / SR, 4), "pause_after": round(gap / SR, 4), "timing": at.get("timing")})
    dur = len(out) / SR
    narration = e / "generated" / "narration.wav"
    with locked(narration):
        tmp = narration.with_name(f".narration.{os.getpid()}.{uuid.uuid4().hex[:8]}.wav")
        try:
            data = array.array("h", out)
            if sys.byteorder == "big":
                data.byteswap()
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes(data.tobytes())
            os.replace(tmp, narration)
        finally:
            if tmp.exists():
                tmp.unlink()
    text = " ".join(b["text"] for b, _ in parts)
    check_words(words, text, dur, "the narration")
    st = narration.stat()
    timing = "alignment" if all(at.get("timing") != "asr" for _, at in parts) else "alignment+asr"
    tr = {"language_code": req.get("language"), "text": text, "words": words, "source": narration.name,
          "source_identity": {"path": str(narration.resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns},
          "model": f"elevenlabs:{req['model']}:{timing}", "voice": req["voice"]}
    import transcribe as core_tr
    problems = [p for p in core_tr.check_doc(tr) if not p.startswith("note:")]
    if problems:
        sys.exit("the narration's transcript fails the core check: " + "; ".join(problems))
    transcript = e / "transcripts" / "narration.json"
    save_json(transcript, tr)
    contract(e, narration, transcript, dur)
    with editing_json(e / GEN, {}) as g:
        for b, _ in parts:
            g["attempts"][b["fingerprint"]]["state"] = "done"
        g["build"] = {"at": now_iso(), "duration": round(dur, 4), "narration": rel(narration, e), "blocks": layout}
    print(f"{narration}: {dur:.2f} s, {len(words)} words; transcript {transcript}")
    print("Listen to the whole narration with the person before editing: stress and pronunciation are not checked by "
          "anything (voice check compares the words only). Then add the picture and run cut.py as for a recorded "
          "narration.")


def contract(e, narration, transcript, dur):
    """reel.json -> voice: off_camera; cut.json -> sources.narration over its whole length at speed 1."""
    project = project_root()
    with editing_json(e / "reel.json", {}) as reel:
        before = reel.get("voice")
        reel["voice"] = "off_camera"
    if before not in (None, "off_camera"):
        warn(f"reel.json -> voice was {before}, now off_camera: the narration is the voice of this reel")
    with editing_json(e / "cut.json", {}) as cut:
        cut.setdefault("fps", 30)
        sources = cut.setdefault("sources", {})
        sources["narration"] = {"file": rel(narration, project), "transcript": rel(transcript, project), "speed": 1.0}
        others = [r for r in cut.get("ranges") or [] if (r.get("source") or "") != "narration"]
        if others:
            warn("cut.json has ranges of other sources: the narration's range is not added; add "
                 f'{{"source": "narration", "start": 0, "end": {dur:.3f}}} where it belongs')
        else:
            cut["ranges"] = [{"source": "narration", "start": 0.0, "end": round(dur, 3), "beat": "narration"}]
    print(f"cut.json: source narration ({rel(narration, project)}), 0–{dur:.2f} s at speed 1; reel.json -> voice: "
          f"off_camera")


def cmd_build(a):
    e = edit_dir(a.edit)
    req = request_of(e, load_script(e))
    left = settle(e, req)
    if left:
        sys.exit(f"not built: block(s) {', '.join(b['id'] for b in left)} have no audio yet")
    build(e, req)


def cmd_status(a):
    e = edit_dir(a.edit)
    req = request_of(e, load_script(e))
    gen = gen_of(e)
    cur = {b["fingerprint"] for b in req["blocks"]}
    for b in req["blocks"]:
        at = gen["attempts"].get(b["fingerprint"]) or {}
        extra = (f", request id {at['request_id']}" if at.get("request_id") else "") + \
                (f", charged {at['character_cost']}" if at.get("character_cost") is not None else "") + \
                (f", {at['parse_error']}" if at.get("parse_error") else "")
        print(f"  {b['id']}: {at.get('state') or 'not voiced'}{extra}")
    old = [(fp, at) for fp, at in gen["attempts"].items() if fp not in cur and at.get("state") in UNRESOLVED]
    for fp, at in old:
        print(f"  ⚠ an earlier text of block {at.get('block')}: request {at.get('state')} "
              f"({at.get('request_id') or 'no request id'}); check the ElevenLabs history")
    if gen.get("plan"):
        print(f"plan {gen['plan']['id']} ({gen['plan']['at']}): ≤ {gen['plan']['credits_max']} credits")
    if gen.get("build"):
        print(f"built {gen['build']['at']}: {gen['build']['narration']}, {gen['build']['duration']} s")


def cmd_check(a):
    """A separate recognition of the built narration (transcripts/narration.check.json) compared with the script."""
    e = edit_dir(a.edit)
    req = request_of(e, load_script(e))
    narration = e / "generated" / "narration.wav"
    if not narration.is_file():
        sys.exit("no narration yet: voice run / build first")
    copy = e / "generated" / "narration.check.wav"  # its own stem: its own transcript, never the main one
    copy.write_bytes(narration.read_bytes())
    core = Path(sys.modules["reels_common"].__file__).resolve().parent
    args = [sys.executable, str(core / "transcribe.py"), str(e), str(copy), "--force"]
    if req.get("language"):
        args += ["--language", req["language"]]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"the check recognition failed: {r.stderr[-500:]}")
    heard = load_json(e / "transcripts" / "narration.check.json") or {}
    diffs = compare(" ".join(b["text"] for b in req["blocks"]), heard.get("words") or [])
    for d in diffs:
        print("  " + d)
    print(f"{len(diffs)} difference(s) between the script and what the recognizer heard"
          + (" (numbers and names often differ in spelling only)" if diffs else "")
          + ". Stress and pronunciation: only listening finds them.")


def compare(text, heard):
    a = [bare(w) for w in text.split() if has_letters(w)]
    src = [w for w in text.split() if has_letters(w)]
    heard = [w for w in heard if has_letters(str(w.get("text", "")))]  # a recognized dash is not a word
    b = [bare(w.get("text", "")) for w in heard]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        at = f"{heard[j1]['start']:.2f} s" if j1 < len(heard) else "the end"
        out.append(f"{at}: script “{' '.join(src[i1:i2])}”, heard “{' '.join(w.get('text', '') for w in heard[j1:j2])}”")
    return out


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="addon.py voice", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the account's voices (free)").set_defaults(fn=cmd_list)
    p = sub.add_parser("use", help="an existing voice of the account, with the owner's consent")
    p.add_argument("voice_id"); p.add_argument("--name", required=True); p.add_argument("--consent")
    p.set_defaults(fn=cmd_use)
    p = sub.add_parser("clone", help="a new voice from the person's own fresh recordings (1-3 min)")
    p.add_argument("files", nargs="+"); p.add_argument("--name", required=True); p.add_argument("--consent")
    p.add_argument("--remove-noise", action="store_true", help="the service's noise removal (can hurt a clean take)")
    p.add_argument("--yes", action="store_true"); p.set_defaults(fn=cmd_clone)
    p = sub.add_parser("forget", help="remove the local record [--remote: and the voice the add-on created]")
    p.add_argument("name"); p.add_argument("--remote", action="store_true"); p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_forget)
    p = sub.add_parser("script", help="voice_script.json from a text file (blocks by paragraph)")
    p.add_argument("edit"); p.add_argument("--text", required=True); p.add_argument("--voice", required=True)
    p.add_argument("--language", default=None); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_script)
    for name, fn, what in (("plan", cmd_plan, "the price in credits per block and the plan id"),
                           ("status", cmd_status, "the state of every block"),
                           ("build", cmd_build, "join the voiced blocks again (free)"),
                           ("check", cmd_check, "recognize the narration separately and compare with the script")):
        p = sub.add_parser(name, help=what); p.add_argument("edit"); p.set_defaults(fn=fn)
    p = sub.add_parser("run", help="paid: voice the blocks of the approved plan")
    p.add_argument("edit"); p.add_argument("--yes", action="store_true"); p.add_argument("--plan")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("recover", help="an unknown block's audio from one ElevenLabs history item")
    p.add_argument("edit"); p.add_argument("block"); p.add_argument("--history", required=True)
    p.set_defaults(fn=cmd_recover)
    p = sub.add_parser("clear", help="drop an unknown request the person found was not charged")
    p.add_argument("edit"); p.add_argument("block"); p.add_argument("--not-charged", action="store_true")
    p.set_defaults(fn=cmd_clear)
    a = ap.parse_args(argv)
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
