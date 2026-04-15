"""
run_dt_lab.py
SAMBP Digital Twin Lab — unified study runner

Supersedes the standalone scripts:
  sambp/system/run_digital_twin_study.py    (TR-43)
  sambp/system/run_dt_estimation_study.py   (TR-44)
  sambp/system/run_dt_validation_study.py   (TR-45)

All studies now run through the proper digital_twin package.

Studies
-------
  A — Update rate vs relay speed (TR-43 §2)
  B — RLS k_ibr convergence (TR-43 §3)
  C — EKF multi-parameter estimation accuracy (TR-44 §2)
  D — EKF drift tracking — slow k_ibr change (TR-44 §4)
  E — DT-relay validation: agreement rate, FP/FN by region (TR-45 §2–3)
  F — End-to-end latency budget (TR-45 §5)

Usage
-----
  python run_dt_lab.py             # all studies
  python run_dt_lab.py --study B   # single study
  python run_dt_lab.py --study E --n-mc 2000
"""

import argparse
import math
import random
import sys
import time
import os
import numpy as np

# Allow running from this directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sambp.digital_twin import DTEngine
from sambp.digital_twin.models.state_space_model  import IBRStateSpaceModel
from sambp.digital_twin.models.scenario_library   import ScenarioLibrary
from sambp.digital_twin.models.protection_mirror  import ProtectionMirror
from sambp.digital_twin.estimation.rls_estimator  import RLSEstimator
from sambp.digital_twin.estimation.ekf_estimator  import EKFEstimator
from sambp.digital_twin.estimation.ekf_phasor_estimator import EKFPhasorEstimator
from sambp.digital_twin.validation.decision_comparator import DecisionComparator
from sambp.digital_twin.validation.flag_engine    import FlagEngine

# ── RNG seeds ──────────────────────────────────────────────────────────────
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

# ── Shared parameters ───────────────────────────────────────────────────────
DT_RATE      = 1000    # Hz
RELAY_T_MIN  = 0.020   # s — Z1/87L trip time
K_IBR_TRUE   = 0.200
F_GFM_TRUE   = 0.500
ALPHA_TRUE   = 0.600
SIGMA_V      = 0.005
SIGMA_I      = 0.010

_FAULT_TYPES = ['3PH', 'SLG', 'SLG', 'SLG', 'SLG', 'SLG', 'LL', 'LL', 'LLG']


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════

def _synth_measurements(k_ibr, alpha, sigma_v=SIGMA_V, sigma_i=SIGMA_I,
                         n_samples=1, rng=None):
    """
    Generate synthetic three-phase voltage and current samples.

    Returns list of (v_abc, i_abc) tuples.
    """
    rng = rng or np.random
    samples = []
    # Produce fault-point RMS-amplitude samples consistent with the EKF
    # observation model h(x):
    #   I_pos = k_ibr
    #   Z_app = V_pos / I_pos = alpha * z_line / k_ibr
    #   → V_pos = alpha * z_line   (relay terminal voltage during fault)
    #
    # Using constant-envelope (DC) samples so RMS = amplitude directly.
    # z_line = 0.050 pu (nominal, matches IBRStateSpaceModel._X_NOM[1]).
    Z_LINE = 0.050
    I_base = k_ibr               # fault current [pu]
    V_base = alpha * Z_LINE      # relay terminal voltage during fault [pu]
    for _ in range(n_samples):
        v_abc = np.array([V_base, V_base, V_base]) + rng.normal(0, sigma_v, 3)
        i_abc = np.array([I_base, I_base, I_base]) + rng.normal(0, sigma_i, 3)
        samples.append((v_abc, i_abc))
    return samples


def hdr(title):
    print(f"\n{'═'*64}")
    print(f"  {title}")
    print(f"{'═'*64}")


def subhdr(title):
    print(f"\n── {title} ──")


# ══════════════════════════════════════════════════════════════════════════
# Study A — Update rate vs relay speed
# ══════════════════════════════════════════════════════════════════════════

