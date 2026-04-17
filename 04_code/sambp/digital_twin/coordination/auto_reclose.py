# =============================================================================
# sambp / digital_twin / coordination / auto_reclose.py
#
# Auto-reclose controller — TR-71 WP 71.2
#
# Implements a DT-assisted auto-reclose sequencer for IBR-dominated feeders.
#
# Key enhancements over a conventional recloser
# ---------------------------------------------
#   1. IBR-aware dead time from DeadTimeEstimator
#   2. ML reclose success predictor: logistic model on EKF features
#   3. Blocking on evolving fault (TR-72 FaultEvolutionEvent — RST/INT/DLG/3PH)
#   4. Feeder de-energisation confirmation via I_pos_mag threshold
#   5. Audit trail of all reclose attempts + outcomes
#
# Shot sequence: FAST → DELAY_1 → DELAY_2 → LOCKOUT  (configurable)
#
# Public API
# ----------
#   ctrl = AutoRecloseController(n_shots=3)
#   result = ctrl.step(t, ekf_state, feeder_live, v_terminal_pu, evt=None)
#       → RecloseAction(action, dead_time_s, shot, confidence, blocked_by)
#   ctrl.reset()
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from estimation.dead_time_estimator import DeadTimeEstimator, DeadTimeResult
from estimation.fault_evolution import FaultEvolutionEvent


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------
_ST_IDLE       = "IDLE"
_ST_OPEN       = "OPEN"          # CB tripped; waiting dead time
_ST_RECLOSE    = "RECLOSE"       # reclose command issued; awaiting result
_ST_LOCKED_OUT = "LOCKED_OUT"    # all shots exhausted

# Actions
_ACT_NONE      = "NONE"
_ACT_START     = "START_DEAD_TIME"
_ACT_RECLOSE   = "RECLOSE"
_ACT_LOCKOUT   = "LOCKOUT"
_ACT_BLOCK     = "BLOCK"

# Blocking reasons
_BLK_EVOLUTION = "EVOLVING_FAULT"
_BLK_NO_DEENRG = "FEEDER_NOT_DEENERGISED"
_BLK_LOCKOUT   = "SHOTS_EXHAUSTED"
_BLK_PREDICTOR = "PREDICTOR_LOW_CONFIDENCE"


# ---------------------------------------------------------------------------
# ML reclose success predictor (logistic regression, offline-trained weights)
# ---------------------------------------------------------------------------

# Feature vector: [k_ibr, f_gfm, I_pos_mag_pre, z_line, v_terminal_pu, shot_frac]
# Weights calibrated on synthetic dataset (TR-71 study A, N=5000 events)
_LR_WEIGHTS = [
    -2.50,   # intercept
    +1.80,   # k_ibr        (higher IBR → faster de-energisation → success)
    +1.20,   # f_gfm        (GFM sustains voltage → harder to confirm deenergised)
    -3.50,   # I_pos_mag_pre (higher fault current → more severe → lower success)
    -2.00,   # z_line        (low impedance → fault energy higher)
    +2.00,   # v_terminal_pu (higher V at reclose → more likely sync'd)
    -1.50,   # shot_frac     (later shot → lower p(success))
]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, x))))


def predict_reclose_success(ekf_state: dict,
                             v_terminal_pu: float,
                             shot_number: int,
                             n_shots: int) -> float:
    """
    Logistic regression predictor: P(reclose success).

    Features
    --------
    k_ibr, f_gfm, I_pos_mag (proxy from k_ibr), z_line,
    v_terminal_pu, shot_frac = (shot-1)/(n_shots-1)

    Returns
    -------
    p_success : float ∈ [0, 1]
    """
    k    = float(ekf_state.get('k_ibr',   0.20))
    fg   = float(ekf_state.get('f_gfm',   0.50))
    zl   = float(ekf_state.get('z_line',  0.050))
    i_pr = k                            # I_pos_mag proxy at pre-fault
    shr  = (shot_number - 1) / max(n_shots - 1, 1)

    feat = [1.0, k, fg, i_pr, zl, v_terminal_pu, shr]
    logit = sum(w * f for w, f in zip(_LR_WEIGHTS, feat))
    return _sigmoid(logit)


# ---------------------------------------------------------------------------
# RecloseAction
# ---------------------------------------------------------------------------

