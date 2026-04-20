# SUBREPORT_paper_a — Real-Time Inverse Parameter Estimation for Adaptive OC Protection

**Paper ID:** paper_a  
**Folder:** `02_papers/paper_a_syncoc_oc/`  
**Manuscript:** `main_paper.tex` (1002 lines, IEEE journal format)  
**Target journal:** IEEE Transactions on Power Delivery / IET Generation, Transmission & Distribution  
**Generated:** 2026-04-20  
**Authors:** Anoop V. Eluvathingal, K. Shanti Swarup (IIT Madras / SGCRL)  
**Cross-linked TRs:** TR-01 (`sync_oc_foundation`), TR-02 (`sync_oc_extended`)

---

## §1 Scope

**What this paper IS:**
- A real-time, local-measurement-only framework for recalibrating overcurrent (OC) relay settings on synchronous generators within a single fault interval
- A physics-constrained six-parameter fault current model where `I_dc,k = -I_sub·sin(φ_k)` is imposed by the current continuity condition at fault inception — not fitted as a free parameter
- A two-pass Levenberg–Marquardt estimator with phase-A-only residual in Pass 1, tail-window refine in Pass 2
- A four-component confidence gate `γ` that blocks adaptation when fit quality is poor
- A bounded adaptive law (rate-limited + hard-clipped) for both `I_p` and `TMS`

**What this paper IS NOT:**
- Not a communication-assisted or wide-area protection scheme — no synchrophasors, no central controller
- Not a machine-learning or data-driven approach — fully physics-grounded model
- Not a multi-phase estimator — deliberate Phase-A-only strategy (avoids DC cross-cancellation across B/C)
- Not a replacement for primary protection — an adaptive supplementary function

**Cross-links:**
- TR-01: foundation simulation study establishing the 6-parameter reduced model and convergence proof
- TR-02: extended study with multi-generator network and HIF sweep (10 cases, `R_f` up to 2.0 pu)
- `02_papers/tikz_master_styles.tex`: shared TikZ/pgfplots style file used by `fig_key_results.tex`

---

## §2 State of the Art

Eight references cited in `references.bib` bound the novelty:

| Ref | Authors | Key approach | Limitation vs. proposed |
|---|---|---|---|
| \[1\] Kundur 1994 | Power System Stability | Machine parameter definitions (Xd, Xd', Xd'', Td') | Textbook baseline — no online estimation |
| \[2\] IEEE Std 1110 | IEEE Guide for SG | Standard reactance/time-constant taxonomy | Offline, nameplate-based |
| \[3\] Blackburn 2006 | Protective Relaying | Fixed OC relay design | No RT ID, no physics constraint, no confidence gate |
| \[4\] IEC 60255-151 | OC relay standard | Inverse-time characteristic definition | Standardises fixed-setting approach |
| \[5\] Brahma & Girgis 2004 | Local pickup update | Adapts `I_p` from measured current magnitude | Assumes fixed source impedance; no transient model; no TMS adapt |
| \[6\] Oudalov et al. 2009 | Communication-based RT coord. | Network-wide setting recompute | Requires reliable comms + full observability; no physics model |
| \[7\] Laaksonen 2017 | Mode-switch table | Pre-computed table indexed to operating state | Discrete state space; no waveform ID; no physics constraint |
| \[8\] Saleh 2017 | Wavelet-based OC | Wavelet features for adaptive OC | Feature extraction only; no model parameter recovery |

**Novelty claim:** The proposed method is the only framework that simultaneously performs real-time waveform-based parameter identification, enforces the DC-offset physics constraint, gates adaptation via a confidence score, and adapts both `I_p` and `TMS` from a single estimator output.

---

## §3 Method

### 3.1 Physics-constrained six-parameter model

The phase-A fault current is modelled as:

```
i_a(t) = I_ss + I_sub·exp(-(t-t₀)/τ_ac)·cos(ω(t-t₀) + φ_a)
        + I_dc,a·exp(-(t-t₀)/τ_dc)
```

where `I_dc,a = -I_sub·sin(φ_a)` is derived analytically from the current continuity condition at `t = t₀` (fault inception). This eliminates one free parameter and reduces the Jacobian condition number from `O(10⁸)` to `κ_n(J) < 20`.

Free parameter vector: `θ = [t₀, I_ss, I_sub, τ_ac, τ_dc, φ_a] ∈ ℝ⁶`

