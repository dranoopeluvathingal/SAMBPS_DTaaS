"""tests/test_phase0_smoke.py
==============================

Wraps ``matlab/run_phase0_smoke.m`` via ``matlab -batch ...`` so the
Phase-0 smoke test runs in the same pytest harness as the Python
unit tests.  Skipped when MATLAB is not on PATH (typical on the
lead-engineer dev box during early Phase 0; the canonical run is in
the CI MATLAB job, which provisions a licensed MATLAB).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJ_ROOT = Path(__file__).resolve().parent.parent
MATLAB = shutil.which("matlab")


@pytest.mark.skipif(MATLAB is None, reason="MATLAB not on PATH")
def test_phase0_smoke_via_matlab_batch() -> None:
    """Run ``matlab -batch run_phase0_smoke`` and assert exit code 0."""
    cmd = [
        MATLAB,
        "-batch",
        "addpath('matlab'); run_phase0_smoke",
    ]
    result = subprocess.run(
        cmd,
        cwd=PROJ_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, (
        f"matlab -batch run_phase0_smoke exited with code "
        f"{result.returncode}\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    assert "PHASE0 SMOKE: PASS" in result.stdout, (
        "expected 'PHASE0 SMOKE: PASS' line in matlab stdout, got:\n"
        f"{result.stdout}"
    )
