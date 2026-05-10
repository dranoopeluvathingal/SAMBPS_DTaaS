# Centralized Microgrid Controller with FS-MPC Interface Converters and Digital Twin Integration — Implementation Plan

**Author:** Anoop Eluvathingal (IIT Madras / NUS / NTU)
**Date:** 26 April 2026
**Purpose:** Engineering plan to scale the Perez & Flores-Bahamonde 2016 single-converter FS-MPC reactive/harmonic compensation scheme into a fleet of microgrid interface converters governed by a centralized microgrid controller (CMC), validated against and continuously calibrated by a microgrid digital twin (MG-DT). Direct scaffolding for MAS-DT-SH thesis Sprints 3–6 and the APPEEC 2026 paper #2.

---

## 0. Executive Summary

The single-converter FS-MPC scheme of [F] gives a microgrid interface converter (MIC) the ability to act simultaneously as a bulk-power gateway and a power-quality device. Operating *one* such converter is well-understood. Operating *several* of them as a coordinated fleet, while a digital twin runs in parallel checking, calibrating, and forecasting, is the open problem this plan addresses.

The proposed architecture is three-layered: a **device layer** of per-converter FS-MPC + outer energy-PI controllers (Layer 1, μs–ms timescale); a **centralized microgrid controller (CMC)** layer that arbitrates mode, dispatches references, and detects faults (Layer 2, s–min timescale); and a **microgrid digital twin (MG-DT)** layer that mirrors the physical plant in soft real-time and provides four services to Layers 1 and 2 — online parameter ID, predictive what-if, anomaly detection, and cyber-attack screening (Layer 3, soft real-time, ms–s).

The plan is staged across **four phases over twelve months** (Single ICA → Fleet → DT integration → HIL validation), with twenty-six concrete deliverables, a 12-test integration matrix, and risk register. Total estimated effort: **140 working days** for one PhD candidate, parallelisable to ~85 calendar days with one MS-thesis collaborator on the DT side.

---

## Part A — System Architecture

### 1. Three-Layer View

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 3 — MICROGRID DIGITAL TWIN (MG-DT)                               │
│  ─────────────────────────────────────────────────────────────────────  │
│  - High-fidelity EMT model (sub-ms) of plant + converters + loads       │
│  - Parameter ID (R, L, C drift; load characterisation)                  │
│  - What-if predictor (1 s … 5 min look-ahead)                           │
│  - Anomaly detector (DT vs. measured residual)                          │
│  - Cyber-attack screen (signal divergence + sequence analysis)          │
└─────────────────────────────────────────────────────────────────────────┘
            ▲                                     │
            │ telemetry (5–100 Hz)                │ recommendations,
            │                                     │ updated parameters,
            │                                     │ predicted refs
            │                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 2 — CENTRALIZED MICROGRID CONTROLLER (CMC)                       │
│  ─────────────────────────────────────────────────────────────────────  │
│  - Mode arbitration (grid / island / transition)                        │
│  - Optimal dispatch (P_ref, Q_ref, v_dc_ref per ICA)                    │
│  - Reactive/Q allocation policy across ICAs                             │
│  - Harmonic absorption allocation (which ICA absorbs what)              │
│  - Fault detection + isolation (FDI) at fleet level                     │
│  - Self-healing reconfiguration (with Switch Agents)                    │
└─────────────────────────────────────────────────────────────────────────┘
            ▲                                     │
            │ telemetry (10–1000 Hz)              │ refs, modes,
            │                                     │ enable/disable
            │                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — DEVICE LAYER (PER ICA + LOCAL SENSORS)                       │
│  ─────────────────────────────────────────────────────────────────────  │
│  ICA-1   ICA-2  …   ICA-N    Switch Agents    Load monitors             │
│  Each ICA:                                                              │
│    - FS-MPC inner current loop  (T_s = 20 µs)                           │
│    - Energy-domain DC-link PI   (BW ≈ 50 Hz)                            │
│    - Local PLL                   (lock < 30 ms)                         │
│    - Telemetry publisher                                                │
│    - Reference subscriber                                               │
└─────────────────────────────────────────────────────────────────────────┘
            ▲                                     ▼
       Physical AC bus  ◄────────►  Loads / DERs / Storage
