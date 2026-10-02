# -*- coding: utf-8 -*-
"""Model engine for generated B-roll: a video model through an API (photorealism: people, places, real objects).

Part of the it-reelsmaker-online add-on. Default: fal.ai + Veo 3.1 Fast. Paid: a run starts only with
generate_now=true, the FAL_KEY key and the person's approval (“yes”) of the price (`run --yes`). Without that the
prompt is ready in generated/prompts.md and the edit goes on without the insert (fallback: the main footage).
Code scenes (engine "code"), scaffold, render and picking up finished clips (`ingest`, also clips made by hand in any
service) are in the core: codescene.py.

Run through the core (the add-on must be linked to the project, see reels_online.py link):
    python <core scripts>/addon.py gen manifest edit/<id>         # generated/prompts.json + prompts.md for engine "model"
    python <core scripts>/addon.py gen validate edit/<id>         # prompt fields, text in the frame, forbidden imagery, faces
    python <core scripts>/addon.py gen run      edit/<id> [--yes] # send to the model (only with a key and the person's "yes")

Prompt fields (insert.gen in visual_plan.json, in English: models understand it better):
  engine (code|model), subject, action, camera, composition, lighting, mood, start, end, [setting], [style], [seconds], [use_from]
"""
import argparse, hashlib, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request, uuid

try:  # the core's scripts folder is on sys.path when this runs through the core's addon.py
    from codescene import (CODE_STYLE, FIELDS, base_item, check as core_check, engine_of, gen_inserts, md_head, md_tail,
                           num, plan_of, put, safe_ingest, scene_text, scene_words)
    from reels_common import edit_dir, editing_json, effective, load_json, safe_slug, save_json, utf8_stdio, warn
except ImportError:
    sys.exit("run this through the core: python <it-reelsmaker scripts>/addon.py gen <command> ...")
from reels_online import GEN_KEYS, api_key, color_name, download, err_text, offline, open_url, read_json_response

# Models through fal.ai (queue: submit -> status_url -> response_url -> video.url). Prices without audio, per second,
# checked on 2026-10-01; check the text-to-video endpoints on the model's page before the first run.
MODELS = {
    "veo3.1-fast": {"endpoint": "fal-ai/veo3.1/fast", "i2v": "fal-ai/veo3.1/fast/image-to-video", "image_key": "image_url",
                    "duration": lambda s: f"{s}s", "durations": [4, 6, 8], "usd_s": 0.10, "neg": True},
    "veo3.1-lite": {"endpoint": "fal-ai/veo3.1/lite", "i2v": "fal-ai/veo3.1/lite/image-to-video", "image_key": "image_url",
                    "duration": lambda s: f"{s}s", "durations": [4, 6, 8], "usd_s": 0.03, "neg": True, "note": "720p, upscaled"},
    "kling-v3-std": {"endpoint": "fal-ai/kling-video/v3/standard/text-to-video",
                     "i2v": "fal-ai/kling-video/v3/standard/image-to-video", "image_key": "start_image_url",
                     "duration": str, "durations": list(range(3, 16)), "usd_s": 0.084, "neg": True},
    "ltx-2.3": {"endpoint": "fal-ai/ltx-2.3/text-to-video", "i2v": "fal-ai/ltx-2.3/image-to-video", "image_key": "image_url",
                "duration": str, "durations": [6, 8, 10], "usd_s": 0.08, "neg": False, "note": "native 1080×1920"},
}
PROVIDERS_SUPPORTED = {"fal"}  # the script only drives the fal.ai queue; another provider -> a prompt to run by hand
PHOTO_STYLE = "photorealistic, natural color grade, cinematic 24 fps"
AI_LABEL = "turn on the AI info label when publishing"  # Meta's rules for photorealistic model footage
# Cyrillic letters in the fields: video models understand English better
CYR = "[" + chr(0x430) + "-" + chr(0x44F) + chr(0x451) + "]"


def model_spec(s):
    """(provider, model, spec, why it can't run): the pair is checked before the price and before the network."""
    prov = s.get("generation_provider") or "fal"
    model = s.get("generation_model") or "veo3.1-fast"
    if prov not in PROVIDERS_SUPPORTED:
        return prov, model, None, (f"provider {prov} is not supported by the script (supported: "
                                   f"{', '.join(sorted(PROVIDERS_SUPPORTED))}); run the prompt by hand and put the clip "
                                   f"at generated/<insert>.mp4, then codescene.py ingest")
    if model not in MODELS:
        return prov, model, None, f"unknown model {model} (available: {', '.join(MODELS)}); fix generation_model"
    return prov, model, MODELS[model], None


