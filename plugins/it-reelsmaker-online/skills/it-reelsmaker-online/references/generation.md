# Video generation by a model

Code scenes (Remotion) are described in `inserts.md` of the core skill `it-reelsmaker`; this file covers the `model` engine only.

| | `model` — a video model via API |
|---|---|
| Used for | photorealism: hands, objects, places, atmosphere |
| Price | ≈ $0.18–0.60 per 6 s; providers and models — `sources.md` in this folder |
| Conditions | an API key, `generate_now=true` and the person's approval (“yes”) of the amount |
| If conditions are not met | the prompt goes to `edit/<id>/generated/prompts.md`, the insert stays `pending`, the edit continues |

**Prompt fields** (`gen` on the insert; for the model — in English):
- `engine` — `code` or `model`;
- `subject`, `action`, `camera`, `composition`, `lighting`, `mood` — what is in the shot and how it is filmed;
- `start`, `end` — the start and end of the action;
- optional: `setting`, `style`, `seconds` (default 6), `use_from` — the second of the clip from which the insert is taken, default 0.3.

**Prompt template for the model:**

```text
Vertical 9:16 {composition}.
Subject: {subject}.
Action: begins with {start}; over {seconds} seconds {action}; ends with {end}, holding still for the final second.
Camera: {camera}, smooth, single continuous shot, no cuts.
Setting & light: {setting}, {lighting}.
Mood & style: {mood}, subtle color accents of {accent and primary as words — models do not understand HEX}, photorealistic, natural color grade, cinematic 24 fps.
Clean frame: no on-screen text, no captions, no logos, no watermarks, no brand names; keep the key subject in the middle third (top and bottom are covered by app interface).
Negative: text, captions, letters, logos, watermark, distorted hands, extra fingers, deformed faces, flicker, cuts, {the brand's forbidden_imagery_en}
```

**Prompt checks:**
- all fields are filled in;
- no text or logo in the scene (phrases such as “no text” and “blank” do not count);
- no imagery forbidden for the brand. Matching is by whole words, allowing for word endings: “hands” is not “handshake”;
- no large face: models get faces wrong, and an AI label would be needed as well;
- the clip is not shorter than the insert.

**A good scene for generation:**
- one action and one camera move;
- a calm start and end;
- the key subject in the middle third: the UI covers the top 220 px and the bottom 420 px;
- no text in the frame; text is added as a layer of the video.

**The `model` engine.**
- The first run without confirmation only states the amount.
- **No double charging**: right after a job is submitted, its id and result URLs are written to the plan; a repeat run resumes the existing job instead of creating a new paid one. If the job failed at the provider, a new generation again needs the person's approval (“yes”).
- **Checks before the price**: the prompt fields are non-empty strings; the provider/model pair is supported, and so is the duration for that model. Otherwise the insert stays a prompt (`pending`) with the reason.
- A clip generated manually in any service is placed at `edit/<id>/generated/<id>.mp4` and picked up the same way.

**AI label.** A photorealistic insert from a model requires the “AI info” label when published on Instagram (Meta's rules). Stylized graphics made with code do not.
