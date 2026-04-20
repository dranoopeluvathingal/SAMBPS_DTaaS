# SUBREPORT_paper_k — A Unified Five-Layer SAMBPS Framework for IBR-Dominated Grids

**Paper ID:** paper_k  
**Full title:** A Unified Five-Layer SAMBPS Framework for IBR-Dominated Grids: Architecture, Coordination, and System-Wide HIL Validation  
**Ref:** IITM/EE/PhD/AVE/paper_k/2026  
**Folder:** `02_papers/paper_k_sambps_unified/`  
**Report file:** `main.tex`  
**Generated:** 2026-04-20  
**Target journal:** IEEE Transactions on Smart Grid  
**Thesis allocation:** Ch. 9 (Centralised / System-Level Protection); cross-ref Ch. 3–8 for individual layers  
**Cross-linked TRs:** TR-01/02 (SyncOC, L3–L4), TR-62 (PV 87L, L2), TR-67 (HIL campaign), TR-56 (DFIG), TR-91 (GNN topology)

---

## §1 Scope

**What paper_k IS:**
- System-integration paper unifying all five SAMBP layers into a single SAMBPS architecture across 9 protection elements (OC, 87T, 87L, 87B, 87G, 87L-PV, 40, 64G, 81)
- Contributions C16–C20: Physics-Reduction Proposition (generalised); Stage-2 veto; sequence backbone; GOOSE 4-rule arbitration; benchmark system-wide validation
- HIL campaign with physical IEDs: SEL-300G + GE D60 + SAMBP Python IED on IEC 61850 Ed2 GOOSE; 62 scenarios, 60/62 = 96.8% agreement
- Characterises 5 system-level failure modes F1–F5 and maps mitigations to SAMBPS layers

**What paper_k IS NOT:**
- Not a layer-by-layer tutorial (that is paper_t — Proceedings IEEE survey)
- Not a single-element deep dive — integration and coordination focus; individual element derivations in TRs
- Not a DSO field study — HIL on RTDS only; field validation is paper_o

**Core contribution:** Proves that independent per-element SAMBP modules, when integrated with GOOSE arbitration and a unified Stage-2 veto, achieve system-level P_D ≥ 0.92 and P_XFA = 0.0000 under full IBR penetration (k_ibr = 1.0).

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. paper_k |
|---|---|---|
| Phadke2009 | Adaptive relaying philosophy | No IBR-specific model reduction |
| Oureilidis2016 | MG protection coordination | Fixed settings; no real-time adaptation |
| Nuhic2018 | IEC 61850 GOOSE for adaptive protection | Single IED; no multi-element arbitration |
| Coffele2015 | Adaptive OC with central controller | Communication-dependent; no local fallback |
| IEEE C37.119 | Adaptive relaying standard | No IBR physics-reduction framework |

**Novelty:** First unified framework integrating physics-derived parameter reduction (C16), Stage-2 veto (C17), sequence backbone (C18), and 4-rule GOOSE arbitration (C19) validated on 9 protection elements across a physical RTDS HIL platform.

---

## §3 Method

### 3.1 Five-Layer Architecture

```
L1: Conventional baseline (IEC/IEEE fixed settings — always active fallback)
L2: Zone model (element-specific physics-reduced model; κ_n characterisation)
L3: LM inverse estimator (two-pass; parameter update each 20ms window)
L4: Confidence gate (γ = Σw_i·s_i; γ_th=0.70; CUEP energy gate)
L5: Arbitration + fallback (GOOSE 4-rule; Stage-2 veto; L1 reversion if veto)
```

### 3.2 Physics-Reduction Proposition (C16 — Generalised)

**Proposition:** A parameter θ_j is reducible if it is either:
- (a) *Collinear* with another parameter in the Jacobian column space (σ_min(J) increases upon elimination), OR
- (b) *Physics-derivable* from remaining parameters via a first-principles constraint (e.g., current continuity, zero-DC of GFL inverter)

**Proof:** SVD interlacing theorem: removing a collinear column increases σ_min; substituting a physics constraint reduces effective DoF by 1 → equivalent to column removal. QED.

**Consequence:** κ_n reduction ≥ 10× in all demonstrated cases; enables real-time L3 estimation.

