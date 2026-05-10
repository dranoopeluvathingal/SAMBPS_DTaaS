# PSCAD case `IEEE_13.pscx` — design document (WP3.3)

This document describes the IEEE 13-node test feeder PSCAD case, the
WP3.3 extension of the WP3.1 single-radial 3-phase
`HIFL_11kV_100km_3ph.pscx`. PSCAD is not on the dev box; the
canonical `pscad/IEEE_13.pscx` is authored on the lead engineer's
licensed Windows station per [`pscad/README_manual_run.md`](README_manual_run.md)
(extended for IEEE feeder topologies when in scope).

The dev-box surrogate that produces [`data/ieee13_720.mat`](../data/ieee13_720.mat)
is [`tools/ieee_feeder_surrogate.py`](../tools/ieee_feeder_surrogate.py),
which reuses the closed-form
[`IEEEFeederNetwork`](../models/faultloc_ieee_feeders.py) reduction
with a 50-section lumped-π line ABCD per segment (the same
independent-pathway pattern as WP3.1 / WP3.2).

## Topology

13 named buses per Kersting (2002) Tab. 4.5:

| Bus | Phases | Notes |
|---|---|---|
| 650 | A B C | Source substation; 4.16 kV LL |
| 632 | A B C | Main bus, lateral takeoff for 633/645/671 |
| 633 | A B C | Mid-feeder spur to 634 via XFM-1 transformer |
| 634 | A B C | Step-down to 0.48 kV via XFM-1 |
| 645 | _ B C | Two-phase lateral |
| 646 | _ B C | Two-phase lateral end (load) |
| 671 | A B C | Heavy load bus |
| 692 | A B C | 671→692 switch (closed) |
| 675 | A B C | End of 692→675 spur |
| 680 | A B C | 671→680 spur |
| 684 | A _ C | Two-phase spur from 671 |
| 611 | _ _ C | Single-phase C lateral end |
| 652 | A _ _ | Single-phase A lateral end |

12 branches per Kersting Tab. 4.5 with line codes 601 (overhead 3-φ),
602 (3-φ underground), 603/604 (2-φ overhead), 605 (1-φ overhead),
606 (3-φ underground concentric), 607 (1-φ underground).

## Per-unit-length line codes

Kersting Tab. 4.4. See
[`models/faultloc_ieee_feeders.py`](../models/faultloc_ieee_feeders.py)
for the full Z_abc and Y_abc matrices (untransposed; in Ω/mile and
µS/mile respectively, converted to per-km in code).

## Loads

Kersting Tab. 4.7 spot loads at buses 634 / 645 / 646 / 671 / 675 /
692 / 611 / 652 (mixed PQ + Z + I per bus per phase). See
[`docs/ieee_feeders_assumptions.md`](../docs/ieee_feeders_assumptions.md)
for the WP3.3 simplifications (constant-Z only this commit).

## Regulators and capacitor banks

* RG60 voltage regulator at 650 (taps 10/8/11 per Kersting Tab. 4.6).
* Capacitor banks at 611 (100 kvar single-phase C) and 675 (200 kvar
  per phase, 600 total).
* All deferred to the WP3.3 follow-up commit.

## Transformer XFM-1

In-line transformer between 633 and 634 (4.16 kV → 0.48 kV; per
Kersting Tab. 4.5 sub-table). Deferred.

## Fault model (unchanged from WP3.1)

* **Type:** SLG-HIF on phase A (other fault types at WP3.4).
* **Location:** at α = 0.5 of the line into the chosen bus (per
  WP3.3 brief: "place the fault at every node at α=0.5 of the line
  into the node").
* **Arc resistance R_x:** sweep R_x ∈ {100, 500, 1000, 2000, 5000} Ω.

## Boundary conditions

* **Source:** balanced 3-phase ideal voltage source at 650 (no source
  impedance; finite Thévenin source impedance at WP3.6).
* **Far-ends:** open termination at all leaf buses.
* **Loads:** see "Loads" above.

## Measurement scheme (unchanged)

* F_s = 10 kHz, N_s = 200, one 50 Hz cycle.
* CT/PT ideal at the source 650.
* Single-bin DFT yields the 3×3 Y_send the IED estimator consumes.
* Dual-channel AWGN: SNR_V ∈ {20, 30, 40, ∞} dB, SNR_I same.

## Parametric sweep — 960-grid

12 fault buses × 5 R_x × 4 SNR_V × 4 SNR_I = 960 cells. The bundle
file name retains the `_720.mat` convention from WP1.1 / WP3.1 /
WP3.2.

## Output bundle schema — `data/ieee13_720.mat`

| Key | Shape | dtype | Units | Description |
|---|---|---|---|---|
| `Y_send` | (960, 3, 3) | complex | siemens | Noiseless 3×3 sending-end admittance per cell |
| `grid_alpha` | (960,) | float | per unit | Fault position on the line into the bus (always 0.5 in WP3.3) |
| `grid_Rx` | (960,) | float | Ω | Arc resistance |
| `grid_SNR_V` | (960,) | float | dB | Voltage-channel SNR |
| `grid_SNR_I` | (960,) | float | dB | Current-channel SNR |
| `grid_fault_bus` | (960,) | str | — | Fault-bus name (e.g., "632", "671") |
| `meta` | dict | str | — | Schema version, feeder name, comments |

## Cross-validation pointers

* [`tools/ieee_feeder_surrogate.py`](../tools/ieee_feeder_surrogate.py)
  — generates the bundle.
* [`tools/build_ieee13_powerflow_report.py`](../tools/build_ieee13_powerflow_report.py)
  — produces [`outputs/phase3_ieee_feeder_powerflow.csv`](../outputs/phase3_ieee_feeder_powerflow.csv).
* [`tests/test_ieee_feeders_powerflow.py`](../tests/test_ieee_feeders_powerflow.py)
  — runs the comparison vs Kersting Tab. 4.10.
* [`docs/ieee_feeders_assumptions.md`](../docs/ieee_feeders_assumptions.md)
  — what's deferred and why.
