// The video's format, a series' marks and a scene's frames, as plain functions (no React): ReelKit reads them, the tests
// run them as is.
// props.format names the format by name: visual_plan.py stage writes "silent" (a no-speech reel over its own picture);
// "scenes-only" and "scenes-voice" are read when a props file gives them, and without a format a props file with no
// video counts as scenes only (stage writes no video for those two).
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

/** A scene's frames as SceneLayer plays it: from round(start·fps), round(dur·fps) frames (at least one). The subtitles
 *  hide in exactly these frames: counted in seconds, a scene at 1.01 s began on frame 30 and the subtitle hid from
 *  frame 31, one frame of subtitle over the scene's field (review 2026-11-17 #36). */
export const sceneFrames = (s: { start: number; dur: number }, fps: number): { from: number; frames: number } =>
  ({ from: Math.round(s.start * fps), frames: Math.max(1, Math.round(s.dur * fps)) });

/** The scenes are the whole picture (no rough cut on screen): every smooth transition is a cut, every mode is full. */
export const scenesOnlyOf = (p: Pick<SeriesProps, "video" | "format">): boolean =>
  p.format ? p.format === "scenes-only" || p.format === "scenes-voice" : !p.video;

/** The corner logo's window: from cornerFrom (or the start) to the end of the rough cut (the caller adds the end card's
 *  fade). */
export const cornerOn = (p: SeriesProps, frame: number, fps: number, tail = 0): boolean =>
  !!p.corner && frame >= Math.round((p.cornerFrom ?? 0) * fps) && frame < p.captions.duration * fps + tail;

/** The corner logo under a scene: it fades out (1 - activity), except a series' logo of the last seconds or a
 *  no-speech reel, where scenes run all along and would hide it for good (Codex review). */
export const cornerFade = (p: Pick<SeriesProps, "cornerFrom" | "format">, activity: number): number =>
  cornerAbove(p) ? 1 : 1 - activity;

/** A corner logo that stays over the scenes is drawn ABOVE the scene layer: under it, a scene's opaque field (a split
 *  slogan's top, a full scene) would cover it however opaque the logo is (Codex review of PR #57). The corner of a
 *  talking head stays below the scenes and fades out under them, as before. */
export const cornerAbove = (p: Pick<SeriesProps, "cornerFrom" | "format">): boolean =>
  p.cornerFrom != null || p.format === "silent";

/** The rubric label's window, from..to (to: the end of the rough cut). */
export const rubricOn = (p: SeriesProps, frame: number, fps: number): boolean => {
  const r = p.rubric;
  if (!r || !r.text?.trim()) return false;
  return frame >= Math.round((r.from ?? 0) * fps) && frame < Math.round((r.to ?? p.captions.duration) * fps);
};
