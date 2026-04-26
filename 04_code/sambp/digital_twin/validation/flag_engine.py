# =============================================================================
# sambp / digital_twin / validation / flag_engine.py
#
# Flag accumulation, statistics, and model-update trigger (TR-45 Study C/D).
#
# The FlagEngine receives verdict dicts from DecisionComparator and:
#   1. Accumulates counts by verdict type and k_ibr region
#   2. Computes rolling FP/FN rates
#   3. Triggers a "model update" notification when flag rates exceed thresholds
#      (the trigger itself is a callback — the DT does NOT auto-update relay
#       settings without operator confirmation)
#
# Flag rate thresholds (TR-45 Study C)
# -------------------------------------
#   FLAG_FP rate > 5%  in any k_ibr region → trigger model review
#   FLAG_FN rate > 2%  in any k_ibr region → trigger urgent review
#   FLAG_CONF rate > 15% overall           → trigger threshold recalibration
#
# Public API
# ----------
# eng = FlagEngine(on_trigger=None)
# eng.record(comparator_result)
# eng.summary()          → dict of counts and rates
# eng.flag_log           → list of all flagged results
# eng.reset()
# =============================================================================

from collections import defaultdict, Counter


# k_ibr operating regions (TR-45 Study C)
def _k_region(k):
    if k < 0.06:
        return 'k<0.06'
    elif k < 0.10:
        return '0.06≤k<0.10'
    else:
        return 'k≥0.10'


# Flag-rate thresholds for model-update trigger
_FP_RATE_THRESH   = 0.05   # 5%
_FN_RATE_THRESH   = 0.02   # 2%
_CONF_RATE_THRESH = 0.15   # 15%


