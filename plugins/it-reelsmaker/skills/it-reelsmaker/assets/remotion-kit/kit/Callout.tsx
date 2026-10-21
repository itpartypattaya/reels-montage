// Callouts (references/callouts.md, experimental): a mark on an object of the rough cut, a leader line drawn from it
// at 45° and then level, and a label wiping in from the line. Variants: `tag` — the subject's name on the style's
// marker plate, an optional second line in small caps under it; `line` — the name over the level line, no plate;
// `badge` — a circle holding a number; `ring` — a ring around the object instead of the dot; `dimension` — a measuring
// line between two points with its label at the middle. The anchor is a point of the rough cut (or a path of points:
// keys, a track, a person), carried to the screen by the same camera and drift as the video (kit/anchor.ts); the line
// and the label keep their size in screen pixels.
// Props come from `visual_plan.py export … --props` (props.callouts), which has checked them against faces, the
// subtitles, the UI zones and the other graphics. Only over the full frame: in the framed format and while a scene
// moves or covers the video (split, panel, window, full) nothing is drawn (validate refuses that overlap).
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { CALLOUT, CALLOUT_TIMES, anchorOnScreen, calloutGeometry, pathAt, zoomAt } from "./anchor";
import type { DriftSegment, PathRow, Shot } from "./anchor";
import { Brand, Look, alpha } from "./brand";
import { fitSize, useFontsReady } from "./Phrase";
import type { Word } from "./Subtitles";
import { speakerRectAt } from "./scenes";
import type { ResolvedTone, SceneSpec, SceneTone } from "./scenes";
import { SCENE_TONES, easeOut } from "./scenes/tones";

