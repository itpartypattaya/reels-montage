// Scene stat: a big number: a counter from → to, focus brackets close in around it, a caption below (text.lines).
// A source for the number is required (visual_plan.py validate; agent → “verify, put in the report”). Number font size follows the zone width.
import React from "react";
import { interpolate } from "remotion";

import { BigNumber, Brackets, LABEL_SIZE, Label, TextBlock, bigNumberSize, useFontsLoaded } from "./parts";
import { both, easeOut, progress } from "./tones";
import type { SceneCtx } from "./types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Stat: React.FC<{ c: SceneCtx }> = ({ c }) => {
  const ready = useFontsLoaded([c.fonts.heading, c.fonts.body]);
  const { spec, frame, tl, tone, bt, surf, fonts } = c;
  const v = spec.value;
  if (!v) return null;
  const lines = spec.text?.lines?.filter(Boolean) ?? [];
  const end = tl.n - tl.tail;
  const card = c.shell === "card";
  const p = interpolate(frame, [tl.lead, tl.lead + Math.max(tl.inF, 24)], [0, 1], { ...clamp, easing: easeOut });
  const label = spec.text?.label ?? null;
  const capWant = card ? 48 : c.mode === "full" ? 76 : 56;
  const numWant = card ? 150 : c.mode === "full" ? 250 : c.mode === "panel" ? 150 : 200;
  // number + bracket margins (0.14 × font size on each side) fit the width; everything together fits the zone height
  const fitW = bigNumberSize(v, numWant, fonts.heading, c.inner.w - 12 - 0.32 * numWant, ready); // + bracket margins of 0.16 × font size

  const capH = lines.length * capWant * 1.1;
  const byH = Math.floor((c.inner.h - capH - (label ? LABEL_SIZE + 20 : 0) - 40) / 1.1);
  const numSize = Math.max(60, Math.min(fitW, byH));
  const m = both(frame, tl.lead, end, tone, bt);
  const br = progress(frame, tl.lead + 6, 14);
  const numColor = card ? surf.text : surf.accent;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
      {label ? <Label text={label} font={fonts.body} surf={surf} motion={m} maxWidth={c.inner.w} /> : null}
      <div style={{ position: "relative", padding: "0.1em 0.16em 0.08em", marginTop: label ? 18 : 0, fontSize: numSize, lineHeight: 1,
        opacity: m.opacity, transform: m.transform, transformOrigin: "0% 50%" }}>
        <BigNumber v={v} p={p} size={numSize} font={fonts.heading} color={numColor} sufColor={surf.text} />
        {/* the brackets in the surface's accent (the marker when it has ≥ 3:1 on the surface, else the text color), as in the
            CTA and word scenes; the marker plate color vanished on a light field (T6: yellow on cream, 1.05:1) */}
        <Brackets x={0} y={0} w="100%" h="100%" progress={br * m.opacity} color={surf.accent} size={Math.round(numSize * 0.2)}
          stroke={Math.max(4, Math.round(numSize * 0.03))} />
      </div>
      {lines.length ? (
        <div style={{ marginTop: Math.round(18 - 0.19 * capWant) }}>
          <TextBlock lines={lines} accent={spec.text?.accent} size={capWant} weight={600} font={fonts.body} labelFont={fonts.body}
            surf={surf} maxWidth={c.inner.w} lineMotion={(k) => both(frame, tl.lead + 8 + k * 4, end, tone, bt)} />
        </div>
      ) : null}
    </div>
  );
};
