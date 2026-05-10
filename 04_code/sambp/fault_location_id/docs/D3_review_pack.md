# D3 — Phase 3 Decision Gate Review Pack

**Project:** SAMBPS DTaaS — `fault_location_id`
**Phase:** 3 — three-phase, multi-section, branched-feeder + IEEE PES test feeders + multi-class faults + Taylor–Fourier + multi-port CRLB + public-dataset validation (W14–W26)
**Gate:** D3 — Phase-3 conference paper drafted; CNRS validation pipeline runs end-to-end; multi-port CRLB consistency at machine precision; R5 closed; tag `v0.5.0-phase3` (defer push)
**Issued:** 2026-05-10
**Author:** Anoop Eluvathingal (PI)
**Cosignatory:** Prof. K. Shanthi Swarup (host advisor)

> Format mirrors §8.1 of `docs/FaultLocationIdentification_ExecutionPlan.pdf`
> (decision-gate template); D0 / D1 / D2 precedents at
> `docs/D0_review_pack.md`, `docs/D1_review_pack.md`,
> `docs/D2_review_pack.md`.

---

## 1. Phase summary

Phase 3 ran eight work packages WP3.1 – WP3.8 from W14–W26:

* **WP3.1 / P3.1** Three-phase Y_send (closed-form distributed-parameter cascaded ABCD with shunt fault on phase A; 6×6 matrix-exponential per uniform line section). Validated against an independent 50-section lumped-π surrogate to max per-entry rel-err **1.4 × 10⁻⁶** on the 720-grid (5 orders of magnitude tighter than the brief 5 % target). 4 tests PASS.
* **WP3.2 / P3.2** Branched extension: lateral + tap load + DG. Tree-walk look-back admittance reduction; per-cell consistency at **2.1 × 10⁻⁷** across 90 unique (α, R_x, fault_branch) cells. 6 tests PASS.
* **WP3.3 / P3.3** IEEE 13 / 34 / 123 test feeders + Kersting-2002 line codes 601-607. Backward / forward sweep power-flow solver with constant-Z loads. **K07 strict 1 %** target unmet (~14 % gap from Kersting Tab. 4.10 due to deferred regulator + transformer + capacitor banks); relaxed 25 % "framework lives" check PASS. 8 tests PASS / 1 xfail-strict.
* **WP3.4 / P3.4** SLG / LL / LLG fault types + multi-type classifier outer loop. **K08 95 %** classification target unmet at SNR_I ≥ 30 dB on the simplified IEEE 34: measured 74.51 % (load dilutes per-entry fault signature on high-R_x cells). Noiseless 100 % framework-lives check PASS. 8 PASS + 1 xfail-strict.
* **WP3.5 / P3.5** Taylor–Fourier K=1 phasor estimator + identifiability map + Hermann–Krener ORC indicator + Villaverde 2024 STRIKE-GOLDD reference. **K06 ≥ 50 % bias-improvement** target met at **55.94 %** mean improvement at the brief representative case (α=0.5, R_x=2000 Ω, SNR_I=30 dB) on a Wang-2020-style arc stimulus. 7 + 13 tests PASS. **R5 CLOSED.**
* **WP3.6 / P3.6** Multi-port FIM: proper-complex-Gaussian-ratio + joint dual-channel CRLB on the 3 × 3 Y_send observation surface (18 real obs vs 2 unknowns). Per-cell consistency at **machine precision** (max abs deviation = 6.66 × 10⁻¹⁶ across 300 cells at SNR_I = 40 dB). AppendixB §B.5 added. 9 tests PASS.
* **WP3.7 / P3.7** External validation against the public CNRS / Recherche Data Gouv IEEE 34-node HIF dataset (DOI 10.57745/KRYCYY). Per-file SHA-256 manifest + end-to-end pipeline + 50-trace CSV + 2 overlay PDFs. **K05 deferred** (train.zip is the unsupervised slice; labelled test.zip ~ 3 GB held back behind `--include-test` due to dev-box constraints). Manuscript v2 §VI.E added with cite to PereiraDeSouza2024CNRS. 4 tests PASS.
* **WP3.8 / P3.8** _(this commit)_ Phase-3 conference paper draft + this D3 review pack + tag `v0.5.0-phase3`.

A total of **121 tests pass + 1 skipped + 11 xfail** (all xfails carry documented R-class escalation reason text); **ruff clean**.

## 2. Acceptance-test results

