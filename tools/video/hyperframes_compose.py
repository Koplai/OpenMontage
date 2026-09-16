"""HyperFrames composition tool — HTML/CSS/GSAP render path.

Sibling to `video_compose` (FFmpeg + Remotion). This tool owns the HyperFrames
runtime end-to-end: workspace materialization, `hyperframes lint`,
`hyperframes check`, and `hyperframes render`. It is invoked by
`video_compose` when `edit_decisions.render_runtime == "hyperframes"`, and
can also be called directly by pipelines that want HyperFrames-specific
operations (check/lint/validate/inspect, scaffold-only, or an
existing-workspace atelier render that preserves authored HTML).

This tool deliberately does NOT attempt parity with every Remotion scene
component. See `skills/core/hyperframes.md` for what is in scope in Phase 1
and what remains Remotion-only.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import time
import tempfile
from pathlib import Path
from typing import Any, Optional
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from lib.render_timeline import normalize_cuts, require_sequential, timeline_duration
from tools.video.video_compose import VideoCompose, _atomic_render, _validate_rendered_video

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ResumeSupport,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


log = logging.getLogger("hyperframes_compose")


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
HYPERFRAMES_VERSION = "0.8.40"


class HyperFramesCompose(BaseTool):
    name = "hyperframes_compose"
    version = "0.2.0"
    tier = ToolTier.CORE
    capability = "video_post"
    provider = "hyperframes"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:npx", "cmd:ffmpeg"]
    install_instructions = (
        "Requires Node.js >= 22 (https://nodejs.org/) and FFmpeg "
        "(https://ffmpeg.org/download.html). Install explicitly with "
        f"`npm install --prefix remotion-composer --no-save hyperframes@{HYPERFRAMES_VERSION}` "
        "(npm package: `hyperframes`). Status never downloads or executes it. "
        "Note: the upstream monorepo develops the package as `@hyperframes/cli`, "
        "but it publishes to npm as `hyperframes`. `npx @hyperframes/cli` "
        "returns 404 -- do NOT use that form. Verify setup with "
        f"`npx hyperframes@{HYPERFRAMES_VERSION} doctor` or run the explicitly requested "
        "`doctor` operation on this tool. Rendering uses only the pinned installed CLI."
    )
    agent_skills = [
        "hyperframes",
        "hyperframes-cli",
        "hyperframes-registry",
        "website-to-video",
        "gsap-core",
        "gsap-timeline",
    ]

    capabilities = [
        "hyperframes_render",
        "hyperframes_lint",
        "hyperframes_validate",
        "hyperframes_inspect",
        "hyperframes_check",
        "hyperframes_doctor",
        "scaffold_workspace",
        "render_existing_workspace",
        "add_block",
    ]

    best_for = [
        "HTML/CSS/GSAP composition: kinetic typography, product promos, launch reels",
        "Motion-graphics-heavy briefs where the scene library in remotion-composer/ doesn't fit",
        "Website-to-video / UI-driven compositions",
        "Registry-block-driven scenes (hyperframes add data-chart, grain-overlay, etc.)",
        "Hand-authored atelier workspaces, including deterministic Three.js worlds",
    ]
    not_good_for = [
        "Word-level caption burn (stays on Remotion in Phase 1)",
        "Avatar / lip-sync presenter (stays on Remotion in Phase 1)",
        "Existing React scene stack (text_card, stat_card, chart, comparison): reuse Remotion",
    ]
    fallback_tools = ["video_compose"]

    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "render",
                    "render_existing",
                    "lint",
                    "validate",
                    "inspect",
                    "check",
                    "doctor",
                    "scaffold_workspace",
                    "add_block",
                ],
                "description": (
                    "render: materialize workspace + lint + validate + render to MP4. "
                    "render_existing: preserve an authored index.html, then check + render it. "
                    "lint: run `hyperframes lint` on an existing workspace. "
                    "validate: run `hyperframes validate` (browser-based). "
                    "inspect: seek an existing workspace and audit layout/runtime issues. "
                    "check: run the current unified lint/runtime/layout/motion/contrast gate. "
                    "doctor: run `hyperframes doctor` to check environment. "
                    "scaffold_workspace: materialize HTML/CSS/assets but do not render. "
                    "add_block: run `hyperframes add <name>` to install a registry "
                    "block or component into an existing workspace."
                ),
            },
            "block_name": {
                "type": "string",
                "description": (
                    "Registry block or component name for operation='add_block' "
                    "(e.g. 'data-chart', 'grain-overlay', 'shimmer-sweep'). "
                    "See https://hyperframes.heygen.com/catalog for the list."
                ),
            },
            "workspace_path": {
                "type": "string",
                "description": (
                    "Target HyperFrames workspace directory. Typically "
                    "`projects/<name>/hyperframes/`. Required for every op "
                    "except doctor."
                ),
            },
            "output_path": {
                "type": "string",
                "description": "Output MP4 path. Used by render and render_existing.",
            },
            "audio_path": {"type": "string", "description": "Approved final mix, padded and muxed after rendering."},
            "subtitle_path": {"type": "string", "description": "Approved subtitles, burned after rendering or explicitly blocked."},
            "draft": {
                "type": "boolean", "default": False,
                "description": "Allow labeled missing-asset placeholders in scaffolds; never an accepted deliverable.",
            },
            "edit_decisions": {
                "type": "object",
                "description": (
                    "Full edit_decisions artifact — required for render and "
                    "scaffold_workspace. Used to generate index.html + CSS."
                ),
            },
            "asset_manifest": {
                "type": "object",
                "description": (
                    "Full asset_manifest artifact — required for render and "
                    "scaffold_workspace. Used to resolve asset IDs to file paths."
                ),
            },
            "playbook": {
                "type": "object",
                "description": (
                    "Loaded playbook dict. Used to drive the style bridge "
                    "(CSS custom properties, typography, motion defaults)."
                ),
            },
            "profile": {
                "type": "string",
                "description": "Media profile name (youtube_landscape, tiktok_vertical, etc.).",
            },
            "quality": {
                "type": "string",
                "enum": ["draft", "standard", "high"],
                "default": "standard",
                "description": "Render quality. `draft` for iterating, `high` for delivery.",
            },
            "fps": {
                "type": "integer",
                "enum": [24, 30, 60],
                "default": 30,
            },
            "strict": {
                "type": "boolean",
                "default": False,
                "description": (
                    "If true, fail the render on any lint error. Matches "
                    "`hyperframes render --strict`."
                ),
            },
            "skip_contrast": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Skip the WCAG contrast audit during check. Acceptable "
                    "while iterating; forbidden for final delivery."
                ),
            },
            "strict_check": {
                "type": "boolean",
                "default": False,
                "description": "Treat HyperFrames check warnings as errors.",
            },
            "snapshots": {
                "type": "boolean",
                "default": False,
                "description": "Save representative quality-check snapshots.",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=3072, vram_mb=0, disk_mb=2000, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=0)
    resume_support = ResumeSupport.FROM_START
    idempotency_key_fields = ["operation", "workspace_path", "edit_decisions"]
    side_effects = [
        "writes HTML/CSS/JS files into workspace_path",
        "copies asset files into workspace_path/assets/",
        "writes MP4 to output_path",
    ]
    user_visible_verification = [
        "Play the rendered MP4 and verify scene pacing, typography, and audio",
        "Inspect workspace_path/index.html in a browser via `npx hyperframes preview`",
    ]

    # ------------------------------------------------------------------
    # Status / availability
    # ------------------------------------------------------------------

    _NODE_FLOOR_MAJOR = 22
    _NPM_PACKAGE = "hyperframes"  # published npm name (NOT @hyperframes/cli — that's 404)
    # Retained for callers that reset the old cache; discovery is now passive
    # and rereads local metadata so explicit installations become visible.
    _npm_resolve_cache: Optional[dict[str, str]] = None
    _cli_probe_cache: Optional[dict[str, str]] = None

    @classmethod
    def _node_major_version(cls) -> Optional[int]:
        """Return Node.js major version, or None if node isn't installed."""
        node = shutil.which("node")
        if not node:
            return None
        try:
            out = subprocess.run(
                [node, "--version"], capture_output=True, text=True, timeout=5
            )
            if out.returncode != 0:
                return None
            match = re.match(r"v?(\d+)\.", out.stdout.strip())
            if not match:
                return None
            return int(match.group(1))
        except (OSError, subprocess.SubprocessError):
            return None

    @classmethod
    def _resolve_npm_package(cls) -> dict[str, str]:
        """Read only installed package metadata; never npm view/npx/doctor."""
        repo = Path(__file__).resolve().parents[2]
        candidates = [
            repo / "remotion-composer/node_modules/hyperframes/package.json",
            repo / "node_modules/hyperframes/package.json",
        ]
        executable = shutil.which("hyperframes")
        if executable:
            # Global npm links resolve into the installed package's bin/dist.
            candidates.extend(p / "package.json" for p in Path(executable).resolve().parents)
        for manifest in candidates:
            if not manifest.is_file():
                continue
            try:
                package = json.loads(manifest.read_text(encoding="utf-8"))
                if package.get("name") != cls._NPM_PACKAGE:
                    continue
                if package.get("version") != HYPERFRAMES_VERSION:
                    continue
                binary = package.get("bin", {})
                relative = binary if isinstance(binary, str) else binary.get("hyperframes")
                entry = (manifest.parent / relative).resolve() if relative else None
                if entry and entry.is_file():
                    return {"version": HYPERFRAMES_VERSION, "entry": str(entry)}
            except (OSError, ValueError, TypeError):
                continue
        return {"error": f"hyperframes@{HYPERFRAMES_VERSION} is not installed with a valid CLI entry"}

    @classmethod
    def _probe_cli(cls) -> dict[str, str]:
        """Passive installed-entry check. Only explicit doctor runs the CLI."""
        installed = cls._resolve_npm_package()
        return {"error": installed["error"]} if "error" in installed else {"status": "installed; doctor not run"}

    def _runtime_check(self) -> dict[str, Any]:
        """Report installed availability, not an active browser/doctor certification."""
        node_major = self._node_major_version()
        ffmpeg_ok = shutil.which("ffmpeg") is not None
        npx_ok = shutil.which("npx") is not None

        reasons: list[str] = []
        if node_major is None:
            reasons.append("node not found on PATH")
        elif node_major < self._NODE_FLOOR_MAJOR:
            reasons.append(
                f"node major version {node_major} < required {self._NODE_FLOOR_MAJOR}"
            )
        if not ffmpeg_ok:
            reasons.append("ffmpeg not found on PATH")

        # Inspect installed metadata only after checking the local tooling.
        npm_resolve: dict[str, str] = {}
        if not reasons:
            npm_resolve = self._resolve_npm_package()
            if "error" in npm_resolve:
                reasons.append(
                    f"npm package `{self._NPM_PACKAGE}` not resolvable: "
                    f"{npm_resolve['error']}"
                )

        cli_probe: dict[str, str] = {}
        if not reasons:
            cli_probe = self._probe_cli()
            if "error" in cli_probe:
                reasons.append(f"published CLI is not executable: {cli_probe['error']}")

        return {
            "runtime_available": not reasons,
            "node_major": node_major,
            "ffmpeg_available": ffmpeg_ok,
            "npx_available": npx_ok,
            "npm_package": self._NPM_PACKAGE,
            "npm_package_version": npm_resolve.get("version"),
            "required_version": HYPERFRAMES_VERSION,
            "npm_resolve_error": npm_resolve.get("error"),
            "cli_probe_status": cli_probe.get("status"),
            "cli_probe_error": cli_probe.get("error"),
            "reasons": reasons,
        }

    def get_status(self) -> ToolStatus:
        check = self._runtime_check()
        return ToolStatus.AVAILABLE if check["runtime_available"] else ToolStatus.UNAVAILABLE

    def get_info(self) -> dict[str, Any]:
        info = super().get_info()
        check = self._runtime_check()
        info["hyperframes_runtime"] = check
        if not check["runtime_available"]:
            info["setup_offer"] = {
                "effort": (
                    "1-minute fix"
                    if check["npx_available"] and check["ffmpeg_available"]
                    else "5-minute fix (install Node 22+ and/or FFmpeg)"
                ),
                "install_instructions": self.install_instructions,
                "unlocks": (
                    "HTML/CSS/GSAP composition runtime — kinetic typography, "
                    "product promos, registry blocks, website-to-video."
                ),
            }
        return info

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        ed = inputs.get("edit_decisions") or {}
        cuts = ed.get("cuts", [])
        total = 0.0
        for c in cuts:
            out_s = float(c.get("out_seconds", 0) or 0)
            in_s = float(c.get("in_seconds", 0) or 0)
            total += max(0.0, out_s - in_s)
        return 30.0 + total * 0.5

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        operation = inputs["operation"]
        start = time.time()
        try:
            if operation == "doctor":
                result = self._doctor(inputs)
            elif operation == "scaffold_workspace":
                result = self._scaffold(inputs)
            elif operation == "lint":
                result = self._lint(inputs)
            elif operation == "validate":
                result = self._validate(inputs)
            elif operation == "inspect":
                result = self._inspect(inputs)
            elif operation == "check":
                result = self._check(inputs)
            elif operation == "render":
                result = self._render(inputs)
            elif operation == "render_existing":
                result = self._render_existing(inputs)
            elif operation == "add_block":
                result = self._add_block(inputs)
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            log.exception("hyperframes_compose failed")
            return ToolResult(success=False, error=f"{type(e).__name__}: {e}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def _doctor(self, inputs: dict[str, Any]) -> ToolResult:
        """Probe the environment. Reports node/ffmpeg/npx plus CLI doctor output."""
        check = self._runtime_check()
        out: dict[str, Any] = {"runtime_check": check}

        if not check["runtime_available"]:
            return ToolResult(
                success=False,
                error=(
                    "HyperFrames runtime floor not met: "
                    + "; ".join(check["reasons"])
                ),
                data=out,
            )

        # Doctor is explicit. Unlike status, it may launch runtime diagnostics.
        try:
            proc = self._run_hf(["doctor"], cwd=None, timeout=180, check=False)
            out["cli_doctor"] = {
                "exit_code": proc.returncode,
                "stdout_tail": (proc.stdout or "")[-4000:],
                "stderr_tail": (proc.stderr or "")[-4000:],
            }
            ok = proc.returncode == 0
            return ToolResult(
                success=ok,
                data=out,
                error=None if ok else f"hyperframes doctor exit {proc.returncode}",
            )
        except Exception as e:
            out["cli_doctor_error"] = str(e)
            return ToolResult(
                success=False,
                error=f"hyperframes doctor failed: {e}",
                data=out,
            )

    def _scaffold(self, inputs: dict[str, Any]) -> ToolResult:
        """Materialize the HyperFrames workspace from OpenMontage artifacts.

        This does NOT call `hyperframes init` — we want full control over the
        generated files so they map cleanly to edit_decisions. `init` is
        meant for humans bootstrapping a project by hand.
        """
        workspace = self._require_workspace(inputs)
        inputs = VideoCompose._prepare_media_inputs(inputs, canonical_audio_supported=True)
        edit_decisions = inputs.get("edit_decisions") or {}
        if edit_decisions.get("render_runtime") not in (None, "", "hyperframes"):
            raise ValueError("HyperFrames cannot execute a different locked render_runtime")
        asset_manifest = inputs.get("asset_manifest") or {}
        playbook = inputs.get("playbook") or {}
        profile_name = inputs.get("profile")

        if not edit_decisions.get("cuts"):
            return ToolResult(
                success=False,
                error="edit_decisions with non-empty cuts[] is required for scaffold_workspace",
            )

        width, height, fps = self._resolve_dimensions(profile_name, inputs.get("fps", 30))

        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "compositions").mkdir(exist_ok=True)
        assets_dir = workspace / "assets"
        assets_dir.mkdir(exist_ok=True)

        audio = edit_decisions.get("audio", {})
        if not audio.get("music") and edit_decisions.get("music"):
            audio = {**audio, "music": edit_decisions["music"]}
        audio_refs = self._resolve_audio_refs(
            {} if inputs.get("audio_path") else audio,
            asset_manifest.get("assets", []),
            workspace,
        )
        # Validate audio before any cut's FFmpeg speed materialization.
        resolved_cuts, asset_copies = self._resolve_and_stage_assets(
            edit_decisions.get("cuts", []), asset_manifest.get("assets", []),
            workspace, draft=bool(inputs.get("draft")),
        )
        for cut in resolved_cuts:
            source = Path(cut.get("source") or "")
            if source.suffix.lower() in _VIDEO_EXTENSIONS:
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "a",
                     "-show_entries", "stream=codec_type", "-of", "json", str(source)],
                    capture_output=True, text=True, timeout=30, check=True,
                )
                cut["_has_audio"] = bool(json.loads(probe.stdout).get("streams"))

        # Style bridge: playbook → CSS custom properties + DESIGN.md.
        css_vars, design_md = self._style_bridge(playbook, edit_decisions)

        # Write hyperframes.json (registry config).
        (workspace / "hyperframes.json").write_text(
            json.dumps(
                {
                    "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                    "paths": {
                        "blocks": "compositions",
                        "components": "compositions/components",
                        "assets": "assets",
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        # Write DESIGN.md (convenience file for human review + workspace context).
        if design_md:
            (workspace / "DESIGN.md").write_text(design_md, encoding="utf-8")

        # Write index.html — the main composition.
        total_duration = self._compute_total_duration(resolved_cuts)
        html = self._generate_index_html(
            cuts=resolved_cuts,
            audio_refs=audio_refs,
            width=width,
            height=height,
            total_duration=total_duration,
            css_vars=css_vars,
            title=edit_decisions.get("metadata", {}).get("title")
            or f"OpenMontage {edit_decisions.get('renderer_family', 'composition')}",
        )
        (workspace / "index.html").write_text(html, encoding="utf-8")

        return ToolResult(
            success=True,
            data={
                "operation": "scaffold_workspace",
                "workspace": str(workspace),
                "width": width,
                "height": height,
                "fps": fps,
                "total_duration_seconds": total_duration,
                "cut_count": len(resolved_cuts),
                "asset_copies": asset_copies,
                "deliverable_accepted": False,
                "draft": bool(inputs.get("draft")),
                "missing_references": [c["_missing_reference"] for c in resolved_cuts if c.get("_missing_reference")],
            },
            artifacts=[str(workspace / "index.html")],
        )

    def _lint(self, inputs: dict[str, Any]) -> ToolResult:
        workspace = self._require_workspace(inputs)
        if not (workspace / "index.html").exists():
            return ToolResult(
                success=False,
                error=f"No index.html in {workspace}. Run scaffold_workspace first.",
            )
        proc = self._run_hf(["lint", "--json"], cwd=workspace, timeout=120, check=False)
        data: dict[str, Any] = {"exit_code": proc.returncode}
        payload = self._parse_json_output(proc.stdout)
        if payload is not None:
            data["report"] = payload
        else:
            data["stdout_tail"] = (proc.stdout or "")[-4000:]
        data["stderr_tail"] = (proc.stderr or "")[-2000:]
        ok = proc.returncode == 0
        return ToolResult(
            success=ok,
            data=data,
            error=None if ok else f"hyperframes lint exit {proc.returncode}",
        )

    def _validate(self, inputs: dict[str, Any]) -> ToolResult:
        workspace = self._require_workspace(inputs)
        if not (workspace / "index.html").exists():
            return ToolResult(
                success=False,
                error=f"No index.html in {workspace}. Run scaffold_workspace first.",
            )
        args = ["validate", "--json"]
        if inputs.get("skip_contrast"):
            args.append("--no-contrast")
        proc = self._run_hf(args, cwd=workspace, timeout=300, check=False)
        data: dict[str, Any] = {"exit_code": proc.returncode}
        payload = self._parse_json_output(proc.stdout)
        if payload is not None:
            data["report"] = payload
        else:
            data["stdout_tail"] = (proc.stdout or "")[-4000:]
        data["stderr_tail"] = (proc.stderr or "")[-2000:]
        ok = proc.returncode == 0
        return ToolResult(
            success=ok,
            data=data,
            error=None if ok else f"hyperframes validate exit {proc.returncode}",
        )

    def _inspect(self, inputs: dict[str, Any]) -> ToolResult:
        """Seek through an authored workspace and audit runtime/layout issues."""
        workspace = self._require_workspace(inputs)
        if not (workspace / "index.html").exists():
            return ToolResult(
                success=False,
                error=f"No index.html in {workspace}.",
            )
        proc = self._run_hf(["inspect", "--json"], cwd=workspace, timeout=300, check=False)
        data: dict[str, Any] = {"exit_code": proc.returncode}
        payload = self._parse_json_output(proc.stdout)
        if payload is not None:
            data["report"] = payload
        else:
            data["stdout_tail"] = (proc.stdout or "")[-4000:]
        data["stderr_tail"] = (proc.stderr or "")[-2000:]
        ok = proc.returncode == 0
        return ToolResult(
            success=ok,
            data=data,
            error=None if ok else f"hyperframes inspect exit {proc.returncode}",
        )

    def _check(self, inputs: dict[str, Any]) -> ToolResult:
        """Run the unified HyperFrames quality gate for authored workspaces."""
        workspace = self._require_workspace(inputs)
        if not (workspace / "index.html").exists():
            return ToolResult(success=False, error=f"No index.html in {workspace}.")
        args = ["check", "--json"]
        if inputs.get("skip_contrast", False):
            args.append("--no-contrast")
        if inputs.get("strict_check", False):
            args.append("--strict")
        if inputs.get("snapshots", False):
            args.append("--snapshots")
        proc = self._run_hf(args, cwd=workspace, timeout=300, check=False)
        data: dict[str, Any] = {"exit_code": proc.returncode}
        payload = self._parse_json_output(proc.stdout)
        if payload is not None:
            data["report"] = payload
        else:
            data["stdout_tail"] = (proc.stdout or "")[-4000:]
        data["stderr_tail"] = (proc.stderr or "")[-2000:]
        ok = proc.returncode == 0
        return ToolResult(
            success=ok,
            data=data,
            error=None if ok else f"hyperframes check exit {proc.returncode}",
        )

    def _add_block(self, inputs: dict[str, Any]) -> ToolResult:
        """Install a registry block or component via `hyperframes add`.

        Blocks are standalone sub-compositions (own dimensions, duration, timeline)
        that land at `compositions/<name>.html`. Components are effect snippets
        that land at `compositions/components/<name>.html`. After install, the
        caller is responsible for wiring the block into `index.html` via
        `data-composition-src` or pasting the component's snippet — see
        `.agents/skills/hyperframes-registry/SKILL.md`.
        """
        workspace = self._require_workspace(inputs)
        block = (inputs.get("block_name") or "").strip()
        if not block:
            return ToolResult(
                success=False,
                error="block_name is required for operation='add_block'",
            )
        if not workspace.exists():
            return ToolResult(
                success=False,
                error=(
                    f"Workspace {workspace} does not exist. Run "
                    "operation='scaffold_workspace' first."
                ),
            )
        args = ["add", block, "--json", "--no-clipboard"]
        proc = self._run_hf(args, cwd=workspace, timeout=300, check=False)
        data: dict[str, Any] = {
            "operation": "add_block",
            "block_name": block,
            "workspace": str(workspace),
            "exit_code": proc.returncode,
        }
        payload = self._parse_json_output(proc.stdout)
        if payload is not None:
            data["report"] = payload
        else:
            data["stdout_tail"] = (proc.stdout or "")[-4000:]
        data["stderr_tail"] = (proc.stderr or "")[-2000:]
        ok = proc.returncode == 0
        return ToolResult(
            success=ok,
            data=data,
            error=None if ok else f"hyperframes add {block} exit {proc.returncode}",
        )

    @_atomic_render(lambda inputs: str(Path(inputs.get("workspace_path", ".")) / "renders" / "final.mp4"))
    def _render(self, inputs: dict[str, Any]) -> ToolResult:
        """Full pipeline: scaffold → lint → validate → render."""
        runtime_ok = self._runtime_check()
        if not runtime_ok["runtime_available"]:
            return ToolResult(
                success=False,
                error=(
                    "HyperFrames runtime not available: "
                    + "; ".join(runtime_ok["reasons"])
                    + ". Per governance, this is a blocker — do NOT silently "
                    "fall back to another runtime without user approval."
                ),
                data={"runtime_check": runtime_ok},
            )

        inputs = VideoCompose._prepare_media_inputs(inputs, canonical_audio_supported=True)
        VideoCompose._require_subtitle_renderer(inputs)
        workspace_root = self._require_workspace(inputs)
        workspace_root.mkdir(parents=True, exist_ok=True)
        # Never scaffold two invocations over one another's HTML/assets.
        workspace = Path(tempfile.mkdtemp(prefix="render-", dir=workspace_root))
        inputs = {**inputs, "workspace_path": str(workspace)}
        output_path = Path(
            inputs.get("output_path") or (workspace / "renders" / "final.mp4")
        ).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        steps: dict[str, Any] = {}

        # 1. Scaffold — generate HTML/CSS/assets.
        scaffold = self._scaffold(inputs)
        steps["scaffold"] = scaffold.data
        if not scaffold.success:
            return ToolResult(
                success=False,
                error=f"Scaffold failed: {scaffold.error}",
                data={"steps": steps},
            )
        self._validate_workspace_references(workspace)

        # 2. Lint — static contract checks.
        lint = self._lint({"workspace_path": str(workspace)})
        steps["lint"] = lint.data
        if not lint.success:
            if inputs.get("strict", False):
                return ToolResult(
                    success=False,
                    error=f"Lint failed (strict mode): {lint.error}",
                    data={"steps": steps},
                )
            log.warning("hyperframes lint reported issues (non-strict mode, continuing)")

        # 3. Validate — browser-based contract + contrast.
        validate = self._validate(
            {
                "workspace_path": str(workspace),
                "skip_contrast": inputs.get("skip_contrast", False),
            }
        )
        steps["validate"] = validate.data
        if not validate.success:
            return ToolResult(
                success=False,
                error=(
                    f"Validate failed: {validate.error}. HyperFrames render "
                    f"is blocked — fix the composition and re-run."
                ),
                data={"steps": steps},
            )

        # 4. Render.
        width, height, fps = self._resolve_dimensions(
            inputs.get("profile"), inputs.get("fps", 30)
        )
        quality = inputs.get("quality", "standard")
        args = [
            "render",
            "--output", str(output_path),
            "--fps", str(fps),
            "--quality", quality,
        ]
        proc = self._run_hf(args, cwd=workspace, timeout=1800, check=False)
        steps["render"] = {
            "exit_code": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
        }
        if proc.returncode != 0:
            return ToolResult(
                success=False,
                error=f"hyperframes render exit {proc.returncode}",
                data={"steps": steps},
            )

        if not output_path.exists():
            return ToolResult(
                success=False,
                error=(
                    f"hyperframes render exited 0 but output file missing: "
                    f"{output_path}. Check stdout_tail for the real path."
                ),
                data={"steps": steps},
            )

        applied = VideoCompose()._apply_external_media(output_path, inputs)
        return ToolResult(
            success=True,
            data={
                "operation": "render",
                "output": str(output_path),
                "workspace": str(workspace),
                "width": width,
                "height": height,
                "fps": fps,
                "quality": quality,
                "steps": steps,
                "executed_runtime": "hyperframes",
                "deliverable_accepted": False,
                "draft": bool(inputs.get("draft")),
                **applied,
            },
            artifacts=[str(output_path)],
        )

    @_atomic_render(lambda inputs: str(Path(inputs.get("workspace_path", ".")) / "renders" / "final.mp4"))
    def _render_existing(self, inputs: dict[str, Any]) -> ToolResult:
        """Validate and render a hand-authored workspace without scaffolding it.

        Atelier compositions own their HTML, CSS, JavaScript, and local assets.
        Re-running `_scaffold` would destroy that authored work, so this path
        performs the mandatory gates against the files already on disk.
        """
        # Canonical audio cannot be inserted into arbitrary authored HTML.
        # Require the approved mix rather than silently ignoring these refs.
        inputs = VideoCompose._prepare_media_inputs(inputs)
        VideoCompose._require_subtitle_renderer(inputs)
        runtime_ok = self._runtime_check()
        if not runtime_ok["runtime_available"]:
            return ToolResult(
                success=False,
                error=(
                    "HyperFrames runtime not available: "
                    + "; ".join(runtime_ok["reasons"])
                    + ". Per governance, do not swap runtimes silently."
                ),
                data={"runtime_check": runtime_ok},
            )

        workspace = self._require_workspace(inputs)
        entry = workspace / "index.html"
        if not entry.is_file():
            return ToolResult(
                success=False,
                error=f"No authored index.html in {workspace}.",
            )
        original_digest = self._file_digest(entry)
        output_path = Path(
            inputs.get("output_path") or (workspace / "renders" / "final.mp4")
        ).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        steps: dict[str, Any] = {}
        self._validate_workspace_references(workspace)
        authored_workspace = workspace
        # The CLI's checks/cache/snapshots must not race over an authored tree.
        workspace = output_path.parent / "authored-workspace"
        shutil.copytree(
            authored_workspace, workspace,
            ignore=shutil.ignore_patterns(".render-*", ".git"),
        )
        self._validate_workspace_references(workspace)

        quality_check = self._check(
            {
                "workspace_path": str(workspace),
                "skip_contrast": inputs.get("skip_contrast", False),
                "strict_check": inputs.get("strict_check", False),
                "snapshots": inputs.get("snapshots", False),
            }
        )
        steps["check"] = quality_check.data
        if not quality_check.success:
            return ToolResult(
                success=False,
                error=f"Quality check failed for authored workspace: {quality_check.error}",
                data={"steps": steps},
            )

        _, _, fps = self._resolve_dimensions(
            inputs.get("profile"), inputs.get("fps", 30)
        )
        quality = inputs.get("quality", "standard")
        args = [
            "render",
            "--output", str(output_path),
            "--fps", str(fps),
            "--quality", quality,
            "--strict",
        ]
        proc = self._run_hf(args, cwd=workspace, timeout=1800, check=False)
        steps["render"] = {
            "exit_code": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
        }
        if proc.returncode != 0:
            return ToolResult(
                success=False,
                error=f"hyperframes render exit {proc.returncode}",
                data={"steps": steps},
            )
        if not output_path.is_file():
            return ToolResult(
                success=False,
                error=f"HyperFrames exited 0 but output is missing: {output_path}",
                data={"steps": steps},
            )
        if self._file_digest(entry) != original_digest or self._file_digest(workspace / "index.html") != original_digest:
            return ToolResult(
                success=False,
                error="Authored index.html changed during render_existing.",
                data={"steps": steps},
            )

        applied = VideoCompose()._apply_external_media(output_path, inputs)
        return ToolResult(
            success=True,
            data={
                "operation": "render_existing",
                "output": str(output_path),
                "workspace": str(authored_workspace),
                "fps": fps,
                "quality": quality,
                "authored_entry_preserved": True,
                "steps": steps,
                "executed_runtime": "hyperframes",
                "deliverable_accepted": False,
                **applied,
            },
            artifacts=[str(output_path)],
        )

    @staticmethod
    def _file_digest(path: Path) -> str:
        from lib.delivery_validation import content_sha256
        return content_sha256(path)

    # ------------------------------------------------------------------
    # Workspace generation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_workspace_references(workspace: Path) -> None:
        """Check the static HTML/CSS media graph locally before browser execution.

        Computed JavaScript references remain the runtime check's responsibility.
        This does not fetch remote resources or certify authored code as trusted.
        """
        class References(HTMLParser):
            def __init__(self):
                super().__init__()
                self.refs: list[str] = []

            def handle_starttag(self, tag, attrs):
                for key, value in attrs:
                    if value and (key in {"src", "poster", "data-composition-src"}
                                  or (tag == "link" and key == "href")):
                        self.refs.append(value)

        pending = [workspace / "index.html"]
        seen: set[Path] = set()
        while pending:
            document = pending.pop().resolve()
            if document in seen:
                continue
            seen.add(document)
            text = document.read_text(encoding="utf-8")
            refs: list[str] = []
            if document.suffix.lower() in {".html", ".htm"}:
                parser = References()
                parser.feed(text)
                refs.extend(parser.refs)
            refs.extend(re.findall(r"url\(\s*['\"]?([^'\"\s)]+)", text))
            for reference in refs:
                parsed = urlsplit(reference)
                if parsed.scheme in {"http", "https", "data", "blob"} or parsed.netloc or not parsed.path:
                    continue
                path = (workspace / unquote(parsed.path).lstrip("/") if parsed.path.startswith("/")
                        else document.parent / unquote(parsed.path)).resolve()
                if not HyperFramesCompose._is_inside(path, workspace) or not path.is_file():
                    raise ValueError(f"Required authored reference not found inside workspace: {reference}")
                if path.suffix.lower() in {".html", ".htm", ".css"}:
                    pending.append(path)

    @staticmethod
    def _require_workspace(inputs: dict[str, Any]) -> Path:
        raw = inputs.get("workspace_path")
        if not raw:
            raise ValueError("workspace_path is required for this operation")
        return Path(raw).resolve()

    @staticmethod
    def _resolve_dimensions(
        profile_name: Optional[str], fps_in: int
    ) -> tuple[int, int, int]:
        """Resolve output dimensions from the media profile, with a safe default."""
        if profile_name:
            try:
                from lib.media_profiles import get_profile  # type: ignore
                p = get_profile(profile_name)
                return int(p.width), int(p.height), int(p.fps)
            except Exception:
                pass
        return 1920, 1080, int(fps_in)

    @staticmethod
    def _compute_total_duration(cuts: list[dict]) -> float:
        return timeline_duration(cuts)

    def _stage_asset(self, source: Path, workspace: Path) -> Path:
        if not source.is_file():
            raise ValueError(f"Required media not found: {source}")
        if self._is_inside(source, workspace):
            return source.resolve()
        digest = self._file_digest(source)
        dest = workspace / "assets" / f"{digest}{source.suffix.lower()}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or self._file_digest(dest) != digest:
            shutil.copy2(source, dest)
        return dest

    def _resolve_and_stage_assets(
        self,
        cuts: list[dict],
        assets: list[dict],
        workspace: Path,
        *,
        draft: bool = False,
    ) -> tuple[list[dict], list[dict[str, str]]]:
        """Resolve asset IDs in cuts[].source, copy files into workspace/assets/.

        HyperFrames resolves `src=` relative to the composition HTML file, so
        every asset must live inside the workspace tree. Copying is simpler
        (and portable) than symlinking, at the cost of disk space — these
        are regenerable under `projects/`.
        """
        asset_lookup = {a["id"]: a for a in assets if "id" in a}
        assets_dir = workspace / "assets"
        copies: list[dict[str, str]] = []
        resolved: list[dict] = []
        cuts = normalize_cuts(cuts)
        require_sequential(cuts)
        for cut in cuts:
            source = cut.get("source", "")
            source = asset_lookup.get(source, {}).get("path", source)
            if source and not Path(source).is_file() and not draft:
                raise ValueError(f"Required cut source not found: {source}")
        for cut in cuts:
            source = cut.get("source", "")
            resolved_cut = dict(cut)
            if source in asset_lookup:
                resolved_cut["source"] = asset_lookup[source].get("path", source)
            src_path = Path(resolved_cut["source"]) if resolved_cut.get("source") else None
            if src_path and src_path.is_file():
                dest = self._stage_asset(src_path, workspace)
                resolved_cut["source"] = str(dest)
                copies.append({"from": str(src_path), "to": str(dest)})
                if dest.suffix.lower() in _VIDEO_EXTENSIONS and cut["speed"] != 1:
                    # HF 0.8.40 has no playback-rate contract. Materialize the
                    # approved trim/speed locally rather than invent an ignored
                    # data attribute or silently play at normal speed.
                    retimed = assets_dir / f"retimed-{secrets.token_hex(8)}.mp4"
                    speed = cut["speed"]
                    self.run_command([
                        "ffmpeg", "-y", "-ss", str(cut["in_seconds"]),
                        "-t", str(cut["out_seconds"] - cut["in_seconds"]),
                        "-i", str(dest), "-map", "0:v:0", "-map", "0:a?",
                        "-vf", f"setpts=(PTS-STARTPTS)/{speed},fps=30",
                        "-af", VideoCompose._build_atempo(speed),
                        "-c:v", "libx264", "-c:a", "aac",
                        "-t", str(cut["timeline_duration_seconds"]), str(retimed),
                    ])
                    _validate_rendered_video(retimed)
                    resolved_cut["source"] = str(retimed)
                    resolved_cut["_media_start_seconds"] = 0
            elif source:
                resolved_cut["_missing_reference"] = str(source)
                resolved_cut["_draft_placeholder"] = True
                resolved_cut["source"] = ""
            elif draft:
                resolved_cut["_draft_placeholder"] = True
            resolved.append(resolved_cut)
        return resolved, copies

    def _resolve_audio_refs(
        self,
        audio: dict[str, Any],
        assets: list[dict],
        workspace: Path,
    ) -> dict[str, Any]:
        """Resolve narration / music asset IDs and stage them."""
        asset_lookup = {a["id"]: a for a in assets if "id" in a}
        out: dict[str, Any] = {"narration": [], "music": None}
        if audio.get("sfx"):
            raise ValueError("HyperFrames SFX require an approved mixed audio_path")

        for seg in audio.get("narration", {}).get("segments", []) or []:
            aid = seg.get("asset_id")
            if not aid:
                raise ValueError("Narration segment requires asset_id")
            src = Path(asset_lookup.get(aid, {}).get("path") or aid)
            dest = self._stage_asset(src, workspace)
            out["narration"].append(
                {
                    "src": str(dest),
                    "start_seconds": float(seg.get("start_seconds", 0) or 0),
                    "end_seconds": float(seg.get("end_seconds", 0) or 0) or None,
                }
            )

        music = audio.get("music", {})
        m_id = music.get("asset_id")
        if m_id:
            if music.get("ducking") or music.get("fade_in_seconds") or music.get("fade_out_seconds"):
                raise ValueError("HyperFrames music fades/ducking require an approved mixed audio_path")
            src = Path(asset_lookup.get(m_id, {}).get("path") or m_id)
            dest = self._stage_asset(src, workspace)
            out["music"] = {
                "src": str(dest),
                "volume": float(0.15 if music.get("volume") is None else music["volume"]),
            }

        return out

    @staticmethod
    def _is_inside(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def _style_bridge(
        self,
        playbook: dict[str, Any],
        edit_decisions: dict[str, Any],
    ) -> tuple[dict[str, str], str]:
        """Bridge OpenMontage playbook → HyperFrames CSS vars + DESIGN.md.

        Delegates to `lib/hyperframes_style_bridge.py` so the logic is
        shareable and testable. Falls back to a safe built-in default when
        the bridge module isn't available.
        """
        try:
            from lib.hyperframes_style_bridge import style_bridge  # type: ignore
            return style_bridge(playbook, edit_decisions)
        except Exception as e:
            log.debug("style_bridge fallback: %s", e)

        vl = (playbook or {}).get("visual_language", {})
        palette = vl.get("color_palette", {})
        typo = (playbook or {}).get("typography", {})

        def _first(raw: Any, default: str) -> str:
            if isinstance(raw, list) and raw:
                return str(raw[0])
            if isinstance(raw, str) and raw:
                return raw
            return default

        bg = _first(palette.get("background"), "#0B0F1A")
        fg = _first(palette.get("text"), "#F5F5F5")
        accent = _first(palette.get("accent"), "#F59E0B")
        primary = _first(palette.get("primary"), "#2563EB")
        heading = typo.get("heading", {}).get("font") or typo.get("heading", {}).get("family") or "Inter"
        body = typo.get("body", {}).get("font") or typo.get("body", {}).get("family") or "Inter"

        css_vars = {
            "--color-bg": bg,
            "--color-fg": fg,
            "--color-accent": accent,
            "--color-primary": primary,
            "--font-heading": heading,
            "--font-body": body,
            "--ease-primary": "cubic-bezier(0.65, 0, 0.35, 1)",
            "--duration-entrance": "0.6s",
        }
        design_md = (
            "# DESIGN\n\n"
            "Generated by OpenMontage HyperFrames style bridge (fallback).\n\n"
            f"- Background: `{bg}`\n"
            f"- Foreground: `{fg}`\n"
            f"- Accent: `{accent}`\n"
            f"- Primary: `{primary}`\n"
            f"- Heading font: `{heading}`\n"
            f"- Body font: `{body}`\n"
        )
        return css_vars, design_md

    # ------------------------------------------------------------------
    # HTML generation (minimal, Phase 1)
    # ------------------------------------------------------------------

    def _generate_index_html(
        self,
        cuts: list[dict],
        audio_refs: dict[str, Any],
        width: int,
        height: int,
        total_duration: float,
        css_vars: dict[str, str],
        title: str,
    ) -> str:
        """Emit a HyperFrames-contract-compliant index.html.

        Phase 1 covers the minimum required for smoke-testing the runtime:
        - still images (img.clip)
        - video clips (video.clip, muted playsinline + separate audio if needed)
        - text cards (div.clip with styled <h1>)
        - narration segments (audio)
        - music bed (audio, lower volume)

        Richer scene types (registry blocks, kinetic typography) are authored
        by the agent directly into compositions/ — this generator just
        provides a functional starting skeleton.
        """
        vars_css = "\n      ".join(f"{k}: {v};" for k, v in css_vars.items())

        clip_html: list[str] = []
        entrance_tweens: list[str] = []
        for i, cut in enumerate(cuts):
            html, tween = self._cut_to_html(i, cut, width, height)
            clip_html.append(html)
            if tween:
                entrance_tweens.append(tween)

        audio_html: list[str] = []
        for j, nar in enumerate(audio_refs.get("narration") or []):
            src = self._rel_from_workspace(nar["src"])
            start = nar.get("start_seconds", 0)
            end = nar.get("end_seconds")
            duration = (end - start) if end and end > start else (total_duration - start)
            audio_html.append(
                f'<audio id="nar-{j}" '
                f'data-start="{self._f(start)}" data-duration="{self._f(duration)}" '
                f'data-track-index="2" src="{self._escape_attr(src)}" '
                f'data-volume="1"></audio>'
            )

        music = audio_refs.get("music")
        if music:
            src = self._rel_from_workspace(music["src"])
            audio_html.append(
                f'<audio id="music" '
                f'data-start="0" data-duration="{self._f(total_duration)}" '
                f'data-track-index="3" src="{self._escape_attr(src)}" '
                f'data-volume="{self._f(music["volume"])}"></audio>'
            )

        tween_block = "\n        ".join(entrance_tweens) if entrance_tweens else "// no tweens"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{self._escape_text(title)}</title>
  <style>
    :root {{
      {vars_css}
    }}
    body {{ margin: 0; background: var(--color-bg); color: var(--color-fg); font-family: var(--font-body); }}
    [data-composition-id="root"] {{
      position: relative;
      width: {width}px;
      height: {height}px;
      overflow: hidden;
    }}
    .clip {{ position: absolute; inset: 0; }}
    .clip.video-clip, .clip.image-clip {{ object-fit: cover; width: 100%; height: 100%; }}
    .clip.text-card {{ display: flex; align-items: center; justify-content: center; padding: 120px 160px; box-sizing: border-box; text-align: center; }}
    .clip.text-card h1 {{ font-family: var(--font-heading); font-weight: 700; font-size: 96px; line-height: 1.1; margin: 0; color: var(--color-fg); }}
    .clip.text-card .subtitle {{ font-size: 36px; margin-top: 24px; color: var(--color-accent); }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
</head>
<body>
  <div data-composition-id="root" data-start="0" data-duration="{self._f(total_duration)}" data-width="{width}" data-height="{height}">
    {"".join(clip_html)}
    {"".join(audio_html)}
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      {tween_block}
      window.__timelines["root"] = tl;
    </script>
  </div>
</body>
</html>
"""

    def _cut_to_html(
        self, index: int, cut: dict, width: int, height: int
    ) -> tuple[str, Optional[str]]:
        """Render one cut + its entrance tween. Returns (html, tween or None)."""
        cut_id = f"cut-{index}"
        cut = normalize_cuts([cut])[0]
        in_s = cut["timeline_start_seconds"]
        duration = cut["timeline_duration_seconds"]

        source = cut.get("source") or ""
        cut_type = (cut.get("type") or "").lower()
        text = cut.get("text") or cut.get("title") or ""

        src_path = Path(source) if source else None
        ext = src_path.suffix.lower() if src_path else ""

        # Decide scene shape
        if cut_type in {"text_card", "hero_title", "callout"} or (not source and text):
            inner = f'<h1>{self._escape_text(text or f"Scene {index + 1}")}</h1>'
            subtitle = cut.get("subtitle") or cut.get("caption")
            if subtitle:
                inner += f'<div class="subtitle">{self._escape_text(subtitle)}</div>'
            html = (
                f'<div id="{cut_id}" class="clip text-card" '
                f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
                f'data-track-index="1">{inner}</div>'
            )
            # Mild entrance — fade + lift.
            tween = (
                f'tl.from("#{cut_id} h1", {{ y: 40, opacity: 0, duration: 0.6, '
                f'ease: "power3.out" }}, {self._f(in_s + 0.1)});'
            )
            return html, tween

        if ext in _IMAGE_EXTENSIONS and src_path:
            rel = self._rel_from_workspace(str(src_path))
            html = (
                f'<img id="{cut_id}" class="clip image-clip" '
                f'src="{self._escape_attr(rel)}" '
                f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
                f'data-track-index="1" alt="">'
            )
            tween = (
                f'tl.from("#{cut_id}", {{ scale: 1.05, opacity: 0, duration: 0.5, '
                f'ease: "power2.out" }}, {self._f(in_s)});'
            )
            return html, tween

        if ext in _VIDEO_EXTENSIONS and src_path:
            rel = self._rel_from_workspace(str(src_path))
            html = (
                f'<video id="{cut_id}" class="clip video-clip" '
                f'src="{self._escape_attr(rel)}" '
                f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
                f'data-media-start="{self._f(cut.get("_media_start_seconds", cut["in_seconds"]))}" '
                f'data-track-index="1" muted playsinline></video>'
            )
            if cut.get("_has_audio"):
                html += (
                    f'<audio id="{cut_id}-audio" src="{self._escape_attr(rel)}" '
                    f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
                    f'data-media-start="{self._f(cut.get("_media_start_seconds", cut["in_seconds"]))}" '
                    f'data-track-index="4" data-volume="1"></audio>'
                )
            return html, None

        # Unknown cut shape — render a placeholder text card so the render
        # still succeeds; lint/validate will surface the issue.
        if ext in {".html", ".htm"} and src_path:
            rel = self._rel_from_workspace(str(src_path))
            composition_id = Path(rel).stem
            html = (
                f'<div id="{cut_id}" class="clip composition-clip" '
                f'data-composition-id="{self._escape_attr(composition_id)}" '
                f'data-composition-src="{self._escape_attr(rel)}" '
                f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
                f'data-width="{width}" data-height="{height}" '
                f'data-track-index="1"></div>'
            )
            return html, None

        if not cut.get("_draft_placeholder"):
            raise ValueError(f"Unsupported or missing required HyperFrames cut: {source or cut.get('id')}")
        placeholder = self._escape_text(text or cut.get("reason") or f"DRAFT: Scene {index + 1}")
        html = (
            f'<div id="{cut_id}" class="clip text-card" '
            f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
            f'data-track-index="1"><h1>{placeholder}</h1></div>'
        )
        return html, None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _run_hf(
        self,
        args: list[str],
        *,
        cwd: Optional[Path],
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess:
        """Invoke the pinned installed CLI entry without a package manager.

        We intentionally bypass `self.run_command` here because we do NOT
        want to raise CalledProcessError on non-zero exits — the caller
        parses lint/validate/render exit codes itself.
        """
        installed = self._resolve_npm_package()
        if "error" in installed:
            return subprocess.CompletedProcess(
                args=args, returncode=127, stdout="", stderr=installed["error"],
            )
        cmd = [shutil.which("node") or "node", installed["entry"], *args]
        # Resolve the Node executable on Windows without shell=True.
        if os.name == "nt":
            resolved = shutil.which(cmd[0])
            if resolved:
                cmd[0] = resolved
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd) if cwd else None,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            # Surface timeouts as a failed CompletedProcess so callers get a
            # uniform shape. The stderr tail will say timeout.
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=124,
                stdout=self._as_text(e.stdout),
                stderr=self._as_text(e.stderr) + f"\n[timeout after {timeout}s]",
            )

    @staticmethod
    def _as_text(value: str | bytes | None) -> str:
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""

    @staticmethod
    def _parse_json_output(stdout: str) -> Optional[Any]:
        """Parse a `--json` report, tolerating surrounding banner lines."""
        if not stdout:
            return None
        start = stdout.find("{")
        end = stdout.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(stdout[start : end + 1])
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _f(v: float) -> str:
        return f"{float(v):.3f}".rstrip("0").rstrip(".")

    @staticmethod
    def _escape_text(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @staticmethod
    def _escape_attr(s: str) -> str:
        return HyperFramesCompose._escape_text(s).replace('"', "&quot;")

    @staticmethod
    def _rel_from_workspace(path: str) -> str:
        """HyperFrames resolves src= relative to index.html. Our asset files
        live under workspace/assets/, so when we stage a copy we know the
        relative path is `assets/<name>`. For files already in the workspace
        tree, fall back to the file name.
        """
        p = Path(path)
        # If it's already a relative path starting with assets/, keep as-is.
        if not p.is_absolute():
            return str(p).replace("\\", "/")
        parts = p.parts
        for anchor in ("assets", "compositions"):
            if anchor in parts:
                index = len(parts) - 1 - list(reversed(parts)).index(anchor)
                return "/".join(parts[index:])
        # Otherwise emit just the basename under assets/.
        return f"assets/{p.name}"
