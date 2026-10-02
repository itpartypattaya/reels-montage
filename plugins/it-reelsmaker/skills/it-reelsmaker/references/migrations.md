# Migrations: bringing settings and brand profiles up to date

Brand profiles and project settings live in your project, so a plugin update doesn't change them. When the skill reads one that is older than the current format, it brings it up to date once, keeping everything that was there.

**Current format:** `brand.json` → `"schema": 2`, `it-reelsmaker.json` → `"schema": 2`. No `schema` field means 1.

**When:** in step 0, whenever a `brand.json` or the project's `it-reelsmaker.json` is read and its `schema` is lower than the current one. This also covers a profile copied in from another project.

**Rules:**
- only add keys and rename them; never delete anything, and keep keys you don't know;
- before writing, copy the file next to it as `<name>.bak` (`brand.json.bak`), replacing an older copy;
- apply the steps one schema at a time, in order, then write the new `schema`;
- say what changed in one line per file; nothing to change → only the `schema` is written, silently;
- the file can't be parsed as JSON → don't touch it, say so, and work with the skill defaults.

| Schema | File | Change | Value |
|---|---|---|---|
| 1 → 2 | `brand.json` | add `tone` if it's missing (profiles from 1.0 have none) | `{"preset": "expert", "overrides": {}}` |
| 1 → 2 | `brand.json` | `motion` and `meme_size` stay as they are; the tone's ceiling still caps the meme size | — |
| 1 → 2 | `it-reelsmaker.json` | add `schema` (`last_seen_version` is written by “What's new”) | `2` |

**The message when a tone is added**, in the person's language: “Brand Acme: the profile had no brand tone, so it is now `expert` (calm, memes only on request). To change it, say ‘change the brand tone’.” The change itself is described in `references/brands.md`, “Changing the brand tone”.

**Adding a step** (for the maintainers): a new key with a default or a renamed key goes in a new row with the next schema number; `assets/brand-template/brand.json` gets that number, and the CHANGELOG mentions it.
