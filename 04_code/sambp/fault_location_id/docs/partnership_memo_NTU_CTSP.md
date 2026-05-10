# Partnership memo — NTU CTSP stability-and-security HIL testbed access

**To:** Prof. Yan Xu, Cham Tao Soon Professorship in Stability &
        Security of Power Systems, School of Electrical &
        Electronic Engineering, Nanyang Technological University

**From:** Anoop Eluvathingal, PI, SAMBPS DTaaS — Fault-Location
        Identification project; co-supervised at IIT Madras Power
        Systems Computational Lab by Prof. K. Shanthi Swarup.

**Subject:** Request for joint use of the NTU CTSP stability-and-
            security HIL testbed for a 2-week visit, Phase-5 HIL
            validation of a single-ended HIF locator.

**Date:** 2026-05-10

---

Dear Prof. Xu,

I am writing to request joint use of the NTU CTSP stability-and-
security HIL testbed for a focused 2-week visit during the
Phase-5 hardware-in-the-loop (HIL) validation of the SAMBPS DTaaS
Fault-Location Identification project (single-ended joint
estimator of HIF location and arc resistance).

### Shared technical context

Your group's ML-DSA work (a long line of IEEE TPS papers on
machine-learning-based dynamic security assessment) sits naturally
adjacent to the data-driven fault-location pipeline we have
developed at SAMBPS DTaaS.  Both projects share the same
fundamental question — *given short post-fault windows of V/I
data, what can be inferred and how reliably?* — and answer it
from complementary directions.  A 2-week HIL run at NTU CTSP
would let us cross-test the proposed locator against the kind of
adversarially-stressed transient operating conditions your
testbed is typically used for, and would feed into a possible
joint paper on the ML-DSA × HIF-locator boundary.

The SAMBPS DTaaS programme (the wider digital-twin-as-a-service
mother project sponsoring this thesis) is also actively building
an offline-to-real-time validation pipeline that the NTU CTSP
testbed would be a natural deployment target for in a follow-on
phase.

### Proposed visit dates

_PLACEHOLDER:_ a 2-week window in **Q4-2026 or Q1-2027**, exact
dates pending CTSP lab calendar.  Travel and accommodation are
self-funded from the IIT-Madras project travel envelope (PI
sign-off recorded 2026-05-10 at up to USD 8 k per visit covering
flights, accommodation, per-diems, and visa fees).

### Technical scope

1. Stand up the proposed HIF locator on a 3-phase IEEE 34-node
   RTDS case at the CTSP testbed.
2. Run a back-to-back stress sweep with the four Phase-4
   competitors under closed-loop SV streaming + relay-class IED
   protection logic.
3. Inject Emanuel + Wang-2020 + Torres-2022 arc stimuli through a
   power amplifier and record the locator's response under
   IED-in-the-loop closed-loop conditions (the K09 acceptance).
4. Joint discussion of a possible ML-DSA cross-track on adversarial
   stress-scenario sweeps for the locator (a follow-on publication
   track, not Phase-5 scope).

### Expected reciprocal benefit

* HIL-traceable validation of the CTSP testbed's stability-and-
  security IED layer on a high-impedance-fault scenario class
  that classical distance / line-differential protection misses.
* Open-source release of our Phase-5 results under MIT licence
  with full provenance to NTU CTSP as the testbed provider; joint
  co-authorship on a follow-on IEEE TSG / TPS paper if the cross-
  track yields publishable results.
* SAMBPS DTaaS contributes the surrogate datasets + Python source
  for any CTSP group member who wants to reproduce the results on
  a different testbed or extend them to the ML-DSA cross-track.

### Request

We respectfully request:

1. Tentative confirmation of a 2-week window for the visit
   (Q4-2026 or Q1-2027).
2. The name + contact details of a **technical liaison** at the
   CTSP testbed (RTDS / IED / amplifier hands-on operator) for
   pre-coordination.
3. A short Zoom call at your convenience to scope the visit and
   the possible ML-DSA cross-track.

I will follow up with a more detailed test plan once a window is
tentatively confirmed.  Thank you for considering this request.

Sincerely,

Anoop Eluvathingal
PhD candidate, IIT Madras Power Systems Computational Lab
SAMBPS DTaaS — Fault-Location Identification project
Email: ianoopeluvathingal@gmail.com
Public repo: https://github.com/SAMBPS-DTaaS/HIF-TF-Locator

cc: Prof. K. Shanthi Swarup (host advisor, IIT Madras)
