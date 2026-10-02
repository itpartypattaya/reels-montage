// ReelKit designed-scene layer (references/scenes.md): the active scene by type, display mode, transitions.
// Layer order in ReelKit: video → B-roll → hook → mark → SCENES → memes → subtitles → end card.
// The mode also changes the main video: Footage takes the speaker frame from speakerRectAt() (split ×0.56, bottom center,
// panel ×0.42 to the edge, window — a 360×480 window around the face); full covers the frame with a field, the voice continues.
// Transitions (brag): two dense layouts are never crossfaded — the old one leaves first, then the new one enters (content enters
// after 0.6 of the layout change, tones.ts → sceneTimeline), a full scene enters through a color field; on a pause — a cut.
import React from "react";
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Brand, Look, alpha, useLookFonts } from "../brand";
import type { Word } from "../Subtitles";
import { surfaces } from "./parts";
import { easeIn, easeOut, enterGrow, pickTone, resolveBrandTone, sceneTimeline, withRollTone } from "./tones";
import type { ResolvedTone, SceneCtx, SceneMode, SceneSpec, Stage } from "./types";
import { Hook } from "./Hook";
import { Quote } from "./Quote";
import { Slogan } from "./Slogan";
import { Stat } from "./Stat";
import { List } from "./List";
import { Contrast } from "./Contrast";
import { WordViz } from "./WordViz";
import { Chat } from "./Chat";
import { Ui } from "./Ui";
import { CtaAction } from "./CtaAction";

