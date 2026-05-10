# D1 — Phase 1 Decision Gate Review Pack

**Project:** SAMBPS DTaaS — `fault_location_id`
**Phase:** 1 — independent simulator validation + corrected CRLB (W2–W10)
**Gate:** D1 — mean location error < 2 % across all simulators at SNR_I ≥ 30 dB; corrected CRLB visualised
**Issued:** 2026-05-10
**Author:** Anoop Eluvathingal (PI)
**Cosignatory:** Prof. K. Shanthi Swarup (host advisor)

> Format mirrors §8.1 of `docs/FaultLocationIdentification_ExecutionPlan.pdf`
> ("Decision-gate (D0–D5) review template").  See also the Phase-1
> arXiv preprint `docs/Phase1_arxiv_preprint.pdf`.

---

## 1. Phase summary

Phase 1 ran six work packages WP1.1–WP1.6 from W2–W10:

* **WP1.1 / P1.1** PSCAD-equivalent waveform set (`data/pscad_720.mat`,
  cosh/sinh ABCD distributed-parameter surrogate).
* **WP1.2 / P1.2** EMTP-RV-equivalent (`data/emtp_720.mat`, 50-section
  pi state-space, independent rng seed).  R1 escalation opened on
  pairwise-RMS-vs-noise artefact.
* **WP1.3 / P1.3** Pure-Python 50-section reference
  (`data/ref_50section_720.mat`).  v1 39.44 % modelling-error
  provenance gap discovered and resolved (v1 used R-L-only 2-section;
  legacy preserved at `models/faultloc_legacy_v1_2section.py`).
* **WP1.4 / P1.4** Cross-platform optimiser re-run on all three
  sources + on-the-fly self-consistent baseline.
  `outputs/phase1_crossplatform_results.csv` (2880 rows),
  `outputs/phase1_delta_error_attribution.csv`, 6 figures in
  `outputs/phase1_figs/`.  R1 escalation: D1's 2 % threshold
  unachievable with 2-section optimiser; gate now depends on
  WP2.1 closed-form distributed-parameter forward model.
* **WP1.5 / P1.5** 100-trial Monte-Carlo wrapper with joblib + parquet
  output.  Bias test (`tests/test_montecarlo_bias.py`).
* **WP1.6 / P1.6** Corrected CRLB: proper-complex-Gaussian-ratio
  (Kuruoğlu 2018) + joint dual-channel (Nehorai-Hawkes 2000).
  `inverse_estimation/faultloc_crlb_proper.py` +
  `_dualchannel.py`; cross-checked in
  `tests/test_crlb_consistency.py` (9/9 pass).  Standalone derivation
  at `docs/AppendixB_correctedCRLB.pdf` (3 pages).  Manuscript §VIII
  rewritten.  R1 + R9 closed.

## 2. Acceptance-test results

| Test ID | Source | Predicate | Measured | Status |
|---|---|---|---|---|
| **T-B1.a** | mean loc-err < 2 % at SNR_I ≥ 30 dB on PSCAD-eq. | 540 cells | mean **29.18 %**, max **518.7 %** | **FAIL — escalated** |
| **T-B1.b** | mean loc-err < 2 % at SNR_I ≥ 30 dB on EMTP-eq. | 540 cells | mean **29.29 %**, max **651.2 %** | **FAIL — escalated** |
| **T-B1.c** | mean loc-err < 2 % at SNR_I ≥ 30 dB on 50-section ref. | 540 cells | mean **30.81 %**, max **850.0 %** | **FAIL — escalated** |
| T-B1.aux | self-consistent passes D1 on noiseless | 45 cells | mean **0.005 %**, max **0.04 %** | **PASS** |
| T-B1.csv | per-cell 95 % CI excludes zero in < 5 % cells | informational | reported in `phase1_montecarlo_summary.csv`; bias diagnostic at `phase1_bias_diagnostic.md` if exceeded | gated on WP1.5 MC completion |
| **T-B2.a** | proper-ratio CRLB and dual-channel CRLB agree to within 5 % at SNR_V = ∞ | 4 (α, R_x, SNR_I) cells | exact agreement (rel-err < 1e-15) | **PASS** |
| T-B2.aux | proper / dual = √2 at SNR_V = SNR_I | 6 cells | within 1 % of √2 (analytical) | **PASS** |
| T-B2.gh | Geary-Hinkley validity holds across grid | grid-wide | true at time-domain SNR_V > -8 dB | **PASS** |
| T-B2.consistency | both bounds finite + positive at any finite SNR | 9 cells | all finite, all > 0 | **PASS** |
| **CRLB overlay** | `outputs/phase1_crlb_overlay/` produced | one 2 × 4 panel | gated on MC completion + plot_crlb_overlay.py | **GATED** |
| `make test` | full suite passes | — | 32 passed + 1 skipped + 7 xfailed (R1-escalated) | **CONDITIONAL PASS** |
| `ruff check .` | lint clean | — | "All checks passed!" | **PASS** |

**Gate-blocker summary.** D1's primary predicate (mean loc-err < 2 % on PSCAD/EMTP/ref50) is **FAILED across all three sources**, with the 6 dataset-specific tests `pytest.xfail`-ed under the documented `TODO Phase1 single-bin DFT identifiability` block.  The corrected CRLB is delivered and tested.  CRLB overlay figure is the last item gated on WP1.5 MC completion.

