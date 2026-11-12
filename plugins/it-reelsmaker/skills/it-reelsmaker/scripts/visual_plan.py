# -*- coding: utf-8 -*-
"""The visual plan of a video (step 7a): editing decisions kept apart from the render.

The plan is edit/<id>/visual_plan.json (+ visual_plan.md for the person). Spans are built from the phrases in
captions.json (the timeline of the finished rough cut); each has a timecode, the line, the main footage and hints.
Inserts (B-roll, memes) are a separate list: an insert may cover the join of two spans (that is how B-roll hides a cut).
The agent makes the decisions (what to show and why); the script computes the budget from the intensity, checks the
rules and hands the inserts over to Remotion.

    python scripts/visual_plan.py init edit/4821 [--set use_memes=true intensity=minimal] [--force]
    python scripts/visual_plan.py add  edit/4821 --kind broll --at "word:resume#1" --dur 1.6 \\
        --what "hands flipping through a printed resume" --why "illustrates the word, hides the s03/s04 cut" \\
        [--query "hands flipping resume paper"] [--source auto|project|local|generated] [--mode replace|window]
    python scripts/visual_plan.py add  edit/4821 --kind meme --at s07 --dur 1.2 --what "a statue shrugs" \\
        --why "irony about the 'perfect candidate'" --mode popup
    python scripts/visual_plan.py add  edit/4821 --kind scene --type quote --mode split --at "word:think#1" --dur 2.6 \\
        --lines "Test how they think," "not what they remember" [--accent think] [--label "NAME / ROLE"] [--source speech] \\
        [--tone calm] [--variant slam] [--items-json '[{"text":"...","at":"word:...#1"}]'] [--value-json '{"to":12}'] \\
        [--media inserts/ui-01.png] [--interaction-json '{"kind":"tap","target":[540,900],"at":"word:...#1"}'] \\
        [--box x,y,w,h] [--side left|right] [--sound card] [--hide-subtitles] --what "..." --why "..."
    python scripts/visual_plan.py init edit/promo1 --scenes-only --duration 22 [--brand acme]   # a promo without footage
    python scripts/visual_plan.py init edit/v1 --scenes-voice [--brand acme]   # scenes over a narration (cut.py voice.wav)
    python scripts/visual_plan.py keep-clear edit/4821 --from 3.7 --to 9.6 --box 60,400,760,420 --what "price card"
    python scripts/visual_plan.py keep-clear edit/4821 --remove 2      # the 2nd zone as numbered in visual_plan.md
    python scripts/visual_plan.py keep-clear edit/4821 --from 23.4 --to 26.7 --box 404,1038,632,652 --what presenter \
        --matte presenter --own-face 595,1120,181,233     # the presenter layer from matte.py place (it prints this line)
    python scripts/visual_plan.py hide-subs edit/4821 --from 23.4 --to 26.7 --why "presenter over a scene"
    python scripts/visual_plan.py hide-subs edit/4821 --remove 1       # numbered in visual_plan.md
    python scripts/visual_plan.py remove edit/4821 c03 [b01 ...]       # take inserts out of the plan (to change one: remove, add)
    python scripts/visual_plan.py validate edit/4821        # errors -> exit code 1; warnings -> exit code 0
    python scripts/visual_plan.py md edit/4821              # visual_plan.md: show it to the person before the render
    python scripts/visual_plan.py shade edit/4821           # the "Typewriter" darkening for 4.5:1 -> reel.json subtitles_shade
    python scripts/visual_plan.py stage edit/4821 --remotion reels [--name 4821]

--at: a second on the timeline (5.2), a span (s03, its start) or a word (word:paint#1, the start of its nth occurrence).
Insert statuses: planned -> ready (the file is prepared) | pending (waiting for a code scene or for the person's
approval) | skipped (declined: the main footage stays, the reason is in fallback). Only ready inserts go into the
render; an unfilled code-scene brief (gen) on an insert that is not ready is a warning, not an error.
Settings come from edit/<id>/reel.json (reelcfg.py save); the plan holds only a snapshot, and validate refreshes it.
`init --set` saves the settings to reel.json. keep-clear without a plan creates a plan with no inserts (a graphics registry).
keep-clear --matte NAME marks a presenter layer (matte.py place prints the command): its span counts in the coverage,
--own-face is the presenter's own face (validate and faces.py audit don't flag it in its own zone), and stage copies
edit/<id>/matte/NAME.webm to public/<id>/. hide-subs: windows where a per-video composition hides the subtitles
(a presenter, an accent title): stage adds them to props.hideSubtitles, faces.py audit reads them.
Coverage is the union of the intervals of all inserts (B-roll and memes, popups included, and presenter layers);
coverage and spacing are errors.
--source online (online footage and memes) needs the online-sources add-on it-reelsmaker-online; without it the online
source is unavailable.

Designed scenes (kind scene, ids c01...; references/scenes.md): types hook, quote, slogan, stat, list, contrast, word,
chat, ui, cta, cover; modes overlay, split, panel, window, full. A scene has no file: validate sets it to ready when its
fields are valid (an error -> planned). Checks: required fields and the mode for the type, the scene tone is one of the
brand's tones, the reading-time floor for the scene tone, a quote from the speech is verbatim per captions.json, a stat
has a source, contrast of the brand colors, coverage (full/split/panel/window together with B-roll), the
overlay/split/window box (face, safe zone, keep_clear), no two scenes at once, not over a meme, only cta in the last 2 s.
The brand tone's ceilings (memes, transitions, flash/whip, full) are errors; reel.json -> tone_override: true turns them
into warnings (going louder on explicit request, noted in the report). stage --props writes props.scenes and adds the
overlay/split/window scenes to keep_clear (faces.py audit sees them), and records the render's subtitle band in the plan
(subtitles_band: the top below the measured chin), which faces.py audit checks.
The "framed" format (reel.json -> format: framed, optional window and label; references/techniques.md): a horizontal
rough cut in a rounded window on the style's field. The camera is clamped to the window (as the kit draws it), boxes
and the subtitle band stay inside the window's text area (reels_common.framed_area: with no label the field above the
window joins it; reel.json -> subtitles_at: below puts the subtitle band on the field under the window instead,
reels_common.framed_sub_area), scenes are overlay or full (full covers the window), and stage writes props.framed (the
window, the label, the rough cut's size, the field color, where the subtitles go) so ReelKit draws the layout itself. validate checks that faces.json was
measured in the source geometry and that the rough cut is horizontal.
The "scenes only" format (init --scenes-only --duration N): no speech spans, --at in seconds only, every scene is full,
scene coverage >= 95 %; transitions are cuts (the texts hand over at the join, as the kit draws it) and more than 4 frames
of empty field at a join is a warning; stage --props: video "", empty captions with the duration, subtitles none.
The "scenes + voice" format (init --scenes-voice, after cut.py cut a sound-only narration into voice.wav): reel.json ->
voice off_camera, the plan's spans and length are the narration's (no 15-25 s limit, a warning past VOICE_MAX_S), every
scene is full and --at may name a spoken word; the subtitles stay on over full scenes unless a scene sets
--hide-subtitles, and a scene box on the subtitle band is an error; scene coverage under 95 % is a warning. stage
--props: video "", props.voice (public/<id>/voice.wav), the narration's captions, props.voiceMode off_camera.
"""
import argparse, contextlib, datetime, filecmp, hashlib, json, math, re, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (CORNER_BOX, FRAMED_HOOK_MIN, FRAMED_LABEL_UP, FRAMED_RADIUS, FRAMED_SUB_GAP, MEME_SIZES, NUMBER_RE, SUB_BAND, SUB_BLOCK_H, SUB_MAX_TOP,
                          SUB_TOP_KIT, budget, cam_fit, edit_dir, editing_json, effective, forbidden_hits, framed_area, framed_sub_area,
                          framed_at, framed_issues, framed_source, framed_view, inside, load_config, load_json, locked,
                          media_kind, online, parse_sets, probe, project_root, safe_slug, save_json, terms, ui_safe,
                          ui_zone, utf8_stdio, warn, LINE_FACE_MARGIN, UI_SAFE)
