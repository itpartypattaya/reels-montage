// ReelKit — a universal video template for any brand: the rough cut (final.mp4) + inserts from the visual plan +
// subtitles and, optionally, a hook, a corner mark and an end card — all in the brand profile's colors and fonts.
// Data arrives as props (`visual_plan.py export … --props`); the video's code is not copied:
//   npx remotion render ReelKit out/<brand>-<slug>-<date>.mp4 --props=<edit>/reelkit-props.json
// Custom graphics (plates on words, etc.) still live in your own Reel<id>.tsx; the kit plugs in there too
// (BrollLayer/MemeLayer/KitSubtitles/SceneLayer). Older Reel*.tsx files do not use the kit.
// Designed scenes (props.scenes, references/scenes.md): a layer above B-roll and the hook, below memes and subtitles; in split/
// panel/window the main video shrinks (speaker frame — kit/scenes speakerRectAt), full covers the frame with a field.
// “Scenes only” format (a promo with no footage): video "" + captions {duration, segments: [], words: []} — brand-color
// background, length — captions.duration. The cover is the ReelCover composition (still) at the bottom of the file.
// “Framed” format (props.framed ← reel.json format: framed, references/techniques.md): a horizontal rough cut in a rounded
// window on the style's field, an optional caps label above it, the camera clamped to the window, scenes, B-roll and
// subtitles inside it — drawn here, no per-video composition. A per-video composition reuses the pieces exported below
// (FramedFootage, FramedLabel, EndCard with its logo sting, Corner, cameraAt/fitCamera, framedGeometry).
import React from "react";
import { AbsoluteFill, CalculateMetadataFunction, Easing, Img, OffthreadVideo, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Brand, Look, alpha, fullLogoOnDark, logoOnDark, styleLook, useLookFonts } from "./kit/brand";
import { neutralBrand } from "./kit/defaultBrand";
import { BrollLayer, Insert, MemeLayer } from "./kit/Inserts";
import { Captions, KitSubtitles, SubtitleMode } from "./kit/Subtitles";
import { breakLines, fitSize, useFontsReady } from "./kit/Phrase";
import { COVER_ZONE, COVER_ZONE_LOW, Cover, CoverText, ResolvedTone, SceneFrameBox, SceneLayer, SceneSpec, contrast, resolveBrandTone, sceneActivity,
  sceneHideIntervals, speakerRectAt, withRollTone } from "./kit/scenes";

export const KIT_FPS = 30;

export type ReelKitProps = {
  video: string; // path inside public/
  captions: Captions;
  // subtitles in another language (subs.py → captions-<lang>.json); the speech words in captions still time the scenes
  subtitleCaptions?: Captions | null;
  brand: Brand;
  // video style (reel.json → style, otherwise brand.style_default): marker / v2 / brand; anything else — marker with a warning
  style?: string | null;
  inserts: Insert[];
  subtitles: SubtitleMode;
  subtitlesShade?: number; // “typewriter”: darkening of the lower part 0..1 (reel.json → subtitles_shade; default 0.35; visual_plan.py shade measures it)
  subtitlesTop?: number; // top of the subtitles (y); from the face measurement — visual_plan.py export --props: chin + 30 px, ≤ 1390
  hideSubtitles?: [number, number][];
  drift?: boolean; // slow scale drift per segment (when there is no camera)
  // virtual camera (references/camera.md): shots in output seconds, from edit/<id>/camera.json via visual_plan.py export;
  // { z, cx, cy } — the scale and the source point that ends up in the frame center; drift — a slow push-in over the shot
  // (+0.02–0.06); whip — a 7-frame move from the previous shot with a light motion blur instead of a cut
  camera?: Shot[] | null;
  hook?: { text: string; until: number } | null;
  corner?: boolean; // brand mark in the corner
  endCard?: { line1?: string; line2?: string; seconds?: number } | null; // no line1: a logo sting (logo with the tagline)
  scenes?: SceneSpec[] | null; // designed scenes (visual_plan.py export --props → scenes); absent — the video renders as before
  sceneTone?: string | null; // the video's scene tone (reel.json → tone, otherwise the brand tone): for scenes without their own tone
  cover?: SceneSpec | null; // cover scene (not part of the video — the ReelCover composition takes it with the same props)
  framed?: Framed | null; // the “framed” format (visual_plan.py export from reel.json format: framed); absent — the full frame
};