class FlagEngine:
    """
    Accumulates and analyses decision comparison results.

    Parameters
    ----------
    on_trigger : callable or None
        Callback invoked when a flag-rate threshold is exceeded.
        Signature: on_trigger(flag_type, region, rate, summary)
        Default None (no callback).
    window : int
        Rolling window size for rate calculations.  Default 200 events.
    """

    def __init__(self, on_trigger=None, window=200):
        self.on_trigger = on_trigger
        self.window     = window

        # All results (circular buffer, capped at window)
        self._results  = []
        # Flagged results only — kept forever (audit log)
        self.flag_log  = []
        # Counts
        self._total    = 0
        self._verdict_counts = Counter()
        self._region_fp  = defaultdict(int)
        self._region_fn  = defaultdict(int)
        self._region_tot = defaultdict(int)

    # ------------------------------------------------------------------
    def record(self, result):
        """
        Record one comparison result.

        Parameters
        ----------
        result : dict — output of DecisionComparator.compare()
        """
        verdict = result.get('verdict', 'UNKNOWN')
        k_ibr   = result.get('k_ibr', 0.0)
        alpha   = result.get('alpha', 0.5)
        region  = _k_region(k_ibr)

        # Skip EXTERNAL events — outside zone, not a protection performance metric
        if result.get('relay_element') == 'EXTERNAL':
            return

        self._total += 1
        self._verdict_counts[verdict] += 1

        # Region tracking (only for internal-zone events)
        if alpha <= 1.0:
            self._region_tot[region] += 1
            if verdict == 'FLAG_FP':
                self._region_fp[region] += 1
            elif verdict == 'FLAG_FN':
                self._region_fn[region] += 1

        # Rolling buffer
        self._results.append(result)
        if len(self._results) > self.window:
            self._results.pop(0)

        # Audit log for flags
        if verdict.startswith('FLAG'):
            self.flag_log.append(result)

        # Check trigger thresholds
        self._check_triggers(region)

    # ------------------------------------------------------------------
    def summary(self):
        """
        Return a summary dict of flag counts and rates.

        Returns
        -------
        dict with keys:
            total, agree, flag_fp, flag_fn, flag_element, flag_conf,
            agree_rate, fp_rate, fn_rate,
            by_region: {region: {total, fp, fn, fp_rate, fn_rate}}
        """
        n = max(self._total, 1)
        agree = self._verdict_counts.get('AGREE', 0)
        fp    = self._verdict_counts.get('FLAG_FP', 0)
        fn    = self._verdict_counts.get('FLAG_FN', 0)
        fe    = self._verdict_counts.get('FLAG_ELEMENT', 0)
        fc    = self._verdict_counts.get('FLAG_CONF', 0)

        by_region = {}
        for reg in ['k<0.06', '0.06≤k<0.10', 'k≥0.10']:
            rt  = max(self._region_tot[reg], 1)
            rfp = self._region_fp[reg]
            rfn = self._region_fn[reg]
            by_region[reg] = {
                'total':   self._region_tot[reg],
                'fp':      rfp,
                'fn':      rfn,
                'fp_rate': rfp / rt,
                'fn_rate': rfn / rt,
            }

        return {
            'total':        self._total,
            'agree':        agree,
            'flag_fp':      fp,
            'flag_fn':      fn,
            'flag_element': fe,
            'flag_conf':    fc,
            'agree_rate':   agree / n,
            'fp_rate':      fp / n,
            'fn_rate':      fn / n,
            'by_region':    by_region,
        }

    # ------------------------------------------------------------------
    def reset(self):
        """Clear all accumulated data."""
        self._results        = []
        self.flag_log        = []
        self._total          = 0
        self._verdict_counts = Counter()
        self._region_fp      = defaultdict(int)
        self._region_fn      = defaultdict(int)
        self._region_tot     = defaultdict(int)

    # ------------------------------------------------------------------
    def _check_triggers(self, region):
        """Check flag-rate thresholds and fire callback if exceeded."""
        if self.on_trigger is None:
            return
        s = self.summary()
        # FP rate by region
        for reg, rdata in s['by_region'].items():
            if rdata['total'] >= 20:   # minimum sample size before triggering
                if rdata['fp_rate'] > _FP_RATE_THRESH:
                    self.on_trigger('FLAG_FP', reg, rdata['fp_rate'], s)
                if rdata['fn_rate'] > _FN_RATE_THRESH:
                    self.on_trigger('FLAG_FN', reg, rdata['fn_rate'], s)
        # Overall FLAG_CONF rate
        n = max(self._total, 1)
        conf_rate = self._verdict_counts.get('FLAG_CONF', 0) / n
        if conf_rate > _CONF_RATE_THRESH and self._total >= 20:
            self.on_trigger('FLAG_CONF', 'ALL', conf_rate, s)

    # ------------------------------------------------------------------
    def print_summary(self):
        """Print a formatted summary to stdout."""
        s = self.summary()
        n = max(s['total'], 1)
        print(f"\n  DT Flag Engine Summary (N={s['total']})")
        print(f"  {'─'*52}")
        print(f"  {'AGREE':>16s}: {s['agree']:>6d}  ({s['agree_rate']*100:.2f}%)")
        print(f"  {'FLAG_FP':>16s}: {s['flag_fp']:>6d}  ({s['fp_rate']*100:.2f}%)")
        print(f"  {'FLAG_FN':>16s}: {s['flag_fn']:>6d}  ({s['fn_rate']*100:.2f}%)")
        print(f"  {'FLAG_ELEMENT':>16s}: {s['flag_element']:>6d}")
        print(f"  {'FLAG_CONF':>16s}: {s['flag_conf']:>6d}")
        print(f"\n  By k_ibr region:")
        hdr = f"  {'Region':>18s} {'N':>6s} {'FP':>6s} {'FN':>6s} {'FP%':>8s} {'FN%':>8s}"
        print(hdr)
        print(f"  {'─'*52}")
        for reg, d in s['by_region'].items():
            print(f"  {reg:>18s} {d['total']:>6d} {d['fp']:>6d} {d['fn']:>6d} "
                  f"{d['fp_rate']*100:>8.2f} {d['fn_rate']*100:>8.2f}")
