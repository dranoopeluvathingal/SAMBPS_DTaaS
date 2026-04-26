# SUBREPORT_TR02 — Extended SAMBP-SyncOC: HIF, Park dq, Sequence, Coordination (Milestones 2–5)

**TR ID:** TR-02  
**Full title:** Extended Adaptive Overcurrent Protection for Synchronous Generators: High-Impedance Faults, Sixth-Order Machine Dynamics, Sequence-Component Estimation, and Multi-Generator Coordination  
**Ref:** IITM/EE/PhD/AVE/TR-02/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR02_sync_oc_extended/`  
**Report file:** `main_report2.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework (Milestones 2–5)  
**Target journal:** IEEE Transactions on Power Delivery  
**Thesis allocation:** Chapter 3 (OC), Chapter 6 (generator suite) — systematic extensions to TR-01  
**Predecessor:** TR-01 (Milestone 1 — foundational 6-param framework)  
**Cross-linked TRs:** TR-01, paper_a (journal paper combining TR-01/02), paper_b (M3+M4 evolution)

---

## §1 Scope

**What TR-02 IS:**
Four systematic extensions to the SAMBP-SyncOC framework of TR-01:

1. **Extension 1 (Milestone 2) — HIF adaptation:** Impedance-aware TMS law `f_HIF(Î_ss)` extending the adaptation benefit into the inverse-time regime (R_f > 0.5 pu)
2. **Extension 2 (Stage 2) — Park dq forward model:** 9-state ODE (`δ, ω, E'q, E'd, E''q, E''d, E_fd, T_m, V_pss`) with AVR/PSS/governor; Radau stiff solver; validates Stage-1 accuracy window
3. **Extension 3 — Sequence-component estimation:** Hilbert–Fortescue decomposition + independent LM fitting per active sequence; positive-sequence governs relay adaptation
4. **Extension 4 — Multi-generator coordination:** Greedy cascade algorithm enforcing pickup selectivity (ΔI_m = 0.20 pu) and IEC trip-time grading (Δt_g = 0.15 s) across N generators; Proposition: finite convergence in ≤ N iterations

**What TR-02 IS NOT:**
- Not a standalone work — requires TR-01 framework; all Stage-1 modules inherited unchanged
- Not a real-time Stage-2 ODE: Radau solver requires 5–30 s per case (Python); online role is initial guess calibration only
- Not a complete LL fault solution: LL confidence γ = 0.587 (below 0.70 gate); fix requires complex-domain measurements or independent τ_ac estimation

---

## §2 State of the Art

Bounded by TR-01 references. Extensions reference:
- Kundur1994 / IEEE1110: Park dq 6th-order model formulation
- IEC60255-151: time-grading margin Δt_g = 0.15 s standard requirement
- Kimbark1956: Fortescue symmetrical components theory

---

## §3 Method

### 3.1 Extension 1 — Impedance-aware TMS adaptation (Milestone 2)

**HIF regime** (R_f > ~0.38 pu): fault current falls below I_inst → inverse-time element governs; trip time sensitive to TMS.

**Extended TMS law:**
```
f_HIF(Î_ss) = clip(Î_ss / I_ss^nom, 0.30, 1.0),   I_ss^nom = 0.51 pu

K_TMS^eff = 0.12  if f_HIF ≥ 0.9   (bolted/low-R)
           = 0.08  if f_HIF < 0.9   (HIF regime, ≥33% TMS reduction)

TMS* = K_TMS^eff · τ̂_ac · f_HIF(Î_ss)
```

**HIF study cases:** 10 cases — 3PH and SLG at R_f ∈ {0.50, 0.75, 1.00, 1.25, 1.50} pu.

**Key finding:** All 10 cases: γ ≥ 0.873 (adaptation accepted), but TMS* is capped at TMS_min = 0.050 throughout (TMS already at minimum in study system). Trip times identical: 105.3 ms (3PH) and 110.9 ms (SLG). Adaptive benefit constrained by the minimum TMS bound; the impedance-aware law is structurally sound but requires a lower TMS_min to manifest speed improvement. For R_f > 1.0 pu (3PH) or R_f > 0.5 pu (SLG), current falls below I_p — protection fails regardless (directional earth fault backup required).

### 3.2 Extension 2 — Sixth-order Park dq forward model (Stage 2)

**State vector (9 states):** `x = [δ, ω, E'q, E'd, E''q, E''d, E_fd, T_m, V_pss]`

