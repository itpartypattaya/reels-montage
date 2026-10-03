// Brand in Remotion: the profile type (src/brands/<slug>.json from `brand.py export`) and font loading.
// The reference copy is the skill's assets/remotion-kit/; older Reel*.tsx compositions do not use kit and are not changed.
import { continueRender, delayRender, staticFile } from "remotion";
import * as Inter from "@remotion/google-fonts/Inter";
import * as Manrope from "@remotion/google-fonts/Manrope";
import * as Oswald from "@remotion/google-fonts/Oswald";
import * as Montserrat from "@remotion/google-fonts/Montserrat";
import * as Onest from "@remotion/google-fonts/Onest";
import * as InterTight from "@remotion/google-fonts/InterTight";
import * as PlayfairDisplay from "@remotion/google-fonts/PlayfairDisplay";
import * as Roboto from "@remotion/google-fonts/Roboto";
import * as Rubik from "@remotion/google-fonts/Rubik";
import * as Unbounded from "@remotion/google-fonts/Unbounded";
import * as GolosText from "@remotion/google-fonts/GolosText";
import * as Nunito from "@remotion/google-fonts/Nunito";
import * as OpenSans from "@remotion/google-fonts/OpenSans";
import * as PTSans from "@remotion/google-fonts/PTSans";

// files — upright faces, italic — italic faces (brand.py font_families); the face is still detected from the file name
export type BrandFont = { family: string; weights?: number[]; source?: "google" | "local"; files?: string[]; italic?: string[] };
// Brand tone (brand.json → tone: the expanded preset from `brand.py export`, reel-defaults.json → brand_tones). kit reads
// only the loudness of effects and the permissions: overshoot (spring bounce) and shake (the hype tone's light shake). The
// other preset fields (memes, transitions, caps) are for visual_plan.py validate. No field → calm, no bounce or shake.
export type BrandTone = {
  preset?: string;
  loudness?: "quiet" | "calm" | "lively" | "loud";
  overshoot?: boolean;
  shake?: boolean;
  scene_tone?: string; // default scene tone (kit/scenes/tones.ts)
};
export type Brand = {
  slug: string;
  name: string;
  tagline?: string;
  colors: {
    primary: string;
    accent: string;
    light: string;
    text_on_primary: string;
    text_on_accent: string;
    extra?: Record<string, string>;
  };
  fonts: { heading: BrandFont; body: BrandFont };
  logos: Record<string, string>;
  motion?: "calm" | "lively" | "energetic";
  tone?: BrandTone;
  subtitles_default?: string;
  style_default?: string;
  // optional: the look of the brand's styles, overrides the styleLook() rules, e.g. { v2: { mark: "#F5FAA4", on_mark: "#111111" } }
  looks?: Record<string, { mark?: string; on_mark?: string; heading?: BrandFont; body?: BrandFont }>;
};

type FontModule = {
  loadFont: (style?: string, opts?: { weights?: string[]; subsets?: string[] }) => { fontFamily: string };
  getInfo: () => { fontFamily: string; fonts: Record<string, Record<string, Record<string, string>>> };
};

// Google fonts with Cyrillic that kit knows. For a new brand font, add an import and an entry here.
const GOOGLE: Record<string, FontModule> = {
  Inter, Manrope, Oswald, Montserrat, Onest, "Inter Tight": InterTight, "Playfair Display": PlayfairDisplay,
  Roboto, Rubik, Unbounded, "Golos Text": GolosText, Nunito, "Open Sans": OpenSans, "PT Sans": PTSans,
} as unknown as Record<string, FontModule>;

const loaded = new Map<string, string>();

const loadGoogle = (f: BrandFont): string => {
  const key = `${f.family}|${(f.weights ?? []).join(",")}`;
  if (loaded.has(key)) return loaded.get(key)!;
  const mod = GOOGLE[f.family] ?? GOOGLE[f.family.replace(/\s+/g, "")];
  if (!mod) {
    console.warn(`kit: font ${f.family} is not registered in src/kit/brand.ts — using Inter`);
    return loadGoogle({ family: "Inter", weights: f.weights });
  }
  const info = mod.getInfo();
  const normal = info.fonts.normal ?? {};
  const have = Object.keys(normal);
  const weights = (f.weights ?? [400, 700]).map(String).filter((w) => have.includes(w));
  const first = normal[weights[0] ?? have[0]] ?? {};
  const subsets = ["cyrillic", "latin"].filter((s) => s in first);
  const { fontFamily } = mod.loadFont("normal", { weights: weights.length ? weights : [have[0]], subsets });
  loaded.set(key, fontFamily);
  return fontFamily;
};

