// Shared scene parts: surfaces in brand colors, the “one phrase — one block” text block (typography.md), the caps label,
// focus brackets, matching scene words to speech, numbers. Colors come only from the brand profile and style (Brand, Look), no HEX.
import React from "react";
import { Img, staticFile } from "remotion";
import { measureText } from "@remotion/layout-utils";
import { Brand, Look, alpha } from "../brand";
import type { Word } from "../Subtitles";
import { fitSize, glue, phraseGap, useFontsLoaded } from "../Phrase";
import type { Motion } from "./tones";
import type { SceneValue, Surface } from "./types";

// ── colors ──
const rgb = (c: string): [number, number, number] | null => {
  const h = c.trim().replace("#", "");
  if (!/^[0-9a-f]{3}([0-9a-f]{3})?$/i.test(h)) return null;
  const n = parseInt(h.length === 3 ? h.split("").map((x) => x + x).join("") : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const lum = (c: [number, number, number]) => {
  const f = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
};
/** WCAG contrast of two HEX colors (a non-HEX value is treated as having enough contrast). */
export const contrast = (a: string, b: string): number => {
  const x = rgb(a);
  const y = rgb(b);
  if (!x || !y) return 21;
  const [l1, l2] = [lum(x), lum(y)].sort((p, q) => q - p);
  return (l1 + 0.05) / (l2 + 0.05);
};
// Distinguishability of fills (not text): a yellow marker on a near-white card barely differs in luminance (1.04) but
// stands out by hue — that is the signature v2 plate. We measure distance in RGB: below 48 the plate merges with the card.
const distinct = (a: string, b: string): boolean => {
  const x = rgb(a);
  const y = rgb(b);
  if (!x || !y) return true;
  return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]) >= 48;
};

/** Scene surfaces: a field in the primary color, a light card, a field in the style's marker color. The accent is only the
 *  style's marker (one accent color per video, references/brands.md): in style v2 it is yellow, and the brand's teal never appears in v2 scenes. */
export const surfaces = (b: Brand, look: Look): { field: Surface; card: Surface; mark: Surface } => {
  const c = b.colors;
  const markOnCard = distinct(look.mark, c.light);
  // the field: primary by default; brand.looks[<style>].field sets another one (a light field: text in the primary color)
  const fbg = look.field ?? c.primary;
  const ftx = look.field ? (contrast(c.primary, fbg) >= 4.5 ? c.primary : c.text_on_primary) : c.text_on_primary;
  const markOnField = !look.field || distinct(look.mark, fbg);
  return {
    field: {
      kind: "field", bg: fbg, text: ftx, hiBg: markOnField ? look.mark : ftx, hiText: markOnField ? look.onMark : fbg,
      accent: contrast(look.mark, fbg) >= 3 ? look.mark : ftx,
      muted: alpha(ftx, 0.64), soft: alpha(ftx, 0.1), line: alpha(ftx, 0.24),
    },
    card: {
      kind: "card", bg: c.light, text: c.primary, hiBg: markOnCard ? look.mark : c.primary,
      hiText: markOnCard ? look.onMark : c.text_on_primary,
      accent: contrast(look.mark, c.light) >= 3 ? look.mark : c.primary,
      muted: alpha(c.primary, 0.6), soft: alpha(c.primary, 0.07), line: alpha(c.primary, 0.16),
    },
    mark: {
      kind: "mark", bg: look.mark, text: look.onMark, hiBg: look.onMark, hiText: look.mark, accent: look.onMark,
      muted: alpha(look.onMark, 0.62), soft: alpha(look.onMark, 0.1), line: alpha(look.onMark, 0.25),
    },
  };
};

// ── words and speech ──
// Cyrillic "yo" is normalized to "ye" so that both spellings match.
export const norm = (s: string): string => s.toLowerCase().replace(/\u0451/g, "\u0435").replace(/[^\p{L}\p{N}]+/gu, "");
export const tokens = (s: string): string[] => glue(s).split(/[  ]+/).filter((t) => norm(t) !== "");

