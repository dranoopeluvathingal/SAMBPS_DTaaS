# SUBREPORT_paper_c — Self-Adaptive Model-Based Protection: Unified SAMBP Framework

**Paper ID:** paper_c  
**Folder:** `02_papers/paper_c_unified_sambp/`  
**Manuscript:** `main_paper_c.tex` (IEEE journal format, IEEEtran)  
**Target journal:** IEEE Transactions on Power Systems  
**Generated:** 2026-04-20  
**Authors:** Anoop V. Eluvathingal, K. Shanti Swarup (IIT Madras / SGCRL)  
**Thesis role:** Unifying architecture paper — cross-references Papers A and B, TRs 56/57/58/62/64/65  
**Cross-linked TRs:** TR-56 (DFIG 87L), TR-57/TR-64 (Bayesian SPRT 87T), TR-58 (Relay 78), TR-62 (PV 87L), TR-65 (Gen suite); Papers A, B

---

## §1 Scope

**What paper_c IS:**
- The **unifying SAMBP architecture paper** — presents the five-layer framework applied uniformly across all four Phase-1 SG protection functions: OC (SyncOC), 87T, 87L, 87B
- A **Physics-Reduction Proposition** with proof sketch: deriving one collinear/physics-derivable parameter reduces `κ_n` by at least one order of magnitude across all four functions
- A **generalised Stage-2 model veto** (Eq. 1: `κ_n < 30 AND f_int < f_thresh`) that handles CT saturation (87T, 87B) and channel anomaly (87L) as a single identifiability condition — no function-specific hard-coding
- **Cross-function quantitative comparison** across 28 scenarios (3 OC, 7 87T, 12 87L, 6 87B): 26/28 correct; 2 known architectural boundaries
- A **Phase-2 IBR extension roadmap** (5 new zone models: TR-56/57-64/58/62/65) targeting ≥62 scenarios in the 2027 revision
- **HIL validation roadmap** (RTDS, 2026 Q4 Phase-1; DFIG+PV emulators 2027 Phase-2)

**What paper_c IS NOT:**
- Not a paper with new simulation results for OC/87T/87L/87B — those results come from Papers A, B and from the TRs; paper_c synthesises and compares them
- Not the IBR-extension paper — Phase-2 results (TR-56 DFIG, TR-64 IBR 87T, TR-62 PV) are summarised as a roadmap table, not validated here
- Not a standalone read — explicitly cites Papers A and B (`EluvathingalPaperA`, `EluvathingalPaperB`) and assumes familiarity with the two-pass LM estimator and confidence gate

**Significance:** paper_c is the highest-level SAMBP paper, bridging the PhD thesis narrative from individual TR results to a unified, certifiable framework claim. The Physics-Reduction Proposition (Proposition 1) is the single most important theoretical contribution of the SAMBP programme.

---

## §2 State of the Art

Key references bounding novelty (from `references_c.bib`):

| Ref | Authors | Approach | Limitation vs. paper_c |
|---|---|---|---|
| Blackburn2006 | Protective Relaying | Fixed-setting relay design | No online estimation; no unified framework |
| Anderson1999 | Power system protection | Static relay characteristics | Offline only |
| Brahma2004 | Topology-adaptive OC | DG-aware pickup update | OC only; topology enumeration, not estimation |
| Saleh2017 | Microgrid N-1 coordination | Optimisation-based | Static relay characteristics; not real-time |
| Sachdev1988 | RLS relay measurements | Recursive least-squares | No physics constraint; Jacobian ill-conditioning |
| Kasztenny2003 | 87T CT saturation | Harmonic-blocking improvement | Function-specific; no generalised veto |
| Schweitzer2009 | 87B CT saturation | High-impedance detection | Function-specific; supplementary scheme |
| Adamiak2006 | 87L channel anomaly | Communication-assisted 87L | Function-specific mitigation |
| Sheikhzadeh2022, Gao2023 | ML adaptive relays | DNN/GNN classifiers | No physics interpretability; no IEC 60255 path |

**Novelty:** First paper to apply a single estimation-based architecture uniformly across all four major protection functions with a formally proven parameter-reduction principle and a generalised veto mechanism.

---

## §3 Method

### 3.1 Five-layer SAMBP architecture

