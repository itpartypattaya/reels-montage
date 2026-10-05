"""addon.py translate: the phrases to a model's API and back into the core's subs/<lang>.json, then the core check.
No network: post() is replaced by canned answers in each provider's own response shape."""
import json

import pytest

from conftest import ADDON
from test_plan import plan_project
from test_subs import EN_TO_DE

KEY = "test-secret-key-value-987654321"


@pytest.fixture
def tr(project, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ADDON))
    import reels_online
    import translate_online
    monkeypatch.setattr(reels_online, "KEYS_FILE", tmp_path / "cfg" / "keys.env")
    monkeypatch.setattr(reels_online, "_KEYS", None)
    for n in reels_online.known_keys():
        monkeypatch.delenv(n, raising=False)
    monkeypatch.delenv("REELS_OFFLINE", raising=False)
    return translate_online


def answer_for(user, drop=()):
    items = json.loads(user)["phrases"]
    return json.dumps({"phrases": [{"id": p["id"], "text": EN_TO_DE[p["src"]]} for p in items if p["id"] not in drop]},
                      ensure_ascii=False)


def shaped(provider, text):
    if provider == "anthropic":
        return {"content": [{"type": "text", "text": text}]}
    if provider == "openai":
        return {"output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": text}]}]}
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def run(mod, *args):
    with pytest.raises(SystemExit) as ex:
        mod.main(["edit/4821", "--to", "de", *args])
    return ex.value.code


@pytest.mark.parametrize("provider,url,header", [
    ("anthropic", "https://api.anthropic.com/v1/messages", "x-api-key"),
    ("openai", "https://api.openai.com/v1/responses", "Authorization"),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent", "x-goog-api-key"),
])
def test_each_provider_fills_the_phrases_and_the_core_checks_them(tr, project, monkeypatch, capsys, provider, url, header):
    e = plan_project(project, {"brand": "acme"})
    brand = json.loads((project / "brands" / "acme" / "brand.json").read_text(encoding="utf-8"))
    brand.update(voice="calm and precise", forbidden_words=["guaranteed"])
    (project / "brands" / "acme" / "brand.json").write_text(json.dumps(brand), encoding="utf-8")
    monkeypatch.setenv(tr.PROVIDERS[provider]["key"], KEY)
    seen = []

    def fake(u, body, headers, timeout, allowed):
        seen.append((u, headers, json.loads(body)))
        assert allowed(u) and not allowed("https://evil.example/")
        req = json.loads(body)
        user = (req.get("messages") or [{}])[0].get("content") or req.get("input") or req["contents"][0]["parts"][0]["text"]
        return shaped(provider, answer_for(user))
    monkeypatch.setattr(tr, "post", fake)

    assert run(tr, "--provider", provider) == 0 and not seen  # paid: only the estimate without --yes
    assert run(tr, "--provider", provider, "--yes") == 0
    u, headers, body = seen[0]
    assert u == url and KEY in str(headers[header])
    system = body.get("system") or body.get("instructions") or body["systemInstruction"]["parts"][0]["text"]
    assert "calm and precise" in system and "guaranteed" in system and "'de'" in system
    doc = json.loads((e / "subs" / "de.json").read_text(encoding="utf-8"))
    assert all(p["text"] for p in doc["phrases"]) and doc["translated_by"].startswith(provider)
    assert (e / "captions-de.json").is_file()  # the core's apply ran
    assert KEY not in capsys.readouterr().out
    assert run(tr, "--provider", provider, "--yes") == 0 and len(seen) == 1  # nothing left to translate


