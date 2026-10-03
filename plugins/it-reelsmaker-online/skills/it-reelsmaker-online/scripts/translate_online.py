# -*- coding: utf-8 -*-
"""Subtitle translation through a language model's API, into the core's subs/<lang>.json. Part of the
it-reelsmaker-online add-on; run through the core:

    python <core scripts>/addon.py translate edit/<id> --to en --provider anthropic|openai|gemini [--model M] [--yes]
    python <core scripts>/addon.py translate edit/<id> --to en --provider openai --price     # only the estimate

By default the agent translates the phrases itself, in the session (core: subs.py, free). This command is for a
translation without a session or a second opinion: it sends the phrases of the speech (subs.py phrases makes them if
missing) with the brand's voice and forbidden words, asks for one translation per phrase within the time the
phrase is on screen, writes them into the phrases still empty (--force: all of them) and runs the core's check
(subs.py apply → captions-<lang>.json). Only text is sent: no audio, no video.

Providers and default models (references/sources.md; --model or the setting translation_model picks another):
  anthropic — claude-sonnet-5-5 (Messages API, ANTHROPIC_API_KEY)
  openai    — gpt-6.1-sol (Responses API, OPENAI_API_KEY)
  gemini    — gemini-3.8-flash (generateContent, GEMINI_API_KEY)
A video's phrases are a few thousand tokens: a cent or less; the estimate prints the tokens.

Paid: --yes, or the person's standing choice `translation_provider` in the project defaults or reel.json; otherwise
only the estimate. No key, no network, a refused request: a warning, exit code 2, and the core way (the agent
translates in the session). REELS_OFFLINE=1: no network at all.
"""
import argparse, json, re, sys
from pathlib import Path

from reels_common import edit_dir, load_config, load_json, project_root, save_json, utf8_stdio, warn
from reels_online import api_key
from transcribe_online import NoService, post
import subs

PROVIDERS = {
    "anthropic": {"key": "ANTHROPIC_API_KEY", "model": "claude-sonnet-5-5", "host": "https://api.anthropic.com/"},
    "openai": {"key": "OPENAI_API_KEY", "model": "gpt-6.1-sol", "host": "https://api.openai.com/"},
    "gemini": {"key": "GEMINI_API_KEY", "model": "gemini-3.8-flash", "host": "https://generativelanguage.googleapis.com/"},
}
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,80}$")
CORE_WAY = "the agent translates the phrases in the session: subs.py phrases, then subs.py apply"


def brief(lang, src_lang, brand, ps):
    """(instructions, the phrases as JSON) for the model."""
    voice = (brand or {}).get("voice") or ""
    banned = (brand or {}).get("forbidden_words") or []
    if isinstance(banned, str):
        banned = [banned]
    rules = [
        f"Translate video subtitles into the language with the code '{lang}'" + (f" from '{src_lang}'" if src_lang else "") + ".",
        "Each item is one spoken phrase. Return exactly one translation per id, in the same order; never merge or "
        "split phrases, never add or drop ids.",
        "Keep it as short as the speech: max_chars is the most that can be read while the phrase is on screen; "
        "go under it, drop filler words rather than meaning.",
        "Names, numbers, brands and terms stay as they are said. Keep questions as questions.",
        "Keep the speaker's form of address: a polite or plural 'you' in the source stays polite in the translation "
        "(German Sie, French vous), an informal one stays informal; keep the meaning of every phrase.",
        "Spoken, natural language for a short vertical video, not a literal translation.",
    ]
    if voice:
        rules.append(f"Brand voice: {voice}.")
    if banned:
        rules.append("Never use these words: " + ", ".join(map(str, banned)) + ".")
    rules.append('Answer with JSON only: {"phrases": [{"id": "p001", "text": "..."}, ...]}')
    items = []
    for k, p in enumerate(ps):
        nxt = ps[k + 1]["start"] if k + 1 < len(ps) else p["end"] + 0.4
        dur = max(0.3, min(nxt, p["end"] + 0.4) - p["start"])
        items.append({"id": p["id"], "src": p["src"], "max_chars": max(len(p["src"]), int(17 * dur))})
    return "\n".join(rules), json.dumps({"phrases": items}, ensure_ascii=False)


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["phrases"],
          "properties": {"phrases": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["id", "text"],
              "properties": {"id": {"type": "string"}, "text": {"type": "string"}}}}}}