**Machine equations:**
```
dE'q/dt  = (1/T'd0)[E_fd − E'q + (Xd − X'd)·id]
dE'd/dt  = (1/T'q0)[−E'd − (Xq − X'q)·iq]
dE''q/dt = (1/T''d0)[E'q − E''q − (X'd − X''d)·id]
dE''d/dt = (1/T''q0)[E'd − E''d + (X'q − X''q)·iq]
dδ/dt    = ω − ωs
dω/dt    = (ωs/2H)[Tm − Te − D(ω−ωs)/ωs]
```

**Controllers:**
- AVR (IEEE Type-1 first-order): dE_fd/dt = (1/τa)[Ka(Vref − Vt − V_pss) − E_fd]
- PSS (lead-lag on Δω): dV_pss/dt = (1/τ2)[K_pss·(τ1/τw)·Δω − V_pss]
- Governor (droop + turbine): dTm/dt = (1/τch)[Pref + (ωs−ω)/(Rd·ωs) − Tm]

**Stator algebraic interface:** 2×2 linear system for [id, iq] solved analytically at each ODE step (fault interval vs. pre-fault Thévenin interval).

**Park inverse transform:** [ia, ib, ic] = P_inv(δ) · [id, iq]

**Solver:** Radau (stiff implicit RK), rtol=10⁻⁶, atol=10⁻⁸; split at switching instants t₀, tc.

**Key result (Stage 2 accuracy):** For 3PH fault R_f=0.01 pu with Stage-1 LM estimator fitting Stage-2 ODE output:
- RMSE_A = 0.425 pu, R²_A = 0.337 — worse than Stage-1 self-fit because AVR excitation boosts field beyond 150 ms and Stage-1 model lacks this
- γ = 0.323 (below 0.70 — adaptation correctly rejected when AVR dynamics dominate)
- **Conclusion:** Stage-1 estimator adequate for first 100–150 ms (subtransient window). Stage-2 ODE role = offline validation and initial guess calibration, not online estimation.

### 3.3 Extension 3 — Sequence-component estimation

**Hilbert–Fortescue decomposition:**
```
I̊_k(t) = i_k(t) + j·H{i_k}(t)   (analytic signal, Hilbert transform via FFT)

I̊_0 = (1/3)[I̊_a + I̊_b + I̊_c]
I̊_1 = (1/3)[I̊_a + a·I̊_b + a²·I̊_c],   a = e^{j2π/3}
I̊_2 = (1/3)[I̊_a + a²·I̊_b + a·I̊_c]
```

**Fault-type routing:**

| Fault | Active seqs | Estimator | Relay adaptation |
|---|---|---|---|
| 3PH | I₁ (= phase A) | Phase-A two-pass (TR-01, unchanged) | θ̂^pos |
| LL | I₁, I₂ | Independent TwoPass per sequence | θ̂^pos |
| SLG | I₁ = I₂ = I₀ | I₁ only (network identity) | θ̂^pos |
| LLG | I₁, I₂, I₀ | Independent per sequence | θ̂^pos |

Symmetry check: if ‖I₂‖/‖I₁‖ < 0.05 → treat as balanced, skip I₂ fit.

Hilbert edge mitigation: 2 ms window offset + Savitzky–Golay smoothing pre-decomposition.

**Results:**

| Case | Fault | RMSE_comb | γ | Adapted | I_p* |
|---|---|---|---|---|---|
| ll_fault_mid_R | LL | 1.396 | 0.587 | No | 1.200 pu (unchanged) |
| slg_fault_high_R | SLG | 0.974 | 0.914 | Yes | 1.100 pu (−8.3%) |

SLG achieves γ=0.914 because I₁=I₂=I₀ (network identity concentrates full fault current in I₁ — clean single-envelope waveform). LL fails gate because I₁ and I₂ share carrier frequency ω₀ (series sequence networks), leaving residual contamination between the two fitted components.

### 3.4 Extension 4 — Multi-generator greedy cascade coordination

**Topology:** N generators G₁…G_N on common busbar + downstream bus relay R_B.

**Constraints:**
- Pickup selectivity: `I_p,k ≥ I_p,k+1 + ΔI_m`,  ΔI_m = 0.20 pu
- Trip-time grading: `t_op,k(I_f,min) ≥ t_op,k+1(I_f,min) + Δt_g`,  Δt_g = 0.15 s

**Algorithm (greedy cascade, repeat-until-stable):**
```
Repeat:
  for k = N downto 1:
    if I_p,k < I_p,k+1 + ΔI_m:
      I_p,k = min(I_p,k+1 + ΔI_m, I_p,max)
Until no change or iter ≥ 10
```

