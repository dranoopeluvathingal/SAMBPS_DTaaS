# SAMBP Digital Twin Lab — v0.1

Real-time parallel-path Digital Twin (DT) for the SAMBP protection scheme.
Validates relay decisions post-event, accumulates flag statistics, and
triggers model-update notifications — without touching the relay chain latency.

Supersedes the standalone scripts in `sambp/system/`:
- `run_digital_twin_study.py` (TR-43)
- `run_dt_estimation_study.py` (TR-44)
- `run_dt_validation_study.py` (TR-45)

---

## Architecture

```
Fault event
    │
    ├── Relay path (physical)
    │     └─ ProtectionMirror.predict(k_relay, α_relay)  ← noisy measurement
    │              ↓
    │         relay decision (element, action)
    │
    └── DT path (parallel, non-blocking, 1 kHz)
          ├─ PhasorDFT           ← one-cycle DFT, Fortescue sequence phasors
          ├─ EKFPhasorEstimator  ← 4-state EKF on phasor observations
          ├─ ScenarioLibrary     ← nearest-neighbour scenario lookup
          └─ ProtectionMirror.predict(k_ekf, α_ekf)  ← EKF-smoothed estimate
                   ↓
             DecisionComparator  ← 5-class verdict
                   ↓
             FlagEngine          ← accumulate, rate-check, trigger callback
```

**Single source of truth**: both relay and DT paths call the same
`ProtectionMirror.predict()`. No duplicate protection logic.

---

## Package layout

| Path | Purpose |
|---|---|
| `__init__.py` | `DTEngine` top-level class |
| `models/state_space_model.py` | `IBRStateSpaceModel` — state vector, h(x), Jacobian |
| `models/scenario_library.py` | Pre-computed fault scenario NN lookup |
| `models/protection_mirror.py` | Relay logic mirror + `TRIP_FAMILIES` taxonomy |
| `estimation/rls_estimator.py` | Scalar RLS for k_ibr (fast, backup) |
| `estimation/ekf_estimator.py` | 4-state EKF, instantaneous sequence approx |
| `estimation/phasor_dft.py` | One-cycle DFT phasor extractor (Fortescue) |
| `estimation/ekf_phasor_estimator.py` | 4-state EKF on DFT phasor observations |
| `validation/decision_comparator.py` | 5-class verdict (AGREE/FP/FN/ELEMENT/CONF) |
| `validation/flag_engine.py` | Flag accumulation + model-update trigger |
| `integration/relay_interface.py` | Adapters: wrap_87L/87T/87B/OC, GOOSE inject |
| `run_dt_lab.py` | Unified study runner (Studies A–G) |

---

## Public API

```python
from sambp.digital_twin import DTEngine
engine = DTEngine(dt_rate_hz=1000, estimator='ekf_phasor')
state  = engine.update(t, v_abc, i_abc)   # 1 kHz loop
result = engine.validate(relay_event)      # post-event
summary = engine.flag_summary

# Components used directly
from sambp.digital_twin.estimation.phasor_dft import PhasorDFT
dft = PhasorDFT(fs=1000, f0=50)
dft.push(v_abc, i_abc)           # one sample per call
if dft.ready:
    p = dft.extract()            # I_pos_mag, I_neg_mag, V_pos_mag, phasors, sequences

from sambp.digital_twin.estimation.ekf_phasor_estimator import EKFPhasorEstimator
ekf = EKFPhasorEstimator(fs=1000, f0=50)
ekf.reset()                      # call at start of each fault event
state = ekf.update(t, v_abc, i_abc)   # k_ibr, z_line, alpha, f_gfm, kappa_n, residual
```

### Verdict taxonomy (DecisionComparator)

| Verdict | Meaning |
|---|---|
| `AGREE` | Relay and DT match in outcome (exact or same protection family) |
| `FLAG_FP` | Relay tripped; DT predicted BLOCK; k_ibr far from thresholds |
| `FLAG_FN` | Relay blocked; DT predicted TRIP; k_ibr far from thresholds |
| `FLAG_ELEMENT` | Both tripped but from different protection families |
| `FLAG_CONF` | Direction mismatch but k_ibr within ±8% of a pickup threshold |

Same-family trips (Z1/87L ↔ 87L) → `AGREE` + `selectivity_note` (speed difference only, not outcome).

---

## Running the Studies

```bash
# from 04_code/
python -m sambp.digital_twin.run_dt_lab              # all studies
python -m sambp.digital_twin.run_dt_lab --study E    # single study
python -m sambp.digital_twin.run_dt_lab --study E --n-mc 2000
python -m sambp.digital_twin.run_dt_lab --study G --n-mc 500
```

No dependencies beyond `numpy`. Requires Python ≥ 3.8.

---

## Studies A–G Results (v0.1 baseline)

| Study | Topic | Key result |
|---|---|---|
| A | DT update rate vs relay speed | 1000 Hz → 20 samples before Z1/87L trip ✓ |
| B | RLS k_ibr convergence | <5% error at 20 updates (20 ms), λ=0.98 |
| C | EKF multi-parameter accuracy | k_ibr RMSE 7.1% at 20 cycles; α RMSE 0.36 |
| D | EKF drift tracking | λ=0.98 tracks slow fleet dispatch; adaptive λ deferred |
| E | DT-relay validation (N=2000) | **95.77% AGREE**; FP 0.11%, FN 0.21% |
| F | End-to-end latency | 52 ms total; DT adds 0 ms (non-blocking) |
| G | EKFEstimator vs EKFPhasorEstimator (N=500) | k_ibr RMSE 28.5× lower (phasor); AGREE 98.52% vs 94.07% |

Study E uses the instantaneous EKFEstimator with 20-cycle pre-convergence.
Study G uses sinusoidal waveforms to exercise the DFT extractor.

---

## Versioning

**v0.1** (April 2026) — initial release.

Changes from TR-43/44/45 standalone scripts:
- Single `ProtectionMirror.predict()` call for both relay and DT paths
- 5-class verdict taxonomy (adds `FLAG_CONF`; same-family → `AGREE`)
- ±8% threshold deadband → `FLAG_CONF` (not FP/FN)
- 20-cycle EKF pre-convergence window before relay fires
- Phasor DFT extractor with exact Fortescue sequence decomposition

**Known limitation (v0.2 target):** alpha RMSE only 1.18× better with phasor DFT —
scalar `Z_app = |V1|/|I1|` discards the impedance angle (alpha–Z_line degeneracy).
Fix: complex `V1/I1 ∈ ℂ` model in EKFPhasorEstimator (tracked: `TR-45-v0.2-a`).

---

## Citation

If you use this package in a publication, please cite the thesis chapter that
incorporates TR-43–45 and note that results were generated with:

```
SAMBP Digital Twin Lab v0.1
sambp/digital_twin/, tag sambp-dt-lab-v0.1
```

Supersedes: `sambp/system/run_digital_twin_study.py` (TR-43),
`run_dt_estimation_study.py` (TR-44), `run_dt_validation_study.py` (TR-45).
