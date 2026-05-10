# SAMBP TR Scope Reconciliation — 2026-04-26

**Raised by:** Namespace audit, 2026-04-19  
**Due:** 2026-04-26 (Action A9)  
**Resolved by:** Anoop V. Eluvathingal  
**Rule:** For each mismatch the *on-disk TR report* is the authoritative scope record.
The gap-plan descriptions were written before execution and are superseded by
what the completed TR actually delivers.

---

## TR-59 — ANDES_syncoc

| Item | Value |
|---|---|
| Folder | `TR59_ANDES_syncoc` |
| Gap-plan description | "Virtual 87G-DFIG via slip-frequency EKF" |
| Actual scope | ANDES positive-sequence time-domain simulation validating syncOC logic |
| Decision | **Folder wins — no action required** |

**Resolution rationale (ANDES silo audit, 2026-04-19):**  
The on-disk scope is correct. TR-59 delivers ANDES positive-sequence validation of
the sync overcurrent protection (`sync_oc`). The folder name `ANDES_syncoc` accurately
reflects the work. The gap-plan label "Virtual 87G-DFIG slip-frequency EKF" was
imprecise wording written before execution — it confused the DFIG ODE work (which
landed in TR-56) with the ANDES-simulation validation that TR-59 actually performs.
No scope conflict exists; the gap-plan entry is simply an early draft label.

**`tr_namespace_map.yaml` entry:** slug = `ANDES_syncoc`, title = "ANDES syncOC" — correct, no update needed.

---

## TR-64 — IBR_87T_integration

| Item | Value |
|---|---|
| Folder | `TR64_IBR_87T_integration` |
| Gap-plan description | "87T SPRT IBR sensitivity analysis" |
| Actual scope | IBR-aware transformer differential protection: three-hypothesis SPRT integrated with zone model (87T); 16-scenario deterministic validation |
| Decision | **Folder wins** |

**Rationale:**  
The TR-64 report title is unambiguous: *"IBR-Aware Transformer Differential Protection:
Integration of Three-Hypothesis SPRT with Zone Model (87T)"*. The gap-plan label
"sensitivity analysis" is a subset of what was delivered — TR-64 performs a full
integration (SPRT + zone model) and validates it, not just a sensitivity sweep.
The folder name `IBR_87T_integration` is the more accurate description.

**Action:**  
- Gap-plan reference updated below (§ Summary table).  
- `tr_namespace_map.yaml`: slug `IBR_87T_integration`, title updated to
  *"IBR-aware 87T: SPRT + zone model integration"*.

**Risk residual:** Low. Scope overlap with TR-57 (SPRT 87T IBR) is intentional:
TR-57 derived the SPRT algorithm; TR-64 integrates it with the zone model and
validates on IBR fault waveforms. The boundary is clean.

---

## TR-65 — OpenDSS_87B

| Item | Value |
|---|---|
| Folder | `TR65_OpenDSS_87B` |
| Gap-plan description | "Integration DFIG+87T+87L combined" |
| Actual scope | OpenDSS-driven integration testing of SAMBP 87B bus-differential on a distribution network; fault phasors extracted via `dss_interface.py`; 40-scenario test (SLG, DLG, 3PH, A-G) |
| Decision | **Folder wins** |

**Rationale:**  
The gap-plan description "DFIG+87T+87L combined" is wrong for this TR — that combined
integration is what TR-66 (IEEE 39-bus) and TR-67 (HIL/RTDS) deliver. TR-65's actual
scope is distinctly different: it is an OpenDSS-simulation-based validation of the 87B
pipeline using a distribution network model. The folder name `OpenDSS_87B` and the
report title *"OpenDSS-Driven Integration Testing of the SAMBP 87B"* are both correct
and precise.

**Action:**  
- Gap-plan reference corrected in summary table below.  
- `tr_namespace_map.yaml`: slug `OpenDSS_87B`, title updated to
  *"OpenDSS-driven 87B integration test (distribution network)"*.

**Risk residual:** Medium → resolved. The "DFIG+87T+87L combined" work is captured
in TR-66/TR-67; nothing is lost.

---

## TR-66 — IEEE39bus_validation

