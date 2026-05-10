"""Static HTML report generator for a fleet+CMC+DT simulation run."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import json
import re


@dataclass
class Report:
    """Aggregates the data needed for the operator dashboard report.

    Build this incrementally during a simulation, then call ``render()`` to
    serialise it to an HTML file. The dashboard layout is fleet-centric:
    one card per ICA + a fleet-overview row.
    """

    title: str = "Microgrid Operator Dashboard"
    sim_t_end_s: float = 0.0
    fleet_ica_ids: list[str] = field(default_factory=list)
    cmc_dispatches: list[dict] = field(default_factory=list)         # CMC.log
    pubsub_history: list[tuple[str, Any]] = field(default_factory=list)
    dt_summary: dict = field(default_factory=dict)
    extra_notes: str = ""

    # ------------------------------------------------------------------
    def _telemetry_series(self, ica_id: str) -> dict[str, list[tuple[float, Any]]]:
        """Group telemetry into time-series per topic key."""
        prefix = f"/ica/{ica_id}/tel/"
        keys = ("v_dc", "i_s_abc", "i_m_abc", "i_l_abc", "v_s_abc", "I_s_amp")
        out: dict[str, list[tuple[float, Any]]] = {k: [] for k in keys}
        for topic, payload in self.pubsub_history:
            if not topic.startswith(prefix):
                continue
            key = topic[len(prefix):]
            if key not in keys:
                continue
            if isinstance(payload, dict) and "value" in payload:
                ts = float(payload.get("ts", 0.0))
                out[key].append((ts, payload["value"]))
        return out

    # ------------------------------------------------------------------
    def _residual_series(self, ica_id: str) -> dict[str, list[tuple[float, Any]]]:
        prefix = f"/dt/{ica_id}/"
        keys = ("residual/v_dc", "residual/i_m_norm", "params/L", "params/r")
        out: dict[str, list[tuple[float, Any]]] = {k: [] for k in keys}
        for topic, payload in self.pubsub_history:
            if not topic.startswith(prefix):
                continue
            key = topic[len(prefix):]
            if key not in keys:
                continue
            if isinstance(payload, dict) and "value" in payload:
                ts = float(payload.get("ts", 0.0))
                out[key].append((ts, payload["value"]))
        return out

    # ------------------------------------------------------------------
    def _alert_events(self) -> list[dict]:
        out = []
        for topic, payload in self.pubsub_history:
            if "/anomaly" in topic or "/cyber_alert" in topic:
                v = payload.get("value", payload) if isinstance(payload, dict) else payload
                ts = payload.get("ts", 0.0) if isinstance(payload, dict) else 0.0
                out.append({"topic": topic, "ts": ts, "value": v})
        return out

    # ------------------------------------------------------------------
    def _q_dispatch_series(self) -> list[dict]:
        """Extract Q allocation per ICA over time from CMC dispatch log."""
        rows = []
        for r in self.cmc_dispatches:
            ts = r.get("ts", 0.0)
            for iid, refs in r.get("published", {}).items():
                rows.append({"ts": ts, "ica": iid, "Q_ref": refs.get("Q_ref", 0.0),
                             "v_dc_ref": refs.get("v_dc_ref", 0.0)})
        return rows

    # ------------------------------------------------------------------
    def _build_payload(self) -> dict:
        per_ica = {}
        for iid in self.fleet_ica_ids:
            tel = self._telemetry_series(iid)
            res = self._residual_series(iid)
            per_ica[iid] = {
                "v_dc": [(t, v) for t, v in tel["v_dc"]],
                "I_s_amp": [(t, v) for t, v in tel["I_s_amp"]],
                "i_s_a": [(t, v[0]) for t, v in tel["i_s_abc"] if isinstance(v, (list, tuple))],
                "i_m_a": [(t, v[0]) for t, v in tel["i_m_abc"] if isinstance(v, (list, tuple))],
                "residual_v_dc": list(res["residual/v_dc"]),
                "residual_im": list(res["residual/i_m_norm"]),
                "L_uH": [(t, v * 1e6) for t, v in res["params/L"] if v is not None],
                "r_mOhm": [(t, v * 1e3) for t, v in res["params/r"] if v is not None],
            }
        # Normalise timestamps to start at 0 if the data is wall-clock-ish
        all_ts = [t for s in per_ica.values() for series in s.values() for (t, _v) in series]
        if all_ts:
            t0 = min(all_ts)
            if t0 > 1e6:   # wall-clock seconds — shift to start at 0
                for iid in per_ica:
                    for k in per_ica[iid]:
                        per_ica[iid][k] = [(t - t0, v) for t, v in per_ica[iid][k]]
        return {
            "title": self.title,
            "sim_t_end_s": self.sim_t_end_s,
            "ica_ids": self.fleet_ica_ids,
            "per_ica": per_ica,
            "alerts": self._alert_events(),
            "q_dispatch": self._q_dispatch_series(),
            "dt_summary": self.dt_summary,
            "extra_notes": self.extra_notes,
        }

    # ------------------------------------------------------------------
    def render(self) -> str:
        payload = self._build_payload()
        return _HTML_TEMPLATE.replace("__PAYLOAD_JSON__", json.dumps(payload))

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.render(), encoding="utf-8")
        return p


# ---------------------------------------------------------------------------
def build_report(
    title: str,
    sim_t_end_s: float,
    fleet_ica_ids: Iterable[str],
    pubsub_history: Iterable[tuple[str, Any]],
    cmc_dispatches: Iterable[dict] | None = None,
    dt_summary: dict | None = None,
    extra_notes: str = "",
) -> Report:
    return Report(
        title=title,
        sim_t_end_s=float(sim_t_end_s),
        fleet_ica_ids=list(fleet_ica_ids),
        pubsub_history=list(pubsub_history),
        cmc_dispatches=list(cmc_dispatches or []),
        dt_summary=dt_summary or {},
        extra_notes=extra_notes,
    )


# ---------------------------------------------------------------------------
_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>fs_mpc_mg dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 0;}
  header { background: #1e3a8a; color: #fff; padding: 16px 24px; }
  header h1 { margin: 0; font-size: 20px; font-weight: 600; }
  header .sub { font-size: 12px; color: #93c5fd; margin-top: 2px; }
  main { padding: 16px 24px; }
  .row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px; flex: 1 1 380px; min-width: 380px; }
  .card h2 { margin: 0 0 8px 0; font-size: 14px; color: #cbd5e1; font-weight: 500; }
  .ica-card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px; flex: 1 1 100%; }
  .kvgrid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 8px; }
  .kv { background: #0f172a; border-radius: 6px; padding: 8px; }
  .kv .k { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: .04em; }
  .kv .v { font-size: 16px; color: #f1f5f9; font-weight: 600; margin-top: 2px; }
  .kv .unit { font-size: 11px; color: #94a3b8; margin-left: 2px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  table th, table td { text-align: left; padding: 4px 6px; border-bottom: 1px solid #334155; }
  table th { color: #94a3b8; font-weight: 500; }
  .severity-critical { color: #f87171; }
  .severity-warning  { color: #fbbf24; }
  .severity-info     { color: #60a5fa; }
  canvas { background: #0f172a; border-radius: 4px; }
  .charts { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
  footer { padding: 12px 24px; color: #64748b; font-size: 11px; border-top: 1px solid #334155; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; margin-left: 8px;}
  .badge-ok   { background: #14532d; color: #86efac; }
  .badge-warn { background: #78350f; color: #fbbf24; }
  .badge-bad  { background: #7f1d1d; color: #fca5a5; }
</style>
</head>
<body>
<header>
  <h1 id="hdr-title">fs_mpc_mg — Microgrid Operator Dashboard</h1>
  <div class="sub" id="hdr-sub"></div>
</header>
<main>

  <div class="row">
    <div class="card">
      <h2>Fleet Overview</h2>
      <div class="kvgrid" id="fleet-kvgrid"></div>
    </div>
    <div class="card">
      <h2>DT Summary</h2>
      <table id="dt-summary"></table>
    </div>
  </div>

  <div class="row">
    <div class="card" style="flex: 1 1 100%;">
      <h2>Q-Dispatch History (CMC)</h2>
      <canvas id="chart-qdispatch" height="180"></canvas>
    </div>
  </div>

  <div id="ica-cards"></div>

  <div class="row">
    <div class="card" style="flex: 1 1 100%;">
      <h2>Alerts &amp; Anomaly Events</h2>
      <table id="alerts-table">
        <thead><tr><th>t (s)</th><th>Topic</th><th>Severity</th><th>Detail</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <div class="row" id="notes-row"></div>

</main>
<footer>
  Generated by fs_mpc_mg v0.3 dashboard. Charts powered by Chart.js.
</footer>

<script>
const D = __PAYLOAD_JSON__;

// Title
document.getElementById('hdr-title').textContent = D.title || 'fs_mpc_mg Dashboard';
document.getElementById('hdr-sub').textContent =
  `Simulated for ${D.sim_t_end_s.toFixed(3)} s · ${D.ica_ids.length} ICAs · ${D.alerts.length} alerts`;

// Fleet KVs
const kv = document.getElementById('fleet-kvgrid');
function addKV(k, v, unit='') {
  const d = document.createElement('div'); d.className = 'kv';
  d.innerHTML = `<div class="k">${k}</div><div class="v">${v}<span class="unit">${unit}</span></div>`;
  kv.appendChild(d);
}
addKV('ICAs', D.ica_ids.length);
addKV('Sim duration', D.sim_t_end_s.toFixed(3), 's');
addKV('CMC dispatches', D.q_dispatch.length / Math.max(D.ica_ids.length, 1));
addKV('Alerts', D.alerts.length);

// DT summary table
const dtTable = document.getElementById('dt-summary');
if (D.dt_summary && Object.keys(D.dt_summary).length) {
  let rows = '';
  rows += `<tr><th>n_ticks</th><td>${D.dt_summary.n_ticks ?? '-'}</td></tr>`;
  rows += `<tr><th>anomaly events</th><td>${D.dt_summary.n_anomaly_events ?? '-'}</td></tr>`;
  rows += `<tr><th>cyber alerts</th><td>${D.dt_summary.n_cyber_alerts ?? '-'}</td></tr>`;
  if (D.dt_summary.rls) {
    for (const [iid, info] of Object.entries(D.dt_summary.rls)) {
      const conv = info.converged ? '<span class="badge badge-ok">conv</span>'
                                   : '<span class="badge badge-warn">…</span>';
      rows += `<tr><th>${iid} L,r</th><td>${(info.L*1e6).toFixed(1)} µH / ${(info.r*1e3).toFixed(1)} mΩ ${conv}</td></tr>`;
    }
  }
  dtTable.innerHTML = rows;
} else {
  dtTable.innerHTML = '<tr><td>No DT data.</td></tr>';
}

// Q dispatch chart
function asXY(arr, fx=(t)=>t, fv=(v)=>v) { return arr.map(([t,v])=>({x: fx(t), y: fv(v)})); }
const ctxQ = document.getElementById('chart-qdispatch');
const dispatchByIca = {};
for (const r of D.q_dispatch) {
  if (!dispatchByIca[r.ica]) dispatchByIca[r.ica] = [];
  dispatchByIca[r.ica].push({x: r.ts, y: r.Q_ref});
}
new Chart(ctxQ, {
  type: 'line',
  data: {
    datasets: Object.entries(dispatchByIca).map(([iid, pts], i) => ({
      label: `${iid}  Q_ref (VAr)`, data: pts, borderWidth: 1.4, tension: 0.0,
      borderColor: ['#60a5fa','#34d399','#f472b6','#fb923c'][i % 4],
    }))
  },
  options: {
    parsing: false, animation: false, responsive: true, maintainAspectRatio: false,
    scales: {
      x: { type: 'linear', title: {display:true, text:'t (s)', color:'#94a3b8'}, ticks:{color:'#94a3b8'}, grid:{color:'#1e293b'} },
      y: { title:{display:true, text:'Q_ref (VAr)', color:'#94a3b8'}, ticks:{color:'#94a3b8'}, grid:{color:'#1e293b'} },
    },
    plugins: { legend: { labels: { color: '#cbd5e1' } } },
  },
});

// Per-ICA cards
const cardsRoot = document.getElementById('ica-cards');
for (const iid of D.ica_ids) {
  const data = D.per_ica[iid] || {};
  const wrap = document.createElement('div');
  wrap.className = 'row';
  wrap.innerHTML = `
    <div class="ica-card">
      <h2>${iid} <span class="badge badge-ok">running</span></h2>
      <div class="charts">
        <div><canvas id="c-vdc-${iid}" height="160"></canvas></div>
        <div><canvas id="c-iamp-${iid}" height="160"></canvas></div>
        <div><canvas id="c-resv-${iid}" height="160"></canvas></div>
        <div><canvas id="c-resi-${iid}" height="160"></canvas></div>
      </div>
    </div>`;
  cardsRoot.appendChild(wrap);

  const mkChart = (id, label, dataset, ylabel, color) => {
    new Chart(document.getElementById(id), {
      type: 'line',
      data: { datasets: [{ label, data: dataset, borderColor: color, borderWidth: 1.0, pointRadius: 0, tension: 0 }] },
      options: {
        parsing: false, animation: false, responsive: true, maintainAspectRatio: false,
        scales: {
          x: { type:'linear', title:{display:true, text:'t (s)', color:'#94a3b8'}, ticks:{color:'#94a3b8'}, grid:{color:'#1e293b'}},
          y: { title:{display:true, text:ylabel, color:'#94a3b8'}, ticks:{color:'#94a3b8'}, grid:{color:'#1e293b'} },
        },
        plugins: { legend: { labels:{color:'#cbd5e1'} } },
      }
    });
  };
  mkChart(`c-vdc-${iid}`,  `${iid} v_dc`,            asXY(data.v_dc || []),       'V',  '#60a5fa');
  mkChart(`c-iamp-${iid}`, `${iid} I_s_amp`,         asXY(data.I_s_amp || []),    'A',  '#a78bfa');
  mkChart(`c-resv-${iid}`, `${iid} v_dc residual`,   asXY(data.residual_v_dc || []), 'V',  '#fbbf24');
  mkChart(`c-resi-${iid}`, `${iid} ‖i_m‖ residual`,  asXY(data.residual_im || []),   'A',  '#f472b6');
}

// Alerts table
const tbody = document.querySelector('#alerts-table tbody');
for (const a of D.alerts) {
  const tr = document.createElement('tr');
  const sev = (a.value && a.value.severity) || 'info';
  const cls = `severity-${sev}`;
  const detail = (a.value && (a.value.detail || a.value.reason)) || JSON.stringify(a.value);
  tr.innerHTML = `<td>${(+a.ts).toFixed(3)}</td><td>${a.topic}</td><td class="${cls}">${sev}</td><td>${detail}</td>`;
  tbody.appendChild(tr);
}
if (!D.alerts.length) {
  tbody.innerHTML = '<tr><td colspan="4">No alerts.</td></tr>';
}

// Notes
if (D.extra_notes) {
  const notes = document.getElementById('notes-row');
  notes.innerHTML = `<div class="card" style="flex: 1 1 100%;"><h2>Notes</h2><pre style="white-space:pre-wrap;color:#cbd5e1;font-size:12px;">${D.extra_notes.replace(/&/g,'&amp;').replace(/</g,'&lt;')}</pre></div>`;
}
</script>
</body>
</html>
"""
