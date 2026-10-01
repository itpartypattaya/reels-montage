# Sources of README images

- `diagrams/*.svg` — diagrams drawn with the baoyu-diagram skill; render with `bun <baoyu-diagram>/scripts/main.ts <file>.svg` and copy the @2x PNG to `docs/img/` (READMEs load images from there by absolute URL, so the plugin folder ships no images except its icon).
- `banner/prompt.md` — prompt for the banner background (Codex image_gen via baoyu-codex-imagegen, aspect 2.35:1); the title is overlaid afterwards with Pillow (Segoe UI).
