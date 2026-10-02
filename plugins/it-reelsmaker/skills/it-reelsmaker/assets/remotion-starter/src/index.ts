// Entry point: npx remotion render src/index.ts <Composition> out/<name>.mp4
import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
