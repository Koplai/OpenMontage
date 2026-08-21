# YouTube Content Engine — Juan Pedro Marquez

> Authoritative operating plan · Spanish first · Version 1.0 · 2026-08-21

## 1. The channel thesis

The channel is not a Microsoft news channel and not a collection of generic
tutorials. It is a field guide for people who must turn Microsoft AI products
into safe, useful, measurable business systems.

Every flagship video must answer five questions:

1. What real operational problem are we solving?
2. What does a poor implementation look like?
3. What can the viewer build, configure, test, or decide today?
4. What evidence shows that the result works?
5. What useful next asset continues the journey?

### Public positioning

Use:

> Arquitecto de soluciones cloud especializado en IA para empresas europeas.

Do not present Juan Pedro publicly as "Microsoft CSA", "Cloud Solution
Architect at Microsoft", or use Microsoft employment as a credential. Product
names and public Microsoft documentation can be discussed normally. Add an
educational-content disclaimer and avoid implying Microsoft endorsement.

### Brand and voice

- Navy `#0A1628`: authority, depth, backgrounds.
- Azure `#4A90E2`: explanation, diagrams, links, active states.
- Gold `#C4A35A`: evidence, decisions, premium accents.
- Satoshi: display typography.
- Inter: body and teleprompter.
- Space Mono: configuration, commands, evidence labels.
- Spanish voice: calm, precise, practical, never inflated.
- Approved closing line: **Claro. Directo. Con rigor.**
- Editorial rule: every important claim leads to a source, configuration,
  architecture, test, or observable result.

The visual source of truth remains
`videos/jp-youtube-channel-kit/CHANNEL-KIT-GUIDE.md`.

## 2. Audience and jobs to be done

### Primary audience

- Power Platform and Microsoft 365 administrators.
- Cloud and solution architects.
- Advanced makers moving agents into production.
- AI, security, governance, and transformation leaders.
- Spanish-speaking professionals preparing to lead Microsoft AI adoption.

### Recurring jobs

| Job | Viewer question | Content response |
| --- | --- | --- |
| Make a decision | Which Microsoft AI tool fits this scenario? | Decision framework plus worked case |
| Deploy safely | What must be controlled before production? | Configuration, test plan, and checklist |
| Explain value | How do I defend the investment? | Business case, measurable outcome, and risks |
| Operate at scale | How do I govern environments, agents, and cost? | Admin walkthrough and operating model |
| Learn a capability | Can I follow this without reading ten documents? | Feynman explanation, diagram, demo, retrieval prompt |
| Prepare for AB-731 | Can I turn the skills outline into practical leadership? | Original scenario-led course and templates |

## 3. Sustainable publishing cadence

### Launch sprint

- Monday, 24 August 2026: dry run and record `VID-001`.
- Thursday, 27 August 2026: publish `VID-001`.
- Week of 31 August: publish two derivatives and review 24-hour data.

### Standard monthly cadence

- **2 flagship videos** per month, 9–15 minutes each.
- **4 Shorts** per month: two purposeful extracts per flagship.
- **2 LinkedIn documents or posts** per month.
- **2 transcript/article pages** on jpmarquez.com.
- **1 new or improved lead magnet** per month, reused across related videos.
- **1 gated AB-731 lesson** per month after the first two flagship videos are
  stable.
- **1 live office hour** per month after the email/community base exists.

Do not increase long-form cadence until two consecutive months are delivered
without skipping technical QA, thumbnails, transcripts, or the 28-day review.
The derivative system exists to increase distribution without multiplying
research.

### Monthly operating rhythm

| Window | Human work | Agent work | Gate |
| --- | --- | --- | --- |
| 18–20 previous month | Add customer questions and strategic priorities | Refresh demand data, SERPs, product changes, and content gaps | DataForSEO job succeeded |
| 21 | Choose two flagship topics and one backup | Score topics and propose angles | Human approves topics |
| 22–25 | Provide field examples and risk constraints | Research pack, claims ledger, outline, CTA mapping | Sources verified |
| 26–28 | Approve story and demo outcome | Draft camera script, screen script, slides, tests | Demo reproducible |
| Week 1 | Record flagship A | Prepare assets and ingest sources | Recording checklist |
| Week 2 | Review and publish A | Edit, QC, captions, metadata, website page | Human final approval |
| Week 3 | Record flagship B | Same production path | Recording checklist |
| Week 4 | Publish B and review A | Derivatives, analytics, backlog update | 7-day learning logged |

