// Helpers for a mascot drawn in code (references/mascot.md, references/mascot-sample.md): blending two poses, arms of
// two segments, the idle breath. Plain math, no React: a brand's module imports what it needs.
import type { MascotFrame } from "./types";

const DEG = Math.PI / 180;
/** Degrees → radians. */
export const rad = (d: number) => d * DEG;
export const mix = (a: number, b: number, k: number) => a + (b - a) * k;
export const clamp01 = (k: number) => Math.max(0, Math.min(1, k));

/** Angle a → b by the shortest arc (350° → 10° turns 20°, not 340°), degrees: the signed turn is read from the
 *  direction of b seen from a (atan2 of the difference's sine and cosine), so any number of full turns drops out.
 *  Exactly opposite directions turn by −180° (counterclockwise on screen), whichever way the angles are written. */
export const angMix = (a: number, b: number, k: number) => {
  let turn = Math.atan2(Math.sin((b - a) * DEG), Math.cos((b - a) * DEG)) / DEG;
  if (turn > 180 - 1e-9) turn -= 360;
  return a + turn * k;
};

/** A pose as named numbers; the keys listed in `angles` (degrees) blend by the shortest arc, the rest linearly. k may
 *  overshoot 1 only when the plan allows it (MascotFrame.k): angles and offsets follow it, sizes and colors should not. */
export type PoseNums = Record<string, number>;
export const poseMix = <T extends PoseNums>(a: T, b: T, k: number, angles: readonly string[] = []): T => {
  const out: PoseNums = {};
  for (const key of Object.keys(b)) {
    const x = a[key] ?? b[key];
    out[key] = angles.includes(key) ? angMix(x, b[key], k) : mix(x, b[key], k);
  }
  return out as T;
};

/** The current pose of a frame, blended: poses[f.prevPose] → poses[f.pose] by f.k (unknown names: neutral). */
export const poseAt = <T extends PoseNums>(poses: Record<string, T>, f: MascotFrame, angles: readonly string[] = []): T => {
  const to = poses[f.pose] ?? poses.neutral;
  const from = poses[f.prevPose] ?? poses.neutral;
  return poseMix(from, to, f.k, angles);
};

/** An arm of two segments from the shoulder s: a1 — the upper arm's angle, a2 — the forearm's (degrees, 0 = right,
 *  90 = down, SVG's y axis). → the elbow and the hand. */
export type Arm = { a1: number; a2: number };
type Pt = [number, number];
/** The point `len` away from p in the direction `deg`. */
const step = (p: Pt, deg: number, len: number): Pt => [p[0] + len * Math.cos(deg * DEG), p[1] + len * Math.sin(deg * DEG)];
export const armPoints = (s: Pt, arm: Arm, l1: number, l2: number) => {
  const elbow = step(s, arm.a1, l1);
  return { elbow, hand: step(elbow, arm.a2, l2) };
};
/** The arm as an SVG path (stroke it with round caps and joins). */
export const armPath = (s: Pt, arm: Arm, l1: number, l2: number) => {
  const { elbow, hand } = armPoints(s, arm, l1, l2);
  return "M " + [s, elbow, hand].map((q) => q.join(" ")).join(" L ");
};
/** The other side's arm: each direction reflected in the vertical axis (its x flips, its y stays), kept in 0..360. */
const reflect = (deg: number) => (((180 - deg) % 360) + 360) % 360;
export const mirrorArm = (a: Arm): Arm => ({ a1: reflect(a.a1), a2: reflect(a.a2) });

/** The pose's own mouth, the expression the speech is drawn over: its width and how far its middle sits below the
 *  corners (px; > 0 a smile, < 0 a frown, 0 a straight line). */
export type MouthBase = { width: number; curve: number };
export type MouthShape = { d: string; filled: boolean; width: number; height: number };
const SHUT = 0.05; // an opening under this is drawn as the expression's line
/** The mouth for a frame, around its centre (0, 0) on the line through its corners: shut, the expression's line
 *  (stroke it); open, a shape whose corners stay at the expression's height, its upper lip curved exactly like the
 *  expression, its lower lip dropped by `open` (fill it). `wide` 1 (an "ee") makes it wider and flatter, 0 (an "oo")
 *  narrower and taller; at 0.5 the corners stay where the expression put them. Corners, then the upper lip to the
 *  right corner, then the lower lip back. */
export const mouthPath = (base: MouthBase, open: number, wide: number): MouthShape => {
  const o = clamp01(open);
  const w = clamp01(wide);
  // the width moves with `wide` only as far as the mouth is open: shut or neutral, the corners are the expression's
  const half = (base.width / 2) * (o <= SHUT ? 1 : 1 + 0.4 * (w - 0.5) * o);
  const cu = 2 * base.curve; // the upper lip keeps the expression's curve (a quadratic curve reaches half its control)
  if (o <= SHUT) return { d: `M ${-half} 0 Q 0 ${cu} ${half} 0`, filled: false, width: 2 * half, height: Math.abs(base.curve) };
  const drop = Math.max(2, base.width * o * mix(0.75, 0.42, w));
  const cl = Math.max(cu + 4, 2 * (base.curve + drop));
  return {
    d: `M ${-half} 0 Q 0 ${cu} ${half} 0 Q 0 ${cl} ${-half} 0 Z`,
    filled: true,
    width: 2 * half,
    height: (cl - Math.min(0, cu)) / 2,
  };
};

/** The idle breath, px in the box: a slow rise and fall, one breath every BREATH_S seconds (background motion,
 *  SKILL.md section 4). */
export const BREATH_S = 3.2;
export const breath = (t: number, amp = 3) => amp * Math.sin((2 * Math.PI * t) / BREATH_S);
