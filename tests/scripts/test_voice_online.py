"""addon.py voice: a narration in the person's own cloned voice through ElevenLabs. No network: the add-on's open_url is
replaced by a fake ElevenLabs that answers in the API's own format (base64 audio and per-character timings, here tone
bursts made by ffmpeg standing in for the words), and every paid path checks that nothing is sent without the "yes"
to the plan and that the key never shows."""
import array
import base64
import io
import json
import os
import subprocess
import sys
import urllib.error
import wave
from pathlib import Path

import pytest

from conftest import ADDON, CORE, ffmpeg, needs_ffmpeg, run_script, write_json

KEY = "el-test-secret-value-0123456789abcdef"
VOICE_ID = "PrRM6eozRnCrcqn2t8ou"
STUBS = str(Path(__file__).resolve().parent / "stubs")


# --- a fake ElevenLabs --------------------------------------------------------------------------------------------

class Resp(io.BytesIO):
    def __init__(self, body, headers=None, status=200):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8"))
        self.headers, self.status = dict(headers or {}), status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(url, status, detail):
    body = json.dumps({"detail": detail}).encode()
    return urllib.error.HTTPError(url, status, "err", {}, io.BytesIO(body))


def tone_mp3(path, words, dur):
    """An mp3 (as the API sends, 44.1 kHz) with a tone burst for every word's time."""
    on = "+".join(f"between(t,{s},{e})" for _, s, e in words)
    ffmpeg("-f", "lavfi", "-i", f"sine=f=300:d={dur}:sample_rate=44100,volume='0.6*({on})':eval=frame",
           "-ac", "1", "-c:a", "libmp3lame", "-b:a", "128k", path)
    return Path(path).read_bytes()


def char_times(text, words):
    """Per-character times of `text` as the API gives them: each word's characters spread over its time, a space
    between words takes the gap."""
    chars, st, en = [], [], []
    toks = text.split(" ")
    assert len(toks) == len(words), (toks, words)
    for k, (tok, (_, s, e)) in enumerate(zip(toks, words)):
        step = (e - s) / len(tok)
        for i, ch in enumerate(tok):
            chars.append(ch); st.append(round(s + i * step, 4)); en.append(round(s + (i + 1) * step, 4))
        if k + 1 < len(toks):
            nxt = words[k + 1][1]
            chars.append(" "); st.append(e); en.append(nxt)
    return {"characters": chars, "character_start_times_seconds": st, "character_end_times_seconds": en}


def tts_answer(tmp, text, words, dur, spoken=None, nwords=None):
    """The JSON of POST /v1/text-to-speech/{id}/with-timestamps. spoken/nwords: what the voice actually read (numbers
    as words) when the alignment carries the normalized text."""
    audio = tone_mp3(tmp / f"tts-{abs(hash(text))}.mp3", nwords or words, dur)
    al = char_times(spoken or text, nwords or words)
    return {"audio_base64": base64.b64encode(audio).decode(), "alignment": al, "normalized_alignment": al}


class Fake:
    """Routes of the fake API; `log` keeps (method, path, body) of every request."""
    def __init__(self, tmp):
        self.tmp, self.log, self.tts, self.balance = tmp, [], [], 30000
        self.history = {}
        self.voice = {"voice_id": VOICE_ID, "name": "Anton", "category": "cloned", "is_owner": True,
                      "voice_verification": {"requires_verification": False}, "preview_url": "https://example.test/p.mp3",
                      "samples": [{"duration_secs": 138.5}], "created_at_unix": 1793210195}

    def __call__(self, req, timeout, allowed=None):
        assert allowed is not None and allowed(req.full_url), req.full_url
        assert req.full_url.startswith("https://api.elevenlabs.io/")
        assert req.get_header("Xi-api-key") == KEY
        path = req.full_url[len("https://api.elevenlabs.io"):]
        body = json.loads(req.data.decode()) if req.data and req.get_method() == "POST" and "voices/add" not in path \
            else req.data
        self.log.append((req.get_method(), path, body))
        if path == "/v1/user/subscription":
            return Resp({"character_count": 30000 - self.balance, "character_limit": 30000, "tier": "starter"})
        if path == "/v1/voices":
            return Resp({"voices": [self.voice, {"voice_id": "premade1", "name": "Rachel", "category": "premade"}]})
        if path.startswith("/v1/voices/") and req.get_method() == "GET":
            return Resp(self.voice)
        if path.startswith("/v1/history/"):
            item, audio = self.history[path.split("/")[3]]
            return Resp(audio, {"content-type": "audio/mpeg"}) if path.endswith("/audio") else Resp(item)
        if "/with-timestamps" in path:
            assert self.tts, f"an unexpected paid request: {path}"
            nxt = self.tts.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            ans, hdr = nxt
            return Resp(ans, {"request-id": f"req{len(self.log)}", "character-cost": str(len(body["text"])), **hdr})
        raise AssertionError(f"no fake route for {req.get_method()} {path}")

    def paid(self):
        return [x for x in self.log if "/with-timestamps" in x[1]]


