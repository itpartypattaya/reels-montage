# Virtual camera and word anchoring: code

The two helpers that keep a Remotion edit stable when the cut changes. The rules for shots are in SKILL.md, section 9.

## Shots in source time

The camera is `{ z, cx, cy }`: the scale and the frame point that ends up in the center. Shots are listed in **source time** and converted with `at(src)`, so a speed change in `cut.py` breaks nothing:
```ts
// file: source file (multicamera: the segment has a src field); seg: segment number, if that second appears in the video twice
const at = (src: number, file?: string, seg?: number) => {
  const pool = SEGS.filter((g) => (file === undefined || g.src === file) && (seg === undefined || g.i === seg));
  const hit = pool.filter((g) => src >= g.src_start - 0.001 && src <= g.src_end + 0.001);
  if (hit.length === 0) throw new Error(`at(${src}): this second was cut out, or wrong source file`);
  if (hit.length > 1) throw new Error(`at(${src}): this second is in several segments — pass seg`);
  const s = hit[0];
  return s.out_start + Math.max(0, src - s.src_start) * (s.out_dur / (s.src_end - s.src_start));
};
const W = { z: 1.0, cx: 540, cy: 960 }, M = { z: 1.1, cx: 540, cy: 1000 },
      C = { z: 1.2, cx: 540, cy: 990 },  P = { z: 1.28, cx: 540, cy: 1000 };
const SHOTS = [ { src: 0, cam: M, drift: 0.05 }, { src: 17.6, cam: P, whip: true }, /* … */ ];
// rendering: <div style={{ transform: `translate(${540 - cx*z}px, ${960 - cy*z}px) scale(${z})`,
//             transformOrigin: "0 0" }}><OffthreadVideo …/></div>
```

## Graphics on the spoken word

Anchor graphics **to the spoken word**, not to a second, so re-cutting shifts nothing:
```ts
const norm = (s: string) => s.toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
const atWord = (word: string, n = 1, offset = 0) => {
  const hits = WORDS.filter((w) => norm(w.text) === norm(word));
  if (hits.length < n) throw new Error(`no word “${word}” #${n}`);
  return hits[n - 1].start + offset;
};
```
Match ignoring edge punctuation and case: between runs, Whisper is inconsistent about punctuation attached to a word (Russian example: *eti*, “these”, comes out as “eti” in one run and “eti.” in another).
