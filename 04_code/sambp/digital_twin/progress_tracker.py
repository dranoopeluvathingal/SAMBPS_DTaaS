"""
progress_tracker.py — TR progress dashboard for the SAMBP Digital Twin Lab.

Usage
-----
    python progress_tracker.py                   # print dashboard
    python progress_tracker.py --update TR-56 status=in_progress wp_done=2
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

PROGRESS_FILE = Path(__file__).with_name("PROGRESS.yaml")

STATUS_SYMBOLS = {
    "not_started": "·",
    "in_progress":  "▶",
    "complete":     "✓",
}
STATUS_ORDER = {"not_started": 0, "in_progress": 1, "complete": 2}


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load() -> dict:
    with PROGRESS_FILE.open() as fh:
        return yaml.safe_load(fh)


def _save(data: dict) -> None:
    with PROGRESS_FILE.open("w") as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_tr(tr_id: str, **kwargs: Any) -> None:
    """Update fields for a single TR and persist to PROGRESS.yaml.

    Parameters
    ----------
    tr_id : str
        TR identifier, e.g. ``'TR-56'``.
    **kwargs :
        Field name / value pairs to update.  Recognised keys:
        ``status``, ``wp_done``, ``wp_total``, ``agree_rate``.
    """
    data = _load()
    trs: dict = data.get("trs", {})
    if tr_id not in trs:
        raise KeyError(f"Unknown TR: {tr_id!r}.  Valid IDs: {list(trs)}")
    entry = trs[tr_id]
    valid_keys = {"status", "wp_done", "wp_total", "agree_rate"}
    for key, value in kwargs.items():
        if key not in valid_keys:
            raise ValueError(f"Unknown field {key!r}.  Valid fields: {valid_keys}")
        if key == "status" and value not in STATUS_SYMBOLS:
            raise ValueError(f"status must be one of {list(STATUS_SYMBOLS)}")
        entry[key] = value
    entry["last_updated"] = datetime.date.today().isoformat()
    _save(data)
    print(f"Updated {tr_id}: {kwargs}")


def print_dashboard() -> None:
    """Print a formatted progress table to stdout."""
    data = _load()
    trs: dict = data.get("trs", {})

    # column widths
    w_id    = 7
    w_title = 46
    w_stat  = 13
    w_wp    = 10
    w_agr   = 9
    w_date  = 12
    sep = "─" * (w_id + w_title + w_stat + w_wp + w_agr + w_date + 13)

    header = (
        f"{'TR':<{w_id}}  {'Title':<{w_title}}  {'Status':<{w_stat}}  "
        f"{'WP':>{w_wp}}  {'Agree':>{w_agr}}  {'Updated':<{w_date}}"
    )
    print()
    print("  SAMBP Digital Twin Lab — TR Progress Dashboard")
    print(f"  {sep}")
    print(f"  {header}")
    print(f"  {sep}")

    counts = {k: 0 for k in STATUS_SYMBOLS}
    for tr_id, entry in trs.items():
        status = entry.get("status", "not_started")
        symbol = STATUS_SYMBOLS.get(status, "?")
        wp_done  = entry.get("wp_done", 0)
        wp_total = entry.get("wp_total", 0)
        agree    = entry.get("agree_rate")
        updated  = entry.get("last_updated") or "—"
        title    = entry.get("title", "")[:w_title]

        agree_str = f"{agree:.1%}" if agree is not None else "—"
        wp_str    = f"{wp_done}/{wp_total}"
        status_str = f"{symbol} {status}"

        print(
            f"  {tr_id:<{w_id}}  {title:<{w_title}}  {status_str:<{w_stat}}  "
            f"{wp_str:>{w_wp}}  {agree_str:>{w_agr}}  {updated:<{w_date}}"
        )
        counts[status] += 1

    n_total = len(trs)
    n_done  = counts["complete"]
    print(f"  {sep}")
    print(
        f"  Totals: {n_total} TRs  |  "
        f"✓ {counts['complete']} complete  "
        f"▶ {counts['in_progress']} in-progress  "
        f"· {counts['not_started']} not started  "
        f"|  {n_done/n_total:.0%} done"
    )
    print()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SAMBP TR progress tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python progress_tracker.py\n"
            "  python progress_tracker.py --update TR-56 status=in_progress wp_done=2\n"
            "  python progress_tracker.py --update TR-45 agree_rate=0.97 status=complete\n"
        ),
    )
    parser.add_argument(
        "--update", nargs="+", metavar=("TR_ID", "KEY=VAL"),
        help="Update a TR: first arg is TR-ID, remainder are KEY=VALUE pairs",
    )
    return parser.parse_args()


def _coerce(value: str) -> Any:
    """Try int → float → str coercion for CLI values."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


if __name__ == "__main__":
    args = _parse_args()
    if args.update:
        tr_id, *pairs = args.update
        kwargs = {}
        for pair in pairs:
            if "=" not in pair:
                sys.exit(f"Expected KEY=VALUE, got: {pair!r}")
            k, v = pair.split("=", 1)
            kwargs[k] = _coerce(v)
        update_tr(tr_id, **kwargs)
    print_dashboard()
