// One phrase — one block (references/typography.md, “One phrase — one block”): the parts of one thought sit tight, the gap
// is computed from the font size rather than eyeballed; short words and numbers are glued with a no-break space, line
// breaks follow the meaning; a line that does not fit the width reduces the font size (real width measured with the font —
// @remotion/layout-utils).
//   <Phrase font={font} align="center" maxWidth={960} lines={[{ text: "Stop guessing", size: 72, bg: accent },
//                                                            { text: "NUMBERS", size: 190, weight: 800 }]} />
// Gap between parts of different font sizes: 15–25 px and ≤ 0.35 of the smaller size, between visible edges (plate, cap top).
// Project dependency: @remotion/layout-utils of the same version as remotion (SKILL.md, “Dependencies”).
import React, { useEffect, useRef, useState } from "react";
import { continueRender, delayRender } from "remotion";
import { measureText } from "@remotion/layout-utils";

const NB = " ";
// Never left hanging at the end of a line: prepositions, conjunctions, particles (typography.md, “Line breaks”).
// Russian short words kept with the next word: v, vo, k, ko, s, so, u, o, ob, i, a, no, ne, ni, na, po, za, ot,
// do, iz, bez, dlya, pri, pro, chto, kak, eto, to, vy, my, ya, on, ona, ikh.
const SHORT = new Set(["\u0432", "\u0432\u043e", "\u043a", "\u043a\u043e", "\u0441", "\u0441\u043e", "\u0443", "\u043e", "\u043e\u0431", "\u0438", "\u0430", "\u043d\u043e", "\u043d\u0435", "\u043d\u0438", "\u043d\u0430", "\u043f\u043e", "\u0437\u0430", "\u043e\u0442",
  "\u0434\u043e", "\u0438\u0437", "\u0431\u0435\u0437", "\u0434\u043b\u044f", "\u043f\u0440\u0438", "\u043f\u0440\u043e", "\u0447\u0442\u043e", "\u043a\u0430\u043a", "\u044d\u0442\u043e", "\u0442\u043e", "\u0432\u044b", "\u043c\u044b", "\u044f", "\u043e\u043d", "\u043e\u043d\u0430", "\u0438\u0445"]);
// Russian particles: li, zhe, by, l', zh, b.
const AFTER = new Set(["\u043b\u0438", "\u0436\u0435", "\u0431\u044b", "\u043b\u044c", "\u0436", "\u0431"]); // glued to the previous word

