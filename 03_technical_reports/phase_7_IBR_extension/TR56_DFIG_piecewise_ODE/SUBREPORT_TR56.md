# SUBREPORT_TR56 — DFIG Piecewise-ODE Current Model for 87L/87G Protection

**TR ID:** TR-56  
**Full title:** DFIG Piecewise-ODE Current Model for 87L/87G Protection with CUSUM Crowbar Detection  
**Folder:** `03_technical_reports/phase_7_IBR_extension/TR56_DFIG_piecewise_ODE/`  
**Report file:** `main_report56.tex`  
**Generated:** 2026-04-20  
**Target journal:** IEEE Transactions on Energy Conversion  
**Thesis allocation:** Chapter 6, §6.1 — Generator Suite (40/64G/78/81/87G)  
**Cross-linked TRs:** TR-57 (87T SPRT), TR-59 (DFIG ANDES validation), TR-62 (PV 2-parameter IBR model), TR-67 (PSCAD EMT full RSC)

---

## §1 Scope

**What TR-56 IS:**
- A 10-parameter piecewise-ODE model for DFIG stator differential current covering both the RSC-active (pre-crowbar) and post-crowbar fault phases
- A CUSUM-based crowbar firing detector operating on the slip-frequency band power of `i_diff(t)` (diagnostic; hardware crowbar hint used for trip path)
- A two-pass Levenberg–Marquardt (LM) estimator initialised from physics priors and a hardware crowbar time hint, with a tail-window Pass-2 refining only `(ω_s, τ_s)`
- Full deterministic validation: 10-scenario sweep (10/10 PASS), Monte Carlo (7 × 1000 internal + 1000 external, CCR = 100%, P_FA = 0)
- ANDES WTDTA1 (Type-3 wind) simulation validation: 6-case matrix (6/6 correct decisions)

**What TR-56 IS NOT:**
- Not a communication-assisted or network-wide protection scheme
- Not replacing TR-62 (PV IBR model) — the pre-crowbar Phase 1 reuses the TR-62 two-parameter IBR model directly
- Not the full EMT (PSCAD/EMTDC) validation with explicit RSC control loops — deferred to TR-67
- Not a general induction machine model — scoped to DFIG wind turbines under grid fault with crowbar activation

**Unifying problem (Ch. 6, §6.1):** The variable-amplitude slip-frequency DC that appears after crowbar firing cannot be captured by the four-parameter SG model, causing the differential relay (87L or 87G) to misclassify the current as load flow or to assert spuriously on the natural response transient. The SG model produces residual norm ~0.4 pu on DFIG faults, triggering the Stage-2 gate to block the trip — a >30% false-block rate.

---

## §2 State of the Art

Eight references in `references56.bib` bound the novelty:

| Key | Authors | Contribution | Limitation vs. TR-56 |
|---|---|---|---|
| Lopez2007 | López et al., IEEE TEC 2007 | RSC-active IBR current model | No post-crowbar slip-frequency component; no estimator |
| Morren2007 | Morren & de Haan, IEEE TEC 2007 | Analytical post-crowbar stator current (3-component) | Derivation only; no inverse estimation, no protection use |
| Pannell2013 | Pannell et al., IEEE TEC 2010 | Analytical symmetrical dip study | No crowbar detection; no two-pass estimator |
| Hu2010 | Hu & He, EPSR 2010 | Unbalanced DFIG control | Control perspective; not protection |
| Dawei2009 | Xiang et al., IEEE TPD 2006 | HVDC + DFIG coordinated control | Offshore context; no relay model |
| Page1954 | Page, Biometrika 1954 | CUSUM sequential test (foundational) | Statistical theory — adapted here for slip-band detection |
| LjungSystem1999 | Ljung 1999 | System identification theory | General framework — underpins two-pass LM strategy |
| MarquardtAlgorithm | Nocedal & Wright 2006 | Numerical Optimization (LM/TRF) | Algorithmic baseline |

**Novelty claim:** TR-56 is the first framework to (i) combine a piecewise-ODE DFIG model with a physics Jacobian, (ii) detect crowbar firing via CUSUM slip-band power, and (iii) integrate the result into a protection trip/restrain decision with a Stage-2 gate identical to TR-62/TR-57.

---

## §3 Method

### 3.1 DFIG two-phase fault current model

**Phase 1 — RSC-active (t < t_cb):**
```
i_pre(t) = k_ibr · sin(ω₀t + φ_pre)
```
Identical to TR-62 two-parameter IBR model. `k_ibr ∈ [0, 2] pu`; no DC offset; no harmonic.

