# =============================================================================
# sambp / sambp_sync_oc
# io_utils/case_logger.py
#
# Structured per-case logging to a text file and optionally stdout.
#
# Public API
# ----------
# CaseLogger(log_dir, case_name, echo)  — class
#   .log(message)     — write timestamped line
#   .log_dict(d)      — write key-value block
#   .close()          — flush and close
#   .log_section(title) — write separator + title
# =============================================================================

import os
import sys
from datetime import datetime


class CaseLogger:
    """
    Per-case file logger.

    Creates one log file per case at:
        {log_dir}/{case_name}_{timestamp}.log

    Parameters
    ----------
    log_dir   : str  — directory for log files (e.g. "outputs/logs")
    case_name : str  — case identifier used in filename
    echo      : bool — if True, also prints to stdout (default True)
    """

    def __init__(self, log_dir, case_name, echo=True):
        os.makedirs(log_dir, exist_ok=True)
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"{case_name}_{ts}.log"
        self._path = os.path.join(log_dir, filename)
        self._echo = echo
        self._f    = open(self._path, "w")
        self.log_section(f"Case: {case_name}  |  Started: {ts}")

    # ------------------------------------------------------------------

    def log(self, message=""):
        """Write a timestamped log line."""
        ts   = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}]  {message}"
        self._f.write(line + "\n")
        self._f.flush()
        if self._echo:
            print(line)

    def log_dict(self, d, title=None):
        """
        Write a dict as indented key-value pairs.

        Parameters
        ----------
        d     : dict
        title : str or None — optional header line
        """
        if title:
            self.log(title)
        for k, v in d.items():
            if isinstance(v, float):
                self.log(f"    {k:<28} = {v:.6g}")
            else:
                self.log(f"    {k:<28} = {v}")

    def log_section(self, title=""):
        """Write a visual separator with title."""
        sep = "=" * 60
        self._f.write(f"\n{sep}\n  {title}\n{sep}\n")
        self._f.flush()
        if self._echo:
            print(f"\n{sep}\n  {title}\n{sep}")

    def close(self):
        """Flush and close the log file."""
        self.log(f"Logger closed. File: {self._path}")
        self._f.close()

    # ------------------------------------------------------------------
    # Context manager support
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def path(self):
        return self._path


# =============================================================================
# Module-level convenience function (no class instance needed)
# =============================================================================

def log_case_metadata(filepath, metadata):
    """
    Save case parameters and estimation results to a standalone metadata file.

    Useful for archiving the full configuration of a run alongside its outputs,
    without needing an active CaseLogger instance.

    Parameters
    ----------
    filepath : str  — output path (e.g. "outputs/logs/case_3ph_meta.txt")
    metadata : dict — arbitrary key-value pairs to record.
                      Nested dicts are written as indented sub-blocks.

    Notes
    -----
    Creates parent directory if needed. Appends a UTC timestamp header.
    """
    import os
    from datetime import datetime, timezone

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with open(filepath, "w") as f:
        f.write(f"# sambp_sync_oc — Case Metadata\n")
        f.write(f"# Written: {ts}\n")
        f.write("=" * 60 + "\n\n")
        _write_dict(f, metadata, indent=0)


def _write_dict(f, d, indent):
    """Recursively write dict as indented key: value lines."""
    prefix = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            f.write(f"{prefix}{k}:\n")
            _write_dict(f, v, indent + 1)
        elif isinstance(v, float):
            f.write(f"{prefix}  {k:<28} : {v:.8g}\n")
        else:
            f.write(f"{prefix}  {k:<28} : {v}\n")
