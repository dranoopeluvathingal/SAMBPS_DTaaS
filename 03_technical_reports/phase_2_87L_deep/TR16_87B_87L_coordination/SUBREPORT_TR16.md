# SUBREPORT_TR16 — 87B/87L Zone Coordination

**TR ID:** TR-16  
**Full title:** 87B/87L Zone Coordination: Non-Conflict Proof and Hybrid Integration (TR-14 Topology + TR-15 87L)  
**Ref:** IITM/EE/PhD/AVE/TR-16/2026  
**Folder:** `03_technical_reports/phase_2_87L_deep/TR16_87B_87L_coordination/`  
**Report file:** `main_report16.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 2 — 87L Deep-Dive  
**Thesis allocation:** Ch. 4 (Line Differential Protection) — multi-zone coordination  
**Cross-linked TRs:** TR-14 (busbar transfer topology), TR-15 (87L Mode 1), TR-07 (double-busbar 87B)

---

## §1 Scope

**What TR-16 IS:**
- Hybrid integration: 87B from TR-14 CSV topology + 87L computed live with TR-15 Config D (Mode 1, voltage-based)
- **Non-conflict analytically proved**: bus fault → i_diff,line=0; line fault → Kirchhoff cancels in bus zone
- **28 scenarios** (4 topologies × 7 fault locations): 28/28 coordinated (100%)
- HIF margin at α=0.05 (ag): Î_fund=0.431 pu = 5.4× above 0.08 pu threshold
- No GOOSE exchange needed between 87B and 87L (physically disjoint zones)
- T4_SPLIT de-energised BB2: no-trip correct in both functions

**What TR-16 IS NOT:**
- Not a new protection function — coordination study of existing TR-14/TR-15 outputs
- Not covering simultaneous bus+line fault (studied in TR-19)
- Not hardware validated

**Core contribution:** Formal non-conflict proof eliminates the possibility of 87B/87L interaction for any fault topology, removing the need for inter-function GOOSE arbitration in the common case.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-16 |
|---|---|---|
| TR-14 | 87B topology-aware (40/40) | No 87L integration |
| TR-15 | 87L voltage-based (Mode 1) | No 87B coordination |
| TR-07 | Double-busbar 87B logic | Static topology |

**Novelty:** Analytical proof of 87B/87L non-conflict; first combined coordination study across 4 topologies; identifies T4_SPLIT de-energised bus as a corner case handled correctly without code changes.

---

## §3 Method

### 3.1 Non-Conflict Proof

**Claim:** For any single fault, 87B and 87L cannot simultaneously produce trip decisions on the same event.

**Bus fault (at bus_A or bus_B):**
```
i_diff,line = i_S,line + i_R,line
            = I_f × (Z_line,R / (Z_line,S + Z_line_R))  [from S]
            + I_f × (Z_line,S / (Z_line_S + Z_line_R))  [from R, opposite sign]
            ≈ 0  (both ends contribute via common path)

More precisely: Kirchhoff's current law at the fault bus →
  I_f = Σ feeder currents  (all from bus side)
  Line CT measures current flowing INTO line from that bus side only
  → i_diff,line = i_S - (-i_R) = 0 for external bus fault
```

**Line fault (at line midpoint):**
```
Bus zone: i_diff,bus = Σ i_feeders (including faulted line)
         = i_healthy_feeders + i_faulted_line
         
KCL at bus: i_healthy_feeders = − i_faulted_line  (no fault current injected at bus)
         → i_diff,bus = 0

Therefore: bus fault → 87B trips, 87L does not; line fault → 87L trips, 87B does not. □
```

### 3.2 Test Matrix

4 topologies (T1, T2, T3, T4) × 7 fault locations (bus_A, bus_B, BC_midpoint, line_1_mid, line_2_mid, line_3_mid, line_4_mid) = 28 scenarios.

### 3.3 HIF Corner Case

α=0.05 (ag) at line_1_mid: I_f,nom × 0.05 = 4.8 × 0.05 = 0.24 pu. After Mode 1 compensation: Î_fund=0.431 pu = 5.4× above I_thresh=0.08 pu. Both 87B (no trip, zero differential) and 87L (trip) behave correctly.

---

## §4 Implementation

```
04_code/sambp/sambp_system/
└── run_coordination_study.py    # hybrid 87B/87L study (TR-14 topology + TR-15 87L)

# No new modules — orchestrates existing TR-14 and TR-15 outputs
```

---

## §5 Validation

### 5.1 Full 28-scenario coordination table

| Topology | Fault location | 87B decision | 87L decision | Coordinated? |
|---|---|---|---|---|
| T1_NORM | bus_A | Trip | No trip | ✓ |
| T1_NORM | bus_B | Trip | No trip | ✓ |
| T1_NORM | line_1_mid | No trip | Trip | ✓ |
| T1_NORM | line_2_mid | No trip | Trip | ✓ |
| T2_TIP | (all 7) | Correct | Correct | 7/7 ✓ |
| T3_POST | (all 7) | Correct | Correct | 7/7 ✓ |
| T4_SPLIT | bus_B (de-energised) | No trip (correct) | No trip (correct) | ✓ |
| T4_SPLIT | bus_A, lines | Correct | Correct | 6/6 ✓ |

**Total: 28/28 (100%) coordinated.**

### 5.2 T4_SPLIT de-energised BB2

BB2 de-energised (all feeders transferred to BB1 via BC): no fault current → i_diff,bus_B=0 (87B no trip), i_diff,line=0 for lines formerly on BB2. Correct: no trip from either function.

### 5.3 GOOSE exchange analysis

87B uses GOOSE for topology reconfiguration (TR-14) and for κ_n/f_int state sharing (TR-06).  
87L uses GOOSE only for state sharing (TR-06).  
**No GOOSE exchange needed between 87B and 87L** — zones are physically disjoint; non-conflict proved analytically.

---

## §6 Results

| Metric | Value |
|---|---|
| Coordination scenarios | 28/28 (100%) |
| Non-conflict proof | Analytical (KCL-based); holds for any single fault |
| HIF margin (α=0.05, ag) | 5.4× above I_thresh (0.431/0.08 pu) |
| T4_SPLIT corner case | Correct no-trip in both functions |
| Inter-function GOOSE | Not required (disjoint zones) |
| Configuration | 87B: TR-14 topology CSV; 87L: TR-15 Config D (Mode 1) |

---

## §7 Limitations

**L-1 — Single fault assumption:** Non-conflict proof holds for single faults. Simultaneous bus + line fault (cross-country) is not covered — studied in TR-19.

**L-2 — Evolving faults:** Fault migrating from line into bus (or vice versa) may produce transient simultaneous signals. Transition handled by state machine timeout (100ms lockout).

**L-3 — T5_LAG not tested:** GOOSE-delayed topology (TR-14 T5_LAG) not included in the 28-scenario matrix. Expected correct based on TR-14 result but not explicitly verified in this study.

**L-4 — No hardware validation:** Simulation only.

---

## §8 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_coordination_study.py --seed 2026 --topologies T1,T2,T3,T4 --faults all

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_2_87L_deep/TR16_87B_87L_coordination
pdflatex main_report16 && bibtex main_report16 && pdflatex main_report16 && pdflatex main_report16
```

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report16.tex` read (425 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report16.tex` is authoritative — this file is a read-only analytical summary.*