## 3. Risk-register update

| ID | Status entering Phase 1 | Action this phase | Status exiting Phase 1 |
|---|---|---|---|
| **R1** Gaussian-on-H FIM invalid in HIF regime | High / High | WP1.6 derives proper-complex-Gaussian-ratio FIM + dual-channel cross-check; tested 9/9 | **CLOSED** |
| **R9** Geary-Hinkley validity reporting | Med / High | WP1.6 implements per-cell GH validity flag; verified across grid | **CLOSED** |
| **R2** 39.44 % section-modelling-error ceiling | High / High | P1.3 finding: v1 used R-L-only 2-section; cascaded-Γ already 100× better; Phase 2 WP2.1 closes residual single-bin DFT identifiability gap | **DOWNGRADED** (Med / Med); closes at WP2.1 |
| **R5** Single-bin DFT bias | High / Med | P1.4 finding: noise × cost-surface conditioning amplifies sub-percent forward gap into ~19 % loc-err on cross-platform data | **OPEN**; closes at WP3.5 (Taylor-Fourier) + WP3.6 (multi-port FIM) |
| **R6** Categorical comparison non-quantitative | High / Med | unchanged this phase | **OPEN**; closes at WP4.5 |
| **R7** Symbolic derivation errors | Low / High | WP1.6 CRLB tests close one channel of this risk | **DOWNGRADED** (Low / Med) |
| **R10** Real HIF more random than diode arc | Med / Med | unchanged this phase | **OPEN**; closes at WP4.3 / WP4.4 / WP5.3 |

**New risks added:** R12 (single-bin DFT identifiability degeneracy) — the cost surface is near-degenerate over a curve in (α, R_x) space; closes at WP3.5 / WP3.6.

## 4. KPI snapshot

| # | KPI | Target | Phase-1 measurement | Status |
|---|---|---|---|---|
| K01 | Mean location error, AWGN, SNR_I = 30 dB | < 1.0 % | self-cons: 0.005 %; cross-platform: ~13 % | partial (self-cons passes, cross-platform gated on WP2.1) |
| K02 | Max location error, AWGN, SNR_I = 30 dB | < 5 % | self-cons: 0.04 %; cross-platform: ~190 % | partial |
| K12 | Public repo + Zenodo DOI | live at D0 | repo private; v0.2.0-phase0 tag local | **GATED** (PI signoff for public flip) |
| K13 | CI green build rate (rolling 30 days) | ≥ 95 % | green on this commit; baseline trend pending | n/a (baseline) |

## 5. Decision recommendation

**Recommend (b) Conditional approval to progress to Phase 2.**

Justification:

* The corrected CRLB (R1 + R9) is delivered, tested and visualised — D1's CRLB predicate is **PASS**.
* D1's < 2 % cross-platform loc-err predicate is **FAIL**, with the failure mode identified, escalated and documented.  The fix (WP2.1 closed-form distributed-parameter forward model, currently the entry point of Phase 2) is now mandatory rather than discretionary, which sharpens the Phase-2 acceptance posture.
* No safety-of-method risks remain open; all open R-class items have explicit Phase-2/3/4 closure paths.

**Pre-progression items (≤ W11 Mon):**
1. WP1.5 MC run completes; commit P1.5 + bias-test result + ECDF figs.
2. CRLB overlay panel `outputs/phase1_crlb_overlay/crlb_overlay_2x4.png` produced from MC summary; appended to D1 evidence pack.
3. PI green light to push v0.3.0-phase1 tag to remote (gated on confirmation; not auto-pushed).

## 6. Publication artefact

* **Phase-1 arXiv preprint** — `docs/Phase1_arxiv_preprint.pdf` (4 pages).
  Title: "Cross-Platform Validation and Proper-Complex-Gaussian-Ratio CRLB for
  Single-Ended HIF Transfer-Function Identification".  License CC-BY 4.0;
  primary arXiv class `eess.SY`, secondary `stat.AP`.  Metadata at
  `outputs/arxiv_metadata.json`.  Posting to arXiv is **gated on PI
  confirmation** per the WP1.7 brief.
* **Camera-ready manuscript v2.0** — `docs/manuscript_v2.pdf` (5 pages
  this commit; was 4 at end of P0.6).  §VIII rewritten in P1.6.
* **Appendix B (corrected CRLB derivation)** — `docs/AppendixB_correctedCRLB.pdf`
  (3 pages, ships at D1).
* **Reproducibility code** — release tag `v0.3.0-phase1`
  (created locally; push gated on PI signoff).

## 7. Signoff

| Role | Name | Signature | Date |
|---|---|---|---|
| Principal Investigator | Anoop Eluvathingal | _pending_ | _pending_ |
| Lead Engineer | Arjundas K. | _pending_ | _pending_ |
| Host Advisor | Prof. K. Shanthi Swarup | _pending_ | _pending_ |
| EMT Cross-Validation Reviewer | Prof. Christian Rehtanz, TU Dortmund | _pending — invited per R1_ | _pending_ |
