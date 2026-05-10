# PSCAD case `HIFL_11kV_100km_3ph.pscx` — design document (WP3.1)

This document describes the **three-phase** extension of the WP1.1 single-phase
case `HIFL_11kV_100km.pscx`. PSCAD itself is a proprietary Windows simulator
(Manitoba Hydro International) and is not installed on the dev box, so this
design doc is the reviewable artefact while `pscad/HIFL_11kV_100km_3ph.pscx`
itself is authored on the lead engineer's licensed Windows station per
`pscad/README_manual_run_3ph.md`.

The schematic-level documentation here is the source of truth for the WP3.1
3-phase model and is mirrored (independent numerical pathway) by the surrogate
`tools/pscad_surrogate_3ph.py`, which is what produces
`data/pscad_3ph_720.mat` on the dev box pending the canonical PSCAD output.

## Topology

```
            Z'_abc, Y'_abc per km
            (3-phase symmetric overhead)
  +--------+   alpha · L          (1-alpha) · L
  | Source |---------------+---------------+----+--+
  | (Th.)  |               |               |       open
  +--------+               R_x (phase A)   R_load
                           SLG-HIF         to ground
                           shunt to
                           ground
```

* **Line length:** L = 100 km (same as the WP1.1 single-phase case).
* **Per-phase model:** Frequency-Dependent (Phase) Model in PSCAD; equivalent
  to the J. Marti FD line in EMTP-RV. The dev-box surrogate uses a
  50-sections-per-side lumped-Π reduction, justified by Saha 2010 Ch. 3.
* **Per-unit-length impedance Z'_abc and shunt admittance Y'_abc:**
  symmetric (transposed-line) approximation:

```
  Z'_abc = Z'_s · I_3 + Z'_m · (J_3 - I_3)
  Y'_abc = Y'_s · I_3 + Y'_m · (J_3 - I_3)
```

  with parameter values (matching `models/faultloc_three_phase_model.py`):

| Quantity | Self | Mutual | Source |
|---|---|---|---|
| R' (Ω/km) | 0.0728 | 0.00364 (= 0.05·R'_s) | Saha 2010 Springer Tab. 3.1 |
| L' (mH/km) | 0.927 | 0.371 (= 0.40·L'_s) | Saha 2010 Springer Tab. 3.1 |
| C' (nF/km) | 11.6 | 3.48 (= 0.30·C'_s) | Saha 2010 Springer Tab. 3.1 |
| G' (S/km) | 0 | 0 | (lossless shunt) |

The mutual ratios (5 % R, 40 % L, 30 % C) are typical of an 11 kV
horizontal-flat-array overhead line with three phase conductors
(Kersting 2002, IEEE 13-node line code 601 after Kron reduction and
post-transposition averaging). The transposed-line assumption is documented
in §II.B of `docs/manuscript_v2.tex` (revision pending; lands at WP3.x in
the IEEE Access response v2 once reviewer comments arrive). Untransposed
Carson coupling is deferred to WP3.2.

## SLG-HIF fault

* **Type:** Single-line-to-ground (SLG) high-impedance fault.
* **Location:** at per-unit position α from the sender (α ∈ {0.10, 0.20,
  ..., 0.90}, 9 values).
* **Faulted phase:** phase A.
* **Healthy phases B, C:** untouched at the fault point.
* **Arc resistance R_x:** parameter sweep R_x ∈ {100, 500, 1000, 2000,
  5000} Ω (5 values).
* **Arc model:** anti-parallel diode pair on phase A, same provenance as
  the WP1.1 single-phase case (Aucoin–Russell 1987 trace family;
  `TODO arc-provenance` carried forward — confirm against Santos-2022
  before camera-ready freezes).

## Boundary conditions

* **Source:** balanced three-phase ideal voltage source behind a
  Thévenin equivalent. Source impedance taken as 0.1 + j·0.5 Ω per phase;
  positive- and zero-sequence Thévenin parameters per the WP3.2 brief.
  In the dev-box surrogate the source is treated as ideal (zero impedance)
  to keep the comparison with the closed-form model clean; WP3.2 lifts this.
