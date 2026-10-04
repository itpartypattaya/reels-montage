// Light flash instead of a transition (references/techniques.md, “Light flash instead of a transition”): a warm-white
// radial spot in `screen` blend that sweeps across the frame, 8 frames centered on the cut frame, opacity on a sine
// 0 → 0.55 → 0. It lifts the brightness of the picture under it rather than covering it with white (the kit's earlier
// `flash` was a 3-frame solid white fill at 0.85). The cut itself is hard, hidden under the peak. How many per video is
// the brand tone's ceiling (references/brands.md), checked by visual_plan.py validate.
import React from "react";
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Brand, alpha } from "./brand";

export const FLASH_FRAMES = 8; // techniques.md: 6–10 frames
export const FLASH_PEAK = 0.55;
const WARM = "#FFECD2"; // warm white (techniques.md: rgba(255, 236, 210, …)) when the brand has no colors.extra.warm

/** Opacity of the flash at frame k of its FLASH_FRAMES: a sine, the peak on the middle frame (the cut). */
export const flashOpacity = (k: number, n = FLASH_FRAMES) => (k < 0 || k > n ? 0 : FLASH_PEAK * Math.sin((Math.PI * k) / n));

/** The flash itself, from its own frame 0 (mount it centered on the cut: FlashAt). */
export const LightFlash: React.FC<{ color?: string; frames?: number }> = ({ color, frames }) => {
  const frame = useCurrentFrame();
  const n = frames ?? FLASH_FRAMES;
  const a = flashOpacity(frame, n);
  if (a <= 0) return null;
  const c = color ?? WARM;
  const x = interpolate(frame, [0, n], [-20, 120], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }); // the spot sweeps left → right
  return (
    <AbsoluteFill style={{ mixBlendMode: "screen", pointerEvents: "none",
      background: `radial-gradient(ellipse 75% 60% at ${x}% 40%, ${alpha(c, a)}, ${alpha(c, 0)} 70%)` }} />
  );
};

/** The warm white of the brand profile (colors.extra.warm or .cream), otherwise the kit's warm white. */
export const flashColor = (brand?: Brand | null) => brand?.colors.extra?.warm ?? brand?.colors.extra?.cream ?? WARM;

/** A light flash centered on second t of the video: from t − 4 frames to t + 4. */
export const FlashAt: React.FC<{ t: number; brand?: Brand | null }> = ({ t, brand }) => {
  const { fps } = useVideoConfig();
  const from = Math.round(t * fps) - FLASH_FRAMES / 2;
  return (
    <Sequence from={from} durationInFrames={FLASH_FRAMES + 1} layout="none">
      <LightFlash color={flashColor(brand)} />
    </Sequence>
  );
};
