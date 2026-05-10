# SUBREPORT_TR12 — 87L Magnitude Override Extension

**TR ID:** TR-12  
**Full title:** 87L Magnitude Override Extension: Zone-Calibrated Veto Suppression for High-Current Internal Faults  
**Ref:** IITM/EE/PhD/AVE/TR-12/2026  
**Folder:** `03_technical_reports/phase_2_87L_deep/TR12_87L_magnitude_override/`  
**Report file:** `main_report12.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 2 — 87L Deep-Dive  
**Thesis allocation:** Ch. 4 (Line Differential Protection) — HIF sensitivity improvement  
**Cross-linked TRs:** TR-10 (87B I_ovr=0.60 pu derivation), TR-11 (87L HIF baseline), TR-13 (pi-section follow-on)

---

## §1 Scope

**What TR-12 IS:**
- Applies the magnitude-override concept from TR-10 to the 87L zone with a zone-calibrated threshold I_ovr=0.30 pu (vs 87B's 0.60 pu)
- Establishes the design rule: "Stage-2 veto shall not suppress when I_fund ≥ zone-calibrated threshold"
- **α50(ag): 0.15→0.10** (I_f,50: 0.72→0.48 pu; 33% reduction in minimum detectable current)
- **α50(3ph): 0.07→0.05** (I_f,50: 0.56→0.40 pu; 29% reduction)
- Through-fault safety verified: Î_fund ≤ 0.08 pu << 0.30 pu → no false override triggered

**What TR-12 IS NOT:**
- Not a forward model improvement (that is TR-13/TR-15)
- Not hardware validated
- Not addressing the distributed-parameter root cause (TR-13 addresses that)

**Core contribution:** Establishes zone-specific I_ovr calibration methodology. Lower I_ovr for 87L (0.30 pu) reflects lower nominal fault current on lines vs buses; proves through-fault safety margin: max CT-sat-only Î_fund ≲ 0.08 pu on lines.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-12 |
|---|---|---|
| TR-10 | I_ovr=0.60 pu for 87B (bus zone) | Not applicable to 87L (different fault levels) |
| TR-11 | 87L HIF penalty characterised | No remediation |
| IEC 60255-187-3 | 87L sensitivity requirements | No model-based veto interaction |

**Novelty:** First zone-calibrated magnitude override for 87L; derives I_ovr from the ratio of minimum internal fault current to maximum CT-saturation-only spurious differential for line-connected CTs.

---

## §3 Method

### 3.1 I_ovr Derivation for 87L

```
Maximum through-fault CT-sat-only differential (87L):
  I_through,max ≈ 3.2 pu (load feeder, typical)
  ε_CT,max = 0.25
  Î_diff,CT-only ≲ ε_CT·I_through·(4/π) ≈ 0.25 × 3.2 × 1.27 ≈ 1.0 pu
  LM attributes to ε_CT → Î_diff,fund ≲ 0.08 pu

Minimum internal fault current (87L zone):
  I_fault,min ≈ I_f,nom × α=0.10 = 8.0 × 0.10 = 0.80 pu

Setting I_ovr = 0.30 pu:
  > Î_diff,fund,CT-only (0.08 pu) — margin 3.75×
  < I_fault,min at target α=0.10 (0.80 pu) — comfortable margin
```

### 3.2 Override Implementation

```python
# line_confidence_gate.py
magnitude_override = (
    I_diff_fund >= gate_cfg.veto_override_I_thresh   # 0.30 pu (87L-specific)
    and conventional_trip
)
model_vetoes_conventional = (
    gate_cfg.model_veto_enable
    and kn < gate_cfg.kappa_thresh
    and f_int < gate_cfg.f_int_trip_thresh
    and not magnitude_override
)
```

### 3.3 Test Matrix

Same α-sweep as TR-11; additionally verify through-fault safety at all ε_CT∈{0,0.05,0.10,0.15,0.20,0.25}.

---

## §4 Implementation

```
04_code/sambp/sambp_line_diff/adaptation/
└── line_confidence_gate.py    # veto_override_I_thresh=0.30 pu added
```

---

## §5 Validation

### 5.1 HIF α-sweep (post-override)

| α | I_f (ag, pu) | Conv TPR | TR-11 SAMBP | TR-12 SAMBP |
|---|---|---|---|---|
| 0.15 | 0.72 | 1.000 | 0.000 | **1.000** ✓ |
| 0.10 | 0.48 | 1.000 | 0.000 | **1.000** ✓ |
| 0.07 | 0.34 | 1.000 | 0.000 | 0.000 |
| 0.05 | 0.24 | 1.000 | 0.000 | 0.000 |

| α | I_f (3ph, pu) | Conv TPR | TR-11 SAMBP | TR-12 SAMBP |
|---|---|---|---|---|
| 0.07 | 0.56 | 1.000 | 0.000 | **1.000** ✓ |
| 0.05 | 0.40 | 1.000 | 0.000 | **1.000** ✓ |
| 0.03 | 0.24 | 1.000 | 0.000 | 0.000 |

### 5.2 Through-fault safety (at all ε_CT)

| ε_CT | Î_diff,fund (pu) | Override fires? | Correct? |
|---|---|---|---|
| 0.00 | 0.000 | No | ✓ |
| 0.10 | 0.041 | No | ✓ |
| 0.25 | 0.081 | No | ✓ |

Max through-fault Î_fund = 0.081 pu < 0.30 pu → override never fires on through-fault. Zero FPR increase.

### 5.3 Detection Threshold Summary

| Zone | Type | TR-11 I_50 | TR-12 I_50 | Improvement |
|---|---|---|---|---|
| 87L/3ph | SAMBP | 0.56 pu | 0.40 pu | −29% |
| 87L/AG | SAMBP | 0.72 pu | 0.48 pu | −33% |

---

## §6 Results

| Metric | Value |
|---|---|
| I_ovr (87L) | 0.30 pu (zone-calibrated; 87B uses 0.60 pu) |
| α50(ag) reduction | 0.15→0.10 (I_f,50: 0.72→0.48 pu, 33%) |
| α50(3ph) reduction | 0.07→0.05 (I_f,50: 0.56→0.40 pu, 29%) |
| Through-fault max Î_fund | 0.081 pu << 0.30 pu (3.7× margin) |
| Through-fault FPR increase | 0.000 (zero) |
| Design rule | Veto suppressed when I_fund ≥ zone-calibrated I_ovr AND conv_trip |

---

## §7 Limitations

**L-1 — Override is a symptom fix:** Root cause is distributed-parameter modelling error. I_ovr is a safety net; proper fix is π-section forward model (TR-13/TR-15).

**L-2 — I_ovr network-dependent:** Low-impedance microgrid or weak-infeed may have I_fault,min < 0.30 pu. Requires zone-specific re-calibration.

**L-3 — α50(ag)=0.07 still unresolved:** Below 0.48 pu (α=0.10), SAMBP still cannot detect. This gap requires forward model improvement (TR-13).

**L-4 — CT open-circuit not covered:** As in TR-10/TR-11.

---

## §8 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_hif_study.py --seed 2026 --n-trials 200 --alpha-levels 1.0,0.7,0.5,0.3,0.2,0.15,0.1,0.07,0.05 --model tr12

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_2_87L_deep/TR12_87L_magnitude_override
pdflatex main_report12 && bibtex main_report12 && pdflatex main_report12 && pdflatex main_report12
```

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report12.tex` read (370 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report12.tex` is authoritative — this file is a read-only analytical summary.*
