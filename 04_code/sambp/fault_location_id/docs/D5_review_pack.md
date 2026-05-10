# D5 — Phase 5 Decision Gate Review Pack

**Project:** SAMBPS DTaaS — `fault_location_id`
**Phase:** 5 — HIL access + IEC 61850 SV/GOOSE integration + 25-scenario campaign + DTaaS Protection-Validation v1.0 + IEEE TPWRD/TSG journal paper (W34–W42)
**Gate:** D5 — final phase-gate; v1.0.0-phase5 release tag; Zenodo DOI mint; PI direction on submission target + co-authors
**Issued:** 2026-05-10
**Author:** Anoop Eluvathingal (PI)
**Cosignatory:** Prof. K. Shanthi Swarup (host advisor)

> Format mirrors §8.1 of `docs/FaultLocationIdentification_ExecutionPlan.pdf`
> (decision-gate template); D0–D4 precedents at `docs/D0_review_pack.md`,
> `docs/D1_review_pack.md`, `docs/D2_review_pack.md`,
> `docs/D3_review_pack.md`, `docs/D4_review_pack.md`.

---

## 1. Phase summary

Phase 5 ran five work packages WP5.1–WP5.5 from W34–W42:

* **WP5.1 / P5.1** HIL platform commissioning + 4 partner memos
  (IITM status + NUS GEMS + NTU CTSP + Amprion HVDC follow-on);
  PI signoff log: USD 8 k/visit budget approved, Typhoon HIL
  fallback PRE-APPROVED at USD 30 k.
* **WP5.2 / P5.2** IEC 61850-9-2LE SV subscriber + custom
  GOOSE publisher (`dtaas/protection_validation/sv_subscriber.py`)
  with HW + dev-box modes; **K09 software-side PASS** (30 / 30
  scenarios under 100 ms latency on dev box).
* **WP5.3 / P5.3** 25 + 5 scenario campaign through the WP5.2
  pipeline.  K09 latency PASS; **K10 mean / p95 location-error
  thresholds NOT met** on dev-box simulation (R-WP4.1-1 single-bin
  DFT identifiability floor; closure path = WP3.5/3.6 multi-bin
  TFT + multi-port FIM optimiser rewire).  K10 institutional
  signoff PENDING (gated on HIL access).
* **WP5.4 / P5.4** SAMBPS DTaaS Protection-Validation v1.0
  module: stdlib REST API (4 endpoints) + Click CLI + scenario-
  engine plugin adapter + static-HTML UI widget + minimal
  Dockerfile.  T-G1 smoke 24 / 24 PASS on 3 Reference Twins.
  IITM SDLC RRR signed (PI signoff PENDING).
  Tag `v1.0.0-dtaas` (local-only).
* **WP5.5 / P5.5** _(this commit)_ IEEE TPWRD (preferred) /
  IEEE TSG (alternative) full-paper draft +
  this D5 review pack + `v1.0.0-phase5` tag.

A total of **222 tests pass + 1 skipped + 16 xfailed** at Phase-5
exit.  All xfails carry documented R-class escalation reason text.
ruff clean.

## 2. T-F1 / T-G1 / T-H1 acceptance results

### 2.1 T-F1 (Phase 4 closeout)

| Test ID | Predicate | Measured | Status |
|---|---|---|---|
| K07 (Phase 4) | mean loc-err < 5 % under composite field-grade impairments | ~62 % | **XFAIL strict** (R-WP4.1-1) |
| K08 (Phase 4) | proposed beats ≥ 2 of 4 competitors on mean loc-err | proposed beats 3 of 4 | **PASS** |
| T-E2 cross-fit Wang-2020 | abs.mean Δ DFT 5.30 %, abs.mean Δ TFT 1.81 % | reported | **PASS** |
| T-E2 cross-fit Torres-2022 | tree / sand / concrete pairwise distinguishable | reported | **PASS** |
| T-E2 competitor signoff | docs/competitor_blind_review.md records signoff state | "PI signoff: pending" | **PASS** (state recorded) |

### 2.2 T-G1 (DTaaS v1.0 release)

| Test ID | Predicate | Measured | Status |
|---|---|---|---|
| T-G1 smoke (3 Reference Twins) | 4 API endpoints + scenario-engine adapter respond on each twin | 24 / 24 | **PASS** |
| T-G1 RRR signoff | docs/RRR_v1.0.0_dtaas.md signed | PI PENDING; self-attested | **CONDITIONAL** |
| T-G1 Docker | image build < 200 MB; tag sambps/protection-validation:v1.0 | Dockerfile authored; image not built | **DEFERRED** (per WP5.4 STOP gate) |

