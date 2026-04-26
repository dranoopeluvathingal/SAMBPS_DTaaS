# SUBREPORT_TR01 — Inverse-Estimation-Based Adaptive OC Protection (SyncOC Milestone 1)

**TR ID:** TR-01  
**Full title:** Inverse-Estimation-Based Adaptive Overcurrent Protection for Synchronous Generators in Active Distribution Networks  
**Ref:** IITM/EE/PhD/AVE/TR-01/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR01_sync_oc_foundation/`  
**Report file:** `main_report1.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework (Milestone 1)  
**Target journal:** IEEE Transactions on Power Delivery  
**Thesis allocation:** Chapter 3 (OC protection) / Chapter 6 (generator suite) — foundational framework  
**Cross-linked TRs:** TR-02 (extensions: HIF, Park dq, sequence, coordination), paper_a (journal submission of this work), paper_b (M3+M4 extend TR-01/02 to asymmetric faults + cascade coordination)

---

## §1 Scope

**What TR-01 IS:**
- The **foundational SAMBP-SyncOC framework**: six-parameter physics-derived reduced fault current model + two-pass Levenberg–Marquardt estimator + four-component confidence gate + bounded adaptive update law
- **Proposition (Current Continuity):** `I_dc,k = −I_sub·sin(φ_k)` — derives the DC offset amplitude from the pre-fault zero-current initial condition, eliminating a free parameter and reducing κ_n from ~10⁸ to < 20
- Demonstrated on 3 study cases (3PH, LL, SLG) with R² > 0.999, γ ∈ [0.89, 0.93], ~60% spurious pickup reduction
- Milestone 1 of the sambp_sync_oc development trajectory

**What TR-01 IS NOT:**
- Not validated on high-impedance faults (R_f > 0.5 pu) — deferred to TR-02 Milestone 2
- Not a multi-generator framework — single SG on Thévenin equivalent only; multi-generator coordination deferred to TR-02
- Not using AVR/PSS dynamics — Stage 1 three-component synthesis model; Stage 2 (Park dq ODE) is TR-02

**Core problem solved:** Fixed OC relay settings calibrated at commissioning produce systematic mis-coordination in ADNs (variable load, IBR, topology changes). TR-01 provides real-time online identification of the fault current model and bounded adaptive relay setting update.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-01 |
|---|---|---|
| Phadke2009 | Formalised adaptive relaying philosophy | No source parameter inference from local measurements |
| Brahma2004 | Adaptive OC for feeders with DG | Assumes generator parameters known a priori |
| Oudalov2009 | Communication-based adaptive MG protection | Requires central controller, complete network observability |
| Girgis1992 | Recursive LS for fault location | Linear voltage-drop model; not nonlinear fault current |
| IEC60255-151 | IEC Very-Inverse OC standard | Fixed settings; no inverse problem formulation |

**Novelty:** First bounded nonlinear least-squares formulation for SG OC relay adaptation from local current measurements, with physics-derived DC constraint eliminating collinearity and a four-component confidence gate governing adaptation decisions.

---

## §3 Method

### 3.1 System

SG + Thévenin network. Parameters: Xd=1.80, Xd'=0.30, Xd''=0.20 pu; Td'=0.80s, Td''=0.030s; Ra=0.010 pu; P0=0.80 pu, Q0=0.20 pu; Rth=0.010, Xth=0.150 pu. IEC Very-Inverse relay: Ip=1.200 pu, TMS=0.050, Iinst=2.500 pu.

### 3.2 Reduced-order fault current model (Stage 1)

```
i_k(t) = [I_ss + (I_sub − I_ss)·e^{−t_rel/τ_ac}]·sin(ωt + φ_k)
         − I_sub·sin(φ_k)·e^{−t_rel/τ_dc},   t ≥ t₀

θ = [t₀, I_ss, I_sub, τ_ac, τ_dc, φ_a] ∈ ℝ⁶
```

**Physics constraint (current continuity at fault inception):**
```
i_k(t₀) = 0  ⟹  I_dc,k = −I_sub·sin(φ_k)
```
This eliminates the free I_dc parameter. Without the constraint, κ_n ~ 10⁸; with it, κ_n < 20.

**Phase-A only residual:** Three-phase concatenated residual suffers DC cross-cancellation (sin φ_a + sin φ_b + sin φ_c = 0); phase-A alone preserves full DC information.

### 3.3 Two-pass Levenberg–Marquardt estimator (Algorithm 1)

