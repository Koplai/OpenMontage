"""Offline regression tests for paid submission, recovery and selector boundaries.

Provider unit tests unwrap BaseTool instrumentation deliberately: budget integration
is covered separately, and every transport here is a double.
"""

import base64
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from tools.base_tool import ToolResult, ToolStatus


@pytest.fixture(autouse=True)
def fake_budget_submission_hook(monkeypatch):
    """Unwrapped provider-only tests use no real budget reservation."""
    monkeypatch.setattr("lib.budget.record_paid_submission", lambda _: None)


def execute(tool, inputs):
    return inspect.unwrap(type(tool).execute)(tool, inputs)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "project.json").write_text(json.dumps({"project_id": "test"}))
    return {"project_dir": str(tmp_path), "output_path": str(tmp_path / "asset.mp4")}


class Clock:
    now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Response:
    status_code = 200
    content = b"video"

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


def test_kling_does_not_retry_ambiguous_post_but_retries_get(monkeypatch):
    from tools._kling.client import KlingClient

    calls = []

    def timeout(*args, **kwargs):
        calls.append(args)
        raise requests.ReadTimeout("accepted but connection lost")

    monkeypatch.setattr("tools._kling.client.time.sleep", lambda _: None)
    client = KlingClient(api_key="fake", session=SimpleNamespace(post=timeout, get=timeout))
    with pytest.raises(Exception):
        client.post("/v1/videos/text2video", {})
    assert len(calls) == 1
    calls.clear()
    with pytest.raises(Exception):
        client.get("/v1/videos/text2video/id")
    assert len(calls) == 3


def test_job_claim_is_project_bound_and_contains_no_request_secrets(project, tmp_path):
    from lib.provider_jobs import ProviderJob

    inputs = {**project, "prompt": "private creative text", "api_key": "secret",
              "approval_token": "approval-secret"}
    job = ProviderJob.open(inputs, "fake", "model", 0.5)
    assert job.should_submit
    job.submitting()
    other = ProviderJob.open(inputs, "fake", "model", 0.5)
    assert not other.should_submit
    with pytest.raises(RuntimeError, match="uncertain"):
        other.require_resumable()
    journal = job.path.read_text()
    assert "secret" not in journal
    assert "private creative text" not in journal
    other_project = tmp_path / "other"
    other_project.mkdir()
    (other_project / "project.json").write_text('{"project_id":"other"}')
    with pytest.raises(ValueError, match="recovery"):
        ProviderJob.open({**inputs, "project_dir": str(other_project),
                          "recovery_id": job.recovery_id}, "fake", "model", 0.5)


def test_fingerprint_hashes_file_content_not_only_path(project, tmp_path):
    from lib.provider_jobs import request_fingerprint

    image = tmp_path / "reference.png"
    image.write_bytes(b"one")
    inputs = {**project, "image_path": str(image), "api_key": "first"}
    first = request_fingerprint(inputs)
    assert first == request_fingerprint({**inputs, "api_key": "second"})
    image.write_bytes(b"two")
    assert first != request_fingerprint(inputs)


def test_fingerprint_hashes_native_image_array_files(tmp_path):
    from lib.provider_jobs import request_fingerprint

    image = tmp_path / "reference.png"
    image.write_bytes(b"one")
    inputs = {"images": [str(image)]}
    first = request_fingerprint(inputs)
    image.write_bytes(b"two")
    assert first != request_fingerprint(inputs)


@pytest.mark.parametrize("module,classname", [
    ("seedance_video", "SeedanceVideo"),
    ("kling_video", "KlingVideo"),
    ("gemini_omni_fal", "GeminiOmniFalVideo"),
])
def test_fal_pending_is_bounded_and_resumes_without_post(monkeypatch, project, module, classname):
    from importlib import import_module
    from lib import provider_jobs

    clock = Clock()
    monkeypatch.setattr(provider_jobs.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(provider_jobs.time, "sleep", clock.sleep)
    monkeypatch.setenv("FAL_KEY", "fake")
    calls = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: (
        calls.append(a) or Response({"request_id": "job-1",
                                    "status_url": "https://queue.fal.run/vendor/model/requests/job-1/status",
                                    "response_url": "https://queue.fal.run/vendor/model/requests/job-1"})))
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response({"status": "IN_PROGRESS"}))
    tool = getattr(import_module("tools.video." + module), classname)()
    inputs = {**project, "prompt": "test", "timeout_seconds": 6, "poll_interval": 2}
    first = execute(tool, inputs)
    assert not first.success
    assert first.cost_usd > 0
    assert first.data["job_id"] == "job-1"
    assert clock.now <= 6
    second = execute(tool, {**inputs, "recovery_id": first.data["recovery_id"]})
    assert not second.success
    assert len(calls) == 1


