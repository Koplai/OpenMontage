"""OpenAI Sora video generation via the OpenAI Video API."""

from __future__ import annotations

import base64
import mimetypes
import os
import time
from pathlib import Path
from typing import Any
from lib.provider_jobs import Deadline, ProviderJob, safe_sdk_read, reject_unsupported_media, JOB_INPUT_PROPERTIES

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ResumeSupport,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


_DEFAULT_MODEL = "sora-2"
_DEFAULT_SIZE = "720x1280"
_DEFAULT_SECONDS = "4"
_ALLOWED_MODELS = ["sora-2", "sora-2-pro"]
_ALLOWED_SIZES = ["1280x720", "720x1280", "1024x1792", "1792x1024"]
_ALLOWED_SECONDS = ["4", "8", "12"]
_MIN_OPENAI_VERSION = (2, 44, 0)


class SoraVideo(BaseTool):
    name = "sora_video"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "openai"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API
    resume_support = ResumeSupport.FROM_CHECKPOINT

    dependencies = []
    install_instructions = (
        "Set OPENAI_API_KEY to your OpenAI API key with Sora API access.\n"
        "  pip install 'openai>=2.44.0'"
    )
    agent_skills = ["ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "native_audio": True,
        "camera_direction": True,
        "social_ads": True,
        "short_clips": True,
    }
    best_for = [
        "OpenAI Sora 2 / Sora 2 Pro clips from the project .env credentials",
        "short cinematic product-ad inserts with native ambience or dialogue",
        "4, 8, or 12 second social-video clips that OpenMontage can stitch and compose",
    ]
    not_good_for = ["offline generation", "long continuous scenes", "projects without Sora API access"]
    fallback_tools = ["veo_video", "gemini_omni_video", "seedance_video", "kling_video", "minimax_video"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            **JOB_INPUT_PROPERTIES,
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video"],
                "default": "text_to_video",
            },
            "model": {
                "type": "string",
                "enum": _ALLOWED_MODELS,
                "default": _DEFAULT_MODEL,
            },
            "size": {
                "type": "string",
                "enum": _ALLOWED_SIZES,
                "default": _DEFAULT_SIZE,
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16"],
                "default": "9:16",
                "description": "Selector-friendly alias used to choose 1280x720 or 720x1280 when size is omitted.",
            },
            "seconds": {
                "type": "string",
                "enum": _ALLOWED_SECONDS,
                "default": _DEFAULT_SECONDS,
            },
            "duration": {
                "type": "string",
                "description": "Alias for seconds. Must be one of 4, 8, or 12.",
            },
            "input_reference_path": {
                "type": "string",
                "description": "Optional jpg/png/webp reference image for image-to-video.",
            },
            "reference_image_path": {
                "type": "string",
                "description": "Alias for input_reference_path.",
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=1000, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=0)
    idempotency_key_fields = ["prompt", "model", "size", "seconds"]
    side_effects = ["writes video file to output_path", "calls OpenAI Video API"]
    user_visible_verification = ["Watch generated clip for motion coherence, artifacts, and audio quality"]

    def get_status(self) -> ToolStatus:
        if not os.environ.get("OPENAI_API_KEY"):
            return ToolStatus.UNAVAILABLE
        if not self._openai_sdk_supports_videos():
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        seconds = int(self._normalize_seconds(inputs))
        # Placeholder estimate until the registry has live OpenAI video pricing.
        return 0.50 * (seconds / 4)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        seconds = int(self._normalize_seconds(inputs))
        return 120.0 * (seconds / 4)

    def normalize_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        reject_unsupported_media(inputs, {*self.input_schema["properties"], "image_path"})
        normalized = dict(inputs)
        normalized["model"] = self._normalize_model(inputs)
        normalized["size"] = self._normalize_size(inputs, normalized["model"])
        normalized["seconds"] = self._normalize_seconds(inputs)
        normalized.pop("duration", None)
        normalized.pop("aspect_ratio", None)
        reference = inputs.get("input_reference_path") or inputs.get("reference_image_path") or inputs.get("image_path")
        for key in ("reference_image_path", "image_path"):
            normalized.pop(key, None)
        operation = inputs.get("operation", "image_to_video" if reference else "text_to_video")
        if operation not in self.capabilities:
            raise ValueError(f"Unsupported Sora operation: {operation}")
        if any(inputs.get(k) for k in (
            "image_url", "reference_image_url", "reference_image_urls", "reference_image_paths",
            "video_url", "video_path", "reference_video_url",
        )):
            raise ValueError("Sora requires a single local input_reference_path; unsupported references cannot be ignored")
        if operation == "image_to_video" and not reference:
            raise ValueError("image_to_video requires input_reference_path")
        if reference:
            normalized["input_reference_path"] = reference
        normalized["operation"] = operation
        return normalized

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if not os.environ.get("OPENAI_API_KEY"):
            return ToolResult(
                success=False,
                error="OPENAI_API_KEY not set. " + self.install_instructions,
                cost_status="not_submitted",
            )
        if not self._openai_sdk_supports_videos():
            return ToolResult(
                success=False,
                error="OpenAI SDK with Videos API support is required. " + self.install_instructions,
                cost_status="not_submitted",
            )

        from openai import OpenAI

        start = time.monotonic()
        job = None
        try:
            inputs = self.normalize_inputs(inputs)
            model, size, seconds = inputs["model"], inputs["size"], inputs["seconds"]
            prompt = str(inputs["prompt"]).strip()
            payload = {"model": model, "prompt": prompt, "size": size, "seconds": seconds}
            if inputs.get("input_reference_path"):
                reference = Path(inputs["input_reference_path"])
                if not reference.is_file():
                    raise ValueError("Input reference is not a file")
                payload["input_reference"] = {"image_url": self._file_to_data_uri(reference)}
            deadline = Deadline(inputs.get("timeout_seconds", 900))
            job = ProviderJob.open(inputs, self.provider, model, self.estimate_cost(inputs))
            job.require_resumable()
            client = OpenAI(max_retries=0, timeout=deadline.remaining(30))
            if job.should_submit:
                job.submitting()
                video = client.videos.create(**payload, timeout=deadline.remaining(30))
                job.submitted(self._get_video_id(video))
            video_id = job.job_id
            if not job.record.get("staged"):
                while True:
                    video = safe_sdk_read(
                        lambda: client.videos.retrieve(video_id, timeout=deadline.remaining(30)), deadline)
                    status = self._get_status_value(video)
                    if status == "completed":
                        job.update(state="generated")
                        break
                    if status in {"failed", "cancelled"}:
                        job.update(state="failed")
                        raise RuntimeError(f"Sora generation {status}")
                    if status not in {"queued", "in_progress"}:
                        raise ValueError("Unexpected Sora status")
                    deadline.sleep(float(inputs.get("poll_interval", 5)))
                content = safe_sdk_read(lambda: client.videos.download_content(
                    video_id, variant="video", timeout=deadline.remaining(120)), deadline)
                temporary = job.path.with_suffix(".download")
                try:
                    self._write_download(content, temporary)
                    job.stage([temporary.read_bytes()])
                finally:
                    temporary.unlink(missing_ok=True)
                deadline.remaining()
            output_path = Path(inputs.get("output_path", job.root / "sora_output.mp4"))
            job.deliver([output_path])
        except Exception as exc:
            return job.failure(exc) if job else ToolResult(success=False, error=str(exc), cost_status="not_submitted")

        return ToolResult(
            success=True,
            data={
                "provider": "openai",
                "model": model,
                "video_id": video_id,
                "prompt": prompt,
                "output": str(output_path),
                "size": size,
                "seconds": seconds,
                "format": "mp4",
                **job.metadata(),
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.monotonic() - start, 2),
            model=model,
            cost_status="estimated",
            provider_request_id=video_id,
        )

    def validate_paid_recovery(self, inputs: dict[str, Any]) -> None:
        inputs = self.normalize_inputs(inputs)
        ProviderJob.validate_recovery(inputs, self.provider, inputs["model"], self.estimate_cost(inputs))

    @classmethod
    def _openai_sdk_supports_videos(cls) -> bool:
        try:
            import openai
            from openai import OpenAI
        except Exception:
            return False

        if cls._version_tuple(getattr(openai, "__version__", "")) < _MIN_OPENAI_VERSION:
            return False
        client = OpenAI()
        try:
            videos = getattr(client, "videos", None)
            return all(callable(getattr(videos, name, None)) for name in ("create", "retrieve", "download_content"))
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _version_tuple(version: str) -> tuple[int, int, int]:
        parts = []
        for part in version.split(".")[:3]:
            digits = "".join(ch for ch in part if ch.isdigit())
            parts.append(int(digits or "0"))
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)

    @staticmethod
    def _normalize_model(inputs: dict[str, Any]) -> str:
        model = str(inputs.get("model", _DEFAULT_MODEL)).strip().lower()
        if model not in _ALLOWED_MODELS:
            raise ValueError("model must be one of: sora-2, sora-2-pro")
        return model

    @staticmethod
    def _normalize_size(inputs: dict[str, Any], model: str) -> str:
        default_size = "1280x720" if inputs.get("aspect_ratio") == "16:9" else _DEFAULT_SIZE
        size = str(inputs.get("size", default_size)).strip().lower()
        allowed = {"1280x720", "720x1280"} if model == "sora-2" else set(_ALLOWED_SIZES)
        if size not in allowed:
            raise ValueError(f"size must be one of: {', '.join(sorted(allowed))} for model {model}")
        return size

    @staticmethod
    def _normalize_seconds(inputs: dict[str, Any]) -> str:
        seconds = str(inputs.get("seconds") or inputs.get("duration") or _DEFAULT_SECONDS).strip().lower()
        seconds = seconds[:-1] if seconds.endswith("s") else seconds
        if seconds not in _ALLOWED_SECONDS:
            raise ValueError("seconds must be one of: 4, 8, 12")
        return seconds

    @staticmethod
    def _get_status_value(video: Any) -> str:
        if isinstance(video, dict):
            return str(video.get("status") or video.get("state") or "unknown")
        return str(getattr(video, "status", None) or getattr(video, "state", None) or "unknown")

    @staticmethod
    def _get_video_id(video: Any) -> str | None:
        if isinstance(video, dict):
            value = video.get("id")
            return value if isinstance(value, str) else None
        value = getattr(video, "id", None)
        return value if isinstance(value, str) else None

    @staticmethod
    def _file_to_data_uri(path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(path.name)
        if not mime_type:
            mime_type = "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _write_download(content: Any, output_path: Path) -> None:
        if hasattr(content, "write_to_file"):
            content.write_to_file(output_path)
            return
        if hasattr(content, "read"):
            output_path.write_bytes(content.read())
            return
        if hasattr(content, "content"):
            output_path.write_bytes(content.content)
            return
        output_path.write_bytes(bytes(content))
