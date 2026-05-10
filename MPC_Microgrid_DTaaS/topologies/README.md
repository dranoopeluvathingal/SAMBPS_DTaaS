# Topology catalogue

Every file here is a Python module that exposes one function:

```python
def build() -> fs_mpc_mg.cmc.Topology:
    """Return a Topology graph (buses, ICAs, loads, switches)."""
```

The adapter layer (`../adapters/*`) consumes that graph and translates it into
the native model format of each external simulator.

## Implemented (stubs)

- `cigre_mv_residential.py` — 11-bus CIGRE benchmark MV
- `cigre_mv_industrial.py` — 7-bus CIGRE benchmark MV industrial
- `ieee_13_bus.py`, `ieee_33_bus.py`, `ieee_34_bus.py` — IEEE PES test feeders
- `campus_dc_microgrid.py` — NUS PSCL / IIT-M hybrid AC/DC template

## Adding a new topology

1. Subclass or instantiate `fs_mpc_mg.cmc.Topology`.
2. Add buses, switches, ICAs, loads.
3. Optionally include per-line-segment R+jX so the adapter layer can build
   line models.
4. Add a corresponding entry in the catalogue table in `../README.md`.
5. Add an integration test in `../fs_mpc_microgrid/tests/test_topology_<name>.py`.
