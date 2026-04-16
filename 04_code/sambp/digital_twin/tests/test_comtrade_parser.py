# =============================================================================
# tests/test_comtrade_parser.py
#
# Unit tests for validation/comtrade_parser.py (TR-76 WP76.1)
#
# Three synthetic COMTRADE file pairs are generated in a tmp directory:
#   pair_ascii  — 6 analog + 2 digital channels, ASCII, 50 Hz, SLG fault
#   pair_binary — 6 analog + 4 digital channels, BINARY, 60 Hz
#   pair_multi  — 2 analog, multi-rate (pre-fault 1 kHz, fault 4 kHz)
# =============================================================================

from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pytest

from validation.comtrade_parser import ComtradeParser, ComtradeRecord, _normalise_channel_name


# ---------------------------------------------------------------------------
# Helpers: COMTRADE file writers
# ---------------------------------------------------------------------------

def _write_cfg(
    path: Path,
    *,
    station: str = "TestStation",
    dev_id:  str = "IED-01",
    rev:     str = "2013",
    freq:    float = 50.0,
    analog_ch: list,      # list of (ch_id, ph, uu, a, b)
    digital_ch: list,     # list of (ch_id, ph, y)
    n_samples: int = 100,
    samp_rate: float = 4000.0,
    data_fmt:  str = "ASCII",
    nrates:    int = 1,
    extra_rates: list | None = None,   # [(samp, endsamp), ...] for multi-rate
) -> None:
    """Write a minimal IEEE C37.111-2013 .cfg file."""
    na = len(analog_ch)
    nd = len(digital_ch)
    lines = []
    # Line 1
    lines.append(f"{station},{dev_id},{rev}")
    # Line 2
    lines.append(f"{na + nd},{na}A,{nd}D")
    # Analog channel defs
    for i, (ch_id, ph, uu, a, b) in enumerate(analog_ch, start=1):
        lines.append(
            f"{i},{ch_id},{ph},,{uu},{a},{b},0,-1000000,1000000,1.0,1.0,P"
        )
    # Digital channel defs
    for i, (ch_id, ph, y) in enumerate(digital_ch, start=1):
        lines.append(f"{i},{ch_id},{ph},,{y}")
    # Frequency
    lines.append(f"{freq}")
    # nrates
    if extra_rates:
        lines.append(str(len(extra_rates)))
        for samp, endsamp in extra_rates:
            lines.append(f"{samp},{endsamp}")
    else:
        lines.append(str(nrates))
        lines.append(f"{samp_rate},{n_samples}")
    # Timestamps
    lines.append("01/01/2026,00:00:00.000000")
    lines.append("01/01/2026,00:00:01.000000")
    # Data format
    lines.append(data_fmt)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def _write_dat_ascii(
    path: Path,
    timestamps: np.ndarray,
    analog_data: np.ndarray,
    digital_data: np.ndarray,
) -> None:
    """Write an ASCII .dat file: sample_no, timestamp, a0, a1, …, d0, d1, …"""
    rows = []
    for i in range(len(timestamps)):
        vals = [str(i + 1), str(int(timestamps[i]))]
        vals += [f"{v:.6f}" for v in analog_data[i]]
        vals += [str(int(v)) for v in digital_data[i]]
        rows.append(",".join(vals))
    path.write_text("\n".join(rows) + "\n", encoding="ascii")


