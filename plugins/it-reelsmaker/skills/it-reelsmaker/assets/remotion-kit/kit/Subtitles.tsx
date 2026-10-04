// Subtitles in brand colors: “Accent” — 2–3 words on a backing in the primary color, the spoken word in the style's
// marker color; “Plate” — the phrase on the style's marker plate (like the v2 “yellow plate”), words are added as they
// are spoken; “Typewriter” — the whole phrase in 1–2 lines, words not yet spoken at 30 %, a caret after the last spoken
// word, over a soft darkening of the lower part of the frame (no outline, no shadow); “none” — no subtitles. Marker
// colors come from styleLook() in brand.ts.
// Chunks follow the speech: a sentence end, a pause and a change of speaker end a chunk, a long phrase is split where it
// reads as two (a pause, a comma) nearest the middle, never after a short function word or a number (noBreak in
// Phrase.tsx). Geometry: lines are computed in advance by measuring the font (@remotion/layout-utils) — the plate grows
// word by word, lines do not jump. A block never has more than two lines: a chunk that measures three is split again
// by the same rules (T4: a 56-character phrase at 56 px wrapped into three lines and reached y 1455). The block's bottom
// is never below y 1500 (the UI is below): two lines that do not fit from top are shown one at a time.
// Two speakers: a word's "speaker" (cut.py: cut.json → ranges → "speaker"/"speakers") picks its color, in the order of
// captions.speakers (sorted labels): brand.colors.speakers when the profile sets them, otherwise the first speaker in
// the mode's own colors and the second in the accent — "Typewriter" and "Accent" color the words, "Bar" the plate.
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { measureText } from "@remotion/layout-utils";
import { Brand, Look, alpha, styleLook } from "./brand";
import { fitSize, noBreak, useFontsReady } from "./Phrase";

// glue: no space before the word (subs.py: a translation into a script written without spaces, word boundaries marked);
// phrase: the id of a translated phrase (subs.py apply): its words are spread over the phrase by length;
// speaker: who says it (cut.py), the subtitle color per speaker
export type Word = { text: string; start: number; end: number; seg: number; src?: number; glue?: boolean; phrase?: string;
  speaker?: string };
export type Captions = {
  duration: number;
  segments: { i: number; src_start: number; src_end: number; out_start: number; out_dur: number }[];
  words: Word[];
  speakers?: string[]; // the speaker labels in color order (cut.py: sorted)
};
export type SubtitleMode = "accent" | "plate" | "typewriter" | "none";
type Chunk = { words: Word[]; start: number; end: number };

