# =============================================================================
# sambp / io_utils / comtrade_adapter.py
#
# Bridge between COMTRADE field-recording / PSCAD EMT output and the SAMBP
# estimator pipeline.  Mirrors the andes_adapter.py pattern so both sources
# feed the same downstream io_utils layer.
#
# Supported sources
# -----------------
# 1. COMTRADE C37.111-1999 / C37.111-2013 (field recordings, RTDS playback)
#    → read_comtrade(cfg_file, dat_file)
# 2. PSCAD CSV / EMTDC output export
#    → read_pscad_csv(csv_file)
# 3. Unified builder → build_fault_case(waveforms, ...) same as andes_adapter
#
# Public API
# ----------
# read_comtrade(cfg_file, dat_file=None, **kw)
#     → ComtradeResult (namedtuple)
#
# read_pscad_csv(csv_file, channel_map=None, fs_out=10000.0)
#     → ComtradeResult  (same namedtuple, source='pscad')
#
# extract_relay_waveforms(result, relay_name, fs_out=10000.0, window=None)
#     → dict {t, ia, ib, ic, va, vb, vc, meta}
#
# build_fault_case(waveforms, fault_type, fault_R_pu)
#     → dict  (direct input to estimate_reduced_source_parameters)
#
# run_full_pipeline(cfg_file, relay_name, fault_type, ...)
#     → dict  (convenience: read + extract + build in one call)
#
# File storage convention (see R-02)
# -----------------------------------
# Field waveforms  →  /root/phd_thesis/05_data/fault_waveforms/
#   Naming: {YYYYMMDD}_{substation}_{fault_type}_{relay_id}.cfg / .dat
# PSCAD exports   →  /root/phd_thesis/05_data/fault_waveforms/pscad/
#   Naming: {case_name}_{fault_bus}_{clearing_time_ms}ms.csv
# =============================================================================

from __future__ import annotations

import os
import warnings
from collections import namedtuple
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.interpolate import interp1d

# comtrade import — lazy, only at runtime
_comtrade = None


def _import_comtrade():
    global _comtrade
    if _comtrade is None:
        try:
            import comtrade as ct
            _comtrade = ct
        except ImportError:
            try:
                # fallback: python-comtrade (pip install comtrade)
                import comtrade as ct
                _comtrade = ct
            except ImportError as e:
                raise ImportError(
                    "comtrade package not installed.  Run:\n"
                    "  pip install comtrade\n"
                    "or activate the project venv."
                ) from e
    return _comtrade


# ---------------------------------------------------------------------------
# Return type — mirrors AndesResult so downstream code is source-agnostic
# ---------------------------------------------------------------------------

ComtradeResult = namedtuple("ComtradeResult", [
    "t",            # ndarray — time vector [s]
    "channels",     # dict {name: ndarray} — all analog channels at native fs
    "fs",           # float — native sample rate [Hz]
    "meta",         # dict — station name, start datetime, frequency, npts
    "source",       # str — 'comtrade' | 'pscad'
    "source_file",  # str — cfg or csv path
])


# ---------------------------------------------------------------------------
# Step 1a — Read COMTRADE C37.111
# ---------------------------------------------------------------------------

