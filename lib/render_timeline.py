"""Canonical cut timing: source trims are never composition positions."""

from __future__ import annotations

import math
from typing import Any


def normalize_cuts(cuts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return validated cuts with explicit timeline start and duration.

    Omitted positions append sequentially. Duration is derived from source
    range / speed; an explicit duration must agree rather than lose content.
    """
    normalized = []
    cursor = 0.0
    for index, cut in enumerate(cuts):
        def number(key: str, default: float) -> float:
            try:
                value = float(cut.get(key, default))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Cut {index}: {key} must be a finite number") from exc
            if not math.isfinite(value):
                raise ValueError(f"Cut {index}: {key} must be a finite number")
            return value

        source_in = number("in_seconds", 0)
        source_out = number("out_seconds", source_in)
        speed = number("speed", 1)
        if source_in < 0 or source_out <= source_in or speed <= 0:
            raise ValueError(f"Cut {index}: require 0 <= in_seconds < out_seconds and speed > 0")
        duration = (source_out - source_in) / speed
        start = number("timeline_start_seconds", cursor)
        declared_duration = number("timeline_duration_seconds", duration)
        if start < 0 or not math.isclose(declared_duration, duration, abs_tol=1e-6):
            raise ValueError(f"Cut {index}: invalid timeline position or duration disagrees with trim/speed")
        normalized.append({
            **cut, "in_seconds": source_in, "out_seconds": source_out, "speed": speed,
            "timeline_start_seconds": start, "timeline_duration_seconds": duration,
        })
        cursor = max(cursor, start + duration)
    return normalized


def timeline_duration(cuts: list[dict[str, Any]]) -> float:
    return max((c["timeline_start_seconds"] + c["timeline_duration_seconds"]
                for c in normalize_cuts(cuts)), default=0.0)


def require_sequential(cuts: list[dict[str, Any]]) -> None:
    """Concat-only engines must reject gaps/layers instead of flattening them."""
    cursor = 0.0
    for cut in cuts:
        if cut.get("layer", "primary") != "primary" or not math.isclose(
            cut["timeline_start_seconds"], cursor, abs_tol=1e-6,
        ):
            raise ValueError("This renderer requires sequential primary cuts; gaps/overlaps/layers are unsupported")
        cursor += cut["timeline_duration_seconds"]
