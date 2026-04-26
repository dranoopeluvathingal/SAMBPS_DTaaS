# Thesis-Design Study: IBR-Aware Distance Protection for Transmission Lines

**Source corpus:** `/root/phd_thesis/03_technical_reports/phase_3_distance/` (TR-28 through TR-37; 10 reports, ~4000 LaTeX lines, ~4100 sampled fault scenarios in Monte Carlo + parametric sweeps)
**Date of study:** 2026-04-25
**Status:** First-pass thesis-design proposal — review, redirect, or refine before any thesis-authoring action.

---

## 1. Executive summary

The Phase 3 corpus is a **tightly coherent body of work suitable for a focused PhD thesis** on distance protection of inverter-based-resource (IBR) fed transmission lines. Ten technical reports decompose the IBR-distance-protection problem into a four-region failure-mode map, design five protection elements that each close one identified gap, integrate them into a verified scheme, extend to auto-reclosing, and probabilistically seal the result with a Monte Carlo reliability assessment of $P_{\text{dep}} = 99.61\%$ at $k_{\text{ibr}} \geq 0.06$ pu.

**Thesis-defensibility verdict:** The corpus carries **a single load-bearing PhD-grade contribution claim** (a complete IBR-line distance-protection scheme down to $k_{\text{ibr}} = 0.06$ pu, with the grid-code argument that follows from it) that decomposes naturally into 5 sub-claims, each anchored by ≥ 1 TR. Methodology is internally consistent (analytic + Python parametric framework, single radial test network, reused IBR FRT model). Validation footprint is non-trivial (~4 100 sampled scenarios) but **not hardware-validated, not EMT-validated, and not field-validated** — these are the principal additional work items required to bring the thesis to defence-grade. Estimated 12–18 months of additional empirical work to close the validation gaps; 6–9 months of authoring work on top of that. Total time-to-defence estimate: **18–27 months from this study**.

The corpus is best positioned as **a thesis on transmission-line protection** (NOT distribution self-healing — that is the separate MAS-DT-SH thesis tracked in `MAS_DT_SH/`). The two theses are non-overlapping and could be defended sequentially or in parallel; this document proposes the structure for the distance-protection thesis only.

---

## 2. Source corpus — contribution-bearing claims per TR

| TR | Topic | Defensible novelty claim | Region of failure-mode map closed |
|---|---|---|---|
| TR-28 | Synthesis of TR-03..TR-27 | (handshake) — establishes the SAMBP differential half | — |
| TR-29 | IBR impedance trajectory | $Z_m^{\text{IBR}}=Z_m^{\text{SG}}$ proof; problem decomposition into 4 regions | — (problem definition) |
| TR-30 | Cross-polarised Mho | Decay-invariance proof: operate boundary fixed at $\alpha Z_L = X_{R1}$ regardless of $V_{\text{mem}}$ decay magnitude | A (1ϕ-fault polarisation) |
| TR-31 | Zero-sequence compensation | Structural distinction $k_0$-as-line-parameter vs $k_0$-compensated-measurement; identifies SLG over-estimation as 3–8× systematic, un-fixable by retuning | A (SLG measurement bias) |
| TR-32 | 67N / 67Q sequence directional | 67N has *inherent* forward selectivity on pure-IBR line (delta blocks reverse $I_0$); 67Q lowers detection floor 60% below distance | A (asymmetric faults) |
| TR-33 | POTT on IBR lines | Repurpose 87L pilot as POTT carrier — zero added hardware; recovers Region B with 32 ms trip vs 300 ms conventional | B (3ϕ memory expiry) |
| TR-34 | Quadrilateral distance | Closed-form $R_{\text{fwd}}$ rule parameterised on $k_{\min}$; identifies structural impossibility region ($k_{\text{ibr}}<0.15 \wedge R_{\text{arc}}>0.006$ pu) | C (arc resistance) |
| TR-35 | Full IBR distance coordination | First fully-integrated 5-element time-ladder; zero gaps for $k_{\text{ibr}} \geq 0.06$; identifies the 0.06 pu floor as a physics limit | (integration verification) |
| TR-36 | Auto-reclose with IBR | Counter-intuitive result: IBR current-limiting *reduces* arc deionisation time vs SG; 87L+67Q/N as memory-independent second-trip elements | (operational extension) |
| TR-37 | Monte Carlo reliability | $P_{\text{dep}}=99.61\%$ on 4 000 trials; all 15 misses share $k_{\text{ibr}}<0.06$ — single root cause; explicit grid-code argument | (probabilistic seal) |

