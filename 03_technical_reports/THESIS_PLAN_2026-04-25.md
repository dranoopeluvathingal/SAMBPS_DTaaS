# Thesis Plan — Locked Scope

**Title (locked):** *Design and Validation of Distance Protection Embedded in a SAMBP-Unified Framework with Communication and Cybersecurity Layer*

**Scope (locked):** The PhD thesis covers (i) the design of distance protection for IBR-fed transmission lines as the contribution centerpiece, (ii) embedding within the SAMBP unified protection framework that already covers the differential (87T/87L/87B) and supervisory chain, (iii) a dedicated communication-layer treatment (IEC 61850 GOOSE, wide-area protection, PMU, COMTRADE), and (iv) a dedicated cybersecurity-layer treatment (attack model, HMAC-SHA256 message integrity, anomaly detection). Validation depth is **comprehensive — G1 through G8** per the gap-analysis in `phase_3_distance/THESIS_DESIGN_STUDY_2026-04-25.md` §8.

**Status:** Working blueprint. This document supersedes the option-A "distance-only" framing in the earlier design study; that study's analysis (per-TR claims, RQ candidates, gap inventory) remains valid as the source material this plan builds on.

**Date:** 2026-04-25.

---

## 1. Source corpus across four pillars

| Pillar | Source TRs | Role in thesis |
|---|---|---|
| **A. SAMBP Differential Foundation** (Phase 1 + 2) | TR-01..27 (27 TRs) — Sync_OC, 87T/87L/87B, CT saturation, MC studies, IBR 87L integration | Architectural frame in Chapter 3; cited as the "first half" of the SAMBP scheme that distance protection embeds within |
| **B. Distance Protection** (Phase 3) — **CENTERPIECE** | TR-28..37 (10 TRs) — impedance trajectory, cross-pol Mho, $k_0$ analysis, 67N/67Q, POTT, quadrilateral, integration, AR, MC reliability | Chapters 4–6; primary contribution body |
| **C. Communication Layer** | TR-06 (IEC 61850 GOOSE), TR-14 (busbar GOOSE), TR-50 (WAPC), TR-77 (PMU/state estimation), TR-87 (COMTRADE) | Chapter 7; integration into protection chain |
| **D. Cybersecurity Layer** | TR-52 (GOOSE anomaly detection), TR-82 (HMAC-SHA256 GOOSE), TR-81 (GMD/GIC stress) | Chapter 8; attack model + mitigations + fallback |

Total citation footprint: ~50 TRs cited from the SAMBPS corpus, with the 10 distance TRs (Pillar B) carrying the primary contribution claims.

---

## 2. Research questions (revised for broader scope)

Seven RQs spanning the four pillars, all answerable from existing TRs + planned G1-G8 work:

- **RQ1** (Pillar A → C1) — *Architectural unification.* How should distance protection be embedded in the SAMBP unified protection framework so that the differential, distance, supervisory, communication, and cybersecurity layers compose into a coherent end-to-end scheme?
- **RQ2** (Pillar B → C2) — *Problem decomposition.* What are the structural failure modes of conventional distance protection on IBR-fed transmission lines, and how do they decompose across the $(\alpha, k_{\text{ibr}})$ parameter plane?
- **RQ3** (Pillar B → C3) — *Polarisation and reach-shape design.* Can polarisation-based and reach-shape modifications of the Mho/quadrilateral characteristic, with sequence-directional backup, restore complete and selective coverage on IBR-fed lines using only signals already available in the conventional protection path?
- **RQ4** (Pillar B → C4) — *Integrated scheme dependability.* What dependability does the integrated five-element distance scheme achieve under realistic statistical fault distributions, and what minimum IBR fault-current contribution does this imply for grid-code policy?
- **RQ5** (Pillar C → C5) — *Communication latency and reliability.* What latency and reliability budgets does IEC 61850 GOOSE / Sampled Values / wide-area protection (WAPC) impose on the integrated scheme, and how do they compose with the protection-element timing constraints (memory hold, AR dead time)?
- **RQ6** (Pillar D → C6) — *Cybersecurity envelope.* Under a documented attack model (spoofed GOOSE, replay, DT-state poisoning, denial-of-service), what mitigations preserve scheme integrity and what is the residual attack surface that remains?
- **RQ7** (cross-pillar → C7) — *End-to-end validation.* Does the integrated SAMBP-unified scheme — distance + differential + communication + cybersecurity layers — deliver the claimed reliability under EMT-domain, hardware-in-loop, and (where available) field-trace conditions?

