# EMTP-RV case — manual GUI build + run instructions

EMTP-RV is a proprietary Windows simulator from Powersys / EMTP
Alliance and the `.ecf` project file is binary; the GUI is the
canonical authoring tool. Until the second engineer (E2) has run the
build below on a licensed Windows EMTP-RV station, the canonical
waveforms in `data/emtp_720.mat` come from
`tools/emtp_surrogate.py` (a Python 50-section pi-model state-space
reference — **independent numerical pathway** from the PSCAD
surrogate).

This README documents (a) the GUI build and (b) the 720-case run.
Refer to `emtp/HIFL_11kV_100km_design.md` for the schematic-level
description and `pscad/HIFL_11kV_100km_design.md` for the parallel
PSCAD case.

> **R1 mitigation.** Build this case on a different machine and by a
> different engineer than the one who built the PSCAD case so that
> human modelling habits do not cross-contaminate the cross-simulator
> validation. If the E2 role is unstaffed, document the cross-engineer
> separation as a known caveat in the WP1.4 milestone document.

---

## Prerequisites

- EMTP-RV ≥ v4.5 with the FD line and Diode_pq macros enabled.
- ScopeView for batch waveform export.
- Python 3.10+ for the automation script `emtp/run_emtp_720.py`
  (uses subprocess to drive the EMTP-RV CLI).

---

## A. Build the canonical case `HIFL_11kV_100km.ecf`

Follow `emtp/HIFL_11kV_100km_design.md` for the topology and
parameter values. In EMTP-RV:

1. **New project.** File → New → Project → name `HIFL_11kV_100km`,
   target `emtp/HIFL_11kV_100km.ecf`.

2. **Solution settings.** Simulation Options:
   - $\Delta t = 50\,\mu$s
   - Duration = 0.16 s (8 cycles at 50 Hz)
   - Output rate = $\Delta t$

3. **Source bus.** Insert single-phase voltage source from the
   Sources palette:
   - Magnitude (peak) = `11000*sqrt(2)/sqrt(3)` V
   - Frequency = 50 Hz
   - Phase = 0 deg

4. **Section-1 line.** Insert `FD line model`:
   - Length parameter: `alpha * 100` km bound to multiple-run.
   - $R'=0.0728$ Ω/km, $L'=0.927$ mH/km, $C'=11.6$ nF/km, $G'=0$.
   - Marti option, fitting band 10 Hz – 100 kHz, 20 poles.

5. **Section-2 line.** As above, length `(1 - alpha) * 100` km.

6. **Fault bus.** Wire the two FD-line outputs to a common bus.

7. **HIF arc element.** Insert `Diode_pq` macro shunt-connected to
   ground at the fault bus, with the parameters listed in
   `HIFL_11kV_100km_design.md`. Insertion control: a `TACS_Switch`
   driven by the comparator `t > 0.10 s`.

8. **CT and PT measurement.** `V_meter` at source bus (channel
   `V_in`); `I_meter` in series with source-bus tie (channel `I_in`).

9. **Multiple-run sweep.** Tools → Design Tool → add four parameters:
   - `alpha`     ∈ {0.05, 0.15, …, 0.95}  (10 values)
   - `Rx`        ∈ {100, 500, 1000, 2000, 5000} (5 values)
   - `snrV_dB`   ∈ {20, 30, 40, 999}     (999 = noiseless)
   - `snrI_dB`   ∈ {20, 30, 40, 999}
   - Total: 800 cells.

10. **Noise channels.** `Noise_Gauss` macros on V_in and I_in,
    amplitudes derived from `snrV_dB`/`snrI_dB` per the same formula
    as the PSCAD case. Independent rng seeds keyed off cell index.

11. **Output channels.** ScopeView export macros for `V_in_chan` and
    `I_in_chan`, decimated to 10 kHz, captured window = cycle 6 of 8.

12. **Save.** File → Save Project.

---

## B. Run the 720-case sweep

The EMTP-RV multiple-run produces 800 cells; the canonical
`data/emtp_720.mat` keeps the 9 alpha values
{0.10, 0.20, …, 0.90} per the same sub-sampling rule as the PSCAD
case.

### B.1 Automation (preferred)

```powershell
cd 04_code\sambp\fault_location_id
python emtp\run_emtp_720.py --case emtp\HIFL_11kV_100km.ecf \
                            --out  data\emtp_720.mat
```

`run_emtp_720.py` invokes the EMTP-RV CLI in batch mode, gathers the
ScopeView output, sub-samples to 720, and writes the canonical
`.mat` schema (mirror of PSCAD).

### B.2 GUI fallback

1. Open `HIFL_11kV_100km.ecf` in EMTP-RV.
2. Run → Multiple-Run → Start (800 simulations).
3. After completion, ScopeView writes per-cell `.scv` files. Use
   `python emtp/run_emtp_720.py --scv-postprocess` to gather and
   stitch into `data/emtp_720.mat`.

---

## C. Verification

```bash
cd 04_code/sambp/fault_location_id
.venv/bin/pytest -q tests/test_pscad_export_shape.py    # schema for both .mats
.venv/bin/python tools/compare_pscad_emtp.py            # cross-comparator
.venv/bin/pytest -q tests/test_pscad_emtp_consistency.py
```

Pass criterion: median per-cell RMS diff < 1 %, 95th percentile < 3 %.
On failure, do not auto-fix — escalate per R1 to Prof. Christian
Rehtanz (TU Dortmund EMT cross-validation reviewer) for an
independent EMTP review.
