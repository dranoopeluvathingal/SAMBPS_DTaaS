"""Live FastAPI dashboard for the FS-MPC microgrid stack.

Subscribes to MQTT telemetry from the running fleet and broadcasts the
latest per-topic state to a WebSocket every 200 ms. Serves a single-page
vanilla-JS app at `/` that renders the state as a grid of cards.

Topic subscriptions (see `comm/topics.py` and `dt/topics.py`):
  /ica/+/tel/+    — all ICA telemetry (v_dc, i_m_abc, ...)
  /dt/#           — all DT topics (residuals, anomalies, forecasts)

Configuration via env vars (so tests can disable MQTT cleanly):
  DASHBOARD_MQTT_HOST   default "localhost"
  DASHBOARD_MQTT_PORT   default 1883
  DASHBOARD_NO_MQTT     "1" → skip the MQTT subscribe entirely. Used by
                        tests/test_dashboard_server.py so the test runs
                        without a broker on localhost.

Optional dependency group: `dashboard-live`
    pip install -e ".[dashboard-live,mqtt]"
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MQTT_BROKER_HOST = os.environ.get("DASHBOARD_MQTT_HOST", "localhost")
MQTT_BROKER_PORT = int(os.environ.get("DASHBOARD_MQTT_PORT", "1883"))
SKIP_MQTT = os.environ.get("DASHBOARD_NO_MQTT", "0") == "1"
WS_TICK_S = 0.2  # broadcast cadence — spec: "re-renders every 200 ms"


# ---------------------------------------------------------------------------
# Shared in-memory state
# ---------------------------------------------------------------------------

# Last value seen per MQTT topic.
#   {topic: {"payload": <decoded>, "last_seen": <unix_seconds>}}
_STATE: dict[str, dict[str, Any]] = {}

# Active WebSocket connections (server-push pattern).
_WS_CONNECTIONS: set[WebSocket] = set()

# paho-mqtt client handle, populated on startup if MQTT is enabled.
_mqtt_client: Any | None = None


# ---------------------------------------------------------------------------
# MQTT plumbing
# ---------------------------------------------------------------------------

def _on_mqtt_message(client: Any, userdata: Any, msg: Any) -> None:
    """paho-mqtt callback. Runs in the network thread; only writes the
    state dict (single-threaded readers in asyncio see a coherent
    snapshot via dict semantics)."""
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {"raw_hex": msg.payload.hex()}
    _STATE[msg.topic] = {"payload": payload, "last_seen": time.time()}


def _setup_mqtt() -> Any:
    """Connect, subscribe to telemetry topics, start the network loop."""
    import paho.mqtt.client as mqtt   # lazy: only required when MQTT is enabled

    client = mqtt.Client(client_id=f"dashboard-{os.getpid()}", protocol=mqtt.MQTTv5)
    client.on_message = _on_mqtt_message
    client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=30)
    # `+` is single-level wildcard; `#` is multi-level (only at end).
    # `/ica/+/tel/+` covers v_dc, i_m_abc, ... at one level under tel/.
    # `/dt/#` covers all DT topics regardless of depth.
    client.subscribe([("/ica/+/tel/+", 1), ("/dt/#", 1)])
    client.loop_start()
    return client


# ---------------------------------------------------------------------------
# WebSocket broadcast loop
# ---------------------------------------------------------------------------

async def _broadcast_loop() -> None:
    """Push the full state dict to every connected WS client every WS_TICK_S."""
    while True:
        try:
            await asyncio.sleep(WS_TICK_S)
            if not _WS_CONNECTIONS:
                continue
            payload = json.dumps({"ts": time.time(), "state": _STATE})
            stale: list[WebSocket] = []
            for ws in list(_WS_CONNECTIONS):
                try:
                    await ws.send_text(payload)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                _WS_CONNECTIONS.discard(ws)
        except asyncio.CancelledError:
            break


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mqtt_client
    if not SKIP_MQTT:
        try:
            _mqtt_client = _setup_mqtt()
        except Exception as exc:   # broker down, paho not installed, etc.
            print(f"[dashboard] MQTT setup failed ({exc!s}); serving without telemetry")
            _mqtt_client = None

    broadcast_task = asyncio.create_task(_broadcast_loop())
    try:
        yield
    finally:
        broadcast_task.cancel()
        try:
            await broadcast_task
        except (asyncio.CancelledError, Exception):
            pass
        if _mqtt_client is not None:
            try:
                _mqtt_client.loop_stop()
                _mqtt_client.disconnect()
            except Exception:
                pass


app = FastAPI(title="fs_mpc_mg live dashboard", lifespan=lifespan)


# ---------------------------------------------------------------------------
# HTML — single-page vanilla JS that renders /ws state as cards
# ---------------------------------------------------------------------------

_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>fs_mpc_mg — live dashboard</title>
<style>
  body { font-family: 'JetBrains Mono', Consolas, monospace;
         padding: 20px; background: #1a1a1a; color: #ddd; margin: 0; }
  h1 { color: #4ec9b0; margin: 0 0 4px 0; font-size: 18px; }
  #status { color: #888; font-size: 11px; margin-bottom: 16px; }
  #grid { display: grid; gap: 6px;
          grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
  .card { padding: 6px 10px; background: #252525;
          border: 1px solid #333; border-radius: 4px; }
  .card .topic  { color: #569cd6; font-size: 10px; word-break: break-all; }
  .card .value  { color: #d7ba7d; font-size: 13px; margin-top: 3px;
                  word-break: break-all; }
  .card.stale .value { color: #555; }
</style>
</head>
<body>
  <h1>fs_mpc_mg — live</h1>
  <div id="status">connecting…</div>
  <div id="grid"></div>
<script>
(function() {
  const grid    = document.getElementById("grid");
  const statusE = document.getElementById("status");
  const proto   = location.protocol === "https:" ? "wss" : "ws";
  const ws      = new WebSocket(proto + "://" + location.host + "/ws");

  function fmtValue(payload) {
    const v = (payload && Object.prototype.hasOwnProperty.call(payload, "value"))
      ? payload.value : payload;
    if (v === null || v === undefined) return "—";
    if (typeof v === "number") return v.toFixed(3);
    if (Array.isArray(v)) return v.map(x => typeof x === "number" ? x.toFixed(2) : x).join(", ");
    let s = JSON.stringify(v);
    return s.length > 80 ? s.slice(0, 80) + "…" : s;
  }

  ws.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    const now = data.ts;
    const topics = Object.keys(data.state).sort();
    statusE.innerText = "tick @ " + new Date(now * 1000).toLocaleTimeString()
      + "  •  " + topics.length + " topics";
    grid.innerHTML = topics.map(t => {
      const info  = data.state[t];
      const stale = (now - info.last_seen) > 1.0;
      return `<div class="card${stale ? ' stale' : ''}">
                <div class="topic">${t}</div>
                <div class="value">${fmtValue(info.payload)}</div>
              </div>`;
    }).join("");
  };
  ws.onerror = () => { statusE.innerText = "ws error"; };
  ws.onclose = () => { statusE.innerText = "disconnected"; };
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _INDEX_HTML


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _WS_CONNECTIONS.add(websocket)
    try:
        # Send initial snapshot immediately so a fresh client has data
        # without waiting up to WS_TICK_S for the next broadcast.
        await websocket.send_text(json.dumps({"ts": time.time(), "state": _STATE}))
        # Keep the connection open. Inbound messages from the client are
        # ignored (server-push only); receive_text just blocks until the
        # client disconnects, then raises WebSocketDisconnect.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        # Don't crash the loop on weird client behaviour
        pass
    finally:
        _WS_CONNECTIONS.discard(websocket)
