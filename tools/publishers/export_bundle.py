"""Local export bundler — the first PUBLISH-tier tool.

Every pipeline ends in a `publish` stage that produces a `publish_log` artifact,
but `tools/publishers/` shipped empty, so the mechanical packaging (copying the
render, writing metadata files, laying out the export directory, and emitting a
schema-valid `publish_log`) had to be hand-rolled by the agent each time.

This tool does that packaging deterministically and locally — no external
account, no upload, no cost. It takes the final render path plus the SEO
metadata the publish-director skill prepares and writes a self-contained export
bundle a creator can hand to any platform, returning a validated `publish_log`
entry with `status: "exported"`.

A networked publisher (e.g. a YouTube uploader) can be added later as a separate
`provider` under the same `publish` capability.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import jsonschema

from lib.delivery_validation import content_sha256, validate_final_delivery
from schemas.artifacts import validate_artifact
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class ExportBundle(BaseTool):
    name = "export_bundle"
    version = "0.1.0"
    tier = ToolTier.PUBLISH
    capability = "publish"
    provider = "local"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = []  # Draft packaging is filesystem-only; final checks fail closed.
    install_instructions = "Draft packaging needs only Python. Final delivery requires local FFmpeg and ffprobe."

    agent_skills = []

    capabilities = ["package_export", "write_publish_log"]
    supports = {
        "local_offline": True,
        "free": True,
        "uploads": False,
    }
    best_for = [
        "packaging a finished render for hand-off to any platform",
        "producing a schema-valid publish_log without an external account",
        "offline / no-API-key publishing",
    ]
    not_good_for = [
        "uploading directly to YouTube/TikTok/etc. (no network publish)",
        "generating SEO metadata or thumbnails (the publish-director prepares those)",
    ]

    input_schema = {
        "type": "object",
        "required": ["video_path", "title"],
        "properties": {
            "video_path": {
                "type": "string",
                "description": "Path to the final rendered video (from render_report.outputs[].path).",
            },
            "delivery_mode": {
                "type": "string", "enum": ["final", "draft"], "default": "final",
                "description": "Final requires output-bound PASS review and decode; draft is never accepted delivery.",
            },
            "final_review": {"type": "object"},
            "render_report": {"type": "object"},
            "title": {"type": "string", "description": "Video title / SEO title."},
            "project_name": {
                "type": "string",
                "description": "Project name; used for the export folder. Defaults to the video's parent-of-parent dir name.",
            },
            "export_dir": {
                "type": "string",
                "description": "Override the export root. Defaults to 'exports/<project_name>'.",
            },
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "chapters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "description": "Either {start_seconds, title} or {time, label}.",
                },
            },
            "subtitles_path": {"type": "string"},
            "thumbnail_path": {"type": "string"},
            "thumbnail_concept": {
                "type": "object",
                "description": "Thumbnail concept JSON when no rendered thumbnail exists.",
            },
            "platform": {
                "type": "string",
                "description": "Target platform label for the publish_log entry. Defaults to 'local'.",
            },
            "visibility": {"type": "string", "enum": ["public", "private", "unlisted"]},
            "timestamp": {
                "type": "string",
                "description": "Override the ISO-8601 timestamp (mainly for deterministic tests).",
            },
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "publish_log": {"type": "object"},
            "export_path": {"type": "string"},
            "files_written": {"type": "array", "items": {"type": "string"}},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=0, network_required=False
    )
    side_effects = ["writes an export bundle directory to disk"]
    user_visible_verification = [
        "Open the export folder and confirm the video, metadata, and chapters are present and correct",
    ]

    # ---- Helpers ----

    @staticmethod
    def _format_chapter_time(seconds: float) -> str:
        seconds = int(round(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _chapter_lines(self, chapters: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for ch in chapters:
            label = ch.get("title") or ch.get("label") or ""
            if "start_seconds" in ch or "time_seconds" in ch:
                ts = self._format_chapter_time(ch.get("start_seconds", ch.get("time_seconds", 0)))
            elif "time" in ch:
                ts = str(ch["time"])
            else:
                ts = "0:00"
            lines.append(f"{ts} - {label}".rstrip(" -"))
        return lines

    # ---- Execution ----

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        staging = None
        try:
            jsonschema.validate(inputs, self.input_schema)
            video_path = Path(inputs["video_path"]).expanduser()
            if not video_path.is_file():
                return ToolResult(success=False, error=f"video_path not found: {video_path}")
            for key in ("subtitles_path", "thumbnail_path"):
                if inputs.get(key) and not Path(inputs[key]).expanduser().is_file():
                    return ToolResult(success=False, error=f"{key} provided but not found: {inputs[key]}")
            mode = inputs.get("delivery_mode", "final")
            if mode == "final":
                validate_final_delivery(video_path, inputs.get("final_review"), inputs.get("render_report"))
            project_name = inputs.get("project_name") or self._infer_project_name(video_path)
            root = (
                Path(inputs["export_dir"]).expanduser()
                if inputs.get("export_dir") else self._default_export_dir(video_path, project_name)
            ).absolute()
            if root.is_symlink() or root.resolve() == video_path.resolve() or root.resolve() in video_path.resolve().parents:
                raise ValueError("export_dir must not be a symlink or contain the source video")
            publish_log = self._publish_log(inputs, root)
            # Validate all prospective logs before creating even the staging directory.
            validate_artifact("publish_log", publish_log)
            root.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.staging-", dir=root.parent))
            result = self._build_bundle({**inputs, "export_dir": str(staging)})
            if not result.success:
                return result
            out_video = Path(result.artifacts[0])
            digest = content_sha256(out_video)
            if mode == "final":
                # copy2 preserves mtime. Revalidate the staged bytes, not merely
                # the source that could have changed between validation/copy.
                review = {**inputs["final_review"], "output_path": str(out_video)}
                validate_final_delivery(out_video, review)
                (staging / "metadata" / "final_review.json").write_text(
                    json.dumps(inputs["final_review"], indent=2), encoding="utf-8"
                )
            (staging / "metadata" / "publish_log.json").write_text(
                json.dumps(publish_log, indent=2), encoding="utf-8"
            )
            (staging / "metadata" / "delivery.json").write_text(json.dumps({
                "delivery_mode": mode, "source_path": str(video_path.resolve()),
                "video_path": str(out_video.relative_to(staging)), "sha256": digest,
            }, indent=2), encoding="utf-8")
            files = [str(root / p.relative_to(staging)) for p in sorted(staging.rglob("*")) if p.is_file()]
            final_video = str(root / out_video.relative_to(staging))
            self._commit_bundle(staging, root)
            return ToolResult(success=True, data={
                "publish_log": publish_log, "export_path": str(root),
                "files_written": files, "delivery_mode": mode,
            }, artifacts=[final_video])
        except Exception as exc:
            return ToolResult(success=False, error=f"Export bundle rejected: {exc}")
        finally:
            if staging is not None and staging.exists():
                try:
                    shutil.rmtree(staging)
                except OSError:
                    import logging
                    logging.getLogger(__name__).warning("Could not remove export staging directory %s", staging)

    @staticmethod
    def _commit_bundle(staging: Path, root: Path) -> None:
        """One namespace operation publishes the entire replacement on POSIX.

        Never emulate a directory exchange with old->backup/new->old renames:
        that loses the atomic visibility and crash-preservation guarantees.
        Unsupported filesystems/platforms fail without changing the old export.
        """
        import ctypes
        import fcntl

        fd = os.open(root.parent, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            if not root.exists():
                os.replace(staging, root)
                return
            if root.is_symlink() or not root.is_dir():
                raise ValueError("Existing export must be a real directory")
            libc = ctypes.CDLL(None, use_errno=True)
            if sys.platform == "darwin":
                swap = libc.renamex_np
                swap.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
                result = swap(os.fsencode(staging), os.fsencode(root), 2)  # RENAME_SWAP
            elif sys.platform.startswith("linux"):
                swap = libc.renameat2
                swap.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
                result = swap(-100, os.fsencode(staging), -100, os.fsencode(root), 2)  # RENAME_EXCHANGE
            else:
                raise OSError("Atomic directory replacement requires macOS or Linux")
            if result != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
        finally:
            os.close(fd)

    @staticmethod
    def _publish_log(inputs: dict[str, Any], export_root: Path) -> dict[str, Any]:
        timestamp = inputs.get("timestamp") or datetime.now(timezone.utc).isoformat()
        # JSON Schema date-time checking may be unavailable without its optional
        # format extras; this local contract must not silently skip validation.
        if datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("publish_log timestamp must include a timezone")
        entry = {
            "platform": inputs.get("platform", "local"),
            "status": "draft" if inputs.get("delivery_mode") == "draft" else "exported",
            "export_path": str(export_root),
            "timestamp": timestamp,
            "metadata_used": {
                "title": inputs["title"], "description": inputs.get("description", ""),
                "hashtags": inputs.get("hashtags", []) or [],
                "chapters": inputs.get("chapters", []) or [],
            },
        }
        if inputs.get("visibility"):
            entry["visibility"] = inputs["visibility"]
        return {"version": "1.0", "entries": [entry]}

    def _build_bundle(self, inputs: dict[str, Any]) -> ToolResult:
        video_path = Path(inputs["video_path"]).expanduser()
        if not video_path.is_file():
            return ToolResult(success=False, error=f"video_path not found: {video_path}")

        title = inputs["title"]
        project_name = inputs.get("project_name") or self._infer_project_name(video_path)

        # Explicitly-provided optional assets must exist — silently dropping them
        # would ship a publish package missing part of an approved deliverable.
        for key in ("subtitles_path", "thumbnail_path"):
            val = inputs.get(key)
            if val and not Path(val).expanduser().is_file():
                return ToolResult(success=False, error=f"{key} provided but not found: {val}")

        export_root = (
            Path(inputs["export_dir"]).expanduser()
            if inputs.get("export_dir")
            else self._default_export_dir(video_path, project_name)
        )

        video_dir = export_root / "video"
        meta_dir = export_root / "metadata"
        thumb_dir = export_root / "thumbnails"
        for d in (video_dir, meta_dir, thumb_dir):
            d.mkdir(parents=True, exist_ok=True)

        files_written: list[str] = []

        # Video
        out_video = video_dir / f"output{video_path.suffix or '.mp4'}"
        shutil.copy2(video_path, out_video)
        files_written.append(str(out_video))

        # Subtitles (optional)
        subs_in = inputs.get("subtitles_path")
        if subs_in:
            subs_in = Path(subs_in).expanduser()
            if subs_in.is_file():
                out_subs = video_dir / f"subtitles{subs_in.suffix or '.srt'}"
                shutil.copy2(subs_in, out_subs)
                files_written.append(str(out_subs))

        description = inputs.get("description", "")
        tags = inputs.get("tags", []) or []
        hashtags = inputs.get("hashtags", []) or []
        chapters = inputs.get("chapters", []) or []
        chapter_lines = self._chapter_lines(chapters)

        # metadata.json
        metadata = {
            "title": title,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "chapters": chapters,
        }
        meta_json = meta_dir / "metadata.json"
        meta_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        files_written.append(str(meta_json))

        # description.txt (description + chapters appended, ready to paste)
        desc_parts = [description] if description else []
        if chapter_lines:
            desc_parts.append("\n".join(chapter_lines))
        desc_txt = meta_dir / "description.txt"
        desc_txt.write_text("\n\n".join(desc_parts) + ("\n" if desc_parts else ""), encoding="utf-8")
        files_written.append(str(desc_txt))

        # tags.txt (one per line)
        if tags:
            tags_txt = meta_dir / "tags.txt"
            tags_txt.write_text("\n".join(tags) + "\n", encoding="utf-8")
            files_written.append(str(tags_txt))

        # chapters.txt
        if chapter_lines:
            chapters_txt = meta_dir / "chapters.txt"
            chapters_txt.write_text("\n".join(chapter_lines) + "\n", encoding="utf-8")
            files_written.append(str(chapters_txt))

        # Thumbnail: real image if given, else concept JSON
        thumb_in = inputs.get("thumbnail_path")
        if thumb_in and Path(thumb_in).expanduser().is_file():
            thumb_in = Path(thumb_in).expanduser()
            out_thumb = thumb_dir / f"thumbnail{thumb_in.suffix or '.png'}"
            shutil.copy2(thumb_in, out_thumb)
            files_written.append(str(out_thumb))
        elif inputs.get("thumbnail_concept"):
            concept = thumb_dir / "concept.json"
            concept.write_text(json.dumps(inputs["thumbnail_concept"], indent=2), encoding="utf-8")
            files_written.append(str(concept))

        publish_log = self._publish_log(inputs, export_root)

        # Validate against the canonical schema so a bad entry fails here, not at checkpoint.
        try:
            from schemas.artifacts import validate_artifact

            validate_artifact("publish_log", publish_log)
        except Exception as exc:  # pragma: no cover - defensive
            return ToolResult(success=False, error=f"publish_log failed schema validation: {exc}")

        return ToolResult(
            success=True,
            data={
                "publish_log": publish_log,
                "export_path": str(export_root),
                "files_written": files_written,
            },
            artifacts=[str(out_video)],
        )

    @staticmethod
    def _default_export_dir(video_path: Path, project_name: str) -> Path:
        """Keep run output inside the project workspace.

        When the render lives at ``projects/<name>/renders/...`` (the OpenMontage
        convention), default the bundle to ``projects/<name>/exports/`` alongside
        ``artifacts/``, ``assets/`` and ``renders/``. Otherwise fall back to a
        top-level ``exports/<project_name>/``.
        """
        resolved = video_path.resolve()
        if resolved.parent.name == "renders":
            return resolved.parent.parent / "exports"
        return Path("exports") / project_name

    @staticmethod
    def _infer_project_name(video_path: Path) -> str:
        # projects/<name>/renders/final.mp4 -> <name>; fall back to the file stem.
        parents = video_path.resolve().parents
        if len(parents) >= 2:
            return parents[1].name
        return video_path.stem
