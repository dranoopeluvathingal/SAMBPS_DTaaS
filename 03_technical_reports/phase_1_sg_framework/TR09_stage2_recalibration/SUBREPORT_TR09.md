# SUBREPORT_TR09 — Stage-2 Confidence Gate Recalibration and Extended MC

**TR ID:** TR-09  
**Full title:** Stage-2 Confidence Gate Recalibration and Extended Monte Carlo Validation (±30%/±60°)  
**Ref:** IITM/EE/PhD/AVE/TR-09/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR09_stage2_recalibration/`  
**Report file:** `main_report9.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework  
**Thesis allocation:** Ch. 9 (System-Level Protection) — estimation layer correctness proof  
**Cross-linked TRs:** TR-08 (failure identification), TR-10 (CT saturation)

---

## §1 Scope

**What TR-09 IS:**
- Implements two fixes for TR-08 root causes: (Class 1) dynamic upper-bound expansion for bus LM estimator; (Class 2) amplitude-only transformer winding perturbation
- Re-validates with **extended** perturbation bounds: δ_I∈±30%, δ_φ∈±60° (wider than TR-08)
- **TPR=1.000, FPR=0.000, correct veto rate=1.000** across all 20 scenarios, 4,000 trials
- Establishes key design principle: "If LM converges correctly → gate passes; if LM misconditioned → gate vetoes on faulty evidence." Fix is in estimation layer, not gate.

**What TR-09 IS NOT:**
- Not a new gate design — gate thresholds unchanged
- Not a CT saturation study (TR-10)
- Not hardware validated

**Core contribution:** Proves that the Stage-2 gate's 100% correct operation (under extended bounds) requires only estimation-layer corrections, not gate redesign. The gate's design invariant ("decides based on model quality, and only that") is preserved.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-09 |
|---|---|---|
| TR-08 | Identified root causes | Did not implement fixes |
| Levenberg1944/Marquardt1963 | LM algorithm | Static bounds; no dynamic expansion |

**Novelty:** Dynamic upper-bound expansion rule `U_dyn = max(U_static, 1.5×Î_rms√2)` with 0.9× activation threshold; amplitude-only transformer perturbation model preserving Yd11 HV/LV coupling.

---

## §3 Method

### 3.1 Class-1 Fix: Dynamic Upper Bound

Root cause: bus_A differential peak ≈ 9 pu; at +δ_I=+30%, peak = 11.7 pu > U_static=10 pu. LM clips I_diff,fund to 10 pu, inflates ε_CT → f_int=0 → veto.

```python
U_dyn = 1.5 × Î_rms·√2  if Î_rms·√2 > 0.9 × U_static
      = U_static           otherwise

# Multi-start: 4 initial guesses at [0.5, 0.4·U_dyn, 0.85·U_dyn, Î_rms·√2] pu
# Select: lowest residual norm solution
```

Verification: bus_A/3ph after fix — Î_diff,fund=12.5–13.1 pu (not clipped), ε_CT=0.000, κ_n=4.27, f_int=1.000.

### 3.2 Class-2 Fix: Amplitude-Only Transformer Perturbation

Root cause: `pw()` function resynthesises transformer winding phases using generic 3-phase template, breaking Yd11 HV/LV relationship and injecting non-zero LV DC (Yd11 matrix cancels balanced LV DC but not HV DC → spurious differential).

```python
def pw_tr(w: np.ndarray) -> np.ndarray:
    """Amplitude-only: preserves phase and DC for transformer winding pairs."""
    if np.max(np.abs(w)) < 1e-9:
        return w.copy()
    result = w.copy()
    result[:, mask] = w[:, mask] * (1 + delta_I)
    return result
```

Physical motivation: source impedance scales both windings by same fault-current multiplier. Phase and DC are not independently variable (volt-second constraint).

`pw_tr()` used for i_T_H_pu and i_T_X_pu only; all other waveforms use full `pw()`.

### 3.3 Extended MC Configuration

