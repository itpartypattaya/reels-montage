# Sample mascot drawn in code: Pip

One complete mascot module for the contract in `references/mascot.md`, as a starting point for a brand's own character: a rounded note with two dot eyes, a mouth and two arms of two segments, in the brand's colors. It shows the conventions every drawn mascot follows: `box` and `poses` as literals (the scripts read them), the box holding every pose with the arms raised, the anchor between the eyes, poses as a table of numbers blended by `rig.ts`, the mouth from `f.open` and `f.wide` over the pose's smile (`mouthPath`), the eyelids from `f.lid`, no text, no outline, no shadow, no randomness.

Copy it into the person's Remotion project as `src/mascot/<Name>.tsx`, change `acme` to the brand's slug, then make it the brand's own: the body's shape, the proportions, the eyes, what each pose does. Every brand gets its own figure; this one is only the pattern. Register it: `brand.py mascot <slug> --drawn src/mascot/<Name>.tsx --symmetric` (Pip mirrors well) and `brand.py stage <slug> --remotion <dir>`; check the types with `npx tsc`.

```tsx
import brand from "../brands/acme.json";
import type { MascotBox, MascotFrame } from "../kit/mascot/types";
import { armPath, mix, mouthPath, poseAt } from "../kit/mascot/rig";

// Pip: a rounded note with two arms, drawn in code in the brand's colors. The box holds every pose, arms included.
export const box: MascotBox = { width: 520, height: 480, anchor: [260, 190] };
export const poses = ["neutral", "talk", "point_left", "point_right", "point_up", "palm", "think", "surprise", "celebrate", "shrug", "wink"];

// a pose as numbers: the arms' angles (degrees, 0 = right, 90 = down), the gaze, the head tilt, the brows, the smile
type P = { la1: number; la2: number; ra1: number; ra2: number; lookX: number; lookY: number; tilt: number; brow: number; smile: number };
const DOWN = { la1: 110, la2: 95, ra1: 70, ra2: 85 };
const base: P = { ...DOWN, lookX: 0, lookY: 0, tilt: 0, brow: 0, smile: 1 };
const POSE: Record<string, P> = {
  neutral: base,
  talk: { ...base, la1: 130, la2: 60 },
  point_left: { ...base, la1: 180, la2: 185, lookX: -8 },
  point_right: { ...base, ra1: 0, ra2: -5, lookX: 8 },
  point_up: { ...base, la1: 200, la2: 270, lookY: -8 },
  palm: { ...base, la1: 135, la2: 200, lookX: -4 },
  think: { ...base, la1: 100, la2: -60, lookX: 6, lookY: -6, tilt: 6, brow: 1, smile: 0.4 },
  surprise: { ...base, la1: 200, la2: 240, ra1: -20, ra2: -60, brow: 1.5, smile: 0 },
  celebrate: { ...base, la1: 225, la2: 260, ra1: -45, ra2: -80, smile: 1.5 },
  shrug: { ...base, la1: 160, la2: 230, ra1: 20, ra2: -50, brow: -1, tilt: -4, smile: 0.5 },
  wink: { ...base, la1: 120, la2: 270, smile: 1.3 },
};
const ANGLES = ["la1", "la2", "ra1", "ra2"] as const;

const C = brand.colors as unknown as Record<string, string>; // via unknown: a profile with `colors.extra` (nested) type-checks too
const BODY = C.primary;
const LIMB = C.accent ?? C.primary;
const INK = "#1B1B1F"; // the features: dark on a light or saturated body; a very dark body takes a light ink

export const render = (f: MascotFrame) => {
  const p = poseAt(POSE, f, ANGLES);
  const eyeH = mix(26, 3, f.lid); // f.lid: 0 open, 0.5 half shut, 1 shut
  const ex = 30 + p.lookX;
  const ey = 190 + p.lookY;
  const mouthY = 262 + p.lookY * 0.5;
  // the pose's own mouth (its smile) is the base the speech opens: Pip talks and keeps smiling
  const mouth = mouthPath({ width: 46, curve: 8 * p.smile }, f.open, f.wide);
  const winkR = f.pose === "wink" && f.k > 0.5;
  return (
    <svg width={520} height={480} viewBox="0 0 520 480" style={{ overflow: "visible" }}>
      <path d={armPath([155, 300], { a1: p.la1, a2: p.la2 }, 70, 62)} stroke={LIMB} strokeWidth={22} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d={armPath([365, 300], { a1: p.ra1, a2: p.ra2 }, 70, 62)} stroke={LIMB} strokeWidth={22} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <rect x={200} y={400} width={30} height={56} rx={15} fill={LIMB} />
      <rect x={290} y={400} width={30} height={56} rx={15} fill={LIMB} />
      <g transform={`rotate(${p.tilt} 260 260)`}>
        <rect x={150} y={80} width={220} height={330} rx={96} fill={BODY} />
        <ellipse cx={260 - ex} cy={ey} rx={12} ry={eyeH / 2} fill={INK} />
        {winkR ? (
          <path d={`M${260 + ex - 12} ${ey} Q${260 + ex} ${ey - 10} ${260 + ex + 12} ${ey}`} stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round" />
        ) : (
          <ellipse cx={260 + ex} cy={ey} rx={12} ry={eyeH / 2} fill={INK} />
        )}
        {p.brow !== 0 ? (
          <g stroke={INK} strokeWidth={6} strokeLinecap="round">
            <line x1={260 - ex - 14} y1={ey - 32 - p.brow * 6} x2={260 - ex + 12} y2={ey - 34 - p.brow * 6} />
            <line x1={260 + ex - 12} y1={ey - 34 - p.brow * 6} x2={260 + ex + 14} y2={ey - 32 - p.brow * 6} />
          </g>
        ) : null}
        <path transform={`translate(${260 + p.lookX * 0.6} ${mouthY - 4})`} d={mouth.d} fill={mouth.filled ? INK : "none"}
          stroke={INK} strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
};
```

**What to change for a brand:** the body (the `rect` → any closed shape inside the box), the arms' lengths (`70, 62`) and shoulders, the colors (`BODY`, `LIMB` from the profile's roles; the features' ink by the body's contrast), the pose table. **What to keep:** the literal `box` and `poses`, the anchor between the eyes, every pose inside the box, `neutral` in the list, the drawing as a pure function of the frame. Type-checked against the kit (`tsc`, remotion 4.0.526) as written here.
