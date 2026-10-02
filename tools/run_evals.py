"""Run the skill-trigger evals for a plugin in this repository.

`claude plugin eval` only reads cases from a folder inside the plugin, but the cases live in evals/<plugin>/
at the repository root, so they never ship to users or reach the directory scan. This script copies the plugin
and its cases into a temporary folder, runs the eval there and copies the results to evals/results/<plugin>/.

Each case is a full Claude run on your own account, so a pass costs tokens and minutes: run it before a
release, not on every edit.

Usage:
    python tools/run_evals.py [--plugin it-reelsmaker] [--model sonnet] [--case GLOB] [--runs N] [-j N]
"""
import argparse
import datetime
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plugin", default="it-reelsmaker")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--case", help="only cases whose name matches this glob")
    ap.add_argument("--runs", type=int, help="runs per case (default: the case's own runs)")
    ap.add_argument("-j", "--concurrency", type=int, default=2)
    a = ap.parse_args()

    plugin = ROOT / "plugins" / a.plugin
    cases = ROOT / "evals" / a.plugin
    if not (plugin / ".claude-plugin" / "plugin.json").exists():
        sys.exit(f"no plugin at {plugin}")
    if not cases.is_dir():
        sys.exit(f"no eval cases at {cases}")

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "evals" / "results" / a.plugin / stamp
    with tempfile.TemporaryDirectory(prefix="plugin-eval-") as tmp:
        work = Path(tmp) / a.plugin
        shutil.copytree(plugin, work)
        shutil.copytree(cases, work / "evals", ignore=shutil.ignore_patterns("results"))
        cmd = ["claude", "plugin", "eval", str(work), "--ablation", "none", "--model", a.model, "--no-publish",
               "--trust-plugin", "-j", str(a.concurrency), "--output-dir", str(out), "--report", str(out / "report.html"),
               "--json", str(out / "result.json")]
        if a.case:
            cmd += ["--case", a.case]
        if a.runs:
            cmd += ["--runs", str(a.runs)]
        out.mkdir(parents=True, exist_ok=True)
        print("running:", " ".join(cmd))
        code = subprocess.run(cmd).returncode
    print(f"results: {out} (exit {code})")
    sys.exit(code)


if __name__ == "__main__":
    main()