Each RQ has a 1:1 contribution mapping (next section) and an evidence carrier set of TRs / experiments.

---

## 3. Contributions (revised — C1..C7)

Patterned after the C1..C5 structure used in the MAS-DT-SH thesis, expanded to seven contributions to cover the broader scope.

| ID | Contribution | Evidence carrier |
|---|---|---|
| **C1** | A unified protection-system architecture (SAMBP) in which differential, distance, supervisory, communication, and cybersecurity layers compose into a single coherent end-to-end scheme — with distance protection treated as a first-class layer integrated by design rather than added on | Pillar A (TR-01..27) + Ch3 architectural narrative |
| **C2** | A four-region decomposition of the IBR-distance-protection problem with the three structural failure modes ($I_{\min}$, $V_{\text{relay}}$, memory expiry) made operationally precise on the $(\alpha, k_{\text{ibr}})$ plane | TR-29 |
| **C3** | A coordinated five-element distance package (cross-pol Mho with decay-invariance proof, structural $k_0$ analysis, 67N/67Q sequence directional, 87L-pilot POTT, quadrilateral with closed-form $R_{\text{fwd}}$) that closes all four region-gaps using only signals already present in the conventional protection path | TR-30, TR-31, TR-32, TR-33, TR-34 |
| **C4** | A probabilistic dependability assessment of the integrated five-element scheme ($P_{\text{dep}} = 99.61\%$ on 4 000 trials), with all residual misses traced to a single structural cause ($k_{\text{ibr}}<0.06$ pu) — supporting an explicit IBR-fault-current minimum as a grid-code policy claim | TR-35, TR-36, TR-37 |
| **C5** | A communication-layer integration that delivers IEC 61850 GOOSE-grade latency for protection-critical signals (sub-4 ms) and Sampled-Values-grade fidelity for measurement-critical signals (sub-millisecond), with WAPC + PMU integration validated end-to-end against the integrated scheme's timing constraints | TR-06, TR-14, TR-50, TR-77, TR-87 + Ch7 work |
| **C6** | A cybersecurity-layer treatment (HMAC-SHA256 GOOSE message integrity, anomaly detection on telemetry, attack model covering spoofed-input / replay / state-poisoning / DoS classes) integrated with the protection scheme via a confidence-gated fallback that preserves safe behaviour under detected compromise | TR-52, TR-82 + Ch8 work |
| **C7** | An end-to-end validation campaign covering analytical proofs, EMT-domain simulation, hardware-in-loop testing, comparative benchmarking against published commercial schemes, and (where access permits) field-trace replay — quantifying integrated scheme reliability under realistic operating conditions | G1..G8 work + Ch9 |

The contribution structure has the architecture → element-design → integration → comm-layer → cyber-layer → end-to-end-validation arc characteristic of a tightly-scoped systems thesis. Each contribution maps to ≥ 1 chapter and ≥ 1 RQ.

---

## 4. Chapter structure (10 chapters, ~95–115k words)

### Part I — Foundation (Chapters 1–2)

#### **Chapter 1 — Literature Review** [~10 000 words]

A survey across all four pillars to position the thesis. Sub-sections:
- §1.1 Distance protection from synchronous-generator-era to IBR-era
- §1.2 IBR fault-current limiting and its impact on protection (FRT, GFL/GFM, current-limiting algorithms)
- §1.3 Differential protection (87T/87L/87B) under IBR conditions — survey of model-based vs measurement-based approaches
- §1.4 Communication infrastructure for protection (IEC 61850, GOOSE, Sampled Values, IEC 62439-3 PRP/HSR redundancy)
- §1.5 Cybersecurity for substation automation (NERC CIP-002..014, IEC 62351, IEC 62443)
- §1.6 Wide-area protection and control (WAPC) literature
- §1.7 Synthesis: the unfilled niche — distance protection embedded in a unified, communication-integrated, cyber-resilient SAMBP framework
- §1.8 Prior-work comparison matrix (similar to Ch1 in MAS-DT-SH)

