# SUBREPORT_paper_t — Self-Adaptive Model-Based Protection: A Unified Five-Layer Framework (Tutorial/Survey)

**Paper ID:** paper_t  
**Full title:** Self-Adaptive Model-Based Protection for IBR-Penetrated Networks: A Unified Five-Layer Framework  
**Ref:** IITM/EE/PhD/AVE/paper_t/2026  
**Folder:** `02_papers/paper_t_sambps_unified/`  
**Report file:** `main.tex`  
**Generated:** 2026-04-20  
**Target venue:** Proceedings of the IEEE (tutorial/survey)  
**Thesis allocation:** Ch. 2 (IBR Modelling background) + Ch. 9 (Centralised/System Protection) — comprehensive survey role  
**Cross-linked TRs:** All SAMBP TRs (TR-01 through TR-91); paper_k (system-integration companion); paper_a/paper_b (source journal papers for C1–C5)

---

## §1 Scope

**What paper_t IS:**
- A **comprehensive layer-by-layer tutorial and survey** of the full SAMBPS framework: C1–C16
- Design principles P1 (physics first), P2 (conservative by default), P3 (stability before speed)
- Formal theorems: UUB adaptive slope (C1); CUEP conservativeness + monotonicity (C13); κ_n cascade decay analysis; veto necessity corollary
- κ_n as the system integrator — simultaneously gates L3, L4, L5 — proved mutually consistent in Appendix
- Multi-hardware validation: SEL-411L relay hardware (96.1%, 120 scenarios) + DSO field recordings (95.5%, 157 recordings)
- VSM model (C10): 9-state Virtual Synchronous Machine — extends estimation window 150ms → 380ms
- Wide-area GOOSE consensus (C14): weighted voting p_trip = Σw_i·v_i / Σw_i; robust to N_SS ≥ 3 nodes

**What paper_t IS NOT:**
- Not a contribution paper (individual novel contributions are in paper_k, paper_a, paper_b, TRs)
- Not a system-integration HIL campaign (that is paper_k — IEEE TSG journal with SEL-300G/GE D60/RTDS/62 scenarios)
- Not a narrow single-element treatment — comprehensive survey across full five-layer stack

**Core purpose:** Provide a definitive reference for the complete SAMBPS design rationale, theoretical guarantees, and validation evidence, accessible to protection engineers not specialised in inverse estimation or IBR modelling.

---

## §2 State of the Art

| Ref | Contribution | Gap addressed by paper_t |
|---|---|---|
| Phadke2009 | Adaptive relaying philosophy | No formal stability/UUB guarantee |
| Kundur1994 | Power system stability (Park model) | Not applied to relay adaptation |
| IEEE C37.119 | Adaptive relaying standard | No physics-reduction or κ_n framework |
| Guerrero2011 | IBR control survey | Not connected to protection adaptation |
| Brahma2004 | Adaptive OC for DG feeders | No confidence gate, no Stage-2 veto |

**Novelty (survey contribution):** First unified theoretical treatment proving that κ_n < 30 is simultaneously necessary and sufficient for safe operation of all five SAMBPS layers, with multi-site field validation across 157 real DSO recordings.

---

## §3 Method

### 3.1 Design Principles

```
P1 (Physics first):      Physics-derived constraints reduce κ_n before numerical optimisation
P2 (Conservative):       γ < γ_th → freeze adaptation → L1 settings; safety before performance
P3 (Stability before speed): UUB proved before deployment; no speed-accuracy trade-off unlocked
                             until stability criterion satisfied
```

### 3.2 κ_n as System Integrator

κ_n simultaneously controls three independent safety mechanisms:

```
L3 (adaptive law):  Update accepted ↔ κ_n < 30  [rate-limit + hard clip also active]
L4 (CUEP gate):     Energy bound V_cuep ≤ V_cr checked only when κ_n < 30
L5 (trip veto):     K(κ_n) ≠ ∅  ↔  κ_n < 30  [veto necessity corollary]

Proved mutually consistent (Appendix): all three gates use same threshold → no
internal conflict; κ_n is single sufficient statistic for layer activation.
```

**κ_n cascade decay:**
```
At fault inception: κ_n ~ 50 (transient parameters ill-conditioned)
Decay time constant: ~17 ms
Below threshold 30 at: ~35 ms (before any standard relay decision at ≥80ms)
```

