// Insert layers from the visual plan (src/plans/<id>.json ← `visual_plan.py export`): B-roll and memes.
// Empty list → the layers draw nothing, the video renders as if there were no inserts.
import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Brand, alpha } from "./brand";
import { FlashAt } from "./LightFlash";

export type Transition = "cut" | "whip" | "fade" | "flash" | "slide";
export type Insert = {
  id: string;
  kind: "broll" | "meme";
  mode: "replace" | "window" | "popup" | "cutaway";
  file: string; // path inside public/
  media: "video" | "image";
  start: number; // second on the output timeline
  dur: number;
  src_in?: number;
  transition_in: Transition;
  transition_out: Transition;
  position?: "top" | "middle" | "left" | "right" | null;
  audio?: boolean;
  plate?: boolean; // light icon → backing in the brand's primary color
  // x, y, w, h on the 1080×1920 screen: a meme popup (memes.py place) or a B-roll window in window mode
  // (a frame checked by the plan to stay clear of the face, keep_clear and the UI)
  box?: [number, number, number, number] | number[] | null;
};

// Safe zone for the window: not above y 220 and not below 1500 (UI), not right of x 960 (buttons on the right).
const SAFE = { left: 0, top: 220, right: 960, bottom: 1500 };
// Default window (no box in the plan): top of the frame, 900×675 (4:3), above the speaker's head in a medium shot.
const WINDOW_BOX = [60, 250, 900, 675];
const warnedBox = new Set<string>();

// Window frame: the plan's box, clamped to the safe zone; overflow → a warning (the plan should give a frame inside the zone).
const windowBox = (ins: Insert): number[] => {
  const b = ins.box && ins.box.length === 4 ? ins.box : WINDOW_BOX;
  const x = Math.max(SAFE.left, b[0]);
  const y = Math.max(SAFE.top, b[1]);
  const w = Math.max(1, Math.min(b[0] + b[2], SAFE.right) - x);
  const h = Math.max(1, Math.min(b[1] + b[3], SAFE.bottom) - y);
  if ((x !== b[0] || y !== b[1] || w !== b[2] || h !== b[3]) && !warnedBox.has(ins.id)) {
    warnedBox.add(ins.id);
    console.warn(`kit: window ${ins.id} [${b.join(", ")}] leaves the safe zone — clipped to [${x}, ${y}, ${w}, ${h}]`);
  }
  return [x, y, w, h];
};