| Layer | Name | Role | Scope |
|---|---|---|---|
| L1 | Conventional baseline | Independent relay; `conv_trip` is necessary condition for model trip | Function-specific |
| L2 | Reduced-parameter zone model | Physics-constrained model; one parameter derived not fitted | Function-specific |
| L3 | Two-pass LM estimator | Shared backend; Pass 1 full window all params; Pass 2 tail window fast params | **Common to all 4** |
| L4 | Composite confidence gate + model veto | `γ ≥ 0.70` gates adaptation; veto suppresses `conv_trip` when `κ_n < 30 AND f_int < f_thresh` | **Common to all 4** |
| L5 | Fallback / coordination | Function-specific safe behaviour when `γ < 0.70` | Function-specific |

**Key invariant:** The model can only trip when the conventional relay has already asserted. The model veto is the only path to *suppress* a conventional trip.

### 3.2 Four zone models (Phase 1 — SG networks)

| Function | Zone model | Free params `p` | Derived parameter | `κ_n` range | Unconstrained `κ_n` |
|---|---|---|---|---|---|
| SyncOC (OC) | 6-param SG fault current | 6 | `I_dc = −I_sub·sin(φ_a)` (DC from AC at fault inception) | 4.5–21 | ~2×10⁸ |
| Transformer (87T) | 5-param harmonic differential | 5 | `f_int = 1 − max(k₂/k₂_th, k₅/k₅_th)` (collinear with `I_diff` at φ≈0) | 4.8–6.7 | ~10⁴–10⁵ |
| Line diff. (87L) | 4-param fund. + DC | 4 | `f_int = max(I_fund, I_DC)/I_thresh` (3 sinusoids at same freq. are rank-2) | 2.45 | ~10³–10⁴ |
| Busbar (87B) | 3-param fund. + CT error | 3 | `f_int = 1 − ε_CT/0.10` (no transformer harmonics, k₂/k₅ absent) | 2.7–4.4 | ~10³ |

All four constrained models satisfy `κ_n < 30` in all 28 Phase-1 scenarios.

### 3.3 Physics-Reduction Proposition (Proposition 1)

> Let `θ ∈ ℝᵖ` be the parameter vector of a zone model `î(θ, t)`, and let `θ_k = g(θ_{-k})` be an exact relation derivable from network physics. Then the column-normalised Jacobian of the constrained model satisfies `κ_n(J_{p-1}) ≪ κ_n(J_p)`. Empirically, the reduction exceeds one order of magnitude in all four SAMBP functions.

**Proof sketch:** The unconstrained `J_p` has column `∂î/∂θ_k` expressible as a linear combination of remaining columns (chain rule on `g`) → rank deficiency → `κ_n → ∞` numerically. Substituting the constraint removes this column, restoring full column rank and eliminating the degenerate singular value.

**Corollary:** For any new protection zone model, first check whether any parameter is derivable via KVL/KCL, transformer turn-ratio, or Fortescue identity. If so, that parameter **must be derived, not fitted**.

### 3.4 Generalised Stage-2 model veto

```
Veto fires if:  κ_n < κ_thresh = 30  AND  f_int < f_thresh
```
- `f_thresh = 0.60` for 87T and 87B (CT saturation)
- `f_thresh = 0.50` for 87L (channel anomaly — tighter because channel-induced differential is weaker)
- OC has no veto path (model only gates adaptation, never suppresses trip)

Veto fires in 3/28 scenarios — one each in 87T, 87L, 87B — all correctly identifying CT saturation or channel degradation. Zero false suppressions of genuine internal faults.

---

## §4 Implementation

### Module tree (Phase-1 scope)

```
04_code/sambp/
├── sync_oc/                    # SyncOC M1–M4 (Papers A, B)
├── transformer_87t/            # 87T five-parameter model + SPRT (TR-57/64)
├── line_diff/                  # 87L four-parameter + channel FSM + π-section
└── busbar_87b/                 # 87B three-parameter + CT error

02_papers/paper_c_unified_sambp/figures/
├── fig_architecture.pdf        # Five-layer 4-column stack (TikZ source in fig_architecture.tex)
├── fig_kappa_comparison.pdf    # κ_n distribution across 28 scenarios (gen_kappa_comparison.py)
├── 87T_characteristic.png      # 87T dual-slope char + 7-event overlay
├── 87B_characteristic.png      # 87B char + 6-event overlay
├── fig_87L_fsm.pdf             # 87L 3-mode FSM + 12-scenario matrix (TikZ in fig_87L_fsm.tex)
├── fig_hil_roadmap.pdf         # Phase-1/2 HIL roadmap (TikZ in fig_hil_roadmap.tex)
└── fig_pickup_stacking.pdf     # (shared with paper_b — from paper_b cascade)
```

