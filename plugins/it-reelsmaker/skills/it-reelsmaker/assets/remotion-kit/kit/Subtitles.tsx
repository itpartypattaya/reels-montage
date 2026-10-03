// Subtitles in brand colors: “Accent” — 2–3 words on a backing in the primary color, the spoken word in the style's
// marker color; “Plate” — the phrase on the style's marker plate (like the v2 “yellow plate”), words are added as they
// are spoken; “Typewriter” — the whole phrase in 1–2 lines, words not yet spoken at 30 %, a caret after the last spoken
// word, over a soft darkening of the lower part of the frame (no outline, no shadow); “none” — no subtitles. Marker
// colors come from styleLook() in brand.ts.
// Geometry: lines are computed in advance by measuring the font (@remotion/layout-utils) — the plate grows word by word,
// lines do not jump. The block's bottom is never below y 1500 (the UI is below): two lines that do not fit from top are
// shown one at a time.
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { measureText } from "@remotion/layout-utils";
import { Brand, Look, alpha, styleLook } from "./brand";
import { fitSize, useFontsReady } from "./Phrase";

// glue: no space before the word (subs.py: a translation into a script written without spaces, word boundaries marked)
export type Word = { text: string; start: number; end: number; seg: number; src?: number; glue?: boolean };
export type Captions = {
  duration: number;
  segments: { i: number; src_start: number; src_end: number; out_start: number; out_dur: number }[];
  words: Word[];
};
export type SubtitleMode = "accent" | "plate" | "typewriter" | "none";
type Chunk = { words: Word[]; start: number; end: number };

// Russian short words not left at the end of a chunk: i, s, do, po, no, ot, ikh, vy, to, da, nu, v, na, a, k, o, u.
const SHORT = new Set(["\u0438", "\u0441", "\u0434\u043e", "\u043f\u043e", "\u043d\u043e", "\u043e\u0442", "\u0438\u0445", "\u0432\u044b", "\u0442\u043e", "\u0434\u0430", "\u043d\u0443", "\u0432", "\u043d\u0430", "\u0430", "\u043a", "\u043e", "\u0443"]);

export const buildChunks = (words: Word[], maxWords = 3, maxChars = 20): Chunk[] => {
  const out: Chunk[] = [];
  let cur: Word[] = [];
  const len = (ws: Word[]) => ws.reduce((n, w) => n + w.text.length + 1, 0);
  const flush = () => {
    if (cur.length) out.push({ words: cur, start: cur[0].start, end: cur[cur.length - 1].end });
    cur = [];
  };
  words.forEach((w, k) => {
    const prev = words[k - 1];
    if (cur.length && prev && (w.seg !== prev.seg || w.start - prev.end > 0.3)) flush();
    if (cur.length && (cur.length >= maxWords || len(cur) + w.text.length > maxChars)) {
      const tail = cur[cur.length - 1];
      if (cur.length > 1 && SHORT.has(tail.text.toLowerCase())) {
        cur.pop();
        flush();
        cur.push(tail);
      } else flush();
    }
    cur.push(w);
  });
  flush();
  out.forEach((c, k) => {
    const next = out[k + 1];
    c.end = next ? Math.min(next.start, c.end + 0.4) : c.end + 0.5;
  });
  return out;
};

export const SUB_BOTTOM = 1500; // subtitle bottom: below it are 420 px of UI (faces.py UI_BOTTOM)
const LEFT = 60;
const MAX_W = 880; // block width including plate padding
const TRACK = 0.3; // letterSpacing, px
const RAMP = 0.25; // s: the typewriter darkening fades in and out around the windows without subtitles
// line geometry: font size, weight, line height, plate padding (top, bottom, side), gap between plate lines
const GEO = {
  plate: { size: 60, weight: 700, lh: 1.15, padT: 5, padB: 8, padH: 22, gap: 6 },
  accent: { size: 66, weight: 800, lh: 1.15, padT: 6, padB: 10, padH: 22, gap: 0 },
  typewriter: { size: 56, weight: 500, lh: 1.22, padT: 0, padB: 0, padH: 0, gap: 0 },
};
type Geo = (typeof GEO)["plate"];
type Block = Chunk & { lines: Word[][]; size: number; top: number };

const text = (ws: Word[]) => ws.map((w, k) => (k && !w.glue ? " " : "") + w.text).join("");
// height of an n-line block: in “Plate” every line is its own plate, otherwise one shared block
const height = (g: Geo, size: number, n: number) =>
  g === GEO.plate ? n *(size * g.lh + g.padT + g.padB) + (n - 1) * g.gap : n * size * g.lh + g.padT + g.padB;

const toLines = (ws: Word[], g: Geo, font: string, ready: boolean): Word[][] => {
  if (!ready) return [ws]; // do not measure before the font loads: measureText would cache the fallback font's width
  const width = (l: Word[]) =>
    measureText({ text: text(l), fontFamily: font, fontSize: g.size, fontWeight: g.weight, letterSpacing: `${TRACK}px` }).width + 2 * g.padH;
  const lines: Word[][] = [];
  let cur: Word[] = [];
  ws.forEach((w) => {
    if (cur.length && width([...cur, w]) > MAX_W) {
      lines.push(cur);
      cur = [];
    }
    cur.push(w);
  });
  if (cur.length) lines.push(cur);
  return lines;
};

