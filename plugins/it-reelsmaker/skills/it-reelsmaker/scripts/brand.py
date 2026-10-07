# -*- coding: utf-8 -*-
"""Brand profiles: save several brands, each with its own design rules, and pick one before editing.

A brand is a folder <project>/brands/<slug>/ with two files (a personal copy of the skill may also keep brands/ next
to its scripts folder):
  brand.json - the machine part: colors by role, fonts, logos, LUT, styles, bans, insert defaults, who approves;
  rules.md   - the brand's design rules in words; grows with revisions (`rule`).

    python scripts/brand.py list [--json]                          # saved brands, most recently used first
    python scripts/brand.py show acme                              # profile + contrast + which files were found
    python scripts/brand.py new --name "Acme" --colors "#0B3D2E,#F2C14E" [--fonts "Montserrat,Inter"]
                       [--slug acme] [--logo logo.png mark.png] [--scan <folder> ...] [--where project|skill]
                       [--approver "..."] [--account business] [--tone premium|warm|expert|story|tech|friendly|drive|bold]
                       [--motion calm|lively|energetic]
    python scripts/brand.py logo acme logo-white.png [--role on_dark]    # logo -> brands/<slug>/assets/ + role in brand.json
    python scripts/brand.py rule acme "Cards only on the left, likes on the right"   # append a design rule to rules.md
    python scripts/brand.py set acme colors.accent=#19B8BB inserts.use_broll=false
    python scripts/brand.py tone acme friendly [--set memes.max=1 flash_max=1] [--reset]   # brand tone: preset + field overrides
    python scripts/brand.py use acme --edit edit/4821              # brand into edit/<id>/reel.json + mark as used
    python scripts/brand.py export acme --remotion reels           # src/brands/<slug>.json + logos in public/brands/<slug>/

Logos, fonts and LUTs live inside the brand: brands/<slug>/assets/ (new and logo copy them there), so a brand moves
between projects as one folder. Logo roles: on_dark - light (for a dark background and over video), on_light - dark,
mark_on_dark / mark_on_light - a compact mark for the corner; the role is detected from brightness and proportions.
The brand tone (brand.json -> tone: {"preset", "overrides"}) is a preset from assets/reel-defaults.json -> brand_tones:
premium "Premium, restrained", warm "Warm, caring", expert "Expert, calm", story "Atmospheric, story-led", tech "Tech,
precise", friendly "Lively, friendly", drive "Energetic, sales-driven", bold "Bold, with humor". It sets the defaults
(intensity, memes, scene tone) and the ceilings for visual_plan.py validate (memes, transitions, flash/whip, full
scenes). Without --tone a new brand gets expert marked "unconfirmed": ask the brand owner for the tone.
Explicit profile fields (motion, memes_policy, inserts) override the preset.
The minimum for a new brand is a name and 1-3 colors. The script looks for the rest (logos, fonts, brand book, LUT,
sample videos) in the project folder (<slug>-brand/, brand/, brands/<slug>/) and in --scan; whatever is missing gets a
safe default, and the script says what it filled in.
New brands are written to the project (--where project, the default). The plugin folder is replaced on update, so
--where skill works only in a personal copy of the skill that already has a brands/ folder next to its scripts folder.
"""
import argparse, contextlib, datetime, hashlib, json, re, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reels_common import (BRAND_SCHEMA, SKILL, TONE_PRESETS, migrate_brand, brand_file, brand_roots, editing_json, find_brand, inside, list_brands,
                          parse_value, project_root, safe_slug, save_json, save_text, tone_rules, tone_summary, utf8_stdio, warn)

TODAY = datetime.date.today().isoformat()
DEFAULT_FONTS = {"heading": {"family": "Manrope", "weights": [600, 800], "source": "google"},
                 "body": {"family": "Inter", "weights": [500, 600, 700, 800], "source": "google"}}


def _cp(codes):
    """Text given as hex Unicode code points separated by spaces (keeps this file free of Cyrillic letters)."""
    return "".join(chr(int(c, 16)) for c in codes.split())


# The Russian lowercase alphabet (with yo after ye) -> Latin: slugs for brand names written in Cyrillic
TR = dict(zip(_cp("430 431 432 433 434 435 451 436 437 438 439 43a 43b 43c 43d 43e 43f 440 441 442 443 444 445 446 447 "
                  "448 449 44a 44b 44c 44d 44e 44f"),
              "a b v g d e e zh z i y k l m n o p r s t u f h ts ch sh sch  y  e yu ya".split(" ")))

# The same words in Russian file names, as code points: logo, mark, emblem, icon, guide, brand, book, avatar
RU = {k: _cp(v) for k, v in {"logo": "43b 43e 433 43e", "mark": "437 43d 430 43a", "emblem": "44d 43c 431 43b 435 43c",
                             "icon": "438 43a 43e 43d 43a", "guide": "433 430 439 434", "brand": "431 440 435 43d 434",
                             "book": "431 443 43a", "avatar": "430 432 430 442 430 440"}.items()}


