# SUBREPORT_TR62 — Two-Parameter Solar PV Zone Model for IBR-Tolerant 87L

**TR ID:** TR-62  
**Full title:** Two-Parameter Solar PV Zone Model for IBR-Tolerant Line Current Differential Protection (87L)  
**Folder:** `03_technical_reports/phase_7_IBR_extension/TR62_PV_2param_87L/`  
**Report file:** `main_report62.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 7 — IBR Extension  
**Target journal:** IEEE Transactions on Industrial Electronics (companion to ieee\_line\_diff paper)  
**Thesis allocation:** Chapter 4 (line differential) — PV zone model subsection; cited in Ch. 6 via paper_c Phase-2 IBR table  
**Cross-linked TRs:** TR-15 (87L baseline), TR-22/23/24 (TDCS detection floor), TR-56 (DFIG model — shares DDR-based selector), TR-64 (87T PV extension), TR-90 (EMT validation engine), TR-67 (HIL — κ_n=1.00 confirmed in hardware)

---

## §1 Scope

**What TR-62 IS:**
- A **physically-derived two-parameter zone model** `θ_PV = [I_fund, φ] ∈ ℝ²` for PV inverter fault current, replacing the four-parameter SG model `θ_SG = [I_fund, φ, I_DC, τ_DC]` when the differential current has no DC component
- **Proposition 1 (Zero DC Offset):** GFL inverter with SRF current controller produces `i(t) = k_ibr·sin(ω₀t + φ) + O(e^{−ωct})` with transient decaying to <1% within ≤15 ms — proven from dq-frame steady state
- **Proposition 2 (Unit Condition Number):** For an integer number of cycles, `κ_n(J_PV) = 1.000` analytically — proven via Jacobian Gram matrix orthogonality
- A **k_ibr-driven model selector** (DDR + exponential veto) routing each relay cycle to either the 2-parameter PV estimator or the 4-parameter SG estimator
- Validated by three independent streams: analytical proof, ANDES PVD1 time-domain simulation (6 cases), and Python waveform synthesis with 5,000-trial MC

**What TR-62 IS NOT:**
- Not a standalone relay — TR-62 is a drop-in zone model; it plugs into the existing SAMBP 87L Stage-2 confidence gate (TR-15) unchanged
- Not a DFIG model — DDR ∈ [0.05, 0.20] routes DFIG to the 4-parameter path; a dedicated 3-parameter DFIG zone model is TR-56 / deferred
- Not applicable to 87T transformer differential without extension — deferred to TR-64 (note: conceptually straightforward when transformer is energised from a PV-dominated bus with no residual flux)

**Core problem solved:** The 4-parameter SG model suffers `κ_n ≈ 36` at a half-cycle window when fitting a pure sinusoid (PV fault), causing the Stage-2 gate to block for 3–5 cycles. The 2-parameter model achieves `κ_n = 1.00` always, enabling single-cycle (20 ms) trip decisions.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-62 |
|---|---|---|
| Blackburn2006 | Fixed 87L relay | `I_f,min = 0.20 pu`; no IBR model; trip ≥ 60 ms |
| SAMBP TR-17 | Adaptive 87L threshold | `I_f,min = 0.08 pu`; partial IBR; trip ≥ 40 ms |
| SAMBP TR-23/24 | TDCS analytical floor | `I_f,min = 0.058 pu` ✓; trip ≥ 40 ms (4-param SG path) |
| **TR-62 (this)** | **2-param PV model** | **`I_f,min = 0.058 pu`; trip ≥ 20 ms** |

**Novelty:** First derivation of a physics-grounded 2-parameter zone model for PV inverter fault current, with proven κ_n = 1 and demonstrated single-cycle detection — 20 ms vs. 40–60 ms for prior 87L methods.

---

## §3 Method

### 3.1 PV inverter current model (Proposition 1)

SRF current controller dq-frame steady state → ABC-frame:
```
i(t) = k_ibr · sin(ω₀t + φ) + O(e^{−ωc·t})

ωc ≈ 300–800 rad/s → transient decays to < 1% within ts ≤ 15 ms
```

Two-parameter model (after transient settles):
```
i_diff^(PV)(t) = I_fund · sin(ωt + φ),   θ_PV = [I_fund, φ]
```

Detection criterion: `I_fund ≥ I_fund,min = 0.058 pu` (TDCS floor, TR-23/24)

### 3.2 Condition number (Proposition 2)

Jacobian: `J_PV ∈ ℝ^{N×2}`, columns `[sin(ωtk + φ), I_fund·cos(ωtk + φ)]`

For N samples spanning an integer number of cycles:
```
J_PV^T · J_PV = (N/2) · diag(1, I_fund²)

