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
import React from "react";
import { AbsoluteFill, CalculateMetadataFunction, Easing, Img, OffthreadVideo, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Brand, Look, alpha, fullLogoOnDark, logoOnDark, styleLook, useLookFonts } from "./kit/brand";
import { neutralBrand } from "./kit/defaultBrand";
import { BrollLayer, Insert, MemeLayer } from "./kit/Inserts";
import { Captions, KitSubtitles, SubtitleMode } from "./kit/Subtitles";
import { breakLines, fitSize, useFontsReady } from "./kit/Phrase";
import { COVER_ZONE, COVER_ZONE_LOW, Cover, CoverText, ResolvedTone, SceneLayer, SceneSpec, resolveBrandTone, sceneActivity, sceneHideIntervals, speakerRectAt,
  withRollTone } from "./kit/scenes";

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
  subtitlesShade?: number; // “typewriter”: darkening of the lower part 0..1 (reel.json → subtitles_shade)
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
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const easeOut = Easing.out(Easing.cubic);

export type Shot = { t: number; z: number; cx: number; cy: number; drift?: number; whip?: boolean };
type Cam = { z: number; cx: number; cy: number; blur: number };
const WHIP = 7; // frames
// the camera window never leaves the frame: cx within [540/z, 1080 − 540/z], cy within [960/z, 1920 − 960/z]
const fit = (z: number, cx: number, cy: number): Cam => {
  const zz = Math.max(1, z);
  return { z: zz, cx: Math.min(Math.max(cx, 540 / zz), 1080 - 540 / zz), cy: Math.min(Math.max(cy, 960 / zz), 1920 - 960 / zz), blur: 0 };
};
const shotAt = (s: Shot, next: Shot | undefined, t: number, end: number): Cam => {
  const k = interpolate(t, [s.t, Math.max(s.t + 0.01, next ? next.t : end)], [0, 1], clamp);
  return fit(s.z * (1 + (s.drift ?? 0) * k), s.cx, s.cy);
};
export const cameraAt = (shots: Shot[], t: number, end: number, fps: number): Cam => {
  let i = -1;
  shots.forEach((s, k) => { if (s.t <= t + 1e-6) i = k; });
  if (i < 0) return fit(1, 540, 960);
  const cam = shotAt(shots[i], shots[i + 1], t, end);
  const p = (t - shots[i].t) * fps / WHIP;
  if (!shots[i].whip || i === 0 || p >= 1) return cam;
  const prev = shotAt(shots[i - 1], shots[i], shots[i].t, end); // where the previous shot ended (with its drift)
  const e = easeOut(Math.max(0, p));
  return { z: prev.z + (cam.z - prev.z) * e, cx: prev.cx + (cam.cx - prev.cx) * e, cy: prev.cy + (cam.cy - prev.cy) * e,
    blur: Math.sin(Math.PI * Math.max(0, p)) * 6 };
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
  const cam = p.camera?.length ? cameraAt(p.camera, t, p.captions.duration, KIT_FPS) : null;
  // speaker frame from the scenes (split/panel/window); without scenes — the whole frame. The markup is the same on every frame: the video
  // is not remounted and the audio is not interrupted; under a full field the video keeps playing too (voice)
  const r = speakerRectAt(p.scenes, frame, KIT_FPS, p.captions.words, bt);
  return (
    <div style={{ position: "absolute", left: r.x, top: r.y, width: r.w, height: r.h, overflow: "hidden", borderRadius: r.r }}>
      <div style={{ position: "absolute", left: r.ox, top: r.oy, width: 1080 * r.k, height: 1920 * r.k,
        ...(cam ? { transform: `translate(${(540 - cam.cx * cam.z) * r.k}px, ${(960 - cam.cy * cam.z) * r.k}px) scale(${cam.z})`,
          transformOrigin: "0 0", filter: cam.blur > 0.05 ? `blur(${cam.blur}px)` : undefined } : { transform: `scale(${z})` }) }}>
        <OffthreadVideo src={staticFile(p.video)} style={{ width: "100%", height: "100%" }} />
      </div>
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
  // font size 100, but every line must fit in x 60–960 (with plate padding of 0.2 em): a long glued token reduces the size
  const size = Math.min(100, ...lines.map((l) => fitSize({ text: l, size: 100, font, weight: 800, maxWidth: 900, padEm: 0.2, ready })));
  return (
    <div style={{ position: "absolute", left: 60, top: 300, opacity: out }}>
      {lines.map((l, k) => (
        <div key={k}>
          <Mark look={look} font={font} size={size} p={interpolate(frame, [3 + 5 * k, 12 + 5 * k], [0, 1], { ...clamp, easing: easeOut })}>{l}</Mark>
        </div>
      ))}
    </div>
  );
};

const Corner: React.FC<{ p: ReelKitProps }> = ({ p }) => {
  const frame = useCurrentFrame();
  const src = logoOnDark(p.brand);
  if (!p.corner || !src || frame >= p.captions.duration * KIT_FPS) return null;
  const a = interpolate(frame, [4, 16], [0, 1], { ...clamp, easing: easeOut }) * (1 - sceneActivity(p.scenes, frame, KIT_FPS)); // fades out during a scene
  if (a <= 0) return null;
  return <Img src={staticFile(src)} style={{ position: "absolute", right: 140, top: 236, width: 112, height: 112, objectFit: "contain", opacity: 0.9 * a }} />;
};

const EndCard: React.FC<{ p: ReelKitProps; look: Look; fonts: { heading: string; body: string } }> = ({ p, look, fonts }) => {
  const frame = useCurrentFrame();
  const ready = useFontsReady([fonts.heading, fonts.body]); // before the early return
  const v = Math.round(p.captions.duration * KIT_FPS);
  if (!p.endCard || frame < v) return null;
  const k = frame - v;
  const bg = interpolate(k, [0, 8], [0, 1], clamp);
  const a = interpolate(k, [3, 15], [0, 1], { ...clamp, easing: easeOut });
  // a logo sting (no line1): the logo centered, under it the brand line (line2, visual_plan.py export --sting takes
  // brand.tagline); with no line2 the logo variant that carries the tagline; otherwise the logo above the CTA lines
  const sting = !p.endCard.line1;
  const own = sting && !p.endCard.line2;
  const logo = own ? p.brand.logos.on_dark_tagline ?? fullLogoOnDark(p.brand) : fullLogoOnDark(p.brand);
  const box = own ? { top: 610, left: 140, width: 800, height: 700 } : sting ? { top: 640, left: 190, width: 700, height: 360 }
    : { top: 520, left: 240, width: 600, height: 300 };
  // CTA lines never run past the frame: the size shrinks to fit x 60–1020 (the plate adds 0.2 em on each side)
  // references/cta.md: the main line 52–60 px (here up to 64, the card is the whole frame), the clarifier 34–38 px in a muted color
  const s1 = p.endCard.line1 ? fitSize({ text: p.endCard.line1, size: 64, font: fonts.heading, weight: 800, maxWidth: 960, padEm: 0.2, ready }) : 64;
  const s2 = p.endCard.line2 ? fitSize({ text: p.endCard.line2, size: sting ? 52 : 38, font: fonts.body, weight: sting ? 600 : 500, maxWidth: 960, ready }) : 38;
  const c = p.brand.colors;
  return (
    <AbsoluteFill style={{ backgroundColor: c.primary, opacity: bg }}>
      {logo ? <Img src={staticFile(logo)} style={{ position: "absolute", ...box, objectFit: "contain", opacity: a }} />
        : <div style={{ position: "absolute", top: 600, width: "100%", textAlign: "center", fontFamily: fonts.heading, fontWeight: 800, fontSize: 96, color: c.text_on_primary, opacity: a }}>{p.brand.name}</div>}
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
  return (
    <AbsoluteFill style={{ backgroundColor: p.brand.colors.primary }}>
      <Footage p={p} bt={bt} />
      <BrollLayer inserts={p.inserts} brand={p.brand} />
      <KitSubtitles captions={p.subtitleCaptions ?? p.captions} brand={p.brand} font={fonts.body} mode={p.subtitles} hide={hide}
        top={p.subtitlesTop ?? 1290} look={look} shade={p.subtitlesShade ?? 0.35} part="shade" />
      <Hook p={p} look={look} font={fonts.heading} />
      <Corner p={p} />
      <SceneLayer scenes={p.scenes} brand={p.brand} look={look} words={p.captions.words} scenesOnly={!p.video} sceneTone={p.sceneTone} />
      <MemeLayer inserts={p.inserts} brand={p.brand} />
      <KitSubtitles captions={p.subtitleCaptions ?? p.captions} brand={p.brand} font={fonts.body} mode={p.subtitles} hide={hide}
        top={p.subtitlesTop ?? 1290} look={look} shade={p.subtitlesShade ?? 0.35} part="text" />
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
  video: string; // path inside public/; "" — background in the brand's primary color
  frameAt?: number | null; // second of the video under the cover (poster.py pick: middle of the hook/cover scene's rest, otherwise 1.0)
  brand: Brand;
  style?: string | null;
  text?: CoverText | null; // lines — the hook, large; label — an all-caps label above it
  cover?: SceneSpec | null; // cover scene from export (text, frameAt) — if text is not set
  logo?: boolean; // brand mark above the hook
  dim?: number; // 0–1: even dimming of the frame with the primary color (not a gradient) when the background is busy
  box?: number[] | null; // x, y, w, h of the text zone (clear of the face); absent — cover.box, otherwise the bottom of the 1:1 zone (with video) or its center
};

export const ReelCover: React.FC<ReelCoverProps> = (p) => {
  const look = styleLook(p.brand, p.style);
  const text: CoverText = p.text ?? (p.cover?.text ? { lines: p.cover.text.lines, accent: p.cover.text.accent, label: p.cover.text.label } : { lines: [] });
  const at = p.frameAt ?? p.cover?.frameAt ?? 1;
  const b = p.box ?? p.cover?.box ?? null;
  const zone = b && b.length === 4 ? { x: b[0], y: b[1], w: b[2], h: b[3] } : p.video ? COVER_ZONE_LOW : COVER_ZONE;
  return (
    <AbsoluteFill style={{ backgroundColor: p.brand.colors.primary }}>
      {p.video ? (
        <OffthreadVideo src={staticFile(p.video)} trimBefore={Math.max(0, Math.round(at * KIT_FPS))} muted style={{ width: 1080, height: 1920 }} />
      ) : null}
      {p.dim ? <AbsoluteFill style={{ backgroundColor: alpha(p.brand.colors.primary, Math.min(1, Math.max(0, p.dim))) }} /> : null}
      <Cover brand={p.brand} look={look} text={text} logo={p.logo} zone={zone} />
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