# The plan's code is in the vp_* modules; this file is the command line and keeps every one of their names,
# because the other scripts and the tests take them from visual_plan. Each module imports what it uses by
# name, so a test that replaces a function patches it where the caller looks it up (vp_scenes.camera_at
# for the scenes), not here.
from vp_core import (ABSTRACT_RE, AND_RE, CTA_RE, EMO_RE, END_CARD_S, FILLER_RE, GEN_FIELDS, HEADROOM_BAND,
                     HEADROOM_MIN, KEEP_ON_INIT, KINDS, LIST_RE, NUM_RE, POINT_RE, QUOTE_RE, SCENE_MODES, SLOGAN_RE,
                     SOURCES, STATUSES, TRANSITIONS, UI_RE, WHY_OLD_FINISH, WINDOW_DEFAULT, WINDOW_SLOTS, _LIN,
                     _RU_AZ, _YE, _YO, _ru, auto_plan, build_plan, current_settings, cut_id, editing_plan, end_now,
                     end_tail, ensure_plan, enumeration, find_spoken, finish_of, fmt_t, format_label, is_inside,
                     item_time, jround, load_plan, near_match, no_footage, norm_words, overlap, phrases, plan_duration,
                     plan_path, read_need, refresh_plan, resolve_at, scene_hints, snapshot, srgb_lum, NO_FOOTAGE,
                     VOICE_MAX_S)  # noqa: F401
from vp_camera import (camera_at, camera_shots, camera_view, chin_on_screen, plan_camera, same_source, source_files,
                       src_to_out, subtitle_top, subtitles_in)  # noqa: F401
from vp_scenes import (CHAT_FROM, COVER_MODES, EXPERIMENTAL_MODES, EXPERIMENTAL_SCENES, INTERACTIONS, JOIN_EMPTY_MAX,
                       SCENE_SOUNDS, SCENE_SOURCES, SCENE_TYPES, SPEAKER_WINDOW, SPLIT_BOX, SPLIT_CAM, VOICE_SUB_GAP,
                       WINDOW_SCENE_BOX, add_scene, subtitle_band_off_camera, voice_stage, check_scenes, default_box, experimental, faces_seen,
                       hidden_windows, hides_subtitles, layout_frames, overlay_slots, scene_box_issues, scene_export,
                       scene_face, scene_keep_entries, scene_text, scene_timeline, scene_tone, scenes_only_cover,
                       text_frames, text_full_on, text_zone, tone_issues, window_issues, without_own, word_times)  # noqa: F401
from vp_defects import (COVER_PAD, INSERT_IN, cmd_accept, defect_issues, hidden_span, hides_face, load_defects,
                        same_defect)  # noqa: F401
from vp_callouts import (CALLOUT, CALLOUT_AT_ONCE, CALLOUT_GAP_S, CALLOUT_INK, CALLOUT_MAX_W, CALLOUT_MOVES,
                         CALLOUT_PEOPLE, CALLOUT_RING, CALLOUT_SEEN, CALLOUT_STILL, CALLOUT_TIMES, CALLOUT_VARIANTS,
                         DRIFT, HOOK_BOX, PERSON_DOWN, PERSON_SIDE, _WIDE, _frames, _patch, _point, _screen_box,
                         _seg_hits, _segs_cross, _stat, _text_w, add_callout, anchor_on_screen, callout_at,
                         callout_context, callout_entrance, callout_geometry, callout_keep_entries, callout_moves,
                         callout_path, callout_side, callout_span, callout_times, callout_width, check_callouts,
                         drift_zoom, hook_lines, label_contrast, motion_note, parse_keys, path_at, path_frames,
                         path_issue, person_path, picture_motion, screen_to_frame, track_key, zoom_at)  # noqa: F401
from vp_validate import (cmd_validate, follow_rough_cut, profile_issues, voice_issues)  # noqa: F401
from vp_stage import (cmd_export, copy_voice)  # noqa: F401
from vp_shade import (SHADE_LINES, SHADE_TARGET, SHADE_X, cmd_shade)  # noqa: F401


