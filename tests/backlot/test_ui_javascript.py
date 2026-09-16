"""Run real UI helper JavaScript without a browser or npm dependencies."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def test_ui_reliability_javascript():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for Backlot JavaScript tests")
    subprocess.run(
        [node, str(Path(__file__).with_name("ui_reliability.mjs"))],
        check=True, timeout=20,
    )


def test_screenshot_helper_import_has_no_environment_or_filesystem_side_effects(tmp_path):
    import sys
    subprocess.run([
        sys.executable, "-c",
        "import os; from pathlib import Path; "
        "before = dict(os.environ); "
        "from scripts import backlot_screenshot_stage as helper; "
        "assert dict(os.environ) == before; "
        "assert not Path(os.environ['OPENMONTAGE_PROJECTS_DIR']).exists()",
    ], check=True, timeout=20, env={
        **os.environ, "OPENMONTAGE_PROJECTS_DIR": str(tmp_path / "untouched"),
    })
