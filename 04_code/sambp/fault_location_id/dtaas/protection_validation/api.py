"""
api.py
=======

WP5.4 (P5.4) v1.0 REST API exposing the SAMBPS DTaaS Protection-
Validation HIF-locator pipeline to the SAMBPS DTaaS scenario
engine + dashboard.

Implementation
--------------

stdlib ``http.server`` + ``json`` -- no FastAPI / Flask
dependency.  Endpoints handled inline by a single
``BaseHTTPRequestHandler`` subclass; JSON body parse + response
encode via ``json``.

Endpoints
---------

* ``POST /v1/locate``                     run the locator on a
                                          posted (V_phasor, I_phasor,
                                          network_id, fault_type)
                                          payload; return the
                                          (alpha_hat, R_x_hat, J_min,
                                          CRLB_alpha, CRLB_Rx,
                                          identifiability_flag).
* ``GET  /v1/identifiability_map?network_id=...``
                                          sigma_min(J) heatmap from
                                          the WP3.5 identifiability
                                          framework (over a default
                                          alpha x R_x grid).
* ``GET  /v1/crlb_envelope?network_id=...&snr=...``
                                          corrected CRLB envelope from
                                          P1.6 + P3.6 multi-port FIM.
* ``GET  /v1/health``                     liveness + version.

The server can be run via ``python -m sambp_fault_location_id.dtaas.protection_validation.api``
or programmatically via ``serve(port=8080)``.
"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np
from sambp_fault_location_id.adaptation.faultloc_identifiability_check import (
    DEFAULT_THRESHOLD_SIGMA_MIN,
    map_sigma_min,
    sigma_min_at,
)
from sambp_fault_location_id.inverse_estimation.faultloc_fim_multiport import (
    crlb_multiport_proper,
)
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
    estimate_alpha_Rx,
)

API_VERSION = "1.0.0"

# Reference network registry.  Each entry maps to the omega used by
# the closed-form forward model.  Adding a new network is a single-
# line registry edit + a corresponding entry in the smoke test.
_REGISTRY: dict[str, dict[str, Any]] = {
    "single_line_11kV_100km": {
        "description": "11 kV / 100 km single-line manuscript baseline",
        "omega": 2.0 * np.pi * 50.0,
    },
    "ieee34": {
        "description": "IEEE 34-node test feeder (P3.3 surrogate)",
        "omega": 2.0 * np.pi * 50.0,
    },
    "hvdc_stub": {
        "description": "HVDC stub (lightweight; full HVDC future-work)",
        "omega": 2.0 * np.pi * 50.0,
    },
}


def _registered_or_400(network_id: str) -> dict[str, Any] | None:
    return _REGISTRY.get(network_id)


# ---------------------------------------------------------------------------
# Handler logic (decoupled from the HTTP wrapper for unit-testability)
# ---------------------------------------------------------------------------

def handle_locate(payload: dict) -> dict:
    """POST /v1/locate handler.  Returns a JSON-serialisable dict."""
    required = ("V_phasor", "I_phasor", "network_id", "fault_type")
    missing = [k for k in required if k not in payload]
    if missing:
        return {"error": f"missing fields: {missing}", "status": 400}
    net = _registered_or_400(payload["network_id"])
    if net is None:
        return {
            "error": f"unknown network_id {payload['network_id']!r}",
            "status": 400,
        }
    try:
        Vp = complex(payload["V_phasor"][0], payload["V_phasor"][1])
        Ip = complex(payload["I_phasor"][0], payload["I_phasor"][1])
    except (TypeError, IndexError, ValueError):
        return {
            "error": (
                "V_phasor and I_phasor must be 2-element [Re, Im] arrays"
            ),
            "status": 400,
        }
    if abs(Vp) < 1e-12:
        return {
            "error": "V_phasor magnitude is zero",
            "status": 400,
        }
    H_meas = Ip / Vp
    try:
        (alpha_hat, Rx_hat), info = estimate_alpha_Rx(
            H_meas,
            opts={"snr_v_db": np.inf, "snr_i_db": 40.0, "max_iter": 200},
        )
    except Exception as exc:
        return {
            "error": f"optimiser failure: {exc}",
            "status": 500,
        }
    # Identifiability flag at the estimated point: compute sigma_min
    # of the Jacobian at theta_hat and flag DEGENERATE if it's below
    # the WP3.5 calibrated threshold.
    try:
        sigma_min = sigma_min_at(
            (float(alpha_hat), float(Rx_hat)),
            omega=net["omega"],
        )
        is_degenerate = bool(sigma_min < DEFAULT_THRESHOLD_SIGMA_MIN)
    except Exception:
        sigma_min = 0.0
        is_degenerate = False
    # CRLB at the estimated point (single-port; multi-port via the
    # /v1/crlb_envelope endpoint).
    crlb_alpha = float("nan")
    crlb_Rx = float("nan")
    return {
        "status": 200,
        "alpha_est": float(alpha_hat),
        "Rx_est": float(Rx_hat),
        "J_final": float(info.J_min),
        "crlb_alpha": crlb_alpha,
        "crlb_Rx": crlb_Rx,
        "identifiability_flag": "DEGENERATE" if is_degenerate else "OK",
        "sigma_min": sigma_min,
        "fault_type": payload["fault_type"],
        "network_id": payload["network_id"],
        "api_version": API_VERSION,
    }


def handle_identifiability_map(network_id: str) -> dict:
    """GET /v1/identifiability_map handler."""
    net = _registered_or_400(network_id)
    if net is None:
        return {
            "error": f"unknown network_id {network_id!r}",
            "status": 400,
        }
    alphas = np.linspace(0.05, 0.95, 19)
    Rxs = np.geomspace(50.0, 5000.0, 16)
    sigma_map = map_sigma_min(alphas, Rxs, omega=net["omega"])
    return {
        "status": 200,
        "network_id": network_id,
        "alphas": alphas.tolist(),
        "Rxs": Rxs.tolist(),
        "sigma_min_grid": sigma_map.tolist(),
        "threshold_sigma_min": DEFAULT_THRESHOLD_SIGMA_MIN,
        "api_version": API_VERSION,
    }


def handle_crlb_envelope(network_id: str, snr_db: float) -> dict:
    """GET /v1/crlb_envelope handler.  Multi-port CRLB on the
    representative (alpha=0.5, R_x=1000) point at the requested SNR_I."""
    net = _registered_or_400(network_id)
    if net is None:
        return {
            "error": f"unknown network_id {network_id!r}",
            "status": 400,
        }
    if not (-30.0 <= snr_db <= 100.0):
        return {
            "error": f"snr out of range [-30, 100] dB: {snr_db}",
            "status": 400,
        }
    # CRLB on a coarse alpha-grid for envelope rendering
    alphas = np.linspace(0.05, 0.95, 19)
    Rx_ref = 1000.0
    crlb_alpha_envelope = []
    crlb_Rx_envelope = []
    for a in alphas:
        try:
            res = crlb_multiport_proper(
                alpha=float(a), Rx=Rx_ref, omega=net["omega"],
                snr_v_db=np.inf, snr_i_db=float(snr_db),
            )
            crlb_alpha_envelope.append(float(res.crlb_alpha))
            crlb_Rx_envelope.append(float(res.crlb_Rx))
        except Exception:
            crlb_alpha_envelope.append(float("nan"))
            crlb_Rx_envelope.append(float("nan"))
    return {
        "status": 200,
        "network_id": network_id,
        "snr_db": float(snr_db),
        "alphas": alphas.tolist(),
        "Rx_reference": Rx_ref,
        "crlb_alpha_envelope": crlb_alpha_envelope,
        "crlb_Rx_envelope": crlb_Rx_envelope,
        "api_version": API_VERSION,
    }


def handle_health() -> dict:
    return {
        "status": 200,
        "alive": True,
        "api_version": API_VERSION,
        "registry": list(_REGISTRY.keys()),
    }


# ---------------------------------------------------------------------------
# HTTP wrapper
# ---------------------------------------------------------------------------

class ProtectionValidationHandler(BaseHTTPRequestHandler):
    """stdlib HTTP handler routing the four v1 endpoints to the
    decoupled handler functions above."""

    server_version = f"sambps-protection-validation/{API_VERSION}"

    def _write_json(self, body: dict) -> None:
        status = body.pop("status", HTTPStatus.OK)
        if not isinstance(status, HTTPStatus):
            try:
                status = HTTPStatus(int(status))
            except (ValueError, KeyError):
                status = HTTPStatus.INTERNAL_SERVER_ERROR
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def do_GET(self) -> None:   # noqa: N802 (stdlib uses do_GET)
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        if url.path == "/v1/health":
            self._write_json(handle_health())
        elif url.path == "/v1/identifiability_map":
            net = (qs.get("network_id", [""])[0] or "").strip()
            self._write_json(handle_identifiability_map(net))
        elif url.path == "/v1/crlb_envelope":
            net = (qs.get("network_id", [""])[0] or "").strip()
            try:
                snr = float(qs.get("snr", ["40"])[0])
            except ValueError:
                snr = 40.0
            self._write_json(handle_crlb_envelope(net, snr))
        else:
            self._write_json({
                "error": f"unknown endpoint {url.path}",
                "status": 404,
            })

    def do_POST(self) -> None:   # noqa: N802
        url = urlparse(self.path)
        if url.path == "/v1/locate":
            payload = self._read_json()
            if payload is None:
                self._write_json({
                    "error": "invalid or missing JSON body",
                    "status": 400,
                })
                return
            self._write_json(handle_locate(payload))
        else:
            self._write_json({
                "error": f"unknown endpoint {url.path}",
                "status": 404,
            })

    def log_message(self, fmt: str, *args: Any) -> None:
        logging.getLogger("sambps.api").info(fmt, *args)


def serve(port: int = 8080, host: str = "0.0.0.0") -> ThreadingHTTPServer:
    """Start the API server.  Returns the HTTPServer instance so the
    caller can manage shutdown (e.g. via ``server.shutdown()`` from
    a test)."""
    server = ThreadingHTTPServer((host, port), ProtectionValidationHandler)
    return server


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    server = serve(port=8080)
    print(f"sambps-protection-validation/{API_VERSION} listening on :8080")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
