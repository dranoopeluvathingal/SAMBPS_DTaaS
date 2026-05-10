# Phase 5 HIL pilot report — 25 + 5 scenario campaign

> **STATUS — DRAFT, SIMULATION ONLY.**  This document was
> generated from the WP5.3 dev-box simulation campaign.  The
> hardware-side equivalent (real IED + real Merging Unit + real
> SV/GOOSE capture + photographs of the lab setup) is gated on
> the WP5.1 partner-window confirmation; once HIL access lands,
> this report is updated with the live-campaign data and the
> ``STATUS — DRAFT, SIMULATION ONLY`` banner is removed.

**Project:** SAMBPS DTaaS — `fault_location_id` Phase 5 (WP5.3)
**Owner:** Anoop Eluvathingal (PI)
**Issued:** 2026-05-10
**Reviewer (target):** Prof. K. Shanthi Swarup + at least one of
            {IITM, NUS GEMS, NTU CTSP, Amprion} per the K10 KPI

---

## 1. Test campaign at a glance

| Item | Value |
|---|---|
| Network | IEEE 34-node test feeder (per WP3.3, single-section forward model) |
| Locator | WP1.4 / WP2.4 single-bin DFT optimiser (WP3.5 TFT-K=1 path also wired in `SVSubscriber`) |
| Pipeline | IEC 61850-9-2LE SV @ 4.8 kHz → SVSubscriber dev-box mode → WP1.4 optimiser → custom GOOSE message |
| Arc stimulus | Wang-2020 distortion-controllable (P4.3) primary; Torres-2022 tree (P4.4) cross-arc subset |
| Scenarios | 25 primary + 5 cross-arc = 30 total |
| Mode | **DEV-BOX SIMULATION** (real HIL pending WP5.1) |
| Vendor IED | _PLACEHOLDER (HIL-site visit per [`ied_target.md`](ied_target.md))_ |
| Merging Unit | _PLACEHOLDER (RTDS GTNETx2-SV / Typhoon HIL native / vendor MU)_ |
| SV configuration | 4.8 kHz, 6 channels (V_a/b/c, I_a/b/c), 96 samples/cycle |

## 2. Scenario list

### 2.1 Primary 25 (Wang-2020 default arc on IEEE 34)

5 fault locations × 5 R_x values × 1 fault-type (SLG):

| α | R_x ∈ {200, 500, 1000, 2000, 5000} Ω |
|---|---|
| 0.1 | scenarios 1–5 |
| 0.3 | scenarios 6–10 |
| 0.5 | scenarios 11–15 |
| 0.7 | scenarios 16–20 |
| 0.9 | scenarios 21–25 |

### 2.2 Cross-arc subset (Torres-2022 ``tree`` profile)

5 of the primary cells re-run with the Torres-2022 ``tree``
profile to demonstrate cross-arc robustness:

| Scenario | α | R_x | Cell |
|---|---|---|---|
| 26 | 0.1 | 200 Ω | re-run of #1 |
| 27 | 0.3 | 500 Ω | re-run of #7 |
| 28 | 0.5 | 1000 Ω | re-run of #13 |
| 29 | 0.7 | 2000 Ω | re-run of #19 |
| 30 | 0.9 | 5000 Ω | re-run of #25 |

## 3. Headline numbers (dev-box simulation)

### 3.1 Primary 25 (Wang-2020)

| Metric | Value | K10 target | Status |
|---|---|---|---|
| Mean loc-err | **239.46 %** | < 5 % | **XFAIL** (R-WP4.1-1 floor) |
| p50 loc-err  | **99.98 %**  | — | — |
| p95 loc-err  | **899.90 %** | < 10 % | **XFAIL** |
| Mean R_x-err | **32.70 %**  | — | — |
| p95 R_x-err  | **56.71 %**  | — | — |
| Mean max-cycle latency | **65.6 ms** | < 100 ms | **PASS** |
| Worst-case max-cycle latency | **85.7 ms** | < 100 ms | **PASS** (K09) |

### 3.2 Cross-arc subset (Torres-tree)

| Metric | Value |
|---|---|
| Mean loc-err | **257.42 %** |
| p95 loc-err  | **766.58 %** |

### 3.3 Diagnosis

The proposed estimator collapses to the boundary α = 1 on every
primary scenario at SNR_I = 40 dB.  This is the **structural
single-bin DFT identifiability floor** documented as R-WP4.1-1 /
R-WP3.4-1 / R5 in the project risk register: at high R_x +
high SNR_I, the per-entry fault signature drops below the line-
admittance baseline, leaving the optimiser cost surface near-
degenerate along a curve in (α, R_x) space and the gradient
descent pulled to the boundary.