def cmd_init(a):
    if a.scenes_only:
        return init_scenes_only(a)
    if a.scenes_voice:
        return init_scenes_voice(a)
    e = edit_dir(a.edit)
    cap = load_json(e / "captions.json")
    if not cap:
        sys.exit(f"no {e / 'captions.json'}: the visual plan is built after the rough cut (step 6)")
    if cap.get("voice") and not (e / "final.mp4").exists():  # cut.py cut a narration: there is no picture to plan over
        sys.exit(f"{e.name} is a narration cut (voice.wav, no picture): its plan is scenes over the voice: "
                 f"visual_plan.py init edit/{e.name} --scenes-voice")
    over = parse_sets(a.set)
    if a.brand:
        over["brand"] = safe_slug(a.brand, "--brand")
    with locked(plan_path(e)):
        old = load_json(plan_path(e))
        if old and old.get("inserts") and not a.force:
            sys.exit(f"the plan already exists: {plan_path(e)} (--force rebuilds it; the inserts are lost, keep_clear stays)")
        if over:  # the single source of settings is reel.json: --set is saved there, not only in the plan's snapshot
            with editing_json(e / "reel.json", {}) as reel:
                reel.update(over)
            print(f"{e / 'reel.json'}: " + ", ".join(f"{k}={v}" for k, v in over.items()))
        s, prov, doc, bdir, brand = current_settings(e, old)
        plan = build_plan(e, cap, s, prov, doc)
        plan["keep_clear"] = (old or {}).get("keep_clear", [])
        plan.update({k: old[k] for k in KEEP_ON_INIT if k in (old or {})})  # the last stage's finish, the subtitle band
        for d in load_defects(e)[0]:  # defects.py: a span with a bad picture gets the cover hint
            for g in plan["segments"]:
                if g["start"] < d["end"] and g["end"] > d["start"]:
                    g["hints"].append(f"picture {d['id']}: {d['kind']} {fmt_t(d['start'])}-{fmt_t(d['end'])} -> cover it "
                                      f"(full or code scene, replacing B-roll, cutaway) or accept it")
        if (old or {}).get("accepted_defects"):
            plan["accepted_defects"] = old["accepted_defects"]
        save_json(plan_path(e), plan)
    eff, why, dur = plan["effective"], plan["fallback"], plan["duration"]
    print(f"plan: {plan_path(e)}: {len(plan['segments'])} spans, {fmt_t(dur)}"
          + (f"; keep_clear kept ({len(plan['keep_clear'])})" if plan["keep_clear"] else ""))
    b = plan["budget"]
    scenes = bool(s.get("use_scenes"))  # T3: "inserts are off" was printed with designed scenes on
    if not eff.get("broll") and not eff.get("memes") and not scenes:
        print("inserts are off: the plan has only the main footage (the edit runs as without inserts)")
    else:
        print(f"budget ({s['intensity']}): up to {b['broll_max'] if eff.get('broll') else 0} B-roll, "
              f"up to {b.get('memes_max', 0) if eff.get('memes') else 0} memes, designed scenes {'on' if scenes else 'off'}, "
              f"inserts <= {b['coverage_max_s']} s in total (full, split, panel and window scenes count), "
              f">= {b.get('min_gap_s')} s between inserts. This is a ceiling, not a target.")
    for k, r in why.items():
        if r != "off" and k in ("online_footage", "generate_now", "online_memes") and s.get({"online_footage": "use_online_footage",
                                                                                         "generate_now": "generate_now",
                                                                                         "online_memes": "use_online_memes"}[k]):
            print(f"  fallback: {k} - {r}")


def init_scenes_only(a):
    """A promo without footage: a plan with no speech spans, scenes at absolute times; captions.json is not needed."""
    e = edit_dir(a.edit, create=True)
    if not a.duration or a.duration <= 0:
        sys.exit("--scenes-only needs --duration in seconds (15-25, best 18-22)")
    over = parse_sets(a.set)
    if a.brand:
        over["brand"] = safe_slug(a.brand, "--brand")
    with locked(plan_path(e)):
        old = load_json(plan_path(e))
        if old and old.get("inserts") and not a.force:
            sys.exit(f"the plan already exists: {plan_path(e)} (--force rebuilds it; the inserts are lost)")
        if over:
            with editing_json(e / "reel.json", {}) as reel:
                reel.update(over)
            print(f"{e / 'reel.json'}: " + ", ".join(f"{k}={v}" for k, v in over.items()))
        s, prov, doc, bdir, brand = current_settings(e, old)
        plan = build_plan(e, {"duration": round(float(a.duration), 3), "segments": [], "words": []}, s, prov, doc)
        plan.update({k: old[k] for k in KEEP_ON_INIT if k in (old or {})})
        plan["format"] = "scenes-only"
        save_json(plan_path(e), plan)
    so = (doc.get("scenes") or {}).get("scenes_only") or {}
    lo, hi = so.get("duration", [15, 25])
    print(f"'scenes only' plan: {plan_path(e)}: {fmt_t(plan['duration'])}, brand {s['brand']}, scene tone {s.get('scene_tone')}")
    if not lo <= plan["duration"] <= hi:
        warn(f"length {plan['duration']} s is outside {lo}-{hi} s (best {'-'.join(map(str, so.get('optimum', [18, 22])))} s)")
    print("storyboard: hook 2-3 s -> reveal 2-4 s -> 2-3 strong moments -> punchline/cta 2-4 s; scenes back to back "
          "(coverage >= 95 %), all in full mode, --at in seconds (3.0)")


