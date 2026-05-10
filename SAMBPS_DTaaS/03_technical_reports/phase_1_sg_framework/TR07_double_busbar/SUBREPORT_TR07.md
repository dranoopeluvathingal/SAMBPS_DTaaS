# SUBREPORT_TR07 — Double-Busbar Coordination with Bus-Coupler Check Zone

**TR ID:** TR-07  
**Full title:** Double-Busbar Coordination: Zone-Selective 87B with Bus-Coupler Check Zone  
**Ref:** IITM/EE/PhD/AVE/TR-07/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR07_double_busbar/`  
**Report file:** `main_report7.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework  
**Thesis allocation:** Ch. 5 (Bus/Transformer Differential)  
**Cross-linked TRs:** TR-04 (single-bus 87B), TR-05 (system integration), TR-06 (GOOSE)

---

## §1 Scope

**What TR-07 IS:**
- Extension of SAMBP 87B (TR-04) to double-busbar (DBB) topology with three zones: Zone 1 (BB1), Zone 2 (BB2), Check Zone (supervisory)
- **10/10 scenarios selective** (5 locations × 2 fault types): BB1, BB2, bus-coupler internal, and external faults
- **Proposition (blind spot):** For any fault position α∈(0,1) along the bus coupler, Zone 1 diff = Zone 2 diff = 0, but Check Zone diff = I_f ≠ 0. Formally proven.
- **Zero code changes** to the `sambp_bus_diff` pipeline — three zones achieved by calling existing modules with different feeder arrays
- κ_n = 4.3 unchanged by adding extra feeders (zone model structure unchanged)

**What TR-07 IS NOT:**
- Not covering dynamic feeder transfer (static feeder allocation only)
- Not validated with GOOSE-based zone reconfiguration (deferred)
- Not modelling CT open-circuit on bus coupler (same irreducible limitation as TR-04)

**Core contribution:** Proves that the Check Zone is the only reliable protection for all bus-coupler internal faults regardless of the number of CTs on the coupler, and that the SAMBP 3-parameter zone model is invariant to the number of physical feeders.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-07 |
|---|---|---|
| Blackburn2006 | DBB protection principles | Fixed slope; no model-based check-zone gate |
| TR-04 | Single-bus SAMBP 87B | Not DBB |

**Novelty:** First model-based (κ_n + f_int gated) DBB protection; proves bus-coupler blind-spot analytically and demonstrates zero-code-change extension from single-bus to DBB.

---

## §3 Method

### 3.1 Double-Busbar Topology

Network: Gen → BB1 ↔ [Bus Coupler] ↔ BB2 → Transformer  
Zones:
```
Zone 1: I_diff,Z1 = I_Gen + I_Line + I_BC,BB1  (BB1-side coupler CT)
Zone 2: I_diff,Z2 = I_BC,BB2 + I_Tr             (BB2-side coupler CT)
Check:  I_diff,CK = I_Gen + I_Line + I_Tr        (no coupler CT included)
```

### 3.2 Bus-Coupler Blind Spot Proposition

**Proposition:** For a fault at position α∈(0,1) along the bus coupler:
- Zone 1: I_f − I_f = 0 (BB1-side CT reads full fault current)
- Zone 2: 0 + 0 = 0 (no current reaches BB2 side)
- Check: I_Gen + 0 = I_f ≠ 0

**Proof:** BC CT at BB1 side reads I_f before fault location; Zone 2 has no current source on BB2 side. Check zone excludes BC CT → captures net injection. QED.

This holds for all α∈(0,1) and is independent of whether the coupler has 1 or 2 CTs.

### 3.3 Trip Logic

```
BB1 trip = Z1 ∧ CK         (zone selectivity + check supervision)
BB2 trip = Z2 ∧ CK
BC fault = CK ∧ ¬Z1 ∧ ¬Z2  (check alone, no zone corroboration)
```

### 3.4 SAMBP Stage-2 Integration

