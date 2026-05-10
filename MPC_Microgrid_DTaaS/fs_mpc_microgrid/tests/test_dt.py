"""Digital-twin layer unit tests."""

import numpy as np
import pytest

from fs_mpc_mg import Plant, PlantParams
from fs_mpc_mg.comm.pubsub import InMemoryPubSub
from fs_mpc_mg.comm.topics import topic_telemetry, topic_ref
from fs_mpc_mg.dt import (
    ShadowPlant, RLSIdentifier, AnomalyDetector, CyberScreen,
    QForecaster, MicrogridDigitalTwin, TwinConfig,
)
from fs_mpc_mg.dt.cyber_screen import CyberPolicy


# -----------------------------------------------------------------
# ShadowPlant
# -----------------------------------------------------------------
def test_shadow_residual_zero_on_perfect_replica():
    """If shadow uses identical params and same inputs, residuals should be tiny."""
    p_real = Plant(PlantParams())
    sp = ShadowPlant(PlantParams())
    sp.set_state(p_real.i_m, p_real.v_dc)
    s = np.array([1.0, 0.0, 0.0])
    v_s = np.array([310.0, -155.0, -155.0])
    dt = 100e-6
    p_real.step(s, v_s, i_dc=0.0, dt=dt)
    sp.step(s, v_s, dt=dt, i_dc=0.0, n_sub=1)
    res = sp.compute_residual(0.0, p_real.i_m, p_real.v_dc)
    assert res.i_m_residual_norm < 1e-6
    assert abs(res.v_dc_residual) < 1e-6


def test_shadow_residual_grows_when_params_drift():
    p_real = Plant(PlantParams(L=1e-3))
    sp = ShadowPlant(PlantParams(L=1.5e-3))   # +50% L drift
    sp.set_state(p_real.i_m, p_real.v_dc)
    s = np.array([1.0, 0.0, 0.0])
    v_s = np.array([310.0, -155.0, -155.0])
    for _ in range(50):
        p_real.step(s, v_s, i_dc=0.0, dt=20e-6)
        sp.step(s, v_s, dt=20e-6, i_dc=0.0, n_sub=1)
    res = sp.compute_residual(0.0, p_real.i_m, p_real.v_dc)
    assert res.i_m_residual_norm > 0.1


# -----------------------------------------------------------------
# RLSIdentifier
# -----------------------------------------------------------------
def test_rls_identifies_known_L_and_r():
    """Drive RLS with synthetic data from a known plant; estimates should converge."""
    L_true, r_true = 1e-3, 50e-3
    p = Plant(PlantParams(L=L_true, r=r_true))
    T_s = 20e-6
    rls = RLSIdentifier(T_s=T_s, init_L=2e-3, init_r=200e-3, min_samples=200)
    s = np.array([1.0, 0.0, 0.0])
    for k in range(2000):
        v_s = 310.0 * np.array([
            np.sin(2 * np.pi * 50.0 * k * T_s),
            np.sin(2 * np.pi * 50.0 * k * T_s - 2 * np.pi / 3),
            np.sin(2 * np.pi * 50.0 * k * T_s + 2 * np.pi / 3),
        ])
        i_m_now = p.i_m.copy()
        v_dc_now = p.v_dc
        p.step(s, v_s, i_dc=0.0, dt=T_s)
        rls.update(p.i_m, i_m_now, v_s, s, v_dc_now)
    res = rls.estimate
    assert res.converged
    assert abs(res.L - L_true) / L_true < 0.05    # within 5%
    assert abs(res.r - r_true) < 50e-3              # within 50 mΩ


# -----------------------------------------------------------------
# AnomalyDetector
# -----------------------------------------------------------------
def test_anomaly_calibration_then_alarm():
    det = AnomalyDetector("ica1", n_sigma=4.0, dwell_count=3, warmup_samples=30)
    # Calibration: small residuals
    for _ in range(100):
        evs = det.update(v_dc_residual=0.2, i_m_residual_norm=0.1, ts=0.0)
    assert evs == [], "no alarms during calibration"
    # Inject sudden large residual sustained for dwell_count ticks
    events = []
    for _ in range(5):
        events += det.update(v_dc_residual=50.0, i_m_residual_norm=0.1, ts=1.0)
    assert any(e.metric == "v_dc_residual" for e in events)


