# -*- coding: utf-8 -*-
"""The checks around the render in one command: before it, the plan check, the storyboard sheet and the text check;
after it, the faces audit of the render and a contact sheet of the finished file.

    python scripts/check.py edit/4821                          # before the render: validate + board + textcheck
    python scripts/check.py edit/4821 --render out/4821.mp4    # after it: faces.py audit + verify/sheet.png
    python scripts/check.py edit/4821 --comp Reel4821 [--shots] [--transitions]   # a per-video composition, more frames

Each step is its own script with its own report (visual_plan.py validate, board.py, textcheck.py, faces.py audit) and
runs whatever the step before it said, so one run shows every problem; then a summary line per step. Exit code 1 if
any step failed. Review 2026-10-17: validate, board, textcheck, stills, the contact sheet and the faces audit were six
commands in two places of the pipeline, and a step left out was not noticed. The board and the text check need the
props of the last export (visual_plan.py export … --props edit/<id>/reelkit-props.json) and the Remotion project;
hand stills are needed only for what the board does not show.
"""
import argparse, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import edit_dir, project_root, utf8_stdio

HERE = Path(__file__).resolve().parent
SHEET_FRAMES = 12  # 6 x 2, as the contact sheet of SKILL.md step 9
AUDIT_SKIPPED = "face audit skipped"  # faces.py audit without OpenCV or the face model: it exits 0, nothing checked
NO_GRAPHICS = "nothing to put on the sheet"  # board.py on a clip with no graphics: it passes, nothing to show (board.NOTHING)


def step(name, cmd, skipped=None, empty=None):
    """Run one check as its own script, its output passed through; -> (name, "ok" | "FAIL" | "skip" | "none"). skipped:
    the line a script prints when it could not check (review 2026-10-18: the faces audit without OpenCV or the model
    exits 0); empty: the line it prints when there is nothing to check (a clip with no graphics has no storyboard)."""
    print(f"\n=== {name}: {subprocess.list2cmdline([str(x) for x in cmd[1:]])}", flush=True)
    r = subprocess.run([str(x) for x in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout, end="", flush=True)
    if r.returncode:
        return name, "FAIL"
    if skipped and skipped in r.stdout:
        return name, "skip"
    return name, "none" if empty and empty in r.stdout else "ok"


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
                        str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def contact_sheet(render, out):
    """12 frames of the finished file in one picture: does the picture change, is the top of the head cut off, does
    text cover the mouth."""
    d = duration(render)
    if not d:
        print(f"\n=== contact sheet: {render} has no duration (not a video?)")
        return "contact sheet", "FAIL"
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n=== contact sheet: {SHEET_FRAMES} frames of {render} -> {out}", flush=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(render), "-vf",
                        f"fps={SHEET_FRAMES / d:.6f},scale=200:356,tile=6x2", "-frames:v", "1", str(out)])
    return "contact sheet", "ok" if r.returncode == 0 and out.is_file() else "FAIL"


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", help="the video folder, edit/<id>")
    ap.add_argument("--render", help="the rendered video: run the checks after the render instead")
    ap.add_argument("--props", help="the props of the last export (default: edit/<id>/reelkit-props.json)")
    ap.add_argument("--remotion", help="the Remotion project (default: it-reelsmaker.json -> remotion_dir)")
    ap.add_argument("--comp", help="a per-video composition instead of ReelKit (Reel<id>)")
    ap.add_argument("--shots", action="store_true", help="board: a frame per camera shot too")
    ap.add_argument("--transitions", action="store_true", help="board: the middle of each smooth entrance too")
    a = ap.parse_args()
    if a.render and (a.props or a.remotion or a.comp or a.shots or a.transitions):
        ap.error("--props, --remotion, --comp, --shots and --transitions belong to the checks before the render")
    project = project_root()
    e = edit_dir(a.edit, project)
    py = sys.executable
    results = []
    if a.render:
        render = Path(a.render)
        if not render.is_file():
            sys.exit(f"no render {render}")
        results.append(step("faces audit", [py, HERE / "faces.py", "audit", render, "--edit", e], skipped=AUDIT_SKIPPED))
        results.append(contact_sheet(render, e / "verify" / "sheet.png"))
    else:
        opts = sum(([f"--{k}", v] for k, v in (("props", a.props), ("remotion", a.remotion), ("comp", a.comp)) if v), [])
        results.append(step("plan check", [py, HERE / "visual_plan.py", "validate", e]))
        results.append(step("storyboard sheet", [py, HERE / "board.py", e, *opts]
                            + (["--shots"] if a.shots else []) + (["--transitions"] if a.transitions else []),
                            empty=NO_GRAPHICS))
        results.append(step("text check", [py, HERE / "textcheck.py", e, *opts]))
    print("\nsummary:")
    for name, status in results:
        print(f"  ok   {name} (no graphics in the props: nothing to show)" if status == "none" else f"  {status:<4} {name}")
    bad = [n for n, st in results if st == "FAIL"]
    skip = [n for n, st in results if st == "skip"]
    if skip:
        print(f"not checked: {', '.join(skip)} (doctor.py says what is missing): check those by eye")
    print("all checks passed" if not bad else f"failed: {', '.join(bad)}: fix them before "
          + ("showing the video" if a.render else "the full render"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
