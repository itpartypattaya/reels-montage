// The brand mascot's contract (references/mascot.md): a module drawn in code (src/gen/mascots.ts registers it) or a
// PNG atlas; MascotLayer places it and hands it one MascotFrame per video frame, resolved by visual_plan.py stage.
import type React from "react";

// A mascot is drawn in its own coordinate box and placed by MascotLayer.
export type MascotBox = { width: number; height: number; anchor: [number, number] }; // anchor = the point between the eyes, in box px
export type MascotFrame = {
  t: number;            // seconds on the render timeline
  pose: string;         // current pose name (dictionary below)
  prevPose: string;     // the pose before the current change
  k: number;            // 0..1 progress of the change prevPose → pose (already eased; may exceed 0..1 only when overshoot is allowed)
  open: number;         // mouth opening 0..1 (0 outside speaking spans)
  talking: boolean;     // inside a speaking span and open > 0.08
  blink: boolean;       // eyes shut on this frame (lid ≥ 0.5): for a module that draws only open or shut eyes
  lid: number;          // 0..1 how shut the eyes are: a blink goes 0.5, 1, 1, 0.5 (and hides every pose change)
  since?: number;       // frames since the current pose change began, set on its first frames only (0, 1, 2)
  facing: 1 | -1;       // -1 = mirrored horizontally (MascotLayer mirrors; the module may ignore it)
};
export type MascotRender = (f: MascotFrame) => React.ReactNode; // returns SVG/HTML inside the box
export type MascotModule = { box: MascotBox; poses: string[]; render: MascotRender };

// Pose dictionary: neutral, talk, point_left, point_right, point_up, palm, think, surprise, celebrate, shrug, wink.
export const POSES = ["neutral", "talk", "point_left", "point_right", "point_up", "palm", "think", "surprise", "celebrate",
  "shrug", "wink"] as const;
