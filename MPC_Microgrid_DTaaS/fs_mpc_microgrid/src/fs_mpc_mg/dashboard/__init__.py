"""Operator dashboard — static HTML report from a simulation run.

The dashboard ingests an `InMemoryPubSub.history()` log (or any sequence
of (topic, payload) pairs) and renders a self-contained HTML file with
inline Chart.js (loaded from CDN). The output can be opened in any
browser, emailed, or attached to a thesis/report — no server required.

For a live deployment, the same `Report` class can be wired behind a
FastAPI/Flask websocket endpoint that updates the JSON inputs in
real time; that work is left to a future Phase-4 deliverable.
"""

from .report import Report, build_report

__all__ = ["Report", "build_report"]
