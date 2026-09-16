"""Mandatory, project-bound governance for concrete paid tool execution.

The private operator approves a prepared request, not a provider-wide permission.
This module makes no creative choices and never retries a submitted operation.
"""

from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from lib.config_model import OpenMontageConfig
from tools.cost_tracker import ApprovalRequiredError, CostTracker


@dataclass(frozen=True)
class PreparedPaidCall:
    project_dir: Path
    entry_id: str
    tool_name: str
    request_hash: str
    estimated_usd: float
    inputs: dict[str, Any]


_PROJECT: ContextVar[Path | None] = ContextVar("paid_project", default=None)
_RESUME: ContextVar[str | None] = ContextVar("paid_resume_entry", default=None)
_ACTIVE: ContextVar[tuple[CostTracker, str] | None] = ContextVar("paid_reservation", default=None)

# Existing selector contracts predate delegates_paid_execution. These concrete
# modules only dispatch to wrapped tools; never exempt by nesting depth or a
# caller-supplied input. New selectors must declare the contract on their class.
_LEGACY_DELEGATES = frozenset({
    "tools.audio.tts_selector",
    "tools.graphics.image_selector",
    "tools.video.video_selector",
    "tools.capture.screen_capture_selector",
})
_FREE_API_PROVIDERS = frozenset({"pexels", "pixabay", "pixabay_music", "freesound"})
_ARTIFACT_CAPABILITIES = frozenset({
    "image_generation", "video_generation", "tts", "music_generation",
    "avatar", "3d_asset_generation", "enhancement", "audio_processing",
})


def _project_tracker(project_dir: Path | str) -> CostTracker:
    root = Path(project_dir).expanduser().resolve(strict=True)
    marker = json.loads((root / "project.json").read_text(encoding="utf-8"))
    identity = {"directory": str(root)}
    for key in ("project_id", "pipeline_type"):
        value = marker.get(key)
        if not isinstance(value, str) or not value.strip() or value == "unknown":
            raise ValueError(f"Initialized project must have a valid {key}")
        identity[key] = value
    policy = OpenMontageConfig.load().budget
    return CostTracker(
        cost_log_path=root / "cost_log.json", project=identity,
        budget_total_usd=policy.total_usd, reserve_pct=policy.reserve_pct,
        mode=policy.mode, single_action_approval_usd=policy.single_action_approval_usd,
        require_approval_for_new_paid_tool=policy.require_approval_for_new_paid_tool,
    )


@contextmanager
def paid_execution(project_dir: Path | str, *, resume_entry_id: str | None = None) -> Iterator[None]:
    """Bind calls in this context to an initialized project; grants no approval.

    Context is isolated between threads/tasks. New worker threads must explicitly
    enter their own context; project identity is not inferred from output paths.
    """
    tracker = _project_tracker(project_dir)
    root = tracker.cost_log_path.parent
    token = _PROJECT.set(root)
    resume_token = _RESUME.set(resume_entry_id)
    try:
        yield
    finally:
        _RESUME.reset(resume_token)
        _PROJECT.reset(token)


def _is_delegate(tool: Any) -> bool:
    return tool.delegates_paid_execution or type(tool).__module__ in _LEGACY_DELEGATES


def _normalized_inputs(tool: Any, inputs: dict, project_dir: Path | None = None) -> dict:
    scoped_inputs = copy.deepcopy(inputs)
    if project_dir is not None:
        # Providers must receive the same initialized workspace during quote and
        # dispatch. Preserve explicit values so mismatches fail scope validation
        # rather than silently replacing a caller's different project.
        scoped_inputs.setdefault("project_dir", str(project_dir))
    normalized = tool.normalize_inputs(scoped_inputs)
    if not isinstance(normalized, dict):
        raise ValueError("normalize_inputs must return a resolved input dictionary")
    return normalized


def _quote(tool: Any, inputs: dict) -> tuple[bool, float]:
    if _is_delegate(tool) or tool.is_non_billable_operation(inputs) is True:
        return False, 0.0
    runtime = getattr(tool.runtime, "value", tool.runtime)
    if runtime in ("local", "local_gpu"):
        return False, 0.0
    amount = CostTracker.money(tool.estimate_cost(copy.deepcopy(inputs)))
    # Known free stock APIs do not become paid simply because they use HTTP.
    # All other API adapters must provide a positive preflight estimate, even
    # when a missing duration or an invalid count made their estimator return 0.
    paid = amount > 0 or (runtime == "api" and tool.provider not in _FREE_API_PROVIDERS)
    if paid and amount == 0:
        raise ApprovalRequiredError("Paid API requires a positive, finite preflight estimate")
    # The deprecated mixed implementation chooses its provider from credentials.
    # Do not approve an estimate that can execute against a different provider.
    if tool.name == "image_gen" and not inputs.get("provider"):
        raise ApprovalRequiredError("image_gen requires an explicit provider; prefer a concrete provider tool")
    return paid, amount


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Paid requests must contain JSON values or Paths, not {type(value).__name__}")