def test_anomaly_no_false_positive_during_warmup():
    det = AnomalyDetector("ica1", n_sigma=3.0, warmup_samples=200)
    # Even a wild value shouldn't fire during warmup
    for _ in range(50):
        evs = det.update(v_dc_residual=100.0, i_m_residual_norm=10.0, ts=0.0)
        assert evs == []


# -----------------------------------------------------------------
# CyberScreen
# -----------------------------------------------------------------
def test_cyber_v_dc_ref_bound_alert():
    cs = CyberScreen(CyberPolicy(v_dc_ref_min=700, v_dc_ref_max=1100))
    a = cs.inspect("ica1", "v_dc_ref", value=1500.0, ts=0.0)
    assert a is not None and a.rule == "v_dc_ref_bound"
    assert a.severity == "critical"


def test_cyber_v_dc_ref_slew_alert():
    cs = CyberScreen(CyberPolicy(v_dc_ref_max_slew=10.0))
    cs.inspect("ica1", "v_dc_ref", 900.0, ts=0.0)
    a = cs.inspect("ica1", "v_dc_ref", 1000.0, ts=0.5)  # slew = 200 V/s > 10
    assert a is not None and a.rule == "v_dc_ref_slew"


def test_cyber_Q_ref_ok_within_bounds():
    cs = CyberScreen()
    assert cs.inspect("ica1", "Q_ref", 5_000.0, ts=0.0) is None


def test_cyber_mode_chatter():
    cs = CyberScreen(CyberPolicy(mode_max_changes_per_window=2, mode_window_s=1.0))
    for k, mode in enumerate(["running", "fault", "running", "fault", "running"]):
        a = cs.inspect("ica1", "mode", mode, ts=0.1 * k)
    # The 4th change within 1 s should trigger
    assert a is not None and a.rule == "mode_chatter"


# -----------------------------------------------------------------
# QForecaster
# -----------------------------------------------------------------
def test_forecaster_returns_none_until_warmup():
    f = QForecaster(sample_period_s=1e-3)
    for k in range(3):
        f.push(k * 1e-3, [10.0, -5.0, -5.0])
    assert f.predict() is None


def test_forecaster_predicts_increasing_trend():
    f = QForecaster(sample_period_s=1e-3, horizon_s=0.1)
    for k in range(50):
        f.push(k * 1e-3, [10.0 + 0.5 * k, -5.0, -5.0])  # linearly growing
    pred = f.predict()
    assert pred is not None
    assert pred.trend_slope > 0
    assert pred.Q_total_predicted > pred.Q_total_now


# -----------------------------------------------------------------
# MicrogridDigitalTwin integration
# -----------------------------------------------------------------
def test_dt_subscribes_and_summarises():
    ps = InMemoryPubSub()
    twin = MicrogridDigitalTwin(["ica1"], ps, TwinConfig())
    # Push synthetic telemetry
    for k in range(10):
        ps.publish_value(topic_telemetry("ica1", "v_dc"), 900.0)
        ps.publish_value(topic_telemetry("ica1", "i_m_abc"), [1.0, -0.5, -0.5])
        ps.publish_value(topic_telemetry("ica1", "v_s_abc"), [310.0, -155.0, -155.0])
        ps.publish_value(topic_telemetry("ica1", "i_l_abc"), [50.0, -25.0, -25.0])
        ps.publish_value(topic_telemetry("ica1", "s_applied"), [1.0, 0.0, 0.0])
        twin.tick(t=k * 1e-3)
    s = twin.summary()
    assert s["n_ticks"] == 10
    assert "ica1" in s["rls"]


def test_dt_cyber_alert_published():
    ps = InMemoryPubSub()
    twin = MicrogridDigitalTwin(["ica1"], ps, TwinConfig())
    ps.publish_value(topic_ref("ica1", "Q_ref"), 1_000_000_000.0)   # spoof
    assert any(t.startswith("/dt/ica1/cyber_alert") for t, _ in ps.history())
