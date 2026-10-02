// Scene contrast: “before → after”: the first line enters, gets struck through and fades, the second enters below it on a marker
// plate (on its spoken word, if it is spoken; otherwise after a reading pause for the first). One phrase is one block: lines of one
// font size on a shared left edge. overlay: both lines on plates over the video (the first light, the second marker).
import React from "react";
import { interpolate } from "remotion";
import { fitSize, glue } from "../Phrase";
import { LABEL_SIZE, Label, tokens, useFontsLoaded, wordTimes } from "./parts";
import { both, easeOut } from "./tones";
import type { SceneCtx } from "./types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Contrast: React.FC<{ c: SceneCtx }> = ({ c }) => {
  const ready = useFontsLoaded([c.fonts.heading, c.fonts.body]);
  const { spec, frame, tl, tone, bt, surf, fonts } = c;
  const lines = (spec.text?.lines?.filter(Boolean) ?? []).map((l) => glue(l));
  if (lines.length < 2) return null;
  const [was, now] = lines;
  const end = tl.n - tl.tail;
  const plates = c.shell === "plates";
  const label = spec.text?.label ?? null;
  const want = plates ? 88 : c.mode === "full" ? 140 : 100;
  const byH = Math.floor((c.inner.h - (label ? LABEL_SIZE + 20 : 0)) / 2.5);
  const size = Math.min(want, byH, ...[was, now].map((t) => fitSize({ text: t, size: want, font: fonts.heading, weight: 800, maxWidth: c.inner.w,
    padEm: 0.2, tracking: -0.01, ready })));
  // frame of the second line: its first word in the speech → else items[1].t → else after reading the first
  const tw = tokens(was);
  const own = wordTimes(tw.concat(tokens(now)), c.words, spec.start, spec.start + spec.dur)[tw.length];
  const t2 = typeof own === "number" ? own : spec.items?.[1]?.t ?? null;
  const read = Math.max(Math.round(0.6 * c.fps), Math.round(0.35 * (tl.settleTo - tl.lead - tl.inF)));
  const f2 = Math.max(tl.lead + tl.inF + 6, t2 !== null ? Math.round((t2 - spec.start) * c.fps) : tl.lead + tl.inF + read);
  const strike = interpolate(frame, [f2 - 10, f2 - 2], [0, 1], { ...clamp, easing: easeOut });
  const m1 = both(frame, tl.lead, end, tone, bt);
  const m2 = both(frame, f2, end, tone, bt);
  const card = c.surfaces.card;
  const row: React.CSSProperties = { display: "inline-block", fontFamily: fonts.heading, fontWeight: 800, fontSize: size, lineHeight: 1.08,
    letterSpacing: "-0.01em", whiteSpace: "pre", position: "relative" };
  const pad = "0.05em 0.2em 0.08em";
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
      {label ? (
        <div style={{ marginBottom: plates ? 4 : Math.round(10 - 0.19 * size) }}>
          <Label text={label} font={fonts.body} surf={surf} chip={plates ? card : null} motion={m1} maxWidth={c.inner.w} />
        </div>
      ) : null}
      <div style={{ opacity: m1.opacity * (1 - 0.5 * strike), transform: m1.transform, transformOrigin: "0% 50%" }}>
        <span style={{ ...row, color: plates ? card.text : surf.text, backgroundColor: plates ? card.bg : undefined, padding: pad }}>
          {was}
          <span style={{ position: "absolute", left: "0.12em", top: "54%", height: Math.max(6, Math.round(size * 0.08)), width: `calc(${strike} * (100% - 0.24em))`,
            backgroundColor: plates ? card.text : surf.accent }} />
        </span>
      </div>
      <div style={{ opacity: m2.opacity, transform: m2.transform, transformOrigin: "0% 50%", marginTop: plates ? 0 : Math.round(size * 0.12) }}>
        <span style={{ ...row, color: surf.hiText, backgroundColor: surf.hiBg, padding: pad }}>{now}</span>
      </div>
    </div>
  );
};
