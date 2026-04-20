# SUBREPORT_TR67 — HIL Validation with DFIG and PV Emulators on RTDS

**TR ID:** TR-67  
**Full title:** Hardware-in-the-Loop Validation of SAMBP with DFIG and PV Emulators on RTDS  
**Folder:** `03_technical_reports/phase_7_IBR_extension/TR67_HIL_RTDS/`  
**Report file:** `main_report67.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 7 — IBR Extension (closes TR-67 milestone)  
**Target journal:** IEEE Transactions on Power Delivery  
**Thesis allocation:** Chapter 7, §7.7  
**Prerequisites:** TR-65 (generator suite integration), TR-66 (RTDS plant model)  
**Cross-linked TRs:** TR-56 (DFIG model), TR-57/64 (87T SPRT), TR-58 (EAC/Relay 78), TR-62 (PV model), TR-63 (gen. suite 40/64G/81), paper_c (unified SAMBP)

---

## §1 Scope

**What TR-67 IS:**
- A **62-scenario RTDS HIL campaign** validating all 9 SAMBP protection functions against physical relay hardware (SEL-300G, GE D60) over IEC 61850 Ed2 GOOSE
- **28 core scenarios** (from paper_c) extended with **34 IBR-specific scenarios** covering DFIG (TR-57×6, TR-58×6, TR-62×6, TR-63×6, TR-64×10)
- **Two discrepancy reports** (D1, D2) with root-cause analysis and firmware resolution paths
- **Corridor test** (10/10): all 9 SAMBP functions exercised simultaneously in scenarios 53–62
- **A/D calibration** verification: amplitude 0.11%, phase 0.15°, noise floor 0.001 pu

**What TR-67 IS NOT:**
- Not a new algorithm TR — all algorithms are imported from TR-56..TR-66; TR-67 is purely a validation campaign
- Not a multi-vendor comparison — validation is against SEL-300G (51/78/81/40/64G) and GE D60 (87L/87T/87B/87G) only; ABB REL650 / Siemens 7SA86 are not included
- Not a field commissioning report — the RTDS plant model is a 6-bus surrogate, not a real substation

**Thesis significance:** TR-67 is the final validation milestone before thesis submission. Its 96.8% scenario agreement rate (target ≥95%) provides the empirical evidence cited in Chapter 7 for the effectiveness of the full SAMBP stack including IBR extensions.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-67 |
|---|---|---|
| Kezunovic2010 | RTDS relay testing methodology | Pure SG grid; no IBR emulators |
| Adamiak2013 | IEC 61850 GOOSE for protection | Does not address adaptive IED logic |
| Hooshyar2019 | IBR fault current characteristics | Simulation only; no hardware relay |
| PaperC | 28-scenario SAMBP validation (software) | Software only; no hardware relay loop |
| TR-66 | RTDS plant model setup | Plant only; relay hardware not yet closed |

**Novelty:** First RTDS HIL campaign closing the loop: EMT plant (RTDS) → physical relays (SEL-300G / GE D60) → adaptive IED (SAMBP Python) → GOOSE feedback, with full IBR emulator suite (DFIG + PV) exercising all 9 SAMBP protection functions in 62 scenarios.

---

## §3 Method

### 3.1 Test bench configuration

**RTDS:** GPC-III rack, 18 NOVACOR processors, Δt = 50 μs. 6-bus plant model with:
- 2 × SG (hydro + thermal)
- 1 × Type-3 DFIG wind farm (TR-56 piecewise-ODE model injected via GTNETx2)
- 1 × Type-4 PV farm (TR-62 current-source model)
- IEC 61850 Ed2 GOOSE via GTNETx2 Ethernet card

**Hardware relays:**
- SEL-300G: functions 51/78/81/40/64G; settings loaded from TR-58 Proposition 1 (Relay 78) and TR-63 (40/64G/81)
- GE D60: functions 87L/87T/87B/87G; differential restraint characteristic from TR-57

**SAMBP Python IED:**
- Platform: Linux Xeon workstation (16-core, 3.6 GHz)
- Software: `04_code/sambp/hil/sambp_iied_v1.1/`
- GOOSE publisher/subscriber via libiec61850 Python bindings
- Decision latency: mean 2.8 ms, 99th-pct 3.9 ms, max 4.0 ms → IEC 61850-5 P2 class ✓

### 3.2 GOOSE dataset schema

Each GOOSE dataset packet (100 ms reporting interval, GOCB-triggered on change):
```
{conv_trip, adapt_trip, κ_n, f_int, seq_type}
```
- `conv_trip`: conventional relay assertion (0/1)
- `adapt_trip`: SAMBP adaptive trip decision (0/1)
- `κ_n`: Jacobian condition number (real-time, from LM estimator)
- `f_int`: integrity flag (CT sat / channel anomaly detector)
- `seq_type`: fault type routing label (3PH / SLG / LL / LLG)

### 3.3 Scenario matrix

| Block | TRs covered | Scenarios | Description |
|---|---|---|---|
| Core (paper_c) | All SG functions | 28 | 28-scenario suite from paper_c reproduced in hardware |
| DFIG 87T/87G (TR-57) | 87T SPRT + 87G | 6 | Internal fault with DFIG infeed; SPRT f_int gate |
| Relay 78 IBR (TR-58) | 78 out-of-step | 6 | GFL penetration 0–50%; standard vs. proposed blinder |
| PV 87L (TR-62) | 87L differential | 6 | PV inverter fault current; κ_n=1.00 path |
| Gen suite (TR-63) | 40/64G/81 | 6 | Loss-of-excitation, field ground, underfrequency |
| 87T SPRT II (TR-64) | 87T SPRT expanded | 10 | CT saturation, sympathetic inrush, through-fault |

**Total: 62 scenarios**

### 3.4 Acceptance criteria

| Criterion | Target | Result |
|---|---|---|
| Scenario agreement rate | ≥ 95% | **96.8% (60/62)** ✓ |
| GOOSE 99th-pct latency | ≤ 4 ms (P2) | **3.9 ms** ✓ |
| A/D amplitude error | ≤ 0.5% | **0.11%** ✓ |
| A/D phase error | ≤ 0.5° | **0.15°** ✓ |
| Corridor test (simultaneous 9-function) | 10/10 | **10/10** ✓ |
| Loss-of-comms fallback time | ≤ 4 ms | **2 ms (1 GOOSE cycle)** ✓ |

---

## §4 Implementation

### Module tree

```
04_code/sambp/hil/
├── sambp_iied_v1.1/
│   ├── goose_pub_sub.py          # libiec61850 Python GOOSE publisher/subscriber
│   ├── iied_main.py              # Main decision loop (2.8 ms mean)
│   ├── rocof_bypass.py           # ROCOF averaging bypass (D2 fix; v1.1 change)
│   └── scenario_loader.py        # 62-scenario COMTRADE/FaultCase loader
├── outputs/tr67/
│   ├── tr67_hil_results.csv      # Per-scenario: expected, result, δ_trip, t_trip, κ_n, f_int
│   └── tr67_calibration.csv      # A/D calibration: amplitude, phase, noise per channel
└── rtds_plant/
    └── rtds_6bus_ibr.rsc         # RTDS draft file (6-bus + DFIG + PV)
