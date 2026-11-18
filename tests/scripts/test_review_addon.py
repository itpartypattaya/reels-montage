"""Findings 42, 43 and 47 of the 2026-11-17 review (the add-on): a failed fal job, the keys file as people write it,
the message when the core is older than the add-on. Fake network only."""
import importlib
import io
import sys
import types
import urllib.error
from types import SimpleNamespace

import pytest

from conftest import ADDON

FAL = "https://queue.fal.run/fal-ai/veo3.1/requests/r1"


@pytest.fixture
def online(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ADDON))
    import reels_online
    monkeypatch.setattr(reels_online, "KEYS_FILE", tmp_path / "cfg" / "keys.env")
    monkeypatch.setattr(reels_online, "_KEYS", None)
    for n in reels_online.known_keys():
        monkeypatch.delenv(n, raising=False)
    return reels_online


# --- 42: fal reports a failed or cancelled request as COMPLETED with an error ---------------------------------------

def fal_job():
    return {"id": "b01", "status": "pending",
            "gen": {"job": {"request_id": "r1", "status_url": FAL + "/status", "response_url": FAL}}}


def answer(status, result_code):
    """fal_http as fal answers: the status, then the result endpoint (an HTTP error with result_code)."""
    def http(url, key, payload=None, timeout=30):
        if url.endswith("/status"):
            return status
        raise urllib.error.HTTPError(url, result_code, "error", {}, io.BytesIO(b'{"detail": "x"}'))
    return http


@pytest.mark.parametrize("status, result_code", [
    ({"status": "COMPLETED", "error": "Internal error", "error_type": "runner_server_error"}, 500),
    ({"status": "COMPLETED", "error": "The request was cancelled", "error_type": "client_cancelled"}, 500),
    ({"status": "COMPLETED"}, 422),  # a validation error of the request: its result is the error, for good
])
def test_a_failed_fal_job_is_given_up_not_resumed_forever(online, tmp_path, monkeypatch, status, result_code):
    # Requirement: a paid job that fal ended with an error has no clip to wait for. It leaves gen.job (kept in
    # job_failed) and the message says a new run pays again, instead of "resumes without paying" on every run.
    # fal has no FAILED status: a failed or cancelled request is COMPLETED with `error` (docs, 2026-11-18).
    import genfootage
    monkeypatch.setattr(genfootage, "fal_http", answer(status, result_code))
    monkeypatch.setattr(genfootage, "put", lambda *a: None)
    i = fal_job()
    genfootage.finish_job(tmp_path, i, "dummy")
    assert "job" not in i["gen"] and i["gen"]["job_failed"]["request_id"] == "r1"
    assert "paid again" in i["fallback"]
    if status.get("error_type"):
        assert status["error_type"] in i["gen"]["job_failed"]["error"]


def test_a_refused_key_on_the_result_keeps_the_paid_job(online, tmp_path, monkeypatch):
    # control: 401 on the result is the key, not the job; the clip is still there for a run with a working key
    import genfootage
    monkeypatch.setattr(genfootage, "fal_http", answer({"status": "COMPLETED"}, 401))
    monkeypatch.setattr(genfootage, "put", lambda *a: None)
    i = fal_job()
    genfootage.finish_job(tmp_path, i, "dummy")
    assert i["gen"]["job"]["request_id"] == "r1" and "job_failed" not in i["gen"]
    assert "without paying again" in i["fallback"]


# --- 43: keys.env as a person or another tool writes it -------------------------------------------------------------

KEYS_TEXT = ("﻿PEXELS_API_KEY=pex-1234567890abcd\r\n"
             "export FAL_KEY=fal-abcdef1234567890\r\n"
             "OPENAI_API_KEY=sk-abc123456789 # my work key\r\n"
             "GROQ_API_KEY=\"gsk-quoted#not-a-comment\"   # the free tier\r\n"
             "  # a comment line\r\n"
             "GEMINI_API_KEY=gm-a#b\r\n")


def test_a_keys_file_with_bom_export_and_comments_is_read_as_written(online):
    # Requirement: a keys file saved by Notepad (BOM, CRLF), copied from a shell profile (`export NAME=...`) or with a
    # note after the value gives the key itself; before, the first key and an exported one were missing and the
    # comment went to the provider as part of the key
    online.KEYS_FILE.parent.mkdir(parents=True)
    online.KEYS_FILE.write_bytes(KEYS_TEXT.encode("utf-8"))
    assert online.api_key("PEXELS_API_KEY") == "pex-1234567890abcd"
    assert online.api_key("FAL_KEY") == "fal-abcdef1234567890"
    assert online.api_key("OPENAI_API_KEY") == "sk-abc123456789"
    assert online.api_key("GROQ_API_KEY") == "gsk-quoted#not-a-comment"
    assert online.api_key("GEMINI_API_KEY") == "gm-a#b"  # a # inside the value, with no space before it, is the key's


def test_keys_remove_finds_an_exported_key_and_the_first_one(online):
    online.KEYS_FILE.parent.mkdir(parents=True)
    online.KEYS_FILE.write_bytes(KEYS_TEXT.encode("utf-8"))
    online.cmd_keys_remove(SimpleNamespace(name="FAL_KEY"))
    online.cmd_keys_remove(SimpleNamespace(name="PEXELS_API_KEY"))
    online._KEYS = None
    text = online.KEYS_FILE.read_text(encoding="utf-8")
    assert "FAL_KEY" not in text and "PEXELS_API_KEY" not in text
    assert online.api_key("FAL_KEY") is None and online.api_key("PEXELS_API_KEY") is None
    assert online.api_key("OPENAI_API_KEY") == "sk-abc123456789"  # the rest is untouched


# --- 47: an older core: the message names what is missing ----------------------------------------------------------

@pytest.mark.parametrize("mod, core_mod", [("genfootage", "codescene"), ("voice_online", "reels_common"),
                                           ("matte_server", "reels_common")])
def test_an_older_core_is_named_with_what_it_lacks(online, monkeypatch, mod, core_mod):
    # Requirement: a core without a name the add-on imports says "update the core" and names the missing import;
    # before, it said "run this through the core" to someone who did just that
    monkeypatch.setitem(sys.modules, core_mod, types.ModuleType(core_mod))  # the module is there, its names are not
    monkeypatch.delitem(sys.modules, mod, raising=False)
    with pytest.raises(SystemExit) as ex:
        importlib.import_module(mod)
    msg = str(ex.value.code)
    assert "update" in msg and "it-reelsmaker" in msg and "cannot import name" in msg, msg


@pytest.mark.parametrize("mod, core_mod", [("genfootage", "codescene"), ("voice_online", "reels_common"),
                                           ("matte_server", "reels_common")])
def test_without_the_core_the_message_says_run_it_through_the_core(online, monkeypatch, mod, core_mod):
    # control: no core module on the path at all is still "run this through the core"
    monkeypatch.setitem(sys.modules, core_mod, None)
    monkeypatch.delitem(sys.modules, mod, raising=False)
    with pytest.raises(SystemExit) as ex:
        importlib.import_module(mod)
    assert "run this through" in str(ex.value.code) and "core" in str(ex.value.code)
