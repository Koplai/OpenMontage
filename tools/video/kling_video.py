"""Kling video generation via fal.ai API.

Best for cinematic B-roll with high visual fidelity and fluid motion.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from lib.provider_jobs import Deadline, ProviderJob, fal_result, safe_get, reject_unsupported_media, JOB_INPUT_PROPERTIES

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


class KlingVideo(BaseTool):
    name = "kling_video"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "kling"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API
    resume_support = ResumeSupport.FROM_CHECKPOINT

    dependencies = []
    install_instructions = (
        "Set FAL_KEY to your fal.ai API key.\n"
        "  Get one at https://fal.ai/dashboard/keys"
    )
    agent_skills = ["ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "native_audio": True,
        "cinematic_quality": True,
    }
    best_for = [
        "cinematic B-roll with highest visual fidelity",
        "fluid motion and camera direction",
        "professional video clips",
    ]
    not_good_for = ["budget-constrained projects", "offline generation", "quick iteration"]
    fallback_tools = ["minimax_video", "veo_video", "wan_video"]

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
            "model_variant": {
                "type": "string",
                "enum": ["v3/standard", "v2.1/master", "v2.1/pro", "v2.1/standard"],
                "default": "v3/standard",
            },
            "duration": {
                "type": "string",
                "enum": ["5", "10"],
                "default": "5",
                "description": "Duration in seconds",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1"],
                "default": "16:9",
            },
            "image_url": {"type": "string", "description": "Reference image URL for image_to_video"},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=0)
    idempotency_key_fields = ["prompt", "model_variant", "operation", "duration"]
    side_effects = ["writes video file to output_path", "calls fal.ai API"]
    user_visible_verification = ["Watch generated clip for motion coherence and visual quality"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        variant = inputs.get("model_variant", "v3/standard")
        duration = int(inputs.get("duration", "5"))
        if "master" in variant:
            return 0.30 * (duration / 5)
        if "pro" in variant:
            return 0.20 * (duration / 5)
        return 0.10 * (duration / 5)  # standard

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 60.0  # ~1 minute typical

    def normalize_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        reject_unsupported_media(inputs, {*self.input_schema["properties"], "reference_image_url"})
        normalized = dict(inputs)
        if inputs.get("reference_image_url") and not inputs.get("image_url"):
            normalized["image_url"] = inputs["reference_image_url"]
        normalized.pop("reference_image_url", None)
        normalized.setdefault("operation", "image_to_video" if normalized.get("image_url") else "text_to_video")
        for key in ("model_variant", "duration", "aspect_ratio"):
            normalized.setdefault(key, self.input_schema["properties"][key]["default"])
        normalized["duration"] = str(normalized["duration"])
        if inputs.get("model") or inputs.get("model_name"):
            raise ValueError("Kling fal selects models through model_variant, not model/model_name")
        for key in ("operation", "model_variant", "duration", "aspect_ratio"):
            if normalized[key] not in self.input_schema["properties"][key]["enum"]:
                raise ValueError(f"Unsupported Kling {key}")
        if normalized["operation"] == "image_to_video" and not normalized.get("image_url"):
            raise ValueError("Kling image_to_video requires image_url")
        if normalized["operation"] == "text_to_video" and normalized.get("image_url"):
            raise ValueError("text_to_video cannot ignore a supplied image")
        if any(inputs.get(k) for k in (
            "image_path", "reference_image_path", "reference_image_urls", "reference_image_paths",
            "video_url", "video_path", "reference_video_urls", "reference_audio_urls",
        )):
            raise ValueError("Kling fal supports one image_url, not local/reference/edit inputs")
        return normalized

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="FAL_KEY not set. " + self.install_instructions,
                cost_status="not_submitted",
            )

        import requests

        start = time.monotonic()
        try:
            inputs = self.normalize_inputs(inputs)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc), cost_status="not_submitted")
        operation = inputs.get("operation", "text_to_video")
        variant = inputs.get("model_variant", "v3/standard")
        # fal.ai uses hyphens in endpoint paths (text-to-video, not text_to_video)
        operation_path = operation.replace("_", "-")
        model_path = f"kling-video/{variant}/{operation_path}"

        payload: dict[str, Any] = {"prompt": inputs["prompt"]}
        if inputs.get("duration"):
            payload["duration"] = inputs["duration"]
        if inputs.get("aspect_ratio"):
            payload["aspect_ratio"] = inputs["aspect_ratio"]
        if operation == "image_to_video" and inputs.get("image_url"):
            payload["image_url"] = inputs["image_url"]

        job = None
        try:
            deadline = Deadline(inputs.get("timeout_seconds", 900))
            endpoint = f"fal-ai/{model_path}"
            job = ProviderJob.open(inputs, self.provider, endpoint, self.estimate_cost(inputs))
            if not job.record.get("staged"):
                data = fal_result(job, endpoint, payload, api_key, deadline, inputs.get("poll_interval", 5))
                job.stage([safe_get(requests.get, data["video"]["url"], deadline).content])
            output_path = Path(inputs.get("output_path", job.root / "kling_output.mp4"))
            job.deliver([output_path])
        except Exception as exc:
            return job.failure(exc) if job else ToolResult(success=False, error=str(exc), cost_status="not_submitted")

        from tools.video._shared import probe_output

        probed = probe_output(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": "kling",
                "model": f"fal-ai/{model_path}",
                "prompt": inputs["prompt"],
                "operation": operation,
                "aspect_ratio": inputs.get("aspect_ratio", "16:9"),
                "output": str(output_path),
                "output_path": str(output_path),
                "format": "mp4",
                **job.metadata(),
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.monotonic() - start, 2),
            model=f"fal-ai/{model_path}",
            cost_status="estimated",
            provider_request_id=job.job_id,
        )

    def validate_paid_recovery(self, inputs: dict[str, Any]) -> None:
        inputs = self.normalize_inputs(inputs)
        endpoint = f"fal-ai/kling-video/{inputs['model_variant']}/{inputs['operation'].replace('_', '-')}"
        ProviderJob.validate_recovery(inputs, self.provider, endpoint, self.estimate_cost(inputs))
