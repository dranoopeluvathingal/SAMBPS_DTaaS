# SUBREPORT_TR20 — Frequency-Adaptive 87L Charging Correction

**TR ID:** TR-20  
**Full title:** Frequency-Adaptive 87L Charging-Current Correction for Inverter-Dominated Microgrids  
**Ref:** IITM/EE/PhD/AVE/TR-20/2026  
**Folder:** `03_technical_reports/phase_2_87L_deep/TR20_frequency_adaptive_87L/`  
**Report file:** `main_report20.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 2 — 87L Deep-Dive  
**Thesis allocation:** Ch. 4 (Line Differential) — microgrid/IBR frequency adaptation  
**Cross-linked TRs:** TR-15 (fixed pi-section baseline), TR-17 (adaptive threshold), TR-21 (harmonic pre-filter references TR-20 frequency estimator)

---

## §1 Scope

**What TR-20 IS:**
- Frequency-adaptive pi-section correction: i_C,adapt = B_C × (f_hat/f0) × Im{H[v_avg]}
- Zero-crossing frequency estimator: median inter-crossing interval, 2-cycle window, accuracy δf < 0.01 Hz
- **21/21 scenarios correct (100%)**: no-fault, internal fault, external fault × 7 frequencies (47–53 Hz)
- **Residual eliminated**: ε_C,adapt < 10^-5 pu vs ε_C,fixed = 0.0033 pu at 47 Hz (>1000× improvement)
- Critical B_C for fixed-correction false trips: 2.0 pu at 47 Hz — study network B_C=0.079 pu is 25× below critical
- ROCOF robustness: 2 Hz/s ROCOF → 6.3×10^-5 pu correction lag error per cycle (negligible)

**What TR-20 IS NOT:**
- Not a new protection element — charging correction upgrade only
- The fixed TR-15 correction is safe for this study network; adaptive is recommended as a robust default
- Not hardware validated

**Core contribution:** Derives the frequency-dependent charging residual formula; identifies critical B_C for fixed-correction failure; shows that zero-crossing estimator achieves δf < 0.01 Hz at 4000 Sa/s — two orders of magnitude better than needed.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-20 |
|---|---|---|
| TR-15 | Voltage-based pi-section (Mode 1) at f=50 Hz | Fixed B_C; residual grows at off-nominal f |
| IEC 60255-181 | Protection operation down to 47 Hz | No charging correction guidance |
| Schweitzer2010 | Zero-crossing frequency estimation | Not applied to differential protection |

**Novelty:** First frequency-adaptive charging correction for model-based line differential; extends safe operation to all foreseeable line lengths (B_C up to 2.0 pu) at any frequency in 47–53 Hz range.

---

## §3 Method

### 3.1 Frequency-Adaptive Formula

```
TR-15 fixed: i_C(t) = B_C × Im{H[v_avg(t)]}
                    = B_C × Im{H[(v_S+v_R)/2]}

Actual charging at f_actual:
  i_C,actual = B_C × (f_actual/f0) × Im{H[v_avg]}

TR-20 adaptive: i_C,adapt = B_C × (f_hat/f0) × Im{H[v_avg]}

Residual after adaptive correction:
  ε_C,adapt = (B_C/f0) × |f_hat - f_actual| × V_rms
  ≤ (0.079/50) × 0.01 × 1.0 = 1.6×10^-5 pu  (for δf < 0.01 Hz)
```

### 3.2 Zero-Crossing Estimator

```python
# Sub-sample interpolation at each positive-going zero crossing:
t_cross,k = k + (-v[k]) / (v[k+1] - v[k])   [samples]

# Period = median inter-crossing interval:
T_hat = median{t_cross,k+1 - t_cross,k}
f_hat = 1/T_hat

# Fallback: f_hat = f0 = 50 Hz if < 3 zero crossings
# Clamp: f_hat ∈ [47, 53] Hz
```

DFT alternative implemented in `line_freq_adaptive.py` for comparison; zero-crossing preferred for lower latency (~0.5 vs 2 cycles).

---

## §4 Validation

### 4.1 No-fault residual charging error

| f (Hz) | ε_C,fixed (pu) | ε_C,adapt (pu) | α50,fix | α50,adp | Improvement |
|---|---|---|---|---|---|
| 47 | 0.00331 | <10^-5 | 0.00331 | <10^-5 | >1000× |
| 48 | 0.00221 | <10^-5 | 0.00221 | <10^-5 | >1000× |
| 50 | 0.00000 | 0.00000 | 0.000 | 0.000 | — |
| 53 | 0.00331 | <10^-5 | 0.00331 | <10^-5 | >1000× |

Both methods satisfy α50 ≤ 0.030 for study network (B_C=0.079 pu). Adaptive provides >1000× margin for future tighter thresholds or larger B_C lines.

### 4.2 Internal fault (0.15 pu) — both methods trip correctly at all 7 frequencies

Fixed-correction slight elevation at 47/53 Hz (residual adds in-phase): conservative effect, no missed trips.

### 4.3 External fault — no false trips at any frequency (both methods)

### 4.4 Frequency estimator accuracy

δf < 0.01 Hz for all 7 test frequencies (4000 Sa/s, 4-cycle window). DFT: δf < 0.1 Hz (adequate but higher latency).

### 4.5 Overall: 21/21 scenarios correct (100%)

---

## §5 Results

| Metric | Value |
|---|---|
| Adaptive formula | i_C = B_C × (f_hat/f0) × Im{H[v_avg]} |
| Residual (adaptive) | <10^-5 pu at all frequencies |
| Residual (fixed) at 47 Hz | 0.0033 pu |
| Improvement | >1000× |
| Frequency estimator accuracy | δf < 0.01 Hz (zero-crossing, 4-cycle window) |
| ROCOF robustness | <10^-4 pu additional error at 2 Hz/s ROCOF |
| Critical B_C (fixed correction) | 2.0 pu at 47 Hz (25× above study network) |
| Selectivity | 21/21 (100%) |

---

## §6 Limitations

**L-1 — Fixed correction is safe for study network:** B_C=0.079 pu is 25× below critical; adaptive is a precautionary recommendation. Mandatory for EHV lines (B_C ≥ 0.5 pu) or tight threshold settings.

**L-2 — Zero-crossing latency during fault inception:** If fault inception occurs during the zero-crossing estimation window, the estimator falls back to f0=50 Hz. Impact: TR-15 behaviour (not degraded vs baseline).

**L-3 — Unbalanced ROCOF:** Phase-A, -B, -C frequencies diverging transiently (asymmetric disturbances) not validated. Extension: use per-phase estimators.

---

## §7 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_freq_adaptive_study.py --seed 2026 --freq-range 47,48,49,50,51,52,53 --model tr20

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_2_87L_deep/TR20_frequency_adaptive_87L
pdflatex main_report20 && bibtex main_report20 && pdflatex main_report20 && pdflatex main_report20
```

---

## §8 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report20.tex` read (450 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report20.tex` is authoritative — this file is a read-only analytical summary.*