---

## §5 Validation

### 5.1 SyncOC (3 scenarios, from Papers A and B)

| Case | γ | Result |
|---|---|---|
| 3PH fault | 0.89–0.93 | Adapt accepted; pickup/TMS recalibrated |
| SLG fault | 0.914 | Adapt accepted; pickup −8.3% |
| LL fault | 0.587 | Gate rejects; fixed settings retained |

### 5.2 Transformer 87T (7 events, all correct)

| Event | `κ_n` | `f_int` | `γ` | Result |
|---|---|---|---|---|
| Normal load | 4.97 | 0.917 | 0.919 | no_trip ✓ |
| Inrush | 5.16 | 0.239 | 0.024 | blocked ✓ |
| Overexcitation | 6.74 | 0.000 | 0.603 | blocked ✓ |
| **Ext. + CT sat.** | **4.95** | **0.454** | **0.170** | **model_veto ✓** |
| Int. A-G | 4.83 | 0.865 | 0.323 | conv. trip ✓ |
| Int. A-B | 4.83 | 0.847 | 0.011 | conv. trip ✓ |
| Int. 3PH | 4.83 | 0.860 | 0.008 | conv. trip ✓ |

Critical result: model veto correctly suppresses CT saturation false trip (κ_n = 4.95, f_int = 0.454 < 0.60).

### 5.3 Line differential 87L (12 scenarios, 11/12 + 1 expected-none)

- All healthy- and degraded-channel scenarios: 8/8 correct
- Loss-channel external + 3PH faults (single-end OC backup): 2/2 correct
- Loss-channel AG internal fault: no-trip by design (expected-none — channel loss removes differential information)
- Key metric: `κ_n = 2.45` for all scenarios — lowest in the SAMBP suite (strong orthogonality between DC and sinusoidal components in 4-parameter model)
- π-section charging compensation (TR-13): mean charging residual reduced 1.43 pu → 9.4×10⁻⁴ pu; α₅₀ reduced 0.07 → 0.05 pu
- Voltage-based correction (TR-15): α₅₀ further reduced to 0.03 (AG) and 0.02 (3PH)

### 5.4 Busbar differential 87B (6 events, 5/6 + 1 architectural boundary)

| Event | `κ_n` | `f_int` | `γ` | Result |
|---|---|---|---|---|
| Normal load | 4.36 | 1.000 | 0.000 | no_trip ✓ |
| External fault | 4.27 | 1.000 | 0.000 | no_trip ✓ |
| **Ext. + CT sat.** | **2.73** | **0.000** | **0.024** | **model_veto ✓** |
| Internal A-G | 4.27 | 1.000 | 0.137 | conv. trip ✓ |
| Internal 3PH | 4.27 | 1.000 | 0.137 | conv. trip ✓ |
| CT open-circuit | 4.36 | 1.000 | 0.845 | model trip ✗† |

† Architectural boundary — see §7 L-3.

---

## §6 Results

**Cross-function summary table:**

| Function | Scenarios | Correct | κ_n range | Compute |
|---|---|---|---|---|
| SyncOC (OC) | 3 | 3/3 | 4.5–21 | ≤ 18 ms |
| 87T | 7 | 7/7 | 4.8–6.7 | ≤ 12 ms |
| 87L | 12 | 11/12 + 1 exp.-none | 2.45 | ≤ 8 ms |
| 87B | 6 | 5/6 + 1 arch. boundary | 2.7–4.4 | ≤ 6 ms |
| **Total** | **28** | **26/28** | **2.45–21** | **< 20 ms all** |

**Model veto summary:**

| Function | Veto fires? | κ_n | f_int | Cause |
|---|---|---|---|---|
| SyncOC | No | — | — | No veto path in OC |
| 87T | Yes | 4.95 | 0.45 | Ext. fault + CT sat. |
| 87L | Yes | 2.45 | 0.00 | Degraded channel |
| 87B | Yes | 2.73 | 0.00 | Ext. fault + CT sat. |

