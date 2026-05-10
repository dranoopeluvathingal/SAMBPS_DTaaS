# SUBREPORT_TR19 — Simultaneous Multi-Feeder Transfer Coordination

**TR ID:** TR-19  
**Full title:** Simultaneous Multi-Feeder Busbar Transfer: 87B Selectivity and GOOSE Coordination During Dual-Feeder Tip-Switch Operations  
**Ref:** IITM/EE/PhD/AVE/TR-19/2026  
**Folder:** `03_technical_reports/phase_2_87L_deep/TR19_simultaneous_transfer/`  
**Report file:** `main_report19.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 2 — 87L Deep-Dive  
**Thesis allocation:** Ch. 4 (Line Differential Protection) — multi-feeder transfer  
**Cross-linked TRs:** TR-14 (single-feeder transfer baseline), TR-16 (87B/87L coordination)

---

## §1 Scope

**What TR-19 IS:**
- Simultaneous dual-feeder busbar transfer: Gen + Line both transferring BB1→BB2 via tip-switch
- 5 GOOSE states (S0_NORM, S1_STALE, S1a_GEN_OK, S1b_LINE_OK, S2_BOTH_OK)
- **50/50 scenarios correct (100%)**: 5 states × 5 fault locations × 2 fault types
- **Zone 2 minimum margin: 45× above pickup** even in fully stale S1_STALE state
- **Vulnerability window: ≤ 8ms** (worst case, 2-hop IEC 61850-8-1 network)
- **Z2 floor is independent of N**: BC-path current is the minimum regardless of how many feeders are simultaneously transferring

**What TR-19 IS NOT:**
- Not covering unequal tip splits (assumed 50/50 make-before-break)
- Not covering GOOSE out-of-order delivery
- Not hardware validated

**Core contribution:** Proves that Zone 2's minimum differential during simultaneous transfer is the BC-path current (50% of I_Gen at 50/50 split), which is invariant to the number of simultaneously transferring feeders N. For this study network, the margin is 45×.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-19 |
|---|---|---|
| TR-14 | Single-feeder conservative TIP rule, 40/40 selective | One feeder only |
| IEC 61850-8-1 | GOOSE retransmit spec | No protection coordination analysis |

**Novelty:** First multi-feeder simultaneous transfer analysis for model-based bus differential; derives BC-floor independence theorem; quantifies vulnerability window for N feeders.

---

## §3 Method

### 3.1 GOOSE State Machine (5 states)

| State | Description | Gen zone | Line zone |
|---|---|---|---|
| S0_NORM | Both on BB1 pre-transfer | Z1 (full) | Z1 (full) |
| S1_STALE | Both DS closed; both GOOSE in flight | Z1 (stale) | Z1 (stale) |
| S1a_GEN_OK | Gen GOOSE received; Line stale | 0.5/Z1+0.5/Z2 | Z1 (stale) |
| S1b_LINE_OK | Line GOOSE received; Gen stale | Z1 (stale) | 0.5/Z1+0.5/Z2 |
| S2_BOTH_OK | Both GOOSE received | Z2 (full) | Z2 (full) |

### 3.2 GOOSE Timing

Vulnerability window for N feeders:
```
ΔT_max = (N−1) × T_lag,max = (N−1) × 8ms
N=2: ΔT=8ms << 20ms (one protection cycle)
```

### 3.3 Zone 2 Differential During S1_STALE

For BB2 fault:
```
I_Gen,via_BC = I_Gen,total × 0.50 = 4.55 pu  (BB1-path via BC)
|ΔI_Z2| = I_BC,Z2 = 4.55 pu
Margin = 4.55/0.10 = 45×  (vs pickup 0.10 pu)
```

BC-path current is independent of N — the floor never falls below 4.55 pu regardless of how many feeders are in TIP.

---

## §4 Validation

### 4.1 Zone 2 differential by GOOSE state (BB2 3-phase fault)

| State | |ΔI_Z2| (pu) | Margin | Trip | Correct |
|---|---|---|---|---|
| S0_NORM | 4.545 | 45× | BB2 | ✓ |
| S1_STALE | 4.545 | 45× | BB2 | ✓ |
| S1a_GEN_OK | 6.818 | 68× | BB2 | ✓ |
| S1b_LINE_OK | 4.545 | 45× | BB2 | ✓ |
| S2_BOTH_OK | 9.091 | 91× | BB2 | ✓ |

### 4.2 N-feeder vulnerability window generalisation

| N feeders | ΔT_worst (ms) | |ΔI_Z2| min (pu) | Margin | BB2 trip |
|---|---|---|---|---|
| 1 | 0 | 4.545 | 45× | ✓ |
| 2 | 8 | 4.545 | 45× | ✓ |
| 3 | 16 | 4.545 | 45× | ✓ |
| 4 | 24 | 4.545 | 45× | ✓ |
| 5 | 32 | 4.545 | 45× | ✓ |

Z2 floor is BC-path current (50% of I_Gen) — independent of N.

### 4.3 Full selectivity

**50/50 scenarios correct (100%).**

- BB1 fault in S1_STALE: Zone 1 receives full I_Gen (conservative rule keeps Gen in Z1) → 10.00 pu, unaffected
- BC_internal fault in S2_BOTH_OK: CK differential detects correctly (consistent with TR-14 T3_POST)
- 87L and 21 operate independently of GOOSE state in all scenarios

---

## §5 Results

| Metric | Value |
|---|---|
| Selectivity | 50/50 (100%) |
| Zone 2 minimum margin (S1_STALE) | 45× (4.545 pu vs 0.10 pu pickup) |
| BC-floor independence | Proved: Z2 min = I_Gen × 0.50, independent of N |
| Vulnerability window (N=2) | 8ms (negligible vs 20ms protection time) |
| 87L/21 GOOSE independence | Confirmed: both functions unaffected by GOOSE state |

---

## §6 Limitations

**L-1 — 50/50 tip split assumed:** Non-50/50 splits generalise to Z2 floor = I_Gen × min_i(s_i); lower split fractions reduce the Z2 floor.

**L-2 — GOOSE out-of-order:** Message n+1 arriving before message n not tested. stNum guard (TR-14) expected to handle correctly.

**L-3 — Simultaneous bus+line fault not covered:** The non-conflict proof (TR-16) applies to single faults only.

**L-4 — No hardware validation:** Simulation only.

---

## §7 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_busbar_transfer_study.py --seed 2026 --simultaneous --topologies all --goose-states all

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_2_87L_deep/TR19_simultaneous_transfer
pdflatex main_report19 && bibtex main_report19 && pdflatex main_report19 && pdflatex main_report19
```

---

## §8 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report19.tex` read (344 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report19.tex` is authoritative — this file is a read-only analytical summary.*
