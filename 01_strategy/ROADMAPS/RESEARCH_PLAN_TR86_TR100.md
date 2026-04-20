# SAMBP Research Plan — TR-86 to TR-100
## Novel Results, Simulations and Thesis Synthesis

**Date:** April 2026  
**Context:** Extends the completed SAMBP framework (TR-01–TR-85) in five tracks:  
(A) Large-scale validation · (B) AI/ML depth · (C) 100% GFM grid · (D) Standards · (E) Thesis synthesis  
**Submission target:** Q3 2028

---

## PRIORITY RANKING

| Priority | TR | Track | Core Deliverable | Novelty |
|:--------:|-----|-------|-----------------|:-------:|
| 1 | TR-86 | A | IEEE 118-bus Monte Carlo (N=50 000) | ★★★★★ |
| 2 | TR-87 | A | PSCAD→SAMBP replay pipeline | ★★★★☆ |
| 3 | TR-88 | A | N-2 cascading contingency study | ★★★★☆ |
| 4 | TR-89 | B | GNN topology-aware protection | ★★★★★ |
| 5 | TR-90 | B | Reinforcement learning for OC coordination | ★★★★★ |
| 6 | TR-91 | B | Federated learning across substations | ★★★☆☆ |
| 7 | TR-92 | C | 100% GFM grid — zero-SG protection | ★★★★★ |
| 8 | TR-93 | C | Black-start/restoration with GFM inverters | ★★★★☆ |
| 9 | TR-94 | C | Inertia-less frequency protection (Relay 81) | ★★★★☆ |
| 10 | TR-95 | D | IEEE 2800-2022 compliance audit | ★★★☆☆ |
| 11 | TR-96 | D | IEC 61850 Ed.3 + IEC 62351-8 key management | ★★★☆☆ |
| 12 | TR-97 | D | Cyber-physical threat tree (IEC 62443) | ★★★☆☆ |
| 13 | TR-98 | E | Full SAMBP sensitivity + Cramér–Rao bounds | ★★★★☆ |
| 14 | TR-99 | E | Cross-chapter consistency audit | ★★☆☆☆ |
| 15 | TR-100 | E | Submission readiness — final LaTeX + bibliography | ★★☆☆☆ |

---

## TRACK A — LARGE-SCALE VALIDATION

### TR-86: IEEE 118-Bus Large-Scale Monte Carlo

**Research gap:** All previous Monte Carlos (TR-08, TR-26, TR-37, TR-66) used networks of ≤14 buses.  
The SAMBP framework has never been stress-tested on a transmission-scale network with realistic  
topology, load diversity, and IBR penetration levels.

**Work packages:**

| WP | Deliverable | Method |
|----|------------|--------|
| 86.1 | IEEE 118-bus IBR overlay | Replace 30/53/100% of SG capacity with GFM/GFL mix; pandapower case118() base |
| 86.2 | Fault scenario generator | 173 lines × 4 fault types × 3 positions = 2 076 fault loci; random R_f ~ LogNorm |
| 86.3 | SAMBP protection stack sweep | Run 87L, 87T, distance (21), 46, 51, 67 for every scenario |
| 86.4 | Monte Carlo engine | N=50 000 trials; Latin Hypercube Sampling on [IBR penetration, R_f, load level] |
| 86.5 | Statistical analysis | PD/PFA per function; confidence intervals (Wilson score); sensitivity tornado chart |
| 86.6 | PDF report | LaTeX report with pgfplots figures |

**Key hypotheses to test:**
- H1: SAMBP 87L agrees with ground truth at ≥ 97% for IBR penetration ≤ 50%
- H2: Distance relay (21) misoperation rate increases monotonically with f_GFM
- H3: Negative-sequence element (46) degrades for GFM-only networks (low I2)

**Deliverables:** `models/ieee118_network.py`, `reports/tr86_mc_generator.py`,  
`tests/test_tr86_ieee118.py`, `phase_8_advanced_extensions/TR86_ieee118_mc/main_report86.pdf`

**Chapter link:** Ch.3 (quantifies protection challenges at scale), Ch.7 (integration evidence)

---