def test_a_missing_phrase_is_left_for_the_session(tr, project, monkeypatch, capsys):
    e = plan_project(project)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setattr(tr, "post", lambda u, body, h, t, a: shaped("openai", answer_for(json.loads(body)["input"], {"p003"})))
    assert run(tr, "--provider", "openai", "--yes") == 2
    doc = json.loads((e / "subs" / "de.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in doc["phrases"] if not p["text"]] == ["p003"]
    assert not (e / "captions-de.json").exists()
    assert "no translation for p003" in capsys.readouterr().err


def test_no_key_and_refusal(tr, project, monkeypatch, capsys):
    import io
    import urllib.error
    plan_project(project)
    assert run(tr, "--provider", "anthropic", "--yes") == 2
    assert "keys set ANTHROPIC_API_KEY" in capsys.readouterr().err
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    import transcribe_online

    def refused(req, timeout, allowed=None):
        body = json.dumps({"type": "error", "error": {"type": "authentication_error", "message": f"bad key {KEY}"}})
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(body.encode()))
    monkeypatch.setattr(transcribe_online, "open_url", refused)
    assert run(tr, "--provider", "anthropic", "--yes") == 2
    err = capsys.readouterr().err
    assert "HTTP 401" in err and KEY not in err and "in the session" in err


def test_parse_rejects_junk(tr):
    assert tr.parse("sorry, I cannot", ["p001"]) == ({}, ["the answer is not the expected JSON"])
    got, probs = tr.parse('```json\n{"phrases": [{"id": "p001", "text": "Hallo"}, {"id": "p999", "text": "x"}]}\n```',
                          ["p001", "p002"])
    assert got == {"p001": "Hallo"} and "no translation for p002" in probs and "an unknown id p999" in probs


def test_forced_retranslation_empties_what_the_model_skipped(tr, project, monkeypatch):
    # review of #12: with --force a skipped phrase kept its old text, so a plain rerun would never retry it
    e = plan_project(project)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setattr(tr, "post", lambda u, body, h, t, a: shaped("openai", answer_for(json.loads(body)["input"])))
    assert run(tr, "--provider", "openai", "--yes") == 0
    monkeypatch.setattr(tr, "post", lambda u, body, h, t, a: shaped("openai", answer_for(json.loads(body)["input"], {"p002"})))
    assert run(tr, "--provider", "openai", "--yes", "--force") == 2
    doc = json.loads((e / "subs" / "de.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in doc["phrases"] if not p["text"]] == ["p002"]  # left for the next run or the session


def test_nothing_to_translate_still_rebuilds_the_subtitles(tr, project, monkeypatch):
    # Codex review: after a timing-only re-cut every phrase kept its translation, so the command exited without apply
    from test_plan import captions
    from conftest import write_json
    e = plan_project(project)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setattr(tr, "post", lambda u, body, h, t, a: shaped("openai", answer_for(json.loads(body)["input"])))
    assert run(tr, "--provider", "openai", "--yes") == 0
    cap = captions()
    for w in cap["words"]:
        w["start"], w["end"] = round(w["start"] + 0.5, 3), round(w["end"] + 0.5, 3)
    write_json(e / "captions.json", cap)
    monkeypatch.setattr(tr, "post", lambda *a: pytest.fail("nothing new to translate: no paid request"))
    assert run(tr, "--provider", "openai", "--yes") == 0
    de = json.loads((e / "captions-de.json").read_text(encoding="utf-8"))
    assert de["words"][0]["start"] == 0.7  # rebuilt on the new times


def test_the_estimate_does_not_promise_a_price(tr, project, capsys):
    plan_project(project)
    assert run(tr, "--provider", "gemini", "--price") == 0
    out = capsys.readouterr().out
    assert "tokens" in out and "cent" not in out


@pytest.mark.parametrize("module,missing", [("translate_online", "subs"), ("transcribe_online", "transcribe")])
def test_an_older_core_gets_a_message_not_a_traceback(tmp_path, module, missing):
    """An older core (before 1.5.0) lacks subs.py and parts of transcribe.py: the add-on says to update the core."""
    import subprocess
    import sys
    names = "edit_dir load_config load_json locked project_root save_json utf8_stdio warn".split()
    (tmp_path / "reels_common.py").write_text("".join(f"{n} = None\n" for n in names), encoding="utf-8")
    code = f"import sys; sys.path[:0] = [{str(tmp_path)!r}, {str(ADDON)!r}]; import {module}"
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1 and "Traceback" not in r.stderr, r.stderr
    assert "it-reelsmaker >= 1.5.0" in r.stderr and missing in r.stderr
