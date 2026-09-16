"""Local, output-bound delivery checks shared by render, checkpoint and export.

These checks establish technical integrity, not creative quality or permission
to publish. Reviewers still own the visual/audio/promise checks.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from schemas.artifacts import validate_artifact


class DeliveryValidationError(ValueError):
    """The output cannot be accepted as a final deliverable."""


def content_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).expanduser().open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DeliveryValidationError(f"Cannot hash output {path}: {exc}") from exc
    return digest.hexdigest()


def validate_media(path: str | Path) -> dict[str, Any]:
    """Require a nonempty video stream, valid container, and full local decode.

    Returns the ffprobe JSON. Missing FFmpeg/ffprobe and timeouts fail closed;
    this never downloads tools or calls a provider.
    """
    path = Path(path).expanduser().resolve()
    try:
        if not path.is_file() or not path.stat().st_size:
            raise DeliveryValidationError(f"Missing or empty video output: {path}")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60, check=True,
        )
        data = json.loads(probe.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
        if not math.isfinite(duration) or duration <= 0 or not any(
            s.get("width", 0) > 0 and s.get("height", 0) > 0 for s in videos
        ):
            raise DeliveryValidationError(f"Invalid video container/stream: {path}")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-xerror", "-err_detect", "explode",
             "-i", str(path), "-map", "0:v", "-map", "0:a?", "-f", "null", "-"],
            capture_output=True, text=True, timeout=max(60, min(duration * 4, 3600)),
            check=True,
        )
        return data
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        if isinstance(exc, DeliveryValidationError):
            raise
        detail = getattr(exc, "stderr", None) or str(exc)
        raise DeliveryValidationError(f"Video probe/decode failed for {path}: {detail}") from exc


def validate_final_delivery(
    video_path: str | Path,
    final_review: dict[str, Any] | None,
    render_report: dict[str, Any] | None = None,
) -> None:
    """Require PASS review of the exact current bytes and an optional report.

    Relative schema paths are interpreted relative to the caller's working
    directory, as they are by the rendering tools. Use absolute paths for
    durable cross-working-directory handoffs.
    """
    try:
        validate_artifact("final_review", final_review)
        if final_review["status"] != "pass":
            raise DeliveryValidationError("Final delivery requires a PASS final_review")
        if final_review.get("recommended_action", "present_to_user") != "present_to_user":
            raise DeliveryValidationError("Final review still requests revision or blocking")
        path = Path(video_path).expanduser().resolve()
        if Path(final_review["output_path"]).expanduser().resolve() != path:
            raise DeliveryValidationError("Final review output_path does not match the output")
        digest = content_sha256(path)
        if final_review.get("output_sha256") != digest:
            raise DeliveryValidationError("Final review output_sha256 is missing or mismatched")
        if final_review.get("output_size_bytes", path.stat().st_size) != path.stat().st_size:
            raise DeliveryValidationError("Final review output_size_bytes is mismatched")
        reviewed_at = datetime.fromisoformat(final_review.get("reviewed_at", "").replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None or reviewed_at.timestamp() < path.stat().st_mtime:
            raise DeliveryValidationError("Final review is stale: reviewed_at precedes output modification")
        if render_report is not None:
            validate_artifact("render_report", render_report)
            outputs = [
                output for output in render_report["outputs"]
                if Path(output["path"]).expanduser().resolve() == path
            ]
            if len(outputs) != 1 or outputs[0].get("sha256") != digest:
                raise DeliveryValidationError("Render report must identify this output and its sha256")
        validate_media(path)
        # Detect concurrent output replacement during the probe/decode.
        if content_sha256(path) != digest or path.stat().st_mtime > reviewed_at.timestamp():
            raise DeliveryValidationError("Output changed during final delivery validation")
    except DeliveryValidationError:
        raise
    except Exception as exc:
        raise DeliveryValidationError(f"Invalid final review/delivery evidence: {exc}") from exc