### 3.3 UUB Theorem (C1)

**Statement:** For the bounded adaptive update law `I_p(k+1) = clip(I_p(k) + K(κ_n)·e_I(k), [I_min, I_max])`, the tracking error `e_I = I_p* − I_p` is uniformly ultimately bounded: `‖e_I(k)‖ ≤ δ_UUB` for all k ≥ k_0, where `δ_UUB = δ_I·(1 + ‖K‖)` and `δ_I` is the rate-limit.

**Proof sketch:** Rate-limit δ_I bounds single-step error; hard clip bounds cumulative error; monotone non-decreasing argument extends to infinite horizon. UUB (not asymptotic stability) is the correct guarantee class for bounded disturbances.

### 3.4 CUEP Conservativeness and Monotonicity Theorems (C13)

```
Conservativeness: V_cuep(k_ibr) ≤ V_cr(k_ibr) for all k_ibr ∈ [0, 1]
  → SAMBPS never declares stable when marginally unstable
  → Zero violations: 1500-scenario IEEE 39-bus validation

Monotonicity: ∂V_cr/∂k_ibr ≤ 0
  → Higher IBR penetration → smaller stability margin → more conservative gate
  → Proved via IBR current-limiting effect on post-fault deceleration area

CCT margin: 12–28 ms conservative margin (measured vs. time-domain simulation)
Zero violations: k_ibr ≤ 0.55 (all scenarios)
```

### 3.5 VSM Model Extension (C10 / G6)

```
9-state Virtual Synchronous Machine: [δ, ω, E'q, E'd, E''q, E''d, E_fd, T_m, V_pss]
Extends estimation window: 150ms → 380ms
Proposition: κ_n < 30 for t ≤ 380ms, k_ibr ≤ 0.60
  Proof: Park dq ODE solution bounded → well-conditioned Jacobian beyond subtransient window
Validation G6: 97.9% agreement (VSM scenarios)
```

### 3.6 Wide-Area GOOSE Consensus (C14)

```
Weighted vote: p_trip = Σ_{i=1}^{N} w_i·v_i / Σ w_i
  v_i ∈ {0, 1} (node i trip vote); w_i = 1/κ_n,i (lower κ_n = higher weight)
Threshold: p_trip ≥ p_th = 0.60

Robustness: N_SS ≥ 3 nodes required; Byzantine fault tolerance N_f ≤ ⌊(N−1)/3⌋
Measured G4 (WAPC): 95.8% correct consensus decisions
```

### 3.7 Layer-by-Layer Exposition (C1–C16 summary)

| C# | Layer | Topic |
|---|---|---|
| C1–C5 | L3 | Inverse estimation: LM, two-pass, UUB, parameter reduction |
| C6–C9 | L4 | Confidence gate: γ score, κ_n threshold, CUEP energy bound |
| C10 | L2/L3 | VSM 9-state model for extended window |
| C11–C12 | L2 | PV/DFIG zone models; DDR selector |
| C13 | L4 | CUEP monotonicity + conservativeness theorems |
| C14 | L5 | Wide-area GOOSE consensus; weighted voting |
| C15–C16 | L5 | Stage-2 veto; fallback coordination; F1–F5 failure modes |

---

## §4 Implementation

### Module tree

```
04_code/sambp/
├── (all element modules — same tree as paper_k)
└── integration/
    ├── goose_consensus.py      # wide-area weighted voting (C14)
    └── vsm_model.py            # 9-state VSM ODE (C10)

02_papers/paper_t_sambps_unified/
├── main.tex                    # This document (773 lines)
├── references.bib
└── figures/
    ├── fig_5layer_overview.pdf
    ├── fig_kappa_cascade.pdf
    ├── fig_uub_proof.pdf
    ├── fig_cuep_margin.pdf
    ├── fig_vsm_window.pdf
    ├── fig_goose_consensus.pdf
    └── fig_field_validation.pdf
```

**Design principle cross-reference table** (main.tex Table I): maps each C# to P1/P2/P3 and layer; serves as reader navigation guide.

---

## §5 Validation

### 5.1 SEL-411L Hardware (G1)

