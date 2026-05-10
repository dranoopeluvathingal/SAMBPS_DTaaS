# HIL platform status — IIT Madras Power Systems Computational Lab

**Project:** SAMBPS DTaaS — `fault_location_id` Phase 5 (real-time
HIL validation)
**Owner:** Anoop Eluvathingal (PI)
**Issued:** 2026-05-10
**Reviewer:** Prof. K. Shanthi Swarup (host advisor, IIT Madras
Power Systems Computational Lab)

---

## 1. Why this document exists

WP5.1 (P5.1) of the v3 Execution Manual requires a real-time
hardware-in-the-loop (HIL) testbed for end-to-end validation of
the proposed HIF locator under arc-stimulus + IED-side
measurement-chain conditions that the dev-box surrogate cannot
reproduce.  Three redundant access paths are pursued in parallel
(see [`docs/hil_access_matrix.md`](hil_access_matrix.md)); this
document records the **primary** path: the IIT Madras Power
Systems Computational Lab.

## 2. Current equipment inventory

| Item | Status | Notes |
|---|---|---|
| RTDS (Real-Time Digital Simulator) | **CONFIRM with PI / lab manager** | _PLACEHOLDER_: existing rack count, NovaCor vs PB5 generation, GTNET / GTAO card complement, IEC 61850-9-2 SV cards. |
| Typhoon HIL | **CONFIRM with PI / lab manager** | _PLACEHOLDER_: HIL-602+ / HIL-606 / HIL-404 platform; expansion-card complement. |
| Relay-class IED | **CONFIRM** | _PLACEHOLDER_: SEL-411L / Schneider P545 / ABB REL670 / GE D60 distance / line-differential relays available for closed-loop tests. |
| Mu-PMU | **CONFIRM** | _PLACEHOLDER_: PMU class (P / M), GPS-disciplined timing reference, IEEE C37.118.2 streaming endpoint. |
| Power amplifier (signal -> secondary CT/PT) | **CONFIRM** | _PLACEHOLDER_: Doble / Megger F6150 / OMICRON CMC356 with low-noise pre-amp stage. |
| GPS-disciplined timing | **CONFIRM** | _PLACEHOLDER_: 1 PPS + IRIG-B distribution to all RT racks. |

The PI is asked to fill in the placeholder rows above before this
document leaves the project; this commit ships the structure +
the dependencies on the placeholder rows.

## 3. Software-license inventory

| Software | License status | Notes |
|---|---|---|
| RSCAD (RTDS) | **CONFIRM** | Per-seat or per-rack; site-license vs node-locked. |
| Typhoon HIL Schematic Editor | **CONFIRM** | Permanent vs annual subscription; advanced-control and protection toolboxes. |
| MATLAB / Simulink Real-Time | **CONFIRM** | Network license server availability; required toolboxes. |
| PSCAD / EMTDC | **CONFIRM** | Education vs Pro edition; co-sim with HIL. |
| OMICRON Test Universe | **CONFIRM** | Required for IED end-to-end tests. |
| IEC 61850 / Goose / SV protocol stack | **CONFIRM** | TASE-2 / Goose / SV-9-2 publishing + subscription stacks. |

## 4. Technician availability

The HIL testbed at IIT Madras is run by [_PLACEHOLDER_: lab
technician name + email + working-hours availability].  Per the
WP5.1 brief, the named technical liaison for the SAMBPS DTaaS
HIL run is requested as part of this commissioning request; the
PI will name the liaison directly to the lab manager.

## 5. Proposed commissioning timeline

| Milestone | Target date | Owner |
|---|---|---|
| Equipment-inventory walkthrough (this document filled in) | _PLACEHOLDER: target Q3-2026_ | PI + lab manager |
| Software-license confirmation | within 2 weeks of walkthrough | PI |
| First test-bench dry-run (proposed locator only, no IED) | **target 2026-Q4** | PI + technician |
| First closed-loop IED-in-the-loop run | target 2027-Q1 | PI + technician + IED partner |
| Phase-5 acceptance (K09: < 2 % loc-err on 5+ traces under closed-loop SV streaming + IED protection logic) | target 2027-Q2 | PI |

The dates assume the redundant NUS-GEMS / NTU-CTSP paths land
within Phase-5; if those paths slip, IITM commissioning becomes
the **critical path** and the dates above need to slide right
proportionally.

## 6. Decision: commission a Typhoon HIL as fallback?

**PI signoff: PRE-APPROVED up to USD 30 k for a Typhoon HIL-602+
+ single signal-amplifier rack as fallback** (recorded 2026-05-10
per the WP5.1 brief sign-off response).  Procurement triggers
automatically if both NUS-GEMS and NTU-CTSP windows slip past
2027-Q1.  USD 60 k upgrade path to a HIL-604+ with two amplifier
racks + SV-streaming card remains an option but is NOT pre-
approved at this commit.

## 7. Open items requiring PI sign-off

1. **Confirm equipment inventory** above (Section 2): exact RTDS /
   Typhoon HIL generation + IED + μ-PMU + amplifier + GPS-timing
   complement.
2. **Confirm software-license envelope** (Section 3).
3. **Name the technical liaison** for the SAMBPS DTaaS HIL run
   (Section 4).
4. **Confirm commissioning timeline** (Section 5) — does the
   first dry-run land in Q4-2026 as proposed?
5. ~~**Decide on Typhoon HIL fallback budget** (Section 6)~~ —
   **PRE-APPROVED 2026-05-10** at USD 30 k envelope.
