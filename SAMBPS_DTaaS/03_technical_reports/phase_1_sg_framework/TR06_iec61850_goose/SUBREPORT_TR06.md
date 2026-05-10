# SUBREPORT_TR06 — IEC 61850 GOOSE Integration for SAMBP

**TR ID:** TR-06  
**Full title:** IEC 61850 GOOSE Integration: Zone-State Messaging for SAMBP Protection Functions  
**Ref:** IITM/EE/PhD/AVE/TR-06/2026  
**Folder:** `03_technical_reports/phase_1_sg_framework/TR06_iec61850_goose/`  
**Report file:** `main_report6.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 1 — SG Framework  
**Thesis allocation:** Ch. 9 (Centralised / System-Level Protection) — GOOSE comms layer  
**Cross-linked TRs:** TR-05 (system integration), TR-07 (double-busbar), TR-67 (HIL with real GOOSE)

---

## §1 Scope

**What TR-06 IS:**
- IEC 61850-8-1 GOOSE integration into the SAMBP five-relay system (OC, 87T, 87L, 87B_A, 87B_B)
- Two GOOSE functions: (1) trip acceleration / zone intertripping; (2) SAMBP state sharing (κ_n, f_int, source)
- Discrete-time simulation (1ms steps) of IEC 61850-8-1 retransmission timing, LAN latency, packet loss
- **Total clearance: 42ms** (0ms detect + 1ms IED + 1ms net + 40ms CB); GOOSE overhead = 2ms (5% of total)
- **10/10 scenarios selective** (inherited from TR-05, verified with GOOSE enabled)
- 1% packet loss: zero impact on clearance (first retransmit at 2ms recovers lost frame)
- WAN 5ms deployment: 46ms clearance → compliant with IEC 60255 Class P1 (100ms)

**What TR-06 IS NOT:**
- Not an ASN.1/BER PDU implementation (timing and state semantics only; full encoding needs pyiec61850)
- Not process-bus Sampled Values (station-bus GOOSE only; IEC 61850-9-2 SV deferred)
- Not main-1/main-2 dual IED topology (single relay per zone)

**Core contribution:** Demonstrates that GOOSE overhead (2ms) is negligible relative to CB operating time (40ms), and that `κ_n` and `f_int` shared via GOOSE enable cross-zone selectivity confirmation without modifying any individual relay logic.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-06 |
|---|---|---|
| IEC 61850-8-1 | GOOSE standard | No protection-state payload specification |
| Nuhic2018 | GOOSE for adaptive protection | Single IED; no κ_n/f_int sharing |
| TR-05 | System selectivity (no GOOSE) | No inter-relay communication |

**Novelty:** First definition of SAMBP GOOSE dataset including κ_n and f_int as protection-quality fields; cross-zone selectivity confirmation via κ_n/f_int exchange without modifying individual relay logic.

---

## §3 Method

### 3.1 GOOSE Retransmission Model

```
IEC 61850-8-1 Annex B retransmit schedule on state change:
T_i = min(2^i · T_1, T_max),  T_1=2ms, T_max=1000ms
Schedule: [2, 4, 8, 16, 32, 64, 128, 256, 512, 1000, 1000, ...] ms
```

State change detected by subscriber comparing `state_num` with last value (robust to out-of-order delivery via `sq_num`).

### 3.2 Network Model (GooseBroker)

```
Base latency τ_net:   1.0ms nominal (switch forwarding + propagation)
Jitter:               Gaussian N(0, σ_j=0.3ms) per frame
Packet loss:          Bernoulli(p_loss); nominal 0%, worst-case 1%
Queue:                min-heap sorted by arrival time; delivered at correct tick
```

### 3.3 SAMBP GOOSE Dataset

```
SambpGooseData fields:
  relay_id           str    — IED identifier
  final_trip         bool   — SAMBP final trip decision
  conv_trip          bool   — conventional element operated
  source             str    — conventional / model_veto / model
  kappa_n            float  — column-normalised condition number
  f_int              float  — integrity index
  I_op_peak          float  — peak operate current [pu]
  model_veto_active  bool   — Stage-2 veto fired
  t_detect_ms        float  — detection time from fault [ms]
```

Published on state change (trip or restore); heartbeat at T_max=1000ms.

### 3.4 Inter-IED Topology

Physical adjacency on radial network: OC ↔ 87B_A ↔ 87L ↔ 87B_B ↔ 87T  
Forward GOOSE: trip acceleration (upstream trip → downstream can skip confirmation).  
Reverse GOOSE: confirmation (downstream f_int > 0.6 → upstream reduces n_confirm).

### 3.5 Cross-Zone Confirmation Protocol

```
Example: Bus B 3ph fault
  87B_B publishes: f_int=1.0, κ_n=4.3, final_trip=True
  87L receives: f_int^{87B_B} > 0.6 → confirms fault on Bus B side
    → 87L: no trip needed (veto already correct; reduce n_confirm requirement)
    → 87B_B: can reduce n_confirm from 2→1, accelerate trip by 1ms
