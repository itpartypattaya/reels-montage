# Video profiles: the video's goal, its defaults and its checklist

Two questions about a video are kept apart:

- **the content format** — what the video is made of: an insight, a list, a skit, a job opening, a client testimonial
  (`reel.json → content_format`, the table in section “Content formats”);
- **the profile** — what the video is for and how loud it may be: teach, entertain, show an expert, promote, sell as a
  paid ad (`reel.json → profile`). A format brings its usual profile; the same skit can be entertaining for reach or a
  paid ad, and then the ad's rules apply.

A profile does three things: it sets the video's **defaults** (intensity, scene tone, memes on or off), it turns on the
**rules** written for it below and in the project playbook (`Applies to: profile:<id>`), and it brings its **checklist**:
`visual_plan.py validate` checks the items it can measure, the agent confirms the rest before showing the draft, and the
report's Supports name every item skipped (`references/playbook.md`, “Supports”).

A video without a profile is edited as before: no profile checklist, the brand tone and the project defaults decide.

## Choosing it

- Clear from the prompt or the footage (“a skit for reach”, “a job opening”, “an ad for the launch”, a horizontal
  podcast recording) → name the profile and the format in one line of the plan and save them:
  `reelcfg.py save edit/<id> --set profile=<id> content_format=<id>` (a format alone brings its profile).
- Not clear → ask **one separate question** before the brief: the 3 most likely profiles, the recommendation first,
  each with one line of what it changes; the rest via “Other”.
- Saved in `reel.json`, not inherited by the next video; `reelcfg.py show` prints the profile, its length range, CTA
  limit and checklist.

## The brand tone stays the ceiling

The profile chooses its defaults under the brand tone (`references/brands.md`, “Brand tone”): an intensity louder than
the tone's is held at the tone's, a scene tone the brand doesn't allow is skipped (the profile lists several, the first
allowed one is taken), memes stay within the tone's limits. `reelcfg.py show` says what was held back.

A brand that makes louder videos of one kind on purpose (an entertaining skit at a calm expert brand) records it once,
as the owner's decision: `brand.py tone <slug> <preset> --profile entertaining` keeps the brand's main tone and gives
that profile its own preset (`brand.json → tone.by_profile`). Its videos then take that tone with no per-video
`tone_override`; the brand's main tone's preset removes the entry. Offer it when the person asked for a louder video
of the same profile twice, or says “our skits are always like this”; the brand owner confirms. `tone_override=true` in
one video's `reel.json` stays for a one-off.

## Profiles

| Profile | `id` | Usual formats | Length | What differs in the edit |
|---|---|---|---|---|
| Educational | `educational` | insight, list, how-to | 30–60 s | one idea per screen, the step number on screen in a list, more text on screen, music low or none, ending = the takeaway + save / follow / comment-word; intensity moderate, scene tone calm or feature, no memes |
| Entertaining | `entertaining` | skit, story, reaction | 15–45 s (skit 45–70) | the fastest pace, a teaser variant always among the structures, payoff with a hold or a loop, memes within the brand tone, a soft CTA or none; intensity active, scene tone punchy / deadpan |
| Expert clip | `expert-clip` | interview or podcast clip, a talk, the framed format | 30–60 s | no cut changes a phrase's meaning, the name and role in the first seconds, softer edges (breaths between thoughts kept), the speaker in frame; intensity minimal, scene tone calm |
| Promo | `promo` | intro, offer / job opening, review, event, case, testimonial, scenes only | 15–45 s | the brand early and more than once, the offer, date, place and price on screen and said, the CTA at the end, facts verified with the client; intensity moderate, scene tone feature |
| Paid ad | `ad` | any format run as an ad | 15–34 s (the profile's range wins) | the ad safe zone for all text (subtitles lifted), the brand by 3 s, hook → benefit → CTA, claims with a source, licensed music only, hook variants for testing; intensity moderate, scene tone punchy / feature, no memes |

The numbers live in `assets/reel-defaults.json → profiles` (a project can change them in its own `reel-defaults.json`).
The paid ad's safe zone, x 65–1015 and y 269–1248, is Meta's Reels-ad guidance (14 % top, 35 % bottom, 6 % at the sides
kept free); TikTok's depends on the caption length, so check its template when the ad runs there.

## Content formats

| Format | `id` | Profile | Length |
|---|---|---|---|
| Insight | `insight` | educational | 30–60 s |
| List, how-to | `list` | educational | 30–60 s |
| Case study | `case` | promo | 30–45 s |
| Story | `story` | entertaining | 30–60 s |
| Skit, verdict | `skit` | entertaining | 45–70 s |
| Testimonial | `testimonial` | promo | 15–25 s |
| Intro video | `intro` | promo | 25–35 s |
| Job opening, offer | `offer` | promo | 15–30 s, two CTAs allowed (apply + recommend) |
| Review (a place, a product; often voice-over) | `review` | promo | 20–45 s |
| Event, launch | `event` | promo | 15–30 s |
| Interview clip | `interview` | expert-clip | 30–60 s |
| Scenes only (no footage) | `scenes-only` | promo | 15–25 s |

The length is a soft range: outside it, `validate` warns and the report says why (a 75 s skit that holds is fine).

## Checklists

Each item has a permanent id. **auto** — `visual_plan.py validate` checks it and prints `ALL-2 ok` or a warning
(`AD-1` and `AD-6` are errors); **validate** — an existing check covers it; **agent** — confirmed by the agent on the
draft and stills before showing it. Evidence: [platform] official platform guidance, [data] a study with data,
[standard] an industry standard, [practice] practitioners' advice, [ours] this plugin's own rule. All are ⚪ external
unless marked “real case” (🟢 verified, `references/playbook.md`); the person's own rule overrides any of them.

### Every profile

- **ALL-1** (auto) the video starts on speech or a hook within the first second: no logo intro, no greeting, no slow
  lead-in. [platform] Meta, TikTok and YouTube Shorts all ask for the point within ~3 s; [data] a logo-only opening cut
  6-second views by 14 % (Vidmob × TikTok).
- **ALL-2** (auto) the length is within the format's (or the ad's) range.
- **ALL-3** (auto) one CTA per video: CTA scenes plus the end card; two only for a job opening (`offer`). [ours]
- **ALL-4** (agent) the video reads without sound: subtitles cover the speech and are proofread. [platform] Meta,
  TikTok; [standard] subtitles at most ~20 characters per second and 2 lines (Netflix timed text).