Zero false suppressions of genuine internal faults across all 28 scenarios.

**Phase-2 IBR extension (roadmap, not yet validated):**

| Zone model | TR | Params | κ_n | Target scenarios |
|---|---|---|---|---|
| DFIG 87L/87G | TR-56 | 10 | 13–68 | 10 |
| Bayesian SPRT 87T | TR-57/TR-64 | 5 + 3 hyp. | 5–7 | 12 |
| IBR-corrected Relay 78 | TR-58 | 4 | — | 10 |
| Solar PV 87L | TR-62 | 2 | 1.00 | 8 |
| Generator suite 40/64G/78/81/87G | TR-65 | — | — | 22 |
| **Phase-2 total** | | | | **≥ 62** |

---

## §7 Limitations

**L-1 — SyncOC LL fault estimation:** γ = 0.587 < 0.70; gate rejects; fixed settings retained safely. Root cause: negative-sequence contamination in Hilbert–Fortescue decomposition. Fix in companion paper `EluvathingalSeqEstim`. (Inherited from paper_b.)

**L-2 — 87L channel-loss internal fault (expected-none):** Single-end OC backup cannot definitively distinguish internal from external without remote measurements. This is the designed-in safe failure mode, not a numerical deficiency.

**L-3 — 87B CT open-circuit (architectural boundary):** `ε_CT ≈ 0` gives `f_int = 1`; veto cannot fire; model issues trip. The 3-parameter zone model cannot distinguish CT open-circuit from a genuine high-impedance internal fault. A supplementary hi-Z detection scheme is required. Known boundary consistent with practice [Schweitzer2009].

**L-4 — Phase-2 IBR results pending:** Table 5 (IBR zone models) lists design targets and TR self-test κ_n values, not full simulation validation. Full validation deferred to the 2027 revision of paper_c.

**L-5 — HIL not yet complete:** As of April 2026, RTDS hardware is planned (mid-2026 Q3); HIL experiments across Phase-1 functions targeted for 2026 Q4. Current validation is software-only.

**L-6 — ML comparison is qualitative:** The comparison with ML-based approaches [Sheikhzadeh2022, Gao2023] is qualitative (interpretability, certification path). No direct head-to-head accuracy comparison on a common dataset is provided.

---

## §8 Reproduction Recipe

```bash
# Run all four Phase-1 functions and collect cross-function comparison
# (individual function runners — see Papers A/B and TRs for per-function commands)
cd /root/phd_thesis/04_code/sambp/sync_oc
python run_milestone2.py --fault_types 3PH SLG LL --n_generators 1

cd /root/phd_thesis/04_code/sambp/transformer_87t
python run_87t_study.py --events all

cd /root/phd_thesis/04_code/sambp/line_diff
python run_87l_study.py --scenarios all --channel_modes healthy degraded loss

cd /root/phd_thesis/04_code/sambp/busbar_87b
python run_87b_study.py --events all

# Generate κ_n comparison figure
cd /root/phd_thesis/02_papers/paper_c_unified_sambp/figures
python gen_kappa_comparison.py

# Compile paper
cd /root/phd_thesis/02_papers/paper_c_unified_sambp
pdflatex main_paper_c && bibtex main_paper_c && \
    pdflatex main_paper_c && pdflatex main_paper_c
```

**Key figures shipped with manuscript:**

| File | Description |
|---|---|
| `fig_architecture.pdf` | Five-layer 4-column SAMBP stack (TikZ) |
| `fig_kappa_comparison.pdf` | κ_n across 28 scenarios by function; κ_thresh=30 dashed |
| `87T_characteristic.png` | 87T dual-slope char + 7-event overlay |
| `87B_characteristic.png` | 87B char + 6-event overlay |
| `fig_87L_fsm.pdf` | 87L 3-mode FSM + 12-scenario matrix (TikZ) |
| `fig_hil_roadmap.pdf` | Phase-1/2 HIL validation roadmap (TikZ) |

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_paper_c.tex` read (892 lines) + `references_c.bib` + figures inventory. Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_paper_c.tex` is authoritative — this file is a read-only analytical summary. Do not edit `main_paper_c.tex` via this file.*
