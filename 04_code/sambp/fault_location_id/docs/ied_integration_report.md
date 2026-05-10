# WP5.2 IEC 61850-9-2 SV + GOOSE — IED integration report

**Project:** SAMBPS DTaaS — `fault_location_id` Phase 5 (WP5.2)
**Owner:** Anoop Eluvathingal (PI)
**Issued:** 2026-05-10
**Status:** **Software-side complete; hardware-side measurements
              pending HIL access** (see [`hil_access_matrix.md`](hil_access_matrix.md))

---

## 1. Executive summary

WP5.2 ships the SV + GOOSE round-trip framework for the SAMBPS
DTaaS HIF-locator integration with a relay-class IED.  Both the
software-side and hardware-side activities are scoped here; the
**software-side is complete and tested** on the dev box, while the
**hardware-side measurements** (real Merging Unit, real IED,
real Wireshark capture) are gated on the WP5.1 partner-access
plan.

K09 acceptance (end-to-end latency < 5 power-frequency cycles =
100 ms at 50 Hz):

| Metric | Mock-replay (dev box) | HW-mode (HIL site) |
|---|---|---|
| K09 ≥ 25 / 30 scenarios under 100 ms | **PASS** (per `hil/test_latency.py::test_K09_mock_replay_...`) | **PENDING** (xfail-strict on the SV capture file presence) |
| Estimator | DFT (the K09 critical-path estimator; TFT-K=1 path is K06) | DFT |
| Max latency observed | < 100 ms across all 30 cells | _PLACEHOLDER (HIL-site capture)_ |

## 2. SV stream timing (target characteristics)

Per the WP5.2 brief: 1-second SV traffic capture at the HIL site
must demonstrate ≤ 10 µs jitter and zero packet loss.  The
`outputs/phase5_sv_capture.pcapng` Wireshark capture file is
generated at the HIL site (the .pcapng file is NOT committed —
WP5.2 brief explicitly forbids binary captures > 50 MB; an
out-of-tree drop point is documented at `data/phase5_hil_drops/`
which is in `.gitignore`).

| SV stream parameter | Target | Mock-replay (dev box) | HW-mode (HIL site) |
|---|---|---|---|
| Sample rate | 4800 Hz (= 50 Hz · 96 samples/cycle) | `SV_RATE_HZ` constant in subscriber module | _HIL-site capture_ |
| Channels | V_a, V_b, V_c, I_a, I_b, I_c | `(V_abc, I_abc)` tuple via `_generate_sv_stream` | _HIL-site capture_ |
| Jitter | ≤ 10 µs | _N/A in mock_ | **PENDING** |
| Packet loss | 0 over 1 s | _N/A in mock_ | **PENDING** |

## 3. End-to-end latency budget

| Stage | Mock-replay (dev box) | HW-mode (HIL site, target) |
|---|---|---|
| SV ingress on subscriber NIC | _N/A in mock_ | < 0.5 ms |
| 1-cycle sample accumulation | 96 / 4800 = 20.0 ms (real-time) | 20.0 ms |
| Phasor estimator (DFT) + WP1.4 / WP2.4 optimiser | < 80 ms (dev box i7) | ≤ 50 ms (dedicated PC) |
| Custom GOOSE encode | _N/A in mock_ | < 1 ms |
| GOOSE egress to IED NIC | _N/A in mock_ | < 0.5 ms |
| **K09 budget total** | **< 100 ms** (= 5 cycles) | **target < 100 ms** |

## 4. SV → GOOSE round-trip — per-scenario K09 results (mock)

The 30 scenarios sweep:

* `alpha`   ∈ {0.1, 0.3, 0.5, 0.7, 0.9} (5 values)
* `R_x`     ∈ {200, 1000, 5000} Ω (3 values)
* `SNR_I`   ∈ {30, 40} dB (2 values)
* `arc`     ∈ {emanuel, kizilcay, wang2020, torres_tree} (4 values)

(5 × 3 × 2 × 4 = 120 cells, sub-sampled to 30 representative
combinations).  K09 acceptance: ≥ 25 of 30 scenarios under
100 ms — measured **30 of 30 PASS** in the latest dev-box run.

The full per-scenario CSV is regenerated at every test-suite run;
see `pytest --tb=short hil/test_latency.py -v` for the per-scenario
output.

## 5. Hardware-side activities (deferred per WP5.1 access plan)

Per the WP5.2 brief items 1, 2, 4, 5 require physical HIL access
that the WP5.1 partner-memo chain has not yet confirmed:

1. **Source IED** (item 1): currently *target-only* in
   [`ied_target.md`](ied_target.md); IED selection at HIL-site
   visit time per the access matrix.
2. **Configure Merging Unit** (item 2): the RTDS GTNETx2-SV /
   Typhoon HIL native MU configuration is documented in
   `ied_target.md` §2; commissioning happens at the HIL site.
3. **Wireshark + iec61850 dissector capture** (item 4): the
   `outputs/phase5_sv_capture.pcapng` capture is generated at
   the HIL site; the file is not committed (size > 50 MB per
   the WP5.2 brief).
4. **End-to-end latency test on real HIL** (item 5): the
   `hil/test_latency.py::test_K09_hil_mode_capture_file_present`
   test is xfail-pending until the HIL capture is dropped at the
   canonical path; closure is gated on partner-window
   confirmation.

## 6. Open items requiring PI / HIL-site sign-off

1. **Confirm IED on site** ([`ied_target.md`](ied_target.md) §1).
2. **Confirm IED firmware version** (§2).
3. **Confirm IED's SCD/CID file is editable** for the custom
   GOOSE message (§4).
4. **Confirm Merging Unit type** (§5).
5. **Drop HIL capture file** at `outputs/phase5_sv_capture.pcapng`
   (after the visit) so the xfail-pending test re-tightens.