@pytest.fixture
def voice(project, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ADDON))
    import reels_online
    import voice_online
    monkeypatch.setattr(reels_online, "KEYS_FILE", tmp_path / "cfg" / "keys.env")
    monkeypatch.setattr(reels_online, "_KEYS", None)
    for n in reels_online.known_keys():
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", KEY)
    write_json(project / "it-reelsmaker.json", {"online_scripts": str(ADDON)})  # linked, as `reels_online.py link` does
    fake = Fake(tmp_path)
    monkeypatch.setattr(reels_online, "open_url", fake)
    voice_online.fake = fake
    return voice_online


def call(mod, *args):
    """Run a voice command in this process -> (exit code or message, stdout+stderr)."""
    try:
        mod.main([str(a) for a in args])
        code = 0
    except SystemExit as ex:
        code = ex.code
    return code


def own_voice(mod):
    assert call(mod, "use", VOICE_ID, "--name", "me", "--consent", "own") == 0


WORDS1 = [("Привет,", 0.3, 0.8), ("это", 0.9, 1.2), ("тест.", 1.3, 1.8)]
WORDS2 = [("Второй", 0.2, 0.7), ("блок.", 0.8, 1.3)]
TEXT1, TEXT2 = "Привет, это тест.", "Второй блок."


def script(project, *blocks, **extra):
    e = project / "edit" / "v1"
    write_json(e / "voice_script.json", {"voice": "me", "language": "ru",
                                         "blocks": [{"id": f"b{k + 1}", "text": t} for k, t in enumerate(blocks)],
                                         **extra})
    return e


def turn_on(e):
    write_json(e / "reel.json", {"generate_voice_now": True})


def plan_id(mod, e, capsys):
    capsys.readouterr()
    assert call(mod, "plan", e) == 0
    return json.loads((e / "voice_gen.json").read_text(encoding="utf-8"))["plan"]["id"]


# --- step 1: key, host, settings, voices.json -------------------------------------------------------------------

def test_the_elevenlabs_key_goes_to_its_api_only_and_never_shows(voice, monkeypatch):
    # Requirement: the ElevenLabs key is sent only to https://api.elevenlabs.io, every redirect hop included, and its
    # value, header or name=value form never reaches the output.
    import reels_online as ro
    ok = ro.elevenlabs_url_ok
    assert ok("https://api.elevenlabs.io/v1/voices")
    for bad in ("http://api.elevenlabs.io/v1/voices", "https://api.elevenlabs.io.evil.test/v1",
                "https://evil.test/?h=api.elevenlabs.io", "https://api.elevenlabs.io:8443/v1", "https://u:p@api.elevenlabs.io/"):
        assert not ok(bad), bad
    with pytest.raises(ValueError):
        ro.elevenlabs("GET", "//evil.test/x", KEY)
    # a redirect to another host is refused before the key could follow
    import urllib.request
    req = urllib.request.Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": KEY})
    with pytest.raises(ValueError):
        ro.SafeRedirect(ok).redirect_request(req, None, 302, "Found", {}, "https://evil.test/steal")
    assert "xi-api-key" in ro.SECRET_HEADERS
    text = ro.scrub(f"headers {{'xi-api-key': '{KEY}'}} and xi-api-key: {KEY[:20]}zz and {KEY}")
    assert KEY not in text and KEY[:20] not in text
    assert "ELEVENLABS_API_KEY" in ro.known_keys()


def test_a_refused_request_does_not_print_the_key(voice, project, capsys):
    # Requirement: an error answer that quotes the key (some services do) is shown without it.
    def refused(req, timeout, allowed=None):
        raise http_error(req.full_url, 401, {"status": "invalid_api_key", "message": f"bad key {KEY}"})
    import reels_online
    reels_online.open_url = refused
    code = call(voice, "list")
    assert KEY not in str(code) and "invalid_api_key" in str(code)


def test_voice_generation_has_its_own_switch_and_the_voice_record_lives_outside_the_project(voice, project):
    # Requirement: synthesis is off until generate_voice_now is on, whatever the B-roll settings say; the voice and its
    # consent are kept in the add-on's own file next to the keys, not in the project or the installed skill.
    import reels_common
    import reels_online as ro
    s, *_ = reels_common.load_config(project / "edit" / "v1")
    assert s["generate_voice_now"] is False
    eff, why = reels_common.effective({**s, "use_broll": True, "generate_now": True})
    assert not eff["generate_voice_now"] and why["generate_voice_now"] == "off"
    eff, why = reels_common.effective({**s, "generate_voice_now": True})
    assert eff["generate_voice_now"]
    own_voice(voice)
    f = ro.voices_file()
    assert f.is_file() and f.parent == ro.KEYS_FILE.parent
    assert project not in f.parents and ADDON.parent not in f.parents
    rec = json.loads(f.read_text(encoding="utf-8"))["voices"]["me"]
    assert rec["voice_id"] == VOICE_ID and rec["consent"]["kind"] == "own" and rec["consent"]["at"]
    assert rec["created_by_addon"] is False


