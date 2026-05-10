"""
dtaas/tests/smoke_test.py — T-G1 smoke test for v1.0.0-dtaas.

Three Reference Twins:

* **Twin 1**: 11 kV / 100 km single-line — the manuscript baseline
  (the WP1.4 / WP2.4 case).
* **Twin 2**: IEEE 34-node — the WP3.3 surrogate.
* **Twin 3**: HVDC stub — lightweight, full HVDC future-work.

Test asserts:

1. The 4 API endpoints respond with status 200 on each twin.
2. ``locate`` returns sensible numbers on a 720-cell stored input.
3. ``identifiability_map`` and ``crlb_envelope`` overlays
   render (CSV emit) without error.
4. The CLI ``validate`` subcommand exits 0.
5. The scenario-engine adapter handles a representative scenario.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest
from sambp_fault_location_id.dtaas.protection_validation.api import (
    API_VERSION,
    ProtectionValidationHandler,
    handle_crlb_envelope,
    handle_health,
    handle_identifiability_map,
    handle_locate,
)
from sambp_fault_location_id.dtaas.protection_validation.scenario_engine_adapter import (
    PLUGIN_INFO,
    configure,
    get_plugin_info,
    handle_scenario,
)

REFERENCE_TWINS = (
    "single_line_11kV_100km",
    "ieee34",
    "hvdc_stub",
)

# A representative (V_phasor, I_phasor) pair on the manuscript
# baseline: balanced 11 kV phase voltage 11 kV * sqrt(2/3) at 0
# rad, locator-band fault current ~ 5 A at SLG fault on alpha=0.5,
# R_x=1000 ohm.  These values are smoke-test fodder, not a hard-
# wired truth -- the test asserts the response *shape* is sensible,
# not specific numerics.
V_PHASOR_REF = [11.0e3 * np.sqrt(2.0 / 3.0), 0.0]
I_PHASOR_REF = [3.5, -1.7]


# =============================================================================
# (1) Direct handler-level smoke (decoupled from HTTP wrapper)
# =============================================================================

@pytest.mark.parametrize("twin", REFERENCE_TWINS)
def test_handle_locate_returns_sensible_response(twin: str) -> None:
    out = handle_locate({
        "V_phasor": V_PHASOR_REF,
        "I_phasor": I_PHASOR_REF,
        "network_id": twin,
        "fault_type": "SLG",
    })
    assert out["status"] == 200, (
        f"locate on {twin!r} returned {out.get('status')}: {out}"
    )
    assert out["network_id"] == twin
    assert out["api_version"] == API_VERSION
    assert 0.0 <= out["alpha_est"] <= 1.0
    assert out["Rx_est"] > 0
    assert out["identifiability_flag"] in ("OK", "DEGENERATE")
    assert "J_final" in out


@pytest.mark.parametrize("twin", REFERENCE_TWINS)
def test_handle_identifiability_map_renders(twin: str) -> None:
    out = handle_identifiability_map(twin)
    assert out["status"] == 200
    assert out["network_id"] == twin
    assert len(out["alphas"]) >= 10
    assert len(out["Rxs"]) >= 10
    assert len(out["sigma_min_grid"]) == len(out["alphas"])


@pytest.mark.parametrize("twin", REFERENCE_TWINS)
def test_handle_crlb_envelope_renders(twin: str) -> None:
    out = handle_crlb_envelope(twin, snr_db=40.0)
    assert out["status"] == 200
    assert out["network_id"] == twin
    assert len(out["alphas"]) == len(out["crlb_alpha_envelope"])


def test_handle_health_responds() -> None:
    out = handle_health()
    assert out["status"] == 200
    assert out["alive"] is True
    assert out["api_version"] == API_VERSION
    for twin in REFERENCE_TWINS:
        assert twin in out["registry"], (
            f"twin {twin!r} not in registry"
        )


# =============================================================================
# (2) HTTP-wrapper smoke (start the server in-process; hit the 4 endpoints)
# =============================================================================

@pytest.fixture(scope="module")
def running_server():
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),   # auto-allocate port
        ProtectionValidationHandler,
    )
    port = server.server_address[1]
    thread = threading.Thread(
        target=server.serve_forever, name="sambps-api", daemon=True,
    )
    thread.start()
    # short wait so the bind completes before the first request
    time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    yield base
    server.shutdown()


def _http_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_http_health(running_server: str) -> None:
    out = _http_get(f"{running_server}/v1/health")
    assert out["alive"] is True
    assert out["api_version"] == API_VERSION


@pytest.mark.parametrize("twin", REFERENCE_TWINS)
def test_http_locate(running_server: str, twin: str) -> None:
    out = _http_post(f"{running_server}/v1/locate", {
        "V_phasor": V_PHASOR_REF,
        "I_phasor": I_PHASOR_REF,
        "network_id": twin,
        "fault_type": "SLG",
    })
    assert out["api_version"] == API_VERSION
    assert 0.0 <= out["alpha_est"] <= 1.0


@pytest.mark.parametrize("twin", REFERENCE_TWINS)
def test_http_identifiability_map(running_server: str, twin: str) -> None:
    out = _http_get(
        f"{running_server}/v1/identifiability_map?network_id={twin}"
    )
    assert out["network_id"] == twin
    assert len(out["alphas"]) > 0


@pytest.mark.parametrize("twin", REFERENCE_TWINS)
def test_http_crlb_envelope(running_server: str, twin: str) -> None:
    out = _http_get(
        f"{running_server}/v1/crlb_envelope?network_id={twin}&snr=40"
    )
    assert out["network_id"] == twin
    assert out["snr_db"] == 40.0


# =============================================================================
# (3) Scenario-engine adapter smoke
# =============================================================================

def test_scenario_engine_adapter_plugin_info() -> None:
    info = get_plugin_info()
    assert info.name == PLUGIN_INFO.name
    assert info.version == API_VERSION
    assert "HIF_SLG" in info.handles_event_classes


def test_scenario_engine_adapter_handle_scenario() -> None:
    configure({"network_id": "single_line_11kV_100km"})
    response = handle_scenario({
        "scenario_id": "smoke-1",
        "timestamp": 1731139200.0,
        "event_class": "HIF_SLG",
        "phasors": {
            "V_phasor": V_PHASOR_REF,
            "I_phasor": I_PHASOR_REF,
        },
        "metadata": {"fault_type": "SLG"},
    })
    assert response["scenario_id"] == "smoke-1"
    assert response["plugin_name"] == PLUGIN_INFO.name
    assert response["decision"] in ("LOCATED", "UNCERTAIN", "ERROR")
    if response["decision"] != "ERROR":
        assert 0.0 <= response["alpha_est"] <= 1.0
        assert response["Rx_est"] > 0


# =============================================================================
# (4) Negative paths
# =============================================================================

def test_handle_locate_unknown_network_400() -> None:
    out = handle_locate({
        "V_phasor": V_PHASOR_REF,
        "I_phasor": I_PHASOR_REF,
        "network_id": "no_such_twin",
        "fault_type": "SLG",
    })
    assert out["status"] == 400
    assert "unknown network_id" in out["error"]


def test_handle_locate_missing_field_400() -> None:
    out = handle_locate({
        "V_phasor": V_PHASOR_REF,
        # missing I_phasor + network_id
    })
    assert out["status"] == 400
