"""Tests for the export_bundle publisher tool.

Covers the tool contract, registry discovery, the export bundle layout, a
schema-valid publish_log, chapter formatting, and the missing-video error path.
"""

import json
import hashlib
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.publishers.export_bundle import ExportBundle
from tools.base_tool import ToolStatus, ToolTier
from tools.tool_registry import ToolRegistry
from schemas.artifacts import validate_artifact


def _make_video(path: Path) -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe required for final delivery tests")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "color=c=blue:s=64x64:r=10:d=1", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-y", str(path),
    ], check=True, capture_output=True)


def _review(video):
    return {
        "version": "1.0", "output_path": str(video), "status": "pass",
        "output_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "recommended_action": "present_to_user",
        "checks": {key: {} for key in (
            "technical_probe", "visual_spotcheck", "audio_spotcheck",
            "promise_preservation", "subtitle_check",
        )},
    }


def test_contract_metadata():
    tool = ExportBundle()
    info = tool.get_info()
    assert info["name"] == "export_bundle"
    assert info["capability"] == "publish"
    assert info["tier"] == ToolTier.PUBLISH.value
    assert info["provider"] == "local"
    assert info["resource_profile"]["network_required"] is False
    assert tool.get_status() == ToolStatus.AVAILABLE
    assert tool.estimate_cost({}) == 0.0


def test_missing_video_errors(tmp_path):
    result = ExportBundle().execute(
        {"video_path": str(tmp_path / "nope.mp4"), "title": "X"}
    )
    assert result.success is False
    assert "not found" in (result.error or "")


def test_export_bundle_layout_and_publish_log(tmp_path):
    video = tmp_path / "projects" / "demo" / "renders" / "final.mp4"
    _make_video(video)
    subs = tmp_path / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

    result = ExportBundle().execute(
        {
            "video_path": str(video),
            "final_review": _review(video),
            "title": "Vector Databases Explained in 60 Seconds",
            "export_dir": str(tmp_path / "out"),
            "description": "A quick explainer.",
            "tags": ["vector db", "explainer"],
            "hashtags": ["#ai", "#database"],
            "chapters": [
                {"start_seconds": 0, "title": "Intro"},
                {"start_seconds": 75, "title": "How it works"},
            ],
            "subtitles_path": str(subs),
            "thumbnail_concept": {"text_overlay": "100x FASTER"},
            "platform": "youtube",
            "visibility": "unlisted",
            "timestamp": "2026-06-29T10:30:00+00:00",
        }
    )
    assert result.success is True
    root = Path(result.data["export_path"])

    # Layout
    assert (root / "video" / "output.mp4").is_file()
    assert (root / "video" / "subtitles.srt").is_file()
    assert (root / "metadata" / "metadata.json").is_file()
    assert (root / "metadata" / "description.txt").is_file()
    assert (root / "metadata" / "tags.txt").is_file()
    assert (root / "metadata" / "chapters.txt").is_file()
    assert (root / "thumbnails" / "concept.json").is_file()

    # tags one-per-line
    assert (root / "metadata" / "tags.txt").read_text().splitlines() == ["vector db", "explainer"]
    # chapter formatting (75s -> 1:15)
    assert "1:15 - How it works" in (root / "metadata" / "chapters.txt").read_text()

    # publish_log is schema-valid and shaped right
    plog = result.data["publish_log"]
    validate_artifact("publish_log", plog)
    entry = plog["entries"][0]
    assert entry["status"] == "exported"
    assert entry["platform"] == "youtube"
    assert entry["visibility"] == "unlisted"
    assert entry["export_path"] == str(root)
    assert entry["metadata_used"]["title"].startswith("Vector Databases")


def test_chapter_time_formatting_hours(tmp_path):
    video = tmp_path / "p" / "renders" / "final.mp4"
    _make_video(video)
    result = ExportBundle().execute(
        {
            "video_path": str(video),
            "final_review": _review(video),
            "title": "Long",
            "export_dir": str(tmp_path / "out"),
            "chapters": [{"time_seconds": 3725, "label": "Deep dive"}],  # 1:02:05
        }
    )
    assert result.success is True
    txt = (Path(result.data["export_path"]) / "metadata" / "chapters.txt").read_text()
    assert "1:02:05 - Deep dive" in txt


def test_infer_project_name(tmp_path):
    video = tmp_path / "projects" / "my-cool-video" / "renders" / "final.mp4"
    _make_video(video)
    result = ExportBundle().execute(
        {"video_path": str(video), "title": "T", "export_dir": str(tmp_path / "out"),
         "final_review": _review(video)}
    )
    # export still works; project name inference exercised via no-export_dir path below
    assert result.success is True