# --- step 3: consent, verification, forget --------------------------------------------------------------------------

def test_no_consent_no_voice_on_both_paths(voice, project, tmp_path):
    # Requirement: neither picking an existing voice nor cloning works without the owner's consent; nothing is sent.
    import reels_online as ro
    code = call(voice, "use", VOICE_ID, "--name", "me")
    assert "--consent own" in str(code) and not voice.fake.log and not ro.voices_file().exists()
    code = call(voice, "clone", tmp_path / "x.mp3", "--name", "me", "--consent", "theirs", "--yes")
    assert "--consent own" in str(code) and not voice.fake.log


def test_a_voice_waiting_for_verification_is_blocked(voice, project, capsys):
    # Requirement: a voice ElevenLabs wants verified cannot narrate until that is done.
    voice.fake.voice["voice_verification"]["requires_verification"] = True
    own_voice(voice)
    e = script(project, TEXT1)
    code = call(voice, "plan", e)
    assert "verify" in str(code) and not voice.fake.paid()


def test_a_library_voice_is_not_the_persons_own(voice):
    voice.fake.voice.update(category="premade", is_owner=False)
    code = call(voice, "use", VOICE_ID, "--name", "me", "--consent", "own")
    assert "not a voice of this account" in str(code)


def test_forget_deletes_remotely_only_what_the_add_on_created_and_only_on_yes(voice, project):
    # Requirement: forget removes the local record; --remote deletes the voice at ElevenLabs only when the add-on made
    # it and the person said yes; a voice picked with `use` is never deleted remotely.
    import reels_online as ro
    own_voice(voice)
    n = len(voice.fake.log)
    code = call(voice, "forget", "me", "--remote", "--yes")
    assert "not created by the add-on" in str(code) and len(voice.fake.log) == n
    assert call(voice, "forget", "me") == 0 and len(voice.fake.log) == n
    assert "me" not in json.loads(ro.voices_file().read_text(encoding="utf-8"))["voices"]
    doc = {"voices": {"made": {"voice_id": "abcdefgh1234", "owner": "self", "created_by_addon": True,
                               "consent": {"kind": "own", "at": "x"}, "verification": "ok"}}}
    ro.write_private(ro.voices_file(), json.dumps(doc))
    deleted = []

    def fake(req, timeout, allowed=None):
        assert allowed(req.full_url)
        deleted.append((req.get_method(), req.full_url))
        return Resp({"status": "ok"})
    ro.open_url = fake
    assert call(voice, "forget", "made", "--remote") == 0 and not deleted  # no yes: only the question
    assert call(voice, "forget", "made", "--remote", "--yes") == 0
    assert deleted == [("DELETE", "https://api.elevenlabs.io/v1/voices/abcdefgh1234")]


# --- step 2: the plan, its price and the "yes" bound to it ----------------------------------------------------------

def test_the_plan_prices_each_block_and_binds_the_yes_to_the_exact_requests(voice, project, capsys):
    # Requirement: the plan names credits per block (characters x the model's rate) and a plan id; a run without the
    # "yes", with another plan id, with the switch off, or after the text changed sends nothing paid.
    own_voice(voice)
    e = script(project, TEXT1, TEXT2)
    pid = plan_id(voice, e, capsys)
    out = capsys.readouterr().out
    assert f"≤ {len(TEXT1)} credits" in out and f"≤ {len(TEXT2)} credits" in out
    assert f"at most {len(TEXT1) + len(TEXT2)} credits" in out and pid in out
    assert call(voice, "run", e) == 0 and not voice.fake.paid()                 # no yes: the price only
    code = call(voice, "run", e, "--yes", "--plan", pid)                        # the switch is off
    assert "generate_voice_now" in str(code) and not voice.fake.paid()
    turn_on(e)
    code = call(voice, "run", e, "--yes", "--plan", "000000000000")             # a yes to another plan
    assert "plan" in str(code) and not voice.fake.paid()
    script(project, TEXT1, "Второй блок, другой.")                               # the text changed after the yes
    code = call(voice, "run", e, "--yes", "--plan", pid)
    assert "changed" in str(code) and not voice.fake.paid()
    # changing a voice setting changes the plan too
    script(project, TEXT1, TEXT2, settings={"stability": 0.3})
    assert call(voice, "run", e, "--yes", "--plan", pid) != 0 and not voice.fake.paid()


def test_a_text_changed_while_the_run_is_going_is_not_sent(voice, project, monkeypatch, capsys):
    # Requirement: the "yes" covers the request the person saw. If another session edits the script after the run
    # checked the plan but before a block is sent, that block is checked again under the lock and not sent.
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    real = voice.balance

    def edited_meanwhile(key):
        script(project, "Совсем другой текст.")
        return real(key)
    monkeypatch.setattr(voice, "balance", edited_meanwhile)
    code = call(voice, "run", e, "--yes", "--plan", pid)
    assert "changed after the plan" in str(code) and not voice.fake.paid()


