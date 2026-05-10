"""
Upgraded synthetic family-labelled waveform library generator
with stronger DFIG crowbar/FRT signature and more distinct
full-converter PMSG controller signature.

Generates labelled cases for:
    - induction_machine_like
    - dfig_like
    - full_converter_pmsg_like
    - grid_following_inverter_like

Each waveform file contains:
    time_s, Va_pu, Vb_pu, Vc_pu, Ia_pu, Ib_pu, Ic_pu

Outputs:
    - waveform CSV files
    - library metadata CSV / JSON
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
# Utilities
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


def logistic_gate(x, x0, sharpness):
    return 1.0 / (1.0 + np.exp(-(x - x0) / sharpness))


def phase_fault_multipliers(fault_type):
    if fault_type == '3ph':
        return (1.00, 1.00, 1.00)
    elif fault_type == 'slg_a':
        return (1.40, 0.92, 0.92)
    elif fault_type == 'slg_b':
        return (0.92, 1.40, 0.92)
    elif fault_type == 'slg_c':
        return (0.92, 0.92, 1.40)
    elif fault_type == 'll_ab':
        return (1.22, 1.22, 0.88)
    elif fault_type == 'll_bc':
        return (0.88, 1.22, 1.22)
    elif fault_type == 'll_ca':
        return (1.22, 0.88, 1.22)
    else:
        return (1.00, 1.00, 1.00)


def voltage_fault_profile(t, t_event, fault_type, scr):
    """
    Synthetic voltage dip profile.
    Lower SCR -> deeper and slower recovery.
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

    scr_factor = np.clip(3.0 / scr, 0.4, 1.8)
    depth = np.clip(depth_base * scr_factor, 0.08, 0.80)

    mA, mB, mC = phase_fault_multipliers(fault_type)
    mmax = max(mA, mB, mC)

    tau = np.maximum(t - t_event, 0.0)
    dip = np.exp(-tau / (0.010 + 0.004 * (3.0 / scr)))
    dip[t < t_event] = 0.0

    Va_out = Va * (1.0 - depth * (mA / mmax) * dip)
    Vb_out = Vb * (1.0 - depth * (mB / mmax) * dip)
    Vc_out = Vc * (1.0 - depth * (mC / mmax) * dip)

    return Va_out, Vb_out, Vc_out, depth


def calc_voltage_magnitude_envelope(Va, Vb, Vc):
    vmag = np.sqrt((Va**2 + Vb**2 + Vc**2) / 3.0)
    return vmag


# ============================================================
# Family-specific current generators
# ============================================================

def induction_machine_family_current(
    t, t_event, f0, base_mag, fault_type, scr, noise_std
):
    """
    Machine-like oscillatory transient on all phases.
    """
    ia, ib, ic = three_phase_base(t, f=f0, mag=base_mag)
    mA, mB, mC = phase_fault_multipliers(fault_type)

    tau = np.maximum(t - t_event, 0.0)

    tau_d = 0.004 + 0.004 * (3.0 / scr)
    f_tr = 700 + 220 * (scr / 3.0)
    K0 = 0.18 + 0.10 * (3.0 / scr)

    trA = K0 * mA * np.exp(-tau / tau_d) * np.sin(2*np.pi*f_tr*tau + 0.10)
    trB = K0 * mB * np.exp(-tau / tau_d) * np.sin(2*np.pi*f_tr*tau - 0.75)
    trC = K0 * mC * np.exp(-tau / tau_d) * np.sin(2*np.pi*f_tr*tau + 0.55)

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


def dfig_family_current_v2(
    t, t_event, f0, base_mag, fault_type, scr, noise_std, Va, Vb, Vc
):
    """
    Stronger DFIG signature:
      - early induction-like oscillatory burst
      - explicit crowbar/FRT transition
      - post-crowbar current-limited tail
      - change in oscillatory richness after gate time
    """
    ia, ib, ic = three_phase_base(t, f=f0, mag=base_mag)
    mA, mB, mC = phase_fault_multipliers(fault_type)

    tau = np.maximum(t - t_event, 0.0)
    vmag = calc_voltage_magnitude_envelope(Va, Vb, Vc)

    # Early machine-like part
    tau1 = 0.0018 + 0.0012 * (3.0 / scr)
    f1 = 1250 + 250 * (scr / 3.0)
    K1 = 0.24 + 0.14 * (3.0 / scr)

    # Crowbar/FRT transition
    tg = 0.0028 + 0.0012 * (3.0 / scr) + rng.uniform(-0.0003, 0.0003)
    g_early = 1.0 - logistic_gate(tau, tg, 0.00018)
    g_late = 1.0 - g_early

    # Post-crowbar/current-limited tail
    tau2 = 0.008 + 0.004 * (3.0 / scr)
    K2 = 0.10 + 0.05 * (3.0 / scr)

    # Voltage-dependent current support after crowbar/FRT
    vdef = np.clip(1.0 - vmag, 0.0, 1.0)
    support = 0.7 + 1.4 * vdef

    def dfig_wave(mult, phase):
        early = K1 * mult * np.exp(-tau / tau1) * np.sin(2*np.pi*f1*tau + phase)

        # late current-limited tail with weak residual oscillation
        late_dc = K2 * mult * support * np.exp(-tau / tau2)
        late_osc = 0.18 * K2 * mult * np.exp(-tau / (0.7 * tau2)) * np.sin(2*np.pi*240*tau + 0.2*phase)

        y = g_early * early + g_late * (late_dc + late_osc)
        y[t < t_event] = 0.0
        return y

    ia = ia + dfig_wave(mA, 0.00)
    ib = ib + dfig_wave(mB, -0.95)
    ic = ic + dfig_wave(mC, 0.65)

    # weak controller ripple after gate time
    post_gate = logistic_gate(tau, tg + 0.0004, 0.00025)
    ia += post_gate * 0.0028 * np.sin(2*np.pi*220*tau + 0.4)
    ib += post_gate * 0.0028 * np.sin(2*np.pi*220*tau + 1.0)
    ic += post_gate * 0.0028 * np.sin(2*np.pi*220*tau - 0.6)

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


