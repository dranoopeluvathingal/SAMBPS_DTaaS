# ADR-001 · SAMBPS Flagship as a Distinct Project (Sister to MAS–DT-SH)

**Status:** Accepted
**Date:** 2026-04-25
**Owner:** Anoop V. Eluvathingal
**Supersedes:** —

---

## Context

The flagship SAMBPS DTaaS work — adaptive protection across IBR / HVDC / transmission, plus the SAMS Digital Twin and SAMS Architect product lines — previously had no scaffolded home in the file tree. The MAS–DT-SH thesis project (distribution-side, multi-agent, action-validating DT) had been scaffolded under `SAMS/MAS_DT_SH/`, but every artefact relating to APPEEC 2026 papers, HVDC adaptive protection, GFM/GFL estimators, and TR-90 federated learning was unattached.

The 2026-04-25 calendar review attempted to map deep-work blocks to folders and immediately surfaced this gap: the deep-work blocks were all SAMBPS-side topics, and there was no SAMBPS-side folder to point them at.

## Decision

Create `SAMS/SAMBPS_FLAGSHIP/` as a sister project to `SAMS/MAS_DT_SH/`, mirroring its scaffold but with SAMBPS-specific framing (transmission/IBR/HVDC scope, `sambp-dt-lab` code package, TR-NN namespace). Keep the two projects strictly separate per the canonical-naming and crosswalk policies of each.

## Rationale

- **Scope cleanliness** — MAS–DT-SH explicitly excludes transmission protection, HVDC, and IBR-dominated transmission. The APPEEC papers all sit in those exclusion zones.
- **Symmetry with MAS–DT-SH** — same 8-folder scaffold means the same mental model applies to both projects. Reduces context-switching cost.
- **Crosswalk reciprocity** — having two projects with reciprocal `sambps_crosswalk.md` / `mas_dt_sh_crosswalk.md` files makes overlap auditable and prevents silent duplication.
- **Calendar mappability** — "Project anchor" footers on calendar deep-work events now point to specific folders that exist.

## Alternatives considered

1. **Drop SAMBPS papers into `MAS_DT_SH/02_papers/`** — rejected. Violates the cross-project naming rule (no SAMBPS acronyms in MAS–DT-SH artefacts). Conflates two scopes.
2. **Top-level `SAMBPS DTaaS/02_papers/`** — rejected. Would skip the sister-project framing and leave SAMBPS without a charter, status ledger, or TR index of its own. Harder to evolve.
3. **Multiple sub-projects** (`SAMBPS_HVDC/`, `SAMBPS_IBR/`, `SAMBPS_DT/`) — rejected as premature. The four APPEEC papers cohere as a single programme; splitting now would fragment the TR namespace and force TR-INDEX duplication.

## Consequences

### Positive
- APPEEC 2026 submission has a clean per-paper scaffold.
- Future SAMBPS-side thesis (placeholder in `CHAPTER_STATUS.md`) has a home before the first chapter is drafted.
- Calendar work is anchored.

### Negative / risk
- Two scaffolds to maintain — solved by enforcing the crosswalk and not duplicating governance text across projects.
- "Flagship" name is generic and may need rebranding once the SAMBPS-side thesis title is finalized. Acceptable until then.

## Implementation (2026-04-25)

- Folder created: `SAMS/SAMBPS_FLAGSHIP/` with all 8 numbered subfolders.
- Files written: `README.md`, `PROJECT_CHARTER.md` (v0.1, MS1–MS7), `CHAPTER_STATUS.md`, `00_governance/{canonical_naming,glossary,mas_dt_sh_crosswalk}.md`, `03_technical_reports/TR_INDEX.md`, `02_papers/appeec_2026/{README,submission_log}.md` and 4 per-paper `submission_metadata.md`.
- Canonical naming `MAS_DT_SGP` → `MAS_DT_SH` applied (separate ADR not warranted; documented in MAS–DT-SH `canonical_naming.md`).
- Calendar `Project anchor` footers added to 8 events pointing into this scaffold.

## Open questions

- Whether to re-name `SAMBPS_FLAGSHIP/` to a more specific working title once the SAMBPS-side thesis takes shape. Defer until M3 (Ch2 draft) of the thesis.

---

## Related ADRs

- `../../../SGCRL/00_governance/decisions/ADR-001-three-pillar-org-structure.md` (parent decision establishing the SAMS housing of projects)