```

### 2. Layer Responsibilities — Functional Allocation

| Function | Layer 1 (Device) | Layer 2 (CMC) | Layer 3 (DT) |
|---|---|---|---|
| Switching-state selection | ✓ FS-MPC at 50 kHz | — | — |
| Inner current ref tracking | ✓ | — | shadow-runs |
| DC-link voltage regulation | ✓ outer PI | sets `v_dc_ref` | shadow-runs |
| Reactive power dispatch | local Q at PCC | ✓ optimal Q split | predicts load Q |
| Harmonic absorption split | local capability | ✓ allocation policy | identifies harmonic profile |
| Mode (grid/island) handling | ✓ executes | ✓ decides | predicts transition |
| FDI / self-healing | local sensor only | ✓ system-wide FDI | early-warning |
| Plant parameter calibration | uses values | applies updates | ✓ identifies online |
| Cyber-attack detection | none | basic plausibility | ✓ residual analysis |
| Operator dashboard | — | live KPIs | ✓ what-if scenarios |
| Economic dispatch (tertiary) | — | ✓ slower MPC | input forecast |

### 3. Latency Budget

| Path | Period / latency target | Why |
|---|---|---|
| Sensor → FS-MPC predictor | < 5 µs | within `T_s` = 20 µs budget |
| FS-MPC inner loop control | 20 µs | fixed by paper [F] |
| Outer energy PI | 200 µs (5 kHz) | aliased control |
| ICA → CMC telemetry publish | 10 ms (100 Hz) | suffices for sub-cycle aggregate metrics |
| CMC → ICA reference push | 10 ms | bound by Ethernet RTT + serialisation |
| CMC dispatch optimisation | 1 s | tertiary-style economic + Q-allocation MPC |
| DT real-time tick | 100 µs internal, 10 ms publish | EMT fidelity for residuals |
| DT parameter-ID update | 10 s | low-rate calibration |
| Mode-transition decision | < 100 ms | IEEE 1547-2018 RT requirements |
| Fault isolation (CMC + Switch Agents) | < 200 ms | industry expectation |
| Cyber-attack alarm | < 1 s | usable SOC alert |

These numbers feed the protocol selection in Part E.

---

## Part B — Layer 1: Per-Converter Device Software (Interface Converter Agent)

### 4. ICA Module Map

```
ICA Agent
├── core/
│   ├── plant.py              # Eq.(1)(2) state model — used by predictor + DT
│   ├── inner_fsmpc.py        # 8-vector predictor + cost + argmin + delay comp
│   ├── outer_energy_pi.py    # Energy-domain PI on E_c = ½Cv_dc²
│   ├── pll.py                # SOGI-PLL positive-sequence detector
│   └── modes.py              # local FSM: starting / running / fault / mode_switch
├── io/
│   ├── adc.py                # measurement abstraction (HW or sim)
│   ├── pwm.py                # gate driver abstraction
│   └── safety.py             # over-current, over-voltage hard cuts (independent of FS-MPC)
├── comm/
│   ├── telemetry.py          # publishes at 100 Hz to CMC and DT
│   ├── refs.py               # subscribes to v_dc_ref, P_ref, Q_ref, mode
│   └── time_sync.py          # PTP/IEEE 1588 interface
├── selftest/
│   ├── unit_predictor.py     # property tests on Eq.(4)
│   ├── thd_meter.py          # online FFT-based THD (post-control)
│   └── audit_log.py          # ring buffer of switching states for forensics
└── main.py                   # event loop (RT priority)
```

### 5. Inner-Loop Pseudocode

```
loop every T_s = 20 µs:
    measure i_m, v_dc, v_s, i_l
    v_s_pos, theta = pll.update(v_s)
    
    # outer loop runs slower; latest setpoint is cached
    I_s_amp = outer.last_amplitude
    i_s_ref = I_s_amp * sin(theta)
    i_m_ref = i_s_ref - i_l
    
    best_s, best_cost = None, +inf
    for s in 8_switching_vectors:
        i_pred = (1 - r*Ts/L) * i_m + (Ts/L) * (v_s - M @ s * v_dc)
        cost = sum((i_pred - i_m_ref)**2)  # 3-phase squared error
        if cost < best_cost:
            best_s, best_cost = s, cost
    
    pwm.apply(best_s)  # one-step delay compensated separately
    telemetry.append((t, i_m, v_dc, best_s, cost))