Maintain one finished backup video and one researched backup topic. If a
Microsoft interface changes, publish the backup instead of rushing an invalid
demo.

## 4. Demand research without invented data

DataForSEO credentials are not currently configured. The first topic is a
provisional editorial choice based on official-product relevance, public
Spanish search-result gaps, existing jpmarquez.com authority, demo value, and
funnel fit. No volume, CPC, trend percentage, or difficulty is claimed.

### Mandatory monthly research gate

Run DataForSEO for Spain and Spanish against the seeds in
`research/dataforseo-keyword-seeds.csv`. Store the raw response unchanged, then
create a normalized table containing:

- keyword and normalized cluster;
- locale and location;
- current search volume and monthly history;
- keyword difficulty or competition metric with its source;
- CPC as commercial-intent context, not a revenue forecast;
- search intent;
- SERP features and top-ranking page types;
- related questions and adjacent terms;
- trend direction and observation date.

Also review:

- YouTube autocomplete and current Spanish results;
- Google and Bing result composition;
- official Microsoft release notes and documentation dates;
- jpmarquez.com Search Console queries once available;
- comments, community questions, client-safe field patterns, and assessment
  responses;
- competitor coverage quality, not just result count.

Archive each run under
`research/YYYY-MM/dataforseo-raw/` and never overwrite historical data.

### Topic score

Score each candidate out of 100:

| Dimension | Weight | Test |
| --- | ---: | --- |
| Demand evidence | 25 | Verified search, site, or community signal |
| Pain and urgency | 20 | Cost, risk, deadline, or blocked outcome |
| Authority fit | 15 | Can Juan Pedro add field-level judgment? |
| Practical proof | 15 | Can the viewer see a result or decision? |
| Funnel fit | 10 | Is there a genuinely useful next asset? |
| Strategic cluster | 10 | Does it strengthen a playlist or course? |
| Freshness | 5 | Is the timing relevant and source current? |

Hard blockers override the score: no verifiable demo, unsafe customer data,
unsupported product claim, unavailable lead magnet, or a topic that depends
only on a short-lived news spike.

## 5. Content architecture

### Playlists available from launch

1. **Copilot Studio: de demo a produccion**  
   Build, secure, test, deploy, and operate agents.
2. **Gobernanza y seguridad de IA**  
   DLP, identity, data, Purview, EU context, monitoring, and responsible AI.
3. **Microsoft Foundry y arquitectura de agentes**  
   Tool decisions, model architecture, evaluation, grounding, and operations.
4. **Liderazgo y ROI de IA — Ruta AB-731**  
   Business value, adoption, operating model, and original preparation
   scenarios.

Create a fifth playlist only when it has at least three planned videos. Use
viewer problems as the organizing principle; products remain discoverability
terms, not the whole information architecture.

### 90-day editorial map

| ID | Target | Flagship promise | Primary CTA | Playlist |
| --- | --- | --- | --- | --- |
| VID-001 | 27 Aug | Five production controls for a Copilot Studio agent | Production checklist | Copilot Studio |
| VID-002 | 10 Sep | Decide between Copilot Studio and Microsoft Foundry using one scenario | Decision matrix | Foundry |
| VID-003 | 24 Sep | Design identity and permissions without confusing sign-in with authorization | Identity worksheet | Governance |
| VID-004 | 8 Oct | Find the hidden operating costs of an AI agent before approval | Agent cost model | Leadership/ROI |
| VID-005 | 22 Oct | Build an evaluation set that catches unsafe and unsupported answers | Evaluation template | Copilot Studio |
| VID-006 | 5 Nov | Turn an AI idea into an AB-731-style transformation business case | Business-case canvas | AB-731 |
| VID-007 | 19 Nov | Design Power Platform environments for governed AI delivery | Environment map | Governance |

`VID-002` through `VID-007` remain provisional until the corresponding monthly
DataForSEO and freshness gate.

### Flagship episode pattern

1. **Cold open (0:00–0:30):** a specific failure, decision, or observable
   consequence.
