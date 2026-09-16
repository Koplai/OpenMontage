"""Seedance 2.0 and 2.5 (ByteDance) video generation via fal.ai API.

Best for cinematic clips with native audio, director-level camera control,
and lip-sync from quoted dialogue in prompts.
"""

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


class SeedanceVideo(BaseTool):
    name = "seedance_video"
    version = "0.3.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "seedance"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API
    resume_support = ResumeSupport.FROM_CHECKPOINT

    dependencies = []
    install_instructions = (
        "Set FAL_KEY to your fal.ai API key.\n"
        "  Get one at https://fal.ai/dashboard/keys"
    )
    agent_skills = ["seedance-2-0", "seedance-2-5", "ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video", "reference_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "reference_to_video": True,
        "multiple_reference_images": True,
        "reference_image": True,
        "native_audio": True,
        "cinematic_quality": True,
        "camera_direction": True,
        "lip_sync": True,
        "multi_shot": True,
        "aspect_ratio": True,
        "seed": True,
    }
    best_for = [
        "preferred premium video gen when FAL_KEY is available",
        "cinematic trailers, teasers, and high-fidelity clips with native synchronized audio",
        "director-level camera control and multi-shot editing in a single generation",
        "lip-sync from quoted dialogue in prompts",
        "Seedance 2.5 reference generation (up to 30 images + 10 video + 10 audio clips)",
        "consistent character identity across shots",
    ]
    not_good_for = ["offline generation", "budget-constrained projects"]
    fallback_tools = ["veo_video", "kling_video", "minimax_video"]
    # Premium model — beat out "experimental stability" baseline. The scoring
    # engine reads quality_score directly when present (see lib/scoring.py).
    quality_score = 0.95

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            **JOB_INPUT_PROPERTIES,
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video", "reference_to_video"],
                "default": "text_to_video",
            },
            "model_variant": {
                "type": "string",
                "enum": ["standard", "fast"],
                "default": "standard",
                "description": "standard = highest quality, fast = lower latency and cost",
            },
            "model_version": {
                "type": "string",
                "enum": ["2.0", "2.5"],
                "default": "2.0",
                "description": "Seedance 2.5 is the current high-quality model; 2.0 retains fast-tier access.",
            },
            "duration": {
                "type": "string",
                "enum": [
                    "auto",
                    "4",
                    "5",
                    "6",
                    "7",
                    "8",
                    "9",
                    "10",
                    "11",
                    "12",
                    "13",
                    "14",
                    "15",
                    "16",
                    "17",
                    "18",
                    "19",
                    "20",
                    "21",
                    "22",
                    "23",
                    "24",
                    "25",
                    "26",
                    "27",
                    "28",
                    "29",
                    "30",
                ],
                "default": "5",
                "description": "Duration in seconds. 'auto' lets the model decide.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
                "default": "16:9",
            },
            "resolution": {
                "type": "string",
                "enum": ["480p", "720p"],
                "default": "720p",
            },
            "generate_audio": {
                "type": "boolean",
                "default": True,
                "description": "Generate synchronized audio (speech, SFX, ambient)",
            },
            "image_url": {
                "type": "string",
                "description": "Start frame image URL for image_to_video (jpg, png, webp)",
            },
            "image_path": {
                "type": "string",
                "description": "Local start-frame path for image_to_video. Auto-uploaded to fal.ai storage.",
            },
            "end_image_url": {
                "type": "string",
                "description": "Optional end frame URL for image_to_video",
            },
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Up to 9 reference image URLs for reference_to_video (identity / wardrobe / setting / style anchors).",
            },
            "reference_image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Local reference image paths for reference_to_video. Auto-uploaded to fal.ai storage.",
            },
            "reference_video_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Up to 3 reference video clip URLs for reference_to_video (motion / camera / pacing anchors).",
            },
            "reference_audio_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Up to 3 reference audio clip URLs for reference_to_video (voice / music / ambience anchors).",
            },
            "seed": {
                "type": "integer",
                "description": "Optional seed for reproducibility",
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=0)
    idempotency_key_fields = [
        "prompt",
        "model_version",
        "model_variant",
        "operation",
        "duration",
        "seed",
    ]
    side_effects = ["writes video file to output_path", "calls fal.ai API"]
    user_visible_verification = [
        "Watch generated clip for motion coherence, audio sync, and visual quality"
    ]

    def _get_api_key(self) -> str | None:
        return os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        if inputs.get("model_version", "2.0") == "2.5":
            return round(
                0.30
                * (
                    30
                    if inputs.get("duration", "5") == "auto"
                    else int(inputs.get("duration", "5"))
                ),
                2,
            )
        variant = inputs.get("model_variant", "standard")
        duration = inputs.get("duration", "5")
        secs = 15 if duration == "auto" else int(duration)
        rate = 0.2419 if variant == "fast" else 0.3034
        return round(rate * secs, 2)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        if inputs.get("model_version", "2.0") == "2.5":
            return 150.0
        variant = inputs.get("model_variant", "standard")
        return 60.0 if variant == "fast" else 120.0

    def normalize_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        reject_unsupported_media(inputs, {*self.input_schema["properties"],
                                          "reference_image_path", "reference_image_url"})
        normalized = dict(inputs)
        for source, target in (("reference_image_path", "image_path"), ("reference_image_url", "image_url")):
            if inputs.get(source):
                if inputs.get(target) and inputs[target] != inputs[source]:
                    raise ValueError(f"Conflicting {source} and {target}")
                normalized[target] = normalized.pop(source)
        refs = any(normalized.get(k) for k in (
            "reference_image_urls", "reference_image_paths", "reference_video_urls", "reference_audio_urls"))
        single = normalized.get("image_url") or normalized.get("image_path")
        normalized.setdefault("operation", "reference_to_video" if refs else (
            "image_to_video" if single else "text_to_video"))
        for key in ("model_version", "model_variant", "duration", "resolution", "aspect_ratio", "generate_audio"):
            normalized.setdefault(key, self.input_schema["properties"][key]["default"])
        normalized["duration"] = str(normalized["duration"])
        for key in ("operation", "model_version", "model_variant", "duration", "resolution", "aspect_ratio"):
            if normalized[key] not in self.input_schema["properties"][key]["enum"]:
                raise ValueError(f"Unsupported Seedance {key}")
        if normalized["model_version"] == "2.5" and normalized["model_variant"] == "fast":
            raise ValueError("Seedance 2.5 has no fast endpoint")
        if inputs.get("model") or inputs.get("model_name"):
            raise ValueError("Seedance selects models through model_version/model_variant, not model/model_name")
        operation = normalized["operation"]
        if operation == "text_to_video" and (refs or single or normalized.get("end_image_url")):
            raise ValueError("text_to_video cannot ignore supplied reference inputs")
        if operation == "image_to_video" and (not single or refs):
            raise ValueError("image_to_video requires a start image, not reference arrays")
        if operation == "reference_to_video" and (not refs or single or normalized.get("end_image_url")):
            raise ValueError("reference_to_video requires reference arrays, not start/end images")
        if normalized.get("video_url") or normalized.get("video_path"):
            raise ValueError("Seedance does not implement video editing")
        for key, limit in (("reference_image", 30), ("reference_video", 10), ("reference_audio", 10)):
            maximum = limit if normalized["model_version"] == "2.5" else (9 if key == "reference_image" else 3)
            count = len(normalized.get(key + "_urls") or []) + len(normalized.get(key + "_paths") or [])
            if count > maximum:
                raise ValueError(f"Seedance {key} limit is {maximum}")
        if normalized["model_version"] == "2.5" and operation == "image_to_video":
            normalized["aspect_ratio"] = "auto"
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
        operation = inputs["operation"]
        model_version = inputs["model_version"]
        variant = inputs["model_variant"]
        operation_path = operation.replace("_", "-")

        if model_version == "2.5":
            if variant == "fast":
                return ToolResult(
                    success=False,
                    error="Seedance 2.5 on fal.ai has no fast endpoint; use model_variant='standard'.",
                )
            model_path = f"bytedance/seedance-2.5/{operation_path}"
        elif variant == "fast":
            model_path = f"bytedance/seedance-2.0/fast/{operation_path}"
        else:
            model_path = f"bytedance/seedance-2.0/{operation_path}"

        job = None
        try:
            deadline = Deadline(inputs.get("timeout_seconds", 900))
            job = ProviderJob.open(inputs, self.provider, model_path, self.estimate_cost(inputs))
            job.require_resumable()
            payload = {}
            if job.should_submit:
                payload = {key: inputs[key] for key in
                           ("prompt", "duration", "aspect_ratio", "resolution", "generate_audio")}
                if inputs.get("seed") is not None:
                    payload["seed"] = inputs["seed"]
                if operation == "image_to_video":
                    payload["image_url"] = inputs.get("image_url") or upload_fal_image(
                        inputs["image_path"], api_key, deadline)
                    if inputs.get("end_image_url"):
                        payload["end_image_url"] = inputs["end_image_url"]
                if operation == "reference_to_video":
                    images = list(inputs.get("reference_image_urls") or [])
                    images.extend(upload_fal_image(path, api_key, deadline)
                                  for path in inputs.get("reference_image_paths") or [])
                    for kind, values in (
                        ("image", images), ("video", inputs.get("reference_video_urls")),
                        ("audio", inputs.get("reference_audio_urls")),
                    ):
                        if values:
                            key = f"{kind}_urls" if model_version == "2.5" else f"reference_{kind}_urls"
                            payload[key] = values
            if not job.record.get("staged"):
                data = fal_result(job, model_path, payload, api_key, deadline, inputs.get("poll_interval", 5))
                job.stage([safe_get(requests.get, data["video"]["url"], deadline).content])
                if isinstance(data.get("seed"), int):
                    job.update(seed=data["seed"])
            output_path = Path(inputs.get("output_path", job.root / "seedance_output.mp4"))
            job.deliver([output_path])
        except Exception as exc:
            return job.failure(exc) if job else ToolResult(success=False, error=str(exc), cost_status="not_submitted")

        from tools.video._shared import probe_output

        probed = probe_output(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": "seedance",
                "model": model_path,
                "prompt": inputs["prompt"],
                "operation": operation,
                "variant": variant,
                "model_version": model_version,
                "aspect_ratio": inputs.get("aspect_ratio", "16:9"),
                "resolution": inputs.get("resolution", "720p"),
                "generate_audio": inputs.get("generate_audio", True),
                "seed": job.record.get("seed"),
                "output": str(output_path),
                "output_path": str(output_path),
                "format": "mp4",
                **job.metadata(),
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.monotonic() - start, 2),
            model=model_path,
            cost_status="estimated",
            provider_request_id=job.job_id,
        )

    def validate_paid_recovery(self, inputs: dict[str, Any]) -> None:
        inputs = self.normalize_inputs(inputs)
        fast = "fast/" if inputs["model_variant"] == "fast" else ""
        endpoint = f"bytedance/seedance-{inputs['model_version']}/{fast}{inputs['operation'].replace('_', '-')}"
        ProviderJob.validate_recovery(inputs, self.provider, endpoint, self.estimate_cost(inputs))
