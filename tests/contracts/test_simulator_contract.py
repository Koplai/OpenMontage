import json
import sys

import pytest

from scripts import backlot_simulate_run


def test_simulator_preserves_existing_project(tmp_path, monkeypatch):
    project = tmp_path / "demo"
    project.mkdir()
    sentinel = project / "keep.txt"
    sentinel.write_text("existing work")
    monkeypatch.setattr(backlot_simulate_run, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["simulate", "--project", "demo", "--fast"])
    with pytest.raises(SystemExit):
        backlot_simulate_run.main()
    assert sentinel.read_text() == "existing work"


def test_simulator_rejects_path_as_identifier(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["simulate", "--project", "../outside"])
    with pytest.raises(SystemExit):
        backlot_simulate_run.main()


def test_simulator_writes_proposal_before_script(tmp_path, monkeypatch):
    monkeypatch.setattr(backlot_simulate_run, "PROJECTS_DIR", tmp_path)
    real_init = backlot_simulate_run.init_project
    monkeypatch.setattr(
        backlot_simulate_run, "init_project",
        lambda *args, **kwargs: real_init(*args, pipeline_dir=tmp_path, **kwargs),
    )
    monkeypatch.setattr(backlot_simulate_run.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(sys, "argv", ["simulate", "--project", "demo", "--fast"])
    assert backlot_simulate_run.main() == 0
    project = tmp_path / "demo"
    proposal = json.loads((project / "checkpoint_proposal.json").read_text())
    assert proposal["status"] == "completed"
    assert proposal["human_approved"] is True
    assert "decision_log" in proposal["artifacts"]
    assert (project / "checkpoint_script.json").is_file()
