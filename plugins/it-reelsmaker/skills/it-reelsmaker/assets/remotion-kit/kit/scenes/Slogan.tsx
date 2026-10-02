// Scene slogan: the main idea as a “punch” (effects.md §7): a field in the style's marker color slides in as a shutter (SceneLayer),
// words rise from below one by one on their spoken words (not found in the speech → evenly), left-aligned, 80–110 px.
// The icon (media, an image) sits above the text and is “drawn in” by a mask from top to bottom. Once or twice per video, not on the hook or CTA.
import React from "react";
import { fitSize, glue } from "../Phrase";
import { Icon, LABEL_SIZE, Label, norm, useFontsLoaded, wordTimes } from "./parts";
import { exit, progress } from "./tones";
import type { SceneCtx } from "./types";

export const Slogan: React.FC<{ c: SceneCtx }> = ({ c }) => {
  const ready = useFontsLoaded([c.fonts.heading, c.fonts.body]);
  const { spec, frame, tl, tone, bt, surf, fonts } = c;
  const lines = (spec.text?.lines?.filter(Boolean) ?? []).map((l) => glue(l));
  if (!lines.length) return null;
  const end = tl.n - tl.tail;
  const icon = spec.media && spec.media.kind === "image" ? spec.media.file : null;
  const iconH = icon ? 220 : 0;
  const label = spec.text?.label ?? null;
  const want = c.mode === "full" ? 140 : 92;
  const lh = 1.12;
  const free = c.inner.h - (label ? LABEL_SIZE + 20 : 0) - (icon ? iconH + 36 : 0);
  const byHeight = Math.floor(free / (lines.length * lh));
  const acc = new Set((spec.text?.accent ? glue(spec.text.accent).split(/[  ]+/) : []).map(norm));
  const size = Math.min(want, byHeight, ...lines.map((l) => fitSize({ text: l, size: want, font: fonts.body, weight: 800, maxWidth: c.inner.w,
    tracking: -0.02, padEm: acc.size ? 0.14 : 0, ready })));
  // words (groups glued with a non-breaking space count as one unit) and their frames
  const units = lines.map((l) => l.split(" "));
  const flat = units.reduce((a, b) => a.concat(b), [] as string[]);
  const own = wordTimes(flat.map((u) => u.split(" ")[0]), c.words, spec.start, spec.start + spec.dur);
  const step = Math.max(4, Math.min(10, Math.round((tl.n * 0.3) / flat.length)));
  let last = tl.lead;
  const starts = flat.map((_, k) => {
    const t = own[k];
    last = Math.max(last, t === null ? tl.lead + k * step : Math.round((t - spec.start) * c.fps));
    return last;
  });
  const out = exit(frame, end, tone, bt);
  const reveal = progress(frame, tl.lead, 12);
  let idx = 0;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", opacity: out.opacity, transform: out.transform, transformOrigin: "0% 50%" }}>
      {icon ? <Icon file={icon} h={iconH} maxW={c.inner.w} surf={surf} reveal={reveal} aspect={spec.media?.aspect} style={{ marginBottom: 36 }} /> : null}
      {label ? <Label text={label} font={fonts.body} surf={surf} maxWidth={c.inner.w}
        motion={{ opacity: progress(frame, tl.lead, tl.inF), transform: "none" }} /> : null}
      <div style={{ marginTop: label ? Math.round(10 - 0.19 * size) : 0 }}>
        {units.map((ws, li) => (
          <div key={li} style={{ overflow: "hidden", paddingBottom: Math.round(size * 0.1), marginBottom: -Math.round(size * 0.1),
            fontFamily: fonts.body, fontWeight: 800, fontSize: size, lineHeight: lh, letterSpacing: "-0.02em", whiteSpace: "pre", color: surf.text }}>
            {ws.map((w, wi) => {
              const k = idx++;
              const p = tl.inF ? progress(frame, starts[k], Math.max(6, tl.inF - 4)) : frame >= starts[k] ? 1 : 0;
              const hi = w.split(" ").some((x) => acc.has(norm(x)));
              return (
                <React.Fragment key={wi}>
                  {wi ? " " : ""}
                  <span style={{ display: "inline-block", transform: `translateY(${(1 - p) * 110}%)`, opacity: p > 0 ? 1 : 0,
                    backgroundColor: hi ? surf.hiBg : undefined, color: hi ? surf.hiText : undefined, padding: hi ? "0 0.14em" : undefined }}>
                    {w}
                  </span>
                </React.Fragment>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};