export type CalloutSpec = {
  id: string;
  variant: "tag" | "line" | "badge" | "ring" | "dimension" | string;
  start: number; // second of the output timeline
  dur: number;
  anchor: number[]; // x, y on the 1080×1920 rough cut
  path?: PathRow[] | null; // a moving anchor: [t from the start, x, y, visibility, scale] (kit/anchor.ts pathAt)
  to?: number[] | null; // dimension: the second point on the rough cut
  radius?: number | null; // ring: the radius on the rough cut, px
  side: "left" | "right";
  below?: boolean | null; // the label under the dot instead of above it
  lines: string[]; // the subject (a badge: the number); an optional second line (a detail)
  w: number; // the label's width, a badge's diameter (visual_plan.py): the text is fitted inside, so the checked box holds
  tone?: SceneTone | string | null; // null → the video's scene tone
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const PULSE = 18; // frames per pulse of the dot's ring (only where the brand tone allows overshoot)
type Pt = number[];
const lerp = (a: Pt, b: Pt, p: number): Pt => [a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p];

const Callout: React.FC<{
  c: CalloutSpec; frame: number; brand: Brand; look: Look; fonts: { heading: string; body: string }; bt: ResolvedTone;
  pos: { x: number; y: number }; to: { x: number; y: number } | null; r: number; vis: number; ready: boolean;
}> = ({ c, frame, brand, look, fonts, bt, pos, to, r, vis, ready }) => {
  const tone: SceneTone = c.tone && c.tone in SCENE_TONES ? (c.tone as SceneTone) : bt.sceneTone;
  const toneIn = SCENE_TONES[tone].in;
  const k = toneIn / CALLOUT_TIMES.calmIn; // parody: 0, everything at once
  const at = (q: number[]) => (k === 0 ? 1 : interpolate(frame, [q[0] * k, q[1] * k], [0, 1], { ...clamp, easing: easeOut }));
  const n = Math.round(c.dur * 30);
  const out = (toneIn === 0 ? (frame < n ? 1 : 0) : interpolate(frame, [n - CALLOUT_TIMES.out, n], [1, 0], clamp)) * vis;
  if (out <= 0 || frame < 0) return null;
  const variant = c.variant || "tag";
  const sub = (c.lines[1] ?? "").trim();
  const g = calloutGeometry(pos.x, pos.y, c.side, !!c.below, c.w, !!sub, variant, r, to ? [to.x, to.y] : null);
  const [px, py] = g.dot;
  const [bx, by, bw, bh] = g.plate;
  const dot = at(CALLOUT_TIMES.dot);
  const line = at(CALLOUT_TIMES.line);
  const wipeT = at(CALLOUT_TIMES.title);
  const wipeS = at(CALLOUT_TIMES.sub);
  const left = c.side === "left" && variant !== "dimension";
  const wipe = (p: number) => (left ? `inset(0 0 0 ${(1 - p) * 100}%)` : `inset(0 ${(1 - p) * 100}% 0 0)`);
  const title = c.lines[0] ?? "";
  const pad = 2 * CALLOUT.padX;
  const ts = fitSize({ text: title, size: CALLOUT.titleSize, font: fonts.heading, weight: 700,
    maxWidth: variant === "badge" ? c.w * 0.78 : c.w - pad, ready });
  const ss = !sub ? CALLOUT.subSize : variant === "badge"
    ? fitSize({ text: sub, size: CALLOUT.badgeSub, font: fonts.body, weight: 600, maxWidth: c.w * 0.8, tracking: 0.08, upper: true, ready })
    : fitSize({ text: sub, size: CALLOUT.subSize, font: fonts.body, weight: 600, maxWidth: c.w - pad, tracking: 0.12, upper: true, ready });
  const ink = look.onMark;
  const c0 = brand.colors;
  // the ring pulses twice after the dot lands, only where the brand tone allows overshoot (calm brands: a still dot)
  const pf = frame - CALLOUT_TIMES.dot[1] * k;
  const pulse = bt.overshoot && variant !== "ring" && variant !== "dimension" && pf >= 0 && pf < 2 * PULSE ? (pf % PULSE) / PULSE : null;
  const stroke = { fill: "none", stroke: look.mark, strokeWidth: CALLOUT.stroke, strokeLinejoin: "round" as const, strokeLinecap: "round" as const };

  let lines: React.ReactNode;
  let mark: React.ReactNode;
  if (variant === "dimension") {
    // the ticks land with the dot's timing, the line grows from its middle to both ends
    const [a, b] = g.segs[0];
    const mid = g.elbow;
    lines = (
      <>
        <path d={`M ${mid[0]} ${mid[1]} L ${lerp(mid, a, line).join(" ")} M ${mid[0]} ${mid[1]} L ${lerp(mid, b, line).join(" ")}`} {...stroke} />
        {g.segs.slice(1).map((s, i) => {
          const m = lerp(s[0], s[1], 0.5);
          return <path key={i} d={`M ${lerp(m, s[0], dot).join(" ")} L ${lerp(m, s[1], dot).join(" ")}`} {...stroke} />;
        })}
      </>
    );
  } else {
    const [o, e] = g.segs[0];
    const end = g.segs[1][1];
    const len = Math.hypot(e[0] - o[0], e[1] - o[1]) + Math.abs(end[0] - e[0]);
    lines = <path d={`M ${o[0]} ${o[1]} L ${e[0]} ${e[1]} L ${end[0]} ${end[1]}`} {...stroke} strokeDasharray={len}
      strokeDashoffset={len * (1 - line)} />;
    mark = variant === "ring" ? (
      <circle cx={px} cy={py} r={g.r} fill="none" stroke={look.mark} strokeWidth={CALLOUT.stroke + 1}
        strokeDasharray={2 * Math.PI * g.r} strokeDashoffset={2 * Math.PI * g.r * (1 - dot)}
        transform={`rotate(${c.side === "left" ? 180 : 0} ${px} ${py})`} />
    ) : (
      <>
        {pulse !== null ? <circle cx={px} cy={py} r={CALLOUT.dot * (1 + 1.6 * pulse)} fill="none" stroke={look.mark}
          strokeWidth={3} opacity={0.6 * (1 - pulse)} /> : null}
        <circle cx={px} cy={py} r={CALLOUT.dot * dot} fill={ink} />
        <circle cx={px} cy={py} r={CALLOUT.core * dot} fill={look.mark} />
      </>
    );
  }

  const row = (h: number) => ({ height: h, lineHeight: `${h}px`, padding: `0 ${CALLOUT.padX}px`, maxWidth: bw,
    boxSizing: "border-box" as const, whiteSpace: "nowrap" as const });
  let label: React.ReactNode;
  if (variant === "badge") {
    const s = 0.4 + 0.6 * wipeT;
    label = (
      <div style={{ width: bw, height: bh, borderRadius: "50%", backgroundColor: look.mark, color: ink, display: "flex",
        flexDirection: "column", alignItems: "center", justifyContent: "center", transform: `scale(${wipeT > 0 ? s : 0})`,
        opacity: wipeT }}>
        <div style={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: ts, lineHeight: 1, whiteSpace: "nowrap" }}>{title}</div>
        {sub ? (
          <div style={{ marginTop: 6, fontFamily: fonts.body, fontWeight: 600, fontSize: ss, letterSpacing: "0.08em",
            textTransform: "uppercase", whiteSpace: "nowrap", opacity: wipeS }}>{sub}</div>
        ) : null}
      </div>
    );
  } else if (variant === "line") {
    // over the picture with no plate: validate measures the text's contrast against the frames under it
    const txt = c0.text_on_primary;
    label = (
      <>
        <div style={{ ...row(CALLOUT.titleH), color: txt, fontFamily: fonts.heading, fontWeight: 700, fontSize: ts, clipPath: wipe(wipeT) }}>
          {title}
        </div>
        {sub ? (
          <div style={{ ...row(CALLOUT.subH), color: txt, fontFamily: fonts.body, fontWeight: 600, fontSize: ss,
            letterSpacing: "0.12em", textTransform: "uppercase", clipPath: wipe(wipeS) }}>
            {sub}
          </div>
        ) : null}
      </>
    );
  } else {
    label = (
      <>
        <div style={{ ...row(CALLOUT.titleH), backgroundColor: look.mark, color: look.onMark, fontFamily: fonts.heading,
          fontWeight: 700, fontSize: ts, clipPath: wipe(wipeT) }}>
          {title}
        </div>
        {sub ? (
          <div style={{ ...row(CALLOUT.subH), backgroundColor: alpha(c0.primary, 0.92), color: c0.text_on_primary,
            fontFamily: fonts.body, fontWeight: 600, fontSize: ss, letterSpacing: "0.12em", textTransform: "uppercase",
            clipPath: wipe(wipeS) }}>
            {sub}
          </div>
        ) : null}
      </>
    );
  }
  const align = variant === "dimension" || variant === "badge" ? "center" : left ? "flex-end" : "flex-start";
  return (
    <div style={{ position: "absolute", inset: 0, opacity: out }}>
      <svg width={1080} height={1920} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
        {lines}
        {mark}
      </svg>
      <div data-rk={`callout:${c.id}`} style={{ position: "absolute", left: bx, top: by, width: bw, display: "flex",
        flexDirection: "column", alignItems: align }}>
        {label}
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
  const rect = speakerRectAt(scenes, frame, 30, words, bt);
  if (Math.abs(rect.k - 1) > 1e-3 || rect.x !== 0 || rect.y !== 0) return null;
  return (
    <>
      {callouts.map((c) => {
        const f0 = Math.round(c.start * 30);
        const f = frame - f0;
        if (f < 0 || f > Math.round(c.dur * 30)) return null;
        const p = pathAt(c.path, c.anchor, f / 30);
        const pos = anchorOnScreen(p.x, p.y, t, camera, segments, drift, end);
        const to = c.to ? anchorOnScreen(c.to[0], c.to[1], t, camera, segments, drift, end) : null;
        const r = (c.radius ?? 0) * p.s * zoomAt(t, camera, segments, drift, end);
        return <Callout key={c.id} c={c} frame={f} brand={brand} look={look} fonts={fonts} bt={bt} pos={pos} to={to}
          r={r} vis={p.v} ready={ready} />;
      })}
    </>
  );
};
