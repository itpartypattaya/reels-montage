# -*- coding: utf-8 -*-
"""The text clock of a no-speech reel (reel.json -> voice: none): edit/<id>/script.json, its timing and its checks.
Part of visual_plan.py (`visual_plan.py script edit/<id> [--bpm N]`); references/no-speaker.md is the full contract.

    {"blocks": [{"id": "hook", "role": "hook", "lines": ["The ad says:", "no income ceiling"],
                 "type": "hook", "variant": "slam", "mode": "full", "tone": "calm", "label": null, "hold": 0.0,
                 "what": "the hook over the office", "why": "the job ad's promise"}, ...]}

The lines are the brief's text word for word. A block lasts as long as its scene needs to be read: the scene kit's
own timing (vp_scenes.scene_timeline, text_full_on) and the plan's reading floor (vp_core.read_need), counted from
the frame when the whole text is on screen until it starts to leave, plus the block's "hold" (a punchline held for
the reaction). With --bpm each block runs on to the next beat of the music's grid (beat k at k * 60 / bpm s from the
video's start): reading wins over the grid, a block is never shortened for a beat. The timing is written into
script.json -> timing with the script's fingerprint; cut.py, music.py and validate refuse a script edited after it.
"""
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import edit_dir, editing_json, load_config, load_json

ROLES = ("hook", "setup", "label", "translation", "point", "punchline", "cta")
ROLE_TYPE = {"hook": ("hook", "slam"), "label": ("hook", "slam"), "setup": ("quote", None),
             "translation": ("quote", None), "point": ("slogan", None), "punchline": ("slogan", None),
             "cta": ("cta", "tap")}
TEXT_TYPES = ("hook", "quote", "slogan", "contrast", "cta")  # a block is text on screen; a list or a stat is its own scene
ENDING_ROLES = ("punchline", "cta")  # the last block of a no-speech reel may hold the last 2 s (references/no-speaker.md)
BPM_RANGE = (70, 140)
SCRIPT_FPS = 30
MAX_BLOCK_S = 20.0


def script_path(e):
    return Path(e) / "script.json"