The **5 distinct novelty claims** that survive into PhD-grade contribution slots are:
1. **Region-decomposition framework** (TR-29) — the four-region $(\alpha, k_{\text{ibr}})$ failure map and the three structural failure modes ($I_{\min}$ blocking, $V_{\text{relay}}$ deficiency, memory expiry) that organise every subsequent design choice.
2. **Decay-invariant cross-pol Mho** (TR-30) — formal proof that the operate boundary is independent of memory-decay magnitude on inductive lines.
3. **Sequence-directional + pilot-POTT scheme** (TR-32 + TR-33) — 67N/67Q for Region A asymmetric, 87L-pilot-POTT for Region B 3ϕ; together they cover what distance alone cannot.
4. **Quadrilateral-with-closed-form-$R_{\text{fwd}}$** (TR-34) — arc-resistance coverage as a parameterised design rule, plus identification of the structural impossibility region.
5. **Probabilistic-reliability + grid-code argument** (TR-37) — quantified $P_{\text{dep}}$ and the IBR-fault-current-floor policy claim that follows.

---

## 3. Candidate research questions

Five RQs, each anchored on identified TRs, mapped 1:1 to candidate contributions in §4:

- **RQ1.** What are the *structural* failure modes of conventional distance protection on IBR-fed transmission lines, and how do they decompose across the $(\alpha, k_{\text{ibr}})$ parameter plane? *(→ C1; TR-29.)*
- **RQ2.** Can polarisation-based and reach-shape modifications of the Mho characteristic restore meaningful Zone-1 / Zone-2 coverage on IBR lines, and what are the analytical operating envelopes of the modified characteristics? *(→ C2; TR-30, TR-31.)*
- **RQ3.** Can sequence-directional elements (67N, 67Q) and pilot-permissive logic (POTT) close the residual coverage gaps that distance characteristics cannot, using only signals already available in the conventional protection path? *(→ C3; TR-32, TR-33.)*
- **RQ4.** Can a quadrilateral characteristic with closed-form arc-resistance reach setting cover the high-resistance fault regime under IBR infeed amplification, and what is the structural impossibility boundary beyond which no distance characteristic can operate? *(→ C4; TR-34.)*
- **RQ5.** What dependability does the integrated five-element scheme achieve under realistic statistical fault distributions, and what minimum IBR fault-current contribution does this imply for grid-code policy? *(→ C5; TR-35, TR-36, TR-37.)*

Each RQ is *answerable* from existing material with the stated level of rigour. The validation gaps in §7 affect the *strength* of the answer (analytic + parametric + Python-MC) rather than its existence.

---

## 4. Candidate thesis contributions

Patterned after the C1..C5 structure used in the MAS-DT-SH thesis. Each contribution maps 1:1 to an RQ and an "evidence carrier" set of TRs:

| ID | Contribution | Gap closed in literature | Evidence carrier |
|---|---|---|---|
| **C1** | A four-region decomposition of the IBR-distance-protection problem with the three structural failure modes ($I_{\min}$, $V_{\text{relay}}$, memory expiry) made operationally precise on the $(\alpha, k_{\text{ibr}})$ plane | Existing literature treats IBR distance issues as a single "weak-source" complaint; this thesis decomposes the failure into independently treatable components | TR-29 |
| **C2** | A cross-polarised Mho design with an analytical decay-invariance proof on inductive lines, plus a structural treatment of $k_0$ residual compensation that distinguishes line-parameter validity from measurement validity under IBR sources | Literature treats memory polarisation as an empirical setting; this thesis gives a closed-form decay-invariant operate boundary | TR-30, TR-31 |
| **C3** | A three-element redundancy package (67N + 67Q + 87L-pilot POTT) that closes the residual Region A and Region B gaps using only signals already present in the conventional protection path, with formal reverse-fault-security proofs | Literature proposes individual sequence-directional elements; this thesis integrates them with a 0-added-hardware POTT scheme and proves selectivity end-to-end | TR-32, TR-33 |
| **C4** | A quadrilateral distance characteristic with a closed-form $R_{\text{fwd}}$ design rule parameterised on minimum IBR penetration, plus identification of the *structural impossibility* region beyond which no distance characteristic can operate | Literature uses heuristic $R_{\text{fwd}}$ settings; this thesis derives the rule from first principles and bounds the impossibility region quantitatively | TR-34 |
| **C5** | A probabilistic dependability assessment of the integrated five-element scheme ($P_{\text{dep}} = 99.61\%$ on 4 000 trials), with all residual misses traced to a single structural cause ($k_{\text{ibr}}<0.06$ pu) — supporting an explicit IBR-fault-current minimum as a grid-code policy claim | Literature reports pass/fail on parametric tests; this thesis closes with a quantified reliability claim AND a derived grid-code recommendation | TR-35, TR-36, TR-37 |

The contribution structure has the same shape as MAS-DT-SH's C1..C5 (problem decomposition → element-design → integration → reliability/policy) but on a different research axis (transmission distance protection, not distribution self-healing).

---

## 5. Proposed chapter structure

Three structural alternatives, each defensible. **Recommendation: Option B** — a clean three-part structure with one chapter per contribution claim plus a rounded-out introduction/methodology/conclusion frame. Same 7-chapter shape as a typical IIT Madras PhD thesis.

### Option A — TR-by-TR (10 chapters; not recommended)

Maps each TR to a chapter. Very faithful to the source corpus but produces an over-fragmented thesis with chapter-level redundancy in problem statement and methodology sections. **Not recommended** for PhD defence.

### Option B — Three-act structure (recommended; 7 chapters)

| Ch | Title | Source TRs | Word target |
|---|---|---|---|
| 1 | Literature Review — distance protection from SG-era to IBR-era | (synthesis from corpus + new lit search) | 8000–10000 |
| 2 | Problem Statement, Research Questions, Contributions | (frames RQ1..RQ5, C1..C5) | 3000–4000 |
| 3 | **Act I:** Theory and problem decomposition — apparent-impedance trajectory, polarisation analysis, sequence-network breakdown | TR-29, TR-30, TR-31 | 12000–15000 |
| 4 | **Act II:** Element design — sequence-directional, pilot POTT, quadrilateral characteristic | TR-32, TR-33, TR-34 | 12000–15000 |
| 5 | **Act III:** Integrated scheme, auto-reclose, and Monte Carlo reliability | TR-35, TR-36, TR-37 | 12000–15000 |
| 6 | Validation — EMT + HIL + (optionally) field-trace replay | (NEW work; see §8) | 8000–10000 |
| 7 | Conclusion, Grid-Code Recommendations, Future Work | (synthesis) | 4000–5000 |

Total target: **60 000–75 000 words** (typical IITM PhD thesis range).

The "three-act" framing — *theory → element design → integration & reliability* — matches the natural arc of the corpus (TR-29–34–37 form a clear narrative axis) and gives examiners a structurally clean reading path.

### Option C — Five-chapter contribution-driven (less common, faster to author; 5 chapters)

| Ch | Title | Source TRs |
|---|---|---|
| 1 | Introduction (lit review + RQs + Cs combined) | (corpus + lit search) |
| 2 | C1+C2: Problem decomposition and polarisation theory | TR-29, TR-30, TR-31 |
| 3 | C3+C4: Element design and integration | TR-32, TR-33, TR-34, TR-35 |
| 4 | C5: Reliability, auto-reclose, grid-code policy | TR-36, TR-37 |
| 5 | Conclusion and future work | — |

