# SUBREPORT_TR08 — Monte Carlo Robustness Study (4k Trials)

**TR ID:** TR-08  
**Full title:** Monte Carlo Robustness Study: Parametric Perturbation Analysis of the Self-Adaptive Multi-Zone Bus Protection Suite  
**Ref:** IITM/EE/PhD/AVE/TR-08/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR08_monte_carlo_4k/`  
**Report file:** `main_report8.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework  
**Thesis allocation:** Ch. 9 (System-Level / Centralised Protection) — robustness evidence  
**Cross-linked TRs:** TR-05 (system integration baseline), TR-09 (recalibration fixes), TR-10 (CT saturation)

---

## §1 Scope

**What TR-08 IS:**
- First Monte Carlo robustness study of SAMBP: 4,000 trials (200/scenario × 20 scenarios) with analytical waveforms, NumPy seed 2026
- Version 1 (v1): analytical synthesis with 4 perturbation dimensions (δ_I, δ_DC, δ_τ, δ_φ)
- Version 2 (v2): pandapower AC power flow + IEC 60909 fault currents, 500 trials/scenario
- v1 reveals: 3 failure types — (A) bus zone systematic veto (TPR=0 bus_A/3ph), (B) transformer FPR artefact (FPR=1.0 bus_C/87T), (C) 87L through-current correct veto (expected)
- v2 achieves perfect selectivity (TPR=FPR=1.0/0.0) — confirms v1 failures were model artefacts, not algorithm deficiencies
- Documents root causes and 5 recommendations (addressed in TR-09)

**What TR-08 IS NOT:**
- Not a corrected study (fixes in TR-09)
- Not a CT saturation study (TR-10)
- Not hardware validated

**Core contribution:** Identifies that LM upper-bound clipping (not gate logic) causes bus zone sensitivity loss, and that independent winding DC perturbation (not the protection algorithm) causes transformer FPR artefact. Both are model artefacts.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-08 |
|---|---|---|
| TR-05 | Nominal selectivity 10/10 | Single nominal waveform per scenario |
| IEEE C37.230 | Protection testing standards | No physics-derived perturbation model |

**Novelty:** First parametric robustness study of SAMBP; identifies v1 model artefacts that would otherwise appear as algorithm failures; pandapower v2 confirms perfect performance under physical fault currents.

---

## §3 Method

### 3.1 Perturbation Model (v1)

```
For each nominal waveform i_k(t) = I_peak·sin(ωt+φ_k) + I_dc·e^{−t/τ}:

δ_I  ~ U(−0.20, +0.20)  → I_peak' = I_peak·(1+δ_I)
δ_dc ~ U(−0.30, +0.30)  → I_dc'   = I_dc·(1+δ_dc)
δ_τ  ~ U(−0.20, +0.20)  → τ'      = τ·(1+δ_τ)
δ_φ  ~ U(−π/4, +π/4)    → φ_k'    = φ_k + δ_φ

N=200 per scenario; 20 scenarios × 200 = 4,000 total trials; seed 2026
```

### 3.2 v2 (Pandapower)

```
Network: radial 100 MVA, 33/11 kV, R/X=0.0637 → τ_dc≈50ms throughout
Pandapower AC power flow: pre-fault V = 0.986–0.992 pu (load sag)
IEC 60909 short-circuit: I_f 9–10% higher than analytical (V_pre < 1.0)
N=500 per scenario; 10 scenarios × 500 = 5,000 trials
```

### 3.3 Metrics

TPR (sensitivity) = trips/expected-trips; FPR (false positive rate) = false-trips/non-trips. Aggregate pools over all relay-scenario pairs.

---

## §4 Implementation

```
04_code/sambp/sambp_system/
├── run_monte_carlo.py          # v1 synthetic waveforms (seed 2026)
├── run_tr08_v2_pandapower.py   # v2 pandapower waveforms (seed 2026)
└── network/
    └── pandapower_network.py   # pandapower network builder

outputs/tr08_v2/
└── tr08_v2_trials.csv          # N=500×10=5,000 rows
```

---

## §5 Validation

### 5.1 v1 Aggregate Performance

