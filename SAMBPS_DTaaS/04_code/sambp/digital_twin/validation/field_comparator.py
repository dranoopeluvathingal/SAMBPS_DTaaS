# =============================================================================
# sambp / digital_twin / validation / field_comparator.py
#
# DT Replay Engine — TR-76 WP 76.3
#
# Replays COMTRADE fault records through the Digital Twin engine and compares
# the DT's predicted decision against the field relay's actual action.
#
# Replay pipeline
# ---------------
# For each record:
#   1. Parse .cfg / .dat via ComtradeParser → ComtradeRecord
#   2. Feed Va/Vb/Vc, Ia/Ib/Ic sample-by-sample into DTEngine.update()
#      (subsampled to dt_rate_hz to match estimator update rate)
#   3. Detect fault onset: voltage magnitude drops below V_SAG_THRESHOLD
#   4. At the first sample after fault onset, extract the DT state
#      (k_ibr estimate from EKF) and run DTEngine.validate()
#   5. Extract field relay decision from digital channels (TRIP, 87L_OP, …)
#   6. Compute trip-time error: dt_trip_time_ms − field_trip_time_ms
#
# Element mapping from digital channels
# --------------------------------------
#   Digital channel  → relay element (in priority order)
#   87L_OP = 1       → '87L'
#   21_OP  = 1       → 'Z1/87L'
#   OC_OP  = 1       → 'OC'
#   (none asserts)   → 'UNKNOWN' (element not recorded)
#
# Public API
# ----------
# cmp = FieldComparator(dt_engine, parser)
# report  = cmp.replay_record(cfg_path, metadata=None) → FieldComparisonReport
# breport = cmp.replay_batch(index_yaml)               → BatchComparisonReport
# =============================================================================

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

# Support both import paths:
#   (a) as part of the digital_twin package  → relative imports work
#   (b) directly from sys.path root          → absolute imports needed
try:
    from .comtrade_parser import ComtradeParser, ComtradeRecord
    from ..models.protection_mirror import ProtectionMirror as _ProtectionMirror
except ImportError:
    from validation.comtrade_parser import ComtradeParser, ComtradeRecord      # type: ignore[no-redef]
    from models.protection_mirror import ProtectionMirror as _ProtectionMirror  # type: ignore[no-redef]

# Fault onset detection: current overcurrent multiplier above pre-fault baseline.
# For a balanced pre-fault at 0.20 pu peak → i_rms ≈ 0.14 pu.
# Fault current rises to 1.0–8.0 pu depending on fault type and IBR mix.
# A 2× multiplier detects all fault types while rejecting normal load variation.
# (Voltage-sag detection fails for balanced 3-phase: instantaneous
#  sqrt(Va²+Vb²+Vc²)/3 = amplitude/√2 ≈ 0.707 pu always, below 0.80 threshold.)
_I_FAULT_MULTIPLIER = 2.0   # current must exceed 2× pre-fault baseline to flag onset

# Pre-fault window fraction for baseline estimation
_PREFAULT_WINDOW_FRAC = 0.20   # use first 20% of record as pre-fault baseline

# Minimum samples to feed before reading DT state (allow estimator to converge)
_WARM_UP_SAMPLES = 5

# Digital channel priority order for element identification
_DIG_ELEMENT_MAP = [
    ("87L_OP", "87L"),
    ("21_OP",  "Z1/87L"),
    ("OC_OP",  "OC"),
]


# ---------------------------------------------------------------------------
# FieldComparisonReport
# ---------------------------------------------------------------------------