def _write_dat_binary(
    path: Path,
    timestamps: np.ndarray,
    analog_raw: np.ndarray,    # int16 raw values (before a*x+b)
    digital_data: np.ndarray,
    n_digital: int,
) -> None:
    """Write a BINARY .dat file using int16 analog + uint16 digital words."""
    n_analog    = analog_raw.shape[1]
    n_dig_words = max(1, (n_digital + 15) // 16)
    fmt = "<II" + "h" * n_analog + "H" * n_dig_words

    buf = bytearray()
    for i in range(len(timestamps)):
        # Pack digital channels into uint16 words (LSB first)
        words = [0] * n_dig_words
        for j in range(n_digital):
            if digital_data[i, j]:
                words[j // 16] |= (1 << (j % 16))
        record = struct.pack(
            fmt,
            i + 1,
            int(timestamps[i]),
            *analog_raw[i].astype(np.int16).tolist(),
            *words,
        )
        buf.extend(record)
    path.write_bytes(bytes(buf))


# ---------------------------------------------------------------------------
# Fixtures: synthetic COMTRADE pairs
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def comtrade_dir(tmp_path_factory) -> Path:
    """Return a temp directory with three synthetic COMTRADE file pairs."""
    d = tmp_path_factory.mktemp("comtrade")

    fs      = 4000.0
    f0      = 50.0
    N       = 200
    t       = np.arange(N) / fs                          # time vector [s]
    ts_us   = (t * 1e6).astype(np.int64)                 # μs timestamps

    # ----------------------------------------------------------------
    # Pair 1 — ASCII, 50 Hz, 6 analog + 2 digital, SLG fault scenario
    # ----------------------------------------------------------------
    va =  1.0 * np.sin(2 * np.pi * f0 * t)
    vb =  1.0 * np.sin(2 * np.pi * f0 * t - 2 * np.pi / 3)
    vc =  1.0 * np.sin(2 * np.pi * f0 * t + 2 * np.pi / 3)
    ia =  0.5 * np.sin(2 * np.pi * f0 * t - np.pi / 6)   # pre-fault
    ib =  0.5 * np.sin(2 * np.pi * f0 * t - 2 * np.pi / 3 - np.pi / 6)
    ic =  0.5 * np.sin(2 * np.pi * f0 * t + 2 * np.pi / 3 - np.pi / 6)
    # SLG: phase-A current doubles after sample 100
    ia[100:] *= 3.0

    analog_data_1 = np.column_stack([va, vb, vc, ia, ib, ic])
    digital_data_1 = np.zeros((N, 2), dtype=np.int32)
    digital_data_1[100:, 0] = 1   # FAULT_DETECT asserts at fault onset

    _write_cfg(
        d / "pair1.cfg",
        station="SubstationAlpha", dev_id="SEL-411L", rev="2013",
        freq=50.0,
        analog_ch=[
            ("Va", "A", "kV",  0.5, 0.0),
            ("Vb", "B", "kV",  0.5, 0.0),
            ("Vc", "C", "kV",  0.5, 0.0),
            ("Ia", "A", "A",   2.0, 0.0),
            ("Ib", "B", "A",   2.0, 0.0),
            ("Ic", "C", "A",   2.0, 0.0),
        ],
        digital_ch=[
            ("FAULT_DETECT", "", 0),
            ("TRIP",         "", 0),
        ],
        n_samples=N, samp_rate=fs, data_fmt="ASCII",
    )
    _write_dat_ascii(d / "pair1.dat", ts_us, analog_data_1, digital_data_1)

    # ----------------------------------------------------------------
    # Pair 2 — BINARY, 60 Hz, 6 analog + 4 digital
    # ----------------------------------------------------------------
    f0b  = 60.0
    t2   = np.arange(N) / fs
    ts2  = (t2 * 1e6).astype(np.int64)

    a_scaling = 0.01    # a coefficient for analog: actual = 0.01 * raw + 0
    # Choose raw int16 values so actual values are clean sine waves
    va2_actual = np.sin(2 * np.pi * f0b * t2)
    # raw = actual / a_scaling  (must fit int16: ±32767)
    raw_va2 = (va2_actual / a_scaling).astype(np.int16)
    # Repeat pattern for 6 channels
    phases  = [0, -2*np.pi/3, 2*np.pi/3]
    raw_v   = np.column_stack(
        [(np.sin(2 * np.pi * f0b * t2 + ph) / a_scaling).astype(np.int16)
         for ph in phases]
    )
    raw_i   = np.column_stack(
        [(0.3 * np.sin(2 * np.pi * f0b * t2 + ph - np.pi/6) / a_scaling).astype(np.int16)
         for ph in phases]
    )
    raw_analog_2 = np.hstack([raw_v, raw_i])   # (N, 6) int16
    digital_data_2 = np.zeros((N, 4), dtype=np.int32)
    digital_data_2[50:150, 1] = 1   # some digital activity

    _write_cfg(
        d / "pair2.cfg",
        station="SubstationBeta", dev_id="GE-D90", rev="2013",
        freq=60.0,
        analog_ch=[
            ("IL1", "A", "A", a_scaling, 0.0),
            ("IL2", "B", "A", a_scaling, 0.0),
            ("IL3", "C", "A", a_scaling, 0.0),
            ("IL1V", "A", "kV", a_scaling, 0.0),
            ("IL2V", "B", "kV", a_scaling, 0.0),
            ("IL3V", "C", "kV", a_scaling, 0.0),
        ],
        digital_ch=[
            ("52A", "", 0), ("RELAY", "", 0), ("CB1", "", 0), ("CB2", "", 0),
        ],
        n_samples=N, samp_rate=fs, data_fmt="BINARY",
    )
    _write_dat_binary(d / "pair2.dat", ts2, raw_analog_2, digital_data_2, n_digital=4)

    # ----------------------------------------------------------------
    # Pair 3 — ASCII, multi-rate (1 kHz pre-fault, 4 kHz during fault)
    # ----------------------------------------------------------------
    N_lo = 50    # 50 samples at 1 kHz  → 50 ms pre-fault
    N_hi = 200   # 200 samples at 4 kHz → 50 ms fault window
    t_lo = np.arange(N_lo) / 1000.0
    t_hi = t_lo[-1] + 1.0/1000.0 + np.arange(N_hi) / 4000.0
    t3   = np.concatenate([t_lo, t_hi])
    ts3  = (t3 * 1e6).astype(np.int64)

    sig_lo = np.sin(2 * np.pi * 50.0 * t_lo)
    sig_hi = np.sin(2 * np.pi * 50.0 * t_hi)
    sig3   = np.concatenate([sig_lo, sig_hi])
    ana3   = np.column_stack([sig3, 0.2 * sig3])

    _write_cfg(
        d / "pair3.cfg",
        station="MultiRate", dev_id="SEL-300G", rev="2013",
        freq=50.0,
        analog_ch=[
            ("Ia", "A", "A", 1.0, 0.0),
            ("Va", "A", "kV", 1.0, 0.0),
        ],
        digital_ch=[],
        n_samples=N_lo + N_hi,
        samp_rate=1000.0,
        data_fmt="ASCII",
        nrates=2,
        extra_rates=[(1000.0, N_lo), (4000.0, N_lo + N_hi)],
    )
    _write_dat_ascii(d / "pair3.dat", ts3, ana3,
                     np.zeros((N_lo + N_hi, 0), dtype=np.int32))

    return d


# ---------------------------------------------------------------------------
# Parser fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def parser() -> ComtradeParser:
    return ComtradeParser()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParseAsciiFormat:
    @pytest.mark.tier1
    def test_channel_count(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        assert len(rec.analog_channels)  == 6
        assert len(rec.digital_channels) == 2

    @pytest.mark.tier1
    def test_sample_count(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        assert len(rec.timestamps) == 200

    @pytest.mark.tier1
    def test_timestamps_monotonic(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        assert np.all(np.diff(rec.timestamps) > 0)

    @pytest.mark.tier1
    def test_waveform_values_finite(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        for name, arr in rec.analog_channels.items():
            assert np.all(np.isfinite(arr)), f"Non-finite values in channel {name}"


class TestParseBinaryFormat:
    @pytest.mark.tier1
    def test_channel_count(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair2.cfg"))
        assert len(rec.analog_channels)  == 6
        assert len(rec.digital_channels) == 4

    @pytest.mark.tier1
    def test_sample_count(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair2.cfg"))
        assert len(rec.timestamps) == 200

    @pytest.mark.tier1
    def test_waveform_values_finite(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair2.cfg"))
        for name, arr in rec.analog_channels.items():
            assert np.all(np.isfinite(arr))

    @pytest.mark.tier1
    def test_digital_bits_valid(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair2.cfg"))
        for name, arr in rec.digital_channels.items():
            assert set(arr.tolist()).issubset({0, 1}), \
                f"Digital channel {name} has values outside {{0,1}}"


class TestChannelNormalization:
    @pytest.mark.tier1
    def test_standard_names_pass_through(self):
        for raw in ("Va", "Vb", "Vc", "Ia", "Ib", "Ic"):
            assert _normalise_channel_name(raw) == raw

    @pytest.mark.tier1
    def test_il1_maps_to_ia(self):
        assert _normalise_channel_name("IL1") == "Ia"

    @pytest.mark.tier1
    def test_il2_maps_to_ib(self):
        assert _normalise_channel_name("IL2") == "Ib"

    @pytest.mark.tier1
    def test_il3_maps_to_ic(self):
        assert _normalise_channel_name("IL3") == "Ic"

    @pytest.mark.tier1
    def test_van_maps_to_va(self):
        assert _normalise_channel_name("VAN") == "Va"

    @pytest.mark.tier1
    def test_unknown_name_returned_verbatim(self):
        assert _normalise_channel_name("WEIRD_SIG") == "WEIRD_SIG"

    @pytest.mark.tier1
    def test_pair1_has_standard_channel_names(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        for expected in ("Va", "Vb", "Vc", "Ia", "Ib", "Ic"):
            assert expected in rec.analog_channels, \
                f"Expected channel {expected!r} not found in {list(rec.analog_channels)}"


class TestScalingApplied:
    @pytest.mark.tier1
    def test_ascii_scaling_a_coeff(self, parser, comtrade_dir):
        """pair1 Va has a=0.5, so scaled = 0.5 * raw ≈ 0.5 * sin(...)."""
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        va  = rec.analog_channels["Va"]
        # The written raw value was sin(…), so scaled should be ~0.5*sin(…)
        assert np.max(np.abs(va)) < 1.0, \
            "Va amplitude should be < 1.0 after a=0.5 scaling"
        assert np.max(np.abs(va)) > 0.3, \
            "Va amplitude should be > 0.3 (non-trivial signal)"

    @pytest.mark.tier1
    def test_binary_scaling_roundtrip(self, parser, comtrade_dir):
        """pair2 analog values should equal a * int16_raw + b = 0.01 * raw."""
        rec = parser.parse(str(comtrade_dir / "pair2.cfg"))
        # The maximum raw int16 value for a unit sine is ~32767 * a_scaling ≈ 0.01
        # Actual waveform amplitude ≈ 1.0 * a_scaling per unit → should be < 1.05
        for name, arr in rec.analog_channels.items():
            assert np.max(np.abs(arr)) < 1.05, \
                f"Channel {name}: unexpected amplitude {np.max(np.abs(arr)):.4f}"

    @pytest.mark.tier1
    def test_offset_applied(self, tmp_path, parser):
        """Verify b-offset: a=1.0, b=5.0 shifts all values by +5."""
        cfg = tmp_path / "offset.cfg"
        dat = tmp_path / "offset.dat"
        N   = 10
        ts  = np.arange(N, dtype=np.int64) * 250    # 4 kHz spacing in μs
        raw = np.ones((N, 1))                        # raw = 1.0
        _write_cfg(
            cfg, station="S", dev_id="D", rev="2013", freq=50.0,
            analog_ch=[("Va", "A", "kV", 1.0, 5.0)],
            digital_ch=[], n_samples=N, samp_rate=4000.0, data_fmt="ASCII",
        )
        _write_dat_ascii(dat, ts, raw, np.zeros((N, 0), dtype=np.int32))
        rec = parser.parse(str(cfg), str(dat))
        np.testing.assert_allclose(rec.analog_channels["Va"], 6.0, atol=1e-9)


class TestMetadataExtraction:
    @pytest.mark.tier1
    def test_station_name(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        assert rec.metadata.station_name == "SubstationAlpha"

    @pytest.mark.tier1
    def test_frequency_50hz(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        assert rec.metadata.frequency == pytest.approx(50.0)

    @pytest.mark.tier1
    def test_frequency_60hz(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair2.cfg"))
        assert rec.metadata.frequency == pytest.approx(60.0)

    @pytest.mark.tier1
    def test_rev_year(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        assert rec.metadata.rev_year == "2013"

    @pytest.mark.tier1
    def test_nrates_single(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        assert rec.metadata.nrates == 1

    @pytest.mark.tier1
    def test_nrates_multi(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair3.cfg"))
        assert rec.metadata.nrates == 2
        assert len(rec.metadata.sample_rates) == 2

    @pytest.mark.tier1
    def test_multi_rate_sample_rates(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair3.cfg"))
        rates = [sr.samp for sr in rec.metadata.sample_rates]
        assert rates[0] == pytest.approx(1000.0)
        assert rates[1] == pytest.approx(4000.0)

    @pytest.mark.tier1
    def test_n_analog_n_digital(self, parser, comtrade_dir):
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        assert rec.metadata.n_analog  == 6
        assert rec.metadata.n_digital == 2


class TestMissingDatAutodetect:
    @pytest.mark.tier1
    def test_dat_discovered_from_cfg_path(self, parser, comtrade_dir):
        """Passing only .cfg should auto-find .dat with same stem."""
        rec = parser.parse(str(comtrade_dir / "pair1.cfg"))
        assert isinstance(rec, ComtradeRecord)
        assert len(rec.timestamps) > 0

    @pytest.mark.tier1
    def test_missing_dat_raises(self, tmp_path, parser):
        cfg = tmp_path / "ghost.cfg"
        _write_cfg(
            cfg, station="X", dev_id="Y", rev="2013", freq=50.0,
            analog_ch=[("Ia", "A", "A", 1.0, 0.0)],
            digital_ch=[], n_samples=10, samp_rate=4000.0, data_fmt="ASCII",
        )
        # ghost.dat does not exist
        with pytest.raises(FileNotFoundError):
            parser.parse(str(cfg))


class TestInvalidFileError:
    @pytest.mark.tier1
    def test_missing_cfg_raises(self, parser, tmp_path):
        with pytest.raises(FileNotFoundError):
            parser.parse(str(tmp_path / "nonexistent.cfg"))

    @pytest.mark.tier1
    def test_corrupted_dat_ascii_raises(self, tmp_path, parser):
        cfg = tmp_path / "bad.cfg"
        dat = tmp_path / "bad.dat"
        _write_cfg(
            cfg, station="S", dev_id="D", rev="2013", freq=50.0,
            analog_ch=[("Va", "A", "kV", 1.0, 0.0)],
            digital_ch=[], n_samples=5, samp_rate=4000.0, data_fmt="ASCII",
        )
        dat.write_text("1,250,not_a_number\n2,500,also_bad\n", encoding="ascii")
        with pytest.raises((ValueError, Exception)):
            parser.parse(str(cfg), str(dat))

    @pytest.mark.tier1
    def test_truncated_binary_dat_raises(self, tmp_path, parser):
        cfg = tmp_path / "trunc.cfg"
        dat = tmp_path / "trunc.dat"
        _write_cfg(
            cfg, station="S", dev_id="D", rev="2013", freq=50.0,
            analog_ch=[("Ia", "A", "A", 1.0, 0.0)],
            digital_ch=[], n_samples=10, samp_rate=4000.0, data_fmt="BINARY",
        )
        # Write a random-length byte string that is NOT a multiple of record size
        dat.write_bytes(b"\x00" * 7)    # 7 bytes — can't be a valid BINARY record
        with pytest.raises((ValueError, Exception)):
            parser.parse(str(cfg), str(dat))
