# -*- coding: utf-8 -*-
"""The brand mascot: a character drawn in code, its mouth animated to your recorded narration (references/mascot.md).

    python scripts/mascot.py mouth edit/<id> [--audio PATH] [--fps 30]   # the mouth's opening per frame -> mouth.json
    python scripts/mascot.py plan  edit/<id> --pose "word:look#1=point_left" [--pose "12.4=palm" ...] [--clear]
        [--from S] [--to S] [--at X,Y] [--scale K] [--auto-place] [--facing 1|-1] [--speaks A-B,C-D|all|none] [--off]
    python scripts/mascot.py check edit/<id>                              # the brand's mascot, the plan, mouth.json
    python scripts/mascot.py check --brand <slug> [--remotion DIR]        # the brand's mascot only

mouth: the track the viewer hears, on the edit's timeline: edit/<id>/voice.wav (scenes over a recorded narration),
else the rough cut's audio (edit/<id>/final.mp4, the file stage copies to public/<id>/video.mp4); --audio names
another file on the same timeline. Per frame of the kit's grid (frame f takes the samples from round(f*sr/fps) to
round((f+1)*sr/fps), no drift), the RMS; speech frames are the ones 10 dB above the noise floor (measured between
the words of captions.json when it has words, else on the quietest tenth; at least -50 dBFS) and inside a word when
there are words; the level is normalized by the 98th percentile of the speech
frames (one click does not squash the rest), smoothed [1,2,1]/4, opened from 0.08 to fully at 0.63, and every
frame that is not speech is closed. mouth.json keeps the frame rate, the frame count (round half up, as the kit
rounds) and stamps of the track and the words: once either changes, stage refuses the old mouth.

plan: the plan's "mascot" field (mascot_plan.py has its format). --pose AT=POSE adds or replaces a pose change at AT
(a second, a span s03 or a word word:look#1, which then follows the word through a re-cut); poses: neutral, talk,
point_left, point_right, point_up, palm, think, surprise, celebrate, shrug, wink. --at X,Y places the anchor (the
point between the eyes), --auto-place drops the placement (the lower left, above the subtitle band). --speaks: where
the mouth moves (half-open spans, seconds); all (the default) is the whole narration, none keeps it closed.
"""
import argparse, json, math, re, subprocess, sys
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import edit_dir, find_brand, load_defaults, load_json, run, save_json, utf8_stdio, warn  # noqa: E402
import mascot_plan as vm  # noqa: E402

THRESHOLD, FULL = 0.08, 0.63
FLOOR_PCT, PEAK_PCT = 0.10, 0.98
GATE_DB, MIN_DB = 10.0, -50.0
WORD_PAD = 0.1  # s around a word: recognizers end words early
MIN_PAUSE_FRAMES = 10  # frames between the words needed to measure the noise floor on them


def kit_fps():
    return int(((load_defaults() or {}).get("scenes") or {}).get("fps", 30))


def jround(x):
    return int(math.floor(x + 0.5))


def read_mono(src):
    """-> (samples as int16 array, sample rate): the first audio stream, mixed to mono, its own rate, aligned to the
    container's start like every analysis track (first_pts=0)."""
    r = run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate", "-of", "json",
             str(src)], check=False)
    try:
        sr = int(json.loads(r.stdout or "{}")["streams"][0]["sample_rate"])
    except (KeyError, IndexError, ValueError, TypeError):
        sys.exit(f"{src}: no audio track")
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-map", "0:a:0", "-ac", "1",
                        "-af", "aresample=async=1:first_pts=0", "-ar", str(sr), "-f", "s16le", "-acodec", "pcm_s16le",
                        "-"], capture_output=True)
    if p.returncode != 0:
        sys.exit(f"{src}: ffmpeg could not read the audio: {p.stderr.decode('utf-8', 'replace')[-400:]}")
    a = array("h")
    a.frombytes(p.stdout[: len(p.stdout) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    return a, sr


def pct(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, jround(q * (len(s) - 1))))] if s else 0.0


def envelope(a, sr, fps, words=None):
    """-> (open per frame, info). words: [(start, end)] on the same timeline (captions.json), or None."""
    n = jround(len(a) * fps / float(sr))
    rms = []
    for f in range(n):
        i0, i1 = jround(f * sr / float(fps)), min(len(a), jround((f + 1) * sr / float(fps)))
        seg = a[i0:i1]
        rms.append(math.sqrt(sum(x * x for x in seg) / len(seg)) / 32768.0 if len(seg) else 0.0)
    db = [20 * math.log10(max(v, 1e-9)) for v in rms]
    inw = None
    if words:
        inw = [False] * n
        for s0, s1 in words:
            for f in range(max(0, int((s0 - WORD_PAD) * fps)), min(n, int(math.ceil((s1 + WORD_PAD) * fps)))):
                inw[f] = True
    # the noise floor: with words, the frames between them (a recording with no pauses has none: only the absolute
    # floor then, or steady speech would gate itself out); without words, the quietest tenth of the track
    out_db = [d for d, w in zip(db, inw) if not w] if inw else db
    floor = pct(out_db, 0.5 if inw else FLOOR_PCT) if len(out_db) >= MIN_PAUSE_FRAMES else None
    gate = max(MIN_DB, floor + GATE_DB) if floor is not None else MIN_DB
    speech = [d >= gate for d in db]
    if inw:
        speech = [a_ and b_ for a_, b_ in zip(speech, inw)]
    sp = [rms[f] for f in range(n) if speech[f]]
    peak = pct(sp, PEAK_PCT) if sp else 0.0
    amp = [min(1.0, v / peak) if peak > 0 else 0.0 for v in rms]
    out = []
    for f in range(n):
        sm = ((amp[f - 1] if f > 0 else 0.0) + 2 * amp[f] + (amp[f + 1] if f + 1 < n else 0.0)) / 4
        o = min(1.0, max(0.0, (sm - THRESHOLD) / (FULL - THRESHOLD))) if speech[f] else 0.0
        out.append(round(o, 3))
    return out, {"floor_db": None if floor is None else round(floor, 1), "gate_db": round(gate, 1), "peak": round(peak, 5),
                 "speech_frames": len(sp), "words": bool(words)}


