# D2 — Phase 2 Decision Gate Review Pack

**Project:** SAMBPS DTaaS — `fault_location_id`
**Phase:** 2 — continuously parametrised forward model + analytical gradients + author response (W10–W14)
**Gate:** D2 — distributed-parameter forward-model accuracy ≤ 5 % vs 50-section reference; estimator improvement ≥ 30 % at SNR_I ≤ 30 dB; manuscript v2 update + IEEE Access response document complete; tag `v0.4.0-phase2` (defer push)
**Issued:** 2026-05-10
**Author:** Anoop Eluvathingal (PI)
**Cosignatory:** Prof. K. Shanthi Swarup (host advisor)

> Format mirrors §8.1 of `docs/FaultLocationIdentification_ExecutionPlan.pdf`
> (decision-gate D0–D5 review template); D0 / D1 precedents at
> `docs/D0_review_pack.md` and `docs/D1_review_pack.md`.

---

## 1. Phase summary

Phase 2 ran six work packages WP2.1–WP2.6 from W10–W14:

* **WP2.1 / P2.1** Closed-form distributed-parameter forward model H(jω₀; α, R_x) via cascaded ABCD blocks (`models/faultloc_distributed_param_model.py`); 4 tests pass (max mag-err 2.7·10⁻⁵ % vs 50-section ref). v3 plan §3.7 modelling-error ceiling retired.
* **WP2.2 / P2.2** Closed-form analytic gradients ∂H/∂α and ∂H/∂R_x (`inverse_estimation/faultloc_analytical_gradients.py`); 8 tests pass (rel-err 10⁻⁹ vs central FD); MATLAB `sym/diff` cross-check at `matlab/tests/test_distributed_partials.m`; Appendix A §A.7 added.
* **WP2.3 / P2.3** 50-section reproduction tightened to D-C (max mag-err < 1 %); already met by P2.1 with 4 orders of magnitude margin; `outputs/phase2_reproduction.csv` (95 rows, all `within_target`); §II.D rewritten.
* **WP2.4 / P2.4** Analytical gradients in optimiser. Default opts switched to `forward_model='distributed'`, `gradient='analytical'`, `cost='ml'`; Stage-1 R_x grid switched to geomspace; diagonal-Newton step direction preserved; backward-compat path retained for legacy comparison. 4 new tests pass.
* **WP2.5 / P2.5** Full 720-grid + Monte-Carlo re-run on continuous model (`run_faultloc_phase2_continuous_param.py`). 6 figures with corrected-CRLB overlay produced; K03 PASS, K04 xfail (−830.82 %, R1 escalation forward to WP3.5/WP3.6); 5× regression test PASS on worst (α, R_x) = (0.95, 5000) cell.
* **WP2.6 / P2.6** _(this commit)_ Manuscript v2 update (§§II / III / IV / VI / abstract / conclusion) with continuously parametrised model, analytical gradients, K03/K04 honest reporting; `docs/IEEE_Access_response_v1.md` author-anticipated reviewer-response document; this `docs/D2_review_pack.md`; tag `v0.4.0-phase2` (push deferred to PI green light).

A backfill commit (`1840761d`) also landed the full 100-trial 4-dataset MC for WP1.5 (288 000 trial-cells) that earlier harness limits had truncated.

## 2. Acceptance-test results

| Test ID | Source | Predicate | Measured | Status |
|---|---|---|---|---|
| **T-C1.K03** | distributed-vs-50sec mean mag-err < 5 % across grid | 95 cells | mean **4.3·10⁻⁶ %**, max **2.7·10⁻⁵ %** | **PASS** (4 orders of magnitude margin) |
| T-C1.K03.tight | distributed-vs-50sec max mag-err < 1 % (D-C target) | 95 cells | max **2.7·10⁻⁵ %** | **PASS** |
| **T-C1.K04** | mean Phase-2 vs Phase-1 cross-platform loc-err improvement ≥ 30 % at SNR_I ≤ 30 dB | 1 080 cells | **−830.82 %** (NEGATIVE) | **xfail strict — R1 escalation** |
| T-C1.5x | forward-model error 5× better than v1 R-L-only on (α, R_x) = (0.95, 5000) | 1 cell | distributed 4.4·10⁻⁵ % vs v1 87.5 % (~2·10⁶ × better) | **PASS** |
| T-C1.analytical_eq_fd | analytical and FD optimisers reach same fixed point on well-conditioned cells | 2 cells | \|Δα\| < 10⁻³, \|ΔR_x\|/R_x < 5·10⁻³ | **PASS** |
| T-C1.analytical_fewer_J | analytical uses < 50 % of FD's J evaluations | 1 cell | analytical 0 extra J/grad vs FD 5 J/grad | **PASS** |
| T-C1.backcompat | Phase-1 baseline opts still import + run | 1 cell | finite (α, R_x) returned, cpu_time > 0 | **PASS** |
| **T-C1.manuscript** | manuscript v2 updated with §§II/III/IV/VI/abstract/conclusion changes | inspection | done; 5 new macros, 4 new subsections, 1 new figure float, K04 honest reporting | **PASS** |
| **T-C1.response** | `docs/IEEE_Access_response_v1.md` complete with anticipated reviewer comments mapped to manuscript line numbers | inspection | done; 8 anticipated comments R1–R8, KPI mapping table, 3 editor-flagged items | **PASS** |
| `make test` | full suite passes | — | **52 passed + 1 skipped + 9 xfailed** (all xfails carry R-class escalation reason text) | **PASS** |
| `ruff check .` | lint clean | — | "All checks passed!" | **PASS** |

