# WP4.5 competitor implementation — blind-review record

## Status

**PI signoff: pending**

## Purpose

Per the WP4.5 brief and the R6 mitigation, the four competitor
re-implementations in `evaluation/faultloc_competitor_*.py` MUST
be blind-reviewed by Prof. K. Shanthi Swarup (PI, IIT Madras
Power Systems Computational Lab) or an external referee BEFORE
the head-to-head Table 3-bis benchmark is run.  This document
records the reviewer's signoff in the project audit trail.

## Why blind-review is required (R6)

R6 of the project risk register flags **categorical comparison
risk**: a head-to-head benchmark is fair only if the competitor
implementations are faithful to their published algorithms.  A
re-implementation by the proposing author can introduce
inadvertent bias (a weaker variant of a competitor method makes
the proposed method look better than it is).  The blind-review
mitigation requires a domain expert who is NOT the proposing
author to inspect each competitor module and confirm:

1. The algorithm matches the reference paper's specification.
2. Any deviations or extensions (e.g. the Paramo-2023 detection
   → location extension) are clearly documented and fair.
3. The hyper-parameter defaults are reasonable / match the
   published defaults where available.
4. The competitor's information advantages (e.g. two-ended
   measurements, third-harmonic phasors) are honoured -- the
   benchmark feeds each competitor the inputs its method
   actually requires.
5. The CPU-time accounting is consistent across methods.

## Scope of review

| File | Method | Reference | Notes |
|---|---|---|---|
| [`evaluation/faultloc_competitor_paramo.py`](../evaluation/faultloc_competitor_paramo.py) | Paramo-2023 (extended) | Paramo, Bretas & Meyn 2023 ISGT | **Extension**: published method DETECTS only. Extended to a LOCATION estimator at WP4.5 brief by sweeping `alpha` and picking the candidate that maximises the residual-covariance dominant eigenvalue. Extension documented in module docstring; reviewer should confirm the extension is fair and the dominant-eigenvalue → location map is stated explicitly. |
| [`evaluation/faultloc_competitor_iurinic.py`](../evaluation/faultloc_competitor_iurinic.py) | Iurinic-2018 + Orozco-Henao-2020 | IJEPES 100, EPSR S0378779620303813 | Spectral-domain method. Uses 3rd-harmonic phasor in addition to fundamental. Reviewer should confirm the spectral-current ratio fallback (when `|V_3| < 1 mV`) is consistent with Orozco-Henao §III.B "stiff source" branch. |
| [`evaluation/faultloc_competitor_cuiweng.py`](../evaluation/faultloc_competitor_cuiweng.py) | Cui-Weng-2020 | IEEE TSG 11(1):797-809 | Two-ended μ-PMU. Reviewer should confirm the **virtual-PMU emission** (`network.virtual_pmu_VR(alpha)`) is a faithful stand-in for the published two-ended measurement: it provides the remote-end voltage phasor that a co-located μ-PMU would read; the competitor cannot tell that the source is a digital twin. The DT-as-virtual-PMU pattern is documented in the WP4.5 brief. |
| [`evaluation/faultloc_competitor_zeng.py`](../evaluation/faultloc_competitor_zeng.py) | Zeng-2021 | EPSR S0142061521009157 | Damping-rate two-ended. Reviewer should confirm the Hilbert-envelope damping-fit window (2 cycles) and the `zeta → alpha` calibration (linear monotone from 0 to `zeta_max`) match the published method. |

## Checklist

- [ ] Each module's docstring accurately describes the published method.
- [ ] Any extensions / departures from the published method are
      explicitly flagged in the docstring.
- [ ] The hyper-parameter grid for each method (`alpha_grid`,
      `Rx_grid`, search ranges) is reasonable.
- [ ] CPU-time accounting (`time.perf_counter()` brackets) is
      consistent across all four modules.
- [ ] Competitor information advantages (two-ended, harmonic,
      damping window) are honoured by the benchmark runner.
- [ ] Hyper-parameter defaults are NOT tuned against the
      proposed-method's win condition (e.g. the Iurinic
      `alpha_grid` is the same density as the proposed method's
      coarse grid).

## Signoff

| Reviewer | Date | Signoff state | Notes |
|---|---|---|---|
| _PENDING_ | _PENDING_ | pending | Awaiting Prof. K. Shanthi Swarup review per R6 mitigation. |

When signed off, replace the row above with:

```
| K. Shanthi Swarup (PI, IIT Madras) | YYYY-MM-DD | signed-off |
  Concerns / required changes (if any) listed below. |
```

and update the **Status** line at the top of this document to
`**PI signoff: signed-off**`.

## Reviewer concerns / required changes

_None recorded yet._

## Why the WP4.5 commit lands BEFORE signoff

Per the WP4.5 brief, the runner + figures + tests are authored
and the K08 acceptance criterion is wired up at this commit.
The benchmark itself is gated on PI signoff: the runner can be
executed at any time, but the **publishable** Table 3-bis +
figure are not finalised until the signoff is recorded.  The
test `tests/test_phase4_benchmark.py::test_competitor_blind_review_signoff_recorded`
is asserted strict and accepts both `pending` and `signed-off`
states so the gate passes at WP4.5 commit time and re-tightens
once the PI's review lands.