Faster to author (~50 000 words) but examiners may flag the compressed introduction. **Acceptable but only if you're under time pressure.**

---

## 6. Methodology already established (reusability)

The corpus has converged on a remarkably consistent toolchain:

**Test network.** Single radial: Generator → $Z_{\text{src}}$ → Bus A → $Z_{\text{line}}$ → Bus B → $Z_{\text{tr}}$ → Bus C. Per-unit base: $Z_{\text{src}} = j0.10$, $Z_{\text{line}} = j0.05$, $Z_{\text{tr}} = j0.30$ pu (with X/R = 20 from TR-32 onward). All 10 TRs use this network — no benchmark drift.

**IBR FRT current model.** $I_{\text{ibr}} = k_{\text{ibr}} e^{j\phi_{\text{FRT}}}$ with $k_{\text{ibr}} \in [0.06, 0.20]$ pu and $\phi_{\text{FRT}} \approx -90°$. Single archetype across all TRs.

**Relay settings.** Zone-1/2/3 reaches $X_{R1} = 0.040$ / $X_{R2} = 0.060$ / $X_{R3} = 0.090$ pu; memory hold $T_{\text{mem}} = 100$ ms (IEC 60255-121); $I_{\min} = 0.10$ pu (distance), $0.04$ pu (sequence directional). Reused TR-29 onward without retuning.

**Simulation tooling.** Python-based parametric framework (`run_pott_study.py`, `run_quad_study.py`, `run_coordination_study.py`); Monte Carlo with seed = 42 (TR-37, mirrors TR-08). All scripts at `/root/phd_thesis/04_code/sambp/distance/` (verify paths).

**Statistics.** Wilson confidence intervals (TR-26 precedent applied in TR-37); Monte Carlo trial count 4 000 (TR-37) — could be expanded to 10 000+ if needed for tighter CIs.

**Reusability for thesis.** The reused infrastructure means **the thesis methodology chapter writes itself** — there is no methodological inconsistency to reconcile. This is one of the strongest properties of the corpus from a thesis-defence perspective.

---

## 7. Validation footprint and sufficiency assessment

### What's already in hand

| Validation type | Coverage | Sufficient for PhD defence? |
|---|---|---|
| Analytical proofs | Decay-invariance (TR-30), $Z_m^{\text{IBR}}=Z_m^{\text{SG}}$ (TR-29), 67N inherent selectivity (TR-32), $R_{\text{fwd}}$ closed form (TR-34) | ✅ Yes — analytic claims are defended by analytic proofs |
| Parametric sweeps | 48-cell coordination matrix (TR-35), 36 Region-B cases (TR-33), various smaller sweeps | ✅ Yes for problem-decomposition and element-design claims |
| Monte Carlo | 4 000 trials TR-37 + 4 000-trial sensitivity sub-studies + 4 000-trial TR-08 differential side + 15 000-trial TR-26 IBR differential | ⚠ Sufficient for $P_{\text{dep}}$ point estimate; **needs Wilson CI** for security and external-fault selectivity |
| EMT-domain | None | ❌ **Required** — phasor-domain analysis must be backed by at least one EMT validation (PSCAD, ATP-EMTP, or RTDS) |
| Hardware-in-loop | None | ⚠ Strongly preferred but optional if EMT is thorough |
| Field data | None | ⚠ Optional — strengthens the thesis but rare in IBR-protection PhDs |
| Comparative benchmarking | None | ❌ **Required** — must compare against ≥ 1 published commercial-relay scheme or utility R&D proposal |

### Quantitative scenario count

- ~4 100 Monte Carlo + parametric scenarios in distance arc (TR-29–37)
- ~19 000 cumulative if differential-arc TR-26 trials are counted via TR-28
- This is **strong by IBR-protection-PhD standards** for in-silico validation but **weak for empirical claims** without EMT/HIL backup

### Single-network limitation

All distance work uses one radial test feeder. The 87L/87T/87B differential work in the SAMBP corpus (TR-03..27) covers radial + double-busbar, but the distance arc is single-topology. **Examiners will ask about parallel lines, mutual coupling, multi-terminal lines, and weak-grid stability.** None of these are in the current corpus.