def test_a_short_balance_an_unknown_rate_and_a_dearer_setting_stop_before_any_paid_request(voice, project, capsys):
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    voice.fake.balance = 5
    pid = plan_id(voice, e, capsys)
    assert "NOT ENOUGH" in capsys.readouterr().out
    code = call(voice, "run", e, "--yes", "--plan", pid)
    assert "credits left" in str(code) and not voice.fake.paid()
    script(project, TEXT1, model="eleven_v3")
    assert "not supported" in str(call(voice, "plan", e))
    script(project, TEXT1, settings={"style": 0.4})
    assert "costs more" in str(call(voice, "plan", e))


def test_without_the_balance_permission_the_run_stops_before_sending(voice, project, capsys):
    # The real key of 2026-11-13 had no "User read": the subscription answered 401 missing_permissions.
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    import reels_online as ro
    real = ro.open_url

    def no_user(req, timeout, allowed=None):
        if req.full_url.endswith("/v1/user/subscription"):
            raise http_error(req.full_url, 401, {"status": "missing_permissions",
                                                 "message": "The API key you used is missing the permission user_read"})
        return real(req, timeout, allowed)
    ro.open_url = no_user
    code = call(voice, "run", e, "--yes", "--plan", pid)
    assert "user_read" in str(code) and "API keys" in str(code) and not voice.fake.paid()


# --- step 4: the run, its states and recovery ---------------------------------------------------------------------

@needs_ffmpeg
def test_a_connection_lost_before_the_answer_is_unknown_and_never_sent_again(voice, project, tmp_path, capsys):
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [ConnectionResetError("the connection was reset")]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 2
    gen = json.loads((e / "voice_gen.json").read_text(encoding="utf-8"))
    assert [a["state"] for a in gen["attempts"].values()] == ["unknown"]
    assert len(voice.fake.paid()) == 1
    voice.fake.tts = [(tts_answer(tmp_path, TEXT1, WORDS1, 2.0), {})]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 2 and len(voice.fake.paid()) == 1  # not again
    assert "voice recover" in capsys.readouterr().out
    assert call(voice, "plan", e) == 0 and "BLOCKED" in capsys.readouterr().out


@needs_ffmpeg
def test_a_cut_answer_and_a_full_disk_keep_the_paid_request_id_and_send_nothing_again(voice, project, tmp_path,
                                                                                        monkeypatch, capsys):
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    good = tts_answer(tmp_path, TEXT1, WORDS1, 2.0)
    cut = json.dumps(good).encode()[:5000]  # the body ends mid-way: not JSON
    voice.fake.tts = [(cut, {})]
    assert call(voice, "run", e, "--yes", "--plan", pid) != 0
    at = next(iter(json.loads((e / "voice_gen.json").read_text(encoding="utf-8"))["attempts"].values()))
    assert at["state"] == "unknown" and at["request_id"] and "not complete" in at["error"]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 2 and len(voice.fake.paid()) == 1
    # a full disk when the answer is being kept: unknown, with the request id to find it in the history
    e2 = project / "edit" / "v2"
    write_json(e2 / "voice_script.json", {"voice": "me", "blocks": [{"id": "b1", "text": TEXT1}]})
    turn_on(e2)
    pid2 = plan_id(voice, e2, capsys)
    voice.fake.tts = [(good, {})]

    def full(path, data):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(voice, "write_atomic", full)
    assert call(voice, "run", e2, "--yes", "--plan", pid2) == 2
    at = next(iter(json.loads((e2 / "voice_gen.json").read_text(encoding="utf-8"))["attempts"].values()))
    assert at["state"] == "unknown" and at["request_id"] and "could not be saved" in at["error"]


@needs_ffmpeg
def test_a_run_stopped_after_the_answer_was_kept_takes_it_up_without_paying_again(voice, project, tmp_path,
                                                                                    monkeypatch, capsys):
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [(tts_answer(tmp_path, TEXT1, WORDS1, 2.0), {})]
    real = voice.update_attempt

    def crash(e_, fp, owner, **f):
        if f.get("state") == "received":
            raise KeyboardInterrupt("the laptop went to sleep")
        return real(e_, fp, owner, **f)
    monkeypatch.setattr(voice, "update_attempt", crash)
    with pytest.raises(KeyboardInterrupt):
        voice.main(["run", str(e), "--yes", "--plan", pid])
    monkeypatch.setattr(voice, "update_attempt", real)
    assert call(voice, "run", e, "--yes", "--plan", pid) == 0
    assert len(voice.fake.paid()) == 1 and (e / "generated" / "narration.wav").is_file()


