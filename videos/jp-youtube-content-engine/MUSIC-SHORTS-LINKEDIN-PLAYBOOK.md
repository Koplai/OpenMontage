# Music, Shorts, and LinkedIn Distribution Playbook

Authoritative operating date: **21 August 2026**

This playbook extends the Spanish-first YouTube content engine with a sonic
identity, an open-source-assisted derivative workflow, and a measurable
LinkedIn-to-YouTube funnel. It does not authorize unattended publishing.

## 1. Sonic identity: calm technical momentum

The music should make the content feel considered, current, and operational.
It must never compete with the explanation.

### Brand sound

- **Style:** restrained modern electronic, ambient-tech, and minimal pulse.
- **Tempo:** 88–96 BPM; default 92 BPM.
- **Harmony:** minor or suspended tonal center with a warmer resolution at the
  CTA; default D minor.
- **Palette:** warm analog pulse, soft sub bass, dry muted percussion, sparse
  glass-like plucks, and a low-air pad.
- **Avoid:** vocals, corporate ukulele, festival drops, trailer braams, busy
  arpeggios, vinyl crackle, comic sounds, or a dominant melody.
- **Signature:** reuse the approved short sonic mark at chapter changes and the
  end card; do not play the full ident before every derivative.

### Music is not continuous by default

| Moment | Treatment | Purpose |
| --- | --- | --- |
| Cold open | 8–16 seconds of controlled tension | Establish consequence without delaying the hook |
| Promise | Brief lift, then fade | Mark the transition from problem to method |
| Dense explanation | No music or barely audible pad | Protect comprehension |
| Live demo | Usually no music | Preserve interface and speech detail |
| Chapter transition | 0.4–0.8 second sonic mark | Orientation, not decoration |
| Decision summary | Quiet pulse returns | Build toward the conclusion |
| CTA and end screen | Warm resolved variation | Create a consistent close |

### Internal mix targets

These are production controls, not claims about platform normalization.

- Dialogue is the reference and remains intelligible on phone speakers.
- Music under speech starts **14–18 dB below dialogue**.
- Apply **4–8 dB side-chain ducking** while Juan Pedro speaks.
- Reduce musical energy around **1.5–4 kHz** when it masks consonants.
- Final master target: approximately **-14 LUFS integrated**, with
  **true peak at or below -1 dBTP**.
- Listen on studio headphones, laptop speakers, and one phone before approval.
- Any music that changes the perceived meaning or emotional weight of a
  technical claim is blocking.

### Generation and rights

Primary path: **ACE-Step 1.5**, using the project tool
`tools/music_gen.py`. ACE-Step source is MIT-licensed, but every generated
asset still receives a provenance record containing prompt, model/version,
seed, generation date, and human approval.

Default prompt:

> Instrumental restrained modern electronic underscore for a senior cloud
> architect explaining enterprise AI governance. Warm analog pulse, sparse
> glass-like plucks, dry muted percussion, low-air pad, calm authority,
> precise and contemporary, no vocals, no dominant melody, no trailer sound,
> no corporate ukulele, spacious mix designed to sit below speech.

Generate one 12-minute family with a fixed seed, plus short hook and CTA
variants. Do not call a paid endpoint until its provider, model, expected cost,
and sample scope have been approved. ElevenLabs Music is an optional paid
fallback, not the default.

## 2. Derivative output contract

Every approved flagship produces:

- two YouTube Shorts;
- the same two ideas re-edited as native LinkedIn videos;
- one LinkedIn document/carousel that summarizes the framework;
- platform-specific copy, captions, thumbnails/covers, links, and UTMs.

A derivative is not an arbitrary excerpt. It must be understandable without
the full episode, teach one useful idea, and lead naturally to the next step.

### Internal format standard

- Master canvas: **1080 × 1920**, 9:16, H.264/AAC.
- Duration target: **35–75 seconds**.
- Spoken hook begins in the first second; no pre-roll ident.
- Captions are burned in and also exported as corrected SRT.
- Maximum two caption lines; keep text inside the channel-kit mobile safe area.
- The face, interface evidence, and captions may not compete for the same area.
- End card: 2–3 seconds, one action only.
- Never crop a Microsoft interface until the required control remains readable.

## 3. Open-source-assisted stack

The production path deliberately combines small, inspectable tools instead of
depending on one opaque “viral score.”

