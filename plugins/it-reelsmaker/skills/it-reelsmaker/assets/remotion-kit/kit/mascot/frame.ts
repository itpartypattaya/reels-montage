// The per-frame plan of the mascot as plain math, with no Remotion import (tests/scripts/test_mascot_acting.py runs
// it with node): the entry that holds on a frame, the MascotFrame a module gets from it, and the pictures the atlas
// shows while a pose changes. MascotLayer.tsx and AtlasMascot.tsx use it.
import type { MascotFrame } from "./types";

/** One entry of the plan (visual_plan.py stage): it holds from frame f until the next entry, written only where a value
 *  changes. lid and since came later: a plan without them still plays (the lid from blink, the switch from k). */
export type MascotPlanFrame = {
  f: number;
  pose: string;
  prev: string;
  k: number;
  open: number;
  blink: boolean;
  lid?: number; // 0..1 how shut the eyes are
  since?: number; // frames since the pose change began, on its first frames only (0, 1, 2)
  facing?: 1 | -1;
};

export const TALK_MIN = 0.08; // an opening under this reads as a closed mouth
export const SWITCH = 0.5; // a plan without `since`: the atlas switches its picture halfway through a change

/** The entry that holds on frame f (the last one with entry.f ≤ f), by binary search. */
export const planAt = (frames: MascotPlanFrame[], f: number): MascotPlanFrame | null => {
  let lo = 0;
  let hi = frames.length - 1;
  let got: MascotPlanFrame | null = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].f <= f) {
      got = frames[mid];
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return got;
};

/** The frame a module draws, from the entry that holds, the second t on the render timeline and the layer's facing. */
export const frameOf = (e: MascotPlanFrame, t: number, facing: 1 | -1): MascotFrame => ({
  t,
  pose: e.pose,
  prevPose: e.prev,
  k: e.k,
  open: e.open,
  talking: e.open > TALK_MIN,
  blink: e.blink,
  lid: typeof e.lid === "number" ? e.lid : e.blink ? 1 : 0,
  ...(typeof e.since === "number" ? { since: e.since } : {}),
  facing: e.facing ?? facing,
});

/** The pictures of a picture mascot on this frame, bottom first: a pose change is a swap under shut eyes, the old
 *  picture on the change's first frame, a two-frame cross-fade (the new one half over the old, then the old one half
 *  under the new: the figure never goes see-through where both cover it), then the new one alone. */
export type SwitchLayer = { pose: string; opacity: number };
export const switchLayers = (f: MascotFrame): SwitchLayer[] => {
  if (f.pose === f.prevPose) return [{ pose: f.pose, opacity: 1 }];
  if (f.since === undefined) return [{ pose: f.k < SWITCH ? f.prevPose : f.pose, opacity: 1 }];
  if (f.since <= 0) return [{ pose: f.prevPose, opacity: 1 }];
  if (f.since === 1) return [{ pose: f.prevPose, opacity: 1 }, { pose: f.pose, opacity: 0.5 }];
  if (f.since === 2) return [{ pose: f.prevPose, opacity: 0.5 }, { pose: f.pose, opacity: 1 }];
  return [{ pose: f.pose, opacity: 1 }];
};
