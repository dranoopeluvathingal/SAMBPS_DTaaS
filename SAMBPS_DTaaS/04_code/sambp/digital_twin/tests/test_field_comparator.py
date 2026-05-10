# =============================================================================
# tests/test_field_comparator.py
#
# Unit + integration tests for validation/field_comparator.py (TR-76 WP76.3)
#
# Uses the same synthetic COMTRADE generator as the 50-record dataset so that
# tests run in-process without touching disk-cached data.
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pytest

# Ensure digital_twin root is on the path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from digital_twin import DTEngine
from validation.comtrade_parser import ComtradeParser
from validation.field_comparator import (
    BatchComparisonReport,
    FieldComparisonReport,
    FieldComparator,
    _find_fault_onset,
    _find_fault_onset_current,
    _field_action,
    _field_element,
    _elements_match,
)
from data.synthetic_comtrade_generator import SyntheticComtradeGenerator


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def output_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("fc_records")


@pytest.fixture(scope="module")
def generator(output_dir):
    return SyntheticComtradeGenerator(output_dir=str(output_dir), seed=1234)


@pytest.fixture(scope="module")
def parser():
    return ComtradeParser()


@pytest.fixture(scope="module")
def engine():
    """Fresh DTEngine for each module run (reset per-record inside comparator)."""
    return DTEngine(estimator="ekf", n_scenarios=200)


@pytest.fixture(scope="module")
def comparator(engine, parser):
    return FieldComparator(engine, parser, dt_rate_hz=1000.0)


# ---------------------------------------------------------------------------
# Helper: generate a single record and return (cfg_path, metadata)
# ---------------------------------------------------------------------------

def _make_record(generator, fault_type="SLG", ibr_type="GFL",
                 k=0.40, scr=5.0, record_id=None):
    rid = record_id or f"test_{fault_type}_{ibr_type}"
    cfg, dat = generator.generate_fault_record(
        fault_type=fault_type,
        ibr_type=ibr_type,
        ibr_penetration=k,
        grid_strength=scr,
        record_id=rid,
    )
    return cfg, {"record_id": rid, "fault_type": fault_type, "ibr_type": ibr_type}


# ---------------------------------------------------------------------------
# test_single_replay
# ---------------------------------------------------------------------------

class TestSingleReplay:

    @pytest.mark.tier1
    def test_returns_field_comparison_report(self, generator, comparator):
        cfg, meta = _make_record(generator, "SLG", "GFL", k=0.40, scr=5.0,
                                 record_id="sr_slg_gfl")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert isinstance(rep, FieldComparisonReport)

    @pytest.mark.tier1
    def test_record_id_propagated(self, generator, comparator):
        cfg, meta = _make_record(generator, "3PH", "GFM", k=0.40, scr=5.0,
                                 record_id="sr_3ph_gfm")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert rep.record_id == "sr_3ph_gfm"

    @pytest.mark.tier1
    def test_fault_type_propagated(self, generator, comparator):
        cfg, meta = _make_record(generator, "LL", "PV", k=0.60, scr=3.0,
                                 record_id="sr_ll_pv")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert rep.fault_type == "LL"

    @pytest.mark.tier1
    def test_ibr_type_propagated(self, generator, comparator):
        cfg, meta = _make_record(generator, "DLG", "BESS", k=0.40, scr=5.0,
                                 record_id="sr_dlg_bess")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert rep.ibr_type == "BESS"

    @pytest.mark.tier1
    def test_field_decision_is_trip(self, generator, comparator):
        """Synthetic records always assert TRIP digital channel."""
        cfg, meta = _make_record(generator, "SLG", "GFL", k=0.50, scr=5.0,
                                 record_id="sr_trip_check")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert rep.field_decision == "TRIP"

    @pytest.mark.tier1
    def test_k_ibr_estimated_is_positive(self, generator, comparator):
        cfg, meta = _make_record(generator, "3PH", "GFL", k=0.60, scr=5.0,
                                 record_id="sr_kibr_pos")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert rep.k_ibr_estimated > 0.0

    @pytest.mark.tier1
    def test_dt_element_is_valid_label(self, generator, comparator):
        valid = {"87L", "Z1/87L", "OC", "MISS", "EXTERNAL", "UNKNOWN"}
        cfg, meta = _make_record(generator, "SLG", "GFM", k=0.40, scr=5.0,
                                 record_id="sr_elem_valid")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert rep.dt_element in valid, f"Unexpected element: {rep.dt_element!r}"

    @pytest.mark.tier1
    def test_dt_decision_is_valid_verdict(self, generator, comparator):
        valid_verdicts = {"AGREE", "FLAG_FP", "FLAG_FN", "FLAG_ELEMENT", "FLAG_CONF"}
        cfg, meta = _make_record(generator, "SLG", "GFL", k=0.40, scr=5.0,
                                 record_id="sr_verdict")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert rep.dt_decision in valid_verdicts

    @pytest.mark.tier1
    def test_agreement_is_bool(self, generator, comparator):
        cfg, meta = _make_record(generator, "SLG", "PV", k=0.50, scr=5.0,
                                 record_id="sr_bool_check")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert isinstance(rep.agreement, bool)

    @pytest.mark.tier1
    def test_field_element_from_digital_channels(self, generator, comparator):
        """Field element should be one of the known digital channel labels."""
        valid_elems = {"87L", "Z1/87L", "OC", "UNKNOWN"}
        cfg, meta = _make_record(generator, "3PH", "DFIG", k=0.40, scr=5.0,
                                 record_id="sr_dig_elem")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert rep.field_element in valid_elems


