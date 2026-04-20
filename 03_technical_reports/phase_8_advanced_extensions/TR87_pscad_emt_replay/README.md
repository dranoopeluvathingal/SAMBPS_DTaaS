# TR-87 — PSCAD → SAMBP EMT Replay Pipeline + COMTRADE C37.111 Ingestor

| Field | Value |
|---|---|
| TR | TR-87 |
| Phase | 8 — Advanced Extensions |
| Priority | P2 |
| Target | Q2 2026 |
| Status | **COMPLETE** (delivered 2026-04-20, commit c68b7fdd) |
| Folder | `03_technical_reports/phase_8_advanced_extensions/TR87_pscad_emt_replay/` |

## Scope

Two deliverables bundled in one TR:

1. **COMTRADE C37.111 ingestor** — `04_code/sambp/io_utils/comtrade_adapter.py`  
   Parses IEEE C37.111-1999 and -2013 field recordings (.cfg/.dat pairs) and
   PSCAD/EMTDC CSV exports into the identical `FaultCase` dict that
   `andes_adapter.py` produces, so the SAMBP Digital Twin pipeline is
   source-agnostic.

2. **PSCAD → SAMBP EMT replay pipeline** (Phase A complete; Phase B Q3 2026)  
   Phase A: adapter + synthetic validation (2/2 PASS).  
   Phase B (conditional on PSCAD licence): headless PSCAD API, CIGRÉ C4.502
   benchmark, phasor vs. EMT error quantification.

## Acceptance Tests

- [ ] `comtrade_adapter.py` parses C37.111-1999 .cfg/.dat without error
- [ ] `comtrade_adapter.py` parses C37.111-2013 CFF without error
- [ ] PSCAD CSV at 200 kHz downsamples correctly to 10 kHz
- [ ] `FaultCase` dict schema matches `andes_adapter.build_fault_case()` byte-for-byte
- [ ] 3PH synthetic waveform: 2000 samples, fs=10 kHz — PASS
- [ ] SLG synthetic waveform: 2000 samples, fs=10 kHz — PASS
- [ ] `scan_fault_waveform_dir()` returns correct file list for `05_data/fault_waveforms/`

## Key Files

| File | Description |
|---|---|
| `main_report87.tex` / `.pdf` | Full TR report |
| `tr87_results.json` | Validation run output |
| `04_code/sambp/io_utils/comtrade_adapter.py` | Production adapter module |
| `04_code/sambp/digital_twin/models/tr87_pscad_emt_runner.py` | Demo/validation runner |
| `05_data/fault_waveforms/` | Field recording storage (currently synthetic only) |

## Cross-References

- **TR-86** (`ieee118_mc`) — immediately preceding TR in Phase 8
- **TR-88** (`n2_cascading`) — immediately following TR in Phase 8
- **TR-43..TR-45** (Digital Twin) — downstream consumer of `FaultCase` dict
- **TR-56, TR-59, TR-62** (ANDES) — parallel source via `andes_adapter.py`
- **`04_code/sambp/io_utils/andes_adapter.py`** — mirror pattern for comtrade_adapter

## PROGRESS.yaml Row

```yaml
TR-87:
  title: "PSCAD→SAMBP EMT replay + COMTRADE C37.111 ingestor (comtrade_adapter.py)"
  status: complete
  wp_done: 2
  wp_total: 2
  agree_rate: 1.00
  last_updated: "2026-04-20"
```
