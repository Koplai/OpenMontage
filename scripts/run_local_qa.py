"""Run zero-key diagnostics in an isolated output directory with bounded execution."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

SCRIPTS = (
    "test_04_audio_mix.py",
    "test_05_video_compose.py",
    "test_06_video_stitch.py",
    "test_07_playbook_intelligence.py",
    "test_08_end_to_end.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", action="append", choices=SCRIPTS)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with TemporaryDirectory(prefix="openmontage-qa-") as output:
        env = dict(os.environ, OPENMONTAGE_QA_OUTPUT_DIR=output, OPENMONTAGE_ALLOW_NETWORK="0")
        for script in args.script or SCRIPTS:
            print(f"Running {script}", flush=True)
            result = subprocess.run([sys.executable, str(root / "tests/qa" / script)], env=env, timeout=600)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