# ---------------------------------------------------------------------------
# test_batch_replay
# ---------------------------------------------------------------------------

class TestBatchReplay:

    @pytest.fixture(scope="class")
    def batch_report(self, generator, comparator, output_dir, tmp_path_factory):
        """Generate 8 records and replay them as a batch via YAML index."""
        import yaml

        records = [
            ("SLG",  "GFL",  0.40, 5.0),
            ("SLG",  "PV",   0.60, 3.0),
            ("LL",   "GFM",  0.40, 5.0),
            ("DLG",  "BESS", 0.40, 5.0),
            ("3PH",  "GFL",  0.60, 5.0),
            ("SLG",  "DFIG", 0.40, 5.0),
            ("LL",   "PV",   0.80, 3.0),
            ("3PH",  "GFM",  0.80, 3.0),
        ]

        index_entries = []
        for i, (ft, it, k, scr) in enumerate(records):
            rid = f"batch_{i:02d}_{ft}_{it}"
            cfg, dat = generator.generate_fault_record(
                fault_type=ft, ibr_type=it,
                ibr_penetration=k, grid_strength=scr,
                record_id=rid,
            )
            index_entries.append({
                "record_id":  rid,
                "fault_type": ft,
                "ibr_type":   it,
                "ibr_penetration_pct": k * 100,
                "scr":        scr,
                "cfg_path":   cfg,
                "dat_path":   dat,
                "source":     "synthetic",
            })

        idx_dir  = tmp_path_factory.mktemp("batch_idx")
        idx_file = idx_dir / "test_index.yaml"
        with idx_file.open("w") as fh:
            yaml.dump({"records": index_entries}, fh)

        return comparator.replay_batch(str(idx_file), base_dir=str(_ROOT))

    @pytest.mark.tier2
    def test_batch_total_records(self, batch_report):
        assert batch_report.total_records == 8

    @pytest.mark.tier2
    def test_batch_agree_count_nonneg(self, batch_report):
        assert batch_report.agree_count >= 0

    @pytest.mark.tier2
    def test_agree_rate_in_range(self, batch_report):
        assert 0.0 <= batch_report.agree_rate <= 1.0

    @pytest.mark.tier2
    def test_per_fault_type_keys_present(self, batch_report):
        expected = {"SLG", "LL", "DLG", "3PH"}
        assert expected.issubset(set(batch_report.per_fault_type))

    @pytest.mark.tier2
    def test_per_ibr_type_rates_valid(self, batch_report):
        for it, rate in batch_report.per_ibr_type.items():
            assert 0.0 <= rate <= 1.0, f"{it}: {rate}"

    @pytest.mark.tier2
    def test_element_match_rate_in_range(self, batch_report):
        assert 0.0 <= batch_report.element_match_rate <= 1.0

    @pytest.mark.tier2
    def test_to_dataframe_shape(self, batch_report):
        pytest.importorskip("pandas")
        df = batch_report.to_dataframe()
        assert df.shape == (8, 14)

    @pytest.mark.tier2
    def test_to_latex_table_contains_toprule(self, batch_report):
        latex = batch_report.to_latex_table()
        assert r"\toprule" in latex
        assert r"\bottomrule" in latex

    @pytest.mark.tier2
    def test_print_summary_no_exception(self, batch_report, capsys):
        batch_report.print_summary()
        captured = capsys.readouterr()
        assert "Batch Comparison Report" in captured.out


