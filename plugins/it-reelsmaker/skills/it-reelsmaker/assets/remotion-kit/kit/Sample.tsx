// A sampled render (props.sample): frame k of the composition shows frame frames[k] of the video, frozen, so one
// Remotion call (`render … --frames=0-(n−1)`) renders any set of frames. The composition keeps the video's length:
// Remotion clamps a frozen frame to the composition's range (a 4-frame composition froze frame 935 at frame 3).
// Used by board.py (the storyboard sheet: a settled frame of every scene and insert) and textcheck.py (text boxes every
// 0.1 s). probe: <TextProbe> logs the boxes of the text on screen (read with --log=verbose); media: false leaves out the
// rough cut, B-roll, memes and screen recordings (text does not depend on them, the pass is faster). A per-video
// composition gets the same with <Sampled sample={p.sample}> around its content.
import React from "react";
import { AbsoluteFill, Freeze, continueRender, delayRender, useCurrentFrame } from "remotion";

export type Sample = { frames: number[]; probe?: boolean; media?: boolean };

/** false inside a sample with media: false — the kit's video and image layers render nothing. */
export const MediaOn = React.createContext(true);
export const useMedia = () => React.useContext(MediaOn);

export const Sampled: React.FC<{ sample: Sample; children: React.ReactNode }> = ({ sample, children }) => {
  const k = useCurrentFrame();
  const root = React.useRef<HTMLDivElement>(null);
  const f = sample.frames[Math.min(Math.max(0, k), sample.frames.length - 1)] ?? 0;
  return (
    <MediaOn.Provider value={sample.media !== false}>
      <AbsoluteFill ref={root}>
        <Freeze frame={f}>{children}</Freeze>
      </AbsoluteFill>
      {sample.probe ? <TextProbe root={root} frame={f} /> : null}
    </MediaOn.Provider>
  );
};

// Text boxes in composition pixels: measured from the root's own box (the page puts the composition far off screen while
// it renders: without that, y came out near −1 000 000), after the fonts load and a frame is laid out (measured at once,
// the first frame of every browser tab was lost: Remotion attaches its console listener a moment later).
// A line per frame: RK_TEXT {"f": frame, "b": [[key, text, x, y, w, h, alpha, visible], …]}.
//   key — the closest data-rk="…" group (kit: sub, hook, label, endcard, cover, scene:<id>; none in a per-video
//     composition) + "/" + the nearest block-level parent, so the words of one line are one box and two lines, or two
//     texts of one scene, are two;
//   alpha — the product of the opacities up to the root (text under 0.05 is left out);
//   visible — the share of the box's core left after the ancestors that clip their content (overflow other than
//     visible). The core is the box without its top and bottom fifth: a line box runs above the capitals and below the
//     baseline, and a reveal mask the height of the line cut 53 % of a slogan word's box with every letter in view.
const PROBE = "RK_TEXT ";
const INLINE = new Set(["inline", "inline-block", "inline-flex", "contents"]);
const CORE = 0.2; // the share of a line box above and below its letters (textcheck.py takes the same)

type Box = { key: string; text: string; x: number; y: number; w: number; h: number; a: number; v: number };