def cmd_mouth(a):
    e = edit_dir(a.edit)
    fps = a.fps or kit_fps()
    src = Path(a.audio).resolve() if a.audio else vm.voice_track(e)
    if not src or not src.is_file():
        sys.exit(f"no narration track: {e / 'voice.wav'} or {e / 'final.mp4'} (or give --audio)")
    words = vm.speech_words(e)
    if not a.audio and src.name == "voice.wav" and (e / "final.mp4").is_file():
        warn("both voice.wav and final.mp4 are here: the mouth follows voice.wav (the recorded narration); if the "
             "render plays the rough cut's own sound, run again with --audio " + str(e / "final.mp4"))
    samples, sr = read_mono(src)
    if not len(samples):
        sys.exit(f"{src}: the audio track is empty")
    opens, info = envelope(samples, sr, fps, words or None)
    try:
        rel = src.relative_to(e.resolve()).as_posix()
    except ValueError:
        rel = str(src)
    save_json(e / "mouth.json", {"version": 1, "fps": fps, "frames": len(opens), "sample_rate": sr, "source": rel,
                                 "explicit": bool(a.audio), "stamp": vm.file_stamp(src),
                                 "words_stamp": vm.words_stamp(words), **info, "open": opens})
    talk = sum(1 for o in opens if o > vm.TALK_MIN)
    print(f"{e / 'mouth.json'}: {len(opens)} frames at {fps} fps from {src.name} ({sr} Hz); the mouth moves on {talk} "
          f"({talk / max(1, len(opens)) * 100:.0f} %)" + ("; speech inside the words of captions.json" if words else ""))
    if not info["speech_frames"]:
        warn("no speech found in the track: the mouth stays closed (a quiet recording or the wrong file?)")


def parse_speaks(v):
    if v in ("all", None):
        return None
    if v == "none":
        return []
    out = []
    for part in v.split(","):
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*", part)
        if not m:
            sys.exit(f"--speaks: expected A-B[,C-D], got {part!r}")
        out.append([float(m.group(1)), float(m.group(2))])
    return out


def cmd_plan(a):
    from vp_core import editing_plan, ensure_plan, resolve_at
    e = edit_dir(a.edit)
    ensure_plan(e)
    cap = load_json(e / "captions.json", {}) or {}
    adds = []
    for p in a.pose or []:
        if "=" not in p:
            sys.exit(f"--pose: expected AT=POSE, got {p!r}")
        at, pose = (x.strip() for x in p.rsplit("=", 1))
        if pose not in vm.POSES:
            sys.exit(f"--pose {p}: unknown pose {pose!r} (the dictionary: {', '.join(vm.POSES)})")
        adds.append((at, pose))
    with editing_plan(e) as plan:
        if a.off:
            plan.pop("mascot", None)
            plan["keep_clear"] = [k for k in plan.get("keep_clear", []) if not k.get("mascot")]  # its box frees up
            print("mascot: off (taken out of the plan)")
            return
        m = plan.setdefault("mascot", {"x": None, "y": None, "scale": None, "facing": 1, "from": 0.0, "to": None,
                                       "track": [], "speaks": None})
        if a.clear:
            m["track"] = []
        for at, pose in adds:
            t = round(resolve_at(at, plan, cap), 3)
            m["track"] = [x for x in m["track"] if str(x.get("at")) != at] + [{"at": at, "t": t, "pose": pose}]
        m["track"].sort(key=lambda x: float(x.get("t") or 0))
        for k in ("from", "to"):
            if getattr(a, k.replace("from", "start")) is not None:
                m[k] = float(getattr(a, k.replace("from", "start")))
        if a.at:
            try:
                m["x"], m["y"] = (int(round(float(v))) for v in a.at.split(","))
            except ValueError:
                sys.exit(f"--at: expected X,Y, got {a.at!r}")
        if a.scale is not None:
            m["scale"] = a.scale
        if a.auto_place:
            m["x"] = m["y"] = m["scale"] = None
        if a.facing is not None:
            m["facing"] = a.facing
        if a.speaks is not None:
            m["speaks"] = parse_speaks(a.speaks)
    print(f"mascot: {len(m['track'])} pose change(s)"
          + (": " + ", ".join(f"{x['pose']} at {x['t']} s ({x['at']})" for x in m["track"]) if m["track"] else "")
          + ("; placed by hand" if m.get("x") is not None else "; placed in the lower left above the subtitles")
          + f"; speaks: {'the whole narration' if m.get('speaks') is None else m['speaks'] or 'never'}")
    print(f"next: visual_plan.py validate edit/{e.name}")


