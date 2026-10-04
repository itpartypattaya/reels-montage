// Scene quote: a verbatim quote (from the speech: visual_plan.py validate checks it against captions.json) + an all-caps label above it.
// On the left, a bar in the marker color grows from top to bottom together with the text (the brand's signature “marker”, references/brands.md).
// overlay: a light card in the box; split/full/window: on the field, the accent word on a plate.
import React from "react";
import { LABEL_SIZE, TextBlock } from "./parts";
import { both, progress } from "./tones";
import type { SceneCtx } from "./types";

const BAR = 8;
const BAR_GAP = 30;

export const Quote: React.FC<{ c: SceneCtx }> = ({ c }) => {
  const { spec, frame, tl, tone, bt, surf, fonts } = c;
  const lines = spec.text?.lines?.filter(Boolean) ?? [];
  if (!lines.length) return null;
  const end = tl.n - tl.tail;
  const card = c.shell === "card";
  const want = card ? 60 : c.mode === "full" ? 120 : 80; // full frame: large (brag: typography fills the frame); beyond that the width limits it
  const label = spec.text?.label ?? null;
  // by height: lines at 1.1 × font size + the label; by width: TextBlock (measured with the font)
  const byHeight = Math.floor((c.inner.h - (label ? LABEL_SIZE + 20 : 0)) / (lines.length * 1.1));
  const size = Math.min(want, byHeight);
  const bar = progress(frame, tl.lead, tl.inF + 6);
  const out = both(frame, tl.lead, end, tone, bt);
  return (
    <div style={{ display: "flex", flexDirection: "row", alignItems: "stretch", opacity: Math.min(1, out.opacity * 3) }}>
      <div style={{ width: BAR, flexShrink: 0, position: "relative", opacity: out.opacity }}>
        <div style={{ position: "absolute", left: 0, top: 0, width: BAR, height: `${bar * 100}%`, backgroundColor: surf.hiBg }} />
      </div>
      <div style={{ marginLeft: BAR_GAP }}>
        <TextBlock lines={lines} accent={spec.text?.accent} label={label} quote size={size} weight={card ? 600 : 700}
          font={card ? fonts.body : fonts.heading} labelFont={fonts.body} surf={surf} maxWidth={c.inner.w - BAR - BAR_GAP}
          lineMotion={(k) => both(frame, tl.lead + 3 + k * 4, end, tone, bt)} labelMotion={both(frame, tl.lead, end, tone, bt)} />
      </div>
    </div>
  );
};
