// hook scene — a large 2–6 word hook (first 0–2 s, a weak start of the speech). Variants:
//   slam — lines enter together (tone motion) and hold; type — typed out with a caret; stack — words stack up
//   one by one (on their own spoken words, if they are spoken); counter — a number counts from → to, the lines are the caption.
// overlay — lines on marker plates directly over the video (like the ReelKit hook), split/full/window — on a field, accent on a plate.
import React from "react";
import { interpolate } from "remotion";
import { glue, phraseGap } from "../Phrase";
import { BigNumber, LABEL_SIZE, TextBlock, bigNumberSize, caretOn, useFontsLoaded, wordTimes } from "./parts";
import { both, easeOut, exit } from "./tones";
import type { SceneCtx } from "./types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const baseSize = (c: SceneCtx) => (c.shell === "plates" ? 96 : c.mode === "full" ? 150 : 112);

export const Hook: React.FC<{ c: SceneCtx }> = ({ c }) => {
  const ready = useFontsLoaded([c.fonts.heading, c.fonts.body]);
  const { spec, frame, tl, tone, bt, surf, fonts } = c;
  const lines = spec.text?.lines?.filter(Boolean) ?? [];
  if (!lines.length) return null;
  const variant = spec.variant ?? "slam";
  const end = tl.n - tl.tail;
  const plates = c.shell === "plates";
  const chip = plates ? c.surfaces.card : null;
  const label = spec.text?.label ?? null;
  const labelH = label ? LABEL_SIZE + 24 : 0;
  const common = { accent: spec.text?.accent, label, font: fonts.heading, labelFont: fonts.body, surf, plates, chip, maxWidth: c.inner.w };
  const stagger = tl.inF <= 8 ? 2 : 4;
  // zone height: the TextBlock line step is 1.21 of the font size with plates (1.08 + 0.13 em padding), 1.1 for text (as in stack below);
  // lines never go below the scene frame (and the frame never goes below y 1500)
  const fitHeight = Math.min(baseSize(c), Math.floor((c.inner.h - labelH) / (lines.length * (plates ? 1.21 : 1.1))));

  if (variant === "stack") {
    // each word is its own line; the font size fits the widest word and the zone height
    const toks = glue(lines.join(" ")).split(" ").filter(Boolean); // a glued group (a particle with its word, e.g. “doesn't sell”) is one line
    const step = Math.max(4, Math.round(tl.inF * 0.6));
    const own = wordTimes(toks.map((t) => t.split(" ")[0]), c.words, spec.start, spec.start + spec.dur);
    let last = tl.lead;
    const starts = toks.map((_, k) => {
      const t = own[k];
      const f = t === null ? tl.lead + k * step : Math.round((t - spec.start) * c.fps);
      last = Math.max(last, f, tl.lead);
      return last;
    });
    const lh = plates ? 1.21 : 1.1;
    const byHeight = Math.floor((c.inner.h - labelH) / (toks.length * lh));
    const size = Math.min(baseSize(c) + 16, byHeight);
    return (
      <TextBlock {...common} lines={toks} size={size} weight={800}
        lineMotion={(k) => both(frame, starts[k], end, tone, bt)} labelMotion={both(frame, tl.lead, end, tone, bt)} />
    );
  }

  if (variant === "type") {
    // typing: the lines take their full space from the first frame, only the typed part is visible; ≈1.5 frames per character, no longer than 1 s
    const total = lines.reduce((a, l) => a + l.length, 0);
    const dur = Math.max(tl.inF, Math.min(total * 1.5, 30));
    const done = Math.floor(interpolate(frame, [tl.lead, tl.lead + dur], [0, total], clamp));
    let rest = done;
    const per = lines.map((l) => {
      const v = Math.max(0, Math.min(l.length, rest));
      rest -= l.length;
      return v;
    });
    const cur = Math.max(0, per.findIndex((v, k) => v < lines[k].length));
    const caretLine = done >= total ? lines.length - 1 : cur;
    const out = exit(frame, end, tone, bt);
    return (
      <div style={{ opacity: frame < tl.lead ? 0 : out.opacity, transform: out.transform, transformOrigin: "0% 50%" }}>
        <TextBlock {...common} lines={lines} size={fitHeight} typed={(k) => per[k]}
          caret={{ k: caretLine, on: caretOn(frame, tl.lead + dur), color: plates ? surf.hiText : surf.accent }} />
      </div>
    );
  }

  if (variant === "counter" && spec.value) {
    const v = spec.value;
    const p = interpolate(frame, [tl.lead, tl.lead + Math.max(tl.inF, 24)], [0, 1], { ...clamp, easing: easeOut });
    const numSize = bigNumberSize(v, c.mode === "full" ? 240 : 200, fonts.heading, c.inner.w - (plates ? 0.32 * 200 : 0), ready);
    const capSize = Math.round(Math.min(72, numSize * 0.36));
    const m = both(frame, tl.lead, end, tone, bt);
    // number → caption gap measured between visible edges: from the digits' baseline (~0.135 of the font size below it in the line) to the top of the caption letters
    // (~0.19 of the font size); a word suffix has descenders (like “y”) — keep at least 10 px from them
    const word = (v.suffix ?? "").trim().length > 2;
    const gap = Math.max(phraseGap(capSize), word ? Math.round(0.42 * numSize * 0.22) + 10 : 0);
    const mt = Math.round(gap - 0.135 * numSize - 0.19 * capSize);
    return (
      <div style={{ opacity: m.opacity, transform: m.transform, transformOrigin: "0% 50%", display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
        <span style={{ display: "inline-block", backgroundColor: plates ? surf.hiBg : undefined, padding: plates ? "0.02em 0.16em 0.04em" : 0,
          fontSize: numSize, lineHeight: 1 }}>
          <BigNumber v={v} p={p} size={numSize} font={fonts.heading} color={plates ? surf.hiText : surf.accent} sufColor={plates ? surf.hiText : surf.text} />
        </span>
        <div style={{ marginTop: plates ? 0 : mt }}>
          <TextBlock {...common} label={null} lines={lines} size={capSize}
            lineMotion={(k) => both(frame, tl.lead + 6 + k * stagger, end, tone, bt)} />
        </div>
      </div>
    );
  }

  // slam (default): the font size is limited by both the width (TextBlock) and the zone height
  return (
    <TextBlock {...common} lines={lines} size={fitHeight}
      lineMotion={(k) => both(frame, tl.lead + k * stagger, end, tone, bt)} labelMotion={both(frame, tl.lead, end, tone, bt)} />
  );
};