| Test ID | Source | Predicate | Measured | Status |
|---|---|---|---|---|
| **K03** | forward-model error vs 50-section ref < 5 % | 95 cells | mean **4.3·10⁻⁶ %** / max **2.7·10⁻⁵ %** | **PASS** (4 OOM margin) |
| **K05** | mean loc-err < 3 % on IEEE 34 (CNRS labelled) at SNR_I ≥ 30 dB | 1550 traces | — | **DEFER** (test.zip) |
| **K06** | TFT-K=1 phasor-bias improvement ≥ 50 % vs DFT (arc stimulus) | 200 trials | **55.94 %** mean | **PASS** |
| **K07** | multi-port proper / dual CRLB consistency within 5 % at SNR_I = 40 dB | 300 cells | **6.66 × 10⁻¹⁶** max abs dev | **PASS** (machine precision) |
| **K08** | SLG / LL / LLG classification accuracy ≥ 95 % at SNR_I ≥ 30 dB | 4500 trials | **74.51 %** | **XFAIL strict** (R-WP3.4-1) |
| **T-D5.5x** | 5× regression on (α, R_x) = (0.95, 5000) | 1 cell | distributed 4.4·10⁻⁵ % vs v1 87.5 % | **PASS** |
| T-D7.sha256 | per-file SHA-256 of fetched CNRS artefacts recorded | 4 files | manifest written | **PASS** |
| T-D7.csv | CNRS validation CSV produced | 50 traces | rows + per-trace estimates | **PASS** |
| `make test` | full Phase-3 suite | — | **121 passed + 1 skipped + 11 xfailed** | **PASS** |
| `ruff check .` | lint clean | — | "All checks passed!" | **PASS** |

**Gate-blocker outcome:**

* **K06** is **PASS** at 55.94 % mean bias improvement.
* **K07** is **PASS** at machine precision.
* **K05** is **DEFERRED** with documented root-cause (the CNRS train slice is unsupervised; labelled test slice is 3 GB and held back behind `--include-test` after dev-box safety hook intercepted the auto-fetch). Mitigation path documented in the changelog: lead engineer fetches via `--include-test` on the licensed Windows runner.
* **K08** is **XFAIL strict** at 74.51 %; R-WP3.4-1 escalation forwards closure to (i) WP3.3 follow-up canonical IEEE 34 line codes and (ii) WP3.5/3.6 multi-bin / multi-port observation lifting the per-entry SNR on the fault signature.

## 3. Risk-register update

| ID | Status entering Phase 3 | Action this phase | Status exiting Phase 3 |
|---|---|---|---|
| **R3** Multi-class fault discrimination | OPEN at D2 | WP3.4 implements SLG / LL / LLG outer loop with 100 % noiseless accuracy; 74.5 % at SNR_I ≥ 30 dB | **DOWNGRADED** (Med/Med); closes at WP3.5 + WP3.6 + WP3.3 follow-up |
| **R5** Single-bin DFT bias | OPEN at D2 | WP3.5 closes via TFT-K=1 (55.94 % bias reduction) + Hermann-Krener ORC certified everywhere; WP3.6 multi-port supplies √9 information accumulation | **CLOSED** |
| R-WP3.3-1 | NEW at WP3.3 | IEEE 13/34/123 power-flow gap (~14 %); 6 IEEE 13 features deferred + IEEE 34/123 line codes deferred | **OPEN**; closes at WP3.3 follow-up |
| R-WP3.4-1 | NEW at WP3.4 | IEEE 34 fault-type classification accuracy gap (74.5 % vs 95 % brief target) | **OPEN**; closes at WP3.5/3.6 + WP3.3 follow-up |
| R-WP3.7-1 | NEW at WP3.7 | K05 measurement requires labelled CNRS test.zip (~ 3 GB); held back by dev-box safety hook | **OPEN**; closes at lead engineer's licensed-Windows follow-up |
| R6 (categorical comparison) | OPEN at D2 | unchanged this phase | **OPEN**; closes at WP4.5 |
| R10 (real HIF stochasticity) | OPEN at D2 | unchanged this phase | **OPEN**; closes at WP4.3 / WP4.4 / WP5.3 |

**Net Phase-3 risk movement:** R5 CLOSED; R3 DOWNGRADED; 3 new R-classes OPEN (all with documented mitigation paths to specific follow-up WPs).

## 4. KPI snapshot (post-Phase-3)