2. **Promise (0:30–0:55):** what the viewer will be able to do.
3. **Mental model (0:55–2:00):** plain-language analogy and one diagram.
4. **Worked case (2:00–8:30):** real configuration or decision.
5. **Boundary test (8:30–10:00):** what fails, when not to use it, or a
   counterexample.
6. **Retrieval (10:00–10:30):** one question the viewer must answer.
7. **Decision/summary (10:30–11:30):** concise rule and evidence.
8. **Next asset (11:30–12:00):** contextual resource and next video.
9. **End-screen runway (last 20 seconds):** no critical content behind UI
   elements.

Use Feynman-style language, worked examples before abstraction, chunking,
signposting, dual coding, retrieval prompts, deliberate pauses, and vocal
contrast. Do not imitate or claim endorsement by a public speaker.

## 6. Funnel and monetization

### Funnel architecture

```text
Search / recommendation / LinkedIn
        ↓
Flagship video → playlist → next video
        ↓
Dedicated /es/videos/ page with chapters and transcript
        ↓
Context-specific PDF or template
        ↓
Consent-based five-email application sequence
        ↓
Free AB-731/community lesson or AI maturity assessment
        ↓
Existing shop product / workshop / qualified advisory conversation
```

The immediate business objective is not advertising revenue. It is trusted,
attributable demand. YouTube Partner Program revenue is a later layer.
YouTube currently documents the full ad-revenue threshold as 1,000 subscribers
plus either 4,000 valid public watch hours in 12 months or 10 million valid
public Shorts views in 90 days, subject to its eligibility and policy review.
Re-check the official requirement before making a public claim.

### Website surfaces to build

The public sitemap currently exposes Spanish resources, assessment, shop, and
blog content, but not a dedicated Spanish video library or AB-731 course
landing page. Add:

- `/es/videos/`: searchable topic hub.
- `/es/videos/<slug>/`: embedded video, transcript, chapters, sources, resource
  form, and related videos.
- `/es/curso/ab-731/`: original course curriculum, diagnostic, progress, and
  enrollment.
- `/es/recursos/<asset>/`: one conversion-focused page per flagship resource.
- `VideoObject`, `BreadcrumbList`, and transcript markup where appropriate.
- UTM capture plus consent and source attribution in the CRM/email system.

Do not publish a video CTA until its landing page works in a private browser,
the email is delivered, and the download can be opened on mobile.

### Five-email application sequence

| Day | Purpose | Content |
| ---: | --- | --- |
| 0 | Deliver | Resource, one-sentence promise, reply question |
| 1 | Apply | Small task using the checklist or template |
| 3 | Diagnose | Common failure and self-assessment |
| 6 | Extend | Related video or AB-731 lesson |
| 10 | Convert | Assessment, product, workshop, or advisory next step |

Every email must teach something even if the reader never purchases. Maintain
GDPR-compatible consent, purpose limitation, unsubscribe, and data-retention
rules.

### Monetization ladder

1. Free videos, transcripts, diagrams, and focused resources.
2. Free registration for the AB-731 learning path/community.
3. Existing downloadable implementation products in the shop.
4. Paid implementation workshop or cohort validated by audience demand.
5. Qualified advisory or speaking engagements.
6. YPP ads, memberships, or sponsorships only when they fit the audience and
   disclosure requirements.

Do not introduce a paid product solely because it completes a funnel diagram.
Use resource conversion, assessment demand, replies, and workshop interest to
validate it first.

## 7. Original AB-731 learning path

The official credential is **Microsoft Certified: AI Transformation Leader**.
The course is **AB-731T00-A — Drive AI transformation in your organization**.
The official study guide lists three broad skill areas as of 22 July 2026:

- identify business value from generative AI, 35–40%;
- identify Microsoft AI apps and Foundry Tools, 35–40%;
- develop implementation and adoption strategies, 20–25%.

The learning path below is original, scenario-led material. It must not copy
Microsoft courseware, exam questions, or protected content.