const BY_TYPE: Record<string, React.FC<{ c: SceneCtx }>> = {
  hook: Hook, quote: Quote, slogan: Slogan, stat: Stat, list: List, contrast: Contrast, word: WordViz, chat: Chat, ui: Ui, cta: CtaAction,
};
// Modes per type (spec, section 4) — a warning only: the plan is checked by visual_plan.py validate
const MODES: Record<string, SceneMode[]> = {
  hook: ["overlay", "split", "full"], quote: ["overlay", "split", "full"], slogan: ["full", "split"], stat: ["overlay", "split", "full"],
  list: ["panel", "split", "full"], contrast: ["overlay", "split", "full"], word: ["overlay", "split", "panel"],
  chat: ["split", "full", "window"], ui: ["split", "full", "window"], cta: ["overlay", "full"],
};
const warned = new Set<string>();
const warnOnce = (key: string, msg: string) => {
  if (warned.has(key)) return;
  warned.add(key);
  console.warn(msg);
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const W = 1080;
const H = 1920;
// Text safe zone: app UI at the top 0–220, bottom 1500–1920, right x > 960 (buttons) — nothing important goes there.
export const SAFE_ZONE = { left: 60, top: 220, right: 960, bottom: 1500 };

/** Scenes that go into the video: not skipped, not cover (the cover is ReelCover only), sorted by time. */
export const playableScenes = (scenes?: SceneSpec[] | null): SceneSpec[] =>
  (scenes ?? []).filter((s) => s.status !== "skipped" && s.type !== "cover" && s.dur > 0).sort((a, b) => a.start - b.start);

const LAYOUT: SceneMode[] = ["split", "panel", "window"];
/** “Scenes only” (no video): there is no speaker, so split/panel/window are drawn as full. */
export const effectiveMode = (s: SceneSpec, scenesOnly: boolean): SceneMode => (scenesOnly && LAYOUT.includes(s.mode) ? "full" : s.mode);

// ── speaker frame (Footage) ──
// x, y, w, h — the visible window on screen; k — scale of the 1080×1920 video inside the window; ox, oy — video offset in the window; r — corner radius
export type SpeakerRect = { x: number; y: number; w: number; h: number; k: number; ox: number; oy: number; r: number };
export const FULL_RECT: SpeakerRect = { x: 0, y: 0, w: W, h: H, k: 1, ox: 0, oy: 0, r: 0 };
const DEFAULT_FACE = [380, 700, 215, 295]; // typical medium shot: the face in the source (as in Presenter window)
const PANEL_W = 340; // speaker window width in panel: the video ×0.42 (454 px) cropped at the sides around the face

export const speakerTarget = (s: SceneSpec): SpeakerRect => {
  const face = s.face && s.face.length === 4 ? s.face : DEFAULT_FACE;
  if (s.mode === "split") {
    const k = 0.56;
    return { x: (W - W * k) / 2, y: 900, w: W * k, h: H * k, k, ox: 0, oy: 0, r: 0 };
  }
  if (s.mode === "panel") {
    const k = 0.42;
    const fcx = (face[0] + face[2] / 2) * k;
    const ox = Math.min(0, Math.max(PANEL_W - W * k, PANEL_W / 2 - fcx)); // face centered in the window, the video never pulls away from the edge
    const left = (s.side ?? "left") === "left";
    return { x: left ? 0 : W - PANEL_W, y: 700, w: PANEL_W, h: H * k, k, ox, oy: 0, r: 0 };
  }
  if (s.mode === "window") {
    const w = 360;
    const h = 480;
    const k = (h * 0.36) / face[3]; // the face is ~36 % of the window height, in the upper third
    const right = (s.side ?? "right") === "right";
    return { x: right ? W - 120 - w : 40, y: H - 420 - h - 20, w, h, k, ox: w / 2 - (face[0] + face[2] / 2) * k, oy: h * 0.3 - (face[1] + face[3] / 2) * k, r: 28 };
  }
  return FULL_RECT;
};

const lerp = (a: SpeakerRect, b: SpeakerRect, p: number): SpeakerRect => {
  const m = (x: number, y: number) => x + (y - x) * p;
  return { x: m(a.x, b.x), y: m(a.y, b.y), w: m(a.w, b.w), h: m(a.h, b.h), k: m(a.k, b.k), ox: m(a.ox, b.ox), oy: m(a.oy, b.oy), r: m(a.r, b.r) };
};

const ADJ = 0.2; // scenes closer than 0.2 s to each other are back to back: the layout does not return between them

/** Speaker frame at a video frame: layout entry/return follows the scene's transitions; back-to-back scenes do not return to the full frame. */
export const speakerRectAt = (scenes: SceneSpec[] | null | undefined, frame: number, fps: number, words: Word[], bt: ResolvedTone): SpeakerRect => {
  const list = playableScenes(scenes);
  const t = frame / fps;
  const isLayout = (s?: SceneSpec) => !!s && LAYOUT.includes(s.mode);
  for (let i = 0; i < list.length; i++) {
    const s = list[i];
    const prev = list[i - 1];
    const next = list[i + 1];
    const prevAdj = !!prev && s.start - (prev.start + prev.dur) <= ADJ;
    const nextAdj = !!next && next.start - (s.start + s.dur) <= ADJ;
    const end = nextAdj ? next.start : s.start + s.dur;
    if (t < s.start || t >= end) continue;
    const f = frame - Math.round(s.start * fps);
    if (s.mode === "overlay") return FULL_RECT;
    if (s.mode === "full") {
      // the speaker is covered by the field; under the field's transitions — the layout of an adjacent back-to-back scene, otherwise the full frame
      const nb = f < (s.dur * fps) / 2 ? (prevAdj ? prev : null) : nextAdj ? next : null;
      return nb && isLayout(nb) ? speakerTarget(nb) : FULL_RECT;
    }
    const tgt = speakerTarget(s);
    const tl = sceneTimeline(s, pickTone(s, bt), s.mode, fps, words);
    const from = prevAdj ? (isLayout(prev) ? speakerTarget(prev) : prev.mode === "full" ? tgt : FULL_RECT) : FULL_RECT;
    const to = nextAdj && (isLayout(next) || next.mode === "full") ? tgt : FULL_RECT;
    let r = tgt;
    if (f < tl.L) r = lerp(from, tgt, interpolate(f, [0, tl.L], [0, 1], { ...clamp, easing: easeOut }));
    if (to !== tgt && tl.Lout > 0 && f >= tl.n - tl.Lout) r = lerp(r, to, interpolate(f, [tl.n - tl.Lout, tl.n], [0, 1], { ...clamp, easing: easeIn }));
    return r;
  }
  return FULL_RECT;
};

/** Intervals without subtitles — the same rule as visual_plan.py hides_subtitles: every mode except overlay, and slogan always;
 *  hook and quote in overlay — yes by default (they repeat the speech); an explicit hide_subtitles: false keeps the subtitles. */
export const sceneHideIntervals = (scenes?: SceneSpec[] | null): [number, number][] =>
  playableScenes(scenes).filter((s) => s.mode !== "overlay" || s.type === "slogan" ||
    (s.hide_subtitles ?? (s.type === "hook" || s.type === "quote")))
    .map((s) => [s.start, s.start + s.dur] as [number, number]);

/** 0..1 — how much the frame is taken by a scene (the corner mark fades out over 6 frames so it does not overlap the scene). */
export const sceneActivity = (scenes: SceneSpec[] | null | undefined, frame: number, fps: number): number => {
  let a = 0;
  playableScenes(scenes).forEach((s) => {
    const f0 = s.start * fps;
    const f1 = (s.start + s.dur) * fps;
    a = Math.max(a, Math.min(interpolate(frame, [f0 - 6, f0], [0, 1], clamp), interpolate(frame, [f1, f1 + 6], [1, 0], clamp)));
  });
  return a;
};

// ── scene zone ──
const clampStage = (s: SceneSpec, b: number[]): Stage => {
  const x = Math.max(SAFE_ZONE.left, b[0]);
  const y = Math.max(SAFE_ZONE.top, b[1]);
  const w = Math.max(1, Math.min(b[0] + b[2], SAFE_ZONE.right) - x);
  const h = Math.max(1, Math.min(b[1] + b[3], SAFE_ZONE.bottom) - y);
  if (x !== b[0] || y !== b[1] || w !== b[2] || h !== b[3]) {
    warnOnce(`box-${s.id}`, `kit: scene ${s.id} box [${b.join(", ")}] goes outside the safe zone — clipped to [${x}, ${y}, ${w}, ${h}]`);
  }
  return { x, y, w, h };
};

export const sceneStage = (s: SceneSpec, mode: SceneMode): Stage => {
  if (s.box && s.box.length === 4 && mode !== "panel") return clampStage(s, s.box);
  switch (mode) {
    case "overlay":
      return { x: 60, y: 250, w: 900, h: 600 }; // headroom above the head; ideally a box from the plan (faces.json)
    case "split":
      return { x: 60, y: 220, w: 900, h: 660 }; // above the speaker (top of the video — y 900); the same zone as in visual_plan.py validate
    case "panel":
      return (s.side ?? "left") === "left" ? { x: PANEL_W + 40, y: 300, w: 960 - PANEL_W - 40, h: 1100 } : { x: 60, y: 300, w: W - PANEL_W - 40 - 60, h: 1100 };
    case "window":
      return { x: 60, y: 250, w: 900, h: 720 }; // above the speaker window (y 1000)
    default:
      return { x: 60, y: 250, w: 900, h: 1200 };
  }
};

const CARD_TYPES = ["quote", "stat", "list", "word", "cta"];
const PAD = { card: [28, 36], panel: [44, 40] };

const SceneFrame: React.FC<{ spec: SceneSpec; brand: Brand; look: Look; fonts: { heading: string; body: string }; bt: ResolvedTone;
  words: Word[]; scenesOnly: boolean }> = (p) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = p.spec;
  const mode = effectiveMode(s, p.scenesOnly);
  const tone = pickTone(s, p.bt);
  const tl = sceneTimeline(s, tone, mode, fps, p.words);
  const S = surfaces(p.brand, p.look);
  const Comp = BY_TYPE[s.type];
  if (!Comp) {
    warnOnce(`type-${s.id}`, `kit: scene ${s.id} — type “${s.type}” is not supported, skipping`);
    return null;
  }
  if (MODES[s.type] && !MODES[s.type].includes(s.mode)) warnOnce(`mode-${s.id}`, `kit: scene ${s.id} (${s.type}) — mode ${s.mode} is not one of ${MODES[s.type].join("/")}`);
  const stage = sceneStage(s, mode);
  const shell: SceneCtx["shell"] =
    mode === "panel" || (mode === "overlay" && CARD_TYPES.includes(s.type)) ? "card" : mode === "overlay" && (s.type === "hook" || s.type === "contrast") ? "plates" : "field";
  const surf = s.type === "slogan" ? S.mark : shell === "card" ? S.card : S.field;
  const pad = shell === "card" ? (mode === "panel" ? PAD.panel : PAD.card) : [0, 0];
  const radius = p.look.style === "v2" ? 0 : 18;
  const words = p.words.filter((w) => w.end > s.start - 0.3 && w.start < s.start + s.dur);
  const c: SceneCtx = {
    spec: s, frame, fps, tl, tone, bt: p.bt, brand: p.brand, look: p.look, fonts: p.fonts, surf, surfaces: S, mode, stage,
    inner: { w: Math.floor((stage.w - 2 * pad[1]) / enterGrow(tone)), h: stage.h - 2 * pad[0] }, shell, words, radius,
  };

  const pin = tl.L ? interpolate(frame, [0, tl.L], [0, 1], { ...clamp, easing: easeOut }) : 1;
  const pout = tl.Lout ? interpolate(frame, [tl.n - tl.Lout, tl.n], [0, 1], { ...clamp, easing: easeIn }) : 0;

  // a field over the whole frame (full) or above the speaker (slogan in split): enters by opacity or as a wipe, leaves the same way
  let field: React.ReactNode = null;
  const slogan = s.type === "slogan";
  if (mode === "full" || slogan) {
    const shutter = (k: SceneCtx["tl"]["tin"]) => k === "slide" || k === "whip" || (slogan && k === "fade");
    const x = (shutter(tl.tin) ? -(1 - pin) * W : 0) + (shutter(tl.tout) ? pout * W : 0);
    const op = (tl.tin === "fade" && !shutter(tl.tin) ? pin : 1) * (tl.tout === "fade" && !shutter(tl.tout) ? 1 - pout : 1);
    const h = mode === "full" ? H : 900;
    field = <div style={{ position: "absolute", left: 0, top: 0, width: W, height: h, backgroundColor: surf.bg, opacity: op, transform: `translateX(${x}px)` }} />;
  }

  // content shell
  let shellStyle: React.CSSProperties = { position: "absolute", left: stage.x, top: stage.y, display: "flex", flexDirection: "column", boxSizing: "border-box" };
  if (shell === "card") {
    const side = (s.side ?? "left") === "left" ? 1 : -1; // panel: the card slides in from the side opposite the speaker
    const slide = mode === "panel" ? (1 - pin) * (stage.w + 80) * side + pout * (stage.w + 80) * side : 0;
    // panel: the card is as wide as the zone, as tall as its content, centered on the zone (not an empty 1100 px sheet)
    shellStyle = {
      ...shellStyle, maxWidth: stage.w, maxHeight: stage.h, padding: `${pad[0]}px ${pad[1]}px`,
      backgroundColor: mode === "panel" ? surf.bg : alpha(surf.bg, 0.94), borderRadius: radius,
      transform: mode === "panel" ? `translateY(-50%) translateX(${slide}px)` : undefined,
      ...(mode === "panel" ? { width: stage.w, top: stage.y + stage.h / 2 } : {}),
    };
  } else {
    shellStyle = { ...shellStyle, width: stage.w, ...(mode === "overlay" ? { maxHeight: stage.h } : { height: stage.h, justifyContent: "center" }) };
  }
  // overlay: container transition (slide — an 80 px slide-in, whip — a jerk with blur); fade/cut — the content itself provides the motion
  if (mode === "overlay") {
    const tf: string[] = [];
    let op = 1;
    let blur = 0;
    if (tl.tin === "slide") {
      tf.push(`translateX(${(1 - pin) * 80}px)`);
      op *= pin;
    }
    if (tl.tout === "slide") {
      tf.push(`translateX(${-pout * 80}px)`);
      op *= 1 - pout;
    }
    if (tl.tin === "whip") {
      tf.push(`scale(${1 + 0.1 * (1 - pin)})`);
      blur += 12 * (1 - pin);
    }
    if (tl.tout === "whip") {
      tf.push(`scale(${1 + 0.08 * pout})`);
      blur += 12 * pout;
      op *= 1 - pout;
    }
    shellStyle = { ...shellStyle, opacity: op, transform: tf.length ? tf.join(" ") : shellStyle.transform, filter: blur > 0.3 ? `blur(${blur}px)` : undefined };
  }

  const flashIn = tl.tin === "flash" ? interpolate(frame, [0, 3], [1, 0], clamp) : 0;
  const flashOut = tl.tout === "flash" ? interpolate(frame, [tl.n - 3, tl.n], [0, 1], clamp) : 0;
  const flash = Math.max(flashIn, flashOut);
  return (
    <AbsoluteFill>
      {field}
      <div style={shellStyle}>
        <Comp c={c} />
      </div>
      {flash > 0 ? <AbsoluteFill style={{ backgroundColor: p.brand.colors.light, opacity: 0.85 * flash }} /> : null}
    </AbsoluteFill>
  );
};

/** Scene layer. words — speech words (captions.words): the “on a pause — cut” rule and slogan words landing on their spoken words.
 *  sceneTone — the video's scene tone (props.sceneTone): for scenes without their own tone. */
export const SceneLayer: React.FC<{ scenes?: SceneSpec[] | null; brand: Brand; look: Look; words?: Word[]; scenesOnly?: boolean;
  sceneTone?: string | null }> = (p) => {
  const { fps } = useVideoConfig();
  const fonts = useLookFonts(p.look);
  const bt = withRollTone(resolveBrandTone(p.brand), p.sceneTone);
  const list = playableScenes(p.scenes);
  return (
    <>
      {list.map((s) => (
        <Sequence key={s.id} from={Math.round(s.start * fps)} durationInFrames={Math.max(1, Math.round(s.dur * fps))} layout="none">
          <SceneFrame spec={s} brand={p.brand} look={p.look} fonts={fonts} bt={bt} words={p.words ?? []} scenesOnly={!!p.scenesOnly} />
        </Sequence>
      ))}
    </>
  );
};
