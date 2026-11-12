# Migrations: bringing settings and brand profiles up to date

Brand profiles and project settings live in your project, so a plugin update doesn't change them. When the skill reads one that is older than the current format, it brings it up to date once, keeping everything that was there.

**Current format:** `brand.json` → `"schema": 2`, `it-reelsmaker.json` → `"schema": 2`. No `schema` field means 1.

**When:** in step 0, whenever a `brand.json` or the project's `it-reelsmaker.json` is read and its `schema` is lower than the current one. This also covers a profile copied in from another project.

**Rules:**
- only add fields and rename them; never delete anything, and keep fields you don't know;
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

**Changes with no schema step** (no file is rewritten; the scripts say what to do the first time they meet an older edit):
- 1.13: a brand tone or a video profile no longer turns B-roll or memes on. A video planned before, with inserts that came from the tone, fails `visual_plan.py validate` with the line that keeps them (`reelcfg.py save edit/<id> --set use_broll=true`) or the advice to remove them.
- 1.13: `visual_plan.py stage` stores the hook, the corner logo and the end card in the plan and keeps them on a later stage. A plan staged before stored no texts: the next stage keeps the corner logo and a logo sting, and stops, the plan unchanged, until `--hook` and `--card` are given again (or `--no-hook`, `--no-end`).
- 1.15: `use_generated_footage` is now `use_code_scenes` (it turns on code scenes drawn in Remotion, which the old name did not say). The old name is still read in every layer (the plugin's, the project's and the add-on's defaults, the brand, `reel.json`, `--set`), the new one wins when a file has both, and `reelcfg.py save`, `defaults` and `preset use` write the new one into the file they change; nothing else is rewritten.
- 1.15: a video profile is opt-in: the skill saves one only when the person asks for it, or `ad` for a paid ad. A video saved before with a `profile` or a `content_format` keeps it; remove it with `reelcfg.py save edit/<id> --set profile=null content_format=null`.
- 1.22: the plugin reads no environment variables. `REELS_PROJECT` → `project_root` in `it-reelsmaker.json` (or run from the project folder); `REELS_FACE_MODEL` → `face_model` there or `--model`; `REELS_MATTE_REMBG` → `matte.rembg` or `--rembg`; rembg's models outside `~/.u2net` → `matte.models` (on Linux also a model kept under the data folder `XDG_DATA_HOME` points to: the plugin no longer looks there by itself); `REELS_ONLINE_SCRIPTS` → the add-on's `link` command (`online_scripts`); the `REELS_DEFAULTS_OVERLAY` layer is gone, put those settings in the project's `reel-defaults.json`. A variable that is still set is simply not read.
- mascot: `brand.json → mascot` (`{"kind": "drawn", "component": …}` or `{"kind": "atlas", "rig": …}`) and `reel-defaults.json → brand_tones.<preset>.mascot` (`off` / `calm` / `full`) are new and optional: a profile without them has no mascot, and a project's own `brand_tones` without the field get the plugin's value (deep merge). An older Remotion project gets `src/gen/mascots.ts` from `kit.py update` (`references/mascot.md`).
- 1.22: `visual_plan.py export` / `brand.py export` → `visual_plan.py stage` / `brand.py stage` (same arguments). The plan's record of the chosen ending moved to `finish`: a video staged before keeps its corner logo and sting, and the next `stage` asks once for `--hook` and `--card` again (or `--no-hook` / `--no-end`).
- 1.22: `brand.py set` / `memes.py set` → `brand.py change` / `memes.py change` (same arguments); `brand.py tone … --set` → `--field`. A clip card's field for the other voice (`cut`/`keep`) is now `other_voice`: rename it in `clips.json`; `longform.py check` warns about a piece with the other voice in it until the card says `other_voice: keep` (or the voice is cut).

**Adding a step** (for the maintainers): a new field with a default or a renamed field of `brand.json` or `it-reelsmaker.json` goes in a new row with the next schema number (a renamed video setting is read under both names instead: `reels_common.RENAMED`); `assets/brand-template/brand.json` gets that number, and the CHANGELOG mentions it.
