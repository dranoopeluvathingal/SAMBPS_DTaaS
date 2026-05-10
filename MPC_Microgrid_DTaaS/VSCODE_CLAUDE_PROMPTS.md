# VS Code Claude — Curated Prompts for `MPC_Microgrid_DTaaS`

> Open VS Code at the project root
> `C:\Users\Anoop Eluvathingal\OneDrive\Desktop\SAMBPS -DTaaS ALL Files\SAMBPS DTaaS\SAMS\MPC_Microgrid_DTaaS`,
> open Claude in the side panel, and paste any prompt below as a self-contained task. Each prompt is written to be **stand-alone** so Claude doesn't need to remember earlier turns.

---

## A. Sanity check & first-light (run this first)

### A.1 — Verify the existing 57-test suite still passes locally
```
You are working in the project at C:\Users\Anoop Eluvathingal\OneDrive\Desktop\SAMBPS -DTaaS ALL Files\SAMBPS DTaaS\SAMS\MPC_Microgrid_DTaaS.

The Python codebase is in fs_mpc_microgrid/. It already builds and tests cleanly on Linux. Please:

1. Create a Python 3.11 venv inside fs_mpc_microgrid/ (use `py -3.11 -m venv .venv`).
2. Activate it (PowerShell: `.\.venv\Scripts\Activate.ps1`).
3. Install the package editable with dev + mqtt extras: `pip install -e .[dev,mqtt]`.
4. Run `pytest -q`. Report total tests and any failures.
5. If any tests fail with ModuleNotFoundError or import path issues on Windows,
   diagnose and fix without disabling the tests. Do not change any test logic.

Stop after pytest passes. Do not run the demo scripts yet.
```

### A.2 — Reproduce all six demo figures
```
The fs_mpc_microgrid/ codebase has 7 demo scripts in scripts/. Run all of them in
this order and check that each prints the expected metrics and saves a PNG into
figures/:

  python scripts\run_loading_mode.py        # expect THD i_s ≈ 4.3%
  python scripts\run_regenerating_mode.py   # expect THD i_s ≈ 2.7%
  python scripts\run_statcom_mode.py        # expect THD i_s < 6%
  python scripts\run_ica_agent_demo.py      # expect 'Final v_dc ≈ 882 V'
  python scripts\run_fleet_demo.py          # expect 'Final v_dc per ICA: ~880 V'
  python scripts\run_dt_demo.py             # expect 'Cyber alerts: 1'
  python scripts\run_dashboard_demo.py      # produces figures\dashboard.html

Open figures\dashboard.html in the default browser at the end. Report any deltas
from the expected values.
```

---

## B. Continue the algorithmic work

### B.1 — Implement the Class A.2 study (Energy-domain PI vs linear v_dc PI)
```
Per the simulation studies plan in docs/FS_MPC_Simulation_Studies_Plan.pdf
(Section 2, study A.2):

Implement a `LinearVdcPI` controller in src/fs_mpc_mg/outer_linear_pi.py that
controls v_dc directly with a small-signal-linearised PI (no energy-domain
trick). Match the closed-loop bandwidth to the existing EnergyPI by linearising
around v_dc_ref = 900 V.

Then write studies/A_baseline/study_A2_energy_vs_linear_pi.py that:
  - Runs the loading mode at i_dc = -80 A with both controllers
  - Logs v_dc(t), i_s(t), I_s_amp(t)
  - Plots a side-by-side comparison (4 panels: v_dc, i_s, error, gain set)
  - Computes overshoot, 1% settling time, RMS tracking error
  - Saves figures/study_A2_energy_vs_linear_pi.png and tables/study_A2.csv
  - Asserts via a unit test that EnergyPI's overshoot is ≤ 50% of linear's

Add tests/test_outer_linear_pi.py mirroring test_outer_pi.py's structure.
Confirm pytest still passes on the full suite.
```

### B.2 — Add the Class C.3 study (headroom-weighted H_mask validation)
```
Per the simulation studies plan §4 (study C.3): validate that the headroom-
weighted harmonic allocation in src/fs_mpc_mg/cmc/h_allocator.py reduces
saturation events on the most-loaded ICA compared to equal-share allocation.

Write studies/C_coordination/study_C3_h_allocation.py that:
  - Builds a 4-ICA fleet where ica1 is loaded to 90% S_max while
    ica2..4 are loaded to 30% S_max
  - Runs two scenarios: HAllocator vs an equal-share dummy
  - Records the number of saturation events on ica1 across 100 cycles
  - Plots i_m,a peaks per ICA and a saturation-event bar chart
  - Asserts the headroom policy reduces ica1 saturations by >= 40%

Output figures/study_C3_h_allocation.png and tables/study_C3.csv.
```

