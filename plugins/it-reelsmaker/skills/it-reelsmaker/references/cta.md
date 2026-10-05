# CTA library

The call-to-action codes and their texts for the end card and the `cta` scene. ⟨YOURS: fill in contacts, remove what you don't need.⟩

**The brand's own library comes first.** A brand can keep its CTAs with exact texts in `brands/<slug>/cta.md`, set in `brand.json → cta_library` (`references/brands.md`). It uses the same columns as the table below; this file gives the structure and generic templates. When the person names a preferred CTA or an exact wording for the brand, it goes into the brand's `cta.md`, not into one video's notes.

## How to offer it (brief, step 7)

The agent does not pick the CTA on its own.
1. Choose by the video's format, the transcript and the audience (“For whom”): up to **3 fitting CTAs**, the recommended one first; from the brand's library first, then from the table below.
2. For each, one line on why it fits this video, and the exact text of both card lines.
3. The other answers, as the last option or through “Other”: **CTA by voice in the last line** (the speaker says it, no card), **no CTA**, or a **logo sting** (an outro with the logo, 2–3 s, no CTA) when the brand wants recognition without a call.
4. A CTA code already given in the prompt is not asked about, but the card text is shown before rendering.
5. **Where** is part of the answer: on the end card (after the video), on a card over the video on the spoken words, or only by voice. These are places for the one CTA, not extra CTAs: a call spoken in the speech plus the same call on a card is one CTA; a different call on the end card replaces the card over the video, unless the person asks for both (then say once that it breaks the one-CTA rule, and record it in `project.md`). A spoken call is never a reason to leave the end-card options out: the person may still want the end card with a call from the library.
6. A `cta` scene over the video and the end card are two places too: the same text in both is the one CTA shown twice. Recommend one (the end card when the video simply ends; the `cta` scene when the call lands on spoken words or needs a gesture such as a tap) and give the other a different job (a logo sting instead of the end card) or leave it out.
7. The logo question decides only where the logo goes; it does not choose a logo sting over an end card with a CTA.
   **The end of a voice-over video** with no call in the speech: a `cta` scene over the last seconds has to fit both the reading floor (`references/scenes.md`) and the rule that only a CTA is on screen in the last 2 s, and two lines often don't (8 words need 2.4 s settled plus the entrance). Offer one of: **one short line** (up to 3 words, 0.8 s, plus a tap on a button) and the clarifier left out or moved to the post caption; **a longer hold**: extend the last range of `cut.json` over the silence after the last word (1.5–2.5 s of picture) so both lines have room; or **the end card** (`export --card "line 1" "line 2"`) instead of the scene, which has its own 2.6 s after the video. Say which one in the plan and why.
8. Texts come from the library word for word. If a clarifier was written for another audience (for companies, and the video speaks to candidates), offer the adaptation next to the original and say it is adapted.

## On the card

One CTA per video (exception: a job opening, with apply + recommend). Tone: a calm invitation, no “Urgent” or “Hurry up”. Two lines: the **main line** (SemiBold, 52–60 px on a card over the video; the kit's full-frame end card draws it up to 64 px / 800, fitted to the width) and a **clarifier** (Medium, 34–38 px, in the style's muted color). Under the main line, the chosen style's accent: a marker bar or focus brackets in “Brand”, a marker bar on the key word or symbol in “Marker”. If the speaker says the link or address, the card enters on those words.

| Code | For whom | Main line | Clarifier | Fits the format |
|---|---|---|---|---|
| `dm` | everyone | Send me a DM | I'll reply personally | insight, case study |
| `dm-word` | everyone | DM me “`{{CODE_WORD}}`” | I'll send ⟨what exactly⟩ | insight with a lead magnet |
| `comment-word` | everyone | Comment “+” below | I'll DM you ⟨what exactly⟩ | insight, checklist |
| `site` | companies | `{{SITE}}` | ⟨YOURS: what's there⟩ | case study, insight for clients |
| `bio` | everyone | Link in bio | ⟨where it leads⟩ | any |
| `messenger` | everyone | ⟨messenger⟩: `{{HANDLE}}` | Message me directly | any |
| `apply` | candidates, customers | Apply via DM | ⟨what to send⟩ | job opening / offer |
| `recommend` | everyone | Know someone like this? | Recommend them: link in bio | job opening |
| `brief` | companies | ⟨YOURS: question to the client⟩ | Describe your task: `{{SITE}}` | case study, testimonial |
| `save` | everyone | Save this so you don't lose it | Useful ⟨when⟩ | insight with a list |
| `share` | everyone | Send this to someone who ⟨who⟩ | — | insight |
| `follow` | everyone | Follow for more | ⟨YOURS: what about and how often⟩ | insight, series |

Promises (“I'll reply within a day”, “every week”, a lead magnet) only if they are actually kept. “Link in bio” only if the link is already there.
