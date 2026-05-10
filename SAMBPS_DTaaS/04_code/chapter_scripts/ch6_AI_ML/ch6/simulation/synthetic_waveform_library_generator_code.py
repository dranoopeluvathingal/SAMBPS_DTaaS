"""
Synthetic family-labelled waveform library generator
for generator-aware inverse model selector benchmarking.

Generates labelled cases for:
    - induction_machine_like
    - dfig_like
    - full_converter_pmsg_like
    - grid_following_inverter_like

Also varies:
    - fault type
    - SCR
    - noise level
    - transient strength
    - decay constants
    - event time

Outputs:
    1. One CSV waveform per case
    2. One metadata CSV containing labels and parameters

Required columns in each waveform file:
    time_s, Va_pu, Vb_pu, Vc_pu, Ia_pu, Ib_pu, Ic_pu
"""

import os
import json
import numpy as np
import pandas as pd


# ============================================================
# Global settings
# ============================================================

SEED = 42
rng = np.random.default_rng(SEED)


# ============================================================
# Utility functions
# ============================================================

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def three_phase_base(t, f=50.0, mag=1.0, phase0=0.0):
    w = 2 * np.pi * f
    a = mag * np.sin(w * t + phase0)
    b = mag * np.sin(w * t - 2*np.pi/3 + phase0)
    c = mag * np.sin(w * t + 2*np.pi/3 + phase0)
    return a, b, c


def add_background_noise(x, std):
    return x + rng.normal(0.0, std, size=len(x))


def add_small_ripple(t, x, ripple_mag=0.003, ripple_freq=350.0, phase=0.0):
    return x + ripple_mag * np.sin(2 * np.pi * ripple_freq * t + phase)


def phase_fault_multipliers(fault_type):
    """
    Approximate phase-dependent voltage/current weighting profiles.
    These are simplified synthetic patterns, not exact network solutions.
    """
    if fault_type == '3ph':
        return (1.0, 1.0, 1.0)
    elif fault_type == 'slg_a':
        return (1.35, 0.95, 0.95)
    elif fault_type == 'slg_b':
        return (0.95, 1.35, 0.95)
    elif fault_type == 'slg_c':
        return (0.95, 0.95, 1.35)
    elif fault_type == 'll_ab':
        return (1.20, 1.20, 0.90)
    elif fault_type == 'll_bc':
        return (0.90, 1.20, 1.20)
    elif fault_type == 'll_ca':
        return (1.20, 0.90, 1.20)
    else:
        return (1.0, 1.0, 1.0)


def voltage_fault_profile(t, t_event, fault_type, scr):
    """
    Simple synthetic voltage dip profile.
    Lower SCR -> deeper and longer disturbance tendency.
    """
    Va, Vb, Vc = three_phase_base(t, f=50.0, mag=1.0)

    depth_base = {
        '3ph': 0.45,
        'slg_a': 0.35,
        'slg_b': 0.35,
        'slg_c': 0.35,
        'll_ab': 0.30,
        'll_bc': 0.30,
        'll_ca': 0.30
    }[fault_type]

    scr_factor = np.clip(3.0 / scr, 0.4, 1.6)
    depth = np.clip(depth_base * scr_factor, 0.08, 0.75)

    mA, mB, mC = phase_fault_multipliers(fault_type)
    tau = np.maximum(t - t_event, 0.0)

    dip_shape = np.exp(-tau / 0.012)
    dip_shape[t < t_event] = 0.0

    Va_out = Va * (1.0 - depth * (mA / max(mA, mB, mC)) * dip_shape)
    Vb_out = Vb * (1.0 - depth * (mB / max(mA, mB, mC)) * dip_shape)
    Vc_out = Vc * (1.0 - depth * (mC / max(mA, mB, mC)) * dip_shape)

    return Va_out, Vb_out, Vc_out


# ============================================================
# Family-specific current models
# ============================================================