@needs_ffmpeg
def test_a_repeat_run_after_a_failure_half_way_voices_only_the_missing_blocks(voice, project, tmp_path, capsys):
    own_voice(voice)
    e = script(project, TEXT1, TEXT2, "Третий.")
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [(tts_answer(tmp_path, TEXT1, WORDS1, 2.0), {}),
                      http_error("https://api.elevenlabs.io/x", 401, {"status": "missing_permissions", "message": "tts"})]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 2
    assert len(voice.fake.paid()) == 2
    gen = json.loads((e / "voice_gen.json").read_text(encoding="utf-8"))
    assert sorted(a["state"] for a in gen["attempts"].values()) == ["saved"]  # the refused one is released
    assert call(voice, "run", e, "--yes", "--plan", pid) != 0  # the plan changed: b1 is paid for already
    pid2 = plan_id(voice, e, capsys)
    out = capsys.readouterr().out
    assert pid2 != pid
    voice.fake.tts = [(tts_answer(tmp_path, TEXT2, WORDS2, 1.6), {}),
                      (tts_answer(tmp_path, "Третий.", [("Третий.", 0.2, 0.8)], 1.0), {})]
    assert call(voice, "run", e, "--yes", "--plan", pid2) == 0
    sent = [x[2]["text"] for x in voice.fake.paid()]
    assert sent == [TEXT1, TEXT2, TEXT2, "Третий."]  # b1 once; b2 again only because it was refused uncharged


@needs_ffmpeg
def test_a_charge_over_the_ceiling_stops_the_run(voice, project, tmp_path, capsys):
    own_voice(voice)
    e = script(project, TEXT1, TEXT2)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [(tts_answer(tmp_path, TEXT1, WORDS1, 2.0), {"character-cost": str(len(TEXT1) + len(TEXT2))})]
    code = call(voice, "run", e, "--yes", "--plan", pid)
    assert "over its ceiling" in str(code) and len(voice.fake.paid()) == 1


# --- step 5: words, joining, transcript ---------------------------------------------------------------------------

def test_words_of_russian_text_from_the_alignment(voice):
    # Requirement: the script's own words get times; ё/е, hyphens, quotes and a lone dash do not break the match;
    # a number spoken as words takes the time of those words; a stretch that does not match is an error with its place.
    def al(text, words):
        return char_times(text, words)
    text = "«Ёлки» — кто-то сказал."
    spoken = [("«Елки»", 0.1, 0.6), ("—", 0.6, 0.65), ("кто-то", 0.7, 1.1), ("сказал.", 1.2, 1.7)]
    words, src = voice.words_for(text, al("«Елки» — кто-то сказал.", spoken))
    assert [w["text"] for w in words] == ["«Ёлки» —", "кто-то", "сказал."]
    # a word starts at its first letter: the opening quote has no sound (6 characters over 0.5 s: «Е at 0.1 + 0.5/6)
    assert words[0]["start"] == pytest.approx(0.1 + 0.5 / 6, abs=1e-3) and words[1]["start"] == 0.7
    assert src == "alignment"
    # numbers: the alignment carries what was read
    text = "Нам 25 лет."
    heard = [("Нам", 0.1, 0.3), ("двадцать", 0.4, 0.8), ("пять", 0.85, 1.1), ("лет.", 1.2, 1.4)]
    words, _ = voice.words_for(text, al("Нам двадцать пять лет.", heard))
    # a word ends with its last letter: the full stop has no sound ("лет." = 4 characters over 1.2..1.4 s)
    assert [(w["text"], w["start"], w["end"]) for w in words] == [("Нам", 0.1, 0.3), ("25", 0.4, 1.1),
                                                                  ("лет.", 1.2, 1.35)]
    # the plain alignment failed, the normalized one (its own characters and times) is used
    words, src = voice.words_for(text, {"characters": ["x"], "character_start_times_seconds": [0.0],
                                        "character_end_times_seconds": [0.1, 0.2]}, al("Нам двадцать пять лет.", heard))
    assert src == "normalized_alignment" and words[1]["text"] == "25"
    # a word the voice did not say
    with pytest.raises(voice.AlignError, match="word 2"):
        voice.words_for("Мама мыла раму.", al("Мама раму.", [("Мама", 0.1, 0.4), ("раму.", 0.5, 0.9)]))
    with pytest.raises(voice.AlignError):
        voice.words_for("Привет.", {"characters": ["П"], "character_start_times_seconds": [float("nan")],
                                    "character_end_times_seconds": [0.2]})


def test_a_transcript_word_outside_the_audio_or_missing_is_refused(voice):
    w = [{"text": "Раз", "start": 0.1, "end": 0.4}, {"text": "два.", "start": 0.5, "end": 3.0}]
    with pytest.raises(voice.AlignError, match="after the audio"):
        voice.check_words(w, "Раз два.", 1.0, "x")
    with pytest.raises(voice.AlignError, match="1 timed word"):
        voice.check_words(w[:1], "Раз два.", 1.0, "x")


def envelope(path, step=0.005):
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        data = array.array("h", w.readframes(w.getnframes()))
    n = int(rate * step)
    return [sum(abs(x) for x in data[k:k + n]) / max(1, len(data[k:k + n])) / 32768 for k in range(0, len(data), n)]


