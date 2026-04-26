# =============================================================================
# sambp / digital_twin / validation / decision_comparator.py
#
# DT-relay decision comparator (TR-45 Study A / Study C).
#
# Compares the physical relay's actual action against the DT's expected
# outcome (from ProtectionMirror + ScenarioLibrary) and classifies the
# result as AGREE, FLAG_FP, FLAG_FN, FLAG_ELEMENT, or FLAG_CONF.
#
# The comparator does NOT block relay operation — it runs in the
# non-blocking post-event path and feeds FlagEngine for auditing.
#
# Verdict taxonomy (revised TR-45 v2)
# ------------------------------------
#   AGREE        — relay action matches DT prediction in *outcome*:
#                  (a) exact element match, or
#                  (b) both TRIP and same protection family
#                      (e.g. relay used Z1/87L, DT predicted 87L —
#                       both correctly identified an in-zone fault;
#                       the difference is speed, not protection outcome).
#                  For (b), 'selectivity_note' is set in the result dict.
#
#   FLAG_FP      — relay tripped; DT predicted BLOCK/MISS
#                  (possible over-reach or spurious operation)
#
#   FLAG_FN      — relay blocked/missed; DT predicted TRIP
#                  (possible under-reach or IBR blind spot)
#
#   FLAG_ELEMENT — relay and DT both tripped but from *different families*
#                  (e.g. relay used 87L, DT predicted OC — different
#                   protection philosophy; warrants investigation)
#
#   FLAG_CONF    — relay action agrees with DT direction but DT confidence
#                  is below threshold; borderline operating point
#
# Same-family logic
# -----------------
# Protection families are defined in ProtectionMirror.TRIP_FAMILIES:
#   'line'  → Z1/87L, 87L      (pilot distance + line differential)
#   'xfmr'  → 87T
#   'bus'   → 87B
#   'oc'    → OC
#   None    → MISS, EXTERNAL
#
# Public API
# ----------
# cmp = DecisionComparator(mirror, conf_threshold=0.15, kappa_threshold=30.0)
# result = cmp.compare(relay_event, dt_expected)
#   → dict with keys: verdict, selectivity_note, reason, relay_element,
#                     dt_element, relay_action, dt_action, confidence,
#                     near_boundary, kappa_n, k_ibr, alpha, lib_outcome
# cmp.verdict_is_flag(verdict)  → bool
# =============================================================================

from ..models.protection_mirror import ProtectionMirror

# Element pickup thresholds (must match ProtectionMirror module constants)
_THRESH_OC   = 0.050   # pu
_THRESH_87L  = 0.060   # pu
_THRESH_Z1   = 0.100   # pu
# Relative deadband around each threshold: k within ±_DEADBAND_REL of a
# threshold is "near threshold" — single-sample relay vs EKF may legitimately
# differ here, so direction mismatches are reclassified as FLAG_CONF.
_DEADBAND_REL = 0.08   # 8 % relative (≈ 2σ for 5 % relay measurement noise)
_THRESHOLDS   = [_THRESH_OC, _THRESH_87L, _THRESH_Z1]


def _near_any_threshold(k_ibr):
    """True if k_ibr is within ±_DEADBAND_REL of any element pickup threshold."""
    return any(abs(k_ibr - t) / t < _DEADBAND_REL for t in _THRESHOLDS)