# ---------------------------------------------------------------------------
# test_time_alignment
# ---------------------------------------------------------------------------

class TestTimeAlignment:

    @pytest.mark.tier1
    def test_dt_trip_time_is_none_or_positive(self, generator, comparator):
        cfg, meta = _make_record(generator, "SLG", "GFL", k=0.50, scr=5.0,
                                 record_id="ta_trip_time")
        rep = comparator.replay_record(cfg, metadata=meta)
        if rep.dt_trip_time_ms is not None:
            assert rep.dt_trip_time_ms >= 0.0

    @pytest.mark.tier1
    def test_field_trip_time_nonneg(self, generator, comparator):
        cfg, meta = _make_record(generator, "3PH", "GFL", k=0.60, scr=5.0,
                                 record_id="ta_field_time")
        rep = comparator.replay_record(cfg, metadata=meta)
        if rep.field_trip_time_ms is not None:
            assert rep.field_trip_time_ms >= 0.0

    @pytest.mark.tier1
    def test_time_error_consistent(self, generator, comparator):
        """time_error = dt_trip_time - field_trip_time when both are not None."""
        cfg, meta = _make_record(generator, "SLG", "GFM", k=0.50, scr=5.0,
                                 record_id="ta_err_consistent")
        rep = comparator.replay_record(cfg, metadata=meta)
        if rep.dt_trip_time_ms is not None and rep.field_trip_time_ms is not None:
            expected_err = rep.dt_trip_time_ms - rep.field_trip_time_ms
            assert abs(rep.time_error_ms - expected_err) < 1e-6

    @pytest.mark.tier1
    def test_fault_onset_detector_returns_index(self):
        """_find_fault_onset: should return an int for a sagging waveform."""
        v = np.ones(200)
        v[80:] = 0.4                        # sag at sample 80
        idx = _find_fault_onset(v, threshold=0.80)
        assert idx is not None
        assert 78 <= idx <= 82

    @pytest.mark.tier1
    def test_fault_onset_none_for_flat_signal(self):
        """No fault onset for a steady 1.0 pu signal."""
        v = np.ones(200)
        idx = _find_fault_onset(v, threshold=0.80)
        assert idx is None

    @pytest.mark.tier1
    def test_fault_onset_ignores_single_spike(self):
        """Single sample below threshold must not trigger (requires 3 consecutive)."""
        v = np.ones(200)
        v[100] = 0.5                        # isolated single dip
        idx = _find_fault_onset(v, threshold=0.80)
        assert idx is None

    @pytest.mark.tier1
    def test_current_onset_detects_fault(self):
        """_find_fault_onset_current: detects step increase above threshold."""
        i = np.full(200, 0.14)              # pre-fault 0.14 pu
        i[80:] = 1.50                       # fault at sample 80
        idx = _find_fault_onset_current(i, threshold=0.30)
        assert idx is not None
        assert 78 <= idx <= 82

    @pytest.mark.tier1
    def test_current_onset_none_for_steady(self):
        """No onset for steady pre-fault current."""
        i = np.full(200, 0.14)
        idx = _find_fault_onset_current(i, threshold=0.30)
        assert idx is None


# ---------------------------------------------------------------------------
# test_agreement_classification
# ---------------------------------------------------------------------------