- **ALL-5** (agent) the voice is clear over the music: the music is ducked under speech. [platform] TikTok.
- **ALL-6** (agent) no other platform's watermark or logo in the footage, memes or B-roll. [platform] Instagram limits
  the reach of such videos.
- **ALL-7** (agent) no more than three flashes in any second (light flashes, strobing cuts). [standard] WCAG 2.3.1.
- **ALL-8** (agent) the music may be used where the video goes: a track from the platform's library is added there, not
  burned in; on YouTube, a Shorts over 60 s with a claimed track is blocked. [platform] YouTube.
- **ALL-9** (agent) the last frame is clean: not cut mid-word, not an empty frame. [ours]

### Educational

- **EDU-1** (agent) one central idea, written in one sentence in `project.md`; the video doesn't drift into a second.
  [practice]
- **EDU-2** (agent) the promise (what the viewer will learn) is said or on screen in the first 3 s. [platform]
- **EDU-3** (agent) one point on screen at a time; in a list, the step number is visible (“2/5”). [practice; the
  segmenting principle of multimedia learning]
- **EDU-4** (agent) the key term is highlighted: an accent word or an accent title on its word. [signaling principle]
- **EDU-5** (agent) a diagram or list scene does not repeat the subtitles word for word next to itself: the subtitles
  are hidden or shortened under it (the kit hides them under list scenes by default). [redundancy principle]
- **EDU-6** (validate) text on screen stays long enough to read (the reading-time floor of `references/scenes.md`).
- **EDU-7** (agent) the ending is the takeaway, then save / follow / comment-word (`references/cta.md`). [practice]

### Entertaining

- **FUN-1** (agent) the first frame is action, a face or the conflict line, not a title card. [platform] Google's
  Shorts guidance; [data] a direct look into the camera raised 2-second views by 14 % (Vidmob × TikTok).
- **FUN-2** (agent) a teaser variant was among the structures offered, and it does not give the punchline away
  (`references/structure.md`). [ours; real case: the strongest structures of the skits came from teasers]
