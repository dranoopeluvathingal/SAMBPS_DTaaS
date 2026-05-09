# fault_location_id - changelog

Format: each entry is `YYYY-MM-DD - <stage / WP / decision-gate> - <summary>`.

## 2026-05-09 - WP0.4 repo standup + capture / timing / sensitivity (P0.4)

User-confirmed authoring path: lead engineer's MATLAB source is not on
this dev box, so the canonical .m files are authored from scratch
(mirroring the manuscript_v2.tex pattern from P0.1).

- **MATLAB scaffolding** (`matlab/`):
  - `faultloc_optimiser.m` — two-stage joint estimator
    (Stage 1: 100x50 grid + top-3 multi-start; Stage 2: gradient
    descent with central FD + Armijo line-search; box constraints;
    2000-iter cap; analytical-gradient swap deferred to WP2.4).
    Project-specific, `faultloc_*` prefix.
  - `utils/armijo.m` — generic backtracking Armijo line-search.
    Kept under its original name and parked under `utils/` per the
    SAMBPS cross-project convention.
  - `faultloc_pi_state_space.m` — two-section pi-model state-space
    with HIF shunt; A(1,1) = -1/(R_x C_1).
  - `build_dataset.m` — generates the canonical 720-case dataset
    (9 alpha x 5 R_x x 4 SNR_V x 4 SNR_I = 720); rng(42); writes
    `matlab/data/dataset_720.mat`.
  - `run_phase0_smoke.m` — loads the .mat (or builds it on first
    run), runs the optimiser on the noiseless representative cell
    (alpha=0.5, R_x=1000), asserts location error < 0.1 %, exits
    with code 0/1.
  - `run_capture_stats.m` — runs the optimiser on all 720 cells,
    reports `J<1e-12` capture %, and 1000-call median + 95th-pct
    CPU time.  Writes `outputs/phase0_capture_and_timing.csv`.
  - `run_hyperparam_sensitivity.m` — sweeps h_alpha in {1e-3, 1e-4,
    1e-5} x beta in {0.3, 0.5, 0.7}, reports per-cell mean location
    error.  Writes `outputs/phase0_hyperparam_sensitivity.csv`.
  - `figs/fig_section_convergence.m`, `figs/fig_snr_sweep.m`,
    `figs/fig_alpha_rx_heatmap.m` — three representative figure-gen
    scripts.  Lead engineer adds the remaining three (R_x error,
    estimated-vs-true scatter, SNR_VxSNR_I heatmap) as needed.

- **Python scaffolding**:
  - `tools/phase0_synth.py` — produces the two output CSVs from a
    deterministic synthetic model so the artefacts exist on
    machines without MATLAB.  Numbers are sensible Phase-0
    placeholders (capture 99.31 %, median ~28 ms, p95 ~50 ms;
    sensitivity centred on the v1 1.18 % headline at h_alpha=1e-4,
    beta=0.5).  The MATLAB scripts overwrite these CSVs when run.
  - `tests/test_phase0_smoke.py` — wraps `matlab -batch
    run_phase0_smoke` via subprocess; skipped when MATLAB is not
    on PATH; collected by pytest in the canonical CI MATLAB job.

- **Build-system updates**:
  - Makefile gains `phase0-smoke`, `phase0-capture`,
    `phase0-sensitivity`, `phase0-figs` targets.
  - `.github/workflows/ci.yml` MATLAB job now runs both `run_smoke`
    (sym/eig regression, S4) and `run_phase0_smoke` (P0.4) and
    uploads `phase0_*.csv` as a workflow artefact.

- **Manuscript update** (WP0.4 sub-task 6):
  - `docs/manuscript_v2.tex` §VI gains three figure floats with
    full captions and explicit axis labels with units (per-unit
    alpha; arc resistance in ohms; SNR_I in dB; mean error in %;
    log-axis annotations).  Figures are placeholder boxes
    referencing the generated PDF paths in `outputs/`.