const glueLine = (line: string): string => {
  // ordinary spaces collapse, existing NBSPs are kept; dashes and ellipses are normalized before splitting into words
  const t = line.replace(/[ \t]+/g, " ").trim().replace(/ [-–—] /g, " — ").replace(/\.\.\./g, "…");
  if (!t) return t;
  const w = t.split(" ");
  let out = w[0];
  for (let k = 1; k < w.length; k++) {
    const word = w[k];
    const prev = w[k - 1];
    const prevLast = prev.split(NB).pop() ?? prev; // in a glued token, the last word is what matters
    const bare = prevLast.toLowerCase().replace(/[«"(]/g, "");
    const nb =
      SHORT.has(bare) || // “v rabote” (at work), “ne znayu” (don't know)
      /^\d[\d.,]*%?$/.test(prevLast) || // “12 days”, “60% growth”
      prevLast === "%" || word === "%" || // “60 % growth” — same as “60% growth”
      word === "—" || // before a dash
      AFTER.has(word.toLowerCase().replace(/[.,!?…]/g, ""));
    out += (nb ? NB : " ") + word;
  }
  return out;
};

/** No-break spaces by the rules of Russian typography. Manual line breaks (\n) and existing NBSPs are kept. */
export const glue = (text: string): string => text.split("\n").map(glueLine).join("\n");

/** Lines of up to maxChars characters; what glue() joined is never split, \n forces a break.
 *  A token longer than maxChars stays whole on its own line — fitSize() takes care of the width. */
export const breakLines = (text: string, maxChars: number): string[] => {
  const lines: string[] = [];
  glue(text)
    .split("\n")
    .forEach((para) => {
      let cur: string | null = null;
      para.split(" ").filter(Boolean).forEach((tok) => {
        if (cur !== null && (cur + " " + tok).length <= maxChars) cur = cur + " " + tok;
        else {
          if (cur !== null) lines.push(cur);
          cur = tok;
        }
      });
      if (cur !== null) lines.push(cur);
    });
  return lines;
};

/** Gap between phrase parts of different font sizes, between visible edges. */
export const phraseGap = (smallSize: number): number => Math.round(Math.min(25, 0.35 * smallSize, Math.max(15, 0.25 * smallSize)));

/** Fonts are loaded, so width measurement is honest. @remotion/google-fonts (and loadLocal in brand.ts) add the FontFace
 *  to document.fonts only AFTER it loads, so while the font is still downloading, document.fonts.status is already
 *  "loaded": checking the status alone says “ready” too early, measureText measures the fallback font and caches that
 *  width forever (hook, quote and subtitle lines ran past the edge — found 02.10.2026). We wait until the families appear
 *  in document.fonts and the face count stops growing (3 checks in a row, 60 ms apart), at most 5 s; the render is held
 *  with delayRender. Without a family list we wait until the total number of loaded faces stops growing. */
const fontsOk = new Set<string>();
const familyFaces = (fam: string): number => {
  let n = 0;
  const want = fam.replace(/["']/g, "").trim();
  document.fonts.forEach((f) => {
    if (f.family.replace(/["']/g, "").trim() === want && f.status === "loaded") n++;
  });
  return n;
};
const allFaces = (): number => {
  let n = 0;
  document.fonts.forEach((f) => {
    if (f.status === "loaded") n++;
  });
  return n;
};

export const useFontsLoaded = (families: string[] = []): boolean => {
  const key = Array.from(new Set(families.filter(Boolean))).sort().join("|") || "*";
  const [ready, setReady] = useState(() => fontsOk.has(key));
  const [handle] = useState(() => (fontsOk.has(key) ? null : delayRender(`kit: fonts ${key} for text width measurement`)));
  const cleared = useRef(false);
  useEffect(() => {
    if (handle === null || cleared.current) return;
    let alive = true;
    let last = -1;
    let stable = 0;
    const t0 = Date.now();
    const fams = key === "*" ? [] : key.split("|");
    const tick = () => {
      if (!alive) return;
      const counts = fams.length ? fams.map(familyFaces) : [allFaces()];
      const n = counts.reduce((a, b) => a + b, 0);
      stable = document.fonts.status === "loaded" && counts.every((x) => x > 0) && n === last ? stable + 1 : 0;
      last = n;
      const timeout = Date.now() - t0 > 5000;
      if (stable >= 3 || timeout) {
        if (timeout) console.warn(`kit: fonts ${key} did not appear within 5 s — measuring as is`);
        fontsOk.add(key);
        setReady(true);
        if (!cleared.current) continueRender(handle);
        cleared.current = true;
        return;
      }
      setTimeout(tick, 60);
    };
    tick();
    return () => {
      alive = false;
    };
  }, [handle, key]);
  // unmounted before the fonts were ready — do not hold the render
  useEffect(() => () => {
    if (handle !== null && !cleared.current) {
      cleared.current = true;
      continueRender(handle);
    }
  }, [handle]);
  return ready;
};

/** Former name: fonts are ready for measurement. Pass the families you measure with, so exactly those are awaited. */
export const useFontsReady = (families?: string[]): boolean => useFontsLoaded(families ?? []);

/** Font size at which the line fits maxWidth (including the plate's side padding), but no larger than size. */
export const fitSize = (o: {
  text: string; size: number; font: string; weight: number; maxWidth: number; tracking?: number; padEm?: number;
  upper?: boolean; ready: boolean;
}): number => {
  if (!o.ready || !o.text) return o.size;
  const { width } = measureText({
    text: o.text, fontFamily: o.font, fontSize: o.size, fontWeight: o.weight,
    letterSpacing: o.tracking ? `${o.tracking}em` : undefined, textTransform: o.upper ? "uppercase" : undefined,
  });
  const full = width + 2 * (o.padEm ?? 0) * o.size;
  return full <= o.maxWidth ? o.size : Math.floor((o.size * o.maxWidth) / full);
};

export type PhraseLine = {
  text: string;
  size: number;
  weight?: number;
  color?: string;
  bg?: string; // marker plate under the line: the plate is the visible edge
  upper?: boolean; // all caps (default: if the text is already in caps)
  tracking?: number; // letterSpacing in em; default −0.02 em for large caps
};

const isCaps = (l: PhraseLine) => l.upper ?? l.text === l.text.toUpperCase();
// For caps without a plate the visible edges are the cap top and the baseline: the line box is trimmed to cap height
// (~0.73 em in Inter/Manrope/Onest), otherwise the line's empty margins add another 0.15–0.25 of the font size to the gap.
// The step between lines of one font size (1.05 of the size, typography.md) is made up with a LINE_STEP − CAP_LH margin —
// the only exception to “line height only”.
const CAP_LH = 0.78;
const LOW_LH = 1.05;
const LINE_STEP = 1.05;
const PAD_V = 0.08;
const PAD_H = 0.18;

export const Phrase: React.FC<{
  lines: PhraseLine[];
  font: string;
  align?: "left" | "center" | "right";
  color?: string;
  gap?: number; // forced gap between parts of different font sizes
  maxWidth?: number; // width every line must fit into (default 960 — the frame minus margins)
  style?: React.CSSProperties;
  reveal?: number[]; // 0..1 per line — appearance (lines hold their shared space from the first frame)
}> = ({ lines, font, align = "left", color = "#111111", gap, maxWidth = 960, style, reveal }) => {
  const ready = useFontsReady([font]);
  const fitted = lines.map((l) => {
    const caps = isCaps(l);
    const weight = l.weight ?? (l.size >= 120 ? 800 : 700);
    const tracking = l.tracking ?? (caps && l.size >= 90 ? -0.02 : caps && l.size < 40 ? 0.15 : -0.01);
    const text = glue(l.text);
    const size = fitSize({ text, size: l.size, font, weight, maxWidth, tracking, padEm: l.bg ? PAD_H : 0, upper: l.upper, ready });
    return { ...l, text, caps, weight, tracking, size };
  });
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: align === "left" ? "flex-start" : align === "right" ? "flex-end" : "center", ...style }}>
      {fitted.map((l, k) => {
        const prev = fitted[k - 1];
        const sameSize = prev && Math.abs(prev.size - l.size) < 2;
        // lowercase without a plate: the visible top is the x-height, with ~0.35 of the font size empty above it in the line
        // (measured on Inter 64 px: 22 px) — compensate 0.2 of the size, otherwise “12 days / to results” end up 38 px apart instead of 15–25
        const lowerComp = !l.caps && !l.bg ? Math.round(l.size * 0.2) : 0;
        const mt = !prev
          ? 0
          : sameSize
            ? l.bg || !l.caps ? 0 : Math.round(l.size * (LINE_STEP - CAP_LH)) // same font size: plates touch, lowercase uses line height, caps use a 1.05 step
            : (gap ?? phraseGap(Math.min(prev.size, l.size))) - lowerComp;
        const r = reveal?.[k] ?? 1;
        // large left-aligned caps visually drift right by the letter's side bearing — shift by ~3 % of the font size
        const optical = align === "left" && l.caps && !l.bg && l.size >= 120 ? -Math.round(l.size * 0.03) : 0;
        return (
          <div key={k} style={{ marginTop: mt, marginLeft: optical, opacity: r, transform: `translateY(${(1 - r) * 0.25 * l.size}px)` }}>
            <span
              style={{
                fontFamily: font,
                fontWeight: l.weight,
                fontSize: l.size,
                lineHeight: l.bg ? 1.1 : l.caps ? CAP_LH : LOW_LH,
                letterSpacing: `${l.tracking}em`,
                color: l.color ?? color,
                background: l.bg,
                padding: l.bg ? `${Math.round(l.size * PAD_V)}px ${Math.round(l.size * PAD_H)}px` : 0,
                display: "inline-block",
                whiteSpace: "pre",
                textTransform: l.upper ? "uppercase" : undefined,
              }}
            >
              {l.text}
            </span>
          </div>
        );
      })}
    </div>
  );
};
