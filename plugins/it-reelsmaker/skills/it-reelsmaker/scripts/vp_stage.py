"""The visual plan's stage command: the plan and the brand become the props of the Remotion project. Part of visual_plan.py, with no command line
of its own: the other scripts take these names from visual_plan."""
import shutil, sys
from pathlib import Path

from reels_common import (CORNER_BOX, FRAMED_RADIUS, FRAMED_SUB_GAP, SUB_BLOCK_H, UI_SAFE, edit_dir, framed_at,
                          framed_source, framed_sub_area, inside, load_json, safe_slug, save_json, voice_mode, warn)
from vp_core import (END_CARD_S, editing_plan, finish_of, load_plan, no_footage)
from vp_camera import (camera_shots, subtitle_top, subtitles_in)
from vp_scenes import (hidden_windows, scene_export, scene_keep_entries)
from vp_callouts import (callout_context, callout_keep_entries, callout_path, callout_width)
from vp_validate import (cmd_validate)


def copy_voice(e, rem, name):
    """The narration of a "scenes + voice" video -> public/<name>/voice.wav, where props.voice points (refreshed when
    cut.py rebuilt it: another size or modification time)."""
    src = e / "voice.wav"
    if not src.is_file():
        sys.exit(f"no {src}: cut the narration first (cut.py edit/{e.name})")
    dst = inside(rem / "public", rem / "public" / name / "voice.wav", "voice copy")
    st, dt = src.stat(), (dst.stat() if dst.exists() else None)
    if not dt or dt.st_size != st.st_size or abs(dt.st_mtime - st.st_mtime) > 1:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"voice: {src} -> public/{name}/voice.wav" + (" (updated)" if dt else ""))