---

## 8. Gaps requiring additional work to make the thesis complete

Ranked by impact-on-defensibility:

### Priority 1 — must close before defence

**G1 — EMT validation of ≥ 3 representative scenarios.** Run 3-phase Region B (TR-33), arc-resistance worst-case (TR-34), and POTT external-fault-security (TR-35) scenarios in PSCAD, ATP-EMTP, or RTDS. Compare phasor-domain predicted trip times against EMT-domain measured times. Publishable as a chapter-6 section. **Effort: 3–4 months.**

**G2 — Comparison with at least one published commercial scheme.** Pick one of: weak-infeed logic (Schweitzer Engineering Labs SEL-411L), IBR-aware Mho (Toshiba GRZ200), or a published utility R&D proposal (e.g. NGESO IBR protection studies). Reproduce its reach settings and run it on the same TR-35 scenario set. Show the SAMBP scheme's coverage advantage (or honest acknowledgement of where it doesn't have one). **Effort: 2–3 months.**

**G3 — Wilson CI on security/external-fault-rejection rate.** TR-37 reports $P_{\text{dep}}$ but not external-fault selectivity as a probability with CI. Re-run the Monte Carlo with explicit external-fault sampling and report TPR/FPR/PPV/NPV with Wilson 95% CIs (mirror the TR-26 reporting style). **Effort: 1 month.**

### Priority 2 — strongly preferred

**G4 — At least one alternative IBR archetype.** Replace the generic FRT current source with a detailed model of either (a) a Type-IV WT with grid-following control, (b) a utility-scale PV inverter with manufacturer-published FRT curve, or (c) a grid-forming inverter with virtual-synchronous-machine control. Show that the scheme's coverage envelope is robust to the IBR model choice. **Effort: 3–4 months.**

**G5 — Multi-terminal / parallel-line topology.** Extend the test network to (a) parallel-line coupled, or (b) three-terminal teed line. Show scheme coverage and identify any new failure modes. **Effort: 2–3 months.**

**G6 — Grid-code achievability analysis from the inverter side.** TR-35/37 propose a $k_{\text{ibr}} \geq 0.06$ pu grid code but the corpus contains no inverter-controller analysis showing this is achievable. Add a short chapter section showing the inverter-side cost (in current rating, control bandwidth, FRT envelope). **Effort: 2 months.**

### Priority 3 — nice-to-have

**G7 — HIL validation on a real IED.** Run the scheme on an SEL-421, SEL-411L, or ABB REL670 with the test scenarios injected via Omicron CMC. Demonstrate one full clearance event. **Effort: 4–6 months (depends on lab access).**

**G8 — Field-data replay.** Obtain real fault records from a utility (e.g. Indian PGCIL, NGESO, ERCOT) and replay them through the scheme. **Effort: 6+ months (depends on data access).**

**G9 — Sympathetic-tripping comprehensive study.** TR-33 mentions sympathetic tripping qualitatively; a focused study on a multi-feeder topology would strengthen C3. **Effort: 2 months.**

### Bare-minimum-defence summary

If you stop at **G1 + G2 + G3** the thesis is defensible at IIT Madras / IIT Delhi / IIT Kharagpur level. **G4–G6 strengthen it materially**; **G7–G9 are bonuses** that don't change defensibility but improve reviewer confidence and post-thesis publication potential. Total minimum-defence additional effort: **~6–8 months** of empirical work + ~6–9 months of authoring.

---

## 9. Risk factors and scope decisions

### Risk-1 — Phase 3 is part of a SAMBP umbrella that may want to be one thesis

The corpus repeatedly references the SAMBP framework as a unified scheme spanning differential (TR-03..27) AND distance (TR-28..37). One legitimate question is whether the thesis should cover **both halves** or only the distance-protection half.

