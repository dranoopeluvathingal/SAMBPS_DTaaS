# fault_location_id - changelog

Format: each entry is `YYYY-MM-DD - <stage / WP / decision-gate> - <summary>`.

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