def study_A():
    hdr("Study A: DT Update Rate vs Relay Speed")
    dt_rates = [100, 200, 500, 1000, 2000, 5000]

    print(f"\n  {'DT rate [Hz]':>14s} {'ms/cycle':>10s} {'Samples before Z1/87L trip':>28s}  OK?")
    print(f"  {'─'*14} {'─'*10} {'─'*28}  {'─'*12}")
    for rate in dt_rates:
        cycle_ms = 1000 / rate
        samples  = int(rate * RELAY_T_MIN)
        ok = '✓' if samples >= 2 else '✗ INSUFFICIENT'
        print(f"  {rate:>14d} {cycle_ms:>10.2f} {samples:>28d}  {ok}")

    print(f"\n  Selected: {DT_RATE} Hz → {int(DT_RATE*RELAY_T_MIN)} samples before fastest trip")
    print(f"  DT cycle: {1000/DT_RATE:.1f} ms  |  Relay min: {RELAY_T_MIN*1000:.0f} ms  |  Margin: ×{int(DT_RATE*RELAY_T_MIN)}")


# ══════════════════════════════════════════════════════════════════════════
# Study B — RLS k_ibr convergence
# ══════════════════════════════════════════════════════════════════════════

def study_B():
    hdr("Study B: RLS k_ibr Convergence (TR-43 §3)")
    rls = RLSEstimator(forget=0.98, k_init=0.10)
    rng = np.random.RandomState(SEED)

    N = 100
    samples = _synth_measurements(K_IBR_TRUE, ALPHA_TRUE,
                                   sigma_i=SIGMA_I, n_samples=N, rng=rng)
    estimates = []
    for v_abc, i_abc in samples:
        state = rls.update(0.0, v_abc, i_abc)
        estimates.append(state['k_ibr'])

    print(f"\n  True k_ibr = {K_IBR_TRUE:.3f}  |  σ_I = {SIGMA_I:.3f} pu  |  λ = {rls.forget}")
    print(f"\n  {'Updates':>8s} {'Time [ms]':>12s} {'k_est':>10s} {'Error [%]':>12s}")
    print(f"  {'─'*8} {'─'*12} {'─'*10} {'─'*12}")
    for n in [5, 10, 20, 50, 100]:
        k_est = estimates[n-1]
        err   = abs(k_est - K_IBR_TRUE) / K_IBR_TRUE * 100
        t_ms  = n / DT_RATE * 1000
        print(f"  {n:>8d} {t_ms:>12.1f} {k_est:>10.4f} {err:>12.2f}")

    print(f"\n  Convergence criterion (<5% error): "
          f"{'met at 20 updates (20 ms)' if abs(estimates[19]-K_IBR_TRUE)/K_IBR_TRUE < 0.05 else 'NOT MET'}")


# ══════════════════════════════════════════════════════════════════════════
# Study C — EKF multi-parameter accuracy
# ══════════════════════════════════════════════════════════════════════════

def study_C():
    hdr("Study C: EKF Multi-Parameter Estimation Accuracy (TR-44 §2)")
    noise_levels = [0.001, 0.002, 0.005, 0.010, 0.020, 0.050]
    N_MC = 200

    print(f"\n  {'σ_I [pu]':>10s} {'k_ibr RMSE [%]':>16s} {'α RMSE [%]':>12s} {'κ_n mean':>10s}")
    print(f"  {'─'*10} {'─'*16} {'─'*12} {'─'*10}")

    for sigma in noise_levels:
        k_errs, a_errs, kappas = [], [], []
        rng = np.random.RandomState(SEED + int(sigma*1000))
        for _ in range(N_MC):
            ekf = EKFEstimator()
            samples = _synth_measurements(K_IBR_TRUE, ALPHA_TRUE,
                                           sigma_i=sigma, n_samples=50, rng=rng)
            state = None
            for v, i in samples:
                state = ekf.update(0.0, v, i)
            if state:
                k_errs.append(abs(state['k_ibr'] - K_IBR_TRUE) / K_IBR_TRUE * 100)
                a_errs.append(abs(state['alpha']  - ALPHA_TRUE)  / ALPHA_TRUE  * 100)
                kappas.append(state['kappa_n'])

        k_rmse = math.sqrt(sum(e**2 for e in k_errs) / len(k_errs))
        a_rmse = math.sqrt(sum(e**2 for e in a_errs) / len(a_errs))
        kappa_mean = sum(kappas) / len(kappas)
        print(f"  {sigma:>10.3f} {k_rmse:>16.2f} {a_rmse:>12.2f} {kappa_mean:>10.1f}")

    print(f"\n  Confidence gate: κ_n < 30 → EKF trusted; κ_n ≥ 30 → library fallback")