class DecisionComparator:
    """
    Compare relay decision with DT prediction and classify the verdict.

    Parameters
    ----------
    mirror          : ProtectionMirror — shared mirror instance
    conf_threshold  : float — min DT confidence to suppress FLAG_CONF (0.15)
    kappa_threshold : float — max κ_n for EKF estimates to be trusted (30.0)
    """

    def __init__(self, mirror, conf_threshold=0.15, kappa_threshold=30.0):
        self.mirror          = mirror
        self.conf_threshold  = conf_threshold
        self.kappa_threshold = kappa_threshold

    # ------------------------------------------------------------------
    def compare(self, relay_event, dt_expected):
        """
        Core comparison: relay event vs DT mirror prediction.

        Parameters
        ----------
        relay_event : dict
            Required keys:
                element    : str   — relay element that operated
                action     : str   — 'TRIP' or 'BLOCK'
                k_ibr      : float — DT-estimated k_ibr (for mirror eval)
                alpha      : float — DT-estimated alpha  (for mirror eval)
                fault_type : str   — fault type label
            Optional keys:
                kappa_n    : float — EKF condition number at event time
                r_arc      : float — arc resistance if known [pu]

        dt_expected : dict
            From ScenarioLibrary.nearest(); contains 'expected_outcome'.

        Returns
        -------
        result : dict
            verdict          : str   — see taxonomy above
            selectivity_note : str or None
                               Set when verdict=AGREE but relay and DT used
                               different elements within the same family.
                               e.g. "Relay Z1/87L (20 ms) vs DT 87L (30 ms);
                               both correct, DT near Z1 boundary."
            reason           : str   — human-readable explanation
            relay_element    : str
            dt_element       : str
            relay_action     : str
            dt_action        : str
            confidence       : float — DT mirror confidence
            near_boundary    : bool  — operating point near Z1/87L boundary
            kappa_n          : float
            k_ibr            : float — DT-estimated k_ibr used for mirror
            alpha            : float — DT-estimated alpha used for mirror
            lib_outcome      : str   — nearest-neighbour library outcome
        """
        r_elem   = relay_event.get('element',    'UNKNOWN')
        r_action = relay_event.get('action',     'UNKNOWN')
        k_ibr    = relay_event.get('k_ibr',      0.0)
        alpha    = relay_event.get('alpha',      0.5)
        ft       = relay_event.get('fault_type', 'SLG')
        kappa_n  = relay_event.get('kappa_n',    1.0)
        r_arc    = relay_event.get('r_arc',      0.0)

        # DT mirror prediction at estimated operating point
        mirror_pred  = self.mirror.predict(k_ibr, alpha, ft, r_arc=r_arc)
        dt_elem      = mirror_pred['element']
        dt_action    = mirror_pred['action']
        dt_conf      = mirror_pred['confidence']
        near_bnd     = mirror_pred.get('near_boundary', False)

        lib_outcome  = dt_expected.get('expected_outcome', 'UNKNOWN')

        r_trips = r_action == 'TRIP'
        d_trips = dt_action == 'TRIP'
        kappa_ok = kappa_n < self.kappa_threshold

        selectivity_note = None

        # ── Classify verdict ─────────────────────────────────────────────
        if r_action == dt_action:
            # ── Correct trip/block direction ─────────────────────────
            if r_elem == dt_elem or not r_trips:
                # Exact element match, or both blocked (element irrelevant for block)
                verdict, reason = self._agree_or_conf(
                    r_elem, r_action, dt_elem, dt_action,
                    dt_conf, kappa_ok, k_ibr, alpha)

            elif ProtectionMirror.is_same_family(r_elem, dt_elem):
                # Same protection family — AGREE, but note the element difference
                verdict = 'AGREE'
                selectivity_note = (
                    f"Element mismatch within '{ProtectionMirror.TRIP_FAMILIES[r_elem]}' "
                    f"family: relay used {r_elem}, DT predicted {dt_elem}. "
                    f"{'Near Z1/87L boundary (α={:.3f}). '.format(alpha) if near_bnd else ''}"
                    f"Both correctly identify in-zone fault; difference is speed/selectivity only.")
                reason = (f"AGREE (same family): relay {r_elem} ({r_action}), "
                          f"DT {dt_elem} ({dt_action}), k={k_ibr:.3f}, α={alpha:.3f}")

            else:
                # Both TRIP but different protection families — genuine FLAG_ELEMENT
                verdict = 'FLAG_ELEMENT'
                reason  = (
                    f"Cross-family element mismatch: relay used {r_elem} "
                    f"(family '{ProtectionMirror.TRIP_FAMILIES.get(r_elem)}') "
                    f"but DT predicted {dt_elem} "
                    f"(family '{ProtectionMirror.TRIP_FAMILIES.get(dt_elem)}'). "
                    f"k={k_ibr:.3f}, α={alpha:.3f}. Investigate element selectivity.")

        elif r_trips and not d_trips:
            # Relay tripped; DT predicted BLOCK.
            # Near-threshold case: relay measurement pushed k over threshold but
            # EKF estimate sits below it — not a genuine false positive, just
            # measurement uncertainty.  Reclassify as FLAG_CONF.
            if _near_any_threshold(k_ibr):
                verdict = 'FLAG_CONF'
                reason  = (f"Relay {r_elem} TRIP but DT predicted {dt_elem} ({dt_action}). "
                           f"k_ibr={k_ibr:.3f} is near a pickup threshold "
                           f"(deadband ±{_DEADBAND_REL*100:.0f}%); "
                           f"disagreement attributed to single-sample measurement "
                           f"uncertainty, not protection failure.")
            else:
                verdict = 'FLAG_FP'
                reason  = (f"Relay {r_elem} TRIP but DT predicted {dt_elem} ({dt_action}). "
                           f"k_ibr={k_ibr:.3f} is far from all thresholds — "
                           f"possible over-reach or spurious operation. "
                           f"Library: {lib_outcome}. α={alpha:.3f}. κ_n={kappa_n:.1f}.")

        else:
            # Relay blocked; DT predicted TRIP.
            if _near_any_threshold(k_ibr):
                verdict = 'FLAG_CONF'
                reason  = (f"Relay {r_elem} BLOCK but DT predicted {dt_elem} ({dt_action}). "
                           f"k_ibr={k_ibr:.3f} is near a pickup threshold "
                           f"(deadband ±{_DEADBAND_REL*100:.0f}%); "
                           f"disagreement attributed to measurement uncertainty.")
            else:
                verdict = 'FLAG_FN'
                reason  = (f"Relay {r_elem} BLOCK but DT predicted {dt_elem} ({dt_action}). "
                           f"k_ibr={k_ibr:.3f} is far from all thresholds — "
                           f"possible under-reach or IBR blind spot. "
                           f"Library: {lib_outcome}. α={alpha:.3f}. κ_n={kappa_n:.1f}.")

        return {
            'verdict':          verdict,
            'selectivity_note': selectivity_note,
            'reason':           reason,
            'relay_element':    r_elem,
            'dt_element':       dt_elem,
            'relay_action':     r_action,
            'dt_action':        dt_action,
            'confidence':       dt_conf,
            'near_boundary':    near_bnd,
            'kappa_n':          kappa_n,
            'k_ibr':            k_ibr,
            'alpha':            alpha,
            'lib_outcome':      lib_outcome,
        }

    # ------------------------------------------------------------------
    def _agree_or_conf(self, r_elem, r_action, dt_elem, dt_action,
                       dt_conf, kappa_ok, k_ibr, alpha):
        """Return (verdict, reason) for cases where action and element agree."""
        if kappa_ok and dt_conf < self.conf_threshold:
            verdict = 'FLAG_CONF'
            reason  = (f"Relay {r_elem} ({r_action}) agreed with DT but "
                       f"confidence {dt_conf:.3f} < threshold {self.conf_threshold:.2f}. "
                       f"Borderline operating point (k={k_ibr:.3f}, α={alpha:.3f}).")
        else:
            verdict = 'AGREE'
            reason  = (f"Relay {r_elem} ({r_action}) matches DT {dt_elem} ({dt_action}). "
                       f"conf={dt_conf:.3f}, κ_n_ok={kappa_ok}.")
        return verdict, reason

    # ------------------------------------------------------------------
    @staticmethod
    def verdict_is_flag(verdict):
        """Return True if the verdict requires operator attention."""
        return verdict.startswith('FLAG')

    @staticmethod
    def verdict_is_agree(verdict):
        """Return True if the verdict indicates correct relay operation."""
        return verdict == 'AGREE'