Platform: SEL-411L distance/differential relay; 120 fault scenarios; SAMBPS Python IED connected via DNP3

| Metric | Value |
|---|---|
| Agreement with SAMBPS | **96.1%** (115/120) |
| Discrepancies | 5 (4 × firmware timing, 1 × CT ratio mismatch) |
| k_ibr range tested | 0–1.0 |

### 5.2 DSO Field Recordings (G7)

Source: 157 real fault recordings from DSO partner; mixed topology (radial + meshed); k_ibr inferred from SCADA

| Metric | Value |
|---|---|
| Correct SAMBPS decisions | **95.5%** (150/157) |
| False operations | 0 |
| Missed trips | 7 (all high-impedance R_f > 1.0 pu — beyond HIF extension scope) |

### 5.3 Wide-Area Consensus (G4)

```
WAPC test: 8-node test network; N_f ∈ {0, 1, 2}; 200 trials
Correct consensus: 95.8%
Degraded with N_f=2: 91.2% (above p_th=0.60 threshold)
```

### 5.4 IEEE 39-Bus CUEP Validation (C13)

```
1500 scenarios; k_ibr ∈ [0, 1.0]; N-1 contingencies
Zero violations V_cuep > V_cr across all 1500 scenarios
CCT margin: 12–28 ms (conservative vs. time-domain Runge-Kutta reference)
```

### 5.5 VSM Extension Validation (G6)

```
97.9% correct adaptation decisions for t_window ∈ [150ms, 380ms]
κ_n < 30 maintained throughout extended window for k_ibr ≤ 0.60
```

---

## §6 Results

| Metric | Value |
|---|---|
| SEL-411L HW agreement | 96.1% (120 scenarios) |
| DSO field agreement | 95.5% (157 recordings) |
| False operations (field) | 0 |
| WAPC consensus accuracy | 95.8% |
| VSM extended-window accuracy | 97.9% |
| CUEP violations (1500 scenarios) | 0 |
| CCT margin | 12–28 ms (conservative) |
| κ_n cascade: below 30 at | ~35 ms |
| UUB bound | δ_UUB = δ_I·(1 + ‖K‖) |
| Design principles | P1 + P2 + P3 all satisfied |

---

## §7 Limitations

**L-1 — Survey scope vs. contribution depth:** Contributions C1–C16 are individually less deep than their source papers (paper_a/b/k, TRs). Cross-references are essential for full derivations.

**L-2 — VSM at k_ibr > 0.60:** κ_n < 30 guarantee for VSM window only proved for k_ibr ≤ 0.60. High-IBR penetration beyond this requires GNN topology adaptation (TR-91).

**L-3 — DSO field data scope:** 157 recordings from a single DSO partner; geographic and grid-type diversity not captured. Multi-DSO study deferred to paper_o.

**L-4 — Consensus robustness at N_f = 2:** 91.2% (below G1/G7 benchmarks). Increasing p_th or N improves robustness at cost of latency.

**L-5 — Proceedings page limit:** Tutorial paper; some derivations abbreviated — full proofs in Appendix or source TRs.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy; COMTRADE reader for DSO field data.

```bash
# κ_n cascade simulation
cd /root/phd_thesis/04_code/sambp/integration
python vsm_model.py --demo cascade

# CUEP validation (IEEE 39-bus)
python sambps_coordinator.py --mode cuep_validation --scenarios 1500

# Wide-area consensus demo
python goose_consensus.py --nodes 8 --nf 1 --trials 200

# Compile paper
cd /root/phd_thesis/02_papers/paper_t_sambps_unified
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

**Key output:** κ_n(t) decay curve; CUEP violation count; consensus accuracy vs. N_f table; field validation confusion matrix.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main.tex` read (773 lines). Manuscript not modified. De-dup confirmed: paper_t (Proceedings IEEE tutorial, C1–C16, SEL-411L + DSO field) is distinct from paper_k (IEEE TSG journal, C16–C20, SEL-300G/GE D60/RTDS HIL). Slug collision `sambps_unified` is naming-only — content is complementary. Recommend folder rename: paper_k → `paper_k_sambps_system`; paper_t → `paper_t_sambps_survey`. |

---

*Sub-report generated by SAMBP archivist pipeline. `main.tex` is authoritative — this file is a read-only analytical summary.*
