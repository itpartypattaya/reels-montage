// Neutral default profile: kit builds without src/brands/<slug>.json (ReelKit preview in Studio, gen/ examples).
// In a render the brand always arrives via props (`visual_plan.py export … --props`); this profile never gets there.
import { Brand } from "./brand";

export const neutralBrand: Brand = {
  slug: "neutral",
  name: "Brand",
  colors: {
    primary: "#16181D",
    accent: "#E9E6DC",
    light: "#F5F4F0",
    text_on_primary: "#F5F4F0",
    text_on_accent: "#16181D",
    extra: {},
  },
  fonts: {
    heading: { family: "Inter", weights: [600, 700, 800], source: "google" },
    body: { family: "Inter", weights: [500, 600, 700, 800], source: "google" },
  },
  logos: {},
  motion: "calm",
  subtitles_default: "plate",
  style_default: "marker",
};
