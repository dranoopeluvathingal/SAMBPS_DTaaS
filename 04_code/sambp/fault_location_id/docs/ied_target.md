# Target IED — Phase 5 IEC 61850-9-2 + GOOSE integration

**Project:** SAMBPS DTaaS — `fault_location_id` Phase 5 (WP5.2)
**Owner:** Anoop Eluvathingal (PI)
**Issued:** 2026-05-10
**Status:** **Hardware sourcing pending** (gated on WP5.1 partner
            access; see [`hil_access_matrix.md`](hil_access_matrix.md))

---

## 1. Why this document exists

WP5.2 (P5.2) of the v3 Execution Manual targets a relay-class
IED in the loop with the proposed HIF locator running on a
substation-side digital-twin emission consumer.  The IED model
is one of:

* SEL-487E (line-current-differential / distance / under-frequency
  composite IED, GOOSE / SV-9-2 capable);
* ABB REF615 (feeder-protection IED, IEC 61850-9-2LE SV
  subscriber + GOOSE publisher);
* Siemens 7SJ85 (over-current + earth-fault numerical IED, IEC
  61850-9-2LE + IEC 61850-8-1).

The actual IED chosen depends on which one is available at the
testbed where Phase-5 K09 is run (see WP5.1 access matrix; the
three redundant paths all carry one or more of these models in
varying configurations).

## 2. Per-vendor capability profile (target characteristics)

| Vendor | Model | SV subscriber (9-2LE 4.8 kHz) | GOOSE publisher (8-1) | GOOSE subscriber | Supported sample rate | Firmware reference |
|---|---|---|---|---|---|---|
| SEL | SEL-487E | YES (via SEL-2240 Merging Unit pair) | YES | YES | 4.8 kHz default; 14.4 kHz optional | Latest available; verify at HIL site |
| ABB | REF615 | YES (native subscriber) | YES | YES | 4.8 kHz, 12.8 kHz | Latest available; verify at HIL site |
| Siemens | 7SJ85 | YES (8-1 + 9-2LE) | YES | YES | 4.8 kHz | Latest available; verify at HIL site |

All three carry the IEC 61850 edition-2.1 capability profile
(LN definitions, MMS reporting, GOOSE retransmission scheme)
that the SAMBPS DTaaS substation-side emission framework expects.

## 3. Selection criteria

The IED model for the K09 acceptance run will be chosen at HIL-
site visit time per the following ordered criteria:

1. **Available on site** during the visit window (necessary
   condition).
2. **GOOSE round-trip demonstrated** in IED's recent firmware
   release notes (preferred over freshly-released firmware).
3. **SV subscriber jitter envelope** ≤ 50 µs published by the
   vendor (the SV → optimiser → GOOSE chain budget).
4. **Open documentation** of the LN class structure for the
   custom GOOSE message used for the (alpha, R_x) emission
   (we publish a custom message; the IED needs to subscribe).

## 4. Custom GOOSE message — `SAMBPS_HIF_LOCATION_EMISSION`

The proposed locator publishes a single GOOSE message back to the
IED with the (alpha, R_x) point estimate:

| Field | Type | Length | Notes |
|---|---|---|---|
| `header.gocbRef` | VisString | up to 65 char | `SAMBPS_HIF_LOC_PROT/SAMBPS$GO$LOC_EST` |
| `header.appId` | uint16 | 2 bytes | `0x4000` (custom IED-direction) |
| `dataset.alpha_pu` | Float32 | 4 bytes | per-unit fault location, [0, 1] |
| `dataset.Rx_ohm` | Float32 | 4 bytes | arc resistance in ohm |
| `dataset.timestamp_utc` | UTCTime | 8 bytes | UTC time of estimate |
| `dataset.confidence` | Float32 | 4 bytes | normalised optimiser confidence |
| `dataset.fault_type` | Enumerated | 1 byte | SLG / LL / LLG / NONE |
| `dataset.estimator` | VisString | up to 16 char | `dft` or `tft_K1` (which estimator emitted this) |

GOOSE retransmission: standard IEC 61850-8-1 retransmission
scheme: 4 ms initial, 8 / 16 / 32 / 64 ms back-off, then 1 s
heartbeat.  The IED must accept the custom dataset (a one-time
SCD/CID file change at the IED's commissioning step).

## 5. Open items requiring PI / HIL-site sign-off

1. **Confirm IED model on site** (Section 1).
2. **Confirm IED firmware version** (Section 2 placeholder rows).
3. **Confirm IED's SV subscriber jitter envelope** (Section 3).
4. **Confirm IED's SCD/CID file is editable** to accept the
   custom GOOSE dataset (Section 4).
5. **Confirm Merging Unit type** at the HIL testbed (RTDS
   GTNETx2-SV vs Typhoon HIL native vs vendor-specific MU).
