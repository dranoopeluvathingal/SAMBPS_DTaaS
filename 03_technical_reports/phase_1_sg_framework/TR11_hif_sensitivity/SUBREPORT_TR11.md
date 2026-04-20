# SUBREPORT_TR11 — High-Impedance Fault Sensitivity Margin Study

**TR ID:** TR-11  
**Full title:** High-Impedance Fault Sensitivity Margin Study: Minimum Detectable Fault Current for Each Protected Zone  
**Ref:** IITM/EE/PhD/AVE/TR-11/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR11_hif_sensitivity/`  
**Report file:** `main_report11.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework  
**Thesis allocation:** Ch. 4/5 (Differential Protection) — detection limits  
**Cross-linked TRs:** TR-08/09/10 (MC + CT saturation), TR-12 (87L magnitude override extension)

---

## §1 Scope

**What TR-11 IS:**
- Scale-factor sweep study: α∈{1.00, 0.70, 0.50, 0.30, 0.20, 0.15, 0.10, 0.07, 0.05} × 10 relay-scenario combinations × 200 trials each
- Establishes minimum detectable fault current (I_50: current at which TPR first drops below 0.50)
- **87B (bus) and 87T zones: TPR=1.000 down to α=0.05** (I_f≥0.20 pu) — no SAMBP penalty vs conventional
- **87L zone: SAMBP Stage-2 raises effective detection threshold to 0.56 pu (3ph) / 0.72 pu (ag)** vs <0.24 pu for conventional — factor 3–4× penalty
- **OC relay:** detection threshold analytically determined by pickup setting (1.5 pu RMS)
- Quantifies the selectivity–sensitivity trade-off inherent in the Stage-2 gate

**What TR-11 IS NOT:**
- Not a correction study (remediation deferred to Phase 2 87L extensions)
- Not hardware validated
- Not applying CT saturation + HIF simultaneously

**Core contribution:** Provides the first quantitative selectivity–sensitivity trade-off characterisation for the SAMBP Stage-2 gate, localising the penalty exclusively to the 87L zone and attributing it to distributed-parameter modelling approximation at low SNR.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-11 |
|---|---|---|
| TR-08/09 | Parametric robustness (nominal current level) | No fault current scaling |
| TR-03 | 87L nominal validation | No HIF current margin |
| IEEE C37.232 | HIF detection guidelines | Not SAMBP-specific |

**Novelty:** Zone-specific HIF margin characterisation with quantitative I_50 thresholds; identifies distributed-parameter modelling as root cause of 87L sensitivity asymmetry.

---

## §3 Method

### 3.1 Scale Factor Sweep

```
i_k^scaled(t) = α·(1+δ_j)·i_k^nom(t),  δ_j ~ U(−0.05, +0.05)

α ∈ {1.00, 0.70, 0.50, 0.30, 0.20, 0.15, 0.10, 0.07, 0.05}
N=200 per (zone, scenario, α); seed 2026
```

±5% jitter prevents identical trials; sign preserved per phase.

### 3.2 Test Matrix

| Zone | Fault location | Type | I_f^nom (pu) |
|---|---|---|---|
| 87B_A | bus_A | 3ph | 10.000 |
| 87B_A | bus_A | AG | 6.000 |
| 87L | line_mid | 3ph | 8.000 |
| 87L | line_mid | AG | 4.800 |
| 87B_B | bus_B | 3ph | 6.667 |
| 87B_B | bus_B | AG | 4.000 |
| 87T | transformer_hv | 3ph | 6.667 |
| 87T | transformer_hv | AG | 4.000 |
| OC | bus_C_load | 3ph | 4.348 |
| OC | bus_C_load | AG | 2.609 |

---

## §4 Implementation

```
04_code/sambp/sambp_system/
└── run_hif_study.py    # scale factor sweep (seed 2026)
```

---

## §5 Validation

### 5.1 Bus differential zones (87B_A, 87B_B) — no penalty

Both bus zones maintain TPR=1.000 for both conv and SAMBP across all α down to 0.05.  
At α=0.05: bus_B/AG: I_f=0.20 pu = I_op^min → detected in all 200 trials. Model accurately fits small sinusoidal differential → low κ_n, f_int≈1.

### 5.2 Transformer zone (87T) — no penalty

Identical to 87B. TPR=1.000 for both methods to α=0.05.

### 5.3 Line differential zone (87L) — critical sensitivity loss