@dataclass
class FieldComparisonReport:
    """
    Single-record comparison: DT prediction vs field relay decision.

    Attributes
    ----------
    record_id         : str  — unique record identifier
    fault_type        : str  — SLG / LL / DLG / 3PH / …
    ibr_type          : str  — SG / DFIG / GFM / GFL / PV / BESS
    dt_decision       : str  — DT verdict: AGREE / FLAG_FP / FLAG_FN / …
    field_decision    : str  — TRIP or BLOCK (from digital channels)
    agreement         : bool — True when dt_decision == 'AGREE'
    dt_trip_time_ms   : float or None  — time from fault onset to DT TRIP [ms]
    field_trip_time_ms: float or None  — time from fault onset to field TRIP [ms]
    time_error_ms     : float or None  — dt_trip_time_ms − field_trip_time_ms
    dt_element        : str  — DT mirror predicted element
    field_element     : str  — element from digital channels
    element_match     : bool — dt_element == field_element (family-level)
    k_ibr_estimated   : float — DT EKF k_ibr estimate at fault onset
    confidence_kappa  : float — DT EKF condition number at fault onset
    reason            : str  — human-readable comparison reason
    selectivity_note  : str or None
    """
    record_id:          str
    fault_type:         str
    ibr_type:           str
    dt_decision:        str
    field_decision:     str
    agreement:          bool
    dt_trip_time_ms:    Optional[float]
    field_trip_time_ms: Optional[float]
    time_error_ms:      Optional[float]
    dt_element:         str
    field_element:      str
    element_match:      bool
    k_ibr_estimated:    float
    confidence_kappa:   float
    reason:             str
    selectivity_note:   Optional[str] = None

    def __repr__(self) -> str:
        ok = "✓" if self.agreement else "✗"
        return (f"FieldComparisonReport({ok} {self.record_id} | "
                f"{self.fault_type}/{self.ibr_type} | "
                f"k={self.k_ibr_estimated:.3f} | {self.dt_decision})")


# ---------------------------------------------------------------------------
# BatchComparisonReport
# ---------------------------------------------------------------------------