# ══════════════════════════════════════════════════════════════════════════
# Study D — EKF drift tracking
# ══════════════════════════════════════════════════════════════════════════

def study_D():
    hdr("Study D: EKF Slow k_ibr Drift Tracking (TR-44 §4)")
    N = 1000
    ekf = EKFEstimator()
    rng = np.random.RandomState(SEED)

    k_true  = [0.20 + 0.10 * math.sin(2*math.pi*i/500) for i in range(N)]
    k_est   = []
    kappa_n = []

    for i in range(N):
        v, ic = _synth_measurements(k_true[i], ALPHA_TRUE,
                                     sigma_i=SIGMA_I, n_samples=1, rng=rng)[0]
        state = ekf.update(i / DT_RATE, v, ic)
        k_est.append(state['k_ibr'])
        kappa_n.append(state['kappa_n'])

    errs = [abs(k_est[i] - k_true[i]) / 0.20 * 100 for i in range(N)]

    print(f"\n  Sinusoidal drift: ±0.10 pu over 500 DT cycles (±50% of k_nom=0.20)")
    print(f"\n  {'Metric':>20s} {'Value':>12s}")
    print(f"  {'─'*20} {'─'*12}")
    print(f"  {'Mean tracking error':>20s} {sum(errs)/N:>12.2f}%")
    print(f"  {'Max tracking error':>20s} {max(errs):>12.2f}%")
    print(f"  {'P95 tracking error':>20s} {sorted(errs)[int(0.95*N)]:>12.2f}%")
    print(f"  {'Mean κ_n':>20s} {sum(kappa_n)/N:>12.1f}")
    print(f"  {'Max κ_n':>20s} {max(kappa_n):>12.1f}")

    n_trusted = sum(1 for k in kappa_n if k < 30)
    print(f"  {'DT trusted [%]':>20s} {n_trusted/N*100:>12.1f}%  (κ_n < 30)")


# ══════════════════════════════════════════════════════════════════════════
# Study E — Validation: agreement rate + FP/FN by region
# ══════════════════════════════════════════════════════════════════════════

