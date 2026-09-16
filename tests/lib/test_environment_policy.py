import json
import os
import subprocess
from pathlib import Path

import pytest

from lib.env_loader import dotenv_value_allowed, load_env, require_env


def test_project_env_cannot_control_process_or_endpoints(tmp_path, monkeypatch, caplog):
    for key in ("PATH", "PYTHONPATH", "OPENAI_BASE_URL", "GOOGLE_APPLICATION_CREDENTIALS", "UNKNOWN_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "PATH=/attacker\nPYTHONPATH=/attacker\nOPENAI_BASE_URL=https://invalid.example\n"
        "GOOGLE_APPLICATION_CREDENTIALS=/attacker.json\nUNKNOWN_KEY=never-log-this\n"
        "FAL_KEY=fixture-only\n",
        encoding="utf-8",
    )
    load_env(tmp_path)
    assert os.environ["FAL_KEY"] == "fixture-only"
    assert all(key not in os.environ for key in (
        "PATH", "PYTHONPATH", "OPENAI_BASE_URL", "GOOGLE_APPLICATION_CREDENTIALS", "UNKNOWN_KEY",
    ))
    assert "Ignoring project .env variable" in caplog.text
    assert "never-log-this" not in caplog.text


def test_launcher_wins_and_interpolation_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "launcher-fixture")
    monkeypatch.setenv("FAL_KEY", " ")
    monkeypatch.setenv("PRIVATE_FIXTURE", "must-not-expand")
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=project-fixture\nFAL_KEY='${PRIVATE_FIXTURE}'\n", encoding="utf-8"
    )
    load_env(tmp_path)
    assert os.environ["OPENAI_API_KEY"] == "launcher-fixture"
    assert os.environ["FAL_KEY"] == "${PRIVATE_FIXTURE}"


@pytest.mark.parametrize("value", ["example.invalid#", "eastus/../../", "eastus\x00other"])
def test_reject_invalid_region(value):
    assert not dotenv_value_allowed("AZURE_SPEECH_REGION", value)


def test_reject_blank_required_variable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", " \t")
    with pytest.raises(EnvironmentError):
        require_env("OPENAI_API_KEY")


def test_javascript_loader_uses_same_policy(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / ".agents/skills/hyperframes-media/scripts/lib/heygen.mjs"
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("HEYGEN_CONFIG_DIR", raising=False)
    (tmp_path / ".env").write_text(
        "FAL_KEY=fixture # comment\nHEYGEN_CONFIG_DIR=/untrusted\nAZURE_SPEECH_REGION=bad#host\n",
        encoding="utf-8",
    )
    probe = (
        f"import {{loadEnvFromDir}} from {json.dumps(script.as_uri())};"
        "loadEnvFromDir(process.argv[1]);"
        "console.log(JSON.stringify({key:process.env.FAL_KEY,dir:process.env.HEYGEN_CONFIG_DIR}));"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", probe, str(tmp_path)], capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout) == {"key": "fixture"}
    assert "HEYGEN_CONFIG_DIR" in result.stderr
