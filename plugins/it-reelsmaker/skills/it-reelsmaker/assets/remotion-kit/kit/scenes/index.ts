// Designed scenes of the kit (references/scenes.md). ReelKit mounts SceneLayer and the speaker frame speakerRectAt;
// your own Reel<id>.tsx can import individual scenes the same way as BrollLayer/MemeLayer.
export * from "./types";
export * from "./tones";
export { SAFE_ZONE, FULL_RECT, SceneLayer, effectiveMode, playableScenes, sceneActivity, sceneHideIntervals, sceneStage, speakerRectAt, speakerTarget } from "./SceneLayer";
export type { SpeakerRect } from "./SceneLayer";
export { Brackets, Label, TextBlock, contrast, fmtNumber, surfaces, wordTimes } from "./parts";
export { Hook } from "./Hook";
export { Quote } from "./Quote";
export { Slogan } from "./Slogan";
export { Stat } from "./Stat";
export { List } from "./List";
export { Contrast } from "./Contrast";
export { WordViz } from "./WordViz";
export { Chat } from "./Chat";
export { Ui } from "./Ui";
export { CtaAction } from "./CtaAction";
export { COVER_ZONE, COVER_ZONE_LOW, Cover } from "./Cover";
export type { CoverText } from "./Cover";