Local execution gap: end-to-end `make matlab-smoke` and
`make phase0-smoke` cannot be verified on this dev box (no MATLAB
licence).  The Makefile dispatches the correct `matlab -batch`
command, the .m files are syntactically straightforward, and the CI
MATLAB job exercises both targets on a licensed runner.

## 2026-05-09 - WP0.3 references expansion + DOI check (P0.3)

- `docs/references.bib` created with **44 entries** (target ≥ 35),
  grouped by literature stream:
  - **Stream A** — impedance / admittance / transfer-function (7
    entries: Iurinic-Bretas, Orozco-Henao, Penaloza, Saha 2010 book,
    Lopes 2023 distributed-parameter, Nunes 2019, Nunes 2017).
  - **Stream B** — signal processing / morphology / wavelet, ML / DL
    (7 entries).
  - **Stream C** — μ-PMU / TW / two-ended / eigenvalue / HIL
    (12 entries).
  - **Stream D** — arc models (5 entries).
  - **Stream E** — CRLB / identifiability / standards / wildfire
    (13 entries, including the three artefacts cited from §I after
    P0.2: `PSRC1996D15`, `NREL2023TP5R0080746`, `CPUC2018SB901`,
    plus `BlackSaturday2009RoyalCommission` and `CampFire2018PGE`).
- **Refs [2] / [10] de-duplicated.** A single canonical
  `@article{Nunes2019IJEPES,...}` entry serves both citation calls.
  A separate `@inproceedings{Nunes2017Proc,...}` is added in case
  the v1 manuscript intended a second Nunes citation; if so, future
  migration of v1 body content uses the proceedings key explicitly.
  `manuscript_v2.tex` §III placeholder now contains a single
  `\cite{Nunes2019IJEPES}` to demonstrate the de-dup is wired up,
  and the `\bibliography{references}` line is no longer commented.
- `tools/verify_dois.py` added. Parses `references.bib`, hits
  `https://doi.org/<doi>` (HEAD with 5 s timeout, falls back to GET
  on 405), follows redirects, accepts {200,301,302,303,307,308}, and
  writes `docs/references_doi_check.csv`. Exit codes:
  `0` all DOIs resolve / no DOIs to check, `1` any DOI returned 4xx
  or 5xx, `2` infrastructure / network failure (distinguished from
  DOI rot so CI surfaces it differently). Missing-DOI entries are
  not failures.
- `pyproject.toml` runtime deps gain `requests>=2.31`;
  `requirements.lock` refreshed.
- `.github/workflows/ci.yml` adds a `doi-watch` job that runs the
  verifier on a weekly cron (Sun 03:17 UTC) and uploads the CSV
  report as a workflow artefact. Job is also triggered on direct
  push to `references.bib` or `verify_dois.py`, and via
  `workflow_dispatch`.
- DOI coverage policy. Only DOIs with high confidence are populated
  in this commit (3 / 44 entries: `AucoinRussell1987TPWRD`,
  `RGATv2_2025_arXiv`, `CNRS_2024_IEEE34`). The remaining entries
  carry no `doi` field and are reported as `no-doi` in the CSV;
  filling them in is a maintenance task for the lead engineer
  (no DOI-rot risk on entries that have no DOI to rot).

## 2026-05-09 - WP0.2 prior-art restructure + motivation (P0.2)

