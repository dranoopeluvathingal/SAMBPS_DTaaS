"""
conftest.py — shared pytest fixtures for the SAMBP Digital Twin Lab test suite.
"""
from __future__ import annotations

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Parametrised axes
# ---------------------------------------------------------------------------

IBR_TYPES = ["SG", "DFIG", "GFM", "GFL", "PV"]
FAULT_TYPES = ["SLG", "LL", "DLG", "3PH"]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "tier1: fast unit tests (< 1 s each)")
    config.addinivalue_line("markers", "tier2: integration tests (1–30 s each)")
    config.addinivalue_line("markers", "tier3: heavy Monte Carlo / HIL tests (> 30 s)")


# ---------------------------------------------------------------------------
# Signal fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_3phase_signal() -> dict:
    """Return 2-cycle, 4000 Sa/s three-phase sinusoidal signal at 50 Hz."""
    fs = 4000          # samples per second
    f0 = 50.0          # fundamental frequency (Hz)
    n_cycles = 2
    t = np.arange(0, n_cycles / f0, 1 / fs)
    phi = 2 * np.pi * f0 * t
    return {
        "t": t,
        "ia": np.sin(phi),
        "ib": np.sin(phi - 2 * np.pi / 3),
        "ic": np.sin(phi + 2 * np.pi / 3),
        "fs": fs,
        "f0": f0,
    }


@pytest.fixture
def sample_fault_scenario() -> dict:
    """Minimal fault scenario dict compatible with ScenarioLibrary format."""
    return {
        "fault_type": "SLG",
        "k_ibr": 0.15,
        "location_pu": 0.5,
        "Rf_pu": 0.0,
        "pre_fault_cycles": 2,
        "post_fault_cycles": 5,
        "ibr_type": "GFL",
        "expected_decision": "TRIP",
    }


# ---------------------------------------------------------------------------
# Engine fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def dt_engine_instance():
    """
    Lightweight Digital Twin engine stub.

    Returns a namespace object with the core sub-systems instantiated so that
    individual tests can import and exercise them without running a full
    simulation loop.
    """
    from types import SimpleNamespace

    from digital_twin.estimation.phasor_dft import PhasorDFT
    from digital_twin.models.protection_mirror import ProtectionMirror
    from digital_twin.models.scenario_library import ScenarioLibrary

    return SimpleNamespace(
        phasor=PhasorDFT(fs=4000, f0=50.0),
        mirror=ProtectionMirror(),
        library=ScenarioLibrary(),
    )


# ---------------------------------------------------------------------------
# Parametrised fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(params=IBR_TYPES)
def ibr_type(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture(params=FAULT_TYPES)
def fault_type(request: pytest.FixtureRequest) -> str:
    return request.param
