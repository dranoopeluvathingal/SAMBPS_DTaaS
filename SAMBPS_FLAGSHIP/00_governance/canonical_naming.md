# SAMBPS Flagship · Canonical Naming

**Version:** 1.0 (2026-04-25)
**Policy:** no deviation in externally distributed artefacts (thesis, papers, presentations, website, proposals).

---

## 1 · Programme name

| Form | Usage |
|---|---|
| **Self-Adaptive Model-Based Protection — Digital Twin as a Service** | Full name, first occurrence in any document |
| **SAMBPS DTaaS** | Short form, all subsequent occurrences |
| **SAMBPS** | Programme acronym (the methodology) when DTaaS framing is unnecessary |
| **the SAMBPS DTaaS platform** | Noun phrase form (refers to the SAMS Digital Twin product) |

### Explicit non-forms
- `SAMPS` (typo) — never
- `SAMBP-S` (hyphenated) — never
- `Sambps` (lowercase) — never; preserve the all-caps acronym
- `SAMBPS DTAAS` (uppercase DTAAS) — always use mixed case `DTaaS`

## 2 · Component names

| Canonical | Short | Use in text | Do not use |
|---|---|---|---|
| Self-Adaptive Model-Based Protection | SAMBPS | the SAMBPS methodology | "SAMP", "MBP" |
| Digital Twin as a Service | DTaaS | the DTaaS platform | "DTaaS-cloud", "twin-as-a-service" |
| Inverter-Based Resource | IBR | IBR, IBRs | "inverter-based source", "IBS" |
| Grid-Forming inverter | GFM | GFM, GFM-IBR | "grid-forming converter" only when strictly accurate |
| Grid-Following inverter | GFL | GFL, GFL-IBR | "grid-following converter" only when strictly accurate |
| High-Voltage Direct Current | HVDC | HVDC | "HV-DC" with hyphen |
| Line-Commutated Converter | LCC | LCC | "Line-commutated CSC" |
| Voltage-Source Converter | VSC | VSC | "voltage source converter" (no hyphen) |
| Modular Multilevel Converter | MMC | MMC | "modular multi-level" |
| Line Differential Protection (87L) | 87L | 87L | "line diff", "87-L" |
| Discrete Wavelet Transform | DWT | DWT | "wavelet transform" alone in formal contexts |
| Generic Object-Oriented Substation Event | GOOSE | GOOSE | always all-caps; never "Goose" |
| Hardware-in-the-Loop | HIL | HIL | "HITL" (reserved for human-in-the-loop) |
| Wide-Area Protection and Control | WAPC | WAPC | "WAPS", "wide-area control" alone |

## 3 · Product line names (under SAMS)

| Canonical | Short | Use |
|---|---|---|
| SAMS Digital Twin | SAMS-DT | Cloud DTaaS platform product |
| SAMS Architect | SAMS-AR | AI research-design engine product |

## 4 · TR namespace

- SAMBPS technical reports: `TR-NN` (1 .. 98+, plus extension suffixes)
- HVDC product line subseries: `TR-H01`, `TR-H02`, ...
- Never reuse a TR number. If a TR is superseded, mark `superseded-by TR-NN+` in `03_technical_reports/TR_INDEX.md`.

## 5 · Cross-project naming rules

- Do **not** use MAS–DT-SH-specific acronyms (FA, ZA, SA, SSA, DERA, RCA, MAS–DT-SH, mas-dt-lab) inside SAMBPS Flagship documents except in clearly-marked crosswalk citations.
- When a concept spans both programmes (e.g. digital twin, protection coordination), SAMBPS Flagship uses **transmission/IBR framing**; MAS–DT-SH uses **distribution-system framing**. Same word, different operating context.

## 6 · Code package naming

| Canonical | Path |
|---|---|
| `sambp-dt-lab` (Python package) | `04_code/sambp_dt_lab/` |
| Module path style | `sambp_dt_lab.<submodule>` (snake_case) |

Releases: `sambp-dt-lab-v0.1`, `v0.2`, etc. Semantic versioning.

## 7 · Change-control

Any change to this file is a governance change. Log a decision record under `00_governance/decisions/ADR-NNN-naming-change.md` before editing.