| Metric | Conventional | SAMBP |
|---|---|---|
| Sensitivity (TPR) | **1.0000** | 0.9006 |
| FPR | 0.0625 | 0.0625 |
| Specificity | 0.9375 | 0.9375 |
| Correct veto rate | — | 0.817 |
| Total vetoes | — | 1,958 |

### 5.2 v1 Notable Failures

**(A) bus_A/3ph — 87B_A: SAMBP TPR = 0.000** (100% vetoed)  
Root cause: I_peak+δ_I > 10 pu (static upper bound); LM clips to 10 pu → ε_CT inflated → f_int=0 → veto. Not inception-angle dependent (veto at all |δ_φ| bins). LM finds wrong local minimum at boundary.

**(B) bus_C_load / 87T: FPR = 1.000** (both conventional and SAMBP)  
Root cause: Independent-winding DC perturbation model applies non-zero DC to LV winding even though nominal through-fault DC is zero. Yd11 matrix M_X zeros balanced LV DC but HV DC uncancelled → spurious differential. Physical systems have correlated HV/LV DC (same source impedance).

**(C) 87L through-current vetoes: Correct** — these are intended (f_int→0 for zero differential).

### 5.3 v2 Aggregate Performance

| Metric | Conventional | SAMBP | Wilson 95% CI |
|---|---|---|---|
| Sensitivity (TPR) | **1.0000** | **1.0000** | [0.9996, 1.000] |
| FPR | 0.0000 | 0.0000 | [0.0000, 0.0002] |
| Specificity | 1.0000 | 1.0000 | — |
| Correct veto rate | — | **1.0000** | — |
| Total vetoes | — | 4,000 | — |

v2 confirms both v1 failures were model artefacts:
- (A) resolved: pandapower V_pre=0.992 pu + correlated fault current shifts LM initial guess away from boundary → correct convergence
- (B) resolved: pandapower computes HV/LV currents from same source voltage → physically correlated DC → differential cancels under Yd11

### 5.4 v1 vs v2 Comparison

| Metric | v1 (synthetic) | v2 (pandapower) | Δ |
|---|---|---|---|
| Conv TPR | 1.0000 | 1.0000 | 0 |
| Conv FPR | 0.0625 | 0.0000 | −0.0625 |
| SAMBP TPR | 0.9006 | 1.0000 | +0.0994 |
| SAMBP FPR | 0.0625 | 0.0000 | −0.0625 |
| Correct veto rate | 0.817 | 1.000 | +0.183 |

---

## §6 Results

| Metric | v1 | v2 |
|---|---|---|
| SAMBP TPR | 0.9006 | **1.0000** |
| SAMBP FPR | 0.0625 | **0.0000** |
| Correct veto rate | 0.817 | **1.000** |
| v1 failure cause | LM clipping + independent DC perturbation | — |
| v2 confirms | Pandapower physical correlation eliminates both artefacts | — |

---

## §7 Limitations

**L-1 — v1 analytical waveform model:** Independent per-winding DC perturbation violates transformer physical coupling. Only applicable to radial test network with analytical waveforms.

**L-2 — v1 LM upper bound:** Static 10 pu upper bound appropriate for through-fault/load levels but clips generator-terminal bus fault currents under +δ_I.

**L-3 — v2 only 10 fault scenarios:** v2 uses 10 scenarios (not 20) due to computational cost; sufficient to validate v1 artefact resolution.

**L-4 — No CT saturation perturbation:** CT saturation not included as perturbation dimension — addressed in TR-10.

---

## §8 Reproduction Recipe

```bash
# v1 study (analytical waveforms)
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_monte_carlo.py --seed 2026 --n-trials 200

# v2 study (pandapower)
python run_tr08_v2_pandapower.py --seed 2026 --n-trials 500

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR08_monte_carlo_4k
pdflatex main_report8 && bibtex main_report8 && pdflatex main_report8 && pdflatex main_report8
```

**Key output:** Per-relay-scenario TPR/FPR; aggregate table; veto statistics; per-trial CSV `tr08_v2_trials.csv`.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report8.tex` read (794 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report8.tex` is authoritative — this file is a read-only analytical summary.*