def induction_machine_family_current(
    t, t_event, f0, base_mag, fault_type, scr, noise_std
):
    """
    Machine-like oscillatory transient on all phases with SCR influence.
    """
    ia, ib, ic = three_phase_base(t, f=f0, mag=base_mag)

    mA, mB, mC = phase_fault_multipliers(fault_type)

    tau = np.maximum(t - t_event, 0.0)
    tau_d = 0.004 + 0.004 * (3.0 / scr)
    f_tr = 700 + 250 * (scr / 3.0)
    K0 = 0.18 + 0.10 * (3.0 / scr)

    trA = K0 * mA * np.exp(-tau / tau_d) * np.sin(2*np.pi*f_tr*tau + 0.1)
    trB = K0 * mB * np.exp(-tau / tau_d) * np.sin(2*np.pi*f_tr*tau - 0.7)
    trC = K0 * mC * np.exp(-tau / tau_d) * np.sin(2*np.pi*f_tr*tau + 0.5)

    trA[t < t_event] = 0.0
    trB[t < t_event] = 0.0
    trC[t < t_event] = 0.0

    ia = ia + trA
    ib = ib + trB
    ic = ic + trC

    ia = add_small_ripple(t, ia, ripple_mag=0.004, ripple_freq=300.0, phase=0.1)
    ib = add_small_ripple(t, ib, ripple_mag=0.004, ripple_freq=300.0, phase=1.2)
    ic = add_small_ripple(t, ic, ripple_mag=0.004, ripple_freq=300.0, phase=-0.8)

    ia = add_background_noise(ia, noise_std)
    ib = add_background_noise(ib, noise_std)
    ic = add_background_noise(ic, noise_std)

    params = {
        'tau_decay_s': tau_d,
        'f_transient_Hz': f_tr,
        'K_base': K0
    }
    return ia, ib, ic, params


def dfig_family_current(
    t, t_event, f0, base_mag, fault_type, scr, noise_std
):
    """
    Two-stage DFIG-like behavior:
        early oscillatory burst
        later crowbar/FRT shaped slower tail
    """
    ia, ib, ic = three_phase_base(t, f=f0, mag=base_mag)

    mA, mB, mC = phase_fault_multipliers(fault_type)

    tau = np.maximum(t - t_event, 0.0)

    tau1 = 0.002 + 0.0015 * (3.0 / scr)
    tau2 = 0.008 + 0.004 * (3.0 / scr)
    f1 = 1100 + 250 * (scr / 3.0)
    tg = 0.0035 + 0.001 * (3.0 / scr)

    K1 = 0.22 + 0.12 * (3.0 / scr)
    K2 = 0.08 + 0.05 * (3.0 / scr)

    gate = 1.0 / (1.0 + np.exp((tau - tg) / 0.00035))

    def dfig_wave(mult, phase):
        early = K1 * mult * np.exp(-tau / tau1) * np.sin(2*np.pi*f1*tau + phase)
        late = K2 * mult * np.exp(-tau / tau2)
        y = gate * early + (1.0 - gate) * late
        y[t < t_event] = 0.0
        return y

    ia = ia + dfig_wave(mA, 0.0)
    ib = ib + dfig_wave(mB, -0.9)
    ic = ic + dfig_wave(mC, 0.6)

    # mild control-shaped low-frequency tail ripple
    ia = add_small_ripple(t, ia, ripple_mag=0.003, ripple_freq=260.0, phase=0.3)
    ib = add_small_ripple(t, ib, ripple_mag=0.003, ripple_freq=260.0, phase=1.0)
    ic = add_small_ripple(t, ic, ripple_mag=0.003, ripple_freq=260.0, phase=-0.4)

    ia = add_background_noise(ia, noise_std)
    ib = add_background_noise(ib, noise_std)
    ic = add_background_noise(ic, noise_std)

    params = {
        'tau1_s': tau1,
        'tau2_s': tau2,
        'f1_Hz': f1,
        'gate_time_s': tg,
        'K1': K1,
        'K2': K2
    }
    return ia, ib, ic, params


