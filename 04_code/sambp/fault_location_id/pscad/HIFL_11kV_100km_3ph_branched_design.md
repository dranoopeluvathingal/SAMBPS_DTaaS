# PSCAD case `HIFL_11kV_100km_3ph_branched.pscx` — design document (WP3.2)

This document describes the **branched** extension of the WP3.1
single-radial 3-phase case `HIFL_11kV_100km_3ph.pscx`.  The same
authoring constraint applies: PSCAD itself is not on the dev box,
so this design doc is the reviewable artefact while
`pscad/HIFL_11kV_100km_3ph_branched.pscx` itself is authored on
the lead engineer's licensed Windows station per
`pscad/README_manual_run.md` (extended for the branched topology
when PSCAD is in scope).

The design here is mirrored (independent numerical pathway) by the
surrogate [`tools/pscad_surrogate_3ph_branched.py`](../tools/pscad_surrogate_3ph_branched.py),
which is what produces [`data/pscad_branched_720.mat`](../data/pscad_branched_720.mat)
on the dev box pending the canonical PSCAD output.

## Topology

```
                  tap (at tau * L_main from sender;
                       default tau = 0.5)
                    |
   sender ----*----+----*---- open far-end           (main feeder, L_main = 100 km)
                    |
                    | lateral (L_lat = 20 km)
                    |
                    +---- DG bus (at dg_pos * L_lat from tap;
                    |             default dg_pos = 0.5)
                    |
                    +---- tap_load (at lateral end)
```

`*` = candidate fault locations.  The `fault_branch` axis selects
between **main** and **lateral**; the `alpha` axis is per-unit on the
chosen branch from sender (main) or from the tap (lateral).

## Per-unit-length parameters

Same as WP3.1 (`pscad/HIFL_11kV_100km_3ph_design.md` Tab. 1):
fully transposed 3-phase line; `Z'_abc = Z'_s I + Z'_m (J - I)`
and `Y'_abc` analogously, with diagonal values from Saha 2010
Springer Tab. 3.1 and mutual ratios (5 % R, 40 % L, 30 % C) from
Kersting 2002 Tab. 4.1 IEEE-13 line code 601.

## Lateral / DG / tap-load parameters

See [`docs/feeder_assumptions.md`](../docs/feeder_assumptions.md) for
the parameter table with provenance.  Headline defaults:

| Element | Default | Brief justification |
|---|---|---|
| Lateral length | 20 km | Typical 11 kV sub-feeder |
| DG | 1 MVA, 0.95 pf, X″<sub>d</sub>=0.20 pu, R=0.05 pu | Per WP3.2 brief |
| DG position on lateral | 0.5 (mid-point) | Per WP3.2 brief |
| Tap load | 1 MW + j 0.5 Mvar at lateral end | Author choice; documented |
| DG coupling transformer | 1:1 ideal (lumped into Z_dg) | Real transformer at WP3.3 |

## Fault model (unchanged from WP3.1)

* **Type:** Single-line-to-ground (SLG) HIF.
* **Faulted phase:** A.
* **Arc resistance R_x:** sweep R_x ∈ {100, 500, 1000, 2000, 5000} Ω.
* **Position α:** {0.10, 0.20, …, 0.90}, per-unit on the chosen
  `fault_branch`.
* **Arc model:** anti-parallel diode pair, same provenance as WP1.1
  (Aucoin–Russell 1987; `TODO arc-provenance` carried forward).

## Boundary conditions

* **Source:** balanced 3-phase ideal voltage source at the sender
  substation (zero source impedance for the WP3.2 acceptance check;
  WP3.6 lifts to a finite Thévenin source impedance).
* **Open far-end on main:** 1 MΩ shunt to ground per phase.
* **Tap load:** constant impedance `Z_load = 32 + j 16 Ω/phase`
  (balanced; constant-power / ZIP loads at WP3.4).
* **DG:** Thévenin source `V_dg` behind `Z_dg = 2 + j 8 Ω/phase`;
  the source amplitude / phase angle is left at "balanced 11 kV phase
  voltage in phase with the substation source" and is not
  parameterised in the WP3.2 surrogate (only `Z_dg` enters Y_send).

## Measurement scheme (unchanged from WP3.1)

* **Sampling:** F_s = 10 kHz, N_s = 200 samples per cycle, one 50 Hz
  cycle window. Same as WP1.1 / WP3.1.
* **CT/PT:** ideal at the sending end; single-bin DFT yields the 3×3
  Y_send the IED estimator consumes.
* **Dual-channel AWGN:** SNR_V ∈ {20, 30, 40, ∞} dB, SNR_I ∈ {20, 30,
  40, ∞} dB; per-phase i.i.d. realisations.

## Parametric sweep — 1440-grid

| Axis | Values | Count |
|---|---|---|
| α | 0.10, 0.20, …, 0.90 | 9 |
| R_x [Ω] | 100, 500, 1000, 2000, 5000 | 5 |
| SNR_V [dB] | 20, 30, 40, ∞ | 4 |
| SNR_I [dB] | 20, 30, 40, ∞ | 4 |
| `fault_branch` | main, lateral | 2 |
| | **total** | **1440** |

The grid is 9·5·4·4·2 = 1440 cells. The bundle filename retains the
`_720.mat` suffix for schema-family consistency with WP1.1 / WP3.1
(720 was the historical headline; the brief calls this an
"extension of the 720-grid").

## Output bundle schema — `data/pscad_branched_720.mat`

| Key | Shape | dtype | Units | Description |
|---|---|---|---|---|
| `Y_send` | (1440, 3, 3) | complex | siemens | Noiseless 3×3 sending-end admittance per cell |
| `grid_alpha` | (1440,) | float | per unit | Per-unit fault position on chosen branch |
| `grid_Rx` | (1440,) | float | Ω | Arc resistance |
| `grid_SNR_V` | (1440,) | float | dB | Voltage-channel SNR (∞ = noiseless) |
| `grid_SNR_I` | (1440,) | float | dB | Current-channel SNR (∞ = noiseless) |
| `grid_fault_branch` | (1440,) | str | — | "main" or "lateral" (whitespace-padded by scipy) |
| `meta` | dict | str | — | Schema version, network parameters, comments |

## Cross-validation pointers

* [`tools/pscad_surrogate_3ph_branched.py`](../tools/pscad_surrogate_3ph_branched.py)
  — Python 50-sections-per-segment lumped-Π surrogate; uses the
  same `Network` reduction as the closed-form, with the line ABCD
  per segment swapped via the `line_abcd_fn` override hook.
* [`tests/test_branched_vs_pscad.py`](../tests/test_branched_vs_pscad.py)
  — asserts |closed-form Y_send| agreement with |surrogate Y_send|
  to within 5 % on every entry of the 3×3 matrix at every (α, R_x,
  fault_branch) cell of the 1440-grid (noiseless slice only).
* [`models/faultloc_three_phase_model.py`](../models/faultloc_three_phase_model.py)
  — closed-form `Network` class with `Y_send` reduction.
* [`docs/feeder_assumptions.md`](../docs/feeder_assumptions.md) —
  parameter rationale + open-question log.

WP3.3 replaces the canonical `HIFL_11kV_100km_3ph_branched.pscx`
with the IEEE 13-node feeder; per-branch parameters move from this
design doc into Kersting 2002-derived line-code tables consumed by
`models/faultloc_ieee_feeders.py`.