```

### 6. Outer-Loop Pseudocode

```
loop every 200 µs:
    E_c = 0.5 * C * v_dc**2
    E_c_ref = 0.5 * C * v_dc_ref**2
    err = E_c_ref - E_c
    integ += err * dt
    I_s_amp = Kp*err + Ki*integ + I_s_ff       # feedforward of (p_dc + p_l)
    outer.last_amplitude = I_s_amp
```

### 7. Reference Interface (CMC → ICA)

| Topic | Type | Rate | Description |
|---|---|---|---|
| `/ica/{id}/refs/v_dc_ref` | float | 1 Hz | DC-link target |
| `/ica/{id}/refs/Q_ref` | float | 10 Hz | reactive support |
| `/ica/{id}/refs/H_mask` | float[H] | 1 Hz | harmonic absorption priority per order |
| `/ica/{id}/refs/mode` | enum | event | grid/island/idle |
| `/ica/{id}/refs/enable` | bool | event | safety arm |

Reactive `Q_ref` is converted locally into an `I_s_ref` amplitude phase shift; harmonic mask `H_mask` filters which orders the FS-MPC compensates.

---

## Part C — Layer 2: Centralized Microgrid Controller

### 8. CMC Functional Decomposition

```
CMC
├── state_estimator/
│   ├── topology_tracker.py   # graph of buses, switches, ICAs, loads
│   ├── pseudomeasurement.py  # fills missing telemetry from DT
│   └── fault_detector.py     # residual-based FDI
├── optimizer/
│   ├── mode_arbiter.py       # FSM grid/island/transition
│   ├── q_allocator.py        # OPF-style Q allocation across ICAs
│   ├── h_allocator.py        # harmonic-absorption splitter per order
│   └── dispatch_mpc.py       # tertiary-style economic MPC (1 min horizon)
├── self_healing/
│   ├── isolator.py           # commands to Switch Agents
│   ├── reconfiguration.py    # post-fault topology
│   └── black_start.py        # islanded re-energisation sequence
├── operator/
│   ├── dashboard_ws.py       # live KPI websocket
│   ├── manual_overrides.py   # operator inputs
│   └── alarms.py             # event log
├── api/
│   ├── ica_pubsub.py         # tx refs, rx telemetry
│   ├── dt_bridge.py          # bidirectional with DT
│   └── scada_dnp3.py         # interface to wider grid SCADA
└── main.py
```

### 9. Q Allocation Optimisation (Heart of CMC)

At each control tick (1 s), CMC solves a small QP:

```
minimize    sum_i  α_i * Q_i^2  +  β * sum_i (V_i - V_ref)^2
            + γ * (sum_i Q_i - Q_total_target)^2
subject to  |Q_i| ≤ S_i^max  (apparent-power limit per ICA)
            Q_i in feasible region given P_i (capability curve)
            sum_i P_i = P_load + P_loss   (active power balance)
            grid-tie limits if grid-connected
```

`Q_total_target` is set by the secondary voltage controller; `α_i`, `β`, `γ` are weights tuned offline. The output `Q_i` is broken into a *fundamental* part (sent as `Q_ref`) and a *harmonic-absorption capacity* (sent as `H_mask`).

**Why a slow MPC and not droop?** In a centralized architecture with reliable comms, the QP gives globally optimal Q sharing rather than the local-only droop optimum. When comms degrade, the CMC falls back to droop coefficients pushed to ICAs — graceful degradation.

### 10. Mode Arbitration FSM

```
                     gridConnected
                       │  ▲
                  TIE_OPEN  TIE_CLOSED
                       │  │
                       ▼  │
             modeTransition (≤100 ms)
                       │  ▲
                 LOSS_OF_GRID  GRID_RESTORED
                       │  │
                       ▼  │
                   islanded
                       │  ▲
                 BLACK_RESTART  BLACK_START_DONE
                       │  │
                       ▼  │
                   blackStart
