# Paid execution on a private workstation

This is a **private, single-user** execution contract, not a public-service
authorization system. It does not authorize any paid generation merely by being
installed. Continue to follow the pipeline, director skills, creative approval,
and checkpoint protocols. The agent chooses the content, provider, and model;
Python enforces the approved spending boundary.

## Operator workflow

1. Initialize the project normally (`lib.checkpoint.init_project`). A real
   `project.json` with `project_id` and `pipeline_type` is required.
2. Resolve the concrete provider and its native inputs. Announce the provider,
   model, exact request, estimated USD, and whether it is a sample or batch.
3. Prepare a request without dispatching it:

   ```python
   from lib.budget import prepare_paid_call, approve_paid_call, paid_execution

   # project_dir is the initialized workspace; tool is the chosen concrete
   # BaseTool; inputs are the proposed native request, with an explicit output
   # destination inside the workspace when the provider writes an artifact.
   request = prepare_paid_call(project_dir, tool, inputs)
   # Present request.inputs and request.estimated_usd to the operator.
   # STOP and obtain explicit consent. Preparation is NOT approval.
   ```

4. Only after the operator approves that request and amount:

   ```python
   approve_paid_call(
       request,
       approved_usd=request.estimated_usd,
       approved_by="private operator",  # identify who actually consented
   )
   with paid_execution(project_dir):
       result = tool.execute(request.inputs)
   ```

`PreparedPaidCall` contains `project_dir`, `entry_id`, `tool_name`,
`request_hash`, `estimated_usd`, and normalized `inputs`. The preview is not an
approval token: changing its inputs does not change the durable approved hash.
Money must be numeric, finite, and nonnegative. The approved amount must equal
the estimate, not a larger blanket allowance. The estimate is reserved and
the approval consumed under one process-safe ledger transaction **before**
the provider executes.

The request hash binds the canonical project directory, tool/provider/version,
working directory, normalized input dictionary, and the contents of existing
local input files named with path/file fields. Output paths are checked against
the project boundary. Different prompts, models, counts, paths, file contents,
or estimated amounts require a new approval. Provider default normalization must
be deterministic and have no side effects. Remote URLs are approved as URLs;
their remote content cannot be frozen by this local ledger.

## Intentional compatibility changes

- **Unscoped paid `tool.execute()` calls are rejected.** An API key, output path
  under `projects/`, `approve_tool()`, or `paid_execution()` context alone is
  not approval. The context binds a project; it grants no permission.
- Reopening a ledger uses its complete persisted policy, not constructor
  defaults or a newly edited global configuration. Policy is fixed for that
  ledger; there is no implicit budget reset or global-limit override.
- The global default is `cap`. Standalone ledger `warn`/`observe` modes remain
  available for estimates and diagnostics. **Real paid execution enforces the
  cap and exact approval in every mode.**
- `approve_tool()` remains a legacy first-tool acknowledgement for standalone
  ledger users. It cannot authorize real generation. `approve_entry()` is the
  lower-level exact-request approval interface.
- Local/local-GPU operations and free stock APIs need no paid context. Paid
  HYBRID paths with positive estimates are governed. Other API adapters must
  provide a positive estimate: missing duration or zero count must not
  accidentally turn a paid API into a free one.
- The deprecated `image_gen` requires an explicit provider even when local;
  prefer a concrete provider or the selector's resolved provider request.
- Ledger version `2.0` persists policy, approvals, reservations, and project
  identity. Version `1.0` remains recognizable to schema consumers but
  **cannot be reopened for spending**: it lacks a trustworthy durable policy.
  Stop and reconcile a backup against provider billing before an explicit,
  reviewed migration. Preserve all completed spend and unresolved holds;
  never delete the old ledger or initialize a blank replacement to bypass it.

## Selector and provider contracts

Selectors do not get blanket approval. A selector may declare
`delegates_paid_execution = True` only if **every** paid side effect calls a
wrapped concrete `BaseTool.execute()`. Its provider-native request must match
the prepared approval exactly. The existing audio/image/video/capture selector
modules have this compatibility classification at the boundary. Nesting depth
never bypasses a concrete provider's gate; only that provider records spend.

Concrete adapters can override `normalize_inputs(inputs)` to resolve native
defaults and aliases. Preparation and execution both normalize before estimating
and hashing. The resolved snapshot, not an unapproved alternative, is executed.
No network calls, provider selection, or paid work belongs in normalization or
estimation.

`ToolResult` adds:

| Field | Meaning |
| --- | --- |
| `cost_entry_id` | Ledger entry used by the gate; set by the wrapper |
| `provider_request_id` | Accepted remote job ID, if known |
| `cost_status="unknown"` | Default; failure does not prove zero billing |
| `cost_status="estimated"` | Approximate generation cost, not settled billing; retains the hold even on successful delivery |
| `cost_status="reported"` | `cost_usd` is the provider's settled/reported cost, including a proven zero |
| `cost_status="not_submitted"` | Failure was provably before dispatch; zero spend and no remote job ID required |

Shared recovery adapters may instead provide `ToolResult.data` with
`remote_task_id`, `recovery_state`, and `cost_status` (`known` or `unknown`).
`known` reconciles the reported `cost_usd`, including a proven zero;
explicit `unknown` retains the full hold **even on a successful result with a
positive cost**. This explicit metadata takes precedence over the legacy
positive-success convention below. `remote_task_id` is persisted as the ledger's
`provider_request_id`; conflicting IDs fail closed. The gate does not copy the
rest of `data` into the ledger. Never put credentials, tokens, or secret URLs in
recovery metadata.