def read_comtrade(
    cfg_file: str,
    dat_file: Optional[str] = None,
    encoding: str = "ascii",
) -> ComtradeResult:
    """
    Parse a COMTRADE recording (.cfg + .dat pair).

    Parameters
    ----------
    cfg_file : path to .cfg file (C37.111-1999 or -2013)
    dat_file : path to .dat file; if None, inferred from cfg_file stem
    encoding : file encoding ('ascii' for 1999, 'utf-8' for 2013)

    Returns
    -------
    ComtradeResult
    """
    ct = _import_comtrade()
    cfg_path = Path(cfg_file)

    if dat_file is None:
        # Try .dat then .DAT
        for ext in (".dat", ".DAT"):
            candidate = cfg_path.with_suffix(ext)
            if candidate.exists():
                dat_file = str(candidate)
                break
        if dat_file is None:
            raise FileNotFoundError(
                f"Cannot find .dat file for {cfg_file}. "
                "Provide dat_file explicitly."
            )

    rec = ct.load(str(cfg_file), str(dat_file))

    t  = np.array(rec.time)
    fs = float(rec.cfg.sample_rates[0][0]) if rec.cfg.sample_rates else _estimate_fs(t)

    channels: Dict[str, np.ndarray] = {}
    for i, (name, data) in enumerate(zip(rec.analog_channel_ids, rec.analog)):
        channels[name.strip()] = np.array(data, dtype=np.float64)

    meta = {
        "station_name": getattr(rec.cfg, "station_name", "unknown"),
        "start_time":   str(getattr(rec, "start_timestamp", "")),
        "frequency":    float(getattr(rec.cfg, "frequency", 50.0)),
        "npts":         len(t),
        "n_channels":   len(channels),
    }

    return ComtradeResult(
        t=t, channels=channels, fs=fs, meta=meta,
        source="comtrade", source_file=str(cfg_file),
    )


# ---------------------------------------------------------------------------
# Step 1b — Read PSCAD CSV export
# ---------------------------------------------------------------------------

def read_pscad_csv(
    csv_file: str,
    channel_map: Optional[Dict[str, str]] = None,
    fs_out: float = 10000.0,
    delimiter: str = ",",
    time_col: str = "time",
) -> ComtradeResult:
    """
    Parse a PSCAD / EMTDC CSV export into a ComtradeResult.

    Parameters
    ----------
    csv_file    : path to CSV (first column = time, remaining = channels)
    channel_map : optional rename dict {csv_col: canonical_name}
                  e.g. {'Va_bus1': 'Va', 'Ia_branch12': 'Ia'}
    fs_out      : output sample rate; PSCAD native is typically 50–200 kHz;
                  will be downsampled to fs_out.
    time_col    : name of the time column header (default 'time')

    Returns
    -------
    ComtradeResult  (source='pscad')
    """
    data = np.genfromtxt(csv_file, delimiter=delimiter, names=True,
                         encoding="utf-8-sig")
    col_names = list(data.dtype.names)

    # Identify time column
    t_col = time_col if time_col in col_names else col_names[0]
    t_raw = data[t_col].astype(np.float64)
    fs_native = _estimate_fs(t_raw)

    channels_raw: Dict[str, np.ndarray] = {}
    for col in col_names:
        if col == t_col:
            continue
        canonical = channel_map.get(col, col) if channel_map else col
        channels_raw[canonical] = data[col].astype(np.float64)

    # Downsample to fs_out if native is higher
    if fs_native > fs_out * 1.05:
        t, channels = _resample_channels(t_raw, channels_raw, fs_out)
        fs = fs_out
    else:
        t, channels, fs = t_raw, channels_raw, fs_native

    meta = {
        "station_name": Path(csv_file).stem,
        "start_time":   f"{t[0]:.6f}s",
        "frequency":    50.0,
        "npts":         len(t),
        "n_channels":   len(channels),
        "native_fs_Hz": fs_native,
    }

    return ComtradeResult(
        t=t, channels=channels, fs=fs, meta=meta,
        source="pscad", source_file=str(csv_file),
    )


# ---------------------------------------------------------------------------
# Step 2 — Extract relay waveforms (source-agnostic)
# ---------------------------------------------------------------------------

# Canonical channel name variants accepted for each phase
_VA_KEYS = ("Va", "VA", "V_a", "v_a", "Va_pu", "Bus_Va")
_VB_KEYS = ("Vb", "VB", "V_b", "v_b", "Vb_pu", "Bus_Vb")
_VC_KEYS = ("Vc", "VC", "V_c", "v_c", "Vc_pu", "Bus_Vc")
_IA_KEYS = ("Ia", "IA", "I_a", "i_a", "Ia_pu", "Br_Ia")
_IB_KEYS = ("Ib", "IB", "I_b", "i_b", "Ib_pu", "Br_Ib")
_IC_KEYS = ("Ic", "IC", "I_c", "i_c", "Ic_pu", "Br_Ic")