def build_prompt(g, seconds, brand):
    code = g.get("engine") == "code"
    pal = ""
    if brand and g.get("engine", "model") == "model" and g.get("brand_palette", True):
        c = brand.get("colors", {})
        names = list(dict.fromkeys(color_name(c[k]) for k in ("accent", "primary") if c.get(k)))
        pal = f", subtle color accents of {' and '.join(names)}" if names else ""
    return scene_text(g, seconds, CODE_STYLE if code else PHOTO_STYLE, pal)


def negative(brand):
    base = ["text", "captions", "letters", "logos", "watermark", "distorted hands", "extra fingers", "deformed faces",
            "flicker", "cuts"]
    return ", ".join(base + list((brand or {}).get("forbidden_imagery_en", [])))


def check(i, brand, lim_seconds=None):
    """The core's checks of the gen fields, plus the model's own: fields not in English and a large face."""
    errs, warns = core_check(i, brand, lim_seconds)
    g = i.get("gen") or {}
    if g.get("engine", "model") != "model":
        return errs, warns
    text = scene_words(g)
    pre, post = [], []
    if re.search(CYR, text, re.I):
        pre.append(f"{i['id']}: the fields are not in English (Cyrillic found); a video model understands English better")
    if re.search(r"\b(face|portrait|close-up of (a )?(man|woman|person))\b", text, re.I):
        post.append(f"{i['id']}: a large face: models get faces wrong, and Meta will require the AI info label; "
                    f"prefer hands, objects, a wide shot")
    return errs, pre + warns + post


def cmd_manifest(a):
    e = edit_dir(a.edit)
    plan, (s, prov, doc, bdir, brand) = plan_of(e)
    eff, why = effective(s)
    items, md = [], [f"# Generation prompts: {plan['id']}", ""]
    prov_name, model, spec, unsupported = model_spec(s)
    spec = spec or {}
    mine = [i for i in gen_inserts(plan) if engine_of(i, eff) == "model"]
    for i in mine:
        g = i.setdefault("gen", {})
        g["engine"] = "model"
        sec = int(num(g.get("seconds"), None) or num(s.get("generation_seconds"), 6) or 6)
        if spec and sec not in spec["durations"]:
            sec = min(spec["durations"], key=lambda d: (d < i["dur"] + 0.3, abs(d - sec)))
        g["seconds"] = sec
        g["publish_note"] = AI_LABEL
        errs, warns = check(i, brand)
        prompt = build_prompt(g, sec, brand) if not errs else None
        can = bool(eff.get("generate_now")) and not unsupported
        item = base_item(i, "model", sec, errs, warns)
        item.update({"prompt": prompt, "negative": negative(brand), "provider": prov_name, "model": model,
                     "endpoint": spec.get("endpoint"), "est_cost_usd": round(spec.get("usd_s", 0) * sec, 2) if spec else None,
                     "can_run_now": can, "why_not_now": None if can else (unsupported or why.get("generate_now")),
                     "job": g.get("job")})
        if unsupported:
            item["warnings"].append(f"{i['id']}: {unsupported}")
        items.append(item)
        md += md_head(i, "model", sec)
        if prompt:
            md += ["```text", prompt, "```", ""]
        cost = f"≈ ${item['est_cost_usd']}" if item["est_cost_usd"] is not None else "price unknown"
        md += [f"Negative: `{item['negative']}`  ", f"Model: {model} via {item['provider']}, {cost}. "
               + ("Can run (`run --yes` after the person's “yes”)." if item["can_run_now"]
                  else f"Not runnable now: {item['why_not_now']}."), ""]
        md += md_tail(errs, warns)
    out = e / "generated"
    out.mkdir(exist_ok=True)
    (out / "prompts.json").write_text(json.dumps({"id": plan["id"], "brand": plan["brand"], "items": items},
                                                 ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "prompts.md").write_text("\n".join(md), encoding="utf-8")
    for i in mine:
        put(e, i, ("gen",))  # engine/seconds into the fresh plan, under the lock
    n_code = len(gen_inserts(plan)) - len(mine)
    print(f"{out / 'prompts.json'}: {len(items)} insert(s) with engine model; prompts: {out / 'prompts.md'}"
          + (f"; {n_code} code scene(s): codescene.py manifest" if n_code else ""))
    bad = [x for x in items if x["errors"]]
    for x in bad:
        for m in x["errors"]:
            print("✗ " + m)
    return 1 if bad else 0


def cmd_validate(a):
    e = edit_dir(a.edit)
    plan, (_, _, _, _, brand) = plan_of(e)
    n = 0
    for i in gen_inserts(plan):
        errs, warns = check(i, brand)
        n += len(errs)
        for m in errs:
            print("✗ " + m)
        for m in warns:
            print("⚠ " + m)
    print(f"generation: {len(gen_inserts(plan))} insert(s), {n} error(s)")
    sys.exit(1 if n else 0)


# --- fal.ai: queue submit -> status_url -> response_url. The job goes into the plan right after submit ----------------
FAL_QUEUE = "https://queue.fal.run/"
FAL_HOSTS = ("fal.run", "fal.ai")


class JobGone(RuntimeError):
    """The fal job ended with an error or disappeared: nothing to resume, a new one will be paid again."""


def fal_url_ok(url):
    """The key goes only to https://*.fal.run / *.fal.ai: the URLs in the plan could have been edited by hand."""
    u = urllib.parse.urlparse(str(url or ""))
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in FAL_HOSTS)


