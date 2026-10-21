// The virtual camera, the template's drift and the callout's layout as plain math, with no Remotion import: ReelKit
// draws the rough cut with it, CalloutLayer places its dots and labels with it, and visual_plan.py repeats every
// number (camera_at, anchor_on_screen, callout_geometry), so the plan checks a callout where the render draws it.
// tests/scripts/test_callouts.py runs this file with node on shared control points against the Python side.

export type Box = { x: number; y: number; w: number; h: number };
export type Shot = { t: number; z: number; cx: number; cy: number; drift?: number; whip?: boolean };
export type Cam = { z: number; cx: number; cy: number; blur: number };
// the camera's clamp geometry: the framed window and the video's cover in it; null — the whole 1080×1920 frame
export type CamView = { win: Box; video: Box } | null;
// a span of the rough cut (captions.json segments): the drift alternates its direction by i
export type DriftSegment = { i: number; out_start: number; out_dur: number };

export const WHIP = 7; // frames
export const WHIP_BLUR = 6; // px on screen at the whip's peak (camera.md), whatever the zoom
export const DRIFT = 0.05; // the template's slow push-in per span when there is no camera
const FULL: Box = { x: 0, y: 0, w: 1080, h: 1920 };

const unit = (t: number, a: number, b: number) => Math.min(1, Math.max(0, (t - a) / (b - a)));
const easeOut = (p: number) => 1 - (1 - p) ** 3; // Remotion's Easing.out(Easing.cubic)

// the camera window never shows past the video: in the full frame cx within [540/z, 1080 − 540/z], cy within
// [960/z, 1920 − 960/z]; in the framed window (view) the window's half size over z inside the video's cover — the same rule
// as reels_common.cam_fit, so validate and faces.py check the faces where this draws them (T7: a full-frame clamp moved a
// framed shot at cx 820 to 540)
export const fitCamera = (z: number, cx: number, cy: number, view?: CamView): Cam => {
  const zz = Math.max(1, z);
  const win = view?.win ?? FULL;
  const v = view?.video ?? FULL;
  const hx = win.w / 2 / zz;
  const hy = win.h / 2 / zz;
  return { z: zz, cx: Math.min(Math.max(cx, v.x + hx), v.x + v.w - hx), cy: Math.min(Math.max(cy, v.y + hy), v.y + v.h - hy), blur: 0 };
};
const shotAt = (s: Shot, next: Shot | undefined, t: number, end: number, view?: CamView): Cam => {
  const k = unit(t, s.t, Math.max(s.t + 0.01, next ? next.t : end));
  return fitCamera(s.z * (1 + (s.drift ?? 0) * k), s.cx, s.cy, view);
};
export const cameraAt = (shots: Shot[], t: number, end: number, fps: number, view?: CamView): Cam => {
  let i = -1;
  shots.forEach((s, k) => { if (s.t <= t + 1e-6) i = k; });
  const win = view?.win ?? FULL;
  if (i < 0) return fitCamera(1, win.x + win.w / 2, win.y + win.h / 2, view);
  const cam = shotAt(shots[i], shots[i + 1], t, end, view);
  const p = (t - shots[i].t) * fps / WHIP;
  if (!shots[i].whip || i === 0 || p >= 1) return cam;
  const prev = shotAt(shots[i - 1], shots[i], shots[i].t, end, view); // where the previous shot ended (with its drift)
  const e = easeOut(Math.max(0, p));
  return { z: prev.z + (cam.z - prev.z) * e, cx: prev.cx + (cam.cx - prev.cx) * e, cy: prev.cy + (cam.cy - prev.cy) * e,
    blur: Math.sin(Math.PI * Math.max(0, p)) * WHIP_BLUR };
};

/** The template's drift at second t (no camera): each span of the rough cut scales around the frame's center,
 *  1 → 1.05 on even spans and back on odd ones; past the last span, the last one. */
export const driftZoom = (segments: DriftSegment[], t: number): number => {
  const seg = segments.find((g) => t >= g.out_start && t < g.out_start + g.out_dur) ?? segments[segments.length - 1];
  if (!seg) return 1;
  const k = unit(t, seg.out_start, seg.out_start + Math.max(1e-6, seg.out_dur));
  return seg.i % 2 === 0 ? 1 + DRIFT * k : 1 + DRIFT - DRIFT * k;
};

/** Where point (x, y) of the full-frame rough cut is on screen at second t: through camera.json's shots (camera.md:
 *  x' = (x − cx)·z + 540), else through the drift (around the frame's center), else where it is. */
export const anchorOnScreen = (x: number, y: number, t: number, camera: Shot[] | null | undefined, segments: DriftSegment[],
  drift: boolean | null | undefined, end: number, fps = 30): { x: number; y: number } => {
  if (camera?.length) {
    const c = cameraAt(camera, t, end, fps);
    return { x: (x - c.cx) * c.z + 540, y: (y - c.cy) * c.z + 960 };
  }
  const z = drift ? driftZoom(segments, t) : 1;
  return { x: 540 + (x - 540) * z, y: 960 + (y - 960) * z };
};

// ── the callout's layout on screen (references/callouts.md), in px, the same at any camera ──
export const CALLOUT = {
  dot: 14, // the dot's outer radius: a disc in the label's color, the line's color inside it (CORE)
  core: 8,
  stroke: 5, // the leader line
  reach: 90, // the 45° run from the dot to the elbow, in x and in y
  run: 48, // the level run from the elbow to the label
  titleH: 70, // the title's plate: 52 px, the heading font, 700
  titleSize: 52,
  subH: 50, // the second line's plate: 34 px caps, the body font, 600
  subSize: 34,
  padX: 18,
};

// the entrance in frames at the calm tone (14 frames in): the dot, the line drawing itself, the title's wipe, the second
// line's wipe; another tone scales them by its own entrance (punchy 8/14, hype 5/14; parody — all at once); the exit is
// a fade of `out` frames
export const CALLOUT_TIMES = { dot: [0, 6], line: [3, 11], title: [8, 18], sub: [11, 21], out: 6, calmIn: 14 };
/** Frames until the callout is fully on screen, for a tone whose scene entrance is toneIn frames. */
export const calloutEntrance = (toneIn: number, sub: boolean): number =>
  Math.ceil((sub ? CALLOUT_TIMES.sub[1] : CALLOUT_TIMES.title[1]) * toneIn / CALLOUT_TIMES.calmIn);

/** The callout's points and boxes for an anchor already on screen (px, py): the label goes to `side` of the dot, up
 *  from it (or down, `below`); the line runs 45° to the elbow, then level to the label, which it meets at the title's
 *  middle. w — the label's width (visual_plan.py measures it); sub — a second line under the title. */
export const calloutGeometry = (px: number, py: number, side: string, below: boolean, w: number, sub: boolean) => {
  const sx = side === "left" ? -1 : 1;
  const sy = below ? 1 : -1;
  const ex = px + sx * CALLOUT.reach;
  const ey = py + sy * CALLOUT.reach;
  const hx = ex + sx * CALLOUT.run;
  const h = CALLOUT.titleH + (sub ? CALLOUT.subH : 0);
  return {
    dot: [px, py], elbow: [ex, ey], end: [hx, ey],
    plate: [sx > 0 ? hx : hx - w, ey - CALLOUT.titleH / 2, w, h],
  };
};
