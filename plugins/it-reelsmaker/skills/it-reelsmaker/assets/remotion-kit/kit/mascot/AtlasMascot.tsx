// The mascot from a ready character picture: the PNG atlas that scripts/mascot_atlas.py cuts from the brand's own
// illustration (references/mascot-atlas.md). One <Img> of the whole atlas, cropped to the current pose's frame.
// Mouth: the pose's talk frame when it has one, else an ellipse in the drawing's line color (a tongue when it opens
// wide). Blink: the pose's blink frame, or an eyelid in the skin color with a lash arc (over the talk frame too).
// A pose change is a frame switch: a picture has no in-between drawings to interpolate.
// The kit reads no files itself: the stage puts rig.json's content into the props (props.mascot.rig) and copies
// atlas.png into public/ (props.mascot.atlas); the layer calls atlasMascot(rig, atlas) once.
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
    const mw = p.mouthW;
    const [mx, my] = at(p.mouth);
    const mrx = (mw / 2) * (1 - 0.15 * f.open);
    const mry = mw * (0.07 + 0.25 * f.open);
    const eyes = p.eyes.map(at);
    const gap = eyes.length > 1 ? Math.hypot(eyes[1][0] - eyes[0][0], eyes[1][1] - eyes[0][1]) : mw * 1.6;
    const lrx = gap * 0.42;
    const lry = gap * 0.46;
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
        <div style={{ position: "absolute", left: ox, top: oy, width: cw, height: ch, overflow: "hidden" }}>
          <Img
            src={file}
            style={{ position: "absolute", left: -cx, top: -cy, width: rig.width, height: rig.height, maxWidth: "none" }}
          />
        </div>
        {mouthOn || lids ? (
          <svg width={bw} height={bh} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
            {mouthOn ? (
              <g transform={`translate(${mx} ${my})`}>
                <ellipse rx={mrx} ry={mry} fill={p.ink} />
                {f.open > TONGUE ? <ellipse cy={mry * 0.45} rx={mrx * 0.55} ry={mry * 0.4} fill={TONGUE_COLOR} /> : null}
              </g>
            ) : null}
            {lids
              ? eyes.map(([ex, ey], i) => (
                  <g key={i} transform={`translate(${ex} ${ey})`}>
                    <ellipse rx={lrx} ry={lry} fill={p.skin} />
                    <path
                      d={`M ${-lrx * 0.9} 0 Q 0 ${lry * 0.35} ${lrx * 0.9} 0`}
                      fill="none"
                      stroke={p.ink}
                      strokeWidth={Math.max(2, gap * 0.06)}
                      strokeLinecap="round"
                    />
                  </g>
                ))
              : null}
          </svg>
        ) : null}
      </div>
    );
  };

  return { box: { width: bw, height: bh, anchor: [ax, ay] }, poses: names, render, symmetric: rig.symmetric };
};