def fal_http(url, key, payload=None, timeout=30):
    if offline():  # REELS_OFFLINE: checked before every request
        raise RuntimeError("REELS_OFFLINE=1: network access is off")
    if not fal_url_ok(url):
        raise ValueError("the job URL is not fal.ai; the key is not sent there")
    hdr = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=hdr, method="POST" if data is not None else "GET")
    try:
        with open_url(req, timeout, fal_url_ok) as r:
            return read_json_response(r)
    except urllib.error.HTTPError as ex:
        if ex.code in (404, 410):
            raise JobGone(f"fal: HTTP {ex.code}: the job is gone") from None
        raise


def fal_submit(endpoint, payload, key):
    job = fal_http(FAL_QUEUE + endpoint, key, payload)
    if not all(job.get(k) for k in ("request_id", "status_url", "response_url")):
        raise RuntimeError("fal: the submit answer has no request_id/status_url/response_url")
    return {k: job.get(k) for k in ("request_id", "status_url", "response_url", "cancel_url") if job.get(k)}


def fal_wait(job, key, timeout_s=900, every=5):
    t0 = time.time()
    while True:
        st = fal_http(job["status_url"], key)
        status = st.get("status")
        job["status"] = status or job.get("status")
        if status == "COMPLETED":
            res = fal_http(job["response_url"], key)
            url = ((res or {}).get("video") or {}).get("url")
            if not url:
                raise JobGone("fal: the result has no video.url")
            return url
        if status in ("FAILED", "ERROR", "CANCELLED"):
            raise JobGone(f"fal: {status}")
        if time.time() - t0 > timeout_s:
            raise TimeoutError("fal: no result in time; the job is saved, a repeat run resumes it without paying again")
        time.sleep(every)


def finish_job(e, i, key):
    """Wait for a paid job, download and prepare the clip. A network error or a timeout keeps the job in the plan."""
    g = i["gen"]
    job = g["job"]
    request_tag = hashlib.sha256(str(job["request_id"]).encode()).hexdigest()
    raw = e / "generated" / f"{safe_slug(i['id'], 'insert id')}-{request_tag}.mp4"
    try:
        if not raw.exists():
            url = fal_wait(job, key)
            download(url, raw)
        job["status"] = "COMPLETED"
        g["model"] = job.get("model")
        g["publish_note"] = AI_LABEL
        if safe_ingest(e, i, raw):
            job["status"] = "DONE"
            print(f"{i['id']}: {job.get('model')} -> ready (job {job['request_id']})")
    except JobGone as ex:
        g["job_failed"] = {**job, "error": err_text(ex, 120)}
        g.pop("job", None)
        i["status"], i["fallback"] = "pending", (f"the fal job gave no clip ({err_text(ex, 80)}); a new generation: "
                                                 f"run --yes (paid again); main footage for now")
        warn(f"{i['id']}: {i['fallback']}")
    except Exception as ex:
        i["status"], i["fallback"] = "pending", (f"fal job {job['request_id']} is saved, no result yet "
                                                 f"({err_text(ex, 120)}); a repeat run resumes it without paying again")
        warn(f"{i['id']}: {i['fallback']}")
    put(e, i)