def extract_relay_waveforms(
    result: ComtradeResult,
    relay_name: str = "",
    fs_out: float = 10000.0,
    window: Optional[Tuple[float, float]] = None,
    f0: float = 50.0,
) -> dict:
    """
    Extract three-phase va/vb/vc and ia/ib/ic from a ComtradeResult.

    The function performs name-resolution across known channel aliases
    (see _VA_KEYS etc.), resamples to fs_out, and trims to window.

    Parameters
    ----------
    result     : ComtradeResult from read_comtrade() or read_pscad_csv()
    relay_name : prefix for channel lookup (e.g. 'L1_' → 'L1_Va', 'L1_Ia')
                 Leave empty to use bare canonical names.
    fs_out     : SAMBP pipeline sample rate (default 10 kHz)
    window     : (t_start, t_end) trim window in seconds; None = full record
    f0         : nominal frequency [Hz]

    Returns
    -------
    dict with keys: t, ia, ib, ic, va, vb, vc, meta
    """
    ch = result.channels
    prefix = relay_name.rstrip("_") + "_" if relay_name else ""

    def _resolve(keys: tuple) -> np.ndarray:
        for k in keys:
            if prefix + k in ch:
                return ch[prefix + k]
        for k in keys:
            if k in ch:
                return ch[k]
        # fallback: zero array (warn)
        warnings.warn(
            f"Channel not found for keys {keys} (prefix='{prefix}'). "
            "Returning zeros.", stacklevel=2
        )
        return np.zeros(len(result.t))

    va = _resolve(_VA_KEYS)
    vb = _resolve(_VB_KEYS)
    vc = _resolve(_VC_KEYS)
    ia = _resolve(_IA_KEYS)
    ib = _resolve(_IB_KEYS)
    ic = _resolve(_IC_KEYS)

    t_src = result.t

    # Resample to fs_out
    if abs(result.fs - fs_out) > 1.0:
        t_out = np.arange(t_src[0], t_src[-1], 1.0 / fs_out)
        def _interp(arr):
            return interp1d(t_src, arr, kind="linear",
                            bounds_error=False, fill_value="extrapolate")(t_out)
        va, vb, vc = _interp(va), _interp(vb), _interp(vc)
        ia, ib, ic = _interp(ia), _interp(ib), _interp(ic)
        t_src = t_out

    # Window trim
    if window is not None:
        t0, t1 = window
        mask = (t_src >= t0) & (t_src <= t1)
        t_src = t_src[mask]
        va, vb, vc = va[mask], vb[mask], vc[mask]
        ia, ib, ic = ia[mask], ib[mask], ic[mask]

    meta = dict(result.meta)
    meta.update({
        "relay_name":  relay_name,
        "fs_out_Hz":   fs_out,
        "window":      window,
        "source":      result.source,
        "source_file": result.source_file,
        "f0_Hz":       f0,
    })

    return dict(t=t_src, va=va, vb=vb, vc=vc,
                ia=ia, ib=ib, ic=ic, meta=meta)


# ---------------------------------------------------------------------------
# Step 3 — Build FaultCase dict (identical to andes_adapter output format)
# ---------------------------------------------------------------------------

