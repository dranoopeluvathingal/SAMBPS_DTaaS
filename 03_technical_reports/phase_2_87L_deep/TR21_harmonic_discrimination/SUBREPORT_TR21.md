# SUBREPORT_TR21 — Harmonic-Component Discrimination for 87L (IBR Networks)

**TR ID:** TR-21  
**Full title:** Harmonic-Component Discrimination for 87L in Inverter-Based Resource Rich Networks  
**Ref:** IITM/EE/PhD/AVE/TR-21/2026  
**Folder:** `03_technical_reports/phase_2_87L_deep/TR21_harmonic_discrimination/`  
**Report file:** `main_report21.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 2 — 87L Deep-Dive  
**Thesis allocation:** Ch. 4 (Line Differential) — IBR harmonic interference  
**Cross-linked TRs:** TR-20 (frequency estimator used for harmonic regressors), TR-22 (negative-sequence 87LN, follow-on)

---

## §1 Scope

**What TR-21 IS:**
- Harmonic pre-filter: linear LS estimation and subtraction of 3rd/5th/7th harmonics from Δi' before the LM estimator
- Regressor matrix H: [cos(3ωt), sin(3ωt), cos(5ωt), sin(5ωt), cos(7ωt), sin(7ωt)] — QR solved once per cycle
- **21/21 scenarios correct (100%)**: no-fault, internal fault, external fault × 7 harmonic levels (0–0.10 pu 3rd harmonic)
- **Confidence fully restored**: c ≥ 0.99 in no-fault study at ALL harmonic levels (vs c ≈ 0.37 without filter for I_h3 ≥ 0.005 pu)
- **Fault detection unaffected**: I_fund estimate invariant to harmonics (orthogonality over integer-cycle windows)
- **Network-type diagnostic**: H_ratio = I_harm,rms / I_fund,DFT; SG (<0.05) / mixed / IBR (>0.20)
- Computational cost: < 0.02 ms per cycle (QR of 160×6 matrix)

**What TR-21 IS NOT:**
- Not correcting the amplitude estimate (harmonic-fundamental orthogonality means DFT amplitude is already unbiased)
- Not addressing inter-harmonics (non-integer multiples of f0)
- Not hardware validated

**Core contribution:** Proves that harmonic injection collapses LM confidence to c ≈ 0.37 (below c_min=0.80) even at IEEE 519 THD levels (I_h3 ≥ 0.005 pu), and that a single pre-filter stage fully restores confidence without affecting fault detection. Exploits fundamental-harmonic orthogonality theorem.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-21 |
|---|---|---|
| TR-11/15 | 87L LM estimator with 4-param model | No harmonic pre-filter; confidence collapses under IBR harmonics |
| IEEE 519 | THD limits (5%) | No impact analysis on model-based protection |
| Hooshyar2019 | IBR fault current characterisation | No differential protection LM confidence analysis |

**Novelty:** First systematic analysis of IBR harmonic impact on model-based line differential confidence gate; proves pre-filter sufficiency via orthogonality theorem; introduces H_ratio diagnostic for network-type identification.

---

## §3 Method

### 3.1 Harmonic Pre-Filter (Linear LS)

```
Δi''(t) = Δi'(t) - Σ_{h∈{3,5,7}} [A_h·cos(hω0t) + B_h·sin(hω0t)]

H = [cos(3ωt), sin(3ωt), cos(5ωt), sin(5ωt), cos(7ωt), sin(7ωt)]  (N×6)
ĉ = (H^T H)^-1 H^T Δi'   (QR factorisation)

Amplitude threshold: skip if √(A_h² + B_h²) < 10^-4 pu (prevents noise subtraction)
```

Regressors use f_hat from TR-20 estimator → maintains orthogonality at any frequency in 47–53 Hz.

### 3.2 Orthogonality Theorem

For integer-cycle windows (K complete cycles):
```
Σ_{n=0}^{KN-1} sin(2πn/N) · sin(2πhn/N) = 0  ∀ h ∈ Z+, h ≠ 1
```
Harmonics do NOT bias the DFT-based I_fund estimate. Pre-filter improves confidence (LM residual norm), not amplitude.

### 3.3 Network Classification

| H_ratio | Network type |
|---|---|
| < 0.05 | SG-dominated (low harmonics) |
| 0.05 – 0.20 | Mixed |
| > 0.20 | IBR-dominated |

IEEE 519 THD limit 5% → I_h3 ≈ 0.035 pu → H_ratio ≈ SG/mixed boundary.

---

## §4 Validation

### 4.1 No-fault confidence vs harmonic injection

| I_h3 (pu) | c without filter | c with TR-21 filter |
|---|---|---|
| 0.000 | 1.000 | 1.000 |
| 0.005 | 0.41 (< c_min) | **0.99** |
| 0.010 | 0.37 (< c_min) | **0.99** |
| 0.050 | 0.37 (< c_min) | **0.99** |
| 0.100 | 0.37 (< c_min) | **0.99** |

Without filter: 1/7 pass c_min=0.80 (zero-harmonic only).  
With TR-21 filter: 7/7 pass c_min=0.80.

### 4.2 Internal fault (0.15 pu): I_fund invariant at all harmonic levels

DFT-recovered I_fund = 0.150 pu regardless of I_h3 (0–0.100 pu). Both methods trip correctly.

### 4.3 External fault: no false trips at any harmonic level (both methods)

### 4.4 Overall: 21/21 scenarios correct (100%)

---

## §5 Results

| Metric | Value |
|---|---|
| Selectivity | 21/21 (100%) |
| No-fault confidence (TR-21) | ≥0.99 at all harmonic levels (0–0.10 pu) |
| No-fault confidence (no filter) | 0.37 for I_h3 ≥ 0.005 pu (below c_min=0.80) |
| Fault amplitude estimate | Invariant (orthogonality theorem) |
| Computational cost | <0.02 ms/cycle (QR of 160×6 matrix) |
| H_ratio diagnostic | SG <0.05 / mixed / IBR >0.20 |
| Pipeline position | Stage 3 (after TR-20 freq-adaptive correction, before LM estimator) |

---

## §6 Limitations

**L-1 — 3rd/5th/7th harmonics only:** Extended IBR spectra (higher harmonics, inter-harmonics) not addressed. Extension: add higher harmonics to regressor matrix.

**L-2 — Regressor orthogonality at non-integer windows:** During fault inception transients the window may be non-integer. Leakage bounded by Dirichlet kernel; negligible for 3rd harmonic at 47 Hz (141 = 3×47 Hz exactly).

**L-3 — Hardware validation absent:** Confidence restoration under real inverter hardware transients (not analytical injection) not tested.

---

## §7 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_harmonic_study.py --seed 2026 --h3-levels 0,0.005,0.01,0.03,0.05,0.08,0.10 --model tr21

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_2_87L_deep/TR21_harmonic_discrimination
pdflatex main_report21 && bibtex main_report21 && pdflatex main_report21 && pdflatex main_report21
```

---

## §8 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report21.tex` read (386 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report21.tex` is authoritative — this file is a read-only analytical summary.*
