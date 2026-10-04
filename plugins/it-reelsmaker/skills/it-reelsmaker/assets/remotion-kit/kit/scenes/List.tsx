// Scene list: 2–5 items in turn, each on its own word (items[].t; missing → evenly, no more often than every 0.6 s).
// The item being spoken sits on a marker plate, past items stay (the list reads as a whole). The number “01” is in the accent color.
// panel: a card next to the shrunk speaker (references/techniques.md, “Slide scene”); split/full: on the field. Title (text.lines) is optional.
// overlay: plates straight over the video in the free zone (the speaker is not moved): the item being spoken on a marker plate
// (look.mark / look.onMark), past items on light plates, the number inside the plate; the title on light plates.
import React from "react";
import { glue } from "../Phrase";
import { LABEL_SIZE, TextBlock, fitWrapped, useFontsLoaded, wrapCount } from "./parts";
import { both, itemFrames } from "./tones";
import type { SceneCtx } from "./types";

export const List: React.FC<{ c: SceneCtx }> = ({ c }) => {
  const ready = useFontsLoaded([c.fonts.heading, c.fonts.body]);
  const { spec, frame, tl, tone, bt, surf, fonts } = c;
  const items = (spec.items ?? []).filter((i) => i && i.text).slice(0, 6);
  if (!items.length) return null;
  const end = tl.n - tl.tail;
  const card = c.shell === "card";
  const plates = c.shell === "plates";
  const light = c.surfaces.card; // the light plate of past items and of the title over the video
  const title = spec.text?.lines?.filter(Boolean) ?? [];
  const label = spec.text?.label ?? null;
  const titleSize = card ? 52 : c.mode === "full" ? 96 : 64;
  const titleGap = plates ? 12 : 36;
  // a title line on a plate takes 1.08 em + 0.13 em of padding (TextBlock), as text 1.1 em
  const titleH = (title.length ? title.length * titleSize * (plates ? 1.21 : 1.1) + titleGap : 0) + (label ? LABEL_SIZE + 20 : 0);
  const gap = card ? 18 : plates ? 12 : 24;
  const want = c.mode === "panel" ? 52 : card ? 46 : plates ? 58 : c.mode === "full" ? 72 : 54;
  const numW = (s: number) => Math.round(s * 1.75);
  // font size: all items fit the height, the longest word fits the width (the plate adds 0.36 em); among sizes
  // want…0.75·want take the one with the fewest line breaks (a short item is not split over two lines), on a tie the larger one
  const texts = items.map((i) => i.text);
  const avail = c.inner.h - titleH;
  const lines = (s: number) => texts.reduce((a, t) => a + wrapCount(t, fonts.body, s, 600, c.inner.w - numW(s) - 0.4 * s, ready), 0);
  const fits = (s: number) => fitWrapped({ texts, font: fonts.body, weight: 600, size: s, width: c.inner.w - numW(s) - 0.4 * s, height: avail,
    lh: 1.18, gap, extra: items.length * 0.14 * s, ready, min: 30 }) === s;
  let size = fitWrapped({ texts, font: fonts.body, weight: 600, size: want, width: c.inner.w - numW(want) - 0.4 * want, height: avail, lh: 1.18,
    gap, extra: items.length * 0.14 * want, ready, min: 30 });
  let best = lines(size);
  for (let s = size - 2; s >= Math.round(0.75 * want); s -= 2) {
    const n = lines(s);
    if (n < best && fits(s)) {
      best = n;
      size = s;
    }
  }
  const starts = itemFrames(items.map((i) => i.t), spec.start, c.fps, tl);
  const active = starts.reduce((a, f, k) => (frame >= f ? k : a), -1);

  const row = (k: number) => both(frame, starts[k], end, tone, bt, { dist: 24, dir: 1 });
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", width: c.inner.w }}>
      {title.length || label ? (
        <div style={{ marginBottom: title.length ? titleGap : 18 }}>
          <TextBlock lines={title} label={label} accent={spec.text?.accent} size={titleSize} font={fonts.heading} labelFont={fonts.body}
            surf={plates ? { ...light, hiBg: light.bg, hiText: light.text } : surf} plates={plates} chip={plates ? light : null}
            maxWidth={c.inner.w} lineMotion={() => both(frame, tl.lead, end, tone, bt)} labelMotion={both(frame, tl.lead, end, tone, bt)} />
        </div>
      ) : null}
      <div style={{ display: "flex", flexDirection: "column", gap }}>
        {items.map((it, k) => {
          const m = row(k);
          const on = k === active;
          const num = k < 9 ? `0${k + 1}` : String(k + 1);
          if (plates) {
            // over the video every line needs its plate: the spoken item on the marker, the past ones on light plates
            return (
              <div key={k} style={{ opacity: m.opacity, transform: m.transform, transformOrigin: "0% 50%" }}>
                <span style={{ fontFamily: fonts.body, fontWeight: 600, fontSize: size, lineHeight: 1.18, color: on ? surf.hiText : light.text,
                  backgroundColor: on ? surf.hiBg : light.bg, padding: "0.05em 0.2em 0.08em", boxDecorationBreak: "clone",
                  WebkitBoxDecorationBreak: "clone" }}>
                  <span style={{ fontFamily: fonts.heading, fontWeight: 800, fontVariantNumeric: "tabular-nums", opacity: 0.72, marginRight: "0.35em" }}>
                    {num}
                  </span>
                  {glue(it.text)}
                </span>
              </div>
            );
          }
          return (
            <div key={k} style={{ display: "flex", flexDirection: "row", alignItems: "baseline", opacity: m.opacity, transform: m.transform, transformOrigin: "0% 50%" }}>
              <div style={{ width: numW(size), flexShrink: 0, fontFamily: fonts.heading, fontWeight: 800, fontSize: size, lineHeight: 1.18,
                color: card ? surf.text : surf.accent, fontVariantNumeric: "tabular-nums", opacity: on ? 1 : 0.7 }}>
                {num}
              </div>
              <div style={{ fontFamily: fonts.body, fontWeight: 600, fontSize: size, lineHeight: 1.18, color: on ? surf.hiText : surf.text }}>
                <span style={{ backgroundColor: on ? surf.hiBg : undefined, padding: "0.02em 0.18em 0.06em", boxDecorationBreak: "clone",
                  WebkitBoxDecorationBreak: "clone", marginLeft: "-0.18em" }}>
                  {glue(it.text)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