| Module | Outcome | Practical artifact | Public YouTube bridge |
| --- | --- | --- | --- |
| 0. Diagnostic | Establish current leadership and AI maturity | Baseline scorecard | Channel trailer / route overview |
| 1. Value discovery | Convert a business problem into an AI opportunity | Opportunity brief | VID-006 |
| 2. Value and cost | Defend value, cost, uncertainty, and risk | Business-case canvas | VID-004 |
| 3. Microsoft AI landscape | Decide among M365 Copilot, Copilot Studio, and Foundry | Decision matrix | VID-002 |
| 4. Grounding and quality | Explain grounding, data quality, and evaluation | Evidence map | VID-005 |
| 5. Responsible and secure AI | Define governance, ownership, and controls | Governance charter | VID-001 / VID-003 |
| 6. Adoption system | Design champions, learning, communication, and feedback | Adoption sprint | Future flagship |
| 7. Operating model | Establish portfolio, environments, metrics, and lifecycle | 90-day operating model | VID-007 |
| 8. Capstone | Present an AI transformation recommendation | Executive transformation plan | Private review session |

Each module uses a case, plain-language model, decision, worked artifact,
retrieval quiz, application task, and source list. Certification preparation
is an outcome; exam-content reproduction is not.

## 8. Human and agent operating model

### Human-only decisions

- Public positioning and personal stories.
- Monthly topic and angle approval.
- Technical-demo approval after a successful dry run.
- Script claims with employment, customer, legal, or policy implications.
- Final cut and thumbnail approval.
- Publish, correction, takedown, and commercial-offer decisions.

### Agent responsibilities

| Agent | Receives | Produces | Cannot do |
| --- | --- | --- | --- |
| Demand researcher | Seeds, Search Console, product updates | Scored topic backlog and evidence pack | Invent metrics |
| Content strategist | Research pack, clusters, funnel map | Monthly slate, episode promise, CTA | Approve topic |
| Technical verifier | Claims, docs, demo tenant | Claims ledger, working demo, failure states | Use customer data |
| Showrunner | Approved angle and demo | Camera script, screen script, chapters, cues | Hide uncertainty |
| Visual producer | Script and brand kit | Slides, diagrams, thumbnail variants, overlays | Break safe areas |
| OpenMontage editor | Original recordings and manifest | Rough cut, captions, audio mix, final masters | Modify originals |
| Quality controller | Cut, sources, manifest, landing page | Blocking/non-blocking report | Waive text overflow |
| YouTube publisher | Approved package | Private upload, metadata, chapters, cards, checks | Make public |
| Web publisher | Transcript and resource | Video page, schema, PDF delivery | Publish broken form |
| Growth analyst | 24h/7d/28d data | Learning memo and backlog changes | Claim causation from one video |

No publishing agent can move a video from private to public without recorded
human approval.

## 9. Storage and handoff contract

Large original media does not belong in Git.

```text
OneDrive/
└── 2 - Areas/YouTube/
    ├── 00_Strategy/
    ├── 01_Content-Calendar/
    ├── 02_Brand-Kit/
    ├── 03_Lead-Magnets/
    ├── 04_Course-AB731/
    └── Videos/
        └── VID-001-copilot-studio-produccion/
            ├── 00_Control/
            ├── 01_Research/
            ├── 02_Script/
            ├── 03_Demo/
            ├── 04_Recordings/INBOX/
            ├── 05_Assets/
            ├── 06_Edit/
            ├── 07_Publish/
            └── 08_Analytics/
```

Capture naming:

- `VID-001_A_CAM_TAKE01.mp4`
- `VID-001_B_SCREEN_TAKE01.mp4`
- `VID-001_C_AUDIO_TAKE01.wav`
- `VID-001_D_ROOMTONE.wav`

The editing agent copies or links immutable originals into the OpenMontage
project workspace, creates a declared `hybrid` pipeline under
`projects/vid-001-copilot-studio-produccion`, and writes outputs back to
`06_Edit` and `07_Publish`. It never edits the source files in place.

The repository stores manifests, scripts, source designs, automation, and QA
rules. OneDrive stores high-volume recordings and delivery masters. A project
is not archived until the final master, captions, transcript, thumbnail,
description, resource, sources, manifest, and analytics snapshot exist.

## 10. Production gates

### Topic gate

- Data source and observation date recorded.
- Promise is specific and practical.
- Search intent and audience job match.
- Demo and resource are feasible.
- No conflict with public-positioning rules.

### Script and demo gate

- Claims ledger links every material product statement to an official source.
- Demo succeeds twice and has a prepared failure state.
- Camera and screen scripts are separate.
- Slide and screen-share cues are embedded but not spoken.
- Word count matches the target duration.
- Uncertainty and product-version date are explicit.

