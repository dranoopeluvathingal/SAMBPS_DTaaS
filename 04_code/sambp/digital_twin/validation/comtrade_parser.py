# =============================================================================
# sambp / digital_twin / validation / comtrade_parser.py
#
# COMTRADE parser — IEEE C37.111-2013 (ASCII and BINARY formats).
#
# Design
# ------
# ComtradeParser.parse() reads a .cfg file and its companion .dat file,
# returning a ComtradeRecord that holds:
#   - timestamps  : μs from trigger, shape (N,)  [int64, microseconds]
#   - analog_channels  : {name: ndarray shape (N,)} after a*raw+b scaling
#   - digital_channels : {name: ndarray shape (N,)} values 0 or 1
#   - metadata    : ComtradeMetadata (station, frequency, rates, …)
#
# Channel-name normalisation
# --------------------------
# Vendor-specific names are mapped to standard phase labels before being
# stored.  The mapping covers common IED naming conventions (see
# VENDOR_CHANNEL_MAP at the bottom of this file).
#
# Scaling
# -------
# Per IEEE C37.111-2013 §5.4.4:
#   actual_value = a * raw_value + b
# The coefficients are read from the .cfg analog-channel lines.
#
# Public API
# ----------
# parser = ComtradeParser()
# record = parser.parse("event.cfg")                 # .dat auto-detected
# record = parser.parse("event.cfg", "event.dat")   # explicit .dat path
#
# record.timestamps          # ndarray int64 [μs]
# record.analog_channels     # dict[str, ndarray float64]
# record.digital_channels    # dict[str, ndarray uint8]
# record.metadata            # ComtradeMetadata
# =============================================================================

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SampleRate:
    """One entry from the nrates section of a .cfg file."""
    samp: float      # samples per second
    endsamp: int     # last sample number at this rate


@dataclass
class ComtradeMetadata:
    """Structured representation of the .cfg header fields."""
    station_name: str
    rec_dev_id:   str
    rev_year:     str           # e.g. '1991', '1999', '2013'
    frequency:    float         # nominal line frequency [Hz]
    start_time:   str           # dd/mm/yyyy,hh:mm:ss.ssssss
    trigger_time: str           # same format
    data_format:  str           # 'ASCII' | 'BINARY' | 'BINARY32' | 'FLOAT32'
    nrates:       int
    sample_rates: List[SampleRate] = field(default_factory=list)
    n_analog:     int = 0
    n_digital:    int = 0


@dataclass
class _AnalogChannelDef:
    index:     int
    ch_id:     str
    ph:        str
    ccbm:      str
    uu:        str        # unit (kV, A, …)
    a:         float      # multiplier
    b:         float      # offset
    skew:      float
    min_val:   float
    max_val:   float
    primary:   float
    secondary: float
    ps:        str        # P or S (primary/secondary)


@dataclass
class _DigitalChannelDef:
    index:    int
    ch_id:    str
    ph:       str
    ccbm:     str
    y:        int         # normal state (0 or 1)


# ---------------------------------------------------------------------------
# Vendor → standard channel name map
# ---------------------------------------------------------------------------

# Keys are lower-cased, stripped, partial match patterns (checked with 'in').
# Values are canonical standard names.
VENDOR_CHANNEL_MAP: Dict[str, str] = {
    # Voltages
    "va": "Va",   "v-a": "Va",  "van": "Va", "phase a v": "Va",
    "vb": "Vb",   "v-b": "Vb",  "vbn": "Vb", "phase b v": "Vb",
    "vc": "Vc",   "v-c": "Vc",  "vcn": "Vc", "phase c v": "Vc",
    # Currents
    "ia": "Ia",   "i-a": "Ia",  "il1": "Ia", "phase a i": "Ia", "cur a": "Ia",
    "ib": "Ib",   "i-b": "Ib",  "il2": "Ib", "phase b i": "Ib", "cur b": "Ib",
    "ic": "Ic",   "i-c": "Ic",  "il3": "Ic", "phase c i": "Ic", "cur c": "Ic",
    # Zero-sequence
    "i0": "I0",   "in": "I0",
    "v0": "V0",
}


