# Local delivery and checkpoint contract

This contract is for **private, trusted local authoring**. It does not authorize
public deployment, upload media, invoke paid providers, or replace the agent's
pipeline orchestration and human approvals.

## Production identity and progression

Initialize production with `lib.checkpoint.init_project(...)`. Once initialized,
`project_id`, `pipeline_type`, and `style_playbook` are immutable. Reinitialization
may refresh the title, not identity. Unknown or broken manifests and explicit
identity mismatches fail closed, including writes with omitted identity fields.
Use another project for another pipeline/style.

`get_next_stage(root, project_id)` and `get_completed_stages(...)` infer the
project's manifest. Foreign project/pipeline/stage records and unapproved gated
completion records raise `CheckpointValidationError`; they never count as
completion. Legacy unmarked workspaces can infer a pipeline from consistent
records. The old no-identity canonical-order utility remains for low-level
legacy callers, not as a production initialization protocol.

Completed and awaiting-human stages must carry **all** manifest `produces`
artifacts, including noncanonical stages such as `character_design` and
`rig_plan`. Registered artifacts are schema-validated, even on partial
checkpoints. Absent predecessors with `checkpoint_required: false` may be
omitted. A present optional checkpoint must still complete and satisfy approval
before advancing; missing checkpoint permission does not waive required inputs.

Approval remains an explicit per-stage assertion by the trusted local operator.
The `decision_log` schema accepts `approval_policy`, but recording that category
does not silently set approval flags or waive manifest gates.

## Accepted video versus produced file

File production success is not final acceptance. A completed compose checkpoint
requires:

- schema-valid `render_report` and `final_review`;
- `final_review.status == "pass"` (not omitted, `revise`, or `fail`);
- `recommended_action == "present_to_user"` if provided;
- matching `final_review.output_path` and `render_report.outputs[].path`;
- `final_review.output_sha256` and matching report output `sha256`;
- timezone-aware `reviewed_at` no earlier than the output's modification time;
- an existing nonempty video, a valid container/video stream, and full FFmpeg
  video/audio decode without errors.

Rewriting or touching the video invalidates earlier evidence. Re-review the
finalized output; do not copy an old review onto a new render. Hashes identify
content, not creative quality: visual/audio/promise inspection remains necessary.
Technical validation runs locally using FFmpeg/ffprobe, with bounded timeouts,
and fails closed if those tools are unavailable.

The current single `final_review` identifies **one output**. A multi-output
report cannot use that review to approve additional videos; checkpoint/export
each accepted deliverable separately until per-output review collections are
implemented. Relative paths keep existing tool semantics (relative to the
caller's working directory); prefer absolute paths for durable handoffs.

## Shared helper API

```python
from lib.delivery_validation import (
    DeliveryValidationError,
    content_sha256,
    validate_media,
    validate_final_delivery,
)

digest = content_sha256(output_path)  # str: lowercase SHA256
probe = validate_media(output_path)   # dict: ffprobe JSON, after full decode
validate_final_delivery(output_path, final_review, render_report=None)  # None
```

All three accept `str | pathlib.Path`. Validation failures raise
`DeliveryValidationError`. Renderers must finalize their output before hashing
and stamping `reviewed_at`; optional `output_size_bytes` must match if present.
Review schema binding fields remain optional for draft/legacy artifact loading,
but **mandatory at the final-delivery boundary**. No review is synthesized by
the checkpoint or export code.

## Export modes and complete replacement

`ExportBundle.execute` takes the existing `video_path` and `title`, plus:

| Input | Contract |
| --- | --- |
| `delivery_mode` | `final` by default; explicit `draft` for diagnostic packaging |
| `final_review` | Inline review object, mandatory for final export |
| `render_report` | Optional inline report; when supplied, output/hash must match |

Final export returns a publish-log entry with `status: "exported"`. Draft export
may package diagnostic bytes and does not require passing review or media
decode; its status is **`draft`**, and returned `delivery_mode` plus
`metadata/delivery.json` preserve that distinction. Neither mode uploads.

Inputs and the prospective publish log validate before staging is created.
The full replacement is built in a unique sibling staging directory. The copied
video is checked again so a source change during copying cannot slip through.
Metadata includes `delivery.json`, `publish_log.json`, and (for final exports)
the original `final_review.json` as provenance. The review's original output
path is retained; `delivery.json` identifies the packaged relative video path
and hash.

The namespace commit is an atomic directory rename/exchange. Omitting captions,
tags, chapters, thumbnail, or thumbnail concept on re-export removes old files.
Validation, copy, or exchange failure leaves the old export unchanged. Symlink
export roots and roots containing the source video are rejected.

Directory exchange uses macOS `renamex_np` or Linux `renameat2`, and a POSIX
directory lock serializes commits. Unsupported platforms/filesystems fail
closed rather than use a two-rename visibility gap. Temporary staging cleanup
failure is logged; it does not invalidate an already committed export. These
are process-failure/atomic-visibility guarantees, not a backup or a guarantee
against arbitrary hardware/filesystem failure.

## Checkpoint/log persistence and recovery

Checkpoint APIs serialize cooperating processes/threads with a POSIX lock on
the projects-root directory (conservative root-wide locking). Incoming artifacts,
JSON serialization, checkpoint shape, and prospective cumulative decisions are
validated before durable checkpoint/log mutation. Callers' artifact dictionaries
are not modified. Decision IDs are append-only: identical repeated entries are
idempotent, conflicting reuse is rejected.

A fsynced `.checkpoint-transaction.json` journal contains the validated
checkpoint and prospective log. Each destination is replaced atomically from
a unique temporary file. If execution stops between replacements, the next
checkpoint API read/write rolls the journal forward under the same lock.
Keep a pending journal for recovery; do not manually delete it. An I/O failure
after journal publication may report an error even though the operation will
commit on recovery—inspect state before retrying with different decisions.

API readers recover before observing state. Direct filesystem observers may
briefly see an old checkpoint alongside a new cumulative log; they do not have
transactional read guarantees. History snapshots remain best-effort with a
visible warning on archival failure. Windows and network-filesystem locking
semantics are not certified by this local POSIX contract.

## Validation coverage

Targeted checkpoint/export tests exercise unknown/foreign identity, actual
pipeline resume, optional predecessors, declared outputs, rejected log
immutability, concurrent writes, interrupted commit recovery, review status and
content/freshness binding, real synthetic FFmpeg fixtures, explicit diagnostic
drafts, stale-file removal, and copy-failure preservation. No provider or paid
calls are necessary.