export const KitSubtitles: React.FC<{
  captions: Captions;
  brand: Brand;
  font: string;
  mode: SubtitleMode;
  hide?: [number, number][]; // windows (s) without subtitles: plates carry the text there, so the component draws nothing in them
  top?: number; // block top; two lines that do not fit above y 1500 are shown one line at a time
  look?: Look; // style (styleLook); defaults to the brand's default style
  shade?: number; // “Typewriter”: darkening of the lower part, 0..1 (0.15–0.25 to start, 0.4–0.6 over light clothing or a light wall)
  // "shade": only the darkening (a layer below the scenes, so a card is not darkened), "text": only the words
  part?: "all" | "shade" | "text";
}> = ({ captions, brand, font, mode, hide = [], top = 1290, look, shade = 0.35, part = "all" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ready = useFontsReady([font]);
  const plate = mode === "plate";
  const tw = mode === "typewriter";
  const g = plate ? GEO.plate : tw ? GEO.typewriter : GEO.accent;
  const hideKey = JSON.stringify(hide);
  const blocks = React.useMemo(() => {
    const words = captions.words.filter((w) => !hide.some(([a, b]) => w.start >= a && w.start < b));
    const out: Block[] = [];
    // “Typewriter” splits by phrases and pauses (up to ~52 characters as a whole), not by a short character limit
    buildChunks(words, plate ? 4 : tw ? 10 : 3, plate ? 26 : tw ? 52 : 20).forEach((c) => {
      const lines = toLines(c.words, g, font, ready);
      // a single long word wider than the frame shrinks the font size (fitSize) instead of running past the edge
      const size = Math.min(g.size, ...lines.map((l) => fitSize({ text: text(l), size: g.size, font, weight: g.weight,
        maxWidth: MAX_W, padEm: g.padH / g.size, ready })));
      const parts = lines.length > 1 && top + height(g, size, lines.length) > SUB_BOTTOM ? lines.map((l) => [l]) : [lines];
      parts.forEach((ls, k) => {
        const next = parts[k + 1];
        out.push({ words: ls.flat(), lines: ls, size, start: k ? ls[0][0].start : c.start, end: next ? next[0][0].start : c.end,
          top: Math.min(top, Math.floor(SUB_BOTTOM - height(g, size, ls.length))) });
      });
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [captions, hideKey, plate, tw, font, ready, top]);
  if (mode === "none") return null;
  const t = frame / fps;
  // the darkening stays between phrases (no flicker) and fades out around the windows without subtitles and at the end
  const near = Math.min(t, captions.duration - t, ...hide.map(([a, b]) => (t < a ? a - t : t >= b ? t - b : 0)));
  const shadeEl = tw && part !== "text" && shade > 0 && near > 0 ? (
    <div style={{ position: "absolute", left: 0, right: 0, top: top - 220, bottom: 0, opacity: Math.min(1, near / RAMP),
      background: `linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,${shade}) 40%, rgba(0,0,0,${shade}) 100%)` }} />
  ) : null;
  if (part === "shade") return shadeEl;
  if (t >= captions.duration) return null;
  if (hide.some(([a, b]) => t >= a && t < b)) return null; // a group's tail and its extension never enter a hide window
  const b = blocks.find((c) => t >= c.start - 0.05 && t < c.end);
  if (!b) return shadeEl;
  const l = look ?? styleLook(brand);
  const type: React.CSSProperties = { fontFamily: font, fontWeight: g.weight, fontSize: b.size, lineHeight: g.lh,
    letterSpacing: TRACK, whiteSpace: "pre" };
  const pad = `${g.padT}px ${g.padH}px ${g.padB}px`;
  if (plate) {
    // every line is its own plate; a word appears at its own start time, line positions are set in advance
    return (
      <div style={{ position: "absolute", left: LEFT, top: b.top, display: "flex", flexDirection: "column", alignItems: "flex-start", gap: g.gap }}>
        {b.lines.map((ln, i) => {
          const shown = ln.filter((w) => w === b.words[0] || t >= w.start - 0.03);
          return shown.length ? (
            <div key={i} style={{ ...type, backgroundColor: l.mark, color: l.onMark, padding: pad }}>{text(shown)}</div>
          ) : null;
        })}
      </div>
    );
  }
  const c = brand.colors;
  if (tw) {
    // the whole phrase is placed at once; spoken words come up to full strength, the caret blinks after the last one
    const said = b.words.filter((w) => t >= w.start - 0.03);
    const last = said[said.length - 1];
    const caret = Math.floor(t * 2) % 2 === 0;
    return (
      <>
        {shadeEl}
        <div style={{ position: "absolute", left: LEFT, top: b.top }}>
          {b.lines.map((ln, i) => (
            <div key={i} style={type}>
              {ln.map((w, k) => (
                <span key={k} style={{ color: c.text_on_primary, opacity: said.includes(w) ? 1 : 0.3 }}>
                  {k && !w.glue ? " " : ""}
                  {w.text}
                  {w === last ? <span style={{ opacity: caret ? 1 : 0 }}>|</span> : null}
                </span>
              ))}
            </div>
          ))}
        </div>
      </>
    );
  }
  return (
    <div style={{ position: "absolute", left: LEFT, top: b.top }}>
      <div style={{ ...type, display: "inline-block", backgroundColor: alpha(c.primary, 0.92), padding: pad }}>
        {b.lines.map((ln, i) => (
          <div key={i}>
            {ln.map((w, k) => {
              const idx = b.words.indexOf(w);
              const next = b.words[idx + 1];
              const active = t >= w.start - 0.03 && (next ? t < next.start - 0.03 : true);
              return (
                <span key={k} style={{ color: active ? l.mark : c.text_on_primary }}>
                  {k && !w.glue ? " " : ""}
                  {w.text}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};