def slugify(name):
    s = "".join(TR.get(c, c) for c in name.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:48].strip("-") or "brand"


# --- Color ---------------------------------------------------------------------------------------------

def norm_hex(c):
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        sys.exit(f"not a color: {c!r} (expected #RRGGBB)")
    return "#" + c.upper()


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def lum(h):
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def vivid(h):
    r, g, b = rgb(h)
    mx, mn = max(r, g, b), min(r, g, b)
    return (mx - mn) * mx  # saturation x brightness


def best_text(bg, options):
    """The first brand color from the list that reads well (contrast >= 4.5), otherwise the most contrasting one."""
    ok = [c for c in options if contrast(bg, c) >= 4.5]
    return ok[0] if ok else max(options, key=lambda c: contrast(bg, c))


def assign_roles(colors):
    """1-N colors -> primary (dark base), accent (the most vivid), light (light surface), text on them."""
    cs = list(dict.fromkeys(colors))
    derived = []
    by_l = sorted(cs, key=lum)
    primary = by_l[0] if lum(by_l[0]) < 0.25 else None
    rest = [c for c in cs if c != primary]
    light = next((c for c in reversed(by_l) if lum(c) > 0.75 and c != primary), None)
    cand = [c for c in rest if c != light] or rest
    accent = max(cand, key=vivid) if cand else None
    if primary is None:
        primary = "#111418"
        derived.append("primary: no dark color, using #111418 (near-black)")
    if accent is None:
        accent = light or "#FFFFFF"
        derived.append(f"accent: no vivid color, using {accent}")
    if light is None:
        light = "#FFFFFF"
        derived.append("light: no light color, using #FFFFFF")
    extra = {f"c{i + 1}": c for i, c in enumerate(c for c in cs if c not in (primary, accent, light))}
    roles = {"primary": primary, "accent": accent, "light": light,
             "text_on_primary": best_text(primary, [light, "#FFFFFF", "#000000"]),
             "text_on_accent": best_text(accent, [primary, "#000000", "#FFFFFF", light]), "extra": extra}
    return roles, derived


def color_checks(c):
    out = []
    pairs = [("text_on_primary", "primary", 4.5), ("text_on_accent", "accent", 4.5), ("accent", "primary", 3.0)]
    for a, b, need in pairs:
        if c.get(a) and c.get(b):
            k = contrast(c[a], c[b])
            out.append((f"{a} on {b}", k, need, k >= need))
    return out


# --- Finding brand materials ---------------------------------------------------------------------------

LOGO_RE = re.compile("|".join(["logo", "logotip", RU["logo"], "mark", RU["mark"], "emblem", RU["emblem"], "icon",
                               RU["icon"], "sign"]), re.I)
BOOK_RE = re.compile("|".join(["brand", "guide", RU["guide"], RU["brand"], "book", RU["book"], "style"]), re.I)


def scan(dirs, depth=3):
    found = {"logos": [], "fonts": [], "brandbook": [], "lut": [], "examples": []}
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if not p.is_file() or len(p.relative_to(d).parts) > depth:
                continue
            ext, name = p.suffix.lower(), p.name
            if ext in (".ttf", ".otf", ".woff", ".woff2"):
                found["fonts"].append(p)
            elif ext == ".cube" or (ext == ".png" and re.search(r"hald|lut", name, re.I)):
                found["lut"].append(p)
            elif ext in (".png", ".svg", ".webp", ".jpg", ".jpeg") and (LOGO_RE.search(name) or d.name.endswith("-brand")):
                found["logos"].append(p)
            elif ext == ".pdf" and (BOOK_RE.search(name) or d.name.endswith("-brand")):
                found["brandbook"].append(p)
            elif ext in (".mp4", ".mov"):
                found["examples"].append(p)
    return found


def logo_tone(p):
    """A light logo -> for a dark background (on_dark), a dark one -> for a light background (on_light). Needs Pillow."""
    try:
        from PIL import Image
        im = Image.open(p).convert("RGBA")
        im.thumbnail((200, 200))
        px = [(r, g, b) for r, g, b, a in im.getdata() if a > 128]
        if not px:
            return None
        L = sum(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in px) / len(px) / 255
        return "on_dark" if L > 0.6 else "on_light"
    except Exception:
        return None


# --- Commands --------------------------------------------------------------------------------------------

def where_of(d):
    return "skill" if Path(d).resolve().is_relative_to(SKILL) else "project"


def tone_of(b):
    """The tone preset from the profile; none -> "none->expert" (that is how load_config reads it; it is written on
    the first edit)."""
    t = b.get("tone") if isinstance(b.get("tone"), dict) else {}
    return t.get("preset") or "none->expert"


