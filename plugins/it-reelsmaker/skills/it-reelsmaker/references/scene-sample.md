# Sample designed scene: a quote in `overlay` mode

One complete scene component for Remotion, as a starting point for the others in `references/scenes.md`. It shows the conventions every scene follows: brand colors and fonts come from the profile, never as HEX values or font names in the code; entrance and exit follow the scene-tone table; the text waits for its fonts before it is measured; the lines form one block; nothing goes outside x 60–960 and y 220–1500.

Copy it into your Remotion project (for example `src/kit/scenes/QuoteScene.tsx`) and adapt it. The quote text must be verbatim from the transcript; the plan check compares it.

```tsx
import React from "react";
import { AbsoluteFill, Easing, continueRender, delayRender, interpolate, spring, useCurrentFrame } from "remotion";

// The part of the brand profile this scene reads (brand.json copied into the Remotion project).
type Brand = {
  colors: { primary: string; accent: string; light: string; text_on_primary: string; text_on_accent: string };
  fonts: { heading: { family: string }; body: { family: string } };
  tone?: { overshoot?: boolean };
};
type SceneTone = "calm" | "deadpan" | "cinematic" | "feature" | "punchy";
type QuoteSpec = {
  start: number; dur: number; // seconds on the video's timeline
  tone?: SceneTone;
  text: { lines: string[]; accent?: string; label?: string };
  box?: [number, number, number, number]; // free zone from the face measurement; default: the "headroom" zone
};

// Scene tones: entrance and exit in frames (the same numbers as the plan check uses).
const TONES: Record<SceneTone, { in: number; out: number }> = {
  calm: { in: 14, out: 9 }, deadpan: { in: 18, out: 12 }, cinematic: { in: 16, out: 10 },
  feature: { in: 10, out: 8 }, punchy: { in: 8, out: 6 },
};
const FPS = 30;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Measure text only after the brand fonts are really loaded, or the fallback font's width gets used.
const useFonts = (families: string[]) => {
  const [handle] = React.useState(() => delayRender("brand fonts"));
  React.useEffect(() => {
    const ok = () => families.every((f) => document.fonts.check(`700 64px "${f}"`));
    const tick = () => (ok() ? continueRender(handle) : setTimeout(tick, 50));
    document.fonts.ready.then(tick);
  }, [families, handle]);
};

export const QuoteScene: React.FC<{ spec: QuoteSpec; brand: Brand }> = ({ spec, brand }) => {
  const frame = useCurrentFrame();
  const c = brand.colors;
  useFonts([brand.fonts.heading.family, brand.fonts.body.family]);
  const t0 = Math.round(spec.start * FPS);
  const n = Math.round(spec.dur * FPS);
  const k = frame - t0;
  if (k < 0 || k >= n) return null;

  const tone = TONES[spec.tone ?? "calm"];
  const p = interpolate(k, [0, tone.in], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const q = interpolate(k, [n - tone.out, n], [1, 0], { ...clamp, easing: Easing.in(Easing.cubic) });
  // punchy lands with a light bounce only if the brand tone allows overshoot; otherwise it settles without one
  const slam = spec.tone === "punchy"
    ? 1.08 - 0.08 * spring({ frame: k, fps: FPS, config: { damping: brand.tone?.overshoot ? 14 : 200 } })
    : 1;

  const [x, y, w] = spec.box ?? [60, 250, 900, 600];
  const size = 64; // lines of one size, line step 1.15
  const accent = (line: string) =>
    line.split(/(\s+)/).map((part, i) =>
      spec.text.accent && part.toLowerCase().includes(spec.text.accent.toLowerCase())
        ? <span key={i} style={{ backgroundColor: c.accent, color: c.text_on_accent, padding: "0 0.12em" }}>{part}</span>
        : <span key={i}>{part}</span>);

  return (
    <AbsoluteFill>
      <div style={{
        position: "absolute", left: x, top: y, width: w, boxSizing: "border-box", padding: "28px 32px",
        backgroundColor: c.light, borderRadius: 18,
        opacity: p * q, transform: `translateY(${(1 - p) * 30}px) scale(${slam})`, transformOrigin: "left top",
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
- the text is settled long enough (`references/scenes.md`, “Reading-time floor”): `dur` minus entrance and exit, counted from the last spoken word if the quote is heard;
- the lines fit 900 px at this size in the brand font; if not, cut the quote or take another line, don't shrink below the cards' size;
- subtitles are hidden for the scene's interval (the quote repeats the speech);
- a still of the settled scene and one mid-entrance.