**Proposition (Finite Convergence):** Converges in ≤ N iterations. Proof: pickups are monotonically non-decreasing under the algorithm and bounded above → violations are non-increasing → propagation terminates in ≤ N steps.

**TMS grading correction:** After selectivity enforcement, check Δt_grade at I_f,min; for violations, reduce downstream TMS:  
`TMS_{k+1}^new = TMS_{k+1} · (t_op,k − Δt_g) / t_op,k+1`

**Results (N=2, 3PH, R_f=0.01 pu):**

| Relay | γ | I_p fixed | I_p before | I_p after | TMS |
|---|---|---|---|---|---|
| Gen 1 | 0.892 | 1.300 | 1.309 | **1.550** | 0.050 |
| Gen 2 | 0.893 | 1.200 | 1.350 | 1.350 | 0.050 |
| Bus | — | 1.000 | 1.000 | 1.000 | 0.030 |

Selectivity OK after enforcement ✓; Grading OK after enforcement ✓.

**Scaling (N=2,3,4, 3PH):**

| N | Gen 1 I_p* | Gen 2 I_p* | Gen 3 I_p* | Gen 4 I_p* | Bus |
|---|---|---|---|---|---|
| 2 | 1.550 | 1.350 | — | — | 1.000 |
| 3 | 1.635 | 1.435 | 1.235 | — | 1.000 |
| 4 | **2.038** | 1.838 | 1.638 | 1.438 | 1.000 |

All cases: selectivity OK + grading OK ✓.

**Graceful degradation (N=3, LL fault):** All γ ∈ [0.558, 0.696] < 0.70 → fixed settings retained. Cascade re-orders: Bus 1.000 → Gen 3 1.200 → Gen 2 1.400 → Gen 1 1.600 pu. Selectivity satisfied from fixed commissioning settings — coordination stage is independent of adaptation stage.

---

## §4 Implementation

### Module tree (new/modified in TR-02)

```
04_code/sambp/sync_oc/
├── config/
│   ├── study_cases.py               # Added HIF_STUDY_CASES (10 cases)
│   ├── system_config.py             # Added park_dq parameter sub-dict
│   └── relay_config.py              # Added MULTI_GEN_CONFIG
├── models/
│   ├── park_dq_model.py             # NEW: 9-state Park dq ODE, Radau solver
│   └── multi_gen_model.py           # NEW: Thévenin superposition multi-gen
├── inverse_estimation/
│   ├── sequence_estimator.py        # NEW: Hilbert–Fortescue decomposition
│   └── objective_functions.py       # Modified: residual_vector_sequence()
├── adaptation/
│   ├── adaptive_mapping.py          # Modified: HIF-aware f_HIF factor
│   └── coordination_logic.py        # NEW: selectivity + grading enforcement
├── evaluation/
│   └── metrics.py                   # Modified: compute_coordination_metrics()
├── main_run_case.py                 # Modified: --stage 2 switch
├── run_milestone2.py                # NEW: HIF batch runner + plots
└── run_multi_gen.py                 # NEW: multi-generator study runner
```

---

## §5 Validation

### 5.1 HIF — 10/10 cases accepted, TMS_min binding

All 10 HIF cases: γ ≥ 0.873 → adaptation accepted. TMS* = 0.050 in all cases (TMS_min binding). Trip times: 105.3 ms (3PH, all R_f), 110.9 ms (SLG, all R_f). Impedance-aware law structurally validated; TMS_min setting prevents speed benefit in this study system.

### 5.2 Stage 2 accuracy — subtransient window validated

Stage-1 estimator accuracy window confirmed at ≤ 150 ms. Beyond 150 ms, AVR dynamics cause divergence (R²_A = 0.337 for full 200 ms window vs. > 0.999 for first 150 ms sub-window). Stage-2 ODE is not suitable for online estimation (5–30 s Radau solve time).

### 5.3 κ_n sweep — physics constraint validated

κ_n vs. window length sweep (Fig: kappa_sweep):
- 6-param physics-constrained: κ_n ≤ 61 at 50 ms, improves to κ_n = 4.5 at 200 ms
- 7-param unconstrained: κ_n ~ 10⁸ at 67 ms and above

This confirms the physics continuity constraint (I_dc = −I_sub·sin φ_a) is a structural prerequisite — not merely an aesthetic modelling choice.

### 5.4 Sequence estimation

SLG: γ=0.914 → adapted, I_p 1.20→1.10 pu (−8.3%). LL: γ=0.587 → rejected, fixed settings retained. Consistent with paper_b M3 results (same κ_n = 17.2 for SLG; same LL failure mode).