**Phase 2 — Post-crowbar (t ≥ t_cb):**
```
i_post(t) = I_fund·sin(ω₀t + φ_fund)
           + I_nat·exp(-t_rel/τ_s)·sin(ω_s·t_rel + φ_nat)
           + I_DC·exp(-t_rel/τ_s)
```
where `t_rel = max(t − t_cb, 0)`. Key physics: `I_nat` and `I_DC` share the **same** time constant `τ_s = L_s'/(R_s + R_cb)` — this collinearity reduction eliminates one free parameter (11 → 10).

**Piecewise transition — smoothed Heaviside:**
```
i_diff(t, θ) = H_r(t)·i_pre(t) + H_σ(t)·i_post(t)
H_σ(t) = 1 / (1 + exp(-(t − t_cb)/σ_h)),  σ_h = 0.5 ms
```
`σ_h = 0.5 ms` makes `∂i_diff/∂t_cb` continuous everywhere — essential for gradient-based optimisation. Transition width (10–90%) ≈ 1.1 ms, below the 1 ms sample interval at `f_s = 1000 Hz`.

**10-parameter vector:**
```
θ = [k_ibr, φ_pre, t_cb, I_fund, φ_fund, I_nat, φ_nat, ω_s, τ_s, I_DC] ∈ ℝ¹⁰
```

### 3.2 Parameter bounds

| θ | Lower | Upper | Physical basis |
|---|---|---|---|
| `k_ibr` | 0 | 2 pu | RSC current limit |
| `φ_pre` | −π | +π rad | Pre-fault phase |
| `t_cb` | 0 | 0.30 s | Crowbar firing time |
| `I_fund` | 0 | 5 pu | Post-crowbar fundamental |
| `φ_fund` | −π | +π rad | Post-crowbar phase |
| `I_nat` | 0 | 3 pu | Natural response amplitude |
| `φ_nat` | −π | +π rad | Natural response phase |
| `ω_s` | −115 | +115 rad/s | Slip frequency (`s ∈ [−0.35, +0.35]`) |
| `τ_s` | 0.01 | 0.50 s | `L_s'/(R_s + R_cb)` |
| `I_DC` | 0 | 3 pu | DC aperiodic term |

### 3.3 Analytical Jacobian

All 10 Jacobian columns are closed-form (`jacobian_idiff_dfig` in `dfig_current_model.py`). The `t_cb` column is the most complex:
```
∂i_diff/∂t_cb = −(dH_σ/dt_cb)·i_pre + (dH_σ/dt_cb)·i_post + H_σ·(∂i_post/∂t_cb)
dH_σ/dt_cb = −H_σ·H_r/σ_h
```
Finite-difference verification: all non-`t_cb` columns match to `< 10⁻⁹` absolute error; `t_cb` column matches to `< 0.6 pu·s⁻¹` (< 1% relative, gradient magnitude ≈ 120 pu·s⁻¹ at transition centre).

### 3.4 CUSUM crowbar detector

Crowbar firing causes a 10–30 dB step increase in slip-band power `P_k` (band `[f_lo, f_hi]` Hz, sliding 2-cycle window):
```
g_k = max(0, g_{k-1} + P_k − P_0 − K),  alarm if g_k ≥ h
K = ½(P_post − P_pre) ≈ 4.5·P_0,   h = 1.5·K   [Wald optimal]
```
**2-cycle window rationale:** 1-cycle Hanning main lobe (~100 Hz) floods the slip band with 50 Hz leakage. 2-cycle main lobe (~50 Hz) + Hanning sidelobe rolloff (−31 dB) reduces leakage to ~1% of fundamental power. Band-power estimated from 2048-point zero-padded FFT (resolution ≈ 0.49 Hz).

**CUSUM role:** Diagnostic + `t_cb` initialisation for Pass-1 LM. Trip decision uses hardware crowbar hint (±1 ms bound), not CUSUM output.

### 3.5 Two-pass LM estimator

**Physics-based initial guess `θ⁽⁰⁾`:**
- `t_cb⁽⁰⁾` ← CUSUM estimate (or hardware hint)
- `k_ibr⁽⁰⁾` ← RMS of pre-crowbar half-window
- `I_fund⁽⁰⁾` ← RMS of post-crowbar window
- `I_nat⁽⁰⁾ = 0.3 pu, ω_s⁽⁰⁾ = 31.4 rad/s (5% slip), τ_s⁽⁰⁾ = 0.08 s`
- `I_DC⁽⁰⁾ = 0.1 pu`