def cmd_list(a):
    items = list_brands()
    items.sort(key=lambda x: (x[2].get("last_used") or "", x[0]), reverse=True)
    if a.json:
        print(json.dumps([{"slug": s, "name": b.get("name"), "primary": b.get("colors", {}).get("primary"),
                           "accent": b.get("colors", {}).get("accent"), "style": (b.get("styles") or {}).get("default"),
                           "approver": b.get("approver"), "last_used": b.get("last_used"), "where": where_of(d),
                           "tone": tone_of(b), "schema": b.get("schema") or 1,
                           "description": b.get("description")} for s, d, b in items], ensure_ascii=False, indent=1))
        return
    if not items:
        print("no saved brands: brand.py new --name ... --colors ...")
        return
    print(f"{'slug':<12} {'name':<22} {'tone':<9} {'primary':<8} {'accent':<8} {'style':<8} {'last used':<11} where")
    for s, d, b in items:
        c = b.get("colors", {})
        print(f"{s:<12} {b.get('name', '')[:22]:<22} {tone_of(b):<9} {c.get('primary', ''):<8} {c.get('accent', ''):<8} "
              f"{(b.get('styles') or {}).get('default') or '-':<8} {b.get('last_used') or '-':<11} {where_of(d)}")


def cmd_show(a):
    d, b = find_brand(a.slug)
    if not b:
        sys.exit(f"no brand {a.slug}; available: {', '.join(s for s, _, _ in list_brands())}")
    if a.json:
        print(json.dumps(b, ensure_ascii=False, indent=1))
        return
    c = b.get("colors", {})
    print(f"{b.get('name')} ({a.slug}), {where_of(d)}: {d}")
    print(f"  {b.get('description', '')}")
    print("  colors: " + ", ".join(f"{k} {v}" for k, v in c.items() if k != "extra") +
          ("; extra: " + ", ".join(f"{k} {v}" for k, v in c.get("extra", {}).items()) if c.get("extra") else ""))
    for name, k, need, ok in color_checks(c):
        print(f"  contrast {name}: {k} {'ok' if ok else f'< {need}: POOR readability'}")
    f = b.get("fonts", {})
    print("  fonts: " + ", ".join(f"{r} {v.get('family')} ({v.get('source')})" for r, v in f.items()))
    for k, v in (b.get("logos") or {}).items():
        p = brand_file(v, d)
        print(f"  logo {k}: {v} {'✓' if p else '✗ NOT FOUND'}")
    lut = b.get("lut") or {}
    if lut.get("hald"):
        print(f"  LUT: {lut['hald']} {'✓' if brand_file(lut['hald'], d) else '✗'} (strength {lut.get('strength', 1.0)})")
    st = b.get("styles") or {}
    print(f"  default style: {st.get('default')}; allowed: {', '.join(st.get('allowed', []))}")
    rules, note = tone_rules(b, slug=a.slug)
    print(f"  default subtitles: {b.get('subtitles_default')}; motion: {rules.get('motion')}"
          + (" (set explicitly in the profile)" if b.get("motion") else f" (from tone {rules['preset']})"))
    print(f"  brand tone: {tone_summary(rules)}")
    m = rules.get("memes") or {}
    print(f"    validate ceilings: memes <= {m.get('max', 0) if m.get('allowed') is not False else 0}"
          f" (and <= the intensity budget), size <= {m.get('size_max') or '-'}, full-frame "
          f"{'allowed' if m.get('cutaway') else 'not allowed'}; transitions {', '.join(rules.get('transitions') or [])}; "
          f"flash <= {rules.get('flash_max')}, whip <= {rules.get('whip_max')}; full scenes <= {rules.get('full_scenes_max')}; "
          f"scene tones {', '.join(rules.get('scene_tones') or [])}")
    print(f"    defaults: intensity {rules.get('intensity')}, memes {'on' if m.get('default') else 'off'}, "
          f"scene tone {rules.get('scene_tone')}, sounds {rules.get('sfx')}; overshoot {'yes' if rules.get('overshoot') else 'no'}, "
          f"shake {'yes' if rules.get('shake') else 'no'}")
    if note:
        print(f"  ⚠ {note}")
    print(f"  approves: {b.get('approver')}; account: {b.get('account')}; memes: {b.get('memes_policy')}")
    if b.get("inserts"):
        print("  brand insert defaults: " + ", ".join(f"{k}={v}" for k, v in b["inserts"].items()))
    if b.get("forbidden_imagery"):
        print("  not allowed in the frame: " + ", ".join(b["forbidden_imagery"]))
    shown = set()
    for k, label in (("rules", "rules"), ("guide", "video guide"), ("cta_library", "CTA library")):
        if b.get(k):
            p = brand_file(b[k], d)
            print(f"  {label}: {p or b[k] + ' ✗'}")
            if p:
                shown.add(Path(p).resolve())
    others = sorted(p for p in Path(d).glob("*.md") if p.resolve() not in shown)
    if others:
        print("  other brand documents: " + ", ".join(p.name for p in others) + " (linked from rules.md)")
    if not b.get("guide") or not b.get("cta_library"):
        print("  the brand's own video guide and CTA library: guide.md / cta.md in the brand folder, set in brand.json "
              "-> guide / cta_library")
    print(f"  last used: {b.get('last_used') or '-'}; profile updated: {b.get('updated')}")