| Item | Value |
|---|---|
| Folder | `TR66_IEEE39bus_validation` |
| Gap-plan description | "Integration microgrid islanding+87B" |
| Actual scope | IEEE 39-bus New England full-system validation of SAMBP nine-function protection scheme (87T, 87L, 87G, 87B, 21, 46, 51, 67, 81) on one protection corridor; impedance-matrix fault current model |
| Decision | **Folder wins** |

**Rationale:**  
The gap-plan description "microgrid islanding+87B" is a misnomer. TR-66 operates on
the IEEE 39-bus transmission test system (not a microgrid), covers nine protection
functions (not just 87B), and does not perform an islanding study. The actual work is
a comprehensive full-system coordination validation — substantially broader in scope
than the gap-plan label implied. The folder name `IEEE39bus_validation` and the report
title *"IEEE 39-Bus Full-System Validation of the SAMBP Nine-Function Protection Scheme"*
are correct.

**Action:**  
- Gap-plan reference corrected in summary table below.  
- `tr_namespace_map.yaml`: slug `IEEE39bus_validation`, title updated to
  *"IEEE 39-bus full-system 9-function SAMBP validation"*.

**Risk residual:** Medium → resolved. Microgrid islanding is a different topic not
covered in TR-66 or anywhere else in TR-01–TR-91 as a standalone study (islanding
detection is addressed in TR-39). No gap is introduced by this reconciliation.

---

## TR-67 — HIL_RTDS

| Item | Value |
|---|---|
| Folder | `TR67_HIL_RTDS` |
| Gap-plan description | "Integration full SAMBP chain" |
| Actual scope | Hardware-in-the-Loop validation of the SAMBP framework with DFIG and PV emulators on RTDS; 62-scenario campaign; SEL-300G, GE D60, and Python IED on IEC 61850 Ed.2 GOOSE bus |
| Decision | **Folder wins** |

**Rationale:**  
"Integration full SAMBP chain" is broadly correct — TR-67 does validate the full
SAMBP chain — but it is not specific enough to distinguish this TR from TR-53
(HIL Protocol) or TR-66 (IEEE 39-bus software validation). The folder name
`HIL_RTDS` and the report title make clear that the distinguishing feature is
*hardware*: real relay hardware (SEL-300G, GE D60) + RTDS + DFIG/PV emulators.
The gap-plan label can be retired in favour of the more specific hardware description.

**Action:**  
- Gap-plan reference updated in summary table below.  
- `tr_namespace_map.yaml`: slug `HIL_RTDS`, title updated to
  *"HIL/RTDS validation — DFIG+PV emulators, SEL+GE relays, IEC 61850 Ed.2"*.

**Risk residual:** Low. TR-67 subsumes "full SAMBP chain" as stated in the gap plan;
no scope is lost. The rename makes the hardware-validation nature explicit.

---

## Summary Table

| TR | Folder | Old gap-plan description | Corrected description | Decision |
|---|---|---|---|---|
| TR-59 | ANDES_syncoc | Virtual 87G-DFIG via slip-frequency EKF | ANDES positive-sequence syncOC validation | Folder wins — no action |
| TR-64 | IBR_87T_integration | 87T SPRT IBR sensitivity analysis | IBR-aware 87T: SPRT + zone model integration | Folder wins |
| TR-65 | OpenDSS_87B | Integration DFIG+87T+87L combined | OpenDSS-driven 87B integration test (distribution network) | Folder wins |
| TR-66 | IEEE39bus_validation | Integration microgrid islanding+87B | IEEE 39-bus full-system 9-function SAMBP validation | Folder wins |
| TR-67 | HIL_RTDS | Integration full SAMBP chain | HIL/RTDS validation — DFIG+PV emulators, SEL+GE relays, IEC 61850 Ed.2 | Folder wins |

**General rule confirmed:** In all five cases the on-disk TR report is the authoritative
scope record. Gap-plan labels were written before execution; when they diverge from the
completed work, the completed work wins. No folder renames are needed.

---

*Document: 03_technical_reports/SCOPE_RECONCILIATION_2026-04-26.md*  
*Author: Anoop V. Eluvathingal, SGCRL, IIT Madras*  
*Date: 2026-04-26*