| α | I_f (3ph) | Conv 3ph | SAMBP 3ph | SAMBP AG |
|---|---|---|---|---|
| 1.00 | 8.000 | 1.000 | 1.000 | 1.000 |
| 0.20 | 1.600 | 1.000 | 1.000 | 1.000 |
| 0.15 | 1.200 | 1.000 | 1.000 | **0.000** ← |
| 0.07 | 0.560 | 1.000 | **0.000** ← | 0.000 |
| 0.05 | 0.400 | 1.000 | 0.000 | 0.000 |

**Effective detection thresholds:**
```
Conv:       I_f,min ≲ 0.24 pu (3ph, α=0.05)
SAMBP 3ph:  I_f,min ≈ 0.56 pu (α=0.07)
SAMBP AG:   I_f,min ≈ 0.72 pu (α=0.15)
```
SAMBP Stage-2 gate raises 87L effective pickup by 3–4× vs conventional relay.

### 5.4 OC relay

Detection at bus_C_load/3ph: pickup 1.5 pu RMS → I_f^nom=4.348 pu peak. Detection fails at α≤0.30 (I_rms ≈ 0.922 pu < 1.5 pu). For AG: I_f^nom=2.609 pu → I_rms≈1.845 pu; detection fails at α≤0.70. Stage-2 gate not applied to OC.

### 5.5 Detection Margin Summary

| Zone | I_f^nom | I_50^conv | I_50^SAMBP | Penalty |
|---|---|---|---|---|
| 87B_A/3ph | 10.000 | <0.50 | <0.50 | None |
| 87B_A/AG | 6.000 | <0.30 | <0.30 | None |
| **87L/3ph** | 8.000 | <0.40 | **0.56** | ≈0.56 pu |
| **87L/AG** | 4.800 | <0.24 | **0.72** | ≈0.72 pu |
| 87B_B/3ph | 6.667 | <0.33 | <0.33 | None |
| 87B_B/AG | 4.000 | <0.20 | <0.20 | None |
| 87T/3ph | 6.667 | <0.33 | <0.33 | None |
| 87T/AG | 4.000 | <0.20 | <0.20 | None |
| OC/3ph | 4.348 | 1.304 | 1.304 | None |
| OC/AG | 2.609 | 1.826 | 1.826 | None |

---

## §6 Results

| Metric | Value |
|---|---|
| 87B, 87T detection threshold | I_f ≥ 0.20 pu (no penalty vs conventional) |
| 87L 3ph detection threshold (SAMBP) | ≈ 0.56 pu (vs <0.24 pu conventional) |
| 87L AG detection threshold (SAMBP) | ≈ 0.72 pu (vs <0.24 pu conventional) |
| Penalty factor (87L) | 3–4× |
| Root cause | Low-SNR differential → LM solution f_int < 0.60 → veto |
| 87B robustness advantage | Direct algebraic sum, no distributed capacitance, better model fit at low I |
| Practical penalty range (87L/AG) | 0.20–0.72 pu (below conventional pickup < this anyway) |
| Preferred remediation | Improved distributed-parameter 87L forward model (π-section) |

---

## §7 Limitations

**L-1 — Practical significance of 87L penalty:** For I_f < 0.20 pu (below I_op^min), conventional relay also cannot detect. Real penalty only for I_f ∈ [0.20, 0.72] pu. Special HIF algorithms required regardless.

**L-2 — Root cause (distributed parameters):** Simple lumped-parameter line model; distributed capacitance and charging current not modelled. At low current, model fit degrades. Π-section model would improve.

**L-3 — No CT saturation combination:** HIF + CT saturation simultaneously not studied.

**L-4 — Magnitude override applicability:** Applying I_ovr to 87L requires I_ovr ≈ 0.30 pu (below 0.72 pu SAMBP threshold) — risks reduced selectivity against through-fault CT saturation. Preferred fix is improved forward model.

---

## §8 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_hif_study.py --seed 2026 --n-trials 200 --alpha-levels 1.0,0.7,0.5,0.3,0.2,0.15,0.1,0.07,0.05

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR11_hif_sensitivity
pdflatex main_report11 && bibtex main_report11 && pdflatex main_report11 && pdflatex main_report11
```

**Key output:** TPR vs α per zone/scenario; I_50 table; detection margin summary; zone-specific selectivity–sensitivity plots.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report11.tex` read (439 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report11.tex` is authoritative — this file is a read-only analytical summary.*
