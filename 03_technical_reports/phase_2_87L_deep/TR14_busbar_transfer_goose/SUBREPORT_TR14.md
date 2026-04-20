# SUBREPORT_TR14 — Busbar Transfer Engine (GOOSE-Based)

**TR ID:** TR-14  
**Full title:** Busbar Transfer Engine: GOOSE-Subscribed Zone Reconfiguration for 5-Topology Double-Busbar Networks  
**Ref:** IITM/EE/PhD/AVE/TR-14/2026  
**Folder:** `03_technical_reports/phase_2_87L_deep/TR14_busbar_transfer_goose/`  
**Report file:** `main_report14.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 2 — 87L Deep-Dive  
**Thesis allocation:** Ch. 4 (Line Differential Protection) — topology reconfiguration  
**Cross-linked TRs:** TR-06 (IEC 61850 GOOSE baseline), TR-07 (double-busbar 87B), TR-16 (87B/87L coordination)

---

## §1 Scope

**What TR-14 IS:**
- BusbarTransferEngine: subscribes to GOOSE DS_OPEN/DS_CLOSE messages and reconfigures zone-feeder arrays dynamically
- Implements 5 topologies: T1 NORM (normal), T2 TIP (transfer-in-progress), T3 POST (post-transfer complete), T4 SPLIT (bus-coupler open), T5 LAG (GOOSE 5ms delayed)
- Conservative TIP rule: zone frozen until DS_OPEN GOOSE arrives — prevents false differential on external faults during transfer
- stNum guard: prevents duplicate reconfigurations on GOOSE retransmissions
- **40/40 (100%) selective** across all topologies and fault locations
- T5_LAG with 5ms GOOSE delay: still correct because BC CT placement preserves zone indication

**What TR-14 IS NOT:**
- Not a busbar protection function (87B in TR-07)
- Not a differential protection study per se — focuses on topology management
- Not hardware validated

**Core contribution:** Proves that the conservative TIP rule (zone unchanged until GOOSE confirmation) eliminates false differential during transfer operations without sacrificing post-transfer selectivity. Derives stNum guard condition for GOOSE retransmit immunity.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-14 |
|---|---|---|
| TR-06 | GOOSE κ_n/f_int state sharing, 42ms clearance | No topology reconfiguration |
| TR-07 | Double-busbar 87B 3-zone logic | Static topology only |
| IEC 61850-8-1 | GOOSE dataset encoding | No protection reconfiguration protocol |

**Novelty:** First SAMBP zone-reconfiguration engine driven by IEC 61850 GOOSE; conservative TIP rule formally justified; stNum guard prevents duplicate-reconfiguration race condition.

---

## §3 Method

### 3.1 Topology State Machine

```
States: T1_NORM → T2_TIP → T3_POST
        T1_NORM → T4_SPLIT (BC open without transfer)
        Any → T5_LAG (GOOSE delayed)

Transitions:
  DS_CLOSE GOOSE received → T2_TIP (freeze zone, do not reconfigure yet)
  DS_OPEN GOOSE received  → T3_POST (reconfigure zone, clear TIP flag)
  GOOSE timeout           → T5_LAG (use last known topology + 5ms correction)
```

### 3.2 Conservative TIP Rule

```
if topology_state == T2_TIP:
    # DS closing: transfer in progress, old topology still active
    zone_feeder_array = zone_feeder_array_pre_transfer
    # Rationale: feeder CT is on the line, not the bus —
    # zone indication correct regardless of which bus the feeder is on

if topology_state == T3_POST:
    # DS open confirmed: transfer complete
    zone_feeder_array = zone_feeder_array_post_transfer
```

### 3.3 stNum Guard

```python
def on_goose_receive(self, msg):
    if msg.stNum == self._last_stNum:
        return  # retransmission — ignore
    self._last_stNum = msg.stNum
    self._process_topology_change(msg)
```

### 3.4 Test Matrix

5 topologies × 8 fault locations (4 bus + 4 line) = 40 scenarios.

---

## §4 Implementation

```
04_code/sambp/sambp_system/
├── busbar_transfer_engine.py    # topology FSM + GOOSE subscriber
├── transfer_network.py          # 5-topology network builder
└── run_busbar_transfer_study.py # 40-scenario study runner
```

---

## §5 Validation

### 5.1 Per-topology selectivity

| Topology | Fault location | Scenarios | Correct |
|---|---|---|---|
| T1_NORM | bus_A, bus_B, line_AB, line_BC | 8 | 8/8 |
| T2_TIP | bus_A, bus_B, line_AB, line_BC | 8 | 8/8 |
| T3_POST | bus_A, bus_B, line_AB, line_BC | 8 | 8/8 |
| T4_SPLIT | bus_A, bus_B, line_AB, line_BC | 8 | 8/8 |
| T5_LAG | bus_A, bus_B, line_AB, line_BC | 8 | 8/8 |

**Total: 40/40 (100%) selective.**

### 5.2 Conservative TIP rule verification

T2_TIP, external fault (line_BC): zone frozen → no differential in 87L zone for bus_A feeder (feeder CT on line, not bus). Correct: no trip.

T2_TIP, internal fault (bus_A): feeder CT sees fault contribution → I_diff,bus_A ≠ 0 → 87B trips. Correct: trip.

### 5.3 T5_LAG (5ms GOOSE delay)

Zone indication remains correct because BC CT is on the bus coupler — its contribution to the differential is topology-independent for line faults. 5ms lag introduces no misclassification in any of 8 scenarios.

---

## §6 Results

| Metric | Value |
|---|---|
| Selectivity | 40/40 (100%) |
| Topologies tested | 5 (T1 NORM/T2 TIP/T3 POST/T4 SPLIT/T5 LAG) |
| Conservative TIP rule | Zone frozen until DS_OPEN GOOSE — zero false differential |
| stNum guard | Prevents duplicate reconfiguration on GOOSE retransmit |
| T5_LAG 5ms | Correct in all 8 scenarios — BC CT placement independent of topology state |
| GOOSE interaction | Reuses TR-06 retransmit schedule; no additional IED modification |

---

## §7 Limitations

**L-1 — GOOSE loss:** Extended GOOSE absence (>T_max=1s) falls back to last known topology. If topology unknown (cold start), T1_NORM assumed. May be incorrect if topology changed during IED restart.

**L-2 — Multi-transfer:** Simultaneous transfer of two feeders not modelled (TR-19 addresses this).

**L-3 — CT polarity under transfer:** Assumes CT polarity marks are consistent across topologies. CT rewiring during physical busbar work (outside relay scope) not handled.

**L-4 — No hardware validation:** Simulation only; DS timing from IEC 61850 spec; actual DS operating time may differ (TR-67 HIL addresses).

---

## §8 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_busbar_transfer_study.py --seed 2026 --topologies all

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_2_87L_deep/TR14_busbar_transfer_goose
pdflatex main_report14 && bibtex main_report14 && pdflatex main_report14 && pdflatex main_report14
```

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report14.tex` read (480 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report14.tex` is authoritative — this file is a read-only analytical summary.*
