# PSCAD case `IEEE_34.pscx` — design document (WP3.3)

This document describes the IEEE 34-node test feeder PSCAD case
(canonical 24.9 kV overhead feeder with 32 branches, 2 voltage
regulators, 2 capacitor banks, and several single-phase laterals).

PSCAD is not on the dev box; the canonical `pscad/IEEE_34.pscx` is
authored on the lead engineer's licensed Windows station per
[`pscad/README_manual_run.md`](README_manual_run.md) (extended for
IEEE feeder topologies).

The dev-box surrogate that produces [`data/ieee34_720.mat`](../data/ieee34_720.mat)
is [`tools/ieee_feeder_surrogate.py`](../tools/ieee_feeder_surrogate.py),
with the WP3.3 simplifications documented in
[`docs/ieee_feeders_assumptions.md`](../docs/ieee_feeders_assumptions.md):
single line code 601 (instead of canonical 300/301/302/303/304),
chained topology (instead of canonical tree with 32 branches),
constant-Z scaled-down loads, no regulators, no capacitor banks.

The surrogate bundle is produced for downstream code-path development
against the canonical schema. Per-bus voltage validation against
Kersting Ch. 5 Tab. 5.10 is **deferred** to the WP3.3 follow-up
commit (per
[`docs/ieee_feeders_assumptions.md`](../docs/ieee_feeders_assumptions.md)).

## Canonical IEEE 34 features (deferred to WP3.3 follow-up)

* 34 buses; 32 branches with line codes 300–304 (24.9 kV overhead).
* Voltage regulators at buses 814 and 850.
* Capacitor banks at buses 844 and 848.
* Several single-phase and two-phase laterals.

## Output bundle schema — `data/ieee34_720.mat`

Same shape conventions as `data/ieee13_720.mat` ([`pscad/IEEE_13_design.md`](IEEE_13_design.md))
with `n_fault_buses = 33` and `n_cells = 33 · 5 · 4 · 4 = 2640`.
