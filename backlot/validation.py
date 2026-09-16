"""Defensive board projections, not production/checkpoint schema validation.

Only fields consumed structurally by the board are constrained. Unknown fields
remain available in the artifact drawer; damaged fields are omitted with their
source location, without discarding readable siblings or rewriting disk.
"""

import math


def diagnose(diagnostics: list[dict], scope: str, message: str) -> None:
    diagnostics.append({"scope": scope, "message": message})


def finite_json(value, scope: str, diagnostics: list[dict]):
    """Python accepts NaN/Infinity in JSON; ASGI's JSON encoder does not."""
    if isinstance(value, float) and not math.isfinite(value):
        diagnose(diagnostics, scope, "expected a finite number")
        return None
    if isinstance(value, dict):
        return {k: finite_json(v, f"{scope}.{k}", diagnostics) for k, v in value.items()}
    if isinstance(value, list):
        return [finite_json(v, f"{scope}[{i}]", diagnostics) for i, v in enumerate(value)]
    return value


def project(value, spec, scope: str, diagnostics: list[dict]):
    if spec is None:
        return value
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            diagnose(diagnostics, scope, "expected an object")
            return {}
        result = dict(value)
        for key, child_spec in spec.items():
            if key in result and result[key] is not None:
                result[key] = project(result[key], child_spec, f"{scope}.{key}", diagnostics)
        return result
    if isinstance(spec, list):
        if not isinstance(value, list):
            diagnose(diagnostics, scope, "expected an array")
            return []
        result = []
        for i, child in enumerate(value):
            child_scope = f"{scope}[{i}]"
            if isinstance(spec[0], dict) and not isinstance(child, dict):
                diagnose(diagnostics, child_scope, "expected an object")
                continue
            result.append(project(child, spec[0], child_scope, diagnostics))
        return result
    if spec == "id":
        valid = isinstance(value, (str, int)) and not isinstance(value, bool)
    elif spec in ("number", "time"):
        valid = type(value) is int or (type(value) is float and math.isfinite(value))
        if valid and spec == "time":
            valid = value >= 0
    else:
        valid = isinstance(value, spec)
    if valid:
        return value
    expected = spec if isinstance(spec, str) else spec.__name__
    diagnose(diagnostics, scope, f"expected {expected}")
    return None


TIMING = {"start_seconds": "time", "end_seconds": "time", "duration_seconds": "time"}
METADATA = {"total_duration_seconds": "time", "partial_progress": {"completed_scene_ids": ["id"]}}
CHECKPOINT = {
    "pipeline_type": str, "status": str, "timestamp": str,
    "human_approved": bool, "metadata": METADATA, "artifacts": {},
    "review": {}, "cost_snapshot": {
        "total_spent_usd": "number", "budget_remaining_usd": "number",
        "total_reserved_usd": "number",
    },
}
MARKER = {"title": str, "name": str, "pipeline_type": str, "created_at": str}
ARTIFACTS = {
    "script": {
        "sections": [{**TIMING, "id": "id", "enhancement_cues": [{}]}],
        "total_duration_seconds": "time",
    },
    "scene_plan": {
        "scenes": [{**TIMING, "id": "id", "script_section_id": "id", "required_assets": [None]}],
        "metadata": METADATA,
    },
    "asset_manifest": {
        "assets": [{"id": "id", "scene_id": "id", "path": str, "type": str}],
        "total_cost_usd": "number",
    },
    "decision_log": {"decisions": [{"options_considered": [{}]}]},
    "brief": {"key_points": [None]},
    "proposal_packet": {
        "concept_options": [{}], "selected_concept": {}, "production_plan": {}, "cost_estimate": {},
    },
    "research_brief": {"sources": [None], "data_points": [None], "angles_discovered": [None]},
    "edit_decisions": {"cuts": [{}], "metadata": {}},
    "render_report": {"outputs": [None]},
    "publish_log": {"entries": [{}]},
}


def artifact_projection(value: dict, name: str, scope: str, diagnostics: list[dict]) -> dict:
    result = project(value, ARTIFACTS.get(name, {}), scope, diagnostics)
    for field in (("scenes",) if name == "scene_plan" else ("sections",) if name == "script" else ()):
        for i, entry in enumerate(result.get(field) or []):
            start, end = entry.get("start_seconds"), entry.get("end_seconds")
            if start is not None and end is not None and end < start:
                diagnose(diagnostics, f"{scope}.{field}[{i}].end_seconds", "ends before start_seconds")
                entry["end_seconds"] = None
    return result
