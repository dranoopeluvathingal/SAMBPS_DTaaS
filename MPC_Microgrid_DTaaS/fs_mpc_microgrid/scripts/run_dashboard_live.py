"""Start the live FastAPI dashboard server on port 8080.

Usage:
    python scripts/run_dashboard_live.py

Requires the `dashboard-live` extra (and `mqtt` extra if you want it
to actually subscribe to a running broker):

    pip install -e ".[dashboard-live,mqtt]"

Environment variables forwarded to the server:
    DASHBOARD_MQTT_HOST   default "localhost"
    DASHBOARD_MQTT_PORT   default 1883
    DASHBOARD_NO_MQTT     "1" disables the MQTT subscribe (offline mode)
"""

from __future__ import annotations

import sys

# Force UTF-8 stdout on Windows so any non-ASCII the server logs doesn't
# crash cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    print("open http://localhost:8080")
    import uvicorn
    from fs_mpc_mg.dashboard.server import app
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