For compatibility, successful results with a positive `cost_usd` reconcile the
adapter's reported amount only when no explicit unknown/estimated billing
metadata is supplied. These legacy reports may still be pricing estimates, not invoices.
A successful zero-cost default is **not** evidence that a paid operation was
free: the reservation remains outstanding unless explicitly reported.

Immediately after acceptance, adapters may call
`lib.budget.record_paid_submission(provider_request_id)` before polling or
delivery. This requires an active governed call and records the ID durably.
The ID cannot later be replaced by a different job. A process crash or delivery
failure must not trigger a fresh submission automatically.

## Failure accounting and reconciliation

- `estimated -> reserved -> executing -> completed/failed` is the normal path.
  Paid claims combine approval validation, reservation, and `executing` in one
  transaction.
- Exceptions, cancellation, timeout, or an unknown failed result retain the full
  reservation as `unknown`. Abrupt process termination can leave `executing`;
  it also retains the full hold. A failed ledger write propagates, never
  permits dispatch, and never implies a refund.
- Only explicit `not_submitted` evidence can release an executing reservation.
  Ordinary `refund(entry_id)` only cancels an unexecuted estimate/reservation.
  It cannot erase completed or failed spend, or release an ambiguous call.
- Exact repeat transitions are idempotent. A conflicting terminal update,
  terminal refund, or replay of a consumed execution approval is rejected.
- Reconcile an unresolved hold only with billing/submission evidence:

  ```python
  from tools.cost_tracker import CostTracker

  tracker = CostTracker(cost_log_path=project_dir / "cost_log.json")
  tracker.reconcile(entry_id, actual_usd=verified_cost, success=False)
  ```

  Record an actual cost even if it exceeds the estimate; losing known spend is
  worse than exposing an overrun. The next call then sees the reduced capacity.
  Estimates cannot guarantee provider prices or prevent provider-side overruns.
  Do not report zero solely because an exception occurred.

The ledger is the spending authority. Do not sum selector and provider results
or infer charges from optional Backlot events.

### Recover without a second generation charge

Journal-aware providers can implement `validate_paid_recovery(inputs)`. It must
read and validate an **existing** durable job belonging to the same project and
resolved request, reject a job still in `prepared` state, and prove that this
route can only poll/download/deliver—not submit. The default implementation
rejects recovery. A caller-supplied `recovery_id` alone is never sufficient.

```python
with paid_execution(project_dir, resume_entry_id=failed_result.cost_entry_id):
    recovered = tool.execute({
        **request.inputs,
        "recovery_id": failed_result.data["recovery_id"],
    })
```

The boundary checks the original approval, request and amount, and locks that
entry's recovery sidecar while the adapter runs. An unknown hold is reconciled
when recovery provides known billing evidence; explicit unknown/estimated
charges remain held even after delivery succeeds. Already-settled spend is
unchanged on re-delivery.
There is no second reservation or charge. Other request fields remain bound to
the original approval, including output paths. Provider recovery must not be
prepared as a new paid call. Unsupported adapters fail closed rather than
silently bypassing the gate.

An `executing` entry is not eligible for recovery: its original worker may
still be alive. After explicitly confirming that worker has stopped, mark the
entry unknown (`tracker.mark_unknown(entry_id)`) and recover the durable job.
Do not release the hold as a shortcut.

## Durability and limits

Each operation locks the stable `cost_log.json.lock` sidecar, reloads and
validates disk state, checks/transitions state, serializes valid JSON, fsyncs a
unique same-directory temporary file, and atomically replaces the log. POSIX
also fsyncs the containing directory. Readers use the same lock. POSIX uses
`flock`; Windows uses `msvcrt` byte-range locking. Lock/validation/storage errors
are fatal, not a reason to execute without governance. Sidecar locks must not
be deleted while any worker may be active. Symlinked logs/locks are rejected.

Supported scope: cooperating processes on a local workstation filesystem.
This is not a network-filesystem/distributed transaction, hostile-code sandbox,
or multi-user authentication boundary. Private operator code can record an
approval, so possession of a Python interpreter with project write access is
trusted. Arbitrary SDK calls outside BaseTool are not sandboxed. Protect the
project filesystem and do not expose this API as a public approval endpoint.

Thread/task contexts are isolated; new worker threads must explicitly enter
`paid_execution(project_dir)`. Approval claims and ledger changes serialize
across processes; provider work runs outside the lock. Retain backups. A
crash after replacement but before acknowledgement may leave a committed hold;
reloading, not retrying generation, is the safe response.

## Offline verification

`tests/tools/test_budget_hardening.py` uses synthetic tools and mocked concrete
provider transports with the **real gate**. It covers stale trackers, spawned
process contention, invalid amounts, immutable spend, restart policy, exact
approval, paid HYBRID/selector boundaries, failure accounting, and atomic-write
failure. Existing cost-tracker tests remain applicable.

Provider-only unit tests can explicitly mock `lib.budget.governed_execute`:

```python
monkeypatch.setattr(
    "lib.budget.governed_execute",
    lambda tool, inputs, execute, *args, **kwargs: execute(tool, inputs, *args, **kwargs),
)
```

Keep their network transports mocked too. This isolates provider behavior; it
does **not** prove governance. Never install this mock as a global test fixture,
and never add environment/pytest detection to production code to bypass the gate.
Dedicated integration tests must continue to exercise the real boundary.
