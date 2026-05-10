# SUBREPORT_TR03 — SAMBP Model-Based Differential Protection: 87T and 87L

**TR ID:** TR-03  
**Full title:** SAMBP Model-Based Differential Protection: Transformer 87T and Line 87L Using Inverse Estimation and Confidence Gating  
**Ref:** IITM/EE/PhD/AVE/TR-03/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR03_87T_87L_foundation/`  
**Report file:** `main_report3.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework  
**Target journal:** IEEE Transactions on Power Delivery  
**Thesis allocation:** Ch. 4 (Line Differential) / Ch. 5 (Transformer/Bus Differential)  
**Cross-linked TRs:** TR-01/02 (OC foundation), TR-04 (87B extension), TR-05 (system integration)

---

## §1 Scope

**What TR-03 IS:**
- SAMBP framework for transformer differential (87T) and line differential (87L): five-layer architecture applied to both functions
- **87T:** 5-parameter zone model `θ_T = [I_f, φ, k_2, k_5, ε_CT]`; `f_int` derived from absence of blocking signatures (avoids collinearity); inrush/overexcitation/CT-saturation discrimination; 7/7 canonical events correct
- **87L:** 4-parameter model `θ_L = [I_fund, φ, I_DC, τ_DC]`; DC exponential orthogonal to sinusoid → full-rank Jacobian; three-mode FSM (Healthy/Degraded/Loss) with OC backup in channel-loss; 12/12 scenarios correct
- Proposition: multi-sinusoidal model (≥3 sinusoids at same frequency) has Jacobian rank ≤ 2 — proves DC-based model is necessary

**What TR-03 IS NOT:**
- Not a three-terminal line extension (two-end only)
- Not validated with hardware IEDs (software only; HIL deferred to TR-67)
- Not covering Stage 2 87T CT saturation pre-detector (deferred)

**Core contribution:** Proves that the SAMBP five-layer pattern transfers directly across protection functions; only the zone model, parameter bounds, and fallback logic require function-specific customisation.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-03 |
|---|---|---|
| Blackburn2006 | Differential protection principles | Fixed harmonic thresholds, no uncertainty quantification |
| Wiszniewski2007 | Model-based 87T | No systematic confidence framework |
| Chothani2014 | Adaptive transformer protection | No κ_n-based identifiability gate |
| Anderson1999 | Power system protection | Static settings; no physics-derived inverse estimation |

**Novelty:** First demonstration that a unified reduced-parameter inverse-estimation framework with κ_n gate transfers across 87T and 87L with zero changes to the estimation or confidence layers.

---

## §3 Method

### 3.1 Shared Mathematical Foundations

**Dual-slope percentage-differential characteristic (both 87T and 87L):**
```
I_op = |I_L + I_R|;  I_rst = ½(|I_L| + |I_R|)

Trip: I_op > Γ(I_rst) with:
  Γ = max(I_op^min, SLP1·I_rst)          for I_rst ≤ I_rst^(k)
  Γ = max(I_op^min, SLP1·I_rst^(k) + SLP2·(I_rst − I_rst^(k)))  otherwise
```

**Column-normalised condition number:** `κ_n(J) = σ_max(J_n)/σ_min(J_n)` where `J_n = J·diag(c_j⁻¹)`

**Confidence score:** `c_conf = [1 − (κ_n−1)/(κ_n^max−1)]⁺ × exp(−‖r‖_n)` — combines identifiability and fit quality

### 3.2 87T Zone Model

```
î_diff(t; θ_T) = I_f·sin(ωt+φ) + k_2·I_f·sin(2ωt+φ) + k_5·I_f·sin(5ωt+φ) + ε_CT·I_f·sgn(sin ωt)
θ_T = [I_f, φ, k_2, k_5, ε_CT],  bounds: I_f∈[0,10], φ∈[−π,π], k_2∈[0,1], k_5∈[0,1], ε_CT∈[0,0.5]
```

**Internal fault indicator (derived, not fitted):**
```
f_int = 1 − (k_2/δ_2 + k_5/δ_5 + ε_CT/δ_ε) / (1/δ_2 + 1/δ_5 + 1/δ_ε)
δ_2=0.15, δ_5=0.35, δ_ε=0.10
```
Fitting `f_int` as free parameter causes `κ_n → ∞` when `φ≈0` (collinearity with fundamental term).

**87T settings:** I_op^min=0.20, SLP1=0.25, SLP2=0.60, I_rst^(k)=1.0, I_hs=5.0 pu; blocking: δ_2=0.15, δ_5=0.35, δ_ε=0.10

### 3.3 87L Zone Model

**Proposition (rank deficiency):** Multi-sinusoidal model `Σ A_j·sin(ωt+φ_j)` has Jacobian rank ≤ 2 (all columns in span{sin ωt, cos ωt}) → parameter estimation ill-posed for any window length.

**Four-parameter model:**
```
î_diff(t; θ_L) = I_fund·sin(ωt+φ) + I_DC·exp(−(t−t_0)/τ_DC)
θ_L = [I_fund, φ, I_DC, τ_DC],  I_fund∈[0,10], φ∈[−π,π], I_DC∈[0,5], τ_DC∈[5ms,500ms]
```

**Proposition (orthogonality):** For ωT≫1, T≫τ: `∫₀ᵀ sin(ωt+φ)·e^{−t/τ} dt ≈ 0` → asymptotically orthogonal → κ_n ≪ ∞.

