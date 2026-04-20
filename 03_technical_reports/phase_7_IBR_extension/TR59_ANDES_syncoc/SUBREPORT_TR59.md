# SUBREPORT_TR59 — ANDES Positive-Sequence Validation of sync_oc Confidence Adaptation

**TR ID:** TR-59  
**Full title:** ANDES Positive-Sequence Validation of Synchronous-Generator Overcurrent Confidence Adaptation (`sync_oc`)  
**Subtitle:** *Finding: positive-sequence simulation is insufficient for SAMBP subtransient identification — EMT simulation required*  
**Folder:** `03_technical_reports/phase_7_IBR_extension/TR59_ANDES_syncoc/`  
**Report file:** `main_report59.tex`  
**Generated:** 2026-04-20  
**Thesis allocation:** Chapter 4, §4.3 — Validation methodology and simulator adequacy  
**Feeds into:** TR-67 (EMT Validation)  
**Cross-linked TRs:** TR-56 (DFIG/87L — avoids this limitation by design), TR-67 (PSCAD EMT re-run)

---

## §1 Scope

**What TR-59 IS:**
- A systematic 10-case validation of the `sync_oc` confidence-adaptation module against ANDES v1.9 positive-sequence (phasor) TDS waveforms
- A definitive empirical finding: **0/10 cases reach the confidence threshold γ ≥ 0.70** when driven by ANDES positive-sequence data
- A physics diagnosis of *why*: positive-sequence phasor reconstruction lacks the DC aperiodic offset and the fast subtransient exponential decrement that SAMBP's 4-parameter model requires
- A formal **Simulator Adequacy Proposition** (Equation 3): `‖∂|i_a^sim|/∂t|_{t=t₀⁺}‖ ≥ I_sub/τ_ac` — positive-sequence simulators do not meet this condition for `τ_ac < 0.1 s`
- The empirical motivation for TR-67 (PSCAD EMT) as the correct validation platform

**What TR-59 IS NOT:**
- Not a software bug report — the low-γ result is the correct engineering outcome; the confidence gate self-diagnoses poor-quality input
- Not a validation of the `sync_oc` estimator itself — that is done on synthetic data (γ ≥ 0.80 baseline confirmed)
- Not an EMT study — ANDES positive-sequence only; full machine flux dynamics → TR-67
- Not applicable to TR-56 (DFIG model): the ANDES WTDTA1 Type-3 model provides adequate high-frequency content via the RSC model

**Central finding:** SAMBP's confidence gate correctly *refuses to adapt* when driven by positive-sequence simulator data — a self-diagnostic property that preserves relay security. The Δγ ≈ 0.30 gap between ANDES data (γ̄ = 0.538) and synthetic data (γ ≥ 0.80) is attributable entirely to missing subtransient physics.

---

## §2 State of the Art

Three references in `references59.bib`:

| Key | Reference | Role in TR-59 |
|---|---|---|
| andes | Cui et al. 2021, ANDES v1.9 | Simulator under test — positive-sequence TDS |
| kundur | Kundur 1994 | Source of GENROU subtransient parameters (`X_d''`, `T_d''`) |
| ieee_c3791 | IEEE C37.91-2021 | Generator protection standard — requires OC relay to correctly classify faults |

**Novelty:** TR-59 is the first document in the SAMBP archive to formally characterise the simulator adequacy condition for confidence-based adaptation, providing the theoretical bridge between the synthetic-data results (TR-01, TR-02, paper_a) and the EMT-validation target (TR-67).

---

## §3 Method

### 3.1 `sync_oc` confidence model under test

The `sync_oc` module fits a 4-parameter subtransient current model:
```
i_a(t) = I_sub·exp(-(t-t₀)/τ_ac)·cos(ω₀t + φ_a) + I_DC·exp(-(t-t₀)/τ_dc)
```
Parameters: `{I_sub, τ_ac, I_DC, τ_dc}`, identified by single-pass Levenberg–Marquardt on the post-fault phase-A waveform.

Confidence score:
```
γ = w_resid·γ_r + w_plaus·γ_p + w_cond·γ_c
```
- `γ_r`: normalised residual score (small RMSE → high score)
- `γ_p`: physics plausibility (`I_sub > I_ss` at fault inception required)
- `γ_c`: Jacobian conditioning penalty

Adaptation accepted only when `γ ≥ γ_th = 0.70`.

### 3.2 ANDES positive-sequence reconstruction — missing physics

ANDES computes the positive-sequence phasor envelope `Î₁(t)` and reconstructs:
```
i_a(t) = Re[Î₁(t)·exp(jω₀t)]
```
This is a **slowly-varying sinusoid**. Two physics features absent:

