// Cover (type cover; not part of the video): the hook in large type on marker plates, centered in the zone that stays visible
// in the profile grid under any crop: a 1:1 square in the frame center (y 420–1500), x 60–960 in width (feed buttons on the right).
// The accent word (text.accent) goes on the style's marker and the rest on light plates, as on the hook over the video (T6:
// without the accent both lines sat on the marker). onField (no video under it, a "scenes only" promo): drawn as a full
// scene is, on the style's field: the text in its color, only the accent on a plate.
// A still frame at rest, no motion. The ReelCover composition (ReelKit.tsx) lays it over a video frame (frameAt);
// poster.py pick/bake burns it into frame 0 and saves cover.jpg.
import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { Brand, Look, logoOnDark, useLookFonts } from "../brand";
import { TextBlock, contrast, surfaces } from "./parts";
import type { Stage } from "./types";

export type CoverText = { lines: string[]; accent?: string | null; label?: string | null };
// 1:1 zone in the center of the 1080×1920 frame, with 60 px margins and without the button column on the right
export const COVER_ZONE: Stage = { x: 60, y: 420, w: 900, h: 1080 };
// over a frame with a person: the lower part of the same zone (chest, y 1020–1500); a medium-shot face sits higher (typically y 700–1000).
// The exact free zone is the box from the plan (faces.json); ReelCover takes it first.
export const COVER_ZONE_LOW: Stage = { x: 60, y: 1020, w: 900, h: 480 };

export const Cover: React.FC<{ brand: Brand; look: Look; text: CoverText; logo?: boolean; zone?: Stage; size?: number; onField?: boolean }> = ({
  brand, look, text, logo, zone = COVER_ZONE, size = 124, onField = false,
}) => {
  const fonts = useLookFonts(look);
  const S = surfaces(brand, look);
  const lines = text.lines.filter(Boolean);
  // on a light field (onField, the style's field lighter than mid-gray) the dark logo variant, else the light one
  const lightField = onField && !!look.field && contrast(look.field, "#000000") > contrast(look.field, "#FFFFFF");
  const src = logo ? (lightField ? brand.logos.mark_on_light ?? brand.logos.on_light ?? logoOnDark(brand) : logoOnDark(brand)) : null;
  const logoH = 96;
  const lh = onField ? 1.1 : 1.21; // plates touching: 1.08 + padding 0.13; text on the field: 1.1
  const byH = Math.floor((zone.h - (src ? logoH + 44 : 0) - (text.label ? 60 : 0)) / Math.max(1, lines.length * lh));
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: zone.x, top: zone.y, width: zone.w, height: zone.h, display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center" }}>
        {src ? <Img src={staticFile(src)} style={{ height: logoH, width: "auto", maxWidth: zone.w * 0.6, objectFit: "contain", marginBottom: 44 }} /> : null}
        <TextBlock lines={lines} accent={text.accent} label={text.label} size={Math.min(size, byH)} weight={800} font={fonts.heading}
          labelFont={fonts.body} surf={S.field} chip={onField ? null : S.card} plates={!onField} align="center" maxWidth={zone.w} />
      </div>
    </AbsoluteFill>
  );
};