```

CMC owns the FSM. ICAs are told the mode but execute autonomously (mode-agnostic FS-MPC of [F] simplifies the transition).

### 11. Harmonic Allocation (Novel Contribution)

In a fleet of N ICAs, total harmonic load `i_l_h` (h = 5, 7, 11, 13…) can be split among them in proportion to their *available headroom* (peak current limit minus fundamental current):

```
H_i_h = i_l_h_total * (S_i^max - |I_i_fund|) / sum_j (S_j^max - |I_j_fund|)
```

The `h_allocator.py` publishes `H_mask` to each ICA. This is the contribution that turns Perez's single-converter scheme into a coordinated fleet — an obvious extension to claim in your thesis chapter.

---

## Part D — Layer 3: Microgrid Digital Twin

### 12. DT Architecture

```
MG-DT
├── physics/
│   ├── emt_model.py          # OpenModelica / PSCAD / Python EMT — sub-ms step
│   ├── grid_eq.py            # equivalent grid (Thevenin or PQ profile)
│   ├── load_models.py        # ZIP, CIGRE-aggregated, 6-pulse rectifier presets
│   └── icas_replica.py       # mirrors of all ICAs
├── identification/
│   ├── recursive_ls.py       # online R, L, C update from residuals
│   ├── load_classifier.py    # classifies load harmonic profile
│   └── parameter_kalman.py   # Kalman state-parameter joint estimator
├── prediction/
│   ├── horizon_simulator.py  # rolls forward 1–300 s with stochastic loads
│   ├── what_if.py            # branched scenarios
│   └── fault_propagator.py   # injects faults to predict CMC response
├── analytics/
│   ├── residual_monitor.py   # measured − DT prediction
│   ├── anomaly_detector.py   # one-class SVM on residuals
│   ├── cyber_screen.py       # message-level integrity + signal divergence
│   └── ml_advisor.py         # offline-trained NN for FS-MPC weight hints
├── api/
│   ├── cmc_bridge.py         # CMC ↔ DT (send predictions, receive snapshots)
│   ├── ica_shadow.py         # parallel ICA emulators
│   └── operator_view.py      # 3D viz endpoint
└── orchestrator.py
```

### 13. DT Use Cases (5 prioritised)

| # | Use case | Direct benefit | Layer |
|---|---|---|---|
| U1 | **Online plant-parameter ID** for FS-MPC predictor | improves `i_m_pred` accuracy under R, L drift | feeds Layer 1 |
| U2 | **Look-ahead Q forecast** from load classifier | CMC pre-emptively dispatches Q | feeds Layer 2 |
| U3 | **Anomaly residual** between DT and measured | early sensor-fault detection | Layer 2 alert |
| U4 | **Cyber-attack screening** on signal/message integrity | rejects spoofed `Q_ref` injections | Layer 2 alert |
| U5 | **Operator what-if** for proposed actions | "what if we open Tie-2 at 10:30?" simulated | Layer 2 UI |

### 14. DT–Controller Co-design Loop

```
        ┌─────── physical plant ────────┐
        │      sensors → measurements    │
        └────────────────┬───────────────┘
                         │
            ┌────────────▼──────────────┐
            │  Layer 1 ICAs (FS-MPC)    │
            │  Layer 2 CMC              │
            └─────┬─────────────────┬───┘
                  │ telemetry       │ commands
                  ▼                 │
            ┌─────────────┐         │
            │   MG-DT     │         │
            │  EMT replica│         │
            └─────┬───────┘         │
                  │ residuals       │
                  │ predictions     │
                  │ updated params  │
                  ▼                 │
        ┌─────────────────────────┐ │
        │  parameter / weight     │ │
        │  recommendations        ├─┘
        └─────────────────────────┘
