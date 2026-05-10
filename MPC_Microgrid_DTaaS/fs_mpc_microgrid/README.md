# fs_mpc_microgrid

Reproduction and extension of Perez & Flores-Bahamonde (2016), *FS-Model Predictive Control of Microgrid Interface Converters for Reactive Power and Harmonic Compensation*, IEEE PEDG, pp. 1206–1211.

This is **Phase 1** of the larger MAS-DT-SH thesis programme (see `~/Desktop/FS_MPC_Centralized_MG_DT_Implementation_Plan.pdf`). The current scaffold implements the single-converter inner FS-MPC loop, the energy-domain DC-link PI, an ideal PLL and a parameterised RL + harmonic load, sufficient to reproduce the qualitative behaviour of the focal paper's Fig. 4 (loading mode with non-linear load).

## Quick start

```bash
cd fs_mpc_microgrid
python -m venv .venv && source .venv/bin/activate    # Linux/Mac
# .venv\Scripts\activate on Windows
pip install -e .[dev]

# run the unit tests
pytest -q

# reproduce a basic loading-mode run and save the figure
python scripts/run_loading_mode.py
# -> figures/loading_mode.png
```

## Repository layout

```
fs_mpc_microgrid/
├── README.md
├── pyproject.toml
├── .gitignore
├── src/fs_mpc_mg/
│   ├── __init__.py
│   ├── plant.py             # 3φ VSI + L-filter + DC-link continuous-time model (Eq. 1, 2)
│   ├── load_model.py        # Linear RL load + harmonic current injector
│   ├── pll.py               # Ideal PLL (with TODO stub for SOGI-PLL)
│   ├── inner_fsmpc.py       # 8-vector FS-MPC current controller (Eq. 4)
│   ├── outer_energy_pi.py   # Energy-domain PI on E_c = ½ C v_dc^2  (Eq. 11)
│   ├── simulator.py         # Fixed-step EMT loop, RK4 sub-step, ZOH switching at T_s
│   └── scenarios.py         # Loading / Regenerating / STATCOM presets
├── tests/
│   ├── test_plant.py        # natural decay with s=000 → i_m → 0
│   ├── test_inner_fsmpc.py  # current step tracks ref in 1–2 samples
│   └── test_outer_pi.py     # v_dc settles to ref under no load
├── scripts/
│   └── run_loading_mode.py  # End-to-end first-light reproduction of Fig. 4
└── figures/                 # Auto-generated outputs land here
```

## Status

| Module | Status | Maps to deliverable |
|---|---|---|
| `plant.py` | Implemented (R, L, C model, M-matrix, RK4) | D02 |
| `load_model.py` | Implemented (linear RL + harmonic injector — proxy for 6-pulse) | D03 |
| `pll.py` | Ideal PLL working; SOGI-PLL stub | D04 (partial) |
| `inner_fsmpc.py` | 8-vector predictor + cost min, 1-step horizon | D05 |
| `outer_energy_pi.py` | PI on `E_c`; tunable | D06 |
| `simulator.py` | Working end-to-end, fixed-step | (glue) |
| `scripts/run_loading_mode.py` | Produces Fig. 4 analogue | D07 (partial) |

Open items: full 6-pulse rectifier with iterative diode commutation; SOGI-PLL; delay-compensation predictor; THD instrumentation; ICA agent wrapper. See `IMPLEMENTATION_PLAN.md` excerpts in this README's parent directory.

## Reference

[F] M. A. Perez and F. Flores-Bahamonde, "FS-Model Predictive Control of Microgrid Interface Converters for Reactive Power and Harmonic Compensation," in *Proc. IEEE PEDG*, 2016, pp. 1206–1211.

## Docker deployment

The full stack (Mosquitto broker + 4 ICAs + CMC + DT) ships with a docker-compose
file in `docker/`:

```bash
cd fs_mpc_microgrid
docker compose -f docker/docker-compose.yml up --build
```

Each service is a Python process that talks to the broker via `MQTTPubSub`
(see `src/fs_mpc_mg/comm/mqtt_pubsub.py`). The entrypoints live under
`src/fs_mpc_mg/entrypoints/` and accept `--broker`, `--id`, etc. arguments
so you can replicate the stack on multiple hosts.

## What's new since v0.3.0

- **`RectifierLoad`** — topology-faithful 6-pulse diode rectifier with
  120°-conduction AC currents and an inductive DC link (smoothing time
  constant configurable). Replaces the parametric harmonic injector for
  studies that need the right phase relationships between fundamental and
  harmonics.
- **`PhaseLockedRLS`** — cycle-decimated wrapper around `RLSIdentifier`.
  Suppresses high-bandwidth switching ripple by committing exactly one
  RLS update per fundamental cycle.
- **Docker stack** in `docker/` — Mosquitto broker + dockerised entrypoints.
- **`scripts/run_dashboard_demo.py`** — generates a self-contained
  `figures/dashboard.html` from any simulation run.
