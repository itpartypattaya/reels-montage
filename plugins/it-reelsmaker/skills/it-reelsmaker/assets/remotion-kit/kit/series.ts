// The video's format and a series' marks, as plain functions (no React): ReelKit reads them, the tests run them as is.
// props.format (visual_plan.py stage) names the format: "silent" (a no-speech reel over its own picture), "scenes-only",
// "scenes-voice"; an older props file without it falls back to "no video = scenes only", as before.
// props.rubric — the series' caps label at the top, from..to (seconds of the video; reel.json → rubric);
// props.cornerFrom — the corner logo only from that second (reel.json → corner_last_s: the last N seconds).

export type SeriesProps = {
  video?: string;
  format?: string | null;
  captions: { duration: number };
  corner?: boolean;
  cornerFrom?: number | null;
  rubric?: { text: string; from?: number | null; to?: number | null } | null;
};

/** The scenes are the whole picture (no rough cut on screen): every smooth transition is a cut, every mode is full. */
export const scenesOnlyOf = (p: Pick<SeriesProps, "video" | "format">): boolean =>
  p.format ? p.format === "scenes-only" || p.format === "scenes-voice" : !p.video;

/** The corner logo's window: from cornerFrom (or the start) to the end of the rough cut (the caller adds the end card's
 *  fade). */
export const cornerOn = (p: SeriesProps, frame: number, fps: number, tail = 0): boolean =>
  !!p.corner && frame >= Math.round((p.cornerFrom ?? 0) * fps) && frame < p.captions.duration * fps + tail;

/** The rubric label's window, from..to (to: the end of the rough cut). */
export const rubricOn = (p: SeriesProps, frame: number, fps: number): boolean => {
  const r = p.rubric;
  if (!r || !r.text?.trim()) return false;
  return frame >= Math.round((r.from ?? 0) * fps) && frame < Math.round((r.to ?? p.captions.duration) * fps);
};
