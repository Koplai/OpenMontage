"""OpenAI GPT Image generation (gpt-image-2)."""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any
from lib.provider_jobs import Deadline, ProviderJob, sdk_available, reject_unsupported_media, JOB_INPUT_PROPERTIES

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


class OpenAIImage(BaseTool):
    name = "openai_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "openai"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API
    resume_support = ResumeSupport.FROM_CHECKPOINT

    dependencies = ["python:openai"]
    install_instructions = (
        "Set OPENAI_API_KEY to your OpenAI API key.\n"
        "  pip install openai"
    )
    agent_skills = ["flux-best-practices"]  # general image gen knowledge

    capabilities = ["generate_image", "generate_illustration", "text_to_image"]
    supports = {
        "complex_instructions": True,
        "text_in_image": True,
        "multiple_outputs": True,
    }
    best_for = [
        "complex multi-element compositions",
        "images with text/labels",
        "following detailed instructions accurately",
    ]
    not_good_for = ["offline generation", "budget-constrained projects at high quality"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            **JOB_INPUT_PROPERTIES,
            "prompt": {"type": "string"},
            "model": {
                "type": "string",
                "enum": ["gpt-image-2"],
                "default": "gpt-image-2",
            },
            "size": {
                "type": "string",
                "enum": ["1024x1024", "1536x1024", "1024x1536", "auto"],
                "default": "1024x1024",
            },
            "quality": {
                "type": "string",
                "enum": ["low", "medium", "high", "auto"],
                "default": "high",
            },
            "output_format": {
                "type": "string",
                "enum": ["png", "jpeg", "webp"],
                "default": "png",
            },
            "n": {"type": "integer", "default": 1, "minimum": 1, "maximum": 4},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=0)
    idempotency_key_fields = ["prompt", "size", "quality", "model"]
    side_effects = ["writes image file to output_path", "calls OpenAI API"]
    user_visible_verification = ["Inspect generated image for relevance and quality"]

    @staticmethod
    def _output_paths(output_path: str | None, count: int, extension: str) -> list[Path]:
        """Derive one output path per generated image.

        With a single image, honor the requested path as-is. With several,
        suffix each with `_1`, `_2`, … so no image overwrites another.
        """
        ext = extension if extension.startswith(".") else f".{extension}"
        if not output_path:
            return [Path(f"generated_image_{idx + 1}{ext}") for idx in range(count)]

        path = Path(output_path)
        suffix = path.suffix or ext
        if count == 1:
            return [path if path.suffix else path.with_suffix(suffix)]

        base = path.with_suffix("") if path.suffix else path
        return [base.parent / f"{base.name}_{idx + 1}{suffix}" for idx in range(count)]

    def get_status(self) -> ToolStatus:
        if os.environ.get("OPENAI_API_KEY") and sdk_available("openai", "OpenAI"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        inputs = self.normalize_inputs(inputs)
        # gpt-image-2 per-image pricing at 1024x1024 (non-square sizes run
        # slightly cheaper): https://developers.openai.com/api/docs/guides/image-generation
        quality = inputs.get("quality", "high")
        n = inputs.get("n", 1)
        cost_map = {"low": 0.006, "medium": 0.053, "high": 0.211, "auto": 0.053}
        return cost_map.get(quality, 0.053) * n

    def normalize_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        reject_unsupported_media(inputs, self.input_schema["properties"])
        normalized = dict(inputs)
        for alias in ("num_images", "number_of_images"):
            if alias in normalized:
                count = normalized.pop(alias)
                if "n" in normalized and normalized["n"] != count:
                    raise ValueError(f"Conflicting n and {alias}")
                normalized["n"] = count
        if (inputs.get("generation_mode") == "edit" or any(inputs.get(k) for k in
                ("image", "images", "image_url", "image_path", "image_urls", "image_paths",
                 "image_list", "element_list", "image_reference"))):
            raise ValueError("OpenAIImage does not implement image editing/reference inputs")
        for key, spec in self.input_schema["properties"].items():
            if "default" in spec:
                normalized.setdefault(key, spec["default"])
            if key in normalized and "enum" in spec and normalized[key] not in spec["enum"]:
                raise ValueError(f"Unsupported {key}")
        n = normalized["n"]
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 4:
            raise ValueError("n must be an integer from 1 to 4")
        return normalized

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(
                success=False,
                error="OpenAI key or SDK unavailable. " + self.install_instructions,
                cost_status="not_submitted",
            )

        from openai import OpenAI

        start = time.monotonic()
        job = None
        try:
            inputs = self.normalize_inputs(inputs)
            model, prompt = inputs["model"], inputs["prompt"]
            deadline = Deadline(inputs.get("timeout_seconds", 900))
            job = ProviderJob.open(inputs, self.provider, model, self.estimate_cost(inputs))
            job.require_resumable()
            if job.should_submit:
                client = OpenAI(max_retries=0, timeout=deadline.remaining(120))
                job.submitting()
                response = client.images.generate(**{
                    key: inputs[key] for key in ("model", "prompt", "size", "quality", "output_format", "n")
                })
                items = response.data or []
                if not items:
                    raise ValueError("OpenAI returned no image outputs")
                # Synchronous image responses cannot be fetched again by task ID.
                # Keep generated bytes durably before attempting final delivery.
                job.stage([base64.b64decode(item.b64_json, validate=True) for item in items])
                deadline.remaining()
            output_paths = self._output_paths(
                inputs.get("output_path") or str(job.root / f"generated_image.{inputs['output_format']}"),
                len(job.record["staged"]), inputs["output_format"])
            job.deliver(output_paths)
            outputs = [str(path) for path in output_paths]
        except Exception as exc:
            return job.failure(exc) if job else ToolResult(success=False, error=str(exc), cost_status="not_submitted")

        return ToolResult(
            success=True,
            data={
                "provider": "openai",
                "model": model,
                "prompt": prompt,
                "output": outputs[0],
                "outputs": outputs,
                "images_generated": len(outputs),
                **job.metadata(),
            },
            artifacts=outputs,
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.monotonic() - start, 2),
            model=model,
            cost_status="estimated",
        )

    def validate_paid_recovery(self, inputs: dict[str, Any]) -> None:
        inputs = self.normalize_inputs(inputs)
        ProviderJob.validate_recovery(inputs, self.provider, inputs["model"], self.estimate_cost(inputs))
