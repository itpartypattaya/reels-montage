// Helpers for a mascot drawn in code (references/mascot.md, references/mascot-sample.md): blending two poses, arms of
// two segments, the idle breath. Plain math, no React: a brand's module imports what it needs.
import type { MascotFrame } from "./types";

export const rad = (d: number) => (d * Math.PI) / 180;
export const mix = (a: number, b: number, k: number) => a + (b - a) * k;
export const clamp01 = (k: number) => Math.max(0, Math.min(1, k));

/** Angle a → b by the shortest arc (350° → 10° turns 20°, not 340°), degrees. */
export const angMix = (a: number, b: number, k: number) => {
  const d = ((((b - a) % 360) + 540) % 360) - 180;
  return a + d * k;
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
export const armPoints = (s: [number, number], arm: Arm, l1: number, l2: number) => {
  const e: [number, number] = [s[0] + Math.cos(rad(arm.a1)) * l1, s[1] + Math.sin(rad(arm.a1)) * l1];
  const h: [number, number] = [e[0] + Math.cos(rad(arm.a2)) * l2, e[1] + Math.sin(rad(arm.a2)) * l2];
  return { elbow: e, hand: h };
};
/** The arm as an SVG path (stroke it with round caps and joins). */
export const armPath = (s: [number, number], arm: Arm, l1: number, l2: number) => {
  const { elbow, hand } = armPoints(s, arm, l1, l2);
  return `M${s[0]} ${s[1]} L${elbow[0]} ${elbow[1]} L${hand[0]} ${hand[1]}`;
};
/** The other side's arm: the angles mirrored around the vertical. */
export const mirrorArm = (a: Arm): Arm => ({ a1: 180 - a.a1, a2: 180 - a.a2 });

/** The idle breath, px in the box: a slow rise and fall (background motion, SKILL.md section 4). */
export const breath = (t: number, amp = 3) => Math.sin(t * 2.1) * amp;
