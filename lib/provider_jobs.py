"""Small durable submission/delivery boundary for workstation provider adapters.

The journal contains identities and hashes, never prompts, credentials, signed
URLs or request bodies. A submit intent is fsynced *before* a paid POST; an
interrupted POST without a job ID is deliberately not automatically retried.
"""

from __future__ import annotations

import hashlib
import errno
import json
import math
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_CONTROL_KEYS = {
    "project_dir", "project_path", "output_path", "output_dir", "recovery_id",
    "timeout_seconds", "poll_interval", "approval_id", "approval_token",
    "request_approval_id", "reservation_id", "task_context", "scene_id",
    "preferred_provider", "allowed_providers",
}
_SECRET_KEY = re.compile(r"(^|_)(key|secret|token|authorization|password|credential)(_|$)", re.I)
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,256}\Z")
_MEDIA_INPUTS = {
    "image", "images", "image_url", "image_path", "image_urls", "image_paths",
    "input_reference", "input_reference_url", "input_reference_path",
    "reference_image", "reference_image_url", "reference_image_path",
    "reference_image_urls", "reference_image_paths", "image_list", "element_list",
    "end_image_url", "reference_tail_image_url", "reference_tail_image_path",
    "video", "video_url", "video_path", "video_urls", "video_paths", "video_list",
    "reference_video_url", "reference_video_path", "reference_video_urls", "reference_video_paths",
    "input_video_path", "previous_interaction_id",
    "reference_audio_url", "reference_audio_urls", "reference_audio_paths",
}
_LOCAL_REFERENCE_KEYS = (_MEDIA_INPUTS - {"element_list", "previous_interaction_id"}) | {
    "path", "file", "files", "reference_images", "reference_video", "reference_audio",
    "audio", "audios", "audio_url", "audio_urls", "videos",
    "last_image", "last_image_url", "image_tail", "first_frame", "first_frame_url",
    "mask", "mask_url", "mask_image",
}
JOB_INPUT_PROPERTIES = {
    "project_dir": {"type": "string", "description": "Initialized project workspace; required for durable paid work."},
    "recovery_id": {"type": "string", "description": "Resume the same project-bound request; never submit a new generation."},
    "generation_id": {"type": "string", "description": "Identity of an explicitly approved fresh generation, not an uncertain retry."},
    "timeout_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600,
                        "description": "Monotonic invocation budget; defaults to 900 seconds (Seedream image: 300)."},
    "poll_interval": {"type": "number", "exclusiveMinimum": 0, "description": "Positive polling interval in seconds."},
}


def reject_unsupported_media(inputs: dict, supported) -> None:
    unsupported = sorted(key for key in _MEDIA_INPUTS if inputs.get(key) and key not in supported)
    if unsupported:
        raise ValueError(f"Unsupported media inputs cannot be ignored: {', '.join(unsupported)}")


def local_media_digest(key: str, value: Any) -> str | None:
    """Shared approval/recovery binding for an explicitly local media value.

    Callers retain the same key when descending lists. Only declared media
    aliases or path/file fields may trigger filesystem access, never prompt
    strings. HTTP(S)/data references are opaque values, not local paths.
    """
    if (key.startswith("output") or key in _CONTROL_KEYS or _SECRET_KEY.search(key)
            or not isinstance(value, (str, Path))):
        return None
    if key not in _LOCAL_REFERENCE_KEYS and not key.endswith(("_path", "_paths", "_file", "_files")):
        return None
    if str(value).lstrip().lower().startswith(("http:", "https:", "data:")):
        return None
    path = Path(value).expanduser()
    try:
        is_file = path.is_file()
    except OSError as exc:
        if exc.errno == errno.ENAMETOOLONG:
            # Native image values may be raw base64 rather than filenames.
            return None
        raise
    if not is_file:
        return None
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def request_fingerprint(inputs: dict[str, Any]) -> str:
    """Hash effective content; changing bytes at a reference path changes identity."""
    def content(value, key=""):
        if isinstance(value, dict):
            return {k: content(v, k) for k, v in sorted(value.items())
                    if k not in _CONTROL_KEYS and not _SECRET_KEY.search(k)}
        if isinstance(value, (list, tuple)):
            return [content(v, key) for v in value]
        digest = local_media_digest(key, value)
        if digest is not None:
            return {"sha256": digest}
        return str(value) if isinstance(value, Path) else value

    encoded = json.dumps(content(inputs), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temp).unlink(missing_ok=True)