def init_scenes_voice(a):
    """Scenes over a recorded narration: the plan on the narration's cut (cut.py on a sound-only source: voice.wav and
    captions.json with its words), the voice off camera, every scene full."""
    e = edit_dir(a.edit)
    cap = load_json(e / "captions.json") or {}
    if not cap.get("voice") or not (e / "voice.wav").is_file():
        sys.exit(f"no narration cut in {e}: cut the recording first: cut.json with the sound-only file as its source, "
                 f"then cut.py edit/{e.name} (it writes voice.wav and captions.json)")
    over = parse_sets(a.set)
    if a.brand:
        over["brand"] = safe_slug(a.brand, "--brand")
    over["voice"] = "off_camera"  # the sound mode of the video (reels_common.VOICE_MODES): the narration is off camera
    with locked(plan_path(e)):
        old = load_json(plan_path(e))
        if old and old.get("inserts") and not a.force:
            sys.exit(f"the plan already exists: {plan_path(e)} (--force rebuilds it; the inserts are lost)")
        with editing_json(e / "reel.json", {}) as reel:
            reel.update(over)
        print(f"{e / 'reel.json'}: " + ", ".join(f"{k}={v}" for k, v in over.items()))
        s, prov, doc, bdir, brand = current_settings(e, old)
        plan = build_plan(e, cap, s, prov, doc)
        plan.update({k: old[k] for k in KEEP_ON_INIT if k in (old or {})})
        plan["format"] = "scenes-voice"
        plan["captions_id"] = cut_id(cap)
        save_json(plan_path(e), plan)
    print(f"'scenes + voice' plan: {plan_path(e)}: {len(plan['segments'])} spans of the narration, {fmt_t(plan['duration'])}"
          f", brand {s['brand']}, scene tone {s.get('scene_tone')}")
    if plan["duration"] > VOICE_MAX_S:
        warn(f"the narration is {plan['duration']:.0f} s: past ~{VOICE_MAX_S} s the render may not fit an 8 GB laptop "
             f"(SKILL.md section 15): cut it shorter or render on a bigger machine")
    print("storyboard: a hook on the first words, then one scene per idea, back to back; every scene is full, --at may "
          "name a spoken word (word:...#1); the subtitles stay on over the scenes (--hide-subtitles on a scene whose text "
          "repeats the narration)")


def meme_rights(meme_id):
    """A meme's rights from the meme index (memes.py index), so validate knows them before memes.py prepare (T5:
    "rights are unknown" for an own meme and a CC one). blocked: forbidden by third-party rights. None: no id, or the
    meme is not indexed yet (a warning)."""
    if not meme_id:
        return None
    import memes
    m = (load_json(memes.index_path(project_root())) or {}).get(meme_id)
    if m is None:
        warn(f"--meme-id {meme_id}: not in the meme index (memes.py index); its rights stay unknown until memes.py prepare")
        return None
    return "blocked" if memes.is_blocked(m) else m.get("rights") or "unknown"


def cmd_add(a):
    if a.kind == "scene":
        return add_scene(a)
    if a.kind == "callout":
        return add_callout(a)
    if a.source not in SOURCES + ["auto"]:
        sys.exit(f"--source {a.source}: for {a.kind} allowed {', '.join(SOURCES + ['auto'])}")
    if a.source == "online" and not online():  # online sources come only with the online add-on
        sys.exit("--source online: the online add-on is not installed; use auto, project, local or generated")
    if a.mode and a.mode not in KINDS[a.kind]["modes"]:  # a wrong mode was saved and failed only at validate
        sys.exit(f"{a.kind} --mode {a.mode}: allowed {', '.join(KINDS[a.kind]['modes'])}"
                 + ("; full frame for B-roll is `replace`" if a.kind == "broll" else ""))
    a.transition = a.transition or "cut"
    e = edit_dir(a.edit)
    cap = load_json(e / "captions.json", {})
    with editing_plan(e) as plan:
        start = resolve_at(a.at, plan, cap)
        kind = a.kind
        pre = KINDS[kind]["prefix"]
        n = 1 + max([int(i["id"][1:]) for i in plan["inserts"] if i["id"].startswith(pre)] or [0])
        mode = a.mode or KINDS[kind]["modes"][0]
        seg = next((g for g in plan["segments"] if g["start"] <= start < g["end"]), None)
        ins = {"id": f"{pre}{n:02d}", "kind": kind, "segment": seg["id"] if seg else None, "start": round(start + a.offset, 3),
               "dur": a.dur, "mode": mode, "what": a.what, "why": a.why, "query": a.query or "",
               "source": a.source, "candidate": None, "file": None, "src_in": 0.0,
               "transition_in": a.transition, "transition_out": a.transition_out or ("cut" if a.transition == "cut" else a.transition),
               "status": "planned", "fallback": "main footage", "credit": None}
        if kind == "meme":
            ins.update({"meme_id": a.meme_id, "position": a.position, "rights": meme_rights(a.meme_id), "audio": False})
        if a.source == "generated":
            ins["gen"] = {k: "" for k in GEN_FIELDS}
        if a.cam:
            ins["cam"] = [float(x) for x in a.cam.split(",")]
        if a.covers:
            ins["covers"] = list(a.covers)
        if kind == "broll" and mode == "window":  # the window box: the given one or the first free slot
            if a.box:
                ins["box"] = [int(float(x)) for x in a.box.split(",")]
            else:
                ins["box"] = next((b for b in WINDOW_SLOTS if not window_issues(e, plan, ins, b)), WINDOW_DEFAULT)
            for m in window_issues(e, plan, ins, ins["box"]):
                warn(f"{ins['id']}: {m}: validate will refuse it; set --box or move the insert")
        plan["inserts"].append(ins)
        plan["inserts"].sort(key=lambda i: i["start"])
    print(f"{ins['id']}: {kind} {mode} {fmt_t(ins['start'])} +{a.dur} s ({ins['segment']}): {a.what}"
          + (f"; window {ins['box']}" if ins.get("box") and kind == "broll" else ""))