After column normalisation: J_n^T · J_n = I₂  →  σ_max = σ_min = 1  →  κ_n = 1.000
```

**Comparison at key window lengths:**

| Window | κ_n (4-param SG) | κ_n (2-param PV) | Improvement | SG trip delay | PV trip delay |
|---|---|---|---|---|---|
| 0.5 cycle | 35.9 | 1.00 | 36× | 5 cyc | 1 cyc |
| 1.0 cycle | 5.4 | 1.00 | 5.4× | 3 cyc | 1 cyc |
| 2.0 cycles | 3.3 | 1.00 | 3.3× | 2 cyc | 1 cyc |
| 3.0 cycles | 2.9 | 1.00 | 2.9× | 1 cyc | 1 cyc |

Stage-2 gate blocks at κ_n ≥ 30 → 4-param model blocked at 0.5-cycle; 2-param always passes.

### 3.3 k_ibr-driven model selector (Algorithm 1)

**DC Decay Ratio (DDR):**
```
DDR = I_DC / max(I_fund, ε),   ε = 10⁻⁹

Physical ranges:
  PV:   DDR ≤ 0.05
  DFIG: DDR ∈ [0.05, 0.20]
  SG:   DDR ∈ [0.30, 1.50]

Selector threshold: DDR_thresh = 0.15
```

**Exponential veto** (secondary gate):
```
veto ⟺  Δ_peak / I_fund ≥ 2.0

Pure sinusoid: ratio = √2 ≈ 1.41 → passes
SG fault (DC + fundamental): ratio 2.0–3.5 → veto fires → sg selected
Margin: 2.0 / 1.41 = 1.42
```

**Algorithm (per relay cycle):**
1. Compute DDR from 4-param Pass-1 estimate
2. Compute r_Δ = Δ_peak / max(I_fund^(1), I_C,nom)
3. If r_Δ ≥ 2.0: return **sg** (exponential veto)
4. s = max(1 − DDR/0.15, 0)
5. If s > 0: return **pv**, score s; else return **sg**, score s

### 3.4 Unified trip gate

```
TRIP ⟺  I_fund ≥ 0.058 pu        [PV threshold]
       ∧  κ_n < 30                 [Stage-2 gate — always satisfied for PV model]
       ∧  ‖r‖_n < 0.10 pu          [residual gate]
       ∧  n_confirm ≥ 2             [confirm cycles]
```

Minimum trip time under 2-param PV model: **2 cycles × 10 ms = 20 ms** (50 Hz)

### 3.5 TR-90 full EMT validation

Custom `PVEmtEngine` (Python/SciPy, TR-90) replaces PSCAD:
- 8-state ODE: `x = [id, iq, vdc, θ_pll, ε_pll, ξ_id, ξ_iq, ξ_vdc]`
- Integrator: RK45, h_max = 0.1 ms, rtol = 10⁻⁶
- Physics: SRF-PLL + cascaded dq current control + DC-link dynamics

7 scenarios:

| ID | Description | P_e,min (pu) | |i_q|_max (pu) | LVRT |
|---|---|---|---|---|
| S1 | 50% voltage dip, 150 ms | +0.212 | 1.183 | Yes |
| S2 | 20% dip (deep LVRT) | +0.085 | 1.183 | Yes |
| S3 | Irradiance 1.0→0.5 pu | −0.053 | 1.119 | No |
| S4 | Irradiance 1.0→0.3 pu | −0.056 | 1.122 | No |
| S5a | PLL narrow (Kp=20) | +0.212 | 1.183 | Yes |
| S5b | PLL wide (Kp=100) | +0.212 | 1.183 | Yes |
| S6 | Q droop + 50% dip | +0.213 | 1.182 | Yes |

Key EMT findings: DDR < 0.03 in all 5 dip scenarios; LVRT reactive injection correct at I_max = 1.10 pu ceiling; PLL bandwidth (Kp ∈ {20,50,100}) has no impact on 1-cycle detection window; PSCAD fully replaceable.

---

## §4 Implementation

### Module tree

```
04_code/sambp/line_diff/
├── models/
│   ├── line_pv_model.py              # 2-param forward model, analytical Jacobian, κ_n function
│   └── line_model_selector.py        # DDR + delta-ratio veto, select_model(), select_from_4param()
├── inverse_estimation/
│   └── line_pv_estimator.py          # Single-pass LM; same API as line_inverse_estimator
│                                     # Unified entry: estimate_line_zone_adaptive()
└── run_tr62_andes.py                 # ANDES PVD1 6-case validation driver

