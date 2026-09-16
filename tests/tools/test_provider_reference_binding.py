"""Content binding across native LOCAL media aliases; no provider/network calls."""

import json
from pathlib import Path

import pytest

from lib.budget import approve_paid_call, paid_execution, prepare_paid_call
from lib.provider_jobs import ProviderJob, request_fingerprint
from tools.base_tool import BaseTool, ToolResult, ToolRuntime
from tools.cost_tracker import ApprovalRequiredError


LOCAL_ALIASES = [
    ("image", False), ("image_url", False), ("images", True),
    ("image_urls", True), ("image_path", False), ("image_paths", True),
    ("reference_image", False), ("reference_images", True),
    ("reference_image_url", False), ("reference_image_urls", True),
    ("reference_image_path", False), ("reference_image_paths", True),
    ("input_reference", False), ("input_reference_path", False),
    ("reference_tail_image_url", False), ("end_image_url", False),
    ("video_url", False), ("reference_video_urls", True),
    ("audio_url", False), ("reference_audio_urls", True),
]


class LocalReferencePaid(BaseTool):
    name = "local_reference_paid"
    provider = "fake"
    runtime = ToolRuntime.API

    def __init__(self):
        self.calls = 0

    def estimate_cost(self, inputs):
        return 0.2

    def execute(self, inputs):
        self.calls += 1
        return ToolResult(success=False, cost_usd=0.2)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "project.json").write_text('{"project_id":"refs","pipeline_type":"framework-smoke"}')
    return tmp_path


def media_input(project, alias, is_list):
    source = project / "local.png"
    source.write_bytes(b"original local media")
    value = [str(source)] if is_list else str(source)
    return source, {alias: value, "project_dir": str(project)}


@pytest.mark.parametrize("alias,is_list", LOCAL_ALIASES)
def test_provider_recovery_binds_every_local_alias(monkeypatch, project, alias, is_list):
    monkeypatch.setattr("lib.budget.record_paid_submission", lambda _: None)
    source, inputs = media_input(project, alias, is_list)
    job = ProviderJob.open(inputs, "fake", "model", 0.2)
    job.submitting()
    job.submitted("job-1")
    recovery = {**inputs, "recovery_id": job.recovery_id}
    ProviderJob.validate_recovery(recovery, "fake", "model", 0.2)
    source.write_bytes(b"replaced local media")
    with pytest.raises(ValueError, match="project/request"):
        ProviderJob.validate_recovery(recovery, "fake", "model", 0.2)
    assert "original local media" not in job.path.read_text()
    assert str(source) not in job.path.read_text()


@pytest.mark.parametrize("alias,is_list", LOCAL_ALIASES)
def test_paid_approval_binds_every_local_alias(project, alias, is_list):
    source, inputs = media_input(project, alias, is_list)
    tool = LocalReferencePaid()
    request = prepare_paid_call(project, tool, inputs)
    approve_paid_call(request, approved_usd=request.estimated_usd, approved_by="fake operator")
    source.write_bytes(b"replaced local media")
    with paid_execution(project), pytest.raises(ApprovalRequiredError):
        tool.execute(request.inputs)
    assert tool.calls == 0
    ledger = (project / "cost_log.json").read_text()
    assert "original local media" not in ledger
    assert str(source) not in ledger


@pytest.mark.parametrize("boundary", ["provider", "budget"])
@pytest.mark.parametrize("value", [
    "https://example.test/ref.png?token=fake",
    "http://example.test/ref.png",
    "data:image/png;base64,c3ludGhldGlj",
])
def test_true_urls_never_trigger_filesystem_probes(monkeypatch, project, boundary, value):
    def unexpected_probe(path):
        raise AssertionError(f"A URL must not be probed as a local path: {path}")

    monkeypatch.setattr(Path, "is_file", unexpected_probe)
    inputs = {"image_path": value, "images": [value], "image_url": value}
    if boundary == "provider":
        request_fingerprint(inputs)
    else:
        from lib.budget import _request_hash
        _request_hash(LocalReferencePaid(), inputs, project)


@pytest.mark.parametrize("boundary", ["provider", "budget"])
def test_arbitrary_prompt_strings_never_trigger_file_reads(monkeypatch, project, boundary):
    source = project / "prompt-looking-path.txt"
    source.write_text("not an input media reference")

    def unexpected_probe(path):
        raise AssertionError("Prompt/text values are not filesystem references")

    monkeypatch.setattr(Path, "is_file", unexpected_probe)
    inputs = {"prompt": str(source), "text": str(source), "negative_prompt": str(source)}
    if boundary == "provider":
        request_fingerprint(inputs)
    else:
        from lib.budget import _request_hash
        _request_hash(LocalReferencePaid(), inputs, project)


@pytest.mark.parametrize("boundary", ["provider", "budget"])
def test_nested_native_image_list_binds_local_bytes(project, boundary):
    source = project / "local.png"
    source.write_bytes(b"first")
    inputs = {"image_list": [{"image_url": str(source)}]}
    if boundary == "provider":
        fingerprint = request_fingerprint
    else:
        from lib.budget import _request_hash
        fingerprint = lambda values: _request_hash(LocalReferencePaid(), values, project)
    first = fingerprint(inputs)
    source.write_bytes(b"second")
    assert fingerprint(inputs) != first


def test_url_values_are_not_persisted_in_provider_journal(project):
    url = "https://example.test/ref.png?token=fake-sensitive"
    job = ProviderJob.open(
        {"project_dir": str(project), "image_url": url, "prompt": "private request text"},
        "fake", "model", 0.2,
    )
    journal = job.path.read_text()
    assert url not in journal
    assert "fake-sensitive" not in journal
    assert "private request text" not in journal
    assert len(json.loads(journal)["request_fingerprint"]) == 64