#### **Chapter 2 — Problem Statement, Research Questions, Contributions** [~4 000 words]

Frames RQ1..RQ7 and C1..C7 explicitly. Modelled after MAS-DT-SH Ch2 (problem statement → RQs → objectives → contributions → scope).

### Part II — SAMBP Framework Frame (Chapter 3)

#### **Chapter 3 — SAMBP Unified Protection Framework** [~12 000 words]

The architectural frame in which distance protection lives. Sub-sections:
- §3.1 SAMBP design principles — model-based protection, Stage-2 confidence gate, multi-element redundancy
- §3.2 Differential foundation — 87T (transformer), 87L (line), 87B (busbar) with the model-based Stage-2 veto chain (TR-03..04, TR-09)
- §3.3 IBR-aware extensions of the differential chain — 87LN, 87LN0, TDCS, adaptive-TDCS (TR-22..27)
- §3.4 System integration scheme — radial + double-busbar topologies (TR-05, TR-07, TR-19)
- §3.5 Communication backbone — IEC 61850 GOOSE primitives (cross-ref Ch7)
- §3.6 The supervisory horizontal — Stage-2 statistic $\kappa_n$, confidence-gated trip authorisation (TR-09)
- §3.7 Where distance protection fits — the architectural slot Chapters 4–6 fill

This chapter is **shorter than the centerpiece chapters** because the differential half is treated as cited foundation (already validated in TR-08, TR-26), not a contribution claim.

### Part III — Distance Protection Centerpiece (Chapters 4–6)

#### **Chapter 4 — Theory of IBR Distance Protection** [~15 000 words]

- §4.1 IBR FRT current model and the $(\alpha, k_{\text{ibr}})$ parameter plane (TR-29 §1)
- §4.2 Apparent-impedance trajectory: the $Z_m^{\text{IBR}} = Z_m^{\text{SG}}$ proof (TR-29)
- §4.3 Three structural failure modes: $I_{\min}$ blocking, $V_{\text{relay}}$ deficiency, memory expiry (TR-29)
- §4.4 Four-region decomposition on the $(\alpha, k_{\text{ibr}})$ plane (TR-29) — **this is C2's load-bearing exhibit**
- §4.5 Cross-polarised Mho characteristic with decay-invariance proof on inductive lines (TR-30)
- §4.6 Zero-sequence compensation $k_0$ structural analysis: line-parameter validity vs measurement-validity under IBR sources (TR-31)
- §4.7 Chapter summary: theory complete; element design follows in Chapter 5

Anchors: `sec:ch4-frt-model`, `sec:ch4-impedance-trajectory`, `sec:ch4-region-map`, `sec:ch4-cross-pol-mho`, `sec:ch4-k0-analysis`.

#### **Chapter 5 — Element Design** [~15 000 words]

- §5.1 Sequence-directional elements: 67N (zero-sequence) and 67Q (negative-sequence) with forward-selectivity proofs (TR-32)
- §5.2 Permissive Overreach Transfer Trip (POTT) using the 87L pilot channel as zero-added-hardware carrier (TR-33)
- §5.3 Quadrilateral distance characteristic with closed-form $R_{\text{fwd}}$ design rule (TR-34)
- §5.4 Structural impossibility region: where no distance characteristic can operate, and the role of 87L as universal back-stop (TR-34, TR-35 §B)
- §5.5 Settings reference: zone reaches, time delays, load-encroachment blinders, polarisation thresholds (settings tables)
- §5.6 Coordination across primary/backup pairs (settings + grading margins)

