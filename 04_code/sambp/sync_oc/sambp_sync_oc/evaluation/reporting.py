# =============================================================================
# sambp / sambp_sync_oc
# evaluation/reporting.py
#
# Save case summaries and generate console reports.
#
# Public API
# ----------
# save_case_summary_csv(results, output_path)  → None
# print_case_summary(summary_dict)             → None
# print_batch_summary(summaries)               → None
# =============================================================================

import csv
import os


def save_case_summary_csv(results, output_path):
    """
    Save case-wise performance summary to CSV.

    Parameters
    ----------
    results     : list[dict] — from comparison.summarise_batch()
    output_path : str        — full path to output .csv file

    Notes
    -----
    - Creates parent directory if it does not exist.
    - Fieldnames are taken from the first dict in results.
    - NaN values are written as empty strings.
    """
    if not results:
        return

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fieldnames = list(results[0].keys())

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            clean = {
                k: ("" if (isinstance(v, float) and v != v) else v)
                for k, v in row.items()
            }
            writer.writerow(clean)


def print_case_summary(summary):
    """
    Print a single case summary to stdout in a readable format.

    Parameters
    ----------
    summary : dict — from compare_fixed_vs_adaptive()
    """
    sep = "─" * 60
    print(sep)
    print(f"  Case : {summary.get('case_name', '?')}   "
          f"Fault: {summary.get('fault_type', '?')}   "
          f"Rf={summary.get('fault_R_pu', float('nan')):.3f} pu")
    print(sep)
    print(f"  Fit   RMSE={summary.get('rmse_combined', float('nan')):.4f} pu   "
          f"R²={summary.get('r2_combined', float('nan')):.4f}")
    print(f"  Conf  γ={summary.get('confidence', float('nan')):.3f}")
    print(f"  Fixed    pickup={summary.get('fixed_pickup_pu', float('nan')):.3f}  "
          f"tms={summary.get('fixed_tms', float('nan')):.4f}  "
          f"trip={_fmt_time(summary.get('fixed_trip_time'))}")
    print(f"  Adapt    pickup={summary.get('adaptive_pickup_pu', float('nan')):.3f}  "
          f"tms={summary.get('adaptive_tms', float('nan')):.4f}  "
          f"trip={_fmt_time(summary.get('adaptive_trip_time'))}")
    delta = summary.get("trip_time_delta")
    if delta is not None and delta == delta:
        sign = "faster" if delta < 0 else "slower"
        print(f"  Δtrip = {delta*1000:+.1f} ms  ({sign})")
    print(f"  Speed improvement : {summary.get('speed_improvement', False)}")
    print(f"  Security maintained: {summary.get('security_maintained', True)}")
    print(sep)


def print_batch_summary(summaries):
    """
    Print a compact table for all cases in a batch study.

    Parameters
    ----------
    summaries : list[dict] — from comparison.summarise_batch()
    """
    header = (f"{'Case':<22} {'Fault':<5} {'Rf':>5}  "
              f"{'RMSE':>7}  {'γ':>5}  "
              f"{'Fixed t':>8}  {'Adapt t':>8}  {'Δt(ms)':>8}  "
              f"{'Speed':>6}  {'Secure':>6}")
    sep = "─" * len(header)
    print(sep)
    print(header)
    print(sep)
    for s in summaries:
        delta = s.get("trip_time_delta")
        delta_str = f"{delta*1000:+.1f}" if (delta is not None and delta == delta) else "  —"
        print(
            f"{s.get('case_name',''):<22} "
            f"{s.get('fault_type',''):<5} "
            f"{s.get('fault_R_pu', float('nan')):>5.3f}  "
            f"{s.get('rmse_combined', float('nan')):>7.4f}  "
            f"{s.get('confidence', float('nan')):>5.3f}  "
            f"{_fmt_time(s.get('fixed_trip_time')):>8}  "
            f"{_fmt_time(s.get('adaptive_trip_time')):>8}  "
            f"{delta_str:>8}  "
            f"{'Yes' if s.get('speed_improvement') else 'No':>6}  "
            f"{'Yes' if s.get('security_maintained', True) else 'NO':>6}"
        )
    print(sep)


def _fmt_time(t):
    """Format trip time (s) as ms string, or '—' if None/NaN."""
    if t is None:
        return "—"
    try:
        if t != t:  # NaN
            return "—"
        return f"{t*1000:.1f} ms"
    except TypeError:
        return "—"
