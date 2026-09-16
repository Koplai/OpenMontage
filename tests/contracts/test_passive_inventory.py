import subprocess
import types

from tools.base_tool import BaseTool, ToolResult
from tools.tool_registry import ToolRegistry
import tools.tool_registry as registry_module


class PassiveFixture(BaseTool):
    name = "passive-fixture"
    dependencies = ["env:OPENMONTAGE_FIXTURE_KEY", "cmd:missing-command-fixture"]

    def execute(self, inputs):
        return ToolResult(success=True)

    def get_info(self):
        raise AssertionError("Inventory must not call get_info")

    def get_status(self):
        raise AssertionError("Inventory must not run status probes")


def test_inventory_never_probes_or_prints_secrets(monkeypatch):
    registry = ToolRegistry()
    registry.register(PassiveFixture())
    registry._discovered_packages.add("tools")
    monkeypatch.setenv("OPENMONTAGE_FIXTURE_KEY", "must-not-be-exposed")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("subprocess")))
    result = registry.configuration_inventory()
    assert result["tools"][0]["configuration_status"] == "missing"
    assert result["tools"][0]["runtime_verified"] is False
    assert "must-not-be-exposed" not in str(result)


def test_discovery_keeps_healthy_modules_and_reports_missing_import(monkeypatch, caplog):
    registry = ToolRegistry()
    package = types.ModuleType("fixture_tools")
    package.__path__ = ["fixture"]
    good = types.ModuleType("fixture_tools.good")

    def import_module(name):
        if name == "fixture_tools":
            return package
        if name.endswith(".bad"):
            raise ImportError("optional fixture dependency missing")
        return good

    monkeypatch.setattr(
        registry_module.pkgutil, "walk_packages",
        lambda *args, **kwargs: [types.SimpleNamespace(name="fixture_tools.bad"), types.SimpleNamespace(name="fixture_tools.good")],
    )
    monkeypatch.setattr(registry_module.importlib, "import_module", import_module)
    visited = []
    monkeypatch.setattr(registry, "register_module", lambda module: visited.append(module.__name__) or [])
    registry.discover("fixture_tools")
    assert visited == ["fixture_tools.good"]
    assert "fixture_tools.bad" in registry.discovery_errors
    assert "optional fixture dependency missing" in caplog.text