1. **DC aperiodic offset** `I_DC·exp(-t/τ_dc)` — filtered by construction (positive-sequence operates at ω₀ only)
2. **Subtransient decrement** `I_sub·exp(-t/τ_ac)` — ANDES GENROU ODE tracks the slowly-varying envelope, but the fast exponential component (`τ_ac ~ 30–100 ms`) is not resolved

Consequence: LM drives `Î_sub → 0.500 pu` (lower bound) in all low-`R_f` cases; plausibility condition `I_sub > I_ss` fails; `γ_p = 0.50`.

### 3.3 Simulator Adequacy Proposition

> Let `i_a^sim(t)` be a simulator-reconstructed phase current. SAMBP confidence `γ ≥ γ_th` requires:
> ```
> ‖∂|i_a^sim|/∂t|_{t=t₀⁺}‖ ≥ I_sub/τ_ac
> ```
> Positive-sequence simulators produce `∂|Î₁|/∂t ≪ I_sub/τ_ac` for `τ_ac < 0.1 s`.

### 3.4 Test configuration

| Parameter | Value |
|---|---|
| Simulator | ANDES v1.9, positive-sequence TDS |
| Network | IEEE 14-bus, standard (no wind extension) |
| Generator model | GENROU (round-rotor, 6th-order salient) |
| Fault bus | Bus 1 (slack generator terminal) |
| Fault types | 3PH, SLG, LL |
| `R_f` sweep | 0.01, 0.05, 0.10/0.15, 0.50 pu |
| Confidence threshold | `γ_th = 0.70` |
| Relay initial settings | pickup = 1.2 pu, TMS = 0.05 s |
| Pre-fault voltage | 1.022 pu |
| Run strategy | One TDS run per unique `R_f`; fault type is post-processed metadata |

Note: ANDES positive-sequence does not distinguish 3PH vs. SLG/LL at the waveform level. Cases sharing the same `R_f` produce identical waveforms.

---

## §4 Implementation

### File map

| File | Description |
|---|---|
| `04_code/sambp/sync_oc/run_tr59_andes.py` | ANDES TDS driver; 10-case batch runner |
| `04_code/sambp/io_utils/andes_adapter.py` | `run_andes_tds(fault_rf=…)` with per-`R_f` caching |
| `04_code/sambp/sync_oc/sync_oc_core.py` | SAMBP confidence scorer, LM estimator, adaptation logic |
| `04_code/sambp/sync_oc/outputs/tr59/tr59_results.csv` | Full 10-case results (confidence, LM parameters, trip times) |
| `04_code/sambp/sync_oc/outputs/tr59/tr59_summary.txt` | Human-readable summary (0/10 adaptation) |

### ANDES adapter interface (from `andes_adapter.py`)

```python
run_andes_tds(fault_rf: float, fault_bus: int = 1,
              network: str = "ieee14.xlsx",
              t_end: float = 2.0, dt: float = 1e-3) -> FaultCase
```
Returns the standard `FaultCase` dict `{t, ia, ib, ic, va, vb, vc, fault_type, fault_R_pu, label, meta, source}` — same schema as `comtrade_adapter.py` (TR-87). Per-`R_f` caching avoids re-running identical TDS simulations for different fault-type labels.

---

## §5 Validation

### 5.1 Full 10-case results (from `tr59_results.csv`)

| Case | Type | `R_f` (pu) | `γ` | `Î_sub` (pu) | `τ̂_ac` (s) | `Î_ss` (pu) | LM cost | Adapted? |
|---|---|---|---|---|---|---|---|---|
| tr59_3ph_R001 | 3PH | 0.01 | 0.500 | 0.500 | 0.0050 | 4.684 | 76.9 | No |
| tr59_3ph_R005 | 3PH | 0.05 | 0.532 | 0.500 | 0.0119 | 3.903 | 79.4 | No |
| tr59_3ph_R010 | 3PH | 0.10 | 0.548 | 0.500 | 0.0171 | 3.103 | 52.2 | No |
| tr59_3ph_R050 | 3PH | 0.50 | 0.582 | 1.153 | 0.0051 | 0.741 | 1.81 | No |
| tr59_slg_R001 | SLG | 0.01 | 0.508 | 0.500 | 0.0050 | 4.641 | 61.1 | No |
| tr59_slg_R005 | SLG | 0.05 | 0.547 | 0.500 | 0.0050 | 3.865 | 27.4 | No |
| tr59_slg_R015 | SLG | 0.15 | 0.543 | 0.500 | 0.0298 | 2.518 | 10.3 | No |
| tr59_slg_R050 | SLG | 0.50 | 0.566 | 1.128 | 0.0062 | 0.748 | 2.52 | No |
| tr59_ll_R001 | LL | 0.01 | 0.508 | 0.500 | 0.0050 | 4.641 | 61.1 | No |
| tr59_ll_R005 | LL | 0.05 | 0.547 | 0.500 | 0.0050 | 3.865 | 27.4 | No |
| **Mean** | | | **0.538** | | | | | **0/10** |

