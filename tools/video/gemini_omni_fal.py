"""Gemini Omni Flash generation and editing through fal.ai."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from lib.provider_jobs import Deadline, ProviderJob, fal_result, safe_get, upload_fal_image, reject_unsupported_media, JOB_INPUT_PROPERTIES

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


class GeminiOmniFalVideo(BaseTool):
    name = "gemini_omni_fal"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "gemini_omni"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API
    resume_support = ResumeSupport.FROM_CHECKPOINT
    agent_skills = ["gemini-omni", "ai-video-gen"]
    capabilities = [
        "text_to_video",
        "image_to_video",
        "reference_to_video",
        "edit_video",
    ]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "reference_to_video": True,
        "video_to_video": True,
        "multiple_reference_images": True,
        "native_audio": True,
    }
    best_for = [
        "Gemini Omni Flash with a fal.ai key",
        "reference-image-driven 3-10 second video with synchronized audio",
    ]
    not_good_for = ["Google interaction-id workflows", "offline generation"]
    fallback_tools = ["gemini_omni_video", "runway_video", "veo_video"]
    dependencies = ["env:FAL_KEY"]
    install_instructions = (
        "Set FAL_KEY (or FAL_AI_API_KEY) from https://fal.ai/dashboard/keys."
    )
    quality_score = 0.85
    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            **JOB_INPUT_PROPERTIES,
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": [
                    "text_to_video",
                    "image_to_video",
                    "reference_to_video",
                    "edit_video",
                ],
                "default": "text_to_video",
            },
            "image_url": {"type": "string"},
            "image_path": {"type": "string"},
            "reference_image_urls": {"type": "array", "items": {"type": "string"}},
            "reference_image_paths": {"type": "array", "items": {"type": "string"}},
            "video_url": {
                "type": "string",
                "description": "Source clip for edit_video",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16"],
                "default": "16:9",
            },
            "duration": {"type": "integer", "minimum": 3, "maximum": 10, "default": 8},
            "output_path": {"type": "string"},
        },
    }
    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=0)
    idempotency_key_fields = [
        "prompt",
        "operation",
        "aspect_ratio",
        "duration",
        "reference_image_urls",
    ]
    side_effects = ["writes video file to output_path", "calls fal.ai API"]
    user_visible_verification = ["Watch the clip and listen for synchronized audio"]

    @staticmethod
    def _api_key() -> str | None:
        return os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if self._api_key() else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return round(0.13 * int(inputs.get("duration", 8)), 2)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 90.0

    def normalize_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        reject_unsupported_media(inputs, self.input_schema["properties"])
        normalized = dict(inputs)
        if inputs.get("model") or inputs.get("model_name"):
            raise ValueError("Gemini Omni fal has fixed operation-specific endpoints, not a model override")
        refs = inputs.get("reference_image_urls") or inputs.get("reference_image_paths")
        single = inputs.get("image_url") or inputs.get("image_path")
        normalized.setdefault("operation", "reference_to_video" if refs else (
            "image_to_video" if single else "text_to_video"))
        operation = normalized["operation"]
        if operation not in self.capabilities:
            raise ValueError(f"Unsupported Gemini Omni operation: {operation}")
        count = len(inputs.get("reference_image_urls") or []) + len(inputs.get("reference_image_paths") or []) + bool(single)
        if operation in {"text_to_video", "edit_video"} and count:
            raise ValueError(f"{operation} does not accept reference images on fal.ai")
        if operation in {"image_to_video", "reference_to_video"} and not count:
            raise ValueError(f"{operation} requires at least one reference image")
        if operation == "image_to_video" and count != 1:
            raise ValueError("image_to_video accepts exactly one image; use reference_to_video")
        if operation == "edit_video" and not inputs.get("video_url"):
            raise ValueError("edit_video requires video_url")
        if inputs.get("video_path") or (operation != "edit_video" and inputs.get("video_url")):
            raise ValueError("Source video is only supported as video_url in edit_video")
        if any(inputs.get(k) for k in ("reference_video_urls", "reference_audio_urls")):
            raise ValueError("Gemini Omni fal does not implement video/audio reference arrays")
        normalized.setdefault("duration", 8)
        normalized.setdefault("aspect_ratio", "16:9")
        if not 3 <= int(normalized["duration"]) <= 10:
            raise ValueError("duration must be between 3 and 10")
        return normalized

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = self._api_key()
        if not api_key:
            return ToolResult(
                success=False, error="FAL_KEY not set. " + self.install_instructions, cost_status="not_submitted"
            )
        import requests
        from tools.video._shared import probe_output

        started = time.monotonic()
        job = None
        endpoints = {
            "text_to_video": "google/gemini-omni-flash",
            "image_to_video": "google/gemini-omni-flash/image-to-video",
            "reference_to_video": "google/gemini-omni-flash/reference-to-video",
            "edit_video": "google/gemini-omni-flash/edit",
        }
        try:
            inputs = self.normalize_inputs(inputs)
            operation = inputs["operation"]
            endpoint = endpoints[operation]
            deadline = Deadline(inputs.get("timeout_seconds", 900))
            job = ProviderJob.open(inputs, self.provider, endpoint, self.estimate_cost(inputs))
            job.require_resumable()
            payload = {}
            if job.should_submit:
                urls = list(inputs.get("reference_image_urls") or [])
                local_paths = list(inputs.get("reference_image_paths") or [])
                if inputs.get("image_path") and not inputs.get("image_url"):
                    local_paths.insert(0, inputs["image_path"])
                for local in local_paths:
                    urls.append(upload_fal_image(local, api_key, deadline))
                if inputs.get("image_url"):
                    urls.insert(0, inputs["image_url"])
                payload = {"prompt": inputs["prompt"], "aspect_ratio": inputs["aspect_ratio"],
                           "duration": int(inputs["duration"])}
                if operation == "image_to_video":
                    payload["image_url"] = urls[0]
                elif operation == "reference_to_video":
                    payload["image_urls"] = urls
                elif operation == "edit_video":
                    payload = {"prompt": inputs["prompt"], "video_url": inputs["video_url"]}
            if not job.record.get("staged"):
                data = fal_result(job, endpoint, payload, api_key, deadline, inputs.get("poll_interval", 5))
                job.stage([safe_get(requests.get, data["video"]["url"], deadline).content])
            output_path = Path(inputs.get("output_path", job.root / "gemini_omni_fal_output.mp4"))
            job.deliver([output_path])
        except Exception as exc:
            return job.failure(exc) if job else ToolResult(success=False, error=str(exc), cost_status="not_submitted")
        return ToolResult(
            success=True,
            data={
                "provider": "gemini_omni",
                "gateway": "fal.ai",
                "model": endpoint,
                "operation": operation,
                "output": str(output_path),
                **job.metadata(),
                **probe_output(output_path),
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.monotonic() - started, 2),
            model=endpoint,
            cost_status="estimated",
            provider_request_id=job.job_id,
        )

    def validate_paid_recovery(self, inputs: dict[str, Any]) -> None:
        inputs = self.normalize_inputs(inputs)
        suffix = {"text_to_video": "", "image_to_video": "/image-to-video",
                  "reference_to_video": "/reference-to-video", "edit_video": "/edit"}[inputs["operation"]]
        ProviderJob.validate_recovery(inputs, self.provider, f"google/gemini-omni-flash{suffix}", self.estimate_cost(inputs))