**Pass 1:** TRF-LM, all 10 parameters, full window. `f_tol = x_tol = g_tol = 10⁻⁸`, ≤2000 evaluations. Locks `{k_ibr, φ_pre, t_cb, I_fund, φ_fund, I_nat, φ_nat, I_DC}`.

**Pass 2:** Tail window (last 3 cycles). Fixes 8 parameters; refines only `(ω_s, τ_s)`. `tol = 10⁻⁹`, ≤600 evaluations. Resolves the primary identifiability challenge (`ω_s` vs. `τ_s` collinearity, κ_n ≈ 12 in isolation on tail window).

**Condition number monitor:**
```
κ_n = σ_max(J̃) / σ_min(J̃),   J̃ = J · D⁻¹,  D_jj = ‖J[:,j]‖
```
Acceptable bound: `κ_max = 80`. At 10% slip, 3-cycle window: `κ_n ≈ 30`.

### 3.6 Stage-2 trip decision

```
Trip if: f_int ≥ 1  AND  κ_n ≤ 80  AND  ‖r‖/√N ≤ 0.15 pu
f_int = max(Î_fund, k̂_ibr) / I_op,min
```
Identical gate structure to TR-57 (87T) and TR-62 (87L/IBR). Backup: segment-amplitude DFT check (pre-crowbar `k_ibr` / post-crowbar `I_fund`) OR'd with LM gate.

---

## §4 Implementation

### Module tree

```
04_code/sambp/generator/
├── models/
│   └── dfig_current_model.py         # 10-param forward model, analytical Jacobian,
│                                     # CUSUM, physics initial guess
├── inverse_estimation/
│   └── dfig_estimator.py             # Two-pass LM; hardware t_cb hint pinning
├── detection/
│   └── crowbar_cusum.py              # CUSUM crowbar detector (diagnostic)
├── run_tr56a_deterministic_mc.py     # TR-56a study driver: 10-scenario + 7-slip MC
└── outputs/tr56a/
    ├── tr56a_deterministic.csv       # 10-scenario results (10/10 PASS)
    ├── tr56a_mc_metrics.csv          # MC summary: P_D, P_FA, CCR, CUSUM t95
    ├── tr56a_mc_internal.csv         # Per-trial internal results
    ├── tr56a_mc_external.csv         # Per-trial external results
    ├── tr56a_waveforms.png           # Representative waveform fits
    ├── tr56a_ccr_vs_slip.png         # CCR vs. slip bar chart
    ├── tr56a_cusum_cdf.png           # CUSUM detection latency CDF
    └── tr56a_omega_error.png         # ω_s estimate error vs. slip

04_code/sambp/line_diff/
└── run_tr56_andes.py                 # ANDES WTDTA1 validation driver (6-case matrix)
```

### Key public API signatures

```python
# models/dfig_current_model.py
dfig_current_model(t, theta, omega0=2*pi*50, sigma_h=5e-4) -> np.ndarray
jacobian_idiff_dfig(t, theta, omega0=2*pi*50, sigma_h=5e-4) -> np.ndarray  # shape (N,10)
cusum_crowbar_detector(i_diff, fs, slip_band=(1.5, 17.5), n_base=4) -> dict
physics_initial_guess(t, i_diff, t_cb_hint=None) -> np.ndarray  # θ⁽⁰⁾

# inverse_estimation/dfig_estimator.py
estimate_dfig_two_pass(t, i_diff, t_cb_hint=None, tail_cycles=3,
                       bounds=DEFAULT_BOUNDS) -> dict
    # returns: {theta_hat, pass1_theta_hat, success, cost, kappa_n, residual_norm}

# detection/crowbar_cusum.py
CrowbarCUSUM(fs, slip_band=(1.5, 17.5), window_cycles=2, n_base=4)
    .update(i_diff_sample) -> bool  # True = crowbar alarm
    .reset() -> None
    .t_cb_estimate -> float | None
```

---

## §5 Validation

### 5.1 Identifiability sweep — condition number vs. slip

| Slip `s` | `ω_s` (rad/s) | `κ_n` (3-cycle window) |
|---|---|---|
| 3% | 9.4 | 67 |
| 6% | 18.8 | 41 |
| 10% | 31.4 | 30 |
| 15% | 47.1 | 24 |
| 20% | 62.8 | 19 |
| 30% | 94.2 | 15 |
| 35% | 110.0 | 13 |

All `κ_n < 80`. At low slip (s = 3%, κ_n = 67) Pass-2 tail refinement is critical to avoid convergence to a local minimum in `τ_s`.

### 5.2 Deterministic 10-scenario sweep (from `tr56a_deterministic.csv`)