```
Pass 1: Full window, all 6 parameters free (TRF solver)
  → Reliable: t₀, I_sub, τ_dc, φ_a (transient parameters — dominant early in window)

Pass 2: Tail window (last 2 cycles ≈ 40 ms), 2 free parameters {I_ss, τ_ac}
  → Pass-1 transient params fixed; well-conditioned tail (κ_n < 10)
  → Reliable: I_ss, τ_ac (AC envelope has settled in tail)

Merge → full θ̂; recompute residual r and Jacobian J
```

Convergence: ‖J^T r‖_∞ ≤ 10⁻⁸ or ‖Δθ‖ ≤ 10⁻⁸

### 3.4 Composite confidence score

```
γ = w_r·s_r + w_c·s_c + w_b·s_b + w_p·s_p,   γ_th = 0.70
weights: (0.35, 0.30, 0.20, 0.15)

s_r = exp(−‖r‖₂ / (N^{1/2}·0.15))         [normalised residual norm]
s_c = log-linear map κ_n ∈ [10 (good), 500 (bad)] → [1, 0]
s_b = 1 − n_bound/6                          [bounds-hit fraction]
s_p = 1 − 0.50·𝟙[I_sub ≤ I_ss]
      − 0.30·𝟙[τ_dc ∉ [5ms, 500ms]]
      − 0.20·𝟙[τ_ac ∉ [3ms, 1s]]            [physics plausibility]
```

### 3.5 Bounded adaptive update law

```
I_p* = α_I · Î_ss,         α_I = 0.80
TMS* = α_TMS · τ̂_ac,      α_TMS = 0.12

Rate-limit: ΔI_p = clip(I_p* − I_p^current, [−δ_I, +δ_I]),  δ_I = 1.0 pu
Hard clip: I_p^final = clip(I_p^current + ΔI_p, [1.1, 3.0] pu)
```

Security preservation: I_p^final ≥ I_load,max guaranteed by clip bounds + α_I = 0.80 calibration.

### 3.6 IEC Very-Inverse relay

```
t_op(M) = TMS · 13.5 / (M − 1),   M = I_rms / I_p > 1

Integration element: ∫ dt / t_op(M(t)) = 1  (accumulates toward trip)
Instantaneous element: I_rms ≥ I_inst → trip immediately
```

---

## §4 Implementation

### Module tree

```
04_code/sambp/sync_oc/
├── models/
│   └── fault_current_model.py          # 3-component synthesis (Stage 1)
├── inverse_estimation/
│   ├── parameter_estimator.py          # Two-pass LM (TRF), 6-param θ
│   └── objective_functions.py          # residual_vector_phaseA()
├── adaptation/
│   ├── bounded_update.py               # clip_relay_settings(), apply_bounded_update()
│   └── adaptive_mapping.py             # θ̂ → {I_p, TMS}
├── signal_processing/
│   └── preprocessing.py                # event detection, window extraction, SG filter
├── relay/
│   └── iec_relay.py                    # IEC VI t_op(), integration element, inst element
├── confidence/
│   └── confidence_scorer.py            # γ = Σ w_i·s_i, 4-component
├── config/
│   ├── system_params.py                # generator + network Thévenin params
│   └── study_cases.py                  # Case 1 (3PH), Case 2 (LL), Case 3 (SLG)
└── main_run_case.py                    # end-to-end pipeline runner

03_technical_reports/phase_1_sg_framework/TR01_sync_oc_foundation/
├── main_report1.tex                    # This document (1530 lines)
├── references1.bib
└── figures/                            # 6 PDF/TikZ figures
    ├── fig_system_architecture.pdf
    ├── fig_fault_current_model.pdf
    ├── fig_two_pass_estimator.pdf
    ├── fig_confidence_framework.pdf
    ├── fig_relay_characteristic.pdf
    └── fig_pipeline_flowchart.pdf
```

**Key API:** `estimate_reduced_source_parameters_two_pass(t, i_a, theta0, bounds)` → `(θ̂, r, J)`; `apply_bounded_update(I_p_current, TMS_current, theta_hat, delta_I, bounds)` → `(I_p_new, TMS_new)`

---

## §5 Validation

### 5.1 Three study cases

| Case | Fault | R_f (pu) | Î_sub (pu) | Î_ss (pu) | τ̂_ac (ms) | τ̂_dc (ms) | R²_A |
|---|---|---|---|---|---|---|---|
| Case 1 | 3PH | 0.01 | 2.838 | 1.858 | 60.6 | 55.9 | 0.9990 |
| Case 2 | LL | 0.05 | 2.838 | 1.858 | 60.6 | 55.9 | 0.9990 |
| Case 3 | SLG | 0.15 | 2.781 | 1.845 | 64.6 | 55.7 | 0.9998 |

