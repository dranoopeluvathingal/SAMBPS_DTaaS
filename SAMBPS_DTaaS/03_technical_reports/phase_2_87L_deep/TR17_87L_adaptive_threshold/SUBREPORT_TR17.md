# SUBREPORT_TR17 — 87L Adaptive Restraint Threshold

**TR ID:** TR-17  
**Full title:** Adaptive 87L Line Differential Threshold as a Function of Restraint Current I_rest  
**Ref:** IITM/EE/PhD/AVE/TR-17/2026  
**Folder:** `03_technical_reports/phase_2_87L_deep/TR17_87L_adaptive_threshold/`  
**Report file:** `main_report17.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 2 — 87L Deep-Dive  
**Thesis allocation:** Ch. 4 (Line Differential Protection) — load-adaptive security  
**Cross-linked TRs:** TR-15 (fixed threshold baseline), TR-16 (coordination — 28/28 preserved), TR-20 (frequency-adaptive, references TR-17 adaptive threshold)

---

## §1 Scope

**What TR-17 IS:**
- Adaptive threshold law: I_thresh(I_rest) = max(I_base, k_slope × I_rest)
- I_base = 0.08 pu (TR-15 no-load threshold); k_slope = 0.15 pu/pu
- Breakpoint: I_rest = I_base/k_slope = 0.08/0.15 = 0.53 pu
- **Constant 30× security margin** at all load levels (vs 4× for fixed threshold at I_rest=4 pu)
- **TR-15 HIF sensitivity fully preserved** at low load (I_rest ≤ 0.53 pu): α50(ag)=0.030 unchanged
- **28/28 coordination scenarios correct**: at fault inception I_rest→0, threshold collapses to I_base=0.08 pu
- Heavy-load no-fault security: 3 scenarios at 1.0/2.0/4.0 pu confirmed no spurious trip

**What TR-17 IS NOT:**
- Not a new forward model — threshold scaling only
- Not addressing off-nominal frequency (TR-20)
- Not hardware validated

**Core contribution:** Derives k_slope=0.15 from the IEC 60255-187-1 minimum margin criterion M_min=30: k_slope/ε_CT = 0.15/0.005 = 30. Proves that the threshold automatically restores to I_base at fault inception (I_rest→0), preserving full HIF sensitivity.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-17 |
|---|---|---|
| TR-15 | Fixed I_thresh=0.08 pu | Security margin degrades 16→4× as load increases |
| IEC 60255-187-1 | Percentage differential relay standards | No model-based adaptive threshold framework |

**Novelty:** First load-adaptive threshold for SAMBP 87L; derives slope from CT class specification; proves at-fault-inception restoration property.

---

## §3 Method

### 3.1 Adaptive Law

```
I_thresh(I_rest) = max(I_base, k_slope × I_rest)
                 = max(0.08,  0.15    × I_rest)   [pu]

Security margin (slope region):
  M = I_thresh / (ε_CT × I_rest) = k_slope / ε_CT = 0.15/0.005 = 30

Breakpoint: I_rest = I_base/k_slope = 0.08/0.15 = 0.53 pu
```

### 3.2 DC Threshold Coupling

```
I_DC,thresh = 0.60 × I_thresh(I_rest)
```
Preserves TR-15 I_DC/I_fund ratio across all load levels.

### 3.3 Restraint Current Estimation

```
I_rest = (|Î_S| + |Î_R|) / 2
```
Estimated from half-cycle (10ms) pre-fault window. At fault inception, through-current collapses → I_rest→0 within one half-cycle → threshold reverts to I_base=0.08 pu.

---

## §4 Implementation

Two call sites in the 87L pipeline modified:
1. `estimate_line_zone_parameters()` — passes adaptive I_fund_fault_thresh
2. `compute_f_int()` — uses same adaptive threshold for f_int normalisation

No changes to LM estimator, confidence gate, or trip logic.

---

## §5 Validation

### 5.1 Threshold characteristic

| I_rest (pu) | I_thresh (pu) | CT error (pu) | Margin | Region |
|---|---|---|---|---|
| 0.00 | 0.080 | 0.000 | ∞ | base floor |
| 0.53 | 0.080 | 0.003 | 30× | breakpoint |
| 1.00 | 0.150 | 0.005 | 30× | slope |
| 2.00 | 0.300 | 0.010 | 30× | slope |
| 4.00 | 0.600 | 0.020 | 30× | slope |

Fixed threshold at I_rest=4 pu: margin = 0.08/0.020 = 4× (inadequate).

### 5.2 α50 vs I_rest (ag fault, I_LINE,ag=4.667 pu)

| I_rest (pu) | I_thresh (pu) | α50(ag) | Remarks |
|---|---|---|---|
| 0.0 | 0.080 | 0.030 | TR-15 unchanged |
| 0.5 | 0.080 | 0.030 | below breakpoint |
| 1.0 | 0.150 | 0.056 | rated load |
| 2.0 | 0.300 | 0.113 | heavy load |
| 4.0 | 0.600 | 0.225 | extreme overload |

Physical: at I_rest=4 pu, a HIF α=0.05 produces differential ≈0.133 pu < 0.60 pu threshold — correctly withheld.

### 5.3 Coordination and security

- 28/28 coordination scenarios (TR-16 matrix): all correct (threshold=I_base at fault inception)
- HIF (α=0.05 ag): Î_fund=0.432 pu, f_int=1.00 — 5.4× margin above 0.08 pu
- LOAD_1.0/2.0/4.0: no spurious trip; margins 30× confirmed

---

## §6 Results

| Metric | Value |
|---|---|
| Adaptive law | I_thresh = max(0.08, 0.15 × I_rest) pu |
| Security margin | 30× constant (slope region) |
| Breakpoint | I_rest = 0.53 pu |
| α50(ag) at I_rest=0 | 0.030 (TR-15 unchanged) |
| Coordination (28 scenarios) | 28/28 correct |
| Heavy-load no-fault | 3/3 correct (1.0/2.0/4.0 pu) |
| GOOSE dependency | None — operates on local CT measurements only |

---

## §7 Limitations

**L-1 — α50 degrades with load:** At I_rest=1 pu, α50(ag) rises to 0.056 — a genuine physical limitation (HIF at high load is below the CT-mismatch floor). Accepted: correct withholding of ambiguous detections.

**L-2 — k_slope assumes CT class 0.5:** For CT class 0.1, k_slope could be reduced to 0.03, enabling better HIF sensitivity at load. For CT class 1.0, k_slope should be raised to 0.30.

**L-3 — Half-cycle I_rest latency:** At fault inception there is a 10ms transition before I_rest updates. During this window, threshold may momentarily be slightly elevated. Negligible for protection (20ms operating time).

---

## §8 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_hif_study.py --seed 2026 --n-trials 200 --model tr17 --adaptive-threshold

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_2_87L_deep/TR17_87L_adaptive_threshold
pdflatex main_report17 && bibtex main_report17 && pdflatex main_report17 && pdflatex main_report17
```

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report17.tex` read (370 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report17.tex` is authoritative — this file is a read-only analytical summary.*
