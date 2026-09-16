"""Cost tracker core: estimate, reserve, reconcile, and persist to cost_log.json.

Implements the budget governance rules from the spec:
- Every paid operation produces a preflight estimate
- The orchestrator reserves estimated budget before execution
- Budget overruns trigger pauses (in warn/cap mode)
- Actual spend is reconciled when the tool finishes or fails
"""

from __future__ import annotations

import json
import copy
import math
import threading
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Optional

from jsonschema import Draft202012Validator, FormatChecker

from lib.budget_transaction import atomic_write_json, ledger_lock
from lib.config_model import BudgetConfig, BudgetMode


class EntryStatus(str, Enum):
    ESTIMATED = "estimated"
    RESERVED = "reserved"
    EXECUTING = "executing"
    UNKNOWN = "unknown"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class BudgetExceededError(Exception):
    """Raised when an operation would exceed the budget in cap mode."""
    pass


class ApprovalRequiredError(Exception):
    """Raised when an operation needs user approval before proceeding."""
    pass


class CostTracker:
    """Tracks estimated, reserved, and actual costs for a pipeline project."""

    def __init__(
        self,
        budget_total_usd: float = 10.0,
        reserve_pct: float = 0.10,
        single_action_approval_usd: float = 0.50,
        require_approval_for_new_paid_tool: bool = True,
        mode: BudgetMode = BudgetMode.CAP,
        cost_log_path: Optional[Path] = None,
        project: Optional[dict[str, str]] = None,
    ) -> None:
        self._policy = BudgetConfig(
            total_usd=budget_total_usd, reserve_pct=reserve_pct,
            single_action_approval_usd=single_action_approval_usd,
            require_approval_for_new_paid_tool=require_approval_for_new_paid_tool, mode=mode,
        )
        if cost_log_path is not None and Path(cost_log_path).is_symlink():
            raise ValueError("Cost ledger cannot be a symlink")
        self.cost_log_path = Path(cost_log_path).resolve() if cost_log_path is not None else None
        self._entries: list[dict[str, Any]] = []
        self._approved_tools: set[str] = set()
        self._project = copy.deepcopy(project)
        self._thread_lock = threading.RLock()
        self._has_loaded = False
        # Initialization itself participates in the same lock as all mutations.
        # Persist even an empty policy: later constructors may not replace it.
        with self._transaction():
            pass

    # ---- Budget calculations ----

    @property
    def budget_total_usd(self) -> float:
        return self._policy.total_usd

    @property
    def reserve_pct(self) -> float:
        return self._policy.reserve_pct

    @property
    def single_action_approval_usd(self) -> float:
        return self._policy.single_action_approval_usd

    @property
    def require_approval_for_new_paid_tool(self) -> bool:
        return self._policy.require_approval_for_new_paid_tool

    @property
    def mode(self) -> BudgetMode:
        return self._policy.mode

    @property
    def entries(self) -> list[dict[str, Any]]:
        with self._transaction(write=False):
            return copy.deepcopy(self._entries)

    def _reserved(self) -> float:
        return float(self._sum(e["reserved_usd"] for e in self._entries))

    def _spent(self) -> float:
        return float(self._sum(e["actual_usd"] for e in self._entries))

    @staticmethod
    def _sum(values) -> Decimal:
        # Preserve the decimal USD inputs without rounding away tiny charges or
        # rejecting an exact .10 + .20 reservation against a .30 cap.
        with localcontext() as context:
            context.prec = 400
            return sum((Decimal(str(value)) for value in values), Decimal(0))

    def _available(self, *, holdback: bool = True) -> Decimal:
        with localcontext() as context:
            context.prec = 400
            capacity = Decimal(str(self.budget_total_usd))
            if holdback:
                capacity *= 1 - Decimal(str(self.reserve_pct))
            return capacity - self._sum(e["actual_usd"] for e in self._entries) - self._sum(
                e["reserved_usd"] for e in self._entries
            )

    def _usable(self) -> float:
        return float(max(Decimal(0), self._available()))

    @property
    def budget_reserved_usd(self) -> float:
        with self._transaction(write=False):
            return self._reserved()

    @property
    def budget_spent_usd(self) -> float:
        with self._transaction(write=False):
            return self._spent()

    @property
    def budget_remaining_usd(self) -> float:
        with self._transaction(write=False):
            return float(self._available(holdback=False))

    @property
    def usable_budget_usd(self) -> float:
        """Budget minus the reserve holdback."""
        with self._transaction(write=False):
            return self._usable()

    def cost_snapshot(self) -> dict[str, float]:
        with self._transaction(write=False):
            return {
                "total_spent_usd": self._spent(),
                "total_reserved_usd": self._reserved(),
                "budget_remaining_usd": float(self._available(holdback=False)),
            }

    # ---- Core operations ----

    def estimate(
        self, tool: str, operation: str, estimated_usd: float, *,
        request_hash: Optional[str] = None,
    ) -> str:
        """Record an estimate, optionally bound to a resolved request hash."""
        estimated_usd = self.money(estimated_usd)
        if not isinstance(tool, str) or not tool.strip() or not isinstance(operation, str) or not operation.strip():
            raise ValueError("tool and operation must be nonempty strings")
        entry_id = self._new_id()
        entry = {
            "id": entry_id,
            "tool": tool,
            "operation": operation,
            "status": EntryStatus.ESTIMATED.value,
            "estimated_usd": estimated_usd,
            "reserved_usd": 0.0,
            "actual_usd": 0.0,
            "timestamp": self._now(),
        }
        if request_hash is not None:
            entry["request_hash"] = request_hash
        with self._transaction():
            self._entries.append(entry)
        return entry_id

    def reserve(self, entry_id: str) -> None:
        """Reserve budget for an estimated entry.

        Raises BudgetExceededError in cap mode, or ApprovalRequiredError
        when the action exceeds the single-action approval threshold.
        """
        with self._transaction():
            entry = self._find(entry_id)
            if entry["status"] == EntryStatus.RESERVED.value:
                return
            self._require_status(entry, EntryStatus.ESTIMATED)
            self._reserve(entry)

    def _reserve(self, entry: dict, *, paid_execution: bool = False) -> None:
        estimated = entry["estimated_usd"]
        approved = entry.get("approval", {}).get("amount_usd") == estimated

        # Check single-action approval threshold
        if estimated > self.single_action_approval_usd and not approved:
            if self.mode != BudgetMode.OBSERVE:
                raise ApprovalRequiredError(
                    f"Action costs ${estimated:.2f}, exceeds "
                    f"single-action threshold ${self.single_action_approval_usd:.2f}"
                )

        # Check new paid tool approval
        if self.require_approval_for_new_paid_tool and estimated > 0 and not approved:
            if entry["tool"] not in self._approved_tools:
                if self.mode != BudgetMode.OBSERVE:
                    raise ApprovalRequiredError(
                        f"First paid use of tool {entry['tool']!r} requires approval"
                    )

        # Check budget
        if Decimal(str(estimated)) > max(Decimal(0), self._available()):
            message = (
                f"Reservation of ${estimated:.2f} exceeds usable budget "
                f"${self._usable():.2f}"
            )
            if self.mode == BudgetMode.CAP or paid_execution:
                raise BudgetExceededError(message)
            if self.mode == BudgetMode.WARN:
                entry["budget_warning"] = True
                entry["budget_warning_message"] = message

        entry["status"] = EntryStatus.RESERVED.value
        entry["reserved_usd"] = estimated
        entry["timestamp"] = self._now()

    def approve_tool(self, tool: str) -> None:
        """Legacy first-tool acknowledgement; never authorizes real execution."""
        if not isinstance(tool, str) or not tool.strip():
            raise ValueError("tool must be a nonempty string")
        with self._transaction():
            self._approved_tools.add(tool)

    def approve_entry(
        self, entry_id: str, *, request_hash: str, approved_usd: float, approved_by: str,
    ) -> None:
        """Record an operator's exact request/amount approval, not blanket consent."""
        approved_usd = self.money(approved_usd)
        if not isinstance(approved_by, str) or not approved_by.strip():
            raise ValueError("approved_by must identify the private operator")
        with self._transaction():
            entry = self._find(entry_id)
            self._require_status(entry, EntryStatus.ESTIMATED)
            if entry.get("request_hash") != request_hash or approved_usd != entry["estimated_usd"]:
                raise ApprovalRequiredError("Approval must match the exact request and estimated amount")
            approval = entry.get("approval")
            if approval is not None:
                if approval["amount_usd"] == approved_usd and approval["approved_by"] == approved_by:
                    return
                raise ValueError("An existing approval cannot be rewritten")
            entry["approval"] = {
                "amount_usd": approved_usd, "approved_by": approved_by, "timestamp": self._now(),
            }

    def begin_execution(self, tool: str, request_hash: str, estimated_usd: float) -> str:
        """Atomically claim one exact approval and reserve before dispatch.

        A claimed entry is never replayed, including after a process crash.
        Multiple explicit approvals of the same request authorize multiple calls.
        """
        estimated_usd = self.money(estimated_usd)
        if self.cost_log_path is None or self._project is None:
            raise ApprovalRequiredError("Paid execution requires a durable project-bound ledger")
        with self._transaction():
            candidates = [
                entry for entry in self._entries
                if entry["tool"] == tool and entry.get("request_hash") == request_hash
                and entry["estimated_usd"] == estimated_usd
                and entry["status"] in (EntryStatus.ESTIMATED.value, EntryStatus.RESERVED.value)
                and entry.get("approval", {}).get("amount_usd") == estimated_usd
            ]
            if not candidates:
                raise ApprovalRequiredError("No unused approval for this exact paid request and amount")
            entry = candidates[0]
            if entry["status"] == EntryStatus.ESTIMATED.value:
                self._reserve(entry, paid_execution=True)
            elif self._available() < 0:
                raise BudgetExceededError("Existing reservations exceed the paid execution cap")
            entry["status"] = EntryStatus.EXECUTING.value
            entry["timestamp"] = self._now()
            return entry["id"]

    def reconcile(self, entry_id: str, actual_usd: float, success: bool = True) -> None:
        """Reconcile actual spend after tool execution."""
        actual_usd = self.money(actual_usd)
        if not isinstance(success, bool):
            raise ValueError("success must be a boolean")
        status = EntryStatus.COMPLETED.value if success else EntryStatus.FAILED.value
        with self._transaction():
            entry = self._find(entry_id)
            if entry["status"] == status and entry["actual_usd"] == actual_usd:
                return
            self._require_status(entry, EntryStatus.RESERVED, EntryStatus.EXECUTING, EntryStatus.UNKNOWN)
            entry.update(status=status, actual_usd=actual_usd, reserved_usd=0.0, timestamp=self._now())

    @contextmanager
    def recover_entry(
        self, entry_id: str, tool: str, request_hash: str, estimated_usd: float,
    ) -> Iterator[dict]:
        """Serialize read/delivery recovery of one original approved operation.

        This lock is per entry, not project-wide, and is released on process
        exit. An executing entry must first be explicitly marked unknown after
        confirming its worker has stopped; a live original call is not resumed.
        Provider-side verification that no new submission can occur is mandatory
        at the execution boundary, in addition to these ledger checks.
        """
        estimated_usd = self.money(estimated_usd)
        if self.cost_log_path is None or self._project is None:
            raise ApprovalRequiredError("Recovery requires a durable project ledger")
        if not isinstance(entry_id, str) or len(entry_id) != 32 or any(c not in "0123456789abcdef" for c in entry_id):
            raise ValueError("Invalid recovery cost entry ID")
        path = self.cost_log_path.with_name(f"{self.cost_log_path.name}.{entry_id}.recovery")
        with ledger_lock(path):
            with self._transaction(write=False):
                entry = self._find(entry_id)
                self._require_status(entry, EntryStatus.UNKNOWN, EntryStatus.COMPLETED, EntryStatus.FAILED)
                if (
                    entry["tool"] != tool or entry.get("request_hash") != request_hash
                    or entry["estimated_usd"] != estimated_usd
                    or entry.get("approval", {}).get("amount_usd") != estimated_usd
                ):
                    raise ApprovalRequiredError("Recovery must match the original approved request and amount")
                snapshot = copy.deepcopy(entry)
            yield snapshot

    def mark_unknown(self, entry_id: str, provider_request_id: Optional[str] = None) -> None:
        """Retain the full hold when submission/billing/delivery is ambiguous."""
        with self._transaction():
            entry = self._find(entry_id)
            self._require_status(entry, EntryStatus.EXECUTING, EntryStatus.UNKNOWN)
            entry["status"] = EntryStatus.UNKNOWN.value
            if provider_request_id is not None:
                if not isinstance(provider_request_id, str) or not provider_request_id.strip():
                    raise ValueError("provider_request_id must be nonempty")
                previous = entry.get("provider_request_id")
                if previous is not None and previous != provider_request_id:
                    raise ValueError("A reservation cannot be reassigned to a different remote job")
                entry["provider_request_id"] = provider_request_id
            entry["timestamp"] = self._now()

    def record_submission(self, entry_id: str, provider_request_id: str) -> None:
        """Persist a remote request ID immediately, before polling/delivery."""
        if not isinstance(provider_request_id, str) or not provider_request_id.strip():
            raise ValueError("provider_request_id must be nonempty")
        with self._transaction():
            entry = self._find(entry_id)
            previous = entry.get("provider_request_id")
            if (
                entry["status"] in (EntryStatus.COMPLETED.value, EntryStatus.FAILED.value)
                and previous == provider_request_id
            ):
                # A verified delivery recovery may repeat the accepted identity.
                # It must not reopen or modify already reconciled spending.
                return
            self._require_status(entry, EntryStatus.EXECUTING, EntryStatus.UNKNOWN)
            if previous is not None and previous != provider_request_id:
                raise ValueError("A reservation cannot be reassigned to a different remote job")
            entry["provider_request_id"] = provider_request_id

    def mark_not_submitted(self, entry_id: str) -> None:
        """Release only on a provider's explicit proof that dispatch did not occur."""
        with self._transaction():
            entry = self._find(entry_id)
            if entry["status"] == EntryStatus.REFUNDED.value:
                return
            self._require_status(entry, EntryStatus.EXECUTING)
            if entry.get("provider_request_id"):
                raise ValueError("A recorded remote job cannot be declared not submitted")
            entry.update(status=EntryStatus.REFUNDED.value, reserved_usd=0.0, timestamp=self._now())

    def refund(self, entry_id: str) -> None:
        """Cancel a reservation without executing."""
        with self._transaction():
            entry = self._find(entry_id)
            if entry["status"] == EntryStatus.REFUNDED.value:
                return
            self._require_status(entry, EntryStatus.ESTIMATED, EntryStatus.RESERVED)
            entry.update(status=EntryStatus.REFUNDED.value, reserved_usd=0.0, timestamp=self._now())

    # ---- Reference-driven estimation ----

    def estimate_from_reference(
        self,
        video_analysis_brief: dict,
        target_duration_seconds: int,
        tool_plan: dict,
    ) -> dict:
        """Estimate production cost based on reference analysis + target duration.

        Args:
            video_analysis_brief: The VideoAnalysisBrief artifact from video analysis
            target_duration_seconds: How long the output video should be
            tool_plan: Which tools will be used for each asset type, e.g.:
                {
                    "image_generation": {"tool": "flux_fal", "cost_per_unit": 0.05},
                    "video_generation": {"tool": "kling_fal", "cost_per_unit": 0.30,
                                         "clip_duration_seconds": 5},
                    "tts": {"tool": "elevenlabs_tts", "cost_per_word": 0.00003},
                    "music": {"tool": "music_gen", "cost_per_track": 0.10},
                }

        Returns:
            Itemized cost breakdown with line items, total, sample cost, and assumptions.
        """
        structure = video_analysis_brief.get("structure_analysis", {})
        pacing = structure.get("pacing_profile", {})
        narration = video_analysis_brief.get("narration_transcript", {})
        ref_duration = video_analysis_brief.get("source", {}).get("duration_seconds", 60)
        pacing_style = pacing.get("pacing_style", "steady_educational")

        # ── Scene count estimation ──
        # Don't just scale linearly — use the PACING DENSITY from the reference.
        # A music video with 8 scenes in 162s has ~3 cuts/min.
        # Scaling to 60s should PRESERVE that cut rate, not reduce scene count.
        ref_scenes = structure.get("total_scenes", 8)
        if ref_duration > 0:
            cuts_per_minute = ref_scenes / (ref_duration / 60)
        else:
            cuts_per_minute = 4.0  # default: moderate pacing

        # Apply pacing-aware minimums (a fast-cut video doesn't become a slideshow)
        min_scenes_by_pacing = {
            "rapid_fire": 10,
            "dynamic_social": 8,
            "steady_educational": 5,
            "slow_contemplative": 3,
            "variable": 6,
        }
        min_scenes = min_scenes_by_pacing.get(pacing_style, 5)

        # Scene count = max(pacing-density-based, minimum for style)
        density_based_scenes = round(cuts_per_minute * (target_duration_seconds / 60))
        estimated_scenes = max(min_scenes, density_based_scenes)

        # ── Narration word count ──
        ref_word_count = narration.get("word_count", 0)
        if ref_duration > 0 and ref_word_count > 0:
            actual_wpm = (ref_word_count / ref_duration) * 60
        else:
            actual_wpm = 150  # default conversational pace
        estimated_words = round(actual_wpm * (target_duration_seconds / 60))

        # ── Motion ratio from reference ──
        scenes_list = structure.get("scenes", [])
        motion_ratio, motion_basis = self._estimate_motion_ratio(
            video_analysis_brief=video_analysis_brief,
            scenes_list=scenes_list,
            pacing_style=pacing_style,
        )

        estimated_motion_scenes = (
            max(1, round(estimated_scenes * motion_ratio))
            if motion_ratio > 0
            else 0
        )
        estimated_still_scenes = estimated_scenes - estimated_motion_scenes

        # ── Video clip coverage ──
        # Video gen tools produce clips of limited duration (typically 5-10s).
        # A 60s video with motion needs enough clips to COVER the duration,
        # not just 1 per scene.
        vid_plan = tool_plan.get("video_generation", {})
        clip_duration = vid_plan.get("clip_duration_seconds", 5) if vid_plan else 5
        motion_seconds = target_duration_seconds * motion_ratio
        clips_needed_for_coverage = max(
            estimated_motion_scenes,
            round(motion_seconds / clip_duration)
        ) if vid_plan else 0

        # ── Retry/waste buffer ──
        # Not every generation succeeds or looks good. Add a buffer.
        retry_multiplier = 1.3  # ~30% extra for retries and rejected outputs

        # ── Image count ──
        # Images per scene depends on visual variety needs:
        # - Explainer: 1-2 images per scene
        # - Music video / cinematic: 2-3 images per scene (mood shifts, variety)
        images_per_scene = 2.0 if pacing_style in ("dynamic_social", "rapid_fire") else 1.5
        estimated_images = max(
            estimated_scenes,
            round(estimated_scenes * images_per_scene)
        )

        # Build line items
        line_items = []
        assumptions = []

        assumptions.append(
            f"{estimated_scenes} scenes (reference has {cuts_per_minute:.1f} cuts/min, "
            f"pacing: {pacing_style})"
        )
        assumptions.append(motion_basis)

        # Image generation
        img_plan = tool_plan.get("image_generation", {})
        if img_plan:
            img_count = round(estimated_images * retry_multiplier)
            unit_cost = img_plan.get("cost_per_unit", 0.05)
            line_items.append({
                "category": "image_generation",
                "provider": img_plan.get("tool", "unknown"),
                "quantity": img_count,
                "unit_cost_usd": unit_cost,
                "total_usd": round(img_count * unit_cost, 4),
                "basis": (
                    f"~{images_per_scene:.0f} images/scene x {estimated_scenes} scenes "
                    f"+ {round((retry_multiplier - 1) * 100)}% retry buffer"
                ),
            })

        # Video generation
        if vid_plan and clips_needed_for_coverage > 0:
            clip_count = round(clips_needed_for_coverage * retry_multiplier)
            unit_cost = vid_plan.get("cost_per_unit", 0.30)
            line_items.append({
                "category": "video_generation",
                "provider": vid_plan.get("tool", "unknown"),
                "quantity": clip_count,
                "unit_cost_usd": unit_cost,
                "total_usd": round(clip_count * unit_cost, 4),
                "basis": (
                    f"{motion_seconds:.0f}s of motion / {clip_duration}s clips = "
                    f"{clips_needed_for_coverage} clips + retry buffer"
                ),
            })
            assumptions.append(
                f"{round(motion_ratio * 100)}% motion ratio → "
                f"{motion_seconds:.0f}s needs {clips_needed_for_coverage} clips "
                f"({clip_duration}s each)"
            )

        # TTS narration
        tts_plan = tool_plan.get("tts", {})
        if tts_plan and estimated_words > 10:
            cost_per_word = tts_plan.get("cost_per_word", 0.00003)
            tts_cost = round(estimated_words * cost_per_word, 4)
            line_items.append({
                "category": "tts_narration",
                "provider": tts_plan.get("tool", "unknown"),
                "quantity": estimated_words,
                "unit_cost_usd": cost_per_word,
                "total_usd": tts_cost,
                "basis": f"Narration at {round(actual_wpm)} WPM = ~{estimated_words} words",
            })
            assumptions.append(
                f"Narration at {round(actual_wpm)} WPM = ~{estimated_words} words "
                f"for {target_duration_seconds} seconds"
            )

        # Music
        music_plan = tool_plan.get("music", {})
        if music_plan:
            music_cost = music_plan.get("cost_per_track", 0.0)
            line_items.append({
                "category": "music",
                "provider": music_plan.get("tool", "unknown"),
                "quantity": 1,
                "unit_cost_usd": music_cost,
                "total_usd": music_cost,
                "basis": "1 background music track",
            })

        subtotal = round(sum(item["total_usd"] for item in line_items), 4)

        # ── Cost range instead of single number ──
        # Low: everything works first try. High: retry buffer fully consumed.
        low_total = round(subtotal / retry_multiplier, 4)
        high_total = round(subtotal * 1.15, 4)  # 15% above retry-buffered estimate

        # Sample cost: 2 scenes worth of assets (hook + 1 middle)
        sample_scenes = 2
        sample_fraction = sample_scenes / max(estimated_scenes, 1)
        sample_cost = round(subtotal * sample_fraction, 4)

        # Confidence based on how much data we have
        if scenes_list and narration.get("word_count", 0) > 0:
            confidence = "high"
        elif scenes_list or narration.get("word_count", 0) > 0:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "line_items": line_items,
            "total_usd": subtotal,
            "total_range_usd": {"low": low_total, "high": high_total},
            "sample_cost_usd": sample_cost,
            "confidence": confidence,
            "assumptions": assumptions,
            "estimated_scenes": estimated_scenes,
            "estimated_images": estimated_images,
            "estimated_clips": clips_needed_for_coverage,
            "estimated_words": estimated_words,
            "motion_ratio": round(motion_ratio, 2),
            "cuts_per_minute": round(cuts_per_minute, 1),
            "target_duration_seconds": target_duration_seconds,
        }

    def _estimate_motion_ratio(
        self,
        *,
        video_analysis_brief: dict,
        scenes_list: list[dict[str, Any]],
        pacing_style: str,
    ) -> tuple[float, str]:
        """Estimate how much of the target treatment truly needs motion."""
        motion_weights = {
            "animation": 1.0,
            "b_roll": 1.0,
            "stock_footage": 1.0,
            "product_shot": 0.9,
            "transition": 0.6,
            "screen_recording": 0.45,
            "talking_head": 0.35,
            "diagram": 0.25,
            "chart": 0.25,
            "text_card": 0.2,
        }
        classified_weights = [
            motion_weights[visual_type]
            for scene in scenes_list
            if (visual_type := scene.get("visual_type")) in motion_weights
        ]
        if classified_weights:
            ratio = sum(classified_weights) / len(classified_weights)
            unknown_count = max(0, len(scenes_list) - len(classified_weights))
            if unknown_count:
                fallback_ratio, _ = self._fallback_motion_ratio(
                    video_analysis_brief=video_analysis_brief,
                    pacing_style=pacing_style,
                )
                ratio = (
                    (sum(classified_weights) + fallback_ratio * unknown_count)
                    / len(scenes_list)
                )
                basis = (
                    "motion ratio blended from classified scene types and "
                    "reference-style fallback for unclassified scenes"
                )
            else:
                basis = "motion ratio derived from classified scene types"
            return round(min(max(ratio, 0.0), 0.95), 2), basis

        return self._fallback_motion_ratio(
            video_analysis_brief=video_analysis_brief,
            pacing_style=pacing_style,
        )

    def _fallback_motion_ratio(
        self,
        *,
        video_analysis_brief: dict,
        pacing_style: str,
    ) -> tuple[float, str]:
        """Fallback heuristic for motion ratio before scene vision enrichment."""
        source_type = video_analysis_brief.get("source", {}).get("type", "")
        replication = video_analysis_brief.get("replication_guidance", {})
        motion_required = bool(replication.get("motion_required"))
        suggested_pipeline = replication.get("suggested_pipeline", "")

        base_by_pacing = {
            "rapid_fire": 0.8,
            "dynamic_social": 0.65,
            "steady_educational": 0.35,
            "slow_contemplative": 0.2,
            "variable": 0.5,
        }
        ratio = base_by_pacing.get(pacing_style, 0.5)

        if source_type in ("shorts", "instagram", "tiktok"):
            ratio = max(ratio, 0.7)
        if motion_required:
            ratio = max(ratio, 0.6)
        if suggested_pipeline == "cinematic":
            ratio = max(ratio, 0.55)

        ratio = round(min(max(ratio, 0.1), 0.95), 2)
        basis = (
            "motion ratio inferred from pacing/style because scene visual types "
            "have not been enriched yet"
        )
        return ratio, basis

    # ---- Persistence ----

    @contextmanager
    def _transaction(self, *, write: bool = True) -> Iterator[None]:
        with self._thread_lock:
            lock = ledger_lock(self.cost_log_path) if self.cost_log_path is not None else nullcontext()
            with lock:
                if self.cost_log_path is not None:
                    if self.cost_log_path.exists():
                        self._load()
                    elif self._has_loaded:
                        raise ValueError("Cost ledger disappeared; refusing to reset committed spending")
                snapshot = copy.deepcopy((self._entries, self._approved_tools, self._policy, self._project))
                try:
                    yield
                    if write:
                        self._save()
                except BaseException:
                    self._entries, self._approved_tools, self._policy, self._project = snapshot
                    raise

    @staticmethod
    def _validate(data: dict) -> None:
        schema_path = Path(__file__).resolve().parents[1] / "schemas/artifacts/cost_log.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
        # JSON Schema's numeric predicates do not reliably reject NaN/Infinity.
        json.dumps(data, allow_nan=False)
        BudgetConfig.model_validate(data["policy"])
        if data["budget_total_usd"] != data["policy"]["total_usd"]:
            raise ValueError("Ledger budget total disagrees with persisted policy")
        seen = set()
        for entry in data["entries"]:
            if entry["id"] in seen:
                raise ValueError("Duplicate cost entry ID")
            seen.add(entry["id"])
            for key in ("estimated_usd", "actual_usd", "reserved_usd"):
                CostTracker.money(entry[key])
            outstanding = entry["status"] in ("reserved", "executing", "unknown")
            terminal_spend = entry["status"] in ("completed", "failed")
            if outstanding and entry["reserved_usd"] != entry["estimated_usd"]:
                raise ValueError("Outstanding entries must retain their full estimate")
            if not outstanding and entry["reserved_usd"] != 0:
                raise ValueError("Only outstanding entries may hold a reservation")
            if not terminal_spend and entry["actual_usd"] != 0:
                raise ValueError("Actual spend may not be hidden in an unspent state")
            if "approval" in entry:
                if not entry.get("request_hash") or entry["approval"]["amount_usd"] != entry["estimated_usd"]:
                    raise ValueError("Approval does not match its exact request and amount")
        if data["budget_reserved_usd"] != float(CostTracker._sum(e["reserved_usd"] for e in data["entries"])):
            raise ValueError("Reserved total disagrees with entries")
        if data["budget_spent_usd"] != float(CostTracker._sum(e["actual_usd"] for e in data["entries"])):
            raise ValueError("Spent total disagrees with entries")

    def _save(self) -> None:
        if self.cost_log_path is None:
            return
        data = {
            "version": "2.0",
            "policy": self._policy.model_dump(mode="json"),
            "budget_total_usd": self.budget_total_usd,
            "budget_reserved_usd": self._reserved(),
            "budget_spent_usd": self._spent(),
            "approved_tools": sorted(self._approved_tools),
            "entries": self._entries,
        }
        if self._project is not None:
            data["project"] = self._project
        self._validate(data)
        atomic_write_json(self.cost_log_path, data)
        self._has_loaded = True

    def _load(self) -> None:
        with open(self.cost_log_path, encoding="utf-8") as f:  # type: ignore[arg-type]
            data = json.load(f)
        if data.get("version") != "2.0":
            raise ValueError("Legacy cost ledger has no durable policy; explicit reviewed migration required")
        self._validate(data)
        if self._project is not None and data.get("project") != self._project:
            raise ValueError("Cost ledger belongs to a different or unbound project")
        self._policy = BudgetConfig.model_validate(data["policy"])
        self._entries = data["entries"]
        self._approved_tools = set(data["approved_tools"])
        self._project = data.get("project")
        self._has_loaded = True

    # ---- Helpers ----

    def _find(self, entry_id: str) -> dict[str, Any]:
        for entry in self._entries:
            if entry["id"] == entry_id:
                return entry
        raise KeyError(f"Cost entry {entry_id!r} not found")

    @staticmethod
    def money(value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("USD amount must be a finite nonnegative number")
        try:
            amount = float(value)
        except OverflowError as exc:
            raise ValueError("USD amount is too large") from exc
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("USD amount must be finite and nonnegative")
        return amount

    @staticmethod
    def _require_status(entry: dict, *allowed: EntryStatus) -> None:
        if entry["status"] not in {status.value for status in allowed}:
            raise ValueError(f"Invalid cost transition from {entry['status']!r}")

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