def study_E(n_mc=1000):
    """
    DT-relay decision validation (TR-45 §2–3), revised.

    Architecture (single source of truth)
    --------------------------------------
    Both the relay and the DT call ProtectionMirror.predict() — the relay
    with its own independent single-sample measurement, the DT with its
    EKF-smoothed multi-sample estimate.  No duplicate zone logic exists.

    Measurement paths
    -----------------
    • Relay path : one fresh noisy (v_r, i_r) sample per event → relay
                   extracts k_relay, alpha_relay → mirror.predict()
    • DT path    : separate noisy sample fed to EKF over many cycles →
                   dt_state['k_ibr'], dt_state['alpha'] → mirror.predict()
                   (via DecisionComparator)

    Disagreement taxonomy (revised DecisionComparator)
    ---------------------------------------------------
    • Same protection family (e.g. Z1/87L vs 87L) → AGREE + selectivity_note
    • Cross-family mismatch (e.g. 87L vs OC)      → FLAG_ELEMENT
    • Trip direction wrong                          → FLAG_FP / FLAG_FN
    """
    hdr(f"Study E: DT-Relay Validation (N={n_mc}) (TR-45 §2–3, revised)")

    library    = ScenarioLibrary(n_scenarios=1000, seed=SEED)
    mirror     = ProtectionMirror()
    comparator = DecisionComparator(mirror, conf_threshold=0.15)
    flags      = FlagEngine()
    ekf        = EKFEstimator()
    rng_r      = random.Random(SEED)
    rng_np     = np.random.RandomState(SEED)

    Z_LINE = 0.050   # pu — must match ProtectionMirror._Z_LINE

    selectivity_count = 0   # Z1/87L ↔ 87L same-family AGREE events

    for _ in range(n_mc):
        k_true = rng_r.uniform(0.04, 0.50)
        al_true = rng_r.uniform(0.00, 1.05)
        ft      = rng_r.choice(_FAULT_TYPES)

        # ── Relay measurement path (single-sample, independent of DT) ──
        # The relay extracts k_ibr from current magnitude (good SNR: σ_I/k ≈ 5%)
        # and alpha from apparent impedance (single-cycle phasor measurement).
        #
        # V_fault = alpha * Z_LINE is an O(0.03 pu) signal; using absolute
        # σ_V = 0.005 gives poor SNR.  Instead, model the relay's apparent-
        # impedance measurement as having relative error: this is consistent
        # with a class 1P CT + class 1P VT at 80 Sa/cycle, where the combined
        # Z_app error is ≈ 2–5 % rms (TR-43 §2, IEC 60255-121 §7.3).
        # We use σ_k_rel = 0.05 (5 % relative on k) and σ_alpha_rel = 0.05
        # (5 % relative on alpha) as the single-cycle relay measurement model.
        k_relay    = max(0.001, k_true    * (1.0 + rng_np.normal(0, 0.05)))
        alpha_relay = max(0.001, min(1.05,
                          al_true * (1.0 + rng_np.normal(0, 0.05))))

        relay_pred   = mirror.predict(k_relay, alpha_relay, ft)
        r_elem       = relay_pred['element']
        r_action     = relay_pred['action']

        # ── DT measurement path (EKF-smoothed, 20 pre-trip update cycles) ─
        # The DT has been running at 1 kHz for the full fault inception period.
        # Z1/87L operates at ≈20 ms → 20 DT updates complete before the relay
        # asserts a trip signal.  Reset EKF per event (each fault is independent).
        # This models the DT's state at the moment the relay fires, not at t=0.
        ekf.reset()
        for _step in range(20):          # 20 DT cycles = 20 ms
            v_dt, ic_dt = _synth_measurements(k_true, al_true,
                                               sigma_i=SIGMA_I, sigma_v=SIGMA_V,
                                               n_samples=1, rng=rng_np)[0]
            dt_state = ekf.update(_step / DT_RATE, v_dt, ic_dt)

        # ── Build relay event (carries relay's decision, DT's estimate) ─
        relay_event = {
            'relay_id':   'LINE_87L_A',
            'element':    r_elem,
            'action':     r_action,
            'fault_type': ft,
            # DT-estimated state used by comparator for mirror evaluation
            'k_ibr':      dt_state['k_ibr'],
            'alpha':      dt_state['alpha'],
            'kappa_n':    dt_state['kappa_n'],
            'residual':   dt_state['residual'],
        }

        dt_expected = library.nearest(dt_state['k_ibr'], dt_state['alpha'])
        result      = comparator.compare(relay_event, dt_expected)
        flags.record(result)

        if result['verdict'] == 'AGREE' and result['selectivity_note']:
            selectivity_count += 1

    flags.print_summary()
    n_total = flags.flag_summary['total'] if hasattr(flags, 'flag_summary') else n_mc
    s = flags.summary()
    n_agree = s['agree']
    print(f"\n  Of {n_agree} AGREE verdicts: {selectivity_count} with selectivity note "
          f"({selectivity_count/max(n_agree,1)*100:.1f}% — Z1↔87L same-family).")
    print(f"  These are correct protection operations; element difference = speed only.")


# ══════════════════════════════════════════════════════════════════════════
# Study F — End-to-end latency budget
# ══════════════════════════════════════════════════════════════════════════

