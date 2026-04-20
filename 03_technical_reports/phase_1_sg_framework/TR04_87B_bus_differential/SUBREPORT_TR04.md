# SUBREPORT_TR04 — SAMBP Model-Based Bus Differential Protection (87B)

**TR ID:** TR-04  
**Full title:** SAMBP Model-Based Bus Differential Protection: Extending the Inverse-Estimation Framework to 87B Using a Three-Parameter CT-Distortion Zone Model  
**Ref:** IITM/EE/PhD/AVE/TR-04/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR04_87B_bus_differential/`  
**Report file:** `main_report4.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework  
**Thesis allocation:** Ch. 5 (Bus/Transformer Differential)  
**Cross-linked TRs:** TR-03 (87T/87L foundation), TR-05 (system integration)

---

## §1 Scope

**What TR-04 IS:**
- SAMBP extension to 87B bus differential protection
- 3-parameter zone model `θ_B = [I_diff, φ, ε_CT]` — simplest in the SAMBP suite
- `f_int = clip(1 − ε_CT/ε_thresh, 0, 1)` with `ε_thresh=0.10` — monotone, identifiable, no collinearity
- κ_n ≤ 6.3 (lowest of any SAMBP function) — proven via linear independence of {sin(ωt+φ), cos(ωt+φ), sgn(sin ωt)}
- 5/6 canonical events correct; CT open-circuit documented as irreducible limitation
- Stage-2 model-veto generalisation: shows same gate mechanism resolves primary security challenge across all three differential functions

**What TR-04 IS NOT:**
- Not a high-impedance 87B scheme (low-impedance; CT open-circuit not immune)
- Not validated on double-busbar with coupler CT (deferred to TR-07)
- Not integrated with IEC 61850 GOOSE (deferred to TR-06)

**Core contribution:** Demonstrates that the SAMBP zone model achieves its best κ_n (2–6) for 87B due to the absence of harmonic blocking sources, and characterises CT open-circuit as an irreducible class of mal-trip for any low-impedance differential scheme.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-04 |
|---|---|---|
| Blackburn2006 | 87B protection principles | Fixed slope settings; no identifiability metric |
| IEC60255-87 | Differential relay standard | No physics-derived CT distortion model |
| TR-03 | 87T/87L SAMBP framework | 87B not addressed |

**Novelty:** First application of κ_n-gated model-based protection to 87B; proves 3-parameter identifiability via Fourier orthogonality argument; achieves κ_n=2–6 (best in SAMBP suite).

---

## §3 Method

### 3.1 Operating and Restraint Quantities

```
I_op(t) = |Σ_{k=1}^{N} i_k(t)|    (all feeder currents, signed into bus)
I_rst(t) = ½·Σ_{k=1}^{N} |i_k(t)|

Trip: same dual-slope as 87T (TR-03): SLP1=0.25, SLP2=0.50, I_op^min=0.20, I_rst^(k)=1.0
Unrestrained high-set: 8.0 pu
```

### 3.2 CT Saturation Model

```
i_CT(t) = i_true(t)                           for |i_true| ≤ I_knee
         = I_knee·sgn(i_true) + α·(i_true − I_knee·sgn(i_true))  otherwise

α=0.15 (85% compression above knee); I_knee = 0.6·I_fault
```

### 3.3 Three-Parameter Zone Model

```
î_diff(t; θ_B) = I_diff·sin(ωt+φ) + ε_CT·I_diff·sgn(sin ωt)
θ_B = [I_diff, φ, ε_CT] ∈ [0,10]×[−π,π]×[0,0.5]
```

This is a proper subset of the 87T model (TR-03), dropping k_2 and k_5 (absent for busbar — no inrush/overexcitation source).

**Internal fault indicator:**
```
f_int = clip(1 − ε_CT/ε_thresh, 0, 1),  ε_thresh=0.10
```
When ε_CT≈0: f_int=1 (clean sinusoid → consistent with internal fault).
When ε_CT≥ε_thresh: f_int=0 (CT saturation distortion present → not internal fault).

### 3.4 Identifiability Proposition

**Proposition:** Basis functions {sin(ωt+φ), cos(ωt+φ), sgn(sin ωt)} are linearly independent for any φ∈(−π,π), T≥1/f → rank(J)=3 → κ_n < ∞.

**Proof:** sgn(sin ωt) has Fourier series `(4/π)Σ_{n odd} sin(nωt)/n`. Its projection onto span{sin ωt, cos ωt} is `(4/π)sin ωt`, leaving residual components at n=3,5,... orthogonal to the fundamental subspace. Hence sgn(sin ωt) ∉ span{sin(ωt+φ), cos(ωt+φ)} → all 3 Jacobian columns independent.

### 3.5 Two-Pass LM