### 3.2 Two-pass Levenberg–Marquardt estimator

**Pass 1** — Full 145 ms window, Phase-A residual only:
- Fits all 6 parameters via Trust-Region Reflective (`scipy.optimize.least_squares`, method='trf')
- Locks `{τ_dc, I_sub, φ_a, t₀}` — well-identified from the early transient
- Phase-A-only residual avoids DC cross-cancellation across phases B and C

**Pass 2** — Tail window (last 2 cycles), frozen transient parameters:
- Fixes `{t₀, φ_a, I_sub, τ_dc}` from Pass 1
- Refines only `I_ss` and `τ_ac` — where the AC envelope has settled
- Removes the collinearity between `I_ss` and the decaying `τ_ac` envelope

### 3.3 Four-component confidence gate

```
γ = 0.35·s_r + 0.30·s_c + 0.20·s_b + 0.15·s_p
```

where:
- `s_r` = length-normalised residual score (per-sample RMSE, normalised by N^(1/2) for window-length invariance)
- `s_c` = convergence score (LM Jacobian rank)
- `s_b` = boundary distance score (proximity to parameter bounds)
- `s_p` = physics plausibility score (`I_sub > I_ss`, `τ_dc > 10 ms`)

Adaptation is triggered when `γ ≥ γ_th = 0.70`.

### 3.4 Bounded adaptive law

```python
# adaptation/bounded_update.py
clip_relay_settings(I_p_new, TMS_new, I_p_bounds, TMS_bounds)
rate_limit_update(I_p_old, I_p_new, delta_max)
apply_bounded_update(relay_state, theta_hat, gamma, gamma_th, bounds, delta_max)
```

- Rate-limit: `|ΔI_p| ≤ δ_max` per adaptation step
- Hard clip: final settings constrained to `[I_p^min, I_p^max]` × `[TMS^min, TMS^max]`
- Provably keeps relay settings in operationally safe region regardless of estimator accuracy

---

## §4 Implementation

### Module tree

```
04_code/sambp/sync_oc/
├── models/
│   ├── reduced_source_model.py      # 6-parameter fault current model + THETA_KEYS
│   ├── sync_generator_model.py      # Full SG machine model (Park dq reference)
│   ├── relay_oc_model.py            # IEC 60255-151 inverse-time curve implementation
│   ├── network_fault_model.py       # Thévenin network + fault impedance
│   ├── park_dq_model.py             # 6th-order dq truth model
│   └── multi_gen_model.py           # Multi-generator network
├── inverse_estimation/
│   ├── parameter_estimator.py       # Two-pass LM estimator (public API)
│   ├── objective_functions.py       # residual_vector(), residual_vector_phaseA()
│   ├── confidence_logic.py          # Confidence score γ computation
│   ├── sensitivity_analysis.py      # Jacobian condition number κ_n
│   └── sequence_estimator.py        # Symmetrical components pre-filter
├── adaptation/
│   ├── bounded_update.py            # clip_relay_settings(), apply_bounded_update()
│   ├── adaptive_mapping.py          # θ_hat → {I_p_new, TMS_new} mapping
│   └── coordination_logic.py        # Multi-relay coordination check
├── signal_processing/
│   ├── event_detection.py           # Fault inception detection (t₀)
│   ├── preprocessing.py             # Anti-alias filter + decimation
│   ├── rms_tools.py                 # Half-cycle RMS
│   ├── sequence_components.py       # α, β, 0, 1, 2 component extraction
│   └── smoothing.py                 # Savitzky-Golay + median filter
├── evaluation/
│   ├── metrics.py                   # R², RMSE, κ_n, γ computation
│   ├── comparison.py                # Prior-work comparison table generation
│   └── reporting.py                 # JSON + LaTeX table output
├── io_utils/
│   ├── csv_io.py                    # CSV read/write for waveform data
│   ├── case_logger.py               # Per-case structured log
│   └── __init__.py
├── config/
│   ├── study_cases.py               # 3 Milestone-1 cases + 10 HIF sweep cases
│   ├── system_config.py             # Network and machine parameters
│   └── relay_config.py              # OC relay bounds and coordination constants
├── main_batch_study.py              # Entry point — batch run over study cases
├── main_run_case.py                 # Single-case runner
├── run_milestone2.py                # Milestone-2 (multi-gen) runner
├── run_multi_gen.py                 # Multi-generator scenario runner
├── run_tr59_andes.py                # ANDES-linked runner (TR-59 cross-link)
├── plot_milestone1.py               # Milestone-1 figure generation
└── sweep_kappa.py                   # Condition number sweep over θ space
```