```

The closed feedback from DT into both Layer 1 (parameters) and Layer 2 (predictions, Q forecasts, what-ifs) is the cyber-physical loop that distinguishes a true digital twin from a plain simulator.

### 15. DT Realisation Choices

| Aspect | Recommendation | Alternatives |
|---|---|---|
| EMT engine | **OpenModelica + Python orchestration via FMI** | PSCAD (license), Simulink, Typhoon HIL |
| State exchange | FMI-Cosim 2.0 | OPC-UA, gRPC streams |
| Parameter ID | **RLS + Kalman hybrid** | particle filter, neural ID |
| Anomaly detector | **One-class SVM** + hard threshold | LSTM autoencoder |
| Cyber screen | **Hash-chained sequence numbers + STL on signals** | dedicated SIEM |
| Real-time host | **Linux PREEMPT-RT + Docker** | bare-metal RTOS |

---

## Part E — Software Stack & Deployment

### 16. Languages and Frameworks

| Layer | Primary | Reason | Secondary |
|---|---|---|---|
| Layer 1 (ICA) | **Python 3.11 + numpy + numba** for the simulation/prototype; **C++/HLS** when porting to FPGA/DSP | matches `fs_mpc_microgrid` repo from the forensic plan | MATLAB/Simulink coder for industry validation |
| Layer 2 (CMC) | **Python 3.11 + cvxpy + asyncio** | QP solver + async I/O | Julia/JuMP if larger systems |
| Layer 3 (DT) | **OpenModelica + Python orchestrator** | open EMT, FMI-friendly | Simulink + Simscape Electrical |
| Operator UI | **React + d3 over websocket** | live dashboards | Grafana |

### 17. Communication Protocols

| Path | Protocol | Why |
|---|---|---|
| Sensor → ICA | analog/digital local | local DSP I/O |
| ICA ↔ CMC | **MQTT v5** (publish/subscribe) over TLS | low-latency, broker-friendly |
| ICA ↔ DT shadow | **DDS** (RTI Connext or eProsima Fast DDS) | RT pub/sub with QoS |
| CMC ↔ DT | **OPC-UA** + FMI | industrial standard, vendor-neutral |
| Switch Agents | **IEC 61850 GOOSE** | sub-4 ms tripping |
| External SCADA | **DNP3 / IEC 60870-5-104** | utility integration |
| Operator UI | **WebSocket + JSON** | browser-friendly |

### 18. Containerisation and Deployment

```
docker-compose.yml
├── ica-{1..N}       # one container per ICA agent (or per real device)
├── cmc              # central controller
├── mg-dt            # digital twin
├── mqtt-broker      # mosquitto
├── dnp3-gateway     # external interface
├── ui-frontend      # React app
└── postgres         # event log + telemetry archive
```

In production each container is pinned to a CPU core (PREEMPT-RT) and the whole stack runs on a 1 RU industrial PC (Moxa V2616A or equivalent). For HIL the CMC runs on the host while the ICAs run inside a Typhoon HIL or OPAL-RT.

---

## Part F — Test Plan

### 19. Test Pyramid

```
Level 4: Field pilot (after Phase 4)
  ▲
Level 3: Hardware-in-loop (Typhoon HIL + 2 real ICAs)
  ▲
Level 2: System integration (full Docker stack, simulated plant)
  ▲
Level 1: Component integration (ICA + CMC, ICA + DT)
  ▲