**Gate-blocker summary.** D2's two primary predicates split:

* **K03 (forward-model accuracy)** is **PASS** with a 4-orders-of-magnitude margin and a 5× regression test certifying the v1 R-L-only ceiling is retired.
* **K04 (cross-platform estimator improvement)** is **xfail strict at −830.82 %**, traced to the single-bin DFT identifiability floor that the corrected CRLB of §VIII predicts. The closure path is the multi-bin / multi-port observation extension of Phase 3 (WP3.5 / WP3.6) and is the subject of the planned IEEE TPWRD follow-on.
* **Manuscript and reviewer-response** are complete and ready for editor circulation.

## 3. Risk-register update

| ID | Status entering Phase 2 | Action this phase | Status exiting Phase 2 |
|---|---|---|---|
| **R2** 39.44 % section-modelling-error ceiling | Med / Med (downgraded at D1) | WP2.1 closed-form distributed model + WP2.3 50-section tightening + WP2.5 5× regression test | **CLOSED** (forward-model side) |
| **R5** Single-bin DFT bias | High / Med | empirically certified by WP1.5 MC backfill (all 2880 cells statistically significantly biased) and by WP2.5 K04 negative result | **OPEN, CERTIFIED**; closes at WP3.5 + WP3.6 |
| **R12** Cost-surface degeneracy in (α, R_x) | open at D1 | WP2.4 diagonal-Newton + analytical-gradient + geomspace R_x grid mitigate but do not break the degeneracy; K04 negative result is the empirical evidence | **OPEN**; closes at WP3.5 + WP3.6 (multi-bin observation breaks the degeneracy by adding observation channels) |
| **R6** Categorical comparison non-quantitative | open at D1 | WP2.6 §VII placeholder retained with explicit scope statement deferring numerical shootout to WP4.5 / TPWRD follow-on | **OPEN**; closes at WP4.5 |
| **R7** Symbolic derivation errors | Low / Med | WP2.2 MATLAB sym/diff cross-check on the analytical gradients; rel-err 10⁻⁹ | **DOWNGRADED** (Low / Low) |
| **R10** Real HIF more random than diode arc | Med / Med | unchanged this phase | **OPEN**; closes at WP4.3 / WP4.4 / WP5.3 |

**No new risks added in Phase 2.**

The WP2.5 K04 negative result is the empirical certification of R12 (cost-surface degeneracy) and R5 (single-bin DFT bias), not a new risk class. R12 → WP3.5/WP3.6 closure path was already in the v3 plan; the K04 result confirms that a forward-model swap alone cannot substitute for the multi-bin extension.

## 4. KPI snapshot (post-Phase-2)

| # | KPI | Target | Phase-2 measurement | Status |
|---|---|---|---|---|
| K01 | Mean location error, AWGN, SNR_I = 30 dB (self-consistent) | < 1.0 % | self-cons unchanged from D1: 0.005 % noiseless / 1.18 % at SNR_I = 20 dB | **PASS** |
| K02 | Max location error, AWGN, SNR_I = 30 dB (self-consistent) | < 5 % | self-cons unchanged from D1: 0.04 % noiseless | **PASS** |
| **K03** | Forward-model error vs 50-section ref | < 5 % | mean **4.3·10⁻⁶ %** / max **2.7·10⁻⁵ %** | **PASS** (4 orders of magnitude margin) |
| **K04** | Phase-2 vs Phase-1 cross-platform improvement at SNR_I ≤ 30 dB | ≥ 30 % | **−830.82 %** (negative) | **FAIL — escalated to WP3.5/WP3.6** |
| K11 | Public repo + Zenodo DOI | live at D1 | repo private; v0.4.0-phase2 tag local | **GATED** (PI signoff for public flip) |
| K12 | Corrected CRLB | live at D1 | live and consumed by §VI.D analysis (proper-ratio CRLB explains K04 result) | **PASS** |
| K13 | CI green build rate (rolling 30 days) | ≥ 95 % | green on this commit; trend pending | n/a (insufficient history) |
| K14 | Reviewer-response turnaround on D-A artefact | ≤ 30 days from comments arriving | author-anticipated v1 response document complete; awaiting comments | **READY** |