### Key public API signatures

```python
# inverse_estimation/parameter_estimator.py
estimate_reduced_source_parameters(
    t_window, ia_meas, ib_meas, ic_meas,
    initial_guess, bounds, frequency_hz=50.0
) → dict  # {theta_hat, success, cost, residual_norm, jacobian}

estimate_reduced_source_parameters_two_pass(
    t_window, ia_meas, ib_meas, ic_meas,
    initial_guess, bounds, frequency_hz=50.0, tail_cycles=2
) → dict  # same keys + pass1_theta_hat

# adaptation/bounded_update.py
clip_relay_settings(I_p_new, TMS_new, I_p_bounds, TMS_bounds) → (I_p, TMS)
rate_limit_update(I_p_old, I_p_new, delta_max) → I_p_clipped
apply_bounded_update(relay_state, theta_hat, gamma, gamma_th,
                     bounds, delta_max) → relay_state_new

# inverse_estimation/confidence_logic.py
compute_confidence_score(residual_norm, jacobian, theta_hat, bounds,
                         N_samples, weights=(0.35, 0.30, 0.20, 0.15)) → γ
```

### Parameter bounds (DEFAULT_BOUNDS)

| Parameter | Lower | Upper | Physical basis |
|---|---|---|---|
| `t₀` | 0.0 s | 2.0 s | Fault inception time |
| `I_ss` | 0.05 pu | 5.0 pu | Steady-state fault current |
| `I_sub` | 0.5 pu | 15.0 pu | Subtransient peak (always > `I_ss`) |
| `τ_ac` | 5 ms | 1.0 s | `T_d''` up to 1 s for large machines |
| `τ_dc` | 10 ms | 500 ms | `X''/ωR` — always > 10 ms physically |
| `φ_a` | −π | +π | Fault inception angle |

---

## §5 Validation

### Milestone-1 study cases (3-phase, LL, SLG faults)

| Case | Fault type | `R_f` (pu) | `R²` | RMSE (pu) | `κ_n(J)` | `γ` | Adapt triggered |
|---|---|---|---|---|---|---|---|
| M1-3Ph | Three-phase | 0.0 | >0.999 | 0.054 | <20 | 0.93 | Yes |
| M1-LL | Line-to-line (A-B) | 0.0 | >0.999 | 0.048 | <20 | 0.91 | Yes |
| M1-SLG | Single-line-to-ground (A-G) | 0.1 | >0.999 | 0.061 | <20 | 0.89 | Yes |

All 3 cases: `γ > γ_th = 0.70` → adaptive pickup recalibration triggered.

### Milestone-2 HIF sweep (10 cases)

Fault resistance `R_f` swept from 0.5 pu to 2.0 pu (5 values × 2 fault types: 3Ph + SLG).

Key finding: Adaptively recalibrated `I_p` detects all 10 HIF cases vs. 0/10 with fixed settings. Spurious pickup reduction: −57% to −61% across the sweep.

### Relay performance summary (Tab. 5)

| Metric | Fixed OC | Proposed |
|---|---|---|
| Spurious pickups (3-phase, nominal) | Baseline | −60% |
| HIF detection rate | 0% | 100% |
| Tripping security (no false trip) | 100% | 100% |
| Max adaptation latency | — | <20 ms |

---

## §6 Results

Key quantitative results from the paper (Tables 2–6):

**Table 2 — Estimated parameters (M1-3Ph case):**

| θ | True | Estimated | Error |
|---|---|---|---|
| `I_ss` | 1.20 pu | 1.22 pu | 1.7% |
| `I_sub` | 6.80 pu | 6.83 pu | 0.4% |
| `τ_ac` | 0.055 s | 0.057 s | 3.6% |
| `τ_dc` | 0.042 s | 0.041 s | 2.4% |
| `φ_a` | 0.31 rad | 0.30 rad | 3.2% |

**Table 4 — Relay performance (adaptive vs. fixed):** −57% to −61% spurious pickups; 100% HIF detection; 100% tripping security.

**Table 6 — Computational cost:**