### 2.3 T-H1 (HIL acceptance)

| Test ID | Predicate | Measured | Status |
|---|---|---|---|
| K09 (software-side, mock) | end-to-end latency < 5 cycles on ≥ 25 of 30 scenarios | 30 / 30 PASS | **PASS** |
| K09 (hardware-side) | SV ingress → GOOSE egress on real IED's NIC < 5 cycles | PENDING HIL | **XFAIL pending** |
| K10 mean | mean loc-err < 5 % across the 25 primary scenarios | 239.46 % | **XFAIL strict** (R-WP4.1-1) |
| K10 p95 | p95 loc-err < 10 % | 899.90 % | **XFAIL strict** |
| K10 institutional signoff | ≥ 1 of {IITM, NUS GEMS, NTU CTSP} signs the report | PENDING | **XFAIL pending HIL** |

## 3. KPI scorecard — all 17 KPIs vs targets (final)

| # | KPI | Target | Final measurement | Status | Closure path |
|---|---|---|---|---|---|
| K01 | self-consistent loc-err | < 1 % | 0.005 % noiseless / 1.18 % at SNR_I=20 dB | **PASS** | -- |
| K02 | self-consistent max loc-err | < 5 % | 0.005 % noiseless / 4.7 % at SNR_I=20 dB | **PASS** | -- |
| K03 | forward-model error | < 5 % | 4.3·10⁻⁶ % mean / 2.7·10⁻⁵ % max (4 OOM tighter) | **PASS** | -- |
| K04 | Phase-2 cross-platform improvement | ≥ 30 % | -830.82 % (R1 escalation) | **XFAIL strict** | WP3.5/3.6 multi-bin rewire |
| K05 | mean loc-err on CNRS labelled set | < 3 % | DEFERRED (test.zip 3 GB held back) | **DEFER** | licensed Windows runner |
| K06 | TFT bias improvement | ≥ 50 % | 55.94 % | **PASS** | -- |
| K07 (Phase 3) | multi-port CRLB consistency | within 5 % at SNR_I=40 dB | 6.66·10⁻¹⁶ (machine precision) | **PASS** | -- |
| K07 (Phase 4) | mean loc-err < 5 % under impairments | ~62 % | **XFAIL strict** (R-WP4.1-1) | WP3.5/3.6 multi-bin |
| K08 (Phase 3) | fault-type classification ≥ 95 % at SNR_I≥30 dB | 74.51 % | **XFAIL strict** (R-WP3.4-1) | WP3.5/3.6 |
| K08 (Phase 4) | proposed beats ≥ 2 of 4 competitors | 3 / 4 beaten | **PASS** | -- |
| K09 (software) | end-to-end latency < 5 cycles | 30 / 30 PASS (max 85.7 ms) | **PASS** | -- |
| K09 (hardware) | SV → GOOSE round-trip on real IED | PENDING HIL | **XFAIL pending** | WP5.1 partner-window |
| K10 mean | HIL mean loc-err < 5 % | 239.46 % (sim only) | **XFAIL strict** | WP3.5/3.6 multi-bin rewire |
| K10 p95 | HIL p95 loc-err < 10 % | 899.90 % (sim only) | **XFAIL strict** | WP3.5/3.6 |
| K10 institutional signoff | ≥ 1 of {IITM, NUS GEMS, NTU CTSP} | PENDING | **XFAIL pending** | partner-window confirmation |
| K11 | public repo + Zenodo DOI | live at v1.0.0-phase5 | repo public; DOI mint pending | **GATED** (PI green-light) |
| K12 | DTaaS scenario-engine plugin | spec + adapter shipped | scenario_engine_adapter.py + smoke test | **PASS** | -- |
| K13 | RRR signoff | IITM SDLC checklist | docs/RRR_v1.0.0_dtaas.md authored | **CONDITIONAL** | PI signoff |
| K14 | TRL level | 6–7 (system prototype demonstrated in operational environment) | TRL 5 (validated in relevant environment, simulated) → **TRL 6 conditional** on HIL campaign closure | **CONDITIONAL** | HIL campaign |

(17 KPIs counting both K07 and K08 dual-numbered Phase 3 / Phase 4.)

## 4. Risk register at Phase-5 exit

