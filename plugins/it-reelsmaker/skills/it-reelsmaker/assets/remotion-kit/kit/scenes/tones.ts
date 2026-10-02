// Scene tones: entry and exit pace (references/scenes.md; the same numbers are in reel-defaults.json → scene_tones).
// enter()/exit() → { opacity, transform } for a scene element. Bounce (spring with low damping) only if the brand tone
// allows overshoot; hype shake only with brand.tone.shake. Otherwise a calm ease-out with no bounce
// (brand.md, calm motion: Easing.out(cubic) or spring with damping 200).
import { Easing, interpolate, spring } from "remotion";
import type { Brand } from "../brand";
import type { Word } from "../Subtitles";
import { Loudness, ResolvedTone, SceneMode, SceneSpec, SceneTone, SceneTransition, Timeline, readBrandTone } from "./types";

export type EnterKind = "rise" | "fade" | "scale" | "slide" | "slam" | "zoom" | "cut";
export type ToneRow = {
  in: number; // entry, frames
  out: number; // exit, frames
  hold: number; // hold after the last word, s
  enter: EnterKind;
  transition: SceneTransition; // default scene transition
  overshoot: boolean; // bounce, if the brand allows it
};

export const SCENE_TONES: Record<SceneTone, ToneRow> = {
  calm: { in: 14, out: 9, hold: 0.4, enter: "rise", transition: "fade", overshoot: false }, // rise 30 px + opacity
  deadpan: { in: 18, out: 12, hold: 0.6, enter: "fade", transition: "fade", overshoot: false }, // opacity only
  cinematic: { in: 16, out: 10, hold: 0.5, enter: "scale", transition: "fade", overshoot: false }, // 0.95 → 1 + opacity
  feature: { in: 10, out: 8, hold: 0.4, enter: "slide", transition: "slide", overshoot: false }, // slide in 60 px from the side
  punchy: { in: 8, out: 6, hold: 0.3, enter: "slam", transition: "cut", overshoot: true }, // slam 1.08 → 1, spring 14
  hype: { in: 5, out: 4, hold: 0.25, enter: "zoom", transition: "cut", overshoot: true }, // 1.2 → 1, shake 2–4 px for 6 frames
  parody: { in: 0, out: 0, hold: 0.5, enter: "cut", transition: "cut", overshoot: false }, // appears all at once
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const easeOut = Easing.out(Easing.cubic);
export const easeIn = Easing.in(Easing.cubic);
export const easeInOut = Easing.inOut(Easing.cubic);

// Brand loudness changes only the amplitude of offsets, not the timing: a quiet brand moves less.
const AMP: Record<Loudness, number> = { quiet: 0.7, calm: 1, lively: 1.15, loud: 1.3 };

const isTone = (t: unknown): t is SceneTone => typeof t === "string" && t in SCENE_TONES;

export const resolveBrandTone = (b: Brand): ResolvedTone => {
  const t = readBrandTone(b) ?? {};
  const loudness: Loudness = t.loudness && t.loudness in AMP ? t.loudness : "calm";
  return { loudness, overshoot: t.overshoot === true, shake: t.shake === true, sceneTone: isTone(t.scene_tone) ? t.scene_tone : "calm" };
};

/** The video's scene tone (props.sceneTone from export) over the brand tone: a scene without a tone takes it. */
export const withRollTone = (bt: ResolvedTone, sceneTone?: string | null): ResolvedTone => (isTone(sceneTone) ? { ...bt, sceneTone } : bt);

/** Scene tone: its own → the video's scene tone (props.sceneTone) → the brand's scene tone → calm. Unknown name → calm with a warning. */
export const pickTone = (spec: SceneSpec, bt: ResolvedTone): SceneTone => {
  if (spec.tone == null || spec.tone === "") return bt.sceneTone;
  if (isTone(spec.tone)) return spec.tone;
  console.warn(`kit: scene ${spec.id}: unknown tone “${spec.tone}”, using calm`);
  return "calm";
};

export type Motion = { opacity: number; transform: string };
export type MotionOpts = { dist?: number; dir?: 1 | -1 };

/** Element entry: start is the frame where the entry begins (from the scene start). */
export const enter = (frame: number, start: number, tone: SceneTone, bt: ResolvedTone, o: MotionOpts = {}): Motion => {
  const row = SCENE_TONES[tone];
  const k = frame - start;
  if (row.in === 0 || row.enter === "cut") return { opacity: k >= 0 ? 1 : 0, transform: "none" };
  const amp = AMP[bt.loudness];
  const p = interpolate(k, [0, row.in], [0, 1], { ...clamp, easing: easeOut });
  const bounce = bt.overshoot && row.overshoot;
  switch (row.enter) {
    case "rise":
      return { opacity: p, transform: `translateY(${(1 - p) * (o.dist ?? 30) * amp}px)` };
    case "fade":
      return { opacity: p, transform: "none" };
    case "scale":
      return { opacity: p, transform: `scale(${0.95 + 0.05 * p})` };
    case "slide":
      return { opacity: p, transform: `translateX(${(1 - p) * 60 * amp * (o.dir ?? -1)}px)` };
    case "slam": {
      const s = spring({ frame: k, fps: 30, config: { damping: bounce ? 14 : 200 }, durationInFrames: row.in });
      return { opacity: interpolate(k, [0, 3], [0, 1], clamp), transform: `scale(${1.08 - 0.08 * s})` };
    }
    case "zoom": {
      const s = bounce ? spring({ frame: k, fps: 30, config: { damping: 14 }, durationInFrames: row.in }) : p;
      // light 6-frame shake, only if the brand tone allows shake (bold/loud); no glow or blur
      const sh = bt.shake && k >= 0 && k < 6 ? (2 + 2 * amp / 1.3) * (1 - k / 6) : 0;
      const dx = sh * Math.sin(k * 2.9);
      const dy = sh * Math.cos(k * 3.7);
      return { opacity: interpolate(k, [0, 2], [0, 1], clamp), transform: `translate(${dx.toFixed(2)}px, ${dy.toFixed(2)}px) scale(${1.2 - 0.2 * s})` };
    }
    default:
      return { opacity: 1, transform: "none" };
  }
};

/** Element exit: end is the frame by which the element is gone. Exit is faster than entry (tone table). */
export const exit = (frame: number, end: number, tone: SceneTone, bt: ResolvedTone, o: MotionOpts = {}): Motion => {
  const row = SCENE_TONES[tone];
  if (row.out === 0) return { opacity: frame < end ? 1 : 0, transform: "none" };
  const amp = AMP[bt.loudness];
  const q = interpolate(frame, [end - row.out, end], [0, 1], { ...clamp, easing: easeIn });
  switch (row.enter) {
    case "rise":
      return { opacity: 1 - q, transform: `translateY(${-q * 24 * amp}px)` };
    case "scale":
      return { opacity: 1 - q, transform: `scale(${1 - 0.03 * q})` };
    case "slide":
      return { opacity: 1 - q, transform: `translateX(${q * 60 * amp * -(o.dir ?? -1)}px)` };
    case "slam":
      return { opacity: 1 - q, transform: `scale(${1 - 0.04 * q})` };
    case "zoom":
      return { opacity: 1 - q, transform: `scale(${1 + 0.08 * q})` };
    default:
      return { opacity: 1 - q, transform: "none" };
  }
};

/** How much larger the element is on entry (punchy slam 1.08, hype zoom 1.2). Scene content scales from the left
 *  edge, so the text width is divided by this number, and on entry the line does not cross x 960. */
export const enterGrow = (tone: SceneTone): number => (SCENE_TONES[tone].enter === "slam" ? 1.08 : SCENE_TONES[tone].enter === "zoom" ? 1.2 : 1);

/** Entry and exit together (the same tone motion). */
export const both = (frame: number, start: number, end: number, tone: SceneTone, bt: ResolvedTone, o: MotionOpts = {}): Motion => {
  const a = enter(frame, start, tone, bt, o);
  const b = exit(frame, end, tone, bt, o);
  const tr = [a.transform, b.transform].filter((t) => t !== "none").join(" ");
  return { opacity: Math.min(a.opacity, b.opacity), transform: tr || "none" };
};

/** Appearance progress 0..1 (for masks, counters, brackets) with the same ease-out as the tone. */
export const progress = (frame: number, start: number, dur: number): number =>
  dur <= 0 ? (frame >= start ? 1 : 0) : interpolate(frame, [start, start + dur], [0, 1], { ...clamp, easing: easeOut });

// Layout change (speaker shrinks/returns, field, shutter) follows the scene transition. fade/slide follow the tone, but
// within effects.md §6: entry 8–14 frames, return 6–10 (faster than entry).
export const layoutFrames = (t: SceneTransition, tone: SceneTone, dir: "in" | "out"): number => {
  if (t === "cut") return 0;
  if (t === "flash") return 3;
  if (t === "whip") return 5;
  const row = SCENE_TONES[tone];
  return dir === "in" ? Math.min(14, Math.max(8, row.in)) : Math.min(10, Math.max(6, row.out));
};

const speaking = (words: Word[], a: number, b: number) => words.some((w) => w.start < b && w.end > a);

/** Scene timing. Rule effects.md §8 “cut on a pause”: if no word is spoken within the transition window, a smooth change
 *  (fade/slide/whip) becomes a cut. In the “scenes only” format (no words) transitions are left as they are. */
export const sceneTimeline = (spec: SceneSpec, tone: SceneTone, mode: SceneMode, fps: number, words: Word[]): Timeline => {
  const row = SCENE_TONES[tone];
  const n = Math.max(1, Math.round(spec.dur * fps));
  let tin: SceneTransition = spec.transition_in ?? row.transition;
  let tout: SceneTransition = spec.transition_out ?? row.transition;
  const smooth = (t: SceneTransition) => t === "fade" || t === "slide" || t === "whip";
  if (words.length) {
    const a = spec.start;
    const b = spec.start + spec.dur;
    if (smooth(tin) && !speaking(words, a, a + layoutFrames(tin, tone, "in") / fps)) tin = "cut";
    if (smooth(tout) && !speaking(words, b - layoutFrames(tout, tone, "out") / fps, b)) tout = "cut";
  }
  const L = layoutFrames(tin, tone, "in");
  const Lout = layoutFrames(tout, tone, "out");
  // overlay does not change the layout: content enters at once, with its own motion; other modes enter after 0.6 of the
  // layout change (Easing.out at 0.6 = 94 % of the way): text does not land on a speaker still moving away, no “double exposure”
  const layout = mode !== "overlay";
  const lead = layout ? Math.round(0.6 * L) : 0;
  const tail = layout ? Math.round(0.6 * Lout) : 0;
  const inF = row.in;
  const outF = row.out;
  return { n, tin, tout, L, Lout, lead, tail, inF, outF, settleFrom: lead + inF, settleTo: n - tail - outF };
};

/** Appearance frame of item k of count: its own t (video seconds) → otherwise evenly, with a step ≥ 0.6 s (reading threshold). */
export const itemFrames = (ts: (number | null | undefined)[], start: number, fps: number, tl: Timeline): number[] => {
  const count = ts.length;
  const free = tl.settleTo - tl.lead - tl.inF - Math.round(0.8 * fps); // the last item gets at least 0.8 s at rest
  const step = Math.max(Math.round(0.6 * fps), Math.floor(free / Math.max(1, count)));
  return ts.map((t, k) => {
    const own = typeof t === "number" ? Math.round((t - start) * fps) : null;
    return Math.max(tl.lead, own ?? tl.lead + k * step);
  });
};