### 5.5 Coordination — all N verified

N=2,3,4 (3PH): all selectivity and grading constraints satisfied after cascade. N=3 LL: graceful degradation confirmed. Convergence bound (≤ N iterations) verified.

---

## §6 Results

| Metric | Value |
|---|---|
| HIF adaptation accepted | 10/10 cases (γ ≥ 0.873) |
| HIF trip time (adaptive vs fixed) | Equal — TMS_min binding |
| Stage-2 ODE γ (full 200ms window) | 0.323 → adaptation correctly rejected |
| Stage-2 ODE γ (sub-transient window ≤150ms) | Consistent with TR-01 (> 0.89) |
| κ_n (6-param, 200ms window) | 4.5 (well-conditioned) |
| κ_n (7-param, 67ms+ window) | ~10⁸ (unreliable) |
| SLG adaptation accepted | γ=0.914 ✓; pickup −8.3% |
| LL adaptation accepted | γ=0.587 ✗; fixed settings retained |
| Coordination (N=2,3,4 3PH) | All selectivity + grading satisfied ✓ |
| Graceful degradation (N=3 LL) | Selectivity satisfied from fixed settings ✓ |
| Convergence (greedy cascade, N=4) | ≤ 4 iterations (within bound of N) |

---

## §7 Limitations

**L-1 — TMS_min binding in HIF study:** The impedance-aware TMS law proposes a reduced TMS, but the minimum setting (0.050) is already at the lower clip bound. The protection speed benefit requires lowering TMS_min, which depends on co-ordination requirements with downstream relays. A lower TMS_min (e.g., 0.02) would allow the HIF law to manifest.

**L-2 — Stage-2 online infeasibility:** Radau solver wall time (5–30 s) prohibits online use. Reduced-order approximation (4th-order single-axis + simplified AVR) is future work.

**L-3 — LL fault estimation failure (same as paper_b L-1):** Hilbert–Fortescue gives γ=0.587 for LL because I₁ and I₂ share carrier frequency ω₀. Fix requires complex-domain (PMU phasor) measurements or independent τ_ac per sequence. Deferred to companion paper EluvathingalSeqEstim.

**L-4 — Coordination conservatism at large N:** Greedy cascade raises upstream pickups linearly (ΔI_m = 0.20 pu/generator). At N=4, Gen 1 reaches 2.038 pu. For N ≥ 5, outermost pickup may approach relay ceiling. Non-uniform grading margins deferred to companion paper EluvathingalCoordGen.

**L-5 — Superposition model for multi-generator fault current:** Each generator's fault current is computed independently via Thévenin superposition. Mutual coupling between generators through the common busbar is not captured. A full network admittance model would be more accurate for tightly coupled machines.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy (Radau solver for Stage 2).

```bash
# Milestone 2: HIF study (10 cases)
cd /root/phd_thesis/04_code/sambp/sync_oc
python run_milestone2.py --output_dir outputs/milestone2/

# Stage 2: Park dq ODE (single case)
python main_run_case.py --case 0 --stage 2

# κ_n sweep (6-param vs 7-param)
python run_kappa_sweep.py --output_dir outputs/kappa_sweep/

# Multi-generator coordination
python run_multi_gen.py --n-gen 2 --fault 3PH    # N=2
python run_multi_gen.py --n-gen 3 --fault 3PH    # N=3
python run_multi_gen.py --n-gen 4 --fault 3PH    # N=4
python run_multi_gen.py --n-gen 3 --fault LL     # graceful degradation

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR02_sync_oc_extended
pdflatex main_report2 && bibtex main_report2 && \
    pdflatex main_report2 && pdflatex main_report2
```

**Key figures:**
- `fig_hif_tclear.pdf` — clearance time vs. R_f (fixed vs. adaptive; TMS_min binding visible)
- `fig_park_dq_model.pdf` — Stage-2 block diagram
- `fig_kappa_sweep.pdf` — κ_n vs. window length (6-param vs. 7-param)
- `fig_sequence_networks.pdf` — positive/negative/zero sequence networks
- `fig_coordination_flowchart.pdf` — selectivity + grading enforcement procedure
- `3ph_fault_low_R_waveform.png` — Stage-2 ODE vs. Stage-1 LM fit (diverges > 50 ms)
- `ll_fault_mid_R_waveform.png` — LL fault Hilbert–Fortescue decomposition (γ=0.587)

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report2.tex` read (1535 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report2.tex` is authoritative — this file is a read-only analytical summary.*