def study_F():
    hdr("Study F: End-to-End Latency Budget (TR-45 §5)")

    chain = [
        ('CT/VT transducer',            0.5,  'Class 1P CT'),
        ('IEC 61869-9 digital sampling', 0.5,  '80 Sa/cycle + framing'),
        ('Merging unit → relay',         1.0,  'IEC 61850-9-2 SV'),
        ('Relay protection algorithm',   18.0, 'Z1/87L trip time'),
        ('GOOSE trip signal',            2.0,  'IEC 61850-8-1'),
        ('Circuit breaker operation',    30.0, 'Vacuum CB, std.'),
    ]
    T_MEM = 100.0   # ms — maximum fault clearance time (T_mem constraint)

    print(f"\n  {'Stage':<34s} {'Latency [ms]':>13s}  Source")
    print(f"  {'─'*34} {'─'*13}  {'─'*24}")
    total = 0.0
    for stage, ms, src in chain:
        print(f"  {stage:<34s} {ms:>13.1f}  {src}")
        total += ms
    print(f"  {'─'*34} {'─'*13}")
    print(f"  {'TOTAL (sensor → CB open)':<34s} {total:>13.1f}")
    print(f"\n  DT cycle latency:  {1000/DT_RATE:.1f} ms  (parallel, non-blocking → adds 0 ms)")
    print(f"  T_mem constraint:  {T_MEM:.0f} ms")
    print(f"  Margin:            {T_MEM - total:.1f} ms  "
          f"({'OK' if T_MEM > total else 'VIOLATED'})")

    # DT lookup timing
    lib = ScenarioLibrary(n_scenarios=1000)
    t0  = time.perf_counter()
    lib.nearest(0.18, 0.55)
    t1  = time.perf_counter()
    print(f"\n  ScenarioLibrary.nearest() lookup: {(t1-t0)*1000:.3f} ms  "
          f"(budget: {1000/DT_RATE:.1f} ms/cycle)")


# ══════════════════════════════════════════════════════════════════════════
# Study G — EKFEstimator vs EKFPhasorEstimator (phasor DFT extractor)
# ══════════════════════════════════════════════════════════════════════════