RULES_TMPL = """# Brand design rules: {name}

> Profile: `brand.json` next to this file. Here are the rules in words: what is allowed, what is not, how the brand looks in Reels.
> The agent reads this file before doing graphics (steps 7-8) and appends rules from revisions here: `brand.py rule {slug} "..."`.

## Basics
- Colors: primary {primary}, accent {accent} (one accent color per video), light {light}.
- Fonts: headings {heading}, body text and subtitles {body}.{derived}
- Source: {source}.

## On-screen style
- Default style: “Marker”: {text_on_accent} text on a {accent} marker bar; subtitles “Accent”.
- Logo: {logo_note}.

## Voice and bans
- (to fill in: tone, forbidden imagery, words the brand does not use)

## Rules from revisions
<!-- revisions: brand.py rule adds dated rules at the end of this section; the heading may be in any language -->
"""

REVISIONS_MARK = "<!-- revisions"
REVISIONS_HEAD = "## Rules from revisions"


def add_rule(text, line):
    """Add a rule line at the end of the revisions section: the one marked with <!-- revisions ... --> (any heading
    language), else the "## Rules from revisions" heading, else a new section at the end of the file."""
    lines = text.rstrip("\n").split("\n")
    start = next((k for k, l in enumerate(lines) if l.strip().startswith(REVISIONS_MARK)), None)
    if start is None:
        start = next((k for k, l in enumerate(lines) if l.strip() == REVISIONS_HEAD), None)
    if start is None:
        lines += ["", REVISIONS_HEAD, line]
        return "\n".join(lines) + "\n"
    end = next((k for k in range(start + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, line)
    return "\n".join(lines) + "\n"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def store(bdir, src):
    """A copy of the file in brands/<slug>/assets/ -> the path for brand.json ("assets/<name>"). The same file (by
    sha256) is not duplicated; a different file with the same name becomes <name>-2, -3 ...; assets already written
    are never replaced."""
    src = Path(src)
    adir = Path(bdir) / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    digest = None
    for n in range(1, 1000):
        dst = adir / (src.name if n == 1 else f"{src.stem}-{n}{src.suffix}")
        if not dst.exists():
            shutil.copy2(src, dst)
            return f"assets/{dst.name}"
        if dst.resolve() == src.resolve():
            return f"assets/{dst.name}"
        digest = digest or sha256(src)
        if dst.stat().st_size == src.stat().st_size and sha256(dst) == digest:
            return f"assets/{dst.name}"
    sys.exit(f"too many files named {src.name} in {adir}")


# --- Fonts: family and style from the file name (no fontTools needed) -------------------------------------

STYLE_PART = re.compile(r"(?:extra|ultra|semi|demi|bold|light|regular|medium|thin|hairline|black|heavy|book|normal|italic|oblique|"
                        r"it|variablefont|variable|vf|wght|opsz|wdth|\d+(?:pt)?)+", re.I)
STYLE_TAIL = re.compile(r"(.+?)(?:(?:Extra|Ultra|Semi|Demi)?(?:Bold|Light)|Regular|Medium|Thin|Hairline|Black|Heavy|Italic)+$")


def font_meta(p):
    """(family, weight, italic) from the file name: Montserrat-SemiBoldItalic -> (Montserrat, 600, True).
    Weight and italic use the same words, in the same order, as the font loader of the Remotion template."""
    stem = Path(p).stem
    parts = [x for x in re.split(r"[-_ ]+", stem) if x]
    fam = []
    for x in parts:
        if fam and STYLE_PART.fullmatch(x):
            break
        fam.append(x)
    family = " ".join(fam) or stem
    m = STYLE_TAIL.match(family)
    if m and len(fam) == 1:  # MontserratBold: no separator
        family = m.group(1)
    w = (900 if re.search(r"black|heavy|900", stem, re.I) else 800 if re.search(r"(?:extra|ultra).?bold|800", stem, re.I)
         else 600 if re.search(r"(?:semi|demi).?bold|600", stem, re.I) else 700 if re.search(r"bold|700", stem, re.I)
         else 500 if re.search(r"medium|500", stem, re.I) else 200 if re.search(r"(?:extra|ultra).?light|200", stem, re.I)
         else 100 if re.search(r"thin|hairline|100", stem, re.I) else 300 if re.search(r"light|300", stem, re.I) else 400)
    italic = bool(re.search(r"italic|oblique", stem, re.I) or re.search(r"[-_ ]it$", stem, re.I))
    return family, w, italic


def font_families(paths):
    """{family: {"files": [...], "weights": [...], "italic": [...]}}. Italic is a separate list (fonts.<role>.italic;
    the font loader registers it as style: italic). A repeated upright weight within a family is skipped."""
    fams = {}
    for p in sorted(paths, key=lambda q: Path(q).name.lower()):
        fam, w, it = font_meta(p)
        g = fams.setdefault(fam, {"files": [], "weights": [], "italic": []})
        if it:
            g["italic"].append(Path(p).as_posix())
        elif w in g["weights"]:
            warn(f"font {Path(p).name}: family {fam} already has weight {w} ({g['files'][g['weights'].index(w)]}), skipped")
        else:
            g["files"].append(Path(p).as_posix())
            g["weights"].append(w)
    return fams


def logo_role(p, taken=None, role=None):
    """Logo role: on_dark (light, for a dark background / over video), on_light (dark), mark_*: a compact mark."""
    if not role or role == "auto":
        tone = logo_tone(p) if Path(p).suffix.lower() != ".svg" else None
        mark = bool(re.search("|".join(["mark", RU["mark"], "emblem", RU["emblem"], "icon", RU["icon"], "avatar",
                                        RU["avatar"]]), Path(p).name, re.I))
        if not mark:
            try:
                from PIL import Image
                w, h = Image.open(p).size
                mark = 0.75 <= w / h <= 1.33
            except Exception:
                pass
        role = ("mark_" if mark else "") + (tone or "file")
    if taken is not None and role in taken:
        role = f"{role}_{len(taken)}"
    return role


@contextlib.contextmanager
def editing_brand(slug):
    """The brand profile under a lock: read it again, change it, write it atomically (parallel sessions)."""
    d, b = find_brand(slug)
    if not b:
        sys.exit(f"no brand {slug}; available: {', '.join(s for s, _, _ in list_brands())}")
    shutil.copy2(d / "brand.json", d / "brand.json.bak")  # a copy before the edit (replaces the previous .bak)
    with editing_json(d / "brand.json", {}) as b:
        for n in migrate_brand(b):  # an older profile is brought up to date on its first edit
            print(f"{slug}: {n}")
        yield d, b
        b["updated"] = TODAY


def cmd_logo(a):
    for f in a.files:
        if not Path(f).is_file():
            sys.exit(f"no file {f}")
    with editing_brand(a.slug) as (d, b):
        logos = b.setdefault("logos", {})
        for f in a.files:
            p = Path(f)
            role = logo_role(p, None if a.role not in (None, "auto") else logos, a.role)
            if role in logos and a.role not in (None, "auto"):
                warn(f"{a.slug}: logo {role} replaced (was {logos[role]}, the file stays in assets/)")
            logos[role] = store(d, p)
            print(f"{a.slug}: logos.{role} = {logos[role]}")
    print("for Remotion: brand.py export " + a.slug + " --remotion <Remotion project>")


def cmd_new(a):
    project = project_root()
    slug = safe_slug(a.slug or slugify(a.name), "--slug")
    if a.where == "skill" and not (SKILL / "brands").is_dir():
        sys.exit(f"--where skill writes into the skill folder, and that works only in a personal copy of the skill "
                 f"that already has {SKILL / 'brands'}; the plugin folder is replaced on update. Use --where project "
                 f"(the default): {project / 'brands'}")
    root = (project / "brands") if a.where == "project" else (SKILL / "brands")
    bdir = inside(root, root / slug, "brand folder")
    if (bdir / "brand.json").exists() and not a.force:
        sys.exit(f"brand {slug} already exists: {bdir} (--force overwrites brand.json, rules.md stays)")
    colors = [norm_hex(c) for c in re.split(r"[,\s;]+", a.colors) if c.strip()]
    if not colors:
        sys.exit("at least one color is needed")
    roles, derived = assign_roles(colors)
    dirs = [project / f"{slug}-brand", project / "brand", project / "brands" / slug, *[Path(s) for s in a.scan or []]]
    found = scan(dirs)
    existed = [d for d in dirs if Path(d).is_dir()]

    def relp(p):
        try:
            return Path(p).resolve().relative_to(project).as_posix()
        except ValueError:
            return str(Path(p).resolve())

    # logos, fonts and LUTs are copied into brands/<slug>/assets/: the brand is self-contained and moves between projects
    bdir.mkdir(parents=True, exist_ok=True)
    logos = {}
    for p in [Path(x) for x in a.logo or []] + sorted(found["logos"], key=lambda x: len(x.name)):
        if not p.is_file():
            warn(f"no logo file {p}")
            continue
        key = logo_role(p, logos)
        logos[key] = store(bdir, p)
    found["fonts"] = [Path(store(bdir, p)) for p in found["fonts"]]
    found["lut"] = [Path(store(bdir, p)) for p in found["lut"]]
    fonts = json.loads(json.dumps(DEFAULT_FONTS))
    font_note, fams = "", None
    if a.fonts:
        names = [x.strip() for x in a.fonts.split(",") if x.strip()]
        fonts["heading"] = {"family": names[0], "weights": [600, 700, 800], "source": "google"}
        fonts["body"] = {"family": names[-1], "weights": [500, 600, 700], "source": "google"}
        font_note = " Check that these Google Fonts families cover the script of the brand's language."
    elif found["fonts"]:
        fams = font_families(found["fonts"])
        usable = {k: v for k, v in fams.items() if v["files"]}
        # headings: the family with the boldest weight; body: the next one by number of weights; one family -> body Inter
        order = sorted(usable, key=lambda k: (-max(usable[k]["weights"]), -len(usable[k]["weights"]), k))
        if order:
            h = order[0]
            fonts["heading"] = {"family": h, "source": "local", "weights": sorted(usable[h]["weights"]), "files": usable[h]["files"],
                                "italic": usable[h]["italic"]}
            rest = sorted(order[1:], key=lambda k: (-len(usable[k]["weights"]), k))
            if rest:
                fonts["body"] = {"family": rest[0], "source": "local", "weights": sorted(usable[rest[0]]["weights"]),
                                 "files": usable[rest[0]]["files"], "italic": usable[rest[0]]["italic"]}
        font_note = (f" Fonts found: " + "; ".join(f"{k} ({', '.join(map(str, sorted(v['weights']))) or 'italic only'})"
                                                   for k, v in fams.items())
                     + f"; headings {fonts['heading']['family']}, body text and subtitles {fonts['body']['family']}."
                     + (" Italic is in fonts.<role>.italic." if any(v["italic"] for v in fams.values()) else "")
                     + (f" To change: brand.py set {slug} fonts.heading.family=... fonts.heading.files=[...] (all families are in fonts_found)." if len(fams) > 1 else ""))
    else:
        font_note = " No brand fonts found: using Manrope + Inter (they cover Latin and Cyrillic)."
    lut = None
    hald = [p for p in found["lut"] if p.suffix.lower() == ".png"]
    cube = [p for p in found["lut"] if p.suffix.lower() == ".cube"]
    if hald or cube:
        lut = {"hald": hald[0].as_posix() if hald else None, "cube": cube[0].as_posix() if cube else None, "strength": 0.7}
    brand = {
        "schema": BRAND_SCHEMA, "slug": slug, "name": a.name, "description": a.description or "", "language": a.language,
        "colors": roles, "fonts": fonts, "logos": logos, "lut": lut, "tagline": a.tagline or "",
        "guide": None, "rules": "rules.md",
        "styles": {"default": "marker", "allowed": ["marker", "brand", "minimal", "editorial", "bold"]},
        "subtitles_default": "accent", "motion": a.motion,  # None: motion comes from the brand tone
        "tone": {"preset": a.tone} if a.tone else {"preset": "expert", "unconfirmed": True},
        "voice": "", "forbidden_imagery": [], "forbidden_imagery_en": [],
        "cta_library": None, "asset_verdicts": None,
        "approver": a.approver or "brand owner (to confirm)", "account": a.account,
        "music_policy": "do not burn in without a commercial license; pick the track in the app when publishing",
        "memes_policy": "strict" if a.account == "business" else "normal",
        "inserts": {}, "brandbook": [relp(p) for p in found["brandbook"]],
        "fonts_found": fams,
        "examples": [relp(p) for p in found["examples"][:10]],
        "derived": derived, "created": TODAY, "updated": TODAY, "last_used": None,
    }
    save_json(bdir / "brand.json", brand)
    rules = bdir / "rules.md"
    if not rules.exists():
        rules.write_text(RULES_TMPL.format(
            name=a.name, slug=slug, primary=roles["primary"], accent=roles["accent"], light=roles["light"],
            text_on_accent=roles["text_on_accent"], heading=fonts["heading"]["family"], body=fonts["body"]["family"],
            derived=("\n- Filled in automatically: " + "; ".join(derived)) if derived else "",
            source=a.source or "name and colors from the person" + (f", materials: {', '.join(str(d) for d in existed)}" if existed else ""),
            logo_note=("available: " + ", ".join(logos)) if logos else "no file: the brand name is typeset on the card"),
            encoding="utf-8")
    print(f"saved brand {a.name} -> {bdir}")
    print(f"  color roles: primary {roles['primary']}, accent {roles['accent']}, light {roles['light']}, "
          f"text on primary {roles['text_on_primary']}, on accent {roles['text_on_accent']}")
    for line in derived:
        print("  filled in: " + line)
    for name, k, need, ok in color_checks(roles):
        if not ok:
            warn(f"contrast {name} {k} < {need}: the text will read poorly; check it on a still frame")
    print(f"  fonts: {fonts['heading']['family']} / {fonts['body']['family']}.{font_note}")
    print(f"  logos: {', '.join(f'{k}={v}' for k, v in logos.items()) or 'not found'}")
    print(f"  brand book: {', '.join(brand['brandbook']) or 'none'}; LUT: {'yes' if lut else 'no'}; "
          f"sample videos: {len(brand['examples'])}")
    print(f"  design rules: {rules}; add the voice and bans if they are known")
    trules, _ = tone_rules(brand, slug=slug)
    print(f"  brand tone: {tone_summary(trules)}")
    if not a.tone:
        warn(f"the brand tone is not set: saved as expert, marked \"unconfirmed\". Ask the brand owner "
             f"(premium / warm / expert / story / tech / friendly / drive / bold) and save it: brand.py tone {slug} <preset>")


def cmd_rule(a):
    with editing_brand(a.slug) as (d, b):  # the profile lock also covers rules.md: two sessions won't overwrite each other's rules
        p = inside(d, d / (b.get("rules") or "rules.md"), "rules file")
        text = p.read_text(encoding="utf-8") if p.exists() else f"# Brand design rules: {b.get('name')}\n"
        # an owner decision with its reason and scope (references/playbook.md): a disliked result is traced to it later
        extra = "".join(f" {k}: {v.strip()}." for k, v in (("Applies to", a.scope), ("Why", a.why)) if v and v.strip())
        base = a.text.strip()
        if extra and base[-1:] not in ".!?…":
            base += "."
        save_text(p, add_rule(text, f"- {TODAY}: {base}{extra}"))
    print(f"rule added to {p}")


def set_path(obj, path, value):
    keys = path.split(".")
    for k in keys[:-1]:
        obj = obj.setdefault(k, {})
    obj[keys[-1]] = value


def cmd_set(a):
    for it in a.pairs:
        if "=" not in it:
            sys.exit(f"expected key=value, got: {it}")
        if it.split("=", 1)[0].strip() == "slug":
            sys.exit("slug can't be changed with set: it is the name of the brand folder")
    with editing_brand(a.slug) as (d, b):
        for it in a.pairs:
            k, v = it.split("=", 1)
            val = parse_value(v)
            if isinstance(val, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", val) and k.startswith("colors."):
                val = norm_hex(val)
            set_path(b, k.strip(), val)
            print(f"{a.slug}: {k} = {val!r}")


def cmd_tone(a):
    """Change the brand tone preset and/or override fields of the preset (tone.overrides)."""
    from reels_common import load_defaults
    tones = (load_defaults() or {}).get("brand_tones") or {}
    base = tones.get(a.preset) or {}
    sets = {}
    for it in a.set or []:
        if "=" not in it:
            sys.exit(f"--set expects key=value, got: {it}")
        k, v = (x.strip() for x in it.split("=", 1))
        head = k.split(".")[0]
        if head not in base or head in ("label", "for"):
            sys.exit(f"no tone field {k!r}; available: " + ", ".join(x for x in base if x not in ("label", "for")))
        ref = base
        for part in k.split("."):  # the value type follows the preset field: "1" in flash_max is a number, not true
            ref = ref.get(part) if isinstance(ref, dict) else None
        if isinstance(ref, (int, float)) and not isinstance(ref, bool):
            try:
                sets[k] = int(v) if re.fullmatch(r"-?\d+", v) else float(v)
            except ValueError:
                sys.exit(f"{k}: a number is needed, got {v!r}")
        else:
            sets[k] = parse_value(v)
    with editing_brand(a.slug) as (d, b):
        t = b.get("tone") if isinstance(b.get("tone"), dict) else {}
        old = t.get("preset")
        over = {} if a.reset else dict(t.get("overrides") or {})
        for k, v in sets.items():
            set_path(over, k, v)
        b["tone"] = {"preset": a.preset, **({"overrides": over} if over else {})}
        rules, _ = tone_rules(b, slug=a.slug)
    print(f"{a.slug}: tone {old or '-'} -> {a.preset}" + (f"; overridden: {json.dumps(over, ensure_ascii=False)}" if over else ""))
    if over and not sets and old != a.preset:
        print("  the previous tone's overrides are kept (--reset removes them)")
    print(f"  {tone_summary(rules)}")
    if b.get("motion") and b["motion"] != base.get("motion"):
        print(f"  motion is set explicitly in the profile: {b['motion']} (overrides the preset's {base.get('motion')}; "
              f"to remove: brand.py set {a.slug} motion=null)")
    print(f"for Remotion: brand.py export {a.slug} --remotion <Remotion project>")


def cmd_use(a):
    from reels_common import edit_dir
    d, b = find_brand(a.slug)
    if not b:
        sys.exit(f"no brand {a.slug}; available: {', '.join(s for s, _, _ in list_brands())}")
    e = edit_dir(a.edit, create=True)  # step 0 of a new video: the edit/<id> folder may not exist yet
    with editing_json(e / "reel.json", {}) as reel:
        reel["brand"] = a.slug
    with editing_json(d / "brand.json", {}) as b:  # last_used without touching updated: the profile did not change
        b["last_used"] = TODAY
    print(f"{e / 'reel.json'}: brand = {a.slug}")
    from visual_plan import refresh_plan
    if refresh_plan(e):
        print("the settings snapshot in visual_plan.json is updated")


def cmd_export(a):
    d, b = find_brand(a.slug)
    if not b:
        sys.exit(f"no brand {a.slug}")
    rem = Path(a.remotion).resolve()
    if not (rem / "src").is_dir():
        sys.exit(f"not a Remotion project: {rem}")
    pub = inside(rem / "public" / "brands", rem / "public" / "brands" / a.slug, "brand folder")  # slug already checked
    pub.mkdir(parents=True, exist_ok=True)
    logos = {}
    for k, v in (b.get("logos") or {}).items():
        p = brand_file(v, d)
        if not p:
            warn(f"logo {k} not found: {v}")
            continue
        shutil.copy2(p, pub / p.name)
        logos[k] = f"brands/{a.slug}/{p.name}"
    fonts = {}
    for role, f in (b.get("fonts") or {}).items():
        f = dict(f)
        if f.get("source") == "local":
            for key in ("files", "italic"):  # italic: italic files, the font loader registers them as style: italic
                files = []
                for v in f.get(key) or []:
                    p = brand_file(v, d)
                    if p:
                        shutil.copy2(p, pub / p.name)
                        files.append(f"brands/{a.slug}/{p.name}")
                if key in f:
                    f[key] = files
        fonts[role] = f
    rules, note = tone_rules(b, slug=a.slug)
    if note:
        warn(note)
    # the resolved brand tone: the Remotion template takes loudness, overshoot, shake, scene tones and the full-scene ceiling
    tone = {k: rules.get(k) for k in ("preset", "label", "loudness", "overshoot", "shake", "scene_tone", "scene_tones",
                                      "full_scenes_max", "transitions", "flash_max", "whip_max", "sfx")}
    out = {"slug": a.slug, "name": b.get("name"), "tagline": b.get("tagline"), "colors": b.get("colors"),
           "fonts": fonts, "logos": logos, "motion": rules.get("motion") or "calm", "tone": tone,
           "subtitles_default": b.get("subtitles_default"), "style_default": (b.get("styles") or {}).get("default")}
    if b.get("looks") is not None:  # style looks for the Remotion template, as they are
        out["looks"] = b["looks"]
    save_json(rem / "src" / "brands" / f"{a.slug}.json", out)
    print(f"src/brands/{a.slug}.json + {len(logos)} logo(s) in public/brands/{a.slug}/; tone {tone['preset']}, "
          f"motion {out['motion']}")


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("slug"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("new")
    p.add_argument("--name", required=True); p.add_argument("--colors", required=True)
    p.add_argument("--slug"); p.add_argument("--fonts"); p.add_argument("--scan", nargs="*")
    p.add_argument("--where", choices=["skill", "project"], default="project",
                   help="project (default): <project>/brands/; skill: brands/ next to the scripts folder, only in a "
                        "personal copy of the skill that already has that folder")
    p.add_argument("--approver"); p.add_argument("--account", default="business", choices=["business", "creator", "personal", "unknown"])
    p.add_argument("--tagline"); p.add_argument("--description"); p.add_argument("--source")
    p.add_argument("--language", default="en", help="the brand's language code, for example en, ru or th (default en)")
    p.add_argument("--motion", choices=["calm", "lively", "energetic"], help="explicit motion; without the flag it comes from the brand tone")
    p.add_argument("--tone", choices=TONE_PRESETS, help="brand tone; without the flag: expert marked \"unconfirmed\"")
    p.add_argument("--logo", nargs="*", help="logo files: copied into brands/<slug>/assets/")
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("logo", help="add or replace a brand logo (a copy in brands/<slug>/assets/)")
    p.add_argument("slug"); p.add_argument("files", nargs="+")
    p.add_argument("--role", default="auto", help="on_dark | on_light | mark_on_dark | mark_on_light | auto | your own name")
    p.set_defaults(fn=cmd_logo)
    p = sub.add_parser("rule", help="a brand rule from a revision, dated (an owner decision: references/playbook.md)")
    p.add_argument("slug"); p.add_argument("text")
    p.add_argument("--why", help="the reason, so a later disliked result can be traced to this rule")
    p.add_argument("--scope", help="which videos it applies to (a format, a style, a scene type)")
    p.set_defaults(fn=cmd_rule)
    p = sub.add_parser("set"); p.add_argument("slug"); p.add_argument("pairs", nargs="+"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("tone", help="brand tone: preset + field overrides")
    p.add_argument("slug"); p.add_argument("preset", choices=TONE_PRESETS)
    p.add_argument("--set", nargs="*", metavar="KEY=VALUE", help="preset fields: memes.max=1 flash_max=1 scene_tone=calm ...")
    p.add_argument("--reset", action="store_true", help="remove the previous overrides")
    p.set_defaults(fn=cmd_tone)
    p = sub.add_parser("use"); p.add_argument("slug"); p.add_argument("--edit", required=True); p.set_defaults(fn=cmd_use)
    p = sub.add_parser("export"); p.add_argument("slug"); p.add_argument("--remotion", required=True); p.set_defaults(fn=cmd_export)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