// Weight and style from the file name (without folders) — the same words as brand.py font_meta. Order matters: ExtraBold
// before Bold, ExtraLight before Light. Italic — Italic / Oblique in the name or a “-It” suffix.
export const localFace = (file: string): { weight: string; style: "normal" | "italic" } => {
  const n = (file.split(/[\\/]/).pop() ?? file).replace(/\.[^.]+$/, "");
  const weight = /black|heavy|900/i.test(n) ? "900" : /(?:extra|ultra).?bold|800/i.test(n) ? "800"
    : /(?:semi|demi).?bold|600/i.test(n) ? "600" : /bold|700/i.test(n) ? "700" : /medium|500/i.test(n) ? "500"
    : /(?:extra|ultra).?light|200/i.test(n) ? "200" : /thin|hairline|100/i.test(n) ? "100" : /light|300/i.test(n) ? "300" : "400";
  return { weight, style: /italic|oblique/i.test(n) || /[-_ ]it$/i.test(n) ? "italic" : "normal" };
};

const loadLocal = (f: BrandFont): string => {
  const family = `${f.family}-local`;
  if (loaded.has(family)) return family;
  loaded.set(family, family);
  const handle = delayRender(`font ${f.family}`);
  Promise.all(
    Array.from(new Set([...(f.files ?? []), ...(f.italic ?? [])])).map((file) => {
      const { weight, style } = localFace(file);
      const face = new FontFace(family, `url(${staticFile(file)})`, { weight, style });
      // FontFaceSet is set-like in browsers, but TypeScript's DOM types omit add(): typed as a Set here
      return face.load().then((ff) => (document.fonts as unknown as Set<FontFace>).add(ff));
    }),
  )
    .catch((e) => console.warn("kit: local font failed to load", e))
    .finally(() => continueRender(handle));
  return family;
};

export const brandFont = (f: BrandFont): string => (f.source === "local" ? loadLocal(f) : loadGoogle(f));

export const useBrandFonts = (b: Brand) => ({ heading: brandFont(b.fonts.heading), body: brandFont(b.fonts.body) });

// hex → rgba with opacity (subtitle backings and the like)
export const alpha = (hex: string, a: number) => {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

// Video style (brand.json → styles; the style prop ← visual_plan.py export). kit implements two kinds of plate:
//   “marker” / “v2” — text on a marker plate: color is colors.extra.marker (or extra.marker_yellow), otherwise accent;
//     text on its own marker is extra.on_marker or #111111, on accent it is text_on_accent. “v2” sets everything in the
//     body font (typography.md: Inter only);
//   “brand” — accent marker, text_on_accent text, brand fonts.
// The rest (minimal, editorial, bold, glass) are not implemented in ReelKit: a console warning and “marker”.
// brand.looks[<style>] overrides any of the fields.
export type Look = { style: string; mark: string; onMark: string; heading: BrandFont; body: BrandFont };
const warned = new Set<string>();

export const styleLook = (b: Brand, style?: string | null): Look => {
  const s = (style || b.style_default || "marker").trim().toLowerCase();
  const known = s === "marker" || s === "v2" || s === "brand";
  if (!known && !warned.has(s)) {
    warned.add(s);
    console.warn(`kit: style “${s}” is not implemented in ReelKit — drawing “marker” in brand colors`);
  }
  const c = b.colors;
  const x = c.extra ?? {};
  const own = s === "brand" ? undefined : x.marker ?? x.marker_yellow;
  const o = b.looks?.[s] ?? {};
  return {
    style: known ? s : "marker",
    mark: o.mark ?? own ?? c.accent,
    onMark: o.on_mark ?? (own ? x.on_marker ?? "#111111" : c.text_on_accent),
    heading: o.heading ?? (s === "v2" ? b.fonts.body : b.fonts.heading),
    body: o.body ?? b.fonts.body,
  };
};

export const useLookFonts = (l: Look) => ({ heading: brandFont(l.heading), body: brandFont(l.body) });

export const logoOnDark =(b: Brand) => b.logos.mark_on_dark ?? b.logos.on_dark ?? b.logos.emblem ?? null;
export const fullLogoOnDark = (b: Brand) => b.logos.on_dark ?? b.logos.on_dark_tagline ?? b.logos.mark_on_dark ?? null;