/** Time (s) of each phrase word from the scene's speech: words are searched in order; not found → null (spread evenly later). */
/** Time of each scene word in the speech: the first identical word after the previous one, only within the scene window
 *  [from − 0.3; to] (otherwise a word spoken earlier in the video would “appear” at once). visual_plan.py word_times computes the same. */
export const wordTimes = (toks: string[], words: Word[], from = -Infinity, to = Infinity): (number | null)[] => {
  const ws: { n: string; start: number }[] = [];
  words.filter((w) => w.start >= from - 0.3 && w.start <= to).forEach((w) => w.text.split(/\s+/).forEach((t) => {
    const n = norm(t);
    if (n) ws.push({ n, start: w.start });
  }));
  let j = 0;
  return toks.map((tok) => {
    const n = norm(tok);
    for (let i = j; i < ws.length; i++) {
      if (ws[i].n === n) {
        j = i + 1;
        return ws[i].start;
      }
    }
    return null;
  });
};

// ── numbers ──
/** 12 → “12”, 3.5 → “3,5” (decimal comma in the output); from 10000 up, a no-break space between digit groups. */
export const fmtNumber = (v: number, decimals = 0): string => {
  const fixed = Math.abs(v).toFixed(Math.max(0, decimals));
  const [int, frac] = fixed.split(".");
  const grouped = int.length >= 5 ? int.replace(/\B(?=(\d{3})+(?!\d))/g, " ") : int;
  return `${v < 0 ? "−" : ""}${grouped}${frac ? "," + frac : ""}`;
};

// ── fonts loaded? ── — the shared useFontsLoaded hook lives in Phrase.tsx (ReelKit and the subtitles use it too)
export { useFontsLoaded };

// ── big number with a counter ──
// Digits are monospaced (tabular-nums: the counter does not jitter); the final value reserves the space and the counting
// value sits at its right edge, so the suffix stays attached to the number (T6: “6   days” mid-count, the number at the
// left of a slot sized for “14”). A suffix word (“ minutes”, “ days”) is 0.42 of the font size on the baseline; a sign
// (“+”, “%”) uses the same size as the digits.
const sufWord = (s: string) => s.trim().length > 2;
const measureNum = (v: SceneValue, size: number, font: string) => {
  const d = v.decimals ?? 0;
  const digits = `${v.prefix ?? ""}${fmtNumber(v.to, d)}`;
  const suf = v.suffix ?? "";
  const word = sufWord(suf);
  const w = (t: string, s: number, wt: number) => (t ? measureText({ text: t, fontFamily: font, fontSize: s, fontWeight: wt, letterSpacing: "-0.02em",
    fontVariantNumeric: "tabular-nums" }).width : 0);
  return w(digits + (word ? "" : suf), size, 800) + (word ? 0.12 * size + w(suf.trim(), size * 0.42, 700) : 0);
};
/** Number font size: no larger than want and fits maxWidth (measured with the font, monospaced digits). */
export const bigNumberSize = (v: SceneValue, want: number, font: string, maxWidth: number, ready: boolean): number => {
  if (!ready) return want;
  const w = measureNum(v, want, font);
  return w <= maxWidth ? want : Math.floor((want * maxWidth) / w);
};
export const BigNumber: React.FC<{ v: SceneValue; p: number; size: number; font: string; color: string; sufColor?: string }> = ({
  v, p, size, font, color, sufColor,
}) => {
  const d = v.decimals ?? 0;
  const from = v.from ?? 0;
  const val = from + (v.to - from) * p;
  const pre = v.prefix ?? "";
  const fin = `${pre}${fmtNumber(v.to, d)}`;
  const now = `${pre}${fmtNumber(d ? val : Math.round(val), d)}`;
  const suf = v.suffix ?? "";
  const word = sufWord(suf);
  const num: React.CSSProperties = { fontFamily: font, fontWeight: 800, fontSize: size, lineHeight: 1, letterSpacing: "-0.02em",
    fontVariantNumeric: "tabular-nums", whiteSpace: "pre", color };
  return (
    <span style={{ display: "inline-flex", alignItems: "baseline" }}>
      <span style={{ ...num, position: "relative", display: "inline-block" }}>
        <span style={{ visibility: "hidden" }}>{fin}</span>
        <span style={{ position: "absolute", right: 0, top: 0 }}>{now}</span>
      </span>
      {suf ? (
        word ? <span style={{ ...num, fontSize: Math.round(size * 0.42), fontWeight: 700, letterSpacing: "-0.01em", marginLeft: Math.round(size * 0.12),
          color: sufColor ?? color }}>{glue(suf.trim())}</span>
          : <span style={{ ...num, color }}>{suf}</span>
      ) : null}
    </span>
  );
};