def study_G(n_mc=500):
    """
    Compare instantaneous-sequence EKF (Study E baseline) against the
    phasor-DFT EKF (EKFPhasorEstimator) on the same Monte Carlo protocol.

    Protocol differences from Study E
    ----------------------------------
    • N_cycles=1 (fs/f0 = 20 samples) pre-convergence for EKFEstimator
      (same as Study E: one-cycle DT window = 20 ms before relay fires).
    • EKFPhasorEstimator is given the same 20 samples; it defers its first
      EKF update until the DFT buffer is full (sample 20), so both estimators
      see identical data.
    • A sinusoidal measurement model is used here to exercise the DFT extractor
      under realistic waveform conditions (constant-envelope DC gives trivial
      DFT results as all energy sits at bin 0, not bin 1).

    Metrics reported
    ----------------
    • k_ibr RMSE across all trials (after 20-sample window)
    • alpha RMSE
    • Mean kappa_n (condition number)
    • AGREE rate and flag breakdown (same comparator / flag-engine as Study E)
    """
    hdr(f"Study G: EKFEstimator vs EKFPhasorEstimator (N={n_mc})")

    FS   = float(DT_RATE)    # 1000 Hz
    F0   = 50.0              # nominal system frequency
    N_CYCLES = int(FS / F0)  # 20 samples per cycle

    mirror     = ProtectionMirror()
    library    = ScenarioLibrary(n_scenarios=1000, seed=SEED)
    comparator = DecisionComparator(mirror, conf_threshold=0.15,
                                    kappa_threshold=30.0)

    ekf_inst   = EKFEstimator()
    ekf_phasor = EKFPhasorEstimator(fs=FS, f0=F0)

    flags_inst   = FlagEngine()
    flags_phasor = FlagEngine()

    rng = np.random.RandomState(SEED + 10)   # different seed from Study E

    # Trackers for RMSE
    err_k_inst   = []
    err_k_phasor = []
    err_al_inst  = []
    err_al_phasor = []
    kn_inst_list  = []
    kn_phasor_list = []

    Z_LINE = 0.050
    OMEGA  = 2.0 * math.pi * F0

    _FAULT_TYPES_G = ['3PH', 'SLG', 'SLG', 'SLG', 'SLG', 'LL', 'LL', 'LLG']

    for trial in range(n_mc):
        k_true  = rng.uniform(0.04, 0.50)
        al_true = rng.uniform(0.00, 1.05)
        ft      = _FAULT_TYPES_G[trial % len(_FAULT_TYPES_G)]

        # ── Build one-cycle sinusoidal waveform ──────────────────────
        # I_base = k_ibr (positive-sequence amplitude, balanced three-phase)
        # V_base = alpha * Z_LINE (positive-sequence voltage amplitude)
        I_base = k_true
        V_base = al_true * Z_LINE

        ekf_inst.reset()
        ekf_phasor.reset()
        state_inst   = ekf_inst.state
        state_phasor = ekf_phasor.state

        for n in range(N_CYCLES):
            theta = OMEGA * n / FS    # phase angle at sample n

            # Balanced three-phase sinusoids (120° apart)
            i_abc = np.array([
                I_base * math.cos(theta),
                I_base * math.cos(theta - 2.0 * math.pi / 3.0),
                I_base * math.cos(theta + 2.0 * math.pi / 3.0),
            ]) + rng.normal(0.0, SIGMA_I, 3)

            v_abc = np.array([
                V_base * math.cos(theta),
                V_base * math.cos(theta - 2.0 * math.pi / 3.0),
                V_base * math.cos(theta + 2.0 * math.pi / 3.0),
            ]) + rng.normal(0.0, SIGMA_V, 3)

            t = n / FS
            state_inst   = ekf_inst.update(t, v_abc, i_abc)
            state_phasor = ekf_phasor.update(t, v_abc, i_abc)

        # ── Record RMSE contributions ────────────────────────────────
        err_k_inst.append((state_inst['k_ibr']   - k_true) ** 2)
        err_k_phasor.append((state_phasor['k_ibr'] - k_true) ** 2)
        err_al_inst.append((state_inst['alpha']   - al_true) ** 2)
        err_al_phasor.append((state_phasor['alpha'] - al_true) ** 2)
        kn_inst_list.append(state_inst['kappa_n'])
        kn_phasor_list.append(state_phasor['kappa_n'])

        # ── DT-relay comparison for both estimators ──────────────────
        for est_state, flags in [(state_inst, flags_inst),
                                  (state_phasor, flags_phasor)]:
            k_relay  = max(0.001, k_true  * (1.0 + rng.normal(0, 0.05)))
            al_relay = max(0.001, min(1.05, al_true * (1.0 + rng.normal(0, 0.05))))
            relay_pred = mirror.predict(k_relay, al_relay, ft)
            relay_event = {
                'element':    relay_pred['element'],
                'action':     relay_pred['action'],
                'fault_type': ft,
                'k_ibr':      est_state['k_ibr'],
                'alpha':      est_state['alpha'],
                'kappa_n':    est_state['kappa_n'],
            }
            dt_expected = library.nearest(est_state['k_ibr'], est_state['alpha'])
            result = comparator.compare(relay_event, dt_expected)
            flags.record(result)

    # ── Results ─────────────────────────────────────────────────────
    rmse_k_inst   = math.sqrt(sum(err_k_inst)    / n_mc)
    rmse_k_phasor = math.sqrt(sum(err_k_phasor)  / n_mc)
    rmse_al_inst  = math.sqrt(sum(err_al_inst)   / n_mc)
    rmse_al_phasor = math.sqrt(sum(err_al_phasor) / n_mc)
    kn_inst_mean  = sum(kn_inst_list)   / n_mc
    kn_phasor_mean = sum(kn_phasor_list) / n_mc

    s_inst   = flags_inst.summary()
    s_phasor = flags_phasor.summary()

    print(f"\n  {'Metric':<34s} {'EKFEstimator':>14s} {'EKFPhasorEstimator':>20s}")
    print(f"  {'─'*34} {'─'*14} {'─'*20}")
    print(f"  {'k_ibr RMSE [pu]':<34s} {rmse_k_inst:>14.4f} {rmse_k_phasor:>20.4f}")
    print(f"  {'alpha RMSE':<34s} {rmse_al_inst:>14.4f} {rmse_al_phasor:>20.4f}")
    print(f"  {'Mean κ_n':<34s} {kn_inst_mean:>14.2f} {kn_phasor_mean:>20.2f}")
    print(f"  {'AGREE rate':<34s} {s_inst['agree_rate']*100:>13.2f}% {s_phasor['agree_rate']*100:>19.2f}%")
    print(f"  {'FLAG_FP rate':<34s} {s_inst['fp_rate']*100:>13.2f}% {s_phasor['fp_rate']*100:>19.2f}%")
    print(f"  {'FLAG_FN rate':<34s} {s_inst['fn_rate']*100:>13.2f}% {s_phasor['fn_rate']*100:>19.2f}%")
    print(f"  {'FLAG_CONF count':<34s} {s_inst['flag_conf']:>14d} {s_phasor['flag_conf']:>20d}")
    print(f"  {'FLAG_ELEMENT count':<34s} {s_inst['flag_element']:>14d} {s_phasor['flag_element']:>20d}")
    print(f"\n  Internal-zone events (EKF):       {s_inst['total']:>6d}")
    print(f"  Internal-zone events (phasor):    {s_phasor['total']:>6d}")
    print(f"\n  DFT gain: k_ibr RMSE ratio = {rmse_k_inst/rmse_k_phasor:.2f}×  "
          f"(phasor {'better' if rmse_k_phasor < rmse_k_inst else 'worse'})")
    print(f"  DFT gain: alpha RMSE ratio = {rmse_al_inst/rmse_al_phasor:.2f}×  "
          f"(phasor {'better' if rmse_al_phasor < rmse_al_inst else 'worse'})")


