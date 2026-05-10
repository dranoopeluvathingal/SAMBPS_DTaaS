# PSCAD case `IEEE_123.pscx` — design document (WP3.3)

This document describes the IEEE 123-node test feeder PSCAD case
(canonical 4.16 kV overhead feeder with 113 branches, 4 voltage
regulators, 4 capacitor banks, mixed PQ + Z + I loads at most buses,
and several single-phase + two-phase laterals).

PSCAD is not on the dev box; the canonical `pscad/IEEE_123.pscx` is
authored on the lead engineer's licensed Windows station per
[`pscad/README_manual_run.md`](README_manual_run.md) (extended for
IEEE feeder topologies).

The dev-box surrogate that produces [`data/ieee123_720.mat`](../data/ieee123_720.mat)
is [`tools/ieee_feeder_surrogate.py`](../tools/ieee_feeder_surrogate.py),
with the WP3.3 simplifications documented in
[`docs/ieee_feeders_assumptions.md`](../docs/ieee_feeders_assumptions.md):
single line code 601, chained topology (instead of canonical tree),
constant-Z scaled-down loads, no regulators, no capacitor banks.

The surrogate bundle is produced for downstream code-path development
against the canonical schema. Per-bus voltage validation against
Kersting Ch. 6 Tab. 6.10 is **deferred** to the WP3.3 follow-up
commit (per
[`docs/ieee_feeders_assumptions.md`](../docs/ieee_feeders_assumptions.md)).

## Canonical IEEE 123 features (deferred to WP3.3 follow-up)

* 123 buses; 113 branches with 4 line codes.
* Voltage regulators at buses 150r, 9r, 25r, 160r.
* Capacitor banks at buses 83, 88, 90, 92.
* Mixed PQ + Z + I loads with voltage-dependent behaviour.

## Output bundle schema — `data/ieee123_720.mat`

Same shape conventions as `data/ieee13_720.mat` ([`pscad/IEEE_13_design.md`](IEEE_13_design.md))
with `n_fault_buses = 122` and `n_cells = 122 · 5 · 4 · 4 = 9760`.
