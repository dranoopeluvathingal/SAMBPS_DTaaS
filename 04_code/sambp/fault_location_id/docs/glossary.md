# Glossary of numerical metrics

WP0.1 deliverable. Single source of truth for every numerical value
reported in [`docs/manuscript_v2.tex`](manuscript_v2.tex). Each row's
"Value" column is byte-identical with the LaTeX macro of the same name
in the manuscript preamble; do **not** hand-edit. To change a value,
edit `\newcommand{\headline...}{...}` in `manuscript_v2.tex` and update
the matching row here in the same commit.

The abstract and §VI cite this glossary via the
`\glossref{TAG}` macro (rendered as a small superscript "see Glossary,
TAG"). Entries are organised by the v3 Execution Plan deliverable
that owns them.

## D-A — Phase 0 baseline metrics

### `LOC-ERR` — fault-location error
- **Definition.** Mean absolute relative error on the per-unit fault
  location $\hat\alpha$ recovered by the two-stage optimiser, taken
  across the 720-case grid
  ($10\alpha \times 5R_x \times 4\,\mathrm{SNR}_V \times 4\,\mathrm{SNR}_I$).
- **Formula.** $\overline{\varepsilon}_{\alpha} =
  \frac{1}{N}\sum_{n=1}^{N}|\hat\alpha_n - \alpha_n|/\alpha_n$,
  with $N = 720$ in the AWGN baseline and $N = 720 \times 100$
  under WP1.5 Monte-Carlo.
- **Units.** Percent (`%`).
- **Scope.** Single-feeder, single-phase, two-section $\pi$-model
  baseline. Re-validated cross-platform (PSCAD, EMTP-RV, 50-section
  reference) under WP1.4.
- **Value (noiseless).** `0.009 %`
- **Value (SNR).** `1.18 % at SNR_I = 20 dB`

### `RX-ERR` — arc-resistance error
- **Definition.** Mean absolute relative error on the recovered arc
  resistance $\hat R_x$ across the 720-case grid.
- **Formula.** $\overline{\varepsilon}_{R_x} =
  \frac{1}{N}\sum_{n=1}^{N}|\hat R_{x,n} - R_{x,n}|/R_{x,n}$.
- **Units.** Percent (`%`).
- **Scope.** Same as `LOC-ERR`. The "envelope" form quantifies the
  worst-case across a band of true $R_x$ values; the "noiseless" form
  isolates the structural floor.
- **Value (noiseless).** `2.42 %`
- **Value (envelope).** `≤ 8 % across 100–2000 Ω at SNR ≥ 30 dB`

### `CRLB-GAP` — empirical-vs-bound headline
- **Definition.** Maximum vertical gap (in dB or relative terms)
  between the empirical RMS estimator error and the corrected
  proper-complex-Gaussian-ratio CRLB envelope, taken at the SNR
  region where the estimator is operating nominally.
- **Formula.** $g(\mathrm{SNR}) =
  20\log_{10}\!\left(\mathrm{RMSE}(\hat\theta)/\sqrt{\mathrm{CRLB}}\right)$,
  evaluated at the high-SNR plateau.
- **Units.** Percent (`%`) when reported as a relative gap; dB when
  reported on the log axis of the overlay plots.
- **Scope.** WP0.1 reports the v1 statement; WP1.6 supplies the
  corrected FIM derivation that this gap is measured against.
- **Value (headline).** `within 15 % of the Cramér–Rao Lower Bound at SNR ≥ 40 dB`

### `SAMP-CFG` — sampling configuration
- **Definition.** Sampling frequency $F_s$, samples-per-window $N_s$
  and observation window length used by every result in the paper.
- **Constraint.** $N_s = F_s / f_0$ with $f_0 = 50$ Hz, hence
  $N_s = 200$ at $F_s = 10$ kHz; "one cycle window" formalises the
  observation as exactly one $f_0$ period for the single-bin DFT
  identification.
- **Units.** kHz, samples, periods.
- **Scope.** Holds for the full 720-case grid; field-grade impairments
  (WP4.1) re-run the grid at the same $F_s$ but vary the ADC
  resolution and the off-nominal frequency offset.
- **Value.** `F_s = 10 kHz, N_s = 200, one cycle window`

## D-C — Phase 2 modelling-error metric (separate from LOC-ERR)

### `MODEL-ERR` — TF-magnitude modelling error vs 50-section reference
- **Definition.** Relative magnitude error of the optimiser's
  forward-model transfer function $H_{\mathrm{model}}(j\omega_0;
  \alpha, R_x)$ versus a 50-section pure-MATLAB reference state-space
  evaluated on the same $(\alpha, R_x)$ grid.
- **Formula.** $\varepsilon_H(\alpha, R_x) =
  ||H_{\mathrm{model}} - H_{\mathrm{ref}}|| / ||H_{\mathrm{ref}}||$.
- **Units.** Percent (`%`).
- **Scope.** Distinct from `LOC-ERR`: this is a structural property of
  the forward model, not a property of the estimator. Quoted so the
  reader does not conflate the two.
- **Value (v1 baseline).** `mean 39.44 %, max 89.78 %`
- **Value (D-C target).** `mean < 5 %, post-WP2.1–WP2.3`

## D-B — Phase 1 statistical metrics

### `MC-CI` — per-cell 95 % confidence interval coverage
- **Definition.** Fraction of the 720 grid cells whose 95 %
  Monte-Carlo confidence interval excludes zero
  (i.e. statistically biased cells).
- **Units.** Percent of cells.
- **Acceptance threshold.** D-B requires `< 5 %` (Execution Plan §6,
  test T-B1).

### `GH-VALID` — Geary-Hinkley validity flag
- **Definition.** Boolean per cell; true when the
  proper-complex-Gaussian-ratio assumption is statistically supported
  by the local SNR regime.
- **Units.** Dimensionless flag.
- **Acceptance.** Reported per cell; failure cells fall back to the
  joint dual-channel FIM (`crlb_dualchannel.m`).

## How to add a new metric

1. Add a `\newcommand{\headlineXxx}{value}` macro to the preamble of
   `manuscript_v2.tex`.
2. Use the macro everywhere it is cited; never hand-type the value.
3. Add a row here with the same `Value` string, byte-for-byte.
4. Cite the row from the manuscript via `\glossref{TAG}`.
5. Update `docs/changelog.md` with the change under the relevant
   work-package tag.

## Provenance

- Motivation citations in the abstract: PSRC D15 (1996,
  "High-Impedance Fault Detection on Distribution Systems",
  IEEE Power Engineering Society Transmission and Distribution
  Committee report), and NREL TP-5R00-80746 (2023,
  "Wildfire Risks Posed to Electric Utility Grids").
- Numerical headline values are inherited from the IEEE_Access-2 v1
  manuscript draft and are subject to refinement in
  WP1.4–WP1.7 (cross-platform re-run) and WP1.6 (corrected CRLB).