Pass 1: All 3 parameters, full window.  
Pass 2: Fix (I_diff, φ); refine ε_CT on tail window (last 2 cycles — steady-state saturation).

### 3.6 Stage-2 Model-Veto Gate

```
Veto fires: κ_n < 30 AND f_int < 0.60
Action: suppress conventional trip
87B primary target: external fault + CT saturation
```

CT open-circuit exception: ε_CT≈0, f_int≈1 → veto does NOT fire → irreducible mal-trip (pure fundamental differential indistinguishable from internal fault without additional info).

---

## §4 Implementation

### Module tree

```
04_code/sambp/sambp_bus_diff/
├── models/
│   ├── bus_diff_baseline.py          # conventional 87B relay
│   ├── bus_event_library.py          # 6 synthetic events
│   └── bus_reduced_zone_model.py     # 3-parameter model
├── inverse_estimation/
│   └── bus_inverse_estimator.py      # two-pass LM
├── adaptation/
│   └── bus_confidence_gate.py        # Stage-2 gate
└── run_bus_diff_study.py             # batch study runner

03_technical_reports/phase_1_sg_framework/TR04_87B_bus_differential/
├── main_report4.tex
├── references4.bib
└── figures/
    ├── fig_87B_characteristic.pdf
    └── fig_87B_system.pdf
```

---

## §5 Validation

### 5.1 Six canonical events

| Event | Conv. | Final | Source | κ_n | f_int | ε_CT |
|---|---|---|---|---|---|---|
| Normal load | ✗ | ✗ | no_trip | 4.4 | 1.00 | 0.000 |
| External fault | ✗ | ✗ | no_trip | 4.3 | 1.00 | 0.000 |
| External+CT sat | ✓ | ✗ | model_veto | 2.7 | 0.00 | 0.265 |
| Internal A-G | ✓ | ✓ | conventional | 4.3 | 1.00 | 0.000 |
| Internal 3-phase | ✓ | ✓ | conventional | 4.3 | 1.00 | 0.000 |
| CT open-circuit* | ✓ | ✓ | model | 4.4 | 1.00 | 0.000 |

*Documented limitation — irreducible in low-impedance scheme.

**5/6 correct (1 documented known limitation). 0 assertion failures.**

### 5.2 κ_n cross-function comparison (updated with 87B)

| Function | p | κ_n range | Threshold |
|---|---|---|---|
| OC (SG) | 6 | 5–20 | 50 |
| 87T | 5 | 4–7 | 30 |
| 87L | 4 | 2–3 | 30 |
| **87B** | **3** | **2–6** | 30 |

### 5.3 Stage-2 veto summary across differential functions

| Function | Veto target | Discriminant |
|---|---|---|
| 87T | External+CT sat | f_int via k_2, k_5, ε_CT |
| 87L | Skew-induced spurious diff | f_int via I_fund/I_DC ratio |
| 87B | External+CT sat | f_int via ε_CT only |

---

## §6 Results

| Metric | Value |
|---|---|
| Canonical events classified | 5/6 (1 documented limitation) |
| Assertion failures | 0 |
| κ_n (all scenarios) | 2.7–4.4 |
| κ_n (best in SAMBP suite) | Yes — 3 parameters vs 4–6 for others |
| CT saturation veto | Correct (f_int=0.00, κ_n=2.7) |
| Internal fault sensitivity | 2/2 correct |
| CT open-circuit | Irreducible mal-trip — low-impedance limitation |
| Pass 1/2 compute overhead | < 60% of 87T (N×3 vs N×5 Jacobian) |

---

## §7 Limitations

**L-1 — CT open-circuit (irreducible):** Clean sinusoidal apparent differential from failed CT indistinguishable from internal fault without CT secondary voltage monitoring. High-impedance 87B scheme required for immunity.

**L-2 — Single bus section:** Double-busbar with bus-coupler CT requires second zone and selector logic — deferred to TR-07.

**L-3 — Low-impedance scheme:** SAMBP 87B is a low-impedance differential scheme; subject to same CT open-circuit vulnerability as all conventional low-impedance 87B relays.

**L-4 — No GOOSE integration:** Hard-wired CT secondary inputs only; merging unit / IEC 61850 GOOSE integration deferred to TR-06.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy.

```bash
cd /root/phd_thesis/04_code/sambp/sambp_bus_diff
python run_bus_diff_study.py

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR04_87B_bus_differential
pdflatex main_report4 && bibtex main_report4 && pdflatex main_report4 && pdflatex main_report4
```

**Key output:** Per-event: `{θ̂, κ_n, f_int, ε_CT, trip_decision, source}`; Stage-2 veto summary.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report4.tex` read (546 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report4.tex` is authoritative — this file is a read-only analytical summary.*