def full_converter_pmsg_family_current_v2(
    t, t_event, f0, base_mag, fault_type, scr, noise_std, Va, Vb, Vc
):
    """
    More distinct PMSG full-converter signature:
      - smooth controller-shaped bounded oscillatory response
      - slower governed recovery than GFL
      - voltage-dependent modulation
      - more oscillatory than GFL, less hybrid than DFIG
    """
    ia, ib, ic = three_phase_base(t, f=f0, mag=base_mag)
    mA, mB, mC = phase_fault_multipliers(fault_type)

    tau = np.maximum(t - t_event, 0.0)
    vmag = calc_voltage_magnitude_envelope(Va, Vb, Vc)
    vdef = np.clip(1.0 - vmag, 0.0, 1.0)

    tau_rise = 0.0012 + 0.0005 * (3.0 / scr)
    tau_fall = 0.0065 + 0.0030 * (3.0 / scr)
    f_ctrl = 420 + 120 * (scr / 3.0)
    K = 0.11 + 0.05 * (3.0 / scr)

    # bounded support modulated by voltage depression
    support = 0.75 + 1.2 * vdef

    def pmsg_wave(mult, phase):
        rise = (1.0 - np.exp(-tau / tau_rise))
        fall = np.exp(-tau / tau_fall)

        # controlled oscillatory component
        ctrl_osc = K * mult * support * rise * fall * np.sin(2*np.pi*f_ctrl*tau + phase)

        # gentle nonoscillatory control envelope
        ctrl_env = 0.35 * K * mult * support * rise * np.exp(-tau / (1.2 * tau_fall))

        y = ctrl_osc + ctrl_env
        y[t < t_event] = 0.0
        return y

    ia = ia + pmsg_wave(mA, 0.15)
    ib = ib + pmsg_wave(mB, -0.70)
    ic = ic + pmsg_wave(mC, 0.85)

    # distinct controller ripple, weaker than DFIG early burst but stronger than GFL
    ia += 0.0022 * np.sin(2*np.pi*310*tau + 0.1) * np.exp(-tau / 0.010) * (tau >= 0)
    ib += 0.0022 * np.sin(2*np.pi*310*tau + 0.8) * np.exp(-tau / 0.010) * (tau >= 0)
    ic += 0.0022 * np.sin(2*np.pi*310*tau - 0.7) * np.exp(-tau / 0.010) * (tau >= 0)

    ia[t < t_event] = three_phase_base(t, f=f0, mag=base_mag)[0][t < t_event]
    ib[t < t_event] = three_phase_base(t, f=f0, mag=base_mag)[1][t < t_event]
    ic[t < t_event] = three_phase_base(t, f=f0, mag=base_mag)[2][t < t_event]

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
    Keep this simpler than PMSG.
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

    ia = add_small_ripple(t, ia, ripple_mag=0.0014, ripple_freq=170.0, phase=0.0)
    ib = add_small_ripple(t, ib, ripple_mag=0.0014, ripple_freq=170.0, phase=1.0)
    ic = add_small_ripple(t, ic, ripple_mag=0.0014, ripple_freq=170.0, phase=-1.0)

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

    Va, Vb, Vc, depth = voltage_fault_profile(t, t_event, fault_type, scr)
    Va = add_background_noise(add_small_ripple(t, Va, 0.0015, 160.0, 0.0), noise_std * 0.4)
    Vb = add_background_noise(add_small_ripple(t, Vb, 0.0015, 160.0, 0.7), noise_std * 0.4)
    Vc = add_background_noise(add_small_ripple(t, Vc, 0.0015, 160.0, -0.7), noise_std * 0.4)

    if family == 'induction_machine_like':
        Ia, Ib, Ic, params = induction_machine_family_current(
            t, t_event, f0, base_mag, fault_type, scr, noise_std
        )
    elif family == 'dfig_like':
        Ia, Ib, Ic, params = dfig_family_current_v2(
            t, t_event, f0, base_mag, fault_type, scr, noise_std, Va, Vb, Vc
        )
    elif family == 'full_converter_pmsg_like':
        Ia, Ib, Ic, params = full_converter_pmsg_family_current_v2(
            t, t_event, f0, base_mag, fault_type, scr, noise_std, Va, Vb, Vc
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
        'base_mag_pu': base_mag,
        'voltage_dip_depth': depth
    }
    meta.update(params)

    return df, meta


# ============================================================
# Library generator
# ============================================================

def generate_synthetic_library_v2(
    output_root='Z_Synthetic_Family_Library_v2',
    n_repeats=6
):
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

                        filename = (
                            f"case_{case_id:05d}_{family}_{fault_type}_"
                            f"scr{scr:.1f}_n{noise_std:.3f}_r{rep+1}.csv"
                        )
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

    print("SUCCESS: Upgraded synthetic waveform library generated.")
    print(f"Waveform folder : {os.path.abspath(waveform_dir)}")
    print(f"Metadata CSV    : {os.path.abspath(meta_csv)}")
    print(f"Metadata JSON   : {os.path.abspath(meta_json)}")
    print(f"Total cases     : {len(meta_df)}")

    return meta_df


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    generate_synthetic_library_v2(
        output_root='Z_Synthetic_Family_Library_v2',
        n_repeats=6
    )