def full_converter_pmsg_family_current(
    t, t_event, f0, base_mag, fault_type, scr, noise_std
):
    """
    Smoother bounded oscillatory control-shaped response.
    """
    ia, ib, ic = three_phase_base(t, f=f0, mag=base_mag)

    mA, mB, mC = phase_fault_multipliers(fault_type)

    tau = np.maximum(t - t_event, 0.0)
    tau_rise = 0.0010 + 0.0004 * (3.0 / scr)
    tau_fall = 0.0050 + 0.0020 * (3.0 / scr)
    f_ctrl = 350 + 120 * (scr / 3.0)
    K = 0.10 + 0.05 * (3.0 / scr)

    def pmsg_wave(mult, phase):
        rise = (1.0 - np.exp(-tau / tau_rise))
        fall = np.exp(-tau / tau_fall)
        y = K * mult * rise * fall * np.sin(2*np.pi*f_ctrl*tau + phase)
        y[t < t_event] = 0.0
        return y

    ia = ia + pmsg_wave(mA, 0.2)
    ib = ib + pmsg_wave(mB, -0.7)
    ic = ic + pmsg_wave(mC, 0.8)

    ia = add_small_ripple(t, ia, ripple_mag=0.002, ripple_freq=220.0, phase=0.1)
    ib = add_small_ripple(t, ib, ripple_mag=0.002, ripple_freq=220.0, phase=0.8)
    ic = add_small_ripple(t, ic, ripple_mag=0.002, ripple_freq=220.0, phase=-0.9)

    ia = add_background_noise(ia, noise_std)
    ib = add_background_noise(ib, noise_std)
    ic = add_background_noise(ic, noise_std)

    params = {
        'tau_rise_s': tau_rise,
        'tau_fall_s': tau_fall,
        'f_ctrl_Hz': f_ctrl,
        'K': K
    }
    return ia, ib, ic, params


def grid_following_inverter_family_current(
    t, t_event, f0, base_mag, fault_type, scr, noise_std
):
    """
    Current-limited, mostly nonoscillatory control-dominated response.
    """
    ia, ib, ic = three_phase_base(t, f=f0, mag=base_mag)

    mA, mB, mC = phase_fault_multipliers(fault_type)

    tau = np.maximum(t - t_event, 0.0)
    tau_rise = 0.0008 + 0.0003 * (3.0 / scr)
    tau_fall = 0.0035 + 0.0015 * (3.0 / scr)
    K = 0.08 + 0.04 * (3.0 / scr)

    def gfl_wave(mult):
        rise = (1.0 - np.exp(-tau / tau_rise))
        fall = np.exp(-tau / tau_fall)
        y = K * mult * rise * fall
        y[t < t_event] = 0.0
        return y

    ia = ia + np.sign(ia + 1e-12) * gfl_wave(mA)
    ib = ib + np.sign(ib + 1e-12) * gfl_wave(mB)
    ic = ic + np.sign(ic + 1e-12) * gfl_wave(mC)

    ia = add_small_ripple(t, ia, ripple_mag=0.0015, ripple_freq=180.0, phase=0.0)
    ib = add_small_ripple(t, ib, ripple_mag=0.0015, ripple_freq=180.0, phase=1.0)
    ic = add_small_ripple(t, ic, ripple_mag=0.0015, ripple_freq=180.0, phase=-1.0)

    ia = add_background_noise(ia, noise_std)
    ib = add_background_noise(ib, noise_std)
    ic = add_background_noise(ic, noise_std)

    params = {
        'tau_rise_s': tau_rise,
        'tau_fall_s': tau_fall,
        'K': K
    }
    return ia, ib, ic, params


# ============================================================
# Case builder
# ============================================================

