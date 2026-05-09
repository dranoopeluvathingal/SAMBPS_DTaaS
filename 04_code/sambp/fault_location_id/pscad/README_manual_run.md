# PSCAD case — manual GUI build + run instructions

The `.pscx` file is a binary PSCAD project that is normally produced
from the GUI. Until the lead engineer has run the build below on a
licensed Windows PSCAD station, the canonical waveforms in
`data/pscad_720.mat` come from `tools/pscad_surrogate.py` (a Python
distributed-parameter ABCD-cascading reference). The two are
expected to agree to within a few percent at $f_0 = 50$ Hz; the WP1.4
cross-platform delta-error report is the formal comparator.

This README documents (a) the GUI build of the canonical case, and
(b) the 720-case run. Refer to `pscad/HIFL_11kV_100km_design.md` for
the schematic-level description.

---

## Prerequisites

- PSCAD ≥ X4 v5 with EMTDC engine.
- Master library + CSMF (Continuous System Model Functions) library.
- Python 3.10+ on the same machine if you intend to run the
  automation script `pscad/run_pscad_720.py` (uses `mhi.pscad`).

---

## A. Build the canonical case `HIFL_11kV_100km.pscx`

Reference: `pscad/HIFL_11kV_100km_design.md` for the topology and
parameter values. Reproduce in PSCAD as follows.

1. **New project.** File → New Project → name `HIFL_11kV_100km`,
   target `pscad/HIFL_11kV_100km.pscx`.

2. **Solution settings.**
   - Time step `Δt = 50 µs` (Nyquist for 10 kHz capture).
   - Output rate = `Δt` (capture every step).
   - Duration = `0.16 s` (8 cycles at 50 Hz).
   - Snapshot file → save at `t = 0.10 s` (5 cycles, post-settle).

3. **Source bus.** Place a single-phase voltage source from `Sources`:
   - Magnitude (peak) = `11000*sqrt(2)/sqrt(3)` V
   - Frequency = `50` Hz
   - Phase = `0` deg

4. **Frequency-dependent line, section 1.** Insert two
   `Frequency-Dependent (Phase) Model` blocks (one per side of fault):
   - Model: `J. Marti`
   - Length parameter: `alpha * 100` km — bind `alpha` to the
     PSCAD multiple-run parameter (step 9).
   - Per-km values: $R'=0.0728$ Ω/km, $L'=0.927$ mH/km,
     $C'=11.6$ nF/km, $G'=0$.
   - Fitting band: 10 Hz – 100 kHz (default).
   - Number of fitting poles: 20 (default).

5. **Frequency-dependent line, section 2.** As above, length
   `(1 - alpha) * 100` km.

6. **Fault bus.** Wire the two line sections together at the fault
   bus.

7. **HIF arc element.** Place the anti-parallel diode model
   (`Diodes` library) shunt-connected to ground at the fault bus:
   - $V_{kp} = 50$ V, $V_{kn} = 45$ V, $R_{sp} = 5$ Ω,
     $R_{sn} = 6$ Ω, $R_{\text{off}} = 1\times 10^6$ Ω,
     $\varepsilon = 1\times 10^{-3}$ A.
   - Arc-insertion control: a `Single-Pole Switch` driven by the
     compare block `t > 0.10 s` (insert at 5-cycle mark).

8. **CT and PT measurements at the source bus.**
   - PT: `Voltage Source Probe` → name `V_in`.
   - CT: `Ammeter` (CT block) → name `I_in`.
   - Both → `Multimeter` → `Output channel` for PSCAD batch export.
   - Sampling: rely on PSCAD's per-step capture at `Δt = 50 µs`,
     then post-process to 10 kHz / 200 samples / one cycle in step 11.

9. **Multiple-Run parameters.** Project Settings → Parametric →
   add four parameters:
   - `alpha`     ∈ {0.05, 0.15, 0.25, …, 0.95}  (10 values)
   - `Rx`        ∈ {100, 500, 1000, 2000, 5000} (5 values)
   - `snrV_dB`   ∈ {20, 30, 40, 999}            (999 = noiseless flag)
   - `snrI_dB`   ∈ {20, 30, 40, 999}
   - Total cells in the GUI sweep: 10 × 5 × 4 × 4 = **800**.

10. **Noise channels.** Insert two
    `Random Number Generator` (Gaussian) blocks from CSMF:
    - `noise_V`: amplitude = `V0 / 10^(snrV_dB/20)` (PSCAD `if snrV_dB == 999 then 0`)
    - `noise_I`: amplitude = `I_rated / 10^(snrI_dB/20)`
    - Add to V_in and I_in respectively before the output channel.

11. **Output channels.** Two output channels per run:
    - `V_in_chan` ← `V_in + noise_V`, decimated to 10 kHz
    - `I_in_chan` ← `I_in + noise_I`, decimated to 10 kHz
    - Captured window: cycle 6 of 8 (i.e. `t ∈ [0.12, 0.14]` s),
      200 samples per channel.

12. **Save.** File → Save Project → confirm
    `pscad/HIFL_11kV_100km.pscx` exists alongside this README.

---

## B. Run the 720-case sweep

The PSCAD GUI sweep produces 800 cells; the canonical
`data/pscad_720.mat` keeps the 720 cells defined by the v3 plan
headline (drop α = 0.05 and α = 0.15 from each (Rx, snrV, snrI)
combination, retaining α ∈ {0.10, 0.20, …, 0.90} → 9 values × 5 × 4
× 4 = 720 cells). Two run modes:

### B.1 Automation (preferred)

```powershell
# In an Anaconda / Python shell on the PSCAD station
cd 04_code\sambp\fault_location_id
python -m pip install mhi.pscad   # Manitoba HVDC Python automation
python pscad\run_pscad_720.py --case pscad\HIFL_11kV_100km.pscx \
                              --out  data\pscad_720.mat
```

`run_pscad_720.py` invokes the multiple-run sweep, gathers the
PSCAD output channels, sub-samples to 720, and writes the MATLAB
v7 file with the fixed schema documented in
`HIFL_11kV_100km_design.md` "Output bundle".

### B.2 GUI fallback (if `mhi.pscad` is unavailable)

1. Open `HIFL_11kV_100km.pscx` in PSCAD.
2. Run → Multiple-Run → Start (800 simulations; ~30–60 minutes
   depending on machine).
3. After completion, PSCAD writes
   `HIFL_11kV_100km.gnu` channel files per cell. Use the
   helper script `pscad/run_pscad_720.py --gnu-postprocess`
   to gather the .gnu files and emit `data/pscad_720.mat` with
   the canonical schema and 720-cell sub-sampling.

---

## C. Verification

After producing `data/pscad_720.mat`:

```bash
cd 04_code/sambp/fault_location_id
.venv/bin/pytest -q tests/test_pscad_export_shape.py
```

Pass criterion: each of `V` and `I` has shape `(720, 200)`, plus the
four `grid_*` arrays have shape `(720,)`, and `meta` is a dict with
the expected keys (see `HIFL_11kV_100km_design.md` "Output bundle").

The WP1.4 cross-platform script (next milestone) consumes
`data/pscad_720.mat` plus EMTP-RV and the 50-section MATLAB reference
to compute the per-cell delta-error vs the WP0.4 self-consistent
baseline.