### TR-87: PSCAD→SAMBP Electromagnetic-Transient Replay Pipeline

**Research gap:** All SAMBP simulations use phasor-domain models. EMT ground truth is needed  
to verify that the phasor approximation holds during IBR fault transients (first 10 ms).

**Work packages:**

| WP | Deliverable | Method |
|----|------------|--------|
| 87.1 | COMTRADE parser extension | Read PSCAD-exported COMTRADE files; extend `comtrade_parser.py` |
| 87.2 | Phasor extractor | DFT sliding window (N=1 cycle) → complex phasors at 1 kHz update rate |
| 87.3 | PSCAD test cases | 10 reference cases: SG-only + 30/50/100% IBR; 3PH and SLG at bus 33 |
| 87.4 | Error analysis | Track V_mag error and I_mag error vs. EMT; report MAE and 95th percentile |
| 87.5 | Phasor validity window | Identify earliest time after fault inception where phasor error < 2% |

**Deliverables:** `estimation/emt_phasor_bridge.py`, `tests/test_tr87_pscad_replay.py`,  
`TR87_pscad_replay/main_report87.pdf`

**Chapter link:** Ch.2 (validates IBR model), Ch.4 (87L phasor accuracy)

---

### TR-88: N-2 Cascading Contingency Protection Study

**Research gap:** TR-79 handled N-2 topology detection with pre-computed tables. TR-88 performs  
a full dynamic cascading failure simulation to measure protection misoperation in cascade chains.

**Work packages:**

| WP | Deliverable | Method |
|----|------------|--------|
| 88.1 | Cascade engine | Sequential fault → trip → redispatch loop; terminates at island or stable state |
| 88.2 | Protection re-evaluation | Re-run SAMBP settings after each step change |
| 88.3 | 100 cascading scenarios | 10 initial contingencies × 10 IBR mixes on 118-bus |
| 88.4 | Misoperation counter | Count sympathetic trips and failed trips per cascade depth |
| 88.5 | Mitigation strategy | Adaptive reach block + GOOSE inhibit after N-1 detected |

**Deliverables:** `models/cascade_engine.py`, `tests/test_tr88_cascade.py`,  
`TR88_cascade/main_report88.pdf`

**Chapter link:** Ch.9 (centralised protection), Ch.7 (integration)

---

## TRACK B — AI/ML ENHANCEMENT

### TR-89: Graph Neural Network for Topology-Aware Protection

**Research gap:** Current SAMBP uses EKF + rule-based coordination. A GNN can learn  
protection zones directly from network graph structure, enabling zero-shot generalisation  
to unseen topologies.

**Work packages:**

| WP | Deliverable | Method |
|----|------------|--------|
| 89.1 | Graph dataset | Convert 118-bus + 10 synthetic topologies to PyTorch Geometric graphs |
| 89.2 | Node features | [V_pu, I_pu, k_ibr, f_gfm, zone_id] per bus |
| 89.3 | GNN architecture | 3-layer GraphSAGE; node classification (TRIP / RESTRAIN / ALARM) |
| 89.4 | Training | 80/10/10 split; weighted cross-entropy (PFA penalty = 10×PD penalty) |
| 89.5 | Benchmarking | Compare GNN vs. rule-based SAMBP on held-out topologies |
| 89.6 | Explainability | Grad-CAM node attribution — which neighbours drive the trip decision |

**Deliverables:** `ml/gnn_protection.py`, `tests/test_tr89_gnn.py`,  
`TR89_gnn/main_report89.pdf`

**Chapter link:** Ch.8 (ML for protection)

---

### TR-90: Reinforcement Learning for Adaptive OC Coordination

**Research gap:** OC coordination is currently a one-shot LP solve (TR-85, AdaptiveOC).  
RL allows online adaptation as the network changes — generation dispatch, IBR curtailment,  
or N-1 topology changes — without re-running the LP.

**Work packages:**

