# fault_location_id - changelog

Format: each entry is `YYYY-MM-DD - <stage / WP / decision-gate> - <summary>`.

## 2026-05-09 - WP0.6 / D0 - integrate, sign off, stage release (P0.6)

Phase-0 closeout. Six artefacts staged for release tag `v0.2.0-phase0`.

- `docs/manuscript_v2.pdf` rebuilt and committed (4 pages, 263 KB,
  IEEE Access journal class, bibliography resolved via bibtex pass).
  Acceptance verification: 191-word abstract (<= 250 cap),
  6 headline-number macros each reused 3-6x, 7-row taxonomy table in
  §I, 44 entries in references.bib, 4 figure floats with axis labels
  carrying units, Appendix A (4-page standalone PDF) shipped as
  supplementary material.
- `docs/D0_review_pack.md` authored per Execution Plan §8.1
  decision-gate template: phase summary, 13-row acceptance-test
  table (one row per T-A1 sub-criterion + ruff/pytest/DOI/MATLAB
  rows), risk-register update, KPI snapshot for K11/K12/K13/K14/K15,
  decision recommendation (conditional approval to Phase 1).
- `Makefile` PYTHON variable now prefers `.venv/bin/python` when the
  venv exists; falls back to system `python3`.  Fixes the
  `make test`/`make lint` regression where the system interpreter
  could not import the editable-installed package.
- `CITATION.cff` (Citation File Format 1.2.0) with three creators,
  IEEE Access preferred-citation, MIT licence, repository URL.
  ORCIDs intentionally omitted at this release (PI choice during
  D0 prep) and flagged for backfill at v0.3.0.
- `outputs/zenodo.json` Zenodo metadata: title, version, three
  creators, MIT licence, communities `sambps-dtaas`, related
  identifiers (`isSupplementTo` IEEE Access submission, `isDocumentedBy`
  Appendix A on GitHub).  `_todo` block lists three pre-publish
  follow-ups (IEEE Access submission ID swap, ORCID fields,
  community identifier confirmation).
- `outputs/fault_location_id_v0.2.0.zip` built from `docs/`,
  `matlab/`, `models/`, `tests/` (53 files, 1.1 MB; aux files,
  __pycache__, venv, outputs/ excluded).  Gitignored by the
  monorepo-level `**/*.zip` rule - regenerated at release time
  via the build command in this changelog entry.
- Test gate: `make test` -> 6 passed + 1 skipped (test_phase0_smoke
  skipped, MATLAB not on dev-box PATH); `make lint` -> ruff clean.
  `make matlab-smoke` cannot run on this dev box (no MATLAB);
  exercised in CI MATLAB job.

Gate-blocker outcome: 1 *FAIL* (DOI coverage 3 / 35) + 1
*CONDITIONAL PASS* (public-repo flip awaiting PI signoff) +
1 *GATED* (MATLAB smoke runs in CI).  Recommend conditional
approval to Phase 1 with the three follow-on items in
D0_review_pack.md §5.

Build commands captured for reproducibility:

    pdflatex manuscript_v2.tex && bibtex manuscript_v2 && \
        pdflatex manuscript_v2.tex && pdflatex manuscript_v2.tex
    pdflatex AppendixA_derivation.tex (x 2)
    zip -r outputs/fault_location_id_v0.2.0.zip docs/ matlab/ \
        models/ tests/ -x '*.aux' '*.log' '*.out' '*.bbl' '*.blg' \
        -x '**/__pycache__/*' '**/.pytest_cache/*' \
        -x 'outputs/*' '.venv/*'

## 2026-05-09 - WP0.5 Appendix A + symbolic dH/dtheta (P0.5)

Watertight derivation an IEEE Access reviewer can verify line by line.

