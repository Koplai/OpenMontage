"""Capability-level video selector that routes between generation and stock providers.

Provider discovery is automatic — any BaseTool with capability="video_generation"
is picked up from the registry.  Adding a new video provider requires only creating
the tool file in tools/video/; no changes to this selector are needed.
"""

from __future__ import annotations

import os

from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStability, ToolStatus, ToolTier


class VideoSelector(BaseTool):
    name = "video_selector"
    version = "0.3.1"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "selector"
    stability = ToolStability.BETA
    runtime = ToolRuntime.HYBRID
    delegates_paid_execution = True
    agent_skills = ["ai-video-gen", "create-video", "ltx2", "gemini-omni", "atlas-cloud"]

    # Operations that REQUIRE motion: an image-only tool (image_selector) is not
    # an acceptable last-resort fallback for these, so fallback_tools_for() drops it.
    MOTION_REQUIRED_OPERATIONS = frozenset({"image_to_video", "reference_to_video", "video_edit", "edit_video"})
    # Deprecated recommendation input; never permits an execution substitution.
    PREFERRED_PROVIDER_GAP = 0.15

    capabilities = [
        "text_to_video", "image_to_video", "reference_to_video", "video_edit", "edit_video", "stock_video",
        "provider_selection", "search_video", "download_video",
    ]
    supports = {
        "user_preference_routing": True,
        "offline_fallback": True,
        "reference_image": True,
        "stock_fallback": True,
    }
    best_for = [
        "preflight routing",
        "user-facing recommendation flows",
        "switching between cloud, local, and stock video tools",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "preferred_provider": {
                "type": "string",
                "description": "Provider name or 'auto'. Valid values are discovered at runtime from the registry.",
                "default": "auto",
            },
            "preferred_provider_gap": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "default": 0.15,
                "description": (
                    "Deprecated recommendation hint, ignored during execution. "
                    "An explicit provider choice is always a hard constraint."
                ),
            },
            "allowed_providers": {"type": "array", "items": {"type": "string"}},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video", "reference_to_video", "video_edit", "edit_video", "rank"],
                "default": "text_to_video",
            },
            "target_operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video", "reference_to_video", "video_edit", "edit_video"],
                "description": "Operation to score when operation='rank'.",
                "default": "text_to_video",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1"],
                "default": "16:9",
                "description": "Video aspect ratio. Passed through to the selected provider.",
            },
            "duration": {
                "type": "string",
                "description": "Duration hint (e.g., '5', '10'). Passed through to the selected provider.",
            },
            "reference_image_path": {
                "type": "string",
                "description": "Local reference image. Only routed to providers that implement local-path inputs.",
            },
            "reference_image_url": {
                "type": "string",
                "description": "URL of a reference image for image_to_video.",
            },
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Reference image URLs for providers that support reference-conditioned video.",
            },
            "reference_image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Local reference image paths for providers that support reference-conditioned video.",
            },
            "reference_video_url": {
                "type": "string",
                "description": "Reference video URL for providers that support video-conditioned generation.",
            },
            "reference_video_path": {
                "type": "string",
                "description": "Local reference video path. Providers that require URLs should reject this clearly.",
            },
            "reference_video_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Reference video URLs for mixed-media generation.",
            },
            "reference_video_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Local reference video paths for mixed-media generation.",
            },
            "reference_audio_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Reference audio URLs for mixed-media generation.",
            },
            "reference_audio_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Local reference audio paths for mixed-media generation.",
            },
            "last_image_url": {"type": "string", "description": "Optional final frame for first/last-frame generation."},
            "last_image_path": {"type": "string", "description": "Optional local final frame."},
            "video_url": {"type": "string", "description": "Source video URL for video editing."},
            "video_path": {"type": "string", "description": "Local source video for video editing."},
            "video_clips": {"type": "array", "items": {"type": "object"}},
            "refers": {"type": "array", "items": {"type": "object"}},
            "image_list": {
                "type": "array",
                "description": "Provider-specific list of image references, e.g. Kling Official Video Omni.",
            },
            "video_list": {
                "type": "array",
                "description": "Provider-specific list of video references, e.g. Kling Official Video Omni.",
            },
            "element_list": {
                "type": "array",
                "description": "Provider-specific element references, e.g. Kling Official element_id objects.",
            },
            "multi_shot": {
                "type": "boolean",
                "description": "Provider-specific multi-shot mode.",
            },
            "shot_type": {
                "type": "string",
                "description": "Provider-specific multi-shot type.",
            },
            "multi_prompt": {
                "type": "array",
                "description": "Structured multi-shot prompts; not inferred from prose.",
            },
            "image_url": {
                "type": "string",
                "description": "Alias for reference_image_url (used by some providers like Kling via fal.ai).",
            },
            "resolution": {
                "type": "string",
                "description": "Resolution hint for providers that support named output resolutions.",
            },
            "api_family": {
                "type": "string",
                "description": "Provider-specific API family hint passed through when supported, e.g. classic/turbo/omni.",
            },
            "model_name": {
                "type": "string",
                "description": "Provider-specific model name passed through when supported.",
            },
            "model": {
                "type": "string",
                "description": "Exact provider model id, e.g. an Atlas Cloud live model route.",
            },
            "model_variant": {
                "type": "string",
                "description": "Provider route variant, e.g. standard or developer.",
            },
            "mode": {
                "type": "string",
                "description": "Provider-specific quality mode passed through when supported.",
            },
            "sound": {
                "type": "string",
                "description": "Provider-specific native audio toggle passed through when supported.",
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
            "workflow_json": {
                "type": "string",
                "description": (
                    "Optional full ComfyUI workflow JSON. Routes to a custom-workflow-capable "
                    "provider (e.g. comfyui_video) based on server availability, not bundled "
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
        """Auto-discover video generation providers from the registry."""
        from tools.tool_registry import registry
        registry.ensure_discovered()
        return [t for t in registry.get_by_capability("video_generation")
                if t.name != self.name]

    @property
    def fallback_tools(self) -> list[str]:
        """Static (input-agnostic) fallback list for external consumers / contracts.

        See :meth:`fallback_tools_for` for the input-aware form used during
        routing, which drops ``image_selector`` for motion-required briefs.
        """
        return [t.name for t in self._providers()] + ["image_selector"]

    def fallback_tools_for(self, inputs: dict[str, object]) -> list[str]:
        """Input-aware fallback list used during routing.

        ``image_selector`` is a legitimate degraded last-resort for a still-image
        brief (text_to_video with no motion requirement), but for motion-required
        operations (image_to_video / reference_to_video) an image-only fallback
        silently defeats the brief. Gate it here at the selector layer so a direct
        caller — with no director skill enforcing the prohibition — still cannot
        fall back to an image tool when motion was requested.
        """
        tools = [t.name for t in self._providers()]
        operation = inputs.get("operation", "text_to_video")
        if operation in self.MOTION_REQUIRED_OPERATIONS:
            return tools
        return tools + ["image_selector"]

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

    def estimate_cost(self, inputs: dict[str, object]) -> float:
        if inputs.get("operation") == "rank":
            return 0.0
        tool, adapted = self.resolve_execution(inputs)
        return tool.estimate_cost(adapted)

    def estimate_runtime(self, inputs: dict[str, object]) -> float:
        if inputs.get("operation") == "rank":
            return 0.0
        tool, adapted = self.resolve_execution(inputs)
        return tool.estimate_runtime(adapted)

    def resolve_execution(self, inputs: dict[str, object]) -> tuple[BaseTool, dict[str, object]]:
        """Resolve without uploads or generation; the budget gate binds this request."""
        tool, _ = self._select_best_tool(inputs, self._providers(), self._prepare_task_context(inputs))
        if tool is None:
            raise ValueError("Requested video provider/model or operation is unavailable; no substitution permitted")
        return tool, self._adapt_inputs(tool, inputs)

    @staticmethod
    def _effective_operation(inputs: dict[str, object]) -> str:
        if inputs.get("operation") == "rank":
            return str(inputs.get("target_operation", "text_to_video"))
        if inputs.get("operation"):
            return str(inputs["operation"])
        if any(inputs.get(k) for k in ("reference_image_urls", "reference_image_paths",
                                      "reference_video_urls", "reference_audio_urls", "image_list", "video_list", "element_list")):
            return "reference_to_video"
        if any(inputs.get(k) for k in ("image_url", "image_path", "reference_image_url",
                                      "reference_image_path", "input_reference_path")):
            return "image_to_video"
        if inputs.get("video_url") or inputs.get("video_path"):
            return "edit_video"
        return "text_to_video"

    def _adapt_inputs(self, tool: BaseTool, inputs: dict[str, object]) -> dict[str, object]:
        from lib.provider_jobs import reject_unsupported_media

        adapted = dict(inputs)
        props = tool.input_schema.get("properties", {})
        adapted["operation"] = self._provider_operation(tool, self._effective_operation(inputs))
        if "query" in props:
            adapted.setdefault("query", adapted.get("prompt", ""))
        for group in (
            ("reference_image_path", "image_path", "input_reference_path"),
            ("reference_image_url", "image_url", "input_reference_url"),
            ("video_path", "reference_video_path", "input_video_path"),
            ("video_url", "reference_video_url"),
            ("model", "model_name"),
        ):
            for source in group:
                if source in adapted and source not in props:
                    target = next((key for key in group if key in props), None)
                    if not target:
                        raise ValueError(f"{tool.name} does not support {source}; cannot drop it")
                    value = adapted.pop(source)
                    if target in adapted and adapted[target] != value:
                        raise ValueError(f"Conflicting {source} and {target}")
                    adapted[target] = value
        for key in ("reference_image_urls", "reference_image_paths", "reference_video_urls",
                    "reference_audio_urls", "video_url", "video_path", "image_list", "video_list",
                    "element_list", "reference_video_url", "reference_tail_image_path",
                    "reference_tail_image_url", "end_image_url"):
            if adapted.get(key) and key not in props:
                raise ValueError(f"{tool.name} cannot consume {key}; references cannot be stripped")
        if adapted["operation"] == "text_to_video" and any(adapted.get(key) for key in (
            "image_path", "reference_image_path", "input_reference_path", "image_url",
            "reference_image_url", "reference_image_urls", "reference_image_paths", "video_url",
            "image_list", "video_list", "element_list",
        )):
            raise ValueError("text_to_video cannot ignore supplied reference/edit inputs")
        for key in ("preferred_provider", "allowed_providers", "task_context", "preferred_provider_gap"):
            adapted.pop(key, None)
        reject_unsupported_media(adapted, props)
        normalizer = getattr(tool, "normalize_inputs", None)
        if callable(normalizer):
            return normalizer(adapted)
        for key, spec in props.items():
            if "default" in spec:
                adapted.setdefault(key, spec["default"])
        return adapted

    @staticmethod
    def _provider_operation(tool: BaseTool, operation: str) -> str:
        """Translate the two existing edit spellings without changing semantics."""
        if operation not in {"edit_video", "video_edit"}:
            return operation
        props = tool.input_schema.get("properties", {})
        advertised = set(getattr(tool, "capabilities", [])) | set(props.get("operation", {}).get("enum", []))
        advertised.update(key for key, value in getattr(tool, "supports", {}).items() if value)
        if operation in advertised:
            return operation
        return "edit_video" if operation == "video_edit" else "video_edit"

    def execute(self, inputs: dict[str, object]) -> ToolResult:
        from lib.scoring import rank_providers

        candidates = self._providers()

        # Rank mode — return scored provider rankings without generating
        if inputs.get("operation") == "rank":
            rank_inputs = self._rank_inputs(inputs)
            task_context = self._prepare_task_context(rank_inputs)
            candidates = self._filter_candidates(rank_inputs, candidates)
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
            result.data["alternatives_considered"] = [
                t.name for t in candidates
                if t.name != tool.name and t.get_status().value == "available"
            ]
            # Input-aware fallback list (drops image_selector for motion-required briefs).
            result.data.setdefault("fallback_tools", self.fallback_tools_for(inputs))
        return result

    def _select_best_tool(
        self,
        inputs: dict[str, object],
        candidates: list[BaseTool],
        task_context: dict[str, object],
    ) -> tuple[BaseTool | None, object]:
        """Rank only eligible candidates; an explicit choice is a hard constraint."""
        from lib.scoring import rank_providers

        preferred = inputs.get("preferred_provider", "auto")
        allowed = set(inputs.get("allowed_providers") or [])
        if allowed:
            candidates = [tool for tool in candidates if tool.provider in allowed or tool.name in allowed]
        if preferred != "auto":
            candidates = [tool for tool in candidates if preferred in {tool.provider, tool.name}]
        candidates = self._filter_candidates(inputs, candidates)

        env_hint = os.environ.get("VIDEO_GEN_LOCAL_MODEL", "").lower()
        env_map = {
            "wan2.2-ti2v-5b": "wan",
            "wan2.2-t2v-a14b": "wan",
            "wan2.2-i2v-a14b": "wan",
            "wan2.1-1.3b": "wan",
            "wan2.1-14b": "wan",
            "hunyuan-1.5": "hunyuan",
            "ltx2-local": "ltx",
            "cogvideo-5b": "cogvideo",
            "cogvideo-2b": "cogvideo",
        }
        if preferred == "auto" and env_hint in env_map:
            preferred = env_map[env_hint]

        rankings = rank_providers(candidates, task_context)

        # Selectable tools, keyed by NAME (not provider). Keying by provider
        # string shadowed one of two tools that legitimately share a provider —
        # e.g. seedance_video (fal) and seedance_replicate both have
        # provider="seedance", so only the first-registered was ever reachable.
        # Keying by name keeps every backend selectable; ranking picks the best.
        selectable_by_name: dict[str, BaseTool] = {
            tool.name: tool for tool in candidates if self._tool_selectable(tool, inputs)
        }

        def _tool_for(score: object) -> BaseTool | None:
            return selectable_by_name.get(getattr(score, "tool_name", None))

        # Environment hints are recommendations only; explicit preferences have
        # already constrained the candidate set, irrespective of score gap.
        if preferred != "auto" and rankings:
            preferred_score = next(
                (s for s in rankings if preferred in {s.provider, s.tool_name} and _tool_for(s) is not None),
                None,
            )
            if preferred_score is not None:
                return _tool_for(preferred_score), preferred_score

        # Return the highest-scored selectable provider
        for score in rankings:
            tool = _tool_for(score)
            if tool is not None:
                return tool, score

        return None, None

    def _prepare_task_context(self, inputs: dict[str, object]) -> dict[str, object]:
        from lib.scoring import normalize_task_context

        return normalize_task_context(
            inputs.get("task_context", {}),
            prompt=str(inputs.get("prompt", "")),
            capability=self.capability,
            operation=str(inputs.get("operation", "text_to_video")),
        )

    @staticmethod
    def _rank_inputs(inputs: dict[str, object]) -> dict[str, object]:
        rank_inputs = dict(inputs)
        rank_inputs["operation"] = inputs.get("target_operation", "text_to_video")
        return rank_inputs

    @staticmethod
    def _tool_context_payload(tool: BaseTool) -> dict[str, object]:
        info = tool.get_info()
        return {
            "selected_tool_agent_skills": info.get("agent_skills", []),
            "required_agent_skills": info.get("agent_skills", []),
            "selected_tool_usage_location": info.get("usage_location"),
            "selected_tool_best_for": info.get("best_for", []),
        }

    def _serialize_rankings(self, candidates: list[BaseTool], rankings: list[object]) -> list[dict[str, object]]:
        tool_by_name = {tool.name: tool for tool in candidates}
        serialized: list[dict[str, object]] = []
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

    def _filter_candidates(
        self,
        inputs: dict[str, object],
        candidates: list[BaseTool],
    ) -> list[BaseTool]:
        exact_model = inputs.get("model") or inputs.get("model_name")
        if exact_model:
            model_matches = [
                tool for tool in candidates
                if any(exact_model in getattr(tool, "input_schema", {}).get("properties", {}).get(key, {}).get("enum", [])
                       for key in ("model", "model_name", "model_variant"))
                or exact_model in tool.get_info().get("model_catalog", {})
                or (inputs.get("preferred_provider") not in (None, "auto")
                    and inputs.get("preferred_provider") in {tool.name, tool.provider}
                    and any(key in tool.input_schema.get("properties", {})
                            and "enum" not in tool.input_schema["properties"][key]
                            for key in ("model", "model_name")))
            ]
            candidates = model_matches
        for key in ("model_variant", "model_version"):
            if inputs.get(key):
                candidates = [tool for tool in candidates
                              if key in tool.input_schema.get("properties", {})
                              and ("enum" not in tool.input_schema["properties"][key]
                                   or inputs[key] in tool.input_schema["properties"][key]["enum"])]

        # A caller-supplied custom workflow is provider-specific (ComfyUI graph
        # JSON). Route it only to custom-workflow-capable providers whose server
        # is reachable — bundled-model readiness is irrelevant in that case.
        if self._has_custom_workflow(inputs):
            return [t for t in candidates if self._custom_workflow_eligible(t, inputs)]

        operation = self._effective_operation(inputs)

        filtered: list[BaseTool] = []
        for tool in candidates:
            supports = getattr(tool, "supports", {})
            props = getattr(tool, "input_schema", {}).get("properties", {})

            native_operation = self._provider_operation(tool, operation)
            advertised = (supports.get(native_operation) or native_operation in getattr(tool, "capabilities", [])
                          or native_operation in props.get("operation", {}).get("enum", []))
            if advertised and self._operation_ready(tool, native_operation):
                filtered.append(tool)

        return filtered

    @staticmethod
    def _operation_ready(tool: BaseTool, operation: str) -> bool:
        checker = getattr(tool, "is_operation_available", None)
        if not callable(checker):
            return True
        return bool(checker(operation))

    @staticmethod
    def _has_custom_workflow(inputs: dict[str, object]) -> bool:
        return bool(inputs.get("workflow_json") or inputs.get("workflow_path"))

    def _custom_workflow_eligible(self, tool: BaseTool, inputs: dict[str, object]) -> bool:
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

    def _tool_selectable(self, tool: BaseTool, inputs: dict[str, object]) -> bool:
        """A provider is selectable if it is AVAILABLE, or if it can serve a
        caller-supplied custom workflow even while bundled models report DEGRADED."""
        if tool.get_status() == ToolStatus.AVAILABLE:
            return True
        return self._custom_workflow_eligible(tool, inputs)