def load_script(e):
    """edit/<id>/script.json, checked. -> the document; an error stops with what to fix."""
    f = script_path(e)
    doc = load_json(f, None)
    if not isinstance(doc, dict):
        sys.exit(f"no {f}: a no-speech reel is timed by its text: write the brief's text blocks into script.json "
                 f"(references/no-speaker.md)")
    blocks = doc.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        sys.exit(f"{f}: no blocks (\"blocks\": [{{\"id\", \"role\", \"lines\"}}, ...])")
    seen = set()
    for k, b in enumerate(blocks):
        where = f"{f.name} block {k + 1}"
        if not isinstance(b, dict):
            sys.exit(f"{where}: a block is an object")
        bid = b.get("id")
        if not isinstance(bid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", bid):
            sys.exit(f"{where}: id {bid!r}: lowercase letters, digits, - and _ (it names the block for the scenes, "
                     f"the picture and the music)")
        if bid in seen:
            sys.exit(f"{where}: the id {bid!r} is used twice: every block has its own id")
        seen.add(bid)
        if b.get("role") not in ROLES:
            sys.exit(f"{where} ({bid}): role {b.get('role')!r} (one of {', '.join(ROLES)})")
        lines = b.get("lines")
        if not isinstance(lines, list) or not lines or not all(isinstance(x, str) and x.strip() for x in lines):
            sys.exit(f"{where} ({bid}): no text: lines is a list of the brief's lines, word for word")
        typ, _ = block_type(b)
        if typ not in TEXT_TYPES:
            sys.exit(f"{where} ({bid}): type {typ!r}: a script block is a text scene ({', '.join(TEXT_TYPES)}); "
                     f"a list, a stat or a chat is a scene of its own (visual_plan.py add)")
        h = b.get("hold", 0.0)
        if not (isinstance(h, (int, float)) and not isinstance(h, bool) and 0 <= h <= 5):
            sys.exit(f"{where} ({bid}): hold {h!r}: seconds 0-5 the block stays after its reading")
    return doc


def block_type(b):
    """A block's scene type and variant: its own, else its role's."""
    typ, var = ROLE_TYPE.get(b.get("role"), ("slogan", None))
    typ = b.get("type") or typ
    var = b.get("variant") if b.get("variant") is not None else (var if typ == ROLE_TYPE.get(b.get("role"), (None,))[0]
                                                                  else None)
    if typ == "hook" and not var:
        var = "slam"
    if typ == "cta" and not var:
        var = "tap"
    return typ, var


def script_id(doc):
    """The fingerprint of what sets the clock: each block's id, role, text and scene look."""
    keys = ("id", "role", "lines", "type", "variant", "mode", "tone", "label", "hold", "transition")
    blob = json.dumps([{k: b.get(k) for k in keys} for b in doc["blocks"]], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def default_mode(typ):
    """The clips stay on screen under the text: overlay where the type has it, else split (the picture in the lower
    window); full (the field covers the frame) only when a block asks for it. 2.4: scenes back to back in full hid
    every frame of the footage."""
    from vp_scenes import SCENE_TYPES
    modes = SCENE_TYPES[typ]["modes"]
    return next((m for m in ("overlay", "split") if m in modes), "full")


def scene_of(b, t, n=1):
    """The designed scene a block becomes (visual_plan.py init --no-speech), at its timing t {start, dur}: c<n>."""
    typ, var = block_type(b)
    tone = b.get("tone")
    tr = b.get("transition") or "cut"  # the texts hand over at the join, as in "scenes only" (T6)
    return {"id": f"c{n:02d}", "kind": "scene", "type": typ, "mode": b.get("mode") or default_mode(typ), "variant": var,
            "segment": None,
            "start": t["start"], "dur": t["dur"], "at": f"block:{b['id']}", "tone": tone,
            "text": {"lines": list(b["lines"]), "accent": b.get("accent"), "label": b.get("label")},
            "items": None, "value": None, "media": None, "interaction": None, "box": b.get("box"), "side": None,
            "source": {"kind": "brief", "ref": f"script.json#{b['id']}"},
            "what": b.get("what") or f"the script's {b['role']} block on screen",
            "why": b.get("why") or f"the brief's {b['role']} text, word for word",
            "transition_in": tr, "transition_out": tr, "sound": b.get("sound"), "hide_subtitles": True,
            "status": "planned", "fallback": "main footage", "script": b["id"], "role": b["role"]}


def read_frames(b, s, doc, fps=SCRIPT_FPS):
    """The fewest frames a block's scene needs to pass the reading floor, as vp_scenes.check_scenes counts it."""
    from vp_core import norm_words, read_need
    from vp_scenes import scene_timeline, scene_tone, text_full_on
    conf = doc.get("scenes") or {}
    R = conf.get("reading") or {}
    tones = {k: v for k, v in (doc.get("scene_tones") or {}).items() if not k.startswith("_")}
    sc = scene_of(b, {"start": 0.0, "dur": 1.0})
    T = tones.get(scene_tone(sc, s)) or tones.get("calm") or {"in": 14, "out": 9, "hold": 0.4}
    lines = sc["text"]["lines"]
    label = str(sc["text"].get("label") or "")
    n_words = len(norm_words(" ".join(([label] if label.strip() else []) + lines)))
    need = read_need(n_words, R)
    for n in range(1, int(MAX_BLOCK_S * fps) + 1):
        x = {**sc, "dur": n / fps}
        tl = scene_timeline(x, T, sc["mode"], fps, [], False)
        rest = (tl["settle_to"] - text_full_on(x, sc["type"], lines, tl, fps, [])) / fps
        if rest + 1e-6 >= need:
            return n, need
    sys.exit(f"script.json block {b['id']}: {n_words} words need more than {MAX_BLOCK_S:g} s on screen: split it")


def time_script(e, doc, bpm=None, fps=SCRIPT_FPS):
    """-> {script_id, fps, bpm, duration, blocks: [{id, role, start, dur, read}]}: the blocks back to back, whole
    frames, each its reading (+ hold), on the beat grid when bpm is given (extended to the next beat, never shorter)."""
    s, _, cfg, _, _ = load_config(e)
    if bpm is not None and not BPM_RANGE[0] <= bpm <= BPM_RANGE[1]:
        sys.exit(f"--bpm {bpm:g}: the music's tempo is {BPM_RANGE[0]}-{BPM_RANGE[1]}")
    beat = 60.0 / bpm if bpm else None
    out, cur = [], 0
    for b in doc["blocks"]:
        n, need = read_frames(b, s, cfg, fps)
        hold = int(round(float(b.get("hold", 0.0)) * fps))
        end = cur + n + hold
        if beat:
            k = math.ceil(end / fps / beat - 1e-9)
            while round(k * beat * fps) < end:
                k += 1
            end = round(k * beat * fps)
        # start + dur is exactly the next start at 3 decimals (no overlap of a thousandth between two scenes)
        out.append({"id": b["id"], "role": b["role"], "start": round(cur / fps, 3),
                    "dur": round(round(end / fps, 3) - round(cur / fps, 3), 3),
                    "read": round(n / fps, 3), "need_s": need})
        cur = end
    return {"script_id": script_id(doc), "fps": fps, "bpm": bpm, "duration": round(cur / fps, 3), "blocks": out}


def clock_id(tm):
    """The fingerprint of a timing: where every block starts and how long it lasts (cut.py keeps it in captions.json:
    the block: joins of the picture were cut on it)."""
    blob = json.dumps([[b["id"], b["start"], b["dur"]] for b in tm["blocks"]])
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def timing_of(e, stop=True):
    """script.json's timing, checked against its text. -> (doc, timing); with stop, a missing or stale timing exits."""
    doc = load_script(e)
    tm = doc.get("timing")
    why = None
    if not isinstance(tm, dict) or not tm.get("blocks"):
        why = "its text blocks are not timed yet"
    elif tm.get("script_id") != script_id(doc):
        why = "its text changed after it was timed"
    if why and stop:
        sys.exit(f"{script_path(e)}: {why}: run python scripts/visual_plan.py script edit/{Path(e).name}"
                 + (f" --bpm {tm['bpm']:g}" if isinstance(tm, dict) and tm.get("bpm") else ""))
    return doc, (None if why else tm)


def cmd_script(a):
    """visual_plan.py script edit/<id> [--bpm N]: time the text blocks, write script.json -> timing, print them."""
    e = edit_dir(a.edit)
    doc = load_script(e)
    tm = time_script(e, doc, a.bpm)
    with editing_json(script_path(e), {}) as d:
        d["timing"] = tm
    print(f"{script_path(e)}: {len(tm['blocks'])} block(s), {tm['duration']:.3f} s"
          + (f", on the {tm['bpm']:g} bpm grid" if tm["bpm"] else ""))
    for b in tm["blocks"]:
        print(f"  {b['id']:<14} {b['role']:<12} {b['start']:>7.3f} +{b['dur']:.3f} s  (reading {b['read']:.3f} s, "
              f"floor {b['need_s']:.2f} s settled)")
    print("Next: cut.py edit/<id> (picture blocks may name block:<id>), then visual_plan.py init edit/<id> --no-speech")


def script_issues(e, plan):
    """validate, a no-speech plan: the scenes are the script's blocks, word for word, each once, at its timing.
    -> (errors, warnings)."""
    errs, warns = [], []
    f = script_path(e)
    doc = load_json(f, None)
    if not isinstance(doc, dict) or not isinstance(doc.get("blocks"), list):
        return [f"no-speech reel: no {f.name}: the text is the clock (references/no-speaker.md)"], warns
    tm = doc.get("timing") if isinstance(doc.get("timing"), dict) else None
    if not tm or tm.get("script_id") != script_id(doc):
        errs.append(f"{f.name}: its text changed after it was timed (or it is not timed): python scripts/visual_plan.py "
                    f"script edit/{e.name}" + (f" --bpm {tm['bpm']:g}" if tm and tm.get("bpm") else "")
                    + ", then cut.py and init --no-speech --force")
        tm = None
    times = {b["id"]: b for b in (tm or {}).get("blocks") or []}
    # only a scene that goes into the render shows its block: a skipped or pending one is not exported (Codex review)
    scenes = [i for i in plan.get("inserts", []) if i.get("kind") == "scene" and i.get("type") != "cover"
              and i.get("status") not in ("skipped", "pending")]
    by = {}
    for sc in scenes:
        if sc.get("script"):
            by.setdefault(sc["script"], []).append(sc)
    for b in doc["blocks"]:
        bid = b.get("id")
        got = by.get(bid) or []
        if not got:
            errs.append(f"{f.name} block {bid}: missing from the plan: every block of the brief is on screen once")
            continue
        if len(got) > 1:
            errs.append(f"{f.name} block {bid}: shown twice ({', '.join(x['id'] for x in got)}): once is the rule")
        for sc in got:
            lines = [str(x) for x in ((sc.get("text") or {}).get("lines") or [])]
            if [x.strip() for x in lines] != [str(x).strip() for x in b.get("lines") or []]:
                errs.append(f"{sc['id']}: not the script word for word (block {bid}): «{' / '.join(lines)[:60]}» "
                            f"instead of «{' / '.join(b.get('lines') or [])[:60]}»: the brief's text is not edited")
            t = times.get(bid)
            if t and (abs(sc["start"] - t["start"]) > 0.5 / SCRIPT_FPS or sc["dur"] + 0.5 / SCRIPT_FPS < t["dur"]):
                errs.append(f"{sc['id']}: at {sc['start']:.3f} +{sc['dur']:.3f} s, but block {bid} is timed "
                            f"{t['start']:.3f} +{t['dur']:.3f} s: the picture and the music follow the timing "
                            f"(init --no-speech --force, or time the script again)")
    known = {b.get("id") for b in doc["blocks"]}
    for bid, got in by.items():
        if bid not in known:
            errs.append(f"{', '.join(x['id'] for x in got)}: block {bid} is not in {f.name}")
    cap = load_json(Path(e) / "captions.json") or {}
    if tm and cap.get("clock_id") and cap["clock_id"] != clock_id(tm):
        errs.append("the rough cut was cut for another timing of the text (blocks moved, the same length or not): "
                    "cut.py again, then init --no-speech --force")
    if tm and abs(float(plan.get("duration") or 0) - float(tm["duration"])) > 0.5 / SCRIPT_FPS:
        errs.append(f"the plan is {plan.get('duration')} s, the timed text {tm['duration']} s: cut.py again "
                    f"(the rough cut follows the text)")
    return errs, warns


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def beats_file(e):
    """edit/<id>/beats.json (music.py --edit writes it next to music.wav) -> (path, document or None)."""
    f = Path(e) / "beats.json"
    doc = load_json(f, None) if f.is_file() else None
    return f, (doc if isinstance(doc, dict) else None)


def beats_issues(e, plan, tail=0.0):
    """validate: beats.json (music made in code) belongs to the WAV it names, has the video's length with its end card,
    and its markers serve blocks of the script at their times. -> (errors, warnings, the plan's music summary or None)."""
    f, b = beats_file(e)
    if b is None:
        return [], [], None
    errs, warns = [], []
    wav = Path(e) / str(b.get("wav") or "music.wav")
    if not wav.is_file():
        errs.append(f"{f.name}: no {wav.name} next to it: music.py --edit edit/{Path(e).name} makes both")
    elif sha256_of(wav) != b.get("wav_sha256"):
        errs.append(f"{f.name} belongs to another {wav.name} (its hash differs): the beats would not be this music's; "
                    f"music.py --edit edit/{Path(e).name} again")
    want = float(plan.get("duration") or 0) + float(tail or 0)
    have = float(b.get("samples") or 0) / float(b.get("rate") or 48000)
    if want and abs(have - want) > 0.5 / SCRIPT_FPS:
        errs.append(f"{wav.name} is {have:.3f} s, the video {want:.3f} s (with its end card): the music is made for the "
                    f"finished length: music.py --edit edit/{Path(e).name}")
    tm = timing_of(e, stop=False)[1] if (Path(e) / "script.json").is_file() else None
    starts = {x["id"]: x["start"] for x in (tm or {}).get("blocks") or []}
    for m in b.get("markers") or []:
        bid = m.get("block")
        if bid and bid not in starts:
            errs.append(f"{f.name}: marker {m.get('kind')} serves block {bid!r}, not in script.json")
        elif bid and abs(float(m.get("requested", 0)) - starts[bid]) > 0.5 / SCRIPT_FPS:
            errs.append(f"{f.name}: marker {m.get('kind')} was set for block {bid} at {m.get('requested')} s, the block "
                        f"now starts at {starts[bid]} s: music.py --edit edit/{Path(e).name} again")
    music = {"beats": [x["t"] for x in b.get("beats") or []],
             "markers": {m["kind"]: m["at"] for m in b.get("markers") or [] if m.get("kind") != "pause"},
             "wav_sha256": b.get("wav_sha256")}
    return errs, warns, music
