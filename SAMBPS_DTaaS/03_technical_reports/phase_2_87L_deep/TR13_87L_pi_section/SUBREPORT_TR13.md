# SUBREPORT_TR13 — 87L Pre-Fault Blind Pi-Section Compensation

**TR ID:** TR-13  
**Full title:** 87L Distributed-Parameter Compensation: Pre-Fault Blind Pi-Section Correction for Charging Current  
**Ref:** IITM/EE/PhD/AVE/TR-13/2026  
**Folder:** `03_technical_reports/phase_2_87L_deep/TR13_87L_pi_section/`  
**Report file:** `main_report13.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 2 — 87L Deep-Dive  
**Thesis allocation:** Ch. 4 (Line Differential Protection) — distributed-parameter compensation  
**Cross-linked TRs:** TR-11 (HIF baseline), TR-12 (magnitude override), TR-15 (voltage-based follow-on)

---

## §1 Scope

**What TR-13 IS:**
- Pre-fault blind pi-section correction: estimates line charging current from 1 cycle (20ms) of pre-fault data using linear least-squares on (v_S+v_R)/2 proxy
- **Residual reduction: 0.018→0.0009 pu (20× improvement)**
- **I_thresh reduction: 0.20→0.12 pu; max_factor: 5.0→3.0**
- **α50(ag): 0.07→0.05** (I_f,50: 0.34→0.28 pu; 18% reduction beyond TR-12)
- **α50(3ph): unchanged at 0.05** (already at noise floor without voltage data)
- Magnitude override (TR-12) becomes redundant as primary mechanism but retained as safety net

**What TR-13 IS NOT:**
- Not a real-time voltage measurement (Mode 1 — that is TR-15)
- Not hardware validated
- Not addressing the remaining penalty below α=0.05 (ag)

**Core contribution:** Proves that a 2-parameter linear LS fit on a single pre-fault cycle suffices to identify pi-section shunt admittance B_C and apply a correction that reduces residual 20×, attributing the remaining penalty to noise floor rather than model error.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-13 |
|---|---|---|
| TR-11 | HIF penalty characterised; root cause = distributed capacitance | No correction |
| TR-12 | Magnitude override reduces α50(ag) 0.15→0.10 | Symptom fix; not forward model |
| IEC 60044-8 | Merging unit accuracy for line differential | No pi-section compensation framework |

**Novelty:** Pre-fault blind correction — does not require voltage measurements during the fault; uses only the 20ms pre-fault window to calibrate B_C; validated that correction is accurate enough to reduce I_thresh from 0.20 to 0.12 pu.

---

## §3 Method

### 3.1 Pi-Section Model (Mode 2 — Pre-Fault Blind)

```
Charging current:  i_C(t) = B_C · dv/dt ≈ B_C · (v_S+v_R)/2 · ω·cos(ωt)

Pre-fault epoch:  t ∈ [t_fault − T_window, t_fault),  T_window=20ms (1 cycle)

Linear LS estimate:
  [B_C, φ_C] = argmin Σ (i_meas(t) − B_C·Im{H[v_proxy(t)]})²

Corrected differential:
  i_diff,corr(t) = i_S(t) + i_R(t) − i_C(t)
```

Three operating modes:
- Mode 1: voltage-based (TR-15) — uses live PT measurements
- Mode 2: pre-fault blind (TR-13) — uses pre-fault epoch to calibrate B_C; no PT during fault
- Mode 3: nominal fallback — fixed B_C from line datasheet

### 3.2 Correction Parameters

| Parameter | TR-11 baseline | TR-13 (Mode 2) |
|---|---|---|
| Residual (pu) | 0.018 | 0.0009 |
| I_thresh (pu) | 0.20 | 0.12 |
| max_factor | 5.0 | 3.0 |
| α50(ag) | 0.07 | 0.05 |
| α50(3ph) | 0.05 | 0.05 |

### 3.3 Test Matrix

Same α-sweep as TR-11/12; additionally verify pre-fault window accuracy at 5 line loading levels (0.2–1.0 pu).

---

## §4 Implementation

```
04_code/sambp/sambp_line_diff/models/
└── line_pi_section_model.py    # Modes 1/2/3; B_C estimation; i_C(t) output

04_code/sambp/sambp_line_diff/
└── line_differential_relay.py  # corrected i_diff fed to forward model
```

---

## §5 Validation

### 5.1 Residual characterisation

| Condition | Residual (pu) | Interpretation |
|---|---|---|
| No correction (baseline) | 0.018 | Capacitive charging uncompensated |
| Mode 3 (nominal B_C) | 0.006 | ±30% B_C error residual |
| Mode 2 (pre-fault LS) | **0.0009** | Near noise floor; 20× improvement |
| Mode 1 (voltage, TR-15) | 0.001 | PT noise floor |

### 5.2 HIF α-sweep (post-correction)

| α | I_f (ag, pu) | Conv | TR-12 | TR-13 (Mode 2) |
|---|---|---|---|---|
| 0.07 | 0.34 | 1.000 | 0.000 | **1.000** ✓ |
| 0.05 | 0.28 | 1.000 | 0.000 | **1.000** ✓ |
| 0.03 | 0.14 | 1.000 | 0.000 | 0.000 |

| α | I_f (3ph, pu) | Conv | TR-12 | TR-13 |
|---|---|---|---|---|
| 0.05 | 0.40 | 1.000 | 1.000 | 1.000 |
| 0.03 | 0.24 | 1.000 | 0.000 | 0.000 |

### 5.3 I_thresh reduction

With residual=0.0009 pu: I_thresh can be safely reduced to 0.12 pu (10× residual, k_max=3.0×).
Previous: I_thresh=0.20 pu = 11× residual of 0.018 pu.

---

## §6 Results

| Metric | Value |
|---|---|
| Residual (Mode 2) | 0.0009 pu (20× reduction from 0.018) |
| I_thresh | 0.20→0.12 pu |
| max_factor | 5.0→3.0 |
| α50(ag) | 0.07→0.05 (18% beyond TR-12) |
| α50(3ph) | 0.05 (unchanged — noise floor) |
| Pre-fault window | 20ms (1 cycle); robust to 0.2–1.0 pu loading |
| Override interaction | TR-12 override retained as safety net; rarely fires post-correction |

---

## §7 Limitations

**L-1 — Requires 20ms pre-fault data:** Evolving faults (inception during CT offset) may have shorter clean pre-fault window. Fallback: Mode 3 nominal.

**L-2 — B_C calibration accuracy:** ±5% error on B_C gives residual ≈ 0.003 pu (still 6× better than baseline). Robust to typical PT class 0.5 accuracy.

**L-3 — α50(3ph) not improved:** 3-phase faults have different charging balance; improvement limited to ag and other unbalanced faults. Mode 1 (TR-15) addresses 3ph.

**L-4 — No CT saturation + HIF combination:** As TR-11 limitation L-3.

---

## §8 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_hif_study.py --seed 2026 --n-trials 200 --alpha-levels 1.0,0.7,0.5,0.3,0.2,0.15,0.1,0.07,0.05,0.03 --model tr13 --pi-mode 2

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_2_87L_deep/TR13_87L_pi_section
pdflatex main_report13 && bibtex main_report13 && pdflatex main_report13 && pdflatex main_report13
```

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report13.tex` read (532 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report13.tex` is authoritative — this file is a read-only analytical summary.*