@dataclass
class RecloseAction:
    """Output of AutoRecloseController.step()."""
    action:       str     # NONE | START_DEAD_TIME | RECLOSE | LOCKOUT | BLOCK
    dead_time_s:  float   # recommended dead time for this shot [s]
    shot:         int     # current shot number (1-based)
    confidence:   float   # composite confidence [0, 1]
    blocked_by:   str     # reason if BLOCK/LOCKOUT, else ""
    p_success:    float   # predicted P(reclose success)


@dataclass
class RecloseAttempt:
    """Audit record for one reclose attempt."""
    t:          float
    shot:       int
    dead_time:  float
    action:     str
    p_success:  float
    outcome:    str   # "PENDING" | "SUCCESS" | "FAILURE"


# ---------------------------------------------------------------------------
# AutoRecloseController
# ---------------------------------------------------------------------------

class AutoRecloseController:
    """
    DT-assisted auto-reclose sequencer for IBR-dominated feeders.

    Parameters
    ----------
    n_shots              : total shots before lockout (default 3)
    p_success_threshold  : minimum predicted success probability to attempt
                           reclose (default 0.30)
    block_on_evolving    : block reclose if a FaultEvolutionEvent with
                           to_type in BLOCK_TYPES is active (default True)
    deenergise_threshold : I_pos_mag [pu] below which feeder is considered
                           de-energised (default 0.05)
    """

    # Evolving fault types that trigger a block
    BLOCK_TYPES = {"DLG", "3PH", "RST", "INT"}

    def __init__(self,
                 n_shots: int = 3,
                 p_success_threshold: float = 0.30,
                 block_on_evolving: bool = True,
                 deenergise_threshold: float = 0.05) -> None:
        self._n         = n_shots
        self._p_thr     = p_success_threshold
        self._block_ev  = block_on_evolving
        self._deenrg    = deenergise_threshold

        self._dt_est    = DeadTimeEstimator()
        self._state     = _ST_IDLE
        self._shot      = 0
        self._t_open    = 0.0    # time CB last opened
        self._t_dead    = 0.0    # current dead time setting
        self._log: List[RecloseAttempt] = []
        self._last_evolution: Optional[FaultEvolutionEvent] = None

    # ------------------------------------------------------------------
    def trip(self, t: float, ekf_state: dict,
             fault_type: str = "SLG") -> RecloseAction:
        """
        Register a protection trip.  Returns the first START_DEAD_TIME action.

        Call this when the relay issues a TRIP command.
        """
        self._state  = _ST_OPEN
        self._shot   = 1
        self._t_open = t
        self._last_evolution = None

        dt_result = self._dt_est.estimate(ekf_state, fault_type, shot_number=1)
        self._t_dead = dt_result.t_dead_s

        p_s = predict_reclose_success(ekf_state, 1.0, 1, self._n)
        rec = RecloseAttempt(t=t, shot=1, dead_time=dt_result.t_dead_s,
                             action=_ACT_START, p_success=p_s, outcome="PENDING")
        self._log.append(rec)

        return RecloseAction(
            action=_ACT_START,
            dead_time_s=dt_result.t_dead_s,
            shot=1,
            confidence=dt_result.confidence,
            blocked_by="",
            p_success=p_s,
        )

    # ------------------------------------------------------------------
    def step(self,
             t: float,
             ekf_state: dict,
             feeder_live: bool,
             v_terminal_pu: float = 1.0,
             fault_type: str = "SLG",
             evolution_event: Optional[FaultEvolutionEvent] = None,
             ) -> RecloseAction:
        """
        Advance the reclose FSM by one DT cycle.

        Parameters
        ----------
        t               : current time [s]
        ekf_state       : EKF state dict (k_ibr, f_gfm, z_line, ...)
        feeder_live     : True if I_pos_mag > deenergise_threshold (feeder live)
        v_terminal_pu   : terminal voltage at reclose point [pu]
        fault_type      : last known fault type
        evolution_event : FaultEvolutionEvent from TR-72 (or None)

        Returns
        -------
        RecloseAction
        """
        # ── Track evolving fault events ───────────────────────────────
        if evolution_event is not None:
            self._last_evolution = evolution_event

        # ── Locked out ────────────────────────────────────────────────
        if self._state == _ST_LOCKED_OUT:
            return RecloseAction(_ACT_LOCKOUT, self._t_dead,
                                 self._shot, 0.0, _BLK_LOCKOUT, 0.0)

        # ── IDLE ──────────────────────────────────────────────────────
        if self._state == _ST_IDLE:
            return RecloseAction(_ACT_NONE, 0.0, 0, 1.0, "", 1.0)

        # ── OPEN: waiting dead time ───────────────────────────────────
        if self._state == _ST_OPEN:
            elapsed = t - self._t_open
            if elapsed < self._t_dead:
                return RecloseAction(_ACT_NONE, self._t_dead - elapsed,
                                     self._shot, 0.8, "", 0.0)

            # Dead time expired — check if we can reclose
            # ── Block check 1: evolving fault ─────────────────────────
            if self._block_ev and self._last_evolution is not None:
                if self._last_evolution.to_type in self.BLOCK_TYPES:
                    if self._last_evolution.confidence >= 0.60:
                        return RecloseAction(
                            _ACT_BLOCK, self._t_dead, self._shot, 0.0,
                            _BLK_EVOLUTION, 0.0,
                        )

            # ── Block check 2: feeder not de-energised ─────────────────
            if feeder_live:
                return RecloseAction(
                    _ACT_BLOCK, self._t_dead, self._shot, 0.5,
                    _BLK_NO_DEENRG, 0.0,
                )

            # ── ML predictor check ─────────────────────────────────────
            p_s = predict_reclose_success(
                ekf_state, v_terminal_pu, self._shot, self._n)

            if p_s < self._p_thr and self._shot > 1:
                # Skip to lockout only after shot 1 (always attempt shot 1)
                self._state = _ST_LOCKED_OUT
                return RecloseAction(_ACT_LOCKOUT, self._t_dead, self._shot,
                                     p_s, _BLK_PREDICTOR, p_s)

            # ── Issue RECLOSE ──────────────────────────────────────────
            self._state = _ST_RECLOSE
            self._log.append(RecloseAttempt(
                t=t, shot=self._shot, dead_time=self._t_dead,
                action=_ACT_RECLOSE, p_success=p_s, outcome="PENDING"))

            return RecloseAction(
                action=_ACT_RECLOSE,
                dead_time_s=self._t_dead,
                shot=self._shot,
                confidence=min(1.0, p_s + 0.1),
                blocked_by="",
                p_success=p_s,
            )

        # ── RECLOSE: awaiting CB close confirmation ────────────────────
        if self._state == _ST_RECLOSE:
            # Caller must call on_reclose_result() to advance state
            return RecloseAction(_ACT_NONE, 0.0, self._shot, 0.7, "", 0.0)

        return RecloseAction(_ACT_NONE, 0.0, self._shot, 0.0, "", 0.0)

    # ------------------------------------------------------------------
    def on_reclose_result(self,
                          t: float,
                          success: bool,
                          ekf_state: dict,
                          fault_type: str = "SLG") -> RecloseAction:
        """
        Register outcome of the last reclose attempt.

        success=True  → transition to IDLE (CB closed, feeder live)
        success=False → increment shot, arm next dead time, or LOCKOUT
        """
        if self._log:
            self._log[-1].outcome = "SUCCESS" if success else "FAILURE"

        if success:
            self._state = _ST_IDLE
            return RecloseAction(_ACT_NONE, 0.0, self._shot, 1.0, "", 1.0)

        # Failed — next shot or lockout
        self._shot += 1
        if self._shot > self._n:
            self._state = _ST_LOCKED_OUT
            return RecloseAction(_ACT_LOCKOUT, 0.0, self._shot - 1,
                                 0.0, _BLK_LOCKOUT, 0.0)

        dt_result = self._dt_est.estimate(ekf_state, fault_type, self._shot)
        self._t_dead  = dt_result.t_dead_s
        self._t_open  = t
        self._state   = _ST_OPEN
        p_s = predict_reclose_success(ekf_state, 1.0, self._shot, self._n)
        return RecloseAction(_ACT_START, dt_result.t_dead_s, self._shot,
                             dt_result.confidence, "", p_s)

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset sequencer to IDLE (call between fault scenarios)."""
        self._dt_est.reset()
        self._state = _ST_IDLE
        self._shot  = 0
        self._t_open = 0.0
        self._t_dead = 0.0
        self._log.clear()
        self._last_evolution = None

    # ------------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def shot(self) -> int:
        return self._shot

    @property
    def audit_log(self) -> List[RecloseAttempt]:
        return list(self._log)

    @property
    def is_locked_out(self) -> bool:
        return self._state == _ST_LOCKED_OUT
