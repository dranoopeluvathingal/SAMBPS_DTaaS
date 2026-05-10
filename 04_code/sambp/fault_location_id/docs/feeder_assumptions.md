# Feeder modelling assumptions — branched 3-phase network (WP3.2)

This document records the parameter defaults used by the `Network`
class in [`models/faultloc_three_phase_model.py`](../models/faultloc_three_phase_model.py)
and their provenance.  Defaults can be overridden through the
constructor; the values below are what the WP3.2 surrogate uses to
produce [`data/pscad_branched_720.mat`](../data/pscad_branched_720.mat),
and what the WP3.2 acceptance test in
[`tests/test_branched_vs_pscad.py`](../tests/test_branched_vs_pscad.py)
asserts against the closed-form Network reduction.

The PI pre-empted the **DG placement and rating** open question in
the WP3.2 brief by setting the default to "1 MVA / 0.95 pf at the
lateral mid-point unless directed otherwise"; the rest of the
parameters below are author-chosen with explicit citations.

## Network topology

```
                tap (at tau * L_main from sender)
                  |
   sender ---X---+---X--- open far-end           (main feeder, L_main = 100 km)
                  |
                  | lateral (L_lat = 20 km)
                  |
                  +--- DG (at dg_pos * L_lat from tap)
                  |
                  +--- tap_load (at lateral end)
```

`X` = candidate fault locations (parameter `fault_branch in {main, lateral}`,
position `alpha` per-unit on the chosen branch from sender or tap
respectively).

## Default parameter values

| Parameter | Default | Source / rationale |
|---|---|---|
| `main_length_km` | **100** | Same as WP3.1 single-radial / WP1.1 single-phase canonical case. |
| `tap_position` | **0.5** (per-unit) | Lateral taps off the mid-feeder, the worst case for upstream / downstream fault discrimination on a radial 11 kV feeder. |
| `lateral_length_km` | **20** | Typical 11 kV sub-feeder length serving a small rural / peri-urban load cluster (Saha 2010 Springer Ch. 3 cites 5–25 km as the operating range). |
| `dg_position` | **0.5** (per-unit on lateral) | Per the WP3.2 brief: "1 MVA / 0.95 pf at the lateral mid-point unless directed otherwise". |
| DG rating | **1 MVA, 0.95 pf inductive** | Per the WP3.2 brief default. Representative of a small renewable / standby generator on an 11 kV distribution lateral. |
| DG sub-transient reactance X″<sub>d</sub> | **0.20 pu** on the (1 MVA, 11 kV) base | IEEE C50.13 / IEEE Std 421.5 typical value for synchronous machines at this size. |
| DG internal resistance R | **0.05 pu** on the same base | Typical machine winding losses; conservative for a small rotating machine. |
| `dg_internal_impedance_ohm` | **2 + j 8 Ω/phase** | Computed as `(R_pu + j X_pu) * Z_base` where `Z_base = V_LL² / S_3ph / 3 = (11e3)² / (3 · 1e6) = 40.33 Ω`. So `Z_dg ≈ 0.05 · 40.33 + j · 0.20 · 40.33 ≈ 2.0 + j 8.07`, rounded. |
| Tap-load rating | **1 MW + j 0.5 Mvar** (~ 0.9 pf inductive) | Representative residential / commercial cluster. Slightly oversized vs the DG so the lateral net injection at f₀ is modestly load-dominant in the no-fault baseline. |
| `tap_load_impedance_ohm` | **32 + j 16 Ω/phase** | Computed as `Z_load = V_phase² / S_load* = (11e3 / sqrt(3))² / (1.0 MVA · (0.9 - j 0.4359))*`, simplifies to `≈ 32.7 + j 15.8`, rounded to 32 + j 16. Constant-impedance representation; constant-power and ZIP loads land at WP3.4 once the fault-type axis (LL / LLG) is wired in. |
| `R_load_open_ohm` | **1 MΩ** | Open far-end shunt; matches the WP2.1 / WP3.1 single-phase / radial baseline. |

All per-unit-length 3-phase Z′<sub>abc</sub> and Y′<sub>abc</sub>
values are inherited from
[`models/faultloc_three_phase_model.py`](../models/faultloc_three_phase_model.py)
preamble (Saha 2010 Springer Tab. 3.1 diagonals; Kersting 2002 Tab.
4.1 mutual ratios). See WP3.1 design doc
[`pscad/HIFL_11kV_100km_3ph_design.md`](../pscad/HIFL_11kV_100km_3ph_design.md)
for the per-unit-length parameter table.