```

---

## §5 Validation

### 5.1 Overall scenario agreement

**60/62 = 96.8% correct** (target ≥ 95% → PASS)

Breakdown by block:

| Block | Scenarios | Correct | Pass rate |
|---|---|---|---|
| Core (paper_c) | 28 | 28 | 100% |
| DFIG 87T/87G (TR-57) | 6 | 6 | 100% |
| Relay 78 IBR (TR-58) | 6 | 5 | 83% (D1) |
| PV 87L (TR-62) | 6 | 6 | 100% |
| Gen suite (TR-63) | 6 | 5 | 83% (D2) |
| 87T SPRT II (TR-64) | 10 | 10 | 100% |

### 5.2 Discrepancy D1 — Relay 78 S06, +23 ms timing offset

**Scenario:** TR-58 block, S06; GFL penetration 30%, deep fault V_min = 0.10 pu.

**Observation:** SEL-300G Relay 78 trip delayed +23 ms relative to SAMBP adaptive decision. Trip decision correct; timing only.

**Root cause:** SEL-300G SWING_CONFIRM filter = 3-cycle confirmation window (default factory setting). SAMBP blinder crossing detected at cycle boundary; relay requires 3 additional cycles of continuous blinder violation before asserting output contact.

**Resolution:** Reduce SWING_CONFIRM from 3 cycles to 1 cycle in SEL-300G relay word settings. Validated in re-test (not within the 62-scenario matrix — noted as post-campaign action).

**Impact on thesis claims:** None. Trip decision correct; only timing. Proposition 1 blinder coordinates confirmed to cause relay assertion in hardware ✓.

### 5.3 Discrepancy D2 — Relay 81 τ_f = 0.05 s, +22 ms timing offset

**Scenario:** TR-63 gen-suite block; underfrequency, fast ROCOF (τ_f = 0.05 s, R = 2.5 Hz/s).

**Observation:** SEL-300G ROCOF element lagged SAMBP ROCOF estimate by +22 ms. Both asserted correct trip; timing discrepancy only.

**Root cause:** SEL-300G ROCOF uses an 8 ms averaging window hardcoded in firmware (not configurable in this relay generation). SAMBP computes ROCOF from two consecutive GOOSE ω samples (2 ms spacing). For fast events (τ_f = 0.05 s), the 8 ms window introduces 4 × Δt_ROCOF = 22 ms phase lag.

**Resolution:** `sambp_iied_v1.1` firmware patch: SAMBP IED now publishes its own ROCOF estimate via a separate GOOSE dataset; the Relay 81 function in the IED bypasses the SEL-300G ROCOF output for τ_f < 0.10 s events. Source: `04_code/sambp/hil/sambp_iied_v1.1/rocof_bypass.py`.

**Impact on thesis claims:** None. Underfrequency trip decision correct. sambp_iied_v1.1 resolves the 22 ms lag for fast events.

### 5.4 Key functional findings

**(1) SPRT f_int gap confirmed:** For inrush scenario (TR-64, scenarios 59–62), SPRT spike integral f_int = 0.34 pu, well below threshold f_thresh = 1.50 pu. GE D60 differential inhibit correctly suppressed; SAMBP veto confirmed consistent.

**(2) PV κ_n = 1.00 confirmed:** For TR-62 PV fault scenarios, all 6 cases: κ_n ≤ 1.02 (vs. target ≤ 1.05 from paper_c Table IV). LM converged in ≤ 8 iterations. This confirms the κ_n = 1.00 analytical result from TR-62 holds in hardware.

**(3) Relay 78 Proposition 1 confirmed in impedance plane:** For 5/6 TR-58 scenarios, measured impedance trajectory crossed the proposed blinder (δ_LB − 5°) before crossing the standard blinder (π − δ₀). The conservatism direction is confirmed in hardware.

**(4) Loss-of-comms fallback:** GOOSE subscription timeout (simulated by disconnecting Ethernet cable at t = 0.5 s during corridor test scenario 55). GE D60 reverted to conventional differential protection within 2 ms (one GOOSE reporting cycle at 100 ms / 50 = 2 ms change-of-value reporting). No spurious trip during fallback.

### 5.5 Corridor test — scenarios 53–62

All 9 SAMBP functions exercised simultaneously. Max observed GOOSE round-trip: 3.8 ms (within P2 class). All 10/10 scenarios correct. No inter-function interference observed.

### 5.6 A/D calibration

| Channel | Amplitude error | Phase error | Noise floor |
|---|---|---|---|
| ia | 0.10% | 0.14° | 0.001 pu |
| ib | 0.11% | 0.15° | 0.001 pu |
| ic | 0.10% | 0.14° | 0.001 pu |
| va | 0.09% | 0.13° | 0.001 pu |
| vb | 0.11% | 0.15° | 0.001 pu |
| vc | 0.10% | 0.14° | 0.001 pu |

All channels within ±0.5% amplitude and ±0.5° phase specification.

---

## §6 Results

| Metric | Value | Target | Status |
|---|---|---|---|
| Scenario agreement | 60/62 = 96.8% | ≥ 95% | PASS ✓ |
| GOOSE 99th-pct latency | 3.9 ms | ≤ 4 ms (P2) | PASS ✓ |
| GOOSE max latency | 4.0 ms | — | — |
| GOOSE mean latency | 2.8 ms | — | — |
| Corridor test | 10/10 | 10/10 | PASS ✓ |
| A/D amplitude error (max) | 0.11% | ≤ 0.5% | PASS ✓ |
| A/D phase error (max) | 0.15° | ≤ 0.5° | PASS ✓ |
| Loss-of-comms fallback | 2 ms | ≤ 4 ms | PASS ✓ |
| SPRT f_int (inrush) | 0.34 pu | < 1.50 pu | PASS ✓ |
| PV κ_n (hardware) | ≤ 1.02 | ≤ 1.05 | PASS ✓ |
| D1 (Relay 78 timing) | +23 ms (correct trip) | — | Noted |
| D2 (ROCOF lag) | +22 ms (correct trip) | — | Fixed v1.1 |

---

## §7 Limitations

**L-1 — 6-bus surrogate plant only:** The RTDS model is a 6-bus surrogate, not a full-scale network. Results are validated for the surrogate topology; extrapolation to multi-voltage-level networks (e.g., IEEE 39-bus) requires additional HIL scenarios.

**L-2 — Two relays only (SEL-300G + GE D60):** Validation is against one SEL and one GE relay family. Other relay manufacturers (ABB REL650, Siemens 7SA86) may have different firmware filter behaviour — particularly SWING_CONFIRM (D1) and ROCOF averaging (D2).

**L-3 — D1 resolution not re-tested in the 62-scenario matrix:** SWING_CONFIRM = 1-cycle recommendation was validated informally post-campaign but not formally re-included as a 63rd scenario. Formal re-test recommended before relay settings are applied to a real substation.

**L-4 — ROCOF bypass (D2) not independently peer-reviewed:** `rocof_bypass.py` in sambp_iied_v1.1 is a software-only fix. It requires IED clock synchronisation to GPS (IEEE 1588 PTP) to be accurate; if clock sync fails, ROCOF estimate degrades to ±50 mHz/s. Noted as a field deployment prerequisite.

**L-5 — No type-test or EMC:** SAMBP Python IED hardware platform (Linux Xeon workstation) has not undergone IEC 60255-26 EMC testing or IEC 60255-27 safety testing required for substation deployment. This is a research prototype.

---

## §8 Reproduction Recipe

**Prerequisites:** RTDS GPC-III access, SEL-300G + GE D60 with GOOSE Ethernet ports, Python ≥ 3.10, libiec61850 Python bindings.

```bash
# Run SAMBP IED (requires RTDS plant running + relays connected)
cd /root/phd_thesis/04_code/sambp/hil/sambp_iied_v1.1
python iied_main.py \
    --scenario_csv ../outputs/tr67/tr67_hil_results.csv \
    --goose_interface eth0 \
    --log_dir ../outputs/tr67/

# Post-process results (no RTDS required — uses tr67_hil_results.csv)
cd /root/phd_thesis/04_code/sambp/hil
python analyse_tr67_results.py \
    --results_csv outputs/tr67/tr67_hil_results.csv \
    --calib_csv outputs/tr67/tr67_calibration.csv \
    --output_dir outputs/tr67/analysis/

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_7_IBR_extension/TR67_HIL_RTDS
pdflatex main_report67 && bibtex main_report67 && \
    pdflatex main_report67 && pdflatex main_report67
```

**Key output files:**
- `tr67_hil_results.csv` — 62 rows: scenario_id, block, expected, result, d_trip_deg, t_trip_ms, kappa_n, f_int, seq_type, pass_fail, discrepancy_note
- `tr67_calibration.csv` — 6 rows (one per CT/VT channel): amplitude_err_pct, phase_err_deg, noise_floor_pu

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report67.tex` read (599 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report67.tex` and `tr67_hil_results.csv` are authoritative — this file is a read-only analytical summary.*
