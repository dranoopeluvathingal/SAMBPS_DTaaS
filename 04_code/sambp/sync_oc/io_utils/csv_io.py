# =============================================================================
# sambp / sambp_sync_oc
# io_utils/csv_io.py
#
# Save and load waveform data in CSV format.
#
# Public API
# ----------
# save_waveform_csv(filepath, data_dict)  → None
# load_waveform_csv(filepath)             → dict
# =============================================================================

import os
import csv
import numpy as np


def save_waveform_csv(filepath, data_dict):
    """
    Save waveform data dict to a CSV file.

    Parameters
    ----------
    filepath  : str  — output path (e.g. "outputs/waveforms/case_3ph.csv")
    data_dict : dict — {column_name: array-like}
                Keys become column headers; all arrays must be equal length.
                Typical keys: "t", "ia", "ib", "ic", "va", "vb", "vc", "i_rms"

    Notes
    -----
    - Creates parent directory if needed.
    - Values written with 8 significant figures.
    """
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

    arrays   = {k: np.asarray(v, dtype=float) for k, v in data_dict.items()}
    lengths  = {k: len(v) for k, v in arrays.items()}
    if len(set(lengths.values())) > 1:
        raise ValueError(
            f"All arrays must have equal length. Got: {lengths}"
        )

    fieldnames = list(arrays.keys())
    n          = next(iter(lengths.values()))

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for i in range(n):
            writer.writerow([f"{arrays[k][i]:.8g}" for k in fieldnames])


def load_waveform_csv(filepath):
    """
    Load a waveform CSV into a dict of numpy arrays.

    Parameters
    ----------
    filepath : str — path to CSV file saved by save_waveform_csv

    Returns
    -------
    dict — {column_name: ndarray(float)}
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Waveform CSV not found: {filepath}")

    data = {}
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for key, val in row.items():
                data.setdefault(key, []).append(float(val))

    return {k: np.array(v, dtype=float) for k, v in data.items()}