def cmd_md(a):
    e = edit_dir(a.edit)
    errs, warns = cmd_validate(a, quiet=True)  # also refreshes the settings snapshot in the plan
    plan = load_plan(e)
    s, eff, why = plan["settings"], plan["effective"], plan.get("fallback", {})
    ins = plan["inserts"]
    ext = online()  # the online part of the header and the download list only with the online add-on
    L = [f"# Visual plan: {plan['id']}", "",
         f"Brand **{plan['brand']}**, length {fmt_t(plan['duration'])}, intensity **{s['intensity']}**, "
         f"B-roll {'on' if eff.get('broll') else 'off'}, memes {'on' if eff.get('memes') else 'off'}, "
         f"code scenes {'on' if eff.get('generated_code') else 'off'}"
         + (f", online footage {'yes' if eff.get('online_footage') else 'no'}" if ext else ""), ""]
    fb = [f"{k}: {v}" for k, v in why.items() if k in ("online_footage", "generate_now", "online_memes") and v != "off"]
    if fb:
        L += ["Fallback: " + "; ".join(fb), ""]
    if plan.get("format") == "scenes-voice":
        L += ["Format: **scenes + recorded voice** (the narration off camera, voice.wav): spans are its phrases, every "
              "scene is full, the subtitles of the narration stay on over the scenes unless a scene hides them.", ""]
    elif plan.get("format") == "scenes-only":
        L += ["Format: **scenes only** (a promo without footage): no speech spans, scenes by time; between scenes the "
              "transition is a cut (one text leaves by its scene's last frame, the next enters from its first).", ""]
    elif framed_at(e):
        fr = framed_at(e)
        L += [f"Format: **framed** (a horizontal source in a window drawn by the kit): window {fr['window']}"
              + (f", label “{fr['label']}”" if fr["label"] else ", no label") + f"; text area {framed_area(fr)}"
              + (f"; subtitles below the window, band {framed_sub_area(fr)}" if fr["subtitles_at"] == "below" else "")
              + ".", ""]
    bt = s.get("brand_tone") or {}
    if bt:
        L += [f"Brand tone **{bt.get('preset')}** ({bt.get('label', '')}), scene tone {s.get('scene_tone') or bt.get('scene_tone')}"
              + (", **tone_override** (ceilings exceeded: noted in the report)" if s.get("tone_override") else ""), ""]
    if plan["segments"]:  # "scenes only": no speech spans, so no table; the scenes are listed below
        L += ["| # | Timecode | Line | Main footage | B-roll | Meme | Scene | Transition | Comment |",
              "|---|---|---|---|---|---|---|---|---|"]
    for g in plan["segments"]:
        over = [i for i in ins if overlap(i, {"start": g["start"], "dur": g["end"] - g["start"]}) > 0.05]
        br = "; ".join(f"**{i['id']}** {i['what']} ({i['source']}, {i['dur']} s, {i['mode']}, {i['status']})"
                       for i in over if i["kind"] == "broll") or "-"
        mm = "; ".join(f"**{i['id']}** {i['what']} ({i['dur']} s, {i['mode']}, {i['status']})"
                       for i in over if i["kind"] == "meme") or "-"
        sn = "; ".join(f"**{i['id']}** {i.get('type')} {i['mode']}{experimental(i)}: {scene_text(i)} ({i['dur']} s, {i['status']})"
                       for i in over if i["kind"] == "scene") or "-"
        sn = "; ".join([sn] * (sn != "-") + [f"**{i['id']}** callout “{' / '.join((i.get('text') or {}).get('lines') or [])}” "
                                             f"({i['dur']} s, {i['status']})" for i in over if i["kind"] == "callout"]) or "-"
        tr = "; ".join(f"{i['id']}: {i['transition_in']}/{i['transition_out']}" for i in over if "transition_in" in i) or "cut"
        main = g["main"] + (f", {g['camera']}" if g.get("camera") else "") + (f"; graphics: {g['graphics']}" if g.get("graphics") else "")
        com = "; ".join(filter(None, [g.get("notes", "")] + [f"{i['id']}: {i['why']}" for i in over]
                               + ([f"hints: {', '.join(g['hints'])}"] if g.get("hints") else [])))
        txt = g["text"] if len(g["text"]) < 90 else g["text"][:87] + "..."
        L.append(f"| {g['id']} | {fmt_t(g['start'])}-{fmt_t(g['end'])} | {txt} | {main} | {br} | {mm} | {sn} | {tr} | {com} |")
    if ins:
        L += ["", "## Inserts", ""]
        for i in ins:
            if i["kind"] == "scene":
                src = i.get("source") or {}
                L.append(f"- **{i['id']}** scene {i.get('type')} {fmt_t(i['start'])} +{i['dur']} s, {i['mode']}{experimental(i)}, tone "
                         f"{scene_tone(i, s)}: {scene_text(i)}. What: {i['what']}. Why: {i['why']}. "
                         + (f"Source: {src.get('kind')}{' (' + src['ref'] + ')' if src.get('ref') else ''}. " if src else "")
                         + f"Transition {i.get('transition_in')}/{i.get('transition_out')}"
                         + (", subtitles hidden" if hides_subtitles(i, s) else "") + f". Status: {i['status']}")
                continue
            if i["kind"] == "callout":
                src = i.get("source") or {}
                L.append(f"- **{i['id']}** callout {i.get('variant')} (experimental) {fmt_t(i['start'])} +{i['dur']} s: "
                         f"“{' / '.join((i.get('text') or {}).get('lines') or [])}”, "
                         + (f"dot on the {i['person']} person's shoulder" if i.get("person") else
                            f"dot from {i.get('anchor')} along {len(i['path'])} {'track points' if i.get('path_by') == 'track' else 'points set by hand'}"
                            if i.get("path") else f"from {i.get('anchor')} to {i.get('to')}" if i.get("to") else
                            f"dot at {i.get('anchor')}")
                         + (f", ring r {i.get('radius'):g}" if i.get("radius") else "") + ", label "
                         f"{i.get('side')}{' below' if i.get('below') else ''}, tone {scene_tone(i, s)}. What: {i['what']}. "
                         f"Why: {i['why']}. " + (f"Source: {src.get('kind')}{' (' + src['ref'] + ')' if src.get('ref') else ''}. "
                                                 if src else "") + f"Status: {i['status']}")
                continue
            c = i.get("candidate") or {}
            L.append(f"- **{i['id']}** {i['kind']} {fmt_t(i['start'])} +{i['dur']} s, {i['mode']}: {i['what']}. "
                     f"Why: {i['why']}. Source: {i['source']}"
                     + (f" ({c.get('provider')}: {c.get('title') or c.get('id')}, {c.get('w')}x{c.get('h')}, "
                        f"{c.get('size_mb', '?')} MB, license {c.get('license', '?')})" if c else "")
                     + f". Status: {i['status']}" + (f" -> {i['fallback']}" if i["status"] in ("pending", "skipped") else ""))
        dl = [i for i in ins if ext and i.get("source") == "online" and (i.get("candidate") or {}).get("provider")
              and i["status"] != "ready"]
        if dl:
            L += ["", "**Download after the person's approval ('yes'):** " + "; ".join(
                f"{i['id']}: {i['candidate']['provider']} {i['candidate'].get('id')}, {i['candidate'].get('size_mb', '?')} MB"
                for i in dl)]
        if any(i.get("source") == "generated" for i in ins):
            L += ["", "Code-scene briefs: `generated/briefs.md` (`codescene.py manifest`)."]
        if any(experimental(i) for i in ins if i["kind"] == "scene"):
            L += ["", "**Experimental** scenes or modes: the kit draws them, but none is checked in a finished video yet; "
                      "look at their storyboard frames (`board.py`) before the full render."]
    keep = plan.get("keep_clear") or []
    if keep:  # cards, the hook, the CTA drawn per video: their texts are shown before the render too (SKILL.md step 8)
        L += ["", "## Graphics zones (keep_clear)", ""]
        L += [f"{n}. {fmt_t(k['start'])}-{fmt_t(k['end'])} {k.get('what', '')} box {k.get('box')}"
              + (f", camera {k['cam']}" if k.get("cam") else "")
              + (f", presenter layer {k['matte']} (counts in the coverage)" if k.get("matte") else "")
              + (f" (scene {k['scene']}, written by stage)" if k.get("scene") else "")
              for n, k in enumerate(keep, 1) if not k.get("callout")]
        # a callout's label has a zone per 0.25 s for the audit: one line here (Fable review: ~10 lines a callout)
        L += [f"- callout {c} label: its box every 0.25 s on screen, written by stage (`remove {c}` takes the callout)"
              for c in dict.fromkeys(k["callout"] for k in keep if k.get("callout"))]
        L += ["", "Remove a zone: `visual_plan.py keep-clear edit/<id> --remove N`."]
    defects, _ = load_defects(e)
    if defects:  # what the person sees about the picture: each defect and how it is handled
        s_, _p, doc_, _b, _br = current_settings(e, plan)
        _e, _w, state = defect_issues(e, plan, s_, doc_, load_json(e / "captions.json", {}))
        L += ["", "## Picture defects (defects.py)", ""]
        L += [f"- {d['id']} {d['kind']} {fmt_t(d['start'])}-{fmt_t(d['end'])}"
              + (f" «{d['words']}»" if d.get("words") else "") + f": {state.get(d['id'], 'open')}" for d in defects]
    hs = plan.get("hide_subtitles") or []
    if hs:
        L += ["", "## Subtitles hidden (hide-subs)", ""]
        L += [f"{n}. {fmt_t(h['start'])}-{fmt_t(h['end'])}" + (f": {h['why']}" if h.get("why") else "")
              for n, h in enumerate(hs, 1)]
        L += ["", "Remove a window: `visual_plan.py hide-subs edit/<id> --remove N`."]
    L += ["", f"Check: {len(errs)} error(s), {len(warns)} warning(s)."]
    L += [f"- error: {m}" for m in errs] + [f"- warning: {m}" for m in warns]
    out = e / "visual_plan.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out)