def test_missing_optional_asset_errors(tmp_path):
    video = tmp_path / "p" / "renders" / "final.mp4"
    _make_video(video)
    for key in ("subtitles_path", "thumbnail_path"):
        result = ExportBundle().execute(
            {
                "video_path": str(video),
                "title": "T",
                "export_dir": str(tmp_path / "out"),
                key: str(tmp_path / "does_not_exist.x"),
            }
        )
        assert result.success is False, key
        assert key in (result.error or "")


def test_default_export_dir_inside_project_workspace(tmp_path):
    # projects/<name>/renders/final.mp4 -> projects/<name>/exports (no export_dir given)
    video = tmp_path / "projects" / "demo" / "renders" / "final.mp4"
    _make_video(video)
    result = ExportBundle().execute({"video_path": str(video), "title": "T",
                                     "final_review": _review(video)})
    assert result.success is True
    assert Path(result.data["export_path"]) == (tmp_path / "projects" / "demo" / "exports").resolve()


def test_registry_discovers_export_bundle():
    reg = ToolRegistry()
    reg.discover()
    assert reg.get("export_bundle") is not None
    assert reg.get_by_capability("publish")[0].name == "export_bundle"


@pytest.mark.parametrize("status", [None, "revise", "fail"])
def test_final_export_requires_pass_review(tmp_path, status):
    video = tmp_path / "final.mp4"
    _make_video(video)
    inputs = {"video_path": str(video), "title": "T", "export_dir": str(tmp_path / "out")}
    if status:
        inputs["final_review"] = {**_review(video), "status": status}
    result = ExportBundle().execute(inputs)
    assert not result.success
    assert "review" in result.error.lower()
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("defect", ["bytes", "path", "stale", "invalid_media", "action"])
def test_final_export_rejects_unbound_or_invalid_output(tmp_path, defect):
    video = tmp_path / "final.mp4"
    _make_video(video)
    review = _review(video)
    if defect == "bytes":
        video.write_bytes(video.read_bytes() + b"changed")
    elif defect == "path":
        review["output_path"] = str(tmp_path / "foreign.mp4")
    elif defect == "stale":
        review["reviewed_at"] = "2000-01-01T00:00:00Z"
    elif defect == "invalid_media":
        video.write_bytes(b"not a video")
        review = _review(video)
    else:
        review["recommended_action"] = "re_render"
    result = ExportBundle().execute({
        "video_path": str(video), "title": "T", "final_review": review,
        "export_dir": str(tmp_path / "out"),
    })
    assert not result.success
    assert not (tmp_path / "out").exists()


def test_explicit_draft_accepts_diagnostic_bytes_but_never_labels_final(tmp_path):
    video = tmp_path / "diagnostic.mp4"
    video.write_bytes(b"explicit diagnostic fixture, not valid final media")
    result = ExportBundle().execute({
        "video_path": str(video), "title": "Diagnostic", "delivery_mode": "draft",
        "export_dir": str(tmp_path / "out"),
    })
    assert result.success
    assert result.data["publish_log"]["entries"][0]["status"] == "draft"
    assert result.data["delivery_mode"] == "draft"


