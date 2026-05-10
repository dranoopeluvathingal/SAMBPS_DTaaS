# SAMBPS Flagship · Reading List

**Last updated:** 2026-04-25
**Status:** seed (skeleton, populate as papers cite)

This list collects key references for the SAMBPS Flagship programme — distinct from the MAS–DT-SH reading list (`../../MAS_DT_SH/08_references/reading_list.md`). Overlap is fine; duplicate entries should cross-reference.

---

## Must-read (🟥)

| # | Reference | Why | Used by |
|---|---|---|---|
| F-01 | IEEE Std C37.243-2015, "IEEE Guide for Application of Digital Line Current Differential Relays" | Foundational reference for adaptive 87L | TR-03, TR-17, TR-20–22; APPEEC 2026 P2 |
| F-02 | IEC 61850 series (esp. 61850-7-4 logical nodes, 61850-9-2 sampled values, 61850-90-5 PMU over GOOSE) | Substation comms backbone for SAMBPS DTaaS | All TRs touching GOOSE; APPEEC P1, P4 |
| F-03 | CIGRÉ TB 727 (HVDC grid protection) | HVDC protection state-of-the-art | TR-H01+; APPEEC P1 |
| F-04 | Glaessgen & Stargel (2012), "The Digital Twin Paradigm" | Foundational DT taxonomy (also in MAS–DT-SH list) | TR-43..45; APPEEC P3 |
| F-05 | Liu et al. (2024), "Digital-twin-driven fault situation identification for distribution networks with distributed wind power," IEEE T-IA | Strongest comparator for DT fault identification | APPEEC P3 (also MAS–DT-SH Ch1 [17]) |

## Should-read (🟨)

| # | Reference | Why |
|---|---|---|
| F-06 | Hertem & Ghandhari (2010), "Multi-terminal VSC HVDC for the European supergrid" | VSC HVDC foundations |
| F-07 | Yu et al. (2023), federated learning for power systems (most-cited recent review) | TR-90 backing |
| F-08 | Konečný et al. (2016), "Federated learning: strategies for improving communication efficiency" | Communication-cost analysis for P4 |
| F-09 | Arrillaga (2008), "High Voltage Direct Current Transmission" | Textbook reference for LCC |
| F-10 | Saeedifard & Iravani (2010), "Dynamic performance of a modular multilevel back-to-back HVDC system" | MMC dynamics |
| F-11 | Zeineldin et al. (2015), adaptive protection with DG, IEEE T-PD | Adaptive protection background (also MAS–DT-SH list) |
| F-12 | Hatziargyriou et al. (2020), "Definition and classification of power system stability revisited" | IBR-aware stability framing |
| F-13 | Xin et al. (2017), Singapore EMA / EPRI grid renewable integration reports | Singapore-site partnership context |

## Context (🟩)

- IEEE PES TR PES-TR68 Power System Dynamic Performance with IBR
- IEEE C37.238 PTP for substation time sync
- ENTSO-E Network Code on Operational Security (Europe / Amprion partnership)
- DOE Quadrennial Energy Review

---

## To populate before APPEEC submission

- [ ] Verify all F-01..F-13 entries cross-cited correctly in P1..P4
- [ ] Add canonical BibTeX file `sambps_flagship.bib` (parallel to `mas_dt_sh.bib` in MAS–DT-SH)
- [ ] Cross-reference any duplicates with MAS–DT-SH list to ensure consistent in-text citation keys

## Cross-project notes

If a reference is used in both SAMBPS Flagship and MAS–DT-SH, **do not** create separate citation keys. Use the same key in both `.bib` files. The crosswalk policy applies only to artefacts and methods; bibliography keys are shared.
