// cta scene — the action from the call to action (references/cta.md) when it is not visible in the frame:
//   tap — a button (interaction.text, otherwise text.lines[1]) is pressed by a finger, brackets close in around it;
//   comment — a code word is typed into the comment field (interaction.text, otherwise the word in quotes « » or “ ” from
//   the CTA lines, otherwise text.lines[1]) and “send” is pressed; bio — the brand's profile header (mark, name) and a tap
//   on the link (interaction.text, otherwise a CTA line that looks like an address: example.com, @handle; none — a tap on
//   the brand name in the header).
// CTA lines not used for the button/field/link are the call itself, large. overlay — a card, full — on a field.
import React from "react";
import { Img, interpolate, staticFile } from "remotion";
import { alpha, logoOnDark } from "../brand";
import { fitSize, glue } from "../Phrase";
import { Brackets, TextBlock, blockSize, caretOn, useFontsLoaded } from "./parts";
import { both, easeOut, progress } from "./tones";
import type { SceneCtx } from "./types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const QUOTED = /[«"„“]([^»"”]+)[»"”]/;
// Link-like line: a domain (Latin or Cyrillic TLD such as .rf, \u0430-\u044f = Russian a–ya), an @handle or an http(s) URL
const isLink = (l: string) => /^\S+\.[a-z\u0430-\u044f]{2,}(\/\S*)?$|^@\S+$|^https?:\/\//i.test(l.trim());

export const CtaAction: React.FC<{ c: SceneCtx }> = ({ c }) => {
  const ready = useFontsLoaded([c.fonts.heading, c.fonts.body]);
  const { spec, frame, tl, tone, bt, surf, fonts, brand } = c;
  const lines = spec.text?.lines?.filter(Boolean) ?? [];
  if (!lines.length) return null;
  const variant = spec.variant ?? "tap";
  const end = tl.n - tl.tail;
  const card = c.shell === "card";
  const it = spec.interaction;
  const tI = Math.max(tl.lead + tl.inF + 4, typeof it?.t === "number" ? Math.round((it.t - spec.start) * c.fps) : tl.lead + tl.inF + 14);
  const headSize = card ? 56 : c.mode === "full" ? 104 : 84;
  const m = both(frame, tl.lead, end, tone, bt);
  const m2 = both(frame, tl.lead + 6, end, tone, bt);
  const head = (ls: string[]) => (
    <TextBlock lines={ls} accent={spec.text?.accent} label={spec.text?.label} size={headSize} font={fonts.heading} labelFont={fonts.body}
      surf={surf} maxWidth={c.inner.w} lineMotion={(k) => both(frame, tl.lead + k * 4, end, tone, bt)} labelMotion={m} />
  );
  const ripple = interpolate(frame, [tI, tI + 14], [0, 1], { ...clamp, easing: easeOut });
  const rippleOn = frame >= tI && frame < tI + 14;
  const tapDot = (x: number | string, y: number | string) => (
    <>
      <div style={{ position: "absolute", left: x, top: y, width: 150 * ripple, height: 150 * ripple, marginLeft: -75 * ripple, marginTop: -75 * ripple,
        borderRadius: "50%", border: `5px solid ${card ? surf.text : surf.hiBg}`, boxSizing: "border-box", opacity: rippleOn ? 1 - ripple : 0 }} />
      <div style={{ position: "absolute", left: x, top: y, width: 60, height: 60, marginLeft: -30, marginTop: -30, borderRadius: 30,
        backgroundColor: alpha(brand.colors.light, 0.75), border: `4px solid ${card ? surf.text : surf.hiBg}`, boxSizing: "border-box",
        transform: `scale(${frame >= tI && frame < tI + 5 ? 0.82 : 1})`, opacity: interpolate(frame, [tI - 8, tI, tI + 10, tI + 16], [0, 1, 1, 0], clamp) }} />
    </>
  );
  const br = progress(frame, tI + 4, 14);

  if (variant === "comment") {
    const q = lines.map((l) => QUOTED.exec(l)).find((x) => !!x);
    const word = glue(it?.text ?? (q ? q[1] : lines[1] ?? ""));
    const headLines = it?.text || q ? lines : [lines[0]];
    const t0 = typeof it?.t === "number" ? tI : tl.lead + tl.inF + 4; // typing starts at the interaction time when the plan sets one
    const typedEnd = t0 + word.length * 2;
    const typed = Math.floor(interpolate(frame, [t0, typedEnd], [0, word.length], clamp));
    const send = typedEnd + 8;
    const fs = card ? 44 : 52;
    const bar = Math.round(fs * 2);
    const fieldBg = card ? surf.line : c.surfaces.card.bg; // on a light card the field is one shade denser, otherwise it is invisible
    const fieldText = card ? surf.text : c.surfaces.card.text;
    const sendRipple = interpolate(frame, [send, send + 14], [0, 1], { ...clamp, easing: easeOut });
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", width: c.inner.w }}>
        {head(headLines)}
        <div style={{ marginTop: 34, display: "flex", alignItems: "center", gap: 18, width: Math.min(c.inner.w, 860), opacity: m2.opacity, transform: m2.transform, transformOrigin: "0% 50%" }}>
          <div style={{ flex: 1, height: bar, boxSizing: "border-box", backgroundColor: fieldBg, borderRadius: c.radius ? bar / 2 : 4, display: "flex",
            alignItems: "center", padding: "0 30px", fontFamily: fonts.body, fontWeight: 600, fontSize: fs, color: fieldText, whiteSpace: "pre", overflow: "hidden" }}>
            {word.slice(0, typed)}
            <span style={{ display: "inline-block", width: 4, height: Math.round(fs * 1.05), marginLeft: 3, backgroundColor: fieldText,
              opacity: caretOn(frame, typedEnd) && frame < send ? 1 : 0 }} />
          </div>
          <div style={{ position: "relative", width: bar, height: bar, borderRadius: bar / 2, backgroundColor: surf.hiBg, flexShrink: 0,
            transform: `scale(${frame >= send && frame < send + 5 ? 0.88 : 1})` }}>
            <div style={{ position: "absolute", left: bar * 0.38, top: bar * 0.28, width: 0, height: 0, borderTop: `${bar * 0.22}px solid transparent`,
              borderBottom: `${bar * 0.22}px solid transparent`, borderLeft: `${bar * 0.32}px solid ${surf.hiText}` }} />
            <div style={{ position: "absolute", left: bar / 2 - 80 * sendRipple, top: bar / 2 - 80 * sendRipple, width: 160 * sendRipple, height: 160 * sendRipple,
              borderRadius: "50%", border: `5px solid ${surf.hiBg}`, boxSizing: "border-box", opacity: frame >= send && frame < send + 14 ? 1 - sendRipple : 0 }} />
          </div>
        </div>
      </div>
    );
  }

  if (variant === "bio") {
    const logo = logoOnDark(brand);
    const own = it?.text ?? lines.find(isLink) ?? "";
    const link = glue(own);
    const headLines = lines.filter((l) => l !== own);
    const av = card ? 104 : 132;
    const nameSize = card ? 46 : 58;
    const linkSize = blockSize({ lines: [link], size: card ? 44 : 54, font: fonts.body, weight: 600, maxWidth: c.inner.w - av - 40, ready });
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", width: c.inner.w }}>
        {headLines.length ? head(headLines) : null}
        <div style={{ marginTop: headLines.length ? 40 : 0, display: "flex", alignItems: "center", gap: 30, opacity: m2.opacity, transform: m2.transform, transformOrigin: "0% 50%" }}>
          <div style={{ width: av, height: av, borderRadius: av / 2, backgroundColor: card ? brand.colors.primary : surf.soft, flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
            {logo ? <Img src={staticFile(logo)} style={{ width: av * 0.62, height: av * 0.62, objectFit: "contain" }} />
              : <span style={{ fontFamily: fonts.heading, fontWeight: 800, fontSize: av * 0.42, color: brand.colors.text_on_primary }}>{brand.name.charAt(0)}</span>}
          </div>
          {link ? (
            <div>
              <div style={{ fontFamily: fonts.heading, fontWeight: 800, fontSize: nameSize, lineHeight: 1.1, color: surf.text }}>{glue(brand.name)}</div>
              <div style={{ position: "relative", display: "inline-block", marginTop: 10, padding: "6px 14px", marginLeft: -14 }}>
                <span style={{ fontFamily: fonts.body, fontWeight: 600, fontSize: linkSize, color: card ? surf.text : surf.accent, whiteSpace: "pre",
                  textDecoration: "underline", textUnderlineOffset: "0.18em", textDecorationThickness: "0.06em" }}>{link}</span>
                {tapDot("55%", "55%")}
                <Brackets x={0} y={0} w="100%" h="100%" progress={br} color={card ? surf.text : surf.accent} size={24} stroke={4} />
              </div>
            </div>
          ) : (
            // no address in the plan — do not make one up: tap on the profile header (brand name), brackets around it
            <div style={{ position: "relative", display: "inline-block", padding: "10px 18px", marginLeft: -18 }}>
              <div style={{ fontFamily: fonts.heading, fontWeight: 800, fontSize: nameSize, lineHeight: 1.1, color: surf.text, whiteSpace: "pre" }}>
                {glue(brand.name)}
              </div>
              {tapDot("50%", "55%")}
              <Brackets x={0} y={0} w="100%" h="100%" progress={br} color={card ? surf.text : surf.accent} size={24} stroke={4} />
            </div>
          )}
        </div>
      </div>
    );
  }

  // tap: button
  const btn = glue(it?.text ?? lines[1] ?? "");
  // button width: text + 1 em padding on each side + 14 px outer margin on each side — all within c.inner.w
  const btnSize = fitSize({ text: btn, size: card ? 46 : 58, font: fonts.body, weight: 700, maxWidth: c.inner.w - 28, padEm: 1, ready });
  // the second CTA line (when the button has its own text) is the clarifier: smaller and muted, so a long clarifier does
  // not shrink the main line (references/cta.md: main 52–60 px, clarifier 34–38 px)
  const sub = it?.text && lines[1] ? glue(lines[1]) : "";
  const subSize = Math.min(Math.round(headSize * 0.64), fitSize({ text: sub, size: Math.round(headSize * 0.64), font: fonts.body, weight: 500,
    maxWidth: c.inner.w, ready }));
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", width: c.inner.w }}>
      {head([lines[0]])}
      {sub ? (
        <div style={{ marginTop: 14, fontFamily: fonts.body, fontWeight: 500, fontSize: subSize, lineHeight: 1.2, whiteSpace: "pre", color: surf.text,
          opacity: 0.72 * m2.opacity, transform: m2.transform }}>{sub}</div>
      ) : null}
      {btn ? (
        <div style={{ position: "relative", marginTop: 38, padding: 14, opacity: m2.opacity, transform: m2.transform, transformOrigin: "0% 50%" }}>
          <div style={{ fontFamily: fonts.body, fontWeight: 700, fontSize: btnSize, lineHeight: 1.1, whiteSpace: "pre", color: surf.hiText,
            backgroundColor: surf.hiBg, padding: "0.45em 1em", borderRadius: c.radius ? 999 : 0, transform: `scale(${frame >= tI && frame < tI + 5 ? 0.96 : 1})` }}>
            {btn}
          </div>
          {tapDot("62%", "58%")}
          <Brackets x={0} y={0} w="100%" h="100%" progress={br} color={surf.accent} size={28} stroke={5} />
        </div>
      ) : null}
    </div>
  );
};
