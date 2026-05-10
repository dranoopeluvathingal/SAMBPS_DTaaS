# Related References for FS-MPC Microgrid Reproduction
**Source folder scanned:** `G:\My Drive\anoop seminar 2\1 PROJ REF` (Drive folder ID `1_y3CkY2xsem6QVMDHynU7QiTx98PFG7i`)
**Target paper being reproduced:** Perez & Flores-Bahamonde 2016, FS-MPC of Microgrid Interface Converters
**Date of scan:** 2026-04-26

---

## Critical finding — coverage gap

**No FS-MPC / predictive control paper for power electronics exists in your drive.** The only MPC paper found across the entire `1 PROJ REF` tree is `A_Model_Predictive_Control_Algorithm_for_large-scale_Integration_of_Electromobility.pdf` — about EV scheduling, not converter control. Implications:

- Your local library is rich in **inverter modelling, smart-inverter Volt-VAR/Volt-Watt, droop-based reactive control, voltage regulation, and microgrid mode-handling** — all directly useful for the *plant model, reference generation, and outer-loop context* of the Perez paper.
- It is **lean on inner-loop predictive-current-control theory** (the heart of Perez's contribution). You will need to fetch 4-6 external references (listed at the end as "external gap fillers") before reproducing the inner FS-MPC loop with confidence.

---

## Tier 1 — Direct hits (closest to the target paper's themes)

These are the papers that most directly support reproduction. Each row is mapped to the exact section of the Perez paper it strengthens.

| # | Title | Drive folder | Why it matters | Strengthens |
|---|---|---|---|---|
| 1 | **An Adoptive Droop Method for Local Reactive Power Compensation in an MV Microgrid** | new collections | Reactive-Q compensation in a microgrid context — alternative to Perez's FS-MPC approach | §1 motivation, §3.B outer loop |
| 2 | **A Hybrid Estimator for Active/Reactive Power Control of Single-Phase Distributed Generation Systems With Energy Storage** | new collections | Power estimation feeding controller refs — adjacent technique | §3.B reference generation |
| 3 | **Steady-State Model and Power Flow Analysis of Electronically-Coupled Distributed (Sources)** | new collections | Plant model of grid-tied inverter — direct modeling reference | §2 plant equations (1)(2) |
| 4 | **Modeling and Simulation of Three Phase Inverter for Fault Study in Microgrids** | new collections | 3-phase VSI modeling with switching states | §2.B `M` matrix, switching vectors |
| 5 | **Modelling and Control of Hybrid AC/DC Microgrid — A Thesis** | new collections | DC bus + AC bus joint modeling — exactly Perez's topology | §2 entire model |
| 6 | **Review of Multifunctional Inverter Topologies and Controls** (appears in 4 IIDG + 7 SMART INVERTER) | 4 IIDG / 7 SMART INV | "One inverter, multiple functions" thesis = Perez's central premise | §1 motivation; framing your literature review |
| 7 | **1 MOST REFFERED PAPER — OVERVIEW OF CONTROL TECHNOLOGIES** (Blaabjerg/Teodorescu-style) | 4 IIDG | Canonical overview of grid-tied inverter control taxonomy — places FS-MPC in context | Background; introduction |
| 8 | **Control for Grid-Connected and Intentional Islanding** (appears in 4 IIDG + 9 ISLANDED) | 4 IIDG / 9 ISLANDED | Mode-handling — Perez's "loading / regen / zero" closely echoes this | §3 mode-agnostic operation |
| 9 | **Reconfigurable Control Scheme for a PV Microinverter Working in Both Grid-Connected and Island Modes** | 9_ISLANDED OPERATION | Cross-mode control — useful contrast with Perez's no-mode-switch approach | §3 controller architecture |
| 10 | **Defining Control Strategies for MicroGrids** | 9_ISLANDED OPERATION | Foundational microgrid control taxonomy | §1 motivation; Ch1 of your thesis |

---

## Tier 2 — Plant modelling and reference design (helps build `plant.py` and `pll.py`)

These tighten the plant model and PLL implementation in your reproduction project.

| # | Title | Drive folder | Specifically helps |
|---|---|---|---|
| 11 | **NREL Advanced Power Electronic** | 4 IIDG Controller Design | DC-link cap sizing, switching dynamics |
| 12 | **1 Important NREL grid tied inverters** | 4 IIDG Controller Design | NREL reference grid-tied design — sanity-check parameters |
| 13 | **Thesis inverter controller design** | 4 IIDG Controller Design | Full-text inner controller derivations — Forward-Euler discretisation |
| 14 | **Modelling and simulation of grid connected inverter (NIT Rourkela thesis)** | 4 IIDG Controller Design | Detailed Simulink-style implementation reference |
| 15 | **a CURRENT LIMITING sTRATEGY DURING FAULT 2019** | 4 IIDG Controller Design | Inner-loop reference saturation — useful for your robustness extension |
| 16 | **a noval protection scheme with inverter controller design** | 4 IIDG Controller Design | Protection-aware controller design |
| 17 | **5_NREL Fault models of different renewable sources** | 4 IIDG Controller Design | Source models behind `i_dc` |
| 18 | **GRID CONNECTED PV / Power Inverter Topologies for** | 4 IIDG Controller Design | Topology baselines |
| 19 | **A cell-to-module-to-array detailed model for photovoltaic panels** | 4 IIDG Controller Design | If you upgrade from "DC current source" to a real PV model |

---

## Tier 3 — Smart-inverter / Volt-VAR (for context and APPEEC paper #2 cross-reference)

These contextualize Perez's work within the broader smart-inverter movement (IEEE 1547-2018, Volt-VAR control). Very useful for your *literature review* but not strictly needed for the simulation reproduction.

| # | Title | Drive folder |
|---|---|---|
| 20 | **1 NREL Photovoltaic Impact Assessment of Smart Inverter Volt-VAR Control** | 7 SMART INVERTER |
| 21 | **1 NREL Application of SMART INVERTER ISGT** | 7 SMART INVERTER |
| 22 | **NREL advanced inverter technology for high penetration** | 7 SMART INVERTER |
| 23 | **0d Vasco — Unbundled smart inverter** | 7 SMART INVERTER |
| 24 | **0b Masha — Smart inverter volt watt control** | 7 SMART INVERTER |
| 25 | **2_Options for control of reactive power** | 8 Voltage regulation |
| 26 | **3_Local Control of Reactive Power by PV** | 8 Voltage regulation |
| 27 | **4_standardlanguage** (likely IEEE 1547 / DER std) | 8 Voltage regulation |

---

## Tier 4 — Microgrid context / multi-mode / agent integration (for thesis Chs 1–3 and MAS-DT-SH)

These tie the FS-MPC controller into the larger MAS-DT-SH narrative — useful when you wrap the controller as an "Interface Converter Agent."

| # | Title | Drive folder |
|---|---|---|
| 28 | **Energy Management and Control of Microgrid using Multi-Agent Systems** | new collections |
| 29 | **Co-ordination and control of Multiple Microgrids Using Multi Agent Techniques** | new collections |
| 30 | **Distributed Cooperative Control of Microgrid Storage** | new collections |
| 31 | **Distributed Intelligent Control of DER and LV Loads in Microgrids** | new collections |
| 32 | **Autonomous Control of Microgrids** | new collections |
| 33 | **A Self-Organizing Architecture for Decentralized Smart Microgrids** | new collections |
| 34 | **Advanced Architecture and Control Concepts for More Microgrids** | new collections |
| 35 | **Microgrids in active network management — Part I (Hierarchical)** | new collections |
| 36 | **Microgrids in active network management — Part II (System Operation, PQ, Protection)** | new collections |
| 37 | **MICROGRID definition (Lasseter)** | 1 Arranged References / MAIN REFERENCES |
| 38 | **Benchmark microgrid IEEE** | 1 Arranged References / MAIN REFERENCES |

---

## Tier 5 — Tangential (don't waste time unless extending)

`POWER QUALITY SEMINAR` folder mostly contains voltage-control papers (06298062.pdf, 06634276.pdf, 06512639.pdf, etc.) that focus on distribution-side voltage management rather than converter-side current control. Skip for FS-MPC reproduction; revisit if you extend to grid voltage support.

`13 Machine Learning`, `12 Artificial Intelligence`, `10 Big Data Analysis` — irrelevant to this reproduction.

---

## External gap-fillers you must fetch (not in your drive)

These are required for a thesis-quality FS-MPC reproduction and are **not present** in `1 PROJ REF`:

| # | Reference | Why |
|---|---|---|
| G1 | **Kouro, Perez, Rodriguez, Llor, Young** — *Model Predictive Control: MPC's Role in the Evolution of Power Electronics*, IEEE Ind. Electron. Mag. 9(4), 2015 | Cited as [24] in Perez paper; delay compensation derivation |
| G2 | **Rodriguez, Cortes** — *Predictive Control of Power Converters and Electrical Drives* (Wiley, 2012) | Foundational FS-MPC textbook |
| G3 | **Cortes, Kazmierkowski, Kennel, Quevedo, Rodriguez** — *Predictive Control in Power Electronics and Drives*, IEEE Trans. Ind. Electron. 55(12), 2008 | Survey paper, cost-function design patterns |
| G4 | **Geyer** — *Model Predictive Control of High Power Converters and Industrial Drives* (Wiley, 2016) | Multi-step horizon, sphere-decoding tricks |
| G5 | **Rodriguez, Teodorescu, Candela, Timbus, Liserre, Blaabjerg** — *New positive-sequence voltage detector for grid synchronization*, IEEE PESC 2006 | Cited as [25] in Perez paper; the PLL design |
| G6 | **He, Li** — *Generalized microgrid harmonic compensation strategies using DG unit interfacing converters*, IECON 2012 | Cited as [14] in Perez paper; closest direct precedent for harmonic-compensation references |
| G7 | **Liu, Tao, Liu, Deng, He** — *Voltage unbalance and harmonics compensation for islanded microgrid inverters*, IET Power Electronics 7(5), 2014 | Cited as [13] in Perez paper |

Action: pull these from IEEE Xplore / Wiley before starting Sprint-week implementation. 30 min each on Xplore should land them.

---

## Summary by relevance band

| Band | # papers | Where to find them | Action |
|---|---|---|---|
| **Tier 1 — direct hits** | 10 | new collections (mainly), 4 IIDG, 7 SMART INV, 9 ISLANDED | **Read first.** Each is mapped to a specific Perez section above. |
| **Tier 2 — plant/PLL** | 9 | 4 IIDG Controller Design | Skim while building `plant.py` and `pll.py`. |
| **Tier 3 — smart-inverter context** | 8 | 7 SMART INV, 8 Voltage Regulation | For your thesis lit review and APPEEC #2 framing. |
| **Tier 4 — MAS/multi-mode context** | 11 | new collections, 1 Arranged References | Use when wrapping as Interface Converter Agent. |
| **Tier 5 — tangential** | (~30+) | POWER QUALITY SEMINAR, 13 ML, 12 AI | Skip for this reproduction. |
| **External gap fillers** | 7 | Not in drive — fetch from IEEE/Wiley | **Required** for proper FS-MPC inner-loop theory. |

---

## Recommended reading order (one week before scaffolding the project)

| Day | Read | Goal |
|---|---|---|
| Mon | Tier 1 #6, #7, #10 (overview + multifunctional inverter + microgrid taxonomy) | Place Perez in the literature |
| Tue | Tier 1 #3, #4, #5 (modelling refs) + Tier 2 #11, #13 | Internalize the plant model |
| Wed | External G1, G2 (Kouro 2015 + Rodriguez/Cortes Ch 1-3) | Master FS-MPC inner loop |
| Thu | External G5 (Rodriguez 2006 PLL) + Tier 1 #1, #2 | Lock down PLL + reference generation |
| Fri | Tier 1 #8, #9 + Tier 4 #28-31 | Frame the multi-mode + agent narrative |
| Sat | Synthesis: open scaffolding for `fs_mpc_microgrid/` per yesterday's plan | Begin implementation |

---

*All Drive view URLs are in the corresponding search results — say "give me the Drive links" and I'll emit the full clickable list per tier.*