| ID | Description | Expected | Decision | `|Δω|` (rad/s) | PASS |
|---|---|---|---|---|---|
| S1 | No crowbar, healthy (k=0.08) | RESTRAIN | RESTRAIN | — | ✓ |
| S2 | No crowbar, internal 3PH (k=0.50) | TRIP | TRIP | — | ✓ |
| S3 | No crowbar, internal SLG (k=0.25) | TRIP | TRIP | — | ✓ |
| S4 | No crowbar, external (noise only) | RESTRAIN | RESTRAIN | — | ✓ |
| S5 | Crowbar s=6%, internal 3PH | TRIP | TRIP | 25.4 | ✓ |
| S6 | Crowbar s=6%, internal SLG | TRIP | TRIP | 21.7 | ✓ |
| S7 | Crowbar s=15%, internal 3PH | TRIP | TRIP | 44.3 | ✓ |
| S8 | Crowbar s=15%, external | RESTRAIN | RESTRAIN | — | ✓ |
| S9 | Crowbar s=3% (min slip) | TRIP | TRIP | 27.3 | ✓ |
| S10 | Crowbar s=35% (max slip) | TRIP | TRIP | 207.5 | ✓ |
| | **Total** | | | | **10/10** |

Note: Large `|Δω|` at S9/S10 reflects spectral resolution limits at extreme slip — does not affect trip/restrain decision (segment-amplitude backup path active).

### 5.3 Monte Carlo (7 × 1000 internal + 1000 external; from `tr56a_mc_metrics.csv`)

`F_s = 4000 S/s`, 8-cycle window, hardware `T_cb` hint. Per-trial randomisation: `k_ibr ~ U(0.25, 0.80)`, `I_fund ~ U(0.15, 0.9·k_ibr)`, `I_nat ~ U(0.10, 0.40)`, `τ_s ~ U(0.04, 0.12) s`, `T_cb ~ U(30, 60) ms`, `σ_n ~ U(3, 10) mpu`.

| Slip | CCR | ≥0.99? | `|Δω|_med` (rad/s) | CUSUM t95 (ms) | ≤80 ms? |
|---|---|---|---|---|---|
| 3% | 1.0000 | **PASS** | 11.7 | 77.7 | **PASS** |
| 6% | 1.0000 | **PASS** | 19.8 | 77.9 | **PASS** |
| 10% | 1.0000 | **PASS** | 25.8 | 72.1 | **PASS** |
| 15% | 1.0000 | **PASS** | 21.1 | 75.0 | **PASS** |
| 20% | 1.0000 | **PASS** | 22.8 | 70.2 | **PASS** |
| 30% | 1.0000 | **PASS** | 92.8 | 50.1 | **PASS** |
| 35% | 1.0000 | **PASS** | 105.9 | 48.9 | **PASS** |
| External | P_FA = 0.0000 | ≤0.01 **PASS** | — | — | — |

**Overall: P_D = 1.0000; CCR ≥ 99% all slips: PASS; P_FA = 0.**

CUSUM t95 revised target: ≤80 ms (original ≤40 ms not achievable with 3-cycle diagnostic window; hardware trip path operates in ≤20 ms independently).

### 5.4 ANDES WTDTA1 validation (IEEE 14-bus, Bus 8 DFIG, Bus 9 fault)

Configuration: ANDES v1.9 WTDTA1 (Type-3), `R_f ∈ {0.01, 0.10, 0.50} pu`, 87L geometry (external: `i_diff = 0` by construction; internal: remote infeed synthesised from Thévenin).

| Case | Scenario | `R_f` (pu) | Expected | Trip? | `i_diff^pk` (pu) | `Î_sub` (pu) | CUSUM (ms) |
|---|---|---|---|---|---|---|---|
| ext_R001 | External | 0.01 | No trip | **N** | 0 | — | — |
| ext_R010 | External | 0.10 | No trip | **N** | 0 | — | — |
| ext_R050 | External | 0.50 | No trip | **N** | 0 | — | — |
| int_R001 | Internal | 0.01 | Trip | **Y** | 18.72 | 0.735 | 55.0 |
| int_R010 | Internal | 0.10 | Trip | **Y** | 16.21 | 0.511 | 58.1 |
| int_R050 | Internal | 0.50 | Trip | **Y** | 14.87 | 0.395 | 152.6 |

**6/6 correct decisions. Zero false trips. LM convergence confirmed in all internal cases.**  
`Î_sub` decreases monotonically with `R_f` — physically expected (higher fault resistance limits subtransient driving voltage).

---

## §6 Results

**Key quantitative claims verified by TR-56:**

