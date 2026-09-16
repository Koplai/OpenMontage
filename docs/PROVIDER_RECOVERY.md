# Provider approval, submission and delivery recovery

This contract targets the **private source workstation**, not a public service.
Tests use fake transports, SDKs, clocks and temporary projects. They do not
certify live provider pricing, model availability, output quality or account access.

## Resolve before approving

Recommendations do not authorize execution. `operation="rank"` on a selector
returns recommendations without generating anything.

Each selector exposes:

```python
provider_tool, native_inputs = selector.resolve_execution(selector_inputs)
```

Resolution performs no upload or generation. It selects an eligible tool and
normalizes aliases into its native inputs. An explicit `preferred_provider`
accepts a provider name **or exact tool name** and is a hard constraint, even
when another provider scores better. Use the tool name to distinguish gateways
sharing a provider name. Unknown/unavailable choices do not fall through.

For images, `n` becomes `num_images` or Google's `number_of_images` as appropriate.
Conflicting aliases fail. Provider/model controls, reference inputs and native
defaults are resolved before estimation. Sora's `duration`/`aspect_ratio` aliases
become `seconds`/`size` before defaults can override them.

Use the **same concrete tool and returned native inputs** for preparation,
approval and execution:

```python
from lib.budget import prepare_paid_call, approve_paid_call, paid_execution

# Include an initialized project_dir and a project-contained output_path in inputs.
tool, params = selector.resolve_execution(inputs)
request = prepare_paid_call(project_dir, tool, params)

# Present request.tool_name, the exact native model/variant/parameters, and
# request.estimated_usd. Only after the human explicitly approves that request:
approve_paid_call(
    request, approved_usd=request.estimated_usd, approved_by="private operator"
)
with paid_execution(project_dir):
    result = tool.execute(request.inputs)
```

Preparation grants no approval. Provider-wide approval, nesting inside another
tool, or a recovery ID alone cannot bypass the BaseTool budget gate. Keep the
`PreparedPaidCall` inputs and resulting `cost_entry_id` for recovery.

## Durable provider records

The following adapters share the small `lib/provider_jobs.py` helper:

- Official Kling video (Classic, Turbo, Omni)
- Sora
- fal Kling, Seedance video and Gemini Omni
- OpenAI image and speech
- Seedream image

The helper is a submission/delivery boundary, **not a pipeline engine**.
Its files live in `<project_dir>/.provider_jobs/`:

| File | Contents |
| --- | --- |
| `<fingerprint>.json` | Version, project identity hash, request fingerprint, provider/model, submission state, estimated liability, remote job ID when known, output hashes |
| `<fingerprint>.<index>.bin` | Private generated media cached for delivery retries |
| `<fingerprint>.lock` | Short process-safe submission/journal update lock |

The journal does **not** contain prompts, request bodies, API keys, approval
tokens, signed media URLs, or raw exception/HTTP response bodies. Request
fingerprints hash content, including local reference-file bytes; credential
fields are excluded. Native local aliases such as `image`, `image_url`, `images`,
`reference_image` and nested `image_list[].image_url` bind the same bytes as
explicit `*_path(s)` fields. `local_media_digest(key, value)` is the shared
approval/recovery primitive: list traversal preserves its original field name,
HTTP(S)/data references never trigger filesystem probes, and prompt/text values
are never treated as local files. Only digests enter the durable identity.
fal status/result paths are persisted only after checking
the fixed HTTPS queue host, expected request ID and absence of query credentials.
Signed media URLs are fetched from the provider response again, not journaled.

Records are project-bound by resolved directory and initialized project identity.
A copied recovery ID cannot authorize a different project or changed content.
Do not delete journals/cached media while billing or delivery is unresolved.
Generated media can itself be sensitive: keep the workspace private and apply
the project's normal backup/retention policy.

### State and crash behavior

1. `prepared`: no generation dispatch has started.
2. `submitting`: an atomic, fsynced intent exists **before** the paid POST.
3. `submitted`: the remote job ID has been fsynced before polling/downloads.
   The same ID is recorded in the active budget reservation.
4. `generated`: the provider completed; synchronous image/speech bytes are
   cached before publication. For queue providers, generation may be complete
   even if downloading the bytes still fails.
5. `delivered`: cached media passed hash checks and was atomically published.
6. `failed`: a queue job reached a terminal failure; its ID/liability remain.

If a POST times out after the provider may have accepted it, **do not submit
again**. A `submitting` record without a known remote ID or complete cached output
is deliberately blocked. Reconcile that submission through the provider's
account/job history before considering another approved generation.

No undocumented idempotency guarantees are assumed. An `external_task_id` is
not treated as proof that repeating an official Kling POST is safe.

Synchronous image/speech APIs have no usable remote retrieval ID here. A crash
between receiving the response and durably staging its media remains an
uncertain, manually reconciled outcome. The tool will not generate again to
conceal that gap. Media already staged can be delivered again without a POST.

