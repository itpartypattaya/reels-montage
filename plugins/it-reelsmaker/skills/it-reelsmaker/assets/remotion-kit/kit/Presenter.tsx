// Presenter over a scene (references/effects.md, section 9): the speaker's cut-out figure (matte.py cut → webm with alpha)
// in front of another scene: a screen recording, a video under review, B-roll, a slide, a code scene. Three layouts:
//   review: the scene in a panel at the top, the presenter at the bottom edge, forehead at the panel's bottom edge, body goes off frame;
//   stream: the scene full frame, a small presenter in a bottom corner, the scene corner under them softly darkened;
//   window: no cut-out, the speaker's regular video in a rounded window in a corner (cheap, no rembg needed).
// Scale and position come from `matte.py place` (props scale, x, y); the code does not pick them. Do not change the side by hand:
// where the figure touches the source frame edge (hand, elbow, lower body), that edge must match the frame edge, otherwise
// a cut-off arm shows mid-screen (effects.md, section 9, “Source crops”; place --side auto picks the side itself).
// The figure is separated from the scene by composition (overlapping the panel edge, darkening the corner), with no outline, glow or shadow.
import React from "react";
import { AbsoluteFill, Easing, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

export type PresenterLayout = "review" | "stream" | "window";
export type PresenterProps = {
  src: string; // public/: <id>/host.webm (review/stream) or <id>/video.mp4 (window)
  from: number; // s on the video timeline
  dur: number;
  srcFrom?: number; // s inside src (for window, the time in video.mp4; the webm from matte.py starts at 0)
  layout: PresenterLayout;
  side: "left" | "right";
  // review / stream, cut-out figure: all three from matte.py place (required; without them the render fails)
  scale?: number;
  x?: number; // top left of the scaled figure video, px
  y?: number;
  panel?: [number, number, number, number] | null; // x, y, w, h of the scene in review
  scene: React.ReactNode; // scene content (fills the panel/frame, objectFit cover)
  bg: string; // background under the panel: a brand color (primary/light), not a black hole
  radius?: number;
  // window: window size, the face in the source and, optionally, the window's top-left position (x, y). Without x/y, the bottom
  // corner on the side `side`, above the app UI. Top-level scale/x/y are not used in window.
  window?: { w: number; h: number; face: [number, number, number, number]; x?: number; y?: number };
  ring?: string; // window: a thin ring in a brand color (optional)
  enter?: number; // entry frames, 12–16
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const easeOut = Easing.out(Easing.cubic);

const Inner: React.FC<PresenterProps> = (p) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = Math.round(p.dur * fps);
  const enter = p.enter ?? 14;
  const inP = interpolate(frame, [0, enter], [0, 1], { ...clamp, easing: easeOut });
  const outP = interpolate(frame, [n - 8, n], [1, 0], clamp); // exit is faster than entry
  const r = p.radius ?? 36;
  const sideSign = p.side === "left" ? -1 : 1;

  if (p.layout !== "window" && (p.scale === undefined || p.x === undefined || p.y === undefined)) {
    throw new Error(`Presenter ${p.layout}: scale, x, y from matte.py place are required`);
  }
  const scale = p.scale ?? 1;
  const figure =
    p.layout === "window" ? null : (
      <div
        style={{
          position: "absolute", left: p.x, top: p.y, width: 1080 * scale, height: 1920 * scale,
          transform: `translateY(${(1 - inP) * 220}px)`, opacity: outP,
        }}
      >
        <OffthreadVideo src={staticFile(p.src)} transparent muted startFrom={Math.round((p.srcFrom ?? 0) * fps)}
          style={{ width: "100%", height: "100%" }} />
      </div>
    );

  if (p.layout === "review") {
    const [px, py, pw, ph] = p.panel ?? [40, 230, 1000, 900];
    return (
      <AbsoluteFill style={{ background: p.bg, opacity: Math.min(1, inP * 3) * outP }}>
        <div style={{ position: "absolute", left: px, top: py + (1 - inP) * -60, width: pw, height: ph, borderRadius: r,
          overflow: "hidden" }}>
          {p.scene}
        </div>
        {figure}
      </AbsoluteFill>
    );
  }

  if (p.layout === "stream") {
    // darkened corner under the presenter: the figure does not drown in a busy scene (instead of an outline and shadow)
    const cx = p.side === "left" ? "0%" : "100%";
    return (
      <AbsoluteFill style={{ opacity: Math.min(1, inP * 3) * outP }}>
        <AbsoluteFill>{p.scene}</AbsoluteFill>
        <AbsoluteFill style={{ background: `radial-gradient(ellipse 70% 45% at ${cx} 100%, rgba(0,0,0,0.38), rgba(0,0,0,0) 70%)` }} />
        {figure}
      </AbsoluteFill>
    );
  }

  // window: the speaker's video in a window, framed on the face (face in the upper third of the window)
  const w = p.window ?? { w: 360, h: 460, face: [380, 700, 215, 295] as [number, number, number, number] };
  const [fx, fy, fw, fh] = w.face;
  const k = (w.h * 0.36) / fh; // face is ~36 % of the window height
  const left = w.w / 2 - (fx + fw / 2) * k;
  const top = w.h * 0.3 - (fy + fh / 2) * k;
  const wx = w.x ?? (p.side === "left" ? 40 : 1080 - 120 - w.w); // on the right, left of the likes column
  const wy = w.y ?? 1920 - 420 - w.h - 20; // above the app UI
  return (
    <AbsoluteFill style={{ opacity: Math.min(1, inP * 3) * outP }}>
      <AbsoluteFill>{p.scene}</AbsoluteFill>
      <div style={{ position: "absolute", left: wx + sideSign * (1 - inP) * 80, top: wy, width: w.w, height: w.h, borderRadius: r,
        overflow: "hidden", boxShadow: p.ring ? `0 0 0 4px ${p.ring}` : undefined }}>
        <div style={{ position: "absolute", left, top, width: 1080 * k, height: 1920 * k }}>
          <OffthreadVideo src={staticFile(p.src)} muted startFrom={Math.round((p.srcFrom ?? p.from) * fps)}
            style={{ width: "100%", height: "100%" }} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** A “presenter over a scene” segment on the video timeline. Sound comes from the main video (the figure is muted). */
export const Presenter: React.FC<PresenterProps> = (p) => {
  const { fps } = useVideoConfig();
  return (
    <Sequence from={Math.round(p.from * fps)} durationInFrames={Math.max(1, Math.round(p.dur * fps))}>
      <Inner {...p} />
    </Sequence>
  );
};