Anchors: `sec:ch5-67-directional`, `sec:ch5-pott`, `sec:ch5-quadrilateral`, `sec:ch5-impossibility-region`.

#### **Chapter 6 — Integrated Scheme, Auto-Reclose, and Reliability** [~15 000 words]

- §6.1 Integrated five-element time-ladder: Z1 quad + 87L + 67N/67Q + Z2/POTT + TDCS backup (TR-35)
- §6.2 Coverage analysis: 48-cell parametric coordination matrix; zero gaps for $k_{\text{ibr}} \geq 0.06$ pu (TR-35)
- §6.3 External-fault security: multiple independent rejection mechanisms (TR-35 §C)
- §6.4 Auto-reclose strategy under IBR memory-pol constraints (TR-36): adaptive dead time, 87L+67Q/N as memory-independent second-trip elements
- §6.5 Monte Carlo reliability assessment: $P_{\text{dep}} = 99.61\%$ on 4 000 trials; all 15 misses share $k_{\text{ibr}} < 0.06$ (TR-37)
- §6.6 Sensitivity analysis: dependability vs IBR penetration — establishes the $k_{\text{ibr}} \geq 0.06$ pu floor (TR-37 §E)
- §6.7 Grid-code policy implication: minimum IBR fault-current contribution as a derived requirement (TR-37 §F + Ch7 cross-ref to standards literature)

Anchors: `sec:ch6-coordination`, `sec:ch6-coverage-matrix`, `sec:ch6-auto-reclose`, `sec:ch6-mc-reliability`, `sec:ch6-grid-code`.

### Part IV — Layer Integration (Chapters 7–8)

#### **Chapter 7 — Communication Layer** [~12 000 words]

- §7.1 IEC 61850 communication architecture — station bus, process bus, ACSI, SCL (TR-06 foundation)
- §7.2 GOOSE for protection-critical signalling: latency budget, jitter, redundancy schemes (TR-06, TR-14)
- §7.3 Sampled Values for measurement-critical telemetry: cadence, time alignment (cross-ref Ch3 §3.5)
- §7.4 Wide-area protection and control (WAPC): two-ended POTT, line-current differential pilots, system-wide event signalling (TR-50)
- §7.5 PMU integration for state estimation — synchrophasor-based reach adjustment for distance protection (TR-77)
- §7.6 COMTRADE-format field-record ingest and replay (TR-87)
- §7.7 Time-synchronisation discipline — IEEE C37.238 Power Profile of IEEE 1588 PTP, IRIG-B compatibility
- §7.8 Communication-failure scenarios: graceful degradation when GOOSE / SV / WAPC links fail
- §7.9 Composition with the protection scheme: timing-budget closure across protection element + comm element (e.g., 87L pilot adds ≤ 2 ms; POTT trip = 32 ms total)

Anchors: `sec:ch7-iec61850-arch`, `sec:ch7-goose`, `sec:ch7-sv`, `sec:ch7-wapc`, `sec:ch7-pmu`, `sec:ch7-comtrade`, `sec:ch7-time-sync`, `sec:ch7-comm-failure`.

#### **Chapter 8 — Cybersecurity Layer** [~12 000 words]

- §8.1 Attack model: spoofed sensor inputs, replayed GOOSE frames, DT-state poisoning, denial-of-service, GMD/GIC environmental stress (TR-52, TR-82, TR-81)
- §8.2 Mitigation: HMAC-SHA256 GOOSE message integrity (TR-82); algorithmic specification, key-management approach
- §8.3 Mitigation: anomaly detection on telemetry streams (TR-52); residual-based, consistency-based, pattern-based detectors
- §8.4 Mitigation: rate limiting and per-source trust scoring
- §8.5 Mitigation: cryptographic logging and tamper-evident audit trail
- §8.6 Degraded-mode fallback: trust-score threshold $\theta_{\min}$, fallback behaviour, recovery dwell
- §8.7 Composition with the protection scheme: confidence-gated supervisory authority, attack-aware $\chi_{\text{prot}}$ variant
- §8.8 Standards alignment: NERC CIP-007, IEC 62443-3-3, NIST SP 800-82 Rev. 3
- §8.9 Residual attack surface: what's not addressed, why, and what compensating controls apply

