// Options: https://remotion.dev/docs/config (each one is also a CLI flag).
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// A fixed cache for the rough cut's frames (OffthreadVideo). By default Remotion sizes it from the RAM free at the
// start: on an 8 GB laptop with other apps open it shrank to a few MB and the render failed with "No frame found at
// position N" (re-encoding the video did not help; a fixed cache did). Lower it on a very small machine.
Config.setOffthreadVideoCacheSizeInBytes(384 * 1024 * 1024);
