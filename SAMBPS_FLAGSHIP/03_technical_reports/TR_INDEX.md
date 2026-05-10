# SAMBPS Flagship · Technical Report Index

**Namespace:** `TR-NN` (numbers 1..98+) · `TR-H01+` (HVDC subseries)
**Last updated:** 2026-04-25
**Owner:** Anoop V. Eluvathingal

This index is the master ledger for SAMBPS-side technical reports. Each TR is a standalone technical document feeding into thesis chapters, journal papers, or product features.

> **Migration note:** TRs were drafted prior to this folder's creation. Migration into `03_technical_reports/<TR-NN>/` is incremental; TRs not yet migrated are flagged with **[external]** in the status column.

---

## TRs referenced in active calendar work (Apr 2026)

| TR ID | Title | Backing | Status | Calendar block |
|---|---|---|---|---|
| TR-77 | PMU state estimation | k_ibr estimator (Mon DWT/k_ibr deep work) · APPEEC 2026 P2 | [external] | Mon 21:00–01:00 IST |
| TR-90 | Federated learning across substations (cross-substation relay coordination) | APPEEC 2026 P4 (Dipti-aligned) · Wed deep work | [external] | Wed 21:00–01:00 IST |
| TR-91 | GraphSAGE / GNN topology-aware protection | APPEEC 2026 P2 (related) · GFM/GFL estimator | [external] | — |
| TR-98 | SEL-411L hardware-in-the-loop validation | Tue SAMS Architect / TR-98 HIL deep work | [external] | Tue 21:00–01:00 IST |
| TR-H01+ | HVDC product subseries (LCC / VSC / MMC adaptive protection) | APPEEC 2026 P1 · Thu HVDC deep work | [external] | Thu 21:00–01:00 IST |
| TR-43..45 | Digital twin: estimation / validation / decision-fusion layers | APPEEC 2026 P3 (DT trajectory prediction) | [external] | — |

---

## TRs referenced via MAS–DT-SH crosswalk

The following SAMBPS TRs are cited in `../00_governance/mas_dt_sh_crosswalk.md` (or its reciprocal). Migrate each into `03_technical_reports/<TR-NN>/` when first edited.

| TR ID | Title | Crosswalk role | Status |
|---|---|---|---|
| TR-03, TR-17, TR-20–22 | Adaptive 87L (line differential) | Cited as broader-context background in MAS–DT-SH Ch4 | [external] |
| TR-38–42 | Microgrid protection (modes) | Cited in MAS–DT-SH Ch3 §3.3 | [external] |
| TR-50 | Wide-Area Protection and Control (WAPC) | Comparative baseline in MAS–DT-SH Ch4 §4.9 | [external] |
| TR-52 | GOOSE cybersecurity | Reused for MAS–DT-SH Ch5 §5.6.6 (cyber-resilience) | [external] |
| TR-68, TR-71, TR-80 | BESS / hybrid AC-DC state-space models | Cited in MAS–DT-SH Ch3 §3.3 (DER representation) | [external] |
| TR-70 | Meshed IBR topology engine | Cited as related work in MAS–DT-SH Ch5 §5.4 | [external] |
| TR-72 | CUSUM evolving fault detector | Reused by MAS–DT-SH | [external] |
| TR-77 | PMU state estimation | Cited by MAS–DT-SH (DSSE comparison) | [external] |
| TR-79 | Multi-agent protection | Comparative baseline in MAS–DT-SH | [external] |
| TR-82 | HMAC-SHA256 GOOSE | Reused for MAS–DT-SH cyber-resilience | [external] |
| TR-85 | Cold-load pickup adaptation | Reused by MAS–DT-SH (post-restoration pickup) | [external] |
| TR-87 Phase A/B | COMTRADE ingestor + PSCAD replay | Reused by MAS–DT-SH `mas_dt_lab.io_utils` | [external] |
| TR-91 | GraphSAGE GNN | Possible MAS–DT-SH Ch4 §4.9 extension | [external] |

---

## Migration workflow

1. Locate the external TR source (Overleaf / local repo / git).
2. Create `03_technical_reports/TR-NN-short-title/` with:
   - `TR-NN_v{N}.pdf` (current version)
   - `manuscript_source/` (LaTeX/markdown source)
   - `figures/`
   - `metadata.md` (authors, version history, related papers/chapters, status)
3. Update the row above: change `[external]` to the path-relative short status (e.g. `🟡 v1.2 migrated`).
4. Cross-link from any chapter or paper that cites this TR.

---

## Numbering rules

- TR-01 through TR-98 reserved for general SAMBPS work.
- TR-H01+ reserved for HVDC subseries (LCC, VSC, MMC product line).
- TR-99+ reserved for advanced extensions / future work.
- Never reuse a retired TR ID. Mark superseded TRs with `superseded-by TR-NN+` and keep the row.

---

_Update this file every time a TR is created, migrated, or superseded._
