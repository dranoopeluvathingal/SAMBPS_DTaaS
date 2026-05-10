# SAMBPS DTaaS Flagship · Project Charter

**Version:** 0.1 (2026-04-25 · initial)
**Owner:** Anoop V. Eluvathingal
**Host lab:** IIT Madras, Power Systems Computational Lab (Prof. K. Shanti Swarup)
**Status:** LIVING — update when scope, objectives, or deliverables change

---

## 1 · Research objective

Design, formalize, validate, and commercialize a **self-adaptive, model-based protection architecture** for IBR-dominated transmission, sub-transmission, and HVDC networks, delivered as a cloud Digital-Twin-as-a-Service (DTaaS) platform. The architecture must:

- Adapt relay settings online to changing IBR fault contributions (GFM/GFL share, k_ibr).
- Use the digital twin as a **state-validating and trajectory-predicting** layer.
- Maintain protection coordination under HVDC commutation, MMC fault behavior, and meshed IBR topology.
- Operate compatibly with IEC 61850 GOOSE, with HMAC-authenticated messaging.
- Scale to multi-substation federated learning for relay coordination.

## 2 · Scope

### In scope
- IBR-dominated transmission and sub-transmission (typ. 110–765 kV).
- HVDC protection: LCC, VSC, MMC topologies (TR-H01+).
- Adaptive line differential (87L) with IBR k_ibr compensation.
- Wavelet (DWT) multi-phase fault logic.
- GFM / GFL estimator: EKF, RLS, PINN approaches.
- DT trajectory prediction for protection decision support.
- Cross-substation federated learning for relay coordination (TR-90).
- HIL validation (TR-98 SEL-411L).
- SAMS Digital Twin cloud platform; SAMS Architect AI research-design engine.

### Out of scope (explicitly)
- Distribution-level FLISR / self-healing (covered by MAS–DT-SH).
- Multi-agent coordination at feeder level (MAS–DT-SH).
- DER-rich distribution operations.

### Adjacent but tracked via crosswalk
See `00_governance/sambps_crosswalk.md`. Reciprocal of the MAS–DT-SH crosswalk.

## 3 · Deliverable categories

| # | Category | Folder | Primary artefacts |
|---|---|---|---|
| D1 | Thesis manuscript (SAMBPS-side, future) | `01_thesis/` | Ch1–Ch7 |
| D2 | Journal / conference papers | `02_papers/` | Submission packages (APPEEC 2026 active) |
| D3 | Technical reports | `03_technical_reports/` | TR-01 .. TR-98+, TR-H01+ |
| D4 | Code package | `04_code/sambp_dt_lab/` | `sambp-dt-lab-v0.x` |
| D5 | Simulation data | `05_data/` | HVDC / IBR / COMTRADE |
| D6 | Presentations | `06_presentations/` | DC / conference / utility-pitch decks |
| D7 | External deliverables | `07_deliverables/` | Assessments, status reports |
| D8 | References / bibliography | `08_references/` | `.bib`, reading list |

## 4 · Active submissions (Apr 2026)

| Paper | Topic | TR backing | Folder | Deadline |
|---|---|---|---|---|
| P1 | HVDC adaptive protection | TR-H01+ | `02_papers/appeec_2026/01_hvdc_adaptive_protection/` | Thu 30 Apr 11:00 IST |
| P2 | GFM/GFL estimator (EKF/RLS/PINN) | TR-77, TR-91 | `02_papers/appeec_2026/02_gfm_gfl_estimator/` | Thu 30 Apr 11:00 IST |
| P3 | DT trajectory prediction | TR-43–45 | `02_papers/appeec_2026/03_dt_trajectory_prediction/` | Thu 30 Apr 11:00 IST |
| P4 | TR-90 federated learning | TR-90 | `02_papers/appeec_2026/04_tr90_federated_learning/` | Thu 30 Apr 11:00 IST |

All 4 framed for NUS ECE / GEMS topic territory + distribution-systems lens (per Dipti outreach plan).

## 5 · Milestones

| ID | Milestone | Target | Status |
|---|---|---|---|
| MS1 | SAMBPS_FLAGSHIP scaffold + charter committed | 2026-04-25 | Done (this commit) |
| MS2 | APPEEC 2026 submission (4 papers) | Thu 30 Apr 11:00 IST | Open — co-author review Mon Apr 27, polish Wed Apr 29 |
| MS3 | Dipti / NUS outreach Draft A landed | Tue 28 Apr | Open |
| MS4 | Yan Xu / NTU Draft B landed | Wed 29 Apr | Open |
| MS5 | Europe coordination (TU Dortmund / Amprion) — pipeline alignment | Thu 30 Apr 15:00 IST | Open (recurring) |
| MS6 | Populate `03_technical_reports/TR_INDEX.md` with all SAMBPS TRs referenced in Ch1–Ch5 | +2 weeks | Open |
| MS7 | First `sambp-dt-lab` release notes (v0.1) | +6 weeks | Open |

## 6 · Governance

- **Canonical naming** per `00_governance/canonical_naming.md`. Hyphen vs. en-dash matters; do not deviate in external artefacts.
- **Decisions** as ADRs in `00_governance/decisions/`.
- **Cross-contamination rule** — SAMBPS artefacts do not duplicate MAS–DT-SH content unless logged in the reciprocal crosswalk.
- **Version control** — full `SAMBPS_FLAGSHIP/` tree to be checked into a dedicated git repo at MS6.

## 7 · Risks

| ID | Risk | L × I | Mitigation |
|---|---|---|---|
| R-SF1 | APPEEC 4-paper submission misses deadline | Med × **High** | Wed 13:30–18:00 polish block; co-author review Mon |
| R-SF2 | Scope drift into MAS–DT-SH (distribution) | Med × Med | Crosswalk file + canonical naming |
| R-SF3 | TR-INDEX gap — many SAMBPS TRs referenced but not yet drafted in this folder | High × Med | MS6 populates index; TRs migrated incrementally |
| R-SF4 | Dipti / NUS outreach territorial friction with Yan Xu / NTU | Low × Med | Draft B explicitly references parallel Dipti contact |
| R-SF5 | Co-author feedback delayed past Tue evening | Med × **High** | Mon 10:30–13:00 explicit ask for Tue-evening turnaround |

---

_Next revision expected after MS2 (APPEEC submission) — outcome will reshape MS3–MS5 timing._
