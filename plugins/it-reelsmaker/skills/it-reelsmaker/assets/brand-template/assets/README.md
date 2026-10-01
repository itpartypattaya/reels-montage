# Brand files

The brand's files go here: logos (PNG with transparency, or SVG), LUTs (hald `.png` for ffmpeg and `.cube` for CapCut), and font files (`.ttf`/`.otf`/`.woff2`) if the font isn't on Google Fonts. Paths in `brand.json` are written relative to the brand folder: `assets/logo-white.png`.

Logo roles:
- `on_dark`: a light logo for a dark background and over video;
- `on_light`: a dark logo for a light background;
- `mark_on_dark` / `mark_on_light`: a compact mark for the frame corner.

The agent can work out the role itself: from the average brightness of the opaque pixels (light → `on_dark`) and from the proportions (near-square, or the word `mark` / `emblem` in the name, or the same word in the brand's language → `mark_*`).
