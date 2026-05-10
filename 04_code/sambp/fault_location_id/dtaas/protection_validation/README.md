# SAMBPS DTaaS Protection-Validation v1.0

> **HIF-locator** as a SAMBPS Digital-Twin-as-a-Service plugin —
> single-ended joint estimation of HIF location and arc resistance
> via power-frequency admittance identification.  REST API +
> Click CLI + scenario-engine plugin + identifiability / CRLB UI
> widget + minimal Docker image.

* **Version**: 1.0.0
* **License**: MIT
* **Status**: pre-release; v1.0.0-dtaas tag pending PI sign-off
  on RRR + the upstream commits in the public repo at
  https://github.com/SAMBPS-DTaaS/HIF-TF-Locator.

---

## 1. Installation

### 1.1 From source (local dev)

```bash
git clone https://github.com/SAMBPS-DTaaS/HIF-TF-Locator
cd HIF-TF-Locator/04_code/sambp/fault_location_id
python -m venv .venv && source .venv/bin/activate
pip install -e .
pip install click   # CLI dep (not in core install_requires)
```

### 1.2 Docker

```bash
docker build -f dtaas/protection_validation/docker/Dockerfile \
             -t sambps/protection-validation:v1.0 .
docker run --rm -p 8080:8080 sambps/protection-validation:v1.0
```

The Docker image is < 200 MB (python:3.12-slim base + numpy/scipy +
the built wheel).

## 2. API reference

Base URL: `http://localhost:8080`.  Server: stdlib `http.server`
(zero new dependencies).

| Endpoint | Method | Description |
|---|---|---|
| `/v1/health` | GET | liveness + version |
| `/v1/locate` | POST | run the locator on a (V, I) phasor pair |
| `/v1/identifiability_map?network_id=…` | GET | sigma_min(J) heatmap |
| `/v1/crlb_envelope?network_id=…&snr=…` | GET | corrected CRLB envelope |

### 2.1 POST `/v1/locate`

Request body:

```json
{
  "V_phasor": [Re(V), Im(V)],
  "I_phasor": [Re(I), Im(I)],
  "network_id": "single_line_11kV_100km",
  "fault_type": "SLG"
}
```

Response (200):

```json
{
  "alpha_est": 0.43,
  "Rx_est": 850.0,
  "J_final": 0.012,
  "crlb_alpha": NaN,
  "crlb_Rx": NaN,
  "identifiability_flag": "OK",
  "sigma_min": 0.034,
  "fault_type": "SLG",
  "network_id": "single_line_11kV_100km",
  "api_version": "1.0.0"
}
```

`identifiability_flag` is `DEGENERATE` if `sigma_min` falls below the
WP3.5 calibrated threshold (`DEFAULT_THRESHOLD_SIGMA_MIN = 1e-2`).

### 2.2 GET `/v1/identifiability_map`

Returns the sigma_min(J) heatmap for the requested network on a
default 19 × 16 (alpha × R_x) grid:

```
GET /v1/identifiability_map?network_id=ieee34
->
{
  "network_id": "ieee34",
  "alphas": [0.05, 0.10, ..., 0.95],
  "Rxs":    [50.0, 70.7, ..., 5000.0],
  "sigma_min_grid": [[..., ...], ...],
  "threshold_sigma_min": 1.0e-2,
  "api_version": "1.0.0"
}
```

### 2.3 GET `/v1/crlb_envelope`

Returns the CRLB on alpha (and on R_x) over a coarse alpha-grid
at the requested SNR_I:

```
GET /v1/crlb_envelope?network_id=ieee34&snr=40
->
{
  "network_id": "ieee34",
  "snr_db": 40.0,
  "alphas": [...],
  "Rx_reference": 1000.0,
  "crlb_alpha_envelope": [...],
  "crlb_Rx_envelope": [...],
  "api_version": "1.0.0"
}
```

### 2.4 GET `/v1/health`

Returns liveness + the registered Reference Twins:

