# SUBREPORT_TR10 — CT Saturation Injection Study

**TR ID:** TR-10  
**Full title:** CT Saturation Injection Study: Stage-2 Gate Immunity to CT Saturation and Concurrent Saturation Sensitivity Analysis  
**Ref:** IITM/EE/PhD/AVE/TR-10/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR10_ct_saturation/`  
**Report file:** `main_report10.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework  
**Thesis allocation:** Ch. 5 (Differential Protection) — CT saturation characterisation  
**Cross-linked TRs:** TR-08 (MC baseline), TR-09 (extended MC), TR-11 (HIF margins)

---

## §1 Scope

**What TR-10 IS:**
- CT saturation sweep study: ε_CT ∈ {0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25} across 4 zones, 2 families × 200 trials each
- Family A (external): CT saturates on through-current → spurious differential (should not trip)
- Family B (internal): CT saturates on fault-current CT → degraded differential (should trip)
- **Pre-fix finding:** Gate correctly suppresses Family A FPR=0.000 but incorrectly vetoes Family B (internal TPR drops to 0.500 at ε_CT≥0.05 for bus zones)
- **Fix:** Magnitude-override rule in `bus_confidence_gate.py`: if Î_diff,fund ≥ 0.60 pu AND conv_trip → suppress veto regardless of f_int
- **Post-fix:** External FPR=0.000, Internal TPR=1.000 for ALL ε_CT∈[0,0.25] across all 4 zones

**What TR-10 IS NOT:**
- Not a CT inrush study (87T inrush discrimination in TR-03)
- Not hardware validated
- Not covering CT open-circuit (TR-04 limitation)

**Core contribution:** Identifies and resolves the fundamental tension: ε_CT-based veto cannot distinguish Scenario X (external+CT sat, I_diff,fund≈0) from Scenario Y (internal+CT sat, I_diff,fund≫0) without the magnitude discriminant. Derives I_ovr=0.60 pu threshold analytically.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-10 |
|---|---|---|
| IEC 60044-6 | CT saturation classification | No model-based gate analysis |
| TR-03/04 | Individual zone CT sat vetoing | No Family A/B systematic sweep |
| TR-09 | MC robustness (no CT sat) | CT saturation not as perturbation |

**Novelty:** First systematic sweep of CT saturation level against dual-family (external + internal) test matrix; derives I_ovr threshold from fundamental bound on CT-saturation-only differential.

---

## §3 Method

### 3.1 CT Saturation Model

SAMBP bus zone forward model already incorporates:
```
i_diff(t) = I_diff,fund·sin(ωt+φ) + ε_CT·I_diff,fund·sgn(sin ωt)
```

Injected distortion:
```
δi_CT(t) = ε_CT·I_peak·sgn(sin(2πf·(t−t_fault)+φ_k)),  t ≥ t_fault
```
Applied to largest-current feeder (Family A) or all feeders (Family B).

### 3.2 Test Matrix

4 zones × 2 families × 7 ε_CT levels × 200 trials = 11,200 total events. N=200 per cell (±5% amplitude jitter, seed 2026).

| Zone | Family A (external) | Family B (internal) |
|---|---|---|
| 87B_A | line_mid/3ph | bus_A/3ph+ag |
| 87L | bus_A/3ph | line_mid/3ph+ag |
| 87B_B | trans_hv/3ph | bus_B/3ph |
| 87T | bus_C_load/3ph | transformer_hv/3ph |

### 3.3 Pre-Fix Tension

```
At ε_CT ≥ 0.05:  f_int = clip(1 − ε_CT/0.10, 0, 1) = 0.5 < 0.60 → veto fires

Gate cannot distinguish:
  Scenario X: external fault + CT sat: I_diff,fund ≈ 0, ε_CT > 0 → CORRECT veto
  Scenario Y: internal fault + CT sat: I_diff,fund ≫ 0, ε_CT > 0 → WRONG veto

Discriminant: Î_diff,fund (large for Y, near-zero for X)
```

### 3.4 Magnitude-Override Fix

```python
magnitude_override = (
    I_diff_fund >= gate_cfg.veto_override_I_thresh   # 0.60 pu
    and conventional_trip
)
model_vetoes_conventional = (
    gate_cfg.model_veto_enable
    and kn < gate_cfg.kappa_thresh
    and f_int < gate_cfg.f_int_trip_thresh
    and not magnitude_override   # suppressed when large differential seen
)
```