def test_sora_download_failure_keeps_id_and_recovers(monkeypatch, project):
    from tools.video.sora_video import SoraVideo

    calls = []
    downloads = []

    def download(video_id, **kwargs):
        downloads.append(video_id)
        if len(downloads) <= 3:
            raise requests.ReadTimeout("delivery timeout")
        return b"video"

    videos = SimpleNamespace(
        create=lambda **kw: calls.append(kw) or {"id": "video-1", "status": "queued"},
        retrieve=lambda *a, **kw: {"id": "video-1", "status": "completed"},
        download_content=download,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(
        __version__="2.44.0", OpenAI=lambda **kw: SimpleNamespace(videos=videos)))
    inputs = {**project, "prompt": "test", "poll_interval": 0.01}
    first = execute(SoraVideo(), inputs)
    assert not first.success and first.cost_usd > 0
    assert first.data["job_id"] == "video-1"
    assert first.data["remote_task_id"] == "video-1"
    assert first.data["recovery_state"] == first.data["submission_state"]
    assert first.data["cost_status"] == "unknown"
    second = execute(SoraVideo(), {**inputs, "recovery_id": first.data["recovery_id"]})
    assert second.success, second.error
    assert len(calls) == 1


def test_image_delivery_retry_uses_staged_bytes(monkeypatch, project, tmp_path):
    from tools.graphics.openai_image import OpenAIImage
    from lib import provider_jobs

    calls = []
    images = SimpleNamespace(generate=lambda **kw: calls.append(kw) or SimpleNamespace(
        data=[SimpleNamespace(b64_json=base64.b64encode(b"image").decode())]))
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(
        OpenAI=lambda **kw: SimpleNamespace(images=images)))
    original = provider_jobs.atomic_write

    def broken_delivery(path, content):
        if Path(path) == tmp_path / "asset.mp4":
            raise OSError("disk full")
        return original(path, content)

    monkeypatch.setattr(provider_jobs, "atomic_write", broken_delivery)
    inputs = {**project, "prompt": "test"}
    first = execute(OpenAIImage(), inputs)
    assert not first.success and first.cost_usd > 0
    monkeypatch.setattr(provider_jobs, "atomic_write", original)
    second = execute(OpenAIImage(), {**inputs, "recovery_id": first.data["recovery_id"]})
    assert second.success, second.error
    assert len(calls) == 1
    assert Path(second.artifacts[0]).read_bytes() == b"image"


class Provider:
    def __init__(self, name, provider, props=None, supports=None, available=True):
        self.name, self.provider = name, provider
        self.input_schema = {"properties": props or {"prompt": {}}}
        self.supports = supports or {}
        self.available = available
        self.executed = None

    def get_status(self):
        return ToolStatus.AVAILABLE if self.available else ToolStatus.UNAVAILABLE

    def get_info(self):
        return {}

    def estimate_cost(self, inputs):
        self.estimated = inputs
        return 0.135 * inputs.get("num_images", inputs.get("number_of_images", 1))

    def execute(self, inputs):
        self.executed = inputs
        return ToolResult(success=True)


def ranks(monkeypatch, providers):
    monkeypatch.setattr("lib.scoring.rank_providers", lambda *a: [
        SimpleNamespace(tool_name=t.name, provider=t.provider, weighted_score=1 - i / 2,
                        explain=lambda: "fake", to_dict=lambda: {})
        for i, t in enumerate(providers)
    ])


@pytest.mark.parametrize("kind", ["video", "image", "tts"])
def test_selector_never_substitutes_explicit_provider(monkeypatch, kind):
    from tools.video.video_selector import VideoSelector
    from tools.graphics.image_selector import ImageSelector
    from tools.audio.tts_selector import TTSSelector

    preferred = Provider("preferred", "preferred", supports={"text_to_video": True})
    better = Provider("better", "better", supports={"text_to_video": True})
    providers = [better, preferred]
    ranks(monkeypatch, providers)
    selector = {"video": VideoSelector, "image": ImageSelector, "tts": TTSSelector}[kind]()
    monkeypatch.setattr(selector, "_providers", lambda: providers)
    result = execute(selector, {"prompt": "test", "text": "test", "preferred_provider": "preferred"})
    assert result.success
    assert preferred.executed is not None and better.executed is None
    preferred.available = False
    result = execute(selector, {"prompt": "test", "text": "test", "preferred_provider": "preferred"})
    assert not result.success
    assert better.executed is None