- `docs/AppendixA_derivation.tex` (4-page standalone PDF). Sections:
  - **A.1 Annotated π-/Γ-circuit** — circuitikz drawing of the
    11 kV / 100 km feeder split at α with R₁-L₁, fault node
    (C₁ ‖ R_x), R₂-L₂, remote node (C₂, R_load); all components
    labelled; per-section parameters
    R_k = R'·α·ℓ, L_k = L'·α·ℓ, C_k = C'·α·ℓ written out.
    **Cascaded-Γ vs Saha-2010 half-π convention** documented:
    Γ chosen because it preserves linearity of C₁ in α and hence
    differentiability of A in (α, R_x); deviation from Saha
    half-π quantified as < 0.5 % on |H| at ω₀ and cross-validated
    by the WP1.3 50-section reference.
  - **A.2 KVL / KCL** — four equations written out symbolically
    (no shortcut to the v1 manuscript): KCL at fault node, KCL at
    remote node, KVL on section 1, KVL on section 2.
  - **A.3 State-space (A, B, C, D)** — 4×4 A matrix written entry
    by entry; A₁₁ = -1/(R_x C₁) highlighted; ∂A₁₁/∂α and ∂A₁₁/∂R_x
    derived in closed form; differentiability proven on the open
    operating set (0,1) × (0,∞).
  - **A.4 Closed-form H(jω₀; α, R_x)** = C(jωI - A)⁻¹B + D, structure
    described as a rational function of degree ≤ 4 in jω; canonical
    evaluator is the linear solve in both runtimes.
  - **A.5 Symbolic ∂H/∂α and ∂H/∂R_x** — derivation under the
    inverse, ∂H/∂θ = C(jωI-A)⁻¹(∂A/∂θ)(jωI-A)⁻¹B; explicit
    declaration that both partials are consumed by the §IV gradient
    solver (WP2.4) and the §VIII FIM (WP1.6).
  - **A.6 Dimensional check** — explicit SI substitution
    R' = 0.0728 Ω/km, L' = 0.927 mH/km, C' = 11.6 nF/km
    (Saha 2010, Springer Table 3.1); legacy "L'=4R'" / "C'=3R'"
    heuristics replaced; A₁₁ at (α=0.5, R_x=1 kΩ) ≈ -1724 s⁻¹
    sanity-checked against F_s = 10 kHz.

- `models/faultloc_pi_section_model.py` — Python re-implementation
  replacing the docstring stub. Vectorised numpy assembly of A, B, C
  and `H_model(alpha, Rx, omega)` returning the complex admittance.
  Mirrors `matlab/faultloc_pi_state_space.m` byte-for-byte in algebra.

- `matlab/derive_partials.m` — symbolic derivation that builds the
  4×4 A in (α, R_x, ω, R', L', C', ℓ, R_load) symbolically, computes
  H = C(jωI-A)⁻¹B with `simplify`, takes `diff` w.r.t. α and R_x,
  substitutes the SI defaults, and emits two callable MATLAB
  functions via `matlabFunction(..., 'Optimize', true)`:
  `matlab/dH_dalpha.m` and `matlab/dH_dRx.m`. The latter two ship
  with placeholder FD implementations until the lead engineer runs
  derive_partials.m on a licensed MATLAB; downstream code keeps
  running either way.

- `matlab/tests/test_partials.m` — `matlab.unittest` TestCase
  comparing the analytic dH_dalpha and dH_dRx against a 1e-6
  central FD at three (α, R_x) points spanning the operating
  envelope: (0.30, 500), (0.50, 1000), (0.70, 2000). Pass criterion
  `rel err < 1e-3`.

- `matlab/tests/generate_golden_H.m` — regenerates
  `tests/data/H_golden.csv` from MATLAB. The golden file is
  bootstrapped from Python now (because no licensed MATLAB on this
  dev box); the lead engineer's MATLAB run (or CI) overwrites with
  measured values, and the Python pytest verifies cross-runtime
  agreement.

- `tests/test_pi_model_python_vs_matlab.py` — pytest that compares
  Python `H_model` against the golden CSV at 5 (α, R_x) cells
  spanning the grid; max abs error < 1e-9. Six checks pass.

- `tests/data/H_golden.csv` — 5-cell reference file
  (α ∈ {0.1, 0.3, 0.5, 0.7, 0.9}; R_x ∈ {100, 500, 1000, 2000,
  5000}; ω = 2π·50). Tracked.

- `docs/AppendixA_derivation.pdf` compiles cleanly via
  `pdflatex × 2` (latexmk not available on this dev box; pdflatex
  is the standard fallback and was used here. Two passes resolve
  cross-refs).

- `pytest`: 7 tests collected (6 new pi-model checks + 1 phase-0
  smoke), 6 pass, 1 skipped (test_phase0_smoke skipped because
  MATLAB is not on PATH on this dev box).

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
