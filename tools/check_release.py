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

TEXT_EXT = {".md", ".json", ".txt", ".svg", ".py", ".ts", ".tsx", ".js", ".mjs", ".css"}
IMAGE_FONT_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ttf", ".otf", ".woff", ".woff2"}
JUNK = {".DS_Store", "Thumbs.db", "desktop.ini"}
LOCAL_CACHE = {"__pycache__", "node_modules"}  # git ignores them, so they never ship; the scan skips them too
# The core makes no network requests (directory policy 3.F): no network modules, no ssh/curl/wget calls.
CORE_NETWORK = re.compile(
    r"^\s*(?:import|from)\s+(?:requests|urllib|http\.client|httpx|aiohttp|socket|ftplib|smtplib|paramiko)\b"
    r"|[\"'](?:ssh|scp|curl|wget)[\"']",
    re.M,
)
MAX_TEXT = 256 * 1024
MAX_FILES = 512
CORE_FORBIDDEN = re.compile(
    r"fal\.ai|\bfal\b|\bveo\b|kling|\bltx\b|runway|sora|seedance|luma ray|pixabay|pexels|magnific|freepik"
    r"|videvo|giphy|openverse|tenor|api[_ -]?key|FAL_KEY|_API_KEY|keys\.env"
    # policy 4.B: no generative image, video, voice or music models in the core (designed scenes are drawn in code)
    r"|kokoro|elevenlabs|text[-_ ]to[-_ ]speech|\btts\b|\bsuno\b|\budio\b|midjourney|\bdall[-·. ]?e\b|stable diffusion"
    r"|\bflux\b|\bimagen\b|hyperframes tts|\bai[-‐‑–— ]generat(?:ed|ion|ing|es?)\b",
    re.I,
)
# Words about access secrets in the core: the directory's scan pairs them with any URL in the plugin and holds every
# version as "Uses a credential from the user's machine" (MCP_FORWARDS_CREDENTIAL_ENV), though the core reads none.
CORE_CREDENTIAL = re.compile(
    r"credential|secret|password|passphrase|access[_ -]?tokens?|auth[_ -]?tokens?|bearer|private[_ -]?key|\.env\b",
    re.I,
)
# The same scan holds a file that reads the environment and names a web address (other authors cleared the hold by
# keeping the two in different files): in the core, a file has one or the other.
CORE_ENV_READ = re.compile(r"os\.environ|getenv\(|process\.env|\$PWD\b|\$HOME\b|\bREELS_[A-Z_]+")
WEB_LINK = re.compile(r"https?://")
# Since 1.22 the core reads no environment variables at all, as other plugins did to clear the same hold.
CORE_READS_ENV = re.compile(r"os\.environ|os\.getenv|\bgetenv\(|process\.env")
# The portal's Validate named two kit files (2026-11-04): `${key}` in a template string read as "reads the installer's
# key" and `0${k + 1}` as "a command assembled at run time". In the core, a template does not interpolate a name that
# sounds like a secret, and does not start with digits right before `${`.
CORE_TEMPLATE = re.compile(
    r"\$\{(?!user_config\.|CLAUDE_)[^}\n]*\b(?:key|keys|token|tokens|pass\w*|secret\w*|auth\w*|pin|cred\w*|session\w*)\b[^}\n]*\}"
    r"|`\d+\$\{",
    re.I,
)
# Re-validate on 8a20682 (2026-11-04) named the next pair: "reads the installer's pass $$" in references/pitfalls.md
# ("pass `text` or `cover`") and "sends data off the machine" in remotion.config.ts (a docs link in a comment). In the
# core: no such word right before a code span, and no web link in a code file.
CORE_WORD_CODE = re.compile(
    r"\b(?:pass\w*|keys?|token\w*|pins?|session\w*|secret\w*|auth\w*|cred\w*|password\w*)[ \t:,(]{1,3}`", re.I
)
# Re-validate on c22bd3e (2026-11-04) named the next pair: "reads the installer's environment (printenv / env /
# export -p / set)" in brand.py (its subcommand "set") and "sends data off the machine: host" in callouts.md (a speaker
# label "HOST"). In the core: no such command name as a string, no word env or host.
CORE_SHELL_WORD = re.compile(r"""\b(?:env|printenv|hosts?|hostname)\b|["'](?:set|env|printenv|export -p)["']""", re.I)
# Re-validate on 05f37c7 named cut.py for "{ws:.2f}-{we:.2f}": a name ws right before a colon reads as a websocket
# address. In the core: no name ws or wss.
CORE_WS = re.compile(r"\bwss?\b")
CODE_EXT = {".py", ".ts", ".tsx", ".js", ".mjs"}
# Python's f-string is the same shape as the `${key}` template the scan named: no such name inside its braces.
CORE_FSTRING = re.compile(
    r"""\bf["'][^"'\n]*\{[^{}\n]*\b(?:key|keys|token\w*|pass\w*|pins?|session\w*|secret\w*|auth\w*|cred\w*)\b[^{}\n]*\}""",
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


def check_changelog(pdir, name, version):
    """The core must have CHANGELOG.md (the skill's "What's new" note reads it); any plugin that has one must keep
    its top entry, "## <version>", equal to plugin.json and non-empty."""
    log = pdir / "CHANGELOG.md"
    if not log.exists():
        if name == CORE:
            errors.append(f"{name}: CHANGELOG.md missing (the skill's What's new note reads it)")
        return
    text = re.sub(r"^```.*?^```[^\n]*$", "", log.read_text(encoding="utf-8"), flags=re.M | re.S)  # no code examples
    m = re.search(r"^## +v?(\S+)[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        errors.append(f"{name}: CHANGELOG.md has no '## <version>' entry")
        return
    top, body = m.group(1), m.group(2)
    if top != version:
        errors.append(f"{name}: CHANGELOG.md top entry {top!r} != plugin.json version {version!r}")
    if not re.search(r"^[-*] +\S", body, re.M):  # a top-level item, not an indented example
        errors.append(f"{name}: CHANGELOG.md entry {top!r} has no items")


def check_plugin(pdir, private_terms):
    name = pdir.name
    files = [p for p in pdir.rglob("*") if p.is_file() and not LOCAL_CACHE & set(p.parts) and p.suffix != ".pyc"]
    if len(files) > MAX_FILES:
        warnings.append(f"{name}: {len(files)} files > {MAX_FILES} (held for review)")
    manifest = pdir / ".claude-plugin" / "plugin.json"
    public_email = ""  # the support contact declared in plugin.json is public on purpose, not a leak
    if not manifest.exists():
        errors.append(f"{name}: no .claude-plugin/plugin.json")
    else:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        public_email = ((data.get("author") or {}).get("email") or "").lower()
        if data.get("name") != name:
            errors.append(f"{name}: plugin.json name {data.get('name')!r} != folder")
        for key in ("version", "description", "author", "license"):
            if key not in data:
                warnings.append(f"{name}: plugin.json has no {key}")
        check_changelog(pdir, name, data.get("version"))
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
        if ext == ".md" and "skills" in f.parts and "!`" in text:  # skill text: an exclamation mark before a backtick runs a shell command
            line = text[: text.index("!`")].count("\n") + 1
            errors.append(f"{rel}:{line}: '!' right before a backtick (Claude Code runs it as a shell command)")
        if f.name != "README.ru.md" and CYRILLIC.search(text):
            line = next(i for i, l in enumerate(text.splitlines(), 1) if CYRILLIC.search(l))
            errors.append(f"{rel}:{line}: Cyrillic text in the English tree")
        if name == CORE:
            m = CORE_FORBIDDEN.search(text)
            if m:
                line = text[: m.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: core mentions online provider/keys: {m.group(0)!r}")
            c = CORE_CREDENTIAL.search(text)
            if c:
                line = text[: c.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: core mentions access secrets (the directory holds it): {c.group(0)!r}")
            t = CORE_TEMPLATE.search(text)
            if t:
                line = text[: t.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: a template the directory reads as a secret or a command: {t.group(0)!r}")
            w = CORE_WORD_CODE.search(text)
            if w:
                line = text[: w.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: a word the directory reads as a secret right before code: {w.group(0)!r}")
            fs = CORE_FSTRING.search(text) if ext == ".py" else None
            if fs:
                line = text[: fs.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: an f-string formats a name the directory reads as a secret: {fs.group(0)[-40:]!r}")
            sw = CORE_SHELL_WORD.search(text)
            if sw:
                line = text[: sw.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: a word the directory reads as reading the environment or as a server: "
                              f"{sw.group(0)!r}")
            ws = CORE_WS.search(text)
            if ws:
                line = text[: ws.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: the name {ws.group(0)!r} (the directory reads it as a websocket address)")
            if ext in CODE_EXT and WEB_LINK.search(text):
                line = text[: WEB_LINK.search(text).start()].count("\n") + 1
                errors.append(f"{rel}:{line}: a web link in a code file (the directory reads it as sending data out)")
            reads_env = CORE_READS_ENV.search(text) if ext in CODE_EXT else None
            if reads_env:
                line = text[: reads_env.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: the core reads the environment ({reads_env.group(0)!r}): take the "
                              f"setting from it-reelsmaker.json or an argument")
            env, link = CORE_ENV_READ.search(text), WEB_LINK.search(text)
            if env and link:
                line = text[: env.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: reads the environment ({env.group(0)!r}) in a file with a web link "
                              f"(the directory holds it): keep the link in another file")
            n = CORE_NETWORK.search(text) if ext in (".py", ".ts", ".tsx", ".js", ".mjs") else None
            if n:
                line = text[: n.start()].count("\n") + 1
                errors.append(f"{rel}:{line}: network access in the core: {n.group(0).strip()!r}")
        scan = text.lower().replace(public_email, "") if public_email else text.lower()
        for term in private_terms:
            if term.lower() in scan:
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
            errors.append(f"{rel}: {lines} lines > 500 (move detail to references/)")
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
