import pytest

from lib.budget import prepare_paid_call
from lib.checkpoint import init_project
from tools.base_tool import BaseTool, ToolResult, ToolRuntime
from tools.cost_tracker import ApprovalRequiredError
from tools.video.seedance_ark import SeedanceArkVideo


class PaidFixture(BaseTool):
    name = "paid-fixture"
    runtime = ToolRuntime.API
    capability = "image_generation"

    def estimate_cost(self, inputs):
        return 0.2

    def execute(self, inputs):
        raise AssertionError("This fixture must never submit")


def test_artifact_destination_is_required_before_approval(tmp_path):
    project = init_project("fixture", title="fixture", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    with pytest.raises(ApprovalRequiredError, match="output destination"):
        prepare_paid_call(project, PaidFixture(), {"prompt": "fixture"})


def test_input_cannot_claim_an_undeclared_free_operation():
    with pytest.raises(ApprovalRequiredError, match="Unscoped"):
        PaidFixture().execute({"task_action": "query", "prompt": "still paid"})


def test_query_of_existing_job_does_not_create_paid_reservation(monkeypatch):
    tool = SeedanceArkVideo()
    monkeypatch.setenv("ARK_API_KEY", "fixture-only")
    monkeypatch.setattr(tool, "_query_task", lambda task_id, api_key: {"id": task_id, "status": "running"})
    monkeypatch.setattr(tool, "_create_task", lambda *args: pytest.fail("Query must never submit"))
    result = tool.execute({"task_action": "query", "task_id": "cgt-fixture"})
    assert result.success
    assert result.cost_entry_id is None


def test_query_usage_is_not_recorded_as_new_spend(monkeypatch, tmp_path):
    from lib.events import read_events

    monkeypatch.setattr("lib.events.PROJECTS_DIR", tmp_path)
    project = init_project("fixture", title="fixture", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    tool = SeedanceArkVideo()
    monkeypatch.setenv("ARK_API_KEY", "fixture-only")
    monkeypatch.setattr(tool, "_query_task", lambda task_id, api_key: {"id": task_id, "status": "succeeded"})
    monkeypatch.setattr(tool, "_cost_from_task", lambda task, inputs: 0.7)
    result = tool.execute({"task_action": "query", "task_id": "cgt-fixture", "project_dir": str(project)})
    assert result.success and result.cost_usd == 0.7
    assert read_events(project)[-1]["cost_usd"] == 0
    assert not (project / "cost_log.json").exists()


def test_dry_run_reports_unknown_quote_without_dispatch():
    class UnavailableQuote(PaidFixture):
        def estimate_cost(self, inputs):
            raise ValueError("No eligible provider")

    result = UnavailableQuote().dry_run({})
    assert result["would_execute"] is False
    assert result["estimated_cost_usd"] is None
    assert result["estimate_error"] == "No eligible provider"


def test_cancel_of_existing_job_never_submits(monkeypatch):
    tool = SeedanceArkVideo()
    monkeypatch.setenv("ARK_API_KEY", "fixture-only")
    called = []
    monkeypatch.setattr(tool, "_cancel_task", lambda task_id, api_key: called.append(task_id))
    monkeypatch.setattr(tool, "_create_task", lambda *args: pytest.fail("Cancel must never submit"))
    result = tool.execute({"task_action": "cancel", "task_id": "cgt-fixture"})
    assert result.success and called == ["cgt-fixture"]
    assert result.cost_entry_id is None
