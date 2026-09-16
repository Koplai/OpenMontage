"""Transcription tool wrapping faster-whisper / WhisperX.

Provides speech-to-text, optional forced alignment and optional speaker labels.
CPU fallback is explicit; an unavailable requested pass is not reported as success.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ResumeSupport,
    ToolResult,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class Transcriber(BaseTool):
    name = "transcriber"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "analysis"
    provider = "whisperx"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = ["python:faster_whisper"]
    install_instructions = (
        "pip install faster-whisper  # CPU mode\n"
        "GPU: install CUDA/cuDNN versions supported by your CTranslate2 build; "
        "the same faster-whisper package is used (no gpu extra).\n"
        "pip install whisperx==3.8.6  # Optional alignment/diarization; "
        "diarization also needs HF_TOKEN and accepted pyannote model terms."
    )
    agent_skills = ["speech-to-text"]

    capabilities = [
        "transcribe",
        "word_timestamps",
        "diarization",
        "language_detection",
    ]

    input_schema = {
        "type": "object",
        "required": ["input_path"],
        "properties": {
            "input_path": {"type": "string", "description": "Path to audio or video file"},
            "model_size": {
                "type": "string",
                "enum": ["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                "default": "base",
            },
            "language": {"type": "string", "description": "ISO 639-1 language code, or null for auto-detect"},
            "diarize": {"type": "boolean", "default": False},
            "align": {"type": "boolean", "default": False,
                      "description": "Run WhisperX forced alignment independently of speaker diarization."},
            "output_dir": {"type": "string", "description": "Directory for output files"},
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "segments": {"type": "array"},
            "word_timestamps": {"type": "array"},
            "language": {"type": "string"},
            "duration_seconds": {"type": "number"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2,
        ram_mb=2048,
        vram_mb=0,  # CPU by default; GPU optional
        disk_mb=500,
        network_required=False,
    )

    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["MemoryError"])
    resume_support = ResumeSupport.FROM_START
    idempotency_key_fields = ["input_path", "model_size", "language"]
    side_effects = ["writes transcript JSON to output_dir"]
    fallback = None
    user_visible_verification = [
        "Check transcript text against source audio",
        "Verify word timestamps align with speech",
    ]

    def get_status(self) -> ToolStatus:
        try:
            import faster_whisper  # noqa: F401
            return ToolStatus.AVAILABLE
        except ImportError:
            return ToolStatus.UNAVAILABLE

    def _has_diarization(self) -> bool:
        if not os.environ.get("HF_TOKEN"):
            return False
        try:
            from whisperx.diarize import DiarizationPipeline  # noqa: F401
            return True
        except (ImportError, OSError):
            return False

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        """Rough estimate: ~0.5x real-time on CPU for 'base' model."""
        return 60.0  # conservative default

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        model_size = inputs.get("model_size", "base")
        language = inputs.get("language")
        diarize = inputs.get("diarize", False)
        output_dir = Path(inputs.get("output_dir", input_path.parent))

        if not input_path.exists():
            return ToolResult(success=False, error=f"Input file not found: {input_path}")

        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return ToolResult(
                success=False,
                error="faster-whisper is not installed. Run: pip install faster-whisper",
            )

        start = time.time()

        # faster-whisper executes through CTranslate2, so that runtime—not
        # PyTorch—is authoritative for CUDA availability and compute types.
        device = "cpu"
        compute_type = "int8"
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                supported = ctranslate2.get_supported_compute_types("cuda")
                for candidate in ("float16", "int8_float16", "float32"):
                    if candidate in supported:
                        device = "cuda"
                        compute_type = candidate
                        break
        except Exception:
            # Probing is advisory. CPU remains a safe deterministic baseline.
            pass

        def _transcribe_on(selected_device: str, selected_compute_type: str):
            model = WhisperModel(
                model_size,
                device=selected_device,
                compute_type=selected_compute_type,
            )
            segments_iter, transcription_info = model.transcribe(
                str(input_path),
                language=language,
                word_timestamps=True,
                vad_filter=True,
            )

            parsed_segments = []
            parsed_words = []
            # faster-whisper evaluates lazily. Draining the iterator here keeps
            # missing CUDA runtime libraries inside the fallback boundary.
            for seg in segments_iter:
                seg_data = {
                    "id": seg.id,
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text.strip(),
                }

                if seg.words:
                    words = []
                    for word in seg.words:
                        word_entry = {
                            "word": word.word,
                            "start": round(word.start, 3),
                            "end": round(word.end, 3),
                            "probability": round(word.probability, 3),
                        }
                        words.append(word_entry)
                        parsed_words.append(word_entry)
                    seg_data["words"] = words

                parsed_segments.append(seg_data)

            return parsed_segments, parsed_words, transcription_info

        gpu_fallback_reason = None
        try:
            segments, word_timestamps, info = _transcribe_on(device, compute_type)
        except Exception as exc:
            if device == "cpu":
                raise
            gpu_fallback_reason = f"{type(exc).__name__}: {exc}"
            device = "cpu"
            compute_type = "int8"
            segments, word_timestamps, info = _transcribe_on(device, compute_type)

        detected_language = language or info.language
        duration = info.duration

        alignment_status = "not_requested"
        diarization_status = "not_requested"
        errors = []
        if inputs.get("align"):
            try:
                segments = self._apply_alignment(str(input_path), segments, detected_language)
                alignment_status = "completed"
            except Exception as exc:
                alignment_status = "failed"
                errors.append(f"Requested alignment failed ({type(exc).__name__}); install/check WhisperX 3.8.6")
        if diarize:
            if not self._has_diarization():
                diarization_status = "unavailable"
                errors.append("Requested diarization unavailable: WhisperX 3.8.6, HF_TOKEN and pyannote access are required")
            else:
                try:
                    segments = self._apply_diarization(str(input_path), segments)
                    diarization_status = "completed"
                except Exception as exc:
                    diarization_status = "failed"
                    errors.append(f"Requested diarization failed ({type(exc).__name__}); verify pyannote model access")

        # One timing source for both nested words and top-level consumers.
        word_timestamps = [word for segment in segments for word in segment.get("words", [])]

        elapsed = time.time() - start

        result_data = {
            "segments": segments,
            "word_timestamps": word_timestamps,
            "language": detected_language,
            "duration_seconds": round(duration, 3),
            "model_size": model_size,
            "device": device,
            "compute_type": compute_type,
            "gpu_fallback_reason": gpu_fallback_reason,
            "alignment_status": alignment_status,
            "diarization_status": diarization_status,
            "warnings": errors,
        }

        # Write transcript JSON
        output_path = output_dir / f"{input_path.stem}_transcript.json"
        output_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

        return ToolResult(
            success=not errors,
            error="; ".join(errors) if errors else None,
            data=result_data,
            artifacts=[str(output_path)],
            duration_seconds=round(elapsed, 2),
        )

    def _apply_alignment(
        self,
        audio_path: str,
        segments: list[dict],
        language: str,
    ) -> list[dict]:
        """Forced alignment is independent of gated speaker model access."""
        import whisperx

        audio = whisperx.load_audio(audio_path)
        align_model, align_metadata = whisperx.load_align_model(language_code=language, device="cpu")
        aligned = whisperx.align(segments, align_model, align_metadata, audio, device="cpu")
        return aligned["segments"]

    def _apply_diarization(self, audio_path: str, segments: list[dict]) -> list[dict]:
        """WhisperX stable 3.8.6 exports this class from whisperx.diarize."""
        import copy
        import whisperx
        from whisperx.diarize import DiarizationPipeline

        audio = whisperx.load_audio(audio_path)
        diarize_model = DiarizationPipeline(token=os.environ["HF_TOKEN"], device="cpu")
        diarize_segments = diarize_model(audio)
        result = whisperx.assign_word_speakers(diarize_segments, {"segments": copy.deepcopy(segments)})
        segments = result["segments"]
        if segments and not any(segment.get("speaker") for segment in segments):
            raise ValueError("Diarization returned no speaker labels")
        return segments
