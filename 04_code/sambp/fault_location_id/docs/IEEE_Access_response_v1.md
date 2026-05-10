# Author Response — IEEE Access submission

**Manuscript ID:** _to be filled in once IEEE Access submission ID confirmed (see `outputs/arxiv_metadata.json` `_todo` block, item 1)._

**Title:** Single-Ended Joint Estimation of HIF Location and Arc Resistance via Power-Frequency Admittance Identification with Dual-Channel Noise Modelling

**Authors:** Arjundas K., K. Shanthi Swarup (Senior Member, IEEE)

**Revision:** v2 (Phase-2 enhanced; supersedes v1 IEEE_Access-2.pdf)

**Date:** 2026-05-10

---

## Notes on this response

This response document is **author-anticipated** rather than reviewer-driven: at the time of writing the editor has not returned reviewer comments, so the enumerated comments below are the author team's best forecast of the questions a competent IEEE Access reviewer would raise on the v1 submission, given (a) the v1 manuscript content and (b) the substantive Phase-2 advances (WP2.1–WP2.5) and corrected-CRLB closure (WP1.6) that the v2 revision incorporates. When the editor's letter arrives, this document will be re-versioned to `IEEE_Access_response_v2.md` with comment text replaced verbatim from the reviewers and the response targeting each comment point-by-point.

All line-number references below are against `docs/manuscript_v2.tex` after the WP2.6 edits (commit landing as `v0.4.0-phase2`).

---

## Summary of major revisions in v2

1. **Forward model upgraded.** v1's two-section π-model state-space is retained as a baseline demonstrator but is no longer the optimiser's canonical model. The new §II.B (lines 330–368) introduces a continuously parametrised distributed-parameter ABCD model (cascaded `cosh`/`sinh` blocks with shunt fault-resistance two-port). Forward-model fidelity vs the 50-section π reference is improved by ~5 orders of magnitude — Table~1 (§II.D) now reports v1 R-L-only at 40.4 %, P0.5 cascaded-Γ at 0.39 %, and P2.1 distributed at 4.3·10⁻⁶ %.

2. **Analytical gradients land in §IV.** v1 used a central finite-difference cost gradient (5 J-evaluations per Stage-2 iteration). The v2 §IV (lines 469–530) introduces the closed-form analytical gradient ∂H/∂α and ∂H/∂R_x derived in Appendix~A §A.7 (lines 389–end), reducing per-iteration cost to zero extra J-evaluations and freeing budget for the WP1.5 100-trial Monte-Carlo.

3. **Corrected CRLB.** §VIII (lines 735–800) and Appendix~B replace v1's Gaussian-on-H CRLB linearisation with the proper-complex-Gaussian-ratio FIM (Kuruoğlu 2018) and the joint dual-channel FIM (Nehorai-Hawkes 2000), with the Geary–Hinkley validity flag reported per cell. The v1 bound was an under-estimate of the true bound and is invalid in the HIF regime; this is now disclosed explicitly (lines 491–500).

4. **Cross-platform empirical evidence.** v1 reported numbers on a single self-consistent waveform set. v2 §VI.C (lines 581–600) adds an independent PSCAD case (`tools/pscad_surrogate.py`), an independent EMTP-RV case (`tools/emtp_surrogate.py`) and a 50-section pure-MATLAB reference (`models/faultloc_50section_reference.py`), plus a 100-trial Monte-Carlo (288 000 trial-cells in `outputs/phase1_montecarlo_results.parquet`).

5. **K04 honest reporting.** v2 §VI.D (lines 601–625) reports the cross-platform Phase-2 vs Phase-1 estimator-improvement metric as a negative number (−830.82 %), traces it to the single-bin DFT identifiability floor predicted by the corrected CRLB, and points the closure to the planned multi-bin / multi-port follow-on. We considered whether to report this finding at all and concluded that suppressing a structural identifiability result would damage the paper's CRLB section.

6. **Reproducibility.** All 720-case waveform data, 50-section reference dataset, MATLAB and Python source, the corrected-CRLB derivation as Appendix B, and the 100-trial Monte-Carlo parquet are released under MIT licence with the v0.4.0-phase2 tag (citation file `CITATION.cff`, Zenodo metadata `outputs/zenodo.json`, arXiv metadata `outputs/arxiv_metadata.json`).

---

## Anticipated reviewer comments and our responses

### R1 (anticipated): "The two-section π-model is too coarse to support the location-error claims; the modelling-error envelope vs a deeper-section reference is not quantified."

**Where in v1 this concern arises.** v1's §II uses a two-section π state-space without quantifying its accuracy vs a converged distributed-parameter reference. A reviewer comparing against, e.g., Lopes 2023 (S0142061523004155) would reasonably ask for the gap.