class Deadline:
    def __init__(self, seconds: float = 900):
        if not math.isfinite(float(seconds)) or not 0 < float(seconds) <= 3600:
            raise ValueError("timeout_seconds must be finite and between 0 and 3600")
        self.end = time.monotonic() + float(seconds)

    def remaining(self, maximum: float = 3600) -> float:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Provider deadline exceeded; resume the recorded recovery_id")
        return min(remaining, maximum)

    def sleep(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("poll_interval must be positive and finite")
        time.sleep(min(seconds, self.remaining()))


class ProviderJob:
    """One project-bound paid request, not a workflow/orchestration engine."""

    @classmethod
    def open(cls, inputs: dict, provider: str, model: str, estimate: float, *, read_only: bool = False):
        from lib.events import infer_project_dir

        root_value = inputs.get("project_dir") or inputs.get("project_path") or infer_project_dir(inputs)
        if not root_value:
            raise ValueError("Provider submission requires an initialized project_dir")
        root = Path(root_value).resolve()
        if not math.isfinite(estimate) or estimate < 0:
            raise ValueError("Provider cost estimate must be finite and nonnegative")
        if "poll_interval" in inputs:
            interval = float(inputs["poll_interval"])
            if not math.isfinite(interval) or interval <= 0:
                raise ValueError("poll_interval must be positive and finite")
        for key in ("output_path", "output_dir"):
            if inputs.get(key) and not Path(inputs[key]).resolve().is_relative_to(root):
                raise ValueError(f"{key} must remain inside the provider recovery project")
        marker = root / "project.json"
        if not marker.is_file() or marker.is_symlink():
            raise ValueError("Provider submission requires an initialized project.json")
        identity = json.loads(marker.read_text())
        project_id = identity.get("project_id") or identity.get("id")
        if not project_id:
            raise ValueError("project.json is missing project_id")
        project_identity = hashlib.sha256(f"{root}:{project_id}".encode()).hexdigest()
        fingerprint = request_fingerprint({"provider": provider, "model": model, "inputs": inputs})
        recovery_id = inputs.get("recovery_id") or fingerprint
        if not re.fullmatch(r"[0-9a-f]{64}", str(recovery_id)):
            raise ValueError("Invalid recovery_id")
        directory = root / ".provider_jobs"
        if not read_only:
            directory.mkdir(mode=0o700, exist_ok=True)
        if directory.is_symlink() or directory.resolve().parent != root:
            raise ValueError("Provider journal must remain inside its project")
        job = cls()
        job.root, job.path = root, directory / f"{recovery_id}.json"
        job.recovery_id = recovery_id
        job.is_recovery = bool(inputs.get("recovery_id"))
        if read_only:
            if not job.path.is_file() or job.path.is_symlink():
                raise ValueError("Unknown recovery_id in this project")
            job.record = json.loads(job.path.read_text())
            if (job.record.get("project_identity") != project_identity
                    or job.record.get("request_fingerprint") != fingerprint):
                raise ValueError("recovery_id does not match this project/request")
            return job
        with job._lock():
            if job.path.exists():
                job.record = json.loads(job.path.read_text())
                if (job.record.get("project_identity") != project_identity
                        or job.record.get("request_fingerprint") != fingerprint):
                    raise ValueError("recovery_id does not match this project/request")
            else:
                if inputs.get("recovery_id"):
                    raise ValueError("Unknown recovery_id in this project")
                job.record = {
                    "version": 1, "project_identity": project_identity,
                    "request_fingerprint": fingerprint, "provider": provider, "model": model,
                    "state": "prepared", "estimated_cost_usd": estimate, "job_id": None,
                }
                job._save()
        return job

    @classmethod
    def validate_recovery(cls, inputs: dict, provider: str, model: str, estimate: float) -> None:
        """Read-only proof for BaseTool's same-reservation delivery/GET route."""
        if not inputs.get("recovery_id"):
            raise ValueError("Verified recovery requires recovery_id")
        job = cls.open(inputs, provider, model, estimate, read_only=True)
        if job.should_submit:
            raise ValueError("Recovery cannot submit a prepared request")
        job.require_resumable()
        if job.job_id and not _ID.fullmatch(str(job.job_id)):
            raise ValueError("Invalid stored provider job identity")
        for index, digest in enumerate(job.record.get("staged") or []):
            path = job.path.with_suffix(f".{index}.bin")
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("Staged provider output is damaged")

    @contextmanager
    def _lock(self):
        import fcntl

        lock_path = self.path.with_suffix(".lock")
        if self.path.is_symlink() or lock_path.is_symlink():
            raise ValueError("Provider journal cannot be a symlink")
        with lock_path.open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _save(self):
        atomic_write(self.path, json.dumps(self.record, sort_keys=True).encode())

    def update(self, **values):
        with self._lock():
            self.record = json.loads(self.path.read_text())
            self.record.update(values)
            self._save()

    @property
    def should_submit(self):
        return self.record["state"] == "prepared"

    @property
    def job_id(self):
        return self.record.get("job_id")

    def submitting(self):
        if self.is_recovery:
            raise ValueError("A recovery invocation cannot submit a new paid request")
        with self._lock():
            self.record = json.loads(self.path.read_text())
            if self.record["state"] != "prepared":
                raise RuntimeError("Submission already claimed; outcome may be uncertain")
            self.record["state"] = "submitting"
            self._save()

    def submitted(self, job_id: str):
        if not isinstance(job_id, str) or not _ID.fullmatch(job_id):
            raise ValueError("Provider returned an invalid job identity")
        self.update(state="submitted", job_id=job_id)
        # The provider journal is authoritative for delivery recovery; record
        # the same accepted ID in the active budget reservation before polling.
        from lib.budget import record_paid_submission
        record_paid_submission(job_id)

    def require_resumable(self):
        if not self.should_submit and not self.job_id and not self.record.get("staged"):
            raise RuntimeError("Submission outcome uncertain; reconcile with provider before any new generation")

    def stage(self, outputs: list[bytes]):
        hashes = []
        for index, content in enumerate(outputs):
            if not content:
                raise ValueError("Provider returned empty media")
            atomic_write(self.path.with_suffix(f".{index}.bin"), content)
            hashes.append(hashlib.sha256(content).hexdigest())
        self.update(state="generated", staged=hashes)

    def deliver(self, paths: list[Path]):
        hashes = self.record.get("staged") or []
        if not hashes or len(paths) != len(hashes):
            raise ValueError("No complete staged output set is available")
        for index, (path, digest) in enumerate(zip(paths, hashes)):
            path = Path(path)
            if not path.resolve().is_relative_to(self.root):
                raise ValueError("Provider delivery must remain inside its project")
            content = self.path.with_suffix(f".{index}.bin").read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("Staged provider output is damaged; do not regenerate automatically")
            atomic_write(path, content)
        self.update(state="delivered")

    def metadata(self):
        state = self.record["state"]
        metadata = {
            "provider": self.record["provider"], "model": self.record["model"],
            "request_fingerprint": self.record["request_fingerprint"],
            "recovery_id": self.recovery_id, "job_id": self.job_id,
            "remote_task_id": self.job_id,
            "submission_state": state, "recovery_state": state,
            "estimated_cost_usd": self.record["estimated_cost_usd"],
        }
        if state != "prepared":
            # "Known" means settled billing, not merely a known job identity.
            # None of these adapters receives authoritative per-job billing.
            metadata["cost_status"] = "unknown"
        return metadata

    def failure(self, exc: Exception):
        from tools.base_tool import ToolResult

        # Exception bodies can contain request URLs, prompt text or API tokens.
        return ToolResult(
            success=False, data={**self.metadata(), "failure_type": type(exc).__name__},
            error=f"{type(exc).__name__}: provider {self.record['state']}; "
                  f"resume recovery_id={self.recovery_id}. "
                  "If submission is uncertain without a job ID, reconcile with the provider first.",
            cost_usd=0.0 if self.should_submit else self.record["estimated_cost_usd"],
            model=self.record["model"],
            cost_status="not_submitted" if self.should_submit else "unknown",
            provider_request_id=self.job_id,
        )


def safe_get(get, url: str, deadline: Deadline, **kwargs):
    """Retry only idempotent reads, within the caller's end-to-end budget."""
    import requests

    for attempt in range(3):
        try:
            response = get(url, timeout=deadline.remaining(30), **kwargs)
            response.raise_for_status()
            deadline.remaining()
            return response
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt == 2 or (status and status not in {408, 429} and status < 500):
                raise
            deadline.sleep(1 + attempt)


def safe_sdk_read(call, deadline: Deadline):
    """OpenAI GETs keep bounded retries even though paid SDK POST retries are off."""
    import requests

    for attempt in range(3):
        try:
            result = call()
            deadline.remaining()
            return result
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            retryable = (
                isinstance(exc, (requests.RequestException, TimeoutError))
                or type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}
                or status in {408, 429} or (isinstance(status, int) and status >= 500)
            )
            if not retryable or attempt == 2:
                raise
            deadline.sleep(attempt + 1)