**Three-mode FSM:**
```
Mode A (Healthy):  Full 87L, n_confirm=2
Mode B (Degraded): Full 87L, n_confirm=3, skew compensation via cross-correlation
Mode C (Loss):     Differential suspended; OC backup: I_inst>6 pu or I_rms>2.5 pu

Transitions:
  A→B: skew >2 samples or jitter/loss detected
  B→C: continuous loss >100ms
  C→B, B→A: channel clean for 500ms
```

### 3.4 Two-Pass LM (both functions)

Pass 1: Full window, all parameters free → global shape (I_f/φ for 87T; I_fund/φ for 87L).  
Pass 2: Tail window, fix slowly-varying; refine (k_2, k_5, ε_CT) for 87T or (I_DC, τ_DC) for 87L.  
Compute: O(N·p²), N≈100 samples, p∈{4,5} → **< 2 ms per relay cycle**.

---

## §4 Implementation

### Module tree

```
04_code/sambp/transformer_87t/
├── transformer_diff_baseline.py
├── transformer_reduced_zone_model.py
├── transformer_inverse_estimator.py
├── transformer_confidence_gate.py
└── (harmonic blocking integrated)

04_code/sambp/line_87l/
├── line_diff_baseline.py
├── line_reduced_zone_model.py
├── line_inverse_estimator.py
├── line_confidence_gate.py
└── line_fallback_logic.py

03_technical_reports/phase_1_sg_framework/TR03_87T_87L_foundation/
├── main_report3.tex
├── references3.bib
└── figures/
```

**Key APIs:**  
87T: `run_87T_relay(time, i_H, i_X, cfg)` → `RelayDecision`; `estimate_zone_parameters(t, i_diff, freq)` → `dict`  
87L: `run_87L_relay(time, i_L, i_R, cfg)` → `LineDiffDecision`; `apply_channel(i_R_true, channel_cfg)` → `(i_R_rx, ChannelState)`

---

## §5 Validation

### 5.1 87T — 7 canonical events

| Event | Conv. | Final | Source | κ_n | c_conf | f_int | k_2 |
|---|---|---|---|---|---|---|---|
| Normal load | ✗ | ✗ | no_trip | ∞ | 0.92 | 0.92 | — |
| Inrush | ✓ | ✗ | blocked | ∞ | 0.02 | 0.24 | 0.42 |
| Overexcitation | ✓ | ✗ | blocked | 6.7 | 0.60 | 0.00 | — |
| External+CT sat | ✓ | ✗ | model_veto | 4.9 | 0.17 | 0.45 | — |
| Internal turn-gnd | ✓ | ✓ | conventional | 4.8 | 0.32 | 0.87 | — |
| Internal A-B | ✓ | ✓ | conventional | 4.8 | 0.01 | 0.85 | — |
| Internal 3-phase | ✓ | ✓ | conventional | 4.8 | 0.01 | 0.86 | — |

**7/7 correct. 0 assertion failures.**

### 5.2 87L — 12 scenarios (3 modes × 4 fault types)

All 12 scenarios correctly classified. Key: healthy/external = model_veto (f_int≈0); internal faults = conventional; Loss-mode internal A-G = no_trip (OC backup not triggered, I < I_inst); Loss-mode 3-phase external = OC-inst trip.

### 5.3 κ_n comparison (all SAMBP functions)

| Function | p | Typical κ_n |
|---|---|---|
| OC (SG) | 6 | 5–20 |
| 87T | 5 | 4–7 |
| 87L | 4 | 2–3 |

All below threshold 30.

---

## §6 Results

| Metric | Value |
|---|---|
| 87T event classification | 7/7 correct |
| 87L scenario classification | 12/12 correct |
| 87T κ_n range | 4.8–6.7 |
| 87L κ_n | ~2.5 (all scenarios) |
| Compute per cycle | < 2 ms |
| f_int: external+CT sat (87T) | 0.45 → veto fires |
| f_int: through-current (87L) | 0.00 → veto fires |
| 87L Mode C OC backup | Correct (3-phase external trip only) |

---

## §7 Limitations

**L-1 — 87T CT saturation pre-detector missing:** External fault + CT saturation trips conventional relay; model veto catches it via f_int but ε_CT suppressed by large fundamental. Stage-2 needs waveform asymmetry detector.

**L-2 — 87L Mode B degraded mal-trip:** Residual skew >relay restraint slope causes conventional mal-trip on healthy/external; SAMBP f_int≈0.5 flags uncertainty but Stage-2 not yet wired to withhold Mode-B conventional trip.

**L-3 — Two-terminal 87L only:** Three-terminal line extension (Thévenin superposition, multiple channel paths) not addressed.

**L-4 — No IEC 61850 SV integration:** Synthetic CT model used; real merging-unit sampled-value streams (IEC 9-2LE) deferred.

**L-5 — Software validation only:** HIL on RTDS deferred to TR-67.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy.

```bash
# 87T batch study
cd /root/phd_thesis/04_code/sambp/transformer_87t
python run_87T_study.py

# 87L scenario matrix
cd /root/phd_thesis/04_code/sambp/line_87l
python run_87L_study.py

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR03_87T_87L_foundation
pdflatex main_report3 && bibtex main_report3 && pdflatex main_report3 && pdflatex main_report3
```

**Key output:** Per-event: `{θ̂, κ_n, f_int, c_conf, trip_decision, source}`; selectivity/blocking summary table.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report3.tex` read (915 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report3.tex` is authoritative — this file is a read-only analytical summary.*