# ══════════════════════════════════════════════════════════════════════════
# DTEngine integration smoke-test
# ══════════════════════════════════════════════════════════════════════════

def study_integration():
    hdr("Integration Smoke-Test: DTEngine end-to-end")
    engine = DTEngine(dt_rate_hz=DT_RATE, n_scenarios=500, estimator='ekf')
    rng    = np.random.RandomState(SEED)

    print(f"\n  Initialised: {engine!r}")
    print(f"  Library:     {engine.library!r}")

    # Run 25 DT cycles
    for i in range(25):
        v, ic = _synth_measurements(K_IBR_TRUE, ALPHA_TRUE,
                                     sigma_i=SIGMA_I, n_samples=1, rng=rng)[0]
        state = engine.update(i / DT_RATE, v, ic)

    print(f"  After 25 DT cycles (25 ms):")
    print(f"    k_ibr  = {state['k_ibr']:.4f}  (true: {K_IBR_TRUE:.3f})")
    print(f"    z_line = {state['z_line']:.4f}")
    print(f"    alpha  = {state['alpha']:.4f}  (true: {ALPHA_TRUE:.3f})")
    print(f"    f_gfm  = {state['f_gfm']:.4f}")
    print(f"    κ_n    = {state['kappa_n']:.2f}")

    # Validate a trip event
    relay_event = {
        'element': '87L', 'action': 'TRIP', 'fault_type': 'SLG',
        'k_ibr': state['k_ibr'], 'alpha': state['alpha'],
        'kappa_n': state['kappa_n'],
    }
    result = engine.validate(relay_event)
    print(f"\n  Validation result: verdict={result['verdict']}, "
          f"conf={result['confidence']:.2f}")
    print(f"  Reason: {result['reason']}")
    print(f"\n  Flag summary: {engine.flag_summary}")
    print(f"\n  DTEngine: OK ✓")


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='SAMBP Digital Twin Lab — unified study runner')
    parser.add_argument('--study', default='ALL',
                        choices=['A', 'B', 'C', 'D', 'E', 'F', 'G', 'INT', 'ALL'],
                        help='Study to run (default: ALL)')
    parser.add_argument('--n-mc', type=int, default=1000,
                        help='Monte Carlo trials for Study E (default: 1000)')
    args = parser.parse_args()

    print("=" * 64)
    print("  SAMBP Digital Twin Lab")
    print("  Supersedes TR-43 / TR-44 / TR-45 standalone scripts")
    print(f"  DT rate: {DT_RATE} Hz  |  seed: {SEED}")
    print("=" * 64)

    dispatch = {
        'A':   study_A,
        'B':   study_B,
        'C':   study_C,
        'D':   study_D,
        'E':   lambda: study_E(args.n_mc),
        'F':   study_F,
        'G':   lambda: study_G(args.n_mc),
        'INT': study_integration,
    }

    if args.study == 'ALL':
        for fn in dispatch.values():
            fn()
    else:
        dispatch[args.study]()

    print(f"\n{'═'*64}")
    print("  Digital Twin Lab run complete.")
    print(f"{'═'*64}\n")


if __name__ == '__main__':
    main()