```

### 3.6 Clearance Budget

```
t_clear = t_detect + t_IED + τ_net + t_CB
        = 0ms     + 1ms    + 1ms   + 40ms  = 42ms

GOOSE overhead (t_IED + τ_net) = 2ms = 5% of total
Circuit breaker dominates
```

---

## §4 Implementation

```
04_code/sambp/integration/
├── goose_broker.py         # network simulation, min-heap queue
├── goose_publisher.py      # state_num, sq_num, retransmit schedule
├── goose_subscriber.py     # state change detection
├── sambp_goose_dataset.py  # SambpGooseData dataclass
└── goose_coordinator.py    # 5-IED topology, cross-zone protocol

03_technical_reports/phase_1_sg_framework/TR06_iec61850_goose/
├── main_report6.tex
├── references6.bib
└── figures/
    ├── fig_goose_retransmit.pdf
    ├── fig_goose_topology.pdf
    └── fig_goose_timing.pdf
```

**Publisher state machine:** `state_num` (logical state changes) + `sq_num` (all transmissions) + `retransmit_cnt` (index into schedule; resets on state change).

---

## §5 Validation

### 5.1 Clearance time — nominal LAN

All 10 scenarios: t_detect=0ms, t_GOOSE=1ms, t_clear=42ms (uniform). OC detection dominates all scenarios.

### 5.2 Latency sensitivity sweep

| Configuration | τ_net | p_loss | t_clear | Δt |
|---|---|---|---|---|
| LAN 0.5ms/0% | 0.5ms | 0% | 41.5ms | −0.5ms |
| LAN 1.0ms/0% (nominal) | 1.0ms | 0% | 42.0ms | — |
| LAN 2.0ms/0% | 2.0ms | 0% | 43.0ms | +1.0ms |
| WAN 5.0ms/0% | 5.0ms | 0% | 46.0ms | +4.0ms |
| LAN 1.0ms/1% | 1.0ms | 1% | 42.0ms | 0ms |

LAN→WAN (0.5→5ms) changes clearance by only 4.5ms (10.7%). 1% loss: zero impact (2ms retransmit recovers in time).

### 5.3 GOOSE event statistics (Bus A / 3ph, 200ms simulation)

| Event type | Count |
|---|---|
| TRIP publications | 2 (OC + 87B_A) |
| IDLE publications | 5 |
| RX_TRIP receptions | 8 |
| RX_IDLE receptions | 29 |
| Total | 44 |

### 5.4 Selectivity with GOOSE enabled

**10/10 scenarios selective** (identical to TR-05; GOOSE adds no false trips or missed trips).

---

## §6 Results

| Metric | Value |
|---|---|
| GOOSE overhead | 2ms (1ms IED + 1ms LAN) |
| Total clearance (nominal) | 42ms |
| CB dominance | 95% of clearance budget |
| 1% packet loss impact | 0ms |
| WAN 5ms clearance | 46ms (IEC 60255 P1 compliant) |
| Selectivity with GOOSE | 10/10 |
| Cross-zone f_int sharing | Enables n_confirm reduction: −1ms acceleration |
| Model-veto GOOSE alert | CT sat veto + sync-error veto propagated correctly |

---

## §7 Limitations

**L-1 — Simplified detection time:** Instantaneous relay model (no DFT delay). Realistic +20ms from DFT → t_clear≈62ms. Hardware-in-loop study required.

**L-2 — No ASN.1/BER encoding:** GOOSE timing and state semantics modelled; full PDU encoding not implemented. Production implementation requires libiec61850 or pyiec61850.

**L-3 — Single relay per zone:** Main-1/main-2 dual IED topology not modelled; additional GOOSE interaction complexity in dual-IED configuration.

**L-4 — No process-bus SV:** Station-bus GOOSE only; IEC 61850-9-2 Sampled Values (merging unit integration) deferred.

**L-5 — Simplified LAN model:** Gaussian jitter; no Ethernet frame collisions or VLAN priority simulation (IEC 61850 requires per-VLAN QoS for Class P1/P2 compliance).

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy, heapq (stdlib).

```bash
cd /root/phd_thesis/04_code/sambp/integration
python goose_coordinator.py --all-scenarios --sim-time 200

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR06_iec61850_goose
pdflatex main_report6 && bibtex main_report6 && pdflatex main_report6 && pdflatex main_report6
```

**Key output:** Per-scenario: `{t_detect, t_goose, t_clear}`; GOOSE event log; κ_n/f_int exchange log; latency sweep table.

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report6.tex` read (495 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report6.tex` is authoritative — this file is a read-only analytical summary.*