def build_fault_case(
    waveforms: dict,
    fault_type: str = "3PH",
    fault_R_pu: float = 0.0,
    label: str = "",
) -> dict:
    """
    Wrap extracted waveforms into the FaultCase dict consumed by
    estimate_reduced_source_parameters() — identical format to andes_adapter.

    Parameters
    ----------
    waveforms  : output of extract_relay_waveforms()
    fault_type : '3PH' | 'SLG' | 'LL' | 'LLG'
    fault_R_pu : fault resistance [pu]
    label      : human-readable tag (stored in meta)

    Returns
    -------
    dict matching FaultCase schema
    """
    return {
        "t":          waveforms["t"],
        "ia":         waveforms["ia"],
        "ib":         waveforms["ib"],
        "ic":         waveforms["ic"],
        "va":         waveforms["va"],
        "vb":         waveforms["vb"],
        "vc":         waveforms["vc"],
        "fault_type": fault_type,
        "fault_R_pu": fault_R_pu,
        "label":      label or waveforms["meta"].get("station_name", ""),
        "meta":       waveforms["meta"],
        "source":     waveforms["meta"].get("source", "unknown"),
    }


# ---------------------------------------------------------------------------
# Convenience: full pipeline
# ---------------------------------------------------------------------------

def run_full_pipeline(
    source_file: str,
    relay_name: str = "",
    fault_type: str = "3PH",
    fault_R_pu: float = 0.0,
    fs_out: float = 10000.0,
    window: Optional[Tuple[float, float]] = None,
    channel_map: Optional[Dict[str, str]] = None,
    dat_file: Optional[str] = None,
) -> dict:
    """
    One-shot pipeline: detect source type, read, extract, build FaultCase.

    Source detection:
      .cfg → COMTRADE
      .csv → PSCAD CSV
      .dat → raw binary COMTRADE (must provide dat_file)
    """
    ext = Path(source_file).suffix.lower()
    if ext == ".cfg":
        result = read_comtrade(source_file, dat_file=dat_file)
    elif ext == ".csv":
        result = read_pscad_csv(source_file, channel_map=channel_map,
                                fs_out=fs_out)
    else:
        raise ValueError(
            f"Unsupported source extension '{ext}'. "
            "Use .cfg (COMTRADE) or .csv (PSCAD)."
        )

    waveforms = extract_relay_waveforms(result, relay_name=relay_name,
                                        fs_out=fs_out, window=window)
    return build_fault_case(waveforms, fault_type=fault_type,
                            fault_R_pu=fault_R_pu)


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _estimate_fs(t: np.ndarray) -> float:
    """Estimate sample rate from time vector median step."""
    if len(t) < 2:
        return 10000.0
    dt = np.median(np.diff(t))
    return float(1.0 / dt) if dt > 0 else 10000.0


def _resample_channels(
    t_src: np.ndarray,
    channels: Dict[str, np.ndarray],
    fs_out: float,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], float]:
    t_out = np.arange(t_src[0], t_src[-1], 1.0 / fs_out)
    resampled = {}
    for name, arr in channels.items():
        resampled[name] = interp1d(
            t_src, arr, kind="linear",
            bounds_error=False, fill_value="extrapolate"
        )(t_out)
    return t_out, resampled, fs_out


# ---------------------------------------------------------------------------
# Batch loader — scan a directory for COMTRADE / PSCAD files
# ---------------------------------------------------------------------------

def scan_fault_waveform_dir(
    directory: str = "/root/phd_thesis/05_data/fault_waveforms/",
    recursive: bool = True,
) -> List[dict]:
    """
    Scan directory for .cfg (COMTRADE) and .csv (PSCAD) files.
    Returns list of dicts: {path, source_type, stem}

    Used by TR-87 batch ingest runner.
    """
    root = Path(directory)
    if not root.exists():
        warnings.warn(f"Fault waveform directory not found: {directory}")
        return []

    found = []
    glob_fn = root.rglob if recursive else root.glob
    for p in sorted(glob_fn("*")):
        if p.suffix.lower() == ".cfg":
            found.append({"path": str(p), "source_type": "comtrade", "stem": p.stem})
        elif p.suffix.lower() == ".csv":
            found.append({"path": str(p), "source_type": "pscad",    "stem": p.stem})
    return found
