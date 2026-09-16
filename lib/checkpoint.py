"""Checkpoint writer/reader for pipeline state persistence.

Each stage writes a checkpoint after completion. The orchestrator uses
checkpoints to resume pipelines and to present state at human checkpoints.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from functools import lru_cache, wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import jsonschema

from schemas.artifacts import ARTIFACT_NAMES, validate_artifact

# All known stages across all pipelines (used only for artifact name lookup).
ALL_KNOWN_STAGES = frozenset([
    "research", "proposal", "idea", "script", "scene_plan",
    "assets", "edit", "compose", "publish",
])

# Backward-compatible alias — existing code / tests that import STAGES still work.
# New code should use get_pipeline_stages(pipeline_type) instead.
STAGES = ["research", "proposal", "idea", "script", "scene_plan",
          "assets", "edit", "compose", "publish"]

CANONICAL_STAGE_ARTIFACTS = {
    "research": "research_brief",
    "proposal": "proposal_packet",
    "idea": "brief",
    "script": "script",
    "scene_plan": "scene_plan",
    "assets": "asset_manifest",
    "edit": "edit_decisions",
    "compose": "render_report",
    "publish": "publish_log",
}

# Additional artifacts that may be produced alongside canonical ones.
# These are not stage-defining but are required by governance contracts.
SUPPLEMENTARY_ARTIFACTS = {
    "source_media_review",  # Required before first planning stage when user media exists
    "final_review",         # Required by compose stage before presenting to user
    "video_analysis_brief", # Reference-video grounding artifact carried alongside stages
}


def get_pipeline_stages(pipeline_type: str | None) -> list[str]:
    """Return the ordered stage list for a specific pipeline.

    Only legacy callers omitting identity use the canonical order. An explicit
    unknown or broken manifest is an error, never an approval-policy fallback.
    """
    if pipeline_type is None:
        # Deterministic canonical fallback — sorted to ensure stable ordering
        import logging
        logging.getLogger(__name__).warning(
            "get_pipeline_stages called without pipeline_type — "
            "using canonical fallback order. Pass pipeline_type for correctness."
        )
        return list(STAGES)

    return [stage["name"] for stage in _manifest_stages(pipeline_type)]

CHECKPOINT_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "checkpoints"
    / "checkpoint.schema.json"
)

# Canonical project root. Checkpoints, artifacts, and the project marker all
# live under PROJECTS_DIR/<project_id>/ — this is the location the Backlot
# board watches. Callers may still pass a different pipeline_dir (tests do),
# but production runs should use the default.
from lib.paths import PROJECTS_DIR  # noqa: E402  (single source of truth)

PROJECT_MARKER_FILENAME = "project.json"
HISTORY_DIRNAME = "history"


class CheckpointValidationError(ValueError):
    """Raised when a checkpoint or its canonical artifacts are invalid."""


def _manifest_stages(pipeline_type: str) -> list[dict[str, Any]]:
    from lib.pipeline_loader import load_pipeline_readonly

    try:
        return load_pipeline_readonly(pipeline_type)["stages"]
    except Exception as exc:
        raise CheckpointValidationError(
            f"Unknown or invalid pipeline_type {pipeline_type!r}: {exc}"
        ) from exc


def _project_identity(
    pipeline_dir: Path,
    project_id: str,
    pipeline_type: str | None = None,
    style_playbook: str | None = None,
) -> tuple[str | None, str | None]:
    """Bind explicit caller identity to the initialized marker, fail closed."""
    marker_path = pipeline_dir / project_id / PROJECT_MARKER_FILENAME
    if marker_path.exists():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if not isinstance(marker, dict) or marker.get("project_id") != project_id:
                raise ValueError("project_id does not match its workspace")
            if not marker.get("pipeline_type"):
                raise ValueError("pipeline_type is missing")
            for key, supplied in (("pipeline_type", pipeline_type), ("style_playbook", style_playbook)):
                if supplied is not None and supplied != marker.get(key):
                    raise ValueError(f"immutable {key} mismatch")
            pipeline_type = marker["pipeline_type"]
            style_playbook = marker.get("style_playbook")
        except (ValueError, OSError) as exc:
            raise CheckpointValidationError(f"Invalid project identity: {exc}") from exc
    if pipeline_type is not None:
        _manifest_stages(pipeline_type)
    _validate_style_playbook(style_playbook)
    return pipeline_type, style_playbook


@contextmanager
def _serialized(pipeline_dir: Path):
    """Serialize local POSIX writers/readers without a mutable lockfile.

    Lock the projects-root directory itself, not a checkpoint inode that will
    be atomically replaced. This also serializes threads with independent FDs.
    """
    import fcntl

    pipeline_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(pipeline_dir, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _atomic_json(path: Path, data: dict) -> None:
    # Serialize first: invalid JSON values must not leave even a temp file.
    payload = json.dumps(data, indent=2, allow_nan=False)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(name).unlink(missing_ok=True)


def _recover_transaction(project_dir: Path) -> None:
    """Roll forward a previously validated checkpoint/log transaction."""
    journal_path = project_dir / ".checkpoint-transaction.json"
    if not journal_path.exists():
        return
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        checkpoint = journal["checkpoint"]
        validate_checkpoint(checkpoint)
        if checkpoint["project_id"] != project_dir.name:
            raise ValueError("journal belongs to another project")
        explicit_pipeline = checkpoint["pipeline_type"]
        bound_pipeline, _ = _project_identity(
            project_dir.parent, checkpoint["project_id"],
            None if explicit_pipeline == "unknown" else explicit_pipeline,
            checkpoint.get("style_playbook"),
        )
        if bound_pipeline is not None and bound_pipeline != explicit_pipeline:
            raise ValueError("journal pipeline does not match initialized identity")
        if journal.get("decision_log") is not None:
            validate_artifact("decision_log", journal["decision_log"])
            if journal["decision_log"]["project_id"] != checkpoint["project_id"]:
                raise ValueError("journal decision_log belongs to another project")
    except (ValueError, KeyError, TypeError, OSError, jsonschema.ValidationError) as exc:
        raise CheckpointValidationError(f"Invalid pending checkpoint transaction: {exc}") from exc
    if journal.get("decision_log") is not None:
        _atomic_json(project_dir / "decision_log.json", journal["decision_log"])
    path = project_dir / f"checkpoint_{checkpoint['stage']}.json"
    _atomic_json(path, checkpoint)
    journal_path.unlink()


def _validate_style_playbook(style_playbook: str | None) -> None:
    """Fail closed when a checkpoint names a visual identity that cannot load."""

    if style_playbook is None:
        return
    try:
        from styles.playbook_loader import list_playbooks, load_playbook

        load_playbook(style_playbook)
    except Exception as exc:
        try:
            available = list_playbooks()
        except Exception:
            available = []
        raise CheckpointValidationError(
            f"Unknown or invalid style_playbook {style_playbook!r}. "
            f"Available playbooks: {available}. Underlying error: {exc}"
        ) from exc


@lru_cache(maxsize=1)
def _load_checkpoint_schema() -> dict[str, Any]:
    with open(CHECKPOINT_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _validate_artifacts_for_stage(
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    pipeline_type: str | None = None,
) -> None:
    if not isinstance(artifacts, dict):
        raise CheckpointValidationError("Checkpoint artifacts must be a dictionary")
    if pipeline_type and pipeline_type != "unknown":
        required = next(
            s.get("produces", []) for s in _manifest_stages(pipeline_type)
            if s["name"] == stage
        )
    else:
        required = [CANONICAL_STAGE_ARTIFACTS[stage]] if stage in CANONICAL_STAGE_ARTIFACTS else []
    if status in {"completed", "awaiting_human"}:
        for artifact_name in required:
            if artifact_name not in artifacts:
                raise CheckpointValidationError(
                    f"Stage {stage!r} with status {status!r} must include "
                    f"declared artifact {artifact_name!r}"
                )

    for artifact_name, artifact_data in artifacts.items():
        if artifact_name not in ARTIFACT_NAMES:
            continue
        if not isinstance(artifact_data, dict):
            raise CheckpointValidationError(
                f"Artifact {artifact_name!r} must be a JSON object matching its schema"
            )
        try:
            validate_artifact(artifact_name, artifact_data)
        except Exception as exc:
            raise CheckpointValidationError(
                f"Artifact {artifact_name!r} failed schema validation: {exc}"
            ) from exc

    if stage == "compose" and status == "completed":
        from lib.delivery_validation import validate_final_delivery, DeliveryValidationError

        try:
            report = artifacts["render_report"]
            review = artifacts.get("final_review")
            # A single final_review identifies a single deliverable. Multiple
            # unreviewed outputs must not hitchhike on that acceptance.
            for output in report["outputs"]:
                validate_final_delivery(output["path"], review, report)
        except (KeyError, DeliveryValidationError) as exc:
            raise CheckpointValidationError(f"Final delivery rejected: {exc}") from exc


def validate_checkpoint(checkpoint: dict[str, Any]) -> None:
    """Validate checkpoint structure and canonical artifact payloads.

    Uses pipeline_type (if present) to resolve the valid stage list.
    Falls back to ALL_KNOWN_STAGES when pipeline_type is absent.
    """
    if not isinstance(checkpoint, dict):
        raise CheckpointValidationError("Checkpoint must be a JSON object")
    stage = checkpoint.get("stage")
    status = checkpoint.get("status")
    artifacts = checkpoint.get("artifacts")
    pipeline_type = checkpoint.get("pipeline_type")

    valid_stages = (
        set(get_pipeline_stages(pipeline_type)) if pipeline_type and pipeline_type != "unknown"
        else ALL_KNOWN_STAGES
    )

    if not isinstance(stage, str) or stage not in valid_stages:
        raise CheckpointValidationError(
            f"Invalid stage: {stage!r} for pipeline {pipeline_type!r}. "
            f"Valid stages: {sorted(valid_stages)}"
        )
    if not isinstance(status, str):
        raise CheckpointValidationError(f"Invalid status: {status!r}")
    if not isinstance(artifacts, dict):
        raise CheckpointValidationError("Checkpoint artifacts must be a dictionary")

    _validate_artifacts_for_stage(stage, status, artifacts, pipeline_type)

    try:
        jsonschema.validate(instance=checkpoint, schema=_load_checkpoint_schema())
    except jsonschema.ValidationError as exc:
        raise CheckpointValidationError(f"Checkpoint failed schema validation: {exc.message}") from exc


def _checkpoint_path(pipeline_dir: Path, project_id: str, stage: str) -> Path:
    return pipeline_dir / project_id / f"checkpoint_{stage}.json"


def init_project(
    project_id: str,
    *,
    title: str,
    pipeline_type: str,
    pipeline_dir: Optional[Path] = None,
    style_playbook: Optional[str] = None,
) -> Path:
    """Initialize a project workspace with the canonical layout + marker file.

    Creates projects/<project_id>/ with the standard subdirectories and writes
    project.json — the marker the Backlot board uses to render a project's
    identity and stage rail before the first checkpoint exists.

    Idempotent: preserves identity and created_at; only title can be refreshed.
    Returns the project directory.
    """
    _validate_style_playbook(style_playbook)
    _manifest_stages(pipeline_type)
    base = pipeline_dir or PROJECTS_DIR
    _project_identity(base, project_id, pipeline_type, style_playbook)
    with _serialized(base):
        return _init_project_locked(project_id, title, pipeline_type, base, style_playbook)


def _init_project_locked(
    project_id: str, title: str, pipeline_type: str,
    base: Path, style_playbook: str | None,
) -> Path:
    pipeline_type, style_playbook = _project_identity(
        base, project_id, pipeline_type, style_playbook
    )
    project_dir = base / project_id
    for sub in (
        "artifacts",
        "assets/images",
        "assets/video",
        "assets/audio",
        "assets/music",
        "renders",
    ):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    marker_path = project_dir / PROJECT_MARKER_FILENAME
    marker: dict[str, Any] = {}
    if marker_path.exists():
        with open(marker_path, encoding="utf-8") as f:
            marker = json.load(f)

    marker.setdefault("version", "1.0")
    marker.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    marker["project_id"] = project_id
    marker["title"] = title
    marker["pipeline_type"] = pipeline_type
    if style_playbook is not None:
        marker["style_playbook"] = style_playbook

    _atomic_json(marker_path, marker)

    return project_dir


def _stage_requires_approval(pipeline_type: Optional[str], stage: str) -> Optional[bool]:
    """Read human_approval_default for a stage from its pipeline manifest.

    Returns None when the stage isn't declared in the manifest or no
    pipeline_type was given — the caller then falls back to the value the
    agent passed in.

    A provided but unknown/broken manifest fails closed.
    """
    if not pipeline_type:
        return None
    for entry in _manifest_stages(pipeline_type):
        if entry["name"] == stage:
            return bool(entry.get("human_approval_default", False))
    return None


def _enforce_stage_prerequisites(
    pipeline_dir: Path,
    project_id: str,
    pipeline_type: str | None,
    stage: str,
    status: str,
) -> None:
    """Require completed, approved predecessors before advancing a stage.

    ``in_progress`` and failure heartbeats remain writable so an operator can
    inspect or resume a broken run. Only lifecycle advancement
    (``awaiting_human``/``completed``) is gated.
    """

    if status not in {"awaiting_human", "completed"}:
        return
    if not pipeline_type or pipeline_type == "unknown":
        return

    stages = get_pipeline_stages(pipeline_type)
    if stage not in stages:
        return

    incomplete: list[str] = []
    unapproved: list[str] = []
    for predecessor in stages[: stages.index(stage)]:
        path = _checkpoint_path(pipeline_dir, project_id, predecessor)
        if not path.exists():
            spec = next(s for s in _manifest_stages(pipeline_type) if s["name"] == predecessor)
            if spec.get("checkpoint_required", True):
                incomplete.append(predecessor)
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                checkpoint = json.load(handle)
            validate_checkpoint(checkpoint)
        except (OSError, json.JSONDecodeError, CheckpointValidationError):
            incomplete.append(predecessor)
            continue
        if (
            checkpoint.get("project_id") != project_id
            or checkpoint.get("pipeline_type") != pipeline_type
            or checkpoint.get("stage") != predecessor
        ):
            incomplete.append(predecessor)
            continue
        if checkpoint.get("status") != "completed":
            incomplete.append(predecessor)
            continue
        if (_stage_requires_approval(pipeline_type, predecessor) or checkpoint.get("human_approval_required")) and not checkpoint.get(
            "human_approved"
        ):
            unapproved.append(predecessor)

    if incomplete or unapproved:
        details = []
        if incomplete:
            details.append(f"incomplete or missing: {incomplete}")
        if unapproved:
            details.append(f"completed without required approval: {unapproved}")
        raise CheckpointValidationError(
            f"PREREQUISITE VIOLATION: stage {stage!r} cannot advance; "
            + "; ".join(details)
            + f". Pipeline order: {stages}."
        )


def _archive_superseded_checkpoint(path: Path, stage: str) -> None:
    """Copy an existing checkpoint into history/ before it is overwritten.

    Preserves the full run record: stage re-runs (script v1 → v2) and gate
    transitions (awaiting_human → completed) remain reconstructable. Repeated
    in_progress refreshes are NOT archived — they are partial-progress
    heartbeats, not versions.

    Archiving is best-effort and must never crash a checkpoint write: the
    Backlot watcher may hold the file open (Windows denies renames of open
    files), so we copy rather than move, and swallow archival I/O failures.
    """
    if not path.exists():
        return
    try:
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    except (json.JSONDecodeError, OSError):
        existing = {}
    if existing.get("status") == "in_progress":
        return

    try:
        import shutil
        stamp = str(existing.get("timestamp", ""))
        safe_stamp = "".join(c for c in stamp if c.isalnum()) or f"{path.stat().st_mtime_ns}"
        history_dir = path.parent / HISTORY_DIRNAME
        history_dir.mkdir(parents=True, exist_ok=True)
        target = history_dir / f"checkpoint_{stage}_{safe_stamp}.json"
        if target.exists():
            target = history_dir / f"checkpoint_{stage}_{safe_stamp}_{path.stat().st_mtime_ns}.json"
        shutil.copyfile(path, target)
    except OSError:
        import logging
        logging.getLogger(__name__).warning(
            "Could not archive superseded checkpoint %s to history/", path
        )


def _decision_log_path(pipeline_dir: Path, project_id: str) -> Path:
    return pipeline_dir / project_id / "decision_log.json"


def _merge_decision_log(
    pipeline_dir: Path, project_id: str, new_log: dict[str, Any]
) -> dict[str, Any]:
    """Validate and return a prospective cumulative log without writing it.

    Each stage may produce decisions. This function merges them into a
    single cumulative file so reviewers and the bench can inspect the
    full audit trail.
    """
    path = _decision_log_path(pipeline_dir, project_id)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                existing = json.load(f)
        except (ValueError, OSError) as exc:
            raise CheckpointValidationError(f"Cannot read cumulative decision_log: {exc}") from exc
    else:
        existing = {
            "version": "1.0",
            "project_id": project_id,
            "decisions": [],
        }

    for log in (existing, new_log):
        try:
            validate_artifact("decision_log", log)
            if log["project_id"] != project_id:
                raise ValueError("decision_log belongs to another project")
        except Exception as exc:
            raise CheckpointValidationError(f"Invalid decision_log: {exc}") from exc
    existing_ids = {d["decision_id"]: d for d in existing["decisions"]}
    if len(existing_ids) != len(existing["decisions"]):
        raise CheckpointValidationError("Duplicate decision_id in cumulative decision_log")
    for decision in new_log["decisions"]:
        old = existing_ids.get(decision["decision_id"])
        if old is not None and old != decision:
            raise CheckpointValidationError("decision_id cannot overwrite append-only history")
        if old is None:
            existing["decisions"].append(decision)
            existing_ids[decision["decision_id"]] = decision

    validate_artifact("decision_log", existing)
    return existing


def _serialized_writer(function):
    @wraps(function)
    def wrapped(pipeline_dir, project_id, stage, status, artifacts, **kwargs):
        pipeline_dir = Path(pipeline_dir)
        # Bad input cannot alter the workspace (including a pending journal).
        _validate_artifacts_for_stage(stage, "in_progress", artifacts)
        if "decision_log" in artifacts and artifacts["decision_log"]["project_id"] != project_id:
            raise CheckpointValidationError("decision_log belongs to another project")
        try:
            json.dumps({"artifacts": artifacts, **kwargs}, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise CheckpointValidationError(f"Checkpoint is not JSON serializable: {exc}") from exc
        _project_identity(pipeline_dir, project_id, kwargs.get("pipeline_type"), kwargs.get("style_playbook"))
        with _serialized(pipeline_dir):
            _recover_transaction(pipeline_dir / project_id)
            return function(pipeline_dir, project_id, stage, status, deepcopy(artifacts), **kwargs)
    return wrapped


@_serialized_writer
def write_checkpoint(
    pipeline_dir: Path,
    project_id: str,
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    *,
    pipeline_type: Optional[str] = None,
    style_playbook: Optional[str] = None,
    checkpoint_policy: str = "guided",
    human_approval_required: bool = False,
    human_approved: bool = False,
    review: Optional[dict] = None,
    cost_snapshot: Optional[dict] = None,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Path:
    """Write a checkpoint file for a pipeline stage."""
    pipeline_type, style_playbook = _project_identity(
        pipeline_dir, project_id, pipeline_type, style_playbook
    )

    valid_stages = (
        set(get_pipeline_stages(pipeline_type)) if pipeline_type
        else ALL_KNOWN_STAGES
    )
    if stage not in valid_stages:
        raise ValueError(
            f"Invalid stage: {stage!r} for pipeline {pipeline_type!r}. "
            f"Valid stages: {sorted(valid_stages)}"
        )

    # --- Gate enforcement (GI-4) ---
    # The pipeline manifest is the binding source of truth for whether a stage
    # gates on human approval; a caller may gate MORE strictly (e.g. a
    # manual_all checkpoint policy) but never less. A gated stage can only be
    # written "completed" with explicit evidence of approval
    # (human_approved=True). Skipping a gate is a hard error.
    #
    # Resume/prerequisite checks also reject old unapproved completion records.
    manifest_gate = _stage_requires_approval(pipeline_type, stage)
    gated = bool(manifest_gate) or human_approval_required
    if gated:
        human_approval_required = True
        if status == "completed" and not human_approved:
            gate_source = (
                f"human_approval_default: true in the {pipeline_type!r} manifest"
                if manifest_gate
                else "human_approval_required=True was passed by the caller"
            )
            raise CheckpointValidationError(
                f"GATE VIOLATION: stage {stage!r} requires human approval "
                f"({gate_source}) but status='completed' was written without "
                f"human_approved=True. Correct protocol: write "
                f"status='awaiting_human', present the artifact summary to the "
                f"user, END YOUR TURN, and only after the user approves "
                f"re-write with status='completed', human_approved=True."
            )

    _enforce_stage_prerequisites(
        pipeline_dir,
        project_id,
        pipeline_type,
        stage,
        status,
    )

    checkpoint = {
        "version": "1.0",
        "project_id": project_id,
        "pipeline_type": pipeline_type or "unknown",
        "stage": stage,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checkpoint_policy": checkpoint_policy,
        "human_approval_required": human_approval_required,
        "human_approved": human_approved,
        "artifacts": artifacts,
    }
    if style_playbook is not None:
        checkpoint["style_playbook"] = style_playbook
    if review is not None:
        checkpoint["review"] = review
    if cost_snapshot is not None:
        checkpoint["cost_snapshot"] = cost_snapshot
    if error is not None:
        checkpoint["error"] = error
    if metadata is not None:
        checkpoint["metadata"] = metadata

    # Merge decision_log: if this checkpoint carries new decisions,
    # append them to the project-level decision log file, then write the
    # reference back into relevant artifacts so downstream consumers can find it.
    cumulative_log = None
    if "decision_log" in artifacts and isinstance(artifacts["decision_log"], dict):
        cumulative_log = _merge_decision_log(pipeline_dir, project_id, artifacts["decision_log"])
        log_ref = str(_decision_log_path(pipeline_dir, project_id))

        # Write decision_log_ref into proposal_packet and render_report
        # artifacts if they are present in this checkpoint.
        for artifact_key in ("proposal_packet", "render_report"):
            if artifact_key in artifacts and isinstance(artifacts[artifact_key], dict):
                plan_or_top = artifacts[artifact_key]
                # proposal_packet stores it under production_plan
                if artifact_key == "proposal_packet":
                    plan = plan_or_top.get("production_plan")
                    if isinstance(plan, dict):
                        plan["decision_log_ref"] = log_ref
                else:
                    plan_or_top["decision_log_ref"] = log_ref

    validate_checkpoint(checkpoint)

    path = _checkpoint_path(pipeline_dir, project_id, stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A validated write-ahead journal makes the two-file update recoverable.
    # Readers using this API lock and roll forward before observing state.
    _archive_superseded_checkpoint(path, stage)
    _atomic_json(path.parent / ".checkpoint-transaction.json", {
        "checkpoint": checkpoint, "decision_log": cumulative_log,
    })
    _recover_transaction(path.parent)

    return path


def read_checkpoint(
    pipeline_dir: Path, project_id: str, stage: str
) -> Optional[dict[str, Any]]:
    """Read a checkpoint file. Returns None if not found."""
    if not Path(pipeline_dir).exists():
        return None
    with _serialized(Path(pipeline_dir)):
        _recover_transaction(Path(pipeline_dir) / project_id)
        return _read_checkpoint_unlocked(Path(pipeline_dir), project_id, stage)


def _read_checkpoint_unlocked(
    pipeline_dir: Path, project_id: str, stage: str, pipeline_type: str | None = None,
) -> dict[str, Any] | None:
    pipeline_type, _ = _project_identity(pipeline_dir, project_id, pipeline_type)
    path = _checkpoint_path(pipeline_dir, project_id, stage)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        checkpoint = json.load(f)
    validate_checkpoint(checkpoint)
    if (
        checkpoint["project_id"] != project_id or checkpoint["stage"] != stage
        or (pipeline_type is not None and checkpoint["pipeline_type"] != pipeline_type)
    ):
        raise CheckpointValidationError(f"Checkpoint ownership mismatch: {path}")
    return checkpoint


def get_latest_checkpoint(
    pipeline_dir: Path, project_id: str
) -> Optional[dict[str, Any]]:
    """Find the most recent checkpoint for a project (by file mtime)."""
    project_dir = pipeline_dir / project_id
    if not project_dir.exists():
        return None

    with _serialized(Path(pipeline_dir)):
        _recover_transaction(project_dir)
        checkpoints = sorted(
            project_dir.glob("checkpoint_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not checkpoints:
            return None
        stage = checkpoints[0].stem.removeprefix("checkpoint_")
        return _read_checkpoint_unlocked(Path(pipeline_dir), project_id, stage)


def _resume_pipeline(
    pipeline_dir: Path, project_id: str, pipeline_type: str | None,
) -> str | None:
    pipeline_type, _ = _project_identity(pipeline_dir, project_id, pipeline_type)
    if pipeline_type is not None:
        return pipeline_type
    # Older projects without project.json can be inferred only if all saved
    # records agree. Never choose an arbitrary file's identity.
    identities = set()
    for path in (pipeline_dir / project_id).glob("checkpoint_*.json"):
        checkpoint = _read_checkpoint_unlocked(
            pipeline_dir, project_id, path.stem.removeprefix("checkpoint_")
        )
        identities.add(checkpoint["pipeline_type"])
    if len(identities) > 1:
        raise CheckpointValidationError("Conflicting pipeline identities in legacy project")
    inferred = next(iter(identities), None)
    return None if inferred == "unknown" else inferred


def _completed_stages_unlocked(
    pipeline_dir: Path, project_id: str, pipeline_type: str | None,
) -> list[str]:
    completed = []
    for stage in get_pipeline_stages(pipeline_type):
        cp = _read_checkpoint_unlocked(pipeline_dir, project_id, stage, pipeline_type)
        if cp and cp["status"] == "completed":
            if (_stage_requires_approval(pipeline_type, stage) or cp.get("human_approval_required")) and not cp.get("human_approved"):
                raise CheckpointValidationError(
                    f"Stage {stage!r} completed without required approval"
                )
            completed.append(stage)
    return completed


def get_completed_stages(
    pipeline_dir: Path, project_id: str, pipeline_type: str | None = None
) -> list[str]:
    """Return list of stages that have a completed checkpoint.

    When pipeline_type is provided, only checks stages defined in that
    pipeline's manifest — preventing false positives from leftover
    checkpoints of a different pipeline type.
    """
    with _serialized(Path(pipeline_dir)):
        _recover_transaction(Path(pipeline_dir) / project_id)
        pipeline_type = _resume_pipeline(Path(pipeline_dir), project_id, pipeline_type)
        return _completed_stages_unlocked(Path(pipeline_dir), project_id, pipeline_type)


def get_next_stage(
    pipeline_dir: Path, project_id: str, pipeline_type: str | None = None
) -> Optional[str]:
    """Determine the next stage to run based on completed checkpoints.

    Uses pipeline-specific stage order so that pipelines with different
    stage sequences (e.g. cinematic vs explainer) progress correctly.
    """
    pipeline_dir = Path(pipeline_dir)
    with _serialized(pipeline_dir):
        _recover_transaction(pipeline_dir / project_id)
        pipeline_type = _resume_pipeline(pipeline_dir, project_id, pipeline_type)
        stages = get_pipeline_stages(pipeline_type)
        completed = set(_completed_stages_unlocked(pipeline_dir, project_id, pipeline_type))
        optional = {
            s["name"] for s in _manifest_stages(pipeline_type)
            if not s.get("checkpoint_required", True)
        } if pipeline_type else set()
        for stage in stages:
            if stage in optional and not _checkpoint_path(pipeline_dir, project_id, stage).exists():
                continue
            if stage not in completed:
                return stage
        return None
