"""Offline regressions for the real paid execution boundary and durable ledger."""

from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
from unittest.mock import Mock

import jsonschema
import pytest

from lib.config_model import BudgetConfig, BudgetMode
from tools.base_tool import BaseTool, ToolResult, ToolRuntime
from tools.cost_tracker import ApprovalRequiredError, BudgetExceededError, CostTracker


def capped(path: Path) -> CostTracker:
    return CostTracker(
        cost_log_path=path, budget_total_usd=1, reserve_pct=0,
        single_action_approval_usd=10, require_approval_for_new_paid_tool=False,
        mode=BudgetMode.CAP,
    )


def test_two_stale_trackers_cannot_reserve_eighty_cents_twice(tmp_path):
    path = tmp_path / "cost_log.json"
    first, second = capped(path), capped(path)
    a = first.estimate("one", "generate", .8)
    b = second.estimate("two", "generate", .8)
    first.reserve(a)
    with pytest.raises(BudgetExceededError):
        second.reserve(b)
    reopened = CostTracker(cost_log_path=path)
    assert len(reopened.entries) == 2
    assert reopened.budget_reserved_usd == .8


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("field", ["total_usd", "single_action_approval_usd", "reserve_pct"])
def test_budget_config_rejects_invalid_numbers(field, value):
    with pytest.raises(ValueError):
        BudgetConfig(**{field: value})


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), -float("inf")])
def test_tracker_rejects_invalid_money_without_mutation(tmp_path, value):
    tracker = capped(tmp_path / "cost_log.json")
    with pytest.raises(ValueError):
        tracker.estimate("paid", "generate", value)
    assert tracker.entries == []
    entry = tracker.estimate("paid", "generate", .8)
    tracker.reserve(entry)
    with pytest.raises(ValueError):
        tracker.reconcile(entry, value)
    assert tracker.budget_reserved_usd == .8


def test_reserve_percentage_is_bounded():
    with pytest.raises(ValueError):
        BudgetConfig(reserve_pct=1.01)
    with pytest.raises(ValueError):
        CostTracker(reserve_pct=1.01)


def test_completed_spend_cannot_be_refunded_or_rewritten(tmp_path):
    tracker = capped(tmp_path / "cost_log.json")
    entry = tracker.estimate("paid", "generate", .8)
    tracker.reserve(entry)
    tracker.reserve(entry)  # idempotent, not a second reservation
    tracker.reconcile(entry, .8)
    tracker.reconcile(entry, .8)  # exactly the same terminal transition is safe
    for action in [lambda: tracker.refund(entry), lambda: tracker.reserve(entry),
                   lambda: tracker.reconcile(entry, 0)]:
        with pytest.raises(ValueError):
            action()
    assert CostTracker(cost_log_path=tracker.cost_log_path).budget_spent_usd == .8


def test_policy_survives_restart_and_conflicting_constructor_defaults(tmp_path):
    path = tmp_path / "cost_log.json"
    tracker = capped(path)
    tracker.estimate("paid", "generate", .2)
    reopened = CostTracker(cost_log_path=path, mode=BudgetMode.OBSERVE, reserve_pct=.9)
    assert reopened.mode == BudgetMode.CAP
    assert reopened.reserve_pct == 0
    assert reopened.single_action_approval_usd == 10
    assert reopened.require_approval_for_new_paid_tool is False


