# MPC_Microgrid_DTaaS

**Model-Predictive-Control of Microgrid Interface Converters as a Digital-Twin-as-a-Service**

A research-and-engineering project that builds, validates, and deploys an FS-MPC-based microgrid converter fleet under a centralized controller and a digital-twin observer. Owns the simulation programme, the cross-tool adapter layer, and the topology library.

> **Mission.** Use *every accessible* simulation tool (Python, MATLAB/Simulink, OpenModelica, PSCAD, PowerFactory, pandapower, PyPSA, OpenDSS) to validate a single canonical FS-MPC + CMC + DT control stack across a *catalogue* of microgrid topologies (CIGRE, IEEE, real-world templates).

---

## Folder layout

```
MPC_Microgrid_DTaaS/
├── README.md                                     # this file
├── VSCODE_CLAUDE_PROMPTS.md                      # curated prompts for VS Code Claude
├── PROJECT_PLAN.md                               # near-term roadmap (next 90 days)
├── fs_mpc_microgrid/                             # the working Python codebase (57 tests)
│   └── (existing src/, tests/, scripts/, docker/, figures/)
├── references/                                   # 10 Tier-1 PDFs (was ~/Desktop/fs_mpc_refs/)
├── docs/                                         # analysis docs, lit review, plans, reports
│   ├── FS_MPC_Microgrid_Forensic_Analysis.md
│   ├── FS_MPC_Microgrid_Literature_Review_IEEE.pdf
│   ├── FS_MPC_Centralized_MG_DT_Implementation_Plan.pdf
│   ├── FS_MPC_Phase_1_2_3_Implementation_Report.pdf
│   └── FS_MPC_Simulation_Studies_Plan.pdf
├── topologies/                                   # microgrid topology catalogue (next sprint)
│   ├── README.md
│   ├── cigre_mv_residential.py                   # CIGRE benchmark MV residential
│   ├── cigre_mv_industrial.py                    # CIGRE benchmark MV industrial
│   ├── ieee_13_bus.py                            # IEEE 13-bus
│   ├── ieee_33_bus.py                            # IEEE 33-bus radial (your APPEEC paper case)
│   ├── ieee_34_bus.py                            # IEEE 34-bus
│   └── campus_dc_microgrid.py                    # NUS / IIT-M campus templates
├── adapters/                                     # cross-tool adapters (next sprint)
│   ├── README.md
│   ├── matlab_simulink/                          # via `matlab.engine`
│   ├── openmodelica_fmi/                         # via `OMPython` + FMPy
│   ├── pscad/                                    # via Python automation hooks
│   ├── powerfactory/                             # via PFPy
│   ├── pandapower/                               # native Python
│   ├── pypsa/                                    # native Python
│   └── opendss/                                  # via opendssdirect.py
├── studies/                                      # the 25-study programme outputs
│   ├── A_baseline/
│   ├── B_sensitivity/
│   ├── C_coordination/
│   ├── D_faults/
│   ├── E_dt_validation/
│   └── F_realtime/
└── deliverables/                                 # paper figures, thesis figures, dashboards
```

---

## What's in `fs_mpc_microgrid/` (already built — Phases 1 to 3)

| Capability | Module |
|---|---|
| 8-vector FS-MPC inner loop with delay compensation | `inner_fsmpc.py` |
| Energy-domain DC-link PI | `outer_energy_pi.py` |
| Three-phase positive-sequence SOGI-PLL | `pll.py` |
| 6-pulse rectifier (120°-conduction) load | `rectifier_load.py` |
| Plant + RK4 integrator | `plant.py` |
| ICA agent (pub/sub-facing) | `ica_agent.py` |
| MQTT + InMemory broker abstraction | `comm/` |
| Centralized microgrid controller | `cmc/` |
| Digital twin (shadow + RLS + anomaly + cyber + forecast) | `dt/` |
| Static HTML operator dashboard | `dashboard/` |
| Docker stack (Mosquitto + ICAs + CMC + DT) | `docker/` |
| 57 passing tests | `tests/` |

---

## Software inventory (what each adapter unlocks)

| Tool | Adapter folder | Use case |
|---|---|---|
| **MATLAB / Simulink** | `adapters/matlab_simulink/` | Vendor-validated PE blocks; co-sim with the Python FS-MPC inner loop. |
| **OpenModelica + FMI** | `adapters/openmodelica_fmi/` | Open EMT replica for the DT shadow. Replaces our Python `ShadowPlant`. |
| **PSCAD / EMTDC** | `adapters/pscad/` | Industry-standard EMT for paper-grade results. Python-driven via PSCAD automation. |
| **DIgSILENT PowerFactory** | `adapters/powerfactory/` | Grid-side studies (LVRT, fault propagation, protection coordination). |
| **pandapower** | `adapters/pandapower/` | Steady-state load flow / OPF on the same topology spec. |
| **PyPSA** | `adapters/pypsa/` | Capacity expansion + economic dispatch over the same buses. |
| **OpenDSS / dss-python** | `adapters/opendss/` | Fast unbalanced QSTS (quasi-static time-series). |
| **Typhoon HIL / OPAL-RT** | `adapters/hil/` (Phase 4) | Real-time hardware-in-loop validation. |
| **Eclipse Mosquitto** | `docker/mosquitto/` | Already in the stack. |

---

## Topology catalogue (what the adapter layer iterates over)

| Topology | Buses | DERs | Load profile | Source |
|---|---:|---|---|---|
| CIGRE MV residential | 11 | 2 PV + 1 wind + 1 BESS | Residential daily curve | CIGRE TF C6.04.02 |
| CIGRE MV industrial | 7 | 2 PV + 1 BESS | Mixed P/Q + 6-pulse rectifier | CIGRE TF C6.04.02 |
| IEEE 13-bus | 13 | 1 PV + 1 BESS | Unbalanced commercial | IEEE PES |
| IEEE 33-bus | 33 | 4 PV + 2 BESS | Radial distribution | Baran-Wu |
| IEEE 34-bus | 34 | 3 PV + 1 BESS | Long radial feeder | IEEE PES |
| Campus DC microgrid | 6 | 2 PV + 1 BESS + 1 EV | Hybrid AC/DC | NUS PSCL / IIT-M |

Each topology is a Python module that returns a `Topology` graph compatible with `fs_mpc_mg.cmc.Topology`. The adapter layer translates that graph into the native format of each tool (Simulink subsystem, Modelica package, PSCAD project, etc.).

---

## Quick start (Windows + VS Code)

```powershell
cd "C:\Users\Anoop Eluvathingal\OneDrive\Desktop\SAMBPS -DTaaS ALL Files\SAMBPS DTaaS\SAMS\MPC_Microgrid_DTaaS\fs_mpc_microgrid"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev,mqtt]
pytest -q                                 # → 57 passed
python scripts\run_loading_mode.py        # → figures\loading_mode.png
```

---

## Where to go next

Open `VSCODE_CLAUDE_PROMPTS.md` and copy any prompt into VS Code's Claude pane. Each prompt is self-contained and produces an artefact (file, figure, test, or report).
