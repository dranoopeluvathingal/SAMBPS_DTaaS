# TR-87 Scope Definition

## What TR-87 IS

- A **COMTRADE C37.111 ingestor** that reads field recordings and PSCAD exports
  and converts them to the `FaultCase` dict consumed by the SAMBP Digital Twin
- A **PSCAD → SAMBP EMT replay pipeline** (Phase A: adapter + validation;
  Phase B: headless PSCAD batch API, conditional on licence)
- The `io_utils` layer bridge that gives the Digital Twin parity between
  simulation sources (ANDES) and measurement sources (COMTRADE/PSCAD)
- The natural home for COMTRADE parsing, as identified in the April 2026
  ANDES-silo audit

## What TR-87 IS NOT

- **Not a PSCAD model builder** — TR-87 reads existing PSCAD exports; it does
  not generate PSCAD projects or run PSCAD simulations autonomously
  (Phase B will add headless API, but the model is pre-built)
- **Not an EMT solver** — PSCAD/EMTDC is the EMT solver; TR-87 only ingests its output
- **Not a replacement for `andes_adapter.py`** — the two adapters are parallel,
  not competing; ANDES remains the primary simulation source for the PhD scope
- **Not a field-recording campaign** — actual field data (Amprion HVDC, NTU HVDC
  test-bench) is a Q3 2026 target; TR-87 Phase A validates on synthetic waveforms
- **Not an HVDC-specific tool** — it is general-purpose; HVDC recordings are a
  future use case under TR-H01+ (separate DTaaS namespace)

## Boundary with Adjacent TRs

| TR | Relation |
|---|---|
| TR-43..45 (Digital Twin) | TR-87 feeds their input `FaultCase` dict |
| TR-56/59/62 (ANDES) | Parallel source — same dict, different adapter |
| TR-86 (IEEE 118-bus MC) | TR-86 uses ANDES; TR-87 enables PSCAD cross-check |
| TR-88 (N-2 cascade) | TR-88 may use TR-87 COMTRADE waveforms as inputs |
| TR-89 (DFIG EMT) | TR-87 COMTRADE ingestor enables DFIG field-recording replay |
| TR-90 (PV EMT) | Same — PV inverter fault recordings |
| TR-91 (GNN) | TR-87 waveforms feed node-feature extraction for graph learning |
| TR-H01+ (HVDC DTaaS) | First integration point for HVDC recordings (separate namespace) |

## Adapter Mirror Pattern

```
andes_adapter.py          comtrade_adapter.py (TR-87)
    │                             │
    ▼                             ▼
AndesResult namedtuple    ComtradeResult namedtuple
    │                             │
    └─────────────────────────────┘
                  │
                  ▼
           FaultCase dict
    {t, ia, ib, ic, va, vb, vc,
     fault_type, fault_R_pu,
     label, meta, source}
                  │
                  ▼
    SAMBP Digital Twin (TR-43..45)
    estimate_reduced_source_parameters()
```

## File Locations

| Artefact | Path |
|---|---|
| Adapter module | `04_code/sambp/io_utils/comtrade_adapter.py` |
| Demo runner | `04_code/sambp/digital_twin/models/tr87_pscad_emt_runner.py` |
| Field waveform store | `05_data/fault_waveforms/` |
| PSCAD export store | `05_data/fault_waveforms/pscad/` |
| TR report | `03_technical_reports/phase_8_advanced_extensions/TR87_pscad_emt_replay/main_report87.pdf` |