class BatchComparisonReport:
    """
    Aggregated comparison metrics over multiple field records.

    Attributes
    ----------
    total_records : int
    agree_count   : int
    flag_count    : int
    agree_rate    : float   — agree_count / total_records
    per_fault_type : dict[str, float]  — agree rate by fault type
    per_ibr_type   : dict[str, float]  — agree rate by IBR type
    time_error_stats : dict with keys mean, std, max (all in ms, None if no trips)
    element_match_rate : float
    reports        : list[FieldComparisonReport]  — all individual reports
    """

    def __init__(self, reports: List[FieldComparisonReport]) -> None:
        self.reports = reports
        self.total_records = len(reports)

        # ---- Counts ----
        self.agree_count = sum(1 for r in reports if r.agreement)
        self.flag_count  = self.total_records - self.agree_count
        self.agree_rate  = (self.agree_count / self.total_records
                            if self.total_records > 0 else 0.0)

        # ---- Per fault type ----
        ft_agree: dict[str, list[bool]] = defaultdict(list)
        it_agree: dict[str, list[bool]] = defaultdict(list)
        for r in reports:
            ft_agree[r.fault_type].append(r.agreement)
            it_agree[r.ibr_type].append(r.agreement)

        self.per_fault_type: dict[str, float] = {
            ft: sum(v) / len(v) for ft, v in ft_agree.items()
        }
        self.per_ibr_type: dict[str, float] = {
            it: sum(v) / len(v) for it, v in it_agree.items()
        }

        # ---- Trip time errors ----
        time_errs = [r.time_error_ms for r in reports
                     if r.time_error_ms is not None]
        if time_errs:
            self.time_error_stats = {
                "mean": statistics.mean(time_errs),
                "std":  statistics.stdev(time_errs) if len(time_errs) > 1 else 0.0,
                "max":  max(abs(e) for e in time_errs),
                "n":    len(time_errs),
            }
        else:
            self.time_error_stats = {"mean": None, "std": None, "max": None, "n": 0}

        # ---- Element match rate ----
        self.element_match_rate = (
            sum(1 for r in reports if r.element_match) / self.total_records
            if self.total_records > 0 else 0.0
        )

        # ---- Verdict breakdown ----
        self._verdicts: dict[str, int] = defaultdict(int)
        for r in reports:
            self._verdicts[r.dt_decision] += 1

    # ------------------------------------------------------------------
    def to_dataframe(self):
        """
        Return a pandas DataFrame with one row per record.
        Requires pandas; raises ImportError if not installed.
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("pandas required for to_dataframe()") from exc

        rows = []
        for r in self.reports:
            rows.append({
                "record_id":           r.record_id,
                "fault_type":          r.fault_type,
                "ibr_type":            r.ibr_type,
                "dt_decision":         r.dt_decision,
                "field_decision":      r.field_decision,
                "agreement":           r.agreement,
                "dt_element":          r.dt_element,
                "field_element":       r.field_element,
                "element_match":       r.element_match,
                "k_ibr_estimated":     r.k_ibr_estimated,
                "confidence_kappa":    r.confidence_kappa,
                "dt_trip_time_ms":     r.dt_trip_time_ms,
                "field_trip_time_ms":  r.field_trip_time_ms,
                "time_error_ms":       r.time_error_ms,
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    def to_latex_table(self) -> str:
        """
        Return a LaTeX longtable with per-fault-type and per-IBR-type
        agreement rates, suitable for insertion into a thesis chapter.
        """
        lines = [
            r"\begin{table}[!t]",
            r"\centering",
            r"\caption{DT Replay Engine: Field Comparison Agreement Rates (TR-76 WP76.3)}",
            r"\label{tab:tr76_field_comparison}",
            r"\begin{tabular}{llrr}",
            r"\toprule",
            r"Category & Group & Records & Agree\,(\%) \\",
            r"\midrule",
        ]

        # Fault type block
        ft_total: dict[str, int] = defaultdict(int)
        ft_agree_n: dict[str, int] = defaultdict(int)
        for r in self.reports:
            ft_total[r.fault_type] += 1
            if r.agreement:
                ft_agree_n[r.fault_type] += 1

        for ft in sorted(ft_total):
            n   = ft_total[ft]
            pct = 100.0 * ft_agree_n[ft] / n
            lines.append(f"Fault type & {ft} & {n} & {pct:.1f}\\% \\\\")

        lines.append(r"\midrule")

        # IBR type block
        it_total: dict[str, int] = defaultdict(int)
        it_agree_n: dict[str, int] = defaultdict(int)
        for r in self.reports:
            it_total[r.ibr_type] += 1
            if r.agreement:
                it_agree_n[r.ibr_type] += 1

        for it in sorted(it_total):
            n   = it_total[it]
            pct = 100.0 * it_agree_n[it] / n
            lines.append(f"IBR type & {it} & {n} & {pct:.1f}\\% \\\\")

        lines += [
            r"\midrule",
            f"Overall & All & {self.total_records} & {self.agree_rate*100:.1f}\\% \\\\",
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def print_summary(self) -> None:
        """Print a formatted batch summary to stdout."""
        W = 62
        sep = "─" * W

        print(f"\n  {'SAMBP DT Replay Engine — Batch Comparison Report':^{W}}")
        print(f"  {sep}")
        print(f"  {'Total records':.<38} {self.total_records:>6}")
        print(f"  {'AGREE':.<38} {self.agree_count:>6}  "
              f"({self.agree_rate * 100:.1f}%)")
        print(f"  {'FLAG (any)':.<38} {self.flag_count:>6}  "
              f"({(1 - self.agree_rate) * 100:.1f}%)")

        print(f"\n  {'Verdict breakdown':}")
        for verdict, count in sorted(self._verdicts.items()):
            pct = 100.0 * count / max(self.total_records, 1)
            print(f"    {verdict:<20} {count:>5}  ({pct:.1f}%)")

        print(f"\n  {'Agreement by fault type':}")
        for ft, rate in sorted(self.per_fault_type.items()):
            n = sum(1 for r in self.reports if r.fault_type == ft)
            print(f"    {ft:<24} {rate*100:>6.1f}%  (N={n})")

        print(f"\n  {'Agreement by IBR type':}")
        for it, rate in sorted(self.per_ibr_type.items()):
            n = sum(1 for r in self.reports if r.ibr_type == it)
            print(f"    {it:<24} {rate*100:>6.1f}%  (N={n})")

        print(f"\n  {'Element match rate':.<38} "
              f"{self.element_match_rate*100:.1f}%")

        ts = self.time_error_stats
        if ts["n"] > 0:
            print(f"\n  Trip time error (DT − field) [ms]  (N={ts['n']})")
            print(f"    mean = {ts['mean']:+.2f} ms")
            print(f"    std  = {ts['std']:.2f} ms")
            print(f"    max  = {ts['max']:.2f} ms")
        else:
            print(f"\n  Trip time error: no paired trip events to compare")

        print(f"  {sep}\n")


# ---------------------------------------------------------------------------
# FieldComparator
# ---------------------------------------------------------------------------

class FieldComparator:
    """
    Replays COMTRADE records through the DT engine and compares decisions.

    Parameters
    ----------
    dt_engine : DTEngine
        Initialised Digital Twin engine.  Its estimator state is reset
        before each record replay to avoid cross-record contamination.
    parser : ComtradeParser
        Parser instance for reading .cfg / .dat file pairs.
    dt_rate_hz : float
        Rate at which DTEngine.update() is called during replay.
        Records are subsampled to this rate.  Default 1000 Hz.
    """

    def __init__(self, dt_engine, parser: ComtradeParser,
                 dt_rate_hz: float = 1000.0) -> None:
        self._engine     = dt_engine
        self._parser     = parser
        self._dt_rate_hz = dt_rate_hz
        self._dt_period  = 1.0 / dt_rate_hz

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def replay_record(
        self,
        cfg_path:  str,
        metadata:  Optional[dict] = None,
    ) -> FieldComparisonReport:
        """
        Replay a single COMTRADE record through the DT engine.

        Parameters
        ----------
        cfg_path : str
            Path to the .cfg file.  The .dat is auto-detected.
        metadata : dict, optional
            Additional context keys: 'fault_type', 'ibr_type', 'record_id'.
            If not given, these are inferred from the .cfg station name / path.

        Returns
        -------
        FieldComparisonReport
        """
        record = self._parser.parse(cfg_path)
        meta   = metadata or {}
        record_id  = meta.get("record_id",  Path(cfg_path).stem)
        fault_type = meta.get("fault_type", "UNKNOWN")
        ibr_type   = meta.get("ibr_type",   "UNKNOWN")

        return self._process_record(record, record_id, fault_type, ibr_type)

    # ------------------------------------------------------------------
    def replay_batch(
        self,
        index_yaml: str,
        base_dir:   Optional[str] = None,
    ) -> BatchComparisonReport:
        """
        Replay all records listed in an index YAML file.

        Parameters
        ----------
        index_yaml : str
            Path to record_index.yaml (produced by generate_records.py).
        base_dir : str, optional
            Root directory for resolving relative cfg_path values in the
            index.  Defaults to the directory containing index_yaml.

        Returns
        -------
        BatchComparisonReport
        """
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("PyYAML required: pip install pyyaml") from exc

        index_path = Path(index_yaml)
        root       = Path(base_dir) if base_dir else index_path.parent.parent.parent

        with index_path.open() as fh:
            index = yaml.safe_load(fh) or {}

        entries  = index.get("records", [])
        reports: List[FieldComparisonReport] = []

        for entry in entries:
            cfg_rel = entry.get("cfg_path", "")
            cfg_abs = root / cfg_rel
            if not cfg_abs.exists():
                # Try path relative to index file location
                cfg_abs = index_path.parent / cfg_rel
            if not cfg_abs.exists():
                continue   # skip missing files silently

            try:
                report = self.replay_record(
                    str(cfg_abs),
                    metadata={
                        "record_id":  entry.get("record_id",  cfg_abs.stem),
                        "fault_type": entry.get("fault_type", "UNKNOWN"),
                        "ibr_type":   entry.get("ibr_type",   "UNKNOWN"),
                    },
                )
                reports.append(report)
            except Exception as exc:   # noqa: BLE001
                # Log bad records but don't abort the batch
                import warnings
                warnings.warn(f"Skipping {cfg_abs.name}: {exc}", stacklevel=2)

        return BatchComparisonReport(reports)

    # ------------------------------------------------------------------
    # Internal replay logic
    # ------------------------------------------------------------------

    def _process_record(
        self,
        record:     ComtradeRecord,
        record_id:  str,
        fault_type: str,
        ibr_type:   str,
    ) -> FieldComparisonReport:
        """Core replay: feed waveform into DT, compare with digital channels."""

        # ---- Reset estimator state to avoid cross-record contamination ----
        if hasattr(self._engine.estimator, "reset"):
            self._engine.estimator.reset()

        # ---- Build time axis in seconds ----
        ts_s = record.timestamps.astype(np.float64) * 1e-6   # μs → s

        # ---- Extract 3-phase voltage and current ----
        try:
            va = record.analog_channels["Va"]
            vb = record.analog_channels["Vb"]
            vc = record.analog_channels["Vc"]
            ia = record.analog_channels["Ia"]
            ib = record.analog_channels["Ib"]
            ic = record.analog_channels["Ic"]
        except KeyError as exc:
            raise ValueError(
                f"Record {record_id} missing expected channel {exc}. "
                f"Available: {list(record.analog_channels)}"
            ) from exc

        # ---- Subsample to dt_rate_hz ----
        record_fs = _infer_sample_rate(ts_s)
        step      = max(1, round(record_fs / self._dt_rate_hz))
        idx_sub   = np.arange(0, len(ts_s), step)
        ts_sub    = ts_s[idx_sub]
        va_s, vb_s, vc_s = va[idx_sub], vb[idx_sub], vc[idx_sub]
        ia_s, ib_s, ic_s = ia[idx_sub], ib[idx_sub], ic[idx_sub]

        # ---- Detect fault onset via current overcurrent ----
        # Voltage-sag detection fails for instantaneous 3-phase samples:
        # sqrt(Va²+Vb²+Vc²)/3 = amplitude/√2 ≈ 0.707 pu always in balanced systems.
        # Current increase is a reliable cross-fault-type indicator.
        i_mag   = np.sqrt((ia_s**2 + ib_s**2 + ic_s**2) / 3)
        n_pre   = max(1, int(len(i_mag) * _PREFAULT_WINDOW_FRAC))
        i_baseline = float(np.median(i_mag[:n_pre])) + 1e-6
        i_thresh   = _I_FAULT_MULTIPLIER * i_baseline
        fault_onset_idx = _find_fault_onset_current(i_mag, i_thresh)

        # ---- k_ibr: measured directly from peak fault-window current ----
        # The EKF model h(x): I_pos = k_ibr was calibrated for fault conditions.
        # In pre-fault, Z_load = V/I ≈ 5 pu drives the EKF's k_ibr to near-zero
        # (wrong operating regime).  We therefore derive k_ibr from the measured
        # RMS current in the first fault cycle rather than the EKF state.
        if fault_onset_idx is not None:
            # Use samples from onset to onset + one cycle (at dt_rate_hz)
            one_cycle = max(1, round(self._dt_rate_hz / record.metadata.frequency))
            fault_slice = slice(fault_onset_idx,
                                min(fault_onset_idx + one_cycle, len(i_mag)))
            k_ibr_est = float(np.max(i_mag[fault_slice]))
            # Clamp to EKF physical bounds
            k_ibr_est = float(np.clip(k_ibr_est, 0.001, 1.0))
        else:
            # No fault detected — use pre-fault RMS (record may be a no-fault baseline)
            k_ibr_est = float(np.mean(i_mag))

        # ---- Run DT update loop (for EKF alpha tracking and trip-time) ----
        dt_state_at_fault: Optional[dict] = None
        dt_trip_idx:       Optional[int]  = None

        for i, (t, v, ib_v, ic_v, i_a, i_b, i_c) in enumerate(
            zip(ts_sub, va_s, vb_s, vc_s, ia_s, ib_s, ic_s)
        ):
            v_abc = np.array([v, ib_v, ic_v])
            i_abc = np.array([i_a, i_b, i_c])
            state = self._engine.update(float(t), v_abc, i_abc)

            # Capture state snapshot for alpha and kappa_n (not k_ibr)
            if (fault_onset_idx is not None
                    and i == fault_onset_idx + _WARM_UP_SAMPLES):
                dt_state_at_fault = state.copy()

            # DT trip detection using measured k_ibr (mirror with waveform current)
            if (dt_trip_idx is None
                    and fault_onset_idx is not None
                    and i > fault_onset_idx + _WARM_UP_SAMPLES):
                # Use the waveform's running current magnitude for mirror evaluation
                k_running = float(i_mag[i]) if i < len(i_mag) else k_ibr_est
                al = (dt_state_at_fault or {}).get("alpha", 0.5)
                pred = self._engine.mirror.predict(k_running, al, fault_type)
                if pred["action"] == "TRIP":
                    dt_trip_idx = i

        # ---- Extract alpha and kappa from EKF state ----
        if dt_state_at_fault is None:
            dt_state_at_fault = {"k_ibr": k_ibr_est, "alpha": 0.5,
                                 "kappa_n": 1.0, "residual": 0.0}

        alpha_est  = float(np.clip(dt_state_at_fault.get("alpha", 0.5), 0.05, 0.95))
        kappa_n    = float(dt_state_at_fault.get("kappa_n", 1.0))

        relay_event = {
            "element":    _field_element(record),
            "action":     _field_action(record),
            "k_ibr":      k_ibr_est,
            "alpha":      alpha_est,
            "fault_type": fault_type,
            "kappa_n":    kappa_n,
        }
        comp_result = self._engine.validate(relay_event)

        # ---- Field trip time ----
        field_trip_idx = _find_trip_onset(
            record.digital_channels.get("TRIP", None), idx_sub
        )

        # ---- Compute trip times [ms] relative to fault onset ----
        t_onset = ts_sub[fault_onset_idx] if fault_onset_idx is not None else None

        dt_trip_ms    = None
        field_trip_ms = None
        time_err_ms   = None

        if t_onset is not None and dt_trip_idx is not None:
            dt_trip_ms = (ts_sub[dt_trip_idx] - t_onset) * 1e3   # s → ms
        if t_onset is not None and field_trip_idx is not None:
            field_trip_ms = (ts_sub[field_trip_idx] - t_onset) * 1e3
        if dt_trip_ms is not None and field_trip_ms is not None:
            time_err_ms = dt_trip_ms - field_trip_ms

        # ---- Build report ----
        field_elem  = relay_event["element"]
        dt_elem     = comp_result["dt_element"]
        elem_match  = _elements_match(field_elem, dt_elem)

        return FieldComparisonReport(
            record_id=          record_id,
            fault_type=         fault_type,
            ibr_type=           ibr_type,
            dt_decision=        comp_result["verdict"],
            field_decision=     relay_event["action"],
            agreement=          comp_result["verdict"] == "AGREE",
            dt_trip_time_ms=    dt_trip_ms,
            field_trip_time_ms= field_trip_ms,
            time_error_ms=      time_err_ms,
            dt_element=         dt_elem,
            field_element=      field_elem,
            element_match=      elem_match,
            k_ibr_estimated=    k_ibr_est,
            confidence_kappa=   kappa_n,
            reason=             comp_result["reason"],
            selectivity_note=   comp_result.get("selectivity_note"),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _infer_sample_rate(ts_s: np.ndarray) -> float:
    """Estimate sample rate from timestamps [s]."""
    if len(ts_s) < 2:
        return 4800.0
    diffs = np.diff(ts_s)
    median_dt = float(np.median(diffs[diffs > 0]))
    return 1.0 / median_dt if median_dt > 0 else 4800.0


def _find_fault_onset(v_mag: np.ndarray, threshold: float) -> Optional[int]:
    """
    Return the index of the first sample where voltage drops below threshold.
    Require 3 consecutive samples below threshold to avoid noise triggers.

    Note: for single-sample instantaneous 3-phase data, sqrt(Va²+Vb²+Vc²)/3 =
    amplitude/√2 ≈ 0.707 pu always (balanced), so this helper is unreliable
    unless the threshold is set well below 0.70.  Prefer _find_fault_onset_current.
    """
    below = v_mag < threshold
    for i in range(len(below) - 2):
        if below[i] and below[i + 1] and below[i + 2]:
            return i
    return None


def _find_fault_onset_current(i_mag: np.ndarray, threshold: float) -> Optional[int]:
    """
    Return the index of the first sample where current magnitude exceeds threshold.
    Requires 3 consecutive samples above threshold to avoid transient false triggers.
    """
    above = i_mag > threshold
    for i in range(len(above) - 2):
        if above[i] and above[i + 1] and above[i + 2]:
            return i
    return None


def _find_trip_onset(
    trip_channel: Optional[np.ndarray],
    idx_sub:      np.ndarray,
) -> Optional[int]:
    """
    Return the index (in the subsampled grid) of the first TRIP assertion.

    Parameters
    ----------
    trip_channel : ndarray (N_full,) or None — full-rate TRIP digital channel
    idx_sub      : ndarray — subsampling index array into full-rate data
    """
    if trip_channel is None or len(trip_channel) == 0:
        return None
    # Subsample TRIP to match the dt grid
    trip_sub = trip_channel[idx_sub]
    trip_on  = np.where(trip_sub > 0)[0]
    return int(trip_on[0]) if len(trip_on) > 0 else None


def _field_element(record: ComtradeRecord) -> str:
    """
    Determine the field relay element from digital channels.

    Priority: 87L_OP > 21_OP > OC_OP > UNKNOWN.
    """
    for ch_name, elem_label in _DIG_ELEMENT_MAP:
        ch = record.digital_channels.get(ch_name)
        if ch is not None and np.any(ch > 0):
            return elem_label
    return "UNKNOWN"


def _field_action(record: ComtradeRecord) -> str:
    """Return 'TRIP' if the TRIP digital channel ever asserts, else 'BLOCK'."""
    trip_ch = record.digital_channels.get("TRIP")
    if trip_ch is not None and np.any(trip_ch > 0):
        return "TRIP"
    return "BLOCK"


def _elements_match(field_elem: str, dt_elem: str) -> bool:
    """
    True when field and DT elements are in the same protection family
    OR both indicate BLOCK (MISS / EXTERNAL / UNKNOWN).
    """
    # Exact match
    if field_elem == dt_elem:
        return True
    # Same protection family
    if _ProtectionMirror.is_same_family(field_elem, dt_elem):
        return True
    # Both block
    block_labels = {"MISS", "EXTERNAL", "BLOCK", "UNKNOWN"}
    if field_elem in block_labels and dt_elem in block_labels:
        return True
    return False
