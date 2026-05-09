# D0 — Phase 0 Decision Gate Review Pack

**Project:** SAMBPS DTaaS — `fault_location_id` (HIF transfer-function locator)
**Phase:** 0 — editorial + reproducibility hardening (W0–W2)
**Gate:** D0 — IEEE Access camera-ready v2.0 frozen; CI green
**Issued:** 2026-05-09
**Author:** Anoop Eluvathingal (PI)
**Cosignatory:** Prof. K. Shanthi Swarup (host advisor, IIT Madras)

> Format mirrors §8.1 of `docs/FaultLocationIdentification_ExecutionPlan.pdf`
> ("Decision-gate (D0–D5) review template").

---

## 1. Phase summary

Phase 0 stood up the `fault_location_id` sub-project from a clean slate:
six work packages (WP0.1 – WP0.6) ran across two weeks W0–W2 and closed
the editorial + reproducibility shortcomings flagged by the v3
Execution Plan §3 audit. The IEEE Access manuscript was rewritten
(title, abstract, conclusion, 7-family taxonomy in §I), the reference
list expanded from 19 to 44 entries, the canonical state-space
derivation written up as a watertight Appendix A with TikZ circuit and
KVL/KCL line by line, and the supporting MATLAB / Python scaffolding
(optimiser, dataset builder, capture / timing / hyperparameter
sensitivity scripts, Python re-implementation, cross-runtime golden
file) committed alongside CI infrastructure (GitHub Actions matrix
over Python 3.10/3.11/3.12, optional MATLAB job, weekly DOI watch).

## 2. Acceptance-test results

Test ID `T-A1` (Execution Plan §6) is the gate test for D-A; expanded
here into one row per sub-criterion.

| Sub-criterion | Source | Predicate | Measured | PASS / FAIL |
|---|---|---|---|---|
| Single coherent metric set | T-A1 (a) | All headline numerical values come from one `\newcommand` macro per quantity, byte-identical wherever cited | 6 macros, used 3–6× each across abstract / §VI / §IX | **PASS** |
| Appendix A includes π-derivation + ∂H/∂θ | T-A1 (b) | `docs/AppendixA_derivation.pdf` exists and contains §A.1–A.6 | 4-page standalone PDF; circuit, KVL/KCL, A,B,C,D, H closed-form, ∂H/∂α, ∂H/∂R_x, dimensional check | **PASS** |
| Repository link resolves | T-A1 (c) | `github.com/SAMBPS-DTaaS/HIF-TF-Locator` accessible | repo provisioned, currently **private** (D0 flips to public) | **CONDITIONAL PASS** — flip pending PI signoff |
| References ≥ 35 entries | T-A1 (d.1) | `docs/references.bib` ≥ 35 `@…{}` entries | 44 entries across streams A–E | **PASS** (target +9) |
| References with valid DOIs | T-A1 (d.2) | DOIs that resolve via `https://doi.org/` | 3 / 44 entries carry verified DOIs (`AucoinRussell1987TPWRD`, `RGATv2_2025_arXiv`, `CNRS_2024_IEEE34`) | **FAIL** — only 3 of the 35-entry threshold met |
| Abstract ≤ 250 words | implicit (P0.1) | word count ≤ 250 | 191 words | **PASS** |
| §I 7-family taxonomy table | implicit (P0.2) | exactly one taxonomy table with 7 rows | 7 data rows; proposed-method "Yes/Yes" call-out in italicised prose immediately after | **PASS** |
| Every figure has axis labels with units | implicit (P0.4 sub-task 6) | all figure floats carry `xlabel`/`ylabel` with units | 3 figure floats, all with units (`α` --, `R_x` Ω, SNR dB, error %) | **PASS** |
| Appendix A as supplementary | implicit (P0.5) | standalone PDF supplied alongside camera-ready | `docs/AppendixA_derivation.pdf` (4 pages, 404 KB) | **PASS** |
| `make test` exits 0 | T-A1 (e) | pytest passes | 6 passed, 1 skipped (`test_phase0_smoke` skipped — MATLAB not on dev-box PATH; runs in CI MATLAB job) | **PASS** |
| `ruff check .` exits 0 | implicit (CI) | ruff lint passes | "All checks passed!" | **PASS** |
| `make matlab-smoke` exits 0 | T-A1 (f) | MATLAB sym/eig + Phase-0 smoke passes | not exercised on this dev box (no MATLAB licence); CI MATLAB job is the canonical execution path | **GATED** — runs in CI, not locally |
| `python tools/verify_dois.py` exits 0 | weekly cron | all DOIs in references.bib resolve | 3 / 3 DOIs resolved (200), 41 `no-doi` (not failures) | **PASS** |

**Gate-blocker summary.** One *FAIL*
(DOI coverage 3 / 35), one *CONDITIONAL PASS* awaiting PI flip
(public-repo visibility), and one *GATED* on CI for the MATLAB smoke.
All other rows PASS.