def uncertain_message(i):
    return (f"{i['id']}: gen.job is submitting/unknown; do not submit again. Check the provider dashboard for "
            "the request first. Restore its request_id/status_url/response_url to resume, or clear gen.job "
            "by hand only after confirming no paid request was accepted.")


def reserve_submit(e, i):
    """Persist a reservation before spending money; re-read the insert under the plan lock."""
    owner = f"{os.getpid()}/{uuid.uuid4().hex}"
    with editing_json(e / "visual_plan.json") as plan:
        current = next(x for x in plan["inserts"] if x["id"] == i["id"])
        g = current.setdefault("gen", {})
        if g.get("job") or current.get("status") == "ready":
            print(uncertain_message(current) if (g.get("job") or {}).get("state") in ("submitting", "unknown")
                  else f"{i['id']}: another session already reserved or completed this insert; run again to resume")
            return None
        g["job"] = {"state": "submitting", "owner": owner, "at": time.time()}
        i["gen"]["job"] = dict(g["job"])
    return owner


def record_submit(e, i, owner, job):
    """Only the reservation owner can replace its job; preserve unrelated plan updates."""
    with editing_json(e / "visual_plan.json") as plan:
        current = next(x for x in plan["inserts"] if x["id"] == i["id"])
        g = current.setdefault("gen", {})
        if (g.get("job") or {}).get("owner") != owner:
            raise RuntimeError("submission reservation changed; check the provider before editing gen.job")
        g["job"] = job
        if i["gen"].get("seconds") is not None:
            g["seconds"] = i["gen"]["seconds"]
        current["status"] = "pending"
        i["gen"]["job"] = dict(job)


def rejected(ex):
    """fal answered with a client error (bad key, bad payload, no such endpoint): nothing was accepted or charged."""
    return isinstance(ex, JobGone) or (isinstance(ex, urllib.error.HTTPError) and 400 <= ex.code < 500)


def release_submit(e, i, owner):
    """Drop this session's reservation after a definite rejection, so a later run can try again."""
    with editing_json(e / "visual_plan.json") as plan:
        current = next(x for x in plan["inserts"] if x["id"] == i["id"])
        g = current.get("gen") or {}
        if (g.get("job") or {}).get("owner") == owner:
            g.pop("job")
    i["gen"].pop("job", None)


