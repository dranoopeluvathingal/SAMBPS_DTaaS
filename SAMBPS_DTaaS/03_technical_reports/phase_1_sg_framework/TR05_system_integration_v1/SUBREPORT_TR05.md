# SUBREPORT_TR05 — SAMBP System Integration Study v1

**TR ID:** TR-05  
**Full title:** System Integration Study: Coordinated Operation of Four Differential Protection Functions  
**Ref:** IITM/EE/PhD/AVE/TR-05/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR05_system_integration_v1/`  
**Report file:** `main_report5.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework  
**Thesis allocation:** Ch. 9 (Centralised / System-Level Protection) — v1 integration baseline  
**Cross-linked TRs:** TR-01 (OC), TR-02 (OC extended), TR-03 (87T/87L), TR-04 (87B), TR-06 (GOOSE)

---

## §1 Scope

**What TR-05 IS:**
- System-level selectivity validation of all four SAMBP functions running concurrently on a radial test network
- 10 fault scenarios (5 locations × 2 fault types: 3PH and AG); all five relays (OC, 87B_A, 87L, 87B_B, 87T) evaluated simultaneously
- **10/10 scenarios selective** — 100% sensitivity and specificity for all four differential relays
- Identifies that Stage-2 model-veto provides selectivity benefit unavailable from conventional relays alone in three specific scenarios (87L through-current, 87T Yd11 external, 87L/87B zero-differential)
- Namespace isolation technique for loading multiple Python `models/` packages in the system coordinator

**What TR-05 IS NOT:**
- Not a meshed or multi-infeed topology study (radial only)
- Not CT saturation under through-faults (individual TR validation only)
- Not GOOSE integrated (deferred to TR-06)
- Not hardware validated (software only)

**Core contribution:** First system-level demonstration that SAMBP five-layer architecture achieves perfect selectivity (10/10) across four simultaneous differential protection functions on a common test network with zero cross-zone interactions.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-05 |
|---|---|---|
| Oureilidis2016 | MG protection coordination | Fixed settings; no model-based gate |
| IEEE C37.119 | Adaptive relaying standard | No cross-zone selectivity framework |
| TR-01 to TR-04 | Individual function validation | No concurrent system-level study |

**Novelty:** System-level proof that κ_n < 30 and f_int thresholds, tuned individually per function (TR-01–04), remain mutually consistent and produce correct selectivity when all four functions operate concurrently.

---

## §3 Method

### 3.1 Test Network

Radial topology: Gen → Bus A → Line → Bus B → Transformer → Bus C  
Base: 100 MVA, 33 kV

| Component | Impedance (pu) |
|---|---|
| Source (SG subtransient) | j0.10 |
| Line | j0.05 |
| Transformer (YNd11) | j0.08 |
| Load | 2.00 (≈50% loading) |

### 3.2 Fault Scenarios

| ID | Location | Owning Zone | I_f,3ph (pu) | I_f,AG (pu) |
|---|---|---|---|---|
| F1 | Bus A | 87B_A | 10.0 | 6.0 |
| F2 | Line midpoint | 87L | 6.67 | 4.0 |
| F3 | Bus B | 87B_B | 5.71 | 3.43 |
| F4 | Transformer HV | 87T | 5.71 | 3.43 |
| F5 | Bus C (external) | none | 4.35 | 2.61 |

CT waveform: `i(t) = I_peak·[sin(ωt+φ_k) + k_DC·e^{−t/τ_DC}]`, k_DC=0.8, τ_DC=50ms

### 3.3 SAMBP Pipeline (all 5 relays)

```
L1: CT waveforms (1 kHz, 50 Hz)
L2: Conventional percentage-differential with fixed thresholds
L3: Two-pass LM zone-model estimator (function-specific θ, 2–5 params)
L4: κ_n + f_int extraction
L5: Stage-2 confidence gate (κ_n < κ* AND f_int < f*)
```

Zone model summary:
| Function | θ components | f_int definition | κ* | f* |
|---|---|---|---|---|
| 87OC | [I_fund, k_3, k_5] | I_1/(I_1+k_3+k_5) | 50 | — |
| 87T | [I_f, φ, k_2, k_5, ε_HV] | I_1/(Σ|k_n|) | 30 | 0.60 |
| 87L | [I_diff, φ, δ_s] | I_1/(I_1+|δ_s|) | 30 | 0.60 |
| 87B | [I_diff, φ, ε_CT] | clip(1−ε_CT/0.10, 0, 1) | 30 | 0.60 |

### 3.4 Namespace Isolation

