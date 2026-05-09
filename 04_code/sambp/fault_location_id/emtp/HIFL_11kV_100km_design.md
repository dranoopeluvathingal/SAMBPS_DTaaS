# HIFL_11kV_100km — EMTP-RV case design

Reviewer-friendly schematic-level documentation of the canonical
EMTP-RV case `emtp/HIFL_11kV_100km.ecf`. Mirrors the PSCAD case in
`pscad/HIFL_11kV_100km_design.md`; the two are intended to be built
by **different engineers** so that human modelling habits do not
cross-contaminate the cross-simulator validation (R1 mitigation per
v3 plan §10).

## Topology — identical to the PSCAD case

```
   V_s        section 1            fault             section 2          remote
  ──────►  R1, L1, C dist.   ────────► R_x ◄────  R2, L2, C dist.   ──────  open / R_load
   |               |              |                       |
   |        CT(I_in)/PT(V_in)                             |
   |     @ 10 kHz, 200 samples,                           |
   |        one cycle window                              |
   |________ ground __________________________________ ground
```

Same source, same per-km parameters, same arc element, same noise
model, same parametric study. The only intentional difference is the
EMTP modelling implementation:

| Element | PSCAD case | EMTP-RV case |
|---|---|---|
| Line | `Frequency-Dependent (Phase) Model` (J. Marti) | `FD line model` (Marti option) |
| Solver | EMTDC (custom Manitoba HVDC engine, trapezoidal) | EMTP-RV solver (modified nodal analysis, trapezoidal) |
| Time step | 50 µs | 50 µs |
| Multiple-run | PSCAD parametric sweep | EMTP-RV "Design Tool" + ScopeView batch export |

## Source bus

* Single-phase voltage source: $V_s = (11000/\sqrt{3})\sqrt{2}\cos(2\pi f_0 t)$
  with $f_0 = 50$ Hz.

## Line — frequency-dependent (Marti option)

Per-km parameters (matched byte-for-byte with PSCAD case):

| Parameter | Value         | Units    |
|-----------|---------------|----------|
| $R'$      | 0.0728        | Ω/km     |
| $L'$      | 0.927e-3      | H/km     |
| $C'$      | 11.6e-9       | F/km     |
| $G'$      | 0.0           | S/km     |

EMTP-RV `FD line model` configured with the same Marti fitting
defaults (10 Hz – 100 kHz band, 20 fitting poles).

## HIF arc element

Anti-parallel diode (EMTP-RV `Diode_pq` block in the macro library):

| Parameter        | Value     | Units |
|------------------|-----------|-------|
| $V_{kp}$         | 50        | V     |
| $V_{kn}$         | 45        | V     |
| $R_{sp}$         | 5         | Ω     |
| $R_{sn}$         | 6         | Ω     |
| $R_{\text{off}}$ | 1.0e6     | Ω     |
| $\varepsilon$    | 1e-3      | A     |

Same `TODO arc-provenance` as the PSCAD case: confirm against
Santos-2022 before camera-ready freezes, see issue tracker
`WP4.2-prep`.

## CT and PT measurement

* PT: `V_meter` block at the source bus → channel `V_in`.
* CT: `I_meter` block in series with the source-bus tie → channel `I_in`.
* Sampling: native 50 µs, decimated to 10 kHz / 200 samples / one cycle
  by the ScopeView export macro.

## Dual-channel AWGN

* `Noise_Gauss` blocks (Powersys macro library) on V and I channels.
* Variance set so the per-cell SNR matches the PSCAD case to within
  rounding.
* Independent rng seeds; per-cell seed = `cell_index` (0..799 for the
  full multiple-run, sub-sampled to 720 by the runner).

## Output bundle

`data/emtp_720.mat` (MATLAB v7), schema **identical** to the PSCAD
bundle (`pscad/HIFL_11kV_100km_design.md` "Output bundle"):

| Key            | Type    | Shape       | Description                       |
|----------------|---------|-------------|-----------------------------------|
| `V`            | float64 | (720, 200)  | Source-end voltage waveform [V]   |
| `I`            | float64 | (720, 200)  | Source-end current waveform [A]   |
| `grid_alpha`   | float64 | (720,)      | Per-unit fault location           |
| `grid_Rx`      | float64 | (720,)      | HIF arc resistance [Ω]            |
| `grid_SNR_V`   | float64 | (720,)      | Voltage-channel SNR [dB]          |
| `grid_SNR_I`   | float64 | (720,)      | Current-channel SNR [dB]          |
| `meta`         | struct  | —           | f0, Fs, Ns, line_length_km, rng_seed, builder, version |

**Cell ordering must match the PSCAD case** (alpha outermost, Rx,
SNR_V, SNR_I innermost) so that `tools/compare_pscad_emtp.py` can do
a direct per-cell index comparison.

## Cross-platform comparator

`tools/compare_pscad_emtp.py` loads both `.mat` files and reports the
per-cell RMS difference of V and I across the 200-sample window.
Acceptance (per `tests/test_pscad_emtp_consistency.py`):

* median per-cell RMS diff < 1 %
* 95th percentile RMS diff < 3 %

Cells that exceed the 2 % flag threshold are dumped to
`outputs/phase1_pscad_vs_emtp.csv` for inspection. If the consistency
test fails, escalate per R1 — engage Prof. Christian Rehtanz
(TU Dortmund) for an independent EMTP review before proceeding to
WP1.4 cross-platform optimiser re-run.