All 10 LM fits converged (`lm_success = True`). Zero adaptations accepted.

### 5.2 Confidence breakdown by `R_f` regime

**Low `R_f` (0.01–0.15 pu):** `Î_sub = 0.500 pu` (lower bound hit). ANDES waveform contains no genuine subtransient decrement; LM has no signal to fit. Since `Î_sub ≤ Î_ss` (e.g. 0.500 vs. 4.684 pu at `R_f = 0.01`), plausibility condition fails → `γ_p = 0.50` → `γ ≤ 0.548`.

**High `R_f` (0.50 pu):** Weak fault current (I_peak ≈ 0.76 pu). Positive-sequence envelope decays toward pre-fault current, providing a small subtransient-like feature. LM pushes `Î_sub ≈ 1.15 pu > Î_ss ≈ 0.74 pu` — plausibility marginally satisfied. But RMSE remains ~0.06 pu → `γ` rises only to 0.582, still below 0.70.

### 5.3 Comparison with synthetic-data baseline

| Condition | `γ` (ANDES) | `γ` (synthetic) | Gap |
|---|---|---|---|
| 3PH, `R_f = 0.01` pu | 0.500 | ≥ 0.85 | ~0.35 |
| 3PH, `R_f = 0.50` pu | 0.582 | ≥ 0.80 | ~0.22 |

Gap Δγ ≈ 0.30 on synthetic vs. ANDES data — attributable entirely to missing subtransient physics.

---

## §6 Results

**Summary metrics (from `tr59_summary.txt`):**

| Metric | Value |
|---|---|
| Cases run | 10 |
| LM failures | 0 |
| Adaptation accepted | 0/10 |
| Mean confidence γ | 0.538 |
| γ range | [0.500, 0.582] |
| Mean trip speedup | 0 ms |
| Fixed-scheme trip times | 1011 ms (`R_f = 0.01`), 1016 ms (`R_f = 0.05`) |

The fixed-scheme trip times confirm ANDES TDS reached fault inception and the OC relay would have operated under original settings. No speedup because γ < γ_th in all cases.

**Key engineering implication:** The confidence gate behaves as designed — it correctly refuses to adapt when input data quality is insufficient. This is a **security property**, not a failure.

---

## §7 Limitations

**L-1 — Positive-sequence scope only:** This TR uses ANDES positive-sequence TDS exclusively. The finding is specific to this simulator class. PSCAD/EMTP-RV EMT tools are expected to meet the simulator adequacy condition — confirmed by TR-67 (pending).

**L-2 — Fault type not distinguished by ANDES:** ANDES positive-sequence does not differentiate 3PH vs. SLG vs. LL at the waveform level. Cases with the same `R_f` produce identical `i_a(t)` regardless of fault type. The fault type label is metadata only. This makes the 10-case matrix effectively a 5-case sweep (4 `R_f` values for 3PH, 4 for SLG with partial overlap, 2 for LL — all sharing waveforms at matching `R_f`).

**L-3 — No AVR dynamics sweep:** All runs use GENROU with fixed excitation. AVR action (EXST1 or SEXS) affects the post-fault voltage recovery and would modify `Î_ss`. The effect on `γ` for AVR-regulated cases is unknown and deferred to TR-67.

**L-4 — Single bus (Bus 1 slack):** All faults are applied at the slack bus. Generator fault current contribution from non-slack buses is not tested. Multi-generator network validation deferred to TR-02 (paper_a follow-on).

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, andes (v1.9+), numpy, scipy.

```bash
# Run 10-case ANDES validation batch
cd /root/phd_thesis/04_code/sambp/sync_oc
python run_tr59_andes.py \
    --network ieee14.xlsx \
    --fault_bus 1 \
    --rf_values 0.01 0.05 0.10 0.50 \
    --rf_slg 0.01 0.05 0.15 0.50 \
    --rf_ll 0.01 0.05 \
    --output_dir outputs/tr59/

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_7_IBR_extension/TR59_ANDES_syncoc
pdflatex main_report59 && bibtex main_report59 && \
    pdflatex main_report59 && pdflatex main_report59
```

**Output files:**
- `outputs/tr59/tr59_results.csv` — full 10-case results with all LM parameters
- `outputs/tr59/tr59_summary.txt` — human-readable 0/10 adaptation summary

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report59.tex` read + `tr59_results.csv` + `tr59_summary.txt`. Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report59.tex` and `outputs/tr59/` are authoritative — this file is a read-only analytical summary.*
