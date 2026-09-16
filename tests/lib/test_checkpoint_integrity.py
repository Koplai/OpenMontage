"""Audited checkpoint identity, manifest, and transaction regressions."""

import json
import multiprocessing
from concurrent.futures import ThreadPoolExecutor

import pytest

from lib.checkpoint import (
    CheckpointValidationError, get_completed_stages, get_next_stage,
    init_project, read_checkpoint, validate_checkpoint, write_checkpoint,
)
from tests.contracts.test_phase0_contracts import sample_artifact
from lib.pipeline_loader import list_pipelines, load_pipeline


def decision_log(project_id="run", decision_id="d1"):
    return {
        "version": "1.0", "project_id": project_id,
        "decisions": [{
            "decision_id": decision_id, "stage": "research",
            "category": "approval_policy", "subject": "Approval policy",
            "options_considered": [{
                "option_id": "guided", "label": "Guided", "score": 1,
                "reason": "Human requested per-stage approval",
            }],
            "selected": "guided", "reason": "Human requested it",
        }],
    }


def _write_decision_process(root, index):
    write_checkpoint(root, "run", "research", "in_progress",
                     {"decision_log": decision_log(decision_id=f"process-{index}")})


@pytest.mark.parametrize("pipeline", ["unknown", "not-a-pipeline", "screen-demo"])
def test_initialized_identity_cannot_be_overridden(tmp_path, pipeline):
    project = init_project("run", title="Run", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    before = (project / "project.json").read_bytes()
    with pytest.raises(CheckpointValidationError):
        write_checkpoint(tmp_path, "run", "script", "completed",
                         {"script": sample_artifact("script")}, pipeline_type=pipeline)
    with pytest.raises(CheckpointValidationError):
        init_project("run", title="Changed", pipeline_type=pipeline, pipeline_dir=tmp_path)
    assert (project / "project.json").read_bytes() == before
    assert not (project / "checkpoint_script.json").exists()


def test_resume_infers_actual_pipeline_and_done(tmp_path):
    init_project("screen", title="Screen", pipeline_type="screen-demo", pipeline_dir=tmp_path)
    assert get_next_stage(tmp_path, "screen") == "idea"
    init_project("run", title="Run", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    for stage, artifact in [("research", "research_brief"), ("script", "script")]:
        write_checkpoint(tmp_path, "run", stage, "completed",
                         {artifact: sample_artifact(artifact)}, human_approved=True)
    assert get_next_stage(tmp_path, "run") is None


@pytest.mark.parametrize("pipeline_type", sorted(list_pipelines()))
def test_every_pipeline_resumes_at_its_first_required_stage(tmp_path, pipeline_type):
    init_project("run", title="Run", pipeline_type=pipeline_type, pipeline_dir=tmp_path)
    expected = next(
        stage["name"] for stage in load_pipeline(pipeline_type)["stages"]
        if stage.get("checkpoint_required", True)
    )
    assert get_next_stage(tmp_path, "run") == expected


@pytest.mark.parametrize("field,value", [
    ("project_id", "foreign"), ("pipeline_type", "cinematic"),
    ("stage", "script"), ("human_approved", False),
])
def test_resume_rejects_foreign_or_unapproved_completion(tmp_path, field, value):
    init_project("run", title="Run", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    path = write_checkpoint(tmp_path, "run", "research", "completed",
                            {"research_brief": sample_artifact("research_brief")},
                            human_approved=True)
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(CheckpointValidationError):
        get_completed_stages(tmp_path, "run")


def test_optional_predecessor_omission_does_not_block(tmp_path):
    init_project("run", title="Run", pipeline_type="animated-explainer", pipeline_dir=tmp_path)
    assert get_next_stage(tmp_path, "run") == "proposal"
    write_checkpoint(tmp_path, "run", "proposal", "completed", {
        "proposal_packet": sample_artifact("proposal_packet"),
        "decision_log": decision_log(),
    }, human_approved=True)
    assert get_next_stage(tmp_path, "run") == "script"


def test_present_but_incomplete_optional_predecessor_still_blocks(tmp_path):
    init_project("run", title="Run", pipeline_type="animated-explainer", pipeline_dir=tmp_path)
    write_checkpoint(tmp_path, "run", "research", "in_progress", {})
    with pytest.raises(CheckpointValidationError, match="PREREQUISITE"):
        write_checkpoint(tmp_path, "run", "proposal", "completed", {
            "proposal_packet": sample_artifact("proposal_packet"),
            "decision_log": decision_log(),
        }, human_approved=True)


def test_invalid_log_changes_no_files_or_callers_artifacts(tmp_path):
    project = init_project("run", title="Run", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    artifacts = {"decision_log": {"version": "1.0", "project_id": "run", "decisions": [{}]}}
    original = json.dumps(artifacts)
    with pytest.raises(CheckpointValidationError):
        write_checkpoint(tmp_path, "run", "research", "in_progress", artifacts)
    assert json.dumps(artifacts) == original
    assert {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert not (project / "decision_log.json").exists()


def test_concurrent_decisions_are_serialized_without_loss(tmp_path):
    init_project("run", title="Run", pipeline_type="framework-smoke", pipeline_dir=tmp_path)

    def write(index):
        write_checkpoint(tmp_path, "run", "research", "in_progress",
                         {"decision_log": decision_log(decision_id=f"d{index}")})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(8)))
    cumulative = json.loads((tmp_path / "run" / "decision_log.json").read_text())
    assert {d["decision_id"] for d in cumulative["decisions"]} == {f"d{i}" for i in range(8)}
    assert read_checkpoint(tmp_path, "run", "research")["status"] == "in_progress"


def test_separate_process_writers_do_not_lose_decisions(tmp_path):
    init_project("run", title="Run", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    processes = [
        multiprocessing.get_context("spawn").Process(
            target=_write_decision_process, args=(tmp_path, index)
        ) for index in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        if process.is_alive():
            process.terminate()
            process.join()
            pytest.fail("Checkpoint process did not finish")
        assert process.exitcode == 0
    cumulative = json.loads((tmp_path / "run" / "decision_log.json").read_text())
    assert {d["decision_id"] for d in cumulative["decisions"]} == {
        f"process-{index}" for index in range(4)
    }


def test_interrupted_log_checkpoint_commit_recovers_before_read(tmp_path, monkeypatch):
    import lib.checkpoint as checkpoint

    project = init_project("run", title="Run", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    real_atomic_json = checkpoint._atomic_json

    def interrupt(path, data):
        if path.name == "checkpoint_research.json":
            raise OSError("simulated interruption after log commit")
        real_atomic_json(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(checkpoint, "_atomic_json", interrupt)
        with pytest.raises(OSError, match="interruption"):
            write_checkpoint(tmp_path, "run", "research", "in_progress",
                             {"decision_log": decision_log()})
    assert (project / ".checkpoint-transaction.json").exists()
    recovered = read_checkpoint(tmp_path, "run", "research")
    cumulative = json.loads((project / "decision_log.json").read_text())
    assert recovered["artifacts"]["decision_log"] == cumulative
    assert not (project / ".checkpoint-transaction.json").exists()


def test_invalid_recovery_log_is_rejected_before_mutating_files(tmp_path):
    project = init_project("run", title="Run", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    path = write_checkpoint(tmp_path, "run", "research", "in_progress", {})
    checkpoint_bytes = path.read_bytes()
    journal = project / ".checkpoint-transaction.json"
    journal.write_text(json.dumps({
        "checkpoint": json.loads(checkpoint_bytes),
        "decision_log": {"version": "1.0", "project_id": "run", "decisions": [{}]},
    }))
    with pytest.raises(CheckpointValidationError, match="pending checkpoint transaction"):
        read_checkpoint(tmp_path, "run", "research")
    assert path.read_bytes() == checkpoint_bytes
    assert not (project / "decision_log.json").exists()
    assert journal.exists()


@pytest.mark.parametrize("defect", ["foreign_log", "conflicting_id", "invalid_status"])
def test_rejected_transaction_preserves_existing_checkpoint_and_log(tmp_path, defect):
    project = init_project("run", title="Run", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    write_checkpoint(tmp_path, "run", "research", "in_progress",
                     {"decision_log": decision_log()})
    before = {p.name: p.read_bytes() for p in project.iterdir() if p.is_file()}
    log = decision_log("other" if defect == "foreign_log" else "run")
    if defect == "conflicting_id":
        log["decisions"][0]["reason"] = "Silently changed history"
    with pytest.raises(CheckpointValidationError):
        write_checkpoint(tmp_path, "run", "research",
                         "invalid" if defect == "invalid_status" else "in_progress",
                         {"decision_log": log})
    assert {p.name: p.read_bytes() for p in project.iterdir() if p.is_file()} == before


@pytest.mark.parametrize("review_status", [None, "revise", "fail", "pass"])
def test_completed_compose_requires_exact_passing_review(tmp_path, review_status):
    from tests.tools.test_export_bundle import _make_video, _review

    video = tmp_path / "final.mp4"
    _make_video(video)
    review = _review(video)
    report = {"version": "1.0", "outputs": [{
        "path": str(video), "sha256": review["output_sha256"], "format": "mp4",
        "resolution": "64x64", "duration_seconds": 1,
    }]}
    artifacts = {"render_report": report}
    if review_status:
        artifacts["final_review"] = {**review, "status": review_status}
    cp = {
        "version": "1.0", "project_id": "run", "pipeline_type": "screen-demo",
        "stage": "compose", "status": "completed",
        "timestamp": "2026-09-16T09:00:00Z", "artifacts": artifacts,
    }
    if review_status == "pass":
        validate_checkpoint(cp)
        video.write_bytes(video.read_bytes() + b"changed")
    with pytest.raises(CheckpointValidationError):
        validate_checkpoint(cp)
