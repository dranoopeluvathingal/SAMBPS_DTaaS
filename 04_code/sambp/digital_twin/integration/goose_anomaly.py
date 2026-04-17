# =============================================================================
# sambp / digital_twin / integration / goose_anomaly.py
#
# GOOSE anomaly detector — TR-82 WP 82.1
#
# GOOSE (Generic Object Oriented Substation Event) per IEC 61850-8-1:
#   • Multicast, publisher-subscriber
#   • Trip / protection signals travel in <4 ms (T1 retransmission)
#   • Retransmission schedule: T1, T2, T3, …, T_stable (doubling back to T0)
#   • StNum (StateNumber): increments on every new event
#   • SqNum (SequenceNumber): increments with each retransmission in the burst
#
# Attack taxonomy and detection strategy
# ----------------------------------------
# REPLAY         : Old message with valid stnum/sqnum replayed later.
#                  Detect: received timestamp >> message timestamp; stnum
#                  not advancing beyond last seen.
# INJECTION      : Fabricated message with arbitrary data.
#                  Detect: HMAC failure (WP 82.2) OR isolation forest outlier.
# TIMING_FLOOD   : Attacker sends messages too fast to exhaust switch buffers.
#                  Detect: inter-arrival < T_min threshold.
# SEQUENCE_SKIP  : stnum jumps by >1 or sqnum is non-monotone within a burst.
#                  Detect: stnum/sqnum discontinuity rules.
# CONTENT        : Dataset values outside learned normal range.
#                  Detect: Isolation Forest on feature vector of (interval,
#                  stnum_delta, sqnum_delta, dataset_hash_bucket).
#
# ML Model — Isolation Forest
# ----------------------------
# Feature vector per message:
#   f0 = inter_arrival_ms          (time between consecutive messages)
#   f1 = stnum_delta                (0 = retransmission, 1 = new event)
#   f2 = sqnum_expected_delta       (1 if correct, else deviation)
#   f3 = retx_interval_normalised   (inter_arrival / expected_retx)
#   f4 = dataset_entropy            (Shannon entropy of dataset bytes)
#
# Train on ≥200 normal messages, then score each incoming message.
# contamination=0.005 (0.5%) → <1% false-positive rate.
#
# Public API
# ----------
#   det = GOOSEAnomalyDetector(app_id=0x0001, T0_ms=4000, T1_ms=2)
#   det.train(normal_messages)         ← fit isolation forest
#   result = det.detect(msg, t_recv)   → GOOSEAnomalyResult
#   det.reset()
# =============================================================================

from __future__ import annotations

import hashlib
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# GOOSE message structure
# ---------------------------------------------------------------------------

@dataclass
class GOOSEMessage:
    """Represents one received GOOSE PDU."""
    gocb_ref:   str            # GOOSE control block reference
    app_id:     int            # application ID
    stnum:      int            # state number (increments on new event)
    sqnum:      int            # sequence number (increments per retransmission)
    t_msg_ms:   float          # message timestamp [ms since epoch]
    dataset:    List           # dataset payload (list of values)
    time_to_live_ms: float = 4000.0  # T0 = stable retransmission interval [ms]
    hmac_tag:   Optional[bytes] = None  # HMAC-SHA256 authentication tag (if present)


# ---------------------------------------------------------------------------
# GOOSEAnomalyResult
# ---------------------------------------------------------------------------

@dataclass
class GOOSEAnomalyResult:
    """Detection result for one GOOSE message."""
    t_recv_ms:    float
    app_id:       int
    stnum:        int
    sqnum:        int
    anomaly:      bool           # True = anomaly detected
    attack_types: List[str]      # detected attack types
    if_score:     float          # isolation forest anomaly score (lower = more anomalous)
    feature_vec:  List[float]    # feature vector used for IF
    severity:     str            # "NONE" | "LOW" | "HIGH" | "CRITICAL"
    reason:       str


# ---------------------------------------------------------------------------
# Internal state for sequence tracking
# ---------------------------------------------------------------------------

@dataclass
class _PublisherState:
    last_stnum:       int   = 0
    last_sqnum:       int   = 0
    last_t_recv_ms:   float = 0.0
    last_t_msg_ms:    float = 0.0
    event_in_progress: bool = False
    retx_count:       int   = 0


# ---------------------------------------------------------------------------
# GOOSEAnomalyDetector
# ---------------------------------------------------------------------------

