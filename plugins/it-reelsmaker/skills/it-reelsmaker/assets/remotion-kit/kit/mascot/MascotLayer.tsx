// The brand mascot on the video (references/mascot.md): plays props.mascot, the per-frame plan visual_plan.py stage
// resolved (poses on words, the mouth from mouth.json, blinks, eased pose changes hidden by a blink). The layer only places the module's
// drawing: its box anchor (the point between the eyes) at x, y, scaled, mirrored when facing is -1, a soft entrance and
// exit, an idle breath. No outline and no shadow (the kit's rule: no shadows); a brand that wants a sticker outline draws
// it in its own module. data-rk="mascot": textcheck.py measures the drawn figure and flags text over it.
import React from "react";
import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { MascotModule } from "./types";
import { breath } from "./rig";
import { frameOf, planAt, type MascotPlanFrame } from "./frame";
import { atlasMascot, type AtlasRig } from "./AtlasMascot";

export type MascotProps = {
  kind: "drawn" | "atlas";
  module: string; // the brand slug: the key in src/gen/mascots.ts (drawn)
  rig?: AtlasRig; // atlas: rig.json's content (visual_plan.py stage reads it; the kit reads no files while rendering)
  atlas?: string; // atlas: the atlas image inside public/
  x: number; // the anchor on screen, px
  y: number;
  scale: number;
  facing: 1 | -1;
  from: number; // seconds on screen
  to: number;
  frames: MascotPlanFrame[];
};

const IN_FRAMES = 10;
const OUT_FRAMES = 8;
const RISE = 24; // px: the mascot rises this much as it fades in
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// one atlas module per rig object and atlas image: the props do not change during a render, the module is made once
const atlasModules = new WeakMap<AtlasRig, Map<string, MascotModule>>();

/** The module that draws this mascot: a drawn module from src/gen/mascots.ts, or the PNG atlas cut by mascot_atlas.py
 *  (AtlasMascot.tsx) from the rig's content and the atlas image in public/. */
export const mascotModule = (p: MascotProps, modules: Record<string, MascotModule>): MascotModule | null => {
  if (p.kind === "drawn") return modules[p.module] ?? null;
  if (p.kind !== "atlas" || !p.rig || typeof p.rig !== "object" || !p.rig.poses) return null;
  let byImage = atlasModules.get(p.rig);
  if (!byImage) {
    byImage = new Map();
    atlasModules.set(p.rig, byImage);
  }
  const key = p.atlas ?? "";
  let m = byImage.get(key);
  if (!m) {
    m = atlasMascot(p.rig, p.atlas);
    byImage.set(key, m);
  }
  return m;
};

// the plan's entries and their frame: kit/mascot/frame.ts (plain math, tested with node)
export { planAt, type MascotPlanFrame };

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
  const f = frameOf(e, t, mascot.facing ?? 1);
  const facing = f.facing;
  const a = Math.min(
    interpolate(frame, [f0, f0 + IN_FRAMES], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) }),
    interpolate(frame, [f1 - OUT_FRAMES, f1], [1, 0], clamp),
  );
  const lift = (1 - a) * RISE + breath(t, 2 * mascot.scale); // the entrance rise and the idle breath
  const { width, height, anchor } = mod.box;
  return (
    <div data-rk="mascot" style={{ position: "absolute", left: 0, top: 0, width, height, opacity: a, transformOrigin: "0 0",
      transform: `translate(${mascot.x}px, ${mascot.y + lift}px) scale(${mascot.scale * facing}, ${mascot.scale}) translate(${-anchor[0]}px, ${-anchor[1]}px)`,
      pointerEvents: "none" }}>
      {mod.render(f)}
    </div>
  );
};
