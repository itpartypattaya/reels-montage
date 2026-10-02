// Scene word: visualizes a word that has no footage (an abstraction): a mini diagram + caption (text.lines).
// variant: grid-pick: a grid of mini cards, the chosen ones (value.to, 1–4) highlighted and framed by focus brackets (“200 → 5”);
//          funnel: a funnel of 3–4 bars (captions from items); timeline: a line with dots appearing in turn (items, on their words);
//          icon: the media picture (a pictogram from the library) is revealed by a mask from top to bottom.
// No growth arrows, check marks or globes (brand guideline bans): only geometry and brand colors.
import React from "react";
import { interpolate } from "remotion";
import { alpha } from "../brand";
import { fitSize, glue } from "../Phrase";
import { Brackets, Icon, LABEL_SIZE, MiniCard, TextBlock, useFontsLoaded } from "./parts";
import { both, easeOut, exit, itemFrames, progress } from "./tones";
import type { SceneCtx } from "./types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const WordViz: React.FC<{ c: SceneCtx }> = ({ c }) => {
  const ready = useFontsLoaded([c.fonts.heading, c.fonts.body]);
  const { spec, frame, tl, tone, bt, surf, fonts } = c;
  const lines = spec.text?.lines?.filter(Boolean) ?? [];
  const label = spec.text?.label ?? null;
  const end = tl.n - tl.tail;
  const card = c.shell === "card";
  const variant = spec.variant ?? (spec.media ? "icon" : "grid-pick");
  const capSize = card ? 48 : c.mode === "full" ? 64 : 56;
  const capH = lines.length ? lines.length * capSize * 1.1 + 32 : 0;
  const labelH = label ? LABEL_SIZE + 20 : 0;
  const vh = Math.max(160, Math.min(c.mode === "full" ? 700 : 520, c.inner.h - capH - labelH));
  const gw = Math.min(c.inner.w, 860);
  // on a light card the soft fill is almost invisible, so one step denser
  const soft = surf.kind === "card" ? surf.line : surf.soft;
  const line = surf.kind === "card" ? alpha(surf.text, 0.28) : surf.line;
  const m = both(frame, tl.lead, end, tone, bt);
  const out = exit(frame, end, tone, bt).opacity; // shared exit; each detail has its own entry

  let visual: React.ReactNode = null;
  if (variant === "funnel") {
    const n = Math.min(4, Math.max(3, spec.items?.length ?? 4));
    const gap = 12;
    const bh = Math.min(96, Math.floor((vh - gap * (n - 1)) / n));
    visual = (
      <div style={{ width: gw, display: "flex", flexDirection: "column", alignItems: "center", gap }}>
        {Array.from({ length: n }).map((_, k) => {
          const p = progress(frame, tl.lead + k * 5, tl.inF || 1);
          const last = k === n - 1;
          const w = gw * (1 - (0.66 * k) / Math.max(1, n - 1));
          const txt = spec.items?.[k]?.text;
          return (
            <div key={k} style={{ position: "relative", width: w, height: bh, opacity: p, display: "flex", alignItems: "center",
              justifyContent: "center" }}>
              {/* the bar grows in width, the caption is not squeezed */}
              <div style={{ position: "absolute", inset: 0, backgroundColor: last ? surf.hiBg : soft, transform: `scaleX(${0.6 + 0.4 * p})`,
                clipPath: "polygon(0 0, 100% 0, 96% 100%, 4% 100%)" }} />
              {txt ? <span style={{ position: "relative", fontFamily: fonts.body, fontWeight: 600, fontSize: Math.round(bh * 0.4),
                color: last ? surf.hiText : surf.text, whiteSpace: "pre" }}>{glue(txt)}</span> : null}
            </div>
          );
        })}
      </div>
    );
  } else if (variant === "timeline") {
    const its = spec.items && spec.items.length >= 2 ? spec.items.slice(0, 5) : [{ text: "" }, { text: "" }, { text: "" }, { text: "" }];
    const starts = itemFrames(its.map((i) => i.t), spec.start, c.fps, tl);
    const active = starts.reduce((a, f, k) => (frame >= f ? k : a), -1);
    const line = interpolate(frame, [tl.lead, tl.lead + 14], [0, 1], { ...clamp, easing: easeOut });
    const seg = gw / its.length;
    const cy = 40;
    // dot captions: one shared font size, each fits its own segment (with 8 px margins), measured with the font
    const lab = Math.min(Math.min(44, Math.round(seg * 0.22)), ...its.map((i) => (i.text ? fitSize({ text: glue(i.text), size: Math.min(44, Math.round(seg * 0.22)),
      font: fonts.body, weight: 600, maxWidth: seg - 16, ready }) : 44)));
    visual = (
      <div style={{ position: "relative", width: gw, height: Math.min(vh, cy + 40 + lab * 2.6) }}>
        <div style={{ position: "absolute", left: seg / 2, top: cy - 3, width: (gw - seg) * line, height: 6, backgroundColor: surf.line }} />
        {its.map((it, k) => {
          const p = progress(frame, starts[k], 8);
          const on = k === active;
          const d = on ? 44 : 28;
          return (
            <React.Fragment key={k}>
              <div style={{ position: "absolute", left: seg * (k + 0.5) - d / 2, top: cy - d / 2, width: d, height: d, borderRadius: d / 2,
                backgroundColor: on ? surf.hiBg : surf.accent, opacity: p, transform: `scale(${0.5 + 0.5 * p})` }} />
              {it.text ? (
                <div style={{ position: "absolute", left: seg * k + 8, top: cy + 40, width: seg - 16, textAlign: "center", fontFamily: fonts.body,
                  fontWeight: 600, fontSize: lab, lineHeight: 1.18, color: surf.text, opacity: p, whiteSpace: "pre" }}>
                  {glue(it.text)}
                </div>
              ) : null}
            </React.Fragment>
          );
        })}
      </div>
    );
  } else if (variant === "icon" && spec.media) {
    const r = progress(frame, tl.lead, 12);
    visual = <Icon file={spec.media.file} h={Math.min(vh, 360)} maxW={gw} surf={surf} reveal={r} aspect={spec.media.aspect} />;
  } else {
    // grid-pick: 4 × 3 mini cards, the chosen ones in the middle row
    const cols = 4;
    const rows = 3;
    const gap = Math.round(gw * 0.03);
    let cw = (gw - gap * (cols - 1)) / cols;
    let ch = cw * 0.68;
    const th = rows * ch + (rows - 1) * gap;
    if (th > vh - 40) {
      const k = (vh - 40) / th;
      cw *= k;
      ch *= k;
    }
    const pick = Math.max(1, Math.min(4, Math.round(spec.value?.to ?? 1)));
    const c0 = Math.floor((cols - pick) / 2);
    const appear = (i: number) => interpolate(frame, [tl.lead + i * 0.7, tl.lead + i * 0.7 + 8], [0, 1], clamp);
    const dim = progress(frame, tl.lead + 16, 12);
    const br = progress(frame, tl.lead + 24, 14);
    const W = cols * cw + (cols - 1) * gap;
    visual = (
      <div style={{ position: "relative", width: W, height: rows * ch + (rows - 1) * gap, margin: "20px 0" }}>
        {Array.from({ length: rows * cols }).map((_, i) => {
          const r = Math.floor(i / cols);
          const col = i % cols;
          const chosen = r === 1 && col >= c0 && col < c0 + pick;
          return (
            <div key={i} style={{ position: "absolute", left: col * (cw + gap), top: r * (ch + gap), opacity: appear(i) * (chosen ? 1 : 1 - 0.72 * dim) }}>
              <MiniCard w={cw} h={ch} radius={c.radius ? 12 : 0} bg={chosen && dim > 0.5 ? surf.hiBg : soft}
                line={chosen && dim > 0.5 ? alpha(surf.hiText, 0.3) : line} dot={chosen && dim > 0.5 ? surf.hiText : line} />
            </div>
          );
        })}
        <Brackets x={c0 * (cw + gap) - 16} y={ch + gap - 16} w={pick * cw + (pick - 1) * gap + 32} h={ch + 32} progress={br}
          color={surf.accent} size={30} stroke={5} />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", opacity: out }}>
      {label ? <TextBlock lines={[]} label={label} size={capSize} font={fonts.body} labelFont={fonts.body} surf={surf} maxWidth={c.inner.w} labelMotion={m} /> : null}
      <div style={{ marginTop: label ? 20 : 0, width: c.inner.w, display: "flex", justifyContent: variant === "icon" ? "flex-start" : "center" }}>{visual}</div>
      {lines.length ? (
        <div style={{ marginTop: 32 }}>
          <TextBlock lines={lines} accent={spec.text?.accent} size={capSize} weight={600} font={fonts.body} labelFont={fonts.body} surf={surf}
            maxWidth={c.inner.w} lineMotion={(k) => both(frame, tl.lead + 10 + k * 4, end, tone, bt)} />
        </div>
      ) : null}
    </div>
  );
};