| # | KPI | Target | Phase-3 measurement | Status |
|---|---|---|---|---|
| K01 | self-consistent loc-err | < 1 % | unchanged from D1: 0.005 % noiseless / 1.18 % at SNR_I = 20 dB | **PASS** |
| K02 | self-consistent max loc-err | < 5 % | unchanged from D1 | **PASS** |
| **K03** | forward-model error | < 5 % | mean 4.3·10⁻⁶ % / max 2.7·10⁻⁵ % | **PASS** (4 OOM margin) |
| K04 | Phase-2 cross-platform improvement | ≥ 30 % | unchanged from D2: -830.82 % (XFAIL strict; R1 escalation) | **FAIL — escalated** (closure at WP3.5 / WP3.6 multi-bin) |
| **K05** | mean loc-err on CNRS labelled set | < 3 % | — | **DEFER** (test.zip) |
| **K06** | TFT bias improvement | ≥ 50 % | **55.94 %** mean | **PASS** |
| **K07** | multi-port CRLB consistency | within 5 % at SNR_I = 40 | **6.66 × 10⁻¹⁶** | **PASS** (machine precision) |
| **K08** | fault-type classification | ≥ 95 % at SNR_I ≥ 30 dB | 74.51 % | **XFAIL** (R-WP3.4-1) |
| K11 | public repo + Zenodo DOI | live at D2 | repo private; v0.5.0-phase3 tag local | **GATED** (PI signoff for public flip) |
| K12 | corrected CRLB | live at D1 | live + extended to multi-port at WP3.6 | **PASS + EXTENDED** |
| K13 | CI green build rate | ≥ 95 % | green on this commit | n/a (insufficient history) |
| K14 | reviewer-response turnaround | ≤ 30 days | author-anticipated v1 from WP2.6; awaiting actual reviewer comments | **READY** |

## 5. Decision recommendation

**Recommend (b) Conditional approval to proceed to Phase 4 (or to continue Phase-3 follow-up if PI prefers depth-first closure of R-WP3.3-1, R-WP3.4-1, R-WP3.7-1 before opening Phase 4).**

Justification:

* **K06 is PASS** at 55.94 % mean bias improvement; **R5 is CLOSED** structurally + empirically.
* **K07 is PASS** at machine precision; the multi-port CRLB framework is correct and the proper-ratio / dual-channel consistency identity is certified entry-by-entry under V-noiseless balanced operation.
* **K08 is XFAIL** at 74.51 %; R-WP3.4-1 escalation forwards closure to documented follow-up paths.
* **K05 is DEFERRED** with documented mitigation; not blocking on PHASE-LEVEL approval but blocking on the WP3.7 follow-up commit.
* The Phase-3 conference paper draft is complete; current page count is **4 pages** in the IEEEtran conference template (the WP3.8 brief target was 6 pages — the draft is dense; can extend to 6 with additional results figures or discussion if PES GM / ISGT reviewers request depth).
* All open R-class items have explicit closure paths in the follow-up commits or in Phase 4 / Phase 5 work packages.

**Pre-progression items (≤ W27 Mon):**

1. PI green light to push `v0.5.0-phase3` tag to remote (along with the WP2.6 push that is also pending).
2. PI direction on conference venue: **IEEE PES GM 2027 (Apr deadline)** vs **ISGT 2027 (Sep deadline)**.
3. PI confirmation on whether to extend the conference paper to a strict 6 pages (additional figures or extended discussion) or to submit at 4 pages.
4. Lead engineer's CNRS test.zip pull on the licensed Windows runner so K05 can be measured and reported.

## 6. Publication artefact

* **Phase-3 conference paper** — `docs/Phase3_conference_paper.pdf`. 4 pages (target was 6 per WP3.8 brief; can extend if PI prefers). Title: "Three-Phase, Multi-Section, Branched-Feeder Single-Ended Joint HIF Estimation with Multi-Port CRLB and Public-Dataset Validation". Structured as: intro + related-work + model (P3.1–P3.4) + TFT (P3.5) + multi-port CRLB (P3.6) + CNRS validation (P3.7) + KPI table + 3 figures + conclusions.
* **Camera-ready manuscript v2.0** — `docs/manuscript_v2.pdf` (8 pages at end of WP3.7; was 7 at end of WP2.6, 5 at end of WP1.6).
* **Appendix A (state-space + symbolic + closed-form gradients)** — `docs/AppendixA_derivation.pdf` (5 pages; unchanged this phase).
* **Appendix B (corrected CRLB derivation + multi-port projection)** — `docs/AppendixB_correctedCRLB.pdf` (4 pages; +1 page at WP3.6 for §B.5 multi-port projection).
* **Reproducibility code** — release tag `v0.5.0-phase3` (created locally; push gated on PI signoff).
* **Phase-3 outputs** — see the phase-3 entries in `docs/changelog.md`.
* **CNRS dataset** — `data/cnrs_ieee34/` with per-file SHA-256 manifest.

## 7. Signoff

| Role | Name | Signature | Date |
|---|---|---|---|
| Principal Investigator | Anoop Eluvathingal | _pending_ | _pending_ |
| Lead Engineer | Arjundas K. | _pending_ | _pending_ |
| Host Advisor | Prof. K. Shanthi Swarup | _pending_ | _pending_ |
| EMT Cross-Validation Reviewer | Prof. Christian Rehtanz, TU Dortmund | _pending — invited per R1 in WP1.2_ | _pending_ |
| External-Dataset Reviewer | Dr. J. Yang (CNRS) | _pending — invited per R-WP3.7-1_ | _pending_ |
