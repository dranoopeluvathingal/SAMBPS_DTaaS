"""Smoke tests for every module under topologies/.

For each `<name>.py` in the sibling `topologies/` directory:

  1. Import the module dynamically (importlib).
  2. Call `<name>.build()`.
  3. Assert it returns a fs_mpc_mg.cmc.Topology with at least one ICA.
  4. Assert each ICA's `bus_id` refers to a bus actually in the topology.
  5. Assert each LoadNode's `bus_id` refers to a real bus.
  6. If any bus has `is_grid=True`, assert `topology.grid_tie_switch()`
     returns a non-None SwitchEdge.

This is a smoke test, not a deep validation — line impedances, daily
profiles, residential vs industrial profiles, and every other
topology-specific detail are not checked here. Catches regressions
where a topology stub gets corrupted (typo'd bus reference, missing
grid tie, empty `Topology()` returned, etc.).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# `topologies/` lives one level up from `fs_mpc_microgrid/`. Add it to sys.path
# so `importlib.import_module("ieee_33_bus")` works even though the directory
# isn't a package (no __init__.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOPOLOGY_DIR = _REPO_ROOT / "topologies"
sys.path.insert(0, str(_TOPOLOGY_DIR))

from fs_mpc_mg.cmc.topology import Topology, SwitchEdge


def _discover_topology_modules() -> list[str]:
    """List importable module names in `topologies/` (excluding __init__ and dotfiles)."""
    if not _TOPOLOGY_DIR.exists():
        return []
    return sorted(
        f.stem for f in _TOPOLOGY_DIR.glob("*.py")
        if not f.stem.startswith("_") and f.stem != "__init__"
    )


TOPOLOGY_MODULES = _discover_topology_modules()


# ---------------------------------------------------------------------------
# Fixture: import + build once per topology, share across the per-topology tests
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", params=TOPOLOGY_MODULES)
def built_topology(request):
    """Import the topology module and return (name, topology). Build failures
    surface as fixture errors that mark all dependent tests as ERROR rather
    than FAIL — pytest output then makes the cause obvious."""
    name = request.param
    mod = importlib.import_module(name)
    assert hasattr(mod, "build"), f"{name} has no `build()` callable"
    t = mod.build()
    assert t is not None, f"{name}.build() returned None"
    return name, t


# ---------------------------------------------------------------------------
# Per-bullet smoke tests (5 functions; bullets 1+2 are covered by the fixture)
# ---------------------------------------------------------------------------
def test_returns_topology_instance(built_topology):
    name, t = built_topology
    assert isinstance(t, Topology), (
        f"{name}.build() returned {type(t).__name__}, not Topology"
    )


def test_has_at_least_one_ica(built_topology):
    name, t = built_topology
    assert len(t.icas) >= 1, f"{name} has no ICAs"


def test_ica_bus_ids_are_real(built_topology):
    name, t = built_topology
    for ica_id, ica in t.icas.items():
        assert ica.bus_id in t.buses, (
            f"{name}: ICA `{ica_id}` references missing bus `{ica.bus_id}`"
        )


def test_load_bus_ids_are_real(built_topology):
    name, t = built_topology
    for load_id, load in t.loads.items():
        assert load.bus_id in t.buses, (
            f"{name}: Load `{load_id}` references missing bus `{load.bus_id}`"
        )


def test_grid_tie_switch_for_grid_connected(built_topology):
    name, t = built_topology
    has_grid_bus = any(b.is_grid for b in t.buses.values())
    if not has_grid_bus:
        pytest.skip(f"{name} has no is_grid=True bus; grid_tie_switch() not required")
    gts = t.grid_tie_switch()
    assert isinstance(gts, SwitchEdge), (
        f"{name} declares a grid bus but grid_tie_switch() returned "
        f"{type(gts).__name__}"
    )