| WP | Deliverable | Method |
|----|------------|--------|
| 90.1 | Environment | OpenAI Gym wrapper: state = [I_load, I_fault_pred, topology_vec]; action = pickup setpoint |
| 90.2 | Reward function | +1 correct trip, –10 nuisance trip, –5 failed trip, –0.1 per setpoint change |
| 90.3 | Agent | Proximal Policy Optimisation (PPO) with 2-layer MLP actor-critic |
| 90.4 | Training | 500 000 environment steps on 14-bus; transfer to 118-bus (zero-shot) |
| 90.5 | Comparison | RL vs. LP-OC vs. fixed relay settings: nuisance trip rate + selectivity index |

**Deliverables:** `ml/rl_oc_agent.py`, `ml/oc_env.py`, `tests/test_tr90_rl.py`,  
`TR90_rl_oc/main_report90.pdf`

**Chapter link:** Ch.8, Ch.9

---

### TR-91: Federated Learning Across Substations

**Research gap:** Centralised training (TR-89, TR-90) requires sharing raw measurements,  
violating substation data privacy (IEC 62351 / NERC CIP). Federated learning trains a  
shared model while keeping raw data at each substation.

**Work packages:**

| WP | Deliverable | Method |
|----|------------|--------|
| 91.1 | Federated coordinator | FedAvg aggregation; simulated 10-substation ring |
| 91.2 | Local models | Each substation trains a small MLP on its own fault records |
| 91.3 | Privacy analysis | Differential privacy (ε-δ) guarantee on gradient sharing |
| 91.4 | Convergence study | Rounds to converge vs. number of substations and data heterogeneity |
| 91.5 | Accuracy | Federated model accuracy vs. centralised upper bound |

**Deliverables:** `ml/federated_coordinator.py`, `tests/test_tr91_federated.py`,  
`TR91_federated/main_report91.pdf`

**Chapter link:** Ch.8, Ch.9

---

## TRACK C — 100% GFM GRID

### TR-92: Zero-SG Protection — 100% Grid-Forming Inverter Network

**Research gap:** The entire SAMBP framework (TR-01–TR-85) assumes at least some  
synchronous generation. In a 100% GFM grid, classical protection assumptions break:  
fault current is current-limited, sequence networks collapse, and voltage-controlled sources  
behave unlike SGs in all fault types.

**Work packages:**

| WP | Deliverable | Method |
|----|------------|--------|
| 92.1 | 100% GFM network model | Modify case14: replace all SG with GFM inverters; retain load |
| 92.2 | Fault current characterisation | Sweep: SLG/DLG/3PH × 14 buses × 3 IBR current limits (1.0/1.2/1.5 pu) |
| 92.3 | Sequence network failure analysis | Quantify I2/I0 suppression; show failure of classical 46/67 elements |
| 92.4 | Novel protection strategy | Voltage-based differential + dV/dt trip for 100% GFM |
| 92.5 | 60-scenario validation | Confirm novel strategy: agree_rate ≥ 90% |

**Deliverables:** `models/gfm100_network.py`, `coordination/gfm100_protection.py`,  
`tests/test_tr92_gfm100.py`, `TR92_gfm100/main_report92.pdf`

**Chapter link:** Ch.2 (IBR modelling), Ch.3 (challenges), Ch.6 (generator protection in zero-SG)

---

### TR-93: Black-Start and Restoration with GFM Inverters

**Research gap:** Black-start is governed by NERC EOP-005 / IEC TR 63227 for SG units.  
No validated protocol exists for GFM-only black-start in islanded microgrids.

**Work packages:**

| WP | Deliverable | Method |
|----|------------|--------|
| 93.1 | Black-start sequence model | Stage machine: ENERGISE → PICK_UP_LOAD → SYNCHRONISE |
| 93.2 | Protection during energisation | Trip blocking during dead-bus energisation (cold-start inrush) |
| 93.3 | Voltage ramp control | GFM V-ramp with current limit to prevent transformer inrush trip |
| 93.4 | Island→grid reconnection | Synchrocheck (25) element for GFM — phase/frequency matching |
| 93.5 | 30-scenario validation | Correct sequence completion ≥ 90%; no nuisance trip |

**Deliverables:** `models/black_start_engine.py`, `tests/test_tr93_blackstart.py`,  
`TR93_blackstart/main_report93.pdf`

