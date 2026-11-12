// The brand mascot on the video (references/mascot.md): plays props.mascot, the per-frame plan visual_plan.py stage
// resolved (poses on words, the mouth from mouth.json, blinks, eased pose changes). The layer only places the module's
// drawing: its box anchor (the point between the eyes) at x, y, scaled, mirrored when facing is -1, a soft entrance and
// exit, an idle breath. No outline and no shadow (the kit's rule: no shadows); a brand that wants a sticker outline draws
// it in its own module. data-rk="mascot": textcheck.py measures the drawn figure and flags text over it.
import React from "react";
import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { MascotFrame, MascotModule } from "./types";

/** One entry of the plan: it holds from frame f until the next entry (stage writes an entry only where a value changes). */
export type MascotPlanFrame = { f: number; pose: string; prev: string; k: number; open: number; blink: boolean; facing?: 1 | -1 };
export type MascotProps = {
  kind: "drawn" | "atlas";
  module: string; // the brand slug: the key in src/gen/mascots.ts (drawn)
  rig?: string; // atlas: rig.json inside public/ (brand.py stage copies it)
  atlas?: string; // atlas: the atlas image inside public/
  x: number; // the anchor on screen, px
  y: number;
  scale: number;
  facing: 1 | -1;
  from: number; // seconds on screen
  to: number;
  frames: MascotPlanFrame[];
};

const TALK_MIN = 0.08;
const IN_FRAMES = 10;
const OUT_FRAMES = 8;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** The module that draws this mascot. kind "atlas" (a PNG atlas cut by mascot.py atlas) plugs in HERE: until its
 *  renderer is part of the kit, an atlas mascot draws nothing. */
export const mascotModule = (p: MascotProps, modules: Record<string, MascotModule>): MascotModule | null =>
  p.kind === "drawn" ? modules[p.module] ?? null : null;

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

export const MascotLayer: React.FC<{ mascot?: MascotProps | null; modules: Record<string, MascotModule> }> = ({ mascot, modules }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!mascot || !mascot.frames?.length) return null;
  const mod = mascotModule(mascot, modules);
  const f0 = Math.round(mascot.from * fps);
  const f1 = Math.round(mascot.to * fps);
  if (!mod || frame < f0 || frame >= f1) return null;
  const e = planAt(mascot.frames, frame);
  if (!e) return null;
  const t = frame / fps;
  const facing = e.facing ?? mascot.facing ?? 1;
  const f: MascotFrame = {
    t, pose: e.pose, prevPose: e.prev, k: e.k, open: e.open, talking: e.open > TALK_MIN, blink: e.blink, facing,
  };
  const a = Math.min(
    interpolate(frame, [f0, f0 + IN_FRAMES], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) }),
    interpolate(frame, [f1 - OUT_FRAMES, f1], [1, 0], clamp),
  );
  const lift = (1 - a) * 24 + Math.sin(t * 2.1) * 2 * mascot.scale; // the entrance rise and the idle breath
  const { width, height, anchor } = mod.box;
  return (
    <div data-rk="mascot" style={{ position: "absolute", left: 0, top: 0, width, height, opacity: a, transformOrigin: "0 0",
      transform: `translate(${mascot.x}px, ${mascot.y + lift}px) scale(${mascot.scale * facing}, ${mascot.scale}) translate(${-anchor[0]}px, ${-anchor[1]}px)`,
      pointerEvents: "none" }}>
      {mod.render(f)}
    </div>
  );
};