// “framed”: the B-roll window is clamped to the window's text area instead of the safe zone
const areaBox = (ins: Insert, a: { x: number; y: number; w: number; h: number }): number[] => {
  const b = ins.box && ins.box.length === 4 ? ins.box : [a.x, a.y, a.w, Math.min(675, a.h)];
  const x = Math.max(a.x, b[0]);
  const y = Math.max(a.y, b[1]);
  return [x, y, Math.max(1, Math.min(b[0] + b[2], a.x + a.w) - x), Math.max(1, Math.min(b[1] + b[3], a.y + a.h) - y)];
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const easeOut = Easing.out(Easing.cubic);
const easeIn = Easing.in(Easing.cubic);

// Transition state at frame k of n: opacity, scale, blur, shift. "flash" is a hard cut under a light flash (FlashAt in
// layer(), centered on the cut: references/techniques.md), not a change of the insert itself.
const look = (k: number, n: number, tin: Transition, tout: Transition) => {
  const IN = tin === "whip" ? 5 : tin === "slide" ? 8 : tin === "fade" ? 7 : 0;
  const OUT = tout === "whip" ? 5 : tout === "slide" ? 8 : tout === "fade" ? 7 : 0;
  const pin = IN ? interpolate(k, [0, IN], [0, 1], { ...clamp, easing: easeOut }) : 1;
  const pout = OUT ? interpolate(k, [n - OUT, n], [1, 0], { ...clamp, easing: easeIn }) : 1;
  let opacity = 1, scale = 1, blur = 0, x = 0;
  if (tin === "fade") opacity *= pin;
  if (tout === "fade") opacity *= pout;
  if (tin === "whip") { scale *= 1 + 0.14 * (1 - pin); blur += 14 * (1 - pin); }
  if (tout === "whip") { scale *= 1 + 0.1 * (1 - pout); blur += 14 * (1 - pout); }
  if (tin === "slide") x += 1080 * (1 - pin);
  if (tout === "slide") x -= 1080 * (1 - pout);
  return { opacity, scale, blur, x };
};

const Media: React.FC<{ ins: Insert; style: React.CSSProperties; zoom?: boolean }> = ({ ins, style, zoom }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (ins.media === "image") {
    const z = zoom ? interpolate(frame, [0, ins.dur * fps], [1, 1.06], clamp) : 1;
    return <Img src={staticFile(ins.file)} style={{ ...style, transform: `scale(${z})` }} />;
  }
  return (
    <OffthreadVideo
      src={staticFile(ins.file)}
      startFrom={Math.round((ins.src_in ?? 0) * fps)}
      muted={!ins.audio}
      volume={ins.audio ? 0.6 : 0}
      transparent={ins.file.endsWith(".webm")}
      style={style}
    />
  );
};

// The “framed” window (ReelKit framedGeometry): a full-frame B-roll or cutaway plays inside it, a B-roll window stays in its
// text area (references/techniques.md: cutaways also go inside the window).
export type InsertArea = { win: { x: number; y: number; w: number; h: number }; r: number; area: { x: number; y: number; w: number; h: number } };

const Clip: React.FC<{ ins: Insert; brand: Brand; framed?: InsertArea | null }> = ({ ins, brand, framed }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = Math.round(ins.dur * fps);
  const l = look(frame, n, ins.transition_in, ins.transition_out);
  const fx: React.CSSProperties = {
    opacity: l.opacity,
    transform: `translateX(${l.x}px) scale(${l.scale})`,
    filter: l.blur ? `blur(${l.blur}px)` : undefined,
  };
  const full: React.CSSProperties = { width: 1080, height: 1920, objectFit: "cover" };
  let body: React.ReactNode;
  if ((ins.mode === "replace" || ins.mode === "cutaway") && framed) {
    const { x, y, w, h } = framed.win;
    const fit: React.CSSProperties = { width: w, height: h, objectFit: ins.mode === "cutaway" && ins.media === "image" ? "contain" : "cover", maxWidth: "none" };
    body = (
      <div style={{ position: "absolute", left: x, top: y, width: w, height: h, overflow: "hidden", borderRadius: framed.r }}>
        <div style={{ position: "absolute", inset: 0, ...fx, backgroundColor: brand.colors.primary }}>
          <Media ins={ins} style={fit} zoom />
        </div>
      </div>
    );
  } else if (ins.mode === "replace" || ins.mode === "cutaway") {
    body = (
      <AbsoluteFill style={{ ...fx, backgroundColor: brand.colors.primary }}>
        <Media ins={ins} style={ins.mode === "cutaway" && ins.media === "image" ? { ...full, objectFit: "contain" } : full} zoom />
      </AbsoluteFill>
    );
  } else if (ins.mode === "window") {
    // window over the speaker: the plan's frame (box) or, by default, the top of the frame; the speaker stays visible
    const [wx, wy, ww, wh] = framed ? areaBox(ins, framed.area) : windowBox(ins);
    body = (
      <div style={{ position: "absolute", left: wx, top: wy, width: ww, height: wh, borderRadius: 28, overflow: "hidden",
        backgroundColor: brand.colors.primary, ...fx }}>
        <Media ins={ins} style={{ width: "100%", height: "100%", objectFit: "cover" }} zoom />
      </div>
    );
  } else {
    // meme popup: never on the face — at the top (default), in the middle or at the side; a calm “pop” with no bounce
    const pop = interpolate(frame, [0, 7], [0.82, 1], { ...clamp, easing: easeOut });
    const out = interpolate(frame, [n - 6, n], [1, 0], clamp);
    // position and size come from the plan (memes.py place: clear of the face, subtitles, UI and graphics); without a plan —
    // a small 300 px meme at the top left. A meme is at most 460 px on its long side: never half the screen.
    const b = ins.box && ins.box.length === 4 ? ins.box : [60, 250, 300, 300];
    const place: React.CSSProperties = { left: b[0], top: b[1], width: Math.min(b[2], 460), height: Math.min(b[3], 460) };
    body = (
      <div style={{ position: "absolute", ...place, display: "flex", alignItems: "center",
        justifyContent: "center", opacity: Math.min(l.opacity, out, interpolate(frame, [0, 4], [0, 1], clamp)),
        transform: `translateX(${l.x}px) scale(${pop * l.scale})`, filter: l.blur ? `blur(${l.blur}px)` : undefined }}>
        <div style={ins.plate ? { backgroundColor: alpha(brand.colors.primary, 0.88), borderRadius: 24, padding: 18,
          width: "100%", height: "100%", boxSizing: "border-box", display: "flex", alignItems: "center", justifyContent: "center" }
          : { width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Media ins={ins} style={{ width: "100%", height: "100%", objectFit: "contain", borderRadius: ins.media === "image" ? 0 : 24 }} />
        </div>
      </div>
    );
  }
  return <>{body}</>;
};

const layer = (inserts: Insert[], brand: Brand, pick: (i: Insert) => boolean, fps: number, framed?: InsertArea | null) =>
  inserts.filter(pick).map((ins) => (
    <React.Fragment key={ins.id}>
      <Sequence from={Math.round(ins.start * fps)} durationInFrames={Math.max(1, Math.round(ins.dur * fps))} layout="none">
        <Clip ins={ins} brand={brand} framed={framed} />
      </Sequence>
      {ins.transition_in === "flash" ? <FlashAt t={ins.start} brand={brand} /> : null}
      {ins.transition_out === "flash" ? <FlashAt t={ins.start + ins.dur} brand={brand} /> : null}
    </React.Fragment>
  ));

// Above the main video, below graphics and subtitles: B-roll (replace/window) and full-screen memes (cutaway).
export const BrollLayer: React.FC<{ inserts: Insert[]; brand: Brand; framed?: InsertArea | null }> = ({ inserts, brand, framed }) => {
  const { fps } = useVideoConfig();
  return <>{layer(inserts, brand, (i) => i.kind === "broll" || i.mode === "cutaway", fps, framed)}</>;
};

// Above graphics, below subtitles: meme popups.
export const MemeLayer: React.FC<{ inserts: Insert[]; brand: Brand }> = ({ inserts, brand }) => {
  const { fps } = useVideoConfig();
  return <>{layer(inserts, brand, (i) => i.kind === "meme" && i.mode === "popup", fps)}</>;
};
