# SUBREPORT_TR15 — 87L Voltage-Based Pi-Section Compensation

**TR ID:** TR-15  
**Full title:** 87L Voltage-Based Pi-Section Compensation: Hilbert-Transform Charging Current Correction (Mode 1)  
**Ref:** IITM/EE/PhD/AVE/TR-15/2026  
**Folder:** `03_technical_reports/phase_2_87L_deep/TR15_87L_voltage_pi_section/`  
**Report file:** `main_report15.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 2 — 87L Deep-Dive  
**Thesis allocation:** Ch. 4 (Line Differential Protection) — voltage-assisted compensation  
**Cross-linked TRs:** TR-13 (pre-fault blind Mode 2), TR-16 (87B/87L coordination with Mode 1)

---

## §1 Scope

**What TR-15 IS:**
- Voltage-based pi-section (Mode 1): computes charging current from live PT measurements using Hilbert transform
- `i_C(t) = B_C · Im{H[(v_S+v_R)/2]}` — no pre-fault window required; works continuously including during fault
- **Residual: 0.001 pu** (PT noise floor — 18× better than Mode 2's 0.0009 pu is similar; primary advantage is continuous operation)
- **I_thresh: 0.08 pu; k_max: 2.0**
- **α50(ag): 0.05→0.03** (40% improvement from TR-13; 70% cumulative from TR-11 baseline)
- **α50(3ph): 0.05→0.02** (71% cumulative improvement from TR-11)
- Trip point: I_fund ≥ (1+k_max)/2 × I_thresh = 1.5 × 0.08 = 0.12 pu

**What TR-15 IS NOT:**
- Not applicable without voltage transformers (Mode 2 or 3 fallback for no-PT installations)
- Not hardware validated (GPS synchronisation assumed <1μs)
- Not addressing the residual penalty below α=0.03

**Core contribution:** Achieves cumulative 70% reduction in minimum detectable current for 87L (from TR-11 baseline), lowering α50(ag) from 0.15 to 0.03. Mode 1 becomes the preferred configuration for PT-equipped lines.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-15 |
|---|---|---|
| TR-13 | Pre-fault blind Mode 2; α50(ag) 0.07→0.05 | Requires pre-fault window; no improvement during fault evolution |
| TR-12 | Magnitude override; α50(ag) 0.15→0.10 | Symptom fix; does not reduce I_thresh |
| TR-11 | 87L HIF penalty baseline | No compensation |

**Novelty:** First continuous charging-current compensation for SAMBP 87L using Hilbert-transform approach; achieves α50(ag)=0.03 (4.8 pu × 0.03 = 0.14 pu absolute fault current) — within special HIF algorithm territory.

---

## §3 Method

### 3.1 Mode 1 Charging Current Computation

```python
def compute_charging_current(v_S: np.ndarray, v_R: np.ndarray,
                              B_C: float, fs: float) -> np.ndarray:
    v_avg = (v_S + v_R) / 2.0
    # Hilbert transform gives 90° phase-shifted (quadrature) component
    # dv/dt ≈ ω·H[v] for sinusoidal signals
    i_C = B_C * np.imag(hilbert(v_avg))
    return i_C

i_diff_corr = i_S + i_R - i_C  # corrected differential
```

### 3.2 Threshold Derivation

```
Residual (PT noise floor):  σ_res = 0.001 pu
k_max = 2.0  (worst-case correction error factor)
I_thresh = k_max × σ_res / (something) → set empirically at 0.08 pu

Trip condition: Î_diff,fund ≥ I_thresh AND conv_trip
              ≡ Î_fund ≥ 0.08 pu (vs 0.12 pu TR-13, 0.20 pu TR-11)
```

### 3.3 Synchronisation Requirement

```
GPS synchronisation: <1μs (standard PMU accuracy)
Phase error from 1μs timing error at 50Hz:
  Δφ = 2π × 50 × 1×10⁻⁶ = 0.000314 rad = 0.018° → negligible

