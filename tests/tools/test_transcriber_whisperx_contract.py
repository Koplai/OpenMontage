"""WhisperX 3.8.6 surface doubles; no ASR/alignment models are loaded."""

import sys
from types import SimpleNamespace

import pytest

from tools.analysis.transcriber import Transcriber


@pytest.fixture
def transcription(monkeypatch, tmp_path):
    word = SimpleNamespace(word="hello", start=0, end=1, probability=0.9)
    segment = SimpleNamespace(id=0, start=0, end=1, text="hello", words=[word])
    model = SimpleNamespace(transcribe=lambda *a, **k: (
        iter([segment]), SimpleNamespace(language="en", duration=1)))
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=lambda *a, **k: model))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 0))
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake")
    return {"input_path": str(audio)}


def test_alignment_without_diarization_has_consistent_word_timestamps(monkeypatch, transcription):
    aligned = [{"start": 0.2, "end": 0.8, "text": "hello",
                "words": [{"word": "hello", "start": 0.2, "end": 0.8, "score": 0.9}]}]
    monkeypatch.setitem(sys.modules, "whisperx", SimpleNamespace(
        load_audio=lambda _: b"fake",
        load_align_model=lambda **k: ("model", {}),
        align=lambda *a, **k: {"segments": aligned},
    ))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    result = Transcriber().execute({**transcription, "align": True})
    assert result.success, result.error
    assert result.data["alignment_status"] == "completed"
    assert result.data["diarization_status"] == "not_requested"
    assert result.data["word_timestamps"] == result.data["segments"][0]["words"]
    assert result.data["word_timestamps"][0]["start"] == 0.2


def test_diarization_uses_submodule_and_token_without_alignment(monkeypatch, transcription):
    calls = []

    class DiarizationPipeline:
        def __init__(self, *, token, device):
            calls.append((token, device))

        def __call__(self, audio):
            return "speakers"

    def assign(speakers, result):
        assert speakers == "speakers"
        result["segments"][0]["words"][0]["speaker"] = "SPEAKER_00"
        result["segments"][0]["speaker"] = "SPEAKER_00"
        return result

    monkeypatch.setitem(sys.modules, "whisperx", SimpleNamespace(
        load_audio=lambda _: b"audio", assign_word_speakers=assign))
    monkeypatch.setitem(sys.modules, "whisperx.diarize", SimpleNamespace(
        DiarizationPipeline=DiarizationPipeline))
    monkeypatch.setenv("HF_TOKEN", "fake-token")
    result = Transcriber().execute({**transcription, "diarize": True})
    assert result.success, result.error
    assert calls == [("fake-token", "cpu")]
    assert result.data["alignment_status"] == "not_requested"
    assert result.data["diarization_status"] == "completed"
    assert result.data["word_timestamps"][0]["speaker"] == "SPEAKER_00"


def test_requested_unavailable_diarization_is_not_success(monkeypatch, transcription):
    monkeypatch.setitem(sys.modules, "whisperx", None)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", None)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    result = Transcriber().execute({**transcription, "diarize": True})
    assert not result.success
    assert result.data["diarization_status"] == "unavailable"
    assert result.data["segments"]  # partial transcription remains usable
    assert "diarization" in result.error


def test_gpu_guidance_does_not_advertise_nonexistent_extra():
    assert "faster-whisper[gpu]" not in Transcriber.install_instructions
