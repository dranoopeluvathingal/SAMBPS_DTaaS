# =============================================================================
# tests/test_neg_seq_supervisor.py
#
# Unit tests for TR-73: negative-sequence supervision.
#
# Tests
# -----
#   1. test_sequence_extraction_accuracy — DFT Fortescue matches theoretical
#      sequence magnitudes for a known unbalanced waveform
#   2. test_supervision_blocking        — IBR distortion (high I2, low V2)
#      correctly issues BLOCK alarm
#   3. test_ibr_distortion_vs_real_fault — same I2/I1 ratio, different V2/V1:
#      IBR case gets BLOCK, fault case gets PERMIT
#   4. test_scenario_library_coverage   — 50 scenarios exist; categories correct
#   5. test_three_phase_fault_no_block  — balanced 3PH fault does not BLOCK
# =============================================================================

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from estimation.neg_seq_supervisor import (
    NegSeqAlarm,
    NegSeqSupervisor,
    SequenceExtractor,
)
from models.unbalance_scenario import UnbalanceScenarioLibrary


# ---------------------------------------------------------------------------
# Waveform generators
# ---------------------------------------------------------------------------

def _balanced_waveform(n: int = 40, fs: float = 1000.0, f0: float = 50.0,
                        v_mag: float = 1.0, i_mag: float = 0.5
                        ) -> tuple[np.ndarray, np.ndarray]:
    """Pure positive-sequence three-phase waveform (no unbalance)."""
    t = np.arange(n) / fs
    w = 2.0 * math.pi * f0
    a = 2.0 * math.pi / 3.0
    v = v_mag * np.column_stack([
        np.cos(w * t),
        np.cos(w * t - a),
        np.cos(w * t - 2 * a),
    ])
    i = i_mag * np.column_stack([
        np.cos(w * t),
        np.cos(w * t - a),
        np.cos(w * t - 2 * a),
    ])
    return v, i


def _unbalanced_waveform(
    n: int = 40,
    fs: float = 1000.0,
    f0: float = 50.0,
    v_neg: float = 0.15,   # V2 magnitude [pu]
    i_neg: float = 0.30,   # I2 magnitude [pu]
) -> tuple[np.ndarray, np.ndarray]:
    """
    Synthesise a waveform with known positive + negative sequence magnitudes.
    Uses inverse Fortescue so the DFT should recover I2/I1 exactly.
    """
    import cmath
    t  = np.arange(n) / fs
    w  = 2.0 * math.pi * f0
    a_ = cmath.rect(1.0, 2.0 * math.pi / 3.0)
    a2 = a_ * a_

    def _phase(m1: float, m2: float, phase_shift: float = 0.0) -> np.ndarray:
        """Generate [Va, Vb, Vc] from (m1, m2) sequence magnitudes."""
        x1 = complex(m1, 0)   # positive seq phasor at 0°
        x2 = complex(m2, 0)   # negative seq phasor at 0°
        xa = x1 + x2
        xb = a2 * x1 + a_ * x2
        xc = a_ * x1 + a2 * x2
        carrier = np.exp(1j * (w * t + phase_shift))
        out = np.zeros((n, 3))
        out[:, 0] = np.real(xa * carrier)
        out[:, 1] = np.real(xb * carrier)
        out[:, 2] = np.real(xc * carrier)
        return out

    v_abc = _phase(1.0, v_neg)
    i_abc = _phase(0.5, i_neg)
    return v_abc, i_abc


def _run_extractor(v_abc: np.ndarray, i_abc: np.ndarray,
                   fs: float = 1000.0, f0: float = 50.0) -> dict:
    """Push all samples into SequenceExtractor and return last extract()."""
    ext = SequenceExtractor(fs=fs, f0=f0)
    for k in range(len(v_abc)):
        ext.push(v_abc[k], i_abc[k])
    return ext.extract()


def _run_supervisor_from_seqs(seqs: dict, k_ibr: float,
                               n_steps: int = 5) -> list[NegSeqAlarm]:
    """Feed the same seqs dict n_steps times into the supervisor."""
    sup = NegSeqSupervisor()
    alarms = []
    for j in range(n_steps):
        a = sup.update(j * 1e-3, seqs, k_ibr)
        if a is not None:
            alarms.append(a)
    return alarms


# ---------------------------------------------------------------------------
# Test 1: sequence extraction accuracy
# ---------------------------------------------------------------------------

def test_sequence_extraction_accuracy():
    """
    Feed a waveform with known I2/I1 = 0.30/0.50 = 0.60 into SequenceExtractor.
    DFT-Fortescue should recover |I2|/|I1| within 2% relative error.
    """
    v_abc, i_abc = _unbalanced_waveform(n=40, i_neg=0.30)
    seqs = _run_extractor(v_abc, i_abc)

    expected_i21 = 0.30 / 0.50   # = 0.60
    actual_i21   = seqs['I2_I1_ratio']
    rel_err      = abs(actual_i21 - expected_i21) / expected_i21

    assert rel_err < 0.02, (
        f"I2/I1 ratio error {rel_err:.3f} exceeds 2% "
        f"(expected {expected_i21:.3f}, got {actual_i21:.3f})"
    )

    # Also check V2/V1 recovery
    expected_v21 = 0.15 / 1.0
    actual_v21   = seqs['V2_V1_ratio']
    rel_err_v    = abs(actual_v21 - expected_v21) / expected_v21
    assert rel_err_v < 0.02, (
        f"V2/V1 ratio error {rel_err_v:.3f} exceeds 2%"
    )