def cmd_keep(a):
    """A zone that memes and windows don't cover: a card, the hook, the CTA, an object in hand. --remove N takes zones out
    (numbered as in visual_plan.md, from 1)."""
    e = edit_dir(a.edit)
    if a.remove:
        with editing_plan(e) as plan:
            keep = plan.get("keep_clear") or []
            bad = [n for n in a.remove if not 1 <= n <= len(keep)]
            if bad:
                sys.exit(f"keep_clear has {len(keep)} zone(s) (visual_plan.md numbers them): no {', '.join(map(str, bad))}")
            own = [n for n in a.remove if keep[n - 1].get("scene") or keep[n - 1].get("callout")]
            if own:
                k0 = keep[own[0] - 1]
                what = "a scene" if k0.get("scene") else "a callout"
                sys.exit(f"zone {', '.join(map(str, own))} belongs to {what} and stage writes it back: remove {what} "
                         f"(visual_plan.py remove {a.edit} {k0.get('scene') or k0.get('callout')}) or move it")
            gone = [keep[n - 1] for n in sorted(set(a.remove))]
            plan["keep_clear"] = [k for n, k in enumerate(keep, 1) if n not in set(a.remove)]
        for k in gone:
            print(f"keep_clear removed: {k.get('what', '')} {k.get('box')} {fmt_t(k['start'])}-{fmt_t(k['end'])}")
        return
    if a.start is None or a.end is None or not a.box or not a.what:
        sys.exit("keep-clear: --from, --to, --box and --what are needed (or --remove N)")
    box = [int(x) for x in a.box.split(",")]
    entry = {"start": a.start, "end": a.end, "box": box, "what": a.what}
    if a.cam:  # the span's camera, so that validate checks the face where the viewer sees it
        entry["cam"] = [float(x) for x in a.cam.split(",")]
    if a.matte:  # a presenter layer (matte.py place): coverage, its WebM copied by stage
        entry["matte"] = safe_slug(a.matte, "--matte", dots=True)
        if not (e / "matte" / f"{entry['matte']}.webm").exists():
            warn(f"no {e / 'matte' / (entry['matte'] + '.webm')}: stage has nothing to copy until matte.py cut makes it")
    if a.own_face:  # the presenter's own face on screen: not a no-go for its own layer
        entry["own_face"] = [int(x) for x in a.own_face.split(",")]
        if len(entry["own_face"]) != 4:
            sys.exit("--own-face: x,y,w,h")
    with locked(plan_path(e)):
        plan = load_json(plan_path(e))
        if plan is None:  # inserts are off and no plan was built: a plan without inserts is created (a graphics registry)
            s, prov, doc, bdir, brand = current_settings(e)
            plan = auto_plan(e, load_json(e / "captions.json"), s, prov, doc)
            print(f"there was no plan: created {plan_path(e)} without inserts (spans and keep_clear only)")
        plan.setdefault("keep_clear", []).append(entry)
        save_json(plan_path(e), plan)
    print(f"keep_clear: {a.what} {box} {fmt_t(a.start)}-{fmt_t(a.end)}")
    import faces as fc
    data = fc.load(e)
    if data and a.matte:  # a presenter layer: the rough cut is not visible under it, the face in it is the presenter's own
        print("presenter layer: counts in the inserts' coverage; the face in it is the presenter's own (not checked)")
    elif data:
        # the face where the viewer sees it: --cam for this zone, else camera.json at each sample's time (as validate
        # and the render audit see it; T4: keep-clear without --cam checked the box against the uncropped frame)
        cam = [float(x) for x in a.cam.split(",")] if a.cam else None
        faces_, how_ = faces_seen(e, plan, data, a.start, a.end, cam, shots_ok=not cam)
        shots = how_ == "camera.json"
        hit = [b for b in faces_ if fc.inter(box, fc.grow(b, fc.MARGIN))]
        how = ", with the camera" if cam else ", with the camera of camera.json" if shots else ", without a camera"
        print(f"warning: '{a.what}' touches the face (margin {fc.MARGIN} px{how}): {fc.union(hit)}: move it to a zone "
              f"from faces.py zones" if hit else f"the face is not touched (per faces.json{how})")


