# Private production hardening - 16 September 2026

**Implemented and locally verified: a production-hardening release candidate
for private, trusted local authoring.** This is not certification for public
hosting, every provider/model, every rendering combination, or unattended billing.

The [15 September audit](audits/2026-09-15-production-readiness.md) remains the
historical baseline. This page records the subsequent implementation and its
actual qualification limits. Setup and recovery commands are in
[production operations](PRODUCTION.md).

## Implemented

| Area | Audit coverage | Result |
| --- | --- | --- |
| Spending and approvals | C1-C3, C7, C13-C14 | Transactional version-2 ledger; finite amounts; immutable settled spend; exact request/amount approval; mandatory concrete-provider execution guard; retained uncertain holds |
| Request fidelity and recovery | C4-C8, C15 | No blind ambiguous POST retries on the audited routes; durable job identities/staged delivery; explicit recovery against the original reservation; strict provider/reference selection; bounded polling |
| Media-content binding | C7 follow-up | Shared hashing covers local reference aliases and nested lists; changing source bytes invalidates approval/recovery; URL and prompt strings do not cause arbitrary file reads |
| Project/checkpoint integrity | C9-C13 | Immutable initialized identity; correct resume; manifest-declared outputs; approval-policy schema; prevalidated, serialized, recoverable checkpoint/log writes |
| Rendering and export | R1-R16 | No silent runtime substitution; shared timeline semantics; isolated intermediates; audio-duration preservation; missing/unsupported input blockers; hash/freshness-bound PASS acceptance; complete atomic export replacement |
| Backlot | B1-B5 | Damaged-state diagnostics; watcher/reconnect recovery; playback preservation; app/workspace health identity; resolved-root containment; sandboxed authored previews |
| Live financial display | C1 integration | Board reads validated ledger totals, shows settled spend and held/unsettled funds separately, and never masks an invalid ledger with stale zero-cost data |
| Transcription | A1-A3 | WhisperX API compatibility and consistent alignment/timestamps; explicit degraded failures; corrected local-ASR setup guidance |
| Release controls | E1-E5, E9 | Hashed Python/bootstrap locks; pinned Remotion family; patched npm resolutions; full compile/type checks; browser/media/dependency CI gates; enforceable isolated QA; source-only distribution contract |
| Recovery feature | E6 | Hash-verified, no-overwrite archives; checkpoint snapshot lock; pending/active-state refusal; timestamp preservation; ZIP64; path/symlink/size/secret-filename checks |
| Stock retrieval | Previously expected failures | Archive.org/Wikimedia search errors propagate; Pond5 requires configured API access and no longer falls through to an empty scraper stub |

The implementation retains the agent/instructions architecture. Python enforces
bounded execution and persistence contracts; it does not become a creative
orchestrator. No new content-generation platform, scheduler, cloud deployment,
or public authentication system was introduced.

## Verified evidence

| Check | Observed outcome |
| --- | --- |
| Full automated suite, including actual browser tests | **2,215 passed, 10 skipped, zero failures or expected failures; one subtest passed** |
| Existing warning | One Starlette/AnyIO deprecation warning; not suppressed |
| Backlot Chromium coverage | **18 real browser cases**, including malformed state, SSE recovery, playback, responsive layout, and authored-HTML origin separation |
| Full local synthetic production | **41 checks passed** across eight initialized stages through a real, reviewed, hash-bound local export; 1080p H.264/AAC |
| Local media diagnostics | Audio mixing, video stitching, playbook checks, and the E2E above passed in isolated temporary workspaces |
| Genuine Remotion smoke | Remotion 4.0.484 and pinned Chromium rendered the repository timeline helper and native CaptionOverlay; **60 video frames at 30 fps**; scene boundary and caption pixels checked |
| Remotion duration detail | Video stream is 2.000 seconds; AAC-muxed container is **2.048 seconds**. Full decode passed |
| Source and types | Full Python compile and installed `tsc --noEmit` passed |
| Dependency scans | **Zero reported vulnerabilities** in the pinned runtime/development Python scans and npm production scan |
| Clean installation | Fresh virtual environment consumed hashed bootstrap/core locks, passed `pip check`, and discovered 121 tools without runtime health probes |
| Archive regressions | Round-trip integrity, canonical-location approval preservation, review timestamps, tampering, traversal, symlinks, no-overwrite, pending transactions, limits, and ZIP64-threshold behavior exercised |
| Test isolation | Provider-only modules opt into an explicitly named transport fixture; real financial/recovery/network tests keep the actual guard. The fixture was separately verified with the session live-network opt-in enabled |

