# Cross-tool adapters

Each subfolder bridges the canonical Python `Topology` + ICA/CMC/DT control
stack to one external simulator. The adapter contract is:

    write_model(topology, out_path)        # serialise topology to vendor format
    co_simulate(topology, scenario)        # run vendor sim with Python control loop
    read_results(path)                     # parse vendor output → numpy/pandas

## Status

| Adapter | Status | Notes |
|---|---|---|
| `pandapower/` | scaffold | Steady-state OPF; convert Topology to pandapower net |
| `pypsa/` | scaffold | Tertiary economic dispatch |
| `opendss/` | scaffold | QSTS unbalanced studies |
| `openmodelica_fmi/` | scaffold | FMI-Cosim 2.0 EMT replica for the DT |
| `matlab_simulink/` | scaffold | Co-sim via `matlab.engine.start_matlab()` |
| `pscad/` | scaffold | PSCAD automation + Python control |
| `powerfactory/` | scaffold | PFPy-based grid studies |
| `hil/` | reserved | Phase 4 — Typhoon HIL / OPAL-RT |

Pick whichever is on your machine and ask Claude to fill in the adapter.