def cmd_hide(a):
    """Windows where the subtitles are hidden by something the plan doesn't hold as a scene (a presenter over a scene, an
    accent title in a per-video composition): stage puts them into props.hideSubtitles, faces.py audit reads them.
    --remove N takes windows out (numbered as in visual_plan.md, from 1)."""
    e = edit_dir(a.edit)
    ensure_plan(e)  # a plain edit has no init (SKILL.md step 7a)
    with editing_plan(e) as plan:
        hs = plan.setdefault("hide_subtitles", [])
        if a.remove:
            bad = [n for n in a.remove if not 1 <= n <= len(hs)]
            if bad:
                sys.exit(f"hide_subtitles has {len(hs)} window(s) (visual_plan.md numbers them): no {', '.join(map(str, bad))}")
            gone = [hs[n - 1] for n in sorted(set(a.remove))]
            plan["hide_subtitles"] = [h for n, h in enumerate(hs, 1) if n not in set(a.remove)]
        else:
            if a.start is None or a.end is None or a.end <= a.start:
                sys.exit("hide-subs: --from and --to (--to after --from) are needed, or --remove N")
            dur = plan.get("duration")
            if dur and (a.start < 0 or a.end > float(dur) + 0.05):
                sys.exit(f"hide-subs: {a.start}-{a.end} is outside the video (0-{dur})")
            gone = []
            hs.append({"start": round(a.start, 3), "end": round(a.end, 3), **({"why": a.why} if a.why else {})})
            hs.sort(key=lambda h: h["start"])
    for h in gone:
        print(f"hide_subtitles removed: {fmt_t(h['start'])}-{fmt_t(h['end'])} {h.get('why', '')}".rstrip())
    if not a.remove:
        print(f"hide_subtitles: {fmt_t(a.start)}-{fmt_t(a.end)}" + (f" ({a.why})" if a.why else "")
              + "; stage puts it into props.hideSubtitles, faces.py audit reads it")