## 5. Decision recommendation

**Recommend (b) Conditional approval to progress to Phase 3.**

Justification:

* **K03 is PASS** with a 4-orders-of-magnitude margin and a 5× regression test that retires the v1 R-L-only modelling-error ceiling. The forward-model side of R2 is closed.
* **K04 is FAIL** with the failure mode (cost-surface degeneracy of the single-bin DFT identifiability) identified, **certified empirically** by both the WP1.5 100-trial MC (all 2880 cells statistically significantly biased) and the WP2.5 K04 measurement (−830.82 %), and **predicted by the corrected CRLB** of §VIII. The closure path (WP3.5 Taylor–Fourier multi-bin + WP3.6 multi-port FIM) was already in the v3 plan; the K04 result sharpens its priority from optional to mandatory.
* **Manuscript v2 is complete** with §§II.A/II.B/II.C bodies, §§III/IV bodies, §§VI.A–D K01–K04 honest reporting, abstract Phase-2 line, conclusion Phase-2 sentence, new figure float for the Phase-2 SNR_I sweep with CRLB overlay, and 5 new headline macros for byte-identical numerics across abstract / §VI / §IX / glossary.
* **Author-response document is complete** (`docs/IEEE_Access_response_v1.md`), anticipating 8 reviewer comments R1–R8 mapped to specific manuscript line numbers, with explicit handling of the K04 negative result and 3 items flagged for editor attention. To be re-versioned to v2 once actual reviewer comments arrive.
* **Test gate is green:** 52 passed + 1 skipped + 9 xfailed (all xfails documented with R-class escalation reason text); ruff clean.
* **Tag `v0.4.0-phase2` created locally**; push deferred to PI green light per the WP2.6 brief.

**Pre-progression items (≤ W15 Mon):**

1. PI green light to push `v0.4.0-phase2` tag to the SAMBPS-DTaaS GitHub remote.
2. PI confirmation on whether to circulate the v2 manuscript + the v1 anticipated response document to the IEEE Access editor proactively (vs. waiting for reviewer comments to arrive and re-versioning the response to v2).
3. Lead engineer's canonical PSCAD and EMTP-RV runs on the licensed Windows stations so the per-cell cross-platform comparison `outputs/phase1_pscad_vs_emtp.csv` can be refreshed and `test_full_grid_consistency` xfail removed.

## 6. Publication artefact

* **Camera-ready manuscript v2.0** — `docs/manuscript_v2.pdf` rebuilt this commit (was 5 pages at end of D1; now ~6 pages with the §II.A/B/C, §III, §IV, §VI.A/B/C/D bodies and the new Phase-2 figure float).
* **Appendix A (state-space + symbolic ∂H/∂θ)** — `docs/AppendixA_derivation.pdf` (5 pages; §A.7 added at P2.2 covers the closed-form distributed-parameter gradient).
* **Appendix B (corrected CRLB derivation)** — `docs/AppendixB_correctedCRLB.pdf` (3 pages; unchanged from D1).
* **Author response document v1** — `docs/IEEE_Access_response_v1.md`. Anticipated reviewer comments mapped to manuscript line numbers; to be re-versioned when actual comments arrive.
* **Reproducibility code** — release tag `v0.4.0-phase2` (created locally; push gated on PI signoff).
* **Phase-2 outputs** — `outputs/phase2_modelfit.csv`, `outputs/phase2_reproduction.csv`, `outputs/phase2_estimator_improvement.csv`, `outputs/phase2_summary_per_cell.csv`, `outputs/phase2_vs_phase1_delta.csv`, `outputs/phase2_results_per_dataset.parquet`, `outputs/phase2_figs/{a..f}_*.png`, `outputs/phase2_hyperparam_sensitivity.csv`.
* **WP1.5 backfill (288 000-row MC)** — `outputs/phase1_montecarlo_results.parquet`, `outputs/phase1_montecarlo_summary.csv`, `outputs/phase1_figs/mc_distribution_*.png` (45 panels).

## 7. Signoff

| Role | Name | Signature | Date |
|---|---|---|---|
| Principal Investigator | Anoop Eluvathingal | _pending_ | _pending_ |
| Lead Engineer | Arjundas K. | _pending_ | _pending_ |
| Host Advisor | Prof. K. Shanthi Swarup | _pending_ | _pending_ |
| EMT Cross-Validation Reviewer | Prof. Christian Rehtanz, TU Dortmund | _pending — invited per R1 in WP1.2_ | _pending_ |
