# Partnership memo — NUS GEMS μ-PMU + RTDS testbed access

**To:** Prof. Dipti Srinivasan, Director,
        Green Energy Management & Smart-Grid Group (GEMS),
        Department of Electrical & Computer Engineering,
        National University of Singapore

**From:** Anoop Eluvathingal, PI, SAMBPS DTaaS — Fault-Location
        Identification project; co-supervised at IIT Madras Power
        Systems Computational Lab by Prof. K. Shanthi Swarup.

**Subject:** Request for joint use of the NUS-GEMS RTDS + μ-PMU
            testbed for a 2-week visit, Phase-5 HIL validation of
            a single-ended HIF locator.

**Date:** 2026-05-10

---

Dear Prof. Srinivasan,

I am writing to request joint use of the NUS-GEMS RTDS + μ-PMU
testbed for a focused 2-week visit during the Phase-5 hardware-
in-the-loop (HIL) validation of the SAMBPS DTaaS Fault-Location
Identification project (single-ended joint estimator of HIF
location and arc resistance).

### Shared technical context

The Cui-Weng 2020 IEEE TSG paper (μ-PMU-based HIF localisation,
TSG vol. 11, no. 1) is one of the four head-to-head competitors
in our Phase-4 numerical benchmark (`outputs/phase4_table3bis.csv`
in the public repository).  A canonical real-time HIL reproduction
of the Cui-Weng pipeline on the GEMS testbed would be an immediate
reciprocal benefit — both for our K05 / K09 Phase-5 acceptance
and for any GEMS group members who want to extend the µ-PMU
locator to multi-fault-class or distributed-resource-saturated
operating conditions.  The ASGARD project's digital-port AIoT
framing is also a natural integration point for the SAMBPS DTaaS
sub-station-side digital-twin emission patterns we have
developed; we would welcome a discussion on a possible
ASGARD-side integration sub-track.

### Proposed visit dates

_PLACEHOLDER:_ a 2-week window in **Q4-2026 or Q1-2027**, exact
dates pending GEMS lab calendar.  Travel and accommodation are
self-funded from the IIT-Madras project travel envelope (PI
sign-off recorded 2026-05-10 at up to USD 8 k per visit covering
flights, accommodation, per-diems, and visa fees).

### Technical scope

1. Stand up the proposed HIF locator on a 3-phase IEEE 34-node
   RTDS case at the GEMS testbed.
2. Stream substation-side V/I and one remote-end μ-PMU phasor
   into the locator + the four Phase-4 competitors over a
   GPS-disciplined IEEE C37.118.2 channel.
3. Inject closed-loop arc stimuli (Emanuel + Wang-2020 + Torres-
   2022) using a Doble / OMICRON power amplifier and capture the
   round-trip locator + competitor outputs.
4. Reproduce the Cui-Weng 2020 µ-PMU two-ended pipeline on the
   same testbed for direct head-to-head comparison.

### Expected reciprocal benefit

* Real-time HIL validation of the GEMS testbed's μ-PMU phasor
  delivery chain on a non-trivial high-impedance fault scenario
  (a fault class that is genuinely hard for the standard
  protection-zone benchmarks the testbed is more often used for).
* Open-source release of our Phase-5 results under MIT licence
  with full provenance to GEMS as the testbed provider; we expect
  this to be a strong addition to the GEMS group's ASGARD output
  list and an easy win for joint co-authorship on a follow-on
  IEEE TSG benchmark paper.
* SAMBPS DTaaS will share the surrogate dataset bundles + MIT-
  licensed source for any GEMS members who want to reproduce the
  results on a different testbed.

### Request

We respectfully request:

1. Tentative confirmation of a 2-week window for the visit
   (Q4-2026 or Q1-2027).
2. The name + contact details of a **technical liaison** at the
   GEMS testbed (RTDS / μ-PMU / amplifier hands-on operator) so
   we can pre-coordinate the test setup.
3. A short Zoom call at your convenience to scope the visit and
   confirm reciprocal expectations.

I will follow up with a more detailed test plan once a window is
tentatively confirmed.  Thank you for considering this request.

Sincerely,

Anoop Eluvathingal
PhD candidate, IIT Madras Power Systems Computational Lab
SAMBPS DTaaS — Fault-Location Identification project
Email: ianoopeluvathingal@gmail.com
Public repo: https://github.com/SAMBPS-DTaaS/HIF-TF-Locator

cc: Prof. K. Shanthi Swarup (host advisor, IIT Madras)