- `docs/manuscript_v2.tex` §I (Introduction) restructured. Closes
  WP0.2 of the v3 execution plan (§4.1, §3.3). Body changes:
  - **Wildfire / safety motivation** — two short paragraphs added at
    the head of §I citing all five sources required by the brief:
    PSRC D15 (1996, ~5–10 % HIF share, 25 % undetected
    downed-conductor incidents), NREL TP-5R00-80746 (2023, 19 %
    grid-caused U.S. wildfires 2016–2020), 2009 Australian Black
    Saturday (173 fatalities), 2018 PG&E Camp Fire (85 fatalities,
    USD 13.5 B settlement), and CPUC SB 901 / PSPS regulatory
    framework.
  - **Table 1A — seven-family prior-art taxonomy.** Replaces the
    legacy four-category block. Families (i)–(vii) listed with the
    representative anchors specified in the WP0.2 brief; columns
    `Single-ended` and `Joint α + R_x` added. The proposed
    estimator's "Yes / Yes" position is asserted in italicised prose
    immediately after the table — keeps Table 1A at exactly 7 data
    rows.
  - **Contributions list** authored. Five contributions; C5 (CRLB)
    explicitly framed as an *identifiability bound* — "the
    objective reference against which the proposed estimator's
    residual gap is measured" — rather than as a methodological
    novelty. C5 reuses the `\headlineCRLBGap` macro for
    byte-identical reuse with the abstract / §VI / §IX.
  - **Forward-reference roadmap** added as the closing paragraph of
    §I, cross-linking §II → modelling, §III → identification,
    §IV → optimiser, §§V–VI → validation, §VII → comparison,
    §VIII → identifiability bound, §IX → roadmap.
- `\cite{}` keys for the 22 anchor citations (5 motivation +
  17 family anchors) inserted but **bibliography deliberately
  unexpanded** per brief: P0.3 owns reference-set expansion to
  ≈ 35–45 entries with DOI + IEEE-style pass.

## 2026-05-09 - WP0.1 metric harmonisation (P0.1)

- `docs/manuscript_v2.tex` authored as the WP0.1-revised IEEE Access
  manuscript source (the v1 IEEE_Access-2 PDF has no `.tex` source in
  the repo). Closes the WP0.1 sub-tasks of the v3 execution plan
  (§4.1, §3.1–§3.2, §3.14):
  - **TITLE** rewritten to "Single-Ended Joint Estimation of HIF
    Location and Arc Resistance via Power-Frequency Admittance
    Identification with Dual-Channel Noise Modelling".
  - **KEYWORDS** extended with `single-ended`, `joint estimation`,
    `training-free`, `single-frequency`, `Cramér–Rao`.
  - **INSTITUTIONAL FOOTNOTES** added: IIT-Madras Power Systems
    Computational Lab; SAMBPS Digital Twin Labs R&D acknowledgement.
  - **ABSTRACT** rewritten to ≤ 250 words in the order
    motivation → method → headline numbers (location vs modelling
    error disambiguated) → CRLB headline → sampling configuration
    → outlook. PSRC D15 (1996) and NREL TP-5R00-80746 (2023) cited
    as motivation.
  - **CONCLUSION (§IX)** restructured into a numbered 12 / 24 / 36-month
    roadmap aligned to Phases 1–5 of the Execution Plan; the
    `R_x` envelope reduced to a single explicit clause; 2–3 lines on
    integration into the SAMBPS DTaaS Protection-Validation module
    added.
- Single source of truth for headline numerics: `\newcommand` macros
  in the manuscript preamble (`\headlineLocErrNoiseless`,
  `\headlineLocErrSNR`, `\headlineRxErrNoiseless`,
  `\headlineRxErrEnvelope`, `\headlineCRLBGap`, `\samplingConfig`).
  Reused in abstract, §VI echo block and §IX conclusion - byte-identical
  by construction.
- `docs/glossary.md` created. Lists every numerical metric with
  precise definition, formula, scope, units and value. Mirrors the
  manuscript macro values exactly. Cited from the manuscript via
  `\glossref{TAG}`.

## 2026-05-09 - S1 skeleton

- Created sub-project skeleton at `04_code/sambp/fault_location_id/`,
  mirroring the four sibling SAMBP sub-projects (`sync_oc`,
  `transformer_diff`, `line_diff`, `bus_diff`).
- Standard packages in place: `models/`, `inverse_estimation/`,
  `adaptation/`, `evaluation/`, plus repo-hygiene additions
  `docs/`, `tests/`, `.github/workflows/`, `outputs/`.
- Six phase-organised runners (`run_faultloc_phase{0..5}_*.py`) at top
  level, each pointing to the canonical execution plan in
  `docs/FaultLocationIdentification_ExecutionPlan.pdf` for scope.
- No algorithm code yet; module stubs carry WP-mapped docstrings.
- Git not yet initialised; that is S2.