## Constant-impedance load assumption

The tap load is modelled as a **constant impedance Z_load to ground**
on each phase (no constant-power or ZIP behaviour). This is exact for
a passive linear load at f₀; it is also the classical small-signal
linearisation used by IEEE C37 fault-analysis tooling. The
implication for HIF identification is that the load contribution to
the sending-end admittance Y_send is itself an LTI block, so the only
non-LTI element on the network is the HIF arc (which the
WP1.1 anti-parallel diode model captures separately).

A constant-power load model would introduce a quasi-Newton iteration
on the load-flow side and an admittance perturbation that depends on
the bus voltage. For the WP3.2 surrogate-vs-closed-form numerical
check this would dominate the comparison residual (~1 % depending on
the operating point), masking the per-segment line-discretisation
error we are trying to certify. Constant-power / ZIP loads are
deferred to **WP3.4** once the fault-type axis is in place; the
constant-impedance assumption is documented as the WP3.2 → WP3.4
reframing.

## DG modelling assumption

The DG is a **Thévenin source `V_dg` behind a series impedance
`Z_dg`** at the lateral mid-point. For the small-signal Y_send
computation (the IED's identification target), the source itself is
an injection rather than an admittance and contributes nothing to the
linear admittance matrix at f₀; only `Z_dg` enters Y_send via the
`1 / Z_dg · I_3` shunt at the DG bus (added to the look-back
admittance during the network reduction).

When the lead engineer's licensed PSCAD station produces canonical
3-phase waveforms, the DG source amplitude and phase angle DO matter
for the time-domain V/I traces (and hence for the WP3.5 / WP3.6
multi-port FIM). At Y_send acceptance level (WP3.2), only the
internal impedance is observable at the substation IED; the source
amplitude / phase is therefore left at "ideal balanced 11 kV phase
voltage in phase with the substation source" and not parameterised
in the WP3.2 surrogate. This will be revisited at WP3.6.

## Coupling transformer

The DG is connected to the lateral via a **1:1 ideal coupling
transformer** for the WP3.2 acceptance check; the ratio and
transformer winding impedance lump into `Z_dg` in this commit. A
realistic 11 kV / 400 V Δ-Y or Y-Y transformer with a finite leakage
reactance and tap-changer is deferred to **WP3.3**, where the IEEE
13-node line-code 601 transformer XFM-1 is wired in along with the
rest of the IEEE feeder data.

## Open question history

The following item from the WP3.2 brief was answered by the PI prior
to this commit:

* **DG placement and rating**: 1 MVA / 0.95 pf at the lateral
  mid-point. (Locked in this document; defaults applied.)

Future opens (carried forward to WP3.3 / WP3.4 / WP3.6):

* What ratio + impedance for the DG coupling transformer? (WP3.3)
* Constant-impedance vs constant-power vs ZIP loads? (WP3.4)
* Multiple laterals (the WP3.2 surrogate has only one)? (WP3.3 IEEE 13)
* Phase-imbalanced loads (the WP3.2 surrogate is balanced)? (WP3.4)

## Phase-4 (WP4.1) impairment-class parameter defaults

The five impairment generators in
[`models/faultloc_noise_impairments.py`](../models/faultloc_noise_impairments.py)
extend the WP1.1 / WP1.4 dual-channel AWGN noise model with the
dominant non-Gaussian field-grade phenomena.  Default parameter
values + provenance below.

### (1) `add_impulsive` — Bernoulli–Gaussian impulsive noise

| Parameter | Default | Source |
|---|---|---|
| `prob` | **0.005** | Per-sample event probability; corresponds to ~1 impulse / cycle at 200 samples. Representative of partial-discharge / PLC background on overhead distribution feeders (PSRC D15 1996; Aucoin–Russell 1987). |
| `mag_db` | **20 dB** | Impulse standard deviation 10× the per-channel rms; matches the IEEE 1159-2019 power-quality "interruption / spike" envelope (transients ≥ 10× steady-state for sub-µs durations). |

### (2) `add_harmonic_background` — IEEE 519-2014 harmonics

| Order | Default per-unit amplitude | Source |
|---|---|---|
| 2nd | 0.02 | IEEE Std 519-2014 Tab. 2 (general distribution: TDD ≤ 5 %, individual harmonics ≤ 4 % at < 11 kV, ≤ 2 % for even orders). |
| 5th | 0.04 | Largest typical odd harmonic; non-linear loads and 6-pulse converters. |
| 7th | 0.03 | Same source family. |
| 11th | 0.02 | Higher-order harmonics; switched-mode loads. |

Phases are randomised independently per channel per the IEEE 519
assumption that harmonics from different sources are statistically
uncorrelated.

### (3) `add_ct_saturation` — IEEE C37.110-2007 CT model

| Parameter | Default | Source |
|---|---|---|
| `remanence_pu` | **0.3** | Fractional residual flux at t=0; sweep range {0, 0.3, 0.5, 0.8} per WP4.1 brief. IEEE C37.110-2007 §5.3.2 cites typical relay-class CTs: 30-50 % residual immediately after a heavy fault clearing. |
| `burden_ohm` | **2.0 Ω** | CT secondary burden; sweep range {1, 2, 4, 8} Ω per WP4.1 brief. 2 Ω is typical IED-relay nominal burden (IEEE C37.110-2007 §4.4). |
| `ct_class` | **`5P20`** | IEEE C37.110-2007 Tab. 5; 5 % composite error at 20× rated current, the protection-class workhorse. Other supported: `10P20`, `5P10`, `10P10`. |
| Saturation envelope | tanh-based with effective knee `I_knee_eff = (V_knee/burden) · (1 − remanence_pu)` | Smooth-saturation approximation; closed-form, differentiable, no DC-bias artefact. |

### (4) `add_off_nominal_frequency` — IEEE C37.118.1 P-class

| Parameter | Default | Source |
|---|---|---|
| `df_hz` | **0.5 Hz** | Off-nominal frequency drift (signed). IEEE C37.118.1-2018 §5.5 P-class compliance envelope ±2 Hz; 0.5 Hz is the typical mid-range test point. ±5 Hz hard cap enforced. |
| Implementation | DFT-based: extract f0 phasor, subtract clean fundamental, re-synthesise at f0 + df_hz, add back the residual | Preserves harmonics + transients while shifting the fundamental. |

### (5) `add_adc_quantisation` — uniform mid-tread

| Parameter | Default | Source |
|---|---|---|
| `bits` | **14** | Typical relay IED ADC resolution (e.g., GE Multilin, SEL relays); sweep {12, 14, 16}. |
| `vref_v` / `iref_a` | **caller-specified** | Voltage / current full-scale reference; runner sets these to 2 × per-channel rms (clean baseline) or 4 × for the composite case. Symmetric clip at ±vref / ±iref. |
| Quantiser type | mid-tread uniform | Standard IEC 61869-9 quantiser convention; round-to-nearest with a step of `2 · vref / 2^bits`. |

### Composite "field-grade" pipeline

`add_composite_field_grade` chains all five in the canonical order
**impulsive → harmonics → CT saturation → off-nominal → ADC**.
This ordering matches the physical signal-chain (impairments at the
primary side propagate through the CT, then the IED's anti-aliasing
filter and ADC); reversing the order would change the CT saturation
operating point because it would see harmonics + impulses already
distorted by the off-nominal-frequency shift.

## References

* IEEE Std 519-2014, *IEEE Recommended Practice and Requirements
  for Harmonic Control in Electric Power Systems*.
* IEEE Std C37.110-2007, *IEEE Guide for the Application of Current
  Transformers Used for Protective Relaying Purposes*.
* IEEE Std C37.118.1-2018, *IEEE Standard for Synchrophasor
  Measurements for Power Systems*.
* IEEE Std 1159-2019, *IEEE Recommended Practice for Monitoring
  Electric Power Quality* (impulsive transient envelope).
* PSRC Working Group D15, "Distribution line protection practices
  industry survey results", 1996 (HIF arc / partial-discharge
  impulsive-noise rates).
* Saha, M.M., Izykowski, J., Rosolowski, E. *Fault Location on Power
  Networks*. Springer, 2010, Ch. 3 (3-phase Bergeron and lateral
  modelling). Bib key `Saha2010BookFL`.
* Kersting, W.H. *Distribution System Modelling and Analysis*. 2nd
  ed., CRC Press, 2002. Tables 4.1 and 4.2 for IEEE 13 line codes.
* IEEE C50.13-2014, *Standard for Cylindrical-Rotor Synchronous
  Generators*, sub-transient reactance bounds.
* IEEE C37.110-2007, *IEEE Guide for the Application of Current
  Transformers Used for Protective Relaying Purposes*, fault-current
  representation conventions.