# ---------------------------------------------------------------------------
# Test 2: supervision blocking for IBR distortion
# ---------------------------------------------------------------------------

def test_supervision_blocking():
    """
    IBR distortion signature: I2/I1 = 0.25 but V2/V1 = 0.05 (low), k_ibr=0.60.
    NegSeqSupervisor must issue at least one BLOCK alarm.
    """
    seqs = {
        'I2_I1_ratio': 0.25,
        'V2_V1_ratio': 0.05,
        'I0_I1_ratio': 0.01,
    }
    alarms = _run_supervisor_from_seqs(seqs, k_ibr=0.60, n_steps=6)

    blocks = [a for a in alarms if a.action == "BLOCK"]
    assert blocks, (
        f"Expected BLOCK for IBR distortion; got {[a.action for a in alarms]}"
    )
    assert blocks[0].classification == "IBR_DISTORTION"
    assert blocks[0].confidence >= 0.55


# ---------------------------------------------------------------------------
# Test 3: IBR distortion vs real fault discrimination
# ---------------------------------------------------------------------------

def test_ibr_distortion_vs_real_fault():
    """
    Same I2/I1 = 0.40, but:
      - IBR case:   V2/V1 = 0.05 (low)  → BLOCK
      - Fault case: V2/V1 = 0.18 (high) → PERMIT
    """
    ibr_seqs = {'I2_I1_ratio': 0.40, 'V2_V1_ratio': 0.05, 'I0_I1_ratio': 0.02}
    flt_seqs = {'I2_I1_ratio': 0.40, 'V2_V1_ratio': 0.18, 'I0_I1_ratio': 0.35}

    ibr_alarms = _run_supervisor_from_seqs(ibr_seqs, k_ibr=0.65, n_steps=6)
    flt_alarms = _run_supervisor_from_seqs(flt_seqs, k_ibr=0.30, n_steps=6)

    ibr_blocks  = [a for a in ibr_alarms if a.action == "BLOCK"]
    flt_permits = [a for a in flt_alarms if a.action == "PERMIT"]

    assert ibr_blocks, (
        f"IBR case should BLOCK; got {[a.action for a in ibr_alarms]}"
    )
    assert flt_permits, (
        f"Fault case should PERMIT; got {[a.action for a in flt_alarms]}"
    )
    assert ibr_blocks[0].classification  == "IBR_DISTORTION"
    assert flt_permits[0].classification == "REAL_FAULT"


# ---------------------------------------------------------------------------
# Test 4: scenario library coverage
# ---------------------------------------------------------------------------

def test_scenario_library_coverage():
    """
    UnbalanceScenarioLibrary must provide exactly 50 scenarios covering all
    four categories with correct expected actions.
    """
    lib       = UnbalanceScenarioLibrary()
    scenarios = lib.all()

    assert len(scenarios) == 50, f"Expected 50, got {len(scenarios)}"

    cats = {s.category for s in scenarios}
    assert "REAL_FAULT"      in cats
    assert "IBR_DISTORTION"  in cats
    assert "LOAD_UNBALANCE"  in cats
    assert "AMBIGUOUS"       in cats

    # IBR distortion scenarios should have BLOCK expected
    ibr_scens = [s for s in scenarios if s.category == "IBR_DISTORTION"]
    assert all(s.expected_action == "BLOCK" for s in ibr_scens), (
        "All IBR_DISTORTION scenarios should expect BLOCK"
    )

    # Real fault SLG/DLG should have PERMIT expected
    real_scens = [s for s in scenarios
                  if s.category == "REAL_FAULT" and s.fault_type in ("SLG", "DLG")]
    assert all(s.expected_action == "PERMIT" for s in real_scens), (
        "All SLG/DLG REAL_FAULT scenarios should expect PERMIT"
    )

    # Verify waveform generation works for at least one scenario
    s = lib.by_id(21)   # IBR distortion scenario
    v_abc, i_abc = lib.generate_waveform(s, fs=1000, f0=50, n_cycles=2)
    assert v_abc.shape == (40, 3)
    assert i_abc.shape == (40, 3)
    assert not np.any(np.isnan(v_abc))


# ---------------------------------------------------------------------------
# Test 5: three-phase fault does not trigger BLOCK
# ---------------------------------------------------------------------------

def test_three_phase_fault_no_block():
    """
    Balanced three-phase fault: I2/I1 < 0.05.
    Supervisor must not issue a BLOCK (would suppress a valid trip).
    """
    v_abc, i_abc = _balanced_waveform(n=40, v_mag=0.60, i_mag=0.90)
    seqs = _run_extractor(v_abc, i_abc)

    # The balanced fault has very low I2/I1 — supervisor should not block
    alarms = _run_supervisor_from_seqs(seqs, k_ibr=0.70, n_steps=8)
    blocks = [a for a in alarms if a.action == "BLOCK"]
    assert not blocks, (
        f"3PH fault must not trigger BLOCK; got {[a.action for a in alarms]}"
    )