def test_serialized_ledger_validates_against_real_schema(tmp_path):
    tracker = capped(tmp_path / "cost_log.json")
    tracker.approve_tool("paid")
    entry = tracker.estimate("paid", "generate", .2)
    tracker.reserve(entry)
    tracker.reconcile(entry, .15)
    schema = json.loads(Path("schemas/artifacts/cost_log.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(json.loads(tracker.cost_log_path.read_text()))


class FakePaid(BaseTool):
    name = "fake_paid"
    provider = "fake"
    runtime = ToolRuntime.API

    def __init__(self, result=None):
        self.submit = Mock(return_value=result or ToolResult(success=True, cost_usd=.2))

    def estimate_cost(self, inputs):
        return inputs.get("amount", .2)

    def execute(self, inputs):
        return self.submit(inputs)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "project.json").write_text(json.dumps({
        "project_id": "project", "pipeline_type": "framework-smoke",
    }))
    return root


def authorize(project, tool, inputs):
    from lib.budget import approve_paid_call, prepare_paid_call
    request = prepare_paid_call(project, tool, inputs)
    approve_paid_call(request, approved_usd=request.estimated_usd, approved_by="test operator")
    return request


def test_unapproved_concrete_provider_submits_nothing(monkeypatch, project):
    from tools.graphics.openai_image import OpenAIImage
    import openai
    client = Mock()
    monkeypatch.setattr(openai, "OpenAI", client)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-not-a-credential")
    with pytest.raises(ApprovalRequiredError):
        OpenAIImage().execute({"prompt": "test", "output_path": str(project / "image.png")})
    client.assert_not_called()


def test_scoped_but_unapproved_call_submits_nothing(project):
    from lib.budget import paid_execution
    tool = FakePaid()
    with paid_execution(project), pytest.raises(ApprovalRequiredError):
        tool.execute({"prompt": "test"})
    tool.submit.assert_not_called()


def test_exact_request_approval_and_reconciliation(project):
    from lib.budget import paid_execution
    tool, inputs = FakePaid(), {"prompt": "approved", "amount": .2}
    request = authorize(project, tool, inputs)
    with paid_execution(project):
        result = tool.execute(inputs)
    assert result.cost_entry_id == request.entry_id
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    assert ledger.budget_spent_usd == .2
    assert ledger.budget_reserved_usd == 0
    with paid_execution(project), pytest.raises(ApprovalRequiredError):
        tool.execute(inputs)  # approvals are single-use, not a replay license
    assert tool.submit.call_count == 1


@pytest.mark.parametrize("change", [{"prompt": "unapproved"}, {"amount": .3}, {"model": "other"}])
def test_changed_request_cannot_use_approval(project, change):
    from lib.budget import paid_execution
    tool, inputs = FakePaid(), {"prompt": "approved", "amount": .2}
    authorize(project, tool, inputs)
    with paid_execution(project), pytest.raises(ApprovalRequiredError):
        tool.execute({**inputs, **change})
    tool.submit.assert_not_called()


@pytest.mark.parametrize("failure", ["result", "exception"])
def test_ambiguous_failure_retains_reservation(project, failure):
    from lib.budget import paid_execution
    tool, inputs = FakePaid(ToolResult(success=False, error="delivery failed")), {"prompt": "test"}
    if failure == "exception":
        tool.submit.side_effect = TimeoutError("submission outcome unknown")
    request = authorize(project, tool, inputs)
    with paid_execution(project):
        if failure == "exception":
            with pytest.raises(TimeoutError):
                tool.execute(inputs)
        else:
            assert not tool.execute(inputs).success
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    assert ledger.entries[0]["status"] == "unknown"
    assert ledger.budget_reserved_usd == .2
    with pytest.raises(ValueError):
        ledger.refund(request.entry_id)
    ledger.reconcile(request.entry_id, .2, success=False)
    assert ledger.budget_spent_usd == .2


def _reserve_in_process(path, ready, start, outcomes):
    tracker = capped(Path(path))
    entry = tracker.estimate("worker", "generate", .8)
    ready.put(True)
    start.wait(15)
    try:
        tracker.reserve(entry)
    except BudgetExceededError:
        outcomes.put("blocked")
    else:
        outcomes.put("reserved")


def test_reservation_is_process_safe(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready, outcomes, start = context.Queue(), context.Queue(), context.Event()
    path = tmp_path / "cost_log.json"
    workers = [context.Process(target=_reserve_in_process, args=(str(path), ready, start, outcomes))
               for _ in range(2)]
    try:
        for worker in workers:
            worker.start()
        for _ in workers:
            ready.get(timeout=20)
        start.set()
        assert sorted(outcomes.get(timeout=20) for _ in workers) == ["blocked", "reserved"]
        for worker in workers:
            worker.join(20)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(5)
    ledger = CostTracker(cost_log_path=path)
    assert len(ledger.entries) == 2
    assert ledger.budget_reserved_usd == .8


def test_fractional_dollars_do_not_falsely_exceed_exact_cap(tmp_path):
    tracker = CostTracker(
        cost_log_path=tmp_path / "cost_log.json", budget_total_usd=.3,
        reserve_pct=0, require_approval_for_new_paid_tool=False,
    )
    tracker.reserve(tracker.estimate("paid", "one", .1))
    tracker.reserve(tracker.estimate("paid", "two", .2))
    assert tracker.budget_remaining_usd == 0


@pytest.mark.parametrize("status,actual,expected,held", [
    ("reported", .15, "failed", 0),
    ("not_submitted", 0, "refunded", 0),
    ("unknown", 0, "unknown", .2),
    ("unknown", .15, "unknown", .2),
    ("estimated", .15, "unknown", .2),
])
def test_provider_failure_metadata_controls_settlement(project, status, actual, expected, held):
    from lib.budget import paid_execution
    tool = FakePaid(ToolResult(success=False, cost_usd=actual, cost_status=status))
    authorize(project, tool, {})
    with paid_execution(project):
        tool.execute({})
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    assert ledger.entries[0]["status"] == expected
    assert ledger.budget_reserved_usd == held
    assert ledger.budget_spent_usd == (.15 if status == "reported" else 0)


def test_missing_success_cost_is_not_proof_of_free_execution(project):
    from lib.budget import paid_execution
    tool = FakePaid(ToolResult(success=True))
    authorize(project, tool, {})
    with paid_execution(project):
        tool.execute({})
    assert CostTracker(cost_log_path=project / "cost_log.json").budget_reserved_usd == .2


def test_exact_approval_above_threshold_does_not_weaken_cap(project):
    from lib.budget import paid_execution
    tool, inputs = FakePaid(), {"amount": 1}
    authorize(project, tool, inputs)
    with paid_execution(project):
        tool.execute(inputs)
    policy = CostTracker(cost_log_path=project / "cost_log.json")
    assert policy.single_action_approval_usd == .5
    assert policy.require_approval_for_new_paid_tool is True
    authorize(project, tool, {"amount": 99})
    with paid_execution(project), pytest.raises(BudgetExceededError):
        tool.execute({"amount": 99})
    assert tool.submit.call_count == 1


def test_approval_requires_exact_amount(project):
    from lib.budget import approve_paid_call, prepare_paid_call
    request = prepare_paid_call(project, FakePaid(), {})
    with pytest.raises(ApprovalRequiredError):
        approve_paid_call(request, approved_usd=.3, approved_by="test")


def test_project_scope_is_not_interchangeable(project, tmp_path):
    from lib.budget import paid_execution
    other = tmp_path / "other"
    other.mkdir()
    (other / "project.json").write_text(json.dumps({"project_id": "other", "pipeline_type": "framework-smoke"}))
    tool = FakePaid()
    authorize(project, tool, {})
    with paid_execution(other), pytest.raises(ApprovalRequiredError):
        tool.execute({})
    tool.submit.assert_not_called()


@pytest.mark.parametrize("damage", ["corrupt", "moved", "identity"])
def test_infrastructure_failure_cannot_submit(project, damage):
    from lib.budget import paid_execution
    tool = FakePaid()
    authorize(project, tool, {})
    with paid_execution(project):
        if damage == "corrupt":
            (project / "cost_log.json").write_text("{")
        elif damage == "moved":
            data = json.loads((project / "cost_log.json").read_text())
            data["project"]["directory"] = "/wrong/project"
            (project / "cost_log.json").write_text(json.dumps(data))
        else:
            (project / "project.json").write_text("{}")
        with pytest.raises((ValueError, KeyError)):
            tool.execute({})
    tool.submit.assert_not_called()


def test_atomic_write_failure_preserves_old_log(tmp_path, monkeypatch):
    import lib.budget_transaction as transaction
    tracker = capped(tmp_path / "cost_log.json")
    entry = tracker.estimate("paid", "generate", .8)
    before = tracker.cost_log_path.read_bytes()
    replace = Mock(side_effect=OSError("disk error"))
    monkeypatch.setattr(transaction.os, "replace", replace)
    with pytest.raises(OSError):
        tracker.reserve(entry)
    assert tracker.cost_log_path.read_bytes() == before
    assert tracker.budget_reserved_usd == 0
    assert not list(tmp_path.glob("*.tmp"))


def test_deleted_ledger_is_not_silently_reset(tmp_path):
    tracker = capped(tmp_path / "cost_log.json")
    entry = tracker.estimate("paid", "generate", .8)
    tracker.reserve(entry)
    tracker.cost_log_path.unlink()
    with pytest.raises(ValueError):
        tracker.estimate("paid", "generate", .8)


def test_input_file_changes_invalidate_approval(project):
    from lib.budget import paid_execution
    source = project / "reference.txt"
    source.write_text("original")
    tool, inputs = FakePaid(), {"input_path": source}
    authorize(project, tool, inputs)
    source.write_text("changed")
    with paid_execution(project), pytest.raises(ApprovalRequiredError):
        tool.execute(inputs)
    tool.submit.assert_not_called()


def test_events_import_failure_does_not_bypass_governance(project, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "lib.events", None)
    tool = FakePaid()
    with pytest.raises(ApprovalRequiredError):
        tool.execute({})
    tool.submit.assert_not_called()


def test_nested_selector_governs_only_concrete_provider(project):
    from lib.budget import paid_execution

    class Selector(BaseTool):
        name = "test_selector"
        runtime = ToolRuntime.HYBRID
        delegates_paid_execution = True

        def execute(self, inputs):
            return provider.execute(inputs)

    provider = FakePaid()
    selector = Selector()
    with paid_execution(project), pytest.raises(ApprovalRequiredError):
        selector.execute({})
    provider.submit.assert_not_called()
    authorize(project, provider, {})
    with paid_execution(project):
        selector.execute({})
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    assert len(ledger.entries) == 1
    assert ledger.budget_spent_usd == .2


def test_paid_hybrid_has_same_gate_as_paid_api(project):
    from lib.budget import paid_execution

    class Hybrid(FakePaid):
        runtime = ToolRuntime.HYBRID

    tool = Hybrid()
    with pytest.raises(ApprovalRequiredError):
        tool.execute({})
    authorize(project, tool, {})
    with paid_execution(project):
        tool.execute({})
    assert tool.submit.call_count == 1


@pytest.mark.parametrize("runtime,provider", [
    (ToolRuntime.LOCAL, "local"), (ToolRuntime.LOCAL_GPU, "local"),
    (ToolRuntime.HYBRID, "local"), (ToolRuntime.API, "pexels"),
    (ToolRuntime.API, "pixabay_music"), (ToolRuntime.API, "freesound"),
])
def test_local_and_known_free_tools_need_no_paid_context(runtime, provider):
    tool = FakePaid()
    tool.runtime, tool.provider = runtime, provider
    tool.estimate_cost = lambda _: 0
    assert tool.execute({}).success
    tool.submit.assert_called_once()


def test_zero_estimate_does_not_make_paid_api_free():
    tool = FakePaid()
    with pytest.raises(ApprovalRequiredError):
        tool.execute({"amount": 0})
    tool.submit.assert_not_called()


def test_submission_id_is_durable_before_failure(project):
    from lib.budget import paid_execution, record_paid_submission
    tool = FakePaid()

    def submit(inputs):
        record_paid_submission("remote-123")
        ledger = CostTracker(cost_log_path=project / "cost_log.json")
        assert ledger.entries[0]["provider_request_id"] == "remote-123"
        raise TimeoutError("polling interrupted")

    tool.submit.side_effect = submit
    authorize(project, tool, {})
    with paid_execution(project), pytest.raises(TimeoutError):
        tool.execute({})
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    assert ledger.entries[0]["status"] == "unknown"
    assert ledger.entries[0]["provider_request_id"] == "remote-123"
    assert ledger.budget_reserved_usd == .2


def test_unknown_cannot_replace_accepted_job_id(tmp_path):
    tracker = CostTracker(
        cost_log_path=tmp_path / "cost_log.json",
        project={"directory": str(tmp_path), "project_id": "test", "pipeline_type": "framework-smoke"},
    )
    entry = tracker.estimate("paid", "generate", .2, request_hash="a" * 64)
    tracker.approve_entry(entry, request_hash="a" * 64, approved_usd=.2, approved_by="test")
    tracker.begin_execution("paid", "a" * 64, .2)
    tracker.record_submission(entry, "original")
    with pytest.raises(ValueError):
        tracker.mark_unknown(entry, "different")
    assert tracker.entries[0]["provider_request_id"] == "original"


def test_normalized_native_request_is_estimated_approved_and_executed(project):
    from lib.budget import paid_execution, prepare_paid_call, approve_paid_call

    class Native(FakePaid):
        def normalize_inputs(self, inputs):
            native = dict(inputs)
            native["amount"] = native.pop("count", native.get("amount", 1))
            native.setdefault("model", "explicit-default")
            return native

    tool = Native()
    request = prepare_paid_call(project, tool, {"count": 2})
    assert request.inputs == {
        "amount": 2, "model": "explicit-default", "project_dir": str(project.resolve()),
    }
    assert request.estimated_usd == 2
    approve_paid_call(request, approved_usd=2, approved_by="operator")
    with paid_execution(project):
        tool.execute({"count": 2})
    tool.submit.assert_called_once_with(request.inputs)


def test_legacy_policyless_ledger_is_not_silently_weakened(tmp_path):
    path = tmp_path / "cost_log.json"
    path.write_text(json.dumps({"version": "1.0", "entries": [], "budget_total_usd": 1}))
    with pytest.raises(ValueError, match="migration"):
        CostTracker(cost_log_path=path)


def test_symlinked_ledger_and_lock_fail_closed(tmp_path):
    target = tmp_path / "target.json"
    tracker = capped(target)
    alias = tmp_path / "cost_log.json"
    alias.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        capped(alias)
    lock = target.with_name(target.name + ".lock")
    lock.unlink()
    lock.symlink_to(tmp_path / "other.lock")
    with pytest.raises(ValueError, match="symlink"):
        tracker.estimate("paid", "generate", .8)


@pytest.mark.parametrize("value", [True, "0.2", None])
def test_money_is_numeric_not_a_coerced_flag_or_string(tmp_path, value):
    with pytest.raises(ValueError):
        BudgetConfig(total_usd=value)
    with pytest.raises(ValueError):
        capped(tmp_path / "cost_log.json").estimate("paid", "generate", value)


def test_caller_cannot_mutate_spend_through_entries_snapshot(tmp_path):
    tracker = capped(tmp_path / "cost_log.json")
    entry = tracker.estimate("paid", "generate", .8)
    tracker.reserve(entry)
    tracker.reconcile(entry, .8)
    tracker.entries[0].update(status="refunded", actual_usd=0)
    assert tracker.budget_spent_usd == .8


def test_reservation_persistence_failure_prevents_dispatch(project, monkeypatch):
    from lib.budget import paid_execution
    import lib.budget_transaction as transaction
    tool = FakePaid()
    authorize(project, tool, {})
    with paid_execution(project):
        monkeypatch.setattr(transaction.os, "replace", Mock(side_effect=OSError("disk full")))
        with pytest.raises(OSError):
            tool.execute({})
    tool.submit.assert_not_called()


@pytest.mark.parametrize("delivery_failure", [False, True])
def test_real_openai_adapter_governance_with_fake_submission(project, monkeypatch, delivery_failure):
    import base64
    from types import SimpleNamespace
    import openai
    from lib.budget import paid_execution
    from lib.provider_jobs import ProviderJob
    from tools.graphics.openai_image import OpenAIImage

    client = Mock()
    client.images.generate.return_value = SimpleNamespace(data=[
        SimpleNamespace(b64_json=base64.b64encode(b"offline-image").decode()),
    ])
    monkeypatch.setattr(openai, "OpenAI", Mock(return_value=client))
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-not-a-credential")
    if delivery_failure:
        monkeypatch.setattr(ProviderJob, "deliver", Mock(side_effect=OSError("disk full")))
    tool = OpenAIImage()
    # The context/approval project must reach the real provider journal without
    # requiring duplicate project_dir metadata in the caller's input dictionary.
    inputs = {"output_path": str(project / "image.png"), "prompt": "test"}
    authorize(project, tool, inputs)
    with paid_execution(project):
        result = tool.execute(inputs)
    assert result.success is not delivery_failure
    client.images.generate.assert_called_once()
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    # These adapters explicitly report estimates, not settled billing. Delivery
    # success does not turn an uncertain generation charge into known spend.
    assert ledger.budget_reserved_usd == .211
    assert ledger.budget_spent_usd == 0


@pytest.mark.parametrize("state", ["completed", "failed", "refunded"])
def test_terminal_entries_cannot_be_reserved_again(tmp_path, state):
    tracker = capped(tmp_path / "cost_log.json")
    entry = tracker.estimate("paid", "generate", .2)
    tracker.reserve(entry)
    if state == "refunded":
        tracker.refund(entry)
        tracker.refund(entry)
    else:
        tracker.reconcile(entry, .2, success=state == "completed")
    with pytest.raises(ValueError):
        tracker.reserve(entry)


def test_estimate_cannot_skip_reservation(tmp_path):
    tracker = capped(tmp_path / "cost_log.json")
    entry = tracker.estimate("paid", "generate", .2)
    with pytest.raises(ValueError):
        tracker.reconcile(entry, .2)


def test_recovery_reuses_unknown_reservation_without_second_charge(project):
    from lib.budget import paid_execution

    class Recoverable(FakePaid):
        def validate_paid_recovery(self, inputs):
            if inputs.get("recovery_id") != "verified-existing-job":
                raise ValueError("unknown recovery job")

    tool = Recoverable(ToolResult(success=False))
    request = authorize(project, tool, {"prompt": "test"})
    with paid_execution(project):
        tool.execute({"prompt": "test"})
    tool.submit.return_value = ToolResult(success=True, cost_usd=.2)
    with paid_execution(project, resume_entry_id=request.entry_id):
        result = tool.execute({"prompt": "test", "recovery_id": "verified-existing-job"})
    assert result.cost_entry_id == request.entry_id
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    assert len(ledger.entries) == 1
    assert ledger.budget_spent_usd == .2
    assert ledger.budget_reserved_usd == 0
    # Re-delivering a settled generation does not record a second generation.
    with paid_execution(project, resume_entry_id=request.entry_id):
        tool.execute({"prompt": "test", "recovery_id": "verified-existing-job"})
    assert ledger.budget_spent_usd == .2


def test_recovery_requires_explicit_provider_verification(project):
    from lib.budget import paid_execution
    tool = FakePaid(ToolResult(success=False))
    request = authorize(project, tool, {})
    with paid_execution(project):
        tool.execute({})
    with paid_execution(project, resume_entry_id=request.entry_id), pytest.raises(ValueError):
        tool.execute({"recovery_id": "made-up"})
    assert tool.submit.call_count == 1


def test_recovery_inputs_cannot_receive_new_generation_approval(project):
    from lib.budget import prepare_paid_call
    with pytest.raises(ApprovalRequiredError):
        prepare_paid_call(project, FakePaid(), {"recovery_id": "already-submitted"})


def test_explicit_estimate_is_not_settled_billing_evidence(project):
    from lib.budget import paid_execution
    tool = FakePaid(ToolResult(success=True, cost_usd=.2, cost_status="estimated"))
    authorize(project, tool, {})
    with paid_execution(project):
        tool.execute({})
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    assert ledger.budget_spent_usd == 0
    assert ledger.budget_reserved_usd == .2


@pytest.mark.parametrize("mode", list(BudgetMode))
def test_real_paid_execution_enforces_cap_even_in_legacy_diagnostic_modes(project, mode):
    from lib.budget import paid_execution
    CostTracker(
        cost_log_path=project / "cost_log.json", budget_total_usd=1,
        reserve_pct=0, mode=mode,
        project={"directory": str(project.resolve()), "project_id": "project", "pipeline_type": "framework-smoke"},
    )
    tool = FakePaid()
    authorize(project, tool, {"amount": 2})
    with paid_execution(project), pytest.raises(BudgetExceededError):
        tool.execute({"amount": 2})
    tool.submit.assert_not_called()


def _claim_in_process(path, ready, start, outcomes):
    tracker = CostTracker(cost_log_path=Path(path))
    ready.put(True)
    start.wait(15)
    try:
        tracker.begin_execution("fake_paid", "a" * 64, .2)
    except ApprovalRequiredError:
        outcomes.put("blocked")
    else:
        outcomes.put("claimed")


def test_exact_approval_can_be_claimed_by_only_one_process(project):
    path = project / "cost_log.json"
    tracker = CostTracker(
        cost_log_path=path,
        project={"directory": str(project.resolve()), "project_id": "project", "pipeline_type": "framework-smoke"},
    )
    entry = tracker.estimate("fake_paid", "generate", .2, request_hash="a" * 64)
    tracker.approve_entry(entry, request_hash="a" * 64, approved_usd=.2, approved_by="operator")
    context = multiprocessing.get_context("spawn")
    ready, outcomes, start = context.Queue(), context.Queue(), context.Event()
    workers = [context.Process(target=_claim_in_process, args=(str(path), ready, start, outcomes))
               for _ in range(2)]
    try:
        for worker in workers:
            worker.start()
        for _ in workers:
            ready.get(timeout=20)
        start.set()
        assert sorted(outcomes.get(timeout=20) for _ in workers) == ["blocked", "claimed"]
        for worker in workers:
            worker.join(20)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(5)
    assert tracker.budget_reserved_usd == .2


@pytest.mark.parametrize("inputs", [{"output_path": "/outside.png"}, {"project_dir": "/other/project"}])
def test_project_paths_cannot_escape_approved_scope(project, inputs):
    from lib.budget import prepare_paid_call
    with pytest.raises(ApprovalRequiredError):
        prepare_paid_call(project, FakePaid(), inputs)


@pytest.mark.parametrize("success", [False, True])
@pytest.mark.parametrize("field_status", ["unknown", "estimated", "reported"])
def test_explicit_unknown_data_metadata_always_retains_hold(project, success, field_status):
    from lib.budget import paid_execution
    tool = FakePaid(ToolResult(
        success=success, cost_usd=.2, cost_status=field_status,
        data={"cost_status": "unknown", "remote_task_id": "accepted-123", "recovery_state": "pending"},
    ))
    authorize(project, tool, {})
    with paid_execution(project):
        tool.execute({})
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    assert ledger.budget_reserved_usd == .2
    assert ledger.budget_spent_usd == 0
    assert ledger.entries[0]["status"] == "unknown"
    assert ledger.entries[0]["provider_request_id"] == "accepted-123"
    assert "recovery_state" not in ledger.entries[0]


@pytest.mark.parametrize("success", [False, True])
@pytest.mark.parametrize("actual", [0, .15])
def test_known_data_metadata_reconciles_reported_cost(project, success, actual):
    from lib.budget import paid_execution
    tool = FakePaid(ToolResult(
        success=success, cost_usd=actual,
        data={"cost_status": "known", "remote_task_id": "accepted-123"},
    ))
    authorize(project, tool, {})
    with paid_execution(project):
        tool.execute({})
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    assert ledger.budget_reserved_usd == 0
    assert ledger.budget_spent_usd == actual
    assert ledger.entries[0]["status"] == ("completed" if success else "failed")
    assert ledger.entries[0]["provider_request_id"] == "accepted-123"


def test_conflicting_remote_identity_metadata_does_not_release_hold(project):
    from lib.budget import paid_execution
    tool = FakePaid(ToolResult(
        success=True, cost_usd=.2, provider_request_id="original",
        data={"cost_status": "known", "remote_task_id": "different"},
    ))
    authorize(project, tool, {})
    with paid_execution(project), pytest.raises(ValueError):
        tool.execute({})
    assert CostTracker(cost_log_path=project / "cost_log.json").budget_reserved_usd == .2


def test_project_context_is_injected_before_normalization_and_estimation(project):
    from lib.budget import approve_paid_call, paid_execution, prepare_paid_call

    class ProjectAware(FakePaid):
        def normalize_inputs(self, inputs):
            assert inputs["project_dir"] == str(project.resolve())
            return dict(inputs)

        def estimate_cost(self, inputs):
            assert inputs["project_dir"] == str(project.resolve())
            return .2

    tool = ProjectAware()
    request = prepare_paid_call(project, tool, {"prompt": "test"})
    assert request.inputs["project_dir"] == str(project.resolve())
    approve_paid_call(request, approved_usd=.2, approved_by="operator")
    with paid_execution(project):
        tool.execute({"prompt": "test"})
    tool.submit.assert_called_once_with(request.inputs)


def test_conflicting_explicit_project_is_not_silently_overwritten(project, tmp_path):
    from lib.budget import paid_execution
    tool = FakePaid()
    authorize(project, tool, {})
    with paid_execution(project), pytest.raises(ApprovalRequiredError):
        tool.execute({"project_dir": str(tmp_path / "different-project")})
    tool.submit.assert_not_called()


def test_submission_hook_rejects_unscoped_use():
    from lib.budget import record_paid_submission
    with pytest.raises(ApprovalRequiredError):
        record_paid_submission("accepted-without-governance")


@pytest.mark.parametrize("success", [False, True])
def test_submission_hook_is_idempotent_during_settled_recovery(project, success):
    from lib.budget import paid_execution, record_paid_submission

    class Recoverable(FakePaid):
        def validate_paid_recovery(self, inputs):
            assert inputs["recovery_id"] == "existing-job"

    tool = Recoverable()

    def submitted(inputs):
        record_paid_submission("remote-123")
        return ToolResult(success=success, cost_usd=.2, cost_status="reported")

    tool.submit.side_effect = submitted
    request = authorize(project, tool, {})
    with paid_execution(project):
        tool.execute({})
    with paid_execution(project, resume_entry_id=request.entry_id):
        tool.execute({"recovery_id": "existing-job"})
    ledger = CostTracker(cost_log_path=project / "cost_log.json")
    assert ledger.budget_spent_usd == .2
    assert ledger.budget_reserved_usd == 0
    assert len(ledger.entries) == 1
    assert ledger.entries[0]["provider_request_id"] == "remote-123"
    with pytest.raises(ValueError):
        ledger.record_submission(request.entry_id, "different-job")
