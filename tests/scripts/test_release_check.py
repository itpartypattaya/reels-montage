"""tools/check_release.py: a private term anywhere in the public repository stops the release, not only inside plugins/."""
import subprocess
import sys

from conftest import ROOT

CHECK = ROOT / "tools" / "check_release.py"


def run_check(tmp_path, *terms):
    f = tmp_path / "terms.txt"
    f.write_text("# private terms\n" + "\n".join(terms) + "\n", encoding="utf-8")
    return subprocess.run([sys.executable, str(CHECK), "--private-terms", str(f)], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", timeout=120)


def test_private_term_outside_plugins_is_an_error(tmp_path):
    # 2026-11-17 review: brand names and clip numbers sat in tests/ on main; the check read only plugins/* and said clean.
    # Two terms that live only outside plugins/: a constant of tools/ and a helper of tests/ (only tracked files are
    # published and scanned, so the tests/ term is one in conftest.py, split here to keep it out of this file).
    helper = "def make_" + "speech"
    r = run_check(tmp_path, "CORE_FORBIDDEN", helper)
    assert r.returncode == 1, r.stdout
    assert "tools/check_release.py: private term 'CORE_FORBIDDEN'" in r.stdout
    assert f"tests/scripts/conftest.py: private term {helper!r}" in r.stdout


def test_private_term_in_a_file_name_is_an_error(tmp_path):
    # the name is published too: a term in a path is caught even when the content does not have it
    r = run_check(tmp_path, "speechlike.py")
    assert r.returncode == 1, r.stdout
    assert "tests/scripts/speechlike.py: private term 'speechlike.py' in the file name" in r.stdout


def test_clean_repository_passes_with_terms(tmp_path):
    # a term that is nowhere in the repository: the scan of every tracked file finds nothing and exits 0
    r = run_check(tmp_path, "zq-no-such-" + "term-7731")  # split: this file must not contain the term itself
    assert r.returncode == 0, r.stdout
    assert "0 errors" in r.stdout