def onsets(env, step=0.005):
    out, quiet, thr = [], True, max(env) / 3
    for k, v in enumerate(env):
        if quiet and v > thr:
            out.append(round(k * step, 3))
            quiet = False
        elif v < thr / 4:
            quiet = True
    return out


@needs_ffmpeg
def test_blocks_join_by_samples_and_the_words_land_on_their_sound(voice, project, tmp_path, capsys):
    # Requirement: the narration is the blocks' audio, trimmed around the words, a bounded pause between blocks; every
    # word's time in the transcript is where its sound is in narration.wav; the transcript passes the core's check.
    own_voice(voice)
    e = script(project, TEXT1, TEXT2)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [(tts_answer(tmp_path, TEXT1, WORDS1, 2.5), {}), (tts_answer(tmp_path, TEXT2, WORDS2, 1.8), {})]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 0
    tr = json.loads((e / "transcripts" / "narration.json").read_text(encoding="utf-8"))
    import transcribe
    assert not [p for p in transcribe.check_doc(tr) if not p.startswith("note:")]
    assert [w["text"] for w in tr["words"]] == [w for w, _, _ in WORDS1 + WORDS2]
    assert tr["model"] == "elevenlabs:eleven_multilingual_v2:alignment" and tr["source_identity"]["size"] > 0
    gen = json.loads((e / "voice_gen.json").read_text(encoding="utf-8"))
    b1, b2 = gen["build"]["blocks"]
    # block 1 kept 0.25..1.95 s (LEAD before 0.3; TAIL after the last letter of "тест." at 1.7, the full stop has no
    # sound), then a sentence pause of 0.45 s
    assert b1["trim"] == [0.25, 1.95] and b1["pause_after"] == 0.45 and b2["at"] == pytest.approx(1.7 + 0.45, abs=1e-3)
    with wave.open(str(e / "generated" / "narration.wav"), "rb") as w:
        n, rate = w.getnframes(), w.getframerate()
    assert rate == 48000 and n / rate == pytest.approx(gen["build"]["duration"], abs=1e-4)
    starts = [w["start"] for w in tr["words"]]
    heard = onsets(envelope(e / "generated" / "narration.wav"))
    assert len(heard) == len(starts)
    for got, want in zip(heard, starts):
        assert abs(got - want) < 0.03, (heard, starts)


# --- step 6: the contract with the core ----------------------------------------------------------------------------

@needs_ffmpeg
def test_the_narration_goes_through_the_core_as_an_off_camera_voice(voice, project, tmp_path, capsys):
    # Requirement: after the run, the core's own path works with no hand edits: cut.py cuts the narration into
    # voice.wav with its subtitles, and visual_plan.py init --scenes-voice plans scenes over it. The project files
    # name the voice, never its id.
    own_voice(voice)
    e = script(project, TEXT1, TEXT2)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [(tts_answer(tmp_path, TEXT1, WORDS1, 2.5), {}), (tts_answer(tmp_path, TEXT2, WORDS2, 1.8), {})]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 0
    reel = json.loads((e / "reel.json").read_text(encoding="utf-8"))
    cut = json.loads((e / "cut.json").read_text(encoding="utf-8"))
    assert reel["voice"] == "off_camera"
    assert cut["sources"]["narration"]["file"] == "edit/v1/generated/narration.wav"
    assert cut["ranges"][0]["source"] == "narration" and cut["sources"]["narration"]["speed"] == 1.0
    env = {"REELS_OFFLINE": "1"}
    run_script("cut.py", "edit/v1", cwd=project, env=env)
    assert (e / "voice.wav").is_file()
    caps = json.loads((e / "captions.json").read_text(encoding="utf-8"))
    assert caps["voice"]["file"] == "voice.wav"  # the core's narration branch, not a video cut
    assert [w["text"] for w in caps["words"]] == [w for w, _, _ in WORDS1 + WORDS2]
    run_script("visual_plan.py", "init", "edit/v1", "--scenes-voice", cwd=project, env=env)
    plan = json.loads((e / "visual_plan.json").read_text(encoding="utf-8"))
    assert plan["format"] == "scenes-voice" and plan["duration"] == pytest.approx(caps["duration"], abs=0.05)
    for f in e.rglob("*.json"):
        assert VOICE_ID not in f.read_text(encoding="utf-8"), f


