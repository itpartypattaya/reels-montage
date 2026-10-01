"""Pre-release checks for the plugins in this repository.

Covers what Anthropic's plugin directory blocks or holds for review, plus this repo's own rules:
the core plugin never mentions online providers or API keys, and the English tree has no Cyrillic
outside README.ru.md. Run `claude plugin validate --strict` separately; this script does not replace it.

Usage:
    python tools/check_release.py [--private-terms FILE]

--private-terms: a local file (kept outside the repo) with one term per line that must not appear
anywhere in the plugins: real brand names, people, private paths.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
CORE = "it-reelsmaker"

TEXT_EXT = {".md", ".json", ".txt", ".svg"}
IMAGE_FONT_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ttf", ".otf", ".woff", ".woff2"}
JUNK = {".DS_Store", "Thumbs.db", "desktop.ini"}
MAX_TEXT = 256 * 1024
MAX_FILES = 512
CORE_FORBIDDEN = re.compile(
    r"fal\.ai|\bfal\b|\bveo\b|kling|\bltx\b|runway|sora|seedance|luma ray|pixabay|pexels|magnific|freepik"
    r"|videvo|giphy|openverse|tenor|api[_ -]?key|FAL_KEY|_API_KEY|keys\.env",
    re.I,
)
CYRILLIC = re.compile(r"[Ѐ-ӿ]")

errors, warnings = [], []


def frontmatter(text):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    return text[4:end] if end > 0 else None


def fm_value(fm, key):
    m = re.search(rf"^{key}:\s*(>-?|\|-?)?\s*\n((?:[ \t]+.*\n?)+)", fm, re.M)
    if m:
        return " ".join(line.strip() for line in m.group(2).splitlines()).strip()
    m = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
    return m.group(1).strip().strip('"') if m else None


def readme_words(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    return len(re.findall(r"\w+", text))


def check_plugin(pdir, private_terms):
    name = pdir.name
    files = [p for p in pdir.rglob("*") if p.is_file()]
    if len(files) > MAX_FILES:
        warnings.append(f"{name}: {len(files)} files > {MAX_FILES} (held for review)")
    manifest = pdir / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        errors.append(f"{name}: no .claude-plugin/plugin.json")
    else:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("name") != name:
            errors.append(f"{name}: plugin.json name {data.get('name')!r} != folder")
        for key in ("version", "description", "author", "license"):
            if key not in data:
                warnings.append(f"{name}: plugin.json has no {key}")
    readme = pdir / "README.md"
    if not readme.exists():
        errors.append(f"{name}: README.md missing")
    elif readme_words(readme.read_text(encoding="utf-8")) < 40:
        errors.append(f"{name}: README.md under 40 words outside code blocks")
    if not (pdir / "LICENSE").exists():
        errors.append(f"{name}: LICENSE missing")

    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if f.name in JUNK or "__MACOSX" in f.parts:
            errors.append(f"{rel}: OS junk file")
            continue
        ext = f.suffix.lower()
        if ext in IMAGE_FONT_EXT:
            continue
        if ext not in TEXT_EXT and f.name != "LICENSE":
            warnings.append(f"{rel}: not a text/image/font file (held for review)")
            continue
        if f.stat().st_size > MAX_TEXT:
            warnings.append(f"{rel}: {f.stat().st_size} bytes > 256 KiB (held for review)")
        text = f.read_text(encoding="utf-8")
        if ext == ".json":
            try:
                json.loads(text)
            except ValueError as e:
                errors.append(f"{rel}: invalid JSON: {e}")
        if f.name != "README.ru.md" and CYRILLIC.search(text):
            line = next(i for i, l in enumerate(text.splitlines(), 1) if CYRILLIC.search(l))
            errors.append(f"{rel}:{line}: Cyrillic text in the English tree")
        if name == CORE:
            m = CORE_FORBIDDEN.search(text)
            if m:
                line = text[: m.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: core mentions online provider/keys: {m.group(0)!r}")
        for term in private_terms:
            if term.lower() in text.lower():
                errors.append(f"{rel}: private term {term!r}")

    for skill in (pdir / "skills").glob("*/SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        rel = skill.relative_to(ROOT).as_posix()
        fm = frontmatter(text)
        if fm is None:
            errors.append(f"{rel}: no YAML front matter")
            continue
        sname = fm_value(fm, "name")
        if sname != skill.parent.name:
            errors.append(f"{rel}: name {sname!r} != folder {skill.parent.name!r}")
        desc = fm_value(fm, "description") or ""
        if not desc:
            errors.append(f"{rel}: no description")
        elif len(desc) > 1024:
            errors.append(f"{rel}: description {len(desc)} chars > 1024")
        lines = text.count("\n") + 1
        if lines > 500:
            warnings.append(f"{rel}: {lines} lines > 500 (move detail to references/)")
        for ref in re.findall(r"`(references/[\w./-]+\.md)`", text):
            if not (skill.parent / ref).exists():
                errors.append(f"{rel}: missing {ref}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private-terms", type=Path)
    args = ap.parse_args()
    terms = []
    if args.private_terms:
        terms = [t.strip() for t in args.private_terms.read_text(encoding="utf-8").splitlines() if t.strip() and not t.startswith("#")]
    for pdir in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        check_plugin(pdir, terms)
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