def cmd_remove(a):
    """Take inserts (B-roll, memes, scenes) out of the plan, with the zones stage wrote for those scenes. To change an
    insert: remove it and add it again (T1 edited visual_plan.json by hand five times for want of this)."""
    e = edit_dir(a.edit)
    with editing_plan(e) as plan:
        have = {i["id"] for i in plan["inserts"]}
        missing = [x for x in a.ids if x not in have]
        if missing:
            sys.exit(f"no insert {', '.join(missing)} in the plan (there are: {', '.join(sorted(have)) or 'none'})")
        gone = [i for i in plan["inserts"] if i["id"] in a.ids]
        plan["inserts"] = [i for i in plan["inserts"] if i["id"] not in a.ids]
        if plan.get("keep_clear"):
            plan["keep_clear"] = [k for k in plan["keep_clear"] if k.get("scene") not in a.ids and k.get("callout") not in a.ids]
    for i in gone:
        print(f"removed {i['id']}: {i['kind']} {i.get('type') or i.get('mode')} {fmt_t(i['start'])} +{i['dur']} s: {i['what']}")
    print("files the inserts used stay where they are; validate and stage again")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("edit"); p.add_argument("--set", nargs="*"); p.add_argument("--force", action="store_true")
    p.add_argument("--scenes-only", action="store_true", help="a promo without footage: a plan without speech, scenes only")
    p.add_argument("--duration", type=float, help="the length of a 'scenes only' video, s (15-25)")
    p.add_argument("--scenes-voice", action="store_true", help="scenes over a recorded narration (cut.py made voice.wav): "
                                                               "the plan on its words, the voice off camera")
    p.add_argument("--brand", help="the video's brand (saved to reel.json)")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("add"); p.add_argument("edit"); p.add_argument("--kind", choices=list(KINDS), required=True)
    p.add_argument("--at", required=True); p.add_argument("--offset", type=float, default=0.0)
    p.add_argument("--dur", type=float, required=True); p.add_argument("--what", required=True); p.add_argument("--why", required=True)
    p.add_argument("--query"); p.add_argument("--mode")
    p.add_argument("--source", default="auto", choices=SOURCES + ["auto"] + SCENE_SOURCES,
                   help="B-roll or meme: where the footage comes from (online needs the online add-on); scene: where the "
                        "text or number comes from (speech|brief|brand|client|agent)")
    p.add_argument("--transition", choices=TRANSITIONS, help="the entrance (B-roll and memes: cut; a scene: per the scene tone)")
    p.add_argument("--transition-out", choices=TRANSITIONS)
    p.add_argument("--meme-id"); p.add_argument("--position", default="top")
    p.add_argument("--box", help="the window box x,y,w,h (B-roll --mode window); without it, the first free slot")
    p.add_argument("--cam", help="z,cx,cy of the camera at this point: the rough cut's faces are checked in screen coordinates")
    p.add_argument("--covers", nargs="+", metavar="DNN", help="picture defects this insert covers (defects.py: d01…)")
    g = p.add_argument_group("scene (--kind scene)")
    g.add_argument("--type", choices=list(SCENE_TYPES)); g.add_argument("--lines", nargs="+", metavar="LINE")
    g.add_argument("--accent"); g.add_argument("--label"); g.add_argument("--source-ref", help="where the text or number comes from")
    g.add_argument("--tone", help="the scene tone (calm, deadpan, cinematic, feature, punchy, hype, parody); without it, the video's tone")
    g.add_argument("--variant"); g.add_argument("--items-json"); g.add_argument("--value-json")
    g.add_argument("--media", help="a screenshot or a recording (copied to edit/<id>/inserts/)"); g.add_argument("--interaction-json")
    g.add_argument("--side", choices=["left", "right"], help="window (right by default) / panel (left): the speaker's side; callout: the label's side "
                        "(default: the one with room)")
    g.add_argument("--frame-at", type=float, help="cover: the video second under the cover (otherwise 1.0 s or poster.py pick)")
    g.add_argument("--sound", choices=SCENE_SOUNDS); g.add_argument("--hide-subtitles", action="store_true")
    g = p.add_argument_group("callout (--kind callout; also --variant tag|line|badge|ring|dimension, --lines, --side, "
                             "--tone, --source)")
    g.add_argument("--anchor", metavar="X,Y", help="the object's point on the 1080x1920 rough cut, where the dot goes")
    g.add_argument("--below", action="store_true", help="the label under the dot (default: above it)")
    g.add_argument("--keys", nargs="+", metavar="T:X,Y", help="a moving dot: points of the rough cut at seconds from the "
                   "callout's start, T:- hides it (a slow pan; a handheld shot: track.py)")
    g.add_argument("--person", choices=CALLOUT_PEOPLE, help="point at a person: the dot follows the shoulder under the "
                   "left, right or central face of faces.json")
    g.add_argument("--radius", type=float, help="ring: the ring's radius around the object, px of the rough cut")
    g.add_argument("--to", metavar="X,Y", help="dimension: the second end of what is measured")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("keep-clear"); p.add_argument("edit"); p.add_argument("--from", dest="start", type=float)
    p.add_argument("--to", dest="end", type=float); p.add_argument("--box", help="x,y,w,h in 1080x1920")
    p.add_argument("--what"); p.add_argument("--cam", help="z,cx,cy of the camera on this span")
    p.add_argument("--remove", type=int, nargs="+", metavar="N", help="remove zone N (numbered in visual_plan.md, from 1)")
    p.add_argument("--matte", help="a presenter layer: the matte.py name (counts in the coverage, stage copies its WebM)")
    p.add_argument("--own-face", help="x,y,w,h: the presenter's own face on screen (not flagged in its own zone)")
    p.set_defaults(fn=cmd_keep)
    p = sub.add_parser("hide-subs", help="hide the subtitles in a window a per-video composition covers")
    p.add_argument("edit"); p.add_argument("--from", dest="start", type=float); p.add_argument("--to", dest="end", type=float)
    p.add_argument("--why"); p.add_argument("--remove", type=int, nargs="+", metavar="N",
                                            help="remove window N (numbered in visual_plan.md, from 1)")
    p.set_defaults(fn=cmd_hide)
    p = sub.add_parser("accept", help="leave a picture defect on purpose (defects.py), with a reason")
    p.add_argument("edit"); p.add_argument("ids", nargs="+", metavar="DNN"); p.add_argument("--why")
    p.add_argument("--remove", action="store_true", help="take the acceptance back")
    p.set_defaults(fn=cmd_accept)
    p = sub.add_parser("remove", help="take inserts out of the plan"); p.add_argument("edit")
    p.add_argument("ids", nargs="+", help="insert ids: c03, b01, m02")
    p.set_defaults(fn=cmd_remove)
    p = sub.add_parser("validate"); p.add_argument("edit")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--sting", action="store_true", help="a logo sting will follow the cut (stage --sting): the last 2 s "
                                                        "count from the end of the whole video")
    g.add_argument("--card", action="store_true", help="an end card will follow the cut (stage --card)")
    p.add_argument("--corner", action="store_true", help="the stage will draw the corner logo (stage --corner): the "
                                                         "brand counts as seen from the first frame")
    p.add_argument("--hook", action="store_true", help="the stage will show a hook headline (stage --hook): the video "
                                                       "counts as opening on its hook")
    p.set_defaults(fn=lambda a: sys.exit(1 if cmd_validate(a)[0] else 0))
    p = sub.add_parser("md"); p.add_argument("edit"); p.set_defaults(fn=cmd_md)
    p = sub.add_parser("shade", help="measure the darkening behind \"Typewriter\" subtitles (reel.json subtitles_shade)")
    p.add_argument("edit"); p.add_argument("--color", help="the subtitle text color (default: the brand's text_on_primary)")
    p.add_argument("--top", type=int, help="the subtitles' top y (default: the band stage recorded, else the chin)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--zone", metavar="X,Y,W,H", help="measure a text zone instead of the subtitle band (a flat darkening)")
    g.add_argument("--scene", metavar="ID", help="measure the box of this scene, over its time (a flat darkening)")
    p.add_argument("--from", dest="start", type=float, help="--zone: from this second (default: the whole video)")
    p.add_argument("--to", dest="end", type=float, help="--zone: up to this second")
    p.add_argument("--target", type=float, help="the contrast to reach (default 4.5 for subtitles, 3.0 for a zone: large text)")
    p.set_defaults(fn=cmd_shade)
    p = sub.add_parser("stage"); p.add_argument("edit"); p.add_argument("--remotion", required=True); p.add_argument("--name")
    p.add_argument("--force", action="store_true"); p.add_argument("--props", help="the props file for the template composition")
    p.add_argument("--subtitles", choices=["accent", "plate", "typewriter", "none"])
    # hook, corner logo and end are kept from the last stage unless a flag changes them (finish_of)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--hook", help="the hook headline over the first 2.4 s (kept by later stages)")
    g.add_argument("--no-hook", action="store_true", help="take the hook headline off")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--card", nargs="+", metavar="LINE", help="the end card: 1-2 CTA lines")
    g.add_argument("--sting", action="store_true", help="a logo sting at the end: the logo with the brand line, 2.6 s, no CTA")
    g.add_argument("--no-end", action="store_true", help="take the end card or sting off")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--corner", action="store_true", help="the brand mark in the corner")
    g.add_argument("--no-corner", action="store_true", help="take the corner mark off")
    p.add_argument("--copy-video", action="store_true")
    p.set_defaults(fn=cmd_export)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