Anchors: `sec:ch8-attack-model`, `sec:ch8-hmac`, `sec:ch8-anomaly-detection`, `sec:ch8-rate-limiting`, `sec:ch8-audit-log`, `sec:ch8-degraded-mode`, `sec:ch8-standards-alignment`, `sec:ch8-residual-surface`.

### Part V — Validation and Conclusion (Chapters 9–10)

#### **Chapter 9 — End-to-End Validation Campaign** [~14 000 words]

The chapter that closes G1..G8. Each section maps to one gap from the original gap analysis:

- §9.1 Methodology: simulation toolchain (analytical + Python parametric + EMT + HIL), test networks, statistical methods, randomisation seeds — establishes per-experiment reproducibility (closes G3 Wilson CI methodology)
- §9.2 EMT validation (PSCAD or ATP-EMTP) of three representative scenarios: 3ϕ Region B, arc-resistance worst-case, POTT external-fault selectivity — phasor-domain predictions vs EMT measurements (**G1**)
- §9.3 Hardware-in-loop validation on a real IED (SEL-411L or ABB REL670 via Omicron CMC injection): three end-to-end clearance events (**G7**)
- §9.4 Comparative benchmarking against ≥ 1 published commercial scheme (SEL weak-infeed logic OR Toshiba IBR-aware Mho OR utility R&D proposal) on the same scenario set (**G2**)
- §9.5 Wilson CI dependability + security characterisation: TPR / FPR / PPV / NPV with 95% CIs, separately for in-zone and external faults (**G3**)
- §9.6 Alternative IBR archetypes: results under (a) Type-IV WT with detailed control, (b) utility-scale PV inverter, (c) GFM virtual-synchronous-machine inverter (**G4**)
- §9.7 Multi-terminal / parallel-line topology extension: scheme behaviour on (a) parallel-coupled lines with mutual coupling, (b) three-terminal teed line (**G5**)
- §9.8 Grid-code achievability from the inverter side: control-bandwidth + current-rating cost of a $k_{\text{ibr}} \geq 0.06$ pu requirement (**G6**)
- §9.9 Field-trace replay (where data access permits): real fault records from PGCIL / NGESO / ERCOT replayed through the integrated scheme (**G8**)
- §9.10 Cyber-resilience harness: structured attack-injection experiments validating the Chapter 8 mitigations end-to-end
- §9.11 Aggregate validation table: all G1..G8 + cyber-harness results in one comparison

Anchors: one per sub-section.

#### **Chapter 10 — Conclusion, Grid-Code Recommendations, and Future Work** [~5 000 words]

- §10.1 Thesis recap: contributions C1..C7 against the empirical evidence
- §10.2 Limitations: honest enumeration of scope boundaries
- §10.3 Grid-code recommendations: minimum IBR fault-current contribution, communication-layer time-sync requirements, cybersecurity-layer minimum mitigations
- §10.4 Future work: post-thesis directions (FW1..FW8 numbering convention, similar to MAS-DT-SH)
- §10.5 Closing positioning statement

### Front and back matter (standard IITM)

- Title page, certificate, declaration, acknowledgements
- Abstract (~500 words)
- Table of contents, list of figures, list of tables, list of acronyms
- Bibliography (~300+ entries across the four pillars)
- List of publications (5+ journal papers anticipated)

---

## 5. Cross-chapter dependencies

| Chapter pair | Dependency direction |
|---|---|
| Ch3 → Ch4 | Ch3 establishes SAMBP frame; Ch4 starts inside that frame |
| Ch4 → Ch5 | Ch4's failure-mode decomposition motivates each element in Ch5 |
| Ch5 → Ch6 | Ch5's elements compose into Ch6's integrated scheme |
| Ch6 → Ch7 | Ch6's POTT relies on Ch7's GOOSE pilot; Ch7's WAPC depends on Ch6's coordination |
| Ch7 → Ch8 | Ch8's HMAC-SHA256 is layered on Ch7's GOOSE; Ch8's anomaly detection consumes Ch7's telemetry |
| All → Ch9 | Ch9 validates the integrated stack |
| Ch9 → Ch10 | Ch10 synthesises Ch9's evidence into contribution claims |