Level 0: Unit tests (per module, per loop)
```

### 20. Test Matrix (12 cases)

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| T01 | 0 | FS-MPC predictor unit (Eq. 4) | tracks step `i_m_ref` in 1–2 samples |
| T02 | 0 | Outer PI energy loop | `v_dc` settles in 20±5 ms on 100 A step |
| T03 | 0 | SOGI-PLL on distorted `v_s` | locks within 30 ms, ±2° error at 5% THD |
| T04 | 1 | ICA standalone — reproduce [F] Fig 4–8 | THD `i_s` < 5% in all 3 modes |
| T05 | 1 | CMC Q-allocator vs. droop baseline | ≥10% lower total `\|Q\|` for same V error |
| T06 | 1 | DT parameter-ID convergence on R drift | 2% accuracy in <10 s |
| T07 | 2 | 4-ICA fleet — coordinated harmonic absorption | system `i_s` THD < 3% per ICA, < 2% PCC |
| T08 | 2 | Mode transition grid → island in 100 ms | `\|v_dc\|` deviation < 5%, no trip |
| T09 | 2 | DT-flagged anomaly during sensor fault on ICA-2 | DT alarm < 500 ms, CMC isolates ICA-2 |
| T10 | 2 | Cyber screen rejects spoofed `Q_ref` | rejected within 1 s, audit log entry |
| T11 | 3 | HIL: 2 real + 2 simulated ICAs | THD < 5%, settling within spec, no oscillation |
| T12 | 4 | Pilot site (small commercial) | 7-day continuous run, reactive billing reduction ≥ 30% |

---

## Part G — Implementation Roadmap

### 21. Phase Plan (12 months)

```
       Month  1   2   3   4   5   6   7   8   9  10  11  12
  Phase 1 : ████████  Single ICA reproduce + harden (T01–T04)
  Phase 2 :         ████████  Fleet + CMC (T05, T07, T08)
  Phase 3 :                 ████████  DT integration (T06, T09, T10)
  Phase 4 :                         ██████  HIL + pilot (T11, T12)