@needs_ffmpeg
def test_check_writes_its_own_transcript_and_keeps_the_main_one(voice, project, tmp_path, monkeypatch, capsys):
    # Requirement: voice check recognizes the narration into a separate transcript; the main one (the alignment) is
    # not touched, and the differences from the script are listed.
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [(tts_answer(tmp_path, TEXT1, WORDS1, 2.5), {})]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 0
    main = (e / "transcripts" / "narration.json").read_text(encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", STUBS)  # faster-whisper stand-in: hears "Hello big world."
    capsys.readouterr()
    assert call(voice, "check", e) == 0
    assert (e / "transcripts" / "narration.check.json").is_file()
    assert (e / "transcripts" / "narration.json").read_text(encoding="utf-8") == main
    out = capsys.readouterr().out
    assert "difference" in out and "Hello" in out and "listening" in out


def test_runner_knows_the_voice_command(project, tmp_path):
    env = {"REELS_OFFLINE": "1", "REELS_KEYS_FILE": str(tmp_path / "k.env")}
    run_script("reels_online.py", "link", "--project", project, cwd=project, env=env, scripts=ADDON)
    assert "voice" in run_script("addon.py", cwd=project, env=env).stdout
    r = run_script("addon.py", "voice", "list", cwd=project, env=env, check=False)
    assert r.returncode != 0 and "REELS_OFFLINE" in r.stderr


# --- the Codex review of 2026-11-13 ---------------------------------------------------------------------------------

def test_a_request_still_being_sent_cannot_be_cleared(voice, project, capsys):
    # Requirement: `clear --not-charged` is for a request found unpaid in the history after its run is over; a fresh
    # `submitting` reservation may be a request in flight, and clearing it would let another run pay for it again.
    own_voice(voice)
    e = script(project, TEXT1)
    req = voice.request_of(e, voice.load_script(e))
    fp = req["blocks"][0]["fingerprint"]
    write_json(e / "voice_gen.json", {"attempts": {fp: {"block": "b1", "state": "submitting", "owner": "1-abc",
                                                        "at": voice.now_iso()}}})
    code = call(voice, "clear", e, "b1", "--not-charged")
    assert "still" in str(code)
    assert json.loads((e / "voice_gen.json").read_text(encoding="utf-8"))["attempts"][fp]["state"] == "submitting"


def test_paid_requests_of_all_reels_go_one_at_a_time(voice, project, monkeypatch, capsys):
    # Requirement: the balance check and the paid request of one block are one step for the whole account: while
    # another run (another reel, another terminal) holds it, this run waits and then stops before sending, so two runs
    # cannot both spend the same remaining credits.
    import reels_online as ro
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    lock = Path(os.path.normcase(os.path.abspath(voice.spend_lock()))).with_name(voice.spend_lock().name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("4242 0\n")  # another run is spending right now
    monkeypatch.setattr(voice, "SPEND_WAIT", 0.3)
    code = call(voice, "run", e, "--yes", "--plan", pid)
    assert "busy" in str(code) and not voice.fake.paid()
    assert lock.is_file() and lock.parent == ro.KEYS_FILE.parent


def test_ambiguous_number_stretches_and_extra_speech_are_errors_and_spoken_signs_keep_their_time(voice):
    def al(text, words):
        return char_times(text, words)
    # "25 кг" read as three words: which word is "25" and which "кг" is a guess: an error with the place
    heard = [("Вес", 0.1, 0.3), ("двадцать", 0.4, 0.7), ("пять", 0.75, 0.9), ("килограммов.", 1.0, 1.6)]
    with pytest.raises(voice.AlignError, match="word 2"):
        voice.words_for("Вес 25 кг.", al("Вес двадцать пять килограммов.", heard))
    # a word the voice said that the script does not have
    with pytest.raises(voice.AlignError, match="not in the script"):
        voice.words_for("Привет мир.", al("Привет лишнее мир.", [("Привет", 0.1, 0.4), ("лишнее", 0.5, 0.9),
                                                                 ("мир.", 1.0, 1.3)]))
    # "50%": the sign is read ("процентов") and has a time of its own in the alignment of the text as sent
    a = {"characters": list("Рост 50%."), "character_start_times_seconds": [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.6, 0.8, 1.6],
         "character_end_times_seconds": [0.15, 0.2, 0.25, 0.3, 0.4, 0.6, 0.8, 1.6, 1.62]}
    words, _ = voice.words_for("Рост 50%.", a)
    assert words[1]["text"] == "50%." and words[1]["end"] == 1.6


@needs_ffmpeg
def test_an_unknown_block_is_recovered_from_its_history_item_with_its_timings(voice, project, tmp_path, capsys):
    # Requirement (checked live 2026-11-13: a history item carries its alignments, and its audio costs nothing): a block
    # whose answer was lost takes the audio and the timings of exactly its history item, with no new paid request and
    # no recognition; an item of another text leaves it unknown.
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [ConnectionResetError("reset")]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 2
    ans = tts_answer(tmp_path, TEXT1, WORDS1, 2.5)
    item = {"history_item_id": "hist0000good", "request_id": "r1", "voice_id": VOICE_ID,
            "model_id": "eleven_multilingual_v2", "text": TEXT1, "output_format": "mp3_44100_128",
            "alignments": {"alignment": ans["alignment"], "normalized_alignment": ans["normalized_alignment"]}}
    voice.fake.history = {"hist0000good": (item, base64.b64decode(ans["audio_base64"])),
                          "hist00000bad": ({**item, "text": "Другой текст."}, b"")}
    code = call(voice, "recover", e, "b1", "--history", "hist00000bad")
    assert "another text" in str(code)
    assert call(voice, "recover", e, "b1", "--history", "hist0000good") == 0
    at = next(iter(json.loads((e / "voice_gen.json").read_text(encoding="utf-8"))["attempts"].values()))
    assert at["state"] == "saved" and at["timing"] == "alignment" and at["history_item"] == "hist0000good"
    assert len(voice.fake.paid()) == 1  # only the lost one
    assert call(voice, "build", e) == 0
    words = json.loads((e / "transcripts" / "narration.json").read_text(encoding="utf-8"))["words"]
    assert [w["text"] for w in words] == [w for w, _, _ in WORDS1]


# --- the paid step 0 of 2026-11-13: what the live service does ------------------------------------------------------

def silent_start(ans):
    """The live answers give the first character a start of 0.0 s and stretch it over the silence before the voice."""
    for a in (ans["alignment"], ans["normalized_alignment"]):
        a["character_start_times_seconds"][0] = 0.0
    return ans


@needs_ffmpeg
def test_the_first_word_starts_where_its_sound_starts(voice, project, tmp_path, capsys):
    # Requirement: the first word's subtitle and the block's trim follow the voice, not the 0.0 s the alignment gives
    # its first character (the live answers start speaking about 0.17 s later).
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [(silent_start(tts_answer(tmp_path, TEXT1, WORDS1, 2.5)), {})]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 0
    words = json.loads((e / "transcripts" / "narration.json").read_text(encoding="utf-8"))["words"]
    gen = json.loads((e / "voice_gen.json").read_text(encoding="utf-8"))
    assert gen["build"]["blocks"][0]["trim"][0] == pytest.approx(0.25, abs=0.03)  # 0.05 s before the sound at 0.3
    assert words[0]["start"] == pytest.approx(0.05, abs=0.03)                      # on the narration's timeline


@needs_ffmpeg
def test_a_balance_that_has_not_caught_up_does_not_let_the_run_overspend(voice, project, tmp_path, capsys):
    # Requirement: the service shows a charge in the balance minutes later (2026-11-13), so the run counts its own
    # charges: with 20 credits, a 17-credit block and then a 12-credit one, the second is not sent.
    own_voice(voice)
    e = script(project, TEXT1, TEXT2)
    turn_on(e)
    voice.fake.balance = 20  # and it stays 20: the fake balance never catches up
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [(tts_answer(tmp_path, TEXT1, WORDS1, 2.5), {})]
    code = call(voice, "run", e, "--yes", "--plan", pid)
    assert "credits left" in str(code) and len(voice.fake.paid()) == 1


def test_a_voice_not_found_is_released_as_not_charged(voice, project, capsys):
    # Live 2026-11-13: 404 voice_not_found has no cost header, no history item and no charge.
    own_voice(voice)
    e = script(project, TEXT1)
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    voice.fake.tts = [http_error("https://api.elevenlabs.io/x", 404, {"status": "voice_not_found", "message": "no"})]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 2
    assert json.loads((e / "voice_gen.json").read_text(encoding="utf-8"))["attempts"] == {}
    assert "nothing was charged" in capsys.readouterr().out


@needs_ffmpeg
def test_pcm_answers_are_decoded_too(voice, project, tmp_path, capsys):
    # Live 2026-11-13: pcm_24000 works on Starter, its length equal to the alignment's end.
    own_voice(voice)
    e = script(project, TEXT1, output_format="pcm_24000")
    turn_on(e)
    pid = plan_id(voice, e, capsys)
    ans = tts_answer(tmp_path, TEXT1, WORDS1, 2.5)
    mp3 = tmp_path / "x.mp3"
    mp3.write_bytes(base64.b64decode(ans["audio_base64"]))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1", "-ar", "24000", "-"],
                         capture_output=True, check=True).stdout
    ans["audio_base64"] = base64.b64encode(raw).decode()
    voice.fake.tts = [(ans, {})]
    assert call(voice, "run", e, "--yes", "--plan", pid) == 0
    assert "output_format=pcm_24000" in voice.fake.paid()[0][1]
    gen = json.loads((e / "voice_gen.json").read_text(encoding="utf-8"))
    assert gen["build"]["duration"] == pytest.approx(1.95 - 0.25 + 0.0, abs=0.02)


def test_check_does_not_count_a_heard_dash_as_a_word(voice):
    # Live 2026-11-13: the recognizer wrote "—" as a word of its own; the check listed it as a difference from the
    # script, though nothing differed.
    heard = [{"text": "Ни", "start": 3.5}, {"text": "дублей", "start": 3.7}, {"text": "—", "start": 4.04},
             {"text": "а", "start": 4.1}, {"text": "голос", "start": 4.2}, {"text": "мой.", "start": 4.5}]
    assert voice.compare("Ни дублей — а голос мой.", heard) == []
    assert len(voice.compare("Ни дублей — а голос твой.", heard)) == 1