def call(provider, model, key, system, user):
    """→ the model's answer text (JSON expected)."""
    host = PROVIDERS[provider]["host"]
    ok = lambda u: str(u).startswith(host)
    if provider == "anthropic":
        r = post(host + "v1/messages", json.dumps({
            "model": model, "max_tokens": 8000, "system": system,
            "messages": [{"role": "user", "content": user}]}).encode(),
            {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, 180, ok)
        return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
    if provider == "openai":
        r = post(host + "v1/responses", json.dumps({
            "model": model, "instructions": system, "input": user,
            "text": {"format": {"type": "json_schema", "name": "subtitles", "schema": SCHEMA, "strict": True}}}).encode(),
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, 180, ok)
        return "".join(c.get("text", "") for o in r.get("output", []) if o.get("type") == "message"
                       for c in o.get("content", []) if c.get("type") == "output_text")
    r = post(f"{host}v1beta/models/{model}:generateContent", json.dumps({
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"responseMimeType": "application/json"}}).encode(),
        {"x-goog-api-key": key, "Content-Type": "application/json"}, 180, ok)
    return "".join(p.get("text", "") for c in r.get("candidates", [])[:1]
                   for p in (c.get("content") or {}).get("parts", []))


def parse(text, ids):
    """{id: translation} from the model's answer; a list of problems when it is not one translation per id."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        got = json.loads(m.group(0) if m else "")["phrases"]
        out = {str(x["id"]): str(x["text"]).strip() for x in got}
    except Exception:
        return {}, ["the answer is not the expected JSON"]
    probs = [f"no translation for {i}" for i in ids if not out.get(i)]
    probs += [f"an unknown id {i}" for i in out if i not in ids]
    return {i: t for i, t in out.items() if i in ids and t}, probs


def cmd_run(a):
    project = project_root()
    e = edit_dir(a.edit, project)
    s, _, _, _, brand = load_config(e)
    provider = a.provider or str(s.get("translation_provider") or "")
    if provider not in PROVIDERS:
        sys.exit(f"--provider is needed ({', '.join(PROVIDERS)}), or translation_provider in the settings")
    model = a.model or (s.get("translation_model") if s.get("translation_provider") == provider else None) \
        or PROVIDERS[provider]["model"]
    if not MODEL_RE.match(model):
        sys.exit(f"--model {model!r}: not a model name")
    f = subs.subs_file(e, a.to)
    cap = subs.load_cap(e)
    doc = load_json(f)
    if not doc or doc.get("captions") != subs.fingerprint(cap):
        subs.cmd_phrases(argparse.Namespace(edit=a.edit, lang=a.to))
        doc = load_json(f)
    todo = [p for p in doc["phrases"] if a.force or not str(p.get("text") or "").strip()]
    if not todo:
        print(f"{f}: every phrase is translated already (--force to translate all again)")
        return 0
    system, user = brief(a.to, cap.get("language") or "", brand, todo if not a.force else doc["phrases"])
    tokens = (len(system) + len(user)) // 3 + len(user) // 2
    print(f"{len(todo)} phrase(s) → {a.to} with {provider} {model}: about {tokens} tokens (a cent or less; "
          f"the provider's price page has the exact price)")
    if a.price:
        return 0
    if not (a.yes or str(s.get("translation_provider") or "") == provider):
        print(f"paid: run again with --yes after the person agrees, or set translation_provider={provider} in the "
              f"project defaults")
        return 0
    key = api_key(PROVIDERS[provider]["key"])
    try:
        if not key:
            raise NoService(f"no {PROVIDERS[provider]['key']} key: the person adds it in their own terminal with "
                            f"reels_online.py keys set {PROVIDERS[provider]['key']}")
        answer = call(provider, model, key, system, user)
    except NoService as ex:
        warn(f"{provider} {model}: {ex}. Instead {CORE_WAY}")
        return 2
    ids = [p["id"] for p in todo]
    got, probs = parse(answer, ids)
    for x in probs:
        warn(f"{provider}: {x}")
    if not got:
        warn(f"{provider} {model}: nothing usable came back; nothing written. Instead {CORE_WAY}")
        return 2
    for p in doc["phrases"]:
        if p["id"] in got:
            p["text"] = got[p["id"]]
    doc["translated_by"] = f"{provider} {model}"
    save_json(f, doc)
    print(f"{f}: {len(got)} of {len(todo)} phrase(s) translated by {provider} {model}")
    for p in doc["phrases"]:
        if p["id"] in got:
            print(f"  {p['id']} {p['start']:7.2f}  {p['src']}\n                {p['text']}")
    if probs:
        print(f"the rest: translate them in the session, then subs.py apply {a.edit} --lang {a.to}")
        return 2
    subs.cmd_apply(argparse.Namespace(edit=a.edit, lang=a.to))
    return 0


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="addon.py translate", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit")
    ap.add_argument("--to", required=True, help="language code of the subtitles, e.g. en, de, pt-BR")
    ap.add_argument("--provider", choices=sorted(PROVIDERS), help="default: translation_provider from the settings")
    ap.add_argument("--model", help="another model of the provider")
    ap.add_argument("--yes", action="store_true", help="the person agreed to the paid request")
    ap.add_argument("--price", action="store_true", help="only the estimate; nothing is sent")
    ap.add_argument("--force", action="store_true", help="translate every phrase again, not only the empty ones")
    a = ap.parse_args(argv)
    sys.exit(cmd_run(a))


if __name__ == "__main__":
    main()