Alternative without GPS: remote current phasor phase correction
  Δφ_est = angle(I_S/I_R) at nominal load → subtract from v_R before H[·]
```

---

## §4 Implementation

```
04_code/sambp/sambp_line_diff/models/
└── line_pi_section_model.py    # Mode 1 added: B_C·Im{H[(v_S+v_R)/2]}

04_code/sambp/sambp_line_diff/
└── line_differential_relay.py  # Mode 1 selected when PT data available
```

---

## §5 Validation

### 5.1 α50 progression (cumulative improvement chain)

| TR | α50(ag) | I_f,50 (pu) | Δ from prev |
|---|---|---|---|
| TR-11 (baseline) | 0.15 | 0.72 | — |
| TR-12 (override) | 0.10 | 0.48 | −33% |
| TR-13 (Mode 2) | 0.05 | 0.24 | −50% |
| **TR-15 (Mode 1)** | **0.03** | **0.14** | **−42%** |

Cumulative: 0.72→0.14 pu = **80% reduction**.

| TR | α50(3ph) | I_f,50 (pu) |
|---|---|---|
| TR-11 | 0.07 | 0.56 |
| TR-12 | 0.05 | 0.40 |
| TR-13 | 0.05 | 0.40 |
| **TR-15** | **0.02** | **0.16** |

### 5.2 HIF α-sweep (Mode 1)

| α | I_f (ag, pu) | Conv | TR-13 | TR-15 |
|---|---|---|---|---|
| 0.05 | 0.24 | 1.000 | 1.000 | 1.000 |
| 0.03 | 0.14 | 1.000 | 0.000 | **1.000** ✓ |
| 0.02 | 0.096 | 1.000 | 0.000 | **0.000** |

### 5.3 HIF margin at α=0.03 (ag)

I_fund = 0.14 pu; I_thresh = 0.08 pu → margin = 0.14/0.08 = 1.75× (above trip). At α=0.02: I_fund = 0.096 pu; margin = 0.096/0.08 = 1.20× — borderline; TPR not reliable.

---

## §6 Results

| Metric | Value |
|---|---|
| Mode 1 charging current formula | i_C = B_C·Im{H[(v_S+v_R)/2]} |
| Residual (Mode 1) | 0.001 pu (PT noise floor) |
| I_thresh | 0.08 pu |
| k_max | 2.0 |
| α50(ag) | 0.03 (cumulative 80% from TR-11 0.72 pu → 0.14 pu) |
| α50(3ph) | 0.02 (cumulative 71% from TR-11 0.56 pu → 0.16 pu) |
| GPS requirement | <1μs (or remote phasor phase correction) |
| Mode fallback | Mode 2 (pre-fault blind) if no PT; Mode 3 (nominal) if no pre-fault window |

---

## §7 Limitations

**L-1 — PT required:** Mode 1 not applicable to lines without voltage transformers. Mode 2 or 3 fallback.

**L-2 — GPS synchronisation:** Assumes <1μs timing accuracy. Without GPS, phase correction from remote phasor introduces additional uncertainty (estimated ±0.5°).

**L-3 — α=0.02 borderline:** At I_fund=0.096 pu, the 0.08 pu threshold margin is only 1.2×. Noise spikes may cause occasional missed detections below α=0.03.

**L-4 — B_C known assumption:** Mode 1 uses nameplate B_C; ±5% error adds 0.005 pu to residual — still << 0.08 pu threshold.

---

## §8 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_hif_study.py --seed 2026 --n-trials 200 --alpha-levels 1.0,0.7,0.5,0.3,0.2,0.15,0.1,0.07,0.05,0.03,0.02 --model tr15 --pi-mode 1

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_2_87L_deep/TR15_87L_voltage_pi_section
pdflatex main_report15 && bibtex main_report15 && pdflatex main_report15 && pdflatex main_report15
```

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report15.tex` read (473 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report15.tex` is authoritative — this file is a read-only analytical summary.*
