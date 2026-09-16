"""Seedream  V5 image generation via fal.ai API.
deep-thinking prompt understanding, native text in 14 languages, and precise control over dense layouts and structured designs.
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
class SeedreamImage(BaseTool):
    name = "seedream_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "bytedance"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.ASYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API
    resume_support = ResumeSupport.FROM_CHECKPOINT

    dependencies = ["env:FAL_KEY"]
    install_instructions = (
        "Set FAL_KEY to your fal.ai API key.\n"
        "  Get one at https://fal.ai/dashboard/keys"
    )
    agent_skills = ["visual-style"]

    capabilities = [
        "generate_image",
        "text_to_image",
        "structured_designs",
        "dense_layouts",
        "multi_language_text",
    ]
    supports = {
        "text_rendering": True,
        "color_palette": True,
        "custom_size": True,
        "structured_designs": True,
        "dense_layouts": True,
        "multi_language_text": True,
    }
    best_for = [
        "raster brand and campaign assets",
        "images with accurate text rendering",
        "structured designs and dense layouts",
        "multi-language text rendering (14 languages)",
    ]
    input_schema = {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                **JOB_INPUT_PROPERTIES,
                "prompt": {"type": "string"},
                "image_size": {
                    "type": "string",
                    "enum": [
                        "square", "square_hd",
                        "landscape_4_3", "landscape_16_9",
                        "portrait_4_3", "portrait_16_9",
                        "auto_1K","auto_2K"
                    ],
                    "default": "auto_2K",
                },
                "num_images": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 4,
                    "default": 1,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["jpeg", "png"],
                    "description": "Output image format. Use 'jpeg' for smaller file size with lossy compression (suitable for web/preview), or 'png' for lossless quality with transparency support (suitable for design assets and further editing).",
                },
                "enable_safety_checker": {
                    "type": "boolean",
                    "default": True,
                    "description": "If set to true, the safety checker will be enabled.",
                 },
                 "output_path": {"type": "string"}
        },
    }
    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=0)
    idempotency_key_fields = [
        "prompt",
        "image_size",
        "output_format",
        "num_images",
        "enable_safety_checker",
    ]
    side_effects = ["writes image file to output_path", "calls fal.ai queue API"]
    user_visible_verification = ["Inspect generated image for brand accuracy and text readability"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        inputs = self.normalize_inputs(inputs)
        image_size = inputs.get("image_size", "auto_2K")
        num_images = inputs.get("num_images", 1)
        size_price_map = {
            "square": 0.0675,
            "square_hd": 0.135,
            "landscape_4_3": 0.0675,
            "landscape_16_9": 0.135,
            "portrait_4_3": 0.0675,
            "portrait_16_9": 0.135,
            "auto_1K": 0.0675,
            "auto_2K": 0.135,
        }
        unit_price = size_price_map.get(image_size, 0.135)
        return round(unit_price * num_images, 4)

    def normalize_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        reject_unsupported_media(inputs, self.input_schema["properties"])
        normalized = dict(inputs)
        if inputs.get("model") or inputs.get("model_name"):
            raise ValueError("SeedreamImage has a fixed v5 pro endpoint, not a model override")
        for alias in ("n", "number_of_images"):
            if alias in normalized:
                count = normalized.pop(alias)
                if "num_images" in normalized and normalized["num_images"] != count:
                    raise ValueError(f"Conflicting {alias} and num_images")
                normalized["num_images"] = count
        normalized.setdefault("num_images", 1)
        normalized.setdefault("image_size", "auto_2K")
        normalized.setdefault("output_format", "jpeg")
        normalized.setdefault("enable_safety_checker", True)
        count = normalized["num_images"]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 4:
            raise ValueError("num_images must be an integer from 1 to 4")
        if inputs.get("generation_mode") == "edit" or any(inputs.get(k) for k in (
            "image", "images", "image_url", "image_path", "image_urls", "image_paths",
            "image_list", "element_list", "image_reference",
        )):
            raise ValueError("SeedreamImage only implements text-to-image, not references/edits")
        return normalized

    @staticmethod
    def _output_paths(
        output_path: str | None, count: int, output_format: str
    ) -> list[Path]:
        path = Path(output_path or f"seedream_image.{output_format}")
        if not path.suffix:
            path = path.with_suffix(f".{output_format}")
        if count == 1:
            return [path]
        return [
            path.with_name(f"{path.stem}_{index}{path.suffix}")
            for index in range(1, count + 1)
        ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        import requests

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="FAL_KEY not set. " + self.install_instructions,
                cost_status="not_submitted",
            )

        start = time.monotonic()
        try:
            inputs = self.normalize_inputs(inputs)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc), cost_status="not_submitted")
        prompt = inputs["prompt"]
        num_images = inputs.get("num_images", 1)
        if isinstance(num_images, bool) or not isinstance(num_images, int):
            return ToolResult(
                success=False, error="num_images must be an integer from 1 to 4."
            )
        if not 1 <= num_images <= 4:
            return ToolResult(
                success=False, error="num_images must be between 1 and 4."
            )
        endpoint = "bytedance/seedream/v5/pro/text-to-image"
        payload: dict[str, Any] = {
            "prompt": prompt,
            "image_size": inputs.get("image_size", "auto_2K"),
            "output_format": inputs.get("output_format", "jpeg"),
            "num_images": num_images,
            "enable_safety_checker": inputs.get("enable_safety_checker", True),
        }

        job = None
        try:
            deadline = Deadline(inputs.get("timeout_seconds", 300))
            job = ProviderJob.open(inputs, self.provider, endpoint, self.estimate_cost(inputs))
            if not job.record.get("staged"):
                data = fal_result(job, endpoint, payload, api_key, deadline, inputs.get("poll_interval", 5))
                images = data.get("images") or []
                if not images or any(not image.get("url") for image in images):
                    raise ValueError("Seedream completed without a complete image set")
                job.stage([safe_get(requests.get, image["url"], deadline).content for image in images])
            request_id = job.job_id
            paths = self._output_paths(inputs.get("output_path") or str(job.root / "seedream_image.jpeg"),
                                       len(job.record["staged"]), inputs["output_format"])
            job.deliver(paths)
            output_paths = [str(path) for path in paths]
        except Exception as exc:
            return job.failure(exc) if job else ToolResult(success=False, error=str(exc), cost_status="not_submitted")

        return ToolResult(
            success=True,
            data={
                "provider": "seedream",
                "model": "seedream_v5",
                "prompt": prompt,
                "request_id": request_id,
                "image_count": len(output_paths),
                "outputs": output_paths,
                **job.metadata(),
            },
            artifacts=output_paths,
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.monotonic() - start, 2),
            model=endpoint,
            cost_status="estimated",
            provider_request_id=request_id,
        )

    def validate_paid_recovery(self, inputs: dict[str, Any]) -> None:
        inputs = self.normalize_inputs(inputs)
        ProviderJob.validate_recovery(inputs, self.provider, "bytedance/seedream/v5/pro/text-to-image",
                                      self.estimate_cost(inputs))
