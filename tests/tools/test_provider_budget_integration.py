"""Real BaseTool budget gate + real adapters; every external transport is fake."""

import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from lib.budget import approve_paid_call, paid_execution, prepare_paid_call
from tools.cost_tracker import ApprovalRequiredError
from tools.base_tool import ToolStatus


@pytest.fixture
def project(tmp_path):
    (tmp_path / "project.json").write_text('{"project_id":"provider-test","pipeline_type":"framework-smoke"}')
    return tmp_path


def approved(project, tool, inputs):
    request = prepare_paid_call(project, tool, {**inputs, "project_dir": str(project)})
    approve_paid_call(request, approved_usd=request.estimated_usd, approved_by="fake test operator")
    return request


def test_sora_recovery_reuses_original_hold_and_records_id_before_poll(monkeypatch, project):
    from tools.video.sora_video import SoraVideo

    creates, downloads = [], []

    def retrieve(*args, **kwargs):
        ledger = json.loads((project / "cost_log.json").read_text())
        assert ledger["entries"][0]["provider_request_id"] == "video-1"
        return {"id": "video-1", "status": "completed"}

    def download(*args, **kwargs):
        downloads.append(args)
        if len(downloads) <= 3:
            raise requests.ReadTimeout("fake delivery failure")
        return b"video"

    videos = SimpleNamespace(
        create=lambda **kwargs: creates.append(kwargs) or {"id": "video-1"},
        retrieve=retrieve, download_content=download,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(
        __version__="2.44.0", OpenAI=lambda **kwargs: SimpleNamespace(videos=videos)))
    monkeypatch.setattr("lib.provider_jobs.time.sleep", lambda _: None)
    tool = SoraVideo()
    request = approved(project, tool, {"prompt": "test", "output_path": str(project / "out.mp4")})
    with paid_execution(project):
        first = tool.execute(request.inputs)
    assert not first.success and first.provider_request_id == "video-1"
    ledger = json.loads((project / "cost_log.json").read_text())
    assert ledger["entries"][0]["reserved_usd"] == request.estimated_usd
    resume_inputs = {**request.inputs, "recovery_id": first.data["recovery_id"]}
    with paid_execution(project, resume_entry_id=first.cost_entry_id):
        recovered = tool.execute(resume_inputs)
    assert recovered.success, recovered.error
    assert recovered.cost_entry_id == first.cost_entry_id
    assert len(creates) == 1
    ledger = json.loads((project / "cost_log.json").read_text())
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["reserved_usd"] == request.estimated_usd
    assert ledger["entries"][0]["actual_usd"] == 0


def test_synchronous_image_delivery_resumes_without_new_approval_or_generation(monkeypatch, project):
    from lib import provider_jobs
    from tools.graphics.openai_image import OpenAIImage

    generates = []
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(
        images=SimpleNamespace(generate=lambda **kw: generates.append(kw) or SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(b"image").decode())])))))
    original = provider_jobs.atomic_write
    output = project / "image.png"

    def fail_delivery(path, data):
        if Path(path) == output:
            raise OSError("fake full disk")
        original(path, data)

    monkeypatch.setattr(provider_jobs, "atomic_write", fail_delivery)
    tool = OpenAIImage()
    request = approved(project, tool, {"prompt": "test", "output_path": str(output)})
    with paid_execution(project):
        first = tool.execute(request.inputs)
    assert not first.success
    resume_inputs = {**request.inputs, "recovery_id": first.data["recovery_id"]}
    with pytest.raises(ApprovalRequiredError):
        prepare_paid_call(project, tool, resume_inputs)
    monkeypatch.setattr(provider_jobs, "atomic_write", original)
    with paid_execution(project, resume_entry_id=first.cost_entry_id):
        recovered = tool.execute(resume_inputs)
    assert recovered.success, recovered.error
    assert len(generates) == 1
    assert output.read_bytes() == b"image"
    ledger = json.loads((project / "cost_log.json").read_text())
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["reserved_usd"] == request.estimated_usd


def test_ambiguous_submission_cannot_use_recovery_to_generate_again(monkeypatch, project):
    from tools.video.kling_video import KlingVideo

    posts = []

    def submit(*args, **kwargs):
        posts.append(args)
        raise requests.ReadTimeout("fake ambiguous response")

    monkeypatch.setenv("FAL_KEY", "fake")
    monkeypatch.setattr(requests, "post", submit)
    tool = KlingVideo()
    request = approved(project, tool, {"prompt": "test", "output_path": str(project / "video.mp4")})
    with paid_execution(project):
        result = tool.execute(request.inputs)
    assert not result.success
    with paid_execution(project, resume_entry_id=result.cost_entry_id):
        with pytest.raises(RuntimeError, match="uncertain"):
            tool.execute({**request.inputs, "recovery_id": result.data["recovery_id"]})
    assert len(posts) == 1


def test_selector_approval_uses_resolved_count_and_exact_native_request(monkeypatch, project):
    from tools.graphics.image_selector import ImageSelector
    from tools.graphics.seedream_image import SeedreamImage

    tool = SeedreamImage()
    monkeypatch.setattr(tool, "get_status", lambda: ToolStatus.AVAILABLE)
    selector = ImageSelector()
    monkeypatch.setattr(selector, "_providers", lambda: [tool])
    selected, params = selector.resolve_execution({
        "prompt": "test", "n": 4, "project_dir": str(project),
        "preferred_provider": "bytedance", "output_path": str(project / "images.png"),
    })
    assert selected is tool
    request = prepare_paid_call(project, selected, params)
    assert request.estimated_usd == 0.54
    assert request.inputs["num_images"] == 4 and "n" not in request.inputs
