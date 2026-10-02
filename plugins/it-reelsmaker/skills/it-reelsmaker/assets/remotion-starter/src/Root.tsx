import { Composition } from "remotion";
import { KIT_FPS, ReelCover, ReelKit, reelCoverDefaults, reelKitDefaults, reelKitMetadata } from "./ReelKit";
import { GEN } from "./gen/registry";

// Created by kit.py new. The kit (src/ReelKit.tsx, src/kit/) is updated by kit.py update; this file is yours.
export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* The template for any brand: the data comes as props (visual_plan.py export --props):
          npx remotion render ReelKit out/<name>.mp4 --props=edit/<id>/reelkit-props.json */}
      <Composition
        id="ReelKit"
        component={ReelKit}
        durationInFrames={90}
        fps={KIT_FPS}
        width={1080}
        height={1920}
        defaultProps={reelKitDefaults}
        calculateMetadata={reelKitMetadata}
      />
      {/* The cover (a still): a video frame + the hook, same props as ReelKit:
          npx remotion still ReelCover edit/<id>/cover.png --props=edit/<id>/reelkit-props.json */}
      <Composition id="ReelCover" component={ReelCover} durationInFrames={1} fps={KIT_FPS} width={1080} height={1920}
        defaultProps={reelCoverDefaults} />
      {/* Code scenes for B-roll (codescene.py scaffold / render) */}
      {GEN.map((g) => (
        <Composition key={g.id} id={g.id} component={g.component} durationInFrames={g.durationInFrames} fps={30} width={1080} height={1920} />
      ))}
    </>
  );
};