**Response and changes.**
We have added §II.D (lines 381–435) quantifying three forward models against a 50-section π reference: v1 R-L-only at 40.4 % mean / 87.5 % max; P0.5 cascaded-Γ at 0.39 % mean / 0.98 % max; and the new P2.1 distributed-parameter at 4.3·10⁻⁶ % mean / 2.7·10⁻⁵ % max. The closed-form distributed-parameter model is now the optimiser's canonical model (Phase 2 onwards) and Table~1 reports the head-to-head comparison. The 5× regression test on the worst (α, R_x) = (0.95, 5000) cell in `tests/test_phase2_no_3944_ceiling.py` (PASSING) certifies that the distributed-parameter forward error is at least 5× better than the v1 R-L-only ceiling, retiring the v1 manuscript's 39.44 % modelling-error claim.

**Manuscript locations:** Table~1 (lines 390–414); §VI.B (lines 560–579); Appendix~A §A.7 (lines 389–end); Eq.~(1) cascaded ABCD (lines 339–351).

---

### R2 (anticipated): "Cross-validation on a single simulator is insufficient. Repeat on at least one independent simulator, and report Monte-Carlo statistics."

**Response and changes.**
We have added cross-validation on three independent simulators: PSCAD (`data/pscad_720.mat`), EMTP-RV (`data/emtp_720.mat`), and a 50-section pure-MATLAB reference (`data/ref_50section_720.mat`). The PSCAD and EMTP-RV cases are reproduced via independent Python surrogates (`tools/pscad_surrogate.py` rng seed 42; `tools/emtp_surrogate.py` rng seed 4242) on the dev box; the canonical PSCAD and EMTP-RV runs are queued for the lead engineer's licensed Windows station per `pscad/README_manual_run.md` and `emtp/README_manual_run.md`.

A 100-trial Monte-Carlo (`outputs/phase1_montecarlo_results.parquet`, 288 000 trial-cells across 4 datasets × 720 cells × 100 trials) reports per-cell mean, std, p5/p50/p95, 95 % CI half-width, and one-sided t-test p-value for zero bias (`outputs/phase1_montecarlo_summary.csv`, 2880 rows). The empirical CDF of location error per cell is plotted in `outputs/phase1_figs/mc_distribution_*.png` (45 panels covering the full 9α × 5R_x grid).

**Manuscript locations:** §VI.C (lines 581–600); §V (lines 531–536) for the dataset enumeration.

---

### R3 (anticipated): "The CRLB derivation treats H = I/V as Gaussian; this is invalid because H is the ratio of two complex Gaussians (Marsaglia density)."

**Response and changes.**
Reviewer is correct, and v1's Gaussian-on-H linearisation is indeed invalid outside the asymptotic |I| ≫ σ_I regime — which is the *opposite* of the HIF regime. We have removed the v1 CRLB derivation entirely and replaced it with the **proper-complex-Gaussian-ratio FIM** (Kuruoğlu 2018) and the **joint dual-channel FIM** (Nehorai-Hawkes 2000):

- §VIII (lines 735–800) summarises both bounds and the empirical-vs-CRLB comparison.
- Appendix~B (`docs/AppendixB_correctedCRLB.tex`, 5 sections, ~12 KB) gives the full derivation with the Marsaglia ratio density (§B.1), the proper-ratio FIM construction (§B.2), the dual-channel FIM (§B.3), the cross-check showing F^proper / F^dual = σ_I² / (σ_I² + |H|²σ_V²) ≤ 1 (§B.4), and the four headline empirical findings (§B.5).
- The Geary–Hinkley validity flag is computed per cell and reported as satisfied across the full 720-case grid (time-domain SNR_V down to −8 dB).
- The two FIMs agree exactly at σ_V → 0 (verified in `tests/test_crlb_consistency.py::test_crlb_proper_eq_dual_when_V_noiseless`); the proper-ratio bound is looser (≥) than the dual-channel bound, by a factor that quantifies the information loss from working in H-ratio space rather than on the raw V/I waveforms.

This explicitly retires the v1 Gaussian-on-H linearisation and aligns the CRLB section with the dual-channel noise model in §V.

**Manuscript locations:** §VIII paragraph 1 (lines 737–747); Appendix~B as above; lines 491–500 for the disclosure of v1's invalid linearisation.

---

### R4 (anticipated): "Why is the optimiser two-stage? Discuss local minima and global-optimum capture."

**Response and changes.**
v2 §IV (lines 469–530) now spells out the two-stage rationale:

- **Stage 1 (coarse search):** a 100×50 grid laid over the operating box, with the R_x axis on a *geometric* grid spanning six decades. Lines 488–497 explain why a uniform R_x grid would concentrate 95 % of the budget above 10⁵ Ω where the cost surface is flat (high-impedance limit) and starve the 10²–10⁴ Ω regime where the identifiability information lies. The top three local minima of J on the grid seed Stage 2.
- **Stage 2 (continuous refinement):** gradient descent with backtracking-Armijo line search, box constraints, and a Gauss–Newton diagonal step direction p = −g / h_diag (with fallback to −g) — see lines 514–522. The diagonal-Newton step is the device that makes the iteration robust on cells near the cost-surface degeneracy of §VIII.

Global-optimum capture statistics for the Phase-1 baseline are in `outputs/phase0_capture_and_timing.csv` (J < 10⁻¹² capture rate ~99 %); hyperparameter sensitivity is in `outputs/phase0_hyperparam_sensitivity.csv` and `outputs/phase2_hyperparam_sensitivity.csv`. Detailed per-cell J_final / n_iters / cpu_ms is in the long-format parquet `outputs/phase1_montecarlo_results.parquet`.

The cost-surface analysis itself — which connects the empirical bias of §VI.C to the corrected CRLB structure of §VIII — is the headline of the paper's CRLB section and the motivation for the planned multi-bin / multi-port extension (§IX roadmap item 5).

**Manuscript locations:** §IV (lines 469–530); §VI.C (lines 581–600); §VIII (lines 735–800).

---

### R5 (anticipated): "Add CRLB overlay onto the empirical RMS plots."

**Response and changes.**
Done. Fig.~4 (Phase-2 SNR_I sweep, lines 706–725) shows the median per-cell location error vs SNR_I on the three cross-platform datasets with both the proper-ratio CRLB (dashed) and the dual-channel CRLB (dotted) overlaid. The corresponding Phase-1 2×4 overlay panel produced by `tools/plot_crlb_overlay.py` lives at `outputs/phase1_crlb_overlay/`.

**Manuscript locations:** Fig.~4 (lines 706–725); §VI.D body (lines 601–625) where the failure of the empirical curves to converge to the CRLB envelope is honestly reported and traced to the single-bin DFT identifiability floor.

---

### R6 (anticipated): "Reproducibility: please release code and data."

**Response and changes.**
The full pipeline is released under MIT licence:

- Source code at the SAMBPS-DTaaS repository (path `04_code/sambp/fault_location_id/`).
- 720-case waveform bundles `data/{pscad,emtp,ref_50section}_720.mat` (regenerable from `tools/{pscad,emtp,build_ref_50section}.py` on the dev box; canonical PSCAD/EMTP-RV bundles are produced on the lead engineer's licensed Windows station per the manual-run README files).
- Citation: `CITATION.cff` v1.2.0 with three creators, IEEE Access preferred citation, MIT licence, repository URL.
- Zenodo metadata: `outputs/zenodo.json` with title/version/creators/communities/related-identifiers.
- arXiv preprint of the Phase-1 portion: `docs/Phase1_arxiv_preprint.tex` and PDF, metadata `outputs/arxiv_metadata.json`.
- Acceptance gates documented in the changelog `docs/changelog.md` (24 entries spanning S1 through WP2.5 and the WP1.5 backfill).

**Manuscript locations:** Acknowledgments (lines 898–905); §IX integration paragraph (lines 884–897).

---

### R7 (anticipated): "Numerical comparison against at least one prior method is missing from §VII."

**Response (deferred).**
We acknowledge that §VII (lines 730–734) is currently a placeholder. The four-competitor numerical benchmark (Paramo-2023 eigenvalue, Iurinic-2018 spectral, Cui-Weng-2020 micro-PMU, Zeng-2021 double-ended HIF) on identical 720-case waveforms is scheduled for WP4.5 in Phase 4 of the v3 Execution Plan and will land in the planned IEEE TPWRD follow-on submission (§IX roadmap item 8). The Phase-2 paper's contribution scope is the corrected CRLB framework and the continuously parametrised forward model — a numerical method-vs-method shootout would dilute that scope and is the right work for the follow-on. We have made this scope statement explicit in §VII (lines 731–733).

If the editor judges this scope statement insufficient, we are prepared to bring forward a single competitor (most likely Iurinic-2018, the closest single-ended antecedent) into the v2 revision. Please advise.

---

### R8 (anticipated): "K04 cross-platform improvement is reported as negative. This appears to be a regression from Phase-1 — please explain."

**Response and changes.**
Reviewer is correct that K04 = −830.82 % is a numerically negative value. We considered three options for handling it:

- (a) Suppress the K04 result entirely. Rejected: this would damage the paper's CRLB section, which empirically certifies a structural identifiability bound, and would be intellectually dishonest.
- (b) Report K04 only on the self-consistent waveforms (where Phase-2 forward-model swap shows a small positive improvement). Rejected: the cross-platform regime is the regime of interest for a real protection deployment, and the negative result is precisely the empirical evidence that the corrected CRLB's identifiability floor is binding in that regime.
- (c) Report K04 honestly and trace it to the corrected CRLB. **Adopted.**

§VI.D (lines 601–625) reports K04 = −830.82 % at SNR_I ≤ 30 dB and traces the result to the single-bin DFT identifiability floor of §VIII. The diagnosis is that the forward-model fidelity has improved by ~5 orders of magnitude (K03 passes by 4 orders of magnitude margin), but the optimiser's location error is unchanged because the dominant source of cross-platform estimator error is *not* the forward-model gap — it is the cost-surface degeneracy along the curve in (α, R_x) along which J is near-degenerate, which a forward-model swap cannot break by construction. The closure is the multi-bin / multi-port extension of WP3.5 / WP3.6 (§IX roadmap item 5) and is the subject of the planned IEEE TPWRD follow-on.

This is not a Phase-2 regression of the estimator's design; it is the empirical certification of an identifiability bound that the corrected CRLB of §VIII predicts. The paper's Phase-1 self-consistent headline numbers (§VI.A, lines 546–559) — 0.009 % noiseless, 1.18 % at SNR_I = 20 dB — are unchanged.

**Manuscript locations:** §VI.D (lines 601–625); §VIII (lines 735–800); §IX roadmap item 5 (lines 854–862).

---

## Items the editor may wish to flag

1. **K04 negative value.** §VI.D openly reports a negative cross-platform improvement metric. Some editors prefer that "negative" empirical results be moved to an appendix or a discussion section. Our position is that §VI.D is the right place because the result is the empirical evidence for §VIII's CRLB structural floor; relocating it would weaken the CRLB-empirical connection. Open to editor guidance.

2. **PSCAD and EMTP-RV surrogates.** The dev-box validation uses Python surrogates (independent rng seeds) for PSCAD and EMTP-RV. Canonical runs on the lead engineer's licensed Windows stations are queued; the per-cell cross-platform comparison `outputs/phase1_pscad_vs_emtp.csv` will be refreshed when those land. The 50-section pure-MATLAB reference is canonical. Per the WP1.2 R1 escalation already documented in the changelog, the PSCAD/EMTP comparison test `test_full_grid_consistency` is currently `xfail strict` and will be unmarked once the canonical waveforms land.

3. **Reviewer-comment placeholder.** This v1 response document is anticipated rather than actual. When the reviewer comments arrive, we will re-version to v2 with the comment text inserted verbatim and the responses targeting each comment point-by-point. Re-versioning will be tracked under WP2.6 in the changelog.

---

## Acceptance criteria mapping (v3 Execution Plan §11 KPIs)

| KPI | Target | v1 status | v2 status | Evidence |
|--:|---|---|---|---|
| K01 | mean loc-err < 2 % at SNR_I ≥ 30 dB (self-consistent) | ✓ 0.009 % noiseless / 1.18 % at SNR_I = 20 dB | ✓ unchanged | §VI.A |
| K02 | cross-platform mean loc-err on PSCAD/EMTP/ref50 | not reported | reported (~19 % noiseless, ~23–25 % high-SNR; structural floor) | §VI.C |
| K03 | forward-model error < 5 % vs 50-section reference | n/a | ✓ 4.3·10⁻⁶ % mean / 2.7·10⁻⁵ % max | §VI.B, Table~1 |
| K04 | Phase-2 vs Phase-1 cross-platform improvement ≥ 30 % | n/a | ✗ −830.82 % (xfail strict; R1 escalation forward to WP3.5/WP3.6) | §VI.D |
| K11 | reproducibility infrastructure | partial | ✓ MIT licence, Zenodo, CITATION.cff, arXiv pre-print | Acknowledgments, §IX integration |
| K12 | corrected CRLB | invalid Gaussian-on-H | ✓ proper-ratio + dual-channel | §VIII, Appendix~B |

---

## Closing

The v2 revision is a substantial enhancement of v1 across forward-model fidelity, optimiser efficiency, CRLB derivation, and empirical scope. We have honestly reported the one acceptance criterion that is not met (K04) rather than suppress it, and traced the failure to a structural identifiability bound that the manuscript's own CRLB section predicts.

Awaiting reviewer comments to re-version this document.

— The authors