io_utils/andes_adapter.py             # Extended: disable_togglers param + generic 87L extractor

03_technical_reports/phase_7_IBR_extension/TR62_PV_2param_87L/
├── main_report62.tex                 # This document (1043 lines)
├── references62.bib                  # Bibliography
└── outputs/tr62/
    ├── tr62_results.csv              # ANDES 6-case results
    └── tr62_summary.txt              # Human-readable summary
```

**Key API:**
- `estimate_line_zone_adaptive(i_diff, t, config)` — unified entry point; routes to pv or sg estimator based on model selector
- `select_model(theta_sg_pass1, delta_peak, I_C_nom)` — returns `(model, ibr_score)`
- `compare_condition_numbers(window_lengths)` — reporting utility (κ_n comparison table)

---

## §5 Validation

### 5.1 ANDES PVD1 — 6-case matrix

Network: IEEE 14-bus + 10×PVD1 at Bus 4, k_ibr = 1.1 pu. Protected line: Bus 4 → Bus 5.

| Case | Scenario | R_f (pu) | Expected | Trip? | t_trip (ms) | Î_fund (pu) | κ_n |
|---|---|---|---|---|---|---|---|
| ext_R001 | External | 0.01 | No trip | N | — | — | — |
| ext_R010 | External | 0.10 | No trip | N | — | — | — |
| ext_R050 | External | 0.50 | No trip | N | — | — | — |
| int_R001 | Internal | 0.01 | Trip | Y | 950 | 6.505 | 1.00 |
| int_R010 | Internal | 0.10 | Trip | Y | 950 | 6.306 | 1.00 |
| int_R050 | Internal | 0.50 | Trip | Y | 950 | ≥10.0 | 1.00 |

**6/6 correct.** κ_n = 1.00 measured in every internal case — Proposition 2 confirmed to numerical precision. Note: t_trip = 950 ms reflects the ANDES fault injection timing in this simulation; the estimator itself latches the trip decision in 20 ms from fault inception.

### 5.2 Python deterministic — 9/9 PASS (TR-62a)

| ID | Scenario | k_ibr | R_f | Expected | Decision | t_dec | Pass |
|---|---|---|---|---|---|---|---|
| P1 | Int 3PH k=1.00 | 1.00 | 0.00 | TRIP | TRIP | 20 ms | ✓ |
| P2 | Int 3PH k=0.30 | 0.30 | 0.00 | TRIP | TRIP | 20 ms | ✓ |
| P3 | Int 3PH k=0.10 | 0.10 | 0.00 | TRIP | TRIP | 20 ms | ✓ |
| P4 | Int SLG k=1.00 | 1.00 | 0.00 | TRIP | TRIP | 20 ms | ✓ |
| P5 | Int SLG k=0.80, Rf=0.20 | 0.80 | 0.20 | TRIP | TRIP | 20 ms | ✓ |
| P6 | Int HIF k=0.30, Rf=0.20 | 0.30 | 0.20 | TRIP | TRIP | 20 ms | ✓ |
| P7 | Ext 3PH k=1.00 | 1.00 | 0.00 | RESTRAIN | RESTRAIN | — | ✓ |
| P8 | Ext SLG k=1.00 | 1.00 | 0.00 | RESTRAIN | RESTRAIN | — | ✓ |
| P9 | PV→SG switch k=0.50 | 0.50 | 0.00 | TRIP | TRIP | 20 ms | ✓ |

### 5.3 Monte Carlo (5,000 internal + 5,000 external trials, TR-62a)

| Metric | Value | Target | Result |
|---|---|---|---|
| P_D = P(TRIP \| internal) | 0.9984 | ≥ 0.995 | PASS |
| P_FA = P(TRIP \| external) | 0.0000 | ≤ 0.001 | PASS |
| t_50 (median trip time) | 20.0 ms | ≤ 20 ms | PASS |
| t_95 (95th percentile) | 20.0 ms | ≤ 40 ms | PASS |
| DDR accuracy (correct model select) | 0.9984 | ≥ 0.98 | PASS |

All 5 acceptance criteria met. 8 non-detected internal trials (0.16%): CT amplitude error + pre-fault load offset pushes Î_fund below threshold — correctly RESTRAIN, not false alarms.

### 5.4 Three-stream comparison

| Metric | Analytical | ANDES PVD1 | Python MC |
|---|---|---|---|
| κ_n | 1.000 (proven) | 1.00 (measured) | 1.01 (mean) |
| Correct decisions | 9/9 | 6/6 | 9/9 det., 99.84% MC |
| t_50 | 20 ms | 20 ms | 20 ms |
| P_FA | — | 0/3 | 0.0000 |
| P_D | — | 3/3 | 0.9984 |

### 5.5 TR-67 HIL confirmation

TR-67 reports `κ_n ≤ 1.02` in all 6 PV 87L hardware scenarios (target ≤ 1.05), confirming Proposition 2 holds in physical hardware with real CT secondary signals.

---

## §6 Results

| Metric | Value | Source |
|---|---|---|
| κ_n (PV model, proven) | 1.000 | Proposition 2 |
| κ_n (PV model, measured ANDES) | 1.00 | tr62_results.csv |
| κ_n (PV model, measured HIL) | ≤ 1.02 | TR-67 |
| κ_n improvement vs. 4-param (0.5 cyc) | 36× | Table: kappa_window |
| Minimum trip time | 20 ms | 2-confirm-cycle gate |
| Detection threshold | 0.058 pu | TDCS floor (TR-23/24) |
| ANDES correct decisions | 6/6 | tr62_results.csv |
| Deterministic scenarios | 9/9 PASS | TR-62a Python |
| P_D (MC, internal faults) | 0.9984 | TR-62a MC |
| P_FA (MC, external faults) | 0.0000 | TR-62a MC |
| DDR model-selection accuracy | 0.9984 | TR-62a MC |
| EMT zero-DC confirmation (DDR) | < 0.03 all 5 dip scenarios | TR-90 PVEmtEngine |
| Relay pickup for PV lines | 0.08 pu (vs. 0.15 pu for SG lines) | Novel TR-62 contribution |

---

## §7 Limitations

**L-1 — Pure GFL assumed:** Proposition 1 is proven for a GFL SRF-controlled inverter. Grid-forming (GFM) inverters in virtual synchronous machine (VSM) mode may inject a DC component if the virtual inertia emulation produces a transient current deviation that matches the DC exponential shape. GFM PV protection deferred.

**L-2 — DC transient window [0, ts]:** Proposition 1 guarantees the DC component is < 1% after ts ≤ 15 ms. During the first 15 ms, the 2-parameter model may underestimate I_fund if the 2 confirm-cycle window is shorter than ts. The estimator window starts from the second zero-crossing (≥ 10 ms post-fault), which partially mitigates this — but for PLL bandwidth Kp = 20 (narrow), the zero-crossing jitter adds ~3 ms. Accepted as a minor limitation.

**L-3 — Single-line (87L) only in this TR:** The κ_n = 1 result is for the line differential 87L. Extension to transformer differential (87T) is noted as TR-64 (deferred). Extension to busbar differential (87B) is separate.

**L-4 — DDR threshold not validated for DFIG-PV mixed feeds:** When a line is fed by both DFIG and PV in parallel, the DDR lies in the PV-DFIG overlap region. The selector defaults to sg (4-param) in the overlap; a 3-way classifier (PV/DFIG/SG) is deferred.

**L-5 — EMT validation uses open-source engine, not PSCAD:** `PVEmtEngine` was validated against analytical expectations and ANDES but not against a commercial EMT tool. For regulatory compliance submissions, independent PSCAD or EMTP-ATP cross-validation is recommended.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy; ANDES v1.9 (for ANDES validation only).

```bash
# Run module self-tests
cd /root/phd_thesis/04_code/sambp/line_diff
python models/line_pv_model.py          # κ_n=1.00 confirmed, healthy/fault/near-threshold
python models/line_model_selector.py    # DDR routing + veto self-test
python inverse_estimation/line_pv_estimator.py  # convergence ≤17 iter, κ_n=1.00

# ANDES 6-case validation
python run_tr62_andes.py \
    --output_dir ../../03_technical_reports/phase_7_IBR_extension/TR62_PV_2param_87L/outputs/tr62/

# TR-90 EMT validation (7 scenarios)
cd /root/phd_thesis/04_code/sambp
python tr90_pv_emt_runner.py \
    --scenarios all \
    --output_dir ../../03_technical_reports/phase_8_advanced_extensions/TR90_pscad_emt_replay/outputs/tr90/

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_7_IBR_extension/TR62_PV_2param_87L
pdflatex main_report62 && bibtex main_report62 && \
    pdflatex main_report62 && pdflatex main_report62
```

**Key output files:**
- `outputs/tr62/tr62_results.csv` — ANDES 6-case: case_id, scenario, R_f, expected, trip, t_trip_ms, i_diff_pk, I_fund_hat, kappa_n, lm_success
- `outputs/tr62/tr62_summary.txt` — human-readable pass/fail summary with κ_n table

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report62.tex` read (1043 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report62.tex`, `tr62_results.csv`, and `tr62_summary.txt` are authoritative — this file is a read-only analytical summary.*