// ── sizes ──
/** How many lines the text takes at the given width (greedy word wrap; what glue() joined is never split). */
export const wrapCount = (text: string, font: string, size: number, weight: number, width: number, ready: boolean): number => {
  const parts = glue(text).split(" ");
  if (!ready) return Math.max(1, Math.ceil((text.length * size * 0.55) / width));
  const w = (t: string) => measureText({ text: t, fontFamily: font, fontSize: size, fontWeight: weight }).width;
  let lines = 1;
  let cur = "";
  parts.forEach((p) => {
    const t = cur ? `${cur} ${p}` : p;
    if (cur && w(t) > width) {
      lines += 1;
      cur = p;
    } else cur = t;
  });
  return lines;
};

/** Font size at which the texts (each its own wrapped paragraph) fit the width and the total height. */
export const fitWrapped = (o: {
  texts: string[]; font: string; weight: number; size: number; width: number; height: number; lh: number; gap: number;
  extra?: number; ready: boolean; min?: number;
}): number => {
  const min = o.min ?? 28;
  // the longest glued word must fit on a line in one piece
  const longest = o.texts.map((t) => glue(t).split(" ")).reduce((a, b) => a.concat(b), [] as string[])
    .reduce((a, b) => (b.length > a.length ? b : a), "");
  for (let s = o.size; s > min; s -= 2) {
    if (o.ready && longest && measureText({ text: longest, fontFamily: o.font, fontSize: s, fontWeight: o.weight }).width > o.width) continue;
    const h = o.texts.reduce((acc, t) => acc + wrapCount(t, o.font, s, o.weight, o.width, o.ready) * s * o.lh, 0) +
      o.gap * Math.max(0, o.texts.length - 1) + (o.extra ?? 0);
    if (h <= o.height) return s;
  }
  return min;
};

// ── caps label ──
export const LABEL_SIZE = 28;
// Caps label → large line: the “≤ 0.35 of the smaller part's font size” rule gives 10 px for a 28 px label, which looks
// cramped; we take 14 px (label above a plate), still smaller than any outer gap
export const LABEL_GAP = Math.max(14, phraseGap(LABEL_SIZE));
/** Caps label above the text. maxWidth is the zone width: a long label (0.2 em tracking + plate padding) shrinks its font
 *  size instead of running past x 960. */
export const Label: React.FC<{ text: string; font: string; surf: Surface; chip?: Surface | null; size?: number; motion?: Motion;
  align?: "left" | "center"; maxWidth?: number }> = ({ text, font, surf, chip, size = LABEL_SIZE, motion, align = "left", maxWidth }) => {
  const ready = useFontsLoaded([font]);
  const fs = maxWidth ? fitSize({ text: glue(text), size, font, weight: chip ? 700 : 600, maxWidth: maxWidth - (chip ? 34 : 0),
    tracking: 0.2, upper: true, ready }) : size;
  return (
  <div style={{ textAlign: align, opacity: motion?.opacity ?? 1, transform: motion?.transform, transformOrigin: align === "left" ? "0% 50%" : "50% 50%" }}>
    <span style={{ display: "inline-block", fontFamily: font, fontWeight: chip ? 700 : 600, fontSize: fs, lineHeight: 1,
      letterSpacing: "0.2em", textTransform: "uppercase", whiteSpace: "pre", color: chip ? chip.text : surf.muted,
      backgroundColor: chip ? chip.bg : undefined, padding: chip ? "10px 14px 10px 20px" : 0 }}>
      {glue(text)}
    </span>
  </div>
  );
};