## Resume, do not regenerate

Results expose:

- `result.cost_entry_id`: the original project budget reservation.
- `result.provider_request_id`: a known remote job ID, when available.
- `result.data.recovery_id`: project-local 64-character recovery fingerprint.
- `result.data.job_id`: the remote job ID (same meaning as provider_request_id).
- `result.data.submission_state`, `request_fingerprint`, `estimated_cost_usd`.
- Shared-workstream aliases: `result.data.remote_task_id` is the same remote ID;
  `result.data.recovery_state` is the same submission state.
- After submission, `result.data.cost_status="unknown"` means **billing** is
  not settled, even when the remote task ID and successful delivery are known.
  `known` is reserved for authoritative settled billing, not a local estimate.
  Before dispatch, the dedicated `result.cost_status="not_submitted"` proves
  no generation was submitted; the data-level cost status is omitted.
- `result.cost_status`: `not_submitted`, `unknown`, or `estimated` for these
  adapters. No adapter claims an actual settled price from an estimate.

For a known job or intact cached output, reuse the original approved inputs:

```python
resume_inputs = {**request.inputs, "recovery_id": result.data["recovery_id"]}
with paid_execution(project_dir, resume_entry_id=result.cost_entry_id):
    recovered = tool.execute(resume_inputs)
```

`validate_paid_recovery(inputs)` checks the project/request journal read-only
and verifies cached hashes. Recovery cannot submit a new generation, including
if a record becomes `prepared` between validation and execution. The budget
boundary reuses the original reservation; it does not approve or charge a
second generation. Already reconciled spend is not rewritten by delivery.

Do not create a new approval for recovery. The original provider parameters,
output path and approval hash remain binding. An executing budget entry must
first be marked unknown through the ledger's operator recovery procedure,
**after confirming the original worker has stopped**. No automatic cancellation
is claimed; timeout may leave the remote job running.

Identical effective requests reuse the journal by default. If the human wants
a genuinely new variation, include a new `generation_id` in its newly approved
request. Never change that identifier merely to get around an uncertain submit.

`cost_usd` on an uncertain failure retains estimated liability rather than
misleadingly reporting free generation. `estimated` successful output is still
an estimate, not a provider invoice: retain the hold until actual billing is
reconciled. Failed delivery does not refund generation.

## Deadlines and retries

`timeout_seconds` is the per-invocation monotonic end-to-end network/poll budget
(default 900 seconds; Seedream image defaults to 300; maximum 3600).
`poll_interval` must be positive and finite. Submission, storage upload,
status/result reads and download calls consume that same budget; polling and
safe-read backoff sleeps are capped by the remaining time. A resume invocation
gets a fresh time budget but reuses the existing generation.

Kling POSTs and OpenAI SDK POSTs have automatic retries disabled. Safe GETs keep
bounded transient-error retries. Network timeouts are bounded at each transport
call; these are not a hard process-kill guarantee for a wedged SDK, filesystem,
OS call or optional local media probe. Worker interruption remains recoverable
from the journal. Provider retention/expired jobs can still require manual
delivery support; no regeneration is used as a hidden download fallback.

## Deliberate fail-closed changes

- Image/reference/edit requests cannot turn into prompt-only generation.
- Unsupported reference types or extra images cannot be silently discarded.
- Explicit provider/model choices cannot be replaced because of score or
  unavailability; a different choice requires a new human approval.
- Local images are routed only to providers with a real local-input adapter.
  Selectors no longer upload local files to an unrelated gateway on their own.
- Both `video_edit` and `edit_video` retain editing semantics and map only to
  providers that advertise one of those operations.
- Providers with fixed endpoints reject unsupported model override fields.
- Seedance `duration="auto"` uses the maximum-duration estimate, not five
  seconds, because the eventual duration is not known at approval time.
- Unscoped paid calls, missing initialized projects and foreign output paths
  are blockers. Runtime code contains no test/environment budget bypass.

## WhisperX and SDK preflight

OpenAI image/speech preflight requires both configuration and an importable
SDK with its `OpenAI` client. Sora additionally checks the Videos-capable SDK
version. A configured key does not certify account access or live model access.

Transcription uses CTranslate2's CUDA capability checks, not PyTorch availability.
There is no `faster-whisper[gpu]` extra: install `faster-whisper` and the CUDA/cuDNN
versions supported by the installed CTranslate2 build.

`align=True` requests forced alignment independently of `diarize=True`.
WhisperX 3.8.6 speaker identification imports
`DiarizationPipeline` from `whisperx.diarize` and passes `token=HF_TOKEN`.
Top-level `word_timestamps` are rebuilt from the final segment words so alignment
and speaker labels cannot disagree with the nested output.

Requested unavailable/failed alignment or diarization produces `success=False`
with explicit `alignment_status`/`diarization_status` and a usable **partial**
transcript artifact. Missing Hugging Face credentials, gated model access or
speaker labels are never silently reported as successful diarization.