def _request_hash(tool: Any, inputs: dict, root: Path) -> str:
    from lib.provider_jobs import local_media_digest

    # Bind local input-file contents as well as their names. A replacement image
    # or transcript is a different request. Output files may legitimately change.
    files: dict[str, str] = {}

    def visit(value: Any, key: str = "") -> None:
        if key.startswith("output") or key in ("project_dir", "project_path"):
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, child_key)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, key)
        else:
            digest = local_media_digest(key, value)
            if digest is not None:
                files[str(Path(value).expanduser().resolve())] = digest

    visit(inputs)
    payload = {
        "project_dir": str(root), "cwd": str(Path.cwd()),
        "tool": tool.name, "provider": tool.provider, "version": tool.version,
        "inputs": inputs, "input_files": files,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_json_value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _check_scope(inputs: dict, root: Path, tool: Any) -> None:
    for key in ("project_dir", "project_path"):
        if inputs.get(key) is not None and Path(inputs[key]).expanduser().resolve() != root:
            raise ApprovalRequiredError(f"{key} conflicts with the paid execution project")
    # Write destinations must belong to this project, not merely look like one.
    if tool.capability in _ARTIFACT_CAPABILITIES and not any(
        inputs.get(key) for key in ("output_path", "output_dir", "output_file")
    ):
        raise ApprovalRequiredError("Paid artifact generation requires an explicit project-scoped output destination")
    for key in ("output_path", "output_dir", "output_file"):
        if inputs.get(key) is not None and not Path(inputs[key]).expanduser().resolve().is_relative_to(root):
            raise ApprovalRequiredError(f"{key} must be inside the paid execution project")


def prepare_paid_call(project_dir: Path | str, tool: Any, inputs: dict[str, Any]) -> PreparedPaidCall:
    """Persist an estimate for already-resolved concrete provider inputs.

    Callers must present these same inputs, provider/model and amount to the
    operator. Preparation alone neither approves nor reserves nor submits.
    """
    if not isinstance(inputs, dict):
        raise ValueError("Paid tool inputs must be a dictionary")
    if "recovery_id" in inputs:
        raise ApprovalRequiredError("Recovery must reuse its original cost entry, not receive a new approval")
    root = Path(project_dir).expanduser().resolve(strict=True)
    inputs = _normalized_inputs(tool, inputs, root)
    paid, amount = _quote(tool, inputs)
    if not paid:
        raise ValueError("Prepare the concrete paid provider request, not a free tool or selector")
    tracker = _project_tracker(root)
    root = tracker.cost_log_path.parent
    _check_scope(inputs, root, tool)
    fingerprint = _request_hash(tool, inputs, root)
    entry_id = tracker.estimate(tool.name, str(inputs.get("operation", "execute")), amount, request_hash=fingerprint)
    return PreparedPaidCall(root, entry_id, tool.name, fingerprint, amount, copy.deepcopy(inputs))


def approve_paid_call(request: PreparedPaidCall, *, approved_usd: float, approved_by: str) -> None:
    """Record explicit operator consent. Not a public-service auth boundary."""
    tracker = _project_tracker(request.project_dir)
    tracker.approve_entry(
        request.entry_id, request_hash=request.request_hash,
        approved_usd=approved_usd, approved_by=approved_by,
    )


def record_paid_submission(provider_request_id: str) -> None:
    """Provider hook: persist the accepted job ID before polling or delivery."""
    active = _ACTIVE.get()
    if active is None:
        raise ApprovalRequiredError("Cannot record a paid submission outside governed execution")
    tracker, entry_id = active
    tracker.record_submission(entry_id, provider_request_id)


def governed_execute(
    tool: Any, inputs: Any, execute: Callable, *args: Any, **kwargs: Any,
) -> Any:
    """Shared execution boundary; infrastructure failures always stop execution.

    Provider-only unit tests can explicitly mock this function. Integration tests
    must exercise it with fake transports, not a global/environment bypass.
    """
    if not isinstance(inputs, dict):
        runtime = getattr(tool.runtime, "value", tool.runtime)
        if runtime not in ("local", "local_gpu"):
            raise ValueError("Remote tool inputs must be a dictionary")
        return execute(tool, inputs, *args, **kwargs)
    runtime = getattr(tool.runtime, "value", tool.runtime)
    if runtime in ("local", "local_gpu") or _is_delegate(tool):
        return execute(tool, inputs, *args, **kwargs)
    root = _PROJECT.get()
    inputs = _normalized_inputs(tool, inputs, root)
    paid, amount = _quote(tool, inputs)
    if not paid:
        return execute(tool, inputs, *args, **kwargs)
    if root is None:
        raise ApprovalRequiredError("Unscoped paid call rejected; use paid_execution(project_dir) after exact approval")
    if args or kwargs:
        raise ApprovalRequiredError("All paid request parameters must be in the approved input dictionary")
    _check_scope(inputs, root, tool)
    tracker = _project_tracker(root)
    resume_entry_id = _RESUME.get()
    if resume_entry_id is not None:
        if not inputs.get("recovery_id"):
            raise ApprovalRequiredError("Verified recovery requires its original provider recovery_id")
        original_inputs = {key: value for key, value in inputs.items() if key != "recovery_id"}
        with tracker.recover_entry(
            resume_entry_id, tool.name, _request_hash(tool, original_inputs, root), amount,
        ) as entry:
            # Do not exempt by input alone. The adapter must verify a durable
            # matching journal and guarantee this route cannot submit anew.
            tool.validate_paid_recovery(inputs)
            settled = entry["status"] in ("completed", "failed")
            return _invoke_paid(tool, inputs, execute, tracker, resume_entry_id, recovery=True, settled=settled)
    if "recovery_id" in inputs:
        raise ApprovalRequiredError("Use paid_execution(..., resume_entry_id=original_cost_entry_id) for recovery")
    entry_id = tracker.begin_execution(tool.name, _request_hash(tool, inputs, root), amount)
    return _invoke_paid(tool, inputs, execute, tracker, entry_id)


def _invoke_paid(
    tool: Any, inputs: dict, execute: Callable, tracker: CostTracker, entry_id: str, *,
    recovery: bool = False, settled: bool = False,
) -> Any:
    token = _ACTIVE.set((tracker, entry_id))
    try:
        try:
            result = execute(tool, inputs)
        except BaseException:
            if not settled:
                tracker.mark_unknown(entry_id)
            raise
        result.cost_entry_id = entry_id
        if not isinstance(result.data, dict):
            raise ValueError("ToolResult.data must be a dictionary")
        remote_task_id = result.data.get("remote_task_id")
        if (
            result.provider_request_id is not None and remote_task_id is not None
            and result.provider_request_id != remote_task_id
        ):
            raise ValueError("Conflicting remote task identities in ToolResult")
        provider_request_id = result.provider_request_id if result.provider_request_id is not None else remote_task_id
        if provider_request_id is not None and not settled:
            tracker.record_submission(entry_id, provider_request_id)
            result.provider_request_id = provider_request_id
        actual = CostTracker.money(result.cost_usd)
        # Shared provider recovery metadata may live in data instead of dedicated
        # fields. Explicit uncertainty overrides the legacy success/positive-cost
        # convention: delivering media is not evidence of settled billing.
        aliases = {
            "known": "reported", "reported": "reported", "unknown": "unknown",
            "uncertain": "unknown", "estimated": "estimated", "not_submitted": "not_submitted",
        }
        raw_status = result.data.get("cost_status", result.cost_status)
        if not isinstance(raw_status, str) or raw_status not in aliases:
            raise ValueError("Invalid ToolResult.cost_status")
        cost_status = aliases[raw_status]
        explicit_unknown = cost_status == "estimated" or (
            "cost_status" in result.data and cost_status == "unknown"
        )
        if recovery and cost_status == "not_submitted":
            raise ValueError("Recovery cannot declare an earlier submission free")
        if settled:
            # Delivery outcome is distinct from the original generation charge.
            # Never double-count or overwrite already reconciled spend.
            return result
        if cost_status == "not_submitted":
            if result.success or actual != 0:
                raise ValueError("not_submitted requires failure and zero reported spend")
            tracker.mark_not_submitted(entry_id)
        elif cost_status == "reported" or (result.success and actual > 0 and not explicit_unknown):
            tracker.reconcile(entry_id, actual, success=result.success)
        else:
            # A zero default is not billing evidence, even on success.
            tracker.mark_unknown(entry_id)
        return result
    finally:
        _ACTIVE.reset(token)
