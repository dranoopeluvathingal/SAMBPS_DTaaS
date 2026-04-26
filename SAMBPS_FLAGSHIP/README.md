# SAMBPS DTaaS · Flagship Programme

**Self-Adaptive Model-Based Protection — Digital Twin as a Service**

The flagship research-and-product programme under SAMS. Sister project to **MAS–DT-SH** (which lives in `../MAS_DT_SH/`); the two programmes share a host lab and a digital-twin philosophy but address different operating contexts.

---

## Scope in one line

A self-adaptive, model-based protection architecture for IBR-dominated transmission and sub-transmission networks, validated through a cloud Digital-Twin-as-a-Service platform (SAMS Digital Twin) and authored via an AI research-design engine (SAMS Architect).

## Relationship to MAS–DT-SH

SAMBPS-Flagship is **distinct from** MAS–DT-SH. Overlap points are tracked in `00_governance/sambps_crosswalk.md` (reciprocal of the MAS–DT-SH file). No content is shared without a crosswalk entry.

| Dimension | SAMBPS-Flagship | MAS–DT-SH |
|---|---|---|
| Target system | IBR-dominated transmission / sub-transmission, HVDC | DER-rich smart distribution |
| Central contribution | Self-adaptive model-based protection (5-layer) | MAS-autonomy + action-validating DT (closed-loop self-healing) |
| Code package | `sambp-dt-lab-v0.1` | `mas-dt-lab` (to be bootstrapped) |
| TR namespace | `TR-NN` (1..98+, plus `TR-H01+` for HVDC) | `MAS-DT-TR-NN` |
| Host lab | IIT Madras PSCL (Prof. K. Shanti Swarup) | Same host lab |

## Folder layout

```
SAMBPS_FLAGSHIP/
├── README.md                          (this file)
├── PROJECT_CHARTER.md                 ← scope, objectives, deliverables
├── CHAPTER_STATUS.md                  ← chapter-level assessment and backlog
│
├── 00_governance/
│   ├── canonical_naming.md            ← SAMBPS canonical acronyms
│   ├── sambps_crosswalk.md            ← reciprocal mapping to MAS–DT-SH
│   ├── glossary.md                    ← SAMBPS-specific terminology
│   └── decisions/                     ← ADRs
│
├── 01_thesis/                         (placeholders until SAMBPS-side thesis lands)
├── 02_papers/                         ← journal / conference submissions
│   └── appeec_2026/                   ← APPEEC 2026 submission package
│       ├── 01_hvdc_adaptive_protection/
│       ├── 02_gfm_gfl_estimator/
│       ├── 03_dt_trajectory_prediction/
│       └── 04_tr90_federated_learning/
├── 03_technical_reports/
│   └── TR_INDEX.md                    ← SAMBPS TR-NN master index
├── 04_code/
│   ├── sambp_dt_lab/                  ← Python package
│   ├── simulations/
│   └── benchmarks/
├── 05_data/
│   ├── hvdc/                          ← LCC / VSC / MMC fault waveforms
│   ├── ibr/                           ← GFM / GFL test cases
│   └── comtrade/                      ← field-waveform ingest
├── 06_presentations/
├── 07_deliverables/
│   ├── assessments/
│   └── status_reports/
└── 08_references/
```

## Quick start

1. Read `PROJECT_CHARTER.md` for scope and milestones.
2. Read `02_papers/appeec_2026/README.md` for the active submission package (deadline: Thu 30 Apr 2026, 11:00 IST).
3. Read `03_technical_reports/TR_INDEX.md` for per-TR status.
4. Read `00_governance/sambps_crosswalk.md` before reusing anything from MAS–DT-SH.

## Authoritative sources

| File | Role |
|---|---|
| `PROJECT_CHARTER.md` | Living charter — scope, milestones, risks |
| `02_papers/appeec_2026/README.md` | APPEEC 2026 submission package status |
| `03_technical_reports/TR_INDEX.md` | SAMBPS TR-NN ledger |
| `00_governance/canonical_naming.md` | SAMBPS canonical acronyms |
| `00_governance/sambps_crosswalk.md` | Reciprocal MAS–DT-SH crosswalk |

---

© 2026 · Anoop V. Eluvathingal · IIT Madras / SGCRL · sister to MAS–DT-SH