class GOOSEAnomalyDetector:
    """
    GOOSE anomaly detector with rule-based + Isolation Forest detection.

    Parameters
    ----------
    app_id          : expected GOOSE application ID
    T0_ms           : stable-state retransmission interval [ms] (default 4000)
    T1_ms           : first burst retransmission interval [ms] (default 2)
    flood_threshold_ms : minimum allowed inter-arrival [ms] (below = flood)
    max_replay_age_ms  : message timestamp older than this → replay alert [ms]
    contamination      : IF contamination parameter (default 0.005 = 0.5%)
    """

    def __init__(self,
                 app_id: int,
                 T0_ms: float = 4000.0,
                 T1_ms: float = 2.0,
                 flood_threshold_ms: float = 0.5,
                 max_replay_age_ms:  float = 5000.0,
                 contamination: float = 0.005) -> None:
        self._app_id      = app_id
        self._T0          = T0_ms
        self._T1          = T1_ms
        self._flood_thr   = flood_threshold_ms
        self._replay_age  = max_replay_age_ms
        self._contamination = contamination

        self._pub: Dict[str, _PublisherState] = {}
        self._if_model = None
        self._trained  = False

        # Collect features during normal training window
        self._train_buf: List[List[float]] = []
        # Learned dataset range bounds (3-sigma from training)
        self._max_log_range: float = float("inf")

    # ------------------------------------------------------------------
    def train(self, normal_messages: List[Tuple[GOOSEMessage, float]]) -> None:
        """
        Fit Isolation Forest on normal traffic.

        Parameters
        ----------
        normal_messages : list of (GOOSEMessage, t_recv_ms) tuples
        """
        if len(normal_messages) < 10:
            return

        feats = []
        state: Dict[str, _PublisherState] = {}

        for msg, t_recv in normal_messages:
            fv = self._extract_features(msg, t_recv, state)
            feats.append(fv)

        X = np.array(feats, dtype=float)
        # Replace NaN/Inf with column medians
        for col in range(X.shape[1]):
            bad = ~np.isfinite(X[:, col])
            if bad.any():
                med = float(np.median(X[~bad, col])) if not bad.all() else 0.0
                X[bad, col] = med

        from sklearn.ensemble import IsolationForest
        self._if_model = IsolationForest(
            n_estimators=100,
            contamination=self._contamination,
            random_state=42,
        )
        self._if_model.fit(X)
        self._trained = True
        # Learn max expected log_range (f4) as mean + 3σ of training data
        f4 = X[:, 4]
        self._max_log_range = float(np.mean(f4) + 3.0 * max(np.std(f4), 1e-6))

    # ------------------------------------------------------------------
    def detect(self, msg: GOOSEMessage, t_recv_ms: float) -> GOOSEAnomalyResult:
        """
        Evaluate one incoming GOOSE message for anomalies.

        Parameters
        ----------
        msg        : received GOOSE message
        t_recv_ms  : receive timestamp [ms]
        """
        attacks: List[str] = []

        # ── App-ID filter ────────────────────────────────────────────────
        if msg.app_id != self._app_id:
            # Could be injection from different publisher
            attacks.append("WRONG_APP_ID")

        key = msg.gocb_ref
        if key not in self._pub:
            self._pub[key] = _PublisherState()
        ps = self._pub[key]

        inter_arr = t_recv_ms - ps.last_t_recv_ms if ps.last_t_recv_ms > 0 else self._T0

        # ── REPLAY detection ─────────────────────────────────────────────
        age = t_recv_ms - msg.t_msg_ms
        if age > self._replay_age and ps.last_t_recv_ms > 0:
            attacks.append("REPLAY")
        # StNum went backwards
        if msg.stnum < ps.last_stnum:
            attacks.append("REPLAY")

        # ── SEQUENCE_SKIP detection ──────────────────────────────────────
        stnum_delta = msg.stnum - ps.last_stnum
        sqnum_delta = msg.sqnum - ps.last_sqnum

        if stnum_delta == 0:
            # Same event: sqnum should increment by 1
            if ps.last_t_recv_ms > 0 and sqnum_delta != 1:
                if sqnum_delta < 0:
                    attacks.append("SEQUENCE_SKIP")
                elif sqnum_delta > 5:
                    attacks.append("SEQUENCE_SKIP")
        elif stnum_delta == 1:
            # New event: sqnum resets to 0 or 1
            if msg.sqnum > 5:
                attacks.append("SEQUENCE_SKIP")
        elif stnum_delta > 1:
            # Missed events — possible packet loss or injection
            if stnum_delta > 3:
                attacks.append("SEQUENCE_SKIP")

        # ── TIMING_FLOOD detection ────────────────────────────────────────
        if inter_arr < self._flood_thr and ps.last_t_recv_ms > 0:
            attacks.append("TIMING_FLOOD")

        # ── Feature extraction + Isolation Forest ────────────────────────
        # update_state=True so ps is updated for next call
        fv = self._extract_features(msg, t_recv_ms, self._pub, update_state=True)

        if_score = 0.0
        if self._trained and self._if_model is not None:
            X_pred = np.array([fv], dtype=float)
            X_pred = np.nan_to_num(X_pred, nan=0.0, posinf=10.0, neginf=-10.0)
            if_score = float(self._if_model.score_samples(X_pred)[0])
            decision = float(self._if_model.decision_function(X_pred)[0])
            # IF outlier OR dataset range exceeds learned 3σ bound
            if decision < 0 or fv[4] > self._max_log_range:
                attacks.append("CONTENT_ANOMALY")

        # ── Build result ──────────────────────────────────────────────────
        anomaly  = len(attacks) > 0
        severity = self._severity(attacks)

        return GOOSEAnomalyResult(
            t_recv_ms=t_recv_ms,
            app_id=msg.app_id,
            stnum=msg.stnum,
            sqnum=msg.sqnum,
            anomaly=anomaly,
            attack_types=attacks,
            if_score=round(if_score, 5),
            feature_vec=[round(f, 4) for f in fv],
            severity=severity,
            reason=(", ".join(attacks) if attacks else "Normal GOOSE traffic"),
        )

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._pub.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_features(self,
                           msg: GOOSEMessage,
                           t_recv_ms: float,
                           state: Dict[str, _PublisherState],
                           update_state: bool = True) -> List[float]:
        key = msg.gocb_ref
        if key not in state:
            state[key] = _PublisherState()
        ps = state[key]

        inter_arr = (t_recv_ms - ps.last_t_recv_ms
                     if ps.last_t_recv_ms > 0 else self._T0)

        stnum_delta  = msg.stnum - ps.last_stnum
        sqnum_delta  = msg.sqnum - ps.last_sqnum if ps.last_t_recv_ms > 0 else 1

        # Expected retransmission interval based on sqnum in burst
        if msg.sqnum > 0 and self._T1 > 0:
            exp_retx = min(self._T1 * (2 ** min(msg.sqnum - 1, 10)), self._T0)
        else:
            exp_retx = self._T0
        retx_norm = inter_arr / max(exp_retx, 1e-3)

        dataset_entropy = self._dataset_entropy(msg.dataset)
        dataset_log_range = self._dataset_log_range(msg.dataset)

        # Log-normalised timing: ~0 for normal, large for flooding/slow
        log_retx_norm = math.log(max(retx_norm, 1e-6) + 1.0)

        # Update state in place so next call has correct deltas
        if update_state:
            ps.last_stnum    = msg.stnum
            ps.last_sqnum    = msg.sqnum
            ps.last_t_recv_ms = t_recv_ms
            ps.last_t_msg_ms  = msg.t_msg_ms

        return [
            float(abs(stnum_delta)),           # f0: state number change
            float(abs(sqnum_delta - 1)),        # f1: sqnum deviation from +1
            min(log_retx_norm, 10.0),           # f2: log(inter_arr/expected+1)
            dataset_entropy,                    # f3: dataset Shannon entropy
            dataset_log_range,                  # f4: log(1 + numeric range) — detects extreme values
        ]

    @staticmethod
    def _dataset_log_range(dataset: List) -> float:
        """Log(1 + numeric range) of dataset values — captures extreme injected values."""
        nums = []
        for v in dataset:
            try:
                nums.append(float(v))
            except (TypeError, ValueError):
                pass
        if len(nums) < 2:
            return 0.0
        return math.log1p(max(nums) - min(nums))

    @staticmethod
    def _dataset_entropy(dataset: List) -> float:
        """Shannon entropy of dataset byte representation."""
        if not dataset:
            return 0.0
        raw = str(dataset).encode()
        if len(raw) < 2:
            return 0.0
        counts = np.bincount(np.frombuffer(raw, dtype=np.uint8), minlength=256)
        probs  = counts / counts.sum()
        probs  = probs[probs > 0]
        return float(-np.sum(probs * np.log2(probs)))

    @staticmethod
    def _severity(attacks: List[str]) -> str:
        if not attacks:
            return "NONE"
        if "TIMING_FLOOD" in attacks or "REPLAY" in attacks:
            return "CRITICAL"
        if "CONTENT_ANOMALY" in attacks or "SEQUENCE_SKIP" in attacks:
            return "HIGH"
        return "LOW"
