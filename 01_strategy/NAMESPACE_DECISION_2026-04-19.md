# NAMESPACE_DECISION_2026-04-19

**Document type:** POLICY  
**ID:** R-09 (closed)  
**Author:** Anoop V. Eluvathingal, SGCRL, IIT Madras  
**Date:** 2026-04-19 (audit) / 2026-04-20 (actions completed)

---

## What Changed and Why

### Context

A full namespace audit was performed on 2026-04-19 across all TR folders,
gap-plan files, chapter maps, and the comprehensive report builder to establish
whether `/root/phd_thesis` could serve as the **single source of truth** for
the TR-01..TR-100 namespace.

### Findings Before Audit

| Finding | Severity | Resolution |
|---|---|---|
| TR-87 absent (sequence gap in TR-86..TR-88) | High | TR-87 delivered 2026-04-20 (R-13 closed) |
| ANDES tracking in separate silo doc | Medium | Confirmed not a silo — ANDES lives in TR-56/59/62 (R-10 closed) |
| 5 soft description mismatches (TR-59/64/65/66/67) | Medium | All resolved 2026-04-26 — folder wins in each case (R-16 closed) |
| Forward plan (TR-92..TR-100) only in root Markdown | Low | Promoted to `tr_namespace_map.yaml` backlog section (R-17 partial) |
| PROGRESS.yaml stale for TR-64..67, TR-83..91 | Low | Updated 2026-04-20 |
| Comprehensive report builder hardcoded "85 TRs" | Medium | Fixed 2026-04-20 — dynamic count, commit ae56109a (R-14 closed) |

### Decisions Made

1. **TR namespace is a single flat space: TR-01..TR-100.**  
   No sub-namespaces, no phase-prefixes in the TR number itself.
   Phase is metadata, not part of the identifier.

2. **HVDC is TR-H01+ (separate namespace).**  
   HVDC converter protection is NOT excluded from SAMBPS DTaaS — it is
   a separate product line deferred from the PhD. The TR-H01+ namespace
   is managed separately and never mixes with the PhD TR-01..TR-100 space.

3. **On-disk folder is the authoritative scope record.**  
   When gap-plan descriptions diverge from completed TR folder+report,
   the folder wins. Gap-plan is a planning artefact; the TR report is the
   delivered artefact. (Applied to TR-59/64/65/66/67.)

4. **No TR number is ever reused.**  
   Deprecated TRs move to `07_archive/reports_old/TR##__deprecated/`
   with a `README_SUPERSEDED.md` pointer at the original location.

5. **Matching rule for new TRs (from this date forward).**  
   Every new TR must land simultaneously in the gap-plan AND on disk
   with matching title. No divergence is acceptable at time of creation.

6. **`tr_namespace_map.yaml` is the single register.**  
   `RESEARCH_PLAN_TR86_TR100.md` (root) is a forwarding pointer only.
   `03_technical_reports/TR_INDEX.md` is a human-readable flat view.
   Both defer to `tr_namespace_map.yaml` for canonical data.

### Files Created/Modified

| File | Action |
|---|---|
| `tr_namespace_map.yaml` | CREATED — 91 active + 9 backlog rows |
| `03_technical_reports/TR_INDEX.md` | CREATED — flat 100-row index |
| `03_technical_reports/SCOPE_RECONCILIATION_2026-04-26.md` | CREATED — 5 decision records |
| `03_technical_reports/phase_8_advanced_extensions/TR87_pscad_emt_replay/README.md` | CREATED |
| `03_technical_reports/phase_8_advanced_extensions/TR87_pscad_emt_replay/scope.md` | CREATED |
| `04_code/sambp/io_utils/comtrade_adapter.py` | CREATED — production adapter |
| `04_code/sambp/digital_twin/PROGRESS.yaml` | UPDATED — TR-64..67 corrected; TR-83..91 added |
| `01_strategy/ROADMAPS/RESEARCH_PLAN_TR86_TR100.md` | MOVED from root |
| `RESEARCH_PLAN_TR86_TR100.md` (root) | REPLACED with forwarding pointer |
| `SAMBP_Comprehensive_Report_Full_Details/build_report.py` | PATCHED — dynamic count |

### Issues Closed

| Issue | Resolution |
|---|---|
| R-09 — namespace definition | Closed: single flat TR-01..TR-100 |
| R-10 — ANDES silo | Closed: no silo, integrated in TR-56/59/62 |
| R-13 — TR-87 sequence gap | Closed: delivered 2026-04-20 |
| R-14 — stale comprehensive report builder | Closed: dynamic count, commit ae56109a |
| R-15 — forward plan silo | Partially closed: promoted to tr_namespace_map.yaml |
| R-16 — description mismatches | Closed: 5 TRs reconciled, folder wins |
| R-17 — backlog not in namespace map | Closed: TR-92..100 in backlog section |

---

*SGCRL, IIT Madras | PhD Candidate: Anoop V. Eluvathingal | Guide: Prof. K. Shanti Swarup*
