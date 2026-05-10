# `pscad/wang2020_arc/` — Wang-2020 distortion-controllable HIAF (WP4.3)

This directory hosts the Wang-2020 distortion-controllable HIAF
PSCAD reference component (DistC-HIAF), authored on the lead
engineer's licensed Windows station per the workflow in
[`pscad/README_manual_run.md`](../README_manual_run.md).

## Status — vendor pending

The canonical PSCAD case `wang2020_arc.pscx` and the upstream
EMTDC FORTRAN sources are **not vendored in this commit**.

* Upstream open-source reference:
  https://github.com/MingjieWei/PSCAD-FILE-DISTC-HIAF-Model
* Reference paper: Wang, Yang & Bo, "A distortion-controllable
  high-impedance arc fault model for renewable-penetrated
  distribution networks", IEEE Trans. Power Delivery, 2020.

The fetch was attempted on 2026-05-10 from the dev-box but was
**blocked by the SAMBPS-DTaaS safety hook** (Untrusted Code
Integration policy: a third-party GitHub repository is being
vendored for downstream execution as PSCAD model code).  The
fetch is queued for the lead engineer's licensed Windows runner,
where the upstream sources can be reviewed manually under the
permitted vendoring policy and the LICENSE / CITATION files
inspected before commit.

When vendored, this directory will additionally contain:

* `wang2020_arc.pscx` — canonical PSCAD case, parameterised by
  `distortion_index in [0, 1]`.
* `wang2020_arc.f` — EMTDC FORTRAN source for the distortion-zone
  per-half-cycle randomisation logic.
* `LICENSE` — upstream license (verbatim copy from the upstream
  repo `LICENSE` file at fetch time, with attribution preserved).
* `CITATION.cff` — upstream citation file plus our wrapping
  attribution.
* `MANIFEST.sha256` — vendored-file checksums.

Until vendored, the **Python surrogate** `Wang2020Arc` in
[`models/faultloc_arc_models.py`](../../models/faultloc_arc_models.py)
is the reference dev-box implementation.  The surrogate matches
the Wang-2020 specification in three observable ways:

1. **Per-half-cycle distortion zone**: fresh `OFFSET`, `EXTENT`,
   `DURATION` drawn each half-cycle, scaled by a global
   `distortion_index in [0, 1]`.
2. **Inter-cycle harmonic variance**: the 3rd-harmonic DFT-bin
   amplitude exhibits inter-trial variance > 5x the deterministic
   Emanuel diode baseline (covered by
   [`tests/test_wang2020_randomness_signature.py`](../../tests/test_wang2020_randomness_signature.py),
   §4).
3. **Determinism limit**: `distortion_index = 0` reproduces the
   Emanuel baseline exactly.

## Canonical PSCAD model spec (when vendored)

* Three-phase distortion-controllable arc model attached at the
  fault bus of the canonical PSCAD case `IEEE_34.pscx`
  (per [`pscad/IEEE_34_design.md`](../IEEE_34_design.md)).
* Per-half-cycle randomisation parameters drawn at solver-step
  granularity using PSCAD's built-in random number sources
  seeded by the case-level Monte-Carlo trial index.
* Output channel: arc current `i_arc(t)` measured between the
  fault-bus phase-A node and ground, sampled at the case rate
  (10 kHz), exported to a `.mat` bundle with the same schema as
  [`data/ieee34_720.mat`](../../data/ieee34_720.mat) plus an
  added trial axis (matches the dev-box bundle
  [`data/wang2020_ieee34_720.mat`](../../data/wang2020_ieee34_720.mat)).

## Output bundle schema — `data/wang2020_ieee34_720.mat`

Mirrors `data/ieee34_720.mat` (per
[`pscad/IEEE_34_design.md`](../IEEE_34_design.md)) with one
additional axis:

| Variable          | Shape                                       | Notes                                            |
|-------------------|---------------------------------------------|--------------------------------------------------|
| `V`               | `(n_trials, n_cells, N_samples)`            | Phase-A bus voltage waveforms                    |
| `I_emanuel`       | `(n_trials, n_cells, N_samples)`            | Baseline Emanuel diode arc current               |
| `I_wang2020`      | `(n_trials, n_cells, N_samples)`            | Wang-2020 distortion-controllable arc current    |
| `grid_alpha`      | `(n_cells,)`                                | Per-cell true normalised fault location          |
| `grid_Rx`         | `(n_cells,)`                                | Per-cell true arc resistance                     |
| `grid_SNR_V`      | `(n_cells,)`                                | Voltage-channel SNR (dB)                         |
| `grid_SNR_I`      | `(n_cells,)`                                | Current-channel SNR (dB)                         |
| `grid_fault_bus`  | `(n_cells,)`                                | Per-cell fault-bus label                         |
| `meta`            | dict                                        | Schema version, `f0_hz`, `fs_hz`, `n_trials`, … |

The dev-box surrogate sub-samples to `n_buses = 5`,
`n_trials = 20`, and `SNR_I >= 30 dB` (see the runner
[`run_faultloc_phase4_wang2020.py`](../../run_faultloc_phase4_wang2020.py)
docstring for the rationale).  The full IEEE 34 720-grid x 100
MC trials canonical run is **deferred to the licensed Windows
runner**.