def generate_case(
    family, fault_type, scr, noise_std,
    fs=10000, f0=50.0, t_start=5.98, t_end=6.04,
    t_event=6.0, base_mag=1.05
):
    t = np.arange(t_start, t_end, 1/fs)

    Va, Vb, Vc = voltage_fault_profile(t, t_event, fault_type, scr)
    Va = add_background_noise(add_small_ripple(t, Va, 0.0015, 160.0, 0.0), noise_std * 0.4)
    Vb = add_background_noise(add_small_ripple(t, Vb, 0.0015, 160.0, 0.7), noise_std * 0.4)
    Vc = add_background_noise(add_small_ripple(t, Vc, 0.0015, 160.0, -0.7), noise_std * 0.4)

    if family == 'induction_machine_like':
        Ia, Ib, Ic, params = induction_machine_family_current(
            t, t_event, f0, base_mag, fault_type, scr, noise_std
        )
    elif family == 'dfig_like':
        Ia, Ib, Ic, params = dfig_family_current(
            t, t_event, f0, base_mag, fault_type, scr, noise_std
        )
    elif family == 'full_converter_pmsg_like':
        Ia, Ib, Ic, params = full_converter_pmsg_family_current(
            t, t_event, f0, base_mag, fault_type, scr, noise_std
        )
    elif family == 'grid_following_inverter_like':
        Ia, Ib, Ic, params = grid_following_inverter_family_current(
            t, t_event, f0, base_mag, fault_type, scr, noise_std
        )
    else:
        raise ValueError(f"Unknown family: {family}")

    df = pd.DataFrame({
        'time_s': t,
        'Va_pu': Va,
        'Vb_pu': Vb,
        'Vc_pu': Vc,
        'Ia_pu': Ia,
        'Ib_pu': Ib,
        'Ic_pu': Ic
    })

    meta = {
        'family': family,
        'fault_type': fault_type,
        'scr': scr,
        'noise_std': noise_std,
        'fs_Hz': fs,
        'f0_Hz': f0,
        't_start_s': t_start,
        't_end_s': t_end,
        't_event_s': t_event,
        'base_mag_pu': base_mag
    }
    meta.update(params)

    return df, meta


# ============================================================
# Library generator
# ============================================================

def generate_synthetic_library(
    output_root='Z_Synthetic_Family_Library',
    n_repeats=6
):
    """
    Generates a moderately large benchmark library.

    Each case is a separate CSV.
    Metadata is collected into one library_metadata.csv.
    """
    waveform_dir = os.path.join(output_root, 'waveforms')
    metadata_dir = os.path.join(output_root, 'metadata')

    ensure_dir(waveform_dir)
    ensure_dir(metadata_dir)

    families = [
        'induction_machine_like',
        'dfig_like',
        'full_converter_pmsg_like',
        'grid_following_inverter_like'
    ]

    fault_types = [
        '3ph',
        'slg_a',
        'slg_b',
        'slg_c',
        'll_ab',
        'll_bc',
        'll_ca'
    ]

    scr_values = [2.0, 3.0, 5.0, 8.0]
    noise_values = [0.002, 0.005, 0.010]

    rows = []
    case_id = 0

    for family in families:
        for fault_type in fault_types:
            for scr in scr_values:
                for noise_std in noise_values:
                    for rep in range(n_repeats):
                        case_id += 1

                        # small randomization
                        t_event = 5.999 + rng.uniform(-0.0015, 0.0015)
                        base_mag = 1.00 + rng.uniform(0.00, 0.08)

                        df, meta = generate_case(
                            family=family,
                            fault_type=fault_type,
                            scr=scr,
                            noise_std=noise_std,
                            fs=10000,
                            f0=50.0,
                            t_start=5.98,
                            t_end=6.04,
                            t_event=t_event,
                            base_mag=base_mag
                        )

                        filename = f"case_{case_id:05d}_{family}_{fault_type}_scr{scr:.1f}_n{noise_std:.3f}_r{rep+1}.csv"
                        filepath = os.path.join(waveform_dir, filename)
                        df.to_csv(filepath, index=False)

                        meta_row = {
                            'case_id': case_id,
                            'filename': filename,
                            'filepath': os.path.abspath(filepath),
                            **meta
                        }
                        rows.append(meta_row)

    meta_df = pd.DataFrame(rows)

    meta_csv = os.path.join(metadata_dir, 'library_metadata.csv')
    meta_json = os.path.join(metadata_dir, 'library_metadata.json')

    meta_df.to_csv(meta_csv, index=False)

    with open(meta_json, 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2)

    print("SUCCESS: Synthetic waveform library generated.")
    print(f"Waveform folder : {os.path.abspath(waveform_dir)}")
    print(f"Metadata CSV    : {os.path.abspath(meta_csv)}")
    print(f"Metadata JSON   : {os.path.abspath(meta_json)}")
    print(f"Total cases     : {len(meta_df)}")

    return meta_df


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    generate_synthetic_library(
        output_root='Z_Synthetic_Family_Library',
        n_repeats=6
    )