const PAUSE = 0.25; // s: a pause this long ends a chunk (typography.md: by phrases and pauses)
const SENTENCE_END = /[.!?\u2026]["\u00bb\u201d)]*$/;

// The speech in chunks of up to maxWords words / maxChars characters. First the phrases: a cut between segments, a pause
// of PAUSE or more, a sentence end. A phrase that does not fit is split where it reads as two — never inside what noBreak
// keeps together (a short function word or a number with its word), rather not leaving a one-word chunk, at the longest
// pause or after a comma nearest the middle — and each half again if needed. T3: a greedy 52-character cut gave
// "...vacancies in different | fields:" and tails of one or two words.
const wordsLen = (ws: Word[]) => ws.reduce((n, w) => n + w.text.length + 1, 0);

// Where a run of words reads best as two: never inside what noBreak keeps together, rather not leaving a one-word
// part, then at the longest pause or after a dash, colon or comma nearest the middle. Returns the index of the second
// part's first word.
export const bestSplit = (ws: Word[]): number => {
  let best = 1;
  let bestScore: number[] | null = null;
  for (let k = 1; k < ws.length; k++) {
    const a = ws.slice(0, k);
    const b = ws.slice(k);
    const gap = Math.min(PAUSE, Math.max(0, ws[k].start - ws[k - 1].end));
    const strong = /[;:—–]$/.test(ws[k - 1].text) ? 0.6 : /,$/.test(ws[k - 1].text) ? 0.3 : 0;
    const score = [noBreak(ws[k - 1].text, ws[k].text) ? 1 : 0, a.length === 1 || b.length === 1 ? 1 : 0,
      Math.abs(wordsLen(a) - wordsLen(b)) / wordsLen(ws) - 2 * gap - strong];
    if (!bestScore || score[0] < bestScore[0] || (score[0] === bestScore[0] && (score[1] < bestScore[1] ||
      (score[1] === bestScore[1] && score[2] < bestScore[2])))) {
      bestScore = score;
      best = k;
    }
  }
  return best;
};

export const buildChunks = (words: Word[], maxWords = 3, maxChars = 20): Chunk[] => {
  const len = wordsLen;
  // maxChars is a guide ("up to ~52 characters"): a whole phrase up to 10 % longer stays one chunk, the lines are measured anyway
  const fits = (ws: Word[]) => ws.length <= maxWords && len(ws) - 1 <= maxChars * 1.1;
  const phrases: Word[][] = [];
  let cur: Word[] = [];
  words.forEach((w, k) => {
    const prev = words[k - 1];
    // a change of speaker ends a phrase too: one block, one speaker's color
    if (cur.length && prev && (w.seg !== prev.seg || w.start - prev.end >= PAUSE || (w.speaker ?? "") !== (prev.speaker ?? ""))) {
      phrases.push(cur);
      cur = [];
    }
    cur.push(w);
    if (SENTENCE_END.test(w.text)) {
      phrases.push(cur);
      cur = [];
    }
  });
  if (cur.length) phrases.push(cur);
  const split = (ws: Word[]): Word[][] => {
    if (ws.length < 2 || fits(ws)) return [ws];
    const best = bestSplit(ws);
    return [...split(ws.slice(0, best)), ...split(ws.slice(best))];
  };
  const out: Chunk[] = phrases.flatMap(split).map((ws) => ({ words: ws, start: ws[0].start, end: ws[ws.length - 1].end }));
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
const RAMP = 0.25; // s: the typewriter darkening fades out and in inside the windows without subtitles
// line geometry: font size, weight, line height, plate padding (top, bottom, side), gap between plate lines
const GEO = {
  plate: { size: 60, weight: 700, lh: 1.15, padT: 5, padB: 8, padH: 22, gap: 6 },
  accent: { size: 66, weight: 800, lh: 1.15, padT: 6, padB: 10, padH: 22, gap: 0 },
  typewriter: { size: 56, weight: 500, lh: 1.22, padT: 0, padB: 0, padH: 0, gap: 0 },
};
type Geo = (typeof GEO)["plate"];
type Block = Chunk & { lines: Word[][]; size: number; top: number };

const text = (ws: Word[]) => ws.map((w, k) => (k && !w.glue ? " " : "") + w.text).join("");

// windows without subtitles, overlapping or touching ones merged
const mergeWindows = (hide: [number, number][]): [number, number][] => {
  const out: [number, number][] = [];
  [...hide].sort((x, y) => x[0] - y[0]).forEach(([a, b]) => {
    const last = out[out.length - 1];
    if (last && a <= last[1] + 0.05) last[1] = Math.max(last[1], b);
    else out.push([a, b]);
  });
  return out;
};

// The darkening's strength 0..1 at second t: full wherever text can be drawn, so the first frame of a phrase after a
// scene already reads at full contrast (T3: it faded in over 0.25 s while the text came at once — 3.6:1 instead of
// 9.6:1). It fades out after a window starts and back in before it ends, inside the window, where no text is drawn; a
// window at the very start or end of the video has no fade on that side.
export const shadeAt = (t: number, duration: number, windows: [number, number][]): number => {
  if (t < 0 || t >= duration) return 0;
  let k = 1;
  windows.forEach(([a, b]) => {
    if (t < a || t >= b) return;
    const out = a <= 0.001 ? 0 : Math.max(0, 1 - (t - a) / RAMP);
    const back = b >= duration - 0.001 ? 0 : Math.max(0, 1 - (b - t) / RAMP);
    k = Math.min(k, Math.max(out, back));
  });
  return k;
};

// The typewriter caret: a thin bar in the style's accent color, from just below the baseline to the cap height, drawn as
// a box that takes no room in the line. A "|" character in the text color read as the letter l in a sans font
// ("specialistsl"); a bar on the baseline in the text color reads the same, so it differs in color and depth.
const Caret: React.FC<{ on: boolean; color: string }> = ({ on, color }) => (
  <span style={{ display: "inline-block", position: "relative", width: 0, height: "0.72em", verticalAlign: "baseline" }}>
    <span style={{ position: "absolute", left: "0.08em", bottom: "-0.12em", width: "0.08em", height: "0.84em", backgroundColor: color,
      opacity: on ? 1 : 0 }} />
  </span>
);
// height of an n-line block: in “Plate” every line is its own plate, otherwise one shared block
const height = (g: Geo, size: number, n: number) =>
  g === GEO.plate ? n *(size * g.lh + g.padT + g.padB) + (n - 1) * g.gap : n * size * g.lh + g.padT + g.padB;

const toLines = (ws: Word[], g: Geo, font: string, ready: boolean, maxW: number = MAX_W): Word[][] => {
  if (!ready) return [ws]; // do not measure before the font loads: measureText would cache the fallback font's width
  const width = (l: Word[]) =>
    measureText({ text: text(l), fontFamily: font, fontSize: g.size, fontWeight: g.weight, letterSpacing: `${TRACK}px` }).width + 2 * g.padH;
  const lines: Word[][] = [];
  let cur: Word[] = [];
  ws.forEach((w) => {
    if (cur.length && width([...cur, w]) > maxW) {
      // a short function word or a number never ends a line: it moves down with its word
      const keep = cur.length > 1 && noBreak(cur[cur.length - 1].text, w.text) ? [cur.pop() as Word] : [];
      lines.push(cur);
      cur = keep;
    }
    cur.push(w);
  });
  if (cur.length) lines.push(cur);
  if (lines.length !== 2) return lines;
  // two lines: the break that makes them most even (greedy filling left one word on the second line: T4 "I realized
  // that sales | left"), still never after a short function word or a number
  let best = -1;
  let bestW = Infinity;
  for (let k = 1; k < ws.length; k++) {
    if (noBreak(ws[k - 1].text, ws[k].text)) continue;
    const w1 = width(ws.slice(0, k));
    const w2 = width(ws.slice(k));
    if (w1 <= maxW && w2 <= maxW && Math.max(w1, w2) < bestW) {
      bestW = Math.max(w1, w2);
      best = k;
    }
  }
  return best > 0 ? [ws.slice(0, best), ws.slice(best)] : lines;
};

const MAX_LINES = 2; // a subtitle block is one or two lines: the band export records (reels_common.SUB_BLOCK_H) holds two

// The speaker labels in color order: captions.speakers (cut.py writes them sorted), else the words' labels sorted.
export const speakerOrder = (captions: Captions): string[] =>
  captions.speakers?.length ? captions.speakers
    : Array.from(new Set(captions.words.map((w) => w.speaker).filter((s): s is string => !!s))).sort();

const luminance = (hex: string) => {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((x) => x + x).join("") : h, 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const x = v / 255;
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
};
// the text color that reads better on a plate of color bg: dark or light
const inkOn = (bg: string, dark: string, light: string) => {
  const ratio = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  const L = luminance(bg);
  return ratio(L, luminance(dark)) >= ratio(L, luminance(light)) ? dark : light;
};
const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

// The color of speaker k (0, 1, ... in speakerOrder) as text over the video or the primary backing: brand.colors.speakers
// when the profile sets them, otherwise the text color for the first speaker and the accent for the second.
const voiceColor = (brand: Brand, k: number) => {
  const list = brand.colors.speakers?.filter(Boolean) ?? [];
  if (list.length) return list[k % list.length];
  return k % 2 === 0 ? brand.colors.text_on_primary : brand.colors.accent;
};

export const KitSubtitles: React.FC<{
  captions: Captions;
  brand: Brand;
  font: string;
  mode: SubtitleMode;
  hide?: [number, number][]; // windows (s) without subtitles: plates carry the text there, so the component draws nothing in them
  top?: number; // block top; two lines that do not fit above y 1500 are shown one line at a time
  look?: Look; // style (styleLook); defaults to the brand's default style
  // "Typewriter": darkening of the lower part, 0..1; default 0.35; measure it: visual_plan.py shade edit/<id> (the value
  // that gives the text 4.5:1 on the lightest frame of the rough cut)
  shade?: number;
  // "shade": only the darkening (a layer below the scenes, so a card is not darkened), "text": only the words
  part?: "all" | "shade" | "text";
  // s after the speech ends that the last phrase and the darkening stay: the end card fades in over them (ReelKit:
  // its field's fade-in). T4: both vanished when the speech ended, two frames into the logo sting's 8-frame fade
  tail?: number;
  // the "framed" format (ReelKit framedGeometry): the text area the block stays in (left edge, width, bottom) and the
  // window the "Typewriter" darkening is clipped to; absent — x 60–940 down to y 1500 and a full-width darkening
  area?: { x: number; y: number; w: number; h: number } | null;
  clip?: { x: number; y: number; w: number; h: number; r?: number } | null;
}> = ({ captions, brand, font, mode, hide = [], top = 1290, look, shade = 0.35, part = "all", tail = 0, area = null, clip = null }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ready = useFontsReady([font]);
  const plate = mode === "plate";
  const tw = mode === "typewriter";
  const g = plate ? GEO.plate : tw ? GEO.typewriter : GEO.accent;
  const left = area ? area.x : LEFT;
  const maxW = area ? Math.min(MAX_W, area.w) : MAX_W;
  const bottom = area ? Math.min(SUB_BOTTOM, area.y + area.h) : SUB_BOTTOM;
  const end = captions.duration + Math.max(0, tail);
  const hideKey = JSON.stringify(hide);
  // a window that reaches the end of the speech reaches the end of the tail too
  const windows = React.useMemo(() => mergeWindows(hide).map(([a, b]) => [a, b >= captions.duration - 0.001 ? end : b] as [number, number]),
    [hideKey, captions.duration, end]); // eslint-disable-line react-hooks/exhaustive-deps
  const blocks = React.useMemo(() => {
    // a translated phrase (subs.py: its words spread over the phrase by length, not on their spoken words) that the
    // windows cover for more than half is hidden whole: a random tail of it after a scene does not read (T3: "company
    // really needs." after a full-screen phrase)
    const spans = new Map<string, [number, number]>();
    captions.words.forEach((w) => {
      if (!w.phrase) return;
      const s = spans.get(w.phrase);
      spans.set(w.phrase, s ? [Math.min(s[0], w.start), Math.max(s[1], w.end)] : [w.start, w.end]);
    });
    const covered = new Set<string>();
    spans.forEach(([a0, a1], id) => {
      const n = windows.reduce((sum, [a, b]) => sum + Math.max(0, Math.min(a1, b) - Math.max(a0, a)), 0);
      if (n > 0.5 * (a1 - a0)) covered.add(id);
    });
    // a word said inside a window is carried by the scene there; a word still being said when the window ends stays, so the
    // rest of its group shows right after the window (dropping every word that began inside lost 0.4-0.6 s of subtitles
    // after a scene); the component draws nothing inside a window anyway (below)
    const words = captions.words.filter((w) => !(w.phrase && covered.has(w.phrase)) && !hide.some(([a, b]) => w.start >= a && w.end <= b));
    // a chunk that measures more than two lines is split again where it reads as two (bestSplit), each part on its own
    const fit = (ws: Word[]): Word[][] => {
      if (ws.length < 2 || toLines(ws, g, font, ready, maxW).length <= MAX_LINES) return [ws];
      const k = bestSplit(ws);
      return [...fit(ws.slice(0, k)), ...fit(ws.slice(k))];
    };
    const out: Block[] = [];
    // "Typewriter" splits by phrases and pauses (up to ~52 characters as a whole), not by a short character limit
    buildChunks(words, plate ? 4 : tw ? 10 : 3, plate ? 26 : tw ? 52 : 20).forEach((c0) => {
      const pieces = fit(c0.words);
      pieces.forEach((ws, i) => {
        const c = { start: i ? ws[0].start : c0.start, end: i + 1 < pieces.length ? pieces[i + 1][0].start : c0.end };
        const lines = toLines(ws, g, font, ready, maxW);
        // a single long word wider than the frame shrinks the font size (fitSize) instead of running past the edge
        const size = Math.min(g.size, ...lines.map((l) => fitSize({ text: text(l), size: g.size, font, weight: g.weight,
          maxWidth: maxW, padEm: g.padH / g.size, ready })));
        const parts = lines.length > 1 && top + height(g, size, lines.length) > bottom ? lines.map((l) => [l]) : [lines];
        parts.forEach((ls, k) => {
          const next = parts[k + 1];
          out.push({ words: ls.flat(), lines: ls, size, start: k ? ls[0][0].start : c.start, end: next ? next[0][0].start : c.end,
            top: Math.min(top, Math.floor(bottom - height(g, size, ls.length))) });
        });
      });
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [captions, hideKey, windows, plate, tw, font, ready, top, maxW, bottom]);
  const order = React.useMemo(() => speakerOrder(captions), [captions]);
  if (mode === "none") return null;
  const t = frame / fps;
  // the darkening stays between phrases (no flicker) and is at full strength wherever text can be drawn (shadeAt)
  const k = shadeAt(t, end, windows);
  const grad = `linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,${shade}) 40%, rgba(0,0,0,${shade}) 100%)`;
  // "framed": the same gradient (in frame coordinates), seen only through the window
  const shadeEl = tw && part !== "text" && shade > 0 && k > 0 ? (clip ? (
    <div style={{ position: "absolute", left: clip.x, top: clip.y, width: clip.w, height: clip.h, overflow: "hidden", borderRadius: clip.r ?? 0 }}>
      <div style={{ position: "absolute", left: -clip.x, top: top - 220 - clip.y, width: 1080, height: 2140 - top, opacity: k, background: grad }} />
    </div>
  ) : (
    <div style={{ position: "absolute", left: 0, right: 0, top: top - 220, bottom: 0, opacity: k, background: grad }} />
  )) : null;
  if (part === "shade") return shadeEl;
  if (t >= end) return null;
  if (windows.some(([a, b]) => t >= a && t < b)) return null; // a group's tail and its extension never enter a hide window
  const b = blocks.find((c) => t >= c.start - 0.05 && t < c.end);
  if (!b) return shadeEl;
  const l = look ?? styleLook(brand);
  const c = brand.colors;
  const who = (w: Word) => Math.max(0, w.speaker ? order.indexOf(w.speaker) : 0);
  const type: React.CSSProperties = { fontFamily: font, fontWeight: g.weight, fontSize: b.size, lineHeight: g.lh,
    letterSpacing: TRACK, whiteSpace: "pre" };
  const pad = `${g.padT}px ${g.padH}px ${g.padB}px`;
  if (plate) {
    // every line is its own plate; a word appears at its own start time, line positions are set in advance. The first
    // speaker keeps the style's marker plate; another speaker's plate is their color (a block is one speaker's)
    const s = who(b.words[0]);
    const own = brand.colors.speakers?.filter(Boolean)[s];
    const bg = s === 0 ? l.mark : own ?? (same(c.accent, l.mark) ? c.light : c.accent);
    const ink = s === 0 ? l.onMark : inkOn(bg, c.primary, c.text_on_primary);
    return (
      <div style={{ position: "absolute", left, top: b.top, display: "flex", flexDirection: "column", alignItems: "flex-start", gap: g.gap }}>
        {b.lines.map((ln, i) => {
          const shown = ln.filter((w) => w === b.words[0] || t >= w.start - 0.03);
          return shown.length ? (
            <div key={i} style={{ ...type, backgroundColor: bg, color: ink, padding: pad }}>{text(shown)}</div>
          ) : null;
        })}
      </div>
    );
  }
  if (tw) {
    // the whole phrase is placed at once; spoken words come up to full strength, the caret blinks after the last one
    const said = b.words.filter((w) => t >= w.start - 0.03);
    const last = said[said.length - 1];
    const caret = Math.floor(t * 2) % 2 === 0;
    return (
      <>
        {shadeEl}
        <div style={{ position: "absolute", left, top: b.top }}>
          {b.lines.map((ln, i) => (
            <div key={i} style={type}>
              {ln.map((w, k) => (
                <span key={k} style={{ color: voiceColor(brand, who(w)), opacity: said.includes(w) ? 1 : 0.3 }}>
                  {k && !w.glue ? " " : ""}
                  {w.text}
                  {w === last ? <Caret on={caret} color={l.mark} /> : null}
                </span>
              ))}
            </div>
          ))}
        </div>
      </>
    );
  }
  return (
    <div style={{ position: "absolute", left, top: b.top }}>
      <div style={{ ...type, display: "inline-block", backgroundColor: alpha(c.primary, 0.92), padding: pad }}>
        {b.lines.map((ln, i) => (
          <div key={i}>
            {ln.map((w, k) => {
              const idx = b.words.indexOf(w);
              const next = b.words[idx + 1];
              const active = t >= w.start - 0.03 && (next ? t < next.start - 0.03 : true);
              // the word being spoken in the marker color; a speaker whose own color is the marker gets the text color for it
              const voice = voiceColor(brand, who(w));
              return (
                <span key={k} style={{ color: active ? (same(voice, l.mark) ? c.text_on_primary : l.mark) : voice }}>
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
