"""Smoke tests for the live FastAPI dashboard server.

Skipped if `fastapi` (the `dashboard-live` extra) is not installed.
Sets `DASHBOARD_NO_MQTT=1` *before* importing the server so the
TestClient lifespan startup doesn't try to connect to a broker
that isn't running on the test machine.
"""

from __future__ import annotations

import json
import os

import pytest

# Skip the whole module if the dashboard-live extra isn't present.
pytest.importorskip("fastapi", reason="fastapi not installed (dashboard-live extra)")
pytest.importorskip("httpx", reason="httpx not installed (required by FastAPI TestClient)")

# Disable MQTT BEFORE importing the server module (env var read at module load).
os.environ["DASHBOARD_NO_MQTT"] = "1"

from fastapi.testclient import TestClient                  # noqa: E402

from fs_mpc_mg.dashboard.server import app                 # noqa: E402


def test_index_returns_200_and_contains_app_name():
    """`GET /` returns the single-page HTML with our title in it."""
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "fs_mpc_mg" in r.text
        # The HTML wires up a WebSocket — verify the client-side glue is there
        assert "/ws" in r.text


def test_ws_endpoint_accepts_connection_and_sends_initial_snapshot():
    """`WebSocket /ws` accepts the connection and immediately sends a
    `{ts, state}` JSON snapshot (so a freshly-connected client doesn't
    wait up to 200 ms for the next broadcast)."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            raw = ws.receive_text()
            payload = json.loads(raw)
            assert "ts" in payload
            assert "state" in payload
            assert isinstance(payload["state"], dict)
