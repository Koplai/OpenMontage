# OpenMontage production-readiness audit

**Audit date:** 15 September 2026

**Audited source:** [`cd9f3c1f03368be87b140af494914b8ee4e3c7a4`](https://github.com/calesthio/OpenMontage/tree/cd9f3c1f03368be87b140af494914b8ee4e3c7a4)

**Intended first deployment:** A private, single-user content-production workstation.

**Change scope:** Assessment and recommendations, not implementation or deployment.

**Implementation update, 16 September 2026:** hardening is underway on the
development branch. This report remains the historical baseline; see
[production operations](../PRODUCTION.md) for the new executable contracts,
installation, and recovery procedures. Implementation is not by itself a
production certification.

## Decision

**Keep OpenMontage and harden its execution contracts. Do not rewrite the studio or add more generation providers first.**

The project already has a useful content-production architecture: an AI coding
agent follows pipeline manifests and director instructions, Python tools perform
bounded operations, JSON artifacts and checkpoints preserve progress, and Backlot
provides a local review board. FFmpeg, Remotion, and HyperFrames are complementary
rendering integrations, not missing features to rebuild.

However, **this snapshot is not ready for unattended paid production or public
multi-user deployment**. Passing tests coexist with confirmed defects that can
change the approved renderer, omit audio/captions, shorten the finished video,
substitute assets, and mix concurrent render jobs. A supervised, private pilot
with explicit output inspection is a reasonable starting point, not a
production certification.

**First priority:** connect approved paid execution to a transactional budget
ledger and recoverable remote-job records. Then make render contracts and
passing final review enforceable. The detailed findings are C1-C9 and R1-R9;
adding another provider does not close these gaps.

| Operating mode | Assessment |
| --- | --- |
| Private, supervised content experiments | Viable with the documented limitations and manual review |
| Repeatable content delivery without technical supervision | Not ready; close execution and acceptance defects first |
| Unattended paid generation or parallel batch production | Not ready; spending, recovery, and per-job isolation must be enforced |
| Public service accepting projects, source code, or uploads | Not ready; additional authentication, isolation, and operational controls are required |

### The product to aim for

For an individual creator, the useful outcome is a repeatable workflow from a
brief or owned source recording to an approved, publishable content package:
video, captions, thumbnail, description, source/rights record, and actual cost.
Reliability of that workflow matters more than the number of providers.

Start with technical screen demos and short explainers; add repurposing and
English/Spanish variants after a representative source-footage run succeeds.
These are recommended acceptance scenarios, not an assertion that those paths
were all rendered in this audit. Retain human approval of script, assets, and
publication. Choose the renderer for each brief explicitly rather than
silently imposing a default.

The actual manifest inventory contains **13 pipelines: six declare
`production`, seven declare `beta`**. These are self-declared metadata, not
independent readiness measurements. In particular, documentary montage and the
smoke manifest exist beyond the abbreviated guide tables.

## Evidence and boundaries

This is a repository-wide readiness assessment with deeper tracing and
reproductions of critical runtime, rendering, export, and board paths. It is
not an exhaustive live certification of every provider, model, platform, or
vendored skill.

The audited tree contains 174 tracked files under `tools/`, 20 under `lib/`,
41 under `remotion-composer/`, 11 under `backlot/`, 126 under `tests/`, and 34
under `schemas/`. These are file counts, not coverage percentages.

| Check | Observed result | What it does not establish |
| --- | --- | --- |
| Offline automated tests, excluding `tests/qa` and `tests/eval` | **1,829 passed, 9 skipped, 3 xfailed; one subtest passed** | Live provider reliability or visual quality |
| Full CI-equivalent `pytest tests/` follow-up | **1,829 passed, 11 skipped, 3 xfailed; one subtest passed** | Legacy printed checks are not all enforceable tests; optional browser/runtime checks remain skipped |
| Composer `tsc --noEmit` after locked dependency installation | Passed | Correct runtime props, timing, or rendered appearance |
| Python compilation across `lib tools backlot schemas styles` | Passed | Semantic correctness |
| Python `pip check` | No broken requirements | Reproducible future resolution |
| Existing zero-key eight-stage E2E diagnostic | **38 checks passed, zero failed** | Real approvals or real provider output; assets and approvals are synthetic |
| Independent final-file probe and full decode | H.264, 1920x1080, 30 fps, AAC, **60.021029 seconds**, full decode without errors | Content quality, caption accuracy, or brand fit |
| Production npm dependency advisory scan | **Three affected packages: two high, one moderate** | Exploit reachability in this application |
| Installed Python environment advisory scan | No findings outside bootstrap `pip`; see dependency section | All optional/GPU dependencies or a future install |
| Wheel inspection | Build succeeds, but required non-Python resources are absent | A usable standalone package |
| Optional HyperFrames QA | Two tests skipped unless explicitly enabled | Actual HyperFrames browser rendering |

The local audit used Python 3.12 and Node 22.19.0. Dependencies were restored
into a worktree-local virtual environment and from the existing npm lockfile
after missing-dependency errors. npm installation used `--ignore-scripts`.
There were no paid generation calls, model downloads, deployments, secret
configuration changes, or real publishing operations.

Skipped coverage included a missing golden fixture, missing comparison footage,
optional Backlot browser coverage, optional live documentation checks, and the
network-guard live-test example. The three expected failures concern archive,
Wikimedia, and Pond5 transport-error propagation. An expected failure is known
unresolved behavior, not a passing implementation.

The Backlot browser module specifically skips when `playwright.sync_api` is
missing. Running it also needs Playwright Chromium and FFmpeg; no
`pytest-playwright` plugin is needed. Its fixture helper replaces
`.backlot/screenshot-stage`, mutates the projects-root environment during import,
and uses fixed port 4897. Isolate staging into a dedicated temporary directory
and verify port ownership before enabling this check; simply pre-setting the
projects-root environment variable is insufficient. Browser installation and
execution were not performed.

The baseline's upstream Python CI was green:
[baseline run](https://github.com/calesthio/OpenMontage/actions/runs/32590539127).
Current upstream `08e2151fa02de28a5d6a312b3d575692bf147ad7` was only one
README showcase commit ahead and also had
[green Python CI](https://github.com/calesthio/OpenMontage/actions/runs/34012989170).
Updating to that commit would not fix the code findings below.

### Priority and evidence vocabulary

- **P1:** A blocker for the affected production workflow: lost content,
  misleading acceptance, uncontrolled consequential execution, or unsafe
  concurrency.
- **P2:** A reliability, recovery, operational, or integration gap that needs a
  release gate or documented restriction.
- **P3:** A narrower compatibility or usability defect.
- **Runtime:** Exercised with synthetic local inputs.
- **Controlled:** Exercised with a process/HTTP/DOM double; not a live external service.
- **Static:** Verified source or contract behavior; runtime limitations are stated.

Priorities describe production impact, not vulnerability-scanner severity.
No numeric readiness score or estimated percentage of development time saved
is asserted.

## Rendering and deliverable findings

All source locations below refer to the audited commit, not to future fixes.

| ID | Priority | Finding and evidence | Smallest correct direction |
| --- | --- | --- | --- |
| R1 | P1 | A locked Remotion render can execute FFmpeg when Remotion is unavailable. Controlled reproduction returned success while the declared runtime remained Remotion. `tools/video/video_compose.py:1375-1400,1630-1722,2517-2519` | Fail with an unavailable-runtime blocker; record executed runtime separately from requested runtime |
| R2 | P1 | The same cuts mean different things across engines. Two distinct clips with source ranges `[0,3]` become six sequential seconds in FFmpeg/cinematic, three overlapping seconds in HyperFrames, and overlapping sequences with four seconds including padding in Explainer. Speed is also not consistently applied. `video_compose.py:512-550,766-825`; `hyperframes_compose.py:1009-1012,1268-1273,1311-1320`; `Explainer.tsx:750-762,850-856`; `Root.tsx:131-141` | Separate source trims from timeline position/duration and adapt every engine explicitly; use the existing cinematic sequential contract as prior art |
| R3 | P1 | High-level HyperFrames rendering drops supplied `audio_path` and `subtitle_path`. Remotion does not convert the top-level subtitle file into its captions input. Review can claim subtitles exist merely because the source file exists. Controlled argument capture plus source proof. `video_compose.py:1640-1689,1815-1850,2605-2635`; `Explainer.tsx:875-889` | Forward/convert approved inputs or reject unsupported combinations; verify applied output rather than source existence |
| R4 | P1 | Presenter routing sends generic `cuts`, not `TalkingHead.videoSrc`; registration has an empty video default and fixed 300-second duration. Controlled props capture; actual browser failure was not tested. `video_compose.py:738-743,1991-2007`; `Root.tsx:187-203`; `TalkingHead.tsx:313-333` | Add a real presenter props/duration adapter or explicitly block this route |
| R5 | P1 | Parallel jobs in one output directory share `.remotion_props.json` and FFmpeg `.compose_tmp` names. A deterministic interleaving showed job B deleting job A's props. `video_compose.py:505-506,520,639-649,2031,2047-2048,2114-2119` | Use invocation-scoped work directories and publish only final outputs atomically |
| R6 | P1 | A four-second video with a 1.5-second external audio mix produced a **1.5-second** FFmpeg result, still marked successful with a passing review. Real local render. `video_compose.py:692-697` | Pad the audio or reject the mismatch; preserve the approved visual duration, reusing the padded-mux semantics at `395-436` |
| R7 | P1 | A half-second synthetic video returned `success=True` while review said `revise` and `recommended_action=re_render`. Callers downgrade only `fail`. `video_compose.py:2654-2679,1101,1740,1872,1932` | Distinguish file-production success from deliverable acceptance; enforce acceptable review at the delivery boundary |
| R8 | P1 | HyperFrames flattens source basenames and treats equal file sizes as identical. Distinct same-size `one/clip.mp4` and `two/clip.mp4` both referenced the first clip's bytes. Narration/music use the same pattern. `hyperframes_compose.py:1033-1041,1066-1070,1086-1090` | Stage by collision-resistant source/content identity; do not use size as a content comparison |
| R9 | P1 | An unresolved required HyperFrames asset became a successful `Scene 1` placeholder; its missing reference disappeared from generated HTML. Missing narration can also be skipped. Controlled scaffold reproduction. `hyperframes_compose.py:1026-1044,1057-1065,1322-1343` | Block missing required inputs before scaffolding; placeholder mode must be explicit and non-deliverable |
| R10 | P2 | FFmpeg ignored nonexistent explicit audio/subtitle files but reported `has_mixed_audio=True` and `has_subtitles=True`. Real local reproduction. `video_compose.py:656-668,692-713` | Reject missing explicitly supplied paths and derive flags from completed operations |
| R11 | P2 | Canonical `subtitles.style="word-by-word"` can reach a resolver expecting `.items()` and raise `AttributeError`. `schemas/artifacts/edit_decisions.schema.json:156-171`; `video_compose.py:2896-2902` | Match the schema's string style contract instead of assuming a dictionary |
| R12 | P2 | Direct render/export paths can accept stale or invalid files. An existing 18-byte invalid output plus a mocked zero renderer exit returned success; export accepted the invalid file too. `video_compose.py:2121-2139`; `hyperframes_compose.py:853-875,950-974`; `tools/publishers/export_bundle.py:158-161,187-190,267-284` | Prove freshness, probe/decode media, and tie exports to accepted render identity |
| R13 | P2 | Re-exporting without a previous thumbnail, subtitles, tags, or chapters leaves those old files in the bundle. Writes precede final publish-log validation. Temporary-directory reproduction. `export_bundle.py:179-199,227-249,267-276` | Build a complete replacement bundle, validate it, then atomically publish it |
| R14 | P2 | HyperFrames timeout handling can mask the real error by concatenating byte-valued `TimeoutExpired.stderr` with a string. Controlled exception reproduction. `hyperframes_compose.py:1379-1387` | Normalize stderr and preserve timeout diagnostics |
| R15 | P2 | HyperFrames converts an explicit music volume of zero into `0.15`. Helper reproduction. `hyperframes_compose.py:1090-1095` | Default only on absent/null values; retain an intentional mute |
| R16 | P3 | Apostrophes in output-directory names break FFmpeg concat path parsing. Real reproduction under `quote's-dir`. `video_compose.py:639-643` | Escape for the concat-file syntax, not just shell syntax |

R12 establishes a weak acceptance condition, not that an upstream renderer
normally returns exit zero on failure.

**R7 was also traced through the downstream boundaries.** Actual-module probes
accepted a completed compose checkpoint containing a schema-valid
`revise/re_render` review, exported its existing byte fixture, and allowed
publish progression to `awaiting_human`. Omitting `final_review` also allowed
compose completion. See `lib/checkpoint.py:124-157,298-341` and
`tools/publishers/export_bundle.py:71-113,158-189`. The export probe tested
packaging enforcement, not valid media; R7's separate real render establishes
the video behavior.

The schema and reviewer instructions explicitly prohibit presenting `revise`
as complete (`schemas/artifacts/final_review.schema.json:5,14-17`;
`skills/meta/reviewer.md:300-318`). An agent that obeys those instructions can
still reject the output, but the executable delivery boundary does not enforce
them. Require an output-bound passing review for final delivery; keep explicit
draft/diagnostic export separate.

### Why the passing render is insufficient

The successful 60-second E2E uses compatible synthetic inputs and explicit
approval booleans. R2, R3, R5, R6, and R8 exercise different conditions: source
trims beginning at zero, runtime-specific input forwarding, concurrent jobs,
audio shorter than video, and duplicate filenames. A happy-path render does
not contradict those failures.

## Backlot and integration boundaries

| ID | Priority | Finding and evidence | Remediation |
| --- | --- | --- | --- |
| B1 | P2 | Malformed nested checkpoint/state shapes produce HTTP 500 despite intended graceful loading. Examples: `metadata: ["bad"]`, `artifacts: ["bad"]`, mixed string/numeric scene times. Initial UI errors are labeled `PROJECT NOT FOUND`. In-process HTTP reproduction. `backlot/state.py:163-173,246-265,403-499,588-614`; `server.py:179-182`; `ui/board.js:1133-1137` | Validate each section, show explicit damaged-state diagnostics, preserve readable portions |
| B2 | P2 | Starting without the projects root permanently stops watching; cached state can remain stale. SSE reconnect `hello`/heartbeat do not reconcile state, and elapsed time alone does not update LIVE/STALLED state. Filesystem/cache and JS-double evidence. `server.py:85-113,132-145,193-207`; `ui/lib.js:66-80`; `state.py:629-655` | Recover root creation, refresh on reconnect, add bounded cache age/time-based refresh |
| B3 | P2 | Refresh clears `app.innerHTML` before reading previous video playback state; updates can reset an active review. DOM-double reproduction. `ui/board.js:819-845,1054-1087` | Capture state before replacement or preserve video elements |
| B4 | P2 | CLI health discovery accepts any HTTP 200 on the expected port, including another app/workspace. Static evidence. `backlot/__main__.py:30-35,55-76` | Check application identity and the intended projects-root identity |
| B5 | P2 | Root containment is inconsistent for symlinks: a linked project exposed outside synthetic bytes; a canonical artifact symlink exposed outside JSON, although direct media access to an inner escaping symlink returned 403. `server.py:271-282,310-319`; `state.py:97-115,246-255` | Apply one resolved-root policy to enumeration, canonical reads, and media |

**B5 requires imported/untrusted symlinks or deliberately linked directories.**
It is not an unconditional remote-file-read finding on a clean private
workstation. Do not generalize a controlled filesystem reproduction into a
demonstrated browser exploit.

Standard Backlot startup correctly binds to `127.0.0.1`
(`backlot/__main__.py:82-85`). It has no implemented multi-user authentication,
project authorization, or Host validation boundary. Authored HTML can be served
on the board origin, and source compositions execute HTML/JavaScript. A
non-loopback Host was accepted in a synthetic request, but DNS rebinding and
browser script exploits were not attempted.

Before accepting untrusted/public submissions, use authenticated access,
project ownership checks, a distinct untrusted-media origin, appropriate content
policies, isolated job processes/containers, restricted filesystem/environment,
egress control, quotas, and abuse limits. A reverse proxy alone does not isolate
executable compositions. These are future service requirements, not a reason
to replace trusted local authoring with a large platform today.

## Installation, CI, dependencies, and commercial delivery

### E1 - P1: Dependency advisories are outside the existing CI gate

`npm audit --omit=dev` found these locked packages:

| Package | Locked version | Scanner severity | Verified advisory examples |
| --- | --- | --- | --- |
| `fast-uri` | 3.1.5 | High | [GHSA-5jgf-p345-68v8](https://github.com/advisories/GHSA-5jgf-p345-68v8), [GHSA-f65p-4m7j-42xc](https://github.com/advisories/GHSA-f65p-4m7j-42xc); scanner identifies fixes at 3.1.6 |
| `browserslist` | 4.28.4 | High | [GHSA-c83g-rgw3-j3cx](https://github.com/advisories/GHSA-c83g-rgw3-j3cx), [GHSA-73wf-gq98-2v4g](https://github.com/advisories/GHSA-73wf-gq98-2v4g) |
| `baseline-browser-mapping` | 2.10.40 | Moderate | [GHSA-w5vr-8v7q-w6rv](https://github.com/advisories/GHSA-w5vr-8v7q-w6rv); scanner identifies fixes at 2.11.0 |

The dependency chain includes Remotion CLI -> bundler -> webpack ->
browserslist; `fast-uri` is both direct and used through webpack/schema-utils/Ajv.
They are build/render dependencies, not proof of an exploitable internet-facing
application endpoint. Review patched resolutions, update the lockfile, and
repeat type and actual-render checks; do not use a forced major-version upgrade.

The Python scanner inspected 52 installed packages. Only the environment's
bootstrap **pip 23.2.1** was flagged: 14 raw findings representing **seven
unique advisory IDs** because the feed repeated records. This is an environment
bootstrap finding, not 14 vulnerable application libraries. Upgrade the
installer in the reproducible setup. No vulnerabilities were reported for the
other resolved Python packages in this scan; optional/GPU/model environments
were not installed or audited.

### E2 - P2: CI does not validate the full shipped runtime

`.github/workflows/ci.yml` runs one Ubuntu/Python 3.11 job. It installs FFmpeg
and Python development dependencies, runs `make lint`, and runs pytest.
`make lint` compiles only four files. There is no Node installation/typecheck,
browser smoke test, dependency-advisory gate, packaging-resource check, or
macOS/Windows matrix in that workflow.

Add a small reproducible merge gate: Python contracts/logic, full source
compilation, locked npm install and TypeScript, one offline render with
ffprobe/full-decode assertions, Backlot browser smoke, and dependency scanning.
Test the Python version actually recommended for users. Broader OS coverage
can follow the initial supported workstation platform.

### E3 - P2: Legacy QA scripts can print failures without failing CI

Five files, `tests/qa/test_04_audio_mix.py` through
`test_08_end_to_end.py`, have no pytest test functions or assert statements.
They execute their diagnostic work at module import.

In the E2E script, `check()` increments a global failure counter and prints
`[FAIL]`, but returns normally; the script has no `sys.exit` based on that
counter (`test_08_end_to_end.py:46-56,649-654`). An isolated call with a false
condition reproduced that non-enforcing behavior. The actual E2E run in this
audit had zero such failures.

Convert the checks into real test cases or make the standalone diagnostic
exit nonzero when any check fails. Avoid render work during collection.
The socket guard in `tests/conftest.py` is valuable, but its autouse fixture
is not a subprocess sandbox and does not cover collection-time code.

### E4 - P2: Installation is not reproducibly pinned

Python requirements mostly specify only lower bounds; there is no Python
lockfile. `setup.py` duplicates only a subset of `requirements.txt`.
The normal setup uses `npm install` rather than the existing npm lockfile's
deterministic install path. HyperFrames is invoked as unversioned
`npx --yes hyperframes`, including availability paths that may fetch/execute it.

Pin a tested Python/Node/FFmpeg/runtime combination and resolved dependencies.
Keep optional provider/model environments separate. HyperFrames discovery
should distinguish passive inspection from an explicitly requested install.
The README's Node 18 minimum is not sufficient for the advertised HyperFrames
path, which needs Node 22 or newer.

For an OpenBao-managed installation, inject credentials into a trusted process
environment; do not copy credentials into the repository or generated projects.
The existing setup creates an empty `.env` template; do not confuse that
convenience path with centralized secret lifecycle management.

### E5 - P2: The built wheel is not a standalone installation

A real wheel build produced `openmontage-0.1.0-py3-none-any.whl` with 302
entries, including 102 test files, but:

- No `pipeline_defs/`, `skills/`, `config.yaml`, or renderer workspace.
- No JSON schema files.
- No Backlot UI resources.
- `setup.py` omits NumPy, Google Auth, FastAPI, Uvicorn, and Watchfiles from the
  dependencies declared by the source-checkout requirements.

This does not invalidate the documented clone-and-setup route. It does mean
that successful wheel construction is not packaging readiness. Either explicitly
support only a reproducible source checkout, or package runtime data and test
an installed artifact outside the repository.

### E6 - P2: Recovery needs the production workspace, not only Git

`projects/` is ignored as regenerable, but it contains the actual checkpoints,
approved/generated assets, decision history, and deliverables. Regenerating
paid assets can cost money and need not reproduce the same output. Source
control is not a backup of a production.

Define project retention, disk-space limits, backup/restore, and a interrupted-run
recovery procedure before relying on unattended work. No backup/restore drill,
power-loss test, or long-running resource benchmark was performed in this audit.

### E7 - P2: Rights metadata is optional at the canonical asset boundary

`schemas/artifacts/asset_manifest.schema.json:14-36` permits an asset without
`license` or `original_url`; a minimal stock-video asset without either field
validated successfully. Some providers and director instructions impose
additional rules, but schema validity alone does not establish commercial rights.

Before publication, require source provenance, license/attribution where
applicable, and appropriate permissions for voices, likenesses, footage, music,
and brand assets. Preserve this evidence in the exported package. The code
license and the media's usage rights are separate.

### E8 - P2: Commercial runtime terms require an explicit decision

OpenMontage's [AGPL-3.0 license](https://github.com/calesthio/OpenMontage/blob/cd9f3c1/LICENSE)
permits commercial use. Merely rendering a video does not automatically put that
video under AGPL; incorporated program material and independently licensed
assets need separate consideration. Distribution or offering a modified covered
program over a network creates different compliance questions from private use.

The locked Remotion version is **4.0.484**. Its
[exact-version license](https://github.com/remotion-dev/remotion/blob/v4.0.484/LICENSE.md)
has free-use categories including individuals and for-profit organizations with
up to three employees, plus qualifying nonprofits. A single operator inside a
larger company is not automatically eligible. Company-license and redistribution
terms need review for the actual entity/use.

[HyperFrames](https://github.com/heygen-com/hyperframes) is
[Apache-2.0](https://github.com/heygen-com/hyperframes/blob/main/LICENSE);
public npm metadata reported 0.8.40 during this audit. That is a current license
observation, not a pinned-runtime or transitive-asset compliance guarantee.

This is a technical compliance assessment, not a legal opinion.

### E9 - P2: Release and provenance controls are incomplete

No official GitHub releases were returned, and the repository had no published
security-policy URL. Install only from the verified source repository.
[Issue #626](https://github.com/calesthio/OpenMontage/issues/626) reports
unofficial lookalike installers; this audit did not download or execute them
and does not independently attest to their contents.

A production source release should identify the supported commit, locked
dependencies, supported operating system, known limitations, regression evidence,
and rollback procedure. A fake third-party installer is not a shortcut to that
work.

## Core execution, spending, and persistence

These findings were reproduced with actual local modules after dependency
restoration, using temporary projects, synthetic inputs, and fake transports.
They do not rely only on comments or an upstream issue description.

| ID | Priority | Finding and evidence | Required correction |
| --- | --- | --- | --- |
| C1 | P1 | Paid execution is not structurally connected to project approval/reservation. Real provider methods reached fake submission transports without a tracker or approval. The BaseTool wrapper emits events, not budget enforcement. `tools/base_tool.py:164-195,230-235`; `tools/graphics/openai_image.py:128-146`; `lib/config_model.py:74-85` | Add a project-bound approved-execution boundary; retain creative orchestration in instructions |
| C2 | P1 | Stale tracker instances bypass caps and overwrite entries: two instances each reserved $0.80 against a $1 cap, while only $0.80 remained durable. `tools/cost_tracker.py:123-156,487-507` | Serialize the complete reload/check/reserve/write transaction, using a process-safe lock or transactional store |
| C3 | P1 | Amount and state validation are insufficient: negative reservations increase available budget; NaN is accepted; refunding a reconciled $0.80 entry erases recorded spend. Actual ledger probes. `cost_tracker.py:101-178` | Require finite nonnegative amounts and valid idempotent transitions; completed spend cannot become an unspent refund |
| C4 | P1 | Kling retries ambiguous paid POSTs: a fake accepted submission followed by `ReadTimeout` caused **three POSTs** in one invocation. `tools/_kling/client.py:53-74,137-156`; `tools/video/kling_official_video.py:225-239` | Separate safe read retries from ambiguous submissions; use documented provider idempotency or recover the original task |
| C5 | P1 | Failure after generation loses job/cost information. Fake successful OpenAI-image generation followed by write failure, and completed Sora generation followed by download failure, returned zero-cost failure; retry generated again. Sora discarded its remote task ID. `openai_image.py:144-180`; `sora_video.py:180-208`; `kling_official_video.py:241-284`; `base_tool.py:386-390` | Persist submission IDs immediately; separate generation from delivery recovery; retain known or uncertain spend instead of declaring zero |
| C6 | P1 | Selectors execute unapproved or incompatible substitutions. Controlled probes executed a higher-scored provider instead of an explicit preference, text-only video for reference/edit operations, and plain image generation after stripping edit/reference controls. `tools/video/video_selector.py:419-445,508-539`; `tools/graphics/image_selector.py:275-315,420-438`; `tools/audio/tts_selector.py:267-286` | Separate recommendation from approved execution; block unsupported operations/reference requirements rather than degrading them |
| C7 | P1 | Image estimation and execution normalize parameters differently. Seedream selection with `n=4` estimated $0.135, then adapted to four `num_images` with a repository estimate of $0.54. These are local code estimates, not verified current prices. `image_selector.py:211-216,260-269`; `seedream_image.py:118-132,159-176` | Resolve provider/native inputs once, then estimate, approve, reserve, and execute that same request |
| C8 | P1 | Some pending-generation loops have no overall deadline. Seedance kept polling through 100 **simulated** hours of `IN_PROGRESS`, until the probe stopped it; similar loops exist in Kling/fal Gemini adapters. `seedance_video.py:346-357`; `kling_video.py:163-175`; `gemini_omni_fal.py:187` onward | Monotonic job deadlines, bounded polling, resumable task IDs, cancellation where supported |
| C9 | P1 | Supplying `pipeline_type="unknown"` bypasses initialized-project approval and prerequisites. A framework-smoke project accepted a completed script with no research checkpoint and `human_approved=False`. `lib/checkpoint.py:263-264,300-301,444-454` | Bind all writes to immutable initialized project identity and reject mismatches |
| C10 | P2 | Resume defaults to the wrong pipeline and counts foreign completion records. Screen-demo defaults to `research` instead of `idea`; finished framework-smoke defaults to `proposal` instead of done. Mismatched project/pipeline records can count as completion. `checkpoint.py:602-633`; `skills/meta/checkpoint-protocol.md:169-185` | Infer project identity, validate ownership/approval, and correct documented resume calls |
| C11 | P2 | Manifest contracts are not consistently enforced. Optional research checkpoint omission still blocks proposal; completed `character_design` with empty artifacts validates despite declared outputs. `checkpoint.py:124-157,298-341`; `pipeline_defs/animated-explainer.yaml:64-90`; `pipeline_defs/character-animation.yaml:134-165`; `tests/lib/test_checkpoint_noncanonical_stage.py:45-54` | Derive mandatory outputs and prerequisite semantics from the manifest, not a fixed stage-name map |
| C12 | P2 | Rejected checkpoints can already have mutated the cumulative decision log. An invalid decision log was persisted before real schema validation rejected the checkpoint. `checkpoint.py:389-419,527-547` | Validate prospective combined state first; commit checkpoint/log coherently or use recoverable journaling |
| C13 | P2 | Real persisted ledger and required preauthorization records violate their schemas: `approved_tools` is an unexpected cost-log property; `approval_policy` is rejected as a decision category. `cost_tracker.py:150-152,490-496`; `schemas/artifacts/cost_log.schema.json:8-34`; `decision_log.schema.json:25-44` | Align real producers and schema consumers; test actual serialized output |
| C14 | P2 | Budget policy is not durable: reopening a CAP ledger by path resets mode to WARN and default thresholds. Tool approval cannot authorize an individual action above the threshold. `cost_tracker.py:43-60,126-140,159-162,487-507` | Persist/version effective policy; approve a specific resolved request and amount without weakening global limits |
| C15 | P2 | Some preflight availability checks equate a configured key with readiness even when the SDK is missing. Controlled OpenAI TTS/image probes reported available, then failed execution. `tools/audio/openai_tts.py:117-120,143-144`; `tools/graphics/openai_image.py:113-116,135` | Check required dependencies and report configured versus runtime-verified status separately |

**C1 is the first release blocker for paid use.** Merely setting
`budget.mode: cap` does not connect the ledger to generation. Fixing C1 without
C2-C7 would still leave incorrect reservations and ambiguous recovery.
Duplicate HTTP submissions are proven in the controlled tests; duplicate
charges depend on live provider behavior and were not measured.

Single-writer checkpoint replacement and history archival are useful existing
protections. They do not establish multi-writer safety: fixed temporary names
and cumulative-log read/modify/write operations need coordination before
parallel writers are supported (`checkpoint.py:389-419,555-562`).

Other bounded risks: optional module import errors can abort registry discovery
(`tools/tool_registry.py:120-136`), and dotenv loaders populate arbitrary unset
environment keys. Public services also need server-owned approval identity
bound to an artifact/request version; a caller-supplied approval boolean is not
an authentication boundary.

### Configuration availability remains unverified

The normal registry summary was deliberately not executed. It calls provider
status/info functions and can invoke downloading-capable
`npx --yes hyperframes doctor --json`
(`tools/tool_registry.py:273-279,353-369`;
`tools/video/hyperframes_compose.py:338-348,389-425`).
Other statuses probe local services.

The correct audit result is **configured provider counts unknown**, not zero,
and not "all providers ready." A passive inventory should report executable/
package presence and credential-presence booleans without executing installers,
probing paid endpoints, or printing secrets. A separate explicit runtime check
can then establish genuine readiness.

## Repair existing media integrations before adding replacements

| ID | Priority | Evidence | Direction |
| --- | --- | --- | --- |
| A1 | P2 | `tools/analysis/transcriber.py:242-279` calls `whisperx.DiarizationPipeline(use_auth_token=...)` and returns original segments on exceptions. Stable WhisperX v3.8.6 defines the class in `whisperx.diarize`, accepts `token=`, and does not export it at the package root. | Correct and version-test the existing adapter; report degraded diarization explicitly |
| A2 | P2 | Alignment is coupled to optional diarization, while the top-level word timestamps can remain from the original faster-whisper result after segments change. `transcriber.py:209-228` | Separate alignment from speaker identification and return consistent timing artifacts |
| A3 | P3 | Installation guidance advertises `faster-whisper[gpu]`, but the inspected upstream package declares only `conversion` and `dev` extras. `transcriber.py:39-44` | Correct GPU setup guidance; distinguish CTranslate2 acceleration from PyTorch availability |

A1 is a source-verified compatibility mismatch, not a live test with downloaded
WhisperX/pyannote models. Primary sources:
[WhisperX v3.8.6 diarization API](https://github.com/m-bain/whisperX/blob/v3.8.6/whisperx/diarize.py#L91-L103),
[package exports](https://github.com/m-bain/whisperX/blob/v3.8.6/whisperx/__init__.py#L1-L31),
and [faster-whisper extras](https://github.com/SYSTRAN/faster-whisper/blob/ed9a06cd89a93e47838f564998a6c09b655d7f43/setup.py#L54-L64).

PySceneDetect, FFmpeg/ffprobe QA, silence cutting, SRT/VTT generation, Remotion,
HyperFrames, faster-whisper, and optional WhisperX are already integrated.
Adding them again under new names would not save development time.

## Public repositories: adopt, adapt, or defer

All ten repositories below were unarchived and enabled when checked on
15 September 2026. License conclusions come from actual license files.
Activity/release signals support a maintenance assessment, not proof of
compatibility or output quality.

**Effort definitions:** Small means a narrow adapter/configuration and tests;
medium means artifact mapping or an isolated runtime plus integration tests;
large means operating another stateful application or replacing architecture.
These are scope estimates, not promises of elapsed time or cost savings.

| Repository | License source | Verified release/activity signal | Recommendation and integration boundary | Effort |
| --- | --- | --- | --- | --- |
| [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) | [Apache-2.0](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/main/LICENSE.txt) | [v0.18.1](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/releases/tag/v0.18.1), 9 Nov 2025, marked prerelease; default branch active 13 Sep 2026 | **Adopt narrowly:** optional Python cuts/tracks/source-range interchange; retain OpenMontage JSON as the authoritative production record | Medium |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | [MIT](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) | [v1.2.1](https://github.com/SYSTRAN/faster-whisper/releases/tag/v1.2.1), 31 Oct 2025; default-branch commit 19 Nov 2025 | **Keep/harden existing:** explicit model cache, revisions, offline setup, and transcript fixtures; quieter activity is not abandonment | Small |
| [WhisperX](https://github.com/m-bain/whisperX) | [BSD-2-Clause](https://github.com/m-bain/whisperX/blob/main/LICENSE) | Stable [v3.8.6](https://github.com/m-bain/whisperX/releases/tag/v3.8.6), 25 May 2026; newer RC; branch active 13 Jul 2026 | **Repair existing:** optional alignment/diarization in an isolated Python environment, returning the existing transcript contract | Medium |
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | [BSD-3-Clause](https://github.com/Breakthrough/PySceneDetect/blob/main/LICENSE) | [v0.7.1](https://github.com/Breakthrough/PySceneDetect/releases/tag/v0.7.1), 22 Jul 2026; adaptive-cut fix committed 12 Sep | **Keep/harden existing:** candidate boundaries with regression fixtures; not semantic highlight selection | Small |
| [Remotion](https://github.com/remotion-dev/remotion) | [Custom Remotion license](https://github.com/remotion-dev/remotion/blob/v4.0.484/LICENSE.md) | Latest observed [v4.0.525](https://github.com/remotion-dev/remotion/releases/tag/v4.0.525), 15 Sep 2026; local lock 4.0.484 | **Maintain existing:** controlled upgrades and caption/media regressions; do not build another editor | Small-medium |
| [HyperFrames](https://github.com/heygen-com/hyperframes) | [Apache-2.0](https://github.com/heygen-com/hyperframes/blob/main/LICENSE) | [v0.8.40](https://github.com/heygen-com/hyperframes/releases/tag/v0.8.40), 14 Sep 2026; newer HEAD work | **Maintain existing:** version-pin CLI and verify adapter/audio behavior | Small-medium |
| [Subtitle Edit](https://github.com/SubtitleEdit/subtitleedit) | [MIT](https://github.com/SubtitleEdit/subtitleedit/blob/main/LICENSE) | Stable [v5.2.0](https://github.com/SubtitleEdit/subtitleedit/releases/tag/v5.2.0), 10 Sep 2026; newer beta | **Adopt optional headless `seconv`:** caption correction/conversion with original preservation and reviewed diffs | Small-medium |
| [auto-editor](https://github.com/WyattBlue/auto-editor) | [Unlicense](https://github.com/WyattBlue/auto-editor/blob/master/LICENSE) | [31.6.0](https://github.com/WyattBlue/auto-editor/releases/tag/31.6.0), 6 Sep 2026; branch active 13 Sep | **Defer unless existing silence cutter is insufficient:** pinned subprocess producing a reviewed edit list; current upstream is Nim, not the old Python API | Medium |
| [n8n](https://github.com/n8n-io/n8n) | [Sustainable Use License](https://github.com/n8n-io/n8n/blob/master/LICENSE.md), fair-code, not permissive open source | Stable [2.39.5](https://github.com/n8n-io/n8n/releases/tag/n8n%402.39.5), 14 Sep 2026; newer prerelease | **Use externally if already operated:** approved publishing handoff/receipts/notifications, not creative-stage orchestration | Small-medium |
| [Postiz](https://github.com/gitroomhq/postiz-app) | [AGPL-3.0](https://github.com/gitroomhq/postiz-app/blob/main/LICENSE) | [v2.23.0](https://github.com/gitroomhq/postiz-app/releases/tag/v2.23.0), 4 Aug 2026; branch active 15 Sep | **Conditional external publisher:** useful for an actual multi-channel calendar need; defer a new self-hosted stack | Medium API integration; large self-hosting |

### Highest-value new integration: OpenTimelineIO

OTIO provides a reusable vocabulary for source ranges, timeline ranges, tracks,
gaps, and frame-rate-aware time. Its
[time ranges](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/main/src/opentime/timeRange.h#L21-L29)
use inclusive start/exclusive end. That is directly relevant to R2, but importing
the library alone does not fix the adapters.

Start with a derivative `.otio` export for basic cuts and audio; then implement
restricted import with explicit warnings for unsupported effects. Test source
offsets, gaps, speed, fractional frame rates, and missing media.
[Other format adapters can be lossy](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/main/src/py-opentimelineio/opentimelineio/adapters/__init__.py#L4-L13).
Do not promise round-trip preservation of bespoke React/GSAP compositions.
Matching Python wheels avoid native compilation; a source build introduces
CMake/native build requirements.

The GitHub latest-release endpoint returned 404 and the inspected release
entries were marked prerelease. Do not silently call v0.18.1 a verified stable
release; choose and validate a specific version.

### Caption/localization improvement without another video platform

Subtitle Edit's [headless CLI](https://github.com/SubtitleEdit/subtitleedit/blob/main/docs/reference/command-line.md)
and [machine-readable help](https://github.com/SubtitleEdit/subtitleedit/blob/main/src/seconv/Program.cs#L45-L52)
avoid reimplementing conversion and common-error correction. Use a subprocess
that writes a separate output; show text/timing differences before making them
canonical. The current console project targets .NET 10 and includes native
SkiaSharp/HarfBuzz dependencies for affected operations. Text-only caption
conversion does not justify downloading OCR, translation, or GPU models.

WhisperX adds heavier Torch/pyannote dependencies and language-specific alignment
models. Keep it optional and isolated. Speaker diarization additionally needs
the chosen model's access/terms and Hugging Face credentials. The source license
does not establish model-weight rights or installed hardware compatibility.

For the local Mac path, retain a tested CPU configuration for faster-whisper.
Installing PyTorch alone does not enable CTranslate2 GPU execution; upstream
GPU guidance is NVIDIA-specific. No GPU benchmark was performed.

### Publishing: one external owner, after approval

OpenMontage's local export is not a network publisher. An approved publish
manifest should be handed to one external scheduler, which records an
idempotency identity, remote post ID, state, and receipts back into the project.
Store OAuth/provider credentials in the publisher's approved secret store.
Default to a reviewed draft until the creator explicitly authorizes posting.

n8n already has
[resumable YouTube upload code](https://github.com/n8n-io/n8n/blob/master/packages/nodes-base/nodes/Google/YouTube/YouTube.node.ts#L833-L900).
Its availability as a tool does not prove a configured publishing workflow.
Keep it external and respect its fair-code license.

Postiz has [public upload/post APIs](https://github.com/gitroomhq/postiz-app/blob/main/apps/backend/src/public-api/routes/v1/public.integrations.controller.ts),
but its [supplied deployment](https://github.com/gitroomhq/postiz-app/blob/main/docker-compose.yaml#L178-L233)
adds PostgreSQL, Redis, and Temporal-related infrastructure. That is substantial
operational scope for a solo creator. Do not deploy both schedulers or embed
Temporal in OpenMontage merely because reliability is a goal.

### Upstream improvements worth tracking

- PySceneDetect's [adaptive minimum-scene-length fix](https://github.com/Breakthrough/PySceneDetect/commit/2fa8290de0353d371eaae92a8a6efb69d16a1e0c)
  is newer than 0.7.1. Reuse its regression fixture; do not claim that release
  already contains it.
- HyperFrames 0.8.40 includes an [opaque-origin Web Audio fix](https://github.com/heygen-com/hyperframes/commit/293829a2c1bde0707548b230b74b5cdf8e8985f2).
  [Later EOF handling](https://github.com/heygen-com/hyperframes/commit/f3bd4234f50c378f60fd63404d12f1f6cc759e4d)
  is a separate post-release change; do not silently change editorial intent
  to a held final frame.
- Remotion 4.0.525 includes
  [remotion-dev/remotion#11299](https://github.com/remotion-dev/remotion/pull/11299)
  for muting frozen media. Upgrade only with regression checks relevant to the
  affected compositions, not merely because a newer version exists.

## Reuse work already proposed to OpenMontage

These pull requests were **open**, not merged fixes in the audited snapshot.
Their retrieved status-check rollups were empty where inspected. Mergeability
is not correctness or passing validation. Review and test focused changes;
do not blindly merge broad branches.

| Candidate | Why it may save implementation work | Review boundary |
| --- | --- | --- |
| [#601](https://github.com/calesthio/OpenMontage/pull/601) | Connects budget governance to the BaseTool execution wrapper | Starting point, not a complete fix: reject fail-open budget behavior, retain uncertain billed spend after failed delivery, and include paid HYBRID paths without double charging selectors |
| [#647](https://github.com/calesthio/OpenMontage/pull/647) | Adds valid CostTracker lifecycle transitions | Does not by itself establish transaction safety, numeric validation, or execution wiring |
| [#625](https://github.com/calesthio/OpenMontage/pull/625) | Adds documented `approval_policy` schema support | Does not fix identity bypass, ledger schema, or authenticated approval |
| [#627](https://github.com/calesthio/OpenMontage/pull/627) | Supplies duration-aware HyperFrames timeouts and chunked encoding | Extract relevant reliability changes; it bundles editorial style/contrast changes and does not solve provider polling deadlines |
| [#651](https://github.com/calesthio/OpenMontage/pull/651) | Corrects Pexels/Pixabay availability and blank-key handling | Stock-provider work, not proof that every SDK/provider readiness check is fixed |
| [#652](https://github.com/calesthio/OpenMontage/pull/652), [#653](https://github.com/calesthio/OpenMontage/pull/653) | Targets archive transport errors and Pond5 contracts | Review against the expected-failure tests and real source API contracts |
| [#655](https://github.com/calesthio/OpenMontage/pull/655) | Centralizes environment-key restrictions and adds safety tests | Broad, behavior-changing proposal; inspect duplicated Python/JS loaders and OpenBao-injected trusted process configuration |
| [#632](https://github.com/calesthio/OpenMontage/pull/632) | Repairs the missing proposal in `scripts/backlot_simulate_run.py` | This is a different script from the already-passing `tests/qa/test_08_end_to_end.py`, which does contain proposal |
| [#622](https://github.com/calesthio/OpenMontage/pull/622) | Offers JianYing draft export for manual editing | Specific NLE format candidate; do not assume generic lossless interchange |
| [#638](https://github.com/calesthio/OpenMontage/pull/638) | Proposes generic MCP tool support | Optional integration work after cost/approval/trust boundaries; not required for the first reliable content workflow |

PR descriptions and selected diffs were inspected, but these candidates were
not merged or executed in this audit. In particular, the proposed #601 behavior
of refunding failed calls must not be confused with evidence that a provider
did not already charge for generation.

## Production-hardening sequence and acceptance gates

This is the recommended implementation order, not a claim that hardening has
been performed. Each slice should be a focused change with a failing regression
first, followed by the relevant existing suites and one real local output check.

| Order | Work package | Completion evidence |
| --- | --- | --- |
| 1 | **Approved paid execution and durable spending**: C1-C7, C14 | An unapproved request sends zero submissions; a cap is enforced through real provider wrappers; concurrent reservations cannot exceed it; NaN/negative inputs fail; completed spend survives restart/refund attempts; failed downloads resume the same task |
| 2 | **Project identity and checkpoint integrity**: C9-C13 | Unknown/foreign pipeline writes fail; every pipeline resumes correctly; required outputs derive from manifests; rejected writes change no durable state; serialized artifacts validate; concurrent writers are coordinated or explicitly rejected |
| 3 | **Consistent render contracts**: R1-R6, R8-R11, R14-R16 | Same cut fixture has the same intended order/duration/speed in every supported engine; missing locked engine/asset blocks; captions/audio are applied; short music does not truncate video; same-name assets and simultaneous jobs remain distinct |
| 4 | **Delivery quality and export transactions**: R7, R12-R13, E7 | `revise`/`fail` cannot become a final export; review binds to output identity; stale/corrupt output is rejected; re-export removes revoked content; rights/provenance and reviewed metadata accompany delivery |
| 5 | **Operational release gate**: B1-B5, E1-E6, E8-E9, C8/C15 | Locked clean setup; reviewed advisories; enforceable QA; board reconnect/damaged-state/browser checks; supported packaging route; restored project after interruption; bounded polling/disk use; documented licensing and rollback |
| 6 | **Creator acceptance and optional reuse**: A1-A3 plus selected integrations | Real reviewed demo, explainer, and repurposed clip on the chosen setup; verify EN/ES captions/names/timing; compare original and export; add OTIO/`seconv` only where they eliminate demonstrated manual work |

For the first production candidate, keep **one writer per project and sequential
renders** until transaction/isolation regressions pass. Use explicit approved
provider/model/runtime selections and provider-side budget limits as defense in
depth, not as a substitute for C1-C7. Investigate remote jobs before retrying an
ambiguous generation failure.

Each creator-acceptance run must retain:

- Brief, approved script/assets, selected tools/models/runtime, and permissions.
- Canonical artifacts, source/model versions where available, hashes, and remote
  task IDs.
- Requested versus measured duration, dimensions, frame rate, codec, full-decode
  result, audio/caption checks, and a human visual/listening review.
- Expected, known actual, and still-uncertain costs, including agent/runtime
  costs where relevant; never convert an unknown charge into zero.
- Final export identity and publication receipt, or an explicit not-published
  state.

The audit did not conduct those real-provider acceptance runs, a backup restore,
public-service penetration testing, comprehensive accessibility testing,
cross-platform execution, or a full model/transitive-license review.

## Reproducing the baseline checks

Run in a disposable/source worktree with supported dependencies restored.
Do not copy credentials into it. Unset `HYPERFRAMES_QA`,
`HYPERFRAMES_QA_RENDER`, and `RUN_KLING_DOC_LIVE_CHECK` unless deliberately
running their external checks; `"0"` is truthy for some opt-ins.

```bash
OPENMONTAGE_ALLOW_NETWORK=0 .venv/bin/python -m pytest tests/ \
  --ignore=tests/qa --ignore=tests/eval -q

# Full follow-up after inspecting the legacy QA's local side effects:
OPENMONTAGE_ALLOW_NETWORK=0 .venv/bin/python -m pytest tests/ -q

.venv/bin/python -m compileall -q lib tools backlot schemas styles
.venv/bin/python -m pip check

npm --prefix remotion-composer ci --ignore-scripts --no-audit --no-fund
(cd remotion-composer && ./node_modules/.bin/tsc --noEmit)
npm --prefix remotion-composer audit --omit=dev

# Synthetic diagnostic; overwrites its named tests/qa/output/e2e_* fixtures.
OPENMONTAGE_ALLOW_NETWORK=0 .venv/bin/python tests/qa/test_08_end_to_end.py
ffprobe -v error -show_format -show_streams -of json \
  tests/qa/output/e2e_final_output.mp4
ffmpeg -v error -i tests/qa/output/e2e_final_output.mp4 -f null -
```

The npm advisory command returned exit 1 because of the findings, not because
the scan failed to run. The isolated Python scanner likewise returned findings
for old bootstrap pip. The full Python suite and TypeScript check exited zero.
These baseline results are recorded faithfully; **no advisory or runtime defect
is claimed fixed by this report**.

Raw local logs, JUnit output, dependency-scan JSON, wheel inspection evidence,
and the synthetic video were retained as session artifacts rather than committed
as generated media or machine-specific data.