* **Far-end load:** open termination, modelled as a 1 MΩ shunt to ground
  per phase (symmetric, three-phase). Matches the WP2.1 single-phase
  open-far-end boundary condition.

## Measurement scheme

* **Sampling:** F_s = 10 kHz, N_s = 200 samples per cycle, one 50 Hz cycle
  window. Same as WP1.1.
* **CT/PT:** ideal at the sending end (sub-station bus). The single-bin DFT
  at f_0 = 50 Hz extracts V̂_a, V̂_b, V̂_c (phase-to-ground) and
  Î_a, Î_b, Î_c (line currents). The IED-observed quantity is the 3×3
  sending-end admittance matrix `Y_send` defined by `I_s = Y_send · V_s`.
* **Dual-channel AWGN:** independent additive white Gaussian noise on V
  and on I per the WP1.1 noise model, parameterised by SNR_V ∈ {20, 30,
  40, ∞} dB and SNR_I ∈ {20, 30, 40, ∞} dB (4 × 4 = 16 noise classes per
  (α, R_x) cell). Noise is injected per phase identically (same SNR; phase
  noise realisations are independent).

## Parametric sweep — 720-grid

| Axis | Values | Count |
|---|---|---|
| α | 0.10, 0.20, ..., 0.90 | 9 |
| R_x [Ω] | 100, 500, 1000, 2000, 5000 | 5 |
| SNR_V [dB] | 20, 30, 40, ∞ | 4 |
| SNR_I [dB] | 20, 30, 40, ∞ | 4 |
| | **total** | **720** |

Same shape as the WP1.1 single-phase grid so the per-cell index between
`pscad_720.mat` (single-phase) and `pscad_3ph_720.mat` is directly
comparable.

## Output bundle schema — `data/pscad_3ph_720.mat`

| Key | Shape | dtype | Units | Description |
|---|---|---|---|---|
| `Y_send` | (720, 3, 3) | complex | siemens | Noiseless 3×3 sending-end admittance per cell |
| `grid_alpha` | (720,) | float | per unit | Per-unit fault position |
| `grid_Rx` | (720,) | float | Ω | Arc resistance |
| `grid_SNR_V` | (720,) | float | dB | Voltage-channel SNR (∞ = noiseless) |
| `grid_SNR_I` | (720,) | float | dB | Current-channel SNR (∞ = noiseless) |
| `meta` | dict | str | — | Schema version, line length, fault type, comments |

**Note on schema departure from WP1.1.** The single-phase WP1.1 bundle
saved time-domain V/I waveforms (shape (720, 200) each). The 3-phase
identification problem operates on the 3×3 admittance matrix directly
rather than on per-phase waveforms, so the 3-phase bundle saves Y_send.
Noise injection in the (α, R_x) estimator path is the responsibility of
the WP3.5/WP3.6 estimator, not of the bundle.

When the canonical PSCAD run lands, V/I time-domain waveforms can be
extracted from PSCAD as a separate artefact `data/pscad_3ph_720_waveforms.mat`
if the lead engineer prefers the WP1.1 schema; the Y_send bundle remains
the canonical input for the WP3.1 acceptance test.

## Cross-validation pointers

* `tools/pscad_surrogate_3ph.py` — Python 50-sections-per-side lumped-Π
  surrogate; independent numerical pathway from
  `models/faultloc_three_phase_model.py` (which uses `scipy.linalg.expm`
  on the 6×6 system matrix).
* `tests/test_3phase_vs_pscad.py` — asserts that |closed-form Y_send|
  agrees with |surrogate Y_send| to within 5 % on every entry of the
  3×3 matrix at every cell of the 720-grid (noiseless slice only).
* `models/faultloc_three_phase_model.py` — closed-form 3-phase model.
* `pscad/README_manual_run_3ph.md` — manual-run instructions for the
  lead engineer's Windows PSCAD station.
* Cross-check on transposed-line assumption: at WP3.2, untransposed
  Carson coupling lands and the per-cell discrepancy vs the surrogate
  here is documented as the WP3.1 → WP3.2 reframing.