This dependency graph is acyclic and natural — the chapters tell a coherent story end-to-end without forward-reference traps.

---

## 6. Methodology framework (cross-pillar)

### Test networks

- **Distance arc** (Pillar B): single radial Generator → $Z_{\text{src}}$ → Bus A → $Z_{\text{line}}$ → Bus B → $Z_{\text{tr}}$ → Bus C; per-unit base $j0.10 / j0.05 / j0.30$ pu, X/R = 20.
- **Differential arc** (Pillar A reuse): radial + double-busbar topologies from TR-05 / TR-07.
- **Multi-terminal extension** (G5): three-terminal teed line OR parallel-coupled lines — to be added.
- **Standard benchmark** for comparative work (G2, G4): IEEE 9-bus or CIGRE 4-bus reference network — to be selected.

### Simulation tooling

| Tier | Tool | Use |
|---|---|---|
| Analytical | Python + NumPy + SymPy | Closed-form proofs, parametric sweeps |
| Phasor-domain | Python `run_*_study.py` scripts (existing, TR-32..37) | Coordination matrix, MC reliability |
| EMT-domain | PSCAD or ATP-EMTP (G1) | EMT validation of 3 scenarios |
| HIL | RTDS or HIL-rig with SEL/ABB IEDs + Omicron CMC (G7) | End-to-end IED clearance verification |
| Cybersecurity | Custom attack-injection harness (G6 + Ch8) | Structured attack experiments |

### Statistical methods

- Monte Carlo: 4 000 trials minimum (TR-37 precedent); upgraded to 10 000+ for G3 Wilson CI work
- Wilson 95% CI (binomial proportion confidence, normal-approximation alternative for very-low FPR)
- Sensitivity sweeps via stratified Monte Carlo (TR-37 §E precedent)
- Comparative benchmarking via per-scenario paired metrics (TPR, clearance time, false-trip rate)

### Bibliography management

- Single canonical bibliography across all chapters (similar to MAS-DT-SH `mas_dt_sh.bib` model)
- Target ~300 entries spanning four pillars; existing per-TR `references*.bib` sources are starting point
- Citation style: IEEE-numbered (IITM convention)

---

## 7. Validation plan — comprehensive G1–G8

Per the user's locked decision (comprehensive validation), all eight gaps from the prior gap-analysis are in scope:

| Gap | Description | Effort | Chapter home |
|---|---|---|---|
| **G1** | EMT validation of 3 scenarios | 3–4 mo | Ch9 §9.2 |
| **G2** | Comparison vs ≥ 1 published commercial scheme | 2–3 mo | Ch9 §9.4 |
| **G3** | Wilson CI on security/external-fault selectivity | 1 mo | Ch9 §9.5 |
| **G4** | Alternative IBR archetypes (Type-IV WT / PV / GFM) | 3–4 mo | Ch9 §9.6 |
| **G5** | Multi-terminal / parallel-line topology | 2–3 mo | Ch9 §9.7 |
| **G6** | Grid-code achievability from inverter side | 2 mo | Ch9 §9.8 |
| **G7** | HIL validation on real IED | 4–6 mo | Ch9 §9.3 |
| **G8** | Field-trace replay | 6+ mo (data-access dependent) | Ch9 §9.9 |

**Plus a new G9 unique to this scope:** **Cyber-resilience harness** — structured attack-injection experiments validating Chapter 8 mitigations end-to-end. Effort: 3–4 mo. Chapter home: Ch9 §9.10.

**Total empirical effort:** ~26–35 months of engineering work if executed sequentially; ~16–20 months with parallelism (e.g. EMT and cyber-harness can run independently).

---

## 8. Path forward — phased execution timeline

### Phase A (months 1–6): Foundation + Wilson CIs