### Recording gate

- No sensitive tenant, customer, email, chat, or notification data.
- Teleprompter, framing, lighting, focus, and white balance locked.
- Screen UI is readable on a phone-sized preview.
- Audio is clean, unclipped, and backed up.
- Room tone and sync cue captured.

### Edit gate

- OpenMontage `hybrid` pipeline declared.
- Story is understandable without decorative motion.
- Brand kit and safe areas respected.
- Text overflow is always blocking.
- Captions are synchronized and corrected.
- Loudness, peaks, silence, black frames, frame rate, and encoding validated.
- Sources and screenshots are licensed or original.
- Twenty seconds remain usable for the end screen.

### Publish gate

- Landing page, consent, delivery email, download, and UTM tested.
- Title and thumbnail promise match the actual video.
- Chapters start at `00:00`, include at least three timestamps, and each chapter
  lasts at least ten seconds.
- Description contains sources, disclaimer, chapters, CTA, and relevant
  language.
- Captions, playlist, cards, end screen, audience setting, and visibility are
  checked.
- Upload remains private until human approval.

### Post-publish gate

- 24 hours: packaging and technical issues.
- 7 days: hook, retention, chapter use, comments, and resource conversion.
- 28 days: search terms, long-tail discovery, qualified leads, and topic-cluster
  contribution.
- Corrections are logged; material errors receive a pinned correction,
  description update, edit, or takedown according to severity.

## 11. Measurement

Use targets as operating hypotheses, not external benchmarks:

| Layer | Metric | Initial operating target |
| --- | --- | --- |
| Packaging | Impressions CTR | 4–6%, then learn by traffic source |
| Hook | Retention at 30 seconds | At least 70% |
| Value | Average percentage viewed | At least 40% on flagship videos |
| Journey | End-screen element CTR | Improve month over month |
| Intent | Resource clicks / unique viewers | Establish baseline in first three videos |
| Conversion | Resource opt-ins / landing visits | Establish baseline before setting target |
| Qualification | Assessment starts and relevant replies | Track by campaign and video |
| Business | Qualified conversations and product revenue | Attribute with UTM and CRM source |

Never compare unlike traffic sources or diagnose causation from a single
upload. Record thumbnail/title changes with timestamps so analytics remain
interpretable.

## 12. Missing elements now included

The original request covered production and publishing. A durable system also
needs:

- public positioning and employer/endorsement boundaries;
- GDPR consent and email data retention;
- source freshness and a correction policy;
- accessibility, captions, readable UI, and color contrast;
- media licensing and provenance;
- immutable originals, backup, and archive rules;
- a backup episode for product UI changes;
- owner succession and continuity;
- landing-page and email-delivery QA before the CTA;
- analytics windows and attribution;
- community moderation and response rhythm;
- a human approval boundary before public publishing.

## 13. Monday, 24 August 2026

1. Open `content-engine.html`.
2. Confirm the resource URL and email delivery exist; if not, build them before
   recording the CTA.
3. Open `video-001/teleprompter.html` on the Elgato display.
4. Execute the five demo tests twice and save the evidence.
5. Record camera, screen, audio, and room tone using the manifest names.
6. Move the recordings to `04_Recordings/INBOX`.
7. Trigger the editing workflow and review the rough cut; do not publish.

The first video package is in `video-001/`.

## Official references

- [Copilot Studio security and governance](https://learn.microsoft.com/microsoft-copilot-studio/security-and-governance)
- [Copilot Studio data policies](https://learn.microsoft.com/microsoft-copilot-studio/admin-data-loss-prevention)
- [Copilot Studio ALM guidance](https://learn.microsoft.com/microsoft-copilot-studio/guidance/alm)
- [AB-731 study guide](https://learn.microsoft.com/credentials/certifications/resources/study-guides/ab-731)
- [AB-731T00 course](https://learn.microsoft.com/training/courses/ab-731t00)
- [AI Transformation Leader credential](https://learn.microsoft.com/credentials/certifications/ai-transformation-leader/)
- [YouTube chapters](https://support.google.com/youtube/answer/9884579)
- [YouTube Partner Program](https://support.google.com/youtube/answer/72851)
- [YouTube custom thumbnails](https://support.google.com/youtube/answer/72431)
- [YouTube end screens](https://support.google.com/youtube/answer/6388789)