### B.3 — Run the digital-twin sensor-fault Monte-Carlo (study D.3)
```
Per studies plan §5 (D.3): generate the ROC curve for the AnomalyDetector by
injecting a sensor offset on a random ICA at a random time across 200 trials.

Write studies/D_faults/study_D3_sensor_fault_montecarlo.py that:
  - Uses a fixed RNG seed for reproducibility (np.random.default_rng(42))
  - Sweeps offset ∈ {5, 10, 25, 50, 100} V, n_sigma ∈ {3, 5, 7}
  - Runs 200 trials per (offset, n_sigma) combination
  - Records true-positive rate and false-positive rate
  - Plots an ROC curve per offset value
  - Saves figures/study_D3_dt_sensor_fault.png and tables/study_D3.csv

Use joblib.Parallel(n_jobs=-1) to parallelise. Expect ~30 minutes total on
a modern laptop.
```

---

## C. New microgrid topologies

### C.1 — Fill in the IEEE 33-bus topology with full line/load data
```
The file topologies/ieee_33_bus.py has bus definitions but the placeholder
load values may need refinement and there are no line impedances. Please:

  1. Add line-segment R+jX from the standard Baran-Wu 1989 table (search the
     project's references/ folder first; if not present, hard-code from any
     authoritative IEEE PES source).
  2. Extend fs_mpc_mg.cmc.Topology to support line edges with (R, X) — add a
     LineEdge dataclass alongside the existing SwitchEdge, store in
     Topology.lines, and add a method `lines_on_bus(bus_id)`.
  3. Update topologies/ieee_33_bus.py to populate all 32 lines.
  4. Add tests/test_ieee_33_bus.py verifying:
       - 33 buses + 1 grid bus = 34 total
       - 32 lines + 1 substation switch = 33 edges
       - All loads sum to ~3.7 MW (sanity check from literature)
  5. Confirm pytest still passes the whole suite.
```

### C.2 — Build the CIGRE MV residential topology end-to-end
```
Take topologies/cigre_mv_residential.py from stub to complete. Use the CIGRE
Task Force C6.04.02 benchmark data (see references/ for any matching PDF).

Required:
  - Correct line impedances per the CIGRE report
  - Two PV inverters at buses 3 and 6 (rated 200 kVA and 300 kVA)
  - One BESS at bus 10 (500 kVA)
  - One wind generator inverter at bus 11 (400 kVA)
  - Residential load profiles at buses 4, 7, 8, 9 with daily curves

Add a new HarmonicLoad subclass `DailyProfileLoad` in src/fs_mpc_mg/load_model.py
that accepts a 24-hour P(t)/Q(t) profile and returns instantaneous load.

Write a study script studies/A_baseline/study_A5_cigre_residential_24h.py that
runs a 24-hour QSTS using the topology and produces a load+generation curve.
```

---

## D. Cross-tool adapters (pick one your machine has)

### D.1 — Build the pandapower adapter (steady-state load flow)
```
Implement adapters/pandapower/topology_to_pp.py with:

    def topology_to_pandapower(topology: Topology) -> pandapowerNet:
        '''Convert a fs_mpc_mg Topology into a pandapower network.'''

Each BusNode -> pandapower bus, each LoadNode -> pandapower load,
each ICANode -> pandapower sgen with controllable=True, each switch -> pandapower
switch element. Add a tests/test_pandapower_adapter.py that:

  1. Builds the IEEE 33-bus topology
  2. Converts it to pandapower
  3. Runs `pp.runpp(net)` and asserts convergence
  4. Verifies bus voltage magnitudes are within 0.95-1.05 p.u.

If pandapower is not installed, install it with `pip install pandapower>=2.13`.
Update the project's pyproject.toml [project.optional-dependencies] with a
'powerflow' extra: `pandapower>=2.13`.

The adapter is non-trivial — carefully map our `s_max` to pandapower's
`max_p_mw`/`max_q_mvar`. Document the mapping in a top-level docstring.
```

