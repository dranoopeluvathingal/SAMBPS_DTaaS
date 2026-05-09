# fault_location_id - changelog

Format: each entry is `YYYY-MM-DD - <stage / WP / decision-gate> - <summary>`.

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