Zone model κ_n ranges (all < 30 threshold):
| Element | Parameters | κ_n range |
|---|---|---|
| OC (51) | 6 | [8, 21] |
| 87T | 5 | [9, 28] |
| 87L | 4 | [6, 14] |
| 87B | 5 | [10, 23] |
| 87G | 6 | [12, 29] |
| 87L-PV | 2 | [7, 16] |

### 3.3 Stage-2 Veto Gate (C17)

```
Veto condition: κ_n ≥ 30  OR  γ < γ_th  OR  Stage-2 flag (Park dq / full EMT)
Action: freeze L3 update → L1 settings retained → no false adaptation
Results: 0 wrong vetoes, 7/8 CT saturation suppressions, 3/3 channel anomaly catches
```

### 3.4 Sequence Backbone (C18)

```
Asymmetric fault: decompose {i_a, i_b, i_c} → {I_0, I_1, I_2} (symmetrical components)
Estimate on positive-sequence (single phase equivalent → lower DoF)
κ_n improvement: 3×–8× for LL/SLG vs. phase-domain estimation
Δγ = +0.047 mean improvement across asymmetric fault cases
Compute overhead: +3.2 ms (total L3 budget 20ms → 16.8ms for zone model)
```

### 3.5 GOOSE 4-Rule Arbitration (C19)

```
Rule 1: High-set instantaneous element → immediate trip (bypasses L3–L4)
Rule 2: Lowest κ_n element wins (best-conditioned estimate governs)
Rule 3: SPRT-confirmed element (secondary statistical test passed) takes priority
Rule 4: Zone selectivity (most specific protecting element — not upstream backup)

GOOSE dataset: {conv_trip, adapt_trip, κ_n, f_int, seq_type}
Cycle: 20ms estimation → GOOSE publish → P2 class ≤4ms
Measured: mean 2.8ms, P99 3.9ms (RTDS HIL)
```

### 3.6 System-Level Failure Modes F1–F5

| Mode | Description | SAMBPS Mitigation |
|---|---|---|
| F1 | IBR current limiting → κ_n spike → false adapt | Stage-2 veto (C17) |
| F2 | CT saturation → corrupted i(t) | Stage-2 veto catches r spike |
| F3 | Asymmetric fault → wrong phase estimate | Sequence backbone (C18) |
| F4 | GOOSE race condition → conflicting trips | 4-rule arbitration (C19) |
| F5 | Communication loss → adaptation frozen | L1 fallback always active (L5) |

---

## §4 Implementation

### Module tree

```
04_code/sambp/
├── sync_oc/            # TR-01/02 SyncOC — 51 element
├── transformer_87t/    # 87T differential
├── line_87l/           # 87L line differential (including PV model TR-62)
├── busbar_87b/         # 87B busbar differential
├── gen_suite/          # 87G + 40 + 64G + 81
├── integration/
│   ├── goose_arbiter.py        # 4-rule arbitration (C19)
│   ├── stage2_veto.py          # κ_n/γ gate + Park dq flag (C17)
│   ├── sequence_backbone.py    # symmetrical components decomp (C18)
│   └── sambps_coordinator.py   # top-level 20ms cycle runner
└── hil/
    └── sambp_iied_v1.1/        # Python IED (IEC 61850 GOOSE Ed2)

03_technical_reports/
└── (individual TRs per element)

02_papers/paper_k_sambps_unified/
├── main.tex            # This document (691 lines)
├── references.bib
└── figures/
    ├── fig_5layer_architecture.pdf
    ├── fig_failure_modes.pdf
    ├── fig_goose_arbitration.pdf
    ├── fig_hil_platform.pdf
    └── fig_benchmark_results.pdf
```

**Key API:** `sambps_coordinator.run_20ms_cycle(fault_case)` → `{trip_decision, element_id, κ_n, γ, rule_applied}`

---

## §5 Validation

### 5.1 HIL Campaign (62 scenarios)

Platform: RTDS GPC-II + SEL-300G (OC/87G) + GE D60 (87T/87L) + SAMBP Python IED  
Protocol: IEC 61850 Ed2 GOOSE; scenarios: k_ibr ∈ {0, 0.25, 0.50, 0.75, 1.0}; fault types: 3PH/LL/SLG; R_f ∈ {0.01, 0.05, 0.15, 0.50} pu