@pytest.mark.parametrize("count_key", ["num_images", "number_of_images"])
def test_image_selector_estimate_and_execute_use_identical_native_count(monkeypatch, count_key):
    from tools.graphics.image_selector import ImageSelector

    provider = Provider("images", "images", {"prompt": {}, count_key: {}})
    ranks(monkeypatch, [provider])
    selector = ImageSelector()
    monkeypatch.setattr(selector, "_providers", lambda: [provider])
    inputs = {"prompt": "test", "n": 4}
    assert selector.estimate_cost(inputs) == pytest.approx(0.54)
    assert execute(selector, inputs).success
    assert provider.estimated == provider.executed
    assert provider.executed[count_key] == 4


@pytest.mark.parametrize("operation", ["reference_to_video", "edit_video"])
def test_video_selector_rejects_unsupported_operation(monkeypatch, operation):
    from tools.video.video_selector import VideoSelector

    provider = Provider("text", "text", supports={"text_to_video": True})
    ranks(monkeypatch, [provider])
    selector = VideoSelector()
    monkeypatch.setattr(selector, "_providers", lambda: [provider])
    assert not execute(selector, {"prompt": "test", "operation": operation}).success
    assert provider.executed is None


def test_image_selector_cannot_strip_edit_inputs(monkeypatch):
    from tools.graphics.image_selector import ImageSelector

    provider = Provider("text", "text")
    ranks(monkeypatch, [provider])
    selector = ImageSelector()
    monkeypatch.setattr(selector, "_providers", lambda: [provider])
    assert not execute(selector, {"prompt": "test", "image_url": "https://example.test/ref"}).success
    assert provider.executed is None


@pytest.mark.parametrize("module,classname", [
    ("tools.graphics.openai_image", "OpenAIImage"),
    ("tools.audio.openai_tts", "OpenAITTS"),
])
def test_openai_preflight_requires_sdk(monkeypatch, module, classname):
    from importlib import import_module

    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setitem(sys.modules, "openai", None)
    assert getattr(import_module(module), classname)().get_status() == ToolStatus.UNAVAILABLE


def test_ambiguous_fal_submission_is_durable_and_cannot_submit_again(monkeypatch, project):
    from tools.video.kling_video import KlingVideo

    monkeypatch.setenv("FAL_KEY", "fake")
    posts = []

    def submit(*args, **kwargs):
        record = json.loads(next(Path(project["project_dir"]).glob(".provider_jobs/*.json")).read_text())
        assert record["state"] == "submitting"
        posts.append(args)
        raise requests.ReadTimeout("fake request token should not be recorded")

    monkeypatch.setattr(requests, "post", submit)
    inputs = {**project, "prompt": "test"}
    first = execute(KlingVideo(), inputs)
    second = execute(KlingVideo(), inputs)
    assert not first.success and not second.success
    assert first.data["recovery_id"] == second.data["recovery_id"]
    assert first.cost_usd == second.cost_usd > 0
    assert len(posts) == 1
    assert "fake request token" not in first.error


def test_submission_id_is_persisted_before_first_get(monkeypatch, project):
    from lib.provider_jobs import Deadline, ProviderJob, fal_result

    job = ProviderJob.open(project, "fal", "vendor/model", 1)
    monkeypatch.setattr(requests, "post", lambda *a, **k: Response({"request_id": "job-1"}))

    def get(url, **kwargs):
        assert json.loads(job.path.read_text())["job_id"] == "job-1"
        if url.endswith("/status"):
            return Response({"status": "COMPLETED"})
        return Response({"video": {"url": "https://media.test/video?token=private"}})

    monkeypatch.setattr(requests, "get", get)
    result = fal_result(job, "vendor/model/text-to-video", {}, "fake", Deadline(10))
    assert "private" in result["video"]["url"]
    assert "private" not in job.path.read_text()
    assert "fake" not in job.path.read_text()


