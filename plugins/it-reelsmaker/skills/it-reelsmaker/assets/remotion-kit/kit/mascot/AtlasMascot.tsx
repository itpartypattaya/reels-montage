// The mascot from a ready character picture: the PNG atlas that scripts/mascot_atlas.py cuts from the brand's own
// illustration (references/mascot-atlas.md). One <Img> of the whole atlas, cropped to the current pose's frame.
// Mouth: the pose's talk frame when it has one, else an ellipse in the drawing's line color (a tongue when it opens
// wide). Blink: the pose's blink frame, or an eyelid in the skin color with a lash arc (over the talk frame too).
// A pose change is a frame switch: a picture has no in-between drawings to interpolate.
// The kit reads no files itself: the stage puts rig.json's content into the props (props.mascot.rig) and copies
// atlas.png into public/ (props.mascot.atlas); the layer calls atlasMascot(rig, atlas) once.
import type React from "react";
import { Img, staticFile } from "remotion";

// The mascot contract: kit/mascot/types.ts (the module made here is a MascotModule the layer places).
import type { MascotModule, MascotRender } from "./types";

// rig.json as mascot_atlas.py writes it: rectangles [x, y, w, h] and points in atlas px; offset places a pose's
// frame in the shared box so that its head lands on the shared anchor; talk/blink frames have the pose's size.
type Rect = [number, number, number, number];
type Pt = [number, number];
export type AtlasPose = {
  cell: Rect;
  offset: Pt;
  eyes: Pt[];
  mouth: Pt;
  mouthW: number;
  skin: string;
  ink: string;
  talk?: Rect;
  blink?: Rect;
};
export type AtlasRig = {
  atlas: string;
  width: number;
  height: number;
  symmetric: boolean;
  box: [number, number];
  anchor: Pt;
  head?: number;
  poses: Record<string, AtlasPose>;
};
// symmetric: false = the picture must never be shown mirrored (one-sided details: a logo, a parting, a watch).
export type AtlasMascotModule = MascotModule & { symmetric: boolean };

const OPEN_FRAME = 0.3; // a drawn talk frame is open or shut: it shows from this opening
const TONGUE = 0.55; // the overlay mouth shows a tongue from this opening
const SWITCH = 0.5; // the frame switches halfway through a pose change
const POP = 0.03; // the most a pose shrinks while k overshoots (0.97 -> 1 as it settles)
const TONGUE_COLOR = "#d9707f";

/** The overlay mouth: a lens whose lower lip drops with the opening (the upper one barely moves, as in speech), in
 *  the drawing's line color, with a tongue in its lower half once it opens wide. */
const OpenMouth: React.FC<{ x: number; y: number; width: number; open: number; ink: string }> = ({ x, y, width, open, ink }) => {
  const half = (width / 2) * (1 - 0.1 * open);
  const drop = width * (0.12 + 0.4 * open);
  const lift = drop * 0.25;
  const lens = `M ${-half} 0 Q 0 ${-lift} ${half} 0 Q 0 ${drop} ${-half} 0 Z`;
  const tw = half * 0.5;
  const tongue = `M ${-tw} ${drop * 0.35} Q 0 ${drop * 0.18} ${tw} ${drop * 0.35} Q 0 ${drop * 0.85} ${-tw} ${drop * 0.35} Z`;
  return (
    <g transform={`translate(${x} ${y})`}>
      <path d={lens} fill={ink} />
      {open > TONGUE ? <path d={tongue} fill={TONGUE_COLOR} /> : null}
    </g>
  );
};

/** A shut eye over a drawn open one: a patch of the face color hiding it, and the lid's line as a downward arc. */
const ShutEye: React.FC<{ x: number; y: number; gap: number; skin: string; ink: string }> = ({ x, y, gap, skin, ink }) => {
  const w = gap * 0.4;
  const h = gap * 0.44;
  const r = w * 0.85;
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={-w} y={-h} width={2 * w} height={2 * h} rx={Math.min(w, h)} fill={skin} />
      <path d={`M ${-r} 0 A ${r} ${r * 0.55} 0 0 0 ${r} 0`} fill="none" stroke={ink} strokeWidth={Math.max(2, gap * 0.06)}
        strokeLinecap="round" />
    </g>
  );
};

// A path inside public/ (the stage copies the atlas there), or a full address as it is.
const fileSrc = (p: string) => (/^[a-z][a-z0-9+.-]*:/i.test(p) ? p : staticFile(p.replace(/^\/+/, "")));

export const atlasMascot = (rig: AtlasRig, atlasSrc?: string): AtlasMascotModule => {
  const names = Object.keys(rig.poses);
  const fallback = rig.poses.neutral ?? rig.poses[names[0]];
  const file = fileSrc(atlasSrc ?? rig.atlas);
  const [bw, bh] = rig.box;
  const [ax, ay] = rig.anchor;

  const render: MascotRender = (f) => {
    const name = f.k < SWITCH ? f.prevPose : f.pose;
    const p = rig.poses[name] ?? rig.poses[f.pose] ?? fallback;
    if (!p) return null;
    const talkFrame = f.talking && f.open >= OPEN_FRAME && p.talk ? p.talk : null;
    const blinkFrame = f.blink && !talkFrame && p.blink ? p.blink : null;
    const [cx, cy, cw, ch] = talkFrame ?? blinkFrame ?? p.cell;
    const [ox, oy] = p.offset;
    // a pose's points are atlas px of its cell; in the box they move with the frame's offset
    const at = (q: Pt): Pt => [ox + q[0] - p.cell[0], oy + q[1] - p.cell[1]];
    const mouthOn = f.talking && !p.talk && f.open > 0.08;
    const lids = f.blink && !blinkFrame && p.eyes.length > 0;
    const over = f.k > 1 ? f.k - 1 : f.k < 0 ? -f.k : 0;
    const scale = 1 - Math.min(POP, over * 0.3);
    // The layer mirrors facing -1; a one-sided picture is turned back so it is never shown mirrored.
    const unmirror = f.facing === -1 && !rig.symmetric;
    const [mx, my] = at(p.mouth);
    const eyes = p.eyes.map(at);
    const gap = eyes.length > 1 ? Math.hypot(eyes[1][0] - eyes[0][0], eyes[1][1] - eyes[0][1]) : p.mouthW * 1.6;
    return (
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: bw,
          height: bh,
          transform: `${unmirror ? "scaleX(-1) " : ""}scale(${scale})`,
          transformOrigin: `${ax}px ${ay}px`,
        }}
      >
        {/* the frame: the atlas at its own size, shifted so the frame's corner sits at the box position */}
        <Img
          src={file}
          style={{ position: "absolute", left: ox, top: oy, width: cw, height: ch, maxWidth: "none",
            objectFit: "none", objectPosition: `${-cx}px ${-cy}px` }}
        />
        {mouthOn || lids ? (
          <svg width={bw} height={bh} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
            {mouthOn ? <OpenMouth x={mx} y={my} width={p.mouthW} open={f.open} ink={p.ink} /> : null}
            {lids ? eyes.map(([ex, ey], i) => <ShutEye key={i} x={ex} y={ey} gap={gap} skin={p.skin} ink={p.ink} />) : null}
          </svg>
        ) : null}
      </div>
    );
  };

  return { box: { width: bw, height: bh, anchor: [ax, ay] }, poses: names, render, symmetric: rig.symmetric };
};