**Chapter link:** Ch.6, Ch.7

---

### TR-94: Inertia-Less Frequency Protection (Relay 81 Redesign)

**Research gap:** TR-63 extended Relay 81 for GFM virtual inertia. In a 100% GFM grid,  
ROCOF is governed by the virtual inertia constant H_v — which is software-controlled  
and can change between operating modes. Classical 81 with fixed ROCOF threshold misfires.

**Work packages:**

| WP | Deliverable | Method |
|----|------------|--------|
| 94.1 | Adaptive ROCOF estimator | Real-time H_v estimation via GOOSE-broadcast virtual inertia |
| 94.2 | Dynamic threshold | df/dt threshold = f(H_v, ΔP_disturbance_estimate) |
| 94.3 | Anti-aliasing filter | 2nd-order Butterworth on raw frequency measurement (fc=10 Hz) |
| 94.4 | 40-scenario test | Under-frequency: 20 disturbance sizes × 2 H_v modes; no false trip |
| 94.5 | NERC PRC-006 compliance | Verify response time ≤ required UFLS timing |

**Deliverables:** `coordination/adaptive_rocof.py`, `tests/test_tr94_rocof.py`,  
`TR94_rocof/main_report94.pdf`

**Chapter link:** Ch.6 (generator suite extended to GFM)

---

## TRACK D — STANDARDS AND COMPLIANCE

### TR-95: IEEE 2800-2022 IBR Interconnection Requirements Audit

**Work packages:**

| WP | Deliverable |
|----|------------|
| 95.1 | Requirements extraction | Map IEEE 2800-2022 §6–§9 to SAMBP protection functions |
| 95.2 | Compliance matrix | Each SAMBP function: COMPLIANT / PARTIAL / NON-COMPLIANT + gap note |
| 95.3 | Gap remediation | For each PARTIAL/NON-COMPLIANT: propose SAMBP modification |
| 95.4 | Traceability table | Maps thesis sections ↔ IEEE 2800-2022 clauses |

**Deliverables:** `TR95_ieee2800/compliance_matrix.tex`, `TR95_ieee2800/main_report95.pdf`

**Chapter link:** Ch.1 (motivation), Ch.3 (challenges framing)

---

### TR-96: IEC 61850 Edition 3 and IEC 62351-8 Key Management

**Work packages:**

| WP | Deliverable |
|----|------------|
| 96.1 | Ed.3 delta analysis | What changes from Ed.2 (TR-06, TR-14, TR-82) in SCL/GOOSE/MMS |
| 96.2 | Key management server | IEC 62351-8 KeyServer simulation: certificate rotation, grace period |
| 96.3 | Integration test | KeyServer ↔ GOOSESecurityLayer (TR-82) end-to-end |
| 96.4 | Latency impact | Measure GOOSE trip latency with vs. without HMAC verification |

**Deliverables:** `integration/key_management_server.py`, `tests/test_tr96_iec61850ed3.py`,  
`TR96_iec61850ed3/main_report96.pdf`

**Chapter link:** Ch.9 (centralised/WA-GOOSE)

---

### TR-97: Cyber-Physical Threat Modelling (IEC 62443 Threat Tree)

**Work packages:**

| WP | Deliverable |
|----|------------|
| 97.1 | Attack surface enumeration | GOOSE spoofing, SAMPLED_VALUE injection, MMS replay, firmware tamper |
| 97.2 | STRIDE threat tree | Structured threat tree; attack paths to protection misoperation |
| 97.3 | Countermeasure mapping | SAMBP TR-82 + TR-96 countermeasures vs. each attack path |
| 97.4 | Residual risk assessment | DREAD scoring; residual risk after countermeasures |

**Deliverables:** `TR97_cyber_threat/threat_tree.tex`, `TR97_cyber_threat/main_report97.pdf`

**Chapter link:** Ch.9

---

## TRACK E — THESIS SYNTHESIS

### TR-98: Full SAMBP Sensitivity Analysis and Cramér–Rao Bounds

**Research gap:** Individual TRs report agree_rate but not the sensitivity of each protection  
function to its tuning parameters. Cramér–Rao lower bounds give the theoretical minimum  
estimation variance for the EKF, providing a principled bound on protection accuracy.

