# P · Adaptive HIF Protection Using Inverse Estimation

**Status:** drafting (next paper, post-APPEEC)
**Conference / journal:** TBD (IEEE-format draft to start)
**Lead:** Anoop V. Eluvathingal

---

## Working title

**Adaptive High-Impedance Fault Protection Using Inverse Estimation**

## Calendar anchor

**Sat 2 May · 15:00–18:00 IST** — Draft IEEE abstract + Introduction.

Output of that block lands in `manuscript_source/` and references go into `../../08_references/reading_list.md`.

## Why this paper next

- High-impedance fault (HIF) protection remains an unsolved problem at scale; conventional overcurrent / negative-sequence approaches are not selective enough below ~5 % rated current.
- Inverse estimation reframes detection as a parameter-recovery problem (treat the fault impedance as the unknown; invert the model from line-end measurements). It plugs into the SAMBPS adaptive-protection family naturally.
- Sits between TR-77 (PMU state estimation) and TR-91 (GNN topology-aware protection) on the SAMBPS-side TR map.

## File index

- `manuscript_source/` — IEEE LaTeX template
- `figures/` — system schematics, fault scenarios, results
- `coauthor_feedback/` — dated feedback files

## Sat 2 May · 15:00–18:00 deliverables

- [ ] IEEE-format abstract (150–250 words): problem · gap · approach · contribution · validation
- [ ] Introduction §1 draft: motivation → prior art → gap → contribution roadmap
- [ ] 5–7 key references identified and added to `../../08_references/reading_list.md`
- [ ] Skeleton of §2 (problem formulation) and §3 (inverse-estimation method) — bullet-level only

## Pre-submission checklist (when target venue is selected)

_(Mirror `appeec_2026/01_hvdc_adaptive_protection/submission_metadata.md` checklist when this paper has a target venue.)_

## Cross-references

- `../../00_governance/canonical_naming.md` — HIF, HVDC, IBR conventions
- `../../00_governance/glossary.md` — terminology
- `../../03_technical_reports/TR_INDEX.md` — link to relevant TRs once identified (probable: TR-77, TR-91, plus a new HIF-specific TR)