| Parameter | TR-08 | TR-09 |
|---|---|---|
| δ_I (current) | U(±20%) | U(±30%) |
| δ_dc | U(±30%) | U(±30%) |
| δ_τ | U(±20%) | U(±20%) |
| δ_φ (inception) | U(±45°) | U(±60°) |
| LM upper bound | static 10 pu | dynamic ×1.5 |
| Transformer perturb | pw() re-synthesis | pw_tr() amplitude |
| N per scenario | 200 | 200 |
| Total trials | 4,000 | 4,000 |
| Seed | 2026 | 2026 |

---

## §4 Implementation

```
04_code/sambp/sambp_system/
└── run_monte_carlo.py               # TR-09 model (seed 2026)

04_code/sambp/sambp_bus_diff/
└── inverse_estimation/
    └── bus_inverse_estimator.py     # dynamic bound + multi-start
```

---

## §5 Validation

### 5.1 Previously degraded cases — all recovered

| Case | TR-08 TPR | TR-09 TPR |
|---|---|---|
| bus_A/3ph — 87B_A | 0.000 | **1.000** ✓ |
| bus_A/ag — 87B_A | 0.695 | **1.000** ✓ |
| bus_B/3ph — 87B_B | 0.515 | **1.000** ✓ |
| bus_C_load 87T FPR | 1.000 | **0.000** ✓ |

### 5.2 Aggregate TR-09 vs TR-08

| Metric | TR-08 Conv | TR-08 SAMBP | TR-09 Conv | TR-09 SAMBP |
|---|---|---|---|---|
| TPR | 1.000 | 0.901 | 1.000 | **1.000** |
| FPR | 0.063 | 0.063 | **0.000** | **0.000** |
| Specificity | 0.938 | 0.938 | **1.000** | **1.000** |
| Correct veto rate | — | 0.817 | — | **1.000** |
| Total vetoes | — | 1,958 | — | 1,600 |

All 1,600 TR-09 vetoes are correct: all 87L through-fault scenarios (8 scenarios × 200 trials). Zero incorrect vetoes.

### 5.3 Key Insight

The conventional relay's FPR improvement (0.063→0.000) is also from the `pw_tr()` fix — the 87T artefact was present in both methods. Fixing the perturbation model improves both simultaneously.

---

## §6 Results

| Metric | Value |
|---|---|
| TPR (SAMBP) | 1.000 |
| FPR (SAMBP) | 0.000 |
| Correct veto rate | 1.000 |
| Total trials | 4,000 |
| Extended bounds | ±30%/±60° (wider than TR-08) |
| Dynamic bound activation | bus_A only (Î≈9 pu > 9 pu = 0.9×U_static) |
| Multi-start improvement | LM finds interior optimum vs boundary local min |
| Design invariant | Gate correct when estimation layer correct |

---

## §7 Limitations

**L-1 — pw_tr() removes inception-angle/DC variation from 87T:** Transformer zone not tested under δ_φ perturbation. Higher-fidelity 87T study requires correlated EMTP/PSCAD sweep.

**L-2 — CT saturation not included:** ε_CT as perturbation dimension not tested here — addressed in TR-10.

**L-3 — Dynamic bound range:** Activates only when Î_rms√2 > 9 pu. For networks with very high fault levels (>15 pu) the 1.5× multiplier may still be insufficient; generalize to network-specific upper bounds in future.

**L-4 — Software only:** Hardware-in-loop validation pending (noted in TR-06/TR-08).

---

## §8 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_monte_carlo.py --seed 2026 --n-trials 200 --model tr09

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR09_stage2_recalibration
pdflatex main_report9 && bibtex main_report9 && pdflatex main_report9 && pdflatex main_report9
```

**Key output:** Per-scenario TPR/FPR table (all 1.000/0.000); veto statistics; comparison with TR-08.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report9.tex` read (542 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report9.tex` is authoritative — this file is a read-only analytical summary.*