| Layer | Tool | Decision |
| --- | --- | --- |
| Transcript | OpenMontage local STT / faster-whisper | Primary Spanish timestamp source |
| Candidate scoring | Local Ollama-compatible LLM | Rank teaching value, self-containment, hook, evidence, and funnel fit |
| Pause cleanup | [auto-editor](https://github.com/WyattBlue/auto-editor) | Optional first pass; active and public-domain source |
| Semantic clipping reference | [OpenClip](https://github.com/linzzzzzz/openclip) | MIT; useful for candidate extraction and CLI workflow |
| Speaker-aware 9:16 reframe | [ClipsAI](https://github.com/ClipsAI/clipsai) | MIT; useful component, but pin and test because upstream activity is stale |
| Cut, captions, brand render | OpenMontage + FFmpeg/HyperFrames | Authoritative output and QA layer |
| Alternative review UI | [FunClip](https://github.com/modelscope/FunClip) | MIT and active; Spanish ASR path must be validated before adoption |

Repository review was performed on 21 August 2026. License and model-weight
terms must be rechecked before every upgrade.

### Rejected as the primary path

- **MoneyPrinterTurbo:** strong automated short-form generator, but its main
  workflow creates new faceless videos from a topic or script; it is not the
  faithful long-form-to-short editor needed here.
- **ShortGPT:** useful generative framework, but not the most direct or current
  path for extracting evidence-led clips from an approved recording.
- **AI-Youtube-Shorts-Generator:** promising local workflow, but the repository
  root did not contain a license file during the 21 August 2026 review despite
  its README claiming MIT. Do not integrate until the licensing ambiguity is
  resolved.
- **“Virality score” as approval:** never sufficient. A human approves every
  excerpt, factual boundary, crop, caption, and CTA.

## 4. Automatic Shorts workflow

1. Start only after the flagship final cut is approved.
2. Transcribe the final master in Spanish with word timestamps.
3. Ask the local scorer for 6–10 candidate passages using:
   - immediate hook;
   - one complete lesson;
   - practical or surprising value;
   - no missing visual context;
   - no unsupported claim;
   - natural route to the full episode.
4. Reject candidates that begin mid-sentence, depend on an unseen screen, expose
   sensitive data, or distort the long-form conclusion.
5. Juan Pedro approves two candidates.
6. Optionally remove dead space with auto-editor.
7. Reframe with ClipsAI or an OpenMontage tracking pass.
8. Render channel-kit captions, evidence callouts, progress bar, and end card.
9. Run technical, factual, visual, audio, caption, and safe-area QA.
10. Export separate YouTube and LinkedIn packages; do not upload one platform's
    metadata unchanged to the other.

## 5. YouTube Shorts → flagship

- Upload the Short natively.
- Use YouTube's **Related video** feature to attach the approved flagship.
- Repeat the link in the description and pinned comment as a fallback.
- The spoken CTA names the benefit: “En el vídeo completo te enseño los cinco
  controles y puedes descargar el checklist.”
- Never send a viewer to a generic channel homepage when a relevant episode or
  playlist exists.

## 6. LinkedIn → YouTube funnel

Upload the clip as a native LinkedIn video with corrected captions. The post is
not a YouTube link preview.

### Post structure

1. One-line problem or counter-intuitive insight.
2. Three short lines that teach the framework.
3. One question that invites a professional example.
4. Direct CTA to the specific YouTube flagship, with a LinkedIn-specific UTM.
5. Mirror the link in the first comment for usability, not as an unsupported
   algorithm tactic.

Example CTA:

> He desarrollado los cinco controles con una demo y un checklist práctico.
> Vídeo completo: {{YOUTUBE_VIDEO_URL_WITH_LINKEDIN_UTM}}

Also place the current flagship or playlist in the LinkedIn profile's Featured
section. LinkedIn remains a discovery surface; YouTube remains the full teaching
experience.

### Cadence per flagship

| Relative day | Asset | Destination |
| ---: | --- | --- |
| 0 | Flagship | YouTube + transcript page |
| +2 | Short A | YouTube Short |
| +3 | Clip A with professional framing | LinkedIn native video |
| +6 | Short B | YouTube Short |
| +7 | Clip B with professional framing | LinkedIn native video |
| +9 | Framework carousel | LinkedIn document |

Monthly result: two flagships, four Shorts, four LinkedIn native videos, and two
LinkedIn documents without creating six new research projects.

## 7. Attribution and learning

Use a distinct `utm_content` for each platform and derivative:

```text
utm_source=linkedin
utm_medium=organic_video
utm_campaign=copilot_studio_produccion
utm_content=vid001_short01
```

Track:

- YouTube Short retention and related-video clicks;
- flagship sessions originating from each derivative;
- LinkedIn video completion, saves, meaningful comments, and outbound clicks;
- checklist opt-ins and assessment starts attributed to the derivative;
- qualified conversations, without claiming causation from a single post.

## 8. Required quality gate

No derivative is publishable until:

- its source time range and transcript are recorded;
- the idea is complete and faithful to the flagship;
- Spanish captions are manually corrected;
- brand safe areas pass at 1080 × 1920 and a phone-size preview;
- music does not mask speech;
- no customer, tenant, notification, or secret is visible;
- YouTube Related video and LinkedIn UTM destinations work;
- Juan Pedro approves the final clip and the platform-specific copy.

## Sources checked on 21 August 2026

- [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5)
- [ClipsAI](https://github.com/ClipsAI/clipsai)
- [auto-editor](https://github.com/WyattBlue/auto-editor)
- [OpenClip](https://github.com/linzzzzzz/openclip)
- [FunClip](https://github.com/modelscope/FunClip)
- [LinkedIn Videos API](https://learn.microsoft.com/linkedin/marketing/community-management/shares/videos-api?view=li-lms-2026-08)
- [LinkedIn Posts API](https://learn.microsoft.com/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-08)
- [YouTube: add a related video to a Short](https://support.google.com/youtube/answer/14075157)