The ten skips are intentional external/optional or missing-fixture coverage,
not certifications of those paths. The three stock transport failures from the
audit were fixed and their expected-failure markers removed.

Some provider tests deliberately mock the financial boundary to test request/
response adapters. Separate tests exercise the real approval/ledger/recovery
boundary with fake transports. Neither type proves a real account's current
quota, price, credential validity, or provider-side idempotency.

## Remaining qualification gates

1. **Caption-capable FFmpeg is missing on the audit workstation.**
   Its FFmpeg build lacks libass. The full caption diagnostic correctly fails
   with an explicit blocker instead of omitting captions or publishing partial
   output. Provision a libass-enabled build before claiming FFmpeg subtitle
   delivery. Native Remotion caption smoke is a different, verified path.
2. **Real provider acceptance remains necessary.** No paid generation,
   real-provider billing reconciliation, or model downloads were performed.
   Verify a small explicitly approved run with the intended credentials,
   models, limits, and recovery procedure.
3. **Rendering coverage is bounded.** The genuine Remotion smoke does not
   certify every Explainer/presenter composition, browser video seeking, or
   HyperFrames. HyperFrames and optional local model stacks need their own
   explicit runtime qualification.
4. **One review binds one accepted output.** Multi-output review collections
   are not implemented. Do not reuse a single review to approve batch
   deliverables; validate/export outputs separately.
5. **Legacy and relocation migrations are explicit.** Version-1 cost logs
   cannot silently become fresh budgets. Reconcile them before spending.
   Restoring at another canonical location does not automatically migrate
   approvals, absolute artifact paths, or provider-job identities.
6. **Platform and trust boundaries remain local.** Checkpoint/export atomic
   guarantees target local macOS/Linux POSIX filesystems. Windows and network
   filesystem behavior are not certified. Public multi-user access needs
   authentication, ownership checks, isolated workers and separate threat
   modeling; loopback/CSP checks are not a hosted-service security boundary.
7. **Creative and commercial acceptance remains human.** Verify narration,
   captions, pacing, claims, accessibility, media/voice rights, and the applicable
   Remotion organization license. Collection labels are not legal clearance;
   [CC-BY requires attribution](https://creativecommons.org/licenses/by/4.0/).
8. **Hosted CI was not observed.** The strengthened workflow is committed,
   but no hosted run was returned by the fork's Actions API during this work.
   The results above are local execution evidence, not a claimed hosted CI pass.

## Deliberate compatibility changes

Unscoped paid calls, changed prepared inputs, unsafe retries, unsupported
references, missing declared outputs, stale/non-PASS final reviews and incomplete
final exports now block explicitly. Read
[paid execution](PAID_EXECUTION.md),
[provider recovery](PROVIDER_RECOVERY.md),
[delivery acceptance](DELIVERY_CONTRACT.md), and
[rendering contracts](RENDER_CONTRACT.md) before updating callers.

Seedance Ark's explicitly nonbillable query/cancel paths remain usable without
creating new generation reservations. Status responses may report an earlier
job's usage, but do not add it to incremental spend again.

Pure selector resolution no longer uploads local images to an unselected
hosting provider. URL-only routes need an approved URL or supported native data
URI. Draft export remains available, but is labeled draft rather than final.