### D.2 — Build the OpenModelica adapter (FMI-driven shadow plant)
```
Implement adapters/openmodelica_fmi/. The goal is to replace fs_mpc_mg.dt.
ShadowPlant with an Open Modelica EMT model exported as FMI 2.0 Co-Sim.

Steps:
  1. Install OMPython (`pip install OMPython`).
  2. Write a Modelica model `Plant3PhaseVSI.mo` that mirrors fs_mpc_mg.plant.Plant
     (Eqs. 1+2). Use Modelica.Electrical.Polyphase library.
  3. Compile the model to an FMU using OMPython.
  4. Write adapters/openmodelica_fmi/shadow_fmu.py that:
       - Loads the FMU via FMPy (`fmpy.simulate_fmu`)
       - Steps it forward by T_s with the same inputs as fs_mpc_mg.plant.Plant.step
       - Returns the same (i_m, v_dc) state
  5. Write tests/test_om_shadow_equivalence.py asserting the FMU and the Python
     plant give residuals < 1% under identical inputs.

Document any compilation issues in adapters/openmodelica_fmi/README.md.
```

### D.3 — Build the MATLAB/Simulink co-sim adapter
```
Implement adapters/matlab_simulink/. Target: drive a Simulink power-electronics
model from Python while the FS-MPC inner loop runs in Python.

Required:
  1. Install matlabengine (`pip install matlabengine`) — requires MATLAB R2023a+
     installed on the host.
  2. Write Simulink/PlantInverter.slx (use Simscape Electrical) with:
       - Three-phase voltage source for v_s
       - Two-level VSI (you can use SimPowerSystems blocks)
       - L+r AC filter
       - C+R DC link
       - Inputs: switching vector s (3 doubles), i_dc (1 double)
       - Outputs: i_m (3), v_dc (1)
  3. Wrap it in adapters/matlab_simulink/simulink_plant.py with:
       class SimulinkPlant: same interface as fs_mpc_mg.plant.Plant.step()
  4. Write tests/test_simulink_plant_equivalence.py: skip if matlab.engine unavailable,
     else verify residual < 5% vs Python plant under a 5-cycle drive.

Use try/except to gracefully handle missing matlabengine and emit a clear
'install MATLAB first' message.
```

---

## E. Operationalisation and Phase 4

### E.1 — Spin up the Docker stack and confirm MQTT round-trip
```
The fs_mpc_microgrid/docker/ folder contains a docker-compose.yml that runs:
  - 1 Mosquitto broker
  - 4 ICA processes (ica1..ica4)
  - 1 CMC
  - 1 DT

Please:
  1. From the fs_mpc_microgrid/ directory, run:
       docker compose -f docker/docker-compose.yml up --build
  2. In a second PowerShell, install mosquitto-clients and use mosquitto_pub
     to send a v_dc_ref change: 
       mosquitto_pub -h localhost -t "/ica/ica1/refs/v_dc_ref" -m '{"value":880.0,"ts":0}'
  3. Use mosquitto_sub to listen on /ica/+/tel/v_dc and verify all four ICAs are
     publishing telemetry at ~10 Hz.
  4. Run for 60 seconds, then docker compose down.
  5. Capture the docker compose logs and write a one-page diagnostic report
     (deliverables/docker_smoketest_report.md) with the message rates per ICA.
```

### E.2 — Add the 6-pulse rectifier to the loading-mode demo
```
The existing scripts/run_loading_mode.py uses HarmonicLoad (a parametric injector).
Switch it to use the new RectifierLoad (topology-faithful 120°-conduction model).

Edit a copy of the script as scripts/run_loading_mode_rectifier.py:
  - Replace HarmonicLoad with RectifierLoad(P_dc_demand=25e3)
  - Pass dt=T_s/N_sub to load.i_l() so I_d updates correctly
  - Run for 80 ms, save figures/loading_mode_rectifier.png
  - Print THD i_s and compare with the parametric-injector baseline (4.29%)

If the THD differs by more than 2 percentage points, diagnose: is it a phase
relationship issue between fundamental and harmonics? An edge-softening
artifact? Document findings inline.
```

---

## F. Paper / thesis writing

### F.1 — Draft the APPEEC #2 manuscript outline
```
Using docs/FS_MPC_Microgrid_Literature_Review_IEEE.pdf and the simulation
results in studies/, draft a 6-page IEEE conference paper for APPEEC 2026 with
this title: "Headroom-Weighted Harmonic Allocation for Multi-Converter
Microgrid Active Filtering Under FS-MPC".

Structure:
  - Abstract (200 words, current results)
  - I. Introduction (motivation + lit review distilled to 1 page)
  - II. System Model (cite Perez 2016, our energy-domain PI as Eq.5 contribution)
  - III. Headroom Allocation Policy (the §11 contribution — patent claim)
  - IV. Simulation Setup (mention all Tier-1 references)
  - V. Results (use studies C.1 + C.3 figures)
  - VI. Conclusion + Future Work

Save to deliverables/papers/appeec_2026_paper2.md. Include placeholder LaTeX
that compiles with the IEEEtran.cls. Do not invent results — only cite the
ones we actually ran.
```