The structural closure path is identified:

* **WP3.5 multi-bin Taylor-Fourier estimator** (K06 PASS at
  55.94 % bias improvement) — already shipped at the WP3.5 commit.
* **WP3.6 multi-port FIM** over the 3×3 Y_send observation
  surface (over-determined by 9× — 18 real obs vs 2 unknowns) —
  already shipped at the WP3.6 commit.
* The closure path requires a **forward-model rewire** in the
  optimiser to use multi-bin TFT phasors on the 3-port observation
  surface.  This is a follow-on commit (out of WP5.3 scope).

The K09 (latency) acceptance is **MET**: all 30 scenarios
complete the SV → SVSubscriber → optimiser → GOOSE pipeline
under 100 ms wall-clock on the dev box (max 85.7 ms; mean
65.6 ms).  The hardware-side end-to-end latency adds the SV
ingress + GOOSE egress NIC time (< 2 ms target per the WP5.2
budget) so the K09 budget on the real HIL has 12 ms of headroom.

## 4. Diagnostic plots

Per-scenario diagnostic plots are generated at
[`outputs/phase5_figs/`](../outputs/phase5_figs/) — one PDF per
scenario.  Each shows:

* Top panel: V_a (kV) + I_a (A) waveform over the 5-cycle window.
* Bottom panel: per-cycle α̂ vs ground-truth α (5 markers).

Selected plots reproduced in the LaTeX-rendered version of this
report (TBD when the LaTeX template lands).

## 5. SV/GOOSE capture metadata

Per the WP5.3 brief: capture truncated to 5 s per scenario;
**only metadata + selected diagnostic plots are committed**.  The
full SV/GOOSE pcapng files (~ 50-200 MB per scenario at 4.8 kHz)
are NOT committed and live at the HIL site's permitted-vendoring
drop point (per [`hil_access_matrix.md`](hil_access_matrix.md)).

| Item | Value |
|---|---|
| SV stream rate | 4800 Hz (= 50 Hz × 96 samples/cycle) |
| Channels | V_a, V_b, V_c, I_a, I_b, I_c |
| Capture window per scenario | 5 s |
| Capture file size per scenario | _PLACEHOLDER (HIL-site capture)_ |
| Wireshark dissector | iec61850 (default in 4.x) |
| Drop location | _PLACEHOLDER (HIL site / licensed Windows runner)_ |

## 6. Photographs of the lab setup

_PLACEHOLDER._  Photographs are captured at the HIL-site visit
window per the WP5.3 brief.  SAMBPS PI consent for any
Amprion / NUS / NTU partner-personnel appearance in the
photographs is recorded separately (release form drafted but not
yet signed by partners).

## 7. Institutional pilot signoff (KPI K10 ≥ 1)

| Institution | Signoff status | Reviewer | Date | Notes |
|---|---|---|---|---|
| IITM | _PENDING_ | _PENDING_ | _PENDING_ | Primary path; signoff after dry-run at IITM RTDS |
| NUS GEMS | _PENDING_ | _PENDING_ | _PENDING_ | Path 2; signoff after partner-window visit |
| NTU CTSP | _PENDING_ | _PENDING_ | _PENDING_ | Path 3; signoff after partner-window visit |
| Amprion | N/A | — | — | HVDC follow-on track only; not in K10 scope |

When at least one institution signs the report, replace the
``_PENDING_`` row above with:

```
| <institution> | signed-off | <reviewer name> | <YYYY-MM-DD> |
                                              <signoff-specific notes> |
```

and update the document banner at the top from "DRAFT, SIMULATION
ONLY" to the live-campaign status.

## 8. Open items

1. **HIL access** — ship the campaign on a real HIL testbed per
   [`hil_access_matrix.md`](hil_access_matrix.md).
2. **Forward-model rewire** — wire the multi-bin TFT + multi-port
   FIM into the optimiser to break the R-WP4.1-1 / R5 floor.
3. **Photographs of lab setup** — capture at HIL-site visit; obtain
   PI / partner consent forms for any partner-personnel appearance.
4. **SV capture pcapng drop point** — coordinate with the licensed
   Windows runner to drop the .pcapng files at a place the project
   can reference without committing the binary captures.
5. **Institutional signoff** — at least one of {IITM, NUS GEMS,
   NTU CTSP} (Amprion is HVDC-only, not in K10 scope).