Loading 4 SAMBP Python projects with identical `models/` sub-packages requires:
1. Clear `models.*` from `sys.modules` before each project load
2. Prepend project root to `sys.path`
3. Execute module (creates direct object refs via `from models.X import Y`)
4. Rename cached `models.*` to `{proj}.models.*` to free namespace

Direct object references are unaffected by cache key renaming — all loaded objects remain valid.

---

## §4 Implementation

```
04_code/sambp/integration/
└── system_coordinator.py      # loads all 4 SAMBP projects, runs concurrent evaluation

03_technical_reports/phase_1_sg_framework/TR05_system_integration_v1/
├── main_report5.tex
├── references5.bib
└── figures/
    ├── fig_system_topology.pdf
    ├── fig_sambp_pipeline.pdf
    └── fig_selectivity_matrix.pdf
```

---

## §5 Validation

### 5.1 Selectivity matrix (10/10 selective)

| Scenario | OC | 87B_A | 87L | 87B_B | 87T | Selective |
|---|---|---|---|---|---|---|
| Bus A / 3ph | T | T | · | · | · | ✓ |
| Bus A / AG | T | T | · | · | · | ✓ |
| Line mid / 3ph | T | · | T | · | · | ✓ |
| Line mid / AG | T | · | T | · | · | ✓ |
| Bus B / 3ph | T | · | · | T | · | ✓ |
| Bus B / AG | T | · | · | T | · | ✓ |
| Tr HV / 3ph | T | · | · | · | T | ✓ |
| Tr HV / AG | T | · | · | · | T | ✓ |
| Bus C / 3ph | T | · | · | · | · | ✓ |
| Bus C / AG | T | · | · | · | · | ✓ |

### 5.2 Per-relay scores

| Relay | TP | FP | FN | Sensitivity | Specificity |
|---|---|---|---|---|---|
| OC | 10 | 0 | 0 | 1.000 | — |
| 87B_A | 2 | 0 | 0 | 1.000 | 1.000 |
| 87L | 2 | 0 | 0 | 1.000 | 1.000 |
| 87B_B | 2 | 0 | 0 | 1.000 | 1.000 |
| 87T | 2 | 0 | 0 | 1.000 | 1.000 |

### 5.3 Stage-2 veto selectivity benefits (3 scenarios)

1. **87L through-current (F1,F3,F4,F5):** Zero differential → f_int=0, κ_n=2.5 → veto suppresses any transient imbalance trip. Conventional relay alone would be vulnerable to CT remanence / channel delay artefacts.
2. **87T external fault + Yd11:** Delta winding zeros balanced DC from LV line currents → I_op=0; veto provides additional security layer.
3. **87L/87B zero-differential:** f_int acts as continuous "how sinusoidal?" measure → robust immunity to noise-induced transient imbalance.

### 5.4 κ_n consistency

All κ_n values consistent with individual TR validation:
- 87B_A/B: κ_n≈4.3; 87L: κ_n≈2.5; 87T: κ_n≈4.9 — all < 30.

---

## §6 Results

| Metric | Value |
|---|---|
| Selectivity | 10/10 |
| Sensitivity (all differential relays) | 1.000 |
| Specificity (all differential relays) | 1.000 |
| Cross-zone false trips | 0 |
| κ_n consistency with individual TRs | Confirmed |
| Stage-2 veto correct restraints | 4 (87L F1,F3,F4,F5 through-current) |
| Namespace isolation | Successful — no Python module conflicts |

---

## §7 Limitations

**L-1 — Simplified radial network:** No load flow, no distributed line parameters, no travelling waves, no multi-infeed meshed topology.

**L-2 — No inter-relay GOOSE:** Each relay runs independently on same waveform snapshot; GOOSE zone-state sharing deferred to TR-06.

**L-3 — Single bus section:** Double-busbar with coupler CT deferred to TR-07.

**L-4 — Simplified detection time:** Relay operates instantaneously (no DFT filter delay). Realistic +20ms (1-cycle DFT) not modelled → hardware-in-loop study required.

**L-5 — No CT saturation under through-faults at system level:** Individual TR validation covers this; system-level CT saturation interaction not studied.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy; all four SAMBP project directories present.

```bash
cd /root/phd_thesis/04_code/sambp/integration
python system_coordinator.py --all-scenarios

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR05_system_integration_v1
pdflatex main_report5 && bibtex main_report5 && pdflatex main_report5 && pdflatex main_report5
```

**Key output:** `selectivity_matrix.csv`; per-relay sensitivity/specificity; κ_n and f_int at trip/restrain decision; Stage-2 veto log.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report5.tex` read (526 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report5.tex` is authoritative — this file is a read-only analytical summary.*
