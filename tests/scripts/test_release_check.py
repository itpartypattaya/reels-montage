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


def fake_core(tmp_path, monkeypatch, files):
    """A core plugin with its required files and `files` ({path: bytes}), checked by check_plugin with ROOT moved."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_release_under_test", CHECK)
    cr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cr)
    root = tmp_path / "repo"
    p = root / "plugins" / cr.CORE
    (p / ".claude-plugin").mkdir(parents=True)
    (p / ".claude-plugin" / "plugin.json").write_text(
        '{"name": "%s", "version": "1.0.0", "description": "d", "author": {"name": "a"}, "license": "MIT"}' % cr.CORE,
        encoding="utf-8")
    (p / "README.md").write_text("A plugin that edits short vertical videos. " * 8, encoding="utf-8")
    (p / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (p / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.0\n\n- First release.\n", encoding="utf-8")
    for rel, data in files.items():
        (p / rel).parent.mkdir(parents=True, exist_ok=True)
        (p / rel).write_bytes(data)
    monkeypatch.setattr(cr, "ROOT", root)
    monkeypatch.setattr(cr, "PLUGINS", root / "plugins")
    cr.check_plugin(p, [])
    return cr.errors, cr.warnings


def test_a_clean_fake_core_passes(tmp_path, monkeypatch):
    errors, _ = fake_core(tmp_path, monkeypatch, {"scripts/run.py": b"print('hello')\n"})
    assert errors == []


def test_a_text_file_of_another_type_is_read_like_any_text(tmp_path, monkeypatch):
    # review 2026-11-17 #13: a .sh or .yaml file got a warning only and its text was never read
    errors, _ = fake_core(tmp_path, monkeypatch, {"scripts/setup.sh": b"curl https://pixabay.com/api\n",
                                                   "config/notes.yaml": "\u0442\u0435\u043a\u0441\u0442: 1\n".encode()})
    assert any("scripts/setup.sh" in e and "pixabay" in e for e in errors), errors
    assert any("config/notes.yaml" in e and "Cyrillic" in e for e in errors), errors


def test_a_binary_file_is_an_error(tmp_path, monkeypatch):
    errors, _ = fake_core(tmp_path, monkeypatch, {"scripts/tool.bin": b"\x00\x01\x02ELF\x00"})
    assert any("scripts/tool.bin" in e and "binary" in e for e in errors), errors


def test_a_forbidden_word_or_cyrillic_in_a_file_name_is_an_error(tmp_path, monkeypatch):
    errors, _ = fake_core(tmp_path, monkeypatch, {"scripts/pexels_search.py": b"print(1)\n",
                                                   "references/\u0437\u0430\u043c\u0435\u0442\u043a\u0438.md": b"notes\n"})
    assert any("pexels_search.py" in e and "file name" in e for e in errors), errors
    assert any("references/" in e and "Cyrillic" in e and "file name" in e for e in errors), errors