def test_replacement_removes_omitted_assets_and_invalid_log_preserves_old(tmp_path):
    video = tmp_path / "final.mp4"
    _make_video(video)
    optional = tmp_path / "subs.srt"
    optional.write_text("diagnostic captions")
    inputs = {
        "video_path": str(video), "title": "T", "final_review": _review(video),
        "export_dir": str(tmp_path / "out"),
    }
    assert ExportBundle().execute({
        **inputs, "tags": ["tag"], "subtitles_path": str(optional),
        "chapters": [{"time": "0:00", "label": "Start"}],
        "thumbnail_concept": {"text": "Old"},
    }).success
    root = tmp_path / "out"
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = ExportBundle().execute({**inputs, "visibility": "invalid"})
    assert not result.success
    assert {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    assert ExportBundle().execute(inputs).success
    for relative in ("metadata/tags.txt", "metadata/chapters.txt", "video/subtitles.srt",
                     "thumbnails/concept.json"):
        assert not (root / relative).exists()


def test_copy_failure_preserves_previous_bundle(tmp_path, monkeypatch):
    video = tmp_path / "final.mp4"
    _make_video(video)
    root = tmp_path / "out"
    root.mkdir()
    (root / "old.txt").write_text("old accepted export")

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copy2", fail)
    result = ExportBundle().execute({
        "video_path": str(video), "title": "T", "final_review": _review(video),
        "export_dir": str(root),
    })
    assert not result.success
    assert (root / "old.txt").read_text() == "old accepted export"


def test_source_changed_while_copying_cannot_become_final(tmp_path, monkeypatch):
    video = tmp_path / "final.mp4"
    _make_video(video)
    original_copy = shutil.copy2

    def corrupt_copy(source, target):
        result = original_copy(source, target)
        Path(target).write_bytes(Path(target).read_bytes() + b"changed during copy")
        return result

    monkeypatch.setattr(shutil, "copy2", corrupt_copy)
    result = ExportBundle().execute({
        "video_path": str(video), "title": "T", "final_review": _review(video),
        "export_dir": str(tmp_path / "out"),
    })
    assert not result.success
    assert not (tmp_path / "out").exists()


def test_invalid_timestamp_rejected_before_any_export_writes(tmp_path):
    video = tmp_path / "final.mp4"
    _make_video(video)
    before = set(tmp_path.iterdir())
    result = ExportBundle().execute({
        "video_path": str(video), "title": "T", "final_review": _review(video),
        "export_dir": str(tmp_path / "out"), "timestamp": "not a timestamp",
    })
    assert not result.success
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("digest", [None, "0" * 64])
def test_supplied_render_report_must_bind_same_hash(tmp_path, digest):
    video = tmp_path / "final.mp4"
    _make_video(video)
    output = {"path": str(video), "format": "mp4", "resolution": "64x64", "duration_seconds": 1}
    if digest:
        output["sha256"] = digest
    result = ExportBundle().execute({
        "video_path": str(video), "title": "T", "final_review": _review(video),
        "render_report": {"version": "1.0", "outputs": [output]},
        "export_dir": str(tmp_path / "out"),
    })
    assert not result.success
    assert not (tmp_path / "out").exists()


def test_concurrent_export_commits_do_not_mix_bundles(tmp_path):
    video = tmp_path / "final.mp4"
    _make_video(video)
    inputs = {
        "video_path": str(video), "final_review": _review(video),
        "export_dir": str(tmp_path / "out"),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(ExportBundle().execute, {**inputs, "title": "A", "tags": ["A"]}),
            pool.submit(ExportBundle().execute, {**inputs, "title": "B"}),
        ]
        assert all(future.result().success for future in futures)
    root = tmp_path / "out"
    metadata = json.loads((root / "metadata" / "metadata.json").read_text())
    assert (root / "metadata" / "tags.txt").exists() == (metadata["title"] == "A")
    log = json.loads((root / "metadata" / "publish_log.json").read_text())
    assert log["entries"][0]["metadata_used"]["title"] == metadata["title"]


def test_probeable_but_corrupt_video_fails_full_decode(tmp_path):
    """A valid header is not evidence that every frame can be decoded."""
    video = tmp_path / "corrupt.mp4"
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe required for final delivery tests")
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x64:rate=10:duration=2", "-c:v", "libx264",
        "-movflags", "+faststart", "-y", str(video),
    ], check=True, capture_output=True)
    data = video.read_bytes()
    # Keep the complete faststart moov but truncate media packets.
    video.write_bytes(data[:len(data) * 3 // 4])
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_format", "-of", "json", str(video),
    ], capture_output=True, text=True, check=True)
    assert float(json.loads(probe.stdout)["format"]["duration"]) > 0
    result = ExportBundle().execute({
        "video_path": str(video), "title": "T", "final_review": _review(video),
        "export_dir": str(tmp_path / "out"),
    })
    assert not result.success
    assert "decode" in result.error.lower()
    assert not (tmp_path / "out").exists()


def test_atomic_exchange_failure_preserves_old_export(tmp_path, monkeypatch):
    video = tmp_path / "final.mp4"
    _make_video(video)
    root = tmp_path / "out"
    root.mkdir()
    (root / "old.txt").write_text("old")

    def reject_exchange(*args):
        raise OSError("atomic exchange unsupported")

    monkeypatch.setattr(ExportBundle, "_commit_bundle", reject_exchange)
    result = ExportBundle().execute({
        "video_path": str(video), "title": "T", "final_review": _review(video),
        "export_dir": str(root),
    })
    assert not result.success
    assert [p.name for p in root.iterdir()] == ["old.txt"]