def _normalise_channel_name(raw: str) -> str:
    """Map a raw vendor channel name to a standard label, or return raw.

    Matching priority:
    1. Exact match (case-insensitive).
    2. Pattern appears in key AND the character immediately after the pattern
       (if any) is non-alphanumeric — prevents 'il1' matching 'il1v'.
    Longer patterns are tried before shorter ones to avoid partial shadowing.
    """
    key = raw.strip().lower()
    if key in VENDOR_CHANNEL_MAP:
        return VENDOR_CHANNEL_MAP[key]
    # Sort longest-pattern-first to avoid shorter patterns shadowing longer ones
    for pattern, standard in sorted(VENDOR_CHANNEL_MAP.items(),
                                    key=lambda kv: len(kv[0]), reverse=True):
        pos = key.find(pattern)
        if pos == -1:
            continue
        end = pos + len(pattern)
        # Require the match ends at end-of-string or at a non-alphanumeric char
        if end == len(key) or not key[end].isalnum():
            return standard
    return raw.strip()


# ---------------------------------------------------------------------------
# ComtradeRecord
# ---------------------------------------------------------------------------

class ComtradeRecord:
    """
    Parsed COMTRADE event record.

    Attributes
    ----------
    timestamps : ndarray, int64, shape (N,)
        Sample timestamps in microseconds relative to the start of recording.
    analog_channels : dict[str, ndarray]
        Scaled (a*raw+b) floating-point waveforms keyed by normalised channel name.
    digital_channels : dict[str, ndarray]
        Boolean (0/1) status channels keyed by normalised channel name.
    metadata : ComtradeMetadata
        Structured .cfg header data.
    """

    def __init__(
        self,
        timestamps:        np.ndarray,
        analog_channels:   Dict[str, np.ndarray],
        digital_channels:  Dict[str, np.ndarray],
        metadata:          ComtradeMetadata,
    ) -> None:
        self.timestamps       = timestamps
        self.analog_channels  = analog_channels
        self.digital_channels = digital_channels
        self.metadata         = metadata

    def __repr__(self) -> str:
        n  = len(self.timestamps)
        na = len(self.analog_channels)
        nd = len(self.digital_channels)
        return (f"ComtradeRecord(samples={n}, analog={na}, "
                f"digital={nd}, station={self.metadata.station_name!r})")


# ---------------------------------------------------------------------------
# ComtradeParser
# ---------------------------------------------------------------------------