- **FUN-3** (agent) no dead air: the speech mask and the cut edges pass; a beat only before a punchline. [practice]
- **FUN-4** (agent) the ending is a payoff with a hold or a loop back to the start; no CTA card after the punchline
  unless the brief chose one. [practice; the loop's effect is not measured anywhere]
- **FUN-5** (validate) memes and reused clips have known rights and fit the brand tone.
- **FUN-6** (agent) if music or sound effects are chosen, they are heard from the first second. [platform] Google
  “announce yourself with audio”.
- **FUN-7** (validate) the techniques stay within the brand tone (or the brand's own tone for this profile).

### Expert clip

- **CLIP-1** (agent) the hook is the strongest line of the recording, even from its middle (a teaser start). [practice]
- **CLIP-2** (agent) no cut changes what the speaker meant: every kept phrase checked against the source transcript in
  context; a joined sentence still says what was said. [ours]
- **CLIP-3** (agent) the name and role are on screen in the first ~5 s (the framed format's caps label, or a card).
  [ours]
- **CLIP-4** (agent) with two speakers, the one speaking is in frame and the subtitles show who speaks. [ours]
- **CLIP-5** (agent) the edges are softer than in an entertaining video: breaths between thoughts are kept, no
  `--density tight`. [ours]
- **CLIP-6** (agent) the source is named (the podcast, the event) in the caption or on screen, and reusing the recording
  is allowed. [ours]
- **CLIP-7** (validate) the crop of a horizontal source keeps the face: the framed format and its face checks.

### Promo

- **PROMO-1** (auto) the brand is heard or seen within 5 s: its name spoken or in a scene, or the corner logo
  (`export --corner`). [platform] Google ABCD “brand early”; [data] the brand with the main message in the first 5 s
  raised the odds of high purchase intent 1.7× (Meta × Toluna, 2026).
- **PROMO-2** (agent) the brand appears more than once, not only on the end card. [data] repeated branding worked 1.8×
  better than one logo at the end (Meta × Toluna).
- **PROMO-3** (agent) the offer, date, place and price are both on screen and said (“see and say”). [platform] Google.
- **PROMO-4** (auto) there is a CTA: a CTA scene, the end card, or one spoken in the last 40 % of the video.
  [platform] Google: show the call to action again at the end.
- **PROMO-5** (agent) every price, date, address, contact and promise is confirmed by the client; anything else goes
  into “to verify”. [ours; real case: a salary range and a price on screen were sent back for verification]
- **PROMO-6** (agent) a paid or bartered partnership is disclosed in the video and with the platform's label when
  posting. [standard] FTC; [platform] Instagram, TikTok.
- **PROMO-7** (agent) links and handles on the end card are readable and real; “link in bio” only if the link is
  already there. [ours]
- **PROMO-8** (agent) a job opening (`offer`): the role, place, format, terms and how to apply are there, and the pay
  only as the client confirmed it. [ours]

### Paid ad

- **AD-1** (auto, error) all text, logos, CTAs, memes and the subtitles stay inside the ad safe zone (x 65–1015,
  y 269–1248): `export` lifts the subtitles for this profile; full-frame scenes are checked on stills. [platform] Meta.
- **AD-2** (auto) the brand or the product within 3 s. [platform] Meta, TikTok.
- **AD-3** (agent) the structure is hook → benefit → CTA, and the CTA matches the campaign's goal. [platform] TikTok.
- **AD-4** (agent) no CTA button drawn at the bottom: the platform adds its own. [practice]
- **AD-5** (agent) every claim (“No. 1”, “twice as fast”, “guaranteed”, a result) has its source in `project.md`; no
  before/after for weight loss, no lines that assert the viewer's personal traits (health, money, beliefs).
  [platform] Meta advertising standards, TikTok ad policies.
- **AD-6** (auto, error) memes and reused clips only with known rights (own, licensed, CC); music only from a licensed
  or commercial library. [platform] TikTok, Meta.
- **AD-7** (agent) 3–5 hook variants are offered for testing (other opening lines or teaser starts); made on request.
  [platform] TikTok: 3–5 creatives per ad group.
- **AD-8** (agent) native, not low quality: a source of 720p or more, clear sound. [platform] TikTok.
- **AD-9** (auto) there is a CTA (as PROMO-4).

## Where the evidence is thin

Platforms publish concrete rules for ads; for organic videos they say little beyond “the point in the first seconds,
sound, subtitles, no watermarks”. No source compares cut frequency, B-roll share or loop endings by video type: the
pace and length numbers of the profiles are this plugin's choices, kept as soft warnings. Vendor data on length by type
(educational longer, entertaining shorter) is not published with its method. Sources disagree on length (TikTok's
ad research: 21–34 s; a study of organic videos: longer ones reach more people) — hence soft ranges.

## Sources

Meta: Reels ads guide and ad safe zones; Meta advertising standards (personal attributes, health); Meta × Toluna
short-form study (2026). TikTok: creative best practices, the SMB creative QA checklist, In-Feed ad specs, Creative
Codes; Vidmob × TikTok hook analysis; TikTok × Kantar on sound. Google: YouTube Shorts help (length, Content ID) and the
Shorts ABCD. Netflix timed text style guide; WCAG 2.3.1; FTC “Disclosures 101”; Mayer's principles of multimedia
learning. Checked in 2026; platform rules change, so recheck before a paid campaign.
