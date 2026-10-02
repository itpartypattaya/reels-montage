// Scene chat: a conversation or notifications in turn (items[].from: me / them / system, items[].t on their words).
// The chat window is a light style card with no messenger logos; own messages on a marker plate on the right, the other
// side's on the left on a soft fill, system ones (“Read”, “last seen 5 days ago”) small and centered. Before a message from
// the other side, 12 frames of “typing…” dots. If the messages do not fit, the window scrolls up. Header: text.lines: [name, status].
// On-screen data is fictional (references/scenes.md).
import React from "react";
import { interpolate } from "remotion";
import { glue } from "../Phrase";
import { useFontsLoaded, wrapCount } from "./parts";
import { both, easeOut, enter, itemFrames } from "./tones";
import type { SceneCtx } from "./types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Chat: React.FC<{ c: SceneCtx }> = ({ c }) => {
  const ready = useFontsLoaded([c.fonts.heading, c.fonts.body]);
  const { spec, frame, tl, tone, bt, fonts } = c;
  const items = (spec.items ?? []).filter((i) => i && i.text);
  if (!items.length) return null;
  const S = c.surfaces.card; // the window is always a light card
  const end = tl.n - tl.tail;
  const W = c.inner.w;
  const head = spec.text?.lines?.filter(Boolean) ?? [];
  const headH = head.length ? 112 : 0;
  const size = c.mode === "full" ? 42 : 38;
  const pad = 30;
  const maxB = Math.round((W - 2 * pad) * 0.76);
  const gap = 14;
  // message heights measured with the font → positions in the feed
  const hs = items.map((it) => {
    if (it.from === "system") return Math.round(size * 0.72 * 1.3) + 6;
    return wrapCount(it.text, fonts.body, size, 500, maxB - 52, ready) * size * 1.28 + 34;
  });
  const ys: number[] = [];
  hs.reduce((y, h, k) => {
    ys[k] = y;
    return y + h + gap;
  }, 0);
  const starts = itemFrames(items.map((i) => i.t), spec.start, c.fps, tl);
  // window height fits the conversation (from the first frame, for all messages), but not taller than the zone; if it does not fit, it scrolls
  const total = ys[ys.length - 1] + hs[hs.length - 1];
  const H = Math.min(c.inner.h, Math.max(Math.round(c.inner.h * 0.4), headH + 2 * pad + total + 6));
  const area = H - headH - 2 * pad;
  // scrolling: after a message appears, the feed moves up over 8 frames so the message is fully visible
  const need = (k: number) => Math.max(0, ys[k] + hs[k] - area);
  let scroll = 0;
  starts.forEach((f, k) => {
    const prev = k ? need(k - 1) : 0;
    if (frame >= f) scroll = interpolate(frame, [f, f + 8], [prev, need(k)], { ...clamp, easing: easeOut });
  });
  const win = both(frame, tl.lead, end, tone, bt);
  const dots = Math.floor(frame / 5) % 4;
  return (
    <div style={{ width: W, height: H, backgroundColor: S.bg, borderRadius: c.radius ? 28 : 0, overflow: "hidden", position: "relative",
      opacity: win.opacity, transform: win.transform, transformOrigin: "0% 50%", fontFamily: fonts.body }}>
      {head.length ? (
        <div style={{ height: headH, boxSizing: "border-box", display: "flex", alignItems: "center", gap: 22, padding: `0 ${pad}px`,
          borderBottom: `2px solid ${S.line}` }}>
          <div style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: S.soft, display: "flex", alignItems: "center",
            justifyContent: "center", fontWeight: 700, fontSize: 34, color: S.text }}>
            {head[0].trim().charAt(0).toUpperCase()}
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 38, color: S.text, lineHeight: 1.15 }}>{glue(head[0])}</div>
            {head[1] ? <div style={{ fontWeight: 500, fontSize: 28, color: S.muted, marginTop: 4 }}>{glue(head[1])}</div> : null}
          </div>
        </div>
      ) : null}
      <div style={{ position: "absolute", left: pad, right: pad, top: headH + pad, height: area, overflow: "hidden" }}>
        <div style={{ position: "relative", transform: `translateY(${-scroll}px)` }}>
          {items.map((it, k) => {
            const m = enter(frame, starts[k], tone, bt, { dist: 30 });
            const mine = it.from === "me";
            if (it.from === "system") {
              return (
                <div key={k} style={{ position: "absolute", top: ys[k], left: 0, right: 0, textAlign: "center", fontWeight: 600,
                  fontSize: Math.round(size * 0.72), color: S.muted, opacity: m.opacity }}>
                  {glue(it.text)}
                </div>
              );
            }
            // “typing…” before a message from the other side
            const typing = !mine && frame >= starts[k] - 12 && frame < starts[k] && (k === 0 || frame >= starts[k - 1] + 4);
            return (
              <React.Fragment key={k}>
                {typing ? (
                  <div style={{ position: "absolute", top: ys[k], left: 0, backgroundColor: S.soft, padding: "20px 26px", borderRadius: c.radius ? 22 : 4 }}>
                    {[0, 1, 2].map((d) => (
                      <span key={d} style={{ display: "inline-block", width: 16, height: 16, borderRadius: 8, marginRight: d < 2 ? 12 : 0,
                        backgroundColor: S.text, opacity: dots > d ? 0.75 : 0.22 }} />
                    ))}
                  </div>
                ) : null}
                <div style={{ position: "absolute", top: ys[k], left: 0, right: 0, display: "flex", justifyContent: mine ? "flex-end" : "flex-start",
                  opacity: m.opacity, transform: m.transform, transformOrigin: "0% 50%" }}>
                  <div style={{ maxWidth: maxB, boxSizing: "border-box", padding: "17px 26px", borderRadius: c.radius ? 22 : 4, fontWeight: 500,
                    fontSize: size, lineHeight: 1.28, backgroundColor: mine ? S.hiBg : S.soft, color: mine ? S.hiText : S.text }}>
                    {glue(it.text)}
                  </div>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
};