export const TextProbe: React.FC<{ root: React.RefObject<HTMLDivElement | null>; frame: number }> = ({ root, frame }) => {
  React.useLayoutEffect(() => {
    const handle = delayRender("text probe");
    let done = false;
    const finish = () => { if (!done) { done = true; continueRender(handle); } };
    // the kit re-lays its text out once its fonts are in (line breaks, fitted sizes; Phrase.tsx useFontsLoaded holds
    // its own delayRender meanwhile): measured as soon as document.fonts was ready, the first frame of every tab had a
    // subtitle phrase still on one 1600 px line. So: fonts ready, no other delayRender pending (Remotion's
    // window.remotion_delayRenderTimeouts), then two animation frames with no change under the root (at most ~10 s).
    const others = () => {
      const pending = (window as unknown as { remotion_delayRenderTimeouts?: Record<string, unknown> }).remotion_delayRenderTimeouts;
      return pending ? Object.keys(pending).filter((k) => k !== String(handle)).length : 0;
    };
    let changed = true;
    const obs = new MutationObserver(() => { changed = true; });
    const log = () => {
      obs.disconnect();
      try {
        const el = root.current;
        if (el) console.log(PROBE + JSON.stringify({ f: frame, b: measure(el).map((b) => [b.key, b.text, b.x, b.y, b.w, b.h, b.a, b.v]) }));
      } finally {
        finish();
      }
    };
    document.fonts.ready.then(() => {
      if (root.current) obs.observe(root.current, { subtree: true, childList: true, attributes: true, characterData: true });
      let quiet = 0;
      let left = 600;
      const tick = () => {
        quiet = changed || others() > 0 ? 0 : quiet + 1;
        changed = false;
        if (quiet >= 2 || --left <= 0) log();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    return () => { obs.disconnect(); finish(); };
  });
  return null;
};

const measure = (el: HTMLElement): Box[] => {
  const R = el.getBoundingClientRect();
  const k = R.width / 1080 || 1;
  const alphaOf = new Map<Element, number>();
  const alpha = (e: Element | null): number => {
    if (!e || e === el) return 1;
    const got = alphaOf.get(e);
    if (got !== undefined) return got;
    const cs = getComputedStyle(e);
    const own = cs.visibility === "hidden" ? 0 : parseFloat(cs.opacity || "1");
    const v = own * alpha(e.parentElement);
    alphaOf.set(e, v);
    return v;
  };
  const keyOf = (e: Element): string => {
    let group = "";
    let block: Element | null = null;
    for (let q: Element | null = e; q && q !== el; q = q.parentElement) {
      if (!block && !INLINE.has(getComputedStyle(q).display)) block = q;
      const g = q.getAttribute("data-rk");
      if (g) { group = g; break; }
    }
    return `${group}/${block ? elementId(block) : "root"}`;
  };
  const clipOf = (e: Element): DOMRect | null => {
    let c: { l: number; t: number; r: number; b: number } | null = null;
    for (let q: Element | null = e; q && q !== el; q = q.parentElement) {
      const cs = getComputedStyle(q);
      if (cs.overflowX === "visible" && cs.overflowY === "visible") continue;
      const r = q.getBoundingClientRect();
      c = c ? { l: Math.max(c.l, r.left), t: Math.max(c.t, r.top), r: Math.min(c.r, r.right), b: Math.min(c.b, r.bottom) }
        : { l: r.left, t: r.top, r: r.right, b: r.bottom };
    }
    return c ? new DOMRect(c.l, c.t, Math.max(0, c.r - c.l), Math.max(0, c.b - c.t)) : null;
  };
  const out: Box[] = [];
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const text = (n.textContent ?? "").trim();
    const parent = n.parentElement;
    if (!text || !parent) continue;
    const a = alpha(parent);
    if (a < 0.05) continue;
    const key = keyOf(parent);
    const clip = clipOf(parent);
    const range = document.createRange();
    range.selectNodeContents(n);
    for (const r of Array.from(range.getClientRects())) {
      if (r.width < 1 || r.height < 1) continue;
      const core = new DOMRect(r.left, r.top + CORE * r.height, r.width, (1 - 2 * CORE) * r.height);
      const vis = clip ? overlap(core, clip) / (core.width * core.height) : 1;
      const b: Box = { key, text, x: (r.left - R.left) / k, y: (r.top - R.top) / k, w: r.width / k, h: r.height / k, a, v: vis };
      // the words of one line (spans of one block) become one box: same key, the same line, a gap under half the height
      const same = out.find((o) => o.key === key && Math.min(o.y + o.h, b.y + b.h) - Math.max(o.y, b.y) > 0.5 * Math.min(o.h, b.h)
        && Math.max(o.x, b.x) - Math.min(o.x + o.w, b.x + b.w) < 0.5 * Math.min(o.h, b.h));
      if (same) {
        const x2 = Math.max(same.x + same.w, b.x + b.w);
        const y2 = Math.max(same.y + same.h, b.y + b.h);
        const area = same.w * same.h + b.w * b.h;
        same.v = (same.v * same.w * same.h + b.v * b.w * b.h) / area;
        same.x = Math.min(same.x, b.x);
        same.y = Math.min(same.y, b.y);
        same.w = x2 - same.x;
        same.h = y2 - same.y;
        same.a = Math.max(same.a, b.a);
        if (same.text.length < 40) same.text = `${same.text} ${b.text}`;
      } else {
        out.push(b);
      }
    }
  }
  return out.map((b) => ({ ...b, text: b.text.slice(0, 40), x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.w), h: Math.round(b.h),
    a: Math.round(b.a * 100) / 100, v: Math.round(b.v * 100) / 100 }));
};

const overlap = (a: DOMRect, b: DOMRect) =>
  Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));

// a stable name for a block element within one frame (its path from the root): two frames of one scene give the same key
const elementId = (e: Element): string => {
  const path: number[] = [];
  for (let q: Element | null = e; q && q.parentElement; q = q.parentElement) {
    path.push(Array.prototype.indexOf.call(q.parentElement.children, q));
    if (q.parentElement.hasAttribute("data-rk")) break;
  }
  return path.reverse().join(".");
};