| Step | Time |
|---|---|
| Pass 1 (full window, 6 params) | ~12 ms |
| Pass 2 (tail, 2 params) | ~4 ms |
| Confidence gate | <1 ms |
| Total | <20 ms |

Target: IED-grade IEC 61850 GOOSE latency budget (~4 ms) not met — estimation is post-fault supplementary function, not primary trip signal. Total <20 ms is within protection supervisory function timing (IEC 60255-1 Class 2, 20 ms).

---

## §7 Limitations

**L-1 — Phase-A-only estimator:** Deliberately fits phase-A residual only in Pass 1 to avoid DC cross-cancellation between phases. Phase B and C waveforms are not modelled; the residual on B/C can reach ±5% in asymmetric faults. Extension to a three-phase sequential estimator is deferred.

**L-2 — Single-exponential DC model:** `I_dc,a = -I_sub·sin(φ_a)·exp(-t/τ_dc)` assumes a single DC time constant. Real machines with damper windings exhibit a double-exponential DC decay; the single-exponential fit overestimates `τ̂_dc` by 8–15% in heavy-load cases.

**L-3 — TMS floor constraint:** Adaptive TMS update is bounded below at `TMS_min = 0.05` (IEC 60255-151 minimum). During prolonged HIF with low `I_ss` estimates, the floor is hit and TMS cannot be reduced further, leaving a residual pickup margin gap of ~12% in `R_f = 2.0` pu cases.

**L-4 — Communication-free scope:** The framework is designed for single-relay local adaptation. Multi-relay coordination (ensuring downstream relay still clears before upstream) requires a coordination check layer; `coordination_logic.py` provides a stub but the full coordination proof is left to TR-02.

**L-5 — No IBR fault current model:** The model assumes a purely synchronous generator. IBR fault current (current-limited, 1.1–1.2 pu, phase-locked) has a fundamentally different signature. Extension to hybrid SG+IBR networks is the subject of later thesis chapters (Ch.4/Ch.6).

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy, matplotlib.

```bash
# 1. Run full batch study (3 Milestone-1 + 10 HIF sweep cases)
cd /root/phd_thesis/04_code/sambp/sync_oc
python main_batch_study.py --study milestone1 milestone2_hif \
    --output_dir results/ --save_json

# 2. Generate Milestone-1 figures (Fig. 2–5 in paper)
python plot_milestone1.py --results_dir results/ --output_dir figures/

# 3. Sweep condition number κ_n over θ parameter space
python sweep_kappa.py --n_samples 500 --output_dir results/kappa_sweep/

# 4. Run single case (interactive)
python main_run_case.py --case M1-3Ph --verbose

# 5. Compile paper
cd /root/phd_thesis/02_papers/paper_a_syncoc_oc
pdflatex main_paper && bibtex main_paper && \
    pdflatex main_paper && pdflatex main_paper
```

**Outputs:**
- `results/batch_results.json` — full θ_hat, R², RMSE, γ, relay performance per case
- `results/kappa_sweep/kappa_surface.png` — condition number surface over (I_sub, τ_ac) grid
- `figures/fig_milestone1_waveform.pdf` — Pass-1 and Pass-2 fit overlaid on measured i_a(t)
- `figures/fig_kappa_comparison.pdf` — κ_n: constrained vs. unconstrained model

**Figures shipped with manuscript:**

| File | Description |
|---|---|
| `fig_fault_current_model.pdf` | Physics-constrained 6-parameter model schematic |
| `fig_pipeline_flowchart.pdf` | End-to-end pipeline: event detection → estimation → gate → adaptation |
| `fig_two_pass_estimator.pdf` | Pass-1 / Pass-2 window diagram |
| `fig_system_architecture.pdf` | Study network: SG + feeder + relay |
| `fig_relay_characteristic.pdf` | IEC 60255-151 inverse-time characteristic with adaptive `I_p` / `TMS` |
| `fig_confidence_framework.pdf` | Four-component γ score decomposition |
| `fig_key_results.tex` | TikZ/pgfplots source for key-results summary figure |

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created; data gathered from full `main_paper.tex` (1002 lines) read + module tree exploration. No manuscript modified. |

---

*Sub-report generated by SAMBP archivist pipeline. Manuscript `main_paper.tex` is authoritative — this file is a read-only analytical summary. Do not edit `main_paper.tex` via this file.*