```
GET /v1/health
->
{
  "alive": true,
  "api_version": "1.0.0",
  "registry": ["single_line_11kV_100km", "ieee34", "hvdc_stub"]
}
```

## 3. CLI

The `cli.py` module ships a Click-based CLI that wraps the same
handlers as the API:

```bash
python -m sambp_fault_location_id.dtaas.protection_validation.cli locate \
    --vre 8990 --vim 0 --ire 3.5 --iim -1.7 \
    --network-id single_line_11kV_100km --fault-type SLG

python -m sambp_fault_location_id.dtaas.protection_validation.cli map \
    --network-id ieee34 --output identifiability_ieee34.csv

python -m sambp_fault_location_id.dtaas.protection_validation.cli envelope \
    --network-id ieee34 --snr 40 --output crlb_envelope_ieee34.csv

python -m sambp_fault_location_id.dtaas.protection_validation.cli validate
```

## 4. SAMBPS DTaaS scenario-engine plugin

`scenario_engine_adapter.py` exposes a 3-function plugin contract:

* `get_plugin_info() -> PluginInfo`
* `configure(config: dict) -> None`
* `handle_scenario(scenario: dict) -> dict`

This is the proposed canonical shape for SAMBPS DTaaS protection
plugins; sibling sub-projects (sync_oc, transformer_diff, line_diff,
bus_diff) will mirror this contract at their WP5.x equivalents.

A scenario emission carries:

```json
{
  "scenario_id": "sc-0001",
  "timestamp": 1731139200.0,
  "event_class": "HIF_SLG",
  "phasors": {
    "V_phasor": [Re, Im],
    "I_phasor": [Re, Im]
  },
  "metadata": {"fault_type": "SLG"}
}
```

The plugin returns a per-scenario decision:

```json
{
  "scenario_id": "sc-0001",
  "decision": "LOCATED" | "UNCERTAIN" | "ERROR",
  "alpha_est": 0.43,
  "Rx_est": 850.0,
  "identifiability_flag": "OK",
  "plugin_name": "protection_validation.fault_location_id",
  "plugin_version": "1.0.0",
  "details": {...}
}
```

## 5. UI widget

The `ui/index.html` widget renders the identifiability heatmap and
the CRLB envelope on top of a network single-line diagram (TODO at
the SLD asset path).  Embed in the SAMBPS DTaaS dashboard via:

```html
<iframe src="https://dtaas.sambps.example.com/protection_validation/ui/index.html"
        width="800" height="600"
        style="border: 0;"></iframe>
```

The widget is pure static HTML + vanilla JS (no React build chain)
and pulls data from the API base URL configured in the UI.

## 6. Reference Twins

Three are registered out of the box:

| network_id | Description | Maturity |
|---|---|---|
| `single_line_11kV_100km` | 11 kV / 100 km single-line — manuscript baseline | production |
| `ieee34` | IEEE 34-node test feeder (P3.3 surrogate) | production |
| `hvdc_stub` | HVDC stub (lightweight; full HVDC future-work) | preview |

Add a new twin by editing `_REGISTRY` in `api.py` plus the
corresponding entry in the smoke test.

## 7. Citation

If you use the SAMBPS DTaaS Protection-Validation pipeline in
academic work, please cite:

* The Phase-3 conference paper (`docs/Phase3_conference_paper.tex`
  in the public repo) for the multi-port CRLB + multi-feeder
  framework.
* The Phase-4 IEEE TSG benchmark paper
  (`docs/Phase4_TSG_benchmark.tex`) for the head-to-head competitor
  comparison on three independent arc-model classes.
* The IEEE Access manuscript (`docs/manuscript_v2.tex`) for the
  single-ended single-feeder baseline.

A consolidated `CITATION.cff` lands at the v1.0.0-dtaas tag.

## 8. Support

Issues / questions: file at the public repo
https://github.com/SAMBPS-DTaaS/HIF-TF-Locator/issues, or contact
the SAMBPS DTaaS programme via Prof. K. Shanthi Swarup, IIT
Madras Power Systems Computational Lab.