// The “framed” format: window — x, y, w, h on the 1080×1920 screen (reel.json → window, default 25, 340, 1030, 1240);
// label — the caps label above the window (reel.json → label); source — w, h of the rough cut (the video is a cover in the
// window, centered, as faces.py maps faces); radius — the window's corners; field — the color around the window (export:
// brand.looks[style].field, else primary)
export type Framed = { window: number[]; label?: string | null; source?: number[] | null; radius?: number | null; field?: string | null };
type Box = { x: number; y: number; w: number; h: number };
export type FramedGeo = { win: Box; r: number; video: Box; cx: number; cy: number; area: Box; label: string | null };
export const FRAMED_WINDOW = [25, 340, 1030, 1240];
const FRAMED_PAD = 35; // text keeps this far from the window's sides (reels_common.FRAMED_PAD)
const FRAMED_LABEL_UP = 48; // the label's top above the window (reels_common.FRAMED_LABEL_UP)
/** The framed layout's geometry, the same rules as reels_common.py (framed_view, framed_area): the video's cover in the
 *  window; the text area inside the window (x 60–960, y ≤ 1500), with no label the field above the window joins it. */
export const framedGeometry = (f: Framed): FramedGeo => {
  const [x, y, w, h] = f.window?.length === 4 ? f.window : FRAMED_WINDOW;
  const [sw, sh] = f.source?.length === 2 && f.source[0] > 0 && f.source[1] > 0 ? f.source : [w, h];
  const k = Math.max(w / sw, h / sh);
  const label = f.label?.trim() || null;
  const ax = Math.max(60, x + FRAMED_PAD);
  const ay = label ? Math.max(220, y + 20) : 220;
  return {
    win: { x, y, w, h }, r: f.radius ?? 50, video: { x: x + (w - sw * k) / 2, y: y + (h - sh * k) / 2, w: sw * k, h: sh * k },
    cx: x + w / 2, cy: y + h / 2, label,
    area: { x: ax, y: ay, w: Math.min(960, x + w - FRAMED_PAD) - ax, h: Math.min(1500, y + h - 20) - ay },
  };
};
const sceneBox = (g: FramedGeo): SceneFrameBox => ({ area: g.area, win: g.win, r: g.r });

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const easeOut = Easing.out(Easing.cubic);