| Metric | Value | Source |
|---|---|---|
| Deterministic sweep | 10/10 PASS | `tr56a_deterministic.csv` |
| Monte Carlo CCR (all slips) | 100% | `tr56a_mc_metrics.csv` |
| P_FA (external) | 0.000 | `tr56a_mc_external.csv` |
| CUSUM t95 (s ≥ 3%) | ≤ 80 ms | `tr56a_mc_metrics.csv` |
| ANDES 6-case matrix | 6/6 correct | `run_tr56_andes.py` |
| Condition number (κ_n) at 10% slip | 30 (< 80) | `main_report56.tex` §6 |
| Jacobian `t_cb` column error | < 0.6 pu·s⁻¹ (< 1%) | self-test |
| SG model false-block rate on DFIG faults | > 30% | Tab. 3, §10 |
| DFIG model false-block rate | < 1% | Tab. 3, §10 |
| DFIG model residual norm | < 0.05 pu (vs. ~0.4 pu SG) | Tab. 3, §10 |

---

## §7 Limitations

**L-1 — High-slip ω_s estimation:** At `s ≥ 30%` the natural response decays within 2–3 post-crowbar cycles (τ_s ≈ 0.05 s). The `|Δω|_med` grows to 93–106 rad/s — poor ω_s recovery. This is a spectral resolution limit, not a protection failure (segment-amplitude backup path corrects). If precise ω_s is needed for condition monitoring, a longer window is required.

**L-2 — Smoothed Heaviside approximation on t_cb Jacobian:** The `t_cb` column uses `H_σ` as a differentiable surrogate for `max(·, 0)` in `t_rel`. Residual Jacobian error ≈ 0.6 pu·s⁻¹ at the transition centre. Negligible for LM convergence (< 1% relative) but limits the theoretical guarantee on the analytical Jacobian.

**L-3 — Single-phase (phase-A) estimator for differential current:** The model is fitted to the scalar `i_diff(t)` waveform. For asymmetric faults (SLG) the differential current is a superposition of positive and negative sequence components; the single-phase model captures the dominant component but may underestimate `I_nat` for severe asymmetric cases.

**L-4 — CUSUM window constraint on detection latency:** The 3-cycle diagnostic window (60 ms) sets a hard lower bound on CUSUM latency. The original ≤40 ms target at `s ≥ 10%` is not achievable with this architecture. Hardware crowbar hint (±1 ms) is the operative input for the LM Pass-1 bound, making CUSUM a backup/diagnostic channel only.

**L-5 — ANDES WTDTA1 vs. full EMT RSC dynamics:** The ANDES Type-3 model uses a simplified RSC representation (no switching harmonics, no current controller saturation). Full EMT validation with PSCAD/EMTDC and explicit RSC control loops is deferred to TR-67. The ANDES validation confirms the relay logic but does not capture RSC gate-blocking transients.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy, andes (v1.9+).

```bash
# 1. Deterministic 10-scenario sweep + 7-slip Monte Carlo
cd /root/phd_thesis/04_code/sambp/generator
python run_tr56a_deterministic_mc.py \
    --output_dir outputs/tr56a/ \
    --fs 4000 \
    --window_cycles 8 \
    --mc_trials 1000

# 2. ANDES WTDTA1 validation (6-case matrix)
cd /root/phd_thesis/04_code/sambp/line_diff
python run_tr56_andes.py \
    --network ieee14_wt3.xlsx \
    --fault_bus 9 \
    --rf_sweep 0.01 0.10 0.50

# 3. Run module self-tests
cd /root/phd_thesis/04_code/sambp/generator
python -m pytest models/ inverse_estimation/ detection/ -v

# 4. Compile TR
cd /root/phd_thesis/03_technical_reports/phase_7_IBR_extension/TR56_DFIG_piecewise_ODE
make
# or: pdflatex main_report56 && bibtex main_report56 && pdflatex main_report56 && pdflatex main_report56
```

**Output files:**
- `outputs/tr56a/tr56a_deterministic.csv` — 10-scenario pass/fail table
- `outputs/tr56a/tr56a_mc_metrics.csv` — P_D, P_FA, CCR, CUSUM t95 per slip
- `outputs/tr56a/tr56a_waveforms.png` — representative LM waveform fits
- `outputs/tr56a/tr56a_ccr_vs_slip.png` — CCR bar chart
- `outputs/tr56a/tr56a_cusum_cdf.png` — detection latency CDF

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report56.tex` read (979 lines) + module tree + output CSV headers. Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report56.tex` and `outputs/tr56a/` are authoritative — this file is a read-only analytical summary.*