def cmd_export(a):
    e = edit_dir(a.edit)
    errs, _ = cmd_validate(a, quiet=True)
    if errs and not a.force:
        for m in errs:
            print("error: " + m)
        sys.exit("the plan has errors: fix them (or use --force)")
    plan = load_plan(e)  # after validate the settings snapshot is current
    fin, notes, kept = finish_of(a, plan)  # hook, corner logo, end: this run's flags, else the last stage's choice
    if notes:  # reviews 2026-10-18: a warning and a dropped card made the video 2.6 s shorter, and the next stage was silent
        sys.exit("nothing staged, the plan is unchanged: " + "; ".join(notes))
    end = fin["end"] or {}
    if kept:
        print(f"kept from {'the last stage' if plan.get('finish') else 'the series preset'}: {', '.join(kept)} "
              f"(--no-hook, --no-corner, --no-end take them off)")
    rem = Path(a.remotion).resolve()
    if not (rem / "package.json").is_file() or not (rem / "src").is_dir():
        sys.exit(f"not a Remotion project (no package.json or src/): {rem}; nothing staged")
    name = safe_slug(a.name or plan["id"], "--name", dots=True)
    pub = inside(rem / "public", rem / "public" / name / "inserts", "inserts folder")
    out, skipped = [], []
    for i in plan["inserts"]:
        if i["kind"] in ("scene", "callout"):  # scenes and callouts: separate lists below
            continue
        if i["status"] != "ready":
            skipped.append(f"{i['id']} ({i['status']}) -> {i.get('fallback') or 'main footage'}")
            continue
        src = e / i["file"]
        pub.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, pub / src.name)
        out.append({"id": i["id"], "kind": i["kind"], "mode": i["mode"], "file": f"{name}/inserts/{src.name}",
                    "media": "image" if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") else "video",
                    "start": i["start"], "dur": i["dur"], "src_in": i.get("src_in", 0.0),
                    "transition_in": i["transition_in"], "transition_out": i["transition_out"],
                    "position": i.get("position"), "audio": i.get("audio", False), "plate": i.get("plate", False),
                    "box": i.get("box")})
    s = plan["settings"]
    cap = load_json(e / "captions.json", {})
    scenes, cover, hide, sk = [], None, [], []
    for i in plan["inserts"]:
        if i["kind"] != "scene":
            continue
        if i["status"] != "ready":
            sk.append(f"{i['id']} ({i['status']})")
            continue
        sp = scene_export(i, e, pub, name, plan, cap, s)
        if i.get("type") == "cover":
            cover = cover or sp
            continue
        scenes.append(sp)
        if sp.get("hide_subtitles"):
            hide.append([sp["start"], round(sp["start"] + sp["dur"], 3)])
    callouts = []  # drawn by the kit's CalloutLayer from their fields (references/callouts.md)
    cctx = callout_context(e, plan)
    for i in plan["inserts"]:
        if i["kind"] != "callout":
            continue
        if i["status"] != "ready":
            sk.append(f"{i['id']} ({i['status']})")
            continue
        lines = (i.get("text") or {}).get("lines") or []
        callouts.append({"id": i["id"], "variant": i["variant"], "start": i["start"], "dur": i["dur"], "anchor": i["anchor"],
                         "path": callout_path(i, cctx) or None, "to": i.get("to"), "radius": i.get("radius"),
                         "side": i["side"], "below": bool(i.get("below")), "lines": lines,
                         "w": i.get("w") or callout_width(lines, i["variant"]), "tone": i.get("tone")})
    hide = sorted(hide + hidden_windows(plan))  # hide-subs: per-video compositions (a presenter, an accent title)
    # presenter layers (keep-clear --matte): the WebM goes next to the rough cut, where Presenter's src points
    # (matte.py place: "<id>/<name>.webm"); before, it was copied by hand
    for k in plan.get("keep_clear", []):
        if not k.get("matte"):
            continue
        m_src = e / "matte" / f"{safe_slug(k['matte'], 'keep_clear matte', dots=True)}.webm"
        m_dst = inside(rem / "public", rem / "public" / name / m_src.name, "matte copy")
        if not m_src.exists():
            warn(f"keep_clear '{k.get('what')}': no {m_src} (matte.py cut): the presenter has no figure to show")
            continue
        md = m_dst.stat() if m_dst.exists() else None
        if not md or md.st_size != m_src.stat().st_size or abs(md.st_mtime - m_src.stat().st_mtime) > 1:
            m_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(m_src, m_dst)
            print(f"matte: {m_src.name} -> public/{name}/{m_src.name}" + (" (updated)" if md else ""))
    # the plan's keep_clear: overlay/split/window scenes (a box on screen); validate (memes, windows) and faces.py audit see them
    # and the labels of ready callouts, per 0.25 s on screen
    entries = scene_keep_entries(plan) + callout_keep_entries(e, plan)
    if entries or any(k.get("scene") or k.get("callout") for k in plan.get("keep_clear", [])):
        with editing_plan(e) as p2:
            old = [k for k in p2.get("keep_clear", []) if not (k.get("scene") or k.get("callout"))]
            sc_k, co_k = scene_keep_entries(p2), callout_keep_entries(e, p2)
            new = old + sc_k + co_k
            if new != p2.get("keep_clear", []):
                p2["keep_clear"] = new
                print(f"keep_clear: {len(sc_k)} overlay/split/window scene(s), {len({k['callout'] for k in co_k})} "
                      f"callout label(s) (for faces.py audit)")
    save_json(rem / "src" / "plans" / f"{name}.json", {"id": name, "duration": plan["duration"], "inserts": out,
                                                     **({"scenes": scenes} if scenes else {})})
    print(f"src/plans/{name}.json: {len(out)} insert(s) go into the render" + (f"; no insert (fallback): {'; '.join(skipped)}" if skipped else "")
          + (f"; {len(scenes)} scene(s)" if scenes or any(x.startswith("c") for x in sk) else "")
          + (f"; {len(callouts)} callout(s)" if callouts else "") + (f" (not ready: {', '.join(sk)})" if sk else "")
          + ("; the cover: props.cover" if cover else ""))
    if a.props:
        # props of the universal template composition: rough cut, subtitles, brand, inserts;
        # `npx remotion render <Template> ... --props=<file>`
        brand = load_json(rem / "src" / "brands" / f"{safe_slug(plan['brand'], 'the plan brand')}.json")
        if not brand:
            sys.exit(f"no src/brands/{plan['brand']}.json: run brand.py stage {plan['brand']} --remotion {a.remotion}")
        only = no_footage(plan)  # no rough cut on screen: "scenes only", "scenes + voice"
        voice = plan.get("format") == "scenes-voice"  # the narration (voice.wav) is the sound, its words the subtitles
        vid, src_v = rem / "public" / name / "video.mp4", e / "final.mp4"
        if not only and not src_v.exists():
            sys.exit(f"no {src_v}: the rough cut is not built")
        # the rough cut copy is refreshed if final.mp4 was re-cut (a different size or modification time)
        st, dt = (src_v.stat() if not only else None), (vid.stat() if vid.exists() else None)
        if not only and (a.copy_video or not dt or dt.st_size != st.st_size or abs(dt.st_mtime - st.st_mtime) > 1):
            vid.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_v, vid)
            print(f"video: {src_v} -> public/{name}/video.mp4" + (" (updated)" if dt else ""))
        if voice:
            copy_voice(e, rem, name)
        lang = plan["settings"].get("subtitles_lang")
        subs_cap = None if (only and not voice) or not lang else subtitles_in(e, lang)
        # the speech words stay in captions (scenes land on them, the render length is its duration); a translation
        # goes only to the subtitles
        props = {"video": "" if only else f"{name}/video.mp4",
                 "captions": {"duration": plan["duration"], "segments": [], "words": []} if only and not voice
                 else load_json(e / "captions.json"),
                 **({"voice": f"{name}/voice.wav"} if voice else {}),
                 **({"subtitleCaptions": subs_cap} if subs_cap else {}),
                 "brand": brand, "inserts": out,
                 "subtitles": a.subtitles or plan["settings"].get("subtitles") or brand.get("subtitles_default") or "accent",
                 "style": plan["settings"].get("style") or brand.get("style_default"),  # the current style from reel.json
                 "hideSubtitles": hide, "drift": True,
                 "hook": {"text": fin["hook"], "until": 2.4} if fin["hook"] else None, "corner": fin["corner"],
                 "endCard": {"line1": end["lines"][0], "line2": end["lines"][1] if len(end["lines"]) > 1 else None,
                             "seconds": END_CARD_S} if end.get("kind") == "card" else
                 {"line2": brand.get("tagline"), "seconds": END_CARD_S} if end.get("kind") == "sting" else None}
        cam = [] if only else camera_shots(e, plan, cap)
        if cam:
            props["camera"], props["drift"] = cam, False
            print(f"camera: {len(cam)} shot(s) from camera.json")
        import faces as fc
        top, band = subtitle_top(e, s, cam)
        fr = None if only else framed_at(e)
        if fr:
            # the framed format: ReelKit draws the window, the label and the video inside it (props.framed); the
            # field is the style's (brand.looks[style].field), else the primary color, as the kit's own field
            src = framed_source(e)
            if not src:
                sys.exit("format framed: the rough cut's size is unknown (no faces.json in source geometry, final.mp4 "
                         "unreadable): run faces.py scan, or rebuild final.mp4")
            look = ((brand.get("looks") or {}).get(str(props["style"] or "").lower()) or {})
            # a window over the whole screen is the 9:16 crop of the horizontal source: no rounded corners (the field
            # would show in the screen's corners)
            full = [int(v) for v in fr["window"]] == [0, 0, 1080, 1920]
            props["framed"] = {"window": fr["window"], "label": fr["label"], "source": list(src),
                               "radius": 0 if full else FRAMED_RADIUS,
                               "field": look.get("field") or (brand.get("colors") or {}).get("primary"),
                               **({"subtitles": "below"} if fr["subtitles_at"] == "below" else {})}
            print(f"framed: window {fr['window']}, source {src[0]}x{src[1]}"
                  + (f", label “{fr['label']}”" if fr["label"] else ", no label") + f", field {props['framed']['field']}"
                  + (", subtitles below the window" if fr["subtitles_at"] == "below" else ""))
        props["subtitlesTop"] = top
        if props["subtitles"] not in ("accent", "plate", "typewriter", "none"):
            mode = {"v2": "plate", "bar": "plate", "typewriter": "typewriter", "print": "typewriter"}.get(str(props["subtitles"]).lower())
            if not mode:
                warn(f"subtitles '{props['subtitles']}': the kit draws accent, plate and typewriter; accent is used")
            props["subtitles"] = mode or "accent"
        if not only or voice:  # faces.py audit checks the render against the band it really has
            # the kit draws at most two lines (Subtitles.tsx): the band is the mode's two-line block from the top, above
            # the UI (T4: the band said 1250-1430 while a three-line phrase reached 1455)
            h = SUB_BLOCK_H.get(props["subtitles"], band[1] - band[0])
            low = fc.H - UI_SAFE["bottom"]  # the kit's own geometry: its subtitles do not move with a project's zone
            if fr:  # the subtitle block stays inside the window's text area (the kit lifts it the same way), or with
                # subtitles_at below right under the window, on the field (the chin is above it, inside the window)
                a0, a1 = framed_sub_area(fr)[1], framed_sub_area(fr)[3]
                low = min(low, a1)
                top = a0 if fr["subtitles_at"] == "below" else max(a0, min(top, a1 - h))
                props["subtitlesTop"] = top
                if fr["subtitles_at"] == "below" and props["subtitles"] == "typewriter":
                    from brand import contrast
                    ink = ((brand.get("colors") or {}).get("speakers") or [None])[0] or (brand.get("colors") or {}).get("text_on_primary") or "#FFFFFF"
                    field = props["framed"]["field"]
                    try:
                        ratio = contrast(ink, field) if field else None
                    except (ValueError, TypeError):
                        ratio = None
                    if ratio is not None and ratio < 4.5:
                        warn(f"subtitles below the window: the typewriter text {ink} on the field {field} is {ratio:.1f}:1 "
                             f"(4.5 needed): pick a darker field (brand.looks.<style>.field) or the plate mode")
            z = (s.get("profile_rules") or {}).get("safe_zone")
            if z and fin["corner"] and not fr:  # the corner logo inside the ad's zone (the kit's default top is 236)
                props["cornerTop"] = max(CORNER_BOX[1], z[1])
            below = bool(fr) and fr["subtitles_at"] == "below"
            if z and top + h > z[3] and below:  # never lifted into the window (Codex review): the window moves up
                warn(f"subtitles below the window: the block ends at y {top + h}, past the ad safe zone of profile "
                     f"{s['profile_rules']['id']} (y {z[3]}), and lifting it would put it over the picture: end the "
                     f"window at y <= {z[3] - h - FRAMED_SUB_GAP} (reelcfg.py save edit/<id> --set window=[...]), or "
                     f"keep the subtitles inside the window")
            elif z and top + h > z[3]:  # a paid ad: the platform's caption and button cover y > the safe zone's bottom
                lifted = max(z[1], z[3] - h)
                print(f"subtitles: lifted from y {top} to {lifted} for profile {s['profile_rules']['id']} (the ad safe "
                      f"zone ends at y {z[3]}); check the chin on the render: faces.py audit")
                top = lifted
                props["subtitlesTop"] = top
            with editing_plan(e) as p2:
                p2["subtitles_band"] = [top, min(low, top + h)]
        if s.get("subtitles_shade") is not None:
            props["subtitlesShade"] = float(s["subtitles_shade"])
        props["callouts"] = callouts  # callouts (kit/Callout.tsx); an older template ignores this prop
        props["scenes"] = scenes  # designed scenes (the scene kit, SceneSpec); an older template ignores this prop
        props["sceneTone"] = s.get("scene_tone") or (s.get("brand_tone") or {}).get("scene_tone")
        if cover:
            props["cover"] = cover  # the cover is a separate still composition, not in the video's timeline
        if only and not voice:
            props["subtitles"], props["drift"] = "none", False
        elif voice:
            props["drift"] = False
        if voice_mode(s) != "on_camera":  # the kit keeps the subtitles over full scenes (off_camera); absent: on camera
            props["voiceMode"] = voice_mode(s)
        if scenes:
            print(f"scenes: {len(scenes)} in props.scenes; subtitles hidden in {len(hide)} window(s)")
        save_json(Path(a.props), props)
        print(f"template props: {a.props}")
    else:  # an agent ran stage without --props and read the plans line as "done": no props, no render
        print(f"no --props: the template props (rough cut, subtitles, brand, scenes) are NOT written, the ReelKit render "
              f"needs them: add --props {(e / 'reelkit-props.json').as_posix()}")
    # what follows the cut, recorded once the stage is through (during it end_tail() reads --sting/--card): validate
    # counts "the last 2 s" from the whole video's end. Codex review: written before the Remotion project check, a
    # failed stage left an end card that the next validate counted
    # The full choice goes into "finish" (the next stage keeps it, finish_of); the markers are what validate and the
    # profile's items read (end_tail, end_now, profile_issues)
    with editing_plan(e) as p2:
        p2["finish"] = fin
        for k, on in (("corner", fin["corner"]), ("hook", bool(fin["hook"]))):
            if on:
                p2[k] = True
            else:
                p2.pop(k, None)
        if end:
            p2["end_card"] = {"kind": end["kind"], "seconds": END_CARD_S}
        else:
            p2.pop("end_card", None)
