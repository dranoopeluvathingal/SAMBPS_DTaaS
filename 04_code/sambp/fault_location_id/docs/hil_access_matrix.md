# WP5.1 HIL access matrix — three redundant AC paths + one HVDC follow-on

**Project:** SAMBPS DTaaS — `fault_location_id` Phase 5
**Owner:** Anoop Eluvathingal (PI)
**Issued:** 2026-05-10
**Reviewer:** Prof. K. Shanthi Swarup (host advisor)

> Per the WP5.1 brief: three redundant access paths to a real-time
> HIL testbed for Phase-5 closed-loop validation of the proposed
> HIF locator, plus one exploratory HVDC follow-on contact.
> All access is **request-pending PI sign-off** (the four memos
> are drafted in this commit but not sent).

---

## Feature-by-feature access matrix

Legend:
  C = confirmed available;
  R = requested in partner memo (this commit);
  P = present at site but availability TBC;
  N = not applicable / not available;
  ? = unknown until partner liaison confirms.

| Feature | IIT Madras (primary) | NUS GEMS (Path 2) | NTU CTSP (Path 3) | Amprion (HVDC follow-on) |
|---|---|---|---|---|
| **RTDS** real-time simulator | ?  (PI to confirm; see [`hil_iitm_status.md`](hil_iitm_status.md) §2) | R (per `partnership_memo_NUS_GEMS.md`) | R (per `partnership_memo_NTU_CTSP.md`) | N (HVDC follow-on; not Phase-5 scope) |
| **Typhoon HIL** real-time simulator | ?  (PI to confirm; fallback option) | ? | ? | N |
| **μ-PMU** with C37.118.2 streaming | ? | R (Cui-Weng 2020 reproduction) | R | N |
| **Relay-class IED** (SEL / Siemens / GE / ABB) | ? | ? | R (closed-loop K09) | N |
| **Power amplifier** (Doble / OMICRON / Megger F6150) | ? | R | R | N |
| **GPS-disciplined timing** (1 PPS + IRIG-B) | ? | R | R | N |
| **IEC 61850-9-2 SV streaming** | ? | ? | R | N |
| **IEC 61850 GOOSE** | ? | ? | R | N |
| **HVDC test bench** (LCC / VSC / MMC) | N | N | N | future contact only — see `partnership_memo_Amprion.md` |
| **Adversarial / stability stress envelope** (ML-DSA cross-track) | N | N | R (CTSP specialty) | N |

## Phase-5 acceptance dependencies

The Phase-5 acceptance criterion **K09** ("mean loc-err < 2 % on
≥ 5 traces under closed-loop SV streaming + IED protection logic
in a HIL testbed") requires AT LEAST ONE site to provide:

* RTDS or Typhoon HIL real-time simulator;
* Relay-class IED in the loop;
* GPS-disciplined timing;
* IEC 61850-9-2 SV streaming OR direct sample-stream injection;
* Power amplifier between simulator and IED;
* μ-PMU (only required if testing the Cui-Weng 2020 / Zeng-2021
  competitor pipelines).

Currently, the three redundant paths cover this matrix as
follows:

| Site | RTDS/Typhoon | IED | Timing | SV | Amplifier | μ-PMU | K09-coverage |
|---|---|---|---|---|---|---|---|
| IIT Madras | ? | ? | ? | ? | ? | ? | **TBC pending PI inventory check** |
| NUS GEMS | R | ? | R | ? | R | R | **K09 partial** (μ-PMU strong; IED + SV TBC) |
| NTU CTSP | R | R | R | R | R | ? | **K09 strong** (full IED + SV + amplifier) |
| Amprion | N | N | N | N | N | N | **N/A** (HVDC follow-on only) |

## Critical-path scenario analysis

Three scenarios captured below, ranked from most-preferred to
fallback:

1. **Best case**: NTU CTSP confirms; K09 done at NTU CTSP in
   Q4-2026 / Q1-2027.  IIT Madras supports at the IDE / non-RT
   integration stage.  NUS GEMS becomes a μ-PMU cross-check
   bench for the Cui-Weng-2020 competitor.

2. **Likely case**: NUS GEMS + NTU CTSP each provide a 2-week
   slot; we run the K09 on NTU CTSP and the μ-PMU competitor
   reproduction on NUS GEMS.  IIT Madras hosts the offline-to-
   real-time integration phase.

3. **Fallback case**: Both NUS-GEMS and NTU-CTSP windows slip past
   Q1-2027.  The PI has **pre-approved up to USD 30 k** for a
   Typhoon HIL-602+ at IIT Madras as fallback (signoff recorded
   2026-05-10; see
   [`hil_iitm_status.md`](hil_iitm_status.md) §6).  Procurement
   triggers automatically if both partner windows slip past
   2027-Q1.

PI sign-off log (recorded 2026-05-10 in response to the WP5.1
brief):

* (a) **Review-and-edit-before-send**: PI to edit memos in the
  working tree directly; commit lands first to capture the audit
  trail; sending is a follow-on PI action.
* (b) **Visit-budget**: APPROVED up to USD 8 k per visit (flights
  + accommodation + per-diem + visa).  Recorded in each partner
  memo's "Proposed visit dates" section.
* (c) **Typhoon HIL fallback**: PRE-APPROVED at USD 30 k for a
  HIL-602+ at IITM if both NUS / NTU windows slip past Q1-2027.
  Recorded in `hil_iitm_status.md` §6.

## File map

| File | Path | Role |
|---|---|---|
| IITM equipment status | [`hil_iitm_status.md`](hil_iitm_status.md) | Primary path inventory + commissioning timeline + Typhoon-fallback decision form |
| NUS GEMS memo | [`partnership_memo_NUS_GEMS.md`](partnership_memo_NUS_GEMS.md) | Path 2: μ-PMU + RTDS testbed access request |
| NTU CTSP memo | [`partnership_memo_NTU_CTSP.md`](partnership_memo_NTU_CTSP.md) | Path 3: stability-and-security HIL testbed access request |
| Amprion memo | [`partnership_memo_Amprion.md`](partnership_memo_Amprion.md) | HVDC follow-on track introduction (NOT Phase-5 scope) |

## Status of this commit

* **All four memos drafted, not sent.**
* **IITM status doc has placeholder rows for the PI's inventory
  walkthrough.**
* **Access matrix populated** with R / ? / C cells per the partner
  memos.
* **PI sign-off requested** before any of the memos leave the
  project.

The WP5.1 commit lands these drafts into the repository so the
draft chain is auditable; the **send** step is gated on PI sign-
off (the same pattern used at WP4.5 for the competitor blind-
review template).