def test_duplicate_submit_claim_is_atomic(project):
    from concurrent.futures import ThreadPoolExecutor
    from lib.provider_jobs import ProviderJob

    def claim(_):
        job = ProviderJob.open(project, "fake", "model", 1)
        try:
            job.submitting()
            return 1
        except RuntimeError:
            return 0

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(claim, range(8))) == 1


def test_staged_delivery_checks_integrity_and_keeps_old_final(project):
    from lib.provider_jobs import ProviderJob

    job = ProviderJob.open(project, "fake", "model", 1)
    job.submitting()
    job.stage([b"good"])
    final = Path(project["output_path"])
    final.write_bytes(b"old")
    job.path.with_suffix(".0.bin").write_bytes(b"damaged")
    with pytest.raises(ValueError, match="damaged"):
        job.deliver([final])
    assert final.read_bytes() == b"old"


def test_project_scope_fails_before_submission(monkeypatch, project, tmp_path):
    from lib.provider_jobs import ProviderJob

    with pytest.raises(ValueError, match="inside"):
        ProviderJob.open({**project, "output_path": str(tmp_path.parent / "outside.mp4")}, "fake", "model", 1)
    assert not list(tmp_path.glob(".provider_jobs/*.json"))


@pytest.mark.parametrize("method", ["classic", "turbo"])
def test_official_polling_uses_monotonic_deadline(monkeypatch, method):
    from tools._kling.client import KlingClient

    clock = Clock()
    monkeypatch.setattr("lib.provider_jobs.time.monotonic", clock.monotonic)
    monkeypatch.setattr("lib.provider_jobs.time.sleep", clock.sleep)
    monkeypatch.setattr("tools._kling.client.time.time", lambda: -99999)
    data = {"code": 0, "data": {"task_status": "processing"}}
    if method == "turbo":
        data["data"] = [{"status": "processing"}]
    client = KlingClient(api_key="fake", session=SimpleNamespace(get=lambda *a, **k: Response(data)))
    with pytest.raises(TimeoutError):
        if method == "classic":
            client.poll_classic("/videos", "job-1", "videos", timeout_seconds=6, poll_interval=2)
        else:
            client.poll_turbo("job-1", timeout_seconds=6, poll_interval=2)
    assert clock.now == 6


def test_sora_selector_aliases_normalize_before_default_seconds(monkeypatch):
    from tools.video.sora_video import SoraVideo
    from tools.video.video_selector import VideoSelector

    tool = SoraVideo()
    monkeypatch.setattr(tool, "get_status", lambda: ToolStatus.AVAILABLE)
    selector = VideoSelector()
    monkeypatch.setattr(selector, "_providers", lambda: [tool])
    ranks(monkeypatch, [tool])
    selected, normalized = selector.resolve_execution({"prompt": "test", "duration": "8", "aspect_ratio": "16:9"})
    assert selected is tool
    assert normalized["seconds"] == "8"
    assert normalized["size"] == "1280x720"
    assert "duration" not in normalized
    assert selector.estimate_cost({"prompt": "test", "duration": "8"}) == 1.0


@pytest.mark.parametrize("classname,module,inputs", [
    ("SeedanceVideo", "tools.video.seedance_video", {"operation": "image_to_video"}),
    ("KlingVideo", "tools.video.kling_video", {"reference_image_paths": ["missing.png"]}),
    ("GeminiOmniFalVideo", "tools.video.gemini_omni_fal",
     {"operation": "image_to_video", "reference_image_urls": ["https://one", "https://two"]}),
    ("SoraVideo", "tools.video.sora_video", {"reference_video_urls": ["https://video"]}),
    ("OpenAIImage", "tools.graphics.openai_image", {"reference_image_path": "missing.png"}),
])
def test_direct_adapters_do_not_ignore_incompatible_media(classname, module, inputs):
    from importlib import import_module

    tool = getattr(import_module(module), classname)()
    with pytest.raises(ValueError):
        tool.normalize_inputs({"prompt": "test", **inputs})


def test_unknown_explicit_model_cannot_fall_through_selector(monkeypatch):
    from tools.video.video_selector import VideoSelector
    from tools.graphics.image_selector import ImageSelector

    provider = Provider("text", "text", {"prompt": {}, "model": {"enum": ["known"]}},
                        {"text_to_video": True})
    ranks(monkeypatch, [provider])
    for selector in (VideoSelector(), ImageSelector()):
        monkeypatch.setattr(selector, "_providers", lambda: [provider])
        assert not execute(selector, {"prompt": "test", "model": "unknown"}).success
    assert provider.executed is None