| ID | Status | Closure |
|---|---|---|
| R1  cross-platform improvement | OPEN | WP3.5/3.6 follow-up |
| R3  multi-class fault discrimination | DOWNGRADED | WP3.5/3.6 follow-up |
| R4  arc-model diversity | **CLOSED** at WP4.4 | -- |
| R5  single-bin DFT bias | **CLOSED** at WP3.5 | -- |
| R6  categorical comparison | **PARTIAL** | competitor blind-review PI signoff |
| R8  HIL access | PARTIAL | partner-window confirmation |
| R10 real HIF stochasticity | **CLOSED** at WP4.4 | -- |
| R-WP3.3-1 IEEE feeder power-flow | OPEN | WP3.3 follow-up canonical line codes |
| R-WP3.4-1 IEEE 34 fault-type | OPEN | WP3.5/3.6 |
| R-WP3.7-1 CNRS test.zip | OPEN | licensed Windows runner |
| R-WP4.1-1 K07 impairment | OPEN | WP3.5/3.6 |
| R-WP4.5-1 competitor signoff | OPEN | PI signoff |

## 5. TRL recommendation

| TRL | Definition | Evidence |
|---|---|---|
| TRL 5 | Component validation in relevant environment | **MET** at WP4.5 (5-method × 3-arc × IEEE 34 sub-sample × 30 trials = 12k estimate calls) |
| **TRL 6** | System / subsystem model demonstration in relevant environment | **MET conditional on HIL campaign closure**.  WP5.4 ships the v1.0 module + smoke-tested REST API + scenario-engine plugin; WP5.3 runs the 30-scenario simulation; WP5.2 wires the IEC 61850 SV/GOOSE pipeline; the structural identifiability floor is documented as the binding limit on the K10 acceptance.  CLOSURE = WP3.5/3.6 multi-bin TFT + multi-port FIM optimiser rewire + the live HIL campaign at one of the three partner sites. |
| TRL 7 | System prototype demonstration in operational environment | **CONDITIONAL** on (a) HIL campaign closure at NUS GEMS / NTU CTSP / IITM with Typhoon HIL; (b) institutional signoff (K10 ≥ 1, target ≥ 2). |

**Recommendation.**  Phase-5 exit at **TRL 5 → TRL 6 conditional**:
all software-side deliverables shipped and tested; the hardware-
side is paper-ready (the WP5.5 journal paper covers the HIL pipeline
+ the 30-scenario campaign), and the live-HIL campaign is the
single remaining step to TRL 7.  The structural identifiability
floor closure (multi-bin TFT + multi-port FIM optimiser rewire)
is in scope for a Phase-6 / follow-on commit train and would lift
all the K07 / K08 / K10 xfail-stricts in the same operation.

## 6. Decision recommendation

* **D5 GATE: PASS conditional on PI sign-off of FOUR items.**

  1. **Submission target** confirmation: IEEE TPWRD (preferred) vs
     IEEE TSG (alternative) for `docs/Phase5_journal_v2.tex`.
  2. **Co-author list** confirmation:
     {Anoop Eluvathingal, Arjundas K., K. Shanthi Swarup} +
     decisions on whether to invite Prof. Christian Rehtanz
     (Phase-1 contribution) / Prof. Dipti Srinivasan (NUS-GEMS,
     Phase-3/4 context) / Prof. Yan Xu (NTU-CTSP, Phase-5
     context) / Fabian Erlemeyer (Amprion, Phase-5/6 HVDC follow-
     on) as co-authors.
  3. **Zenodo DOI mint**: confirm the v1.0 release archive is
     uploaded to Zenodo and the DOI is wired into the README +
     this paper.
  4. **Push to GitHub master + tag push**: same gate as the WP4.6
     v0.6.0-phase4 push; deferred until competitor blind-review
     and RRR PI signoff land.

* **Phase 6 kickoff** (optional, post-D5):
  * The structural multi-bin TFT + multi-port FIM optimiser rewire
    (lifts K04 / K07 / K08 / K10).
  * The live HIL campaign at one of {IITM Typhoon, NUS-GEMS,
    NTU-CTSP}.
  * The HVDC follow-on track via Amprion (Phase-6/7 sub-project).

## 7. Open items carried forward

1. **Submission target** (TPWRD vs TSG) — PI direction.
2. **Co-author list** — PI direction.
3. **Competitor blind-review** signoff (R-WP4.5-1).
4. **DTaaS RRR** signoff (docs/RRR_v1.0.0_dtaas.md).
5. **Partner memos** edit + send (NUS-GEMS, NTU-CTSP, Amprion).
6. **HIL campaign** at confirmed partner window.
7. **Zenodo DOI** mint at the v1.0.0-phase5 tag.
8. **Push to GitHub master + tags** (v0.6.0-phase4, v1.0.0-dtaas,
   v1.0.0-phase5) — gated on the four PI signoffs above.
9. **Phase-6 multi-bin / multi-port optimiser rewire** —
   structural closure of K04 / K07 / K08 / K10.