Physical references: I_sub^ref = 2.857 pu; τ_dc^ref = 55.7 ms; φ_a = π/2. Estimated values agree closely.

Note: Î_ss ≈ 1.86 pu (not 0.51 pu) because within the 145ms window the dominant level is I_tr = V/(Xd' + Xth) — physically correct for relay adaptation.

### 5.2 Sensitivity and confidence

| Case | κ_n | RMSE_A (pu) | Bounds-hit | γ | Adaptation |
|---|---|---|---|---|---|
| Case 1 (3PH) | 5.10 | 0.054 | 0/6 | **0.894** | Accepted |
| Case 2 (LL) | 5.10 | 0.054 | 0/6 | **0.894** | Accepted |
| Case 3 (SLG) | 15.23 | 0.022 | 0/6 | **0.921** | Accepted |

All κ_n < 20 (well-conditioned), all γ > 0.70, all s_p = 1.0.

### 5.3 Relay performance — fixed vs. adaptive

| Case | I_p fixed → adaptive | TMS | Trip time (fixed) | Trip time (adaptive) | Pickup reduction | Security |
|---|---|---|---|---|---|---|
| Case 1 | 1.200 → 1.487 pu | 0.050 unchanged | 105.3 ms | 105.3 ms | **−57.9%** | Yes |
| Case 2 | 1.200 → 1.487 pu | 0.050 unchanged | 110.9 ms | 110.9 ms | **−60.1%** | Yes |
| Case 3 | 1.200 → 1.476 pu | 0.050 unchanged | 110.9 ms | 110.9 ms | **−61.3%** | Yes |

Trip time unchanged: all three cases trigger the instantaneous element (I_rms > I_inst = 2.5 pu). Adaptive benefit = pickup margin improvement (security). Speed benefit expected for R_f > 0.5 pu (inverse-time regime — deferred to TR-02).

### 5.4 Computational performance

| Component | Evaluations | Wall time |
|---|---|---|
| Pass 1 (LM full window) | ≤ 20 NFev | — |
| Pass 2 (LM tail window) | ≤ 15 NFev | — |
| Total (Python, serial) | ≤ 35 NFev | **< 20 ms** |

Well within < 100 ms protection IED budget.

---

## §6 Results

| Metric | Value |
|---|---|
| R²_A (all cases) | > 0.999 |
| RMSE_A | 0.022–0.054 pu (0.4–1.1% of peak) |
| κ_n (physics-constrained model) | 5.1–15.2 |
| κ_n (unconstrained 7-param baseline) | ~10⁸ |
| γ (all cases) | 0.894–0.921 (threshold = 0.70) |
| Spurious pickup reduction | ~57–61% |
| Security maintained | Yes (all fault types) |
| Total estimation time | < 20 ms |

---

## §7 Limitations

**L-1 — Stage 1 model only:** No AVR, PSS, or governor dynamics. Accurate for first 100–150 ms (subtransient + transient onset). Beyond 150 ms, AVR boost elevates I_ss above Stage-1 prediction. Stage 2 (Park dq ODE) addresses this — TR-02.

**L-2 — Phase-A only estimation:** Phases B/C reconstruction from phase-A parameters is accurate only for balanced 3PH. Asymmetric faults (LL, SLG) require sequence decomposition for phases B/C — TR-02 Extension 3.

**L-3 — Instantaneous element dominates:** For the study cases (R_f ≤ 0.15 pu), all trips are instantaneous. The adaptive TMS benefit for inverse-time operation is not demonstrated in TR-01 — demonstrated in TR-02 (HIF cases).

**L-4 — Single generator:** Selectivity and grading for multi-generator busbars not addressed — TR-02 Extension 4.

**L-5 — Empirical calibration constants:** α_I = 0.80 and α_TMS = 0.12 were chosen empirically for the study system parameters. Generalisation to other machine types requires recalibration.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy.

```bash
# Run all three study cases
cd /root/phd_thesis/04_code/sambp/sync_oc
python main_run_case.py --case 0  # 3PH (Case 1)
python main_run_case.py --case 1  # LL  (Case 2)
python main_run_case.py --case 2  # SLG (Case 3)

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR01_sync_oc_foundation
pdflatex main_report1 && bibtex main_report1 && \
    pdflatex main_report1 && pdflatex main_report1
```

**Key output:** per-case: `θ̂`, `r`, `J`, `γ`, `κ_n`, `I_p^final`, `TMS^final`, trip time (fixed and adaptive), spurious pickup count.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report1.tex` read (1530 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report1.tex` is authoritative — this file is a read-only analytical summary.*