Same 3-parameter model `θ_B = [I_diff, φ, ε_CT]` and Stage-2 gate applied independently to each of the three zones. For external faults: all zone differentials → 0, f_int→0, veto fires. For fault cases: f_int≈1.0, κ_n≈4.3.

---

## §4 Implementation

```
04_code/sambp/sambp_bus_diff/       # zero changes from TR-04

03_technical_reports/phase_1_sg_framework/TR07_double_busbar/
├── main_report7.tex
├── references7.bib
└── figures/
    ├── fig_double_bus_topology.pdf
    └── fig_bc_blind_spot.pdf
```

Three-zone implementation: call `run_bus_diff_study()` three times with different feeder arrays [Gen+Line+BC_BB1], [BC_BB2+Tr], [Gen+Line+Tr].

---

## §5 Validation

### 5.1 Selectivity matrix (10/10)

| Scenario | Z1 | Z2 | CK | BB1 | BB2 | BC | Sel |
|---|---|---|---|---|---|---|---|
| BB1/3ph | T | · | T | T | · | · | ✓ |
| BB1/AG | T | · | T | T | · | · | ✓ |
| BB2/3ph | · | T | T | · | T | · | ✓ |
| BB2/AG | · | T | T | · | T | · | ✓ |
| BC/3ph | · | · | T | · | · | T | ✓ |
| BC/AG | · | · | T | · | · | T | ✓ |
| Line ext/3ph | · | · | · | · | · | · | ✓ |
| Line ext/AG | · | · | · | · | · | · | ✓ |
| Load ext/3ph | · | · | · | · | · | · | ✓ |
| Load ext/AG | · | · | · | · | · | · | ✓ |

### 5.2 SAMBP parameters (selected scenarios)

| Scenario | Zone | Trip | κ_n | f_int | I_op |
|---|---|---|---|---|---|
| BB1/3ph | Z1 | ✓ conv | 4.3 | 1.000 | 17.24 |
| BB2/3ph | Z2 | ✓ conv | 4.3 | 1.000 | 15.67 |
| BC/3ph | CK | ✓ conv | 4.3 | 1.000 | 16.42 |
| Ext/3ph | Z1 | ✗ no_trip | 4.3 | 1.000 | 0.00 |

κ_n=4.3 identical to TR-04 single-bus result — adding extra feeders does not affect zone model identifiability.

### 5.3 Comparison with TR-04

| Property | TR-04 (single) | TR-07 (DBB) |
|---|---|---|
| Zones | 1 | 3 (Z1, Z2, CK) |
| κ_n | 4.3 | 4.3 (unchanged) |
| Code changes | — | 0 |
| BC fault coverage | N/A | Check zone |
| Scenarios | 6 | 10 |
| Selectivity | 5/6 | 10/10 |

---

## §6 Results

| Metric | Value |
|---|---|
| Selectivity | 10/10 |
| Bus-coupler fault detection | Check zone (only reliable mechanism) |
| κ_n (all zones) | 4.3 (invariant to feeder count) |
| Code changes to sambp_bus_diff | 0 |
| Stage-2 veto on external faults | Correct (f_int→0 for all zones) |
| Blind spot proposition | Formally proved (all α∈(0,1)) |

---

## §7 Limitations

**L-1 — Static feeder allocation:** Dynamic feeder transfer between buses requires real-time GOOSE/SCADA reconfiguration of zone feeder arrays — not implemented.

**L-2 — No temporal coordination:** Check zone assert window relative to zone relay timing not modelled (lockout logic deferred).

**L-3 — CT open-circuit on BC:** Same irreducible limitation as TR-04; BC CT failure would create false differential in both Z1 and Z2.

**L-4 — No GOOSE zone reconfiguration:** Busbar isolator position GOOSE integration for dynamic reconfiguration deferred.

---

## §8 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_bus_diff
python run_double_bus_study.py  # wraps run_bus_diff_study() for 3 zones

cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR07_double_busbar
pdflatex main_report7 && bibtex main_report7 && pdflatex main_report7 && pdflatex main_report7
```

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report7.tex` read (439 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report7.tex` is authoritative — this file is a read-only analytical summary.*