def fal_result(job: ProviderJob, endpoint: str, payload: dict, api_key: str,
               deadline: Deadline, poll_interval: float = 5) -> dict:
    """Submit once and poll a fal queue job. Signed output URLs stay in memory."""
    import requests

    headers = {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}
    job.require_resumable()
    if job.should_submit:
        job.submitting()
        response = requests.post(f"https://queue.fal.run/{endpoint}", headers=headers,
                                 json=payload, timeout=deadline.remaining(30))
        response.raise_for_status()
        queued = response.json()
        request_id = queued.get("request_id")
        if not request_id and queued.get("response_url"):
            request_id = urlsplit(queued["response_url"]).path.rsplit("/", 1)[-1]
        job.submitted(request_id)
        paths = {}
        for key in ("status_url", "response_url"):
            if queued.get(key):
                url = urlsplit(queued[key])
                if (url.scheme != "https" or url.netloc != "queue.fal.run"
                        or url.query or url.fragment
                        or f"/requests/{request_id}" not in url.path):
                    raise ValueError("Unexpected fal queue URL; recover using the job ID")
                paths[key.replace("_url", "_path")] = url.path
        job.update(**paths)
    route = "/".join(endpoint.split("/")[:2])
    response_path = job.record.get("response_path") or f"/{route}/requests/{job.job_id}"
    status_path = job.record.get("status_path") or f"{response_path}/status"
    while True:
        status = safe_get(requests.get, f"https://queue.fal.run{status_path}", deadline,
                          headers=headers).json().get("status")
        if status == "COMPLETED":
            job.update(state="generated")
            break
        if status in {"FAILED", "CANCELLED"}:
            job.update(state="failed")
            raise RuntimeError(f"Provider job {status}")
        if status not in {"IN_QUEUE", "IN_PROGRESS"}:
            raise ValueError("Unexpected fal queue status")
        deadline.sleep(float(poll_interval))
    return safe_get(requests.get, f"https://queue.fal.run{response_path}", deadline,
                    headers=headers).json()


def upload_fal_image(image_path: str, api_key: str, deadline: Deadline) -> str:
    """The existing fal storage protocol, with the generation call's deadline."""
    import mimetypes
    import requests

    path = Path(image_path)
    content_type = mimetypes.guess_type(path.name)[0] or "image/png"
    content = path.read_bytes()
    response = requests.post(
        "https://rest.alpha.fal.ai/storage/upload/initiate",
        headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
        json={"content_type": content_type, "file_name": path.name},
        timeout=deadline.remaining(30),
    )
    response.raise_for_status()
    upload = response.json()
    response = requests.put(upload["upload_url"], headers={"Content-Type": content_type},
                            data=content, timeout=deadline.remaining(60))
    response.raise_for_status()
    deadline.remaining()
    return upload["file_url"]


def sdk_available(module_name: str, symbol: str) -> bool:
    import importlib

    try:
        return callable(getattr(importlib.import_module(module_name), symbol, None))
    except (ImportError, OSError):
        return False