1. Author Ch1 literature review skeleton (~6 weeks)
2. Author Ch2 problem statement / RQ / contribution (~3 weeks)
3. Author Ch3 SAMBP framework chapter from TR-01..27 sources (~6 weeks)
4. Re-run TR-37 Monte Carlo with explicit external-fault sampling; produce Wilson CIs (G3, ~4 weeks)
5. Set up EMT toolchain (PSCAD or ATP-EMTP) — environment install + test-network port (~4 weeks)

### Phase B (months 7–14): Distance-centerpiece chapters + EMT/comparative validation

6. Author Ch4 theory chapter (~6 weeks)
7. Author Ch5 element-design chapter (~6 weeks)
8. Author Ch6 integration/AR/reliability chapter (~6 weeks)
9. EMT-validate 3 scenarios (G1, ~12 weeks; can run parallel to authoring)
10. Reproduce one published commercial scheme + comparative benchmarking (G2, ~10 weeks; parallel)

### Phase C (months 15–22): Communication + cybersecurity layers + alt-IBR + multi-terminal

11. Author Ch7 communication chapter (~6 weeks)
12. Author Ch8 cybersecurity chapter (~6 weeks)
13. Add detailed Type-IV WT or GFM IBR model; rerun coordination + MC (G4, ~12 weeks)
14. Extend test network to multi-terminal (G5, ~10 weeks)
15. Inverter-side grid-code achievability (G6, ~8 weeks)

### Phase D (months 23–30): HIL + field replay + cyber-harness + Ch9 + Ch10

16. HIL validation on real IED (G7, ~16 weeks)
17. Field-trace replay (G8, depends on data access, ~16 weeks)
18. Cyber-resilience harness experiments (G9, ~12 weeks)
19. Author Ch9 validation chapter (~6 weeks; parallel to G7..G9)
20. Author Ch10 conclusion (~3 weeks)

### Phase E (months 31–36+): Integration, polish, defence prep

21. Integration pass across all 10 chapters; cross-reference fixing; figure regeneration
22. Supervisor review cycles (typically 2–3 rounds)
23. Synopsis preparation (institutional 6–8 page document)
24. Defence preparation

**Total time-to-defence: 30–42 months from this study, depending on data access (G8) and lab access (G7).**

---

## 9. Risks under the locked scope

### Risk-1 — Thesis is large

10 chapters, ~95–115k words, 7 contributions, 9 validation gaps. This is at the upper end of IITM thesis size and committee tolerance. **Mitigation:** the chapter structure has clear part-boundaries (I/II/III/IV/V) so examiners can read modularly; each chapter has a self-contained narrative; the 5 anticipated journal papers can pre-publish content during Phase B–D so the thesis is "summary of published work" rather than primary venue.

### Risk-2 — HIL and field-trace access dependencies (G7, G8)

Lab access for IEDs and utility-data access for field traces are both schedule-uncertain. **Mitigation:** Phase D execution is parallelisable; if G7 lab access is delayed, complete G1–G6 + G9 first and defer HIL to a journal paper post-defence. Same for G8.

### Risk-3 — Authoring effort across four pillars

The thesis requires fluency in distance protection, differential protection, communication standards, and cybersecurity — the supervisor and the committee may want sub-specialist reviewers. **Mitigation:** the thesis is positioned as a *systems integration* contribution; the pillars are integrated by design rather than independently expert.

### Risk-4 — Inverter manufacturer cooperation for G4 (alt-IBR archetypes)