| Metric | Result | Target |
|---|---|---|
| Overall agreement | 60/62 = **96.8%** | ≥ 95% |
| D1 (Relay 78 SWING_CONFIRM=3cyc) | +23ms delay | Hardware firmware limitation |
| D2 (ROCOF 8ms window) | +22ms lag | Fixed in sambp_iied_v1.1 |
| GOOSE mean latency | 2.8 ms | ≤ 4ms (P2) |
| GOOSE P99 latency | 3.9 ms | ≤ 4ms (P2) |
| Corridor test | 10/10 | — |

### 5.2 Monte Carlo Benchmark (C20)

8,000 trials; IEEE 39-bus model; k_ibr swept [0, 1.0]; 9 protection elements

| Metric | Value | Condition |
|---|---|---|
| P_D (min across 9 elements) | **0.92** | k_ibr = 1.0 |
| P_FA | 0.0000 | All k_ibr |
| P_XFA (N-1 cross-element false alarm) | **0.0000** | 18 element pairs, 8,000 MC |
| Selectivity (correct element trips) | 99.1% | — |

### 5.3 Coordination Cases A/B/C

| Case | Topology | k_ibr | Elements | Result |
|---|---|---|---|---|
| A | Radial feeder | 0.75 | 51 + 87L | Correct selectivity, grading maintained |
| B | Meshed MG | 1.00 | 87B + 87T + 51 | 4-rule arbitration Rule 2 applied; correct |
| C | N-1 contingency | 0.50 | 87L-PV + 87G | L1 fallback activated; no false trip |

---

## §6 Results

| Metric | Value |
|---|---|
| Elements validated | 9 (OC, 87T, 87L, 87B, 87G, 87L-PV, 40, 64G, 81) |
| κ_n (all elements) | < 30 (Stage-2 veto threshold) |
| P_D (k_ibr=1.0, worst element) | 0.92 |
| P_XFA (N-1, 18 pairs) | 0.0000 |
| HIL agreement | 96.8% (60/62) |
| GOOSE P99 latency | 3.9 ms |
| Wrong vetoes | 0 |
| CT sat suppressions | 7/8 |
| Channel anomaly catches | 3/3 |
| Physics-Reduction: κ_n reduction | ≥ 10× all elements |
| Sequence backbone Δγ | +0.047 mean |

---

## §7 Limitations

**L-1 — Firmware-limited Relay 78:** SEL-300G SWING_CONFIRM=3 cyc introduces +23ms; cannot be changed without firmware upgrade. SAMBPS coordination unaffected but trip time budget tight for fast fault clearing.

**L-2 — 9-element scope:** 9 elements cover standard protection suite; non-standard elements (e.g., inter-area oscillation damping control relays) not addressed.

**L-3 — RTDS HIL only:** Field validation deferred to paper_o. RTDS model fidelity validated against real recordings but direct hardware-in-field test not performed.

**L-4 — GOOSE P99 3.9ms measured on RTDS network:** Real substation network timing may differ; IEC 61850 Ed2 P2 class specification ≤4ms is the binding requirement.

**L-5 — MC on IEEE 39-bus only:** Single reference system; generalisation to other transmission topologies not proven; ongoing in TR-91 (GNN topology-aware).

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy, pycomtrade, pyiec61850; RTDS access for HIL.

```bash
# Monte Carlo benchmark (no HIL required)
cd /root/phd_thesis/04_code/sambp/integration
python sambps_coordinator.py --mode mc --trials 8000 --system ieee39

# Run coordination cases A/B/C
python sambps_coordinator.py --case A
python sambps_coordinator.py --case B
python sambps_coordinator.py --case C

# Compile paper
cd /root/phd_thesis/02_papers/paper_k_sambps_unified
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

**Key output:** per-trial `{element, trip_decision, κ_n, γ, rule_applied}`; aggregate P_D, P_FA, P_XFA; per-scenario HIL agreement log.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main.tex` read (691 lines). Manuscript not modified. De-dup confirmed: paper_k (IEEE TSG journal, C16–C20) is distinct from paper_t (Proceedings IEEE tutorial, C1–C16). |

---

*Sub-report generated by SAMBP archivist pipeline. `main.tex` is authoritative — this file is a read-only analytical summary.*