- **Argument for both:** A single integrated thesis on "SAMBP — model-based protection for IBR-rich transmission" claims more, scopes more cleanly, and produces one defence rather than two.
- **Argument against both:** A 50-TR thesis would be ~150 000 words — too long for IITM PhD format. The differential half is already fully validated and could anchor a separate thesis or a series of journal papers.
- **Recommendation:** Write the **distance-half thesis** (this proposal) AS the PhD thesis. Differential half stays as a supporting foundation cited from Ch1/2 and used as the SAMBP "first half" architectural context. Ch6 §4.10 of the SAMBP synthesis (TR-28) explicitly hands off to the distance arc — this is your thesis-frame inheritance.

### Risk-2 — Single-archetype IBR limitation may attract examiner pushback

Generic FRT current source ($k_{\text{ibr}} e^{j\phi}$) is convenient but examiners may push on "what about Type-IV WT? what about GFM?" — G4 closes this.

### Risk-3 — No EMT validation is a hard examiner red flag

Phasor-domain analytics are mathematically rigorous but examiners in a protection field will ask "show me one EMT trace where the scheme trips correctly." G1 closes this.

### Risk-4 — Numbering inconsistencies in source corpus

Minor cross-reference drift in the TR sources (TR-29 forward-references "TR-34 POTT" when actual POTT is TR-33; TR-36 cites `\cite{SAMBP_TR33}` for TR-32 results). These need fixing during chapter authoring but are not technical content errors.

### Risk-5 — Test-network simplicity is honest but spartan

The single radial Gen→Z_src→Bus_A→Z_line→Bus_B→Z_tr→Bus_C testbed is simpler than typical thesis benchmarks. **Recommendation:** add a section in Ch1 explicitly defending the test-network choice as deliberate (pure-effect isolation; no confounding from network topology) rather than a limitation. Then close G5 (multi-terminal) to demonstrate the scheme generalises.

---

## 10. Comparison with literature (quick map)

A full literature survey is Ch1 work; the following is a placeholder showing where the thesis sits in the field:

| Theme | Representative prior work | This thesis differentiator |
|---|---|---|
| IBR fault-current limiting impact on distance | Hooshyar 2014, IEEE PES IBR Task Force 2018, Fang 2021 | Region-decomposition framework (C1) — most prior work treats IBR distance as a single weak-source problem |
| Cross-polarised Mho on weak sources | Roberts & Guzman 1995, Mooney 2008 | Decay-invariance proof (C2) — most prior work uses empirical settings |
| Sequence-directional on IBR | Quispe 2019, Bayrak 2021 | Inherent-selectivity proof for 67N on pure-IBR delta-blocked lines (C3) |
| POTT on weak sources | IEEE C37.113-2015, Schweitzer 2017 | Pilot-channel-reuse argument (zero added hardware; C3) |
| Quadrilateral arc-resistance on IBR | Andrade 2018, Tziouvaras 2018 | Closed-form $R_{\text{fwd}}$ design rule parameterised on $k_{\min}$ (C4) |
| Reliability assessment for IBR protection schemes | Khan 2020, Saleh 2022 | Quantified $P_{\text{dep}}$ + grid-code policy argument (C5) |

A proper Ch1 lit review needs ~30–50 references across these themes. The corpus's existing bibliographies (`references28.bib` through `references37.bib`) are a starting point but will need expansion to cover non-IBR-specific distance-protection literature.

---

## 11. Recommended path forward

### Phase A (months 1–3): close G3 + scope confirmation
1. Confirm thesis scope decision (distance-only vs SAMBP-unified) — discuss with supervisor.
2. Re-run TR-37 Monte Carlo with explicit external-fault sampling; produce Wilson CIs (G3).
3. Write the Chapter 1 literature review skeleton (5000–7000 words; first-pass draft).
4. Write Chapter 2 problem-statement / RQ / contribution chapter (first pass, ~3000 words).

### Phase B (months 4–9): close G1, G2; first-pass thesis chapters
5. Set up a PSCAD or ATP-EMTP test environment matching the radial test network.
6. EMT-validate ≥ 3 scenarios: 3ϕ Region B, arc-resistance worst-case, external-fault selectivity (G1).
7. Reproduce one published commercial scheme on same scenario set (G2).
8. Author Chapters 3, 4, 5 first-pass drafts (~30 000 words combined).