### F.2 — Generate the MAS-DT-SH thesis Ch4 outline
```
For the PhD thesis chapter on the Math+Algorithm layer (Ch4), write
deliverables/thesis_chapters/ch4_outline.md covering:

  4.1 FS-MPC inner loop derivation (Eq. 1+2 of Perez)
  4.2 Energy-domain DC-link control (the §11 contribution)
  4.3 Multi-converter coordination via centralized QP
  4.4 Harmonic-absorption headroom policy
  4.5 Digital-twin shadow + RLS
  4.6 Cyber screening + anomaly detection
  4.7 Empirical results (point to studies/* outputs)

Each subsection should be ~1 page with key equations, references to the
existing fs_mpc_microgrid/ source files, and pointer to the simulation study
that validates it.
```

---

## G. Maintenance and refactoring

### G.1 — Add a topology-test harness
```
Create tests/test_all_topologies.py that:
  1. Imports every module in topologies/
  2. Calls .build() on each
  3. Asserts that the returned object is a Topology with at least 1 ICA
  4. Asserts that each ICA's bus_id refers to a real bus
  5. Asserts that each LoadNode's bus_id refers to a real bus
  6. Verifies that grid_tie_switch() exists for grid-connected topologies

This is a smoke test, not a deep validation. Use pytest.parametrize to iterate
the topology modules dynamically (use importlib).
```

### G.2 — Convert the dashboard from static HTML to a live FastAPI app
```
The current dashboard is a static HTML report. Add a live server variant in
src/fs_mpc_mg/dashboard/server.py that:

  1. Starts a FastAPI app on port 8080
  2. Subscribes to all /ica/+/tel/* and /dt/+/* topics on the MQTT broker
  3. Pushes updates to a websocket at /ws
  4. Serves a single-page React app (or vanilla JS) at / that re-renders every
     200 ms

Add tests/test_dashboard_server.py that uses TestClient to verify the / endpoint
returns 200 and the /ws endpoint accepts a websocket.

Add a 'dashboard-live' optional dependency group to pyproject.toml: 
  fastapi>=0.110, uvicorn>=0.27, websockets>=12.

Add scripts/run_dashboard_live.py that starts the server and prints
'open http://localhost:8080'.
```

---

## H. Ad-hoc / Debugging

### H.1 — Diagnose a regression
```
After your latest change, pytest reports N failures. For each failure:
  1. Identify the exact assertion that fired
  2. Bisect the regression by running `git diff HEAD~5` and inspecting which
     commit introduced the issue
  3. Reproduce the failure with a minimal repro script in scratch/repro_<N>.py
  4. Propose a fix; do not commit it until I review the diagnosis

Never disable a failing test to make CI green.
```

### H.2 — Profile the hot path
```
Instrument scripts/run_loading_mode.py with cProfile. Identify the top 5
functions by cumulative time. If the FS-MPC inner loop is dominant, try
replacing the Python loop with numba @njit and re-measure. Save the cProfile
output and the speedup table to deliverables/profile_report.md.
```

---

## I. Cross-tool sweep (the "all available softwares" prompt)

### I.1 — Run the same scenario across N tools
```
Build studies/A_baseline/study_A6_cross_tool_consistency.py that runs the
loading-mode scenario (i_dc = -80A, 80 ms) through every adapter that's
available on this machine, in the following preference order:

  1. fs_mpc_mg native Python (always available)
  2. pandapower (steady-state baseline)
  3. PyPSA (economic dispatch comparator)
  4. OpenDSS (QSTS unbalanced)
  5. OpenModelica via FMI
  6. MATLAB/Simulink
  7. PSCAD if PSCAD automation is configured
  8. PowerFactory if PFPy is installed

For each available tool, record:
  - THD i_s
  - Final v_dc
  - Wall-clock simulation time
  - Memory peak

Produce a comparison table in figures/study_A6_cross_tool_consistency.csv
and a bar chart in figures/study_A6_cross_tool_consistency.png. Skip any tool
whose Python bindings are not installed (without erroring out).
```

---

## How to use this file

1. Open VS Code Claude.
2. Paste the entire prompt block (everything between the triple-backtick fences) as a single message.
3. Let Claude do the work end-to-end.
4. Check tests pass and figures/CSVs are produced before moving to the next prompt.
5. Commit each prompt's output as a single git commit so progress is rewindable.

Each prompt above is an atomic unit. They can be reordered or skipped; cross-references between prompts are explicit (e.g., "as in study A.2") so VS Code Claude can find them without context from earlier sessions.