class ComtradeParser:
    """
    IEEE C37.111-2013 COMTRADE file parser (ASCII and BINARY formats).

    Usage
    -----
    parser = ComtradeParser()
    record = parser.parse("path/to/event.cfg")
    record = parser.parse("path/to/event.cfg", "path/to/event.dat")
    """

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    def parse(self, cfg_path: str, dat_path: Optional[str] = None) -> ComtradeRecord:
        """
        Parse a COMTRADE file pair and return a ComtradeRecord.

        Parameters
        ----------
        cfg_path : str
            Path to the .cfg configuration file.
        dat_path : str, optional
            Path to the .dat data file.  If omitted, the parser looks for a
            file with the same stem as *cfg_path* but with the .dat extension.

        Returns
        -------
        ComtradeRecord

        Raises
        ------
        FileNotFoundError
            If either file cannot be found.
        ValueError
            If the .cfg file is malformed or the data format is unsupported.
        """
        cfg_path = Path(cfg_path)
        if not cfg_path.exists():
            raise FileNotFoundError(f"CFG file not found: {cfg_path}")

        if dat_path is None:
            dat_path = cfg_path.with_suffix(".dat")
        else:
            dat_path = Path(dat_path)
        if not dat_path.exists():
            raise FileNotFoundError(f"DAT file not found: {dat_path}")

        try:
            metadata, analog_defs, digital_defs = self._parse_cfg(cfg_path)
        except (IndexError, KeyError, struct.error) as exc:
            raise ValueError(f"Malformed CFG file ({cfg_path}): {exc}") from exc

        fmt = metadata.data_format.upper()
        if fmt == "ASCII":
            timestamps, raw_analog, raw_digital = self._parse_dat_ascii(
                dat_path, len(analog_defs), len(digital_defs)
            )
        elif fmt in ("BINARY", "BINARY32"):
            timestamps, raw_analog, raw_digital = self._parse_dat_binary(
                dat_path, len(analog_defs), len(digital_defs), fmt
            )
        else:
            raise ValueError(f"Unsupported data format: {fmt!r}")

        # Apply scaling: actual = a * raw + b
        analog_channels: Dict[str, np.ndarray] = {}
        for adef in analog_defs:
            raw = raw_analog[:, adef.index]
            scaled = adef.a * raw.astype(np.float64) + adef.b
            name = _normalise_channel_name(adef.ch_id)
            analog_channels[name] = scaled

        digital_channels: Dict[str, np.ndarray] = {}
        for ddef in digital_defs:
            raw = raw_digital[:, ddef.index].astype(np.uint8)
            name = _normalise_channel_name(ddef.ch_id)
            digital_channels[name] = raw

        return ComtradeRecord(
            timestamps=timestamps,
            analog_channels=analog_channels,
            digital_channels=digital_channels,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # CFG parser
    # ------------------------------------------------------------------

    def _parse_cfg(
        self, cfg_path: Path
    ) -> Tuple[ComtradeMetadata, List[_AnalogChannelDef], List[_DigitalChannelDef]]:
        """
        Parse a .cfg file into metadata + channel definitions.

        Returns
        -------
        (ComtradeMetadata, list[_AnalogChannelDef], list[_DigitalChannelDef])
        """
        lines = cfg_path.read_text(encoding="ascii", errors="replace").splitlines()
        if not lines:
            raise ValueError("CFG file is empty")

        idx = 0

        # ---- Line 1: station_name, rec_dev_id[, rev_year] ----
        parts = [p.strip() for p in lines[idx].split(",")]
        station_name = parts[0] if len(parts) > 0 else ""
        rec_dev_id   = parts[1] if len(parts) > 1 else ""
        rev_year     = parts[2] if len(parts) > 2 else "1991"
        idx += 1

        # ---- Line 2: TT,##A,##D  (total channels, analog count, digital count) ----
        parts = [p.strip() for p in lines[idx].split(",")]
        # format: "<total>A,<n_d>D" or "<total>,<n_a>A,<n_d>D"
        n_analog = n_digital = 0
        for part in parts:
            if part.upper().endswith("A"):
                n_analog = int(part[:-1])
            elif part.upper().endswith("D"):
                n_digital = int(part[:-1])
        idx += 1

        # ---- Analog channel definitions ----
        analog_defs: List[_AnalogChannelDef] = []
        for i in range(n_analog):
            p = [x.strip() for x in lines[idx].split(",")]
            # An, ch_id, ph, ccbm, uu, a, b, skew, min, max, primary, secondary, PS
            adef = _AnalogChannelDef(
                index=i,
                ch_id=p[1] if len(p) > 1 else f"A{i+1}",
                ph=   p[2] if len(p) > 2 else "",
                ccbm= p[3] if len(p) > 3 else "",
                uu=   p[4] if len(p) > 4 else "",
                a=    float(p[5]) if len(p) > 5 and p[5] else 1.0,
                b=    float(p[6]) if len(p) > 6 and p[6] else 0.0,
                skew= float(p[7]) if len(p) > 7 and p[7] else 0.0,
                min_val=   float(p[8])  if len(p) > 8  and p[8]  else -1e9,
                max_val=   float(p[9])  if len(p) > 9  and p[9]  else  1e9,
                primary=   float(p[10]) if len(p) > 10 and p[10] else 1.0,
                secondary= float(p[11]) if len(p) > 11 and p[11] else 1.0,
                ps=        p[12]        if len(p) > 12 else "P",
            )
            analog_defs.append(adef)
            idx += 1

        # ---- Digital channel definitions ----
        digital_defs: List[_DigitalChannelDef] = []
        for i in range(n_digital):
            p = [x.strip() for x in lines[idx].split(",")]
            # Dn, ch_id, ph, ccbm, y
            ddef = _DigitalChannelDef(
                index=i,
                ch_id=p[1] if len(p) > 1 else f"D{i+1}",
                ph=   p[2] if len(p) > 2 else "",
                ccbm= p[3] if len(p) > 3 else "",
                y=    int(p[4]) if len(p) > 4 and p[4] else 0,
            )
            digital_defs.append(ddef)
            idx += 1

        # ---- Line frequency ----
        frequency = float(lines[idx].strip())
        idx += 1

        # ---- nrates and sample-rate pairs ----
        nrates = int(lines[idx].strip())
        idx += 1
        sample_rates: List[SampleRate] = []
        for _ in range(max(nrates, 1)):
            p = [x.strip() for x in lines[idx].split(",")]
            sample_rates.append(SampleRate(
                samp=    float(p[0]),
                endsamp= int(p[1]),
            ))
            idx += 1

        # ---- Start time, trigger time ----
        start_time   = lines[idx].strip(); idx += 1
        trigger_time = lines[idx].strip(); idx += 1

        # ---- Data format ----
        data_format = lines[idx].strip().upper(); idx += 1

        metadata = ComtradeMetadata(
            station_name=station_name,
            rec_dev_id=rec_dev_id,
            rev_year=rev_year,
            frequency=frequency,
            start_time=start_time,
            trigger_time=trigger_time,
            data_format=data_format,
            nrates=nrates,
            sample_rates=sample_rates,
            n_analog=n_analog,
            n_digital=n_digital,
        )
        return metadata, analog_defs, digital_defs

    # ------------------------------------------------------------------
    # ASCII .dat parser
    # ------------------------------------------------------------------

    def _parse_dat_ascii(
        self,
        dat_path: Path,
        n_analog:  int,
        n_digital: int,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Parse an ASCII-format .dat file.

        Each row: sample_number, timestamp_μs, a1, a2, …, d1, d2, …

        Returns
        -------
        timestamps  : ndarray int64  (N,)
        raw_analog  : ndarray float64 (N, n_analog)
        raw_digital : ndarray int32   (N, n_digital)
        """
        try:
            text = dat_path.read_text(encoding="ascii", errors="replace")
        except OSError as exc:
            raise FileNotFoundError(f"Cannot read DAT file: {dat_path}") from exc

        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                vals = [float(v) for v in line.split(",")]
            except ValueError as exc:
                raise ValueError(
                    f"Malformed ASCII DAT row in {dat_path}: {line!r}"
                ) from exc
            rows.append(vals)

        if not rows:
            raise ValueError(f"DAT file contains no data rows: {dat_path}")

        data = np.array(rows, dtype=np.float64)          # (N, 2+na+nd)
        timestamps  = data[:, 1].astype(np.int64)         # column 1: μs stamp
        raw_analog  = data[:, 2 : 2 + n_analog]
        raw_digital = data[:, 2 + n_analog : 2 + n_analog + n_digital].astype(np.int32)

        return timestamps, raw_analog, raw_digital

    # ------------------------------------------------------------------
    # BINARY .dat parser
    # ------------------------------------------------------------------

    def _parse_dat_binary(
        self,
        dat_path: Path,
        n_analog:  int,
        n_digital: int,
        fmt:       str = "BINARY",
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Parse a BINARY-format .dat file (IEEE C37.111-1999/2013).

        Record structure per sample:
          - 4 bytes  : sample number    (uint32 LE)
          - 4 bytes  : timestamp [μs]   (uint32 LE)
          - 2 bytes  : each analog channel (int16 LE)
          - 2 bytes  : each group of 16 digital channels (uint16 LE packed bits)

        Parameters
        ----------
        fmt : 'BINARY' (int16 analog) or 'BINARY32' (int32 analog, not yet used).

        Returns
        -------
        timestamps  : ndarray int64  (N,)
        raw_analog  : ndarray float64 (N, n_analog)
        raw_digital : ndarray int32   (N, n_digital)
        """
        n_dig_words = max(1, (n_digital + 15) // 16)   # 16 digital bits per uint16

        # Build struct format string
        if fmt == "BINARY32":
            analog_fmt = f"{n_analog}i"   # int32
            analog_bytes = 4 * n_analog
        else:
            analog_fmt = f"{n_analog}h"   # int16
            analog_bytes = 2 * n_analog

        dig_fmt   = f"{n_dig_words}H"     # uint16 words
        dig_bytes = 2 * n_dig_words

        record_fmt   = f"<II{analog_fmt[len(str(n_analog)):]}{dig_fmt}"
        # Rebuild cleanly:
        record_fmt   = f"<II"
        if fmt == "BINARY32":
            record_fmt += "i" * n_analog
        else:
            record_fmt += "h" * n_analog
        record_fmt += "H" * n_dig_words

        record_size  = struct.calcsize(record_fmt)

        try:
            raw_bytes = dat_path.read_bytes()
        except OSError as exc:
            raise FileNotFoundError(f"Cannot read DAT file: {dat_path}") from exc

        if len(raw_bytes) % record_size != 0:
            raise ValueError(
                f"BINARY DAT size {len(raw_bytes)} is not a multiple of "
                f"record size {record_size} (format {fmt})"
            )

        n_samples = len(raw_bytes) // record_size
        timestamps  = np.empty(n_samples, dtype=np.int64)
        raw_analog  = np.empty((n_samples, n_analog),  dtype=np.float64)
        raw_digital = np.zeros((n_samples, n_digital), dtype=np.int32)

        offset = 0
        for i in range(n_samples):
            record = struct.unpack_from(record_fmt, raw_bytes, offset)
            offset += record_size
            # record = (sample_no, timestamp_μs, a0, a1, …, d_word0, …)
            timestamps[i] = record[1]
            raw_analog[i] = record[2 : 2 + n_analog]
            # Unpack digital words (LSB-first within each uint16)
            dword_offset = 2 + n_analog
            for w, word in enumerate(record[dword_offset:]):
                for b in range(16):
                    dig_idx = w * 16 + b
                    if dig_idx < n_digital:
                        raw_digital[i, dig_idx] = (word >> b) & 1

        return timestamps, raw_analog, raw_digital
