# SAMBPS DTaaS - fault_location_id - Makefile
#
# Targets follow the v3 execution plan WBS phases.  Each `phase{N}` target
# runs the corresponding `run_faultloc_phase{N}_*.py` script.

PYTHON ?= python3
PIP    ?= $(PYTHON) -m pip

.PHONY: help setup test lint format clean matlab-smoke \
        phase0 phase1 phase2 phase3 phase4 phase5 \
        all-phases

help:
	@echo "fault_location_id - common targets:"
	@echo "  make setup        Install package (editable) + dev extras"
	@echo "  make test         Run pytest"
	@echo "  make lint         Run ruff check"
	@echo "  make format       Run black (and ruff format)"
	@echo "  make clean        Remove build / cache artefacts"
	@echo "  make matlab-smoke Run MATLAB sym/eig smoke (WP0.4 sub-task 4)"
	@echo "  make phase0       Run Phase 0 baseline (WP0.1-0.5)"
	@echo "  make phase1       Run Phase 1 cross-platform + corrected CRLB"
	@echo "  make phase2       Run Phase 2 continuously parametrised optimiser"
	@echo "  make phase3       Run Phase 3 three-phase / IEEE feeders / TFT"
	@echo "  make phase4       Run Phase 4 impairments + competitor benchmark"
	@echo "  make phase5       Run Phase 5 HIL pilot + DTaaS productisation"
	@echo "  make all-phases   Run phase0 through phase5 in sequence"

setup:
	$(PIP) install -e ".[dev]"

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m black .
	$(PYTHON) -m ruff check --fix .

clean:
	rm -rf build dist *.egg-info
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

matlab-smoke:
	matlab -batch "addpath('matlab'); run_smoke"

phase0-smoke:
	matlab -batch "addpath('matlab'); addpath('matlab/utils'); run_phase0_smoke"

phase0-capture:
	matlab -batch "addpath('matlab'); addpath('matlab/utils'); run_capture_stats"

phase0-sensitivity:
	matlab -batch "addpath('matlab'); addpath('matlab/utils'); run_hyperparam_sensitivity"

phase0-figs:
	matlab -batch "addpath('matlab'); addpath('matlab/utils'); addpath('matlab/figs'); fig_section_convergence; fig_snr_sweep; fig_alpha_rx_heatmap"

phase0: setup
	$(PYTHON) run_faultloc_phase0_baseline.py

phase1: setup
	$(PYTHON) run_faultloc_phase1_crossplatform.py

phase2: setup
	$(PYTHON) run_faultloc_phase2_continuous_param.py

phase3: setup
	$(PYTHON) run_faultloc_phase3_threephase.py

phase4: setup
	$(PYTHON) run_faultloc_phase4_impairments.py

phase5: setup
	$(PYTHON) run_faultloc_phase5_hil.py

all-phases: phase0 phase1 phase2 phase3 phase4 phase5