```

### 22. Phase 1 — Single ICA (Months 1–3, 35 person-days)

| # | Deliverable | Day |
|---|---|---|
| D01 | Repo scaffold `fs_mpc_microgrid/` (per earlier forensic plan) | 1 |
| D02 | Plant model `plant.py` + tests | 3 |
| D03 | 6-pulse + linear load model | 5 |
| D04 | SOGI-PLL implementation + lock test | 7 |
| D05 | FS-MPC inner loop + delay-comp + tests | 12 |
| D06 | Outer energy PI + tests | 14 |
| D07 | Reproduce [F] Fig 4–10 in notebooks | 20 |
| D08 | THD quantification + report | 22 |
| D09 | ICA agent wrapper (`io.adc`, `comm.refs`, `comm.telemetry`) | 28 |
| D10 | First end-to-end ICA-only Docker container | 35 |

### 23. Phase 2 — Centralized Controller + Fleet (Months 4–6, 40 person-days)

| # | Deliverable | Day |
|---|---|---|
| D11 | MQTT broker + topic schema | 38 |
| D12 | CMC scaffold `cmc/` repo | 40 |
| D13 | Topology tracker + state estimator | 47 |
| D14 | Mode arbitration FSM + tests | 52 |
| D15 | Q allocator (cvxpy QP) + tests | 58 |
| D16 | Harmonic allocator + tests | 62 |
| D17 | 4-ICA fleet simulation harness | 70 |
| D18 | Operator dashboard MVP | 75 |

### 24. Phase 3 — Digital Twin (Months 7–9, 35 person-days)

| # | Deliverable | Day |
|---|---|---|
| D19 | OpenModelica EMT replica | 80 |
| D20 | FMI bridge to CMC | 85 |
| D21 | RLS parameter ID | 92 |
| D22 | Anomaly detector + cyber screen | 100 |
| D23 | Look-ahead Q forecaster | 105 |
| D24 | DT-CMC closed loop + integration tests T06, T09, T10 | 110 |

### 25. Phase 4 — HIL + Pilot (Months 10–12, 30 person-days)

| # | Deliverable | Day |
|---|---|---|
| D25 | Typhoon HIL or OPAL-RT integration | 120 |
| D26 | Two-real-ICA hardware bench (NUS PSCL or IIT Madras lab) | 130 |
| D27 | T11 HIL test pass | 135 |
| D28 | T12 pilot deployment | 140 |

### 26. Effort Summary

| Phase | Person-days | Calendar months |
|---|---|---|
| Phase 1 | 35 | 3 |
| Phase 2 | 40 | 3 |
| Phase 3 | 35 | 3 |
| Phase 4 | 30 | 3 |
| **Total** | **140** | **12** |

With a single MS-thesis collaborator on the DT side (Phase 3 in parallel with Phase 2 final third), calendar can compress to ~9 months.

---

## Part H — Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| FS-MPC Forward Euler instability at T_s = 20 µs and L = 1 mH | Medium | High | Use trapezoidal predictor; verify pole locations |
| Hardware MQTT broker latency exceeds 10 ms budget | Medium | Med | Shadow with DDS or co-locate broker on CMC host |
| Anomaly false alarms swamp operator | High | Med | Tune SVM threshold offline with historical residuals; gating with multi-sample window |
| OpenModelica + Python FMI sync drift | Medium | Med | Use FMI-Cosim 2.0 with Jacobi master, audit reconciliation step |
| Data-driven param ID overfits transient | Medium | Med | Frequency-domain bandlimit on RLS update; freeze during transitions |
| Cyber screen rejects legitimate operator override | Low | Med | Operator authentication path (signed tokens) bypasses signal screen |
| Loss of comms degrades CMC dispatch | High | High | Local droop fallback already loaded in each ICA |
| HIL availability bottleneck | High | Med | Reserve Typhoon early (Month 8), have Python EMT fallback |
| Phase-3 (DT) requires more domain knowledge than budgeted | Medium | High | Recruit MS-thesis collaborator with Modelica experience |
| Pilot site permission delays | Medium | Med | Early engagement with NUS / IIT Madras facilities team in Month 6 |

---

## Part I — Master Summary Table

| Aspect | Choice / Value |
|---|---|
| **Architecture** | 3-layer: Device · CMC · MG-DT |
| **Inner loop** | FS-MPC, T_s = 20 µs, 8 vectors, delay-comp at k+2 |
| **Outer loop** | Energy-domain PI on E_c = ½Cv_dc² |
| **Centralized dispatch** | 1 Hz QP for Q + harmonic allocation |
| **DT engine** | OpenModelica EMT + Python FMI orchestrator |
| **DT services** | Parameter ID · Q forecast · Anomaly · Cyber screen · What-if |
| **Comms** | MQTT v5 (ICA↔CMC), DDS (ICA↔DT), OPC-UA + FMI (CMC↔DT), GOOSE (Switches) |
| **Languages** | Python (Layers 1, 2, DT orchestrator), Modelica (DT physics) |
| **Container** | Docker + PREEMPT-RT Linux on industrial PC |
| **Test pyramid** | 12-case matrix from unit to pilot |
| **Phases** | 4 phases × 3 months each |
| **Total effort** | 140 person-days; ≥9 calendar months with collaborator |
| **PhD relevance** | Maps directly onto MAS-DT-SH Sprints 3 (orchestrator), 4 (switch agents), 5 (taxonomy), 6 (Algorithm-1 end-to-end) |
| **Patent angle** | Harmonic-allocation policy across ICAs (Section 11) |
| **Publication anchor** | Reproduction + extension paper to IEEE Trans. Smart Grid 2026 |

---

## Part J — Concrete Next-Week Tasks

If you start tomorrow (Mon 27 Apr 2026):

| Day | Task | Output |
|---|---|---|
| Mon | Create `fs_mpc_microgrid/` repo, `pyproject.toml`, CI | green pipeline |
| Tue | Implement `plant.py` Eq. (1)(2) | unit tests pass |
| Wed | Implement `inner_fsmpc.py` Eq. (4) | step response visible |
| Thu | Implement `outer_energy_pi.py` | DC-link converges to ref |
| Fri | First ICA simulation reproduces [F] Fig 4 | THD < 5% |
| Sat | Capture screenshots, draft thesis-Ch4 paragraph + APPEEC #2 citation | text drafted |
| Sun | Sabbath — review the week, lock Phase 1 plan | decision log entry |

This single week converts the present plan from intent into evidence and unblocks Sprint 2 of MAS-DT-SH while you're in the APPEEC submission home stretch.

---

*Companion documents on the same workspace folder:*
*- `FS_MPC_Microgrid_Forensic_Analysis.md` — line-by-line read of the focal paper [F].*
*- `FS_MPC_Related_References_From_Drive.md` — Tier-1 reference library curation.*
*- `FS_MPC_Microgrid_Literature_Review_IEEE.pdf` — full systematic review with figures.*
*- `~/Desktop/fs_mpc_refs/` — local Tier-1 PDFs for offline reading.*