## 3. Risk-register update

Per Execution Plan §10, no risk row escalated this phase. Notable updates:

| ID | Risk | Likely | Impact | Phase-0 outcome |
|---|---|---|---|---|
| R1 | Gaussian-on-H FIM invalid in HIF regime | High | High | **Unchanged** — closes in WP1.6 (Phase 1) |
| R2 | 39.44 % section-modelling-error ceiling | High | High | **Unchanged** — closes in WP2.1–2.5 (Phase 2) |
| R4 | Diode arc parameter provenance gap | Med | Med | **Mitigated** in WP0.5 (every parameter cited; SI substitution explicit; legacy heuristics replaced) |
| R6 | Categorical comparison non-quantitative | High | Med | **Unchanged** — closes in WP4.5 (Phase 4) |
| R7 | Symbolic derivation errors | Low | High | **Mitigated** — `matlab/derive_partials.m` + `test_partials.m` + cross-runtime Python golden test |

**New risk added:** R11 — DOI coverage gap (3 / 44). Likely Med, Impact Low (no DOI-rot risk on entries with no DOI to rot). Mitigation: lead engineer runs a one-pass Crossref / IEEE Xplore lookup against the 41 entries currently `no-doi` and refreshes `references.bib`; weekly cron job (S3) catches any rot thereafter.

## 4. KPI snapshot

| # | KPI | Target | Phase-0 measurement | Status |
|---|---|---|---|---|
| K11 | References, IEEE-style, valid DOI | ≥ 35 | 44 entries / 3 with verified DOI | partial (count met, DOI coverage gap — see §2 row "References with valid DOIs") |
| K12 | Public repo + Zenodo DOI | live at D0 | repo provisioned, **private**; Zenodo DOI minted on D0 release | **GATED** — pending PI signoff to flip public + push tag |
| K13 | CI green build rate (rolling 30 days) | ≥ 95 % | 0 PRs run yet; pipeline green on this commit | n/a (baseline) |
| K14 | 95th-percentile estimator CPU time | published | 49.30 ms (synth, P0.4) / canonical MATLAB run pending CI | published (synth) |
| K15 | Hyperparameter sensitivity table coverage | full | 9-cell sweep present; best at h_alpha=1e-4, beta=0.5 (1.18 %) | **PASS** |

## 5. Decision recommendation

**Recommend (b) Conditional approval to progress to Phase 1, with the following follow-on items:**

1. **Pre-progression (≤ W3 Mon)** — Lead engineer runs a Crossref / IEEE Xplore DOI lookup pass against the 41 `no-doi` entries in `references.bib`; commits as `WP0.3 follow-up: DOI coverage`; reruns `python tools/verify_dois.py` to refresh `references_doi_check.csv`. Target: ≥ 35 / 44 entries with verified DOIs before camera-ready submission.
2. **Pre-progression** — PI confirms green light to flip `github.com/SAMBPS-DTaaS/HIF-TF-Locator` to public and push the `v0.2.0-phase0` tag. The CI MATLAB job (`run_smoke` + `run_phase0_smoke`) runs end-to-end on the GitHub-hosted runner once visibility flips.
3. **Concurrent with Phase 1** — `matlab/derive_partials.m` is run on a licensed MATLAB to overwrite the FD placeholders in `matlab/dH_dalpha.m` / `dH_dRx.m` with the symbolic forms; `test_partials.m` then verifies relative error < 1e-3 against FD.

## 6. Publication artefact

- **Camera-ready manuscript** — `docs/manuscript_v2.pdf` (4 pages, 263 KB; compiled from `manuscript_v2.tex` against `references.bib` via `pdflatex` × 2 + `bibtex`).
- **Supplementary material** — `docs/AppendixA_derivation.pdf` (4 pages, 404 KB).
- **Glossary** — `docs/glossary.md` (single source of truth for headline numerics).
- **Reproducibility code** — full repo at `04_code/sambp/fault_location_id/`; release tag `v0.2.0-phase0` (created locally; push gated on PI signoff).
- **Reproducibility data** — Phase-0 baseline CSVs `outputs/phase0_capture_and_timing.csv` and `outputs/phase0_hyperparam_sensitivity.csv` (tracked); 720-case dataset regenerable via `matlab/build_dataset.m`.
- **Zenodo deposition** — staged at `outputs/fault_location_id_v0.2.0.zip` + `outputs/zenodo.json`; DOI minted on push.

## 7. Signoff

| Role | Name | Signature | Date |
|---|---|---|---|
| Principal Investigator | Anoop Eluvathingal | _pending_ | _pending_ |
| Lead Engineer | Arjundas K. | _pending_ | _pending_ |
| Host Advisor | Prof. K. Shanthi Swarup, IIT Madras | _pending_ | _pending_ |
