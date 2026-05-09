# fault_location_id

**fault_location_id — Single-ended joint estimation of HIF location α and arc resistance Rx via power-frequency admittance identification with dual-channel noise modelling.**

This sub-project of the SAMBPS DTaaS monorepo operationalises the IEEE Access
manuscript transfer-function HIF locator into a 48-week, ≈ 252 person-day
delivery plan. A two-section π-model state-space (Phase 0) admits a continuous
parametrisation in (α, Rx) which is then refined to a closed-form cascaded
ABCD / Bergeron distributed-parameter model (Phase 2). The estimator is a
two-stage joint optimiser (grid + multi-start, then gradient-with-Armijo) with
analytical gradients and a maximum-likelihood cost weighted by the corrected
proper-complex-Gaussian-ratio Fisher information (Phase 1). Phases 3–5
generalise to three-phase IEEE 13/34/123 feeders, validate against four
literature competitors under five field-grade impairment classes, and
hardware-test on RTDS / Typhoon HIL with a real IEC 61850-9-2 SV / GOOSE IED
loop. The canonical execution plan with day-level WBS, RACI, decision gates
and acceptance tests is `docs/FaultLocationIdentification_ExecutionPlan.pdf`.

## Status

**Phase 0 — in progress.** Editorial + reproducibility hardening, IEEE Access
camera-ready. WP0.1 through WP0.6, target close W2 Fri (29 May 2026, gate D0).

## Folder map

```
fault_location_id/
├── README.md                                        ← you are here
├── LICENSE                                           (MIT)
├── pyproject.toml
├── Makefile
├── .gitignore
├── .github/workflows/ci.yml
├── __init__.py
├── docs/
│   ├── FaultLocationIdentification_ExecutionPlan.pdf  ← canonical plan
│   ├── FaultLocationIdentification_ExecutionPlan.tex
│   └── changelog.md
├── models/                  WP0.5, WP2.1, WP3.1, WP3.3, WP3.5, WP4.1-4.4
├── inverse_estimation/      WP1.6, WP2.2, WP2.4, WP3.6
├── adaptation/              WP3.5, gate hand-off to DTaaS
├── evaluation/              WP4.5  (Paramo / Iurinic / Cui-Weng / Zeng)
├── tests/                   acceptance tests for D-A through D-H
├── outputs/                 CSV / MAT / PNG artefacts (gitignored, .gitkeep tracked)
├── run_faultloc_phase0_baseline.py
├── run_faultloc_phase1_crossplatform.py
├── run_faultloc_phase2_continuous_param.py
├── run_faultloc_phase3_threephase.py
├── run_faultloc_phase4_impairments.py
└── run_faultloc_phase5_hil.py
```

Every Python module's docstring states which v3 work package(s) it
implements, the relevant acceptance test, and the public API target.

## Build instructions

```bash
# 1. Install (editable) with dev extras
make setup
# equivalent to:  python -m pip install -e ".[dev]"

# 2. Run the test suite (collects 0 tests at S2; populated as deliverables land)
pytest

# 3. Run the MATLAB Phase-0 smoke test
matlab -batch "addpath('matlab'); run_phase0_smoke"
```

Convenience phase runners are exposed as Makefile targets:
`make phase0`, `make phase1`, …, `make phase5`.

## Citation

If you use this code, please cite the IEEE Access submission:

```bibtex
@article{ArjundasSwarup2026HIFTF,
  author    = {Arjundas, K. and Swarup, K. Shanthi},
  title     = {Single-Ended Joint Estimation of HIF Location and Arc Resistance
               via Power-Frequency Admittance Identification with
               Dual-Channel Noise Modelling},
  journal   = {IEEE Access},
  year      = {2026},
  note      = {Submitted; reproducibility code released under MIT.}
}
```

## Data availability

The 720-case synthetic waveform set, the 50-section MATLAB reference
dataset, all PSCAD / EMTP-RV models, and the analysis scripts are released
under MIT alongside this repository at the Zenodo DOI minted on every
decision-gate release (D0, D2, D4, D5). The Zenodo DOI is published in
`docs/changelog.md` and in the camera-ready Data Availability Statement
once Phase 0 closes (D-A); until then the placeholder is `<DOI-pending>`.

## License

MIT — see [LICENSE](LICENSE). Copyright © 2026 SAMBPS Digital Twin Labs
(Anoop Eluvathingal et al.).
