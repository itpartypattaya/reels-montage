// Callouts (references/callouts.md, experimental): a dot on an object of the rough cut, a leader line drawn from it
// at 45° and then level, and a label plate wiping in from the line — the subject's name on the style's marker plate,
// an optional second line in small caps under it. The anchor is a point of the rough cut, carried to the screen by the
// same camera and drift as the video (kit/anchor.ts); the line and the label keep their size in screen pixels.
// Props come from `visual_plan.py export … --props` (props.callouts), which has checked them against faces, the
// subtitles, the UI zones and the other graphics. Only over the full frame: in the framed format and while a scene
// moves or covers the video (split, panel, window, full) nothing is drawn (validate refuses that overlap).
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { CALLOUT, CALLOUT_TIMES, anchorOnScreen, calloutGeometry } from "./anchor";
import type { DriftSegment, Shot } from "./anchor";
import { Brand, Look, alpha } from "./brand";
import { fitSize, useFontsReady } from "./Phrase";
import type { Word } from "./Subtitles";
import { speakerRectAt } from "./scenes";
import type { ResolvedTone, SceneSpec, SceneTone } from "./scenes";
import { SCENE_TONES, easeOut } from "./scenes/tones";

export type CalloutSpec = {
  id: string;
  variant: "tag" | string;
  start: number; // second of the output timeline
  dur: number;
  anchor: number[]; // x, y on the 1080×1920 rough cut
  side: "left" | "right";
  below?: boolean | null; // the label under the dot instead of above it
  lines: string[]; // the subject; an optional second line (a detail)
  w: number; // the label's width (visual_plan.py): the text is fitted inside it, so the checked box holds
  tone?: SceneTone | string | null; // null → the video's scene tone
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const PULSE = 18; // frames per pulse of the dot's ring (only where the brand tone allows overshoot)

const Callout: React.FC<{
  c: CalloutSpec; frame: number; brand: Brand; look: Look; fonts: { heading: string; body: string }; bt: ResolvedTone;
  pos: { x: number; y: number }; ready: boolean;
}> = ({ c, frame, brand, look, fonts, bt, pos, ready }) => {
  const tone: SceneTone = c.tone && c.tone in SCENE_TONES ? (c.tone as SceneTone) : bt.sceneTone;
  const toneIn = SCENE_TONES[tone].in;
  const k = toneIn / CALLOUT_TIMES.calmIn; // parody: 0, everything at once
  const at = (r: number[]) => (k === 0 ? 1 : interpolate(frame, [r[0] * k, r[1] * k], [0, 1], { ...clamp, easing: easeOut }));
  const n = Math.round(c.dur * 30);
  const out = toneIn === 0 ? (frame < n ? 1 : 0) : interpolate(frame, [n - CALLOUT_TIMES.out, n], [1, 0], clamp);
  if (out <= 0 || frame < 0) return null;
  const sub = (c.lines[1] ?? "").trim();
  const g = calloutGeometry(pos.x, pos.y, c.side, !!c.below, c.w, !!sub);
  const [px, py] = g.dot;
  const [ex, ey] = g.elbow;
  const [hx, hy] = g.end;
  const [bx, by, bw] = g.plate;
  const len = Math.hypot(ex - px, ey - py) + Math.abs(hx - ex);
  const dot = at(CALLOUT_TIMES.dot);
  const line = at(CALLOUT_TIMES.line);
  const wipeT = at(CALLOUT_TIMES.title);
  const wipeS = at(CALLOUT_TIMES.sub);
  const left = c.side === "left";
  const wipe = (p: number) => (left ? `inset(0 0 0 ${(1 - p) * 100}%)` : `inset(0 ${(1 - p) * 100}% 0 0)`);
  const title = c.lines[0] ?? "";
  const ts = fitSize({ text: title, size: CALLOUT.titleSize, font: fonts.heading, weight: 700, maxWidth: c.w - 2 * CALLOUT.padX, ready });
  const ss = sub ? fitSize({ text: sub, size: CALLOUT.subSize, font: fonts.body, weight: 600, maxWidth: c.w - 2 * CALLOUT.padX,
    tracking: 0.12, upper: true, ready }) : CALLOUT.subSize;
  const ink = look.onMark;
  // the ring pulses twice after the dot lands, only where the brand tone allows overshoot (calm brands: a still dot)
  const pf = frame - CALLOUT_TIMES.dot[1] * k;
  const pulse = bt.overshoot && pf >= 0 && pf < 2 * PULSE ? (pf % PULSE) / PULSE : null;
  const c0 = brand.colors;
  return (
    <div style={{ position: "absolute", inset: 0, opacity: out }}>
      <svg width={1080} height={1920} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
        <path d={`M ${px} ${py} L ${ex} ${ey} L ${hx} ${hy}`} fill="none" stroke={look.mark} strokeWidth={CALLOUT.stroke}
          strokeLinejoin="round" strokeDasharray={len} strokeDashoffset={len * (1 - line)} />
        {pulse !== null ? <circle cx={px} cy={py} r={CALLOUT.dot * (1 + 1.6 * pulse)} fill="none" stroke={look.mark}
          strokeWidth={3} opacity={0.6 * (1 - pulse)} /> : null}
        <circle cx={px} cy={py} r={CALLOUT.dot * dot} fill={ink} />
        <circle cx={px} cy={py} r={CALLOUT.core * dot} fill={look.mark} />
      </svg>
      <div data-rk={`callout:${c.id}`} style={{ position: "absolute", left: bx, top: by, width: bw, display: "flex", flexDirection: "column",
        alignItems: left ? "flex-end" : "flex-start" }}>
        <div style={{ height: CALLOUT.titleH, lineHeight: `${CALLOUT.titleH}px`, padding: `0 ${CALLOUT.padX}px`, maxWidth: bw,
          boxSizing: "border-box", whiteSpace: "nowrap", backgroundColor: look.mark, color: look.onMark, fontFamily: fonts.heading,
          fontWeight: 700, fontSize: ts, clipPath: wipe(wipeT) }}>
          {title}
        </div>
        {sub ? (
          <div style={{ height: CALLOUT.subH, lineHeight: `${CALLOUT.subH}px`, padding: `0 ${CALLOUT.padX}px`, maxWidth: bw,
            boxSizing: "border-box", whiteSpace: "nowrap", backgroundColor: alpha(c0.primary, 0.92), color: c0.text_on_primary,
            fontFamily: fonts.body, fontWeight: 600, fontSize: ss, letterSpacing: "0.12em", textTransform: "uppercase",
            clipPath: wipe(wipeS) }}>
            {sub}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export const CalloutLayer: React.FC<{
  callouts?: CalloutSpec[] | null; brand: Brand; look: Look; fonts: { heading: string; body: string }; bt: ResolvedTone;
  camera?: Shot[] | null; segments: DriftSegment[]; drift?: boolean | null; end: number; scenes?: SceneSpec[] | null; words: Word[];
}> = ({ callouts, brand, look, fonts, bt, camera, segments, drift, end, scenes, words }) => {
  const frame = useCurrentFrame();
  const ready = useFontsReady([fonts.heading, fonts.body]); // before the early returns
  if (!callouts?.length) return null;
  const t = frame / 30;
  // the speaker frame of a split/panel/window/full scene: the rough cut is not where the anchor points
  const r = speakerRectAt(scenes, frame, 30, words, bt);
  if (Math.abs(r.k - 1) > 1e-3 || r.x !== 0 || r.y !== 0) return null;
  return (
    <>
      {callouts.map((c) => {
        const f = frame - Math.round(c.start * 30);
        if (f < 0 || f > Math.round(c.dur * 30)) return null;
        const pos = anchorOnScreen(c.anchor[0], c.anchor[1], t, camera, segments, drift, end);
        return <Callout key={c.id} c={c} frame={f} brand={brand} look={look} fonts={fonts} bt={bt} pos={pos} ready={ready} />;
      })}
    </>
  );
};