class TestAgreementClassification:

    @pytest.mark.tier1
    def test_elements_match_exact(self):
        assert _elements_match("87L", "87L") is True

    @pytest.mark.tier1
    def test_elements_match_same_family(self):
        """Z1/87L and 87L are in the 'line' family → match."""
        assert _elements_match("Z1/87L", "87L") is True

    @pytest.mark.tier1
    def test_elements_no_match_cross_family(self):
        assert _elements_match("87L", "OC") is False

    @pytest.mark.tier1
    def test_elements_match_both_block(self):
        assert _elements_match("MISS", "EXTERNAL") is True
        assert _elements_match("UNKNOWN", "MISS") is True

    @pytest.mark.tier1
    def test_field_action_detects_trip(self):
        """_field_action: TRIP digital channel asserts."""
        from validation.comtrade_parser import ComtradeRecord, ComtradeMetadata
        meta = ComtradeMetadata("S", "D", "2013", 50.0, "", "", "ASCII", 1)
        trip_ch = np.array([0, 0, 1, 1, 0])
        rec = ComtradeRecord(
            timestamps=np.arange(5, dtype=np.int64),
            analog_channels={},
            digital_channels={"TRIP": trip_ch},
            metadata=meta,
        )
        assert _field_action(rec) == "TRIP"

    @pytest.mark.tier1
    def test_field_action_detects_block(self):
        from validation.comtrade_parser import ComtradeRecord, ComtradeMetadata
        meta = ComtradeMetadata("S", "D", "2013", 50.0, "", "", "ASCII", 1)
        rec = ComtradeRecord(
            timestamps=np.arange(5, dtype=np.int64),
            analog_channels={},
            digital_channels={"TRIP": np.zeros(5, dtype=np.int32)},
            metadata=meta,
        )
        assert _field_action(rec) == "BLOCK"

    @pytest.mark.tier1
    def test_field_element_priority_87l_over_oc(self):
        """87L_OP takes priority over OC_OP."""
        from validation.comtrade_parser import ComtradeRecord, ComtradeMetadata
        meta = ComtradeMetadata("S", "D", "2013", 50.0, "", "", "ASCII", 1)
        rec = ComtradeRecord(
            timestamps=np.arange(5, dtype=np.int64),
            analog_channels={},
            digital_channels={
                "87L_OP": np.array([0, 0, 1, 1, 0]),
                "OC_OP":  np.array([0, 0, 1, 1, 0]),
            },
            metadata=meta,
        )
        assert _field_element(rec) == "87L"

    @pytest.mark.tier1
    def test_field_element_unknown_when_none_assert(self):
        from validation.comtrade_parser import ComtradeRecord, ComtradeMetadata
        meta = ComtradeMetadata("S", "D", "2013", 50.0, "", "", "ASCII", 1)
        rec = ComtradeRecord(
            timestamps=np.arange(5, dtype=np.int64),
            analog_channels={},
            digital_channels={
                "87L_OP": np.zeros(5, dtype=np.int32),
                "OC_OP":  np.zeros(5, dtype=np.int32),
            },
            metadata=meta,
        )
        assert _field_element(rec) == "UNKNOWN"

    @pytest.mark.tier2
    def test_high_ibr_penetration_tends_to_agree(self, generator, comparator):
        """At k=0.80 with 3PH fault, DT should detect TRIP — likely AGREE."""
        cfg, meta = _make_record(generator, "3PH", "GFL", k=0.80, scr=5.0,
                                 record_id="ac_high_k")
        rep = comparator.replay_record(cfg, metadata=meta)
        # DT must at least attempt to classify (not crash)
        assert rep.dt_decision is not None
        assert rep.k_ibr_estimated >= 0.0

    @pytest.mark.tier2
    def test_report_repr_contains_record_id(self, generator, comparator):
        cfg, meta = _make_record(generator, "SLG", "GFL", k=0.40, scr=5.0,
                                 record_id="repr_test_record")
        rep = comparator.replay_record(cfg, metadata=meta)
        assert "repr_test_record" in repr(rep)
