import ast
from pathlib import Path
import re
import sys
import types

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
import pytest

from scripts import run_local_qa
from tests.qa.conftest import collect_ignore

ROOT = Path(__file__).resolve().parents[2]


def test_legacy_diagnostics_are_not_collected_as_tests():
    assert set(collect_ignore) == set(run_local_qa.SCRIPTS)


def test_failed_semantic_qa_check_is_an_error():
    path = ROOT / "tests/qa/test_08_end_to_end.py"
    tree = ast.parse(path.read_text())
    check = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "check")
    enforcement = tree.body[-1]
    namespace = {"PASS": 0, "FAIL": 0}
    exec(compile(ast.Module(body=[check], type_ignores=[]), str(path), "exec"), namespace)
    namespace["check"]("deliberately failed fixture", False)
    with pytest.raises(SystemExit) as raised:
        exec(compile(ast.Module(body=[enforcement], type_ignores=[]), str(path), "exec"), namespace)
    assert raised.value.code == 1


def test_qa_runner_stops_on_failure_and_cleans_fixture_workspace(monkeypatch):
    observed = []

    def fail(command, *, env, timeout):
        observed.append(Path(env["OPENMONTAGE_QA_OUTPUT_DIR"]))
        assert observed[-1].is_dir()
        assert env["OPENMONTAGE_ALLOW_NETWORK"] == "0"
        assert timeout == 600
        return types.SimpleNamespace(returncode=7)

    monkeypatch.setattr(sys, "argv", ["run_local_qa"])
    monkeypatch.setattr(run_local_qa.subprocess, "run", fail)
    assert run_local_qa.main() == 7
    assert len(observed) == 1
    assert not observed[0].exists()


def _pins(path):
    return {
        canonicalize_name(name): version
        for name, version in re.findall(
            r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==(\S+) \\",
            path.read_text(), flags=re.MULTILINE,
        )
    }


@pytest.mark.parametrize("manifest,lock", [
    ("requirements.txt", "requirements.lock"),
    ("requirements-dev.txt", "requirements-dev.lock"),
])
def test_lock_covers_declared_requirements(manifest, lock):
    pins = _pins(ROOT / lock)
    assert pins
    for line in (ROOT / manifest).read_text().splitlines():
        spec = line.split("#", 1)[0].strip()
        if not spec or spec.startswith("-r"):
            continue
        requirement = Requirement(spec)
        version = pins[canonicalize_name(requirement.name)]
        assert requirement.specifier.contains(version), f"{requirement} incompatible with {version}"


def test_development_and_runtime_resolve_shared_packages_identically():
    runtime = _pins(ROOT / "requirements.lock")
    development = _pins(ROOT / "requirements-dev.lock")
    assert {name: development[name] for name in runtime} == runtime