def component_check(rem, comp, cached):
    """The drawn mascot's module in the Remotion project: the file, its box and poses as brand.json caches them."""
    from brand import read_component
    errs = []
    p = Path(rem) / comp
    if not p.is_file():
        return [f"the mascot's component {p} is missing"]
    got, why = read_component(p)
    if not got:
        return [why]
    for k in ("box", "anchor", "poses"):
        if cached.get(k) != got[k]:
            errs.append(f"brand.json mascot.{k} {cached.get(k)} differs from the component's {got[k]}: brand.py stage "
                        f"refreshes it")
    bad = [x for x in got["poses"] if x not in vm.POSES]
    if bad:
        errs.append(f"the component has poses outside the dictionary: {', '.join(bad)}")
    reg = Path(rem) / "src" / "gen" / "mascots.ts"
    if not reg.is_file() or f'"{cached.get("_slug")}"' not in reg.read_text(encoding="utf-8"):
        errs.append(f"not registered in {reg}: brand.py stage <slug> --remotion {rem}")
    return errs


def cmd_check(a):
    errs, warns = [], []
    if a.edit:
        import visual_plan as vp
        e = edit_dir(a.edit)
        plan = vp.load_plan(e)
        s, _prov, doc, bdir, brand = vp.current_settings(e, plan)
        er, wr = vm.issues(e, plan, s, doc, brand, bdir, kit_fps())
        errs += er
        warns += wr
        if not plan.get("mascot"):
            print("the plan has no mascot (mascot.py plan adds it)")
        slug = plan.get("brand")
    else:
        slug = a.brand
        bdir, brand = find_brand(slug)
    if not brand:
        sys.exit(f"no brand {slug}")
    geo, why = vm.geometry(brand, bdir)
    if not geo:
        errs.append(why)
    else:
        print(f"brand {slug}: a {geo['kind']} mascot, box {geo['box'][0]:g}x{geo['box'][1]:g}, anchor "
              f"{geo['anchor'][0]:g},{geo['anchor'][1]:g}, poses {', '.join(geo['poses'])}"
              + (", symmetric" if geo["symmetric"] else ""))
        missing = [p for p in vm.POSES if p not in geo["poses"]]
        if "neutral" not in geo["poses"]:
            errs.append("the mascot has no neutral pose (every track starts from it)")
        if missing:
            print("  stand-ins: " + ", ".join(f"{p} -> {'/'.join(map(str, vm.substitute(p, geo)))}" for p in missing))
        if geo["kind"] == "drawn":
            from board import remotion_dir
            try:
                rem = remotion_dir(a.remotion)
            except SystemExit:
                rem = None
            if rem:
                errs += component_check(rem, brand["mascot"].get("component"), {**brand["mascot"], "_slug": slug})
    for m in errs:
        print("error: " + m)
    for m in warns:
        print("warning: " + m)
    print(f"{len(errs)} error(s), {len(warns)} warning(s)")
    sys.exit(1 if errs else 0)


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("mouth", help="the mouth's opening per frame from the narration -> edit/<id>/mouth.json")
    p.add_argument("edit"); p.add_argument("--audio", help="another track on the edit's timeline")
    p.add_argument("--fps", type=int, help="the kit's frame rate (default: reel-defaults.json scenes.fps, 30)")
    p.set_defaults(fn=cmd_mouth)
    p = sub.add_parser("plan", help="the plan's mascot: poses on words, placement, where it speaks")
    p.add_argument("edit"); p.add_argument("--pose", action="append", metavar="AT=POSE")
    p.add_argument("--clear", action="store_true", help="drop the pose changes first")
    p.add_argument("--from", dest="start", type=float); p.add_argument("--to", type=float)
    p.add_argument("--at", metavar="X,Y", help="the anchor (the point between the eyes) on screen")
    p.add_argument("--scale", type=float); p.add_argument("--auto-place", action="store_true")
    p.add_argument("--facing", type=int, choices=[1, -1])
    p.add_argument("--speaks", help="A-B[,C-D] seconds, all (default) or none")
    p.add_argument("--off", action="store_true", help="take the mascot out of the plan")
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("check", help="the brand's mascot, the plan's mascot and mouth.json")
    p.add_argument("edit", nargs="?"); p.add_argument("--brand"); p.add_argument("--remotion")
    p.set_defaults(fn=cmd_check)
    a = ap.parse_args()
    if a.cmd == "check" and not (a.edit or a.brand):
        ap.error("check: give edit/<id> or --brand <slug>")
    a.fn(a)


if __name__ == "__main__":
    main()
