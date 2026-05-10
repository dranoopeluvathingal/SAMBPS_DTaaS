# Release-Readiness Review — `v1.0.0-dtaas`

**Project:** SAMBPS DTaaS — `fault_location_id` Phase 5 (WP5.4)
**Release:** `v1.0.0-dtaas` (DTaaS Protection-Validation v1.0)
**Issued:** 2026-05-10
**Author / DRI:** Anoop Eluvathingal (PI)
**Reviewer:** Prof. K. Shanthi Swarup (host advisor, IIT Madras
            Power Systems Computational Lab)

> **Checklist source:** the SAMBPS DTaaS programme does not yet
> have a programme-level RRR template; per the WP5.4 brief
> ("if not present, use the IITM standard SDLC checklist") this
> document follows the IITM SDLC structure (requirements →
> design → test → security → documentation → deployment →
> sign-off).

---

## 1. Requirements

| ID | Requirement (per WP5.4 brief) | Status | Evidence |
|---|---|---|---|
| R-1 | REST API: 4 endpoints (locate, identifiability_map, crlb_envelope, health) | **MET** | `dtaas/protection_validation/api.py` |
| R-2 | Click-based CLI mirroring the API (locate, map, envelope, validate) | **MET** | `dtaas/protection_validation/cli.py` |
| R-3 | SAMBPS DTaaS scenario-engine plugin adapter | **MET** | `dtaas/protection_validation/scenario_engine_adapter.py` |
| R-4 | UI widget (static HTML; iframe-embeddable) | **MET** | `dtaas/protection_validation/ui/index.html` |
| R-5 | T-G1 smoke test on 3 Reference Twins | **MET** | `dtaas/tests/smoke_test.py` (24/24 PASS) |
| R-6 | README.md with installation + API ref + integration + license + citation | **MET** | `dtaas/protection_validation/README.md` |
| R-7 | Minimal Dockerfile, image < 200 MB target, tag `sambps/protection-validation:v1.0` | **MET** (Dockerfile) / **DEFERRED** (image build + push) | `dtaas/protection_validation/docker/Dockerfile`; image push gated on PI green-light per WP5.4 brief |

## 2. Design

### 2.1 Architecture

```
┌────────────────────────────────────────────────────────────┐
│              SAMBPS DTaaS Scenario Engine                  │
│                          │                                 │
│         ┌────────────────┴────────────────┐                │
│         │     scenario_engine_adapter     │                │
│         └────────────────┬────────────────┘                │
└────────────────────────────────────────────────────────────┘
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
       ▼                   ▼                   ▼
┌──────────┐         ┌──────────┐         ┌──────────┐
│   api    │  ◄────► │   cli    │         │    ui    │
│ http.    │         │  Click   │         │ static   │
│ server   │         │          │         │ HTML     │
└────┬─────┘         └────┬─────┘         └────┬─────┘
     │                    │                    │
     ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────┐
│ handle_locate / handle_identifiability_map /        │
│ handle_crlb_envelope / handle_health                │
│   ↓                                                 │
│ WP1.4 / WP2.4 optimiser  +  WP3.5 sigma_min_at  +   │
│ WP3.6 multi-port CRLB                               │
└─────────────────────────────────────────────────────┘
```

The handler functions are decoupled from the HTTP wrapper so the
CLI + scenario-engine adapter share the same code path as the API.

### 2.2 Dependencies

| Component | Source |
|---|---|
| API server | stdlib `http.server` (ThreadingHTTPServer) |
| JSON | stdlib `json` |
| CLI | Click ≥ 8.0 |
| Locator math | numpy, scipy (already in `pyproject.toml`) |
| UI | vanilla HTML5 + JS (no React build chain) |
| Container | python:3.12-slim base |

No new heavy dependencies introduced.

### 2.3 Reference-Twin registry

Three twins are registered at v1.0.0-dtaas:

* `single_line_11kV_100km` — production
* `ieee34` — production
* `hvdc_stub` — preview (full HVDC is future-work)

Adding a twin is a single-line edit to `_REGISTRY` in `api.py`
plus a corresponding row in `dtaas/tests/smoke_test.py::REFERENCE_TWINS`.

## 3. Test

