// Designed scenes (references/scenes.md): scene types from the visual plan. The plan is edit/<id>/visual_plan.json →
// inserts[] with kind "scene" (ids c01, c02…); into the video via `visual_plan.py export … --props` → props.scenes (timing
// already resolved: start/dur, items[].t, interaction.t are seconds of the output timeline).
import type { Brand, Look } from "../brand";
import type { Word } from "../Subtitles";

export type SceneType = "hook" | "quote" | "slogan" | "stat" | "list" | "contrast" | "word" | "chat" | "ui" | "cta" | "cover";
// overlay — over the frame inside box; split — scene on top, speaker ×0.56 below; panel — speaker ×0.42 on one side, panel
// on the other; window — scene fills the frame, speaker in a rounded window; full — scene fills the frame, speaker hidden (voice continues)
export type SceneMode = "overlay" | "split" | "panel" | "window" | "full";
export type SceneTone = "calm" | "deadpan" | "cinematic" | "feature" | "punchy" | "hype" | "parody";
export type SceneTransition = "cut" | "fade" | "whip" | "slide" | "flash";

export type SceneItem = {
  text: string;
  t?: number | null; // second of the output timeline (from at: word:… on export); absent — items are spaced evenly
  at?: string | null;
  from?: "me" | "them" | "system" | null; // chat
};

export type SceneValue = { from?: number | null; to: number; prefix?: string | null; suffix?: string | null; decimals?: number | null };

export type SceneSpec = {
  id: string;
  kind?: "scene";
  type: SceneType;
  mode: SceneMode;
  start: number; // second of the output timeline
  dur: number;
  at?: string | null;
  tone?: SceneTone | string | null; // null → the brand's scene tone (brand.tone.scene_tone) → calm
  variant?: string | null; // hook: slam/type/stack/counter; word: grid-pick/funnel/timeline/icon; cta: tap/comment/bio
  text?: { lines: string[]; accent?: string | null; label?: string | null } | null;
  items?: SceneItem[] | null;
  value?: SceneValue | null;
  // aspect — file width/height (ui: the cursor and tap land on target only when the ratio is known; absent — 9:16)
  media?: { file: string; kind: "image" | "video"; aspect?: number | null } | null;
  // target — fractions of the media frame (0–1, from the top-left corner); values > 1 are read as pixels of a 1080×1920 source
  interaction?: { kind: "tap" | "type" | "cursor" | "swipe"; target?: number[] | null; text?: string | null; at?: string | null; t?: number | null } | null;
  box?: number[] | null; // x, y, w, h on the 1080×1920 screen: the scene zone (overlay — required, from faces.json; otherwise — by mode)
  side?: "left" | "right" | null; // panel: where the speaker moves (default left); window: window corner (default right)
  face?: number[] | null; // x, y, w, h of the face in the source (faces.json over the scene's time): window placement and panel crop
  source?: { kind: "speech" | "brief" | "brand" | "client" | "agent" | string; ref?: string | null } | null;
  what?: string;
  why?: string;
  transition_in?: SceneTransition | null; // null → the tone's default transition
  transition_out?: SceneTransition | null;
  sound?: string | null; // sound is chosen at mixing; the kit does not play it
  hide_subtitles?: boolean | null;
  status?: "planned" | "ready" | "skipped" | string;
  frameAt?: number | null; // cover only: second of the video under the cover (if poster.py set it)
};

// Brand tone — a copy of the Brand.tone field (kit/brand.ts). Kept as a separate copy so scenes also build with a brand.ts without tone.
export type SceneBrandTone = {
  preset?: string;
  loudness?: "quiet" | "calm" | "lively" | "loud";
  overshoot?: boolean;
  shake?: boolean;
  scene_tone?: string;
};
export const readBrandTone = (b: Brand): SceneBrandTone | undefined => (b as unknown as { tone?: SceneBrandTone }).tone;

export type Loudness = "quiet" | "calm" | "lively" | "loud";
// Resolved brand tone for the kit: no brand.tone → calm, no overshoot and no shake.
export type ResolvedTone = { loudness: Loudness; overshoot: boolean; shake: boolean; sceneTone: SceneTone };

// Timing of one scene in frames from its start (tones.ts → sceneTimeline). The reading threshold is measured on settleFrom/settleTo.
export type Timeline = {
  n: number; // scene length
  tin: SceneTransition; // transitions after the “on a pause — cut” rule
  tout: SceneTransition;
  L: number; // layout change on entry (speaker shrinks, field, wipe)
  Lout: number; // and on exit
  lead: number; // content starts entering after 0.6 of the layout change
  tail: number; // and finishes exiting before 0.6 of the reverse change
  inF: number; // content entry by tone
  outF: number; // content exit by tone
  settleFrom: number; // the text is fully on screen and not leaving: [settleFrom, settleTo)
  settleTo: number;
};

export type Stage = { x: number; y: number; w: number; h: number };

// The surface the text sits on: field (primary color), light card, or a marker-colored field (slogan).
export type Surface = {
  kind: "field" | "card" | "mark";
  bg: string;
  text: string;
  hiBg: string; // highlight plate (accent word, the item being spoken)
  hiText: string;
  accent: string; // accent color of text and lines (brackets, marker bar, numbers) — only the style's marker color
  muted: string; // labels, captions
  soft: string; // secondary fills (mini cards, other people's messages)
  line: string; // thin lines
};

export type SceneCtx = {
  spec: SceneSpec;
  frame: number; // frame from the scene start
  fps: number;
  tl: Timeline;
  tone: SceneTone;
  bt: ResolvedTone;
  brand: Brand;
  look: Look;
  fonts: { heading: string; body: string };
  surf: Surface; // content surface in this mode
  surfaces: { field: Surface; card: Surface; mark: Surface };
  mode: SceneMode; // mode adjusted for “scenes only” (no video: split/panel/window → full)
  stage: Stage; // scene zone, always inside x 60–960, y 220–1500
  inner: { w: number; h: number }; // room for content inside the zone (minus card padding)
  shell: "card" | "plates" | "field"; // what is under the content: a card, plates directly over the video, a color field
  words: Word[]; // speech words during the scene (seconds of the output timeline) — for “the word on its own word”
  radius: number; // corner radius of the style's cards (v2 — no rounding)
};
