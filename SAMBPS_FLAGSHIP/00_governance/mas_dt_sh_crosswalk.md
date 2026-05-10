# SAMBPS Flagship ↔ MAS–DT-SH Crosswalk

**Purpose:** reciprocal of `../../MAS_DT_SH/00_governance/sambps_crosswalk.md`. Explicit record of concept / artefact overlap between the two programmes. Add a row here before reusing anything from MAS–DT-SH inside SAMBPS Flagship (or vice versa).

**Last updated:** 2026-04-25

---

## 1 · Concept-level crosswalk (reciprocal view)

| SAMBPS Flagship concept | MAS–DT-SH counterpart | Nature of overlap | Reuse policy |
|---|---|---|---|
| Digital twin (5-component, transmission/IBR scope) | Action-validating DT (Ch5, distribution scope) | Same DT-as-validator philosophy; different operating context | Cite each other; no code reuse without crosswalk row |
| Wide-Area Protection and Control (TR-50) | Multi-agent feeder restoration coordination | Both coordinate protection across nodes; different scales | SAMBPS WAPC is comparative baseline in MAS–DT-SH Ch4 §4.9 |
| Meshed IBR topology engine (TR-70) | Radial distribution + sectionalising switches | Different topology classes | Citations only |
| GOOSE cybersecurity (TR-52, TR-82) | Distribution-side cyber-resilience (MAS–DT-SH Ch5 §5.6.6) | Same HMAC + anomaly mechanics | **Reuse allowed** — MAS–DT-SH cites SAMBPS attack model and HMAC implementation |
| PMU state estimation (TR-77) | DSSE (distribution-system state estimation, typ. non-PMU) | Both two-ended-measurement based | Different observability assumptions; cite each other |
| COMTRADE ingestor (TR-87 Phase A/B) | MAS–DT-SH `mas_dt_lab.io_utils` | Same parser problem | **Reuse** the ingestor structure; MAS–DT-SH wraps with DER metadata |
| GraphSAGE / GNN protection (TR-91) | Possible Ch4 §4.9 extension | Shared graph-ML toolkit | MAS–DT-SH may cite as extension (post-thesis) |
| Microgrid protection (TR-38–42) | MAS–DT-SH MAS-execution layer | Microgrid TRs cover modes; MAS adds execution | Cite as related work |
| BESS / hybrid AC-DC (TR-68, TR-71, TR-80) | MAS–DT-SH Ch3 §3.3 DER representation | Same BESS state-space models | Cite when DER models reused |
| Adaptive 87L (TR-03, TR-17, TR-20–22) | Distribution feeder OC/directional (MAS–DT-SH protection layer) | Different protection elements (transmission line diff vs. distribution OC) | Citations only — different element classes |
| CUSUM evolving fault detector (TR-72) | MAS–DT-SH fault detection | Both detect regime changes | **Reuse** the CUSUM algorithm |
| Cold-load pickup (TR-85) | MAS–DT-SH post-restoration pickup | Directly relevant | **Reuse** the CLPUEstimator |
| Federated learning across substations (TR-90) | Distribution-side federated relay coordination | Both federate; different node populations | Cite each other; SAMBPS-side is canonical for transmission |

## 2 · Artefact-level reuse log (reciprocal)

Log every artefact copied or adapted from MAS–DT-SH into SAMBPS Flagship here. (Reuse from SAMBPS into MAS–DT-SH is logged on the MAS–DT-SH side.)

| Date | Artefact (MAS–DT-SH side) | Destination (SAMBPS Flagship side) | Adaptation notes |
|---|---|---|---|
| _(none yet)_ | | | |

## 3 · Forbidden patterns

- Do **not** copy/paste MAS–DT-SH thesis text into SAMBPS Flagship documents. Cite, do not duplicate.
- Do **not** use MAS–DT-SH-specific acronyms (FA, ZA, SA, SSA, DERA, RCA) inside SAMBPS Flagship documents except via crosswalk citation.
- Do **not** publish the same figure in both programmes without cross-citation.

## 4 · Reciprocal note

The authoritative crosswalk is the union of this file and `../../MAS_DT_SH/00_governance/sambps_crosswalk.md`. When adding a row here, also add the matching row to the MAS–DT-SH side.
