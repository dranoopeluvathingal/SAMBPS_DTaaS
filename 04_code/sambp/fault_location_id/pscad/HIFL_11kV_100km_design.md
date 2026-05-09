# HIFL_11kV_100km — PSCAD case design

Reviewer-friendly schematic-level documentation of the canonical PSCAD
case `pscad/HIFL_11kV_100km.pscx`. Maintained because the `.pscx`
binary is opaque to non-PSCAD reviewers (e.g. a TU Dortmund EMT
cross-check by Prof. Rehtanz, R1 mitigation per v3 plan §10).

## Topology

```
   V_s        section 1            fault             section 2          remote
  ──────►  R1, L1, C dist.   ────────► R_x ◄────  R2, L2, C dist.   ──────  open / R_load
   |               |              |                       |
   |               |              v ground                |
   |        CT(I_in)/PT(V_in)                             |
   |     @ 10 kHz, 200 samples,                           |
   |        one cycle window                              |
   |________ ground __________________________________ ground
```

* Source bus: ideal voltage source $V_s = V_0\sqrt{2}\cos(2\pi f_0 t)$
  with $V_0 = 11000/\sqrt{3}$ V (phase voltage), $f_0 = 50$ Hz.
* Line: 100 km overhead distribution feeder, modelled as
  **frequency-dependent (Bergeron / J. Marti)** — *not lumped-π*. The
  v3 plan deliberately wants PSCAD to disagree with the 2-section
  optimiser by an amount we can quantify; the FD line is the
  disagreement source.
  Per-km parameters (Saha 2010, Springer Table 3.1; mirrored in
  `models/faultloc_pi_section_model.py`):

  | Parameter | Value         | Units    |
  |-----------|---------------|----------|
  | $R'$      | 0.0728        | Ω/km     |
  | $L'$      | 0.927e-3      | H/km     |
  | $C'$      | 11.6e-9       | F/km     |
  | $G'$      | 0.0           | S/km     |

  Frequency-dependence: J. Marti model with default fitting band
  10 Hz – 100 kHz (PSCAD default). Travel time
  $\tau = \ell\sqrt{L'C'} \approx 327\,\mu$s for $\ell = 100$ km.

* Fault at α∈(0,1): the line is split as two cascaded FD sections of
  lengths $\alpha\,\ell$ and $(1-\alpha)\,\ell$, joined at the fault
  bus where the HIF arc element is shunt-connected.

* HIF arc: anti-parallel diode model
  ([`Sec. II.C` of v1 manuscript]; v3 plan §3.6 + WP0.5 provenance):

  | Parameter        | Value     | Units |
  |------------------|-----------|-------|
  | $V_{kp}$         | 50        | V     |
  | $V_{kn}$         | 45        | V     |
  | $R_{sp}$         | 5         | Ω     |
  | $R_{sn}$         | 6         | Ω     |
  | $R_{\text{off}}$ | 1.0e6     | Ω     |
  | $\varepsilon$    | 1e-3      | A     |

  **Provenance.** v3 plan §3.6 + Top-8 R4 + R10: parameter
  provenance gap is open. The Emanuel-1990 sandy-soil values
  (kV-range $V_p/V_n$, tens-to-thousands $\Omega$ $R_p/R_n$) and
  Santos-2022 surface-resolved table contradict the values above.
  The diode-arc parameters used here come directly from the v1
  IEEE_Access-2 manuscript Sect. II.C; arc-class diversification
  (Cassie–Mayr–Kizilcay, Wang-2020 distortion-controllable,
  Torres-2022) lands in WP4.2–4.4. **TODO arc-provenance** — this
  block to be confirmed against Santos-2022 before camera-ready
  freezes, see issue tracker WP4.2-prep.

* CT and PT measurement at the source terminal:
  - `PT_in` ↔ $V_{in}(t)$ (phase voltage)
  - `CT_in` ↔ $I_{in}(t)$ (line current)
  - Sampling rate: $F_s = 10$ kHz
  - Window: $N_s = 200$ samples = one $f_0$ period

* Dual-channel additive Gaussian white noise (PSCAD `random_white_noise`
  source):
  - `noise_V`: scaled to give voltage SNR = `SNR_V` dB
  - `noise_I`: scaled to give current SNR = `SNR_I` dB
  - Independent rng seeds (PSCAD `set_random_seed` block)

* Remote terminal: open through 1 MΩ load resistor (matches
  `R_load = 1e6` in `faultloc_pi_section_model.py`).

## Parametric study driver

PSCAD multiple-run sweep over the 720-cell grid:

| Parameter | Values                              | Count |
|-----------|-------------------------------------|-------|
| $\alpha$  | 0.05, 0.15, …, 0.95 (step 0.10)     | 10    |
| $R_x$     | 100, 500, 1000, 2000, 5000          | 5     |
| $\mathrm{SNR}_V$ | 20, 30, 40, ∞                | 4     |
| $\mathrm{SNR}_I$ | 20, 30, 40, ∞                | 4     |
| **Total**  |                                     | **800** |

> **Grid sizing note.** The v3 manual uses both "10 α × 5 Rx × 4 × 4 = 800" and "720 cases" as headline numbers, which are inconsistent. Phase-0 used 9 α values to land on exactly 720; this PSCAD case uses 10 α values (the v3 §3.10 wording) and the runner sub-samples to 720. See `pscad/README_manual_run.md` for the exact sub-sampling rule.

For each cell the simulation:
1. Initialises the line with no-fault for 5 cycles (transient settle).
2. Inserts the HIF arc at the fault bus at $t = 5/f_0$ s.
3. Runs to $t = 7/f_0$ s.
4. Captures the steady-state cycle (cycle 6 of 7).
5. Exports $(V_{in}(t), I_{in}(t))$ — 200 samples per channel.

## Output bundle

`data/pscad_720.mat` (MATLAB v7 format), keys:

| Key            | Type       | Shape       | Description                       |
|----------------|------------|-------------|-----------------------------------|
| `V`            | float64    | (720, 200)  | Source-end voltage waveform [V]   |
| `I`            | float64    | (720, 200)  | Source-end current waveform [A]   |
| `grid_alpha`   | float64    | (720,)      | Per-unit fault location           |
| `grid_Rx`      | float64    | (720,)      | HIF arc resistance [Ω]            |
| `grid_SNR_V`   | float64    | (720,)      | Voltage-channel SNR [dB] (Inf = noiseless) |
| `grid_SNR_I`   | float64    | (720,)      | Current-channel SNR [dB] (Inf = noiseless) |
| `meta`         | struct     | —           | f0, Fs, Ns, line_length_km, rng_seed, builder, version |

## Cross-validation against the optimiser

The 2-section optimiser of `matlab/faultloc_optimiser.m` is run on
the resulting waveforms; the per-cell location-error and Rx-error
deltas vs the WP0.4 self-consistent baseline quantify the modelling
gap that WP2.1 (cascaded ABCD / Bergeron closed-form $H$) closes.
Acceptance: WP1.4 reports the gap on `results/phase1_crossplatform.csv`;
gate D1 = mean location error < 2 % at SNR_I ≥ 30 dB across all 3
simulators (PSCAD, EMTP-RV, 50-section reference).