def cmd_run(a):
    """Paid generation by a model. Not yet tested live (no FAL_KEY at the time of writing): watch the first run.
    Reserve gen.job before submit; persist the returned request ID to resume without paying again. An uncertain
    submit requires a provider check before clearing gen.job. To deliberately regenerate a completed insert,
    delete its completed gen.job and set status back to pending; raw files are bound to the request ID."""
    e = edit_dir(a.edit)
    plan, (s, prov, doc, bdir, brand) = plan_of(e)
    eff, why = effective(s)
    todo = [i for i in gen_inserts(plan) if (i.get("gen") or {}).get("engine") == "model" and i["status"] != "ready"]
    if not todo:
        print("nothing to generate with a model")
        return

    def hold(items, reason):
        for i in items:
            i["status"] = "pending"
            i["fallback"] = f"model generation not started ({reason}); prompt: generated/prompts.md; main footage for now"
            put(e, i, ("status", "fallback"))

    blocked = [i for i in todo if ((i.get("gen") or {}).get("job") or {}).get("state") in ("submitting", "unknown")]
    for i in blocked:
        print(uncertain_message(i))
    todo = [i for i in todo if i not in blocked]
    # 1) jobs already paid for: resume them (no "yes" on the price needed: no new money is spent)
    resume = [i for i in todo if ((i.get("gen") or {}).get("job") or {}).get("request_id")
              and i["gen"]["job"].get("status") != "DONE"]
    for i in resume:
        job = i["gen"]["job"]
        if job.get("provider", "fal") != "fal":
            warn(f"{i['id']}: unsupported saved job provider; refusing before reading any key")
            continue
        key = api_key("FAL_KEY")
        if offline() or not key:
            i["status"], i["fallback"] = "pending", (f"paid job {job['request_id']} is waiting: "
                                                     f"{'REELS_OFFLINE=1' if offline() else 'no FAL_KEY key'}; repeat run later")
            warn(f"{i['id']}: {i['fallback']}")
            put(e, i)
            continue
        print(f"{i['id']}: resuming job {job['request_id']} ({job.get('model')}) without paying again")
        finish_job(e, i, key)
    fresh = [i for i in todo if not (i.get("gen") or {}).get("job")]
    if not fresh:
        return

    # 2) new jobs: is it on, is the provider/model pair supported, is the prompt complete: before the price and the network
    if not eff.get("generate_now"):
        hold(fresh, why.get("generate_now"))
        print(f"model generation not started: {why.get('generate_now')}. Prompts: {e / 'generated' / 'prompts.md'}. "
              f"The inserts are pending; the edit goes on without them.")
        return
    prov_name, model, spec, unsupported = model_spec(s)
    if unsupported:
        hold(fresh, unsupported)
        print(f"model generation not started: {unsupported}. The inserts are pending; the edit goes on without them.")
        return
    ok = []
    for i in fresh:
        g = i.setdefault("gen", {})
        errs, _ = check(i, brand)
        sec = int(num(g.get("seconds"), 6) or 6)
        if not errs and sec not in spec["durations"]:
            errs = [f"{i['id']}: {model} supports {spec['durations']} s, but seconds={sec} (addon.py gen manifest picks one)"]
        if errs:
            hold([i], "; ".join(errs))
            warn(f"{i['id']}: not running: {'; '.join(errs)}")
            continue
        g["seconds"] = sec
        ok.append(i)
    if not ok:
        return
    total = sum(spec["usd_s"] * i["gen"]["seconds"] for i in ok)
    if not a.yes:
        print(f"ready to run {len(ok)} clip(s) with {model}, ≈ ${total:.2f}. This needs the person's explicit “yes”; "
              f"then repeat with --yes")
        return
    key = api_key(GEN_KEYS[prov_name])
    for i in ok:
        g = i["gen"]
        if offline() or not key:
            hold([i], "REELS_OFFLINE=1" if offline() else f"no {GEN_KEYS[prov_name]} key")
            continue
        payload = {"prompt": build_prompt(g, g["seconds"], brand), "aspect_ratio": "9:16",
                   "duration": spec["duration"](g["seconds"]), "generate_audio": False}
        if spec.get("neg"):
            payload["negative_prompt"] = negative(brand)
        if g.get("seed") is not None:
            payload["seed"] = g["seed"]
        endpoint = spec["endpoint"]
        if g.get("image_url"):
            payload[spec["image_key"]] = g["image_url"]
            endpoint = spec["i2v"]
        owner = reserve_submit(e, i)
        if owner is None:
            continue
        try:
            job = fal_submit(endpoint, payload, key)
        except Exception as ex:
            if rejected(ex):
                release_submit(e, i, owner)
                hold([i], f"{prov_name} rejected the request ({err_text(ex, 120)}); nothing was charged")
                warn(f"{i['id']}: {i['fallback']}")
                continue
            unknown = {**g["job"], "state": "unknown", "provider": prov_name, "error": err_text(ex, 120)}
            record_submit(e, i, owner, unknown)
            i["status"], i["fallback"] = "pending", uncertain_message(i)
            warn(f"{i['id']}: {i['fallback']}")
            put(e, i, ("status", "fallback"))
            continue
        g["job"] = {"provider": prov_name, "model": model, "endpoint": endpoint, **job, "status": "IN_QUEUE", "owner": owner,
                    "submitted": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "est_cost_usd": round(spec["usd_s"] * g["seconds"], 2)}
        i["status"] = "pending"
        record_submit(e, i, owner, g["job"])
        print(f"{i['id']}: job {job['request_id']} sent ({model}, ≈ ${g['job']['est_cost_usd']})")
        finish_job(e, i, key)


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="addon.py gen", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("manifest"); p.add_argument("edit"); p.set_defaults(fn=lambda a: sys.exit(cmd_manifest(a)))
    p = sub.add_parser("validate"); p.add_argument("edit"); p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("run"); p.add_argument("edit"); p.add_argument("--yes", action="store_true"); p.set_defaults(fn=cmd_run)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