**Work packages:**

| WP | Deliverable |
|----|------------|
| 98.1 | Parameter sensitivity | ±10% perturbation of each EKF parameter; measure Δagree_rate |
| 98.2 | Fisher information matrix | Compute FIM for EKF state vector at each operating point |
| 98.3 | Cramér–Rao bound | CRLB for k_ibr and f_gfm estimation; compare to EKF covariance |
| 98.4 | Tornado chart | Rank parameters by sensitivity; identify critical tuning knobs |
| 98.5 | Robustness certificate | Formal claim: SAMBP meets PD ≥ 0.97, PFA ≤ 0.01 for ±20% parameter error |

**Deliverables:** `estimation/sensitivity_analysis.py`, `TR98_sensitivity/main_report98.pdf`

**Chapter link:** All chapters (closes open proofs)

---

### TR-99: Cross-Chapter Consistency Audit

**Work packages:**

| WP | Deliverable |
|----|------------|
| 99.1 | Proposition inventory | List all Propositions/Theorems/Lemmas in Ch.2–9 with proof location |
| 99.2 | Symbol table | Unified notation table; flag conflicts between chapters |
| 99.3 | Figure cross-reference | Every figure traced to its generating script and data |
| 99.4 | Citation completeness | Every claim with [cite] linked to bib entry; no orphan citations |
| 99.5 | Chapter dependency graph | TikZ DAG showing which chapters depend on which TR results |

**Deliverables:** `01_thesis/audit/consistency_report.tex`, `TR99_audit/main_report99.pdf`

**Chapter link:** All chapters

---

### TR-100: Submission Readiness

**Work packages:**

| WP | Deliverable |
|----|------------|
| 100.1 | LaTeX compilation clean | Zero warnings in thesis_main.tex; all \ref resolved |
| 100.2 | Figure resolution | All figures ≥ 300 DPI; PDF/A-1b compliance |
| 100.3 | Bibliography | BibTeX: no duplicate keys, no missing DOIs for published papers |
| 100.4 | Abstract and synopsis | Final abstract (≤ 300 words); synopsis (≤ 10 pages) updated |
| 100.5 | Plagiarism check | iThenticate run; similarity ≤ 15% (IIT Madras threshold) |
| 100.6 | Pre-submission sign-off | Checklist signed by supervisor; submission package assembled |

**Deliverables:** `01_thesis/active/thesis_main.pdf` (final), submission package

---

## CRITICAL PATH

```
TR-86 (scale-up) ──────────────────────────────────────────────┐
TR-87 (EMT replay) ─────────────────────────────────────────── │
TR-88 (N-2 cascade) ────────────────────────────────────────── │
                                                                 ├──► TR-98 (sensitivity) ──► TR-99 (audit) ──► TR-100 (submit)
TR-92 (100% GFM) ──► TR-93 (black start) ──► TR-94 (ROCOF) ── │
                                                                 │
TR-89 (GNN) ──► TR-90 (RL) ──► TR-91 (federated) ─────────── ┘
TR-95/96/97 (standards) ──────────────────────────────────────────────────────────────────────►
```

| Milestone | Target |
|-----------|--------|
| TR-86–TR-88 complete | Q2 2026 |
| TR-89–TR-91 complete | Q3 2026 |
| TR-92–TR-94 complete | Q4 2026 |
| TR-95–TR-97 complete | Q1 2027 |
| TR-98–TR-99 complete | Q2 2027 |
| TR-100 + submission | Q3 2028 |

---

## NEW-TR CHECKLIST (5 rules, unchanged from TR-56 plan)

1. **Mathematical novelty first** — does it add a new model, estimator, or proof?
2. **Chapter linkage** — every TR maps to ≥ 1 thesis chapter section
3. **Scenario library** — minimum 20 scenarios; agree_rate reported
4. **PDF report** — LaTeX report compiled before TR marked COMPLETE
5. **PROGRESS.yaml** — entry added/updated on completion

---

*Document generated: April 2026 | SAMBP Research Group, IIT Madras EE*