**I_ovr threshold derivation:**
```
Maximum CT-sat-only differential (no real fault):
  Î_diff,CT-only ≲ ε_CT·I_through·(4/π) ≈ 0.25 × 5 pu × 1.27 ≈ 1.6 pu (extreme)
  But LM attributes square-wave to ε_CT → estimated Î_diff,fund ≲ 0.3 pu

Setting I_ovr = 0.60 pu:
  > estimated sat-only fundamental (0.3 pu)
  < minimum fault current in test network (≥ 2.0 pu)
  → comfortable margin both ways
```

---

## §4 Implementation

```
04_code/sambp/sambp_system/
└── run_ct_study.py                          # CT saturation sweep

04_code/sambp/sambp_bus_diff/adaptation/
└── bus_confidence_gate.py                   # magnitude override added
```

---

## §5 Validation

### 5.1 Pre-fix results (aggregate by ε_CT)

| ε_CT | Conv ext FPR | SAMBP ext FPR | Conv int TPR | SAMBP int TPR | Veto OK% |
|---|---|---|---|---|---|
| 0.00 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 |
| 0.02 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 |
| 0.05 | 0.250 | **0.000** | 1.000 | **0.500** | 0.571 |
| 0.10–0.25 | 0.250 | **0.000** | 1.000 | **0.500** | 0.571 |

Conv FPR=0.250 at ε_CT≥0.05: 87T trips on bus_C_load when transformer HV-side CT saturates.

### 5.2 Post-fix results (aggregate by ε_CT)

| ε_CT | Conv ext FPR | SAMBP ext FPR | Conv int TPR | SAMBP int TPR | Veto OK% |
|---|---|---|---|---|---|
| 0.00 | 0.000 | **0.000** | 1.000 | **1.000** | 1.000 |
| 0.02 | 0.000 | **0.000** | 1.000 | **1.000** | 1.000 |
| 0.05–0.25 | 0.250 | **0.000** | 1.000 | **1.000** | **1.000** |

SAMBP suppresses conventional relay FPR=0.250 while recovering internal TPR to 1.000.

### 5.3 Per-zone at ε_CT=0.25 (post-fix)

| Zone | Conv ext FPR | SAMBP ext FPR | Conv int TPR | SAMBP int TPR |
|---|---|---|---|---|
| 87B_A | 0.000 | 0.000 | 1.000 | 1.000 |
| 87L | 0.000 | 0.000 | 1.000 | 1.000 |
| 87B_B | 0.000 | 0.000 | 1.000 | 1.000 |
| **87T** | **1.000** | **0.000** | 1.000 | 1.000 |

87T is the only zone where conventional relay fails (FPR=1.000 at ε_CT≥0.05). SAMBP fully suppresses it while maintaining TPR=1.000.

---

## §6 Results

| Metric | Value |
|---|---|
| Post-fix External FPR | 0.000 (all ε_CT, all zones) |
| Post-fix Internal TPR | 1.000 (all ε_CT, all zones) |
| Conventional FPR at ε_CT≥0.05 | 0.250 (87T zone) — fully suppressed by SAMBP |
| Veto accuracy (post-fix) | 1.000 |
| Magnitude override threshold I_ovr | 0.60 pu (analytically derived) |
| 87L/87B_B zones (no override needed) | Robust across full ε_CT range |
| Pre-fix sensitivity loss (bus zones) | TPR 0.500 at ε_CT≥0.05 → recovered to 1.000 |

---

## §7 Limitations

**L-1 — I_ovr depends on network fault levels:** For high-impedance microgrids (I_fault,min ≪ 2 pu), the margin between sat-only differential and minimum fault current narrows. Zone-specific I_ovr tuning required.

**L-2 — CT open-circuit not covered:** Open-circuit produces clean sinusoidal spurious differential → f_int≈1.0, override may fire incorrectly. Requires CT secondary voltage monitoring (high-impedance scheme).

**L-3 — No CT remanence:** Pre-existing DC remanence in CT cores not modelled. Effect on saturation onset is scenario-dependent.

**L-4 — pw_tr() limitation for 87T:** Amplitude-only perturbation (from TR-09) means 87T Family B not tested under δ_φ. Higher-fidelity EMTP/PSCAD transformer study recommended.

---

## §8 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_ct_study.py --seed 2026 --n-trials 200 --eps-levels 0,0.02,0.05,0.10,0.15,0.20,0.25

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR10_ct_saturation
pdflatex main_report10 && bibtex main_report10 && pdflatex main_report10 && pdflatex main_report10
```

**Key output:** Pre/post-fix FPR/TPR tables by ε_CT; per-zone breakdown; veto accuracy sweep.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report10.tex` read (485 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report10.tex` is authoritative — this file is a read-only analytical summary.*
