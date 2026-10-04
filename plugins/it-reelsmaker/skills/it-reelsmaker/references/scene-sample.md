# Sample designed scene: a quote in `overlay` mode

One complete scene component for Remotion, as a starting point for the others in `references/scenes.md`. It shows the conventions every scene follows: brand colors and fonts come from the profile, never as HEX values or font names in the code; entrance and exit follow the scene-tone table; the text waits for its fonts before it is measured; the lines form one block; nothing goes outside x 60–960 and y 220–1500.

Copy it into your Remotion project (for example `src/kit/scenes/QuoteScene.tsx`) and adapt it. The quote text must be verbatim from the transcript; the plan check compares it. The two other tones, `hype` and `parody` (`bold` only), follow the same pattern: a row in `TONES` and one in `MOTION`.

```tsx
import React from "react";
import { AbsoluteFill, Easing, continueRender, delayRender, interpolate, spring, useCurrentFrame } from "remotion";

// The part of the brand profile this scene reads (brand.json copied into the Remotion project).
type Brand = {
  colors: { primary: string; accent: string; light: string; text_on_primary: string; text_on_accent: string };
  fonts: { heading: { family: string }; body: { family: string } };
};
type SceneTone = "calm" | "deadpan" | "cinematic" | "feature" | "punchy";
type QuoteSpec = {
  start: number; dur: number; // seconds on the video's timeline
  tone?: SceneTone; // the scene's own tone; otherwise the video's
  text: { lines: string[]; accent?: string; label?: string };
  box?: [number, number, number, number]; // x, y, w, h: free zone from the face measurement; default: the "headroom" zone
};
// Resolved once for the video and passed in, not read from brand.json here: the video's scene tone
// (reel.json → scene_tone, else the brand tone preset's) and whether the brand tone allows overshoot
// (the preset plus tone.overrides, references/brands.md).
type ToneRules = { sceneTone: SceneTone; overshoot: boolean };

// Scene tones: entrance and exit in frames (the same numbers as the plan check uses).
const TONES: Record<SceneTone, { in: number; out: number }> = {
  calm: { in: 14, out: 9 }, deadpan: { in: 18, out: 12 }, cinematic: { in: 16, out: 10 },
  feature: { in: 10, out: 8 }, punchy: { in: 8, out: 6 },
};
// Entrance motion by tone; p goes 0 → 1 over the entrance, s is the punchy slam scale.
const MOTION: Record<SceneTone, (p: number, s: number) => string> = {
  calm: (p) => `translateY(${(1 - p) * 30}px)`, // rise 30 px
  deadpan: () => "none", // fade only
  cinematic: (p) => `scale(${0.95 + 0.05 * p})`, // 0.95 → 1
  feature: (p) => `translateX(${(p - 1) * 60}px)`, // slide 60 px from the left
  punchy: (_p, s) => `scale(${s})`, // slam 1.08 → 1
};
const FPS = 30;
const SLAM = 1.08;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Wait for the brand fonts before the first frame is taken. document.fonts.load() also starts the download:
// a font is otherwise fetched only once some text on screen uses it, and before the scene starts nothing does.
// The wait is capped, so a missing font can't hang the render; the warning names it.
const useBrandFonts = (fonts: string[]) => {
  const key = fonts.join("|"); // a string, so the effect doesn't rerun on every frame
  const [handle] = React.useState(() => delayRender(`brand fonts ${key}`));
  React.useEffect(() => {
    let done = false;
    const finish = (warning?: string) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      if (warning) console.warn(warning);
      continueRender(handle);
    };
    const timer = setTimeout(() => finish(`fonts not loaded in 5 s, rendering with a fallback: ${key}`), 5000);
    const list = key.split("|");
    Promise.all(list.map((f) => document.fonts.load(f)))
      .then((faces) => {
        const missing = list.filter((_, i) => faces[i].length === 0);
        finish(missing.length ? `no web font registered for ${missing.join(", ")}: a fallback is used` : undefined);
      })
      .catch((e) => finish(`font loading failed: ${e}`));
    return () => finish();
  }, [key, handle]);
};

// Accent: whole words, ignoring case and the punctuation around them ("think" is not "thinking").
const bare = (s: string) => s.toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");

export const QuoteScene: React.FC<{ spec: QuoteSpec; brand: Brand; rules: ToneRules }> = ({ spec, brand, rules }) => {
  const frame = useCurrentFrame();
  const c = brand.colors;
  useBrandFonts([`800 64px "${brand.fonts.heading.family}"`, `700 26px "${brand.fonts.body.family}"`]);
  const t0 = Math.round(spec.start * FPS);
  const n = Math.round(spec.dur * FPS);
  const k = frame - t0;
  if (k < 0 || k >= n) return null;

  const tone = spec.tone ?? rules.sceneTone;
  const T = TONES[tone];
  const p = interpolate(k, [0, T.in], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const q = interpolate(k, [n - T.out, n], [1, 0], { ...clamp, easing: Easing.in(Easing.cubic) });
  // punchy settles within its entrance frames; a light bounce only if the brand tone allows overshoot
  const s = tone === "punchy"
    ? SLAM - (SLAM - 1) * spring({ frame: k, fps: FPS, durationInFrames: T.in, config: { damping: rules.overshoot ? 12 : 200 } })
    : 1;

  const [x, y, w, h] = spec.box ?? [60, 250, 900, 600];
  // the card is narrowed so that its motion stays inside the box: the slide starts at the box edge,
  // and the slam at 1.08 is exactly the box width
  const left = tone === "feature" ? x + 60 : tone === "punchy" ? x + (w - w / SLAM) / 2 : x;
  const width = tone === "feature" ? w - 60 : tone === "punchy" ? w / SLAM : w;
  const size = 64; // lines of one size, line step 1.15
  const accents = new Set((spec.text.accent ?? "").split(/\s+/).map(bare).filter(Boolean));
  const accent = (line: string) =>
    line.split(/(\s+)/).map((part, i) =>
      accents.has(bare(part))
        ? <span key={i} style={{ backgroundColor: c.accent, color: c.text_on_accent, padding: "0 0.12em" }}>{part}</span>
        : <span key={i}>{part}</span>);

  return (
    <AbsoluteFill>
      <div style={{
        position: "absolute", left, top: y, width, maxHeight: h, boxSizing: "border-box", padding: "28px 32px",
        backgroundColor: c.light, borderRadius: 18,
        opacity: p * q, transform: MOTION[tone](p, s), transformOrigin: "50% 0",
      }}>
        {spec.text.label ? (
          // all-caps label right above the quote: one block, 14 px gap
          <div style={{ fontFamily: brand.fonts.body.family, fontWeight: 700, fontSize: 26, letterSpacing: "0.2em",
            color: c.primary, opacity: 0.6, marginBottom: 14 }}>{spec.text.label}</div>
        ) : null}
        {spec.text.lines.map((line, i) => (
          <div key={i} style={{ fontFamily: brand.fonts.heading.family, fontWeight: 800, fontSize: size,
            lineHeight: 1.15, color: c.primary }}>
            {i === 0 ? "“" : ""}{accent(line)}{i === spec.text.lines.length - 1 ? "”" : ""}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
```

Checks for this scene before rendering:
- the box is in a free zone from the face measurement and is recorded in `keep_clear`;
- the text is settled long enough (`references/scenes.md`, “Reading-time floor”): `dur` minus entrance and exit, and if the quote is heard, the scene leaves no earlier than the tone's hold after the last spoken word;
- the lines fit the card at this size in the brand font (the box width, minus 60 px for `feature`, divided by 1.08 for `punchy`), and the card fits the box height (1.08 times taller in `punchy`); if not, cut the quote or take another line, don't shrink below the cards' size;
- subtitles are hidden for the scene's interval (the quote repeats the speech);
- a still of the settled scene and one mid-entrance.