export type Shot = { t: number; z: number; cx: number; cy: number; drift?: number; whip?: boolean };
type Cam = { z: number; cx: number; cy: number; blur: number };
const WHIP = 7; // frames
const WHIP_BLUR = 6; // px on screen at the whip's peak (camera.md), whatever the zoom
export const STING_IN = 8; // frames: the end card's field fades in over the last phrase (subtitles and their darkening stay)
// the camera window never shows past the video: in the full frame cx within [540/z, 1080 − 540/z], cy within
// [960/z, 1920 − 960/z]; in the framed window (view) the window's half size over z inside the video's cover — the same rule
// as reels_common.cam_fit, so validate and faces.py check the faces where this draws them (T7: a full-frame clamp moved a
// framed shot at cx 820 to 540)
export type CamView = { win: Box; video: Box } | null;
const FULL: Box = { x: 0, y: 0, w: 1080, h: 1920 };
export const fitCamera = (z: number, cx: number, cy: number, view?: CamView): Cam => {
  const zz = Math.max(1, z);
  const win = view?.win ?? FULL;
  const v = view?.video ?? FULL;
  const hx = win.w / 2 / zz;
  const hy = win.h / 2 / zz;
  return { z: zz, cx: Math.min(Math.max(cx, v.x + hx), v.x + v.w - hx), cy: Math.min(Math.max(cy, v.y + hy), v.y + v.h - hy), blur: 0 };
};
const shotAt = (s: Shot, next: Shot | undefined, t: number, end: number, view?: CamView): Cam => {
  const k = interpolate(t, [s.t, Math.max(s.t + 0.01, next ? next.t : end)], [0, 1], clamp);
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

export const reelKitMetadata: CalculateMetadataFunction<ReelKitProps> = ({ props }) => ({
  durationInFrames: Math.max(1, Math.round(props.captions.duration * KIT_FPS) +
    (props.endCard ? Math.round((props.endCard.seconds ?? 2.6) * KIT_FPS) : 0)),
});

const Footage: React.FC<{ p: ReelKitProps; bt: ResolvedTone }> = ({ p, bt }) => {
  const frame = useCurrentFrame();
  const t = frame / KIT_FPS;
  const segs = p.captions.segments;
  const seg = segs.find((g) => t >= g.out_start && t < g.out_start + g.out_dur) ?? segs[segs.length - 1];
  let z = 1;
  if (p.drift && seg) {
    const k = interpolate(t, [seg.out_start, seg.out_start + seg.out_dur], [0, 1], clamp);
    z = seg.i % 2 === 0 ? 1 + 0.05 * k : 1.05 - 0.05 * k;
  }
  if (!p.video) return null;
  if (p.framed) return <FramedFootage p={p} z={z} />;
  const cam = p.camera?.length ? cameraAt(p.camera, t, p.captions.duration, KIT_FPS) : null;
  // speaker frame from the scenes (split/panel/window); without scenes — the whole frame. The markup is the same on every frame: the video
  // is not remounted and the audio is not interrupted; under a full field the video keeps playing too (voice)
  const r = speakerRectAt(p.scenes, frame, KIT_FPS, p.captions.words, bt);
  // the blur sits on the scaled layer, so CSS multiplies it by the zoom: divided back, the screen gets sin(πp)·6 px at
  // any zoom (T4: 7.8 px at ×1.3 left the faces unreadable at the whip's peak)
  const blur = cam ? Math.min(WHIP_BLUR, cam.blur) / cam.z : 0;
  return (
    <div style={{ position: "absolute", left: r.x, top: r.y, width: r.w, height: r.h, overflow: "hidden", borderRadius: r.r }}>
      <div style={{ position: "absolute", left: r.ox, top: r.oy, width: 1080 * r.k, height: 1920 * r.k,
        ...(cam ? { transform: `translate(${(540 - cam.cx * cam.z) * r.k}px, ${(960 - cam.cy * cam.z) * r.k}px) scale(${cam.z})`,
          transformOrigin: "0 0", filter: blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : undefined } : { transform: `scale(${z})` }) }}>
        <OffthreadVideo src={staticFile(p.video)} style={{ width: "100%", height: "100%", maxWidth: "none", maxHeight: "none" }} />
      </div>
    </div>
  );
};

/** “Framed”: the rough cut as a cover in the rounded window, the virtual camera in the screen coordinates faces.py uses
 *  (x' = (x − cx)·z + the window's center), clamped to the window. z — the template's drift when there is no camera. */
export const FramedFootage: React.FC<{ p: ReelKitProps; z?: number }> = ({ p, z = 1 }) => {
  const frame = useCurrentFrame();
  if (!p.framed || !p.video) return null;
  const t = frame / KIT_FPS;
  const g = framedGeometry(p.framed);
  const view = { win: g.win, video: g.video };
  const cam = p.camera?.length ? cameraAt(p.camera, t, p.captions.duration, KIT_FPS, view) : fitCamera(z, g.cx, g.cy, view);
  return <FramedWindow g={g} cam={cam} video={p.video} />;
};

/** The rounded window with the rough cut in it under camera `cam`; trimBefore — a still (the cover's frame). */
const FramedWindow: React.FC<{ g: FramedGeo; cam: Cam; video: string; trimBefore?: number }> = ({ g, cam, video, trimBefore }) => {
  const blur = Math.min(WHIP_BLUR, cam.blur) / cam.z;
  return (
    <div style={{ position: "absolute", left: g.win.x, top: g.win.y, width: g.win.w, height: g.win.h, overflow: "hidden", borderRadius: g.r }}>
      <div style={{ position: "absolute", left: -g.win.x, top: -g.win.y, width: 1080, height: 1920, transformOrigin: "0 0",
        transform: `translate(${g.cx - cam.cx * cam.z}px, ${g.cy - cam.cy * cam.z}px) scale(${cam.z})`,
        filter: blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : undefined }}>
        {/* maxWidth: none — a project's Tailwind preflight (img, video { max-width: 100% }) shrinks a video wider than its
            parent, and OffthreadVideo then letterboxes the frame into a narrow band (references/pitfalls.md) */}
        <OffthreadVideo src={staticFile(video)} trimBefore={trimBefore} muted={trimBefore !== undefined} style={{ position: "absolute",
          left: g.video.x, top: g.video.y, width: g.video.w, height: g.video.h, maxWidth: "none", maxHeight: "none" }} />
      </div>
    </div>
  );
};

/** The field around the framed window: export writes framed.field (the style's field, else primary). */
const framedField = (p: Pick<ReelKitProps, "framed" | "brand" | "style">) =>
  p.framed?.field ?? styleLook(p.brand, p.style).field ?? p.brand.colors.primary;
/** The corner mark's size in the framed label's row above the window (< 56 — no room, no mark). */
const framedCornerSize = (g: FramedGeo) => Math.min(112, g.win.y - 12 - 224);
/** The corner mark: over the video the light variant; on the framed field the one that reads on it (a light field —
 *  the dark mark, as Cover does on a light field: a white mark vanished on a cream field). */
const cornerLogo = (p: Pick<ReelKitProps, "framed" | "brand" | "style">) => {
  if (!p.framed) return logoOnDark(p.brand);
  const field = framedField(p);
  const light = contrast(field, "#000000") > contrast(field, "#FFFFFF");
  return light ? p.brand.logos.mark_on_light ?? p.brand.logos.on_light ?? logoOnDark(p.brand) : logoOnDark(p.brand);
};

/** “Framed”: the caps label above the window — the brand's body font, 600, 28 px, +0.2 em, in the color that reads on the
 *  field (primary on a light field, text_on_primary on a dark one). With the corner mark in the same row the label stops
 *  16 px before it (a 31-character label ran under the mark). still — the cover: shown at once, no fade-in. */
export const FramedLabel: React.FC<{ p: Pick<ReelKitProps, "framed" | "brand" | "style" | "corner">; font: string; still?: boolean }> = (
  { p, font, still },
) => {
  const frame = useCurrentFrame();
  const ready = useFontsReady([font]); // before the early return
  if (!p.framed) return null;
  const g = framedGeometry(p.framed);
  if (!g.label) return null;
  const c = p.brand.colors;
  const field = framedField(p);
  const ink = contrast(c.primary, field) >= 4.5 ? c.primary : c.text_on_primary;
  const cs = framedCornerSize(g);
  const maxWidth = p.corner && cornerLogo(p) && cs >= 56 ? Math.min(g.area.w, 1080 - 140 - cs - 16 - g.area.x) : g.area.w;
  const size = fitSize({ text: g.label, size: 28, font, weight: 600, maxWidth, tracking: 0.2, upper: true, ready });
  const a = still ? 1 : interpolate(frame, [2, 16], [0, 1], { ...clamp, easing: easeOut });
  return (
    <div style={{ position: "absolute", left: g.area.x, top: Math.max(220, g.win.y - FRAMED_LABEL_UP), fontFamily: font, fontWeight: 600,
      fontSize: size, lineHeight: 1, letterSpacing: "0.2em", textTransform: "uppercase", whiteSpace: "nowrap", color: ink, opacity: a,
      transform: `translateY(${(1 - a) * 12}px)` }}>
      {g.label}
    </div>
  );
};

const Mark: React.FC<{ look: Look; font: string; size: number; p: number; children: React.ReactNode }> = ({ look, font, size, p, children }) => (
  <div style={{ display: "inline-block", backgroundColor: look.mark, color: look.onMark, fontFamily: font,
    fontWeight: 800, fontSize: size, lineHeight: 1.08, padding: "0.05em 0.2em 0.08em", clipPath: `inset(0 ${(1 - p) * 100}% 0 0)` }}>
    {children}
  </div>
);

const Hook: React.FC<{ p: ReelKitProps; look: Look; font: string }> = ({ p, look, font }) => {
  const frame = useCurrentFrame();
  const ready = useFontsReady([font]); // before the early return: React hooks always run in the same order
  if (!p.hook || frame > p.hook.until * KIT_FPS) return null;
  const end = p.hook.until * KIT_FPS;
  const out = interpolate(frame, [end - 8, end], [1, 0], clamp);
  const lines = breakLines(p.hook.text, 14); // line breaks by meaning: prepositions and numbers do not dangle (typography.md)
  // font size 100, but every line must fit in x 60–960 (with plate padding of 0.2 em): a long glued token reduces the size;
  // “framed”: the top of the window's text area (with no label, the field above the window), its width
  const g = p.framed ? framedGeometry(p.framed) : null;
  const maxW = g ? g.area.w : 900;
  const size = Math.min(100, ...lines.map((l) => fitSize({ text: l, size: 100, font, weight: 800, maxWidth: maxW, padEm: 0.2, ready })));
  return (
    <div style={{ position: "absolute", left: g ? g.area.x : 60, top: g ? g.area.y + 10 : 300, opacity: out }}>
      {lines.map((l, k) => (
        <div key={k}>
          <Mark look={look} font={font} size={size} p={interpolate(frame, [3 + 5 * k, 12 + 5 * k], [0, 1], { ...clamp, easing: easeOut })}>{l}</Mark>
        </div>
      ))}
    </div>
  );
};

export const Corner: React.FC<{ p: ReelKitProps }> = ({ p }) => {
  const frame = useCurrentFrame();
  const src = cornerLogo(p);
  // stays while the end card's field fades in over it (STING_IN), as the subtitles do
  if (!p.corner || !src || frame >= p.captions.duration * KIT_FPS + (p.endCard ? STING_IN : 0)) return null;
  const a = interpolate(frame, [4, 16], [0, 1], { ...clamp, easing: easeOut }) * (1 - sceneActivity(p.scenes, frame, KIT_FPS)); // fades out during a scene
  if (a <= 0) return null;
  // “framed”: on the field above the window, in the label's row (no room there — no mark)
  const g = p.framed ? framedGeometry(p.framed) : null;
  const size = g ? framedCornerSize(g) : 112;
  if (size < 56) return null;
  return <Img src={staticFile(src)} style={{ position: "absolute", right: 140, top: g ? g.win.y - 12 - size : 236, width: size, height: size,
    objectFit: "contain", opacity: 0.9 * a }} />;
};

export const EndCard: React.FC<{ p: ReelKitProps; look: Look; fonts: { heading: string; body: string } }> = ({ p, look, fonts }) => {
  const frame = useCurrentFrame();
  const ready = useFontsReady([fonts.heading, fonts.body]); // before the early return
  const v = Math.round(p.captions.duration * KIT_FPS);
  if (!p.endCard || frame < v) return null;
  const k = frame - v;
  const bg = interpolate(k, [0, STING_IN], [0, 1], clamp);
  const a = interpolate(k, [3, 15], [0, 1], { ...clamp, easing: easeOut });
  // a logo sting (no line1): the logo centered, under it the brand line (line2, visual_plan.py export --sting takes
  // brand.tagline); with no line2 the logo variant that carries the tagline. With a CTA (SKILL.md: logo, tagline, CTA):
  // the logo, the brand line (brand.tagline) small under it, then the CTA lines; a profile without a tagline takes the
  // logo variant that carries it, if there is one. The CTA card once showed the logo without the brand line.
  const sting = !p.endCard.line1;
  const own = sting && !p.endCard.line2;
  const lockup = p.brand.logos.on_dark_tagline;
  const logo = own || (!sting && !p.brand.tagline) ? lockup ?? fullLogoOnDark(p.brand) : fullLogoOnDark(p.brand);
  const tag = !sting && p.brand.tagline && !(lockup && logo === lockup) ? p.brand.tagline : null;
  const box = own ? { top: 610, left: 140, width: 800, height: 700 } : sting ? { top: 640, left: 190, width: 700, height: 360 }
    : { top: tag ? 470 : 520, left: 240, width: 600, height: 300 };
  // every text of the card stays within x 120–960 on the frame's axis: right of x 960 is the app's buttons column (a
  // 960 px CTA plate ran to x 1016 under it); the plate adds 0.2 em on each side.
  // references/cta.md: the main line 52–60 px (here up to 64, the card is the whole frame), the clarifier 34–38 px in a muted color
  const TEXT_W = 840;
  const s1 = p.endCard.line1 ? fitSize({ text: p.endCard.line1, size: 64, font: fonts.heading, weight: 800, maxWidth: TEXT_W, padEm: 0.2, ready }) : 64;
  const s2 = p.endCard.line2 ? fitSize({ text: p.endCard.line2, size: sting ? 52 : 38, font: fonts.body, weight: sting ? 600 : 500, maxWidth: TEXT_W, ready }) : 38;
  const st = tag ? fitSize({ text: tag, size: 34, font: fonts.body, weight: 500, maxWidth: TEXT_W, ready }) : 34;
  const c = p.brand.colors;
  return (
    <AbsoluteFill style={{ backgroundColor: c.primary, opacity: bg }}>
      {logo ? <Img src={staticFile(logo)} style={{ position: "absolute", ...box, objectFit: "contain", opacity: a }} />
        : <div style={{ position: "absolute", top: tag ? 560 : 600, width: "100%", textAlign: "center", fontFamily: fonts.heading, fontWeight: 800, fontSize: 96, color: c.text_on_primary, opacity: a }}>{p.brand.name}</div>}
      {tag ? (
        <div style={{ position: "absolute", top: 796, width: "100%", textAlign: "center", fontFamily: fonts.body, fontWeight: 500, fontSize: st,
          color: c.text_on_primary, opacity: 0.72 * a }}>{tag}</div>
      ) : null}
      {p.endCard.line1 ? (
        <div style={{ position: "absolute", top: 900, width: "100%", textAlign: "center" }}>
          <Mark look={look} font={fonts.heading} size={s1} p={interpolate(k, [10, 19], [0, 1], { ...clamp, easing: easeOut })}>{p.endCard.line1}</Mark>
        </div>
      ) : null}
      {p.endCard.line2 ? (
        <div style={{ position: "absolute", top: sting ? 1080 : 1000, width: "100%", textAlign: "center", fontFamily: fonts.body, fontWeight: sting ? 600 : 500, fontSize: s2,
          color: c.text_on_primary, opacity: interpolate(k, [16, 26], [0, sting ? 1 : 0.72], clamp) }}>{p.endCard.line2}</div>
      ) : null}
    </AbsoluteFill>
  );
};

export const ReelKit: React.FC<ReelKitProps> = (p) => {
  const look = styleLook(p.brand, p.style); // marker color and fonts of the chosen style (kit/brand.ts)
  const fonts = useLookFonts(look);
  const bt = withRollTone(resolveBrandTone(p.brand), p.sceneTone);
  // subtitles are hidden on split/panel/window/full and slogan scenes (the scene text replaces them) and on hide_subtitles —
  // this duplicates the export's hideSubtitles, which does no harm
  const hide = [...(p.hideSubtitles ?? []), ...sceneHideIntervals(p.scenes)];
  // the last phrase and the darkening stay under the end card while its field fades in, then the card covers them
  // (T4: they vanished when the speech ended, on the second frame of the logo sting's 8-frame fade: a visible step)
  const tail = p.endCard ? STING_IN / KIT_FPS : 0;
  // “framed”: the window, the label above it, everything else inside the window's text area
  const g = p.framed && p.video ? framedGeometry(p.framed) : null;
  const subArea = g ? { area: g.area, clip: { ...g.win, r: g.r } } : {};
  // behind the speaker shrunk by a split/panel/window scene (and around the framed window): the style's field
  // (brand.looks[style].field), the same surface the scene's text is colored for; without it, primary
  return (
    <AbsoluteFill style={{ backgroundColor: (g ? p.framed?.field : null) ?? look.field ?? p.brand.colors.primary }}>
      <Footage p={p} bt={bt} />
      {g ? <FramedLabel p={p} font={fonts.body} /> : null}
      <BrollLayer inserts={p.inserts} brand={p.brand} framed={g ? sceneBox(g) : null} />
      <KitSubtitles captions={p.subtitleCaptions ?? p.captions} brand={p.brand} font={fonts.body} mode={p.subtitles} hide={hide}
        top={p.subtitlesTop ?? 1290} look={look} shade={p.subtitlesShade ?? 0.35} part="shade" tail={tail} {...subArea} />
      <Hook p={p} look={look} font={fonts.heading} />
      <Corner p={p} />
      <SceneLayer scenes={p.scenes} brand={p.brand} look={look} words={p.captions.words} scenesOnly={!p.video} sceneTone={p.sceneTone}
        framed={g ? sceneBox(g) : null} />
      <MemeLayer inserts={p.inserts} brand={p.brand} />
      <KitSubtitles captions={p.subtitleCaptions ?? p.captions} brand={p.brand} font={fonts.body} mode={p.subtitles} hide={hide}
        top={p.subtitlesTop ?? 1290} look={look} shade={p.subtitlesShade ?? 0.35} part="text" tail={tail} {...subArea} />
      <EndCard p={p} look={look} fonts={fonts} />
    </AbsoluteFill>
  );
};

export const reelKitDefaults: ReelKitProps = {
  video: "",
  captions: { duration: 3, segments: [], words: [] },
  brand: neutralBrand, // the kit's neutral profile: the project builds without src/brands/<slug>.json
  style: null,
  inserts: [],
  subtitles: "accent",
  drift: true,
  hook: { text: "ReelKit template", until: 2.5 },
  corner: true,
  endCard: null,
};

// ── Cover: a video frame + Cover on top (still) ──
//   npx remotion still ReelCover <edit>/cover.png --props=<edit>/reelkit-props.json
// Takes the same props as ReelKit (extra fields do no harm): text — text, otherwise cover.text (props.cover from export);
// frame — frameAt, otherwise cover.frameAt, otherwise 1.0 s.
// Root.tsx: <Composition id="ReelCover" component={ReelCover} durationInFrames={1} fps={KIT_FPS} width={1080} height={1920}
//   defaultProps={reelCoverDefaults} />
export type ReelCoverProps = {
  video: string; // path inside public/; "" — background in the style's field (brand.looks[style].field), else the primary color
  frameAt?: number | null; // second of the video under the cover (poster.py pick: middle of the hook/cover scene's rest, otherwise 1.0)
  brand: Brand;
  style?: string | null;
  text?: CoverText | null; // lines — the hook, large; label — an all-caps label above it
  cover?: SceneSpec | null; // cover scene from export (text, frameAt) — if text is not set
  logo?: boolean; // brand mark above the hook
  dim?: number; // 0–1: even dimming of the frame with the primary color (not a gradient) when the background is busy
  box?: number[] | null; // x, y, w, h of the text zone (clear of the face); absent — cover.box, otherwise the bottom of the 1:1 zone (with video) or its center
  framed?: Framed | null; // the “framed” format (ReelKit's props): the frame in the window, the label above it, the field around
};

/** A zone kept inside the framed text area; a zone that falls outside it — the lower part of the area. */
const zoneIn = (z: { x: number; y: number; w: number; h: number }, a: Box) => {
  const x = Math.max(z.x, a.x);
  const y = Math.max(z.y, a.y);
  const w = Math.min(z.x + z.w, a.x + a.w) - x;
  const h = Math.min(z.y + z.h, a.y + a.h) - y;
  return w >= 300 && h >= 160 ? { x, y, w, h } : { x: a.x, y: Math.max(a.y, a.y + a.h - 480), w: a.w, h: Math.min(480, a.h) };
};

export const ReelCover: React.FC<ReelCoverProps> = (p) => {
  const look = styleLook(p.brand, p.style);
  const fonts = useLookFonts(look);
  const text: CoverText = p.text ?? (p.cover?.text ? { lines: p.cover.text.lines, accent: p.cover.text.accent, label: p.cover.text.label } : { lines: [] });
  const at = p.frameAt ?? p.cover?.frameAt ?? 1;
  const b = p.box ?? p.cover?.box ?? null;
  const base = b && b.length === 4 ? { x: b[0], y: b[1], w: b[2], h: b[3] } : p.video ? COVER_ZONE_LOW : COVER_ZONE;
  // “framed”: the frame in the window on the field, the label above it, the text inside the window's text area, the same
  // layout as the video's frames (a full-frame cover baked into frame 0 jumped to another layout)
  const g = p.framed && p.video ? framedGeometry(p.framed) : null;
  const zone = g ? zoneIn(base, g.area) : base;
  const dim = p.dim ? alpha(p.brand.colors.primary, Math.min(1, Math.max(0, p.dim))) : null;
  // without video (a "scenes only" promo): the style's field, as in ReelKit, and the text drawn as on a full scene (no plates);
  // T6: the cover came out on the primary color while the video's scenes sat on the style's light field
  return (
    <AbsoluteFill style={{ backgroundColor: g ? framedField(p) : look.field ?? p.brand.colors.primary }}>
      {g ? (
        <FramedWindow g={g} cam={fitCamera(1, g.cx, g.cy, { win: g.win, video: g.video })} video={p.video}
          trimBefore={Math.max(0, Math.round(at * KIT_FPS))} />
      ) : p.video ? (
        <OffthreadVideo src={staticFile(p.video)} trimBefore={Math.max(0, Math.round(at * KIT_FPS))} muted style={{ width: 1080, height: 1920 }} />
      ) : null}
      {dim && g ? (
        <div style={{ position: "absolute", left: g.win.x, top: g.win.y, width: g.win.w, height: g.win.h, borderRadius: g.r, backgroundColor: dim }} />
      ) : dim ? <AbsoluteFill style={{ backgroundColor: dim }} /> : null}
      {g ? <FramedLabel p={{ framed: p.framed, brand: p.brand, style: p.style, corner: false }} font={fonts.body} still /> : null}
      <Cover brand={p.brand} look={look} text={text} logo={p.logo} zone={zone} onField={!p.video} />
    </AbsoluteFill>
  );
};

// text and frameAt are null: --props are merged over defaultProps, so a non-empty default text would override props.cover
// from export (“Cover template” on the real cover), and frameAt: 1 would override cover.frameAt. To try it in Studio, pass your own text in the props.
export const reelCoverDefaults: ReelCoverProps = {
  video: "",
  frameAt: null,
  brand: neutralBrand,
  style: null,
  text: null,
  logo: false,
  dim: 0,
};