// ── text block: label + lines of one font size, the accent word on a plate ──
const QUOTE_OPEN = /^[«"„“]/;
const QUOTE_CLOSE = /[»"”]$/;
const CYRILLIC = /[\u0400-\u04FF]/;

export type TextBlockProps = {
  lines: string[];
  accent?: string | null;
  label?: string | null;
  size: number; // desired line font size; a line wider than maxWidth reduces it (measured with the font)
  font: string;
  labelFont: string;
  weight?: number;
  surf: Surface;
  maxWidth: number;
  align?: "left" | "center";
  plates?: boolean; // every line on a marker plate (per video); with an accent and a chip: the accent on the marker, the rest on the chip's light plate
  quote?: boolean; // quotes around the text: « » for Cyrillic, “ ” for other scripts
  chip?: Surface | null; // label on a light plate (per video)
  lineMotion?: (k: number) => Motion;
  labelMotion?: Motion;
  // type: how many characters of line k are already typed (the rest keeps its space but is invisible)
  typed?: (k: number) => number;
  caret?: { k: number; on: boolean; color: string } | null;
};

/** Line font size of the block (what TextBlock will draw), so neighboring elements can align to it. */
export const blockSize = (o: { lines: string[]; size: number; font: string; weight?: number; maxWidth: number; plates?: boolean;
  accent?: string | null; quote?: boolean; ready: boolean }): number => {
  const weight = o.weight ?? (o.size >= 110 ? 800 : 700);
  return Math.min(o.size, ...prepLines(o.lines, o.quote).map((l) =>
    fitSize({ text: l, size: o.size, font: o.font, weight, maxWidth: o.maxWidth, padEm: o.plates ? 0.2 : splitAccent(l, o.accent) ? 0.18 : 0,
      tracking: -0.01, ready: o.ready })));
};

const prepLines = (lines: string[], quote?: boolean): string[] => {
  const ls = lines.map((l) => glue(l));
  if (quote && ls.length) {
    // guillemets for Cyrillic text, curly double quotes for every other script
    const [open, close] = CYRILLIC.test(ls.join(" ")) ? ["«", "»"] : ["“", "”"];
    if (!QUOTE_OPEN.test(ls[0])) ls[0] = open + ls[0];
    const last = ls.length - 1;
    if (!QUOTE_CLOSE.test(ls[last])) ls[last] = ls[last] + close;
  }
  return ls;
};

// find the accent in the line, ignoring case and no-break spaces
const splitAccent = (line: string, accent?: string | null): [string, string, string] | null => {
  if (!accent) return null;
  const a = glue(accent).toLowerCase().replace(/ /g, " ");
  const l = line.toLowerCase().replace(/ /g, " ");
  const i = l.indexOf(a);
  if (i < 0 || !a) return null;
  return [line.slice(0, i), line.slice(i, i + a.length), line.slice(i + a.length)];
};

export const TextBlock: React.FC<TextBlockProps> = (p) => {
  const ready = useFontsLoaded([p.font, p.labelFont]);
  const weight = p.weight ?? (p.size >= 110 ? 800 : 700);
  const lines = prepLines(p.lines, p.quote);
  const size = blockSize({ ...p, weight, ready });
  const lh = p.plates ? 1.08 : 1.1;
  // Label → lines gap between visible edges (typography.md): LABEL_GAP minus the empty space below the label caps (~0.14 of
  // its font size) and above the line's letters (for a plate the visible edge is the plate itself, for text ~0.19 of the font size)
  const mt = p.label ? Math.round(LABEL_GAP - 0.14 * LABEL_SIZE - (p.plates ? 0 : 0.19 * size)) + (p.chip ? 4 : 0) : 0;
  const align = p.align ?? "left";
  const plate: React.CSSProperties = { backgroundColor: p.surf.hiBg, color: p.surf.hiText, boxDecorationBreak: "clone",
    WebkitBoxDecorationBreak: "clone" };
  // one accent per block (typography.md): the first line that has it
  const accLine = p.accent ? lines.findIndex((l) => splitAccent(l, p.accent)) : -1;
  // plates with an accent: the other words on the light plate (the chip), the accent alone on the style's marker - the same
  // split as on a field, where only the accent has a plate. Every line on the marker hid the accent (a hook over the video
  // in the brand style: the accent word looked like the rest). One color, no size change: accent color OR size, not both.
  const lightPlates = !!p.plates && accLine >= 0 && !!p.chip;
  const base: React.CSSProperties = lightPlates && p.chip ? { ...plate, backgroundColor: p.chip.bg, color: p.chip.text } : plate;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: align === "left" ? "flex-start" : "center", textAlign: align }}>
      {p.label ? <Label text={p.label} font={p.labelFont} surf={p.surf} chip={p.chip} motion={p.labelMotion} align={align}
        maxWidth={p.maxWidth} /> : null}
      <div style={{ marginTop: mt, display: "flex", flexDirection: "column", alignItems: align === "left" ? "flex-start" : "center" }}>
        {lines.map((l, k) => {
          const m = p.lineMotion?.(k);
          const n = p.typed ? p.typed(k) : l.length;
          const shown = l.slice(0, n);
          const rest = l.slice(n);
          const caret = p.caret && p.caret.k === k ? (
            <span style={{ display: "inline-block", width: Math.max(4, Math.round(size * 0.07)), height: Math.round(size * 0.9),
              marginLeft: Math.round(size * 0.04), verticalAlign: "-0.12em", backgroundColor: p.caret.color, opacity: p.caret.on ? 1 : 0 }} />
          ) : null;
          const type: React.CSSProperties = { fontFamily: p.font, fontWeight: weight, fontSize: size, lineHeight: lh,
            letterSpacing: "-0.01em", whiteSpace: "pre", color: p.surf.text };
          let body: React.ReactNode;
          const acc = k === accLine ? splitAccent(l, p.accent) : null;
          if (p.plates && !(lightPlates && acc)) {
            body = (
              <span style={{ ...type, ...base, display: "inline-block", padding: "0.05em 0.2em 0.08em" }}>
                {shown}
                {caret}
                {rest ? <span style={{ visibility: "hidden" }}>{rest}</span> : null}
              </span>
            );
          } else {
            // line = [before, accent, after]; every part holds its space from the first frame, the accent plate appears once it is fully typed
            const segs = acc ? acc : [l, "", ""];
            // on a light plate the marker fills the plate's height and reaches its edge at the line's start or end; the
            // negative margins keep the line's width as measured
            const lp = segs[0] ? 0.12 : 0.2;
            const rp = segs[2] ? 0.12 : 0.2;
            const accStyle: React.CSSProperties = p.plates
              ? { display: "inline-block", padding: `0.05em ${rp}em 0.08em ${lp}em`, margin: `-0.05em -${rp}em -0.08em -${lp}em` }
              : { display: "inline-block", lineHeight: 1, padding: "0.03em 0.18em 0.1em" };
            let off = 0;
            body = (
              <span style={{ ...type, ...(p.plates ? { ...base, padding: "0.05em 0.2em 0.08em" } : {}), display: "inline-block" }}>
                {segs.map((s, i) => {
                  const from = off;
                  off += s.length;
                  if (!s) return null;
                  const vis = Math.max(0, Math.min(s.length, n - from));
                  const here = n > from && n <= from + s.length; // the caret is in this part
                  const inner = (
                    <>
                      {s.slice(0, vis)}
                      {here || (n === 0 && i === 0) ? caret : null}
                      {vis < s.length ? <span style={{ visibility: "hidden" }}>{s.slice(vis)}</span> : null}
                    </>
                  );
                  return i === 1 ? (
                    <span key={i} style={{ ...(vis >= s.length ? plate : {}), ...accStyle }}>{inner}</span>
                  ) : (
                    <React.Fragment key={i}>{inner}</React.Fragment>
                  );
                })}
              </span>
            );
          }
          return (
            <div key={k} style={{ opacity: m?.opacity ?? 1, transform: m?.transform, transformOrigin: align === "left" ? "0% 50%" : "50% 50%" }}>
              {body}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── focus brackets ⌜⌝⌞⌟: converge from the edges (progress 0 → 60 px apart, 1 → in place) ──
export const Brackets: React.FC<{ x: number; y: number; w: number | string; h: number | string; progress: number; color: string; size?: number;
  stroke?: number }> = ({ x, y, w, h, progress, color, size = 34, stroke = 6 }) => {
  const spread = (1 - progress) * 60;
  const c: React.CSSProperties = { position: "absolute", width: size, height: size, borderColor: color, borderStyle: "solid", borderWidth: 0 };
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, opacity: progress }}>
      <div style={{ ...c, left: -spread, top: -spread, borderLeftWidth: stroke, borderTopWidth: stroke }} />
      <div style={{ ...c, right: -spread, top: -spread, borderRightWidth: stroke, borderTopWidth: stroke }} />
      <div style={{ ...c, left: -spread, bottom: -spread, borderLeftWidth: stroke, borderBottomWidth: stroke }} />
      <div style={{ ...c, right: -spread, bottom: -spread, borderRightWidth: stroke, borderBottomWidth: stroke }} />
    </div>
  );
};

/** Icon (media) revealed by a top-to-bottom mask. Library icons are light, made for a dark background: on a light
 *  surface (card, marker field) we draw its silhouette in the surface's text color (CSS mask from the file's alpha). */
export const Icon: React.FC<{ file: string; h: number; maxW: number; surf: Surface; reveal: number; aspect?: number | null; style?: React.CSSProperties }> = ({
  file, h, maxW, surf, reveal, aspect, style,
}) => {
  const clip = `inset(0 0 ${(1 - reveal) * 100}% 0)`;
  if (surf.kind === "field") {
    return <Img src={staticFile(file)} style={{ height: h, width: "auto", maxWidth: maxW, objectFit: "contain", clipPath: clip, ...style }} />;
  }
  const w = Math.min(maxW, Math.round(h * (aspect && aspect > 0 ? aspect : 1)));
  const url = `url("${staticFile(file)}")`;
  return (
    <div style={{ width: w, height: h, backgroundColor: surf.text, WebkitMaskImage: url, maskImage: url, WebkitMaskSize: "contain", maskSize: "contain",
      WebkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat", WebkitMaskPosition: "left center", maskPosition: "left center", clipPath: clip, ...style }} />
  );
};

/** Caret blink: always visible while typing, then 15 frames on / 15 off. */
export const caretOn = (frame: number, typingEnd: number) => frame < typingEnd || Math.floor((frame - typingEnd) / 15) % 2 === 0;

/** Text-free mini resume card (avatar + lines) for the “out of many — a few” grid. */
export const MiniCard: React.FC<{ w: number; h: number; bg: string; line: string; dot: string; radius: number }> = ({ w, h, bg, line, dot, radius }) => {
  const pad = w * 0.09;
  const av = h * 0.3;
  const bar = (left: number, top: number, width: number): React.ReactNode => (
    <div style={{ position: "absolute", left, top, width, height: Math.max(6, h * 0.07), borderRadius: 4, backgroundColor: line }} />
  );
  return (
    <div style={{ position: "relative", width: w, height: h, borderRadius: radius, backgroundColor: bg }}>
      <div style={{ position: "absolute", left: pad, top: pad, width: av, height: av, borderRadius: av / 2, backgroundColor: dot }} />
      {bar(pad * 1.6 + av, pad + av * 0.12, w * 0.42)}
      {bar(pad * 1.6 + av, pad + av * 0.58, w * 0.26)}
      {bar(pad, h * 0.64, w - pad * 2)}
      {bar(pad, h * 0.8, (w - pad * 2) * 0.62)}
    </div>
  );
};
