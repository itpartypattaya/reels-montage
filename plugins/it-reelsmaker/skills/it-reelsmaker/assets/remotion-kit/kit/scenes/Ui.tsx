// Scene ui: the product in action: a screenshot or screen recording (media) + an action (interaction): the cursor moves in and
// clicks, a finger taps (ripple), typing into a field with a caret, a swipe (the feed moves up). target is in fractions of the media
// frame (0–1); values > 1 are pixels of the 1080×1920 source. media.aspect is the file's width/height (missing → 9:16, phone).
// Caption on top: text.label + text.lines (optional). Personal data on screen is fictional (references/scenes.md).
import React from "react";
import { Img, OffthreadVideo, interpolate, staticFile } from "remotion";
import { alpha } from "../brand";
import { glue } from "../Phrase";
import { LABEL_SIZE, TextBlock, caretOn } from "./parts";
import { both, easeInOut, easeOut } from "./tones";
import type { SceneCtx } from "./types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Ui: React.FC<{ c: SceneCtx }> = ({ c }) => {
  const { spec, frame, tl, tone, bt, surf, fonts, brand } = c;
  if (!spec.media) return null;
  const end = tl.n - tl.tail;
  const lines = spec.text?.lines?.filter(Boolean) ?? [];
  const label = spec.text?.label ?? null;
  const capSize = c.mode === "full" ? 56 : 48;
  const capH = (lines.length ? lines.length * capSize * 1.1 : 0) + (label ? LABEL_SIZE + 20 : 0) + (lines.length || label ? 28 : 0);
  const aspect = spec.media.aspect && spec.media.aspect > 0 ? spec.media.aspect : 9 / 16;
  const bw = c.inner.w;
  const bh = c.inner.h - capH;
  const fw = Math.round(Math.min(bw, bh * aspect));
  const fh = Math.round(fw / aspect);
  const m = both(frame, tl.lead, end, tone, bt);

  const it = spec.interaction;
  const tI = Math.max(tl.lead + 8, typeof it?.t === "number" ? Math.round((it.t - spec.start) * c.fps) : tl.lead + tl.inF + 12);
  const tg = it?.target && it.target.length >= 2 ? it.target : [0.5, 0.6];
  const tx = (tg[0] > 1 ? tg[0] / 1080 : tg[0]) * fw;
  const ty = (tg[1] > 1 ? tg[1] / 1920 : tg[1]) * fh;
  const ripple = interpolate(frame, [tI, tI + 14], [0, 1], { ...clamp, easing: easeOut });
  const rippleOn = frame >= tI && frame < tI + 14;
  const press = frame >= tI && frame < tI + 5 ? 0.85 : 1;
  const ring = (
    <div style={{ position: "absolute", left: tx - 90 * ripple, top: ty - 90 * ripple, width: 180 * ripple, height: 180 * ripple,
      borderRadius: "50%", border: `5px solid ${surf.hiBg}`, boxSizing: "border-box", opacity: rippleOn ? 1 - ripple : 0 }} />
  );
  let action: React.ReactNode = null;
  let scrollY = 0;
  if (it?.kind === "cursor") {
    const mv = interpolate(frame, [tI - 16, tI], [0, 1], { ...clamp, easing: easeInOut });
    const sx = Math.min(fw - 20, tx + fw * 0.3);
    const sy = Math.min(fh - 20, ty + fh * 0.22);
    const cx = sx + (tx - sx) * mv;
    const cy = sy + (ty - sy) * mv;
    action = (
      <>
        {ring}
        <svg width={44} height={60} viewBox="0 0 22 30" style={{ position: "absolute", left: cx, top: cy, transform: `scale(${press})`,
          transformOrigin: "0 0", opacity: interpolate(frame, [tI - 22, tI - 16], [0, 1], clamp) }}>
          <path d="M1 1 L1 23 L7 18 L11 28 L15 26 L11 17 L19 17 Z" fill={brand.colors.primary} stroke={brand.colors.light} strokeWidth={1.6} strokeLinejoin="round" />
        </svg>
      </>
    );
  } else if (it?.kind === "type") {
    const text = glue(it.text ?? "");
    const typed = Math.floor(interpolate(frame, [tI, tI + text.length * 1.5], [0, text.length], clamp));
    const iw = Math.round(fw * 0.82);
    const ix = Math.max(0, Math.min(fw - iw, tx - iw / 2));
    const fs = Math.round(Math.min(44, fw * 0.06));
    const card = c.surfaces.card;
    action = (
      <div style={{ position: "absolute", left: ix, top: ty - 44, width: iw, height: 88, boxSizing: "border-box", backgroundColor: card.bg,
        border: `3px solid ${surf.hiBg}`, borderRadius: c.radius ? 44 : 6, display: "flex", alignItems: "center", padding: "0 28px",
        fontFamily: fonts.body, fontWeight: 500, fontSize: fs, color: card.text, whiteSpace: "pre", overflow: "hidden",
        opacity: interpolate(frame, [tI - 8, tI], [0, 1], clamp) }}>
        {text.slice(0, typed)}
        <span style={{ display: "inline-block", width: 4, height: Math.round(fs * 1.05), marginLeft: 3, backgroundColor: card.text,
          opacity: caretOn(frame, tI + text.length * 1.5) ? 1 : 0 }} />
      </div>
    );
  } else if (it?.kind === "swipe") {
    const sw = interpolate(frame, [tI, tI + 14], [0, 1], { ...clamp, easing: easeInOut });
    scrollY = -sw * fh * 0.18;
    const dy = -sw * fh * 0.25;
    action = (
      <div style={{ position: "absolute", left: tx - 34, top: ty - 34 + dy, width: 68, height: 68, borderRadius: 34,
        backgroundColor: alpha(brand.colors.light, 0.7), border: `4px solid ${surf.hiBg}`, boxSizing: "border-box",
        opacity: interpolate(frame, [tI - 6, tI, tI + 14, tI + 20], [0, 1, 1, 0], clamp) }} />
    );
  } else if (it) {
    // tap (default): a finger dot fades in, press, ripple
    action = (
      <>
        {ring}
        <div style={{ position: "absolute", left: tx - 34, top: ty - 34, width: 68, height: 68, borderRadius: 34,
          backgroundColor: alpha(brand.colors.light, 0.7), border: `4px solid ${surf.hiBg}`, boxSizing: "border-box",
          transform: `scale(${press})`, opacity: interpolate(frame, [tI - 8, tI, tI + 10, tI + 16], [0, 1, 1, 0], clamp) }} />
      </>
    );
  }
  // swipe: the frame is 22 % taller than the window, the feed moves up and shows what follows, not emptiness
  const media: React.CSSProperties = { width: fw, height: it?.kind === "swipe" ? Math.round(fh * 1.22) : fh, objectFit: "cover",
    objectPosition: "50% 0%", transform: `translateY(${scrollY}px)` };
  const off = Math.round((c.inner.w - fw) / 2); // caption aligned to the left edge of the media frame (shared axis), not to the zone edge
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", width: c.inner.w, paddingLeft: off, boxSizing: "border-box" }}>
      {lines.length || label ? (
        <div style={{ marginBottom: 28 }}>
          <TextBlock lines={lines} label={label} accent={spec.text?.accent} size={capSize} weight={700} font={fonts.heading} labelFont={fonts.body}
            surf={surf} maxWidth={c.inner.w - off} lineMotion={() => m} labelMotion={m} />
        </div>
      ) : null}
      <div style={{ position: "relative", width: fw, height: fh, opacity: m.opacity, transform: m.transform, transformOrigin: "0% 50%" }}>
        <div style={{ position: "absolute", inset: 0, borderRadius: c.radius ? 28 : 8, overflow: "hidden", backgroundColor: c.surfaces.card.bg }}>
          {spec.media.kind === "video" ? (
            <OffthreadVideo src={staticFile(spec.media.file)} muted style={media} />
          ) : (
            <Img src={staticFile(spec.media.file)} style={media} />
          )}
        </div>
        {action}
      </div>
    </div>
  );
};
