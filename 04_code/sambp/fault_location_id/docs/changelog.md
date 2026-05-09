# fault_location_id - changelog

Format: each entry is `YYYY-MM-DD - <stage / WP / decision-gate> - <summary>`.

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