Detailed inverter controller models are vendor-protected. **Mitigation:** use generic Type-IV WT controller from published academic models (e.g. Erlich, Slootweg) and a generic GFM virtual-synchronous-machine model (Zhong, D'Arco). Acknowledge in §9.6 that vendor-specific models are out of scope.

### Risk-5 — IITM template constraints

Thesis must conform to IITM PhD thesis LaTeX template. **Mitigation:** authoring in Markdown (per ADR-002 in the MAS-DT-SH precedent) with conversion at submission via pandoc — same model as MAS-DT-SH. Same toolchain reusable.

### Risk-6 — Bibliography management at scale

~300 entries across four pillars. **Mitigation:** maintain single canonical `.bib` file with careful T2-style fabrication audits at every commit (the MAS-DT-SH T2 audit caught 3 fabricated entries; Phase 3 distance corpus has 10 separate per-TR bibs that need consolidation + audit).

---

## 10. Decision points still open (post-scope-lock)

1. **Authoring format:** Markdown-first (per MAS-DT-SH precedent + ADR-002) vs LaTeX-from-the-start. **Recommendation: Markdown-first** — same toolchain reuse, faster iteration during the long authoring phase, conversion at M7.
2. **Repository layout:** This thesis lives WHERE in the file system? Options:
   - (a) New top-level repo `/root/phd_thesis/SAMBP_DISTANCE/` (sibling of `MAS_DT_SH/`)
   - (b) Under `/root/phd_thesis/01_thesis_sambp/` similar to existing layout
   - (c) Under `03_technical_reports/` itself with a new `_thesis/` subdir
   - **Recommendation: (a)** — clean separation, mirrors MAS-DT-SH's structure, supports per-thesis git history.
3. **Synopsis deliverable:** Should I draft the 6–8 page IITM PhD synopsis from this plan now, or wait until Phase A literature-review skeleton is in?  **Recommendation:** Wait for Phase A so the synopsis cites real content; but I can produce a *draft synopsis structure* (sections + word targets + citation-skeleton) as a reusable template.
4. **First commit:** What is the first concrete deliverable I produce? **Recommendation:** Phase A item 1 — Ch1 literature review skeleton (~6 weeks of authoring; first commit is the skeleton + per-section anchor stubs).

---

## 11. Recommendation summary

**The plan is ambitious but defensible.** The four-pillar scope (distance + SAMBP + comm + cyber) is internally coherent — every pillar has a contribution-bearing claim, every chapter has a 1:1 RQ, every validation gap has a chapter section. The 30–42 month timeline is consistent with a substantive PhD on a systems-integration topic.

**Proposed immediate next action:** decide on items 1–4 in §10 (authoring format, repo layout, synopsis timing, first commit) so I can scaffold the new thesis repo and start Phase A. If you authorise it now, my next deliverable would be the new `SAMBP_DISTANCE/` repo with:

```
SAMBP_DISTANCE/
├── 00_governance/
│   ├── ADR-001-thesis-scope.md       # locked-scope record
│   ├── ADR-002-authoring-format-md-first.md  # Markdown-first
│   └── canonical_naming.md            # acronyms, TR mapping
├── 01_thesis/
│   ├── ch01_literature_review/
│   │   └── ch01_draft.md              # skeleton with section anchors
│   ├── ch02_problem_statement/
│   ├── ch03_sambp_framework/
│   ├── ch04_distance_theory/
│   ├── ch05_distance_elements/
│   ├── ch06_distance_integration/
│   ├── ch07_communication/
│   ├── ch08_cybersecurity/
│   ├── ch09_validation/
│   └── ch10_conclusion/
├── 02_papers/                          # 5 anticipated journal papers
├── 03_technical_reports/               # symlinks to existing TRs
├── 08_references/
│   └── sambp_distance.bib              # consolidated + T2-audited
└── CHAPTER_STATUS.md
```

Same shape as MAS-DT-SH. Same Markdown-first authoring discipline. Same audit-log + cross-cutting-observation framework. Then I'd write Ch1's first-pass skeleton (~3 000 words, anchor structure in place) as the first commit.

**Reply with one of:**
- `proceed scaffold` — I create the SAMBP_DISTANCE repo + scaffold + first-pass Ch1 skeleton in the next turn
- `proceed scaffold + synopsis draft` — same plus a reusable synopsis-structure template
- `revise plan` — specify changes to RQs / Cs / chapter structure before committing
- `pause` — review this plan in detail before any authoring action

No file touched outside this design document. Existing inner-repo (MAS_DT_SH) HEAD unchanged at `2ccfc76`.
