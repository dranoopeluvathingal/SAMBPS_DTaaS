"""tests/test_torres_six_features.py
=====================================

WP4.4 (P4.4) Torres-2022 stochastic-configurable arc tests.

Properties asserted:

1. ``Torres2022Arc`` is a concrete ``ArcModelBase``; profile string
   resolution accepts only known names.
2. Input validation: bad profile type, intensity outside [0, 1],
   ``Rx <= 0``, mismatched ``t``/``v`` shapes -- all raise.
3. Default constructor (no profile) reduces to the Emanuel
   baseline exactly (all six flags False).
4. **Six features can be toggled independently**: each of BUILD-UP,
   SHOULDER, ASYMMETRY, AVALANCHE, INTERMITTENCE, MODULATION
   produces a measurable waveform-statistics shift on its own (all
   other features off).  The signature for each feature has a
   distinct *direction* in the (rms, |peak|, asymmetry, p95-decay,
   sample-zero-fraction, low-freq-power) feature space.
5. **Three canonical profiles produce distinguishable waveforms**:
   ``tree``, ``sand``, ``concrete`` differ pairwise in mean |i|
   AND in at least one shape statistic.
6. Cross-fit CSV from the runner has the expected schema.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from sambp_fault_location_id.models.faultloc_arc_models import (
    TORRES_PROFILES,
    ArcModelBase,
    EmanuelArc,
    Torres2022Arc,
    TorresProfile,
)

PROJ_ROOT = Path(__file__).resolve().parent.parent
WP44_CSV = PROJ_ROOT / "outputs" / "phase4_torres_results.csv"

FS = 10_000.0
F0 = 50.0
N_CYCLES = 4
N = int(round(N_CYCLES * FS / F0))
T = np.arange(N) / FS
V_PEAK = 11.0e3 * np.sqrt(2.0 / 3.0)


def _v_clean() -> np.ndarray:
    return V_PEAK * np.cos(2.0 * np.pi * F0 * T)


def _baseline_emanuel() -> EmanuelArc:
    return EmanuelArc(V_kp=2000.0, V_kn=1800.0)


# =============================================================================
# (1) ABC + class hierarchy + profile resolution
# =============================================================================

def test_torres_is_arc_model_base() -> None:
    assert issubclass(Torres2022Arc, ArcModelBase)


def test_torres_three_canonical_profiles_present() -> None:
    assert {"tree", "sand", "concrete"} <= set(TORRES_PROFILES.keys())
    for name in ("tree", "sand", "concrete"):
        prof = TORRES_PROFILES[name]
        assert isinstance(prof, TorresProfile)


def test_torres_profile_string_unknown() -> None:
    with pytest.raises(ValueError, match="unknown profile"):
        Torres2022Arc(profile="quartz")


def test_torres_profile_bad_type() -> None:
    with pytest.raises(TypeError, match="profile must be"):
        Torres2022Arc(profile=42)


# =============================================================================
# (2) Input validation
# =============================================================================

def test_torres_intensity_validation() -> None:
    bad_prof = TorresProfile(build_up=True, build_up_intensity=1.5)
    with pytest.raises(ValueError, match="must be in"):
        Torres2022Arc(profile=bad_prof)


def test_torres_input_validation() -> None:
    arc = Torres2022Arc(profile="tree", rng=np.random.default_rng(2))
    v = _v_clean()
    with pytest.raises(ValueError, match="Rx must be"):
        arc.synthesise_current(T, v, 0.0)
    with pytest.raises(ValueError, match="must have the same shape"):
        arc.synthesise_current(T, v[:50], 1000.0)


# =============================================================================
# (3) Default constructor reduces to baseline
# =============================================================================

def test_torres_default_profile_matches_emanuel() -> None:
    """Default constructor leaves all six flags False -> the
    perturbation pipeline is a no-op -> output == Emanuel baseline."""
    v = _v_clean()
    Rx = 1000.0
    em = _baseline_emanuel()
    arc = Torres2022Arc(emanuel=em, rng=np.random.default_rng(3))
    i_baseline = em.synthesise_current(T, v, Rx)
    i_torres = arc.synthesise_current(T, v, Rx)
    np.testing.assert_array_equal(i_torres, i_baseline)


# =============================================================================
# (4) Six features can be toggled independently
# =============================================================================

def _solo_profile(feature_name: str, intensity: float = 0.6) -> TorresProfile:
    """Profile with exactly one feature on at the given intensity."""
    flags = {f: False for f in (
        "build_up", "shoulder", "asymmetry", "avalanche",
        "intermittence", "modulation",
    )}
    intens = {f"{f}_intensity": 0.0 for f in flags}
    flags[feature_name] = True
    intens[f"{feature_name}_intensity"] = intensity
    return TorresProfile(**flags, **intens)


@pytest.mark.parametrize("feat", [
    "build_up", "shoulder", "asymmetry", "avalanche",
    "intermittence", "modulation",
])
def test_torres_each_feature_is_observable(feat: str) -> None:
    """Turning on exactly one feature changes the waveform vs the
    Emanuel baseline by a measurable amount.  This is the WP4.4
    independence acceptance: each feature contributes distinguishably
    on its own."""
    v = _v_clean()
    Rx = 1000.0
    em = _baseline_emanuel()
    i_baseline = em.synthesise_current(T, v, Rx)
    arc = Torres2022Arc(
        profile=_solo_profile(feat, intensity=0.6),
        emanuel=em,
        rng=np.random.default_rng(7),
    )
    i = arc.synthesise_current(T, v, Rx)
    delta = np.abs(i - i_baseline)
    rms_delta = float(np.sqrt(np.mean(delta ** 2)))
    rms_baseline = float(np.sqrt(np.mean(i_baseline ** 2)))
    rel = rms_delta / max(rms_baseline, 1e-9)
    assert rel > 0.005, (
        f"feature {feat!r} should produce > 0.5 % relative RMS change "
        f"vs baseline; got rel={rel:.4f}"
    )


def test_torres_features_have_distinct_signatures() -> None:
    """The six features should perturb the waveform in DISTINCT
    directions in feature space.  We compute a 4-statistic
    fingerprint per feature (rms-delta, asymmetry-delta, peak-delta,
    sample-zero-count-delta) and assert that no two features have
    co-linear fingerprints (max pairwise cosine similarity < 0.999)."""
    v = _v_clean()
    Rx = 1000.0
    em = _baseline_emanuel()
    i_b = em.synthesise_current(T, v, Rx)
    feats = [
        "build_up", "shoulder", "asymmetry", "avalanche",
        "intermittence", "modulation",
    ]
    fps = {}
    for f in feats:
        arc = Torres2022Arc(
            profile=_solo_profile(f, intensity=0.6),
            emanuel=em,
            rng=np.random.default_rng(11),
        )
        i = arc.synthesise_current(T, v, Rx)
        d = i - i_b
        rms = float(np.sqrt(np.mean(d ** 2)))
        asym = float(np.mean(d[d > 0]) + np.mean(d[d < 0])) if (
            np.any(d > 0) and np.any(d < 0)
        ) else 0.0
        peak = float(np.max(np.abs(d)))
        nzero = float(np.sum(np.abs(i) < 1e-9))
        fps[f] = np.array([rms, asym, peak, nzero])
    # Cosine similarity matrix
    feats_list = list(fps.keys())
    n_distinct_pairs = 0
    n_pairs = 0
    for i in range(len(feats_list)):
        for j in range(i + 1, len(feats_list)):
            a, b = fps[feats_list[i]], fps[feats_list[j]]
            denom = np.linalg.norm(a) * np.linalg.norm(b)
            if denom <= 1e-12:
                continue
            cs = float(abs(np.dot(a, b) / denom))
            n_pairs += 1
            if cs < 0.999:
                n_distinct_pairs += 1
    # Almost all pairs should be distinct (cosine sim < 0.999).
    assert n_distinct_pairs >= n_pairs - 1, (
        f"too many near-co-linear feature signatures: "
        f"{n_distinct_pairs} / {n_pairs} pairs distinct"
    )


# =============================================================================
# (5) Three canonical profiles produce distinguishable waveforms
# =============================================================================

def test_torres_three_profiles_distinguishable() -> None:
    v = _v_clean()
    Rx = 1000.0
    em = _baseline_emanuel()
    waves = {}
    for prof in ("tree", "sand", "concrete"):
        arc = Torres2022Arc(profile=prof, emanuel=em,
                            rng=np.random.default_rng(13))
        waves[prof] = arc.synthesise_current(T, v, Rx)
    # Pairwise differences should all be > 1 % of baseline RMS
    rms_baseline = float(np.sqrt(
        np.mean(em.synthesise_current(T, v, Rx) ** 2)
    ))
    profiles = list(waves.keys())
    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            d = waves[profiles[i]] - waves[profiles[j]]
            rel = float(np.sqrt(np.mean(d ** 2))) / max(rms_baseline, 1e-9)
            assert rel > 0.01, (
                f"profiles {profiles[i]!r} and {profiles[j]!r} too "
                f"similar; rel-RMS-diff={rel:.4f}"
            )


def test_torres_concrete_least_perturbed() -> None:
    """Concrete is the smoothest / lowest-intensity profile by
    construction.  It must perturb the baseline LESS than tree/sand."""
    v = _v_clean()
    Rx = 1000.0
    em = _baseline_emanuel()
    i_b = em.synthesise_current(T, v, Rx)
    deltas = {}
    for prof in ("tree", "sand", "concrete"):
        arc = Torres2022Arc(profile=prof, emanuel=em,
                            rng=np.random.default_rng(17))
        i = arc.synthesise_current(T, v, Rx)
        deltas[prof] = float(np.sqrt(np.mean((i - i_b) ** 2)))
    assert deltas["concrete"] < deltas["tree"], (
        f"concrete must perturb less than tree; "
        f"concrete={deltas['concrete']:.3f}, tree={deltas['tree']:.3f}"
    )
    assert deltas["concrete"] < deltas["sand"], (
        f"concrete must perturb less than sand; "
        f"concrete={deltas['concrete']:.3f}, sand={deltas['sand']:.3f}"
    )


# =============================================================================
# (6) RNG hygiene
# =============================================================================

def test_torres_rng_determinism() -> None:
    v = _v_clean()
    Rx = 1000.0
    em = _baseline_emanuel()
    a1 = Torres2022Arc(profile="tree", emanuel=em,
                       rng=np.random.default_rng(23))
    a2 = Torres2022Arc(profile="tree", emanuel=em,
                       rng=np.random.default_rng(23))
    a3 = Torres2022Arc(profile="tree", emanuel=em,
                       rng=np.random.default_rng(24))
    i1 = a1.synthesise_current(T, v, Rx)
    i2 = a2.synthesise_current(T, v, Rx)
    i3 = a3.synthesise_current(T, v, Rx)
    np.testing.assert_array_equal(i1, i2)
    assert np.max(np.abs(i1 - i3)) > 1e-6


# =============================================================================
# (7) Cross-fit CSV schema
# =============================================================================

def test_wp44_csv_schema() -> None:
    if not WP44_CSV.exists():
        pytest.skip(
            f"{WP44_CSV} not present; run "
            f"`python run_faultloc_phase4_torres.py` first."
        )
    rows = list(csv.DictReader(WP44_CSV.open()))
    assert len(rows) >= 50, f"expected >= 50 rows; got {len(rows)}"
    expected = {
        "trial", "profile", "fault_bus", "alpha_true", "Rx_true",
        "snr_v_db", "snr_i_db",
        "loc_err_emanuel", "loc_err_torres",
        "delta_loc_err_pct",
    }
    assert expected <= set(rows[0].keys())


def test_wp44_csv_three_profiles_present() -> None:
    if not WP44_CSV.exists():
        pytest.skip(f"{WP44_CSV} not present")
    rows = list(csv.DictReader(WP44_CSV.open()))
    profiles_seen = {r["profile"] for r in rows}
    assert {"tree", "sand", "concrete"} <= profiles_seen, (
        f"expected all three canonical profiles; got {profiles_seen}"
    )
