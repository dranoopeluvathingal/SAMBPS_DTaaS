"""Dashboard report unit tests."""

from fs_mpc_mg.dashboard import Report, build_report


def test_report_renders_minimal_html():
    r = build_report(
        title="Test",
        sim_t_end_s=0.01,
        fleet_ica_ids=["ica1"],
        pubsub_history=[
            ("/ica/ica1/tel/v_dc", {"value": 900.0, "ts": 0.001}),
            ("/ica/ica1/tel/v_dc", {"value": 901.0, "ts": 0.002}),
        ],
    )
    html = r.render()
    assert "<!doctype html>" in html
    assert "ica1" in html
    assert "v_dc" in html  # alt text or label
    assert "__PAYLOAD_JSON__" not in html  # token replaced


def test_report_handles_empty_inputs():
    r = build_report(title="Empty", sim_t_end_s=0.0,
                     fleet_ica_ids=[], pubsub_history=[])
    html = r.render()
    assert "<!doctype html>" in html
    assert "Empty" in html


def test_report_alerts_in_table():
    r = build_report(
        title="Alerts test", sim_t_end_s=0.05,
        fleet_ica_ids=["ica1"],
        pubsub_history=[
            ("/dt/ica1/anomaly", {"value": {"severity": "warning",
                                            "reason": "test fault"}, "ts": 0.02}),
        ],
    )
    html = r.render()
    # Alert payload must be embedded as JSON inside the script
    assert "test fault" in html