### Phase C (months 10–15): close G4 + G5 + G6
9. Add detailed Type-IV WT or GFM IBR model; rerun coordination + MC studies (G4).
10. Extend to parallel-line or three-terminal topology (G5).
11. Add inverter-side grid-code achievability analysis (G6).
12. Author Chapter 6 validation chapter (~10 000 words).

### Phase D (months 16–18+): integrate, polish, defend
13. Finalise Chapter 7 conclusion + grid-code recommendation.
14. Integration pass across all 7 chapters; cross-reference fixing; figure regeneration.
15. Supervisor review cycles.
16. Synopsis preparation; defence preparation.

### Optional Phase E: HIL / field validation
G7 + G8 — push these post-thesis into journal submissions if access materialises during Phase B-D.

### Publication strategy

The corpus naturally supports **5 journal papers** post-thesis:
- Paper 1: Region-decomposition + cross-pol Mho theory (TR-29 + TR-30) — IEEE Trans. Power Delivery
- Paper 2: 67N/67Q + POTT integration (TR-32 + TR-33) — IEEE Trans. Power Delivery
- Paper 3: Quadrilateral with $R_{\text{fwd}}$ closed-form rule (TR-34) — IEEE Trans. Power Delivery
- Paper 4: Full integration + Monte Carlo reliability (TR-35 + TR-37) — IEEE Trans. Power Systems
- Paper 5: Grid-code recommendation + cost-benefit analysis (TR-37 + new G6 work) — Electric Power Systems Research or similar

---

## 12. Summary + decision points for the user

**The corpus is thesis-grade.** A focused PhD thesis on *IBR-Aware Distance Protection for Transmission Lines* with the proposed C1..C5 contribution structure is defensible at top-tier Indian and international institutions, conditional on closing G1 (EMT validation), G2 (comparative benchmarking), and G3 (Wilson CIs on security).

**Decision points the user needs to make:**

1. **Thesis scope:** distance-only (this proposal) vs. SAMBP-unified (covers both differential + distance halves). **Recommendation: distance-only.**
2. **Chapter structure:** Option A / B / C from §5. **Recommendation: Option B (three-act, 7 chapters).**
3. **Validation depth:** bare-minimum (G1–G3 only) vs. full (G1–G6) vs. comprehensive (G1–G8). **Recommendation: aim for G1–G6 if time allows; G1–G3 is the floor for defence.**
4. **Title direction.** Proposed: *"State-Adaptive Model-Based Distance Protection for Inverter-Based-Resource Transmission Lines"* — but several alternatives are defensible:
   - *"Distance Protection Schemes for IBR-Rich Transmission Networks"*
   - *"Apparent-Impedance Trajectory and Coordinated Protection in Inverter-Dominated Power Systems"*
   - *"Adaptive Mho/Quadrilateral Distance Protection with Sequence-Directional Backup for IBR-Fed Lines"*

**Next steps after user review of this study:**

- If the proposal is broadly accepted: I can help author the **synopsis** (the institutional 6–8 page document that opens the PhD-registration process at IITM) using the contribution structure here.
- If more detail is needed: I can dispatch follow-up focused studies on specific gaps (e.g. literature-review depth analysis, EMT-toolchain selection, IBR-archetype trade-off analysis).
- If the proposal is rejected: redirect — I can re-do the analysis under a different framing (e.g. SAMBP-unified) or apply this same template to a different corpus.

---

*This document is a first-pass design study, not a thesis-authoring commitment. All numbers in §5 / §7 / §8 (word targets, effort estimates) are indicative; calibrate against your supervisor's expectations and your time budget.*

*The 10 TR sources, the cross-cutting findings, and the C1..C5 / RQ1..RQ5 contribution structure are the load-bearing technical content. The chapter-structure proposal, the gap analysis, and the path-forward sequence are advisory — adjust freely.*
