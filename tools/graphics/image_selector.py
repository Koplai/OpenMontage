"""Capability-level image selector that routes between generation and stock providers.

Provider discovery is automatic — any BaseTool with capability="image_generation"
is picked up from the registry.  Adding a new image provider requires only creating
the tool file in tools/graphics/; no changes to this selector are needed.
"""

from __future__ import annotations

from typing import Any

from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStability, ToolStatus, ToolTier


class ImageSelector(BaseTool):
    name = "image_selector"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "selector"
    stability = ToolStability.BETA
    runtime = ToolRuntime.HYBRID
    delegates_paid_execution = True
    agent_skills = ["flux-best-practices", "bfl-api", "atlas-cloud"]

    capabilities = [
        "generate_image", "search_image", "download_image",
        "provider_selection", "text_to_image", "stock_image",
    ]
    supports = {
        "user_preference_routing": True,
        "offline_fallback": True,
        "stock_fallback": True,
    }
    best_for = [
        "preflight routing — pick the best image provider for the task",
        "switching between generated and stock images",
        "recommend alternatives when a preferred provider is unavailable",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Image description (used as prompt for generation or query for stock)",
            },
            "negative_prompt": {
                "type": "string",
                "description": "What to avoid in the generated image. Passed to providers that support it.",
            },
            "width": {"type": "integer", "description": "Image width in pixels"},
            "height": {"type": "integer", "description": "Image height in pixels"},
            "seed": {"type": "integer", "description": "Random seed for reproducibility (generation providers only)"},
            "n": {"type": "integer", "description": "Number of image variations to request when supported."},
            "aspect_ratio": {
                "type": "string",
                "description": "Aspect ratio hint for providers that support ratio-based generation.",
            },
            "resolution": {
                "type": "string",
                "description": "Resolution tier for providers that support named resolutions.",
            },
            "api_family": {
                "type": "string",
                "description": "Provider-specific API family hint passed through when supported.",
            },
            "model_name": {
                "type": "string",
                "description": "Provider-specific model name passed through when supported.",
            },
            "model": {
                "type": "string",
                "description": "Exact provider model id, e.g. an Atlas Cloud live model route.",
            },
            "generation_mode": {
                "type": "string",
                "enum": ["generate", "edit"],
                "default": "generate",
                "description": "Use 'edit' when providing one or more source images.",
            },
            "image_url": {"type": "string", "description": "Single source image URL for edit-capable providers."},
            "image_path": {"type": "string", "description": "Single local source image path for edit-capable providers."},
            "image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple source image URLs for compositing edits.",
            },
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple local source image paths for compositing edits.",
            },
            "image_list": {
                "type": "array",
                "description": "Provider-specific image reference list, e.g. Kling Official Image Omni.",
            },
            "element_list": {
                "type": "array",
                "description": "Provider-specific element references, e.g. Kling Official element_id objects.",
            },
            "image_reference": {
                "type": "string",
                "description": "Provider-specific reference type, e.g. subject or face.",
            },
            "image_fidelity": {
                "type": "number",
                "description": "Provider-specific reference image fidelity hint.",
            },
            "human_fidelity": {
                "type": "number",
                "description": "Provider-specific human or face fidelity hint.",
            },
            "result_type": {
                "type": "string",
                "description": "Provider-specific result type, e.g. single or series.",
            },
            "series_amount": {
                "type": "string",
                "description": "Provider-specific series amount for image series generation.",
            },
            "watermark": {
                "type": "boolean",
                "description": "Provider-specific watermark toggle passed through when supported.",
            },
            "callback_url": {
                "type": "string",
                "description": "Provider-specific callback URL. Current OpenMontage providers still poll by default.",
            },
            "external_task_id": {
                "type": "string",
                "description": "Provider-specific idempotency/provenance task id.",
            },
            "preferred_provider": {
                "type": "string",
                "description": "Provider name or 'auto'. Valid values are discovered at runtime from the registry.",
                "default": "auto",
            },
            "allowed_providers": {
                "type": "array",
                "items": {"type": "string"},
            },
            "operation": {
                "type": "string",
                "enum": ["generate", "rank"],
                "default": "generate",
                "description": "Operation mode. 'rank' returns scored provider rankings without generating.",
            },
            "workflow_json": {
                "type": "string",
                "description": (
                    "Optional full ComfyUI workflow JSON. Routes to a custom-workflow-capable "
                    "provider (e.g. comfyui_image) based on server availability, not bundled "
                    "model readiness. Requires output_node."
                ),
            },
            "workflow_path": {
                "type": "string",
                "description": (
                    "Optional path to a ComfyUI workflow JSON file. Routes to a custom-workflow-"
                    "capable provider based on server availability. Requires output_node."
                ),
            },
            "output_node": {
                "type": "string",
                "description": "ComfyUI output node ID for a custom workflow_json/workflow_path.",
            },
            "workflow_name": {
                "type": "string",
                "description": "Optional human-readable provenance label for a custom workflow.",
            },
            "workflow_model": {
                "type": "string",
                "description": "Optional model/provenance label for a custom workflow.",
            },
            "workflow_model_stack": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Optional provenance metadata for custom workflow dependencies.",
            },
            "output_path": {"type": "string"},
        },
    }

    def _providers(self) -> list[BaseTool]:
        """Auto-discover image generation providers from the registry."""
        from tools.tool_registry import registry
        registry.ensure_discovered()
        return [t for t in registry.get_by_capability("image_generation")
                if t.name != self.name]

    @property
    def fallback_tools(self) -> list[str]:
        """Dynamically built from discovered providers."""
        return [t.name for t in self._providers()]

    @property
    def provider_matrix(self) -> dict[str, dict[str, str]]:
        """Built at runtime from each provider's best_for field."""
        matrix = {}
        for tool in self._providers():
            strength = ", ".join(tool.best_for) if tool.best_for else tool.name
            matrix[tool.provider] = {"tool": tool.name, "strength": strength}
        return matrix

    def get_status(self) -> ToolStatus:
        if any(tool.get_status() == ToolStatus.AVAILABLE for tool in self._providers()):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        if inputs.get("operation") == "rank":
            return 0.0
        tool, adapted = self.resolve_execution(inputs)
        return tool.estimate_cost(adapted)

    def resolve_execution(self, inputs: dict[str, Any]) -> tuple[BaseTool, dict[str, Any]]:
        """Pure resolution for estimation, exact-request approval and execution."""
        tool, _ = self._select_best_tool(inputs, self._providers(), self._prepare_task_context(inputs))
        if tool is None:
            raise ValueError("Requested image provider/model or reference operation is unavailable; no substitution permitted")
        return tool, self._adapt_inputs(tool, inputs)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        from lib.scoring import rank_providers

        task_context = self._prepare_task_context(inputs)
        candidates = self._filter_candidates(inputs, self._providers())

        # Rank mode — return scored provider rankings without generating
        if inputs.get("operation") == "rank":
            rankings = rank_providers(candidates, task_context)
            return ToolResult(
                success=True,
                data={
                    "rankings": self._serialize_rankings(candidates, rankings),
                    "explanation": "\n".join(r.explain() for r in rankings[:5]),
                    "normalized_task_context": task_context,
                },
            )

        # Normal generation — use scored selection
        try:
            tool, adapted = self.resolve_execution(inputs)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        result = tool.execute(adapted)
        if result.success:
            result.data.setdefault("selected_tool", tool.name)
            result.data["selected_provider"] = tool.provider
            result.data["selection_reason"] = f"Resolved {tool.provider} ({tool.name}); rankings are recommendations only"
            result.data.update(self._tool_context_payload(tool))
        return result

    @staticmethod
    def _adapt_inputs(tool: BaseTool, inputs: dict[str, Any]) -> dict[str, Any]:
        from lib.provider_jobs import reject_unsupported_media

        adapted = dict(inputs)
        props = tool.input_schema.get("properties", {})
        if "query" in props and "query" not in adapted:
            adapted["query"] = adapted.get("prompt", "")
        reference_keys = ("image_url", "image_path", "image_urls", "image_paths")
        if "images" in props and "images" not in adapted:
            refs = list(adapted.get("image_paths") or []) + list(adapted.get("image_urls") or [])
            refs += [adapted[key] for key in ("image_path", "image_url") if adapted.get(key)]
            if refs:
                adapted["images"] = refs
                for key in reference_keys:
                    adapted.pop(key, None)
        for source, targets in (
            ("model_name", ("model",)), ("model", ("model_name",)),
            ("n", ("num_images", "number_of_images")),
            ("num_images", ("n", "number_of_images")),
            ("number_of_images", ("n", "num_images")),
        ):
            if source in adapted and source not in props:
                target = next((key for key in targets if key in props), None)
                if target:
                    value = adapted.pop(source)
                    if target in adapted and adapted[target] != value:
                        raise ValueError(f"Conflicting {source} and {target}")
                    adapted[target] = value
                else:
                    raise ValueError(f"{tool.name} does not support {source}")
        for key in (*reference_keys, "images", "image", "image_list", "element_list", "image_reference"):
            if adapted.get(key) and key not in props:
                raise ValueError(f"{tool.name} cannot consume {key}; references cannot be stripped")
        if adapted.get("generation_mode") == "edit" and "generation_mode" not in props:
            if not any(adapted.get(key) for key in (*reference_keys, "images", "image", "image_list")):
                raise ValueError(f"{tool.name} cannot perform the requested edit")
        for key in ("preferred_provider", "allowed_providers", "task_context", "operation"):
            adapted.pop(key, None)
        reject_unsupported_media(adapted, props)
        for passthrough_key in (
                "negative_prompt",
                "width",
                "height",
                "seed",
                "n",
                "aspect_ratio",
                "resolution",
                "generation_mode",
                "image_url",
                "image_path",
                "image_urls",
                "image_paths",
                "image_list",
                "element_list",
                "api_family",
                "model_name",
                "model",
                "image_reference",
                "image_fidelity",
                "human_fidelity",
                "result_type",
                "series_amount",
                "watermark",
                "callback_url",
                "external_task_id",
                "workflow_json",
                "workflow_path",
                "output_node",
                "workflow_name",
                "workflow_model",
                "workflow_model_stack",
        ):
            if passthrough_key in adapted and passthrough_key not in props:
                adapted.pop(passthrough_key)
        for key, spec in props.items():
            if "default" in spec:
                adapted.setdefault(key, spec["default"])
        normalizer = getattr(tool, "normalize_inputs", None)
        return normalizer(adapted) if callable(normalizer) else adapted

    def _select_best_tool(
        self,
        inputs: dict[str, Any],
        candidates: list[BaseTool],
        task_context: dict[str, Any],
    ) -> tuple[BaseTool | None, object]:
        """Select the best provider using scored ranking."""
        from lib.scoring import rank_providers

        preferred = inputs.get("preferred_provider", "auto")
        allowed = set(inputs.get("allowed_providers") or [])
        if allowed:
            candidates = [tool for tool in candidates if tool.provider in allowed or tool.name in allowed]
        if preferred != "auto":
            candidates = [tool for tool in candidates if preferred in {tool.provider, tool.name}]
        candidates = self._filter_candidates(inputs, candidates)

        rankings = rank_providers(candidates, task_context)

        selectable = {tool.name: tool for tool in candidates if self._tool_selectable(tool, inputs)}
        for score_item in rankings:
            if score_item.tool_name in selectable:
                return selectable[score_item.tool_name], score_item

        return None, None

    def _prepare_task_context(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from lib.scoring import normalize_task_context

        return normalize_task_context(
            inputs.get("task_context", {}),
            prompt=inputs.get("prompt", ""),
            capability=self.capability,
            operation=inputs.get("generation_mode", inputs.get("operation", "generate")),
        )

    @staticmethod
    def _tool_context_payload(tool: BaseTool) -> dict[str, Any]:
        info = tool.get_info()
        return {
            "selected_tool_agent_skills": info.get("agent_skills", []),
            "required_agent_skills": info.get("agent_skills", []),
            "selected_tool_usage_location": info.get("usage_location"),
            "selected_tool_best_for": info.get("best_for", []),
        }

    def _serialize_rankings(self, candidates: list[BaseTool], rankings: list[object]) -> list[dict[str, Any]]:
        tool_by_name = {tool.name: tool for tool in candidates}
        serialized: list[dict[str, Any]] = []
        for score in rankings:
            item = score.to_dict()
            tool = tool_by_name.get(score.tool_name)
            if tool:
                info = tool.get_info()
                item["agent_skills"] = info.get("agent_skills", [])
                item["usage_location"] = info.get("usage_location")
                item["best_for"] = info.get("best_for", [])
                item["supports"] = info.get("supports", {})
                item["status"] = str(tool.get_status())
            serialized.append(item)
        return serialized

    def _filter_candidates(self, inputs: dict[str, Any], candidates: list[BaseTool]) -> list[BaseTool]:
        exact_model = inputs.get("model") or inputs.get("model_name")
        if exact_model:
            model_matches = [
                tool for tool in candidates
                if any(exact_model in getattr(tool, "input_schema", {}).get("properties", {}).get(key, {}).get("enum", [])
                       for key in ("model", "model_name"))
                or exact_model in tool.get_info().get("model_catalog", {})
                or (inputs.get("preferred_provider") not in (None, "auto")
                    and inputs.get("preferred_provider") in {tool.name, tool.provider}
                    and any(key in tool.input_schema.get("properties", {})
                            and "enum" not in tool.input_schema["properties"][key]
                            for key in ("model", "model_name")))
            ]
            candidates = model_matches

        # A caller-supplied custom workflow is provider-specific (ComfyUI graph
        # JSON). Route it only to custom-workflow-capable providers whose server
        # is reachable — bundled-model readiness is irrelevant in that case.
        if self._has_custom_workflow(inputs):
            return [t for t in candidates if self._custom_workflow_eligible(t, inputs)]

        wants_edit = (
            inputs.get("generation_mode") == "edit"
            or inputs.get("image_url")
            or inputs.get("image_path")
            or inputs.get("image_urls")
            or inputs.get("image_paths")
            or inputs.get("image_list")
            or inputs.get("element_list")
            or inputs.get("images")
            or inputs.get("image_reference")
        )
        if not wants_edit:
            return candidates

        filtered: list[BaseTool] = []
        for tool in candidates:
            props = getattr(tool, "input_schema", {}).get("properties", {})
            supports = getattr(tool, "supports", {})
            if supports.get("image_edit") or any(
                key in props for key in ("image", "images", "image_url", "image_path", "image_urls", "image_paths", "image_list", "element_list")
            ):
                filtered.append(tool)
        return filtered

    @staticmethod
    def _has_custom_workflow(inputs: dict[str, Any]) -> bool:
        return bool(inputs.get("workflow_json") or inputs.get("workflow_path"))

    def _custom_workflow_eligible(self, tool: BaseTool, inputs: dict[str, Any]) -> bool:
        """Whether a tool can run the caller-supplied custom workflow.

        Eligibility is based on server availability, not bundled-model readiness:
        a provider qualifies when it advertises ``custom_workflow`` support, an
        ``output_node`` is supplied, and its backend is reachable (status is not
        UNAVAILABLE).
        """
        if not self._has_custom_workflow(inputs):
            return False
        if not inputs.get("output_node"):
            return False
        supports = getattr(tool, "supports", {})
        if not supports.get("custom_workflow"):
            return False
        return tool.get_status() != ToolStatus.UNAVAILABLE

    def _tool_selectable(self, tool: BaseTool, inputs: dict[str, Any]) -> bool:
        """A provider is selectable if it is AVAILABLE, or if it can serve a
        caller-supplied custom workflow even while bundled models report DEGRADED."""
        if tool.get_status() == ToolStatus.AVAILABLE:
            return True
        return self._custom_workflow_eligible(tool, inputs)