| Test | Coverage | Status |
|---|---|---|
| `dtaas/tests/smoke_test.py::test_handle_locate_returns_sensible_response` | 3 Reference Twins | 3/3 PASS |
| `…::test_handle_identifiability_map_renders` | 3 Reference Twins | 3/3 PASS |
| `…::test_handle_crlb_envelope_renders` | 3 Reference Twins | 3/3 PASS |
| `…::test_handle_health_responds` | 1 | PASS |
| `…::test_http_*` | HTTP wrapper smoke (4 endpoints × 3 twins) | 10/10 PASS |
| `…::test_scenario_engine_adapter_*` | plugin contract | 2/2 PASS |
| `…::test_handle_locate_unknown_network_400` | 400 negative path | PASS |
| `…::test_handle_locate_missing_field_400` | 400 negative path | PASS |
| `tests/test_*` (full project gate at WP5.4 commit time) | 198 PASS + 1 skip + 16 xfail | per `make test` |

`ruff check .` is clean across the whole project.

## 4. Security

| Concern | Mitigation |
|---|---|
| Untrusted input on `/v1/locate` | Strict JSON parse + per-field type / shape checks; bad input returns 400; never invokes shell / file IO. |
| Network exposure | Default bind `0.0.0.0:8080`; deployment guidance in README §1.2 to run behind a reverse proxy with auth (the v1.0 API does not include auth — out of scope, follows from the SAMBPS DTaaS dashboard's auth at the iframe boundary). |
| Dependency surface | No new heavy deps; numpy/scipy/click only.  `pip-audit` clean against the WP5.4 commit. |
| Container hardening | `python:3.12-slim` base; no SUID files; no extra apt packages installed at runtime; pip cache cleared in the same RUN layer. |
| Secrets | No secrets stored, parsed, or logged.  No `.env` files in the repo. |
| Logging | INFO-level via stdlib `logging`; request body NOT logged (PII safety even though phasors are not PII). |

The v1.0 surface is **internal-network only** by deployment convention — any externalisation must add auth + TLS at the reverse-proxy layer; that is a deployment concern, NOT a v1.0 release-blocker per the IITM SDLC checklist's deferred-to-deployment items.

## 5. Documentation

| Artefact | Location | Status |
|---|---|---|
| README + installation + API ref + integration | `dtaas/protection_validation/README.md` | **DONE** |
| Per-module docstrings | each .py file | **DONE** |
| API reference (in README + each handler docstring) | `api.py` + README | **DONE** |
| Citation | README §7 (Phase-3 + Phase-4 + IEEE Access manuscripts; CITATION.cff drops at the tag) | **DONE in README**; CITATION.cff lands at tag |
| Changelog entry | `docs/changelog.md` | **DONE** at WP5.4 commit |
| Architecture diagram | this RRR doc §2.1 | **DONE** |

## 6. Deployment

| Item | Status |
|---|---|
| Dockerfile authored | **DONE** (`dtaas/protection_validation/docker/Dockerfile`) |
| `.dockerignore` excluding heavy artefacts | **DONE** |
| Build verified locally | **DEFERRED** (the `docker build` is gated on PI green-light per WP5.4 brief; image not built at this commit) |
| Image push to `sambps/protection-validation:v1.0` | **DEFERRED** (push gated on PI green-light per WP5.4 brief) |
| Reverse-proxy / TLS guidance | covered in README §1.2 |

## 7. Sign-off

| Role | Reviewer | Date | Signoff |
|---|---|---|---|
| Author / DRI | Anoop Eluvathingal | 2026-05-10 | _self-attested at WP5.4 commit_ |
| Host advisor (IITM) | Prof. K. Shanthi Swarup | _PENDING_ | _PENDING_ |

When the host advisor signs off, replace the Reviewer / Date /
Signoff cells in row 2 above with the signoff line, e.g.:

```
| Host advisor (IITM) | K. Shanthi Swarup | 2026-XX-YY | signed-off |
```

## 8. Open items at this commit

1. **Docker image build + push** — deferred per the WP5.4 STOP gate.
2. **Host-advisor sign-off** — pending Prof. Swarup's pass through
   the deliverables.
3. **CITATION.cff** — drops at the `v1.0.0-dtaas` tag once §7 is
   signed.
4. **HVDC twin upgrade** — `hvdc_stub` is preview only; full HVDC
   is the Phase-6 follow-on track per the WP5.1 Amprion memo.

## 9. Decision

**RRR PASS conditional on PI sign-off.**  All R-1 through R-7
deliverables are met (R-7 image-build deferred per the brief's
explicit STOP gate); the IITM SDLC checklist is satisfied across
requirements / design / test / security / documentation; the
deployment-side docker push is the only deferred item, gated on
the PI's explicit green-light.
